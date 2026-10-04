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
  ranking table (owner choice 10 binds the ranking by that hash in the receipt
  of the first scoring run).

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
  a connector can be a critical link.

It reads no flood layer and computes no closure, no reroute, no access loss, no
FPPS, no A-E class and no ensemble. A first run is never replaced silently:
``--supersede`` takes the reason. ``--verify`` recomputes everything with the
generation time of the receipt and compares the top-20 file and the receipt
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
from typing import Any

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
STATUS = "first_run_unreviewed_candidates"
STATUS_NOTE = (
    "First run of plan task E6 on the E4 planning context of record. The links are unreviewed candidates: the desk "
    "check of the top 20 (plan task V1) has not been done, and no link is an observed closure. Owner choice 10 binds "
    "the ranking by the SHA-256 of the whole ranking table in the receipt of the first scoring run."
)
CONFIDENCE_BASIS = (
    "OSM roads and hospitals are unverified map records, and WorldPop 2020 is a modelled resident count. Routes are "
    "modelled class speeds on an undirected graph, and the grade joins are coordinate coincidences whose passability "
    "is unknown. No link was checked against imagery, on the ground or by a reviewer."
)
ASSUMPTIONS = (
    "A resident's baseline route is the fastest modelled vehicle route from the road node their WorldPop 2020 cell "
    "snaps to (within 250 m) to the nearest destination: an OSM hospital in the routing context or a main-road entry "
    "(a node of a trunk or primary edge, links included). One shortest-path tree serves both kinds of destination, "
    "so a route ends at the first destination it meets (owner choice 9).",
    "The flow of a link is the number of residents whose baseline route uses it (WorldPop 2020 residents at each "
    "origin node; drafter reading DR-B03). It measures use. Another route may exist, and the flow does not say what "
    "closing the link would cost.",
    "Links are ranked by flow, and equal flows by edge ID. Equal routes go to the smaller destination ID, then to the "
    "smaller parent node ID and edge ID, as in floodguard.evidence_interventions.select_interventions.",
    "An edge is the straight segment between two road nodes, so one street is many edges. Edges of a street with no "
    "resident between them carry the same flow and take neighbouring ranks.",
    "graph_bridge is true when removing the edge disconnects the modelled graph (Tarjan). osm_bridge repeats the OSM "
    "tag bridge=yes. Neither shows that a structure exists or what state it is in.",
    "in_flood_extent is null because no flood layer is read. The flag is added for each flood input when a case is "
    "assessed.",
    "Road times are fixed class speeds on an undirected graph. One-way rules, turn restrictions and road condition "
    "are not represented. A grade join shows that two ways end at the same OSM coordinate; it does not show that "
    "the transition can be driven.",
    "Routes stay inside the routing context of the case. Roads and destinations outside it are not seen.",
)
LIMITATIONS = (
    "One run on one machine. The ranking depends on the OSM extract, on WorldPop 2020 and on the corridor of record.",
    "Every node of a trunk or primary edge is a main-road entry, so an edge between two such nodes carries no flow: "
    "trunk and primary roads themselves are not ranked, and the ranking finds the roads that lead to them and to "
    "the hospitals. The share of residents whose nearest destination is a main-road entry is under demand.",
    "No reroute was run: the flow is not the number of residents a closure would cut off.",
)
OPEN_POINTS = (
    {
        "id": "E6-OP1",
        "point": "Whether a grade-join connector can be a critical link.",
        "protocol_says": "Rank baseline vehicle edges. A join is a zero-length connector edge between two nodes at "
                         "the same coordinate (grade_join_policy).",
        "what_this_run_does": "The connectors are edges of the baseline graph and are ranked like any other, marked "
                              "edge_kind grade_join. The run stops if one is among the top 20; none was "
                              "(ranking.grade_join_connectors).",
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
)
RUN_NOTE = (
    "Everything outside this section is a function of the inputs and the generation time: --verify recomputes it "
    "byte for byte. This section records the run itself and is not compared."
)


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
        BuildError: when a parameter of the protocol is not the one ``floodguard.critical_links`` applies.
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
    if block["ranking_output"]["binding"] != "bound_in_first_run_receipt":
        raise BuildError("protocol v1b binds the ranking another way than in the first run receipt")
    return {
        "rule": list(block["rule"]),
        "parameters": dict(parameters),
        "demand_weight": block["demand_weight"],
        "destination_set_for_ranking": block["destination_set_for_ranking"],
        "main_road_entry_definition": v1b["facility_sets"]["services"]["main_road_entry"]["definition"],
        "unit_rule": next(cell["selection_rule"] for cell in v1b["scenario_engine_grid"]["cells"] if cell["id"] == "S3"),
        "uses_flood_input": False,
        "ranking_output_binding": block["ranking_output"]["binding"],
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
    """Return the baseline vehicle edges (context edges and grade-join connectors), checked against the join log."""

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
    """Return the public facility set of the context (owner choice 9), checked against the E4 receipt."""

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


def assemble(
    context: Mapping[str, Any],
    edges: Sequence[Mapping[str, Any]],
    destinations: Sequence[Mapping[str, Any]],
    units: Sequence[tuple[str, Any]],
    *,
    generated_at_utc: str,
    header: Mapping[str, Any],
    paths: Mapping[str, str],
) -> dict[str, Any]:
    """Rank the links of a context and assemble the top-20 file, the ranking table and the receipt body.

    Everything here is a function of the arguments, so the same inputs and generation time give the same bytes.

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

    Returns:
        ``top20`` (bytes), ``ranking_table`` (bytes) and ``receipt_body`` (a dict without ``run``).

    Raises:
        OpenPointError: when a grade-join connector is among the top 20.
    """

    if not str(generated_at_utc).strip():
        raise BuildError("a run needs a generation time")
    top_n = critical_links.OUTPUT_TOP_N
    reroute_n = critical_links.FULL_REROUTE_TOP_N
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
    osm_retrieved_at = context["source_metadata"]["osm"]["retrieved_at_utc"]
    source_timestamps = {
        "osm_retrieved_at_utc": osm_retrieved_at,
        "population_year_represented": 2020,
        "boundaries_valid_on": header["boundaries_valid_on"],
        "context_generated_at": header["inputs"]["context"]["context_generated_at"],
    }
    provenance = {
        "status": STATUS,
        "status_note": STATUS_NOTE,
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
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "generated_at_utc": generated_at_utc,
        "protocol_item": "Plan task E6 (plan 8.1, row E6): protocol v1b critical_link_selection (open item OI-07; "
                         "owner choices 9 and 10; drafter readings DR-B03 and DR-B06)",
        "case": header["case"],
        "travel_mode": VEHICLE,
        "run_kind": "first_run",
        "status": STATUS,
        "status_note": STATUS_NOTE,
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
            "grade_join_connectors": {
                "ranked": len(connectors),
                "best_rank": connectors[0]["rank"] if connectors else None,
                "among_the_top_20": 0,
                "among_the_top_200": sum(row["rank"] <= reroute_n for row in connectors),
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
                "binding_note": "Owner choice 10: the receipt of the first scoring run records this SHA-256, before "
                                "any scoring. The top 20, the S3 links of each tambon and the S3b bridge edges are "
                                "read from this table.",
                "retained_in_git": False,
                "retained_note": "The table names the tambon of every ranked link, so it is not written into Git. "
                                 "It is a function of the inputs: --write-ranking writes these bytes to a path "
                                 "outside the repository, and --verify recomputes this SHA-256.",
            },
        },
        "open_points": [dict(point) for point in OPEN_POINTS],
        "assumptions": list(ASSUMPTIONS),
        "limitations": list(LIMITATIONS),
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


def compute(args: argparse.Namespace, generated_at_utc: str) -> dict[str, Any]:
    """Check every input, rank the links and return the outputs in memory."""

    v1b = read_json(PROTOCOL_PATHS["v1b"])
    protocols = protocols_in_force()
    rule = selection_rule(v1b)
    e4_receipt, e4_record = load_e4_receipt(args.case, v1b)
    context, context_record = load_retained_context(e4_receipt, args.context_root)
    edges, graph = baseline_graph(context, e4_receipt, v1b)
    destinations, destination_record = destination_set(context, e4_receipt)
    units, unit_record = reporting_units(args.boundaries, context, e4_receipt, v1b)
    paths = output_paths(args.case)
    header = {
        "case": CASE_IDS[args.case],
        "boundaries_valid_on": e4_receipt["source_timestamps"]["boundaries_valid_on"],
        "protocols_in_force": {**protocols, "receipts_file": RECEIPTS.relative_to(ROOT).as_posix(), "checked": True},
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
        paths={key: path.relative_to(ROOT).as_posix() for key, path in paths.items()},
    )


def _implementation() -> dict[str, Any]:
    import numpy
    import pyproj
    import shapely

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    modules = ("critical_links", "planning_context", "grade_join", "evidence_context", "evidence_scenarios")
    return {
        "base_commit": commit.stdout.strip() or None,
        "script_sha256": planning_context.sha256_file(Path(__file__)),
        **{f"{name}_sha256": planning_context.sha256_file(ROOT / "src" / "floodguard" / f"{name}.py") for name in modules},
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "shapely": shapely.__version__,
        "geos": ".".join(str(part) for part in shapely.geos_version),
        "pyproj": pyproj.__version__,
    }


def run_build(args: argparse.Namespace) -> dict[str, Any]:
    """Run the ranking once and write the top-20 file and the receipt; return a short summary."""

    paths = output_paths(args.case)
    existing = [path for path in paths.values() if path.exists()]
    supersedes = None
    if existing:
        if not (args.supersede and args.supersede.strip()):
            raise BuildError("a first run exists; pass --supersede with the reason to replace it")
        supersedes = {
            "reason": args.supersede.strip(),
            **{f"{key}_sha256": planning_context.sha256_file(path) for key, path in paths.items() if path.exists()},
        }
        if paths["receipt"].exists():
            supersedes["generated_at_utc"] = read_json(paths["receipt"])["generated_at_utc"]
    started = _utc_now()
    clock = time.perf_counter()
    outputs = compute(args, _utc_now())
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
    if supersedes is not None:
        run["supersedes"] = supersedes
    paths["top20"].write_bytes(outputs["top20"])
    paths["receipt"].write_bytes(planning_context.encode_json({**body, "run": run}))
    return {
        "case": body["case"],
        "receipt": paths["receipt"].relative_to(ROOT).as_posix(),
        "receipt_sha256": planning_context.sha256_file(paths["receipt"]),
        "top_20": body["outputs"]["top_20"],
        "ranking_table_sha256": body["outputs"]["ranking_table"]["sha256"],
        "ranked_links": body["ranking"]["ranked_links"],
        "wall_time_seconds": run["wall_time_seconds"],
    }


def run_verify(args: argparse.Namespace) -> dict[str, Any]:
    """Recompute the ranking with the receipt's generation time and compare byte for byte. Nothing is written."""

    paths = output_paths(args.case)
    if not paths["receipt"].is_file():
        raise BuildError("there is no receipt of this case to verify")
    committed = json.loads(paths["receipt"].read_text(encoding="ascii"))
    outputs = compute(args, committed["generated_at_utc"])
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
        "receipt": paths["receipt"].relative_to(ROOT).as_posix(),
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


def main(argv: list[str] | None = None) -> int:
    """Run or verify the baseline critical-link ranking of a case and print a JSON summary."""

    args = parse_args(argv)
    try:
        if args.verify:
            result = run_verify(args)
            print(json.dumps(result))
            return 0 if result["verified"] else 1
        print(json.dumps(run_build(args)))
    except OpenPointError as error:
        print(json.dumps({"stopped": "the protocol does not decide this case", "reason": str(error)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
