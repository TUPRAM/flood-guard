"""Small explicit graphs test intervention relevance without observed claims."""

from copy import deepcopy

import pytest

from floodguard import evidence_scenarios as scenarios
from floodguard.evidence_interventions import (
    intervention_effect_summary,
    select_interventions,
)


def pop(key, node, value, snap=0):
    return {
        "population_id": key,
        "node_id": node,
        "total_population": value,
        "subdistrict_id": "area",
        "snap_distance_m": snap,
    }


def edge(key, a, b, time):
    return {"edge_id": key, "from_node": a, "to_node": b, "normal_minutes": time}


def site(key, node):
    return {"facility_id": key, "node_id": node, "snap_distance_m": 0}


def test_selection_uses_routes_and_underserved_demand_instead_of_first_id():
    population = [pop("large-served", "a", 100), pop("small-unserved", "e", 20)]
    roads = [edge("ab", "a", "b", 5), edge("ac", "a", "c", 20), edge("ef", "e", "f", 3)]
    sites = [site("z-used", "b"), site("a-unused", "c")]
    baseline = scenarios.calculate_total_access(population, roads, sites)
    selected = select_interventions(population, roads, sites, baseline)
    assert selected["closed_edge_id"] == "ab"
    assert selected["removed_facility_id"] == "z-used"
    assert selected["hypothetical_added_node"] == "e"
    assert selected["hypothetical_capacity_node"] == "a"
    assert selected["candidates"]["close_edge"][0]["baseline_route_population"] == 100
    assert selected["bounds"]["outcome_evaluations_per_family"] == 1
    reversed_result = scenarios.calculate_total_access(
        population[::-1], roads[::-1], sites[::-1]
    )
    assert (
        select_interventions(
            population[::-1], roads[::-1], sites[::-1], reversed_result
        )
        == selected
    )


def test_coverage_groups_conserve_mass_and_time_deltas_do_not_impute_missing():
    population = [
        pop("served", "a", 100),
        pop("no-route", "e", 20),
        pop("missing", None, 7, None),
    ]
    roads = [edge("ab", "a", "b", 5), edge("ac", "a", "c", 7), edge("ef", "e", "f", 2)]
    result = scenarios.calculate_total_access(
        population,
        roads,
        [site("b", "b"), site("c", "c")],
        scenario={"removed_facility_ids": ["b"]},
    )
    coverage = result["coverage_review"]
    for phase in ("baseline", "scenario"):
        for threshold in ("15", "30", "60"):
            assert (
                coverage["missing_graph_coverage_population"]
                + coverage[phase]["graph_connected_no_modelled_route_population"]
                + sum(coverage[phase]["thresholds"][threshold].values())
                == 127
            )
    assert coverage["missing_graph_coverage_population"] == 7
    assert coverage["baseline"]["graph_connected_no_modelled_route_population"] == 20
    summary = result["travel_time_summary"]
    assert summary["comparison_population"] == 100
    assert summary["baseline_population_weighted_mean_minutes"] == 5
    assert summary["scenario_population_weighted_mean_minutes"] == 7
    assert summary["population_weighted_mean_delta_minutes"] == 2
    assert summary["additional_person_minutes"] == 200
    effect = intervention_effect_summary({"remove_destination": result})[
        "remove_destination"
    ]
    assert effect["threshold_change"] is False and effect["travel_time_change"] is True
    assert all(
        row["travel_time_delta_minutes"] is None
        for row in result["node_results"]
        if row["population_id"] != "served"
    )


def test_equivalent_alternative_is_reported_as_zero_without_reselecting():
    population = [pop("p", "a", 10)]
    roads = [
        edge("ab", "a", "b", 1),
        edge("ac", "a", "c", 0.5),
        edge("cb", "c", "b", 0.5),
    ]
    baseline = scenarios.calculate_total_access(population, roads, [site("s", "b")])
    selected = select_interventions(population, roads, [site("s", "b")], baseline)
    result = scenarios.calculate_total_access(
        population,
        roads,
        [site("s", "b")],
        scenario={"closed_edge_ids": [selected["closed_edge_id"]]},
        baseline_result=baseline,
    )
    effect = intervention_effect_summary({"close_edge": result})["close_edge"]
    assert not effect["threshold_change"] and not effect["travel_time_change"]
    assert "equivalent alternative" in effect["explanation"]


def test_route_loss_and_restoration_are_not_finite_delta_zero():
    population = [pop("p", "a", 10)]
    roads = [edge("ab", "a", "b", 5)]
    result = scenarios.calculate_total_access(
        population, roads, [site("s", "b")], scenario={"closed_edge_ids": ["ab"]}
    )
    assert result["travel_time_summary"]["comparison_population"] == 0
    assert (
        result["travel_time_summary"]["population_weighted_mean_delta_minutes"] is None
    )
    assert (
        result["travel_time_summary"]["newly_without_modelled_route_population"] == 10
    )
    restored = scenarios.calculate_total_access(
        population, roads, [], scenario={"added_facilities": [site("new", "a")]}
    )
    assert restored["travel_time_summary"]["newly_with_modelled_route_population"] == 10


def test_reuse_baseline_avoids_recomputing_pairs_and_rejects_stale_inputs(monkeypatch):
    population = [pop("p", "a", 10)]
    roads = [edge("ab", "a", "b", 5)]
    sites = [site("s", "b")]
    baseline = scenarios.calculate_total_access(population, roads, sites)
    original = deepcopy(baseline)
    monkeypatch.setattr(
        scenarios,
        "_reachable_pairs",
        lambda *args: pytest.fail("baseline shortest paths were recomputed"),
    )
    result = scenarios.calculate_total_access(
        population,
        roads,
        sites,
        scenario={"removed_facility_ids": ["s"]},
        baseline_result=baseline,
    )
    assert result["totals"]["people_losing_30_min_access"] == 10
    assert baseline == original
    with pytest.raises(scenarios.EvidenceScenarioError, match="does not match"):
        scenarios.calculate_total_access(
            [pop("p", "a", 11)], roads, sites, baseline_result=baseline
        )


def test_zero_length_routes_cycles_and_no_graph_have_deterministic_selection():
    population = [pop("p", "a", 10)]
    roads = [edge("ab", "a", "b", 0), edge("bc", "b", "c", 0), edge("ca", "c", "a", 0)]
    sites = [site("s", "b")]
    baseline = scenarios.calculate_total_access(population, roads, sites)
    assert select_interventions(
        population, roads, sites, baseline
    ) == select_interventions(population, roads[::-1], sites, baseline)
    empty = scenarios.calculate_total_access([], [], [])
    assert select_interventions([], [], [], empty)["closed_edge_id"] is None
    zero_population = [pop("zero", "a", 0)]
    zero = scenarios.calculate_total_access(zero_population, roads, sites)
    assert (
        select_interventions(zero_population, roads, sites, zero)[
            "hypothetical_added_node"
        ]
        is None
    )
