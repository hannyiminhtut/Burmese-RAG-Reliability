"""Generate a non-semantic structural error inventory from frozen held-out data."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analyze_heldout_automated import ROOT, RUN_FREEZE, load_records, read_json, sha256, validate_population, verify_run_freeze
from src.analyze_paired_statistics import RETRIEVAL_CSV, load_retrieval


PROTOCOL_FREEZE = ROOT / "freezes" / "uit-systematic-error-analysis-protocol-v1.0" / "systematic_error_analysis_protocol_freeze.json"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "systematic_error_analysis_v1.0"
LANGUAGES = ("EN", "MY", "MIX")


def verify_protocol_freeze(root: Path = ROOT, path: Path = PROTOCOL_FREEZE) -> dict[str, Any]:
    freeze = read_json(path)
    protocol = freeze["protocol"]
    if sha256(root / protocol["path"]) != protocol["sha256"]:
        raise ValueError("Systematic error-analysis protocol hash mismatch")
    for name, source in freeze["source_freezes"].items():
        if sha256(root / source["path"]) != source["sha256"]:
            raise ValueError(f"Error-analysis source freeze mismatch for {name}")
    return freeze


def classify_record(record: dict[str, Any], retrieval: dict[str, Any]) -> dict[str, Any]:
    answerable = record["answerability"] == "answerable"
    false_abstention = answerable and record["decision"] == "ABSTAIN"
    false_answer = not answerable and record["decision"] == "ANSWER"
    hit5 = None if retrieval["hit_at_5"] == "" else int(retrieval["hit_at_5"])
    gold_page_miss_at_5 = answerable and hit5 == 0
    contract_invalid = record.get("error_status") != "ok"
    infrastructure_event = bool(record.get("infrastructure_error"))
    flags = []
    if false_abstention:
        flags.append("false_abstention")
    if false_answer:
        flags.append("false_answer")
    if gold_page_miss_at_5:
        flags.append("gold_page_miss_at_5")
    if contract_invalid:
        flags.append("contract_invalid")
    if infrastructure_event:
        flags.append("infrastructure_event_recorded")
    return {
        "run_id": record["run_id"],
        "split_label": record["split_label"],
        "intent_id": record["intent_id"],
        "variant_id": record["variant_id"],
        "language_condition": record["language_condition"],
        "answerability": record["answerability"],
        "decision": record["decision"],
        "decision_correct": int(not false_abstention and not false_answer),
        "hit_at_1": retrieval["hit_at_1"],
        "hit_at_3": retrieval["hit_at_3"],
        "hit_at_5": retrieval["hit_at_5"],
        "false_abstention": int(false_abstention),
        "false_answer": int(false_answer),
        "gold_page_miss_at_5": int(gold_page_miss_at_5),
        "contract_invalid": int(contract_invalid),
        "infrastructure_event_recorded": int(infrastructure_event),
        "error_status": record.get("error_status", ""),
        "validation_stage": record.get("validation_stage", ""),
        "infrastructure_error_class": record.get("infrastructure_error_class", ""),
        "attempt_count": record.get("attempt_count", ""),
        "structural_flag_count": len(flags),
        "structural_flags": "|".join(flags),
        "semantic_assessment": "NOT_EVALUATED",
    }


def aggregate_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    scopes = [("overall", "all", rows)]
    scopes += [("language", language, [r for r in rows if r["language_condition"] == language]) for language in LANGUAGES]
    scopes += [("answerability", value, [r for r in rows if r["answerability"] == value]) for value in ("answerable", "unanswerable")]
    for scope_type, scope_value, subset in scopes:
        for flag in ("false_abstention", "false_answer", "gold_page_miss_at_5", "contract_invalid", "infrastructure_event_recorded"):
            count = sum(int(row[flag]) for row in subset)
            output.append({"scope_type": scope_type, "scope_value": scope_value, "metric": flag, "numerator": count, "denominator": len(subset), "proportion": count / len(subset)})
    return output


def retrieval_decision_contingency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    answerable = [row for row in rows if row["answerability"] == "answerable"]
    output = []
    for language in ("ALL", *LANGUAGES):
        subset = answerable if language == "ALL" else [row for row in answerable if row["language_condition"] == language]
        for hit5 in (1, 0):
            for decision in ("ANSWER", "ABSTAIN"):
                count = sum(int(row["hit_at_5"]) == hit5 and row["decision"] == decision for row in subset)
                output.append({
                    "language": language,
                    "answerability": "answerable",
                    "gold_page_hit_at_5": hit5,
                    "decision": decision,
                    "count": count,
                    "language_answerable_denominator": len(subset),
                    "interpretation_boundary": "gold-page intersection, not semantic evidence sufficiency",
                })
    return output


def paired_disagreements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_intent: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_intent[row["intent_id"]][row["language_condition"]] = row
    output = []
    for intent_id in sorted(by_intent):
        variants = by_intent[intent_id]
        if set(variants) != set(LANGUAGES):
            raise ValueError(f"Incomplete paired intent: {intent_id}")
        if len({variants[language]["answerability"] for language in LANGUAGES}) != 1:
            raise ValueError(f"Answerability mismatch for paired intent: {intent_id}")
        decisions = [variants[language]["decision"] for language in LANGUAGES]
        if len(set(decisions)) == 1:
            continue
        output.append({
            "intent_id": intent_id,
            "answerability": variants["EN"]["answerability"],
            "EN_decision": variants["EN"]["decision"],
            "MY_decision": variants["MY"]["decision"],
            "MIX_decision": variants["MIX"]["decision"],
            "EN_decision_correct": variants["EN"]["decision_correct"],
            "MY_decision_correct": variants["MY"]["decision_correct"],
            "MIX_decision_correct": variants["MIX"]["decision_correct"],
            "EN_hit_at_5": variants["EN"]["hit_at_5"],
            "MY_hit_at_5": variants["MY"]["hit_at_5"],
            "MIX_hit_at_5": variants["MIX"]["hit_at_5"],
            "MY_false_abstention_EN_correct": int(variants["MY"]["false_abstention"] and variants["EN"]["decision_correct"]),
            "MY_false_abstention_MIX_correct": int(variants["MY"]["false_abstention"] and variants["MIX"]["decision_correct"]),
            "MY_false_abstention_EN_and_MIX_correct": int(variants["MY"]["false_abstention"] and variants["EN"]["decision_correct"] and variants["MIX"]["decision_correct"]),
            "semantic_assessment": "NOT_EVALUATED",
        })
    return output


def analyze(records: list[dict[str, Any]], retrieval: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    validate_population(records)
    classified = [classify_record(record, retrieval[record["variant_id"]]) for record in records]
    inventory = [row for row in classified if row["structural_flag_count"] > 0]
    counts = aggregate_counts(classified)
    contingency = retrieval_decision_contingency(classified)
    disagreements = paired_disagreements(classified)
    flag_counts = {flag: sum(row[flag] for row in classified) for flag in ("false_abstention", "false_answer", "gold_page_miss_at_5", "contract_invalid", "infrastructure_event_recorded")}
    pattern_counts = Counter((row["EN_decision"], row["MY_decision"], row["MIX_decision"]) for row in disagreements)
    report = {
        "analysis_version": "systematic-structural-error-analysis-v1.0",
        "analysis_type": "automated_non_semantic_structural_error_analysis",
        "population": {"records": 222, "semantic_intents": 74, "development_records": 0, "answerable": 180, "unanswerable": 42},
        "flag_counts": flag_counts,
        "records_with_any_structural_flag": len(inventory),
        "records_with_multiple_structural_flags": sum(row["structural_flag_count"] > 1 for row in inventory),
        "paired_decision_disagreement_intents": len(disagreements),
        "paired_decision_patterns_among_disagreements": {"|".join(key): value for key, value in sorted(pattern_counts.items())},
        "my_false_abstention_patterns": {
            "MY_false_abstention_EN_correct": sum(row["MY_false_abstention_EN_correct"] for row in disagreements),
            "MY_false_abstention_MIX_correct": sum(row["MY_false_abstention_MIX_correct"] for row in disagreements),
            "MY_false_abstention_EN_and_MIX_correct": sum(row["MY_false_abstention_EN_and_MIX_correct"] for row in disagreements),
        },
        "semantic_measures": "NOT_EVALUATED",
        "causal_failure_attribution": "NOT_EVALUATED",
    }
    return report, {"inventory": inventory, "counts": counts, "contingency": contingency, "disagreements": disagreements}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path = DEFAULT_OUTPUT_DIR, overwrite: bool = False) -> dict[str, Any]:
    run_freeze = verify_run_freeze()
    protocol_freeze = verify_protocol_freeze()
    generation_path = ROOT / run_freeze["artifacts"]["jsonl"]["path"]
    records = load_records(generation_path)
    retrieval = load_retrieval(RETRIEVAL_CSV)
    report, tables = analyze(records, retrieval)
    report.update({
        "run_id": run_freeze["run_id"],
        "protocol_freeze_id": protocol_freeze["protocol_freeze_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_hashes": {"run_freeze": sha256(RUN_FREEZE), "generation_jsonl": sha256(generation_path), "retrieval_csv": sha256(RETRIEVAL_CSV), "protocol_freeze": sha256(PROTOCOL_FREEZE)},
    })
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory already contains files: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "results_json": output_dir / "systematic_error_analysis_v1.0.json",
        "inventory_csv": output_dir / "structural_error_inventory_v1.0.csv",
        "counts_csv": output_dir / "structural_error_counts_v1.0.csv",
        "contingency_csv": output_dir / "retrieval_decision_contingency_v1.0.csv",
        "disagreements_csv": output_dir / "paired_language_disagreements_v1.0.csv",
    }
    with paths["results_json"].open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_csv(paths["inventory_csv"], tables["inventory"])
    write_csv(paths["counts_csv"], tables["counts"])
    write_csv(paths["contingency_csv"], tables["contingency"])
    write_csv(paths["disagreements_csv"], tables["disagreements"])
    manifest = {
        "analysis_version": report["analysis_version"],
        "run_id": report["run_id"],
        "protocol_freeze_id": report["protocol_freeze_id"],
        "population": report["population"],
        "inputs": report["input_hashes"],
        "outputs": {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for name, path in paths.items()},
        "semantic_measures": "NOT_EVALUATED",
        "created_at": report["created_at"],
    }
    manifest_path = output_dir / "systematic_error_analysis_manifest_v1.0.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run(args.output_dir, args.overwrite)
    print("held-out records analyzed = 222")
    print("development records analyzed = 0")
    print(f"records with structural flags = {report['records_with_any_structural_flag']}")
    print("semantic measures = NOT_EVALUATED")


if __name__ == "__main__":
    main()
