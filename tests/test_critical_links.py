"""Baseline critical-link ranking (plan task E6) on small invented graphs.

Every graph here is synthetic: the answers are worked out by hand in the
comments. No real place is routed, and nothing here reads a flood layer or
computes an FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

import json
import random

import networkx as nx
import pytest
from shapely.geometry import box

from floodguard import critical_links
from floodguard.critical_links import (
    FULL_REROUTE_TOP_N,
    OUTPUT_TOP_N,
    TIE_BREAK,
    UNIT_AMBIGUOUS,
    UNIT_ASSIGNED,
    UNIT_NONE,
    CriticalLinkError,
    assign_units,
    destinations_routed_onward,
    flag_in_extent,
    graph_bridges,
    link_features,
    origin_demand,
    rank_links,
    ranking_table,
    reroute_after_closure,
    sha256_bytes,
    shortest_path_tree,
    spt_flow,
)
from floodguard.evidence_scenarios import calculate_total_access
from floodguard.evidence_interventions import select_interventions
from floodguard.grade_join import JOIN_EDGE_KIND


def edge(key: str, a: str, b: str, minutes: float, **extra: object) -> dict:
    return {"edge_id": key, "from_node": a, "to_node": b, "normal_minutes": minutes, **extra}


def pop(key: str, node: str | None, residents: float, snap: float | None = 0.0) -> dict:
    return {"population_id": key, "node_id": node, "total_population": residents, "snap_distance_m": snap,
            "subdistrict_id": "invented"}


def site(key: str, node: str, snap: float = 0.0) -> dict:
    return {"facility_id": key, "node_id": node, "snap_distance_m": snap}


def flows(result: dict) -> dict[str, float]:
    return {row["edge_id"]: row["spt_flow_residents"] for row in result["links"]}


def test_protocol_parameters_are_the_ones_v1b_states() -> None:
    assert (FULL_REROUTE_TOP_N, OUTPUT_TOP_N, TIE_BREAK) == (200, 20, "stable edge ID")


def test_a_line_carries_the_residents_behind_each_edge() -> None:
    """a - b - c - d with the destination at d: 10 at a, 5 at b, none at c."""

    roads = [edge("ab", "a", "b", 1), edge("bc", "b", "c", 1), edge("cd", "c", "d", 1)]
    people = [pop("p-a", "a", 10), pop("p-b", "b", 5)]
    result = rank_links(roads, people, [site("hospital", "d")])
    # ab carries the 10 of a; bc and cd carry the 10 and the 5. bc and cd tie, and bc has the smaller ID.
    assert [(row["rank"], row["edge_id"], row["spt_flow_residents"]) for row in result["links"]] == [
        (1, "bc", 15), (2, "cd", 15), (3, "ab", 10)]
    summary = result["summary"]
    assert summary["residents"] == summary["connected_residents_with_a_baseline_route"] == 15
    assert summary["connected_residents_without_a_baseline_route"] == 0
    assert result["residents_by_destination"] == {"hospital": 15}
    # A line has no second route: every edge is a graph bridge.
    assert all(row["graph_bridge"] for row in result["links"])


def test_ranking_ties_break_on_the_edge_id_whatever_the_input_order() -> None:
    """Three spokes with the same residents: the ranking is the order of the edge IDs."""

    roads = [edge("spoke-c", "hub", "c", 1), edge("spoke-a", "hub", "a", 2), edge("spoke-b", "hub", "b", 3)]
    people = [pop("p-a", "a", 7), pop("p-b", "b", 7), pop("p-c", "c", 7)]
    sites = [site("hospital", "hub")]
    result = rank_links(roads, people, sites)
    assert [row["edge_id"] for row in result["links"]] == ["spoke-a", "spoke-b", "spoke-c"]
    assert rank_links(roads[::-1], people[::-1], sites) == result


def test_equal_routes_break_on_the_parent_node_and_then_the_edge_id() -> None:
    """A square: the origin o reaches the destination d through m or through n in the same time."""

    roads = [edge("d-m", "d", "m", 1), edge("d-n", "d", "n", 1), edge("m-o", "m", "o", 1), edge("n-o", "n", "o", 1)]
    people = [pop("p-o", "o", 4)]
    result = rank_links(roads, people, [site("hospital", "d")])
    # Both routes take 2 minutes. The tree keeps the smaller (parent node, edge ID): through m.
    assert flows(result) == {"d-m": 4, "m-o": 4}
    assert rank_links(roads[::-1], people, [site("hospital", "d")]) == result
    # Two edges between the same nodes with the same time: the smaller edge ID carries the route.
    twin = [edge("twin-2", "d", "o", 1), edge("twin-1", "d", "o", 1)]
    assert flows(rank_links(twin, people, [site("hospital", "d")])) == {"twin-1": 4}


def test_equally_near_destinations_break_on_the_destination_id() -> None:
    roads = [edge("left", "o", "x", 2), edge("right", "o", "y", 2)]
    people = [pop("p-o", "o", 9)]
    result = rank_links(roads, people, [site("site-b", "x"), site("site-a", "y")])
    assert flows(result) == {"right": 9}
    assert result["residents_by_destination"] == {"site-a": 9}


def test_a_destination_enters_with_the_time_of_its_connector() -> None:
    """A hospital 100 m from its node costs 1.2 minutes at 5 km/h, so a nearer plain destination can win."""

    roads = [edge("to-hospital", "o", "h", 1), edge("to-entry", "o", "e", 2)]
    people = [pop("p-o", "o", 3)]
    hospital = site("hospital", "h", 100.0)
    entry = site("entry", "e", 0.0)
    tree = shortest_path_tree(roads, [hospital, entry])
    assert tree["minutes"]["h"] == pytest.approx(1.2) and tree["minutes"]["o"] == pytest.approx(2.0)
    assert flows(rank_links(roads, people, [hospital, entry])) == {"to-entry": 3}
    # Beyond the 100 m limit a destination is left out, as in the access code.
    assert flows(rank_links(roads, people, [site("hospital", "h", 100.1), entry])) == {"to-entry": 3}
    assert rank_links(roads, people, [site("hospital", "h", 100.1)])["links"] == []


def test_an_edge_between_two_destinations_carries_nobody() -> None:
    """Hospital and main-road entries as one destination set: a route ends at the first destination it meets."""

    roads = [
        edge("feeder", "home", "m1", 2, road_class="residential"),
        edge("main-road", "m1", "m2", 1, road_class="trunk"),
        edge("to-hospital", "m2", "h", 1, road_class="secondary"),
    ]
    people = [pop("p-home", "home", 50), pop("p-m2", "m2", 8)]
    sites = [site("OSM-way-1", "h", 20.0), site("main-road-entry-m1", "m1"), site("main-road-entry-m2", "m2")]
    result = rank_links(roads, people, sites)
    # The 50 stop at m1 and the 8 are already at m2: only the feeder carries anybody.
    assert flows(result) == {"feeder": 50}
    assert result["residents_by_destination"] == {"main-road-entry-m1": 50, "main-road-entry-m2": 8}
    assert result["summary"]["destinations_supplied"] == 3
    assert result["summary"]["destinations_that_are_a_nearest_destination"] == 2
    assert result["summary"]["destination_nodes_routed_onward_at_an_equal_time"] == 0


def test_a_zero_minute_edge_between_two_destination_nodes_is_crossed_towards_the_smaller_id() -> None:
    """Open point E6-OP7: this documents what the comparison of select_interventions does; it decides nothing.

    Two main-road entries a and b share a coordinate and a grade-join connector that takes no time. Both enter the
    tree at 0 minutes. (0, "main-road-entry-a") is smaller than (0, "main-road-entry-b"), so node b is given to
    entry a and gets the connector as its tree edge: the 10 residents standing at entry b and the 4 whose route
    reaches it count on the connector.
    """

    roads = [edge("grade-join-ab", "a", "b", 0.0, edge_kind=JOIN_EDGE_KIND, length_m=0.0),
             edge("street", "b", "c", 1)]
    people = [pop("p-b", "b", 10), pop("p-c", "c", 4)]
    sites = [site("main-road-entry-a", "a"), site("main-road-entry-b", "b")]
    result = rank_links(roads, people, sites)
    assert flows(result) == {"grade-join-ab": 14, "street": 4}
    assert result["residents_by_destination"] == {"main-road-entry-a": 14}
    tree = shortest_path_tree(roads, sites)
    assert tree["entry_minutes"] == {"a": 0.0, "b": 0.0} and tree["predecessor"]["b"] == ("a", "grade-join-ab")
    assert destinations_routed_onward(tree, flows(result)) == {
        "nodes": ["b"], "nodes_carrying_residents_onward": 1, "residents_carried_onward": 14}
    summary = result["summary"]
    assert summary["destination_nodes_routed_onward_at_an_equal_time"] == 1
    assert summary["destination_nodes_carrying_residents_onward_at_an_equal_time"] == 1
    assert summary["residents_carried_onward_from_a_destination_node_at_an_equal_time"] == 14
    # Nobody at entry b or behind it: the node is still routed onward, and it carries nobody.
    empty = rank_links(roads, [], sites)["summary"]
    assert empty["destination_nodes_routed_onward_at_an_equal_time"] == 1
    assert empty["destination_nodes_carrying_residents_onward_at_an_equal_time"] == 0
    assert empty["residents_carried_onward_from_a_destination_node_at_an_equal_time"] == 0
    # Three entries in a row: c is given to a through b. A resident who passes both is counted once.
    chain = [edge("grade-join-ab", "a", "b", 0.0, edge_kind=JOIN_EDGE_KIND), edge("grade-join-bc", "b", "c", 0.0,
             edge_kind=JOIN_EDGE_KIND)]
    three = [*sites, site("main-road-entry-c", "c")]
    chained = rank_links(chain, [pop("p-b", "b", 5), pop("p-c", "c", 10)], three)
    assert flows(chained) == {"grade-join-ab": 15, "grade-join-bc": 10}
    assert destinations_routed_onward(shortest_path_tree(chain, three), flows(chained)) == {
        "nodes": ["b", "c"], "nodes_carrying_residents_onward": 2, "residents_carried_onward": 15}
    # select_interventions, which the protocol names as the pattern, does the same on this graph.
    pattern = select_interventions(people, roads, sites, calculate_total_access(people, roads, sites))
    assert [(row["edge_id"], row["baseline_route_population"]) for row in pattern["candidates"]["close_edge"]] == [
        ("grade-join-ab", 14), ("street", 4)]

    # With an edge that takes time the residents at entry b stay there: only a tie moves them.
    timed = [edge("link-ab", "a", "b", 1), edge("street", "b", "c", 1)]
    result = rank_links(timed, people, sites)
    assert flows(result) == {"street": 4} and result["summary"]["destination_nodes_routed_onward_at_an_equal_time"] == 0
    # A destination that another one reaches in less time is routed onward too, but that is a shorter route, not a
    # tie: the hospital stands 100 m from node h (1.2 minutes) and entry e is 1 minute away.
    nearer = [edge("h-e", "h", "e", 1)]
    tree = shortest_path_tree(nearer, [site("hospital", "h", 100.0), site("entry", "e")])
    assert tree["predecessor"]["h"] == ("e", "h-e") and tree["minutes"]["h"] == pytest.approx(1.0)
    assert destinations_routed_onward(tree, {"h-e": 5.0})["nodes"] == []


def test_disconnected_nodes_have_no_route_and_carry_no_flow() -> None:
    roads = [edge("ab", "a", "b", 1), edge("xy", "x", "y", 1)]
    people = [
        pop("served", "a", 10),
        pop("island", "x", 6),             # on the graph, but its component has no destination
        pop("no-node", None, 3, None),     # not snapped to the graph
        pop("too-far", "a", 2, 250.5),     # snapped beyond 250 m
        pop("unknown-node", "ghost", 1),   # its node is not in the graph
        pop("empty", "y", 0),              # a cell with no resident
    ]
    result = rank_links(roads, people, [site("hospital", "b")])
    assert flows(result) == {"ab": 10}
    summary = result["summary"]
    assert summary["residents"] == 22
    assert summary["residents_connected_to_the_graph"] == 16
    assert summary["residents_not_connected_to_the_graph"] == 6
    assert summary["connected_residents_with_a_baseline_route"] == 10
    assert summary["connected_residents_without_a_baseline_route"] == 6
    assert summary["origin_nodes"] == 2 and summary["origin_nodes_with_a_baseline_route"] == 1
    assert summary["nodes_reached_by_the_tree"] == 2 and summary["graph_nodes"] == 4
    # The access code counts the same people as connected without a route.
    access = calculate_total_access(people, roads, [site("hospital", "b")])
    review = access["coverage_review"]
    assert review["missing_graph_coverage_population"] == summary["residents_not_connected_to_the_graph"]
    assert review["baseline"]["graph_connected_no_modelled_route_population"] == (
        summary["connected_residents_without_a_baseline_route"])
    demand, totals = origin_demand(people, {"a", "b", "x", "y"})
    assert demand == {"a": 10, "x": 6} and totals["residents"] == 22


def _bridge_town() -> tuple[list[dict], list[dict], list[dict]]:
    """A ring of four streets (r1-r4) with the hospital on it, and a village behind one river bridge."""

    roads = [
        edge("ring-1", "h", "r1", 1), edge("ring-2", "r1", "r2", 1),
        edge("ring-3", "r2", "r3", 1), edge("ring-4", "r3", "h", 1),
        edge("river-bridge", "r2", "v1", 1, bridge="yes"),
        edge("village-street", "v1", "v2", 1),
    ]
    people = [pop("p-r1", "r1", 30), pop("p-r2", "r2", 5), pop("p-v1", "v1", 40), pop("p-v2", "v2", 20)]
    return roads, people, [site("hospital", "h")]


def test_a_bridge_is_flagged_and_closing_it_isolates_exactly_its_flow() -> None:
    roads, people, sites = _bridge_town()
    assert graph_bridges(roads) == {"river-bridge", "village-street"}
    result = rank_links(roads, people, sites)
    # r2 is 2 minutes from the hospital both ways round; the tree keeps the smaller parent node, r1.
    assert flows(result) == {"ring-1": 95, "ring-2": 65, "river-bridge": 60, "village-street": 20}
    by_id = {row["edge_id"]: row for row in result["links"]}
    assert by_id["river-bridge"]["graph_bridge"] is True and by_id["river-bridge"]["osm_bridge"] is True
    assert by_id["village-street"]["graph_bridge"] is True and by_id["village-street"]["osm_bridge"] is False
    assert by_id["ring-1"]["graph_bridge"] is False and by_id["ring-2"]["graph_bridge"] is False
    assert result["summary"]["graph_bridge_edges"] == 2
    assert result["summary"]["ranked_links_that_are_graph_bridges"] == 2

    # The all-routes-lost case: nobody behind a graph bridge has another route.
    lost = reroute_after_closure(roads, people, sites, ["river-bridge"])
    assert lost["residents_losing_every_route"] == by_id["river-bridge"]["spt_flow_residents"] == 60
    assert lost["origin_nodes_losing_every_route"] == ["v1", "v2"]
    assert lost["residents_with_a_baseline_route"] == 95 and lost["residents_with_a_longer_route"] == 0
    # A ring edge has a way round: its 95 residents all keep a route, and 30 of them take longer.
    kept = reroute_after_closure(roads, people, sites, ["ring-1"])
    assert kept["residents_losing_every_route"] == 0 and kept["origin_nodes_losing_every_route"] == []
    assert kept["residents_with_a_longer_route"] == 30
    with pytest.raises(CriticalLinkError, match="not in the graph"):
        reroute_after_closure(roads, people, sites, ["no-such-edge"])


def test_only_a_graph_bridge_can_take_every_route_from_anybody() -> None:
    """The fact behind open point E6-OP5: a link that is not a graph bridge, closed on its own, isolates nobody."""

    generator = random.Random(605)
    isolating = 0
    for _ in range(40):
        nodes = [f"n{index:02d}" for index in range(generator.randint(4, 14))]
        pairs = sorted({tuple(sorted(generator.sample(nodes, 2))) for _ in range(generator.randint(3, 22))})
        # Minutes 0 to 2: zero-minute edges are in, as grade-join connectors are in the real graph.
        roads = [edge(f"e-{a}-{b}", a, b, generator.randint(0, 2)) for a, b in pairs]
        used = sorted({node for pair in pairs for node in pair})
        people = [pop(f"p-{node}", node, generator.randint(1, 9)) for node in used]
        sites = [site("site-1", used[0]), site("site-2", used[-1])]
        for row in rank_links(roads, people, sites)["links"]:
            lost = reroute_after_closure(roads, people, sites, [row["edge_id"]])["residents_losing_every_route"]
            if not row["graph_bridge"]:
                assert lost == 0, row["edge_id"]
            isolating += lost > 0
    assert isolating > 20, "the fixture must hold bridges whose closure isolates somebody"


def test_a_resident_at_a_destination_keeps_the_route_when_every_edge_there_closes() -> None:
    roads = [edge("only", "h", "a", 1)]
    people = [pop("at-hospital", "h", 4), pop("p-a", "a", 6)]
    result = reroute_after_closure(roads, people, [site("hospital", "h")], ["only"])
    assert result["residents_with_a_baseline_route"] == 10
    assert result["residents_losing_every_route"] == 6


def test_two_edges_between_the_same_nodes_are_not_bridges_and_a_connector_can_be_one() -> None:
    roads = [edge("twin-1", "a", "b", 1), edge("twin-2", "a", "b", 2), edge("tail", "b", "c", 1)]
    assert graph_bridges(roads) == {"tail"}
    # A zero-minute grade-join connector is an edge of the graph like any other.
    joined = [edge("road-1", "a", "b", 1), edge("road-2", "b2", "c", 1),
              edge("grade-join-1", "b", "b2", 0.0, edge_kind=JOIN_EDGE_KIND, length_m=0.0)]
    assert graph_bridges(joined) == {"road-1", "road-2", "grade-join-1"}
    result = rank_links(joined, [pop("p-c", "c", 5)], [site("hospital", "a")])
    kinds = {row["edge_id"]: row["edge_kind"] for row in result["links"]}
    assert kinds == {"grade-join-1": JOIN_EDGE_KIND, "road-1": "road", "road-2": "road"}
    # Three equal flows: the edge ID decides, whatever the kind of edge.
    assert [row["edge_id"] for row in result["links"]] == ["grade-join-1", "road-1", "road-2"]


def test_bridge_finding_agrees_with_networkx_on_random_graphs() -> None:
    generator = random.Random(20261004)
    for _ in range(60):
        nodes = [f"n{index:02d}" for index in range(generator.randint(2, 30))]
        pairs = {tuple(sorted(generator.sample(nodes, 2))) for _ in range(generator.randint(1, 40))}
        roads = [edge(f"e-{a}-{b}", a, b, 1) for a, b in sorted(pairs)]
        graph = nx.Graph()
        graph.add_edges_from(pairs)
        expected = {f"e-{min(a, b)}-{max(a, b)}" for a, b in nx.bridges(graph)}
        assert graph_bridges(roads) == expected


def test_a_long_road_does_not_hit_the_recursion_limit() -> None:
    roads = [edge(f"e{index:05d}", f"n{index:05d}", f"n{index + 1:05d}", 1) for index in range(5000)]
    assert len(graph_bridges(roads)) == 5000
    result = rank_links(roads, [pop("far", "n05000", 2)], [site("hospital", "n00000")])
    assert len(result["links"]) == 5000 and {row["spt_flow_residents"] for row in result["links"]} == {2}


def test_the_ranking_is_the_close_edge_ranking_of_select_interventions() -> None:
    """Protocol v1b says the selection follows evidence_interventions.py: same flows, same order."""

    generator = random.Random(7)
    nodes = [f"n{index:02d}" for index in range(40)]
    pairs = sorted({tuple(sorted(generator.sample(nodes, 2))) for _ in range(70)})
    # Whole minutes make equal routes common, so the tie rules are exercised.
    roads = [edge(f"e-{a}-{b}", a, b, generator.randint(1, 3)) for a, b in pairs]
    used = sorted({node for pair in pairs for node in pair})
    people = [pop(f"p-{node}", node, generator.randint(1, 9)) for node in used]
    sites = [site("site-2", used[0]), site("site-1", used[-1], 30.0), site("site-3", used[len(used) // 2])]
    baseline = calculate_total_access(people, roads, sites)
    pattern = select_interventions(people, roads, sites, baseline)
    result = rank_links(roads, people, sites)
    assert pattern["candidate_counts"]["close_edge"] == len(result["links"]) > 10
    assert [(row["edge_id"], row["spt_flow_residents"]) for row in result["links"][:10]] == [
        (row["edge_id"], row["baseline_route_population"]) for row in pattern["candidates"]["close_edge"]]
    # The tree gives the same travel time as the access code for every origin with a route.
    tree = shortest_path_tree(roads, sites)
    for row in baseline["node_results"]:
        assert tree["minutes"][row["node_id"]] == pytest.approx(row["normal_access_minutes"])
    assert set(spt_flow(tree, origin_demand(people, tree["minutes"])[0])) == set(flows(result))


def test_the_ranking_follows_select_interventions_across_zero_minute_edges_too() -> None:
    """Grade-join connectors take no time, which select_interventions never met: the two still agree."""

    generator = random.Random(1307)
    for _ in range(25):
        nodes = [f"n{index:02d}" for index in range(generator.randint(5, 25))]
        pairs = sorted({tuple(sorted(generator.sample(nodes, 2))) for _ in range(generator.randint(4, 45))})
        roads = [edge(f"e-{a}-{b}", a, b, generator.randint(0, 2)) for a, b in pairs]
        used = sorted({node for pair in pairs for node in pair})
        people = [pop(f"p-{node}", node, generator.randint(1, 9)) for node in used]
        sites = [site(f"site-{index}", node) for index, node in enumerate(generator.sample(used, min(3, len(used))))]
        pattern = select_interventions(people, roads, sites, calculate_total_access(people, roads, sites))
        ranked = rank_links(roads, people, sites)["links"]
        assert pattern["candidate_counts"]["close_edge"] == len(ranked)
        assert [(row["edge_id"], row["spt_flow_residents"]) for row in ranked[:10]] == [
            (row["edge_id"], row["baseline_route_population"]) for row in pattern["candidates"]["close_edge"]]


def test_malformed_inputs_are_refused() -> None:
    roads = [edge("ab", "a", "b", 1)]
    with pytest.raises(CriticalLinkError, match="edge IDs must be unique"):
        rank_links([*roads, edge("ab", "b", "c", 1)], [], [site("s", "a")])
    with pytest.raises(CriticalLinkError, match="node to itself"):
        rank_links([edge("loop", "a", "a", 1)], [], [site("s", "a")])
    with pytest.raises(CriticalLinkError, match="destination IDs must be unique"):
        rank_links(roads, [], [site("s", "a"), site("s", "b")])
    with pytest.raises(CriticalLinkError, match="population IDs must be unique"):
        rank_links(roads, [pop("p", "a", 1), pop("p", "b", 1)], [site("s", "a")])
    with pytest.raises(CriticalLinkError, match="resident count"):
        rank_links(roads, [pop("p", "a", float("nan"))], [site("s", "a")])
    with pytest.raises(CriticalLinkError, match="travel time"):
        rank_links([edge("ab", "a", "b", -1)], [], [site("s", "a")])
    with pytest.raises(CriticalLinkError, match="normal_minutes or a modelled road_class"):
        rank_links([{"edge_id": "ab", "from_node": "a", "to_node": "b", "length_m": 5.0, "road_class": "path"}], [],
                   [site("s", "a")])
    # Without normal_minutes the class speed applies: 1 km of trunk road at 70 km/h.
    timed = shortest_path_tree(
        [{"edge_id": "ab", "from_node": "a", "to_node": "b", "length_m": 1000.0, "road_class": "trunk"}], [site("s", "a")])
    assert timed["minutes"]["b"] == pytest.approx(60 / 70)


# Two invented units side by side near 100 E, 20 N; the boundary is the meridian 100.01. A third polygon overlaps
# the south of the east unit, as a badly drawn boundary file would.
WEST = ("unit-west", box(100.00, 20.00, 100.01, 20.01))
EAST = ("unit-east", box(100.01, 20.00, 100.02, 20.01))
OVERLAP = ("unit-overlap", box(100.012, 19.99, 100.02, 20.003))
NODES = {
    "w1": [100.002, 20.005], "w2": [100.004, 20.005],      # both in the west unit
    "x1": [100.008, 20.005], "x2": [100.018, 20.005],      # crosses the boundary; midpoint 100.013 is east
    "y1": [100.004, 20.005], "y2": [100.012, 20.005],      # crosses the boundary; midpoint 100.008 is west
    "o1": [100.030, 20.005], "o2": [100.040, 20.005],      # outside every unit
    "b1": [100.014, 20.001], "b2": [100.016, 20.001],      # where the east unit and the third polygon overlap
    "j1": [100.015, 20.006], "j2": [100.015, 20.006],      # a zero-length connector in the east unit
}


def test_a_link_belongs_to_the_unit_that_holds_its_midpoint() -> None:
    """Drafter reading DR-B06: where the edge lies; an edge that crosses a boundary goes by its midpoint."""

    roads = [
        edge("inside-west", "w1", "w2", 1), edge("crossing-east", "x1", "x2", 1), edge("crossing-west", "y1", "y2", 1),
        edge("outside", "o1", "o2", 1), edge("in-two-units", "b1", "b2", 1), edge("connector", "j1", "j2", 0),
    ]
    assigned = assign_units(roads, NODES, [WEST, EAST, OVERLAP])
    assert assigned["inside-west"] == {"unit_id": "unit-west", "unit_assignment": UNIT_ASSIGNED}
    assert assigned["crossing-east"] == {"unit_id": "unit-east", "unit_assignment": UNIT_ASSIGNED}
    assert assigned["crossing-west"] == {"unit_id": "unit-west", "unit_assignment": UNIT_ASSIGNED}
    assert assigned["connector"] == {"unit_id": "unit-east", "unit_assignment": UNIT_ASSIGNED}
    # The protocol gives no rule for these two, so no unit is assigned.
    assert assigned["outside"] == {"unit_id": None, "unit_assignment": UNIT_NONE}
    assert assigned["in-two-units"] == {"unit_id": None, "unit_assignment": UNIT_AMBIGUOUS}
    assert assign_units(roads[::-1], NODES, [OVERLAP, EAST, WEST]) == assigned
    assert assign_units([], NODES, [WEST]) == {}
    assert assign_units(roads[:1], NODES, [])["inside-west"]["unit_assignment"] == UNIT_NONE
    with pytest.raises(CriticalLinkError, match="unit IDs must be unique"):
        assign_units(roads, NODES, [WEST, WEST])
    with pytest.raises(CriticalLinkError, match="unknown node"):
        assign_units([edge("lost", "w1", "nowhere", 1)], NODES, [WEST])


def test_the_in_extent_flag_comes_from_the_intersected_edges_of_a_flood_input() -> None:
    roads, people, sites = _bridge_town()
    links = rank_links(roads, people, sites)["links"]
    assert all("in_flood_extent" not in row for row in links)
    flagged = flag_in_extent(links, {"river-bridge", "an-unranked-edge"})
    assert {row["edge_id"] for row in flagged if row["in_flood_extent"]} == {"river-bridge"}
    assert [row["rank"] for row in flagged] == [row["rank"] for row in links]


def test_the_ranking_table_and_the_features_are_reproducible() -> None:
    roads = [edge("west-road", "w1", "w2", 1, road_class="local", length_m=200.0, osm_way_id="11"),
             edge("cross-road", "w2", "x2", 1, road_class="local", length_m=1400.0, osm_way_id="12")]
    people = [pop("p-w1", "w1", 12), pop("p-w2", "w2", 3)]
    sites = [site("hospital", "x2")]
    links = rank_links(roads, people, sites)["links"]
    units = assign_units(links, NODES, [WEST, EAST])
    table = ranking_table(links, units, context_canonical_sha256="c" * 64)
    assert table.endswith(b"\n") and b"\r" not in table and table.decode("ascii")
    document = json.loads(table)
    assert document["schema_version"] == critical_links.RANKING_TABLE_SCHEMA
    assert document["context_canonical_sha256"] == "c" * 64 and document["tie_break"] == TIE_BREAK
    assert [(row["rank"], row["edge_id"], row["spt_flow_residents"], row["unit_id"]) for row in document["links"]] == [
        (1, "cross-road", 15, "unit-east"), (2, "west-road", 12, "unit-west")]
    again = rank_links(roads[::-1], people[::-1], sites)["links"]
    assert sha256_bytes(ranking_table(again, assign_units(again, NODES, [EAST, WEST]),
                                      context_canonical_sha256="c" * 64)) == sha256_bytes(table)
    assert "unit_id" not in json.loads(ranking_table(links, context_canonical_sha256="c" * 64))["links"][0]

    features = link_features(links, NODES, {"source_timestamp": "2026-01-01T00:00:00Z", "confidence_class": "low"})
    assert [feature["properties"]["rank"] for feature in features] == [1, 2]
    assert features[0]["geometry"] == {"type": "LineString", "coordinates": [[100.004, 20.005], [100.018, 20.005]]}
    assert features[0]["properties"]["confidence_class"] == "low" and features[0]["properties"]["osm_way_id"] == "12"
    with pytest.raises(CriticalLinkError, match="unknown node"):
        link_features([{**links[0], "to_node": "nowhere"}], NODES, {})
