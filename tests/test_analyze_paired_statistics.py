import math

import pytest

from src.analyze_paired_statistics import cochran_q, holm_adjust, mcnemar_exact, wilson_interval


def test_wilson_interval_contains_observed_proportion():
    lower, upper = wilson_interval(32, 42)
    assert lower < 32 / 42 < upper
    assert 0 <= lower <= upper <= 1


def test_wilson_interval_empty_denominator():
    assert wilson_interval(0, 0) == (None, None)


def test_exact_mcnemar_counts_and_effects():
    result = mcnemar_exact([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["both_success"] == 1
    assert result["a_only_success"] == 1
    assert result["b_only_success"] == 1
    assert result["both_failure"] == 1
    assert result["p_value_unadjusted"] == 1.0
    assert result["paired_risk_difference"] == 0.0
    assert result["matched_odds_ratio"] == 1.0


def test_exact_mcnemar_handles_zero_discordant_cell():
    result = mcnemar_exact([1, 1, 0], [0, 0, 0])
    assert result["matched_odds_ratio"] == "Infinity"
    assert math.isfinite(result["matched_odds_ratio_continuity_corrected"])


def test_holm_adjustment_is_monotone_in_sorted_order():
    raw = [0.04, 0.01, 0.03]
    adjusted = holm_adjust(raw)
    ordered = sorted(zip(raw, adjusted))
    assert [value for _, value in ordered] == sorted(value for _, value in ordered)
    assert all(adjusted_value >= raw_value for raw_value, adjusted_value in zip(raw, adjusted))


def test_cochran_q_detects_identical_columns_as_undefined():
    result = cochran_q([[1, 1, 1], [0, 0, 0]])
    assert result["statistic"] is None
    assert result["p_value"] is None


def test_cochran_q_rejects_wrong_shape():
    with pytest.raises(ValueError, match="N x 3"):
        cochran_q([[1, 0]])
