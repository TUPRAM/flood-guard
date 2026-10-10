"""The need mix inside a reporting unit: what the scenario does to its residents, cell by cell, in plain kinds.

A planning class is one letter for a whole tambon. The counts behind it are sums over 100 m demand cells, and those
cells do not all fare alike: some lie in the water, some stay dry and lose every road, some keep a road and lose
the hospital. This module names those kinds, puts every cell in exactly one of them, and sums residents by kind.

**A need type is not a class.** It uses no score, no threshold of class rule v1 and no confidence, it is computed
below the unit the protocol scores, and it changes no class. The kinds are the same counts the exposure, the road
criticality and the access gap are built from, seen before they are summed. Residents are modelled counts and a
closure is a modelled assumption; a need type of a cell says nothing about a household.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

IN_THE_WATER, DRY_CUT_OFF, DRY_LOSES_HOSPITAL, NOT_AFFECTED, NOT_ASSESSED = (
    "in_the_water", "dry_but_cut_off", "dry_and_loses_the_hospital", "not_affected", "not_assessed")
NEED_TYPES: tuple[str, ...] = (IN_THE_WATER, DRY_CUT_OFF, DRY_LOSES_HOSPITAL, NOT_AFFECTED, NOT_ASSESSED)
"""The order is the order of the test: a cell takes the first kind that fits, so every resident is counted once."""

WORDS: dict[str, str] = {
    IN_THE_WATER: "The centre of the cell lies inside the flood layer.",
    DRY_CUT_OFF: "Outside the flood layer; had a road route to a hospital or a main road before, and has none in the flooded run.",
    DRY_LOSES_HOSPITAL: "Outside the flood layer and still with a road route; reached a hospital within 30 minutes before, and does not in the flooded run.",
    NOT_AFFECTED: "Outside the flood layer, and none of the two losses above.",
    NOT_ASSESSED: "Outside the flood layer, and not joined to the road graph or without any road route even before the flood: access cannot be said.",
}
ACTION_WORDS: dict[str, str] = {
    IN_THE_WATER: "people and homes in the water",
    DRY_CUT_OFF: "dry, with every road cut",
    DRY_LOSES_HOSPITAL: "dry and on the road network, with the hospital out of reach",
    NOT_AFFECTED: "not affected in the scenario",
    NOT_ASSESSED: "access not assessed",
}


class NeedMixError(ValueError):
    """The arrays of the cells do not fit together."""


def _booleans(*arrays: Any) -> list[np.ndarray]:
    listed = [np.asarray(array, dtype=bool) for array in arrays]
    if len({array.shape for array in listed}) != 1 or listed[0].ndim != 1:
        raise NeedMixError("every array describes the same cells, one value for each")
    return listed


def label_cells(inside: Any, connected: Any, had_route: Any, has_route: Any, had_hospital: Any, has_hospital: Any) -> np.ndarray:
    """Return the index into :data:`NEED_TYPES` of every cell, for one flooded run.

    Args:
        inside: The cell centre lies inside the flood layer of the run.
        connected: The cell is joined to the road graph.
        had_route, has_route: A road route to a hospital or a main road, before the flood and in the flooded run.
        had_hospital, has_hospital: A hospital within 30 minutes, before the flood and in the flooded run.

    Raises:
        NeedMixError: for a cell that has in the flooded run what it had not before, or has access without being
            joined to the graph.
    """

    wet, joined, route_before, route_after, hospital_before, hospital_after = _booleans(
        inside, connected, had_route, has_route, had_hospital, has_hospital)
    if np.any(route_after & ~route_before) or np.any(hospital_after & ~hospital_before):
        raise NeedMixError("a flooded run gives a cell a route or a hospital it had not before the flood")
    if np.any((route_before | hospital_before) & ~joined) or np.any(hospital_before & ~route_before):
        raise NeedMixError("access needs a cell joined to the graph, and a hospital in reach needs a route")
    labels = np.full(wet.shape, NEED_TYPES.index(NOT_AFFECTED), dtype="int8")
    labels[route_before & ~route_after] = NEED_TYPES.index(DRY_CUT_OFF)
    lost_hospital_only = route_after & hospital_before & ~hospital_after
    labels[lost_hospital_only] = NEED_TYPES.index(DRY_LOSES_HOSPITAL)
    labels[~route_before] = NEED_TYPES.index(NOT_ASSESSED)
    labels[wet] = NEED_TYPES.index(IN_THE_WATER)
    return labels


def mix(labels: Any, residents: Any, where: Any | None = None) -> dict[str, Any]:
    """Residents by need type, and the share of each, over the cells of ``where`` (all cells when omitted)."""

    index = np.asarray(labels)
    people = np.asarray(residents, dtype="float64")
    chosen = np.ones(index.shape, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    if not (index.shape == people.shape == chosen.shape) or index.ndim != 1:
        raise NeedMixError("labels, residents and the selection describe the same cells")
    if np.any(people < 0) or not np.isfinite(people).all() or np.any((index < 0) | (index >= len(NEED_TYPES))):
        raise NeedMixError("residents are 0 or more, and a label is one of the need types")
    sums = np.bincount(index[chosen], weights=people[chosen], minlength=len(NEED_TYPES))
    total = float(sums.sum())
    return {"residents": round(total, 1),
            "by_type": {name: {"residents": round(float(sums[number]), 1),
                               "share": None if total == 0 else round(float(sums[number]) / total, 4)}
                        for number, name in enumerate(NEED_TYPES)}}


def overlaps(inside: Any, connected: Any, had_route: Any, has_route: Any, had_hospital: Any, has_hospital: Any, residents: Any,
             where: Any | None = None) -> dict[str, float]:
    """What the order of the test hides: residents in the water who are also cut off, or who also lose the hospital."""

    wet, _joined, route_before, route_after, hospital_before, hospital_after = _booleans(
        inside, connected, had_route, has_route, had_hospital, has_hospital)
    people = np.asarray(residents, dtype="float64")
    chosen = np.ones(wet.shape, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    cut_off = route_before & ~route_after
    lost_hospital = hospital_before & ~hospital_after
    return {
        "in_the_water_and_cut_off": round(float(people[chosen & wet & cut_off].sum()), 1),
        "in_the_water_and_losing_the_hospital": round(float(people[chosen & wet & lost_hospital].sum()), 1),
        "cut_off_in_the_water_or_dry": round(float(people[chosen & cut_off].sum()), 1),
        "losing_the_hospital_in_the_water_or_dry": round(float(people[chosen & lost_hospital].sum()), 1),
    }


def mix_range(mixes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The lowest and the highest share and count of every need type over a set of runs of the same cells."""

    if not mixes:
        raise NeedMixError("a range needs at least one run")
    result: dict[str, Any] = {}
    for name in NEED_TYPES:
        shares = [entry["by_type"][name]["share"] for entry in mixes if entry["by_type"][name]["share"] is not None]
        counts = [entry["by_type"][name]["residents"] for entry in mixes]
        result[name] = {"share_lowest": min(shares) if shares else None, "share_highest": max(shares) if shares else None,
                        "residents_lowest": min(counts), "residents_highest": max(counts)}
    return result


def squares(x: Any, y: Any, size_m: float) -> tuple[np.ndarray, np.ndarray]:
    """The column and row of the square of ``size_m`` metres that holds each point, counted from the origin of the projection."""

    if size_m <= 0:
        raise NeedMixError("a square needs a side above 0")
    return (np.floor(np.asarray(x, dtype="float64") / size_m).astype("int64"),
            np.floor(np.asarray(y, dtype="float64") / size_m).astype("int64"))


def by_square(labels: Any, residents: Any, columns: Any, rows: Any) -> list[dict[str, Any]]:
    """Residents by need type in every square that holds a cell, with the type most residents fall in.

    A tie goes to the type earlier in :data:`NEED_TYPES`. A square with no resident has no leading type.
    """

    index = np.asarray(labels)
    people = np.asarray(residents, dtype="float64")
    column, row = np.asarray(columns), np.asarray(rows)
    if not (index.shape == people.shape == column.shape == row.shape):
        raise NeedMixError("labels, residents and the squares describe the same cells")
    keys, inverse = np.unique(np.stack([column, row], axis=1), axis=0, return_inverse=True)
    inverse = inverse.ravel()
    table = np.zeros((len(keys), len(NEED_TYPES)))
    np.add.at(table, (inverse, index), people)
    listed = []
    for number, (square_column, square_row) in enumerate(keys.tolist()):
        sums = table[number]
        total = float(sums.sum())
        listed.append({"column": int(square_column), "row": int(square_row), "residents": round(total, 1),
                       "leading_type": None if total == 0 else NEED_TYPES[int(np.argmax(sums))],
                       "by_type": {name: round(float(sums[position]), 1) for position, name in enumerate(NEED_TYPES)}})
    return listed
