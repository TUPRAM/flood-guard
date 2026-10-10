"""The need mix inside a unit: every cell in one kind, and the sums that go with them."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard import need_mix as nm

#                      wet    wet+cut  dry cut  dry hosp  fine   unjoined  no route before  dry, no hospital before
INSIDE = np.array([True, True, False, False, False, False, False, False])
CONNECTED = np.array([True, True, True, True, True, False, True, True])
HAD_ROUTE = np.array([True, True, True, True, True, False, False, True])
HAS_ROUTE = np.array([True, False, False, True, True, False, False, True])
HAD_HOSPITAL = np.array([True, True, True, True, True, False, False, False])
HAS_HOSPITAL = np.array([True, False, False, False, True, False, False, False])
RESIDENTS = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 5.0, 3.0, 2.0])
ARGUMENTS = (INSIDE, CONNECTED, HAD_ROUTE, HAS_ROUTE, HAD_HOSPITAL, HAS_HOSPITAL)


def names(labels: np.ndarray) -> list[str]:
    return [nm.NEED_TYPES[index] for index in labels.tolist()]


def test_every_cell_takes_the_first_kind_that_fits() -> None:
    assert names(nm.label_cells(*ARGUMENTS)) == [
        nm.IN_THE_WATER, nm.IN_THE_WATER, nm.DRY_CUT_OFF, nm.DRY_LOSES_HOSPITAL, nm.NOT_AFFECTED, nm.NOT_ASSESSED, nm.NOT_ASSESSED,
        nm.NOT_AFFECTED]


def test_a_cell_in_the_water_is_in_the_water_whatever_else_is_true_of_it() -> None:
    everything = nm.label_cells(np.ones(8, dtype=bool), CONNECTED, HAD_ROUTE, HAS_ROUTE, HAD_HOSPITAL, HAS_HOSPITAL)
    assert set(names(everything)) == {nm.IN_THE_WATER}


def test_the_mix_counts_each_resident_once() -> None:
    whole = nm.mix(nm.label_cells(*ARGUMENTS), RESIDENTS)
    counts = {name: entry["residents"] for name, entry in whole["by_type"].items()}
    assert counts == {nm.IN_THE_WATER: 30.0, nm.DRY_CUT_OFF: 30.0, nm.DRY_LOSES_HOSPITAL: 40.0, nm.NOT_AFFECTED: 52.0, nm.NOT_ASSESSED: 8.0}
    assert whole["residents"] == 160.0 and sum(counts.values()) == 160.0
    assert sum(entry["share"] for entry in whole["by_type"].values()) == pytest.approx(1.0, abs=1e-3)
    part = nm.mix(nm.label_cells(*ARGUMENTS), RESIDENTS, where=np.array([True, True, True, False, False, False, False, False]))
    assert part["residents"] == 60.0 and part["by_type"][nm.IN_THE_WATER]["share"] == 0.5
    assert nm.mix(nm.label_cells(*ARGUMENTS), RESIDENTS, where=np.zeros(8, dtype=bool))["by_type"][nm.NOT_AFFECTED]["share"] is None


def test_the_overlaps_say_what_the_order_hides() -> None:
    hidden = nm.overlaps(*ARGUMENTS, RESIDENTS)
    assert hidden == {"in_the_water_and_cut_off": 20.0, "in_the_water_and_losing_the_hospital": 20.0,
                      "cut_off_in_the_water_or_dry": 50.0, "losing_the_hospital_in_the_water_or_dry": 90.0}


def test_impossible_cells_are_refused() -> None:
    with pytest.raises(nm.NeedMixError, match="had not before"):
        nm.label_cells(INSIDE, CONNECTED, HAD_ROUTE, np.ones(8, dtype=bool), HAD_HOSPITAL, HAS_HOSPITAL)
    with pytest.raises(nm.NeedMixError, match="joined to the graph"):
        nm.label_cells(INSIDE, np.zeros(8, dtype=bool), HAD_ROUTE, HAS_ROUTE, HAD_HOSPITAL, HAS_HOSPITAL)
    with pytest.raises(nm.NeedMixError):
        nm.label_cells(INSIDE[:3], CONNECTED, HAD_ROUTE, HAS_ROUTE, HAD_HOSPITAL, HAS_HOSPITAL)
    with pytest.raises(nm.NeedMixError):
        nm.mix(np.array([0, 9]), np.array([1.0, 1.0]))


def test_the_range_over_runs_gives_the_lowest_and_the_highest_of_each_kind() -> None:
    first = nm.mix(nm.label_cells(*ARGUMENTS), RESIDENTS)
    drier = nm.mix(nm.label_cells(np.zeros(8, dtype=bool), CONNECTED, HAD_ROUTE, HAS_ROUTE, HAD_HOSPITAL, HAS_HOSPITAL), RESIDENTS)
    spread = nm.mix_range([first, drier])
    assert spread[nm.IN_THE_WATER] == {"share_lowest": 0.0, "share_highest": 0.1875, "residents_lowest": 0.0, "residents_highest": 30.0}
    assert spread[nm.DRY_CUT_OFF]["residents_highest"] == 50.0, "the cell that was in the water and cut off is dry and cut off in the drier run"
    with pytest.raises(nm.NeedMixError):
        nm.mix_range([])


def test_squares_hold_the_residents_of_their_cells_by_kind() -> None:
    x = np.array([10.0, 499.0, 500.0, 760.0, 10.0, 10.0, 10.0, 10.0])
    y = np.array([10.0, 10.0, 10.0, 10.0, 600.0, 600.0, 600.0, 600.0])
    columns, rows = nm.squares(x, y, 500.0)
    assert columns.tolist() == [0, 0, 1, 1, 0, 0, 0, 0] and rows.tolist() == [0, 0, 0, 0, 1, 1, 1, 1]
    listed = {(item["column"], item["row"]): item for item in nm.by_square(nm.label_cells(*ARGUMENTS), RESIDENTS, columns, rows)}
    assert listed[(0, 0)]["leading_type"] == nm.IN_THE_WATER and listed[(0, 0)]["residents"] == 30.0
    assert listed[(1, 0)]["leading_type"] == nm.DRY_LOSES_HOSPITAL and listed[(1, 0)]["by_type"][nm.DRY_CUT_OFF] == 30.0
    assert listed[(0, 1)]["leading_type"] == nm.NOT_AFFECTED and listed[(0, 1)]["residents"] == 60.0
    assert sum(item["residents"] for item in listed.values()) == 160.0
    with pytest.raises(nm.NeedMixError):
        nm.squares(x, y, 0.0)


def test_a_tie_between_two_kinds_goes_to_the_one_tested_first_and_an_empty_square_has_none() -> None:
    labels = np.array([nm.NEED_TYPES.index(nm.DRY_CUT_OFF), nm.NEED_TYPES.index(nm.IN_THE_WATER), nm.NEED_TYPES.index(nm.NOT_AFFECTED)])
    listed = nm.by_square(labels, np.array([5.0, 5.0, 0.0]), np.array([0, 0, 3]), np.array([0, 0, 3]))
    assert listed[0]["leading_type"] == nm.IN_THE_WATER and listed[1]["leading_type"] is None


def test_the_words_of_every_kind_are_given_and_none_calls_a_place_safe() -> None:
    assert set(nm.WORDS) == set(nm.ACTION_WORDS) == set(nm.NEED_TYPES)
    assert all("safe" not in text.lower() for text in (*nm.WORDS.values(), *nm.ACTION_WORDS.values()))
