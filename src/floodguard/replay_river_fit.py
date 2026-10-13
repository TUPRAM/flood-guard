"""The replay's flood model: a peak level for each stretch of channel, fitted to the mud line of a satellite image.

The plan is ``docs/proposal_execution/replay_river_fit_plan_v1.md``. This
module holds the pure functions: the evidence of a flood read from two
optical scenes, the level of each stretch of channel, the squares that are
held back, and the shares that are reported.
``scripts/build_mae_sai_flood_timeline.py`` reads the files and routes the
flow.

A fitted level follows the image it was fitted to. The result is a modelled
scenario: not an observation of the flood, not a forecast and not a warning.
"""

from __future__ import annotations

from typing import Any

import numpy as np

CLEAR_CLASSES: tuple[int, ...] = (4, 5, 6, 7, 11)   # Sentinel-2 scene classification: vegetation, bare, water, unclassified, snow
GREEN_BEFORE_NDVI: float = 0.45
BARE_AFTER_NDVI: float = 0.25
RED_OVER_GREEN: float = 1.08
RED_OVER_BLUE: float = 1.3
WET_MNDWI: float = 0.0

RIVER_BURN_M: float = 20.0
STRETCH_RADIUS_M: float = 1000.0
MIN_EVIDENCE_CELLS: int = 50
COVERED_SHARE: float = 0.90
MAX_LEVEL_M: float = 8.0
LEVEL_STEP_M: float = 0.1
SMOOTH_RADIUS_M: float = 500.0
BORROW_RADIUS_M: float = 3000.0
SQUARE_M: float = 2000.0


class RiverFitError(ValueError):
    """The arrays cannot support the fit."""


def _ratio(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(bottom > 0, top / bottom, np.nan)


def flood_evidence(before: dict[str, np.ndarray], after: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Return (judged, evidence) from two optical scenes of reflectance bands.

    ``before`` needs ``red``, ``nir`` and ``scl``; ``after`` needs ``red``,
    ``green``, ``blue``, ``nir``, ``swir16`` and ``scl``. A cell is judged
    when it is clear on both dates and green before. It is evidence when it
    is judged and afterwards either brown without plants or still wet.
    """

    shape = np.asarray(before["red"]).shape
    for scene, names in ((before, ("red", "nir", "scl")), (after, ("red", "green", "blue", "nir", "swir16", "scl"))):
        for name in names:
            if np.asarray(scene[name]).shape != shape:
                raise RiverFitError("every band of both scenes must have one shape")
    clear = (np.isin(before["scl"], CLEAR_CLASSES) & (before["red"] > 0) & np.isin(after["scl"], CLEAR_CLASSES) & (after["red"] > 0))
    ndvi_before = _ratio(before["nir"] - before["red"], before["nir"] + before["red"])
    ndvi_after = _ratio(after["nir"] - after["red"], after["nir"] + after["red"])
    mndwi_after = _ratio(after["green"] - after["swir16"], after["green"] + after["swir16"])
    with np.errstate(invalid="ignore"):
        judged = clear & (ndvi_before >= GREEN_BEFORE_NDVI)
        brown = (after["red"] > after["green"] * RED_OVER_GREEN) & (after["red"] > after["blue"] * RED_OVER_BLUE)
        evidence = judged & (((ndvi_after <= BARE_AFTER_NDVI) & brown) | (mndwi_after > WET_MNDWI))
    return judged, evidence


def chessboard(rows: int, columns: int, cell_m: float, square_m: float = SQUARE_M) -> np.ndarray:
    """True on the squares that are held back: squares of ``square_m`` alternating like a chessboard."""

    if cell_m <= 0 or square_m < cell_m:
        raise RiverFitError("a square must be at least one cell wide")
    per = square_m / cell_m
    row = (np.arange(rows) // per).astype("int64")
    column = (np.arange(columns) // per).astype("int64")
    return ((row[:, None] + column[None, :]) % 2) == 1


def _box_sum(values: np.ndarray, radius_px: int) -> np.ndarray:
    from scipy import ndimage

    size = 2 * radius_px + 1
    return ndimage.uniform_filter(values.astype("float64"), size=size, mode="constant", cval=0.0) * size * size


def fit_levels(
    hand: np.ndarray,
    drain: np.ndarray,
    channel: np.ndarray,
    evidence: np.ndarray,
    fallback: np.ndarray,
    cell_m: float,
    *,
    use: np.ndarray | None = None,
    radius_m: float = STRETCH_RADIUS_M,
    min_cells: int = MIN_EVIDENCE_CELLS,
    covered_share: float = COVERED_SHARE,
    max_level_m: float = MAX_LEVEL_M,
    step_m: float = LEVEL_STEP_M,
    smooth_radius_m: float = SMOOTH_RADIUS_M,
    borrow_radius_m: float = 0.0,
) -> dict[str, Any]:
    """Fit a peak level to each stretch of channel and hand it to the cells that drain there.

    ``hand`` is the height of each cell above the channel cell it drains to
    and ``drain`` the flat index of that channel cell (negative where there
    is none). ``evidence`` marks the cells that show a flood. ``fallback`` is
    the level every channel cell has when its stretch is not fitted. ``use``
    limits the channel cells whose evidence may be used (the squares that are
    not held back); every channel cell still receives a level. With
    ``borrow_radius_m`` above zero, a channel cell whose stretch is not fitted
    takes the level of the nearest fitted channel cell within that distance
    before it falls back: the water surface along a river has no steps.

    Returns ``level`` (per cell, from its channel cell), ``channel_level`` and
    ``fitted`` (per channel cell; NaN and False off the channels) and
    ``evidence_cells`` (per channel cell: the evidence of its stretch).
    """

    shape = np.asarray(hand).shape
    for name, array in (("drain", drain), ("channel", channel), ("evidence", evidence), ("fallback", fallback)):
        if np.asarray(array).shape != shape:
            raise RiverFitError(f"{name} must have the shape of hand")
    if not 0 < covered_share <= 1 or step_m <= 0 or max_level_m <= step_m:
        raise RiverFitError("the share must lie in (0, 1] and the level step below the highest level")
    channel = np.asarray(channel, dtype=bool)
    flat_drain = np.asarray(drain).ravel()
    usable = np.asarray(evidence, dtype=bool).ravel() & (flat_drain >= 0) & np.isfinite(np.asarray(hand).ravel())
    if use is not None:
        allowed = np.asarray(use, dtype=bool).ravel()
        usable &= allowed[np.clip(flat_drain, 0, None)]
    bins = int(round(max_level_m / step_m))
    which = np.minimum((np.asarray(hand).ravel()[usable] / step_m).astype("int64"), bins)   # the last bin holds everything above
    radius_px = max(1, int(round(radius_m / cell_m)))
    cells = shape[0] * shape[1]
    drains = flat_drain[usable]
    # The evidence of a stretch: every evidence cell that drains to a channel cell within the radius.
    total = _box_sum(np.bincount(drains, minlength=cells).reshape(shape), radius_px)
    running = np.zeros(shape, dtype="float64")
    level = np.full(shape, np.nan, dtype="float64")
    for index in range(bins + 1):
        here = which == index
        if not here.any():
            continue
        running += _box_sum(np.bincount(drains[here], minlength=cells).reshape(shape), radius_px)
        reached = np.isnan(level) & (total > 0.5) & (running >= covered_share * total - 1e-6)
        level[reached] = min((index + 1) * step_m, max_level_m)
    fitted = channel & (total >= min_cells - 0.5) & np.isfinite(level)
    channel_level = np.where(fitted, level, np.asarray(fallback, dtype="float64"))
    borrowed = np.zeros(shape, dtype=bool)
    if borrow_radius_m > 0 and fitted.any():
        from scipy import ndimage

        distance, (rows, columns) = ndimage.distance_transform_edt(~fitted, return_indices=True)
        borrowed = channel & ~fitted & (distance * cell_m <= borrow_radius_m)
        channel_level = np.where(borrowed, level[rows, columns], channel_level)
    channel_level = np.where(channel, channel_level, 0.0)
    smooth_px = max(1, int(round(smooth_radius_m / cell_m)))
    with np.errstate(divide="ignore", invalid="ignore"):
        smoothed = _box_sum(channel_level, smooth_px) / _box_sum(channel.astype("float64"), smooth_px)
    channel_level = np.where(channel, smoothed, np.nan)
    flat_level = channel_level.ravel()
    per_cell = np.where(flat_drain >= 0, flat_level[np.clip(flat_drain, 0, None)], np.nan).reshape(shape)
    return {"level": per_cell, "channel_level": channel_level, "fitted": fitted, "borrowed": borrowed,
            "evidence_cells": np.where(channel, total, np.nan)}


def shares(evidence: np.ndarray, judged: np.ndarray, wet: np.ndarray, where: np.ndarray | None = None, cell_km2: float = 1.0) -> dict[str, Any]:
    """What is reported of a modelled peak against the evidence, on the cells of ``where``."""

    inside = np.ones(np.asarray(evidence).shape, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    seen = np.asarray(evidence, dtype=bool) & inside
    could = np.asarray(judged, dtype=bool) & inside
    flooded = np.asarray(wet, dtype=bool) & inside
    return {
        "evidence_km2": round(float(seen.sum()) * cell_km2, 2),
        "peak_km2": round(float(flooded.sum()) * cell_km2, 2),
        "share_of_the_evidence_inside_the_peak": None if not seen.any() else round(float((seen & flooded).sum()) / float(seen.sum()), 4),
        "share_of_the_judged_peak_with_evidence": None if not (flooded & could).any() else round(
            float((seen & flooded).sum()) / float((flooded & could).sum()), 4),
    }
