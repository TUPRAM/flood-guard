"""A sturdier THEOS-2 water rule: the development draw and the candidates.

The plan is ``docs/proposal_execution/theos2_water_rule_v2_plan_v1.md``. This
module holds the pure functions; ``scripts/build_theos2_water_rule_v2.py``
reads the files.

The rule reads four uncalibrated bands of one image. Nothing here is a ground
check, and the development labels are the reading of an AI model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np

DEVELOPMENT_SEED: int = 20261012
KEEP_AWAY_PX: int = 10  # 20 m at the 2 m of the rule
NOT_DRAWN: int = 250    # a group index no group has: pixels too near a test point

# Points per group, in the order of floodguard.theos2_water_labels.GROUPS (plan section 2).
DEVELOPMENT_POINTS: dict[str, tuple[int, ...]] = {
    "sukhothai": (16, 16, 12, 16, 24, 12),
    "chip_003": (16, 16, 12, 16, 24, 12),
    "chip_001": (8, 8, 6, 8, 12, 6),
}


def away_from(shape: tuple[int, int], pixels: Iterable[tuple[int, int]], distance_px: int) -> np.ndarray:
    """True where a pixel is more than ``distance_px`` (in rows and in columns) from every pixel of ``pixels``."""

    free = np.ones(shape, dtype=bool)
    for row, column in pixels:
        free[max(0, row - distance_px):row + distance_px + 1, max(0, column - distance_px):column + distance_px + 1] = False
    return free


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

WATER_NO: int = 0
WATER_YES: int = 1
WATER_UNOBSERVABLE: int = 255


class WaterRuleError(ValueError):
    """The arrays or the configuration cannot support the rule."""


@dataclass(frozen=True)
class WaterRuleV2:
    """The second water rule. Every value is fixed; nothing is found on the image and nothing is set by eye.

    A pixel is water when its red-against-near-infrared index is at or below
    ``index_water_max``: water takes up near infrared, so the near-infrared
    value falls below the red one, also when the water is muddy. Cloud is
    white, and its index sits near zero. Inside a bright object at least
    ``cloud_min_width_px`` wide, a pixel whose index is above
    ``index_cloud_min`` is unobservable; a pixel below it is bright muddy
    water and stays water. The two brightness limits are those of rule v1.
    """

    index_water_max: float = -0.01
    index_cloud_min: float = -0.04
    bright_brightness_min: float = 520.0
    bright_nir_min: float = 560.0
    cloud_min_width_px: int = 40
    cloud_margin_px: int = 10


def red_nir_index(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """(NIR - red) / (NIR + red), the index known as NDVI; NaN where the sum is not positive.

    Plants push it up, water pulls it below zero.
    """

    r = np.asarray(red, dtype="float64")
    n = np.asarray(nir, dtype="float64")
    if r.shape != n.shape:
        raise WaterRuleError("red and nir must share one shape")
    total = r + n
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(total > 0, (n - r) / total, np.nan)


def water_v2(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    nir: np.ndarray,
    valid: np.ndarray,
    config: WaterRuleV2 = WaterRuleV2(),
) -> tuple[np.ndarray, dict[str, Any]]:
    """Classify each pixel of a four-band image as water, not water or unobservable with rule v2.

    Returns a ``uint8`` raster (0 not water, 1 water, 255 unobservable) and a
    summary with the configuration and the pixel counts.
    """

    from floodguard.theos2_cross_check import bright_object_mask

    bands = [np.asarray(band, dtype="float64") for band in (red, green, blue, nir)]
    mask = np.asarray(valid, dtype=bool)
    if bands[0].ndim != 2 or any(band.shape != bands[0].shape for band in bands) or mask.shape != bands[0].shape:
        raise WaterRuleError("the four bands and the valid mask must share one two-dimensional shape")
    if not config.index_cloud_min <= config.index_water_max:
        raise WaterRuleError("index_cloud_min must not lie above index_water_max")
    r, g, b, n = bands
    index = red_nir_index(r, n)
    bright = bright_object_mask(
        (r + g + b) / 3.0, n, brightness_min=config.bright_brightness_min, nir_min=config.bright_nir_min,
        min_width_px=config.cloud_min_width_px, margin_px=config.cloud_margin_px,
    )
    seen = mask & np.isfinite(index)
    with np.errstate(invalid="ignore"):
        cloud = seen & bright & (index > config.index_cloud_min)
        water = seen & ~cloud & (index <= config.index_water_max)
    result = np.full(mask.shape, WATER_UNOBSERVABLE, dtype="uint8")
    result[seen & ~cloud] = WATER_NO
    result[water] = WATER_YES
    summary = {
        "configuration": asdict(config),
        "pixels": int(mask.size),
        "valid_pixels": int(mask.sum()),
        "unobservable_cloud_pixels": int(cloud.sum()),
        "observable_pixels": int((seen & ~cloud).sum()),
        "water_pixels": int(water.sum()),
        "water_pixels_inside_bright_objects": int((water & bright).sum()),
    }
    return result, summary
