from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.annotation_rasterization import (
    AnnotationRasterizationError,
    canonical_geometry_parts_payload,
    rasterize_annotation_geometries,
    write_rasterized_annotation_outputs,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    ReviewerConfidence,
    annotation_content_sha256,
)


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("shapely") is None,
    reason="optional geo dependency is not installed",
)


def _annotation(
    *,
    reviewed_extent: str = "entire_query_core",
    geometry_parts: pd.DataFrame | None = None,
) -> AnnotationRecord:
    timestamp = datetime(2024, 9, 16, tzinfo=timezone.utc)
    bound_parts = _parts() if geometry_parts is None else geometry_parts
    return AnnotationRecord(
        annotation_id="ANN-A",
        event_id="TH-MAESAI-2024-09",
        tile_id="TILE-1",
        query_region_id="QUERY-1",
        reviewer_id="RV-A",
        reviewer_revision=1,
        primary_class=LabelClass.DRY_LAND,
        confidence=ReviewerConfidence.HIGH,
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv"),
        review_complete=True,
        reviewed_extent=reviewed_extent,
        geometry=canonical_geometry_parts_payload(bound_parts),
        review_started_at=timestamp,
        review_finished_at=timestamp,
        protocol_version="label_factory_protocol_v1",
        tool_version="qgis_manual_review_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=timestamp,
        locked_at_utc=timestamp,
    )


def _query() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "query_region_id": "QUERY-1",
                "event_id": "TH-MAESAI-2024-09",
                "tile_id": "TILE-1",
                "bbox_min_x": 0.0,
                "bbox_min_y": 0.0,
                "bbox_max_x": 40.0,
                "bbox_max_y": 40.0,
                "query_size_pixels": 4,
                "crs": "EPSG:32647",
                "grid_id": "UTM47N_10M",
                "grid_contract_sha256": "a" * 64,
                "source_registry_sha256": "b" * 64,
                "eligible_for_agreement": True,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "assumptions": "Synthetic grid contract only.",
            }
        ]
    )


def _parts(*, fill: bool = False) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "annotation_id": "ANN-A",
                "geometry_part_id": "DRY-LEFT",
                "class_code": 0,
                "geometry_wkt": "POLYGON ((0 0, 20 0, 20 40, 0 40, 0 0))",
                "fill_unpainted_with_primary_class": fill,
            },
            {
                "annotation_id": "ANN-A",
                "geometry_part_id": "FLOOD-RIGHT",
                "class_code": 1,
                "geometry_wkt": "POLYGON ((20 0, 40 0, 40 40, 20 40, 20 0))",
                "fill_unpainted_with_primary_class": fill,
            },
        ]
    )


def test_multiclass_geometry_becomes_canonical_cell_labels() -> None:
    cells = rasterize_annotation_geometries([_annotation()], _query(), _parts())

    assert len(cells) == 16
    assert cells["label_code"].value_counts().to_dict() == {0: 8, 1: 8}
    assert cells["cell_id"].is_unique
    assert cells["eligible_for_agreement"].eq(True).all()
    assert cells["eligible_for_query_model_training"].eq(False).all()
    assert cells["eligible_for_fpps"].eq(False).all()


def test_unpainted_reviewed_cells_are_not_silently_dry() -> None:
    parts = _parts().iloc[[0]].copy()

    with pytest.raises(AnnotationRasterizationError, match="unassigned"):
        rasterize_annotation_geometries(
            [_annotation(geometry_parts=parts)], _query(), parts
        )

    parts["fill_unpainted_with_primary_class"] = True
    cells = rasterize_annotation_geometries(
        [_annotation(geometry_parts=parts)], _query(), parts
    )
    assert cells["label_code"].eq(0).all()


def test_geometry_outside_query_is_rejected() -> None:
    parts = _parts()
    parts.loc[0, "geometry_wkt"] = "POLYGON ((-1 0, 20 0, 20 40, -1 40, -1 0))"

    with pytest.raises(AnnotationRasterizationError, match="outside query"):
        rasterize_annotation_geometries(
            [_annotation(geometry_parts=parts)], _query(), parts
        )


@pytest.mark.parametrize("mutation", ["changed", "extra", "missing"])
def test_geometry_parts_must_exactly_match_locked_annotation(mutation: str) -> None:
    locked_parts = _parts()
    supplied_parts = locked_parts.copy()
    if mutation == "changed":
        supplied_parts.loc[0, "geometry_wkt"] = (
            "POLYGON ((0 0, 10 0, 10 40, 0 40, 0 0))"
        )
    elif mutation == "extra":
        extra = supplied_parts.iloc[[0]].copy()
        extra.loc[:, "geometry_part_id"] = "DRY-EXTRA"
        extra.loc[:, "geometry_wkt"] = "POLYGON ((0 0, 5 0, 5 40, 0 40, 0 0))"
        supplied_parts = pd.concat([supplied_parts, extra], ignore_index=True)
    else:
        supplied_parts = supplied_parts.iloc[[0]].copy()

    with pytest.raises(AnnotationRasterizationError, match="do not exactly match"):
        rasterize_annotation_geometries(
            [_annotation(geometry_parts=locked_parts)],
            _query(),
            supplied_parts,
        )


def test_legacy_unbound_geometry_is_not_rasterizable() -> None:
    annotation = replace(
        _annotation(),
        geometry="POLYGON ((0 0, 40 0, 40 40, 0 40, 0 0))",
    )

    with pytest.raises(AnnotationRasterizationError, match="unbound legacy geometry"):
        rasterize_annotation_geometries([annotation], _query(), _parts())


def test_canonical_payload_is_independent_of_geometry_part_row_order() -> None:
    parts = _parts()
    reversed_parts = parts.iloc[::-1].reset_index(drop=True)

    assert canonical_geometry_parts_payload(parts) == canonical_geometry_parts_payload(
        reversed_parts
    )


def test_writer_is_hashed_and_non_overwriting(tmp_path: Path) -> None:
    annotation = _annotation()
    written = write_rasterized_annotation_outputs(
        [annotation],
        _query(),
        _parts(),
        cell_output_path=tmp_path / "cells.csv",
        manifest_output_path=tmp_path / "cells.manifest.json",
    )

    assert written.cell_labels.exists()
    assert written.manifest.exists()
    manifest = json.loads(written.manifest.read_text(encoding="utf-8"))
    assert manifest["source_annotation_content_sha256"] == {
        annotation.annotation_id: annotation_content_sha256(annotation)
    }
    with pytest.raises(AnnotationRasterizationError, match="must not be overwritten"):
        write_rasterized_annotation_outputs(
            [annotation],
            _query(),
            _parts(),
            cell_output_path=written.cell_labels,
            manifest_output_path=written.manifest,
        )
