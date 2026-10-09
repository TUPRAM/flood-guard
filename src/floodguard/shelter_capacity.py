"""Listed shelter places against the residents who can walk to them (protocol v1b, ``facility_sets.two_step_access``).

The method the protocol names: binary two-step floating catchment (2SFCA) at 15, 30 and 60 minutes on the located
DDPM rows, with participation of 5, 10 and 25 percent, labelled "listed planned capacity; scenario". This module
computes it on a matrix of travel minutes, which is what a district of some tens of thousands of demand cells
needs; :func:`floodguard.two_step_access.calculate_binary_2sfca` is the reference it is tested against.

A ratio is listed places per resident who would seek a place. It allocates nobody to a shelter. The capacities
are listed planning figures whose operating status nobody verified, the participation shares are assumptions, and
nothing here is an input of the planning score, a class or an official warning.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

THRESHOLDS_MINUTES = (15, 30, 60)
PRIMARY_THRESHOLD_MINUTES = 30
PARTICIPATION_PERCENT = (5, 10, 25)
LABEL = "listed planned capacity; scenario"


class ShelterCapacityError(ValueError):
    """The travel matrix, the demand and the supply do not fit together."""


def _checked(minutes: np.ndarray, demand: np.ndarray, supply: np.ndarray | None) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    matrix = np.asarray(minutes, dtype="float64")
    people = np.asarray(demand, dtype="float64")
    if matrix.ndim != 2 or people.shape != (matrix.shape[0],):
        raise ShelterCapacityError("minutes is origins by sites, and demand has one value for every origin")
    if np.isnan(matrix).any() or (matrix < 0).any():
        raise ShelterCapacityError("a travel time is 0 or more, or infinite where there is no route")
    if not np.isfinite(people).all() or (people < 0).any():
        raise ShelterCapacityError("demand must be finite and 0 or more")
    places = None
    if supply is not None:
        places = np.asarray(supply, dtype="float64")
        if places.shape != (matrix.shape[1],) or not np.isfinite(places).all() or (places < 0).any():
            raise ShelterCapacityError("supply has one finite value, 0 or more, for every site")
    return matrix, people, places


def two_step(minutes: np.ndarray, demand: np.ndarray, supply: np.ndarray, threshold_minutes: float) -> dict[str, np.ndarray]:
    """Binary 2SFCA at one threshold.

    Args:
        minutes: Travel minutes from every origin (row) to every site (column); ``inf`` where there is no route.
        demand: The demand of every origin, in people.
        supply: The supply of every site, in places.
        threshold_minutes: A site is in reach of an origin at this many minutes or fewer.

    Returns:
        ``site_catchment_demand`` (the demand in reach of each site), ``site_ratio`` (supply over that demand;
        ``nan`` where no demand is in reach), ``origin_reaches_a_site`` and ``origin_accessibility`` (the sum
        of the ratios of the sites in reach of an origin: 0 where none is, ``nan`` where one of them has no
        ratio).
    """

    matrix, people, places = _checked(minutes, demand, supply)
    assert places is not None
    reach = matrix <= float(threshold_minutes)
    catchment = (reach * people[:, None]).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(catchment > 0, places / catchment, np.nan)
    accessibility = np.where(reach, ratio[None, :], 0.0).sum(axis=1)
    return {"site_catchment_demand": catchment, "site_ratio": ratio, "origin_reaches_a_site": reach.any(axis=1),
            "origin_accessibility": accessibility}


def nearest_site(minutes: np.ndarray, threshold_minutes: float) -> np.ndarray:
    """The column of the nearest site within the threshold for every origin, or -1; a tie goes to the lower column."""

    matrix = np.asarray(minutes, dtype="float64")
    if matrix.ndim != 2:
        raise ShelterCapacityError("minutes is origins by sites")
    if matrix.shape[1] == 0:
        return np.full(matrix.shape[0], -1, dtype="int64")
    nearest = matrix.argmin(axis=1)
    within = matrix[np.arange(matrix.shape[0]), nearest] <= float(threshold_minutes)
    return np.where(within, nearest, -1)


def assigned_demand(nearest: np.ndarray, demand: np.ndarray, sites: int) -> np.ndarray:
    """The demand whose nearest site each site is. Residents are counted at one site only; nobody is allocated."""

    index = np.asarray(nearest, dtype="int64")
    people = np.asarray(demand, dtype="float64")
    if index.shape != people.shape or (index >= sites).any():
        raise ShelterCapacityError("nearest and demand describe the same origins, and a column must exist")
    kept = index >= 0
    return np.bincount(index[kept], weights=people[kept], minlength=sites).astype("float64")


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    """The median of ``values`` when each counts ``weights`` times; ``None`` without any weight."""

    numbers = np.asarray(values, dtype="float64")
    weight = np.asarray(weights, dtype="float64")
    kept = np.isfinite(numbers) & (weight > 0)
    if not kept.any():
        return None
    order = np.argsort(numbers[kept], kind="stable")
    ordered, cumulative = numbers[kept][order], np.cumsum(weight[kept][order])
    return float(ordered[int(np.searchsorted(cumulative, cumulative[-1] / 2.0))])


def reading(accessibility_all_residents: np.ndarray, reaches: np.ndarray, residents: np.ndarray,
            participation_percent: Sequence[float] = PARTICIPATION_PERCENT, where: np.ndarray | None = None) -> dict[str, Any]:
    """What one group of origins is told by a 2SFCA run: who is in reach of a shelter, and who of them is short of places.

    ``accessibility_all_residents`` is the ratio computed with every resident as demand. With a participation of
    ``p`` percent every demand is multiplied by ``p / 100``, so every ratio is divided by it: no second run is needed.
    A resident is short of places when the listed places in reach, shared among everyone in reach who would seek
    one, come to fewer than one place per person.
    """

    access = np.asarray(accessibility_all_residents, dtype="float64")
    reach = np.asarray(reaches, dtype=bool)
    people = np.asarray(residents, dtype="float64")
    inside = np.ones(people.shape, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    if not (access.shape == reach.shape == people.shape == inside.shape):
        raise ShelterCapacityError("accessibility, reach, residents and the selection describe the same origins")
    counted = inside & reach & (people > 0)
    in_reach = float(people[counted].sum())
    result: dict[str, Any] = {"residents": round(float(people[inside].sum()), 1), "residents_in_reach_of_a_shelter": round(in_reach, 1),
                              "participation": {}}
    for percent in participation_percent:
        if not 0 < percent <= 100:
            raise ShelterCapacityError("participation is a percentage above 0 and at most 100")
        scaled = access / (percent / 100.0)
        short = counted & (scaled < 1.0)
        result["participation"][str(percent)] = {
            "people_seeking_a_place": round(in_reach * percent / 100.0, 1),
            "residents_in_reach_with_under_one_listed_place_per_person_seeking": round(float(people[short].sum()), 1),
            "share_of_the_residents_in_reach": None if in_reach == 0 else round(float(people[short].sum()) / in_reach, 4),
            "median_listed_places_per_person_seeking": (
                None if in_reach == 0 else round(weighted_median(scaled[counted], people[counted]) or 0.0, 3)),
        }
    return result
