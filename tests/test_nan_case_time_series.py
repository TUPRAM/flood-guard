"""The time series of the Nan case (``scripts/nan_case_time_series.py``), on invented data only.

An invented frame in the open sea (about 97.2 E, 7.2 N; nothing here is a place): a 20 m grid of 6 rows and 8
columns, two tambons in a unit raster, six demand cells, three frozen maps of invented passes (a full footprint of
relative orbit 62, a partial footprint of orbit 135 and a Sentinel-1C pass of orbit 62) with their records, maps
that must not count, and two invented gauge series. The figures are checked against values worked out by hand.
No layer, record or series of the real case is read.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest
from pyproj import Transformer

from floodguard import m1z
from floodguard import nan_case_chain as chain_rules
from floodguard.nan_frame import DEMAND_COLUMNS
from floodguard.wording_lint import json_strings, lint_texts, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nan_case_time_series.py"
WORDING_RULES = ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json"


def _load() -> Any:
    name = "nan_case_time_series_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ts = _load()

# The invented grid: west 300000, north 800120 in EPSG:32647, 6 rows and 8 columns of 20 m.
WEST, NORTH, ROWS, COLS = 300_000.0, 800_120.0, 6, 8
GRID = chain_rules.RasterGrid(WEST, NORTH, ROWS, COLS)
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
F, N, X = m1z.FLAGGED, m1z.NOT_FLAGGED, m1z.NO_ANSWER
LABEL_A, LABEL_B, LABEL_C = "20250719T2308_o62_S1A", "20250724T2316_o135_S1A", "20250725T2300_o62_S1C"


def unit_raster() -> np.ndarray:
    """Columns 0-3 tambon 1, columns 4-7 tambon 2; the cell of row 0, column 7 lies in no tambon."""

    values = np.zeros((ROWS, COLS), dtype="uint8")
    values[:, 0:4] = 1
    values[:, 4:8] = 2
    values[0, 7] = 0
    return values


def base_map() -> tuple[np.ndarray, np.ndarray]:
    """Every cell asked of the radar and dry; permanent water at (5, 0) and (5, 1); terrain at (0, 0) and (0, 1)."""

    reason = np.full((ROWS, COLS), m1z.REASON_RADAR_DRY, dtype="uint8")
    code = np.full((ROWS, COLS), N, dtype="uint8")
    reason[5, 0:2] = m1z.REASON_PERMANENT_WATER
    reason[0, 0:2] = m1z.REASON_TERRAIN_HAND
    return code, reason


def levels_from(code: np.ndarray, reason: np.ndarray, lower: list[tuple[int, int]], central: list[tuple[int, int]],
                upper: list[tuple[int, int]]) -> dict[str, np.ndarray]:
    out = {}
    for level, cells in (("lower", lower), ("central", central), ("upper", upper)):
        values = code.copy()
        for row, col in cells:
            values[row, col] = F
        out[level] = values
    for row, col in central:
        reason[row, col] = m1z.REASON_FLAGGED
    return out


def map_a() -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Pass A (orbit 62, full): no answer on built-up (1, 4), (1, 5) and no radar after on (2, 6), (2, 7)."""

    code, reason = base_map()
    for row, col, why in ((1, 4, m1z.REASON_BUILT_UP_LOW), (1, 5, m1z.REASON_BUILT_UP_LOW),
                          (2, 6, m1z.REASON_NO_RADAR_AFTER), (2, 7, m1z.REASON_NO_RADAR_AFTER)):
        code[row, col], reason[row, col] = X, why
    central = [(3, 1), (3, 2), (4, 1), (4, 2), (3, 5), (4, 5), (0, 7)]
    codes = levels_from(code, reason, lower=[(3, 1), (3, 2), (0, 7)], central=central, upper=[*central, (3, 3), (4, 6)])
    return codes, reason


def map_b() -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Pass B (orbit 135, partial): no radar after on the whole of tambon 2."""

    code, reason = base_map()
    code[:, 4:8], reason[:, 4:8] = X, m1z.REASON_NO_RADAR_AFTER
    codes = levels_from(code, reason, lower=[(3, 1), (3, 2)], central=[(3, 1), (3, 2)], upper=[(3, 1), (3, 2), (4, 1)])
    return codes, reason


def map_c() -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Pass C (orbit 62, Sentinel-1C, full): radar everywhere."""

    code, reason = base_map()
    central = [(3, 1), (3, 2), (3, 5), (4, 5), (4, 6)]
    codes = levels_from(code, reason, lower=[(3, 1), (3, 2)], central=central, upper=[*central, (4, 1)])
    return codes, reason


def centre(row: int, col: int) -> tuple[float, float]:
    return WEST + 20 * col + 10, NORTH - 20 * row - 10


DEMAND = [  # population_id, unit, residents, (row, col) of the 20 m cell that holds the centre
    ("p1", "TH0001", 10.0, (3, 1)),   # flagged in the three maps of A
    ("p2", "TH0001", 5.0, (3, 3)),    # flagged in the upper map of A only
    ("p3", "TH0001", 2.0, (0, 0)),    # terrain
    ("p4", "TH0002", 7.0, (1, 4)),    # no answer in A
    ("p5", "TH0002", 3.0, (4, 5)),    # flagged in the central and upper maps of A
    ("p6", "TH0002", 1.5, (4, 6)),    # flagged in the upper map of A
]


def demand_record() -> dict[str, Any]:
    rows = []
    for identifier, unit_id, residents, (row, col) in DEMAND:
        x, y = centre(row, col)
        longitude, latitude = TO_WGS84(x, y)
        values = {"population_id": identifier, "unit_id": unit_id, "unit_assignment": "cell_centre_in_one_unit",
                  "residents_2020": residents, "residents_rescaled_2024": residents, "kept_at_2020": False,
                  "longitude": longitude, "latitude": latitude, "x_32647": round(x, 3), "y_32647": round(y, 3),
                  "grid_row": row, "grid_col": col, "node_id": None, "snap_distance_m": None}
        rows.append([values[name] for name in DEMAND_COLUMNS])
    return {"schema": "floodguard.nan_case_demand_cells.v1", "columns": list(DEMAND_COLUMNS), "rows": rows}


def demand() -> Any:
    found, _summary = ts.demand_from_record(demand_record(), GRID)
    return found


UNITS = [ts.Unit("TH0001", "Invented One", "TH00", 1), ts.Unit("TH0002", "Invented Two", "TH00", 2)]


# ---------------------------------------------------------------------------
# The pure parts
# ---------------------------------------------------------------------------


def test_pass_figures_count_flooded_land_shares_and_residents_by_hand() -> None:
    codes, reason = map_a()
    found = ts.pass_figures(codes, reason, unit_raster(), UNITS, demand(), GRID)
    frame, (one, two) = found["frame"], found["units"]
    # Tambon 1: 24 cells, 2 of permanent water -> 22 of land; 2 answered by terrain; flags 2 / 4 / 5.
    assert one["land_cells"] == 22 and one["land_km2"] == 0.0088
    assert one["flagged_cells"] == {"lower": 2, "central": 4, "upper": 5}
    assert one["flooded_land_km2"] == {"lower": 0.0008, "central": 0.0016, "upper": 0.002}
    assert one["flagged_share_of_land"]["central"] == round(4 / 22, 6)
    assert one["no_answer_share_of_land"] == 0.0 and one["terrain_answered_share_of_land"] == round(2 / 22, 6)
    assert one["radar_value_share_of_land_not_answered_by_terrain"] == 1.0
    assert one["residents_2020"] == 17.0
    assert one["residents_in_flagged_cells"] == {"lower": 10.0, "central": 10.0, "upper": 15.0}
    # Tambon 2: 23 cells of land (one cell is in no tambon); 4 without an answer, 2 of them without radar after.
    assert two["land_cells"] == 23 and two["flagged_cells"] == {"lower": 0, "central": 2, "upper": 3}
    assert two["no_answer_share_of_land"] == round(4 / 23, 6) and two["no_radar_after_share_of_land"] == round(2 / 23, 6)
    assert two["radar_value_share_of_land_not_answered_by_terrain"] == round(1 - 2 / 23, 6)
    assert two["residents_in_flagged_cells"] == {"lower": 0.0, "central": 3.0, "upper": 4.5}
    assert two["residents_in_no_answer_cells"] == 7.0
    # The frame: the flagged cell of row 0, column 7 lies in no tambon and is not counted.
    assert frame["land_cells"] == 45 and frame["flagged_cells"] == {"lower": 2, "central": 6, "upper": 8}
    assert frame["flooded_land_km2"]["central"] == 0.0024
    assert frame["no_answer_share_of_land"] == round(4 / 45, 6)
    assert frame["radar_value_share_of_land_not_answered_by_terrain"] == round(1 - 2 / 43, 6)
    assert frame["residents_2020"] == 28.5 and frame["residents_in_flagged_cells"] == {"lower": 10.0, "central": 13.0, "upper": 19.5}
    assert found["checks"] == {"no_answer_cells_same_in_the_three_maps": True,
                               "lower_flags_within_central_and_central_within_upper": True,
                               "flagged_cells_outside_the_land_of_the_frame_central": 0}


def test_the_resident_lookup_is_the_score_chains_grid_lookup() -> None:
    found = demand()
    codes, _reason = map_a()
    values = chain_rules.grid_values_at(codes["central"], GRID, found.x, found.y)
    assert values.tolist() == [F, N, N, X, F, N]
    _demand, summary = ts.demand_from_record(demand_record(), GRID)
    assert summary["cells_whose_projected_cell_differs_from_the_frame_lane_grid_cell"] == 0
    assert summary["demand_cells"] == 6 and summary["residents_2020"] == 28.5


def test_partial_footprints_are_labelled_with_their_coverage() -> None:
    partial = ts.coverage_record(135, {"footprint_share_of_grid": 0.1023, "valid_share": {"vh": 0.1}}, 0.12)
    assert partial["footprint"] == "partial" and partial["relative_orbit_with_a_partial_footprint"] is True
    assert "10% of the frame grid" in partial["label"] and "12%" in partial["label"]
    assert partial["catalogue_footprint_share_of_grid"] == 0.1023 and partial["valid_vh_share_of_grid"] == 0.1
    assert ts.coverage_record(99, {"footprint_share_of_grid": 0.8216}, None)["footprint"] == "partial"
    assert ts.coverage_record(172, None, None)["footprint"] == "partial"
    full = ts.coverage_record(62, {"footprint_share_of_grid": 0.9999}, 0.99)
    assert full["footprint"] == "full" and full["label"].startswith("full footprint")
    # Another orbit with a footprint under 0.99 of the grid is partial too.
    assert ts.coverage_record(18, {"footprint_share_of_grid": 0.5}, None)["footprint"] == "partial"


def test_the_common_radar_land_keeps_only_cells_every_pass_of_a_group_sees() -> None:
    masks = {}
    for label, (codes, reason) in ((LABEL_A, map_a()), (LABEL_B, map_b()), (LABEL_C, map_c())):
        figures = ts.pass_figures(codes, reason, unit_raster(), UNITS, demand(), GRID)
        masks[label] = ts.pack_masks(figures["masks"])
    found = ts.common_area_figures({"every pass": [LABEL_A, LABEL_B, LABEL_C], "relative orbit 62": [LABEL_A, LABEL_C]}, masks)
    every = found["every pass"]
    assert every["common_land_cells"] == 22 and every["common_land_share_of_frame_land"] == round(22 / 45, 6)
    assert [row["flooded_land_km2_central"] for row in every["by_pass"]] == [0.0016, 0.0008, 0.0008]
    orbit = found["relative orbit 62"]
    assert orbit["common_land_cells"] == 43
    assert [row["flooded_land_km2_central"] for row in orbit["by_pass"]] == [0.0024, 0.002]
    assert [row["flooded_land_km2_upper"] for row in orbit["by_pass"]] == [0.0032, 0.0024]


def gauge_file(path: Path, rows: list[tuple[str, str]]) -> str:
    text = "datetime_thai_time,level_m_msl,gauge_height_m,discharge_m3_s\n" + "".join(
        f"{when},{level},{'' if not level else round(float(level) - 192.2, 3)},\n" for when, level in rows)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_gauge_levels_are_read_at_a_time_by_reading_or_interpolation(tmp_path: Path) -> None:
    from datetime import datetime

    path = tmp_path / "series.csv"
    gauge_file(path, [("2025-07-20 05:00", "195.5"), ("2025-07-20 06:00", "196.0"), ("2025-07-20 07:00", "196.6"),
                      ("2025-07-20 08:00", ""), ("2025-07-20 09:00", ""), ("2025-07-20 10:00", ""), ("2025-07-20 11:00", "197.0")])
    readings = ts.read_gauge_csv(path)
    assert ts.value_at(readings, datetime(2025, 7, 20, 6, 0), "level_m_msl") == {"value": 196.0, "how": "the reading of 2025-07-20 06:00"}
    between = ts.value_at(readings, datetime(2025, 7, 20, 6, 8), "level_m_msl")
    assert between["value"] == round(196.0 + 8 / 60 * 0.6, 3) and between["how"].startswith("linear between")
    gap = ts.value_at(readings, datetime(2025, 7, 20, 8, 30), "level_m_msl")
    assert gap["value"] is None and "240 minutes apart" in gap["how"]
    assert ts.value_at(readings, datetime(2025, 7, 21, 0, 0), "level_m_msl")["value"] is None
    assert ts.value_at(readings, datetime(2025, 7, 20, 6, 30), "gauge_height_m")["value"] == round((3.8 + 4.4) / 2, 3)
    assert ts.nearest_reading(readings, datetime(2025, 7, 20, 6, 8))["time_thai"] == "2025-07-20 06:00"
    assert ts.nearest_reading(readings, datetime(2025, 7, 20, 9, 0)) is None
    with pytest.raises(ts.TimeSeriesError):
        (tmp_path / "bad.csv").write_text("time,level\n", encoding="utf-8")
        ts.read_gauge_csv(tmp_path / "bad.csv")


def test_the_firewall_refuses_sealed_and_reference_paths() -> None:
    for path in ("/x/proposal_execution/nan_case_v1/jaxa_sealed/a.zip", "/x/method/case_n2_reference/ref.tif",
                 "/x/gfm/flood.tif", "/x/IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif", "/x/water_v2_chip_003_2m.tif",
                 "/x/outputs/theos2_water_labels/key_v1.json"):
        assert ts.firewall_refusal(path) is not None, path
        with pytest.raises(ts.TimeSeriesError):
            ts.refuse_firewall([path])
    assert ts.firewall_refusal("/x/proposal_execution/nan_case_v1/method/maps/m1z_20250719T2308_o62_S1A.tif") is None
    assert ts.firewall_refusal("/x/proposal_execution/nan_case_v1/frame/demand_cells_v1.json") is None


def test_nice_ticks_cover_the_range() -> None:
    assert ts.nice_ticks(0.0, 37.0) == [0.0, 10.0, 20.0, 30.0, 40.0]
    assert ts.nice_ticks(-12.6, 5.2)[0] <= -12.6 and ts.nice_ticks(-12.6, 5.2)[-1] >= 5.2
    assert ts.nice_ticks(0.0, 0.0) == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


# ---------------------------------------------------------------------------
# The whole stage on an invented root
# ---------------------------------------------------------------------------


def write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=1) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def write_units(path: Path) -> str:
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=ROWS, width=COLS, count=1, dtype="uint8", crs="EPSG:32647",
                       transform=GRID.transform) as target:
        target.write(unit_raster(), 1)
    return ts.sha256_file(path)


def write_pass(folder: Path, label: str, time_utc: str, orbit: int, platform: str, codes: dict[str, np.ndarray], reason: np.ndarray,
               freeze_sha256: str, *, file: str | None, summary: dict[str, Any] | None = None) -> Path:
    path = folder / f"m1z_{label}.tif"
    digest = ts.method.write_map(path, (WEST, NORTH, ROWS, COLS), [("code_lower", codes["lower"]), ("code_central", codes["central"]),
                                                                   ("code_upper", codes["upper"]), ("reason_central", reason)])
    record = {"schema": "floodguard.nan_case_m1z_map.v1", "generated_at_utc": "2026-10-15T00:00:00Z",
              "pass": {"file": file, "time_utc": time_utc, "relative_orbit": orbit, "platform": platform, "label": label},
              "freeze_record": {"path": "outputs/nan_case/freeze_v1.json", "sha256": freeze_sha256},
              "map": {"name": path.name, "sha256": digest, "bands": ["code_lower", "code_central", "code_upper", "reason_central"]},
              "summary": summary or {}}
    write_json(path.with_suffix(".json"), record)
    return path


@pytest.fixture()
def case(tmp_path: Path) -> Any:
    root, external = tmp_path / "repo", tmp_path / "external"
    frame_dir = external / "proposal_execution" / "nan_case_v1" / "frame"
    maps_dir = external / "proposal_execution" / "nan_case_v1" / "method" / "maps"
    gauge_dir = external / "proposal_execution" / "nan_case_v1" / "consequence" / "gauge"
    maps_dir.mkdir(parents=True)
    gauge_dir.mkdir(parents=True)
    grid = {"west": WEST, "north": NORTH, "rows": ROWS, "cols": COLS}
    write_json(root / ts.PROTOCOL, {"schema": "floodguard.nan_case_protocol.v1", "grid": {"frame": grid},
                                    "event": {"window_utc": ["2025-07-15T17:00:00Z", "2025-08-13T16:59:59Z"]}})
    write_json(root / ts.AMENDMENT_1, {"changes": {"platform_offset": {"offset_db": {"sentinel-1c": 0.79}}}})
    units_sha = write_units(frame_dir / ts.UNIT_RASTER_NAME)
    demand_sha = write_json(frame_dir / ts.DEMAND_NAME, demand_record())
    write_json(root / ts.FRAME_RECORD, {
        "units": [{"adm3_pcode": unit.unit_id, "adm3_name": unit.name, "adm2_pcode": unit.district, "raster_value": unit.raster_value}
                  for unit in UNITS],
        "unit_raster": {"grid": grid, "sha256": units_sha},
        "files_outside_git": {"demand_cells": {"sha256": demand_sha}, "unit_raster": {"sha256": units_sha}}})
    freeze_sha = write_json(root / ts.FREEZE, {"flood_levels": {"lower": {"z_vh_max": -1.5}, "central": {"z_vh_max": -1.0},
                                                                 "upper": {"z_vh_max": -0.5}}})
    write_json(root / ts.RADAR_RECORD, {"event_passes": [
        {"key": "20250719T2308Z_s1a_o62", "platform": "Sentinel-1A", "relative_orbit": 62, "orbit_state": "descending",
         "start_utc": "2025-07-19T23:08:07Z", "footprint_share_of_grid": 1.0, "file": "event_20250719T2308Z_s1a_o62.tif",
         "valid_share": {"vh": 1.0}},
        {"key": "20250724T2316Z_s1a_o135", "platform": "Sentinel-1A", "relative_orbit": 135, "orbit_state": "descending",
         "start_utc": "2025-07-24T23:16:16Z", "footprint_share_of_grid": 0.1023},
        {"key": "20250725T2300Z_s1c_o62", "platform": "Sentinel-1C", "relative_orbit": 62, "orbit_state": "descending",
         "start_utc": "2025-07-25T23:00:00Z", "footprint_share_of_grid": 0.9999, "file": "event_20250725T2300Z_s1c_o62.tif",
         "valid_share": {"vh": 1.0}}]})
    n1_sha = gauge_file(gauge_dir / "series_n1.csv", [
        ("2025-07-20 06:00", "196.0"), ("2025-07-20 07:00", "196.6"), ("2025-07-25 06:00", "200.0"), ("2025-07-25 07:00", ""),
        ("2025-07-25 08:00", ""), ("2025-07-25 09:00", ""), ("2025-07-25 10:00", "201.0"), ("2025-07-26 06:00", "199.5")])
    gauge_file(gauge_dir / "series_n75.csv", [("2025-07-20 06:00", "190.0")])
    write_json(root / ts.NEWS_RECORD, {"gauge_records": [
        {"station": "N.1", "agency": "invented", "place": "invented place", "river": "invented river",
         "file_outside_git": {"name": "series_n1.csv", "sha256": n1_sha}, "reading_step": "hourly", "retrieved_at_utc": "2026-10-14T00:00:00Z",
         "peak_m_msl": 201.0, "peak_times_thai_time": ["2025-07-25 10:00"], "levels": {"min_bank": {"level_m_msl": 199.2}}},
        {"station": "N.75", "agency": "invented", "place": "invented place", "river": "invented river",
         "file_outside_git": {"name": "series_n75.csv", "sha256": "0" * 64}, "levels": {"min_bank": {"level_m_msl": 192.8}}}]})
    write_json(root / ts.TEST_RESULT, {"binding": {"flood_input_of_case_N1": {"label": LABEL_C}}})
    a_codes, a_reason = map_a()
    write_pass(maps_dir, LABEL_A, "2025-07-19T23:08:07Z", 62, "Sentinel-1A", a_codes, a_reason, freeze_sha,
               file="event_20250719T2308Z_s1a_o62.tif",
               summary={"central": {"flagged_km2_frame_land": 0.0024, "no_answer_share_frame_land": round(4 / 45, 6)},
                        "lower": {"flagged_km2_frame_land": 0.0008}, "upper": {"flagged_km2_frame_land": 0.0032}})
    b_codes, b_reason = map_b()
    write_pass(maps_dir, LABEL_B, "2025-07-24T23:16:16Z", 135, "Sentinel-1A", b_codes, b_reason, freeze_sha, file="event_other_name.tif")
    c_codes, c_reason = map_c()
    write_pass(maps_dir, LABEL_C, "2025-07-25T23:00:00Z", 62, "Sentinel-1C", c_codes, c_reason, freeze_sha,
               file="event_20250725T2300Z_s1c_o62.tif")
    # Maps that must not count: another freeze record, changed bytes, and a map without its record.
    write_pass(maps_dir, "20250728T1120_o99_S1C", "2025-07-28T11:20:49Z", 99, "Sentinel-1C", a_codes, a_reason, "f" * 64, file=None)
    changed = write_pass(maps_dir, "20250731T2308_o62_S1A", "2025-07-31T23:08:03Z", 62, "Sentinel-1A", a_codes, a_reason, freeze_sha, file=None)
    changed.write_bytes(changed.read_bytes() + b"\0")
    (maps_dir / "m1z_stray.tif").write_bytes(b"not a map")
    paths = ts.default_paths(external, root=root)
    return paths


def test_the_stage_writes_the_series_beside_the_gauges(case: Any) -> None:
    record = ts.build(case, generated_at="2026-10-15T01:00:00Z", git_commit="0" * 40)
    assert [item["pass"] for item in record["passes"]] == [LABEL_A, LABEL_B, LABEL_C]
    a, b, c = record["passes"]
    assert a["time_thai"] == "2025-07-20T06:08:07+07:00" and a["platform"] == "Sentinel-1A" and a["relative_orbit"] == 62
    assert a["frame"]["flooded_land_km2"] == {"lower": 0.0008, "central": 0.0024, "upper": 0.0032}
    assert a["frame_figures_beside_the_map_record"]["same"] is True
    assert c["frame_figures_beside_the_map_record"]["same"] is None
    assert a["coverage"]["footprint"] == "full" and a["coverage"]["catalogue_footprint_share_of_grid"] == 1.0
    assert b["coverage"]["footprint"] == "partial" and b["coverage"]["catalogue_footprint_share_of_grid"] == 0.1023
    assert b["radar_record_key"] == "20250724T2316Z_s1a_o135"   # matched by platform, orbit and time
    assert b["coverage"]["radar_value_share_of_frame_land_not_answered_by_terrain"] == round(1 - 23 / 43, 6)
    assert c["platform_offset_db_applied_by_the_method"] == 0.79 and a["platform_offset_db_applied_by_the_method"] == 0.0
    assert [item["is_the_flood_input_of_case_N1"] for item in record["passes"]] == [False, False, True]
    assert a["passes_of_the_same_orbit"] == [LABEL_A, LABEL_C] and b["passes_of_the_same_orbit"] == [LABEL_B]
    groups = record["common_radar_land"]["groups"]
    assert set(groups) == {"every pass", "relative orbit 62", "relative orbit 135"}
    assert groups["every pass"]["common_land_cells"] == 22 and groups["relative orbit 62"]["common_land_cells"] == 43
    # Tambon rows: three passes by two tambons, flat.
    rows = record["tambon_rows"]
    assert len(rows) == 6 and rows[0]["pass"] == LABEL_A and rows[0]["unit_id"] == "TH0001"
    assert rows[1]["residents_in_flagged_cells_central"] == 3.0 and rows[1]["residents_in_no_answer_cells"] == 7.0
    assert rows[3]["no_radar_after_share_of_land"] == 1.0 and rows[3]["flooded_land_km2_central"] == 0.0
    # Maps that do not count are listed with why.
    why = {item["map"].rsplit("/", 1)[-1]: item["why"] for item in record["inputs"]["maps_not_used"]}
    assert set(why) == {"m1z_20250728T1120_o99_S1C.tif", "m1z_20250731T2308_o62_S1A.tif", "m1z_stray.tif"}
    assert "another freeze record" in why["m1z_20250728T1120_o99_S1C.tif"]
    assert "bytes" in why["m1z_20250731T2308_o62_S1A.tif"] and "no record" in why["m1z_stray.tif"]
    assert record["inputs"]["radar_record_passes_without_a_frozen_map"] == []
    assert record["inputs"]["maps_index"] is None and "maps stage" in record["inputs"]["maps_index_note"]
    # Gauges: read at the pass times, beside each pass; a file whose SHA-256 differs is not read.
    stations = {station["station"]: station for station in record["gauges"]["stations"]}
    at = {row["pass"]: row for row in stations["N.1"]["at_passes"]}
    assert at[LABEL_A]["level_m_msl"] == round(196.0 + 8.1167 / 60 * 0.6, 3)
    assert at[LABEL_A]["level_minus_m"]["min_bank"] == round(at[LABEL_A]["level_m_msl"] - 199.2, 3)
    assert at[LABEL_B]["level_m_msl"] is None and "minutes apart" in at[LABEL_B]["how"]
    assert at[LABEL_C]["level_m_msl"] == 199.5 and at[LABEL_C]["time_thai"] == "2025-07-26 06:00"
    assert stations["N.75"]["file"]["read"] is False and stations["N.75"]["at_passes"] == []
    assert c["gauge_levels_m_msl_at_the_pass"] == {"N.1": 199.5}
    assert record["gauges"]["status"] == "read"


def test_the_written_record_carries_the_fields_of_every_record(case: Any) -> None:
    record = ts.build(case, generated_at="2026-10-15T01:00:00Z", git_commit="0" * 40)
    data = case.out_json.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n") and hashlib.sha256(data).hexdigest() == record["written"]["sha256"]
    written = json.loads(data.decode("utf-8"))
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert written[key], key
    assert written["official_warning"] is False and written["operational_status"] == "non_operational"
    assert written["can_feed_decision_layer"] is False and written["report_only"] is True
    assert written["source_timestamp"].startswith("Sentinel-1 passes 2025-07-19T23:08:07Z")
    assert written["order"]["test_result"]["path"] == ts.TEST_RESULT
    assert written["inputs"]["demand_cells"]["path"].startswith(ts.EXTERNAL_LABEL)
    # One tambon row per line.
    lines = data.decode("utf-8").splitlines()
    assert sum(1 for line in lines if line.startswith('  {"pass": ')) == 6
    # The chart is a PNG of 1400 x 900 pixels, named with its SHA-256.
    png = case.out_png.read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and hashlib.sha256(png).hexdigest() == written["chart"]["sha256"]
    assert (written["chart"]["width"], written["chart"]["height"]) == (1400, 900)
    # A second run records the file it replaces.
    again = ts.build(case, generated_at="2026-10-15T02:00:00Z", git_commit="0" * 40)
    assert again["supersedes"] == {"sha256": record["written"]["sha256"], "generated_at_utc": "2026-10-15T01:00:00Z"}


def test_passes_of_the_radar_record_without_a_map_are_listed(case: Any) -> None:
    radar = json.loads((case.root / ts.RADAR_RECORD).read_text(encoding="utf-8"))
    radar["event_passes"].append({"key": "20250805T2316Z_s1a_o135", "platform": "Sentinel-1A", "relative_orbit": 135,
                                  "start_utc": "2025-08-05T23:16:12Z", "footprint_share_of_grid": 0.1044, "status": "not fetched yet"})
    write_json(case.root / ts.RADAR_RECORD, radar)
    write_json(case.maps_dir / ts.MAPS_INDEX_NAME, {"maps": {LABEL_A: {"name": f"m1z_{LABEL_A}.tif"}}})
    record = ts.build(case, generated_at="2026-10-15T01:00:00Z", git_commit="0" * 40)
    missing = record["inputs"]["radar_record_passes_without_a_frozen_map"]
    assert [item["key"] for item in missing] == ["20250805T2316Z_s1a_o135"]
    assert missing[0]["status_in_the_radar_record"] == "not fetched yet"
    assert record["inputs"]["maps_index"]["maps_listed"] == 1 and record["inputs"]["maps_index_note"] is None
    assert [item["map"]["in_the_maps_index"] for item in record["passes"]] == [True, False, False]


def test_test_1_of_record_names_the_flood_input_of_case_n1(case: Any) -> None:
    """Amendment 2: when test 1 of record exists, its binding names the N1 input, not the first run's."""

    write_json(case.root / ts.TEST_1_OF_RECORD, {"binding": {"flood_input_of_case_N1": {"label": LABEL_A}}})
    record = ts.build(case, generated_at="2026-10-15T01:00:00Z", git_commit="0" * 40)
    assert [item["is_the_flood_input_of_case_N1"] for item in record["passes"]] == [True, False, False]
    assert record["order"]["flood_input_of_case_N1_from"]["path"] == ts.TEST_1_OF_RECORD
    assert record["order"]["flood_input_of_case_N1"] == LABEL_A
    assert record["order"]["test_result"]["path"] == ts.TEST_RESULT


def _entry(label: str, orbit: int, seen: float) -> dict[str, Any]:
    return {"pass": label, "relative_orbit": orbit,
            "coverage": {"radar_value_share_of_frame_land_not_answered_by_terrain": seen}}


def test_the_comparison_groups_leave_out_a_pass_that_sees_almost_nothing() -> None:
    passes = [_entry("p1", 62, 1.0), _entry("p2", 135, 0.0005), _entry("p3", 99, 0.98), _entry("p4", 62, 1.0)]
    groups = ts.comparison_groups(passes)
    assert list(groups) == ["every pass", ts.SEEN_GROUP, "relative orbit 62", "relative orbit 135", "relative orbit 99"]
    assert groups[ts.SEEN_GROUP] == ["p1", "p3", "p4"] and groups["every pass"] == ["p1", "p2", "p3", "p4"]
    # No extra group when it would repeat another one.
    assert ts.SEEN_GROUP not in ts.comparison_groups([_entry("p1", 62, 1.0), _entry("p2", 135, 0.0), _entry("p4", 62, 1.0)])
    assert ts.SEEN_GROUP not in ts.comparison_groups([_entry("p1", 62, 1.0), _entry("p3", 99, 0.98)])


def test_the_chart_notes_say_which_passes_see_almost_nothing() -> None:
    lines = ts.chart_coverage_notes([_entry("p1", 62, 1.0), _entry("p2", 135, 0.0005), _entry("p3", 99, 0.98)])
    assert len(lines) == 2 and "99, 135, 172" in lines[0]
    assert lines[1].startswith("Orbit 135: radar on under 1% ") and "no observation" in lines[1]
    assert len(ts.chart_coverage_notes([_entry("p1", 62, 1.0)])) == 1
    assert ts.under_axis_share(0.0005) == "<1%" and ts.under_axis_share(0.9826) == "98%" and ts.under_axis_share(None) is None


def test_the_stage_refuses_before_the_test_and_writes_nothing(case: Any) -> None:
    (case.root / ts.TEST_RESULT).unlink()
    with pytest.raises(ts.TimeSeriesError, match="order rule"):
        ts.build(case)
    assert not case.out_json.exists() and not case.out_png.exists()
    code = ts.main(["run", "--external-root", str(case.external), "--repo-root", str(case.root)])
    assert code == ts.EXIT_REFUSED and not case.out_json.exists()


def test_the_stage_refuses_inputs_that_are_not_the_recorded_ones(case: Any) -> None:
    demand_path = case.frame_dir / ts.DEMAND_NAME
    demand_path.write_bytes(demand_path.read_bytes() + b" ")
    with pytest.raises(ts.TimeSeriesError, match="demand cells"):
        ts.build(case)
    assert not case.out_json.exists()


def test_the_stage_refuses_without_a_frozen_map(case: Any) -> None:
    for path in case.maps_dir.glob("m1z_*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["freeze_record"]["sha256"] = "e" * 64
        path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ts.TimeSeriesError, match="no frozen map"):
        ts.build(case)


def test_the_stage_refuses_paths_behind_the_firewall(case: Any) -> None:
    sealed = ts.Paths(root=case.root, external=case.external, maps_dir=case.external / "jaxa_sealed", frame_dir=case.frame_dir,
                      gauge_dir=case.gauge_dir, out_json=case.out_json, out_png=case.out_png)
    with pytest.raises(ts.TimeSeriesError, match="sealed folder"):
        ts.build(sealed)
    gfm = ts.Paths(root=case.root, external=case.external, maps_dir=case.maps_dir, frame_dir=case.frame_dir,
                   gauge_dir=case.external / "GFM", out_json=case.out_json, out_png=case.out_png)
    with pytest.raises(ts.TimeSeriesError, match="firewall"):
        ts.build(gfm)
    assert not case.out_json.exists()


def test_check_inputs_opens_no_map_and_needs_no_test(case: Any, tmp_path: Path) -> None:
    (case.root / ts.TEST_RESULT).unlink()
    for path in case.maps_dir.glob("*"):
        path.unlink()
    case.maps_dir.rmdir()
    preview = tmp_path / "preview.png"
    found = ts.check_inputs(case, chart_preview=preview)
    assert found["inputs_checked"] is True and found["units"] == 2
    assert found["demand_cells"]["residents_2020"] == 28.5
    assert [item["coverage"] for item in found["radar_record_event_passes"]] == ["full", "partial", "full"]
    assert found["gauges"]["levels_at_the_listed_pass_times_m_msl"]["N.1"]["20250725T2300Z_s1c_o62"] == 199.5
    assert preview.read_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ts.TimeSeriesError, match="outside the repository"):
        ts.check_inputs(case, chart_preview=case.root / "preview.png")


def test_the_wording_passes_the_shared_lint(case: Any) -> None:
    rules = load_rules(WORDING_RULES)
    script = [("scripts/nan_case_time_series.py", "\n".join(python_strings(SCRIPT.read_text(encoding="utf-8"))))]
    assert lint_texts(script, rules) == []
    ts.build(case, generated_at="2026-10-15T01:00:00Z", git_commit="0" * 40)
    written = json.loads(case.out_json.read_text(encoding="utf-8"))
    assert lint_texts(list(json_strings(written)), rules) == []
