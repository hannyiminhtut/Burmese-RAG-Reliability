"""Paired statistical analysis for frozen EN, MY, and MIX held-out outcomes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import scipy
from scipy.stats import binomtest, chi2

from src.analyze_heldout_automated import ROOT, RUN_FREEZE, load_records, read_json, sha256, validate_population, verify_run_freeze


PROTOCOL_FREEZE = ROOT / "freezes" / "uit-statistical-analysis-protocol-v1.0" / "statistical_analysis_protocol_freeze.json"
AUTOMATED_ANALYSIS_FREEZE = ROOT / "freezes" / "uit-automated-heldout-analysis-v1.0" / "automated_heldout_analysis_freeze.json"
RETRIEVAL_CSV = ROOT / "results" / "heldout_retrieval_results_v1.1.csv"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "paired_statistical_analysis_v1.0"
LANGUAGES = ("EN", "MY", "MIX")
PAIRS = (("EN", "MY"), ("EN", "MIX"), ("MY", "MIX"))


def verify_protocol_freeze(root: Path = ROOT, path: Path = PROTOCOL_FREEZE) -> dict[str, Any]:
    freeze = read_json(path)
    protocol = freeze["protocol"]
    if sha256(root / protocol["path"]) != protocol["sha256"]:
        raise ValueError("Statistical protocol hash mismatch")
    for name, source in freeze["source_freezes"].items():
        if sha256(root / source["path"]) != source["sha256"]:
            raise ValueError(f"Statistical protocol source mismatch for {name}")
    return freeze


def load_retrieval(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 222 or len({row["variant_id"] for row in rows}) != 222:
        raise ValueError("Expected 222 unique held-out retrieval variants")
    return {row["variant_id"]: row for row in rows}


def build_paired_rows(records: list[dict[str, Any]], retrieval: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    validate_population(records)
    by_intent: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        variant = record["variant_id"]
        if variant not in retrieval:
            raise ValueError(f"Missing retrieval row: {variant}")
        by_intent[record["intent_id"]][record["language_condition"]] = record
    if len(by_intent) != 74:
        raise ValueError(f"Expected 74 semantic intents, found {len(by_intent)}")
    rows: list[dict[str, Any]] = []
    for intent_id in sorted(by_intent):
        variants = by_intent[intent_id]
        if set(variants) != set(LANGUAGES):
            raise ValueError(f"Intent {intent_id} does not contain exactly EN, MY, and MIX")
        answerability = {variants[language]["answerability"] for language in LANGUAGES}
        if len(answerability) != 1:
            raise ValueError(f"Answerability differs across variants for {intent_id}")
        row: dict[str, Any] = {"intent_id": intent_id, "answerability": answerability.pop()}
        for language in LANGUAGES:
            record = variants[language]
            retrieval_row = retrieval[record["variant_id"]]
            expected_decision = "ANSWER" if record["answerability"] == "answerable" else "ABSTAIN"
            row[f"{language}_decision"] = record["decision"]
            row[f"{language}_decision_correct"] = int(record["decision"] == expected_decision)
            row[f"{language}_false_abstention"] = int(record["answerability"] == "answerable" and record["decision"] == "ABSTAIN")
            row[f"{language}_false_answer"] = int(record["answerability"] == "unanswerable" and record["decision"] == "ANSWER")
            for k in (1, 3, 5):
                value = retrieval_row[f"hit_at_{k}"]
                row[f"{language}_hit_at_{k}"] = "" if value == "" else int(value)
        rows.append(row)
    return rows


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - half, center + half


def cochran_q(matrix: list[list[int]]) -> dict[str, Any]:
    if not matrix or any(len(row) != 3 for row in matrix):
        raise ValueError("Cochran's Q requires a nonempty N x 3 paired matrix")
    k = 3
    column_sums = [sum(row[j] for row in matrix) for j in range(k)]
    row_sums = [sum(row) for row in matrix]
    total = sum(column_sums)
    denominator = k * total - sum(value * value for value in row_sums)
    if denominator == 0:
        return {"statistic": None, "degrees_of_freedom": 2, "p_value": None}
    statistic = (k - 1) * (k * sum(value * value for value in column_sums) - total * total) / denominator
    return {"statistic": statistic, "degrees_of_freedom": 2, "p_value": float(chi2.sf(statistic, 2))}


def mcnemar_exact(a_values: list[int], b_values: list[int]) -> dict[str, Any]:
    if len(a_values) != len(b_values) or not a_values:
        raise ValueError("McNemar inputs must be equal-length, nonempty paired vectors")
    both_success = sum(a == 1 and b == 1 for a, b in zip(a_values, b_values))
    a_only = sum(a == 1 and b == 0 for a, b in zip(a_values, b_values))
    b_only = sum(a == 0 and b == 1 for a, b in zip(a_values, b_values))
    both_failure = len(a_values) - both_success - a_only - b_only
    discordant = a_only + b_only
    p_value = 1.0 if discordant == 0 else float(binomtest(a_only, discordant, 0.5, alternative="two-sided").pvalue)
    raw_odds_ratio: float | str | None
    if b_only == 0:
        raw_odds_ratio = None if a_only == 0 else "Infinity"
    else:
        raw_odds_ratio = a_only / b_only
    return {
        "both_success": both_success,
        "a_only_success": a_only,
        "b_only_success": b_only,
        "both_failure": both_failure,
        "discordant_pairs": discordant,
        "p_value_unadjusted": p_value,
        "paired_risk_difference": (a_only - b_only) / len(a_values),
        "matched_odds_ratio": raw_odds_ratio,
        "matched_odds_ratio_continuity_corrected": (a_only + 0.5) / (b_only + 0.5),
    }


def holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, (index, value) in enumerate(indexed):
        candidate = min(1.0, (m - rank) * value)
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def outcome_specifications() -> list[tuple[str, str]]:
    return [
        ("decision_correct", "all"),
        ("hit_at_1", "answerable"),
        ("hit_at_3", "answerable"),
        ("hit_at_5", "answerable"),
        ("false_abstention", "answerable"),
        ("false_answer", "unanswerable"),
    ]


def filter_population(rows: list[dict[str, Any]], population: str) -> list[dict[str, Any]]:
    return rows if population == "all" else [row for row in rows if row["answerability"] == population]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    descriptive: list[dict[str, Any]] = []
    omnibus: list[dict[str, Any]] = []
    pairwise: list[dict[str, Any]] = []
    for outcome, population in outcome_specifications():
        subset = filter_population(rows, population)
        language_values: dict[str, list[int]] = {}
        proportions: list[float] = []
        for language in LANGUAGES:
            values = [int(row[f"{language}_{outcome}"]) for row in subset]
            language_values[language] = values
            successes = sum(values)
            lower, upper = wilson_interval(successes, len(values))
            proportion = successes / len(values)
            proportions.append(proportion)
            descriptive.append({
                "outcome": outcome,
                "population": population,
                "language": language,
                "numerator": successes,
                "denominator": len(values),
                "proportion": proportion,
                "ci_95_lower": lower,
                "ci_95_upper": upper,
            })
        q = cochran_q([[language_values[language][i] for language in LANGUAGES] for i in range(len(subset))])
        omnibus.append({
            "outcome": outcome,
            "population": population,
            "paired_intents": len(subset),
            "test": "Cochran_Q",
            **q,
            "proportion_range_effect_size": max(proportions) - min(proportions),
            "significant_at_0_05": q["p_value"] is not None and q["p_value"] < 0.05,
        })
        outcome_pairs: list[dict[str, Any]] = []
        for language_a, language_b in PAIRS:
            result = mcnemar_exact(language_values[language_a], language_values[language_b])
            outcome_pairs.append({
                "outcome": outcome,
                "population": population,
                "paired_intents": len(subset),
                "language_a": language_a,
                "language_b": language_b,
                "test": "exact_McNemar",
                **result,
            })
        adjusted = holm_adjust([row["p_value_unadjusted"] for row in outcome_pairs])
        for row, adjusted_p in zip(outcome_pairs, adjusted):
            row["p_value_holm"] = adjusted_p
            row["significant_after_holm_0_05"] = adjusted_p < 0.05
            pairwise.append(row)
    return {
        "analysis_version": "paired-statistical-analysis-v1.0",
        "design": "paired_by_semantic_intent",
        "alpha": 0.05,
        "confidence_level": 0.95,
        "multiplicity_correction": "Holm within each outcome",
        "population": {"semantic_intents": 74, "question_variants": 222, "answerable_intents": 60, "unanswerable_intents": 14},
        "descriptive": descriptive,
        "omnibus": omnibus,
        "pairwise": pairwise,
        "semantic_measures": "NOT_EVALUATED",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path = DEFAULT_OUTPUT_DIR, overwrite: bool = False) -> dict[str, Any]:
    run_freeze = verify_run_freeze()
    protocol_freeze = verify_protocol_freeze()
    if sha256(AUTOMATED_ANALYSIS_FREEZE) != protocol_freeze["source_freezes"]["automated_heldout_analysis"]["sha256"]:
        raise ValueError("Automated held-out analysis freeze changed")
    generation_path = ROOT / run_freeze["artifacts"]["jsonl"]["path"]
    records = load_records(generation_path)
    retrieval = load_retrieval(RETRIEVAL_CSV)
    rows = build_paired_rows(records, retrieval)
    report = analyze(rows)
    report.update({
        "run_id": run_freeze["run_id"],
        "protocol_freeze_id": protocol_freeze["protocol_freeze_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "software": {"python": platform.python_version(), "scipy": scipy.__version__},
        "input_hashes": {
            "run_freeze": sha256(RUN_FREEZE),
            "generation_jsonl": sha256(generation_path),
            "retrieval_csv": sha256(RETRIEVAL_CSV),
            "protocol_freeze": sha256(PROTOCOL_FREEZE),
            "automated_analysis_freeze": sha256(AUTOMATED_ANALYSIS_FREEZE),
        },
    })
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory already contains files: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "paired_statistical_results_v1.0.json",
        "descriptive_csv": output_dir / "descriptive_metrics_v1.0.csv",
        "omnibus_csv": output_dir / "omnibus_tests_v1.0.csv",
        "pairwise_csv": output_dir / "pairwise_tests_v1.0.csv",
        "paired_outcomes_csv": output_dir / "intent_level_paired_outcomes_v1.0.csv",
    }
    with paths["json"].open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_csv(paths["descriptive_csv"], report["descriptive"])
    write_csv(paths["omnibus_csv"], report["omnibus"])
    write_csv(paths["pairwise_csv"], report["pairwise"])
    write_csv(paths["paired_outcomes_csv"], rows)
    manifest = {
        "analysis_version": report["analysis_version"],
        "protocol_freeze_id": report["protocol_freeze_id"],
        "run_id": report["run_id"],
        "population": report["population"],
        "software": report["software"],
        "inputs": report["input_hashes"],
        "outputs": {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for name, path in paths.items()},
        "semantic_measures": "NOT_EVALUATED",
        "created_at": report["created_at"],
    }
    manifest_path = output_dir / "paired_statistical_analysis_manifest_v1.0.json"
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
    print("paired semantic intents = 74")
    print("question variants = 222")
    print("development records = 0")
    print("semantic measures = NOT_EVALUATED")


if __name__ == "__main__":
    main()
