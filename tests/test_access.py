from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.access import AccessError, calculate_access_loss

FIXTURES = Path(__file__).parent / "fixtures"


def load_population() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_population_nodes.csv")


def load_edges() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_access_edges.csv")


def load_facilities() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_facilities.csv")


def test_calculate_access_loss_computes_threshold_losses() -> None:
    result = calculate_access_loss(load_population(), load_edges(), load_facilities())

    by_id = result.set_index("subdistrict_id")

    assert by_id.loc["FG-TB-001", "people_losing_15_min_access"] == pytest.approx(100)
    assert by_id.loc["FG-TB-001", "people_losing_30_min_access"] == pytest.approx(100)
    assert by_id.loc["FG-TB-001", "people_losing_60_min_access"] == pytest.approx(100)
    assert by_id.loc["FG-TB-002", "people_losing_15_min_access"] == pytest.approx(0)
    assert by_id.loc["FG-TB-002", "people_losing_30_min_access"] == pytest.approx(30)
    assert by_id.loc["FG-TB-002", "people_losing_60_min_access"] == pytest.approx(0)
    assert by_id.loc["FG-TB-003", "people_losing_30_min_access"] == pytest.approx(60)
    assert by_id.loc["FG-TB-003", "people_losing_60_min_access"] == pytest.approx(60)
    assert by_id.loc["FG-TB-004", "people_losing_60_min_access"] == pytest.approx(0)


def test_calculate_access_loss_tracks_vulnerable_and_non_vulnerable_losses() -> None:
    result = calculate_access_loss(load_population(), load_edges(), load_facilities())
    by_id = result.set_index("subdistrict_id")

    assert by_id.loc["FG-TB-002", "total_vulnerable_population"] == pytest.approx(20)
    assert by_id.loc["FG-TB-002", "total_non_vulnerable_population"] == pytest.approx(60)
    assert by_id.loc[
        "FG-TB-002",
        "vulnerable_population_losing_30_min_access",
    ] == pytest.approx(20)
    assert by_id.loc[
        "FG-TB-002",
        "non_vulnerable_population_losing_30_min_access",
    ] == pytest.approx(10)


def test_calculate_access_loss_closed_disrupted_edge_causes_loss() -> None:
    result = calculate_access_loss(load_population(), load_edges(), load_facilities())
    row = result.set_index("subdistrict_id").loc["FG-TB-001"]

    assert row["people_losing_15_min_access"] == pytest.approx(100)


def test_calculate_access_loss_no_normal_access_is_not_counted_as_lost() -> None:
    population = pd.DataFrame(
        {
            "node_id": ["P-REMOTE"],
            "subdistrict_id": ["REMOTE"],
            "subdistrict_name": ["Remote"],
            "total_population": [25],
            "vulnerable_population": [5],
            "non_vulnerable_population": [20],
        }
    )
    edges = pd.DataFrame(
        {
            "from_node": ["P-REMOTE"],
            "to_node": ["F1"],
            "normal_minutes": [90],
            "disrupted_minutes": [""],
        }
    )

    result = calculate_access_loss(population, edges, load_facilities())

    assert result.loc[0, "people_losing_60_min_access"] == pytest.approx(0)


def test_calculate_access_loss_rejects_missing_columns() -> None:
    population = load_population().drop(columns=["total_population"])

    with pytest.raises(AccessError, match="total_population"):
        calculate_access_loss(population, load_edges(), load_facilities())
