"""Plan task E4: build the planning context of a case (protocol v1b, open items OI-04 and OI-06).

Plan 8.1 row E4: ``build_planning_context.py`` + ``grade_join.py`` (corridor;
whitelist PII; located-shelter flag). Acceptance: at least 4 hospitals, a
baseline no-route share of at most 10%, a PII whitelist test, and ``load_aois``
still returning 6. Plan 3.1 P2 fixes the call: ``build_context_inputs``
unchanged, with

* ``aoi_geometry``: the demand area of the case;
* ``routing_geometry``: the routing polygon of the case, read from its committed
  file and checked against the SHA-256 that protocol v1b records;
* ``reporting_geometry``: the union of the COD-AB tha_admin3 polygons that
  intersect the routing polygon;
* ``facilities``: the DDPM located shelters, whitelisted, flagged and
  corroborated (``floodguard.planning_context.shelter_facilities``); the OSM
  hospitals are extracted by the builder and get the DGA match afterwards, and
  the main-road entries (owner choice 8) are graph nodes;
* the grade joins of ``grade_join.py`` at 0 m (owner choice 20), logged.

Cases:

* ``se1`` (Mae Sai): demand = the eight tambons of protocol v1a clipped to AOI-02
  (owner choice 21); routing = the corridor of record
  (``outputs/planning_v1/corridor_of_record.geojson``). In vehicle mode the
  receipt is compared with the values the E0 spike run of record measured
  (``corridor_polygon.run_of_record.e4_reproduction_check``).
* ``se2`` (Mueang Chiang Rai): demand = the pf-07 frame; routing = the pf-07
  routing geometry (both checked against ``corridor_polygon.se2_frame``). The
  receipt compares the hospital objects with the frame build's list.

A build is the BUILD OF RECORD when the operator declares a compute window
(``--compute-window``): plan 5 item 1 asks for builds to run serially in a
declared window, and decision log R13 (3 October 2026) accepted in advance that
the agent declares the E4 window on the terms of the corridor run (no other
project job running, the window recorded). It writes its receipt and join log to
``outputs/planning_v1/`` and refuses to replace an earlier build of record unless
``--supersede-record`` gives the reason. Any other build is a candidate and
writes nothing into Git.

The facility table and a copy of the context hold DDPM rows (pitch level) and
are written outside Git, under
``<context root>/proposal_execution/planning_v1/<case>/e4_<mode>[_candidate]/``.

``--verify`` rebuilds the case into a temporary folder under ``--work-dir`` and
compares byte for byte: the join log, the facility table, and the receipt without
its ``run`` section; it also checks the context hash of the retained context.
The rebuild takes the generation time and run kind of the receipt it checks.

No flood layer is read. No closure, access loss, FPPS, A-E class or ensemble is
computed; the only access figure is the baseline connected-no-route share to
hospitals for the whole frame. Inputs live outside Git, so their locations are
arguments::

    python scripts/build_planning_context.py --case se1 \
        --context-root <external data root> \
        --ddpm-shelters <open data>/shelters/dpm-gd002_final2.csv \
        --dga-facilities <open data>/healthcare/thailand_health_facilities_th.geojson \
        --reviewed-junctions <finals run>/review/osm_junction_review.json \
        --work-dir <a scratch folder outside Git> \
        [--travel-mode legacy_vehicle|walking] [--compute-window "<declaration>"] \
        [--supersede-record "<reason>"] [--verify]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import evidence_context, planning_context  # noqa: E402
from floodguard.ddpm_shelters import read_ddpm_shelters  # noqa: E402
from floodguard.planning_frames import geometry_sha256  # noqa: E402

PROTOCOL_V1A = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1a.json"
PROTOCOL_V1B = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
PROCESSED_PARTS = ("proposal_execution", "planning_v1")
EXTERNAL_PLACEHOLDER = "<external_data_workspace>"
# The COD-AB read window: the bounds of the case's base geometry widened by this much (the E0 spike's window).
BOUNDARY_WINDOW_MARGIN_DEG = 0.45
MODES = {"legacy_vehicle": "vehicle", "walking": "walking"}
CASE_IDS = {"se1": "se1_mae_sai", "se2": "se2_mueang_chiang_rai"}
CASE_TITLES = {
    "se1": "Mae Sai: the eight tambons, routed through the corridor of record",
    "se2": "Mueang Chiang Rai: the pf-07 frame, routed through its 3 km routing geometry",
}
WINDOW_AUTHORITY = (
    "Decision log R13 (3 October 2026, Putu for both owners): the owners accepted in advance that the agent "
    "declares the E4 build's compute window on the terms of the corridor run of record: no other project job "
    "running, and the window recorded."
)
CANDIDATE_NOTE = (
    "Candidate: an E4 build without a declared compute window. It is not the build of record and closes no open item."
)
RUN_NOTE = (
    "Everything outside this section is a function of the inputs and the generation time: --verify rebuilds it "
    "byte for byte. This section records the run itself and is not compared."
)


class BuildError(ValueError):
    """Raised when an input is not the one protocol v1b names, or a build would replace a record silently."""


@dataclass
class Case:
    """The geometries of a case and the description the receipt records."""

    key: str
    demand: Any
    routing: Any
    routing_geojson: dict[str, Any]
    reporting: Any
    description: dict[str, Any]
    input_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class Sources:
    """The facility inputs that live outside the external data root."""

    ddpm_rows: list[dict[str, Any]]
    dga_points: list[tuple[float, float]]
    reviewed_junctions: list[dict[str, Any]]
    input_hashes: dict[str, str | None]


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


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


def load_case(key: str, boundaries: Path, v1a: dict[str, Any], v1b: dict[str, Any]) -> Case:
    """Read the demand, routing and reporting geometry of a case, checking every file against protocol v1b."""

    import pyogrio
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    corridor = v1b["corridor_polygon"]
    boundaries_sha256 = planning_context.sha256_file(boundaries)
    if boundaries_sha256 not in corridor["construction"]["boundary_source"]:
        raise BuildError("the boundary file is not the one protocol v1b names")
    hashes = {"boundaries_sha256": boundaries_sha256}
    if key == "se1":
        construction = corridor["construction"]
        aoi_path = ROOT / construction["base"]
        hashes["aoi_02_sha256"] = planning_context.sha256_file(aoi_path)
        if hashes["aoi_02_sha256"] != construction["base_sha256"]:
            raise BuildError("AOI-02 differs from the file protocol v1b names")
        aoi_02 = unary_union([shape(feature["geometry"]) for feature in read_json(aoi_path)["features"]])
        source = corridor["geometry_file"]
        routing_path = ROOT / source["path"]
        expected_geometry = corridor["run_of_record"]["corridor_geometry_sha256"]
        base_bounds = aoi_02.bounds
    elif key == "se2":
        frame = corridor["se2_frame"]
        frame_path = ROOT / frame["planning_frame_file"]
        hashes["planning_frame_sha256"] = planning_context.sha256_file(frame_path)
        if hashes["planning_frame_sha256"] != frame["sha256"]:
            raise BuildError("the pf-07 frame differs from the file protocol v1b names")
        units = read_json(frame_path)["features"]
        if sorted(unit["properties"]["adm3_pcode"] for unit in units) != sorted(frame["unit_list"]):
            raise BuildError("the pf-07 frame does not hold the units protocol v1b lists")
        source = frame["routing_geometry"]
        routing_path = ROOT / source["path"]
        expected_geometry = source["geometry_sha256"]
        base_bounds = None
    else:
        raise BuildError(f"unknown case {key}")
    hashes["routing_file_sha256"] = planning_context.sha256_file(routing_path)
    if hashes["routing_file_sha256"] != source["sha256"]:
        raise BuildError("the routing geometry file differs from the file protocol v1b names")
    features = read_json(routing_path)["features"]
    if len(features) != 1:
        raise BuildError("the routing geometry file must hold one feature")
    routing_geojson = features[0]["geometry"]
    if geometry_sha256(routing_geojson) != expected_geometry:
        raise BuildError("the routing geometry differs from the geometry protocol v1b names")
    routing = shape(routing_geojson)
    west, south, east, north = base_bounds or routing.bounds
    margin = BOUNDARY_WINDOW_MARGIN_DEG
    window = box(west - margin, south - margin, east + margin, north + margin)
    admin3 = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=["adm3_pcode"], bbox=window.bounds)
    intersecting = admin3[admin3.geometry.intersects(routing)]
    reporting = unary_union(list(intersecting.geometry))
    if key == "se1":
        tambons = v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"]
        selected = admin3[admin3["adm3_pcode"].isin(tambons)]
        if sorted(selected["adm3_pcode"]) != sorted(tambons):
            raise BuildError("the eight Mae Sai tambons were not all found")
        demand = unary_union(list(selected.geometry)).intersection(aoi_02)
        rules = {
            "aoi_geometry": "The union of the eight Mae Sai tambons of protocol v1a, clipped to AOI-02 (owner choice 21).",
            "routing_geometry": "The corridor of record (protocol v1b corridor_polygon.geometry_file).",
        }
        named_ways = list(corridor["acceptance"]["ways_within_routing_context"])
        expected_hospital_ids = None
    else:
        demand = unary_union([shape(unit["geometry"]) for unit in units])
        rules = {
            "aoi_geometry": "The union of the 16 tambons of the pf-07 frame (protocol v1b corridor_polygon.se2_frame).",
            "routing_geometry": "The pf-07 routing geometry (protocol v1b corridor_polygon.se2_frame.routing_geometry).",
        }
        named_ways = []
        expected_hospital_ids = [row["facility_id"] for row in frame["hospital_destinations"]]
    rules["reporting_geometry"] = "The union of the COD-AB tha_admin3 polygons that intersect the routing geometry."
    description = {
        "case_id": CASE_IDS[key],
        "title": CASE_TITLES[key],
        "rules": rules,
        "routing_source": {
            "path": routing_path.relative_to(ROOT).as_posix(),
            "sha256": hashes["routing_file_sha256"],
            "geometry_sha256": geometry_sha256(routing_geojson),
            "checked_against_protocol_v1b": True,
        },
        "named_ways": named_ways,
        "expected_hospital_ids": expected_hospital_ids,
        "reporting_units_intersecting": int(len(intersecting)),
        "main_road_entry_definition": v1b["facility_sets"]["services"]["main_road_entry"]["definition"],
    }
    return Case(key, demand, routing, routing_geojson, reporting, description, hashes)


def read_sources(ddpm: Path, dga: Path, reviewed_junctions: Path | None) -> Sources:
    """Read the DDPM list through its whitelist, the DGA points and the reviewed junctions."""

    rows = read_ddpm_shelters(ddpm)
    records = read_json(dga)["features"]
    points = [(float(row["geometry"]["coordinates"][0]), float(row["geometry"]["coordinates"][1])) for row in records]
    document = read_json(reviewed_junctions) if reviewed_junctions else {}
    reviewed = document.get("reviewed_junctions", []) if isinstance(document, dict) else list(document)
    return Sources(rows, points, reviewed, {
        "ddpm_file_sha256": planning_context.sha256_file(ddpm),
        "dga_file_sha256": planning_context.sha256_file(dga),
        "reviewed_junctions_sha256": planning_context.sha256_file(reviewed_junctions) if reviewed_junctions else None,
    })


def expected_values(v1b: dict[str, Any]) -> dict[str, Any]:
    """Return what the Mae Sai vehicle build must reproduce: v1b's check plus the spike's input hashes."""

    check = v1b["corridor_polygon"]["run_of_record"]["e4_reproduction_check"]
    spike_path = ROOT / check["source"]
    if planning_context.sha256_file(spike_path) != check["source_sha256"]:
        raise BuildError("the spike receipt differs from the file protocol v1b names")
    spike = read_json(spike_path)
    hashes, counts = spike["input_hashes"], spike["facility_counts"]
    return {
        **{key: check[key] for key in (
            "source", "source_sha256", "corridor_geometry_sha256", "edge_count", "grade_split_count", "joins_sha256",
            "join_count", "facility_counts", "mae_sai_hospital_facility_id", "context_canonical_sha256",
            "accepted_differences")},
        "inputs": {
            "osm_pbf_sha256": hashes["osm_pbf_sha256"],
            "worldpop_2020_sha256": hashes["worldpop_2020_sha256"],
            "boundaries_sha256": hashes["boundaries_sha256"],
            "aoi_02_sha256": hashes["aoi_02_sha256"],
            "reviewed_junctions_sha256": hashes["reviewed_junctions_sha256"],
            "dga_file_sha256": counts["dga_file_sha256"],
            "ddpm_file_sha256": counts["ddpm_file_sha256"],
        },
    }


def output_paths(case: Case, travel_mode: str, record: bool, context_root: Path) -> dict[str, Path]:
    """Return where a build's files go: the receipt and join log in Git for a record, the rest outside Git."""

    short = MODES[travel_mode]
    processed = context_root.joinpath(*PROCESSED_PARTS, case.description["case_id"],
                                      f"e4_{short}" if record else f"e4_{short}_candidate")
    paths = {
        "processed": processed,
        "facility_table": processed / "planning_facilities.json",
        "context": processed / "context_inputs.json",
    }
    if record:
        paths["receipt"] = OUTPUT_DIR / f"e4_planning_context_{case.key}_{short}.json"
        paths["join_log"] = OUTPUT_DIR / f"grade_join_log_e4_{case.key}_{short}.json"
    else:
        paths["receipt"] = processed / "receipt.json"
        paths["join_log"] = processed / "grade_join_log.json"
    return paths


def load_aois_counts() -> dict[str, Any]:
    """Count the AOIs ``load_aois`` returns from both AOI folders; it refuses anything but six."""

    from floodguard.evidence_catalog import load_aois

    counts: dict[str, Any] = {}
    for folder in ("resources/aoi", "resources/aoi/upload"):
        try:
            counts[folder] = len(load_aois(ROOT / folder))
        except ValueError as error:
            counts[folder] = f"refused: {error}"
    return counts


def status_notes(case: Case, travel_mode: str) -> dict[str, str]:
    """Return the status notes of a build of record and a candidate for this case and mode."""

    record = (f"Build of record of plan task E4 for case {case.description['case_id']} ({MODES[travel_mode]}), made "
              "in a compute window the operator declared (run.compute_window) under decision log R13. ")
    if case.key == "se1" and travel_mode == "legacy_vehicle":
        record += ("Protocol v1b open items OI-04 (join log) and OI-06 (facility counts) close from it only if its "
                   "values match corridor_polygon.run_of_record.e4_reproduction_check (reproduction_check) or the "
                   "owners accept the difference.")
    else:
        record += "It is a context for the later planning tasks; it closes no open item of protocol v1b."
    return {"record": record, "candidate": CANDIDATE_NOTE}


def build(case: Case, sources: Sources, *, v1b: dict[str, Any], context_root: Path, scratch: Path,
          travel_mode: str, record: bool, paths: dict[str, Path], generated_at_utc: str | None = None) -> dict[str, Any]:
    """Run one E4 build in ``scratch`` and return its outputs in memory, with the path of the context it wrote."""

    from shapely.geometry import mapping

    facility_sets = v1b["facility_sets"]["sets"][1]
    for key in ("hospital_match_distance_m", "shelter_match_distance_m"):
        if float(facility_sets[key]) != planning_context.MATCH_DISTANCE_M:
            raise BuildError(f"protocol v1b {key} is not the distance this build applies")
    timings: dict[str, float] = {}
    started = time.perf_counter()
    routing_context = case.routing.intersection(case.reporting)
    pbf = context_root / "open_context" / "osm_geofabrik" / "thailand-latest.osm.pbf"
    objects, extract_info = planning_context.extract_osm_match_objects(
        pbf, planning_context.match_object_bounds(routing_context), scratch / "osm_buildings_amenities")
    shelters, summary = planning_context.shelter_facilities(sources.ddpm_rows, routing_context, objects)
    summary["osm_extract"] = extract_info
    del objects
    timings["shelters_and_osm_match_objects"] = round(time.perf_counter() - started, 1)

    started = time.perf_counter()
    context = evidence_context.build_context_inputs(
        context_root, mapping(case.demand), case.routing_geojson, shelters, scratch / "context",
        reporting_geometry=mapping(case.reporting), travel_mode=travel_mode,
        reviewed_junctions=sources.reviewed_junctions,
    )
    timings["context_build"] = round(time.perf_counter() - started, 1)

    started = time.perf_counter()
    inputs = {
        **case.input_hashes,
        **sources.input_hashes,
        "osm_pbf_sha256": context["input_hashes"]["osm"],
        "worldpop_2020_sha256": context["input_hashes"]["worldpop"],
    }
    expected = expected_values(v1b) if case.key == "se1" and travel_mode == "legacy_vehicle" else None
    outputs = planning_context.assemble_outputs(
        context,
        case={**case.description, "reviewed_junctions_supplied": len(sources.reviewed_junctions)},
        record=record,
        generated_at_utc=generated_at_utc or _utc_now(),
        shelter_summary=summary,
        dga_points=sources.dga_points,
        inputs=inputs,
        paths={key: _logical(paths[key], context_root) for key in ("join_log", "facility_table", "context", "receipt")},
        acceptance=v1b["corridor_polygon"]["acceptance"],
        load_aois_counts=load_aois_counts(),
        expected=expected,
        status_notes=status_notes(case, travel_mode),
    )
    timings["assembly_and_baseline_access"] = round(time.perf_counter() - started, 1)
    del context
    outputs["context_file"] = scratch / "context" / "context_inputs.json"
    outputs["timings"] = timings
    return outputs


def peak_memory_gib() -> float | None:
    """Return this process's peak working set (Windows) or peak resident memory (POSIX) in GiB."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(int(counters.PeakWorkingSetSize) / 1024 ** 3, 2)
    try:
        import resource
    except ImportError:
        return None
    scale = 1 if sys.platform == "darwin" else 1024
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale / 1024 ** 3, 2)


def _implementation() -> dict[str, Any]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    modules = ("planning_context", "evidence_context", "grade_join", "ddpm_shelters", "shelter_corroboration",
               "hospital_counts")
    return {
        "base_commit": commit.stdout.strip() or None,
        "builder_sha256": planning_context.sha256_file(Path(__file__)),
        **{f"{name}_sha256": planning_context.sha256_file(ROOT / "src" / "floodguard" / f"{name}.py")
           for name in modules},
    }


def _retained_context_hash(path: Path) -> str | None:
    """Read the canonical SHA-256 at the end of a context file without loading it (the builder writes it last)."""

    if not path.is_file():
        return None
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 256))
        tail = stream.read().decode("utf-8", errors="replace")
    match = re.search(r'"canonical_sha256":"([0-9a-f]{64})"\}\s*$', tail)
    return match.group(1) if match else None


def run_build(args: argparse.Namespace, case: Case, sources: Sources, v1b: dict[str, Any]) -> dict[str, Any]:
    """Build a case and write its files; return a short summary."""

    record = bool(args.compute_window and args.compute_window.strip())
    paths = output_paths(case, args.travel_mode, record, args.context_root)
    supersedes = None
    if record and paths["receipt"].exists():
        if not (args.supersede_record and args.supersede_record.strip()):
            raise BuildError("a build of record exists; pass --supersede-record with the reason to replace it")
        earlier = json.loads(paths["receipt"].read_text(encoding="ascii"))
        supersedes = {
            "receipt_sha256": planning_context.sha256_file(paths["receipt"]),
            "generated_at_utc": earlier["generated_at_utc"],
            "reason": args.supersede_record.strip(),
        }
    started_utc, started_local = _utc_now(), _local_now()
    clock = time.perf_counter()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="e4-build-", dir=args.work_dir))
    try:
        outputs = build(case, sources, v1b=v1b, context_root=args.context_root, scratch=scratch,
                        travel_mode=args.travel_mode, record=record, paths=paths)
        peak = peak_memory_gib()
        body = outputs["receipt_body"]
        paths["processed"].mkdir(parents=True, exist_ok=True)
        shutil.copyfile(outputs["context_file"], paths["context"])
        paths["facility_table"].write_bytes(outputs["facility_table"])
        paths["join_log"].parent.mkdir(parents=True, exist_ok=True)
        paths["join_log"].write_bytes(outputs["join_log"])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    run = {
        "generated_at_utc": body["generated_at_utc"],
        "run_started_at_utc": started_utc,
        "run_started_at_local": started_local,
        "run_finished_at_utc": _utc_now(),
        "run_finished_at_local": _local_now(),
        "wall_time_minutes": round((time.perf_counter() - clock) / 60, 2),
        "timing_seconds": outputs["timings"],
        "peak_working_set_gib": peak,
        "peak_note": "Peak working set of this Python process over the whole build; it leaves out the ogr2ogr child "
                     "processes.",
        "compute_window": {
            "plan_rule": v1b["corridor_polygon"]["compute_window"],
            "declared": record,
            "declared_by_the_operator": args.compute_window.strip() if record else None,
            "authority": WINDOW_AUTHORITY if record else None,
            "note": "Declared when the operator passes --compute-window. This script cannot see what else runs on the "
                    "machine; the declaration says what was checked.",
        },
        "machine": {
            "logical_processors": os.cpu_count(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "implementation": _implementation(),
        "protocol_v1b_sha256_at_build": planning_context.sha256_file(PROTOCOL_V1B),
        "processed_folder": _logical(paths["processed"], args.context_root),
        "note": RUN_NOTE,
    }
    if supersedes is not None:
        run["supersedes"] = supersedes
    paths["receipt"].write_bytes(planning_context.encode_json({**body, "run": run}))
    return {
        "case": case.description["case_id"],
        "travel_mode": args.travel_mode,
        "run_kind": body["run_kind"],
        "receipt": _logical(paths["receipt"], args.context_root),
        "receipt_sha256": planning_context.sha256_file(paths["receipt"]),
        "acceptance": body["acceptance"]["criteria_met"],
        "reproduction_all_same": (body["reproduction_check"] or {}).get("all_same"),
        "reproduction_differences": (body["reproduction_check"] or {}).get("differences"),
        "counts": body["facilities"]["counts"],
        "join_count": body["grade_joins"]["join_count"],
        "wall_time_minutes": run["wall_time_minutes"],
    }


def run_verify(args: argparse.Namespace, case: Case, sources: Sources, v1b: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the case into a temporary folder and compare it byte for byte with the files it wrote before."""

    targets = [output_paths(case, args.travel_mode, record, args.context_root) for record in (True, False)]
    paths = next((candidate for candidate in targets if candidate["receipt"].is_file()), None)
    if paths is None:
        raise BuildError("there is no build of this case and mode to verify")
    committed = json.loads(paths["receipt"].read_text(encoding="ascii"))
    record = committed["run_kind"] == "build_of_record"
    args.work_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="e4-verify-", dir=args.work_dir))
    try:
        outputs = build(case, sources, v1b=v1b, context_root=args.context_root, scratch=scratch,
                        travel_mode=args.travel_mode, record=record, paths=paths,
                        generated_at_utc=committed["generated_at_utc"])
        rebuilt = scratch / "rebuilt"
        rebuilt.mkdir()
        files = {
            "join_log": (paths["join_log"], rebuilt / "grade_join_log.json", outputs["join_log"]),
            "facility_table": (paths["facility_table"], rebuilt / "planning_facilities.json", outputs["facility_table"]),
            "receipt_without_run": (None, rebuilt / "receipt_without_run.json",
                                    planning_context.encode_json(outputs["receipt_body"])),
        }
        problems = []
        compared = []
        for name, (existing, target, data) in files.items():
            target.write_bytes(data)
            if existing is None:
                before = planning_context.encode_json(planning_context.receipt_body(committed))
            elif existing.is_file():
                before = existing.read_bytes()
            else:
                problems.append(f"{name}: the file of the earlier build is missing")
                continue
            compared.append(name)
            if before != target.read_bytes():
                problems.append(f"{name}: the rebuild differs byte for byte")
        retained = _retained_context_hash(paths["context"])
        if retained != outputs["context_canonical_sha256"]:
            problems.append("context: the retained context's canonical SHA-256 differs from the rebuild's")
        if committed["context"]["canonical_sha256"] != outputs["context_canonical_sha256"]:
            problems.append("context: the receipt's canonical SHA-256 differs from the rebuild's")
    finally:
        if not args.keep_verify_folder:
            shutil.rmtree(scratch, ignore_errors=True)
    return {
        "verified": not problems,
        "case": case.description["case_id"],
        "travel_mode": args.travel_mode,
        "run_kind": committed["run_kind"],
        "receipt": _logical(paths["receipt"], args.context_root),
        "compared": compared + ["context_canonical_sha256"],
        "problems": problems,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=sorted(CASE_IDS), required=True)
    parser.add_argument("--context-root", type=Path, required=True, help="the external data root")
    parser.add_argument("--boundaries", type=Path,
                        help="COD-AB file; default <context root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip")
    parser.add_argument("--ddpm-shelters", type=Path, required=True)
    parser.add_argument("--dga-facilities", type=Path, required=True)
    parser.add_argument("--reviewed-junctions", type=Path)
    parser.add_argument("--travel-mode", choices=sorted(MODES), default="legacy_vehicle")
    parser.add_argument("--work-dir", type=Path, required=True, help="a scratch folder outside Git")
    parser.add_argument("--compute-window", help="the operator's declaration of the compute window: who declared it, "
                                                 "when, and what was checked. Makes the build the build of record.")
    parser.add_argument("--supersede-record", help="the reason for replacing an existing build of record")
    parser.add_argument("--verify", action="store_true", help="rebuild into a temporary folder and compare")
    parser.add_argument("--keep-verify-folder", action="store_true", help="keep the temporary folder of --verify")
    args = parser.parse_args(argv)
    for name in ("work_dir", "context_root"):
        resolved = getattr(args, name).resolve()
        if resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents:
            parser.error(f"--{name.replace('_', '-')} must be outside the repository")
    if args.verify and args.compute_window:
        parser.error("--verify takes the run kind from the receipt it checks; leave out --compute-window")
    if args.boundaries is None:
        args.boundaries = args.context_root / "open_context" / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
    return args


def main(argv: list[str] | None = None) -> int:
    """Build or verify the planning context of a case and print a JSON summary."""

    args = parse_args(argv)
    v1a = read_json(PROTOCOL_V1A)
    v1b = read_json(PROTOCOL_V1B)
    case = load_case(args.case, args.boundaries, v1a, v1b)
    sources = read_sources(args.ddpm_shelters, args.dga_facilities, args.reviewed_junctions)
    if args.verify:
        result = run_verify(args, case, sources, v1b)
        print(json.dumps(result))
        return 0 if result["verified"] else 1
    print(json.dumps(run_build(args, case, sources, v1b)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
