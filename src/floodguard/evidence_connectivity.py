"""Source-bound topology diagnostics; graph dependency is not observed isolation."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from floodguard.evidence_scenarios import calculate_total_access, facility_connectors


def _tree_totals(
    tree: nx.Graph, demand: Mapping[Any, float], sites: Mapping[Any, int]
) -> tuple[dict, dict, dict, dict]:
    """Aggregate a forest once so each cut can be evaluated in linear total time."""
    parent, subtotal, total, order = {}, {}, {}, []
    for root in tree:
        if root in parent:
            continue
        parent[root] = None
        stack, component = [root], []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in tree[node]:
                if neighbor not in parent:
                    parent[neighbor] = node
                    stack.append(neighbor)
        for node in reversed(component):
            children = [n for n in tree[node] if parent.get(n) == node]
            subtotal[node] = (
                math.fsum([demand.get(node, 0), *(subtotal[n][0] for n in children)]),
                sites.get(node, 0) + sum(subtotal[n][1] for n in children),
            )
        for node in component:
            total[node] = subtotal[root]
        order.extend(component)
    return parent, subtotal, total, {node: i for i, node in enumerate(order)}


def audit_connectivity(
    population: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    facilities: Sequence[Mapping[str, Any]],
    *,
    source_timestamp: str | None = None,
) -> dict[str, Any]:
    """Count bridges/cut vertices and residents losing *all* destination routes.

    Uses the same connector acceptance and baseline demand as total access.
    Parallel road edges are retained: neither parallel edge is a bridge.
    Edge impacts are individual removals, never additive. Node removal also
    removes demand and destinations attached to that node. Already inaccessible
    demand and missing connectors are reported separately, never newly lost.
    """
    baseline = calculate_total_access(population, edges, facilities)
    graph = nx.MultiGraph()
    for edge in edges:
        graph.add_edge(edge["from_node"], edge["to_node"], key=edge["edge_id"])
    simple = nx.Graph(graph)
    demand: dict[str, float] = defaultdict(float)
    for row in baseline["node_results"]:
        if row["snap_status"] == "connected":
            demand[row["node_id"]] += row["total_population"]
    sites: dict[str, int] = defaultdict(int)
    for site in facilities:
        for connection in facility_connectors(site):
            if (
                connection["node_id"] in graph
                and connection["snap_distance_m"] is not None
                and connection["snap_distance_m"] <= 100
            ):
                sites[connection["node_id"]] += 1

    bridges = {frozenset(pair) for pair in nx.bridges(graph)}
    without_bridges = simple.copy()
    without_bridges.remove_edges_from(tuple(pair) for pair in bridges)
    component_of, tree = {}, nx.Graph()
    weights, counts = {}, {}
    for index, nodes in enumerate(nx.connected_components(without_bridges)):
        tree.add_node(index)
        weights[index] = math.fsum(demand[n] for n in nodes)
        counts[index] = sum(sites[n] for n in nodes)
        component_of.update({n: index for n in nodes})
    for pair in bridges:
        start, end = tuple(pair)
        tree.add_edge(component_of[start], component_of[end])
    parent, subtotal, totals, _ = _tree_totals(tree, weights, counts)
    edge_rows = []
    for edge in sorted(edges, key=lambda row: row["edge_id"]):
        start, end = edge["from_node"], edge["to_node"]
        is_bridge = frozenset((start, end)) in bridges
        loss = 0.0
        if is_bridge:
            a, b = component_of[start], component_of[end]
            child = a if parent[a] == b else b
            subpop, subsites = subtotal[child]
            allpop, allsites = totals[child]
            if allsites:
                loss = (subpop if subsites == 0 else 0) + (
                    max(0.0, allpop - subpop) if allsites == subsites else 0
                )
        edge_rows.append(
            {
                "edge_id": edge["edge_id"],
                "osm_way_id": edge.get("osm_way_id"),
                "from_node": start,
                "to_node": end,
                "is_bridge": is_bridge,
                "residents_losing_all_routes": loss,
            }
        )

    # A block-cut forest gives all articulation impacts without rerouting once
    # per node. Demand on cut vertices is owned by the vertex, not every block.
    articulations = set(nx.articulation_points(simple))
    block_tree, owner = nx.Graph(), {}
    for node in sorted(articulations):
        key = ("node", node)
        block_tree.add_node(key)
        owner[node] = key
    for index, nodes in enumerate(nx.biconnected_components(simple)):
        block = ("block", index)
        block_tree.add_node(block)
        for node in nodes:
            if node in articulations:
                block_tree.add_edge(block, owner[node])
            else:
                owner[node] = block
    for node in nx.isolates(simple):
        owner[node] = ("isolated", node)
        block_tree.add_node(owner[node])
    block_demand: dict[Any, float] = defaultdict(float)
    block_sites: dict[Any, int] = defaultdict(int)
    for node in simple:
        block_demand[owner[node]] += demand[node]
        block_sites[owner[node]] += sites[node]
    parent, subtotal, totals, _ = _tree_totals(block_tree, block_demand, block_sites)
    node_rows = []
    for node in sorted(articulations):
        key = owner[node]
        allpop, allsites = totals[key]
        loss = demand[node] if allsites else 0.0
        if allsites:
            for neighbor in block_tree[key]:
                if parent.get(neighbor) == key:
                    side_pop, side_sites = subtotal[neighbor]
                else:
                    side_pop = max(0.0, allpop - subtotal[key][0])
                    side_sites = allsites - subtotal[key][1]
                if not side_sites:
                    loss += side_pop
        node_rows.append({"node_id": node, "residents_losing_all_routes": loss})
    rows = baseline["node_results"]
    return {
        "schema_version": "1.0",
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "evidence_role": "candidate",
        "official_warning": False,
        "operational_status": "non_operational",
        "method": "multigraph_bridges_and_block_cut_forest_v1",
        "baseline_input_sha256": baseline["baseline_input_sha256"],
        "nodes": graph.number_of_nodes(),
        "edges": len(edges),
        "connected_components": nx.number_connected_components(graph),
        "bridges": len(bridges),
        "articulation_points": len(articulations),
        "eligible_destination_connectors": sum(sites.values()),
        "baseline_residents_with_route": math.fsum(
            r["total_population"]
            for r in rows
            if r["normal_access_minutes"] is not None
        ),
        "baseline_residents_without_route": math.fsum(
            r["total_population"]
            for r in rows
            if r["snap_status"] == "connected" and r["normal_access_minutes"] is None
        ),
        "residents_without_accepted_connector": math.fsum(
            r["total_population"] for r in rows if r["snap_status"] != "connected"
        ),
        "edge_impacts": edge_rows,
        "articulation_impacts": node_rows,
        "assumptions": [
            "Individual deletion impacts overlap and must not be summed.",
            "All-route dependency, not travel-time threshold loss or observed isolation.",
            "A bridge in this extracted graph does not establish a unique real-world entrance.",
            "Destination connectors remain the existing unverified scenario assumptions.",
        ],
    }
