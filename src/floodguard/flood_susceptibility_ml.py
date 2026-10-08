"""A trained flood-susceptibility model: the pure parts (plan: ``docs/proposal_execution/flood_susceptibility_model_plan_v1.md``).

Spatial folds, the three models of the plan, calibration and the figures the plan fixes. Everything here works on
arrays; ``scripts/build_flood_susceptibility_model.py`` builds the features and reads the label.

The label is an agency season layer, not ground truth, so every figure is agreement with that layer. The model
says how likely a place is to lie inside the area mapped as water in one season. It is not a flood map of any
day, it feeds no score, and nothing here is an official warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

SEED = 20261008
BLOCK_M = 3000.0
FOLDS = 5
ABSTAIN_LOW, ABSTAIN_HIGH = 0.3, 0.7
CITE_MARGIN = 0.02
BASELINE = "baseline_logistic_hand"
RANDOM_FOREST = "random_forest"
GRADIENT_BOOSTING = "gradient_boosted_trees"
RANDOM_FOREST_GRID: tuple[dict[str, Any], ...] = ({"min_samples_leaf": 20}, {"min_samples_leaf": 100})
GRADIENT_BOOSTING_GRID: tuple[dict[str, Any], ...] = tuple(
    {"learning_rate": rate, "max_leaf_nodes": leaves} for rate in (0.05, 0.1) for leaves in (15, 31))


class SusceptibilityError(ValueError):
    """The arrays or the settings cannot support the model."""


def block_folds(x: np.ndarray, y: np.ndarray, *, block_m: float = BLOCK_M, folds: int = FOLDS, seed: int = SEED) -> np.ndarray:
    """Give every cell a fold, by the block of ``block_m`` metres its centre lies in.

    All cells of one block share a fold, so a fold is never tested on ground whose next-door cells it was fitted
    on. Blocks are dealt to folds in a shuffled order that depends only on the seed and the set of blocks.
    """

    east = np.asarray(x, dtype="float64")
    north = np.asarray(y, dtype="float64")
    if east.shape != north.shape or east.ndim != 1 or east.size == 0:
        raise SusceptibilityError("x and y must be one-dimensional and of one length")
    if folds < 2 or block_m <= 0:
        raise SusceptibilityError("at least two folds and a positive block size are needed")
    columns = np.floor(east / block_m).astype("int64")
    rows = np.floor(north / block_m).astype("int64")
    keys = columns * 1_000_003 + rows
    blocks, inverse = np.unique(keys, return_inverse=True)
    if blocks.size < folds:
        raise SusceptibilityError("fewer blocks than folds")
    order = np.random.default_rng(seed).permutation(blocks.size)
    fold_of_block = np.empty(blocks.size, dtype="int64")
    fold_of_block[order] = np.arange(blocks.size) % folds
    return fold_of_block[inverse]


def make_model(kind: str, settings: Mapping[str, Any] | None = None, *, seed: int = SEED) -> Any:
    """Build one of the three models of the plan, unfitted."""

    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    chosen = dict(settings or {})
    if kind == BASELINE:
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    if kind == RANDOM_FOREST:
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=int(chosen.get("min_samples_leaf", 20)),
                                      max_features="sqrt", n_jobs=-1, random_state=seed)
    if kind == GRADIENT_BOOSTING:
        return HistGradientBoostingClassifier(max_iter=200, learning_rate=float(chosen.get("learning_rate", 0.1)),
                                              max_leaf_nodes=int(chosen.get("max_leaf_nodes", 31)),
                                              l2_regularization=1.0, random_state=seed)
    raise SusceptibilityError(f"unknown model kind {kind!r}")


def out_of_fold(kind: str, settings: Mapping[str, Any] | None, features: np.ndarray, label: np.ndarray,
                folds: np.ndarray, *, seed: int = SEED) -> np.ndarray:
    """Predict every cell with a model that was fitted without the cell's fold."""

    values = np.asarray(features, dtype="float64")
    target = np.asarray(label).astype("int64")
    groups = np.asarray(folds)
    if values.ndim != 2 or values.shape[0] != target.shape[0] or groups.shape != target.shape:
        raise SusceptibilityError("features, label and folds must describe the same cells")
    predicted = np.full(target.shape, np.nan, dtype="float64")
    for fold in np.unique(groups):
        held_out = groups == fold
        if np.unique(target[~held_out]).size < 2:
            raise SusceptibilityError("a training fold holds one class only")
        model = make_model(kind, settings, seed=seed)
        model.fit(values[~held_out], target[~held_out])
        predicted[held_out] = model.predict_proba(values[held_out])[:, 1]
    return predicted


def fit_isotonic(raw: np.ndarray, label: np.ndarray) -> Any:
    """Isotonic calibration of raw model values against the label (fitted on out-of-fold values)."""

    from sklearn.isotonic import IsotonicRegression

    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit(np.asarray(raw, dtype="float64"), np.asarray(label, dtype="float64"))
    return calibrator


def reliability_table(probability: np.ndarray, label: np.ndarray, *, bins: int = 10) -> list[dict[str, Any]]:
    """Cells, mean value and flooded share in each of ``bins`` bins of equal width over 0 to 1."""

    p = np.asarray(probability, dtype="float64")
    y = np.asarray(label, dtype="float64")
    if p.shape != y.shape or p.ndim != 1:
        raise SusceptibilityError("probability and label must be one-dimensional and of one length")
    index = np.minimum((p * bins).astype("int64"), bins - 1)
    rows = []
    for position in range(bins):
        inside = index == position
        count = int(inside.sum())
        rows.append({
            "from": round(position / bins, 2), "to": round((position + 1) / bins, 2), "cells": count,
            "mean_value": round(float(p[inside].mean()), 6) if count else None,
            "flooded_share": round(float(y[inside].mean()), 6) if count else None,
        })
    return rows


def expected_calibration_error(probability: np.ndarray, label: np.ndarray, *, bins: int = 10) -> float:
    """The cell-weighted mean gap between the mean value and the flooded share of each bin."""

    table = reliability_table(probability, label, bins=bins)
    total = sum(row["cells"] for row in table)
    if total == 0:
        raise SusceptibilityError("no cell to calibrate on")
    return round(sum(row["cells"] * abs(row["mean_value"] - row["flooded_share"]) for row in table if row["cells"]) / total, 6)


def abstention(probability: np.ndarray, label: np.ndarray, *, low: float = ABSTAIN_LOW, high: float = ABSTAIN_HIGH) -> dict[str, Any]:
    """Give no answer between ``low`` and ``high``; report the share with an answer and the agreement on it."""

    p = np.asarray(probability, dtype="float64")
    y = np.asarray(label).astype(bool)
    answered = (p < low) | (p > high)
    count = int(answered.sum())
    agree = int(((p > high) & y).sum() + ((p < low) & ~y).sum())
    return {
        "no_answer_from": low, "no_answer_to": high,
        "cells": int(p.size), "cells_with_an_answer": count,
        "share_with_an_answer": round(count / p.size, 6) if p.size else None,
        "agreement_on_answered_cells": round(agree / count, 6) if count else None,
        "agreement_if_every_cell_is_answered_at_0.5": round(float(((p > 0.5) == y).mean()), 6) if p.size else None,
    }


def risk_coverage(probability: np.ndarray, label: np.ndarray, *, steps: int = 10) -> list[dict[str, Any]]:
    """Agreement on the most confident cells, for growing shares of the cells (confidence is distance from 0.5)."""

    p = np.asarray(probability, dtype="float64")
    y = np.asarray(label).astype(bool)
    if p.size == 0:
        raise SusceptibilityError("no cell")
    order = np.argsort(-np.abs(p - 0.5), kind="stable")
    correct = ((p > 0.5) == y)[order]
    cumulative = np.cumsum(correct)
    rows = []
    for step in range(1, steps + 1):
        kept = max(1, int(round(p.size * step / steps)))
        rows.append({"share_of_cells_answered": round(step / steps, 2), "cells": kept,
                     "agreement": round(float(cumulative[kept - 1] / kept), 6)})
    return rows


def scores(probability: np.ndarray, label: np.ndarray, *, training_prevalence: float) -> dict[str, Any]:
    """The figures the plan fixes for one set of cells."""

    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    p = np.asarray(probability, dtype="float64")
    y = np.asarray(label).astype("int64")
    if np.unique(y).size < 2:
        return {"cells": int(y.size), "flooded_cells": int(y.sum()), "note": "one class only: no ranking figure"}
    reference = float(np.mean((training_prevalence - y) ** 2))
    brier = float(brier_score_loss(y, p))
    return {
        "cells": int(y.size), "flooded_cells": int(y.sum()), "flooded_share": round(float(y.mean()), 6),
        "roc_auc": round(float(roc_auc_score(y, p)), 6),
        "average_precision": round(float(average_precision_score(y, p)), 6),
        "brier": round(brier, 6),
        "brier_of_always_answering_the_training_share": round(reference, 6),
        "brier_skill": round(1.0 - brier / reference, 6) if reference > 0 else None,
        "expected_calibration_error": expected_calibration_error(p, y),
        "reliability": reliability_table(p, y),
        "abstention": abstention(p, y),
        "risk_coverage": risk_coverage(p, y),
    }


@dataclass(frozen=True)
class Selection:
    """The setting kept for one kind of model and how each setting did in the grouped cross-validation."""

    kind: str
    settings: dict[str, Any]
    trials: tuple[dict[str, Any], ...]


def select_settings(kind: str, grid: Sequence[Mapping[str, Any]], features: np.ndarray, label: np.ndarray,
                    folds: np.ndarray, *, seed: int = SEED) -> tuple[Selection, np.ndarray]:
    """Keep the setting with the highest mean average precision over the folds; return it with its out-of-fold values."""

    from sklearn.metrics import average_precision_score

    target = np.asarray(label).astype("int64")
    groups = np.asarray(folds)
    best: tuple[float, dict[str, Any], np.ndarray] | None = None
    trials = []
    for settings in (grid or ({},)):
        predicted = out_of_fold(kind, settings, features, target, groups, seed=seed)
        per_fold = [float(average_precision_score(target[groups == fold], predicted[groups == fold]))
                    for fold in np.unique(groups) if np.unique(target[groups == fold]).size == 2]
        mean = float(np.mean(per_fold))
        trials.append({"settings": dict(settings), "mean_average_precision": round(mean, 6),
                       "by_fold": [round(value, 6) for value in per_fold]})
        if best is None or mean > best[0]:
            best = (mean, dict(settings), predicted)
    assert best is not None
    return Selection(kind, best[1], tuple(trials)), best[2]


def cite_decision(test: Mapping[str, Mapping[str, Any]], *, margin: float = CITE_MARGIN) -> dict[str, Any]:
    """Apply the plan's rule: a tree model is cited only if it beats the baseline by the margin on both figures."""

    base = test[BASELINE]
    rows = {}
    for kind in (RANDOM_FOREST, GRADIENT_BOOSTING):
        gain_auc = test[kind]["roc_auc"] - base["roc_auc"]
        gain_ap = test[kind]["average_precision"] - base["average_precision"]
        rows[kind] = {"roc_auc_gain": round(gain_auc, 6), "average_precision_gain": round(gain_ap, 6),
                      "meets_the_margin": bool(gain_auc >= margin and gain_ap >= margin)}
    passing = [kind for kind, row in rows.items() if row["meets_the_margin"]]
    cited = max(passing, key=lambda kind: test[kind]["average_precision"]) if passing else BASELINE
    return {"margin": margin, "against_the_baseline": rows, "model_to_cite": cited,
            "rule": "A tree model is cited ahead of the baseline only if, on the three test districts together, it is "
                    "at least the margin higher in ROC AUC and in average precision."}
