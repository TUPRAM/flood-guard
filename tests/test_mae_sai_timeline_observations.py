"""Tests for the VIIRS and rain-gauge stages of the Mae Sai timeline bake."""

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
