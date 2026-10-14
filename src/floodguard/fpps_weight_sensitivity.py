"""How far the order of the units of a scored case depends on the five weights of the planning score.

The planning score (FPPS) adds five components, each on 0-100, with the weights of ``floodguard.scoring``. The weights
are the project's choice. This module answers one question about a published case: would the order of its units be
another one with other weights? It reads the component values of the published case and adds them up again with

* named weightings (five equal weights; three equal groups; flood and exposure only; the published weights with the two
  access components left out),
* each published weight halved and raised by half, one at a time, the others scaled so that the weights sum to one,
* many random weightings, drawn evenly from all sets of five weights that sum to one.

It is report only: it changes no score, no weight and no class, and it is not part of the planning protocol. A class
follows rules on the components as well as the score, so nothing here says how a class would change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from floodguard.scoring import DEFAULT_WEIGHTS

COMPONENTS: tuple[str, ...] = tuple(DEFAULT_WEIGHTS)
"""The five components, in the order of the scoring module."""

SCHEMA = "floodguard.fpps_weight_sensitivity.v1"
LABEL = "Report only. It changes no score, weight or class."
FACTORS: tuple[float, ...] = (0.5, 1.5)
DRAWS = 200_000
SEED = 20261012
ACCESS_COMPONENTS: tuple[str, ...] = ("access_gap_0_100", "road_criticality_0_100")


class WeightSensitivityError(ValueError):
    """The inputs cannot be read as one case with five components for each unit."""


def _vector(weights: Mapping[str, float]) -> np.ndarray:
    if set(weights) != set(COMPONENTS):
        raise WeightSensitivityError(f"weights must name exactly {list(COMPONENTS)}")
    vector = np.array([float(weights[name]) for name in COMPONENTS])
    if (vector < 0).any() or not np.isclose(vector.sum(), 1.0, atol=1e-9):
        raise WeightSensitivityError("weights must be zero or more and sum to one")
    return vector


def _matrix(values: Mapping[str, Mapping[str, float]]) -> tuple[list[str], np.ndarray]:
    units = list(values)
    if len(units) < 2:
        raise WeightSensitivityError("an order needs two units or more")
    rows = []
    for unit in units:
        if set(values[unit]) != set(COMPONENTS):
            raise WeightSensitivityError(f"unit {unit}: components must be exactly {list(COMPONENTS)}")
        row = [float(values[unit][name]) for name in COMPONENTS]
        if any(not 0.0 <= value <= 100.0 for value in row):
            raise WeightSensitivityError(f"unit {unit}: a component is outside 0-100")
        rows.append(row)
    return units, np.array(rows)


def order_of(scores: Sequence[float], units: Sequence[str]) -> list[str]:
    """The units from the highest score down. Equal scores keep the order the units were given in."""

    return [units[index] for index in np.argsort(-np.asarray(scores, dtype=float), kind="stable")]


def named_weightings() -> dict[str, dict[str, float]]:
    """The weightings set beside the published one, each summing to one."""

    published = dict(DEFAULT_WEIGHTS)
    kept = {name: (0.0 if name in ACCESS_COMPONENTS else weight) for name, weight in published.items()}
    total = sum(kept.values())
    return {
        "equal": {name: 1 / len(COMPONENTS) for name in COMPONENTS},
        # Flood and exposure, access and routes, and age: one third each, halved inside the first two groups.
        "three_groups": {"flood_likelihood_0_100": 1 / 6, "exposure_0_100": 1 / 6, "access_gap_0_100": 1 / 6,
                         "road_criticality_0_100": 1 / 6, "vulnerability_context_0_100": 1 / 3},
        "flood_and_exposure_only": {"flood_likelihood_0_100": 0.5, "exposure_0_100": 0.5, "access_gap_0_100": 0.0,
                                    "road_criticality_0_100": 0.0, "vulnerability_context_0_100": 0.0},
        "without_access": {name: weight / total for name, weight in kept.items()},
    }


def one_at_a_time(factor: float) -> dict[str, dict[str, float]]:
    """The published weights with one weight multiplied by ``factor`` and all five scaled to sum to one."""

    if factor <= 0:
        raise WeightSensitivityError("the factor must be above zero")
    result = {}
    for name in COMPONENTS:
        changed = dict(DEFAULT_WEIGHTS)
        changed[name] *= factor
        total = sum(changed.values())
        result[name] = {key: value / total for key, value in changed.items()}
    return result


def _rank_correlation(ranks: np.ndarray, reference: np.ndarray) -> np.ndarray:
    count = reference.size
    return 1 - 6 * ((ranks - reference) ** 2).sum(axis=1) / (count * (count**2 - 1))


def assess(values: Mapping[str, Mapping[str, float]], *, draws: int = DRAWS, seed: int = SEED) -> dict[str, Any]:
    """The order of the units under the published weights and under the other weightings.

    Args:
        values: For each unit, its five component values on 0-100, keyed by component name.
        draws: Number of random weightings.
        seed: Seed of the random weightings; the result is the same for the same seed.

    Returns:
        A report with the published order and scores, each named weighting, each one-at-a-time change, and for the
        random weightings the share in which each unit is first, in which the first three and the first four are the
        same units, in which the whole order is the same, and the rank correlation with the published order.

    Raises:
        WeightSensitivityError: for a unit without exactly the five components, a value outside 0-100, fewer than two
            units, or fewer than one draw.
    """

    if draws < 1:
        raise WeightSensitivityError("draws must be one or more")
    units, matrix = _matrix(values)

    def weighting(weights: Mapping[str, float]) -> dict[str, Any]:
        scores = matrix @ _vector(weights)
        order = order_of(scores, units)
        return {"weights": {name: round(float(weights[name]), 6) for name in COMPONENTS}, "order": order,
                "scores": {unit: round(float(score), 2) for unit, score in zip(units, scores)}, "first": order[0]}

    published = weighting(DEFAULT_WEIGHTS)
    reference = published["order"]

    def beside(entry: dict[str, Any]) -> dict[str, Any]:
        return {**entry, "same_order": entry["order"] == reference}

    named = [{"id": name, **beside(weighting(weights))} for name, weights in named_weightings().items()]
    single = [{"component": name, "factor": factor, **beside(weighting(weights))}
              for factor in FACTORS for name, weights in one_at_a_time(factor).items()]

    generator = np.random.default_rng(seed)
    random_weights = generator.dirichlet(np.ones(len(COMPONENTS)), size=draws)
    scores = random_weights @ matrix.T
    # Rank 0 is the highest score. Ties (which need two units with the same five values) keep the given order.
    ranks = np.argsort(np.argsort(-scores, axis=1, kind="stable"), axis=1, kind="stable")
    reference_rank = np.array([reference.index(unit) for unit in units])
    first = ranks.argmin(axis=1)
    correlation = _rank_correlation(ranks, reference_rank)

    def same_leaders(count: int) -> float:
        leaders = reference_rank < count
        return float(((ranks < count) == leaders).all(axis=1).mean())

    return {
        "schema": SCHEMA,
        "label": LABEL,
        "components": list(COMPONENTS),
        "published": published,
        "named": named,
        "one_at_a_time": single,
        "random": {
            "draws": draws,
            "seed": seed,
            "distribution": "even over all sets of five weights, each zero or more, that sum to one",
            "share_first": {unit: round(float((first == index).mean()), 4) for index, unit in enumerate(units) if (first == index).any()},
            "share_same_first_three": round(same_leaders(3), 4),
            "share_same_first_four": round(same_leaders(4), 4),
            "share_same_order": round(float((ranks == reference_rank).all(axis=1).mean()), 4),
            "rank_correlation": {"median": round(float(np.median(correlation)), 3), "p05": round(float(np.quantile(correlation, 0.05)), 3),
                                 "lowest": round(float(correlation.min()), 3)},
        },
        "limits": [
            "The components are those of the published case. A component that is wrong stays wrong under every weighting.",
            "A class follows rules on the components as well as the score, so this report says nothing about classes.",
            "Random weightings are drawn evenly over all weight sets. Nobody proposes most of them; the share is a measure of how much room there is, not a probability.",
        ],
    }
