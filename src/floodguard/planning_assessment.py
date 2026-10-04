"""Planning assessment: the rows of one case, assembled, written and verified (plan task E8).

Restructuring plan v2, sections 3.1 (stages P5, P6 and P8), 3.3 to 3.5, 5 and 7.1. For one case of protocol v1a
and its reporting units this module assembles what the overlay schema asks of each unit in the lane of the case
(``floodguard.planning_overlay``, task E11), from measurements the earlier tasks produced:

* the five component records through :mod:`floodguard.normalisation`, exactly as the signed scoring frame states
  them: flood likelihood from the flood input of task E1 with the anchor of decision D4 and permanent water left
  out, exposure as a share, access gap and road criticality from the **counts** of the task E5 tables (a row
  that stores a ratio is refused), vulnerability from the age counts of task E7 on the national anchors. Nothing
  is scaled by the other units of the batch (guardrail GR2);
* the confidence record through :func:`floodguard.confidence.derive_confidence` (rule v1), with its measurements;
* FPPS, the binding class and its reason code through the unchanged scorer (``scoring.score_subdistricts``): class
  rule v1 is binding (decision D6);
* the would-be class where protocol v1a states one: a low-confidence row with all five components, not under
  guardrail GR1. It is the scorer rerun with confidence medium and is never binding;
* class rule v2 as the labelled secondary axis (:func:`class_v2`), in the order E, A, B, C, D of drafter reading
  DR-A08. Triggers E and A are computed from the row. The outcomes of B, C and D are inputs
  (:class:`V2TriggerInputs`): no stage computes them yet. A row whose v2 result depends on a trigger that was
  not evaluated has no v2 result the protocols state, so the overlay is not written (:class:`V2NotEvaluableError`);
* leave-one-component-out (drafter reading DR-A02) and the headline slot, which stays ``not_evaluated``: the
  ensemble is task E10 (guardrail GR8);
* guardrails GR1 (fewer than 100 residents: no class), GR3 (one flood input, one routing context, one closure
  rule; :func:`lane_purity_record` compares the hashes), GR5 (nothing is computed unless both protocol files are in
  force: every rule object here comes from :func:`load_assessment_rules`), GR6 (the rights level of the overlay is
  the minimum across its lineage) and GR7 (no OBS row that is not event-aligned carries a class above E).

The overlay is written and verified with ``floodguard.planning_overlay`` and its validator bound to the two
protocol files (:func:`write_assessment`, :func:`verify_assessment`). The verifier also checks what the overlay
schema cannot: that every reporting unit of the case has exactly one row (protocol v1a, ``case_portfolio``:
"Every cell of every case is reported whatever it shows").

The functions take measurements as arguments and read no file besides the protocol files. Where the protocols
state no value (a unit with no land outside permanent water, no resident, or nobody with baseline access) the
component is left out, the confidence rule records C5 as failed, and the row is class E with reason
``low_confidence``. An assessment is planning guidance for preparedness and post-event prioritisation. It is not
an official warning and not an observation of a flood, and class E never means safe.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
import math
from pathlib import Path
from typing import Any

import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from floodguard import closure_rules, flood_inputs, normalisation, rights
from floodguard.confidence import (
    COMPONENT_COMPUTED,
    SCENARIO_LANES,
    ConfidenceError,
    ConfidenceInputs,
    coverage_by_construction_applies,
    derive_confidence,
)
from floodguard.evidence_scenarios import FACILITY_SNAP_LIMIT_M, POPULATION_SNAP_LIMIT_M
from floodguard.normalisation import NormalisationError, frame_record, protocol_hashes, read_protocol_in_force
from floodguard.planning_overlay import (
    CLASSES_ABOVE_E,
    CLOSURE_BASIS_PREFIX,
    EVENT_ALIGNED,
    FIXTURE_KIND,
    FIXTURE_LABEL,
    FIXTURE_MODE,
    FLOOD_INPUT_ROLE,
    GUARDRAIL_GR8,
    HEADLINE_NOT_EVALUATED,
    NO_V2_TRIGGER,
    PORTFOLIO_KIND,
    ROUTING_CONTEXT_ROLE,
    SCHEMA_ID,
    SCHEMA_VERSION,
    V2_TRIGGER_ORDER,
    OverlayProblem,
    PlanningOverlayError,
    ProtocolBinding,
    expected_temporal_relation,
    load_overlay,
    load_protocol_binding,
    summarise_overlay,
    write_overlay,
)
from floodguard.scoring import SCORE_COMPONENTS, score_subdistricts

ASSESSMENT_VERSION = "planning_assessment_v1"
CANDIDATE_MODE = "candidate"
NOT_COMPUTED = "not_computed"
ACCESS_COUNT_KEYS: frozenset[str] = frozenset(
    {"mode", "threshold_minutes", "baseline_access_residents", "newly_lost_residents"}
)
"""What one service of the access gap carries: its mode, its threshold and two counts of residents. No ratio."""
ROUTE_COUNT_KEYS: frozenset[str] = frozenset({"residents_losing_all_routes", "residents_with_baseline_route"})
STORED_RATIO_WORDS: frozenset[str] = frozenset({"share", "shares", "ratio", "fraction", "percent", "pct", "rate"})
"""A key with one of these words holds a ratio of two counts. Task E8 computes its components from counts only."""
STORED_COMPONENT_SUFFIX = "_0_100"
"""A key that ends like this holds a value on the 0-100 scale: a component, not a count."""
HOSPITAL = "hospital"
REFERENCE_CELL_WORDS: tuple[str, ...] = ("as-provided flood state", "public facilities", "WorldPop 2020", "default weights")
"""What protocol v1b says of the default cell, beside its passability level (``ensemble_grid.headline_rule``)."""
CLASS_E_WORDING = "Planning guidance only. Not an official warning. Class E never means safe."

OPEN_POINTS: tuple[Mapping[str, str], ...] = (
    {
        "id": "E8-OP1",
        "point": "A v2 result that depends on a trigger nobody evaluated.",
        "signed_files_say": "Protocol v1a class_rules.v2: five triggers, evaluated in the order E, A, B, C, D; the first "
                            "one met gives the class, and a unit that meets none gets 'no_v2_trigger'. Protocol v1b "
                            "class_rule_v2_inputs defines the inputs of B, C and D, and says that the recurrence flag "
                            "cannot be computed where the JRC tile is not on disk. Neither says what the v2 result is "
                            "when a trigger cannot be evaluated.",
        "what_this_task_does": "Triggers E and A are computed from the row. The outcomes of B, C and D are inputs, and no "
                               "stage computes them yet. Where an earlier trigger in the order is met, the result is "
                               "stated and a trigger that was not evaluated is written with met false and the words "
                               "'Not evaluated'. Where the result depends on such a trigger, the overlay is not written.",
        "for_the_owners": "Whether an overlay may say 'not evaluated' for the v2 axis of a row (a schema change), or "
                          "whether the inputs of B, C and D are built first: the single-link closures of the top-20 "
                          "links, the serving-facility test and the recurrence flag.",
    },
    {
        "id": "E8-OP2",
        "point": "Which closure level the row of the overlay uses.",
        "signed_files_say": "Protocol v1b ensemble_grid.headline_rule names the default cell (as-provided flood state, "
                            "central passability, public facilities, WorldPop 2020, P10 / P90 anchors, default weights), "
                            "and protocol v1a demo_tambon_rule takes the FPPS of that cell. Neither says in so many "
                            "words that the row of the overlay is the default cell.",
        "what_this_task_does": "The row is the default cell: the flood input as provided, the closure level the "
                               "reference-cell sentence names, the public services, the frame's own anchors and weights.",
        "for_the_owners": "Whether the overlay row is the default cell.",
    },
    {
        "id": "E8-OP3",
        "point": "The two measurements of confidence conditions C7 and C8 for one unit.",
        "signed_files_say": "Protocol v1a confidence_rule_v1: C7 'Baseline vehicle connected-no-route share is at most "
                            "10 percent' and C8 'At least one hospital is reachable at baseline', per unit and lane. "
                            "The share was measured for the whole frame by tasks E0 and E4, for the hospital service.",
        "what_this_task_does": "C7 is the E0 definition applied to one unit, from the counts of the task E5 table: the "
                               "unit's residents connected to the vehicle graph with no modelled route to a hospital, "
                               "over its connected residents (1 when nobody is connected). C8 counts the hospital "
                               "destinations that at least one connected resident of the unit can reach on the "
                               "baseline vehicle graph.",
        "for_the_owners": "Whether C7 is judged on the hospital service, and whether C8 counts OSM hospital objects "
                          "(as here) or distinct named hospitals. The condition needs one or more either way.",
    },
    {
        "id": "E8-OP4",
        "point": "The source timestamp of an overlay whose flood input has no instant.",
        "signed_files_say": "AGENTS.md asks every output for a source timestamp. Overlay schema 1.0 takes an instant "
                            "(a date and a time). The product 4009 layers have a date or a season window, no time.",
        "what_this_task_does": "The overlay and its rows state the last date of the flood input's source period at "
                               "00:00:00 UTC, and say so in the assumptions. Each input states its own source time as "
                               "its record gives it.",
        "for_the_owners": "Whether the schema should take a date or a period.",
    },
    {
        "id": "E8-OP5",
        "point": "The rights level of an input that has no rights record.",
        "signed_files_say": "Protocol v1a guardrail GR6: the rights level of an overlay is the minimum across its "
                            "lineage. The rights registry holds a record for product 4009 only. Protocol v1b says of "
                            "the WorldPop 2024 age rasters: 'Public catalog says CC BY 4.0. Public derivatives require "
                            "purpose-specific review.'",
        "what_this_task_does": "The level of each input is stated by the script that reads it, with its basis. This "
                               "module only takes the minimum.",
        "for_the_owners": "The purpose-specific review of the age rasters, and whether open-licence inputs need a "
                          "record in the registry.",
    },
)
"""What the signed files leave open for this task. None of it is decided here."""


class PlanningAssessmentError(ValueError):
    """Raised when the inputs of an assessment break its contract or a guardrail."""


class LanePurityError(PlanningAssessmentError):
    """Raised when the components of a row would come from two flood inputs, contexts or closure rules (GR3)."""


class V2NotEvaluableError(PlanningAssessmentError):
    """Raised when the v2 result of a row depends on a trigger that was not evaluated.

    ``rows`` lists each such row: its unit and the triggers that were not evaluated.
    """

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.rows: tuple[dict[str, Any], ...] = tuple(dict(row) for row in rows)
        units = ", ".join(str(row["unit_id"]) for row in self.rows)
        super().__init__(
            "the v2 result depends on a trigger that was not evaluated, and the protocols state no result for that "
            f"case (open point E8-OP1); units: {units}"
        )


# ---------------------------------------------------------------------------
# The rules, read from the two protocol files in force
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssessmentRules:
    """What this module reads from the protocol files in force, beside the overlay binding.

    ``reference_closure_level`` is the passability level of the default cell of protocol v1b
    (``ensemble_grid.headline_rule.reference_cell``). ``v2_*`` are the parameters of class rule v2 in protocol
    v1a; ``v2_dependent_share_min`` is the national anchor the percentile names. ``lane_definitions`` holds the
    definition protocol v1a gives each lane, which is the scenario declaration of a season-envelope row.
    """

    binding: ProtocolBinding
    reference_closure_level: str
    v2_dependent_share_percentile: str
    v2_dependent_share_min: float
    v2_isolated_residents_min: float
    v2_critical_link_rank_max: int
    headline_class_retention_min: float
    lane_definitions: Mapping[str, str]
    lane_display_texts: Mapping[str, str]
    reporting_frames: Mapping[str, tuple[str, ...]]
    class_e_wording: str


def load_assessment_rules(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> AssessmentRules:
    """Read the rules of an assessment from the two protocol files, which must both be in force (guardrail GR5).

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not in force.
        PlanningAssessmentError: when a file does not hold what this module implements: class rule v1 binding
            and v2 secondary, the would-be rule, or a default cell with one passability level.
    """

    binding = load_protocol_binding(v1a_path, v1b_path, receipts_path)
    v1a, _v1a_sha256 = read_protocol_in_force("v1a", v1a_path, receipts_path)
    v1b, _v1b_sha256 = read_protocol_in_force("v1b", v1b_path, receipts_path)
    try:
        return _rules(binding, v1a, v1b)
    except PlanningAssessmentError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise PlanningAssessmentError(f"the protocol files do not hold what the assessment reads: {error!r}") from error


def _rules(binding: ProtocolBinding, v1a: Mapping[str, Any], v1b: Mapping[str, Any]) -> AssessmentRules:
    """Read every parameter; a missing key is turned into PlanningAssessmentError by the caller."""

    class_rules = v1a["class_rules"]
    v1, v2 = class_rules["v1"], class_rules["v2"]
    if v1["binding"] is not True or v2["binding"] is not False or v2["label_when_shown"] != "secondary":
        raise PlanningAssessmentError("this module implements class rule v1 as binding and v2 as the secondary axis")
    if "confidence set to medium" not in v1["would_be_class"] or "never binding" not in v1["would_be_class"]:
        raise PlanningAssessmentError("protocol v1a states the would-be class in other words than this module reads")
    reference = str(v1b["ensemble_grid"]["headline_rule"]["reference_cell"])
    levels = [level for level in closure_rules.LEVELS if f"{level} passability" in reference]
    if len(levels) != 1 or any(words not in reference for words in REFERENCE_CELL_WORDS):
        raise PlanningAssessmentError("protocol v1b does not name the default cell as this module reads it")
    parameters = v2["parameters"]
    percentile = str(parameters["national_dependent_share_percentile"])
    lanes = {str(row["lane"]): row for row in v1a["evidence_tier_model"]["lanes"]}
    portfolio = v1a["case_portfolio"]
    return AssessmentRules(
        binding=binding,
        reference_closure_level=levels[0],
        v2_dependent_share_percentile=percentile,
        v2_dependent_share_min=float(binding.frame.vulnerability_anchors[percentile]),
        v2_isolated_residents_min=float(parameters["isolated_residents_min"]),
        v2_critical_link_rank_max=int(parameters["critical_link_rank_max"]),
        headline_class_retention_min=binding.headline_class_retention_min,
        lane_definitions={lane: str(row["definition"]) for lane, row in lanes.items()},
        lane_display_texts={lane: str(row["display_text"]) for lane, row in lanes.items() if "display_text" in row},
        reporting_frames={"mae_sai": tuple(str(unit) for unit in portfolio["mae_sai_reporting_frame"]["units"])},
        class_e_wording=str(v1a["wording"]["class_e_wording"]),
    )


# ---------------------------------------------------------------------------
# What a case, a flood input and a unit are
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseSpec:
    """The case an overlay belongs to: a case of protocol v1a, or an invented fixture (not a place)."""

    case_id: str
    kind: str
    title_en: str
    title_th: str
    frame: str
    case_reference_date: date | None
    lane: str
    tier: str
    scenario_id: str | None = None
    scenario_declaration: str | None = None
    scenario_base: str | None = None
    fixture_notice: str | None = None


@dataclass(frozen=True)
class FloodInputSpec:
    """The one flood input of the rows: its identifier in the overlay, its protocol name and its dates.

    ``source_instant`` is what the overlay states as its source timestamp (open point E8-OP4).
    """

    input_id: str
    name: str
    acquisition_date: date | None
    source_instant: str


@dataclass(frozen=True)
class ClosureSpec:
    """The one closure rule of the rows: its version and level. The basis is the flood input of the row."""

    version: str
    level: str


@dataclass(frozen=True, kw_only=True)
class V2TriggerInputs:
    """The outcomes of the v2 triggers a row cannot compute from itself; ``None`` says not evaluated.

    Attributes:
        link_isolation: Trigger B (protocol v1b ``class_rule_v2_inputs.trigger_B_isolation``): a top-20 link of
            the baseline critical-link ranking that intersects the flood extent, closed on its own, takes every
            route from at least 500 residents of the unit.
        serving_facility: The facility part of trigger C (``trigger_C_serving_facility``): an OSM hospital or a
            uniquely located DDPM shelter serving the unit is inside the extent or loses all vehicle routes.
        recurrence_flag: The flag of trigger D (``trigger_D_recurrence_flag``).
        *_evidence: What was measured, in a sentence; for a trigger that was not evaluated, why not.
    """

    link_isolation: bool | None = None
    link_isolation_evidence: str = "no stage has closed the top-20 links one at a time"
    serving_facility: bool | None = None
    serving_facility_evidence: str = "no stage has run the serving-facility test"
    recurrence_flag: bool | None = None
    recurrence_evidence: str = "no stage has computed the recurrence flag"


@dataclass(frozen=True, kw_only=True)
class UnitMeasurements:
    """The measurements of one reporting unit in one lane. Every count is for this unit only.

    Attributes:
        unit_id, unit_name_en, unit_name_th: The unit.
        flooded_non_permanent_water_land_area, non_permanent_water_land_area: The two areas of the flood
            likelihood, in one area unit (:func:`floodguard.flood_inputs.flooded_land_areas`).
        unit_residents: The residents the row is scored on (the population cells whose centre is in the unit).
        residents_inside_flood_extent: Those residents whose cell centre is inside the flood extent, for each
            of the three levels ``minus``, ``as_provided`` and ``plus`` of the flood input.
        access_gap_inputs: For each service, its mode, its threshold and two counts
            (:data:`ACCESS_COUNT_KEYS`), as the task E5 table gives them.
        residents_losing_all_routes, residents_with_baseline_route: The two counts of road criticality.
        children_0_14, older_60_plus, age_residents: The age counts of task E7, or ``None`` when the unit has none.
        unit_valid_coverage: The measured share of the unit inside the product footprint, or ``None``.
        coverage_by_construction: True only where protocol v1a grants condition C3 by construction.
        residents_connected_to_the_graph, connected_residents_without_a_hospital_route: The two counts of
            the baseline vehicle connected-no-route share (condition C7).
        hospitals_reachable_at_baseline: The hospitals a connected resident of the unit can reach at baseline (C8).
        t2_abstention_fraction, t2_geoid_held_out_test_iou: For an own candidate only.
        v2: The outcomes of the v2 triggers B, C and D.
        assumptions: What the measurements of this unit assume, beyond what every row says.
    """

    unit_id: str
    unit_name_en: str
    unit_name_th: str
    flooded_non_permanent_water_land_area: float
    non_permanent_water_land_area: float
    unit_residents: float
    residents_inside_flood_extent: Mapping[str, float]
    access_gap_inputs: Mapping[str, Mapping[str, Any]]
    residents_losing_all_routes: float
    residents_with_baseline_route: float
    children_0_14: float | None
    older_60_plus: float | None
    age_residents: float | None
    unit_valid_coverage: float | None
    coverage_by_construction: bool
    residents_connected_to_the_graph: float
    connected_residents_without_a_hospital_route: float
    hospitals_reachable_at_baseline: int | None
    t2_abstention_fraction: float | None = None
    t2_geoid_held_out_test_iou: float | None = None
    v2: V2TriggerInputs = field(default_factory=V2TriggerInputs)
    assumptions: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Measurements of one unit from geometry, cells and the tables of the earlier tasks
# ---------------------------------------------------------------------------


def unit_coverage(unit: BaseGeometry, footprint: BaseGeometry) -> float:
    """Return the share of a unit's area inside a product footprint (condition C3), both in EPSG:32647.

    Raises:
        PlanningAssessmentError: for a unit with no area.
    """

    area = float(unit.area)
    if not area > 0:
        raise PlanningAssessmentError("a unit needs an area to have a coverage")
    if footprint.is_empty:
        return 0.0
    return min(1.0, float(flood_inputs.as_multipolygon(shapely.intersection(unit, footprint)).area) / area)


def residents_by_unit(cells: Iterable[Mapping[str, Any]], extent: BaseGeometry | None = None) -> dict[str, float]:
    """Sum the residents of each unit, or those whose cell centre is inside a flood extent.

    Protocol v1a, exposure: "residents whose population cell centre is inside the flood extent". The centre is
    inside when the extent covers the point, as ``floodguard.evidence_flood_scenario`` reads it.

    Args:
        cells: Rows with ``unit_id`` (``None`` for a cell that counts for no unit), ``residents`` and the cell
            centre ``x`` and ``y`` in the coordinates of the extent (EPSG:32647).
        extent: The flood extent; ``None`` sums every cell of the unit.

    Returns:
        ``unit_id -> residents`` for every unit that has a cell; a unit with no cell inside gets 0.
    """

    rows = [row for row in cells if row["unit_id"] is not None]
    totals: dict[str, list[float]] = {str(row["unit_id"]): [] for row in rows}
    if not rows:
        return {}
    inside: Any = [True] * len(rows)
    if extent is not None:
        if extent.is_empty:
            inside = [False] * len(rows)
        else:
            shapely.prepare(extent)
            points = shapely.points([float(row["x"]) for row in rows], [float(row["y"]) for row in rows])
            inside = shapely.covers(extent, points)
    for row, counted in zip(rows, inside):
        if counted:
            totals[str(row["unit_id"])].append(float(row["residents"]))
    return {unit_id: math.fsum(values) for unit_id, values in totals.items()}


def baseline_no_route_share(connected_residents: float, connected_without_a_route: float) -> float:
    """Return the baseline vehicle connected-no-route share of one unit (condition C7).

    The E0 spike's definition (``floodguard.planning_context.no_route_share``) applied to one unit: residents
    connected to the graph with no modelled route, over the connected residents; 1 when nobody is connected.

    Raises:
        PlanningAssessmentError: for a count that is not finite or negative, or more without a route than connected.
    """

    for value in (connected_residents, connected_without_a_route):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise PlanningAssessmentError("the counts of the no-route share must be finite and not negative")
    if connected_without_a_route > connected_residents * (1 + 1e-9) + 1e-9:
        raise PlanningAssessmentError("more residents are without a route than are connected to the graph")
    if connected_residents <= 0:
        return 1.0
    return min(1.0, connected_without_a_route / connected_residents)


def hospitals_reachable_at_baseline(
    cells: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    hospitals: Iterable[Mapping[str, Any]],
    *,
    population_snap_limit_m: float = POPULATION_SNAP_LIMIT_M,
    facility_snap_limit_m: float = FACILITY_SNAP_LIMIT_M,
) -> dict[str, int]:
    """Count, for each unit, the hospitals a connected resident of the unit can reach on the baseline graph (C8).

    The graph is undirected, as the access model uses it, so a hospital is reachable from a cell when both snap
    to one connected component. A cell counts when it has residents and snaps to a road node within the
    population limit; a hospital when it snaps to a road node within the facility limit.

    Args:
        cells: Rows with ``unit_id``, ``residents``, ``node_id`` and ``snap_distance_m``.
        edges: The baseline edges (``from_node``, ``to_node``), grade joins included.
        hospitals: Destination rows with ``facility_id``, ``node_id`` and ``snap_distance_m``.

    Returns:
        ``unit_id -> number of hospitals`` for every unit that has a cell.
    """

    parent: dict[Any, Any] = {}

    def find(node: Any) -> Any:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    for edge in edges:
        start, end = edge["from_node"], edge["to_node"]
        parent.setdefault(start, start)
        parent.setdefault(end, end)
        first, second = find(start), find(end)
        if first != second:
            parent[second] = first
    sites: dict[str, Any] = {}
    for row in hospitals:
        node, snap = row.get("node_id"), row.get("snap_distance_m")
        if node in parent and snap is not None and snap <= facility_snap_limit_m:
            sites[str(row["facility_id"])] = find(node)
    components: dict[str, set[Any]] = {}
    for row in cells:
        if row["unit_id"] is None:
            continue
        found = components.setdefault(str(row["unit_id"]), set())
        node, snap = row.get("node_id"), row.get("snap_distance_m")
        if node in parent and snap is not None and snap <= population_snap_limit_m and float(row["residents"]) > 0:
            found.add(find(node))
    return {unit_id: sum(1 for root in sites.values() if root in found) for unit_id, found in components.items()}


def _stored_ratio_keys(value: Any, path: str = "") -> list[str]:
    """Find every key of a table row that names a ratio of two counts."""

    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            where = f"{path}.{key}" if path else str(key)
            name = str(key).lower()
            if name.endswith(STORED_COMPONENT_SUFFIX) or STORED_RATIO_WORDS & set(name.split("_")):
                found.append(where)
            found.extend(_stored_ratio_keys(child, where))
    return found


def access_counts_from_e5_row(row: Mapping[str, Any], services: Sequence[str]) -> dict[str, Any]:
    """Take the counts of one unit from a row of a task E5 table, and nothing else.

    The access gap and the road criticality are computed from counts of residents
    (``floodguard.normalisation``). A row that stores a ratio of two counts is refused: the first E5 table held
    the route ratio, which is the road-criticality component divided by 100.

    Args:
        row: One unit row of one run of the table (``floodguard.access_diff_units.v2``).
        services: The services of the access gap at the level of the overlay.

    Returns:
        ``residents``, ``access_gap_inputs``, the two route counts and the two counts of the baseline
        no-route share of the hospital service.

    Raises:
        PlanningAssessmentError: for a row that stores a ratio, lacks a service or carries other keys for one.
    """

    ratios = _stored_ratio_keys(row)
    if ratios:
        raise PlanningAssessmentError(
            f"the access table stores a ratio of two counts ({', '.join(ratios[:4])}): the components are computed "
            "from counts, never from a stored ratio"
        )
    try:
        stated = row["access_gap_inputs"]
        missing = [service for service in services if service not in stated]
        if missing:
            raise PlanningAssessmentError(f"the access table has no counts for the service(s) {missing}")
        inputs = {service: dict(stated[service]) for service in services}
        if any(set(counts) != ACCESS_COUNT_KEYS for counts in inputs.values()):
            raise PlanningAssessmentError(f"a service of the access gap carries exactly {sorted(ACCESS_COUNT_KEYS)}")
        routes = dict(row["road_criticality_inputs"])
        if set(routes) != ROUTE_COUNT_KEYS:
            raise PlanningAssessmentError(f"the road-criticality inputs are exactly {sorted(ROUTE_COUNT_KEYS)}")
        hospital = row["access"][HOSPITAL]
        connected = float(hospital["residents_connected_to_the_graph"])
        with_route = float(hospital["residents_with_a_baseline_route"])
        return {
            "unit_id": str(row["unit_id"]),
            "residents": float(row["residents"]),
            "access_gap_inputs": inputs,
            "residents_losing_all_routes": float(routes["residents_losing_all_routes"]),
            "residents_with_baseline_route": float(routes["residents_with_baseline_route"]),
            "residents_connected_to_the_graph": connected,
            "connected_residents_without_a_hospital_route": max(0.0, connected - with_route),
            "residents_with_a_baseline_hospital_route": with_route,
        }
    except (KeyError, TypeError, ValueError) as error:
        raise PlanningAssessmentError(f"the row is not a unit row of a task E5 table: {error!r}") from error


def age_counts_from_e7_row(row: Mapping[str, Any]) -> dict[str, float | None]:
    """Take the three age counts of one unit from a row of the task E7 table.

    The dependent share the table states is not read: ``floodguard.normalisation`` computes it from the counts.
    A unit the table gives no share (``dependent_share_unavailable_reason``) has no counts here.
    """

    try:
        if row.get("dependent_share_unavailable_reason") is not None or row["residents"] is None:
            return {"children_0_14": None, "older_60_plus": None, "age_residents": None}
        return {
            "children_0_14": float(row["children_0_14"]),
            "older_60_plus": float(row["older_60_plus"]),
            "age_residents": float(row["residents"]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise PlanningAssessmentError(f"the row is not a unit row of the task E7 table: {error!r}") from error


# ---------------------------------------------------------------------------
# One row
# ---------------------------------------------------------------------------


def component_records(frame: normalisation.PlanningFrame, unit: UnitMeasurements) -> tuple[dict[str, Any], list[str]]:
    """Compute the five component records of one unit, each through the frame v1 function of its component.

    Returns:
        The records by component (``None`` where the protocol states no value for the unit) and, for each
        component that is not computed, a sentence saying why.

    Raises:
        PlanningAssessmentError: when a service of the access gap carries anything but its two counts, its mode
            and its threshold.
    """

    for service, counts in unit.access_gap_inputs.items():
        if set(counts) != ACCESS_COUNT_KEYS:
            raise PlanningAssessmentError(
                f"service {service}: the access gap is computed from {sorted(ACCESS_COUNT_KEYS)}, never from a stored ratio"
            )
    as_provided = unit.residents_inside_flood_extent[flood_inputs.AS_PROVIDED]
    calls = {
        "flood_likelihood_0_100": lambda: normalisation.flood_likelihood(
            frame,
            flooded_non_permanent_water_land_area=unit.flooded_non_permanent_water_land_area,
            non_permanent_water_land_area=unit.non_permanent_water_land_area,
        ),
        "exposure_0_100": lambda: normalisation.exposure(
            frame, residents_inside_flood_extent=as_provided, unit_residents=unit.unit_residents
        ),
        "access_gap_0_100": lambda: normalisation.access_gap(
            frame, services={service: dict(counts) for service, counts in unit.access_gap_inputs.items()}
        ),
        "road_criticality_0_100": lambda: normalisation.road_criticality(
            frame,
            residents_losing_all_routes=unit.residents_losing_all_routes,
            residents_with_baseline_route=unit.residents_with_baseline_route,
        ),
        "vulnerability_context_0_100": lambda: normalisation.vulnerability_context(
            frame, children_0_14=unit.children_0_14, older_60_plus=unit.older_60_plus, residents=unit.age_residents
        ),
    }
    records: dict[str, Any] = {}
    notes: list[str] = []
    for name in SCORE_COMPONENTS:
        try:
            records[name] = calls[name]()
        except NormalisationError as error:
            records[name] = None
            notes.append(f"{name} is not computed: {error}.")
    return records, notes


def _exposure_at_level(frame: normalisation.PlanningFrame, unit: UnitMeasurements, level: str) -> float | None:
    """Exposure with the flood input at one level, or None where the protocol states no value."""

    try:
        record = normalisation.exposure(
            frame, residents_inside_flood_extent=unit.residents_inside_flood_extent[level], unit_residents=unit.unit_residents
        )
    except NormalisationError:
        return None
    return float(record["value_0_100"])


def _scored(values: Mapping[str, float], confidence_class: str, weights: Mapping[str, float]) -> tuple[float, str, str]:
    """FPPS, v1 class and reason code of one row from the unchanged scorer."""

    table = pd.DataFrame(
        [{"subdistrict_id": "row", "subdistrict_name": "row", "confidence_class": confidence_class, **values}]
    )
    row = score_subdistricts(table, dict(weights)).iloc[0]
    return float(row["fpps_0_100"]), str(row["action_class"]), str(row["action_reason_code"])


def scoring_block(
    values: Mapping[str, float | None],
    confidence_class: str,
    gr1_applies: bool,
    frame_header: Mapping[str, Any],
) -> dict[str, Any]:
    """FPPS, the binding v1 class, its reason code, the would-be class and leave-one-component-out of one row.

    Protocol v1a: class rule v1 is binding and is the unchanged ``scoring.assign_action_class``. Low confidence
    gives class E with reason ``low_confidence``. The would-be class is the scorer rerun with confidence medium,
    for a low-confidence row only, and is never binding. Guardrail GR1 (drafter reading DR-A09): a unit with
    fewer residents than the minimum has no binding class, no would-be class and no leave-one-out class, and
    its reason code is ``insufficient_denominator``. A row with a component that is not computed has no FPPS.
    """

    if any(values[name] is None for name in SCORE_COMPONENTS):
        if confidence_class != "low":
            raise PlanningAssessmentError("a row with a component that is not computed is low confidence (condition C5)")
        block = {"fpps_0_100": None, "action_class": "E", "action_reason_code": "low_confidence",
                 "would_be_class": None, "leave_one_component_out": None}
    else:
        complete = {name: float(values[name]) for name in SCORE_COMPONENTS}  # type: ignore[arg-type]
        fpps, action_class, reason_code = _scored(complete, confidence_class, frame_header["weights"])
        would_be = None
        if confidence_class == "low" and not gr1_applies:
            would_be = _scored(complete, "medium", frame_header["weights"])[1]
        loco = {}
        for dropped in SCORE_COMPONENTS:
            left_out = _scored(complete, confidence_class, frame_header["leave_one_component_out_weights"][dropped])
            loco[dropped] = {"fpps_0_100": left_out[0], "action_class": None if gr1_applies else left_out[1]}
        block = {"fpps_0_100": fpps, "action_class": action_class, "action_reason_code": reason_code,
                 "would_be_class": would_be, "leave_one_component_out": loco}
    if gr1_applies:
        block.update({"action_class": None, "action_reason_code": "insufficient_denominator", "would_be_class": None})
    return block


def _shown(value: float | None) -> str:
    return "not computed" if value is None else f"{value:.2f}"


def class_v2(
    rules: AssessmentRules,
    *,
    unit_id: str,
    fpps: float | None,
    exposure: float | None,
    confidence_class: str,
    gr1_applies: bool,
    action_class: str | None,
    dependent_share: float | None,
    triggers: V2TriggerInputs,
) -> dict[str, Any]:
    """Class rule v2 of one row: a labelled secondary axis, never binding (protocol v1a ``class_rules.v2``).

    The triggers are evaluated in the order E, A, B, C, D and the first one met gives the class; a unit that
    meets none is ``no_v2_trigger`` (drafter reading DR-A08). Trigger E: low confidence, exposure below the
    floor or FPPS below the minimum. Trigger A: the v1 class is A and the unit's dependent share is at or above
    the national percentile protocol v1a names. Trigger B, the facility part of C and the flag of D are inputs.
    C also needs an FPPS at or above the minimum and medium (or scenario) confidence; D an FPPS at or above it.

    A unit under guardrail GR1 has no v2 class. A trigger that was not evaluated and stands after the first
    trigger met is written with ``met`` false and evidence that starts with "Not evaluated".

    Raises:
        V2NotEvaluableError: when no trigger before it is met and a trigger was not evaluated: the result would
            depend on it, and the protocols state no result for that case.
    """

    block = {"class_rule_version": rules.binding.class_rule_v2["version"], "label": "secondary", "binding": False}
    if gr1_applies:
        return {**block, "result": None, "trigger_evidence": []}
    fpps_min = float(rules.binding.class_rule_v2["fpps_min"])
    exposure_floor = float(rules.binding.class_rule_v2["exposure_floor_for_non_e"])
    scored_enough = fpps is not None and fpps >= fpps_min
    low = confidence_class == "low"
    percentile, share_min = rules.v2_dependent_share_percentile, rules.v2_dependent_share_min
    share_text = "not computed" if dependent_share is None else f"{dependent_share:.6f}"
    met: dict[str, bool | None] = {
        "E": low or not scored_enough or (exposure is not None and exposure < exposure_floor),
        "A": action_class == "A" and dependent_share is not None and dependent_share >= share_min,
        "B": triggers.link_isolation,
        "C": False if (not scored_enough or low) else triggers.serving_facility,
        "D": False if not scored_enough else triggers.recurrence_flag,
    }
    evidence = {
        "E": f"Confidence {confidence_class}; exposure {_shown(exposure)} against a floor of {exposure_floor:g}; "
             f"FPPS {_shown(fpps)} against a minimum of {fpps_min:g}.",
        "A": f"v1 class {action_class}; dependent share {share_text} against the national {percentile} of {share_min}.",
        "B": f"A top-{rules.v2_critical_link_rank_max} critical link inside the flood extent, closed on its own, takes "
             f"every route from at least {rules.v2_isolated_residents_min:g} residents of the unit: "
             f"{triggers.link_isolation_evidence}.",
        "C": f"FPPS {_shown(fpps)} against a minimum of {fpps_min:g}, confidence {confidence_class}, and a serving "
             f"hospital or uniquely located shelter inside the extent or without a vehicle route: "
             f"{triggers.serving_facility_evidence}.",
        "D": f"FPPS {_shown(fpps)} against a minimum of {fpps_min:g}, and the recurrence flag: "
             f"{triggers.recurrence_evidence}.",
    }
    first = None
    for trigger in V2_TRIGGER_ORDER:
        if met[trigger] is None:
            not_evaluated = [name for name in V2_TRIGGER_ORDER if met[name] is None]
            raise V2NotEvaluableError([{"unit_id": unit_id, "triggers_not_evaluated": not_evaluated}])
        if met[trigger]:
            first = trigger
            break
    rows = []
    for trigger in V2_TRIGGER_ORDER:
        if met[trigger] is None:
            rows.append({
                "trigger": trigger,
                "met": False,
                "evidence": f"Not evaluated: {evidence[trigger]} The result does not depend on it: trigger {first} "
                            "stands before it in the order E, A, B, C, D.",
            })
        else:
            rows.append({"trigger": trigger, "met": bool(met[trigger]), "evidence": evidence[trigger]})
    return {**block, "result": first or NO_V2_TRIGGER, "trigger_evidence": rows}


def headline_slot(rules: AssessmentRules) -> dict[str, Any]:
    """The headline-stability slot of a row before the ensemble has run: not evaluated (guardrail GR8)."""

    return {
        "guardrail": GUARDRAIL_GR8,
        "status": HEADLINE_NOT_EVALUATED,
        "class_retention": None,
        "class_retention_min": rules.headline_class_retention_min,
    }


def assess_unit(
    rules: AssessmentRules,
    case: CaseSpec,
    flood: FloodInputSpec,
    closure: ClosureSpec,
    unit: UnitMeasurements,
    *,
    routing_context_id: str,
    frame_header: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the overlay row of one unit: components, confidence, FPPS, classes, leave-one-out, headline slot.

    Raises:
        PlanningAssessmentError: when the measurements break the contract of the confidence rule (coverage
            declared by construction outside the case protocol v1a grants, a lane and tier that do not belong
            together) or a guardrail.
        V2NotEvaluableError: see :func:`class_v2`.
    """

    frame, rule = rules.binding.frame, rules.binding.rule
    header = frame_record(frame) if frame_header is None else frame_header
    if set(unit.residents_inside_flood_extent) != set(flood_inputs.LEVELS):
        raise PlanningAssessmentError(f"exposure is measured at the three levels {list(flood_inputs.LEVELS)}")
    if case.kind == FIXTURE_KIND and FIXTURE_LABEL not in unit.unit_name_en:
        raise PlanningAssessmentError(f"a fixture unit is named '{FIXTURE_LABEL}'")
    if (case.tier == "T1") != (case.scenario_id is not None and case.scenario_declaration is not None):
        raise PlanningAssessmentError("a tier T1 case carries its scenario declaration, and no other case does")
    components, notes = component_records(frame, unit)
    values = {name: None if record is None else float(record["value_0_100"]) for name, record in components.items()}
    by_construction = unit.coverage_by_construction
    if by_construction and not coverage_by_construction_applies(rule, unit_id=unit.unit_id, flood_input=flood.name):
        raise PlanningAssessmentError(
            f"unit {unit.unit_id}: protocol v1a grants coverage by construction to product 4009 in the Mae Sai "
            "reporting frame only; the coverage of any other unit or input is measured"
        )
    try:
        confidence = derive_confidence(
            ConfidenceInputs(
                unit_id=unit.unit_id,
                lane=case.lane,
                tier=case.tier,
                flood_input=flood.name,
                scenario_base=case.scenario_base,
                acquisition_date=flood.acquisition_date,
                case_reference_date=case.case_reference_date,
                unit_valid_coverage=unit.unit_valid_coverage,
                coverage_by_construction=by_construction,
                exposure_plus_one_pixel_0_100=_exposure_at_level(frame, unit, flood_inputs.PLUS),
                exposure_minus_one_pixel_0_100=_exposure_at_level(frame, unit, flood_inputs.MINUS),
                t2_abstention_fraction=unit.t2_abstention_fraction,
                t2_geoid_held_out_test_iou=unit.t2_geoid_held_out_test_iou,
                component_status={
                    name: COMPONENT_COMPUTED if components[name] is not None else NOT_COMPUTED
                    for name in SCORE_COMPONENTS
                },
                unit_residents=unit.unit_residents,
                baseline_vehicle_no_route_share=baseline_no_route_share(
                    unit.residents_connected_to_the_graph, unit.connected_residents_without_a_hospital_route
                ),
                hospitals_reachable_at_baseline=unit.hospitals_reachable_at_baseline,
            ),
            rule,
        )
    except ConfidenceError as error:
        raise PlanningAssessmentError(f"unit {unit.unit_id}: {error}") from error
    confidence_class = confidence["confidence_class"]
    gr1_applies = bool(confidence["guardrail_gr1"]["applies"])
    scoring = scoring_block(values, confidence_class, gr1_applies, header)
    vulnerability = components["vulnerability_context_0_100"]
    v2 = class_v2(
        rules,
        unit_id=unit.unit_id,
        fpps=scoring["fpps_0_100"],
        exposure=values["exposure_0_100"],
        confidence_class=confidence_class,
        gr1_applies=gr1_applies,
        action_class=scoring["action_class"],
        dependent_share=None if vulnerability is None else float(vulnerability["dependent_share"]),
        triggers=unit.v2,
    )
    relation = expected_temporal_relation(confidence["measurements"], rule.recency_window_days)
    if case.lane == "OBS" and relation != EVENT_ALIGNED and scoring["action_class"] in CLASSES_ABOVE_E:
        raise PlanningAssessmentError(
            f"unit {unit.unit_id}: guardrail GR7: an OBS row that is {relation} carries no binding class above E"
        )
    assumptions = [
        f"Road closure is modelled from the flood input ({closure.version}, {closure.level} level): a flood "
        "intersection does not prove a road closure.",
        "Residents are modelled counts. A population cell counts for the unit whose polygon holds its centre, and a "
        "resident is inside the flood extent when the cell centre is.",
        *notes,
        *unit.assumptions,
    ]
    if any(item["evidence"].startswith("Not evaluated") for item in v2["trigger_evidence"]):
        assumptions.append(
            "A v2 trigger written as 'Not evaluated' with met false was not shown to be met and was not shown to be "
            "unmet. The v2 result stands without it, because an earlier trigger in the order is met."
        )
    scenario = None
    if case.tier == "T1":
        scenario = {"id": case.scenario_id, "declaration": case.scenario_declaration}
    return {
        "row_id": f"{case.case_id}:{unit.unit_id}:{case.lane}",
        "unit_id": unit.unit_id,
        "unit_name_en": unit.unit_name_en,
        "unit_name_th": unit.unit_name_th,
        "tier": case.tier,
        "lane": case.lane,
        "temporal_relation": relation,
        "flood_input": flood.name,
        "scenario": scenario,
        "lineage": {
            "flood_input_id": flood.input_id,
            "routing_context_id": routing_context_id,
            "closure_rule": {
                "version": closure.version,
                "level": closure.level,
                "closure_basis": f"{CLOSURE_BASIS_PREFIX}{flood.input_id}",
            },
        },
        "normalisation_version": frame.version,
        "components": components,
        "fpps_0_100": scoring["fpps_0_100"],
        "confidence": confidence,
        "action_class": scoring["action_class"],
        "action_reason_code": scoring["action_reason_code"],
        "would_be_class": scoring["would_be_class"],
        "class_v2": v2,
        "leave_one_component_out": scoring["leave_one_component_out"],
        "headline_stability": headline_slot(rules),
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": flood.source_instant,
        "assumptions": list(dict.fromkeys(assumptions)),
    }


# ---------------------------------------------------------------------------
# The overlay of one case
# ---------------------------------------------------------------------------


def assemble_overlay(
    rules: AssessmentRules,
    case: CaseSpec,
    flood: FloodInputSpec,
    closure: ClosureSpec,
    units: Sequence[UnitMeasurements],
    inputs: Sequence[Mapping[str, Any]],
    *,
    routing_context_id: str,
    generated_at: str,
    git_commit: str,
    source_name: str,
    data_version: str = ASSESSMENT_VERSION,
    assumptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble the overlay of one case: the header, the lineage inputs and one row for each unit.

    The rights level of the overlay is the minimum across the rights levels of ``inputs`` (guardrail GR6). The
    result is a plain mapping in the shape of overlay schema 1.0; :func:`write_assessment` validates and writes it.

    Args:
        rules: The rules of the protocol files in force (:func:`load_assessment_rules`).
        case: The case; a fixture case gives ``dataset_mode`` ``fixture_demo``.
        flood, closure: The one flood input and the one closure rule of every row (guardrail GR3).
        units: The measurements of each reporting unit, once each.
        inputs: The lineage input records of the overlay (schema ``input``), with the flood input and the
            routing context among them.
        routing_context_id: The ``input_id`` of the one routing context of every row.
        generated_at, git_commit, source_name, data_version: Header fields.
        assumptions: What the overlay assumes, beyond what this function states.

    Raises:
        PlanningAssessmentError: for no unit or a repeated one, a lineage that does not name the flood input
            and the routing context, a closure level the closure rule does not have, or a pitch-level access
            gap in a public overlay.
        V2NotEvaluableError: when the v2 result of one or more rows depends on a trigger that was not evaluated.
    """

    identifiers = [unit.unit_id for unit in units]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise PlanningAssessmentError("an overlay needs its units, each once")
    if closure.version != closure_rules.CLOSURE_RULE_VERSION or closure.level not in closure_rules.LEVELS:
        raise PlanningAssessmentError(f"the closure rule of a row is {closure_rules.CLOSURE_RULE_VERSION} at one of {closure_rules.LEVELS}")
    by_id = {str(item["input_id"]): item for item in inputs}
    if len(by_id) != len(inputs):
        raise PlanningAssessmentError("an input is listed twice")
    stated = by_id.get(flood.input_id)
    acquired = None if flood.acquisition_date is None else flood.acquisition_date.isoformat()
    if stated is None or stated["role"] != FLOOD_INPUT_ROLE or stated["name"] != flood.name or stated["acquisition_date"] != acquired:
        raise PlanningAssessmentError("the lineage does not hold the flood input of the rows, with its name and its date")
    if by_id.get(routing_context_id, {}).get("role") != ROUTING_CONTEXT_ROLE:
        raise PlanningAssessmentError("the lineage does not hold the routing context of the rows")
    header = frame_record(rules.binding.frame)
    rows: list[dict[str, Any]] = []
    undetermined: list[dict[str, Any]] = []
    for unit in units:
        try:
            rows.append(assess_unit(rules, case, flood, closure, unit, routing_context_id=routing_context_id, frame_header=header))
        except V2NotEvaluableError as error:
            undetermined.extend(error.rows)
    if undetermined:
        raise V2NotEvaluableError(undetermined)
    eligibility = rights.minimum_level(str(item["rights_level"]) for item in inputs)
    for row in rows:
        record = row["components"]["access_gap_0_100"]
        if record is not None and record["publication_level"] == rights.PITCH_LEVEL and eligibility == rights.PUBLIC_LEVEL:
            raise PlanningAssessmentError(
                "guardrail GR6: the shelter service is pitch level, so its access gap cannot sit in a public overlay; "
                "the lineage must hold the pitch-level input it was computed from"
            )
    fixture = case.kind == FIXTURE_KIND
    listed = [
        *assumptions,
        "Every row is the default cell of protocol v1b: the flood input as provided, the closure level the "
        "reference-cell sentence names, the public services unless the access-gap record says pitch, the frame's "
        "own anchors and weights. The ensemble has not run, so every headline slot is not_evaluated.",
        "source_timestamp is the last date of the flood input's source period at 00:00:00 UTC: the schema takes an "
        "instant, and the flood input has no time of day. Each input states its own source time.",
        "The component records were produced by floodguard.normalisation and the confidence records by "
        "floodguard.confidence under the two signed protocol files, from the measurements each record echoes.",
        rules.binding.frame.lane_disclosure,
        CLASS_E_WORDING,
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_id": SCHEMA_ID,
        "dataset_mode": FIXTURE_MODE if fixture else CANDIDATE_MODE,
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": flood.source_instant,
        "generated_at": generated_at,
        "source_name": source_name,
        "data_version": data_version,
        "git_commit": git_commit,
        "case": {
            "case_id": case.case_id,
            "kind": case.kind,
            "title_en": case.title_en,
            "title_th": case.title_th,
            "frame": case.frame,
            "case_reference_date": None if case.case_reference_date is None else case.case_reference_date.isoformat(),
            "fixture_notice": case.fixture_notice if fixture else None,
        },
        "protocol_sha256": protocol_hashes(rules.binding.frame),
        "evidence_tier_model_version": "evidence_tiers_v1",
        "normalisation_version": rules.binding.frame.version,
        "confidence_rule_version": rules.binding.rule.version,
        "class_rule_version": "class_rule_v1",
        "secondary_class_rule_version": rules.binding.class_rule_v2["version"],
        "scoring_frame": header,
        "publication_eligibility": eligibility,
        "inputs": [dict(item) for item in inputs],
        "assumptions": list(dict.fromkeys(listed)),
        "rows": rows,
    }


def case_spec_from_protocol(
    rules: AssessmentRules,
    case_id: str,
    *,
    title_en: str,
    title_th: str,
    frame: str,
    scenario_base: str | None = None,
) -> CaseSpec:
    """Build the :class:`CaseSpec` of a case of protocol v1a ``case_portfolio``.

    The lane, the tier and the reference date are those of the protocol. A case in a scenario lane carries the
    definition protocol v1a gives its lane as its scenario declaration, under the lane's own identifier.

    Raises:
        PlanningAssessmentError: for a case that is not in the portfolio.
    """

    known = rules.binding.cases.get(case_id)
    if known is None:
        raise PlanningAssessmentError(f"{case_id!r} is not a case of protocol v1a case_portfolio")
    reference = None if known.case_reference_date is None else date.fromisoformat(known.case_reference_date)
    scenario = known.lane in SCENARIO_LANES
    declaration = None
    if scenario:
        display = rules.lane_display_texts.get(known.lane)
        declaration = rules.lane_definitions[known.lane] + (f" Shown as: {display}." if display else "")
    return CaseSpec(
        case_id=case_id,
        kind=PORTFOLIO_KIND,
        title_en=title_en,
        title_th=title_th,
        frame=frame,
        case_reference_date=reference,
        lane=known.lane,
        tier=known.tier,
        scenario_id=known.lane if scenario else None,
        scenario_declaration=declaration,
        scenario_base=scenario_base if scenario else None,
    )


# ---------------------------------------------------------------------------
# Guardrails and verification
# ---------------------------------------------------------------------------


def lane_purity_record(pairs: Mapping[str, tuple[Any, Any]]) -> dict[str, Any]:
    """Compare, pair by pair, what two stages say of the one flood input, routing context and closure rule (GR3).

    Protocol v1a, guardrail GR3: "The five components of a row come from one flood input, one routing context
    and one closure rule. The planning verifier must check the input hashes." Each pair holds the value one
    stage used and the value another stage recorded for the same thing (an identifier or a SHA-256).

    Returns:
        The pairs that were compared, each with ``same: true``.

    Raises:
        LanePurityError: when a pair differs, or nothing was compared.
    """

    if not pairs:
        raise LanePurityError("guardrail GR3: nothing was compared")
    differing = sorted(name for name, (first, second) in pairs.items() if first != second or first is None)
    if differing:
        raise LanePurityError(
            "guardrail GR3: the components would not come from one flood input, one routing context and one "
            f"closure rule; these differ between the stages: {differing}"
        )
    return {
        "guardrail": "GR3_lane_purity",
        "result": "PASS",
        "compared": {name: {"value": first, "same": True} for name, (first, _second) in sorted(pairs.items())},
    }


def guardrail_report(
    overlay: Mapping[str, Any],
    rules: AssessmentRules,
    *,
    reporting_units: Sequence[str],
    lane: str,
) -> dict[str, Any]:
    """Check the guardrails of protocol v1a on an assembled overlay and say what was checked.

    The overlay validator checks each row against itself. This adds what belongs to a case: every reporting
    unit has exactly one row in the lane of the case ("Every cell of every case is reported whatever it
    shows"), and every row names the same flood input, routing context and closure rule.

    Raises:
        PlanningAssessmentError: for a guardrail that does not hold.
    """

    rows = [row for row in overlay["rows"] if row["lane"] == lane]
    found = sorted(row["unit_id"] for row in rows)
    if found != sorted(reporting_units):
        missing = sorted(set(reporting_units) - set(found))
        other = sorted({unit for unit in found if unit not in reporting_units or found.count(unit) > 1})
        raise PlanningAssessmentError(
            f"every reporting unit of the case has exactly one row in lane {lane}: missing {missing}; not of the "
            f"frame, or repeated: {other}"
        )
    lineages = {
        (row["lineage"]["flood_input_id"], row["lineage"]["routing_context_id"],
         row["lineage"]["closure_rule"]["version"], row["lineage"]["closure_rule"]["level"],
         row["lineage"]["closure_rule"]["closure_basis"])
        for row in rows
    }
    if len(lineages) != 1:
        raise LanePurityError("guardrail GR3: the rows of a case name one flood input, one routing context and one closure rule")
    gr1_rows = [row for row in rows if row["confidence"]["guardrail_gr1"]["applies"]]
    for row in gr1_rows:
        if row["action_class"] is not None or row["would_be_class"] is not None or row["class_v2"]["result"] is not None:
            raise PlanningAssessmentError(f"guardrail GR1: unit {row['unit_id']} has fewer residents than the minimum and carries a class")
    complete = [row for row in rows if all(record is not None for record in row["components"].values())]
    gr2: dict[str, Any] = {"result": "PASS", "rows_checked": 0}
    if complete:
        try:
            gr2 = normalisation.reject_batch_scaled_components(
                rules.binding.frame,
                [{"unit_id": row["unit_id"], "normalisation_version": row["normalisation_version"],
                  "components": dict(row["components"])} for row in complete],
            )
        except NormalisationError as error:
            raise PlanningAssessmentError(str(error)) from error
    gr2["rows_with_a_component_not_computed"] = len(rows) - len(complete)
    gr2["note"] = ("Every record of a row with all five components is recomputed from the inputs it echoes. The "
                   "overlay parser (floodguard.planning_overlay) recomputes the records of every other row one by one.")
    if dict(overlay["protocol_sha256"]) != protocol_hashes(rules.binding.frame):
        raise PlanningAssessmentError("guardrail GR5: the overlay does not name the two protocol files in force")
    lowest = rights.minimum_level(item["rights_level"] for item in overlay["inputs"])
    if overlay["publication_eligibility"] != lowest:
        raise PlanningAssessmentError("guardrail GR6: the rights level of the overlay is the minimum across its lineage")
    breaches = [row["unit_id"] for row in rows
                if row["lane"] == "OBS" and row["temporal_relation"] != EVENT_ALIGNED and row["action_class"] in CLASSES_ABOVE_E]
    if breaches:
        raise PlanningAssessmentError(f"guardrail GR7: OBS rows that are not event-aligned carry a class above E: {breaches}")
    if any(row["headline_stability"]["status"] != HEADLINE_NOT_EVALUATED for row in rows):
        raise PlanningAssessmentError("guardrail GR8: no ensemble has run, so every headline slot is not_evaluated")
    flood_id, context_id, version, level, basis = next(iter(lineages))
    return {
        "every_reporting_unit_has_one_row": {"result": "PASS", "units": len(found), "lane": lane},
        "GR1_minimum_denominators": {"result": "PASS", "units_without_a_class": len(gr1_rows),
                                     "unit_residents_min_for_class": rules.binding.rule.gr1_unit_residents_min_for_class},
        "GR2_no_max_normalisation": gr2,
        "GR3_lane_purity": {"result": "PASS", "flood_input_id": flood_id, "routing_context_id": context_id,
                            "closure_rule": {"version": version, "level": level, "closure_basis": basis},
                            "lane_disclosure": rules.binding.frame.lane_disclosure},
        "GR5_blinding": {"result": "PASS", "protocol_sha256": dict(overlay["protocol_sha256"]),
                         "note": "Both protocol files were in force when the rules were read."},
        "GR6_publication_eligibility": {"result": "PASS", "publication_eligibility": lowest,
                                        "lineage_levels": {item["input_id"]: item["rights_level"] for item in overlay["inputs"]}},
        "GR7_temporal_honesty": {"result": "PASS", "obs_rows_not_event_aligned": sum(
            1 for row in rows if row["lane"] == "OBS" and row["temporal_relation"] != EVENT_ALIGNED)},
        "GR8_headline_stability": {"result": "PASS", "status_of_every_row": HEADLINE_NOT_EVALUATED,
                                   "class_retention_min": rules.headline_class_retention_min,
                                   "note": "The ensemble is plan task E10. No class is headlined before it has run."},
    }


def write_assessment(
    overlay: Mapping[str, Any],
    path: Path | str,
    schema: Mapping[str, Any],
    rules: AssessmentRules,
    *,
    rights_basis_4009: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an overlay against the protocol files in force and write it; return path, bytes and SHA-256.

    This is ``floodguard.planning_overlay.write_overlay`` with the protocol binding: a refused overlay is
    never written, and only a public overlay may be written under ``apps/web/public``.

    Raises:
        floodguard.planning_overlay.PlanningOverlayError: when the overlay is refused.
    """

    return write_overlay(overlay, path, schema, binding=rules.binding, rights_basis_4009=rights_basis_4009)


def verify_assessment(
    path: Path | str,
    schema: Mapping[str, Any],
    rules: AssessmentRules,
    *,
    reporting_units: Sequence[str],
    lane: str,
    expected_input_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read a written overlay back and verify it: the validator bound to the protocols, then the guardrails.

    Args:
        path: The overlay file.
        schema: The overlay JSON schema.
        rules: The rules of the protocol files in force.
        reporting_units: The reporting units of the case.
        lane: The lane of the case.
        expected_input_sha256: ``input_id -> SHA-256`` of the lineage inputs, when the caller holds them: the
            overlay must name exactly these (guardrail GR3, "the planning verifier must check the input hashes").

    Returns:
        ``verified``, the problems found (code, path, message), the guardrail report and the summary of the overlay.
    """

    problems: list[dict[str, str]] = []
    try:
        overlay = load_overlay(path, schema, binding=rules.binding)
    except PlanningOverlayError as error:
        return {"verified": False, "problems": [_problem(item) for item in error.problems], "guardrails": None, "summary": None}
    guardrails = None
    try:
        guardrails = guardrail_report(overlay, rules, reporting_units=reporting_units, lane=lane)
    except PlanningAssessmentError as error:
        problems.append({"code": "guardrail", "path": "$", "message": str(error)})
    if expected_input_sha256 is not None:
        named = {item["input_id"]: item["sha256"] for item in overlay["inputs"]}
        if named != dict(expected_input_sha256):
            differing = sorted(key for key in {*named, *expected_input_sha256} if named.get(key) != expected_input_sha256.get(key))
            problems.append({"code": "lineage_hash", "path": "$.inputs",
                             "message": f"the overlay does not name the inputs it was computed from: {differing}"})
    return {"verified": not problems, "problems": problems, "guardrails": guardrails, "summary": summarise_overlay(overlay)}


def _problem(item: OverlayProblem) -> dict[str, str]:
    return {"code": item.code, "path": item.path, "message": item.message}
