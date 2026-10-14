"""The score chain of the Nan case, on invented data only.

Two parts. The pure parts of ``floodguard.nan_case_chain`` are checked on invented arrays, polygons and confidence
inputs: the raster codes, the footprints, the report-only no-answer figures, the Nan binding rule in the place of
the T2 skill condition, the checks of a result file, the headline over the cells run and the firewall. Then the
whole chain (``scripts/nan_case_chain.py``) is run on an invented frame in the open sea (two units, a road graph of
nine nodes, seven demand cells, three flood rasters on a 20 m grid with no-answer cells, a land-cover raster and an
age table) and its result is checked against figures worked out by hand. No layer of a real place is read. What is
real is what every run reads unchanged: the two signed protocol files, the Nan protocol file and the national-anchor
receipt protocol v1b names.
"""

from __future__ import annotations

from datetime import date
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest
from pyproj import Transformer
import shapely
from shapely.geometry import LineString, box, mapping
from shapely.ops import transform

from floodguard import closure_rules, flood_inputs
from floodguard import nan_case_chain as nan
from floodguard.confidence import ConfidenceInputs, derive_confidence, load_confidence_rule
from floodguard.evidence_context import _context_content_hash
from floodguard.planning_overlay import load_protocol_binding, load_overlay_schema, SCHEMA_RELATIVE_PATH
from floodguard.wording_lint import lint_texts, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A, V1B, RECEIPTS = DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl"
RULE = load_confidence_rule(V1A, RECEIPTS)
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
# An invented origin in the open sea (about 97.2 E, 7.2 N): nothing below is a place.
ORIGIN_X, ORIGIN_Y = 300_000.0, 800_000.0
COMPONENTS = ("flood_likelihood_0_100", "exposure_0_100", "access_gap_0_100", "road_criticality_0_100",
              "vulnerability_context_0_100")


def _load_chain() -> Any:
    name = "nan_case_chain_script"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "nan_case_chain.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


chain = _load_chain()


def metres(geometry: Any) -> Any:
    return transform(lambda x, y: (x + ORIGIN_X, y + ORIGIN_Y), geometry)


def wgs84(geometry: Any) -> Any:
    return transform(lambda x, y: TO_WGS84(x + ORIGIN_X, y + ORIGIN_Y), geometry)


def lonlat(x_m: float, y_m: float) -> list[float]:
    longitude, latitude = TO_WGS84(ORIGIN_X + x_m, ORIGIN_Y + y_m)
    return [longitude, latitude]


def outcome(**changes: Any) -> nan.CaseOutcome:
    values = dict(test_1_passed=True, dry_control_passed=True, test_1_iou=0.45,
                  reference="an invented reference map (fixture, not a place)", case_reference_date=date(2025, 7, 28))
    values.update(changes)
    return nan.CaseOutcome(**values)


def own_inputs(**changes: Any) -> ConfidenceInputs:
    """Confidence inputs of an invented tier T2 unit that passes every condition of rule v1 but C1."""

    values = dict(unit_id="FX-N-U9", lane="OBS", tier="T2", flood_input="Invented M1-z map (fixture, not a place)",
                  scenario_base=None, acquisition_date=date(2025, 7, 28), case_reference_date=date(2025, 7, 28),
                  unit_valid_coverage=0.9, coverage_by_construction=False, exposure_plus_one_pixel_0_100=12.0,
                  exposure_minus_one_pixel_0_100=10.0, t2_abstention_fraction=0.1, t2_geoid_held_out_test_iou=0.45,
                  component_status={name: "computed" for name in COMPONENTS}, unit_residents=500.0,
                  baseline_vehicle_no_route_share=0.0, hospitals_reachable_at_baseline=2)
    values.update(changes)
    return ConfidenceInputs(**values)


# ---------------------------------------------------------------------------
# The pure parts
# ---------------------------------------------------------------------------


def test_a_flood_raster_holds_the_three_codes_of_the_case_and_each_treatment_reads_no_answer_its_way() -> None:
    values = np.array([[1, 0, 255], [0, 1, 255]], dtype="uint8")
    assert nan.check_flood_values(values) == {"cells": 6, "flagged": 2, "not_flagged": 2, "no_answer": 2}
    with pytest.raises(nan.NanChainError, match="1 \\(flagged\\)"):
        nan.check_flood_values(np.array([[1, 2]], dtype="uint8"))
    with pytest.raises(nan.NanChainError, match="rows"):
        nan.check_flood_values(values, nan.RasterGrid(0.0, 40.0, 3, 3))
    assert nan.treatment_mask(values, nan.BINDING_TREATMENT).tolist() == [[True, False, False], [False, True, False]]
    assert nan.treatment_mask(values, nan.SENSITIVITY_TREATMENT).tolist() == [[True, False, True], [False, True, True]]
    with pytest.raises(nan.NanChainError, match="treatment"):
        nan.treatment_mask(values, "no_answer_dropped")


def test_the_grid_is_read_as_the_areas_record_writes_it() -> None:
    areas = json.loads((ROOT / "outputs" / "nan_case" / "areas_v1.json").read_text(encoding="utf-8"))
    protocol = json.loads((DOCS / "nan_case_protocol_v1.json").read_text(encoding="utf-8"))
    grid = nan.grid_from_record(areas["areas"]["nan_frame"]["grid"])
    assert grid == nan.grid_from_record(protocol["grid"]["frame"])
    assert (grid.rows, grid.cols, grid.cell_m, grid.epsg) == (4303, 4280, 20.0, 32647)
    assert grid.bounds == (639520.0, 2111500.0 - 4303 * 20, 639520.0 + 4280 * 20, 2111500.0)
    with pytest.raises(nan.NanChainError):
        nan.grid_from_record({"west": 0, "north": 0, "rows": 0, "cols": 3})


def test_footprints_traced_whole_or_tile_by_tile_cover_the_same_cells() -> None:
    grid = nan.RasterGrid(0.0, 400.0, 20, 20)
    mask = np.zeros((20, 20), dtype=bool)
    mask[2:15, 3:18] = True
    mask[17, 17] = True
    whole = nan.cell_footprints(mask, grid.transform)
    pieces = nan.tiled_footprints(mask, grid.transform, tile_cells=4)
    assert math.isclose(whole.area, mask.sum() * 400.0)
    assert len(pieces) > 4 and math.isclose(sum(piece.area for piece in pieces), whole.area)
    assert shapely.union_all(pieces).symmetric_difference(whole).area < 1e-6
    assert nan.cell_footprints(np.zeros((3, 3), dtype=bool), grid.transform).is_empty
    with pytest.raises(nan.NanChainError):
        nan.tiled_footprints(mask, grid.transform, tile_cells=0)


def test_the_closure_extent_of_an_own_raster_drops_polygons_under_five_cells_and_another_raster_keeps_them() -> None:
    grid = nan.RasterGrid(0.0, 200.0, 10, 10)
    mask = np.zeros((10, 10), dtype=bool)
    mask[1:4, 1:3] = True          # six cells: kept
    mask[7, 7] = mask[8, 8] = True  # two cells, 8-connected: dropped
    kept, counts = nan.closure_extent(mask, grid.transform, tier="T2", minimum_px=5)
    assert math.isclose(kept.area, 6 * 400.0) and counts["polygons_dropped"] == 1 and counts["connectivity"] == 8
    whole, record = nan.closure_extent(mask, grid.transform, tier="T3", minimum_px=5)
    assert math.isclose(whole.area, 8 * 400.0) and "tier T3" in record["rule"]


def test_lengths_summed_over_tile_pieces_are_the_lengths_closure_rule_v1_measures() -> None:
    grid = nan.RasterGrid(ORIGIN_X, ORIGIN_Y + 400.0, 20, 20)
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 2:19] = True
    nodes = {"a": lonlat(10.0, 100.0), "b": lonlat(390.0, 330.0), "c": lonlat(200.0, 395.0), "d": lonlat(200.0, 10.0),
             "e": lonlat(5.0, 5.0), "f": lonlat(30.0, 5.0)}
    edges = [{"edge_id": "ab", "from_node": "a", "to_node": "b"}, {"edge_id": "cd", "from_node": "c", "to_node": "d"},
             {"edge_id": "ef", "from_node": "e", "to_node": "f"}]
    whole = flood_inputs.project(nan.cell_footprints(mask, grid.transform), flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    expected = {row["edge_id"]: row for row in closure_rules.edge_intersections(edges, nodes, whole)}
    identifiers, lines = nan.edge_lines_in_metres(edges, nodes)
    found = {row["edge_id"]: row for row in nan.edge_lengths_inside_pieces(identifiers, lines,
                                                                            nan.tiled_footprints(mask, grid.transform, tile_cells=3))}
    assert set(found) == set(expected) == {"ab", "cd"}
    for edge_id in found:
        assert math.isclose(found[edge_id]["intersection_length_m"], expected[edge_id]["intersection_length_m"], abs_tol=1e-6)
        assert math.isclose(found[edge_id]["intersection_fraction"], expected[edge_id]["intersection_fraction"], abs_tol=1e-9)
    with pytest.raises(nan.NanChainError, match="unknown node"):
        nan.edge_lines_in_metres([{"edge_id": "x", "from_node": "a", "to_node": "nowhere"}], nodes)


def test_the_no_answer_figures_of_a_unit_are_its_land_its_residents_and_its_edges_in_no_answer_cells() -> None:
    grid = nan.RasterGrid(0.0, 1000.0, 50, 100)
    values = np.zeros((50, 100), dtype="uint8")
    values[0:10, 50:60] = nan.NO_ANSWER   # x 1000..1200, y 800..1000: 40,000 m2, in unit B
    units = {"A": box(0.0, 0.0, 1000.0, 1000.0), "B": box(1000.0, 0.0, 2000.0, 1000.0)}
    water = box(1000.0, 0.0, 1100.0, 100.0)  # 10,000 m2 of permanent water in unit B
    pieces = nan.tiled_footprints(values == nan.NO_ANSWER, grid.transform, tile_cells=4)
    lines = np.array([LineString([(1100.0, 0.0), (1100.0, 950.0)]), LineString([(0.0, 500.0), (900.0, 500.0)])], dtype=object)
    crossing = nan.edges_crossing_by_unit(["north", "west"], lines, pieces, units)
    assert crossing["B"]["edges"] == 1 and math.isclose(crossing["B"]["length_inside_m"], 150.0)
    assert crossing["A"] == {"edges": 0, "length_inside_m": 0.0}
    cells = [{"population_id": "p1", "unit_id": "B", "residents": 70.0}, {"population_id": "p2", "unit_id": "B", "residents": 30.0},
             {"population_id": "p3", "unit_id": "A", "residents": 5.0}]
    at = nan.grid_values_at(values, grid, [1150.0, 1500.0, 10.0], [900.0, 500.0, 10.0])
    assert at.tolist() == [255, 0, 0]
    assert nan.grid_values_at(values, grid, [-5.0], [10.0]).tolist() == [-1]
    figures = nan.no_answer_by_unit(units=units, water=water, no_answer_pieces=pieces, cells=cells, cell_values=at,
                                    edges_crossing=crossing)
    assert math.isclose(figures["B"]["land_outside_permanent_water_m2"], 990_000.0)
    assert math.isclose(figures["B"]["no_answer_share_of_land"], 40_000.0 / 990_000.0)
    assert math.isclose(figures["B"]["answered_share_of_land"], 1 - 40_000.0 / 990_000.0)
    assert (figures["B"]["residents"], figures["B"]["residents_in_no_answer_cells"]) == (100.0, 70.0)
    assert figures["A"]["no_answer_share_of_land"] == 0.0 and figures["A"]["vehicle_edges_crossing_no_answer_cells"] == 0


def test_the_nan_binding_rule_takes_the_place_of_the_t2_skill_condition_behind_c1() -> None:
    derive = nan.nan_derivation(outcome())
    rule_v1 = derive_confidence(own_inputs(), RULE)
    assert rule_v1["basis"]["C1_tier"] == "fail" and rule_v1["t2_skill_condition"]["status"] == "not_evaluated_by_the_rule"
    record = derive(own_inputs(), RULE)
    skill = record["t2_skill_condition"]
    assert record["confidence_class"] == "medium" and record["basis"]["C1_tier"] == "pass" and record["failed_conditions"] == []
    assert skill["status"] == "evaluated" and skill["passes"] is True
    assert skill["measurements"] == {"geoid_held_out_test_iou": 0.45, "abstention_fraction": 0.1, "unit_valid_coverage": 0.9,
                                     "recency_days": 0}
    assert skill["metric_wording"].startswith("agreement with an invented reference map") and "not accuracy" in skill["metric_wording"]
    # Everything else is rule v1 as written.
    assert {key: value for key, value in record["basis"].items() if key != "C1_tier"} == {
        key: value for key, value in rule_v1["basis"].items() if key != "C1_tier"}
    assert record["measurements"] == rule_v1["measurements"] and record["thresholds"] == rule_v1["thresholds"]
    assert record["assumptions"][-1] == nan.NAN_RULE_SENTENCE

    # The case-level outcome failed (the dry control): the map is declared unable to meet the bar, whatever the tambon.
    failed = nan.nan_derivation(outcome(dry_control_passed=False))(own_inputs(), RULE)
    assert failed["confidence_class"] == "low" and failed["failed_conditions"] == ["C1_tier"]
    assert failed["reason_code"] == "low_confidence" and failed["t2_skill_condition"]["status"] == "declared_unable_to_meet"
    assert nan.nan_derivation(outcome(test_1_passed=None, test_1_iou=None))(
        own_inputs(t2_geoid_held_out_test_iou=None), RULE)["confidence_class"] == "low"
    # The tambon's own figures: more than 0.20 without an answer fails C1 (and C4 as written); less than 0.80 answered fails C1 and C3.
    wide = derive(own_inputs(t2_abstention_fraction=0.25, unit_valid_coverage=0.75), RULE)
    assert wide["failed_conditions"] == ["C1_tier", "C3_coverage", "C4_input_uncertainty"]
    assert wide["t2_skill_condition"]["failed_conditions"] == ["mae_sai_abstention_fraction_max", "mae_sai_unit_coverage_min"]
    late = derive(own_inputs(acquisition_date=date(2025, 8, 1)), RULE)
    assert late["failed_conditions"] == ["C1_tier", "C2_recency"]
    few = derive(own_inputs(unit_residents=50.0), RULE)
    assert few["reason_code"] == "insufficient_denominator" and "C6_residents" in few["failed_conditions"]
    # Case N2 (the reference as provided, tier T3): rule v1 as written.
    agency = own_inputs(tier="T3", flood_input="An invented reference map (fixture, not a place)", t2_abstention_fraction=None,
                        t2_geoid_held_out_test_iou=None)
    assert derive(agency, RULE) == derive_confidence(agency, RULE)
    with pytest.raises(nan.NanChainError, match="test 1 figure"):
        derive(own_inputs(t2_geoid_held_out_test_iou=0.5), RULE)


def test_an_outcome_whose_parts_do_not_fit_is_refused() -> None:
    with pytest.raises(nan.NanChainError, match="at least 0.4"):
        nan.check_outcome(outcome(test_1_iou=0.39))
    with pytest.raises(nan.NanChainError, match="at least 0.4"):
        nan.check_outcome(outcome(test_1_iou=None))
    with pytest.raises(nan.NanChainError, match="2025-07-31"):
        nan.check_outcome(outcome(fallback=True))
    assert nan.check_outcome(outcome(fallback=True, case_reference_date=date(2025, 7, 31))).passed
    assert not nan.check_outcome(outcome(test_1_passed=False, test_1_iou=0.3)).passed
    nan.check_rule_thresholds(RULE)
    record = outcome().as_record()
    assert record["case_level_test_outcome_passed"] is True and record["wording"].endswith("not accuracy")


def test_the_headline_over_the_cells_run_is_guardrail_gr8_at_60_percent() -> None:
    grid = chain.ensemble.load_grid(V1A, V1B, RECEIPTS)

    def unit(kept: int, cells: int = 90) -> dict[str, Any]:
        rows = [{"cell_id": f"c{index}", "status": "computed", "action_class": "D" if index < kept else "E",
                 "would_be_class": None, "action_reason_code": "resilience" if index < kept else "low_priority_score"}
                for index in range(cells)]
        return {"unit_id": "FX", "reference_cell": {"action_class": "D", "would_be_class": None, "action_reason_code": "resilience"},
                "cells": rows}

    scope = [f"c{index}" for index in range(90)]
    eligible = nan.headline_over_the_cells_run(grid, unit(54), scope=scope, over="90 invented cells")
    unstable = nan.headline_over_the_cells_run(grid, unit(53), scope=scope, over="90 invented cells")
    assert (eligible["status"], eligible["class_retention"]) == ("headline_eligible", 0.6)
    assert unstable["status"] == "unstable_verify" and unstable["fallback_text"] == grid.fallback_text
    assert nan.headline_slot(eligible) == {"guardrail": "GR8_headline_stability", "status": "headline_eligible",
                                           "class_retention": 0.6, "class_retention_min": 0.6}
    retention = nan.would_be_retention(unit(60), scope=scope)
    assert (retention["cells"], retention["cells_keeping_it"]) == (90, 60)
    assert nan.class_under_medium({"action_class": "E", "would_be_class": "B", "action_reason_code": "low_confidence"}) == "B"
    assert nan.class_under_medium({"action_class": "E", "would_be_class": None, "action_reason_code": "low_confidence"}) is None
    with pytest.raises(nan.NanChainError):
        nan.headline_over_the_cells_run(grid, unit(54), scope=["nowhere"], over="none")


def test_test_5_compares_the_binding_or_would_be_class_of_each_tambon() -> None:
    first = [{"unit_id": f"U{index}", "action_class": "E", "would_be_class": "D" if index < 7 else "C"} for index in range(10)]
    second = [{"unit_id": f"U{index}", "action_class": "D", "would_be_class": None} for index in range(10)]
    result = nan.class_agreement(first, second)
    assert (result["same_class"], result["share"], result["passes"]) == (7, 0.7, True)
    assert not nan.class_agreement(first[:9] + [{"unit_id": "U9", "action_class": "A", "would_be_class": None}],
                                   second[:6] + [{"unit_id": f"U{index}", "action_class": "B", "would_be_class": None}
                                                 for index in range(6, 10)])["passes"]
    with pytest.raises(nan.NanChainError):
        nan.class_agreement(first, second[:5])


def test_the_firewall_refuses_the_sealed_folder_and_the_theos2_files_of_31_july() -> None:
    refused = [
        "C:/data/proposal_execution/nan_case_v1/jaxa_sealed/JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip",
        "/data/IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif", "/data/water_v2_chip_001_2m.tif", "/data/chip_003_2m.npz",
        "/data/held_chip_001_reference_labels.json",
    ]
    assert all(nan.firewall_refusal(path) for path in refused)
    assert nan.firewall_refusal("/data/proposal_execution/nan_case_v1/test/jaxa_20250728_on_the_frame_grid.tif") is None
    assert nan.firewall_refusal("/data/frame/context_inputs.json") is None
    with pytest.raises(chain.ChainError):
        chain.refuse_sealed([Path("/x/jaxa_sealed/a.zip")])


def test_the_wording_of_the_chain_passes_the_shared_lint() -> None:
    lint = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    sources = ["src/floodguard/nan_case_chain.py", "scripts/nan_case_chain.py"]
    # The task's own wording "agreement with <reference>, not accuracy" is the one phrase the replay lint does not
    # list as a denial; it is removed before the lint, and every other string is linted as written.
    items = [(name, "\n".join(text.replace("not accuracy", "not a measure") for text in python_strings((ROOT / name).read_text(encoding="utf-8"))))
             for name in sources]
    assert lint_texts(items, lint) == []


# ---------------------------------------------------------------------------
# The whole chain on an invented frame
# ---------------------------------------------------------------------------


GRID = nan.RasterGrid(ORIGIN_X, ORIGIN_Y + 1000.0, 50, 60)
"""60 by 50 cells of 20 m: x 0 to 1,200 m and y 0 to 1,000 m from the invented origin."""
UNITS = {"FX-N-U1": box(0.0, 0.0, 600.0, 1000.0), "FX-N-U2": box(600.0, 0.0, 1200.0, 1000.0)}
NODES = {"h": (100.0, 100.0), "a": (300.0, 100.0), "b": (500.0, 100.0), "c": (700.0, 100.0), "d": (900.0, 100.0),
         "e": (1100.0, 100.0), "q": (900.0, 300.0), "g": (1110.0, 800.0)}
STREETS = [("p1", "h", "a", "primary", 60.0), ("p2", "a", "b", "primary", 60.0), ("r1", "b", "c", "residential", 25.0),
           ("r2", "c", "d", "residential", 25.0), ("r3", "d", "e", "residential", 25.0), ("r4", "d", "q", "residential", 25.0),
           ("r5", "e", "g", "residential", 25.0)]
CELLS = {"c1": ("a", (300.0, 100.0), 1000.0), "c5": (None, (300.0, 800.0), 50.0), "c2": ("c", (700.0, 100.0), 800.0),
         "c3": ("e", (1100.0, 100.0), 500.0), "c4": ("q", (900.0, 300.0), 600.0), "c6": ("d", (800.0, 100.0), 300.0),
         "c8": ("g", (1150.0, 700.0), 100.0)}
AGES = {"FX-N-U1": (200.0, 150.0, 1000.0), "FX-N-U2": (600.0, 500.0, 2000.0)}   # children 0-14, 60 and over, all residents
WATER = box(400.0, 900.0, 500.0, 1000.0)   # 10,000 m2 of permanent water, in unit 1
P10, P90 = 0.351416, 0.477677


def cells_of(x0: float, x1: float, y0: float, y1: float) -> tuple[slice, slice]:
    """The rows and columns of the grid for a box in metres from the invented origin."""

    return slice(int((1000.0 - y1) / 20), int((1000.0 - y0) / 20)), slice(int(x0 / 20), int(x1 / 20))


def flood_raster(block: tuple[float, float, float, float]) -> np.ndarray:
    values = np.zeros((GRID.rows, GRID.cols), dtype="uint8")
    values[cells_of(*block)] = nan.FLAGGED
    values[cells_of(200.0, 240.0, 300.0, 320.0)] = nan.FLAGGED       # two isolated cells in unit 1 (800 m2)
    values[cells_of(1000.0, 1200.0, 600.0, 1000.0)] = nan.NO_ANSWER  # 80,000 m2 without an answer in unit 2
    values[cells_of(0.0, 100.0, 900.0, 1000.0)] = nan.NO_ANSWER      # 10,000 m2 without an answer in unit 1
    return values


# Street r2 (c to d, 200 m at y = 100 m) has 80 m in the central map, 40 m in the lower (six cells: at least five, so
# the closure rule keeps it) and 120 m in the upper map.
CENTRAL, LOWER, UPPER = (760.0, 840.0, 60.0, 140.0), (780.0, 820.0, 80.0, 140.0), (740.0, 860.0, 40.0, 160.0)


def write_raster(path: Path, values: np.ndarray, *, cell_m: float, west: float, north: float, nodata: int | None) -> None:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="uint8",
                       crs="EPSG:32647", transform=from_origin(west, north, cell_m, cell_m), nodata=nodata,
                       tiled=True, blockxsize=16, blockysize=16, compress="deflate") as target:
        target.write(values, 1)


def invented_context() -> dict[str, Any]:
    edges = [{"edge_id": edge_id, "from_node": start, "to_node": end,
              "length_m": float(LineString([NODES[start], NODES[end]]).length), "road_class": road_class,
              "normal_minutes": float(LineString([NODES[start], NODES[end]]).length) / 1000 / speed * 60,
              "osm_way_id": edge_id, "bridge": "no", "layer": "0", "tunnel": "no", "travel_mode": "legacy_vehicle"}
             for edge_id, start, end, road_class, speed in STREETS]
    population = []
    for identifier, (node, centre, residents) in CELLS.items():
        snap = None if node is None else float(math.dist(NODES[node], centre))
        population.append({"population_id": identifier, "subdistrict_id": "aoi-demand-not-administrative-unit",
                           "total_population": residents, "node_id": node, "snap_distance_m": snap,
                           "longitude": lonlat(*centre)[0], "latitude": lonlat(*centre)[1]})
    context = {"travel_mode": "legacy_vehicle", "edges": edges, "generated_at": "2030-01-02T00:00:00+00:00",
               "node_coordinates": {node: lonlat(*position) for node, position in NODES.items()}, "population": population,
               "osm_facilities": [{"facility_id": "OSM-way-fx", "service_type": "hospital", "candidate_destination_eligible": True,
                                   "within_routing_context": True, "node_id": "h", "snap_distance_m": 0.0,
                                   "name": "an invented hospital"}],
               "facilities": [], "connectivity_review": {"review_candidates": []}}
    context["canonical_sha256"] = _context_content_hash(context)
    return context


def invented_frame(tmp_path: Path, *, rescaled: bool = False) -> dict[str, Path]:
    paths = {"context": tmp_path / "frame" / "context_inputs.json", "boundaries": tmp_path / "frame" / "units.geojson",
             "land_cover": tmp_path / "frame" / "land_cover.tif", "age_table": tmp_path / "frame" / "age_table.json"}
    paths["context"].parent.mkdir(parents=True)
    paths["context"].write_text(json.dumps(invented_context()), encoding="utf-8")
    features = [{"type": "Feature", "geometry": mapping(wgs84(UNITS[unit_id])),
                 "properties": {"unit_id": unit_id, "name_en": f"Invented unit {number} (fixture, not a place)",
                                "name_th": f"หน่วยทดสอบ {number} (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)"}}
                for number, unit_id in enumerate(UNITS, start=1)]
    paths["boundaries"].write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    land = np.full((120, 140), 40, dtype="uint8")   # 10 m cells, x -100..1,300 m and y -100..1,100 m
    land[10:20, 50:60] = 80                          # x 400..500, y 900..1,000: the permanent water
    write_raster(paths["land_cover"], land, cell_m=10.0, west=ORIGIN_X - 100.0, north=ORIGIN_Y + 1100.0, nodata=None)
    paths["age_table"].write_text(json.dumps({"source_timestamp": "2029-09-01", "units": [
        {"unit_id": unit_id, "children_0_14": children, "older_60_plus": older, "residents": total,
         "dependent_share_unavailable_reason": None} for unit_id, (children, older, total) in AGES.items()]}), encoding="utf-8")
    for name, block in (("central", CENTRAL), ("lower", LOWER), ("upper", UPPER)):
        paths[name] = tmp_path / "maps" / f"{name}.tif"
        write_raster(paths[name], flood_raster(block), cell_m=20.0, west=GRID.west, north=GRID.north, nodata=255)
    if rescaled:
        paths["rescaled"] = tmp_path / "frame" / "rescaled.json"
        paths["rescaled"].write_text(json.dumps({identifier: residents * 1.1 for identifier, (_n, _c, residents) in CELLS.items()}),
                                     encoding="utf-8")
    return paths


def arguments_of(tmp_path: Path, paths: dict[str, Path], **changes: Any) -> Any:
    values = dict(
        case_id="N1", external=tmp_path / "external", context=paths["context"],
        flood={name: paths[name] for name in ("central", "lower", "upper")}, flood_input_id="fx_nan_m1z_central",
        flood_name="Invented M1-z map (fixture, not a place)", acquisition_date=date(2025, 7, 28),
        source_instant="2025-07-28T11:21:00Z", outcome=outcome(), boundaries=paths["boundaries"],
        land_cover=paths["land_cover"], age_table=paths["age_table"], out_dir=tmp_path / "out", work_dir=tmp_path / "work",
        fixture=True, unit_layer=None, unit_id_field="unit_id", unit_name_en_field="name_en", unit_name_th_field="name_th",
        grid=GRID, git_commit="0123abc", generated_at="2030-01-05T00:00:00Z",
        rescaled_population=paths.get("rescaled"))
    values.update(changes)
    return chain.NanArguments(**values)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="ascii"))


def test_the_chain_on_an_invented_frame_gives_the_figures_worked_out_by_hand(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path)
    summary = chain.nan_run(arguments_of(tmp_path, paths))
    assert summary["verified"] is True and summary["rows"] == 2 and summary["ensemble_cells_run"] == 90
    result_path = tmp_path / "out" / "planning_result_n1_nan_v1_fixture.json"
    data = result_path.read_bytes()
    assert b"\r\n" not in data and hashlib.sha256(data).hexdigest() == summary["result_sha256"]
    overlay = json.loads(data.decode("ascii"))
    assert (overlay["schema_version"], overlay["dataset_mode"], overlay["official_warning"]) == ("1.1", "fixture_demo", False)
    assert overlay["accepted_fpps"] is None and overlay["accepted_action_class"] is None and overlay["can_feed_decision_layer"] is False
    rows = {row["unit_id"]: row for row in overlay["rows"]}
    two = rows["FX-N-U2"]
    values = {name: two["components"][name]["value_0_100"] for name in COMPONENTS}
    # Unit 2: 600,000 m2 of land; 6,400 m2 flagged; 2,300 residents, 300 of them in a flagged cell; the closed street r2
    # cuts 1,500 residents (c3, c4, c6 and c8) off the hospital and the main road; age counts 600 + 500 of 2,000.
    expected = {"flood_likelihood_0_100": 100 * 6_400 / 600_000 / 0.20, "exposure_0_100": 100 * 300 / 2_300,
                "access_gap_0_100": 100 * 1_500 / 2_300, "road_criticality_0_100": 100 * 1_500 / 2_300,
                "vulnerability_context_0_100": 100.0}
    assert all(math.isclose(values[name], expected[name], rel_tol=1e-9, abs_tol=1e-9) for name in COMPONENTS), values
    fpps = 0.30 * expected["flood_likelihood_0_100"] + 0.25 * expected["exposure_0_100"] + 0.20 * expected["access_gap_0_100"] \
        + 0.15 * expected["road_criticality_0_100"] + 0.10 * 100.0
    assert math.isclose(two["fpps_0_100"], round(fpps, 2)) and two["action_class"] == "D"
    confidence = two["confidence"]
    assert confidence["confidence_class"] == "medium" and confidence["basis"]["C1_tier"] == "pass"
    assert math.isclose(confidence["measurements"]["t2_abstention_fraction"], 80_000 / 600_000)
    assert math.isclose(confidence["measurements"]["unit_valid_coverage"], 1 - 80_000 / 600_000)
    assert confidence["t2_skill_condition"]["status"] == "evaluated" and confidence["measurements"]["exposure_plus_minus_one_pixel_points"] == 0.0
    one = rows["FX-N-U1"]
    assert math.isclose(one["components"]["flood_likelihood_0_100"]["value_0_100"], 100 * 800 / 590_000 / 0.20)
    assert (one["action_class"], one["action_reason_code"]) == ("E", "low_priority_score")
    assert one["components"]["vulnerability_context_0_100"]["value_0_100"] == 0.0
    assert two["lineage"]["closure_rule"] == {"version": "closure_rule_v1", "level": "central",
                                              "closure_basis": "modelled_from_fx_nan_m1z_central"}
    # The headline slot carries guardrail GR8 over the 90 cells run, and the no-answer figures stand in the row.
    assert all(row["headline_stability"]["status"] in ("headline_eligible", "unstable_verify") for row in rows.values())
    assert any("No answer (code 255) on 0.1333" in text for text in two["assumptions"])

    record = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture_record.json")
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert record[key]
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    no_answer = {item["unit_id"]: item for item in record["no_answer_by_tambon"]}
    assert math.isclose(no_answer["FX-N-U2"]["no_answer_share_of_land"], 80_000 / 600_000)
    assert math.isclose(no_answer["FX-N-U1"]["no_answer_share_of_land"], 10_000 / 590_000)
    assert no_answer["FX-N-U2"]["residents_in_no_answer_cells"] == 100.0 and no_answer["FX-N-U1"]["residents_in_no_answer_cells"] == 0.0
    assert no_answer["FX-N-U2"]["vehicle_edges_crossing_no_answer_cells"] == 1   # street r5 runs through the block
    assert no_answer["FX-N-U2"]["residents_in_flagged_cells_by_grid_lookup"] == 300.0
    assert record["checks"]["residents_in_flagged_cells_polygon_and_grid_lookup_differ_by"] == 0.0
    assert record["checks"]["result_file"]["verified"] is True and record["checks"]["default_cell_of_the_ensemble_is_the_row"] is True
    assert [item["code"] for item in record["checks"]["result_file"]["accepted"]] == ["confidence_not_rule_record"] * 2
    # The sensitivity run: the no-answer block counted as flagged raises unit 2's flooded land to 86,400 m2.
    sensitivity = {item["unit_id"]: item for item in record["sensitivity_no_answer_counted_as_flagged"]["table"]}
    twin = sensitivity["FX-N-U2"]["no_answer_counted_as_flagged"]
    assert math.isclose(twin["components"]["flood_likelihood_0_100"], 100 * 86_400 / 600_000 / 0.20)
    assert math.isclose(twin["components"]["exposure_0_100"], 100 * 400 / 2_300)
    assert sensitivity["FX-N-U2"]["binding"]["fpps_0_100"] == two["fpps_0_100"]
    # The ensemble: 90 cells (no 2024-rescaled demand), the flood axis read from the three maps.
    ensemble_summary = record["ensemble"]["summary"]
    assert (ensemble_summary["cells_run"], ensemble_summary["cells_not_run"]) == (90, 450)
    assert "population_axis_dropped_by_the_nan_protocol" in "".join(ensemble_summary["cells_not_run_by_reason"])
    work = read(tmp_path / "work" / "ensemble_n1.json")
    unit_two = next(unit for unit in work["ensemble"]["units"] if unit["unit_id"] == "FX-N-U2")
    kept = sum(1 for cell in unit_two["cells"] if cell["action_class"] == unit_two["reference_cell"]["action_class"])
    assert math.isclose(record["ensemble"]["headlines"]["FX-N-U2"]["class_retention"], kept / 90)
    combinations = {(item["flood_input_single_state"], item["passability"]): item["components"]
                     for item in unit_two["routing_combinations"] if item["population_vintage"] == "worldpop_2020"}
    # The strict level delays street r2 in the central and the lower map (f = 0.4 and 0.2) and cuts nobody off.
    assert combinations[("as_provided", "strict")]["access_gap_0_100"] == 0.0 == combinations[("minus", "strict")]["road_criticality_0_100"]
    assert math.isclose(combinations[("plus", "strict")]["access_gap_0_100"], 100 * 1_500 / 2_300)
    assert math.isclose(combinations[("minus", "central")]["flood_likelihood_0_100"], 100 * 2_400 / 600_000 / 0.20)
    assert math.isclose(combinations[("plus", "permissive")]["flood_likelihood_0_100"], 100 * 14_400 / 600_000 / 0.20)
    access = read(tmp_path / "work" / "access_runs_n1.json")
    runs = {(run["flood_level"], run["closure_level"]): run for run in access["runs"]}
    assert runs[("as_provided", "strict")]["closure"]["vehicle"]["delayed_edges"] == 1
    assert runs[("minus", "central")]["closure"]["vehicle"]["closed_edges"] == 1
    assert runs[("plus", "strict")]["closure"]["vehicle"]["closed_edges"] == 1
    lineage = {item["input_id"]: item for item in overlay["inputs"]}
    assert lineage["nan_access_runs"]["sha256"] == hashlib.sha256((tmp_path / "work" / "access_runs_n1.json").read_bytes()).hexdigest()
    assert overlay["publication_eligibility"] == "public"


def test_a_failed_case_level_outcome_makes_every_row_class_e_with_its_would_be_class(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path)
    chain.nan_run(arguments_of(tmp_path, paths, outcome=outcome(dry_control_passed=False), sensitivity=False))
    overlay = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture.json")
    two = next(row for row in overlay["rows"] if row["unit_id"] == "FX-N-U2")
    assert (two["action_class"], two["action_reason_code"], two["would_be_class"]) == ("E", "low_confidence", "D")
    assert two["confidence"]["failed_conditions"] == ["C1_tier"]
    assert two["confidence"]["t2_skill_condition"]["status"] == "declared_unable_to_meet"
    assert two["class_v2"]["result"] == "E"
    record = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture_record.json")
    assert record["sensitivity_no_answer_counted_as_flagged"] is None
    assert record["ensemble"]["would_be_retention"]["FX-N-U2"]["class_with_confidence_medium_in_the_default_cell"] == "D"
    assert record["case_outcome"]["case_level_test_outcome_passed"] is False


def test_with_the_rescaled_demand_the_ensemble_runs_its_180_cells(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path, rescaled=True)
    summary = chain.nan_run(arguments_of(tmp_path, paths, sensitivity=False))
    assert summary["ensemble_cells_run"] == 180
    record = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture_record.json")
    assert record["ensemble"]["summary"]["cells_run"] == 180 and record["inputs"]["rescaled_demand"]["source"] == "given"
    work = read(tmp_path / "work" / "ensemble_n1.json")
    # Over all 180 cells the protocol's own headline is evaluated, and the chain's headline is the same record.
    for unit in work["ensemble"]["units"]:
        mine = work["headlines"][unit["unit_id"]]
        assert (mine["status"], mine["class_retention"]) == (unit["headline_stability"]["status"], unit["headline_stability"]["class_retention"])


def test_case_n2_is_rule_v1_as_written_and_stays_outside_git(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path)
    arguments = arguments_of(tmp_path, paths, case_id="N2", flood_input_id="fx_reference_map",
                             flood_name="Invented reference map (fixture, not a place)", sensitivity=False,
                             flood={"central": paths["central"]})
    summary = chain.nan_run(arguments)
    assert summary["publication_eligibility"] == "local" and summary["ensemble_cells_run"] == 30
    overlay = read(tmp_path / "out" / "planning_result_n2_nan_v1_fixture.json")
    two = next(row for row in overlay["rows"] if row["unit_id"] == "FX-N-U2")
    assert two["tier"] == "T3" and two["confidence"]["t2_skill_condition"] is None
    assert two["confidence"]["basis"]["C1_tier"] == "pass" and two["confidence"]["measurements"]["t2_abstention_fraction"] is None
    record = read(tmp_path / "out" / "planning_result_n2_nan_v1_fixture_record.json")
    assert record["checks"]["result_file"]["accepted"] == []
    with pytest.raises(chain.ChainError, match="outside Git"):
        chain.nan_run(arguments_of(tmp_path, paths, case_id="N2", flood_input_id="fx_reference_map", sensitivity=False,
                                   flood={"central": paths["central"]}, out_dir=ROOT / "outputs" / "nan_case"))


def test_the_chain_refuses_before_it_measures_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = invented_frame(tmp_path)
    sealed = tmp_path / "proposal_execution" / "nan_case_v1" / "jaxa_sealed" / "context_inputs.json"
    with pytest.raises(chain.ChainError, match="sealed folder"):
        chain.nan_run(arguments_of(tmp_path, paths, context=sealed))
    monkeypatch.setattr(chain, "FREEZE_RECORD", tmp_path / "no_freeze_record.json")
    with pytest.raises(chain.ChainError, match="order rule.*freeze record"):
        chain.nan_run(arguments_of(tmp_path, paths, fixture=False))
    (tmp_path / "freeze_v1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(chain, "FREEZE_RECORD", tmp_path / "freeze_v1.json")
    monkeypatch.setattr(chain, "TEST_RECORD", tmp_path / "no_test_record.json")
    with pytest.raises(chain.ChainError, match="after the test"):
        chain.nan_run(arguments_of(tmp_path, paths, fixture=False))
    with pytest.raises(chain.ChainError, match="identifier"):
        chain.nan_run(arguments_of(tmp_path, paths, flood_input_id="Not:An:Id"))
    shifted = tmp_path / "maps" / "shifted.tif"
    write_raster(shifted, flood_raster(CENTRAL), cell_m=20.0, west=GRID.west + 20.0, north=GRID.north, nodata=255)
    with pytest.raises(chain.ChainError, match="grid"):
        chain.nan_run(arguments_of(tmp_path, paths, flood={"central": shifted}))
    assert not (tmp_path / "out").exists()


def test_the_result_file_check_accepts_only_what_the_nan_protocol_says(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path)
    chain.nan_run(arguments_of(tmp_path, paths, sensitivity=False))
    overlay = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture.json")
    binding = load_protocol_binding(V1A, V1B, RECEIPTS)
    schema = load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH)
    derive = nan.nan_derivation(outcome())
    assert nan.nan_overlay_problems(overlay, schema, binding, derive)["verified"] is True
    # A confidence record the binding rule would not give is refused.
    changed = json.loads(json.dumps(overlay))
    changed["rows"][1]["confidence"]["t2_skill_condition"]["measurements"]["abstention_fraction"] = 0.01
    checked = nan.nan_overlay_problems(changed, schema, binding, derive)
    assert checked["verified"] is False and any(item["path"].startswith("$.rows[1]") for item in checked["refused"])
    # So is a class the rows do not give.
    changed = json.loads(json.dumps(overlay))
    changed["rows"][1]["action_class"] = "A"
    assert nan.nan_overlay_problems(changed, schema, binding, derive)["verified"] is False
    # Judged by another outcome, the same file is refused: the outcome is part of the rule.
    assert nan.nan_overlay_problems(overlay, schema, binding, nan.nan_derivation(outcome(dry_control_passed=False)))["verified"] is False


def test_the_earlier_builders_are_used_unchanged_and_without_a_derivation_rule_v1_applies() -> None:
    assert chain.e8 is chain.e10.e8_builder and chain.e5 is chain.e8.e5_builder
    import inspect

    from floodguard import planning_assessment, uncertainty_ensemble

    for function in (planning_assessment.assess_unit, planning_assessment.assemble_overlay, uncertainty_ensemble.run_ensemble):
        assert inspect.signature(function).parameters["derive"].default is None


def test_the_input_checks_open_no_flood_map_and_count_the_frame(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path, rescaled=True)
    for name in ("central", "lower", "upper"):
        paths[name].unlink()   # no flood map exists: the checks never open one
    checked = chain.nan_check_inputs(arguments_of(tmp_path, paths, flood={}))
    assert checked["inputs_checked"] is True and checked["grid_covers_every_unit"] is True
    assert (checked["demand_cells"], checked["demand_cells_in_one_unit"]) == (7, 7)
    assert checked["residents_in_the_units"] == 1050.0 + 2300.0
    assert checked["units_with_no_reachable_hospital_at_baseline"] == 0
    assert math.isclose(checked["permanent_water_km2_in_the_reporting_frame"], 0.01)
    assert checked["age_table"]["holds_every_unit"] is True and checked["rescaled_demand"]["covers_every_demand_cell"] is True
    assert not (tmp_path / "out").exists()


def write_method_map(path: Path) -> None:
    """A map as the method lane writes it: bands code_lower, code_central, code_upper and the central reasons."""

    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    bands = [("code_lower", flood_raster(LOWER)), ("code_central", flood_raster(CENTRAL)), ("code_upper", flood_raster(UPPER)),
             ("reason_central", np.zeros((GRID.rows, GRID.cols), dtype="uint8"))]
    with rasterio.open(path, "w", driver="GTiff", width=GRID.cols, height=GRID.rows, count=4, dtype="uint8", crs="EPSG:32647",
                       transform=from_origin(GRID.west, GRID.north, 20.0, 20.0), nodata=255) as target:
        for index, (name, values) in enumerate(bands, start=1):
            target.write(values, index)
            target.set_band_description(index, name)


def test_a_map_of_the_method_lane_gives_the_same_result_as_three_rasters(tmp_path: Path) -> None:
    paths = invented_frame(tmp_path)
    chain.nan_run(arguments_of(tmp_path, paths, sensitivity=False))
    separate = read(tmp_path / "out" / "planning_result_n1_nan_v1_fixture.json")
    method_map = tmp_path / "method" / "maps" / "m1z_20250728T1121_o99_S1C.tif"
    write_method_map(method_map)
    values, record = chain.read_flood_raster(method_map, GRID, "upper")
    assert record["band"] == 3 and (values == flood_raster(UPPER)).all()
    chain.nan_run(arguments_of(tmp_path, paths, sensitivity=False, flood={name: method_map for name in ("central", "lower", "upper")},
                               out_dir=tmp_path / "out_map"))
    banded = read(tmp_path / "out_map" / "planning_result_n1_nan_v1_fixture.json")
    assert [row["fpps_0_100"] for row in banded["rows"]] == [row["fpps_0_100"] for row in separate["rows"]]
    assert [row["headline_stability"] for row in banded["rows"]] == [row["headline_stability"] for row in separate["rows"]]
    with pytest.raises(chain.ChainError, match="code_middle"):
        chain.read_flood_raster(method_map, GRID, "middle")


def test_the_outcome_and_the_flood_input_are_read_from_the_test_record(tmp_path: Path) -> None:
    external = tmp_path / "external"
    method_map = external / "proposal_execution" / "nan_case_v1" / "method" / "maps" / "m1z_20250728T1121_o99_S1C.tif"
    write_method_map(method_map)
    digest = hashlib.sha256(method_map.read_bytes()).hexdigest()
    record = {"test_1": {"reference": "an invented reference map (fixture, not a place)", "passes": True,
                         "central": {"iou_no_answer_as_not_flagged": 0.47, "no_answer_share": 0.1}},
              "dry_control": {"passes": True},
              "binding": {"test_1_passes": True, "dry_control_passes": True, "case_reference_date": "2025-07-28",
                          "flood_input_of_case_N1": {"time_utc": "2025-07-28T11:21:00Z", "relative_orbit": 99, "platform": "Sentinel-1C",
                                                     "label": "20250728T1121_o99_S1C",
                                                     "map": {"name": method_map.name, "sha256": digest}}}}
    path = tmp_path / "test_result_v1.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    found, read_back = chain.outcome_from_test_result(path, external)
    assert (found.passed, found.test_1_iou, found.fallback) == (True, 0.47, False)
    assert read_back["map_path"] == method_map and read_back["test_result"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    record["binding"]["flood_input_of_case_N1"]["map"]["sha256"] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(chain.ChainError, match="not the file the test record names"):
        chain.outcome_from_test_result(path, external)
    path.write_text(json.dumps({"binding": {}}), encoding="utf-8")
    with pytest.raises(chain.ChainError, match="binding outcome"):
        chain.outcome_from_test_result(path, external)


def test_the_command_line_asks_for_every_input_of_a_run_unless_it_only_checks(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        chain.main(["nan", "--case", "N1", "--external-root", str(tmp_path), "--context", str(tmp_path / "context.json")])
    with pytest.raises(SystemExit):
        chain.main(["nan", "--case", "N3", "--external-root", str(tmp_path), "--context", str(tmp_path / "context.json")])
    sealed = tmp_path / "jaxa_sealed" / "context.json"
    assert chain.main(["nan", "--case", "N1", "--external-root", str(tmp_path), "--context", str(sealed), "--check-inputs"]) == 2
