from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
import pytest
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
SCENARIO_BUILDER_PATH = REPO_ROOT / "scripts" / "build_mae_sai_real_context.py"
SCENARIO_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "build_mae_sai_real_context_for_tests",
    SCENARIO_BUILDER_PATH,
)
assert SCENARIO_BUILDER_SPEC is not None
assert SCENARIO_BUILDER_SPEC.loader is not None
SCENARIO_BUILDER = importlib.util.module_from_spec(SCENARIO_BUILDER_SPEC)
SCENARIO_BUILDER_SPEC.loader.exec_module(SCENARIO_BUILDER)


def _write_scenario_artifact_inputs(directory: Path) -> tuple[Path, Path, Path]:
    population_path = directory / "population.csv"
    edge_path = directory / "edges.csv"
    facility_path = directory / "facilities.csv"
    pd.DataFrame([{"node_id": "node-1", "population": 12.0}]).to_csv(
        population_path,
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame([{"edge_id": "edge-1", "minutes": 3.5}]).to_csv(
        edge_path,
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame([{"facility_id": "facility-1", "status": "candidate"}]).to_csv(
        facility_path,
        index=False,
        lineterminator="\n",
    )
    return population_path, edge_path, facility_path


def _write_scenario_receipt(
    directory: Path,
    *,
    git_commit: str | None = None,
    source_timestamp: str = "2024-09-16T06:16:01+07:00",
    generated_at: str = "2026-07-20T08:30:00Z",
    output_name: str = "scenario.json",
) -> Path:
    population_path, edge_path, facility_path = _write_scenario_artifact_inputs(
        directory
    )
    return SCENARIO_BUILDER._write_scenario_input_manifest(
        population_path=population_path,
        edge_path=edge_path,
        facility_path=facility_path,
        output_path=directory / output_name,
        git_commit=_repository_head() if git_commit is None else git_commit,
        source_timestamp=source_timestamp,
        generated_at=generated_at,
    )


def _repository_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


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
            0, "manual_reference_overlaps_thailand_adm3_candidate"
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


def test_scenario_receipt_binds_explicit_provenance_and_is_self_hashed(
    tmp_path: Path,
) -> None:
    manifest_path = _write_scenario_receipt(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    receipt_sha256 = manifest.pop("receipt_sha256")
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == receipt_sha256
    assert manifest["git_commit"] == _repository_head()
    assert manifest["source_timestamp"] == "2024-09-15T23:16:01Z"
    assert manifest["generated_at"] == "2026-07-20T08:30:00Z"
    assert manifest["source_name"].startswith(
        "CDSE Sentinel-1 candidate change context"
    )
    assert manifest["source_licenses"] == [
        "Copernicus Sentinel data legal notice",
        "WorldPop CC BY 4.0",
        "OpenStreetMap ODbL 1.0",
    ]


@pytest.mark.parametrize(
    "git_commit",
    ["", "7e42882", "g" * 40, "a" * 39, "a" * 41],
)
def test_scenario_receipt_rejects_nonimmutable_git_commit(
    tmp_path: Path,
    git_commit: str,
) -> None:
    with pytest.raises(ValueError, match="forty-character hexadecimal commit"):
        _write_scenario_receipt(tmp_path, git_commit=git_commit)


def test_scenario_receipt_rejects_nonexistent_full_commit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identify a commit reachable"):
        _write_scenario_receipt(tmp_path, git_commit="f" * 40)


@pytest.mark.parametrize(
    ("field", "timestamp", "message"),
    [
        ("source_timestamp", "not-a-time", "Invalid UTC timestamp"),
        (
            "source_timestamp",
            "2024-09-15T23:16:01",
            "must include a UTC offset",
        ),
        ("generated_at", "not-a-time", "Invalid UTC timestamp"),
        (
            "generated_at",
            "2026-07-20T08:30:00",
            "must include a UTC offset",
        ),
    ],
)
def test_scenario_receipt_rejects_invalid_or_naive_timestamps(
    tmp_path: Path,
    field: str,
    timestamp: str,
    message: str,
) -> None:
    kwargs = {field: timestamp}
    with pytest.raises(ValueError, match=message):
        _write_scenario_receipt(tmp_path, **kwargs)


def test_scenario_receipt_bytes_are_deterministic_lf(tmp_path: Path) -> None:
    first = _write_scenario_receipt(tmp_path, output_name="first.json")
    second = _write_scenario_receipt(tmp_path, output_name="second.json")

    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()
    assert first.read_bytes().endswith(b"\n")


def test_committed_mae_sai_scenario_inputs_are_checksum_bound_and_path_safe() -> None:
    output_dir = REPO_ROOT / "outputs"
    manifest_path = output_dir / "mae_sai_scenario_inputs_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    receipt_sha256 = manifest.pop("receipt_sha256")
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == receipt_sha256
    assert manifest["study_area_id"] == "mae_sai_candidate_v1"
    assert manifest["dataset_mode"] == "candidate"
    assert manifest["operational_status"] == "non_operational"
    assert manifest["official_warning"] is False
    assert manifest["data_version"] == "mae-sai-candidate-2024-09-15-v1"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_commit"])
    assert manifest["processing_allowed"] is True
    assert manifest["can_feed_decision_layer"] is False
    assert manifest["reason_blocked"]
    assert manifest["source_licenses"] == [
        "Copernicus Sentinel data legal notice",
        "WorldPop CC BY 4.0",
        "OpenStreetMap ODbL 1.0",
    ]
    assert b"\r\n" not in manifest_path.read_bytes()

    rows_by_role = {
        "population_nodes": 13_620,
        "access_edges": 30_443,
        "facility_candidates": 42,
    }
    for artifact in manifest["artifacts"]:
        path = output_dir / artifact["relative_path"]
        assert path.parent == output_dir
        assert path.is_file()
        assert b"\r\n" not in path.read_bytes()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        frame = pd.read_csv(path)
        assert len(frame) == rows_by_role[artifact["role"]]
        assert list(frame.columns) == artifact["columns"]

    serialized = "\n".join(
        (output_dir / artifact["relative_path"]).read_text(encoding="utf-8")
        for artifact in manifest["artifacts"]
    )
    assert "C:\\Users\\" not in serialized
    assert "C:/Users/" not in serialized
    assert "FloodGuard_external_data" not in serialized
