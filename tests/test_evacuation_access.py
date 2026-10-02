"""Tests for stage-dependent evacuation access, greedy shelter ranking and the capacity-aware plan."""

from __future__ import annotations

import math

import numpy as np
import pytest

from floodguard.evacuation_access import (
    CAPACITY_BASES,
    NEVER_LOST,
    NO_BASELINE_ACCESS,
    PEOPLE_UNIT,
    capacitated_assignment,
    capacitated_plan,
    capacity_bounds,
    closure_stage,
    cutoff_levels,
    greedy_plan,
    knee_index,
    reachable_within,
    robust_core,
)


def line_graph():
    # 0 - 1 - 2 - 3, 10 minutes per edge; 4 is isolated.
    u = np.array([0, 1, 2])
    v = np.array([1, 2, 3])
    minutes = np.array([10.0, 10.0, 10.0])
    return u, v, minutes


def test_closure_stage_scales_with_depth_factor() -> None:
    assert closure_stage(1.0, 1.0) == pytest.approx(1.3)
    assert closure_stage(1.0, 0.5) == pytest.approx(1.6)  # Tributary water rises half as much.
    assert math.isinf(closure_stage(None, 1.0))
    assert math.isinf(closure_stage(1.0, 0.0))


def test_reachable_respects_threshold_and_closed_edges() -> None:
    u, v, minutes = line_graph()
    open_all = np.array([True, True, True])
    assert reachable_within(5, u, v, minutes, open_all, [0], 20).tolist() == [True, True, True, False, False]
    assert reachable_within(5, u, v, minutes, np.array([True, False, True]), [0], 60).tolist() == [True, True, False, False, False]
    assert not reachable_within(5, u, v, minutes, open_all, [], 60).any()


def test_cutoff_levels_codes() -> None:
    u, v, minutes = line_graph()
    close = np.array([math.inf, 1.0, math.inf])  # Middle edge closes at stage 1.0.
    codes = cutoff_levels(5, u, v, minutes, close, [0], [5.0], [0.0, 0.5, 1.0, 1.5], 60)
    assert codes[0] == NEVER_LOST and codes[1] == NEVER_LOST
    assert codes[2] == 2 and codes[3] == 2  # Lost at levels[2] = 1.0.
    assert codes[4] == NO_BASELINE_ACCESS


def test_flooded_shelter_stops_serving() -> None:
    u, v, minutes = line_graph()
    close = np.full(3, math.inf)
    codes = cutoff_levels(4, u, v, minutes, close, [0, 3], [0.5, 9.0], [0.0, 0.5, 1.0], 15)
    # Shelter 0 floods at 0.5; node 1 was served by it (10 min) but is 20 min from shelter 3.
    assert codes[1] == 1
    assert codes[2] == NEVER_LOST and codes[3] == NEVER_LOST


def test_greedy_plan_is_nested_and_knee() -> None:
    demand = np.array([100.0, 50.0, 30.0, 5.0])
    coverage = [np.array([1, 0, 0, 0], bool), np.array([1, 1, 0, 0], bool), np.array([0, 0, 1, 1], bool)]
    ranking = greedy_plan(demand, coverage, max_sites=5, min_gain_share=0.0)
    assert [r["candidate"] for r in ranking] == [1, 2]  # Site 0 adds nothing once site 1 is chosen.
    assert ranking[-1]["cumulative_share"] == pytest.approx(1.0)
    assert knee_index(ranking, 0.8) == 1
    assert knee_index([], 0.9) is None


def test_cutoff_levels_for_sets_matches_single_set() -> None:
    from floodguard.evacuation_access import cutoff_levels_for_sets

    u, v, minutes = line_graph()
    close = np.array([math.inf, 1.0, 0.6])
    levels = [0.0, 0.5, 1.0, 1.5]
    sets = [([0], [5.0]), ([0, 3], [0.5, 9.0])]
    multi = cutoff_levels_for_sets(5, u, v, minutes, close, sets, levels, 60)
    for index, (nodes, flood) in enumerate(sets):
        assert multi[index].tolist() == cutoff_levels(5, u, v, minutes, close, nodes, flood, levels, 60).tolist()


# --- Capacity-aware plan ---------------------------------------------------------------------------------
#
# The plan assigns residents to sites they can walk to without loading a site beyond its capacity. Every figure is a
# T1 scenario on a modelled flood: no score and no action class comes out of it.


def random_case(seed: int, n_nodes: int = 14, n_sites: int = 7) -> tuple[np.ndarray, list[np.ndarray], np.ndarray, np.ndarray]:
    """Random demand (thousandths of a resident), reach masks and two capacity bounds (unknown = 0 in the lower one)."""
    rng = np.random.default_rng(seed)
    demand = np.round(rng.uniform(0.0, 40.0, n_nodes), 3)
    demand[rng.random(n_nodes) < 0.15] = 0.0
    reach = [rng.random(n_nodes) < 0.35 for _ in range(n_sites)]
    upper = rng.integers(0, 60, n_sites).astype(float)
    lower = np.where(rng.random(n_sites) < 0.4, 0.0, upper)
    return demand, reach, lower, upper


def units(value: float) -> int:
    return int(round(value / PEOPLE_UNIT))


def network_flow(demand: np.ndarray, reach: list[np.ndarray], capacity: np.ndarray, sites: list[int]) -> tuple[int, dict]:
    """Independent check with networkx: a min-cost maximum flow, in thousandths of a resident."""
    networkx = pytest.importorskip("networkx")
    graph = networkx.DiGraph()
    graph.add_node("source")
    graph.add_node("sink")
    for site in sites:
        graph.add_edge("source", ("site", site), capacity=units(capacity[site]), weight=0)
        for node in np.flatnonzero(reach[site]):
            # Any cost works for the size of the flow; a distance-like cost makes it a real min-cost problem.
            graph.add_edge(("site", site), ("node", int(node)), capacity=units(demand[node]), weight=1 + (site * 7 + int(node) * 3) % 5)
    for node in range(demand.size):
        graph.add_edge(("node", node), "sink", capacity=units(demand[node]), weight=0)
    flow = networkx.max_flow_min_cost(graph, "source", "sink")
    return sum(flow["source"].values()), flow


def test_capacity_bounds_use_zero_and_the_kind_median_for_an_unknown_capacity() -> None:
    capacities = [100, None, 40, 80, None, 30, None, 10]
    kinds = ["school", "school", "worship", "worship", "worship", "worship", "community", "school"]
    lower, upper, basis = capacity_bounds(capacities, kinds)
    assert lower.tolist() == [100, 0, 40, 80, 0, 30, 0, 10]
    # School median of (100, 10) = 55; worship median of (40, 80, 30) = 40. No community site has an estimate, so
    # it takes the median of all five known values (10, 30, 40, 80, 100) = 40.
    assert upper.tolist() == [100, 55, 40, 80, 40, 30, 40, 10]
    assert basis == ["estimate", "kind_median", "estimate", "estimate", "kind_median", "estimate", "all_kinds_median", "estimate"]
    assert set(basis) <= set(CAPACITY_BASES)
    assert (lower <= upper).all()
    # A median between two values is rounded down: places are whole people.
    assert capacity_bounds([3, 6, None], ["a", "a", "a"])[1].tolist() == [3, 6, 4]
    # Nothing known at all: the upper bound has nothing to go on either.
    nothing = capacity_bounds([None, None], ["a", "b"])
    assert nothing[0].tolist() == [0, 0] and nothing[1].tolist() == [0, 0] and nothing[2] == ["none", "none"]
    with pytest.raises(ValueError, match="same length"):
        capacity_bounds([1], ["a", "b"])
    with pytest.raises(ValueError, match="not negative"):
        capacity_bounds([-1], ["a"])


def test_assignment_serves_everyone_in_reach_until_the_site_is_full() -> None:
    demand = np.array([100.0, 50.0, 30.0, 20.0])
    reach = [np.array([1, 1, 0, 0], bool), np.array([0, 1, 1, 0], bool)]
    result = capacitated_assignment(demand, reach, [120.0, 60.0])
    # Site 0 is full at 120; site 1 takes the 30 only it can reach and 30 of the shared node; node 3 has no site.
    assert (result["demand"], result["served"], result["overflow"]) == (200.0, 180.0, 20.0)
    assert result["loads"] == [120.0, 60.0]
    assert all(reach[site][node] for site, node, _ in result["flows"])
    assert sum(people for _, _, people in result["flows"]) == pytest.approx(180.0)
    # A site carrying 2,430 residents on the nearest-site rule holds only what its capacity allows.
    crowded = capacitated_assignment(np.array([2430.0]), [np.array([True])], [79.0])
    assert (crowded["served"], crowded["overflow"], crowded["loads"]) == (79.0, 2351.0, [79.0])
    # No site, no capacity or nobody in reach: nobody is served and the whole demand overflows.
    assert capacitated_assignment(demand, [], [])["overflow"] == 200.0
    assert capacitated_assignment(demand, reach, [0.0, 0.0])["served"] == 0.0
    assert capacitated_assignment(demand, [np.zeros(4, bool)], [500.0])["served"] == 0.0


@pytest.mark.parametrize("seed", range(12))
def test_assignment_matches_a_min_cost_flow_and_never_exceeds_capacity_or_demand(seed: int) -> None:
    demand, reach, _, capacity = random_case(seed)
    result = capacitated_assignment(demand, reach, capacity)
    expected, flow = network_flow(demand, reach, capacity, list(range(len(reach))))
    assert units(result["served"]) == expected  # The size of the assignment is the maximum a min-cost flow reaches.
    assert result["overflow"] == pytest.approx(result["demand"] - result["served"], abs=1e-9)
    assert units(result["demand"]) == sum(units(value) for value in demand)
    per_site = np.zeros(len(reach))
    per_node = np.zeros(demand.size)
    for site, node, people in result["flows"]:
        assert reach[site][node] and people > 0  # Only within the walking limit.
        per_site[site] += people
        per_node[node] += people
    assert (per_site <= capacity + 1e-9).all()  # Load never exceeds capacity.
    assert (per_node <= demand + 1e-9).all()  # Nobody is assigned twice.
    assert per_site.tolist() == pytest.approx(result["loads"])
    # networkx respects the same limits, so the two solutions are comparable.
    assert all(sum(flow[("site", site)].values()) <= units(capacity[site]) for site in range(len(reach)))


@pytest.mark.parametrize("seed", range(12))
def test_capacitated_plan_keeps_its_invariants_under_both_bounds(seed: int) -> None:
    demand, reach, lower, upper = random_case(seed)
    plan = capacitated_plan(demand, reach, lower, upper, max_sites=len(reach))
    ranking = plan["ranking"]
    assert ranking and len({entry["candidate"] for entry in ranking}) == len(ranking)
    total = plan["demand"]
    order = [entry["candidate"] for entry in ranking]
    for position, entry in enumerate(ranking, start=1):
        for key, capacity in (("lower", lower), ("upper", upper)):
            bound = entry[key]
            assert bound["capacity"] == capacity[entry["candidate"]]
            assert 0 <= bound["load"] <= bound["capacity"]  # Load never exceeds capacity.
            assert bound["overflow"] == pytest.approx(total - bound["served"], abs=1e-9)  # overflow = demand - served.
            assert bound["served"] == pytest.approx(sum(row[key]["load"] for row in ranking[:position]), abs=1e-9)
            # The running total is what a min-cost maximum flow over the first k sites reaches.
            assert units(bound["served"]) == network_flow(demand, reach, capacity, order[:position])[0]
        assert entry["lower"]["served"] <= entry["upper"]["served"]  # Lower bound <= upper bound.
        assert entry["upper"]["served"] <= entry["within_reach"] + 1e-9 <= total + 1e-9
    # The loads are one valid assignment for every plan size: sites capped at their loads can carry them all.
    for key in ("lower", "upper"):
        loads = np.zeros(len(reach))
        for entry in ranking:
            loads[entry["candidate"]] = entry[key]["load"]
        assert capacitated_assignment(demand, reach, loads)["served"] == pytest.approx(loads.sum(), abs=1e-9)


@pytest.mark.parametrize("seed", range(12))
def test_capacitated_plan_is_nested_greedy_and_deterministic(seed: int) -> None:
    demand, reach, lower, upper = random_case(seed)
    full = capacitated_plan(demand, reach, lower, upper, max_sites=len(reach))
    assert capacitated_plan(demand, reach, lower, upper, max_sites=len(reach)) == full  # Same input, same plan.
    for size in range(1, len(full["ranking"]) + 1):
        # The plan for k sites is the first k entries of the plan for k + 1.
        assert capacitated_plan(demand, reach, lower, upper, max_sites=size)["ranking"] == full["ranking"][:size]
    # Each step takes the site with the largest gain in residents served under the upper bound (brute force).
    chosen: list[int] = []
    served = 0
    for entry in full["ranking"]:
        gains = {}
        for site in range(len(reach)):
            if site in chosen:
                continue
            mask = np.zeros(len(reach), bool)
            mask[[*chosen, site]] = True
            gains[site] = units(capacitated_assignment(demand, reach, np.where(mask, upper, 0.0))["served"]) - served
        best = max(gains.values())
        assert gains[entry["candidate"]] == best == units(entry["upper"]["load"])
        chosen.append(entry["candidate"])
        served += best
    # Ranking stops only when no remaining site adds anybody.
    rest = [site for site in range(len(reach)) if site not in chosen]
    everything = units(capacitated_assignment(demand, reach, upper)["served"])
    assert served == everything or not rest


def test_capacitated_plan_breaks_ties_by_the_lower_bound_then_by_index() -> None:
    demand = np.array([50.0, 50.0, 50.0])
    reach = [np.array([1, 0, 0], bool), np.array([0, 1, 0], bool), np.array([0, 0, 1], bool)]
    # All three add 40 under the upper bound; site 1 and 2 have a known capacity, site 0 does not.
    plan = capacitated_plan(demand, reach, [0.0, 40.0, 40.0], [40.0, 40.0, 40.0], max_sites=3)
    assert [entry["candidate"] for entry in plan["ranking"]] == [1, 2, 0]
    assert [entry["lower"]["served"] for entry in plan["ranking"]] == [40.0, 80.0, 80.0]
    assert [entry["upper"]["served"] for entry in plan["ranking"]] == [40.0, 80.0, 120.0]
    assert [entry["upper"]["overflow"] for entry in plan["ranking"]] == [110.0, 70.0, 30.0]


def test_capacitated_plan_stops_at_the_gain_floor_and_counts_a_given_order() -> None:
    demand = np.array([100.0, 50.0, 30.0, 20.0])
    reach = [np.array([1, 1, 0, 0], bool), np.array([0, 1, 1, 0], bool), np.array([0, 0, 0, 1], bool)]
    capacity = [120.0, 60.0, 1.0]
    plan = capacitated_plan(demand, reach, capacity, capacity, max_sites=3)
    assert [entry["candidate"] for entry in plan["ranking"]] == [0, 1, 2]
    assert [entry["upper"]["load"] for entry in plan["ranking"]] == [120.0, 60.0, 1.0]
    assert [entry["within_reach"] for entry in plan["ranking"]] == [150.0, 180.0, 200.0]
    # A site must add at least 1 % of the 200 residents: the one-place site is not ranked.
    assert len(capacitated_plan(demand, reach, capacity, capacity, max_sites=3, min_gain_share=0.01)["ranking"]) == 2
    # A given order is counted as it stands (to see what an existing ranking can hold), even a site that adds nobody.
    given = capacitated_plan(demand, reach, [120.0, 0.0, 1.0], capacity, max_sites=3, order=[2, 1, 0])
    assert [entry["candidate"] for entry in given["ranking"]] == [2, 1, 0]
    assert [entry["upper"]["load"] for entry in given["ranking"]] == [1.0, 60.0, 120.0]
    assert [entry["lower"]["load"] for entry in given["ranking"]] == [1.0, 0.0, 120.0]
    assert given["ranking"][-1]["upper"]["served"] == plan["ranking"][-1]["upper"]["served"] == 181.0
    with pytest.raises(ValueError, match="at most once"):
        capacitated_plan(demand, reach, capacity, capacity, max_sites=3, order=[0, 0])


def test_capacitated_plan_refuses_inputs_it_cannot_count() -> None:
    demand = np.array([10.0, 5.0])
    reach = [np.array([1, 1], bool)]
    with pytest.raises(ValueError, match="lower capacity bound exceeds"):
        capacitated_plan(demand, reach, [9.0], [8.0], max_sites=1)
    with pytest.raises(ValueError, match="one value per candidate"):
        capacitated_plan(demand, reach, [9.0, 1.0], [9.0, 1.0], max_sites=1)
    with pytest.raises(ValueError, match="one entry per demand node"):
        capacitated_plan(demand, [np.array([1, 1, 1], bool)], [9.0], [9.0], max_sites=1)
    with pytest.raises(ValueError, match="not negative"):
        capacitated_plan(np.array([-1.0, 5.0]), reach, [9.0], [9.0], max_sites=1)
    with pytest.raises(ValueError, match="too large"):
        capacitated_plan(np.array([3e6, 5.0]), reach, [9.0], [9.0], max_sites=1)
    empty = capacitated_plan(demand, [], [], [], max_sites=3)
    assert empty == {"demand": 15.0, "ranking": []}


def test_capacity_aware_results_carry_no_score_and_no_action_class() -> None:
    demand, reach, lower, upper = random_case(3)
    plan = capacitated_plan(demand, reach, lower, upper, max_sites=3)
    keys = set(plan) | {key for entry in plan["ranking"] for key in (*entry, *entry["lower"], *entry["upper"])}
    assert not any(word in key for key in keys for word in ("fpps", "action", "score", "class"))


def test_robust_core_keeps_the_sites_chosen_at_every_what_if_level() -> None:
    peak = ["C049", "C007", "C107", "C084"]
    lower = ["C025", "C049", "C107", "C011"]
    higher = ["C049", "C007", "C084"]
    assert robust_core([peak, lower, higher], 1) == []
    assert robust_core([peak, lower, higher], 2) == ["C049"]
    assert robust_core([peak, lower, higher], 4) == ["C049"]  # A ranking shorter than k counts in full.
    assert robust_core([peak, lower], 4) == ["C049", "C107"]  # In the order of the first ranking.
    assert robust_core([peak], 3) == peak[:3]
    assert robust_core([], 3) == [] and robust_core([peak, lower], 0) == []
    # The core for k sites is never larger than k, and it only grows with k when every ranking is long enough.
    assert all(len(robust_core([peak, lower], k)) <= k for k in range(1, 6))
