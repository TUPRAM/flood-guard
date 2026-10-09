"""The runner of plan task E5 (scripts/build_access_diff.py), on an invented road network.

Every road, cell, unit, shelter and flood extent here is invented. No FPPS, no A-E class and no ensemble is
computed. The last tests read the committed receipt and table of the real run, when they are on the checkout,
and check what they say about themselves; they compute nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import pytest
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

from floodguard import access_diff, flood_inputs, normalisation, rights

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUTS = ROOT / "outputs" / "planning_v1"
V1A = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
V1B = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
ORIGIN_X, ORIGIN_Y = 590_000.0, 2_258_000.0
HASHES = {"planning_protocol_v1a": "a" * 64, "planning_protocol_v1b": "b" * 64}
UNIT_IDS = ["U1", "U2"]


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("build_access_diff", ROOT / "scripts" / "build_access_diff.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def lonlat(x_m: float, y_m: float) -> list[float]:
    longitude, latitude = TO_WGS84(ORIGIN_X + x_m, ORIGIN_Y + y_m)
    return [longitude, latitude]


def metres(geometry: Any) -> Any:
    """Shift a geometry given in metres from the invented origin into EPSG:32647."""

    return transform(lambda x, y: (x + ORIGIN_X, y + ORIGIN_Y), geometry)


NODES = {"h": (-200.0, 0.0), "m0": (0.0, 0.0), "m1": (200.0, 0.0), "r1": (200.0, 200.0), "r2": (200.0, 400.0),
         "r2b": (200.0, 400.0), "r3": (200.0, 600.0), "q": (400.0, 200.0)}
STREETS = [  # edge, from, to, road class, vehicle speed km/h
    ("s-h", "h", "m0", "secondary", 50.0), ("p0", "m0", "m1", "primary", 60.0), ("r-a", "m1", "r1", "residential", 25.0),
    ("r-b", "r1", "r2", "residential", 25.0), ("r-c", "r2b", "r3", "residential", 25.0), ("r-q", "r1", "q", "residential", 25.0),
]
CELLS = [("c1", "r1", 10.0, (200.0, 200.0)), ("c2", "r2", 20.0, (200.0, 400.0)), ("c3", "r3", 30.0, (200.0, 600.0)),
         ("c4", "q", 40.0, (400.0, 200.0)), ("c5", None, 5.0, (900.0, 100.0))]
# The flood covers all of r-b, the grade join at its north end, 10 m of r-a and of r-c, and 50 m of r-q.
FLOOD = metres(box(190.0, 190.0, 210.0, 410.0).union(box(300.0, 190.0, 340.0, 210.0)))
UNITS = [("U1", transform(lambda x, y: TO_WGS84(x + ORIGIN_X, y + ORIGIN_Y), box(-500.0, -500.0, 1500.0, 300.0))),
         ("U2", transform(lambda x, y: TO_WGS84(x + ORIGIN_X, y + ORIGIN_Y), box(-500.0, 300.0, 1500.0, 1500.0)))]


def invented_context(travel_mode: str) -> dict[str, Any]:
    """A planning context of eight nodes as ``build_context_inputs`` would write its parts."""

    edges = []
    for edge_id, start, end, road_class, speed in STREETS:
        length = 200.0
        edges.append({
            "edge_id": edge_id, "from_node": start, "to_node": end, "length_m": length, "road_class": road_class,
            "normal_minutes": length / 1000 / (5.0 if travel_mode == "walking" else speed) * 60, "osm_way_id": edge_id,
            "bridge": "no", "layer": "0", "tunnel": "no", "travel_mode": travel_mode})
    population = [
        {"population_id": identifier, "subdistrict_id": "aoi-demand-not-administrative-unit", "total_population": residents,
         "node_id": node, "snap_distance_m": None if node is None else 0.0,
         "longitude": lonlat(*centre)[0], "latitude": lonlat(*centre)[1]}
        for identifier, node, residents, centre in CELLS]
    shelter = {"service_type": "ddpm_located_shelter", "location_status": "located", "candidate_destination_eligible": True,
               "within_routing_context": True, "name": "an invented shelter name", "capacity": 100.0}
    return {
        "travel_mode": travel_mode,
        "edges": edges,
        "node_coordinates": {node: lonlat(*position) for node, position in NODES.items()},
        "population": population,
        "osm_facilities": [{"facility_id": "OSM-way-1", "service_type": "hospital", "candidate_destination_eligible": True,
                            "within_routing_context": True, "node_id": "h", "snap_distance_m": 0.0, "name": "invented hospital"}],
        "facilities": [{**shelter, "facility_id": "DDPM-gd002-row-1", "node_id": "r3", "snap_distance_m": 10.0},
                       {**shelter, "facility_id": "DDPM-gd002-row-2", "node_id": "m0", "snap_distance_m": 0.0},
                       {**shelter, "facility_id": "DDPM-gd002-row-3", "node_id": "q", "snap_distance_m": 0.0,
                        "location_status": "location_unverified"}],
        "connectivity_review": {"review_candidates": [{
            "coordinates": lonlat(200.0, 400.0),
            "nodes": [{"node_id": "r2", "grade": ["0", "no", "no"], "way_ids": ["r-b"], "endpoint_way_ids": ["r-b"]},
                      {"node_id": "r2b", "grade": ["1", "yes", "no"], "way_ids": ["r-c"], "endpoint_way_ids": ["r-c"]}]}]},
    }


@pytest.fixture(scope="module")
def world() -> dict[str, Any]:
    services = access_diff.service_rules(V1A, V1B)
    graphs = {"vehicle": runner.mode_graph("vehicle", invented_context("legacy_vehicle")),
              "walking": runner.mode_graph("walking", invented_context("walking"))}
    baselines = {mode: runner.baseline_runs(graph, services) for mode, graph in graphs.items()}
    population = graphs["vehicle"].population
    cells = access_diff.demand_cells(population, access_diff.assign_cells(population, UNITS))
    computed = runner.case_runs("INVENTED", "invented_input", {"as_provided": FLOOD}, graphs, baselines, services,
                                access_diff.closure_arguments(V1B), cells, UNIT_IDS)
    return {"services": services, "graphs": graphs, "baselines": baselines, "cells": cells, "computed": computed}


def test_a_mode_graph_carries_the_joins_and_only_what_a_route_needs_of_a_destination(world: dict[str, Any]) -> None:
    vehicle, walking = world["graphs"]["vehicle"], world["graphs"]["walking"]

    assert vehicle.record["grade_join_connectors"] == 1 and vehicle.record["context_edges"] == 6
    assert vehicle.record["destinations"] == {"hospital": 1, "main_road_entry": 2, "ddpm_located_shelter": 2}
    assert sorted(row["node_id"] for row in vehicle.destinations["main_road_entry"]) == ["m0", "m1"]
    assert [row["facility_id"] for row in walking.destinations["ddpm_located_shelter"]] == ["DDPM-gd002-row-1", "DDPM-gd002-row-2"], (
        "a row whose location is not verified is not a destination")
    for rows in walking.destinations.values():
        assert all(set(row) == {"facility_id", "node_id", "snap_distance_m"} for row in rows), "no name leaves the context"
    with pytest.raises(runner.BuildError, match="travel mode walking"):
        runner.mode_graph("walking", invented_context("legacy_vehicle"))


def test_each_closure_level_gives_a_baseline_run_a_flooded_run_and_a_table(world: dict[str, Any]) -> None:
    runs = {run["closure_level"]: run for run in world["computed"]["runs"]}

    assert list(runs) == ["strict", "central", "permissive"]
    assert all(run["flood_level"] == "as_provided" and run["closure_basis"] == "modelled_from_invented_input" for run in runs.values())
    strict, central, permissive = (runs[level]["closure"]["vehicle"] for level in ("strict", "central", "permissive"))
    assert (strict["closed_edges"], strict["delayed_edges"], strict["intersected_edges"]) == (1, 1, 4)
    assert strict["largest_travel_time_factor"] == pytest.approx(1.5), "50 m of 200 m inside, k = 2"
    assert (central["closed_edges"], central["delayed_edges"], central["intersected_edges_left_open"]) == (2, 0, 2)
    assert (permissive["closed_edges"], permissive["delayed_edges"]) == (4, 0)
    assert strict["connectors_with_their_coordinate_inside_the_extent"] == 1, "the join has no length and is never closed"
    assert strict["entries_with_every_main_road_edge_closed"] == 0 and strict["main_road_entries"] == 2

    def unit(level: str, unit_id: str, table: str = "public_services") -> dict[str, Any]:
        return next(row for row in runs[level][table]["units"] if row["unit_id"] == unit_id)

    # Strict: r-b is closed, so the 50 residents of U2 lose every route; r-q is only slowed.
    assert unit("strict", "U2")["access_gap_inputs"]["hospital"] == {
        "mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 50.0, "newly_lost_residents": 50.0}
    assert unit("strict", "U2")["road_criticality_inputs"] == {"residents_losing_all_routes": 50.0, "residents_with_baseline_route": 50.0}
    assert unit("strict", "U1")["access_gap_inputs"]["main_road_entry"]["newly_lost_residents"] == 0.0
    assert unit("strict", "U1")["access"]["hospital"]["residents_not_connected_to_the_graph"] == 5.0
    # Central: r-q closes at 50 m, so the 40 residents of the side street are lost too.
    assert unit("central", "U1")["access_gap_inputs"]["hospital"]["newly_lost_residents"] == 40.0
    assert unit("central", "U1")["access"]["hospital"]["thresholds_minutes"]["30"] == {
        "baseline_access_residents": 50.0, "flooded_access_residents": 10.0, "newly_lost_residents": 40.0,
        "newly_gained_residents": 0.0, "baseline_access_unavailable_reason": None}
    assert unit("central", "U1")["routes"]["residents_losing_all_routes"] == 40.0
    assert unit("permissive", "U2")["routes"] == {
        "services": ["hospital", "main_road_entry"], "residents_with_baseline_route": 50.0, "residents_losing_all_routes": 50.0,
        "connected_residents_without_a_baseline_route": 0.0, "baseline_route_unavailable_reason": None}

    for run in runs.values():
        assert set(run["public_services"]["units"][0]["access"]) == {"hospital", "main_road_entry"}
        assert set(run["pitch_services"]["units"][0]["access"]) == {"hospital", "main_road_entry", "ddpm_located_shelter"}
        assert run["public_services"]["whole_frame"]["residents"] == 105.0
    # Walking to a shelter: under strict the residents north of the closed street still reach the shelter at r3.
    shelter = unit("strict", "U2", "pitch_services")["access_gap_inputs"]["ddpm_located_shelter"]
    assert shelter == {"mode": "walking", "threshold_minutes": 30, "baseline_access_residents": 50.0, "newly_lost_residents": 0.0}
    assert unit("central", "U1", "pitch_services")["access_gap_inputs"]["ddpm_located_shelter"]["newly_lost_residents"] == 40.0
    assert runs["central"]["closure_walking"]["closed_edges"] == 2


def test_the_runs_are_checked_against_calculate_total_access_and_never_gain(world: dict[str, Any]) -> None:
    checks = world["computed"]["checks"]

    assert len(checks["reference"]) == 1 and checks["reference"][0]["closure_level"] == "permissive"
    assert checks["reference"][0]["same"] is True and checks["reference"][0]["baseline_run"]["cells_compared"] == 4
    assert checks["shorter_routes_in_a_flooded_run"] == 0 and checks["residents_gaining_access"] == 0.0
    assert {key for key in world["computed"]["timing_seconds"] if "edge_intersections" in key} == {
        "as_provided_edge_intersections_vehicle", "as_provided_edge_intersections_walking"}


def _flood_record(level: str) -> dict[str, Any]:
    return {
        "case_id": "INVENTED", "input_id": "invented_input", "input_name": "an invented layer", "lane": "SCN-ENV", "tier": "T1",
        "temporal_relation": "season_window", "case_reference_date": None, "source_timestamp": "2024-08-01/2024-10-12",
        "label": None, "field_validation": 0, "source": {"layer": "INVENTED_LAYER"},
        "rights": {
            "licence": {"name": "CC BY-SA 4.0", "full_name": "Creative Commons Attribution-ShareAlike 4.0 International",
                        "spdx_id": "CC-BY-SA-4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "legal_code_url": "https://creativecommons.org/licenses/by-sa/4.0/legalcode"},
            "attribution": "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009", "share_alike": "shared alike, in its own file",
            "record_path": "docs/proposal_execution/rights_basis_4009_v1.json", "record_sha256": "c" * 64,
            "record_status": "confirmed", "confirmed_by": ["an owner"], "confirmed_on": "2026-10-02",
            "rights_level": level, "rights_level_basis": "an invented basis"},
    }


def _table(world: dict[str, Any], service_set: str, level: str, walking_status: str = "candidate") -> dict[str, Any]:
    contexts = {
        "vehicle": {"status": "of_record", "run_kind": "build_of_record", "path": "<external_data_workspace>/v", "canonical_sha256": "d" * 64,
                    "osm_retrieved_at_utc": "2026-07-10T02:46:49Z", "ddpm_list_file_dated": "2026-09-21"},
        "walking": {"status": walking_status, "run_kind": "candidate", "path": "<external_data_workspace>/w", "canonical_sha256": "e" * 64},
    }
    return runner.table_document(
        "INVENTED", service_set, level, generated_at_utc="2026-10-04T14:00:00Z", receipt_label="outputs/planning_v1/receipt.json",
        record=_flood_record("public"), rules=flood_inputs.rules_from_protocols(V1A, V1B), hashes=HASHES,
        services=world["services"], runs=world["computed"]["runs"], contexts=contexts, vehicle_context=contexts["vehicle"],
        flood_files={"as_provided": {"path": "<external_data_workspace>/layer.geojson", "sha256": "f" * 64, "bytes": 1}},
        units={"valid_on": ["2022-01-22"]}, unit_ids=UNIT_IDS, arguments=access_diff.closure_arguments(V1B),
        notice_label="docs/proposal_execution/rights_basis_4009_v1_NOTICE.txt")


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _keys(child)}
    return set()


COUNT_KEYS = {"residents", "demand_cells", "residents_connected_to_the_graph", "residents_not_connected_to_the_graph",
              "residents_with_a_baseline_route", "residents_with_a_route_in_the_flooded_run", "baseline_access_residents",
              "flooded_access_residents", "newly_lost_residents", "newly_gained_residents", "residents_with_baseline_route",
              "residents_losing_all_routes", "connected_residents_without_a_baseline_route"}
PARAMETER_KEYS = {"access_gap_threshold_minutes", "threshold_minutes"}
"""The only keys of a unit row that hold a number: counts of residents or cells, and the thresholds of the services."""


def _numbers(value: Any, key: str = "") -> list[tuple[str, float]]:
    """Every number of a row with the key it sits under."""

    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, (int, float)):
        return [(key, float(value))]
    if isinstance(value, dict):
        return [pair for name, child in value.items() for pair in _numbers(child, name)]
    return [pair for child in value for pair in _numbers(child, key)]


def _holds(row: Any, value: float) -> bool:
    return any(math.isclose(number, value, rel_tol=1e-9, abs_tol=1e-12) for _key, number in _numbers(row))


def _rows(runs: Any) -> list[dict[str, Any]]:
    return [row for run in runs for row in (*run["units"], run["whole_frame"])]


def assert_counts_only(runs: Any) -> None:
    """Every number of every row is a count or a threshold: no ratio of two counts is written, under any name."""

    for row in _rows(runs):
        for key, number in _numbers(row):
            assert key in COUNT_KEYS | PARAMETER_KEYS, f"{key} holds a number and is neither a count nor a threshold"
            assert number >= 0 and (key not in PARAMETER_KEYS or number in (15.0, 30.0, 60.0))
        routes = row["road_criticality_inputs"]
        assert routes["residents_losing_all_routes"] <= routes["residents_with_baseline_route"] <= row["residents"] + 1e-6
        for service in row["access"].values():
            for at_threshold in service["thresholds_minutes"].values():
                assert at_threshold["newly_lost_residents"] <= at_threshold["baseline_access_residents"], "EQ-04"
                assert (at_threshold["baseline_access_unavailable_reason"] == access_diff.NO_BASELINE_ACCESS) is (
                    at_threshold["baseline_access_residents"] == 0)


def test_no_value_in_a_table_of_the_runner_equals_a_component_of_the_same_inputs(world: dict[str, Any]) -> None:
    """On the invented network: no row of a table holds a ratio of its counts, so none holds a component / 100.

    In this network every resident who loses access loses every route, so the newly-lost share of a service, the
    route ratio and both components divided by 100 are one number in several rows (0.8 in U1 at the central
    level). A table that held any ratio of its counts would hold the component. The resident counts of this
    network are small whole numbers (50 residents, a component of 50), so the component itself is compared in
    tests/test_access_diff.py, on a unit whose figures are all different.
    """

    frame = normalisation.load_planning_frame(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json",
                                              DOCS / "RECEIPTS.jsonl")
    compared = 0
    for service_set, level in (("public_services", "public"), ("pitch_services", "pitch")):
        table = _table(world, service_set, level)
        assert_counts_only(table["runs"])
        for row in _rows(table["runs"]):
            if row["road_criticality_inputs_unavailable_reason"] is None:
                component = normalisation.road_criticality(frame, **row["road_criticality_inputs"])["value_0_100"]
                if 0 < component < 100:
                    assert not _holds(row, component / 100), "the road-criticality component divided by 100"
                    compared += 1
            if row["access_gap_inputs_unavailable_reason"] is None:
                gap = normalisation.access_gap(frame, services=row["access_gap_inputs"])
                assert gap["publication_level"] == level
                for value in (gap["value_0_100"], *(100 * service["newly_lost_share"] for service in gap["services"]
                                                    if service["newly_lost_share"] is not None)):
                    if 0 < value < 100:
                        assert not _holds(row, value / 100), "the access gap divided by 100, or a service's share"
                        compared += 1
    assert compared >= 12, "the invented network has rows whose components are neither 0 nor 100"
    central_u1 = next(row for row in world["computed"]["runs"][1]["public_services"]["units"] if row["unit_id"] == "U1")
    assert normalisation.road_criticality(frame, **central_u1["road_criticality_inputs"])["value_0_100"] == pytest.approx(80.0)
    assert not _holds(central_u1, 0.8) and not _holds(central_u1, 80.0)
    # The check can fail: the same row with the route ratio in it, under any name, is caught.
    assert _holds({**central_u1, "routes": {**central_u1["routes"], "any_name": 40.0 / 50.0}}, 0.8)


def test_a_table_says_what_it_is_and_carries_its_licence_credit_and_change_notice(world: dict[str, Any]) -> None:
    table = _table(world, "public_services", "public")
    text = runner.encode(table).decode("ascii")

    assert text.endswith("\n") and "\r" not in text
    assert table["schema_version"] == access_diff.UNIT_TABLE_SCHEMA == "floodguard.access_diff_units.v2"
    assert table["status"] == "unit_inputs" and table["usable_by_task_e8"] is True
    assert table["official_warning"] is False and table["operational_status"] == "non_operational"
    assert table["can_feed_decision_layer"] is False and table["confidence_class"] == "low"
    assert table["source_timestamp"] and table["confidence_basis"] and table["assumptions"] and table["limitations"]
    assert table["protocol_sha256"] == HASHES
    assert "not the components and not an FPPS" in table["status_note"]
    licence = table["licence"]
    assert licence["name"] == "CC BY-SA 4.0" and licence["spdx_id"] == "CC-BY-SA-4.0"
    assert licence["credit"] == "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
    assert licence["change_notice"].startswith("Changed by FloodGuard:") and "INVENTED_LAYER" in licence["change_notice"]
    assert "FloodGuard did not validate it" in licence["standard_sentence"]
    assert licence["rights_record"]["record_status"] == "confirmed" and licence["publication_level"] == "public"
    assert {row["id"] for row in licence["other_inputs"]} == {"osm", "worldpop-2020", "cod-ab"}
    assert [run["closure_level"] for run in table["runs"]] == ["strict", "central", "permissive"]
    assert all(run["closure_basis"] == "modelled_from_invented_input" for run in table["runs"])
    assert [row["unit_id"] for row in table["runs"][0]["units"]] == UNIT_IDS
    assert [point["id"] for point in table["open_points"]][:2] == ["E5-OP1", "E5-OP2"]
    # Inputs only: counts of residents, and no component value, no ratio, no score and no class anywhere in the table.
    assert_counts_only(table["runs"])
    assert not {key for key in _keys(table["runs"]) if "share" in key or "ratio" in key}
    assert not {key for key in _keys(table) if key.endswith("_0_100") or "fpps" in key.lower() or "action_class" in key}
    assert "access-gap component (0-100)" in table["not_computed"] and "FPPS" in table["not_computed"]
    assert any("road-criticality component divided by 100" in line for line in table["not_computed"])
    # The table says how close its counts are to the two components.
    definitions = table["definitions"]
    assert "100 x their ratio" in definitions["road_criticality_inputs"] and "not written here" in definitions["road_criticality_inputs"]
    assert "No ratio of two counts is written" in definitions["counts_only"] and "E5-OP8" in definitions["counts_only"]
    assert [point["id"] for point in table["open_points"]][-1] == "E5-OP8"


def test_the_public_table_holds_nothing_of_the_pitch_level_shelter_service(world: dict[str, Any]) -> None:
    public = runner.encode(_table(world, "public_services", "public")).decode("ascii")
    pitch = _table(world, "pitch_services", "pitch")

    document = json.loads(public)
    figures = json.dumps([document["runs"], document["services"], document["contexts"], document["licence"],
                          document["source_timestamps"], document["flood_input"]]).lower()
    assert "ddpm" not in figures and "shelter" not in figures and "walking" not in figures
    assert "walking" not in document["contexts"] and "walking" not in document["runs"][0]["closure"]
    assert [rule["service"] for rule in document["services"]] == ["hospital", "main_road_entry"]

    assert [rule["service"] for rule in pitch["services"]] == ["hospital", "main_road_entry", "ddpm_located_shelter"]
    assert pitch["status"] == "unit_inputs_candidate_walking_context" and "E5-OP5" in pitch["status_note"]
    # A table that rests on a candidate walking context says that task E8 may not use it.
    assert pitch["usable_by_task_e8"] is False and "not usable by task E8" in pitch["status_note"]
    assert "candidate" in pitch["usable_by_task_e8_basis"]
    assert pitch["contexts"]["walking"]["status"] == "candidate" and "walking" in pitch["runs"][0]["closure"]
    assert "ddpm-shelters" in {row["id"] for row in pitch["licence"]["other_inputs"]}
    assert "invented shelter name" not in runner.encode(pitch).decode("ascii"), "no shelter is named"
    of_record = _table(world, "pitch_services", "pitch", walking_status="of_record")
    assert of_record["status"] == "unit_inputs" and of_record["usable_by_task_e8"] is True


def test_the_receipt_summary_is_for_the_whole_frame_only(world: dict[str, Any]) -> None:
    summary = runner.whole_frame_summary(world["computed"]["runs"])

    assert [row["closure_level"] for row in summary] == ["strict", "central", "permissive"]
    text = json.dumps(summary)
    assert "U1" not in text and "U2" not in text and "ddpm_located_shelter" not in text and "closure_walking" not in text
    assert summary[1]["access_gap_inputs"]["hospital"]["newly_lost_residents"] == 90.0
    assert summary[1]["road_criticality_inputs"] == {"residents_losing_all_routes": 90.0, "residents_with_baseline_route": 100.0}


def test_a_main_road_entry_whose_main_road_edges_are_all_closed_is_counted(world: dict[str, Any]) -> None:
    graph = world["graphs"]["vehicle"]

    assert runner.entry_state(graph, {"p0"}) == {
        "main_road_entries": 2, "entries_with_every_main_road_edge_closed": 2, "entries_with_every_edge_closed": 0}
    assert runner.entry_state(graph, {"p0", "r-a"})["entries_with_every_edge_closed"] == 1


def test_the_walking_context_of_record_is_preferred_and_a_missing_one_is_none(tmp_path: Path) -> None:
    base = tmp_path / "proposal_execution" / "planning_v1" / "se1_mae_sai"
    assert runner.find_walking_context(tmp_path, "se1_mae_sai", None) is None
    for name in ("e4_walking_candidate", "e4_walking"):
        (base / name).mkdir(parents=True)
        (base / name / "context_inputs.json").write_text("{}", encoding="ascii")
        assert runner.find_walking_context(tmp_path, "se1_mae_sai", None) == base / name / "context_inputs.json"
    given = tmp_path / "other.json"
    assert runner.find_walking_context(tmp_path, "se1_mae_sai", given) == given


def _walking_build(tmp_path: Path, **run_changes: Any) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """An invented candidate walking build on disk: its files, the record the runner makes of it and its receipt."""

    external = tmp_path / "external"
    folder = external / "proposal_execution" / "planning_v1" / "se1_mae_sai" / "e4_walking_candidate"
    folder.mkdir(parents=True)
    label = "<external_data_workspace>/proposal_execution/planning_v1/se1_mae_sai/e4_walking_candidate"
    (folder / "planning_facilities.json").write_bytes(b"an invented facility table\n")
    (folder / "grade_join_log.json").write_bytes(b"an invented join log\n")
    receipt = {
        "generated_at_utc": "2026-10-04T13:09:29Z", "case": "se1_mae_sai", "travel_mode": "walking", "run_kind": "candidate",
        "computes": "One baseline context. No flood layer, no closure, no access loss.",
        "source_timestamp": "2026-07-10T02:46:49Z", "source_timestamps": {"osm_retrieved_at_utc": "2026-07-10T02:46:49Z"},
        "confidence_class": "low", "confidence_basis": "Unverified map and list records.",
        "context_call": {"travel_mode": "walking", "facilities_supplied": 2},
        "routing_source": {"path": "outputs/planning_v1/corridor_of_record.geojson", "sha256": "1" * 64},
        "context": {"edges": 6, "road_nodes": 8, "population_cells": 5},
        "grade_joins": {"join_count": 1, "joins_sha256": "2" * 64, "log_path": f"{label}/grade_join_log.json",
                        "log_sha256": hashlib.sha256(b"an invented join log\n").hexdigest()},
        "facilities": {"supplied_shelters_snapped_within_100_m": 2,
                       "facility_table": {"path": f"{label}/planning_facilities.json",
                                          "sha256": hashlib.sha256(b"an invented facility table\n").hexdigest()}},
        "input_hashes": {"osm_pbf_sha256": "3" * 64, "worldpop_2020_sha256": "4" * 64},
        "assumptions": ["An invented build."], "limitations": ["One build on one machine."],
        "run": {"run_started_at_utc": "2026-10-04T13:07:10Z", "run_finished_at_utc": "2026-10-04T13:09:33Z", "wall_time_minutes": 2.38,
                "compute_window": {"plan_rule": "Builds run serially in a declared compute window.", "declared": False,
                                   "declared_by_the_operator": None, "authority": None},
                "implementation": {"builder_sha256": "5" * 64}, "protocol_v1b_sha256_at_build": HASHES["planning_protocol_v1b"],
                **run_changes},
    }
    record = {"status": "candidate", "usable_by_task_e8": False, "receipt_in_git": False, "path": f"{label}/context_inputs.json",
              "file_sha256": "6" * 64, "canonical_sha256": "7" * 64,
              "receipt": {"path": f"{label}/receipt.json", "sha256": "8" * 64, "bytes": 100}}
    return record, receipt, external


def test_a_candidate_walking_build_is_reported_in_git_by_the_run_that_uses_it(tmp_path: Path) -> None:
    """Every run on real units is reported in outputs/planning_v1: the E4 builder keeps a candidate's receipt outside Git."""

    record, receipt, external = _walking_build(tmp_path)
    report = runner.walking_context_report(record, receipt, generated_at_utc="2026-10-04T16:00:00Z", hashes=HASHES,
                                           receipt_label="outputs/planning_v1/e5_access_diff_mae_sai.json", external=external)

    assert report["schema_version"] == "floodguard.walking_context_run_report.v1"
    # What the run register asks of a registered file: a generation time and the SHA-256 of both protocol files.
    assert report["generated_at_utc"] == "2026-10-04T16:00:00Z" and report["protocol_sha256"] == HASHES
    assert report["status"] == "candidate_context_build_reported_after_the_fact" and report["usable_by_task_e8"] is False
    for words in ("written after the build", "none was declared", "outside what plan row E5 names", "E5-OP5"):
        assert words in report["status_note"], words
    assert report["compute_window"]["declared"] is False and report["parameters"]["run_kind"] == "candidate"
    assert report["timestamps"]["build_started_at_utc"] == "2026-10-04T13:07:10Z"
    assert report["timestamps"]["build_finished_at_utc"] == "2026-10-04T13:09:33Z"
    assert report["inputs"]["files_sha256"] == receipt["input_hashes"]
    assert [(entry["what"], len(entry["sha256"])) for entry in report["outputs"]] == [
        ("context", 64), ("build_receipt", 64), ("facility_table", 64), ("grade_join_log", 64)]
    assert report["outputs"][1]["sha256"] == "8" * 64 and report["outputs"][0]["canonical_sha256"] == "7" * 64
    assert all(entry["path"].startswith("<external_data_workspace>/") for entry in report["outputs"])
    assert report["official_warning"] is False and report["confidence_class"] == "low" and report["assumptions"]
    assert report["source_timestamp"] == "2026-07-10T02:46:49Z" and str(tmp_path) not in json.dumps(report)
    assert runner.encode(report) == runner.encode(runner.walking_context_report(
        record, receipt, generated_at_utc="2026-10-04T16:00:00Z", hashes=HASHES,
        receipt_label="outputs/planning_v1/e5_access_diff_mae_sai.json", external=external)), "the report follows from its inputs"

    # A file the build receipt names must be on disk as the bytes it names.
    log = external / "proposal_execution" / "planning_v1" / "se1_mae_sai" / "e4_walking_candidate" / "grade_join_log.json"
    log.write_bytes(b"another join log\n")
    with pytest.raises(runner.BuildError, match="grade join log of the walking build is missing or is not the file"):
        runner.walking_context_report(record, receipt, generated_at_utc="t", hashes=HASHES, receipt_label="r", external=external)
    other_record, other_receipt, other_external = _walking_build(tmp_path / "other", protocol_v1b_sha256_at_build="9" * 64)
    with pytest.raises(runner.BuildError, match="built under another protocol v1b"):
        runner.walking_context_report(other_record, other_receipt, generated_at_utc="t", hashes=HASHES, receipt_label="r",
                                      external=other_external)


def test_a_second_run_needs_a_reason_and_a_replacement_needs_a_receipt(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="existing receipt"):
        runner.run("mae_sai", tmp_path, tmp_path / "none.gdb.zip", output_dir=output_dir, register_dir=output_dir / "run_register",
                   replace_reason="a reason")
    runner.receipt_path_for("mae_sai", output_dir).write_text("{}", encoding="ascii")
    with pytest.raises(FileExistsError, match="--replace --reason"):
        runner.run("mae_sai", tmp_path, tmp_path / "none.gdb.zip", output_dir=output_dir, register_dir=output_dir / "run_register")
    with pytest.raises(SystemExit):
        runner.main(["--frame", "mae_sai", "--external-data", str(tmp_path), "--replace"])
    with pytest.raises(runner.BuildError, match="not a path under the external data root"):
        runner.external_path("outputs/planning_v1/x.json", tmp_path)


def test_the_run_history_keeps_the_files_of_a_run_whose_receipt_was_never_committed() -> None:
    """A receipt replaced before it is committed leaves only what the next one says of it: that is carried forward."""

    first = {"generated_at_utc": "t1", "receipt_sha256": "a" * 64, "reason": "the first reason", "figures_same": True,
             "outputs_of_the_superseded_run": {"outputs/planning_v1/table.json": "1" * 64}}
    assert runner.earlier_runs({}, first) == [{
        "generated_at_utc": "t1", "receipt_sha256": "a" * 64, "superseded_because": "the first reason",
        "figures_same_as_the_run_that_replaced_it": True, "outputs_sha256": {"outputs/planning_v1/table.json": "1" * 64}}]
    # The second receipt named the files of the first in its supersedes block only, and its history entry had none.
    second_receipt = {"run_history": [{"generated_at_utc": "t1", "receipt_sha256": "a" * 64, "superseded_because": "the first reason",
                                       "figures_same_as_the_run_that_replaced_it": True}],
                      "supersedes": first}
    second = {"generated_at_utc": "t2", "receipt_sha256": "b" * 64, "reason": "the second reason", "figures_same": True,
              "outputs_of_the_superseded_run": {"outputs/planning_v1/table.json": "2" * 64}}
    history = runner.earlier_runs(second_receipt, second)
    assert [entry["receipt_sha256"] for entry in history] == ["a" * 64, "b" * 64]
    assert [entry["outputs_sha256"]["outputs/planning_v1/table.json"] for entry in history] == ["1" * 64, "2" * 64]
    assert "outputs_sha256" not in second_receipt["run_history"][0], "the receipt that is read is not changed"


RECEIPT = OUTPUTS / "e5_access_diff_mae_sai.json"


def _committed_receipt() -> dict[str, Any]:
    if not RECEIPT.is_file():
        pytest.skip("the E5 run has not been made on this checkout")
    return json.loads(RECEIPT.read_text(encoding="ascii"))


def test_the_committed_receipt_reports_the_run_and_binds_its_tables() -> None:
    receipt = _committed_receipt()
    register = OUTPUTS / "run_register"

    assert receipt["schema_version"] == runner.RECEIPT_SCHEMA and receipt["status"] == "run_receipt"
    assert receipt["protocol_state"] == {"v1a": "in_force", "v1b": "in_force"}
    assert receipt["parameters"]["flood_levels_run"] == ["as_provided"]
    assert receipt["parameters"]["closure_rule"]["levels"] == ["strict", "central", "permissive"]
    assert receipt["inputs"]["planning_context_vehicle"]["canonical_sha256"] == V1B["corridor_polygon"]["e4_build_of_record"][
        "context_canonical_sha256"]
    assert receipt["checks"]["e4_baseline"]["same"] is True
    assert receipt["checks"]["against_calculate_total_access_all_same"] is True
    assert receipt["checks"]["shorter_routes_in_a_flooded_run"] == 0 and receipt["checks"]["residents_gaining_access"] == 0.0
    assert receipt["timestamps"]["run_started_at_utc"] <= receipt["timestamps"]["run_finished_at_utc"]
    assert receipt["rights"]["written_under_apps_web_public"] is False
    entry = json.loads((register / RECEIPT.name).read_text(encoding="ascii"))
    assert entry == {"path": RECEIPT.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(RECEIPT.read_bytes()).hexdigest()}
    for case_id, group in receipt["outputs"].items():
        if case_id == runner.WALKING_CONTEXT_OUTPUTS:
            continue
        levels = receipt["rights"]["publication_level"][case_id]
        for row in group["files"]:
            if row["what"] != "unit_table":
                continue
            assert row["publication_level"] == levels[row["service_set"]]
            assert row["in_git"] is (row["publication_level"] == "public"), "only a table with a public lineage is in Git"
            if row["in_git"]:
                path = ROOT / row["path"]
                assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
                registered = json.loads((register / path.name).read_text(encoding="ascii"))
                assert registered == {"path": row["path"], "sha256": row["sha256"]}
            else:
                assert row["path"].startswith("<external_data_workspace>/")
    # Whole-frame figures only, and nothing of the pitch-level shelter service.
    results = json.dumps(receipt["results"])
    assert "TH57" not in results and "ddpm_located_shelter" not in results
    for case in receipt["results"].values():
        assert [run["closure_level"] for run in case["runs"]] == ["strict", "central", "permissive"]
        closed = [run["closure"]["vehicle"]["closed_edges"] for run in case["runs"]]
        assert closed == sorted(closed), "strict closes the fewest edges and permissive the most"
    assert not {key for key in _keys(receipt) if key.endswith("_0_100") or "fpps" in key.lower() or "action_class" in key}
    # Whole-frame counts only: no ratio of two counts is in the results either.
    assert not {key for key in _keys(receipt["results"]) if "share" in key or "ratio" in key}
    for case in receipt["results"].values():
        for run in case["runs"]:
            assert {key for key, _number in _numbers({name: run[name] for name in ("residents", "access_gap_inputs", "road_criticality_inputs",
                                                                                 "residents_not_connected_to_the_graph", "cells_in_no_unit")})
                    } <= COUNT_KEYS | PARAMETER_KEYS | {"hospital", "main_road_entry"}


def test_the_committed_receipt_names_the_first_table_which_held_the_route_ratio() -> None:
    """The first table of this task held the road-criticality component / 100. The receipt that replaced it says so."""

    receipt = _committed_receipt()
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["figures_same"] is True
    first = receipt["run_history"][0]
    assert first["generated_at_utc"] == "2026-10-04T13:24:17Z" and first["figures_same_as_the_run_that_replaced_it"] is True
    for words in ("share_losing_all_routes", "road-criticality component of protocol v1a divided by 100", "counts of residents only"):
        assert words in first["superseded_because"], words
    table = "outputs/planning_v1/e5_access_diff_se1_mae_sai_public_services.json"
    # The first table is named by the SHA-256 it had in commit 233385e; the table here is another file.
    assert first["outputs_sha256"][table] == "e8d0166dc6f5a33be98661c42483ae80f6e8e347d7e5e88bbfa7c25786f46b3d"
    assert hashlib.sha256((ROOT / table).read_bytes()).hexdigest() != first["outputs_sha256"][table]
    assert all(len(entry["receipt_sha256"]) == 64 and entry["outputs_sha256"] for entry in receipt["run_history"])
    assert receipt["supersedes"]["receipt_sha256"] == receipt["run_history"][-1]["receipt_sha256"]


def test_the_committed_receipt_says_which_of_its_figures_come_from_a_local_level_layer() -> None:
    """GR6 speaks of apps/web/public only; whether a local level allows a figure in Git is for the owners (E1-OP1)."""

    receipt = _committed_receipt()
    assert receipt["rights"]["levels_and_git"] == rights.LEVELS_AND_GIT
    listed = receipt["rights"]["figures_of_local_level_layers_in_this_receipt"]
    local = [case_id for case_id, levels in receipt["rights"]["publication_level"].items() if levels["flood_input"] != "public"]
    assert [row["case_id"] for row in listed["figures"]] == sorted(local, key=receipt["parameters"]["cases"].index) == ["O2"]
    assert listed["figures"][0]["where"] == "results.O2" and "E1-OP1" in listed["for_the_owners"]
    # The lineage of a table is the extent it reads: the extent states the level the registry gives its layer.
    for case_id, flood in receipt["inputs"]["flood_inputs"].items():
        assert {entry["rights_level"] for entry in flood["extents"].values()} == {flood["rights_level"]}, case_id


def test_the_committed_run_reports_the_candidate_walking_build_and_marks_its_tables() -> None:
    """The walking build this lane made is reported in Git and registered; its tables are not inputs of task E8."""

    receipt = _committed_receipt()
    walking = receipt["inputs"]["planning_context_walking"]
    if walking is None:
        pytest.skip("the committed run computed no shelter service")
    shelter = receipt["shelter_service"]
    assert walking["status"] == "candidate" and walking["compute_window_declared"] is False and walking["receipt_in_git"] is False
    assert shelter["usable_by_task_e8"] is walking["usable_by_task_e8"] is False and "not usable by task E8" in shelter["note"]
    group = receipt["outputs"][runner.WALKING_CONTEXT_OUTPUTS]["files"]
    assert [row["what"] for row in group] == ["context_run_report"] and group[0]["path"] == shelter["context_run_report"]
    path = ROOT / group[0]["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == group[0]["sha256"]
    registered = json.loads((OUTPUTS / "run_register" / path.name).read_text(encoding="ascii"))
    assert registered == {"path": group[0]["path"], "sha256": group[0]["sha256"]}
    report = json.loads(path.read_text(encoding="ascii"))
    assert report["generated_at_utc"] == receipt["generated_at_utc"] and report["protocol_sha256"] == receipt["protocol_sha256"]
    assert report["receipt_file"] == RECEIPT.relative_to(ROOT).as_posix() and report["usable_by_task_e8"] is False
    assert report["compute_window"]["declared"] is False and report["parameters"]["travel_mode"] == "walking"
    bound = {entry["what"]: entry for entry in report["outputs"]}
    assert bound["context"]["canonical_sha256"] == walking["canonical_sha256"] and bound["context"]["sha256"] == walking["file_sha256"]
    assert bound["build_receipt"]["sha256"] == walking["receipt"]["sha256"]
    assert report["timestamps"]["build_started_at_utc"] < report["timestamps"]["build_finished_at_utc"] < report["generated_at_utc"]
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", path.read_text(encoding="ascii")), "no machine path in the report"
    for case_id, group in receipt["outputs"].items():
        for row in group["files"]:
            if row.get("service_set") == "pitch_services":
                assert row["in_git"] is False, "a table of the shelter service stays outside Git"


def test_the_committed_tables_are_inputs_with_a_licence_and_no_component_value() -> None:
    receipt = _committed_receipt()
    rows = [row for group in receipt["outputs"].values() for row in group["files"] if row.get("in_git") and row["what"] == "unit_table"]
    assert rows, "the season-envelope table of the public services has a public lineage"
    for row in rows:
        table = json.loads((ROOT / row["path"]).read_text(encoding="ascii"))
        assert table["service_set"] == "public_services" and table["publication_level"] == "public"
        assert table["generated_at_utc"] == receipt["generated_at_utc"] and table["receipt_file"] == RECEIPT.relative_to(ROOT).as_posix()
        assert table["licence"]["name"] == "CC BY-SA 4.0" and table["licence"]["rights_record"]["record_status"] == "confirmed"
        assert table["licence"]["credit"] == V1A["wording"]["product_4009_credit"]
        assert table["licence"]["standard_sentence"] == V1A["wording"]["standard_4009_sentence"]
        assert table["licence"]["change_notice"].startswith("Changed by FloodGuard:")
        figures = json.dumps([table["runs"], table["services"], table["contexts"], table["licence"],
                              table["source_timestamps"], table["flood_input"]]).lower()
        assert "ddpm" not in figures and "shelter" not in figures and "walking" not in figures, (
            "pitch-level data stays outside Git")
        assert not {key for key in _keys(table) if key.endswith("_0_100") or "fpps" in key.lower() or "action_class" in key}
        assert table["schema_version"] == access_diff.UNIT_TABLE_SCHEMA and table["usable_by_task_e8"] is True
        assert len(table["runs"]) == 3
        for run in table["runs"]:
            assert [unit["unit_id"] for unit in run["units"]] == sorted(V1A["case_portfolio"]["mae_sai_reporting_frame"]["units"])
        # Counts of residents only. The test reads the table and divides nothing: a row of real units holds no
        # number under a key that is not a count or a threshold, so it holds no ratio and no component.
        assert_counts_only(table["runs"])
        assert not {key for key in _keys(table["runs"]) if "share" in key or "ratio" in key}
        assert "No ratio of two counts is written" in table["definitions"]["counts_only"]
        assert "100 x their ratio" in table["definitions"]["road_criticality_inputs"]


def test_a_second_demand_is_counted_on_the_same_runs_and_changes_nothing_else(world: dict[str, Any]) -> None:
    doubled = [{**cell, "residents": 2 * cell["residents"]} for cell in world["cells"]]
    computed = runner.case_runs("INVENTED", "invented_input", {"as_provided": FLOOD}, world["graphs"], world["baselines"],
                                world["services"], access_diff.closure_arguments(V1B), world["cells"], UNIT_IDS,
                                alternate_cells={"doubled": doubled})

    for with_second, without in zip(computed["runs"], world["computed"]["runs"]):
        assert runner.ALTERNATE_DEMAND not in without, "task E5 passes no second demand and its runs carry none"
        second = with_second.pop(runner.ALTERNATE_DEMAND)["doubled"]
        assert with_second == without, "the tables of the first demand are those of a run without a second demand"
        for mine, theirs in zip(second["units"], without["public_services"]["units"]):
            assert mine["unit_id"] == theirs["unit_id"] and mine["residents"] == pytest.approx(2 * theirs["residents"])
            assert mine["road_criticality_inputs"]["residents_losing_all_routes"] == pytest.approx(
                2 * theirs["road_criticality_inputs"]["residents_losing_all_routes"])
