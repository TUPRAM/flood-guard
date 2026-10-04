"""Radar flood candidates on a reporting frame (plan tasks A2 and A4).

Three own candidates of tier T2 (protocol v1a, ``evidence_tier_model``), each a
pure function of arrays:

* **UN-SPIDER reproduction** (plan row A2): the UN-SPIDER recommended practice
  for Sentinel-1 flood mapping, with its published ratio of 1.25, untuned.
* **M1-literal** and **M1-v2** (plan row A4): the two methods of
  ``floodguard.sar_change_v2``, applied tile by tile on the lattice of the
  GEOID benchmark, because that is how both were run when M1-v2 was frozen.

This module adds no detection rule of its own. It cuts a frame into tiles,
calls the frozen functions, puts the tiles back together and counts cells per
unit. It computes no FPPS, no A-E class and no ensemble. A candidate is not an
observation and never a warning.

Cell codes follow ``sar_change_v2``: 0 not a candidate, 1 flood candidate,
255 no answer. A second raster gives the reason for a cell without an answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from floodguard import sar_change_v2 as sar

# The GEOID-Flood sample tiles are 1024 by 1024 cells of 10 m, and their
# corners are whole multiples of 10,240 m in their UTM zone (checked on the
# tile headers). M1-v2 was tuned and frozen on those tiles and declines a
# whole tile at a time, so the same lattice is used wherever it is applied.
GEOID_TILE_CELLS: int = 1024
GEOID_CELL_M: float = 10.0

# Names of the flood inputs as protocol v1a writes them (t2_skill_bar).
FLOOD_INPUT_NAMES: dict[str, str] = {
    "un_spider": "UN-SPIDER reproduction",
    "m1_literal": "M1-literal",
    "m1_v2": "M1-v2",
}
METHODS: tuple[str, ...] = tuple(FLOOD_INPUT_NAMES)

# Reasons, one per cell. Codes below 10 mean "no answer".
REASON_ANSWERED: int = 0
REASON_OUTSIDE_FRAME: int = 1
REASON_NO_VALID_RADAR_INPUT: int = 2
REASON_METHOD_DECLINED: int = 3
# Codes from 10 mark a cell the method answered "not a candidate" after one of
# its own removal steps (UN-SPIDER reproduction only).
REASON_REMOVED_PERMANENT_WATER: int = 10
REASON_REMOVED_SMALL_GROUP: int = 11
REASON_REMOVED_SLOPE: int = 12
REASON_LABELS: dict[int, str] = {
    REASON_ANSWERED: "answered",
    REASON_OUTSIDE_FRAME: "outside_reporting_frame",
    REASON_NO_VALID_RADAR_INPUT: "no_valid_radar_input",
    REASON_METHOD_DECLINED: "method_declined_for_the_tile",
    REASON_REMOVED_PERMANENT_WATER: "answered_removed_as_permanent_water",
    REASON_REMOVED_SMALL_GROUP: "answered_removed_by_connected_pixel_rule",
    REASON_REMOVED_SLOPE: "answered_removed_by_slope_rule",
}

# Flood-state levels of the T2 lane (protocol v1b, ensemble_grid, axis
# flood_input_single_state): the threshold moved by -1, 0 and +1 dB.
THRESHOLD_SHIFTS_DB: tuple[float, ...] = (-1.0, 0.0, 1.0)
LEVELS_NO_ANSWER: int = 255


class RadarCandidateError(ValueError):
    """The arrays or the configuration cannot support the candidate."""


# ---------------------------------------------------------------------------
# Tile lattice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LatticeTile:
    """One tile of the lattice: its column and row index and its bounds."""

    column: int
    row: int
    west: float
    south: float
    east: float
    north: float

    @property
    def name(self) -> str:
        return f"E{self.column:03d}N{self.row:03d}"


def lattice_tiles(
    bounds: Sequence[float], *, tile_cells: int = GEOID_TILE_CELLS, cell_m: float = GEOID_CELL_M
) -> list[LatticeTile]:
    """Return every lattice tile that overlaps ``bounds`` (west, south, east, north).

    Tile corners are whole multiples of ``tile_cells * cell_m`` in the
    projected coordinate system, as in the GEOID sample. Tiles are listed
    from north to south and west to east.
    """

    west, south, east, north = (float(value) for value in bounds)
    if not (east > west and north > south):
        raise RadarCandidateError("bounds must be west, south, east, north with a positive extent")
    size = tile_cells * cell_m
    first_column, last_column = math.floor(west / size), math.ceil(east / size) - 1
    first_row, last_row = math.floor(south / size), math.ceil(north / size) - 1
    return [
        LatticeTile(
            column=column,
            row=row,
            west=column * size,
            south=row * size,
            east=(column + 1) * size,
            north=(row + 1) * size,
        )
        for row in range(last_row, first_row - 1, -1)
        for column in range(first_column, last_column + 1)
    ]


def tile_window(
    tile: LatticeTile, grid_west: float, grid_north: float, cell_m: float
) -> tuple[slice, slice]:
    """Row and column slices of a tile inside a grid aligned to the lattice."""

    column = (tile.west - grid_west) / cell_m
    row = (grid_north - tile.north) / cell_m
    cells = (tile.east - tile.west) / cell_m
    if min(column, row) < 0 or any(abs(value - round(value)) > 1e-6 for value in (column, row, cells)):
        raise RadarCandidateError("the tile is not aligned to the grid")
    first_row, first_column, size = int(round(row)), int(round(column)), int(round(cells))
    return slice(first_row, first_row + size), slice(first_column, first_column + size)


# ---------------------------------------------------------------------------
# UN-SPIDER recommended practice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnSpiderConfig:
    """The parameters of the UN-SPIDER recommended practice. Nothing is tuned.

    They are the values of the published Google Earth Engine script of the
    practice ("Flood mapping and damage assessment using Sentinel-1 SAR data
    in Google Earth Engine"): VH polarisation, one pass direction, a focal
    mean of 50 m radius on the backscatter in dB, the after image divided by
    the before image, a threshold of 1.25 on that quotient, removal of
    perennial water, of groups of fewer than 8 connected cells and of slopes
    of 5 or more.
    """

    polarisation: str = "vh"
    smoothing: str = "focal_mean_circle_on_db"
    smoothing_radius_m: float = 50.0
    difference: str = "after_db_divided_by_before_db"
    difference_threshold: float = 1.25
    perennial_water: str = "removed_before_the_connected_pixel_rule"
    min_connected_cells: int = 8
    connectivity: str = "eight_connected"
    max_slope: float = 5.0
    slope_unit: str = "degrees"
    slope_rule: str = "cells_with_slope_at_or_above_max_slope_are_removed_last"


def circle_offsets(radius_cells: float) -> list[tuple[int, int]]:
    """Offsets of the cells whose centre lies within ``radius_cells`` of a cell centre."""

    if radius_cells < 0:
        raise RadarCandidateError("radius_cells must not be negative")
    reach = int(math.floor(radius_cells + 1e-9))
    return [
        (row, column)
        for row in range(-reach, reach + 1)
        for column in range(-reach, reach + 1)
        if row * row + column * column <= radius_cells * radius_cells + 1e-9
    ]


def focal_mean_circle(values: np.ndarray, valid: np.ndarray, radius_cells: float) -> np.ndarray:
    """Mean of the valid cells inside a circle around each valid cell.

    Cells that are not valid do not enter any mean and are NaN in the result,
    as a masked pixel is in the practice's ``focal_mean``.
    """

    data = np.asarray(values, dtype="float64")
    mask = np.asarray(valid, dtype=bool)
    if data.ndim != 2 or mask.shape != data.shape:
        raise RadarCandidateError("values and valid must share a two-dimensional shape")
    offsets = circle_offsets(radius_cells)
    reach = max(abs(value) for offset in offsets for value in offset)
    clean = np.pad(np.where(mask, data, 0.0), reach)
    weights = np.pad(mask.astype("float64"), reach)
    total = np.zeros(data.shape, dtype="float64")
    count = np.zeros(data.shape, dtype="float64")
    height, width = data.shape
    for row, column in offsets:
        window = np.s_[reach + row : reach + row + height, reach + column : reach + column + width]
        total += clean[window]
        count += weights[window]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
    return np.where(mask, mean, np.nan)


def keep_connected_groups(mask: np.ndarray, min_cells: int) -> np.ndarray:
    """Keep the cells that belong to an 8-connected group of at least ``min_cells`` cells."""

    from scipy import ndimage

    flags = np.asarray(mask, dtype=bool)
    if flags.ndim != 2:
        raise RadarCandidateError("mask must be two-dimensional")
    if min_cells < 1:
        raise RadarCandidateError("min_cells must be at least 1")
    labels, groups = ndimage.label(flags, structure=np.ones((3, 3), dtype=bool))
    if groups == 0:
        return np.zeros(flags.shape, dtype=bool)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_cells
    keep[0] = False
    return keep[labels]


def un_spider_candidate(
    pre: np.ndarray,
    post: np.ndarray,
    *,
    in_frame: np.ndarray,
    permanent_water: np.ndarray,
    slope: np.ndarray,
    cell_m: float,
    config: UnSpiderConfig = UnSpiderConfig(),
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Apply the UN-SPIDER recommended practice to one image pair.

    ``pre`` and ``post`` are linear sigma0 of the practice's polarisation on
    one grid. The steps, in the order of the published script:

    1. Clip both images to the area of interest (``in_frame``).
    2. Convert to dB and take the focal mean inside a circle of 50 m.
    3. Divide the after image by the before image (both in dB).
    4. Flag the cells where the quotient is above 1.25.
    5. Set the cells of perennial water to "not flooded".
    6. Drop every group of fewer than 8 connected flagged cells.
    7. Drop the cells whose slope is 5 or more.

    Returns the candidate (0, 1, 255), the reason of every cell, the quotient
    and a summary with the count after each step.
    """

    before = np.asarray(pre, dtype="float64")
    after = np.asarray(post, dtype="float64")
    frame = np.asarray(in_frame, dtype=bool)
    water = np.asarray(permanent_water, dtype=bool)
    gradient = np.asarray(slope, dtype="float64")
    if before.ndim != 2 or any(
        item.shape != before.shape for item in (after, frame, water, gradient)
    ):
        raise RadarCandidateError("every layer must share one two-dimensional shape")
    if cell_m <= 0:
        raise RadarCandidateError("cell_m must be positive")
    with np.errstate(invalid="ignore"):
        radiometry = np.isfinite(before) & np.isfinite(after) & (before > 0) & (after > 0)
    valid = frame & radiometry
    with np.errstate(divide="ignore", invalid="ignore"):
        before_db = np.where(valid, 10.0 * np.log10(before), np.nan)
        after_db = np.where(valid, 10.0 * np.log10(after), np.nan)
    radius_cells = config.smoothing_radius_m / cell_m
    before_mean = focal_mean_circle(before_db, valid, radius_cells)
    after_mean = focal_mean_circle(after_db, valid, radius_cells)
    with np.errstate(divide="ignore", invalid="ignore"):
        quotient = np.where(valid & (before_mean != 0), after_mean / before_mean, np.nan)
        flagged = valid & np.isfinite(quotient) & (quotient > config.difference_threshold)
    outside_water = flagged & ~water
    grouped = keep_connected_groups(outside_water, config.min_connected_cells)
    with np.errstate(invalid="ignore"):
        gentle = np.isfinite(gradient) & (gradient < config.max_slope)
    final = grouped & gentle

    candidate = np.full(before.shape, sar.CANDIDATE_ABSTAIN, dtype="uint8")
    candidate[valid] = sar.CANDIDATE_NO
    candidate[final] = sar.CANDIDATE_YES
    reason = np.full(before.shape, REASON_OUTSIDE_FRAME, dtype="uint8")
    reason[frame] = REASON_NO_VALID_RADAR_INPUT
    reason[valid] = REASON_ANSWERED
    reason[flagged & water] = REASON_REMOVED_PERMANENT_WATER
    reason[outside_water & ~grouped] = REASON_REMOVED_SMALL_GROUP
    reason[grouped & ~gentle] = REASON_REMOVED_SLOPE
    summary = {
        "method": "un_spider",
        "configuration": asdict(config),
        "smoothing_radius_cells": radius_cells,
        "smoothing_kernel_cells": len(circle_offsets(radius_cells)),
        "frame_cells": int(frame.sum()),
        "valid_cells": int(valid.sum()),
        "cells_with_zero_before_mean": int((valid & (before_mean == 0)).sum()),
        "cells_with_positive_before_mean_db": int((valid & (before_mean > 0)).sum()),
        "cells_above_threshold": int(flagged.sum()),
        "cells_above_threshold_with_positive_before_mean_db": int((flagged & (before_mean > 0)).sum()),
        "cells_removed_as_perennial_water": int((flagged & water).sum()),
        "cells_removed_by_connected_pixel_rule": int((outside_water & ~grouped).sum()),
        "cells_removed_by_slope_rule": int((grouped & ~gentle).sum()),
        "cells_without_a_slope_value_among_the_removed": int((grouped & ~np.isfinite(gradient)).sum()),
        "candidate_cells": int(final.sum()),
        "median_before_db": _median(before_mean, valid),
        "median_after_db": _median(after_mean, valid),
    }
    return candidate, reason, quotient.astype("float32"), summary


def _median(values: np.ndarray, where: np.ndarray) -> float | None:
    return round(float(np.median(values[where])), 4) if where.any() else None


# ---------------------------------------------------------------------------
# Terrain helpers for the practice's slope rule
# ---------------------------------------------------------------------------


def block_mean(values: np.ndarray, factor: int) -> np.ndarray:
    """Average non-overlapping ``factor`` by ``factor`` blocks; a ragged edge is dropped."""

    data = np.asarray(values, dtype="float64")
    if data.ndim != 2 or factor < 1:
        raise RadarCandidateError("values must be two-dimensional and factor at least 1")
    rows, columns = (data.shape[0] // factor) * factor, (data.shape[1] // factor) * factor
    if rows == 0 or columns == 0:
        raise RadarCandidateError("the array is smaller than one block")
    trimmed = data[:rows, :columns]
    return trimmed.reshape(rows // factor, factor, columns // factor, factor).mean(axis=(1, 3))


def slope_degrees(elevation: np.ndarray, spacing_x_m: np.ndarray | float, spacing_y_m: float) -> np.ndarray:
    """Slope in degrees from the four neighbours of each cell.

    ``spacing_x_m`` may be one value or one value per row (a geographic grid
    has narrower cells towards the poles). Border cells are NaN.
    """

    heights = np.asarray(elevation, dtype="float64")
    if heights.ndim != 2 or min(heights.shape) < 3:
        raise RadarCandidateError("elevation must be two-dimensional with at least three rows and columns")
    across = np.broadcast_to(np.asarray(spacing_x_m, dtype="float64").reshape(-1, 1), (heights.shape[0], 1))
    if np.any(across <= 0) or spacing_y_m <= 0:
        raise RadarCandidateError("cell spacings must be positive")
    slope = np.full(heights.shape, np.nan, dtype="float64")
    east_west = (heights[1:-1, 2:] - heights[1:-1, :-2]) / (2.0 * across[1:-1])
    north_south = (heights[:-2, 1:-1] - heights[2:, 1:-1]) / (2.0 * spacing_y_m)
    slope[1:-1, 1:-1] = np.degrees(np.arctan(np.hypot(east_west, north_south)))
    return slope


# ---------------------------------------------------------------------------
# M1-literal and M1-v2 on a tile, with the declared threshold levels
# ---------------------------------------------------------------------------


def nested_levels(layers: Sequence[np.ndarray], answered: np.ndarray) -> np.ndarray:
    """Code nested candidate extents, strictest first, as one raster.

    ``layers`` holds the candidate cells from the strictest threshold to the
    loosest. The result is the number of levels at which a cell is a
    candidate (0 to ``len(layers)``), or 255 where the method gave no answer.
    The extents must be nested: each one inside the next.
    """

    mask = np.asarray(answered, dtype=bool)
    levels = np.zeros(mask.shape, dtype="uint8")
    previous: np.ndarray | None = None
    for layer in layers:
        flags = np.asarray(layer, dtype=bool)
        if flags.shape != mask.shape:
            raise RadarCandidateError("every level must have the shape of the answered mask")
        if previous is not None and np.any(previous & ~flags):
            raise RadarCandidateError("the candidate extents are not nested")
        levels += flags.astype("uint8")
        previous = flags
    levels[~mask] = LEVELS_NO_ANSWER
    return levels


def m1_literal_tile(
    pre: np.ndarray, post: np.ndarray, config: sar.M1LiteralConfig = sar.M1LiteralConfig()
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Run M1-literal on one tile and add the three declared threshold levels.

    The candidate is exactly what ``sar_change_v2.m1_literal_predict``
    returns. The levels repeat its last two steps with the Otsu threshold
    moved by -1, 0 and +1 dB; the level at 0 dB must equal the candidate.

    M1-literal flags a cell only where delta-VH is below the threshold and
    below 0 dB. That second clause is kept at every level, so a level whose
    moved threshold is above 0 dB is cut at 0 dB. Where the Otsu threshold is
    0 dB or more, the +1 dB level is the central level again; where it lies
    between -1 and 0 dB, the +1 dB level moves by less than 1 dB. The summary
    says for each level whether it was cut (``effective_threshold_db``,
    ``cut_at_0_db``, ``plus_level``); see :func:`literal_level_cut`.

    Returns the candidate, the change score (delta-VH in dB, post minus pre,
    after the Lee filter), the level raster and the summary.
    """

    filtered = sar.filter_pair(
        pre,
        post,
        speckle_filter=config.speckle_filter,
        equivalent_looks=config.equivalent_looks,
        window_pixels=config.speckle_window_pixels,
    )
    candidate, summary = sar.m1_literal_from_filtered(filtered, config)
    delta_vh = (filtered.post_db[1] - filtered.pre_db[1]).astype("float32")
    threshold = summary["otsu_threshold_delta_vh_db"]
    answered = candidate != sar.CANDIDATE_ABSTAIN
    layers: list[np.ndarray] = []
    cells: dict[str, int | None] = {}
    for shift in THRESHOLD_SHIFTS_DB:
        key = _shift_key(shift)
        if threshold is None:
            layers.append(np.zeros(candidate.shape, dtype=bool))
            cells[key] = None
            continue
        with np.errstate(invalid="ignore"):
            raw = filtered.valid & (delta_vh < threshold + shift) & (delta_vh < 0)
        layers.append(sar.majority_filter(raw, filtered.valid))
        cells[key] = int(layers[-1].sum())
    if threshold is not None and not np.array_equal(layers[1], candidate == sar.CANDIDATE_YES):
        raise RadarCandidateError("the level at 0 dB does not reproduce M1-literal")
    summary = {
        **summary,
        "threshold_levels": {
            "shifts_db": list(THRESHOLD_SHIFTS_DB),
            "applied_to": "the Otsu threshold on delta-VH; a lower threshold is stricter",
            "candidate_cells": cells,
            **literal_level_cut(threshold),
        },
    }
    return candidate, delta_vh, nested_levels(layers, answered), summary


PLUS_LEVEL_FULL_SHIFT: str = "full_shift"
PLUS_LEVEL_CUT: str = "cut_at_0_db"
PLUS_LEVEL_SAME_AS_CENTRAL: str = "identical_to_the_central_level"


def literal_level_cut(threshold: float | None) -> dict[str, Any]:
    """Say what the below-zero clause of M1-literal does to each threshold level.

    M1-literal flags a cell where delta-VH is below the Otsu threshold and
    below 0 dB, so the threshold that takes effect at a level is the smaller
    of the moved threshold and 0 dB. ``plus_level`` names the outcome for the
    +1 dB level: the full shift (the Otsu threshold is -1 dB or lower), cut
    at 0 dB (between -1 and 0 dB), or identical to the central level (0 dB or
    higher, where the central level is itself cut at 0 dB).
    """

    clause = ("M1-literal flags a cell only where delta-VH is below the threshold and below 0 dB; the second "
              "clause is kept at every level, so a moved threshold above 0 dB is cut at 0 dB.")
    if threshold is None:
        return {"below_zero_clause": clause, "effective_threshold_db": None, "cut_at_0_db": None,
                "plus_level": None, "plus_level_shift_that_took_effect_db": None}
    moved = {_shift_key(shift): round(float(threshold) + shift, 6) for shift in THRESHOLD_SHIFTS_DB}
    effective = {key: round(min(value, 0.0), 4) + 0.0 for key, value in moved.items()}
    central, plus = effective[_shift_key(0.0)], effective[_shift_key(max(THRESHOLD_SHIFTS_DB))]
    if plus == central:
        outcome = PLUS_LEVEL_SAME_AS_CENTRAL
    elif moved[_shift_key(max(THRESHOLD_SHIFTS_DB))] > 0.0:
        outcome = PLUS_LEVEL_CUT
    else:
        outcome = PLUS_LEVEL_FULL_SHIFT
    return {
        "below_zero_clause": clause,
        "effective_threshold_db": effective,
        "cut_at_0_db": {key: value > 0.0 for key, value in moved.items()},
        "plus_level": outcome,
        "plus_level_shift_that_took_effect_db": round(plus - central, 4) + 0.0,
    }


def m1_v2_tile(
    pre: np.ndarray, post: np.ndarray, config: sar.M1V2Config
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Run M1-v2 on one tile and add the three declared threshold levels.

    The candidate is exactly what ``sar_change_v2.m1_v2_predict_filtered``
    returns for the tile on its own. The configuration must use the per-tile
    threshold scope and darkening only, as the frozen one does: a pooled
    threshold or a second side would need a different tiling rule.

    Returns the candidate, the change score (darkening in dB, positive where
    the backscatter fell), the level raster and the summary.
    """

    if config.threshold_scope != "per_tile" or config.sides() != ("darkening",):
        raise RadarCandidateError("the tile runner supports the per-tile scope and darkening only")
    filtered = sar.filter_pair(
        pre, post, speckle_filter=config.speckle_filter, equivalent_looks=config.equivalent_looks
    )
    candidate, summary = sar.m1_v2_predict_filtered({"tile": filtered}, config)["tile"]
    score = sar.change_score(filtered, config.channel, "darkening").astype("float32")
    threshold = summary["sides"]["darkening"]["threshold_db"]
    answered = candidate != sar.CANDIDATE_ABSTAIN
    layers = []
    cells: dict[str, int | None] = {}
    for shift in sorted(THRESHOLD_SHIFTS_DB, reverse=True):
        key = _shift_key(shift)
        if threshold is None:
            layers.append(np.zeros(candidate.shape, dtype=bool))
            cells[key] = None
            continue
        with np.errstate(invalid="ignore"):
            raw = filtered.valid & (score >= threshold + shift)
        layers.append(sar.majority_filter(raw, filtered.valid))
        cells[key] = int(layers[-1].sum())
    if threshold is not None and not np.array_equal(layers[1], candidate == sar.CANDIDATE_YES):
        raise RadarCandidateError("the level at 0 dB does not reproduce M1-v2")
    summary = {
        **summary,
        "threshold_levels": {
            "shifts_db": list(THRESHOLD_SHIFTS_DB),
            "applied_to": "the Kittler-Illingworth threshold on the darkening; a higher threshold is stricter",
            "candidate_cells": cells,
            "lowest_level_threshold_is_positive": None if threshold is None else bool(threshold - 1.0 > 0),
        },
    }
    return candidate, score, nested_levels(layers, answered), summary


def _shift_key(shift: float) -> str:
    return f"{shift:+.0f}_db" if shift else "0_db"


TileRunner = Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]]


def run_on_tiles(
    pre: np.ndarray,
    post: np.ndarray,
    tiles: Sequence[LatticeTile],
    runner: TileRunner,
    *,
    grid_west: float,
    grid_north: float,
    cell_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, dict[str, Any]]]:
    """Run a per-tile method on every tile and put the results on the grid.

    ``pre`` and ``post`` are ``(2, H, W)`` linear sigma0, VV before VH, on a
    grid aligned to the lattice. Each tile is handed to ``runner`` on its
    own, exactly as a GEOID tile was: its speckle filter, its threshold and
    its cleaning step see nothing outside the tile.

    Returns the candidate, the reason of every cell without an answer, the
    change score, the level raster and one summary per tile. Cells in no
    tile are "no answer" with the reason "outside the reporting frame".
    """

    before = np.asarray(pre)
    after = np.asarray(post)
    if before.ndim != 3 or before.shape[0] != 2 or after.shape != before.shape:
        raise RadarCandidateError("pre and post must share the shape (2, H, W)")
    shape = before.shape[1:]
    candidate = np.full(shape, sar.CANDIDATE_ABSTAIN, dtype="uint8")
    reason = np.full(shape, REASON_OUTSIDE_FRAME, dtype="uint8")
    score = np.full(shape, np.nan, dtype="float32")
    levels = np.full(shape, LEVELS_NO_ANSWER, dtype="uint8")
    summaries: dict[str, dict[str, Any]] = {}
    for tile in tiles:
        rows, columns = tile_window(tile, grid_west, grid_north, cell_m)
        if rows.stop > shape[0] or columns.stop > shape[1]:
            raise RadarCandidateError(f"tile {tile.name} lies outside the grid")
        tile_candidate, tile_score, tile_levels, summary = runner(
            before[:, rows, columns], after[:, rows, columns]
        )
        valid = sar.valid_radiometry(before[:, rows, columns], after[:, rows, columns])
        tile_reason = np.where(valid, REASON_METHOD_DECLINED, REASON_NO_VALID_RADAR_INPUT).astype("uint8")
        tile_reason[tile_candidate != sar.CANDIDATE_ABSTAIN] = REASON_ANSWERED
        candidate[rows, columns] = tile_candidate
        reason[rows, columns] = tile_reason
        score[rows, columns] = tile_score
        levels[rows, columns] = tile_levels
        summaries[tile.name] = summary
    return candidate, reason, score, levels, summaries


def restrict_to_frame(
    candidate: np.ndarray, reason: np.ndarray, levels: np.ndarray | None, in_frame: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Blank every cell outside the reporting frame: no answer, with that reason."""

    frame = np.asarray(in_frame, dtype=bool)
    if candidate.shape != frame.shape or reason.shape != frame.shape:
        raise RadarCandidateError("the layers and the frame must share a shape")
    clipped = np.where(frame, candidate, sar.CANDIDATE_ABSTAIN).astype("uint8")
    reasons = np.where(frame, reason, REASON_OUTSIDE_FRAME).astype("uint8")
    clipped_levels = None if levels is None else np.where(frame, levels, LEVELS_NO_ANSWER).astype("uint8")
    return clipped, reasons, clipped_levels


# ---------------------------------------------------------------------------
# Counting per unit
# ---------------------------------------------------------------------------


def unit_rows(
    candidate: np.ndarray,
    reason: np.ndarray,
    unit_index: np.ndarray,
    unit_ids: Sequence[str],
    *,
    cell_area_km2: float,
    valid_input: np.ndarray,
    permanent_water: np.ndarray,
    coverage_min: float,
    abstention_max: float,
) -> list[dict[str, Any]]:
    """Count cells per unit: coverage, cells without an answer and candidate area.

    ``unit_index`` holds 0 outside every unit and ``k`` for the cells whose
    centre lies in unit ``unit_ids[k - 1]``. Shares are taken over all cells
    of the unit.

    Two coverage figures are given, because protocol v1a asks for "unit valid
    coverage inside the product footprint or analysis extent" and does not
    say which: ``input_coverage`` is the share of the unit with valid radar
    input on both dates, and ``answer_coverage`` is the share with an answer
    from the method. ``abstention_fraction`` is the share without an answer,
    so ``answer_coverage + abstention_fraction`` is 1.
    """

    index = np.asarray(unit_index)
    if any(np.asarray(item).shape != index.shape for item in (candidate, reason, valid_input, permanent_water)):
        raise RadarCandidateError("every layer must have the shape of the unit index")
    if index.max(initial=0) > len(unit_ids):
        raise RadarCandidateError("the unit index names a unit that is not listed")
    bins = len(unit_ids) + 1

    def count(mask: np.ndarray) -> np.ndarray:
        return np.bincount(index[mask].ravel(), minlength=bins)

    cells = count(np.ones(index.shape, dtype=bool))
    valid = count(np.asarray(valid_input, dtype=bool))
    answered = count(candidate != sar.CANDIDATE_ABSTAIN)
    flagged = candidate == sar.CANDIDATE_YES
    candidates = count(flagged)
    candidates_on_land = count(flagged & ~np.asarray(permanent_water, dtype=bool))
    water = count(np.asarray(permanent_water, dtype=bool))
    declined = count(reason == REASON_METHOD_DECLINED)
    no_input = count(reason == REASON_NO_VALID_RADAR_INPUT)
    rows: list[dict[str, Any]] = []
    for position, unit_id in enumerate(unit_ids, start=1):
        total = int(cells[position])
        if total == 0:
            raise RadarCandidateError(f"unit {unit_id} has no cell on the grid")
        answer_coverage = int(answered[position]) / total
        input_coverage = int(valid[position]) / total
        abstention = (total - int(answered[position])) / total
        reasons = []
        if int(declined[position]):
            reasons.append(REASON_LABELS[REASON_METHOD_DECLINED])
        if int(no_input[position]):
            reasons.append(REASON_LABELS[REASON_NO_VALID_RADAR_INPUT])
        rows.append(
            {
                "unit_id": unit_id,
                "cells": total,
                "area_km2": round(total * cell_area_km2, 4),
                "permanent_water_cells": int(water[position]),
                "valid_input_cells": int(valid[position]),
                "answered_cells": int(answered[position]),
                "cells_without_an_answer": total - int(answered[position]),
                "cells_without_an_answer_by_reason": {
                    REASON_LABELS[REASON_METHOD_DECLINED]: int(declined[position]),
                    REASON_LABELS[REASON_NO_VALID_RADAR_INPUT]: int(no_input[position]),
                },
                "input_coverage": round(input_coverage, 6),
                "answer_coverage": round(answer_coverage, 6),
                "abstention_fraction": round(abstention, 6),
                "input_coverage_at_least_min": input_coverage >= coverage_min,
                "answer_coverage_at_least_min": answer_coverage >= coverage_min,
                "abstention_at_most_max": abstention <= abstention_max,
                "low_confidence_reason_codes": reasons if answer_coverage < coverage_min else [],
                "candidate_cells": int(candidates[position]),
                "candidate_area_km2": round(int(candidates[position]) * cell_area_km2, 4),
                "candidate_cells_outside_permanent_water": int(candidates_on_land[position]),
                "candidate_area_outside_permanent_water_km2": round(
                    int(candidates_on_land[position]) * cell_area_km2, 4
                ),
                "candidate_share_of_answered_cells": (
                    round(int(candidates[position]) / int(answered[position]), 6)
                    if int(answered[position])
                    else None
                ),
            }
        )
    return rows


def frame_totals(rows: Sequence[Mapping[str, Any]], *, cell_area_km2: float) -> dict[str, Any]:
    """Add the unit rows up to the frame: the same figures over every cell of the frame."""

    keys = (
        "cells",
        "permanent_water_cells",
        "valid_input_cells",
        "answered_cells",
        "cells_without_an_answer",
        "candidate_cells",
        "candidate_cells_outside_permanent_water",
    )
    total = {key: int(sum(int(row[key]) for row in rows)) for key in keys}
    cells = total["cells"]
    if cells == 0:
        raise RadarCandidateError("the frame has no cell")
    return {
        **total,
        "area_km2": round(cells * cell_area_km2, 4),
        "input_coverage": round(total["valid_input_cells"] / cells, 6),
        "answer_coverage": round(total["answered_cells"] / cells, 6),
        "abstention_fraction": round(total["cells_without_an_answer"] / cells, 6),
        "candidate_area_km2": round(total["candidate_cells"] * cell_area_km2, 4),
        "candidate_area_outside_permanent_water_km2": round(
            total["candidate_cells_outside_permanent_water"] * cell_area_km2, 4
        ),
        "units": len(rows),
        "units_with_input_coverage_at_least_min": sum(bool(row["input_coverage_at_least_min"]) for row in rows),
        "units_with_answer_coverage_at_least_min": sum(bool(row["answer_coverage_at_least_min"]) for row in rows),
        "units_with_abstention_at_most_max": sum(bool(row["abstention_at_most_max"]) for row in rows),
    }


def level_areas(
    levels: np.ndarray, unit_index: np.ndarray, unit_ids: Sequence[str], *, cell_area_km2: float
) -> dict[str, Any]:
    """Candidate area per unit at the strictest, the central and the loosest threshold."""

    index = np.asarray(unit_index)
    if np.asarray(levels).shape != index.shape:
        raise RadarCandidateError("the level raster must have the shape of the unit index")
    bins = len(unit_ids) + 1
    names = ("strictest", "central", "loosest")
    counts = {
        name: np.bincount(
            index[(levels != LEVELS_NO_ANSWER) & (levels >= minimum)].ravel(), minlength=bins
        )
        for name, minimum in zip(names, (3, 2, 1))
    }
    return {
        "levels": "strictest, central and loosest threshold (protocol v1b: the threshold moved by 1 dB each way)",
        "frame_km2": {name: round(int(counts[name][1:].sum()) * cell_area_km2, 4) for name in names},
        "units_km2": {
            unit_id: {name: round(int(counts[name][position]) * cell_area_km2, 4) for name in names}
            for position, unit_id in enumerate(unit_ids, start=1)
        },
    }


def strata_areas(
    candidate: np.ndarray,
    in_frame: np.ndarray,
    classes: np.ndarray,
    labels: Mapping[int, str],
    *,
    cell_area_km2: float,
) -> list[dict[str, Any]]:
    """Frame cells, answered cells and candidate cells in each class of a layer."""

    frame = np.asarray(in_frame, dtype=bool)
    codes = np.asarray(classes)
    if candidate.shape != frame.shape or codes.shape != frame.shape:
        raise RadarCandidateError("the layers must share a shape")
    rows = []
    for code, label in labels.items():
        here = frame & (codes == code)
        answered = here & (candidate != sar.CANDIDATE_ABSTAIN)
        flagged = here & (candidate == sar.CANDIDATE_YES)
        rows.append(
            {
                "class": label,
                "frame_cells": int(here.sum()),
                "answered_cells": int(answered.sum()),
                "candidate_cells": int(flagged.sum()),
                "candidate_area_km2": round(int(flagged.sum()) * cell_area_km2, 4),
                "candidate_share_of_answered_cells": (
                    round(int(flagged.sum()) / int(answered.sum()), 6) if int(answered.sum()) else None
                ),
            }
        )
    other = frame & ~np.isin(codes, list(labels))
    if other.any():
        rows.append(
            {
                "class": "other_or_no_value",
                "frame_cells": int(other.sum()),
                "answered_cells": int((other & (candidate != sar.CANDIDATE_ABSTAIN)).sum()),
                "candidate_cells": int((other & (candidate == sar.CANDIDATE_YES)).sum()),
                "candidate_area_km2": round(
                    int((other & (candidate == sar.CANDIDATE_YES)).sum()) * cell_area_km2, 4
                ),
                "candidate_share_of_answered_cells": None,
            }
        )
    return rows


def slope_classes(slope: np.ndarray, edges: Sequence[float]) -> tuple[np.ndarray, dict[int, str]]:
    """Class every cell by slope: ``edges`` are the lower bounds after the first class."""

    values = np.asarray(slope, dtype="float64")
    bounds = [float(edge) for edge in edges]
    if not bounds or any(later <= earlier for earlier, later in zip(bounds, bounds[1:])):
        raise RadarCandidateError("edges must be an increasing list")
    classes = np.full(values.shape, 255, dtype="uint8")
    finite = np.isfinite(values)
    classes[finite] = np.digitize(values[finite], bounds).astype("uint8")
    labels = {0: f"below_{bounds[0]:g}_degrees"}
    for position, edge in enumerate(bounds, start=1):
        upper = bounds[position] if position < len(bounds) else None
        labels[position] = (
            f"{edge:g}_to_below_{upper:g}_degrees" if upper is not None else f"{edge:g}_degrees_or_more"
        )
    return classes, labels
