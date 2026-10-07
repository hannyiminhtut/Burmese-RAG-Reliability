"""Build the blinded semantic-annotation package from frozen held-out outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RUN_FREEZE = ROOT / "freezes" / "uit-heldout-run-v1.1-20260819-03" / "heldout_run_freeze.json"
PROTOCOL_FREEZE = ROOT / "freezes" / "uit-semantic-annotation-protocol-v1.0" / "semantic_annotation_protocol_freeze.json"
OUTPUT_DIR = ROOT / "data" / "evaluation" / "semantic_annotation_v1.0"
RANDOM_SEED = 20260820

LABEL_COLUMNS = [
    "reviewer_id",
    "decision_correctness",
    "evidence_conditioned_decision_appropriateness",
    "answer_correctness",
    "numeric_correctness",
    "groundedness",
    "hallucination",
    "citation_support",
    "language_consistency",
    "output_cleanliness",
    "abstention_wording_compliance",
    "contract_validity_confirmation",
    "gold_evidence_location",
    "primary_failure_attribution",
    "secondary_failure_attributions",
    "reviewer_evidence_notes",
    "annotation_complete",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def verify_frozen_sources() -> Dict[str, Any]:
    run_freeze = read_json(RUN_FREEZE)
    protocol_freeze = read_json(PROTOCOL_FREEZE)
    for artifact in run_freeze["artifacts"].values():
        path = ROOT / artifact["path"]
        if sha256(path) != artifact["sha256"]:
            raise ValueError(f"Frozen held-out artifact changed: {path}")
    protocol = protocol_freeze["protocol"]
    if sha256(ROOT / protocol["path"]) != protocol["sha256"]:
        raise ValueError("Frozen semantic annotation protocol changed")
    if sha256(RUN_FREEZE) != protocol_freeze["applies_to"]["run_freeze_sha256"]:
        raise ValueError("Run freeze differs from annotation protocol freeze")
    return {"run_freeze": run_freeze, "protocol_freeze": protocol_freeze}


def build_rows(frozen: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    run_path = ROOT / frozen["run_freeze"]["artifacts"]["jsonl"]["path"]
    records = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines() if line]
    metadata_path = ROOT / "models" / "uit_academic_credits_v1_1_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata_by_id = {row["chunk_id"]: row for row in metadata}
    if len(records) != 222 or len({row["variant_id"] for row in records}) != 222:
        raise ValueError("Expected 222 unique frozen held-out records")

    shuffled = list(records)
    random.Random(RANDOM_SEED).shuffle(shuffled)
    reviewer_rows: List[Dict[str, Any]] = []
    key_rows: List[Dict[str, Any]] = []
    for position, record in enumerate(shuffled, 1):
        annotation_id = f"UIT-ANN-{position:03d}"
        original_citations = record.get("original_citations", record.get("citations", []))
        row: Dict[str, Any] = {
            "annotation_id": annotation_id,
            "language_condition": record["language_condition"],
            "answerability": record["answerability"],
            "question": record["question"],
            "gold_answer": record.get("benchmark_gold_answer", ""),
            "generated_decision": record["decision"],
            "generated_answer": record["generated_answer"],
            "original_citations": json.dumps(original_citations, ensure_ascii=False),
            "frozen_contract_status": "PASS" if record["error_status"] == "ok" else "FAIL",
            "frozen_validation_stage": record["validation_stage"],
            "frozen_validation_error": record.get("validation_error", ""),
        }
        # Gold answers are not duplicated in generation records; recover them from the benchmark below.
        for rank, chunk_id in enumerate(record["retrieved_chunk_ids"], 1):
            chunk = metadata_by_id[chunk_id]
            row[f"evidence_{rank}_chunk_id"] = chunk_id
            row[f"evidence_{rank}_pages"] = json.dumps(
                chunk.get("pages", [chunk["page"]]), ensure_ascii=False
            )
            row[f"evidence_{rank}_text"] = chunk["text"]
        for column in LABEL_COLUMNS:
            row[column] = ""
        reviewer_rows.append(row)
        key_rows.append({
            "annotation_id": annotation_id,
            "original_position": position,
            "intent_id": record["intent_id"],
            "variant_id": record["variant_id"],
            "run_id": record["run_id"],
        })

    benchmark_path = ROOT / frozen["run_freeze"]["frozen_inputs"]["benchmark"]["path"]
    with benchmark_path.open("r", encoding="utf-8-sig", newline="") as stream:
        benchmark_by_variant = {row["variant_id"]: row for row in csv.DictReader(stream)}
    for row, key in zip(reviewer_rows, key_rows):
        row["gold_answer"] = benchmark_by_variant[key["variant_id"]]["gold_answer"]
    return reviewer_rows, key_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty annotation table")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    frozen = verify_frozen_sources()
    if OUTPUT_DIR.exists() and any(OUTPUT_DIR.iterdir()):
        raise FileExistsError(f"Annotation package already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reviewer_rows, key_rows = build_rows(frozen)
    write_csv(OUTPUT_DIR / "reviewer_1_annotation.csv", reviewer_rows)
    write_csv(OUTPUT_DIR / "reviewer_2_annotation.csv", reviewer_rows)
    write_csv(OUTPUT_DIR / "blinded_id_key.csv", key_rows)
    print("annotation rows = 222")
    print("semantic labels assigned = 0")
    print("development records included = 0")


if __name__ == "__main__":
    main()
