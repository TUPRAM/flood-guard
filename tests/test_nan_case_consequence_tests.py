"""Tests of tests 3a, 3b and 4 of the Nan case (scripts/nan_case_consequence_tests.py) on invented data.

Every graph, point, polygon, map, water raster and record below is invented, at an invented origin in the open sea
(about 97.2 E, 7.2 N): nothing is a place. The committed records of the case are read only where the test says so
(the five points, the amendment and the pass catalogue, which hold positions and metadata, no flag).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np
from pyproj import Transformer
import pytest
from shapely.geometry import LineString, MultiPolygon, Point, box, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, flood_inputs, m1z  # noqa: E402
from floodguard import nan_case_chain as nan  # noqa: E402
from floodguard.wording_lint import json_strings, lint_texts, load_rules, python_strings  # noqa: E402

SCRIPT = ROOT / "scripts" / "nan_case_consequence_tests.py"
WORDING_RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
V1B = json.loads((ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform


def load_script() -> Any:
    """Load the script as a module, without running it."""

    spec = importlib.util.spec_from_file_location("nan_case_consequence_tests_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ct = load_script()

# ---------------------------------------------------------------------------------------------------------------------
# The invented frame: 100 by 100 cells of 20 m, x 300,000 to 302,000 and y 800,000 to 802,000 (EPSG:32647)
# ---------------------------------------------------------------------------------------------------------------------

WEST, NORTH, CELL = 300_000.0, 802_000.0, 20.0
GRID = nan.RasterGrid(WEST, NORTH, 100, 100)
CHIP = {"west": 301_000.0, "south": 800_200.0, "east": 301_600.0, "north": 800_600.0}
HOSPITAL_BOX = box(300_800.0, 801_100.0, 300_900.0, 801_200.0)

EDGES = {
    # name: (x0, y0, x1, y1, road class, bridge)
    "e-found": (300_200, 801_710, 300_400, 801_710, "residential", "no"),
    "e-dry": (301_000, 801_710, 301_200, 801_710, "residential", "no"),
    "e-uncovered": (300_300, 800_510, 300_500, 800_510, "residential", "no"),
    "e-trunk": (301_400, 800_910, 301_800, 800_910, "trunk", "no"),
    "e-hosp": (300_700, 801_150, 300_800, 801_150, "tertiary", "no"),
    "c-wet-closed": (301_100, 800_310, 301_300, 800_310, "residential", "no"),
    "c-wet-open": (301_100, 800_410, 301_300, 800_410, "residential", "no"),
    "c-dry-closed": (301_100, 800_510, 301_300, 800_510, "residential", "no"),
    "c-straddle": (300_900, 800_350, 301_100, 800_350, "residential", "no"),
    "c-short": (301_400, 800_310, 301_430, 800_310, "residential", "no"),
    "far": (301_900, 801_900, 301_950, 801_900, "residential", "no"),
}


def cell(x: float, y: float) -> tuple[int, int]:
    """Row and column of the cell that holds a point of the invented grid."""

    return int((NORTH - y) // CELL), int((x - WEST) // CELL)


def graph(definitions: dict[str, tuple] = EDGES) -> tuple[list[dict[str, Any]], dict[str, tuple[float, float]]]:
    """Invented vehicle edges (one segment each) with their nodes in longitude and latitude, and one grade-join connector."""

    edges, nodes = [], {}
    for name, (x0, y0, x1, y1, road_class, bridge) in definitions.items():
        nodes[f"{name}-a"], nodes[f"{name}-b"] = TO_WGS84(x0, y0), TO_WGS84(x1, y1)
        edges.append({"edge_id": name, "from_node": f"{name}-a", "to_node": f"{name}-b", "length_m": float(np.hypot(x1 - x0, y1 - y0)),
                      "road_class": road_class, "normal_minutes": 1.0, "osm_way_id": f"invented-{name}", "bridge": bridge,
                      "layer": "0", "tunnel": "no", "travel_mode": "legacy_vehicle"})
    first = next(iter(definitions))
    edges.append({"edge_id": "join-1", "from_node": f"{first}-a", "to_node": f"{first}-a", "length_m": 0.0, "road_class": "local",
                  "normal_minutes": 0.0, "osm_way_id": None, "bridge": "no", "layer": "0", "tunnel": "no",
                  "travel_mode": "legacy_vehicle", "edge_kind": "grade_join"})
    return edges, nodes


def routing() -> flood_inputs.Frame:
    """The invented routing geometry: the whole grid."""

    return flood_inputs.Frame(flood_inputs.ROUTING_CONTEXT, "invented", MultiPolygon([box(WEST, NORTH - 2000.0, WEST + 2000.0, NORTH)]), {})


def roads_for(definitions: dict[str, tuple], reach: list[tuple[Any, float]]) -> Any:
    edges, nodes = graph(definitions)
    selected, lines = ct.select_edges(edges, nodes, reach)
    return ct.Roads(selected, nodes, lines, routing(), access_diff.closure_arguments(V1B),
                    int(V1B["closure_rule_v1"]["parameters"]["raster_minimum_polygon_px"]), GRID)


def dry_map() -> tuple[np.ndarray, np.ndarray]:
    """A central map where the radar answers every cell 'not flagged' (code 0, reason radar dry)."""

    return np.zeros((GRID.rows, GRID.cols), dtype="uint8"), np.full((GRID.rows, GRID.cols), m1z.REASON_RADAR_DRY, dtype="uint8")


def flag(code: np.ndarray, reason: np.ndarray, row: int | slice, col: int | slice) -> None:
    code[row, col], reason[row, col] = m1z.FLAGGED, m1z.REASON_FLAGGED


def no_answer(code: np.ndarray, reason: np.ndarray, row: int | slice, col: int | slice, why: int) -> None:
    code[row, col], reason[row, col] = m1z.NO_ANSWER, why


# ---------------------------------------------------------------------------------------------------------------------
# Times, footprints and cells
# ---------------------------------------------------------------------------------------------------------------------


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_the_window_of_test_3b_holds_both_ends_in_thai_time_and_leaves_out_the_31_july_pass() -> None:
    assert not ct.in_window_3b(utc("2025-07-19T16:59:59Z"))
    assert ct.in_window_3b(utc("2025-07-19T17:00:00Z"))
    assert ct.in_window_3b(utc("2025-07-31T16:59:59Z"))
    assert not ct.in_window_3b(utc("2025-07-31T17:00:00Z"))
    assert not ct.in_window_3b(utc("2025-07-31T23:08:03Z"))  # 1 August 06:08 Thai time
    assert ct.thai_date(utc("2025-07-25T23:06:50Z")) == "2025-07-26"
    assert ct.thai_date(utc("2025-07-22T11:22:07Z")) == "2025-07-22"


def test_the_footprint_of_a_pass_is_read_from_the_reasons_and_terrain_says_nothing() -> None:
    radar, outside, slope = m1z.REASON_RADAR_DRY, m1z.REASON_NO_RADAR_AFTER, m1z.REASON_TERRAIN_SLOPE
    assert ct.footprint_cover(np.array([radar, m1z.REASON_TREE_COVER_LOW, slope]))["status"] == "covered"
    assert ct.footprint_cover(np.array([outside, outside, slope]))["status"] == "not_covered"
    assert ct.footprint_cover(np.array([outside, radar]))["status"] == "partly_covered"
    assert ct.footprint_cover(np.array([slope, m1z.REASON_PERMANENT_WATER]))["status"] == "not_known_from_the_map"
    assert ct.footprint_cover(np.array([], dtype="uint8"))["status"] == "not_known_from_the_map"
    counted = ct.footprint_cover(np.array([outside, radar, slope, m1z.REASON_FLAGGED]))
    assert (counted["cells_with_radar_data_after"], counted["cells_without_radar_data_after"],
            counted["cells_answered_first_by_terrain_or_permanent_water"]) == (2, 1, 1)


def test_cells_near_a_geometry_are_those_whose_centre_lies_inside_or_within_the_distance() -> None:
    rows, cols = ct.cells_near(HOSPITAL_BOX, GRID, 0.0)
    assert len(rows) == 25 and set(rows.tolist()) == set(range(40, 45)) and set(cols.tolist()) == set(range(40, 45))
    rows, cols = ct.cells_near(Point(300_010.0, 801_990.0), GRID, 20.0)  # the centre of the corner cell and its neighbours
    assert sorted(zip(rows.tolist(), cols.tolist())) == [(0, 0), (0, 1), (1, 0)]
    rows, cols = ct.cells_near(HOSPITAL_BOX, GRID, 200.0)
    assert len(rows) > 25


# ---------------------------------------------------------------------------------------------------------------------
# Closure rule v1 at the central level, as the score chain applies it
# ---------------------------------------------------------------------------------------------------------------------


def test_the_central_closure_is_closure_rule_v1_on_the_flagged_cells_with_small_polygons_dropped() -> None:
    definitions = {
        "inside": (300_100, 801_910, 300_300, 801_910, "residential", "no"),      # wholly on flags: closed
        "trunk-long": (300_100, 801_510, 300_500, 801_510, "trunk", "no"),        # 120 m of 400 m on flags: closed by length
        "small-group": (300_100, 801_110, 300_300, 801_110, "residential", "no"),  # under 3 flagged cells: dropped, open
        "no-answer": (300_100, 800_710, 300_300, 800_710, "residential", "no"),    # under no-answer cells: open
        "bridge": (301_100, 801_910, 301_200, 801_910, "trunk", "yes"),           # 40 m of 100 m, a bridge: closed at a quarter
        "not-bridge": (301_100, 801_510, 301_200, 801_510, "trunk", "no"),        # the same without the tag: delayed
    }
    code, reason = dry_map()
    flag(code, reason, 4, slice(5, 15))
    flag(code, reason, 24, slice(5, 11))
    flag(code, reason, 44, slice(5, 8))
    no_answer(code, reason, 64, slice(5, 15), m1z.REASON_BUILT_UP_LOW)
    for row in (4, 24):  # two cells under the edge, three below it: one 8-connected polygon of five cells
        flag(code, reason, row, slice(55, 57))
        flag(code, reason, row + 1, slice(55, 58))
    roads = roads_for(definitions, [(box(WEST, NORTH - 2000.0, WEST + 2000.0, NORTH), 0.0)])
    closure = ct.central_closure(code, roads, tier="T2", flood_input_id="invented_map")
    assert closure["closed"] == {"inside", "trunk-long", "bridge"}
    assert closure["delayed"] == {"not-bridge"}
    assert closure["closure_basis"] == "modelled_from_invented_map" and closure["level"] == "central"
    assert closure["inside"]["trunk-long"]["intersection_length_m"] == pytest.approx(120.0, abs=0.01)
    assert closure["extent"]["polygons_dropped"] == 1
    assert "join-1" not in roads.lines  # the zero-length grade-join connector is left out
    # A raster of case N2 (tier T3) keeps its small polygons.
    reference = ct.central_closure(code, roads, tier="T3", flood_input_id="invented_reference")
    assert "small-group" in reference["closed"]


# ---------------------------------------------------------------------------------------------------------------------
# Test 3a on an invented chip
# ---------------------------------------------------------------------------------------------------------------------

FINE_WEST, FINE_NORTH, FINE_M = 300_900.0, 800_700.0, 2.0


def water_raster() -> np.ndarray:
    """Invented rule v2 water at 2 m over x 300,900 to 301,700 and y 800,100 to 800,700 (1 water, 0 not, 255 no value)."""

    fine = np.zeros((300, 400), dtype="uint8")
    fine[190:200, 100:200] = 1  # under c-wet-closed, 200 m
    fine[140:150, 100:130] = 1  # under c-wet-open, 60 m
    fine[190:200, 250:258] = 1  # under c-short, 16 m of its 30 m
    fine[170:180, 0:100] = 1    # under c-straddle, half of it outside the chip rectangle
    fine[275:300, :] = 255      # no value, away from every edge
    return fine


def fine_transform() -> Any:
    from rasterio.transform import from_origin

    return from_origin(FINE_WEST, FINE_NORTH, FINE_M, FINE_M)


def map_of_pass_3a() -> tuple[np.ndarray, np.ndarray]:
    code, reason = dry_map()
    for name in ("c-wet-closed", "c-dry-closed", "c-straddle", "e-uncovered"):
        x0, y0, x1, _y1, *_ = EDGES[name]
        row, first = cell(x0, y0)
        _row, last = cell(x1 - 1, y0)
        flag(code, reason, row, slice(first, last + 1))
    return code, reason


def test_rule_v2_water_is_read_as_the_test_stage_reads_it_and_only_inside_the_rectangle() -> None:
    water = ct.rule_v2_water(water_raster(), fine_transform(), CHIP)
    assert water[195, 150] == 1 and water[195, 300] == 0
    assert water[280, 200] == 255           # no value
    assert water[175, 20] == 255            # water, but outside the rectangle (x < 301,000)
    assert water[175, 80] == 1              # water inside the rectangle
    assert water[0, 200] == 255             # y above the rectangle's north edge


def test_3a_counts_the_closed_edges_seen_under_water_by_the_r26_rule() -> None:
    roads = roads_for(EDGES, [(box(CHIP["west"], CHIP["south"], CHIP["east"], CHIP["north"]), 0.0)])
    code, _reason = map_of_pass_3a()
    ours = ct.central_closure(code, roads, tier="T2", flood_input_id="invented_3a")
    reference = np.zeros_like(code)
    row, first = cell(301_100, 800_410)
    reference[row, first:first + 10] = 1
    theirs = ct.central_closure(reference, roads, tier="T3", flood_input_id="invented_n2")
    water = ct.rule_v2_water(water_raster(), fine_transform(), CHIP)
    found = ct.roads_under_theos2_water(roads, CHIP, water, fine_transform(), {"our_map": ours, "case_n2_reference": theirs})
    assert found["edges_crossing_the_rectangle"] == 5
    assert found["edges_compared"] == 4          # c-straddle has half its centreline outside: not compared
    assert found["edges_seen_under_water"] == 3  # c-wet-closed, c-wet-open, c-short (half of a short edge)
    mine = found["by_extent"]["our_map"]
    assert (mine["closed_edges_crossing_the_rectangle"], mine["closed_edges_compared"], mine["closed_edges_not_compared"]) == (3, 2, 1)
    assert mine["share_of_closed_edges_seen_under_water"]["by_edges"] == pytest.approx(0.5)
    assert mine["share_of_edges_seen_under_water_that_it_closes"]["by_edges"] == pytest.approx(1 / 3, abs=1e-6)
    listed = {row["edge_id"]: (row["closed"], row["seen_under_water"]) for row in mine["edges_closed_or_seen_under_water"]}
    assert listed == {"c-wet-closed": (True, True), "c-wet-open": (False, True), "c-dry-closed": (True, False), "c-short": (False, True)}
    other = found["by_extent"]["case_n2_reference"]
    assert other["share_of_closed_edges_seen_under_water"]["by_edges"] == pytest.approx(1.0)
    assert other["share_of_edges_seen_under_water_that_it_closes"]["by_edges"] == pytest.approx(1 / 3, abs=1e-6)
    assert "edges_closed_or_seen_under_water" not in other  # of case N2 only counts and shares


# ---------------------------------------------------------------------------------------------------------------------
# The committed records the stage reads (positions and metadata only)
# ---------------------------------------------------------------------------------------------------------------------


def test_the_committed_records_give_four_placed_points_one_unplaced_and_the_hospital_site() -> None:
    amendment = json.loads((ROOT / ct.AMENDMENT_1).read_text(encoding="utf-8"))
    stated = ct.check_amendment(amendment)
    assert stated["buffer_m"] == 300.0 and stated["hospital_osm_way"] == "315323384"
    record = json.loads((ROOT / ct.CONSEQUENCE_POINTS).read_text(encoding="utf-8"))
    specs = {spec.point_id: spec for spec in ct.point_specs(record)}
    assert [spec["id"] for spec in ct.POINTS_3B] == list(specs)
    assert specs["cut_nan021_km0_000"].geometry is None
    assert specs["cut_1243_km59_100"].geometry.geom_type == "Point"
    assert specs["cut_1243_km59_100"].placement["reading_consistent_with_the_lists_in_the_record"] == "southern_end"
    assert {spec.geometry.geom_type for name, spec in specs.items() if name not in ("cut_nan021_km0_000", "cut_1243_km59_100")} == {"LineString"}
    site = ct.hospital_spec(record, stated["hospital_osm_way"])
    assert site.about["area_m2_measured"] == pytest.approx(site.about["area_m2_in_the_record"], rel=1e-3)


def test_the_pass_catalogue_gives_the_passes_of_each_test() -> None:
    passes = ct.passes_of_record(json.loads((ROOT / ct.RADAR_RECORD).read_text(encoding="utf-8")))
    window = [item.key for item in passes if ct.in_window_3b(item.start)]
    assert "20250731T2308Z_s1a_o62" not in window and "20250719T2308Z_s1a_o62" in window
    assert ct.nearest_pass(passes, ct.parse_utc(ct.TEST_3A_PASS_UTC)).key == "20250731T2308Z_s1a_o62"
    assert [item.key for item in passes if ct.thai_date(item.start) == "2025-07-26"] == ["20250725T2306Z_s1c_o62"]


def test_another_list_of_points_in_the_amendment_is_refused() -> None:
    amendment = json.loads((ROOT / ct.AMENDMENT_1).read_text(encoding="utf-8"))
    amendment["changes"]["test_3b_points"]["points"] = amendment["changes"]["test_3b_points"]["points"][:4]
    with pytest.raises(ct.StageError):
        ct.check_amendment(amendment)
    amendment = json.loads((ROOT / ct.AMENDMENT_1).read_text(encoding="utf-8"))
    amendment["changes"]["test_3b_points"]["buffer_m"] = 500
    with pytest.raises(ct.StageError):
        ct.check_amendment(amendment)


# ---------------------------------------------------------------------------------------------------------------------
# The whole stage on an invented world
# ---------------------------------------------------------------------------------------------------------------------

PASSES = [
    # key, platform, orbit, start, status
    ("20250719T1659Z_s1a_o135", "Sentinel-1A", 135, "2025-07-19T16:59:59Z", "fetched"),     # one second before the window
    ("20250719T2308Z_s1a_o62", "Sentinel-1A", 62, "2025-07-19T23:08:07Z", "fetched"),      # A, 20 July Thai time
    ("20250722T1122Z_s1a_o99", "Sentinel-1A", 99, "2025-07-22T11:22:07Z", "fetched"),      # E, 22 July Thai time
    ("20250724T2316Z_s1a_o135", "Sentinel-1A", 135, "2025-07-24T23:16:16Z", "not fetched yet"),
    ("20250725T2306Z_s1c_o62", "Sentinel-1C", 62, "2025-07-25T23:06:50Z", "fetched"),      # B, 26 July Thai time
    ("20250731T2308Z_s1a_o62", "Sentinel-1A", 62, "2025-07-31T23:08:03Z", "fetched"),      # C, test 3a, 1 August Thai time
    ("20250806T2306Z_s1c_o62", "Sentinel-1C", 62, "2025-08-06T23:06:51Z", "not fetched yet"),
]


def maps_of_the_passes() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """The invented central maps of the fetched passes."""

    def edge_cells(name: str, count: int | None = None) -> tuple[int, slice]:
        x0, y0, x1, _y1, *_ = EDGES[name]
        row, first = cell(x0, y0)
        _row, last = cell(x1 - 1, y0)
        return row, slice(first, last + 1 if count is None else first + count)

    early = dry_map()
    flag(*early, *edge_cells("e-dry"))
    a = dry_map()
    flag(*a, *edge_cells("e-found"))
    no_answer(*a, slice(55, 96), slice(0, 45), m1z.REASON_NO_RADAR_AFTER)  # the footprint misses e-uncovered
    row, cols = edge_cells("e-trunk", 3)
    flag(*a, row, slice(cols.start + 5, cols.start + 8))                    # three cells under e-trunk: dropped
    e = dry_map()
    no_answer(*e, slice(40, 45), slice(40, 45), m1z.REASON_BUILT_UP_LOW)    # the hospital site without an answer
    b = dry_map()
    flag(*b, row, slice(cols.start + 5, cols.start + 11))                   # six cells: 120 m of e-trunk
    flag(*b, slice(40, 45), slice(35, 45))                                  # the site and the cells west of it, under e-hosp
    no_answer(*b, slice(45, 47), slice(40, 45), m1z.REASON_BUILT_UP_LOW)    # no answer just south of the site
    return {"20250719T1659Z_s1a_o135": early, "20250719T2308Z_s1a_o62": a, "20250722T1122Z_s1a_o99": e,
            "20250725T2306Z_s1c_o62": b, "20250731T2308Z_s1a_o62": map_of_pass_3a()}


def write_tif(path: Path, bands: list[tuple[str, np.ndarray]], *, west: float, north: float, size: float) -> str:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    rows, cols = bands[0][1].shape
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=cols, count=len(bands), dtype="uint8", nodata=255,
                       crs="EPSG:32647", transform=from_origin(west, north, size, size)) as target:
        for index, (name, values) in enumerate(bands, start=1):
            target.write(np.asarray(values, dtype="uint8"), index)
            target.set_band_description(index, name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line(*points: tuple[float, float]) -> dict[str, Any]:
    return mapping(LineString(points))


def build_world(tmp_path: Path) -> SimpleNamespace:
    """Write an invented repository root and external data root for one run of the stage."""

    root, external = tmp_path / "repo", tmp_path / "external"
    for name in (ct.AMENDMENT_1, ct.PROTOCOL_V1B):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, root / name)
    write_json(root / ct.PROTOCOL, {"schema": "invented", "grid": {"frame": {"west": WEST, "north": NORTH, "rows": GRID.rows, "cols": GRID.cols},
                                                                  "chips": {ct.CHIP_TOWN: CHIP}}})
    site = MultiPolygon([box(300_800.0, 801_100.0, 300_900.0, 801_200.0)])
    site_wgs84 = flood_inputs.project(site, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    write_json(root / ct.CONSEQUENCE_POINTS, {
        "inputs": {"osm_extract": {"retrieved_at_utc": "2026-07-10T00:00:00Z"}},
        "reported_cuts": [
            {"id": "cut_1243_km59_100", "route": "1243", "km_as_listed": "59+100", "status": "placed", "method": "tambon_part",
             "placed": {"epsg32647": line((300_100.0, 801_710.0), (300_500.0, 801_710.0))}, "placement_confidence": "low",
             "check_chainage_from_either_end": {"reading_consistent_with_the_lists": "southern_end",
                                                "km_59_100_from_southern_end": {"epsg32647": {"type": "Point", "coordinates": [300_300.0, 801_710.0]}}}},
            {"id": "cut_nan4020_km31_690", "route": "invented", "status": "placed", "method": "milestones",
             "placed": {"epsg32647": line((301_000.0, 801_710.0), (301_200.0, 801_710.0))}},
            {"id": "cut_nan4020_km10_500", "route": "invented", "status": "placed", "method": "milestones",
             "placed": {"epsg32647": line((300_300.0, 800_510.0), (300_500.0, 800_510.0))}},
            {"id": "cut_nan021_km0_000", "route": "invented", "status": "route_not_found", "placed": None},
        ],
        "supplementary_cuts": [
            {"id": "cut_nan3019_km7_000", "route": "invented", "status": "placed", "method": "milestones",
             "placed": {"epsg32647": line((301_500.0, 800_910.0), (301_700.0, 800_910.0))}},
        ],
        "hospitals": [{"id": "nan_hospital", "osm": {"type": "way", "id": "315323384"}, "name_th": "invented",
                       "tags": {"operator": "invented"}, "polygon": {"wgs84": mapping(site_wgs84), "area_m2": 10_000.0}}],
    })
    write_json(root / ct.NEWS_RECORDS, {
        "records": [{"id": "invented_hospital_record", "topic": "hospital", "published_local": "2025-07-24T08:13+07:00", "time_said": "invented"},
                    {"id": "invented_road_record", "topic": "road_cuts", "published_local": "2025-07-31T15:44+07:00", "time_said": "invented"}],
        "gauge_records": [{"station": "G.1", "place": "invented", "river": "invented", "peak_times_thai_time": ["2025-07-24 16:00"],
                           "levels": {"min_bank": {"level_m_msl": 10.0, "runs_above_thai_time": [["2025-07-23 09:00", "2025-07-26 10:00"]]}}}],
    })
    write_json(root / ct.RADAR_RECORD, {"event_passes": [
        {"key": key, "platform": platform, "relative_orbit": orbit, "start_utc": start, "status": status, "footprint_share_of_grid": 1.0}
        for key, platform, orbit, start, status in PASSES]})
    freeze_sha = write_json(root / ct.FREEZE, {"invented": "freeze record"})

    maps = external / ct.MAPS
    reference = np.zeros((GRID.rows, GRID.cols), dtype="uint8")
    row, first = cell(301_100, 800_410)
    reference[row, first:first + 10] = 1
    reference[0:5, :] = 255
    n2_sha = write_tif(external / ct.CASE_N2_REFERENCE / "reference_test_1_jaxa_20250728.tif",
                       [("reference: 1 water, 0 not water, 255 not observed", reference)], west=WEST, north=NORTH, size=CELL)
    test_sha = write_json(root / ct.TEST_RESULT, {"binding": {"reference_of_case_N2": {"name": "reference_test_1_jaxa_20250728.tif",
                                                                                         "sha256": n2_sha, "what": "invented"}}})
    index: dict[str, Any] = {"freeze_record": {"path": ct.FREEZE, "sha256": freeze_sha}, "test_result": {"sha256": test_sha}, "maps": {}}
    by_key = {key: (platform, orbit, start) for key, platform, orbit, start, _status in PASSES}
    for key, (code, reason) in maps_of_the_passes().items():
        platform, orbit, start = by_key[key]
        when = utc(start)
        label = f"{when:%Y%m%dT%H%M}_o{orbit}_S1{platform[-1]}"
        digest = write_tif(maps / f"m1z_{label}.tif", [("code_lower", code), ("code_central", code), ("code_upper", code),
                                                       ("reason_central", reason)], west=WEST, north=NORTH, size=CELL)
        write_json(maps / f"m1z_{label}.json", {"pass": {"time_utc": start, "relative_orbit": orbit, "platform": platform, "label": label},
                                                 "freeze_record": {"path": ct.FREEZE, "sha256": freeze_sha},
                                                 "map": {"name": f"m1z_{label}.tif", "sha256": digest}})
        index["maps"][label] = {"name": f"m1z_{label}.tif", "sha256": digest, "record": f"m1z_{label}.json"}
    write_json(maps / ct.MAPS_INDEX, index)

    context = external / ct.CONTEXT
    context.parent.mkdir(parents=True, exist_ok=True)
    context.write_bytes(b'{"invented": "context; the graph comes from the test hook"}\n')
    routing_sha = write_json(external / ct.ROUTING_GEOMETRY, {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(flood_inputs.project(
            box(WEST - 100.0, NORTH - 2100.0, WEST + 2100.0, NORTH + 100.0), flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS))}]})
    write_json(root / ct.FRAME_RECORD, {"files_outside_git": {"context": {"sha256": hashlib.sha256(context.read_bytes()).hexdigest()},
                                                               "routing_geometry": {"sha256": routing_sha}}})
    water_sha = write_tif(external / ct.RULE_V2_WORK / "water_v2_chip_003_2m.tif", [("water", water_raster())],
                          west=FINE_WEST, north=FINE_NORTH, size=FINE_M)
    write_json(root / ct.RULE_V2_FREEZE, {"frozen_rule": {"chips": {"chip_003": {"raster_outside_git": {"name": "water_v2_chip_003_2m.tif",
                                                                                                       "sha256": water_sha}}}}})
    edges, nodes = graph()
    hooks = {"load_graph": lambda path, external_root: (edges, nodes, {"canonical_sha256": "invented", "graph": {"road_nodes": len(nodes)}})}
    return SimpleNamespace(root=root, external=external, hooks=hooks, maps=maps, freeze_sha=freeze_sha)


def run_stage(world: SimpleNamespace, *extra: str) -> dict[str, Any]:
    return ct.run(["--external-root", str(world.external), *extra], root=world.root, hooks=world.hooks)


@pytest.fixture()
def world(tmp_path: Path) -> SimpleNamespace:
    return build_world(tmp_path)


def test_the_stage_on_an_invented_world_finds_two_of_the_five_points(world: SimpleNamespace) -> None:
    record = run_stage(world)
    written = json.loads((world.root / ct.OUTPUT).read_text(encoding="utf-8"))
    assert written["test_3b"]["measure"] == record["test_3b"]["measure"]
    assert b"\r\n" not in (world.root / ct.OUTPUT).read_bytes()
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[key]
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False

    t3b = record["test_3b"]
    assert [item["key"] for item in t3b["passes_in_the_window"]] == [
        "20250719T2308Z_s1a_o62", "20250722T1122Z_s1a_o99", "20250724T2316Z_s1a_o135", "20250725T2306Z_s1c_o62"]
    assert t3b["measure"]["listed_points"] == 5 and t3b["measure"]["placed"] == 4 and t3b["measure"]["found"] == 2
    assert t3b["measure"]["share_of_the_five_listed_points_found"] == pytest.approx(0.4)
    points = {row["id"]: row for row in t3b["points"]}

    found = points["cut_1243_km59_100"]                  # found: e-found closed on pass A
    assert found["found"] and found["found_on_passes"] == ["20250719T2308Z_s1a_o62"]
    first = found["passes"][0]
    assert [edge["edge_id"] for edge in first["closed_edges_within_the_buffer"]] == ["e-found"]
    assert first["closed_edges_within_the_buffer"][0]["osm_way_id"] == "invented-e-found"
    assert first["footprint"]["status"] == "covered"

    dry = points["cut_nan4020_km31_690"]                 # not found: closed only one second before the window
    assert not dry["found"]
    assert all(not entry.get("closed_edges_within_the_buffer") for entry in dry["passes"])

    uncovered = points["cut_nan4020_km10_500"]           # not found: not covered on A, dry on E and B, closed after the window
    assert not uncovered["found"]
    on_a = uncovered["passes"][0]
    assert on_a["footprint"]["status"] == "not_covered" and on_a["state"] == "the pass's footprint does not cover the point"
    assert uncovered["passes"][1]["footprint"]["status"] == "covered"

    unplaced = points["cut_nan021_km0_000"]              # not placed: counts as not found
    assert not unplaced["placed"] and not unplaced["found"]
    assert all(entry["state"] == "the point has no position" for entry in unplaced["passes"])

    supplementary = points["cut_nan3019_km7_000"]        # found on B by the trunk length rule; A's three cells are dropped
    assert supplementary["found_on_passes"] == ["20250725T2306Z_s1c_o62"]
    on_b = next(entry for entry in supplementary["passes"] if entry["pass"] == "20250725T2306Z_s1c_o62")
    assert on_b["closed_edges_within_the_buffer"][0]["length_inside_the_closure_extent_m"] == pytest.approx(120.0, abs=0.1)

    not_fetched = next(entry for entry in found["passes"] if entry["pass"] == "20250724T2316Z_s1a_o135")
    assert not_fetched["map"] is None and not_fetched["state"] == "no map of this pass"


def test_the_stage_reports_test_3a_and_the_case_n2_extent(world: SimpleNamespace) -> None:
    t3a = run_stage(world)["test_3a"]
    assert t3a["pass"]["key"] == "20250731T2308Z_s1a_o62"
    assert t3a["edges_compared"] == 4 and t3a["edges_seen_under_water"] == 3
    mine = t3a["by_extent"]["our_map"]
    assert mine["share_of_closed_edges_seen_under_water"]["by_edges"] == pytest.approx(0.5)
    assert mine["share_of_edges_seen_under_water_that_it_closes"]["by_edges"] == pytest.approx(1 / 3, abs=1e-6)
    assert t3a["case_n2_reference"]["given"] and t3a["case_n2_reference"]["report_only"]
    assert t3a["by_extent"]["case_n2_reference"]["closed_edges_compared"] == 1


def test_the_stage_reports_the_hospital_on_22_and_26_july_beside_the_news(world: SimpleNamespace) -> None:
    t4 = run_stage(world)["test_4"]
    assert t4["check_only"] is True and t4["pass_mark"] is None
    assert t4["news_records_cited"] == ["invented_hospital_record"]
    by_day = {entry["thai_date"]: entry for entry in t4["passes"]}
    before, after = by_day["2025-07-22"], by_day["2025-07-26"]
    assert before["pass"]["key"] == "20250722T1122Z_s1a_o99"
    assert before["cells_inside_the_site"]["no_answer"] == 25 and before["cells_inside_the_site"]["flagged"] == 0
    assert before["closed_edges_within_200_m"] == []
    assert after["pass"]["key"] == "20250725T2306Z_s1c_o62"
    assert after["cells_inside_the_site"]["flagged"] == 25
    assert after["cells_inside_or_within_200_m"]["flagged"] == 50
    assert after["cells_inside_or_within_200_m"]["no_answer"] == 10
    assert [edge["edge_id"] for edge in after["closed_edges_within_200_m"]] == ["e-hosp"]
    assert after["news_records_beside"][0]["id"] == "invented_hospital_record"
    assert after["news_records_beside"][0]["hours_from_the_pass_to_publication"] == pytest.approx(-45.9, abs=0.1)
    assert after["gauges_at_the_pass"][0]["levels"]["min_bank"]["above_at_the_pass"] is True
    assert before["gauges_at_the_pass"][0]["levels"]["min_bank"]["above_at_the_pass"] is False


def test_the_record_names_the_freeze_the_test_result_and_every_input_by_sha256(world: SimpleNamespace) -> None:
    record = run_stage(world)
    assert record["order"]["freeze_record"]["sha256"] == world.freeze_sha
    assert record["order"]["test_result"]["sha256"] == hashlib.sha256((world.root / ct.TEST_RESULT).read_bytes()).hexdigest()
    assert record["order"]["maps_index"]["test_result_matches"] is True
    for name in ("protocol", "amendment_1", "consequence_points", "news_records", "radar_record", "frame_record", "rule_v2_freeze",
                 "context", "routing_geometry", "rule_v2_water_chip_003", "case_n2_reference"):
        assert len(record["inputs"][name]["sha256"]) == 64
    assert set(record["inputs"]["maps"]) == {"20250719T2308Z_s1a_o62", "20250722T1122Z_s1a_o99", "20250725T2306Z_s1c_o62",
                                             "20250731T2308Z_s1a_o62"}
    assert record["rules"]["edges_measured"]["road_edges_the_tests_read"] < record["rules"]["edges_measured"]["edges_of_the_graph"]


def test_the_stage_refuses_before_the_test_result_exists(world: SimpleNamespace) -> None:
    (world.root / ct.TEST_RESULT).unlink()
    with pytest.raises(ct.StageError, match="test_result_v1.json does not exist"):
        run_stage(world)
    assert not (world.root / ct.OUTPUT).exists()


def test_the_stage_runs_once_unless_replaced_with_a_reason(world: SimpleNamespace) -> None:
    run_stage(world)
    with pytest.raises(ct.StageError, match="runs once"):
        run_stage(world)
    with pytest.raises(ct.StageError, match="needs --reason"):
        run_stage(world, "--replace")
    again = run_stage(world, "--replace", "--reason", "invented second run")
    assert again["supersedes"]["reason"] == "invented second run"


def test_the_stage_refuses_a_map_made_under_another_freeze(world: SimpleNamespace) -> None:
    record_path = next(world.maps.glob("m1z_20250719T2308*.json"))
    found = json.loads(record_path.read_text(encoding="utf-8"))
    found["freeze_record"]["sha256"] = "0" * 64
    record_path.write_text(json.dumps(found), encoding="utf-8")
    with pytest.raises(ct.StageError, match="freeze record in force"):
        run_stage(world)


def test_the_stage_refuses_a_fetched_pass_without_a_map(world: SimpleNamespace) -> None:
    for path in world.maps.glob("m1z_20250722T1122*"):
        path.unlink()
    with pytest.raises(ct.StageError, match="has no map"):
        run_stage(world)


def test_the_firewall_refuses_the_sealed_folder_and_the_dry_chip_and_holds_chip_003_until_the_test(tmp_path: Path) -> None:
    with pytest.raises(ct.StageError, match="sealed"):
        ct.firewall(tmp_path / "proposal_execution" / "nan_case_v1" / "jaxa_sealed" / "a.zip", tmp_path)
    with pytest.raises(ct.StageError, match="firewall"):
        ct.firewall(tmp_path / "water_v2_chip_001_2m.tif", tmp_path)
    with pytest.raises(ct.StageError, match="firewall"):
        ct.firewall(tmp_path / "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif", tmp_path)
    with pytest.raises(ct.StageError, match="only after the test"):
        ct.firewall(tmp_path / "water_v2_chip_003_2m.tif", tmp_path)
    (tmp_path / ct.TEST_RESULT).parent.mkdir(parents=True)
    (tmp_path / ct.TEST_RESULT).write_text("{}", encoding="utf-8")
    ct.firewall(tmp_path / "water_v2_chip_003_2m.tif", tmp_path)


def test_the_context_must_be_the_file_the_frame_record_names(world: SimpleNamespace) -> None:
    (world.external / ct.CONTEXT).write_bytes(b"{}\n")
    with pytest.raises(ct.StageError, match="not the context"):
        run_stage(world)


# ---------------------------------------------------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------------------------------------------------


def test_the_wording_of_the_stage_and_of_its_record_passes_the_shared_lint(world: SimpleNamespace) -> None:
    script = "\n".join(python_strings(SCRIPT.read_text(encoding="utf-8")))
    assert lint_texts([(str(SCRIPT.name), script)], WORDING_RULES) == []
    record = run_stage(world)
    texts = [(path, text) for path, text in json_strings(record)]
    assert lint_texts(texts, WORDING_RULES) == []
