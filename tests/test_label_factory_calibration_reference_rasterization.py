from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.annotation_rasterization import (
    AnnotationRasterizationError,
    canonical_geometry_parts_payload,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    ReviewerConfidence,
)
from floodguard.label_factory.calibration import (
    write_calibration_reference_artifacts,
)
from floodguard.label_factory.calibration_reference_rasterization import (
    REFERENCE_INPUT_COLUMNS,
    build_calibration_reference_cell_input,
    verify_calibration_reference_input_manifest,
    write_calibration_reference_cell_input,
)


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("shapely") is None,
    reason="optional geo dependency is not installed",
)

UTC = timezone.utc
SOURCE_TIME = datetime(2024, 9, 15, 23, 16, 1, tzinfo=UTC)
LOCK_TIME = datetime(2024, 9, 16, 4, 0, tzinfo=UTC)
GRID_SHA = "a" * 64
SOURCE_SHA = "b" * 64
AUTHORITY_ID = "FG-RA-001"


def test_locked_authority_geometry_becomes_freeze_ready_reference_input(
    tmp_path: Path,
) -> None:
    queries = _queries()
    annotations, parts = _authority_geometry(queries)
    evidence = tmp_path / "authority-acceptance.pdf"
    evidence.write_bytes(b"Synthetic authority evidence fixture only.")

    outputs = write_calibration_reference_cell_input(
        annotations,
        queries,
        parts,
        authority_id=AUTHORITY_ID,
        authority_role_evidence=evidence,
        assumptions="Synthetic authority geometry raster fixture only.",
        cell_output_path=tmp_path / "reference-cells-input.csv",
        manifest_output_path=tmp_path / "reference-cells-input.manifest.json",
    )

    cells = pd.read_csv(outputs.cells)
    assert tuple(cells.columns) == REFERENCE_INPUT_COLUMNS
    assert len(cells) == 8 * 4
    assert set(cells["label_code"]) == {0, 1, 2, 3, 4, 255}
    assert cells.groupby("query_region_id").size().eq(4).all()
    manifest = verify_calibration_reference_input_manifest(outputs.manifest)
    assert manifest["authority_id"] == AUTHORITY_ID
    assert manifest["confidential"] is True
    assert manifest["calibration_reference_frozen"] is False
    assert manifest["eligible_for_query_model_training"] is False

    # This proves the generated table is the exact input contract accepted by
    # the existing immutable reference freezer.
    frozen = write_calibration_reference_artifacts(
        outputs.cells,
        queries,
        reference_id="CAL-REF-1",
        authority_type="adjudicated",
        authority_id=AUTHORITY_ID,
        protocol_version="label_factory_protocol_v1",
        created_at_utc=LOCK_TIME,
        assumptions=(
            "Synthetic fixture; source lineage is bound by the reference-input manifest."
        ),
        cells_output_path=tmp_path / "reference-cells-v1.csv",
        manifest_output_path=tmp_path / "reference-cells-v1.json",
    )
    assert frozen.cells.exists()
    assert frozen.manifest.exists()


def test_reference_rasterizer_rejects_cross_class_overlap() -> None:
    queries = _queries()
    annotations, parts = _authority_geometry(queries)
    first_id = annotations[0].annotation_id
    extra = pd.DataFrame(
        [
            {
                "annotation_id": first_id,
                "geometry_part_id": "OVERLAP-FLOOD",
                "class_code": 1,
                "geometry_wkt": "POLYGON ((0 10, 10 10, 10 20, 0 20, 0 10))",
                "fill_unpainted_with_primary_class": False,
            }
        ]
    )
    changed_parts = pd.concat([parts, extra], ignore_index=True)
    first_parts = changed_parts[
        changed_parts["annotation_id"].astype(str).eq(first_id)
    ]
    changed_annotations = list(annotations)
    changed_annotations[0] = replace(
        changed_annotations[0],
        geometry=canonical_geometry_parts_payload(first_parts),
    )

    with pytest.raises(AnnotationRasterizationError, match="overlap cell"):
        build_calibration_reference_cell_input(
            changed_annotations,
            queries,
            changed_parts,
            authority_id=AUTHORITY_ID,
        )


def test_reference_rasterizer_requires_exact_authority_lineage() -> None:
    queries = _queries()
    annotations, parts = _authority_geometry(queries)
    changed = list(annotations)
    changed[0] = replace(changed[0], grid_contract_sha256="c" * 64)

    with pytest.raises(AnnotationRasterizationError, match="wrong grid hash"):
        build_calibration_reference_cell_input(
            changed,
            queries,
            parts,
            authority_id=AUTHORITY_ID,
        )


def test_reference_input_tamper_is_detected(tmp_path: Path) -> None:
    queries = _queries()
    annotations, parts = _authority_geometry(queries)
    evidence = tmp_path / "authority-acceptance.eml"
    evidence.write_text("Synthetic evidence.", encoding="utf-8")
    outputs = write_calibration_reference_cell_input(
        annotations,
        queries,
        parts,
        authority_id=AUTHORITY_ID,
        authority_role_evidence=evidence,
        assumptions="Synthetic tamper fixture only.",
        cell_output_path=tmp_path / "cells.csv",
        manifest_output_path=tmp_path / "cells.json",
    )
    cells = pd.read_csv(outputs.cells)
    cells.loc[0, "label_code"] = 4
    cells.to_csv(outputs.cells, index=False, lineterminator="\n")

    with pytest.raises(AnnotationRasterizationError, match="checksum"):
        verify_calibration_reference_input_manifest(outputs.manifest)


def _queries() -> pd.DataFrame:
    rows = []
    for index in range(1, 9):
        rows.append(
            {
                "query_region_id": f"CAL-Q{index:02d}",
                "event_id": "TH-CAL-2024-09",
                "tile_id": f"CAL-TILE-{index:02d}",
                "bbox_min_x": 0.0,
                "bbox_min_y": 0.0,
                "bbox_max_x": 20.0,
                "bbox_max_y": 20.0,
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
                "eligible_for_agreement": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": SOURCE_TIME.isoformat().replace("+00:00", "Z"),
                "assumptions": "Synthetic calibration query fixture only.",
            }
        )
    return pd.DataFrame(rows)


def _authority_geometry(
    queries: pd.DataFrame,
) -> tuple[tuple[AnnotationRecord, ...], pd.DataFrame]:
    annotations: list[AnnotationRecord] = []
    all_parts: list[pd.DataFrame] = []
    for index, query in enumerate(queries.to_dict("records"), start=1):
        annotation_id = f"AUTH-{query['query_region_id']}"
        reviewed_extent = "entire_query_core"
        if index == 1:
            specs = (
                ("DRY", 0, "POLYGON ((0 10, 10 10, 10 20, 0 20, 0 10))"),
                ("FLOOD", 1, "POLYGON ((10 10, 20 10, 20 20, 10 20, 10 10))"),
                ("WATER", 2, "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"),
                ("UNCERTAIN", 3, "POLYGON ((10 0, 20 0, 20 10, 10 10, 10 0))"),
            )
            fill = False
        elif index == 2:
            specs = (
                ("ARTIFACT", 4, "POLYGON ((0 10, 20 10, 20 20, 0 20, 0 10))"),
                ("DRY", 0, "POLYGON ((0 0, 20 0, 20 10, 0 10, 0 0))"),
            )
            fill = False
        elif index == 3:
            reviewed_extent = "POLYGON ((0 10, 20 10, 20 20, 0 20, 0 10))"
            specs = (
                ("DRY-TOP", 0, "POLYGON ((0 10, 20 10, 20 20, 0 20, 0 10))"),
            )
            fill = False
        else:
            specs = (("DRY-FILL", 0, ""),)
            fill = True
        parts = pd.DataFrame(
            [
                {
                    "annotation_id": annotation_id,
                    "geometry_part_id": part_id,
                    "class_code": class_code,
                    "geometry_wkt": geometry_wkt,
                    "fill_unpainted_with_primary_class": fill,
                }
                for part_id, class_code, geometry_wkt in specs
            ]
        )
        all_parts.append(parts)
        annotations.append(
            AnnotationRecord(
                annotation_id=annotation_id,
                event_id=str(query["event_id"]),
                tile_id=str(query["tile_id"]),
                query_region_id=str(query["query_region_id"]),
                reviewer_id=AUTHORITY_ID,
                reviewer_revision=1,
                primary_class=LabelClass.DRY_LAND,
                confidence=ReviewerConfidence.HIGH,
                ambiguity_reason_codes=(),
                evidence_layers_used=("pre_event_vv", "event_time_vv"),
                review_complete=True,
                reviewed_extent=reviewed_extent,
                geometry=canonical_geometry_parts_payload(parts),
                review_started_at=LOCK_TIME,
                review_finished_at=LOCK_TIME,
                protocol_version="label_factory_protocol_v1",
                tool_version="qgis_manual_review_v1",
                model_predictions_visible=False,
                other_reviewer_annotations_visible=False,
                created_at_utc=LOCK_TIME,
                locked_at_utc=LOCK_TIME,
                source_timestamp=SOURCE_TIME,
                assumptions="Synthetic locked authority reference decision only.",
                bundle_manifest_sha256="c" * 64,
                context_manifest_sha256="d" * 64,
                grid_contract_sha256=GRID_SHA,
                source_registry_sha256=SOURCE_SHA,
            )
        )
    return tuple(annotations), pd.concat(all_parts, ignore_index=True)
