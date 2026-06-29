from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.road_risk import RoadRiskError, score_road_disruption

FIXTURES = Path(__file__).parent / "fixtures"


def load_roads() -> pd.DataFrame:
    geojson = json.loads((FIXTURES / "sample_roads.geojson").read_text(encoding="utf-8"))
    return pd.DataFrame([feature["properties"] for feature in geojson["features"]])


def load_flood() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_flood_probability.csv")


def test_score_road_disruption_computes_fixture_probabilities() -> None:
    result = score_road_disruption(load_roads(), load_flood())

    risk_by_road = dict(
        zip(
            result["road_id"],
            result["road_disruption_probability_0_1"],
            strict=True,
        )
    )

    assert risk_by_road == {
        "FG-RD-001": pytest.approx(0.832),
        "FG-RD-002": pytest.approx(0.717),
        "FG-RD-003": pytest.approx(0.547),
    }
    assert {
        "road_id",
        "subdistrict_id",
        "road_disruption_probability_0_1",
        "confidence_class",
        "top_risk_reason",
        "source_name",
        "source_timestamp",
        "assumptions",
    }.issubset(result.columns)


def test_score_road_disruption_applies_road_class_weighting() -> None:
    roads = pd.DataFrame(
        {
            "road_id": ["primary-road", "local-road"],
            "road_class": ["primary", "local"],
            "bridge_flag": [False, False],
            "subdistrict_id": ["FG-TB-001", "FG-TB-001"],
            "surrounding_inundation_0_1": [0.5, 0.5],
        }
    )

    result = score_road_disruption(roads, load_flood())

    primary = result.loc[result["road_id"] == "primary-road"].iloc[0]
    local = result.loc[result["road_id"] == "local-road"].iloc[0]
    assert primary["road_disruption_probability_0_1"] > local[
        "road_disruption_probability_0_1"
    ]


def test_score_road_disruption_applies_bridge_adjustment() -> None:
    roads = pd.DataFrame(
        {
            "road_id": ["no-bridge", "bridge"],
            "road_class": ["secondary", "secondary"],
            "bridge_flag": [False, True],
            "subdistrict_id": ["FG-TB-002", "FG-TB-002"],
            "surrounding_inundation_0_1": [0.5, 0.5],
        }
    )

    result = score_road_disruption(roads, load_flood())

    bridge = result.loc[result["road_id"] == "bridge"].iloc[0]
    no_bridge = result.loc[result["road_id"] == "no-bridge"].iloc[0]
    assert bridge["road_disruption_probability_0_1"] == pytest.approx(
        no_bridge["road_disruption_probability_0_1"] + 0.05
    )


def test_score_road_disruption_allows_probability_boundaries() -> None:
    roads = pd.DataFrame(
        {
            "road_id": ["low", "high"],
            "road_class": ["local", "primary"],
            "bridge_flag": [False, True],
            "subdistrict_id": ["LOW", "HIGH"],
            "surrounding_inundation_0_1": [0, 1],
        }
    )
    flood = pd.DataFrame(
        {
            "subdistrict_id": ["LOW", "HIGH"],
            "mean_flood_probability_0_1": [0, 1],
            "confidence_class": ["high", "high"],
            "source_name": ["test", "test"],
            "source_timestamp": ["2026-06-29T00:00:00Z", "2026-06-29T00:00:00Z"],
        }
    )

    result = score_road_disruption(roads, flood)

    assert result.loc[result["road_id"] == "low", "road_disruption_probability_0_1"].item() == pytest.approx(0.035)
    assert result.loc[result["road_id"] == "high", "road_disruption_probability_0_1"].item() == pytest.approx(1.0)


def test_score_road_disruption_rejects_out_of_range_probability() -> None:
    roads = load_roads()
    roads.loc[0, "surrounding_inundation_0_1"] = 1.1

    with pytest.raises(RoadRiskError, match="surrounding_inundation_0_1"):
        score_road_disruption(roads, load_flood())


def test_score_road_disruption_rejects_unknown_road_class() -> None:
    roads = load_roads()
    roads.loc[0, "road_class"] = "skyway"

    with pytest.raises(RoadRiskError, match="Unknown road_class"):
        score_road_disruption(roads, load_flood())


def test_score_road_disruption_rejects_missing_columns() -> None:
    roads = load_roads().drop(columns=["road_class"])

    with pytest.raises(RoadRiskError, match="road_class"):
        score_road_disruption(roads, load_flood())
