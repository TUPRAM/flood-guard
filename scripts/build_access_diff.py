"""Build the access difference tables of the Mae Sai cases and report the run (plan task E5).

Plan 8.1 row E5: "Access diff (two runs) x services x thresholds; per-tambon table; EQ-04 test; diff-logic
test". For each case (SE1, the 2024 season envelope; O2, the layer of 22 October 2024) and each level of
closure rule v1 (strict, central, permissive) this script makes a baseline run and a flooded run of modelled
access and writes, per tambon, the counts the signed scoring frame names:

* residents with baseline access to a hospital within 30 minutes and to a main-road entry within 15 minutes,
  by vehicle, and those among them who newly lose it (15, 30 and 60 minutes are all reported);
* the newly-lost share, counted only for residents with baseline access (requirement EQ-04);
* residents with a baseline route to any hospital or main-road entry who lose all routes;
* at pitch level only: the same for walking 30 minutes to a DDPM located shelter.

**These tables are the inputs of the access-gap and road-criticality components for plan task E8. They are
not the components. The script computes no component value, no FPPS, no A-E class and no ensemble.** A
closure is a modelled assumption (``closure_basis``), not an observed closure, and nothing written here is an
observation of a flood, a warning of any kind or an operational product. The product 4009 layers are used as
provided; FloodGuard did not validate them.

**What it reads, and what it checks before it computes.** Nothing is rebuilt.

* Protocol v1a and v1b, which must both be in force (``RECEIPTS.jsonl``).
* The planning context of record of task E4 (vehicle), from the path its receipt names under the external
  data root; its canonical SHA-256 is recomputed and must be the one protocol v1b records. Its grade joins,
  hospitals and main-road entries must be those the E4 receipt records.
* A walking context for the shelter service, when one is on disk: a build of the unchanged E4 builder in
  travel mode walking. The E4 build of record is a vehicle context, so the walking context is a candidate
  until the owners accept one (open point E5-OP5); the receipt says which it was. Without one, the shelter
  service is not computed and the receipt says so.
* The flood inputs task E1 wrote, read back through ``floodguard.flood_inputs.read_written_input``; the
  input record and the extent must be the files the registered E1 receipt binds by SHA-256.
* The rights registry (``floodguard.rights``): each product 4009 layer must still have a confirmed record.

**Where things go.** A table whose lineage is public (rights level of every input) is written into
``outputs/planning_v1/``; any other table is written outside Git, under
``<external data root>/proposal_execution/planning_v1/<case>/e5_access_diff/``, beside the licence notice of
the rights record. Every table derived from product 4009 carries CC BY-SA 4.0, the credit and a change
notice. The run receipt is ``outputs/planning_v1/e5_access_diff_<frame>.json``; it and every table in Git are
registered in ``outputs/planning_v1/run_register/``::

    python scripts/build_access_diff.py --frame mae_sai --external-data <external data root> \
        [--walking-context <context_inputs.json of a walking E4 build>] \
        [--development-read "<what was read before this run>"] [--replace --reason "<why>"] [--verify]

Every run is reported. A second run needs ``--replace --reason`` and its receipt names every earlier run.
``--verify`` computes everything again with the generation time of the receipt, compares every table byte
for byte and writes nothing. The measurement of the season envelope against the road graph takes about ten
minutes for each travel mode (``closure_rules.edge_intersections``, unchanged); the receipt records the times.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, flood_inputs, planning_context, rights, season_envelope  # noqa: E402
from floodguard.evidence_context import _context_content_hash  # noqa: E402
from floodguard.evidence_scenarios import (  # noqa: E402
    CONNECTOR_SPEED_KMH,
    FACILITY_SNAP_LIMIT_M,
    MODELLED_ROAD_SPEED_KMH,
    POPULATION_SNAP_LIMIT_M,
    calculate_total_access,
)
from floodguard.grade_join import JOIN_EDGE_KIND, apply_grade_joins, joins_sha256  # noqa: E402

RECEIPT_SCHEMA = "floodguard.access_diff_run_receipt.v1"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
REGISTER_DIR = OUTPUT_DIR / "run_register"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_LABEL = "<external_data_workspace>"
PROCESSED_RELATIVE_PATH = Path("proposal_execution") / "planning_v1"
BOUNDARY_RELATIVE_PATH = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
BOUNDARY_LAYER = "tha_admin3"
UNIT_ID_FIELD = "adm3_pcode"
E1_STAGE_FOLDER = "e1_flood_input"
STAGE_FOLDER = "e5_access_diff"
LICENCE_NOTICE_NAME = "LICENSE_NOTICE.txt"
PUBLIC_SERVICES, PITCH_SERVICES = "public_services", "pitch_services"
FLOOD_LEVELS_RUN: tuple[str, ...] = (flood_inputs.AS_PROVIDED,)
"""The flood level this task runs. The minus and plus levels are an axis of the ensemble (plan task E10)."""
CLOSURE_FRAME = flood_inputs.ROUTING_CONTEXT
DDPM_RIGHTS_LEVEL = rights.PITCH_LEVEL
RECORD, CANDIDATE = "build_of_record", "candidate"

FRAME_SETS: dict[str, dict[str, Any]] = {
    "mae_sai": {
        "title": "Mae Sai",
        "cases": ("SE1", "O2"),
        "run_order": ("O2", "SE1"),
        "case_folders": {"SE1": "se1_mae_sai", "O2": "o2_mae_sai"},
        "context_case": "se1",
        "context_folder": "se1_mae_sai",
        "e1_receipt": "e1_flood_inputs_mae_sai.json",
    },
}

COMPUTES = (
    "For cases SE1 and O2 over the Mae Sai frame, at the flood level as provided and under the strict, central and "
    "permissive levels of closure rule v1: a baseline run and a flooded run of modelled access, and per tambon the "
    "residents with baseline access, the residents newly losing it, the newly-lost share counted only for residents "
    "with baseline access, and the residents with a baseline route to any hospital or main-road entry who lose all "
    "routes. These are inputs of the access-gap and road-criticality components. No component value, no FPPS, no A-E "
    "class and no ensemble."
)
CONFIDENCE_BASIS = (
    "Modelled access on OpenStreetMap roads at fixed class speeds, with WorldPop 2020 modelled residents, under "
    "closures assumed from an unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; "
    "Field_Validation=0) that FloodGuard did not validate. No closure, route, facility or count was checked on the "
    "ground or against an independent source."
)
ASSUMPTIONS = [
    "A closure is a modelled assumption of closure rule v1 (closure_basis), not an observed closure. A flood "
    "intersection does not prove that a road was closed, and an edge outside the extent is unchanged by assumption, "
    "not because it was seen dry.",
    "The product 4009 layers are used as provided: preliminary agency extents that were not checked in the field "
    "(Field_Validation=0). FloodGuard did not validate them.",
    "SE1 is the 2024 season envelope scenario: every area ever mapped as water in the season is treated as flooded at "
    "once, and every road it meets is treated under the closure rule at once. It is not an observation of any day and "
    "not the water of September 2024.",
    "O2 is the layer of 22 October 2024, its own dated case: late-season residual water. It does not describe the "
    "September event.",
    "Each edge is the straight segment between its two nodes in EPSG:32647, and the length inside the extent is "
    "measured on that segment (protocol v1b closure_rule_v1.geometry). The central level applies the 0.25 fraction to "
    "edges tagged bridge=yes or tunnel=culvert only; culvert=* is not read (owner choice 23).",
    "Travel time is the fastest modelled route on an undirected graph from the road node a WorldPop 2020 cell snaps to "
    "(within 250 m) to the nearest destination, plus the connectors of the cell and the destination at 5 km/h. "
    "Vehicle edges use fixed class speeds; walking edges use 5 km/h. One-way rules, turn restrictions, road condition "
    "and the time of day are not represented.",
    "A resident has access within a threshold when the modelled time is at most the threshold. A resident is newly "
    "lost when they had access in the baseline run and do not have it in the flooded run. A resident with no baseline "
    "access is never counted as losing it (requirement EQ-04).",
    "A resident loses all routes when they had a baseline route, of any length, to a hospital or a main-road entry and "
    "have none to any of them in the flooded run. A longer route is not a lost route.",
    "A WorldPop 2020 cell counts for the tambon whose 2022 COD-AB polygon holds its centre (open point E5-OP1). "
    "Residents are modelled 2020 counts, roads are OpenStreetMap as retrieved in July 2026, boundaries are of 2022 and "
    "the flood layers of 2024.",
    "Destinations are the same in both runs. A hospital, a shelter or a main-road entry inside the flood extent stays "
    "a destination (open point E5-OP4).",
]
LIMITATIONS = [
    "One flood level is run: the layer as provided. The minus and plus levels, the corroborated shelter set and the "
    "population vintage are axes of the ensemble (plan task E10) and are not run here.",
    "A resident whose cell does not snap to the graph within 250 m has no modelled access in either run and is in no "
    "numerator and no denominator; the tables give their number per tambon.",
    "A unit where nobody had baseline access, or nobody had a baseline route, has a share of null with a reason code. "
    "The protocols state no value for it (open point E5-OP2).",
    "The permissive level closes every intersected edge, however short the stretch inside the extent; the strict "
    "level closes an edge only when half of it is inside. The three levels are reported side by side and none is a "
    "central estimate of what was passable.",
    "Routes stay inside the routing context of the case. Roads and destinations outside it are not seen.",
    "The third-party satellite imagery UNOSAT and GISTDA used to make the product is not relicensed by these files, "
    "and UNOSAT and GISTDA do not endorse FloodGuard or its use of the product.",
]
NOT_COMPUTED = [
    "access-gap component (0-100)", "road-criticality component (0-100)", "any other component", "FPPS", "A-E class",
    "would-be class", "ensemble cell", "class rule v2 triggers (top-20 link closed on its own; serving facility)",
    "equity difference and ratio by age group", "2SFCA shelter supply", "travel-time summaries per tambon",
    "the minus and plus flood levels", "the corroborated shelter set", "2024-rescaled demand",
    "case O1 (no radar candidate has been delivered to this lane)",
]


class BuildError(ValueError):
    """Raised when an input is not the one a signed file or a registered receipt names."""


@dataclass
class ModeGraph:
    """The baseline graph of one travel mode, its demand cells and the destinations of its services."""

    mode: str
    travel_mode: str
    edges: list[dict[str, Any]]
    nodes: set[str]
    node_coordinates: Mapping[str, Sequence[float]]
    population: list[dict[str, Any]]
    destinations: dict[str, list[dict[str, Any]]]
    record: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    """Return the current UTC time to the second, as the receipts write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def encode(payload: Mapping[str, Any]) -> bytes:
    """Serialise a receipt or a table: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file."""

    return flood_inputs.sha256_file(path)


def path_label(path: Path, root: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        pass
    if external is not None:
        try:
            return f"{EXTERNAL_LABEL}/{resolved.relative_to(external.resolve()).as_posix()}"
        except ValueError:
            pass
    return path.name


def file_record(path: Path, root: Path, external: Path | None) -> dict[str, Any]:
    """Return the label, the SHA-256 and the size of an input file."""

    return {"path": path_label(path, root, external), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def external_path(label: str, external: Path) -> Path:
    """Turn a path a receipt writes under the external data placeholder into a path on this machine."""

    if not label.startswith(EXTERNAL_LABEL + "/"):
        raise BuildError(f"{label} is not a path under the external data root")
    return external / label[len(EXTERNAL_LABEL) + 1:]


# ---------------------------------------------------------------------------
# Inputs, each checked against the file that names it
# ---------------------------------------------------------------------------


def destination_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep what a route needs of a destination: its ID, its node and its snap distance. No name is carried."""

    return [{"facility_id": str(row["facility_id"]), "node_id": row["node_id"], "snap_distance_m": row["snap_distance_m"]}
            for row in rows]


def shelter_destinations(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the DDPM located shelters a context was supplied with that are destinations."""

    return destination_rows([
        row for row in context["facilities"]
        if row.get("service_type") == access_diff.DDPM_LOCATED_SHELTER and row.get("location_status") == "located"
        and row.get("candidate_destination_eligible") is True and row.get("within_routing_context") is True
    ])


def mode_graph(mode: str, context: Mapping[str, Any]) -> ModeGraph:
    """Build the baseline graph of one mode from a planning context: its edges with the grade joins of decision D13.

    Raises:
        BuildError: when the context was built for another travel mode.
    """

    travel_mode = access_diff.CONTEXT_TRAVEL_MODES[mode]
    if context["travel_mode"] != travel_mode:
        raise BuildError(f"the {mode} runs need a context built in travel mode {travel_mode}")
    edges, joins = apply_grade_joins(context)
    destinations = {
        access_diff.HOSPITAL: destination_rows(planning_context.hospital_destinations(context)),
        access_diff.MAIN_ROAD_ENTRY: destination_rows(planning_context.main_road_entries(context)),
        access_diff.DDPM_LOCATED_SHELTER: shelter_destinations(context),
    }
    graph = ModeGraph(mode, travel_mode, edges, access_diff.graph_nodes(edges), context["node_coordinates"],
                      list(context["population"]), destinations)
    graph.record = {
        "travel_mode": travel_mode,
        "context_edges": len(context["edges"]),
        "grade_join_connectors": len(joins),
        "joins_sha256": joins_sha256(joins),
        "road_nodes": len(graph.nodes),
        "demand_cells": len(graph.population),
        "destinations": {name: len(rows) for name, rows in destinations.items()},
        "destinations_snapped_to_the_graph": {
            name: sum(1 for row in rows if row["node_id"] in graph.nodes and row["snap_distance_m"] is not None
                      and row["snap_distance_m"] <= FACILITY_SNAP_LIMIT_M)
            for name, rows in destinations.items()},
    }
    return graph


def load_vehicle_context(v1b: Mapping[str, Any], external: Path, output_dir: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the planning context of record of task E4 and check it against protocol v1b and the E4 receipt.

    Raises:
        BuildError: when the E4 receipt is not the file protocol v1b records, or the retained context is
            missing or does not have the canonical SHA-256 of record (stored and recomputed).
    """

    record = v1b["corridor_polygon"]["e4_build_of_record"]
    receipt_path = root / record["build_receipt_path"]
    if not receipt_path.is_file() or receipt_path.resolve().parent != output_dir.resolve():
        raise BuildError("the E4 receipt protocol v1b names is not in the planning output folder")
    receipt_sha256 = sha256_file(receipt_path)
    if receipt_sha256 != record["build_receipt_sha256"]:
        raise BuildError("the E4 receipt is not the one protocol v1b records")
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    expected = record["context_canonical_sha256"]
    if receipt["run_kind"] != RECORD or receipt["context"]["canonical_sha256"] != expected:
        raise BuildError("the E4 receipt is not the build of record of the context protocol v1b names")
    context_path = external_path(str(receipt["context"]["path"]), external)
    if not context_path.is_file():
        raise BuildError("the retained context of record is missing; it is not rebuilt here")
    context = json.loads(context_path.read_bytes().decode("utf-8"))
    if context.get("canonical_sha256") != expected or _context_content_hash(context) != expected:
        raise BuildError("the retained context does not have the canonical SHA-256 of the context of record")
    graph = mode_graph(access_diff.VEHICLE, context)
    recorded = receipt["grade_joins"]
    if (graph.record["joins_sha256"], graph.record["grade_join_connectors"]) != (recorded["joins_sha256"], recorded["join_count"]):
        raise BuildError("the grade joins of the context differ from those the E4 receipt records")
    facilities = receipt["facilities"]
    entry_nodes = [row["node_id"] for row in graph.destinations[access_diff.MAIN_ROAD_ENTRY]]
    entry_sha256 = planning_context.sha256_bytes(json.dumps(entry_nodes, separators=(",", ":")).encode("ascii"))
    hospitals = sorted(row["facility_id"] for row in graph.destinations[access_diff.HOSPITAL])
    if hospitals != sorted(row["facility_id"] for row in facilities["hospitals_in_routing_context"]):
        raise BuildError("the hospitals of the context differ from those the E4 receipt records")
    if (len(entry_nodes), entry_sha256) != (facilities["main_road_entries"], facilities["main_road_entry_node_ids_sha256"]):
        raise BuildError("the main-road entries of the context differ from those the E4 receipt records")
    return context, {
        "status": "of_record",
        "run_kind": receipt["run_kind"],
        "path": str(receipt["context"]["path"]),
        "file_sha256": sha256_file(context_path),
        "canonical_sha256": expected,
        "canonical_sha256_recomputed": True,
        "context_generated_at": str(context["generated_at"]),
        "receipt": {"path": record["build_receipt_path"], "sha256": receipt_sha256},
        "named_in": "planning_protocol_v1b.json /corridor_polygon/e4_build_of_record",
        "input_hashes": dict(receipt["input_hashes"]),
        "osm_retrieved_at_utc": receipt["source_timestamps"]["osm_retrieved_at_utc"],
        "ddpm_list_file_dated": receipt["source_timestamps"]["ddpm_list_file_dated"],
        "hospital_facility_ids": hospitals,
        "main_road_entry_node_ids_sha256": entry_sha256,
        "baseline_no_route": dict(receipt["baseline_no_route"]["with_grade_joins"]),
    }


def find_walking_context(external: Path, folder: str, given: Path | None) -> Path | None:
    """Return the walking context to use: the one given, else a build of record, else a candidate, else none."""

    if given is not None:
        return given
    base = external / PROCESSED_RELATIVE_PATH / folder
    for name in ("e4_walking", "e4_walking_candidate"):
        if (base / name / "context_inputs.json").is_file():
            return base / name / "context_inputs.json"
    return None


def load_walking_context(path: Path, vehicle: Mapping[str, Any], vehicle_record: Mapping[str, Any], external: Path,
                         output_dir: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a walking context built by the unchanged E4 builder and check it against its receipt and the vehicle context.

    Raises:
        BuildError: when the context has no receipt, its canonical SHA-256 is not the one its receipt names, or
            it was built from other inputs, other demand cells or other supplied shelters than the context of record.
    """

    context = json.loads(path.read_bytes().decode("utf-8"))
    canonical = _context_content_hash(context)
    if context.get("canonical_sha256") != canonical:
        raise BuildError("the walking context does not have the canonical SHA-256 it states")
    candidates = (path.parent / "receipt.json", output_dir / "e4_planning_context_se1_walking.json")
    receipt_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if receipt_path is None:
        raise BuildError("the walking context has no E4 receipt beside it or in the planning output folder")
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    if receipt["travel_mode"] != "walking" or receipt["context"]["canonical_sha256"] != canonical:
        raise BuildError("the E4 receipt of the walking context names another context")
    if receipt["input_hashes"] != vehicle_record["input_hashes"]:
        raise BuildError("the walking context was built from other input files than the context of record")
    for key in ("aoi_geometry", "routing_geometry", "reporting_geometry", "supplied_facilities", "osm", "worldpop"):
        if context["input_hashes"][key] != vehicle["input_hashes"][key]:
            raise BuildError(f"the walking context differs from the context of record in {key}")

    def cells(source: Mapping[str, Any]) -> list[tuple[str, float, float, float]]:
        return sorted((row["population_id"], row["total_population"], row["longitude"], row["latitude"])
                      for row in source["population"])

    if cells(context) != cells(vehicle):
        raise BuildError("the walking context holds other demand cells than the context of record")
    of_record = receipt["run_kind"] == RECORD
    return context, {
        "status": "of_record" if of_record else "candidate",
        "run_kind": receipt["run_kind"],
        "status_note": (
            "A walking build of record of the E4 builder. Its compute window is under run.compute_window in its receipt."
            if of_record else
            "Candidate: a walking build of the unchanged E4 builder without a declared compute window. The E4 build of "
            "record is a vehicle context, and decision R13 accepted a compute window for that build only. The shelter "
            "tables that rest on this context are candidate inputs until the owners accept a walking build (open "
            "point E5-OP5)."),
        "path": path_label(path, root, external),
        "file_sha256": sha256_file(path),
        "canonical_sha256": canonical,
        "canonical_sha256_recomputed": True,
        "context_generated_at": str(context["generated_at"]),
        "receipt": file_record(receipt_path, root, external),
        "receipt_generated_at_utc": receipt["generated_at_utc"],
        "builder_sha256": receipt["run"]["implementation"]["builder_sha256"],
        "same_input_files_as_the_context_of_record": True,
        "same_demand_cells_and_supplied_shelters_as_the_context_of_record": True,
        "compute_window_declared": bool(receipt["run"]["compute_window"]["declared"]),
    }


def read_units(boundaries: Path, unit_ids: Sequence[str]) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Read the unit polygons of the case frame from the COD-AB boundary layer, in longitude and latitude.

    Raises:
        BuildError: when the layer is not in EPSG:4326 or a unit is missing or repeated.
    """

    import pyogrio

    quoted = ", ".join(f"'{unit}'" for unit in unit_ids)
    table = pyogrio.read_dataframe(boundaries, layer=BOUNDARY_LAYER, columns=[UNIT_ID_FIELD, "valid_on"],
                                   where=f"{UNIT_ID_FIELD} IN ({quoted})")
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise BuildError("the boundary layer must be EPSG:4326")
    found = sorted((str(code), geometry) for code, geometry in zip(table[UNIT_ID_FIELD], table.geometry))
    if [code for code, _geometry in found] != sorted(unit_ids):
        raise BuildError("the boundary layer does not hold each unit of the frame exactly once")
    return found, {"layer": BOUNDARY_LAYER, "unit_id_field": UNIT_ID_FIELD, "units": len(found),
                   "valid_on": sorted({str(value)[:10] for value in table["valid_on"]})}


def load_e1_receipt(settings: Mapping[str, Any], output_dir: Path, register_dir: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the receipt of the E1 run and check that it is the registered one.

    Raises:
        BuildError: when the receipt is missing or its SHA-256 is not the one the run register holds.
    """

    path = output_dir / settings["e1_receipt"]
    entry_path = register_dir / settings["e1_receipt"]
    if not path.is_file() or not entry_path.is_file():
        raise BuildError("the E1 receipt or its entry in the run register is missing")
    digest = sha256_file(path)
    entry = json.loads(entry_path.read_text(encoding="ascii"))
    if entry["sha256"] != digest:
        raise BuildError("the E1 receipt is not the one the run register holds")
    return json.loads(path.read_text(encoding="ascii")), {"path": path_label(path, root, None), "sha256": digest,
                                                          "registered_in": path_label(entry_path, root, None)}


def load_flood_input(case_id: str, settings: Mapping[str, Any], e1_receipt: Mapping[str, Any], external: Path,
                     registry: rights.RightsRegistry, hashes: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read one flood input task E1 wrote, as the bytes the E1 receipt binds, and ask the rights registry again.

    Returns:
        The input record, the extents by level (EPSG:32647, clipped to the routing context) and what was read.

    Raises:
        BuildError: when a file is not the one the E1 receipt binds, the input was made under other protocol
            files, or its rights record is no longer the confirmed record the input names.
    """

    folder = external / PROCESSED_RELATIVE_PATH / settings["case_folders"][case_id] / E1_STAGE_FOLDER
    record, extents = flood_inputs.read_written_input(folder)
    bound = {entry["path"]: entry["sha256"] for entry in e1_receipt["outputs"][case_id]["files"]}
    prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{settings['case_folders'][case_id]}/{E1_STAGE_FOLDER}/"
    record_sha256 = sha256_file(folder / flood_inputs.INPUT_RECORD_NAME)
    if bound.get(prefix + flood_inputs.INPUT_RECORD_NAME) != record_sha256:
        raise BuildError(f"the input record of case {case_id} is not the one the E1 receipt binds")
    files: dict[str, Any] = {}
    for level in FLOOD_LEVELS_RUN:
        entry = next(row for row in record["files"] if row.get("what") == "flood_extent" and row["level"] == level
                     and row["frame"] == CLOSURE_FRAME)
        if bound.get(prefix + entry["file"]) != entry["sha256"]:
            raise BuildError(f"the {level} extent of case {case_id} is not the one the E1 receipt binds")
        files[level] = {"path": prefix + entry["file"], "sha256": entry["sha256"], "bytes": entry["bytes"]}
    if record["case_id"] != case_id or dict(record["protocol_sha256"]) != dict(hashes):
        raise BuildError(f"the flood input of case {case_id} was written for another case or under other protocol files")
    grant = registry.require_use(rights.PRODUCT_4009, layer=record["source"]["layer"])
    stated = record["rights"]
    if (grant.record_sha256, grant.rights_level) != (stated["record_sha256"], stated["rights_level"]):
        raise BuildError(f"the rights record of case {case_id} is not the confirmed record its flood input names")
    return record, {level: extents[level][CLOSURE_FRAME] for level in FLOOD_LEVELS_RUN}, {
        "input_id": record["input_id"],
        "input_record": {"path": prefix + flood_inputs.INPUT_RECORD_NAME, "sha256": record_sha256},
        "extents": files,
        "frame": CLOSURE_FRAME,
        "rights_level": grant.rights_level,
    }


# ---------------------------------------------------------------------------
# The runs
# ---------------------------------------------------------------------------


def baseline_runs(graph: ModeGraph, services: Sequence[access_diff.ServiceRule]) -> dict[str, dict[str, float | None]]:
    """Make the baseline run of every service of one mode."""

    return {
        rule.service: access_diff.cell_minutes(graph.population, graph.edges, graph.destinations[rule.service],
                                               baseline_nodes=graph.nodes)
        for rule in services if rule.mode == graph.mode
    }


def entry_state(graph: ModeGraph, closed: set[str]) -> dict[str, int]:
    """Count the main-road entries whose main-road edges, or all of whose edges, a closure result closes."""

    main: dict[str, list[str]] = {}
    every: dict[str, list[str]] = {}
    for edge in graph.edges:
        for node in (edge["from_node"], edge["to_node"]):
            every.setdefault(node, []).append(edge["edge_id"])
            if edge.get("road_class") in planning_context.MAIN_ROAD_CLASSES and edge.get("edge_kind") is None:
                main.setdefault(node, []).append(edge["edge_id"])
    entries = [row["node_id"] for row in graph.destinations[access_diff.MAIN_ROAD_ENTRY]]
    return {
        "main_road_entries": len(entries),
        "entries_with_every_main_road_edge_closed": sum(1 for node in entries if all(edge_id in closed for edge_id in main[node])),
        "entries_with_every_edge_closed": sum(1 for node in entries if all(edge_id in closed for edge_id in every[node])),
    }


def joins_inside_extent(graph: ModeGraph, extent_metres: Any) -> dict[str, int]:
    """Count the grade-join connectors whose coordinate lies inside a flood extent (given in EPSG:32647)."""

    from pyproj import Transformer
    import shapely

    joins = [edge for edge in graph.edges if edge.get("edge_kind") == JOIN_EDGE_KIND]
    if not joins:
        return {"grade_join_connectors": 0, "connectors_with_their_coordinate_inside_the_extent": 0}
    # Lists, not arrays: pyproj treats an array of one element as a single point.
    longitudes = [float(graph.node_coordinates[edge["from_node"]][0]) for edge in joins]
    latitudes = [float(graph.node_coordinates[edge["from_node"]][1]) for edge in joins]
    x, y = Transformer.from_crs(flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS, always_xy=True).transform(longitudes, latitudes)
    points = shapely.points(list(x), list(y))
    shapely.prepare(extent_metres)
    return {"grade_join_connectors": len(joins),
            "connectors_with_their_coordinate_inside_the_extent": int(shapely.intersects(extent_metres, points).sum())}


def reference_check(graph: ModeGraph, service: str, closed_edge_ids: Sequence[str], thresholds: Sequence[int],
                    baseline: Mapping[str, float | None], flooded: Mapping[str, float | None]) -> dict[str, Any]:
    """Compare both runs of one service with ``calculate_total_access`` (unchanged) for a set of closed edges."""

    reference = calculate_total_access(graph.population, graph.edges, graph.destinations[service],
                                       scenario={"closed_edge_ids": list(closed_edge_ids)}, thresholds=tuple(thresholds))
    rows = [row for row in reference["node_results"] if row["snap_status"] == "connected"]
    before = access_diff.access_flags_differ(baseline, {row["population_id"]: row["normal_access_minutes"] for row in rows}, thresholds)
    after = access_diff.access_flags_differ(flooded, {row["population_id"]: row["scenario_access_minutes"] for row in rows}, thresholds)
    return {
        "service": service,
        "mode": graph.mode,
        "closed_edges": len(closed_edge_ids),
        "baseline_run": before,
        "flooded_run": after,
        "same": before["cells_that_differ"] == 0 and after["cells_that_differ"] == 0,
    }


def case_runs(
    case_id: str,
    flood_input_id: str,
    extents_metres: Mapping[str, Any],
    graphs: Mapping[str, ModeGraph],
    baselines: Mapping[str, Mapping[str, Mapping[str, float | None]]],
    services: Sequence[access_diff.ServiceRule],
    arguments: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    unit_ids: Sequence[str],
) -> dict[str, Any]:
    """Make the flooded runs of one case and compare each with the baseline: one entry per flood level and closure level.

    Args:
        case_id: The case (for the record only).
        flood_input_id: The flood input, for ``closure_basis``.
        extents_metres: ``flood level -> extent`` in EPSG:32647, clipped to the routing context.
        graphs: ``mode -> ModeGraph``; ``vehicle`` always, ``walking`` when a walking context was supplied.
        baselines: ``mode -> service -> cell_minutes`` of the baseline run.
        services: The services of the protocols.
        arguments: ``access_diff.closure_arguments``.
        cells: ``access_diff.demand_cells``.
        unit_ids: The units of the case frame.

    Returns:
        ``runs``: per flood level and closure level, the closure summary of each mode, the public-services
        table and, with a walking graph, the pitch-services table; ``checks`` and ``timing_seconds``.
    """

    public = [rule for rule in services if rule.publication_level == access_diff.PUBLIC_LEVEL]
    with_shelter = access_diff.WALKING in graphs
    runs: list[dict[str, Any]] = []
    checks: dict[str, Any] = {"reference": [], "shorter_routes_in_a_flooded_run": 0, "residents_gaining_access": 0.0}
    timings: dict[str, float] = {}
    measured: dict[str, Any] = {}
    for flood_level, extent_metres in extents_metres.items():
        extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
        if not extent.is_valid:
            raise BuildError(f"the {flood_level} extent of case {case_id} is not a valid geometry in longitude and latitude")
        intersections: dict[str, list[dict[str, Any]]] = {}
        for mode, graph in graphs.items():
            clock = time.perf_counter()
            intersections[mode] = closure_rules.edge_intersections(graph.edges, graph.node_coordinates, extent)
            timings[f"{flood_level}_edge_intersections_{mode}"] = round(time.perf_counter() - clock, 1)
            measured[f"{flood_level}_{mode}"] = joins_inside_extent(graph, extent_metres)
        for level in closure_rules.LEVELS:
            clock = time.perf_counter()
            flooded: dict[str, dict[str, float | None]] = {}
            closures: dict[str, Any] = {}
            for mode, graph in graphs.items():
                changed, result = access_diff.flooded_edges(level, graph.edges, intersections[mode],
                                                            flood_input_id=flood_input_id, arguments=arguments)
                closures[mode] = access_diff.closure_summary(result, graph.edges)
                closures[mode].update(measured[f"{flood_level}_{mode}"])
                if mode == access_diff.VEHICLE:
                    closures[mode].update(entry_state(graph, set(result["closed_edge_ids"])))
                for rule in services:
                    if rule.mode != mode:
                        continue
                    flooded[rule.service] = access_diff.cell_minutes(
                        graph.population, changed, graph.destinations[rule.service], baseline_nodes=graph.nodes)
                    before = baselines[mode][rule.service]
                    checks["shorter_routes_in_a_flooded_run"] += sum(
                        1 for key, value in flooded[rule.service].items()
                        if value is not None and before[key] is not None and value < before[key] - 1e-9)
                if mode == access_diff.VEHICLE and level == "permissive":
                    hospital = next(rule for rule in public if rule.service == access_diff.HOSPITAL)
                    checks["reference"].append({
                        "flood_level": flood_level, "closure_level": level,
                        **reference_check(graph, hospital.service, result["closed_edge_ids"], hospital.thresholds_minutes,
                                          baselines[mode][hospital.service], flooded[hospital.service])})
            before_all = {name: minutes for mode in graphs for name, minutes in baselines[mode].items()}
            entry: dict[str, Any] = {
                "flood_level": flood_level,
                "closure_level": level,
                "closure_basis": f"modelled_from_{flood_input_id}",
                "closure": {access_diff.VEHICLE: closures[access_diff.VEHICLE]},
                PUBLIC_SERVICES: access_diff.unit_rows(cells, unit_ids, public, before_all, flooded),
            }
            if with_shelter:
                entry["closure_walking"] = closures[access_diff.WALKING]
                entry[PITCH_SERVICES] = access_diff.unit_rows(cells, unit_ids, services, before_all, flooded)
            tables = [entry[PUBLIC_SERVICES]] + ([entry[PITCH_SERVICES]] if with_shelter else [])
            for table in tables:
                for service in table["whole_frame"]["access"].values():
                    checks["residents_gaining_access"] += math.fsum(
                        row["newly_gained_residents"] for row in service["thresholds_minutes"].values())
            runs.append(entry)
            timings[f"{flood_level}_{level}_runs_and_tables"] = round(time.perf_counter() - clock, 1)
    return {"runs": runs, "checks": checks, "timing_seconds": timings}


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def other_inputs(with_shelters: bool) -> list[dict[str, str]]:
    """List the inputs besides product 4009 whose figures a table holds, each with its licence and credit."""

    listed = [
        {"id": "osm", "name": "OpenStreetMap Thailand extract (Geofabrik), roads and hospitals of the planning context",
         "licence": "ODbL 1.0", "attribution": "(c) OpenStreetMap contributors",
         "used_for": "The road graph, the hospitals and the main-road entries."},
        {"id": "worldpop-2020", "name": "WorldPop Thailand 100 m population 2020 (tha_ppp_2020.tif)",
         "licence": "CC BY 4.0", "attribution": "WorldPop (www.worldpop.org), University of Southampton",
         "used_for": "The residents of each demand cell."},
        {"id": "cod-ab", "name": "HDX Thailand COD-AB subdistrict boundaries (tha_admin3)", "licence": "CC BY-IGO",
         "attribution": "OCHA / HDX Thailand COD-AB", "used_for": "The tambon each demand cell counts for."},
    ]
    if with_shelters:
        listed.append({
            "id": "ddpm-shelters", "name": "DDPM listed shelters, dpm-gd002_final2.csv (open-data 2026-09-21)",
            "licence": "Listed, operating status unverified; pitch level only (decision D8b); no publication scope is "
                       "recorded for it in this repository",
            "attribution": "Department of Disaster Prevention and Mitigation (DDPM), Thailand",
            "used_for": "The located shelters that are the destinations of the walking service. No shelter is named."})
    problems = season_envelope.other_input_problems(listed)
    if problems:
        raise BuildError(f"an input besides the product lacks its licence or credit: {problems}")
    return listed


def licence_block(record: Mapping[str, Any], rules: flood_inputs.FloodInputRules, level: str, with_shelters: bool,
                  notice_label: str) -> dict[str, Any]:
    """Return the licence, the credit and the change notice of one table derived from a product 4009 layer."""

    stated = record["rights"]
    licence = stated["licence"]
    return {
        "applies_to": "Every figure of this file: each is derived from UNOSAT/GISTDA product 4009.",
        **{key: licence[key] for key in ("name", "full_name", "spdx_id", "url", "legal_code_url")},
        "credit": stated["attribution"],
        "share_alike": stated["share_alike"],
        "standard_sentence": rules.standard_4009_sentence,
        "change_notice": (
            f"Changed by FloodGuard: the layer {record['source']['layer']} was repaired (make_valid), projected from "
            "EPSG:4326 to EPSG:32647 and clipped to the routing corridor (plan task E1); road segments were then "
            "measured against it, closure rule v1 was applied to them, and modelled access was compared with and "
            "without those closures. This file holds resident counts per subdistrict, not the layer. Source: "
            f"{stated['attribution']}, {licence['name']}."),
        "rights_record": {"path": stated["record_path"], "sha256": stated["record_sha256"], "record_status": stated["record_status"],
                          "confirmed_by": stated["confirmed_by"], "confirmed_on": stated["confirmed_on"]},
        "flood_input_rights_level": stated["rights_level"],
        "flood_input_rights_level_basis": stated["rights_level_basis"],
        "publication_level": level,
        "publication_level_rule": "Protocol v1a guardrail GR6: the rights level of an output is the minimum across its "
                                  "lineage. Nothing here is written under apps/web/public/.",
        "licence_notice_file": notice_label,
        "other_inputs": other_inputs(with_shelters),
        "not_legal_advice": True,
    }


def table_document(
    case_id: str, service_set: str, level: str, *, generated_at_utc: str, receipt_label: str, record: Mapping[str, Any],
    rules: flood_inputs.FloodInputRules, hashes: Mapping[str, str], services: Sequence[access_diff.ServiceRule],
    runs: Sequence[Mapping[str, Any]], contexts: Mapping[str, Mapping[str, Any]], vehicle_context: Mapping[str, Any],
    flood_files: Mapping[str, Any], units: Mapping[str, Any], unit_ids: Sequence[str], arguments: Mapping[str, Any],
    notice_label: str,
) -> dict[str, Any]:
    """Assemble one per-tambon table: the runs of one case for one set of services, with what it is and its licence."""

    with_shelters = service_set == PITCH_SERVICES
    listed = [rule for rule in services if with_shelters or rule.publication_level == access_diff.PUBLIC_LEVEL]
    walking = contexts.get(access_diff.WALKING)
    status_note = (
        "Written with protocol v1a and v1b in force (protocol_sha256). These are inputs of the access-gap and "
        "road-criticality components for plan task E8. They are not the components and not an FPPS; the components, "
        "the FPPS and the A-E class belong to task E8 and are not here.")
    if with_shelters and walking is not None and walking["status"] != "of_record":
        status_note += (" The shelter service rests on a candidate walking context, so its figures are candidate "
                        "inputs until the owners accept a walking build (open point E5-OP5).")
    return {
        "schema_version": access_diff.UNIT_TABLE_SCHEMA,
        "generated_at_utc": generated_at_utc,
        "receipt_file": receipt_label,
        "access_diff_version": access_diff.ACCESS_DIFF_VERSION,
        "plan_task": "E5: access diff (two runs) x services x thresholds; per-tambon table",
        "case_id": case_id,
        "case_frame": "mae_sai",
        "lane": record["lane"],
        "tier": record["tier"],
        "temporal_relation": record["temporal_relation"],
        "case_reference_date": record["case_reference_date"],
        "service_set": service_set,
        "status": "unit_inputs" if not (with_shelters and walking is not None and walking["status"] != "of_record")
                  else "unit_inputs_candidate_walking_context",
        "status_note": status_note,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "computes": COMPUTES,
        "source_timestamp": record["source_timestamp"],
        "source_timestamps": {
            "flood_input": record["source_timestamp"],
            "osm_retrieved_at_utc": vehicle_context["osm_retrieved_at_utc"],
            "population_year_represented": 2020,
            "tambon_boundaries_valid_on": units["valid_on"],
            **({"ddpm_list_file_dated": vehicle_context["ddpm_list_file_dated"]} if with_shelters else {}),
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": dict(hashes),
        "publication_level": level,
        "licence": licence_block(record, rules, level, with_shelters, notice_label),
        "flood_input": {
            "input_id": record["input_id"],
            "input_name": record["input_name"],
            "label": record.get("label"),
            "used_as_provided": True,
            "field_validation": record.get("field_validation"),
            "levels_run": list(FLOOD_LEVELS_RUN),
            "frame": CLOSURE_FRAME,
            "files": dict(flood_files),
        },
        "contexts": {mode: {key: value[key] for key in ("status", "run_kind", "path", "canonical_sha256")}
                     for mode, value in contexts.items() if with_shelters or mode == access_diff.VEHICLE},
        "closure_rule": {
            "version": closure_rules.CLOSURE_RULE_VERSION,
            "levels": list(closure_rules.LEVELS),
            "length_thresholds_m": dict(arguments["length_thresholds_m"]),
            "delay_factor_k": dict(arguments["delay_factor_k"]),
            "strict_delay_rule": arguments["strict_delay_rule"],
            "culvert_tag_handling": arguments["culvert_tag_handling"],
            "closure_is_an_assumption": "Every run carries closure_basis: modelled_from_<input>. A flood intersection "
                                        "does not prove a road closure.",
        },
        "services": [rule.as_record() for rule in listed],
        "definitions": {
            "baseline_access_residents": "Residents whose modelled time to the nearest destination of the service is at "
                                         "most the threshold in the baseline run.",
            "newly_lost_residents": "Residents with baseline access who do not have access within the threshold in the "
                                    "flooded run. A resident with no baseline access is never counted (EQ-04).",
            "newly_lost_share": "newly_lost_residents / baseline_access_residents; null with a reason when nobody had "
                                "baseline access.",
            "access_gap_inputs": "For each service at its access-gap threshold: what "
                                 "floodguard.normalisation.access_gap takes. An input of the component, not the component.",
            "road_criticality_inputs": "Residents with a baseline route to any hospital or main-road entry, and those "
                                       "among them with no route to any of them in the flooded run: what "
                                       "floodguard.normalisation.road_criticality takes. An input, not the component.",
            "residents_not_connected_to_the_graph": "Residents of cells that do not snap to the graph of the mode "
                                                    "within 250 m. They are in no numerator and no denominator.",
            "unit_rule": "A WorldPop 2020 cell counts for the tambon whose polygon holds its centre (open point E5-OP1).",
        },
        "unit_ids": sorted(unit_ids),
        "runs": [
            {
                "flood_level": item["flood_level"],
                "closure_level": item["closure_level"],
                "closure_basis": item["closure_basis"],
                "closure": {**item["closure"], **({access_diff.WALKING: item["closure_walking"]} if with_shelters else {})},
                **item[service_set],
            }
            for item in runs
        ],
        "open_points": [dict(point) for point in access_diff.OPEN_POINTS],
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }


def whole_frame_summary(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the whole-frame figures of the public services of every run of a case, for the receipt."""

    summary = []
    for item in runs:
        frame = item[PUBLIC_SERVICES]["whole_frame"]
        summary.append({
            "flood_level": item["flood_level"],
            "closure_level": item["closure_level"],
            "closure_basis": item["closure_basis"],
            "closure": item["closure"],
            "residents": frame["residents"],
            "access_gap_inputs": frame["access_gap_inputs"],
            "road_criticality_inputs": frame["road_criticality_inputs"],
            "residents_not_connected_to_the_graph": {
                name: service["residents_not_connected_to_the_graph"] for name, service in frame["access"].items()},
            "cells_in_no_unit": item[PUBLIC_SERVICES]["cells_in_no_unit"],
        })
    return summary


def software_versions() -> dict[str, str]:
    """Return the versions of the libraries that decide the geometry."""

    import numpy
    import pyogrio
    import pyproj
    import shapely

    return {"python": platform.python_version(), "numpy": numpy.__version__, "shapely": shapely.__version__,
            "geos": shapely.geos_version_string, "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str,
            "pyogrio": pyogrio.__version__}


def build(frame_set: str, external: Path, boundaries: Path, *, generated_at_utc: str, walking_context: Path | None = None,
          docs: Path = DOCS, root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
          development_reads: Sequence[str] = ()) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, Any]]:
    """Compute every table of a frame set and the body of the run receipt (nothing is written).

    Returns:
        The files to write into Git (by repository path), the files to write outside Git (by their path under
        the processed-data folder) and the receipt without its time fields.

    Raises:
        BuildError: when an input is not the one a signed file or a registered receipt names.
        ValueError: when a protocol is not in force, or the rights registry refuses a layer.
    """

    timings: dict[str, Any] = {}
    clock = time.perf_counter()
    settings = FRAME_SETS[frame_set]
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    hashes = flood_inputs.protocol_hashes(rules)
    v1a = json.loads((docs / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    services = access_diff.service_rules(v1a, v1b)
    arguments = access_diff.closure_arguments(v1b)
    registry = rights.RightsRegistry(root)

    vehicle_context, vehicle_record = load_vehicle_context(v1b, external, output_dir, root)
    graphs = {access_diff.VEHICLE: mode_graph(access_diff.VEHICLE, vehicle_context)}
    contexts: dict[str, dict[str, Any]] = {access_diff.VEHICLE: vehicle_record}
    walking_path = find_walking_context(external, settings["context_folder"], walking_context)
    if walking_path is not None:
        walking, walking_record = load_walking_context(walking_path, vehicle_context, vehicle_record, external, output_dir, root)
        graphs[access_diff.WALKING] = mode_graph(access_diff.WALKING, walking)
        contexts[access_diff.WALKING] = walking_record
        del walking
    for mode, graph in graphs.items():
        contexts[mode]["graph"] = graph.record
    if vehicle_context["source_metadata"]["osm"]["license_status"] != "odbl_1_0_attribution_and_share_alike_obligations_apply":
        raise BuildError("the context states another licence for OpenStreetMap than the one the tables credit")
    for heavy in ("road_geojson", "facilities_geojson", "osm_facilities_geojson", "connectivity_review", "public_origins", "edges"):
        vehicle_context.pop(heavy, None)

    boundary = file_record(boundaries, root, external)
    if boundary["sha256"] != rules.boundary_file_sha256:
        raise BuildError("the boundary file is not the one protocol v1b names")
    units, unit_summary = read_units(boundaries, rules.reporting_units)
    unit_ids = [unit_id for unit_id, _geometry in units]
    assignment = access_diff.assign_cells(graphs[access_diff.VEHICLE].population, units)
    cells = access_diff.demand_cells(graphs[access_diff.VEHICLE].population, assignment)
    timings["contexts_and_units"] = round(time.perf_counter() - clock, 1)

    clock = time.perf_counter()
    baselines = {mode: baseline_runs(graph, services) for mode, graph in graphs.items()}
    timings["baseline_runs"] = round(time.perf_counter() - clock, 1)
    hospital_run = baselines[access_diff.VEHICLE][access_diff.HOSPITAL]
    residents = {cell["population_id"]: cell["residents"] for cell in cells}
    no_route = math.fsum(residents[key] for key, value in hospital_run.items() if value is None)
    recorded = vehicle_record["baseline_no_route"]
    e4_check = {
        "what": "The baseline vehicle run of the hospital service against the whole-frame figures of the E4 receipt.",
        "connected_residents_without_a_route": {"e4_receipt": recorded["connected_residents_without_a_route"],
                                                "this_run": round(no_route, 6)},
        "graph_connected_residents": {"e4_receipt": recorded["graph_connected_residents"],
                                      "this_run": round(math.fsum(residents[key] for key in hospital_run), 6)},
    }
    e4_check["same"] = all(row["e4_receipt"] == row["this_run"] for row in e4_check.values() if isinstance(row, dict))
    if not e4_check["same"]:
        raise BuildError("the baseline run does not reproduce the whole-frame figures of the E4 receipt")

    e1_receipt, e1_record = load_e1_receipt(settings, output_dir, register_dir, root)
    record_4009, record_4009_sha256 = registry.read_record(rights.PRODUCT_4009)
    if record_4009["required_attribution_text"] != rules.product_4009_credit:
        raise BuildError("the credit of the rights record is not the credit protocol v1a states")
    notice_path = root / record_4009["licence_notice_file"]
    notice = notice_path.read_bytes()
    receipt_label = path_label(receipt_path_for(frame_set, output_dir), root, None)

    git_files: dict[str, bytes] = {}
    external_files: dict[str, bytes] = {}
    outputs: dict[str, Any] = {}
    results: dict[str, Any] = {}
    checks: dict[str, Any] = {"e4_baseline": e4_check, "against_calculate_total_access": [],
                              "shorter_routes_in_a_flooded_run": 0, "residents_gaining_access": 0.0}
    flood_records: dict[str, Any] = {}
    rights_levels: dict[str, Any] = {}
    case_timings: dict[str, Any] = {}
    for case_id in settings["run_order"]:
        clock = time.perf_counter()
        record, extents, flood_record = load_flood_input(case_id, settings, e1_receipt, external, registry, hashes)
        computed = case_runs(case_id, record["input_id"], extents, graphs, baselines, services, arguments, cells, unit_ids)
        checks["against_calculate_total_access"].extend({"case_id": case_id, **row} for row in computed["checks"]["reference"])
        checks["shorter_routes_in_a_flooded_run"] += computed["checks"]["shorter_routes_in_a_flooded_run"]
        checks["residents_gaining_access"] += computed["checks"]["residents_gaining_access"]
        flood_records[case_id] = {**flood_record, "lane": record["lane"], "tier": record["tier"],
                                  "temporal_relation": record["temporal_relation"], "source_timestamp": record["source_timestamp"]}
        folder = f"{settings['case_folders'][case_id]}/{STAGE_FOLDER}"
        written: list[dict[str, Any]] = []
        levels: dict[str, str] = {}
        needs_notice = False
        sets = [PUBLIC_SERVICES] + ([PITCH_SERVICES] if access_diff.WALKING in graphs else [])
        for service_set in sets:
            lineage = [flood_record["rights_level"]] + ([DDPM_RIGHTS_LEVEL] if service_set == PITCH_SERVICES else [])
            level = rights.minimum_level(lineage)
            levels[service_set] = level
            in_git = level == rights.PUBLIC_LEVEL
            notice_label = (path_label(notice_path, root, None) if in_git else LICENCE_NOTICE_NAME)
            document = table_document(
                case_id, service_set, level, generated_at_utc=generated_at_utc, receipt_label=receipt_label, record=record,
                rules=rules, hashes=hashes, services=services, runs=computed["runs"], contexts=contexts,
                vehicle_context=vehicle_record, flood_files=flood_record["extents"], units=unit_summary, unit_ids=unit_ids,
                arguments=arguments, notice_label=notice_label)
            data = encode(document)
            entry = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "what": "unit_table",
                     "service_set": service_set, "publication_level": level, "in_git": in_git, "unit_count": len(unit_ids),
                     "runs": len(computed["runs"])}
            if in_git:
                name = f"{output_dir.relative_to(root).as_posix()}/e5_access_diff_{settings['case_folders'][case_id]}_{service_set}.json"
                git_files[name] = data
                written.append({"path": name, **entry})
            else:
                name = f"{folder}/access_diff_units__{service_set}.json"
                external_files[name] = data
                needs_notice = True
                written.append({"path": f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{name}", **entry})
        if needs_notice:
            external_files[f"{folder}/{LICENCE_NOTICE_NAME}"] = notice
            written.append({"path": f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/{folder}/{LICENCE_NOTICE_NAME}",
                            "sha256": hashlib.sha256(notice).hexdigest(), "bytes": len(notice), "what": "licence_notice"})
        outputs[case_id] = {"files": written}
        rights_levels[case_id] = {"flood_input": flood_record["rights_level"], **levels}
        results[case_id] = {
            "whole_frame_note": "Whole-frame figures of the public services (hospital and main-road entry, vehicle). "
                                "They are inputs of two components, not component values. The per-tambon figures are in "
                                "the tables; the figures of the shelter service are pitch level and stay outside Git.",
            "runs": whole_frame_summary(computed["runs"]),
        }
        case_timings[case_id] = {**computed["timing_seconds"], "case_total": round(time.perf_counter() - clock, 1)}
    timings["cases"] = case_timings
    checks["against_calculate_total_access_all_same"] = all(row["same"] for row in checks["against_calculate_total_access"])
    if not checks["against_calculate_total_access_all_same"]:
        raise BuildError("the runs differ from calculate_total_access on the hospital service")

    walking_record = contexts.get(access_diff.WALKING)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "plan_task": "E5: access diff (two runs) x services x thresholds; per-tambon table; EQ-04 test; diff-logic test",
        "run": f"Access difference of cases {' and '.join(settings['cases'])} over the {settings['title']} frame",
        "status": "run_receipt",
        "status_note": "Receipt of one run on real units, made with protocol v1a and v1b in force. Every run is reported: "
                       "a second run writes a new receipt that names this one. The tables are inputs of the access-gap "
                       "and road-criticality components for plan task E8; they are not the components and not an FPPS.",
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "computes": COMPUTES,
        "source_timestamp": vehicle_record["osm_retrieved_at_utc"],
        "source_timestamps": {
            **{case_id: flood_records[case_id]["source_timestamp"] for case_id in settings["cases"]},
            "osm_retrieved_at_utc": vehicle_record["osm_retrieved_at_utc"],
            "population_year_represented": 2020,
            "tambon_boundaries_valid_on": unit_summary["valid_on"],
            "ddpm_list_file_dated": vehicle_record["ddpm_list_file_dated"],
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": hashes,
        "protocol_state": {name: "in_force" for name in ("v1a", "v1b")},
        "licence": {
            "applies_to": "Every figure of this run that is derived from UNOSAT/GISTDA product 4009: the closure counts "
                          "and the resident counts of cases SE1 and O2, here and in the tables.",
            **{key: record_4009["licence"][key] for key in ("name", "full_name", "spdx_id", "url", "legal_code_url")},
            "credit": record_4009["required_attribution_text"],
            "share_alike": record_4009["share_alike"],
            "standard_sentence": rules.standard_4009_sentence,
            "change_notice": "Changed by FloodGuard: each product 4009 layer was repaired, projected to EPSG:32647 and "
                             "clipped to the routing corridor (plan task E1); road segments were measured against it, "
                             "closure rule v1 was applied and modelled access was compared with and without the "
                             "closures. Each table states its own licence, credit and change notice. Source: "
                             f"{record_4009['required_attribution_text']}, {record_4009['licence']['name']}.",
            "other_inputs": other_inputs(walking_record is not None),
            "not_legal_advice": True,
        },
        "parameters": {
            "frame_set": frame_set,
            "cases": list(settings["cases"]),
            "unit_ids": sorted(unit_ids),
            "flood_levels_run": list(FLOOD_LEVELS_RUN),
            "flood_levels_not_run": [level for level in flood_inputs.LEVELS if level not in FLOOD_LEVELS_RUN],
            "closure_frame": CLOSURE_FRAME,
            "closure_rule": {
                "version": closure_rules.CLOSURE_RULE_VERSION,
                "levels": list(closure_rules.LEVELS),
                "closed_fraction_min": closure_rules.CLOSED_FRACTION_MIN,
                "bridge_culvert_closed_fraction_min": closure_rules.BRIDGE_CULVERT_CLOSED_FRACTION_MIN,
                "delay_min_intersected_length_m": closure_rules.DELAY_MIN_INTERSECTED_LENGTH_M,
                "min_intersection_m": closure_rules.MIN_INTERSECTION_M,
                "length_thresholds_m": arguments["length_thresholds_m"],
                "delay_factor_k": arguments["delay_factor_k"],
                "strict_delays": arguments["strict_delays"],
                "strict_delay_rule": arguments["strict_delay_rule"],
                "culvert_tag_handling": arguments["culvert_tag_handling"],
                "source": "planning_protocol_v1b.json /closure_rule_v1 (parameters, unassigned_road_classes, "
                          "delay_under_strict, culvert_tag_handling; owner choices 4, 5 and 23)",
            },
            "services": [rule.as_record() for rule in services],
            "services_source": "planning_protocol_v1a.json /scoring_frame/components/access_gap_0_100 and "
                               "planning_protocol_v1b.json /facility_sets/services",
            "route_services": list(access_diff.ROUTE_SERVICES),
            "population_snap_limit_m": POPULATION_SNAP_LIMIT_M,
            "facility_snap_limit_m": FACILITY_SNAP_LIMIT_M,
            "connector_speed_kmh": CONNECTOR_SPEED_KMH,
            "modelled_road_speeds_kmh": dict(MODELLED_ROAD_SPEED_KMH),
            "walking_speed_kmh": 5.0,
            "unit_rule": "A demand cell counts for the tambon whose polygon holds its centre (open point E5-OP1).",
            "baseline_runs": "One baseline run per service and mode serves both cases and all three closure levels: it "
                             "reads no flood input.",
        },
        "inputs": {
            "planning_protocol_v1a": {"path": path_label(docs / "planning_protocol_v1a.json", root, external),
                                      "sha256": hashes["planning_protocol_v1a"]},
            "planning_protocol_v1b": {"path": path_label(docs / "planning_protocol_v1b.json", root, external),
                                      "sha256": hashes["planning_protocol_v1b"]},
            "protocol_receipts": file_record(docs / "RECEIPTS.jsonl", root, external),
            "planning_context_vehicle": {key: value for key, value in vehicle_record.items() if key != "graph"},
            "planning_context_walking": ({key: value for key, value in walking_record.items() if key != "graph"}
                                         if walking_record is not None else None),
            "e1_receipt": e1_record,
            "flood_inputs": flood_records,
            "rights_record_4009": {"path": registry.entry(rights.PRODUCT_4009).record_path, "sha256": record_4009_sha256,
                                   "record_status": record_4009["record_status"]},
            "licence_notice_4009": file_record(notice_path, root, external),
            "tambon_boundaries": {**boundary, **unit_summary},
        },
        "rights": {
            "registry": "floodguard.rights.REGISTERED_RECORDS",
            "rule": "The rights registry is asked for each product 4009 layer before its extent is read, and the record "
                    "must be the confirmed record the flood input names. A table goes into Git only when the minimum "
                    "rights level across its lineage is public; any other table stays outside Git. Nothing is written "
                    "under apps/web/public/.",
            "ddpm_shelters": DDPM_RIGHTS_LEVEL,
            "publication_level": rights_levels,
            "written_under_apps_web_public": False,
        },
        "graphs": {mode: graph.record for mode, graph in graphs.items()},
        "demand": {
            "demand_cells": len(cells),
            "residents": math.fsum(cell["residents"] for cell in cells),
            "cells_in_one_unit": sum(1 for cell in cells if cell["unit_id"] is not None),
            "cells_in_no_unit": sum(1 for row in assignment.values() if row["unit_assignment"] == access_diff.CELL_IN_NO_UNIT),
            "cells_in_more_than_one_unit": sum(1 for row in assignment.values()
                                               if row["unit_assignment"] == access_diff.CELL_IN_SEVERAL_UNITS),
        },
        "results": results,
        "shelter_service": (
            {"computed": True, "mode": access_diff.WALKING, "context_status": walking_record["status"],
             "note": "The figures of the shelter service are pitch level and are in the pitch-services tables outside "
                     "Git only. None is in this receipt."}
            if walking_record is not None else
            {"computed": False, "note": "No walking context was on disk, so the shelter service was not computed "
                                        "(open point E5-OP5)."}),
        "checks": checks,
        "outputs": outputs,
        "development_reads": {
            "what": "Reads of the same inputs made while the code was written, before this run. They wrote no table and "
                    "no value for a single tambon. They are listed because every run is reported.",
            "reads": list(development_reads),
        },
        "open_points": [dict(point) for point in access_diff.OPEN_POINTS],
        "not_computed": NOT_COMPUTED,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run loaded, "
                                "identified by their own SHA-256, committed or not.",
            "builder_sha256": sha256_file(Path(__file__)),
            **{f"{name}_module_sha256": sha256_file(root / "src" / "floodguard" / f"{name}.py")
               for name in ("access_diff", "closure_rules", "critical_links", "flood_inputs", "grade_join",
                            "planning_context", "evidence_scenarios", "rights", "rights_basis")},
            "access_diff_version": access_diff.ACCESS_DIFF_VERSION,
            "software": software_versions(),
        },
        "timing_seconds": timings,
    }
    return git_files, external_files, receipt


def output_hashes(outputs: Mapping[str, Any]) -> dict[str, str]:
    """Return the SHA-256 of every file a receipt binds, keyed by its path label."""

    return {entry["path"]: entry["sha256"] for group in outputs.values() for entry in group["files"]}


def receipt_path_for(frame_set: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """Return the one place the receipt of a frame set is written."""

    return output_dir / f"e5_access_diff_{frame_set}.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def figures_of(receipt: Mapping[str, Any]) -> str:
    """Return the figures of a receipt as canonical JSON: the whole-frame results and the closure counts."""

    return _canonical(receipt["results"])


def run(frame_set: str, external: Path, boundaries: Path, *, walking_context: Path | None = None, docs: Path = DOCS,
        root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR,
        replace_reason: str | None = None, development_reads: Sequence[str] = ()) -> dict[str, Any]:
    """Compute the tables, write them, write the receipt and register it; return a short summary.

    Raises:
        FileExistsError: when the receipt exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no receipt exists.
        BuildError, ValueError: see :func:`build`.
    """

    receipt_path = receipt_path_for(frame_set, output_dir)
    if replace_reason is None and receipt_path.exists():
        raise FileExistsError("the receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not receipt_path.exists():
        raise FileNotFoundError("--replace needs an existing receipt")
    started = utc_now()
    clock = time.perf_counter()
    git_files, external_files, receipt = build(
        frame_set, external, boundaries, generated_at_utc=started, walking_context=walking_context, docs=docs, root=root,
        output_dir=output_dir, register_dir=register_dir, development_reads=development_reads)
    supersedes, history = None, None
    if replace_reason is not None:
        previous = json.loads(receipt_path.read_text(encoding="ascii"))
        supersedes = {
            "receipt_sha256": sha256_file(receipt_path),
            "generated_at_utc": previous.get("generated_at_utc"),
            "reason": replace_reason,
            "figures_same": figures_of(previous) == figures_of(receipt),
            "note": "The superseded receipt is named here by its SHA-256, and run_history lists every earlier run. A "
                    "receipt that was replaced before it was committed is not in the Git history: only its SHA-256 "
                    "remains. figures_same compares the whole-frame results and the closure counts of the two receipts; "
                    "a table carries its generation time, so its bytes differ between runs.",
        }
        history = [*previous.get("run_history", []), {
            "generated_at_utc": supersedes["generated_at_utc"], "receipt_sha256": supersedes["receipt_sha256"],
            "superseded_because": replace_reason, "figures_same_as_the_run_that_replaced_it": supersedes["figures_same"]}]
        for stale in output_hashes(previous["outputs"]):
            if not stale.startswith(EXTERNAL_LABEL) and stale not in git_files and (root / stale).is_file():
                (root / stale).unlink()
                (register_dir / Path(stale).name).unlink(missing_ok=True)
    processed_root = external / PROCESSED_RELATIVE_PATH
    for name, data in external_files.items():
        target = processed_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    register_dir.mkdir(parents=True, exist_ok=True)
    for name, data in git_files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        (register_dir / target.name).write_bytes(encode({"path": name, "sha256": hashlib.sha256(data).hexdigest()}))
    finished = utc_now()
    receipt = {
        "schema_version": receipt["schema_version"],
        "generated_at_utc": started,
        "run_kind": "first_run" if supersedes is None else "superseding_run",
        **{key: value for key, value in receipt.items() if key != "schema_version"},
        "timestamps": {"run_started_at_utc": started, "run_finished_at_utc": finished,
                       "wall_time_minutes": round((time.perf_counter() - clock) / 60, 2),
                       "note": "generated_at_utc is the start of the run; the tables carry the same time."},
    }
    if supersedes is not None:
        receipt["supersedes"] = supersedes
        receipt["run_history"] = history
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(encode(receipt))
    receipt_sha256 = sha256_file(receipt_path)
    label = path_label(receipt_path, root, None)
    (register_dir / receipt_path.name).write_bytes(encode({"path": label, "sha256": receipt_sha256}))
    return {"receipt": label, "receipt_sha256": receipt_sha256, "tables_in_git": sorted(git_files),
            "files_outside_git": len(external_files), "generated_at_utc": started,
            "wall_time_minutes": receipt["timestamps"]["wall_time_minutes"],
            "shelter_service_computed": receipt["shelter_service"]["computed"]}


def verify(frame_set: str, external: Path, boundaries: Path, *, walking_context: Path | None = None, docs: Path = DOCS,
           root: Path = ROOT, output_dir: Path = OUTPUT_DIR, register_dir: Path = REGISTER_DIR) -> dict[str, Any]:
    """Compute every table again and compare it with the receipt and with the files on disk; write nothing."""

    receipt = json.loads(receipt_path_for(frame_set, output_dir).read_text(encoding="ascii"))
    git_files, external_files, body = build(
        frame_set, external, boundaries, generated_at_utc=receipt["generated_at_utc"], walking_context=walking_context,
        docs=docs, root=root, output_dir=output_dir, register_dir=register_dir)
    bound = output_hashes(receipt["outputs"])
    prefix = f"{EXTERNAL_LABEL}/{PROCESSED_RELATIVE_PATH.as_posix()}/"
    computed = {**{name: (root / name, data) for name, data in git_files.items()},
                **{prefix + name: (external / PROCESSED_RELATIVE_PATH / name, data) for name, data in external_files.items()}}
    differing, missing = [], []
    for label, (target, data) in computed.items():
        digest = hashlib.sha256(data).hexdigest()
        if bound.get(label) != digest:
            differing.append(label)
        if not target.is_file():
            missing.append(label)
        elif sha256_file(target) != digest:
            differing.append(f"{label} (on disk)")
    unbound = sorted(set(bound) - set(computed))
    figures_same = figures_of(receipt) == figures_of(body) and _canonical(receipt["checks"]) == _canonical(body["checks"])
    return {"verified": not differing and not missing and not unbound and figures_same, "files_compared": len(computed),
            "differing": sorted(set(differing)), "missing_on_disk": missing, "bound_but_not_recomputed": unbound,
            "receipt_figures_and_checks_same": figures_same}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run, or verify the last one."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frame", choices=sorted(FRAME_SETS), required=True)
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--boundaries", type=Path, default=None,
                        help="the COD-AB boundary file; default: <external data root>/" + BOUNDARY_RELATIVE_PATH.as_posix())
    parser.add_argument("--walking-context", type=Path, default=None,
                        help="context_inputs.json of a walking build of the E4 builder; default: the build of record, "
                             "else the candidate, under the external data root")
    parser.add_argument("--development-read", action="append", default=[],
                        help="one read of the inputs made before this run, in a sentence; repeat for each")
    parser.add_argument("--replace", action="store_true", help="make a second run; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the run is repeated (one sentence)")
    parser.add_argument("--verify", action="store_true", help="compute the tables again and compare them with the receipt; write nothing")
    args = parser.parse_args(argv)
    if args.replace != bool((args.reason or "").strip()):
        parser.error("--replace and --reason go together")
    external = args.external_data or (Path(os.environ[EXTERNAL_DATA_VARIABLE]) if os.environ.get(EXTERNAL_DATA_VARIABLE) else None)
    if external is None:
        parser.error(f"give --external-data or set {EXTERNAL_DATA_VARIABLE}")
    boundaries = args.boundaries or external / BOUNDARY_RELATIVE_PATH
    try:
        if args.verify:
            summary = verify(args.frame, external, boundaries, walking_context=args.walking_context)
            print(json.dumps(summary))
            return 0 if summary["verified"] else 1
        summary = run(args.frame, external, boundaries, walking_context=args.walking_context,
                      replace_reason=args.reason.strip() if args.replace else None, development_reads=args.development_read)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
