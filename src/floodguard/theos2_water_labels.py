"""The THEOS-2 water rule against labels that two people give on the image.

The plan is ``docs/proposal_execution/theos2_water_label_check_plan_v1.md``.
This module holds the pure functions: the six groups a pixel of the rule can
fall in, the draw of the points, the label a point is scored with, and the
figures for a stratified random sample (Stehman 2014). It reads no file;
``scripts/build_theos2_water_labels.py`` does.

Nothing here is a ground check. The labels come from the same image the rule
reads, so every figure is agreement between a rule and two readers of one
image, at one time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from floodguard import theos2_cross_check as cc

SEED: int = 20261011
EDGE_PX: int = 3

GROUPS: tuple[str, ...] = (
    "water_inside", "water_edge", "dropped_small_object", "land_edge", "land_inside", "unobservable",
)
WATER_GROUPS: tuple[str, ...] = ("water_inside", "water_edge")
ANSWERED_GROUPS: tuple[str, ...] = GROUPS[:5]
EDGE_GROUPS: tuple[str, ...] = ("water_edge", "land_edge")
RECEIVES_SPARE_POINTS: str = "land_inside"

# Points per group, in the order of GROUPS (plan section 3).
PLANNED_POINTS: dict[str, tuple[int, ...]] = {
    "sukhothai": (20, 20, 15, 20, 30, 15),
    "chip_003": (20, 20, 15, 20, 30, 15),
    "chip_001": (10, 10, 8, 10, 15, 7),
}
CHIPS: tuple[str, ...] = tuple(PLANNED_POINTS)
REFERENCE_CHIPS: tuple[str, ...] = ("sukhothai", "chip_003")
PRACTICE_CHIP: str = "sukhothai"

WATER: str = "water"
NOT_WATER: str = "not_water"
CANNOT_TELL: str = "cannot_tell"
LABELS: tuple[str, ...] = (WATER, NOT_WATER, CANNOT_TELL)

Z_95: float = 1.959964


class LabelCheckError(ValueError):
    """The arrays, the draw or a label file cannot support the check."""


# ---------------------------------------------------------------------------
# The groups and the draw
# ---------------------------------------------------------------------------


def groups_of(water: np.ndarray, above_threshold: np.ndarray, *, edge_px: int = EDGE_PX) -> np.ndarray:
    """Put every pixel of the rule's raster in one of the six groups.

    ``water`` is the raster of :func:`floodguard.theos2_cross_check.optical_water`
    (0 not water, 1 water, 255 unobservable) and ``above_threshold`` says where
    the water index is at or above the threshold the rule applied. Returns a
    ``uint8`` raster of indices into :data:`GROUPS`.
    """

    from scipy import ndimage

    rule = np.asarray(water)
    above = np.asarray(above_threshold, dtype=bool)
    if rule.ndim != 2 or above.shape != rule.shape:
        raise LabelCheckError("the water raster and the threshold mask must share one two-dimensional shape")
    if edge_px < 1:
        raise LabelCheckError("edge_px must be at least 1")
    wet = rule == cc.WATER_YES
    dry = rule == cc.WATER_NO
    if (wet & ~above).any():
        raise LabelCheckError("a water pixel lies below the threshold: the mask is not the one of this raster")
    near = np.ones((2 * edge_px + 1, 2 * edge_px + 1), dtype=bool)
    dropped = dry & above
    result = np.full(rule.shape, GROUPS.index("unobservable"), dtype="uint8")
    result[dry] = GROUPS.index("land_inside")
    result[dry & ndimage.binary_dilation(wet, structure=near)] = GROUPS.index("land_edge")
    result[dropped] = GROUPS.index("dropped_small_object")
    result[wet] = GROUPS.index("water_inside")
    result[wet & ndimage.binary_dilation(dry, structure=near)] = GROUPS.index("water_edge")
    return result


def group_sizes(groups: np.ndarray) -> dict[str, int]:
    """The number of pixels in each group."""

    counts = np.bincount(np.asarray(groups).ravel(), minlength=len(GROUPS))
    return {name: int(counts[index]) for index, name in enumerate(GROUPS)}


def points_per_group(sizes: Mapping[str, int], planned: Sequence[int]) -> dict[str, int]:
    """The planned points, with the points of a group that is too small given to ``land_inside``."""

    if len(planned) != len(GROUPS):
        raise LabelCheckError("one planned number is needed for each group")
    result = {name: int(number) for name, number in zip(GROUPS, planned)}
    for name in GROUPS:
        if name != RECEIVES_SPARE_POINTS and sizes[name] < result[name]:
            result[RECEIVES_SPARE_POINTS] += result[name]
            result[name] = 0
    if sizes[RECEIVES_SPARE_POINTS] < result[RECEIVES_SPARE_POINTS]:
        raise LabelCheckError("the chip holds too few pixels that are not water for the planned points")
    return result


def draw(groups: np.ndarray, points: Mapping[str, int], *, seed: int, chip_number: int) -> list[dict[str, Any]]:
    """Draw the points of one chip: random pixels inside each group, none twice.

    The random numbers of a group depend on the seed, the number of the chip
    and the number of the group only, so one group can be drawn again alone.
    """

    raster = np.asarray(groups)
    drawn: list[dict[str, Any]] = []
    for index, name in enumerate(GROUPS):
        wanted = int(points[name])
        if wanted == 0:
            continue
        flat = np.flatnonzero(raster.ravel() == index)
        if flat.size < wanted:
            raise LabelCheckError(f"group {name} holds fewer pixels than its points")
        chosen = np.random.default_rng([seed, chip_number, index]).choice(flat, size=wanted, replace=False)
        for pixel in np.sort(chosen):
            row, column = divmod(int(pixel), raster.shape[1])
            drawn.append({"group": name, "row": row, "column": column})
    return drawn


def draw_practice(groups: np.ndarray, taken: Iterable[tuple[int, int]], *, seed: int) -> list[dict[str, Any]]:
    """One practice point of each group that has a pixel left, none of them among ``taken``."""

    raster = np.asarray(groups)
    used = {row * raster.shape[1] + column for row, column in taken}
    practice: list[dict[str, Any]] = []
    for index, name in enumerate(GROUPS):
        flat = np.flatnonzero(raster.ravel() == index)
        if flat.size == 0:
            continue
        order = np.random.default_rng([seed, 1000, index]).permutation(flat)
        pixel = next((int(value) for value in order if int(value) not in used), None)
        if pixel is None:
            continue
        row, column = divmod(pixel, raster.shape[1])
        practice.append({"group": name, "row": row, "column": column})
    return practice


def in_one_order(points: Sequence[Mapping[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    """Put the points of every chip in one random order and name them ``p001``, ``p002``, ..."""

    order = np.random.default_rng([seed, 2000]).permutation(len(points))
    width = max(3, len(str(len(points))))
    return [{"id": f"p{place + 1:0{width}d}", **dict(points[int(index)])} for place, index in enumerate(order)]


# ---------------------------------------------------------------------------
# The labels
# ---------------------------------------------------------------------------


def check_labels(labels: Mapping[str, Any], *, sample_id: str, point_ids: Sequence[str]) -> dict[str, str]:
    """Check one label file against the draw and return its label for every point.

    The file must name the draw it was made for and hold one of the three
    labels for every point, and no other point.
    """

    if labels.get("sample_id") != sample_id:
        raise LabelCheckError("the label file was made for another draw of points")
    if not str(labels.get("labeller", "")).strip():
        raise LabelCheckError("the label file names no labeller")
    given = labels.get("labels")
    if not isinstance(given, Mapping):
        raise LabelCheckError("the label file holds no labels")
    missing = [point for point in point_ids if point not in given]
    extra = sorted(set(given) - set(point_ids))
    if missing or extra:
        raise LabelCheckError(f"the label file misses {len(missing)} points and holds {len(extra)} unknown ones")
    result = {point: (given[point]["label"] if isinstance(given[point], Mapping) else given[point]) for point in point_ids}
    wrong = sorted({str(label) for label in result.values() if label not in LABELS})
    if wrong:
        raise LabelCheckError(f"labels that are not one of the three: {wrong}")
    return result


def agreed(first: Mapping[str, str], second: Mapping[str, str]) -> dict[str, str | None]:
    """The label a point is scored with: the one both gave, where it is water or not water; else ``None``."""

    if set(first) != set(second):
        raise LabelCheckError("the two labellers did not label the same points")
    return {point: (label if label == second[point] and label in (WATER, NOT_WATER) else None) for point, label in first.items()}


def alone(labels: Mapping[str, str]) -> dict[str, str | None]:
    """The scoring label of one labeller alone: water or not water; ``None`` where they could not tell."""

    return {point: (label if label in (WATER, NOT_WATER) else None) for point, label in labels.items()}


def between_labellers(first: Mapping[str, str], second: Mapping[str, str]) -> dict[str, Any]:
    """How far two labellers agree: the table of their labels, the share alike, and Cohen's kappa."""

    if set(first) != set(second) or not first:
        raise LabelCheckError("the two labellers did not label the same points")
    table = {a: {b: 0 for b in LABELS} for a in LABELS}
    for point, label in first.items():
        table[label][second[point]] += 1
    total = len(first)
    same = sum(table[label][label] for label in LABELS) / total
    by_chance = sum(
        sum(table[label].values()) * sum(table[other][label] for other in LABELS) for label in LABELS
    ) / total**2
    kappa = None if by_chance >= 1.0 else (same - by_chance) / (1.0 - by_chance)
    return {
        "points": total,
        "table_first_by_second": table,
        "share_same_label": round(same, 4),
        "share_same_by_chance": round(by_chance, 4),
        "cohens_kappa": None if kappa is None else round(kappa, 4),
    }


# ---------------------------------------------------------------------------
# The figures of a stratified random sample
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stratum:
    """One group of one chip: its number of pixels and, for each scored point, the two indicators of a ratio."""

    size: int
    y: tuple[float, ...]
    x: tuple[float, ...]


def stratified_ratio(strata: Sequence[Stratum]) -> dict[str, Any]:
    """The ratio of two totals from a stratified random sample, with its standard error.

    Stehman (2014), equations for a ratio estimator when the strata are not
    the map classes: the totals of ``y`` and of ``x`` are estimated by the
    stratum means times the stratum sizes, and the variance by the sample
    variances and covariance inside each stratum, with the finite population
    correction. A stratum with pixels and no scored point is left out and
    counted; one with a single point adds nothing to the variance.
    """

    used = [stratum for stratum in strata if stratum.size > 0 and len(stratum.y) > 0]
    without_a_point = sum(1 for stratum in strata if stratum.size > 0 and len(stratum.y) == 0)
    if any(len(stratum.y) != len(stratum.x) for stratum in used):
        raise LabelCheckError("a stratum needs one y and one x for each point")
    if any(len(stratum.y) > stratum.size for stratum in used):
        raise LabelCheckError("a stratum holds more points than pixels")
    total_y = sum(stratum.size * float(np.mean(stratum.y)) for stratum in used)
    total_x = sum(stratum.size * float(np.mean(stratum.x)) for stratum in used)
    points = sum(len(stratum.y) for stratum in used)
    base = {"points": points, "strata_without_a_scored_point": without_a_point,
            "strata_with_one_point": sum(1 for stratum in used if len(stratum.y) == 1)}
    if total_x <= 0:
        return {"estimate": None, "standard_error": None, "interval_95": None, **base}
    ratio = total_y / total_x
    variance = 0.0
    for stratum in used:
        n = len(stratum.y)
        if n < 2:
            continue
        y, x = np.asarray(stratum.y, dtype="float64"), np.asarray(stratum.x, dtype="float64")
        spread = float(np.var(y, ddof=1) + ratio**2 * np.var(x, ddof=1) - 2.0 * ratio * np.cov(y, x, ddof=1)[0, 1])
        variance += stratum.size**2 * (1.0 - n / stratum.size) * max(spread, 0.0) / n
    error = math.sqrt(variance) / total_x
    return {
        "estimate": round(ratio, 4),
        "standard_error": round(error, 4),
        "interval_95": [round(max(0.0, ratio - Z_95 * error), 4), round(min(1.0, ratio + Z_95 * error), 4)],
        **base,
    }


def wilson(successes: int, trials: int) -> dict[str, Any]:
    """A share of one group with its Wilson 95 percent interval."""

    if trials < 0 or not 0 <= successes <= max(trials, 0):
        raise LabelCheckError("successes must lie between 0 and trials")
    if trials == 0:
        return {"count": 0, "of": 0, "share": None, "interval_95": None}
    share = successes / trials
    centre = (share + Z_95**2 / (2 * trials)) / (1 + Z_95**2 / trials)
    half = Z_95 * math.sqrt(share * (1 - share) / trials + Z_95**2 / (4 * trials**2)) / (1 + Z_95**2 / trials)
    return {"count": successes, "of": trials, "share": round(share, 4),
            "interval_95": [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]}


def _strata(points: Sequence[Mapping[str, Any]], scoring: Mapping[str, str | None], sizes: Mapping[tuple[str, str], int],
            chips: Sequence[str], groups: Sequence[str], y_of: Any, x_of: Any) -> list[Stratum]:
    strata = []
    for chip in chips:
        for group in groups:
            scored = [scoring[point["id"]] for point in points
                      if point["chip"] == chip and point["group"] == group and scoring[point["id"]] is not None]
            rule_water = group in WATER_GROUPS
            strata.append(Stratum(
                size=int(sizes[(chip, group)]),
                y=tuple(float(y_of(rule_water, label == WATER)) for label in scored),
                x=tuple(float(x_of(rule_water, label == WATER)) for label in scored),
            ))
    return strata


def figures(points: Sequence[Mapping[str, Any]], scoring: Mapping[str, str | None],
            sizes: Mapping[tuple[str, str], int], chips: Sequence[str]) -> dict[str, Any]:
    """Figures a to g of the plan for one set of chips and one set of scoring labels.

    ``points`` hold ``id``, ``chip`` and ``group``; ``scoring`` gives each point
    water, not water or ``None`` (left out); ``sizes`` gives the pixels of each
    group of each chip.
    """

    def ratio(groups: Sequence[str], y_of: Any, x_of: Any) -> dict[str, Any]:
        return stratified_ratio(_strata(points, scoring, sizes, chips, groups, y_of, x_of))

    def one(_rule: bool, _label: bool) -> bool:
        return True

    inside_only = tuple(group for group in ANSWERED_GROUPS if group not in EDGE_GROUPS)
    answered_pixels = sum(sizes[(chip, group)] for chip in chips for group in ANSWERED_GROUPS)
    water_pixels = sum(sizes[(chip, group)] for chip in chips for group in WATER_GROUPS)
    same_at_edges = ratio(EDGE_GROUPS, lambda rule, label: rule == label, one)

    def counted(group: str) -> dict[str, Any]:
        mine = [point["id"] for point in points if point["chip"] in chips and point["group"] == group]
        scored = [scoring[point] for point in mine if scoring[point] is not None]
        return {"points": len(mine), "left_out": len(mine) - len(scored),
                "labelled_water": wilson(sum(1 for label in scored if label == WATER), len(scored))}

    in_chips = [point for point in points if point["chip"] in chips]
    return {
        "chips": list(chips),
        "points": len(in_chips),
        "points_scored": sum(1 for point in in_chips if scoring[point["id"]] is not None),
        "points_left_out_by_group": {
            group: sum(1 for point in in_chips if point["group"] == group and scoring[point["id"]] is None) for group in GROUPS
        },
        "a_share_of_rule_water_labelled_water": ratio(WATER_GROUPS, lambda rule, label: label, one),
        "b_share_of_labelled_water_the_rule_finds": ratio(
            ANSWERED_GROUPS, lambda rule, label: rule and label, lambda rule, label: label),
        "c_share_of_answered_area_where_both_say_the_same": ratio(ANSWERED_GROUPS, lambda rule, label: rule == label, one),
        "d_water_share_of_answered_area": {
            "by_the_rule": None if answered_pixels == 0 else round(water_pixels / answered_pixels, 4),
            "by_the_labels": ratio(ANSWERED_GROUPS, lambda rule, label: label, one),
        },
        "e_dropped_small_objects": counted("dropped_small_object"),
        "f_unobservable": counted("unobservable"),
        "g_edges": {
            "a_without_the_edge_groups": ratio(("water_inside",), lambda rule, label: label, one),
            "b_without_the_edge_groups": ratio(inside_only, lambda rule, label: rule and label, lambda rule, label: label),
            "share_of_edge_area_where_rule_and_labels_differ": {
                **same_at_edges,
                "estimate": None if same_at_edges["estimate"] is None else round(1.0 - same_at_edges["estimate"], 4),
                "interval_95": None if same_at_edges["interval_95"] is None else [
                    round(1.0 - same_at_edges["interval_95"][1], 4), round(1.0 - same_at_edges["interval_95"][0], 4)],
            },
        },
    }


def label_counts(points: Sequence[Mapping[str, Any]], labels: Mapping[str, str], chips: Sequence[str]) -> dict[str, dict[str, int]]:
    """For one labeller, the number of points of each group given each of the three labels."""

    counts = {group: {label: 0 for label in LABELS} for group in GROUPS}
    for point in points:
        if point["chip"] in chips:
            counts[point["group"]][labels[point["id"]]] += 1
    return counts
