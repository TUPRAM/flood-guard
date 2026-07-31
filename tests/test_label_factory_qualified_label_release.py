from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.label_factory.qualified_label_release import (
    DOWNSTREAM_SAFETY_FIELDS,
    QualifiedLabelReleaseError,
    build_formal_review_authorization,
    build_qualified_label_release,
    build_review_pair_evidence_receipt,
    canonical_sha256,
    validate_qualified_label_release,
)
from floodguard.label_factory.qualified_reference_release import (
    SYNTHETIC_STATUS,
    build_qualified_reference_release,
)


BUNDLE_A_SHA = "a" * 64
BUNDLE_B_SHA = "b" * 64
EVIDENCE_SET_SHA = "c" * 64
AGREEMENT_SHA = "d" * 64
CONSENSUS_SHA = "e" * 64
ADJUDICATION_IMPORT_SHA = "f" * 64
ADJUDICATION_BUNDLE_SHA = "1" * 64
GRID_SHA = "2" * 64
SOURCE_REGISTRY_SHA = "3" * 64
CONTEXT_SHA = "4" * 64
CALIBRATION_QUERY_SHA = "5" * 64
CALIBRATION_REFERENCE_SHA = "6" * 64
LABEL_CONTENT_SHA = "7" * 64
QA_SHA = "9" * 64
RASTER_LINEAGE_SHA = "0" * 64


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = deepcopy(value)
    sealed.pop(field, None)
    sealed[field] = canonical_sha256(sealed)
    return sealed


def _calibration() -> dict[str, Any]:
    return _seal(
        {
            "artifact_schema": "floodguard.reviewer_calibration_receipt.v1",
            "reviewer_ids": ["FG-RV-A-001", "FG-RV-B-001"],
            "protocol_version": "label-factory-protocol-v1",
            "taxonomy_version": "flood-label-v1",
            "calibration_completed_at_utc": "2024-09-19T12:00:00Z",
            "formal_review_not_before_utc": "2024-09-20T00:00:00Z",
            "query_manifest_sha256": CALIBRATION_QUERY_SHA,
            "calibration_reference_manifest_sha256": CALIBRATION_REFERENCE_SHA,
            "query_region_ids": ["CAL-001"],
            "calibration_passed": True,
            "dataset_role": "reviewer_calibration",
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        },
        "receipt_sha256",
    )


def _appointment(
    category: str,
    role_id: str,
    person_id: str,
    *,
    review_lane: str,
) -> dict[str, Any]:
    return {
        "role_category": category,
        "role_id": role_id,
        "person_id": person_id,
        "review_lane": review_lane,
        "project_operator": False,
        "prior_prohibited_evidence_exposure": False,
        "appointment_status": "accepted_with_attributable_local_evidence",
        "qualification_evidence_id": f"QUAL-{role_id}",
    }


def _human_role_package(
    calibration: dict[str, Any],
) -> dict[str, Any]:
    return _seal(
        {
            "artifact_schema": "floodguard.human_role_package.v1",
            "event_id": "mae-sai-2024",
            "protocol_version": "label-factory-protocol-v1",
            "taxonomy_version": "flood-label-v1",
            "formal_review_authorized": True,
            "package_status": "formal_review_gate_open_independent_a_b",
            "genuinely_blinded_double_review": True,
            "reference_authority_adjudicator_dual_role_allowed": False,
            "appointments": [
                _appointment(
                    "reference_authority",
                    "FG-RA-001",
                    "HUMAN-RA",
                    review_lane="authority_role_not_blinded",
                ),
                _appointment(
                    "reviewer_a",
                    "FG-RV-A-001",
                    "HUMAN-A",
                    review_lane="independent_blinded",
                ),
                _appointment(
                    "reviewer_b",
                    "FG-RV-B-001",
                    "HUMAN-B",
                    review_lane="independent_blinded",
                ),
                _appointment(
                    "adjudicator_c",
                    "FG-ADJ-C-001",
                    "HUMAN-C",
                    review_lane="authority_role_not_blinded",
                ),
            ],
            "calibration_receipt": {"receipt_sha256": calibration["receipt_sha256"]},
            "formal_review_authorized_from_utc": "2024-09-20T00:00:00Z",
            "eligible_for_model_training": False,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        },
        "manifest_sha256",
    )


def _authorization_inputs(
    *,
    dataset_mode: str = "fixture_demo",
    authority_evidence_kind: str | None = None,
    release_purpose: str = "flood_model_training_labels",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    calibration = _calibration()
    package = _human_role_package(calibration)
    authorization = build_formal_review_authorization(
        authorization_id="AUTH-001",
        dataset_mode=dataset_mode,
        release_purpose=release_purpose,
        study_area_id="MAE-SAI-STUDY",
        human_role_package=package,
        reviewer_calibration_receipt=calibration,
        authority_evidence_kind=authority_evidence_kind
        or (
            "synthetic_fixture_only"
            if dataset_mode == "fixture_demo"
            else "production_attributable_evidence"
        ),
        created_at_utc="2024-09-20T00:00:00Z",
        expires_at_utc="2024-10-20T00:00:00Z",
        assumptions=["Synthetic tests exercise contracts, not evidence authority."],
    )
    return authorization, package, calibration


def _annotation(
    category: str,
    *,
    primary_class: int = 1,
    geometry: str | None = "POLYGON ((0 0, 1 0, 1 1, 0 0))",
    query_region_id: str = "QRY-001",
) -> dict[str, Any]:
    is_a = category == "reviewer_a"
    return {
        "annotation_id": "ANN-A-001" if is_a else "ANN-B-001",
        "event_id": "mae-sai-2024",
        "tile_id": "TILE-001",
        "query_region_id": query_region_id,
        "reviewer_id": "FG-RV-A-001" if is_a else "FG-RV-B-001",
        "reviewer_revision": 1,
        "primary_class": primary_class,
        "confidence": "high",
        "review_complete": True,
        "geometry": geometry,
        "reviewed_extent": "POLYGON ((0 0, 2 0, 2 2, 0 0))",
        "review_started_at": (
            "2024-09-21T00:00:00Z" if is_a else "2024-09-21T00:30:00Z"
        ),
        "review_finished_at": (
            "2024-09-21T01:00:00Z" if is_a else "2024-09-21T01:30:00Z"
        ),
        "protocol_version": "label-factory-protocol-v1",
        "model_predictions_visible": False,
        "other_reviewer_annotations_visible": False,
        "created_at_utc": ("2024-09-21T01:30:00Z" if is_a else "2024-09-21T02:00:00Z"),
        "locked_at_utc": ("2024-09-21T02:00:00Z" if is_a else "2024-09-21T03:00:00Z"),
        "review_stage": "primary" if is_a else "secondary",
        "bundle_manifest_sha256": BUNDLE_A_SHA if is_a else BUNDLE_B_SHA,
        "context_manifest_sha256": CONTEXT_SHA,
        "grid_contract_sha256": GRID_SHA,
        "source_registry_sha256": SOURCE_REGISTRY_SHA,
    }


def _adjudication(
    annotation_a: dict[str, Any],
    annotation_b: dict[str, Any],
    *,
    outcome: str = "accept_a",
) -> dict[str, Any]:
    final_class: int | None
    final_geometry: str | None
    if outcome == "accept_a":
        final_class = annotation_a["primary_class"]
        final_geometry = annotation_a["geometry"]
    elif outcome == "accept_b":
        final_class = annotation_b["primary_class"]
        final_geometry = annotation_b["geometry"]
    elif outcome == "uncertain":
        final_class, final_geometry = 3, None
    elif outcome == "unobservable":
        final_class, final_geometry = 4, None
    elif outcome == "reject":
        final_class, final_geometry = None, None
    else:
        final_class = 1
        final_geometry = "POLYGON ((0 0, 3 0, 3 3, 0 0))"
    queue = {
        "queue_id": "QUEUE-001",
        "event_id": annotation_a["event_id"],
        "tile_id": annotation_a["tile_id"],
        "query_region_id": annotation_a["query_region_id"],
        "reviewer_a_annotation_id": annotation_a["annotation_id"],
        "reviewer_b_annotation_id": annotation_b["annotation_id"],
        "reviewer_a_sha256": canonical_sha256(annotation_a),
        "reviewer_b_sha256": canonical_sha256(annotation_b),
        "reason_codes": ["class_disagreement"],
        "created_at_utc": "2024-09-21T05:00:00Z",
        "status": "open",
    }
    record = {
        "adjudication_id": "ADJ-001",
        "queue_id": queue["queue_id"],
        "event_id": queue["event_id"],
        "tile_id": queue["tile_id"],
        "query_region_id": queue["query_region_id"],
        "reviewer_a_annotation_id": queue["reviewer_a_annotation_id"],
        "reviewer_b_annotation_id": queue["reviewer_b_annotation_id"],
        "reviewer_a_sha256": queue["reviewer_a_sha256"],
        "reviewer_b_sha256": queue["reviewer_b_sha256"],
        "adjudicator_id": "FG-ADJ-C-001",
        "outcome": outcome,
        "final_primary_class": final_class,
        "final_geometry": final_geometry,
        "ambiguity_reason_codes": ["resolved-class-disagreement"],
        "resolution_reason_codes": ["resolved-class-disagreement"],
        "notes": "Synthetic adjudication.",
        "protocol_version": "label-factory-protocol-v1",
        "resolved_at_utc": "2024-09-21T06:00:00Z",
        "locked_at_utc": "2024-09-21T07:00:00Z",
    }
    return {
        "queue_item": queue,
        "record": record,
        "adjudication_bundle_sha256": ADJUDICATION_BUNDLE_SHA,
        "adjudication_import_receipt_sha256": ADJUDICATION_IMPORT_SHA,
        "consensus_receipt_sha256": CONSENSUS_SHA,
        "model_predictions_visible": False,
    }


def _pair_context(
    *,
    annotation_a: dict[str, Any] | None = None,
    annotation_b: dict[str, Any] | None = None,
    adjudication: dict[str, Any] | None = None,
    purpose: str = "flood_model_training_labels",
) -> dict[str, Any]:
    authorization, package, calibration = _authorization_inputs(release_purpose=purpose)
    annotation_a = annotation_a or _annotation("reviewer_a")
    annotation_b = annotation_b or _annotation("reviewer_b")
    pair = build_review_pair_evidence_receipt(
        pair_id="PAIR-001",
        formal_review_authorization=authorization,
        human_role_package=package,
        reviewer_calibration_receipt=calibration,
        reviewer_a_annotation=annotation_a,
        reviewer_b_annotation=annotation_b,
        reviewer_a_bundle_sha256=BUNDLE_A_SHA,
        reviewer_b_bundle_sha256=BUNDLE_B_SHA,
        reviewer_a_evidence_set_sha256=EVIDENCE_SET_SHA,
        reviewer_b_evidence_set_sha256=EVIDENCE_SET_SHA,
        agreement_evidence_sha256=AGREEMENT_SHA,
        consensus_receipt_sha256=CONSENSUS_SHA,
        reveal_at_utc="2024-09-21T04:00:00Z",
        adjudication=adjudication,
        assumptions=["Synthetic pair tests strict lineage and blinding."],
    )
    return {
        "authorization": authorization,
        "package": package,
        "calibration": calibration,
        "annotation_a": annotation_a,
        "annotation_b": annotation_b,
        "adjudication": adjudication,
        "pair": pair,
    }


def _labelset() -> dict[str, Any]:
    return _seal(
        {
            "artifact_schema": "floodguard.labelset_manifest.v1",
            "labelset_id": "LABELSET-001",
            "label_content_sha256": LABEL_CONTENT_SHA,
            "created_at_utc": "2024-09-21T07:30:00Z",
        },
        "manifest_sha256",
    )


def _labelset_validation(
    labelset: dict[str, Any],
    *,
    query_region_ids: list[str] | None = None,
) -> dict[str, Any]:
    return _seal(
        {
            "artifact_schema": "floodguard.labelset_validation_receipt.v1",
            "labelset_id": labelset["labelset_id"],
            "labelset_manifest_sha256": labelset["manifest_sha256"],
            "validated_at_utc": "2024-09-21T08:00:00Z",
            "reviewer_calibration_receipt_sha256": _calibration()["receipt_sha256"],
            "agreement_evidence_sha256": AGREEMENT_SHA,
            "raster_lineage_sha256": RASTER_LINEAGE_SHA,
            "query_region_ids": query_region_ids or ["QRY-001"],
            "qa_ready": True,
            "open_adjudication_count": 0,
            "eligible_for_query_model_training": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        },
        "receipt_sha256",
    )


@lru_cache(maxsize=1)
def _synthetic_reference_release(
    *,
    purpose: str = "flood_model_training_labels",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        raster_path = root / "synthetic_reference.tif"
        grid_path = root / "analysis_grid.json"
        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="uint8",
            crs="EPSG:6933",
            transform=from_origin(0.0, 20.0, 10.0, 10.0),
            nodata=255,
        ) as dataset:
            dataset.write(
                np.array([[0, 1], [1, 0]], dtype=np.uint8),
                1,
            )
        grid_path.write_text(
            json.dumps(
                {
                    "target_crs": "EPSG:6933",
                    "transform": [10.0, 0.0, 0.0, 0.0, -10.0, 20.0],
                    "width": 2,
                    "height": 2,
                }
            ),
            encoding="utf-8",
        )
        return build_qualified_reference_release(
            None,
            release_id="synthetic-reference-release-v1",
            study_area_id="MAE-SAI-STUDY",
            event_id="mae-sai-2024",
            experiment_id="synthetic-integration-v1",
            source_timestamp="2024-09-15T12:00:00Z",
            generated_at="2024-09-19T00:00:00Z",
            source_name="Project-owned synthetic binary fixture",
            assumptions=[
                "Synthetic fixture exercises compatibility plumbing only.",
                "It is not Thai-event evidence.",
            ],
            data_version="synthetic-v1",
            git_commit="6833c8b71fb18f5b8ea17d5d9f8e0745157643c2",
            purpose=purpose,
            release_status=SYNTHETIC_STATUS,
            reference_authority_class="synthetic_fixture",
            reference_product_id="synthetic-binary-mask-v1",
            reference_artifact_path=raster_path,
            analysis_grid_contract_path=grid_path,
            observation_start="2024-09-15T00:00:00Z",
            observation_end="2024-09-15T23:59:59Z",
        )


def _release_context(
    *,
    purpose: str = "flood_model_training_labels",
    class_counts: dict[int, int] | None = None,
) -> dict[str, Any]:
    pair_context = _pair_context(purpose=purpose)
    labelset = _labelset()
    validation = _labelset_validation(labelset)
    reference = deepcopy(_synthetic_reference_release(purpose=purpose))
    release = build_qualified_label_release(
        release_id="RELEASE-001",
        purpose=purpose,
        formal_review_authorization=pair_context["authorization"],
        human_role_package=pair_context["package"],
        reviewer_calibration_receipt=pair_context["calibration"],
        labelset_manifest=labelset,
        labelset_validation_receipt=validation,
        review_pair_receipts=[pair_context["pair"]],
        qualified_reference_release_receipt=reference,
        qa_receipt_sha256=QA_SHA,
        agreement_evidence_sha256=AGREEMENT_SHA,
        raster_lineage_sha256=RASTER_LINEAGE_SHA,
        consensus_receipt_sha256=CONSENSUS_SHA,
        adjudication_import_receipt_sha256=ADJUDICATION_IMPORT_SHA,
        class_counts=class_counts or {0: 20, 1: 10, 2: 3, 3: 2, 4: 1, 255: 4},
        created_at_utc="2024-09-22T00:00:00Z",
        assumptions=["Synthetic release validates bridge invariants only."],
    )
    return {
        **pair_context,
        "labelset": labelset,
        "validation": validation,
        "reference": reference,
        "release": release,
    }


def test_formal_authorization_binds_four_distinct_people_and_stays_nonoperational() -> (
    None
):
    authorization, _, _ = _authorization_inputs()

    assert {role["person_id"] for role in authorization["roles"].values()} == {
        "HUMAN-RA",
        "HUMAN-A",
        "HUMAN-B",
        "HUMAN-C",
    }
    assert authorization["reviewer_ids"] == ["FG-RV-A-001", "FG-RV-B-001"]
    assert authorization["synthetic_fixture_only"] is True
    assert authorization["processing_allowed"] is True
    assert all(authorization[field] is False for field in DOWNSTREAM_SAFETY_FIELDS)


@pytest.mark.parametrize(
    ("category", "field", "value"),
    [
        ("adjudicator_c", "person_id", "HUMAN-RA"),
        ("reviewer_a", "review_lane", "authority_role_not_blinded"),
        ("reviewer_a", "project_operator", True),
        ("reviewer_b", "prior_prohibited_evidence_exposure", True),
    ],
)
def test_formal_authorization_rejects_role_separation_or_blinding_breaches(
    category: str,
    field: str,
    value: Any,
) -> None:
    calibration = _calibration()
    package = _human_role_package(calibration)
    appointment = next(
        row for row in package["appointments"] if row["role_category"] == category
    )
    appointment[field] = value
    package = _seal(package, "manifest_sha256")

    with pytest.raises(QualifiedLabelReleaseError):
        build_formal_review_authorization(
            authorization_id="AUTH-FAIL",
            dataset_mode="fixture_demo",
            release_purpose="flood_model_training_labels",
            study_area_id="MAE-SAI-STUDY",
            human_role_package=package,
            reviewer_calibration_receipt=calibration,
            authority_evidence_kind="synthetic_fixture_only",
            created_at_utc="2024-09-20T00:00:00Z",
            expires_at_utc="2024-10-20T00:00:00Z",
            assumptions=["Expected fail-closed test."],
        )


def test_candidate_mode_rejects_caller_authored_role_and_calibration_mappings() -> None:
    calibration = _calibration()
    package = _human_role_package(calibration)
    package["synthetic_fixture_only"] = True
    package = _seal(package, "manifest_sha256")

    with pytest.raises(QualifiedLabelReleaseError, match="frozen human-role"):
        build_formal_review_authorization(
            authorization_id="AUTH-CANDIDATE",
            dataset_mode="candidate",
            release_purpose="flood_model_training_labels",
            study_area_id="MAE-SAI-STUDY",
            human_role_package=package,
            reviewer_calibration_receipt=calibration,
            authority_evidence_kind="production_attributable_evidence",
            created_at_utc="2024-09-20T00:00:00Z",
            expires_at_utc="2024-10-20T00:00:00Z",
            assumptions=["Expected fixture-authority rejection."],
        )


def test_candidate_authorization_requires_canonical_file_backed_inputs() -> None:
    with pytest.raises(QualifiedLabelReleaseError, match="frozen human-role"):
        _authorization_inputs(dataset_mode="candidate")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("calibration_passed", False),
        ("reviewer_ids", ["FG-RV-A-001", "SOMEONE-ELSE"]),
        ("protocol_version", "different-protocol"),
    ],
)
def test_formal_authorization_rejects_wrong_calibration(
    field: str,
    value: Any,
) -> None:
    calibration = _calibration()
    calibration[field] = value
    calibration = _seal(calibration, "receipt_sha256")
    package = _human_role_package(calibration)

    with pytest.raises(QualifiedLabelReleaseError):
        build_formal_review_authorization(
            authorization_id="AUTH-CAL-FAIL",
            dataset_mode="fixture_demo",
            release_purpose="flood_model_training_labels",
            study_area_id="MAE-SAI-STUDY",
            human_role_package=package,
            reviewer_calibration_receipt=calibration,
            authority_evidence_kind="synthetic_fixture_only",
            created_at_utc="2024-09-20T00:00:00Z",
            expires_at_utc="2024-10-20T00:00:00Z",
            assumptions=["Expected calibration rejection."],
        )


def test_direct_agreement_pair_records_identical_evidence_and_lock_order() -> None:
    context = _pair_context()
    pair = context["pair"]

    assert pair["pair_outcome"] == "paired_agreement_locked"
    assert pair["synthetic_fixture_only"] is True
    assert pair["adjudication"] is None
    assert pair["reviewer_evidence_set_sha256"] == {
        "reviewer_a": EVIDENCE_SET_SHA,
        "reviewer_b": EVIDENCE_SET_SHA,
    }
    assert pair["reveal_at_utc"] > max(pair["locked_at_by_reviewer"].values())
    assert all(pair[field] is False for field in DOWNSTREAM_SAFETY_FIELDS)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_visibility", "explicit field"),
        ("visible_predictions", "blinding breach"),
        ("visible_peer", "blinding breach"),
        ("review_before_authorization", "chronology"),
        ("reveal_before_lock", "revealed|reveal"),
        ("different_lineage", "common"),
        ("different_evidence", "different review evidence"),
    ],
)
def test_pair_builder_fails_closed_on_independence_and_lineage_breaches(
    mutation: str,
    match: str,
) -> None:
    authorization, package, calibration = _authorization_inputs()
    annotation_a = _annotation("reviewer_a")
    annotation_b = _annotation("reviewer_b")
    reveal = "2024-09-21T04:00:00Z"
    evidence_b = EVIDENCE_SET_SHA
    if mutation == "missing_visibility":
        annotation_a.pop("other_reviewer_annotations_visible")
    elif mutation == "visible_predictions":
        annotation_b["model_predictions_visible"] = True
    elif mutation == "visible_peer":
        annotation_a["other_reviewer_annotations_visible"] = True
    elif mutation == "review_before_authorization":
        annotation_a["review_started_at"] = "2024-09-19T00:00:00Z"
    elif mutation == "reveal_before_lock":
        reveal = "2024-09-21T02:30:00Z"
    elif mutation == "different_lineage":
        annotation_b["grid_contract_sha256"] = "f" * 64
    else:
        evidence_b = "f" * 64

    with pytest.raises(QualifiedLabelReleaseError, match=match):
        build_review_pair_evidence_receipt(
            pair_id="PAIR-FAIL",
            formal_review_authorization=authorization,
            human_role_package=package,
            reviewer_calibration_receipt=calibration,
            reviewer_a_annotation=annotation_a,
            reviewer_b_annotation=annotation_b,
            reviewer_a_bundle_sha256=BUNDLE_A_SHA,
            reviewer_b_bundle_sha256=BUNDLE_B_SHA,
            reviewer_a_evidence_set_sha256=EVIDENCE_SET_SHA,
            reviewer_b_evidence_set_sha256=evidence_b,
            agreement_evidence_sha256=AGREEMENT_SHA,
            consensus_receipt_sha256=CONSENSUS_SHA,
            reveal_at_utc=reveal,
            assumptions=["Expected strict pair rejection."],
        )


def test_disagreement_requires_and_hash_binds_separate_adjudicator() -> None:
    annotation_a = _annotation("reviewer_a", primary_class=1)
    annotation_b = _annotation("reviewer_b", primary_class=0)
    with pytest.raises(QualifiedLabelReleaseError, match="requires adjudication"):
        _pair_context(annotation_a=annotation_a, annotation_b=annotation_b)

    adjudication = _adjudication(annotation_a, annotation_b)
    context = _pair_context(
        annotation_a=annotation_a,
        annotation_b=annotation_b,
        adjudication=adjudication,
    )

    assert context["pair"]["pair_outcome"] == "adjudicated_locked"
    assert context["pair"]["adjudication"]["adjudicator_id"] == "FG-ADJ-C-001"
    assert context["pair"]["disagreement_reasons"] == ["class_disagreement"]


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_adjudicator",
        "model_visible",
        "wrong_source_hash",
        "queue_before_reveal",
        "wrong_final_class",
    ],
)
def test_adjudication_binding_rejects_substitution(
    mutation: str,
) -> None:
    annotation_a = _annotation("reviewer_a", primary_class=1)
    annotation_b = _annotation("reviewer_b", primary_class=0)
    adjudication = _adjudication(annotation_a, annotation_b)
    if mutation == "wrong_adjudicator":
        adjudication["record"]["adjudicator_id"] = "FG-RA-001"
    elif mutation == "model_visible":
        adjudication["model_predictions_visible"] = True
    elif mutation == "wrong_source_hash":
        adjudication["queue_item"]["reviewer_a_sha256"] = "f" * 64
        adjudication["record"]["reviewer_a_sha256"] = "f" * 64
    elif mutation == "queue_before_reveal":
        adjudication["queue_item"]["created_at_utc"] = "2024-09-21T02:00:00Z"
    else:
        adjudication["record"]["final_primary_class"] = 0

    with pytest.raises(QualifiedLabelReleaseError):
        _pair_context(
            annotation_a=annotation_a,
            annotation_b=annotation_b,
            adjudication=adjudication,
        )


def test_training_release_preserves_unknown_codes_and_denies_decision_use() -> None:
    context = _release_context()
    release = context["release"]

    assert release["binary_eligible_codes"] == [0, 1, 2]
    assert release["synthetic_fixture_only"] is True
    assert release["binary_excluded_codes"] == [3, 4, 255]
    assert release["binary_eligible_cell_count"] == 33
    assert release["binary_excluded_cell_count"] == 7
    assert release["unknown_cells_preserved"] is True
    assert release["eligible_for_flood_model_training"] is True
    assert release["eligible_for_model_evaluation"] is False
    assert (
        release["qualified_reference_receipt_sha256"]
        == context["reference"]["release_sha256"]
    )
    assert release["release_authority_status"] == ("not_applicable_synthetic_fixture")
    assert release["release_authority_receipt_sha256"] is None
    assert release["release_authority_signature_verified"] is False
    assert release["confers_release_authority"] is False
    assert all(release[field] is False for field in DOWNSTREAM_SAFETY_FIELDS)


def test_final_evaluation_release_is_not_training_eligible() -> None:
    release = _release_context(purpose="model_final_evaluation")["release"]

    assert release["eligible_for_flood_model_training"] is False
    assert release["eligible_for_query_model_training"] is False
    assert release["eligible_for_model_evaluation"] is True
    assert release["qualified_reference_purpose"] == "model_final_evaluation"


def test_training_label_release_rejects_final_evaluation_reference() -> None:
    context = _release_context()
    final_evaluation_reference = _synthetic_reference_release(
        purpose="model_final_evaluation"
    )

    with pytest.raises(
        QualifiedLabelReleaseError,
        match="receipt purpose differs from label-release purpose",
    ):
        validate_qualified_label_release(
            context["release"],
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=final_evaluation_reference,
        )


def test_final_evaluation_label_release_rejects_training_reference() -> None:
    context = _release_context(purpose="model_final_evaluation")
    training_reference = _synthetic_reference_release(
        purpose="flood_model_training_labels"
    )

    with pytest.raises(
        QualifiedLabelReleaseError,
        match="receipt purpose differs from label-release purpose",
    ):
        validate_qualified_label_release(
            context["release"],
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=training_reference,
        )


@pytest.mark.parametrize("mode", ["candidate", "official_input"])
def test_nonfixture_authorization_rejects_minimal_caller_mappings(
    mode: str,
) -> None:
    with pytest.raises(QualifiedLabelReleaseError, match="frozen human-role"):
        _authorization_inputs(dataset_mode=mode)


def test_actual_qualified_reference_receipt_self_hash_is_required() -> None:
    context = _release_context()
    reference = deepcopy(context["reference"])
    reference["release_id"] = "substituted-reference-release"

    with pytest.raises(
        QualifiedLabelReleaseError,
        match="canonical validator|self-hash",
    ):
        validate_qualified_label_release(
            context["release"],
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=reference,
        )


def test_resealed_reference_for_another_event_is_rejected() -> None:
    context = _release_context()
    reference = deepcopy(context["reference"])
    reference["event_id"] = "another-event"
    reference = _seal(reference, "release_sha256")

    with pytest.raises(QualifiedLabelReleaseError, match="event or study area"):
        validate_qualified_label_release(
            context["release"],
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=reference,
        )


def test_training_review_lineage_cannot_be_rewrapped_for_final_evaluation() -> None:
    context = _release_context()
    release = deepcopy(context["release"])
    release["purpose"] = "model_final_evaluation"
    release["qualified_reference_purpose"] = "model_final_evaluation"
    release["qualified_reference_authorized_purpose"] = "model_final_evaluation"
    release["eligible_for_query_model_training"] = False
    release["eligible_for_flood_model_training"] = False
    release["eligible_for_model_evaluation"] = True
    release = _seal(release, "release_sha256")

    with pytest.raises(QualifiedLabelReleaseError, match="pre-review"):
        validate_qualified_label_release(
            release,
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=context["reference"],
        )


def test_release_cannot_predate_labelset_validation_or_review_lock() -> None:
    context = _release_context()
    release = deepcopy(context["release"])
    release["created_at_utc"] = "2024-09-21T07:59:59Z"
    release = _seal(release, "release_sha256")

    with pytest.raises(QualifiedLabelReleaseError, match="predates review"):
        validate_qualified_label_release(
            release,
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=context["reference"],
        )


def test_private_absolute_path_is_rejected_recursively() -> None:
    calibration = _calibration()
    package = _human_role_package(calibration)

    with pytest.raises(QualifiedLabelReleaseError, match="private absolute path"):
        build_formal_review_authorization(
            authorization_id="AUTH-PRIVATE-PATH",
            dataset_mode="fixture_demo",
            release_purpose="flood_model_training_labels",
            study_area_id="MAE-SAI-STUDY",
            human_role_package=package,
            reviewer_calibration_receipt=calibration,
            authority_evidence_kind="synthetic_fixture_only",
            created_at_utc="2024-09-20T00:00:00Z",
            expires_at_utc="2024-10-20T00:00:00Z",
            assumptions=[
                r"Nested receipt was copied from C:\Users\reviewer\secret.json."
            ],
        )


@pytest.mark.parametrize(
    "counts",
    [
        {0: 20, 1: 0, 2: 3, 3: 2, 4: 1, 255: 4},
        {0: 0, 1: 10, 2: 0, 3: 2, 4: 1, 255: 4},
        {0: 20, 1: 10, 2: 3, 3: 2, 4: 1},
    ],
)
def test_training_release_rejects_missing_classes_or_unknown_code_contract(
    counts: dict[int, int],
) -> None:
    with pytest.raises(QualifiedLabelReleaseError):
        _release_context(class_counts=counts)


def test_release_rejects_incomplete_review_pair_coverage() -> None:
    context = _pair_context()
    labelset = _labelset()
    validation = _labelset_validation(labelset, query_region_ids=["QRY-001", "QRY-002"])

    with pytest.raises(QualifiedLabelReleaseError, match="exactly cover"):
        build_qualified_label_release(
            release_id="RELEASE-COVERAGE-FAIL",
            purpose="flood_model_training_labels",
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=labelset,
            labelset_validation_receipt=validation,
            review_pair_receipts=[context["pair"]],
            qualified_reference_release_receipt=_synthetic_reference_release(),
            qa_receipt_sha256=QA_SHA,
            agreement_evidence_sha256=AGREEMENT_SHA,
            raster_lineage_sha256=RASTER_LINEAGE_SHA,
            consensus_receipt_sha256=CONSENSUS_SHA,
            adjudication_import_receipt_sha256=ADJUDICATION_IMPORT_SHA,
            class_counts={0: 20, 1: 10, 2: 3, 3: 2, 4: 1, 255: 4},
            created_at_utc="2024-09-22T00:00:00Z",
            assumptions=["Expected coverage rejection."],
        )


@pytest.mark.parametrize(
    "mutation",
    ["decision_authority", "unknown_code_loss", "evidence_set_substitution"],
)
def test_validator_rejects_semantic_tampering_even_after_rehash(
    mutation: str,
) -> None:
    context = _release_context()
    release = deepcopy(context["release"])
    pairs = [deepcopy(context["pair"])]
    if mutation == "decision_authority":
        release["eligible_for_decision_layer"] = True
        release = _seal(release, "release_sha256")
    elif mutation == "unknown_code_loss":
        release["binary_excluded_codes"] = [3, 4]
        release = _seal(release, "release_sha256")
    else:
        pairs[0]["reviewer_evidence_set_sha256"]["reviewer_b"] = "f" * 64
        pairs[0] = _seal(pairs[0], "receipt_sha256")
        release["review_pair_receipt_sha256_by_query"]["QRY-001"] = pairs[0][
            "receipt_sha256"
        ]
        release = _seal(release, "release_sha256")

    with pytest.raises(QualifiedLabelReleaseError):
        validate_qualified_label_release(
            release,
            formal_review_authorization=context["authorization"],
            human_role_package=context["package"],
            reviewer_calibration_receipt=context["calibration"],
            labelset_manifest=context["labelset"],
            labelset_validation_receipt=context["validation"],
            review_pair_receipts=pairs,
            qualified_reference_release_receipt=context["reference"],
        )
