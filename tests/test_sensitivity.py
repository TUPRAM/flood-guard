from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.sensitivity import (
    SensitivityError,
    run_weight_sensitivity,
    summarize_rank_instability,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_population() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_population.csv")


def test_run_weight_sensitivity_uses_deterministic_scenarios() -> None:
    result = run_weight_sensitivity(load_population())

    assert set(result["weight_scenario"]) == {
        "default",
        "access_heavy",
        "exposure_heavy",
        "road_heavy",
        "vulnerability_heavy",
    }
    assert len(result) == 25


def test_run_weight_sensitivity_normalizes_weights() -> None:
    result = run_weight_sensitivity(load_population())
    weight_columns = [
        column
        for column in result.columns
        if column.startswith("weight_") and column != "weight_scenario"
    ]

    sums = result.loc[:, weight_columns].sum(axis=1)

    assert all(value == pytest.approx(1.0) for value in sums)


def test_summarize_rank_instability_flags_rank_range_threshold() -> None:
    sensitivity = pd.DataFrame(
        {
            "weight_scenario": ["default", "alt", "default", "alt"],
            "subdistrict_id": ["A", "A", "B", "B"],
            "subdistrict_name": ["Alpha", "Alpha", "Beta", "Beta"],
            "rank": [1, 3, 2, 1],
            "action_class": ["A", "A", "B", "B"],
            "confidence_class": ["high", "high", "medium", "medium"],
        }
    )

    result = summarize_rank_instability(sensitivity).set_index("subdistrict_id")

    assert result.loc["A", "rank_range"] == 2
    assert bool(result.loc["A", "ranking_unstable"]) is True
    assert bool(result.loc["B", "ranking_unstable"]) is False


def test_run_weight_sensitivity_preserves_low_confidence_action_class() -> None:
    result = run_weight_sensitivity(load_population())
    low_confidence = result[result["subdistrict_id"] == "FG-TB-005"]

    assert set(low_confidence["confidence_class"]) == {"low"}
    assert set(low_confidence["action_class"]) == {"E"}


def test_run_weight_sensitivity_rejects_missing_fpps_input_columns() -> None:
    frame = load_population().drop(columns=["access_gap_0_100"])

    with pytest.raises(ValueError, match="access_gap_0_100"):
        run_weight_sensitivity(frame)


def test_summarize_rank_instability_requires_default_scenario() -> None:
    sensitivity = pd.DataFrame(
        {
            "weight_scenario": ["alt"],
            "subdistrict_id": ["A"],
            "subdistrict_name": ["Alpha"],
            "rank": [1],
            "action_class": ["A"],
            "confidence_class": ["high"],
        }
    )

    with pytest.raises(SensitivityError, match="default scenario"):
        summarize_rank_instability(sensitivity)
