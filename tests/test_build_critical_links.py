"""Plan task E6: the script that ranks the links of the planning context of record.

The assembly is tested on an invented context: a road of thirty edges that ends
at one destination. The input checks are tested on the committed protocol files
and on altered copies in a temporary folder. The last tests read the committed
outputs of the first run; they skip when the run has not been made. Nothing
here reads a flood layer or computes an FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

import pytest
from shapely.geometry import box

from floodguard import critical_links
from floodguard.evidence_context import _context_content_hash
from floodguard.grade_join import JOIN_EDGE_KIND

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_critical_links.py"
_SPEC = importlib.util.spec_from_file_location("build_critical_links", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
builder = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(builder)

OUTPUTS = ROOT / "outputs" / "planning_v1"
TOP_20 = OUTPUTS / "critical_links_top20_se1_vehicle.geojson"
RECEIPT = OUTPUTS / "e6_critical_links_se1_vehicle.json"
UNITS = [("unit-west", box(100.00, 20.00, 100.01, 20.01)), ("unit-east", box(100.01, 20.00, 100.02, 20.01))]
HEADER: dict[str, Any] = {
    "case": "invented_case",
    "boundaries_valid_on": "2025-01-01",
    "protocols_in_force": {"v1a": {"path": "v1a.json", "sha256": "a" * 64}, "v1b": {"path": "v1b.json", "sha256": "b" * 64}},
    "rule": {"ranking_output_binding": "bound_in_first_run_receipt"},
    "inputs": {"context": {"context_generated_at": "2026-01-01T00:00:00+00:00"}},
    "graph": {},
    "destinations": {},
    "units": {"units": 2},
}
PATHS = {"top20": "outputs/planning_v1/critical_links_top20_invented_vehicle.geojson",
         "receipt": "outputs/planning_v1/e6_critical_links_invented_vehicle.json"}
WHEN = "2026-01-02T03:04:05Z"


def _road(connector_after: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """A road n00 - n01 - ... - n30 with the hospital at n00 and k residents at node k.

    Edge k (from node k-1 to node k) carries the residents of nodes k to 30, so the flows fall along the road and
    the ranking is the order of the edges. ``connector_after`` puts a zero-length grade-join connector after that node.
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


def _assemble(connector_after: int | None = None) -> dict[str, Any]:
    context, edges, destinations = _road(connector_after)
    return builder.assemble(context, edges, destinations, UNITS, generated_at_utc=WHEN, header=HEADER, paths=PATHS)


def test_the_assembly_writes_the_top_20_and_binds_the_whole_ranking_by_its_hash() -> None:
    outputs = _assemble()
    top = outputs["top20"]
    assert top.endswith(b"\n") and b"\r" not in top and top == _assemble()["top20"]
    collection = json.loads(top.decode("ascii"))
    features = collection["features"]
    assert collection["type"] == "FeatureCollection" and len(features) == critical_links.OUTPUT_TOP_N == 20
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
        assert "unreviewed" in properties["status"] and "not been done" in properties["status_note"]
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
    assert ranking["grade_join_connectors"] == {"ranked": 0, "best_rank": None, "among_the_top_20": 0, "among_the_top_200": 0}
    assert receipt["demand"]["residents"] == receipt["demand"]["connected_residents_with_a_baseline_route"] == 465
    assert receipt["demand"]["residents_by_nearest_destination_service"] == {"hospital": 465}
    assert "No flood layer" in receipt["computes"] and receipt["rule_as_applied"]["module"] == "src/floodguard/critical_links.py"
    assert {point["id"] for point in receipt["open_points"]} == {"E6-OP1", "E6-OP2", "E6-OP3", "E6-OP4"}

    # The unit of each link is in the table and nowhere else: the committed files name no unit.
    rows = json.loads(table)["links"]
    assert [row["unit_id"] for row in rows[:19]] == ["unit-west"] * 19 and rows[29]["unit_id"] == "unit-east"
    assert ranking["unit_assignment"]["units_that_hold_a_ranked_link"] == 2
    assert sum(ranking["unit_assignment"]["ranked_links"].values()) == 30
    committed_text = top.decode("ascii") + builder.planning_context.encode_json(receipt).decode("ascii")
    assert "unit-west" not in committed_text and "unit-east" not in committed_text
    assert "unit_id" not in committed_text and "subdistrict_id" not in committed_text


def test_a_connector_among_the_top_20_stops_the_run_and_one_below_is_counted() -> None:
    with pytest.raises(builder.OpenPointError, match="does not say whether a connector can be a critical link"):
        _assemble(connector_after=4)
    receipt = _assemble(connector_after=25)["receipt_body"]
    # The connector carries the same residents as the edge after it and has the smaller ID: rank 26.
    assert receipt["ranking"]["grade_join_connectors"] == {
        "ranked": 1, "best_rank": 26, "among_the_top_20": 0, "among_the_top_200": 1}
    assert receipt["ranking"]["top_200"]["grade_join_connectors"] == 1 and receipt["ranking"]["ranked_links"] == 31
    assert receipt["ranking"]["full_reroute_set"]["grade_join_connectors_among_them"] == ["grade-join-0001"]
    assert receipt["ranking"]["ranked_links_by_road_class"] == {"grade_join": 1, "residential": 30}
    with pytest.raises(builder.BuildError, match="generation time"):
        context, edges, destinations = _road()
        builder.assemble(context, edges, destinations, UNITS, generated_at_utc=" ", header=HEADER, paths=PATHS)


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
    assert "midpoint" in rule["unit_rule"] and rule["uses_flood_input"] is False
    for pointer, value in ((("parameters", "output_top_n"), 10), (("uses_flood_input",), True),
                           (("ranking_output", "binding"), "bound_here")):
        changed = deepcopy(v1b)
        block = changed["critical_link_selection"]
        for key in pointer[:-1]:
            block = block[key]
        block[pointer[-1]] = value
        with pytest.raises(builder.BuildError):
            builder.selection_rule(changed)


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


@pytest.fixture(scope="module")
def first_run() -> tuple[dict[str, Any], dict[str, Any]]:
    if not (TOP_20.exists() and RECEIPT.exists()):
        pytest.skip("the E6 ranking has not been run on this checkout")
    return json.loads(RECEIPT.read_text(encoding="ascii")), json.loads(TOP_20.read_text(encoding="ascii"))


def test_the_first_run_receipt_binds_its_inputs_its_outputs_and_both_protocols(
    first_run: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    receipt, collection = first_run
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


def test_the_top_20_of_the_first_run_is_ranked_by_flow_and_then_by_edge_id(
    first_run: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    receipt, collection = first_run
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
    top = receipt["ranking"]["top_20"]
    assert top["graph_bridges"] == sum(row["graph_bridge"] for row in rows)
    assert top["osm_bridge_yes"] == sum(row["osm_bridge"] for row in rows)
    assert top["distinct_osm_ways"] == len({row["osm_way_id"] for row in rows})
    assert top["largest_flow_residents"] == round(rows[0]["spt_flow_residents"], 3)
