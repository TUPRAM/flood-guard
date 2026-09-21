"""Deterministic, bounded scenario selection from model relevance, not events."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .evidence_scenarios import (
    CONNECTOR_SPEED_KMH,
    FACILITY_SNAP_LIMIT_M,
    MODELLED_ROAD_SPEED_KMH,
)


def select_interventions(
    population: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    facilities: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    """Rank baseline route demand before evaluating one change per family.

    A multi-source shortest-path tree assigns tied routes by stable site/node/edge
    IDs. Its edge demand is a relevance proxy, not betweenness or a prediction of
    closure harm. No scenario outcome or flood reference tunes these selections.
    Only the first ten ranked candidates are retained; all candidates are counted.
    """
    graph = defaultdict(list)
    for edge in sorted(edges, key=lambda row: row["edge_id"]):
        minutes = edge.get("normal_minutes")
        if minutes is None:
            minutes = (
                edge["length_m"]
                / 1000
                / MODELLED_ROAD_SPEED_KMH[edge["road_class"]]
                * 60
            )
        a, b = edge["from_node"], edge["to_node"]
        graph[a].append((b, minutes, edge["edge_id"]))
        graph[b].append((a, minutes, edge["edge_id"]))
    best, predecessor, queue = {}, {}, []
    for site in sorted(facilities, key=lambda row: row["facility_id"]):
        node, snap = site.get("node_id"), site.get("snap_distance_m")
        if node not in graph or snap is None or snap > FACILITY_SNAP_LIMIT_M:
            continue
        value = (snap / 1000 / CONNECTOR_SPEED_KMH * 60, site["facility_id"])
        if node not in best or value < best[node]:
            best[node] = value
            heapq.heappush(queue, (*value, node))
    settled, order = set(), []
    while queue:
        minutes, site, node = heapq.heappop(queue)
        if node in settled or best[node] != (minutes, site):
            continue
        settled.add(node)
        order.append(node)
        for other, cost, edge_id in sorted(graph[node]):
            if other in settled:
                continue
            candidate = (minutes + cost, site)
            previous = best.get(other)
            link = (node, edge_id)
            if (
                previous is None
                or candidate < previous
                or (candidate == previous and link < predecessor.get(other, ("~", "~")))
            ):
                best[other] = candidate
                predecessor[other] = link
                heapq.heappush(queue, (*candidate, other))
    by_id = {row["population_id"]: row for row in population}
    loads, site_loads, addition_nodes = defaultdict(float), defaultdict(float), {}
    for result in sorted(
        baseline["node_results"], key=lambda row: row["population_id"]
    ):
        if result["snap_status"] != "connected":
            continue
        pop = by_id[result["population_id"]]
        node, demand = pop["node_id"], pop["total_population"]
        if demand <= 0:
            continue
        if node in best:
            loads[node] += demand
            site_loads[best[node][1]] += demand
        candidate = addition_nodes.setdefault(
            node,
            {
                "node_id": node,
                "population_without_30_min_access": 0.0,
                "baseline_person_minutes": 0.0,
                "resident_population": 0.0,
            },
        )
        candidate["resident_population"] += demand
        before = result["normal_access_minutes"]
        candidate["population_without_30_min_access"] += (
            demand if before is None or before > 30 else 0
        )
        candidate["baseline_person_minutes"] += (
            demand * before if before is not None else 0
        )
    edge_loads = {}
    for node in reversed(order):
        if node in predecessor:
            parent, edge_id = predecessor[node]
            edge_loads[edge_id] = loads[node]
            loads[parent] += loads[node]
    closures = sorted(
        (
            {"edge_id": key, "baseline_route_population": value}
            for key, value in edge_loads.items()
            if value > 0
        ),
        key=lambda row: (-row["baseline_route_population"], row["edge_id"]),
    )
    removals = sorted(
        (
            {"facility_id": key, "baseline_nearest_population": value}
            for key, value in site_loads.items()
            if value > 0
        ),
        key=lambda row: (-row["baseline_nearest_population"], row["facility_id"]),
    )
    additions = sorted(
        addition_nodes.values(),
        key=lambda row: (
            -row["population_without_30_min_access"],
            -row["baseline_person_minutes"],
            -row["resident_population"],
            row["node_id"],
        ),
    )
    component_of = {}
    for origin in sorted(graph):
        if origin in component_of:
            continue
        component_of[origin] = origin
        pending = [origin]
        while pending:
            current = pending.pop()
            for neighbour, _, _ in graph[current]:
                if neighbour not in component_of:
                    component_of[neighbour] = origin
                    pending.append(neighbour)
    component_population = defaultdict(float)
    for node, candidate in sorted(addition_nodes.items()):
        component_population[component_of[node]] += candidate["resident_population"]
    capacity_candidates = sorted(
        [
            {
                "node_id": node,
                "resident_population": candidate["resident_population"],
                "component_residential_population": component_population[
                    component_of[node]
                ],
            }
            for node, candidate in addition_nodes.items()
        ],
        key=lambda row: (
            -row["component_residential_population"],
            -row["resident_population"],
            row["node_id"],
        ),
    )
    return {
        "selection_version": "baseline_model_relevance_v1",
        "closed_edge_id": closures[0]["edge_id"] if closures else None,
        "removed_facility_id": removals[0]["facility_id"] if removals else None,
        "hypothetical_added_node": additions[0]["node_id"] if additions else None,
        "hypothetical_capacity_node": capacity_candidates[0]["node_id"]
        if capacity_candidates
        else None,
        "candidates": {
            "close_edge": closures[:10],
            "remove_destination": removals[:10],
            "add_destination": additions[:10],
            "capacity_site": capacity_candidates[:10],
        },
        "candidate_counts": {
            "close_edge": len(closures),
            "remove_destination": len(removals),
            "add_destination": len(additions),
            "capacity_site": len(capacity_candidates),
        },
        "selection_reason": {
            "close_edge": "Highest residential population using a baseline shortest-path-tree edge; stable edge ID breaks ties. Alternative routes may eliminate the effect.",
            "remove_destination": "Largest baseline nearest-destination residential population; stable site ID breaks ties. Equally near substitutes may eliminate the effect.",
            "add_destination": "Demand node ranked by residents without 30-minute access, then finite baseline person-minutes, resident count and stable node ID. This is a hypothetical site, not a suitability decision.",
            "capacity_site": "For a separate capacity mechanics experiment: largest graph-connected residential component, then largest demand node and stable node ID. No land/safety/activation suitability is established; it need not be the underserved-access addition.",
        },
        "bounds": {
            "shortest_path_tree_passes": 1,
            "ranked_candidates_retained_per_family": 10,
            "outcome_evaluations_per_family": 1,
            "threshold_minutes": 30,
        },
        "limitations": [
            "Demand-based candidates are explicit stress/benefit scenarios, not observed closures or optimal interventions.",
            "No candidate is selected by a favorable post-intervention result. Routing/candidate facility gaps may dominate the ranking.",
            "No site feasibility, land ownership, flood safety, activation or shelter capacity is established.",
        ],
    }


def intervention_effect_summary(
    access: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Explain threshold-zero results using travel times and missing coverage."""
    result = {}
    for family, value in sorted(access.items()):
        if "totals" not in value:
            result[family] = {
                "status": "unavailable",
                "explanation": value.get("reason"),
            }
            continue
        totals = value["totals"]
        times = value["travel_time_summary"]
        threshold_changed = any(
            totals[f"people_{direction}_{limit}_min_access"] > 1e-9
            for direction in ("losing", "gaining")
            for limit in (15, 30, 60)
        )
        time_changed = any(
            times[key] > 1e-9
            for key in (
                "slower_population",
                "faster_population",
                "newly_with_modelled_route_population",
                "newly_without_modelled_route_population",
            )
        )
        explanation = (
            "Baseline comparison; no intervention imposed."
            if family == "baseline"
            else "Threshold access changes in this model."
            if threshold_changed
            else "Travel time or route availability changes without crossing the reported access thresholds."
            if time_changed
            else "No modelled effect: the selected change has an equivalent alternative, no marginal route benefit, or lies outside evaluated demand routes. This does not show real-world safety or irrelevance."
        )
        result[family] = {
            "status": "evaluated",
            "threshold_change": threshold_changed,
            "travel_time_change": time_changed,
            "explanation": explanation,
            "coverage_review": value["coverage_review"],
            "travel_time_summary": times,
        }
    return result
