"""Buildings in the water against residents in the water.

The plan is ``docs/proposal_execution/buildings_in_water_plan_v1.md``. This
module holds the pure functions: which buildings are used, the ring of ground
around a building on a 2 m raster, whether a building stands in water, and
the three readings of "residents in the water" of a population cell. It reads
no file; ``scripts/build_buildings_in_water.py`` does.

Building outlines are drawn by a model on satellite images and say nothing of
who lives in a building. Every figure sets one model against another; none is
a count of people, an observation of a flooded house or a warning.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

MIN_AREA_M2: float = 10.0
MIN_CONFIDENCE: float = 0.70
RING_INNER_PX: int = 1    # pixels on or beside an outline are not ground: 2 m at the 2 m of the water raster
RING_OUTER_PX: int = 4    # 8 m
MIN_RING_PX: int = 6
MIN_ANSWERED_SHARE: float = 0.5
IN_WATER_SHARE: float = 0.5
OTHER_SHARES: tuple[float, ...] = (0.25, 0.75)
EDGE_MARGIN_M: float = 20.0
CELL_REACH_M: float = 75.0
DIFFERENCE_POINTS: float = 5.0

WATER_NO: int = 0
WATER_YES: int = 1
WATER_UNOBSERVABLE: int = 255


class BuildingsError(ValueError):
    """The arrays cannot support the count."""


def used(area_m2: Sequence[float], confidence: Sequence[float | None]) -> np.ndarray:
    """Which outlines are used: large enough, and confident enough where the source gives a confidence.

    A confidence that is missing, not a number or negative means the source
    gives none (Microsoft); such an outline is kept on its area alone.
    """

    area = np.asarray(area_m2, dtype="float64")
    given = np.array([np.nan if value is None else float(value) for value in confidence], dtype="float64")
    if area.shape != given.shape:
        raise BuildingsError("one area and one confidence are needed for each outline")
    without = ~np.isfinite(given) | (given < 0)
    return (area >= MIN_AREA_M2) & (without | (given >= MIN_CONFIDENCE))


def rings(labels: np.ndarray, *, inner_px: int = RING_INNER_PX, outer_px: int = RING_OUTER_PX) -> np.ndarray:
    """The ring of each building on the raster of building labels.

    ``labels`` holds 0 where there is no building and the number of the
    building elsewhere. Returns a raster of the same shape with the number of
    the building whose ring a pixel belongs to, and 0 elsewhere: a pixel is in
    the ring of its nearest building when it is more than ``inner_px`` and at
    most ``outer_px`` pixels from it.
    """

    from scipy import ndimage

    raster = np.asarray(labels)
    if raster.ndim != 2:
        raise BuildingsError("the label raster must be two-dimensional")
    if not 0 <= inner_px < outer_px:
        raise BuildingsError("the ring needs an inner distance below its outer distance")
    if not (raster > 0).any():
        return np.zeros(raster.shape, dtype=raster.dtype)
    distance, (rows, columns) = ndimage.distance_transform_edt(raster == 0, return_indices=True)
    nearest = raster[rows, columns]
    return np.where((distance > inner_px) & (distance <= outer_px), nearest, 0).astype(raster.dtype)


def ring_counts(ring: np.ndarray, water: np.ndarray, buildings: int) -> dict[str, np.ndarray]:
    """For each building 1..``buildings``: the pixels of its ring, those with an answer, and those that are water."""

    ring_raster, water_raster = np.asarray(ring), np.asarray(water)
    if ring_raster.shape != water_raster.shape:
        raise BuildingsError("the ring raster and the water raster must share one shape")
    flat = ring_raster.ravel()
    answered = (water_raster != WATER_UNOBSERVABLE).ravel()
    wet = (water_raster == WATER_YES).ravel()
    size = buildings + 1
    return {
        "ring_px": np.bincount(flat, minlength=size)[1:size],
        "answered_px": np.bincount(flat, weights=answered, minlength=size)[1:size].astype("int64"),
        "water_px": np.bincount(flat, weights=wet, minlength=size)[1:size].astype("int64"),
    }


def assessed(counts: Mapping[str, np.ndarray]) -> np.ndarray:
    """A building is assessed when its ring is large enough and at least half of it has an answer."""

    ring = np.asarray(counts["ring_px"], dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(ring > 0, np.asarray(counts["answered_px"]) / ring, 0.0)
    return (ring >= MIN_RING_PX) & (share >= MIN_ANSWERED_SHARE)


def in_water(counts: Mapping[str, np.ndarray], share: float = IN_WATER_SHARE) -> np.ndarray:
    """An assessed building stands in water when at least ``share`` of the answered pixels of its ring are water."""

    answered = np.asarray(counts["answered_px"], dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        wet = np.where(answered > 0, np.asarray(counts["water_px"]) / answered, 0.0)
    return assessed(counts) & (wet >= share)


def residents_in_water(residents: np.ndarray, centre_in_water: np.ndarray, water_share_of_area: np.ndarray | None,
                       buildings_assessed: np.ndarray, buildings_in_water: np.ndarray) -> dict[str, Any]:
    """The readings of residents in the water, on the cells that can be compared.

    A cell is compared when it has residents, its centre has an answer
    (``centre_in_water`` is not NaN), and it holds at least one assessed
    building. ``water_share_of_area`` may be ``None`` where the water is a
    layer of polygons and not a raster.
    """

    people = np.asarray(residents, dtype="float64")
    centre = np.asarray(centre_in_water, dtype="float64")
    held = np.asarray(buildings_assessed, dtype="float64")
    wet = np.asarray(buildings_in_water, dtype="float64")
    if not (people.shape == centre.shape == held.shape == wet.shape):
        raise BuildingsError("every reading needs one value for each cell")
    if (wet > held).any():
        raise BuildingsError("a cell holds more buildings in the water than buildings")
    with_residents = people > 0
    compared = with_residents & np.isfinite(centre) & (held > 0)
    total = float(people[compared].sum())

    def reading(share: np.ndarray) -> dict[str, Any]:
        count = float((people[compared] * share[compared]).sum())
        return {"residents": round(count), "share": None if total == 0 else round(count / total, 4)}

    with np.errstate(divide="ignore", invalid="ignore"):
        by_buildings = np.where(held > 0, wet / held, 0.0)
    result = {
        "cells_with_residents": int(with_residents.sum()),
        "residents": round(float(people[with_residents].sum())),
        "cells_compared": int(compared.sum()),
        "residents_compared": round(total),
        "residents_in_cells_without_an_assessed_building": round(float(people[with_residents & (held == 0)].sum())),
        "centre_rule": reading(np.nan_to_num(centre)),
        "buildings": reading(by_buildings),
    }
    if water_share_of_area is not None:
        area = np.asarray(water_share_of_area, dtype="float64")
        if area.shape != people.shape:
            raise BuildingsError("every reading needs one value for each cell")
        result["area"] = reading(np.nan_to_num(area))
    first, second = result["centre_rule"]["share"], result["buildings"]["share"]
    result["buildings_minus_centre_rule_points"] = None if first is None else round((second - first) * 100, 1)
    return result


def verdict(points: float | None) -> str:
    """The sentence of the plan on the centre rule, from the difference in percentage points."""

    if points is None:
        return "no cell could be compared"
    if abs(points) <= DIFFERENCE_POINTS:
        return f"the buildings reading is within {DIFFERENCE_POINTS:g} points of the centre rule"
    return f"the buildings reading is {'higher' if points > 0 else 'lower'} than the centre rule by {abs(points):g} points"
