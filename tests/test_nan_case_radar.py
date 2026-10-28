"""Tests of the radar lane of the Nan case on invented data: no network is used.

Pass grouping, the latest-first selection with its cap, the 20 m cell rule (mean of linear gamma0 over at least
3 valid 10 m cells), the streaming dry-season statistics in dB against numpy, the sensor difference, and the
reading of a pass from local rasters, aligned and warped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nan_case_radar.py"


def _script() -> Any:
    if "nan_case_radar" in sys.modules:
        return sys.modules["nan_case_radar"]
    spec = importlib.util.spec_from_file_location("nan_case_radar", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["nan_case_radar"] = module
    spec.loader.exec_module(module)
    return module


radar = _script()


def scene(item: str, platform: str, orbit: int, start: str, seconds: int = 25) -> dict[str, Any]:
    begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return {"item": item, "platform": platform, "relative_orbit": orbit, "orbit_state": "descending",
            "start_utc": start, "end_utc": (begin + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")}


# ---------------------------------------------------------------------------
# Passes and their selection
# ---------------------------------------------------------------------------


def test_scenes_group_into_passes_by_platform_orbit_and_start_time() -> None:
    scenes = [
        scene("a2", "SENTINEL-1A", 62, "2025-07-31T23:08:28Z"),
        scene("a1", "sentinel-1a", 62, "2025-07-31T23:08:03Z"),
        scene("c1", "sentinel-1c", 62, "2025-07-31T23:08:10Z"),  # same time, other platform: another pass
        scene("a3", "sentinel-1a", 62, "2025-08-12T23:08:03Z"),  # same orbit twelve days later
        scene("a4", "sentinel-1a", 99, "2025-07-31T23:09:00Z"),  # other orbit
        scene("a1", "sentinel-1a", 62, "2025-07-31T23:08:03Z"),  # the same scene twice is kept once
    ]
    passes = radar.group_passes(scenes)
    assert [entry["key"] for entry in passes] == ["20250731T2308Z_s1a_o62", "20250731T2308Z_s1c_o62",
                                                 "20250731T2309Z_s1a_o99", "20250812T2308Z_s1a_o62"]
    first = passes[0]
    assert [member["item"] for member in first["scenes"]] == ["a1", "a2"]
    assert first["platform"] == "Sentinel-1A" and first["relative_orbit"] == 62
    assert first["start_utc"] == "2025-07-31T23:08:03Z" and first["end_utc"] == "2025-07-31T23:08:53Z"
    assert first["start_thai"] == "2025-08-01T06:08:03+07:00"
    # A scene 301 s after the previous one starts a new pass; within 300 s it joins.
    split = radar.group_passes([scene("x", "sentinel-1a", 62, "2025-01-01T00:00:00Z"),
                                scene("y", "sentinel-1a", 62, "2025-01-01T00:05:01Z")])
    joined = radar.group_passes([scene("x", "sentinel-1a", 62, "2025-01-01T00:00:00Z"),
                                 scene("y", "sentinel-1a", 62, "2025-01-01T00:05:00Z")])
    assert len(split) == 2 and len(joined) == 1


def test_catalogue_times_of_both_formats_parse_to_utc() -> None:
    assert radar.parse_utc("2025-01-08 23:08:37.411549+00:00") == datetime(2025, 1, 8, 23, 8, 37, 411549, tzinfo=timezone.utc)
    assert radar.parse_utc("2025-07-16T11:20:48.993968Z").hour == 11
    assert radar.platform_name("SENTINEL-1B") == "Sentinel-1B" and radar.platform_code("Sentinel-1C") == "s1c"
    with pytest.raises(radar.RadarCaseError):
        radar.platform_name("landsat-8")


def test_dry_passes_are_taken_latest_first_up_to_the_cap() -> None:
    days = [datetime(2025, 1, 1, 23, 8, tzinfo=timezone.utc) + timedelta(days=6 * index) for index in range(12)]
    passes = radar.group_passes([scene(f"s{index}", "sentinel-1a" if index % 3 else "sentinel-1c", 62,
                                       day.strftime("%Y-%m-%dT%H:%M:%SZ")) for index, day in enumerate(days)])
    passes += radar.group_passes([scene("other", "sentinel-1a", 99, "2025-04-30T11:22:00Z")])
    chosen = radar.select_latest(passes, cap=10, relative_orbit=62)
    assert len(chosen) == 10
    assert [entry["scenes"][0]["item"] for entry in chosen] == [f"s{index}" for index in range(11, 1, -1)]
    assert all(entry["relative_orbit"] == 62 for entry in chosen)
    assert len(radar.select_latest(passes[:4], cap=10)) == 4  # fewer than the cap: all of them
    window = radar.passes_starting_between(passes, datetime(2025, 2, 1, tzinfo=timezone.utc),
                                           datetime(2025, 2, 28, 23, 59, 59, tzinfo=timezone.utc))
    assert [entry["start_utc"][:10] for entry in window] == ["2025-02-06", "2025-02-12", "2025-02-18", "2025-02-24"]
    with pytest.raises(radar.RadarCaseError):
        radar.select_latest(passes, cap=-1)


def test_the_named_tuning_pass_is_matched_by_platform_orbit_and_time() -> None:
    passes = radar.group_passes([scene("b", "SENTINEL-1B", 164, "2021-09-27T23:00:11Z"),
                                 scene("a", "SENTINEL-1A", 164, "2021-09-27T23:00:40Z")])
    when = datetime(2021, 9, 27, 23, 0, tzinfo=timezone.utc)
    matched = radar.match_named_pass(passes, platform="Sentinel-1B", relative_orbit=164, when=when)
    assert [entry["key"] for entry in matched] == ["20210927T2300Z_s1b_o164"]
    assert radar.match_named_pass(passes, platform="Sentinel-1B", relative_orbit=164, when=when + timedelta(hours=1)) == []


# ---------------------------------------------------------------------------
# The 20 m cell and the dry-season statistics
# ---------------------------------------------------------------------------


def test_the_20m_cell_is_the_mean_of_at_least_three_valid_10m_cells() -> None:
    fine = np.array([
        [0.1, 0.3, 0.2, np.nan, 0.5, 0.0],
        [0.2, 0.4, 0.4, 0.6, np.nan, -1.0],
        [np.nan, np.nan, 1.0, 1.0, np.inf, 0.2],
        [np.nan, 0.8, 1.0, 1.0, 0.4, 0.6],
    ], dtype="float32")
    coarse = radar.block_mean_2x2(fine)
    assert coarse.shape == (2, 3) and coarse.dtype == np.float32
    assert coarse[0, 0] == pytest.approx(0.25)  # four valid cells
    assert coarse[0, 1] == pytest.approx(0.4)  # three valid cells: (0.2 + 0.4 + 0.6) / 3
    assert np.isnan(coarse[0, 2])  # 0.5 only: zero and negative values are not valid
    assert np.isnan(coarse[1, 0])  # one valid cell
    assert coarse[1, 1] == pytest.approx(1.0)
    assert coarse[1, 2] == pytest.approx(0.4)  # infinity is not valid: (0.2 + 0.4 + 0.6) / 3
    # The mean is taken on linear values, not on dB.
    assert radar.block_mean_2x2(np.array([[0.01, 1.0], [1.0, 1.0]]))[0, 0] == pytest.approx(0.7525)
    assert np.isnan(radar.block_mean_2x2(np.array([[0.1, 0.1], [0.1, np.nan]]), min_valid=4)[0, 0])
    with pytest.raises(radar.RadarCaseError):
        radar.block_mean_2x2(np.ones((3, 4)))


def invented_dry_season(seed: int = 4) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Seven passes of linear VH and VV on a 9 by 7 grid with gaps, from two platforms."""

    generator = np.random.default_rng(seed)
    vh = generator.uniform(0.002, 0.08, size=(7, 9, 7))
    vv = generator.uniform(0.01, 0.4, size=(7, 9, 7))
    vh[generator.random(vh.shape) < 0.2] = np.nan
    vv[generator.random(vv.shape) < 0.1] = np.nan
    vv[2, 0, 0] = 0.0  # not a valid value
    vh[:, 8, 6] = np.nan  # a cell no pass saw
    platforms = ["Sentinel-1A", "Sentinel-1C", "Sentinel-1A", "Sentinel-1A", "Sentinel-1C", "Sentinel-1A", "Sentinel-1A"]
    return vh, vv, platforms


def numpy_reference(vh: np.ndarray, vv: np.ndarray, keep: np.ndarray) -> dict[str, np.ndarray]:
    with np.errstate(invalid="ignore", divide="ignore"):
        vh_db = np.where(np.isfinite(vh) & (vh > 0), 10 * np.log10(vh), np.nan)
        vv_db = np.where(np.isfinite(vv) & (vv > 0), 10 * np.log10(vv), np.nan)
    both = np.isfinite(vh_db) & np.isfinite(vv_db) & keep[:, None, None]
    vh_db, vv_db = np.where(both, vh_db, np.nan), np.where(both, vv_db, np.nan)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return {"n_valid": both.sum(axis=0), "vh_mean_db": np.nanmean(vh_db, axis=0), "vh_std_db": np.nanstd(vh_db, axis=0),
                "vv_mean_db": np.nanmean(vv_db, axis=0), "vv_std_db": np.nanstd(vv_db, axis=0)}


@pytest.mark.parametrize("on_disk", [False, True])
def test_streaming_mean_and_population_std_in_db_equal_numpy(tmp_path: Path, on_disk: bool) -> None:
    vh, vv, platforms = invented_dry_season()
    accumulator = radar.DryAccumulator((9, 7), platforms, folder=tmp_path / "acc" if on_disk else None)
    for index in range(len(platforms)):
        for top in range(0, 9, 4):  # added in strips of rows, as the script reads a pass
            accumulator.add(platforms[index], vh[index, top:top + 4], vv[index, top:top + 4], row0=top)
    stats = accumulator.statistics()
    expected = numpy_reference(vh, vv, np.ones(len(platforms), dtype=bool))
    assert np.array_equal(stats["n_valid"], expected["n_valid"])
    for band in ("vh_mean_db", "vh_std_db", "vv_mean_db", "vv_std_db"):
        assert np.array_equal(np.isnan(stats[band]), np.isnan(expected[band]))
        assert np.allclose(stats[band], expected[band], atol=1e-9, equal_nan=True)
    assert stats["n_valid"][8, 6] == 0 and np.isnan(stats["vh_mean_db"][8, 6])
    # One platform alone.
    alone = accumulator.statistics(platforms=["Sentinel-1C"])
    only_c = numpy_reference(vh, vv, np.array([name == "Sentinel-1C" for name in platforms]))
    assert np.allclose(alone["vh_mean_db"], only_c["vh_mean_db"], atol=1e-9, equal_nan=True)
    # A strip of rows gives the same values as the whole.
    assert np.allclose(accumulator.statistics(2, 5)["vv_std_db"], stats["vv_std_db"][2:5], equal_nan=True)
    with pytest.raises(radar.RadarCaseError):
        accumulator.add("Sentinel-1A", vh[0, :4], vv[0, :4], row0=7)
    if on_disk:
        accumulator.close()
        resumed = radar.DryAccumulator((9, 7), platforms, folder=tmp_path / "acc", resume=True)
        assert np.allclose(resumed.statistics()["vh_mean_db"], stats["vh_mean_db"], equal_nan=True)
        resumed.close()


def test_sensor_difference_is_the_median_over_cells_valid_in_both() -> None:
    first = np.array([[-20.0, -18.0, np.nan], [-15.0, -21.0, -19.0]])
    second = np.array([[-20.6, -18.4, -17.0], [np.nan, -21.9, -19.7]])
    result = radar.sensor_difference(first, second)
    assert result["cells_valid_in_both"] == 4
    assert result["median_db"] == pytest.approx(0.65)  # differences 0.6, 0.4, 0.9, 0.7
    assert result["flagged"] is True and result["flag_abs_median_above_db"] == 0.5
    small = radar.sensor_difference(first, first + 0.3)
    assert small["median_db"] == pytest.approx(-0.3) and small["flagged"] is False
    assert radar.sensor_difference(first, first - 0.5)["flagged"] is False  # 0.5 is not above 0.5
    empty = radar.sensor_difference(np.array([np.nan]), np.array([1.0]))
    assert empty["cells_valid_in_both"] == 0 and empty["flagged"] is None


def test_tasks_cover_the_grid_with_even_edges() -> None:
    tasks = radar.read_tasks(8606, 8560, 12)
    assert len(tasks) == 12
    covered = np.zeros((8606, 8560), dtype="uint8")
    for r0, r1, c0, c1 in tasks:
        assert r0 % 2 == r1 % 2 == c0 % 2 == c1 % 2 == 0
        covered[r0:r1, c0:c1] += 1
    assert (covered == 1).all()
    assert radar.read_tasks(302, 302, 12) == [(0, 302, 0, 302)]
    assert len(radar.read_tasks(4096, 3072, 12)) == 12  # six column blocks by two row groups
    with pytest.raises(radar.RadarCaseError):
        radar.column_blocks(7, 2)


def test_paths_inside_the_sealed_folder_are_refused(tmp_path: Path) -> None:
    with pytest.raises(radar.RadarCaseError):
        radar.guard_path(tmp_path / "nan_case_v1" / "jaxa_sealed" / "x.tif")
    assert radar.guard_path(tmp_path / "nan_case_v1" / "radar") == tmp_path / "nan_case_v1" / "radar"


# ---------------------------------------------------------------------------
# Reading a pass from local rasters
# ---------------------------------------------------------------------------


def write_scene(path: Path, values: np.ndarray, west: float, north: float, epsg: int = 32647) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1, dtype="float32",
                       nodata=-32768.0, crs=f"EPSG:{epsg}", transform=from_origin(west, north, 10.0, 10.0)) as target:
        target.write(values.astype("float32"), 1)


def local_resolver(folder: Path, asked: list[str]) -> Any:
    def resolve(item_id: str) -> dict[str, Any]:
        asked.append(item_id)
        return {"datetime": "2025-01-01T00:00:00Z", "platform": "sentinel-1a", "relative_orbit": 62, "orbit_state": "descending",
                "assets": {"vv": str(folder / f"{item_id}_vv.tif"), "vh": str(folder / f"{item_id}_vh.tif")}}

    return resolve


def test_a_pass_is_mosaicked_at_10m_then_averaged_to_20m(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    # The 20 m grid: 6 rows by 5 columns from (1000, 5000); its 10 m lattice is 12 by 10.
    grid = (1000.0, 5000.0, 6, 5)
    # Scene a starts two 10 m rows above and two columns left of the grid: it covers grid rows 0-6.
    north_values = np.full((9, 14), 0.2, dtype="float32")
    north_values[3, 2] = -32768.0  # grid row 1, column 0: no data, and scene b does not reach it
    north_values[7, 2] = -32768.0  # grid row 5, column 0: no data, filled from scene b
    # Scene b covers grid rows 5-11.
    south_values = np.full((10, 14), 0.6, dtype="float32")
    for name, values, top in (("a", north_values, 5020.0), ("b", south_values, 4950.0)):
        write_scene(tmp_path / f"{name}_vv.tif", values, 980.0, top)
        write_scene(tmp_path / f"{name}_vh.tif", np.where(values > 0, values / 4, values), 980.0, top)
    asked: list[str] = []
    image, details = radar.read_pass_20m(grid, ["a", "b"], resolve=local_resolver(tmp_path, asked), threads=4)
    assert image.shape == (2, 6, 5) and image.dtype == np.float32
    assert [entry["read_method"] for entry in details["scenes"]] == ["aligned", "aligned"]
    expected = np.full((6, 5), 0.2)
    expected[2, 0] = (3 * 0.2 + 0.6) / 4  # the gap of scene a took scene b's value before the mean
    expected[3] = 0.4  # one 10 m row of each scene
    expected[4:] = 0.6
    assert np.allclose(image[0], expected) and np.allclose(image[1], expected / 4)
    # Cell (0, 0) holds three valid 10 m cells: it keeps a value.
    assert np.isfinite(image[:, 0, 0]).all()
    write_dir = tmp_path / "out"
    entry = {"key": "20250101T0000Z_s1a_o62", "platform": "Sentinel-1A", "relative_orbit": 62, "orbit_state": "descending",
             "start_utc": "2025-01-01T00:00:00Z", "end_utc": "2025-01-01T00:00:25Z", "start_thai": "2025-01-01T07:00:00+07:00",
             "scenes": [{"item": "a"}, {"item": "b"}]}
    record = radar.fetch_pass_file(write_dir, "test_area", grid, entry, "event_x", resolve=local_resolver(tmp_path, asked), threads=2)
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert key in record
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    with rasterio.open(write_dir / "event_x.tif") as cached:
        assert cached.count == 2 and cached.res == (20.0, 20.0) and cached.descriptions == ("gamma0 VV, linear", "gamma0 VH, linear")
        assert np.allclose(cached.read(), image, equal_nan=True)
    assert record["sha256"] == radar.s1_rtc.sha256_file(write_dir / "event_x.tif")
    again = radar.fetch_pass_file(write_dir, "test_area", grid, entry, "event_x", resolve=lambda item: pytest.fail("no read"))
    assert again["sha256"] == record["sha256"]


def test_the_second_scene_is_read_only_where_the_first_left_gaps(tmp_path: Path) -> None:
    grid = (0.0, 100.0, 5, 5)
    full = np.full((10, 10), 0.3, dtype="float32")
    for name in ("a", "b"):
        write_scene(tmp_path / f"{name}_vv.tif", full, 0.0, 100.0)
        write_scene(tmp_path / f"{name}_vh.tif", full, 0.0, 100.0)
    image, details = radar.read_pass_20m(grid, ["a", "b"], resolve=local_resolver(tmp_path, []), threads=1)
    assert np.allclose(image, 0.3)
    assert details["scenes"][0]["blocks_read"] == {"vv": 1, "vh": 1}
    assert details["scenes"][1]["blocks_read"] == {"vv": 0, "vh": 0}


def test_a_scene_on_another_utm_zone_is_taken_by_nearest_neighbour(tmp_path: Path) -> None:
    from pyproj import Transformer

    # A constant scene on UTM zone 48 around a grid on zone 47 near 102 degrees east.
    grid = (820260.0, 1754780.0, 4, 4)
    to48 = Transformer.from_crs(32647, 32648, always_xy=True).transform
    x48, y48 = to48(grid[0], grid[1])
    values = np.full((60, 60), 0.05, dtype="float32")
    west, north = 10.0 * round((x48 - 300) / 10), 10.0 * round((y48 + 300) / 10)
    write_scene(tmp_path / "z_vv.tif", values, west, north, epsg=32648)
    write_scene(tmp_path / "z_vh.tif", values / 5, west, north, epsg=32648)
    image, details = radar.read_pass_20m(grid, ["z"], resolve=local_resolver(tmp_path, []), threads=2)
    assert details["scenes"][0]["read_method"] == "nearest_neighbour_onto_the_10m_lattice"
    assert details["scenes"][0]["file_crs"] == "EPSG:32648"
    assert np.allclose(image[0], 0.05) and np.allclose(image[1], 0.01)


# ---------------------------------------------------------------------------
# The committed records
# ---------------------------------------------------------------------------


RECORDS = sorted((ROOT / "outputs" / "nan_case").glob("radar_passes_*_v1.json"))


@pytest.mark.parametrize("path", RECORDS, ids=[path.name for path in RECORDS])
def test_committed_pass_records_carry_the_envelope_and_no_token(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "sig=" not in text and "?st=" not in text and "blob.core.windows.net" not in text
    assert b"\r\n" not in path.read_bytes()
    record = json.loads(text)
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[key]
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["event_passes"], "every area has at least one event pass"
    for entry in record["event_passes"]:
        assert entry["status"] in {"fetched", "not fetched yet", "failed"}
        assert entry["key"].endswith(f"_o{entry['relative_orbit']}")
    for orbit, block in record["dry_season"]["by_orbit"].items():
        keys = block["selected_latest_first"]
        found = {entry["key"]: entry for entry in block["passes_found"]}
        assert len(keys) <= 10 and all(found[key]["relative_orbit"] == int(orbit) for key in keys)
        starts = [found[key]["start_utc"] for key in keys]
        assert starts == sorted(starts, reverse=True)
        lower, upper = record["dry_season"]["window_utc"]
        assert all(lower <= start <= upper for start in starts)


def test_drystats_streams_the_passes_writes_the_statistics_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rasterio = pytest.importorskip("rasterio")
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    levels = {"p1": (0.01, 0.1), "p2": (0.01, 0.2), "p3": (0.04, 0.4)}  # (VH, VV) linear
    for item, (vh, vv) in levels.items():
        vh_values = np.full((10, 10), vh, dtype="float32")
        if item == "p3":
            vh_values[:4, :4] = -32768.0  # p3 has no value in the 20 m cells (0..1, 0..1)
        write_scene(scenes_dir / f"{item}_vh.tif", vh_values, 0.0, 100.0)
        write_scene(scenes_dir / f"{item}_vv.tif", np.full((10, 10), vv, dtype="float32"), 0.0, 100.0)
    passes = radar.group_passes([scene("p1", "sentinel-1a", 62, "2025-03-01T23:08:00Z"),
                                 scene("p2", "sentinel-1c", 62, "2025-03-07T23:07:00Z"),
                                 scene("p3", "sentinel-1a", 62, "2025-03-13T23:08:00Z")])
    selected = radar.select_latest(passes, cap=10, relative_orbit=62)
    record_file = tmp_path / "radar_passes_t_v1.json"
    radar.write_json(record_file, {"event_passes": [], "dry_season": {
        "window_utc": ["2025-01-01T00:00:00Z", "2025-04-30T23:59:59Z"], "rule": "latest first, at most 10",
        "by_orbit": {"62": {"passes_found": passes, "selected_latest_first": [entry["key"] for entry in selected]}}}})
    monkeypatch.setattr(radar, "load_areas", lambda: {"t": {"grid": {"west": 0, "north": 100, "rows": 5, "cols": 5}}})
    monkeypatch.setattr(radar, "record_path", lambda area_id: record_file)
    monkeypatch.setattr(radar, "CatalogueResolver", lambda: local_resolver(scenes_dir, []))
    for key, value in radar.PROCESS_GDAL_OPTIONS.items():
        monkeypatch.setenv(key, value)
    external = tmp_path / "external"
    radar.main(["drystats", "--area", "t", "--orbit", "62", "--external-root", str(external), "--threads", "2"])
    folder = external / "proposal_execution" / "nan_case_v1" / "radar" / "t"
    assert sorted(path.name for path in folder.iterdir()) == ["dry_o62.json", "dry_o62.tif"]
    with rasterio.open(folder / "dry_o62.tif") as dry:
        assert dry.descriptions == ("vh_mean_db", "vh_std_db", "vv_mean_db", "vv_std_db", "n_valid")
        bands = dry.read()
    vh_db = 10 * np.log10(np.array([0.01, 0.01, 0.04]))
    vv_db = 10 * np.log10(np.array([0.1, 0.2, 0.4]))
    assert np.allclose(bands[0, 2:, 2:], vh_db.mean(), atol=1e-4) and np.allclose(bands[1, 2:, 2:], vh_db.std(), atol=1e-4)
    assert np.allclose(bands[2, 2:, 2:], vv_db.mean(), atol=1e-4) and np.allclose(bands[3, 2:, 2:], vv_db.std(), atol=1e-4)
    assert np.allclose(bands[4, 2:, 2:], 3) and np.allclose(bands[4, :2, :2], 2)  # p3 does not count where VH is missing
    assert np.allclose(bands[0, :2, :2], -20.0, atol=1e-4) and np.allclose(bands[1, :2, :2], 0.0, atol=1e-4)
    result = json.loads((folder / "dry_o62.json").read_text(encoding="utf-8"))
    assert result["official_warning"] is False and result["operational_status"] == "non_operational"
    assert [entry["key"] for entry in result["passes_used"]] == [entry["key"] for entry in selected]
    sensor = result["sensor_agreement"]
    assert sensor["applies"] is True and sensor["platforms"] == ["Sentinel-1A", "Sentinel-1C"]
    # Sentinel-1A mean VH: (-20 + -13.98) / 2 = -16.99 where p3 counts, -20 where it does not; Sentinel-1C: -20.
    assert sensor["median_db"] == pytest.approx(vh_db[[0, 2]].mean() + 20.0, abs=1e-3) and sensor["flagged"] is True
    assert sensor["cells_valid_in_both"] == 25 and sensor["correction_applied"] is False
    medians = {entry["key"]: entry["median_vh_db"] for entry in result["per_pass_medians_for_information"]["passes"]}
    assert medians[selected[0]["key"]] == pytest.approx(vh_db[2], abs=1e-3)
    assert result["n_valid_histogram"] == {"0": 0, "1": 0, "2": 4, "3": 21}
    refreshed = json.loads(record_file.read_text(encoding="utf-8"))
    assert refreshed["dry_season"]["by_orbit"]["62"]["statistics"]["status"] == "computed"
