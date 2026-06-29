from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss
from floodguard.scenarios import (
    SCENARIO_COMPARISON_COLUMNS,
    ScenarioError,
    build_scenario_comparison,
    merge_scenario_comparison,
    run_access_scenario,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(FIXTURES / "sample_population_nodes.csv"),
        pd.read_csv(FIXTURES / "sample_access_edges.csv"),
        pd.read_csv(FIXTURES / "sample_facilities.csv"),
    )


def baseline_outputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    population, edges, facilities = load_inputs()
    access = calculate_access_loss(population, edges, facilities)
    equity = compute_equity_gap(equity_input_from_access_loss(access, threshold=30))
    return access, equity


def test_add_temporary_shelter_reduces_target_access_loss() -> None:
    population, edges, facilities = load_inputs()
    baseline_access, baseline_equity = baseline_outputs()

    scenario = run_access_scenario(
        population,
        edges,
        facilities,
        "add_temporary_shelter",
        baseline_access=baseline_access,
        baseline_equity=baseline_equity,
    )

    scenario_access = scenario["access_loss"].set_index("subdistrict_id")
    baseline = baseline_access.set_index("subdistrict_id")
    assert scenario_access.loc["FG-TB-002", "people_losing_30_min_access"] < baseline.loc["FG-TB-002", "people_losing_30_min_access"]
    assert scenario["scenario_summary"].loc[0, "change_people_losing_30_min_access"] == pytest.approx(-30)


def test_close_road_increases_target_access_loss() -> None:
    population, edges, facilities = load_inputs()
    baseline_access, baseline_equity = baseline_outputs()

    scenario = run_access_scenario(
        population,
        edges,
        facilities,
        "close_road",
        baseline_access=baseline_access,
        baseline_equity=baseline_equity,
    )

    scenario_access = scenario["access_loss"].set_index("subdistrict_id")
    baseline = baseline_access.set_index("subdistrict_id")
    assert scenario_access.loc["FG-TB-002", "people_losing_30_min_access"] > baseline.loc["FG-TB-002", "people_losing_30_min_access"]
    assert scenario["scenario_summary"].loc[0, "change_people_losing_30_min_access"] == pytest.approx(50)


def test_run_access_scenario_rejects_invalid_scenario() -> None:
    population, edges, facilities = load_inputs()

    with pytest.raises(ScenarioError, match="Unknown access scenario"):
        run_access_scenario(population, edges, facilities, "unknown")


def test_close_road_rejects_missing_edge() -> None:
    population, edges, facilities = load_inputs()

    with pytest.raises(ScenarioError, match="No edge found"):
        run_access_scenario(
            population,
            edges,
            facilities,
            "close_road",
            from_node="NOPE",
            to_node="F1",
        )


def test_scenario_summary_contains_expected_columns() -> None:
    population, edges, facilities = load_inputs()
    baseline_access, baseline_equity = baseline_outputs()

    scenario = run_access_scenario(
        population,
        edges,
        facilities,
        "add_temporary_shelter",
        baseline_access=baseline_access,
        baseline_equity=baseline_equity,
    )

    assert {
        "scenario_name",
        "baseline_people_losing_30_min_access",
        "scenario_people_losing_30_min_access",
        "change_people_losing_30_min_access",
        "baseline_max_equity_gap_ratio",
        "scenario_max_equity_gap_ratio",
        "change_max_equity_gap_ratio",
    }.issubset(scenario["scenario_summary"].columns)


def test_build_scenario_comparison_outputs_geojson_fields() -> None:
    population, edges, facilities = load_inputs()
    baseline_access, baseline_equity = baseline_outputs()
    temporary_shelter = run_access_scenario(
        population,
        edges,
        facilities,
        "add_temporary_shelter",
        baseline_access=baseline_access,
        baseline_equity=baseline_equity,
    )
    road_closure = run_access_scenario(
        population,
        edges,
        facilities,
        "close_road",
        baseline_access=baseline_access,
        baseline_equity=baseline_equity,
    )

    comparison = build_scenario_comparison(
        baseline_access,
        baseline_equity,
        temporary_shelter["access_loss"],
        temporary_shelter["equity_gap"],
        road_closure["access_loss"],
        road_closure["equity_gap"],
    ).set_index("subdistrict_id")

    assert set(SCENARIO_COMPARISON_COLUMNS).issubset(comparison.columns)
    assert comparison.loc[
        "FG-TB-002",
        "temporary_shelter_change_people_losing_30_min_access",
    ] == pytest.approx(-30)
    assert comparison.loc[
        "FG-TB-002",
        "road_closure_change_people_losing_30_min_access",
    ] == pytest.approx(50)


def test_merge_scenario_comparison_rejects_missing_priority_rows() -> None:
    priority = pd.DataFrame({"subdistrict_id": ["FG-TB-001", "FG-TB-002"]})
    comparison = pd.DataFrame(
        {
            "subdistrict_id": ["FG-TB-001"],
            **{column: [0] for column in SCENARIO_COMPARISON_COLUMNS},
        }
    )

    with pytest.raises(ScenarioError, match="Missing scenario comparison row"):
        merge_scenario_comparison(priority, comparison)
