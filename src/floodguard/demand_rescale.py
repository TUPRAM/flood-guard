"""The 2024-rescaled demand of the population-vintage axis (protocol v1b, ``ensemble_grid``, owner choice 12).

The formula of the protocol: within each 1 km cell of the WorldPop 2024 grid, every 2020 100 m count is multiplied
by the ratio of the cell's 2024 total to the sum of the 2020 counts inside the cell; a cell whose 2020 sum is zero
keeps zero. :func:`floodguard.age_exposure.rescale_2020_counts_to_2024` applies it and leaves two points open.
This module closes them the way ``scripts/bridge_worldpop_age_access.py`` already bridges the two grids, which is
the option the owners chose (decision log R12) and the reading recorded in R38:

1. a 100 m count belongs to the 1 km cell that holds the centre of its 100 m cell;
2. a positive 2020 count whose 1 km cell has no valid 2024 total is neither set to zero nor rescaled: it keeps its
   2020 value, and the counts and residents this touches are reported.

The resident counts are modelled (WorldPop), not observed. Nothing here computes a component or a class.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np

from floodguard import age_exposure

RESCALED_LEVEL = "rescaled_2024"
RULES = (
    "A 100 m count belongs to the 1 km cell that holds the centre of its 100 m cell.",
    "A positive 2020 count whose 1 km cell has no valid 2024 total keeps its 2020 value and is reported; it is neither "
    "set to zero nor rescaled.",
)


class DemandRescaleError(ValueError):
    """The two grids, or the demand cells, do not fit together."""


def cell_index(x: np.ndarray, y: np.ndarray, *, west: float, north: float, cell_width: float, cell_height: float,
               rows: int, columns: int) -> np.ndarray:
    """The identifier of the grid cell that holds each point: ``row * columns + column``, or -1 outside the grid.

    The grid is north-up with its upper-left corner at ``(west, north)``; ``cell_height`` is positive.
    """

    if cell_width <= 0 or cell_height <= 0 or rows <= 0 or columns <= 0:
        raise DemandRescaleError("the grid needs positive cell sizes and a positive number of rows and columns")
    column = np.floor((np.asarray(x, dtype="float64") - west) / cell_width).astype("int64")
    row = np.floor((north - np.asarray(y, dtype="float64")) / cell_height).astype("int64")
    inside = (row >= 0) & (row < rows) & (column >= 0) & (column < columns)
    return np.where(inside, row * columns + column, -1)


def rescale_counts(counts_2020: np.ndarray, cell_ids: np.ndarray, totals_2024: Mapping[int, float | None]) -> dict[str, Any]:
    """Apply the formula of the protocol with the two rules of this module.

    Args:
        counts_2020: Every 2020 100 m count of the 1 km cells in scope, finite and not negative. All counts of a
            1 km cell must be here, not only those of the demand cells: the ratio needs their sum.
        cell_ids: The 1 km cell of each count (rule 1), same shape; -1 for a count outside the 2024 grid.
        totals_2024: The 2024 total of each 1 km cell, or ``None`` where it has none.

    Returns:
        ``counts`` (the rescaled counts, same shape), ``kept_at_2020`` (a mask of the counts rule 2 leaves
        unchanged) and a record of what was done.
    """

    counts = np.asarray(counts_2020, dtype="float64")
    cells = np.asarray(cell_ids)
    if counts.shape != cells.shape:
        raise DemandRescaleError("counts and cell identifiers must have one shape")
    totals = {int(cell): total for cell, total in totals_2024.items()}
    totals.setdefault(-1, None)
    try:
        applied = age_exposure.rescale_2020_counts_to_2024(counts, cells.astype("int64"), totals)
    except age_exposure.AgeExposureError as error:
        raise DemandRescaleError(str(error)) from error
    rescaled = applied["rescaled_counts"]
    kept = np.isnan(rescaled)
    result = np.where(kept, counts, rescaled)
    ratios = [value for value in applied["ratio_by_cell"].values() if value is not None]
    return {
        "counts": result,
        "kept_at_2020": kept,
        "record": {
            "rules": list(RULES),
            "counts_2020": int(counts.size), "positive_counts_2020": int((counts > 0).sum()),
            "residents_2020": applied["residents_2020"],
            "residents_after": math.fsum(result.ravel().tolist()),
            "cells_1km_with_a_ratio": len(ratios),
            "ratio_lowest_median_highest": [round(float(np.min(ratios)), 6), round(float(np.median(ratios)), 6), round(float(np.max(ratios)), 6)] if ratios else None,
            "kept_at_2020_because_the_1km_cell_has_no_2024_total": {
                "counts": int(kept.sum()), "residents_2020": math.fsum(counts[kept].tolist()),
                "cells_1km": len(applied["without_2024_total"]["cells"])},
            "residents_2024_in_1km_cells_with_no_2020_count": applied["unallocated_2024_residents"],
        },
    }


def demand_values(grid_counts: np.ndarray, grid_rescaled: np.ndarray, rows: Sequence[int], columns: Sequence[int],
                  stated_residents: Sequence[float], *, tolerance: float = 1e-3) -> np.ndarray:
    """Read the rescaled count of every demand cell from the rescaled grid, after checking it is the same cell.

    A demand cell is a pixel of the 2020 grid. Its stated resident count must be the count of the pixel it is
    looked up at, or the lookup is wrong and nothing is returned.

    Raises:
        DemandRescaleError: when a demand cell lies outside the grid window or its count is not the pixel's.
    """

    row = np.asarray(rows, dtype="int64")
    column = np.asarray(columns, dtype="int64")
    stated = np.asarray(stated_residents, dtype="float64")
    if not (row.shape == column.shape == stated.shape):
        raise DemandRescaleError("rows, columns and residents must describe the same demand cells")
    if row.size and (row.min() < 0 or column.min() < 0 or row.max() >= grid_counts.shape[0] or column.max() >= grid_counts.shape[1]):
        raise DemandRescaleError("a demand cell lies outside the window of the 2020 grid")
    found = np.asarray(grid_counts, dtype="float64")[row, column]
    wrong = np.abs(found - stated) > tolerance * np.maximum(1.0, np.abs(stated))
    if wrong.any():
        raise DemandRescaleError(f"{int(wrong.sum())} demand cell(s) do not carry the count of the 2020 pixel they were looked up at")
    return np.asarray(grid_rescaled, dtype="float64")[row, column]
