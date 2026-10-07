"""Generate only the frozen 222-question held-out split."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.evaluate_retrieval import load_benchmark, load_pilot_intents
from src.experiment_freeze import DEFAULT_FREEZE, sha256_file, verify_freeze
from src.generate_pilot import (
    CSV_COLUMNS, DEFAULT_BASE_URL, DEFAULT_MODEL, GENERATION_SETTINGS,
    MAX_INFRASTRUCTURE_ATTEMPTS, PARSER_VERSION, PROMPT_VERSION,
    REQUIRED_OLLAMA_ENVIRONMENT, RESOURCE_PROFILE_VERSION, _summary,
    _write_manifest, generate_one,
)
from src.ollama_client import OllamaClient, sha256_digest_audit


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELDOUT_COLUMNS = CSV_COLUMNS + ["split_label", "language_consistency"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def language_consistency(decision: str, language: str, answer: str) -> str:
    if decision == "ABSTAIN":
        return "NOT_APPLICABLE"
    has_myanmar = bool(re.search(r"[\u1000-\u109f]", answer))
    has_english = bool(re.search(r"[A-Za-z]", answer))
    if language == "EN":
        return "PASS" if has_english and not has_myanmar else "FAIL"
    if language == "MY":
        return "PASS" if has_myanmar else "FAIL"
    if language == "MIX":
        return "PASS" if has_myanmar and has_english else "FAIL"
    raise ValueError(f"Unknown language condition: {language}")


def load_heldout_inputs(manifest: Dict[str, Any], root: Path) -> Dict[str, Any]:
    paths = manifest["paths"]
    benchmark = load_benchmark(root / paths["benchmark"])
    pilot_ids = set(load_pilot_intents(root / paths["development_intents"]))
    selected = [row for row in benchmark if row["intent_id"] not in pilot_ids]
    with (root / paths["heldout_retrieval_results"]).open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        retrieval_rows = list(csv.DictReader(stream))
    metadata = json.loads((root / paths["metadata"]).read_text(encoding="utf-8"))
    metadata_by_id = {row["chunk_id"]: row for row in metadata}
    benchmark_by_variant = {row["variant_id"]: row for row in selected}

    if len(selected) != 222 or len({row["intent_id"] for row in selected}) != 74:
        raise ValueError("Held-out benchmark must contain exactly 74 intents and 222 questions")
    if len(retrieval_rows) != 222:
        raise ValueError("Frozen held-out retrieval must contain exactly 222 rows")
    if any(row["intent_id"] in pilot_ids for row in retrieval_rows):
        raise ValueError("Development intent found in held-out retrieval rows")
    if {row["variant_id"] for row in retrieval_rows} != set(benchmark_by_variant):
        raise ValueError("Held-out retrieval variants differ from the frozen benchmark split")

    inputs: List[Dict[str, Any]] = []
    for retrieval in retrieval_rows:
        benchmark_row = benchmark_by_variant[retrieval["variant_id"]]
        if retrieval["question"] != benchmark_row["question"]:
            raise ValueError(f"Question mismatch for {retrieval['variant_id']}")
        chunk_ids = json.loads(retrieval["retrieved_chunk_ids"])
        if len(chunk_ids) != 5:
            raise ValueError(f"{retrieval['variant_id']} does not have frozen Top-5 evidence")
        try:
            chunks = [metadata_by_id[chunk_id] for chunk_id in chunk_ids]
        except KeyError as exc:
            raise ValueError(f"Unknown frozen chunk ID: {exc.args[0]}") from exc
        inputs.append({"benchmark": benchmark_row, "retrieval": retrieval, "chunks": chunks})

    counts = Counter(row["answerability"] for row in selected)
    languages = Counter(row["language_condition"] for row in selected)
    if counts != {"answerable": 180, "unanswerable": 42}:
        raise ValueError(f"Unexpected held-out answerability counts: {dict(counts)}")
    if languages != {"EN": 74, "MY": 74, "MIX": 74}:
        raise ValueError(f"Unexpected held-out language counts: {dict(languages)}")
    return {"inputs": inputs, "pilot_ids": sorted(pilot_ids)}


def _write_csv(path: Path, records: List[Dict[str, Any]]) -> None:
    json_fields = {
        "cited_chunk_ids", "cited_pages", "citations", "retrieved_chunk_ids",
        "retrieved_pages", "generation_settings", "parsed_response",
        "parsed_model_output", "original_citations", "citation_normalizations",
        "attempt_history",
    }
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HELDOUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = dict(record)
            for field in json_fields:
                row[field] = json.dumps(row[field], ensure_ascii=False)
            writer.writerow(row)


def verify_live_ollama(client: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the live Ollama version, exact model name, and canonical digest."""
    frozen = manifest["generation"]
    observed_version = client.version()
    if observed_version != frozen["ollama_version"]:
        raise ValueError("Installed Ollama version differs from the freeze")
    model_info = client.model_info()
    if model_info.get("name") != frozen["ollama_model"]:
        raise ValueError("Installed Ollama model name differs from the freeze")
    audit = sha256_digest_audit(
        model_info.get("digest", ""), frozen["ollama_model_manifest_digest"]
    )
    if not audit["digest_match"]:
        raise ValueError("Installed Ollama model digest differs from the freeze")
    return {
        "ollama_version": observed_version,
        "model_name": model_info["name"],
        **audit,
    }


def run(args: argparse.Namespace, client_factory: Any = OllamaClient) -> Dict[str, Any]:
    freeze_path = args.freeze.resolve()
    manifest = verify_freeze(freeze_path)
    root = freeze_path.parents[2]
    heldout = load_heldout_inputs(manifest, root)
    print("held-out questions selected = 222")
    print("development questions selected = 0")
    print("static frozen inputs verified = true")

    client = client_factory(
        base_url=args.base_url, model=manifest["generation"]["ollama_model"],
        timeout_seconds=manifest["generation"]["timeout_seconds"],
    )
    live_audit = verify_live_ollama(client, manifest)
    print("live Ollama version verified = true")
    print("live Ollama model name verified = true")
    print("live Ollama model digest verified = true")
    if args.dry_run:
        print("no Ollama generation performed")
        return {**heldout, "live_ollama_audit": live_audit}

    mismatches = {
        key: {"required": value, "observed": os.environ.get(key)}
        for key, value in REQUIRED_OLLAMA_ENVIRONMENT.items()
        if os.environ.get(key) != value
    }
    if mismatches:
        raise ValueError("CPU-safe Ollama environment is not active: " + json.dumps(mismatches))
    if not args.run_id or not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_id):
        raise ValueError("Live and resume runs require a safe --run-id")

    output_root = args.output_root.resolve()
    run_dir = output_root / args.run_id
    jsonl_path = run_dir / f"{args.run_id}.jsonl"
    csv_path = run_dir / f"{args.run_id}_summary.csv"
    run_manifest_path = run_dir / f"{args.run_id}_manifest.json"

    if args.resume:
        if not jsonl_path.is_file() or not run_manifest_path.is_file():
            raise ValueError("Cannot resume: checkpoint or run manifest is missing")
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if run_manifest.get("freeze_id") != manifest["freeze_id"]:
            raise ValueError("Cannot resume under a different experiment freeze")
        records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
    else:
        if run_dir.exists():
            raise FileExistsError(f"Run already exists and will not be overwritten: {run_dir}")
        run_dir.mkdir(parents=True)
        records = []
        run_manifest = {
            "run_id": args.run_id,
            "freeze_id": manifest["freeze_id"],
            "freeze_manifest": str(freeze_path),
            "freeze_manifest_sha256": sha256_file(freeze_path),
            "prompt_version": PROMPT_VERSION,
            "parser_version": PARSER_VERSION,
            "resource_profile_version": RESOURCE_PROFILE_VERSION,
            "ollama_version": live_audit["ollama_version"],
            "ollama_model": live_audit["model_name"],
            "ollama_digest_verification": live_audit,
            "settings": GENERATION_SETTINGS,
            "max_infrastructure_attempts": MAX_INFRASTRUCTURE_ATTEMPTS,
            "created_at": _utc_now(),
            "heldout_question_count": 222,
            "development_question_count": 0,
            "status": "in_progress",
            "output_paths": {
                "jsonl": str(jsonl_path), "csv_summary": str(csv_path),
                "manifest": str(run_manifest_path),
            },
        }
        _write_manifest(run_manifest_path, run_manifest)

    completed = {record["variant_id"] for record in records}
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
        for item in heldout["inputs"]:
            variant_id = item["benchmark"]["variant_id"]
            if variant_id in completed:
                continue
            record = generate_one(client, args.run_id, item)
            record["split_label"] = "heldout_test"
            record["language_consistency"] = language_consistency(
                record["decision"], record["language_condition"], record["generated_answer"]
            ) if record["valid_model_response_received"] else "NOT_EVALUATED"
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            records.append(record)
            _write_csv(csv_path, records)
            run_manifest["checkpoint"] = _summary(records)
            run_manifest["updated_at"] = _utc_now()
            _write_manifest(run_manifest_path, run_manifest)
            LOGGER.info("Checkpointed %s (%s)", variant_id, record["error_status"])

    run_manifest["status"] = "complete" if len(records) == 222 else "incomplete"
    run_manifest["completed_at"] = _utc_now()
    run_manifest["summary"] = _summary(records)
    _write_csv(csv_path, records)
    _write_manifest(run_manifest_path, run_manifest)
    return {"jsonl": jsonl_path, "csv": csv_path, "manifest": run_manifest_path}


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run frozen held-out Ollama generation")
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "results" / "heldout_generation")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run and args.resume:
        parser.error("--dry-run and --resume cannot be combined")
    return args


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(parse_args())


if __name__ == "__main__":
    main()
