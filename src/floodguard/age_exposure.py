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
* the share under two other allocations of the same cells, with the smallest
  and the largest of the three (three allocations, not a bound on the error);
* the cells that lie partly outside every unit of the boundary layer, and how
  much of the share rests on them (reading DR-B04 is silent on such cells);
* a reading of the age grid itself: how many cells carry the same age
  composition; and
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
from rasterio.windows import Window
from rasterio.windows import bounds as window_bounds
from rasterio.windows import transform as window_transform
from shapely.geometry import box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

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

# A cell counts as inside the boundary layer when the layer's units together cover this share of its projected
# area. The cover is built from several polygons, each projected on its own: an edge two units share becomes two
# chords that can lie millimetres to centimetres apart, which leaves slivers of a few square metres. One
# ten-thousandth of a 1 km cell is about 85 square metres: wider than those slivers, and far less than any part
# of a cell that would move a count. It is a parameter of a description, not a rule of the protocol.
IN_LAYER_MIN_FRACTION = 1.0 - 1e-4

# Parameters of the reading of the age grid (composition_reading and share_clusters). They describe the input;
# no rule of the protocol uses them.
SHARE_GROUP_DECIMALS = 6
SHARE_GROUP_MIN_CELLS = 20
SHARE_CLUSTER_GAP = 1e-4

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
    "Low and high are the smallest and the largest dependent share under three allocations of the same cells: "
    "the projected-area fraction (the value of record), only the cells wholly inside the unit, and every cell "
    "that touches the unit counted in full. They are three allocations, not a bound on the allocation error: "
    "another allocation can give a share outside them. Where the cells around a unit carry the same age "
    "composition the three agree, so a narrow range does not show that the share is precise. It is not a "
    "confidence interval and it does not cover the error of the modelled age counts."
)
AGE_CELLS_STATEMENT = (
    "The number of distinct 1 km cells of the age grid that overlap the unit and carry a valid count in all "
    "20 age bands. A cell on the unit's edge counts once, whatever share of it is inside."
)
BORDER_CELLS_STATEMENT = (
    "A valid cell lies partly outside every unit when the units of the boundary layer together cover less than "
    "the whole of its projected area (EPSG:32647): for a unit on the national border, a cell that straddles the "
    "border. Under the allocation of record the unit takes such a cell's counts by its area share like any other "
    "cell, the part of the cell's count that falls outside the layer goes to no unit, and the cell's age "
    "composition is that of the whole cell, which may include residents who live outside the layer. Reading "
    "DR-B04 does not say how such a cell is treated; nothing is adjusted here."
)
GRID_READING_STATEMENT = (
    "A reading of the input age grid, not of any unit. Populated cells are grouped by their dependent share "
    "rounded to a stated number of decimal places; a group counts when it holds at least a stated number of "
    "cells. In the window of the frame the shares are also sorted and cut into clusters wherever two "
    "neighbouring shares differ by more than a stated gap."
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
        layer_fraction: Share of the cell's projected area that lies inside any
            unit of the boundary layer, or ``None`` when it was not measured.
    """

    raster_row: int
    raster_col: int
    fraction: float
    covered_m2: float
    residents: float | None
    children_0_14: float | None
    older_60_plus: float | None
    layer_fraction: float | None = None

    @property
    def supported(self) -> bool:
        """Say whether all 20 age bands carry a valid count in this cell."""

        return self.residents is not None

    @property
    def wholly_inside(self) -> bool:
        """Say whether the unit covers the whole cell."""

        return self.fraction >= WHOLLY_INSIDE_MIN_FRACTION

    @property
    def cell_m2(self) -> float:
        """Return the projected area of the whole cell in square metres."""

        return self.covered_m2 / self.fraction

    @property
    def partly_outside_every_unit(self) -> bool | None:
        """Say whether part of the cell lies in no unit of the boundary layer; ``None`` when not measured."""

        if self.layer_fraction is None:
            return None
        return self.layer_fraction < IN_LAYER_MIN_FRACTION


class UnitLayer:
    """Every unit polygon of a boundary layer, to measure how much of a cell lies inside any unit.

    Args:
        geometries: The polygons of all units of the layer, in EPSG:4326 and valid.

    Raises:
        AgeExposureError: when the layer holds no unit.
    """

    def __init__(self, geometries: Iterable[Any]) -> None:
        self._geometries = list(geometries)
        if not self._geometries:
            raise AgeExposureError("a boundary layer needs at least one unit")
        self._tree = STRtree(self._geometries)
        self._projector = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
        self._projected: dict[int, Any] = {}

    def __len__(self) -> int:
        return len(self._geometries)

    def fraction_inside(self, cell: Any) -> float:
        """Return the share of a cell's projected area (EPSG:32647) that lies inside any unit of the layer.

        Args:
            cell: The cell as a box in EPSG:4326.
        """

        pixel = transform(self._projector, cell)
        pieces = []
        for index in sorted(int(found) for found in self._tree.query(cell, predicate="intersects")):
            if index not in self._projected:
                self._projected[index] = transform(self._projector, self._geometries[index])
            piece = self._projected[index].intersection(pixel)
            if not piece.is_empty and piece.area > 0:
                pieces.append(piece)
        if not pieces:
            return 0.0
        return min(1.0, unary_union(pieces).area / pixel.area)


def read_unit_cells(geometry: Any, rasters: Mapping[str, rasterio.io.DatasetReader],
                    layer: UnitLayer | None = None) -> list[AgeCell]:
    """List the 1 km age cells that overlap a unit, with the overlap and the whole-cell counts.

    The overlap comes from the same routine the national anchors used
    (``floodguard.evidence_age_surface._coverage``), so the fractions here are
    the fractions behind :func:`summarize_geometry`.

    Args:
        geometry: The unit polygon in EPSG:4326.
        rasters: The 20 open age rasters, keyed by band.
        layer: Every unit of the boundary layer. When given, each cell with a
            valid count also carries the share of its area inside any unit.

    Raises:
        ValueError: when the geometry does not meet the age grid.
    """

    if set(rasters) != set(AGE_BANDS):
        raise AgeExposureError("exactly the 20 age bands are required")
    window, fractions, covered_m2 = _coverage(geometry, rasters[AGE_BANDS[0]])
    affine = window_transform(window, rasters[AGE_BANDS[0]].transform)
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
        residents = children = older = in_layer = None
        fraction = float(fractions[row, col])
        if shared[row, col]:
            residents = math.fsum(float(values[band][row, col]) for band in AGE_BANDS)
            children = math.fsum(float(values[band][row, col]) for band in CHILD_BANDS)
            older = math.fsum(float(values[band][row, col]) for band in OLDER_BANDS)
            if layer is not None:
                if fraction >= WHOLLY_INSIDE_MIN_FRACTION:
                    in_layer = 1.0  # the unit itself covers the cell
                else:
                    # The same cell box as in ``_coverage``.
                    x0, y0 = affine * (col, row)
                    x1, y1 = affine * (col + 1, row + 1)
                    cell = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                    in_layer = max(fraction, layer.fraction_inside(cell))
        cells.append(AgeCell(
            raster_row=int(window.row_off) + row,
            raster_col=int(window.col_off) + col,
            fraction=fraction,
            covered_m2=float(covered_m2[row, col]),
            residents=residents,
            children_0_14=children,
            older_60_plus=older,
            layer_fraction=in_layer,
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
    """Return the dependent share under three allocations of the same cells, with the smallest and the largest.

    The plan gives no formula for a range that reflects the 1 km allocation.
    This one re-allocates the same cells two other ways: only the cells wholly
    inside the unit, and every cell that touches the unit counted in full. Low
    and high are the smallest and the largest of the three shares, so the
    value of record always lies between them. They are three allocations, not
    a bound: the value of record can lie outside the two other allocations,
    and a fourth allocation can give a share outside low and high.

    Returns:
        ``low``, ``high``, the share and the cell and resident counts of each
        allocation, and ``value_of_record_between_the_two_other_allocations``.
        Low and high are ``None`` when the value of record is unavailable.
    """

    central = allocate_cells(cells, PROJECTED_AREA_FRACTION)
    inside = allocate_cells(cells, CELLS_WHOLLY_INSIDE)
    touching = allocate_cells(cells, CELLS_ANY_TOUCHING)
    shares = [row["dependent_share"] for row in (central, inside, touching) if row["dependent_share"] is not None]
    others = [row["dependent_share"] for row in (inside, touching) if row["dependent_share"] is not None]
    value = central["dependent_share"]
    between = None
    if value is not None and len(others) == 2:
        between = min(others) <= value <= max(others)
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
        "other_allocations_available": len(others),
        "value_of_record_between_the_two_other_allocations": between,
    }


_BORDER_KEYS = (
    "cells", "residents_the_unit_takes_from_them", "share_of_the_units_residents",
    "dependent_share_of_what_the_unit_takes_from_them", "residents_from_the_other_cells",
    "dependent_share_from_the_other_cells", "residents_of_those_cells_in_no_unit",
    "area_of_those_cells_in_no_unit_km2",
)
_FRAME_BORDER_KEYS = (
    "distinct_cells", "residents_in_those_cells", "residents_the_frames_units_take_from_them",
    "residents_of_those_cells_in_no_unit", "area_of_those_cells_in_no_unit_km2",
)
# What is reported when the cells were read without the boundary layer: nothing is guessed.
_BORDER_CELLS_NOT_MEASURED: dict[str, Any] = {"measured": False, **{key: None for key in _BORDER_KEYS}}
_FRAME_BORDER_CELLS_NOT_MEASURED: dict[str, Any] = {"measured": False, **{key: None for key in _FRAME_BORDER_KEYS}}


def border_cell_summary(cells: Sequence[AgeCell]) -> dict[str, Any]:
    """Describe the valid cells of a unit that lie partly outside every unit of the boundary layer.

    Reading DR-B04 allocates a cell's counts by area and is silent on a cell
    that no set of units covers in full (a cell that straddles the national
    border, or the coast). This function changes no allocation. It splits the
    counts of record into the part the unit takes from such cells and the part
    it takes from all other cells, and adds the part of those cells' counts
    that goes to no unit.

    Args:
        cells: The cells that overlap the unit, read with a :class:`UnitLayer`.

    Returns:
        ``measured`` (false, with every figure ``None``, when the cells were
        read without a layer), the number of such cells, the residents the unit
        takes from them and from the other cells with the dependent share of
        each part, and the residents and the area of those cells in no unit.
    """

    supported = [cell for cell in cells if cell.supported]
    if any(cell.layer_fraction is None for cell in supported):
        return dict(_BORDER_CELLS_NOT_MEASURED)
    border = [cell for cell in supported if cell.partly_outside_every_unit]
    rest = [cell for cell in supported if not cell.partly_outside_every_unit]
    taken = allocate_cells(border, PROJECTED_AREA_FRACTION)
    other = allocate_cells(rest, PROJECTED_AREA_FRACTION)
    total = taken["residents"] + other["residents"]
    return {
        "measured": True,
        "cells": len(border),
        "residents_the_unit_takes_from_them": taken["residents"],
        "share_of_the_units_residents": taken["residents"] / total if total > 0 else None,
        "dependent_share_of_what_the_unit_takes_from_them": taken["dependent_share"],
        "residents_from_the_other_cells": other["residents"],
        "dependent_share_from_the_other_cells": other["dependent_share"],
        "residents_of_those_cells_in_no_unit": math.fsum(
            (1.0 - cell.layer_fraction) * cell.residents for cell in border),
        "area_of_those_cells_in_no_unit_km2": math.fsum(
            (1.0 - cell.layer_fraction) * cell.cell_m2 for cell in border) / 1e6,
    }


def frame_border_cells(cells_by_unit: Mapping[str, Sequence[AgeCell]]) -> dict[str, Any]:
    """Count once every cell that lies partly outside every unit, over all units of a frame.

    A border cell can overlap two units of the frame, so the per-unit figures
    of :func:`border_cell_summary` cannot be added up. This function counts
    each cell once.

    Returns:
        ``measured``, the number of distinct cells, their whole-cell residents,
        the residents the frame's units take from them, and the residents and
        the area of those cells in no unit of the boundary layer.
    """

    distinct: dict[tuple[int, int], AgeCell] = {}
    taken: list[float] = []
    for cells in cells_by_unit.values():
        for cell in cells:
            if not cell.supported:
                continue
            if cell.layer_fraction is None:
                return dict(_FRAME_BORDER_CELLS_NOT_MEASURED)
            if cell.partly_outside_every_unit:
                # A cell read for two units carries the same counts and the same cover of the layer.
                distinct.setdefault((cell.raster_row, cell.raster_col), cell)
                taken.append(cell.fraction * cell.residents)
    found = [distinct[key] for key in sorted(distinct)]
    return {
        "measured": True,
        "distinct_cells": len(found),
        "residents_in_those_cells": math.fsum(cell.residents for cell in found),
        "residents_the_frames_units_take_from_them": math.fsum(taken),
        "residents_of_those_cells_in_no_unit": math.fsum(
            (1.0 - cell.layer_fraction) * cell.residents for cell in found),
        "area_of_those_cells_in_no_unit_km2": math.fsum(
            (1.0 - cell.layer_fraction) * cell.cell_m2 for cell in found) / 1e6,
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


def unit_age_exposure(geometry: Any, rasters: Mapping[str, rasterio.io.DatasetReader], *,
                      layer: UnitLayer | None = None) -> dict[str, Any]:
    """Compute one unit's dependent share with its cells, supported area and range.

    The counts of record are those of
    :func:`floodguard.evidence_age_surface.summarize_geometry`, the function
    behind the national anchors. The cell table is a second computation of the
    same sums; the two must agree.

    Args:
        geometry: The unit polygon in EPSG:4326, valid and not empty.
        rasters: The 20 open WorldPop age rasters, keyed by band.
        layer: Every unit of the boundary layer, to find the cells that lie
            partly outside every unit. Without it those cells are not measured.

    Returns:
        ``status``, the four counts, ``dependent_share`` (``None`` with a
        reason when the unit has no valid age cell or no resident),
        ``allocation_range``, ``cells_partly_outside_every_unit``,
        ``age_cells``, ``area`` and ``band_mask_mismatch``.

    Raises:
        ValueError: for a bad geometry or rasters on different grids.
        AgeExposureError: when the two computations disagree.
    """

    return _unit_record(geometry, rasters, layer)[0]


def _unit_record(geometry: Any, rasters: Mapping[str, rasterio.io.DatasetReader],
                 layer: UnitLayer | None) -> tuple[dict[str, Any], list[AgeCell]]:
    """Return a unit's record (see :func:`unit_age_exposure`) and the cells it was computed from."""

    summary = summarize_geometry(geometry, rasters)
    cells = read_unit_cells(geometry, rasters, layer)
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
    record["cells_partly_outside_every_unit"] = (
        border_cell_summary(cells) if layer is not None else dict(_BORDER_CELLS_NOT_MEASURED))
    record["age_cells"] = support["age_cells"]
    record["area"] = support["area"]
    record["band_mask_mismatch"] = summary["band_mask_mismatch"]
    return record, cells


def age_exposure_table(
    units: Iterable[tuple[str, Any]],
    raster_paths: Mapping[str, Path],
    *,
    layer_units: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Compute :func:`unit_age_exposure` for several units, sorted by unit identifier.

    Args:
        units: Pairs of unit identifier and polygon (EPSG:4326).
        raster_paths: The 20 age rasters, keyed by band.
        layer_units: The polygons of every unit of the boundary layer; see
            :func:`age_exposure_frame`.

    Raises:
        AgeExposureError: for a missing band or a repeated or empty identifier.
    """

    return age_exposure_frame(units, raster_paths, layer_units=layer_units, grid_reading=False)["units"]


def age_exposure_frame(
    units: Iterable[tuple[str, Any]],
    raster_paths: Mapping[str, Path],
    *,
    layer_units: Iterable[Any] | None = None,
    grid_reading: bool = True,
) -> dict[str, Any]:
    """Compute the unit rows of a frame, its border cells counted once, and a reading of the age grid.

    Args:
        units: Pairs of unit identifier and polygon (EPSG:4326): the units of the frame.
        raster_paths: The 20 age rasters, keyed by band.
        layer_units: The polygons of every unit of the boundary layer (the
            frame's units among them). When given, the cells that lie partly
            outside every unit are measured; otherwise they are marked as not
            measured.
        grid_reading: Whether to read the composition of the age grid
            (:func:`age_grid_reading`); it reads every cell of the 20 rasters.

    Returns:
        ``units`` (one row per unit, sorted by identifier),
        ``border_cells`` (:func:`frame_border_cells`) and ``age_grid_reading``
        (``None`` when not asked for).

    Raises:
        AgeExposureError: for a missing band, a repeated or empty identifier,
            or an empty boundary layer.
    """

    if set(raster_paths) != set(AGE_BANDS):
        raise AgeExposureError("exactly the 20 age bands are required")
    layer = UnitLayer(layer_units) if layer_units is not None else None
    rows: list[dict[str, Any]] = []
    cells_by_unit: dict[str, list[AgeCell]] = {}
    with ExitStack() as stack:
        rasters = {band: stack.enter_context(rasterio.open(raster_paths[band])) for band in AGE_BANDS}
        for unit_id, geometry in units:
            unit_id = str(unit_id)
            if not unit_id or unit_id in cells_by_unit:
                raise AgeExposureError("unit identifiers must be present and unique")
            record, cells = _unit_record(geometry, rasters, layer)
            cells_by_unit[unit_id] = cells
            rows.append({"unit_id": unit_id, **record})
        reading = age_grid_reading(rasters, frame_window(cells_by_unit)) if grid_reading else None
    rows.sort(key=lambda row: row["unit_id"])
    border = frame_border_cells(cells_by_unit) if layer is not None else dict(_FRAME_BORDER_CELLS_NOT_MEASURED)
    return {"units": rows, "border_cells": border, "age_grid_reading": reading}


def frame_window(cells_by_unit: Mapping[str, Sequence[AgeCell]]) -> Window:
    """Return the smallest window of the age grid that holds every cell overlapping a unit of the frame."""

    rows = [cell.raster_row for cells in cells_by_unit.values() for cell in cells]
    cols = [cell.raster_col for cells in cells_by_unit.values() for cell in cells]
    if not rows:
        raise AgeExposureError("the frame overlaps no cell of the age grid")
    return Window(min(cols), min(rows), max(cols) - min(cols) + 1, max(rows) - min(rows) + 1)


def read_grid_counts(rasters: Mapping[str, rasterio.io.DatasetReader],
                     window: Window | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read the residents and the dependants of every cell of the age grid, or of one window of it.

    Returns:
        Three arrays of the window's shape: residents (the sum of the 20
        bands), dependants (ages 0-14 plus 60 and over) and a mask that is
        true where all 20 bands carry a valid count. Residents and dependants
        are zero where the mask is false.
    """

    if set(rasters) != set(AGE_BANDS):
        raise AgeExposureError("exactly the 20 age bands are required")
    residents: np.ndarray | None = None
    dependants: np.ndarray | None = None
    shared: np.ndarray | None = None
    for band in AGE_BANDS:
        array = rasters[band].read(1, window=window, masked=True)
        data = np.asarray(array.data, dtype="float64")
        valid = ~np.ma.getmaskarray(array) & np.isfinite(data) & (data >= 0)
        clean = np.where(valid, data, 0.0)
        if residents is None or dependants is None or shared is None:
            residents, dependants, shared = np.zeros(clean.shape), np.zeros(clean.shape), valid
        shared = shared & valid
        residents += clean
        if band in CHILD_BANDS or band in OLDER_BANDS:
            dependants += clean
    assert residents is not None and dependants is not None and shared is not None
    # A cell that lacks any band carries no count at all, as in the allocation of record.
    residents[~shared] = 0.0
    dependants[~shared] = 0.0
    return residents, dependants, shared


def composition_reading(residents: Any, dependants: Any, valid: Any, *,
                        decimals: int = SHARE_GROUP_DECIMALS,
                        min_cells: int = SHARE_GROUP_MIN_CELLS) -> dict[str, Any]:
    """Count the cells of a grid, and how many of them share a dependent share with many other cells.

    Populated cells are grouped by their dependent share rounded to
    ``decimals`` places. A group counts when it holds at least ``min_cells``
    cells. Many cells in few groups means the grid carries one age composition
    over many cells, so neighbouring units get nearly the same share whatever
    the allocation.

    Args:
        residents: Residents of each cell.
        dependants: Residents aged 0-14 plus 60 and over of each cell.
        valid: True where the cell carries a valid count in every band.
        decimals: Decimal places the share is rounded to before grouping.
        min_cells: The smallest group that counts.

    Returns:
        Cell counts (all, valid, not valid, valid with zero residents,
        populated), the residents, the dependent share of all residents, and
        ``same_share_groups``: the number of groups that count, their cells and
        residents, and those cells as a share of the populated cells.

    Raises:
        AgeExposureError: for arrays of different shapes or parameters out of range.
    """

    total = np.asarray(residents, dtype="float64")
    dependent = np.asarray(dependants, dtype="float64")
    mask = np.asarray(valid, dtype=bool)
    if not total.shape == dependent.shape == mask.shape:
        raise AgeExposureError("residents, dependants and valid must have the same shape")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 12:
        raise AgeExposureError("decimals must be an integer from 0 to 12")
    if isinstance(min_cells, bool) or not isinstance(min_cells, int) or min_cells < 1:
        raise AgeExposureError("min_cells must be a positive integer")
    populated = mask & (total > 0)
    counts = total[populated]
    shares = dependent[populated] / counts
    groups = cells = 0
    in_groups = 0.0
    if counts.size:
        _values, inverse, sizes = np.unique(np.round(shares, decimals), return_inverse=True, return_counts=True)
        by_group = np.bincount(inverse.ravel(), weights=counts, minlength=len(sizes))
        large = sizes >= min_cells
        groups, cells, in_groups = int(large.sum()), int(sizes[large].sum()), float(by_group[large].sum())
    everyone = math.fsum(counts.tolist())
    return {
        "cells": int(mask.size),
        "cells_with_valid_counts": int(mask.sum()),
        "cells_without_valid_counts": int(mask.size - mask.sum()),
        "valid_cells_with_zero_residents": int((mask & (total == 0)).sum()),
        "populated_cells": int(populated.sum()),
        "residents": everyone,
        "dependent_share_of_all_residents": math.fsum(dependent[populated].tolist()) / everyone if everyone > 0 else None,
        "same_share_groups": {
            "decimals": decimals,
            "min_cells": min_cells,
            "groups": groups,
            "cells": cells,
            "residents": in_groups,
            "share_of_populated_cells": cells / int(populated.sum()) if populated.any() else None,
        },
    }


def share_clusters(shares: Any, residents: Any, *, gap: float = SHARE_CLUSTER_GAP,
                   min_cells: int = SHARE_GROUP_MIN_CELLS) -> dict[str, Any]:
    """Sort cells by dependent share and cut them into clusters wherever two neighbours differ by more than ``gap``.

    Args:
        shares: The dependent share of each populated cell.
        residents: The residents of each of those cells.
        gap: Two neighbouring shares further apart than this start a new cluster.
        min_cells: Clusters with at least this many cells are listed; the rest are summed.

    Returns:
        ``gap``, ``min_cells``, ``clusters`` (lowest and highest share, cells
        and residents of each listed cluster, largest first) and
        ``smaller_clusters`` (their number, cells, residents and the lowest
        and highest share among them).

    Raises:
        AgeExposureError: for inputs of different lengths or parameters out of range.
    """

    values = np.asarray(shares, dtype="float64").ravel()
    counts = np.asarray(residents, dtype="float64").ravel()
    if values.shape != counts.shape:
        raise AgeExposureError("shares and residents must have the same length")
    if isinstance(gap, bool) or not math.isfinite(gap) or gap <= 0:
        raise AgeExposureError("gap must be a positive number")
    if isinstance(min_cells, bool) or not isinstance(min_cells, int) or min_cells < 1:
        raise AgeExposureError("min_cells must be a positive integer")
    order = np.argsort(values, kind="stable")
    values, counts = values[order], counts[order]
    starts = [0, *(np.nonzero(np.diff(values) > gap)[0] + 1).tolist(), len(values)] if len(values) else [0]
    listed: list[dict[str, Any]] = []
    small: list[dict[str, Any]] = []
    for first, last in zip(starts[:-1], starts[1:]):
        cluster = {
            "lowest_share": float(values[first]), "highest_share": float(values[last - 1]),
            "cells": int(last - first), "residents": math.fsum(counts[first:last].tolist()),
        }
        (listed if cluster["cells"] >= min_cells else small).append(cluster)
    listed.sort(key=lambda cluster: (-cluster["cells"], cluster["lowest_share"]))
    return {
        "gap": gap,
        "min_cells": min_cells,
        "clusters": listed,
        "smaller_clusters": {
            "clusters": len(small),
            "cells": sum(cluster["cells"] for cluster in small),
            "residents": math.fsum(cluster["residents"] for cluster in small),
            "lowest_share": min((cluster["lowest_share"] for cluster in small), default=None),
            "highest_share": max((cluster["highest_share"] for cluster in small), default=None),
        },
    }


def age_grid_reading(rasters: Mapping[str, rasterio.io.DatasetReader], window: Window) -> dict[str, Any]:
    """Read how uniform the age composition of the input grid is, in one window and over the whole grid.

    This describes the input. It computes nothing for a unit.

    Args:
        rasters: The 20 open age rasters, keyed by band.
        window: The window to describe, in rows and columns of the grid.

    Returns:
        ``frame_window`` (the window in rows and columns with its bounds, its
        :func:`composition_reading` and its :func:`share_clusters`) and
        ``whole_grid`` (the grid's size and its :func:`composition_reading`).
    """

    source = rasters[AGE_BANDS[0]]
    residents, dependants, valid = read_grid_counts(rasters, window)
    populated = valid & (residents > 0)
    west, south, east, north = window_bounds(window, source.transform)
    everywhere = read_grid_counts(rasters)
    return {
        "frame_window": {
            "row_off": int(window.row_off), "col_off": int(window.col_off),
            "height": int(window.height), "width": int(window.width),
            "bounds_west_south_east_north": [west, south, east, north],
            **composition_reading(residents, dependants, valid),
            "share_clusters": share_clusters(dependants[populated] / residents[populated], residents[populated]),
        },
        "whole_grid": {
            "height": int(source.height), "width": int(source.width),
            **composition_reading(*everywhere),
        },
    }


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
