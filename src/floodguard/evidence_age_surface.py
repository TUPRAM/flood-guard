"""Review exact-year raster age estimates at full-unit and AOI-intersection grain.

This module keeps modelled residential counts separate from observed exposure,
access loss, and accepted vulnerability. Pixel counts are apportioned by their
projected area overlap; no bilinear interpolation or age-share transfer is used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform
from shapely.geometry import box, mapping
from shapely.ops import transform
from shapely.prepared import prep

AGE_BANDS = ("00", "01", "05", "10", "15", "20", "25", "30", "35", "40",
             "45", "50", "55", "60", "65", "70", "75", "80", "85", "90")
CHILD_BANDS = ("00", "01", "05", "10")
OLDER_BANDS = ("60", "65", "70", "75", "80", "85", "90")


def _coverage(geometry: Any, source: rasterio.io.DatasetReader) -> tuple[Window, np.ndarray, np.ndarray]:
    """Return per-cell count fractions and covered square metres in EPSG:32647."""
    left, bottom, right, top = geometry.bounds
    floating = from_bounds(left, bottom, right, top, transform=source.transform)
    col0 = max(0, math.floor(floating.col_off))
    row0 = max(0, math.floor(floating.row_off))
    col1 = min(source.width, math.ceil(floating.col_off + floating.width))
    row1 = min(source.height, math.ceil(floating.row_off + floating.height))
    if col1 <= col0 or row1 <= row0:
        raise ValueError("Geometry has no WorldPop grid intersection")
    window = Window(col0, row0, col1 - col0, row1 - row0)
    affine = window_transform(window, source.transform)
    touched = rasterize(
        [(mapping(geometry), 1)], out_shape=(int(window.height), int(window.width)),
        transform=affine, all_touched=True, fill=0, dtype="uint8",
    )
    projector = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
    projected = transform(projector, geometry)
    prepared = prep(projected)
    fractions = np.zeros(touched.shape, dtype="float64")
    covered_m2 = np.zeros(touched.shape, dtype="float64")
    rows, cols = np.nonzero(touched)
    for row, col in zip(rows, cols, strict=True):
        x0, y0 = affine * (int(col), int(row))
        x1, y1 = affine * (int(col) + 1, int(row) + 1)
        pixel = transform(projector, box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        if not prepared.intersects(pixel):
            continue
        area = pixel.area if prepared.covers(pixel) else projected.intersection(pixel).area
        if area <= 0:
            continue
        covered_m2[row, col] = area
        fractions[row, col] = min(1.0, area / pixel.area)
    return window, fractions, covered_m2


def summarize_geometry(
    geometry: Any,
    rasters: Mapping[str, rasterio.io.DatasetReader],
) -> dict[str, Any]:
    """Sum fractional model counts only where every required age band is valid."""
    if set(rasters) != set(AGE_BANDS):
        raise ValueError("Exactly the 20 mutually exclusive age bands are required")
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError("A nonempty valid polygon is required")
    first = rasters[AGE_BANDS[0]]
    if first.crs is None or first.crs.to_epsg() != 4326:
        raise ValueError("WorldPop age source must use EPSG:4326")
    for band in AGE_BANDS[1:]:
        other = rasters[band]
        if (other.crs != first.crs or other.transform != first.transform
                or other.width != first.width or other.height != first.height):
            raise ValueError(f"Age raster {band} is on a different grid")
    window, fraction, covered_m2 = _coverage(geometry, first)
    stack = []
    masks = []
    for band in AGE_BANDS:
        array = rasters[band].read(1, window=window, masked=True)
        values = np.asarray(array.data, dtype="float64")
        valid = ~np.ma.getmaskarray(array)
        valid &= np.isfinite(values) & (values >= 0)
        stack.append(values)
        masks.append(valid)
    shared = np.logical_and.reduce(masks)
    mask_mismatch = any(not np.array_equal(mask, masks[0]) for mask in masks[1:])
    geometry_m2 = transform(
        Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform,
        geometry,
    ).area
    supported_m2 = float(np.sum(covered_m2[shared], dtype="float64"))
    if not shared.any() or supported_m2 <= 0:
        return {
            "status": "unavailable_no_common_raster_support",
            "population_estimate": None, "children_0_14_estimate": None,
            "older_60_plus_estimate": None, "other_15_59_estimate": None,
            "band_counts": None, "geometry_area_km2": geometry_m2 / 1e6,
            "source_supported_area_km2": 0.0, "source_coverage_fraction": 0.0,
            "band_mask_mismatch": mask_mismatch,
        }
    weights = np.where(shared, fraction, 0.0)
    counts = {band: float(np.sum(values * weights, dtype="float64"))
              for band, values in zip(AGE_BANDS, stack, strict=True)}
    total = math.fsum(counts.values())
    children = math.fsum(counts[band] for band in CHILD_BANDS)
    older = math.fsum(counts[band] for band in OLDER_BANDS)
    other = total - children - older
    if other < -1e-7:
        raise ValueError("Age bands do not reconcile")
    return {
        "status": "partial_band_coverage" if mask_mismatch else "modelled_research_estimate",
        "population_estimate": total,
        "children_0_14_estimate": children,
        "older_60_plus_estimate": older,
        "other_15_59_estimate": max(0.0, other),
        "band_counts": counts,
        "geometry_area_km2": geometry_m2 / 1e6,
        "source_supported_area_km2": supported_m2 / 1e6,
        "source_coverage_fraction": min(1.0, supported_m2 / geometry_m2),
        "band_mask_mismatch": mask_mismatch,
    }


def review_units(
    raster_paths: Mapping[str, Path], units: Mapping[str, Any], aoi: Any,
) -> list[dict[str, Any]]:
    """Compare whole reporting units with their clipped AOI intersections."""
    if aoi.is_empty or not aoi.is_valid:
        raise ValueError("AOI must be valid and nonempty")
    with ExitStack() as stack:
        rasters = {band: stack.enter_context(rasterio.open(raster_paths[band]))
                   for band in AGE_BANDS}
        rows = []
        for unit_id, unit in sorted(units.items()):
            if unit.is_empty or not unit.is_valid:
                raise ValueError(f"Unit {unit_id} is invalid")
            intersection = unit.intersection(aoi)
            if intersection.is_empty or intersection.area <= 0:
                continue
            full = summarize_geometry(unit, rasters)
            clipped = summarize_geometry(intersection, rasters)
            rows.append({
                "unit_id": unit_id,
                "full_unit": full,
                "aoi_intersection": clipped,
                "aoi_geometry_area_fraction": (
                    clipped["geometry_area_km2"] / full["geometry_area_km2"]
                ),
            })
        return rows
