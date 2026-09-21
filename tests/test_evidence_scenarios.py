"""Small invented graph fixtures verify the explicit planning scenario lane."""

import json
import math
from copy import deepcopy

import pytest

from floodguard.evidence_scenarios import (
    EvidenceScenarioError,
    allocate_shelter_capacity,
    build_illustrative_scenarios,
    calculate_total_access,
    evidence_assessment,
)
from floodguard.scoring import SCORE_COMPONENTS


def population(key="p", node="a", demand=100, snap=0, area="area"):
    return {
        "population_id": key,
        "subdistrict_id": area,
        "node_id": node,
        "total_population": demand,
        "snap_distance_m": snap,
    }


def facility(key="s", node="b", capacity=None, snap=0):
    return {
        "facility_id": key,
        "node_id": node,
        "capacity": capacity,
        "snap_distance_m": snap,
    }


def edge(key="ab", start="a", end="b", minutes=10):
    return {
        "edge_id": key,
        "from_node": start,
        "to_node": end,
        "normal_minutes": minutes,
    }


def pair(person="p", site="s", minutes=10):
    return {"population_id": person, "facility_id": site, "travel_minutes": minutes}


def test_total_only_access_counts_new_loss_separately_from_existing_isolation():
    pops = [
        population(),
        population("isolated", "c", demand=20),
        population("bad-snap", "a", demand=7, snap=251),
    ]
    edges = [edge(), edge("cd", "c", "d")]
    result = calculate_total_access(
        pops, edges, [facility()], scenario={"closed_edge_ids": ["ab"]}
    )
    for threshold in (15, 30, 60):
        assert result["totals"][f"people_losing_{threshold}_min_access"] == 100
        assert result["totals"][f"people_already_without_{threshold}_min_access"] == 27
    assert result["totals"]["total_population"] == 127
    assert result["totals"]["unconnected_population"] == 7
    assert result["equity_gap_ratio"] is None
    assert result["equity_status"] == "unavailable_demographic_groups_not_supplied"
    assert "vulnerable_population" not in result["node_results"][0]


def test_both_walking_connectors_count_and_limits_are_inclusive():
    result = calculate_total_access(
        [population(snap=250)], [edge(minutes=11)], [facility(snap=100)]
    )
    assert result["node_results"][0]["normal_access_minutes"] == pytest.approx(15.2)
    assert result["totals"]["people_already_without_15_min_access"] == 100
    assert result["totals"]["people_already_without_30_min_access"] == 0
    assert result["connector_speed_kmh"] == 5
    too_far = calculate_total_access([population()], [edge()], [facility(snap=100.01)])
    assert too_far["node_results"][0]["normal_access_minutes"] is None
    assert (
        too_far["facility_snap_review"][0]["snap_status"] == "unconnected_snap_too_far"
    )


def test_destinations_can_be_removed_added_or_entirely_missing():
    removed = calculate_total_access(
        [population()], [edge()], [facility()], scenario={"removed_facility_ids": ["s"]}
    )
    assert removed["totals"]["people_losing_15_min_access"] == 100
    added = calculate_total_access(
        [population()], [edge()], [], scenario={"added_facilities": [facility()]}
    )
    assert added["totals"]["people_gaining_15_min_access"] == 100
    assert added["totals"]["people_already_without_15_min_access"] == 100
    assert added["totals"]["people_losing_15_min_access"] == 0
    absent = calculate_total_access([population()], [edge()], [])
    assert absent["totals"]["people_already_without_60_min_access"] == 100


def test_explicit_modelled_speed_and_parallel_edges_do_not_change_input():
    edges = [
        {
            "edge_id": "ab",
            "from_node": "a",
            "to_node": "b",
            "length_m": 1000,
            "road_class": "local",
        },
        edge("parallel", minutes=1),
    ]
    original = deepcopy(edges)
    result = calculate_total_access(
        [population()], edges, [facility()], scenario={"closed_edge_ids": ["parallel"]}
    )
    assert result["node_results"][0]["normal_access_minutes"] == 1
    assert result["node_results"][0]["scenario_access_minutes"] == 3
    assert result["modelled_road_speeds_kmh"]["local"] == 20
    assert edges == original


def test_unknown_and_disconnected_nodes_are_not_falsely_snapped():
    result = calculate_total_access(
        [population(node=None, snap=None), population("missing", "unknown")],
        [edge()],
        [facility()],
    )
    assert result["totals"]["unconnected_population"] == 200
    assert {row["snap_status"] for row in result["node_results"]} == {
        "unconnected_missing_snap",
        "unconnected_node_not_in_graph",
    }
    empty = calculate_total_access([], [], [])
    assert empty["areas"] == []
    assert empty["totals"]["total_population"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"closed_edge_ids": ["unknown"]},
        {"closed_edge_ids": ["ab", "ab"]},
        {"removed_facility_ids": ["unknown"]},
        {"closed_edge_ids": "ab"},
        {"added_facilities": [facility()]},
        {"unknown": True},
    ],
)
def test_scenario_rejects_unbound_or_ambiguous_changes(change):
    with pytest.raises(EvidenceScenarioError):
        calculate_total_access([population()], [edge()], [facility()], scenario=change)


@pytest.mark.parametrize("invalid", [-1, math.nan, math.inf, True, "bad"])
def test_nonfinite_or_negative_numeric_inputs_fail(invalid):
    with pytest.raises(EvidenceScenarioError):
        calculate_total_access([population(demand=invalid)], [edge()], [facility()])
    with pytest.raises(EvidenceScenarioError):
        calculate_total_access([population()], [edge(minutes=invalid)], [facility()])
    with pytest.raises(EvidenceScenarioError):
        allocate_shelter_capacity(
            [population()], [facility(capacity=invalid)], [pair()]
        )


def test_missing_snap_and_duplicate_ids_are_not_silently_accepted():
    no_snap = population()
    no_snap.pop("snap_distance_m")
    with pytest.raises(EvidenceScenarioError, match="explicit"):
        calculate_total_access([no_snap], [edge()], [facility()])
    with pytest.raises(EvidenceScenarioError, match="duplicate"):
        calculate_total_access([population(), population()], [edge()], [facility()])
    with pytest.raises(EvidenceScenarioError, match="duplicate"):
        calculate_total_access([population()], [edge(), edge()], [facility()])


def test_capacity_flow_handles_competing_demand_and_is_deterministic():
    # Greedily assigning p1 to s1 can strand p2. Maximum flow serves both.
    pops = [population("p1", demand=6), population("p2", demand=6)]
    sites = [facility("s1", capacity=6), facility("s2", capacity=6)]
    pairs = [pair("p1", "s1"), pair("p1", "s2"), pair("p2", "s1")]
    result = allocate_shelter_capacity(pops, sites, pairs)
    assert result["served_population"] == 12
    assert result["unserved_population"] == 0
    assert result["allocations"] == [
        {
            "population_id": "p1",
            "facility_id": "s2",
            "allocated_population": 6,
            "travel_minutes": 10,
        },
        {
            "population_id": "p2",
            "facility_id": "s1",
            "allocated_population": 6,
            "travel_minutes": 10,
        },
    ]
    assert allocate_shelter_capacity(pops[::-1], sites[::-1], pairs[::-1]) == result


def test_unknown_capacity_differs_from_zero_and_unreachable_demand():
    pops = [population(), population("unreachable", demand=25)]
    sites = [
        facility("unknown"),
        facility("zero", capacity=0),
        facility("known", capacity=30),
    ]
    pairs = [pair(site=site) for site in ("unknown", "zero", "known")]
    result = allocate_shelter_capacity(pops, sites, pairs)
    assert result["served_population"] == 30
    assert result["unserved_population"] == 95
    assert result["unknown_capacity_facility_ids"] == ["unknown"]
    assert result["calculation_status"] == "incomplete_unknown_capacity"
    assert result["unmet_population_with_unknown_capacity"] == 70
    assert result["unreachable_population"] == 25
    rows = {row["facility_id"]: row for row in result["facility_results"]}
    assert rows["unknown"]["capacity"] is None
    assert rows["unknown"]["remaining_capacity"] is None
    assert rows["zero"]["capacity"] == 0
    assert rows["zero"]["capacity_status"] == "known"
    assert (
        result["population_results"][1]["reachable_unknown_capacity_facilities"] == []
    )


def test_fractional_demand_conservation_threshold_and_duplicate_pairs():
    result = allocate_shelter_capacity(
        [population(demand=0.75)],
        [facility(capacity=0.4)],
        [pair(minutes=31), pair(minutes=30)],
    )
    assert result["served_population"] == pytest.approx(0.4)
    assert result["unserved_population"] == pytest.approx(0.35)
    assert sum(
        row["allocated_population"] for row in result["allocations"]
    ) == pytest.approx(0.4)
    excluded = allocate_shelter_capacity(
        [population()], [facility(capacity=100)], [pair(minutes=30.001)]
    )
    assert excluded["served_population"] == 0
    assert allocate_shelter_capacity([], [], [])["served_population"] == 0
    with pytest.raises(EvidenceScenarioError, match="unknown"):
        allocate_shelter_capacity(
            [population()], [facility(capacity=100)], [pair(person="unknown")]
        )


def test_missing_fpps_is_null_with_unchanged_weights_and_explicit_completions():
    result = evidence_assessment(
        {"flood_likelihood_0_100": 50, "exposure_0_100": 0}, area_id="area"
    )
    assert result["assessment_status"] == "incomplete"
    assert result["fpps_0_100"] is None
    assert result["action_class"] is None
    assert result["components"]["exposure_0_100"] == 0
    assert result["fixed_weight_bounds"] == {
        "lower": 15.0,
        "upper": 60.0,
        "meaning": "arithmetic_bounds_not_confidence_interval",
    }
    assert [row["fpps_0_100"] for row in result["scenario_completions"]] == [
        15,
        37.5,
        60,
    ]
    assert {row["action_class"] for row in result["scenario_completions"]} == {"E"}
    assert {row["action_reason_code"] for row in result["scenario_completions"]} == {
        "low_confidence"
    }
    assert result["weights"]["flood_likelihood_0_100"] == 0.30


def test_complete_score_preserves_existing_high_priority_and_low_confidence_rules():
    values = dict.fromkeys(SCORE_COMPONENTS, 100)
    low = evidence_assessment(values, area_id="area")
    assert low["fpps_0_100"] == 100
    assert low["action_class"] == "E"
    assert low["action_reason_code"] == "low_confidence"
    high = evidence_assessment(values, area_id="area", confidence_class="high")
    assert high["action_class"] == "A"
    assert (
        high["fixed_weight_bounds"]["lower"]
        == high["fixed_weight_bounds"]["upper"]
        == 100
    )
    assert high["scenario_completions"] == []
    for value in (101, -1, math.inf, math.nan, False):
        with pytest.raises(EvidenceScenarioError):
            evidence_assessment({"exposure_0_100": value}, area_id="area")


def test_illustrative_fallback_is_explicitly_synthetic_and_json_safe():
    result = build_illustrative_scenarios("aoi-01", [99.9, 20.3, 100, 20.4])
    assert result["synthetic"] is True
    assert "not an AOI access result" in result["title"]
    assert result["source_timestamp"] is None
    assert all(
        feature["properties"]["synthetic"]
        for feature in result["map_geojson"]["features"]
    )
    assert (
        result["access_scenarios"]["close_edge"]["totals"][
            "people_losing_30_min_access"
        ]
        == 100
    )
    assert [row["served_population"] for row in result["capacity_scenarios"]] == [
        50,
        100,
        100,
    ]
    assert result["assessment"]["fpps_0_100"] is None
    json.dumps(result, allow_nan=False)


def test_capacity_demand_partitions_are_disjoint_and_conserve_total():
    pops = [
        population("known", demand=10),
        population("uncertain", demand=8),
        population("unreachable", demand=7),
        population("excluded", node=None, snap=None, demand=6),
    ]
    result = allocate_shelter_capacity(
        pops,
        [facility("known-site", capacity=4), facility("unknown-site")],
        [pair("known", "known-site"), pair("uncertain", "unknown-site")],
    )
    assert result["served_population"] == 4
    assert result["capacity_limited_unmet_population"] == 6
    assert result["unmet_population_with_unknown_capacity"] == 8
    assert result["unreachable_population"] == 7
    assert result["excluded_coverage_population"] == 6
    assert result["total_population"] == 31
    with pytest.raises(EvidenceScenarioError, match="excluded connector"):
        allocate_shelter_capacity(pops, [facility(capacity=10)], [pair("excluded")])


@pytest.mark.parametrize(
    "change,expected_calls",
    [
        (None, [("s",)]),
        ({"removed_facility_ids": ["s"]}, [("s",)]),
        ({"added_facilities": [facility("new", node="a")]}, [("s",), ("new",)]),
        (
            {
                "removed_facility_ids": ["s"],
                "added_facilities": [facility("new", node="a")],
            },
            [("s",), ("new",)],
        ),
        ({"closed_edge_ids": ["ab"]}, [("s",), ("s",)]),
    ],
)
def test_destination_changes_reuse_unchanged_paths_without_changing_results(
    monkeypatch, change, expected_calls
):
    import floodguard.evidence_scenarios as module

    original = module._reachable_pairs
    calls = []

    def traced(pops, sites, graph):
        calls.append(tuple(row["facility_id"] for row in sites))
        return original(pops, sites, graph)

    monkeypatch.setattr(module, "_reachable_pairs", traced)
    pops, sites, roads = [population(snap=25)], [facility(snap=50)], [edge()]
    result = calculate_total_access(pops, roads, sites, scenario=change)
    assert calls == expected_calls
    selected = change or {}
    graph, _ = module._graph(roads)
    changed_graph, _ = module._graph(
        [
            row
            for row in roads
            if row["edge_id"] not in selected.get("closed_edge_ids", [])
        ]
    )
    for node in graph:
        changed_graph.setdefault(node, [])
    remaining = [
        row
        for row in sites
        if row["facility_id"] not in selected.get("removed_facility_ids", [])
    ]
    remaining += selected.get("added_facilities", [])
    assert result["baseline_reachable_pairs"] == original(pops, sites, graph)
    assert result["scenario_reachable_pairs"] == original(
        pops, remaining, changed_graph
    )
