"""Rasterise locked human geometry onto canonical query-core cells.

This is the bridge between reviewer drawings and cell-level agreement.  It is
strict by design: every geometry must stay inside its query core, different
classes may not cover the same cell, and unpainted reviewed cells remain
unreviewed unless the reviewer explicitly requested primary-class fill.
Every external geometry row must exactly match the versioned multipart payload
inside the locked annotation record; the annotation is the source of truth.
Individual reviewer rasters are agreement evidence, not frozen training truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    annotation_content_sha256,
)


GEOMETRY_PARTS_PAYLOAD_SCHEMA = "floodguard.annotation_geometry_parts.v1"


GEOMETRY_PART_COLUMNS = (
    "annotation_id",
    "geometry_part_id",
    "class_code",
    "geometry_wkt",
    "fill_unpainted_with_primary_class",
)

QUERY_GRID_COLUMNS = (
    "query_region_id",
    "event_id",
    "tile_id",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "query_size_pixels",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "eligible_for_agreement",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "assumptions",
)

CELL_LABEL_COLUMNS = (
    "annotation_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "reviewer_id",
    "review_stage",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
    "label_class",
    "cell_center_x",
    "cell_center_y",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "eligible_for_agreement",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "assumptions",
)


class AnnotationRasterizationError(ValueError):
    """Raised when reviewer geometry cannot safely become canonical cells."""


class AnnotationRasterizationDependencyError(RuntimeError):
    """Raised when the explicitly requested geospatial dependency is absent."""


@dataclass(frozen=True)
class RasterizedAnnotationOutputs:
    """Paths for a cell-label CSV and checksum-bearing manifest."""

    cell_labels: Path
    manifest: Path


def canonical_geometry_parts_payload(geometry_parts: pd.DataFrame) -> str:
    """Return the exact geometry payload that must be locked in an annotation.

    The payload binds every drawable part and the fill policy to the immutable
    :class:`AnnotationRecord`.  Rows are sorted by ``geometry_part_id`` so
    equivalent exports have one deterministic representation.  The
    ``annotation_id`` is deliberately not duplicated inside the payload: it is
    already a required, immutable field of the enclosing annotation record.
    """

    _require_columns(geometry_parts, GEOMETRY_PART_COLUMNS, "geometry parts")
    parts = geometry_parts.copy().fillna("")
    annotation_ids = {str(value).strip() for value in parts["annotation_id"]}
    if len(parts) == 0 or len(annotation_ids) != 1 or "" in annotation_ids:
        raise AnnotationRasterizationError(
            "Geometry payload must contain one annotation_id and at least one part."
        )

    fill_values = {
        _strict_bool(value, "fill_unpainted_with_primary_class")
        for value in parts["fill_unpainted_with_primary_class"]
    }
    if len(fill_values) != 1:
        raise AnnotationRasterizationError(
            "Geometry payload has an inconsistent fill policy."
        )
    fill_primary = next(iter(fill_values))

    canonical_parts: list[dict[str, object]] = []
    seen_part_ids: set[str] = set()
    for row in parts.to_dict("records"):
        part_id = str(row["geometry_part_id"]).strip()
        if not part_id or part_id in seen_part_ids:
            raise AnnotationRasterizationError(
                "geometry_part_id values must be non-blank and unique."
            )
        seen_part_ids.add(part_id)
        class_code = _drawable_class_code(row["class_code"], part_id)
        canonical_parts.append(
            {
                "class_code": class_code,
                "geometry_part_id": part_id,
                "geometry_wkt": str(row["geometry_wkt"]).strip(),
            }
        )

    payload = {
        "fill_unpainted_with_primary_class": fill_primary,
        "parts": sorted(canonical_parts, key=lambda item: str(item["geometry_part_id"])),
        "schema": GEOMETRY_PARTS_PAYLOAD_SCHEMA,
    }
    return _canonical_json(payload)


def validate_annotation_geometry_against_query(
    annotation: AnnotationRecord,
    query: Mapping[str, object] | None = None,
) -> None:
    """Validate polygon syntax and, when supplied, canonical query containment."""

    _Point, box, loads = _load_shapely()
    if annotation.reviewed_extent == "entire_query_core":
        reviewed_extent = None
    else:
        reviewed_extent = _polygon_wkt(
            loads,
            annotation.reviewed_extent,
            "reviewed_extent",
        )
    geometries: list[object] = []
    if annotation.geometry is not None:
        if _looks_like_geometry_parts_payload(annotation.geometry):
            payload = _parse_canonical_geometry_parts_payload(annotation.geometry)
            for part in payload["parts"]:
                wkt = str(part["geometry_wkt"])
                if wkt:
                    geometries.append(
                        _polygon_wkt(
                            loads,
                            wkt,
                            f"geometry part {part['geometry_part_id']}",
                        )
                    )
        else:
            # Legacy single-geometry records remain readable for adjudication
            # and import validation.  They are deliberately not rasterizable:
            # rasterization requires the canonical multipart binding below.
            geometries.append(
                _polygon_wkt(loads, annotation.geometry, "annotation geometry")
            )
    if query is None:
        return
    min_x = _finite(query.get("bbox_min_x"), "bbox_min_x")
    min_y = _finite(query.get("bbox_min_y"), "bbox_min_y")
    max_x = _finite(query.get("bbox_max_x"), "bbox_max_x")
    max_y = _finite(query.get("bbox_max_y"), "bbox_max_y")
    if min_x >= max_x or min_y >= max_y:
        raise AnnotationRasterizationError("Canonical query bounds are invalid.")
    core = box(min_x, min_y, max_x, max_y)
    effective_extent = core if reviewed_extent is None else reviewed_extent
    if not core.covers(effective_extent):
        raise AnnotationRasterizationError("reviewed_extent extends outside query core.")
    for geometry in geometries:
        if not effective_extent.covers(geometry):
            raise AnnotationRasterizationError(
                "annotation geometry extends outside reviewed_extent or query core."
            )


def rasterize_annotation_geometries(
    annotations: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame,
    geometry_parts: pd.DataFrame,
) -> pd.DataFrame:
    """Return canonical cell labels for locked reviewer annotations."""

    if not annotations:
        raise AnnotationRasterizationError("At least one annotation is required.")
    _require_columns(query_manifest, QUERY_GRID_COLUMNS, "query manifest")
    _require_columns(geometry_parts, GEOMETRY_PART_COLUMNS, "geometry parts")
    query_rows = query_manifest.copy().fillna("")
    if query_rows["query_region_id"].astype(str).duplicated().any():
        raise AnnotationRasterizationError("query manifest query_region_id must be unique.")
    for row in query_rows.to_dict("records"):
        _require_sha256(row["grid_contract_sha256"], "grid_contract_sha256")
        _require_sha256(row["source_registry_sha256"], "source_registry_sha256")
    query_by_id = {
        str(row["query_region_id"]): row
        for row in query_rows.to_dict("records")
    }
    annotation_ids = [record.annotation_id for record in annotations]
    if len(annotation_ids) != len(set(annotation_ids)):
        raise AnnotationRasterizationError("annotation_id values must be unique.")
    extra_parts = sorted(
        set(geometry_parts["annotation_id"].astype(str)) - set(annotation_ids)
    )
    if extra_parts:
        raise AnnotationRasterizationError(
            f"Geometry parts reference unknown annotations: {extra_parts[:5]!r}."
        )

    rows: list[dict[str, object]] = []
    for annotation in annotations:
        if not annotation.is_locked or not annotation.review_complete:
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} must be locked and complete."
            )
        if annotation.model_predictions_visible or annotation.other_reviewer_annotations_visible:
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} is not independently blinded."
            )
        query = query_by_id.get(annotation.query_region_id)
        if query is None:
            raise AnnotationRasterizationError(
                f"No canonical query row exists for {annotation.query_region_id}."
            )
        if str(query["event_id"]) != annotation.event_id or str(
            query["tile_id"]
        ) != annotation.tile_id:
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} event/tile lineage does not "
                "match the canonical query manifest."
            )
        parts = geometry_parts[
            geometry_parts["annotation_id"].astype(str).eq(annotation.annotation_id)
        ].copy()
        if parts.empty:
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} needs a geometry-control row."
            )
        _require_geometry_parts_binding(annotation, parts)
        rows.extend(_rasterize_one(annotation, query, parts))
    return pd.DataFrame(rows, columns=CELL_LABEL_COLUMNS)


def write_rasterized_annotation_outputs(
    annotations: Sequence[AnnotationRecord],
    query_manifest: pd.DataFrame | str | Path,
    geometry_parts: pd.DataFrame | str | Path,
    *,
    cell_output_path: str | Path,
    manifest_output_path: str | Path,
) -> RasterizedAnnotationOutputs:
    """Rasterise and write agreement-only cells with source/output hashes."""

    queries = (
        query_manifest.copy()
        if isinstance(query_manifest, pd.DataFrame)
        else pd.read_csv(query_manifest).fillna("")
    )
    parts = (
        geometry_parts.copy()
        if isinstance(geometry_parts, pd.DataFrame)
        else pd.read_csv(geometry_parts).fillna("")
    )
    cells = rasterize_annotation_geometries(annotations, queries, parts)
    cell_path = Path(cell_output_path)
    manifest_path = Path(manifest_output_path)
    if cell_path.suffix.lower() != ".csv":
        raise AnnotationRasterizationError("Cell-label output must be CSV.")
    if manifest_path.suffix.lower() != ".json":
        raise AnnotationRasterizationError("Rasterization manifest must be JSON.")
    if cell_path.exists() or manifest_path.exists():
        raise AnnotationRasterizationError(
            "Rasterized annotation outputs are immutable and must not be overwritten."
        )
    cell_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    cells.to_csv(cell_path, index=False, lineterminator="\n")
    cell_hash = _file_sha256(cell_path)
    payload = {
        "artifact_schema": "floodguard.annotation_cell_raster.v1",
        "annotation_ids": sorted(record.annotation_id for record in annotations),
        "source_annotation_content_sha256": {
            record.annotation_id: annotation_content_sha256(record)
            for record in sorted(annotations, key=lambda item: item.annotation_id)
        },
        "grid_contract_sha256_by_query": {
            str(row["query_region_id"]): str(row["grid_contract_sha256"]).lower()
            for row in queries.to_dict("records")
        },
        "source_registry_sha256_by_query": {
            str(row["query_region_id"]): str(row["source_registry_sha256"]).lower()
            for row in queries.to_dict("records")
        },
        "query_manifest_rows_sha256": _frame_sha256(queries),
        "geometry_parts_rows_sha256": _frame_sha256(parts),
        "cell_labels_file": cell_path.name,
        "cell_labels_sha256": cell_hash,
        "cell_count": len(cells),
        "eligible_for_agreement": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Cell-centre rasterization of locked blinded reviewer geometry; "
            "individual reviewer cells require pairing/adjudication before freeze."
        ),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RasterizedAnnotationOutputs(cell_labels=cell_path, manifest=manifest_path)


def _require_geometry_parts_binding(
    annotation: AnnotationRecord,
    parts: pd.DataFrame,
) -> None:
    """Fail closed unless external parts exactly match locked annotation content."""

    if annotation.geometry is None:
        raise AnnotationRasterizationError(
            f"Annotation {annotation.annotation_id} has no locked geometry-parts payload."
        )
    if not _looks_like_geometry_parts_payload(annotation.geometry):
        raise AnnotationRasterizationError(
            f"Annotation {annotation.annotation_id} uses an unbound legacy geometry; "
            "rasterization requires the canonical geometry-parts payload."
        )
    supplied_annotation_ids = {
        str(value).strip() for value in parts["annotation_id"]
    }
    if supplied_annotation_ids != {annotation.annotation_id}:
        raise AnnotationRasterizationError(
            f"Geometry parts do not belong exclusively to {annotation.annotation_id}."
        )
    _parse_canonical_geometry_parts_payload(annotation.geometry)
    expected_payload = canonical_geometry_parts_payload(parts)
    if annotation.geometry != expected_payload:
        raise AnnotationRasterizationError(
            f"Geometry parts for annotation {annotation.annotation_id} do not exactly "
            "match its locked geometry-parts payload."
        )


def _rasterize_one(
    annotation: AnnotationRecord,
    query: Mapping[str, object],
    parts: pd.DataFrame,
) -> list[dict[str, object]]:
    Point, box, loads = _load_shapely()
    size = _positive_integer(query["query_size_pixels"], "query_size_pixels")
    min_x = _finite(query["bbox_min_x"], "bbox_min_x")
    min_y = _finite(query["bbox_min_y"], "bbox_min_y")
    max_x = _finite(query["bbox_max_x"], "bbox_max_x")
    max_y = _finite(query["bbox_max_y"], "bbox_max_y")
    if min_x >= max_x or min_y >= max_y:
        raise AnnotationRasterizationError("Canonical query bounds are invalid.")
    cell_width = (max_x - min_x) / size
    cell_height = (max_y - min_y) / size
    if not math.isclose(cell_width, cell_height, rel_tol=1e-9, abs_tol=1e-9):
        raise AnnotationRasterizationError(
            "Canonical query cells must be square in the projected CRS."
        )
    query_polygon = box(min_x, min_y, max_x, max_y)
    if annotation.reviewed_extent == "entire_query_core":
        reviewed_extent = query_polygon
    else:
        reviewed_extent = _polygon_wkt(loads, annotation.reviewed_extent, "reviewed_extent")
        if not query_polygon.covers(reviewed_extent):
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} reviewed_extent leaves its query core."
            )

    fills = {
        _strict_bool(value, "fill_unpainted_with_primary_class")
        for value in parts["fill_unpainted_with_primary_class"]
    }
    if len(fills) != 1:
        raise AnnotationRasterizationError(
            f"Annotation {annotation.annotation_id} has inconsistent fill policy."
        )
    fill_primary = next(iter(fills))
    geometries: list[tuple[LabelClass, object, str]] = []
    seen_part_ids: set[str] = set()
    for row in parts.to_dict("records"):
        part_id = str(row["geometry_part_id"]).strip()
        if not part_id or part_id in seen_part_ids:
            raise AnnotationRasterizationError(
                f"Annotation {annotation.annotation_id} geometry_part_id values must be unique."
            )
        seen_part_ids.add(part_id)
        try:
            label = LabelClass(int(row["class_code"]))
        except (TypeError, ValueError) as exc:
            raise AnnotationRasterizationError(
                f"Geometry part {part_id} has invalid class_code."
            ) from exc
        if label is LabelClass.UNREVIEWED:
            raise AnnotationRasterizationError(
                "Unreviewed is an absence of a decision, not a drawable geometry class."
            )
        wkt = str(row["geometry_wkt"]).strip()
        if not wkt:
            if not fill_primary or label is not annotation.primary_class:
                raise AnnotationRasterizationError(
                    f"Blank geometry part {part_id} is allowed only as the explicit "
                    "primary-class fill control."
                )
            continue
        geometry = _polygon_wkt(loads, wkt, f"geometry part {part_id}")
        if not query_polygon.covers(geometry):
            raise AnnotationRasterizationError(
                f"Geometry part {part_id} extends outside query {annotation.query_region_id}."
            )
        if not reviewed_extent.covers(geometry):
            raise AnnotationRasterizationError(
                f"Geometry part {part_id} extends outside reviewed_extent."
            )
        geometries.append((label, geometry, part_id))

    output: list[dict[str, object]] = []
    unassigned_reviewed = 0
    for row_index in range(size):
        y = max_y - (row_index + 0.5) * cell_height
        for column_index in range(size):
            x = min_x + (column_index + 0.5) * cell_width
            point = Point(x, y)
            if not reviewed_extent.covers(point):
                label = LabelClass.UNREVIEWED
            else:
                matches = [
                    (candidate, part_id)
                    for candidate, geometry, part_id in geometries
                    if geometry.covers(point)
                ]
                matched_classes = {candidate for candidate, _part_id in matches}
                if len(matched_classes) > 1:
                    raise AnnotationRasterizationError(
                        f"Different classes overlap cell ({row_index}, {column_index}) "
                        f"for annotation {annotation.annotation_id}."
                    )
                if matched_classes:
                    label = next(iter(matched_classes))
                elif fill_primary:
                    label = annotation.primary_class
                else:
                    label = LabelClass.UNREVIEWED
                    unassigned_reviewed += 1
            output.append(
                {
                    "annotation_id": annotation.annotation_id,
                    "event_id": annotation.event_id,
                    "tile_id": annotation.tile_id,
                    "query_region_id": annotation.query_region_id,
                    "reviewer_id": annotation.reviewer_id,
                    "review_stage": annotation.review_stage.value,
                    "cell_id": (
                        f"{annotation.query_region_id}_R{row_index:04d}_C{column_index:04d}"
                    ),
                    "row_index": row_index,
                    "column_index": column_index,
                    "label_code": int(label),
                    "label_class": label.name.lower(),
                    "cell_center_x": x,
                    "cell_center_y": y,
                    "crs": str(query["crs"]),
                    "grid_id": str(query["grid_id"]),
                    "grid_contract_sha256": str(query["grid_contract_sha256"]),
                    "source_registry_sha256": str(query["source_registry_sha256"]),
                    "eligible_for_agreement": True,
                    "eligible_for_query_model_training": False,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                    "source_timestamp": str(query["source_timestamp"]),
                    "assumptions": str(query["assumptions"]),
                }
            )
    if unassigned_reviewed:
        raise AnnotationRasterizationError(
            f"Annotation {annotation.annotation_id} marks review_complete but leaves "
            f"{unassigned_reviewed} reviewed cells unassigned; draw all classes or "
            "explicitly enable primary-class fill."
        )
    return output


def _load_shapely() -> tuple[object, object, object]:
    try:
        from shapely import Point, box, wkt
    except (ImportError, ModuleNotFoundError) as exc:
        raise AnnotationRasterizationDependencyError(
            "Human-geometry rasterization requires the optional geo dependency; "
            "install it with `uv sync --extra geo`."
        ) from exc
    return Point, box, wkt.loads


def _polygon_wkt(loader: object, value: str, label: str) -> object:
    try:
        geometry = loader(value)  # type: ignore[operator]
    except Exception as exc:
        raise AnnotationRasterizationError(f"{label} is not valid WKT.") from exc
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise AnnotationRasterizationError(f"{label} must be a non-empty polygon.")
    if not geometry.is_valid:
        raise AnnotationRasterizationError(f"{label} is topologically invalid.")
    return geometry


def _looks_like_geometry_parts_payload(value: str) -> bool:
    return value.lstrip().startswith("{")


def _parse_canonical_geometry_parts_payload(value: str) -> dict[str, object]:
    """Parse a locked payload and require its one canonical representation."""

    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AnnotationRasterizationError(
            "Locked geometry-parts payload is not valid JSON."
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema",
        "fill_unpainted_with_primary_class",
        "parts",
    }:
        raise AnnotationRasterizationError(
            "Locked geometry-parts payload has unexpected or missing fields."
        )
    if raw["schema"] != GEOMETRY_PARTS_PAYLOAD_SCHEMA:
        raise AnnotationRasterizationError("Unsupported geometry-parts payload schema.")
    fill_primary = raw["fill_unpainted_with_primary_class"]
    if not isinstance(fill_primary, bool):
        raise AnnotationRasterizationError(
            "Locked geometry-parts fill policy must be boolean."
        )
    raw_parts = raw["parts"]
    if not isinstance(raw_parts, list) or not raw_parts:
        raise AnnotationRasterizationError(
            "Locked geometry-parts payload must contain at least one part."
        )

    canonical_parts: list[dict[str, object]] = []
    seen_part_ids: set[str] = set()
    for index, part in enumerate(raw_parts):
        if not isinstance(part, dict) or set(part) != {
            "geometry_part_id",
            "class_code",
            "geometry_wkt",
        }:
            raise AnnotationRasterizationError(
                f"Locked geometry part {index} has unexpected or missing fields."
            )
        part_id = part["geometry_part_id"]
        geometry_wkt = part["geometry_wkt"]
        if (
            not isinstance(part_id, str)
            or not part_id.strip()
            or part_id != part_id.strip()
        ):
            raise AnnotationRasterizationError(
                "Locked geometry_part_id values must be canonical non-blank strings."
            )
        if part_id in seen_part_ids:
            raise AnnotationRasterizationError(
                "Locked geometry_part_id values must be unique."
            )
        seen_part_ids.add(part_id)
        if not isinstance(geometry_wkt, str) or geometry_wkt != geometry_wkt.strip():
            raise AnnotationRasterizationError(
                f"Locked geometry part {part_id} WKT is not canonical."
            )
        class_code = _drawable_class_code(part["class_code"], part_id)
        canonical_parts.append(
            {
                "class_code": class_code,
                "geometry_part_id": part_id,
                "geometry_wkt": geometry_wkt,
            }
        )

    canonical = {
        "fill_unpainted_with_primary_class": fill_primary,
        "parts": sorted(canonical_parts, key=lambda item: str(item["geometry_part_id"])),
        "schema": GEOMETRY_PARTS_PAYLOAD_SCHEMA,
    }
    if value != _canonical_json(canonical):
        raise AnnotationRasterizationError(
            "Locked geometry-parts payload is not in canonical deterministic form."
        )
    return canonical


def _drawable_class_code(value: object, part_id: str) -> int:
    if isinstance(value, bool):
        raise AnnotationRasterizationError(
            f"Geometry part {part_id} has invalid class_code."
        )
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise AnnotationRasterizationError(
            f"Geometry part {part_id} has invalid class_code."
        ) from exc
    try:
        label = LabelClass(numeric)
    except ValueError as exc:
        raise AnnotationRasterizationError(
            f"Geometry part {part_id} has invalid class_code."
        ) from exc
    if label is LabelClass.UNREVIEWED:
        raise AnnotationRasterizationError(
            "Unreviewed is an absence of a decision, not a drawable geometry class."
        )
    return int(label)


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise AnnotationRasterizationError(
            f"{label} is missing columns: {', '.join(missing)}"
        )


def _strict_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise AnnotationRasterizationError(f"{label} must be an explicit boolean.")


def _require_sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise AnnotationRasterizationError(f"{label} must be a complete SHA-256.")
    return text


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise AnnotationRasterizationError(f"{label} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AnnotationRasterizationError(f"{label} must be a positive integer.") from exc
    if number <= 0 or float(value) != number:
        raise AnnotationRasterizationError(f"{label} must be a positive integer.")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise AnnotationRasterizationError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnnotationRasterizationError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise AnnotationRasterizationError(f"{label} must be finite.")
    return number


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    text = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
