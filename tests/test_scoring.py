from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.scoring import (
    ACTION_REASON_CODES,
    MissingColumnsError,
    assign_action_reason_code,
    score_subdistricts,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_sample_population() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_population.csv")


def test_score_subdistricts_computes_expected_scores_and_columns() -> None:
    frame = load_sample_population()

    result = score_subdistricts(frame)

    assert {
        "subdistrict_id",
        "subdistrict_name",
        "fpps_0_100",
        "action_class",
        "action_reason_code",
        "top_reason",
        "confidence_class",
    }.issubset(result.columns)
    assert result.loc[0, "subdistrict_id"] == "FG-TB-001"
    assert result.loc[0, "subdistrict_name"] == "River Market"
    assert result.loc[0, "confidence_class"] == "high"
    assert result.loc[0, "fpps_0_100"] == pytest.approx(81.60)
    assert result.loc[1, "fpps_0_100"] == pytest.approx(63.85)


def test_score_subdistricts_assigns_all_action_classes() -> None:
    result = score_subdistricts(load_sample_population())

    classes_by_id = dict(zip(result["subdistrict_id"], result["action_class"], strict=True))

    assert classes_by_id == {
        "FG-TB-001": "A",
        "FG-TB-002": "B",
        "FG-TB-003": "C",
        "FG-TB-004": "D",
        "FG-TB-005": "E",
    }
    assert "life-safety" in result.loc[result["subdistrict_id"] == "FG-TB-001", "top_reason"].item()
    assert "isolation" in result.loc[result["subdistrict_id"] == "FG-TB-002", "top_reason"].item()
    assert "essential services" in result.loc[result["subdistrict_id"] == "FG-TB-003", "top_reason"].item()
    assert "Highest driver" in result.loc[result["subdistrict_id"] == "FG-TB-004", "top_reason"].item()
    assert "confidence is low" in result.loc[result["subdistrict_id"] == "FG-TB-005", "top_reason"].item()
    reasons_by_id = dict(
        zip(result["subdistrict_id"], result["action_reason_code"], strict=True)
    )
    assert reasons_by_id == {
        "FG-TB-001": "life_safety_exposure",
        "FG-TB-002": "critical_route_access",
        "FG-TB-003": "essential_service_access",
        "FG-TB-004": "resilience",
        "FG-TB-005": "low_confidence",
    }
    assert set(reasons_by_id.values()).issubset(set(ACTION_REASON_CODES))


def test_action_reason_code_distinguishes_the_two_class_e_paths() -> None:
    low_confidence = {
        "confidence_class": "low",
        "fpps_0_100": 80,
        "action_class": "E",
    }
    low_priority = {
        "confidence_class": "high",
        "fpps_0_100": 34.99,
        "action_class": "E",
    }

    assert assign_action_reason_code(low_confidence) == "low_confidence"
    assert assign_action_reason_code(low_priority) == "low_priority_score"


def test_score_subdistricts_raises_clear_error_for_missing_columns() -> None:
    frame = load_sample_population().drop(columns=["access_gap_0_100"])

    with pytest.raises(MissingColumnsError, match="access_gap_0_100"):
        score_subdistricts(frame)


def test_score_subdistricts_rejects_out_of_range_component_values() -> None:
    frame = load_sample_population()
    frame.loc[0, "exposure_0_100"] = 101

    with pytest.raises(ValueError, match="exposure_0_100"):
        score_subdistricts(frame)


def test_score_subdistricts_handles_boundary_values() -> None:
    frame = pd.DataFrame(
        [
            {
                "subdistrict_id": "LOW",
                "subdistrict_name": "All Zero",
                "flood_likelihood_0_100": 0,
                "exposure_0_100": 0,
                "access_gap_0_100": 0,
                "road_criticality_0_100": 0,
                "vulnerability_context_0_100": 0,
                "confidence_class": "high",
            },
            {
                "subdistrict_id": "HIGH",
                "subdistrict_name": "All Hundred",
                "flood_likelihood_0_100": 100,
                "exposure_0_100": 100,
                "access_gap_0_100": 100,
                "road_criticality_0_100": 100,
                "vulnerability_context_0_100": 100,
                "confidence_class": "high",
            },
        ]
    )

    result = score_subdistricts(frame)

    assert result.loc[0, "fpps_0_100"] == pytest.approx(0)
    assert result.loc[0, "action_class"] == "E"
    assert result.loc[1, "fpps_0_100"] == pytest.approx(100)
    assert result.loc[1, "action_class"] == "A"


def test_score_subdistricts_normalizes_custom_weights() -> None:
    frame = load_sample_population().iloc[[0]].copy()
    weights = {
        "flood_likelihood_0_100": 3,
        "exposure_0_100": 0,
        "access_gap_0_100": 0,
        "road_criticality_0_100": 0,
        "vulnerability_context_0_100": 0,
    }

    result = score_subdistricts(frame, weights=weights)

    assert result.loc[0, "fpps_0_100"] == pytest.approx(88)
