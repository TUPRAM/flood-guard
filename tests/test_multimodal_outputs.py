from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from floodguard.fusion import SAR_ONLY_MODE, SAR_OPTICAL_MODE
from floodguard.historical_susceptibility import (
    CONTEXT_BOUNDARY,
    CONTEXT_LABEL,
    validate_basin_event_partition,
)


REPO_ROOT = Path(__file__).parents[1]
OUTPUTS = REPO_ROOT / "outputs"


def test_generated_fusion_output_preserves_sar_fallback_and_declares_modes() -> None:
    decisions = pd.read_csv(OUTPUTS / "sample_sar_optical_fusion.csv")

    assert set(decisions["decision_input_mode"]) == {SAR_ONLY_MODE, SAR_OPTICAL_MODE}
    assert set(decisions["decision_layer_use_status"]) == {
        "research_sidecar_not_used_by_fpps"
    }
    fallback = decisions.loc[decisions["decision_input_mode"] == SAR_ONLY_MODE]
    assert (fallback["flood_probability_0_1"] == fallback["sar_probability_0_1"]).all()
    assert set(fallback["fallback_equivalence_status"]) == {"passed"}
    selected = set(decisions["selected_optical_candidate_id"].dropna())
    assert "S2-FIXTURE-CLEAR-001" in selected
    assert "THEOS2-FIXTURE-BLOCKED-004" not in selected


def test_generated_candidate_assessment_keeps_theos2_failure_auditable() -> None:
    assessed = pd.read_csv(
        OUTPUTS / "sample_optical_fusion_candidate_assessment.csv"
    ).set_index("optical_candidate_id")

    theos2 = assessed.loc["THEOS2-FIXTURE-BLOCKED-004"]
    assert not bool(theos2["optical_eligible"])
    assert "theos2_permission_not_approved" in theos2["optical_eligibility_reason"]
    sentinel2 = assessed.loc["S2-FIXTURE-CLEAR-004"]
    assert bool(sentinel2["optical_eligible"])


def test_generated_fusion_validation_has_separate_non_claiming_slices() -> None:
    validation = pd.read_csv(OUTPUTS / "sample_sar_optical_fusion_validation.csv")

    assert list(validation["evaluation_slice"]) == [
        "sar_all",
        "sar_paired_subset",
        "optical_only",
        "fused",
    ]
    assert validation["fallback_equivalence_passed"].all()
    assert validation["improvement_claim_status"].str.contains("not_claimed").all()


def test_generated_optical_features_mask_cloud_and_near_cloud_rows() -> None:
    features = pd.read_csv(OUTPUTS / "sample_sentinel2_optical_features.csv")
    valid = features.set_index("pixel_id")["optical_valid"].to_dict()

    assert valid == {
        "S2-PX-001": True,
        "S2-PX-002": False,
        "S2-PX-003": False,
    }
    assert set(features["flood_truth_status"]) == {"not_flood_truth"}
    assert not features["eligible_for_flood_truth"].any()
    cloudy = features.set_index("pixel_id").loc["S2-PX-002"]
    assert pd.isna(cloudy["post_B03_masked"])
    assert pd.isna(cloudy["post_B11_masked"])
    assert pd.isna(cloudy["ndwi_change"])


def test_generated_historical_context_is_not_current_flood_or_forecast() -> None:
    context = pd.read_csv(OUTPUTS / "sample_historical_susceptibility_context.csv")

    assert set(context["context_label"]) == {CONTEXT_LABEL}
    assert set(context["context_boundary"]) == {CONTEXT_BOUNDARY}
    assert not context["eligible_as_current_flood"].any()
    assert not context["eligible_as_forecast"].any()
    assert not context["eligible_to_replace_event_sar"].any()
    hillside = context.set_index("unit_id").loc["FG-TB-005"]
    assert hillside["historical_conflict_status"] == "current_sar_high_historical_low"


def test_generated_monotonicity_and_group_holdout_evidence_passes() -> None:
    monotonicity = pd.read_csv(
        OUTPUTS / "sample_historical_susceptibility_monotonicity.csv"
    )
    partitions = pd.read_csv(OUTPUTS / "sample_historical_basin_event_partitions.csv")

    assert monotonicity["monotonicity_passed"].all()
    assert validate_basin_event_partition(partitions)
    assert set(partitions["partition"]) == {"train", "calibration", "test"}
    for frame in (monotonicity, partitions):
        assert frame["source_timestamp"].notna().all()
        assert frame["confidence_class"].notna().all()
        assert frame["assumptions"].notna().all()


def test_dashboard_geojson_adds_context_without_changing_fpps() -> None:
    priority = pd.read_csv(OUTPUTS / "sample_priority_scores.csv").set_index(
        "subdistrict_id"
    )
    payload = json.loads(
        (OUTPUTS / "priority_subdistricts.geojson").read_text(encoding="utf-8")
    )
    properties = {
        feature["properties"]["subdistrict_id"]: feature["properties"]
        for feature in payload["features"]
    }

    assert set(properties) == set(priority.index)
    for unit_id, props in properties.items():
        assert props["fpps_0_100"] == priority.at[unit_id, "fpps_0_100"]
        assert props["fusion_candidate_mode"] in {SAR_ONLY_MODE, SAR_OPTICAL_MODE}
        assert props["decision_layer_use_status"] == (
            "research_sidecar_not_used_by_fpps"
        )
        assert props["context_label"] == CONTEXT_LABEL
        assert props["context_boundary"] == CONTEXT_BOUNDARY
