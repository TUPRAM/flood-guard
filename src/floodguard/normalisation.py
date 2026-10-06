"""Planning frame v1 (protocol v1a ``scoring_frame``, decision D4; plan 3.4, task E2).

The module has two parts.

**The national vulnerability anchors** (protocol v1b). The vulnerability
component is anchored on percentiles of the dependent share (residents aged
0-14 plus residents aged 60 and over, divided by all residents) across Thai
tambons. The first part holds the pure arithmetic of that step: the dependent
share of one unit, the unit set, the percentile rule and the five anchors P5,
P10, P75, P90 and P95. It computed the values that protocol v1b records and is
unchanged since.

**The scoring frame.** The second part turns the measured quantities of one unit
into the five FPPS components, each on 0-100, exactly as the signed protocol
states them:

* flood likelihood: ``100 x min(1, flooded share of non-permanent-water land / anchor)``,
  with the anchor of decision D4 and its two one-at-a-time sensitivity values;
* exposure: share only, ``100 x residents inside the extent / unit residents``;
* access gap: the baseline-access-weighted mean of the newly-lost access shares;
* road criticality: ``100 x residents who lose all routes / residents with a baseline route``;
* vulnerability: the dependent share between the national P10 and P90 anchors.

Every anchor, weight and service threshold is read from the two protocol files
(:func:`load_planning_frame`); none is written in this module. The scale is
absolute: a component is a function of its own unit's inputs and of declared
constants, never of the other units in a batch. :func:`reject_batch_scaled_components`
is the check of guardrail GR2: it recomputes every component record from the
inputs the row echoes and refuses a row whose value, or any other field of the
record, differs. Every component record carries the SHA-256 of the two protocol
files that produced it, and a frame that was not read from the files in force
(:func:`load_planning_frame`) computes nothing.
:func:`leave_one_component_out_weights` gives the weights of the
leave-one-component-out rule (drafter reading DR-A02).

The module computes no FPPS and no A-E class. Where the protocol states no value
(a unit with no non-permanent-water land, no resident, or nobody with baseline
access) a function raises :class:`NormalisationError`; it does not pick one.
Component values are planning inputs, not observations of a flood and not an
official warning.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any

from floodguard.scoring import SCORE_COMPONENTS, validate_weights

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


# ---------------------------------------------------------------------------
# Frame v1: the declared constants, read from the signed protocol files
# ---------------------------------------------------------------------------

PUBLIC_LEVEL = "public"
PITCH_LEVEL = "pitch"
PROTOCOL_SIGNED = "signed"
LOCO_READING = "DR-A02"
GUARDRAIL_GR2 = "GR2_no_max_normalisation"
PROTOCOL_NAMES: tuple[str, ...] = ("v1a", "v1b")
SHARE_TOLERANCE = 1e-9
# The float guard of the GR2 value comparison. It is fixed: the check takes no tolerance from its caller.
VERIFY_TOLERANCE = 1e-9
VALUE_FIELD = "value_0_100"
_ABSENT = object()
# Row fields of docs/model_contract.md section 2b. Guardrail GR2: they apply to the GeoAI runner only.
GEOAI_RUNNER_ANCHOR_FIELDS: tuple[str, ...] = ("flood_anchor_version", "exposure_anchor_version")


class BatchScalingError(NormalisationError):
    """Raised when a component is not the absolute frame v1 value of its own inputs (guardrail GR2)."""


@dataclass(frozen=True)
class AccessService:
    """One service of the access-gap component, as protocol v1a declares it."""

    service: str
    mode: str
    threshold_minutes: int
    level: str


@dataclass(frozen=True, eq=False)
class PlanningFrame:
    """The constants of planning frame v1. Every value comes from the protocol files."""

    version: str
    weights: Mapping[str, float]
    definitions: Mapping[str, str]
    normalisation_rule: str
    flood_anchor: float
    flood_anchor_sensitivity: tuple[float, ...]
    flood_anchor_disclosure: str
    permanent_water: Mapping[str, Any]
    access_services: tuple[AccessService, ...]
    vulnerability_anchors: Mapping[str, float]
    vulnerability_bounds: tuple[str, str]
    vulnerability_sensitivity_bounds: tuple[str, str]
    vulnerability_anchor_receipt_sha256: str
    vulnerability_caveat: str
    lane_disclosure: str
    protocol_sha256: Mapping[str, str | None]


def read_protocol_in_force(name: str, path: Path | str, receipts_path: Path | str) -> tuple[dict[str, Any], str]:
    """Read one planning protocol file and refuse it unless it is in force.

    A protocol is in force when its status is ``signed`` and every line of
    ``RECEIPTS.jsonl`` that records a hash for it names the SHA-256 of exactly
    these bytes (protocol v1a, ``change_control.receipt``).

    Args:
        name: ``v1a`` or ``v1b``.
        path: The protocol file.
        receipts_path: The ``RECEIPTS.jsonl`` file that records the signed hashes.

    Returns:
        The parsed protocol and the SHA-256 of its bytes.

    Raises:
        NormalisationError: when the file is not signed, or no receipt or another hash is recorded.
    """

    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    protocol = json.loads(data.decode("utf-8"))
    key = f"planning_protocol_{name}_sha256"
    recorded: set[str] = set()
    for line in Path(receipts_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        outputs = json.loads(line).get("output_hashes")
        if isinstance(outputs, dict) and key in outputs:
            recorded.add(str(outputs[key]))
    if protocol.get("status") != PROTOCOL_SIGNED or recorded != {digest}:
        raise NormalisationError(
            f"planning protocol {name} is not in force: its status must be signed and the receipts "
            "must record the SHA-256 of exactly these bytes"
        )
    return protocol, digest


def load_planning_frame(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> PlanningFrame:
    """Read frame v1 from the two protocol files, which must both be in force.

    Raises:
        NormalisationError: when a file is not in force, v1b names another v1a,
            or a frame parameter is missing.
    """

    v1a, v1a_sha256 = read_protocol_in_force("v1a", v1a_path, receipts_path)
    v1b, v1b_sha256 = read_protocol_in_force("v1b", v1b_path, receipts_path)
    if v1b.get("depends_on", {}).get("v1a_sha256") != v1a_sha256:
        raise NormalisationError("protocol v1b does not name the v1a file that was read")
    return _checked_frame(v1a, v1b, {"v1a": v1a_sha256, "v1b": v1b_sha256})


def planning_frame_from_protocols(v1a: Mapping[str, Any], v1b: Mapping[str, Any]) -> PlanningFrame:
    """Check that the parsed protocols v1a (the rules) and v1b (the national anchors) hold frame v1.

    The frame this returns carries no protocol hash, because parsed mappings
    cannot be tied to the bytes that ``RECEIPTS.jsonl`` records. It shows what
    a parsed file declares; the component functions, :func:`frame_record` and
    the GR2 check refuse it. A frame that computes comes from
    :func:`load_planning_frame` only.

    Args:
        v1a: The parsed decision-rules protocol; its ``scoring_frame`` is read.
        v1b: The parsed engineering protocol; its ``national_vulnerability_anchors`` are read.

    Raises:
        NormalisationError: when a file is not signed, declares another frame
            version or an exposure anchor, leaves an anchor empty, or lacks a parameter.
    """

    return _checked_frame(v1a, v1b, {name: None for name in PROTOCOL_NAMES})


def _checked_frame(v1a: Mapping[str, Any], v1b: Mapping[str, Any], hashes: Mapping[str, str | None]) -> PlanningFrame:
    """Build frame v1; a parameter the files lack becomes NormalisationError."""

    try:
        return _frame(v1a, v1b, hashes)
    except NormalisationError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise NormalisationError(f"the protocol files do not hold the frame v1 parameters: {error!r}") from error


def _frame(v1a: Mapping[str, Any], v1b: Mapping[str, Any], hashes: Mapping[str, str | None]) -> PlanningFrame:
    """Read every frame constant; a missing key is turned into NormalisationError by the caller."""

    if v1a["status"] != PROTOCOL_SIGNED or v1b["status"] != PROTOCOL_SIGNED:
        raise NormalisationError("frame v1 is read from signed protocol files only")
    frame = v1a["scoring_frame"]
    if frame["version"] != NORMALISATION_FRAME_VERSION:
        raise NormalisationError(f"this module implements {NORMALISATION_FRAME_VERSION}, not {frame['version']!r}")
    components = frame["components"]
    if set(components) != set(SCORE_COMPONENTS) or set(frame["weights"]) != set(SCORE_COMPONENTS):
        raise NormalisationError("the protocol does not declare exactly the five FPPS components")
    readings = [row["status"] for row in v1a["drafter_readings"] if row["id"] == LOCO_READING]
    if readings != ["confirmed"]:
        raise NormalisationError(f"drafter reading {LOCO_READING} (leave-one-component-out) is not confirmed")

    flood = components["flood_likelihood_0_100"]
    exposure_rule = components["exposure_0_100"]
    exposure_anchors = [exposure_rule["headcount_anchor"], exposure_rule["density_anchor"]]
    if exposure_rule["kind"] != "share_only" or exposure_anchors != [None, None]:
        raise NormalisationError("this module implements share-only exposure; the protocol declares an anchor")

    access = components["access_gap_0_100"]
    levels = ((PUBLIC_LEVEL, access["public_level_services"]), (PITCH_LEVEL, access["pitch_level_adds"]))
    services = tuple(
        AccessService(str(row["service"]), str(row["mode"]), int(row["threshold_minutes"]), level)
        for level, rows in levels
        for row in rows
    )
    if len({service.service for service in services}) != len(services) or not access["public_level_services"]:
        raise NormalisationError("the access-gap services must be named once each, with a public service")

    vulnerability = components["vulnerability_context_0_100"]
    section = v1b["national_vulnerability_anchors"]
    if section["status"] != "fixed":
        raise NormalisationError("the national vulnerability anchors are not fixed in protocol v1b")
    anchors = {str(key): _unit_interval(value, f"national anchor {key}") for key, value in section["values"].items()}
    bounds = (_anchor_key(vulnerability["lower_anchor"]), _anchor_key(vulnerability["upper_anchor"]))
    sensitivity = vulnerability["anchor_sensitivity"]
    sensitivity_bounds = (_anchor_key(sensitivity["lower"]), _anchor_key(sensitivity["upper"]))
    for lower, upper in (bounds, sensitivity_bounds):
        if not anchors[lower] < anchors[upper]:
            raise NormalisationError("the lower vulnerability anchor must be below the upper one")

    water = flood["permanent_water"]
    return PlanningFrame(
        version=NORMALISATION_FRAME_VERSION,
        weights=MappingProxyType({name: float(frame["weights"][name]) for name in SCORE_COMPONENTS}),
        definitions=MappingProxyType({name: str(components[name]["definition"]) for name in SCORE_COMPONENTS}),
        normalisation_rule=str(frame["normalisation"]),
        flood_anchor=_unit_interval(flood["anchor"], "the flood anchor"),
        flood_anchor_sensitivity=tuple(
            _unit_interval(value, "a flood sensitivity anchor") for value in flood["anchor_sensitivity_one_at_a_time"]
        ),
        flood_anchor_disclosure=str(flood["anchor_disclosure"]),
        permanent_water=MappingProxyType({"source": str(water["source"]), "class": int(water["class"])}),
        access_services=services,
        vulnerability_anchors=MappingProxyType(anchors),
        vulnerability_bounds=bounds,
        vulnerability_sensitivity_bounds=sensitivity_bounds,
        vulnerability_anchor_receipt_sha256=str(section["output_receipt"]["sha256"]),
        vulnerability_caveat=str(vulnerability["caveat"]),
        lane_disclosure=str(frame["lane_disclosure"]),
        protocol_sha256=MappingProxyType(dict(hashes)),
    )


def _unit_interval(value: Any, name: str) -> float:
    """Return a declared anchor, which must be a number strictly between 0 and 1."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NormalisationError(f"{name} is not a number in the protocol")
    if not 0 < value < 1:
        raise NormalisationError(f"{name} must lie strictly between 0 and 1")
    return float(value)


def _anchor_key(name: Any) -> str:
    """Turn the protocol's anchor name (``national_P10``) into the key of the anchor values (``P10``)."""

    return str(name).removeprefix("national_")


def protocol_hashes(frame: PlanningFrame) -> dict[str, str]:
    """Return the SHA-256 of the two protocol files a frame was read from.

    Protocol v1a, ``change_control``: outputs carry ``protocol_sha256`` so each
    value can be tied to the protocol bytes that produced it.

    Raises:
        NormalisationError: when the frame carries no hash for either file, so
            it was not read from the files in force.
    """

    hashes = {name: frame.protocol_sha256.get(name) for name in PROTOCOL_NAMES}
    if not all(isinstance(value, str) and value for value in hashes.values()):
        raise NormalisationError(
            "frame v1 carries no protocol hashes: read it with load_planning_frame, "
            "which checks both files against RECEIPTS.jsonl"
        )
    return hashes


def frame_record(frame: PlanningFrame) -> dict[str, Any]:
    """Return the frame header a planning row cites: version, anchors, weights and protocol hashes.

    Raises:
        NormalisationError: for a frame that was not read from the protocol files in force.
    """

    hashes = protocol_hashes(frame)
    lower, upper = frame.vulnerability_bounds
    sensitivity_lower, sensitivity_upper = frame.vulnerability_sensitivity_bounds
    return {
        "normalisation_version": frame.version,
        "normalisation_rule": frame.normalisation_rule,
        "weights": dict(frame.weights),
        "flood_anchor": frame.flood_anchor,
        "flood_anchor_sensitivity_one_at_a_time": list(frame.flood_anchor_sensitivity),
        "flood_anchor_disclosure": frame.flood_anchor_disclosure,
        "permanent_water": dict(frame.permanent_water),
        "exposure_kind": "share_only",
        "access_services": [
            {
                "service": service.service,
                "mode": service.mode,
                "threshold_minutes": service.threshold_minutes,
                "level": service.level,
            }
            for service in frame.access_services
        ],
        "vulnerability_anchor_version": ANCHOR_VERSION,
        "vulnerability_anchors": {"lower": lower, "upper": upper, "values": dict(frame.vulnerability_anchors)},
        "vulnerability_anchor_sensitivity": {"lower": sensitivity_lower, "upper": sensitivity_upper},
        "vulnerability_anchor_receipt_sha256": frame.vulnerability_anchor_receipt_sha256,
        "leave_one_component_out_weights": leave_one_component_out_weights(frame.weights),
        "lane_disclosure": frame.lane_disclosure,
        "protocol_sha256": hashes,
    }


# ---------------------------------------------------------------------------
# Frame v1: the five components, each for one unit, each on 0-100
# ---------------------------------------------------------------------------


def _count(value: Any, name: str) -> float:
    """Return a measured quantity (residents or area) as a float; it must be finite and not negative.

    Any real number type is taken (a numpy scalar from a raster sum, for
    example). The component records echo the float this returns, so a record is
    plain JSON whatever type the caller passed.
    """

    if isinstance(value, bool) or not isinstance(value, Real):
        raise NormalisationError(f"{name} must be one number for one unit")
    if not math.isfinite(value) or value < 0:
        raise NormalisationError(f"{name} must be finite and not negative")
    return float(value)


def _share(numerator: float, denominator: float, part_name: str, whole_name: str) -> float:
    """Return part / whole for one unit, refusing a zero denominator and a part above the whole."""

    if denominator <= 0:
        raise NormalisationError(f"{whole_name} is zero: the protocol states no component value for such a unit")
    if numerator > denominator * (1 + SHARE_TOLERANCE) + SHARE_TOLERANCE:
        raise NormalisationError(f"{part_name} exceeds {whole_name}")
    return min(1.0, numerator / denominator)


def _anchored(share: float, anchor: float) -> float:
    """Return 100 x min(1, share / anchor)."""

    return 100.0 * min(1.0, share / anchor)


def _between(share: float, lower: float, upper: float) -> float:
    """Return 100 x clip((share - lower) / (upper - lower), 0, 1)."""

    return 100.0 * min(1.0, max(0.0, (share - lower) / (upper - lower)))


def flood_likelihood(
    frame: PlanningFrame,
    *,
    flooded_non_permanent_water_land_area: float,
    non_permanent_water_land_area: float,
) -> dict[str, Any]:
    """Flood likelihood: 100 x min(1, flooded share of the unit's non-permanent-water land / anchor).

    Args:
        frame: Frame v1, from :func:`load_planning_frame`.
        flooded_non_permanent_water_land_area: The unit's land inside the flood
            extent, permanent water left out. Any one area unit.
        non_permanent_water_land_area: The unit's land with permanent water left
            out (WorldCover class 80 in every case), in the same unit.

    Returns:
        The value on the signed anchor, the two one-at-a-time sensitivity
        values, the anchor disclosure and the inputs.

    Raises:
        NormalisationError: for a unit with no non-permanent-water land, a
            flooded area above the land area, or a frame not read from the files in force.
    """

    hashes = protocol_hashes(frame)
    flooded = _count(flooded_non_permanent_water_land_area, "flooded_non_permanent_water_land_area")
    land = _count(non_permanent_water_land_area, "non_permanent_water_land_area")
    share = _share(flooded, land, "flooded_non_permanent_water_land_area", "non_permanent_water_land_area")
    return {
        "component": "flood_likelihood_0_100",
        "value_0_100": _anchored(share, frame.flood_anchor),
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "definition": frame.definitions["flood_likelihood_0_100"],
        "inputs": {"flooded_non_permanent_water_land_area": flooded, "non_permanent_water_land_area": land},
        "flooded_share": share,
        "anchor": frame.flood_anchor,
        "anchor_sensitivity_one_at_a_time": [
            {"anchor": anchor, "value_0_100": _anchored(share, anchor)} for anchor in frame.flood_anchor_sensitivity
        ],
        "anchor_disclosure": frame.flood_anchor_disclosure,
        "permanent_water": dict(frame.permanent_water),
    }


def exposure(frame: PlanningFrame, *, residents_inside_flood_extent: float, unit_residents: float) -> dict[str, Any]:
    """Exposure, share only: 100 x residents whose cell centre is inside the extent / unit residents.

    No headcount anchor and no density anchor exists in frame v1, so the value
    does not change when both counts are multiplied by one factor.

    Raises:
        NormalisationError: for a unit with no resident, more exposed residents
            than residents, or a frame not read from the files in force.
    """

    hashes = protocol_hashes(frame)
    inside = _count(residents_inside_flood_extent, "residents_inside_flood_extent")
    residents = _count(unit_residents, "unit_residents")
    share = _share(inside, residents, "residents_inside_flood_extent", "unit_residents")
    return {
        "component": "exposure_0_100",
        "value_0_100": 100.0 * share,
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "definition": frame.definitions["exposure_0_100"],
        "inputs": {"residents_inside_flood_extent": inside, "unit_residents": residents},
        "exposed_share": share,
        "kind": "share_only",
    }


def access_gap(frame: PlanningFrame, *, services: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Access gap: the baseline-access-weighted mean of the newly-lost access shares.

    For each service the newly-lost share is the residents who lose access over
    the residents who had it at baseline; nobody without baseline access is
    counted. The shares are averaged with the baseline-access residents of each
    service as weights, which is the residents newly losing access over the
    residents with baseline access, summed over the services.

    Args:
        frame: Frame v1.
        services: One entry per service. The names are either the public-level
            services of the protocol or those plus the pitch-level one. Each
            entry states ``mode`` and ``threshold_minutes`` (they must be the
            protocol's), ``baseline_access_residents`` and ``newly_lost_residents``.

    Raises:
        NormalisationError: for another set of services, another mode or
            threshold, more residents losing access than had it, a unit where
            nobody had baseline access to any service, or a frame not read from
            the files in force.
    """

    hashes = protocol_hashes(frame)
    if not isinstance(services, Mapping):
        raise NormalisationError("services must map each service name to its counts")
    public = {service.service for service in frame.access_services if service.level == PUBLIC_LEVEL}
    declared = {service.service for service in frame.access_services}
    if set(services) == public:
        level = PUBLIC_LEVEL
    elif set(services) == declared:
        level = PITCH_LEVEL
    else:
        raise NormalisationError(
            f"the access gap takes the services {sorted(public)} (public level) or {sorted(declared)} (pitch level)"
        )
    rows: list[dict[str, Any]] = []
    weighted_shares: list[float] = []
    for service in frame.access_services:
        if service.service not in services:
            continue
        supplied = services[service.service]
        if not isinstance(supplied, Mapping):
            raise NormalisationError(f"service {service.service} needs a mapping of its counts")
        if supplied.get("mode") != service.mode or supplied.get("threshold_minutes") != service.threshold_minutes:
            raise NormalisationError(
                f"service {service.service} is declared as {service.mode}, {service.threshold_minutes} minutes"
            )
        baseline = _count(supplied.get("baseline_access_residents"), f"{service.service} baseline_access_residents")
        lost = _count(supplied.get("newly_lost_residents"), f"{service.service} newly_lost_residents")
        if lost > baseline * (1 + SHARE_TOLERANCE) + SHARE_TOLERANCE:
            raise NormalisationError(
                f"{service.service}: newly lost access is counted only for residents who had access at baseline"
            )
        share = None
        if baseline > 0:
            share = min(1.0, lost / baseline)
            weighted_shares.append(baseline * share)
        rows.append({
            "service": service.service,
            "mode": service.mode,
            "threshold_minutes": service.threshold_minutes,
            "baseline_access_residents": baseline,
            "newly_lost_residents": lost,
            "newly_lost_share": share,
        })
    total = math.fsum(row["baseline_access_residents"] for row in rows)
    if total <= 0:
        raise NormalisationError(
            "no resident had baseline access to any service: the protocol states no access gap for such a unit"
        )
    return {
        "component": "access_gap_0_100",
        "value_0_100": 100.0 * min(1.0, math.fsum(weighted_shares) / total),
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "definition": frame.definitions["access_gap_0_100"],
        "inputs": {
            "services": {
                row["service"]: {
                    "mode": row["mode"],
                    "threshold_minutes": row["threshold_minutes"],
                    "baseline_access_residents": row["baseline_access_residents"],
                    "newly_lost_residents": row["newly_lost_residents"],
                }
                for row in rows
            },
        },
        "services": rows,
        "baseline_access_residents_all_services": total,
        "publication_level": level,
    }


def road_criticality(
    frame: PlanningFrame,
    *,
    residents_losing_all_routes: float,
    residents_with_baseline_route: float,
) -> dict[str, Any]:
    """Road criticality: 100 x residents who lose all routes / residents with a baseline route.

    The residents counted are those with a baseline route to any hospital or
    main road; the numerator is those among them who lose every such route.

    Raises:
        NormalisationError: for a unit where nobody had a baseline route, more
            residents losing their routes than had one, or a frame not read from
            the files in force.
    """

    hashes = protocol_hashes(frame)
    losing = _count(residents_losing_all_routes, "residents_losing_all_routes")
    connected = _count(residents_with_baseline_route, "residents_with_baseline_route")
    share = _share(losing, connected, "residents_losing_all_routes", "residents_with_baseline_route")
    return {
        "component": "road_criticality_0_100",
        "value_0_100": 100.0 * share,
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "definition": frame.definitions["road_criticality_0_100"],
        "inputs": {"residents_losing_all_routes": losing, "residents_with_baseline_route": connected},
        "share_losing_all_routes": share,
    }


def vulnerability_context(
    frame: PlanningFrame,
    *,
    children_0_14: float,
    older_60_plus: float,
    residents: float,
) -> dict[str, Any]:
    """Vulnerability: 100 x clip((dependent share - lower anchor) / (upper anchor - lower anchor), 0, 1).

    The anchors are the national P10 and P90 of protocol v1b; the value on the
    P5 and P95 anchors is returned beside it as the anchor sensitivity.

    Raises:
        NormalisationError: for a count that is not one finite number, the count
            errors :func:`dependent_share` refuses, or a frame not read from the
            files in force.
    """

    hashes = protocol_hashes(frame)
    children = _count(children_0_14, "children_0_14")
    older = _count(older_60_plus, "older_60_plus")
    total = _count(residents, "residents")
    share = dependent_share(children, older, total)
    anchors = frame.vulnerability_anchors
    lower, upper = frame.vulnerability_bounds
    sensitivity_lower, sensitivity_upper = frame.vulnerability_sensitivity_bounds
    return {
        "component": "vulnerability_context_0_100",
        "value_0_100": _between(share, anchors[lower], anchors[upper]),
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "definition": frame.definitions["vulnerability_context_0_100"],
        "inputs": {"children_0_14": children, "older_60_plus": older, "residents": total},
        "dependent_share": share,
        "anchors": {"lower": lower, "lower_value": anchors[lower], "upper": upper, "upper_value": anchors[upper]},
        "anchor_sensitivity": {
            "lower": sensitivity_lower,
            "lower_value": anchors[sensitivity_lower],
            "upper": sensitivity_upper,
            "upper_value": anchors[sensitivity_upper],
            "value_0_100": _between(share, anchors[sensitivity_lower], anchors[sensitivity_upper]),
        },
        "anchor_version": ANCHOR_VERSION,
        "anchor_receipt_sha256": frame.vulnerability_anchor_receipt_sha256,
        "caveat": frame.vulnerability_caveat,
    }


COMPONENT_FUNCTIONS = MappingProxyType({
    "flood_likelihood_0_100": flood_likelihood,
    "exposure_0_100": exposure,
    "access_gap_0_100": access_gap,
    "road_criticality_0_100": road_criticality,
    "vulnerability_context_0_100": vulnerability_context,
})


# ---------------------------------------------------------------------------
# Guardrail GR2 (no batch scaling) and the leave-one-component-out weights
# ---------------------------------------------------------------------------


def _components_to_check(components: Any) -> tuple[str, ...]:
    """Return the components a GR2 check covers, in frame order; they must be named once each."""

    if isinstance(components, (str, bytes, Mapping)):
        raise NormalisationError("components must be a sequence of FPPS component names")
    try:
        names = [str(name) for name in components]
    except TypeError as error:
        raise NormalisationError("components must be a sequence of FPPS component names") from error
    if not names or len(set(names)) != len(names) or not set(names) <= set(SCORE_COMPONENTS):
        raise NormalisationError(f"components must name, once each, one or more of {list(SCORE_COMPONENTS)}")
    return tuple(name for name in SCORE_COMPONENTS if name in names)


def reject_batch_scaled_components(
    frame: PlanningFrame,
    rows: Iterable[Mapping[str, Any]],
    *,
    components: Sequence[str] = SCORE_COMPONENTS,
) -> dict[str, Any]:
    """Refuse rows whose components are not the absolute frame v1 records (guardrail GR2).

    Each row carries ``unit_id``, ``normalisation_version`` and ``components``:
    the records the component functions return, for exactly the components
    named in ``components``. Every record is recomputed from the inputs it
    echoes. A value that depends on the other rows of a batch (scaled by the
    batch maximum, for example) cannot be reproduced that way and is refused.
    So is a record that differs from the recomputed one in any other field
    (another anchor, another version, other protocol hashes), a row that
    declares another frame, and the anchor versions of the GeoAI runner on a
    row or inside a record.

    The value comparison uses the fixed float guard ``VERIFY_TOLERANCE``; the
    caller cannot widen it. Every other field must be equal.

    Args:
        frame: Frame v1, from :func:`load_planning_frame`.
        rows: The rows to check.
        components: The components every row carries. The default is all five;
            a case that computes fewer (protocol v1a case SE2-dist: flood
            likelihood and exposure only) names those.

    Returns:
        A short record of what was checked.

    Raises:
        BatchScalingError: for a row that is not on frame v1 or whose record differs.
        NormalisationError: for an empty batch, an unknown component name,
            echoed inputs the frame refuses, or a frame not read from the files in force.
    """

    hashes = protocol_hashes(frame)
    names = _components_to_check(components)
    checked: list[dict[str, Any]] = []
    other_findings: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise BatchScalingError("guardrail GR2: a row maps unit_id, normalisation_version and components")
        unit_id = row.get("unit_id")
        if row.get("normalisation_version") != frame.version:
            raise BatchScalingError(f"guardrail GR2: unit {unit_id!r} does not declare {frame.version}")
        foreign = [field for field in GEOAI_RUNNER_ANCHOR_FIELDS if field in row]
        if foreign:
            raise BatchScalingError(
                f"guardrail GR2: unit {unit_id!r} carries {foreign}, the anchor versions of the GeoAI runner"
            )
        records = row.get("components")
        if not isinstance(records, Mapping) or set(records) != set(names):
            raise BatchScalingError(f"guardrail GR2: unit {unit_id!r} does not carry exactly the records {list(names)}")
        values: dict[str, tuple[float, float]] = {}
        for name in names:
            record = records[name]
            where = f"{name} of unit {unit_id!r}"
            if not isinstance(record, Mapping):
                raise BatchScalingError(f"guardrail GR2: {where} does not echo the inputs of frame v1")
            foreign = [field for field in GEOAI_RUNNER_ANCHOR_FIELDS if field in record]
            if foreign:
                raise BatchScalingError(
                    f"guardrail GR2: {where} carries {foreign}, the anchor versions of the GeoAI runner"
                )
            try:
                absolute = COMPONENT_FUNCTIONS[name](frame, **record["inputs"])
                supplied = record[VALUE_FIELD]
            except (KeyError, TypeError) as error:
                raise BatchScalingError(f"guardrail GR2: {where} does not echo the inputs of frame v1") from error
            values[name] = (_count(supplied, where), absolute[VALUE_FIELD])
            fields = sorted({*record, *absolute} - {VALUE_FIELD})
            differing = [field for field in fields if record.get(field, _ABSENT) != absolute.get(field, _ABSENT)]
            if differing:
                other_findings.append(f"{where}: {differing}")
        checked.append({"unit_id": unit_id, "values": values})
    if not checked:
        raise NormalisationError("there is no row to check")
    for name in names:
        supplied_values = [row["values"][name][0] for row in checked]
        absolute_values = [row["values"][name][1] for row in checked]
        differing_units = [
            row["unit_id"]
            for row, supplied, absolute in zip(checked, supplied_values, absolute_values)
            if abs(supplied - absolute) > VERIFY_TOLERANCE
        ]
        if not differing_units:
            continue
        finding = "is not the frame v1 value of the inputs it echoes"
        top = max(absolute_values)
        if top > 0:
            rescaled = [100.0 * absolute / top for absolute in absolute_values]
            if all(abs(supplied - scaled) <= VERIFY_TOLERANCE for supplied, scaled in zip(supplied_values, rescaled)):
                finding = "is the frame v1 value divided by the batch maximum (max-normalisation)"
        raise BatchScalingError(f"guardrail GR2: {name} {finding} for unit(s) {differing_units}")
    if other_findings:
        raise BatchScalingError(
            "guardrail GR2: a record is not the frame v1 record of the inputs it echoes; "
            f"fields that differ: {'; '.join(other_findings)}"
        )
    return {
        "guardrail": GUARDRAIL_GR2,
        "result": "PASS",
        "normalisation_version": frame.version,
        "protocol_sha256": hashes,
        "components": list(names),
        "rows_checked": len(checked),
        "components_checked": len(checked) * len(names),
        "tolerance": VERIFY_TOLERANCE,
        "fields_compared": "every field of every record; value_0_100 within the tolerance, the others exactly",
    }


def leave_one_component_out_weights(weights: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """Return, for each component, the weights with that component at 0 and the other four renormalised.

    Protocol v1a, ``scoring_frame.leave_one_component_out`` (drafter reading
    DR-A02): the renormalisation is that of ``scoring.validate_weights``, so the
    four remaining weights keep their proportions and sum to 1. The FPPS and the
    class under each set of weights are computed by the scoring step, not here.

    Args:
        weights: The weights of the row: the frame's default or a weight preset.

    Raises:
        NormalisationError: when the weights are not valid FPPS weights (a
            weight that is not a finite number included), or dropping a
            component leaves no weight at all.
    """

    try:
        if not all(math.isfinite(float(value)) for value in weights.values()):
            raise ValueError("every weight must be a finite number")
        base = validate_weights(weights)
        return {dropped: validate_weights({**base, dropped: 0.0}) for dropped in SCORE_COMPONENTS}
    except (ValueError, TypeError, AttributeError) as error:
        raise NormalisationError(f"leave-one-component-out needs valid FPPS weights: {error}") from error
