"""Tests of the consequence points of the Nan case: placing a reported cut along a route line by milestones or by
tambon, on invented geometries; the routing point of a hospital; the gauge peaks; and the committed records."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.wording_lint import find_violations, json_strings, load_rules, python_strings  # noqa: E402

SCRIPT = ROOT / "scripts" / "nan_case_consequence_points.py"
POINTS = ROOT / "outputs" / "nan_case" / "consequence_points_v1.json"
NEWS = ROOT / "outputs" / "nan_case" / "news_records_v1.json"
WORDING_RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")


def load_script() -> Any:
    """Load the script as a module, without running it."""

    spec = importlib.util.spec_from_file_location("nan_case_consequence_points", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


cp = load_script()


def same(x: Any, y: Any, z: Any = None) -> Any:
    """An identity 'projection': the invented geometries are already in metres."""

    return (x, y) if z is None else (x, y, z)


def tags(**values: str) -> str:
    """An ``other_tags`` field as GDAL's OSM driver writes it."""

    return ",".join(f'"{key.replace("_", ":")}"=>"{value}"' for key, value in values.items())


# ---------------------------------------------------------------------------------------------------------------------
# Tags and references
# ---------------------------------------------------------------------------------------------------------------------

def test_other_tags_are_read_with_escaped_quotes() -> None:
    text = '"ref"=>"นน.4020","name:en"=>"The \\"Old\\" Road","distance"=>"13"'
    assert cp.parse_other_tags(text) == {"ref": "นน.4020", "name:en": 'The "Old" Road', "distance": "13"}
    assert cp.parse_other_tags(None) == {}
    assert cp.parse_other_tags("") == {}


def test_reference_spellings_are_made_one() -> None:
    assert cp.normalise_ref("นน.4020") == ["นน.4020"]
    assert cp.normalise_ref("นน. 4020") == ["นน.4020"]
    assert cp.normalise_ref("นน 4020") == ["นน.4020"]
    assert cp.normalise_ref("1243;AH13") == ["1243", "AH13"]
    assert cp.normalise_ref("นน.ถ1-0009") == ["นน.ถ1-0009"]
    assert cp.normalise_ref(None) == []


def test_a_rural_road_matches_its_prefix_and_its_bare_number_only_in_the_province() -> None:
    route = cp.Route("4020", "นน", "rural")
    assert cp.ref_matches("นน.4020", route, touches_province=False) == "prefixed"
    assert cp.ref_matches("นน 4020", route, touches_province=False) == "prefixed"
    assert cp.ref_matches("4020", route, touches_province=True) == "bare"
    assert cp.ref_matches("4020", route, touches_province=False) is None
    assert cp.ref_matches("พร.4020", route, touches_province=True) is None
    assert cp.ref_matches("นน.40201", route, touches_province=True) is None


def test_a_national_highway_matches_its_number_and_no_longer_number() -> None:
    route = cp.Route("1243", None, "national")
    assert cp.ref_matches("1243", route, touches_province=False) == "national"
    assert cp.ref_matches("ทล.1243", route, touches_province=False) == "national"
    assert cp.ref_matches("11243", route, touches_province=True) is None
    assert cp.ref_matches("นน.1243", route, touches_province=True) is None


def test_milestone_distances_are_read_as_km() -> None:
    assert cp.parse_km("13") == 13.0
    assert cp.parse_km("120.2") == pytest.approx(120.2)
    assert cp.parse_km("13 km") == 13.0
    assert cp.parse_km("59+100") == pytest.approx(59.1)
    assert cp.parse_km("near the bridge") is None
    assert cp.parse_km(None) is None


# ---------------------------------------------------------------------------------------------------------------------
# Placement along a line
# ---------------------------------------------------------------------------------------------------------------------

def test_ways_merge_into_one_chain_longest_first() -> None:
    chains = cp.merged_chains([LineString([(0, 0), (1000, 0)]), LineString([(1000, 0), (3000, 0)]),
                               LineString([(5000, 5000), (5100, 5000)])])
    assert [round(chain.length) for chain in chains] == [3000, 100]
    assert cp.merged_chains([LineString([(0, 0), (10, 0)])])[0].length == 10
    assert cp.merged_chains([]) == []


def test_km_are_interpolated_between_two_milestones_whose_spacing_is_not_one_km_per_km() -> None:
    line = LineString([(0, 0), (30000, 0)])
    milestones = [("m0", 0.0, Point(0, 5)), ("m13", 13.0, Point(10734, -6)), ("m17", 17.0, Point(14754, 3))]
    stations, rejected = cp.stations_on_line(line, milestones)
    assert rejected == [] and [st.km for st in stations] == [0.0, 13.0, 17.0]
    s, how = cp.km_to_s(10.5, stations)
    assert how == "interpolated"
    assert s == pytest.approx(10.5 / 13.0 * 10734.0)
    s, how = cp.km_to_s(15.0, stations)
    assert how == "interpolated" and s == pytest.approx(10734 + 0.5 * 4020)
    ratios = cp.segment_ratios(stations)
    assert ratios[0]["osm_m_per_official_m"] == pytest.approx(0.8257, abs=1e-4)


def test_beyond_the_last_milestone_the_line_is_read_at_one_metre_per_metre() -> None:
    line = LineString([(0, 0), (40000, 0)])
    stations, _ = cp.stations_on_line(line, [("a", 24.0, Point(21755, 0)), ("b", 28.0, Point(25758, 0))])
    s_from, how_from = cp.km_to_s(31.69, stations)
    s_to, how_to = cp.km_to_s(32.2, stations)
    assert how_from == how_to == "extrapolated_after_last"
    assert s_from == pytest.approx(25758 + 3690) and s_to == pytest.approx(25758 + 4200)
    s_before, how_before = cp.km_to_s(23.0, stations)
    assert how_before == "extrapolated_before_first" and s_before == pytest.approx(20755)


def test_a_line_drawn_against_the_km_is_turned_round() -> None:
    line = LineString([(20000, 0), (0, 0)])                     # drawn from km 20 towards km 0
    stations, _ = cp.stations_on_line(line, [("m0", 0.0, Point(0, 2)), ("m10", 10.0, Point(10000, 2))])
    oriented, stations, flipped = cp.orient_by_stations(line, stations)
    assert flipped and oriented.coords[0] == (0.0, 0.0)
    s, _ = cp.km_to_s(12.0, stations)
    assert oriented.interpolate(s).x == pytest.approx(12000.0)


def test_a_milestone_far_from_the_line_is_not_used() -> None:
    line = LineString([(0, 0), (10000, 0)])
    stations, rejected = cp.stations_on_line(line, [("near", 1.0, Point(1000, 29)), ("far", 2.0, Point(2000, 31))])
    assert [st.osm_id for st in stations] == ["near"]
    assert rejected[0]["osm_id"] == "far" and rejected[0]["offset_m"] == 31.0


def test_milestones_out_of_order_along_the_line_are_refused() -> None:
    line = LineString([(0, 0), (30000, 0)])
    stations = [cp.Station("a", 0.0, 0.0, 0.0), cp.Station("b", 10.0, 10000.0, 0.0), cp.Station("c", 20.0, 9000.0, 0.0)]
    with pytest.raises(cp.PlacementError):
        cp.km_to_s(5.0, stations)
    with pytest.raises(cp.PlacementError):
        cp.check_monotonic([cp.Station("a", 3.0, 0.0, 0.0), cp.Station("b", 3.0, 500.0, 0.0)])
    with pytest.raises(cp.PlacementError):
        cp.km_to_s(1.0, [])
    del line


def test_a_single_km_zero_milestone_at_the_far_end_turns_the_line_and_reads_at_unit_scale() -> None:
    line = LineString([(0, 0), (8000, 0)])
    stations, _ = cp.stations_on_line(line, [("zero", 0.0, Point(7990, 0))])
    oriented, stations, flipped = cp.orient_by_stations(line, stations)
    assert flipped and stations[0].s_m == pytest.approx(10.0)
    s, how = cp.km_to_s(7.0, stations)
    assert how == "unit_scale_from_single" and s == pytest.approx(7010.0)
    # A single milestone that is not km 0 does not fix the direction.
    other, kept, turned = cp.orient_by_stations(line, [cp.Station("x", 5.0, 4000.0, 0.0)])
    assert not turned and other.equals(line) and kept[0].km == 5.0


def test_the_unit_scale_check_reads_from_the_nearest_milestone() -> None:
    stations = [cp.Station("m0", 0.0, 20.0, 0.0), cp.Station("m13", 13.0, 10754.0, 0.0)]
    s, nearest = cp.km_to_s_unit_from_nearest(10.5, stations)
    assert nearest.osm_id == "m13" and s == pytest.approx(10754.0 - 2500.0)


def test_a_part_of_the_line_is_cut_out_and_clipped_to_it() -> None:
    line = LineString([(0, 0), (1000, 0), (1000, 1000)])
    part, clipped = cp.cut_part(line, 500.0, 1500.0)
    assert part.length == pytest.approx(1000.0) and part.coords[0] == (500.0, 0.0) and part.coords[-1] == (1000.0, 500.0)
    point, _ = cp.cut_part(line, 1200.0, 1200.0)
    assert point.geom_type == "Point" and (point.x, point.y) == (1000.0, 200.0)
    beyond, clipped = cp.cut_part(line, 1900.0, 2300.0)
    assert clipped == {"beyond_start_m": 0.0, "beyond_end_m": 300.0} and beyond.length == pytest.approx(100.0)


def test_the_part_inside_a_tambon_is_the_route_clipped_to_it() -> None:
    lines = [LineString([(0, 0), (10000, 0)]), LineString([(10000, 0), (10000, 5000)])]
    part = cp.part_inside(lines, box(8000, -100, 10500, 3000))
    assert part.length == pytest.approx(2000.0 + 3000.0)
    assert cp.part_inside(lines, box(0, 6000, 100, 7000)).is_empty


def test_lengths_are_counted_by_tambon() -> None:
    units = [{"adm3_pcode": "A", "adm3_name": "West", "geometry_m": box(0, -10, 600, 10)},
             {"adm3_pcode": "B", "adm3_name": "East", "geometry_m": box(600, -10, 2000, 10)}]
    rows = cp.lengths_by_unit(LineString([(100, 0), (1000, 0)]), units)
    assert rows == [{"adm3_pcode": "A", "adm3_name": "West", "length_m": 500.0},
                    {"adm3_pcode": "B", "adm3_name": "East", "length_m": 400.0}]
    assert cp.lengths_by_unit(Point(700, 0), units)[0]["adm3_pcode"] == "B"


def test_the_gap_along_the_line_to_a_tambon() -> None:
    line = LineString([(0, 0), (10000, 0)])
    assert cp.along_line_gap(line, 5000.0, box(4000, -10, 6000, 10)) == 0.0
    assert cp.along_line_gap(line, 1000.0, box(4000, -10, 6000, 10)) == pytest.approx(3000.0)
    assert cp.along_line_gap(line, 1000.0, box(0, 100, 10, 200)) is None


# ---------------------------------------------------------------------------------------------------------------------
# A cut placed end to end on invented OSM rows
# ---------------------------------------------------------------------------------------------------------------------

def invented_osm() -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]], Polygon]:
    """A road Nan 4020 of 30 km (three ways, one tagged with the bare number), a Phrae 4020 elsewhere, highway 1243
    without milestones, and three tambons along the x axis (metres)."""

    lines = pd.DataFrame([
        {"osm_id": "1", "name": None, "highway": "tertiary", "other_tags": tags(ref="นน.4020"),
         "geometry": LineString([(0, 0), (10000, 0)])},
        {"osm_id": "2", "name": None, "highway": "tertiary", "other_tags": tags(ref="นน. 4020", bridge="yes"),
         "geometry": LineString([(10000, 0), (10050, 0)])},
        {"osm_id": "3", "name": None, "highway": "tertiary", "other_tags": tags(ref="4020"),
         "geometry": LineString([(10050, 0), (30000, 0)])},
        {"osm_id": "4", "name": None, "highway": "tertiary", "other_tags": tags(ref="พร.4020"),
         "geometry": LineString([(0, 90000), (5000, 90000)])},
        {"osm_id": "5", "name": None, "highway": "secondary", "other_tags": tags(ref="1243"),
         "geometry": LineString([(0, 2000), (30000, 2000)])},
        {"osm_id": "6", "name": None, "highway": "residential", "other_tags": None,
         "geometry": LineString([(0, 500), (100, 500)])},
    ])
    points = pd.DataFrame([
        {"osm_id": "m0", "highway": "milestone", "ref": "นน.4020", "other_tags": tags(distance="0"),
         "geometry": Point(0, 6)},
        {"osm_id": "m10", "highway": "milestone", "ref": "นน.4020", "other_tags": tags(distance="10"),
         "geometry": Point(9000, -4)},                    # the first 10 km are 1 km short on the map
        {"osm_id": "m20", "highway": "milestone", "ref": "นน.4020", "other_tags": tags(distance="20"),
         "geometry": Point(19000, 3)},
        {"osm_id": "x", "highway": "milestone", "ref": "พร.4020", "other_tags": tags(distance="3"),
         "geometry": Point(3000, 0)},
        {"osm_id": "bus", "highway": "bus_stop", "ref": None, "other_tags": None, "geometry": Point(5, 5)},
    ])
    units = [
        {"adm3_pcode": "T1", "adm3_name": "First", "adm3_name_th": "หนึ่ง", "adm2_name": "D", "geometry_m": box(-100, -5000, 8000, 5000)},
        {"adm3_pcode": "T2", "adm3_name": "Second", "adm3_name_th": "สอง", "adm2_name": "D", "geometry_m": box(8000, -5000, 21000, 5000)},
        {"adm3_pcode": "T3", "adm3_name": "Third", "adm3_name_th": "สาม", "adm2_name": "D", "geometry_m": box(21000, -5000, 31000, 5000)},
    ]
    province = box(-100, -5000, 31000, 5000)
    return lines, points, units, province


def test_a_cut_is_placed_by_milestones_on_the_route_with_its_reference() -> None:
    lines, points, units, province = invented_osm()
    cut = cp.Cut("c", "นน.4020 กม. 12+000 - 13+000", cp.Route("4020", "นน", "rural"), 12.0, 13.0, "T2", "สอง", True)
    entry = cp.place_cut(cut, lines, points, units, province, same, same)
    assert entry["status"] == "placed" and entry["method"] == "milestones"
    assert entry["route_ways"] == ["1", "2", "3"] and entry["route_ways_bare_number"] == ["3"]
    assert [m["osm_id"] for m in entry["milestones_used"]] == ["m0", "m10", "m20"]
    assert entry["chainage"]["how_from"] == entry["chainage"]["how_to"] == "interpolated"
    assert entry["chainage"]["s_from_m"] == pytest.approx(11000.0) and entry["chainage"]["s_to_m"] == pytest.approx(12000.0)
    assert entry["way_ids"] == ["3"]
    assert entry["inside_named_tambon"] is True and entry["share_inside_named_tambon"] == 1.0
    assert entry["placed"]["length_m"] == pytest.approx(1000.0)
    assert entry["placed"]["epsg32647"]["coordinates"][0] == [11000.0, 0.0]
    assert cp.placement_confidence(entry) == "medium"
    sentence = cp.certainty_sentence(entry)
    assert sentence.startswith("Placed by milestones, interpolated between the milestones of km 10 and km 20")
    assert "inside Second" in sentence


def test_a_cut_before_the_first_ten_km_lands_where_the_short_map_puts_it() -> None:
    lines, points, units, province = invented_osm()
    cut = cp.Cut("c", "นน.4020 กม. 8+500 - 9+500", cp.Route("4020", "นน", "rural"), 8.5, 9.5, "T1", "หนึ่ง", True)
    entry = cp.place_cut(cut, lines, points, units, province, same, same)
    # Interpolated between km 0 and km 10 (9 km apart on the map): 7.65 km to 8.55 km along the line, which leaves
    # the named tambon at 8 km; the unit-scale check from km 10 reads 7.5 to 8.5 km.
    assert entry["chainage"]["s_from_m"] == pytest.approx(7650.0) and entry["chainage"]["s_to_m"] == pytest.approx(8550.0)
    assert entry["inside_named_tambon"] is False
    assert entry["share_inside_named_tambon"] == pytest.approx(350.0 / 900.0, abs=1e-3)
    assert entry["check_unit_scale_from_nearest_milestone"]["s_from_m"] == pytest.approx(7500.0)
    assert cp.placement_confidence(entry) == "low"
    assert "which the list names" in cp.certainty_sentence(entry)


def test_a_route_without_milestones_is_placed_as_its_part_inside_the_named_tambon() -> None:
    lines, points, units, province = invented_osm()
    cut = cp.Cut("c", "ทล.1243 กม.59+100", cp.Route("1243", None, "national"), 59.1, 59.1, "T2", "สอง", True)
    entry = cp.place_cut(cut, lines, points, units, province, same, same)
    assert entry["status"] == "placed" and entry["method"] == "tambon_part"
    assert entry["placed"]["length_m"] == pytest.approx(13000.0)
    assert entry["way_ids"] == ["5"] and entry["milestones_used"] == []
    assert cp.placement_confidence(entry) == "low"
    assert "has no mapped milestone" in cp.certainty_sentence(entry)


def test_a_route_missing_from_osm_gets_no_position() -> None:
    lines, points, units, province = invented_osm()
    cut = cp.Cut("c", "นน.021 กม. 0+000 - 0+300", cp.Route("021", "นน", "rural"), 0.0, 0.3, "T1", "หนึ่ง", True)
    entry = cp.place_cut(cut, lines, points, units, province, same, same)
    assert entry["status"] == "route_not_found"
    assert entry["placed"] is None and entry["way_ids"] == [] and entry["placement_confidence"] is None
    assert entry["refs_on_ways_in_named_tambon"] == {"1243": 1, "นน.4020": 1}
    assert entry["certainty"].startswith("Not placed")


def test_a_route_that_misses_the_named_tambon_gets_no_position() -> None:
    lines, points, units, province = invented_osm()
    units = units + [{"adm3_pcode": "T9", "adm3_name": "Away", "adm3_name_th": "ไกล", "adm2_name": "D",
                      "geometry_m": box(0, 40000, 1000, 41000)}]
    cut = cp.Cut("c", "ทล.1243", cp.Route("1243", None, "national"), 1.0, 1.0, "T9", "ไกล", True)
    entry = cp.place_cut(cut, lines, points, units, province, same, same)
    assert entry["status"] == "route_misses_named_tambon" and entry["placed"] is None


# ---------------------------------------------------------------------------------------------------------------------
# Hospitals, gauges, firewall
# ---------------------------------------------------------------------------------------------------------------------

def test_the_routing_point_follows_the_se2_rule() -> None:
    site = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    node, role, _ = cp.routing_point(Point(3, 4), [])
    assert (node.x, node.y) == (3, 4) and role == "osm_facility_node"
    one, role, ids = cp.routing_point(site, [("e1", "main", Point(10, 5)), ("e2", "no", Point(0, 5)),
                                              ("e3", "yes", Point(20, 20))])
    assert (one.x, one.y) == (10, 5) and ids == ["e1"] and "entrance" in role
    two, role, ids = cp.routing_point(site, [("e1", "main", Point(10, 5)), ("e2", "yes", Point(0, 5))])
    assert site.contains(two) and ids == ["e1", "e2"] and role.startswith("derived_site_interior")


def test_the_gauge_summary_gives_the_peak_hours_and_the_runs_above_each_level() -> None:
    # The service leaves hours empty; a run above the bank goes on across them, and a reading below ends it.
    series = [("2025-07-23 20:00", 198.0), ("2025-07-23 21:00", 199.5), ("2025-07-23 22:00", 200.1),
              ("2025-07-23 23:00", None), ("2025-07-24 00:00", None), ("2025-07-24 01:00", 201.69),
              ("2025-07-24 02:00", 201.69), ("2025-07-24 03:00", 199.0), ("2025-07-25 10:00", 199.3)]
    summary = cp.gauge_summary(series, {"bank": 199.2, "high": 201.0}, gauge_zero_msl=192.2)
    assert summary["peak_msl"] == 201.69 and summary["peak_gauge_m"] == 9.49
    assert summary["peak_times_local"] == ["2025-07-24 01:00", "2025-07-24 02:00"] and summary["readings_at_peak"] == 2
    assert summary["readings_with_value"] == 7 and summary["readings_in_series"] == 9
    bank = summary["levels"]["bank"]
    assert bank["readings_above"] == 5 and bank["first_above_local"] == "2025-07-23 21:00"
    assert bank["runs_above_local"] == [["2025-07-23 21:00", "2025-07-24 02:00"], ["2025-07-25 10:00", "2025-07-25 10:00"]]
    assert bank["peak_minus_level_m"] == 2.49
    assert summary["levels"]["high"]["runs_above_local"] == [["2025-07-24 01:00", "2025-07-24 02:00"]]
    assert cp.gauge_summary([("2025-07-24 00:00", None)], {}, None)["peak_msl"] is None


def test_a_long_gap_ends_a_run_and_many_peak_readings_are_shortened() -> None:
    values = [("2025-07-24 01:00", 5.0), ("2025-07-24 09:00", 5.0)]       # eight hours apart
    assert cp.runs_above(values, 1.0) == [["2025-07-24 01:00", "2025-07-24 01:00"], ["2025-07-24 09:00", "2025-07-24 09:00"]]
    series = [(f"2025-07-25 05:{minute:02d}", 190.66) for minute in range(0, 60, 10)] + [("2025-07-25 06:00", 190.66)]
    summary = cp.gauge_summary(series, {}, None)
    assert summary["peak_times_local"] == ["2025-07-25 05:00", "2025-07-25 06:00"] and summary["readings_at_peak"] == 7


def test_paths_behind_the_firewall_are_refused() -> None:
    for name in ("x/nan_case_v1/jaxa_sealed/a.zip", "IMG_T2V_20250731035100_ORTHO.tif", "water_v2_chip_003_2m.tif",
                 "gfm_extent.tif", "held_chip_001_reference.json"):
        with pytest.raises(cp.BuildError):
            cp.refuse_firewalled(name)
    assert cp.refuse_firewalled("consequence/osm_extract_v1.gpkg").name == "osm_extract_v1.gpkg"


def test_the_ministry_entries_are_the_four_of_the_protocol() -> None:
    protocol = json.loads((ROOT / "docs" / "proposal_execution" / "nan_case_protocol_v1.json").read_text(encoding="utf-8"))
    text = protocol["tests"]["test_3b_reported_cuts"]["record"]
    assert [cut.in_protocol_list for cut in cp.CUTS] == [True] * 4
    for number, km in (("1243", "59+100"), ("4020", "31+690"), ("4020", "10+500"), ("021", "0+000")):
        assert number in text and km in text
    assert [(cut.km_from, cut.km_to) for cut in cp.CUTS] == [(59.1, 59.1), (31.69, 32.2), (10.5, 10.9), (0.0, 0.3)]
    assert all(not cut.in_protocol_list for cut in cp.SUPPLEMENTARY_CUTS)


# ---------------------------------------------------------------------------------------------------------------------
# The committed records
# ---------------------------------------------------------------------------------------------------------------------

ENVELOPE = ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions", "official_warning",
            "operational_status")


@pytest.fixture(scope="module")
def points_record() -> dict[str, Any]:
    if not POINTS.exists():
        pytest.skip("the record of positions has not been written")
    return json.loads(POINTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def news_record() -> dict[str, Any]:
    if not NEWS.exists():
        pytest.skip("the news record has not been written")
    return json.loads(NEWS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [POINTS, NEWS])
def test_the_records_carry_the_envelope_and_lf_line_ends(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} has not been written")
    raw = path.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    record = json.loads(raw.decode("utf-8"))
    for key in ENVELOPE:
        assert key in record
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert isinstance(record["assumptions"], list) and all(isinstance(item, str) for item in record["assumptions"])


def test_the_positions_record_holds_the_four_points_and_credits_osm(points_record: dict[str, Any]) -> None:
    cuts = points_record["reported_cuts"]
    assert [entry["id"] for entry in cuts] == [cut.id for cut in cp.CUTS]
    assert "OpenStreetMap contributors" in points_record["attribution"] and "ODbL" in points_record["attribution"]
    for entry in cuts:
        assert entry["certainty"]
        if entry["status"] == "placed":
            assert entry["way_ids"] and entry["placed"]["epsg32647"] and entry["placed"]["wgs84"]
            assert entry["method"] in ("milestones", "tambon_part")
        else:
            assert entry["placed"] is None and entry["way_ids"] == []
    assert set(points_record["summary"]["placed"]) | set(points_record["summary"]["not_placed"]) == {c.id for c in cp.CUTS}
    hospitals = {entry["id"]: entry for entry in points_record["hospitals"]}
    assert set(hospitals) == {"nan_hospital", "wiang_sa_hospital"}
    for entry in hospitals.values():
        if entry["status"] == "located":
            assert entry["osm"]["id"] and entry["routing_point"]["wgs84"]["type"] == "Point"


def test_the_news_records_say_where_and_when(news_record: dict[str, Any]) -> None:
    assert news_record["records"]
    for record in news_record["records"]:
        for key in ("source_url", "publisher", "published_local", "paraphrase", "time_said", "place_said"):
            assert record[key], (record["id"], key)
        assert record["source_url"].startswith("https://")
        if not record["published_local"].startswith(("2025-07", "2025-08")):
            assert "other_event" in record["id"]


def test_the_text_passes_the_shared_wording_lint() -> None:
    # The phrase the case prescribes ("agreement with a reference, not accuracy") is taken out first, as in the
    # tuning-reference tests; nothing else may match.
    items = [("script", text) for text in python_strings(SCRIPT.read_text(encoding="utf-8"))]
    for path in (POINTS, NEWS):
        if path.exists():
            items += [(f"{path.name} {where}", text)
                      for where, text in json_strings(json.loads(path.read_text(encoding="utf-8")))]
    findings = [finding.describe() for source, text in items
                for finding in find_violations(text.replace("not accuracy", ""), WORDING_RULES, source)]
    assert findings == []
