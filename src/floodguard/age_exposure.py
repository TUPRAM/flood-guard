"""Per-unit dependent share from the WorldPop 2024 1 km age counts (plan task E7).

The vulnerability component of planning frame v1 rests on a unit's dependent
share: residents aged 0-14 plus residents aged 60 and over, divided by all
residents (protocol v1a, ``scoring_frame.components.vulnerability_context_0_100``).
This module computes that share for a reporting unit, with what a reader needs
to judge it:

* the age counts, allocated to the unit by the projected-area fraction of each
  1 km cell inside the unit. That is the allocation protocol v1b states for the
  national anchors (``national_vulnerability_anchors.method.allocation``,
  drafter reading DR-B04), and the counts come from the same function the
  anchors used, :func:`floodguard.evidence_age_surface.summarize_geometry`;
* the number of 1 km age cells the share rests on;
* the part of the unit's area that has no age counts (the unsupported area);
* a low/high range from two other allocations of the same cells; and
* the 2024-rescaled demand rule of protocol v1b (owner choice 12), as a pure
  function.

It computes no vulnerability component, no FPPS, no A-E class and no ensemble.
The counts are modelled estimates, not observations, and nothing here is an
official warning.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

from floodguard.evidence_age_surface import (
    AGE_BANDS,
    CHILD_BANDS,
    OLDER_BANDS,
    _coverage,
    summarize_geometry,
)
from floodguard.normalisation import dependent_share

AGE_EXPOSURE_VERSION = "age_exposure_v1"

# The three ways this module spreads a 1 km cell's counts over a unit.
PROJECTED_AREA_FRACTION = "projected_area_fraction"
CELLS_WHOLLY_INSIDE = "cells_wholly_inside"
CELLS_ANY_TOUCHING = "cells_any_touching"
ALLOCATION_RULES: tuple[str, ...] = (PROJECTED_AREA_FRACTION, CELLS_WHOLLY_INSIDE, CELLS_ANY_TOUCHING)

# A cell counts as wholly inside when the unit covers this share of its projected area.
# The overlap is computed in floating point, so an exact 1.0 is not required.
WHOLLY_INSIDE_MIN_FRACTION = 1.0 - 1e-9

# The two computations of the central counts (the anchors' function and this
# module's cell table) must agree to this tolerance, or the build stops.
_RELATIVE_TOLERANCE = 1e-9
_ABSOLUTE_TOLERANCE = 1e-6

ALLOCATION_STATEMENT = (
    "Each 1 km cell's counts go to a unit by the fraction of the cell's projected area (EPSG:32647) inside "
    "the unit, on cells where all 20 age bands are valid (protocol v1b national_vulnerability_anchors.method."
    "allocation, drafter reading DR-B04; floodguard.evidence_age_surface.summarize_geometry)."
)
RANGE_STATEMENT = (
    "Low and high are the smallest and the largest dependent share over three allocations of the same cells: "
    "the projected-area fraction (the value of record), only the cells wholly inside the unit, and every cell "
    "that touches the unit counted in full. It shows how far the 1 km cell size can move the share. It is not "
    "a confidence interval and it does not cover the error of the modelled age counts."
)
AGE_CELLS_STATEMENT = (
    "The number of distinct 1 km cells of the age grid that overlap the unit and carry a valid count in all "
    "20 age bands. A cell on the unit's edge counts once, whatever share of it is inside."
)
UNSUPPORTED_AREA_STATEMENT = (
    "The part of the unit's projected area (EPSG:32647) that lies in cells with no valid count in at least one "
    "of the 20 age bands, or outside the age grid. It has no age count: it is unknown, not zero."
)


class AgeExposureError(ValueError):
    """Raised when age-exposure inputs break the rules of this module."""


@dataclass(frozen=True)
class AgeCell:
    """One 1 km cell of the age grid that overlaps a unit.

    Attributes:
        raster_row: Row of the cell in the source grid.
        raster_col: Column of the cell in the source grid.
        fraction: Share of the cell's projected area that lies inside the unit.
        covered_m2: That overlap in square metres (EPSG:32647).
        residents: The whole cell's residents (the sum of the 20 age bands), or
            ``None`` when any band has no valid count there.
        children_0_14: The whole cell's residents aged 0-14, or ``None``.
        older_60_plus: The whole cell's residents aged 60 and over, or ``None``.
    """

    raster_row: int
    raster_col: int
    fraction: float
    covered_m2: float
    residents: float | None
    children_0_14: float | None
    older_60_plus: float | None

    @property
    def supported(self) -> bool:
        """Say whether all 20 age bands carry a valid count in this cell."""

        return self.residents is not None

    @property
    def wholly_inside(self) -> bool:
        """Say whether the unit covers the whole cell."""

        return self.fraction >= WHOLLY_INSIDE_MIN_FRACTION


def read_unit_cells(geometry: Any, rasters: Mapping[str, rasterio.io.DatasetReader]) -> list[AgeCell]:
    """List the 1 km age cells that overlap a unit, with the overlap and the whole-cell counts.

    The overlap comes from the same routine the national anchors used
    (``floodguard.evidence_age_surface._coverage``), so the fractions here are
    the fractions behind :func:`summarize_geometry`.

    Args:
        geometry: The unit polygon in EPSG:4326.
        rasters: The 20 open age rasters, keyed by band.

    Raises:
        ValueError: when the geometry does not meet the age grid.
    """

    if set(rasters) != set(AGE_BANDS):
        raise AgeExposureError("exactly the 20 age bands are required")
    window, fractions, covered_m2 = _coverage(geometry, rasters[AGE_BANDS[0]])
    values: dict[str, np.ndarray] = {}
    valid: list[np.ndarray] = []
    for band in AGE_BANDS:
        array = rasters[band].read(1, window=window, masked=True)
        data = np.asarray(array.data, dtype="float64")
        values[band] = data
        valid.append(~np.ma.getmaskarray(array) & np.isfinite(data) & (data >= 0))
    shared = np.logical_and.reduce(valid)
    cells: list[AgeCell] = []
    rows, cols = np.nonzero(covered_m2 > 0)
    for row, col in zip(rows.tolist(), cols.tolist(), strict=True):
        residents = children = older = None
        if shared[row, col]:
            residents = math.fsum(float(values[band][row, col]) for band in AGE_BANDS)
            children = math.fsum(float(values[band][row, col]) for band in CHILD_BANDS)
            older = math.fsum(float(values[band][row, col]) for band in OLDER_BANDS)
        cells.append(AgeCell(
            raster_row=int(window.row_off) + row,
            raster_col=int(window.col_off) + col,
            fraction=float(fractions[row, col]),
            covered_m2=float(covered_m2[row, col]),
            residents=residents,
            children_0_14=children,
            older_60_plus=older,
        ))
    return cells


def _weight(cell: AgeCell, rule: str) -> float:
    """Return the share of a cell's counts that one allocation rule gives the unit."""

    if rule == PROJECTED_AREA_FRACTION:
        return cell.fraction
    if rule == CELLS_WHOLLY_INSIDE:
        return 1.0 if cell.wholly_inside else 0.0
    if rule == CELLS_ANY_TOUCHING:
        return 1.0 if cell.fraction > 0 else 0.0
    raise AgeExposureError(f"unknown allocation rule: {rule}")


def allocate_cells(cells: Iterable[AgeCell], rule: str) -> dict[str, Any]:
    """Sum the cells' counts for a unit under one allocation rule.

    Args:
        cells: The cells that overlap the unit.
        rule: ``projected_area_fraction`` (the value of record, reading DR-B04),
            ``cells_wholly_inside`` or ``cells_any_touching``.

    Returns:
        The number of cells used, the residents, children, older adults and
        other residents, and the dependent share. The share is ``None`` when
        no cell is used or the cells used hold no resident.

    Raises:
        AgeExposureError: for an unknown rule.
    """

    if rule not in ALLOCATION_RULES:
        raise AgeExposureError(f"unknown allocation rule: {rule}")
    residents: list[float] = []
    children: list[float] = []
    older: list[float] = []
    for cell in cells:
        weight = _weight(cell, rule)
        if not cell.supported or weight <= 0:
            continue
        residents.append(weight * cell.residents)
        children.append(weight * cell.children_0_14)
        older.append(weight * cell.older_60_plus)
    total = math.fsum(residents)
    young = math.fsum(children)
    old = math.fsum(older)
    return {
        "rule": rule,
        "cells_used": len(residents),
        "residents": total,
        "children_0_14": young,
        "older_60_plus": old,
        "other_15_59": max(0.0, total - young - old),
        "dependent_share": dependent_share(young, old, total) if total > 0 else None,
    }


def allocation_range(cells: Sequence[AgeCell]) -> dict[str, Any]:
    """Return the low/high range of the dependent share over the three allocations.

    The plan gives no formula for a range that reflects the 1 km allocation.
    This one re-allocates the same cells two other ways: only the cells wholly
    inside the unit, and every cell that touches the unit counted in full. Low
    and high are the smallest and the largest of the three shares, so the
    value of record always lies inside the range.

    Returns:
        ``low``, ``high``, the share and the cell and resident counts of each
        allocation, and ``value_of_record_between_the_two_extremes``. Low and
        high are ``None`` when the value of record is unavailable.
    """

    central = allocate_cells(cells, PROJECTED_AREA_FRACTION)
    inside = allocate_cells(cells, CELLS_WHOLLY_INSIDE)
    touching = allocate_cells(cells, CELLS_ANY_TOUCHING)
    shares = [row["dependent_share"] for row in (central, inside, touching) if row["dependent_share"] is not None]
    extremes = [row["dependent_share"] for row in (inside, touching) if row["dependent_share"] is not None]
    value = central["dependent_share"]
    between = None
    if value is not None and len(extremes) == 2:
        between = min(extremes) <= value <= max(extremes)
    return {
        "low": min(shares) if value is not None else None,
        "high": max(shares) if value is not None else None,
        PROJECTED_AREA_FRACTION: value,
        CELLS_WHOLLY_INSIDE: {
            "cells": inside["cells_used"], "residents": inside["residents"],
            "dependent_share": inside["dependent_share"],
        },
        CELLS_ANY_TOUCHING: {
            "cells": touching["cells_used"], "residents": touching["residents"],
            "dependent_share": touching["dependent_share"],
        },
        "extremes_available": len(extremes),
        "value_of_record_between_the_two_extremes": between,
    }


def area_outside_grid_km2(geometry: Any, source: rasterio.io.DatasetReader) -> float:
    """Return the projected area (EPSG:32647) of a unit that lies outside the age grid's extent."""

    outside = geometry.difference(box(*source.bounds))
    if outside.is_empty:
        return 0.0
    projector = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
    return transform(projector, outside).area / 1e6


def support_summary(cells: Sequence[AgeCell], unit_area_km2: float, outside_grid_km2: float = 0.0) -> dict[str, Any]:
    """Count a unit's age cells and measure the area the age grid supports.

    Args:
        cells: The cells that overlap the unit.
        unit_area_km2: The unit's projected area (EPSG:32647) in square kilometres.
        outside_grid_km2: The part of that area outside the age grid's extent.

    Returns:
        ``age_cells`` (cell counts) and ``area`` (square kilometres and
        shares of the unit's area). The unsupported area is the area in cells
        with no valid count plus the area outside the grid.
        ``reconciliation_residual_km2`` is the unit's area minus the supported
        and the unsupported area: cell edges are projected as straight lines,
        so it is close to zero and not exactly zero.

    Raises:
        AgeExposureError: when an area is not a usable number.
    """

    if isinstance(unit_area_km2, bool) or not math.isfinite(unit_area_km2) or unit_area_km2 <= 0:
        raise AgeExposureError("the unit area must be a positive number")
    if isinstance(outside_grid_km2, bool) or not math.isfinite(outside_grid_km2) or outside_grid_km2 < 0:
        raise AgeExposureError("the area outside the grid must be a number that is not negative")
    supported = [cell for cell in cells if cell.supported]
    unsupported = [cell for cell in cells if not cell.supported]
    supported_km2 = math.fsum(cell.covered_m2 for cell in supported) / 1e6
    in_invalid_cells_km2 = math.fsum(cell.covered_m2 for cell in unsupported) / 1e6
    unsupported_km2 = in_invalid_cells_km2 + outside_grid_km2
    return {
        "age_cells": {
            "with_valid_counts": len(supported),
            "wholly_inside": sum(1 for cell in supported if cell.wholly_inside),
            "partly_inside": sum(1 for cell in supported if not cell.wholly_inside),
            "without_valid_counts": len(unsupported),
            "cell_equivalents": math.fsum(cell.fraction for cell in supported),
        },
        "area": {
            "unit_km2": unit_area_km2,
            "supported_km2": supported_km2,
            "unsupported_km2": unsupported_km2,
            "supported_fraction": min(1.0, supported_km2 / unit_area_km2),
            "unsupported_fraction": min(1.0, unsupported_km2 / unit_area_km2),
            "unsupported_in_cells_without_valid_counts_km2": in_invalid_cells_km2,
            "unsupported_outside_the_age_grid_km2": outside_grid_km2,
            "reconciliation_residual_km2": unit_area_km2 - supported_km2 - unsupported_km2,
        },
    }


def _same(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=_RELATIVE_TOLERANCE, abs_tol=_ABSOLUTE_TOLERANCE)


def unit_age_exposure(geometry: Any, rasters: Mapping[str, rasterio.io.DatasetReader]) -> dict[str, Any]:
    """Compute one unit's dependent share with its cells, supported area and range.

    The counts of record are those of
    :func:`floodguard.evidence_age_surface.summarize_geometry`, the function
    behind the national anchors. The cell table is a second computation of the
    same sums; the two must agree.

    Args:
        geometry: The unit polygon in EPSG:4326, valid and not empty.
        rasters: The 20 open WorldPop age rasters, keyed by band.

    Returns:
        ``status``, the four counts, ``dependent_share`` (``None`` with a
        reason when the unit has no valid age cell or no resident),
        ``allocation_range``, ``age_cells``, ``area`` and
        ``band_mask_mismatch``.

    Raises:
        ValueError: for a bad geometry or rasters on different grids.
        AgeExposureError: when the two computations disagree.
    """

    summary = summarize_geometry(geometry, rasters)
    cells = read_unit_cells(geometry, rasters)
    support = support_summary(
        cells, summary["geometry_area_km2"], area_outside_grid_km2(geometry, rasters[AGE_BANDS[0]]))
    if not _same(support["area"]["supported_km2"], summary["source_supported_area_km2"]):
        raise AgeExposureError("the cell table and the anchors' function disagree on the supported area")
    record: dict[str, Any] = {
        "status": summary["status"],
        "residents": summary["population_estimate"],
        "children_0_14": summary["children_0_14_estimate"],
        "older_60_plus": summary["older_60_plus_estimate"],
        "other_15_59": summary["other_15_59_estimate"],
        "dependent_share": None,
        "dependent_share_unavailable_reason": None,
    }
    if summary["population_estimate"] is None:
        record["dependent_share_unavailable_reason"] = "no_valid_age_cell"
    else:
        central = allocate_cells(cells, PROJECTED_AREA_FRACTION)
        pairs = (("residents", "population_estimate"), ("children_0_14", "children_0_14_estimate"),
                 ("older_60_plus", "older_60_plus_estimate"))
        if any(not _same(central[mine], summary[theirs]) for mine, theirs in pairs):
            raise AgeExposureError("the cell table and the anchors' function disagree on the counts")
        if summary["population_estimate"] > 0:
            record["dependent_share"] = dependent_share(
                summary["children_0_14_estimate"], summary["older_60_plus_estimate"], summary["population_estimate"])
        else:
            record["dependent_share_unavailable_reason"] = "no_residents"
    spread = allocation_range(cells)
    if record["dependent_share"] is not None:
        # The value of record is the anchors' computation; keep the range around that exact number.
        spread[PROJECTED_AREA_FRACTION] = record["dependent_share"]
        spread["low"] = min(spread["low"], record["dependent_share"])
        spread["high"] = max(spread["high"], record["dependent_share"])
    else:
        spread["low"] = spread["high"] = spread[PROJECTED_AREA_FRACTION] = None
    record["allocation_range"] = spread
    record["age_cells"] = support["age_cells"]
    record["area"] = support["area"]
    record["band_mask_mismatch"] = summary["band_mask_mismatch"]
    return record


def age_exposure_table(
    units: Iterable[tuple[str, Any]],
    raster_paths: Mapping[str, Path],
) -> list[dict[str, Any]]:
    """Compute :func:`unit_age_exposure` for several units, sorted by unit identifier.

    Args:
        units: Pairs of unit identifier and polygon (EPSG:4326).
        raster_paths: The 20 age rasters, keyed by band.

    Raises:
        AgeExposureError: for a missing band or a repeated or empty identifier.
    """

    if set(raster_paths) != set(AGE_BANDS):
        raise AgeExposureError("exactly the 20 age bands are required")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with ExitStack() as stack:
        rasters = {band: stack.enter_context(rasterio.open(raster_paths[band])) for band in AGE_BANDS}
        for unit_id, geometry in units:
            unit_id = str(unit_id)
            if not unit_id or unit_id in seen:
                raise AgeExposureError("unit identifiers must be present and unique")
            seen.add(unit_id)
            rows.append({"unit_id": unit_id, **unit_age_exposure(geometry, rasters)})
    rows.sort(key=lambda row: row["unit_id"])
    return rows


def rescale_2020_counts_to_2024(
    counts_2020: Any,
    cell_ids: Any,
    totals_2024: Mapping[int, float | None],
) -> dict[str, Any]:
    """Rescale 2020 100 m counts to the 2024 totals of their 1 km cells (protocol v1b, owner choice 12).

    The rule, from ``ensemble_grid.core_axes[population_vintage].rescale_formula``:
    within each 1 km cell of the WorldPop 2024 grid, multiply every 2020 100 m
    count by the ratio of the cell's 2024 total (the sum of the 20 age bands)
    to the sum of the 2020 100 m counts inside the cell. A cell whose 2020 sum
    is zero keeps zero, and the 2024 residents it leaves out are reported as
    unallocated.

    The rule is silent on two points. This function decides neither:

    * which 1 km cell a 100 m count is "inside". The caller says so through
      ``cell_ids``; on the Thai grids the 100 m cells do not nest in the 1 km
      cells.
    * what a positive count becomes when its 1 km cell has no valid 2024
      total. Such a count is returned as ``nan`` and reported under
      ``without_2024_total``, and ``complete`` is false. A zero count stays
      zero: no ratio changes it.

    Args:
        counts_2020: The 2020 100 m counts, finite and not negative, any shape.
        cell_ids: The integer identifier of the 1 km cell each count is inside;
            same shape as ``counts_2020``.
        totals_2024: The 2024 total of every 1 km cell in scope, or ``None``
            for a cell with no valid total. A cell listed here that holds no
            2020 count has a 2020 sum of zero.

    Returns:
        ``rescaled_counts`` (an array of the input shape), ``ratio_by_cell``,
        ``residents_2020``, ``residents_2024_rescaled``,
        ``unallocated_2024_residents``, ``cells_with_zero_2020_sum``,
        ``without_2024_total`` and ``complete``.

    Raises:
        AgeExposureError: for counts or totals that are not finite or are
            negative, shapes that differ, identifiers that are not integers,
            or a count whose cell is missing from ``totals_2024``.
    """

    counts = np.asarray(counts_2020, dtype="float64")
    cells = np.asarray(cell_ids)
    if counts.shape != cells.shape:
        raise AgeExposureError("counts_2020 and cell_ids must have the same shape")
    if cells.size and cells.dtype.kind not in "iu":
        raise AgeExposureError("cell_ids must be integers")
    if not np.all(np.isfinite(counts)) or np.any(counts < 0):
        raise AgeExposureError("2020 counts must be finite and not negative")
    totals: dict[int, float | None] = {}
    for cell, total in totals_2024.items():
        if isinstance(cell, bool) or not isinstance(cell, (int, np.integer)):
            raise AgeExposureError("the keys of totals_2024 must be integers")
        if total is not None and (isinstance(total, bool) or not math.isfinite(total) or total < 0):
            raise AgeExposureError("a 2024 total must be finite and not negative, or None")
        totals[int(cell)] = None if total is None else float(total)

    flat_counts = counts.ravel()
    unique, inverse = np.unique(cells.ravel(), return_inverse=True)
    inverse = inverse.ravel()
    sums = np.bincount(inverse, weights=flat_counts, minlength=len(unique))
    missing = [int(cell) for cell in unique.tolist() if int(cell) not in totals]
    if missing:
        raise AgeExposureError(f"{len(missing)} cell(s) hold a 2020 count but are missing from totals_2024")

    factors = np.ones(len(unique), dtype="float64")
    ratio_by_cell: dict[int, float | None] = {}
    sum_by_cell: dict[int, float] = {}
    unresolved_cells: list[int] = []
    for index, cell in enumerate(unique.tolist()):
        cell = int(cell)
        sum_2020 = float(sums[index])
        sum_by_cell[cell] = sum_2020
        total = totals[cell]
        if sum_2020 == 0:
            ratio_by_cell[cell] = None  # keeps zero; any 2024 residents are unallocated
        elif total is None:
            ratio_by_cell[cell] = None
            factors[index] = np.nan
            unresolved_cells.append(cell)
        else:
            ratio_by_cell[cell] = total / sum_2020
            factors[index] = total / sum_2020
    with np.errstate(invalid="ignore"):
        flat_rescaled = np.where(flat_counts == 0, 0.0, flat_counts * factors[inverse])
    unresolved = np.isnan(flat_rescaled)

    zero_sum_cells = sorted(cell for cell in totals if sum_by_cell.get(cell, 0.0) == 0)
    for cell in zero_sum_cells:
        ratio_by_cell.setdefault(cell, None)
    unallocated = math.fsum(totals[cell] for cell in zero_sum_cells if totals[cell] is not None)
    return {
        "rescaled_counts": flat_rescaled.reshape(counts.shape),
        "ratio_by_cell": dict(sorted(ratio_by_cell.items())),
        "residents_2020": math.fsum(flat_counts.tolist()),
        "residents_2024_rescaled": math.fsum(flat_rescaled[~unresolved].tolist()),
        "unallocated_2024_residents": unallocated,
        "cells_with_zero_2020_sum": zero_sum_cells,
        "without_2024_total": {
            "cells": sorted(unresolved_cells),
            "counts": int(unresolved.sum()),
            "residents_2020": math.fsum(flat_counts[unresolved].tolist()),
            "note": "Protocol v1b gives no rule for a positive 2020 count whose 1 km cell has no valid 2024 "
                    "total. These counts are not rescaled (nan).",
        },
        "complete": not unresolved_cells,
    }
