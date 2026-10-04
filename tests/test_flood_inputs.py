"""Flood inputs (plan task E1) on invented geometries.

No test here reads a real flood layer, a real boundary or a real land-cover raster, and none computes an
FPPS, a component, a class or an ensemble. The parameters come from the two signed protocol files; the
product archive, the candidate raster and the land-cover rasters are written by the tests into a scratch
folder. The tests of the committed run read its receipt and the run register only: they recompute nothing.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import warnings
import zipfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
import shapely
from shapely.geometry import MultiPolygon, Polygon, box

from floodguard import flood_inputs, rights, rights_basis
from floodguard.flood_inputs import (
    ANALYSIS_CRS,
    AS_PROVIDED,
    LEVELS,
    MINUS,
    PLUS,
    REPORTING_FRAME,
    ROUTING_CONTEXT,
    WGS84_CRS,
    FloodInputError,
    InputSpec,
)
from floodguard.rights import RegisteredRecord, RightsRefusedError, RightsRegistry

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
RECEIPT = ROOT / "outputs" / "planning_v1" / "e1_flood_inputs_mae_sai.json"
REGISTER = ROOT / "outputs" / "planning_v1" / "run_register" / "e1_flood_inputs_mae_sai.json"
ACCUMULATED = "CHIANGRAI_20240801_20241012_AccumulatedFlood"
LAYER_22_OCT = "CHIANGRAI_20241022_FloodExtent"
CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
# An invented place in UTM zone 47N, near 99.86 E, 20.35 N. Every test geometry is given in metres from it.
EAST, NORTH = 590_000.0, 2_250_000.0


def metres(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    return box(EAST + x0, NORTH + y0, EAST + x1, NORTH + y1)


def lonlat(geometry):
    """The same geometry in longitude and latitude, as a source file gives it."""

    return flood_inputs.project(geometry, ANALYSIS_CRS, WGS84_CRS)


@pytest.fixture(scope="module")
def rules() -> flood_inputs.FloodInputRules:
    return flood_inputs.load_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")


@pytest.fixture(scope="module")
def protocols() -> tuple[dict, dict]:
    return (json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8")),
            json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def grant() -> rights.RightsGrant:
    return RightsRegistry(ROOT).require_use(rights.PRODUCT_4009, layer=ACCUMULATED)


def frames() -> list[flood_inputs.Frame]:
    """A reporting frame of two units (each 1 km by 1 km) and a routing context of 3 km by 1 km around them."""

    reporting = flood_inputs.frame_from_units(
        REPORTING_FRAME, "two invented units",
        [("U2", lonlat(metres(1000, 0, 2000, 1000))), ("U1", lonlat(metres(0, 0, 1000, 1000)))], {"file": "invented"})
    routing = flood_inputs.frame_from_wgs84(ROUTING_CONTEXT, "an invented corridor", lonlat(metres(-500, 0, 2500, 1000)), {"file": "invented"})
    return [reporting, routing]


def spec(**changes) -> InputSpec:
    base = dict(
        case_id="SE1", input_id="invented:polygon", input_name="An invented agency polygon", lane="SCN-ENV", tier="T1",
        case_reference_date=None, acquisition_date=None, season_window=("2024-08-01", "2024-10-12"),
        temporal_relation="season_window", source_timestamp="2024-08-01/2024-10-12", source={"layer": "invented"},
        geometry_kind="vector", confidence_basis="An invented layer.", assumptions=("An invented layer.",))
    return InputSpec(**{**base, **changes})


def area(geometry) -> float:
    return float(geometry.area)


# ---------------------------------------------------------------------------
# The parameters are the ones the signed files state
# ---------------------------------------------------------------------------


def test_the_rules_are_read_from_the_two_signed_protocols(rules: flood_inputs.FloodInputRules) -> None:
    assert rules.one_pixel_m == 20.0
    assert rules.recency_window_days == 3
    assert (rules.permanent_water_source, rules.permanent_water_class) == ("ESA WorldCover 2021 v200", 80)
    assert rules.raster_minimum_polygon_px == 5
    assert rules.reporting_units == ("TH570901", "TH570902", "TH570903", "TH570904", "TH570905", "TH570906", "TH570908", "TH570909")
    assert rules.accumulated_layer["layer"] == ACCUMULATED and rules.accumulated_layer["temporal_relation"] == "season_window"
    assert rules.layer_22_oct["layer"] == LAYER_22_OCT and rules.layer_22_oct["temporal_relation"] == "event_aligned"
    assert {case: (rules.cases[case]["lane"], rules.cases[case]["tier"]) for case in ("SE1", "O2", "O1")} == {
        "SE1": ("SCN-ENV", "T1"), "O2": ("OBS", "T3"), "O1": ("OBS", "T2")}
    assert rules.product_4009_credit == CREDIT and "did not validate" in rules.standard_4009_sentence
    assert rules.routing_geometry_file["path"] == "outputs/planning_v1/corridor_of_record.geojson"
    hashes = flood_inputs.protocol_hashes(rules)
    assert hashes == {f"planning_protocol_{name}": hashlib.sha256((DOCS / f"planning_protocol_{name}.json").read_bytes()).hexdigest()
                      for name in ("v1a", "v1b")}


def test_rules_from_parsed_files_carry_no_hash_and_refuse_what_the_files_do_not_state(protocols: tuple[dict, dict]) -> None:
    v1a, v1b = protocols
    parsed = flood_inputs.rules_from_protocols(v1a, v1b)
    assert parsed.one_pixel_m == 20.0
    with pytest.raises(FloodInputError, match="carry no protocol hashes"):
        flood_inputs.protocol_hashes(parsed)

    draft = {**v1a, "status": "draft_for_signature"}
    with pytest.raises(FloodInputError, match="signed protocol files only"):
        flood_inputs.rules_from_protocols(draft, v1b)

    uneven = copy.deepcopy(v1b)
    axis = next(row for row in uneven["ensemble_grid"]["core_axes"] if row["axis"] == "flood_input_single_state")
    axis["one_pixel_m"]["plus"] = 10
    with pytest.raises(FloodInputError, match="one positive one-pixel distance"):
        flood_inputs.rules_from_protocols(v1a, uneven)

    without_water = copy.deepcopy(v1a)
    del without_water["scoring_frame"]["components"]["flood_likelihood_0_100"]["permanent_water"]
    with pytest.raises(FloodInputError, match="do not hold the flood-input parameters"):
        flood_inputs.rules_from_protocols(without_water, v1b)

    other_relations = copy.deepcopy(v1a)
    other_relations["date_rule"]["temporal_relation_values"] = ["event_aligned", "dated_other"]
    with pytest.raises(FloodInputError, match="other temporal relations"):
        flood_inputs.rules_from_protocols(other_relations, v1b)


def test_load_rules_refuses_protocol_files_that_are_not_in_force(tmp_path: Path) -> None:
    from floodguard.normalisation import NormalisationError

    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json", "RECEIPTS.jsonl"):
        (tmp_path / name).write_bytes((DOCS / name).read_bytes())
    edited = tmp_path / "planning_protocol_v1b.json"
    edited.write_bytes(edited.read_bytes() + b"\n")
    with pytest.raises(NormalisationError, match="not in force"):
        flood_inputs.load_rules(tmp_path / "planning_protocol_v1a.json", edited, tmp_path / "RECEIPTS.jsonl")


@pytest.mark.parametrize(
    ("acquired", "reference", "window", "expected"),
    [
        ("2024-10-22", "2024-10-22", None, "event_aligned"),
        ("2024-09-16", "2024-09-15", None, "event_aligned"),
        ("2024-09-18", "2024-09-15", None, "event_aligned"),
        ("2024-09-12", "2024-09-15", None, "event_aligned"),
        ("2024-09-19", "2024-09-15", None, "dated_other"),
        ("2024-09-11", "2024-09-15", None, "dated_other"),
        ("2024-10-22", "2024-09-15", None, "dated_other"),
        ("2024-10-22", None, None, "dated_other"),
        (None, None, ("2024-08-01", "2024-10-12"), "season_window"),
        # A season window is never aligned with an event, whatever the reference date.
        (None, "2024-09-15", ("2024-08-01", "2024-10-12"), "season_window"),
    ],
)
def test_the_date_rule_is_strict(acquired, reference, window, expected) -> None:
    """Protocol v1a date_rule: event_aligned only within +/-3 days of the case reference date."""

    assert flood_inputs.temporal_relation(acquired, reference, window_days=3, season_window=window) == expected


def test_the_date_rule_refuses_an_input_with_no_date_or_with_two() -> None:
    with pytest.raises(FloodInputError, match="either one acquisition date or a season window"):
        flood_inputs.temporal_relation(None, "2024-09-15", window_days=3)
    with pytest.raises(FloodInputError, match="either one acquisition date or a season window"):
        flood_inputs.temporal_relation("2024-10-22", "2024-10-22", window_days=3, season_window=("2024-08-01", "2024-10-12"))
    with pytest.raises(FloodInputError, match="YYYY-MM-DD"):
        flood_inputs.temporal_relation("22 Oct 2024", "2024-10-22", window_days=3)
    with pytest.raises(FloodInputError, match="ends before it starts"):
        flood_inputs.temporal_relation(None, None, window_days=3, season_window=("2024-10-12", "2024-08-01"))


# ---------------------------------------------------------------------------
# Repair, levels and clip
# ---------------------------------------------------------------------------


def bow_tie(x0: float, y0: float, size: float) -> Polygon:
    """A ring that crosses itself: two triangles of size x size / 4 each once repaired."""

    return Polygon([(EAST + x0, NORTH + y0), (EAST + x0 + size, NORTH + y0 + size), (EAST + x0 + size, NORTH + y0),
                    (EAST + x0, NORTH + y0 + size), (EAST + x0, NORTH + y0)])


def test_invalid_parts_are_repaired_and_counted() -> None:
    product = lonlat(MultiPolygon([metres(100, 100, 300, 300), bow_tie(400, 100, 100), bow_tie(5000, 5000, 100)]))
    extent, record = flood_inputs.repair_product(product, frames(), source_crs=WGS84_CRS, reach_m=20.0)
    assert record["method"] == "make_valid"
    assert (record["source_parts"], record["source_parts_invalid"]) == (3, 2)
    # The far bow tie cannot reach a frame: it is counted as invalid in the layer and is not read or repaired.
    assert (record["parts_read"], record["parts_repaired"], record["parts_repaired_after_projection"]) == (2, 1, 0)
    assert record["by_frame"] == {REPORTING_FRAME: {"parts_within_reach": 2, "parts_repaired": 1},
                                  ROUTING_CONTEXT: {"parts_within_reach": 2, "parts_repaired": 1}}
    assert extent.is_valid and isinstance(extent, MultiPolygon)
    assert area(extent) == pytest.approx(200 * 200 + 100 * 100 / 2, abs=0.01)


def test_a_part_is_read_when_it_can_reach_a_frame_at_the_plus_level() -> None:
    reporting = frames()[:1]
    near = lonlat(metres(2010, 100, 2100, 200))   # 10 m east of the reporting frame
    far = lonlat(metres(2030, 100, 2100, 200))    # 30 m east of it
    _extent, record = flood_inputs.repair_product(MultiPolygon([near, far]), reporting, source_crs=WGS84_CRS, reach_m=20.0)
    assert record["parts_read"] == 1
    empty, record = flood_inputs.repair_product(MultiPolygon(), reporting, source_crs=WGS84_CRS, reach_m=20.0)
    assert empty.is_empty and record["source_parts"] == 0
    none_near, record = flood_inputs.repair_product(far, reporting, source_crs=WGS84_CRS, reach_m=20.0)
    assert none_near.is_empty and (record["source_parts"], record["parts_read"]) == (1, 0)


def test_the_minus_and_plus_levels_are_twenty_metre_buffers() -> None:
    """Protocol v1b, owner choice 2: a 20 m negative or positive buffer in EPSG:32647."""

    square = metres(0, 0, 200, 200)
    levels = flood_inputs.one_pixel_levels(square, 20.0)
    assert list(levels) == list(LEVELS)
    assert area(levels[AS_PROVIDED]) == pytest.approx(40_000)
    assert levels[MINUS].bounds == pytest.approx((EAST + 20, NORTH + 20, EAST + 180, NORTH + 180))
    assert area(levels[MINUS]) == pytest.approx(160 * 160)
    assert levels[PLUS].bounds == pytest.approx((EAST - 20, NORTH - 20, EAST + 220, NORTH + 220))
    # Round corners: the square, four 20 m strips and one circle of 20 m radius drawn with 64 segments.
    circle = 0.5 * 64 * 20 * 20 * math.sin(2 * math.pi / 64)
    assert area(levels[PLUS]) == pytest.approx(40_000 + 4 * 200 * 20 + circle, rel=1e-9)
    assert circle == pytest.approx(math.pi * 400, rel=0.002)
    with pytest.raises(FloodInputError, match="must be positive"):
        flood_inputs.one_pixel_levels(square, 0.0)


def test_the_minus_level_removes_narrow_water_and_the_plus_level_joins_near_water() -> None:
    strip = metres(0, 0, 500, 30)                                  # 30 m wide: narrower than two pixels
    pair = MultiPolygon([metres(0, 100, 100, 200), metres(130, 100, 230, 200)])   # 30 m apart
    levels = flood_inputs.one_pixel_levels(MultiPolygon([strip, *pair.geoms]), 20.0)
    assert len(levels[AS_PROVIDED].geoms) == 3
    assert len(levels[MINUS].geoms) == 2 and area(levels[MINUS]) == pytest.approx(2 * 60 * 60)
    assert len(levels[PLUS].geoms) == 2            # the two squares are one polygon now; the strip is the other


def test_the_levels_are_made_before_the_clip_so_a_frame_edge_is_not_moved(rules, grant) -> None:
    """A flood polygon that crosses the frame edge keeps that edge at every level."""

    frame = flood_inputs.frame_from_wgs84(REPORTING_FRAME, "one invented frame", lonlat(metres(0, 0, 1000, 1000)), {})
    crossing = metres(-500, 100, 500, 300)
    outside = metres(1010, 500, 1100, 600)         # 10 m east of the frame: it enters only at the plus level
    built = flood_inputs.build_flood_input(lonlat(MultiPolygon([crossing, outside])), [frame], spec=spec(), rules=rules, grant=grant)
    assert area(built.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(500 * 200, abs=0.01)
    # Eroded on three sides, not along the frame edge at x = 0.
    assert area(built.extent(MINUS, REPORTING_FRAME)) == pytest.approx(480 * 160, abs=0.01)
    assert built.extent(MINUS, REPORTING_FRAME).bounds[0] == pytest.approx(EAST, abs=0.002)
    corner = 400 - 0.25 * 0.5 * 64 * 400 * math.sin(2 * math.pi / 64)
    grown = 520 * 240 - 2 * corner
    entering = 10 * 100 + 2 * (0.5 * 20 * 20 * math.acos(0.5) - 0.5 * 10 * math.sqrt(300))
    assert area(built.extent(PLUS, REPORTING_FRAME)) == pytest.approx(grown + entering, rel=1e-3)
    by_level = built.record["levels"]["by_level"]
    assert by_level[AS_PROVIDED][REPORTING_FRAME]["area_km2"] == pytest.approx(0.1)
    assert by_level[MINUS][REPORTING_FRAME]["area_m2"] < by_level[AS_PROVIDED][REPORTING_FRAME]["area_m2"] < by_level[PLUS][REPORTING_FRAME]["area_m2"]
    assert built.record["repair"]["parts_read"] == 2 and built.record["repair"]["parts_repaired"] == 0


def test_an_input_is_clipped_to_the_reporting_frame_and_to_the_routing_context(rules, grant) -> None:
    both = frames()
    product = lonlat(MultiPolygon([metres(-400, 400, 400, 600), metres(1900, 100, 2300, 300), bow_tie(1500, 700, 100)]))
    footprint = lonlat(metres(-1000, -1000, 2200, 2000))
    built = flood_inputs.build_flood_input(product, both, spec=spec(), rules=rules, grant=grant, footprint=footprint)

    assert area(built.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(400 * 200 + 100 * 200 + 5000, abs=0.01)
    assert area(built.extent(AS_PROVIDED, ROUTING_CONTEXT)) == pytest.approx(800 * 200 + 400 * 200 + 5000, abs=0.01)
    for level in LEVELS:
        for frame in both:
            extent = built.extent(level, frame.name)
            assert extent.is_valid and frame.geometry.buffer(0.002).covers(extent)
            # Coordinates are on the 1 mm grid, so the bytes written are the geometry measured.
            coordinates = shapely.get_coordinates(extent)
            assert np.allclose(coordinates, np.round(coordinates, 3), atol=1e-9)
        assert shapely.covers(built.extent(level, ROUTING_CONTEXT).buffer(0.002), built.extent(level, REPORTING_FRAME))
    wgs84 = built.extent_wgs84(AS_PROVIDED, REPORTING_FRAME)
    assert 99 < wgs84.bounds[0] < 101 and 20 < wgs84.bounds[1] < 21

    record = built.record
    assert json.loads(json.dumps(record)) == record
    assert record["schema_version"] == "floodguard.flood_input.v1"
    assert (record["case_id"], record["lane"], record["tier"], record["temporal_relation"]) == ("SE1", "SCN-ENV", "T1", "season_window")
    assert record["source_timestamp"] == "2024-08-01/2024-10-12" and record["season_window"] == ["2024-08-01", "2024-10-12"]
    assert record["confidence_class"] == "low" and record["confidence_basis"] and record["assumptions"]
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False
    assert record["rights"]["record_status"] == "confirmed" and record["rights"]["licence"]["name"] == "CC BY-SA 4.0"
    assert record["protocol_sha256"] == flood_inputs.protocol_hashes(rules)
    assert record["frames"][REPORTING_FRAME]["units"] == ["U1", "U2"]
    assert record["frames"][REPORTING_FRAME]["area_km2"] == pytest.approx(2.0, abs=1e-6)
    assert record["frames"][ROUTING_CONTEXT]["area_km2"] == pytest.approx(3.0, abs=1e-6)
    assert record["repair"]["parts_repaired"] == 1 and record["repair"]["source_parts_invalid"] == 1
    assert record["levels"]["one_pixel_m"] == 20.0 and record["levels"]["none_is_central"] is True
    assert "owner choice 2" in record["levels"]["rule"]
    # The footprint covers the whole reporting frame and the routing context up to x = 2200 m.
    assert record["footprint"]["by_frame"][REPORTING_FRAME]["share_of_frame"] == pytest.approx(1.0, abs=1e-6)
    assert record["footprint"]["by_frame"][ROUTING_CONTEXT]["share_of_frame"] == pytest.approx(2700 / 3000, abs=1e-6)
    assert record["permanent_water"] is None
    assert "area_on_permanent_water_km2" not in record["levels"]["by_level"][AS_PROVIDED][REPORTING_FRAME]


def test_an_extent_goes_into_the_closure_rule_as_it_is(rules, grant) -> None:
    """The closure rule (plan task E3) takes a valid extent in longitude and latitude and measures in EPSG:32647."""

    from floodguard import closure_rules

    both = frames()
    built = flood_inputs.build_flood_input(lonlat(metres(400, 400, 600, 600)), both, spec=spec(), rules=rules, grant=grant)
    nodes = {"a": lonlat(shapely.Point(EAST + 300, NORTH + 500)).coords[0], "b": lonlat(shapely.Point(EAST + 700, NORTH + 500)).coords[0],
             "c": lonlat(shapely.Point(EAST + 300, NORTH + 900)).coords[0]}
    edges = [{"edge_id": "crossing", "from_node": "a", "to_node": "b"}, {"edge_id": "clear", "from_node": "a", "to_node": "c"}]
    lengths = {}
    for level in LEVELS:
        extent = built.extent_wgs84(level, ROUTING_CONTEXT)
        assert extent.is_valid
        rows = closure_rules.edge_intersections(edges, nodes, extent)
        assert [row["edge_id"] for row in rows] == ["crossing"]
        lengths[level] = rows[0]["intersection_length_m"]
    # The 400 m edge crosses the 200 m square; one pixel less or more on each side at the minus and plus levels.
    assert lengths == {MINUS: pytest.approx(160, abs=0.01), AS_PROVIDED: pytest.approx(200, abs=0.01), PLUS: pytest.approx(240, abs=0.01)}


def test_frames_and_levels_are_checked(rules, grant) -> None:
    both = frames()
    product = lonlat(metres(100, 100, 300, 300))
    with pytest.raises(FloodInputError, match="needs its frames, each once"):
        flood_inputs.build_flood_input(product, [], spec=spec(), rules=rules, grant=grant)
    with pytest.raises(FloodInputError, match="needs its frames, each once"):
        flood_inputs.build_flood_input(product, [both[0], both[0]], spec=spec(), rules=rules, grant=grant)
    with pytest.raises(FloodInputError, match="minus, as_provided and plus"):
        flood_inputs.build_flood_input(None, both, spec=spec(), rules=rules, grant=grant, levels={AS_PROVIDED: MultiPolygon()}, repair={})
    with pytest.raises(FloodInputError, match="needs its units, each once"):
        flood_inputs.frame_from_units(REPORTING_FRAME, "x", [("U1", product), ("U1", product)], {})
    with pytest.raises(FloodInputError, match="needs its units, each once"):
        flood_inputs.frame_from_units(REPORTING_FRAME, "x", [], {})
    with pytest.raises(FloodInputError, match="has no polygon"):
        flood_inputs.frame_from_units(REPORTING_FRAME, "x", [("U1", shapely.Point(99.9, 20.3))], {})
    with pytest.raises(FloodInputError, match="has no polygon"):
        flood_inputs.frame_from_wgs84(ROUTING_CONTEXT, "x", shapely.LineString([(99.9, 20.3), (99.91, 20.3)]), {})


# ---------------------------------------------------------------------------
# Permanent water: the scoring frame of protocol v1a
# ---------------------------------------------------------------------------


def land_cover(path: Path, *, crs: str = ANALYSIS_CRS) -> Path:
    """An invented land-cover raster of 10 m cells over 1 km by 1 km: cropland, a block of water, a block of no value."""

    cells = np.full((100, 100), 40, dtype="uint8")
    cells[20:40, 10:20] = 80        # x 100..200 m, y 600..800 m: 100 m by 200 m of permanent water
    cells[90:95, 90:100] = 0        # x 900..1000 m, y 50..100 m: no land-cover value
    tags = {"product_version": "V2.0.0", "time_start": "2021-01-01T00:00:00Z", "time_end": "2021-12-31T23:59:59Z",
            "license": "CC-BY 4.0 - https://creativecommons.org/licenses/by/4.0/", "copyright": "An invented land-cover project 2021"}
    with rasterio.open(path, "w", driver="GTiff", height=100, width=100, count=1, dtype="uint8", crs=crs, nodata=0,
                       transform=from_origin(EAST, NORTH + 1000, 10, 10)) as target:
        target.write(cells, 1)
        target.update_tags(**tags)
    return path


def test_permanent_water_is_every_cell_of_class_80(tmp_path: Path, rules) -> None:
    frame = flood_inputs.frame_from_wgs84(REPORTING_FRAME, "one invented frame", lonlat(metres(50, 50, 950, 950)), {})
    water = flood_inputs.permanent_water(land_cover(tmp_path / "cover.tif"), frame, water_class=rules.permanent_water_class,
                                         source_name=rules.permanent_water_source)
    assert water.frame == REPORTING_FRAME and water.geometry.is_valid
    assert area(water.geometry) == pytest.approx(100 * 200, abs=0.01)
    record = water.record
    assert (record["source"], record["class"]) == ("ESA WorldCover 2021 v200", 80)
    assert record["permanent_water_km2"] == pytest.approx(0.02) and record["frame_km2"] == pytest.approx(0.81, abs=1e-6)
    assert record["non_permanent_water_km2"] == pytest.approx(0.79, abs=1e-6)
    # Cells with no land-cover value are not water. Their area inside the frame is reported: 50 m by 50 m.
    assert record["no_land_cover_value_km2"] == pytest.approx(0.0025)
    assert record["class_cells_in_window"] == 200 and record["sha256"] == hashlib.sha256((tmp_path / "cover.tif").read_bytes()).hexdigest()
    assert record["licence"].startswith("CC-BY 4.0") and record["attribution"] == "An invented land-cover project 2021"
    assert "scoring_frame" in record["rule"] and "class 80" in record["rule"]


def test_permanent_water_refuses_a_raster_that_does_not_cover_the_frame(tmp_path: Path, rules) -> None:
    path = land_cover(tmp_path / "cover.tif")
    beyond = flood_inputs.frame_from_wgs84(REPORTING_FRAME, "one invented frame", lonlat(metres(500, 500, 1500, 900)), {})
    with pytest.raises(FloodInputError, match="does not cover frame"):
        flood_inputs.permanent_water(path, beyond, water_class=80, source_name=rules.permanent_water_source)
    whole = flood_inputs.Frame(REPORTING_FRAME, "the whole raster", MultiPolygon([metres(0, 0, 1000, 1000)]), {})
    assert area(flood_inputs.permanent_water(path, whole, water_class=80, source_name="x").geometry) == pytest.approx(20_000, abs=0.01)
    dry = flood_inputs.permanent_water(path, whole, water_class=95, source_name="x")
    assert dry.geometry.is_empty and dry.record["permanent_water_km2"] == 0


def test_permanent_water_is_read_from_a_raster_in_longitude_and_latitude(tmp_path: Path, rules) -> None:
    """The WorldCover tiles are in EPSG:4326: cell footprints are projected to EPSG:32647 before they are measured."""

    west, south, east, north = lonlat(metres(0, 0, 1000, 1000)).bounds
    step = 0.0001
    width, height = int((east - west) / step) + 20, int((north - south) / step) + 20
    cells = np.full((height, width), 10, dtype="uint8")
    cells[30:50, 30:60] = 80
    path = tmp_path / "cover_wgs84.tif"
    transform = from_origin(west - 10 * step, north + 10 * step, step, step)
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width, count=1, dtype="uint8", crs=WGS84_CRS,
                       nodata=0, transform=transform) as target:
        target.write(cells, 1)
    block = box(transform.c + 30 * step, transform.f - 50 * step, transform.c + 60 * step, transform.f - 30 * step)
    expected = flood_inputs.project(block, WGS84_CRS, ANALYSIS_CRS)
    frame = flood_inputs.frame_from_wgs84(REPORTING_FRAME, "one invented frame", lonlat(metres(0, 0, 1000, 1000)), {})
    water = flood_inputs.permanent_water(path, frame, water_class=80, source_name=rules.permanent_water_source)
    assert expected.area == pytest.approx(30 * 20 * 10.45 * 11.07, rel=0.02)   # about 10.5 m by 11.1 m per cell here
    # The same block, up to the 1 mm coordinate grid of the written geometry.
    assert area(water.geometry) == pytest.approx(area(shapely.intersection(expected, frame.geometry)), abs=1.0)
    assert water.record["raster_crs"] == WGS84_CRS and water.record["no_land_cover_value_km2"] == 0


def test_permanent_water_does_not_cut_the_extent_and_gives_the_flood_likelihood_areas(tmp_path: Path, rules, grant) -> None:
    """Protocol v1a scoring frame: flooded share of the unit's non-permanent-water land. Nothing else reads the water."""

    frame = flood_inputs.frame_from_wgs84(REPORTING_FRAME, "one invented frame", lonlat(metres(50, 50, 950, 950)), {})
    water = flood_inputs.permanent_water(land_cover(tmp_path / "cover.tif"), frame, water_class=80, source_name=rules.permanent_water_source)
    flood = metres(150, 650, 350, 850)                  # 200 m by 200 m; 50 m by 150 m of it lies on the water
    built = flood_inputs.build_flood_input(lonlat(flood), [frame], spec=spec(), rules=rules, grant=grant, water=water)
    summary = built.record["levels"]["by_level"][AS_PROVIDED][REPORTING_FRAME]
    assert area(built.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(40_000, abs=0.01)   # the extent is whole
    assert summary["area_km2"] == pytest.approx(0.04)
    assert summary["area_on_permanent_water_km2"] == pytest.approx(0.0075)
    assert summary["area_outside_permanent_water_km2"] == pytest.approx(0.0325)
    assert built.record["permanent_water"]["permanent_water_km2"] == pytest.approx(0.02)

    areas = flood_inputs.flooded_land_areas(frame.geometry, built.extent(AS_PROVIDED, REPORTING_FRAME), water.geometry)
    assert set(areas) == {"flooded_non_permanent_water_land_area", "non_permanent_water_land_area"}
    assert areas["non_permanent_water_land_area"] == pytest.approx(900 * 900 - 20_000, abs=0.05)
    assert areas["flooded_non_permanent_water_land_area"] == pytest.approx(40_000 - 7_500, abs=0.05)
    dry = flood_inputs.flooded_land_areas(frame.geometry, MultiPolygon(), MultiPolygon())
    assert dry == {"flooded_non_permanent_water_land_area": 0.0, "non_permanent_water_land_area": pytest.approx(810_000, abs=0.05)}

    other = flood_inputs.PermanentWater("another_frame", water.geometry, water.record)
    with pytest.raises(FloodInputError, match="not among the frames of the case"):
        flood_inputs.build_flood_input(lonlat(flood), [frame], spec=spec(), rules=rules, grant=grant, water=other)


# ---------------------------------------------------------------------------
# SE1 and O2 on an invented product archive
# ---------------------------------------------------------------------------


def write_archive(external: Path, relative_path: str, layers: dict[str, dict]) -> Path:
    """Write an invented file geodatabase with the given layers and zip it as the product archive is zipped."""

    geopandas = pytest.importorskip("geopandas")
    pandas = pytest.importorskip("pandas")
    pyogrio = pytest.importorskip("pyogrio")
    if "w" not in pyogrio.list_drivers().get("OpenFileGDB", ""):
        pytest.skip("this GDAL build cannot write a file geodatabase")
    archive = external / relative_path
    archive.parent.mkdir(parents=True, exist_ok=True)
    geodatabase = external / "scratch" / flood_inputs.GEODATABASE_4009
    geodatabase.parent.mkdir(parents=True, exist_ok=True)
    for index, (name, layer) in enumerate(layers.items()):
        columns = {key: [value] for key, value in layer["attributes"].items()}
        if "Sensor_Date" in columns:
            columns["Sensor_Date"] = [pandas.Timestamp(columns["Sensor_Date"][0], tz="UTC")]
        table = geopandas.GeoDataFrame(columns, geometry=[layer["geometry"]], crs=WGS84_CRS)
        with warnings.catch_warnings():
            # The writer notes that an integer column is stored as a float column; the loader reads it back as 0.
            warnings.simplefilter("ignore", RuntimeWarning)
            pyogrio.write_dataframe(table, geodatabase, layer=name, driver="OpenFileGDB", append=index > 0)
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in sorted(geodatabase.iterdir()):
            zipped.write(path, f"{flood_inputs.GEODATABASE_4009}/{path.name}")
    return archive


def product_case(tmp_path: Path, *, attributes: dict | None = None, record_changes: dict | None = None) -> dict:
    """An invented repository root with a rights record, and an external root with the archive that record names."""

    flood_attributes = {"Field_Validation": 0, "Sensor_Date": "2024-10-22", "EventCode": "FL20240912THA", **(attributes or {})}
    layers = {
        ACCUMULATED: {"attributes": flood_attributes, "geometry": lonlat(MultiPolygon([
            metres(100, 100, 500, 300), bow_tie(1200, 400, 200), metres(2100, 600, 2400, 800), metres(9000, 9000, 9100, 9100)]))},
        LAYER_22_OCT: {"attributes": flood_attributes, "geometry": lonlat(MultiPolygon([
            metres(200, 150, 400, 250), metres(600, 600, 900, 630)]))},
        flood_inputs.ANALYSIS_EXTENT_LAYER_4009: {"attributes": {"EventCode": "FL20240912THA"},
                                                  "geometry": lonlat(MultiPolygon([metres(-2000, -2000, 12000, 12000)]))},
    }
    record = json.loads((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_text(encoding="utf-8"))
    external = tmp_path / "external"
    archive = write_archive(external, record["archive"]["relative_path"], layers)
    record["archive"].update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), bytes=archive.stat().st_size)
    for key, value in (record_changes or {}).items():
        record[key] = value
    root = tmp_path / "repository"
    path = root / rights_basis.RIGHTS_BASIS_4009_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return {"registry": RightsRegistry(root), "external": external, "archive": archive, "record_path": path, "record": record}


def test_se1_is_the_season_envelope_scenario(tmp_path: Path, rules) -> None:
    case = product_case(tmp_path)
    loaded = flood_inputs.load_se1(frames(), rules=rules, registry=case["registry"], external_root=case["external"])
    record = loaded.record
    assert (record["case_id"], record["lane"], record["tier"]) == ("SE1", "SCN-ENV", "T1")
    # The layer carries Sensor_Date 2024-10-22, and it is still a season window: it has no date per patch.
    assert record["temporal_relation"] == "season_window" and record["acquisition_date"] is None
    assert record["sensor_date_attribute"] == "2024-10-22" and record["case_reference_date"] is None
    assert record["season_window"] == ["2024-08-01", "2024-10-12"] and record["source_timestamp"] == "2024-08-01/2024-10-12"
    assert record["not_an_observation_of_any_day"] is True and record["used_as_provided"] is True
    assert record["field_validation"] == 0 and record["standard_sentence"] == rules.standard_4009_sentence
    assert record["credit"] == CREDIT and record["input_name"] == "UNOSAT/GISTDA product 4009, accumulated layer"
    assert record["source"]["layer"] == ACCUMULATED and record["source"]["footprint_layer"] == flood_inputs.ANALYSIS_EXTENT_LAYER_4009
    assert record["source"]["archive"]["sha256"] == case["record"]["archive"]["sha256"]
    assert record["source"]["layer_attributes"] == {"Field_Validation": 0, "Sensor_Date": "2024-10-22", "EventCode": "FL20240912THA"}
    assert record["rights"]["rights_level"] == "public" and record["rights"]["licence"]["name"] == "CC BY-SA 4.0"
    assert record["confidence_class"] == "low" and "did not validate" in record["confidence_basis"]
    assert any("not an observation of any day" in line for line in record["assumptions"])
    # Four parts in the layer; the far one is not read; one of the three read was invalid and was repaired.
    repair = record["repair"]
    assert (repair["source_parts"], repair["source_parts_invalid"], repair["parts_read"], repair["parts_repaired"]) == (4, 1, 3, 1)
    assert area(loaded.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(400 * 200 + 200 * 200 / 2, abs=2.0)
    assert area(loaded.extent(AS_PROVIDED, ROUTING_CONTEXT)) == pytest.approx(400 * 200 + 200 * 200 / 2 + 300 * 200, abs=2.0)
    assert record["footprint"]["by_frame"][ROUTING_CONTEXT]["share_of_frame"] == pytest.approx(1.0, abs=1e-6)


def test_o2_is_its_own_dated_case(tmp_path: Path, rules) -> None:
    case = product_case(tmp_path)
    loaded = flood_inputs.load_o2(frames(), rules=rules, registry=case["registry"], external_root=case["external"], footprint_layer=None)
    record = loaded.record
    assert (record["case_id"], record["lane"], record["tier"]) == ("O2", "OBS", "T3")
    assert record["acquisition_date"] == "2024-10-22" == record["case_reference_date"] == record["source_timestamp"]
    assert record["temporal_relation"] == "event_aligned" and record["season_window"] is None
    assert record["label"] == "late-season residual water, 22 Oct 2024"
    assert "date only" in record["acquisition_time_precision"]
    assert any("does not describe the September event" in line for line in record["assumptions"])
    assert "not_an_observation_of_any_day" not in record
    # The rights record names only the accumulated layer as in scope, so this layer is held at the local level.
    assert record["rights"]["rights_level"] == "local" and record["rights"]["record_status"] == "confirmed"
    assert record["footprint"] is None and loaded.footprints == {}
    # The 30 m strip is gone at the minus level; the 200 m by 100 m block keeps 160 m by 60 m.
    assert area(loaded.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(200 * 100 + 300 * 30, abs=2.0)
    assert area(loaded.extent(MINUS, REPORTING_FRAME)) == pytest.approx(160 * 60, abs=2.0)
    assert len(loaded.extent(MINUS, REPORTING_FRAME).geoms) == 1


def test_no_file_is_opened_before_the_rights_registry_allows_the_use(tmp_path: Path, rules) -> None:
    record = json.loads((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_text(encoding="utf-8"))
    record["owner_confirmation"].update(status="pending", confirmed_by=[], confirmed_on=None)
    record.update(record_status="draft_pending_owner_confirmation", signed_by_human=False, human_rights_clearance=False)
    root = tmp_path / "repository"
    path = root / rights_basis.RIGHTS_BASIS_4009_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    # There is no archive at all under this external root: the refusal comes from the record, before any read.
    for loader in (flood_inputs.load_se1, flood_inputs.load_o2):
        with pytest.raises(RightsRefusedError, match="not confirmed by the owners"):
            loader(frames(), rules=rules, registry=RightsRegistry(root), external_root=tmp_path / "nothing_here")
    with pytest.raises(RightsRefusedError, match="no rights record is registered"):
        flood_inputs.load_se1(frames(), rules=rules, registry=RightsRegistry(root, ()), external_root=tmp_path / "nothing_here")


def test_the_archive_must_be_the_one_the_rights_record_names(tmp_path: Path, rules) -> None:
    case = product_case(tmp_path)
    with case["archive"].open("ab") as stream:
        stream.write(b"\0")
    with pytest.raises(RightsRefusedError, match="size differs"):
        flood_inputs.load_se1(frames(), rules=rules, registry=case["registry"], external_root=case["external"])


def test_a_layer_that_is_not_what_the_signed_files_say_is_refused(tmp_path: Path, rules) -> None:
    checked = product_case(tmp_path / "checked", attributes={"Field_Validation": 1})
    with pytest.raises(FloodInputError, match="Field_Validation is 1"):
        flood_inputs.load_se1(frames(), rules=rules, registry=checked["registry"], external_root=checked["external"])
    other_event = product_case(tmp_path / "event", attributes={"EventCode": "FL20250101THA"})
    with pytest.raises(FloodInputError, match="EventCode"):
        flood_inputs.load_o2(frames(), rules=rules, registry=other_event["registry"], external_root=other_event["external"])
    other_date = product_case(tmp_path / "date", attributes={"Sensor_Date": "2024-10-12"})
    with pytest.raises(FloodInputError, match="not the date in the layer name"):
        flood_inputs.load_o2(frames(), rules=rules, registry=other_date["registry"], external_root=other_date["external"])
    other_credit = product_case(tmp_path / "credit", record_changes={"required_attribution_text": "Another credit"})
    with pytest.raises(FloodInputError, match="credit of the rights record"):
        flood_inputs.load_se1(frames(), rules=rules, registry=other_credit["registry"], external_root=other_credit["external"])
    good = product_case(tmp_path / "good")
    with pytest.raises(FloodInputError, match="not a product 4009 case"):
        flood_inputs.load_product_4009("O1", frames(), rules=rules, registry=good["registry"], external_root=good["external"])


def test_the_product_spec_follows_the_date_rule(rules) -> None:
    archive = {"file_name": "x.zip", "sha256": "0" * 64, "bytes": 1}
    attributes = {"Field_Validation": 0, "Sensor_Date": "2024-10-22", "EventCode": "FL20240912THA"}
    o2 = flood_inputs.product_4009_spec("O2", rules, attributes, archive, "FL20240912THA")
    assert (o2.temporal_relation, o2.acquisition_date, o2.case_reference_date) == ("event_aligned", "2024-10-22", "2024-10-22")
    se1 = flood_inputs.product_4009_spec("SE1", rules, attributes, archive, "FL20240912THA")
    assert (se1.temporal_relation, se1.acquisition_date, se1.season_window) == ("season_window", None, ("2024-08-01", "2024-10-12"))
    with pytest.raises(FloodInputError, match="not a product 4009 case"):
        flood_inputs.product_4009_spec("O1", rules, attributes, archive, "FL20240912THA")
    # Had protocol v1a given case O2 a September reference date, the same layer would be dated_other and refused as T3.
    moved = flood_inputs.FloodInputRules(**{**rules.__dict__, "cases": {**rules.cases, "O2": {**rules.cases["O2"], "case_reference_date": "2024-09-15"}}})
    with pytest.raises(FloodInputError, match="the dates give dated_other"):
        flood_inputs.product_4009_spec("O2", moved, attributes, archive, "FL20240912THA")


# ---------------------------------------------------------------------------
# O1: an own radar candidate, on an invented raster
# ---------------------------------------------------------------------------

NO_ANSWER = 255


def candidate_cells() -> np.ndarray:
    """50 by 50 cells of 20 m: a block of flood, a three-cell blob, five cells that touch at corners, cells with no answer."""

    cells = np.zeros((50, 50), dtype="uint8")
    cells[10:20, 10:20] = 1                        # x 200..400 m, y 600..800 m
    cells[40, 5:8] = 1                             # three cells in a row
    for step in range(5):
        cells[30 + step, 30 + step] = 1            # five cells that touch only at their corners
    cells[0:5, :] = NO_ANSWER                      # the top 100 m of the grid
    cells[5:10, 40:45] = NO_ANSWER                 # x 800..900 m, y 800..900 m
    return cells


def write_raster(path: Path, cells: np.ndarray, *, crs: str = ANALYSIS_CRS, cell_m: float = 20.0, nodata: int | None = NO_ANSWER) -> str:
    with rasterio.open(path, "w", driver="GTiff", height=cells.shape[0], width=cells.shape[1], count=1, dtype="uint8",
                       crs=crs, nodata=nodata, transform=from_origin(EAST, NORTH + cells.shape[0] * cell_m, cell_m, cell_m)) as target:
        target.write(cells, 1)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(tmp_path: Path, rules, *, kind: str = "one_pixel", rasters: dict[str, np.ndarray] | None = None, **changes) -> Path:
    """Write an invented candidate (rasters and receipt) and return the path of its receipt."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    rasters = rasters or {AS_PROVIDED: candidate_cells()}
    entries = {level: {"path": f"candidate_{level}.tif", "sha256": write_raster(tmp_path / f"candidate_{level}.tif", cells)}
               for level, cells in rasters.items()}
    receipt = {
        "schema_version": flood_inputs.RADAR_RECEIPT_SCHEMA,
        "case_id": "O1",
        "candidate_id": "UN-SPIDER reproduction" if kind == "one_pixel" else "M1-v2",
        "rights_input_id": "invented_sentinel1",
        "acquisition_time_utc": "2024-09-15T23:16:00Z",
        "acquisition_date": "2024-09-16",
        "level_kind": kind,
        "level_parameter": "one pixel on the output extent" if kind == "one_pixel" else "Kittler-Illingworth threshold -1 / 0 / +1 dB",
        "rasters": entries,
        "encoding": {"flood": 1, "not_flood": 0, "no_answer": NO_ANSWER},
        "protocol_sha256": flood_inputs.protocol_hashes(rules),
        "inputs": {"scene": {"sha256": "1" * 64}},
        "source_timestamp": "2024-09-15T23:16:00Z",
        "generated_at_utc": "2026-10-04T00:00:00Z",
        "confidence_class": "low",
        "confidence_basis": "An invented candidate.",
        "assumptions": ["An invented candidate on an invented grid."],
        "official_warning": False,
        "operational_status": "non_operational",
        **changes,
    }
    path = tmp_path / "candidate_receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def radar_registry(tmp_path: Path) -> RightsRegistry:
    record = {"schema": "floodguard.test_rights_basis.v1", "record_id": "invented_sentinel1_v1", "legal_notice_title": "An invented notice",
              "required_attribution_text": "Contains invented radar data", "signed_by_human": True, "human_rights_clearance": True,
              "official_warning": False, "operational_status": "non_operational", "can_feed_decision_layer": False}
    root = tmp_path / "repository"
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "invented_rights.json").write_text(json.dumps(record), encoding="utf-8")
    return RightsRegistry(root, (RegisteredRecord("invented_sentinel1", "docs/invented_rights.json", "an invented radar source"),))


def radar_frames() -> list[flood_inputs.Frame]:
    reporting = flood_inputs.Frame(REPORTING_FRAME, "one invented unit", MultiPolygon([metres(100, 100, 900, 900)]), {},
                                   {"U1": MultiPolygon([metres(100, 100, 900, 900)])})
    routing = flood_inputs.Frame(ROUTING_CONTEXT, "an invented corridor", MultiPolygon([metres(0, 0, 1200, 1000)]), {})
    return [reporting, routing]


def test_o1_reads_a_candidate_raster_with_its_receipt(tmp_path: Path, rules) -> None:
    receipt = candidate(tmp_path / "candidate", rules)
    loaded = flood_inputs.load_o1(receipt, radar_frames(), rules=rules, registry=radar_registry(tmp_path))
    record = loaded.record
    assert json.loads(json.dumps(record)) == record
    assert (record["case_id"], record["lane"], record["tier"]) == ("O1", "OBS", "T2")
    assert record["input_name"] == "UN-SPIDER reproduction" and record["own_candidate"] is True
    assert (record["acquisition_date"], record["case_reference_date"], record["temporal_relation"]) == ("2024-09-16", "2024-09-15", "event_aligned")
    assert record["confidence_class"] == "low" and "own unqualified candidate" in record["confidence_basis"]
    assert record["geometry_kind"] == "raster" and record["source"]["cell_m"] == 20.0
    assert record["source"]["receipt"]["sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert record["rights"]["rights_level"] == "local" and record["rights"]["attribution"] == "Contains invented radar data"
    assert record["protocol_sha256"] == flood_inputs.protocol_hashes(rules)

    # As provided: the block, the blob and the five cells, all inside the reporting frame.
    assert area(loaded.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(100 * 400 + 3 * 400 + 5 * 400, abs=0.01)
    # Minus: a 20 m buffer leaves 160 m by 160 m of the block; a single row of cells and single cells vanish.
    assert area(loaded.extent(MINUS, REPORTING_FRAME)) == pytest.approx(160 * 160, abs=0.01)
    assert area(loaded.extent(PLUS, REPORTING_FRAME)) > area(loaded.extent(AS_PROVIDED, REPORTING_FRAME))
    assert record["level_kind"] == "one_pixel" and "E1-OP5" in record["levels"]["rule"] and record["levels_nested"] is True

    # Unknown is not dry: the cells with no answer and the part of a frame outside the grid are reported.
    coverage = record["coverage"]
    assert coverage[REPORTING_FRAME] == {"grid_share_of_frame": 1.0, "no_answer_share_of_frame": 0.015625, "answered_share_of_frame": 0.984375}
    assert coverage[ROUTING_CONTEXT]["grid_share_of_frame"] == pytest.approx(1000 / 1200, abs=1e-6)
    assert coverage[ROUTING_CONTEXT]["no_answer_share_of_frame"] == pytest.approx((100 * 1000 + 100 * 100) / 1_200_000, abs=1e-6)

    # The 5-pixel rule of the closure rule needs a neighbourhood the protocol does not give: nothing is built without it.
    assert loaded.closure_extents == {} and record["closure_extents"]["built"] is False
    assert "E1-OP6" in record["closure_extents"]["reason"]


@pytest.mark.parametrize(("connectivity", "polygons", "dropped", "cells_dropped", "kept_m2"),
                         [(4, 7, 6, 8, 40_000), (8, 3, 1, 3, 42_000)])
def test_o1_drops_polygons_under_five_pixels_once_the_neighbourhood_is_given(
        tmp_path: Path, rules, connectivity: int, polygons: int, dropped: int, cells_dropped: int, kept_m2: float) -> None:
    """Protocol v1b closure_rule_v1: for T2 rasters, polygons under 5 pixels are dropped before intersection."""

    receipt = candidate(tmp_path / "candidate", rules)
    loaded = flood_inputs.load_o1(receipt, radar_frames(), rules=rules, registry=radar_registry(tmp_path),
                                  closure_polygon_connectivity=connectivity)
    closure = loaded.record["closure_extents"]
    assert closure["built"] is True and closure["levels_built"] == [AS_PROVIDED]
    counts = closure["by_level"][AS_PROVIDED]
    assert (counts["polygons"], counts["polygons_dropped"], counts["cells_dropped"]) == (polygons, dropped, cells_dropped)
    assert (counts["minimum_px"], counts["connectivity"]) == (5, connectivity)
    assert area(loaded.closure_extents[AS_PROVIDED][REPORTING_FRAME]) == pytest.approx(kept_m2, abs=0.01)
    # The extent itself keeps every flood cell: the rule is about closures only.
    assert area(loaded.extent(AS_PROVIDED, REPORTING_FRAME)) == pytest.approx(43_200, abs=0.01)


def test_o1_takes_three_threshold_rasters_as_its_three_levels(tmp_path: Path, rules) -> None:
    """Protocol v1b t2_levels_by_input: M1-v2 levels are three thresholds, not a buffer."""

    def block(first: int, last: int) -> np.ndarray:
        cells = np.zeros((50, 50), dtype="uint8")
        cells[first:last, first:last] = 1
        return cells

    receipt = candidate(tmp_path / "candidate", rules, kind="threshold",
                        rasters={MINUS: block(11, 19), AS_PROVIDED: block(10, 20), PLUS: block(9, 21)})
    loaded = flood_inputs.load_o1(receipt, radar_frames(), rules=rules, registry=radar_registry(tmp_path), closure_polygon_connectivity=4)
    assert [area(loaded.extent(level, REPORTING_FRAME)) for level in LEVELS] == pytest.approx([160 * 160, 200 * 200, 240 * 240], abs=0.01)
    record = loaded.record
    assert record["input_name"] == "M1-v2" and record["level_kind"] == "threshold" and record["levels_nested"] is True
    assert "No buffer is applied" in record["levels"]["rule"] and "Kittler-Illingworth" in record["levels"]["rule"]
    assert record["closure_extents"]["levels_built"] == sorted(LEVELS)
    assert set(record["source"]["rasters"]) == set(LEVELS)


def test_o1_refuses_a_candidate_without_a_confirmed_rights_record(tmp_path: Path, rules) -> None:
    """No rights record exists for the radar source data in the repository today (open point E1-OP2)."""

    receipt = candidate(tmp_path / "candidate", rules)
    with pytest.raises(RightsRefusedError, match="no rights record is registered"):
        flood_inputs.load_o1(receipt, radar_frames(), rules=rules, registry=RightsRegistry(ROOT))
    unsigned = candidate(tmp_path / "unsigned", rules, rights_input_id=rights.SENTINEL2_AUTOMATED_TRACK)
    with pytest.raises(RightsRefusedError, match="not signed by a human"):
        flood_inputs.load_o1(unsigned, radar_frames(), rules=rules, registry=RightsRegistry(ROOT))


def test_o1_refuses_a_receipt_that_is_not_the_interface(tmp_path: Path, rules) -> None:
    registry = radar_registry(tmp_path)

    def load(name: str, **changes) -> None:
        flood_inputs.load_o1(candidate(tmp_path / name, rules, **changes), radar_frames(), rules=rules, registry=registry)

    incomplete = candidate(tmp_path / "incomplete", rules)
    receipt = json.loads(incomplete.read_text(encoding="utf-8"))
    del receipt["assumptions"], receipt["rights_input_id"]
    incomplete.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(FloodInputError, match="lacks: rights_input_id, assumptions"):
        flood_inputs.load_o1(incomplete, radar_frames(), rules=rules, registry=registry)
    with pytest.raises(FloodInputError, match="is not floodguard.radar_candidate_receipt.v1"):
        load("schema", schema_version="floodguard.other.v1")
    with pytest.raises(FloodInputError, match="names no flood input"):
        load("name", candidate_id="legacy 2.25 dB mask")
    with pytest.raises(FloodInputError, match="names no flood input"):
        load("case", case_id="O2")
    with pytest.raises(FloodInputError, match="not an official warning"):
        load("warning", official_warning=True)
    with pytest.raises(FloodInputError, match="low confidence and its assumptions"):
        load("confidence", confidence_class="medium")
    with pytest.raises(FloodInputError, match="low confidence and its assumptions"):
        load("assumptions", assumptions=[])
    with pytest.raises(FloodInputError, match="other protocol files"):
        load("protocol", protocol_sha256={"planning_protocol_v1a": "0" * 64, "planning_protocol_v1b": "0" * 64})
    with pytest.raises(FloodInputError, match="level_kind is threshold"):
        load("kind", level_kind="spatial")
    with pytest.raises(FloodInputError, match="level_kind is threshold"):
        load("levels", level_kind="threshold")           # a threshold candidate names three rasters, not one
    with pytest.raises(FloodInputError, match="YYYY-MM-DD"):
        load("date", acquisition_date="16 Sep 2024")


def test_o1_refuses_a_raster_that_is_not_the_one_the_receipt_names_or_not_on_the_grid(tmp_path: Path, rules) -> None:
    registry, both = radar_registry(tmp_path), radar_frames()

    swapped = candidate(tmp_path / "swapped", rules)
    write_raster(swapped.parent / "candidate_as_provided.tif", np.zeros((50, 50), dtype="uint8"))
    with pytest.raises(FloodInputError, match="is not the raster the receipt names"):
        flood_inputs.load_o1(swapped, both, rules=rules, registry=registry)

    def rewritten(name: str, cells: np.ndarray, **raster) -> Path:
        path = candidate(tmp_path / name, rules)
        digest = write_raster(path.parent / "candidate_as_provided.tif", cells, **raster)
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["rasters"][AS_PROVIDED]["sha256"] = digest
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path

    with pytest.raises(FloodInputError, match="delivered in EPSG:32647"):
        flood_inputs.load_o1(rewritten("crs", candidate_cells(), crs="EPSG:32648"), both, rules=rules, registry=registry)
    with pytest.raises(FloodInputError, match="nodata value must be the no_answer value"):
        flood_inputs.load_o1(rewritten("nodata", candidate_cells(), nodata=None), both, rules=rules, registry=registry)
    odd = candidate_cells()
    odd[45, 45] = 7
    with pytest.raises(FloodInputError, match="flood \\(1\\), not flood \\(0\\) or no answer"):
        flood_inputs.load_o1(rewritten("value", odd), both, rules=rules, registry=registry)
    # A one-pixel level is 20 m: a candidate on 10 m cells is refused, not buffered by another distance.
    with pytest.raises(FloodInputError, match="has 20 m cells; this raster has 10 m cells"):
        flood_inputs.load_o1(rewritten("cell", candidate_cells(), cell_m=10.0), both, rules=rules, registry=registry)

    def block(first: int, last: int, size: int = 50) -> np.ndarray:
        cells = np.zeros((size, size), dtype="uint8")
        cells[first:last, first:last] = 1
        return cells

    uneven = candidate(tmp_path / "uneven", rules, kind="threshold",
                       rasters={MINUS: block(11, 19, 40), AS_PROVIDED: block(10, 20), PLUS: block(9, 21)})
    with pytest.raises(FloodInputError, match="share one grid"):
        flood_inputs.load_o1(uneven, both, rules=rules, registry=registry)


def test_the_five_pixel_rule_needs_a_neighbourhood() -> None:
    flood = candidate_cells() == 1
    transform = from_origin(EAST, NORTH + 1000, 20, 20)
    with pytest.raises(FloodInputError, match="E1-OP6"):
        flood_inputs.drop_small_polygons(flood, transform, minimum_px=5, connectivity=6)
    nothing, counts = flood_inputs.drop_small_polygons(np.zeros((5, 5), dtype=bool), transform, minimum_px=5, connectivity=4)
    assert nothing.is_empty and counts["polygons"] == 0


# ---------------------------------------------------------------------------
# Written layers and their change notice
# ---------------------------------------------------------------------------


def test_a_change_notice_states_the_steps_of_the_rights_record_in_its_order() -> None:
    notice = flood_inputs.change_notice(clip_geometry="two invented units", repair_count=3, source_crs=WGS84_CRS,
                                        change=flood_inputs.level_sentence(MINUS, 20.0), credit=CREDIT, licence_name="CC BY-SA 4.0")
    assert notice == (
        "Changed by FloodGuard: clipped to two invented units; geometry repaired (make_valid; 3 parts repaired); "
        "reprojected from EPSG:4326 to EPSG:32647; extent shrunk by a 20 m negative buffer (the minus level of protocol "
        "v1b); coordinates snapped to a 0.001 m grid; not rasterised. Source: UNOSAT and GISTDA, FL20240912THA, UNOSAT "
        "product 4009, CC BY-SA 4.0."
    )
    record = json.loads((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_text(encoding="utf-8"))
    assert [step["id"] for step in record["change_notice"]["steps"]] == ["clip", "geometry_repair", "reprojection", "rasterisation"]
    order = [notice.index(text) for text in ("clipped to", "geometry repaired", "reprojected from", "not rasterised")]
    assert order == sorted(order)
    assert record["required_attribution_text"] in notice and record["licence"]["name"] in notice
    assert "{" not in notice
    assert "extent grown by a 20 m buffer" in flood_inputs.level_sentence(PLUS, 20.0)
    assert flood_inputs.level_sentence(AS_PROVIDED, 20.0) == "extent otherwise as provided"
    raster = flood_inputs.change_notice(clip_geometry="x", repair_count=0, source_crs=ANALYSIS_CRS, change="y", credit="z",
                                        licence_name="w", geometry_kind="raster")
    assert "kept in EPSG:32647" in raster and "polygonised from the cells of the raster" in raster
    with pytest.raises(FloodInputError, match="unknown level"):
        flood_inputs.level_sentence("central", 20.0)
    with pytest.raises(FloodInputError, match="whole number"):
        flood_inputs.change_notice(clip_geometry="x", repair_count=-1, source_crs=WGS84_CRS, change="y", credit="z", licence_name="w")
    with pytest.raises(FloodInputError, match="whole number"):
        flood_inputs.change_notice(clip_geometry="x", repair_count=True, source_crs=WGS84_CRS, change="y", credit="z", licence_name="w")
    with pytest.raises(FloodInputError, match="must be stated"):
        flood_inputs.change_notice(clip_geometry=" ", repair_count=0, source_crs=WGS84_CRS, change="y", credit="z", licence_name="w")


def test_a_written_layer_carries_its_rights_and_reads_back_as_the_same_geometry(rules, grant) -> None:
    both = frames()
    product = lonlat(MultiPolygon([metres(100, 100, 500, 300), bow_tie(1200, 400, 200)]))
    built = flood_inputs.build_flood_input(product, both, spec=spec(statements={"standard_sentence": rules.standard_4009_sentence,
                                                                                "used_as_provided": True, "field_validation": 0}),
                                           rules=rules, grant=grant, footprint=lonlat(metres(-1000, -1000, 3000, 2000)))
    reporting = both[0]
    properties = flood_inputs.layer_properties(built, level=PLUS, frame=reporting, what="flood_extent",
                                               change=flood_inputs.level_sentence(PLUS, rules.one_pixel_m))
    assert properties["licence"]["name"] == "CC BY-SA 4.0" and properties["credit"] == CREDIT
    assert properties["rights_level"] == "public" and properties["share_alike"]
    assert properties["rights_record"]["path"] == rights_basis.RIGHTS_BASIS_4009_PATH.as_posix()
    assert "1 parts repaired" in properties["change_notice"] and "two invented units" in properties["change_notice"]
    assert CREDIT in properties["change_notice"] and "CC BY-SA 4.0" in properties["change_notice"]
    assert properties["standard_sentence"] == rules.standard_4009_sentence and properties["field_validation"] == 0
    assert (properties["level"], properties["frame"], properties["lane"], properties["temporal_relation"]) == (PLUS, REPORTING_FRAME, "SCN-ENV", "season_window")
    assert properties["official_warning"] is False and properties["confidence_class"] == "low" and properties["assumptions"]
    assert properties["protocol_sha256"] == flood_inputs.protocol_hashes(rules)

    data = flood_inputs.encode_layer(built.extent(PLUS, REPORTING_FRAME), properties, "flood_extent__plus__reporting_frame")
    assert data == flood_inputs.encode_layer(built.extent(PLUS, REPORTING_FRAME), properties, "flood_extent__plus__reporting_frame")
    assert data.endswith(b"\n") and b"\r" not in data and data.decode("ascii")
    assert b"generated_at" not in data, "a layer file has no generation time, so its SHA-256 follows from its inputs"
    geometry, read = flood_inputs.decode_layer(data)
    assert read == properties and geometry.equals_exact(built.extent(PLUS, REPORTING_FRAME), 0.0)
    assert json.loads(data)["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::32647"

    footprint = flood_inputs.layer_properties(built, level=None, frame=reporting, what="product_footprint", change="analysis extent otherwise as provided")
    assert footprint["what"] == "product_footprint" and "0 parts repaired" in footprint["change_notice"]
    empty = flood_inputs.encode_layer(MultiPolygon(), properties, "empty")
    assert flood_inputs.decode_layer(empty)[0].is_empty

    for missing in ("source_timestamp", "confidence_class", "assumptions"):
        with pytest.raises(FloodInputError, match=f"states its {missing}"):
            flood_inputs.encode_layer(MultiPolygon(), {key: value for key, value in properties.items() if key != missing}, "x")
    with pytest.raises(FloodInputError, match="non-operational"):
        flood_inputs.encode_layer(MultiPolygon(), {**properties, "official_warning": True}, "x")
    with pytest.raises(FloodInputError, match="not a floodguard.flood_input_layer.v1 layer"):
        flood_inputs.decode_layer(b'{"type":"FeatureCollection","features":[]}\n')
    two = json.loads(data)
    two["features"] = two["features"] * 2
    with pytest.raises(FloodInputError, match="holds one feature"):
        flood_inputs.decode_layer(json.dumps(two).encode("ascii"))


def test_the_open_points_are_listed_and_none_is_decided_in_silence() -> None:
    identifiers = [point["id"] for point in flood_inputs.OPEN_POINTS]
    assert identifiers == [f"E1-OP{number}" for number in range(1, 10)]
    for point in flood_inputs.OPEN_POINTS:
        assert set(point) == {"id", "point", "signed_files_say", "what_this_module_does", "for_the_owners"}
        assert all(isinstance(value, str) and value.strip() for value in point.values())


def test_the_module_computes_no_score() -> None:
    """Task E1 computes flood-input layers only: no scorer, no class and no ensemble is imported or called."""

    for name in ("src/floodguard/flood_inputs.py", "src/floodguard/rights.py", "scripts/build_flood_inputs.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+floodguard\.(?:scoring|confidence|sensitivity)\b", source, re.MULTILINE), name
        assert not re.search(r"\b(?:score_subdistricts|action_class\s*=|fpps_0_100)\b", source), name
        for called in ("flood_likelihood(", "exposure(", "access_gap(", "road_criticality(", "vulnerability_context("):
            assert f"normalisation.{called}" not in source, name
        assert "C:/Users" not in source and "C:\\Users" not in source, "no machine path in the code"


# ---------------------------------------------------------------------------
# A written input read back, and the builder script on an invented repository
# ---------------------------------------------------------------------------


def write_input(folder: Path, built: flood_inputs.FloodInput, both: list[flood_inputs.Frame], rules) -> dict:
    """Write the extents of an input and its record the way the builder does."""

    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for level in LEVELS:
        for frame in both:
            name = f"flood_extent__{level}__{frame.name}.geojson"
            properties = flood_inputs.layer_properties(built, level=level, frame=frame, what="flood_extent",
                                                       change=flood_inputs.level_sentence(level, rules.one_pixel_m))
            data = flood_inputs.encode_layer(built.extent(level, frame.name), properties, name)
            (folder / name).write_bytes(data)
            entries.append(flood_inputs.file_entry(name, data, what="flood_extent", level=level, frame=frame.name))
    (folder / "LICENSE_NOTICE.txt").write_bytes(b"an invented notice\n")
    entries.append(flood_inputs.file_entry("LICENSE_NOTICE.txt", b"an invented notice\n", what="licence_notice"))
    record = {**built.record, "files": entries}
    (folder / flood_inputs.INPUT_RECORD_NAME).write_text(json.dumps(record), encoding="ascii")
    return record


def test_a_written_input_is_read_back_only_as_the_bytes_its_record_names(tmp_path: Path, rules, grant) -> None:
    both = frames()
    built = flood_inputs.build_flood_input(lonlat(MultiPolygon([metres(100, 100, 500, 300), metres(2100, 400, 2300, 600)])), both,
                                           spec=spec(), rules=rules, grant=grant)
    written = write_input(tmp_path / "input", built, both, rules)
    record, extents = flood_inputs.read_written_input(tmp_path / "input")
    assert record == written and set(extents) == set(LEVELS)
    for level in LEVELS:
        for frame in both:
            assert extents[level][frame.name].equals_exact(built.extent(level, frame.name), 0.0)

    layer = tmp_path / "input" / f"flood_extent__{PLUS}__{REPORTING_FRAME}.geojson"
    original = layer.read_bytes()
    layer.write_bytes(original.replace(b"season_window", b"event_aligned"))
    with pytest.raises(FloodInputError, match="is not the file the record names"):
        flood_inputs.read_written_input(tmp_path / "input")
    layer.unlink()
    with pytest.raises(FloodInputError, match="is not in the folder"):
        flood_inputs.read_written_input(tmp_path / "input")
    layer.write_bytes(original)

    record_path = tmp_path / "input" / flood_inputs.INPUT_RECORD_NAME
    swapped = json.loads(record_path.read_text(encoding="ascii"))
    plus = [entry for entry in swapped["files"] if entry.get("level") == PLUS]
    plus[0]["frame"], plus[1]["frame"] = plus[1]["frame"], plus[0]["frame"]
    record_path.write_text(json.dumps(swapped), encoding="ascii")
    with pytest.raises(FloodInputError, match="does not say the level, frame and input"):
        flood_inputs.read_written_input(tmp_path / "input")
    swapped["files"] = [entry for entry in written["files"] if entry.get("level") != MINUS]
    record_path.write_text(json.dumps(swapped), encoding="ascii")
    with pytest.raises(FloodInputError, match="each of the three levels"):
        flood_inputs.read_written_input(tmp_path / "input")
    record_path.write_text(json.dumps({"schema_version": "other"}), encoding="ascii")
    with pytest.raises(FloodInputError, match="is not a floodguard.flood_input.v1 record"):
        flood_inputs.read_written_input(tmp_path / "input")
    with pytest.raises(FloodInputError, match="no input_record.json"):
        flood_inputs.read_written_input(tmp_path / "nothing")


def load_builder():
    spec_ = importlib.util.spec_from_file_location("build_flood_inputs", ROOT / "scripts" / "build_flood_inputs.py")
    assert spec_ is not None and spec_.loader is not None
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    return module


def invented_repository(tmp_path: Path, rules) -> dict:
    """An invented repository and external data root that hold every input the builder reads."""

    geopandas = pytest.importorskip("geopandas")
    case = product_case(tmp_path)
    root, external = tmp_path / "repository", case["external"]
    notice = root / "docs" / "proposal_execution" / "rights_basis_4009_v1_NOTICE.txt"
    notice.write_bytes(b"An invented licence notice.\n")

    def geojson(path: Path, geometry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": shapely.geometry.mapping(lonlat(geometry))}]}), encoding="utf-8")

    corridor = root / "outputs" / "planning_v1" / "corridor_of_record.geojson"
    geojson(corridor, metres(-500, 0, 2500, 1000))
    geojson(root / "resources" / "aoi" / "aoi-01_mae_sai_core.geojson", metres(0, 0, 600, 400))
    boundaries = external / "boundaries.gpkg"
    units = geopandas.GeoDataFrame(
        {"adm3_pcode": ["U1", "U2", "U3"], "valid_on": ["2022-01-22"] * 3},
        geometry=[lonlat(metres(0, 0, 1000, 1000)), lonlat(metres(1000, 0, 2000, 1000)), lonlat(metres(0, 5000, 1000, 6000))], crs=WGS84_CRS)
    units.to_file(boundaries, layer="tha_admin3", driver="GPKG")
    cells = np.full((120, 240), 40, dtype="uint8")
    cells[80:100, 20:30] = 80                       # x 0..100 m, y 0..200 m of the reporting frame
    cover = external / "ESA_WorldCover_10m_2021_v200_invented_Map.tif"
    with rasterio.open(cover, "w", driver="GTiff", height=120, width=240, count=1, dtype="uint8", crs=ANALYSIS_CRS, nodata=0,
                       transform=from_origin(EAST - 200, NORTH + 1000, 10, 10)) as target:
        target.write(cells, 1)
        target.update_tags(product_version="V2.0.0", time_start="2021-01-01T00:00:00Z", time_end="2021-12-31T23:59:59Z",
                           license="CC-BY 4.0", copyright="An invented land-cover project 2021")
    invented_rules = dataclasses.replace(
        rules, reporting_units=("U1", "U2"), boundary_file_sha256=hashlib.sha256(boundaries.read_bytes()).hexdigest(),
        routing_geometry_file={"path": "outputs/planning_v1/corridor_of_record.geojson", "sha256": hashlib.sha256(corridor.read_bytes()).hexdigest()})
    return {"root": root, "external": external, "boundaries": boundaries, "cover": cover, "rules": invented_rules,
            "processed": external / "proposal_execution" / "planning_v1", "receipt": root / "outputs" / "planning_v1" / "e1_flood_inputs_mae_sai.json",
            "register": root / "outputs" / "planning_v1" / "run_register"}


def test_the_builder_writes_the_layers_reports_the_run_and_verifies_it(tmp_path: Path, rules, monkeypatch) -> None:
    """One run on an invented repository: layers, records, receipt, register entry, verify, and a second run."""

    builder = load_builder()
    made = invented_repository(tmp_path, rules)
    monkeypatch.setattr(builder.flood_inputs, "load_rules", lambda *_paths: made["rules"])
    arguments = ("mae_sai", made["external"], made["boundaries"], made["cover"])
    places = {"processed_root": made["processed"], "receipt_path": made["receipt"], "root": made["root"]}

    summary = builder.run(*arguments, **places, register_dir=made["register"], development_reads=["An invented earlier read."])
    receipt = json.loads(made["receipt"].read_text(encoding="ascii"))
    assert summary["receipt"] == "outputs/planning_v1/e1_flood_inputs_mae_sai.json" and summary["files_written"] == 21
    assert summary["receipt_sha256"] == hashlib.sha256(made["receipt"].read_bytes()).hexdigest()
    assert json.loads((made["register"] / made["receipt"].name).read_text(encoding="ascii")) == {
        "path": summary["receipt"], "sha256": summary["receipt_sha256"]}
    assert receipt["run_kind"] == "first_run" and receipt["schema_version"] == "floodguard.flood_inputs_run_receipt.v1"
    assert receipt["protocol_sha256"] == flood_inputs.protocol_hashes(rules)
    assert receipt["development_reads"]["reads"] == ["An invented earlier read."]
    assert receipt["confidence_class"] == "low" and receipt["official_warning"] is False and receipt["assumptions"]
    assert receipt["inputs"]["tambon_boundaries"]["path"] == "<external_data_workspace>/boundaries.gpkg"
    assert str(tmp_path) not in made["receipt"].read_text(encoding="ascii"), "no machine path in the receipt"

    # Every file the receipt binds is on disk with those bytes, and each input reads back from its folder.
    for path, digest in builder.output_hashes(receipt["outputs"]).items():
        target = made["processed"] / path.split("/proposal_execution/planning_v1/", 1)[1]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, path
    for case, folder in (("SE1", "se1_mae_sai"), ("O2", "o2_mae_sai")):
        record, extents = flood_inputs.read_written_input(made["processed"] / folder / "e1_flood_input")
        assert record["case_id"] == case and record["generated_at_utc"] == receipt["generated_at_utc"]
        assert (made["processed"] / folder / "e1_flood_input" / "LICENSE_NOTICE.txt").read_bytes() == b"An invented licence notice.\n"
        summary_area = receipt["flood_inputs"][case]["levels"]["by_level"][AS_PROVIDED][REPORTING_FRAME]["area_m2"]
        assert area(extents[AS_PROVIDED][REPORTING_FRAME]) == pytest.approx(summary_area, abs=0.01)
    water, properties = flood_inputs.decode_layer((made["processed"] / "mae_sai_frame" / "e1_flood_input" / "permanent_water__reporting_frame.geojson").read_bytes())
    assert area(water) == pytest.approx(100 * 200, abs=0.01) and properties["what"] == "permanent_water"
    assert properties["credit"] == "An invented land-cover project 2021" and "CC BY-SA" not in json.dumps(properties)
    se1 = receipt["flood_inputs"]["SE1"]["levels"]["by_level"][AS_PROVIDED][REPORTING_FRAME]
    # The accumulated block (x 100..500, y 100..300) does not meet the water block (x 0..100, y 0..200).
    assert se1["area_on_permanent_water_km2"] == 0 and se1["area_outside_permanent_water_km2"] == se1["area_km2"]

    # The acceptance check clips both layers to the invented AOI-01 (x 0..600 m, y 0..400 m).
    acceptance = receipt["acceptance"]
    assert acceptance["layers"]["SE1"]["clip_km2_epsg32647"] == pytest.approx(0.08, abs=1e-5)
    assert acceptance["layers"]["O2"]["clip_km2_epsg32647"] == pytest.approx(0.02, abs=1e-5)
    assert acceptance["reproduced"] is False and acceptance["expected_km2"] == 15.34

    # The corridor reaches 500 m beyond the units on both sides; the footprint covers all of it here.
    check = receipt["footprint_check"]
    assert check["routing_context_that_can_hold_roads"]["tha_admin3_units_meeting_the_routing_context"] == 2
    assert check["routing_context_that_can_hold_roads"]["share_of_routing_context"] == pytest.approx(2 / 3, abs=1e-6)
    assert check["by_case"]["SE1"]["routing_context_that_can_hold_roads_outside_the_footprint_km2"] == 0

    assert builder.verify(*arguments, **places) == {
        "verified": True, "files_compared": 21, "differing": [], "missing_on_disk": [], "bound_but_not_recomputed": []}
    layer = made["processed"] / "o2_mae_sai" / "e1_flood_input" / "flood_extent__minus__routing_context.geojson"
    original = layer.read_bytes()
    layer.write_bytes(original + b" ")
    changed = builder.verify(*arguments, **places)
    assert changed["verified"] is False and changed["differing"] == ["o2_mae_sai/e1_flood_input/flood_extent__minus__routing_context.geojson (on disk)"]
    layer.unlink()
    assert builder.verify(*arguments, **places)["missing_on_disk"] == ["o2_mae_sai/e1_flood_input/flood_extent__minus__routing_context.geojson"]
    layer.write_bytes(original)

    # Every run is reported: a second run is refused unless it says why, and its receipt names the first.
    with pytest.raises(FileExistsError, match="--replace --reason"):
        builder.run(*arguments, **places, register_dir=made["register"])
    builder.run(*arguments, **places, register_dir=made["register"], replace_reason="An invented reason.")
    second = json.loads(made["receipt"].read_text(encoding="ascii"))
    assert second["run_kind"] == "superseding_run"
    assert second["supersedes"]["receipt_sha256"] == summary["receipt_sha256"] and second["supersedes"]["reason"] == "An invented reason."
    assert second["supersedes"]["layers_same"] is True and second["supersedes"]["layers_that_differ"] == []
    first_entry = {"generated_at_utc": receipt["generated_at_utc"], "receipt_sha256": summary["receipt_sha256"],
                   "superseded_because": "An invented reason.", "layers_same_as_the_run_that_replaced_it": True}
    assert second["run_history"] == [first_entry] and "run_history" not in receipt
    second_sha256 = hashlib.sha256(made["receipt"].read_bytes()).hexdigest()
    builder.run(*arguments, **places, register_dir=made["register"], replace_reason="Another invented reason.")
    third = json.loads(made["receipt"].read_text(encoding="ascii"))
    assert third["supersedes"]["receipt_sha256"] == second_sha256
    assert third["run_history"] == [first_entry, {"generated_at_utc": second["generated_at_utc"], "receipt_sha256": second_sha256,
                                                  "superseded_because": "Another invented reason.",
                                                  "layers_same_as_the_run_that_replaced_it": True}]
    # A receipt written before run_history existed names only the run it superseded: that run is kept too.
    older = {"supersedes": {"generated_at_utc": "t0", "receipt_sha256": "a", "reason": "r0", "layers_same": True}}
    newer = {"generated_at_utc": "t1", "receipt_sha256": "b", "reason": "r1", "layers_same": False}
    assert [entry["receipt_sha256"] for entry in builder.earlier_runs(older, newer)] == ["a", "b"]
    assert json.loads((made["register"] / made["receipt"].name).read_text(encoding="ascii"))["sha256"] == hashlib.sha256(made["receipt"].read_bytes()).hexdigest()


def test_the_builder_refuses_inputs_the_signed_files_do_not_name(tmp_path: Path, rules, monkeypatch) -> None:
    builder = load_builder()
    made = invented_repository(tmp_path, rules)
    places = {"processed_root": made["processed"], "receipt_path": made["receipt"], "root": made["root"], "register_dir": made["register"]}
    with pytest.raises(FileNotFoundError, match="--replace needs an existing receipt"):
        builder.run("mae_sai", made["external"], made["boundaries"], made["cover"], **places, replace_reason="x")

    monkeypatch.setattr(builder.flood_inputs, "load_rules", lambda *_paths: dataclasses.replace(made["rules"], boundary_file_sha256="0" * 64))
    with pytest.raises(ValueError, match="boundary file is not the one protocol v1b names"):
        builder.run("mae_sai", made["external"], made["boundaries"], made["cover"], **places)
    other_corridor = {**made["rules"].routing_geometry_file, "sha256": "0" * 64}
    monkeypatch.setattr(builder.flood_inputs, "load_rules", lambda *_paths: dataclasses.replace(made["rules"], routing_geometry_file=other_corridor))
    with pytest.raises(ValueError, match="corridor file is not the one protocol v1b names"):
        builder.run("mae_sai", made["external"], made["boundaries"], made["cover"], **places)
    monkeypatch.setattr(builder.flood_inputs, "load_rules", lambda *_paths: dataclasses.replace(made["rules"], reporting_units=("U1", "U9")))
    with pytest.raises(ValueError, match="each unit of the frame exactly once"):
        builder.run("mae_sai", made["external"], made["boundaries"], made["cover"], **places)

    monkeypatch.setattr(builder.flood_inputs, "load_rules", lambda *_paths: made["rules"])
    renamed = made["cover"].with_name("land_cover_2020.tif")
    renamed.write_bytes(made["cover"].read_bytes())
    with pytest.raises(ValueError, match="is not named as that product"):
        builder.run("mae_sai", made["external"], made["boundaries"], renamed, **places)
    with rasterio.open(made["cover"], "r+") as target:
        target.update_tags(product_version="V1.0.0")
    with pytest.raises(ValueError, match="the raster says otherwise"):
        builder.run("mae_sai", made["external"], made["boundaries"], made["cover"], **places)
    assert not made["receipt"].exists() and not made["processed"].exists(), "a refused run writes nothing"


def test_the_builder_names_files_without_a_machine_path_and_needs_its_arguments(tmp_path: Path, capsys) -> None:
    builder = load_builder()
    external = tmp_path / "external"
    (external / "a").mkdir(parents=True)
    (external / "a" / "b.tif").write_bytes(b"x")
    (tmp_path / "elsewhere.bin").write_bytes(b"y")
    assert builder.path_label(ROOT / "docs" / "proposal_execution" / "RECEIPTS.jsonl", ROOT, external) == "docs/proposal_execution/RECEIPTS.jsonl"
    assert builder.path_label(external / "a" / "b.tif", ROOT, external) == "<external_data_workspace>/a/b.tif"
    assert builder.path_label(tmp_path / "elsewhere.bin", ROOT, external) == "elsewhere.bin"
    assert builder.path_label(tmp_path / "elsewhere.bin", ROOT, None) == "elsewhere.bin"
    assert builder.receipt_path_for("mae_sai") == ROOT / "outputs" / "planning_v1" / "e1_flood_inputs_mae_sai.json"
    encoded = builder.encode({"a": "\u00e9"})
    assert encoded == b'{\n  "a": "\\u00e9"\n}\n'

    monkey_environment = {key: value for key, value in os.environ.items() if key != builder.EXTERNAL_DATA_VARIABLE}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "environ", monkey_environment)
        with pytest.raises(SystemExit) as stopped:
            builder.main(["--frame", "mae_sai"])
        assert stopped.value.code == 2 and "FLOODGUARD_EXTERNAL_DATA" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        builder.main(["--frame", "mae_sai", "--external-data", str(external), "--replace"])
    assert "--replace and --reason go together" in capsys.readouterr().err

    water = flood_inputs.PermanentWater(REPORTING_FRAME, MultiPolygon(), {"source": "x", "file": "x.tif", "licence": "", "attribution": "y"})
    with pytest.raises(ValueError, match="lacks its licence or credit"):
        builder.other_inputs(water)


# ---------------------------------------------------------------------------
# The committed run: its receipt and its place in the run register
# ---------------------------------------------------------------------------


def committed_receipt() -> dict:
    if not RECEIPT.exists():
        pytest.skip("the E1 run has not been made on this checkout")
    return json.loads(RECEIPT.read_text(encoding="ascii"))


def test_the_committed_run_is_registered_and_names_both_protocols() -> None:
    receipt = committed_receipt()
    entry = json.loads(REGISTER.read_text(encoding="ascii"))
    assert entry == {"path": "outputs/planning_v1/e1_flood_inputs_mae_sai.json", "sha256": hashlib.sha256(RECEIPT.read_bytes()).hexdigest()}
    assert receipt["protocol_sha256"] == {f"planning_protocol_{name}": hashlib.sha256((DOCS / f"planning_protocol_{name}.json").read_bytes()).hexdigest()
                                          for name in ("v1a", "v1b")}
    assert receipt["status"] == "run_receipt" and receipt["official_warning"] is False
    assert receipt["confidence_class"] == "low" and receipt["operational_status"] == "non_operational"
    assert receipt["timestamps"]["run_started_at_utc"] == receipt["generated_at_utc"] <= receipt["timestamps"]["run_finished_at_utc"]


def test_the_committed_run_used_the_inputs_the_signed_files_name(rules) -> None:
    receipt = committed_receipt()
    record = json.loads((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_text(encoding="utf-8"))
    inputs = receipt["inputs"]
    assert inputs["product_4009_archive"]["sha256"] == record["archive"]["sha256"]
    assert inputs["product_4009_archive"]["bytes"] == record["archive"]["bytes"]
    assert inputs["rights_record_4009"]["sha256"] == hashlib.sha256((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_bytes()).hexdigest()
    assert inputs["rights_record_4009"]["record_status"] == "confirmed"
    assert inputs["tambon_boundaries"]["sha256"] == rules.boundary_file_sha256
    assert inputs["routing_geometry"] == {"path": rules.routing_geometry_file["path"], "sha256": rules.routing_geometry_file["sha256"],
                                         "bytes": (ROOT / rules.routing_geometry_file["path"]).stat().st_size}
    assert receipt["parameters"]["one_pixel_m"] == rules.one_pixel_m == 20.0
    assert receipt["parameters"]["unit_ids"] == list(rules.reporting_units)
    assert receipt["parameters"]["permanent_water"]["class"] == 80
    assert receipt["permanent_water"]["source"] == "ESA WorldCover 2021 v200" and receipt["permanent_water"]["product_version"] == "V2.0.0"
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", RECEIPT.read_text(encoding="ascii")), "no machine path in the receipt"


def test_the_committed_run_reports_each_input_as_the_protocol_names_it() -> None:
    receipt = committed_receipt()
    se1, o2 = receipt["flood_inputs"]["SE1"], receipt["flood_inputs"]["O2"]
    assert (se1["lane"], se1["tier"], se1["temporal_relation"], se1["acquisition_date"]) == ("SCN-ENV", "T1", "season_window", None)
    assert (o2["lane"], o2["tier"], o2["temporal_relation"], o2["acquisition_date"]) == ("OBS", "T3", "event_aligned", "2024-10-22")
    assert se1["source"]["layer"] == ACCUMULATED and o2["source"]["layer"] == LAYER_22_OCT
    for record in (se1, o2):
        assert record["used_as_provided"] is True and record["field_validation"] == 0
        assert record["confidence_class"] == "low" and record["assumptions"] and record["source_timestamp"]
        assert record["rights"]["record_status"] == "confirmed" and record["rights"]["licence"]["name"] == "CC BY-SA 4.0"
        assert record["repair"]["method"] == "make_valid" and record["repair"]["parts_repaired"] >= 0
        assert record["permanent_water"]["class"] == 80
        by_level = record["levels"]["by_level"]
        for frame in (REPORTING_FRAME, ROUTING_CONTEXT):
            assert by_level[MINUS][frame]["area_km2"] <= by_level[AS_PROVIDED][frame]["area_km2"] <= by_level[PLUS][frame]["area_km2"]
        for level in LEVELS:
            assert by_level[level][REPORTING_FRAME]["area_km2"] <= by_level[level][ROUTING_CONTEXT]["area_km2"]
            summary = by_level[level][REPORTING_FRAME]
            assert summary["area_on_permanent_water_km2"] + summary["area_outside_permanent_water_km2"] == pytest.approx(summary["area_km2"], abs=2e-6)
    # The record names the accumulated layer only: the envelope may be published, the 22 October layer is local.
    assert receipt["rights"]["output_rights_level"] == {"SE1": "public", "O2": "local"}
    assert receipt["rights"]["written_under_apps_web_public"] is False
    assert receipt["licence"]["name"] == "CC BY-SA 4.0" and receipt["licence"]["credit"] == CREDIT
    assert CREDIT in receipt["licence"]["change_notice"]
    assert [item["id"] for item in receipt["licence"]["other_inputs"]] == ["esa-worldcover", "cod-ab", "osm"]


def test_the_committed_run_reproduces_the_acceptance_figure_of_plan_row_e1() -> None:
    acceptance = committed_receipt()["acceptance"]
    assert acceptance["expected_km2"] == 15.34 and acceptance["reproduced"] is True
    assert round(acceptance["layers"]["SE1"]["clip_km2_epsg32647"], 2) == 15.34
    assert acceptance["aoi_01"]["sha256"] == hashlib.sha256((ROOT / "resources" / "aoi" / "aoi-01_mae_sai_core.geojson").read_bytes()).hexdigest()
    assert acceptance["layers"]["SE1"]["repair"]["source_parts_invalid"] >= acceptance["layers"]["SE1"]["repair"]["parts_repaired"]


def test_the_committed_run_binds_every_layer_and_holds_no_value_for_a_single_tambon() -> None:
    receipt = committed_receipt()
    outputs = receipt["outputs"]
    assert set(outputs) == {"frame", "SE1", "O2"}
    assert [entry["what"] for entry in outputs["frame"]["files"]] == ["permanent_water"]
    notice = hashlib.sha256((ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1_NOTICE.txt").read_bytes()).hexdigest()
    for case in ("SE1", "O2"):
        files = outputs[case]["files"]
        extents = {(entry["level"], entry["frame"]) for entry in files if entry["what"] == "flood_extent"}
        assert extents == {(level, frame) for level in LEVELS for frame in (REPORTING_FRAME, ROUTING_CONTEXT)}
        assert sorted(entry["frame"] for entry in files if entry["what"] == "product_footprint") == [REPORTING_FRAME, ROUTING_CONTEXT]
        assert [entry["sha256"] for entry in files if entry["what"] == "licence_notice"] == [notice]
        assert sum(entry["what"] == "input_record" for entry in files) == 1
        for entry in files:
            assert entry["path"].startswith("<external_data_workspace>/proposal_execution/planning_v1/") and len(entry["sha256"]) == 64

    def keys(value) -> list[str]:
        if isinstance(value, dict):
            return [*value, *(key for child in value.values() for key in keys(child))]
        if isinstance(value, list):
            return [key for child in value for key in keys(child)]
        return []

    # Tambon codes appear only in lists of units: nothing in the receipt is keyed by a tambon.
    assert not [key for key in keys(receipt) if re.fullmatch(r"TH\d{6}", key)]
    assert not [key for key in keys(receipt) if re.search(r"by_tambon|by_unit|per_tambon|fpps|action_class", key, re.IGNORECASE)]
    assert "No FPPS" in receipt["computes"] and "FPPS" in receipt["not_computed"]
    assert [point["id"] for point in receipt["open_points"]] == [point["id"] for point in flood_inputs.OPEN_POINTS]
