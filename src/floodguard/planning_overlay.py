"""Planning assessment overlay: strict validator, loader and writer (plan 7.1, task E11).

The overlay is the file the planning engine writes for one case and every
screen reads: one row per unit, lane and flood input. Its shape is
``packages/contracts/schemas/planning-assessment-overlay.schema.json``. This
module adds what a JSON schema cannot say, and names every refusal with a code
that the web parser (``apps/web/src/lib/planning-assessment-overlay.ts``) uses
too:

* the invariants of protocol v1a at every tier: not an official warning,
  non-operational, ``accepted_fpps`` and ``accepted_action_class`` null, no
  class above E without medium confidence, high confidence never assigned;
* guardrail GR1 (fewer than 100 residents: no binding class, no would-be class,
  no v2 class, reason ``insufficient_denominator``), GR7 (temporal honesty), GR8
  (the headline-stability slot), GR6 (the rights level of an overlay is the
  minimum across its lineage) and GR3 (one flood input, one routing context and
  one closure rule per row);
* the arithmetic the row states about itself, recomputed with
  ``scoring.score_subdistricts``: FPPS, the binding v1 class and its reason
  code, the would-be class (the scorer rerun with confidence medium, never
  binding) and leave-one-component-out;
* with a :class:`ProtocolBinding` (the frame and the confidence rule read from
  the two protocol files in force): every component record is the frame v1
  record of the inputs it echoes (guardrail GR2), every confidence record is
  what rule v1 derives from the measurements it echoes, and the hashes are those
  of the files in force.

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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.confidence import (
    CONDITION_IDS,
    ENGINE_LANE,
    FAIL,
    OBSERVED_LANE,
    REASON_INSUFFICIENT_DENOMINATOR,
    REASON_LOW_CONFIDENCE,
    SCENARIO_LANES,
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
LANES: tuple[str, ...] = (OBSERVED_LANE, *SCENARIO_LANES, ENGINE_LANE)
# Protocol v1a evidence_tier_model.tiers: the lanes a row of each tier may carry. T4 has no lane.
TIER_LANES: dict[str, tuple[str | None, ...]] = {
    "T0": (ENGINE_LANE,),
    "T1": SCENARIO_LANES,
    "T2": (OBSERVED_LANE,),
    "T3": (OBSERVED_LANE,),
    "T4": (None,),
}
EVENT_ALIGNED = "event_aligned"
TEMPORAL_RELATIONS: tuple[str, ...] = (EVENT_ALIGNED, "dated_other", "season_window")
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
HEADLINE_NOT_EVALUATED = "not_evaluated"
HEADLINE_ELIGIBLE = "headline_eligible"
HEADLINE_UNSTABLE = "unstable_verify"
FIXTURE_MODE = "fixture_demo"
FIXTURE_LABEL = "not a place"
PRODUCT_4009_LICENCE = "CC BY-SA 4.0"
PRODUCT_4009_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
"""Protocol v1a wording.product_4009_credit; the rights record carries the same text."""
PUBLIC_WEB_ROOT: tuple[str, ...] = ("apps", "web", "public")
FPPS_TOLERANCE = 1e-9
WEIGHT_SUM_TOLERANCE = 1e-9

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
PROTOCOL_HASH_MISMATCH = "protocol_hash_mismatch"
SCORING_FRAME_INCONSISTENT = "scoring_frame_inconsistent"
DUPLICATE_ID = "duplicate_id"
FIXTURE_LABEL_MISSING = "fixture_label_missing"
PROTOCOL_NOT_IN_FORCE = "protocol_not_in_force"
FRAME_NOT_PROTOCOL_FRAME = "frame_not_protocol_frame"
COMPONENT_NOT_FRAME_RECORD = "component_not_frame_record"
CONFIDENCE_NOT_RULE_RECORD = "confidence_not_rule_record"
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
    PROTOCOL_HASH_MISMATCH,
    SCORING_FRAME_INCONSISTENT,
    DUPLICATE_ID,
    FIXTURE_LABEL_MISSING,
    PROTOCOL_NOT_IN_FORCE,
    FRAME_NOT_PROTOCOL_FRAME,
    COMPONENT_NOT_FRAME_RECORD,
    CONFIDENCE_NOT_RULE_RECORD,
    PUBLIC_WRITE_NOT_ELIGIBLE,
    PRODUCT_4009_RIGHTS_NOT_CONFIRMED,
)
"""Every refusal code this module gives."""

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


@dataclass(frozen=True)
class ProtocolBinding:
    """The frame and the confidence rule read from the two protocol files in force."""

    frame: PlanningFrame
    rule: ConfidenceRule


def load_protocol_binding(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> ProtocolBinding:
    """Read frame v1 and confidence rule v1 from the protocol files, which must both be in force.

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not in force.
        floodguard.confidence.ConfidenceError: when v1a does not hold rule v1.
    """

    return ProtocolBinding(
        frame=load_planning_frame(v1a_path, v1b_path, receipts_path),
        rule=load_confidence_rule(v1a_path, receipts_path),
    )


def load_overlay_schema(path: Path | str) -> dict[str, Any]:
    """Read the overlay JSON schema from ``path`` (see ``SCHEMA_RELATIVE_PATH``)."""

    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(schema, dict) or schema.get("$id") != SCHEMA_ID:
        raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", f"the schema file is not {SCHEMA_ID}")])
    return schema


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------


def schema_problems(overlay: Any, schema: Mapping[str, Any]) -> list[OverlayProblem]:
    """Return the JSON-schema violations of ``overlay`` as ``structure`` problems, sorted by path."""

    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    found = [
        OverlayProblem(STRUCTURE, _json_path(error.absolute_path), error.message[:300])
        for error in validator.iter_errors(overlay)
    ]
    return sorted(found, key=lambda item: (item.path, item.message))


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
            inputs they echo and the hashes are compared with the files in force.
    """

    if not isinstance(overlay, Mapping):
        return [OverlayProblem(STRUCTURE, "$", "the overlay must be a JSON object")]
    structure = schema_problems(overlay, schema)
    problems = [*_guard_problems(overlay), *structure]
    checks: list[Callable[[], list[OverlayProblem]]] = [lambda: _overlay_level_problems(overlay)]
    rows = overlay.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            checks.append(lambda row=row, index=index: _row_problems(overlay, row, f"$.rows[{index}]"))
    if binding is not None:
        checks.append(lambda: _binding_problems(overlay, binding))
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


def load_overlay(
    path: Path | str,
    schema: Mapping[str, Any],
    *,
    binding: ProtocolBinding | None = None,
) -> dict[str, Any]:
    """Read an overlay file and return it only when it is accepted.

    Raises:
        PlanningOverlayError: when the file is not a JSON object or is refused.
    """

    try:
        overlay = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PlanningOverlayError([OverlayProblem(STRUCTURE, "$", f"not valid JSON: {error.msg}")]) from error
    validate_overlay(overlay, schema, binding=binding)
    return overlay


def _json_path(parts: Iterable[Any]) -> str:
    """Return a path like ``rows[3].confidence.basis`` from the parts jsonschema reports."""

    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _guard_problems(overlay: Mapping[str, Any]) -> list[OverlayProblem]:
    """The refusals that must be named whatever else is wrong; they assume nothing about the shape."""

    problems: list[OverlayProblem] = []
    if overlay.get("official_warning") is not False:
        problems.append(OverlayProblem(OFFICIAL_WARNING_NOT_FALSE, "$.official_warning", "must be false"))
    if overlay.get("operational_status") != "non_operational":
        problems.append(OverlayProblem(NOT_NON_OPERATIONAL, "$.operational_status", "must be non_operational"))
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
    for name, values in (
        ("input_id", [item["input_id"] for item in inputs]),
        ("row_id", [row["row_id"] for row in overlay["rows"]]),
    ):
        repeated = sorted({value for value in values if values.count(value) > 1})
        if repeated:
            problems.append(OverlayProblem(DUPLICATE_ID, "$", f"{name} repeated: {repeated}"))
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
    for index, row in enumerate(overlay["rows"]):
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
        if not _cites_product_4009(item):
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
        unlabelled = [row["row_id"] for row in overlay["rows"] if FIXTURE_LABEL not in row["unit_name_en"]]
        if unlabelled:
            problems.append(
                OverlayProblem(
                    FIXTURE_LABEL_MISSING, "$.rows", f"fixture units are named '{FIXTURE_LABEL}': {unlabelled}"
                )
            )
    return problems


def _cites_product_4009(item: Mapping[str, Any]) -> bool:
    """Say whether an input record names product 4009 in its name, attribution or identifier."""

    return any(
        isinstance(item.get(key), str) and PRODUCT_4009_CITATION.search(item[key])
        for key in ("input_id", "name", "attribution")
    )


def cites_product_4009(overlay: Mapping[str, Any]) -> bool:
    """Say whether any input in the lineage of ``overlay`` is UNOSAT/GISTDA product 4009."""

    return any(_cites_product_4009(item) for item in overlay.get("inputs", ()) if isinstance(item, Mapping))


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
        if flood is None or flood["role"] != "flood_input" or flood["name"] != row["flood_input"]:
            add(LINEAGE_UNRESOLVED, "lineage.flood_input_id", "does not name the flood input of the row")
        routing = inputs.get(lineage["routing_context_id"])
        if routing is None or routing["role"] != "routing_context":
            add(LINEAGE_UNRESOLVED, "lineage.routing_context_id", "does not name a routing context")

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
            add(GR1_NO_CLASS, "action_class", "only a unit under guardrail GR1 has no class")
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
        problems.extend(_v2_problems(row, confidence_class, gr1_applies, where))
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
    if record["protocol_v1a_sha256"] != overlay["protocol_sha256"]["v1a"]:
        add(PROTOCOL_HASH_MISMATCH, "protocol_v1a_sha256", "differs from $.protocol_sha256.v1a")
    basis = record["basis"]
    failed = [name for name in CONDITION_IDS if basis[name] == FAIL]
    if record["failed_conditions"] != failed:
        add(CONFIDENCE_RECORD_MISMATCH, "failed_conditions", f"the basis record fails {failed}")
    expected_class = "low" if failed else "medium"
    if record["confidence_class"] != expected_class:
        add(CONFIDENCE_RECORD_MISMATCH, "confidence_class", f"the basis record gives {expected_class}")
    gr1 = record["guardrail_gr1"]
    applies = gr1["applies"]
    measurements = record["measurements"]
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
    if row["lane"] == OBSERVED_LANE and (row["temporal_relation"] == EVENT_ALIGNED) != (basis["C2_recency"] == "pass"):
        problems.append(
            OverlayProblem(
                TEMPORAL_RELATION_MISMATCH,
                f"{where}.temporal_relation",
                "an input is event_aligned only when its acquisition is inside the recency window (condition C2)",
            )
        )
    return problems


def _v2_problems(row: Mapping[str, Any], confidence_class: str, gr1_applies: bool, where: str) -> list[OverlayProblem]:
    """Check the secondary v2 axis: evaluation order E, A, B, C, D; first trigger met gives the class."""

    v2 = row["class_v2"]
    if gr1_applies:
        return []
    result = v2["result"]
    evidence = v2["trigger_evidence"]
    order = [item["trigger"] for item in evidence]
    met = [item["trigger"] for item in evidence if item["met"]]
    expected = met[0] if met else NO_V2_TRIGGER
    wrong = []
    if order != list(V2_TRIGGER_ORDER):
        wrong.append(f"trigger_evidence lists {order}, not {list(V2_TRIGGER_ORDER)}")
    elif result != expected:
        wrong.append(f"result is {result!r}; the first trigger met gives {expected!r}")
    if confidence_class == "low" and result != "E":
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
            derived = derive_confidence(_confidence_inputs(record), binding.rule)
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


def _date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


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
    """Say whether ``path`` lies under a web public folder (``apps/web/public``)."""

    parts = [part.lower() for part in Path(path).absolute().parts]
    width = len(PUBLIC_WEB_ROOT)
    return any(tuple(parts[start : start + width]) == PUBLIC_WEB_ROOT for start in range(len(parts) - width + 1))


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
    ``public`` may be written under ``apps/web/public``. An overlay with
    UNOSAT/GISTDA product 4009 in its lineage is written there only when
    ``rights_basis_4009`` is the rights record and the owners have confirmed it
    (``floodguard.rights_basis``).

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


def _counts(keys: Iterable[str], values: Iterable[Any]) -> dict[str, int]:
    """Count ``values`` under ``keys``; None is counted as ``none``."""

    out = {key: 0 for key in (*keys, "none")}
    for value in values:
        out["none" if value is None else str(value)] += 1
    return out


def summarise_overlay(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Count what an accepted overlay holds: rows by tier, lane, class, reason code and guardrail outcome.

    The web parser computes the same summary from the same file, so a test on
    each side can show that both read the same content.
    """

    rows = overlay["rows"]
    confidences = [row["confidence"] for row in rows]
    derived = [record for record in confidences if record is not None and record["confidence_kind"] != KIND_DECLARED]
    failed = {name: 0 for name in CONDITION_IDS}
    basis = {name: 0 for name in ("pass", "fail", "by_construction", "by_scenario_declaration")}
    for record in derived:
        for name in record["failed_conditions"]:
            failed[name] += 1
        for value in record["basis"].values():
            basis[value] += 1
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
        "rows_by_confidence_class": _counts(
            ("low", "medium"), (None if record is None else record["confidence_class"] for record in confidences)
        ),
        "rows_by_confidence_kind": _counts(
            ("observed", "scenario", KIND_DECLARED),
            (None if record is None else record["confidence_kind"] for record in confidences),
        ),
        "rows_by_binding_class": _counts(ACTION_CLASSES, (row["action_class"] for row in rows)),
        "rows_by_reason_code": _counts(REASON_CODES, (row["action_reason_code"] for row in rows)),
        "rows_by_would_be_class": _counts(ACTION_CLASSES, (row["would_be_class"] for row in rows)),
        "rows_by_v2_result": _counts(
            (*ACTION_CLASSES, NO_V2_TRIGGER),
            (None if row["class_v2"] is None else row["class_v2"]["result"] for row in rows),
        ),
        "rows_by_headline_status": _counts(
            (HEADLINE_NOT_EVALUATED, HEADLINE_ELIGIBLE, HEADLINE_UNSTABLE),
            (row["headline_stability"]["status"] for row in rows),
        ),
        "failed_condition_counts": failed,
        "basis_value_counts": basis,
        "rows_under_gr1": sum(1 for record in derived if record["guardrail_gr1"]["applies"]),
        "rows_without_fpps": sum(1 for row in rows if row["fpps_0_100"] is None),
        "obs_rows_not_event_aligned": sum(
            1 for row in rows if row["lane"] == OBSERVED_LANE and row["temporal_relation"] != EVENT_ALIGNED
        ),
        "inputs_by_rights_level": _counts(PUBLICATION_LEVELS, (item["rights_level"] for item in overlay["inputs"])),
        "content_sha256": content_sha256(overlay),
    }
