"""Planning frame v1: the national vulnerability anchors (protocol v1b, plan 3.4).

The vulnerability component of the planning frame is anchored on percentiles of
the dependent share (residents aged 0-14 plus residents aged 60 and over,
divided by all residents) across Thai tambons. This module holds the pure
arithmetic of that step: the dependent share of one unit, the unit set, the
percentile rule and the five anchors P5, P10, P75, P90 and P95.

It reads no file and scores nothing. It computes no FPPS, no A-E class and no
component value for any unit: the anchors are constants for the whole country.
The other parts of frame v1 that plan task E2 names (the component formulas and
the rejection of batch-scaled components) are not built here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

NORMALISATION_FRAME_VERSION = "planning_frame_v1"
ANCHOR_VERSION = "national_vulnerability_anchors_v1"
ANCHOR_PERCENTILES: tuple[int, ...] = (5, 10, 75, 90, 95)
MIN_UNIT_RESIDENTS = 100.0
ANCHOR_DECIMALS = 6
UNIT_SET_RULE = (
    "Every tha_admin3 unit with at least 100 modelled 2024 residents on the cells "
    "where all 20 age bands are valid. Units with no such cell, and units below "
    "100 residents, are left out and counted."
)
PERCENTILE_METHOD = (
    "Unweighted across units: every unit counts once. Linear interpolation between "
    "order statistics at position (n - 1) x p / 100 on the ascending values "
    "(Hyndman and Fan type 7, the numpy default)."
)
REQUIRED_UNIT_FIELDS = ("unit_id", "residents", "children_0_14", "older_60_plus")


class NormalisationError(ValueError):
    """Raised when anchor inputs break the planning-frame contract."""


def dependent_share(children_0_14: float, older_60_plus: float, residents: float) -> float:
    """Return (children aged 0-14 + adults aged 60 and over) / all residents.

    Args:
        children_0_14: Modelled residents aged 0-14.
        older_60_plus: Modelled residents aged 60 and over.
        residents: All modelled residents of the unit; must be positive.

    Raises:
        NormalisationError: for a non-finite or negative count, a zero
            denominator, or groups that exceed the total.
    """

    values = (children_0_14, older_60_plus, residents)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise NormalisationError("age counts must be numbers")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise NormalisationError("age counts must be finite and not negative")
    if residents <= 0:
        raise NormalisationError("a dependent share needs a positive resident count")
    dependants = children_0_14 + older_60_plus
    if dependants > residents * (1 + 1e-9) + 1e-9:
        raise NormalisationError("children and older adults exceed the resident count")
    return min(1.0, dependants / residents)


def percentile_linear(values: Sequence[float], percent: float) -> float:
    """Return a percentile by linear interpolation between order statistics.

    The position is ``(n - 1) * percent / 100`` on the ascending values, which
    is Hyndman and Fan type 7 and the default of ``numpy.percentile``.

    Raises:
        NormalisationError: for an empty or non-finite sample, or a percent
            outside 0-100.
    """

    if not 0 <= percent <= 100:
        raise NormalisationError("percent must lie between 0 and 100")
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise NormalisationError("a percentile needs at least one value")
    if any(not math.isfinite(value) for value in ordered):
        raise NormalisationError("percentile values must be finite")
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def percentile_weighted(values: Sequence[float], weights: Sequence[float], percent: float) -> float:
    """Return a resident-weighted percentile (lowest value whose cumulative weight reaches the share).

    This is not the anchor rule. It exists so the receipt can show the owners
    how far a different percentile rule would move the anchors.
    """

    if not 0 <= percent <= 100:
        raise NormalisationError("percent must lie between 0 and 100")
    if len(values) != len(weights) or not values:
        raise NormalisationError("values and weights must be non-empty and the same length")
    pairs = sorted((float(value), float(weight)) for value, weight in zip(values, weights))
    if any(not math.isfinite(value) or not math.isfinite(weight) or weight <= 0 for value, weight in pairs):
        raise NormalisationError("weighted percentile needs finite values and positive weights")
    target = math.fsum(weight for _value, weight in pairs) * percent / 100
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= target:
            return value
    return pairs[-1][0]


def select_anchor_units(
    units: Iterable[Mapping[str, Any]],
    *,
    min_residents: float = MIN_UNIT_RESIDENTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply the unit-set rule and return the units used, with their dependent share.

    Args:
        units: One mapping per administrative unit with ``unit_id``,
            ``residents``, ``children_0_14`` and ``older_60_plus``. A unit with
            no valid age cell carries ``None`` in the three counts.
        min_residents: The minimum-denominator rule (guardrail GR1 uses 100).

    Returns:
        The used units sorted by ``unit_id``, each with ``dependent_share``,
        and a count of the units read, used and left out by reason.

    Raises:
        NormalisationError: for a missing field or a repeated ``unit_id``.
    """

    if isinstance(min_residents, bool) or not math.isfinite(min_residents) or min_residents <= 0:
        raise NormalisationError("min_residents must be a positive number")
    used: list[dict[str, Any]] = []
    counts = {"units_read": 0, "units_used": 0, "excluded_no_age_support": 0, "excluded_below_min_residents": 0}
    seen: set[str] = set()
    for unit in units:
        missing = [field for field in REQUIRED_UNIT_FIELDS if field not in unit]
        if missing:
            raise NormalisationError(f"unit record lacks {', '.join(missing)}")
        unit_id = str(unit["unit_id"])
        if not unit_id or unit_id in seen:
            raise NormalisationError("unit_id values must be present and unique")
        seen.add(unit_id)
        counts["units_read"] += 1
        residents = unit["residents"]
        if residents is None:
            counts["excluded_no_age_support"] += 1
            continue
        if residents < min_residents:
            counts["excluded_below_min_residents"] += 1
            continue
        share = dependent_share(unit["children_0_14"], unit["older_60_plus"], residents)
        used.append({"unit_id": unit_id, "residents": float(residents), "dependent_share": share})
        counts["units_used"] += 1
    used.sort(key=lambda row: row["unit_id"])
    return used, counts


def national_vulnerability_anchors(
    units: Iterable[Mapping[str, Any]],
    *,
    min_residents: float = MIN_UNIT_RESIDENTS,
    percentiles: Sequence[int] = ANCHOR_PERCENTILES,
    decimals: int = ANCHOR_DECIMALS,
) -> dict[str, Any]:
    """Compute the national dependent-share anchors from per-unit age counts.

    The returned ``values`` are rounded to ``decimals`` places; those rounded
    numbers are the constants the protocol records. ``values_full_precision``
    keeps the unrounded results for audit.

    Raises:
        NormalisationError: when no unit passes the unit-set rule, or the
            anchors are not strictly increasing (a degenerate frame).
    """

    used, counts = select_anchor_units(units, min_residents=min_residents)
    if not used:
        raise NormalisationError("no unit passes the unit-set rule")
    shares = [row["dependent_share"] for row in used]
    full = {f"P{percent}": percentile_linear(shares, percent) for percent in percentiles}
    values = {key: round(value, decimals) for key, value in full.items()}
    ordered = [values[f"P{percent}"] for percent in sorted(percentiles)]
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:])):
        raise NormalisationError("anchors must be strictly increasing; the frame is degenerate")
    return {
        "anchor_version": ANCHOR_VERSION,
        "frame_version": NORMALISATION_FRAME_VERSION,
        "values": values,
        "values_full_precision": full,
        "decimals": decimals,
        "unit_set_rule": UNIT_SET_RULE,
        "percentile_method": PERCENTILE_METHOD,
        "min_unit_residents": float(min_residents),
        "unit_count": counts["units_used"],
        "excluded_unit_count": counts["units_read"] - counts["units_used"],
        "counts": counts,
        "distribution": {
            "minimum": min(shares),
            "median": percentile_linear(shares, 50),
            "mean": math.fsum(shares) / len(shares),
            "maximum": max(shares),
        },
        "residents_in_used_units": math.fsum(row["residents"] for row in used),
    }
