from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    annotation_content_sha256,
    append_annotation_record,
)
from floodguard.label_factory.calibration import (
    ReviewerCalibrationReceipt,
    write_reviewer_calibration_receipt,
)
from floodguard.label_factory.event_registry import EventRecord
from floodguard.label_factory.manifests import build_grid_manifests
from floodguard.label_factory.readiness import (
    LabelFactoryReadinessError,
    build_grid_validation_receipt,
    build_label_factory_readiness,
    build_label_factory_readiness_summary,
    load_grid_validation_receipt,
    validate_grid_validation_receipt_against_evidence,
    write_grid_validation_receipt,
    write_label_factory_readiness_outputs,
)
from floodguard.label_factory.review_workflow import (
    LabelsetValidationReceipt,
    write_labelset_validation_receipt,
)
from label_factory_processing_fixtures import synthetic_processing_receipt
from test_label_factory_event_registry import event_row, valid_sources
from test_label_factory_manifests import assignment_row, source_records


def _manual() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_mask_status": "weak_reference_candidate",
                "feature_count": 1,
                "unqualified_ml_label_allowed": False,
                "processing_allowed": False,
                "inspected_at_utc": "2026-07-09T09:58:22Z",
            }
        ]
    )


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_pixel_count": 65536,
                "reference_positive_pixel_count": 12557,
                "source_timestamp": "2024-09-15T23:16:01Z",
            }
        ]
    )


def _metrics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "can_feed_decision_layer": True,
                "ml_area_error_ratio": 2.450472,
                "confidence_class": "low",
            }
        ]
    )


def test_readiness_preserves_human_and_geographic_blockers() -> None:
    readiness = build_label_factory_readiness(_manual(), _features(), _metrics())
    statuses = dict(zip(readiness["check_id"], readiness["status"], strict=True))

    assert statuses["weak_reference_seed_scope"] == "ready_for_seed_only"
    assert statuses["cleared_training_labels"] == "blocked"
    assert statuses["canonical_projected_grid"] == "blocked"
    assert statuses["reviewer_calibration_complete"] == "blocked"
    assert statuses["blind_double_review"] == "blocked"
    assert statuses["immutable_training_labelset"] == "blocked"
    assert statuses["query_model_safety_boundary"] == "legacy_gate_rejected"
    assert statuses["geographic_generalization"] == "blocked"


def test_readiness_accepts_only_fully_verified_phase_one_evidence(
    tmp_path: Path,
) -> None:
    events, sources, processing_receipt, tiles, queries = _grid_inputs(tmp_path)
    grid_hash = str(tiles.iloc[0]["grid_contract_sha256"])
    query = queries.iloc[0]
    a = _annotation(
        "ANN-A",
        "RV-A",
        "primary",
        grid_hash=grid_hash,
        tile_id=str(query["tile_id"]),
        query_id=str(query["query_region_id"]),
    )
    b = _annotation(
        "ANN-B",
        "RV-B",
        "secondary",
        grid_hash=grid_hash,
        tile_id=str(query["tile_id"]),
        query_id=str(query["query_region_id"]),
    )
    annotation_log = tmp_path / "annotations.jsonl"
    append_annotation_record(annotation_log, a)
    append_annotation_record(annotation_log, b)
    agreement_path = tmp_path / "agreement.json"
    agreement_path.write_text(
        json.dumps(_agreement_evidence(a, b, grid_hash=grid_hash)),
        encoding="utf-8",
    )
    release_path = _write_release_receipt(
        tmp_path / "release-validation.json",
        grid_hash=grid_hash,
        query_id=str(query["query_region_id"]),
    )
    calibration_path = _write_calibration_receipt(
        tmp_path / "reviewer-calibration.json"
    )

    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        event_manifest=events,
        source_asset_manifest=sources,
        processing_alignment_receipt=processing_receipt,
        canonical_tile_manifest=tiles,
        canonical_query_manifest=queries,
        annotation_log=annotation_log,
        agreement_evidence=agreement_path,
        reviewer_calibration_receipt=calibration_path,
        labelset_validation_receipt=release_path,
        allow_ungoverned_fixture=True,
    )
    statuses = dict(zip(readiness["check_id"], readiness["status"], strict=True))
    assert statuses["canonical_projected_grid"] == "ready"
    assert statuses["reviewer_calibration_complete"] == "ready"
    assert statuses["blind_double_review"] == "ready"
    assert statuses["cleared_training_labels"] == "ready"
    assert statuses["immutable_training_labelset"] == "ready"


def test_plausible_optional_rows_never_mark_phase_one_ready(tmp_path: Path) -> None:
    agreement = tmp_path / "agreement.json"
    agreement.write_text("{}", encoding="utf-8")
    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        canonical_tile_manifest=pd.DataFrame(
            [
                {
                    "tile_id": "T1",
                    "event_id": "E1",
                    "grid_contract_sha256": "a" * 64,
                    "feature_schema_version": "sar_change_v2",
                    "query_model_only": True,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                }
            ]
        ),
        agreement_evidence=agreement,
        annotation_manifest=pd.DataFrame(
            [
                {
                    "query_region_id": "Q1",
                    "reviewer_id": "A",
                    "review_stage": "primary",
                    "review_complete": True,
                    "locked_at_utc": "2024-09-16T00:00:00Z",
                    "model_predictions_visible": False,
                    "other_reviewer_annotations_visible": False,
                },
                {
                    "query_region_id": "Q1",
                    "reviewer_id": "B",
                    "review_stage": "secondary",
                    "review_complete": True,
                    "locked_at_utc": "2024-09-16T00:05:00Z",
                    "model_predictions_visible": False,
                    "other_reviewer_annotations_visible": False,
                },
            ]
        ),
        labelset_manifest=pd.DataFrame(
            [
                {
                    "manifest_sha256": "c" * 64,
                    "qa_ready": True,
                    "open_adjudication_count": 0,
                    "eligible_for_query_model_training": True,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                }
            ]
        ),
    )
    indexed = readiness.set_index("check_id")

    assert indexed.at["canonical_projected_grid", "status"] == "blocked"
    assert "partial_grid_evidence" in indexed.at["canonical_projected_grid", "observed"]
    assert indexed.at["blind_double_review", "status"] == "blocked"
    assert "not a verified hash chain" in indexed.at["blind_double_review", "observed"]
    assert indexed.at["immutable_training_labelset", "status"] == "blocked"
    assert "compact tabular release claims" in indexed.at[
        "immutable_training_labelset", "observed"
    ]


def test_grid_readiness_requires_governance_for_standalone_receipt_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    events, sources, processing_receipt, tiles, queries = _grid_inputs(tmp_path)
    receipt = build_grid_validation_receipt(
        events,
        sources,
        processing_receipt,
        tiles,
        queries,
        validated_at_utc=datetime(2024, 9, 21, tzinfo=timezone.utc),
        allow_ungoverned_fixture=True,
    )
    receipt_path = write_grid_validation_receipt(
        receipt, tmp_path / "grid-validation.json"
    )
    assert load_grid_validation_receipt(receipt_path) == receipt
    assert (
        validate_grid_validation_receipt_against_evidence(
            receipt_path,
            events,
            sources,
            processing_receipt,
            tiles,
            queries,
            allow_ungoverned_fixture=True,
        )
        == receipt
    )
    assert receipt["artifact_schema"] == "floodguard.grid_validation_receipt.v3"
    assert receipt["governance_binding_status"] == "synthetic_fixture_only"
    assert receipt["production_readiness_eligible"] is False

    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        grid_validation_receipt=receipt_path,
    ).set_index("check_id")
    assert readiness.at["canonical_projected_grid", "status"] == "blocked"
    assert "governance_package_required=true" in readiness.at[
        "canonical_projected_grid", "observed"
    ]

    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["tile_count"] += 1
    tampered_path = tmp_path / "grid-validation-tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(LabelFactoryReadinessError, match="self-hash mismatch"):
        load_grid_validation_receipt(tampered_path)

    semantically_unsafe = dict(receipt)
    semantically_unsafe["production_readiness_eligible"] = True
    unsigned = {
        key: value
        for key, value in semantically_unsafe.items()
        if key != "receipt_sha256"
    }
    semantically_unsafe["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    unsafe_path = tmp_path / "grid-validation-unsafe.json"
    unsafe_path.write_text(json.dumps(semantically_unsafe), encoding="utf-8")
    with pytest.raises(LabelFactoryReadinessError, match="Synthetic grid receipts"):
        load_grid_validation_receipt(unsafe_path)


def test_malformed_review_and_release_evidence_are_explicitly_validation_failed(
    tmp_path: Path,
) -> None:
    annotation_log = tmp_path / "annotations.jsonl"
    annotation_log.write_text("not-json\n", encoding="utf-8")
    agreement = tmp_path / "agreement.json"
    agreement.write_text("{}", encoding="utf-8")
    release = tmp_path / "release.json"
    release.write_text('{"qa_ready": true}', encoding="utf-8")

    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        annotation_log=annotation_log,
        agreement_evidence=agreement,
        labelset_validation_receipt=release,
    ).set_index("check_id")

    assert readiness.at["blind_double_review", "status"] == "blocked"
    assert "validation_failed=double_review" in readiness.at[
        "blind_double_review", "observed"
    ]
    assert readiness.at["immutable_training_labelset", "status"] == "blocked"
    assert "validation_failed=labelset_validation_receipt" in readiness.at[
        "immutable_training_labelset", "observed"
    ]


def test_calibration_readiness_rejects_tampered_receipt(tmp_path: Path) -> None:
    path = _write_calibration_receipt(tmp_path / "calibration.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["formal_review_not_before_utc"] = "2024-09-15T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")

    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        reviewer_calibration_receipt=path,
    ).set_index("check_id")
    assert readiness.at["reviewer_calibration_complete", "status"] == "blocked"
    assert "validation_failed=reviewer_calibration_receipt" in readiness.at[
        "reviewer_calibration_complete", "observed"
    ]


def test_agreement_evidence_must_match_exact_annotation_hashes_and_query_coverage(
    tmp_path: Path,
) -> None:
    _events, _sources, _processing_receipt, tiles, queries = _grid_inputs(tmp_path)
    grid_hash = str(tiles.iloc[0]["grid_contract_sha256"])
    query = queries.iloc[0]
    a = _annotation(
        "ANN-A",
        "RV-A",
        "primary",
        grid_hash=grid_hash,
        tile_id=str(query["tile_id"]),
        query_id=str(query["query_region_id"]),
    )
    b = _annotation(
        "ANN-B",
        "RV-B",
        "secondary",
        grid_hash=grid_hash,
        tile_id=str(query["tile_id"]),
        query_id=str(query["query_region_id"]),
    )
    log = tmp_path / "annotations.jsonl"
    append_annotation_record(log, a)
    append_annotation_record(log, b)
    evidence = _agreement_evidence(a, b, grid_hash=grid_hash)
    evidence["annotation_sha256_by_id"]["ANN-A"] = "0" * 64
    agreement = tmp_path / "agreement.json"
    agreement.write_text(json.dumps(evidence), encoding="utf-8")

    readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        annotation_log=log,
        agreement_evidence=agreement,
    ).set_index("check_id")
    assert readiness.at["blind_double_review", "status"] == "blocked"
    assert "validation_failed=double_review" in readiness.at[
        "blind_double_review", "observed"
    ]
    assert "exact latest reviews" in readiness.at[
        "blind_double_review", "observed"
    ]

    wrong_coverage = _agreement_evidence(a, b, grid_hash=grid_hash)
    wrong_coverage["query_region_ids"] = ["UNKNOWN-QUERY"]
    coverage_path = tmp_path / "agreement-wrong-coverage.json"
    coverage_path.write_text(json.dumps(wrong_coverage), encoding="utf-8")
    coverage_readiness = build_label_factory_readiness(
        _manual(),
        _features(),
        _metrics(),
        annotation_log=log,
        agreement_evidence=coverage_path,
    ).set_index("check_id")
    assert coverage_readiness.at["blind_double_review", "status"] == "blocked"
    assert "query_region_ids do not exactly match reviewer pairs" in coverage_readiness.at[
        "blind_double_review", "observed"
    ]


def test_hardened_legacy_flag_does_not_pretend_query_committee_exists() -> None:
    metrics = _metrics()
    metrics.loc[0, "can_feed_decision_layer"] = False

    readiness = build_label_factory_readiness(_manual(), _features(), metrics)
    safety = readiness[
        readiness["check_id"].eq("query_model_safety_boundary")
    ].iloc[0]

    assert safety["status"] == "blocked"
    assert "no query committee" in safety["blocker"].lower()


def test_write_readiness_outputs_are_honest(tmp_path: Path) -> None:
    written = write_label_factory_readiness_outputs(
        _manual(),
        _features(),
        _metrics(),
        csv_output_path=tmp_path / "readiness.csv",
        summary_output_path=tmp_path / "readiness.md",
    )

    assert written["readiness"].exists()
    summary = written["summary"].read_text(encoding="utf-8")
    assert "not training- or decision-ready" in summary
    assert "ineligible for FPPS" in summary


def test_summary_lists_each_check() -> None:
    readiness = build_label_factory_readiness(_manual(), _features(), _metrics())
    summary = build_label_factory_readiness_summary(readiness)

    assert "weak_reference_seed_scope" in summary
    assert "query_model_safety_boundary" in summary


def _grid_inputs(
    tmp_path: Path,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, object],
    pd.DataFrame,
    pd.DataFrame,
]:
    events = pd.DataFrame([event_row()])
    sources = pd.DataFrame(valid_sources())
    event_records = [EventRecord.from_mapping(event_row())]
    source_record_values = source_records()
    processing_receipt = synthetic_processing_receipt(
        tmp_path / "processing",
        event_records,
        source_record_values,
    )
    canonical = build_grid_manifests(
        event_records,
        [assignment_row()],
        source_record_values,
        processing_receipt,
        allow_ungoverned_fixture=True,
    )
    return (
        events,
        sources,
        processing_receipt,
        canonical.tiles,
        canonical.query_regions,
    )


def _annotation(
    annotation_id: str,
    reviewer_id: str,
    review_stage: str,
    *,
    grid_hash: str,
    tile_id: str,
    query_id: str,
) -> AnnotationRecord:
    started = datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
    reviewer_token = "a" if reviewer_id == "RV-A" else "b"
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id="TH-MAESAI-2024-09",
        tile_id=tile_id,
        query_region_id=query_id,
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=LabelClass.TEMPORARY_FLOOD,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv", "dem_hillshade"),
        review_complete=True,
        reviewed_extent="POLYGON ((0 0, 2 0, 2 2, 0 0))",
        geometry="POLYGON ((0 0, 1 0, 1 1, 0 0))",
        review_started_at=started,
        review_finished_at=started + timedelta(minutes=10),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=started + timedelta(minutes=11),
        locked_at_utc=started + timedelta(minutes=12),
        review_stage=review_stage,
        source_timestamp=datetime(2024, 9, 16, tzinfo=timezone.utc),
        assumptions="Synthetic readiness evidence fixture only.",
        bundle_manifest_sha256=reviewer_token * 64,
        context_manifest_sha256=("c" if reviewer_id == "RV-A" else "d") * 64,
        grid_contract_sha256=grid_hash,
        source_registry_sha256="f" * 64,
    )


def _agreement_evidence(
    a: AnnotationRecord,
    b: AnnotationRecord,
    *,
    grid_hash: str,
) -> dict[str, object]:
    annotation_hashes = {
        a.annotation_id: annotation_content_sha256(a),
        b.annotation_id: annotation_content_sha256(b),
    }
    cell_hashes = {a.annotation_id: "1" * 64, b.annotation_id: "2" * 64}
    return {
        "artifact_schema": "floodguard.reviewer_agreement.v1",
        "reviewer_a_id": a.reviewer_id,
        "reviewer_b_id": b.reviewer_id,
        "measurement_unit": "canonical_cell_labels",
        "grid_contract_sha256": grid_hash,
        "query_region_ids": [a.query_region_id],
        "annotation_sha256_by_id": annotation_hashes,
        "reviewer_cell_artifact_sha256_by_annotation_id": cell_hashes,
        "review_import_provenance_by_annotation_id": {
            record.annotation_id: {
                "bundle_manifest_sha256": record.bundle_manifest_sha256,
                "context_manifest_sha256": record.context_manifest_sha256,
                "grid_contract_sha256": record.grid_contract_sha256,
                "source_registry_sha256": record.source_registry_sha256,
            }
            for record in (a, b)
        },
        "query_count": 1,
        "total_cell_count": 4,
        "boundary_metric_query_count": 1,
        "aggregate": {
            "per_class": {"1": {"dice_f1": 0.90, "iou": 0.82}},
            "cohen_kappa": 0.88,
        },
        "per_query": [
            {
                "event_id": a.event_id,
                "tile_id": a.tile_id,
                "query_region_id": a.query_region_id,
                "reviewer_a_annotation_id": a.annotation_id,
                "reviewer_b_annotation_id": b.annotation_id,
                "reviewer_a_annotation_sha256": annotation_hashes[a.annotation_id],
                "reviewer_b_annotation_sha256": annotation_hashes[b.annotation_id],
                "reviewer_a_cell_artifact_sha256": cell_hashes[a.annotation_id],
                "reviewer_b_cell_artifact_sha256": cell_hashes[b.annotation_id],
                "cell_count": 4,
                "agreement": {"boundary": {"f1": 0.90}},
            }
        ],
        "critical_strata": {"urban": 0.80},
    }


def _write_release_receipt(
    path: Path,
    *,
    grid_hash: str,
    query_id: str,
) -> Path:
    values = {
        "labelset_id": "mae_sai_labels_v0.1.0",
        "labelset_manifest_sha256": "a" * 64,
        "validated_at_utc": datetime(2024, 9, 17, tzinfo=timezone.utc),
        "qa_report_sha256": "b" * 64,
        "qa_evidence_manifest_sha256": "c" * 64,
        "reviewer_calibration_receipt_sha256": "1" * 64,
        "agreement_evidence_sha256": "d" * 64,
        "raster_lineage_sha256": "e" * 64,
        "raster_sha256_by_name": (("labels.csv", "f" * 64),),
        "grid_contract_sha256": grid_hash,
        "query_region_ids": (query_id,),
        "qa_ready": True,
        "open_adjudication_count": 0,
    }
    provisional = LabelsetValidationReceipt(**values, receipt_sha256="")
    digest = _json_sha256(provisional.to_dict(include_self_hash=False))
    receipt = replace(provisional, receipt_sha256=digest)
    return write_labelset_validation_receipt(receipt, path)


def _write_calibration_receipt(path: Path) -> Path:
    query_ids = tuple(f"CAL-Q{index:02d}" for index in range(1, 9))
    annotation_ids_by_reviewer = tuple(
        (
            reviewer_id,
            tuple(f"CAL-ANN-{reviewer_id}-{query_id}" for query_id in query_ids),
        )
        for reviewer_id in ("RV-A", "RV-B")
    )
    annotation_ids = [
        annotation_id
        for _reviewer_id, reviewer_annotations in annotation_ids_by_reviewer
        for annotation_id in reviewer_annotations
    ]
    per_query = [
        {
            "query_region_id": query_id,
            "comparable_cell_count": 4,
            "temporary_flood_dice": 1.0,
            "temporary_flood_iou": 1.0,
            "cohen_kappa": 1.0,
            "boundary_f1": 1.0,
        }
        for query_id in query_ids
    ]
    metrics = {
        "temporary_flood_dice": 1.0,
        "temporary_flood_iou": 1.0,
        "cohen_kappa": 1.0,
        "mean_boundary_f1": 1.0,
        "critical_strata_dice": {"urban": 1.0},
        "query_count": 8,
        "comparable_cell_count": 32,
        "ignored_cell_count": 0,
        "per_query": per_query,
    }
    values = {
        "reviewer_ids": ("RV-A", "RV-B"),
        "protocol_version": "protocol_v1",
        "taxonomy_version": "flood_label_v1",
        "calibration_completed_at_utc": datetime(
            2024, 9, 16, 0, 0, tzinfo=timezone.utc
        ),
        "formal_review_not_before_utc": datetime(
            2024, 9, 16, 0, 30, tzinfo=timezone.utc
        ),
        "query_manifest_sha256": "0" * 64,
        "query_region_ids": query_ids,
        "annotation_sha256_by_id": tuple(
            (annotation_id, hashlib.sha256(annotation_id.encode()).hexdigest())
            for annotation_id in annotation_ids
        ),
        "annotation_ids_by_reviewer": annotation_ids_by_reviewer,
        "reviewer_cell_sha256_by_reviewer": (
            ("RV-A", "1" * 64),
            ("RV-B", "2" * 64),
        ),
        "reviewer_cell_manifest_sha256_by_reviewer": (
            ("RV-A", "3" * 64),
            ("RV-B", "4" * 64),
        ),
        "calibration_reference_manifest_sha256": "5" * 64,
        "calibration_reference_cells_sha256": "6" * 64,
        "grid_contract_sha256_by_query": tuple(
            (query_id, "7" * 64) for query_id in query_ids
        ),
        "source_registry_sha256_by_query": tuple(
            (query_id, "8" * 64) for query_id in query_ids
        ),
        "source_timestamp_by_query": tuple(
            (query_id, "2024-09-15T23:00:00Z") for query_id in query_ids
        ),
        "metrics_by_reviewer": (("RV-A", metrics), ("RV-B", metrics)),
        "thresholds": (
            ("cohen_kappa", 0.75),
            ("critical_stratum_dice", 0.65),
            ("mean_boundary_f1", 0.70),
            ("temporary_flood_dice", 0.75),
        ),
        "query_strata_sha256": "9" * 64,
        "assumptions": "Synthetic passing calibration receipt for readiness tests.",
    }
    provisional = ReviewerCalibrationReceipt(**values, receipt_sha256="")
    receipt = replace(
        provisional,
        receipt_sha256=_json_sha256(provisional.to_dict(include_self_hash=False)),
    )
    return write_reviewer_calibration_receipt(receipt, path)


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
