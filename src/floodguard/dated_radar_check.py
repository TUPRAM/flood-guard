"""Radar flood candidates against a dated agency flood layer: the pure counting.

The comparison of work package 3 sets the three radar methods against the
single-date layer that UNOSAT and GISTDA dated 22 October 2024. The agreement
counts are those of :mod:`floodguard.theos2_cross_check`; this module adds what
a vector reference needs: which cells sit at the edge of the layer, the cells
that are compared, and the sentences the plan fixed before the result was seen.

Every figure made here is agreement with an agency layer that was not checked
in the field. None is accuracy, and nothing here computes a planning score.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from floodguard import theos2_cross_check as cc

LOW_SHARE_OF_REFERENCE_FLAGGED = 0.10
"""Plan section 5: below this share in both readings, a method "does not see" the water of that date."""

READINGS_DIFFER_FACTOR = 2.0
"""Plan section 5: above this factor between the readings, the image before decides the result."""


class DatedRadarCheckError(ValueError):
    """The inputs of the comparison do not fit together."""


def interior_cells(reference: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Cells of ``region`` whose eight neighbours carry the same reference value.

    A cell at the rim of the raster, or beside a cell outside ``region``, is
    not interior: its neighbourhood is not fully known.
    """

    wet = np.asarray(reference, dtype=bool)
    inside = np.asarray(region, dtype=bool)
    if wet.shape != inside.shape or wet.ndim != 2:
        raise DatedRadarCheckError("the reference and the region must be two rasters of one shape")
    rows, columns = wet.shape
    same = np.zeros(wet.shape, dtype=bool)
    if rows < 3 or columns < 3:
        return same
    centre = wet[1:-1, 1:-1]
    uniform = np.ones(centre.shape, dtype=bool)
    known = inside[1:-1, 1:-1].copy()
    for row_shift in (-1, 0, 1):
        for column_shift in (-1, 0, 1):
            if row_shift == 0 and column_shift == 0:
                continue
            window = (slice(1 + row_shift, rows - 1 + row_shift), slice(1 + column_shift, columns - 1 + column_shift))
            uniform &= wet[window] == centre
            known &= inside[window]
    same[1:-1, 1:-1] = uniform & known
    return same


def frame_counts(in_district: np.ndarray, permanent_water: np.ndarray, reference: np.ndarray, season: np.ndarray,
                 *, cell_area_km2: float) -> dict[str, Any]:
    """Counts of the frame before any radar is read: what is compared and what the reference holds."""

    district = np.asarray(in_district, dtype=bool)
    water = np.asarray(permanent_water, dtype=bool)
    wet = np.asarray(reference, dtype=bool)
    envelope = np.asarray(season, dtype=bool)
    if not (district.shape == water.shape == wet.shape == envelope.shape):
        raise DatedRadarCheckError("the four rasters must have one shape")
    if cell_area_km2 <= 0:
        raise DatedRadarCheckError("cell_area_km2 must be positive")
    frame = district & ~water
    reference_in_district = int((wet & district).sum())

    def km2(cells: int) -> float:
        return round(cells * cell_area_km2, 4)

    return {
        "district_cells": int(district.sum()),
        "district_km2": km2(int(district.sum())),
        "permanent_water_cells_left_out": int((district & water).sum()),
        "frame_cells": int(frame.sum()),
        "reference_cells_in_the_district": reference_in_district,
        "reference_km2_in_the_district": km2(reference_in_district),
        "reference_cells_on_permanent_water_left_out": int((wet & district & water).sum()),
        "reference_cells_in_the_frame": int((wet & frame).sum()),
        "reference_km2_in_the_frame": km2(int((wet & frame).sum())),
        "reference_share_of_the_frame": round(int((wet & frame).sum()) / int(frame.sum()), 6) if frame.any() else None,
        "reference_cells_inside_the_season_layer": int((wet & district & envelope).sum()),
        "reference_share_inside_the_season_layer": (
            round(int((wet & district & envelope).sum()) / reference_in_district, 6) if reference_in_district else None),
    }


def rename_reference_keys(value: Any) -> Any:
    """The agreement counts were written for an optical reference; here the reference is an agency layer."""

    if isinstance(value, dict):
        return {("reference_wet_km2" if key == "optical_wet_km2" else key): rename_reference_keys(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [rename_reference_keys(item) for item in value]
    return value


def method_agreement(candidate: np.ndarray, reference: np.ndarray, compared: np.ndarray, interior: np.ndarray,
                     land_cover: np.ndarray, groups: Mapping[str, tuple[int, ...]], *, cell_area_km2: float) -> dict[str, Any]:
    """The agreement of one candidate with the dated layer: all compared cells, without edge cells, by land cover."""

    region = np.asarray(compared, dtype=bool)
    wet = np.asarray(reference, dtype=bool) & region
    inner = region & np.asarray(interior, dtype=bool)
    return rename_reference_keys({
        "all_compared_cells": cc.agreement(candidate, wet, region, cell_area_km2=cell_area_km2),
        "without_cells_at_the_edge_of_the_layer": cc.agreement(candidate, wet & inner, inner, cell_area_km2=cell_area_km2),
        "by_land_cover_worldcover_2021": cc.agreement_by_class(candidate, wet, region, land_cover, groups,
                                                               cell_area_km2=cell_area_km2),
    })


def share_flagged(agreement: Mapping[str, Any]) -> float | None:
    """Of the reference water, the share a method flags; a cell without an answer counts as not flagged."""

    value = agreement["all_compared_cells"]["strict_no_answer_counts_as_not_a_candidate"].get("recall")
    return None if value is None else float(value)


def fixed_sentences(readings: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Apply the two reading rules of plan section 5.

    ``readings`` maps a reading (``primary``, ``second``) to the agreement of
    each method. The rules are applied as written; nothing is chosen here.
    """

    if set(readings) != {"primary", "second"}:
        raise DatedRadarCheckError("the plan names two readings: primary and second")
    methods = sorted(readings["primary"])
    if sorted(readings["second"]) != methods:
        raise DatedRadarCheckError("both readings must hold the same methods")
    result: dict[str, Any] = {}
    for method in methods:
        first = share_flagged(readings["primary"][method])
        second = share_flagged(readings["second"][method])
        known = first is not None and second is not None
        low, high = (min(first, second), max(first, second)) if known else (None, None)
        result[method] = {
            "share_of_reference_water_flagged": {"primary": first, "second": second},
            "does_not_see_the_water_of_that_date": bool(known and high < LOW_SHARE_OF_REFERENCE_FLAGGED),
            "the_image_before_decides_the_result": bool(known and high > 0 and (low == 0 or high / low > READINGS_DIFFER_FACTOR)),
        }
    return {
        "rules": {
            "does_not_see_the_water_of_that_date": f"below {LOW_SHARE_OF_REFERENCE_FLAGGED} in both readings",
            "the_image_before_decides_the_result": f"the readings differ by more than a factor of {READINGS_DIFFER_FACTOR}",
        },
        "by_method": result,
    }
