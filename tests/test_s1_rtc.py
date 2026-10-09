"""Tests of the Sentinel-1 window reader on local rasters: no network is used."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodguard import s1_rtc

rasterio = pytest.importorskip("rasterio")
EPSG, CELL = 32647, 10.0


def write_scene(path: Path, values: np.ndarray, west: float, north: float) -> None:
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1, dtype="float32",
                       nodata=float("nan"), crs=f"EPSG:{EPSG}", transform=from_origin(west, north, CELL, CELL)) as target:
        target.write(values.astype("float32"), 1)


def test_parallel_read_equals_a_plain_read_and_pads_outside_the_raster(tmp_path: Path) -> None:
    values = np.arange(40 * 30, dtype="float32").reshape(40, 30) + 1
    write_scene(tmp_path / "scene.tif", values, west=1000.0, north=5000.0)
    # A grid that starts 5 cells left of and 3 cells above the raster and ends inside it.
    grid = (1000.0 - 5 * CELL, 5000.0 + 3 * CELL, 20, 25)
    window = s1_rtc.read_window_parallel(str(tmp_path / "scene.tif"), grid, epsg=EPSG, cell_m=CELL, threads=4, strip_rows=7)
    assert window.shape == (20, 25) and window.dtype == np.float32
    assert np.isnan(window[:3]).all() and np.isnan(window[:, :5]).all()
    assert np.array_equal(window[3:, 5:], values[:17, :20])
    with pytest.raises(s1_rtc.S1RtcError):
        s1_rtc.read_window_parallel(str(tmp_path / "scene.tif"), (1003.0, 5000.0, 4, 4), epsg=EPSG, cell_m=CELL)
    with pytest.raises(s1_rtc.S1RtcError):
        s1_rtc.read_window_parallel(str(tmp_path / "scene.tif"), grid, epsg=32648, cell_m=CELL)


def test_fetch_pass_mosaics_in_order_reads_a_later_scene_only_for_gaps_and_caches(tmp_path: Path) -> None:
    north_part = np.full((10, 10), 0.2, dtype="float32")
    north_part[6:] = np.nan  # the first scene ends after six rows
    north_part[0, 0] = -1.0  # not a valid backscatter
    south_part = np.full((10, 10), 0.5, dtype="float32")
    for name, values in (("a_vv", north_part), ("a_vh", north_part * 2), ("b_vv", south_part), ("b_vh", south_part * 2)):
        write_scene(tmp_path / f"{name}.tif", values, west=0.0, north=100.0)
    asked: list[str] = []

    def resolve(item_id: str) -> dict[str, object]:
        asked.append(item_id)
        return {"datetime": f"2024-01-0{len(asked)}T00:00:00Z", "platform": "test", "relative_orbit": 1, "orbit_state": "descending",
                "assets": {"vv": str(tmp_path / f"{item_id}_vv.tif"), "vh": str(tmp_path / f"{item_id}_vh.tif")}}

    grid = (0.0, 100.0, 10, 10)
    record = s1_rtc.fetch_pass(tmp_path, grid, ("a", "b"), "pass", epsg=EPSG, cell_m=CELL, resolve=resolve, threads=2)
    assert asked == ["a", "b"] and [source["item"] for source in record["sources"]] == ["a", "b"]
    with rasterio.open(tmp_path / record["window_file"]) as cached:
        image = cached.read()
    assert image.shape == (2, 10, 10)
    assert np.allclose(image[0, 1:6], 0.2) and np.allclose(image[0, 6:], 0.5) and image[0, 0, 0] == pytest.approx(0.5)
    assert np.allclose(image[1, 1:6], 0.4) and record["valid_share"] == 1.0
    assert record["window_sha256"] == s1_rtc.sha256_file(tmp_path / "pass.tif")
    # A second call reads the cache and asks nobody.
    again = s1_rtc.fetch_pass(tmp_path, grid, ("a", "b"), "pass", epsg=EPSG, cell_m=CELL, resolve=resolve)
    assert asked == ["a", "b"] and again["window_sha256"] == record["window_sha256"]
    # A first scene without gaps makes the second one unnecessary.
    asked.clear()
    s1_rtc.fetch_pass(tmp_path, grid, ("b", "a"), "full", epsg=EPSG, cell_m=CELL, resolve=resolve)
    assert asked == ["b"]
    with pytest.raises(s1_rtc.S1RtcError):
        s1_rtc.fetch_pass(tmp_path, grid, (), "none", epsg=EPSG, cell_m=CELL, resolve=resolve)


def test_median_of_passes_is_taken_in_db_over_the_passes_that_saw_the_cell(tmp_path: Path) -> None:
    grid = (0.0, 30.0, 3, 3)
    levels = (0.01, 0.1, 1.0)  # -20, -10 and 0 dB
    paths = []
    for index, level in enumerate(levels):
        image = np.full((2, 3, 3), level, dtype="float32")
        if index == 0:
            image[:, 0, 0] = np.nan  # seen by two passes only
        image[:, 2, 2] = np.nan  # seen by none
        if index > 0:
            image[:, 1, 1] = np.nan  # seen by the first pass only
        path = tmp_path / f"pass_{index}.tif"
        s1_rtc.write_window(path, list(image), grid, epsg=EPSG, cell_m=CELL)
        paths.append(path)
    median, spread = s1_rtc.median_of_passes(paths, strip_rows=2)
    assert median.shape == (2, 3, 3) and median[0, 0, 1] == pytest.approx(-10.0, abs=1e-4)
    assert median[0, 0, 0] == pytest.approx(-5.0, abs=1e-4) and spread[0, 0, 0] == pytest.approx(5.0, abs=1e-4)
    assert median[0, 1, 1] == pytest.approx(-20.0, abs=1e-4) and spread[0, 1, 1] == pytest.approx(0.0, abs=1e-6)
    assert np.isnan(median[:, 2, 2]).all() and np.isnan(spread[:, 2, 2]).all()
    assert spread[1, 0, 1] == pytest.approx(np.std([-20.0, -10.0, 0.0]), abs=1e-4)
    with pytest.raises(s1_rtc.S1RtcError):
        s1_rtc.median_of_passes([])
