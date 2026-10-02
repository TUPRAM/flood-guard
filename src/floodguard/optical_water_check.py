"""Sentinel-2 water check for a case replay: MNDWI on clear pixels, and how its area compares with the model.

The check answers one question about an optical scene: where the scene classification says the ground was seen,
how much of it reads as open water or water-logged ground? It uses the modified normalised difference water index

    MNDWI = (green - swir16) / (green + swir16)

on surface reflectance (digital number / 10000 for the Earth Search L2A files, see
:func:`floodguard.flood_timeline.sentinel2_l2a_reflectance`). A positive index means the surface absorbs
short-wave infrared more than it reflects green light, which open water does, and so do saturated mud and wet
sediment. The result is therefore labelled "water or saturated mud", never "flood extent".

Everything here is a pure function on arrays that already share one grid. Nothing opens a file, and nothing is a
real-time detector, a validated flood map or an official warning. The area comparison with the model is
indicative: it uses unrounded cell counts, one threshold and no field check.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from floodguard.flood_timeline import sentinel2_l2a_reflectance

MNDWI_THRESHOLD = 0.0
"""A pixel reads as water or saturated mud when its MNDWI is above this value."""

SCL_CLASSES: Mapping[int, str] = {
    0: "no_data",
    1: "saturated_or_defective",
    2: "dark_area",
    3: "cloud_shadow",
    4: "vegetation",
    5: "not_vegetated",
    6: "water",
    7: "unclassified",
    8: "cloud_medium_probability",
    9: "cloud_high_probability",
    10: "thin_cirrus",
    11: "snow_or_ice",
}
"""Sentinel-2 L2A scene classification (SCL) values."""

SCL_NOT_CLEAR: frozenset[int] = frozenset({0, 3, 8, 9, 10})
"""SCL classes the check drops: no data, cloud shadow, cloud (medium and high probability) and thin cirrus."""

SCL_STRICT_CLEAR: frozenset[int] = frozenset({4, 5, 6})
"""A stricter reading of "clear" used as a sensitivity: vegetation, bare ground and water only."""


@dataclass(frozen=True)
class WetSurface:
    """MNDWI, the clear mask and the water-or-saturated-mud mask of one scene, on one grid."""

    index: np.ndarray
    clear: np.ndarray
    wet: np.ndarray


def mndwi(green: np.ndarray, swir16: np.ndarray) -> np.ndarray:
    """Return MNDWI = (green - swir16) / (green + swir16) for two reflectance arrays.

    The inputs are surface reflectance (not digital numbers). A cell is NaN where either band is not finite or
    where the two bands do not sum to a positive value.
    """
    g = np.asarray(green, dtype=np.float64)
    s = np.asarray(swir16, dtype=np.float64)
    if g.shape != s.shape:
        raise ValueError("green and swir16 must share one shape")
    total = g + s
    usable = np.isfinite(g) & np.isfinite(s) & (total > 0)
    out = np.full(g.shape, np.nan, dtype=np.float64)
    np.divide(g - s, total, out=out, where=usable)
    return out


def scl_clear_mask(scl: np.ndarray, not_clear: Iterable[int] = SCL_NOT_CLEAR) -> np.ndarray:
    """Return True where the scene classification says the ground was seen.

    By default it drops class 0 (no data), 3 (cloud shadow), 8 and 9 (cloud) and 10 (thin cirrus). Values outside
    the SCL range 0-11 are treated as no data.
    """
    values = np.asarray(scl)
    dropped = sorted({int(value) for value in not_clear})
    known = np.isin(values, sorted(SCL_CLASSES))
    return known & ~np.isin(values, dropped)


def wet_surface(green_dn: np.ndarray, swir16_dn: np.ndarray, scl: np.ndarray, threshold: float = MNDWI_THRESHOLD,
                not_clear: Iterable[int] = SCL_NOT_CLEAR) -> WetSurface:
    """Return the MNDWI, the clear mask and the water-or-saturated-mud mask of one L2A scene.

    ``green_dn`` and ``swir16_dn`` are Earth Search L2A digital numbers on one grid (0 = no data); reflectance is
    DN / 10000 with nothing subtracted. A pixel is clear when its SCL class is kept and both bands hold data; it is
    wet when it is clear and its MNDWI is above ``threshold``.
    """
    index = mndwi(sentinel2_l2a_reflectance(green_dn), sentinel2_l2a_reflectance(swir16_dn))
    if np.shape(scl) != index.shape:
        raise ValueError("the scene classification must be on the same grid as the bands")
    clear = scl_clear_mask(scl, not_clear) & np.isfinite(index)
    return WetSurface(index=index, clear=clear, wet=clear & (index > threshold))


def upsample(mask: np.ndarray, factor: int) -> np.ndarray:
    """Repeat every cell ``factor`` times along both axes (a 20 m mask onto the 10 m grid it nests in)."""
    if factor < 1:
        raise ValueError("factor must be at least 1")
    return np.repeat(np.repeat(np.asarray(mask), factor, axis=0), factor, axis=1)


def _km2(mask: np.ndarray, cell_km2: float) -> float:
    return float(np.count_nonzero(mask)) * cell_km2


def _same_shape(*arrays: np.ndarray) -> None:
    shapes = {np.shape(array) for array in arrays}
    if len(shapes) != 1:
        raise ValueError(f"every mask must share one grid; got shapes {sorted(shapes)}")


def scene_areas(wet: np.ndarray, clear: np.ndarray, area: np.ndarray, permanent: np.ndarray, cell_km2: float) -> dict:
    """Clear share and water-or-saturated-mud area of one scene inside ``area``.

    ``permanent`` marks cells left out of the water area on every date (the caller's permanent-water rule). The
    clear share is the clear part of ``area``, permanent cells included; the water area counts clear cells outside
    ``permanent`` only. With nothing clear the water area is ``None``: nothing was observed, which is not zero.
    """
    _same_shape(wet, clear, area, permanent)
    wet, clear, area, permanent = (np.asarray(a, dtype=bool) for a in (wet, clear, area, permanent))
    if np.any(wet & ~clear):
        raise ValueError("a wet cell must be a clear cell")
    area_km2 = _km2(area, cell_km2)
    if area_km2 <= 0:
        raise ValueError("the area of interest is empty")
    clear_km2 = _km2(clear & area, cell_km2)
    seen = clear & area & ~permanent
    return {
        "clear_km2": round(clear_km2, 2),
        "clear_share": round(clear_km2 / area_km2, 3),
        "water_km2": round(_km2(wet & seen, cell_km2), 2) if clear_km2 > 0 else None,
    }


def new_water_areas(event_wet: np.ndarray, event_clear: np.ndarray, pre_wet: np.ndarray, pre_clear: np.ndarray,
                    area: np.ndarray, permanent: np.ndarray, cell_km2: float) -> dict:
    """Water or saturated mud on the event date that was not there on the earlier date, where both dates are clear."""
    _same_shape(event_wet, event_clear, pre_wet, pre_clear, area, permanent)
    both = (np.asarray(event_clear, dtype=bool) & np.asarray(pre_clear, dtype=bool) & np.asarray(area, dtype=bool)
            & ~np.asarray(permanent, dtype=bool))
    event = np.asarray(event_wet, dtype=bool) & both
    pre = np.asarray(pre_wet, dtype=bool) & both
    both_km2 = _km2(both, cell_km2)
    return {
        "both_clear_km2": round(both_km2, 2),
        "event_water_km2": round(_km2(event, cell_km2), 2) if both_km2 > 0 else None,
        "pre_event_water_km2": round(_km2(pre, cell_km2), 2) if both_km2 > 0 else None,
        "new_water_km2": round(_km2(event & ~pre, cell_km2), 2) if both_km2 > 0 else None,
        "no_longer_water_km2": round(_km2(pre & ~event, cell_km2), 2) if both_km2 > 0 else None,
    }


def model_overlap(wet: np.ndarray, clear: np.ndarray, model_wet: np.ndarray, area: np.ndarray, permanent: np.ndarray,
                  cell_km2: float) -> dict:
    """How the modelled water compares with the observed water or saturated mud, inside the clear part of ``area``.

    Every figure is a model value placed beside the observation (key names start with ``model_``):
    the model's area in the whole of ``area`` and in its clear part, the overlap, the union, their ratio
    (``model_agreement_iou``), the share of the observed area the model reaches and the share of the modelled area
    the observation confirms as wet. Ratios are ``None`` when their denominator is zero.
    """
    _same_shape(wet, clear, model_wet, area, permanent)
    area = np.asarray(area, dtype=bool) & ~np.asarray(permanent, dtype=bool)
    model = np.asarray(model_wet, dtype=bool) & area
    seen = np.asarray(clear, dtype=bool) & area
    observed = np.asarray(wet, dtype=bool) & seen
    model_seen = model & seen
    overlap = _km2(observed & model_seen, cell_km2)
    union = _km2(observed | model_seen, cell_km2)
    observed_km2 = _km2(observed, cell_km2)
    model_seen_km2 = _km2(model_seen, cell_km2)

    def ratio(numerator: float, denominator: float) -> float | None:
        return round(numerator / denominator, 3) if denominator > 0 else None

    return {
        "model_flood_km2_district": round(_km2(model, cell_km2), 2),
        "model_flood_km2_clear": round(model_seen_km2, 2),
        "model_overlap_km2": round(overlap, 2),
        "model_union_km2": round(union, 2),
        "model_agreement_iou": ratio(overlap, union),
        "model_share_of_observed_water_reached": ratio(overlap, observed_km2),
        "model_share_inside_observed_water": ratio(overlap, model_seen_km2),
    }


def class_areas(scl: np.ndarray, area: np.ndarray, cell_km2: float) -> dict[str, float]:
    """Area of every scene-classification class present inside ``area``, keyed by class name."""
    _same_shape(scl, area)
    values = np.asarray(scl)[np.asarray(area, dtype=bool)]
    out: dict[str, float] = {}
    for value in np.unique(values).tolist():
        name = SCL_CLASSES.get(int(value), "no_data")
        out[name] = round(out.get(name, 0.0) + float(np.count_nonzero(values == value)) * cell_km2, 2)
    return out
