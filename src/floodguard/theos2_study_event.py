"""The radar readings of the study event set against a dated THEOS-2 image: the counts and the sentences fixed in the plan.

Plan: ``docs/proposal_execution/theos2_study_event_check_plan_v1.md``. The radar readings of the Sentinel-1 pass of
15 September 2024 are frozen before any THEOS-2 image of the event is received; this module scores them against the
water read from such an image and writes the sentences the plan fixed, whatever the figures turn out to be.

An agreement with an image is agreement with what one optical image shows, read by one rule. It is not a check
on the ground, and nothing here is an official warning or an input of the planning score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

NAME_MARGIN_IOU = 0.02
"""A new reading is named better than the fixed rules only when its IoU is higher than the best of them by this much."""

FIXED_RULES = ("un_spider_last_pass_before", "m1_literal_last_pass_before", "m1_v2_last_pass_before")
NEW_READINGS = ("frozen_detector", "simple_threshold", "un_spider_dry_baseline")
READINGS = (*NEW_READINGS, *FIXED_RULES)
GAP_SENTENCE = ("The image was taken {hours:.1f} hours after the radar pass. Water that left in between counts against the radar, "
                "so the share of flags on water is a lower bound; water that arrived in between counts against it too.")
ROAD_DRY_SENTENCE = ("A road piece that is dry on the image may still have been under water at the peak of the flood, days earlier. "
                     "The image cannot show that a road stayed passable.")
ROAD_WET_SENTENCE = "A road piece under water on the image, days after the peak, was very likely under water at the peak."


class StudyEventError(ValueError):
    """The readings and the reference do not fit together."""


def score(flag: np.ndarray, wet: np.ndarray, compared: np.ndarray, *, cell_km2: float) -> dict[str, Any]:
    """One reading against the reference, on the cells that are compared.

    Returns the four counts, the areas, the share of flags on water, the share of water flagged and the
    intersection over union; a share with an empty denominator is ``None``.
    """

    flagged, water, where = (np.asarray(array, dtype=bool) for array in (flag, wet, compared))
    if not (flagged.shape == water.shape == where.shape):
        raise StudyEventError("the reading, the reference and the compared cells must have one shape")
    if np.any(water & ~where):
        raise StudyEventError("a reference water cell must be a compared cell")
    both = int((flagged & water).sum())
    radar_only = int((flagged & where & ~water).sum())
    image_only = int((water & ~flagged).sum())
    neither = int(where.sum()) - both - radar_only - image_only
    union = both + radar_only + image_only
    return {
        "cells": {"both": both, "radar_only": radar_only, "image_only": image_only, "neither": neither},
        "flagged_km2": round((both + radar_only) * cell_km2, 4), "reference_water_km2": round((both + image_only) * cell_km2, 4),
        "flags_on_reference_water": None if both + radar_only == 0 else round(both / (both + radar_only), 4),
        "reference_water_flagged": None if both + image_only == 0 else round(both / (both + image_only), 4),
        "iou": None if union == 0 else round(both / union, 4),
    }


def score_readings(readings: Mapping[str, np.ndarray], wet: np.ndarray, compared: np.ndarray, *, cell_km2: float,
                   strata: Mapping[str, np.ndarray] | None = None) -> dict[str, Any]:
    """Every reading against the reference, on all compared cells and on each stratum of them."""

    missing = [name for name in READINGS if name not in readings]
    if missing:
        raise StudyEventError(f"the frozen readings {missing} are missing")
    result: dict[str, Any] = {}
    for name in READINGS:
        entry = score(readings[name], wet, compared, cell_km2=cell_km2)
        if strata:
            entry["by_stratum"] = {label: score(readings[name], np.asarray(wet, dtype=bool) & np.asarray(inside, dtype=bool),
                                                np.asarray(compared, dtype=bool) & np.asarray(inside, dtype=bool), cell_km2=cell_km2)
                                   for label, inside in strata.items()}
        result[name] = entry
    return result


def statement(scores: Mapping[str, Mapping[str, Any]], *, hours_after_the_pass: float, margin: float = NAME_MARGIN_IOU) -> dict[str, Any]:
    """The sentences the plan fixed, from the scores of the primary scene.

    A new reading is named better than the fixed rules only when its IoU is higher than the best fixed rule's by
    ``margin`` or more. Without a figure for every fixed rule nothing is named.
    """

    fixed = {name: scores[name].get("iou") for name in FIXED_RULES}
    new = {name: scores[name].get("iou") for name in NEW_READINGS}
    gap = GAP_SENTENCE.format(hours=hours_after_the_pass)
    if any(value is None for value in fixed.values()):
        return {"named_better": [], "best_fixed_rule": None, "sentence": "A fixed rule has no figure on this scene; nothing is named.",
                "time_gap": gap, "margin_iou": margin}
    best = max(fixed, key=lambda name: (fixed[name], name))
    named = [name for name, value in new.items() if value is not None and round(value - fixed[best], 6) >= margin]
    if named:
        sentence = (f"On the dated image of the study event, {', '.join(named)} is better than the best fixed rule ({best}) by at least "
                    f"{margin:.2f} in intersection over union. This is one scene; the fixed rules of record are not replaced by it.")
    else:
        sentence = (f"On the dated image of the study event, no new reading is better than the best fixed rule ({best}) by {margin:.2f} "
                    "in intersection over union. The fixed rules stay.")
    return {"named_better": named, "best_fixed_rule": best, "iou": {**new, **fixed}, "sentence": sentence, "time_gap": gap, "margin_iou": margin}


def road_reading(pieces: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What the image shows of a road: its pieces seen under water, dry, or not observable, with the two fixed cautions.

    Each piece holds ``length_m``, ``observable_m`` and ``water_m`` (centreline metres) and ``seen_under_water``.
    """

    length = sum(float(piece["length_m"]) for piece in pieces)
    observable = sum(float(piece["observable_m"]) for piece in pieces)
    water = sum(float(piece["water_m"]) for piece in pieces)
    if water > observable + 1e-6 or observable > length + 1e-6:
        raise StudyEventError("water metres are among the observable metres, and those among the length")
    under = sum(1 for piece in pieces if piece["seen_under_water"])
    return {
        "pieces": len(pieces), "pieces_seen_under_water": under,
        "length_m": round(length, 1), "observable_m": round(observable, 1), "water_m": round(water, 1),
        "share_of_the_observable_length_on_water": None if observable == 0 else round(water / observable, 4),
        "reading": ("not observable on the image" if observable == 0 else
                    "water on the image" if under else "no piece seen under water on the image"),
        "caution": ROAD_WET_SENTENCE if under else ROAD_DRY_SENTENCE,
    }
