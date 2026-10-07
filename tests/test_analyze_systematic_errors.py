from src.analyze_systematic_errors import classify_record, paired_disagreements, retrieval_decision_contingency


def record(answerability="answerable", decision="ANSWER", language="EN", intent="Q001", **extra):
    value = {"run_id": "run", "split_label": "heldout_test", "intent_id": intent, "variant_id": f"{intent}-{language}", "language_condition": language, "answerability": answerability, "decision": decision, "error_status": "ok", "validation_stage": "validated", "infrastructure_error": False, "attempt_count": 1}
    value.update(extra)
    return value


def retrieval(hit5="1"):
    return {"hit_at_1": "1", "hit_at_3": "1", "hit_at_5": hit5}


def test_false_abstention_and_retrieval_miss_can_overlap():
    result = classify_record(record(decision="ABSTAIN"), retrieval("0"))
    assert result["false_abstention"] == 1
    assert result["gold_page_miss_at_5"] == 1
    assert result["structural_flag_count"] == 2


def test_false_answer_does_not_receive_retrieval_miss_flag():
    result = classify_record(record(answerability="unanswerable", decision="ANSWER"), retrieval(""))
    assert result["false_answer"] == 1
    assert result["gold_page_miss_at_5"] == 0


def test_contract_and_infrastructure_flags_are_preserved():
    result = classify_record(record(error_status="ValueError", infrastructure_error=True), retrieval())
    assert result["contract_invalid"] == 1
    assert result["infrastructure_event_recorded"] == 1


def test_contingency_uses_gold_page_intersection_wording():
    row = classify_record(record(), retrieval())
    table = retrieval_decision_contingency([row])
    assert sum(item["count"] for item in table if item["language"] == "ALL") == 1
    assert all("not semantic evidence sufficiency" in item["interpretation_boundary"] for item in table)


def test_paired_disagreement_only_includes_different_decisions():
    rows = [classify_record(record(language="EN", decision="ANSWER"), retrieval()), classify_record(record(language="MY", decision="ABSTAIN"), retrieval()), classify_record(record(language="MIX", decision="ANSWER"), retrieval())]
    result = paired_disagreements(rows)
    assert len(result) == 1
    assert result[0]["MY_false_abstention_EN_and_MIX_correct"] == 1
