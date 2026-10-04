"""Confidence rule v1 (protocol v1a ``confidence_rule_v1``; plan 3.3 and 5 item 9, task E2).

The rule gives one unit in one lane a confidence class, from explicit inputs:

* ``high`` requires tier T4, which is locked in this release. It is never assigned.
* ``medium`` requires all eight conditions C1 to C8.
* ``low`` otherwise.

Every row records ``pass``, ``fail``, ``by_construction`` or
``by_scenario_declaration`` for each condition and lists the failed ones; those
condition IDs are the reason codes of a low class.

Scenario rows (tier T1, lanes SCN and SCN-ENV) follow drafter reading DR-A07,
which the owners confirmed at signing: scenario confidence is derived. C1 is
judged on the base flood input of the scenario (``by_scenario_declaration`` for
an agency product used as provided; a fail for an own T2 candidate that does not
pass the T2 skill condition), C2 is replaced by the scenario declaration, and C3
to C8 are evaluated as for an observed row. The row carries
``confidence_kind: scenario`` and is never counted as observed confidence.

Guardrail GR1 (drafter reading DR-A09, confirmed): a unit with fewer than 100
residents has no binding class, no would-be class and no v2 class. Its
confidence is still recorded as low with C6 among the failed conditions, and its
reason code is ``insufficient_denominator``, ahead of ``low_confidence``.

Rights are not an input (they drive ``publication_eligibility``), and no
ensemble output is used. Every threshold is read from the protocol file
(:func:`load_confidence_rule`). The functions are pure: they read no flood
layer, compute no FPPS and assign no A-E class. A missing measurement is
recorded as ``fail``: medium needs every condition shown. A confidence class is
planning guidance; it is not a validation of a flood map and not an official warning.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Real
from pathlib import Path
from typing import Any

from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.normalisation import read_protocol_in_force
from floodguard.scoring import SCORE_COMPONENTS

CONFIDENCE_RULE_VERSION = "confidence_rule_v1"
CONDITION_IDS: tuple[str, ...] = (
    "C1_tier",
    "C2_recency",
    "C3_coverage",
    "C4_input_uncertainty",
    "C5_components",
    "C6_residents",
    "C7_baseline_no_route",
    "C8_hospital",
)
PASS = "pass"
FAIL = "fail"
BY_CONSTRUCTION = "by_construction"
BY_SCENARIO_DECLARATION = "by_scenario_declaration"
BASIS_VALUES: tuple[str, ...] = (PASS, FAIL, BY_CONSTRUCTION, BY_SCENARIO_DECLARATION)

OBSERVED_LANE = "OBS"
SCENARIO_LANES: tuple[str, ...] = ("SCN", "SCN-ENV")
SEASON_ENVELOPE_LANE = "SCN-ENV"
ENGINE_LANE = "ENG"
# Protocol v1a evidence_tier_model.tiers: the lane of each tier.
TIER_LANES: dict[str, str | None] = {"T0": "ENG", "T1": "SCN", "T2": "OBS", "T3": "OBS", "T4": None}
DERIVED_TIERS: tuple[str, ...] = ("T1", "T2", "T3")

SCENARIO_BASE_AGENCY = "agency_product_as_provided"
SCENARIO_BASE_OWN_CANDIDATE = "own_t2_candidate"
SCENARIO_BASES: tuple[str, ...] = (SCENARIO_BASE_AGENCY, SCENARIO_BASE_OWN_CANDIDATE)

COMPONENT_COMPUTED = "computed"
COMPONENT_STATUSES: tuple[str, ...] = (COMPONENT_COMPUTED, "assumed", "not_computed")

KIND_OBSERVED = "observed"
KIND_SCENARIO = "scenario"
REASON_LOW_CONFIDENCE = "low_confidence"
REASON_INSUFFICIENT_DENOMINATOR = "insufficient_denominator"
GUARDRAIL_GR1 = "GR1_minimum_denominators"
# Drafter readings this module implements; each must be confirmed in the signed file.
REQUIRED_READINGS: tuple[str, ...] = ("DR-A07", "DR-A09")

SKILL_DECLARED_UNABLE = "declared_unable_to_meet"
SKILL_NOT_EVALUATED = "not_evaluated_by_the_rule"
SKILL_EVALUATED = "evaluated"


class ConfidenceError(ValueError):
    """Raised when confidence inputs or the protocol break the rule v1 contract."""


@dataclass(frozen=True)
class ConfidenceRule:
    """The thresholds of confidence rule v1. Every value comes from protocol v1a."""

    version: str
    recency_window_days: float
    unit_valid_coverage_min: float
    exposure_plus_minus_one_pixel_max_points: float
    t2_abstention_fraction_max: float
    unit_residents_min: float
    baseline_vehicle_no_route_share_max: float
    hospitals_reachable_at_baseline_min: float
    skill_geoid_held_out_test_iou_min: float
    skill_abstention_fraction_max: float
    skill_unit_coverage_min: float
    skill_recency_window_days: float
    skill_declared_unable_to_meet: tuple[str, ...]
    skill_evaluated_by_the_rule: tuple[str, ...]
    gr1_unit_residents_min_for_class: float
    protocol_sha256: str | None


@dataclass(frozen=True, kw_only=True)
class ConfidenceInputs:
    """The explicit inputs of rule v1 for one unit in one lane.

    Every field has to be given; ``None`` says that a measurement does not
    exist, and the condition that needs it then fails. No field holds a rights
    level or an ensemble output: rule v1 uses neither.

    Attributes:
        unit_id: The unit the row describes.
        lane: ``OBS``, ``SCN`` or ``SCN-ENV``.
        tier: ``T2`` or ``T3`` in lane OBS; ``T1`` in the scenario lanes.
        flood_input: The flood input, or for a scenario row its base flood
            input, named as protocol v1a names it.
        scenario_base: For a T1 row, ``agency_product_as_provided`` or
            ``own_t2_candidate``; ``None`` for an observed row.
        acquisition_date: The calendar date of the acquisition, or ``None`` for
            an input with no single date (the season-window layer).
        case_reference_date: The reference date of the case, or of the base
            case of a scenario row.
        unit_valid_coverage: The unit's valid coverage inside the product
            footprint or analysis extent, 0-1.
        coverage_by_construction: True when the analysis extent of an agency
            product covers the unit by construction (protocol: product 4009 in
            Mae Sai). The condition is then reported as ``by_construction``.
        exposure_plus_one_pixel_0_100: Exposure with the flood input grown by one pixel.
        exposure_minus_one_pixel_0_100: Exposure with the flood input shrunk by one pixel.
        t2_abstention_fraction: The abstention fraction of an own T2 candidate.
        t2_geoid_held_out_test_iou: The GEOID held-out test IoU of an own T2
            candidate (agreement with a same-pass CEMS map, not independent accuracy).
        component_status: For each of the five FPPS components, ``computed``,
            ``assumed`` or ``not_computed``.
        unit_residents: The residents of the unit.
        baseline_vehicle_no_route_share: The baseline vehicle connected-no-route share, 0-1.
        hospitals_reachable_at_baseline: The number of hospitals reachable at baseline.
    """

    unit_id: str
    lane: str
    tier: str
    flood_input: str
    scenario_base: str | None
    acquisition_date: date | None
    case_reference_date: date | None
    unit_valid_coverage: float | None
    coverage_by_construction: bool
    exposure_plus_one_pixel_0_100: float | None
    exposure_minus_one_pixel_0_100: float | None
    t2_abstention_fraction: float | None
    t2_geoid_held_out_test_iou: float | None
    component_status: Mapping[str, str]
    unit_residents: float
    baseline_vehicle_no_route_share: float | None
    hospitals_reachable_at_baseline: int | None


# ---------------------------------------------------------------------------
# The rule, read from the protocol
# ---------------------------------------------------------------------------


def load_confidence_rule(v1a_path: Path | str, receipts_path: Path | str) -> ConfidenceRule:
    """Read rule v1 from protocol v1a, which must be in force (see ``read_protocol_in_force``).

    Raises:
        ConfidenceError: when the file does not hold rule v1 as this module implements it.
        floodguard.normalisation.NormalisationError: when the file is not in force.
    """

    v1a, v1a_sha256 = read_protocol_in_force("v1a", v1a_path, receipts_path)
    return confidence_rule_from_protocol(v1a, protocol_sha256=v1a_sha256)


def confidence_rule_from_protocol(v1a: Mapping[str, Any], *, protocol_sha256: str | None = None) -> ConfidenceRule:
    """Build rule v1 from the parsed protocol v1a.

    Raises:
        ConfidenceError: when the file is not signed, declares another rule
            version, another condition list or vocabulary, uses rights or an
            ensemble output, leaves a required drafter reading unconfirmed, or
            lacks a threshold.
    """

    try:
        return _rule(v1a, protocol_sha256)
    except ConfidenceError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ConfidenceError(f"protocol v1a does not hold confidence rule v1: {error!r}") from error


def _rule(v1a: Mapping[str, Any], protocol_sha256: str | None) -> ConfidenceRule:
    """Read every threshold; a missing key is turned into ConfidenceError by the caller."""

    if v1a["status"] != "signed":
        raise ConfidenceError("confidence rule v1 is read from the signed protocol file only")
    section = v1a["confidence_rule_v1"]
    if section["version"] != CONFIDENCE_RULE_VERSION:
        raise ConfidenceError(f"this module implements {CONFIDENCE_RULE_VERSION}, not {section['version']!r}")
    conditions = {row["id"]: row for row in section["medium_requires_all"]}
    if tuple(conditions) != CONDITION_IDS:
        raise ConfidenceError("the protocol does not list the eight conditions C1 to C8 in order")
    if section["uses_ensemble_output"] is not False or section["rights_are_an_input"] is not False:
        raise ConfidenceError("this module implements a rule that uses no ensemble output and no rights input")
    if tuple(section["vocabulary"]) != tuple(VALID_CONFIDENCE_CLASSES):
        raise ConfidenceError("the confidence vocabulary of the protocol is not the one the scorer accepts")
    statuses = {row["id"]: row["status"] for row in v1a["drafter_readings"]}
    unconfirmed = [reading for reading in REQUIRED_READINGS if statuses.get(reading) != "confirmed"]
    if unconfirmed:
        raise ConfidenceError(f"drafter reading(s) {unconfirmed} are not confirmed in the protocol")
    tiers = {row["tier"]: row["lane"] for row in v1a["evidence_tier_model"]["tiers"]}
    lanes = {row["lane"] for row in v1a["evidence_tier_model"]["lanes"]}
    if tiers != TIER_LANES or lanes != {OBSERVED_LANE, ENGINE_LANE, *SCENARIO_LANES}:
        raise ConfidenceError("the tiers and lanes of the protocol are not the ones this module implements")
    class_rule = v1a["class_rules"]["v1"]
    declared_codes = {*class_rule["reason_codes"], *class_rule["added_reason_code"]}
    if not {REASON_LOW_CONFIDENCE, REASON_INSUFFICIENT_DENOMINATOR} <= declared_codes:
        raise ConfidenceError("the protocol does not declare the reason codes this module records")

    skill = v1a["t2_skill_bar"]
    guardrails = {row["id"]: row for row in v1a["guardrails"]}
    input_uncertainty = conditions["C4_input_uncertainty"]["threshold"]
    rule = ConfidenceRule(
        version=CONFIDENCE_RULE_VERSION,
        recency_window_days=_threshold(conditions["C2_recency"]["threshold"]["recency_window_days"]),
        unit_valid_coverage_min=_threshold(conditions["C3_coverage"]["threshold"]["unit_valid_coverage_min"]),
        exposure_plus_minus_one_pixel_max_points=_threshold(
            input_uncertainty["exposure_plus_minus_one_pixel_max_points"]
        ),
        t2_abstention_fraction_max=_threshold(input_uncertainty["t2_abstention_fraction_max"]),
        unit_residents_min=_threshold(conditions["C6_residents"]["threshold"]["unit_residents_min"]),
        baseline_vehicle_no_route_share_max=_threshold(
            conditions["C7_baseline_no_route"]["threshold"]["baseline_vehicle_no_route_share_max"]
        ),
        hospitals_reachable_at_baseline_min=_threshold(
            conditions["C8_hospital"]["threshold"]["hospitals_reachable_at_baseline_min"]
        ),
        skill_geoid_held_out_test_iou_min=_threshold(skill["conditions"]["geoid_held_out_test_iou_min"]),
        skill_abstention_fraction_max=_threshold(skill["conditions"]["mae_sai_abstention_fraction_max"]),
        skill_unit_coverage_min=_threshold(skill["conditions"]["mae_sai_unit_coverage_min"]),
        skill_recency_window_days=_threshold(skill["conditions"]["recency_window_days"]),
        skill_declared_unable_to_meet=tuple(str(name) for name in skill["declared_unable_to_meet"]),
        skill_evaluated_by_the_rule=tuple(str(name) for name in skill["evaluated_by_the_rule"]),
        gr1_unit_residents_min_for_class=_threshold(
            guardrails[GUARDRAIL_GR1]["parameters"]["unit_residents_min_for_class"]
        ),
        protocol_sha256=protocol_sha256,
    )
    if rule.gr1_unit_residents_min_for_class != rule.unit_residents_min:
        raise ConfidenceError(
            "guardrail GR1 and condition C6 must use one resident threshold: "
            "the protocol records C6 as failed for every unit that GR1 covers"
        )
    return rule


def _threshold(value: Any) -> float:
    """Return a declared threshold, which must be a finite number that is not negative."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ConfidenceError("a threshold of rule v1 is not a number in the protocol")
    if not math.isfinite(value) or value < 0:
        raise ConfidenceError("a threshold of rule v1 must be finite and not negative")
    return float(value)


# ---------------------------------------------------------------------------
# Input checks and small comparisons
# ---------------------------------------------------------------------------


def _measure(value: Any, name: str, upper: float) -> float | None:
    """Return a measurement between 0 and ``upper``, or None when it was not measured."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ConfidenceError(f"{name} must be a number or None")
    if not math.isfinite(value) or value < 0 or value > upper:
        raise ConfidenceError(f"{name} must lie between 0 and {upper:g}")
    return float(value)


def _calendar_date(value: Any, name: str) -> date | None:
    """Return a calendar date or None; a datetime is refused so the day count stays explicit."""

    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ConfidenceError(f"{name} must be a calendar date (datetime.date) or None")
    return value


def _at_least(value: float | None, minimum: float) -> bool:
    """Say whether a measurement reaches a minimum; a missing measurement does not."""

    if value is None:
        return False
    return value >= minimum


def _at_most(value: float | None, maximum: float) -> bool:
    """Say whether a measurement stays within a maximum; a missing measurement does not."""

    if value is None:
        return False
    return value <= maximum


def _basis(met: bool) -> str:
    """Return the basis value of an evaluated condition."""

    if met:
        return PASS
    return FAIL


def recency_days(acquisition_date: date | None, case_reference_date: date | None) -> int | None:
    """Return the whole days between an acquisition date and a case reference date.

    The dates are calendar dates the caller supplies; the result is None when
    either is missing (an input with no single acquisition date has none).
    """

    if acquisition_date is None or case_reference_date is None:
        return None
    return abs((acquisition_date - case_reference_date).days)


def _own_candidate(inputs: ConfidenceInputs) -> bool:
    """Check lane, tier and scenario base; say whether the (base) flood input is an own T2 candidate."""

    if inputs.lane == ENGINE_LANE or inputs.tier == "T0":
        raise ConfidenceError("engine rows (tier T0, lane ENG) declare their confidence per row; rule v1 derives none")
    if inputs.tier == "T4":
        raise ConfidenceError("tier T4 is locked in this release: high confidence is never assigned")
    if inputs.tier not in DERIVED_TIERS or inputs.lane not in (OBSERVED_LANE, *SCENARIO_LANES):
        raise ConfidenceError(f"unknown lane {inputs.lane!r} or tier {inputs.tier!r}")
    if (inputs.tier == "T1") != (inputs.lane in SCENARIO_LANES):
        raise ConfidenceError("tier T1 belongs to the lanes SCN and SCN-ENV; tiers T2 and T3 belong to lane OBS")
    if inputs.tier != "T1":
        if inputs.scenario_base is not None:
            raise ConfidenceError("scenario_base is given for tier T1 rows only")
        return inputs.tier == "T2"
    if inputs.scenario_base not in SCENARIO_BASES:
        raise ConfidenceError(f"a tier T1 row names its base flood input as one of {SCENARIO_BASES}")
    if inputs.lane == SEASON_ENVELOPE_LANE and inputs.scenario_base != SCENARIO_BASE_AGENCY:
        raise ConfidenceError("lane SCN-ENV is the agency season-envelope layer, used as provided")
    return inputs.scenario_base == SCENARIO_BASE_OWN_CANDIDATE


def _component_statuses(component_status: Any) -> dict[str, str]:
    """Check that each of the five components is computed, assumed or not computed."""

    if not isinstance(component_status, Mapping) or set(component_status) != set(SCORE_COMPONENTS):
        raise ConfidenceError("component_status must name exactly the five FPPS components")
    statuses = {name: component_status[name] for name in SCORE_COMPONENTS}
    unknown = [name for name, status in statuses.items() if status not in COMPONENT_STATUSES]
    if unknown:
        raise ConfidenceError(f"component_status of {unknown} must be one of {COMPONENT_STATUSES}")
    return statuses


# ---------------------------------------------------------------------------
# The T2 skill condition and rule v1
# ---------------------------------------------------------------------------


def t2_skill_condition(
    rule: ConfidenceRule,
    *,
    flood_input: str,
    geoid_held_out_test_iou: float | None,
    abstention_fraction: float | None,
    unit_valid_coverage: float | None,
    acquisition_date: date | None,
    case_reference_date: date | None,
) -> dict[str, Any]:
    """Evaluate the T2 skill condition of protocol v1a (``t2_skill_bar``).

    A T2 input is low confidence unless all four conditions pass. An input the
    protocol declares unable to meet the condition does not pass whatever its
    numbers are, and neither does an input the protocol does not list as
    evaluated by the rule. The GEOID figure is agreement with a same-pass CEMS
    map; it is not independent accuracy.

    Returns:
        ``passes``, the ``status`` of the input, and pass or fail for each of
        the four conditions with the measurements and thresholds used.
    """

    iou = _measure(geoid_held_out_test_iou, "t2_geoid_held_out_test_iou", 1.0)
    abstention = _measure(abstention_fraction, "t2_abstention_fraction", 1.0)
    coverage = _measure(unit_valid_coverage, "unit_valid_coverage", 1.0)
    days = recency_days(
        _calendar_date(acquisition_date, "acquisition_date"),
        _calendar_date(case_reference_date, "case_reference_date"),
    )
    conditions = {
        "geoid_held_out_test_iou_min": _basis(_at_least(iou, rule.skill_geoid_held_out_test_iou_min)),
        "mae_sai_abstention_fraction_max": _basis(_at_most(abstention, rule.skill_abstention_fraction_max)),
        "mae_sai_unit_coverage_min": _basis(_at_least(coverage, rule.skill_unit_coverage_min)),
        "recency_window_days": _basis(_at_most(days, rule.skill_recency_window_days)),
    }
    if flood_input in rule.skill_declared_unable_to_meet:
        status = SKILL_DECLARED_UNABLE
    elif flood_input not in rule.skill_evaluated_by_the_rule:
        status = SKILL_NOT_EVALUATED
    else:
        status = SKILL_EVALUATED
    failed = [name for name, value in conditions.items() if value == FAIL]
    return {
        "flood_input": flood_input,
        "status": status,
        "passes": status == SKILL_EVALUATED and not failed,
        "conditions": conditions,
        "failed_conditions": failed,
        "measurements": {
            "geoid_held_out_test_iou": iou,
            "abstention_fraction": abstention,
            "unit_valid_coverage": coverage,
            "recency_days": days,
        },
        "thresholds": {
            "geoid_held_out_test_iou_min": rule.skill_geoid_held_out_test_iou_min,
            "mae_sai_abstention_fraction_max": rule.skill_abstention_fraction_max,
            "mae_sai_unit_coverage_min": rule.skill_unit_coverage_min,
            "recency_window_days": rule.skill_recency_window_days,
        },
        "metric_wording": "agreement with a same-pass CEMS map, not independent accuracy",
    }


def derive_confidence(inputs: ConfidenceInputs, rule: ConfidenceRule) -> dict[str, Any]:
    """Apply confidence rule v1 to one unit in one lane.

    Args:
        inputs: The explicit inputs of the row.
        rule: Rule v1, from :func:`load_confidence_rule`.

    Returns:
        ``confidence_class`` (``medium`` or ``low``; never ``high``),
        ``confidence_kind`` (``observed`` or ``scenario``), the ``basis`` of
        each condition, ``failed_conditions``, the ``reason_code`` the class
        step must carry, the guardrail GR1 record, and the measurements and
        thresholds used.

    Raises:
        ConfidenceError: for an engine row or tier T4, a lane and tier that do
            not belong together, or a measurement outside its range.
    """

    if not isinstance(inputs.unit_id, str) or not inputs.unit_id or not isinstance(inputs.flood_input, str):
        raise ConfidenceError("unit_id and flood_input must be text, and unit_id must not be empty")
    own_candidate = _own_candidate(inputs)
    scenario = inputs.tier == "T1"
    coverage = _measure(inputs.unit_valid_coverage, "unit_valid_coverage", 1.0)
    plus = _measure(inputs.exposure_plus_one_pixel_0_100, "exposure_plus_one_pixel_0_100", 100.0)
    minus = _measure(inputs.exposure_minus_one_pixel_0_100, "exposure_minus_one_pixel_0_100", 100.0)
    abstention = _measure(inputs.t2_abstention_fraction, "t2_abstention_fraction", 1.0)
    iou = _measure(inputs.t2_geoid_held_out_test_iou, "t2_geoid_held_out_test_iou", 1.0)
    no_route = _measure(inputs.baseline_vehicle_no_route_share, "baseline_vehicle_no_route_share", 1.0)
    hospitals = _measure(inputs.hospitals_reachable_at_baseline, "hospitals_reachable_at_baseline", math.inf)
    residents = _measure(inputs.unit_residents, "unit_residents", math.inf)
    acquisition = _calendar_date(inputs.acquisition_date, "acquisition_date")
    reference = _calendar_date(inputs.case_reference_date, "case_reference_date")
    statuses = _component_statuses(inputs.component_status)
    if residents is None:
        raise ConfidenceError("unit_residents is required: guardrail GR1 and condition C6 both need it")
    if hospitals is not None and hospitals != int(hospitals):
        raise ConfidenceError("hospitals_reachable_at_baseline must be a whole number or None")
    if not isinstance(inputs.coverage_by_construction, bool):
        raise ConfidenceError("coverage_by_construction must be True or False")
    if not own_candidate and (abstention is not None or iou is not None):
        raise ConfidenceError("the T2 abstention fraction and GEOID IoU belong to an own T2 candidate only")
    if inputs.coverage_by_construction and own_candidate:
        raise ConfidenceError("coverage by construction is stated for an agency product, not for an own candidate")
    if inputs.coverage_by_construction and coverage is not None and coverage < rule.unit_valid_coverage_min:
        raise ConfidenceError("coverage is declared by construction, but the measured coverage is below the minimum")

    skill = None
    if own_candidate:
        skill = t2_skill_condition(
            rule,
            flood_input=inputs.flood_input,
            geoid_held_out_test_iou=iou,
            abstention_fraction=abstention,
            unit_valid_coverage=coverage,
            acquisition_date=acquisition,
            case_reference_date=reference,
        )

    basis: dict[str, str] = {}
    if inputs.tier == "T3":
        basis["C1_tier"] = PASS
    elif skill is None:
        basis["C1_tier"] = BY_SCENARIO_DECLARATION
    else:
        basis["C1_tier"] = _basis(skill["passes"])

    days = recency_days(acquisition, reference)
    if scenario:
        basis["C2_recency"] = BY_SCENARIO_DECLARATION
    else:
        basis["C2_recency"] = _basis(_at_most(days, rule.recency_window_days))

    if inputs.coverage_by_construction:
        basis["C3_coverage"] = BY_CONSTRUCTION
    else:
        basis["C3_coverage"] = _basis(_at_least(coverage, rule.unit_valid_coverage_min))

    difference = None
    if plus is not None and minus is not None:
        difference = abs(plus - minus)
    input_uncertainty = [_at_most(difference, rule.exposure_plus_minus_one_pixel_max_points)]
    if own_candidate:
        input_uncertainty.append(_at_most(abstention, rule.t2_abstention_fraction_max))
    basis["C4_input_uncertainty"] = _basis(all(input_uncertainty))

    basis["C5_components"] = _basis(all(status == COMPONENT_COMPUTED for status in statuses.values()))
    basis["C6_residents"] = _basis(residents >= rule.unit_residents_min)
    basis["C7_baseline_no_route"] = _basis(_at_most(no_route, rule.baseline_vehicle_no_route_share_max))
    basis["C8_hospital"] = _basis(_at_least(hospitals, rule.hospitals_reachable_at_baseline_min))

    failed = [condition for condition in CONDITION_IDS if basis[condition] == FAIL]
    confidence_class = "medium"
    reason_code = None
    if failed:
        confidence_class = "low"
        reason_code = REASON_LOW_CONFIDENCE
    gr1_applies = residents < rule.gr1_unit_residents_min_for_class
    if gr1_applies:
        reason_code = REASON_INSUFFICIENT_DENOMINATOR

    confidence_kind = KIND_OBSERVED
    assumptions = [
        "Derived from the listed measurements only. No ensemble output and no rights level is read.",
        "A condition whose measurement is missing is recorded as fail: medium needs every condition shown.",
        "High requires tier T4, which is locked in this release, so high is never assigned.",
    ]
    if scenario:
        confidence_kind = KIND_SCENARIO
        assumptions.append(
            "Scenario confidence (drafter reading DR-A07, confirmed at signing): C1 is judged on the base flood "
            "input and C2 is replaced by the scenario declaration. It is never shown or counted as observed confidence."
        )
    if gr1_applies:
        assumptions.append(
            "Guardrail GR1: fewer residents than the minimum, so the unit gets no binding class, no would-be class "
            "and no v2 class (insufficient_denominator). Its confidence is still recorded as low."
        )
    return {
        "unit_id": inputs.unit_id,
        "lane": inputs.lane,
        "tier": inputs.tier,
        "flood_input": inputs.flood_input,
        "scenario_base": inputs.scenario_base,
        "confidence_rule_version": rule.version,
        "confidence_class": confidence_class,
        "confidence_kind": confidence_kind,
        "basis": basis,
        "failed_conditions": failed,
        "reason_code": reason_code,
        "guardrail_gr1": {
            "id": GUARDRAIL_GR1,
            "applies": gr1_applies,
            "unit_residents_min_for_class": rule.gr1_unit_residents_min_for_class,
            "no_binding_class": gr1_applies,
            "no_would_be_class": gr1_applies,
            "no_v2_class": gr1_applies,
        },
        "t2_skill_condition": skill,
        "measurements": {
            "recency_days": days,
            "acquisition_date": _iso(acquisition),
            "case_reference_date": _iso(reference),
            "unit_valid_coverage": coverage,
            "coverage_by_construction": inputs.coverage_by_construction,
            "exposure_plus_one_pixel_0_100": plus,
            "exposure_minus_one_pixel_0_100": minus,
            "exposure_plus_minus_one_pixel_points": difference,
            "t2_abstention_fraction": abstention,
            "component_status": statuses,
            "unit_residents": residents,
            "baseline_vehicle_no_route_share": no_route,
            "hospitals_reachable_at_baseline": hospitals,
        },
        "thresholds": {
            "recency_window_days": rule.recency_window_days,
            "unit_valid_coverage_min": rule.unit_valid_coverage_min,
            "exposure_plus_minus_one_pixel_max_points": rule.exposure_plus_minus_one_pixel_max_points,
            "t2_abstention_fraction_max": rule.t2_abstention_fraction_max,
            "unit_residents_min": rule.unit_residents_min,
            "baseline_vehicle_no_route_share_max": rule.baseline_vehicle_no_route_share_max,
            "hospitals_reachable_at_baseline_min": rule.hospitals_reachable_at_baseline_min,
        },
        "uses_ensemble_output": False,
        "rights_are_an_input": False,
        "protocol_v1a_sha256": rule.protocol_sha256,
        "assumptions": assumptions,
    }


def _iso(value: date | None) -> str | None:
    """Return a date as ISO text, or None."""

    if value is None:
        return None
    return value.isoformat()
