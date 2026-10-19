"""Mud on the THEOS-2 scene of 17 September 2024: the scaling, the three candidate rules, the draw and the choice.

Plan: ``docs/proposal_execution/theos2_17sep_recession_and_mud_plan_v1.md``, section 4. The functions here are pure;
``scripts/build_theos2_17sep_mud.py`` reads the files. Mud is a reading of one image by one rule, not a ground survey.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Any, Mapping, Sequence

import numpy as np

SCALING_SEED: int = 20261019
SCALING_CELLS: int = 20_000
DEVELOPMENT_SEED: int = 20261019
TEST_SEED: int = 20261020
CLEAR_SCL: tuple[int, ...] = (4, 5, 6, 7, 11)  # the clear classes of the river fit
GREEN_BEFORE_NDVI: float = 0.45
MIN_OBJECT_PX: int = 5  # 20 square metres at 2 m
MIN_OBJECT_PX_V2: int = 25  # 100 square metres at 2 m, amendment 1
NEW_DEVELOPMENT_SEED: int = 20261021
OPENED_STRATA: tuple[str, ...] = ("opened_mud", "opened_not_mud")
OPENED_POINTS: dict[str, int] = {"opened_mud": 20, "opened_not_mud": 20}
KEEP_AWAY_PX: int = 10  # 20 m from every earlier development point
EDGE_PX: int = 3  # 6 m at 2 m, a square neighbourhood
CHOICE_MARGIN: float = 0.02
CANDIDATES: tuple[str, ...] = ("mud_s0", "mud_s1", "mud_s2")
GRID_NDVI_MAX: tuple[float, ...] = (0.15, 0.20, 0.25, 0.30)
GRID_RED_OVER_GREEN: tuple[float, ...] = (1.00, 1.04, 1.08, 1.12)
GRID_RED_OVER_BLUE: tuple[float, ...] = (1.1, 1.2, 1.3, 1.4)

MUD_NO: int = 0
MUD_YES: int = 1
MUD_UNOBSERVABLE: int = 255

GROUPS: tuple[str, ...] = ("mud_inside", "mud_edge", "near_mud", "ground_far", "unobservable")
DEVELOPMENT_POINTS: dict[str, int] = {"mud_inside": 40, "mud_edge": 30, "near_mud": 30, "ground_far": 45, "unobservable": 15}
TEST_POINTS: dict[str, int] = {"mud_inside": 45, "mud_edge": 30, "near_mud": 25, "ground_far": 40, "unobservable": 10}
LABELS: tuple[str, ...] = ("mud", "bare_cannot_tell", "not_mud", "cannot_tell")


class MudError(ValueError):
    """The arrays, the points or the labels cannot support the rule."""


@dataclass(frozen=True)
class MudLimits:
    """The colour rule of the replay's mud line: plants absent, red above green and above blue."""

    ndvi_max: float = 0.25
    red_over_green_min: float = 1.08
    red_over_blue_min: float = 1.3


# ---------------------------------------------------------------------------
# The scaling of the counts to Sentinel-2 reflectance
# ---------------------------------------------------------------------------


def _pair_slopes(x: np.ndarray, y: np.ndarray, start: int, stop: int) -> np.ndarray:
    dx = x[None, :] - x[start:stop, None]
    dy = y[None, :] - y[start:stop, None]
    keep = (np.arange(x.size)[None, :] > np.arange(start, stop)[:, None]) & (dx != 0)
    return dy[keep] / dx[keep]


def theil_sen(x: Sequence[float], y: Sequence[float], *, chunk: int = 256, bins: int = 1 << 16) -> dict[str, float]:
    """The Theil-Sen line of ``y`` on ``x``: the median of the slopes of all pairs with distinct ``x``, exactly.

    The intercept is ``median(y) - slope * median(x)``, as scipy gives it. The slopes are never all held at once:
    one pass finds their range, one counts them into bins, one keeps the bin that holds the median.
    """

    xs, ys = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    if xs.shape != ys.shape or xs.ndim != 1 or xs.size < 2:
        raise MudError("x and y must be one-dimensional and of one length, at least two")
    blocks = [(start, min(xs.size, start + chunk)) for start in range(0, xs.size, chunk)]
    low, high, total = np.inf, -np.inf, 0
    for start, stop in blocks:
        slopes = _pair_slopes(xs, ys, start, stop)
        if slopes.size:
            low, high, total = min(low, float(slopes.min())), max(high, float(slopes.max())), total + slopes.size
    if total == 0:
        raise MudError("every x is the same: no slope")
    ranks = sorted({(total - 1) // 2, total // 2})
    if high == low:
        slope = low
    else:
        width = (high - low) / bins
        counts = np.zeros(bins, dtype="int64")
        for start, stop in blocks:
            slopes = _pair_slopes(xs, ys, start, stop)
            counts += np.bincount(np.minimum(((slopes - low) / width).astype("int64"), bins - 1), minlength=bins)
        cumulative = np.cumsum(counts)
        values = []
        for rank in ranks:
            index = int(np.searchsorted(cumulative, rank, side="right"))
            before = int(cumulative[index - 1]) if index else 0
            kept = []
            for start, stop in blocks:
                slopes = _pair_slopes(xs, ys, start, stop)
                kept.append(slopes[np.minimum(((slopes - low) / width).astype("int64"), bins - 1) == index])
            values.append(float(np.sort(np.concatenate(kept))[rank - before]))
        slope = float(np.mean(values))
    return {"slope": slope, "intercept": float(np.median(ys) - slope * np.median(xs)), "pairs": int(total)}


def scale(counts: np.ndarray, line: Mapping[str, float]) -> np.ndarray:
    """Counts put on the scale of reflectance by one fitted line."""

    return np.asarray(counts, dtype="float32") * np.float32(line["slope"]) + np.float32(line["intercept"])


# ---------------------------------------------------------------------------
# The candidates
# ---------------------------------------------------------------------------


def ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """(NIR - red) / (NIR + red); NaN where the sum is not positive."""

    r, n = np.asarray(red, dtype="float32"), np.asarray(nir, dtype="float32")
    total = r + n
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(total > 0, (n - r) / total, np.nan)


def colour_rule(red: np.ndarray, green: np.ndarray, blue: np.ndarray, nir: np.ndarray, limits: MudLimits) -> np.ndarray:
    """True where a scaled pixel has the colour of mud: no plants, red above green and above blue by the limits."""

    with np.errstate(invalid="ignore"):
        return ((ndvi(red, nir) <= limits.ndvi_max) & (red > limits.red_over_green_min * green)
                & (red > limits.red_over_blue_min * blue))


def drop_small(mask: np.ndarray, min_px: int = MIN_OBJECT_PX) -> np.ndarray:
    """``mask`` without its objects (8-connected) of fewer than ``min_px`` pixels."""

    from scipy import ndimage

    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if count == 0:
        return np.zeros(mask.shape, dtype=bool)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_px
    keep[0] = False
    return keep[labels]


def answer(colour: np.ndarray, observable: np.ndarray, before_ok: np.ndarray | None = None,
           min_px: int = MIN_OBJECT_PX) -> np.ndarray:
    """Mud (1), not mud (0) or unobservable (255) from a colour mask, the observable pixels and, for ``mud_s1``, the condition before."""

    mud = colour & observable
    if before_ok is not None:
        mud &= before_ok
    mud = drop_small(mud, min_px)
    result = np.full(colour.shape, MUD_UNOBSERVABLE, dtype="uint8")
    result[observable] = MUD_NO
    result[mud] = MUD_YES
    return result


def threshold_grid() -> list[MudLimits]:
    """The 64 limits ``mud_s2`` may take, in the order ties are broken (the first wins)."""

    return [MudLimits(a, b, c) for a, b, c in product(GRID_NDVI_MAX, GRID_RED_OVER_GREEN, GRID_RED_OVER_BLUE)]


# ---------------------------------------------------------------------------
# Groups and points
# ---------------------------------------------------------------------------


def groups(answers: np.ndarray, edge_px: int = EDGE_PX) -> np.ndarray:
    """The group index of each pixel (order of ``GROUPS``) from the answers of one rule; 255 where nothing was read."""

    from scipy import ndimage

    size = 2 * edge_px + 1
    square = np.ones((size, size), dtype=bool)
    mud = answers == MUD_YES
    not_mud = answers != MUD_YES
    near_not_mud = ndimage.binary_dilation(not_mud, structure=square)
    near_mud = ndimage.binary_dilation(mud, structure=square)
    result = np.full(answers.shape, 255, dtype="uint8")
    result[mud & ~near_not_mud] = 0
    result[mud & near_not_mud] = 1
    result[(answers == MUD_NO) & near_mud] = 2
    result[(answers == MUD_NO) & ~near_mud] = 3
    result[answers == MUD_UNOBSERVABLE] = 4
    return result


def allocate(available: Mapping[tuple[str, str], int], wanted: Mapping[str, int], orders: Sequence[str],
             group_names: Sequence[str] = GROUPS, spill_to: str = "ground_far") -> dict[tuple[str, str], int]:
    """Points per (group, order): half of a group in each order; a shortfall goes to the other order, then to ``spill_to``.

    ``available`` counts the pixels of each (group, order). The first order takes the odd point.
    """

    taken: dict[tuple[str, str], int] = {(group, order): 0 for group in group_names for order in orders}
    spill: dict[str, int] = {order: 0 for order in orders}
    for group in group_names:
        want = wanted.get(group, 0)
        share = [want - want // 2, want // 2][:len(orders)] if len(orders) == 2 else [want]
        for index, order in enumerate(orders):
            taken[(group, order)] = min(share[index], available.get((group, order), 0))
        for index, order in enumerate(orders):
            short = share[index] - taken[(group, order)]
            for other in orders:
                if short and other != order:
                    extra = min(short, available.get((group, other), 0) - taken[(group, other)])
                    taken[(group, other)] += extra
                    short -= extra
            spill[order] += short
    for order in orders:
        # The shortfall goes to ``spill_to`` in the same order first, then in the other order.
        for target_order in [order, *[other for other in orders if other != order]]:
            key = (spill_to, target_order)
            extra = min(spill[order], available.get(key, 0) - taken[key])
            taken[key] += extra
            spill[order] -= extra
    return taken


def draw(group_raster: np.ndarray, order_raster: np.ndarray, orders: Sequence[str], counts: Mapping[tuple[str, str], int],
         seed: int, *, free: np.ndarray | None = None, group_names: Sequence[str] = GROUPS) -> list[dict[str, Any]]:
    """Draw pixels at random inside each (group, order) without drawing a pixel twice; ``free`` marks pixels that may be drawn."""

    points: list[dict[str, Any]] = []
    for group_index, group in enumerate(group_names):
        for order_index, order in enumerate(orders):
            want = counts.get((group, order), 0)
            if not want:
                continue
            inside = (group_raster == group_index) & (order_raster == order_index)
            if free is not None:
                inside &= free
            rows, columns = np.nonzero(inside)
            if rows.size < want:
                raise MudError(f"{group} in {order} holds {rows.size} pixels, fewer than {want} points")
            rng = np.random.default_rng([seed, group_index, order_index])
            chosen = rng.choice(rows.size, size=want, replace=False)
            points += [{"group": group, "order": order, "row": int(rows[i]), "column": int(columns[i])} for i in sorted(chosen)]
    order = np.random.default_rng([seed, 99]).permutation(len(points))
    return [points[i] for i in order]


# ---------------------------------------------------------------------------
# Scores and the choice
# ---------------------------------------------------------------------------


def weighted_f1(points: Sequence[Mapping[str, Any]], said_mud: Sequence[bool], weights: Mapping[tuple[str, str], float]) -> dict[str, Any]:
    """Area-weighted F1 of the label mud on the points labelled mud or not mud; unobservable counts as not mud.

    ``weights`` maps (group, order) to the pixels a point of it stands for.
    """

    tp = fp = fn = 0.0
    used = 0
    for point, said in zip(points, said_mud):
        label = point.get("label")
        if label not in ("mud", "not_mud"):
            continue
        weight = float(weights[(point["group"], point["order"])])
        used += 1
        if said and label == "mud":
            tp += weight
        elif said:
            fp += weight
        elif label == "mud":
            fn += weight
    denominator = 2 * tp + fp + fn
    return {"f1": None if denominator == 0 else round(2 * tp / denominator, 4), "points": used,
            "precision": None if tp + fp == 0 else round(tp / (tp + fp), 4), "recall": None if tp + fn == 0 else round(tp / (tp + fn), 4)}


def point_weights(available: Mapping[tuple[str, str], int], points: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], float]:
    """Pixels per point of each (group, order) that holds points."""

    drawn: dict[tuple[str, str], int] = {}
    for point in points:
        key = (point["group"], point["order"])
        drawn[key] = drawn.get(key, 0) + 1
    return {key: available[key] / count for key, count in drawn.items()}


def mean_score(values: Sequence[float | None]) -> float | None:
    kept = [value for value in values if value is not None]
    return None if not kept else round(float(np.mean(kept)), 4)


def choose(scores: Mapping[str, float | None], margin: float = CHOICE_MARGIN,
           order: Sequence[str] = ("mud_s0", "mud_s1", "mud_s2")) -> str:
    """The first candidate stays unless the next is better by the margin, and so on along ``order``.

    Plan v1: ``mud_s0``, ``mud_s1``, ``mud_s2``. Amendment 1: ``mud_s0``, ``mud_s3``, ``mud_s4``.
    """

    chosen = order[0]
    for candidate in order[1:]:
        if scores.get(candidate) is not None and (scores.get(chosen) is None or scores[candidate] >= scores[chosen] + margin - 1e-12):
            chosen = candidate
    return chosen


def limits_dict(limits: MudLimits) -> dict[str, float]:
    return asdict(limits)
