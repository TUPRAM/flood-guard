"""The frame and planning context of the Nan case N1 (decision log R51).

Most tests run the rules of ``floodguard.nan_frame`` and parts of ``scripts/nan_case_frame.py`` on invented
squares, invented roads and an invented raster. The last tests read the committed case protocol and, when it
exists, the committed record ``outputs/nan_case/frame_v1.json``. Nothing here reads a flood layer or computes a
flood flag, a closure, an access loss, a component, an FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import pytest
from shapely.geometry import Point, box

from floodguard import access_diff, nan_frame, planning_assessment, planning_context
from floodguard.access_diff import ServiceRule
from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.wording_lint import find_violations, json_strings, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "proposal_execution" / "nan_case_protocol_v1.json"
AREAS = ROOT / "outputs" / "nan_case" / "areas_v1.json"
RECORD = ROOT / "outputs" / "nan_case" / "frame_v1.json"
SCRIPT = ROOT / "scripts" / "nan_case_frame.py"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
STEP = 0.01


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("nan_case_frame", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _unit(code: str, district: str, name: str, geometry: Any) -> dict[str, Any]:
    return {"adm3_pcode": code, "adm3_name": f"Unit {code}", "adm3_name_th": f"th {code}", "adm2_pcode": district,
            "adm2_name": name, "adm1_pcode": district[:4], "valid_on": "2022-01-22", "geometry": geometry}


def _rows() -> list[dict[str, Any]]:
    """11, 7 and 17 invented squares for the three districts, and two squares of a fourth district."""

    rows = []
    for column, (code, name, count) in enumerate(nan_frame.DISTRICTS):
        for number in range(1, count + 1):
            square = box(100.0 + column * STEP, 18.0 + number * STEP, 100.0 + (column + 1) * STEP,
                         18.0 + (number + 1) * STEP)
            rows.append(_unit(f"{code}{number:02d}", code, name, square))
    rows += [_unit(f"TH5502{number:02d}", "TH5502", "Another district", box(101.0, 18.0, 101.01, 18.01))
             for number in (1, 2)]
    return rows


# ---------------------------------------------------------------------------
# The protocol and the units
# ---------------------------------------------------------------------------


def test_the_committed_protocol_states_the_frame_this_lane_builds() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    stated = nan_frame.check_protocol_frame(protocol)
    areas = json.loads(AREAS.read_text(encoding="utf-8"))["areas"]["nan_frame"]["grid"]
    assert {key: stated["grid"][key] for key in ("west", "north", "rows", "cols")} == areas
    assert stated["grid"] == {"west": 639520, "north": 2111500, "rows": 4303, "cols": 4280, "epsg": 32647, "cell_m": 20}
    for change in (("case_id", "N2"), ("frame.district_pcodes", ["TH5501", "TH5507", "TH5514"]),
                   ("frame.units", "every unit (36 units)"), ("grid.cell_m", 10)):
        broken = deepcopy(protocol)
        target = broken
        *parents, key = change[0].split(".")
        for parent in parents:
            target = target[parent]
        target[key] = change[1]
        with pytest.raises(nan_frame.NanFrameError):
            nan_frame.check_protocol_frame(broken)


def test_frame_units_takes_the_three_districts_and_checks_each_count() -> None:
    units = nan_frame.frame_units(_rows())
    assert len(units) == nan_frame.EXPECTED_UNITS
    assert [row["adm3_pcode"] for row in units] == sorted(row["adm3_pcode"] for row in units)
    assert {row["adm2_pcode"] for row in units} == {"TH5501", "TH5514", "TH5507"}
    short = [row for row in _rows() if row["adm3_pcode"] != "TH550705"]
    with pytest.raises(nan_frame.NanFrameError, match="TH5507 has 16 units"):
        nan_frame.frame_units(short)
    renamed = _rows()
    renamed[0]["adm2_name"] = "Mueang Nan District"
    with pytest.raises(nan_frame.NanFrameError, match="named"):
        nan_frame.frame_units(renamed)


def test_the_grid_is_the_buffered_union_snapped_outward_to_20_m() -> None:
    # The bounds of the real buffered union (EPSG:32647), as measured when the case protocol was written.
    grid = nan_frame.snapped_grid((639533.9513579708, 2025458.5937510757, 725109.2463370211, 2111487.362384418))
    assert grid == {"west": 639520, "north": 2111500, "rows": 4303, "cols": 4280}
    assert nan_frame.snapped_grid((0.0, 0.0, 40.0, 40.0)) == {"west": 0, "north": 40, "rows": 2, "cols": 2}
    assert nan_frame.snapped_grid((-1.0, -1.0, 1.0, 1.0)) == {"west": -20, "north": 20, "rows": 2, "cols": 2}
    check = nan_frame.compare_grid({"west": 0, "north": 40, "rows": 2, "cols": 3}, {"west": 0, "north": 40, "rows": 2, "cols": 2})
    assert check["differing_keys"] == ["cols"] and check["same"] is False
    with pytest.raises(nan_frame.NanFrameError):
        nan_frame.snapped_grid((1.0, 1.0, 1.0, 2.0))


def test_grid_cell_places_points_by_floor_and_refuses_points_outside() -> None:
    grid = {"west": 0, "north": 100, "rows": 5, "cols": 4}
    assert nan_frame.grid_cell(0.0, 100.0, grid) == (0, 0)
    assert nan_frame.grid_cell(19.999, 80.001, grid) == (0, 0)
    assert nan_frame.grid_cell(20.0, 80.0, grid) == (1, 1)
    assert nan_frame.grid_cell(79.9, 0.1, grid) == (4, 3)
    assert nan_frame.grid_cell(80.0, 50.0, grid) is None
    assert nan_frame.grid_cell(10.0, 100.5, grid) is None


def test_unit_table_gives_areas_and_raster_values_in_code_order() -> None:
    units = [_unit("TH550102", "TH5501", "Mueang Nan", box(0, 0, 1000, 2000)),
             _unit("TH550101", "TH5501", "Mueang Nan", box(1000, 0, 2000, 1000))]
    table = nan_frame.unit_table(units, lambda geometry: geometry)
    assert [(row["adm3_pcode"], row["raster_value"], row["area_km2"]) for row in table] == [
        ("TH550101", 1, 1.0), ("TH550102", 2, 2.0)]
    assert nan_frame.containing_units(Point(1000, 500), units) == ["TH550101", "TH550102"]
    assert nan_frame.containing_units(Point(500, 1500), units) == ["TH550102"]
    assert nan_frame.containing_units(Point(5000, 5000), units) == []


# ---------------------------------------------------------------------------
# Main-road destinations
# ---------------------------------------------------------------------------


def _edge(edge_id: str, start: str, end: str, road_class: str, way: str, minutes: float = 1.0, **extra: Any) -> dict[str, Any]:
    return {"edge_id": edge_id, "from_node": start, "to_node": end, "road_class": road_class, "osm_way_id": way,
            "normal_minutes": minutes, "length_m": minutes * 1000, "bridge": "no", "tunnel": "no", "layer": "0", **extra}


def test_main_road_summary_counts_the_entries_of_trunk_and_primary_edges() -> None:
    edges = [_edge("e1", "a", "b", "trunk", "10"), _edge("e2", "b", "c", "primary", "11"),
             _edge("e3", "c", "d", "residential", "12"),
             _edge("j1", "c", "x", "primary", "13", edge_kind="grade_join_connector")]
    coordinates = {node: [100.0 + index * 0.001, 18.0] for index, node in enumerate("abcdx")}
    entries = planning_context.main_road_entries({"edges": edges, "node_coordinates": coordinates})
    summary = nan_frame.main_road_summary(entries, edges)
    assert summary["entries"] == 3 and [row["node_id"] for row in entries] == ["a", "b", "c"]
    assert summary["node_ids_sha256"] == planning_context.sha256_bytes(
        json.dumps(["a", "b", "c"], separators=(",", ":")).encode("ascii"))
    assert summary["osm_ways"] == [{"osm_way_id": "10", "road_classes": ["trunk"]},
                                   {"osm_way_id": "11", "road_classes": ["primary"]}]
    assert summary["entries_by_road_class"] == {"primary": 2, "trunk": 2}
    assert summary["ways_by_road_class"] == {"primary": 1, "trunk": 1}
    with pytest.raises(nan_frame.NanFrameError):
        nan_frame.main_road_summary(entries, edges[2:])


# ---------------------------------------------------------------------------
# Demand cells
# ---------------------------------------------------------------------------


def _metres(lon: float, lat: float) -> tuple[float, float]:
    """An invented projection: one degree is 100 km, so the grid arithmetic is easy to check."""

    return (lon - 100.0) * 100_000.0, (lat - 18.0) * 100_000.0


def test_demand_rows_count_each_cell_for_the_unit_that_holds_its_centre() -> None:
    units = [("TH550101", box(100.0, 18.0, 100.001, 18.001)), ("TH550102", box(100.001, 18.0, 100.002, 18.001))]
    population = [
        {"population_id": "c1", "total_population": 10.0, "longitude": 100.0005, "latitude": 18.0005,
         "node_id": "n1", "snap_distance_m": 5.0},
        {"population_id": "c2", "total_population": 4.0, "longitude": 100.0015, "latitude": 18.0002,
         "node_id": None, "snap_distance_m": 300.0},
        {"population_id": "c3", "total_population": 2.5, "longitude": 100.001, "latitude": 18.0005,
         "node_id": "n2", "snap_distance_m": 1.0},  # on the shared boundary: in no unit row
        {"population_id": "c4", "total_population": 1.0, "longitude": 100.01, "latitude": 18.01,
         "node_id": None, "snap_distance_m": None},  # outside both units
    ]
    assignment = access_diff.assign_cells(population, units)
    grid = {"west": 0, "north": 200, "rows": 10, "cols": 10}
    rescaled = {"c1": 12.0, "c2": 4.0, "c3": 3.0, "c4": 1.0}
    rows = nan_frame.demand_rows(population, assignment, _metres, grid, rescaled, {"c2": True})
    index = {name: position for position, name in enumerate(nan_frame.DEMAND_COLUMNS)}
    by_id = {row[index["population_id"]]: row for row in rows}
    assert by_id["c1"][index["unit_id"]] == "TH550101"
    assert by_id["c2"][index["unit_id"]] == "TH550102" and by_id["c2"][index["kept_at_2020"]] is True
    assert by_id["c3"][index["unit_id"]] is None and by_id["c3"][index["unit_assignment"]] == access_diff.CELL_IN_SEVERAL_UNITS
    assert by_id["c4"][index["unit_assignment"]] == access_diff.CELL_IN_NO_UNIT
    assert (by_id["c1"][index["x_32647"]], by_id["c1"][index["y_32647"]]) == (50.0, 50.0)
    assert (by_id["c1"][index["grid_row"]], by_id["c1"][index["grid_col"]]) == (7, 2)
    assert by_id["c4"][index["grid_row"]] is None  # 1 km east of the invented grid
    summary = nan_frame.demand_summary(rows, ["TH550101", "TH550102", "TH550103"])
    assert summary["demand_cells"] == 4 and summary["residents_2020"] == 17.5
    assert summary["residents_rescaled_2024"] == 20.0
    assert summary["by_unit"]["TH550101"] == {"demand_cells": 1, "residents_2020": 10.0, "residents_rescaled_2024": 12.0}
    assert summary["by_unit"]["TH550103"]["demand_cells"] == 0
    assert summary["cells_in_no_unit_or_several"] == {"demand_cells": 2, "residents_2020": 3.5, "residents_rescaled_2024": 4.0}
    assert summary["cells_outside_the_grid"] == 1
    with pytest.raises(nan_frame.NanFrameError):
        nan_frame.demand_rows(population, assignment, _metres, grid, {"c1": 1.0})
    with pytest.raises(nan_frame.NanFrameError):
        nan_frame.demand_rows([*population, population[0]], assignment, _metres, grid)
    not_rescaled = nan_frame.demand_rows(population, assignment, _metres, grid)
    assert nan_frame.demand_summary(not_rescaled, ["TH550101", "TH550102"])["residents_rescaled_2024"] is None


# ---------------------------------------------------------------------------
# Baseline access
# ---------------------------------------------------------------------------


SERVICES = (ServiceRule(access_diff.HOSPITAL, access_diff.VEHICLE, (15, 30, 60), 30, access_diff.PUBLIC_LEVEL),
            ServiceRule(access_diff.MAIN_ROAD_ENTRY, access_diff.VEHICLE, (15, 30, 60), 15, access_diff.PUBLIC_LEVEL))


def _baseline() -> tuple[list[dict[str, Any]], dict[str, dict[str, float | None]]]:
    """A road a-b-c-d with a hospital at d and a main-road entry at b; a separate road e-f with nothing on it."""

    edges = [_edge("ab", "a", "b", "primary", "1", minutes=10.0), _edge("bc", "b", "c", "residential", "2", minutes=10.0),
             _edge("cd", "c", "d", "residential", "3", minutes=15.0), _edge("ef", "e", "f", "residential", "4", minutes=2.0)]
    nodes = access_diff.graph_nodes(edges)
    population = [
        {"population_id": "p1", "node_id": "c", "snap_distance_m": 0.0},   # hospital 15 min, main road 10 min
        {"population_id": "p2", "node_id": "a", "snap_distance_m": 0.0},   # hospital 35 min, main road 10 min
        {"population_id": "p3", "node_id": "e", "snap_distance_m": 0.0},   # connected, no route to anything
        {"population_id": "p4", "node_id": None, "snap_distance_m": None},  # not connected
    ]
    destinations = {
        access_diff.HOSPITAL: [{"facility_id": "H", "node_id": "d", "snap_distance_m": 0.0}],
        access_diff.MAIN_ROAD_ENTRY: [{"facility_id": "M", "node_id": "b", "snap_distance_m": 0.0}],
    }
    runs = {service: access_diff.cell_minutes(population, edges, rows, baseline_nodes=nodes)
            for service, rows in destinations.items()}
    cells = [{"population_id": "p1", "unit_id": "U1", "residents": 10.0},
             {"population_id": "p2", "unit_id": "U1", "residents": 5.0},
             {"population_id": "p3", "unit_id": "U2", "residents": 3.0},
             {"population_id": "p4", "unit_id": "U2", "residents": 2.0}]
    return cells, runs


def test_baseline_rows_count_access_within_the_gap_thresholds_and_the_no_route_share() -> None:
    cells, runs = _baseline()
    table = access_diff.unit_rows(cells, ["U1", "U2", "U3"], SERVICES, runs, runs)
    result = nan_frame.baseline_table(table, hospital_gap_minutes=30, main_road_gap_minutes=15,
                                      no_route_share=planning_assessment.baseline_no_route_share)
    by_unit = {row["unit_id"]: row for row in result["units"]}
    one, two, three = by_unit["U1"], by_unit["U2"], by_unit["U3"]
    assert one["residents"] == 15.0 and one["residents_connected_to_the_graph"] == 15.0
    assert one["hospital_within_30_minutes_residents"] == 10.0  # p2 needs 35 minutes
    assert one["main_road_within_15_minutes_residents"] == 15.0
    assert one["services"][access_diff.HOSPITAL]["baseline_access_residents_by_threshold_minutes"] == {
        "15": 10.0, "30": 10.0, "60": 15.0}
    assert one["connected_residents_without_a_hospital_route"] == 0.0 and one["baseline_vehicle_no_route_share"] == 0.0
    assert two["residents_not_connected_to_the_graph"] == 2.0 and two["residents_connected_to_the_graph"] == 3.0
    assert two["connected_residents_without_a_hospital_route"] == 3.0 and two["baseline_vehicle_no_route_share"] == 1.0
    assert two["connected_residents_without_any_route"] == 3.0
    assert three["residents"] == 0.0 and three["baseline_vehicle_no_route_share"] == 1.0  # nobody connected: 1 (C7)
    whole = result["whole_frame"]
    assert whole["residents"] == 20.0 and whole["connected_residents_without_a_hospital_route"] == 3.0
    assert math.isclose(whole["baseline_vehicle_no_route_share"], 3.0 / 18.0)


def test_a_row_with_a_flooded_run_is_refused_as_a_baseline() -> None:
    cells, runs = _baseline()
    flooded = {service: dict(minutes) for service, minutes in runs.items()}
    flooded[access_diff.HOSPITAL]["p1"] = None
    table = access_diff.unit_rows(cells, ["U1", "U2"], SERVICES, runs, flooded)
    with pytest.raises(nan_frame.NanFrameError, match="baseline-only"):
        nan_frame.baseline_table(table, hospital_gap_minutes=30, main_road_gap_minutes=15,
                                 no_route_share=planning_assessment.baseline_no_route_share)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def _record() -> dict[str, Any]:
    return {"generated_at_utc": "2026-10-14T00:00:00Z", "source_timestamp": "2026-07-10T02:46:49Z",
            "confidence_class": "low", "assumptions": ["An invented sentence."], "official_warning": False,
            "operational_status": "non_operational", "name": "\u0e19\u0e48\u0e32\u0e19"}


def test_records_need_the_provenance_fields_and_encode_as_ascii_with_lf() -> None:
    data = nan_frame.encode_record(_record())
    assert data.endswith(b"}\n") and b"\r" not in data and data.decode("ascii")
    assert json.loads(data)["name"] == "\u0e19\u0e48\u0e32\u0e19"
    assert nan_frame.encode_record(_record(), indent=None).count(b"\n") == 1
    for key, value in (("official_warning", True), ("operational_status", "operational"), ("assumptions", []),
                       ("generated_at_utc", "2026-10-14 00:00"), ("source_timestamp", " ")):
        broken = {**_record(), key: value}
        with pytest.raises(nan_frame.NanFrameError):
            nan_frame.encode_record(broken)
    missing = _record()
    del missing["confidence_class"]
    with pytest.raises(nan_frame.NanFrameError):
        nan_frame.check_record(missing)


# ---------------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------------


def test_the_script_takes_its_locations_from_arguments_and_never_opens_the_sealed_folder(tmp_path: Path) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "C:/" not in source and "C:\\" not in source and "Users" not in source
    assert "FloodGuard_external_data" not in source
    script = _script()
    with pytest.raises(script.FrameBuildError):
        script.refuse_sealed(tmp_path / "nan_case_v1" / "jaxa_sealed" / "anything.zip")
    script.refuse_sealed(tmp_path / "nan_case_v1" / "frame")
    with pytest.raises(SystemExit):
        script.parse_args(["--external-root", str(tmp_path), "--work-dir", str(ROOT / "outputs"), "--stage", "frame"])
    with pytest.raises(SystemExit):
        script.parse_args(["--external-root", str(tmp_path), "--stage", "age"])  # the age stage needs --age-dir
    with pytest.raises(SystemExit):
        script.parse_args(["--external-root", str(tmp_path), "--stage", "record", "--replace"])
    args = script.parse_args(["--external-root", str(tmp_path), "--stage", "frame"])
    assert args.work_dir == tmp_path / "proposal_execution" / "nan_case_v1" / "frame"
    assert script.parse_args(["--external-root", str(tmp_path), "--stage", "verify"]).stage == "verify"
    label = script.label(tmp_path / "proposal_execution" / "x.json", tmp_path)
    assert label == "<external_data_workspace>/proposal_execution/x.json"
    assert script.external_path(label, tmp_path) == tmp_path / "proposal_execution" / "x.json"
    with pytest.raises(script.FrameBuildError):
        script.external_path("outputs/nan_case/frame_v1.json", tmp_path)


def test_the_unit_raster_takes_the_unit_of_each_cell_centre(tmp_path: Path) -> None:
    import rasterio

    script = _script()
    grid = {"west": 0, "north": 640, "rows": 32, "cols": 32}
    units = [_unit("TH550101", "TH5501", "Mueang Nan", box(0, 0, 320, 640)),
             _unit("TH550102", "TH5501", "Mueang Nan", box(300, 0, 640, 320))]  # overlaps the first by one column
    table = nan_frame.unit_table(units, lambda geometry: geometry)
    path = tmp_path / "units.tif"
    result = script.unit_raster(path, units, table, grid, lambda geometry: geometry, "2026-10-14T00:00:00Z")
    with rasterio.open(path) as source:
        values = source.read(1)
        assert source.crs.to_epsg() == 32647 and source.profile["compress"].lower() == "deflate"
        assert source.profile["tiled"] is True and source.transform.a == 20.0
        assert source.tags()["official_warning"] == "false"
    assert values[0, 0] == 1 and values[31, 31] == 2 and values[0, 31] == nan_frame.UNIT_RASTER_NONE
    assert values[20, 15] == nan_frame.UNIT_RASTER_SEVERAL  # centre x = 310 m lies in both squares
    assert result["cells_in_several_units"] == 16 and result["cells_with_a_unit"] == 32 * 16 + 16 * 16 - 16


def test_the_boundless_check_reads_past_the_raster_edge(tmp_path: Path) -> None:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    script = _script()
    path = tmp_path / "population.tif"
    data = np.array([[1.0, 2.0, -99999.0, 0.0], [3.0, 4.0, 5.0, 6.0]], dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", height=2, width=4, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(100.0, 18.002, 0.001, 0.001), nodata=-99999.0) as target:
        target.write(data, 1)
    # The unit reaches 1.5 cells north of the raster's top edge: the read must be boundless.
    units = [{"geometry": box(100.0, 18.0, 100.003, 18.0035)}]
    population = [{"total_population": value} for value in (1.0, 2.0, 3.0, 4.0, 5.0)]
    check = script.boundless_check(path, units, population)
    assert check["window_inside_the_raster"] is False
    assert check["independent_read"] == {"cells": 5, "residents_2020": 15.0}  # 0 and nodata are not demand; 6 is outside
    assert check["cell_difference"] == 0 and check["resident_difference"] == 0.0


def test_the_texts_of_the_module_and_the_script_pass_the_shared_wording_lint() -> None:
    items = [("script", text) for text in python_strings(SCRIPT.read_text(encoding="utf-8"))]
    items += [("module", text) for text in python_strings((ROOT / "src" / "floodguard" / "nan_frame.py").read_text(encoding="utf-8"))]
    assert len(items) > 100
    findings = [finding.describe() for source, text in items for finding in find_violations(text, RULES, source)]
    assert findings == []
    assert find_violations("The frame was validated against the JAXA map.", RULES)


# ---------------------------------------------------------------------------
# The committed record
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def record() -> dict[str, Any]:
    if not RECORD.is_file():
        pytest.skip("outputs/nan_case/frame_v1.json is not built in this checkout")
    data = RECORD.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n") and data.decode("ascii")
    return json.loads(data)


def test_the_record_carries_provenance_and_passes_the_wording_lint(record: dict[str, Any]) -> None:
    nan_frame.check_record(record)
    assert record["confidence_class"] in VALID_CONFIDENCE_CLASSES
    assert record["case_id"] == "N1" and record["schema"] == "floodguard.nan_case_frame.v1"
    findings = [finding.describe() for path, text in json_strings(record) for finding in find_violations(text, RULES, path)]
    assert findings == []


def test_the_record_holds_the_35_units_their_hospitals_and_their_baseline(record: dict[str, Any]) -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    units = record["units"]
    assert len(units) == 35 and record["counts"]["units_by_district"] == {"TH5501": 11, "TH5514": 7, "TH5507": 17}
    assert sorted({row["adm2_pcode"] for row in units}) == sorted(protocol["frame"]["district_pcodes"])
    assert [row["raster_value"] for row in units] == list(range(1, 36))
    assert math.isclose(sum(row["area_km2"] for row in units), record["frame_area_km2"], abs_tol=1e-3)
    assert record["grid_check"]["same"] is True
    hospitals = record["hospitals"]["hospitals"]
    assert len(hospitals) == record["hospitals"]["counts"]["osm_objects"] == record["counts"]["osm_hospital_objects"]
    assert record["hospitals"]["context_check"]["same"] is True
    assert all(row["destination_in_the_context"] for row in hospitals)
    baseline = record["baseline_access"]
    assert [row["unit_id"] for row in baseline["units"]] == [row["adm3_pcode"] for row in units]
    assert baseline["check_against_the_context_receipt"]["same"] is True
    for row in baseline["units"]:
        assert 0.0 <= row["baseline_vehicle_no_route_share"] <= 1.0
        assert row["hospital_within_30_minutes_residents"] <= row["residents_connected_to_the_graph"] + 1e-6
        assert row["main_road_within_15_minutes_residents"] <= row["residents_connected_to_the_graph"] + 1e-6
        assert math.isclose(row["residents"], row["residents_connected_to_the_graph"]
                            + row["residents_not_connected_to_the_graph"], abs_tol=1e-3)
    whole = baseline["whole_frame_worldpop_2020"]
    in_units = sum(row["residents"] for row in baseline["units"])
    assert math.isclose(in_units + baseline["cells_in_no_unit"]["residents"], whole["residents"], rel_tol=1e-9)


def test_the_record_names_files_outside_git_only_by_placeholder_and_hash(record: dict[str, Any]) -> None:
    text = RECORD.read_text(encoding="ascii")
    assert "C:\\\\" not in text and "C:/" not in text and "Users" not in text
    for name, entry in record["files_outside_git"].items():
        assert entry["path"].startswith("<external_data_workspace>/proposal_execution/nan_case_v1/frame/"), name
        assert len(entry["sha256"]) == 64
    assert "jaxa" not in text.lower().replace("no jaxa, gfm or theos-2 file was opened by this lane", "")
