"""Planning assessment overlay: strict validator, loader and writer (plan 7.1, task E11).

The overlay is the file the planning engine writes for one case and every
screen reads: one row per unit, lane, flood input and scenario. Its shape is
``packages/contracts/schemas/planning-assessment-overlay.schema.json``. This
module adds what a JSON schema cannot say, and names every refusal with a code
that the web parser (``apps/web/src/lib/planning-assessment-overlay.ts``) uses
too:

* the invariants of protocol v1a at every tier: not an official warning,
  non-operational, ``accepted_fpps`` and ``accepted_action_class`` null, no
  class above E without medium confidence, high confidence never assigned;
* guardrail GR1 (fewer than 100 residents: no binding class, no would-be class,
  no v2 class, reason ``insufficient_denominator``), judged on one resident
  count per row; GR7 (temporal honesty), with the temporal relation of a row
  derived from the two dates the row echoes; GR8 (the headline-stability slot);
  GR6 (the rights level of an overlay is the minimum across its lineage) and
  GR3 (one flood input, one routing context and one closure rule per row, the
  closure modelled from that flood input);
* the confidence record against itself: every basis value C1 to C8 is
  recomputed from the measurements and thresholds the record echoes;
* the arithmetic the row states about itself, recomputed with
  ``scoring.score_subdistricts``: FPPS, the binding v1 class and its reason
  code, the would-be class (the scorer rerun with confidence medium, never
  binding) and leave-one-component-out; and the v2 axis against the row;
* with a :class:`ProtocolBinding` (the frame, the confidence rule and the case
  portfolio read from the two protocol files in force): every component record
  is the frame v1 record of the inputs it echoes (guardrail GR2), every
  confidence record is what rule v1 derives from the measurements it echoes,
  the hashes are those of the files in force, and a portfolio case carries the
  reference date, lane, tier and flood inputs protocol v1a gives it.

A candidate overlay is refused without a :class:`ProtocolBinding`; only a
fixture (``dataset_mode: fixture_demo``, not a place) is checked without one.

The field shapes of the component and confidence records are those
``normalisation.py`` and ``confidence.py`` return. Nothing here reads a flood
layer or produces a result of its own: the functions check and serialise a
mapping they are given, and the recomputation is only compared with what the
mapping states. An overlay is planning guidance for preparedness and post-event
prioritisation. It is not an official warning, and class E never means safe.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.confidence import (
    BY_CONSTRUCTION,
    BY_SCENARIO_DECLARATION,
    C4_FLOAT_GUARD_POINTS,
    COMPONENT_COMPUTED,
    CONDITION_IDS,
    ENGINE_LANE,
    FAIL,
    OBSERVED_LANE,
    PASS,
    REASON_INSUFFICIENT_DENOMINATOR,
    REASON_LOW_CONFIDENCE,
    SCENARIO_BASE_AGENCY,
    SCENARIO_BASE_OWN_CANDIDATE,
    SCENARIO_LANES,
    SEASON_ENVELOPE_LANE,
    SKILL_EVALUATED,
    ConfidenceError,
    ConfidenceInputs,
    ConfidenceRule,
    derive_confidence,
    load_confidence_rule,
)
from floodguard.normalisation import (
    NormalisationError,
    PlanningFrame,
    frame_record,
    load_planning_frame,
    protocol_hashes,
    read_protocol_in_force,
    reject_batch_scaled_components,
)
from floodguard.rights_basis import PRODUCT_4009_CITATION, RightsBasisError, require_owner_confirmation
from floodguard.scoring import ACTION_REASON_CODES, SCORE_COMPONENTS, score_subdistricts

SCHEMA_VERSION = "1.0"
SCHEMA_ID = "https://floodguard.th/contracts/planning-assessment-overlay.schema.json"
SCHEMA_RELATIVE_PATH = Path("packages/contracts/schemas/planning-assessment-overlay.schema.json")
"""Repository-relative path of the overlay schema."""

TIERS: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4")
LOCKED_TIER = "T4"
ENGINE_TIER = "T0"
SCENARIO_TIER = "T1"
OWN_CANDIDATE_TIER = "T2"
AGENCY_TIER = "T3"
LANES: tuple[str, ...] = (OBSERVED_LANE, *SCENARIO_LANES, ENGINE_LANE)
# Protocol v1a evidence_tier_model.tiers: the lanes a row of each tier may carry. T4 has no lane.
TIER_LANES: dict[str, tuple[str | None, ...]] = {
    "T0": (ENGINE_LANE,),
    "T1": SCENARIO_LANES,
    "T2": (OBSERVED_LANE,),
    "T3": (OBSERVED_LANE,),
    "T4": (None,),
}
SCENARIO_COLUMN = "SCN"
NO_LANE_COLUMN = "no_lane"
LANE_COLUMNS: tuple[str, ...] = (OBSERVED_LANE, SCENARIO_COLUMN, ENGINE_LANE, NO_LANE_COLUMN)
"""The columns a count is reported in (protocol v1a class_coverage_deliverable: OBS / SCN / ENG).

Lane SCN-ENV is part of the SCN column. ``no_lane`` holds the rows of the locked tier T4.
"""
DERIVED_COLUMNS: tuple[str, ...] = (OBSERVED_LANE, SCENARIO_COLUMN)
EVENT_ALIGNED = "event_aligned"
DATED_OTHER = "dated_other"
SEASON_WINDOW = "season_window"
TEMPORAL_RELATIONS: tuple[str, ...] = (EVENT_ALIGNED, DATED_OTHER, SEASON_WINDOW)
ACTION_CLASSES: tuple[str, ...] = ("A", "B", "C", "D", "E")
CLASSES_ABOVE_E: tuple[str, ...] = ("A", "B", "C", "D")
REASON_CODES: tuple[str, ...] = (*ACTION_REASON_CODES, REASON_INSUFFICIENT_DENOMINATOR)
PUBLICATION_LEVELS: tuple[str, ...] = ("local", "pitch", "public")
"""Guardrail GR6, lowest first: the rights level of an overlay is the minimum across its lineage."""
ACCEPTED_FIELDS: tuple[str, ...] = ("accepted_fpps", "accepted_action_class")
KIND_DECLARED = "declared"
KIND_BY_TIER: dict[str, str] = {"T0": KIND_DECLARED, "T1": "scenario", "T2": "observed", "T3": "observed"}
# Protocol v1a class_rules.v1.reason_codes: the reason code of each class above E.
REASON_BY_CLASS: dict[str, str] = {
    "A": "life_safety_exposure",
    "B": "critical_route_access",
    "C": "essential_service_access",
    "D": "resilience",
}
NO_V2_TRIGGER = "no_v2_trigger"
V2_TRIGGER_ORDER: tuple[str, ...] = ("E", "A", "B", "C", "D")
"""Protocol v1a class_rules.v2.evaluation.order (drafter reading DR-A08)."""
V2_FPPS_MIN = 35.0
V2_EXPOSURE_FLOOR_FOR_NON_E = 10.0
"""Protocol v1a class_rules.v2.parameters fpps_min and exposure_floor_for_non_e."""
HEADLINE_NOT_EVALUATED = "not_evaluated"
HEADLINE_ELIGIBLE = "headline_eligible"
HEADLINE_UNSTABLE = "unstable_verify"
GUARDRAIL_GR8 = "GR8_headline_stability"
FIXTURE_MODE = "fixture_demo"
FIXTURE_KIND = "fixture"
PORTFOLIO_KIND = "portfolio_case"
FIXTURE_LABEL = "not a place"
FLOOD_INPUT_ROLE = "flood_input"
ROUTING_CONTEXT_ROLE = "routing_context"
CLOSURE_BASIS_PREFIX = "modelled_from_"
"""Protocol v1b closure_rule_v1: every output carries ``closure_basis: modelled_from_<input>``."""
PRODUCT_4009_SOURCE = "unosat_product_4009"
"""The value of ``inputs[].source_product`` that declares UNOSAT/GISTDA product 4009."""
PRODUCT_4009_LICENCE = "CC BY-SA 4.0"
PRODUCT_4009_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
"""Protocol v1a wording.product_4009_credit; the rights record carries the same text."""
PRODUCT_4009_EVENT_CODE = "FL20240912THA"
PRODUCT_4009_LAYER_NAMES: tuple[str, ...] = (
    "CHIANGRAI_20240801_20241012_AccumulatedFlood",
    "CHIANGRAI_20241022_FloodExtent",
)
"""Protocol v1a date_rule.product_4009: the accumulated layer and the 22 Oct layer."""
# Text that names product 4009 whatever the spelling: the citation the rights module knows, the bare product
# number ("the 4009 22 Oct layer"), the event code and the two layer names of protocol v1a.
_PRODUCT_4009_TEXT = re.compile(
    "|".join((
        PRODUCT_4009_CITATION.pattern,
        r"(?:^|[^0-9A-Za-z])4009(?![0-9])",
        re.escape(PRODUCT_4009_EVENT_CODE),
        *(re.escape(name) for name in PRODUCT_4009_LAYER_NAMES),
    )),
    re.IGNORECASE,
)
CASES_WITHOUT_CLASS: tuple[str, ...] = ("SE2-dist",)
"""Protocol v1a case SE2-dist: flood likelihood and exposure only, no FPPS and no class.

Schema 1.0 gives every scored row a class, so it does not carry this case.
"""
PUBLIC_WEB_ROOT: tuple[str, ...] = ("apps", "web", "public")
FPPS_TOLERANCE = 1e-9
WEIGHT_SUM_TOLERANCE = 1e-9
MEASUREMENT_TOLERANCE = 1e-9

# Refusal codes. The web parser uses the same strings.
STRUCTURE = "structure"
UNKNOWN_TIER = "unknown_tier"
ACCEPTED_VALUE_NOT_NULL = "accepted_value_not_null"
OFFICIAL_WARNING_NOT_FALSE = "official_warning_not_false"
NOT_NON_OPERATIONAL = "operational_status_not_non_operational"
CLASS_ABOVE_E_WITHOUT_MEDIUM_CONFIDENCE = "class_above_e_without_medium_confidence"
TEMPORAL_HONESTY_GR7 = "temporal_honesty_gr7"
HIGH_CONFIDENCE_NOT_ASSIGNED = "high_confidence_not_assigned"
TIER_LANE_MISMATCH = "tier_lane_mismatch"
T4_LOCKED_ROW_CARRIES_VALUES = "t4_locked_row_carries_values"
CONFIDENCE_RECORD_MISMATCH = "confidence_record_mismatch"
TEMPORAL_RELATION_MISMATCH = "temporal_relation_mismatch"
ASSUMED_COMPONENT = "assumed_component_in_a_row"
COMPONENT_MISMATCH = "component_mismatch"
FPPS_MISMATCH = "fpps_mismatch"
GR1_NO_CLASS = "gr1_no_class"
LOW_CONFIDENCE_FORCES_E = "low_confidence_forces_e"
CLASS_RULE_MISMATCH = "class_rule_mismatch"
REASON_CODE_MISMATCH = "reason_code_mismatch"
WOULD_BE_CLASS_MISMATCH = "would_be_class_mismatch"
V2_RESULT_INCONSISTENT = "v2_result_inconsistent"
LOCO_MISMATCH = "leave_one_component_out_mismatch"
HEADLINE_STABILITY_INCONSISTENT = "headline_stability_inconsistent"
LINEAGE_UNRESOLVED = "lineage_unresolved"
PUBLICATION_NOT_LINEAGE_MINIMUM = "publication_eligibility_not_lineage_minimum"
PRODUCT_4009_LICENCE_MISSING = "product_4009_licence_missing"
SOURCE_PRODUCT_NOT_DECLARED = "source_product_not_declared"
PROTOCOL_HASH_MISMATCH = "protocol_hash_mismatch"
SCORING_FRAME_INCONSISTENT = "scoring_frame_inconsistent"
DUPLICATE_ID = "duplicate_id"
FIXTURE_LABEL_MISSING = "fixture_label_missing"
PROTOCOL_BINDING_REQUIRED = "protocol_binding_required"
PROTOCOL_NOT_IN_FORCE = "protocol_not_in_force"
FRAME_NOT_PROTOCOL_FRAME = "frame_not_protocol_frame"
COMPONENT_NOT_FRAME_RECORD = "component_not_frame_record"
CONFIDENCE_NOT_RULE_RECORD = "confidence_not_rule_record"
CASE_NOT_PROTOCOL_CASE = "case_not_protocol_case"
PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER = "product_4009_layer_not_protocol_layer"
PUBLIC_WRITE_NOT_ELIGIBLE = "public_write_not_eligible"
PRODUCT_4009_RIGHTS_NOT_CONFIRMED = "product_4009_rights_not_confirmed"

REFUSAL_CODES: tuple[str, ...] = (
    STRUCTURE,
    UNKNOWN_TIER,
    ACCEPTED_VALUE_NOT_NULL,
    OFFICIAL_WARNING_NOT_FALSE,
    NOT_NON_OPERATIONAL,
    CLASS_ABOVE_E_WITHOUT_MEDIUM_CONFIDENCE,
    TEMPORAL_HONESTY_GR7,
    HIGH_CONFIDENCE_NOT_ASSIGNED,
    TIER_LANE_MISMATCH,
    T4_LOCKED_ROW_CARRIES_VALUES,
    CONFIDENCE_RECORD_MISMATCH,
    TEMPORAL_RELATION_MISMATCH,
    ASSUMED_COMPONENT,
    COMPONENT_MISMATCH,
    FPPS_MISMATCH,
    GR1_NO_CLASS,
    LOW_CONFIDENCE_FORCES_E,
    CLASS_RULE_MISMATCH,
    REASON_CODE_MISMATCH,
    WOULD_BE_CLASS_MISMATCH,
    V2_RESULT_INCONSISTENT,
    LOCO_MISMATCH,
    HEADLINE_STABILITY_INCONSISTENT,
    LINEAGE_UNRESOLVED,
    PUBLICATION_NOT_LINEAGE_MINIMUM,
    PRODUCT_4009_LICENCE_MISSING,
    SOURCE_PRODUCT_NOT_DECLARED,
    PROTOCOL_HASH_MISMATCH,
    SCORING_FRAME_INCONSISTENT,
    DUPLICATE_ID,
    FIXTURE_LABEL_MISSING,
    PROTOCOL_BINDING_REQUIRED,
    PROTOCOL_NOT_IN_FORCE,
    FRAME_NOT_PROTOCOL_FRAME,
    COMPONENT_NOT_FRAME_RECORD,
    CONFIDENCE_NOT_RULE_RECORD,
    CASE_NOT_PROTOCOL_CASE,
    PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER,
    PUBLIC_WRITE_NOT_ELIGIBLE,
    PRODUCT_4009_RIGHTS_NOT_CONFIRMED,
)
"""Every refusal code this module gives."""

PYTHON_ONLY_CODES: tuple[str, ...] = (
    PROTOCOL_BINDING_REQUIRED,
    PUBLIC_WRITE_NOT_ELIGIBLE,
    PRODUCT_4009_RIGHTS_NOT_CONFIRMED,
)
"""Codes the web parser never gives: it always holds the protocol binding, and it writes nothing."""

_SHAPE_ERRORS = (KeyError, TypeError, AttributeError, ValueError, IndexError)


@dataclass(frozen=True)
class OverlayProblem:
    """One reason an overlay is refused: a stable code, where it was found and what is wrong."""

    code: str
    path: str
    message: str


class PlanningOverlayError(ValueError):
    """Raised when an overlay is refused. ``problems`` lists every reason found."""

    def __init__(self, problems: Iterable[OverlayProblem]) -> None:
        self.problems: tuple[OverlayProblem, ...] = tuple(problems)
        shown = "; ".join(f"{item.code} at {item.path}: {item.message}" for item in self.problems[:5])
        more = len(self.problems) - 5
        super().__init__(f"planning overlay refused: {shown}" + (f" (and {more} more)" if more > 0 else ""))

    @property
    def codes(self) -> tuple[str, ...]:
        """The refusal codes, once each, in the order found."""

        return tuple(dict.fromkeys(item.code for item in self.problems))


# ---------------------------------------------------------------------------
# The protocol binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProtocolCase:
    """One case of protocol v1a ``case_portfolio``: its reference date, lane, tier and flood inputs."""

    case_id: str
    case_reference_date: str | None
    lane: str
    tier: str
    flood_inputs: tuple[str, ...]


@dataclass(frozen=True)
class Product4009Layers:
    """The names protocol v1a gives the two product 4009 layers, and the date of the dated one.

    ``accumulated_names`` and ``dated_names`` hold the layer name of
    ``date_rule.product_4009`` and the flood-input names of the cases built on
    the layer. The accumulated layer has no single acquisition date.
    """

    accumulated_names: tuple[str, ...]
    dated_names: tuple[str, ...]
    dated_acquisition_date: str


@dataclass(frozen=True)
class ProtocolBinding:
    """What the validator reads from the two protocol files in force.

    ``frame`` and ``rule`` recompute the component and confidence records.
    ``cases`` and ``cut_cases`` bind the case header, and ``product_4009`` the
    two layers of that product. ``class_rule_v1``, ``class_rule_v2`` and
    ``headline_class_retention_min`` are handed to the web parser
    (:func:`protocol_binding_record`); this module takes the v1 class from
    ``scoring.py``, which protocol v1a names as the source of the rule.
    """

    frame: PlanningFrame
    rule: ConfidenceRule
    cases: Mapping[str, ProtocolCase]
    cut_cases: tuple[str, ...]
    class_rule_v1: tuple[Mapping[str, Any], ...]
    class_rule_v2: Mapping[str, Any]
    product_4009: Product4009Layers
    headline_class_retention_min: float


def load_protocol_binding(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> ProtocolBinding:
    """Read frame v1, confidence rule v1 and the case portfolio from the protocol files in force.

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not in
            force, or protocol v1a does not hold what this module binds to.
        floodguard.confidence.ConfidenceError: when v1a does not hold rule v1.
    """

    frame = load_planning_frame(v1a_path, v1b_path, receipts_path)
    rule = load_confidence_rule(v1a_path, receipts_path)
    v1a, _sha256 = read_protocol_in_force("v1a", v1a_path, receipts_path)
    try:
        return _binding(frame, rule, v1a)
    except NormalisationError:
        raise
    except _SHAPE_ERRORS as error:
        raise NormalisationError(f"protocol v1a does not hold what the overlay binds to: {error!r}") from error


def _binding(frame: PlanningFrame, rule: ConfidenceRule, v1a: Mapping[str, Any]) -> ProtocolBinding:
    """Read the case portfolio, the class rules and the product 4009 layers; refuse a protocol this module is not."""

    portfolio = v1a["case_portfolio"]
    cases = {
        str(case["id"]): ProtocolCase(
            case_id=str(case["id"]),
            case_reference_date=case["case_reference_date"],
            lane=str(case["lane"]),
            tier=str(case["tier"]),
            flood_inputs=tuple(str(name) for name in case["flood_inputs"]),
        )
        for case in portfolio["cases"]
    }
    product = v1a["date_rule"]["product_4009"]
    accumulated, dated = product["accumulated_layer"], product["layer_22_oct"]
    if (str(accumulated["layer"]), str(dated["layer"])) != PRODUCT_4009_LAYER_NAMES:
        raise NormalisationError("protocol v1a does not name the two product 4009 layers this module recognises")
    if accumulated["lane"] != SEASON_ENVELOPE_LANE or accumulated["temporal_relation"] != SEASON_WINDOW:
        raise NormalisationError("protocol v1a does not place the 4009 accumulated layer in lane SCN-ENV")
    accumulated_names = [str(accumulated["layer"])]
    dated_names = [str(dated["layer"])]
    for case in cases.values():
        if case.lane == SEASON_ENVELOPE_LANE:
            accumulated_names.extend(case.flood_inputs)
        if case.case_id == dated["case"]:
            dated_names.extend(case.flood_inputs)
    if cases[str(dated["case"])].case_reference_date != dated["case_reference_date"]:
        raise NormalisationError("protocol v1a gives the 22 Oct layer and its own case two reference dates")
    date.fromisoformat(dated["case_reference_date"])
    v2 = v1a["class_rules"]["v2"]
    parameters = v2["parameters"]
    if (
        tuple(v2["evaluation"]["order"]) != V2_TRIGGER_ORDER
        or v2["evaluation"]["otherwise"] != NO_V2_TRIGGER
        or float(parameters["fpps_min"]) != V2_FPPS_MIN
        or float(parameters["exposure_floor_for_non_e"]) != V2_EXPOSURE_FLOOR_FOR_NON_E
    ):
        raise NormalisationError("protocol v1a does not hold class rule v2 as this module checks it")
    notes = {case["id"]: str(case.get("note", "")) for case in portfolio["cases"]}
    if any("no FPPS and no class" not in notes.get(case_id, "") for case_id in CASES_WITHOUT_CLASS):
        raise NormalisationError("protocol v1a does not describe the cases this module treats as having no class")
    guardrails = {row["id"]: row for row in v1a["guardrails"]}
    return ProtocolBinding(
        frame=frame,
        rule=rule,
        cases=cases,
        cut_cases=tuple(str(name) for name in portfolio["cut_now"]),
        class_rule_v1=tuple(v1a["class_rules"]["v1"]["rules"]),
        class_rule_v2={
            "version": str(v2["version"]),
            "order": list(V2_TRIGGER_ORDER),
            "otherwise": NO_V2_TRIGGER,
            "fpps_min": V2_FPPS_MIN,
            "exposure_floor_for_non_e": V2_EXPOSURE_FLOOR_FOR_NON_E,
        },
        product_4009=Product4009Layers(
            accumulated_names=tuple(dict.fromkeys(accumulated_names)),
            dated_names=tuple(dict.fromkeys(dated_names)),
            dated_acquisition_date=str(dated["case_reference_date"]),
        ),
        headline_class_retention_min=float(guardrails[GUARDRAIL_GR8]["parameters"]["class_retention_min"]),
    )


def protocol_binding_record(binding: ProtocolBinding) -> dict[str, Any]:
    """Return the protocol constants the web parser checks an overlay against, as plain JSON.

    The web parser cannot read the protocol files, so it reads this record,
    which ``apps/web/scripts/planning-overlay-fixture.py`` writes and a test
    compares with the files in force. Every value comes from protocol v1a or
    v1b, or is a constant of this module that :func:`load_protocol_binding`
    checks against v1a. It holds no value for any unit.
    """

    rule = binding.rule
    layers = binding.product_4009
    return {
        "about": (
            "Constants of the signed planning protocols v1a and v1b, written by "
            "apps/web/scripts/planning-overlay-fixture.py from the two files in force. The web parser of the "
            "planning assessment overlay checks every overlay against them. Not edited by hand; it holds no "
            "value for any unit."
        ),
        "protocol_sha256": protocol_hashes(binding.frame),
        "scoring_frame": frame_record(binding.frame),
        "component_definitions": {name: binding.frame.definitions[name] for name in SCORE_COMPONENTS},
        "vulnerability_caveat": binding.frame.vulnerability_caveat,
        "confidence_rule": {
            "version": rule.version,
            "thresholds": _rule_thresholds(rule),
            "gr1_unit_residents_min_for_class": rule.gr1_unit_residents_min_for_class,
            "t2_skill": {
                "thresholds": _skill_thresholds(rule),
                "declared_unable_to_meet": list(rule.skill_declared_unable_to_meet),
                "evaluated_by_the_rule": list(rule.skill_evaluated_by_the_rule),
            },
            "own_t2_candidates_named": list(rule.own_t2_candidates_named),
            "coverage_by_construction": {
                "units": list(rule.coverage_by_construction_units),
                "flood_inputs": list(rule.coverage_by_construction_flood_inputs),
            },
        },
        "class_rule_v1": {"version": "class_rule_v1", "rules": [dict(row) for row in binding.class_rule_v1]},
        "class_rule_v2": dict(binding.class_rule_v2),
        "headline": {"guardrail": GUARDRAIL_GR8, "class_retention_min": binding.headline_class_retention_min},
        "cases": [
            {
                "id": case.case_id,
                "case_reference_date": case.case_reference_date,
                "lane": case.lane,
                "tier": case.tier,
                "flood_inputs": list(case.flood_inputs),
            }
            for case in binding.cases.values()
        ],
        "cases_without_class": list(CASES_WITHOUT_CLASS),
        "cut_cases": list(binding.cut_cases),
        "product_4009": {
            "source_product": PRODUCT_4009_SOURCE,
            "licence": PRODUCT_4009_LICENCE,
            "credit": PRODUCT_4009_CREDIT,
            "event_code": PRODUCT_4009_EVENT_CODE,
            "layer_names": list(PRODUCT_4009_LAYER_NAMES),
            "accumulated_names": list(layers.accumulated_names),
            "dated_names": list(layers.dated_names),
            "dated_acquisition_date": layers.dated_acquisition_date,
        },
    }


def _rule_thresholds(rule: ConfidenceRule) -> dict[str, float]:
    """The thresholds a confidence record echoes, as ``confidence.derive_confidence`` writes them."""

    return {
        "recency_window_days": rule.recency_window_days,
        "unit_valid_coverage_min": rule.unit_valid_coverage_min,
        "exposure_plus_minus_one_pixel_max_points": rule.exposure_plus_minus_one_pixel_max_points,
        "exposure_plus_minus_one_pixel_float_guard_points": C4_FLOAT_GUARD_POINTS,
        "t2_abstention_fraction_max": rule.t2_abstention_fraction_max,
        "unit_residents_min": rule.unit_residents_min,
        "baseline_vehicle_no_route_share_max": rule.baseline_vehicle_no_route_share_max,
        "hospitals_reachable_at_baseline_min": rule.hospitals_reachable_at_baseline_min,
    }


def _skill_thresholds(rule: ConfidenceRule) -> dict[str, float]:
    """The thresholds a T2 skill record echoes, as ``confidence.t2_skill_condition`` writes them."""

    return {
        "geoid_held_out_test_iou_min": rule.skill_geoid_held_out_test_iou_min,
        "mae_sai_abstention_fraction_max": rule.skill_abstention_fraction_max,
        "mae_sai_unit_coverage_min": rule.skill_unit_coverage_min,
        "recency_window_days": rule.skill_recency_window_days,
    }


def load_overlay_schema(path: Path | str) -> dict[str, Any]:
    """Read the overlay JSON schema from ``path`` (see ``SCHEMA_RELATIVE_PATH``)."""

    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(schema, dict) or schema.get("$id") != SCHEMA_ID:
        raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", f"the schema file is not {SCHEMA_ID}")])
    return schema


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------


def _ecmascript_pattern(pattern: str) -> str:
    """Give a pattern that ends in ``$`` the meaning it has in ECMAScript.

    Python's ``$`` also matches before a final line feed, so ``abc\\n`` would
    pass ``^[a-z]+$`` here and fail it in the web parser. ``\\Z`` matches at the
    very end only.
    """

    if pattern.endswith("$") and not pattern.endswith("\\$"):
        return pattern[:-1] + r"\Z"
    return pattern


@lru_cache(maxsize=1)
def _validator_class() -> Any:
    """The draft 2020-12 validator with ``pattern`` anchored as the web parser anchors it."""

    from jsonschema import Draft202012Validator, ValidationError, validators

    def pattern(validator: Any, value: str, instance: Any, schema: Any) -> Any:
        if validator.is_type(instance, "string") and not re.search(_ecmascript_pattern(value), instance):
            yield ValidationError(f"{instance!r} does not match {value!r}")

    return validators.extend(Draft202012Validator, {"pattern": pattern})


def schema_problems(overlay: Any, schema: Mapping[str, Any]) -> list[OverlayProblem]:
    """Return the JSON-schema violations of ``overlay`` as ``structure`` problems, sorted by path.

    Calendar dates are checked (``format: date``), and a pattern that ends in
    ``$`` does not accept a trailing line feed, so the result is the one the
    web parser gives for the same text.
    """

    from jsonschema import FormatChecker

    validator = _validator_class()(schema, format_checker=FormatChecker(("date",)))
    found = [
        OverlayProblem(STRUCTURE, _json_path(error.absolute_path), error.message[:300])
        for error in validator.iter_errors(overlay)
    ]
    return sorted(found, key=lambda item: (item.path, item.message))


def _non_finite_problems(value: Any, path: str = "$") -> list[OverlayProblem]:
    """Find every number that is not finite. JSON has none, and the web parser cannot read one."""

    if isinstance(value, float) and not math.isfinite(value):
        return [OverlayProblem(STRUCTURE, path, "a number is not finite")]
    if isinstance(value, Mapping):
        return [item for key, child in value.items() for item in _non_finite_problems(child, f"{path}.{key}")]
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in _non_finite_problems(child, f"{path}[{index}]")]
    return []


def overlay_problems(
    overlay: Any,
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
) -> list[OverlayProblem]:
    """Return every reason ``overlay`` is refused; an empty list means it is accepted.

    Args:
        overlay: The parsed overlay.
        schema: The overlay JSON schema (:func:`load_overlay_schema`).
        binding: The protocols in force (:func:`load_protocol_binding`). When
            given, the component and confidence records are recomputed from the
            inputs they echo, the hashes are compared with the files in force
            and the case header is compared with protocol v1a. An overlay that
            is not a fixture is refused without it.
    """

    if not isinstance(overlay, Mapping):
        return [OverlayProblem(STRUCTURE, "$", "the overlay must be a JSON object")]
    structure = [*_non_finite_problems(overlay), *schema_problems(overlay, schema)]
    problems = [*_guard_problems(overlay, binding), *structure]
    checks: list[Callable[[], list[OverlayProblem]]] = [lambda: _overlay_level_problems(overlay)]
    rows = overlay.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            checks.append(lambda row=row, index=index: _row_problems(overlay, row, f"$.rows[{index}]"))
    if binding is not None:
        checks.append(lambda: _binding_problems(overlay, binding))
        checks.append(lambda: _case_problems(overlay, binding))
        checks.append(lambda: _product_4009_layer_problems(overlay, binding))
    for check in checks:
        try:
            problems.extend(check())
        except _SHAPE_ERRORS:
            # A malformed overlay can break a cross-field check. The structure problems already say why.
            if not structure:
                raise
    return list(dict.fromkeys(problems))


def validate_overlay(
    overlay: Any,
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
) -> None:
    """Raise :class:`PlanningOverlayError` unless ``overlay`` is accepted."""

    problems = overlay_problems(overlay, schema, binding=binding)
    if problems:
        raise PlanningOverlayError(problems)


def _refuse_json_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


def load_overlay(
    path: Path | str,
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
) -> dict[str, Any]:
    """Read an overlay file and return it only when it is accepted.

    ``NaN`` and ``Infinity`` are not JSON: a file that holds one is refused, as
    the web parser refuses it.

    Raises:
        PlanningOverlayError: when the file is not JSON, is not a JSON object or is refused.
    """

    try:
        overlay = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_refuse_json_constant)
    except ValueError as error:
        detail = error.msg if isinstance(error, json.JSONDecodeError) else str(error)
        raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", f"not valid JSON: {detail}")]) from error
    validate_overlay(overlay, schema, binding=binding)
    return overlay


def _json_path(parts: Iterable[Any]) -> str:
    """Return a path like ``rows[3].confidence.basis`` from the parts jsonschema reports."""

    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _guard_problems(overlay: Mapping[str, Any], binding: ProtocolBinding | None) -> list[OverlayProblem]:
    """The refusals that must be named whatever else is wrong; they assume nothing about the shape."""

    problems: list[OverlayProblem] = []
    if overlay.get("official_warning") is not False:
        problems.append(OverlayProblem(OFFICIAL_WARNING_NOT_FALSE, "$.official_warning", "must be false"))
    if overlay.get("operational_status") != "non_operational":
        problems.append(OverlayProblem(NOT_NON_OPERATIONAL, "$.operational_status", "must be non_operational"))
    if binding is None and overlay.get("dataset_mode") != FIXTURE_MODE:
        problems.append(
            OverlayProblem(
                PROTOCOL_BINDING_REQUIRED,
                "$.dataset_mode",
                "only a fixture (fixture_demo) is checked without the two protocol files in force: a candidate "
                "overlay needs load_protocol_binding",
            )
        )
    for name in ACCEPTED_FIELDS:
        if overlay.get(name) is not None:
            problems.append(OverlayProblem(ACCEPTED_VALUE_NOT_NULL, f"$.{name}", "is null while tier T4 is locked"))
    rows = overlay.get("rows")
    if not isinstance(rows, list):
        return problems
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        where = f"$.rows[{index}]"
        if row.get("tier") not in TIERS:
            problems.append(OverlayProblem(UNKNOWN_TIER, f"{where}.tier", f"{row.get('tier')!r} is not one of {TIERS}"))
        for name in ACCEPTED_FIELDS:
            if row.get(name) is not None:
                problems.append(
                    OverlayProblem(ACCEPTED_VALUE_NOT_NULL, f"{where}.{name}", "is null while tier T4 is locked")
                )
        confidence = row.get("confidence")
        confidence_class = confidence.get("confidence_class") if isinstance(confidence, Mapping) else None
        action_class = row.get("action_class")
        if confidence_class == "high":
            problems.append(
                OverlayProblem(
                    HIGH_CONFIDENCE_NOT_ASSIGNED,
                    f"{where}.confidence.confidence_class",
                    "high requires tier T4, which is locked in this release",
                )
            )
        if action_class in CLASSES_ABOVE_E and confidence_class != "medium":
            problems.append(
                OverlayProblem(
                    CLASS_ABOVE_E_WITHOUT_MEDIUM_CONFIDENCE,
                    f"{where}.action_class",
                    f"binding class {action_class} with confidence {confidence_class!r}: "
                    "no class above E without medium confidence",
                )
            )
        if (
            row.get("lane") == OBSERVED_LANE
            and row.get("temporal_relation") != EVENT_ALIGNED
            and action_class in CLASSES_ABOVE_E
        ):
            problems.append(
                OverlayProblem(
                    TEMPORAL_HONESTY_GR7,
                    f"{where}.action_class",
                    f"an OBS row that is {row.get('temporal_relation')!r}, not event_aligned, "
                    f"carries binding class {action_class}",
                )
            )
    return problems


def _overlay_level_problems(overlay: Mapping[str, Any]) -> list[OverlayProblem]:
    """Checks on the header: hashes, rights, identifiers and fixture labels."""

    problems: list[OverlayProblem] = []
    hashes = overlay["protocol_sha256"]
    if overlay["scoring_frame"]["protocol_sha256"] != hashes:
        problems.append(
            OverlayProblem(PROTOCOL_HASH_MISMATCH, "$.scoring_frame.protocol_sha256", "differs from $.protocol_sha256")
        )
    frame = overlay["scoring_frame"]
    weight_sets = {"weights": frame["weights"]}
    left_out = frame["leave_one_component_out_weights"]
    weight_sets.update({f"leave_one_component_out_weights.{name}": left_out[name] for name in SCORE_COMPONENTS})
    for name, weights in weight_sets.items():
        dropped = name.rpartition(".")[2]
        if abs(sum(weights.values()) - 1.0) > WEIGHT_SUM_TOLERANCE or (dropped in weights and weights[dropped] != 0):
            problems.append(
                OverlayProblem(
                    SCORING_FRAME_INCONSISTENT,
                    f"$.scoring_frame.{name}",
                    "the weights sum to 1, and a leave-one-out set gives the dropped component 0",
                )
            )
    inputs = overlay["inputs"]
    rows = overlay["rows"]
    for name, values in (
        ("input_id", [item["input_id"] for item in inputs]),
        ("row_id", [row["row_id"] for row in rows]),
    ):
        repeated = sorted({value for value in values if values.count(value) > 1})
        if repeated:
            problems.append(OverlayProblem(DUPLICATE_ID, "$", f"{name} repeated: {repeated}"))
    keys = [_row_key(row) for row in rows]
    twice = sorted({row["row_id"] for row, key in zip(rows, keys) if keys.count(key) > 1})
    if twice:
        problems.append(
            OverlayProblem(
                DUPLICATE_ID,
                "$.rows",
                "one row is one unit in one lane with one flood input and one scenario; "
                f"these rows share theirs: {twice}",
            )
        )
    lowest = min(PUBLICATION_LEVELS.index(item["rights_level"]) for item in inputs)
    eligibility = overlay["publication_eligibility"]
    if eligibility != PUBLICATION_LEVELS[lowest]:
        problems.append(
            OverlayProblem(
                PUBLICATION_NOT_LINEAGE_MINIMUM,
                "$.publication_eligibility",
                f"{eligibility!r} is not the minimum across the lineage ({PUBLICATION_LEVELS[lowest]!r})",
            )
        )
    for index, row in enumerate(rows):
        record = row["components"]["access_gap_0_100"]
        if isinstance(record, Mapping) and record.get("publication_level") == "pitch" and eligibility == "public":
            problems.append(
                OverlayProblem(
                    PUBLICATION_NOT_LINEAGE_MINIMUM,
                    f"$.rows[{index}].components.access_gap_0_100.publication_level",
                    "a pitch-level access gap cannot sit in a public overlay",
                )
            )
    for index, item in enumerate(inputs):
        if not _declares_product_4009(item):
            if _names_product_4009(item):
                problems.append(
                    OverlayProblem(
                        SOURCE_PRODUCT_NOT_DECLARED,
                        f"$.inputs[{index}].source_product",
                        f"the input names product 4009, so its source_product is {PRODUCT_4009_SOURCE!r}",
                    )
                )
            continue
        complete = (
            item["licence"] == PRODUCT_4009_LICENCE
            and PRODUCT_4009_CREDIT in item["attribution"]
            and isinstance(item["change_notice"], str)
            and bool(item["change_notice"].strip())
        )
        if not complete:
            problems.append(
                OverlayProblem(
                    PRODUCT_4009_LICENCE_MISSING,
                    f"$.inputs[{index}]",
                    f"a product 4009 input carries the licence {PRODUCT_4009_LICENCE}, the credit "
                    f"'{PRODUCT_4009_CREDIT}' and a change notice",
                )
            )
    if overlay["dataset_mode"] == FIXTURE_MODE:
        unlabelled = [row["row_id"] for row in rows if FIXTURE_LABEL not in row["unit_name_en"]]
        if unlabelled:
            problems.append(
                OverlayProblem(
                    FIXTURE_LABEL_MISSING, "$.rows", f"fixture units are named '{FIXTURE_LABEL}': {unlabelled}"
                )
            )
    return problems


def _row_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """What one row is: its unit, lane, flood input and scenario."""

    scenario = row["scenario"]
    return (row["unit_id"], row["lane"], row["lineage"]["flood_input_id"], None if scenario is None else scenario["id"])


def _declares_product_4009(item: Mapping[str, Any]) -> bool:
    """Say whether an input record declares product 4009 as its source product."""

    return item.get("source_product") == PRODUCT_4009_SOURCE


def _names_product_4009(item: Mapping[str, Any]) -> bool:
    """Say whether an input record names product 4009 in its identifier, name or attribution.

    The text is matched against the citation the rights module knows, the bare
    product number, the event code and the two layer names of protocol v1a.
    """

    return any(
        isinstance(item.get(key), str) and _PRODUCT_4009_TEXT.search(item[key])
        for key in ("input_id", "name", "attribution")
    )


def cites_product_4009(overlay: Mapping[str, Any]) -> bool:
    """Say whether any input in the lineage of ``overlay`` is UNOSAT/GISTDA product 4009.

    An input is product 4009 when it declares it (``source_product``) or names
    it. A validated overlay never names it without declaring it.
    """

    return any(
        _declares_product_4009(item) or _names_product_4009(item)
        for item in overlay.get("inputs", ())
        if isinstance(item, Mapping)
    )


def _row_problems(overlay: Mapping[str, Any], row: Mapping[str, Any], where: str) -> list[OverlayProblem]:
    """The cross-field checks of one row."""

    problems: list[OverlayProblem] = []

    def add(code: str, field: str, message: str) -> None:
        problems.append(OverlayProblem(code, f"{where}.{field}" if field else where, message))

    tier, lane = row["tier"], row["lane"]
    if lane not in TIER_LANES[tier]:
        add(TIER_LANE_MISMATCH, "lane", f"tier {tier} belongs to {TIER_LANES[tier]}, not {lane!r}")
    components = row["components"]
    if tier == LOCKED_TIER:
        carried = [
            name
            for name in (
                "temporal_relation",
                "flood_input",
                "scenario",
                "fpps_0_100",
                "confidence",
                "action_class",
                "action_reason_code",
                "would_be_class",
                "class_v2",
                "leave_one_component_out",
            )
            if row[name] is not None
        ]
        carried += [name for name in SCORE_COMPONENTS if components[name] is not None]
        carried += [name for name, value in row["lineage"].items() if value is not None]
        if row["headline_stability"]["status"] != HEADLINE_NOT_EVALUATED:
            carried.append("headline_stability")
        if carried:
            add(T4_LOCKED_ROW_CARRIES_VALUES, "", f"tier T4 is locked in this release; the row carries {carried}")
        return problems

    confidence = row["confidence"]
    confidence_class = confidence["confidence_class"]
    kind = confidence["confidence_kind"]
    if kind != KIND_BY_TIER[tier]:
        expected_kind = KIND_BY_TIER[tier]
        add(CONFIDENCE_RECORD_MISMATCH, "confidence.confidence_kind", f"tier {tier} carries {expected_kind} confidence")
    gr1_applies = False
    lineage = row["lineage"]
    if kind == KIND_DECLARED:
        if any(components[name] is None for name in SCORE_COMPONENTS):
            add(COMPONENT_MISMATCH, "components", "an engine row carries all five components")
    else:
        gr1_applies = bool(confidence["guardrail_gr1"]["applies"])
        problems.extend(_derived_confidence_problems(overlay, row, where))
        inputs = {item["input_id"]: item for item in overlay["inputs"]}
        flood = inputs.get(lineage["flood_input_id"])
        if flood is None or flood["role"] != FLOOD_INPUT_ROLE or flood["name"] != row["flood_input"]:
            add(LINEAGE_UNRESOLVED, "lineage.flood_input_id", "does not name the flood input of the row")
        elif flood["acquisition_date"] != confidence["measurements"]["acquisition_date"]:
            add(
                CONFIDENCE_RECORD_MISMATCH,
                "confidence.measurements.acquisition_date",
                f"is {confidence['measurements']['acquisition_date']!r}; the flood input record says "
                f"{flood['acquisition_date']!r}",
            )
        routing = inputs.get(lineage["routing_context_id"])
        if routing is None or routing["role"] != ROUTING_CONTEXT_ROLE:
            add(LINEAGE_UNRESOLVED, "lineage.routing_context_id", "does not name a routing context")
        expected_basis = f"{CLOSURE_BASIS_PREFIX}{lineage['flood_input_id']}"
        if lineage["closure_rule"]["closure_basis"] != expected_basis:
            add(
                LINEAGE_UNRESOLVED,
                "lineage.closure_rule.closure_basis",
                f"the closure of a row is modelled from its own flood input (guardrail GR3): {expected_basis}",
            )
        exposure = components["exposure_0_100"]
        residents = confidence["measurements"]["unit_residents"]
        if (
            isinstance(exposure, Mapping)
            and exposure.get("synthetic") is not True
            and exposure["inputs"]["unit_residents"] != residents
        ):
            add(
                CONFIDENCE_RECORD_MISMATCH,
                "confidence.measurements.unit_residents",
                f"is {residents!r}; the exposure record of the row counts {exposure['inputs']['unit_residents']!r} "
                "unit residents. Guardrail GR1 and condition C6 are judged on the residents the row is scored on",
            )

    values: dict[str, float | None] = {}
    for name in SCORE_COMPONENTS:
        record = components[name]
        values[name] = None if record is None else float(record["value_0_100"])
        if record is None:
            continue
        if record["component"] != name:
            add(COMPONENT_MISMATCH, f"components.{name}.component", f"is {record['component']!r}")
        if record.get("synthetic") is True:
            if tier != ENGINE_TIER:
                add(COMPONENT_MISMATCH, f"components.{name}", "a synthetic value belongs to an engine row (tier T0)")
        elif record["protocol_sha256"] != overlay["protocol_sha256"]:
            add(PROTOCOL_HASH_MISMATCH, f"components.{name}.protocol_sha256", "differs from $.protocol_sha256")

    fpps = row["fpps_0_100"]
    loco = row["leave_one_component_out"]
    action_class, reason_code, would_be = row["action_class"], row["action_reason_code"], row["would_be_class"]
    complete = all(value is not None for value in values.values())
    scored = _score(values, confidence_class, overlay["scoring_frame"]["weights"]) if complete else None
    if scored is None:
        if fpps is not None or loco is not None:
            message = "a row with a component that is not computed has no FPPS and no leave-one-out"
            add(FPPS_MISMATCH, "fpps_0_100", message)
    elif fpps is None or abs(fpps - scored[0]) > FPPS_TOLERANCE:
        add(FPPS_MISMATCH, "fpps_0_100", f"is {fpps!r}; the frame weights give {scored[0]!r}")

    if gr1_applies:
        v2 = row["class_v2"]
        if (
            action_class is not None
            or reason_code != REASON_INSUFFICIENT_DENOMINATOR
            or would_be is not None
            or v2["result"] is not None
            or v2["trigger_evidence"]
        ):
            add(
                GR1_NO_CLASS,
                "action_class",
                "guardrail GR1: no binding class, no would-be class and no v2 class; reason insufficient_denominator",
            )
    else:
        if action_class is None or reason_code == REASON_INSUFFICIENT_DENOMINATOR:
            add(
                GR1_NO_CLASS,
                "action_class",
                "in schema 1.0 every row below tier T4 carries a class, and only a unit under guardrail GR1 has none",
            )
        if confidence_class == "low":
            if action_class != "E" or reason_code != REASON_LOW_CONFIDENCE:
                message = "low confidence gives binding class E, reason low_confidence"
                add(LOW_CONFIDENCE_FORCES_E, "action_class", message)
        else:
            expected_reason = "low_priority_score" if action_class == "E" else REASON_BY_CLASS.get(action_class)
            if action_class is not None and reason_code != expected_reason:
                add(
                    REASON_CODE_MISMATCH,
                    "action_reason_code",
                    f"is {reason_code!r}; class {action_class} carries {expected_reason}",
                )
            if scored is not None and action_class != scored[1]:
                add(CLASS_RULE_MISMATCH, "action_class", f"is {action_class!r}; class rule v1 gives {scored[1]!r}")

    expected_would_be = None
    if confidence_class == "low" and not gr1_applies and complete:
        expected_would_be = _score(values, "medium", overlay["scoring_frame"]["weights"])[1]
    if would_be != expected_would_be:
        add(
            WOULD_BE_CLASS_MISMATCH,
            "would_be_class",
            f"is {would_be!r}; the scorer rerun with confidence medium gives {expected_would_be!r} "
            "(a would-be class exists for low-confidence rows only and is never binding)",
        )

    if scored is not None and loco is not None:
        loco_weights = overlay["scoring_frame"]["leave_one_component_out_weights"]
        for dropped in SCORE_COMPONENTS:
            left_out = _score(values, confidence_class, loco_weights[dropped])
            expected_class = None if gr1_applies else left_out[1]
            entry = loco[dropped]
            if abs(entry["fpps_0_100"] - left_out[0]) > FPPS_TOLERANCE or entry["action_class"] != expected_class:
                expected = f"expected {left_out[0]!r} and {expected_class!r}"
                add(LOCO_MISMATCH, f"leave_one_component_out.{dropped}", expected)
    elif scored is not None:
        add(LOCO_MISMATCH, "leave_one_component_out", "is required on every row that has an FPPS")

    if tier != ENGINE_TIER:
        problems.extend(_v2_problems(row, confidence_class, gr1_applies, values["exposure_0_100"], where))
    headline = row["headline_stability"]
    retention = headline["class_retention"]
    status = headline["status"]
    expected_status = HEADLINE_NOT_EVALUATED
    if retention is not None:
        expected_status = HEADLINE_ELIGIBLE if retention >= headline["class_retention_min"] else HEADLINE_UNSTABLE
    if status != expected_status or (action_class is None and status != HEADLINE_NOT_EVALUATED):
        add(
            HEADLINE_STABILITY_INCONSISTENT,
            "headline_stability",
            f"status {status!r} with retention {retention!r} and class {action_class!r} (guardrail GR8)",
        )
    return problems


def _date(value: str | None) -> date | None:
    """A calendar date from its ISO text; None stays None. An impossible date raises ValueError."""

    return None if value is None else date.fromisoformat(value)


def _recency_days(acquisition_date: str | None, case_reference_date: str | None) -> int | None:
    """The whole days between two echoed dates, or None when either is missing."""

    acquired, reference = _date(acquisition_date), _date(case_reference_date)
    if acquired is None or reference is None:
        return None
    return abs((acquired - reference).days)


def _met(passes: bool) -> str:
    return PASS if passes else FAIL


def _at_least(value: float | None, minimum: float) -> bool:
    return value is not None and value >= minimum


def _at_most(value: float | None, maximum: float) -> bool:
    return value is not None and value <= maximum


def _differs(stated: float | None, expected: float | None) -> bool:
    """Say whether a stated measurement differs from the one recomputed from the other measurements."""

    if stated is None or expected is None:
        return stated is not expected
    return abs(stated - expected) > MEASUREMENT_TOLERANCE


def _own_candidate(record: Mapping[str, Any]) -> bool:
    """Say whether the (base) flood input of a confidence record is an own T2 candidate."""

    return record["tier"] == OWN_CANDIDATE_TIER or record["scenario_base"] == SCENARIO_BASE_OWN_CANDIDATE


def expected_temporal_relation(measurements: Mapping[str, Any], recency_window_days: float) -> str:
    """Return the temporal relation the two echoed dates give (protocol v1a ``date_rule``).

    An input is ``event_aligned`` only when its acquisition is within the
    recency window of the case reference date; the rule is strict. A dated
    input outside the window, or with no reference date to compare with, is
    ``dated_other``. An input with no single acquisition date is a
    ``season_window``.
    """

    if measurements["acquisition_date"] is None:
        return SEASON_WINDOW
    days = _recency_days(measurements["acquisition_date"], measurements["case_reference_date"])
    return EVENT_ALIGNED if _at_most(days, recency_window_days) else DATED_OTHER


def expected_basis(record: Mapping[str, Any]) -> dict[str, str]:
    """Recompute the basis of C1 to C8 from the measurements and thresholds a confidence record echoes.

    This is rule v1 (protocol v1a ``confidence_rule_v1``) applied to the
    record's own numbers: C1 from the tier and the T2 skill record, C2 from the
    two dates (or the scenario declaration for a tier T1 row), C3 to C8 from
    their measurements. A missing measurement fails its condition.
    """

    measurements, thresholds = record["measurements"], record["thresholds"]
    skill = record["t2_skill_condition"]
    tier = record["tier"]
    basis: dict[str, str] = {}
    if tier == AGENCY_TIER:
        basis["C1_tier"] = PASS
    elif skill is not None:
        basis["C1_tier"] = _met(skill["passes"] is True)
    else:
        basis["C1_tier"] = BY_SCENARIO_DECLARATION if tier == SCENARIO_TIER else FAIL
    if tier == SCENARIO_TIER:
        basis["C2_recency"] = BY_SCENARIO_DECLARATION
    else:
        days = _recency_days(measurements["acquisition_date"], measurements["case_reference_date"])
        basis["C2_recency"] = _met(_at_most(days, thresholds["recency_window_days"]))
    if measurements["coverage_by_construction"] is True:
        basis["C3_coverage"] = BY_CONSTRUCTION
    else:
        coverage_min = thresholds["unit_valid_coverage_min"]
        basis["C3_coverage"] = _met(_at_least(measurements["unit_valid_coverage"], coverage_min))
    plus, minus = measurements["exposure_plus_one_pixel_0_100"], measurements["exposure_minus_one_pixel_0_100"]
    points = None if plus is None or minus is None else abs(plus - minus)
    points_max = (
        thresholds["exposure_plus_minus_one_pixel_max_points"]
        + thresholds["exposure_plus_minus_one_pixel_float_guard_points"]
    )
    input_uncertainty = _at_most(points, points_max)
    if _own_candidate(record):
        abstention_max = thresholds["t2_abstention_fraction_max"]
        input_uncertainty = input_uncertainty and _at_most(measurements["t2_abstention_fraction"], abstention_max)
    basis["C4_input_uncertainty"] = _met(input_uncertainty)
    statuses = measurements["component_status"]
    basis["C5_components"] = _met(all(statuses[name] == COMPONENT_COMPUTED for name in SCORE_COMPONENTS))
    basis["C6_residents"] = _met(measurements["unit_residents"] >= thresholds["unit_residents_min"])
    no_route_max = thresholds["baseline_vehicle_no_route_share_max"]
    basis["C7_baseline_no_route"] = _met(_at_most(measurements["baseline_vehicle_no_route_share"], no_route_max))
    hospitals_min = thresholds["hospitals_reachable_at_baseline_min"]
    basis["C8_hospital"] = _met(_at_least(measurements["hospitals_reachable_at_baseline"], hospitals_min))
    return basis


def _skill_record_problems(record: Mapping[str, Any], where: str) -> list[OverlayProblem]:
    """Check the T2 skill record of an own candidate against the measurements it echoes (v1a ``t2_skill_bar``)."""

    problems: list[OverlayProblem] = []
    skill = record["t2_skill_condition"]
    measurements = record["measurements"]
    own_candidate = _own_candidate(record)

    def add(code: str, field: str, message: str) -> None:
        problems.append(OverlayProblem(code, f"{where}.confidence.{field}", message))

    if (skill is not None) != own_candidate:
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "t2_skill_condition",
            "an own candidate (tier T2, or the own-candidate base of a scenario) carries the T2 skill record, "
            "and no other row does",
        )
    if not own_candidate and measurements["t2_abstention_fraction"] is not None:
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "measurements.t2_abstention_fraction",
            "the T2 abstention fraction belongs to an own candidate only",
        )
    if skill is None:
        return problems
    measured, limits = skill["measurements"], skill["thresholds"]
    days = _recency_days(measurements["acquisition_date"], measurements["case_reference_date"])
    echoed = {
        "abstention_fraction": measurements["t2_abstention_fraction"],
        "unit_valid_coverage": measurements["unit_valid_coverage"],
        "recency_days": days,
    }
    for name, value in echoed.items():
        if _differs(measured[name], value):
            add(
                CONFIDENCE_RECORD_MISMATCH,
                f"t2_skill_condition.measurements.{name}",
                f"is {measured[name]!r}; the confidence record measures {value!r}",
            )
    if skill["flood_input"] != record["flood_input"]:
        add(CONFIDENCE_RECORD_MISMATCH, "t2_skill_condition.flood_input", "is not the flood input of the record")
    conditions = {
        "geoid_held_out_test_iou_min": _met(
            _at_least(measured["geoid_held_out_test_iou"], limits["geoid_held_out_test_iou_min"])
        ),
        "mae_sai_abstention_fraction_max": _met(
            _at_most(measured["abstention_fraction"], limits["mae_sai_abstention_fraction_max"])
        ),
        "mae_sai_unit_coverage_min": _met(
            _at_least(measured["unit_valid_coverage"], limits["mae_sai_unit_coverage_min"])
        ),
        "recency_window_days": _met(_at_most(measured["recency_days"], limits["recency_window_days"])),
    }
    failed = [name for name, value in conditions.items() if value == FAIL]
    if dict(skill["conditions"]) != conditions or list(skill["failed_conditions"]) != failed:
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "t2_skill_condition.conditions",
            f"the measurements of the skill record give {conditions}",
        )
    if skill["passes"] is not (skill["status"] == SKILL_EVALUATED and not failed):
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "t2_skill_condition.passes",
            "a T2 input passes only when the rule evaluates it and all four conditions pass",
        )
    return problems


def _derived_confidence_problems(
    overlay: Mapping[str, Any], row: Mapping[str, Any], where: str
) -> list[OverlayProblem]:
    """Check a derived confidence record against its row and against itself."""

    problems: list[OverlayProblem] = []
    record = row["confidence"]

    def add(code: str, field: str, message: str) -> None:
        problems.append(OverlayProblem(code, f"{where}.confidence.{field}", message))

    for name in ("unit_id", "lane", "tier", "flood_input"):
        if record[name] != row[name]:
            add(CONFIDENCE_RECORD_MISMATCH, name, f"is {record[name]!r}; the row says {row[name]!r}")
    if (record["scenario_base"] is not None) != (row["tier"] == SCENARIO_TIER):
        add(CONFIDENCE_RECORD_MISMATCH, "scenario_base", "a scenario base is named for tier T1 rows only")
    if record["lane"] == SEASON_ENVELOPE_LANE and record["scenario_base"] != SCENARIO_BASE_AGENCY:
        add(CONFIDENCE_RECORD_MISMATCH, "scenario_base", "lane SCN-ENV is the agency season layer, used as provided")
    if record["protocol_v1a_sha256"] != overlay["protocol_sha256"]["v1a"]:
        add(PROTOCOL_HASH_MISMATCH, "protocol_v1a_sha256", "differs from $.protocol_sha256.v1a")
    measurements = record["measurements"]
    thresholds = record["thresholds"]
    basis = record["basis"]
    days = _recency_days(measurements["acquisition_date"], measurements["case_reference_date"])
    if _differs(measurements["recency_days"], days):
        message = f"the two dates of the record are {days!r} days apart"
        add(CONFIDENCE_RECORD_MISMATCH, "measurements.recency_days", message)
    plus, minus = measurements["exposure_plus_one_pixel_0_100"], measurements["exposure_minus_one_pixel_0_100"]
    points = None if plus is None or minus is None else abs(plus - minus)
    if _differs(measurements["exposure_plus_minus_one_pixel_points"], points):
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "measurements.exposure_plus_minus_one_pixel_points",
            f"the two exposures of the record are {points!r} points apart",
        )
    if measurements["coverage_by_construction"] is True and _own_candidate(record):
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "measurements.coverage_by_construction",
            "coverage by construction is stated for an agency product, not for an own candidate",
        )
    problems.extend(_skill_record_problems(record, where))
    recomputed = expected_basis(record)
    for name in CONDITION_IDS:
        if basis[name] != recomputed[name]:
            add(
                CONFIDENCE_RECORD_MISMATCH,
                f"basis.{name}",
                f"is {basis[name]!r}; the measurements the record echoes give {recomputed[name]!r}",
            )
    failed = [name for name in CONDITION_IDS if basis[name] == FAIL]
    if record["failed_conditions"] != failed:
        add(CONFIDENCE_RECORD_MISMATCH, "failed_conditions", f"the basis record fails {failed}")
    expected_class = "low" if failed else "medium"
    if record["confidence_class"] != expected_class:
        add(CONFIDENCE_RECORD_MISMATCH, "confidence_class", f"the basis record gives {expected_class}")
    gr1 = record["guardrail_gr1"]
    applies = gr1["applies"]
    if applies != (measurements["unit_residents"] < gr1["unit_residents_min_for_class"]):
        add(GR1_NO_CLASS, "guardrail_gr1.applies", "does not follow from the unit residents")
    if any(gr1[name] != applies for name in ("no_binding_class", "no_would_be_class", "no_v2_class")):
        add(GR1_NO_CLASS, "guardrail_gr1", "no binding class, no would-be class and no v2 class go together")
    if applies and "C6_residents" not in failed:
        add(GR1_NO_CLASS, "failed_conditions", "a unit under guardrail GR1 fails condition C6")
    expected_reason = None
    if failed:
        expected_reason = REASON_LOW_CONFIDENCE
    if applies:
        expected_reason = REASON_INSUFFICIENT_DENOMINATOR
    if record["reason_code"] != expected_reason:
        add(CONFIDENCE_RECORD_MISMATCH, "reason_code", f"is {record['reason_code']!r}, expected {expected_reason!r}")
    statuses = measurements["component_status"]
    for name in SCORE_COMPONENTS:
        if statuses[name] == "assumed":
            problems.append(
                OverlayProblem(
                    ASSUMED_COMPONENT,
                    f"{where}.confidence.measurements.component_status.{name}",
                    "no case row and no scenario cell carries an assumed component (drafter reading DR-A05)",
                )
            )
        if (row["components"][name] is not None) != (statuses[name] == "computed"):
            problems.append(
                OverlayProblem(
                    COMPONENT_MISMATCH,
                    f"{where}.components.{name}",
                    f"the confidence record says {statuses[name]}; a record is present only for a computed component",
                )
            )
    if row["lane"] == OBSERVED_LANE and measurements["case_reference_date"] != overlay["case"]["case_reference_date"]:
        add(
            CONFIDENCE_RECORD_MISMATCH,
            "measurements.case_reference_date",
            "an OBS row is judged against the reference date of its case",
        )
    relation = expected_temporal_relation(measurements, thresholds["recency_window_days"])
    if row["lane"] == SEASON_ENVELOPE_LANE and relation != SEASON_WINDOW:
        problems.append(
            OverlayProblem(
                TEMPORAL_RELATION_MISMATCH,
                f"{where}.confidence.measurements.acquisition_date",
                "lane SCN-ENV is the season layer, which has no single acquisition date and is not a dated extent",
            )
        )
    if row["temporal_relation"] != relation:
        problems.append(
            OverlayProblem(
                TEMPORAL_RELATION_MISMATCH,
                f"{where}.temporal_relation",
                f"is {row['temporal_relation']!r}; the dates the row echoes give {relation!r}. An input is "
                "event_aligned only when its acquisition is inside the recency window, and one with no single "
                "acquisition date is a season_window",
            )
        )
    return problems


def _v2_problems(
    row: Mapping[str, Any],
    confidence_class: str,
    gr1_applies: bool,
    exposure: float | None,
    where: str,
) -> list[OverlayProblem]:
    """Check the secondary v2 axis: its order, its result and what the triggers say against the row.

    Protocol v1a ``class_rules.v2``: the triggers are evaluated in the order E,
    A, B, C, D and the first one met gives the class. Trigger E is met by low
    confidence, an exposure below 10 or an FPPS below 35; A needs the v1 class
    A; C needs an FPPS of at least 35 and medium (or scenario) confidence; D
    needs an FPPS of at least 35. The other inputs of A to D (the national P75,
    critical links, facilities, recurrence) are not in the overlay, so those
    triggers are checked one way only.
    """

    v2 = row["class_v2"]
    if gr1_applies:
        return []
    result = v2["result"]
    evidence = v2["trigger_evidence"]
    order = [item["trigger"] for item in evidence]
    met = [item["trigger"] for item in evidence if item["met"]]
    expected = met[0] if met else NO_V2_TRIGGER
    low = confidence_class == "low"
    fpps = row["fpps_0_100"]
    scored_enough = fpps is not None and fpps >= V2_FPPS_MIN
    wrong = []
    if order != list(V2_TRIGGER_ORDER):
        wrong.append(f"trigger_evidence lists {order}, not {list(V2_TRIGGER_ORDER)}")
    else:
        if result != expected:
            wrong.append(f"result is {result!r}; the first trigger met gives {expected!r}")
        trigger_e = low or not scored_enough or (exposure is not None and exposure < V2_EXPOSURE_FLOOR_FOR_NON_E)
        if ("E" in met) != trigger_e:
            wrong.append(
                f"trigger E is {'met' if trigger_e else 'not met'} for this row: low confidence, exposure below "
                f"{V2_EXPOSURE_FLOOR_FOR_NON_E:g} or FPPS below {V2_FPPS_MIN:g}"
            )
        if "A" in met and row["action_class"] != "A":
            wrong.append("trigger A needs the v1 class A")
        if "C" in met and (not scored_enough or low):
            wrong.append(f"trigger C needs an FPPS of at least {V2_FPPS_MIN:g} and medium confidence")
        if "D" in met and not scored_enough:
            wrong.append(f"trigger D needs an FPPS of at least {V2_FPPS_MIN:g}")
    if low and result != "E":
        wrong.append("low confidence gives v2 class E")
    return [OverlayProblem(V2_RESULT_INCONSISTENT, f"{where}.class_v2", "; ".join(wrong))] if wrong else []


def _score(
    values: Mapping[str, float | None], confidence_class: str, weights: Mapping[str, float]
) -> tuple[float, str, str]:
    """Return FPPS, v1 class and reason code of one row from ``scoring.score_subdistricts`` (unchanged)."""

    return _scored(
        tuple(float(values[name]) for name in SCORE_COMPONENTS),  # type: ignore[arg-type]
        confidence_class,
        tuple(float(weights[name]) for name in SCORE_COMPONENTS),
    )


@lru_cache(maxsize=4096)
def _scored(values: tuple[float, ...], confidence_class: str, weights: tuple[float, ...]) -> tuple[float, str, str]:
    """One call of the scorer. It is a pure function of its arguments, so equal calls are answered once."""

    row = {"subdistrict_id": "row", "subdistrict_name": "row", "confidence_class": confidence_class}
    table = pd.DataFrame([{**row, **dict(zip(SCORE_COMPONENTS, values))}])
    scored = score_subdistricts(table, dict(zip(SCORE_COMPONENTS, weights))).iloc[0]
    return float(scored["fpps_0_100"]), str(scored["action_class"]), str(scored["action_reason_code"])


# ---------------------------------------------------------------------------
# Checks that need the protocol files in force
# ---------------------------------------------------------------------------


def _binding_problems(overlay: Mapping[str, Any], binding: ProtocolBinding) -> list[OverlayProblem]:
    """Recompute every record from the inputs it echoes, under the protocols in force."""

    problems: list[OverlayProblem] = []
    hashes = protocol_hashes(binding.frame)
    if dict(overlay["protocol_sha256"]) != hashes:
        problems.append(
            OverlayProblem(
                PROTOCOL_NOT_IN_FORCE, "$.protocol_sha256", "is not the SHA-256 of the protocol files in force"
            )
        )
    if overlay["scoring_frame"] != frame_record(binding.frame):
        problems.append(
            OverlayProblem(
                FRAME_NOT_PROTOCOL_FRAME, "$.scoring_frame", "is not the frame v1 header of the protocols in force"
            )
        )
    for index, row in enumerate(overlay["rows"]):
        where = f"$.rows[{index}]"
        records = {
            name: record
            for name, record in row["components"].items()
            if isinstance(record, Mapping) and record.get("synthetic") is not True
        }
        if records:
            check_row = {
                "unit_id": row["unit_id"],
                "normalisation_version": row["normalisation_version"],
                "components": records,
            }
            try:
                reject_batch_scaled_components(binding.frame, [check_row], components=list(records))
            except NormalisationError as error:
                problems.append(OverlayProblem(COMPONENT_NOT_FRAME_RECORD, f"{where}.components", str(error)[:300]))
        record = row["confidence"]
        if not isinstance(record, Mapping) or record.get("confidence_kind") == KIND_DECLARED:
            continue
        try:
            inputs = _confidence_inputs(record)
        except ValueError as error:
            message = f"not a calendar date: {error}"
            problems.append(OverlayProblem(STRUCTURE, f"{where}.confidence.measurements", message))
            continue
        try:
            derived = derive_confidence(inputs, binding.rule)
        except ConfidenceError as error:
            problems.append(OverlayProblem(CONFIDENCE_NOT_RULE_RECORD, f"{where}.confidence", str(error)[:300]))
            continue
        differing = sorted(key for key in {*derived, *record} if derived.get(key) != record.get(key))
        if differing:
            problems.append(
                OverlayProblem(
                    CONFIDENCE_NOT_RULE_RECORD,
                    f"{where}.confidence",
                    f"rule v1 derives other values from the echoed measurements: {differing}",
                )
            )
    return problems


def _confidence_inputs(record: Mapping[str, Any]) -> ConfidenceInputs:
    """Rebuild the inputs of rule v1 from the measurements a confidence record echoes."""

    measurements = record["measurements"]
    skill = record["t2_skill_condition"]
    hospitals = measurements["hospitals_reachable_at_baseline"]
    return ConfidenceInputs(
        unit_id=record["unit_id"],
        lane=record["lane"],
        tier=record["tier"],
        flood_input=record["flood_input"],
        scenario_base=record["scenario_base"],
        acquisition_date=_date(measurements["acquisition_date"]),
        case_reference_date=_date(measurements["case_reference_date"]),
        unit_valid_coverage=measurements["unit_valid_coverage"],
        coverage_by_construction=measurements["coverage_by_construction"],
        exposure_plus_one_pixel_0_100=measurements["exposure_plus_one_pixel_0_100"],
        exposure_minus_one_pixel_0_100=measurements["exposure_minus_one_pixel_0_100"],
        t2_abstention_fraction=measurements["t2_abstention_fraction"],
        t2_geoid_held_out_test_iou=None if skill is None else skill["measurements"]["geoid_held_out_test_iou"],
        component_status=measurements["component_status"],
        unit_residents=measurements["unit_residents"],
        baseline_vehicle_no_route_share=measurements["baseline_vehicle_no_route_share"],
        hospitals_reachable_at_baseline=hospitals,
    )


def case_flood_input_names(case: ProtocolCase, layers: Product4009Layers) -> tuple[str, ...]:
    """Return every name protocol v1a gives the flood inputs of a case.

    They are the ``flood_inputs`` of the case and, for a case built on a
    product 4009 layer, the names of that layer.
    """

    names = list(case.flood_inputs)
    for layer_names in (layers.accumulated_names, layers.dated_names):
        if set(names) & set(layer_names):
            names.extend(layer_names)
    return tuple(dict.fromkeys(names))


def _case_problems(overlay: Mapping[str, Any], binding: ProtocolBinding) -> list[OverlayProblem]:
    """Compare the case header and the rows of its own lane with protocol v1a ``case_portfolio``.

    A portfolio case names a case of v1a and carries the reference date v1a
    gives it. A row in lane OBS or SCN-ENV belongs to a case of that lane,
    carries the tier of the case and one of its flood inputs. Rows in lane SCN
    (scenario cells built on a base case), engine rows and the T4 placeholder
    are not compared: the protocols do not say which overlay carries them.
    """

    problems: list[OverlayProblem] = []
    case = overlay["case"]
    case_id = case["case_id"]
    known = binding.cases.get(case_id)

    def add(code: str, path: str, message: str) -> None:
        problems.append(OverlayProblem(code, path, message))

    if case["kind"] != PORTFOLIO_KIND:
        if known is not None or case_id in binding.cut_cases:
            message = f"a fixture does not carry the id of protocol case {case_id!r}"
            add(CASE_NOT_PROTOCOL_CASE, "$.case.case_id", message)
        return problems
    if known is None:
        cut = ", which v1a cut (case_portfolio.cut_now)" if case_id in binding.cut_cases else ""
        add(CASE_NOT_PROTOCOL_CASE, "$.case.case_id", f"{case_id!r}{cut} is not a case of protocol v1a case_portfolio")
        return problems
    if case_id in CASES_WITHOUT_CLASS:
        add(
            CASE_NOT_PROTOCOL_CASE,
            "$.case.case_id",
            f"v1a gives case {case_id} flood likelihood and exposure only, no FPPS and no class; schema "
            f"{SCHEMA_VERSION} does not carry it",
        )
        return problems
    if case["case_reference_date"] != known.case_reference_date:
        add(
            CASE_NOT_PROTOCOL_CASE,
            "$.case.case_reference_date",
            f"is {case['case_reference_date']!r}; v1a gives case {case_id} {known.case_reference_date!r}",
        )
    names = case_flood_input_names(known, binding.product_4009)
    for index, row in enumerate(overlay["rows"]):
        lane = row["lane"]
        if lane not in (OBSERVED_LANE, SEASON_ENVELOPE_LANE):
            continue
        where = f"$.rows[{index}]"
        if lane != known.lane:
            message = f"v1a gives case {case_id} lane {known.lane}, not a {lane} row"
            add(CASE_NOT_PROTOCOL_CASE, f"{where}.lane", message)
            continue
        if row["tier"] != known.tier:
            add(CASE_NOT_PROTOCOL_CASE, f"{where}.tier", f"v1a places case {case_id} at tier {known.tier}")
        if row["flood_input"] not in names:
            add(
                CASE_NOT_PROTOCOL_CASE,
                f"{where}.flood_input",
                f"{row['flood_input']!r} is not a flood input v1a gives case {case_id}: {list(names)}",
            )
    return problems


def _product_4009_layer_problems(overlay: Mapping[str, Any], binding: ProtocolBinding) -> list[OverlayProblem]:
    """Bind a product 4009 flood input to the layer protocol v1a names (``date_rule.product_4009``).

    The accumulated layer has no single acquisition date and is used in lane
    SCN-ENV only; the 22 Oct layer carries its own date. A flood input that
    declares the product therefore carries one of the names v1a gives the two
    layers, so its date cannot be restated.
    """

    problems: list[OverlayProblem] = []
    layers = binding.product_4009
    accumulated_ids: set[str] = set()

    def add(code: str, path: str, message: str) -> None:
        problems.append(OverlayProblem(code, path, message))

    for index, item in enumerate(overlay["inputs"]):
        if item["role"] != FLOOD_INPUT_ROLE or not _declares_product_4009(item):
            continue
        where = f"$.inputs[{index}]"
        if item["name"] in layers.accumulated_names:
            accumulated_ids.add(item["input_id"])
            if item["acquisition_date"] is not None:
                add(
                    PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER,
                    f"{where}.acquisition_date",
                    "the accumulated layer has no per-patch dates: it has no single acquisition date",
                )
        elif item["name"] in layers.dated_names:
            if item["acquisition_date"] != layers.dated_acquisition_date:
                add(
                    PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER,
                    f"{where}.acquisition_date",
                    f"v1a dates the 22 Oct layer {layers.dated_acquisition_date}",
                )
        else:
            known = [*layers.accumulated_names, *layers.dated_names]
            add(
                PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER,
                f"{where}.name",
                f"a product 4009 flood input carries one of the names v1a gives its two layers: {known}",
            )
    for index, row in enumerate(overlay["rows"]):
        if row["lineage"]["flood_input_id"] in accumulated_ids and row["lane"] != SEASON_ENVELOPE_LANE:
            add(
                PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER,
                f"$.rows[{index}].lane",
                "v1a uses the accumulated layer in lane SCN-ENV only (scenario only)",
            )
    return problems


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def overlay_text(
    overlay: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
) -> str:
    """Return the file text of an accepted overlay: ASCII JSON, two-space indent, one final line feed.

    Raises:
        PlanningOverlayError: when the overlay is refused. A refused overlay is never serialised.
    """

    validate_overlay(overlay, schema, binding=binding)
    return json.dumps(overlay, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def is_public_web_path(path: Path | str) -> bool:
    """Say whether ``path`` lies under a web public folder (``apps/web/public``).

    The path is judged as written (with every ``..`` collapsed) and as the
    file system resolves it (links and junctions followed). Either one under
    ``apps/web/public`` makes it a public path.
    """

    target = Path(path)
    width = len(PUBLIC_WEB_ROOT)
    forms = (Path(os.path.normpath(target.absolute())), target.resolve())
    for form in forms:
        parts = [part.lower() for part in form.parts]
        if any(tuple(parts[start : start + width]) == PUBLIC_WEB_ROOT for start in range(len(parts) - width + 1)):
            return True
    return False


def write_overlay(
    overlay: Mapping[str, Any],
    path: Path | str,
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
    rights_basis_4009: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an overlay and write it; return the path, byte count and SHA-256 written.

    Guardrail GR6: only an overlay whose ``publication_eligibility`` is
    ``public`` may be written under ``apps/web/public``, and every flood input
    of such an overlay declares its source product. An overlay with
    UNOSAT/GISTDA product 4009 in its lineage is written there only when
    ``rights_basis_4009`` is the rights record and the owners have confirmed it
    (``floodguard.rights_basis``). A candidate overlay is written nowhere
    without ``binding``.

    Raises:
        PlanningOverlayError: when the overlay is refused or may not be written to ``path``.
    """

    text = overlay_text(overlay, schema, binding=binding)
    target = Path(path)
    if is_public_web_path(target):
        if overlay["publication_eligibility"] != "public":
            raise PlanningOverlayError(
                [
                    OverlayProblem(
                        PUBLIC_WRITE_NOT_ELIGIBLE,
                        "$.publication_eligibility",
                        f"{overlay['publication_eligibility']!r}: "
                        "only public overlays are written under apps/web/public",
                    )
                ]
            )
        undeclared = [
            OverlayProblem(
                PUBLIC_WRITE_NOT_ELIGIBLE,
                f"$.inputs[{index}].source_product",
                "a flood input of an overlay written under apps/web/public declares its source product",
            )
            for index, item in enumerate(overlay["inputs"])
            if item["role"] == FLOOD_INPUT_ROLE and item["source_product"] is None
        ]
        if undeclared:
            raise PlanningOverlayError(undeclared)
        if cites_product_4009(overlay):
            try:
                if rights_basis_4009 is None:
                    raise RightsBasisError("no rights record was given")
                require_owner_confirmation(rights_basis_4009)
            except RightsBasisError as error:
                raise PlanningOverlayError(
                    [OverlayProblem(PRODUCT_4009_RIGHTS_NOT_CONFIRMED, "$.inputs", str(error))]
                ) from error
    data = text.encode("ascii")
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


# ---------------------------------------------------------------------------
# Content digest and summary (the web parser computes the same two)
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Serialise ``value`` the same way in Python and in JavaScript.

    Object keys are sorted, there is no white space, text is not ASCII-escaped,
    and a number is written as ECMAScript writes it (``15`` for 15.0, ``1e-9``
    for 1e-09), so the SHA-256 of the result is the same on both sides.

    Raises:
        PlanningOverlayError: for a number that is not finite or a value that is not JSON.
    """

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _ecmascript_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Mapping):
        items = (f"{json.dumps(str(key), ensure_ascii=False)}:{canonical_json(value[key])}" for key in sorted(value))
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", f"{type(value).__name__} is not a JSON value")])


def _ecmascript_number(value: float) -> str:
    """Write a float as ECMAScript ``Number::toString`` does (shortest digits that round-trip)."""

    if not math.isfinite(value):
        raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", "a number is not finite")])
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    _sign, digit_tuple, exponent = Decimal(repr(abs(value))).as_tuple()
    digits = "".join(str(digit) for digit in digit_tuple).lstrip("0")
    stripped = digits.rstrip("0")
    exponent = int(exponent) + len(digits) - len(stripped)
    count = len(stripped)
    point = count + exponent
    if count <= point <= 21:
        return sign + stripped + "0" * (point - count)
    if 0 < point <= 21:
        return f"{sign}{stripped[:point]}.{stripped[point:]}"
    if -6 < point <= 0:
        return f"{sign}0.{'0' * -point}{stripped}"
    power = point - 1
    mantissa = stripped if count == 1 else f"{stripped[0]}.{stripped[1:]}"
    return f"{sign}{mantissa}e{'+' if power >= 0 else '-'}{abs(power)}"


def content_sha256(overlay: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical JSON of ``overlay``: a digest of its content, not of its file bytes."""

    return hashlib.sha256(canonical_json(overlay).encode("utf-8")).hexdigest()


def lane_column(lane: str | None) -> str:
    """Return the column a row is counted in: OBS, SCN (with SCN-ENV), ENG, or ``no_lane`` for tier T4."""

    if lane is None:
        return NO_LANE_COLUMN
    return SCENARIO_COLUMN if lane in SCENARIO_LANES else lane


def _counts(keys: Iterable[str], values: Iterable[Any]) -> dict[str, int]:
    """Count ``values`` under ``keys``; None is counted as ``none``."""

    out = {key: 0 for key in (*keys, "none")}
    for value in values:
        out["none" if value is None else str(value)] += 1
    return out


def _counts_by_column(
    rows: Iterable[Mapping[str, Any]],
    keys: Iterable[str],
    value: Callable[[Mapping[str, Any]], Any],
    columns: tuple[str, ...] = LANE_COLUMNS,
) -> dict[str, dict[str, int]]:
    """Count one value of each row, separately for each lane column."""

    keys = tuple(keys)
    rows = list(rows)
    return {
        column: _counts(keys, (value(row) for row in rows if lane_column(row["lane"]) == column))
        for column in columns
    }


def summarise_overlay(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Count what an accepted overlay holds: rows by tier and lane, and classes and confidence per lane column.

    Classes, reason codes and confidence are counted per lane column (OBS, SCN
    with SCN-ENV, ENG, and ``no_lane`` for tier T4) and never across them:
    protocol v1a counts scenario classes only in the SCN column, never counts
    engine classes as an observed or scenario distribution, and never counts
    scenario confidence as observed confidence.

    The web parser computes the same summary from the same file, so a test on
    each side can show that both read the same content.
    """

    rows = overlay["rows"]
    derived_rows = [
        row for row in rows if row["confidence"] is not None and row["confidence"]["confidence_kind"] != KIND_DECLARED
    ]
    failed = {column: {name: 0 for name in CONDITION_IDS} for column in DERIVED_COLUMNS}
    basis_values = (PASS, FAIL, BY_CONSTRUCTION, BY_SCENARIO_DECLARATION)
    basis = {column: {name: 0 for name in basis_values} for column in DERIVED_COLUMNS}
    for row in derived_rows:
        column = lane_column(row["lane"])
        for name in row["confidence"]["failed_conditions"]:
            failed[column][name] += 1
        for value in row["confidence"]["basis"].values():
            basis[column][value] += 1

    def confidence_of(name: str) -> Callable[[Mapping[str, Any]], Any]:
        return lambda row: None if row["confidence"] is None else row["confidence"][name]

    return {
        "case_id": overlay["case"]["case_id"],
        "dataset_mode": overlay["dataset_mode"],
        "publication_eligibility": overlay["publication_eligibility"],
        "protocol_sha256": dict(overlay["protocol_sha256"]),
        "row_count": len(rows),
        "unit_count": len({row["unit_id"] for row in rows}),
        "rows_by_tier": _counts(TIERS, (row["tier"] for row in rows)),
        "rows_by_lane": _counts(LANES, (row["lane"] for row in rows)),
        "rows_by_temporal_relation": _counts(TEMPORAL_RELATIONS, (row["temporal_relation"] for row in rows)),
        "rows_by_confidence_kind": _counts(
            ("observed", "scenario", KIND_DECLARED), map(confidence_of("confidence_kind"), rows)
        ),
        "confidence_class_by_lane_column": _counts_by_column(
            rows, ("low", "medium"), confidence_of("confidence_class")
        ),
        "binding_class_by_lane_column": _counts_by_column(rows, ACTION_CLASSES, lambda row: row["action_class"]),
        "reason_code_by_lane_column": _counts_by_column(rows, REASON_CODES, lambda row: row["action_reason_code"]),
        "would_be_class_by_lane_column": _counts_by_column(rows, ACTION_CLASSES, lambda row: row["would_be_class"]),
        "v2_result_by_lane_column": _counts_by_column(
            rows,
            (*ACTION_CLASSES, NO_V2_TRIGGER),
            lambda row: None if row["class_v2"] is None else row["class_v2"]["result"],
        ),
        "headline_status_by_lane_column": _counts_by_column(
            rows,
            (HEADLINE_NOT_EVALUATED, HEADLINE_ELIGIBLE, HEADLINE_UNSTABLE),
            lambda row: row["headline_stability"]["status"],
        ),
        "failed_conditions_by_lane_column": failed,
        "basis_values_by_lane_column": basis,
        "rows_under_gr1": sum(1 for row in derived_rows if row["confidence"]["guardrail_gr1"]["applies"]),
        "rows_without_fpps": sum(1 for row in rows if row["fpps_0_100"] is None),
        "obs_rows_not_event_aligned": sum(
            1 for row in rows if row["lane"] == OBSERVED_LANE and row["temporal_relation"] != EVENT_ALIGNED
        ),
        "inputs_by_rights_level": _counts(PUBLICATION_LEVELS, (item["rights_level"] for item in overlay["inputs"])),
        "content_sha256": content_sha256(overlay),
    }
