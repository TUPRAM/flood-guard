"""Side-by-side access figures of shelter sets (``floodguard.shelter_set_comparison``).

Synthetic nodes only: eight resident nodes, two shelter sets and a short stage curve. The figures are a T1
scenario; the cut-off hour comes from illustrative stage keyframes, not observed.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import shelter_set_comparison as module
from floodguard.evacuation_access import NEVER_LOST, NO_BASELINE_ACCESS
from floodguard.shelter_set_comparison import (
    CUTOFF_COVERAGE_SHARE,
    CUTOFF_NO_BASELINE,
    CUTOFF_NOT_REACHED,
    CUTOFF_REACHED,
    ShelterSetComparisonError,
    ShelterSetSummary,
    access_cutoff_hour,
    level_index,
    lost_access,
    shelter_set_summary,
)

ROOT = Path(__file__).resolve().parents[1]

# Eight resident nodes. Cut codes are level indices at 0.05 m steps: 2 = lost from 0.10 m, 10 = from 0.50 m,
# 40 = from 2.00 m; 254 never loses access; 255 has no shelter of the set within reach before the flood.
POPULATION = np.array([100.0, 200.0, 50.0, 400.0, 30.0, 20.0, 150.0, 50.0])
VULNERABLE = np.array([0.0, 20.0, 50.0, 0.0, 30.0, 0.0, 0.0, 10.0])
SET_A = np.array([2, 10, 40, NEVER_LOST, NO_BASELINE_ACCESS, NO_BASELINE_ACCESS, 10, NEVER_LOST], dtype=np.uint8)
SET_B = np.array([NO_BASELINE_ACCESS, 2, 2, NO_BASELINE_ACCESS, 10, NEVER_LOST, NO_BASELINE_ACCESS, NO_BASELINE_ACCESS], dtype=np.uint8)
WET_HOMES = np.array([True, True, False, False, True, True, False, False])
# Hourly stages: dry, rising to a 2.5 m peak at hour 5, then falling.
STAGES = [0.0, 0.0, 0.1, 0.5, 2.0, 2.5, 1.0, 0.3, 0.05, 0.0]


def summary(codes: np.ndarray, stage: float, **kwargs) -> ShelterSetSummary:
    return shelter_set_summary(POPULATION, codes, stage, STAGES, vulnerable_population=VULNERABLE, **kwargs)


# --- Level index and lost access ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "index"),
    [(0.0, 0), (0.049, 0), (0.05, 1), (0.1, 2), (0.15, 3), (0.35, 7), (3.5, 70), (4.05, 81)],
)
def test_level_index_floors_the_stage_with_a_small_tolerance(stage: float, index: int) -> None:
    assert level_index(stage) == index


def test_lost_access_never_counts_codes_254_and_255() -> None:
    codes = np.array([1, 2, 70, 71, NEVER_LOST, NO_BASELINE_ACCESS], dtype=np.uint8)
    assert lost_access(codes, 0.0).tolist() == [False] * 6
    assert lost_access(codes, 0.1).tolist() == [True, True, False, False, False, False]
    assert lost_access(codes, 3.5).tolist() == [True, True, True, False, False, False]
    assert lost_access(codes, 99.0).tolist() == [True, True, True, True, False, False]


def test_lost_access_matches_the_bake_stage_node_by_node() -> None:
    pytest.importorskip("rasterio")  # The bake stage imports it.
    spec = importlib.util.spec_from_file_location("mae_sai_timeline_evacuation", ROOT / "scripts" / "mae_sai_timeline_evacuation.py")
    evac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evac)
    codes = np.arange(256, dtype=np.uint8)
    for stage in (0.0, 0.049, 0.05, 0.0999999, 0.1, 0.35, 1.0, 2.65, 3.5, 4.0, 4.05, 12.7):
        assert lost_access(codes, stage).tolist() == evac.lost_at(codes, stage).tolist(), stage
    assert module.LEVEL_STEP_M == 0.05 and evac.LEVELS[1] == 0.05


# --- The four figures ----------------------------------------------------------------------------------


def test_baseline_keeping_and_newly_lost_with_the_sets_own_denominator() -> None:
    before = summary(SET_A, 0.0)
    # Nodes 4 and 5 (50 residents) have no shelter of set A within reach before the flood.
    assert (before.residents, before.baseline, before.keeping, before.lost, before.lost_share) == (1000.0, 950.0, 950.0, 0.0, 0.0)
    at_half = summary(SET_A, 0.5)
    # Codes 2 and 10 are lost at 0.5 m: nodes 0, 1 and 6 (450 residents) out of the 950 with baseline access.
    assert (at_half.keeping, at_half.lost, at_half.lost_share) == (500.0, 450.0, 0.4737)
    peak = summary(SET_A, 2.5)
    assert (peak.keeping, peak.lost, peak.lost_share) == (450.0, 500.0, 0.5263)
    assert peak.keeping + peak.lost == peak.baseline
    # The share is of the baseline, never of all residents.
    assert peak.lost_share == round(500 / 950, 4) != round(500 / 1000, 4)


def test_a_mask_counts_only_the_chosen_residents() -> None:
    wet = summary(SET_A, 2.5, mask=WET_HOMES)
    # Wet homes: nodes 0, 1, 4, 5 (350 residents); nodes 0 and 1 (300) have baseline access and both lose it.
    assert (wet.residents, wet.baseline, wet.keeping, wet.lost, wet.lost_share) == (350.0, 300.0, 0.0, 300.0, 1.0)
    everyone = summary(SET_A, 2.5, mask=np.ones(8, dtype=bool))
    assert everyone == summary(SET_A, 2.5)


def test_proxy_vulnerable_residents_are_counted_within_the_baseline() -> None:
    peak = summary(SET_A, 2.5)
    # Baseline nodes 0, 1, 2, 3, 6, 7 hold 80 proxy-vulnerable residents; nodes 1 and 2 (70) have lost access.
    assert (peak.vulnerable_baseline, peak.vulnerable_lost) == (80.0, 70.0)
    assert shelter_set_summary(POPULATION, SET_A, 2.5, STAGES).vulnerable_baseline == 0.0


def test_two_sets_can_each_lead_on_one_way_of_counting_and_nothing_ranks_them() -> None:
    a_all, b_all = summary(SET_A, 2.5), summary(SET_B, 2.5)
    a_wet, b_wet = summary(SET_A, 2.5, mask=WET_HOMES), summary(SET_B, 2.5, mask=WET_HOMES)
    # Set A reaches more residents overall; set B keeps more of the residents whose homes flood.
    assert a_all.baseline > b_all.baseline
    assert b_wet.keeping > a_wet.keeping
    fields = {field.name for field in dataclasses.fields(ShelterSetSummary)}
    assert fields == {"residents", "baseline", "keeping", "lost", "lost_share", "vulnerable_baseline", "vulnerable_lost", "cutoff_status", "cutoff_hour"}
    assert not any(word in name for name in fields for word in ("rank", "score", "fpps", "class", "winner", "better"))


# --- The cut-off hour ----------------------------------------------------------------------------------


def test_cutoff_hour_is_the_first_hour_below_half_of_the_baseline() -> None:
    peak = summary(SET_A, 2.5)
    # Keeping by hour: 950, 950, 850, 500, 450, 450, ... Half of 950 is 475, first undercut at hour 4.
    assert (peak.cutoff_status, peak.cutoff_hour) == (CUTOFF_REACHED, 4)
    # The hour belongs to the whole replay, not to the stage the other figures are read at.
    assert (summary(SET_A, 0.0).cutoff_status, summary(SET_A, 0.0).cutoff_hour) == (CUTOFF_REACHED, 4)
    wet = summary(SET_A, 2.5, mask=WET_HOMES)
    # Wet homes with baseline access: 300; hour 2 keeps 200 (not below 150), hour 3 keeps 0.
    assert (wet.cutoff_status, wet.cutoff_hour) == (CUTOFF_REACHED, 3)


def test_cutoff_is_strictly_below_half_so_exactly_half_does_not_count() -> None:
    assert access_cutoff_hour(100, [100, 60, 50, 50]) == (CUTOFF_NOT_REACHED, None)
    assert access_cutoff_hour(100, [100, 60, 50, 49.999, 10]) == (CUTOFF_REACHED, 3)
    assert CUTOFF_COVERAGE_SHARE == 0.5


def test_cutoff_not_reached_and_no_baseline_are_reported_as_such() -> None:
    assert access_cutoff_hour(100, [100, 90, 80]) == (CUTOFF_NOT_REACHED, None)
    assert access_cutoff_hour(100, []) == (CUTOFF_NOT_REACHED, None)
    assert access_cutoff_hour(0, [0, 0]) == (CUTOFF_NO_BASELINE, None)
    nobody = shelter_set_summary(POPULATION, np.full(8, NO_BASELINE_ACCESS, dtype=np.uint8), 2.5, STAGES)
    assert (nobody.baseline, nobody.keeping, nobody.lost, nobody.lost_share) == (0.0, 0.0, 0.0, None)
    assert (nobody.cutoff_status, nobody.cutoff_hour) == (CUTOFF_NO_BASELINE, None)
    never = shelter_set_summary(POPULATION, np.full(8, NEVER_LOST, dtype=np.uint8), 2.5, STAGES)
    assert (never.baseline, never.lost, never.lost_share, never.cutoff_status) == (1000.0, 0.0, 0.0, CUTOFF_NOT_REACHED)


def test_another_coverage_share_moves_the_cutoff() -> None:
    assert summary(SET_A, 2.5, coverage_share=0.9).cutoff_hour == 2  # 850 < 855
    assert summary(SET_A, 2.5, coverage_share=0.4).cutoff_status == CUTOFF_NOT_REACHED  # never below 380
    assert access_cutoff_hour(100, [100, 60, 30], 0.7) == (CUTOFF_REACHED, 1)


def test_access_returns_when_the_water_recedes_but_the_cutoff_stays_the_first_hour() -> None:
    falling = summary(SET_A, 0.05)
    assert (falling.keeping, falling.lost) == (950.0, 0.0)
    assert falling.cutoff_hour == 4


# --- Inputs and output shape ---------------------------------------------------------------------------


def test_mismatched_or_invalid_arrays_are_refused() -> None:
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(POPULATION, SET_A[:-1], 1.0, STAGES)
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(POPULATION, SET_A, 1.0, STAGES, mask=WET_HOMES[:-1])
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(POPULATION, SET_A, 1.0, STAGES, vulnerable_population=VULNERABLE[:-1])
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(np.where(np.arange(8) == 0, -1.0, POPULATION), SET_A, 1.0, STAGES)
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(np.where(np.arange(8) == 0, np.nan, POPULATION), SET_A, 1.0, STAGES)
    with pytest.raises(ShelterSetComparisonError):
        shelter_set_summary(POPULATION.reshape(2, 4), SET_A.reshape(2, 4), 1.0, STAGES)


def test_summary_is_a_frozen_record_that_serialises_to_json() -> None:
    peak = summary(SET_A, 2.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        peak.lost = 0.0  # type: ignore[misc]
    record = json.loads(json.dumps(peak.as_dict()))
    assert record == {"residents": 1000.0, "baseline": 950.0, "keeping": 450.0, "lost": 500.0, "lost_share": 0.5263,
                      "vulnerable_baseline": 80.0, "vulnerable_lost": 70.0, "cutoff_status": "reached", "cutoff_hour": 4}


def test_fractional_residents_sum_exactly_in_any_node_order() -> None:
    rng = np.random.default_rng(20240912)
    people = rng.uniform(0.01, 30.0, 500)
    codes = rng.choice(np.array([3, 7, 20, 70, NEVER_LOST, NO_BASELINE_ACCESS], dtype=np.uint8), 500)
    stages = [0.0, 0.2, 0.4, 1.2, 3.5, 1.0, 0.0]
    first = shelter_set_summary(people, codes, 3.5, stages)
    order = rng.permutation(500)
    again = shelter_set_summary(people[order], codes[order], 3.5, stages)
    assert first == again
    assert first.keeping + first.lost == pytest.approx(first.baseline, abs=1e-9)


def test_module_states_what_the_figures_are() -> None:
    text = " ".join(module.__doc__.split())
    assert "T1 scenario on a modelled flood" in text
    assert "illustrative stage keyframes and are not observed" in text
    assert "does not rank the sets" in text
    assert "no priority score or action class" in text
