"""Radar flood detection, second round: a dry-season baseline, a cut set per scene, cleaning, and the plan's rules.

The plan is ``docs/proposal_execution/radar_detection_improvement_plan_v1.md``. This module holds the pure parts
of its six changes:

* A and C: features of the image after an event measured against the median of dry-season passes;
* B: a cut that each scene sets for itself, from the tiles of the scene that hold two clear groups of values;
* E: cleaning after the cut (slopes, small groups, growth into nearly-as-dark neighbours);
* F: which cells the radar cannot be asked about;
* the rule by which a change is kept, and the sentences fixed for the one test.

Every figure made with these functions is agreement with a reference layer, not accuracy. Nothing here computes
a planning score or a class.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from floodguard import radar_flood_classifier as rfc

FEATURES_BASELINE: tuple[str, ...] = (
    "vv_after_db", "vh_after_db", "vv_anomaly_db", "vh_anomaly_db", "vv_dry_db", "vh_dry_db",
    "vv_dry_spread_db", "vh_dry_spread_db", "vh_minus_vv_after_db", "vh_after_spread_db", "slope_deg", "land_cover",
)
NOT_OBSERVABLE_CLASSES: tuple[int, ...] = (10, 50)
"""ESA WorldCover classes where C-band radar is not asked about water: tree cover and built-up."""

TILE_CELLS = 256
TILE_MIN_VALID_SHARE = 0.5
TILE_MIN_SIDE_SHARE = 0.10
TILE_MIN_SEPARATION = 4.0
"""Two groups must stand this many pooled spreads apart. One bell-shaped group cut at its middle already gives
2.65, so the bar is set well above that. Fixed on invented data, before any scene was read."""
MAX_SLOPE_DEG = 5.0
MIN_GROUP_CELLS = 8
GROW_DB = 1.5
KEEP_MARGIN_IOU = 0.02
IMPROVED_MARGIN_IOU = 0.03
IMPROVED_MIN_PRECISION = 0.70


class RadarDetectionError(ValueError):
    """The inputs of the detection do not fit together."""


def baseline_features(after: np.ndarray, dry_median_db: np.ndarray, dry_spread_db: np.ndarray, slope: np.ndarray,
                      land_cover: np.ndarray) -> dict[str, np.ndarray]:
    """Features of one image after an event, measured against the dry-season baseline of the same cells.

    ``after`` is ``(2, H, W)`` linear gamma0, VV before VH; ``dry_median_db`` and ``dry_spread_db`` are
    ``(2, H, W)`` in dB (:func:`floodguard.s1_rtc.median_of_passes`). The anomaly is the image after minus the
    dry-season median, both as 5 by 5 means: negative where the ground went dark.
    """

    image = np.asarray(after, dtype="float64")
    median = np.asarray(dry_median_db, dtype="float64")
    spread = np.asarray(dry_spread_db, dtype="float64")
    if image.ndim != 3 or image.shape[0] != 2 or median.shape != image.shape or spread.shape != image.shape:
        raise RadarDetectionError("the image after and the two baseline rasters must be (2, H, W) arrays of one shape")
    if np.asarray(slope).shape != image.shape[1:] or np.asarray(land_cover).shape != image.shape[1:]:
        raise RadarDetectionError("slope and land cover must have the shape of the image")
    vv_after, vh_after = rfc.to_db(rfc.focal_mean(image[0])), rfc.to_db(rfc.focal_mean(image[1]))
    vv_dry, vh_dry = rfc.focal_mean(median[0]), rfc.focal_mean(median[1])
    vh_cell = rfc.to_db(image[1])
    mean = rfc.focal_mean(vh_cell)
    texture = np.sqrt(np.clip(rfc.focal_mean(vh_cell ** 2) - mean ** 2, 0.0, None))
    features = {
        "vv_after_db": vv_after, "vh_after_db": vh_after, "vv_anomaly_db": vv_after - vv_dry, "vh_anomaly_db": vh_after - vh_dry,
        "vv_dry_db": vv_dry, "vh_dry_db": vh_dry, "vv_dry_spread_db": rfc.focal_mean(spread[0]), "vh_dry_spread_db": rfc.focal_mean(spread[1]),
        "vh_minus_vv_after_db": vh_after - vv_after, "vh_after_spread_db": texture,
        "slope_deg": np.asarray(slope, dtype="float64"), "land_cover": np.asarray(land_cover, dtype="float64"),
    }
    return {name: features[name].astype("float32") for name in FEATURES_BASELINE}


def otsu_split(values: np.ndarray, *, bins: int = 128) -> dict[str, float] | None:
    """Otsu's threshold of a sample, with how well it separates two groups.

    Returns the threshold, the share of values at or below it, and the separation: the distance of the two group
    means in units of the pooled spread inside the groups. ``None`` for a sample with one value only.
    """

    sample = np.asarray(values, dtype="float64").ravel()
    sample = sample[np.isfinite(sample)]
    if sample.size < 2 or sample.min() == sample.max():
        return None
    counts, edges = np.histogram(sample, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    weight = counts / counts.sum()
    below = np.cumsum(weight)
    mass = np.cumsum(weight * centres)
    total = mass[-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        between = (total * below - mass) ** 2 / (below * (1 - below))
    between[~np.isfinite(between)] = -1.0
    best = int(np.argmax(between[:-1]))
    threshold = float(edges[best + 1])
    low, high = sample[sample <= threshold], sample[sample > threshold]
    if low.size == 0 or high.size == 0:
        return None
    pooled = float(np.sqrt((low.var() * low.size + high.var() * high.size) / sample.size))
    separation = float((high.mean() - low.mean()) / pooled) if pooled > 0 else float("inf")
    return {"threshold": threshold, "share_at_or_below": float(low.size / sample.size), "separation": separation}


def scene_cut(values: np.ndarray, valid: np.ndarray, *, fallback: float, tile_cells: int = TILE_CELLS) -> dict[str, Any]:
    """The cut a scene sets for itself: the median Otsu threshold of its tiles that hold two clear groups.

    A tile counts when at least half of it is valid, each side of its split holds a tenth of its values or more,
    and the two groups stand at least four pooled spreads apart. A scene without such a tile shows one group only
    and takes ``fallback``.
    """

    data = np.asarray(values, dtype="float64")
    if data.ndim != 2 or np.asarray(valid).shape != data.shape:
        raise RadarDetectionError("values and valid must be two rasters of one shape")
    usable = np.asarray(valid, dtype=bool) & np.isfinite(data)
    thresholds, tiles = [], 0
    for row in range(0, data.shape[0], tile_cells):
        for column in range(0, data.shape[1], tile_cells):
            window = (slice(row, row + tile_cells), slice(column, column + tile_cells))
            inside = usable[window]
            tiles += 1
            if inside.sum() < TILE_MIN_VALID_SHARE * tile_cells * tile_cells:
                continue
            split = otsu_split(data[window][inside])
            if split is None:
                continue
            side = min(split["share_at_or_below"], 1 - split["share_at_or_below"])
            if side >= TILE_MIN_SIDE_SHARE and split["separation"] >= TILE_MIN_SEPARATION:
                thresholds.append(split["threshold"])
    if thresholds:
        return {"cut": float(np.median(thresholds)), "source": "the scene's own tiles", "tiles": tiles, "tiles_with_two_groups": len(thresholds)}
    return {"cut": float(fallback), "source": "the frozen cut: no tile of the scene holds two clear groups", "tiles": tiles, "tiles_with_two_groups": 0}


def clean(flag: np.ndarray, slope: np.ndarray, *, grow_from: np.ndarray | None = None, max_slope: float = MAX_SLOPE_DEG,
          min_group: int = MIN_GROUP_CELLS) -> np.ndarray:
    """Clean the flags of a scene.

    Flags on slopes of ``max_slope`` degrees or more are dropped, then connected groups (8 neighbours) of fewer
    than ``min_group`` cells. With ``grow_from`` (the cells that are nearly as dark as a flagged cell), a kept
    group grows into the connected cells of ``grow_from`` it touches.
    """

    from scipy import ndimage

    flags = np.asarray(flag, dtype=bool)
    gentle = np.asarray(slope, dtype="float64") < max_slope
    if flags.shape != gentle.shape or flags.ndim != 2:
        raise RadarDetectionError("flags and slope must be two rasters of one shape")
    everything = np.ones((3, 3), dtype=bool)

    def large_groups(mask: np.ndarray) -> np.ndarray:
        labels, count = ndimage.label(mask, structure=everything)
        if count == 0:
            return mask
        sizes = np.bincount(labels.ravel())
        keep = sizes >= min_group
        keep[0] = False
        return keep[labels]

    kept = large_groups(flags & gentle)
    if grow_from is None:
        return kept
    wider = (np.asarray(grow_from, dtype=bool) | kept) & gentle
    labels, count = ndimage.label(wider, structure=everything)
    if count == 0:
        return kept
    seeded = np.zeros(count + 1, dtype=bool)
    seeded[np.unique(labels[kept])] = True
    seeded[0] = False
    return seeded[labels]


def observable(land_cover: np.ndarray) -> np.ndarray:
    """Cells where the radar can be asked about water: everything but tree cover and built-up ground."""

    return ~np.isin(np.asarray(land_cover), NOT_OBSERVABLE_CLASSES)


def keep_changes(steps: Sequence[Mapping[str, Any]], *, margin: float = KEEP_MARGIN_IOU) -> dict[str, Any]:
    """Apply the plan's rule for keeping a change.

    ``steps`` are in the order they were tried; each has a ``name`` and ``iou`` by held-out area. The first is
    the baseline to beat. A later step is kept only when its intersection over union is higher than that of the
    step kept before it, by ``margin`` or more, on every area.
    """

    if not steps:
        raise RadarDetectionError("at least the baseline step is needed")
    areas = sorted(steps[0]["iou"])
    kept = steps[0]
    trail = [{"name": kept["name"], "iou": dict(kept["iou"]), "kept": True, "why": "the baseline to beat"}]
    for step in steps[1:]:
        if sorted(step["iou"]) != areas:
            raise RadarDetectionError("every step must be scored on the same held-out areas")
        gains = {area: None if step["iou"][area] is None or kept["iou"][area] is None
                 else round(float(step["iou"][area]) - float(kept["iou"][area]), 6) for area in areas}
        better = all(gain is not None and gain >= margin for gain in gains.values())
        trail.append({"name": step["name"], "iou": dict(step["iou"]), "gain_over_the_step_kept_before": gains, "kept": bool(better),
                      "why": f"better by {margin} or more on every held-out area" if better
                      else f"not better by {margin} on every held-out area"})
        if better:
            kept = step
    return {"margin_in_iou": margin, "held_out_areas": areas, "steps": trail, "kept": kept["name"]}


def statement_for_the_test(frozen: Mapping[str, Any], threshold: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]], *,
                   frozen_is_the_threshold: bool = False) -> dict[str, Any]:
    """The sentences the plan fixed for the one test on the held-out chips.

    Each argument holds ``iou`` and ``flagged_that_is_reference_water`` on the held-out chips together.
    """

    if not rules or any(entry.get("iou") is None for entry in rules.values()):
        raise RadarDetectionError("every fixed rule needs a figure")
    best_rule = max(rules, key=lambda name: rules[name]["iou"])
    best = float(rules[best_rule]["iou"])

    def improved(entry: Mapping[str, Any]) -> bool:
        return bool(entry.get("iou") is not None and entry["iou"] - best >= IMPROVED_MARGIN_IOU
                    and (entry.get("flagged_that_is_reference_water") or 0) >= IMPROVED_MIN_PRECISION)

    frozen_improved, threshold_improved = improved(frozen), improved(threshold)
    beats_threshold = bool(not frozen_is_the_threshold and frozen.get("iou") is not None and threshold.get("iou") is not None
                           and frozen["iou"] - threshold["iou"] >= IMPROVED_MARGIN_IOU)
    if frozen_is_the_threshold:
        named = "simple_threshold" if threshold_improved else "fixed_rules"
        said = ("The simple threshold was the detector frozen for the test. It is better than the best fixed rule on the "
                "held-out chips and is the detector the project names." if threshold_improved else
                "The simple threshold was the detector frozen for the test. It is not better than the fixed rules on the "
                "held-out chips; the fixed rules stay.")
    elif frozen_improved and beats_threshold:
        named, said = "frozen_detector", "The frozen detector is improved: better than the best fixed rule and better than the simple threshold."
    elif threshold_improved or frozen_improved:
        named = "simple_threshold"
        said = ("The frozen detector is not better than the simple threshold by the margin. The simple threshold is the "
                "detector the project names; nothing more complex was needed.")
    else:
        named, said = "fixed_rules", "Neither the frozen detector nor the simple threshold is better than the fixed rules; the fixed rules stay."
    return {"best_fixed_rule": best_rule, "best_fixed_rule_iou": best, "margin_in_iou": IMPROVED_MARGIN_IOU,
            "min_share_of_flags_on_water": IMPROVED_MIN_PRECISION, "frozen_detector_improved": frozen_improved,
            "simple_threshold_improved": threshold_improved, "frozen_better_than_the_simple_threshold": beats_threshold,
            "detector_the_project_names": named, "what_is_said": said}
