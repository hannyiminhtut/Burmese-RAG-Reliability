"""Generate answers for the frozen 15-question development pilot only."""

from __future__ import annotations

import argparse
import ctypes
import csv
import hashlib
import json
import logging
import os
import re
import time
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import yaml

from src.evaluate_retrieval import load_benchmark, load_pilot_intents, select_fixed_pilot
from src.ollama_client import (
    OllamaClient, OllamaConnectionError, OllamaError, OllamaModelError,
    OllamaResponseError, OllamaTimeoutError,
)


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "uit-context-only-json-v3"
PARSER_VERSION = "uit-citation-object-parser-v3"
ABSTENTION_RESPONSE = (
    "The provided academic regulations do not contain sufficient information "
    "to answer the question."
)
DEFAULT_MODEL = "gemma3:4b-it-q4_K_M"
DEFAULT_BASE_URL = "http://localhost:11434"
GENERATION_SETTINGS = {
    "temperature": 0,
    "top_p": 0.9,
    "top_k": 40,
    "seed": 42,
    "num_ctx": 4096,
    "num_predict": 512,
}
RESOURCE_PROFILE_VERSION = "uit-cpu-safe-v1"
RESOURCE_SAFETY_MARGIN_TOKENS = 1024
MAX_INFRASTRUCTURE_ATTEMPTS = 2
RETRY_COOLDOWN_SECONDS = 5.0
REQUIRED_OLLAMA_ENVIRONMENT = {
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_MAX_LOADED_MODELS": "1",
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["ANSWER", "ABSTAIN"]},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["chunk_id", "page"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decision", "answer", "citations"],
    "additionalProperties": False,
}
CSV_COLUMNS = [
    "run_id", "intent_id", "variant_id", "language_condition",
    "answerability", "question", "generated_answer", "decision",
    "cited_chunk_ids", "cited_pages", "citations", "retrieved_chunk_ids",
    "retrieved_pages", "generation_model", "prompt_version", "parser_version",
    "generation_settings", "total_runtime_seconds", "load_duration_ns",
    "prompt_eval_duration_ns", "eval_duration_ns", "ollama_total_duration_ns",
    "raw_response", "parsed_response", "raw_model_response", "raw_ollama_response",
    "parsed_model_output", "original_citations",
    "citation_type_normalized", "original_page_value", "normalized_page_value",
    "citation_normalizations", "abstention_decision", "abstention_wording_compliant",
    "resource_profile_version", "prompt_token_count", "prompt_token_count_source",
    "selected_num_ctx", "selected_num_predict", "attempt_count", "attempt_history",
    "http_status", "infrastructure_error", "infrastructure_error_class",
    "valid_model_response_received", "available_memory_before_request_bytes",
    "validation_stage", "validation_error", "error_status", "error_notes",
]


class GenerationSchemaError(OllamaResponseError):
    """Structured model output violated the v2 contract."""

    def __init__(self, message: str, parsed_output: Any) -> None:
        super().__init__(message)
        self.parsed_output = parsed_output


def estimate_prompt_tokens(prompt: str) -> int:
    """Return a calibrated pre-request heuristic, not a tokenizer measurement."""
    return math.ceil((len(prompt.encode("utf-8")) / 4) * 1.10)


def available_memory_bytes() -> Any:
    """Return available physical memory on Windows without adding a dependency."""
    try:
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.available_physical)
    except (AttributeError, OSError, ValueError):
        pass
    return None


def classify_infrastructure_error(exc: BaseException) -> Any:
    """Classify only failures eligible for the bounded infrastructure retry."""
    message = str(exc).lower()
    if isinstance(exc, OllamaModelError) and getattr(exc, "status_code", None) == 500:
        if "bad_alloc" in message or "ggml_assert" in message:
            return "model_runner_memory_allocation_failure"
        if "model runner has unexpectedly stopped" in message:
            return "model_runner_unexpected_stop"
    if isinstance(exc, OllamaTimeoutError):
        return "ollama_timeout"
    if isinstance(exc, OllamaConnectionError):
        return "ollama_connection_failure"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _load_metadata(config: Dict[str, Any], root: Path) -> List[Dict[str, Any]]:
    try:
        metadata_path = _resolve(root, config["index"]["metadata_file"])
    except KeyError as exc:
        raise ValueError("Generation requires config.index.metadata_file") from exc
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, list):
        raise ValueError("Retrieval metadata must be a JSON array")
    return metadata


def load_pilot_inputs(
    config_path: Path,
    pilot_intents_path: Path,
    retrieval_results_path: Path,
) -> Dict[str, Any]:
    """Load and cross-check the immutable benchmark, split, retrieval, and evidence."""
    config_path = config_path.resolve()
    root = config_path.parent.parent
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    benchmark_path = _resolve(root, config["benchmark"]["file"])
    benchmark = load_benchmark(benchmark_path)
    pilot_ids = load_pilot_intents(pilot_intents_path)
    pilot_rows = select_fixed_pilot(benchmark, pilot_ids)
    benchmark_by_variant = {row["variant_id"]: row for row in pilot_rows}

    with retrieval_results_path.open("r", encoding="utf-8-sig", newline="") as stream:
        retrieval_rows = list(csv.DictReader(stream))
    if len(retrieval_rows) != 15:
        raise ValueError(f"Expected 15 pilot retrieval rows, found {len(retrieval_rows)}")
    if {row["intent_id"] for row in retrieval_rows} != set(pilot_ids):
        raise ValueError("Retrieval rows do not match the fixed pilot intent IDs")

    metadata = _load_metadata(config, root)
    metadata_by_id = {item["chunk_id"]: item for item in metadata}
    inputs = []
    for retrieval in retrieval_rows:
        variant_id = retrieval["variant_id"]
        if variant_id not in benchmark_by_variant:
            raise ValueError(f"Non-pilot retrieval variant found: {variant_id}")
        benchmark_row = benchmark_by_variant[variant_id]
        if retrieval["question"] != benchmark_row["question"]:
            raise ValueError(f"Question mismatch for {variant_id}")
        chunk_ids = json.loads(retrieval["retrieved_chunk_ids"])
        if not isinstance(chunk_ids, list) or len(chunk_ids) != 5:
            raise ValueError(f"{variant_id} must supply exactly 5 retrieved chunks")
        chunks = []
        for chunk_id in chunk_ids:
            if chunk_id not in metadata_by_id:
                raise ValueError(f"Unknown retrieved chunk ID: {chunk_id}")
            chunks.append(metadata_by_id[chunk_id])
        inputs.append({"benchmark": benchmark_row, "retrieval": retrieval, "chunks": chunks})

    if len({item["benchmark"]["intent_id"] for item in inputs}) != 5:
        raise ValueError("Selected questions must contain exactly 5 pilot intents")
    heldout_count = sum(item["benchmark"]["intent_id"] not in set(pilot_ids) for item in inputs)
    if heldout_count:
        raise ValueError(f"Held-out questions selected: {heldout_count}")
    return {
        "config": config,
        "root": root,
        "benchmark_path": benchmark_path,
        "metadata_path": _resolve(root, config["index"]["metadata_file"]),
        "pilot_ids": pilot_ids,
        "inputs": inputs,
        "selected_question_count": len(inputs),
        "heldout_question_count": heldout_count,
    }


def build_prompt(item: Dict[str, Any]) -> str:
    benchmark = item["benchmark"]
    language_rules = {
        "EN": "Answer in English.",
        "MY": "Answer in Myanmar (Burmese).",
        "MIX": "Answer in natural Burmese-English mixed language.",
    }
    evidence_blocks = []
    for index, chunk in enumerate(item["chunks"], 1):
        evidence_blocks.append(
            f"EVIDENCE_{index}\n"
            f"chunk_id: {chunk['chunk_id']}\n"
            f"page: {int(chunk['page'])}\n"
            f"text:\n{chunk['text']}\n"
            f"END_EVIDENCE_{index}"
        )
    return (
        f"PROMPT_VERSION: {PROMPT_VERSION}\n"
        "You are a context-only assistant for UIT academic regulations.\n"
        "Use only the five evidence chunks below. Do not use external, prior, or "
        "parametric knowledge. Do not infer facts absent from the evidence.\n"
        f"{language_rules[benchmark['language_condition']]}\n"
        "If evidence is insufficient, set decision to ABSTAIN, set answer exactly to:\n"
        f"{ABSTENTION_RESPONSE}\n"
        "For ABSTAIN, copy the configured response exactly. Add no explanation, "
        "prefix, suffix, translation, or citation.\n"
        "For ANSWER, citations must contain at least one object shaped exactly as "
        '{"chunk_id":"<id>","page":<integer>}. A chunk_id and page are an '
        "inseparable pair. Copy both values from the same supplied EVIDENCE block. "
        "Never combine a chunk_id from one block with a page from another block. "
        "Use a JSON integer for page, never a string.\n"
        "Valid ANSWER shape example (EXAMPLE-ONLY and 123 are schematic and must never be copied):\n"
        '{"decision":"ANSWER","answer":"Supported answer.","citations":'
        '[{"chunk_id":"EXAMPLE-ONLY","page":123}]}\n'
        "Valid ABSTAIN JSON example:\n"
        f'{json.dumps({"decision": "ABSTAIN", "answer": ABSTENTION_RESPONSE, "citations": []}, ensure_ascii=False)}\n'
        "Return one JSON object only, with no Markdown or additional text.\n"
        f"LANGUAGE_CONDITION: {benchmark['language_condition']}\n"
        f"QUESTION: {benchmark['question']}\n"
        "EVIDENCE_TOP_5_BEGIN\n"
        + "\n\n".join(evidence_blocks)
        + "\nEVIDENCE_TOP_5_END"
    )


def parse_generation(text: str) -> Dict[str, Any]:
    """Parse v2 output, explicitly normalizing digit-only page strings.

    Normalization is intentionally observable in ``citation_normalizations``;
    values such as ``page 8``, ``8-9``, floats, booleans, and null are rejected.
    """
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OllamaResponseError("Model response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise GenerationSchemaError("Model output must be a JSON object", result)
    required = {"decision", "answer", "citations"}
    missing = required - set(result)
    if missing:
        raise GenerationSchemaError(
            "Model output missing field(s): " + ", ".join(sorted(missing)), result
        )
    if result["decision"] not in {"ANSWER", "ABSTAIN"}:
        raise GenerationSchemaError("Model decision must be ANSWER or ABSTAIN", result)
    if not isinstance(result["answer"], str):
        raise GenerationSchemaError("Model answer must be a string", result)
    if not isinstance(result["citations"], list):
        raise GenerationSchemaError("Model citations must be an array", result)
    parsed = dict(result)
    parsed["citations"] = []
    parsed["citation_normalizations"] = []
    for index, citation in enumerate(result["citations"]):
        if not isinstance(citation, dict) or set(citation) != {"chunk_id", "page"}:
            raise GenerationSchemaError(
                f"Citation {index} must contain exactly chunk_id and page", result
            )
        if not isinstance(citation["chunk_id"], str) or not citation["chunk_id"]:
            raise GenerationSchemaError(
                f"Citation {index} chunk_id must be a non-empty string", result
            )
        original_page = citation["page"]
        normalized_page = original_page
        if isinstance(original_page, str) and re.fullmatch(r"[0-9]+", original_page):
            normalized_page = int(original_page)
            parsed["citation_normalizations"].append({
                "citation_index": index,
                "chunk_id": citation["chunk_id"],
                "original_page_value": original_page,
                "normalized_page_value": normalized_page,
            })
        elif not isinstance(original_page, int) or isinstance(original_page, bool):
            raise GenerationSchemaError(
                f"Citation {index} page must be a JSON integer or digit-only string; "
                f"received {original_page!r}", result
            )
        parsed["citations"].append({
            "chunk_id": citation["chunk_id"], "page": normalized_page
        })
    parsed["cited_chunk_ids"] = [item["chunk_id"] for item in parsed["citations"]]
    parsed["cited_pages"] = [item["page"] for item in parsed["citations"]]
    parsed["_original_parsed_response"] = result
    return parsed


def validate_citations(generation: Dict[str, Any], chunks: Sequence[Dict[str, Any]]) -> None:
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    citations = generation["citations"]
    if generation["decision"] == "ABSTAIN":
        if generation["answer"] != ABSTENTION_RESPONSE:
            raise ValueError("ABSTAIN answer does not match the deterministic response")
        if citations:
            raise ValueError("ABSTAIN response must not contain citations")
        return
    if not generation["answer"].strip():
        raise ValueError("ANSWER response must contain an answer")
    if not citations:
        raise ValueError("ANSWER must contain at least one citation")
    for citation in citations:
        chunk_id, page = citation["chunk_id"], citation["page"]
        if chunk_id not in chunk_map:
            raise ValueError(f"Invented or unsupplied chunk citation: {chunk_id}")
        if not isinstance(page, int) or isinstance(page, bool):
            raise ValueError(f"Citation page must be an integer for {chunk_id}")
        valid_pages = chunk_map[chunk_id].get("pages", [chunk_map[chunk_id]["page"]])
        if page not in valid_pages:
            raise ValueError(f"Citation page {page} does not match chunk {chunk_id}")


def _base_record(run_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    benchmark = item["benchmark"]
    retrieval = item["retrieval"]
    return {
        "run_id": run_id,
        "intent_id": benchmark["intent_id"],
        "variant_id": benchmark["variant_id"],
        "language_condition": benchmark["language_condition"],
        "answerability": benchmark["answerability"],
        "question": benchmark["question"],
        "generated_answer": "",
        "decision": "",
        "cited_chunk_ids": [],
        "cited_pages": [],
        "citations": [],
        "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in item["chunks"]],
        "retrieved_pages": [chunk.get("pages", [chunk["page"]]) for chunk in item["chunks"]],
        "generation_model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "parser_version": PARSER_VERSION,
        "generation_settings": dict(GENERATION_SETTINGS),
        "total_runtime_seconds": 0.0,
        "load_duration_ns": None,
        "prompt_eval_duration_ns": None,
        "eval_duration_ns": None,
        "ollama_total_duration_ns": None,
        "raw_response": "",
        "parsed_response": None,
        "raw_model_response": "",
        "raw_ollama_response": "",
        "parsed_model_output": None,
        "original_citations": [],
        "citation_type_normalized": False,
        "original_page_value": None,
        "normalized_page_value": None,
        "citation_normalizations": [],
        "abstention_decision": None,
        "abstention_wording_compliant": None,
        "resource_profile_version": RESOURCE_PROFILE_VERSION,
        "prompt_token_count": None,
        "prompt_token_count_source": "estimated_utf8_bytes_div4",
        "selected_num_ctx": GENERATION_SETTINGS["num_ctx"],
        "selected_num_predict": GENERATION_SETTINGS["num_predict"],
        "attempt_count": 0,
        "attempt_history": [],
        "http_status": None,
        "infrastructure_error": False,
        "infrastructure_error_class": "",
        "valid_model_response_received": False,
        "available_memory_before_request_bytes": None,
        "validation_stage": "not_started",
        "validation_error": "",
        "error_status": "",
        "error_notes": "",
    }


def generate_one(
    client: OllamaClient, run_id: str, item: Dict[str, Any],
    sleep_func: Any = time.sleep,
) -> Dict[str, Any]:
    record = _base_record(run_id, item)
    started = time.perf_counter()
    prompt = build_prompt(item)
    record["prompt_token_count"] = estimate_prompt_tokens(prompt)
    response = None
    for attempt_number in range(1, MAX_INFRASTRUCTURE_ATTEMPTS + 1):
        memory_before = available_memory_bytes()
        attempt = {
            "attempt_number": attempt_number,
            "available_memory_before_request_bytes": memory_before,
            "prompt_token_estimate": estimate_prompt_tokens(prompt),
            "selected_num_ctx": GENERATION_SETTINGS["num_ctx"],
            "selected_num_predict": GENERATION_SETTINGS["num_predict"],
            "http_status": None,
            "infrastructure_error": False,
            "infrastructure_error_class": "",
            "valid_model_response_received": False,
            "error_type": "",
            "error_message": "",
        }
        record["attempt_count"] = attempt_number
        record["available_memory_before_request_bytes"] = memory_before
        record["validation_stage"] = "ollama_request"
        try:
            response = client.generate(prompt, GENERATION_SETTINGS, OUTPUT_SCHEMA)
            attempt["http_status"] = 200
            attempt["valid_model_response_received"] = True
            attempt["prompt_token_count"] = response.get("prompt_eval_count")
            record["attempt_history"].append(attempt)
            record["http_status"] = 200
            record["valid_model_response_received"] = True
            if isinstance(response.get("prompt_eval_count"), int):
                record["prompt_token_count"] = response["prompt_eval_count"]
                record["prompt_token_count_source"] = "ollama_prompt_eval_count"
            break
        except OllamaError as exc:
            classification = classify_infrastructure_error(exc)
            attempt.update(
                http_status=getattr(exc, "status_code", None),
                infrastructure_error=classification is not None,
                infrastructure_error_class=classification or "",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            record["attempt_history"].append(attempt)
            record["http_status"] = getattr(exc, "status_code", None)
            record["infrastructure_error"] = classification is not None
            record["infrastructure_error_class"] = classification or ""
            if classification and attempt_number < MAX_INFRASTRUCTURE_ATTEMPTS:
                LOGGER.warning(
                    "Transient infrastructure failure for %s; retrying after %.1fs",
                    item["benchmark"]["variant_id"], RETRY_COOLDOWN_SECONDS,
                )
                sleep_func(RETRY_COOLDOWN_SECONDS)
                continue
            record["validation_error"] = str(exc)
            record["error_status"] = type(exc).__name__
            record["error_notes"] = str(exc)
            record["total_runtime_seconds"] = time.perf_counter() - started
            return record

    if response is None:
        raise RuntimeError("Infrastructure retry loop ended without a response or error")
    try:
        record.update(
            raw_response=response.get("response", ""),
            raw_model_response=response.get("response", ""),
            raw_ollama_response=json.dumps(response, ensure_ascii=False),
            load_duration_ns=response.get("load_duration"),
            prompt_eval_duration_ns=response.get("prompt_eval_duration"),
            eval_duration_ns=response.get("eval_duration"),
            ollama_total_duration_ns=response.get("total_duration"),
        )
        record["validation_stage"] = "parsing"
        generation = parse_generation(response["response"])
        original_parsed = generation["_original_parsed_response"]
        normalized_parsed = {
            key: value for key, value in generation.items()
            if key != "_original_parsed_response"
        }
        normalizations = generation["citation_normalizations"]
        original_values = [item["original_page_value"] for item in normalizations]
        normalized_values = [item["normalized_page_value"] for item in normalizations]
        record.update(
            generated_answer=generation["answer"],
            decision=generation["decision"],
            cited_chunk_ids=generation["cited_chunk_ids"],
            cited_pages=generation["cited_pages"],
            citations=generation["citations"],
            parsed_response=original_parsed,
            parsed_model_output=normalized_parsed,
            original_citations=original_parsed["citations"],
            citation_type_normalized=bool(normalizations),
            original_page_value=(original_values[0] if len(original_values) == 1 else original_values or None),
            normalized_page_value=(normalized_values[0] if len(normalized_values) == 1 else normalized_values or None),
            citation_normalizations=normalizations,
            abstention_decision=generation["decision"] == "ABSTAIN",
            abstention_wording_compliant=(
                generation["answer"] == ABSTENTION_RESPONSE
                if generation["decision"] == "ABSTAIN" else None
            ),
        )
        record["validation_stage"] = "citation_and_contract_validation"
        validate_citations(generation, item["chunks"])
        record.update(
            validation_stage="validated",
            error_status="ok",
        )
    except (OllamaError, ValueError, KeyError, TypeError) as exc:
        if hasattr(exc, "parsed_output"):
            invalid_parsed = getattr(exc, "parsed_output")
            record["parsed_response"] = invalid_parsed
            record["parsed_model_output"] = invalid_parsed
            if isinstance(invalid_parsed, dict):
                record["generated_answer"] = invalid_parsed.get("answer", "")
                record["decision"] = invalid_parsed.get("decision", "")
                record["original_citations"] = invalid_parsed.get("citations", [])
        record["validation_error"] = str(exc)
        record["error_status"] = type(exc).__name__
        record["error_notes"] = str(exc)
    record["total_runtime_seconds"] = time.perf_counter() - started
    return record


def _write_csv(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = dict(record)
            for key in (
                "cited_chunk_ids", "cited_pages", "citations", "retrieved_chunk_ids",
                "retrieved_pages", "generation_settings", "parsed_response",
                "parsed_model_output", "original_citations", "citation_normalizations",
                "attempt_history",
            ):
                row[key] = json.dumps(row[key], ensure_ascii=False)
            writer.writerow(row)


def _write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _summary(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "completed_records": len(records),
        "decisions": dict(Counter(record["decision"] or "ERROR" for record in records)),
        "errors": dict(Counter(record["error_status"] for record in records if record["error_status"] != "ok")),
        "by_language": {
            language: dict(Counter(record["decision"] or "ERROR" for record in records if record["language_condition"] == language))
            for language in ("EN", "MY", "MIX")
        },
        "by_answerability": {
            label: dict(Counter(record["decision"] or "ERROR" for record in records if record["answerability"] == label))
            for label in ("answerable", "unanswerable")
        },
    }


def run(args: argparse.Namespace, client_factory: Any = OllamaClient) -> Dict[str, Any]:
    inputs = load_pilot_inputs(args.config, args.pilot_intents, args.retrieval_results)
    prompt_estimates = {
        item["benchmark"]["variant_id"]: estimate_prompt_tokens(build_prompt(item))
        for item in inputs["inputs"]
    }
    maximum_estimate = max(prompt_estimates.values())
    required_capacity = (
        maximum_estimate + GENERATION_SETTINGS["num_predict"]
        + RESOURCE_SAFETY_MARGIN_TOKENS
    )
    if required_capacity > GENERATION_SETTINGS["num_ctx"]:
        raise ValueError(
            f"Resource profile context is unsafe: requires {required_capacity} tokens"
        )
    print(f"selected questions = {inputs['selected_question_count']}")
    print(f"held-out questions = {inputs['heldout_question_count']}")
    print(
        "estimated prompt tokens: "
        f"min={min(prompt_estimates.values())} "
        f"max={maximum_estimate} "
        f"mean={sum(prompt_estimates.values()) / len(prompt_estimates):.2f}"
    )
    if args.dry_run:
        for item in inputs["inputs"]:
            LOGGER.info(
                "DRY RUN %s | chunks=%s\n%s",
                item["benchmark"]["variant_id"],
                [chunk["chunk_id"] for chunk in item["chunks"]],
                build_prompt(item),
            )
        return inputs

    environment_mismatches = {
        key: {"required": value, "observed": os.environ.get(key)}
        for key, value in REQUIRED_OLLAMA_ENVIRONMENT.items()
        if os.environ.get(key) != value
    }
    if environment_mismatches:
        raise ValueError(
            "CPU-safe Ollama environment is not active: "
            + json.dumps(environment_mismatches, sort_keys=True)
        )

    if not args.run_id or not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_id):
        raise ValueError("Live and resume runs require a safe --run-id")
    run_dir = args.output_root / args.run_id
    jsonl_path = run_dir / f"{args.run_id}.jsonl"
    csv_path = run_dir / f"{args.run_id}_summary.csv"
    manifest_path = run_dir / f"{args.run_id}_manifest.json"
    if args.resume:
        if not manifest_path.is_file() or not jsonl_path.is_file():
            raise ValueError("Cannot resume: run manifest or JSONL checkpoint is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        if run_dir.exists():
            raise FileExistsError(f"Run already exists and will not be overwritten: {run_dir}")
        run_dir.mkdir(parents=True)
        records = []
        manifest = {}

    client = client_factory(
        base_url=args.base_url, model=args.model, timeout_seconds=args.timeout_seconds
    )
    ollama_version = client.version()
    installed_model = client.require_model()
    input_hashes = {
        "config_sha256": _sha256(args.config),
        "benchmark_sha256": _sha256(inputs["benchmark_path"]),
        "pilot_intents_sha256": _sha256(args.pilot_intents),
        "retrieval_results_sha256": _sha256(args.retrieval_results),
        "metadata_sha256": _sha256(inputs["metadata_path"]),
    }
    if args.resume:
        if manifest.get("input_hashes") != input_hashes:
            raise ValueError("Cannot resume because frozen input hashes changed")
        if manifest.get("model") != installed_model or manifest.get("settings") != GENERATION_SETTINGS:
            raise ValueError("Cannot resume because model or generation settings changed")
        if (
            manifest.get("prompt_version") != PROMPT_VERSION
            or manifest.get("parser_version") != PARSER_VERSION
            or manifest.get("output_schema") != OUTPUT_SCHEMA
        ):
            raise ValueError("Cannot resume because the prompt/parser contract changed")
        if manifest.get("resource_profile_version") != RESOURCE_PROFILE_VERSION:
            raise ValueError("Cannot resume because the resource profile changed")
    else:
        manifest = {
            "run_id": args.run_id,
            "model": installed_model,
            "ollama_version": ollama_version,
            "base_url": args.base_url,
            "prompt_version": PROMPT_VERSION,
            "parser_version": PARSER_VERSION,
            "output_format": "explicit_json_schema",
            "output_schema": OUTPUT_SCHEMA,
            "abstention_response": ABSTENTION_RESPONSE,
            "settings": dict(GENERATION_SETTINGS),
            "resource_profile_version": RESOURCE_PROFILE_VERSION,
            "resource_profile": {
                "cpu_only": True,
                "sequential_requests": True,
                "max_infrastructure_attempts": MAX_INFRASTRUCTURE_ATTEMPTS,
                "retry_cooldown_seconds": RETRY_COOLDOWN_SECONDS,
                "required_ollama_environment": REQUIRED_OLLAMA_ENVIRONMENT,
                "prompt_token_estimator": "ceil((UTF-8 byte length / 4) * 1.10); calibrated heuristic, not model-tokenizer exact",
                "prompt_token_estimates": prompt_estimates,
                "estimated_minimum": min(prompt_estimates.values()),
                "estimated_maximum": maximum_estimate,
                "estimated_mean": sum(prompt_estimates.values()) / len(prompt_estimates),
                "safety_margin_tokens": RESOURCE_SAFETY_MARGIN_TOKENS,
                "required_context_capacity": required_capacity,
            },
            "created_at": _utc_now(),
            "input_hashes": input_hashes,
            "development_question_count": 15,
            "heldout_question_count": 0,
            "output_paths": {
                "jsonl": str(jsonl_path), "csv_summary": str(csv_path),
                "manifest": str(manifest_path),
            },
            "status": "in_progress",
        }
        _write_manifest(manifest_path, manifest)

    completed = {record["variant_id"] for record in records}
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
        for item in inputs["inputs"]:
            variant_id = item["benchmark"]["variant_id"]
            if variant_id in completed:
                continue
            record = generate_one(client, args.run_id, item)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            records.append(record)
            _write_csv(csv_path, records)
            manifest["checkpoint"] = _summary(records)
            manifest["updated_at"] = _utc_now()
            _write_manifest(manifest_path, manifest)
            LOGGER.info("Checkpointed %s (%s)", variant_id, record["error_status"])

    manifest["status"] = "complete" if len(records) == 15 else "incomplete"
    manifest["completed_at"] = _utc_now()
    manifest["pilot_summary"] = _summary(records)
    _write_csv(csv_path, records)
    _write_manifest(manifest_path, manifest)
    return {"jsonl": jsonl_path, "csv": csv_path, "manifest": manifest_path}


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Ollama development pilot")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs" / "experiment_config_v1.1.yaml")
    parser.add_argument("--pilot-intents", type=Path, default=PROJECT_ROOT / "results" / "pilot_intents.json")
    parser.add_argument("--retrieval-results", type=Path, default=PROJECT_ROOT / "results" / "pilot_retrieval_results_v1.1.csv")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "results" / "ollama_pilot")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.resume and args.dry_run:
        parser.error("--resume and --dry-run cannot be combined")
    return args


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(parse_args())


if __name__ == "__main__":
    main()
