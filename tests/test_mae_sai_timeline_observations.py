"""Tests for the VIIRS, Sentinel-2 water check and rain-gauge stages of the Mae Sai timeline bake."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import from_origin

SPEC = importlib.util.spec_from_file_location(
    "mae_sai_timeline_observations", Path(__file__).resolve().parents[1] / "scripts" / "mae_sai_timeline_observations.py"
)
obs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(obs)


def test_viirs_classes_split_cloud_clear_water_and_flood_fraction() -> None:
    codes = np.array([[30, 17, 99, 100, 150, 200, 0]], dtype=np.uint8)
    cls = obs.viirs_classes(codes)
    assert cls["cloud"].tolist() == [[True, False, False, False, False, False, False]]
    assert cls["clear"].tolist() == [[False, True, True, True, True, True, False]]  # 0 = no data, not clear.
    assert cls["water"].tolist() == [[False, False, True, False, False, False, False]]
    assert cls["flood_fraction"][0].tolist() == pytest.approx([0, 0, 0, 0, 0.5, 1.0, 0])


def test_viirs_display_bins() -> None:
    codes = np.array([30, 17, 99, 101, 124, 125, 150, 175, 200, 0], dtype=np.uint8)
    assert obs.viirs_png_codes(codes).tolist() == [1, 2, 3, 4, 4, 5, 6, 7, 7, 0]


def test_pixel_area_shrinks_with_latitude() -> None:
    transform = from_origin(99.0, 21.0, 0.003372, 0.003372)
    area = obs.pixel_area_km2(transform, (2, 1))
    assert area[0, 0] == pytest.approx(0.003372 * 111.32 * np.cos(np.radians(21.0 - 0.001686)) * 0.003372 * 110.57, rel=1e-6)
    assert 0.13 < area[0, 0] < 0.14  # About 375 m x 375 m.


def test_rainfall_parses_hours_skips_repeated_headers_and_reads_metadata(tmp_path: Path) -> None:
    (tmp_path / "MOU189.csv").write_text(
        "station_code,measure_datetime,rainfall_1h,quality_flag\n"
        "MOU189,2024-09-08 23:00:00,5,N\n"  # Before the replay: ignored.
        "MOU189,2024-09-09 00:00:00,1.5,N\n"
        "station_code,measure_datetime,rainfall_1h,quality_flag\n"  # Repeated header mid-file.
        "MOU189,2024-09-10 12:00:00,20,N\n",
        encoding="utf-8",
    )
    (tmp_path / "mou_0all_stn_metadata.csv").write_text(
        "﻿Station_Code,Station_Name,Latitude,Longitude\nMOU189,x,20.38133,99.86719\n", encoding="utf-8"
    )
    rain = obs.rainfall(tmp_path, 48)
    [station] = rain["stations"]
    assert station["code"] == "MOU189" and station["lat"] == pytest.approx(20.38133)
    series = rain["hourly_mm"]["MOU189"]
    assert len(series) == 48 and series[0] == 1.5
    assert series[36] == 20  # 10 Sep 12:00 ICT is hour 36.
    assert series[1] is None
    assert station["total_mm"] == pytest.approx(21.5)
    assert station["max_hour_mm"] == 20
    assert station["missing_hours"] == 46


# --- Sentinel-2 water check (MNDWI on clear pixels) -----------------------------------------------------------

S2_BOUNDS = (500000.0, 2000000.0, 500800.0, 2000800.0)  # 40 x 40 cells of 20 m; the replay grid is 80 x 80 cells of 10 m.
S2_MARGIN = 40.0  # The files reach 40 m past the replay area on every side, as a real tile does.


def write_band(path: Path, inner: np.ndarray, res: float, margin_value: int) -> None:
    """Write a uint16 GeoTIFF whose centre is ``inner`` and whose margin holds ``margin_value``."""
    import rasterio

    pad = int(S2_MARGIN / res)
    data = np.full((inner.shape[0] + 2 * pad, inner.shape[1] + 2 * pad), margin_value, dtype=np.uint16)
    data[pad:-pad, pad:-pad] = inner
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1, dtype="uint16", crs="EPSG:32647",
                       transform=from_origin(S2_BOUNDS[0] - S2_MARGIN, S2_BOUNDS[3] + S2_MARGIN, res, res), nodata=0) as dst:
        dst.write(data, 1)


def write_scene(folder: Path, green20: np.ndarray, swir20: np.ndarray, scl20: np.ndarray) -> None:
    """A scene whose 10 m green band varies inside every 20 m cell (-100, +100, +100, -100) around ``green20``."""
    green10 = np.repeat(np.repeat(green20, 2, axis=0), 2, axis=1).astype(np.int32)
    green10[0::2, 0::2] -= 100
    green10[1::2, 1::2] -= 100
    green10[0::2, 1::2] += 100
    green10[1::2, 0::2] += 100
    write_band(folder / "green.tif", green10, 10.0, 9000)
    write_band(folder / "swir16.tif", swir20, 20.0, 9000)
    write_band(folder / "scl.tif", scl20, 20.0, 9)


@pytest.fixture()
def s2_scenes(tmp_path: Path) -> tuple[Path, Path]:
    dry_green, dry_swir, wet_green, wet_swir = 600, 2000, 1400, 300
    # 15 Sep: cloud over rows 0-9, unclassified in rows 10-11; columns 0-14 strongly wet, 15-19 weakly wet (index 0.048).
    green = np.full((40, 40), dry_green)
    swir = np.full((40, 40), dry_swir)
    scl = np.full((40, 40), 4)
    green[10:, :15], swir[10:, :15], scl[12:, :20] = wet_green, wet_swir, 6
    green[10:, 15:20], swir[10:, 15:20] = 1100, 1000
    scl[:10], scl[10:12] = 9, 7
    write_scene(tmp_path / "event", green, swir, scl)
    # 5 Sep: clear except a cloud shadow in the lower right; columns 0-4 wet.
    green = np.full((40, 40), dry_green)
    swir = np.full((40, 40), dry_swir)
    scl = np.full((40, 40), 4)
    green[:, :5], swir[:, :5], scl[:, :5] = wet_green, wet_swir, 6
    scl[30:, 30:] = 3
    write_scene(tmp_path / "pre", green, swir, scl)
    return tmp_path / "pre", tmp_path / "event"


def test_sentinel2_bands_are_read_onto_the_20m_grid_with_green_averaged(s2_scenes: tuple[Path, Path]) -> None:
    _, event = s2_scenes
    transform = from_origin(S2_BOUNDS[0], S2_BOUNDS[3], 20.0, 20.0)
    surface, scl = obs.sentinel2_wet_surface(event, "EPSG:32647", transform, (40, 40))
    green = obs.sentinel2_band(event / "green.tif", "EPSG:32647", transform, (40, 40), obs.Resampling.average)
    # The 2 x 2 mean removes the +/-100 pattern; nothing from the margin (9000) leaks in.
    assert green[20, 0] == pytest.approx(1400) and green[20, 17] == pytest.approx(1100) and green[20, 30] == pytest.approx(600)
    assert green.max() < 2000 and scl.dtype == np.uint8 and scl[0, 0] == 9 and scl[10, 0] == 7 and scl[20, 0] == 6 and scl[20, 30] == 4
    assert surface.index[20, 0] == pytest.approx((1400 - 300) / 1700) and surface.index[20, 17] == pytest.approx(100 / 2100)
    assert surface.index[20, 30] == pytest.approx((600 - 2000) / 2600)
    assert not surface.clear[:10].any() and surface.clear[10:].all()
    assert surface.wet[10:, :20].all() and not surface.wet[:, 20:].any() and not surface.wet[:10].any()


def test_sentinel2_water_check_counts_clear_water_new_water_and_the_model_overlap(s2_scenes: tuple[Path, Path]) -> None:
    pre, event = s2_scenes
    district = np.ones((80, 80), dtype=bool)
    district[76:] = False  # The last two 20 m rows lie outside the district.
    permanent = np.zeros((80, 80), dtype=bool)
    permanent[:, :2] = True  # One 20 m column of mapped channel.
    model = np.zeros((80, 80), dtype=bool)
    model[40:, 20:60] = True  # 20 m rows 20-39, columns 10-29.
    opened: list[str] = []

    def track(path: Path) -> Path:
        opened.append(f"{path.parent.name}/{path.name}")
        return path

    out = obs.sentinel2_water_check(pre, event, "EPSG:32647", S2_BOUNDS, district, permanent, model, 10.0, track)
    assert sorted(opened) == ["event/green.tif", "event/scl.tif", "event/swir16.tif", "pre/green.tif", "pre/scl.tif", "pre/swir16.tif"]
    assert (out["resolution_m"], out["threshold"], out["district_km2"], out["permanent_water_km2"]) == (20.0, 0.0, 0.61, 0.02)
    # 15 Sep: 28 clear rows of 40 cells in the district; wet columns 1-19 (column 0 is channel).
    assert out["scenes"]["event"] == {"clear_km2": 0.45, "clear_share": 0.737, "water_km2": 0.21, "scl_class_km2": {
        "vegetation": 0.21, "water": 0.21, "unclassified": 0.03, "cloud_high_probability": 0.16}}
    # 5 Sep: everything but the shadow block is clear; wet columns 1-4.
    assert out["scenes"]["pre_event"]["clear_share"] == 0.947 and out["scenes"]["pre_event"]["water_km2"] == 0.06
    assert out["scenes"]["pre_event"]["scl_class_km2"]["cloud_shadow"] == 0.03
    # New water needs both dates clear: columns 5-19 of the 28 rows clear on 15 Sep.
    assert out["change"] == {"both_clear_km2": 0.4, "event_water_km2": 0.21, "pre_event_water_km2": 0.04, "new_water_km2": 0.17, "no_longer_water_km2": 0.0}
    # The model (360 cells in the district, all of them clear) overlaps the observed area in 180 cells of 712.
    assert out["model_at_event_scene"] == {
        "model_flood_km2_district": 0.14, "model_flood_km2_clear": 0.14, "model_overlap_km2": 0.07, "model_union_km2": 0.28,
        "model_agreement_iou": 0.253, "model_share_of_observed_water_reached": 0.338, "model_share_inside_observed_water": 0.5}
    strict, loose, looser = out["sensitivity"]
    assert [row["id"] for row in out["sensitivity"]] == ["strict_clear", "threshold_0_1", "threshold_0_2"]
    # Dropping the unclassified rows 10-11 leaves 26 clear rows.
    assert (strict["event_clear_share"], strict["event_water_km2"], strict["new_water_km2"], strict["model_agreement_iou"]) == (0.684, 0.2, 0.16, 0.267)
    assert (strict["pre_event_clear_share"], strict["pre_event_water_km2"]) == (0.947, 0.06)
    # A threshold of 0.1 drops the weakly wet columns 15-19 (index 0.048) on 15 Sep and nothing on 5 Sep.
    assert (loose["event_clear_share"], loose["event_water_km2"], loose["pre_event_water_km2"], loose["new_water_km2"], loose["model_agreement_iou"]) == (
        0.737, 0.16, 0.06, 0.11, 0.136)
    figures = lambda row: {key: value for key, value in row.items() if key not in ("id", "rule")}  # noqa: E731
    assert figures(looser) == figures(loose) and "0.2" in looser["rule"] and "0.1" in loose["rule"]
    # Model output sits only where the bake names it as model output.
    assert all(key.startswith("model_") for key in out["model_at_event_scene"])
    assert not any(key.startswith("model_") for key in out["change"])
    assert not any(key.startswith("model_") for scene in out["scenes"].values() for key in scene)


def test_sentinel2_water_check_refuses_a_grid_that_does_not_nest(s2_scenes: tuple[Path, Path]) -> None:
    pre, event = s2_scenes
    with pytest.raises(ValueError, match="nest"):
        obs.sentinel2_water_check(pre, event, "EPSG:32647", S2_BOUNDS, np.ones((81, 80), bool), np.zeros((81, 80), bool), np.zeros((81, 80), bool), 10.0)
    with pytest.raises(ValueError, match="nest"):
        obs.sentinel2_water_check(pre, event, "EPSG:32647", S2_BOUNDS, np.ones((80, 80), bool), np.zeros((80, 80), bool), np.zeros((80, 80), bool), 15.0)
    with pytest.raises(ValueError, match="nest"):  # A replay grid coarser than the Sentinel-2 grid.
        obs.sentinel2_water_check(pre, event, "EPSG:32647", S2_BOUNDS, np.ones((20, 20), bool), np.zeros((20, 20), bool), np.zeros((20, 20), bool), 40.0)
