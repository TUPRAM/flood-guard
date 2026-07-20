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
    ReviewerConfidence,
    annotation_content_sha256,
)
from floodguard.label_factory.calibration import (
    ReviewerCalibrationError,
    build_reviewer_calibration_failure_diagnostic,
    build_reviewer_calibration_receipt,
    load_reviewer_calibration_receipt,
    require_formal_review_calibration,
    verify_reviewer_calibration_failure_diagnostic,
    write_calibration_reference_artifacts,
    write_reviewer_calibration_failure_diagnostic,
    write_reviewer_calibration_receipt,
)


UTC = timezone.utc
SOURCE_TIME = datetime(2024, 9, 15, 23, 0, tzinfo=UTC)
LOCK_TIME = datetime(2024, 9, 16, 2, 0, tzinfo=UTC)
GRID_SHA = "a" * 64
SOURCE_SHA = "b" * 64
PROTOCOL = "label_factory_protocol_v1"


def test_build_write_load_calibration_receipt_from_real_artifacts(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt = _build(fixture)

    assert receipt.reviewer_ids == ("RV-A", "RV-B")
    assert len(receipt.query_region_ids) == 8
    assert dict(receipt.metrics_by_reviewer)["RV-A"]["temporary_flood_dice"] == 1.0
    assert receipt.formal_review_not_before_utc >= receipt.calibration_completed_at_utc
    assert receipt.to_dict()["eligible_for_query_model_training"] is False

    path = tmp_path / "calibration-receipt.json"
    write_reviewer_calibration_receipt(receipt, path)
    assert load_reviewer_calibration_receipt(path) == receipt
    with pytest.raises(FileExistsError):
        write_reviewer_calibration_receipt(receipt, path)


def test_receipt_tamper_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt = _build(fixture)
    path = tmp_path / "receipt.json"
    write_reviewer_calibration_receipt(receipt, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metrics_by_reviewer"]["RV-A"]["cohen_kappa"] = 0.99
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReviewerCalibrationError, match="self-hash"):
        load_reviewer_calibration_receipt(path)


def test_receipt_duplicate_safety_key_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt = _build(fixture)
    path = tmp_path / "duplicate-receipt.json"
    write_reviewer_calibration_receipt(receipt, path)
    raw = path.read_text(encoding="utf-8")
    path.write_text(
        raw.replace("{\n", '{\n  "eligible_for_warning": true,\n', 1),
        encoding="utf-8",
    )

    with pytest.raises(
        ReviewerCalibrationError,
        match="duplicate JSON key: eligible_for_warning",
    ):
        load_reviewer_calibration_receipt(path)


def test_reference_cell_tamper_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    reference_path = fixture["reference_cells"]
    reference = pd.read_csv(reference_path)
    reference.loc[0, "label_code"] = 1
    reference.to_csv(reference_path, index=False, lineterminator="\n")

    with pytest.raises(ReviewerCalibrationError, match="failed checksum"):
        _build(fixture)


def test_calibration_requires_at_least_eight_unique_queries(tmp_path: Path) -> None:
    query = _query_manifest(7)
    with pytest.raises(ReviewerCalibrationError, match="at least 8"):
        write_calibration_reference_artifacts(
            _reference_input(query),
            query,
            reference_id="CAL-REF-1",
            authority_type="expert_consensus",
            authority_id="EXPERT-PANEL-1",
            protocol_version=PROTOCOL,
            created_at_utc=LOCK_TIME,
            assumptions="Synthetic calibration fixture.",
            cells_output_path=tmp_path / "ref.csv",
            manifest_output_path=tmp_path / "ref.json",
        )


def test_low_scoring_reviewer_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, bad_reviewer="RV-B")

    with pytest.raises(ReviewerCalibrationError, match="failed calibration thresholds"):
        _build(fixture)


def test_failed_reviewer_gets_confidential_nonpass_diagnostic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, bad_reviewer="RV-B")
    diagnostic = _build_failure_diagnostic(fixture)

    assert diagnostic.failed_reviewer_ids == ("RV-B",)
    assert dict(diagnostic.failure_reasons_by_reviewer)["RV-A"] == ()
    assert dict(diagnostic.failure_reasons_by_reviewer)["RV-B"]
    payload = diagnostic.to_dict()
    assert payload["artifact_schema"].endswith("failure_diagnostic.v1")
    assert payload["calibration_passed"] is False
    assert payload["formal_review_authorized"] is False
    assert payload["confidential"] is True
    assert payload["eligible_for_query_model_training"] is False
    assert "formal_review_not_before_utc" not in payload

    path = tmp_path / "confidential-failure-diagnostic.json"
    write_reviewer_calibration_failure_diagnostic(diagnostic, path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["diagnostic_sha256"] == diagnostic.diagnostic_sha256
    with pytest.raises(FileExistsError):
        write_reviewer_calibration_failure_diagnostic(diagnostic, path)


def test_failure_diagnostic_cannot_replace_a_pass_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    with pytest.raises(ReviewerCalibrationError, match="All reviewers passed"):
        _build_failure_diagnostic(fixture)


def test_failure_diagnostic_tamper_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, bad_reviewer="RV-B")
    diagnostic = _build_failure_diagnostic(fixture)
    tampered = replace(diagnostic, failed_reviewer_ids=("RV-A",))

    with pytest.raises(ReviewerCalibrationError, match="status"):
        verify_reviewer_calibration_failure_diagnostic(tampered)


def test_wrong_dataset_role_is_rejected(tmp_path: Path) -> None:
    query = _query_manifest()
    query.loc[0, "dataset_role"] = "training_and_query_pool"

    with pytest.raises(ReviewerCalibrationError, match="wrong dataset_role"):
        write_calibration_reference_artifacts(
            _reference_input(query),
            query,
            reference_id="CAL-REF-1",
            authority_type="expert_consensus",
            authority_id="EXPERT-PANEL-1",
            protocol_version=PROTOCOL,
            created_at_utc=LOCK_TIME,
            assumptions="Synthetic calibration fixture.",
            cells_output_path=tmp_path / "ref.csv",
            manifest_output_path=tmp_path / "ref.json",
        )


def test_wrong_reviewer_identity_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    cells_path = fixture["reviewer_cells"]["RV-B"]
    cells = pd.read_csv(cells_path)
    cells["reviewer_id"] = "RV-C"
    cells.to_csv(cells_path, index=False, lineterminator="\n")
    manifest_path = fixture["reviewer_manifests"]["RV-B"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cell_labels_sha256"] = _sha(cells_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ReviewerCalibrationError, match="another identity"):
        _build(fixture)


def test_protocol_and_taxonomy_are_exact(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    annotations = list(fixture["annotations"])
    annotations[0] = replace(annotations[0], protocol_version="other_protocol")
    fixture["annotations"] = annotations

    with pytest.raises(ReviewerCalibrationError, match="different protocol"):
        _build(fixture)

    fixture = _fixture(tmp_path / "taxonomy")
    with pytest.raises(ReviewerCalibrationError, match="taxonomy_version"):
        build_reviewer_calibration_receipt(
            fixture["annotations"],
            fixture["query_path"],
            reviewer_cell_paths=fixture["reviewer_cells"],
            reviewer_cell_manifest_paths=fixture["reviewer_manifests"],
            reference_cell_path=fixture["reference_cells"],
            reference_manifest_path=fixture["reference_manifest"],
            query_strata=fixture["strata_path"],
            protocol_version=PROTOCOL,
            taxonomy_version="flood_label_v2",
            formal_review_not_before_utc=LOCK_TIME + timedelta(hours=1),
            assumptions="Synthetic mismatch test.",
        )


def test_formal_review_must_start_after_matching_calibration(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt = _build(fixture)
    too_early = replace(
        fixture["annotations"][0],
        query_region_id="FORMAL-Q1",
        review_started_at=receipt.formal_review_not_before_utc - timedelta(seconds=1),
        review_finished_at=receipt.formal_review_not_before_utc,
        created_at_utc=receipt.formal_review_not_before_utc,
        locked_at_utc=receipt.formal_review_not_before_utc,
    )

    with pytest.raises(ReviewerCalibrationError, match="began before"):
        require_formal_review_calibration(
            receipt,
            annotation_records=[too_early],
            reviewer_ids=("RV-A", "RV-B"),
            semantics={"taxonomy": "flood_label_v1"},
        )

    with pytest.raises(ReviewerCalibrationError, match="identities"):
        require_formal_review_calibration(
            receipt,
            annotation_records=[fixture["annotations"][0]],
            reviewer_ids=("RV-A", "RV-C"),
            semantics={"taxonomy": "flood_label_v1"},
        )


def test_255_only_reviewer_query_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    cells_path = fixture["reviewer_cells"]["RV-A"]
    cells = pd.read_csv(cells_path)
    first_query = str(cells.iloc[0]["query_region_id"])
    cells.loc[cells["query_region_id"].eq(first_query), "label_code"] = 255
    cells.loc[cells["query_region_id"].eq(first_query), "label_class"] = "unreviewed"
    cells.to_csv(cells_path, index=False, lineterminator="\n")
    manifest_path = fixture["reviewer_manifests"]["RV-A"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cell_labels_sha256"] = _sha(cells_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ReviewerCalibrationError, match="255-only"):
        _build(fixture)


def _build(fixture: dict[str, object]):
    return build_reviewer_calibration_receipt(
        fixture["annotations"],
        fixture["query_path"],
        reviewer_cell_paths=fixture["reviewer_cells"],
        reviewer_cell_manifest_paths=fixture["reviewer_manifests"],
        reference_cell_path=fixture["reference_cells"],
        reference_manifest_path=fixture["reference_manifest"],
        query_strata=fixture["strata_path"],
        protocol_version=PROTOCOL,
        formal_review_not_before_utc=LOCK_TIME + timedelta(hours=1),
        assumptions="Synthetic calibration receipt fixture only.",
    )


def _build_failure_diagnostic(fixture: dict[str, object]):
    return build_reviewer_calibration_failure_diagnostic(
        fixture["annotations"],
        fixture["query_path"],
        reviewer_cell_paths=fixture["reviewer_cells"],
        reviewer_cell_manifest_paths=fixture["reviewer_manifests"],
        reference_cell_path=fixture["reference_cells"],
        reference_manifest_path=fixture["reference_manifest"],
        query_strata=fixture["strata_path"],
        protocol_version=PROTOCOL,
        diagnostic_created_at_utc=LOCK_TIME + timedelta(hours=1),
        assumptions="Synthetic confidential calibration failure diagnostic.",
    )


def _fixture(tmp_path: Path, *, bad_reviewer: str | None = None) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    query = _query_manifest()
    query_path = tmp_path / "calibration-queries.csv"
    query.to_csv(query_path, index=False, lineterminator="\n")
    reference_outputs = write_calibration_reference_artifacts(
        _reference_input(query),
        query_path,
        reference_id="CAL-REF-1",
        authority_type="expert_consensus",
        authority_id="EXPERT-PANEL-1",
        protocol_version=PROTOCOL,
        created_at_utc=LOCK_TIME,
        assumptions="Synthetic expert reference fixture only.",
        cells_output_path=tmp_path / "reference-cells.csv",
        manifest_output_path=tmp_path / "reference-manifest.json",
    )
    annotations: list[AnnotationRecord] = []
    reviewer_cells: dict[str, Path] = {}
    reviewer_manifests: dict[str, Path] = {}
    reference = pd.read_csv(reference_outputs.cells)
    for reviewer_id in ("RV-A", "RV-B"):
        reviewer_annotations = [
            _annotation(reviewer_id, row) for row in query.to_dict("records")
        ]
        annotations.extend(reviewer_annotations)
        cells = _reviewer_cells(
            reviewer_id,
            reviewer_annotations,
            reference,
            bad=reviewer_id == bad_reviewer,
        )
        cell_path = tmp_path / f"{reviewer_id}-cells.csv"
        manifest_path = tmp_path / f"{reviewer_id}-cells.json"
        cells.to_csv(cell_path, index=False, lineterminator="\n")
        manifest = {
            "artifact_schema": "floodguard.annotation_cell_raster.v1",
            "annotation_ids": sorted(
                annotation.annotation_id for annotation in reviewer_annotations
            ),
            "source_annotation_content_sha256": {
                annotation.annotation_id: annotation_content_sha256(annotation)
                for annotation in reviewer_annotations
            },
            "grid_contract_sha256_by_query": {
                str(row["query_region_id"]): GRID_SHA
                for row in query.to_dict("records")
            },
            "source_registry_sha256_by_query": {
                str(row["query_region_id"]): SOURCE_SHA
                for row in query.to_dict("records")
            },
            "query_manifest_rows_sha256": "c" * 64,
            "geometry_parts_rows_sha256": "d" * 64,
            "cell_labels_file": cell_path.name,
            "cell_labels_sha256": _sha(cell_path),
            "cell_count": len(cells),
            "eligible_for_agreement": True,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "assumptions": "Synthetic reviewer cell fixture only.",
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        reviewer_cells[reviewer_id] = cell_path
        reviewer_manifests[reviewer_id] = manifest_path
    strata = pd.DataFrame(
        [
            {
                "query_region_id": f"CAL-Q{index:02d}",
                "stratum": "urban" if index <= 4 else "steep_terrain",
            }
            for index in range(1, 9)
        ]
    )
    strata_path = tmp_path / "calibration-strata.csv"
    strata.to_csv(strata_path, index=False, lineterminator="\n")
    return {
        "annotations": annotations,
        "query_path": query_path,
        "reviewer_cells": reviewer_cells,
        "reviewer_manifests": reviewer_manifests,
        "reference_cells": reference_outputs.cells,
        "reference_manifest": reference_outputs.manifest,
        "strata_path": strata_path,
    }


def _query_manifest(count: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(1, count + 1):
        rows.append(
            {
                "query_region_id": f"CAL-Q{index:02d}",
                "event_id": "TH-CAL-2024-09",
                "tile_id": f"CAL-TILE-{index:02d}",
                "query_size_pixels": 2,
                "resolution_m": 10.0,
                "crs": "EPSG:32647",
                "grid_id": "CAL-GRID-1",
                "grid_contract_sha256": GRID_SHA,
                "source_registry_sha256": SOURCE_SHA,
                "dataset_role": "reviewer_calibration",
                "eligible_for_human_annotation": True,
                "eligible_for_active_selection": False,
                "eligible_for_query_model_training": False,
                "eligible_for_training_after_human_review": "no",
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": SOURCE_TIME.isoformat().replace("+00:00", "Z"),
                "assumptions": "Synthetic fixed calibration query only.",
            }
        )
    return pd.DataFrame(rows)


def _reference_input(query: pd.DataFrame) -> pd.DataFrame:
    rows = []
    labels = ((0, 1), (0, 1))
    for item in query.to_dict("records"):
        query_id = str(item["query_region_id"])
        for row_index in range(2):
            for column_index in range(2):
                rows.append(
                    {
                        "event_id": item["event_id"],
                        "tile_id": item["tile_id"],
                        "query_region_id": query_id,
                        "cell_id": f"{query_id}_R{row_index:04d}_C{column_index:04d}",
                        "row_index": row_index,
                        "column_index": column_index,
                        "label_code": labels[row_index][column_index],
                    }
                )
    return pd.DataFrame(rows)


def _annotation(reviewer_id: str, query: dict[str, object]) -> AnnotationRecord:
    query_id = str(query["query_region_id"])
    return AnnotationRecord(
        annotation_id=f"ANN-{reviewer_id}-{query_id}",
        event_id=str(query["event_id"]),
        tile_id=str(query["tile_id"]),
        query_region_id=query_id,
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=LabelClass.TEMPORARY_FLOOD,
        confidence=ReviewerConfidence.HIGH,
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv", "dem_hillshade"),
        review_complete=True,
        reviewed_extent="entire_query_core",
        geometry="POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
        review_started_at=LOCK_TIME - timedelta(minutes=20),
        review_finished_at=LOCK_TIME - timedelta(minutes=10),
        protocol_version=PROTOCOL,
        tool_version="qgis_manual_review_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=LOCK_TIME - timedelta(minutes=5),
        locked_at_utc=LOCK_TIME,
        source_timestamp=SOURCE_TIME,
        assumptions="Synthetic locked calibration review only.",
        bundle_manifest_sha256=("c" if reviewer_id == "RV-A" else "d") * 64,
        context_manifest_sha256=("e" if reviewer_id == "RV-A" else "f") * 64,
        grid_contract_sha256=GRID_SHA,
        source_registry_sha256=SOURCE_SHA,
    )


def _reviewer_cells(
    reviewer_id: str,
    annotations: list[AnnotationRecord],
    reference: pd.DataFrame,
    *,
    bad: bool,
) -> pd.DataFrame:
    annotation_by_query = {
        annotation.query_region_id: annotation.annotation_id
        for annotation in annotations
    }
    rows = []
    for index, item in enumerate(reference.to_dict("records")):
        label_code = int(item["label_code"])
        if bad:
            label_code = 0 if label_code == 1 else 1
        rows.append(
            {
                "annotation_id": annotation_by_query[str(item["query_region_id"])],
                "event_id": item["event_id"],
                "tile_id": item["tile_id"],
                "query_region_id": item["query_region_id"],
                "reviewer_id": reviewer_id,
                "review_stage": "primary",
                "cell_id": item["cell_id"],
                "row_index": item["row_index"],
                "column_index": item["column_index"],
                "label_code": label_code,
                "label_class": LabelClass(label_code).name.lower(),
                "cell_center_x": float(index),
                "cell_center_y": float(index),
                "crs": item["crs"],
                "grid_id": item["grid_id"],
                "grid_contract_sha256": item["grid_contract_sha256"],
                "source_registry_sha256": item["source_registry_sha256"],
                "eligible_for_agreement": True,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": item["source_timestamp"],
                "assumptions": "Synthetic reviewer cell fixture only.",
            }
        )
    return pd.DataFrame(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
