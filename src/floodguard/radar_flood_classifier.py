"""A supervised radar flood classifier: features of an image pair, a weighted sample, and the counting (work package 7).

The plan is ``docs/proposal_execution/radar_flood_classifier_plan_v1.md``. The classifier is an observation model:
every feature comes from a Sentinel-1 image pair or is a mask the fixed radar rules use as well (slope, land
cover). No feature says where water usually stands.

It is report-only. Nothing here computes a planning score or a class, and every figure made with these functions
is agreement with a reference layer, not accuracy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from floodguard import flood_susceptibility_ml as ml

SEED = 20261009
WINDOW = 5
MAX_WATER_CELLS = 150_000
MAX_OTHER_CELLS = 450_000
BETTER_BY_IOU = 0.03
WITHHELD_LOW, WITHHELD_HIGH = 0.3, 0.7
CUTS = tuple(round(0.02 * step, 2) for step in range(1, 50))

FEATURES_ALL: tuple[str, ...] = (
    "vv_after_db", "vh_after_db", "vv_before_db", "vh_before_db", "vv_change_db", "vh_change_db",
    "vh_minus_vv_after_db", "vh_after_spread_db", "slope_deg", "land_cover",
)
FEATURES_AFTER_ONLY: tuple[str, ...] = (
    "vv_after_db", "vh_after_db", "vh_minus_vv_after_db", "vh_after_spread_db", "slope_deg", "land_cover",
)
FEATURES_BASELINE: tuple[str, ...] = ("vh_after_db",)

BASELINE = "baseline_logistic_vh_after"
PRIMARY = "gradient_boosted_trees_all_features"
RANDOM_FOREST = "random_forest_all_features"
AFTER_ONLY = "gradient_boosted_trees_after_only"
MODELS: dict[str, dict[str, Any]] = {
    BASELINE: {"kind": ml.BASELINE, "features": FEATURES_BASELINE, "grid": (None,)},
    PRIMARY: {"kind": ml.GRADIENT_BOOSTING, "features": FEATURES_ALL,
              "grid": tuple({"learning_rate": rate, "max_leaf_nodes": leaves} for rate in (0.05, 0.1) for leaves in (15, 31))},
    RANDOM_FOREST: {"kind": ml.RANDOM_FOREST, "features": FEATURES_ALL, "grid": ({"min_samples_leaf": 20},)},
    AFTER_ONLY: {"kind": ml.GRADIENT_BOOSTING, "features": FEATURES_AFTER_ONLY,
                 "grid": tuple({"learning_rate": rate, "max_leaf_nodes": leaves} for rate in (0.05, 0.1) for leaves in (15, 31))},
}


class RadarClassifierError(ValueError):
    """The inputs of the classifier do not fit together."""


def focal_mean(values: np.ndarray, size: int = WINDOW) -> np.ndarray:
    """Mean of the valid values in a ``size`` by ``size`` window; NaN where the window holds none."""

    from scipy.ndimage import uniform_filter

    data = np.asarray(values, dtype="float64")
    valid = np.isfinite(data)
    total = uniform_filter(np.where(valid, data, 0.0), size=size, mode="constant", cval=0.0)
    share = uniform_filter(valid.astype("float64"), size=size, mode="constant", cval=0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(share > 1e-9, total / share, np.nan)


def to_db(linear: np.ndarray) -> np.ndarray:
    values = np.asarray(linear, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.isfinite(values) & (values > 0), 10.0 * np.log10(values), np.nan)


def pair_features(before: np.ndarray, after: np.ndarray, slope: np.ndarray, land_cover: np.ndarray) -> dict[str, np.ndarray]:
    """The features of plan section 4 for one image pair.

    ``before`` and ``after`` are ``(2, H, W)`` linear gamma0, VV before VH. Backscatter is averaged in a 5 by 5
    window in linear units and then turned into dB, as the fixed rules filter before they compare.
    """

    first = np.asarray(before, dtype="float64")
    second = np.asarray(after, dtype="float64")
    if first.shape != second.shape or first.ndim != 3 or first.shape[0] != 2:
        raise RadarClassifierError("before and after must be two (2, H, W) images of one shape")
    if np.asarray(slope).shape != first.shape[1:] or np.asarray(land_cover).shape != first.shape[1:]:
        raise RadarClassifierError("slope and land cover must have the shape of the images")
    vv_after, vh_after = to_db(focal_mean(second[0])), to_db(focal_mean(second[1]))
    vv_before, vh_before = to_db(focal_mean(first[0])), to_db(focal_mean(first[1]))
    vh_after_cell = to_db(second[1])
    mean = focal_mean(vh_after_cell)
    spread = np.sqrt(np.clip(focal_mean(vh_after_cell ** 2) - mean ** 2, 0.0, None))
    features = {
        "vv_after_db": vv_after, "vh_after_db": vh_after, "vv_before_db": vv_before, "vh_before_db": vh_before,
        "vv_change_db": vv_after - vv_before, "vh_change_db": vh_after - vh_before,
        "vh_minus_vv_after_db": vh_after - vv_after, "vh_after_spread_db": spread,
        "slope_deg": np.asarray(slope, dtype="float64"), "land_cover": np.asarray(land_cover, dtype="float64"),
    }
    return {name: features[name].astype("float32") for name in FEATURES_ALL}


def usable_cells(features: Mapping[str, np.ndarray], names: Sequence[str] = FEATURES_ALL) -> np.ndarray:
    """Cells where every named feature has a value."""

    usable = None
    for name in names:
        finite = np.isfinite(features[name])
        usable = finite if usable is None else usable & finite
    if usable is None:
        raise RadarClassifierError("no feature was named")
    return usable


def draw_sample(label: np.ndarray, *, max_water: int = MAX_WATER_CELLS, max_other: int = MAX_OTHER_CELLS,
                seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """Pick the cells of the training sample and the weight that puts the true share of water back.

    Water cells and other cells are drawn at random, each at one rate for all districts, so every district keeps
    its share of each. Returns the sorted indices and, for each, how many cells of the frame it stands for.
    """

    wet = np.asarray(label, dtype=bool).ravel()
    if wet.size == 0 or wet.all() or not wet.any():
        raise RadarClassifierError("the sample needs cells of both kinds")
    rng = np.random.default_rng(seed)
    chosen, weights = [], []
    for value, limit in ((True, max_water), (False, max_other)):
        members = np.flatnonzero(wet == value)
        take = min(limit, members.size)
        chosen.append(rng.choice(members, size=take, replace=False))
        weights.append(np.full(take, members.size / take, dtype="float64"))
    index = np.concatenate(chosen)
    order = np.argsort(index)
    return index[order], np.concatenate(weights)[order]


def weighted_isotonic(raw: np.ndarray, label: np.ndarray, weight: np.ndarray) -> Any:
    """Isotonic calibration on out-of-fold values, with the weights of the sample."""

    from sklearn.isotonic import IsotonicRegression

    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
        np.asarray(raw, dtype="float64"), np.asarray(label, dtype="float64"), sample_weight=np.asarray(weight, dtype="float64"))


def flag_counts(flagged: np.ndarray, label: np.ndarray, weight: np.ndarray | None = None) -> dict[str, Any]:
    """Of the flagged cells the share that is reference water, of the reference water the share flagged, and IoU."""

    yes = np.asarray(flagged, dtype=bool).ravel()
    wet = np.asarray(label, dtype=bool).ravel()
    if yes.shape != wet.shape:
        raise RadarClassifierError("flags and labels must have one length")
    scale = np.ones(yes.size, dtype="float64") if weight is None else np.asarray(weight, dtype="float64").ravel()
    tp = float(scale[yes & wet].sum())
    fp = float(scale[yes & ~wet].sum())
    fn = float(scale[~yes & wet].sum())
    return {
        "flagged_cells": round(tp + fp, 1), "reference_water_cells": round(tp + fn, 1),
        "flagged_that_is_reference_water": round(tp / (tp + fp), 6) if tp + fp else None,
        "reference_water_flagged": round(tp / (tp + fn), 6) if tp + fn else None,
        "iou": round(tp / (tp + fp + fn), 6) if tp + fp + fn else None,
    }


def best_cut(probability: np.ndarray, label: np.ndarray, weight: np.ndarray, cuts: Sequence[float] = CUTS) -> dict[str, Any]:
    """The cut with the highest weighted intersection over union; the lowest such cut on a tie."""

    values = np.asarray(probability, dtype="float64")
    trials = [{"cut": float(cut), **flag_counts(values >= cut, label, weight)} for cut in cuts]
    scored = [trial for trial in trials if trial["iou"] is not None]
    if not scored:
        raise RadarClassifierError("no cut flags a cell")
    best = max(scored, key=lambda trial: (trial["iou"], -trial["cut"]))
    return {"cut": best["cut"], "iou_out_of_fold": best["iou"], "trials": trials}


def ranking(probability: np.ndarray, label: np.ndarray, weight: np.ndarray | None = None) -> dict[str, Any]:
    """ROC AUC and average precision; empty when the labels hold one kind only."""

    from sklearn.metrics import average_precision_score, roc_auc_score

    wet = np.asarray(label, dtype=bool)
    if wet.all() or not wet.any():
        return {"roc_auc": None, "average_precision": None, "note": "one class only"}
    return {"roc_auc": round(float(roc_auc_score(wet, probability, sample_weight=weight)), 6),
            "average_precision": round(float(average_precision_score(wet, probability, sample_weight=weight)), 6)}


def withheld(probability: np.ndarray, label: np.ndarray, *, low: float = WITHHELD_LOW, high: float = WITHHELD_HIGH) -> dict[str, Any]:
    """Cells left without an answer when values between ``low`` and ``high`` are withheld, and the counts on the rest."""

    values = np.asarray(probability, dtype="float64")
    answered = (values < low) | (values > high)
    return {"withheld_between": [low, high], "cells": int(values.size), "cells_with_an_answer": int(answered.sum()),
            "share_with_an_answer": round(float(answered.mean()), 6) if values.size else None,
            "on_answered_cells": flag_counts(values[answered] > high, np.asarray(label, dtype=bool).ravel()[answered])}


def statement(model_iou: Mapping[str, float | None], rule_iou: Mapping[str, float | None], *,
              primary: str = PRIMARY, margin: float = BETTER_BY_IOU) -> dict[str, Any]:
    """Apply plan section 8 to the figures of test B.

    A model is "better than a fixed rule" when its intersection over union is higher by ``margin`` or more. The
    classifier is named as an improvement only when the primary model is better than every fixed rule.
    """

    if primary not in model_iou:
        raise RadarClassifierError("the primary model has no figure")
    if not rule_iou or any(value is None for value in rule_iou.values()):
        raise RadarClassifierError("every fixed rule needs a figure")
    better = {
        model: {rule: bool(value is not None and value - float(other) >= margin) for rule, other in rule_iou.items()}
        for model, value in model_iou.items()}
    beats_all = {model: all(row.values()) for model, row in better.items()}
    others = sorted(model for model, wins in beats_all.items() if wins and model != primary)
    if beats_all[primary]:
        said = "The primary model is better than all three fixed rules on the independent test."
    elif others:
        said = ("The primary model is not better than all three fixed rules on the independent test. A comparison "
                "model is, and it is not renamed as the result.")
    else:
        said = ("No model is better than all three fixed rules on the independent test. A classifier trained on "
                "agency labels of one date did not carry over; the fixed rules stay the project's radar reading.")
    return {"margin_in_iou": margin, "better_than_each_fixed_rule": better, "better_than_all_fixed_rules": beats_all,
            "classifier_named_as_an_improvement": bool(beats_all[primary]),
            "comparison_models_better_than_all_fixed_rules": others, "what_is_said": said}
