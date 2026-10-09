"""The 2024-rescaled demand: the two rules of decision log R38 on invented grids."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard import demand_rescale

GRID = {"west": 100.0, "north": 21.0, "cell_width": 0.5, "cell_height": 0.5, "rows": 2, "columns": 2}


def test_a_point_belongs_to_the_cell_that_holds_it() -> None:
    x = np.array([100.1, 100.6, 100.1, 100.9])
    y = np.array([20.9, 20.9, 20.4, 20.01])
    assert demand_rescale.cell_index(x, y, **GRID).tolist() == [0, 1, 2, 3]


def test_a_point_outside_the_grid_has_no_cell() -> None:
    x = np.array([99.9, 101.0, 100.2, 100.2])
    y = np.array([20.5, 20.5, 21.1, 19.99])
    assert demand_rescale.cell_index(x, y, **GRID).tolist() == [-1, -1, -1, -1]


def test_a_point_on_an_inner_edge_goes_to_the_cell_east_and_south_of_it() -> None:
    assert demand_rescale.cell_index(np.array([100.5]), np.array([20.5]), **GRID).tolist() == [3]


def test_a_grid_needs_positive_sizes() -> None:
    with pytest.raises(demand_rescale.DemandRescaleError):
        demand_rescale.cell_index(np.array([100.1]), np.array([20.9]), **{**GRID, "cell_width": 0.0})


def test_counts_are_scaled_to_the_2024_total_of_their_cell() -> None:
    counts = np.array([[1.0, 3.0], [2.0, 0.0]])
    cells = np.array([[7, 7], [8, 8]])
    result = demand_rescale.rescale_counts(counts, cells, {7: 8.0, 8: 1.0})
    assert result["counts"].tolist() == [[2.0, 6.0], [1.0, 0.0]]
    assert not result["kept_at_2020"].any()
    assert result["record"]["residents_2020"] == 6.0
    assert result["record"]["residents_after"] == 9.0
    assert result["record"]["ratio_lowest_median_highest"] == [0.5, 1.25, 2.0]


def test_a_count_whose_cell_has_no_2024_total_keeps_its_2020_value_and_is_reported() -> None:
    counts = np.array([4.0, 5.0, 1.0])
    cells = np.array([7, 7, 9])
    result = demand_rescale.rescale_counts(counts, cells, {7: None, 9: 3.0})
    assert result["counts"].tolist() == [4.0, 5.0, 3.0]
    assert result["kept_at_2020"].tolist() == [True, True, False]
    kept = result["record"]["kept_at_2020_because_the_1km_cell_has_no_2024_total"]
    assert kept == {"counts": 2, "residents_2020": 9.0, "cells_1km": 1}


def test_a_count_outside_the_2024_grid_keeps_its_2020_value() -> None:
    result = demand_rescale.rescale_counts(np.array([2.5]), np.array([-1]), {})
    assert result["counts"].tolist() == [2.5]
    assert result["kept_at_2020"].tolist() == [True]


def test_a_cell_with_no_2020_count_keeps_zero_and_its_2024_residents_are_reported() -> None:
    result = demand_rescale.rescale_counts(np.array([0.0, 2.0]), np.array([7, 8]), {7: 12.0, 8: 2.0})
    assert result["counts"].tolist() == [0.0, 2.0]
    assert result["record"]["residents_2024_in_1km_cells_with_no_2020_count"] == 12.0


def test_shapes_must_agree() -> None:
    with pytest.raises(demand_rescale.DemandRescaleError):
        demand_rescale.rescale_counts(np.array([1.0, 2.0]), np.array([7]), {7: 1.0})


def test_the_rescaled_count_of_a_demand_cell_is_read_from_its_own_pixel() -> None:
    counts = np.array([[1.0, 3.0], [2.0, 0.0]])
    rescaled = np.array([[2.0, 6.0], [1.0, 0.0]])
    values = demand_rescale.demand_values(counts, rescaled, [0, 1], [1, 0], [3.0, 2.0])
    assert values.tolist() == [6.0, 1.0]


def test_a_demand_cell_that_does_not_carry_the_count_of_its_pixel_is_refused() -> None:
    counts = np.array([[1.0, 3.0], [2.0, 0.0]])
    with pytest.raises(demand_rescale.DemandRescaleError, match="do not carry the count"):
        demand_rescale.demand_values(counts, counts * 2, [0], [1], [2.0])


def test_a_demand_cell_outside_the_window_is_refused() -> None:
    counts = np.zeros((2, 2))
    with pytest.raises(demand_rescale.DemandRescaleError, match="outside the window"):
        demand_rescale.demand_values(counts, counts, [2], [0], [0.0])
