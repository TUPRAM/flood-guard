"""Learning a water rule from the labels of the label check, one chip left out at a time.

Plan: ``docs/proposal_execution/theos2_water_label_ml_plan_v1.md``. The labelled points of two chips fit a model, the
points of the third are predicted, and each chip is left out once. Report only: a water map of an image is not an
observation of a flood, and nothing here enters a planning score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

SEED = 20261012
WINDOW_PX = 5
"""Side of the neighbourhood of a point: 5 pixels of 2 m."""

FEATURES: tuple[str, ...] = (
    "blue", "green", "red", "nir", "green_nir_index", "red_nir_index", "blue_nir_index", "brightness",
    "nir_mean_5x5", "nir_sd_5x5", "red_nir_index_mean_5x5", "red_nir_index_sd_5x5",
)
MODELS: tuple[str, ...] = ("one_index", "logistic", "forest", "boosting")
WATER, NOT_WATER = "water", "not_water"
COMPARISONS = len(MODELS)
SHARED_LEVEL_Z = 2.4977
"""Standard errors for a two-sided 95% level shared over four comparisons (0.05 / 4)."""


class LabelLearningError(ValueError):
    """The inputs cannot be used for the fit the plan describes."""


def _index(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    total = first + second
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, (first - second) / np.where(total > 0, total, 1.0), 0.0)


def _window_stats(layer: np.ndarray, rows: np.ndarray, columns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    half = WINDOW_PX // 2
    means, deviations = [], []
    for row, column in zip(rows, columns):
        part = layer[max(0, row - half):row + half + 1, max(0, column - half):column + half + 1]
        means.append(float(part.mean()))
        deviations.append(float(part.std()))
    return np.array(means), np.array(deviations)


def features(bands: Mapping[str, np.ndarray], rows: Sequence[int], columns: Sequence[int]) -> np.ndarray:
    """The twelve features of the plan at the given pixels of one chip.

    Args:
        bands: ``blue``, ``green``, ``red`` and ``nir`` of the chip at 2 m, as the water rules read them.
        rows, columns: The pixels, on the grid of the bands.

    Returns:
        One row for each pixel, the columns in the order of :data:`FEATURES`. Each band is divided by its median over
        the chip's pixels with a positive near infrared value, so that chips of different days are on one scale.

    Raises:
        LabelLearningError: for a missing band, bands of different shapes, a pixel outside the chip, or a chip whose
            band has no positive median.
    """

    if set(bands) != {"blue", "green", "red", "nir"}:
        raise LabelLearningError("the four bands blue, green, red and nir are needed")
    shape = bands["nir"].shape
    if any(band.shape != shape for band in bands.values()):
        raise LabelLearningError("the bands are not on one grid")
    rows_, columns_ = np.asarray(rows, dtype=int), np.asarray(columns, dtype=int)
    if rows_.shape != columns_.shape or rows_.ndim != 1:
        raise LabelLearningError("rows and columns must be two lists of the same length")
    if rows_.size and (rows_.min() < 0 or columns_.min() < 0 or rows_.max() >= shape[0] or columns_.max() >= shape[1]):
        raise LabelLearningError("a pixel lies outside the chip")
    seen = bands["nir"] > 0
    scaled = {}
    for name, band in bands.items():
        median = float(np.median(band[seen])) if seen.any() else 0.0
        if median <= 0:
            raise LabelLearningError(f"the {name} band has no positive median over the chip")
        scaled[name] = band.astype("float64") / median
    red_nir = _index(scaled["nir"], scaled["red"])
    nir_mean, nir_sd = _window_stats(scaled["nir"], rows_, columns_)
    index_mean, index_sd = _window_stats(red_nir, rows_, columns_)
    at = lambda layer: layer[rows_, columns_]  # noqa: E731
    columns_out = [
        at(scaled["blue"]), at(scaled["green"]), at(scaled["red"]), at(scaled["nir"]),
        at(_index(scaled["green"], scaled["nir"])), at(red_nir), at(_index(scaled["blue"], scaled["nir"])),
        (at(scaled["blue"]) + at(scaled["green"]) + at(scaled["red"]) + at(scaled["nir"])) / 4,
        nir_mean, nir_sd, index_mean, index_sd,
    ]
    return np.column_stack(columns_out)


def make_model(name: str) -> Any:
    """A model of the plan, with the settings the plan fixes."""

    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if name in ("one_index", "logistic"):
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, random_state=SEED))
    if name == "forest":
        return RandomForestClassifier(n_estimators=500, min_samples_leaf=5, random_state=SEED)
    if name == "boosting":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.1, random_state=SEED)
    raise LabelLearningError(f"no model is called {name}")


def columns_of(name: str) -> list[int]:
    """The feature columns a model reads: one for ``one_index``, all twelve for the others."""

    return [FEATURES.index("red_nir_index")] if name == "one_index" else list(range(len(FEATURES)))


def _fit(model: Any, name: str, x: np.ndarray, y: np.ndarray, weights: np.ndarray | None) -> Any:
    if weights is None:
        return model.fit(x, y)
    if name in ("one_index", "logistic"):
        return model.fit(x, y, logisticregression__sample_weight=weights)
    return model.fit(x, y, sample_weight=weights)


def leave_one_chip_out(points: Sequence[Mapping[str, Any]], matrix: np.ndarray, labels: Mapping[str, str | None],
                       weights: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Predict every point with models fitted on the points of the other chips.

    Args:
        points: The points, each with ``id`` and ``chip``, in the order of the rows of ``matrix``.
        matrix: The features of the points.
        labels: The scoring label of each point: water, not water, or None where there is none.
        weights: The weight of each point in the fit; None for the same weight for every point.

    Returns:
        ``answers``: for each model, its answer (water or not water) at every point, also at points without a label.
        ``folds``: for each chip left out, the labelled points fitted on and their count of water labels.

    Raises:
        LabelLearningError: for fewer than two chips, rows that do not match the points, or a fold whose training
            points hold one label only.
    """

    if matrix.shape != (len(points), len(FEATURES)):
        raise LabelLearningError("one row of twelve features is needed for each point")
    chips = sorted({point["chip"] for point in points})
    if len(chips) < 2:
        raise LabelLearningError("leaving one chip out needs two chips or more")
    ids = [point["id"] for point in points]
    labelled = np.array([labels[i] in (WATER, NOT_WATER) for i in ids])
    target = np.array([1 if labels[i] == WATER else 0 for i in ids])
    chip_of = np.array([point["chip"] for point in points])
    weight = None if weights is None else np.array([float(weights[i]) for i in ids])
    answers: dict[str, dict[str, str]] = {name: {} for name in MODELS}
    folds = {}
    for chip in chips:
        train = labelled & (chip_of != chip)
        test = chip_of == chip
        if len(set(target[train].tolist())) < 2:
            raise LabelLearningError(f"without {chip} the labelled points hold one label only")
        folds[chip] = {"points_fitted_on": int(train.sum()), "of_them_water": int(target[train].sum()), "points_predicted": int(test.sum())}
        for name in MODELS:
            use = columns_of(name)
            model = _fit(make_model(name), name, matrix[train][:, use], target[train], None if weight is None else weight[train])
            predicted = model.predict(matrix[test][:, use])
            for point_id, value in zip(np.array(ids)[test], predicted):
                answers[name][str(point_id)] = WATER if int(value) == 1 else NOT_WATER
    return {"answers": answers, "folds": folds}


def area_weights(points: Sequence[Mapping[str, Any]], sizes: Mapping[tuple[str, str], int]) -> dict[str, float]:
    """For each point, the pixels it stands for: the pixels of its group in its chip over the points drawn there."""

    drawn: dict[tuple[str, str], int] = {}
    for point in points:
        key = (point["chip"], point["group"])
        drawn[key] = drawn.get(key, 0) + 1
    return {point["id"]: sizes[(point["chip"], point["group"])] / drawn[(point["chip"], point["group"])] for point in points}


def shown_better(difference: Mapping[str, Any]) -> bool:
    """The rule of the plan: above zero by more than the standard errors of a level shared over four comparisons."""

    estimate, error = difference.get("estimate"), difference.get("standard_error")
    if estimate is None or error is None:
        return False
    return bool(estimate - SHARED_LEVEL_Z * error > 0)
