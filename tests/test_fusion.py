from __future__ import annotations

import json
from pathlib import Path
import struct

import pandas as pd
import pytest

from floodguard.fusion import (
    DECISION_OUTPUT_COLUMNS,
    MODEL_CONTRACT_SCHEMA,
    OPTICAL_ONLY_VALIDATION_MODE,
    QUALITY_POLICY_SCHEMA,
    SAR_ONLY_MODE,
    SAR_OPTICAL_MODE,
    VALIDATION_MODES,
    FusionError,
    FusionModelContract,
    FusionQualityPolicy,
    assess_optical_candidates,
    evaluate_fusion_modes,
    run_late_fusion,
    verify_sar_fallback_equivalence,
    write_fusion_model_contract,
    write_fusion_quality_policy,
)


def _policy() -> FusionQualityPolicy:
    return FusionQualityPolicy(
        max_cloud_shadow_fraction_0_1=0.25,
        max_temporal_offset_hours=48.0,
        min_valid_fraction_0_1=0.70,
        min_overlap_fraction_0_1=0.80,
    )


def _contract(
    *,
    optical_source_family: str = "sentinel2",
) -> FusionModelContract:
    return FusionModelContract(
        sar_model_id="sar-encoder-v1",
        optical_model_id="optical-encoder-v1",
        fusion_model_id="late-fusion-v1",
        sar_input_features=(
            "pre_vv_db",
            "event_vv_db",
            "pre_vh_db",
            "event_vh_db",
            "vv_change_db",
            "vh_change_db",
        ),
        optical_input_features=(
            "blue_reflectance",
            "green_reflectance",
            "red_reflectance",
            "red_edge_reflectance",
            "nir_reflectance",
            "swir_reflectance",
            "ndwi",
            "mndwi",
            "cloud_distance_m",
            "pre_post_spectral_change",
        ),
        sar_weight=0.65,
        optical_weight=0.35,
        modality_dropout_probability=0.30,
        optical_source_family=optical_source_family,
    )


def _sar_inputs(*, include_reference: bool = False) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "cell_id": "CELL-A",
            "sar_probability_0_1": 0.12345678912345678,
            "source_timestamp": "2024-09-15T23:16:01Z",
            "confidence_class": "high",
            "assumptions": "SAR encoder research probability for CELL-A.",
            "reference_flood_extent": 1,
        },
        {
            "cell_id": "CELL-B",
            "sar_probability_0_1": 0.80,
            "source_timestamp": "2024-09-15T23:16:01Z",
            "confidence_class": "medium",
            "assumptions": "SAR encoder research probability for CELL-B.",
            "reference_flood_extent": 0,
        },
        {
            "cell_id": "CELL-C",
            "sar_probability_0_1": 0.70,
            "source_timestamp": "2024-09-15T23:16:01Z",
            "confidence_class": "low",
            "assumptions": "SAR encoder research probability for CELL-C.",
            "reference_flood_extent": 1,
        },
    ]
    frame = pd.DataFrame(rows)
    if not include_reference:
        frame = frame.drop(columns=["reference_flood_extent"])
    return frame


def _optical_candidate(
    *,
    cell_id: str = "CELL-A",
    candidate_id: str = "S2-A",
    source_family: str = "sentinel2",
    probability: object = 0.90,
    cloud: object = 0.10,
    temporal_offset: object = 12.0,
    valid: object = 0.90,
    overlap: object = 0.95,
    grid_status: str = "aligned_to_sar_grid",
    calibration_status: str = "calibrated",
    provenance_status: str = "verified",
    rights_status: str = "approved_for_model_input",
    confidence: str = "medium",
    **theos2_statuses: object,
) -> dict[str, object]:
    return {
        "cell_id": cell_id,
        "optical_candidate_id": candidate_id,
        "optical_source_family": source_family,
        "optical_probability_0_1": probability,
        "cloud_shadow_fraction_0_1": cloud,
        "temporal_offset_hours": temporal_offset,
        "valid_fraction_0_1": valid,
        "overlap_fraction_0_1": overlap,
        "grid_alignment_status": grid_status,
        "calibration_status": calibration_status,
        "provenance_status": provenance_status,
        "rights_status": rights_status,
        "source_timestamp": "2024-09-16T03:45:00Z",
        "confidence_class": confidence,
        "assumptions": f"{source_family} optical encoder research probability.",
        "theos2_permission_status": theos2_statuses.get(
            "theos2_permission_status", "approved_for_model_input"
        ),
        "theos2_event_overlap_status": theos2_statuses.get(
            "theos2_event_overlap_status", "confirmed"
        ),
        "theos2_temporal_alignment_status": theos2_statuses.get(
            "theos2_temporal_alignment_status", "confirmed"
        ),
        "theos2_grid_alignment_status": theos2_statuses.get(
            "theos2_grid_alignment_status", "confirmed"
        ),
    }


def test_public_modes_and_model_contract_are_exact_and_explicit() -> None:
    contract = _contract()
    payload = contract.to_dict()

    assert SAR_ONLY_MODE == "SAR only"
    assert SAR_OPTICAL_MODE == "SAR + optical"
    assert OPTICAL_ONLY_VALIDATION_MODE == "Optical only"
    assert VALIDATION_MODES == ("SAR only", "Optical only", "SAR + optical")
    assert payload["schema"] == MODEL_CONTRACT_SCHEMA
    assert payload["encoders"]["sar"]["role"] == "separate_sar_encoder"
    assert payload["encoders"]["optical"]["role"] == "separate_optical_encoder"
    assert payload["encoders"]["optical"]["source_family"] == "sentinel2"
    assert payload["late_fusion"] == {
        "method": "weighted_probability_average_after_encoders",
        "sar_weight": 0.65,
        "optical_weight": 0.35,
    }
    assert payload["modality_dropout"] == {
        "probability": 0.30,
        "rule": "optical_branch_only_sar_branch_never_dropped",
    }
    assert payload["validation_modes"] == [
        "SAR only",
        "Optical only",
        "SAR + optical",
    ]
    assert payload["training_status"] == "contract_only_no_training_or_improvement_claim"


@pytest.mark.parametrize(
    ("sar_weight", "optical_weight"),
    [(0.0, 1.0), (1.0, 0.0)],
)
def test_late_fusion_contract_requires_both_modalities(
    sar_weight: float,
    optical_weight: float,
) -> None:
    with pytest.raises(FusionError, match="greater than zero"):
        FusionModelContract(
            sar_model_id="sar",
            optical_model_id="optical",
            fusion_model_id="fusion",
            sar_input_features=("vv",),
            optical_input_features=("ndwi",),
            sar_weight=sar_weight,
            optical_weight=optical_weight,
            modality_dropout_probability=0.3,
        )


@pytest.mark.parametrize("dropout", [0.0, 1.0])
def test_modality_dropout_contract_keeps_both_availability_states(
    dropout: float,
) -> None:
    with pytest.raises(FusionError, match="greater than zero and below one"):
        FusionModelContract(
            sar_model_id="sar",
            optical_model_id="optical",
            fusion_model_id="fusion",
            sar_input_features=("vv",),
            optical_input_features=("ndwi",),
            sar_weight=0.65,
            optical_weight=0.35,
            modality_dropout_probability=dropout,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sar_encoder_role", "shared_encoder"),
        ("optical_encoder_role", "shared_encoder"),
        ("late_fusion_method", "early_fusion"),
        ("training_status", "trained_and_improved"),
    ],
)
def test_model_contract_rejects_labels_that_misstate_implementation(
    field: str,
    value: str,
) -> None:
    kwargs = {
        "sar_model_id": "sar",
        "optical_model_id": "optical",
        "fusion_model_id": "fusion",
        "sar_input_features": ("vv",),
        "optical_input_features": ("ndwi",),
        "sar_weight": 0.65,
        "optical_weight": 0.35,
        "modality_dropout_probability": 0.3,
        field: value,
    }
    with pytest.raises(FusionError):
        FusionModelContract(**kwargs)


@pytest.mark.parametrize("timestamp", ["2024-09-15T23:16:01", "not-a-timestamp"])
def test_fusion_source_timestamps_require_iso_timezone(timestamp: str) -> None:
    sar = _sar_inputs()
    sar.loc[0, "source_timestamp"] = timestamp
    with pytest.raises(FusionError, match="source_timestamp"):
        run_late_fusion(sar, None, policy=_policy(), contract=_contract())

    optical = pd.DataFrame([_optical_candidate()])
    optical.loc[0, "source_timestamp"] = timestamp
    with pytest.raises(FusionError, match="source_timestamp"):
        run_late_fusion(
            _sar_inputs(),
            optical,
            policy=_policy(),
            contract=_contract(),
        )


def test_numpy_boolean_probability_is_not_coerced_to_one() -> None:
    sar = _sar_inputs()
    sar["sar_probability_0_1"] = sar["sar_probability_0_1"].astype(object)
    sar.loc[0, "sar_probability_0_1"] = pd.Series([True]).iloc[0]
    with pytest.raises(FusionError, match="not boolean"):
        run_late_fusion(sar, None, policy=_policy(), contract=_contract())


def test_quality_policy_and_model_contract_can_be_persisted_immutably(
    tmp_path: Path,
) -> None:
    policy_path = write_fusion_quality_policy(_policy(), tmp_path / "quality.json")
    model_path = write_fusion_model_contract(_contract(), tmp_path / "model.json")

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    model = json.loads(model_path.read_text(encoding="utf-8"))
    assert policy["schema"] == QUALITY_POLICY_SCHEMA
    assert policy["max_cloud_shadow_fraction_0_1"] == 0.25
    assert policy["max_temporal_offset_hours"] == 48.0
    assert policy["min_valid_fraction_0_1"] == 0.70
    assert policy["min_overlap_fraction_0_1"] == 0.80
    assert policy["required_grid_alignment_status"] == "aligned_to_sar_grid"
    assert policy["required_calibration_status"] == "calibrated"
    assert policy["required_provenance_status"] == "verified"
    assert policy["required_rights_status"] == "approved_for_model_input"
    assert policy["required_theos2_permission_status"] == "approved_for_model_input"
    assert policy["optical_source_priority"] == ["sentinel2", "theos2"]
    assert len(policy["content_sha256"]) == 64
    assert model["schema"] == MODEL_CONTRACT_SCHEMA
    assert model["validation_modes"] == list(VALIDATION_MODES)
    assert len(model["content_sha256"]) == 64

    with pytest.raises(FusionError, match="immutable"):
        write_fusion_quality_policy(_policy(), policy_path)


def test_missing_optical_preserves_sar_probability_bits_and_common_fields() -> None:
    sar = _sar_inputs().iloc[[0]].copy()
    decisions = run_late_fusion(
        sar,
        None,
        policy=_policy(),
        contract=_contract(),
    )
    row = decisions.iloc[0]

    assert tuple(decisions.columns) == DECISION_OUTPUT_COLUMNS
    assert row["decision_input_mode"] == "SAR only"
    assert row["fusion_fallback_reason"] == "no_optical_candidate"
    assert row["fallback_equivalence_status"] == "passed"
    assert struct.pack("!d", row["flood_probability_0_1"]) == struct.pack(
        "!d", sar.iloc[0]["sar_probability_0_1"]
    )
    assert row["source_timestamp"] == "2024-09-15T23:16:01Z"
    assert row["confidence_class"] == "high"
    assert "preserved exactly" in row["assumptions"]
    assert "no fusion-improvement claim" in row["assumptions"]
    assert json.loads(row["quality_policy_json"])[
        "max_cloud_shadow_fraction_0_1"
    ] == 0.25
    assert json.loads(row["model_contract_json"])["validation_modes"] == list(
        VALIDATION_MODES
    )
    assert verify_sar_fallback_equivalence(decisions) is True


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ({"cloud": 0.26}, "cloud_shadow_exceeds_limit"),
        ({"temporal_offset": -49.0}, "temporal_offset_exceeds_limit"),
        ({"valid": 0.69}, "valid_fraction_below_limit"),
        ({"overlap": 0.79}, "overlap_fraction_below_limit"),
        ({"grid_status": "misaligned"}, "grid_alignment_not_approved"),
        ({"calibration_status": "unknown"}, "calibration_not_approved"),
        ({"provenance_status": "unverified"}, "provenance_not_approved"),
        ({"rights_status": "context_only"}, "rights_not_approved"),
    ],
)
def test_each_common_quality_gate_fails_closed(
    replacement: dict[str, object],
    reason: str,
) -> None:
    candidate = _optical_candidate(**replacement)
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        pd.DataFrame([candidate]),
        policy=_policy(),
        contract=_contract(),
    )
    row = decisions.iloc[0]

    assert row["decision_input_mode"] == SAR_ONLY_MODE
    assert reason in row["fusion_fallback_reason"]
    assert row["fallback_equivalence_status"] == "passed"
    assert row["flood_probability_0_1"] == row["sar_probability_0_1"]


def test_quality_thresholds_are_inclusive() -> None:
    candidate = _optical_candidate(
        cloud=0.25,
        temporal_offset=-48.0,
        valid=0.70,
        overlap=0.80,
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        pd.DataFrame([candidate]),
        policy=_policy(),
        contract=_contract(),
    )

    assert decisions.iloc[0]["decision_input_mode"] == SAR_OPTICAL_MODE


def test_eligible_late_fusion_uses_separate_probabilities_and_conservative_metadata() -> None:
    sar = _sar_inputs().iloc[[0]].copy()
    optical = pd.DataFrame([_optical_candidate(probability=0.90, confidence="medium")])
    decisions = run_late_fusion(
        sar,
        optical,
        policy=_policy(),
        contract=_contract(),
    )
    row = decisions.iloc[0]

    expected = 0.65 * sar.iloc[0]["sar_probability_0_1"] + 0.35 * 0.90
    assert row["decision_input_mode"] == "SAR + optical"
    assert row["decision_layer_use_status"] == "research_sidecar_not_used_by_fpps"
    assert row["flood_probability_0_1"] == pytest.approx(expected)
    assert row["selected_optical_candidate_id"] == "S2-A"
    assert row["selected_optical_source_family"] == "sentinel2"
    assert row["fusion_fallback_reason"] == "none"
    assert row["fallback_equivalence_status"] == "not_applicable_fused"
    assert row["source_timestamp"] == "2024-09-16T03:45:00Z"
    assert row["confidence_class"] == "medium"
    assert row["cloud_shadow_fraction_0_1"] == pytest.approx(0.10)
    assert "Separate encoder probabilities" in row["assumptions"]
    assert "no improvement claim" in row["assumptions"]


@pytest.mark.parametrize(
    ("status_field", "bad_status", "reason"),
    [
        (
            "theos2_permission_status",
            "preview_only",
            "theos2_permission_not_approved",
        ),
        (
            "theos2_event_overlap_status",
            "none_of_current_mvp_points",
            "theos2_event_overlap_not_confirmed",
        ),
        (
            "theos2_temporal_alignment_status",
            "unresolved",
            "theos2_temporal_alignment_not_confirmed",
        ),
        (
            "theos2_grid_alignment_status",
            "unresolved",
            "theos2_grid_alignment_not_confirmed",
        ),
    ],
)
def test_theos2_requires_separate_permission_overlap_time_and_alignment_gates(
    status_field: str,
    bad_status: str,
    reason: str,
) -> None:
    candidate = _optical_candidate(
        candidate_id="THEOS-A",
        source_family="theos2",
        **{status_field: bad_status},
    )
    assessment = assess_optical_candidates(pd.DataFrame([candidate]), _policy())
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        pd.DataFrame([candidate]),
        policy=_policy(),
        contract=_contract(),
    )

    assert bool(assessment.iloc[0]["optical_eligible"]) is False
    assert reason in assessment.iloc[0]["optical_eligibility_reason"]
    assert reason in assessment.iloc[0]["fusion_fallback_reason"]
    assert decisions.iloc[0]["decision_input_mode"] == SAR_ONLY_MODE
    assert reason in decisions.iloc[0]["fusion_fallback_reason"]


def test_ineligible_theos2_does_not_block_eligible_sentinel2() -> None:
    candidates = pd.DataFrame(
        [
            _optical_candidate(
                candidate_id="THEOS-BLOCKED",
                source_family="theos2",
                probability=0.99,
                theos2_permission_status="preview_only",
                theos2_event_overlap_status="none_of_current_mvp_points",
                theos2_temporal_alignment_status="unresolved",
                theos2_grid_alignment_status="unresolved",
            ),
            _optical_candidate(
                candidate_id="S2-ELIGIBLE",
                source_family="sentinel2",
                probability=0.75,
            ),
        ]
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        candidates,
        policy=_policy(),
        contract=_contract(),
    )
    row = decisions.iloc[0]

    assert row["decision_input_mode"] == SAR_OPTICAL_MODE
    assert row["selected_optical_candidate_id"] == "S2-ELIGIBLE"
    assert row["selected_optical_source_family"] == "sentinel2"
    assert row["optical_probability_0_1"] == pytest.approx(0.75)


def test_theos2_can_be_selected_only_after_all_separate_gates_pass() -> None:
    candidate = _optical_candidate(
        candidate_id="THEOS-ELIGIBLE",
        source_family="theos2",
        probability=0.88,
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        pd.DataFrame([candidate]),
        policy=_policy(),
        contract=_contract(optical_source_family="theos2"),
    )

    assert decisions.iloc[0]["decision_input_mode"] == SAR_OPTICAL_MODE
    assert decisions.iloc[0]["selected_optical_source_family"] == "theos2"
    assert decisions.iloc[0]["selected_optical_candidate_id"] == "THEOS-ELIGIBLE"


def test_theos2_candidate_cannot_use_a_sentinel2_encoder_contract() -> None:
    candidate = _optical_candidate(
        candidate_id="THEOS-WRONG-CONTRACT",
        source_family="theos2",
        probability=0.88,
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        pd.DataFrame([candidate]),
        policy=_policy(),
        contract=_contract(optical_source_family="sentinel2"),
    )

    row = decisions.iloc[0]
    assert row["decision_input_mode"] == SAR_ONLY_MODE
    assert row["flood_probability_0_1"] == row["sar_probability_0_1"]
    assert "optical_source_family_not_supported_by_model_contract" in row[
        "fusion_fallback_reason"
    ]


def test_source_priority_is_persisted_and_selection_is_deterministic() -> None:
    candidates = pd.DataFrame(
        [
            _optical_candidate(
                candidate_id="THEOS-CLEARER",
                source_family="theos2",
                cloud=0.01,
            ),
            _optical_candidate(
                candidate_id="S2-PREFERRED",
                source_family="sentinel2",
                cloud=0.20,
            ),
        ]
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        candidates,
        policy=_policy(),
        contract=_contract(),
    )

    assert decisions.iloc[0]["selected_optical_candidate_id"] == "S2-PREFERRED"
    policy = json.loads(decisions.iloc[0]["quality_policy_json"])
    assert policy["optical_source_priority"] == ["sentinel2", "theos2"]


def test_selection_normalizes_numeric_strings_before_quality_sorting() -> None:
    candidates = pd.DataFrame(
        [
            _optical_candidate(
                candidate_id="S2-CLOUD-010",
                source_family="sentinel2",
                cloud="0.10",
            ),
            _optical_candidate(
                candidate_id="S2-CLOUD-002",
                source_family="sentinel2",
                cloud="0.02",
            ),
        ]
    )
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        candidates,
        policy=_policy(),
        contract=_contract(),
    )

    assert decisions.iloc[0]["selected_optical_candidate_id"] == "S2-CLOUD-002"


def test_evaluator_reports_all_and_paired_sar_optical_and_fused_without_claim() -> None:
    sar = _sar_inputs(include_reference=True)
    candidates = pd.DataFrame(
        [
            _optical_candidate(cell_id="CELL-A", candidate_id="S2-A", probability=0.90),
            _optical_candidate(cell_id="CELL-B", candidate_id="S2-B", probability=0.10),
            _optical_candidate(
                cell_id="CELL-C",
                candidate_id="S2-CLOUDY",
                probability=0.95,
                cloud=0.90,
            ),
        ]
    )
    evaluation = evaluate_fusion_modes(
        sar,
        candidates,
        policy=_policy(),
        contract=_contract(),
    )
    by_slice = evaluation.set_index("evaluation_slice")

    assert list(evaluation["evaluation_slice"]) == [
        "sar_all",
        "sar_paired_subset",
        "optical_only",
        "fused",
    ]
    assert by_slice.loc["sar_all", "validation_mode"] == SAR_ONLY_MODE
    assert by_slice.loc["sar_paired_subset", "validation_mode"] == SAR_ONLY_MODE
    assert by_slice.loc["optical_only", "validation_mode"] == OPTICAL_ONLY_VALIDATION_MODE
    assert by_slice.loc["fused", "validation_mode"] == SAR_OPTICAL_MODE
    assert by_slice.loc["sar_all", "sample_count"] == 3
    assert by_slice.loc["sar_paired_subset", "sample_count"] == 2
    assert by_slice.loc["optical_only", "sample_count"] == 2
    assert by_slice.loc["fused", "sample_count"] == 2
    assert evaluation["fallback_equivalence_passed"].eq(True).all()  # noqa: E712
    assert evaluation["fusion_fallback_reason"].str.contains(
        "cloud_shadow_exceeds_limit"
    ).all()
    assert evaluation["improvement_claim_status"].eq(
        "not_claimed_descriptive_metrics_only"
    ).all()
    assert evaluation["assumptions"].str.contains("no improvement").all()
    assert evaluation["source_timestamp"].str.len().gt(0).all()
    assert evaluation["confidence_class"].eq("low").all()
    assert evaluation["quality_policy_json"].str.len().gt(0).all()
    assert evaluation["model_contract_json"].str.len().gt(0).all()


def test_evaluator_still_reports_empty_paired_modes_when_all_optical_fails() -> None:
    evaluation = evaluate_fusion_modes(
        _sar_inputs(include_reference=True),
        pd.DataFrame(
            [
                _optical_candidate(
                    cell_id="CELL-A",
                    candidate_id="S2-CLOUDY",
                    cloud=0.99,
                )
            ]
        ),
        policy=_policy(),
        contract=_contract(),
    ).set_index("evaluation_slice")

    assert evaluation.loc["sar_all", "sample_count"] == 3
    for slice_name in ("sar_paired_subset", "optical_only", "fused"):
        assert evaluation.loc[slice_name, "sample_count"] == 0
        assert pd.isna(evaluation.loc[slice_name, "iou"])
    assert bool(evaluation["fallback_equivalence_passed"].all()) is True
    assert evaluation["fusion_fallback_reason"].str.len().gt(0).all()


def test_malformed_inputs_and_contracts_fail_closed() -> None:
    with pytest.raises(FusionError, match="sum to 1.0"):
        FusionModelContract(
            sar_model_id="sar",
            optical_model_id="optical",
            fusion_model_id="fusion",
            sar_input_features=("vv",),
            optical_input_features=("nir",),
            sar_weight=0.7,
            optical_weight=0.4,
            modality_dropout_probability=0.2,
        )
    with pytest.raises(FusionError, match="sentinel2 and theos2"):
        FusionQualityPolicy(
            0.2,
            24,
            0.8,
            0.9,
            optical_source_priority=("sentinel2",),
        )

    duplicate_sar = pd.concat(
        [_sar_inputs().iloc[[0]], _sar_inputs().iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(FusionError, match="unique cell_id"):
        run_late_fusion(
            duplicate_sar,
            None,
            policy=_policy(),
            contract=_contract(),
        )

    malformed_optical = pd.DataFrame([_optical_candidate(cloud="not-a-number")])
    with pytest.raises(FusionError, match="cloud_shadow_fraction_0_1 must be numeric"):
        run_late_fusion(
            _sar_inputs().iloc[[0]],
            malformed_optical,
            policy=_policy(),
            contract=_contract(),
        )


def test_equivalence_verifier_rejects_changed_sar_only_probability() -> None:
    decisions = run_late_fusion(
        _sar_inputs().iloc[[0]],
        None,
        policy=_policy(),
        contract=_contract(),
    )
    decisions.loc[0, "flood_probability_0_1"] += 1e-12

    with pytest.raises(FusionError, match="changed probability bytes"):
        verify_sar_fallback_equivalence(decisions)
