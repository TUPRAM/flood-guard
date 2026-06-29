from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.exports import ExportError, write_priority_geojson, write_road_risk_geojson
from floodguard.scenarios import SCENARIO_COMPARISON_COLUMNS

FIXTURES = Path(__file__).parent / "fixtures"


def priority_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "subdistrict_id": ["FG-TB-001"],
            "subdistrict_name": ["River Market"],
            "fpps_0_100": [81.6],
            "action_class": ["A"],
            "top_reason": ["High exposure and access loss require life-safety action."],
            "confidence_class": ["high"],
            "source_timestamp": ["2026-06-29T00:00:00Z"],
            "assumptions": ["synthetic"],
        }
    )
    for column in SCENARIO_COMPARISON_COLUMNS:
        frame[column] = 0
    frame.loc[0, "baseline_equity_gap_ratio"] = 1.0
    frame.loc[0, "temporary_shelter_change_people_losing_30_min_access"] = -30
    frame.loc[0, "road_closure_change_people_losing_30_min_access"] = 50
    return frame


def road_risk_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "road_id": ["FG-RD-001"],
            "subdistrict_id": ["FG-TB-001"],
            "road_disruption_probability_0_1": [0.832],
            "confidence_class": ["high"],
            "top_risk_reason": ["Highest road-risk driver is flood probability."],
            "source_timestamp": ["2026-06-29T00:00:00Z"],
            "assumptions": ["synthetic"],
        }
    )


def test_write_priority_geojson_merges_and_preserves_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "priority.geojson"

    write_priority_geojson(
        FIXTURES / "sample_admin.geojson",
        priority_frame(),
        output_path,
    )

    geojson = json.loads(output_path.read_text(encoding="utf-8"))
    props = geojson["features"][0]["properties"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    assert props["subdistrict_id"] == "FG-TB-001"
    assert props["fpps_0_100"] == pytest.approx(81.6)
    assert props["source_timestamp"] == "2026-06-29T00:00:00Z"
    assert props["confidence_class"] == "high"
    assert props["assumptions"] == "synthetic"
    assert props["baseline_people_losing_30_min_access"] == 0
    assert props["temporary_shelter_change_people_losing_30_min_access"] == -30
    assert props["road_closure_change_people_losing_30_min_access"] == 50


def test_write_road_risk_geojson_merges_road_geometry(tmp_path: Path) -> None:
    output_path = tmp_path / "road_risk.geojson"

    write_road_risk_geojson(
        FIXTURES / "sample_roads.geojson",
        road_risk_frame(),
        output_path,
    )

    geojson = json.loads(output_path.read_text(encoding="utf-8"))
    props = geojson["features"][0]["properties"]
    assert len(geojson["features"]) == 1
    assert props["road_id"] == "FG-RD-001"
    assert props["road_disruption_probability_0_1"] == pytest.approx(0.832)
    assert geojson["features"][0]["geometry"]["type"] == "LineString"


def test_write_priority_geojson_rejects_missing_geometry_match(tmp_path: Path) -> None:
    frame = priority_frame()
    frame.loc[0, "subdistrict_id"] = "MISSING"

    with pytest.raises(ExportError, match="Missing GeoJSON geometry"):
        write_priority_geojson(
            FIXTURES / "sample_admin.geojson",
            frame,
            tmp_path / "priority.geojson",
        )


def test_write_priority_geojson_rejects_duplicate_ids(tmp_path: Path) -> None:
    frame = pd.concat([priority_frame(), priority_frame()], ignore_index=True)

    with pytest.raises(ExportError, match="duplicate subdistrict_id"):
        write_priority_geojson(
            FIXTURES / "sample_admin.geojson",
            frame,
            tmp_path / "priority.geojson",
        )


def test_write_road_risk_geojson_rejects_missing_join_key(tmp_path: Path) -> None:
    frame = road_risk_frame().drop(columns=["road_id"])

    with pytest.raises(ExportError, match="road_id"):
        write_road_risk_geojson(
            FIXTURES / "sample_roads.geojson",
            frame,
            tmp_path / "road_risk.geojson",
        )
