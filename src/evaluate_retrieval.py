"""Run the deterministic 15-question retrieval pilot."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple

import yaml

from src.retrieve import Retriever


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment_config.yaml"
RESULT_COLUMNS = [
    "run_id", "split_label", "intent_id", "variant_id", "language_condition",
    "answerability", "question", "gold_evidence_page", "top1_chunk_id",
    "top1_page", "top1_score", "retrieved_chunk_ids", "retrieved_pages",
    "retrieved_page_sets", "retrieved_scores", "hit_at_1", "hit_at_3", "hit_at_5",
    "first_relevant_rank", "reciprocal_rank", "evaluation_status", "error_notes",
]
EXPECTED_PILOT_INTENTS = {"Q002", "Q008", "Q024", "Q029", "Q057"}


def load_benchmark(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "intent_id", "variant_id", "language_condition", "answerability",
        "question", "evidence_page",
    }
    if not rows:
        raise ValueError("Benchmark is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError("Benchmark missing column(s): " + ", ".join(sorted(missing)))
    return rows


def load_pilot_intents(path: Path) -> List[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    intent_ids = document.get("selected_intent_ids")
    if not isinstance(intent_ids, list) or len(intent_ids) != 5:
        raise ValueError("Pilot-intent file must contain exactly 5 selected_intent_ids")
    if any(not isinstance(item, str) or not item for item in intent_ids):
        raise ValueError("Pilot intent IDs must be non-empty strings")
    if len(set(intent_ids)) != 5:
        raise ValueError("Pilot intent IDs must be unique")
    if set(intent_ids) != EXPECTED_PILOT_INTENTS:
        raise ValueError("Pilot intent IDs do not match the frozen development set")
    return intent_ids


def select_fixed_pilot(
    rows: Sequence[Dict[str, str]], selected_ids: Sequence[str]
) -> List[Dict[str, str]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["intent_id"]].append(row)

    missing = [intent_id for intent_id in selected_ids if intent_id not in grouped]
    if missing:
        raise ValueError("Pilot intent ID(s) absent from benchmark: " + ", ".join(missing))
    for intent_id in selected_ids:
        variants = grouped[intent_id]
        labels = {row["answerability"] for row in variants}
        languages = [row["language_condition"] for row in variants]
        if len(variants) != 3 or Counter(languages) != Counter({"EN": 1, "MY": 1, "MIX": 1}):
            raise ValueError(f"Intent {intent_id} must have exactly EN, MY, and MIX variants")
        if labels not in ({"answerable"}, {"unanswerable"}):
            raise ValueError(f"Intent {intent_id} has inconsistent answerability labels")
    selected_set = set(selected_ids)
    pilot_rows = [row for row in rows if row["intent_id"] in selected_set]
    if len(selected_ids) != 5 or len(pilot_rows) != 15:
        raise ValueError("Fixed pilot must contain exactly 5 intents and 15 rows")
    if Counter(row["language_condition"] for row in pilot_rows) != Counter(
        {"EN": 5, "MY": 5, "MIX": 5}
    ):
        raise ValueError("Fixed pilot must contain exactly 5 EN, 5 MY, and 5 MIX rows")
    if Counter(row["answerability"] for row in pilot_rows) != Counter(
        {"answerable": 9, "unanswerable": 6}
    ):
        raise ValueError("Fixed pilot must contain exactly 9 answerable and 6 unanswerable rows")
    return pilot_rows


def select_heldout_rows(
    rows: Sequence[Dict[str, str]], pilot_intent_ids: Sequence[str]
) -> List[Dict[str, str]]:
    """Exclude the exact development intents and validate the frozen test split."""
    pilot_set = set(pilot_intent_ids)
    if pilot_set != EXPECTED_PILOT_INTENTS:
        raise ValueError("Held-out exclusion does not match the frozen development set")
    heldout = [row for row in rows if row["intent_id"] not in pilot_set]
    heldout_intents = {row["intent_id"] for row in heldout}
    if heldout_intents & pilot_set:
        raise ValueError("Development and held-out intent sets overlap")
    checks = {
        "semantic intents": (len(heldout_intents), 74),
        "question variants": (len(heldout), 222),
        "answerable rows": (
            sum(row["answerability"] == "answerable" for row in heldout), 180
        ),
        "unanswerable rows": (
            sum(row["answerability"] == "unanswerable" for row in heldout), 42
        ),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise ValueError(f"Expected {expected} held-out {label}, found {actual}")
    languages = Counter(row["language_condition"] for row in heldout)
    if languages != Counter({"EN": 74, "MY": 74, "MIX": 74}):
        raise ValueError(f"Expected 74 held-out rows per language, found {dict(languages)}")
    return heldout


def parse_evidence_pages(value: Any) -> Set[int]:
    """Parse integers, inclusive ranges, and comma/semicolon-separated pages."""
    if isinstance(value, (list, tuple, set)):
        pages: Set[int] = set()
        for item in value:
            pages.update(parse_evidence_pages(item))
        return pages
    text = str(value).strip()
    if not text:
        return set()
    pages: Set[int] = set()
    for token in re.split(r"[,;]", text):
        token = token.strip()
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", token)
        if match:
            start, end = map(int, match.groups())
            if start > end:
                raise ValueError(f"Descending evidence-page range: {token}")
            pages.update(range(start, end + 1))
        elif re.fullmatch(r"\d+", token):
            pages.add(int(token))
        else:
            raise ValueError(f"Malformed evidence-page value: {text}")
    return pages


def relevance_metrics(
    retrieved_pages: Sequence[Any], gold_pages: Set[int]
) -> Dict[str, Any]:
    if not gold_pages:
        raise ValueError("Answerable question has no gold evidence page")
    relevant_ranks = []
    for rank, page_value in enumerate(retrieved_pages, start=1):
        if parse_evidence_pages(page_value) & gold_pages:
            relevant_ranks.append(rank)
    first = min(relevant_ranks) if relevant_ranks else None
    return {
        "hit_at_1": int(any(rank <= 1 for rank in relevant_ranks)),
        "hit_at_3": int(any(rank <= 3 for rank in relevant_ranks)),
        "hit_at_5": int(any(rank <= 5 for rank in relevant_ranks)),
        "first_relevant_rank": first if first is not None else "",
        "reciprocal_rank": (1.0 / first) if first is not None else 0.0,
    }


def _score_summary(values: Sequence[float]) -> Dict[str, Any]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
    }


def _detailed_score_summary(values: Sequence[float]) -> Dict[str, Any]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "standard_deviation": statistics.pstdev(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _answerable_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [
        row for row in rows
        if row["answerability"] == "answerable" and row["evaluation_status"] == "evaluated"
    ]
    if not valid:
        return {"Hit@1": None, "Hit@3": None, "Hit@5": None, "MRR": None}
    return {
        "Hit@1": statistics.fmean(row["hit_at_1"] for row in valid),
        "Hit@3": statistics.fmean(row["hit_at_3"] for row in valid),
        "Hit@5": statistics.fmean(row["hit_at_5"] for row in valid),
        "MRR": statistics.fmean(row["reciprocal_rank"] for row in valid),
    }


def write_results_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_pilot(
    config_path: Path = CONFIG_PATH,
    pilot_intents_path: Path = PROJECT_ROOT / "results" / "pilot_intents.json",
    output_results: Path = PROJECT_ROOT / "results" / "pilot_retrieval_results.csv",
    output_summary: Path = PROJECT_ROOT / "results" / "pilot_retrieval_summary.json",
    retriever: Any = None,
) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    root = config_path.resolve().parent.parent
    benchmark_path = root / Path(config["benchmark"]["file"])
    seed = config["reproducibility"]["random_seed"]
    rows = load_benchmark(benchmark_path)
    selected_ids = load_pilot_intents(pilot_intents_path)
    pilot_rows = select_fixed_pilot(rows, selected_ids)
    if retriever is None:
        retriever = Retriever(config_path=config_path)

    protected_names = {
        "pilot_retrieval_results_v1.0.csv",
        "pilot_retrieval_summary_v1.0.json",
    }
    if output_results.name in protected_names or output_summary.name in protected_names:
        raise ValueError("Output path would overwrite a protected v1.0 result")
    output_results.parent.mkdir(parents=True, exist_ok=True)
    output_summary.parent.mkdir(parents=True, exist_ok=True)

    result_rows: List[Dict[str, Any]] = []
    run_id = f"{config['experiment_id']}-pilot-seed-{seed}"
    for row in pilot_rows:
        result: Dict[str, Any] = {
            "run_id": run_id,
            "split_label": "development_pilot",
            "intent_id": row["intent_id"],
            "variant_id": row["variant_id"],
            "language_condition": row["language_condition"],
            "answerability": row["answerability"],
            "question": row["question"],
            "gold_evidence_page": row["evidence_page"],
            "top1_chunk_id": "", "top1_page": "", "top1_score": "",
            "retrieved_chunk_ids": "[]", "retrieved_pages": "[]",
            "retrieved_page_sets": "[]", "retrieved_scores": "[]",
            "hit_at_1": "", "hit_at_3": "",
            "hit_at_5": "", "first_relevant_rank": "",
            "reciprocal_rank": "", "evaluation_status": "error", "error_notes": "",
        }
        try:
            retrieved = retriever.retrieve(row["question"], top_k=5)
            ids = [item["chunk_id"] for item in retrieved]
            pages = [item["page"] for item in retrieved]
            page_sets = [item.get("pages", [item["page"]]) for item in retrieved]
            scores = [item["similarity_score"] for item in retrieved]
            result.update(
                top1_chunk_id=ids[0], top1_page=pages[0], top1_score=scores[0],
                retrieved_chunk_ids=json.dumps(ids, ensure_ascii=False),
                retrieved_pages=json.dumps(pages, ensure_ascii=False),
                retrieved_page_sets=json.dumps(page_sets, ensure_ascii=False),
                retrieved_scores=json.dumps(scores, ensure_ascii=False),
            )
            if row["answerability"] == "answerable":
                result.update(relevance_metrics(page_sets, parse_evidence_pages(row["evidence_page"])))
                result["evaluation_status"] = "evaluated"
            else:
                result["evaluation_status"] = "unanswerable_score_only"
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            result["error_notes"] = str(exc)
        result_rows.append(result)

    write_results_csv(output_results, result_rows)
    successful = [row for row in result_rows if row["evaluation_status"] != "error"]
    scores = [float(row["top1_score"]) for row in successful]
    score_groups = {
        "overall": scores,
        "answerable": [float(r["top1_score"]) for r in successful if r["answerability"] == "answerable"],
        "unanswerable": [float(r["top1_score"]) for r in successful if r["answerability"] == "unanswerable"],
    }
    for language in ("EN", "MY", "MIX"):
        score_groups[language] = [
            float(r["top1_score"]) for r in successful if r["language_condition"] == language
        ]
    summary = {
        "experiment_id": config["experiment_id"],
        "corpus_version": config["corpus"]["corpus_version"],
        "chunk_count": retriever.manifest["chunk_count"],
        "embedding_model": retriever.manifest["embedding_model"],
        "fixed_pilot_intent_ids": selected_ids,
        "random_seed": seed,
        "selected_intent_count": len(selected_ids),
        "total_question_count": len(result_rows),
        "answerable_question_count": sum(r["answerability"] == "answerable" for r in result_rows),
        "unanswerable_question_count": sum(r["answerability"] == "unanswerable" for r in result_rows),
        "counts_by_language_condition": dict(Counter(r["language_condition"] for r in result_rows)),
        "answerable_metrics": _answerable_metrics(result_rows),
        "answerable_metrics_by_language": {
            language: _answerable_metrics([r for r in result_rows if r["language_condition"] == language])
            for language in ("EN", "MY", "MIX")
        },
        "top1_similarity_scores": {name: _score_summary(values) for name, values in score_groups.items()},
        "error_count": sum(r["evaluation_status"] == "error" for r in result_rows),
        "skipped_row_count": 0,
        "creation_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    output_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOGGER.info("Saved retrieval pilot results for %d questions", len(result_rows))
    return {"selected_intent_ids": selected_ids, "results": result_rows, "summary": summary}


def run_heldout(
    config_path: Path,
    pilot_intents_path: Path,
    output_results: Path,
    output_summary: Path,
    retriever: Any = None,
) -> Dict[str, Any]:
    """Evaluate all non-development intents as the frozen held-out test set."""
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    root = config_path.resolve().parent.parent
    benchmark_rows = load_benchmark(root / Path(config["benchmark"]["file"]))
    pilot_ids = load_pilot_intents(pilot_intents_path)
    heldout_rows = select_heldout_rows(benchmark_rows, pilot_ids)
    if retriever is None:
        retriever = Retriever(config_path=config_path)

    if output_results.name == "pilot_retrieval_results_v1.0.csv" or output_summary.name == "pilot_retrieval_summary_v1.0.json":
        raise ValueError("Output path would overwrite a protected v1.0 result")
    output_results.parent.mkdir(parents=True, exist_ok=True)
    output_summary.parent.mkdir(parents=True, exist_ok=True)

    questions = [row["question"] for row in heldout_rows]
    retrieved_batches = retriever.retrieve_many(questions, top_k=5)
    if len(retrieved_batches) != len(heldout_rows):
        raise ValueError("Batch retrieval result count does not match held-out rows")

    run_id = f"{config['experiment_id']}-heldout-test"
    result_rows: List[Dict[str, Any]] = []
    for row, retrieved in zip(heldout_rows, retrieved_batches):
        result: Dict[str, Any] = {
            "run_id": run_id,
            "split_label": "heldout_test",
            "intent_id": row["intent_id"],
            "variant_id": row["variant_id"],
            "language_condition": row["language_condition"],
            "answerability": row["answerability"],
            "question": row["question"],
            "gold_evidence_page": row["evidence_page"],
            "top1_chunk_id": "", "top1_page": "", "top1_score": "",
            "retrieved_chunk_ids": "[]", "retrieved_pages": "[]",
            "retrieved_page_sets": "[]", "retrieved_scores": "[]",
            "hit_at_1": "", "hit_at_3": "", "hit_at_5": "",
            "first_relevant_rank": "", "reciprocal_rank": "",
            "evaluation_status": "error", "error_notes": "",
        }
        try:
            ids = [item["chunk_id"] for item in retrieved]
            pages = [item["page"] for item in retrieved]
            page_sets = [item.get("pages", [item["page"]]) for item in retrieved]
            scores = [item["similarity_score"] for item in retrieved]
            if len(ids) != 5:
                raise ValueError(f"Expected 5 retrieved chunks, found {len(ids)}")
            result.update(
                top1_chunk_id=ids[0], top1_page=pages[0], top1_score=scores[0],
                retrieved_chunk_ids=json.dumps(ids, ensure_ascii=False),
                retrieved_pages=json.dumps(pages, ensure_ascii=False),
                retrieved_page_sets=json.dumps(page_sets, ensure_ascii=False),
                retrieved_scores=json.dumps(scores, ensure_ascii=False),
            )
            if row["answerability"] == "answerable":
                result.update(
                    relevance_metrics(page_sets, parse_evidence_pages(row["evidence_page"]))
                )
                result["evaluation_status"] = "evaluated"
            else:
                result["evaluation_status"] = "unanswerable_score_only"
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            result["error_notes"] = str(exc)
        result_rows.append(result)

    write_results_csv(output_results, result_rows)
    successful = [row for row in result_rows if row["evaluation_status"] != "error"]
    answerable_scores = [
        float(row["top1_score"]) for row in successful
        if row["answerability"] == "answerable"
    ]
    unanswerable_scores = [
        float(row["top1_score"]) for row in successful
        if row["answerability"] == "unanswerable"
    ]
    summary = {
        "experiment_id": config["experiment_id"],
        "corpus_version": config["corpus"]["corpus_version"],
        "corpus_sha256": retriever.manifest["input_sha256"],
        "excluded_pilot_intent_ids": pilot_ids,
        "heldout_intent_count": len({row["intent_id"] for row in result_rows}),
        "heldout_question_count": len(result_rows),
        "answerable_question_count": sum(row["answerability"] == "answerable" for row in result_rows),
        "unanswerable_question_count": sum(row["answerability"] == "unanswerable" for row in result_rows),
        "counts_by_language_condition": dict(Counter(row["language_condition"] for row in result_rows)),
        "answerable_metrics": _answerable_metrics(result_rows),
        "answerable_metrics_by_language": {
            language: _answerable_metrics(
                [row for row in result_rows if row["language_condition"] == language]
            )
            for language in ("EN", "MY", "MIX")
        },
        "top1_score_statistics": {
            "answerable": _detailed_score_summary(answerable_scores),
            "unanswerable": _detailed_score_summary(unanswerable_scores),
        },
        "error_count": sum(row["evaluation_status"] == "error" for row in result_rows),
        "skipped_row_count": 0,
        "creation_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    output_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOGGER.info("Saved held-out retrieval results for %d questions", len(result_rows))
    return {"results": result_rows, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the frozen retrieval index")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--pilot-intents", type=Path, required=True)
    parser.add_argument("--output-results", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--heldout", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    runner = run_heldout if args.heldout else run_pilot
    runner(
        config_path=args.config, pilot_intents_path=args.pilot_intents,
        output_results=args.output_results, output_summary=args.output_summary,
    )


if __name__ == "__main__":
    main()
