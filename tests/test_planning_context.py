"""Plan task E4 (the planning context) on invented inputs.

The roads, hospitals, shelters, people and DGA records below are made up, around
99.0 E, 20.0 N; no real place is routed. The names and phone numbers in the
shelter list are test strings, not people: the point of the PII tests is that
they never reach an output. Plan row E4 asks for: a PII whitelist test, the
located-shelter flag, at least 4 hospitals, a no-route share of at most 10%, and
``load_aois`` still returning 6. These tests cover the rules; the counts of the
real corridor come from the build of record.

The last test runs the real context builder on a small clip of the national
files and is skipped unless FLOODGUARD_EXTERNAL_DATA names the external data root.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest
from shapely.geometry import Point, box, mapping

from floodguard import evidence_context, planning_context
from floodguard.ddpm_shelters import LOCATED, read_ddpm_shelters
from floodguard.grade_join import apply_grade_joins
from floodguard.planning_context import (
    BUILDER_SNAP_KEYS,
    DDPM_LOCATED_SHELTER,
    MAIN_ROAD_ENTRY,
    OSM_MATCH_LAYERS,
    PERSONAL_FIELD,
    SHELTER_FACILITY_KEYS,
    SHELTER_SOURCE_KEYS,
    PlanningContextError,
    assemble_outputs,
    assert_no_personal_fields,
    dga_matches,
    main_road_entries,
    receipt_body,
    reproduction_check,
    shelter_facilities,
)
from floodguard.shelter_corroboration import AMENITY, BUILDING

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_V1B = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
SOURCE_TIMESTAMP = "2026-07-10T02:46:49Z"
GENERATED_AT = "2026-10-03T05:00:00Z"
HEADER = [
    "ที่", "ภาค", "จังหวัด",
    "อำเภอ", "ตำบล",
    "หมู่บ้าน/ชุมชน",
    "สถานที่", "รองรับ",
    "สถานที่รับผิดชอบอปท.",
    "ชื่อ - สกุล ผู้ประสาน",
    "หมายเลขโทรศัพท์",
    "ไฟฟ้า", "ประปา", "สุขา",
    "ละติจูด", "ลองจิจูด",
]
PERSON = "TEST-COORDINATOR-NAME"
PHONE = "000-TEST-PHONE"
ROUTING = box(98.99, 19.99, 99.02, 20.02)
DEMAND = box(98.995, 19.995, 99.01, 20.01)
REPORTING = box(98.98, 19.98, 99.03, 20.03)
# About 0.001 degree of longitude is 104.6 m at 20 degrees north.
LON_M = 0.001 / 104.6


def _way(osm_id: str, coordinates: list[list[float]], **tags: str) -> dict[str, Any]:
    other = ",".join(f'"{key}"=>"{value}"' for key, value in tags.items() if key != "highway")
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, "highway": tags.get("highway", "primary"), "other_tags": other or None},
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


ROADS = {"type": "FeatureCollection", "features": [
    _way("1", [[99.000, 20.000], [99.001, 20.000]], highway="primary"),
    _way("2", [[99.001, 20.000], [99.002, 20.000]], highway="primary", bridge="yes", layer="1"),
    _way("3", [[99.002, 20.000], [99.003, 20.000]], highway="primary_link"),
    _way("4", [[99.003, 20.000], [99.003, 20.002]], highway="residential"),
    _way("5", [[99.000, 20.000], [99.000, 20.002]], highway="residential"),
    _way("6", [[99.003, 20.002], [99.004, 20.002]], highway="trunk"),
    # A bridge that starts 1e-7 degree (about 1 cm) from the end of way 6: no shared coordinate, no join at 0 m.
    _way("7", [[99.0040001, 20.002], [99.005, 20.002]], highway="tertiary", bridge="yes", layer="1"),
]}
HOSPITAL_A = box(99.0028, 20.0018, 99.0032, 20.0022)
POINTS = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"osm_way_id": "100", "amenity": "hospital", "name": "Synthetic hospital A"},
     "geometry": mapping(HOSPITAL_A)},
    {"type": "Feature", "properties": {"osm_id": "200", "amenity": "hospital", "name": "Synthetic hospital B"},
     "geometry": {"type": "Point", "coordinates": [99.0001, 20.0001]}},
    {"type": "Feature", "properties": {"osm_id": "300", "amenity": "hospital", "name": "Synthetic hospital C"},
     "geometry": {"type": "Point", "coordinates": [99.05, 20.05]}},
]}
# (longitude, latitude, residents). The second cell snaps to the cut-off bridge of way 7.
CELLS = [(99.0002, 20.0002, 100.0), (99.0031, 20.0015, 60.0), (99.0052, 20.0021, 40.0)]


def fake_build_context_inputs(context_root, aoi_geometry, routing_geometry, facilities, output_dir, *,
                              reporting_geometry=None, travel_mode="legacy_vehicle", reviewed_junctions=()):
    """Stand in for build_context_inputs on the invented roads, through the builder's own graph and snap code."""

    aoi = evidence_context._polygon(aoi_geometry)
    routing = evidence_context._polygon(routing_geometry)
    scope = evidence_context._polygon(reporting_geometry)
    assert routing.covers(aoi)
    scoped = routing.intersection(scope)
    edges, nodes, _geojson, topology = evidence_context._road_graph(
        ROADS, scoped, travel_mode=travel_mode, reviewed_junctions=reviewed_junctions)
    index = evidence_context._NodeIndex(nodes, allowed_geometry=scope)
    population = []
    for number, (lon, lat, people) in enumerate(CELLS):
        node, distance = index.snap(lon, lat, 250.0)
        population.append({"population_id": f"cell-{number}", "subdistrict_id": "synthetic-unit",
                           "total_population": people, "node_id": node, "snap_distance_m": distance,
                           "longitude": lon, "latitude": lat})
    supplied = evidence_context._snap_facilities(facilities, scoped, index)
    osm = evidence_context._snap_facilities(evidence_context._osm_facilities(POINTS), scoped, index)
    review = topology.pop("grade_connection_review")
    evidence_context._rank_connection_review(review, nodes, edges, population)
    total = sum(row["total_population"] for row in population)
    package = {
        "schema_version": "floodguard.context_scenario_inputs.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "travel_mode": travel_mode,
        "population": population,
        "edges": edges,
        "facilities": supplied,
        "osm_facilities": osm,
        "node_coordinates": nodes,
        "connectivity_review": review,
        "coverage": {**topology, "population_cells": len(population), "modelled_population_2020": total,
                     "population_snap_coverage_fraction": 1.0},
        "source_metadata": {"osm": {"retrieved_at_utc": SOURCE_TIMESTAMP}},
        "input_hashes": {"osm": "a" * 64, "worldpop": "b" * 64,
                         "supplied_facilities": evidence_context._canonical_hash(list(facilities))},
    }
    package["canonical_sha256"] = evidence_context._context_content_hash(package)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    evidence_context._write_json(Path(output_dir) / "context_inputs.json", package)
    return package


def _shelter_row(number: int, latitude: str, longitude: str, places: str = "100") -> list[str]:
    return [str(number), "north", "province", "district", "tambon", "village", f"place {number}", places,
            "lao", PERSON, PHONE, "yes", "yes", "yes", latitude, longitude]


def _ddpm_file(tmp_path: Path) -> Path:
    rows = [
        _shelter_row(1, "20.0010", "99.0010"),  # inside, on a building: corroborated by a building
        _shelter_row(2, "20.0050", "99.0060"),  # inside, about 10 m from an amenity point
        _shelter_row(3, "20.0150", "99.0150"),  # inside, far from both: located, not corroborated
        *[_shelter_row(number, "20.0030", "99.0020") for number in (4, 5, 6)],  # a placeholder coordinate
        _shelter_row(7, "20.1000", "99.1000"),  # outside the routing context
        _shelter_row(8, "", "99.0010"),  # no coordinate
    ]
    path = tmp_path / "shelters.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


MATCH_OBJECTS = [
    (frozenset({BUILDING}), box(99.0009, 20.0009, 99.0011, 20.0011)),
    (frozenset({AMENITY}), Point(99.0061, 20.0050)),
]


def _case() -> dict[str, Any]:
    return {
        "case_id": "synthetic_case",
        "title": "Invented roads",
        "rules": {"aoi_geometry": "a box", "routing_geometry": "a box", "reporting_geometry": "a box"},
        "routing_source": {"path": "synthetic", "sha256": "d" * 64, "geometry_sha256": "e" * 64},
        "named_ways": [100],
        "expected_hospital_ids": None,
        "reporting_units_intersecting": 1,
        "main_road_entry_definition": "The nearest node on a trunk or primary edge (including links).",
        "reviewed_junctions_supplied": 0,
    }


ACCEPTANCE = {"hospitals_in_context_min": 4, "baseline_vehicle_no_route_share_max": 0.1}
PATHS = {"join_log": "log.json", "facility_table": "<external_data_workspace>/table.json",
         "context": "<external_data_workspace>/context_inputs.json", "receipt": "receipt.json"}
DGA = [(99.0032 + 100 * LON_M, 20.0020)]  # about 100 m east of hospital A's footprint


def _assembled(tmp_path: Path, folder: str = "first") -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = read_ddpm_shelters(_ddpm_file(tmp_path))
    shelters, summary = shelter_facilities(rows, ROUTING.intersection(REPORTING), MATCH_OBJECTS)
    summary["osm_extract"] = {"note": "invented objects"}
    context = fake_build_context_inputs(tmp_path, mapping(DEMAND), mapping(ROUTING), shelters, tmp_path / folder,
                                        reporting_geometry=mapping(REPORTING))
    return assemble_outputs(
        context, case=_case(), record=True, generated_at_utc=GENERATED_AT, shelter_summary=summary,
        dga_points=DGA, inputs={"ddpm_file_sha256": "f" * 64}, paths=PATHS, acceptance=ACCEPTANCE,
        load_aois_counts={"resources/aoi": 6, "resources/aoi/upload": 6},
    ) | {"context": context}


# --- PII whitelist -------------------------------------------------------------------------------------------------

def test_pii_whitelist_keeps_no_personal_column_and_refuses_one(tmp_path: Path) -> None:
    rows = read_ddpm_shelters(_ddpm_file(tmp_path))
    shelters, _summary = shelter_facilities(rows, ROUTING.intersection(REPORTING), MATCH_OBJECTS)
    assert shelters and all(set(row) <= set(SHELTER_SOURCE_KEYS) for row in shelters)
    built = _assembled(tmp_path)
    supplied = built["context"]["facilities"]
    assert supplied and all(set(row) <= SHELTER_FACILITY_KEYS for row in supplied)
    # The coordinator's name and phone number never reach the context, the table, the receipt or the join log.
    outputs = [json.dumps(built["context"], ensure_ascii=False), built["facility_table"].decode("ascii"),
               json.dumps(built["receipt_body"]), built["join_log"].decode("ascii")]
    for text in outputs:
        assert PERSON not in text and PHONE not in text
    table = json.loads(built["facility_table"])
    for row in table["services"][DDPM_LOCATED_SHELTER]["rows"]:
        assert set(row) <= SHELTER_FACILITY_KEYS
    # The whitelist holds no personal-looking name, and the guard catches every one of these.
    assert not [key for key in SHELTER_FACILITY_KEYS if PERSONAL_FIELD.search(key)]
    for column in ("coordinator_name", "phone", "telephone", "mobile_number", "contact_person", "national_id",
                   "id_card", "email", "surname", HEADER[9], HEADER[10]):
        assert PERSONAL_FIELD.search(column), column
        with pytest.raises(PlanningContextError, match="PII whitelist"):
            assert_no_personal_fields([{**supplied[0], column: "x"}])
        # Even a whitelist that someone widened by mistake does not let it through.
        with pytest.raises(PlanningContextError, match="PII whitelist"):
            assert_no_personal_fields([{**supplied[0], column: "x"}], SHELTER_FACILITY_KEYS | {column})
    with pytest.raises(PlanningContextError, match="outside the PII whitelist: remarks"):
        assert_no_personal_fields([{**supplied[0], "remarks": "x"}])


def test_a_build_refuses_a_supplied_row_outside_the_whitelist(tmp_path: Path) -> None:
    built = _assembled(tmp_path)
    context = built["context"]
    context["facilities"][0] = {**context["facilities"][0], "coordinator_name": PERSON}
    with pytest.raises(PlanningContextError, match="PII whitelist"):
        assemble_outputs(
            context, case=_case(), record=True, generated_at_utc=GENERATED_AT,
            shelter_summary={"ddpm_rows_with_a_coordinate_in_the_routing_context": {"located_rows": 3},
                             "shelter_corroboration": {}},
            dga_points=DGA, inputs={}, paths=PATHS, acceptance=ACCEPTANCE, load_aois_counts={"resources/aoi": 6},
        )


# --- Located-shelter flag and corroboration ------------------------------------------------------------------------

def test_only_located_shelters_inside_the_routing_context_are_supplied_with_their_flag(tmp_path: Path) -> None:
    rows = read_ddpm_shelters(_ddpm_file(tmp_path))
    shelters, summary = shelter_facilities(rows, ROUTING.intersection(REPORTING), MATCH_OBJECTS)
    assert [row["facility_id"] for row in shelters] == ["DDPM-gd002-row-1", "DDPM-gd002-row-2", "DDPM-gd002-row-3"]
    for row in shelters:
        assert row["location_status"] == LOCATED
        assert row["service_type"] == DDPM_LOCATED_SHELTER and row["candidate_destination_eligible"] is True
        assert row["capacity_status"] == "listed_planned_unverified"
        assert row["label"] == "listed, operating status unverified"
        assert row["publication_level"] == "pitch"
    inside = summary["ddpm_rows_with_a_coordinate_in_the_routing_context"]
    # Rows 1-6 have a coordinate in the context; rows 4-6 share a placeholder coordinate and are not located.
    assert inside["listed_rows"] == 6 and inside["located_rows"] == 3 and inside["unlocated_rows"] == 3
    built = _assembled(tmp_path)
    assert built["receipt_body"]["facilities"]["counts"]["located_ddpm_shelters"] == 3
    assert all(row["within_routing_context"] is True for row in built["context"]["facilities"])


def test_corroboration_uses_150_m_and_says_what_matched(tmp_path: Path) -> None:
    rows = read_ddpm_shelters(_ddpm_file(tmp_path))
    shelters, summary = shelter_facilities(rows, ROUTING.intersection(REPORTING), MATCH_OBJECTS)
    flags = {row["facility_id"]: row["corroboration"] for row in shelters}
    assert flags == {"DDPM-gd002-row-1": "building", "DDPM-gd002-row-2": "amenity_only", "DDPM-gd002-row-3": "none"}
    assert all(row["corroboration_distance_m"] == 150.0 for row in shelters)
    counts = summary["shelter_corroboration"]
    assert (counts["corroborated_rows"], counts["matched_to_a_building_rows"],
            counts["matched_to_an_amenity_only_rows"]) == (2, 1, 1)

    footprint = box(99.0100, 20.0100, 99.0102, 20.0102)
    located = [
        {"source_row_number": str(number), "place_name_th": "p", "province_th": "p", "district_th": "d",
         "tambon_th": "t", "listed_places": 10.0, "location_status": LOCATED, "latitude": 20.0101,
         "longitude": 99.0102 + metres * LON_M}
        for number, metres in ((1, 140.0), (2, 160.0), (3, 0.0))
    ]
    near_far, _summary = shelter_facilities(located, ROUTING, [(frozenset({BUILDING}), footprint)])
    assert [row["corroboration"] for row in near_far] == ["building", "none", "building"]
    tight, _summary = shelter_facilities(located, ROUTING, [(frozenset({BUILDING}), footprint)], distance_m=50.0)
    assert [row["corroboration"] for row in tight] == ["none", "none", "building"]


def test_hospitals_get_the_dga_match_at_150_m() -> None:
    hospitals = [{"facility_id": "a", "source_geometry": mapping(HOSPITAL_A)}]
    edge = 99.0032
    assert dga_matches(hospitals, [(edge + 140 * LON_M, 20.0020)]) == {"a": 1}
    assert dga_matches(hospitals, [(edge + 160 * LON_M, 20.0020)]) == {"a": 0}
    assert dga_matches(hospitals, []) == {"a": 0}
    with pytest.raises(PlanningContextError):
        dga_matches(hospitals, [(edge, 20.0)], distance_m=-1.0)


# --- Grade joins, main-road entries and the receipt ------------------------------------------------------------------

def test_join_log_joins_only_identical_coordinates_at_0_m(tmp_path: Path) -> None:
    built = _assembled(tmp_path)
    log = json.loads(built["join_log"])
    assert log["coincidence_tolerance_m"] == 0.0 and log["status"] == "log_of_record"
    _edges, joins = apply_grade_joins(built["context"])
    assert log["joins"] == joins and log["join_count"] == 2
    assert sorted(join["coordinates"] for join in joins) == [[99.001, 20.0], [99.002, 20.0]]
    # Way 7 starts 1e-7 degree from way 6's end: no join there, because nearness never joins.
    assert all(join["coordinates"] != [99.004, 20.002] for join in joins)
    assert log["context_canonical_sha256"] == built["context_canonical_sha256"]
    receipt = built["receipt_body"]
    assert receipt["grade_joins"]["join_count"] == 2 and receipt["grade_joins"]["coincidence_tolerance_m"] == 0.0
    assert receipt["grade_joins"]["log_sha256"] == planning_context.sha256_bytes(built["join_log"])
    assert log["source_timestamp"] == SOURCE_TIMESTAMP and log["generated_at_utc"] == GENERATED_AT


def test_main_road_entries_are_the_nodes_of_trunk_and_primary_edges(tmp_path: Path) -> None:
    context = _assembled(tmp_path)["context"]
    entries = main_road_entries(context)
    ways = {way for row in entries for way in row["osm_way_ids"]}
    assert ways == {"1", "2", "3", "6"}  # primary, primary bridge, primary_link, trunk; never residential or tertiary
    assert len(entries) == 8 and all(row["snap_distance_m"] == 0.0 for row in entries)
    assert all(row["service_type"] == MAIN_ROAD_ENTRY for row in entries)
    joined, _joins = apply_grade_joins(context)
    assert main_road_entries({**context, "edges": joined}) == entries  # a join connector is never a main road


def test_receipt_carries_counts_acceptance_and_provenance(tmp_path: Path) -> None:
    built = _assembled(tmp_path)
    receipt = built["receipt_body"]
    for key in ("source_timestamp", "generated_at_utc", "confidence_class", "confidence_basis", "assumptions"):
        assert receipt[key]
    assert receipt["confidence_class"] == "low" and receipt["official_warning"] is False
    assert receipt["operational_status"] == "non_operational" and "run" not in receipt
    assert "FPPS" in receipt["computes"] and "no A-E class" in receipt["computes"]
    counts = receipt["facilities"]["counts"]
    assert counts == {"osm_hospitals": 2, "dga_matched_hospitals": 1, "located_ddpm_shelters": 3,
                      "corroborated_shelters": 2}
    assert receipt["facilities"]["main_road_entries"] == 8
    acceptance = receipt["acceptance"]
    assert acceptance["hospital_count"] == 2 and acceptance["criteria_met"]["hospitals_in_context_min"] is False
    assert acceptance["named_ways_within_routing_context"] == {"100": True}
    # 40 of the 200 residents snap to the cut-off bridge: a share of 0.2, over the plan's 0.1.
    assert acceptance["baseline_vehicle_no_route_share"] == 0.2
    assert acceptance["criteria_met"]["baseline_vehicle_no_route_share_max"] is False
    assert acceptance["criteria_met"]["load_aois_still_returns_6"] is True
    text = planning_context.encode_json(receipt).decode("ascii")
    assert "subdistrict_id" not in text and "place 1" not in text  # counts, not rows
    table = json.loads(built["facility_table"])
    assert table["publication_level"] == "pitch" and table["confidence_class"] == "low"
    assert {row["facility_id"]: row["dga_matched"] for row in table["services"]["hospital"]["rows"]} == {
        "OSM-node-200": False, "OSM-way-100": True}


def test_a_walking_context_reports_its_share_without_the_vehicle_criterion(tmp_path: Path) -> None:
    rows = read_ddpm_shelters(_ddpm_file(tmp_path))
    shelters, summary = shelter_facilities(rows, ROUTING.intersection(REPORTING), MATCH_OBJECTS)
    context = fake_build_context_inputs(tmp_path, mapping(DEMAND), mapping(ROUTING), shelters, tmp_path / "walk",
                                        reporting_geometry=mapping(REPORTING), travel_mode="walking")
    receipt = assemble_outputs(
        context, case=_case(), record=False, generated_at_utc=GENERATED_AT, shelter_summary=summary,
        dga_points=DGA, inputs={}, paths=PATHS, acceptance=ACCEPTANCE, load_aois_counts={"resources/aoi": 6},
    )["receipt_body"]
    assert receipt["travel_mode"] == "walking" and receipt["baseline_no_route"]["travel_mode"] == "walking"
    assert receipt["acceptance"]["criteria_met"]["baseline_vehicle_no_route_share_max"] is None
    assert receipt["acceptance"]["baseline_vehicle_no_route_share"] is None
    # Walking keeps trunk roads out unless foot is allowed, so way 6 gives no main-road entry here.
    assert receipt["facilities"]["main_road_entries"] == 6


def test_reproduction_check_names_every_difference() -> None:
    expected = {
        "source": "spike.json", "source_sha256": "0" * 64, "corridor_geometry_sha256": "1" * 64, "edge_count": 10,
        "grade_split_count": 2, "joins_sha256": "2" * 64, "join_count": 1,
        "facility_counts": {"osm_hospitals": 6, "dga_matched_hospitals": 6, "located_ddpm_shelters": 82,
                            "corroborated_shelters": 48},
        "mae_sai_hospital_facility_id": "OSM-way-1", "context_canonical_sha256": "3" * 64, "accepted_differences": [],
        "inputs": {"osm_pbf_sha256": "4" * 64},
    }
    observed = {
        "corridor_geometry_sha256": "1" * 64, "edge_count": 10, "grade_split_count": 2, "joins_sha256": "2" * 64,
        "join_count": 1, "facility_counts": dict(expected["facility_counts"]), "hospital_facility_ids": ["OSM-way-1"],
        "context_canonical_sha256": "5" * 64, "inputs": {"osm_pbf_sha256": "4" * 64},
    }
    same = reproduction_check(observed, expected, facilities_supplied=82)
    assert same["all_same"] is True and same["differences"] == []
    assert same["context_canonical_sha256"]["expected_to_differ"] is True
    observed["facility_counts"]["corroborated_shelters"] = 47
    observed["hospital_facility_ids"] = []
    different = reproduction_check(observed, expected, facilities_supplied=82)
    assert different["all_same"] is False
    assert different["differences"] == ["facility_counts.corroborated_shelters", "mae_sai_hospital_facility_id"]
    # Without supplied facilities the context must be the spike's context.
    assert "context_canonical_sha256" in reproduction_check(observed, expected, facilities_supplied=0)["differences"]


# --- Determinism, verify and load_aois -------------------------------------------------------------------------------

def test_the_same_inputs_give_the_same_bytes(tmp_path: Path) -> None:
    first = _assembled(tmp_path / "a")
    second = _assembled(tmp_path / "b")
    assert first["context_canonical_sha256"] == second["context_canonical_sha256"]
    assert first["join_log"] == second["join_log"]
    assert first["facility_table"] == second["facility_table"]
    assert planning_context.encode_json(first["receipt_body"]) == planning_context.encode_json(second["receipt_body"])
    raw = first["join_log"]
    assert b"\r" not in raw and raw.endswith(b"\n") and raw.decode("ascii")


def _script():
    spec = importlib.util.spec_from_file_location("build_planning_context", ROOT / "scripts" / "build_planning_context.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs, because its dataclasses look their module up by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _script()

    def load_case(key, boundaries, v1a, v1b):
        description = {**_case(), "case_id": module.CASE_IDS[key], "named_ways": []}
        description.pop("reviewed_junctions_supplied")
        return module.Case(key, DEMAND, ROUTING, mapping(ROUTING), REPORTING, description, {"boundaries_sha256": "9" * 64})

    def extract(pbf, bounds, target):
        target.mkdir(parents=True, exist_ok=True)
        return list(MATCH_OBJECTS), {"note": "invented objects", "bounds_wgs84": [round(value, 6) for value in bounds]}

    monkeypatch.setattr(module, "load_case", load_case)
    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(planning_context, "extract_osm_match_objects", extract)
    monkeypatch.setattr(evidence_context, "build_context_inputs", fake_build_context_inputs)
    return module


def _arguments(tmp_path: Path, *extra: str) -> list[str]:
    dga = tmp_path / "dga.geojson"
    dga.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": list(DGA[0])}}]}),
        encoding="utf-8")
    return ["--case", "se1", "--context-root", str(tmp_path / "external"), "--boundaries", str(tmp_path / "b.zip"),
            "--ddpm-shelters", str(_ddpm_file(tmp_path)), "--dga-facilities", str(dga),
            "--work-dir", str(tmp_path / "work"), *extra]


def test_build_writes_candidates_outside_git_and_verify_compares_bytes(script, tmp_path: Path, capsys) -> None:
    assert script.main(_arguments(tmp_path)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["run_kind"] == "candidate"
    candidate = tmp_path / "external" / "proposal_execution" / "planning_v1" / "se1_mae_sai" / "e4_vehicle_candidate"
    assert sorted(path.name for path in candidate.iterdir()) == [
        "context_inputs.json", "grade_join_log.json", "planning_facilities.json", "receipt.json"]
    assert not (tmp_path / "outputs").exists(), "a candidate writes nothing into Git"
    receipt = json.loads((candidate / "receipt.json").read_text(encoding="ascii"))
    assert receipt["status"] == "candidate" and receipt["run"]["compute_window"]["declared"] is False
    assert receipt["reproduction_check"]["all_same"] is False  # invented roads are not the corridor
    assert list(tmp_path.joinpath("work").iterdir()) == [], "the scratch folder is removed"

    assert script.main(_arguments(tmp_path, "--verify")) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    table = candidate / "planning_facilities.json"
    table.write_bytes(table.read_bytes().replace(b'"none"', b'"building"', 1))
    assert script.main(_arguments(tmp_path, "--verify")) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] is False and result["problems"] == ["facility_table: the rebuild differs byte for byte"]


def test_a_build_of_record_writes_to_git_and_is_never_replaced_silently(script, tmp_path: Path, capsys) -> None:
    window = "Declared by the operator for a test; nothing else ran."
    assert script.main(_arguments(tmp_path, "--compute-window", window)) == 0
    capsys.readouterr()
    receipt_path = tmp_path / "outputs" / "e4_planning_context_se1_vehicle.json"
    log_path = tmp_path / "outputs" / "grade_join_log_e4_se1_vehicle.json"
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    assert receipt["run_kind"] == "build_of_record" and receipt["status"] == "of_record"
    assert receipt["run"]["compute_window"]["declared_by_the_operator"] == window
    assert "R13" in receipt["run"]["compute_window"]["authority"] and "R13" in receipt["status_note"]
    assert "OI-04" in receipt["status_note"] and "e4_reproduction_check" in receipt["status_note"]
    log = json.loads(log_path.read_text(encoding="ascii"))
    assert log["status"] == "log_of_record" and log["generated_at_utc"] == receipt["generated_at_utc"]
    assert receipt["grade_joins"]["log_sha256"] == planning_context.sha256_file(log_path)
    assert receipt["facilities"]["facility_table"]["path"].startswith("<external_data_workspace>/proposal_execution/")
    raw = receipt_path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")

    with pytest.raises(script.BuildError, match="supersede"):
        script.main(_arguments(tmp_path, "--compute-window", window))
    assert script.main(_arguments(tmp_path, "--verify")) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["verified"] is True and verified["run_kind"] == "build_of_record"
    assert script.main(_arguments(tmp_path, "--compute-window", window, "--supersede-record", "a test rerun")) == 0
    capsys.readouterr()
    again = json.loads(receipt_path.read_text(encoding="ascii"))
    assert again["run"]["supersedes"]["reason"] == "a test rerun"
    assert receipt_body(again)["facilities"]["counts"] == receipt_body(receipt)["facilities"]["counts"]


def test_work_folders_inside_the_repository_are_refused(script, tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("--work-dir") + 1] = str(ROOT / "outputs")
    with pytest.raises(SystemExit):
        script.parse_args(arguments)


def test_load_aois_still_returns_6_and_e4_writes_nothing_under_resources_aoi(tmp_path: Path) -> None:
    module = _script()
    assert module.load_aois_counts() == {"resources/aoi": 6, "resources/aoi/upload": 6}
    case = module.Case("se1", DEMAND, ROUTING, mapping(ROUTING), REPORTING, {"case_id": "se1_mae_sai"})
    for record in (True, False):
        for mode in module.MODES:
            for path in module.output_paths(case, mode, record, tmp_path).values():
                assert "resources" not in path.parts, path
    assert module.OUTPUT_DIR == ROOT / "outputs" / "planning_v1"


def test_the_cases_read_the_files_protocol_v1b_names() -> None:
    protocol = json.loads(PROTOCOL_V1B.read_text(encoding="utf-8"))
    corridor = protocol["corridor_polygon"]
    assert planning_context.sha256_file(ROOT / corridor["geometry_file"]["path"]) == corridor["geometry_file"]["sha256"]
    frame = corridor["se2_frame"]
    assert planning_context.sha256_file(ROOT / frame["planning_frame_file"]) == frame["sha256"]
    assert planning_context.sha256_file(ROOT / frame["routing_geometry"]["path"]) == frame["routing_geometry"]["sha256"]
    assert protocol["facility_sets"]["sets"][1]["shelter_match_distance_m"] == planning_context.MATCH_DISTANCE_M
    assert protocol["grade_join_policy"]["coincidence_tolerance_m"] == 0
    expected = _script().expected_values(protocol)
    assert expected["join_count"] == 345 and expected["edge_count"] == 65328 and expected["grade_split_count"] == 371
    assert expected["joins_sha256"].startswith("d289f728")
    assert expected["facility_counts"] == {"osm_hospitals": 6, "dga_matched_hospitals": 6,
                                           "located_ddpm_shelters": 82, "corroborated_shelters": 48}


def test_the_osm_extraction_is_the_spike_s() -> None:
    """E4 must count corroborated shelters on the objects the spike counted on."""

    spike = (ROOT / "scripts" / "run_planning_context_spike.py").read_text(encoding="utf-8")
    for layer, where in OSM_MATCH_LAYERS:
        assert f'("{layer}", "{where}")' in spike
    assert "MATCH_OBJECT_MARGIN_DEG = 0.002" in spike and planning_context.MATCH_OBJECT_MARGIN_DEG == 0.002
    assert set(BUILDER_SNAP_KEYS) <= SHELTER_FACILITY_KEYS


# --- Real data, small clip -------------------------------------------------------------------------------------------

EXTERNAL = os.environ.get("FLOODGUARD_EXTERNAL_DATA")


@pytest.mark.skipif(not EXTERNAL, reason="FLOODGUARD_EXTERNAL_DATA is not set")
def test_real_builder_on_a_small_clip_keeps_the_whitelist(tmp_path: Path) -> None:
    """One build with the unchanged builder on about 4 km of Mae Sai town; invented shelters, no DGA records."""

    module = _script()
    root = Path(str(EXTERNAL))
    routing = box(99.865, 20.405, 99.900, 20.440)
    demand = box(99.870, 20.410, 99.895, 20.435)
    description = {**_case(), "case_id": "smoke_mae_sai_town", "named_ways": []}
    description.pop("reviewed_junctions_supplied")
    case = module.Case("smoke", demand, routing, mapping(routing), routing, description, {})
    rows = [
        {"source_row_number": str(number), "place_name_th": "test place", "province_th": "p", "district_th": "d",
         "tambon_th": "t", "listed_places": 50.0, "location_status": LOCATED, "latitude": latitude,
         "longitude": longitude}
        for number, (longitude, latitude) in enumerate([(99.880, 20.420), (99.885, 20.425), (99.890, 20.415)], 1)
    ]
    sources = module.Sources(rows, [], [], {})
    protocol = json.loads(PROTOCOL_V1B.read_text(encoding="utf-8"))
    paths = module.output_paths(case, "legacy_vehicle", False, tmp_path / "external")
    built = module.build(case, sources, v1b=protocol, context_root=root, scratch=tmp_path / "scratch",
                         travel_mode="legacy_vehicle", record=False, paths=paths, generated_at_utc=GENERATED_AT)
    context = json.loads(built["context_file"].read_text(encoding="utf-8"))
    assert context["canonical_sha256"] == built["context_canonical_sha256"]
    assert all(set(row) <= SHELTER_FACILITY_KEYS for row in context["facilities"])
    assert len(context["facilities"]) == 3
    receipt = built["receipt_body"]
    assert receipt["facilities"]["counts"]["located_ddpm_shelters"] == 3
    assert receipt["edge_counts"]["edges"] > 0 and receipt["source_timestamp"]
    # Assembling the same context again gives the same bytes.
    summary = {"ddpm_rows_with_a_coordinate_in_the_routing_context":
               receipt["facilities"]["ddpm_rows_with_a_coordinate_in_the_routing_context"],
               "shelter_corroboration": {key: value for key, value in
                                         receipt["facilities"]["shelter_corroboration"].items() if key != "osm_extract"},
               "osm_extract": receipt["facilities"]["shelter_corroboration"]["osm_extract"]}
    again = assemble_outputs(
        context, case={**description, "reviewed_junctions_supplied": 0}, record=False, generated_at_utc=GENERATED_AT,
        shelter_summary=summary, dga_points=[], inputs=receipt["input_hashes"],
        paths={key: receipt_path for key, receipt_path in (
            ("join_log", receipt["grade_joins"]["log_path"]), ("facility_table", receipt["facilities"]["facility_table"]["path"]),
            ("context", receipt["context"]["path"]), ("receipt", ""))},
        acceptance=protocol["corridor_polygon"]["acceptance"], load_aois_counts=receipt["acceptance"]["load_aois_counts"],
        status_notes=module.status_notes(case, "legacy_vehicle"),
    )
    assert again["join_log"] == built["join_log"] and again["facility_table"] == built["facility_table"]
    assert planning_context.encode_json(again["receipt_body"]) == planning_context.encode_json(receipt)
