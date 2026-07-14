from __future__ import annotations

import json

import pandas as pd
import pytest

from floodguard.historical_susceptibility import (
    AGGREGATE_FEATURE_SCHEMA,
    CONTEXT_BOUNDARY,
    CONTEXT_LABEL,
    HistoricalSusceptibilityError,
    HistoricalSusceptibilityPolicy,
    classify_context_conflict,
    partition_basin_event_groups,
    run_monotonicity_checks,
    score_historical_susceptibility,
    validate_basin_event_partition,
    validate_historical_susceptibility_features,
)


def _features(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "unit_id": "FG-HIST-001",
        **{feature: 0.5 for feature in AGGREGATE_FEATURE_SCHEMA},
        "current_sar_probability_0_1": 0.55,
        "source_timestamp": "2026-06-29T00:00:00Z",
        "confidence_class": "high",
        "assumptions": "Synthetic historical context fixture.",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_equal_features_score_fifty_and_keep_context_boundary() -> None:
    result = score_historical_susceptibility(_features()).iloc[0]

    assert result["historical_susceptibility_0_100"] == pytest.approx(50.0)
    assert result["historical_susceptibility_class"] == "moderate"
    assert result["context_label"] == CONTEXT_LABEL
    assert result["context_boundary"] == CONTEXT_BOUNDARY
    assert not bool(result["eligible_as_current_flood"])
    assert not bool(result["eligible_as_forecast"])
    assert not bool(result["eligible_to_replace_event_sar"])
    assert result["calibration_status"] == (
        "uncalibrated_requires_basin_event_target_corpus"
    )


def test_contributions_sum_to_score_and_explain_top_driver() -> None:
    result = score_historical_susceptibility(
        _features(global_flood_history_0_1=1.0)
    ).iloc[0]
    contributions = json.loads(result["historical_feature_contributions_json"])

    assert sum(contributions.values()) == pytest.approx(
        result["historical_susceptibility_0_100"]
    )
    assert result["historical_top_driver"] == "global_flood_history_0_1"
    assert "Top contribution" in result["historical_explanation"]
    assert "Global flood history" in result["historical_explanation"]
    assert "global_flood_history_0_1" not in result["historical_explanation"]


def test_missing_features_are_renormalized_and_downgrade_confidence() -> None:
    frame = _features(
        jrc_water_occurrence_0_1=None,
        jrc_water_seasonality_0_1=None,
    )
    result = score_historical_susceptibility(frame).iloc[0]

    assert result["historical_susceptibility_0_100"] == pytest.approx(50.0)
    assert result["historical_available_weight_0_1"] == pytest.approx(0.80)
    assert result["confidence_class"] == "medium"
    assert "jrc_water_occurrence_0_1" in result["historical_missing_features"]
    assert "jrc_water_seasonality_0_1" in result["historical_missing_features"]


def test_any_missing_feature_caps_high_input_confidence_at_medium() -> None:
    result = score_historical_susceptibility(
        _features(soil_runoff_potential_0_1=None)
    ).iloc[0]

    assert result["historical_available_weight_0_1"] == pytest.approx(0.96)
    assert result["confidence_class"] == "medium"


def test_low_feature_coverage_withholds_score_and_reports_conflict_unavailable() -> None:
    missing = {feature: None for feature in AGGREGATE_FEATURE_SCHEMA}
    missing["global_flood_history_0_1"] = 0.9
    result = score_historical_susceptibility(_features(**missing)).iloc[0]

    assert pd.isna(result["historical_susceptibility_0_100"])
    assert result["historical_susceptibility_class"] == "unavailable"
    assert result["historical_conflict_status"] == "not_evaluated"
    assert result["confidence_class"] == "low"
    assert "withheld" in result["historical_explanation"]


@pytest.mark.parametrize("invalid", [-0.01, 1.01, float("inf"), "bad"])
def test_feature_values_fail_closed_outside_normalized_range(invalid: object) -> None:
    with pytest.raises(HistoricalSusceptibilityError):
        validate_historical_susceptibility_features(
            _features(global_flood_history_0_1=invalid)
        )


def test_boolean_features_and_current_sar_are_rejected() -> None:
    with pytest.raises(HistoricalSusceptibilityError, match="not boolean"):
        validate_historical_susceptibility_features(
            _features(global_flood_history_0_1=True)
        )
    with pytest.raises(HistoricalSusceptibilityError, match="not boolean"):
        validate_historical_susceptibility_features(
            _features(current_sar_probability_0_1=False)
        )
    with pytest.raises(HistoricalSusceptibilityError, match="not boolean"):
        validate_historical_susceptibility_features(
            _features(jrc_water_change_0_1=pd.Series([True]).iloc[0])
        )


def test_required_columns_and_unique_units_are_enforced() -> None:
    with pytest.raises(HistoricalSusceptibilityError, match="Missing"):
        validate_historical_susceptibility_features(
            _features().drop(columns=["slope_susceptibility_0_1"])
        )
    duplicate = pd.concat([_features(), _features()], ignore_index=True)
    with pytest.raises(HistoricalSusceptibilityError, match="unique"):
        validate_historical_susceptibility_features(duplicate)


@pytest.mark.parametrize(
    "timestamp",
    ["2026-06-29T00:00:00", "not-a-timestamp"],
)
def test_source_timestamp_requires_iso_timezone(timestamp: str) -> None:
    with pytest.raises(HistoricalSusceptibilityError, match="source_timestamp"):
        validate_historical_susceptibility_features(_features(source_timestamp=timestamp))


def test_current_sar_is_preserved_and_high_sar_low_context_warns() -> None:
    low_context = {feature: 0.1 for feature in AGGREGATE_FEATURE_SCHEMA}
    result = score_historical_susceptibility(
        _features(current_sar_probability_0_1=0.88, **low_context)
    ).iloc[0]

    assert result["current_sar_probability_0_1"] == pytest.approx(0.88)
    assert result["historical_conflict_status"] == "current_sar_high_historical_low"
    assert "do not discard" in result["historical_conflict_warning"]


def test_low_sar_high_context_is_not_presented_as_current_flood() -> None:
    status, warning = classify_context_conflict(0.12, 82.0)

    assert status == "current_sar_low_historical_high"
    assert "does not establish current flooding" in warning


def test_missing_current_sar_makes_comparison_unavailable() -> None:
    result = score_historical_susceptibility(
        _features(current_sar_probability_0_1=None)
    ).iloc[0]

    assert pd.isna(result["current_sar_probability_0_1"])
    assert result["historical_conflict_status"] == "not_evaluated"


def test_monotonicity_checks_pass_for_every_available_feature() -> None:
    checks = run_monotonicity_checks(_features())

    assert set(checks["feature_name"]) == set(AGGREGATE_FEATURE_SCHEMA)
    assert checks["monotonicity_passed"].all()
    assert (checks["score_delta"] > 0).all()
    assert set(checks["source_timestamp"]) == {"2026-06-29T00:00:00Z"}
    assert set(checks["confidence_class"]) == {"high"}
    assert checks["assumptions"].str.contains("monotonicity only").all()


def test_policy_rejects_negative_or_incomplete_weights() -> None:
    incomplete = {feature: 1 / 10 for feature in AGGREGATE_FEATURE_SCHEMA[:-1]}
    with pytest.raises(HistoricalSusceptibilityError, match="every aggregate"):
        HistoricalSusceptibilityPolicy(feature_weights=incomplete)

    negative = dict(HistoricalSusceptibilityPolicy().feature_weights)
    negative["global_flood_history_0_1"] = -0.1
    with pytest.raises(HistoricalSusceptibilityError):
        HistoricalSusceptibilityPolicy(feature_weights=negative)
    with pytest.raises(HistoricalSusceptibilityError, match="greater than zero"):
        HistoricalSusceptibilityPolicy(minimum_available_weight_0_1=0.0)


def _group_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["A", "B", "C", "D", "E"],
            "basin_id": ["B1", "B1", "B2", "B3", "B4"],
            "event_id": ["E1", "E2", "E2", "E3", "E4"],
            "source_timestamp": ["2025-12-31T00:00:00Z"] * 5,
            "confidence_class": ["medium"] * 5,
            "assumptions": ["Synthetic split-integrity fixture."] * 5,
        }
    )


def test_partition_propagates_complete_connected_basin_event_holdouts() -> None:
    partitioned = partition_basin_event_groups(
        _group_rows(),
        test_basins=["B1"],
        test_events=[],
        calibration_basins=["B4"],
    )

    by_sample = partitioned.set_index("sample_id")["partition"].to_dict()
    assert by_sample == {
        "A": "test",
        "B": "test",
        "C": "test",
        "D": "train",
        "E": "calibration",
    }
    assert validate_basin_event_partition(partitioned)
    assert set(partitioned["source_timestamp"]) == {"2025-12-31T00:00:00Z"}
    assert set(partitioned["confidence_class"]) == {"medium"}


def test_conflicting_connected_holdout_seeds_fail_closed() -> None:
    with pytest.raises(HistoricalSusceptibilityError, match="conflicting"):
        partition_basin_event_groups(
            _group_rows(),
            test_basins=["B1"],
            test_events=[],
            calibration_events=["E2"],
        )


def test_validator_detects_basin_or_event_leakage() -> None:
    leaked = _group_rows()
    leaked["partition"] = ["train", "test", "test", "train", "test"]

    with pytest.raises(HistoricalSusceptibilityError, match="leaks"):
        validate_basin_event_partition(leaked)
