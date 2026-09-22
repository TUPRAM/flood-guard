"""Topology impacts must agree with actual access loss, including parallel roads."""

import random

import networkx as nx
import pytest

from floodguard.evidence_connectivity import audit_connectivity
from floodguard.evidence_scenarios import calculate_total_access


def fixture(edges, sites=("d",)):
    roads = [
        {"edge_id": str(i), "from_node": u, "to_node": v, "normal_minutes": 1}
        for i, (u, v) in enumerate(edges)
    ]
    nodes = sorted({n for pair in edges for n in pair})
    pops = [
        {
            "population_id": n,
            "subdistrict_id": "area",
            "node_id": n,
            "snap_distance_m": 0,
            "total_population": (i + 1) * 1.1,
        }
        for i, n in enumerate(nodes)
    ]
    facilities = [
        {"facility_id": str(i), "node_id": n, "snap_distance_m": 0}
        for i, n in enumerate(sites)
    ]
    return pops, roads, facilities


@pytest.mark.parametrize("sites", [("d",), ("a", "d"), ()])
def test_parallel_edges_and_disconnected_demand(sites):
    pops, edges, facilities = fixture(
        [("a", "b"), ("a", "b"), ("b", "c"), ("c", "d"), ("x", "y")], sites
    )
    pops.append(
        {
            "population_id": "unknown",
            "subdistrict_id": "area",
            "node_id": "a",
            "snap_distance_m": 251,
            "total_population": 1000,
        }
    )
    result = audit_connectivity(pops, edges, facilities)
    assert result["bridges"] == 3
    assert result["articulation_points"] == 2
    assert result["residents_without_accepted_connector"] == 1000
    for row in result["edge_impacts"]:
        actual = calculate_total_access(
            pops, edges, facilities, scenario={"closed_edge_ids": [row["edge_id"]]}
        )
        lost = sum(
            r["total_population"]
            for r in actual["node_results"]
            if r["normal_access_minutes"] is not None
            and r["scenario_access_minutes"] is None
        )
        assert row["residents_losing_all_routes"] == pytest.approx(lost)
    assert result["edge_impacts"][0]["is_bridge"] is False


def test_articulation_impacts_against_brute_force():
    rng = random.Random(402)
    for _ in range(12):
        graph = nx.gnp_random_graph(15, 0.13, seed=rng.randrange(10000))
        pairs = [(str(a), str(b)) for a, b in graph.edges]
        if not pairs:
            continue
        pops, edges, facilities = fixture(pairs, ("0", "8"))
        result = audit_connectivity(pops, edges, facilities)
        graph = nx.Graph(pairs)
        destinations = {f["node_id"] for f in facilities} & set(graph)
        before = (
            set().union(*(nx.node_connected_component(graph, n) for n in destinations))
            if destinations
            else set()
        )
        for row in result["articulation_impacts"]:
            changed = graph.copy()
            changed.remove_node(row["node_id"])
            after = set().union(
                *(
                    nx.node_connected_component(changed, n)
                    for n in destinations
                    if n in changed
                )
            )
            expected = sum(
                p["total_population"] for p in pops if p["node_id"] in before - after
            )
            assert row["residents_losing_all_routes"] == pytest.approx(expected)


def test_empty_graph():
    result = audit_connectivity([], [], [])
    assert result["bridges"] == result["articulation_points"] == 0
    assert result["edge_impacts"] == result["articulation_impacts"] == []


def test_multiple_connectors_do_not_duplicate_service_or_demand():
    pops, edges, sites = fixture([("a", "b"), ("b", "c"), ("c", "d")])
    sites[0]["connectors"] = [{"node_id": n, "snap_distance_m": 10} for n in ("a", "d")]
    result = audit_connectivity(pops, edges, sites)
    assert result["eligible_destination_connectors"] == 2
    assert all(r["residents_losing_all_routes"] == 0 for r in result["edge_impacts"])
    access = calculate_total_access(
        pops, edges, sites, scenario={"closed_edge_ids": ["1"]}
    )
    assert len(access["scenario_reachable_pairs"]) == len(pops)
    assert all(r["scenario_access_minutes"] is not None for r in access["node_results"])


def test_unaccepted_extra_connector_does_not_rescue_access():
    pops, edges, sites = fixture([("a", "b"), ("b", "d")])
    sites[0]["connectors"] = [
        {"node_id": "a", "snap_distance_m": 101},
        {"node_id": "d", "snap_distance_m": 0},
    ]
    result = audit_connectivity(pops, edges, sites)
    assert result["eligible_destination_connectors"] == 1
    assert result["edge_impacts"][0]["residents_losing_all_routes"] > 0
