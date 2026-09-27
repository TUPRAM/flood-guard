"""Day-by-day flood reconstruction helpers for the Mae Sai September 2024 case.

The reconstruction is a HAND (height above nearest drainage) threshold model:
a cell is wet when the assumed river stage exceeds its HAND value, and the
water depth is ``stage - HAND``. Stage values are illustrative keyframes derived
from the event narrative; they are not gauge observations. Nothing here is a
real-time detector or an official warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

import numpy as np

HAND_STEP_M = 0.05
"""Vertical resolution of the encoded HAND raster (metres per code step)."""

CHANNEL_CODE = 0
"""Code for mapped drainage-channel cells (always water)."""

NEVER_CODE = 255
"""Code for cells above the encoded range or outside the valid DEM."""

MAX_ENCODED_HAND_M = (NEVER_CODE - 1) * HAND_STEP_M

IMPASSABLE_DEPTH_M = 0.3
"""Depth at which a road segment is treated as impassable for ordinary vehicles."""

Phase = Literal["dry", "onset", "peak", "receding", "gone"]
RoadState = Literal["dry", "wet", "impassable"]


@dataclass(frozen=True)
class StageKeyframe:
    """Assumed river stage (metres above the channel reference) at local noon."""

    day: date
    phase: Phase
    stage_m: float


KEYFRAMES: tuple[StageKeyframe, ...] = (
    StageKeyframe(date(2024, 9, 9), "dry", 0.0),
    StageKeyframe(date(2024, 9, 10), "onset", 0.1),
    StageKeyframe(date(2024, 9, 11), "peak", 3.2),
    StageKeyframe(date(2024, 9, 12), "peak", 3.5),
    StageKeyframe(date(2024, 9, 13), "receding", 1.8),
    StageKeyframe(date(2024, 9, 14), "receding", 0.9),
    StageKeyframe(date(2024, 9, 15), "receding", 0.25),
    StageKeyframe(date(2024, 9, 16), "gone", 0.08),
    StageKeyframe(date(2024, 9, 17), "gone", 0.04),
    StageKeyframe(date(2024, 9, 18), "gone", 0.02),
    StageKeyframe(date(2024, 9, 19), "gone", 0.0),
)
"""Days are local (ICT, UTC+7). Magnitudes are illustrative; see ``timeline.json`` assumptions."""

EXTRA_ANCHORS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),  # 10 Sep 00:00: the river stays in bank for the whole dry day.
    (1.0 + 22 / 24, 1.5),  # 10 Sep 22:00: overflow into town during the night.
)
"""Sub-daily anchors (days since 9 Sep 00:00 ICT, stage m) added to the local-noon keyframes."""


def stage_anchors(keyframes: Sequence[StageKeyframe] = KEYFRAMES,
                  extra: Sequence[tuple[float, float]] = EXTRA_ANCHORS) -> list[tuple[float, float]]:
    """Return sorted interpolation knots: keyframe ``i`` at ``i + 0.5`` (local noon) plus ``extra``."""
    if not keyframes:
        raise ValueError("at least one keyframe is required")
    knots = {round(i + 0.5, 6): k.stage_m for i, k in enumerate(keyframes)}
    for t, stage in extra:
        knots[round(t, 6)] = stage
    return sorted(knots.items())


def stage_at(t_days: float, keyframes: Sequence[StageKeyframe] = KEYFRAMES,
             extra: Sequence[tuple[float, float]] = EXTRA_ANCHORS) -> float:
    """Return the stage at ``t_days`` after 9 Sep 00:00 ICT by linear interpolation between anchors.

    Values are held constant before the first and after the last anchor.
    """
    knots = stage_anchors(keyframes, extra)
    return float(np.interp(t_days, [t for t, _ in knots], [v for _, v in knots]))


def encode_hand(hand_m: np.ndarray, channel: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Encode HAND metres into uint8 codes (0 channel, 1-254 HAND, 255 never/invalid)."""
    codes = np.clip(np.rint(np.asarray(hand_m, dtype=float) / HAND_STEP_M), 1, NEVER_CODE - 1)
    codes = codes.astype(np.uint8)
    codes[np.asarray(hand_m) > MAX_ENCODED_HAND_M] = NEVER_CODE
    codes[~np.asarray(valid, dtype=bool)] = NEVER_CODE
    codes[np.asarray(channel, dtype=bool) & np.asarray(valid, dtype=bool)] = CHANNEL_CODE
    return codes


def decode_hand(codes: np.ndarray) -> np.ndarray:
    """Decode uint8 codes into HAND metres; ``NEVER_CODE`` becomes ``inf``."""
    codes = np.asarray(codes)
    hand = codes.astype(float) * HAND_STEP_M
    hand[codes == NEVER_CODE] = np.inf
    return hand


def depth_at_stage(codes: np.ndarray, stage_m: float) -> np.ndarray:
    """Return water depth (m) for each coded cell at ``stage_m``; channel cells get the stage."""
    depth = np.clip(stage_m - decode_hand(codes), 0.0, None)
    depth[np.asarray(codes) == CHANNEL_CODE] = max(stage_m, 0.0)
    return depth


def flooded_area_km2(histogram: Sequence[int], stage_m: float, pixel_area_m2: float) -> float:
    """Return the out-of-channel flooded area implied by a 256-bin HAND code histogram."""
    if len(histogram) != 256:
        raise ValueError("histogram must have 256 bins")
    codes = np.arange(256)
    wet = (codes != CHANNEL_CODE) & (codes != NEVER_CODE) & (codes * HAND_STEP_M < stage_m)
    return float(np.asarray(histogram, dtype=float)[wet].sum() * pixel_area_m2 / 1e6)


def road_state(min_hand_m: float, stage_m: float) -> RoadState:
    """Classify a road segment from its lowest sampled HAND value."""
    depth = round(stage_m - min_hand_m, 6)  # Avoid 3.5 - 3.2 == 0.2999999999999998.
    if depth >= IMPASSABLE_DEPTH_M:
        return "impassable"
    if depth > 0:
        return "wet"
    return "dry"
