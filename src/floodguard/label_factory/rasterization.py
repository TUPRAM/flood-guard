"""Deterministic positive-unlabeled rasterisation for weak polygon seeds.

This module intentionally does not create reviewed flood labels.  A legacy
polygon is rasterised by cell centre, then converted to the explicit weak-seed
taxonomy: polygon interior is a weak positive, exterior is unreviewed, and an
optional boundary band is weak-uncertain.  The accompanying manifest preserves
that provenance so the numeric code ``1`` cannot be mistaken for human truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import TypeAlias

import pandas as pd

from floodguard.label_factory.contracts import (
    QUERY_MODEL_ELIGIBILITY,
    WeakSeedLabel,
    convert_weak_binary_mask_to_positive_unlabeled,
)
from floodguard.label_factory.tiling import Bounds, validate_projected_metre_crs


Coordinate: TypeAlias = tuple[float, float]
Ring: TypeAlias = tuple[Coordinate, ...]
Polygon: TypeAlias = tuple[Ring, ...]


class RasterizationError(ValueError):
    """Raised when geometry or raster metadata violate the seed contract."""


@dataclass(frozen=True)
class WeakSeedRaster:
    """Immutable weak-seed grid and its declared projected-grid metadata."""

    values: tuple[tuple[WeakSeedLabel, ...], ...]
    bounds: Bounds
    crs: str
    boundary_buffer_cells: int

    @property
    def height_cells(self) -> int:
        """Return raster row count."""

        return len(self.values)

    @property
    def width_cells(self) -> int:
        """Return raster column count."""

        return len(self.values[0])

    @property
    def cell_width_m(self) -> float:
        """Return horizontal output spacing in projected metres."""

        return (self.bounds.max_x - self.bounds.min_x) / self.width_cells

    @property
    def cell_height_m(self) -> float:
        """Return vertical output spacing in projected metres."""

        return (self.bounds.max_y - self.bounds.min_y) / self.height_cells

    def class_counts(self) -> dict[str, int]:
        """Return complete weak-seed class counts, including zero counts."""

        flat = [value for row in self.values for value in row]
        return {
            label.name.lower(): sum(value is label for value in flat)
            for label in WeakSeedLabel
        }

    def to_long_frame(self) -> pd.DataFrame:
        """Return one row per cell using north-to-south raster row order."""

        rows: list[dict[str, object]] = []
        for row_index, row in enumerate(self.values):
            for column_index, label in enumerate(row):
                rows.append(
                    {
                        "row": row_index,
                        "column": column_index,
                        "weak_seed_code": int(label),
                        "weak_seed_class": label.name.lower(),
                        "source_type": "positive_unlabeled_weak_seed",
                        "reviewed_truth": False,
                    }
                )
        return pd.DataFrame(rows)


def load_geojson_polygons(path: str | Path) -> tuple[Polygon, ...]:
    """Load Polygon/MultiPolygon members from a GeoJSON object.

    Features without geometry are ignored.  Other non-empty geometry types are
    rejected rather than silently buffered or coerced.
    """

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RasterizationError(f"Could not read GeoJSON geometry: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RasterizationError("GeoJSON root must be an object.")

    geometry_objects: list[Mapping[str, object]] = []
    object_type = payload.get("type")
    if object_type == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise RasterizationError("FeatureCollection.features must be a list.")
        for feature in features:
            if not isinstance(feature, Mapping):
                raise RasterizationError("Every GeoJSON feature must be an object.")
            geometry = feature.get("geometry")
            if geometry is None:
                continue
            if not isinstance(geometry, Mapping):
                raise RasterizationError("Feature geometry must be an object or null.")
            geometry_objects.append(geometry)
    elif object_type == "Feature":
        geometry = payload.get("geometry")
        if geometry is not None:
            if not isinstance(geometry, Mapping):
                raise RasterizationError("Feature geometry must be an object or null.")
            geometry_objects.append(geometry)
    else:
        geometry_objects.append(payload)

    polygons: list[Polygon] = []
    for geometry in geometry_objects:
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "Polygon":
            polygons.append(_coerce_polygon(coordinates))
        elif geometry_type == "MultiPolygon":
            if not isinstance(coordinates, list):
                raise RasterizationError("MultiPolygon coordinates must be a list.")
            polygons.extend(_coerce_polygon(item) for item in coordinates)
        else:
            raise RasterizationError(
                "Weak seed geometry must be Polygon or MultiPolygon; "
                f"found {geometry_type!r}."
            )
    if not polygons:
        raise RasterizationError("GeoJSON contains no polygon geometry.")
    return tuple(polygons)


def rasterize_positive_unlabeled_seed(
    polygons: Sequence[Polygon],
    *,
    bounds: Bounds,
    width_cells: int,
    height_cells: int,
    crs: str,
    boundary_buffer_cells: int = 0,
) -> WeakSeedRaster:
    """Rasterise polygon union using cell centres and weak-seed semantics.

    Row zero is the north edge and column zero is the west edge.  Cell-centre
    inclusion is deterministic and independent of polygon input order.  This
    routine does not infer CRS transformations; input coordinates must already
    be in the explicitly supplied projected metre CRS.
    """

    normalized_crs = validate_projected_metre_crs(crs)
    _positive_integer(width_cells, "width_cells")
    _positive_integer(height_cells, "height_cells")
    if not polygons:
        raise RasterizationError("At least one polygon is required.")
    canonical_polygons = tuple(_coerce_existing_polygon(item) for item in polygons)

    cell_width = (bounds.max_x - bounds.min_x) / width_cells
    cell_height = (bounds.max_y - bounds.min_y) / height_cells
    if not math.isfinite(cell_width) or not math.isfinite(cell_height):
        raise RasterizationError("Raster cell dimensions must be finite.")
    binary: list[list[int]] = []
    for row_index in range(height_cells):
        y = bounds.max_y - (row_index + 0.5) * cell_height
        row: list[int] = []
        for column_index in range(width_cells):
            x = bounds.min_x + (column_index + 0.5) * cell_width
            row.append(
                int(any(_point_in_polygon((x, y), polygon) for polygon in canonical_polygons))
            )
        binary.append(row)
    try:
        weak_values = convert_weak_binary_mask_to_positive_unlabeled(
            binary,
            boundary_buffer_cells=boundary_buffer_cells,
        )
    except ValueError as exc:
        raise RasterizationError(str(exc)) from exc
    return WeakSeedRaster(
        values=weak_values,
        bounds=bounds,
        crs=normalized_crs,
        boundary_buffer_cells=boundary_buffer_cells,
    )


def write_weak_seed_outputs(
    source_geojson_path: str | Path,
    raster: WeakSeedRaster,
    *,
    raster_output_path: str | Path,
    manifest_output_path: str | Path,
    seed_id: str,
    event_id: str,
    grid_id: str,
    query_region_id: str,
    tile_id: str,
    grid_contract_sha256: str,
    query_manifest_sha256: str,
    source_timestamp: str,
    assumptions: str,
) -> dict[str, Path]:
    """Write a cell CSV and provenance manifest without leaking local paths."""

    source_path = Path(source_geojson_path)
    raster_path = Path(raster_output_path)
    manifest_path = Path(manifest_output_path)
    if raster_path.suffix.lower() != ".csv" or manifest_path.suffix.lower() != ".csv":
        raise RasterizationError("Weak-seed raster and manifest outputs must be CSV.")
    if raster_path.exists() or manifest_path.exists():
        raise RasterizationError("Weak-seed outputs must not overwrite existing files.")
    for label, value in {
        "seed_id": seed_id,
        "event_id": event_id,
        "grid_id": grid_id,
        "query_region_id": query_region_id,
        "tile_id": tile_id,
        "source_timestamp": source_timestamp,
        "assumptions": assumptions,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise RasterizationError(f"{label} must not be blank.")
    for label, digest in {
        "grid_contract_sha256": grid_contract_sha256,
        "query_manifest_sha256": query_manifest_sha256,
    }.items():
        if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
            raise RasterizationError(f"{label} must be a complete SHA-256.")
    try:
        timestamp = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RasterizationError("source_timestamp must be valid ISO-8601.") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise RasterizationError("source_timestamp must be timezone-aware.")
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise RasterizationError(f"Could not hash weak-seed source: {exc}") from exc

    raster_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    raster.to_long_frame().to_csv(raster_path, index=False)
    counts = raster.class_counts()
    safety = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()
    manifest = pd.DataFrame(
        [
            {
                "seed_id": seed_id,
                "event_id": event_id,
                "grid_id": grid_id,
                "grid_contract_sha256": grid_contract_sha256.lower(),
                "query_region_id": query_region_id,
                "tile_id": tile_id,
                "query_manifest_sha256": query_manifest_sha256.lower(),
                "source_type": "positive_unlabeled_weak_seed",
                "source_file_hint": source_path.name,
                "source_geometry_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "raster_file_hint": raster_path.name,
                "crs": raster.crs,
                "bbox_min_x": raster.bounds.min_x,
                "bbox_min_y": raster.bounds.min_y,
                "bbox_max_x": raster.bounds.max_x,
                "bbox_max_y": raster.bounds.max_y,
                "width_cells": raster.width_cells,
                "height_cells": raster.height_cells,
                "cell_width_m": raster.cell_width_m,
                "cell_height_m": raster.cell_height_m,
                "boundary_buffer_cells": raster.boundary_buffer_cells,
                "weak_positive_cells": counts["weak_positive"],
                "weak_uncertain_cells": counts["weak_uncertain"],
                "unreviewed_cells": counts["unreviewed"],
                "reviewed_truth": False,
                "eligible_for_training_before_human_review": False,
                **safety,
                "source_timestamp": source_timestamp,
                "confidence_class": "low",
                "assumptions": assumptions,
            }
        ]
    )
    manifest.to_csv(manifest_path, index=False)
    return {"raster": raster_path, "manifest": manifest_path}


def _coerce_polygon(value: object) -> Polygon:
    if not isinstance(value, list) or not value:
        raise RasterizationError("Polygon coordinates must contain at least one ring.")
    rings: list[Ring] = []
    for ring_value in value:
        if not isinstance(ring_value, list):
            raise RasterizationError("Polygon rings must be coordinate lists.")
        ring = tuple(_coerce_coordinate(item) for item in ring_value)
        rings.append(_validated_ring(ring))
    return tuple(rings)


def _coerce_existing_polygon(value: object) -> Polygon:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise RasterizationError("Each polygon must contain at least one ring.")
    rings: list[Ring] = []
    for ring_value in value:
        if not isinstance(ring_value, Sequence) or isinstance(ring_value, (str, bytes)):
            raise RasterizationError("Each polygon ring must be a coordinate sequence.")
        ring = tuple(_coerce_coordinate(item) for item in ring_value)
        rings.append(_validated_ring(ring))
    return tuple(rings)


def _coerce_coordinate(value: object) -> Coordinate:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2:
        raise RasterizationError("Coordinates must contain finite x and y values.")
    try:
        x = float(value[0])
        y = float(value[1])
    except (TypeError, ValueError) as exc:
        raise RasterizationError("Coordinates must contain finite x and y values.") from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise RasterizationError("Coordinates must contain finite x and y values.")
    return (x, y)


def _validated_ring(ring: Ring) -> Ring:
    if len(ring) < 4:
        raise RasterizationError("Polygon rings require at least four coordinates.")
    if ring[0] != ring[-1]:
        raise RasterizationError("Polygon rings must be explicitly closed.")
    if len(set(ring[:-1])) < 3:
        raise RasterizationError("Polygon rings require at least three distinct vertices.")
    return ring


def _point_in_polygon(point: Coordinate, polygon: Polygon) -> bool:
    if not _point_in_ring(point, polygon[0]):
        return False
    return not any(_point_in_ring(point, hole) for hole in polygon[1:])


def _point_in_ring(point: Coordinate, ring: Ring) -> bool:
    x, y = point
    inside = False
    for start, end in zip(ring, ring[1:]):
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
    return inside


def _point_on_segment(point: Coordinate, start: Coordinate, end: Coordinate) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    scale = max(1.0, abs(x), abs(y), abs(x1), abs(y1), abs(x2), abs(y2))
    if abs(cross) > 1e-12 * scale * scale:
        return False
    return (
        min(x1, x2) - 1e-12 * scale <= x <= max(x1, x2) + 1e-12 * scale
        and min(y1, y2) - 1e-12 * scale <= y <= max(y1, y2) + 1e-12 * scale
    )


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RasterizationError(f"{label} must be a positive integer.")
    return value


def utc_now() -> str:
    """Return a manifest-compatible UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
