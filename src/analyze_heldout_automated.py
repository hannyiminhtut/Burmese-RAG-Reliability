"""Reproducible non-semantic analysis of the frozen held-out generation run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUN_FREEZE = ROOT / "freezes" / "uit-heldout-run-v1.1-20260819-03" / "heldout_run_freeze.json"
WAIVER = ROOT / "docs" / "semantic_evaluation_waiver_v1.0.md"
WAIVER_FREEZE = ROOT / "freezes" / "uit-semantic-evaluation-waiver-v1.0" / "semantic_evaluation_waiver_freeze.json"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "automated_evaluation_v1.0"
DEVELOPMENT_INTENTS = {"Q002", "Q008", "Q024", "Q029", "Q057"}
NOT_EVALUATED = [
    "semantic_answer_correctness",
    "numeric_correctness",
    "groundedness",
    "hallucination_rate",
    "claim_level_citation_support",
    "semantic_language_consistency",
    "semantic_failure_attribution",
    "benchmark_evidence_ambiguity",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def verify_run_freeze(root: Path = ROOT, freeze_path: Path = RUN_FREEZE) -> dict[str, Any]:
    freeze = read_json(freeze_path)
    for name, artifact in freeze["artifacts"].items():
        path = root / artifact["path"]
        actual = sha256(path)
        if actual != artifact["sha256"]:
            raise ValueError(f"Frozen artifact hash mismatch for {name}: {path}")
    for name, artifact in freeze["frozen_inputs"].items():
        path = root / artifact["path"]
        actual = sha256(path)
        if actual != artifact["sha256"]:
            raise ValueError(f"Frozen input hash mismatch for {name}: {path}")
    return freeze


def verify_waiver_freeze(root: Path = ROOT, freeze_path: Path = WAIVER_FREEZE) -> dict[str, Any]:
    freeze = read_json(freeze_path)
    waiver = freeze["waiver"]
    if sha256(root / waiver["path"]) != waiver["sha256"]:
        raise ValueError("Frozen semantic-evaluation waiver hash mismatch")
    for name, source in freeze["frozen_sources"].items():
        if sha256(root / source["path"]) != source["sha256"]:
            raise ValueError(f"Waiver source hash mismatch for {name}")
    return freeze


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        records.append(row)
    return records


def validate_population(records: list[dict[str, Any]]) -> None:
    if len(records) != 222:
        raise ValueError(f"Expected 222 held-out records, found {len(records)}")
    variant_ids = [row["variant_id"] for row in records]
    if len(set(variant_ids)) != 222:
        raise ValueError("Expected 222 unique variant IDs")
    if any(row.get("split_label") != "heldout_test" for row in records):
        raise ValueError("Every record must have split_label=heldout_test")
    overlap = sorted({row["intent_id"] for row in records} & DEVELOPMENT_INTENTS)
    if overlap:
        raise ValueError(f"Development intent overlap: {overlap}")
    expected_languages = {"EN": 74, "MY": 74, "MIX": 74}
    if dict(Counter(row["language_condition"] for row in records)) != expected_languages:
        raise ValueError("Expected 74 EN, 74 MY, and 74 MIX records")
    expected_answerability = {"answerable": 180, "unanswerable": 42}
    if dict(Counter(row["answerability"] for row in records)) != expected_answerability:
        raise ValueError("Expected 180 answerable and 42 unanswerable records")


def safe_div(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": safe_div(numerator, denominator)}


def numeric_summary(values: Iterable[float]) -> dict[str, Any]:
    data = list(values)
    if not data:
        return {"count": 0, "mean": None, "median": None, "standard_deviation": None, "minimum": None, "maximum": None}
    return {
        "count": len(data),
        "mean": statistics.fmean(data),
        "median": statistics.median(data),
        "standard_deviation": statistics.pstdev(data),
        "minimum": min(data),
        "maximum": max(data),
    }


def decision_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(r["answerability"] == "unanswerable" and r["decision"] == "ABSTAIN" for r in records)
    fp = sum(r["answerability"] == "answerable" and r["decision"] == "ABSTAIN" for r in records)
    fn = sum(r["answerability"] == "unanswerable" and r["decision"] == "ANSWER" for r in records)
    tn = sum(r["answerability"] == "answerable" and r["decision"] == "ANSWER" for r in records)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "positive_decision": "ABSTAIN",
        "confusion_matrix": {
            "unanswerable_abstain": tp,
            "answerable_abstain_false_abstention": fp,
            "unanswerable_answer_false_answer": fn,
            "answerable_answer": tn,
        },
        "decision_accuracy": metric(tp + tn, len(records)),
        "abstention_precision": {"numerator": tp, "denominator": tp + fp, "value": precision},
        "abstention_recall": {"numerator": tp, "denominator": tp + fn, "value": recall},
        "abstention_f1": {"numerator": 2 * tp, "denominator": 2 * tp + fp + fn, "value": f1},
    }


def contract_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = sum(r.get("error_status") == "ok" for r in records)
    abstentions = [r for r in records if r["decision"] == "ABSTAIN"]
    compliant = sum(r.get("abstention_wording_compliant") is True for r in abstentions)
    answers = [r for r in records if r["decision"] == "ANSWER"]
    validated_answers = sum(r.get("error_status") == "ok" for r in answers)
    infrastructure = sum(bool(r.get("infrastructure_error")) for r in records)
    return {
        "contract_valid": metric(valid, len(records)),
        "contract_invalid_count": len(records) - valid,
        "abstention_wording_compliance": metric(compliant, len(abstentions)),
        "mechanically_validated_answer_outputs": metric(validated_answers, len(answers)),
        "infrastructure_error": metric(infrastructure, len(records)),
        "validation_error_types": dict(sorted(Counter(r.get("error_status", "") for r in records if r.get("error_status") != "ok").items())),
        "validation_stages": dict(sorted(Counter(r.get("validation_stage", "") for r in records).items())),
        "infrastructure_error_classes": dict(sorted(Counter(r.get("infrastructure_error_class", "") for r in records if r.get("infrastructure_error")).items())),
    }


def analyze(records: list[dict[str, Any]], retrieval_summary: dict[str, Any]) -> dict[str, Any]:
    validate_population(records)
    by_language = {language: decision_metrics([r for r in records if r["language_condition"] == language]) for language in ("EN", "MY", "MIX")}
    runtime = numeric_summary(float(r["total_runtime_seconds"]) for r in records)
    attempts = numeric_summary(float(r.get("attempt_count", 0)) for r in records)
    ollama_seconds = numeric_summary(float(r["ollama_total_duration_ns"]) / 1_000_000_000 for r in records if r.get("ollama_total_duration_ns") is not None)
    prompt_tokens = numeric_summary(float(r["prompt_token_count"]) for r in records if r.get("prompt_token_count") is not None)
    return {
        "analysis_version": "automated-non-semantic-heldout-v1.0",
        "analysis_type": "automated_non_semantic_heldout_analysis",
        "population": {
            "records": len(records),
            "semantic_intents": len({r["intent_id"] for r in records}),
            "development_records": 0,
            "language_counts": dict(Counter(r["language_condition"] for r in records)),
            "answerability_counts": dict(Counter(r["answerability"] for r in records)),
            "decision_counts": dict(Counter(r["decision"] for r in records)),
        },
        "retrieval": {
            "answerable_metrics": retrieval_summary["answerable_metrics"],
            "answerable_metrics_by_language": retrieval_summary["answerable_metrics_by_language"],
            "top1_score_statistics": retrieval_summary["top1_score_statistics"],
        },
        "decision": decision_metrics(records),
        "decision_by_language": by_language,
        "contract_and_reliability": contract_metrics(records),
        "runtime": {
            "total_runtime_seconds": runtime,
            "ollama_total_duration_seconds": ollama_seconds,
            "attempt_count": attempts,
            "prompt_token_count": prompt_tokens,
            "sum_total_runtime_seconds": math.fsum(float(r["total_runtime_seconds"]) for r in records),
        },
        "human_dependent_semantic_measures": {name: "NOT_EVALUATED" for name in NOT_EVALUATED},
    }


def flatten_metric_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scope, metrics in [("overall", report["decision"]), *[(language, report["decision_by_language"][language]) for language in ("EN", "MY", "MIX")]]:
        for name in ("decision_accuracy", "abstention_precision", "abstention_recall", "abstention_f1"):
            value = metrics[name]
            rows.append({"section": "decision", "scope": scope, "metric": name, "numerator": value["numerator"], "denominator": value["denominator"], "value": value["value"], "evaluation_status": "EVALUATED"})
    retrieval = report["retrieval"]
    for scope, metrics in [("overall_answerable", retrieval["answerable_metrics"]), *[(f"{language}_answerable", retrieval["answerable_metrics_by_language"][language]) for language in ("EN", "MY", "MIX")]]:
        denominator = 180 if scope == "overall_answerable" else 60
        for name, value in metrics.items():
            numerator = value * denominator if name == "MRR" else round(value * denominator)
            rows.append({"section": "retrieval", "scope": scope, "metric": name, "numerator": numerator, "denominator": denominator, "value": value, "evaluation_status": "EVALUATED"})
    for name, value in report["human_dependent_semantic_measures"].items():
        rows.append({"section": "semantic", "scope": "overall", "metric": name, "numerator": "", "denominator": "", "value": "", "evaluation_status": value})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path = DEFAULT_OUTPUT_DIR, overwrite: bool = False) -> dict[str, Any]:
    freeze = verify_run_freeze()
    waiver_freeze = verify_waiver_freeze()
    jsonl_path = ROOT / freeze["artifacts"]["jsonl"]["path"]
    records = load_records(jsonl_path)
    retrieval_summary_path = ROOT / "results" / "heldout_retrieval_summary_v1.1.json"
    report = analyze(records, read_json(retrieval_summary_path))
    report.update({
        "run_id": freeze["run_id"],
        "run_freeze_id": freeze["run_freeze_id"],
        "run_freeze_sha256": sha256(RUN_FREEZE),
        "waiver_version": "semantic-evaluation-waiver-v1.0",
        "waiver_sha256": sha256(WAIVER),
        "waiver_freeze_id": waiver_freeze["waiver_freeze_id"],
        "waiver_freeze_sha256": sha256(WAIVER_FREEZE),
        "input_jsonl_sha256": sha256(jsonl_path),
        "retrieval_summary_sha256": sha256(retrieval_summary_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory already contains files: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "heldout_automated_metrics_v1.0.json"
    csv_path = output_dir / "heldout_automated_metrics_v1.0.csv"
    with json_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_csv(csv_path, flatten_metric_rows(report))
    manifest = {
        "analysis_version": report["analysis_version"],
        "analysis_type": report["analysis_type"],
        "run_id": report["run_id"],
        "record_count": 222,
        "development_record_count": 0,
        "waiver_sha256": report["waiver_sha256"],
        "inputs": {
            "run_freeze": {"path": str(RUN_FREEZE.relative_to(ROOT)), "sha256": report["run_freeze_sha256"]},
            "waiver_freeze": {"path": str(WAIVER_FREEZE.relative_to(ROOT)), "sha256": report["waiver_freeze_sha256"]},
            "generation_jsonl": {"path": freeze["artifacts"]["jsonl"]["path"], "sha256": report["input_jsonl_sha256"]},
            "retrieval_summary": {"path": str(retrieval_summary_path.relative_to(ROOT)), "sha256": report["retrieval_summary_sha256"]},
        },
        "outputs": {
            "json": {"path": str(json_path.relative_to(ROOT)), "sha256": sha256(json_path)},
            "csv": {"path": str(csv_path.relative_to(ROOT)), "sha256": sha256(csv_path)},
        },
        "human_semantic_annotation_performed": False,
        "created_at": report["created_at"],
    }
    manifest_path = output_dir / "heldout_automated_analysis_manifest_v1.0.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace this version's generated analysis artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run(args.output_dir, overwrite=args.overwrite)
    print(f"held-out records analyzed = {report['population']['records']}")
    print("development records analyzed = 0")
    print("human semantic annotation performed = false")


if __name__ == "__main__":
    main()
