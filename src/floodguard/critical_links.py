"""Baseline critical-link ranking for the planning overlay (plan task E6).

Protocol v1b ``critical_link_selection`` states the rule:

1. Rank baseline vehicle edges by demand-weighted shortest-path-tree flow.
2. Add graph bridges (Tarjan) to cover the all-routes-lost case.
3. Fully reroute only the top 200 ranked edges.
4. Output the top 20 per case, each with a bridge flag and an in-extent flag.

and the details the owners confirmed or decided:

* the demand weight is the WorldPop 2020 residents at each origin node, and ties
  break on the stable edge ID, following
  ``floodguard.evidence_interventions.select_interventions`` (drafter reading
  DR-B03);
* the destinations are the public facility set, OSM hospitals and main-road
  entries, in vehicle mode (owner choice 9);
* a link belongs to the tambon where its edge lies, and an edge that crosses a
  boundary goes by its midpoint (drafter reading DR-B06);
* the ranking is bound by its SHA-256 in the receipt of the first run (owner
  choice 10).

This module holds that rule as pure functions on an edge list, demand rows and
destinations. It reads no file and no flood layer, and it computes no closure
from a flood extent, no FPPS, no A-E class and no ensemble.

How the rule is read here, and nothing more:

* One multi-source shortest-path tree is grown from every destination at once,
  with the comparisons of ``select_interventions``: a node takes the smallest
  ``(minutes, destination ID)``, and among equal routes the smallest
  ``(parent node ID, edge ID)``. A resident's baseline route is the route of
  their origin node to its nearest destination in that tree.
* The flow of an edge is the number of residents whose baseline route uses it.
  Only edges with a positive flow are ranked, as in ``select_interventions``,
  by flow (largest first) and then by edge ID.
* A graph bridge is an edge whose removal disconnects the graph (Tarjan).
  Every ranked link carries that flag, and the OSM ``bridge=yes`` tag beside it.
* The in-extent flag needs a flood extent, which the baseline ranking does not
  read. ``flag_in_extent`` adds it later from the edges a flood input intersects
  (``floodguard.closure_rules.edge_intersections``).
* ``reroute_after_closure`` is the full reroute of the rule for a set of closed
  edges: it rebuilds the tree without them and counts the residents who had a
  baseline route and lose every route. The protocol does not say what a
  reroute of the top 200 writes, so this module ranks nothing by it.

A ranked link is a modelled candidate. It is not an observed closure, and no
link has been checked on the ground.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
import hashlib
import heapq
import json
import math
from typing import Any

from floodguard.evidence_scenarios import (
    CONNECTOR_SPEED_KMH,
    FACILITY_SNAP_LIMIT_M,
    MODELLED_ROAD_SPEED_KMH,
    POPULATION_SNAP_LIMIT_M,
    facility_connectors,
)

RANKING_RULE_VERSION = "critical_link_ranking_v1"
RANKING_TABLE_SCHEMA = "floodguard.critical_link_ranking.v1"
# Protocol v1b critical_link_selection.parameters.
FULL_REROUTE_TOP_N = 200
OUTPUT_TOP_N = 20
TIE_BREAK = "stable edge ID"
ROAD_EDGE_KIND = "road"
ANALYSIS_EPSG = 32647
UNIT_ASSIGNED = "midpoint_in_one_unit"
UNIT_NONE = "midpoint_in_no_unit"
UNIT_AMBIGUOUS = "midpoint_in_more_than_one_unit"
# Sorts after every node and edge ID this project writes; the sentinel of select_interventions.
_NO_LINK = ("~", "~")


class CriticalLinkError(ValueError):
    """Raised when the inputs of the ranking break its contract."""


def _edge_minutes(edge: Mapping[str, Any]) -> float:
    """Return the modelled travel time of an edge, as ``select_interventions`` reads it."""

    minutes = edge.get("normal_minutes")
    if minutes is None:
        road_class = edge.get("road_class")
        if road_class not in MODELLED_ROAD_SPEED_KMH:
            raise CriticalLinkError("an edge needs normal_minutes or a modelled road_class with length_m")
        minutes = edge["length_m"] / 1000 / MODELLED_ROAD_SPEED_KMH[road_class] * 60
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes < 0:
        raise CriticalLinkError("edge travel time must be a finite number of minutes, 0 or more")
    return float(minutes)


def _adjacency(
    edges: Sequence[Mapping[str, Any]], nodes: Iterable[str] = ()
) -> dict[str, list[tuple[str, float, str]]]:
    """Return ``node -> sorted [(neighbour, minutes, edge ID)]`` for an undirected edge list.

    Raises:
        CriticalLinkError: for a repeated edge ID or an edge from a node to itself.
    """

    graph: dict[str, list[tuple[str, float, str]]] = {str(node): [] for node in nodes}
    seen: set[str] = set()
    for edge in sorted(edges, key=lambda row: row["edge_id"]):
        edge_id = edge["edge_id"]
        if edge_id in seen:
            raise CriticalLinkError("edge IDs must be unique")
        seen.add(edge_id)
        start, end = edge["from_node"], edge["to_node"]
        if start == end:
            raise CriticalLinkError("an edge from a node to itself is not supported")
        minutes = _edge_minutes(edge)
        graph.setdefault(start, []).append((end, minutes, edge_id))
        graph.setdefault(end, []).append((start, minutes, edge_id))
    for neighbours in graph.values():
        neighbours.sort()
    return graph


def shortest_path_tree(
    edges: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
    *,
    nodes: Iterable[str] = (),
    facility_snap_limit_m: float = FACILITY_SNAP_LIMIT_M,
) -> dict[str, Any]:
    """Grow one multi-source shortest-path tree from every destination.

    The comparisons are those of ``select_interventions``. A destination enters
    at its snapped node with the time of its connector (snap distance at the
    connector speed). A node takes the smallest ``(minutes, destination ID)``;
    among equal candidates it keeps the smallest ``(parent node ID, edge ID)``.
    The result does not depend on the order of the inputs.

    Args:
        edges: Undirected edges with ``edge_id``, ``from_node``, ``to_node`` and
            ``normal_minutes`` (or ``length_m`` and a modelled ``road_class``).
        destinations: Rows with ``facility_id``, ``node_id`` and
            ``snap_distance_m`` (or explicit ``connectors``). A destination
            without a node in the graph, or snapped beyond the limit, is left out.
        nodes: Nodes to keep in the graph although no edge uses them; a closure
            may leave an origin or a destination without any edge.
        facility_snap_limit_m: The largest snap distance of a destination.

    Returns:
        ``minutes`` (node -> minutes to its nearest destination), ``destination``
        (node -> that destination's ID), ``predecessor`` (node -> ``(parent node,
        edge ID)`` of the tree edge towards the destination; a root has none) and
        ``settle_order`` (nodes in the order they were settled). A node that no
        destination reaches is in none of them.

    Raises:
        CriticalLinkError: for a repeated destination ID or a malformed edge.
    """

    graph = _adjacency(edges, nodes)
    sites = sorted(destinations, key=lambda row: row["facility_id"])
    if len({site["facility_id"] for site in sites}) != len(sites):
        raise CriticalLinkError("destination IDs must be unique")
    best: dict[str, tuple[float, str]] = {}
    predecessor: dict[str, tuple[str, str]] = {}
    queue: list[tuple[float, str, str]] = []
    for site in sites:
        for connection in facility_connectors(site):
            node, snap = connection.get("node_id"), connection.get("snap_distance_m")
            if node not in graph or snap is None or snap > facility_snap_limit_m:
                continue
            value = (snap / 1000 / CONNECTOR_SPEED_KMH * 60, site["facility_id"])
            if node not in best or value < best[node]:
                best[node] = value
                heapq.heappush(queue, (*value, node))
    settled: set[str] = set()
    order: list[str] = []
    while queue:
        minutes, site_id, node = heapq.heappop(queue)
        if node in settled or best[node] != (minutes, site_id):
            continue
        settled.add(node)
        order.append(node)
        for other, cost, edge_id in graph[node]:
            if other in settled:
                continue
            candidate = (minutes + cost, site_id)
            previous = best.get(other)
            link = (node, edge_id)
            if (
                previous is None
                or candidate < previous
                or (candidate == previous and link < predecessor.get(other, _NO_LINK))
            ):
                best[other] = candidate
                predecessor[other] = link
                heapq.heappush(queue, (*candidate, other))
    return {
        "minutes": {node: best[node][0] for node in order},
        "destination": {node: best[node][1] for node in order},
        "predecessor": {node: predecessor[node] for node in order if node in predecessor},
        "settle_order": order,
    }


def origin_demand(
    population: Sequence[Mapping[str, Any]],
    graph_nodes: Iterable[str],
    *,
    snap_limit_m: float = POPULATION_SNAP_LIMIT_M,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return the residents at each origin node, and the totals.

    A population cell is connected when it has a node of the graph and a snap
    distance within the limit, as in ``calculate_total_access``. Its residents
    are added to that node, cell by cell in the order of ``population_id``.

    Args:
        population: Rows with ``population_id``, ``total_population``,
            ``node_id`` and ``snap_distance_m`` (the last two may be null).
        graph_nodes: The nodes of the graph.
        snap_limit_m: The largest snap distance of a population cell.

    Returns:
        ``node -> residents`` for the nodes with residents, and ``residents``,
        ``residents_connected_to_the_graph``, ``residents_not_connected_to_the_graph``.

    Raises:
        CriticalLinkError: for a repeated population ID or a count that is not a
            finite number, 0 or more.
    """

    known = set(graph_nodes)
    rows = sorted(population, key=lambda row: row["population_id"])
    if len({row["population_id"] for row in rows}) != len(rows):
        raise CriticalLinkError("population IDs must be unique")
    demand: dict[str, float] = defaultdict(float)
    connected: list[float] = []
    unconnected: list[float] = []
    for row in rows:
        residents = row["total_population"]
        if isinstance(residents, bool) or not isinstance(residents, (int, float)) or not math.isfinite(residents) or residents < 0:
            raise CriticalLinkError("a resident count must be a finite number, 0 or more")
        node, snap = row.get("node_id"), row.get("snap_distance_m")
        if node is None or snap is None or snap > snap_limit_m or node not in known:
            unconnected.append(float(residents))
            continue
        connected.append(float(residents))
        if residents > 0:
            demand[node] += float(residents)
    totals = {
        "residents": math.fsum(connected) + math.fsum(unconnected),
        "residents_connected_to_the_graph": math.fsum(connected),
        "residents_not_connected_to_the_graph": math.fsum(unconnected),
    }
    return dict(demand), totals


def spt_flow(tree: Mapping[str, Any], demand: Mapping[str, float]) -> dict[str, float]:
    """Return the residents whose baseline route uses each tree edge.

    The residents of every origin node the tree reaches are carried along the
    tree towards the destination, from the last settled node to the first, as in
    ``select_interventions``. Edges that carry nobody are left out.
    """

    predecessor = tree["predecessor"]
    loads: dict[str, float] = defaultdict(float)
    for node, residents in demand.items():
        if node in tree["minutes"]:
            loads[node] = residents
    flows: dict[str, float] = {}
    for node in reversed(tree["settle_order"]):
        if node in predecessor:
            parent, edge_id = predecessor[node]
            flows[edge_id] = loads[node]
            loads[parent] += loads[node]
    return {edge_id: value for edge_id, value in flows.items() if value > 0}


def graph_bridges(edges: Sequence[Mapping[str, Any]]) -> set[str]:
    """Return the IDs of the edges whose removal disconnects the graph (Tarjan's bridge finding).

    Two edges between the same pair of nodes are never bridges. The search is
    iterative, so a long road does not hit the recursion limit.
    """

    adjacency: dict[str, list[tuple[str, str]]] = {
        node: [(other, edge_id) for other, _minutes, edge_id in neighbours]
        for node, neighbours in _adjacency(edges).items()
    }
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    bridges: set[str] = set()
    counter = 0
    for root in sorted(adjacency):
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack: list[tuple[str, str | None, Any]] = [(root, None, iter(adjacency[root]))]
        while stack:
            node, parent_edge, neighbours = stack[-1]
            for other, edge_id in neighbours:
                if edge_id == parent_edge:
                    continue
                if other in index:
                    low[node] = min(low[node], index[other])
                    continue
                index[other] = low[other] = counter
                counter += 1
                stack.append((other, edge_id, iter(adjacency[other])))
                break
            else:
                stack.pop()
                if stack:
                    parent = stack[-1][0]
                    low[parent] = min(low[parent], low[node])
                    if low[node] > index[parent] and parent_edge is not None:
                        bridges.add(parent_edge)
    return bridges


def rank_links(
    edges: Sequence[Mapping[str, Any]],
    population: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rank the edges of a baseline graph by demand-weighted shortest-path-tree flow.

    Args:
        edges: The baseline vehicle edges (context edges and grade-join connectors).
        population: The demand rows (see ``origin_demand``).
        destinations: The destination set (see ``shortest_path_tree``).

    Returns:
        ``links``: one row per edge with a positive flow, ranked from 1 by flow
        (largest first) and then by edge ID. Each row has ``rank``, ``edge_id``,
        ``spt_flow_residents``, ``graph_bridge`` (Tarjan), ``osm_bridge`` (the
        OSM tag ``bridge=yes``), ``edge_kind`` (``road`` or the connector kind),
        ``road_class``, ``osm_way_id``, ``from_node``, ``to_node``, ``length_m``
        and ``normal_minutes``.
        ``summary``: the demand totals, the residents with and without a baseline
        route, and counts of nodes, edges, graph bridges and ranked links.
        ``residents_by_destination``: destination ID -> residents whose baseline
        route ends there.
    """

    graph = _adjacency(edges)
    tree = shortest_path_tree(edges, destinations)
    demand, totals = origin_demand(population, graph)
    flows = spt_flow(tree, demand)
    bridges = graph_bridges(edges)
    by_id = {edge["edge_id"]: edge for edge in edges}
    links = [
        {
            "edge_id": edge_id,
            "spt_flow_residents": flow,
            "graph_bridge": edge_id in bridges,
            "osm_bridge": by_id[edge_id].get("bridge") == "yes",
            "edge_kind": by_id[edge_id].get("edge_kind") or ROAD_EDGE_KIND,
            "road_class": by_id[edge_id].get("road_class"),
            "osm_way_id": by_id[edge_id].get("osm_way_id"),
            "from_node": by_id[edge_id]["from_node"],
            "to_node": by_id[edge_id]["to_node"],
            "length_m": by_id[edge_id].get("length_m"),
            "normal_minutes": _edge_minutes(by_id[edge_id]),
        }
        for edge_id, flow in flows.items()
    ]
    links.sort(key=lambda row: (-row["spt_flow_residents"], row["edge_id"]))
    links = [{"rank": position, **row} for position, row in enumerate(links, start=1)]
    routed = sorted(node for node in demand if node in tree["minutes"])
    by_destination: dict[str, float] = defaultdict(float)
    for node in routed:
        by_destination[tree["destination"][node]] += demand[node]
    with_route = math.fsum(demand[node] for node in routed)
    connected = totals["residents_connected_to_the_graph"]
    return {
        "ranking_rule_version": RANKING_RULE_VERSION,
        "tie_break": TIE_BREAK,
        "links": links,
        "summary": {
            **totals,
            "connected_residents_with_a_baseline_route": with_route,
            "connected_residents_without_a_baseline_route": connected - with_route,
            "origin_nodes": len(demand),
            "origin_nodes_with_a_baseline_route": len(routed),
            "graph_nodes": len(graph),
            "graph_edges": len(by_id),
            "nodes_reached_by_the_tree": len(tree["settle_order"]),
            "destinations_supplied": len(destinations),
            "destinations_that_are_a_nearest_destination": len(by_destination),
            "graph_bridge_edges": len(bridges),
            "ranked_links": len(links),
            "ranked_links_that_are_graph_bridges": sum(row["graph_bridge"] for row in links),
        },
        "residents_by_destination": dict(sorted(by_destination.items())),
    }


def assign_units(
    edges: Sequence[Mapping[str, Any]],
    node_coordinates: Mapping[str, Sequence[float]],
    units: Sequence[tuple[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Say which unit each edge belongs to (drafter reading DR-B06).

    A link belongs to the unit where its edge lies, and an edge that crosses a
    boundary goes by its midpoint. An edge that lies in one unit has its
    midpoint there, so the midpoint decides in both cases. The edge is the
    straight segment between its two nodes in EPSG:32647, as in closure rule v1.

    Args:
        edges: Rows with ``edge_id``, ``from_node`` and ``to_node``.
        node_coordinates: Longitude and latitude (WGS84) of every node.
        units: ``(unit ID, shapely polygon in WGS84)`` pairs.

    Returns:
        ``edge_id -> {"unit_id", "unit_assignment"}``. ``unit_id`` is None when
        the midpoint lies in no unit (``midpoint_in_no_unit``) or in more than one,
        on a shared boundary or where two polygons overlap
        (``midpoint_in_more_than_one_unit``): the protocol gives no rule for
        those, so none is applied.

    Raises:
        CriticalLinkError: for a repeated unit ID or an edge with an unknown node.
    """

    import numpy as np
    import shapely
    from pyproj import Transformer
    from shapely.ops import transform

    identifiers = [str(unit_id) for unit_id, _geometry in units]
    if len(set(identifiers)) != len(identifiers):
        raise CriticalLinkError("unit IDs must be unique")
    rows = list(edges)
    if not rows:
        return {}
    try:
        start = np.array([node_coordinates[row["from_node"]][:2] for row in rows], dtype="float64")
        end = np.array([node_coordinates[row["to_node"]][:2] for row in rows], dtype="float64")
    except KeyError as error:
        raise CriticalLinkError(f"an edge refers to an unknown node: {error.args[0]}") from error
    projection = Transformer.from_crs(4326, ANALYSIS_EPSG, always_xy=True).transform
    # Lists, not arrays: pyproj treats an array of one element as a single point.
    start_x, start_y = (np.asarray(values) for values in projection(start[:, 0].tolist(), start[:, 1].tolist()))
    end_x, end_y = (np.asarray(values) for values in projection(end[:, 0].tolist(), end[:, 1].tolist()))
    midpoints = shapely.points((start_x + end_x) / 2, (start_y + end_y) / 2)
    holders: dict[int, list[str]] = defaultdict(list)
    if identifiers:
        tree = shapely.STRtree([transform(projection, geometry) for _unit_id, geometry in units])
        for point_index, unit_index in zip(*tree.query(midpoints, predicate="intersects")):
            holders[int(point_index)].append(identifiers[int(unit_index)])
    result: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(rows):
        found = sorted(holders.get(position, []))
        if len(found) == 1:
            result[row["edge_id"]] = {"unit_id": found[0], "unit_assignment": UNIT_ASSIGNED}
        else:
            result[row["edge_id"]] = {"unit_id": None, "unit_assignment": UNIT_AMBIGUOUS if found else UNIT_NONE}
    return result


def flag_in_extent(links: Sequence[Mapping[str, Any]], intersected_edge_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Return the links with ``in_flood_extent`` set from the edges a flood input intersects.

    Args:
        links: Ranked link rows.
        intersected_edge_ids: The edge IDs ``floodguard.closure_rules.edge_intersections``
            returns for one flood input: more than 1e-6 m of the edge inside the extent.
    """

    inside = set(intersected_edge_ids)
    return [{**row, "in_flood_extent": row["edge_id"] in inside} for row in links]


def reroute_after_closure(
    edges: Sequence[Mapping[str, Any]],
    population: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
    closed_edge_ids: Iterable[str],
) -> dict[str, Any]:
    """Close some edges, rebuild every route and count the residents who lose every route.

    The count is the one protocol v1a (road criticality) and protocol v1b (class
    rule v2, trigger B) name: residents who had a baseline route to a destination
    and have none after the closure. Residents who keep a route that takes longer
    are counted beside it. Every node of the baseline graph is kept, so a
    resident whose origin node is itself a destination keeps that route.

    Raises:
        CriticalLinkError: when a closed edge is not in the graph.
    """

    closed = set(closed_edge_ids)
    if closed - {edge["edge_id"] for edge in edges}:
        raise CriticalLinkError("a closed edge is not in the graph")
    graph = _adjacency(edges)
    demand, _totals = origin_demand(population, graph)
    before = shortest_path_tree(edges, destinations)["minutes"]
    after = shortest_path_tree(
        [edge for edge in edges if edge["edge_id"] not in closed], destinations, nodes=graph
    )["minutes"]
    with_route = sorted(node for node in demand if node in before)
    lost = [node for node in with_route if node not in after]
    slower = [node for node in with_route if node in after and after[node] > before[node]]
    return {
        "closed_edge_ids": sorted(closed),
        "residents_with_a_baseline_route": math.fsum(demand[node] for node in with_route),
        "residents_losing_every_route": math.fsum(demand[node] for node in lost),
        "residents_with_a_longer_route": math.fsum(demand[node] for node in slower),
        "origin_nodes_losing_every_route": lost,
    }


def ranking_table(
    links: Sequence[Mapping[str, Any]],
    units: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    context_canonical_sha256: str,
) -> bytes:
    """Serialise the whole ranking as canonical JSON: the bytes whose SHA-256 binds it.

    Args:
        links: The ranked rows of ``rank_links``.
        units: ``assign_units`` for those rows, or None when no unit is assigned.
        context_canonical_sha256: The canonical SHA-256 of the context the ranking belongs to.

    Returns:
        ASCII JSON with sorted keys, no spaces and one final newline. The same
        ranking gives the same bytes.
    """

    rows = [
        {**row, **({key: units[row["edge_id"]][key] for key in ("unit_id", "unit_assignment")} if units is not None else {})}
        for row in links
    ]
    document = {
        "schema_version": RANKING_TABLE_SCHEMA,
        "ranking_rule_version": RANKING_RULE_VERSION,
        "tie_break": TIE_BREAK,
        "context_canonical_sha256": context_canonical_sha256,
        "links": rows,
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return (text + "\n").encode("ascii")


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of some bytes as lowercase hex."""

    return hashlib.sha256(data).hexdigest()


def link_features(
    links: Sequence[Mapping[str, Any]],
    node_coordinates: Mapping[str, Sequence[float]],
    properties: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return one GeoJSON feature per link: the straight segment between its two nodes.

    Args:
        links: Ranked link rows (for example the first 20).
        node_coordinates: Longitude and latitude (WGS84) of every node.
        properties: Properties every feature carries: source timestamp,
            confidence, assumptions and status. A link's own values come last.
    """

    features = []
    for row in links:
        try:
            line = [[float(value) for value in node_coordinates[row[key]][:2]] for key in ("from_node", "to_node")]
        except KeyError as error:
            raise CriticalLinkError(f"a link refers to an unknown node: {error.args[0]}") from error
        features.append({
            "type": "Feature",
            "properties": {**properties, **row},
            "geometry": {"type": "LineString", "coordinates": line},
        })
    return features
