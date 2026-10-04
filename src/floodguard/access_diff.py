"""Access difference between a baseline run and a flooded run (plan task E5; plan 3.1, stage P4).

Protocol v1a (``scoring_frame.components``) states two components that need this difference:

* access gap: "Baseline-access-weighted mean of newly-lost access shares, counted only for people who had
  access at baseline" (requirement EQ-04), for the hospital service (vehicle, 30 minutes), the main-road
  entry (vehicle, 15 minutes) and, at pitch level, the DDPM located shelter (walking, 30 minutes);
* road criticality: "100 x residents with a baseline route to any hospital or main road who lose all routes /
  those residents".

This module holds the difference itself and nothing else. For one case, one flood level and one closure level
it takes the travel time of every demand cell in the baseline run and in the flooded run and returns, per
unit, the counts those two definitions name:

* residents with baseline access to a service within a threshold, and those among them who no longer have it
  in the flooded run (newly lost). A resident with no baseline access is never counted as losing it;
* residents with a baseline route to any hospital or main-road entry, and those among them with no route to
  any of them in the flooded run.

**These are inputs of the two components. This module computes no component value, no FPPS, no A-E class and
no ensemble**, and it averages nothing over services: ``floodguard.normalisation.access_gap`` and
``road_criticality`` do that in plan task E8, from the mappings :func:`unit_rows` writes for them.

**The rows hold counts of residents and no ratio of them.** How close the counts are to the components is said
plainly, here and in every table. The road-criticality component is 100 x ``residents_losing_all_routes /
residents_with_baseline_route``, so that ratio is not written. The access-gap component is 100 x the mean of
the newly-lost shares of the services (``newly lost / baseline access``, at each service's access-gap
threshold), weighted by baseline access; one service's share equals it wherever the services have the same
share, and at a long threshold it can equal the road-criticality ratio, so no share is written either. Where
a denominator is zero the row carries a reason code: the protocol states no value for that case and none is
made up here (open points E5-OP2 and E5-OP8).

How the two runs are made, each as the signed files and the existing code state it:

* A flooded run is the baseline graph with the edges closure rule v1 closes taken out and the edges it delays
  slowed (``floodguard.closure_rules``, protocol v1b ``closure_rule_v1``). :func:`closure_arguments` reads the
  length thresholds and the strict-level delay rule from the protocol and refuses a protocol whose parameters
  are not the ones ``closure_rules`` applies.
* Travel time is the one ``floodguard.evidence_scenarios.calculate_total_access`` models: the fastest modelled
  route from the road node a cell snaps to (within 250 m) to the nearest destination, plus the two connectors
  at 5 km/h. :func:`cell_minutes` grows one tree from all destinations of a service at once
  (``floodguard.critical_links.shortest_path_tree``), because the main-road service has one destination per
  node of a trunk or primary edge. The tests compare it with ``calculate_total_access``.
* A cell is connected when it snaps to a node of the **baseline** graph. The same cells are compared in both
  runs: a cell whose node loses every edge is a cell that lost its routes, not a cell without a graph.
* Destinations are the same in both runs. A hospital, a shelter or a main-road entry inside the flood extent
  stays a destination: the protocols do not say otherwise (see :data:`OPEN_POINTS`).

A closure is a modelled assumption (``closure_basis``), not an observed closure, and nothing here is an
observation of a flood, a warning of any kind or an operational product.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from floodguard import closure_rules, critical_links
from floodguard.evidence_scenarios import CONNECTOR_SPEED_KMH, FACILITY_SNAP_LIMIT_M, POPULATION_SNAP_LIMIT_M

ACCESS_DIFF_VERSION = "access_diff_v1"
UNIT_TABLE_SCHEMA = "floodguard.access_diff_units.v2"

VEHICLE, WALKING = "vehicle", "walking"
CONTEXT_TRAVEL_MODES: Mapping[str, str] = {VEHICLE: "legacy_vehicle", WALKING: "walking"}
"""The ``travel_mode`` of the planning context that serves each mode of protocol v1a."""

PUBLIC_LEVEL, PITCH_LEVEL = "public", "pitch"
HOSPITAL, MAIN_ROAD_ENTRY, DDPM_LOCATED_SHELTER = "hospital", "main_road_entry", "ddpm_located_shelter"
ROUTE_SERVICES: tuple[str, ...] = (HOSPITAL, MAIN_ROAD_ENTRY)
"""The services of the road-criticality definition: "a baseline route to any hospital or main road"."""

NO_BASELINE_ACCESS = "no_resident_with_baseline_access"
NO_BASELINE_ROUTE = "no_resident_with_a_baseline_route"
CELL_IN_ONE_UNIT = "cell_centre_in_one_unit"
CELL_IN_NO_UNIT = "cell_centre_in_no_unit"
CELL_IN_SEVERAL_UNITS = "cell_centre_in_more_than_one_unit"

STRICT_DELAY_WORDING = "is delayed with k = 2"
"""The words of protocol v1b ``closure_rule_v1.delay_under_strict.rule`` that decide the strict-level delay."""

OPEN_POINTS: tuple[Mapping[str, str], ...] = (
    {
        "id": "E5-OP1",
        "point": "Which unit a demand cell counts for.",
        "signed_files_say": "Protocol v1b corridor_polygon.context_call.tambon_attribution: 'Done downstream of the "
                            "context build.' Protocol v1a states the cell-centre rule for exposure, and v1b for the "
                            "SE2-blind district total; neither states it for the access tables.",
        "what_this_task_does": "A WorldPop 2020 cell counts for the unit whose polygon holds its centre. A cell whose "
                               "centre lies in no unit, or in more than one, is counted in no unit and reported.",
        "for_the_owners": "Whether the cell-centre rule is the rule for the access tables too.",
    },
    {
        "id": "E5-OP2",
        "point": "A unit where nobody had baseline access to a service, or nobody had a baseline route.",
        "signed_files_say": "The access gap is counted 'only for people who had access at baseline' and road "
                            "criticality divides by the residents with a baseline route. Nothing on a zero denominator.",
        "what_this_task_does": "Writes the counts and a reason code. No value is put in the place of the missing "
                               "ratio. floodguard.normalisation refuses such a unit in the same way.",
        "for_the_owners": "What such a unit gets in task E8: no component, or a stated value.",
    },
    {
        "id": "E5-OP3",
        "point": "Residents whose cell does not snap to the road graph within 250 m.",
        "signed_files_say": "Nothing. The context builder leaves such a cell without a node, and "
                            "calculate_total_access reports it as missing graph coverage.",
        "what_this_task_does": "Reports them per unit as not connected. They have no modelled access in either run, "
                               "so they are in no numerator and no denominator.",
        "for_the_owners": "Whether they stay outside both, as residents with no baseline access do.",
    },
    {
        "id": "E5-OP4",
        "point": "A destination inside the flood extent.",
        "signed_files_say": "The main-road entry is 'the nearest node on a trunk or primary edge (including links) "
                            "inside the routing context'. Nothing on an entry whose main-road edges are closed in the "
                            "flooded run, or on a hospital or shelter inside the extent (class rule v2 trigger C reads "
                            "the latter, in task E8).",
        "what_this_task_does": "Keeps the same destinations in both runs. A resident whose cell snaps to a main-road "
                               "entry keeps that entry at zero road distance even when every main-road edge at it is "
                               "closed. The receipt counts the entries in that state.",
        "for_the_owners": "Whether a main-road entry whose trunk or primary edges are all closed is still an entry.",
    },
    {
        "id": "E5-OP5",
        "point": "Which planning context the walking service uses.",
        "signed_files_say": "The DDPM located shelter service is walking, 30 minutes (v1a pitch_level_adds, v1b "
                            "facility_sets, owner choice 7). The E4 build of record is a vehicle context, and decision "
                            "R13 accepted a compute window for that build only.",
        "what_this_task_does": "Uses a walking context built by the unchanged E4 builder (travel mode walking: 5 km/h "
                               "on OSM roads and paths where walking is not prohibited) when one is supplied, and says "
                               "whether it is a build of record or a candidate. The vehicle context is never walked. A "
                               "candidate was built by this task's lane without a declared compute window, which is "
                               "outside what plan row E5 names; the builder keeps a candidate's receipt outside Git, so "
                               "the run that uses it writes a report of that build into outputs/planning_v1 and "
                               "registers it. Tables that rest on a candidate are marked as not usable by task E8.",
        "for_the_owners": "A walking build of record in a declared compute window they accept (plan 5 item 1; decision "
                          "R13 covers the vehicle build only), with its receipt in outputs/planning_v1; then a new run "
                          "of this task. Until then the shelter tables are not inputs of task E8.",
    },
    {
        "id": "E5-OP6",
        "point": "A grade-join connector inside the flood extent.",
        "signed_files_say": "Closure rule v1 measures the length of an edge inside the extent. A grade join (decision "
                            "D13) has no length.",
        "what_this_task_does": "A connector is never intersected, so it stays open under every level. The receipt "
                               "counts the connectors whose coordinate lies inside the extent.",
        "for_the_owners": "Whether a join inside the extent closes with the edges it links.",
    },
    {
        "id": "E5-OP7",
        "point": "Which runs the difference is taken between when an edge is delayed.",
        "signed_files_say": "Plan 3.1 P4: calculate_total_access unchanged, run twice, on the original and the "
                            "modified edges. The protocols name no function.",
        "what_this_task_does": "Both runs use one multi-source tree per service (floodguard.critical_links), which "
                               "gives the travel times of calculate_total_access; tests and a check on the hospital "
                               "service of the real context compare the two.",
        "for_the_owners": "Nothing, unless the per-destination runs of calculate_total_access are wanted as the record.",
    },
    {
        "id": "E5-OP8",
        "point": "Ratios of the counts.",
        "signed_files_say": "Protocol v1a: road criticality is '100 x residents with a baseline route to any hospital "
                            "or main road who lose all routes / those residents'; the access gap is the "
                            "'baseline-access-weighted mean of newly-lost access shares'. Plan row E5 names the access "
                            "difference and a per-tambon table; the components belong to task E8.",
        "what_this_task_does": "Writes counts of residents and no ratio of them. The ratio of the two route counts is "
                               "the road-criticality component divided by 100. A service's newly-lost share is one "
                               "step from the access gap: it equals that component divided by 100 wherever the services "
                               "have the same share, and at a long threshold it can equal the route ratio. The first "
                               "run of this task wrote both ratios for each tambon; the run that replaced it writes "
                               "neither, and its receipt says so.",
        "for_the_owners": "Whether the per-service newly-lost share is wanted from this task as a descriptive figure, "
                          "or comes from task E8 with the components; and whether the first table, which is in the "
                          "Git history, needs more than the note in the receipt that replaced it.",
    },
)
"""Points the signed files leave open for this task. Each is reported; none is decided here."""


class AccessDiffError(ValueError):
    """Raised when the inputs of the access difference break its contract, or a protocol parameter is not the code's."""


# ---------------------------------------------------------------------------
# What the protocols state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceRule:
    """One service of the access-gap component, as the two protocols declare it."""

    service: str
    mode: str
    thresholds_minutes: tuple[int, ...]
    access_gap_threshold_minutes: int
    publication_level: str

    def as_record(self) -> dict[str, Any]:
        """Return the rule as plain JSON values."""

        return {
            "service": self.service,
            "mode": self.mode,
            "thresholds_minutes": list(self.thresholds_minutes),
            "access_gap_threshold_minutes": self.access_gap_threshold_minutes,
            "publication_level": self.publication_level,
        }


def service_rules(v1a: Mapping[str, Any], v1b: Mapping[str, Any]) -> tuple[ServiceRule, ...]:
    """Read the services of the access gap from the two protocols and check that they agree.

    Protocol v1a (``scoring_frame.components.access_gap_0_100``) names each service with its mode and the
    threshold of the access gap; protocol v1b (``facility_sets.services``) repeats them and lists the
    thresholds that are reported.

    Raises:
        AccessDiffError: when a service of v1a is not in v1b, or the two files state another mode or threshold.
    """

    try:
        component = v1a["scoring_frame"]["components"]["access_gap_0_100"]
        engineering = v1b["facility_sets"]["services"]
        levels = ((PUBLIC_LEVEL, component["public_level_services"]), (PITCH_LEVEL, component["pitch_level_adds"]))
        rules: list[ServiceRule] = []
        for level, rows in levels:
            for row in rows:
                name = str(row["service"])
                if name not in engineering:
                    raise AccessDiffError(f"protocol v1b facility_sets names no service {name!r}")
                declared = engineering[name]
                thresholds = tuple(int(value) for value in declared["thresholds_minutes"])
                gap = int(row["threshold_minutes"])
                if (declared["mode"], int(declared["access_gap_threshold_minutes"])) != (row["mode"], gap):
                    raise AccessDiffError(f"protocol v1a and v1b state another mode or threshold for {name!r}")
                if gap not in thresholds or row["mode"] not in CONTEXT_TRAVEL_MODES:
                    raise AccessDiffError(f"service {name!r}: the access-gap threshold or the mode is not one this code runs")
                if level == PITCH_LEVEL and declared.get("publication_level") != PITCH_LEVEL:
                    raise AccessDiffError(f"service {name!r} is added at pitch level in v1a and is not pitch level in v1b")
                rules.append(ServiceRule(name, str(row["mode"]), thresholds, gap, level))
    except (KeyError, TypeError, ValueError) as error:
        raise AccessDiffError(f"the protocol files do not hold the access services: {error!r}") from error
    if len({rule.service for rule in rules}) != len(rules) or not rules:
        raise AccessDiffError("the access services must be named once each")
    return tuple(rules)


def closure_arguments(v1b: Mapping[str, Any]) -> dict[str, Any]:
    """Return what ``closure_rules`` needs from protocol v1b: the length thresholds and the strict-level delay rule.

    The thresholds are those of the plan (``parameters.length_threshold_m_by_road_class``) and those the owners
    decided for motorway, residential and unclassified roads (``unassigned_road_classes``, owner choice 4). The
    strict level delays an edge that stays open (``delay_under_strict``, owner choice 5).

    Raises:
        AccessDiffError: when a parameter of the protocol is not the one ``floodguard.closure_rules`` applies,
            or the strict-level delay rule is not stated in the words this code reads.
    """

    try:
        block = v1b["closure_rule_v1"]
        parameters = block["parameters"]
        declared = {
            "version": block["version"],
            "closed_fraction_min": parameters["closed_fraction_min"],
            "bridge_culvert_closed_fraction_min": parameters["bridge_culvert_closed_fraction_min"],
            "delay_min_intersected_length_m": parameters["delay_min_intersected_length_m"],
            "delay_factor_k": {level: block["levels"][level]["delay_factor_k"] for level in closure_rules.LEVELS},
            "plan_thresholds": {key: float(value) for key, value in parameters["length_threshold_m_by_road_class"].items()},
        }
        applied = {
            "version": closure_rules.CLOSURE_RULE_VERSION,
            "closed_fraction_min": closure_rules.CLOSED_FRACTION_MIN,
            "bridge_culvert_closed_fraction_min": closure_rules.BRIDGE_CULVERT_CLOSED_FRACTION_MIN,
            "delay_min_intersected_length_m": closure_rules.DELAY_MIN_INTERSECTED_LENGTH_M,
            "delay_factor_k": dict(closure_rules.DELAY_FACTOR_K),
            "plan_thresholds": dict(closure_rules.PLAN_LENGTH_THRESHOLD_M),
        }
        if block["status"] != "fixed" or declared != applied:
            raise AccessDiffError("protocol v1b closure_rule_v1 is not fixed, or its parameters are not the ones "
                                  "floodguard.closure_rules applies")
        thresholds = {**declared["plan_thresholds"],
                      **{str(key): float(value) for key, value in block["unassigned_road_classes"]["length_threshold_m"].items()}}
        strict_rule = str(block["delay_under_strict"]["rule"])
    except (KeyError, TypeError, ValueError) as error:
        raise AccessDiffError(f"protocol v1b does not hold the closure parameters: {error!r}") from error
    if STRICT_DELAY_WORDING not in strict_rule or not strict_rule.startswith("Under strict"):
        raise AccessDiffError("protocol v1b states the strict-level delay rule in other words than this code reads")
    return {
        "length_thresholds_m": thresholds,
        "strict_delays": True,
        "strict_delay_rule": strict_rule,
        "delay_factor_k": declared["delay_factor_k"],
        "culvert_tag_handling": str(block["culvert_tag_handling"]["rule"]),
    }


# ---------------------------------------------------------------------------
# One run: the travel time of every connected cell
# ---------------------------------------------------------------------------


def graph_nodes(edges: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return the nodes an edge list uses."""

    nodes: set[str] = set()
    for edge in edges:
        nodes.add(edge["from_node"])
        nodes.add(edge["to_node"])
    return nodes


def cell_minutes(
    population: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
    *,
    baseline_nodes: Iterable[str],
    snap_limit_m: float = POPULATION_SNAP_LIMIT_M,
    facility_snap_limit_m: float = FACILITY_SNAP_LIMIT_M,
) -> dict[str, float | None]:
    """Return the modelled minutes from every connected cell to its nearest destination, in one run.

    The travel time is that of ``calculate_total_access``: the connector of the destination, the fastest
    route on the undirected graph and the connector of the cell, both connectors at 5 km/h.

    Args:
        population: Demand cells with ``population_id``, ``node_id`` and ``snap_distance_m``.
        edges: The edges of this run: the baseline edges, or the edges closure rule v1 leaves.
        destinations: The destinations of one service (``facility_id``, ``node_id``, ``snap_distance_m``).
        baseline_nodes: The nodes of the baseline graph. A cell is connected when it snaps to one of them
            within the limit, in every run, so both runs cover the same cells.
        snap_limit_m: The largest snap distance of a cell (250 m).
        facility_snap_limit_m: The largest snap distance of a destination (100 m).

    Returns:
        ``population_id -> minutes`` for every connected cell; ``None`` where the cell is connected and no
        destination can be reached. A cell that is not connected is not in the result.

    Raises:
        AccessDiffError: for a repeated population ID, or an edge that uses a node outside the baseline graph.
    """

    known = set(baseline_nodes)
    if not graph_nodes(edges) <= known:
        raise AccessDiffError("a run uses a node that the baseline graph does not have")
    try:
        tree = critical_links.shortest_path_tree(edges, destinations, nodes=known, facility_snap_limit_m=facility_snap_limit_m)
    except critical_links.CriticalLinkError as error:
        raise AccessDiffError(str(error)) from error
    reached = tree["minutes"]
    result: dict[str, float | None] = {}
    for row in population:
        identifier = row["population_id"]
        if identifier in result:
            raise AccessDiffError("population IDs must be unique")
        node, snap = row.get("node_id"), row.get("snap_distance_m")
        if node is None or snap is None or snap > snap_limit_m or node not in known:
            continue
        minutes = reached.get(node)
        result[identifier] = None if minutes is None else minutes + snap / 1000 / CONNECTOR_SPEED_KMH * 60
    return result


def flooded_edges(
    level: str,
    edges: Sequence[Mapping[str, Any]],
    intersections: Sequence[Mapping[str, Any]],
    *,
    flood_input_id: str,
    arguments: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply one level of closure rule v1 and return the edges of the flooded run with the closure result.

    Args:
        level: ``strict``, ``central`` or ``permissive``.
        edges: The baseline edges.
        intersections: ``closure_rules.edge_intersections`` of those edges with one flood extent.
        flood_input_id: The flood input, for ``closure_basis``.
        arguments: The output of :func:`closure_arguments`.

    Raises:
        AccessDiffError: when ``closure_rules`` refuses the inputs.
    """

    try:
        result = closure_rules.apply_closure_rule(
            level, edges, intersections, flood_input_id=flood_input_id,
            length_thresholds_m=arguments["length_thresholds_m"], strict_delays=arguments["strict_delays"])
        return closure_rules.modified_edges(edges, result), result
    except closure_rules.ClosureRuleError as error:
        raise AccessDiffError(str(error)) from error


def closure_summary(result: Mapping[str, Any], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count the closed and delayed edges of one closure result, by road class, and bind the result by SHA-256.

    The SHA-256 is that of the closed edge IDs and the delayed edges with their factors, as canonical JSON.
    """

    by_id = {edge["edge_id"]: edge for edge in edges}
    closed = list(result["closed_edge_ids"])
    delayed = [dict(row) for row in result["delayed_edges"]]
    factors = [row["travel_time_factor"] for row in delayed]
    document = json.dumps({"closed_edge_ids": closed, "delayed_edges": delayed}, sort_keys=True, separators=(",", ":"),
                          allow_nan=False)
    return {
        "closure_rule_version": result["closure_rule_version"],
        "level": result["level"],
        "closure_basis": result["closure_basis"],
        "edges": len(by_id),
        "intersected_edges": result["intersected_edge_count"],
        "closed_edges": len(closed),
        "delayed_edges": len(delayed),
        "intersected_edges_left_open": result["intersected_edge_count"] - len(closed) - len(delayed),
        "closed_edges_by_road_class": dict(sorted(Counter(str(by_id[edge_id].get("road_class")) for edge_id in closed).items())),
        "delayed_edges_by_road_class": dict(sorted(Counter(str(by_id[row["edge_id"]].get("road_class")) for row in delayed).items())),
        "closed_bridge_tagged_edges": sum(1 for edge_id in closed if closure_rules.is_bridge_or_culvert(by_id[edge_id])),
        "largest_travel_time_factor": max(factors) if factors else None,
        "closure_result_sha256": hashlib.sha256(document.encode("ascii")).hexdigest(),
    }


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def assign_cells(population: Sequence[Mapping[str, Any]], units: Sequence[tuple[str, Any]]) -> dict[str, dict[str, Any]]:
    """Say which unit each demand cell counts for: the unit whose polygon holds the centre of the cell.

    Args:
        population: Demand cells with ``population_id``, ``longitude`` and ``latitude`` (the cell centre, WGS84).
        units: ``(unit ID, shapely polygon in WGS84)`` pairs.

    Returns:
        ``population_id -> {"unit_id", "unit_assignment"}``. ``unit_id`` is ``None`` when the centre lies in no
        unit, or in more than one (on a shared boundary, or where two polygons overlap): the protocols give no
        rule for those, so none is applied.

    Raises:
        AccessDiffError: for a repeated unit ID or population ID.
    """

    import shapely

    identifiers = [str(unit_id) for unit_id, _geometry in units]
    if len(set(identifiers)) != len(identifiers):
        raise AccessDiffError("unit IDs must be unique")
    rows = list(population)
    if len({row["population_id"] for row in rows}) != len(rows):
        raise AccessDiffError("population IDs must be unique")
    holders: dict[int, list[str]] = defaultdict(list)
    if identifiers and rows:
        centres = shapely.points([float(row["longitude"]) for row in rows], [float(row["latitude"]) for row in rows])
        tree = shapely.STRtree([geometry for _unit_id, geometry in units])
        for cell_index, unit_index in zip(*tree.query(centres, predicate="intersects")):
            holders[int(cell_index)].append(identifiers[int(unit_index)])
    result: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(rows):
        found = sorted(holders.get(position, []))
        if len(found) == 1:
            result[row["population_id"]] = {"unit_id": found[0], "unit_assignment": CELL_IN_ONE_UNIT}
        else:
            result[row["population_id"]] = {"unit_id": None, "unit_assignment": CELL_IN_SEVERAL_UNITS if found else CELL_IN_NO_UNIT}
    return result


def demand_cells(population: Sequence[Mapping[str, Any]], assignment: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the cells of the difference: ``population_id``, ``unit_id`` (or ``None``) and ``residents``.

    Raises:
        AccessDiffError: for a cell without an assignment, or a resident count that is not a finite number, 0 or more.
    """

    cells = []
    for row in sorted(population, key=lambda item: item["population_id"]):
        residents = row["total_population"]
        if isinstance(residents, bool) or not isinstance(residents, (int, float)) or not math.isfinite(residents) or residents < 0:
            raise AccessDiffError("a resident count must be a finite number, 0 or more")
        if row["population_id"] not in assignment:
            raise AccessDiffError("every demand cell needs a unit assignment")
        cells.append({"population_id": row["population_id"], "unit_id": assignment[row["population_id"]]["unit_id"],
                      "residents": float(residents)})
    return cells


# ---------------------------------------------------------------------------
# The difference
# ---------------------------------------------------------------------------


def _checked_runs(cells: Sequence[Mapping[str, Any]], baseline: Mapping[str, float | None],
                  flooded: Mapping[str, float | None]) -> None:
    """Refuse two runs that do not cover the same connected cells, a repeated cell, a resident count that is no
    count and a travel time that is no time."""

    if set(baseline) != set(flooded):
        raise AccessDiffError("the baseline run and the flooded run must cover the same connected cells")
    identifiers = [cell["population_id"] for cell in cells]
    if len(set(identifiers)) != len(identifiers):
        raise AccessDiffError("population IDs must be unique")
    for cell in cells:
        residents = cell["residents"]
        if isinstance(residents, bool) or not isinstance(residents, (int, float)) or not math.isfinite(residents) or residents < 0:
            raise AccessDiffError("a resident count must be a finite number, 0 or more")
    for run in (baseline, flooded):
        for minutes in run.values():
            if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, (int, float))
                                        or not math.isfinite(minutes) or minutes < 0):
                raise AccessDiffError("travel time must be a finite number of minutes, 0 or more, or None for no route")


def service_diff(
    cells: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, float | None],
    flooded: Mapping[str, float | None],
    thresholds_minutes: Sequence[int],
) -> dict[str, Any]:
    """Compare the two runs of one service over one group of cells (a unit, or the whole frame).

    A resident has access within a threshold when the modelled time is at most the threshold. A resident is
    newly lost when they had access in the baseline run and do not have it in the flooded run. A resident
    without baseline access is in no numerator and no denominator (requirement EQ-04): the residents newly
    lost are always among the residents with baseline access.

    Only counts are returned. The newly-lost share (``newly_lost_residents / baseline_access_residents``) is
    not: it is one step from the access-gap component, which task E8 computes. Where nobody had baseline
    access the threshold carries ``baseline_access_unavailable_reason``; the protocol states no share for
    that case.

    Args:
        cells: The cells of the group, each with ``population_id`` and ``residents``.
        baseline: ``cell_minutes`` of the baseline run. It may cover cells outside the group.
        flooded: ``cell_minutes`` of the flooded run, for the same connected cells.
        thresholds_minutes: The thresholds to report.

    Returns:
        The residents of the group, those connected to the graph and those not, those with a route in each
        run, and per threshold: ``baseline_access_residents``, ``flooded_access_residents``,
        ``newly_lost_residents``, ``newly_gained_residents`` and ``baseline_access_unavailable_reason``.

    Raises:
        AccessDiffError: when the runs do not cover the same cells, a resident count is not a finite number,
            0 or more, or a threshold is not a positive whole number.
    """

    limits = tuple(thresholds_minutes)
    if not limits or len(set(limits)) != len(limits) or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in limits):
        raise AccessDiffError("thresholds must be distinct positive whole numbers of minutes")
    _checked_runs(cells, baseline, flooded)
    connected = [cell for cell in cells if cell["population_id"] in baseline]
    result: dict[str, Any] = {
        "residents": math.fsum(cell["residents"] for cell in cells),
        "residents_connected_to_the_graph": math.fsum(cell["residents"] for cell in connected),
        "residents_not_connected_to_the_graph": math.fsum(
            cell["residents"] for cell in cells if cell["population_id"] not in baseline),
        "residents_with_a_baseline_route": math.fsum(
            cell["residents"] for cell in connected if baseline[cell["population_id"]] is not None),
        "residents_with_a_route_in_the_flooded_run": math.fsum(
            cell["residents"] for cell in connected if flooded[cell["population_id"]] is not None),
        "thresholds_minutes": {},
    }
    for limit in limits:
        had: list[float] = []
        has: list[float] = []
        lost: list[float] = []
        gained: list[float] = []
        for cell in connected:
            before, after = baseline[cell["population_id"]], flooded[cell["population_id"]]
            access_before = before is not None and before <= limit
            access_after = after is not None and after <= limit
            if access_before:
                had.append(cell["residents"])
            if access_after:
                has.append(cell["residents"])
            if access_before and not access_after:
                lost.append(cell["residents"])
            if access_after and not access_before:
                gained.append(cell["residents"])
        baseline_access = math.fsum(had)
        result["thresholds_minutes"][str(limit)] = {
            "baseline_access_residents": baseline_access,
            "flooded_access_residents": math.fsum(has),
            "newly_lost_residents": math.fsum(lost),
            "newly_gained_residents": math.fsum(gained),
            "baseline_access_unavailable_reason": NO_BASELINE_ACCESS if baseline_access <= 0 else None,
        }
    return result


def route_diff(
    cells: Sequence[Mapping[str, Any]],
    baseline_by_service: Mapping[str, Mapping[str, float | None]],
    flooded_by_service: Mapping[str, Mapping[str, float | None]],
) -> dict[str, Any]:
    """Count the residents with a baseline route to any of the services who lose all routes.

    Road criticality (protocol v1a): "residents with a baseline route to any hospital or main road who lose
    all routes / those residents". A resident has a baseline route when any of the services can be reached in
    the baseline run, whatever the time; they lose all routes when none of them can be reached in the flooded
    run. A longer route is not a lost route.

    The two counts are returned and their ratio is not: 100 x the ratio is the road-criticality component,
    which ``floodguard.normalisation.road_criticality`` computes in plan task E8. Where nobody had a baseline
    route the result says so (``baseline_route_unavailable_reason``); the protocol states no value for that
    case.

    Args:
        cells: The cells of the group, each with ``population_id`` and ``residents``.
        baseline_by_service: ``service -> cell_minutes`` of the baseline run.
        flooded_by_service: ``service -> cell_minutes`` of the flooded run, for the same services and cells.

    Returns:
        ``services``, ``residents_with_baseline_route``, ``residents_losing_all_routes``,
        ``connected_residents_without_a_baseline_route`` and ``baseline_route_unavailable_reason``.

    Raises:
        AccessDiffError: when the services differ, or the runs do not cover the same connected cells.
    """

    services = sorted(baseline_by_service)
    if not services or services != sorted(flooded_by_service):
        raise AccessDiffError("the two runs must hold the same services")
    covered = set(baseline_by_service[services[0]])
    for service in services:
        _checked_runs(cells, baseline_by_service[service], flooded_by_service[service])
        if set(baseline_by_service[service]) != covered:
            raise AccessDiffError("every service of a route difference must cover the same connected cells")
    had: list[float] = []
    lost: list[float] = []
    never: list[float] = []
    for cell in cells:
        identifier = cell["population_id"]
        if identifier not in covered:
            continue
        before = any(baseline_by_service[service][identifier] is not None for service in services)
        after = any(flooded_by_service[service][identifier] is not None for service in services)
        if before:
            had.append(cell["residents"])
            if not after:
                lost.append(cell["residents"])
        else:
            never.append(cell["residents"])
    with_route, losing = math.fsum(had), math.fsum(lost)
    return {
        "services": services,
        "residents_with_baseline_route": with_route,
        "residents_losing_all_routes": losing,
        "connected_residents_without_a_baseline_route": math.fsum(never),
        "baseline_route_unavailable_reason": NO_BASELINE_ROUTE if with_route <= 0 else None,
    }


def unit_rows(
    cells: Sequence[Mapping[str, Any]],
    unit_ids: Sequence[str],
    services: Sequence[ServiceRule],
    baseline_by_service: Mapping[str, Mapping[str, float | None]],
    flooded_by_service: Mapping[str, Mapping[str, float | None]],
    *,
    route_services: Sequence[str] = ROUTE_SERVICES,
) -> dict[str, Any]:
    """Build the table of one case, one flood level and one closure level: one row per unit, and the whole frame.

    Each row carries the difference of every service at every reported threshold, and the two mappings task
    E8 passes on unchanged:

    * ``access_gap_inputs``: for each service, ``mode``, ``threshold_minutes`` (the access-gap threshold),
      ``baseline_access_residents`` and ``newly_lost_residents``, as ``floodguard.normalisation.access_gap``
      takes them;
    * ``road_criticality_inputs``: ``residents_losing_all_routes`` and ``residents_with_baseline_route``, as
      ``floodguard.normalisation.road_criticality`` takes them.

    No component value is computed, and the ratio of the two road-criticality counts is not written: it is the
    component divided by 100. Where a denominator is zero the row says so
    (``access_gap_inputs_unavailable_reason``, ``road_criticality_inputs_unavailable_reason``).

    Args:
        cells: The output of :func:`demand_cells`.
        unit_ids: The units of the case frame; each gets a row, with or without cells.
        services: The services of the table (:func:`service_rules`, or the public ones among them).
        baseline_by_service: ``service -> cell_minutes`` of the baseline run.
        flooded_by_service: ``service -> cell_minutes`` of the flooded run.
        route_services: The services whose routes road criticality reads.

    Returns:
        ``units`` (rows sorted by unit ID), ``whole_frame`` (the same figures over every cell) and
        ``cells_in_no_unit`` (the cells that count for no unit, and their residents).

    Raises:
        AccessDiffError: for a repeated unit, a cell of a unit that is not listed, or a missing service.
    """

    listed = [str(unit_id) for unit_id in unit_ids]
    if len(set(listed)) != len(listed):
        raise AccessDiffError("unit IDs must be unique")
    names = [rule.service for rule in services]
    if len(set(names)) != len(names) or not names:
        raise AccessDiffError("the services of a table must be named once each")
    for name in (*names, *route_services):
        if name not in baseline_by_service or name not in flooded_by_service:
            raise AccessDiffError(f"no run was made for service {name!r}")
    if not set(route_services) <= set(names):
        raise AccessDiffError("the services of the route difference must be services of the table")
    known = {cell["population_id"] for cell in cells}
    if len(known) != len(cells):
        raise AccessDiffError("population IDs must be unique")
    for name in names:
        if not set(baseline_by_service[name]) <= known:
            raise AccessDiffError(f"the run of service {name!r} covers a cell that is not a demand cell")
    grouped: dict[str, list[Mapping[str, Any]]] = {unit_id: [] for unit_id in listed}
    unassigned: list[Mapping[str, Any]] = []
    for cell in cells:
        if cell["unit_id"] is None:
            unassigned.append(cell)
        elif cell["unit_id"] in grouped:
            grouped[cell["unit_id"]].append(cell)
        else:
            raise AccessDiffError(f"a cell counts for unit {cell['unit_id']!r}, which is not a unit of the table")

    def row(group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        access: dict[str, Any] = {}
        gap_inputs: dict[str, Any] = {}
        for rule in services:
            diff = service_diff(group, baseline_by_service[rule.service], flooded_by_service[rule.service],
                                rule.thresholds_minutes)
            at_gap = diff["thresholds_minutes"][str(rule.access_gap_threshold_minutes)]
            access[rule.service] = {
                "mode": rule.mode,
                "publication_level": rule.publication_level,
                "access_gap_threshold_minutes": rule.access_gap_threshold_minutes,
                **{key: value for key, value in diff.items() if key != "residents"},
            }
            gap_inputs[rule.service] = {
                "mode": rule.mode,
                "threshold_minutes": rule.access_gap_threshold_minutes,
                "baseline_access_residents": at_gap["baseline_access_residents"],
                "newly_lost_residents": at_gap["newly_lost_residents"],
            }
        routes = route_diff(group, {name: baseline_by_service[name] for name in route_services},
                            {name: flooded_by_service[name] for name in route_services})
        nobody = all(entry["baseline_access_residents"] <= 0 for entry in gap_inputs.values())
        return {
            "residents": math.fsum(cell["residents"] for cell in group),
            "demand_cells": len(group),
            "access": access,
            "access_gap_inputs": gap_inputs,
            "access_gap_inputs_unavailable_reason": NO_BASELINE_ACCESS if nobody else None,
            "road_criticality_inputs": {
                "residents_losing_all_routes": routes["residents_losing_all_routes"],
                "residents_with_baseline_route": routes["residents_with_baseline_route"],
            },
            "road_criticality_inputs_unavailable_reason": routes["baseline_route_unavailable_reason"],
            "routes": routes,
        }

    return {
        "units": [{"unit_id": unit_id, **row(grouped[unit_id])} for unit_id in sorted(listed)],
        "whole_frame": row(list(cells)),
        "cells_in_no_unit": {
            "demand_cells": len(unassigned),
            "residents": math.fsum(cell["residents"] for cell in unassigned),
            "note": "Cells whose centre lies in no unit of the frame, or in more than one. They are in the whole "
                    "frame and in no unit row.",
        },
    }


def access_flags_differ(
    cell_runs: Mapping[str, float | None],
    reference: Mapping[str, float | None],
    thresholds_minutes: Sequence[int],
) -> dict[str, Any]:
    """Compare the travel times of one run with a reference run of the same cells (``calculate_total_access``).

    Returns:
        How many cells were compared, how many differ in having a route or in having access within any of the
        thresholds, and the largest difference in minutes among the cells with a route in both.
    """

    if set(cell_runs) != set(reference):
        raise AccessDiffError("the two runs must cover the same connected cells")
    differing = 0
    largest = 0.0
    for identifier, minutes in cell_runs.items():
        other = reference[identifier]
        if (minutes is None) != (other is None):
            differing += 1
            continue
        if minutes is None or other is None:
            continue
        largest = max(largest, abs(minutes - other))
        if any((minutes <= limit) != (other <= limit) for limit in thresholds_minutes):
            differing += 1
    return {"cells_compared": len(cell_runs), "cells_that_differ": differing, "largest_difference_minutes": largest}
