"""Tests for stage-dependent evacuation access and greedy shelter ranking."""

from __future__ import annotations

import math

import numpy as np
import pytest

from floodguard.evacuation_access import (
    NEVER_LOST,
    NO_BASELINE_ACCESS,
    closure_stage,
    cutoff_levels,
    greedy_plan,
    knee_index,
    reachable_within,
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
