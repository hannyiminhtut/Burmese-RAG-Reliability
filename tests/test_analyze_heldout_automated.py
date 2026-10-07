import json
from pathlib import Path

import pytest

from src.analyze_heldout_automated import analyze, decision_metrics, validate_population, verify_waiver_freeze


def make_records() -> list[dict]:
    records = []
    languages = ("EN", "MY", "MIX")
    for intent_number in range(1, 75):
        intent_id = f"T{intent_number:03d}"
        for language in languages:
            answerable = intent_number <= 60
            records.append({
                "intent_id": intent_id,
                "variant_id": f"{intent_id}-{language}",
                "language_condition": language,
                "answerability": "answerable" if answerable else "unanswerable",
                "decision": "ANSWER" if answerable else "ABSTAIN",
                "split_label": "heldout_test",
                "error_status": "ok",
                "validation_stage": "validated",
                "abstention_wording_compliant": True if not answerable else None,
                "infrastructure_error": False,
                "total_runtime_seconds": 1.0,
                "ollama_total_duration_ns": 500_000_000,
                "attempt_count": 1,
                "prompt_token_count": 100,
            })
    return records


def retrieval_summary() -> dict:
    base = {"Hit@1": 0.5, "Hit@3": 0.7, "Hit@5": 0.8, "MRR": 0.6}
    return {
        "answerable_metrics": base,
        "answerable_metrics_by_language": {language: base for language in ("EN", "MY", "MIX")},
        "top1_score_statistics": {},
    }


def test_exact_population_is_accepted():
    validate_population(make_records())


def test_development_overlap_is_rejected():
    records = make_records()
    records[0]["intent_id"] = "Q002"
    with pytest.raises(ValueError, match="Development intent overlap"):
        validate_population(records)


def test_incorrect_population_count_is_rejected():
    with pytest.raises(ValueError, match="Expected 222"):
        validate_population(make_records()[:-1])


def test_abstention_metrics_use_abstain_as_positive():
    rows = [
        {"answerability": "unanswerable", "decision": "ABSTAIN"},
        {"answerability": "answerable", "decision": "ABSTAIN"},
        {"answerability": "unanswerable", "decision": "ANSWER"},
        {"answerability": "answerable", "decision": "ANSWER"},
    ]
    result = decision_metrics(rows)
    assert result["decision_accuracy"]["value"] == 0.5
    assert result["abstention_precision"]["value"] == 0.5
    assert result["abstention_recall"]["value"] == 0.5
    assert result["abstention_f1"]["value"] == 0.5
    assert result["abstention_f1"]["numerator"] == 2
    assert result["abstention_f1"]["denominator"] == 4


def test_semantic_measures_remain_not_evaluated():
    result = analyze(make_records(), retrieval_summary())
    assert set(result["human_dependent_semantic_measures"].values()) == {"NOT_EVALUATED"}


def test_validation_failures_are_retained():
    records = make_records()
    records[0]["error_status"] = "ValueError"
    records[0]["validation_stage"] = "citation_validation"
    result = analyze(records, retrieval_summary())
    assert result["population"]["records"] == 222
    assert result["contract_and_reliability"]["contract_invalid_count"] == 1
    assert result["contract_and_reliability"]["contract_valid"]["denominator"] == 222


def test_frozen_waiver_verifies():
    result = verify_waiver_freeze()
    assert result["waiver_freeze_id"] == "UIT-SEMANTIC-EVALUATION-WAIVER-FREEZE-v1.0"
