from __future__ import annotations

import pandas as pd
import pytest

from floodguard.equity import (
    EquityError,
    compute_equity_gap,
    equity_input_from_access_loss,
    equity_loss_sensitivity_bounds,
)


def base_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subdistrict_id": "A",
                "subdistrict_name": "Alpha",
                "total_vulnerable_population": 100,
                "vulnerable_population_losing_access": 50,
                "total_non_vulnerable_population": 200,
                "non_vulnerable_population_losing_access": 50,
                "confidence_class": "medium",
            }
        ]
    )


def test_compute_equity_gap_normal_ratio() -> None:
    result = compute_equity_gap(base_frame())

    assert result.loc[0, "vulnerable_access_loss_rate"] == pytest.approx(0.5)
    assert result.loc[0, "non_vulnerable_access_loss_rate"] == pytest.approx(0.25)
    assert result.loc[0, "equity_difference_pp"] == pytest.approx(25.0)
    assert result.loc[0, "equity_gap_ratio"] == pytest.approx(2.0)
    assert result.loc[0, "equity_metric_version"] == "2.0"
    assert "2 times" in result.loc[0, "interpretation_text"]
    assert pd.isna(result.loc[0, "equity_ratio_lower_bound"])
    assert result.loc[0, "equity_ratio_bound_unavailable_reason"] == "unknown_coverage_not_supplied"


def test_compute_equity_gap_handles_no_vulnerable_denominator() -> None:
    frame = base_frame()
    frame.loc[0, "total_vulnerable_population"] = 0
    frame.loc[0, "vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert pd.isna(result.loc[0, "vulnerable_access_loss_rate"])
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert pd.isna(result.loc[0, "equity_difference_pp"])
    assert result.loc[0, "equity_ratio_unavailable_reason"] == "group_population_zero"
    assert "no vulnerable population denominator" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_no_non_vulnerable_denominator() -> None:
    frame = base_frame()
    frame.loc[0, "total_non_vulnerable_population"] = 0
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert pd.isna(result.loc[0, "non_vulnerable_access_loss_rate"])
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert result.loc[0, "equity_ratio_unavailable_reason"] == "comparison_population_zero"
    assert "no non-vulnerable population denominator" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_non_vulnerable_zero_loss_with_vulnerable_loss() -> None:
    frame = base_frame()
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert result.loc[0, "non_vulnerable_access_loss_rate"] == pytest.approx(0)
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert result.loc[0, "equity_difference_pp"] == pytest.approx(50)
    assert result.loc[0, "equity_ratio_unavailable_reason"] == "comparison_loss_rate_zero"
    assert "undefined" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_both_groups_zero_loss() -> None:
    frame = base_frame()
    frame.loc[0, "vulnerable_population_losing_access"] = 0
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert result.loc[0, "equity_difference_pp"] == pytest.approx(0)
    assert result.loc[0, "equity_ratio_unavailable_reason"] == "comparison_loss_rate_zero"
    assert "Both modeled loss rates are zero" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_rejects_missing_columns() -> None:
    frame = base_frame().drop(columns=["confidence_class"])

    with pytest.raises(EquityError, match="confidence_class"):
        compute_equity_gap(frame)


def test_equity_retains_full_precision_until_presentation() -> None:
    frame = base_frame()
    frame.loc[0, "total_vulnerable_population"] = 30
    frame.loc[0, "vulnerable_population_losing_access"] = 1
    frame.loc[0, "total_non_vulnerable_population"] = 70
    frame.loc[0, "non_vulnerable_population_losing_access"] = 2

    row = compute_equity_gap(frame).iloc[0]

    assert row["vulnerable_access_loss_rate"] == pytest.approx(1 / 30)
    assert row["non_vulnerable_access_loss_rate"] == pytest.approx(2 / 70)
    assert row["equity_difference_pp"] == pytest.approx(100 * (1 / 30 - 2 / 70))
    assert row["equity_gap_ratio"] == pytest.approx((1 / 30) / (2 / 70))


@pytest.mark.parametrize("column,value", [
    ("total_vulnerable_population", float("inf")),
    ("vulnerable_population_losing_access", float("nan")),
    ("total_non_vulnerable_population", -1),
])
def test_equity_rejects_nonfinite_or_negative_counts(column: str, value: float) -> None:
    frame = base_frame()
    frame[column] = frame[column].astype(float)
    frame.loc[0, column] = value
    with pytest.raises(EquityError, match="finite non-negative"):
        compute_equity_gap(frame)


def test_equity_rejects_loss_above_population_and_inconsistent_groups() -> None:
    frame = base_frame()
    frame.loc[0, "vulnerable_population_losing_access"] = 101
    with pytest.raises(EquityError, match="loss exceeds"):
        compute_equity_gap(frame)

    frame = base_frame()
    frame["total_population"] = 299
    with pytest.raises(EquityError, match="do not reconcile"):
        compute_equity_gap(frame)


def test_equity_unknown_coverage_bounds_keep_missing_population_explicit() -> None:
    frame = base_frame()
    frame["vulnerable_population_access_unknown"] = 20
    frame["non_vulnerable_population_access_unknown"] = 40

    row = compute_equity_gap(frame).iloc[0]

    assert row["vulnerable_access_loss_rate_lower_bound"] == pytest.approx(0.5)
    assert row["vulnerable_access_loss_rate_upper_bound"] == pytest.approx(0.7)
    assert row["non_vulnerable_access_loss_rate_lower_bound"] == pytest.approx(0.25)
    assert row["non_vulnerable_access_loss_rate_upper_bound"] == pytest.approx(0.45)
    assert row["equity_difference_pp_lower_bound"] == pytest.approx(5)
    assert row["equity_difference_pp_upper_bound"] == pytest.approx(45)
    assert row["equity_ratio_lower_bound"] == pytest.approx(0.5 / 0.45)
    assert row["equity_ratio_upper_bound"] == pytest.approx(0.7 / 0.25)
    assert row["vulnerable_access_unknown_share"] == pytest.approx(0.2)


def test_equity_unknown_coverage_with_zero_comparison_lower_rate_has_no_ratio_bound() -> None:
    bounds = equity_loss_sensitivity_bounds(100, 10, 20, 200, 0, 40)

    assert bounds["equity_difference_pp_lower_bound"] == pytest.approx(-10)
    assert bounds["equity_difference_pp_upper_bound"] == pytest.approx(30)
    assert bounds["equity_ratio_lower_bound"] is None
    assert bounds["equity_ratio_upper_bound"] is None
    assert (
        bounds["equity_ratio_bound_unavailable_reason"]
        == "comparison_loss_rate_interval_includes_zero"
    )


def test_equity_unknown_inputs_must_be_paired_and_not_overlap_known_loss() -> None:
    frame = base_frame()
    frame["vulnerable_population_access_unknown"] = 20
    with pytest.raises(EquityError, match="Both group"):
        compute_equity_gap(frame)
    frame["non_vulnerable_population_access_unknown"] = 200
    with pytest.raises(EquityError, match="loss plus unknown"):
        compute_equity_gap(frame)


def test_equity_access_adapter_passes_unknown_coverage_without_zero_filling() -> None:
    access = base_frame().rename(columns={
        "vulnerable_population_losing_access": "vulnerable_population_losing_30_min_access",
        "non_vulnerable_population_losing_access": "non_vulnerable_population_losing_30_min_access",
    })
    assert "vulnerable_population_access_unknown" not in equity_input_from_access_loss(access)
    access["vulnerable_population_access_unknown"] = 20
    access["non_vulnerable_population_access_unknown"] = 40
    result = equity_input_from_access_loss(access)
    assert result.loc[0, "vulnerable_population_access_unknown"] == 20
    assert result.loc[0, "non_vulnerable_population_access_unknown"] == 40
