"""Tests for the population, evacuation-access and shelter-siting stage of the Mae Sai timeline bake.

Everything here runs on small synthetic fixtures: no external data and no baked revision is needed.
The stage produces a T1 planning scenario on a modelled flood, never an observation of who was cut off.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from floodguard.evacuation_access import NEVER_LOST, NO_BASELINE_ACCESS, cutoff_levels
from floodguard.flood_timeline import CHANNEL_CODE, HAND_STEP_M, IMPASSABLE_DEPTH_M, NEVER_CODE

SPEC = importlib.util.spec_from_file_location(
    "mae_sai_timeline_evacuation", Path(__file__).resolve().parents[1] / "scripts" / "mae_sai_timeline_evacuation.py"
)
evac = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evac)

PEAK_STAGE_M = 3.5


def identity(x, y):
    """Stand-in for the lon/lat to UTM transform: the fixtures are already in metres."""
    return x, y


def grid(width: int = 100, height: int = 100, res: float = 10.0) -> SimpleNamespace:
    """A north-up grid like the bake's ``Grid``: bounds are (west, south, east, north)."""
    return SimpleNamespace(crs="EPSG:32647", bounds=(0.0, 0.0, width * res, height * res), res=res, width=width, height=height,
                           shape=(height, width), transform=from_origin(0.0, height * res, res, res))


def polygons(rows: list[dict]) -> gpd.GeoDataFrame:
    columns = {"osm_id": None, "osm_way_id": None, "name": None, "amenity": None, "building": None, "other_tags": None}
    return gpd.GeoDataFrame([{**columns, **row} for row in rows], geometry="geometry")


def points(rows: list[dict]) -> gpd.GeoDataFrame:
    columns = {"osm_id": None, "name": None, "other_tags": None}
    return gpd.GeoDataFrame([{**columns, **row} for row in rows], geometry="geometry")


def facilities_file(tmp_path: Path, features: list[dict]) -> Path:
    path = tmp_path / "facilities.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def facility(facility_id: str, kind: str, x: float, y: float, name: str = "") -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": {"facility_id": facility_id, "facility_type": kind, "facility_name": name}}


# --- OSM tags ---------------------------------------------------------------------------------------


def test_tag_reads_one_key_from_an_osm_other_tags_string() -> None:
    tags = '"amenity"=>"shelter","shelter_type"=>"public_transport","office"=>"government"'
    assert evac.tag(tags, "amenity") == "shelter"
    assert evac.tag(tags, "office") == "government"
    assert evac.tag(tags, "religion") is None
    assert evac.tag(None, "amenity") is None
    assert evac.tag(float("nan"), "amenity") is None  # pandas uses NaN for a missing tag string.
    assert evac.txt(float("nan")) == "" and evac.txt("wat") == "wat"


# --- Shelter candidates -------------------------------------------------------------------------------


def test_shelter_candidates_exclude_amenity_shelter_huts(tmp_path: Path) -> None:
    osm_polygons = polygons([
        {"osm_way_id": "101", "name": "Ban Mai School", "amenity": "school", "geometry": box(0, 0, 100, 100)},
        {"osm_way_id": "102", "building": "yes", "geometry": box(10, 10, 30, 45)},  # 700 m² inside the school grounds.
        {"osm_way_id": "103", "name": "Bus stop hut", "amenity": "shelter", "building": "yes", "geometry": box(1000, 0, 1030, 30)},
        {"osm_way_id": "104", "name": "Wat Tham", "building": "temple", "geometry": box(2000, 0, 2020, 20)},
        {"osm_id": "9", "name": "District office", "other_tags": '"office"=>"government"', "geometry": box(3000, 0, 3050, 50)},
    ])
    osm_points = points([
        {"osm_id": "201", "name": "Field hut", "other_tags": '"amenity"=>"shelter"', "geometry": Point(1500, 500)},
        {"osm_id": "202", "name": "Wat Pa", "other_tags": '"amenity"=>"place_of_worship"', "geometry": Point(4000, 0)},
        {"osm_id": "203", "name": "Cafe", "other_tags": '"amenity"=>"cafe"', "geometry": Point(4500, 0)},
    ])
    path = facilities_file(tmp_path, [
        facility("OSM-301", "community_facility", 5000, 0, "Village hall"),
        facility("OSM-302", "health_facility", 5500, 0, "Clinic"),  # Not a shelter kind.
        facility("OSM-303", "school", 60, 60, "Ban Mai School (duplicate)"),  # Within 80 m of the mapped school.
    ])
    sites = evac.shelter_candidates(osm_polygons, osm_points, path, identity)
    assert [(site["id"], site["kind"], site["name"]) for site in sites] == [
        ("C001", "school", "Ban Mai School"),
        ("C002", "worship", "Wat Tham"),
        ("C003", "government", "District office"),
        ("C004", "worship", "Wat Pa"),
        ("C005", "community", "Village hall"),
    ]
    names = {site["name"] for site in sites}
    assert "Bus stop hut" not in names and "Field hut" not in names
    assert "shelter" not in evac.SITE_AMENITIES and "shelter" not in evac.SITE_BUILDINGS
    assert [site["source"] for site in sites] == ["OSM way/101", "OSM way/104", "OSM relation/9", "OSM node/202", "OSM node/301"]
    assert [site["has_polygon"] for site in sites] == [True, True, True, False, False]


def test_shelter_capacity_is_footprint_times_half_over_sphere_space(tmp_path: Path) -> None:
    assert evac.USABLE_FLOOR_SHARE == 0.5 and evac.SPHERE_M2_PER_PERSON == 3.5
    osm_polygons = polygons([
        {"osm_way_id": "1", "name": "grounds with one hall", "amenity": "school", "geometry": box(0, 0, 100, 100)},
        {"osm_way_id": "2", "building": "yes", "geometry": box(10, 10, 30, 45)},  # 700 m² -> 100 people.
        {"osm_way_id": "3", "name": "worship hall", "building": "temple", "geometry": box(1000, 0, 1000 + 557 / 20, 20)},  # 557 m².
        {"osm_way_id": "4", "name": "tiny hall", "building": "civic", "geometry": box(2000, 0, 2003, 2)},  # 6 m²: under one person.
        {"osm_way_id": "5", "name": "one-person hall", "building": "civic", "geometry": box(3000, 0, 3003.5, 2)},  # 7 m².
        {"osm_way_id": "6", "name": "grounds without buildings", "amenity": "school", "geometry": box(4000, 0, 4100, 100)},
        {"osm_way_id": "7", "building": "yes", "geometry": box(5000, 0, 5020, 14)},  # 280 m², 15 m from the point below.
    ])
    osm_points = points([{"osm_id": "8", "name": "point beside a hall", "other_tags": '"amenity"=>"townhall"', "geometry": Point(5035, 7)}])
    sites = {site["name"]: site for site in evac.shelter_candidates(osm_polygons, osm_points, facilities_file(tmp_path, []), identity)}
    assert (sites["grounds with one hall"]["footprint_m2"], sites["grounds with one hall"]["capacity_est"]) == (700, 100)
    assert (sites["worship hall"]["footprint_m2"], sites["worship hall"]["capacity_est"]) == (557, 79)  # int(557 * 0.5 / 3.5)
    assert (sites["tiny hall"]["footprint_m2"], sites["tiny hall"]["capacity_est"]) == (6, None)
    assert (sites["one-person hall"]["footprint_m2"], sites["one-person hall"]["capacity_est"]) == (7, 1)
    assert (sites["grounds without buildings"]["footprint_m2"], sites["grounds without buildings"]["capacity_est"]) == (0, None)
    # A point site takes whole buildings within 30 m.
    assert (sites["point beside a hall"]["footprint_m2"], sites["point beside a hall"]["capacity_est"]) == (280, 40)
    for site in sites.values():
        expected = site["footprint_m2"] * 0.5 / 3.5
        assert site["capacity_est"] == (int(expected) if expected >= 1 else None)


# --- Eligibility: freeboard at the modelled peak --------------------------------------------------------


def eligibility_fixture() -> tuple[np.ndarray, np.ndarray, SimpleNamespace, dict]:
    aoi = grid()
    codes = np.full(aoi.shape, NEVER_CODE, dtype=np.uint8)
    k = np.ones(aoi.shape, dtype=np.float32)

    def block(x: float, y: float, code: int, factor: float = 1.0) -> None:
        col, row = int(x // aoi.res), int((aoi.bounds[3] - y) // aoi.res)
        codes[row - 2:row + 3, col - 2:col + 3] = code
        k[row - 2:row + 3, col - 2:col + 3] = factor

    block(105, 905, 80)  # 4.00 m: 0.50 m above the 3.5 m peak.
    block(305, 905, 79)  # 3.95 m: 0.45 m above the peak.
    block(505, 905, 90, 0.5)  # 4.50 m on a tributary with k = 0.5: 0.5 * 1.0 = 0.50 m.
    block(705, 905, 89, 0.5)  # 4.45 m with k = 0.5: 0.475 m.
    block(105, 705, 40)  # 2.00 m: under water at the peak.
    block(305, 705, 80)
    codes[int((aoi.bounds[3] - 705) // aoi.res), int(305 // aoi.res)] = CHANNEL_CODE  # A channel cell under the site.
    graph = {"xy": np.array([[105.0, 905.0], [305.0, 905.0], [505.0, 905.0], [705.0, 905.0], [105.0, 705.0], [305.0, 705.0], [505.0, 705.0]])}
    return codes, k, aoi, graph


def test_freeboard_rule_needs_half_a_metre_at_the_modelled_peak() -> None:
    assert evac.SHELTER_FREEBOARD_M == 0.5
    codes, k, aoi, graph = eligibility_fixture()
    sites = [{"x": x, "y": y} for x, y in graph["xy"]]
    evac.evaluate_sites(sites, graph, codes, k, aoi, PEAK_STAGE_M)
    exact, short, tributary, tributary_short, flooded, channel, high_ground = sites
    assert (exact["h"], exact["freeboard_m"], exact["eligible"], exact["ineligible_reasons"]) == (4.0, 0.5, True, [])
    assert (short["h"], short["freeboard_m"], short["eligible"]) == (3.95, 0.45, False)
    assert short["ineligible_reasons"] == ["floods_or_under_freeboard_at_peak"]
    # Freeboard is water-surface clearance: the per-reach depth factor scales it.
    assert (tributary["k"], tributary["freeboard_m"], tributary["eligible"]) == (0.5, 0.5, True)
    assert tributary_short["freeboard_m"] == pytest.approx(0.47, abs=0.011) and tributary_short["eligible"] is False
    assert (flooded["freeboard_m"], flooded["eligible"]) == (-1.5, False)
    assert (channel["flood_stage"], channel["freeboard_m"], channel["eligible"]) == (0.0, None, False)
    assert channel["ineligible_reasons"] == ["floods_or_under_freeboard_at_peak"]
    # Ground above the encoded range never floods: eligible without a freeboard figure.
    assert math.isinf(high_ground["flood_stage"]) and high_ground["freeboard_m"] is None and high_ground["eligible"] is True
    assert all(site["m"] for site in sites) and all(site["snap_m"] == 0 for site in sites)


def test_sites_outside_the_model_or_far_from_a_road_are_ineligible() -> None:
    codes, k, aoi, graph = eligibility_fixture()
    outside = {"x": -500.0, "y": 905.0}
    unmodelled = {"x": 105.0, "y": 905.0}
    far_from_road = {"x": 105.0, "y": 905.0 - 401.0}
    near_road = {"x": 505.0, "y": 705.0 - 400.0}
    valid = np.ones(aoi.shape, dtype=bool)
    valid[:20, :20] = False  # The terrain model has no value under the "unmodelled" site.
    sites = [outside, unmodelled, far_from_road, near_road]
    evac.evaluate_sites(sites, graph, codes, k, aoi, PEAK_STAGE_M, valid)
    assert outside["m"] is False and outside["ineligible_reasons"] == ["outside_model", "no_road_within_400m"]
    assert unmodelled["m"] is False and unmodelled["ineligible_reasons"] == ["outside_model"]
    assert unmodelled["h"] is None and unmodelled["freeboard_m"] is None
    assert evac.SNAP_MAX_M == 400.0
    assert far_from_road["snap_m"] == 201 and far_from_road["eligible"] is True  # Snaps to the node 201 m south.
    assert near_road["snap_m"] == 400 and near_road["eligible"] is True
    lonely = {"x": 905.0, "y": 105.0}
    evac.evaluate_sites([lonely], graph, codes, k, aoi, PEAK_STAGE_M, valid)
    assert lonely["snap_m"] > 400 and lonely["ineligible_reasons"] == ["no_road_within_400m"]


# --- Demand: homes wet at a stage ---------------------------------------------------------------------


def test_home_wet_follows_the_hand_code_rule() -> None:
    home_code = np.array([CHANNEL_CODE, 1, 10, 69, 70, 71, 254, NEVER_CODE], dtype=np.uint8)
    assert evac.home_wet(home_code, 0.0).tolist() == [False] * 8  # Nothing is wet before the stage rises.
    assert evac.home_wet(home_code, 0.05).tolist() == [True, False, False, False, False, False, False, False]
    assert evac.home_wet(home_code, 0.5001).tolist() == [True, True, True, False, False, False, False, False]
    # Wet means code * 0.05 m < stage: a home exactly at the stage level stays dry.
    assert evac.home_wet(home_code, PEAK_STAGE_M).tolist() == [True, True, True, True, False, False, False, False]
    assert evac.home_wet(home_code, 99.0).tolist() == [True, True, True, True, True, True, True, False]  # Never code stays dry.
    assert HAND_STEP_M == 0.05


# --- Sampling helpers -----------------------------------------------------------------------------------


def test_sample_road_returns_the_earliest_closure_as_an_equivalent_depth_factor() -> None:
    aoi = grid(4, 1)
    xs, ys = np.array([5.0, 15.0, 25.0, 35.0]), np.full(4, 5.0)

    def closure(codes: list[int], factors: list[float]) -> tuple[float | None, float]:
        return evac.sample_road(np.array([codes], dtype=np.uint8), np.array([factors], dtype=np.float32), aoi, xs, ys)

    # Lowest point 1.0 m with k = 1 closes at 1.3 m; the higher tributary sample would close at 1.8 m.
    assert closure([20, 24, NEVER_CODE, CHANNEL_CODE], [1.0, 0.5, 1.0, 1.0]) == (1.0, 1.0)
    # Lowest point 1.0 m with k = 0.5 closes at 1.6 m, but the 1.2 m main-stem sample closes first, at 1.5 m.
    h, k = closure([20, 24, NEVER_CODE, CHANNEL_CODE], [0.5, 1.0, 1.0, 1.0])
    assert (h, k) == (1.0, 0.6)
    assert h + IMPASSABLE_DEPTH_M / k == pytest.approx(1.5)
    # Channel cells under a bridge and never-flooded cells are ignored; with nothing else there is no closure.
    assert closure([CHANNEL_CODE, CHANNEL_CODE, NEVER_CODE, NEVER_CODE], [1.0] * 4) == (None, 1.0)
    assert evac.sample_road(np.array([[20]], dtype=np.uint8), np.ones((1, 1), dtype=np.float32), grid(1, 1), np.array([500.0]), np.array([5.0])) == (None, 1.0)


def test_sample_eff_and_codes_at_read_the_lowest_usable_cell() -> None:
    aoi = grid(3, 1)
    codes = np.array([[CHANNEL_CODE, 30, 12]], dtype=np.uint8)
    k = np.array([[1.0, 0.8, 0.4]], dtype=np.float32)
    xs, ys = np.array([5.0, 15.0, 25.0]), np.full(3, 5.0)
    assert evac.sample_eff(codes, k, aoi, xs, ys) == (0.6, 0.4)
    assert evac.sample_eff(codes, k, aoi, xs[:1], ys[:1]) == (None, 1.0)
    assert evac.codes_at(codes, aoi, 5.0, 5.0) == CHANNEL_CODE
    assert evac.codes_at(codes, aoi, 29.9, 0.1) == 12
    assert evac.codes_at(codes, aoi, 30.0, 5.0) == NEVER_CODE  # Outside the grid.
    assert evac.codes_at(codes, aoi, 5.0, -1.0) == NEVER_CODE


# --- Greedy plan and access cut-off codes ---------------------------------------------------------------


def plan_fixture() -> tuple[list[dict], list[dict], dict]:
    """Road 0-1-2-3-4-5 with 1 km links; node 6 has no road.

    Homes at nodes 1, 2, 3 and 6 are wet at the 3.5 m peak (the plan's demand); the home at node 4 stays dry.
    Link 0-1 becomes impassable at 0.8 m and link 3-4 at 2.0 m.
    """
    u, v = np.array([0, 1, 2, 3, 4]), np.array([1, 2, 3, 4, 5])
    population = pd.DataFrame({"node_id": ["n1", "n2", "n3", "n4", "n6"], "total_population": [100.0, 50.0, 30.0, 20.0, 10.0],
                               "vulnerable_population": [10.0, 0.0, 30.0, 0.0, 10.0]})
    graph = {
        "ids": list(range(7)), "u": u, "v": v, "length": np.full(5, 1000.0),
        "close": np.array([0.8, math.inf, math.inf, 2.0, math.inf]),
        "pop": population, "pop_index": np.array([1, 2, 3, 4, 6]),
        "home_code": np.array([10, 20, 60, 100, 10], dtype=np.uint8),
    }
    sites = [
        {"id": "C001", "node": 0, "flood_stage": math.inf, "eligible": True},
        {"id": "C002", "node": 2, "flood_stage": 0.0, "eligible": False},  # Would cover the most, but floods.
        {"id": "C003", "node": 5, "flood_stage": math.inf, "eligible": True},
    ]
    reported = [{"node": 2, "flood_stage": 1.5}]  # Reported in use in 2024; water reaches it at 1.5 m.
    return sites, reported, graph


def test_coverage_masks_use_two_kilometres_on_roads_still_open() -> None:
    assert evac.ACCESS_THRESHOLD_M == 2000.0
    sites, _, graph = plan_fixture()
    eligible = [site for site in sites if site["eligible"]]
    demand = np.array([1, 2, 3, 6])
    masks, dist = evac.coverage_masks(eligible, graph, demand, evac.EVACUATION_STAGE_M)
    assert [mask.tolist() for mask in masks] == [[True, True, False, False], [False, False, True, False]]
    assert dist[0, 2] == pytest.approx(2000.0) and not np.isfinite(dist[0, 3])  # 3 km is past the limit.
    # One metre beyond 2 km is out of reach.
    longer = {**graph, "length": np.array([1000.0, 1001.0, 1000.0, 1000.0, 1000.0])}
    assert evac.coverage_masks(eligible, longer, demand, 0.0)[0][0].tolist() == [True, False, False, False]
    # Late evacuation at 1.0 m: link 0-1 is already impassable, so the first site serves nobody.
    late, _ = evac.coverage_masks(eligible, graph, demand, evac.LATE_EVACUATION_STAGE_M)
    assert [mask.tolist() for mask in late] == [[False, False, False, False], [False, False, True, False]]


def test_plan_and_access_ranks_eligible_sites_and_codes_every_set() -> None:
    sites, reported, graph = plan_fixture()
    result = evac.plan_and_access(sites, reported, graph, PEAK_STAGE_M)
    # Demand is every resident of a home that is wet at the peak: 100 + 50 + 30 + 10.
    assert result["demand_people"] == 190
    assert result["uncoverable_people"] == 10  # Node 6 has no road to any site.
    assert result["eligible_count"] == 2
    ranking = result["ranking"]
    assert [entry["candidate_id"] for entry in ranking] == ["C001", "C003"]  # The flooded site C002 is never ranked.
    assert [entry["marginal_demand"] for entry in ranking] == [150.0, 30.0]
    assert [entry["cumulative_demand"] for entry in ranking] == [150.0, 180.0]
    assert [entry["cumulative_share"] for entry in ranking] == [0.7895, 0.9474]
    assert [entry["loads"] for entry in ranking] == [[150], [150, 30]]  # Each resident goes to the nearest chosen site.
    assert [entry["late_cumulative_share"] for entry in ranking] == [0.0, 0.1579]
    assert result["knee_k"] == 2  # Smallest plan reaching 90% of the best coverage (162 of 180).
    assert result["set_ids"] == ["reported_2024", "plan_1", "plan_2"]
    codes = result["node_codes"]
    assert codes.shape == (3, 5) and codes.dtype == np.uint8
    # Rows follow graph["pop_index"]: nodes 1, 2, 3, 4, 6. Levels are 0.05 m apart, so 0.8 m is index 16.
    assert codes[0].tolist() == [30, 30, 30, 30, NO_BASELINE_ACCESS]  # The reported site floods at 1.5 m.
    assert codes[1].tolist() == [16, 16, NO_BASELINE_ACCESS, NO_BASELINE_ACCESS, NO_BASELINE_ACCESS]
    assert codes[2].tolist() == [16, 16, 40, NEVER_LOST, NO_BASELINE_ACCESS]
    assert (NEVER_LOST, NO_BASELINE_ACCESS) == (254, 255)
    # No score and no action class comes out of this stage.
    assert not {"fpps", "action_class", "accepted_fpps", "accepted_action_class"} & set(result)


def test_plan_and_access_without_reported_sites_has_only_plan_sets() -> None:
    sites, _, graph = plan_fixture()
    result = evac.plan_and_access(sites, [], graph, PEAK_STAGE_M)
    assert result["set_ids"] == ["plan_1", "plan_2"]
    assert result["node_codes"].shape == (2, 5)


def test_lost_at_counts_only_nodes_that_had_access_and_lost_it() -> None:
    codes = np.array([1, 16, 40, 80, NEVER_LOST, NO_BASELINE_ACCESS], dtype=np.uint8)
    assert evac.lost_at(codes, 0.0).tolist() == [False] * 6
    assert evac.lost_at(codes, 0.05).tolist() == [True, False, False, False, False, False]
    assert evac.lost_at(codes, 0.79).tolist() == [True, False, False, False, False, False]
    assert evac.lost_at(codes, 0.8).tolist() == [True, True, False, False, False, False]
    assert evac.lost_at(codes, 3.5).tolist() == [True, True, True, False, False, False]
    assert evac.lost_at(codes, 4.0).tolist() == [True, True, True, True, False, False]
    # 254 (never lost) and 255 (no access even before the flood) are never counted as lost, however high the stage.
    assert evac.lost_at(codes, 100.0).tolist() == [True, True, True, True, False, False]
    assert evac.lost_at(np.array([254, 255], dtype=np.uint8), 12.7).tolist() == [False, False]  # Level index 254.


def test_lost_at_level_index_survives_binary_rounding() -> None:
    # 0.15 / 0.05 and 0.35 / 0.05 fall just under 3 and 7 in binary floating point; the level must still count.
    assert 0.15 / 0.05 < 3 and 0.35 / 0.05 < 7
    for index, level in enumerate(evac.LEVELS):
        codes = np.array([index], dtype=np.uint8)
        assert evac.lost_at(codes, level).tolist() == [True], level
        if index:
            assert evac.lost_at(codes, level - 0.01).tolist() == [False], level
    assert len(evac.LEVELS) == 81 and evac.LEVELS[0] == 0.0 and evac.LEVELS[-1] == 4.0


def test_lost_at_agrees_with_a_direct_reachability_check() -> None:
    sites, _, graph = plan_fixture()
    result = evac.plan_and_access(sites, [], graph, PEAK_STAGE_M)
    row = result["node_codes"][1]  # plan_2
    single = cutoff_levels(7, graph["u"], graph["v"], graph["length"], graph["close"], [0, 5], [math.inf, math.inf],
                           evac.LEVELS, evac.ACCESS_THRESHOLD_M)
    assert row.tolist() == single[graph["pop_index"]].tolist()
    people = graph["pop"]["total_population"].to_numpy(float)
    vulnerable = graph["pop"]["vulnerable_population"].to_numpy(float)
    lost_by_stage = {stage: evac.lost_at(row, stage) for stage in (0.5, 0.8, 2.0, PEAK_STAGE_M)}
    assert [float(people[mask].sum()) for mask in lost_by_stage.values()] == [0.0, 150.0, 180.0, 180.0]
    assert [float(vulnerable[mask].sum()) for mask in lost_by_stage.values()] == [0.0, 10.0, 40.0, 40.0]


# --- Graph loading and population -----------------------------------------------------------------------


def test_build_graph_attaches_closure_stages_and_home_codes(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "mae_sai_access_edges.csv").write_text(
        "from_node,to_node,normal_minutes\nN-0.0005-0.0005,N-0.0015-0.0005,2\nN-0.0015-0.0005,N-0.0025-0.0005,2\n", encoding="utf-8")
    (tmp_path / "outputs" / "mae_sai_population_nodes.csv").write_text(
        "node_id,total_population,vulnerable_population\nN-0.0005-0.0005,40,4\nN-0.0025-0.0005,60,0\nN-0.0035-0.0005,5,5\n", encoding="utf-8")
    aoi = grid(40, 10)
    codes = np.full(aoi.shape, NEVER_CODE, dtype=np.uint8)
    codes[:, :10] = 20  # 1.0 m
    codes[:, 10:20] = 30  # 1.5 m
    codes[:, 30:] = CHANNEL_CODE
    k = np.ones(aoi.shape, dtype=np.float32)
    opened: list[Path] = []

    def track(path: Path) -> Path:
        opened.append(path)
        return path

    graph = evac.build_graph(tmp_path, lambda lon, lat: (lon * 1e5, lat * 1e5), codes, k, aoi, track)
    assert [path.name for path in opened] == ["mae_sai_access_edges.csv", "mae_sai_population_nodes.csv"]
    assert len(graph["ids"]) == 4 and graph["length"].tolist() == pytest.approx([100.0, 100.0])
    # A link closes 0.3 m above its lowest usable sample: 1.0 m and 1.5 m ground.
    assert graph["close"].tolist() == pytest.approx([1.3, 1.8])
    assert graph["pop_index"].tolist() == [0, 2, 3]
    # The home at x = 250 m is on never-flooded ground; the home at x = 350 m sits on a channel cell (riverside).
    assert graph["home_code"].tolist() == [20, NEVER_CODE, CHANNEL_CODE]
    assert evac.home_wet(graph["home_code"], 0.5).tolist() == [False, False, True]
    assert evac.node_lonlat("N-99.8826-20.4460") == (99.8826, 20.446)


def test_population_grid_keeps_density_and_density_codes_stay_in_range(tmp_path: Path) -> None:
    aoi = SimpleNamespace(crs="EPSG:32647", bounds=(590000.0, 2250000.0, 592000.0, 2252000.0), res=10.0, width=200, height=200,
                          shape=(200, 200), transform=from_origin(590000.0, 2252000.0, 10.0, 10.0))
    res = 1 / 1200  # WorldPop's 3 arc-second grid.
    path = tmp_path / "worldpop.tif"
    with rasterio.open(path, "w", driver="GTiff", width=120, height=120, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(99.82, 20.40, res, res), nodata=-99999.0) as dst:
        dst.write(np.full((120, 120), 8.0, dtype=np.float32), 1)
    coarse, fine = evac.population_grid(path, aoi)
    assert coarse.shape == (20, 20) and fine.shape == (200, 200)
    # 8 people per 3 arc-second cell (about 92.8 m x 87.0 m here) is about 9.9 people per hectare.
    assert coarse.min() == pytest.approx(9.9, abs=0.15) and coarse.max() == pytest.approx(9.9, abs=0.15)
    assert fine.sum() == pytest.approx(coarse.sum())  # Spreading over 10 m cells keeps every person.
    water = SimpleNamespace(crs="EPSG:32647", shape=(40, 40), transform=from_origin(590000.0, 2252000.0, 50.0, 50.0))
    density, cap = evac.density_codes(coarse, aoi, water)
    assert density.dtype == np.uint8 and density.max() <= 254 and cap == pytest.approx(9.9, abs=0.15)
    empty, empty_cap = evac.density_codes(np.zeros((20, 20)), aoi, water)
    assert not empty.any() and empty_cap == 1.0
