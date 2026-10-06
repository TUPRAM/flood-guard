"""Traceable routes from named public pins to separate candidate services."""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

from .evidence_scenarios import CONNECTOR_SPEED_KMH, FACILITY_SNAP_LIMIT_M, facility_connectors


def calculate_pin_route(
    context: Mapping,
    origin: Mapping,
    destinations: Sequence[Mapping],
    *,
    closed_edge_ids: Sequence[str] = (),
    removed_facility_ids: Sequence[str] = (),
) -> dict:
    """Find a reproducible minimum-time undirected route, with explicit connectors.

    Geometries are modelled paths, not instructions to travel or observed usable
    roads. The supplied graph must already enforce jurisdiction and travel mode.
    Destination tie breaking uses its stable ID, never its service importance.
    """
    edge_by_id = {row["edge_id"]: row for row in context["edges"]}
    if (
        len(edge_by_id) != len(context["edges"])
        or set(closed_edge_ids) - edge_by_id.keys()
    ):
        raise ValueError("Duplicate or unknown road-edge identity")
    sites = {row["facility_id"]: row for row in destinations}
    if len(sites) != len(destinations) or set(removed_facility_ids) - sites.keys():
        raise ValueError("Duplicate or unknown destination identity")
    empty = {
        "status": "unavailable",
        "reason": "",
        "destination_id": None,
        "destination_name": None,
        "total_minutes": None,
        "network_minutes": None,
        "connector_minutes": None,
        "distance_m": None,
        "edge_ids": [],
        "coordinates": [],
        "connectors": [],
    }
    graph = defaultdict(list)
    for edge in sorted(context["edges"], key=lambda row: row["edge_id"]):
        a, b = edge["from_node"], edge["to_node"]
        graph[a]
        graph[b]
        if edge["edge_id"] not in closed_edge_ids:
            minutes = edge["normal_minutes"]
            if not math.isfinite(minutes) or minutes < 0:
                raise ValueError("Network travel times must be finite and nonnegative")
            graph[a].append((b, minutes, edge["edge_id"]))
            graph[b].append((a, minutes, edge["edge_id"]))
    node, snap = origin.get("node_id"), origin.get("snap_distance_m")
    if (
        node not in graph
        or snap is None
        or not math.isfinite(snap)
        or snap < 0
        or snap > FACILITY_SNAP_LIMIT_M
    ):
        return {
            **empty,
            "reason": "Prepared public origin has no accepted connector within 100 m; access is unknown.",
        }
    candidates = [
        site
        for site in destinations
        if site["facility_id"] not in removed_facility_ids
        and site.get("candidate_destination_eligible") is True
        and any(connection.get("node_id") in graph
                and connection.get("snap_distance_m") is not None
                and 0 <= connection["snap_distance_m"] <= FACILITY_SNAP_LIMIT_M
                for connection in facility_connectors(site))
    ]
    if not candidates:
        return {
            **empty,
            "reason": "No eligible connected destination of this service type; other services are not substituted.",
        }
    distances, predecessor, settled, queue = {node: 0.0}, {}, set(), [(0.0, node)]
    while queue:
        cost, current = heapq.heappop(queue)
        if current in settled:
            continue
        settled.add(current)
        for other, minutes, edge_id in sorted(graph[current]):
            if other in settled:
                continue
            candidate = cost + minutes
            old = distances.get(other, math.inf)
            if candidate < old or (
                candidate == old
                and (current, edge_id) < predecessor.get(other, ("~", "~"))
            ):
                distances[other] = candidate
                predecessor[other] = (current, edge_id)
                heapq.heappush(queue, (candidate, other))
    available = [
        (
            distances[connection["node_id"]]
            + connection["snap_distance_m"] / 1000 / CONNECTOR_SPEED_KMH * 60,
            site["facility_id"],
            {**site, **connection},
        )
        for site in candidates
        for connection in facility_connectors(site)
        if connection["node_id"] in distances and connection.get("snap_distance_m") is not None
        and 0 <= connection["snap_distance_m"] <= FACILITY_SNAP_LIMIT_M
    ]
    if not available:
        return {
            **empty,
            "reason": "Origin is graph-connected but no modelled route reaches the selected service.",
        }
    _, _, site = min(available, key=lambda value: (*value[:2], value[2]["node_id"]))
    current, reverse_nodes, reverse_edges = site["node_id"], [site["node_id"]], []
    while current != node:
        current, edge_id = predecessor[current]
        reverse_nodes.append(current)
        reverse_edges.append(edge_id)
    nodes, edges = list(reversed(reverse_nodes)), list(reversed(reverse_edges))
    coordinates = [context["node_coordinates"][key] for key in nodes]
    origin_point = [origin["longitude"], origin["latitude"]]
    destination_point = [site["longitude"], site["latitude"]]
    connector_minutes = (
        (snap + site["snap_distance_m"]) / 1000 / CONNECTOR_SPEED_KMH * 60
    )
    network_minutes = distances[site["node_id"]]
    return {
        "status": "available",
        "reason": "Modelled path to the minimum-time connected candidate; operation and safe passability unverified.",
        "destination_id": site["facility_id"],
        "destination_name": site.get("name") or site["facility_id"],
        "total_minutes": round(network_minutes + connector_minutes, 4),
        "network_minutes": round(network_minutes, 4),
        "connector_minutes": round(connector_minutes, 4),
        "distance_m": round(
            sum(edge_by_id[key]["length_m"] for key in edges)
            + snap
            + site["snap_distance_m"],
            2,
        ),
        "edge_ids": edges,
        "coordinates": coordinates,
        "connectors": [
            [origin_point, coordinates[0]],
            [coordinates[-1], destination_point],
        ],
    }


def build_pin_comparisons(contexts: Mapping[str, Mapping], *, flood_closures: Mapping[str, Sequence[str]] | None = None) -> dict:
    """Compare up to three named public origins, with path-based explicit changes.

    A closure targets the longest edge of that origin's baseline route, selected
    before its consequence is evaluated. Removal targets its nearest baseline
    destination. Both changes are independent, hypothetical disruptions.
    """
    walking = contexts["walking"]
    available = [
        row
        for row in walking.get("public_origins", [])
        if row.get("name") and row.get("node_id")
    ]
    official = [row for row in available if row["origin_id"].startswith("official-")]
    selected = sorted(
        official or available,
        key=lambda row: ("municipality" not in row["origin_id"], row["origin_id"]),
    )[:3]
    origins = [
        {
            "id": row["origin_id"],
            "name": row["name"],
            "longitude": row["longitude"],
            "latitude": row["latitude"],
            "source_url": row["source_url"],
            "geometry_role": row.get("geometry_role", "mapped_location"),
            "location_status": "official_site_marker_entrance_unverified"
            if row["origin_id"].startswith("official-")
            else "public_map_record_entrance_unverified",
        }
        for row in selected
    ]
    comparisons = []
    for mode, context in sorted(contexts.items()):
        by_origin = {row["origin_id"]: row for row in context.get("public_origins", [])}
        edge_by_id = {row["edge_id"]: row for row in context["edges"]}
        for pin in origins:
            origin = by_origin.get(pin["id"])
            if origin is None:
                continue
            for service in ("hospital", "primary_care", "pharmacy", "shelter"):
                sites = [
                    row
                    for row in context["osm_facilities"]
                    if row.get("service_type") == service
                    and row.get("candidate_destination_eligible") is True
                    and row.get("within_routing_context") is True
                ]
                before = calculate_pin_route(context, origin, sites)
                closure = sorted(
                    before["edge_ids"],
                    key=lambda key: (-edge_by_id[key]["length_m"], key),
                )[:1]
                if flood_closures is not None:
                    closure = list(flood_closures[mode])
                removed = [before["destination_id"]] if before["destination_id"] else []
                for kind, identifiers in (
                    ("close_edge", closure),
                    ("remove_destination", removed),
                ):
                    after = calculate_pin_route(
                        context,
                        origin,
                        sites,
                        closed_edge_ids=identifiers if kind == "close_edge" else (),
                        removed_facility_ids=identifiers
                        if kind == "remove_destination"
                        else (),
                    )
                    comparisons.append(
                        {
                            "id": f"{pin['id']}-{service}-{mode}-{kind}",
                            "origin_id": pin["id"],
                            "service_type": service,
                            "travel_mode": mode,
                            "scenario_kind": kind,
                            "changed_ids": identifiers,
                            "selection_method": ("All positive-length road intersections with the fixed SAR flood candidate, selected before computing route effects; candidate inundation and assumed closures, not observed passability." if flood_closures is not None else "Longest baseline route edge, stable ID tie-break; selected before measuring the closure effect.")
                            if kind == "close_edge"
                            else "Remove this origin's minimum-time baseline destination; no other service substitutes.",
                            "context_sha256": context["canonical_sha256"],
                            "baseline": before,
                            "after": after,
                            "delta_minutes": round(
                                after["total_minutes"] - before["total_minutes"], 4
                            )
                            if before["status"] == after["status"] == "available"
                            else None,
                        }
                    )
    return {
        "status": "available" if origins else "unavailable",
        "origins": origins,
        "comparisons": comparisons,
        "limitations": [
            "Prepared pins cite public site markers or named OSM map records. None establishes a verified entrance or private user location.",
            "Before and after refer to independent imposed changes on the same mixed-year model, not observed pre/post-flood road conditions.",
            "Dashed connectors are assumptions; the displayed route is not a safe evacuation instruction.",
        ],
    }
