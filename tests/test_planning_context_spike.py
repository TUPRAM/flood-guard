"""E0 spike helpers and the SE2-blind district rule, on invented inputs.

The committed spike receipts are checked for shape only, and for one thing
that matters: while the route rule (open item OI-02) is undecided, none of the
spike's candidate values may sit in protocol v1b as if it were decided.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "planning_v1"
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def spike():
    return _load("run_planning_context_spike")


@pytest.fixture(scope="module")
def ranking():
    return _load("rank_chiang_rai_district_population")


def test_fastest_path_ends_at_the_goal_node_that_is_quickest_to_reach(spike) -> None:
    # 0 -1- 1 -1- 2 -1- 3, a slow direct edge 0-3, and a spur 1-4.
    sources, targets, minutes = [0, 1, 2, 0, 1], [1, 2, 3, 3, 4], [1.0, 1.0, 1.0, 5.0, 0.5]
    path, total = spike.fastest_path(5, sources, targets, minutes, origin=0, goal_nodes=[3])
    assert path == [0, 1, 2] and total == pytest.approx(3.0)
    path, total = spike.fastest_path(5, sources, targets, minutes, origin=0, goal_nodes=[3, 4])
    assert path == [0, 4] and total == pytest.approx(1.5)
    path, total = spike.fastest_path(5, sources, targets, minutes, origin=3, goal_nodes=[3])
    assert path == [] and total == 0.0


def test_fastest_path_uses_the_quicker_of_two_parallel_edges_and_refuses_unreachable_goals(spike) -> None:
    path, total = spike.fastest_path(2, [0, 0], [1, 1], [4.0, 2.0], origin=0, goal_nodes=[1])
    assert path == [1] and total == pytest.approx(2.0)
    with pytest.raises(ValueError, match="reached"):
        spike.fastest_path(3, [0], [1], [1.0], origin=0, goal_nodes=[2])
    with pytest.raises(ValueError, match="no goal"):
        spike.fastest_path(3, [0], [1], [1.0], origin=0, goal_nodes=[])


def test_no_route_share_divides_by_graph_connected_residents(spike) -> None:
    access = {
        "totals": {"total_population": 1000.0},
        "coverage_review": {
            "missing_graph_coverage_population": 200.0,
            "baseline": {"graph_connected_no_modelled_route_population": 40.0},
        },
    }
    result = spike.no_route_share(access)
    assert result["graph_connected_residents"] == 800.0
    assert result["share"] == pytest.approx(0.05)
    assert result["residents_not_connected_to_the_graph"] == 200.0
    access["coverage_review"]["missing_graph_coverage_population"] = 1000.0
    assert spike.no_route_share(access)["share"] == 1.0


def test_spike_variants_and_helpers(spike) -> None:
    assert spike.VARIANTS == {"proposal": ("trunk", "primary"), "whole_path": None}
    assert set(spike.ROUTE_RULES) == set(spike.VARIANTS)
    assert "trunk or primary" in spike.ROUTE_RULES["proposal"]
    assert "every segment" in spike.ROUTE_RULES["whole_path"]
    peak = spike.peak_memory_gib()
    assert peak is None or peak > 0
    assert spike.encode({"a": "\u0e01"}) == b'{\n  "a": "\\u0e01"\n}\n'


def test_edge_counts_and_hospital_breakdown_are_counts_for_the_whole_context(spike) -> None:
    edges = [
        {"road_class": "residential", "bridge": "no", "tunnel": "no"},
        {"road_class": "residential", "bridge": "yes", "tunnel": "no"},
        {"road_class": "trunk", "bridge": "no", "tunnel": "culvert"},
        {"road_class": "local"},
    ]
    counts = spike.edge_tag_counts(edges)
    assert counts["edges"] == 4 and counts["by_road_class"] == {"local": 1, "residential": 2, "trunk": 1}
    assert counts["share_by_road_class"]["residential"] == 0.5
    assert counts["bridge_yes_edges"] == 1 and counts["tunnel_culvert_edges"] == 1
    assert counts["by_bridge_tag"] == {"no": 3, "yes": 1}
    assert "culvert=*" in counts["culvert_tag_note"]
    assert spike.edge_tag_counts([])["share_by_road_class"] == {}

    destinations = [
        {"name": "Hospital A"}, {"name": "hospital  a"}, {"name": "Hospital B"}, {"name": spike.UNNAMED_FACILITY},
    ]
    breakdown = spike.hospital_breakdown(destinations)
    assert breakdown["osm_objects"] == 4 and breakdown["distinct_named_hospitals"] == 2
    assert breakdown["unnamed_objects"] == 1 and breakdown["objects_that_repeat_a_named_hospital"] == 1


def test_a_run_is_compared_with_the_previous_run_of_the_same_variant(spike, tmp_path: Path) -> None:
    assert spike.previous_run("proposal", tmp_path) is None
    assert spike.reproducibility(None, {})["compared"] is False

    geometry = {"type": "Polygon", "coordinates": [[[99.0, 20.0], [99.1, 20.0], [99.1, 20.1], [99.0, 20.0]]]}
    joins = [{"join_id": "grade-join-a", "node_ids": ["n1", "n2"]}]
    (tmp_path / "e0_context_spike_proposal.json").write_bytes(spike.encode({
        "generated_at_utc": "2026-10-02T00:00:00Z", "context": {"canonical_sha256": "c" * 64},
        "e0_spike_record_candidate": {"edge_count": 10},
    }))
    (tmp_path / "corridor_candidate_proposal.geojson").write_bytes(spike.encode({
        "type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": geometry}],
    }))
    # An older log without joins_sha256 can still be compared: the hash is taken over its joins.
    (tmp_path / "grade_join_log_candidate_proposal.json").write_bytes(spike.encode({"join_count": 1, "joins": joins}))
    previous = spike.previous_run("proposal", tmp_path)
    assert previous is not None and previous["generated_at_utc"] == "2026-10-02T00:00:00Z"
    assert previous["corridor_geometry_sha256"] == spike.geometry_sha256(geometry)

    current = {key: previous[key] for key in (
        "context_canonical_sha256", "corridor_geometry_sha256", "joins_sha256", "edge_count", "join_count")}
    same = spike.reproducibility(previous, current)
    assert same["compared"] is True and same["all_same"] is True and set(same["same"].values()) == {True}
    moved = dict(geometry, coordinates=[[[99.0, 20.0], [99.2, 20.0], [99.1, 20.1], [99.0, 20.0]]])
    different = spike.reproducibility(previous, {**current, "corridor_geometry_sha256": spike.geometry_sha256(moved)})
    assert different["all_same"] is False and different["same"]["corridor_geometry_sha256"] is False
    assert different["same"]["joins_sha256"] is True


def test_memory_sampler_gives_a_block_its_own_peak(spike) -> None:
    import time

    if spike.current_memory_gib() is None:
        pytest.skip("current memory cannot be read on this platform")
    with spike.MemorySampler(interval=0.01) as sampler:
        block = bytearray(64 * 1024 * 1024)
        time.sleep(0.05)
        del block
    assert sampler.samples >= 2 and sampler.start_gib is not None
    assert sampler.peak_gib is not None and sampler.peak_gib >= sampler.start_gib
    whole_process = spike.peak_memory_gib()
    assert whole_process is None or sampler.peak_gib <= whole_process + 1e-6


def test_blind_district_is_the_most_populous_eligible_one(ranking) -> None:
    totals = {"D1": 500.0, "D2": 300.0, "D3": 290.0, "D4": 300.0}
    choice = ranking.select_blind_district(totals, {"D1"})
    assert choice["selected"] == "D2" and choice["runner_up"] == "D4"  # tie broken on the lower code
    assert choice["margin_share_of_selected"] == 0.0
    choice = ranking.select_blind_district({"D1": 500.0, "D2": 300.0, "D3": 150.0}, {"D1"})
    assert choice["selected"] == "D2" and choice["margin_share_of_selected"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        ranking.select_blind_district({"D1": 500.0, "D2": 300.0}, {"D1"})
    with pytest.raises(ValueError):
        ranking.select_blind_district({"D1": 500.0, "D2": 0.0, "D3": 1.0}, {"D1"})
    assert ranking.EXCLUDED_DISTRICTS == {"TH5701": "Mueang Chiang Rai", "TH5709": "Mae Sai"}


def test_committed_district_ranking_matches_the_protocol(ranking) -> None:
    path = OUTPUTS / "se2_blind_district_ranking.json"
    if not path.exists():
        pytest.skip("the district ranking has not been run on this checkout")
    raw = path.read_bytes()
    receipt = json.loads(raw.decode("ascii"))
    assert receipt["official_warning"] is False and receipt["source_timestamp"] and receipt["assumptions"]
    assert receipt["confidence_class"] == "low"
    rows = receipt["districts_ranked"]
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
    assert rows == sorted(rows, key=lambda row: (-row["residents_2020"], row["adm2_pcode"]))
    eligible = [row for row in rows if row["eligible"]]
    assert receipt["selected_district"]["adm2_pcode"] == eligible[0]["adm2_pcode"]
    assert not any(row["eligible"] for row in rows if row["adm2_pcode"] in ranking.EXCLUDED_DISTRICTS)
    blind = json.loads(PROTOCOL.read_text(encoding="utf-8"))["corridor_polygon"]["se2_frame"]["se2_blind_district"]
    if blind is None:
        pytest.skip("the SE2-blind district is not recorded in protocol v1b yet")
    assert blind["adm2_pcode"] == receipt["selected_district"]["adm2_pcode"]
    assert blind["evidence_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("variant", ["proposal", "whole_path"])
def test_committed_spike_receipts_are_candidates_and_stay_out_of_the_protocol(variant: str) -> None:
    path = OUTPUTS / f"e0_context_spike_{variant}.json"
    if not path.exists():
        pytest.skip("the E0 spike has not been run on this checkout")
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    receipt = json.loads(raw.decode("ascii"))
    assert receipt["status"] == "candidate_measurement" and receipt["route_rule_variant"] == variant
    assert receipt["official_warning"] is False and receipt["confidence_class"] == "low"
    assert receipt["source_timestamp"] and receipt["assumptions"]
    # A run counts as made in a declared compute window only when the operator declared one.
    window = receipt["acceptance"]["compute_window"]
    assert window["met"] is bool(window["declared_by_the_operator"])
    record = receipt["e0_spike_record_candidate"]
    assert set(record) == {
        "hospital_count", "within_routing_context_for_named_ways", "edge_count", "wall_time_minutes",
        "peak_ram_gib", "grade_split_count", "baseline_vehicle_no_route_share",
    }
    for name in ("corridor", "grade_joins"):
        key = "log" if name == "grade_joins" else ""
        file_path = ROOT / receipt[name][f"{key}_path".lstrip("_")]
        assert hashlib.sha256(file_path.read_bytes()).hexdigest() == receipt[name][f"{key}_sha256".lstrip("_")]
    # No figure for a single tambon, and no personal field from the shelter list.
    text = raw.decode("ascii")
    assert "TH5709" not in text and "subdistrict_id" not in text and "phone" not in text.lower()

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in protocol["open_items"]}
    if items["OI-02"]["status"] == "open":
        corridor = protocol["corridor_polygon"]
        assert corridor["route_selection_rule"]["rule"] is None
        assert corridor["geometry_file"] == {"path": None, "sha256": None}
        assert set(corridor["e0_spike_record"].values()) == {None}
        assert protocol["grade_join_policy"]["join_log"] == {"path": None, "sha256": None, "join_count": None}
        for dependent in ("OI-01", "OI-03", "OI-04"):
            assert items[dependent]["status"] == "open", dependent


def _toy_network() -> tuple[dict, dict]:
    """A trunk road leaving a small AOI, a tertiary road beyond it, and a hospital at the far end."""

    roads = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"osm_id": "1", "highway": "trunk"},
         "geometry": {"type": "LineString", "coordinates": [[99.05, 20.0], [99.10, 20.0], [99.20, 20.0]]}},
        {"type": "Feature", "properties": {"osm_id": "2", "highway": "tertiary"},
         "geometry": {"type": "LineString", "coordinates": [[99.20, 20.0], [99.30, 20.0]]}},
        {"type": "Feature", "properties": {"osm_id": "3", "highway": "primary", "access": "private"},
         "geometry": {"type": "LineString", "coordinates": [[99.05, 20.0], [99.30, 20.0]]}},
    ]}
    areas = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"osm_way_id": "999", "amenity": "hospital"},
         "geometry": {"type": "Polygon", "coordinates": [[
             [99.2999, 20.0001], [99.3009, 20.0001], [99.3009, 20.0009], [99.2999, 20.0009], [99.2999, 20.0001],
         ]]}},
    ]}
    return roads, areas


def test_corridor_reaches_the_hospital_only_when_the_whole_path_is_buffered(spike) -> None:
    from shapely.geometry import box

    roads, areas = _toy_network()
    aoi, scope = box(99.00, 19.95, 99.10, 20.05), box(98.9, 19.8, 99.5, 20.2)
    results = {}
    for variant, kept in spike.VARIANTS.items():
        corridor, records = spike.build_corridor(roads, areas, aoi, scope, {999: "toy hospital"}, 3000.0, kept)
        assert corridor.covers(aoi) and corridor.geom_type == "Polygon"
        results[variant] = records[0]
    for record in results.values():
        assert record["route_found"] and record["snapped_within_100_m"]
        assert record["path_osm_way_ids"] == ["2", "1"]  # the private road is never used
        assert set(record["route_km_by_road_class"]) == {"tertiary", "trunk"}
    assert results["proposal"]["kept_osm_way_ids"] == ["1"]
    assert results["proposal"]["way_polygon_inside_corridor"] is False
    assert results["whole_path"]["kept_osm_way_ids"] == ["2", "1"]
    assert results["whole_path"]["way_polygon_inside_corridor"] is True
    missing = spike.build_corridor(roads, areas, aoi, scope, {123: "not mapped"}, 3000.0, None)[1][0]
    assert missing == {"osm_way": 123, "name": "not mapped", "found_in_osm_extract": False}


def test_facility_counts_are_counts_only(spike, tmp_path: Path) -> None:
    import csv

    from shapely.geometry import box

    from test_ddpm_shelters import HEADER, PERSON, PHONE, _row

    destinations = [
        {"facility_id": "OSM-way-1", "name": spike.MAE_SAI_HOSPITAL_NAME_TH,
         "source_geometry": {"type": "Point", "coordinates": [99.05, 20.0]}},
        {"facility_id": "OSM-way-2", "name": "other",
         "source_geometry": {"type": "Point", "coordinates": [99.08, 20.0]}},
    ]
    dga = tmp_path / "dga.geojson"
    dga.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [99.0505, 20.0]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [99.09, 20.0]}},
    ]}), encoding="utf-8")
    ddpm = tmp_path / "ddpm.csv"
    with ddpm.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        writer.writerows([_row(1, "100", "20.0", "99.05"), _row(2, "1,000", "20.01", "99.06"),
                          _row(3, "50", "20.3", "99.9")])
    counts = spike.facility_counts(destinations, box(99.0, 19.9, 99.1, 20.1), dga, ddpm)
    assert counts["osm_hospitals"] == 2
    assert counts["mae_sai_hospital_facility_ids_by_osm_name"] == ["OSM-way-1"]
    assert counts["dga_matched_hospitals"] == 1  # 52 m away; the other record is about 1 km away
    assert counts["located_ddpm_shelters"] == 2
    assert counts["ddpm_rows_with_a_coordinate_in_the_routing_context"]["located_places"] == 1100.0
    assert counts["corroborated_shelters"] is None and counts["ddpm_publication_level"] == "pitch"
    text = json.dumps(counts)
    assert PERSON not in text and PHONE not in text
    bare = spike.facility_counts(destinations, box(99.0, 19.9, 99.1, 20.1), None, None)
    assert bare["dga_matched_hospitals"] is None and bare["located_ddpm_shelters"] is None
