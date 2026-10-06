"""Plan task E6: the script that ranks the links of the planning context of record.

The assembly is tested on an invented context: a road of thirty edges that ends
at one destination. The input checks are tested on the committed protocol files,
on altered copies in a temporary folder, and on an invented world (protocol
files, E4 receipt, join log, boundary file and retained context) in which the
script builds, supersedes and verifies. The last tests read the committed
outputs; they skip when the run has not been made. Nothing here reads a flood
layer or computes an FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

import pytest
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from floodguard import critical_links
from floodguard.evidence_context import _canonical_hash, _context_content_hash
from floodguard.grade_join import JOIN_EDGE_KIND, apply_grade_joins, joins_sha256
from floodguard.planning_frames import geometry_sha256

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_critical_links.py"
_SPEC = importlib.util.spec_from_file_location("build_critical_links", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
builder = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(builder)

OUTPUTS = ROOT / "outputs" / "planning_v1"
TOP_20 = OUTPUTS / "critical_links_top20_se1_vehicle.geojson"
RECEIPT = OUTPUTS / "e6_critical_links_se1_vehicle.json"
# The first run of 4 October 2026 (commit 5bdee2f). Its receipt recorded the SHA-256 of the ranking table.
FIRST_RUN = {
    "run_kind": "first_run",
    "generated_at_utc": "2026-10-04T08:24:35Z",
    "evidence_sha256": "bcebbb953807507fb14564c1ab5d513d982f0edd0231d01d2368a93f83b61474",
    "top_20_sha256": "18f1b9f39d09cf4f5bb98d412003de64a301f45a1cdf369f217e3c0da94dc0f1",
    "ranking_table_sha256": "dad48c4993c1545ce0142f2dfe98d7b6af8858fda1dc2364914207e14115307c",
}
WORDING = "v1b is signed with the rule alone; the ranking's SHA-256 is recorded in the receipt of the first run, before any scoring."
UNITS = [("unit-west", box(100.00, 20.00, 100.01, 20.01)), ("unit-east", box(100.01, 20.00, 100.02, 20.01))]
HEADER: dict[str, Any] = {
    "case": "invented_case",
    "boundaries_valid_on": "2025-01-01",
    "protocols_in_force": {"v1a": {"path": "v1a.json", "sha256": "a" * 64}, "v1b": {"path": "v1b.json", "sha256": "b" * 64}},
    "rule": {"ranking_output_binding": "bound_in_first_run_receipt", "ranking_output_binding_wording": WORDING,
             "links_per_unit": 3},
    "inputs": {"context": {"context_generated_at": "2026-01-01T00:00:00+00:00"}},
    "graph": {},
    "destinations": {},
    "units": {"units": 2},
}
PATHS = {"top20": "outputs/planning_v1/critical_links_top20_invented_vehicle.geojson",
         "receipt": "outputs/planning_v1/e6_critical_links_invented_vehicle.json"}
WHEN = "2026-01-02T03:04:05Z"
OPEN_POINT_IDS = {"E6-OP1", "E6-OP2", "E6-OP3", "E6-OP4", "E6-OP5", "E6-OP6", "E6-OP7"}


def _road(
    connector_after: int | None = None, ring: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """A road n00 - n01 - ... - n30 with the hospital at n00 and k residents at node k.

    Edge k (from node k-1 to node k) carries the residents of nodes k to 30, so the flows fall along the road and
    the ranking is the order of the edges. ``connector_after`` puts a zero-length grade-join connector after that
    node. ``ring`` adds edge 31 from n30 back to n00, so every edge has a way round and none is a graph bridge.
    """

    nodes = {f"n{index:02d}": [100.0 + 0.0005 * index, 20.005] for index in range(31)}
    edges = []
    for index in range(1, 31):
        start = f"n{index - 1:02d}"
        if connector_after is not None and index - 1 == connector_after:
            nodes["join"] = list(nodes[start])
            edges.append({"edge_id": "grade-join-0001", "from_node": start, "to_node": "join", "length_m": 0.0,
                          "road_class": "local", "normal_minutes": 0.0, "osm_way_id": None, "bridge": "no",
                          "edge_kind": JOIN_EDGE_KIND})
            start = "join"
        edges.append({"edge_id": f"osm-way-7-segment-{index:02d}", "from_node": start, "to_node": f"n{index:02d}",
                      "length_m": 52.0, "road_class": "residential", "normal_minutes": 0.125, "osm_way_id": "7",
                      "bridge": "yes" if index == 3 else "no"})
    if ring:
        edges.append({"edge_id": "osm-way-7-segment-31", "from_node": "n30", "to_node": "n00", "length_m": 52.0,
                      "road_class": "residential", "normal_minutes": 0.125, "osm_way_id": "7", "bridge": "no"})
    population = [{"population_id": f"cell-{index:02d}", "total_population": float(index), "node_id": f"n{index:02d}",
                   "snap_distance_m": 10.0} for index in range(1, 31)]
    context = {
        "schema_version": "floodguard.context_scenario_inputs.v1",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "travel_mode": "legacy_vehicle",
        "population": population,
        "node_coordinates": nodes,
        "source_metadata": {"osm": {"retrieved_at_utc": "2025-12-31T00:00:00Z"}},
        "input_hashes": {},
    }
    context["canonical_sha256"] = _context_content_hash(context)
    destinations = [{"facility_id": "OSM-way-1", "node_id": "n00", "snap_distance_m": 0.0, "service_type": "hospital"}]
    return context, edges, destinations


def _assemble(connector_after: int | None = None, ring: bool = False, **extra: Any) -> dict[str, Any]:
    context, edges, destinations = _road(connector_after, ring)
    return builder.assemble(
        context, edges, destinations, UNITS, generated_at_utc=WHEN, header=HEADER, paths=PATHS, **extra)


def test_the_assembly_writes_the_top_20_and_binds_the_whole_ranking_by_its_hash() -> None:
    outputs = _assemble()
    top = outputs["top20"]
    assert top.endswith(b"\n") and b"\r" not in top and top == _assemble()["top20"]
    collection = json.loads(top.decode("ascii"))
    features = collection["features"]
    assert collection["type"] == "FeatureCollection" and len(features) == critical_links.OUTPUT_TOP_N == 20
    assert collection["run_kind"] == "first_run"
    assert [feature["properties"]["rank"] for feature in features] == list(range(1, 21))
    assert [feature["properties"]["edge_id"] for feature in features] == [f"osm-way-7-segment-{k:02d}" for k in range(1, 21)]
    # Edge k carries the residents of nodes k to 30: 465 on the first edge.
    assert features[0]["properties"]["spt_flow_residents"] == 465 and features[19]["properties"]["spt_flow_residents"] == 275
    for feature in features:
        properties = feature["properties"]
        assert properties["confidence_class"] == "low" and properties["official_warning"] is False
        assert properties["operational_status"] == "non_operational" and properties["assumptions"]
        assert properties["source_timestamp"] == "2025-12-31T00:00:00Z" and properties["generated_at_utc"] == WHEN
        assert properties["graph_bridge"] is True and properties["in_flood_extent"] is None
        assert properties["osm_bridge"] is (properties["rank"] == 3)
        assert properties["status"] == "first_run_unreviewed_candidates" and "not been done" in properties["status_note"]
        assert feature["geometry"]["type"] == "LineString" and len(feature["geometry"]["coordinates"]) == 2

    receipt = outputs["receipt_body"]
    table = outputs["ranking_table"]
    assert receipt["outputs"]["top_20"] == {"path": PATHS["top20"], "sha256": hashlib.sha256(top).hexdigest(), "features": 20}
    assert receipt["outputs"]["ranking_table"]["sha256"] == hashlib.sha256(table).hexdigest() == collection["ranking_table_sha256"]
    assert receipt["outputs"]["ranking_table"]["links"] == 30 and receipt["outputs"]["ranking_table"]["retained_in_git"] is False
    assert receipt["protocols_in_force"] == HEADER["protocols_in_force"]
    assert collection["protocol_v1a_sha256"] == "a" * 64 and collection["protocol_v1b_sha256"] == "b" * 64
    ranking = receipt["ranking"]
    assert ranking["ranked_links"] == 30 and ranking["top_20"]["links"] == 20 and ranking["top_200"]["links"] == 30
    assert ranking["top_20"]["largest_flow_residents"] == 465 and ranking["top_20"]["smallest_flow_residents"] == 275
    assert ranking["top_20"]["distinct_osm_ways"] == 1 and ranking["top_20"]["by_road_class"] == {"residential": 20}
    assert ranking["top_20"]["tie_at_the_cut_broken_by_edge_id"] is False
    assert ranking["full_reroute_set"]["edge_ids_in_rank_order"] == [f"osm-way-7-segment-{k:02d}" for k in range(1, 31)]
    connectors = ranking["grade_join_connectors"]
    assert {key: connectors[key] for key in connectors if key != "note"} == {
        "ranked": 0, "best_rank": None, "among_the_top_20": 0, "among_the_top_200": 0,
        "sharing_their_flow_with_a_road_edge": 0,
        "ranked_directly_ahead_of_a_road_edge_with_the_same_flow": 0, "links_per_unit_read_by_scenario_s3": 3,
        "units_where_one_is_among_the_highest_ranked_links_of_the_unit": 0}
    assert receipt["demand"]["residents"] == receipt["demand"]["connected_residents_with_a_baseline_route"] == 465
    assert receipt["demand"]["residents_by_nearest_destination_service"] == {"hospital": 465}
    onward = receipt["demand"]["destination_nodes_routed_onward_at_an_equal_time"]
    assert (onward["nodes"], onward["nodes_carrying_residents_onward"], onward["residents_carried_onward"]) == (0, 0, 0)
    assert "E6-OP7" in onward["note"]
    assert "No flood layer" in receipt["computes"] and receipt["rule_as_applied"]["module"] == "src/floodguard/critical_links.py"
    assert {point["id"] for point in receipt["open_points"]} == OPEN_POINT_IDS

    # The unit of each link is in the table and nowhere else: the committed files name no unit.
    rows = json.loads(table)["links"]
    assert [row["unit_id"] for row in rows[:19]] == ["unit-west"] * 19 and rows[29]["unit_id"] == "unit-east"
    assert ranking["unit_assignment"]["units_that_hold_a_ranked_link"] == 2
    assert sum(ranking["unit_assignment"]["ranked_links"].values()) == 30
    committed_text = top.decode("ascii") + builder.planning_context.encode_json(receipt).decode("ascii")
    assert "unit-west" not in committed_text and "unit-east" not in committed_text
    assert "unit_id" not in committed_text and "subdistrict_id" not in committed_text


def test_graph_bridges_are_flagged_and_nothing_is_added_which_the_receipt_reports_as_an_open_point() -> None:
    """Protocol v1b: 'Add graph bridges (Tarjan) to cover the all-routes-lost case.' It does not say added to what."""

    v1b = builder.read_json(builder.PROTOCOL_PATHS["v1b"])
    assert builder.BRIDGE_RULE == v1b["critical_link_selection"]["rule"][1]
    point = next(point for point in builder.OPEN_POINTS if point["id"] == "E6-OP5")
    assert builder.BRIDGE_RULE in point["protocol_says"] and "Nothing is added" in point["what_this_run_does"]
    assert "not a decided reading" in point["what_this_run_does"] and "trigger B" in point["why_it_matters"]
    assert point["needed_from_the_owners"].strip()
    reworded = deepcopy(v1b)
    reworded["critical_link_selection"]["rule"][1] = "Add graph bridges."
    with pytest.raises(builder.BuildError, match="graph-bridge line"):
        builder.selection_rule(reworded)

    # A line: every edge is a graph bridge, and the top 20 are bridges because of their flow, not because of a rule.
    line = _assemble()["receipt_body"]
    bridges = line["ranking"]["graph_bridges"]
    assert (bridges["in_the_baseline_graph"], bridges["ranked"], bridges["among_the_top_20"]) == (30, 30, 20)
    assert (bridges["among_the_top_200"], bridges["best_rank"], bridges["flow_residents_at_the_best_rank"]) == (30, 1, 465)
    assert bridges["added_to_the_ranking"] == 0 and "E6-OP5" in bridges["reading"]
    assert bridges["closing_one_top_20_link_on_its_own"].startswith("20 of the top 20 links are graph bridges (30 of the top 200).")
    assert line["limitations"][-1] == bridges["closing_one_top_20_link_on_its_own"]
    assert "E6-OP5" in line["rule_as_applied"]["graph_bridges"]

    # A ring: no edge is a graph bridge, so closing any single top-20 link isolates nobody. The receipt says so.
    context, edges, destinations = _road(ring=True)
    ring = _assemble(ring=True)["receipt_body"]
    bridges = ring["ranking"]["graph_bridges"]
    assert (bridges["in_the_baseline_graph"], bridges["ranked"], bridges["among_the_top_20"]) == (0, 0, 0)
    assert bridges["best_rank"] is None and bridges["flow_residents_at_the_best_rank"] is None
    note = bridges["closing_one_top_20_link_on_its_own"]
    assert note.startswith("No link among the top 20 is a graph bridge, and none among the top 200.")
    assert "isolates nobody" in note and "no reroute was run" in note and ring["limitations"][-1] == note
    assert ring["ranking"]["top_20"]["graph_bridges"] == 0 and ring["ranking"]["ranked_links"] == 30
    for edge_id in ring["ranking"]["full_reroute_set"]["edge_ids_in_rank_order"][:20]:
        closed = critical_links.reroute_after_closure(edges, context["population"], destinations, [edge_id])
        assert closed["residents_losing_every_route"] == 0, edge_id
    assert builder.single_closure_note(0, 3).startswith(
        "No link among the top 20 is a graph bridge, and 3 among the top 200 are.")


def test_a_connector_among_the_top_20_stops_the_run_and_one_below_is_counted() -> None:
    with pytest.raises(builder.OpenPointError, match="does not say whether a connector can be a critical link"):
        _assemble(connector_after=4)
    receipt = _assemble(connector_after=25)["receipt_body"]
    # The connector carries the same residents as the edge after it and has the smaller ID: rank 26, with the
    # road edge directly behind it. The three highest-ranked links of the east unit are edges 21 to 23.
    connectors = receipt["ranking"]["grade_join_connectors"]
    assert {key: connectors[key] for key in connectors if key != "note"} == {
        "ranked": 1, "best_rank": 26, "among_the_top_20": 0, "among_the_top_200": 1,
        "sharing_their_flow_with_a_road_edge": 1,
        "ranked_directly_ahead_of_a_road_edge_with_the_same_flow": 1, "links_per_unit_read_by_scenario_s3": 3,
        "units_where_one_is_among_the_highest_ranked_links_of_the_unit": 0}
    assert receipt["ranking"]["top_200"]["grade_join_connectors"] == 1 and receipt["ranking"]["ranked_links"] == 31
    assert receipt["ranking"]["full_reroute_set"]["grade_join_connectors_among_them"] == ["grade-join-0001"]
    assert receipt["ranking"]["ranked_links_by_road_class"] == {"grade_join": 1, "residential": 30}
    with pytest.raises(builder.BuildError, match="generation time"):
        context, edges, destinations = _road()
        builder.assemble(context, edges, destinations, UNITS, generated_at_utc=" ", header=HEADER, paths=PATHS)


def test_a_connector_among_the_highest_ranked_links_of_a_unit_is_counted_and_no_unit_is_named() -> None:
    """Open point E6-OP1 reaches scenario S3: the three highest-ranked links of a unit come from the same table."""

    outputs = _assemble(connector_after=21)
    receipt = outputs["receipt_body"]
    # The east unit starts at edge 21. The connector after node 21 carries the flow of edge 22 and sorts ahead of
    # it, so the unit's three highest-ranked links are edge 21, the connector and edge 22: ranks 21, 22 and 23.
    rows = json.loads(outputs["ranking_table"])["links"]
    east = [row for row in rows if row["unit_id"] == "unit-east"][:3]
    assert [(row["rank"], row["edge_kind"]) for row in east] == [(21, "road"), (22, JOIN_EDGE_KIND), (23, "road")]
    assert east[1]["spt_flow_residents"] == east[2]["spt_flow_residents"] == sum(range(22, 31))
    connectors = receipt["ranking"]["grade_join_connectors"]
    assert connectors["among_the_top_20"] == 0 and connectors["best_rank"] == 22
    assert connectors["units_where_one_is_among_the_highest_ranked_links_of_the_unit"] == 1
    assert connectors["ranked_directly_ahead_of_a_road_edge_with_the_same_flow"] == 1
    assert connectors["sharing_their_flow_with_a_road_edge"] == 1
    assert "unit-east" not in builder.planning_context.encode_json(receipt).decode("ascii")
    point = next(point for point in receipt["open_points"] if point["id"] == "E6-OP1")
    assert "sorts" in point["what_this_run_does"] and "S3" in point["what_this_run_does"]

    # Two connectors on one path (a way joined at both ends) carry one flow: both sort ahead of the road edges
    # with that flow, and only the second has a road edge at the next rank. A flow no road edge has is no tie.
    def row(edge_id: str, flow: float, kind: str = "road") -> dict[str, Any]:
        return {"edge_id": edge_id, "spt_flow_residents": flow, "edge_kind": kind}

    assert builder.connector_ties([
        row("grade-join-a", 5.0, JOIN_EDGE_KIND), row("grade-join-b", 5.0, JOIN_EDGE_KIND), row("osm-way-1", 5.0),
        row("osm-way-2", 5.0), row("grade-join-c", 3.0, JOIN_EDGE_KIND), row("osm-way-3", 2.0),
    ]) == {"sharing_their_flow_with_a_road_edge": 2, "ranked_directly_ahead_of_a_road_edge_with_the_same_flow": 1}
    assert builder.connector_ties([]) == {
        "sharing_their_flow_with_a_road_edge": 0, "ranked_directly_ahead_of_a_road_edge_with_the_same_flow": 0}


def _earlier(**changes: Any) -> dict[str, Any]:
    return {**FIRST_RUN, "replaced_because": "The review of 4 October 2026 found open points the receipt left out.", **changes}


def test_a_run_says_whether_it_is_the_first_run_or_supersedes_one() -> None:
    table = FIRST_RUN["ranking_table_sha256"]
    first = builder.run_statement([], WHEN, table, WORDING)
    assert (first["run_kind"], first["status"]) == ("first_run", "first_run_unreviewed_candidates")
    assert first["status_note"].startswith("First run of plan task E6") and "not been done" in first["status_note"]
    assert first["run_history"] == {
        "earlier_runs": [], "first_run_generated_at_utc": WHEN, "ranking_table_sha256_recorded_by_the_first_run": table,
        "this_run_computed_that_ranking_table": True, "note": "This is the first run."}
    # Both notes quote protocol v1b word for word, and neither speaks of a scoring run.
    for note in (first["status_note"], first["binding_note"]):
        assert f'"{WORDING}"' in note and "first scoring run" not in note
        assert "the receipt of the first run of the ranking" in note
    assert "E6-OP1" in first["status_note"] and "E6-OP5" in first["status_note"]

    later = builder.run_statement([_earlier()], "2026-10-04T12:00:00Z", table, WORDING)
    assert (later["run_kind"], later["status"]) == ("superseding_run", "superseding_run_unreviewed_candidates")
    assert "First run" not in later["status_note"] and table in later["status_note"]
    assert "that supersedes the first run, generated 2026-10-04T08:24:35Z." in later["status_note"]
    assert f'"{WORDING}"' in later["status_note"] and f'"{WORDING}"' in later["binding_note"]
    assert "repeats the record and replaces nothing" in later["binding_note"] and "E6-OP6" in later["binding_note"]
    history = later["run_history"]
    assert history["earlier_runs"] == [_earlier()] and history["first_run_generated_at_utc"] == FIRST_RUN["generated_at_utc"]
    assert history["ranking_table_sha256_recorded_by_the_first_run"] == table

    # A third run keeps both earlier runs, oldest first.
    second = _earlier(run_kind="superseding_run", generated_at_utc="2026-10-04T12:00:00Z", evidence_sha256="c" * 64,
                      replaced_because="A second reason.")
    third = builder.run_statement([_earlier(), second], "2026-10-05T00:00:00Z", table, WORDING)
    assert third["run_history"]["earlier_runs"] == [_earlier(), second] and "2 earlier runs" in third["status_note"]
    assert "supersedes the run generated 2026-10-04T12:00:00Z" in third["status_note"]
    assert "the first run was generated 2026-10-04T08:24:35Z" in third["status_note"]


def test_a_superseding_run_with_another_ranking_table_stops_and_a_malformed_history_is_refused() -> None:
    table = FIRST_RUN["ranking_table_sha256"]
    with pytest.raises(builder.OpenPointError, match="does not say whether a later run may change a recorded ranking"):
        builder.run_statement([_earlier()], "2026-10-04T12:00:00Z", "e" * 64, WORDING)
    with pytest.raises(builder.OpenPointError, match="E6-OP6"):
        _assemble(earlier_runs=[_earlier(generated_at_utc="2026-01-01T00:00:00Z")])
    for broken, message in (
        ([_earlier(run_kind="superseding_run")], "first run followed by superseding runs"),
        ([_earlier(), _earlier(generated_at_utc="2026-10-04T09:00:00Z")], "first run followed by superseding runs"),
        ([{key: value for key, value in _earlier().items() if key != "top_20_sha256"}], "first run followed"),
        ([_earlier(replaced_because=" ")], "the reason it was replaced"),
        ([_earlier(evidence_sha256="abc")], "three SHA-256 values"),
    ):
        with pytest.raises(builder.BuildError, match=message):
            builder.run_statement(broken, "2026-10-04T12:00:00Z", table, WORDING)
    # A run is generated after every run it supersedes.
    for when in ("2026-10-04T08:24:35Z", "2026-10-04T08:00:00Z"):
        with pytest.raises(builder.BuildError, match="generated after every run it supersedes"):
            builder.run_statement([_earlier()], when, table, WORDING)

    # The same assembly as a first run and as a superseding run: same ranking, another status in every feature.
    first = _assemble()
    again = _assemble(earlier_runs=[_earlier(
        generated_at_utc="2026-01-01T00:00:00Z", ranking_table_sha256=first["receipt_body"]["outputs"]["ranking_table"]["sha256"])])
    assert again["ranking_table"] == first["ranking_table"] and again["top20"] != first["top20"]
    collection = json.loads(again["top20"])
    assert collection["run_kind"] == again["receipt_body"]["run_kind"] == "superseding_run"
    assert {feature["properties"]["status"] for feature in collection["features"]} == {"superseding_run_unreviewed_candidates"}
    assert not any(feature["properties"]["status_note"].startswith("First run") for feature in collection["features"])


def test_a_missing_or_altered_context_is_reported_and_never_rebuilt(tmp_path: Path) -> None:
    context, _edges, _destinations = _road()
    logical = "<external_data_workspace>/proposal_execution/planning_v1/invented/e4_vehicle/context_inputs.json"
    receipt = {"context": {"path": logical, "canonical_sha256": context["canonical_sha256"]}}
    with pytest.raises(builder.BuildError, match="retained context is missing"):
        builder.load_retained_context(receipt, tmp_path)
    target = tmp_path / "proposal_execution" / "planning_v1" / "invented" / "e4_vehicle" / "context_inputs.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(context, separators=(",", ":")), encoding="utf-8")
    loaded, record = builder.load_retained_context(receipt, tmp_path)
    assert loaded == context and record["canonical_sha256"] == context["canonical_sha256"]
    assert record["path"] == logical and record["file_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()

    # One resident more: the stored hash still says the old value, the recomputed one does not.
    altered = deepcopy(context)
    altered["population"][0]["total_population"] += 1.0
    target.write_text(json.dumps(altered, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(builder.BuildError, match="differs from the context of record"):
        builder.load_retained_context(receipt, tmp_path)
    # A context that is consistent in itself but is not the one the receipt names.
    altered["canonical_sha256"] = _context_content_hash(altered)
    target.write_text(json.dumps(altered, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(builder.BuildError, match="differs from the context of record"):
        builder.load_retained_context(receipt, tmp_path)
    with pytest.raises(builder.BuildError, match="under the external data root"):
        builder.load_retained_context({"context": {"path": "C:/somewhere/context.json", "canonical_sha256": "0"}}, tmp_path)
    walking = {**context, "travel_mode": "walking"}
    walking["canonical_sha256"] = _context_content_hash(walking)
    target.write_text(json.dumps(walking, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(builder.BuildError, match="not a vehicle context"):
        builder.load_retained_context({"context": {"path": logical, "canonical_sha256": walking["canonical_sha256"]}}, tmp_path)


def test_both_protocols_must_be_in_force_and_state_the_parameters_the_code_applies(tmp_path: Path) -> None:
    in_force = builder.protocols_in_force()
    for name, path in builder.PROTOCOL_PATHS.items():
        assert in_force[name] == {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    # A copy with one more byte is not the file the receipt names.
    copies = {}
    for name, path in builder.PROTOCOL_PATHS.items():
        copies[name] = tmp_path / path.name
        copies[name].write_bytes(path.read_bytes())
    assert builder.protocols_in_force(copies)["v1b"]["sha256"] == in_force["v1b"]["sha256"]
    copies["v1b"].write_bytes(builder.PROTOCOL_PATHS["v1b"].read_bytes() + b"\n")
    with pytest.raises(builder.BuildError, match="v1b is not in force"):
        builder.protocols_in_force(copies)

    v1b = builder.read_json(builder.PROTOCOL_PATHS["v1b"])
    rule = builder.selection_rule(v1b)
    assert rule["parameters"] == {"full_reroute_top_n": 200, "output_top_n": 20, "tie_break": "stable edge ID"}
    assert rule["rule"][0] == "Rank baseline vehicle edges by demand-weighted shortest-path-tree flow."
    assert "OSM hospitals and main-road entry" in rule["destination_set_for_ranking"]
    assert "midpoint" in rule["unit_rule"] and rule["uses_flood_input"] is False and rule["links_per_unit"] == 3
    # The sentence on the binding is read from the signed file, so the outputs cannot misquote it.
    assert rule["ranking_output_binding_wording"] == WORDING
    assert WORDING in v1b["critical_link_selection"]["ranking_output"]["binding_status"]
    for pointer, value in ((("parameters", "output_top_n"), 10), (("uses_flood_input",), True),
                           (("ranking_output", "binding"), "bound_here")):
        changed = deepcopy(v1b)
        block = changed["critical_link_selection"]
        for key in pointer[:-1]:
            block = block[key]
        block[pointer[-1]] = value
        with pytest.raises(builder.BuildError):
            builder.selection_rule(changed)
    # Neither the script nor the module says the hash is recorded by a scoring run.
    for path in (SCRIPT, ROOT / "src" / "floodguard" / "critical_links.py", OUTPUTS / "README.md"):
        assert "first scoring run" not in path.read_text(encoding="utf-8"), path.name


def test_the_e4_receipt_must_be_the_one_protocol_v1b_records(tmp_path: Path) -> None:
    v1b = builder.read_json(builder.PROTOCOL_PATHS["v1b"])
    source = OUTPUTS / "e4_planning_context_se1_vehicle.json"
    receipt, record = builder.load_e4_receipt("se1", v1b)
    assert record == {"path": "outputs/planning_v1/e4_planning_context_se1_vehicle.json",
                      "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    assert receipt["context"]["canonical_sha256"] == v1b["corridor_polygon"]["e4_build_of_record"]["context_canonical_sha256"]
    with pytest.raises(builder.BuildError, match="no E4 receipt"):
        builder.load_e4_receipt("se1", v1b, tmp_path)
    (tmp_path / source.name).write_bytes(source.read_bytes().replace(b'"edges": 65328', b'"edges": 65329'))
    with pytest.raises(builder.BuildError, match="not the one protocol v1b records"):
        builder.load_e4_receipt("se1", v1b, tmp_path)


def test_the_external_data_root_is_an_argument_or_an_environment_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(builder.ENV_ROOT, raising=False)
    with pytest.raises(SystemExit):
        builder.parse_args([])
    with pytest.raises(SystemExit):
        builder.parse_args(["--context-root", str(ROOT / "outputs")])
    with pytest.raises(SystemExit):
        builder.parse_args(["--context-root", str(tmp_path), "--write-ranking", str(ROOT / "outputs" / "table.json")])
    with pytest.raises(SystemExit):
        builder.parse_args(["--context-root", str(tmp_path), "--verify", "--supersede", "a reason"])
    monkeypatch.setenv(builder.ENV_ROOT, str(tmp_path))
    args = builder.parse_args([])
    assert args.context_root == tmp_path and args.case == "se1"
    assert args.boundaries == tmp_path / "open_context" / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
    # No local path is written into the script.
    assert not re.search(r"[A-Za-z]:[\\/]|/Users/|/home/", SCRIPT.read_text(encoding="utf-8"))


# An invented world: everything the script reads, written into a temporary folder. The road is the one above with
# a trunk edge beyond its last node (two main-road entries) and a spur that ends where node n10 lies (one grade join).

WORLD_UNITS = {"unit-west": box(100.00, 20.00, 100.01, 20.01), "unit-east": box(100.01, 20.00, 100.02, 20.01),
               "unit-far": box(100.20, 20.20, 100.21, 20.21)}
WORLD_AREA = box(100.00, 20.00, 100.02, 20.01)


def _world_context() -> dict[str, Any]:
    context, edges, _destinations = _road()
    nodes = context["node_coordinates"]
    nodes["t1"] = [100.0155, 20.005]
    nodes["g1"] = list(nodes["n10"])
    nodes["g2"] = [100.005, 20.006]
    edges.append({"edge_id": "osm-way-9-segment-01", "from_node": "n30", "to_node": "t1", "length_m": 52.0,
                  "road_class": "trunk", "normal_minutes": 0.05, "osm_way_id": "9", "bridge": "no"})
    edges.append({"edge_id": "osm-way-8-segment-01", "from_node": "g1", "to_node": "g2", "length_m": 110.0,
                  "road_class": "residential", "normal_minutes": 0.25, "osm_way_id": "8", "bridge": "no"})
    context["population"].append(
        {"population_id": "cell-g2", "total_population": 1.5, "node_id": "g2", "snap_distance_m": 10.0})
    context["edges"] = edges
    context["connectivity_review"] = {"review_candidates": [{"coordinates": list(nodes["n10"]), "nodes": [
        {"node_id": "g1", "grade": ["no", "1", "no"], "way_ids": ["8"], "endpoint_way_ids": ["8"]},
        {"node_id": "n10", "grade": ["no", "0", "no"], "way_ids": ["7"], "endpoint_way_ids": ["7"]},
    ]}]}
    context["osm_facilities"] = [{"facility_id": "OSM-way-1", "service_type": "hospital", "node_id": "n00",
                                  "snap_distance_m": 0.0, "candidate_destination_eligible": True,
                                  "within_routing_context": True}]
    return context


def _write_units(path: Path, units: dict[str, Any]) -> None:
    import geopandas

    frame = geopandas.GeoDataFrame({"adm3_pcode": list(units)}, geometry=list(units.values()), crs="EPSG:4326")
    frame.to_file(path, layer="tha_admin3", driver="GPKG")


def _units_as_read(path: Path) -> tuple[int, str]:
    """The number of units that intersect the routing geometry and the canonical hash of their union, read back."""

    import pyogrio

    margin = builder.BOUNDARY_WINDOW_MARGIN_DEG
    west, south, east, north = WORLD_AREA.bounds
    frame = pyogrio.read_dataframe(path, layer="tha_admin3", columns=["adm3_pcode"],
                                   bbox=(west - margin, south - margin, east + margin, north + margin))
    held = frame[frame.geometry.intersects(WORLD_AREA)]
    return len(held), _canonical_hash(mapping(unary_union(list(held.geometry))))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _world(
    folder: Path,
    *,
    alter: Callable[[dict[str, Any]], None] | None = None,
    units: dict[str, Any] | None = None,
) -> tuple[list[str], Any]:
    """Write the invented world and return the command line and the layout of a run in it.

    The E4 receipt records the joins, hospitals, main-road entries and reporting units of the unaltered context and
    of ``WORLD_UNITS``. ``alter`` changes the retained context and ``units`` the boundary file after that, each with
    its own hash kept right, so exactly one thing differs from what the E4 receipt records.
    """

    external, held, docs = folder / "external", folder / "outputs", folder / "docs"
    for path in (external, held, docs):
        path.mkdir(parents=True)
    recorded_units = folder / "recorded_units.gpkg"
    _write_units(recorded_units, WORLD_UNITS)
    unit_count, union_sha256 = _units_as_read(recorded_units)
    boundaries = external / "boundaries.gpkg"
    _write_units(boundaries, units or WORLD_UNITS)

    base = _world_context()
    base["input_hashes"] = {"reporting_geometry": union_sha256}
    _edges, joins = apply_grade_joins(base)
    entries = builder.planning_context.main_road_entries(base)
    retained = deepcopy(base)
    if alter is not None:
        alter(retained)
    retained["canonical_sha256"] = _context_content_hash(retained)
    logical = "<external_data_workspace>/proposal_execution/planning_v1/invented/e4_vehicle/context_inputs.json"
    target = external / logical.split("/", 1)[1]
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(retained, separators=(",", ":")), encoding="utf-8")

    join_log = held / "grade_join_log_e4_se1_vehicle.json"
    join_log.write_text(json.dumps({"joins": joins}) + "\n", encoding="ascii")
    aoi = folder / "aoi.geojson"
    aoi.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(WORLD_AREA)}]}), encoding="ascii")
    routing_geometry = json.loads(json.dumps(mapping(WORLD_AREA)))
    routing = held / "corridor_of_record.geojson"
    routing.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": routing_geometry}]}), encoding="ascii")

    e4 = held / "e4_planning_context_se1_vehicle.json"
    e4.write_text(json.dumps({
        "run_kind": "build_of_record",
        "travel_mode": "legacy_vehicle",
        "context": {"path": logical, "canonical_sha256": retained["canonical_sha256"]},
        "grade_joins": {"log_path": str(join_log), "joins_sha256": joins_sha256(joins), "join_count": len(joins)},
        "facilities": {
            "hospitals_in_routing_context": [{"facility_id": "OSM-way-1"}],
            "main_road_entries": len(entries),
            "main_road_entry_node_ids_sha256": hashlib.sha256(
                json.dumps([row["node_id"] for row in entries], separators=(",", ":")).encode("ascii")).hexdigest(),
        },
        "input_hashes": {"boundaries_sha256": _sha256(boundaries)},
        "routing_source": {"sha256": _sha256(routing), "geometry_sha256": geometry_sha256(routing_geometry)},
        "context_call": {"reporting_units_intersecting": unit_count},
        "source_timestamps": {"boundaries_valid_on": "2025-01-01"},
    }), encoding="ascii")

    real = builder.read_json(builder.PROTOCOL_PATHS["v1b"])
    v1a = docs / "planning_protocol_v1a.json"
    v1a.write_text(json.dumps({"status": "signed"}), encoding="ascii")
    v1b = docs / "planning_protocol_v1b.json"
    v1b.write_text(json.dumps({
        "status": "signed",
        "depends_on": {"v1a_sha256": _sha256(v1a)},
        "critical_link_selection": real["critical_link_selection"],
        "facility_sets": {"services": {"main_road_entry": {"definition": "A node of a trunk or primary edge."}}},
        "scenario_engine_grid": {"cells": [cell for cell in real["scenario_engine_grid"]["cells"] if cell["id"] == "S3"]},
        "grade_join_policy": {"join_log": {"path": str(join_log), "sha256": _sha256(join_log), "join_count": len(joins)}},
        "corridor_polygon": {
            "e4_build_of_record": {"build_receipt_path": f"outputs/planning_v1/{e4.name}", "build_receipt_sha256": _sha256(e4),
                                   "context_canonical_sha256": retained["canonical_sha256"]},
            "construction": {"boundary_source": f"An invented boundary file (SHA-256 {_sha256(boundaries)})",
                             "base": str(aoi), "base_sha256": _sha256(aoi)},
            "geometry_file": {"path": str(routing), "sha256": _sha256(routing)},
        },
    }), encoding="ascii")
    receipts = docs / "RECEIPTS.jsonl"
    receipts.write_text("".join(
        json.dumps({"time_utc": "2026-01-01T00:00:00Z", "output_hashes": {f"planning_protocol_{name}_sha256": _sha256(path)}}) + "\n"
        for name, path in (("v1a", v1a), ("v1b", v1b))), encoding="ascii")
    layout = builder.Layout({"v1a": v1a, "v1b": v1b}, receipts, held)
    return ["--context-root", str(external), "--boundaries", str(boundaries)], layout


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every reading of the time another second, so a run made at once after another is still later."""

    ticks = iter(range(3_600))

    def now() -> str:
        tick = next(ticks)
        return f"2026-02-03T04:{tick // 60:02d}:{tick % 60:02d}Z"

    monkeypatch.setattr(builder, "_utc_now", now)


def test_a_run_builds_supersedes_and_verifies_in_a_temporary_folder(
    tmp_path: Path, clock: None, capsys: pytest.CaptureFixture[str]
) -> None:
    argv, layout = _world(tmp_path)
    paths = builder.output_paths("se1", layout.output_dir)

    assert builder.main(argv, layout) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary["run_kind"], summary["earlier_runs"]) == ("first_run", 0)
    first = json.loads(paths["receipt"].read_text(encoding="ascii"))
    first_hashes = {key: _sha256(path) for key, path in paths.items()}
    assert first["run_kind"] == "first_run" and first["run_history"]["earlier_runs"] == []
    assert first["graph"]["grade_join_connectors"] == 1 and first["destinations"]["main_road_entries"] == 2
    assert first["units"]["units"] == 2 and first["ranking"]["grade_join_connectors"]["ranked"] == 1
    assert summary["receipt_sha256"] == first_hashes["receipt"] and first["outputs"]["top_20"]["sha256"] == first_hashes["top20"]
    assert builder.main([*argv, "--verify"], layout) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True

    # A second run without a reason replaces nothing.
    with pytest.raises(builder.BuildError, match="pass --supersede with the reason"):
        builder.main(argv, layout)
    assert {key: _sha256(path) for key, path in paths.items()} == first_hashes

    # With a reason it says what it is, in the receipt and in every feature, and keeps the first run on record.
    assert builder.main([*argv, "--supersede", "The review found a point the receipt left out."], layout) == 0
    assert json.loads(capsys.readouterr().out)["run_kind"] == "superseding_run"
    second = json.loads(paths["receipt"].read_text(encoding="ascii"))
    second_receipt_sha256 = _sha256(paths["receipt"])
    assert second["run_kind"] == "superseding_run" and second["status"] == "superseding_run_unreviewed_candidates"
    assert second["run_history"]["earlier_runs"] == [{
        "run_kind": "first_run", "generated_at_utc": first["generated_at_utc"], "evidence_sha256": first_hashes["receipt"],
        "top_20_sha256": first_hashes["top20"], "ranking_table_sha256": first["outputs"]["ranking_table"]["sha256"],
        "replaced_because": "The review found a point the receipt left out."}]
    assert second["outputs"]["ranking_table"]["sha256"] == first["outputs"]["ranking_table"]["sha256"]
    assert second["generated_at_utc"] > first["generated_at_utc"] and "First run" not in second["status_note"]
    collection = json.loads(paths["top20"].read_text(encoding="ascii"))
    assert collection["run_kind"] == "superseding_run"
    assert {feature["properties"]["status"] for feature in collection["features"]} == {second["status"]}
    assert builder.main([*argv, "--verify"], layout) == 0
    capsys.readouterr()

    # A third run keeps the whole chain.
    assert builder.main([*argv, "--supersede", "A second reason."], layout) == 0
    capsys.readouterr()
    third = json.loads(paths["receipt"].read_text(encoding="ascii"))
    chain = third["run_history"]["earlier_runs"]
    assert [run["run_kind"] for run in chain] == ["first_run", "superseding_run"]
    assert chain[0] == second["run_history"]["earlier_runs"][0] and chain[1]["evidence_sha256"] == second_receipt_sha256
    assert chain[1]["replaced_because"] == "A second reason." and "2 earlier runs" in third["status_note"]
    assert third["run_history"]["first_run_generated_at_utc"] == first["generated_at_utc"]
    assert builder.main([*argv, "--verify"], layout) == 0
    capsys.readouterr()

    # A receipt that lists earlier runs and calls itself the first run does not verify; nor does an edited top 20.
    kept = paths["receipt"].read_bytes()
    paths["receipt"].write_bytes(kept.replace(b'"run_kind": "superseding_run"', b'"run_kind": "first_run"', 1))
    assert builder.main([*argv, "--verify"], layout) == 1
    assert "receipt_without_run" in json.loads(capsys.readouterr().out)["problems"][0]
    paths["receipt"].write_bytes(kept)
    top = paths["top20"].read_bytes()
    paths["top20"].write_bytes(top.replace(b'"rank": 1,', b'"rank": 9,', 1))
    assert builder.main([*argv, "--verify"], layout) == 1
    capsys.readouterr()
    # A top-20 file that is not the one the receipt records cannot be put on record: nothing is replaced.
    with pytest.raises(builder.BuildError, match="not the one its receipt records"):
        builder.main([*argv, "--supersede", "A third reason."], layout)
    paths["top20"].write_bytes(top)

    # A superseding run whose table is not the one the first run recorded stops, and both files stay as they were.
    paths["receipt"].write_bytes(kept.replace(
        third["outputs"]["ranking_table"]["sha256"].encode("ascii"), b"f" * 64))
    before = {key: _sha256(path) for key, path in paths.items()}
    assert builder.main([*argv, "--supersede", "A third reason."], layout) == 2
    stopped = json.loads(capsys.readouterr().out)
    assert "E6-OP6" in stopped["reason"] and {key: _sha256(path) for key, path in paths.items()} == before
    paths["top20"].unlink()
    with pytest.raises(builder.BuildError, match="only one of its two files"):
        builder.main([*argv, "--supersede", "A third reason."], layout)


def _no_join(context: dict[str, Any]) -> None:
    context["connectivity_review"]["review_candidates"][0]["nodes"][1]["endpoint_way_ids"] = []


def _another_hospital(context: dict[str, Any]) -> None:
    context["osm_facilities"][0]["facility_id"] = "OSM-way-2"


def _another_entry_node(context: dict[str, Any]) -> None:
    context["node_coordinates"]["t2"] = [100.0156, 20.005]
    trunk = next(edge for edge in context["edges"] if edge["road_class"] == "trunk")
    trunk["to_node"] = "t2"


@pytest.mark.parametrize(("change", "message"), [
    ({"alter": _no_join}, "the grade joins of the context differ from those the E4 receipt records"),
    ({"alter": _another_hospital}, "the hospitals of the context differ from those the E4 receipt records"),
    ({"alter": _another_entry_node}, "the main-road entries of the context differ from those the E4 receipt records"),
    ({"units": {**WORLD_UNITS, "unit-east": box(100.01, 20.00, 100.02, 20.009)}},
     "the union of the reporting units is not the reporting geometry of the context"),
    ({"units": {**WORLD_UNITS, "unit-east": box(100.10, 20.10, 100.11, 20.11)}},
     "the number of reporting units differs from the E4 receipt"),
], ids=["one join", "one hospital ID", "one entry node", "one unit polygon", "one unit moved away"])
def test_one_thing_that_differs_from_the_e4_receipt_stops_the_run_and_nothing_is_written(
    tmp_path: Path, clock: None, change: dict[str, Any], message: str
) -> None:
    argv, layout = _world(tmp_path, **change)
    with pytest.raises(builder.BuildError, match=message):
        builder.main(argv, layout)
    assert not any(path.exists() for path in builder.output_paths("se1", layout.output_dir).values())


def test_a_boundary_file_a_join_log_or_a_routing_file_that_is_not_the_recorded_one_stops_the_run(
    tmp_path: Path, clock: None
) -> None:
    argv, layout = _world(tmp_path)
    boundaries = Path(argv[3])
    kept = boundaries.read_bytes()
    _write_units(boundaries, {**WORLD_UNITS, "unit-east": box(100.01, 20.00, 100.02, 20.009)})
    with pytest.raises(builder.BuildError, match="the boundary file is not the one protocol v1b and the E4 receipt name"):
        builder.main(argv, layout)
    boundaries.write_bytes(kept)
    for name, message in (("grade_join_log_e4_se1_vehicle.json", "the grade-join log is not the one protocol v1b records"),
                          ("corridor_of_record.geojson", "the routing geometry file is not the one")):
        path = layout.output_dir / name
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        with pytest.raises(builder.BuildError, match=message):
            builder.main(argv, layout)
        path.write_bytes(original)
    assert not any(path.exists() for path in builder.output_paths("se1", layout.output_dir).values())
    assert builder.main(argv, layout) == 0


@pytest.fixture(scope="module")
def run_of_record() -> tuple[dict[str, Any], dict[str, Any]]:
    if not (TOP_20.exists() and RECEIPT.exists()):
        pytest.skip("the E6 ranking has not been run on this checkout")
    return json.loads(RECEIPT.read_text(encoding="ascii")), json.loads(TOP_20.read_text(encoding="ascii"))


def test_the_committed_receipt_binds_its_inputs_its_outputs_and_both_protocols(
    run_of_record: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    receipt, collection = run_of_record
    v1b = builder.read_json(builder.PROTOCOL_PATHS["v1b"])
    record = v1b["corridor_polygon"]["e4_build_of_record"]
    for name, path in builder.PROTOCOL_PATHS.items():
        assert receipt["protocols_in_force"][name]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["inputs"]["e4_receipt"] == {
        "path": record["build_receipt_path"], "sha256": record["build_receipt_sha256"],
        "is_the_receipt_protocol_v1b_records": True}
    assert receipt["inputs"]["context"]["canonical_sha256"] == record["context_canonical_sha256"]
    assert receipt["inputs"]["context"]["path"].startswith("<external_data_workspace>/")
    assert receipt["graph"]["joins_sha256"] == v1b["grade_join_policy"]["join_log_from_spike_run_of_record"]["joins_sha256"]
    assert receipt["graph"]["context_edges"] == record["edges"]
    assert receipt["graph"]["edges"] == record["edges"] + v1b["grade_join_policy"]["join_log"]["join_count"]
    counts = v1b["facility_sets"]["counts_in_corridor"]
    assert receipt["destinations"]["hospitals"] == counts["osm_hospitals"]
    assert receipt["destinations"]["main_road_entries"] == record["facilities"]["main_road_entries"]
    assert receipt["destinations"]["ddpm_shelters_used"] == 0
    assert receipt["rule"]["parameters"] == v1b["critical_link_selection"]["parameters"]
    assert receipt["rule"]["rule"] == v1b["critical_link_selection"]["rule"]
    assert receipt["outputs"]["top_20"] == {
        "path": TOP_20.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TOP_20.read_bytes()).hexdigest(),
        "features": len(collection["features"])}
    assert receipt["outputs"]["ranking_table"]["sha256"] == collection["ranking_table_sha256"]
    assert receipt["outputs"]["ranking_table"]["binding"] == v1b["critical_link_selection"]["ranking_output"]["binding"]
    assert collection["context_canonical_sha256"] == record["context_canonical_sha256"]
    assert collection["receipt"] == RECEIPT.relative_to(ROOT).as_posix()
    assert receipt["generated_at_utc"] == collection["generated_at_utc"]
    assert receipt["run"]["run_started_at_utc"] <= receipt["generated_at_utc"] <= receipt["run"]["run_finished_at_utc"]
    assert "No flood layer" in receipt["computes"] and "no FPPS" in receipt["computes"]
    assert receipt["ranking"]["grade_join_connectors"]["among_the_top_20"] == 0
    reroute = receipt["ranking"]["full_reroute_set"]["edge_ids_in_rank_order"]
    assert len(reroute) == len(set(reroute)) == min(200, receipt["ranking"]["ranked_links"])
    # Every node of a trunk or primary edge is a destination, so no such edge carries a route.
    by_class = receipt["ranking"]["ranked_links_by_road_class"]
    assert sum(by_class.values()) == receipt["ranking"]["ranked_links"]
    assert "trunk" not in by_class and "primary" not in by_class


def test_the_committed_run_keeps_the_first_run_on_record_and_the_ranking_it_bound(
    run_of_record: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    """The first run's receipt recorded the SHA-256 of the ranking table. A later run repeats it and says what it is."""

    receipt, collection = run_of_record
    history = receipt["run_history"]
    earlier = history["earlier_runs"]
    assert receipt["outputs"]["ranking_table"]["sha256"] == FIRST_RUN["ranking_table_sha256"]
    assert history["ranking_table_sha256_recorded_by_the_first_run"] == FIRST_RUN["ranking_table_sha256"]
    assert history["first_run_generated_at_utc"] == FIRST_RUN["generated_at_utc"]
    assert history["this_run_computed_that_ranking_table"] is True
    if receipt["generated_at_utc"] == FIRST_RUN["generated_at_utc"]:
        assert receipt["run_kind"] == "first_run" and earlier == []
    else:
        assert receipt["run_kind"] == collection["run_kind"] == "superseding_run"
        assert {key: earlier[0][key] for key in FIRST_RUN} == FIRST_RUN and earlier[0]["replaced_because"].strip()
        assert [run["run_kind"] for run in earlier[1:]] == ["superseding_run"] * (len(earlier) - 1)
        assert all(run["ranking_table_sha256"] == FIRST_RUN["ranking_table_sha256"] for run in earlier)
        times = [run["generated_at_utc"] for run in earlier] + [receipt["generated_at_utc"]]
        assert times == sorted(set(times))
        assert "First run" not in receipt["status_note"] and FIRST_RUN["generated_at_utc"] in receipt["status_note"]
    assert receipt["status"] == builder.STATUS_BY_RUN_KIND[receipt["run_kind"]]
    for note in (receipt["status_note"], receipt["outputs"]["ranking_table"]["binding_note"]):
        assert f'"{WORDING}"' in note and "first scoring run" not in note
    # What the committed files say about the open points is what the script says now.
    assert receipt["open_points"] == [dict(point) for point in builder.OPEN_POINTS]
    assert {point["id"] for point in receipt["open_points"]} == OPEN_POINT_IDS
    bridges = receipt["ranking"]["graph_bridges"]
    assert bridges["among_the_top_20"] == receipt["ranking"]["top_20"]["graph_bridges"]
    assert bridges["among_the_top_200"] == receipt["ranking"]["top_200"]["graph_bridges"]
    assert bridges["ranked"] == receipt["ranking"]["ranked_links_that_are_graph_bridges"] and bridges["added_to_the_ranking"] == 0
    assert bridges["closing_one_top_20_link_on_its_own"] == builder.single_closure_note(
        bridges["among_the_top_20"], bridges["among_the_top_200"]) == receipt["limitations"][-1]
    if bridges["among_the_top_20"] == 0:
        assert "isolates nobody" in receipt["limitations"][-1]
        assert bridges["best_rank"] is None or bridges["best_rank"] > 20


def test_the_top_20_of_the_committed_run_is_ranked_by_flow_and_then_by_edge_id(
    run_of_record: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    receipt, collection = run_of_record
    rows = [feature["properties"] for feature in collection["features"]]
    assert len(rows) == 20 and [row["rank"] for row in rows] == list(range(1, 21))
    keys = [(-row["spt_flow_residents"], row["edge_id"]) for row in rows]
    assert keys == sorted(keys) and len({row["edge_id"] for row in rows}) == 20
    assert [row["edge_id"] for row in rows] == receipt["ranking"]["full_reroute_set"]["edge_ids_in_rank_order"][:20]
    assert rows[0]["spt_flow_residents"] <= receipt["demand"]["connected_residents_with_a_baseline_route"]
    for row, feature in zip(rows, collection["features"]):
        assert row["spt_flow_residents"] > 0 and row["edge_kind"] == "road"
        assert isinstance(row["graph_bridge"], bool) and isinstance(row["osm_bridge"], bool)
        assert row["in_flood_extent"] is None, "the baseline ranking reads no flood layer"
        assert feature["geometry"]["type"] == "LineString" and len(feature["geometry"]["coordinates"]) == 2
        assert row["status"] == receipt["status"] and "unreviewed" in row["status"]
        assert row["status_note"] == receipt["status_note"]
    top = receipt["ranking"]["top_20"]
    assert top["graph_bridges"] == sum(row["graph_bridge"] for row in rows)
    assert top["osm_bridge_yes"] == sum(row["osm_bridge"] for row in rows)
    assert top["distinct_osm_ways"] == len({row["osm_way_id"] for row in rows})
    assert top["largest_flow_residents"] == round(rows[0]["spt_flow_residents"], 3)
