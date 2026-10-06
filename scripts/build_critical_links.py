"""Plan task E6: the baseline critical-link ranking of a case (protocol v1b ``critical_link_selection``).

Plan 8.1 row E6: ``critical_links.py``; acceptance: a top-20 GeoJSON and a
fixture test. The rule is in ``src/floodguard/critical_links.py``. This script
runs it on the planning context of record that task E4 built and kept outside
Git, and writes:

* ``outputs/planning_v1/critical_links_top20_<case>_vehicle.geojson``: the 20
  highest-ranked links, each with its flow, the graph-bridge flag (Tarjan), the
  OSM bridge tag and a null in-extent flag (no flood layer is read);
* ``outputs/planning_v1/e6_critical_links_<case>_vehicle.json``: the receipt,
  with the SHA-256 of every input, the parameters, the SHA-256 of both protocol
  files in force, the SHA-256 of the top-20 file and the SHA-256 of the whole
  ranking table. Protocol v1b ``critical_link_selection.ranking_output`` (owner
  choice 10) says: "v1b is signed with the rule alone; the ranking's SHA-256 is
  recorded in the receipt of the first run, before any scoring." The receipt of
  the first run of this script is that receipt.

The whole ranking table also says which tambon each link belongs to (drafter
reading DR-B06). It names tambons, so it is not written into Git:
``--write-ranking`` writes its bytes to a path outside the repository.

Nothing is rebuilt. The script takes the context from the path the E4 receipt
names under the external data root, and stops when

* either protocol file is not in force (its SHA-256 is not the one in
  ``RECEIPTS.jsonl``);
* the E4 receipt is not the one protocol v1b records;
* the retained context is missing, or its canonical SHA-256 differs from the
  receipt's;
* the grade joins, the hospitals, the main-road entries or the reporting units
  differ from what the E4 receipt records;
* a grade-join connector is among the top 20: the protocol does not say whether
  a connector can be a critical link;
* a run that supersedes an earlier one gives another ranking table than the
  first run recorded: the protocol does not say whether a later run may change
  a recorded ranking.

The other points the protocol leaves open are written into the receipt
(``open_points``) and decided nowhere in this script. The first of them: the
protocol says "Add graph bridges (Tarjan) to cover the all-routes-lost case"
and not what they are added to, so nothing is added and a bridge is only
flagged.

It reads no flood layer and computes no closure, no reroute, no access loss, no
FPPS, no A-E class and no ensemble. A run is never replaced silently:
``--supersede`` takes the reason, and the receipt it writes says that it is a
superseding run and lists every earlier run under ``run_history`` (generation
time, SHA-256 of the replaced receipt and top-20 file, SHA-256 of its ranking
table, reason). ``--verify`` recomputes everything with the generation time and
the earlier runs of the receipt and compares the top-20 file and the receipt
(without its ``run`` section) byte for byte; it writes nothing.

The external data root is an argument or the environment variable
``FLOODGUARD_EXTERNAL_DATA``::

    python scripts/build_critical_links.py --case se1 --context-root <external data root> \
        [--boundaries <COD-AB file>] [--write-ranking <path outside Git>] \
        [--supersede "<reason>"] [--verify]
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import critical_links, planning_context  # noqa: E402
from floodguard.evidence_context import _canonical_hash, _context_content_hash  # noqa: E402
from floodguard.grade_join import JOIN_EDGE_KIND, apply_grade_joins, joins_sha256  # noqa: E402
from floodguard.planning_frames import geometry_sha256  # noqa: E402

DOCS = ROOT / "docs" / "proposal_execution"
PROTOCOL_PATHS = {"v1a": DOCS / "planning_protocol_v1a.json", "v1b": DOCS / "planning_protocol_v1b.json"}
RECEIPTS = DOCS / "RECEIPTS.jsonl"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
ENV_ROOT = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_PLACEHOLDER = "<external_data_workspace>"
RECEIPT_SCHEMA = "floodguard.critical_links_e6.v1"
TOP_SCHEMA = "floodguard.critical_links_top20.v1"
VEHICLE = "legacy_vehicle"
CASE_IDS = {"se1": "se1_mae_sai"}
# The COD-AB read window of the E4 build (scripts/build_planning_context.py), so the units come in the same order.
BOUNDARY_WINDOW_MARGIN_DEG = 0.45
FIRST_RUN = "first_run"
SUPERSEDING_RUN = "superseding_run"
STATUS_BY_RUN_KIND = {
    FIRST_RUN: "first_run_unreviewed_candidates",
    SUPERSEDING_RUN: "superseding_run_unreviewed_candidates",
}
EARLIER_RUN_KEYS = frozenset(
    {"run_kind", "generated_at_utc", "evidence_sha256", "top_20_sha256", "ranking_table_sha256", "replaced_because"})
UNREVIEWED_NOTE = (
    "The links are unreviewed candidates: the desk check of the top 20 (plan task V1) has not been done, and no link "
    "is an observed closure."
)
OPEN_POINTS_NOTE = (
    "The owners' answers to open points E6-OP1 (grade-join connectors) and E6-OP5 (what the graph bridges are added "
    "to) can change the ranking; they are needed before a later task uses that SHA-256."
)
CONFIDENCE_BASIS = (
    "OSM roads and hospitals are unverified map records, and WorldPop 2020 is a modelled resident count. Routes are "
    "modelled class speeds on an undirected graph, and the grade joins are coordinate coincidences whose passability "
    "is unknown. No link was checked against imagery, on the ground or by a reviewer."
)
ASSUMPTIONS = (
    "A resident's baseline route is the fastest modelled vehicle route from the road node their WorldPop 2020 cell "
    "snaps to (within 250 m) to the nearest destination: an OSM hospital in the routing context or a main-road entry "
    "(a node of a trunk or primary edge, links included). One shortest-path tree serves both kinds of destination "
    "(owner choice 9), so a route ends at the first destination it meets. The one exception is a zero-minute edge "
    "between two destination nodes, which is crossed towards the destination with the smaller ID (open point E6-OP7).",
    "The flow of a link is the number of residents whose baseline route uses it (WorldPop 2020 residents at each "
    "origin node; drafter reading DR-B03). It measures use. Another route may exist, and the flow does not say what "
    "closing the link would cost.",
    "Links are ranked by flow, and equal flows by edge ID. Equal routes go to the smaller destination ID, then to the "
    "smaller parent node ID and edge ID, as in floodguard.evidence_interventions.select_interventions.",
    "An edge is the straight segment between two road nodes, so one street is many edges. Edges of a street with no "
    "resident between them carry the same flow and take neighbouring ranks.",
    "graph_bridge is true when removing the edge disconnects the modelled graph (Tarjan). osm_bridge repeats the OSM "
    "tag bridge=yes. Neither shows that a structure exists or what state it is in. A graph bridge is flagged and "
    "ranked by its flow like any other edge: nothing is added to the ranking for it (open point E6-OP5).",
    "in_flood_extent is null because no flood layer is read. The flag is added for each flood input when a case is "
    "assessed.",
    "Road times are fixed class speeds on an undirected graph. One-way rules, turn restrictions and road condition "
    "are not represented. A grade join shows that two ways end at the same OSM coordinate; it does not show that "
    "the transition can be driven.",
    "Routes stay inside the routing context of the case. Roads and destinations outside it are not seen.",
)
LIMITATIONS = (
    "Computed on one machine. The ranking depends on the OSM extract, on WorldPop 2020 and on the corridor of record.",
    "Every node of a trunk or primary edge is a main-road entry, so an edge between two such nodes that takes time "
    "carries no flow: trunk and primary roads themselves are not ranked, and the ranking finds the roads that lead "
    "to them and to the hospitals. The share of residents whose nearest destination is a main-road entry is under "
    "demand.",
    "No reroute was run: the flow is not the number of residents a closure would cut off.",
)
BRIDGE_RULE = "Add graph bridges (Tarjan) to cover the all-routes-lost case."
OPEN_POINTS = (
    {
        "id": "E6-OP1",
        "point": "Whether a grade-join connector can be a critical link.",
        "protocol_says": "Rank baseline vehicle edges. A join is a zero-length connector edge between two nodes at "
                         "the same coordinate (grade_join_policy).",
        "what_this_run_does": "The connectors are edges of the baseline graph and are ranked like any other, marked "
                              "edge_kind grade_join. A connector between two nodes without residents carries the "
                              "same flow as the road edges on either side of it, and its ID (grade-join-...) sorts "
                              "before a road edge ID (osm-way-...), so the tie-break on the stable edge ID ranks it "
                              "ahead of every road edge with that flow. The run stops if a connector is among the "
                              "top 20. It does not stop for the highest-ranked links of a unit, which scenario S3 "
                              "reads from the same table: ranking.grade_join_connectors counts the connectors that "
                              "share their flow with a road edge and the units where a connector is among the "
                              "highest-ranked links, and names no unit.",
        "needed_from_the_owners": "Whether connectors are ranked at all, and what happens to the ranks if they are "
                                  "not. The answer can change the ranking table (see E6-OP6). Until then a task "
                                  "that selects the S3 links of a unit meets the same undecided case.",
    },
    {
        "id": "E6-OP2",
        "point": "What the full reroute of the top 200 writes, and whether it changes the output.",
        "protocol_says": "Fully reroute only the top 200 ranked edges. Output the top 20.",
        "what_this_run_does": "No reroute is run. The receipt lists the 200 highest-ranked edge IDs "
                              "(ranking.full_reroute_set); floodguard.critical_links.reroute_after_closure closes "
                              "edges and counts the residents who lose every route.",
    },
    {
        "id": "E6-OP3",
        "point": "Whether the bridge flag of the output is the graph bridge (Tarjan) or the OSM tag bridge=yes.",
        "protocol_says": "Add graph bridges (Tarjan). Output the top 20, each with a bridge flag. Scenario S3b uses "
                         "OSM bridge=yes.",
        "what_this_run_does": "Both are written: graph_bridge and osm_bridge.",
    },
    {
        "id": "E6-OP4",
        "point": "The tambon of a link whose midpoint lies in no reporting unit or in more than one.",
        "protocol_says": "A link belongs to the tambon where its edge lies; an edge that crosses a boundary goes by "
                         "its midpoint (drafter reading DR-B06).",
        "what_this_run_does": "Such a link gets no unit (ranking.unit_assignment counts them).",
    },
    {
        "id": "E6-OP5",
        "point": "What 'Add graph bridges' adds the bridges to (the ranked set, the 200 edges of the full reroute "
                 "or the 20 of the output), and where a graph bridge stands against a link ranked by flow.",
        "protocol_says": "'" + BRIDGE_RULE + "' (critical_link_selection.rule, second line). The fourth line "
                         "already asks for a bridge flag on each of the top 20.",
        "what_this_run_does": "Nothing is added. The ranked set is the edges with a positive flow, in the order of "
                              "their flow, and each carries graph_bridge as a flag; a graph bridge enters the 200 "
                              "or the 20 only by its flow. This is not a decided reading: under it the second line "
                              "of the rule adds nothing to the fourth, and the all-routes-lost case reaches an "
                              "output only where a bridge is ranked high enough (ranking.graph_bridges gives the "
                              "counts and the best rank of a graph bridge).",
        "why_it_matters": "Closing an edge that is not a graph bridge takes every route from nobody. Class rule v2 "
                          "trigger B (class_rule_v2_inputs.trigger_B_isolation) closes on its own each top-20 link "
                          "that intersects the flood extent and counts the residents who lose every route, so it "
                          "can only fire through a top-20 link that is a graph bridge.",
        "needed_from_the_owners": "What the bridges are added to and how a bridge is ordered against a flow-ranked "
                                  "link. The answer can change the ranking table (see E6-OP6), so it is needed "
                                  "before a later task records or uses the SHA-256 of the table.",
    },
    {
        "id": "E6-OP6",
        "point": "Whether a run that supersedes the first run may change the ranking the first run recorded.",
        "protocol_says": "The ranking's SHA-256 is recorded in the receipt of the first run, before any scoring "
                         "(critical_link_selection.ranking_output). Every run is reported (change_control). Nothing "
                         "is said about a later run of the ranking.",
        "what_this_run_does": "A superseding run lists every earlier run under run_history and must recompute the "
                              "ranking table the first run recorded. If its table differs it stops and writes "
                              "nothing.",
        "needed_from_the_owners": "If an answer to E6-OP1 or E6-OP5 changes the table: how the new ranking is bound.",
    },
    {
        "id": "E6-OP7",
        "point": "Where a route ends when a zero-minute edge joins two destination nodes.",
        "protocol_says": "The ranking follows the pattern of select_interventions in "
                         "src/floodguard/evidence_interventions.py (critical_link_selection.reuse), and a grade "
                         "join is a zero-length connector edge (grade_join_policy). Neither says where a route "
                         "ends when two destinations are reached in the same time.",
        "what_this_run_does": "The comparison of select_interventions is kept: a node takes the smallest (minutes, "
                              "destination ID). A destination node joined to another destination node by a "
                              "zero-minute edge is therefore routed across that edge to the destination with the "
                              "smaller ID, and every resident whose route reaches that node counts on the edge. "
                              "demand.destination_nodes_routed_onward_at_an_equal_time counts such nodes and those "
                              "residents.",
    },
)
RUN_NOTE = (
    "Everything outside this section is a function of the inputs, the generation time and the earlier runs listed "
    "under run_history: --verify takes the last two from this receipt and recomputes the rest byte for byte. This "
    "section records the run itself and is not compared."
)


class Layout(NamedTuple):
    """Where a run reads the protocol files and the E4 receipt, and where it writes. The default is the repository."""

    protocol_paths: Mapping[str, Path]
    receipts: Path
    output_dir: Path


REPOSITORY = Layout(PROTOCOL_PATHS, RECEIPTS, OUTPUT_DIR)


class BuildError(ValueError):
    """Raised when an input is not the one the protocol or the E4 receipt names."""


class OpenPointError(BuildError):
    """Raised when the run meets a case the protocol does not decide."""


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rounded(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _logical(path: Path, context_root: Path) -> str:
    """Name a path without a local prefix: relative to the repository, or under the external data placeholder."""

    resolved = path.resolve()
    for base, prefix in ((ROOT.resolve(), None), (context_root.resolve(), EXTERNAL_PLACEHOLDER)):
        try:
            relative = resolved.relative_to(base).as_posix()
        except ValueError:
            continue
        return relative if prefix is None else f"{prefix}/{relative}"
    return path.name


def protocols_in_force(
    paths: Mapping[str, Path] = PROTOCOL_PATHS, receipts_path: Path = RECEIPTS
) -> dict[str, dict[str, str]]:
    """Return the SHA-256 of both protocol files, after checking that each is in force.

    A protocol file is in force when its status is ``signed`` and every hash
    that ``RECEIPTS.jsonl`` records for it equals the SHA-256 of the file.

    Raises:
        BuildError: when a file is not in force, or v1b does not name the v1a hash.
    """

    lines = [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result: dict[str, dict[str, str]] = {}
    for name, path in paths.items():
        digest = planning_context.sha256_file(path)
        key = f"planning_protocol_{name}_sha256"
        recorded = {str(line["output_hashes"][key]) for line in lines
                    if isinstance(line.get("output_hashes"), dict) and key in line["output_hashes"]}
        if recorded != {digest} or read_json(path).get("status") != "signed":
            raise BuildError(f"planning protocol {name} is not in force: its SHA-256 is not the one RECEIPTS.jsonl records")
        result[name] = {"path": path.relative_to(ROOT).as_posix() if ROOT in path.parents else path.name, "sha256": digest}
    if read_json(paths["v1b"])["depends_on"]["v1a_sha256"] != result["v1a"]["sha256"]:
        raise BuildError("protocol v1b does not name the v1a file in force")
    return result


def selection_rule(v1b: Mapping[str, Any]) -> dict[str, Any]:
    """Return protocol v1b's critical-link rule, after checking that the module applies its parameters.

    Raises:
        BuildError: when a parameter of the protocol is not the one ``floodguard.critical_links`` applies, or
            the protocol states the graph-bridge line in other words than open point E6-OP5 quotes.
    """

    block = v1b["critical_link_selection"]
    parameters = block["parameters"]
    expected = {
        "full_reroute_top_n": critical_links.FULL_REROUTE_TOP_N,
        "output_top_n": critical_links.OUTPUT_TOP_N,
        "tie_break": critical_links.TIE_BREAK,
    }
    if parameters != expected:
        raise BuildError("protocol v1b critical_link_selection.parameters are not the ones this code applies")
    if block["status"] != "fixed" or block["uses_flood_input"] is not False:
        raise BuildError("protocol v1b critical_link_selection is not fixed, or says the ranking uses a flood input")
    binding = block["ranking_output"]["binding"]
    if binding != "bound_in_first_run_receipt":
        raise BuildError("protocol v1b binds the ranking another way than in the first run receipt")
    if BRIDGE_RULE not in block["rule"]:
        raise BuildError("protocol v1b states the graph-bridge line of the rule in other words than open point E6-OP5 quotes")
    s3 = next(cell for cell in v1b["scenario_engine_grid"]["cells"] if cell["id"] == "S3")
    return {
        "rule": list(block["rule"]),
        "parameters": dict(parameters),
        "demand_weight": block["demand_weight"],
        "destination_set_for_ranking": block["destination_set_for_ranking"],
        "main_road_entry_definition": v1b["facility_sets"]["services"]["main_road_entry"]["definition"],
        "unit_rule": s3["selection_rule"],
        "links_per_unit": s3["parameters"]["links_per_tambon"],
        "uses_flood_input": False,
        "ranking_output_binding": binding,
        "ranking_output_binding_wording": block["ranking_output"]["binding_options"][binding],
        "readings_and_choices": "Drafter readings DR-B03 (demand weight, tie-break), DR-B06 (unit of a link) and "
                                "DR-B07 (the ranking may run without a flood input); owner choices 9 (destinations) "
                                "and 10 (binding), decision log R12.",
    }


def load_e4_receipt(case: str, v1b: Mapping[str, Any], output_dir: Path = OUTPUT_DIR) -> tuple[dict[str, Any], dict[str, str]]:
    """Read the receipt of the E4 build of record, checking it is the file protocol v1b records.

    Raises:
        BuildError: when the receipt is missing, is not the recorded file, or is not a vehicle build of record.
    """

    record = v1b["corridor_polygon"]["e4_build_of_record"]
    path = output_dir / f"e4_planning_context_{case}_vehicle.json"
    if not path.is_file():
        raise BuildError(f"there is no E4 receipt for case {case} in vehicle mode")
    digest = planning_context.sha256_file(path)
    if path.relative_to(output_dir).as_posix() != Path(record["build_receipt_path"]).name or digest != record["build_receipt_sha256"]:
        raise BuildError("the E4 receipt is not the one protocol v1b records")
    receipt = read_json(path)
    if receipt["run_kind"] != "build_of_record" or receipt["travel_mode"] != VEHICLE:
        raise BuildError("the E4 receipt is not a vehicle build of record")
    if receipt["context"]["canonical_sha256"] != record["context_canonical_sha256"]:
        raise BuildError("the E4 receipt names another context than protocol v1b")
    return receipt, {"path": record["build_receipt_path"], "sha256": digest}


def load_retained_context(receipt: Mapping[str, Any], context_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Read the context the E4 build kept outside Git and check its canonical SHA-256. Nothing is rebuilt.

    Raises:
        BuildError: when the file is missing, or its canonical SHA-256 (stored or recomputed) differs from the
            one the E4 receipt records.
    """

    logical = str(receipt["context"]["path"])
    if not logical.startswith(EXTERNAL_PLACEHOLDER + "/"):
        raise BuildError("the E4 receipt does not name a context under the external data root")
    path = context_root / logical[len(EXTERNAL_PLACEHOLDER) + 1:]
    expected = receipt["context"]["canonical_sha256"]
    if not path.is_file():
        raise BuildError(f"the retained context is missing ({logical}); it is not rebuilt here: run the E4 --verify "
                         "or ask the owners")
    context = json.loads(path.read_bytes().decode("utf-8"))
    recomputed = _context_content_hash(context)
    if context.get("canonical_sha256") != expected or recomputed != expected:
        raise BuildError("the retained context differs from the context of record: its canonical SHA-256 is not the "
                         "one the E4 receipt records; it is not rebuilt here")
    if context["travel_mode"] != VEHICLE:
        raise BuildError("the retained context is not a vehicle context")
    return context, {
        "path": logical,
        "canonical_sha256": recomputed,
        "file_sha256": planning_context.sha256_file(path),
        "context_generated_at": str(context["generated_at"]),
    }


def baseline_graph(
    context: Mapping[str, Any], receipt: Mapping[str, Any], v1b: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the baseline vehicle edges (context edges and grade-join connectors), checked against the join log.

    Raises:
        BuildError: when the joins of the context differ from those the E4 receipt records, or the join log is
            not the one protocol v1b records.
    """

    edges, joins = apply_grade_joins(context)
    recorded = receipt["grade_joins"]
    policy = v1b["grade_join_policy"]["join_log"]
    log_path = ROOT / recorded["log_path"]
    if (joins_sha256(joins), len(joins)) != (recorded["joins_sha256"], recorded["join_count"]):
        raise BuildError("the grade joins of the context differ from those the E4 receipt records")
    if recorded["log_path"] != policy["path"] or planning_context.sha256_file(log_path) != policy["sha256"]:
        raise BuildError("the grade-join log is not the one protocol v1b records")
    return edges, {
        "context_edges": len(context["edges"]),
        "grade_join_connectors": len(joins),
        "joins_sha256": recorded["joins_sha256"],
        "join_log": {"path": recorded["log_path"], "sha256": policy["sha256"]},
    }


def destination_set(context: Mapping[str, Any], receipt: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the public facility set of the context (owner choice 9), checked against the E4 receipt.

    Raises:
        BuildError: when the hospitals or the main-road entries of the context differ from those the E4 receipt
            records.
    """

    hospitals = planning_context.hospital_destinations(context)
    entries = planning_context.main_road_entries(context)
    recorded = receipt["facilities"]
    entry_nodes_sha256 = planning_context.sha256_bytes(
        json.dumps([row["node_id"] for row in entries], separators=(",", ":")).encode("ascii"))
    if sorted(row["facility_id"] for row in hospitals) != sorted(
            row["facility_id"] for row in recorded["hospitals_in_routing_context"]):
        raise BuildError("the hospitals of the context differ from those the E4 receipt records")
    if (len(entries), entry_nodes_sha256) != (recorded["main_road_entries"], recorded["main_road_entry_node_ids_sha256"]):
        raise BuildError("the main-road entries of the context differ from those the E4 receipt records")
    destinations = [
        {"facility_id": str(row["facility_id"]), "node_id": row["node_id"], "snap_distance_m": row["snap_distance_m"],
         "service_type": service}
        for service, rows in ((planning_context.HOSPITAL, hospitals), (planning_context.MAIN_ROAD_ENTRY, entries))
        for row in rows
    ]
    return destinations, {
        "set": "public",
        "hospitals": len(hospitals),
        "hospital_facility_ids": sorted(str(row["facility_id"]) for row in hospitals),
        "main_road_entries": len(entries),
        "main_road_entry_node_ids_sha256": entry_nodes_sha256,
        "ddpm_shelters_used": 0,
        "same_as_the_e4_receipt": True,
    }


def reporting_units(
    boundaries: Path, context: Mapping[str, Any], receipt: Mapping[str, Any], v1b: Mapping[str, Any]
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Return the tambon polygons of the context's reporting geometry: the units a link can belong to.

    They are the COD-AB ``tha_admin3`` polygons that intersect the routing geometry, read as the E4 build read
    them. Their union must have the canonical SHA-256 the context records for its reporting geometry.

    Raises:
        BuildError: when the boundary file, AOI-02 or the routing geometry is not the one protocol v1b names,
            or the units differ from the reporting units of the context.
    """

    import pyogrio
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union

    corridor = v1b["corridor_polygon"]
    construction = corridor["construction"]
    boundaries_sha256 = planning_context.sha256_file(boundaries)
    if boundaries_sha256 not in construction["boundary_source"] or boundaries_sha256 != receipt["input_hashes"]["boundaries_sha256"]:
        raise BuildError("the boundary file is not the one protocol v1b and the E4 receipt name")
    aoi_path = ROOT / construction["base"]
    if planning_context.sha256_file(aoi_path) != construction["base_sha256"]:
        raise BuildError("AOI-02 differs from the file protocol v1b names")
    routing_path = ROOT / corridor["geometry_file"]["path"]
    routing_sha256 = planning_context.sha256_file(routing_path)
    if routing_sha256 != corridor["geometry_file"]["sha256"] or routing_sha256 != receipt["routing_source"]["sha256"]:
        raise BuildError("the routing geometry file is not the one protocol v1b and the E4 receipt name")
    routing_geojson = read_json(routing_path)["features"][0]["geometry"]
    if geometry_sha256(routing_geojson) != receipt["routing_source"]["geometry_sha256"]:
        raise BuildError("the routing geometry differs from the geometry the E4 receipt names")
    routing = shape(routing_geojson)
    west, south, east, north = unary_union([shape(feature["geometry"]) for feature in read_json(aoi_path)["features"]]).bounds
    margin = BOUNDARY_WINDOW_MARGIN_DEG
    window = box(west - margin, south - margin, east + margin, north + margin)
    admin3 = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=["adm3_pcode"], bbox=window.bounds)
    intersecting = admin3[admin3.geometry.intersects(routing)]
    union_sha256 = _canonical_hash(mapping(unary_union(list(intersecting.geometry))))
    if len(intersecting) != receipt["context_call"]["reporting_units_intersecting"]:
        raise BuildError("the number of reporting units differs from the E4 receipt")
    if union_sha256 != context["input_hashes"]["reporting_geometry"]:
        raise BuildError("the union of the reporting units is not the reporting geometry of the context")
    units = sorted(zip((str(code) for code in intersecting["adm3_pcode"]), intersecting.geometry), key=lambda unit: unit[0])
    return units, {
        "rule": "The COD-AB tha_admin3 polygons that intersect the routing geometry: the reporting units of the E4 "
                "context. A link belongs to the unit that holds the midpoint of its edge (drafter reading DR-B06).",
        "units": len(units),
        "boundaries_sha256": boundaries_sha256,
        "routing_file_sha256": routing_sha256,
        "union_canonical_sha256": union_sha256,
        "union_is_the_reporting_geometry_of_the_context": True,
    }


def _cut(links: Sequence[Mapping[str, Any]], size: int) -> dict[str, Any]:
    """Describe the first ``size`` links: flows at both ends, ties, road classes and flags."""

    top = list(links[:size])
    flows = Counter(row["spt_flow_residents"] for row in top)
    tie_at_the_cut = len(links) > size and bool(top) and links[size]["spt_flow_residents"] == top[-1]["spt_flow_residents"]
    return {
        "links": len(top),
        "largest_flow_residents": _rounded(top[0]["spt_flow_residents"], 3) if top else None,
        "smallest_flow_residents": _rounded(top[-1]["spt_flow_residents"], 3) if top else None,
        "links_that_share_their_flow_with_another": sum(count for count in flows.values() if count > 1),
        "tie_at_the_cut_broken_by_edge_id": tie_at_the_cut,
        "distinct_osm_ways": len({row["osm_way_id"] for row in top if row["osm_way_id"] is not None}),
        "by_road_class": dict(sorted(Counter(str(row["road_class"]) for row in top).items())),
        "graph_bridges": sum(row["graph_bridge"] for row in top),
        "osm_bridge_yes": sum(row["osm_bridge"] for row in top),
        "grade_join_connectors": sum(row["edge_kind"] == JOIN_EDGE_KIND for row in top),
    }


def connector_ties(links: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count the ranked grade-join connectors that the tie-break on the edge ID puts ahead of a road edge.

    Args:
        links: The ranked rows of ``rank_links``, in rank order.

    Returns:
        ``sharing_their_flow_with_a_road_edge``: connectors whose flow is exactly the flow of at least one
        ranked road edge; the connector ID sorts first, so each is ranked ahead of those road edges.
        ``ranked_directly_ahead_of_a_road_edge_with_the_same_flow``: those among them whose next rank is such a
        road edge (the others are followed by another connector with the same flow).
    """

    road_flows = {row["spt_flow_residents"] for row in links if row["edge_kind"] != JOIN_EDGE_KIND}
    return {
        "sharing_their_flow_with_a_road_edge": sum(
            row["edge_kind"] == JOIN_EDGE_KIND and row["spt_flow_residents"] in road_flows for row in links),
        "ranked_directly_ahead_of_a_road_edge_with_the_same_flow": sum(
            row["edge_kind"] == JOIN_EDGE_KIND and following["edge_kind"] != JOIN_EDGE_KIND
            and following["spt_flow_residents"] == row["spt_flow_residents"]
            for row, following in zip(links, links[1:])),
    }


def single_closure_note(top_20_bridges: int, top_200_bridges: int) -> str:
    """Say what closing one top-20 link on its own can do, from the graph bridges among the ranked links.

    Removing an edge that is not a graph bridge leaves every node connected to the nodes it was connected to, so
    nobody loses every route. The sentence follows from the bridge flags alone; no reroute is run for it.
    """

    ending = "This follows from the graph alone; no reroute was run."
    if top_20_bridges == 0:
        among_200 = "and none among the top 200" if top_200_bridges == 0 else f"and {top_200_bridges} among the top 200 are"
        return (
            f"No link among the top 20 is a graph bridge, {among_200}. Removing an edge that is not a graph bridge "
            "leaves every node connected to the nodes it was connected to, so closing any single top-20 link on its "
            f"own isolates nobody: every resident with a baseline route keeps one. {ending}"
        )
    return (
        f"{top_20_bridges} of the top 20 links are graph bridges ({top_200_bridges} of the top 200). Closing one of "
        "them on its own may leave residents without a route; only a reroute says how many. Closing any other "
        f"single top-20 link isolates nobody, because an edge that is not a graph bridge has a way round. {ending}"
    )


def run_statement(
    earlier_runs: Sequence[Mapping[str, Any]], generated_at_utc: str, table_sha256: str, wording: str
) -> dict[str, Any]:
    """Say what kind of run this is, from the runs it supersedes, and what that means for the recorded ranking.

    Args:
        earlier_runs: The runs this one supersedes, oldest first; empty for a first run. Each has ``run_kind``,
            ``generated_at_utc``, ``evidence_sha256`` (the replaced receipt), ``top_20_sha256``,
            ``ranking_table_sha256`` and ``replaced_because``.
        generated_at_utc: The generation time of this run.
        table_sha256: The SHA-256 of the ranking table this run computed.
        wording: Protocol v1b's sentence on where the ranking's SHA-256 is recorded, quoted as the file has it.

    Returns:
        ``run_kind``, ``status``, ``status_note``, ``binding_note`` and ``run_history``.

    Raises:
        BuildError: when the earlier runs are malformed, out of order or not earlier than this run.
        OpenPointError: when the table differs from the one the first run recorded.
    """

    earlier = [dict(run) for run in earlier_runs]
    for position, run in enumerate(earlier):
        if set(run) != EARLIER_RUN_KEYS or run["run_kind"] != (FIRST_RUN if position == 0 else SUPERSEDING_RUN):
            raise BuildError("the earlier runs of the receipt are not a first run followed by superseding runs")
        if not str(run["replaced_because"]).strip() or any(
                len(str(run[key])) != 64 for key in ("evidence_sha256", "top_20_sha256", "ranking_table_sha256")):
            raise BuildError("an earlier run needs the reason it was replaced and three SHA-256 values")
    times = [run["generated_at_utc"] for run in earlier] + [generated_at_utc]
    if times != sorted(set(times)):
        raise BuildError("a superseding run must be generated after every run it supersedes")
    quoted = f'Protocol v1b critical_link_selection.ranking_output (owner choice 10) says: "{wording}"'
    if not earlier:
        return {
            "run_kind": FIRST_RUN,
            "status": STATUS_BY_RUN_KIND[FIRST_RUN],
            "status_note": (
                f"First run of plan task E6 on the E4 planning context of record. {UNREVIEWED_NOTE} {quoted} The "
                "receipt of this run is the receipt of the first run of the ranking, so the SHA-256 of the whole "
                f"ranking table that it records (outputs.ranking_table.sha256) is that record. {OPEN_POINTS_NOTE}"
            ),
            "binding_note": (
                f"{quoted} This is the receipt of the first run of the ranking, and this SHA-256 is that record. "
                "The top 20, the S3 links of each tambon and the S3b bridge edges are read from this table. The "
                "script computes no score and cannot see what other tasks have run: the generation time of this "
                "receipt is what places the record before any scoring."
            ),
            "run_history": {
                "earlier_runs": [],
                "first_run_generated_at_utc": generated_at_utc,
                "ranking_table_sha256_recorded_by_the_first_run": table_sha256,
                "this_run_computed_that_ranking_table": True,
                "note": "This is the first run.",
            },
        }
    first, previous = earlier[0], earlier[-1]
    if table_sha256 != first["ranking_table_sha256"] or any(
            run["ranking_table_sha256"] != first["ranking_table_sha256"] for run in earlier):
        raise OpenPointError(
            "the ranking table of this run is not the one the first run recorded (SHA-256 "
            f"{first['ranking_table_sha256']}). Protocol v1b does not say whether a later run may change a recorded "
            "ranking (open point E6-OP6), so nothing is written."
        )
    if len(earlier) == 1:
        superseded = f"supersedes the first run, generated {first['generated_at_utc']}"
    else:
        superseded = (f"supersedes the run generated {previous['generated_at_utc']} ({len(earlier)} earlier runs; "
                      f"the first run was generated {first['generated_at_utc']})")
    return {
        "run_kind": SUPERSEDING_RUN,
        "status": STATUS_BY_RUN_KIND[SUPERSEDING_RUN],
        "status_note": (
            f"A run of plan task E6 on the E4 planning context of record that {superseded}. "
            f"{UNREVIEWED_NOTE} {quoted} The receipt of the first run recorded the SHA-256 "
            f"{first['ranking_table_sha256']} for the whole ranking table. This run computed the same table, so that "
            f"record stands and the receipt of this run repeats it. {OPEN_POINTS_NOTE}"
        ),
        "binding_note": (
            f"{quoted} The receipt of the first run (generated {first['generated_at_utc']}) is that record. This run "
            "computed the same table, so this SHA-256 repeats the record and replaces nothing. A superseding run "
            "whose table differs stops and writes nothing (open point E6-OP6). The top 20, the S3 links of each "
            "tambon and the S3b bridge edges are read from this table. The script computes no score and cannot see "
            "what other tasks have run: the generation time of the first run is what places the record before any "
            "scoring."
        ),
        "run_history": {
            "earlier_runs": earlier,
            "first_run_generated_at_utc": first["generated_at_utc"],
            "ranking_table_sha256_recorded_by_the_first_run": first["ranking_table_sha256"],
            "this_run_computed_that_ranking_table": True,
            "note": "The earlier runs, oldest first. Each was replaced by the run after it; evidence_sha256 is the "
                    "SHA-256 of the receipt that was replaced. A replaced file is in the Git history if its run was "
                    "committed.",
        },
    }


def assemble(
    context: Mapping[str, Any],
    edges: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
    units: Sequence[tuple[str, Any]],
    *,
    generated_at_utc: str,
    header: Mapping[str, Any],
    paths: Mapping[str, str],
    earlier_runs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Rank the links of a context and assemble the top-20 file, the ranking table and the receipt body.

    Everything here is a function of the arguments, so the same inputs, generation time and earlier runs give
    the same bytes.

    Args:
        context: The planning context (``population``, ``node_coordinates``, ``canonical_sha256``,
            ``source_metadata``).
        edges: The baseline vehicle edges: context edges and grade-join connectors.
        destinations: The destination set, each row with its ``service_type``.
        units: ``(unit ID, polygon)`` pairs for drafter reading DR-B06.
        generated_at_utc: The generation time written into both files.
        header: The parts of the receipt the caller checked: ``case``, ``protocols_in_force``, ``rule``,
            ``inputs``, ``graph``, ``destinations``, ``units`` and ``boundaries_valid_on``.
        paths: Logical paths of the ``top20`` file and the ``receipt``.
        earlier_runs: The runs this one supersedes, oldest first (see ``run_statement``); empty for a first run.

    Returns:
        ``top20`` (bytes), ``ranking_table`` (bytes) and ``receipt_body`` (a dict without ``run``).

    Raises:
        OpenPointError: when a grade-join connector is among the top 20, or the ranking table of a superseding
            run differs from the one the first run recorded.
    """

    if not str(generated_at_utc).strip():
        raise BuildError("a run needs a generation time")
    top_n = critical_links.OUTPUT_TOP_N
    reroute_n = critical_links.FULL_REROUTE_TOP_N
    per_unit = int(header["rule"]["links_per_unit"])
    ranking = critical_links.rank_links(edges, context["population"], destinations)
    links = ranking["links"]
    connectors = [row for row in links if row["edge_kind"] == JOIN_EDGE_KIND]
    if any(row["rank"] <= top_n for row in connectors):
        raise OpenPointError(
            "a grade-join connector is among the top 20 links (ranks "
            + ", ".join(str(row["rank"]) for row in connectors if row["rank"] <= top_n)
            + "). Protocol v1b does not say whether a connector can be a critical link, so nothing is written."
        )
    assigned = critical_links.assign_units(links, context["node_coordinates"], units)
    table = critical_links.ranking_table(links, assigned, context_canonical_sha256=context["canonical_sha256"])
    table_sha256 = critical_links.sha256_bytes(table)
    statement = run_statement(
        earlier_runs, generated_at_utc, table_sha256, header["rule"]["ranking_output_binding_wording"])
    osm_retrieved_at = context["source_metadata"]["osm"]["retrieved_at_utc"]
    source_timestamps = {
        "osm_retrieved_at_utc": osm_retrieved_at,
        "population_year_represented": 2020,
        "boundaries_valid_on": header["boundaries_valid_on"],
        "context_generated_at": header["inputs"]["context"]["context_generated_at"],
    }
    provenance = {
        "status": statement["status"],
        "status_note": statement["status_note"],
        "generated_at_utc": generated_at_utc,
        "source_timestamp": osm_retrieved_at,
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "assumptions": list(ASSUMPTIONS),
        "official_warning": False,
        "operational_status": "non_operational",
    }
    top = [{**row, "in_flood_extent": None} for row in links[:top_n]]
    collection = {
        "type": "FeatureCollection",
        "name": Path(paths["top20"]).stem,
        "schema_version": TOP_SCHEMA,
        "case": header["case"],
        "travel_mode": VEHICLE,
        "generated_at_utc": generated_at_utc,
        "run_kind": statement["run_kind"],
        "ranking_rule_version": ranking["ranking_rule_version"],
        "context_canonical_sha256": context["canonical_sha256"],
        "ranking_table_sha256": table_sha256,
        "protocol_v1a_sha256": header["protocols_in_force"]["v1a"]["sha256"],
        "protocol_v1b_sha256": header["protocols_in_force"]["v1b"]["sha256"],
        "receipt": paths["receipt"],
        "features": critical_links.link_features(top, context["node_coordinates"], provenance),
    }
    top_bytes = planning_context.encode_json(collection)

    summary = ranking["summary"]
    service = {row["facility_id"]: row["service_type"] for row in destinations}
    by_service: dict[str, list[float]] = {}
    nearest: Counter[str] = Counter()
    for facility_id, residents in ranking["residents_by_destination"].items():
        by_service.setdefault(service[facility_id], []).append(residents)
        nearest[service[facility_id]] += 1
    with_route = summary["connected_residents_with_a_baseline_route"]
    assignment = Counter(row["unit_assignment"] for row in assigned.values())
    top_assignment = Counter(assigned[row["edge_id"]]["unit_assignment"] for row in top)
    reroute_set = [row["edge_id"] for row in links[:reroute_n]]
    # The highest-ranked links of each unit, as scenario S3 reads them from the table. Counts only; no unit is named.
    unit_top: dict[str, list[Mapping[str, Any]]] = {}
    for row in links:
        unit_id = assigned[row["edge_id"]]["unit_id"]
        if unit_id is not None and len(unit_top.setdefault(unit_id, [])) < per_unit:
            unit_top[unit_id].append(row)
    units_with_a_connector_on_top = sum(
        any(row["edge_kind"] == JOIN_EDGE_KIND for row in rows) for rows in unit_top.values())
    ranked_bridges = [row for row in links if row["graph_bridge"]]
    top_20_bridges = sum(row["graph_bridge"] for row in links[:top_n])
    top_200_bridges = sum(row["graph_bridge"] for row in links[:reroute_n])
    closure_note = single_closure_note(top_20_bridges, top_200_bridges)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "generated_at_utc": generated_at_utc,
        "protocol_item": "Plan task E6 (plan 8.1, row E6): protocol v1b critical_link_selection (open item OI-07; "
                         "owner choices 9 and 10; drafter readings DR-B03 and DR-B06)",
        "case": header["case"],
        "travel_mode": VEHICLE,
        "run_kind": statement["run_kind"],
        "status": statement["status"],
        "status_note": statement["status_note"],
        "run_history": statement["run_history"],
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "One baseline ranking of road links by the residents whose baseline route uses them, the graph "
                    "bridges of the baseline graph, and the unit of each ranked link. No flood layer, no closure, no "
                    "reroute, no access loss, no FPPS, no A-E class, no ensemble, and no figure for a single tambon.",
        "source_timestamp": osm_retrieved_at,
        "source_timestamps": source_timestamps,
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocols_in_force": header["protocols_in_force"],
        "rule": header["rule"],
        "rule_as_applied": {
            "ranking_rule_version": ranking["ranking_rule_version"],
            "module": "src/floodguard/critical_links.py",
            "tree": "One multi-source shortest-path tree from every destination, with the comparisons of "
                    "floodguard.evidence_interventions.select_interventions: smallest (minutes, destination ID), "
                    "then smallest (parent node ID, edge ID).",
            "ranked": "Edges with a positive flow, by flow (largest first) and then by edge ID.",
            "graph_bridges": "Flagged on every ranked link (Tarjan). Nothing is added to the ranked set, to the 200 "
                             "edges of the full reroute or to the 20 of the output: the protocol does not say what "
                             "the bridges are added to (open point E6-OP5).",
            "population_snap_limit_m": critical_links.POPULATION_SNAP_LIMIT_M,
            "facility_snap_limit_m": critical_links.FACILITY_SNAP_LIMIT_M,
            "connector_speed_kmh": critical_links.CONNECTOR_SPEED_KMH,
            "unit_assignment_epsg": critical_links.ANALYSIS_EPSG,
        },
        "inputs": header["inputs"],
        "graph": {
            **header["graph"],
            "edges": summary["graph_edges"],
            "nodes": summary["graph_nodes"],
            "nodes_reached_by_the_tree": summary["nodes_reached_by_the_tree"],
            "graph_bridge_edges": summary["graph_bridge_edges"],
        },
        "destinations": {
            **header["destinations"],
            "supplied_to_the_tree": summary["destinations_supplied"],
            "that_are_a_nearest_destination": dict(sorted(nearest.items())),
        },
        "units": header["units"],
        "demand": {
            "source": "WorldPop 2020 cells of the context (the demand area of the case), summed at the road node each "
                      "cell snaps to.",
            "population_cells": len(context["population"]),
            "residents": _rounded(summary["residents"]),
            "residents_connected_to_the_graph": _rounded(summary["residents_connected_to_the_graph"]),
            "residents_not_connected_to_the_graph": _rounded(summary["residents_not_connected_to_the_graph"]),
            "connected_residents_with_a_baseline_route": _rounded(with_route),
            "connected_residents_without_a_baseline_route": _rounded(summary["connected_residents_without_a_baseline_route"]),
            "origin_nodes": summary["origin_nodes"],
            "origin_nodes_with_a_baseline_route": summary["origin_nodes_with_a_baseline_route"],
            "residents_by_nearest_destination_service": {
                key: _rounded(sum(sorted(values))) for key, values in sorted(by_service.items())},
            "share_of_routed_residents_by_nearest_destination_service": {
                key: _rounded(sum(sorted(values)) / with_route) if with_route else None
                for key, values in sorted(by_service.items())},
            "destination_nodes_routed_onward_at_an_equal_time": {
                "nodes": summary["destination_nodes_routed_onward_at_an_equal_time"],
                "nodes_carrying_residents_onward": summary["destination_nodes_carrying_residents_onward_at_an_equal_time"],
                "residents_carried_onward": _rounded(
                    summary["residents_carried_onward_from_a_destination_node_at_an_equal_time"]),
                "note": "Destination nodes that another destination with a smaller ID reaches in exactly the node's "
                        "own entry time, as across a zero-minute grade join between two main-road entries. Every "
                        "resident whose route reaches such a node counts on the edge that leaves it (open point "
                        "E6-OP7).",
            },
            "scope": "Whole frame only. No figure is written for a single tambon.",
        },
        "ranking": {
            "ranked_links": len(links),
            "ranked_links_that_are_graph_bridges": summary["ranked_links_that_are_graph_bridges"],
            "ranked_links_with_osm_bridge_yes": sum(row["osm_bridge"] for row in links),
            "ranked_links_by_road_class": dict(sorted(Counter(
                JOIN_EDGE_KIND if row["edge_kind"] == JOIN_EDGE_KIND else str(row["road_class"]) for row in links).items())),
            "top_20": _cut(links, top_n),
            "top_200": _cut(links, reroute_n),
            "graph_bridges": {
                "in_the_baseline_graph": summary["graph_bridge_edges"],
                "ranked": len(ranked_bridges),
                "among_the_top_20": top_20_bridges,
                "among_the_top_200": top_200_bridges,
                "best_rank": ranked_bridges[0]["rank"] if ranked_bridges else None,
                "flow_residents_at_the_best_rank": (
                    _rounded(ranked_bridges[0]["spt_flow_residents"], 3) if ranked_bridges else None),
                "added_to_the_ranking": 0,
                "reading": "Flagged only. The protocol's line '" + BRIDGE_RULE + "' is not applied as an addition, "
                           "because it does not say what the bridges are added to (open point E6-OP5).",
                "closing_one_top_20_link_on_its_own": closure_note,
            },
            "grade_join_connectors": {
                "ranked": len(connectors),
                "best_rank": connectors[0]["rank"] if connectors else None,
                "among_the_top_20": 0,
                "among_the_top_200": sum(row["rank"] <= reroute_n for row in connectors),
                **connector_ties(links),
                "links_per_unit_read_by_scenario_s3": per_unit,
                "units_where_one_is_among_the_highest_ranked_links_of_the_unit": units_with_a_connector_on_top,
                "note": "Counts only; no unit is named. The run stops for a connector among the top 20 and does "
                        "not stop for one among the highest-ranked links of a unit (open point E6-OP1).",
            },
            "unit_assignment": {
                "units_that_hold_a_ranked_link": len({row["unit_id"] for row in assigned.values() if row["unit_id"]}),
                "ranked_links": dict(sorted(assignment.items())),
                "top_20": dict(sorted(top_assignment.items())),
                "note": "Counts only. The unit of each link is in the ranking table, which is not written into Git.",
            },
            "full_reroute_set": {
                "rule": "Fully reroute only the top 200 ranked edges. No reroute is run here; these are the edges "
                        "the rule names.",
                "edge_ids_in_rank_order": reroute_set,
                "grade_join_connectors_among_them": [
                    row["edge_id"] for row in links[:reroute_n] if row["edge_kind"] == JOIN_EDGE_KIND],
                "edge_ids_sha256": planning_context.sha256_bytes(
                    json.dumps(reroute_set, separators=(",", ":")).encode("ascii")),
            },
        },
        "outputs": {
            "top_20": {
                "path": paths["top20"],
                "sha256": critical_links.sha256_bytes(top_bytes),
                "features": len(top),
            },
            "ranking_table": {
                "sha256": table_sha256,
                "schema_version": critical_links.RANKING_TABLE_SCHEMA,
                "links": len(links),
                "bytes": len(table),
                "binding": header["rule"]["ranking_output_binding"],
                "binding_note": statement["binding_note"],
                "retained_in_git": False,
                "retained_note": "The table names the tambon of every ranked link, so it is not written into Git. "
                                 "It is a function of the inputs: --write-ranking writes these bytes to a path "
                                 "outside the repository, and --verify recomputes this SHA-256.",
            },
        },
        "open_points": [dict(point) for point in OPEN_POINTS],
        "assumptions": list(ASSUMPTIONS),
        "limitations": [*LIMITATIONS, closure_note],
    }
    return {"top20": top_bytes, "ranking_table": table, "receipt_body": receipt}


def receipt_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return a receipt without its ``run`` section: the part a recomputation must reproduce byte for byte."""

    return {key: value for key, value in receipt.items() if key != "run"}


def output_paths(case: str, output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
    """Return where the top-20 file and the receipt of a case go."""

    return {
        "top20": output_dir / f"critical_links_top20_{case}_vehicle.geojson",
        "receipt": output_dir / f"e6_critical_links_{case}_vehicle.json",
    }


def compute(
    args: argparse.Namespace,
    generated_at_utc: str,
    earlier_runs: Sequence[Mapping[str, Any]] = (),
    layout: Layout = REPOSITORY,
) -> dict[str, Any]:
    """Check every input, rank the links and return the outputs in memory."""

    v1b = read_json(layout.protocol_paths["v1b"])
    protocols = protocols_in_force(layout.protocol_paths, layout.receipts)
    rule = selection_rule(v1b)
    e4_receipt, e4_record = load_e4_receipt(args.case, v1b, layout.output_dir)
    context, context_record = load_retained_context(e4_receipt, args.context_root)
    edges, graph = baseline_graph(context, e4_receipt, v1b)
    destinations, destination_record = destination_set(context, e4_receipt)
    units, unit_record = reporting_units(args.boundaries, context, e4_receipt, v1b)
    paths = output_paths(args.case, layout.output_dir)
    header = {
        "case": CASE_IDS[args.case],
        "boundaries_valid_on": e4_receipt["source_timestamps"]["boundaries_valid_on"],
        "protocols_in_force": {
            **protocols, "receipts_file": _logical(layout.receipts, args.context_root), "checked": True},
        "rule": rule,
        "inputs": {
            "e4_receipt": {**e4_record, "is_the_receipt_protocol_v1b_records": True},
            "context": {
                **context_record,
                "canonical_sha256_is_the_one_in_the_e4_receipt": True,
                "note": "The context of record, kept outside Git by the E4 build. Its canonical SHA-256 was "
                        "recomputed from the file before the ranking; nothing was rebuilt.",
            },
            "source_files_of_the_context": dict(sorted(context["input_hashes"].items())),
            "boundaries": {
                "path": _logical(args.boundaries, args.context_root),
                "sha256": unit_record["boundaries_sha256"],
                "layer": "tha_admin3",
            },
            "routing_geometry": {
                "path": v1b["corridor_polygon"]["geometry_file"]["path"],
                "sha256": unit_record["routing_file_sha256"],
            },
        },
        "graph": graph,
        "destinations": destination_record,
        "units": {key: value for key, value in unit_record.items()
                  if key not in {"boundaries_sha256", "routing_file_sha256"}},
    }
    return assemble(
        context, edges, destinations, units, generated_at_utc=generated_at_utc, header=header,
        paths={key: _logical(path, args.context_root) for key, path in paths.items()},
        earlier_runs=earlier_runs,
    )


def _implementation() -> dict[str, Any]:
    import numpy
    import pyproj
    import shapely

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False)
    modules = ("critical_links", "planning_context", "grade_join", "evidence_context", "evidence_scenarios")
    return {
        "base_commit": commit.stdout.strip() or None,
        "working_tree_differs_from_the_base_commit": bool(changed.stdout.strip()) if changed.returncode == 0 else None,
        "script_sha256": planning_context.sha256_file(Path(__file__)),
        **{f"{name}_sha256": planning_context.sha256_file(ROOT / "src" / "floodguard" / f"{name}.py") for name in modules},
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "shapely": shapely.__version__,
        "geos": ".".join(str(part) for part in shapely.geos_version),
        "pyproj": pyproj.__version__,
    }


def earlier_runs_of(paths: Mapping[str, Path], reason: str | None) -> list[dict[str, Any]]:
    """Return the runs a new run supersedes, oldest first, read from the files that are there.

    The last entry is the run whose files are about to be replaced: its generation time, the SHA-256 of its
    receipt and of its top-20 file, the SHA-256 of its ranking table and the reason it is replaced.

    Raises:
        BuildError: when files of an earlier run exist and no reason is given, or the earlier run cannot be
            recorded faithfully (the receipt is missing, or the top-20 file is not the one it records).
    """

    if not any(path.exists() for path in paths.values()):
        return []
    if not (reason and reason.strip()):
        raise BuildError("an earlier run exists; pass --supersede with the reason to replace it")
    if not (paths["receipt"].is_file() and paths["top20"].is_file()):
        raise BuildError("an earlier run left only one of its two files, so it cannot be recorded; nothing is replaced")
    replaced = json.loads(paths["receipt"].read_text(encoding="ascii"))
    top_20_sha256 = planning_context.sha256_file(paths["top20"])
    if top_20_sha256 != replaced["outputs"]["top_20"]["sha256"]:
        raise BuildError("the top-20 file is not the one its receipt records, so the earlier run cannot be recorded; "
                         "nothing is replaced")
    return [
        *(dict(run) for run in replaced.get("run_history", {}).get("earlier_runs", [])),
        {
            "run_kind": replaced["run_kind"],
            "generated_at_utc": replaced["generated_at_utc"],
            "evidence_sha256": planning_context.sha256_file(paths["receipt"]),
            "top_20_sha256": top_20_sha256,
            "ranking_table_sha256": replaced["outputs"]["ranking_table"]["sha256"],
            "replaced_because": reason.strip(),
        },
    ]


def run_build(args: argparse.Namespace, layout: Layout = REPOSITORY) -> dict[str, Any]:
    """Run the ranking once and write the top-20 file and the receipt; return a short summary."""

    paths = output_paths(args.case, layout.output_dir)
    earlier = earlier_runs_of(paths, args.supersede)
    started = _utc_now()
    clock = time.perf_counter()
    outputs = compute(args, _utc_now(), earlier, layout)
    body = outputs["receipt_body"]
    run = {
        "run_started_at_utc": started,
        "run_finished_at_utc": _utc_now(),
        "wall_time_seconds": round(time.perf_counter() - clock, 1),
        "implementation": _implementation(),
        "machine": {"system": platform.system(), "release": platform.release(), "logical_processors": os.cpu_count()},
        "ranking_table_written_to": None,
        "note": RUN_NOTE,
    }
    if args.write_ranking is not None:
        args.write_ranking.parent.mkdir(parents=True, exist_ok=True)
        args.write_ranking.write_bytes(outputs["ranking_table"])
        run["ranking_table_written_to"] = _logical(args.write_ranking, args.context_root)
    paths["top20"].write_bytes(outputs["top20"])
    paths["receipt"].write_bytes(planning_context.encode_json({**body, "run": run}))
    return {
        "case": body["case"],
        "run_kind": body["run_kind"],
        "earlier_runs": len(earlier),
        "receipt": _logical(paths["receipt"], args.context_root),
        "receipt_sha256": planning_context.sha256_file(paths["receipt"]),
        "top_20": body["outputs"]["top_20"],
        "ranking_table_sha256": body["outputs"]["ranking_table"]["sha256"],
        "ranked_links": body["ranking"]["ranked_links"],
        "wall_time_seconds": run["wall_time_seconds"],
    }


def run_verify(args: argparse.Namespace, layout: Layout = REPOSITORY) -> dict[str, Any]:
    """Recompute the ranking with the receipt's generation time and earlier runs and compare byte for byte.

    Nothing is written. The run kind, the status and every note are recomputed from the earlier runs the receipt
    lists, so a receipt that lists an earlier run and calls itself a first run does not verify.
    """

    paths = output_paths(args.case, layout.output_dir)
    if not paths["receipt"].is_file():
        raise BuildError("there is no receipt of this case to verify")
    committed = json.loads(paths["receipt"].read_text(encoding="ascii"))
    earlier = committed.get("run_history", {}).get("earlier_runs", [])
    outputs = compute(args, committed["generated_at_utc"], earlier, layout)
    problems = []
    if not paths["top20"].is_file() or paths["top20"].read_bytes() != outputs["top20"]:
        problems.append("top_20: the committed file differs from the recomputation byte for byte")
    if planning_context.encode_json(receipt_body(committed)) != planning_context.encode_json(outputs["receipt_body"]):
        problems.append("receipt_without_run: the committed receipt differs from the recomputation byte for byte")
    if committed["outputs"]["ranking_table"]["sha256"] != critical_links.sha256_bytes(outputs["ranking_table"]):
        problems.append("ranking_table: the SHA-256 in the receipt differs from the recomputation")
    return {
        "verified": not problems,
        "case": committed["case"],
        "run_kind": committed.get("run_kind"),
        "receipt": _logical(paths["receipt"], args.context_root),
        "compared": ["top_20", "receipt_without_run", "ranking_table_sha256"],
        "problems": problems,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=sorted(CASE_IDS), default="se1")
    parser.add_argument("--context-root", type=Path, default=os.environ.get(ENV_ROOT),
                        help=f"the external data root (default: the environment variable {ENV_ROOT})")
    parser.add_argument("--boundaries", type=Path,
                        help="COD-AB file; default <context root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip")
    parser.add_argument("--write-ranking", type=Path,
                        help="also write the whole ranking table here; it names tambons, so the path must be outside Git")
    parser.add_argument("--supersede", help="the reason for replacing the files of an earlier run")
    parser.add_argument("--verify", action="store_true", help="recompute and compare with the committed files")
    args = parser.parse_args(argv)
    if args.context_root is None:
        parser.error(f"pass --context-root or set {ENV_ROOT}")
    args.context_root = Path(args.context_root)
    for name in ("context_root", "write_ranking"):
        value = getattr(args, name)
        if value is not None and (value.resolve() == ROOT.resolve() or ROOT.resolve() in value.resolve().parents):
            parser.error(f"--{name.replace('_', '-')} must be outside the repository")
    if args.verify and (args.supersede or args.write_ranking):
        parser.error("--verify writes nothing; leave out --supersede and --write-ranking")
    if args.boundaries is None:
        args.boundaries = args.context_root / "open_context" / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
    return args


def main(argv: list[str] | None = None, layout: Layout = REPOSITORY) -> int:
    """Run or verify the baseline critical-link ranking of a case and print a JSON summary."""

    args = parse_args(argv)
    try:
        if args.verify:
            result = run_verify(args, layout)
            print(json.dumps(result))
            return 0 if result["verified"] else 1
        print(json.dumps(run_build(args, layout)))
    except OpenPointError as error:
        print(json.dumps({"stopped": "the protocol does not decide this case", "reason": str(error)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
