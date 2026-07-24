"""Network-free tests for the real GeoAI pipeline (no training, no fetch).

These exercise the pure numpy/rasterio components on a deterministic synthetic
scene. Modules that need optional deps (pandas, scikit-learn) are guarded so the
suite still runs in the runner's base test environment.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("rasterio")

from geoai_runner.realpipeline import infrastructure, sar_flood, susceptibility
from geoai_runner.realpipeline.raster_io import write_geotiff
from geoai_runner.realpipeline.registry import COMPONENTS, component_by_key, mvp_components
from geoai_runner.realpipeline.synth import build_scene, subdistrict_features


@pytest.fixture(scope="module")
def scene():
    return build_scene()


@pytest.fixture(scope="module")
def scene_dir(scene, tmp_path_factory):
    d = tmp_path_factory.mktemp("scene")
    tr, crs = scene.grid.transform, scene.grid.crs
    write_geotiff(d / "pre_vv.tif", scene.sar_pre_vv, tr, crs)
    write_geotiff(d / "pre_vh.tif", scene.sar_pre_vh, tr, crs)
    write_geotiff(d / "post_vv.tif", scene.sar_post_vv, tr, crs)
    write_geotiff(d / "post_vh.tif", scene.sar_post_vh, tr, crs)
    write_geotiff(d / "perm.tif", scene.permanent_water, tr, crs, dtype="uint8")
    write_geotiff(d / "floodref.tif", scene.flood_reference, tr, crs, dtype="uint8")
    write_geotiff(d / "s2.tif", scene.s2, tr, crs)
    write_geotiff(d / "hand.tif", scene.hand, tr, crs)
    write_geotiff(d / "slope.tif", scene.slope, tr, crs)
    write_geotiff(d / "dist.tif", scene.dist_to_river, tr, crs)
    write_geotiff(d / "twi.tif", scene.twi, tr, crs)
    return d


def test_scene_is_coherent(scene):
    assert scene.dem.shape == (256, 256)
    assert 0.01 < float(scene.flood_reference.mean()) < 0.3
    w = scene.flood_reference.astype(bool)
    assert scene.sar_post_vh[w].mean() < scene.sar_post_vh[~w].mean()


def test_sar_change_detection_recovers_flood(scene_dir, tmp_path):
    res = sar_flood.detect_sar_flood_extent(
        scene_dir / "pre_vv.tif", scene_dir / "pre_vh.tif",
        scene_dir / "post_vv.tif", scene_dir / "post_vh.tif", tmp_path / "a",
        permanent_water_path=scene_dir / "perm.tif",
        reference_flood_path=scene_dir / "floodref.tif",
    )
    assert res.metrics["iou"] > 0.4
    assert res.artifacts["flood_binary"].exists()


def test_susceptibility_separates_flood(scene_dir, tmp_path):
    res = susceptibility.compute_susceptibility_index(
        scene_dir / "hand.tif", scene_dir / "slope.tif",
        scene_dir / "dist.tif", scene_dir / "twi.tif", tmp_path / "c",
        reference_flood_path=scene_dir / "floodref.tif",
    )
    assert res.metrics["auc"] > 0.7
    assert 0 <= res.susceptibility_0_100.min() <= res.susceptibility_0_100.max() <= 100


def test_building_extraction(scene_dir, tmp_path):
    res = infrastructure.extract_buildings_classical(scene_dir / "s2.tif", tmp_path / "d")
    assert res.metrics["building_count"] > 5
    fc = json.loads(res.artifacts["footprints"].read_text(encoding="utf-8"))
    assert all("area_m2" in f["properties"] for f in fc["features"])


def test_sam_path_reports_offline(scene_dir, tmp_path):
    with pytest.raises(infrastructure.SAMUnavailableError):
        infrastructure.extract_buildings_sam(scene_dir / "s2.tif", [], tmp_path / "sam")


def test_registry_integrity():
    assert len({c.key for c in COMPONENTS}) == len(COMPONENTS)
    assert len(mvp_components()) == 4
    assert component_by_key("sar_flood").letter == "A"


def test_aggregate_feeds_root_scoring(scene_dir, scene, tmp_path):
    pytest.importorskip("pandas")
    from floodguard.scoring import score_subdistricts

    from geoai_runner.realpipeline import aggregate

    sar = sar_flood.detect_sar_flood_extent(
        scene_dir / "pre_vv.tif", scene_dir / "pre_vh.tif",
        scene_dir / "post_vv.tif", scene_dir / "post_vh.tif", tmp_path / "a",
        permanent_water_path=scene_dir / "perm.tif",
    )
    susc = susceptibility.compute_susceptibility_index(
        scene_dir / "hand.tif", scene_dir / "slope.tif",
        scene_dir / "dist.tif", scene_dir / "twi.tif", tmp_path / "c",
    )
    bld = infrastructure.extract_buildings_classical(
        scene_dir / "s2.tif", tmp_path / "d", flood_extent_path=sar.artifacts["flood_binary"],
    )
    feats = subdistrict_features(scene.grid)
    ai = aggregate.aggregate_subdistrict_ai_inputs(
        feats, sar.artifacts["flood_probability"], susc.artifacts["susceptibility"],
        bld.artifacts["footprints"],
    )
    scored = score_subdistricts(aggregate.build_fpps_input_table(ai))
    assert scored["action_class"].isin(list("ABCDE")).all()
