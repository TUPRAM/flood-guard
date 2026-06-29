from __future__ import annotations

import pandas as pd
import pytest

from floodguard.equity import EquityError, compute_equity_gap


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
    assert result.loc[0, "equity_gap_ratio"] == pytest.approx(2.0)
    assert "more likely" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_no_vulnerable_denominator() -> None:
    frame = base_frame()
    frame.loc[0, "total_vulnerable_population"] = 0
    frame.loc[0, "vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert pd.isna(result.loc[0, "vulnerable_access_loss_rate"])
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert "no vulnerable population denominator" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_no_non_vulnerable_denominator() -> None:
    frame = base_frame()
    frame.loc[0, "total_non_vulnerable_population"] = 0
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert pd.isna(result.loc[0, "non_vulnerable_access_loss_rate"])
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert "no non-vulnerable population denominator" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_non_vulnerable_zero_loss_with_vulnerable_loss() -> None:
    frame = base_frame()
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert result.loc[0, "non_vulnerable_access_loss_rate"] == pytest.approx(0)
    assert pd.isna(result.loc[0, "equity_gap_ratio"])
    assert "undefined" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_handles_both_groups_zero_loss() -> None:
    frame = base_frame()
    frame.loc[0, "vulnerable_population_losing_access"] = 0
    frame.loc[0, "non_vulnerable_population_losing_access"] = 0

    result = compute_equity_gap(frame)

    assert result.loc[0, "equity_gap_ratio"] == pytest.approx(1.0)
    assert "No measured access-loss gap" in result.loc[0, "interpretation_text"]


def test_compute_equity_gap_rejects_missing_columns() -> None:
    frame = base_frame().drop(columns=["confidence_class"])

    with pytest.raises(EquityError, match="confidence_class"):
        compute_equity_gap(frame)
