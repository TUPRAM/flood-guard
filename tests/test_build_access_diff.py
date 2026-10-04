"""The runner of plan task E5 (scripts/build_access_diff.py), on an invented road network.

Every road, cell, unit, shelter and flood extent here is invented. No FPPS, no A-E class and no ensemble is
computed. The last tests read the committed receipt and table of the real run, when they are on the checkout,
and check what they say about themselves; they compute nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

from floodguard import access_diff, flood_inputs

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
    assert unit("central", "U1")["access"]["hospital"]["thresholds_minutes"]["30"]["newly_lost_share"] == pytest.approx(0.8)
    assert unit("central", "U1")["routes"]["residents_losing_all_routes"] == 40.0
    assert unit("permissive", "U2")["routes"]["share_losing_all_routes"] == 1.0

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


def test_a_table_says_what_it_is_and_carries_its_licence_credit_and_change_notice(world: dict[str, Any]) -> None:
    table = _table(world, "public_services", "public")
    text = runner.encode(table).decode("ascii")

    assert text.endswith("\n") and "\r" not in text
    assert table["schema_version"] == access_diff.UNIT_TABLE_SCHEMA and table["status"] == "unit_inputs"
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
    # Inputs only: no component value, no score and no class anywhere in the table.
    assert not {key for key in _keys(table) if key.endswith("_0_100") or "fpps" in key.lower() or "action_class" in key}
    assert "access-gap component (0-100)" in table["not_computed"] and "FPPS" in table["not_computed"]


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
    assert pitch["contexts"]["walking"]["status"] == "candidate" and "walking" in pitch["runs"][0]["closure"]
    assert "ddpm-shelters" in {row["id"] for row in pitch["licence"]["other_inputs"]}
    assert "invented shelter name" not in runner.encode(pitch).decode("ascii"), "no shelter is named"
    assert _table(world, "pitch_services", "pitch", walking_status="of_record")["status"] == "unit_inputs"


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


def test_the_committed_tables_are_inputs_with_a_licence_and_no_component_value() -> None:
    receipt = _committed_receipt()
    rows = [row for group in receipt["outputs"].values() for row in group["files"] if row.get("in_git")]
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
        assert len(table["runs"]) == 3
        for run in table["runs"]:
            assert [unit["unit_id"] for unit in run["units"]] == sorted(V1A["case_portfolio"]["mae_sai_reporting_frame"]["units"])
            for unit in run["units"]:
                for service in unit["access"].values():
                    for at_threshold in service["thresholds_minutes"].values():
                        assert at_threshold["newly_lost_residents"] <= at_threshold["baseline_access_residents"], "EQ-04"
                        if at_threshold["baseline_access_residents"] == 0:
                            assert at_threshold["newly_lost_share"] is None
                            assert at_threshold["newly_lost_share_unavailable_reason"] == access_diff.NO_BASELINE_ACCESS
                        else:
                            assert at_threshold["newly_lost_share"] == pytest.approx(
                                at_threshold["newly_lost_residents"] / at_threshold["baseline_access_residents"])
                inputs = unit["road_criticality_inputs"]
                assert inputs["residents_losing_all_routes"] <= inputs["residents_with_baseline_route"] <= unit["residents"] + 1e-6
