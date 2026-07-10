from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from floodguard.mae_sai_context import (
    build_access_hotspot_geojson,
    build_facility_geojson,
    build_mae_sai_context_outputs,
    build_road_risk_geojson,
    geometry_representative_point,
    point_in_geometry,
)
from floodguard.sar_raster_extract import (
    SARRasterInputs,
    summarize_sar_probability_by_geometries,
)


REPO_ROOT = Path(__file__).parents[1]


def square_feature(
    subdistrict_id: str,
    name: str,
    left: float,
    right: float,
) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "subdistrict_id": subdistrict_id,
            "subdistrict_name": name,
            "subdistrict_name_th": name,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [left, 20.40],
                    [right, 20.40],
                    [right, 20.44],
                    [left, 20.44],
                    [left, 20.40],
                ]
            ],
        },
    }


def write_raster(path: Path, values: np.ndarray) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(99.80, 20.44, 0.01, 0.01),
    ) as dataset:
        dataset.write(values.astype("float32"), 1)


def admin_geojson() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            square_feature("A", "Area A", 99.80, 99.84),
            square_feature("B", "Area B", 99.84, 99.88),
        ],
    }


def roads_geojson() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "R-A",
                    "name": "Road A",
                    "highway": "primary",
                    "other_tags": '"bridge"=>"yes"',
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [99.805, 20.42],
                        [99.815, 20.42],
                        [99.825, 20.42],
                        [99.835, 20.42],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "R-B",
                    "name": "Road B",
                    "highway": "secondary",
                    "other_tags": "",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [99.845, 20.42],
                        [99.855, 20.42],
                        [99.865, 20.42],
                        [99.875, 20.42],
                    ],
                },
            },
        ],
    }


def points_geojson() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "F-A",
                    "name": "Clinic A",
                    "other_tags": '"amenity"=>"clinic"',
                },
                "geometry": {"type": "Point", "coordinates": [99.805, 20.42]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "F-B",
                    "name": "School B",
                    "other_tags": '"amenity"=>"school"',
                },
                "geometry": {"type": "Point", "coordinates": [99.875, 20.42]},
            },
        ],
    }


def sar_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subdistrict_id": "A",
                "subdistrict_name": "Area A",
                "mean_flood_probability_0_1": 0.30,
                "p90_flood_probability_0_1": 0.70,
                "binary_flood_share_0_1": 0.20,
                "mean_combined_sar_change_score": 1.5,
                "sample_pixel_count": 100,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "processing_scope": "candidate",
                "assumptions": "fixture",
            },
            {
                "subdistrict_id": "B",
                "subdistrict_name": "Area B",
                "mean_flood_probability_0_1": 0.10,
                "p90_flood_probability_0_1": 0.30,
                "binary_flood_share_0_1": 0.05,
                "mean_combined_sar_change_score": 0.5,
                "sample_pixel_count": 100,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "processing_scope": "candidate",
                "assumptions": "fixture",
            },
        ]
    )


def test_point_in_geometry_handles_reporting_polygons() -> None:
    geometry = square_feature("A", "Area A", 99.80, 99.84)["geometry"]

    assert point_in_geometry(99.82, 20.42, geometry)
    assert not point_in_geometry(99.86, 20.42, geometry)


def test_build_mae_sai_context_outputs_joins_real_context_contracts(
    tmp_path: Path,
) -> None:
    worldpop = tmp_path / "worldpop.tif"
    dem = tmp_path / "dem.tif"
    write_raster(worldpop, np.full((4, 8), 25.0, dtype="float32"))
    write_raster(
        dem,
        np.tile(np.arange(8, dtype="float32"), (4, 1)) * 5.0,
    )

    outputs = build_mae_sai_context_outputs(
        admin_geojson(),
        roads_geojson(),
        points_geojson(),
        sar_summary(),
        worldpop_path=str(worldpop),
        dem_path=str(dem),
    )

    assert len(outputs.decision_inputs) == 2
    assert set(outputs.decision_inputs["subdistrict_id"]) == {"A", "B"}
    assert outputs.population_context["total_population"].sum() == 800.0
    assert len(outputs.road_risk) == 2
    assert len(outputs.facilities) == 2
    assert set(outputs.access_loss["subdistrict_id"]) == {"A", "B"}
    assert set(outputs.equity_gap["subdistrict_id"]) == {"A", "B"}
    assert outputs.road_risk["assumptions"].str.contains(
        "not a segment-level raster intersection"
    ).all()
    road_geojson = build_road_risk_geojson(roads_geojson(), outputs.road_risk)
    facility_geojson = build_facility_geojson(outputs.facilities)
    hotspot_geojson = build_access_hotspot_geojson(
        admin_geojson(),
        outputs.access_loss,
        outputs.equity_gap,
    )
    assert len(road_geojson["features"]) == 2
    assert len(facility_geojson["features"]) == 2
    assert len(hotspot_geojson["features"]) == 2
    assert road_geojson["features"][0]["properties"]["candidate_status"].startswith(
        "candidate_"
    )
    assert facility_geojson["features"][0]["properties"]["candidate_status"] == (
        "unverified_osm_candidate"
    )
    assert outputs.decision_inputs["context_status"].eq(
        "real_open_context_joined_with_proxy_vulnerability"
    ).all()
    assert not bool(
        outputs.quality_summary.loc[
            0, "manual_reference_overlaps_official_adm3"
        ]
    )


def test_geometry_representative_point_stays_inside_reporting_polygon() -> None:
    geometry = square_feature("A", "Area A", 99.80, 99.84)["geometry"]

    longitude, latitude = geometry_representative_point(geometry)

    assert point_in_geometry(longitude, latitude, geometry)


def test_sar_probability_summary_uses_polygons_as_aggregation_not_labels(
    tmp_path: Path,
) -> None:
    pre_vv = tmp_path / "pre_vv.tif"
    pre_vh = tmp_path / "pre_vh.tif"
    post_vv = tmp_path / "post_vv.tif"
    post_vh = tmp_path / "post_vh.tif"
    pre = np.full((4, 8), 10.0, dtype="float32")
    post = np.full((4, 8), 10.0, dtype="float32")
    post[:, :4] = 1.0
    for path, values in (
        (pre_vv, pre),
        (pre_vh, pre),
        (post_vv, post),
        (post_vh, post),
    ):
        write_raster(path, values)
    inputs = SARRasterInputs(
        pre_vv_uri=str(pre_vv),
        pre_vh_uri=str(pre_vh),
        post_vv_uri=str(post_vv),
        post_vh_uri=str(post_vh),
        reference_geometries=(),
        reference_crs="EPSG:4326",
    )

    summary = summarize_sar_probability_by_geometries(
        inputs,
        admin_geojson()["features"],
        output_shape=(8, 8),
    )

    area_a = summary.set_index("subdistrict_id").loc["A"]
    area_b = summary.set_index("subdistrict_id").loc["B"]
    assert area_a["mean_flood_probability_0_1"] > 0.9
    assert area_b["mean_flood_probability_0_1"] < 0.1
    assert summary["processing_scope"].eq(
        "real_sentinel1_adm3_candidate_context"
    ).all()


def test_committed_mae_sai_context_outputs_keep_real_grain_and_redacted_paths() -> None:
    output_dir = REPO_ROOT / "outputs"
    decision = pd.read_csv(output_dir / "mae_sai_real_context_decision_inputs.csv")
    quality = pd.read_csv(output_dir / "mae_sai_context_quality_summary.csv")
    priority = json.loads(
        (output_dir / "mae_sai_priority_subdistricts.geojson").read_text(
            encoding="utf-8"
        )
    )
    road_geometry = json.loads(
        (output_dir / "mae_sai_road_risk.geojson").read_text(encoding="utf-8")
    )
    facility_geometry = json.loads(
        (output_dir / "mae_sai_facilities.geojson").read_text(encoding="utf-8")
    )
    hotspot_geometry = json.loads(
        (output_dir / "mae_sai_access_hotspots.geojson").read_text(encoding="utf-8")
    )

    assert len(decision) == 8
    assert decision["subdistrict_id"].nunique() == 8
    assert decision["subdistrict_id"].str.startswith("TH5709").all()
    assert decision["context_status"].eq(
        "real_open_context_joined_with_proxy_vulnerability"
    ).all()
    assert (pd.to_numeric(decision["road_count"]) > 0).all()
    assert len(priority["features"]) == 8
    assert len(road_geometry["features"]) == int(quality.loc[0, "road_way_count"])
    assert len(facility_geometry["features"]) == int(
        quality.loc[0, "facility_count"]
    )
    assert len(hotspot_geometry["features"]) == 8
    assert any(
        feature["properties"]["candidate_status"]
        == "modeled_access_loss_candidate"
        for feature in hotspot_geometry["features"]
    )
    assert int(quality.loc[0, "road_way_count"]) > 0
    assert int(quality.loc[0, "facility_count"]) > 0
    assert float(quality.loc[0, "worldpop_total_population"]) > 0

    derived_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            output_dir / "mae_sai_real_context_decision_inputs.csv",
            output_dir / "mae_sai_context_quality_summary.csv",
            output_dir / "mae_sai_priority_subdistricts.geojson",
            output_dir / "mae_sai_road_risk.geojson",
            output_dir / "mae_sai_facilities.geojson",
            output_dir / "mae_sai_access_hotspots.geojson",
        )
    )
    assert "C:\\Users\\" not in derived_text
    assert "C:/Users/" not in derived_text
    assert "FloodGuard_external_data" not in derived_text
