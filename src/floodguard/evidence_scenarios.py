"""Explicit planning scenarios, with missing evidence kept separate from zero.

These helpers are an additive research lane. They neither qualify flood reference
data nor change the strict decision scorer or its low-confidence class-E rule.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from floodguard.access import _facility_minutes_by_node
from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS, score_subdistricts

CONNECTOR_SPEED_KMH = 5.0
POPULATION_SNAP_LIMIT_M = 250.0
FACILITY_SNAP_LIMIT_M = 100.0
MODELLED_ROAD_SPEED_KMH = {
    "motorway": 80.0,
    "trunk": 70.0,
    "primary": 60.0,
    "secondary": 50.0,
    "tertiary": 40.0,
    "residential": 25.0,
    "unclassified": 25.0,
    "local": 20.0,
}


class EvidenceScenarioError(ValueError):
    """Raised when scenario inputs are ambiguous or numerically invalid."""


def calculate_total_access(
    population: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    facilities: Sequence[Mapping[str, Any]],
    *,
    scenario: Mapping[str, Any] | None = None,
    thresholds: Sequence[int] = (15, 30, 60),
    source_timestamp: str | None = None,
    assumptions: Sequence[str] = (),
    baseline_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare total-population access without inventing demographic groups.

    Population rows require population_id, subdistrict_id, total_population,
    node_id and snap_distance_m. Facilities require facility_id and the last two
    fields. A null node/distance or excessive snap is explicitly unconnected.
    Edges require unique edge_id/from_node/to_node and either normal_minutes or
    length_m/road_class. All travel times are modelled and edges are undirected.
    Scenario accepts closed_edge_ids, removed_facility_ids and added_facilities.
    No facility is a valid scenario; it means unavailable destination access.
    An optional result from these identical baseline inputs reuses its route
    pairs after an input-hash check. Coverage and finite-trip time comparisons
    are reported separately from legacy threshold totals.
    """
    pops = _population(population)
    sites = _facilities(facilities)
    limits = tuple(thresholds)
    if (
        not limits
        or len(set(limits)) != len(limits)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in limits
        )
    ):
        raise EvidenceScenarioError("thresholds must be unique positive integers")
    graph, edge_rows = _graph(edges)
    change = dict(scenario or {})
    if set(change) - {"closed_edge_ids", "removed_facility_ids", "added_facilities"}:
        raise EvidenceScenarioError("unknown scenario option")
    closed = _selected_ids(change.get("closed_edge_ids", ()), "closed_edge_ids")
    removed = _selected_ids(
        change.get("removed_facility_ids", ()), "removed_facility_ids"
    )
    if closed - {edge["edge_id"] for edge in edge_rows}:
        raise EvidenceScenarioError("scenario closes an unknown edge")
    if removed - {site["facility_id"] for site in sites}:
        raise EvidenceScenarioError("scenario removes an unknown facility")
    additions = _facilities(change.get("added_facilities", ()))
    if {site["facility_id"] for site in additions} & {
        site["facility_id"] for site in sites
    }:
        raise EvidenceScenarioError("added facility IDs must be new")
    selected_sites = [
        site for site in sites if site["facility_id"] not in removed
    ] + additions
    signature = hashlib.sha256(
        json.dumps([pops, edge_rows, sites], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if baseline_result is not None:
        if baseline_result.get("baseline_input_sha256") != signature:
            raise EvidenceScenarioError("baseline result does not match access inputs")
        normal_pairs = baseline_result["baseline_reachable_pairs"]
    else:
        normal_pairs = _reachable_pairs(pops, sites, graph)
    changed_graph = graph
    if closed:
        changed_graph, _ = _graph(
            [edge for edge in edge_rows if edge["edge_id"] not in closed]
        )
        # Retain isolated original nodes after closures, including zero-length trips.
        for node in graph:
            changed_graph.setdefault(node, [])
        changed_pairs = _reachable_pairs(pops, selected_sites, changed_graph)
    elif removed or additions:
        # Destination-only changes preserve existing routes and connector costs.
        changed_pairs = [
            pair for pair in normal_pairs if pair["facility_id"] not in removed
        ]
        if additions:
            changed_pairs.extend(_reachable_pairs(pops, additions, graph))
            changed_pairs.sort(
                key=lambda row: (row["population_id"], row["facility_id"])
            )
    else:
        changed_pairs = normal_pairs
    normal = _nearest_by_population(normal_pairs)
    changed = _nearest_by_population(changed_pairs)
    node_results = []
    for pop in pops:
        before = normal.get(pop["population_id"])
        after = changed.get(pop["population_id"])
        row = {**pop, "normal_access_minutes": before, "scenario_access_minutes": after}
        for threshold in limits:
            baseline_access = before is not None and before <= threshold
            scenario_access = after is not None and after <= threshold
            row[f"already_without_{threshold}_min_access"] = not baseline_access
            row[f"loses_{threshold}_min_access"] = (
                baseline_access and not scenario_access
            )
            row[f"gains_{threshold}_min_access"] = (
                not baseline_access and scenario_access
            )
        row["snap_status"] = _snap_status(pop, POPULATION_SNAP_LIMIT_M, graph)
        for label, value in (("baseline", before), ("scenario", after)):
            row[f"{label}_access_status"] = (
                "missing_graph_coverage"
                if row["snap_status"] != "connected"
                else "no_modelled_route_to_selected_destination"
                if value is None
                else "modelled_route_available"
            )
        row["travel_time_delta_minutes"] = (
            after - before if before is not None and after is not None else None
        )
        node_results.append(row)
    areas = [
        {
            "subdistrict_id": area,
            **_access_totals(
                [row for row in node_results if row["subdistrict_id"] == area], limits
            ),
        }
        for area in sorted({pop["subdistrict_id"] for pop in pops})
    ]
    return {
        **_metadata(source_timestamp, assumptions),
        "method": "modelled_undirected_nearest_destination_with_walking_connectors",
        "connector_speed_kmh": CONNECTOR_SPEED_KMH,
        "population_snap_limit_m": POPULATION_SNAP_LIMIT_M,
        "facility_snap_limit_m": FACILITY_SNAP_LIMIT_M,
        "modelled_road_speeds_kmh": dict(MODELLED_ROAD_SPEED_KMH),
        "scenario": {
            "closed_edge_ids": sorted(closed),
            "removed_facility_ids": sorted(removed),
            "added_facility_ids": sorted(site["facility_id"] for site in additions),
        },
        "node_results": node_results,
        "areas": areas,
        "totals": _access_totals(node_results, limits),
        "coverage_review": _coverage_review(node_results, limits),
        "travel_time_summary": _travel_time_summary(node_results),
        "baseline_input_sha256": signature,
        "baseline_reachable_pairs": normal_pairs,
        "scenario_reachable_pairs": changed_pairs,
        "facility_snap_review": [
            {
                "facility_id": site["facility_id"],
                "snap_status": _snap_status(site, FACILITY_SNAP_LIMIT_M, changed_graph),
            }
            for site in selected_sites
        ],
        "equity_gap_ratio": None,
        "equity_status": "unavailable_demographic_groups_not_supplied",
    }


def _coverage_review(
    rows: Sequence[Mapping[str, Any]], thresholds: Sequence[int]
) -> dict[str, Any]:
    """Partition resident demand without interpreting graph gaps as observed isolation."""
    result = {
        "missing_graph_coverage_population": math.fsum(
            row["total_population"] for row in rows if row["snap_status"] != "connected"
        )
    }
    for label, key in (
        ("baseline", "normal_access_minutes"),
        ("scenario", "scenario_access_minutes"),
    ):
        connected = [row for row in rows if row["snap_status"] == "connected"]
        result[label] = {
            "graph_connected_no_modelled_route_population": math.fsum(
                row["total_population"] for row in connected if row[key] is None
            ),
            "thresholds": {
                str(limit): {
                    "modelled_reachable_population": math.fsum(
                        row["total_population"]
                        for row in connected
                        if row[key] is not None and row[key] <= limit
                    ),
                    "modelled_over_threshold_population": math.fsum(
                        row["total_population"]
                        for row in connected
                        if row[key] is not None and row[key] > limit
                    ),
                }
                for limit in thresholds
            },
        }
    result["interpretation"] = (
        "Disjoint missing graph coverage, graph-connected no modelled route, over-threshold and within-threshold groups. Missing roads, destinations, restrictions and grade connections remain possible; no observed isolation claim."
    )
    return result


def _travel_time_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in rows if row["travel_time_delta_minutes"] is not None]
    population = math.fsum(row["total_population"] for row in comparable)
    weighted = math.fsum(
        row["total_population"] * row["travel_time_delta_minutes"] for row in comparable
    )
    return {
        "comparison_population": population,
        "baseline_population_weighted_mean_minutes": math.fsum(
            row["total_population"] * row["normal_access_minutes"] for row in comparable
        )
        / population
        if population
        else None,
        "scenario_population_weighted_mean_minutes": math.fsum(
            row["total_population"] * row["scenario_access_minutes"]
            for row in comparable
        )
        / population
        if population
        else None,
        "population_weighted_mean_delta_minutes": weighted / population
        if population
        else None,
        "net_change_person_minutes": weighted,
        "additional_person_minutes": math.fsum(
            row["total_population"] * max(0, row["travel_time_delta_minutes"])
            for row in comparable
        ),
        "saved_person_minutes": math.fsum(
            row["total_population"] * max(0, -row["travel_time_delta_minutes"])
            for row in comparable
        ),
        "slower_population": math.fsum(
            row["total_population"]
            for row in comparable
            if row["travel_time_delta_minutes"] > 1e-9
        ),
        "faster_population": math.fsum(
            row["total_population"]
            for row in comparable
            if row["travel_time_delta_minutes"] < -1e-9
        ),
        "newly_without_modelled_route_population": math.fsum(
            row["total_population"]
            for row in rows
            if row["normal_access_minutes"] is not None
            and row["scenario_access_minutes"] is None
        ),
        "newly_with_modelled_route_population": math.fsum(
            row["total_population"]
            for row in rows
            if row["normal_access_minutes"] is None
            and row["scenario_access_minutes"] is not None
        ),
        "interpretation": "Finite-route comparisons only; missing/unreachable trips are never converted to zero or a fabricated infinite travel time. Positive delta is slower.",
    }


def allocate_shelter_capacity(
    population: Sequence[Mapping[str, Any]],
    facilities: Sequence[Mapping[str, Any]],
    reachable_pairs: Sequence[Mapping[str, Any]],
    *,
    threshold_minutes: float = 30,
    source_timestamp: str | None = None,
    assumptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Maximize served demand under explicit known scenario capacities.

    Demand may be fractional modelled population. Sorted Edmonds-Karp flow makes
    results reproducible; this is not a closest-shelter or individual evacuation
    assignment. Unknown capacities are excluded, not assigned zero. Zero is an
    explicit capacity. Reachability pairs must come from the same reviewed graph
    and include population_id, facility_id, travel_minutes. Only shelters should
    be passed as facilities; healthcare beds are not shelter capacity.
    """
    import networkx as nx

    pops = _population(population)
    sites = _facilities(facilities)
    threshold = _number(threshold_minutes, "threshold_minutes")
    if threshold <= 0:
        raise EvidenceScenarioError("threshold_minutes must be positive")
    pop_ids = {row["population_id"] for row in pops}
    site_ids = {row["facility_id"] for row in sites}
    excluded_pop_ids = {
        row["population_id"]
        for row in pops
        if not _valid_connector(row, POPULATION_SNAP_LIMIT_M)
    }
    excluded_site_ids = {
        row["facility_id"]
        for row in sites
        if not _valid_connector(row, FACILITY_SNAP_LIMIT_M)
    }
    pairs: dict[tuple[str, str], float] = {}
    for pair in reachable_pairs:
        person = _text(pair.get("population_id"), "population_id")
        site = _text(pair.get("facility_id"), "facility_id")
        minutes = _number(pair.get("travel_minutes"), "travel_minutes")
        if person not in pop_ids or site not in site_ids:
            raise EvidenceScenarioError(
                "reachability pair references unknown population/facility"
            )
        if person in excluded_pop_ids or site in excluded_site_ids:
            raise EvidenceScenarioError(
                "reachability pair references an excluded connector"
            )
        key = (person, site)
        pairs[key] = min(minutes, pairs.get(key, math.inf))
    pairs = {key: value for key, value in pairs.items() if value <= threshold}
    destinations_by_population: dict[str, list[str]] = {key: [] for key in pop_ids}
    for person, site in sorted(pairs):
        destinations_by_population[person].append(site)
    capacity = {
        site["facility_id"]: None
        if site.get("capacity") is None
        else _number(site["capacity"], "capacity")
        for site in sites
    }
    network = nx.DiGraph()
    source, sink = ("source", ""), ("sink", "")
    network.add_nodes_from([source, sink])
    total = math.fsum(pop["total_population"] for pop in pops)
    for pop in pops:
        network.add_edge(
            source,
            ("population", pop["population_id"]),
            capacity=pop["total_population"],
        )
    for site in sites:
        cap = capacity[site["facility_id"]]
        if cap is not None:
            network.add_edge(("facility", site["facility_id"]), sink, capacity=cap)
    for person, site in sorted(pairs):
        if capacity[site] is not None:
            network.add_edge(("population", person), ("facility", site), capacity=total)
    flow_value, flow = nx.maximum_flow(
        network, source, sink, flow_func=nx.algorithms.flow.edmonds_karp
    )
    allocations = []
    allocated_by_population: dict[str, list[float]] = {key: [] for key in pop_ids}
    allocated_by_facility: dict[str, list[float]] = {key: [] for key in site_ids}
    for person, site in sorted(pairs):
        amount = flow.get(("population", person), {}).get(("facility", site), 0.0)
        if amount > 0:
            allocations.append(
                {
                    "population_id": person,
                    "facility_id": site,
                    "allocated_population": float(amount),
                    "travel_minutes": pairs[(person, site)],
                }
            )
            allocated_by_population[person].append(float(amount))
            allocated_by_facility[site].append(float(amount))
    demand_rows = []
    for pop in pops:
        person = pop["population_id"]
        served = math.fsum(allocated_by_population[person])
        unknown = [
            site
            for site in destinations_by_population[person]
            if capacity[site] is None
        ]
        known = [
            site
            for site in destinations_by_population[person]
            if capacity[site] is not None
        ]
        unserved = max(0.0, pop["total_population"] - served)
        reason = (
            "excluded_coverage"
            if person in excluded_pop_ids
            else "unreachable"
            if not (known or unknown)
            else "unknown_capacity"
            if unknown and unserved > 0
            else "capacity_limited"
            if unserved > 0
            else "fully_served"
        )
        demand_rows.append(
            {
                "population_id": person,
                "total_population": pop["total_population"],
                "served_population": served,
                "unserved_population": unserved,
                "unserved_reason": reason,
                "reachable_known_capacity_facilities": known,
                "reachable_unknown_capacity_facilities": unknown,
            }
        )
    facility_rows = []
    for site in sites:
        key = site["facility_id"]
        allocated = math.fsum(allocated_by_facility[key])
        facility_rows.append(
            {
                "facility_id": key,
                "capacity": capacity[key],
                "capacity_status": "unknown" if capacity[key] is None else "known",
                "allocated_population": allocated,
                "remaining_capacity": None
                if capacity[key] is None
                else max(0.0, capacity[key] - allocated),
            }
        )
    served = float(flow_value)
    if not math.isclose(
        served, math.fsum(row["served_population"] for row in demand_rows), abs_tol=1e-8
    ):
        raise EvidenceScenarioError("capacity allocation failed demand conservation")
    partitions = {
        output: math.fsum(
            row["unserved_population"]
            for row in demand_rows
            if row["unserved_reason"] == reason
        )
        for output, reason in (
            ("capacity_limited_unmet_population", "capacity_limited"),
            ("unreachable_population", "unreachable"),
            ("excluded_coverage_population", "excluded_coverage"),
            ("unmet_population_with_unknown_capacity", "unknown_capacity"),
        )
    }
    if not math.isclose(
        total, served + math.fsum(partitions.values()), rel_tol=1e-10, abs_tol=1e-8
    ):
        raise EvidenceScenarioError(
            "capacity demand partitions do not conserve population"
        )
    return {
        **_metadata(source_timestamp, assumptions),
        "method": "maximum_served_demand_sorted_edmonds_karp",
        "threshold_minutes": threshold,
        "demand_definition": "scenario_demand_not_observed_evacuations",
        "total_population": total,
        "served_population": served,
        "unserved_population": max(0.0, total - served),
        **partitions,
        "calculation_status": "incomplete_unknown_capacity"
        if any(value is None for value in capacity.values())
        else "complete_scenario",
        "unknown_capacity_facility_ids": sorted(
            key for key, value in capacity.items() if value is None
        ),
        "interpretation": "Known-capacity scenario only; unserved demand is not a verified shelter shortage.",
        "allocations": allocations,
        "population_results": demand_rows,
        "facility_results": facility_rows,
    }


def evidence_assessment(
    components: Mapping[str, float | None],
    *,
    area_id: str,
    area_name: str = "",
    confidence_class: str = "low",
    source_timestamp: str | None = None,
    assumptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Keep incomplete FPPS null and show fixed-weight arithmetic sensitivity.

    Missing components are explicitly completed at 0, 50 and 100 in three
    separate scenarios. These are assumptions, not imputed observations or
    confidence intervals. A complete case uses the unchanged strict scorer.
    """
    identifier = _text(area_id, "area_id")
    if set(components) - set(SCORE_COMPONENTS):
        raise EvidenceScenarioError("unknown FPPS component")
    if confidence_class not in {"low", "medium", "high"}:
        raise EvidenceScenarioError("invalid confidence_class")
    values: dict[str, float | None] = {}
    for key in SCORE_COMPONENTS:
        value = components.get(key)
        values[key] = None if value is None else _number(value, key)
        if values[key] is not None and values[key] > 100:
            raise EvidenceScenarioError(f"{key} must be between 0 and 100")
    missing = [key for key in SCORE_COMPONENTS if values[key] is None]
    lower = math.fsum(
        DEFAULT_WEIGHTS[key] * value
        for key, value in values.items()
        if value is not None
    )
    upper = lower + math.fsum(DEFAULT_WEIGHTS[key] * 100 for key in missing)

    def scored(filled: Mapping[str, float]) -> dict[str, Any]:
        row = score_subdistricts(
            pd.DataFrame(
                [
                    {
                        "subdistrict_id": identifier,
                        "subdistrict_name": area_name or identifier,
                        "confidence_class": confidence_class,
                        **filled,
                    }
                ]
            )
        ).iloc[0]
        return {
            "fpps_0_100": float(row["fpps_0_100"]),
            "action_class": str(row["action_class"]),
            "action_reason_code": str(row["action_reason_code"]),
        }

    actual = {"fpps_0_100": None, "action_class": None, "action_reason_code": None}
    scenarios = []
    if missing:
        for assumed in (0, 50, 100):
            completion = {
                key: float(assumed) if value is None else value
                for key, value in values.items()
            }
            scenarios.append(
                {
                    "scenario_id": f"unknown_components_{assumed}",
                    "evidence_role": "scenario",
                    "assumed_missing_value": assumed,
                    "assumed_components": missing,
                    "components": completion,
                    **scored(completion),
                }
            )
    else:
        actual = scored(values)
    return {
        **_metadata(source_timestamp, assumptions),
        "confidence_class": confidence_class,
        "area_id": identifier,
        "components": values,
        "assessment_status": "incomplete" if missing else "complete_candidate",
        "missing_components": missing,
        "weights": dict(DEFAULT_WEIGHTS),
        **actual,
        "fixed_weight_bounds": {
            "lower": round(lower, 2),
            "upper": round(upper, 2),
            "meaning": "arithmetic_bounds_not_confidence_interval",
        },
        "scenario_completions": scenarios,
    }


def build_illustrative_scenarios(
    aoi_id: str, bounds: Sequence[float]
) -> dict[str, Any]:
    """Create an explicitly synthetic demonstration within an AOI bounding box.

    Coordinates only position a diagram. Population, roads, facilities, demand,
    capacities and component values are invented scenario inputs; they are never
    observations, source-derived estimates or evidence of actual local access.
    """
    identifier = _text(aoi_id, "aoi_id")
    if len(bounds) != 4:
        raise EvidenceScenarioError("bounds must contain west, south, east, north")
    west, south, east, north = [float(value) for value in bounds]
    if not all(math.isfinite(value) for value in (west, south, east, north)) or not (
        -180 <= west < east <= 180 and -90 <= south < north <= 90
    ):
        raise EvidenceScenarioError("invalid WGS84 bounds")
    coordinates = {
        "west": [west + (east - west) * 0.25, south + (north - south) * 0.5],
        "center": [(west + east) / 2, (south + north) / 2],
        "east": [west + (east - west) * 0.75, south + (north - south) * 0.5],
    }
    pops = [
        {
            "population_id": "illustrative-demand",
            "subdistrict_id": identifier,
            "total_population": 100.0,
            "node_id": "west",
            "snap_distance_m": 0.0,
        }
    ]
    edges = [
        {
            "edge_id": "illustrative-west",
            "from_node": "west",
            "to_node": "center",
            "normal_minutes": 8,
        },
        {
            "edge_id": "illustrative-east",
            "from_node": "center",
            "to_node": "east",
            "normal_minutes": 8,
        },
    ]
    sites = [
        {
            "facility_id": "illustrative-shelter",
            "node_id": "east",
            "snap_distance_m": 0.0,
            "capacity": 50.0,
        }
    ]
    notes = [
        "Synthetic diagram: all demand, graph travel times, destinations and capacities are invented.",
        "AOI bounds position the diagram only; no local route, site or population observation is asserted.",
    ]
    baseline = calculate_total_access(pops, edges, sites, assumptions=notes)
    scenarios = {
        "baseline": baseline,
        "close_edge": calculate_total_access(
            pops,
            edges,
            sites,
            scenario={"closed_edge_ids": ["illustrative-east"]},
            assumptions=notes,
        ),
        "remove_destination": calculate_total_access(
            pops,
            edges,
            sites,
            scenario={"removed_facility_ids": ["illustrative-shelter"]},
            assumptions=notes,
        ),
        "add_destination": calculate_total_access(
            pops,
            edges,
            sites,
            scenario={
                "added_facilities": [
                    {
                        "facility_id": "illustrative-added",
                        "node_id": "center",
                        "snap_distance_m": 0.0,
                        "capacity": 50,
                    }
                ]
            },
            assumptions=notes,
        ),
    }
    capacity = [
        allocate_shelter_capacity(
            pops,
            [{**sites[0], "capacity": value}],
            baseline["baseline_reachable_pairs"],
            assumptions=notes,
        )
        for value in (50, 100, 200)
    ]
    features = [
        {
            "type": "Feature",
            "properties": {
                "edge_id": edge["edge_id"],
                "evidence_role": "scenario",
                "synthetic": True,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    coordinates[edge["from_node"]],
                    coordinates[edge["to_node"]],
                ],
            },
        }
        for edge in edges
    ]
    return {
        **_metadata(None, notes),
        "aoi_id": identifier,
        "synthetic": True,
        "title": "Illustrative mechanics only — not an AOI access result",
        "access_scenarios": scenarios,
        "capacity_scenarios": capacity,
        "assessment": evidence_assessment({}, area_id=identifier, assumptions=notes),
        "map_geojson": {"type": "FeatureCollection", "features": features},
    }


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EvidenceScenarioError(f"{field} must be a finite nonnegative number")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise EvidenceScenarioError(
            f"{field} must be a finite nonnegative number"
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise EvidenceScenarioError(f"{field} must be a finite nonnegative number")
    return number


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceScenarioError(f"{field} must be a nonempty string")
    return value.strip()


def _selected_ids(values: Sequence[Any], field: str) -> set[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise EvidenceScenarioError(f"{field} must be a sequence of IDs")
    result = [_text(value, field) for value in values]
    if len(set(result)) != len(result):
        raise EvidenceScenarioError(f"{field} has duplicate IDs")
    return set(result)


def _records(rows: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    result = [dict(row) for row in rows]
    for row in result:
        row[key] = _text(row.get(key), key)
    if len({row[key] for row in result}) != len(result):
        raise EvidenceScenarioError(f"duplicate {key}")
    return sorted(result, key=lambda row: row[key])


def _population(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = _records(rows, "population_id")
    for row in result:
        row["subdistrict_id"] = _text(row.get("subdistrict_id"), "subdistrict_id")
        row["total_population"] = _number(
            row.get("total_population"), "total_population"
        )
        _validate_snap(row)
    return result


def _facilities(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = _records(rows, "facility_id")
    for row in result:
        _validate_snap(row)
        if "connectors" in row:
            connectors = row["connectors"]
            if not isinstance(connectors, list) or not connectors:
                raise EvidenceScenarioError("explicit facility connectors must be nonempty")
            seen = set()
            for connector in connectors:
                if not isinstance(connector, dict) or set(connector) != {"node_id", "snap_distance_m"}:
                    raise EvidenceScenarioError("facility connector must contain only node_id and snap_distance_m")
                _validate_snap(connector)
                if connector["node_id"] in seen:
                    raise EvidenceScenarioError("duplicate facility connector node")
                seen.add(connector["node_id"])
        if row.get("capacity") is not None:
            row["capacity"] = _number(row["capacity"], "capacity")
    return result


def facility_connectors(site: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return explicit reviewed scenario connections, or the legacy single snap."""
    return site.get("connectors", [site])


def _validate_snap(row: dict[str, Any]) -> None:
    if "node_id" not in row or "snap_distance_m" not in row:
        raise EvidenceScenarioError(
            "node_id and snap_distance_m must be explicit (nullable)"
        )
    if row["node_id"] is not None:
        row["node_id"] = _text(row["node_id"], "node_id")
    if row["snap_distance_m"] is not None:
        row["snap_distance_m"] = _number(row["snap_distance_m"], "snap_distance_m")


def _valid_connector(row: Mapping[str, Any], limit: float) -> bool:
    return (
        row["node_id"] is not None
        and row["snap_distance_m"] is not None
        and row["snap_distance_m"] <= limit
    )


def _graph(
    edges: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[tuple[str, float]]], list[dict[str, Any]]]:
    records = _records(edges, "edge_id")
    graph: dict[str, list[tuple[str, float]]] = {}
    for edge in records:
        start = _text(edge.get("from_node"), "from_node")
        end = _text(edge.get("to_node"), "to_node")
        if start == end:
            raise EvidenceScenarioError("self-loop road edges are not supported")
        if "normal_minutes" in edge:
            minutes = _number(edge["normal_minutes"], "normal_minutes")
        else:
            road_class = edge.get("road_class")
            if road_class not in MODELLED_ROAD_SPEED_KMH:
                raise EvidenceScenarioError(
                    "a modelled road_class or explicit normal_minutes is required"
                )
            minutes = (
                _number(edge.get("length_m"), "length_m")
                / 1000
                / MODELLED_ROAD_SPEED_KMH[road_class]
                * 60
            )
        graph.setdefault(start, []).append((end, minutes))
        graph.setdefault(end, []).append((start, minutes))
    return graph, records


def _snap_status(row: Mapping[str, Any], limit: float, graph: Mapping[str, Any]) -> str:
    if row["node_id"] is None or row["snap_distance_m"] is None:
        return "unconnected_missing_snap"
    if row["snap_distance_m"] > limit:
        return "unconnected_snap_too_far"
    if row["node_id"] not in graph:
        return "unconnected_node_not_in_graph"
    return "connected"


def _reachable_pairs(
    pops: Sequence[Mapping[str, Any]],
    sites: Sequence[Mapping[str, Any]],
    graph: dict[str, list[tuple[str, float]]],
) -> list[dict[str, Any]]:
    result = []
    for site in sites:
        distances = {}
        for connection in facility_connectors(site):
            if _snap_status(connection, FACILITY_SNAP_LIMIT_M, graph) != "connected":
                continue
            connector = connection["snap_distance_m"] / 1000 / CONNECTOR_SPEED_KMH * 60
            for node, minutes in _facility_minutes_by_node(graph, {connection["node_id"]}).items():
                distances[node] = min(distances.get(node, math.inf), minutes + connector)
        for pop in pops:
            if _snap_status(pop, POPULATION_SNAP_LIMIT_M, graph) != "connected":
                continue
            distance = distances.get(pop["node_id"])
            if distance is not None:
                result.append(
                    {
                        "population_id": pop["population_id"],
                        "facility_id": site["facility_id"],
                        "travel_minutes": distance
                        + pop["snap_distance_m"] / 1000 / CONNECTOR_SPEED_KMH * 60,
                    }
                )
    return sorted(result, key=lambda row: (row["population_id"], row["facility_id"]))


def _nearest_by_population(pairs: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for pair in pairs:
        key = pair["population_id"]
        result[key] = min(result.get(key, math.inf), pair["travel_minutes"])
    return result


def _access_totals(
    rows: Sequence[Mapping[str, Any]], thresholds: Sequence[int]
) -> dict[str, Any]:
    result = {
        "total_population": math.fsum(row["total_population"] for row in rows),
        "unconnected_population": math.fsum(
            row["total_population"] for row in rows if row["snap_status"] != "connected"
        ),
    }
    for threshold in thresholds:
        for state, label in (
            ("already_without", "already_without"),
            ("loses", "losing"),
            ("gains", "gaining"),
        ):
            result[f"people_{label}_{threshold}_min_access"] = math.fsum(
                row["total_population"]
                for row in rows
                if row[f"{state}_{threshold}_min_access"]
            )
    return result


def _metadata(
    source_timestamp: str | None, assumptions: Sequence[str]
) -> dict[str, Any]:
    return {
        "source_name": "FloodGuard explicit planning scenario",
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "evidence_role": "scenario",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "assumptions": list(
            dict.fromkeys(
                [
                    *assumptions,
                    "Modelled planning scenario; not observed road passability, facility activation or evacuation demand.",
                ]
            )
        ),
    }
