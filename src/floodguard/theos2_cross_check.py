"""THEOS-2 optical cross-check of the radar flood candidates.

The plan is ``docs/proposal_execution/theos2_cross_check_plan_v1.md``. This
module holds the pure functions: the optical water rule on a four-band THEOS-2
image, the cells that are compared, the agreement counts, and the length of a
road centreline that lies on optical water. It reads no file and calls no
radar method; ``scripts/build_theos2_radar_cross_check.py`` does both.

Nothing here is an observation of a flood at the radar pass, an accuracy
figure or a warning. The optical image and the radar pass are hours apart, so
every count is agreement between two sensors at two times.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

CANDIDATE_NO: int = 0
CANDIDATE_YES: int = 1
CANDIDATE_NO_ANSWER: int = 255

WATER_NO: int = 0
WATER_YES: int = 1
WATER_UNOBSERVABLE: int = 255


class CrossCheckError(ValueError):
    """The arrays or the configuration cannot support the cross-check."""


# ---------------------------------------------------------------------------
# Optical water on the THEOS-2 image
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpticalWaterConfig:
    """The optical water rule. Every value is set on the THEOS-2 image alone.

    ``ndwi_threshold`` is the water threshold on NDWI. When it is ``None`` the
    upper threshold of a three-class Otsu split is used (see
    :func:`multi_otsu_thresholds`). Bright, wide objects (cloud, large bright
    roofs, bare bright ground) are unobservable, with a margin around them.
    ``unobservable_boxes`` are rectangles, in pixels of the image, marked
    unobservable by eye (thin cloud that the brightness rule does not catch).
    Connected water objects smaller than ``min_object_px`` are dropped: at 2 m
    they are mostly roofs.
    """

    ndwi_threshold: float | None = None
    histogram_low: float = -0.6
    histogram_high: float = 0.4
    histogram_bins: int = 200
    bright_brightness_min: float = 520.0
    bright_nir_min: float = 560.0
    bright_min_width_px: int = 11
    bright_margin_px: int = 10
    min_object_px: int = 250
    unobservable_boxes: tuple[tuple[int, int, int, int], ...] = ()


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """McFeeters' water index, (green - NIR) / (green + NIR); NaN where the sum is not positive."""

    g = np.asarray(green, dtype="float64")
    n = np.asarray(nir, dtype="float64")
    if g.shape != n.shape:
        raise CrossCheckError("green and nir must share one shape")
    total = g + n
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(total > 0, (g - n) / total, np.nan)


def _histogram(values: np.ndarray, low: float, high: float, bins: int) -> tuple[np.ndarray, np.ndarray]:
    if not (high > low and bins >= 4):
        raise CrossCheckError("the histogram needs high above low and at least four bins")
    data = np.asarray(values, dtype="float64").ravel()
    data = data[np.isfinite(data)]
    if data.size == 0:
        raise CrossCheckError("no finite value to threshold")
    counts, edges = np.histogram(data, bins=bins, range=(low, high))
    if counts.sum() == 0:
        raise CrossCheckError("no value inside the histogram range")
    return counts.astype("float64"), edges


def otsu_threshold(values: np.ndarray, *, low: float, high: float, bins: int = 200) -> float:
    """Otsu's two-class threshold on a histogram of ``values``; a bin edge."""

    counts, edges = _histogram(values, low, high, bins)
    centres = (edges[:-1] + edges[1:]) / 2.0
    weights = counts / counts.sum()
    below = np.cumsum(weights)
    moment = np.cumsum(weights * centres)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (moment[-1] * below - moment) ** 2 / (below * (1.0 - below))
    between[~np.isfinite(between)] = -1.0
    return float(edges[int(np.argmax(between)) + 1])


def multi_otsu_thresholds(
    values: np.ndarray, *, low: float, high: float, bins: int = 200
) -> tuple[float, float]:
    """The two thresholds of a three-class Otsu split of a histogram of ``values``.

    Both are bin edges, the lower one first. The split maximises the
    between-class variance of three classes.
    """

    counts, edges = _histogram(values, low, high, bins)
    centres = (edges[:-1] + edges[1:]) / 2.0
    weights = counts / counts.sum()
    cumulative = np.cumsum(weights)
    moment = np.cumsum(weights * centres)
    first = np.arange(bins)[:, None]
    second = np.arange(bins)[None, :]
    w0 = cumulative[:, None]
    w1 = cumulative[None, :] - cumulative[:, None]
    w2 = 1.0 - cumulative[None, :]
    m0 = moment[:, None]
    m1 = moment[None, :] - moment[:, None]
    m2 = moment[-1] - moment[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        variance = m0**2 / w0 + m1**2 / w1 + m2**2 / w2
    usable = (second > first) & (w0 > 0) & (w1 > 0) & (w2 > 0)
    variance = np.where(usable & np.isfinite(variance), variance, -np.inf)
    if not np.isfinite(variance).any():
        raise CrossCheckError("the histogram does not hold three populated classes")
    i, j = np.unravel_index(int(np.argmax(variance)), variance.shape)
    return float(edges[i + 1]), float(edges[j + 1])


def bright_object_mask(
    brightness: np.ndarray, nir: np.ndarray, *, brightness_min: float, nir_min: float, min_width_px: int, margin_px: int
) -> np.ndarray:
    """Bright objects at least ``min_width_px`` wide, grown by ``margin_px``.

    A pixel is bright when its mean visible value and its NIR value are both
    above their limits. An opening with a square of ``min_width_px`` removes
    narrower objects (small roofs); a dilation adds the margin.
    """

    from scipy import ndimage

    if min_width_px < 1 or margin_px < 0:
        raise CrossCheckError("min_width_px must be at least 1 and margin_px must not be negative")
    with np.errstate(invalid="ignore"):
        bright = (np.asarray(brightness) > brightness_min) & (np.asarray(nir) > nir_min)
    opened = ndimage.binary_opening(bright, structure=np.ones((min_width_px, min_width_px), dtype=bool))
    if margin_px == 0:
        return opened
    size = 2 * margin_px + 1
    return ndimage.binary_dilation(opened, structure=np.ones((size, size), dtype=bool))


def optical_water(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    nir: np.ndarray,
    valid: np.ndarray,
    config: OpticalWaterConfig = OpticalWaterConfig(),
) -> tuple[np.ndarray, dict[str, Any]]:
    """Classify each pixel of a four-band image as water, not water or unobservable.

    Returns a ``uint8`` raster (0 not water, 1 water, 255 unobservable) and a
    summary with the thresholds that were applied and the pixel counts.
    """

    from scipy import ndimage

    bands = [np.asarray(band, dtype="float64") for band in (red, green, blue, nir)]
    mask = np.asarray(valid, dtype=bool)
    if bands[0].ndim != 2 or any(band.shape != bands[0].shape for band in bands) or mask.shape != bands[0].shape:
        raise CrossCheckError("the four bands and the valid mask must share one two-dimensional shape")
    r, g, b, n = bands
    index = ndwi(g, n)
    brightness = (r + g + b) / 3.0
    bright = bright_object_mask(
        brightness, n, brightness_min=config.bright_brightness_min, nir_min=config.bright_nir_min,
        min_width_px=config.bright_min_width_px, margin_px=config.bright_margin_px,
    )
    boxed = np.zeros(mask.shape, dtype=bool)
    for row0, row1, col0, col1 in config.unobservable_boxes:
        if not (0 <= row0 < row1 <= mask.shape[0] and 0 <= col0 < col1 <= mask.shape[1]):
            raise CrossCheckError("an unobservable box lies outside the image")
        boxed[row0:row1, col0:col1] = True
    observable = mask & ~bright & ~boxed & np.isfinite(index)
    two_class = otsu_threshold(index[observable], low=config.histogram_low, high=config.histogram_high,
                               bins=config.histogram_bins)
    lower, upper = multi_otsu_thresholds(index[observable], low=config.histogram_low, high=config.histogram_high,
                                         bins=config.histogram_bins)
    threshold = upper if config.ndwi_threshold is None else float(config.ndwi_threshold)
    with np.errstate(invalid="ignore"):
        flagged = observable & (index >= threshold)
    labels, _ = ndimage.label(flagged, structure=np.ones((3, 3), dtype=bool))
    sizes = np.bincount(labels.ravel())
    keep = sizes >= config.min_object_px
    keep[0] = False
    water = keep[labels]
    result = np.full(mask.shape, WATER_UNOBSERVABLE, dtype="uint8")
    result[observable] = WATER_NO
    result[water] = WATER_YES
    summary = {
        "configuration": {**asdict(config), "unobservable_boxes": [list(box) for box in config.unobservable_boxes]},
        "ndwi_threshold_applied": round(threshold, 6),
        "ndwi_threshold_source": "three_class_otsu_upper" if config.ndwi_threshold is None else "configured",
        "ndwi_two_class_otsu": round(two_class, 6),
        "ndwi_three_class_otsu": [round(lower, 6), round(upper, 6)],
        "pixels": int(mask.size),
        "valid_pixels": int(mask.sum()),
        "unobservable_bright_object_pixels": int((mask & bright).sum()),
        "unobservable_boxed_pixels": int((mask & boxed & ~bright).sum()),
        "observable_pixels": int(observable.sum()),
        "flagged_pixels_before_object_rule": int(flagged.sum()),
        "pixels_dropped_by_object_rule": int(flagged.sum() - water.sum()),
        "water_pixels": int(water.sum()),
    }
    return result, summary


# ---------------------------------------------------------------------------
# Cells that are compared, and the agreement counts
# ---------------------------------------------------------------------------


def reference_cells(
    water_share: np.ndarray,
    observable_share: np.ndarray,
    *,
    min_observable_share: float = 0.9,
    wet_share: float = 0.5,
    mixed_band: tuple[float, float] = (0.1, 0.9),
) -> dict[str, np.ndarray]:
    """Turn per-cell shares into the compared, wet, dry and mixed cells.

    ``water_share`` is the share of the observable fine pixels of a cell that
    are water, and ``observable_share`` the share of its fine pixels that are
    observable. A cell is compared at ``min_observable_share`` or more, wet at
    ``wet_share`` or more, and mixed strictly inside ``mixed_band``.
    """

    share = np.asarray(water_share, dtype="float64")
    seen = np.asarray(observable_share, dtype="float64")
    if share.shape != seen.shape:
        raise CrossCheckError("the two share rasters must have one shape")
    with np.errstate(invalid="ignore"):
        compared = np.isfinite(share) & np.isfinite(seen) & (seen >= min_observable_share)
        wet = compared & (share >= wet_share)
        mixed = compared & (share > mixed_band[0]) & (share < mixed_band[1])
    return {"compared": compared, "wet": wet, "dry": compared & ~wet, "mixed": mixed}


def scores(tp: int, fp: int, fn: int, tn: int) -> dict[str, float | None]:
    """IoU, precision, recall and F1 of the positive class; ``None`` where a denominator is zero."""

    def ratio(top: int, bottom: int) -> float | None:
        return round(top / bottom, 6) if bottom > 0 else None

    return {
        "iou": ratio(tp, tp + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def agreement(
    candidate: np.ndarray, wet: np.ndarray, compared: np.ndarray, *, cell_area_km2: float
) -> dict[str, Any]:
    """Count a candidate raster (0, 1, 255) against wet and dry reference cells.

    Two readings, as in the GEOID benchmark: on the cells the method answered,
    and strictly, where a compared cell without an answer counts as "not a
    candidate".
    """

    codes = np.asarray(candidate)
    is_wet = np.asarray(wet, dtype=bool)
    region = np.asarray(compared, dtype=bool)
    if codes.shape != is_wet.shape or codes.shape != region.shape:
        raise CrossCheckError("the candidate and the reference must have one shape")
    if cell_area_km2 <= 0:
        raise CrossCheckError("cell_area_km2 must be positive")
    if np.any(is_wet & ~region):
        raise CrossCheckError("a wet cell lies outside the compared cells")
    answered = region & (codes != CANDIDATE_NO_ANSWER)
    yes = region & (codes == CANDIDATE_YES)

    def counts(where: np.ndarray) -> dict[str, Any]:
        tp = int((yes & is_wet & where).sum())
        fp = int((yes & ~is_wet & where).sum())
        fn = int((~yes & is_wet & where).sum())
        tn = int((~yes & ~is_wet & where).sum())
        return {
            "cells": int(where.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "candidate_km2": round((tp + fp) * cell_area_km2, 4),
            "optical_wet_km2": round((tp + fn) * cell_area_km2, 4),
            **scores(tp, fp, fn, tn),
        }

    compared_cells = int(region.sum())
    return {
        "compared_cells": compared_cells,
        "answered_cells": int(answered.sum()),
        "answered_share": round(int(answered.sum()) / compared_cells, 6) if compared_cells else None,
        "on_answered_cells": counts(answered),
        "strict_no_answer_counts_as_not_a_candidate": counts(region),
    }


def agreement_by_class(
    candidate: np.ndarray,
    wet: np.ndarray,
    compared: np.ndarray,
    classes: np.ndarray,
    groups: Mapping[str, Sequence[int]],
    *,
    cell_area_km2: float,
) -> dict[str, Any]:
    """:func:`agreement` inside each group of class codes (land cover); ``other`` takes the rest."""

    codes = np.asarray(classes)
    region = np.asarray(compared, dtype=bool)
    if codes.shape != region.shape:
        raise CrossCheckError("the class raster must have the shape of the compared cells")
    taken = np.zeros(region.shape, dtype=bool)
    result: dict[str, Any] = {}
    for name, members in groups.items():
        inside = region & np.isin(codes, list(members))
        taken |= inside
        result[name] = agreement(candidate, np.asarray(wet, dtype=bool) & inside, inside, cell_area_km2=cell_area_km2)
    rest = region & ~taken
    result["other"] = agreement(candidate, np.asarray(wet, dtype=bool) & rest, rest, cell_area_km2=cell_area_km2)
    return result


# ---------------------------------------------------------------------------
# Road centrelines on optical water
# ---------------------------------------------------------------------------


def centreline_water_lengths(
    segments: np.ndarray,
    water: np.ndarray,
    *,
    west: float,
    north: float,
    cell_m: float,
    step_m: float = 1.0,
) -> list[dict[str, float]]:
    """Measure how much of each straight segment lies on optical water.

    ``segments`` has the shape ``(N, 2, 2)``: start and end, x and y, in the
    projected system of the ``water`` raster (0 not water, 1 water, 255
    unobservable), whose upper-left corner is ``(west, north)``. Each segment
    is sampled every ``step_m`` metres at the middle of each step. A sample
    outside the raster is unobservable.

    Returns, per segment, its length, the length on water, the observable
    length and the two shares that follow from them.
    """

    lines = np.asarray(segments, dtype="float64")
    raster = np.asarray(water)
    if lines.ndim != 3 or lines.shape[1:] != (2, 2):
        raise CrossCheckError("segments must have the shape (N, 2, 2)")
    if raster.ndim != 2 or cell_m <= 0 or step_m <= 0:
        raise CrossCheckError("water must be two-dimensional, and cell_m and step_m positive")
    rows: list[dict[str, float]] = []
    for start, end in lines:
        length = float(np.hypot(*(end - start)))
        steps = max(1, int(np.ceil(length / step_m)))
        position = (np.arange(steps) + 0.5) / steps
        x = start[0] + position * (end[0] - start[0])
        y = start[1] + position * (end[1] - start[1])
        column = np.floor((x - west) / cell_m).astype(int)
        row = np.floor((north - y) / cell_m).astype(int)
        inside = (row >= 0) & (row < raster.shape[0]) & (column >= 0) & (column < raster.shape[1])
        values = np.full(steps, WATER_UNOBSERVABLE, dtype="uint8")
        values[inside] = raster[row[inside], column[inside]]
        piece = length / steps
        on_water = float((values == WATER_YES).sum()) * piece
        observable = float((values != WATER_UNOBSERVABLE).sum()) * piece
        rows.append({
            "length_m": length,
            "on_water_m": on_water,
            "observable_m": observable,
            "observable_share": observable / length if length > 0 else 0.0,
            "on_water_share_of_observable": on_water / observable if observable > 0 else 0.0,
        })
    return rows


def seen_under_water(
    row: Mapping[str, float], *, min_length_m: float = 20.0, short_edge_m: float = 40.0, short_edge_share: float = 0.5
) -> bool:
    """Say whether a road edge counts as seen under water on the optical image.

    At ``min_length_m`` of centreline on water or more; an edge shorter than
    ``short_edge_m`` also counts at ``short_edge_share`` of its length or more.
    """

    if row["on_water_m"] >= min_length_m:
        return True
    return row["length_m"] < short_edge_m and row["length_m"] > 0 and row["on_water_m"] / row["length_m"] >= short_edge_share


def road_agreement(
    modelled_closed: Sequence[bool], seen_wet: Sequence[bool], lengths_m: Sequence[float]
) -> dict[str, Any]:
    """Compare the modelled state of road edges with what the optical image shows.

    Counts edges and kilometres in the four cells of the comparison and gives
    the two shares the plan asks for: of the edges the rule closes, the share
    seen under water; of the edges seen under water, the share the rule closes.
    """

    closed = np.asarray(modelled_closed, dtype=bool)
    wet = np.asarray(seen_wet, dtype=bool)
    length = np.asarray(lengths_m, dtype="float64")
    if not (closed.shape == wet.shape == length.shape) or closed.ndim != 1:
        raise CrossCheckError("the three sequences must have one length")

    def cell(mask: np.ndarray) -> dict[str, float | int]:
        return {"edges": int(mask.sum()), "km": round(float(length[mask].sum()) / 1000.0, 3)}

    both, only_rule, only_seen, neither = closed & wet, closed & ~wet, ~closed & wet, ~closed & ~wet

    def share(top: np.ndarray, bottom: np.ndarray) -> dict[str, float | None]:
        return {
            "by_edges": round(int(top.sum()) / int(bottom.sum()), 6) if bottom.any() else None,
            "by_km": round(float(length[top].sum()) / float(length[bottom].sum()), 6) if length[bottom].sum() > 0 else None,
        }

    return {
        "edges": int(closed.size),
        "km": round(float(length.sum()) / 1000.0, 3),
        "closed_by_rule_and_seen_under_water": cell(both),
        "closed_by_rule_not_seen_under_water": cell(only_rule),
        "open_by_rule_seen_under_water": cell(only_seen),
        "open_by_rule_not_seen_under_water": cell(neither),
        "share_of_rule_closed_that_is_seen_under_water": share(both, closed),
        "share_of_seen_under_water_that_the_rule_closes": share(both, wet),
    }
