from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from floodguard.label_factory.annotations import AnnotationRecord, LabelClass
from floodguard.label_factory.qa import (
    LabelFactoryQAError,
    run_label_factory_qa,
    validate_binary_training_rows,
    validate_dataset_roles,
    validate_query_model_safety,
    validate_source_assets,
    validate_test_set_isolation,
)


def test_full_qa_report_passes_safe_foundation() -> None:
    report = run_label_factory_qa(
        source_assets=_valid_assets(),
        dataset_assignments=_assignments(),
        usage_records=[{"region_id": "TRAIN-1", "purpose": "training"}, {"region_id": "TEST-1", "purpose": "final_evaluation"}],
        query_models=[_safe_query_model()],
        query_records=[
            {"round_id": "R1", "selected": True, "selection_lane": "active"},
            {
                "round_id": "R1",
                "selected": True,
                "selection_lane": "random_control",
                "sampling_stratum": "E1|urban",
                "sampling_stratum_population": 4,
                "sampling_stratum_quota": 1,
                "inclusion_probability": 0.25,
            },
        ],
        annotations=[_annotation()],
        binary_training_rows=[{"region_id": "TRAIN-1", "label_code": 1, "binary_target": 1}],
    )

    assert report.ready is True
    assert report.blocking_failures == ()
    report.raise_for_failures()


def test_source_qa_fails_closed_on_missing_rights_and_reversed_time() -> None:
    assets = _valid_assets()
    assets[0]["processing_allowed"] = None
    assets[0]["acquisition_time"] = "2024-09-20T00:00:00Z"

    failures = [finding for finding in validate_source_assets(assets) if not finding.passed]

    assert {finding.check_id for finding in failures} >= {"rights_processing", "pre_before_post"}


def test_source_qa_accepts_canonical_registry_field_names() -> None:
    assets = [
        {
            "asset_id": "S1-PRE",
            "event_id": "E1",
            "event_relative_role": "pre_event",
            "product_id": "P-PRE",
            "acquisition_time_utc": "2024-09-01T00:00:00Z",
            "processing_allowed": True,
            "ml_label_derivation_allowed": True,
        },
        {
            "asset_id": "S1-EVENT",
            "event_id": "E1",
            "event_relative_role": "event_time",
            "product_id": "P-EVENT",
            "acquisition_time_utc": "2024-09-15T00:00:00Z",
            "processing_allowed": True,
            "ml_label_derivation_allowed": True,
        },
    ]

    assert not [finding for finding in validate_source_assets(assets) if not finding.passed]


def test_split_leakage_and_test_usage_are_blocking() -> None:
    assignments = _assignments() + [
        {"region_id": "LEAK-1", "overlap_group": "G1", "dataset_role": "fixed_within_event_development"}
    ]

    role_findings = validate_dataset_roles(assignments)
    usage_findings = validate_test_set_isolation(
        _assignments(),
        [{"region_id": "TEST-1", "purpose": "threshold_selection"}],
    )

    assert any(f.check_id == "overlap_group_single_dataset_role" and not f.passed for f in role_findings)
    assert any(f.check_id == "untouched_test_isolation" and not f.passed for f in usage_findings)


@pytest.mark.parametrize("purpose", ["train", "training_v2", "unknown_future_use"])
def test_unknown_test_usage_purposes_fail_closed(purpose: str) -> None:
    findings = validate_test_set_isolation(
        _assignments(),
        [{"region_id": "TEST-1", "purpose": purpose}],
    )
    assert any(
        finding.check_id == "untouched_test_isolation" and not finding.passed
        for finding in findings
    )


def test_query_model_flags_and_excluded_binary_labels_fail() -> None:
    unsafe = _safe_query_model()
    unsafe["eligible_for_fpps"] = True

    model_failures = [f for f in validate_query_model_safety([unsafe]) if not f.passed]
    label_failures = [
        f
        for f in validate_binary_training_rows(
            [{"region_id": "R-3", "label_code": 3, "binary_target": 0}]
        )
        if not f.passed
    ]

    assert any(f.check_id == "query_model_eligible_for_fpps" for f in model_failures)
    assert any(f.check_id == "binary_training_label_eligible" for f in label_failures)


def test_missing_random_lane_blocks_round_and_report_raises() -> None:
    report = run_label_factory_qa(
        query_records=[
            {"round_id": "R1", "selected": True, "selection_lane": "active"}
        ]
    )

    assert report.ready is False
    with pytest.raises(LabelFactoryQAError, match="random_control_lane_present"):
        report.raise_for_failures()


def test_random_lane_requires_auditable_inclusion_probability() -> None:
    report = run_label_factory_qa(
        query_records=[
            {
                "round_id": "R1",
                "selected": True,
                "selection_lane": "random_control",
                "sampling_stratum": "E1|urban",
                "sampling_stratum_population": 4,
                "sampling_stratum_quota": 1,
                "inclusion_probability": 0.50,
            }
        ]
    )

    assert report.ready is False
    with pytest.raises(LabelFactoryQAError, match="random_control_sampling_design"):
        report.raise_for_failures()


def _valid_assets() -> list[dict[str, object]]:
    return [
        {"asset_id": "S1-PRE", "event_id": "E1", "asset_role": "pre_event", "product_id": "P-PRE", "acquisition_time": "2024-09-01T00:00:00Z", "processing_allowed": True, "label_derivation_allowed": True},
        {"asset_id": "S1-POST", "event_id": "E1", "asset_role": "post_event", "product_id": "P-POST", "acquisition_time": "2024-09-15T00:00:00Z", "processing_allowed": True, "label_derivation_allowed": True},
    ]


def _assignments() -> list[dict[str, str]]:
    return [
        {"region_id": "TRAIN-1", "overlap_group": "G1", "dataset_role": "training_and_query_pool"},
        {"region_id": "TEST-1", "overlap_group": "G2", "dataset_role": "untouched_geographic_test"},
    ]


def _safe_query_model() -> dict[str, object]:
    return {
        "model_id": "Q0-LR",
        "model_purpose": "query_ranking",
        "eligible_for_review_queue": True,
        "eligible_for_training_after_human_review": "conditional",
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }


def _annotation() -> AnnotationRecord:
    start = datetime(2024, 9, 16, tzinfo=timezone.utc)
    return AnnotationRecord(
        annotation_id="ANN-1", event_id="E1", tile_id="T1", query_region_id="TRAIN-1", reviewer_id="RV-A", reviewer_revision=1,
        primary_class=LabelClass.TEMPORARY_FLOOD, confidence="high", ambiguity_reason_codes=(), evidence_layers_used=("pre_vv", "post_vv"),
        review_complete=True, reviewed_extent="POLYGON EMPTY", geometry=None, review_started_at=start,
        review_finished_at=start + timedelta(minutes=1), protocol_version="v1", tool_version="qgis-v1",
        model_predictions_visible=False, other_reviewer_annotations_visible=False,
        created_at_utc=start + timedelta(minutes=2), locked_at_utc=start + timedelta(minutes=3),
    )
