"""E0 context spike for the planning corridor (protocol v1b, open items OI-01 to OI-04 and OI-06).

Plan section 5 item 1 asks for one vehicle context build with the corrected
call, and for these numbers: hospital count, whether the three named hospital
ways are inside the routing context, edge count, wall time, peak RAM,
grade-split count and the baseline no-route share.

The corridor polygon depends on a rule the plan does not state: how the trunk
and primary routes to the three hospitals are picked (open item OI-02, an owner
decision). This spike builds the corridor under one of two candidate rules:

* ``proposal``: the proposal recorded in protocol v1b, made precise in
  ``ROUTE_RULES`` below (buffer the trunk and primary segments of the fastest path);
* ``whole_path``: the same path, with every segment buffered whatever its class.

A run is a CANDIDATE unless two things hold: the owners have chosen its rule
(protocol v1b records the rule text under ``route_selection_rule.rule``, which
must equal ``ROUTE_RULES[variant]``), and the operator declared a compute window
for it. Such a run is the RUN OF RECORD: its corridor, join log and counts are
the ones protocol v1b records. A candidate writes ``*_candidate_<variant>``
files; the run of record writes ``e0_context_run_of_record.json``,
``corridor_of_record.geojson`` and ``grade_join_log_of_record.json``, and
refuses to replace an earlier run of record unless ``--supersede-record`` gives
the reason. Every file says inside itself which of the two it is, and carries
its source timestamp, a confidence class and its assumptions.

The plan asks for builds to run serially in a declared compute window with no
concurrent SNAP jobs. A run counts as made in such a window only when the
operator passes ``--compute-window`` with the declaration; otherwise the receipt
records that criterion as not met. A run compares itself with the previous
candidate run of the same variant found in ``outputs/planning_v1`` and records
whether the polygon, the joins and the context are the same.

When the shelter match distance is decided in protocol v1b and the DDPM file is
given, the run also counts corroborated shelters: located DDPM rows with an OSM
building or amenity within that distance (``floodguard.shelter_corroboration``).
The OSM buildings and amenities are extracted from the same OSM file, in the
bounding box of the routing context widened by ``MATCH_OBJECT_MARGIN_DEG``. This
step runs after the figures of the E0 record are taken; its time and memory are
reported apart.

A context build is allowed before v1b is in force. The spike reads no flood
layer and computes no closure, no access loss, no FPPS, no A-E class and no
ensemble. It reports one baseline figure for the whole demand frame and no
figure for a single tambon. The DDPM shelter file is read through the column
whitelist of ``floodguard.ddpm_shelters``; only counts leave this script.

Inputs live outside Git, so their locations are arguments::

    python scripts/run_planning_context_spike.py --variant proposal \
        --context-root <external data root> \
        --boundaries <external data root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip \
        --reviewed-junctions <finals run>/review/osm_junction_review.json \
        --dga-facilities <open data>/healthcare/thailand_health_facilities_th.geojson \
        --ddpm-shelters <open data>/shelters/dpm-gd002_final2.csv \
        --work-dir <a scratch folder outside Git> \
        [--compute-window "<who declared it, when, what was checked>"]
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.ddpm_shelters import LOCATED, read_ddpm_shelters, summarise  # noqa: E402
from floodguard.evidence_context import (  # noqa: E402
    ROAD_CLASSES,
    _extract_osm,
    _tags,
    build_context_inputs,
)
from floodguard.evidence_scenarios import MODELLED_ROAD_SPEED_KMH, calculate_total_access  # noqa: E402
from floodguard.grade_join import apply_grade_joins, join_log, joins_sha256  # noqa: E402
from floodguard.shelter_corroboration import corroborate_shelters, osm_match_kinds  # noqa: E402

SCHEMA_VERSION = "floodguard.e0_context_spike.v1"
PROTOCOL_V1A = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1a.json"
PROTOCOL_V1B = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
SEARCH_MARGIN_DEG = 0.45
HOSPITAL_SNAP_LIMIT_M = 100.0
HOSPITAL_MATCH_DISTANCE_M = 150.0
# Room around the routing context for OSM objects that a shelter near its edge can match (about 210 m at 20 N).
MATCH_OBJECT_MARGIN_DEG = 0.002
MAE_SAI_HOSPITAL_NAME_TH = "โรงพยาบาลแม่สาย"
UNNAMED_FACILITY = "Unnamed OSM candidate"
MEMORY_SAMPLE_SECONDS = 0.2
RECORD_FILES = {
    "receipt": "e0_context_run_of_record.json",
    "corridor": "corridor_of_record.geojson",
    "log": "grade_join_log_of_record.json",
}
CANDIDATE_STATUS_NOTE = (
    "Candidate: open item OI-02 (the route rule) is an owner decision that has not been made. This file is not "
    "the corridor or the join log of record."
)
RECORD_STATUS_NOTE = (
    "Of record: built under the route rule the owners chose for open item OI-02 (owner choice 1, option B, "
    "decision log R12), in a compute window the operator declared (plan 5 item 1). Protocol v1b records this "
    "file by its SHA-256."
)
CONFIDENCE_BASIS = (
    "OSM roads and hospitals are unverified map records; travel times are modelled class speeds on an undirected "
    "graph; the timing was taken on a shared machine."
)
RECORD_CONFIDENCE_BASIS = (
    "OSM roads, hospitals, buildings and amenities are unverified map records; travel times are modelled class "
    "speeds on an undirected graph; the timing is one measurement on one desktop machine in a declared compute window."
)
CORRIDOR_ASSUMPTIONS = [
    "The route rule is a candidate for open item OI-02; it is not an owner decision.",
    "The fastest path is found on fixed class speeds on an undirected graph that joins ways at every shared "
    "vertex coordinate. One-way rules, turn restrictions and road condition are not represented.",
    "The polygon is AOI-02 plus 3 km buffers measured in EPSG:32647. It is a routing context, not a hazard zone, "
    "an evacuation zone or a flood extent.",
    "OSM hospital ways are map records. Their operation, entrance and capacity are not verified.",
]
RULE_DECIDED_ASSUMPTION = (
    "The route rule is the one the owners chose for open item OI-02 (owner choice 1, option B, with its seven "
    "sub-rules; decision log R12)."
)
# Variant -> the road classes of the fastest path that are buffered (None buffers every segment).
VARIANTS: dict[str, tuple[str, ...] | None] = {"proposal": ("trunk", "primary"), "whole_path": None}
_ROUTE_RULE_START = (
    "For each of the three hospitals: build an undirected vehicle graph from every OSM road in the search window "
    "that lies inside Thailand, joining ways wherever they share a vertex coordinate; use the modelled class speeds; "
    "snap the hospital to the road vertex nearest to its OSM way polygon; take the fastest path from that vertex to "
    "the first road vertex inside AOI-02 (the vertex of AOI-02 with the smallest travel time); "
)
ROUTE_RULES = {
    "proposal": _ROUTE_RULE_START + "keep the segments of that path whose class is trunk or primary, links included; "
                "buffer them by 3 km in EPSG:32647; and union the three buffers with AOI-02.",
    "whole_path": _ROUTE_RULE_START + "keep every segment of that path, whatever its road class; buffer the path by "
                  "3 km in EPSG:32647; and union the three buffers with AOI-02.",
}


def decided_variant(v1b: dict[str, Any]) -> str | None:
    """Return the variant whose rule protocol v1b records as decided (open item OI-02 closed), or None."""

    items = {item["id"]: item for item in v1b["open_items"]}
    if items.get("OI-02", {}).get("status") != "closed":
        return None
    rule = v1b["corridor_polygon"]["route_selection_rule"].get("rule")
    matches = [variant for variant, text in ROUTE_RULES.items() if text == rule]
    return matches[0] if len(matches) == 1 else None


def is_run_of_record(variant: str, compute_window: str | None, v1b: dict[str, Any]) -> bool:
    """A run is of record when its rule is the decided one and a compute window was declared for it."""

    return bool(compute_window and compute_window.strip()) and decided_variant(v1b) == variant


def output_paths(variant: str, of_record: bool, output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
    """Return where the receipt, the corridor and the join log of a run go."""

    if of_record:
        return {key: output_dir / name for key, name in RECORD_FILES.items()}
    return {
        "receipt": output_dir / f"e0_context_spike_{variant}.json",
        "corridor": output_dir / f"corridor_candidate_{variant}.geojson",
        "log": output_dir / f"grade_join_log_candidate_{variant}.json",
    }


def run_labels(variant: str, of_record: bool, v1b: dict[str, Any]) -> dict[str, Any]:
    """Return the status words, notes, confidence basis and rule assumption a run's files carry."""

    if of_record:
        return {
            "file_status": "of_record",
            "receipt_status": "run_of_record",
            "log_status": "log_of_record",
            "status_note": RECORD_STATUS_NOTE,
            "receipt_status_note": RECORD_STATUS_NOTE + " The figures under e0_spike_record are the ones the plan "
                                   "asks for (plan 5 item 1).",
            "confidence_basis": RECORD_CONFIDENCE_BASIS,
            "rule_assumption": RULE_DECIDED_ASSUMPTION,
        }
    decided = decided_variant(v1b)
    if decided is None:
        note = CANDIDATE_STATUS_NOTE
        rule_assumption = CORRIDOR_ASSUMPTIONS[0]
    elif decided == variant:
        note = ("Candidate: the owners chose this route rule for open item OI-02, but no compute window was "
                "declared for this run, so it is not the run of record.")
        rule_assumption = RULE_DECIDED_ASSUMPTION
    else:
        note = "Candidate: this is not the route rule the owners chose for open item OI-02."
        rule_assumption = "The route rule is not the one the owners chose for open item OI-02."
    return {
        "file_status": "candidate",
        "receipt_status": "candidate_measurement",
        "log_status": "candidate",
        "status_note": note,
        "receipt_status_note": note + " Nothing here closes an open item.",
        "confidence_basis": CONFIDENCE_BASIS,
        "rule_assumption": rule_assumption,
    }


def machine_description() -> dict[str, Any]:
    """Describe the machine a run was timed on: processors and installed memory. No user or host names."""

    description: dict[str, Any] = {
        "logical_processors": os.cpu_count(),
        "system": platform.system(),
        "release": platform.release(),
        "python": platform.python_version(),
        "physical_memory_gib": None,
        "available_memory_gib_at_start": None,
    }
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(status)):
            description["physical_memory_gib"] = round(status.ullTotalPhys / 1024 ** 3, 2)
            description["available_memory_gib_at_start"] = round(status.ullAvailPhys / 1024 ** 3, 2)
    return description


def extract_match_objects(pbf: Path, bounds: tuple[float, float, float, float],
                          target: Path) -> tuple[list[tuple[frozenset[str], Any]], dict[str, Any]]:
    """Extract OSM buildings and amenities from ``pbf`` inside ``bounds`` for shelter corroboration.

    Two passes of the GDAL OSM driver, as the context builder makes them:
    closed ways and multipolygon relations tagged building or amenity, and
    nodes whose other tags mention either key. Each object keeps its match
    kinds (``osm_match_kinds``); an object with neither kind is dropped. The
    extracted files stay in ``target`` (outside Git) and are named in the
    receipt by their SHA-256.
    """

    import pyogrio

    from floodguard.evidence_context import ogr_runtime_identity
    from floodguard.open_context_extract import _run_ogr2ogr, find_qgis_bin

    target.mkdir(parents=True, exist_ok=True)
    bin_dir = find_qgis_bin()
    layers = (
        ("multipolygons", "building IS NOT NULL OR amenity IS NOT NULL"),
        ("points", "other_tags LIKE '%building%' OR other_tags LIKE '%amenity%'"),
    )
    objects: list[tuple[frozenset[str], Any]] = []
    info: dict[str, Any] = {
        "bounds_wgs84": [round(value, 6) for value in bounds],
        "margin_deg": MATCH_OBJECT_MARGIN_DEG,
        "ogr_runtime": ogr_runtime_identity(bin_dir),
        "layers": {},
        "retained": False,
        "retained_note": "The extracted files were written outside Git and not kept; their SHA-256 values name them.",
    }
    for layer, where in layers:
        path = target / f"osm_{layer}_building_or_amenity.geojson"
        _run_ogr2ogr(bin_dir, ["-f", "GeoJSON", "-spat", *[str(value) for value in bounds], "-where", where,
                               "-lco", "RFC7946=YES", str(path), str(pbf), layer])
        frame = pyogrio.read_dataframe(path)
        columns = [column for column in frame.columns if column != "geometry"]
        kept = Counter()
        for values, geometry in zip(frame[columns].itertuples(index=False, name=None), frame.geometry):
            if geometry is None or geometry.is_empty:
                continue
            # OSM attributes are strings; a missing one comes back as NaN or None and is left out.
            properties = {key: value for key, value in zip(columns, values) if isinstance(value, str)}
            kinds = osm_match_kinds(_tags(properties))
            if kinds:
                objects.append((kinds, geometry))
                kept["kept"] += 1
                for kind in kinds:
                    kept[kind] += 1
        info["layers"][layer] = {
            "where": where,
            "features_read": int(len(frame)),
            "objects_kept": kept["kept"],
            "with_building": kept["building"],
            "with_amenity": kept["amenity"],
            "file_sha256": sha256_file(path),
        }
        del frame
    return objects, info


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    """Serialise a committed JSON output: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _windows_working_set_bytes() -> tuple[int, int] | None:
    """Return (peak, current) working set of this process in bytes on Windows, or None."""

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
    return int(counters.PeakWorkingSetSize), int(counters.WorkingSetSize)


def peak_memory_gib() -> float | None:
    """Return this process's peak resident memory in GiB, or None when it cannot be read."""

    if os.name == "nt":
        sizes = _windows_working_set_bytes()
        return None if sizes is None else sizes[0] / 1024 ** 3
    try:
        import resource
    except ImportError:
        return None
    scale = 1 if sys.platform == "darwin" else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale / 1024 ** 3


def current_memory_gib() -> float | None:
    """Return this process's current resident memory in GiB, or None when it cannot be read."""

    if os.name == "nt":
        sizes = _windows_working_set_bytes()
        return None if sizes is None else sizes[1] / 1024 ** 3
    try:
        with open("/proc/self/statm", encoding="ascii") as stream:
            resident_pages = int(stream.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE") / 1024 ** 3
    except (OSError, ValueError, IndexError, AttributeError):
        return None


class MemorySampler:
    """Sample this process's resident memory while a block runs, to give that block its own peak.

    ``peak_memory_gib`` is the peak over the whole process and cannot be reset,
    so it cannot say how much one step needs. This sampler reads the current
    resident memory every ``interval`` seconds between ``__enter__`` and
    ``__exit__``. A sampled peak can miss a short spike, and it includes memory
    that earlier steps have not yet returned to the operating system.
    """

    def __init__(self, interval: float = MEMORY_SAMPLE_SECONDS) -> None:
        self.interval = interval
        self.peak_gib: float | None = None
        self.start_gib: float | None = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _read(self) -> None:
        value = current_memory_gib()
        if value is not None:
            self.samples += 1
            self.peak_gib = value if self.peak_gib is None else max(self.peak_gib, value)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._read()

    def __enter__(self) -> "MemorySampler":
        self.start_gib = current_memory_gib()
        self._read()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._read()


def geometry_sha256(geometry: dict[str, Any]) -> str:
    """Return the SHA-256 of a GeoJSON geometry alone, so two runs can be compared whatever their run time."""

    encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def edge_tag_counts(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Count context edges by road class and by bridge and tunnel tag. Counts for the whole context only."""

    total = len(edges)
    by_class = Counter(str(edge["road_class"]) for edge in edges)
    bridge = Counter(str(edge.get("bridge", "no")) for edge in edges)
    tunnel = Counter(str(edge.get("tunnel", "no")) for edge in edges)
    return {
        "edges": total,
        "by_road_class": dict(sorted(by_class.items())),
        "share_by_road_class": {key: round(value / total, 6) for key, value in sorted(by_class.items())},
        "by_bridge_tag": dict(sorted(bridge.items())),
        "by_tunnel_tag": dict(sorted(tunnel.items())),
        "bridge_yes_edges": bridge.get("yes", 0),
        "tunnel_culvert_edges": tunnel.get("culvert", 0),
        "culvert_tag_note": "The context builder carries the OSM bridge, tunnel and layer tags on each edge. It does "
                            "not carry a culvert=* tag, so an edge tagged only that way is not counted or treated here.",
    }


def hospital_breakdown(destinations: list[dict[str, Any]]) -> dict[str, Any]:
    """Say how many OSM hospital objects there are and how many different hospitals they name.

    The plan's acceptance asks for at least four hospitals and does not say
    whether two OSM objects for one hospital count twice. Objects with the same
    OSM name are one named hospital; an object without a name is counted apart.
    """

    names = Counter(" ".join(str(row["name"]).split()).casefold() for row in destinations
                    if row["name"] != UNNAMED_FACILITY)
    unnamed = sum(row["name"] == UNNAMED_FACILITY for row in destinations)
    return {
        "osm_objects": len(destinations),
        "distinct_named_hospitals": len(names),
        "unnamed_objects": unnamed,
        "objects_that_repeat_a_named_hospital": sum(count - 1 for count in names.values()),
        "rule": "Objects with the same OSM name are one named hospital. An object without a name is counted apart; "
                "nothing here shows that it is a hospital in its own right.",
    }


def previous_run(variant: str, output_dir: Path = OUTPUT_DIR) -> dict[str, Any] | None:
    """Read what the previous run of this variant left in the output folder, before it is overwritten."""

    receipt_path = output_dir / f"e0_context_spike_{variant}.json"
    corridor_path = output_dir / f"corridor_candidate_{variant}.geojson"
    log_path = output_dir / f"grade_join_log_candidate_{variant}.json"
    if not (receipt_path.is_file() and corridor_path.is_file() and log_path.is_file()):
        return None
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    corridor = json.loads(corridor_path.read_text(encoding="ascii"))
    log = json.loads(log_path.read_text(encoding="ascii"))
    return {
        "generated_at_utc": receipt["generated_at_utc"],
        "receipt_sha256": sha256_file(receipt_path),
        "context_canonical_sha256": receipt["context"]["canonical_sha256"],
        "corridor_geometry_sha256": geometry_sha256(corridor["features"][0]["geometry"]),
        "joins_sha256": joins_sha256(log["joins"]),
        "edge_count": receipt["e0_spike_record_candidate"]["edge_count"],
        "join_count": log["join_count"],
    }


def reproducibility(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Compare this run with the previous run of the same variant."""

    if previous is None:
        return {"compared": False, "note": "No earlier run of this variant was found in outputs/planning_v1."}
    keys = ("context_canonical_sha256", "corridor_geometry_sha256", "joins_sha256", "edge_count", "join_count")
    same = {key: previous[key] == current[key] for key in keys}
    return {
        "compared": True,
        "note": "The earlier run's receipt, corridor and join log were read from outputs/planning_v1 before this "
                "run replaced them. Run times, timings and memory figures differ between runs and are not compared.",
        "previous_run": previous,
        "this_run": {key: current[key] for key in keys},
        "same": same,
        "all_same": all(same.values()),
    }


def fastest_path(
    node_count: int, sources: list[int], targets: list[int], minutes: list[float], origin: int, goal_nodes: list[int],
) -> tuple[list[int], float]:
    """Return the edge indices of the fastest path from ``origin`` to the nearest goal node.

    Args:
        node_count: Number of graph nodes.
        sources, targets, minutes: One entry per undirected edge.
        origin: The node the search starts from (the hospital).
        goal_nodes: Candidate end nodes (the vertices inside AOI-02).

    Returns:
        The path as edge indices from the origin outwards, and its travel time.
        A goal equal to the origin gives an empty path.

    Raises:
        ValueError: when no goal node can be reached.
    """

    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

    if not goal_nodes:
        raise ValueError("no goal node")
    best: dict[tuple[int, int], tuple[float, int]] = {}
    for index, (start, end, cost) in enumerate(zip(sources, targets, minutes)):
        key = (min(start, end), max(start, end))
        if start != end and (key not in best or (cost, index) < best[key]):
            best[key] = (cost, index)
    rows = np.fromiter((key[0] for key in best), dtype="int64", count=len(best))
    cols = np.fromiter((key[1] for key in best), dtype="int64", count=len(best))
    # A zero weight would be read as "no edge" by the sparse solver.
    costs = np.fromiter((max(value[0], 1e-12) for value in best.values()), dtype="float64", count=len(best))
    matrix = coo_matrix((costs, (rows, cols)), shape=(node_count, node_count)).tocsr()
    distances, predecessors = dijkstra(matrix, directed=False, indices=origin, return_predecessors=True)
    goals = np.asarray(sorted(goal_nodes), dtype="int64")
    reachable = goals[np.isfinite(distances[goals])]
    if reachable.size == 0:
        raise ValueError("no goal node can be reached")
    goal = int(reachable[np.argmin(distances[reachable])])
    path: list[int] = []
    node = goal
    while node != origin:
        previous = int(predecessors[node])
        path.append(best[(min(previous, node), max(previous, node))][1])
        node = previous
    path.reverse()
    return path, float(distances[goal])


def no_route_share(access: dict[str, Any]) -> dict[str, float]:
    """Return the baseline connected-no-route share and its two population terms."""

    review = access["coverage_review"]
    total = access["totals"]["total_population"]
    connected = total - review["missing_graph_coverage_population"]
    no_route = review["baseline"]["graph_connected_no_modelled_route_population"]
    return {
        "residents": total,
        "graph_connected_residents": connected,
        "connected_residents_without_a_route": no_route,
        "share": no_route / connected if connected else 1.0,
        "residents_not_connected_to_the_graph": review["missing_graph_coverage_population"],
    }


def _route_graph(roads: dict[str, Any], scope: Any) -> dict[str, Any]:
    """Build the route-selection graph: shared vertex coordinates join, whatever the grade."""

    import numpy as np
    import shapely
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    node_index: dict[tuple[float, float], int] = {}
    starts, ends, way_ids, classes, segments = [], [], [], [], []
    for feature in sorted(roads["features"], key=lambda item: str(item.get("properties", {}).get("osm_id", ""))):
        tags = _tags(feature.get("properties", {}))
        road_class = ROAD_CLASSES.get(tags.get("highway", ""))
        prohibited = tags.get("access") in {"no", "private"} or tags.get("motor_vehicle") in {"no", "private"}
        geometry = feature.get("geometry", {})
        if road_class is None or prohibited or geometry.get("type") != "LineString":
            continue
        coordinates = [(float(point[0]), float(point[1])) for point in geometry["coordinates"]]
        for first, second in zip(coordinates, coordinates[1:]):
            if first == second:
                continue
            starts.append(node_index.setdefault(first, len(node_index)))
            ends.append(node_index.setdefault(second, len(node_index)))
            way_ids.append(tags.get("osm_id"))
            classes.append(road_class)
            segments.append((first, second))
    lines = shapely.linestrings(np.asarray(segments, dtype="float64"))
    shapely.prepare(scope)
    inside = shapely.covers(scope, lines)
    keep = np.nonzero(inside)[0]
    lon1 = np.asarray([segments[i][0][0] for i in keep])
    lat1 = np.asarray([segments[i][0][1] for i in keep])
    lon2 = np.asarray([segments[i][1][0] for i in keep])
    lat2 = np.asarray([segments[i][1][1] for i in keep])
    _az1, _az2, metres = geod.inv(lon1, lat1, lon2, lat2)
    speeds = np.asarray([MODELLED_ROAD_SPEED_KMH[classes[i]] for i in keep])
    coordinates = np.asarray(sorted(node_index, key=node_index.get), dtype="float64")
    return {
        "node_coordinates": coordinates,
        "sources": [starts[i] for i in keep],
        "targets": [ends[i] for i in keep],
        "minutes": (metres / 1000 / speeds * 60).tolist(),
        "metres": metres.tolist(),
        "way_ids": [way_ids[i] for i in keep],
        "classes": [classes[i] for i in keep],
        "segments": [segments[i] for i in keep],
    }


def build_corridor(roads: dict[str, Any], areas: dict[str, Any], aoi_02: Any, scope: Any,
                   hospital_ways: dict[int, str], buffer_m: float,
                   kept_classes: tuple[str, ...] | None) -> tuple[Any, list[dict[str, Any]]]:
    """Apply a route rule and return the corridor polygon (WGS84) and one record per hospital.

    ``kept_classes`` names the road classes of the fastest path that are
    buffered; ``None`` buffers the whole path.
    """

    import numpy as np
    import shapely
    from pyproj import Transformer
    from shapely.geometry import LineString, shape
    from shapely.ops import transform, unary_union

    to_metres = Transformer.from_crs(4326, 32647, always_xy=True).transform
    to_degrees = Transformer.from_crs(32647, 4326, always_xy=True).transform
    graph = _route_graph(roads, scope)
    coordinates = graph["node_coordinates"]
    used = np.zeros(len(coordinates), dtype=bool)
    used[graph["sources"]] = True
    used[graph["targets"]] = True
    x, y = to_metres(coordinates[:, 0], coordinates[:, 1])
    points = shapely.points(x, y)
    in_aoi = np.nonzero(used & shapely.contains_xy(aoi_02, coordinates[:, 0], coordinates[:, 1]))[0].tolist()
    polygons = {}
    for feature in areas["features"]:
        way_id = _tags(feature.get("properties", {})).get("osm_way_id")
        if way_id and int(way_id) in hospital_ways:
            polygons[int(way_id)] = shape(feature["geometry"])
    buffers, records = [], []
    for way_id, name in sorted(hospital_ways.items()):
        record: dict[str, Any] = {"osm_way": way_id, "name": name, "found_in_osm_extract": way_id in polygons}
        records.append(record)
        if way_id not in polygons:
            continue
        site = transform(to_metres, polygons[way_id])
        distances = shapely.distance(points, site)
        distances[~used] = np.inf
        origin = int(np.argmin(distances))
        record["snap_distance_m"] = round(float(distances[origin]), 2)
        record["snapped_within_100_m"] = bool(distances[origin] <= HOSPITAL_SNAP_LIMIT_M)
        try:
            path, minutes = fastest_path(len(coordinates), graph["sources"], graph["targets"], graph["minutes"],
                                         origin, in_aoi)
        except ValueError as error:
            record["route_found"] = False
            record["route_error"] = str(error)
            continue
        kept = [index for index in path if kept_classes is None or graph["classes"][index] in kept_classes]
        by_class: dict[str, float] = {}
        for index in path:
            by_class[graph["classes"][index]] = by_class.get(graph["classes"][index], 0.0) + graph["metres"][index]
        record.update({
            "route_found": True,
            "route_minutes": round(minutes, 2),
            "route_km": round(sum(graph["metres"][index] for index in path) / 1000, 3),
            "route_km_by_road_class": {key: round(value / 1000, 3) for key, value in sorted(by_class.items())},
            "kept_km": round(sum(graph["metres"][index] for index in kept) / 1000, 3),
            "path_segment_count": len(path),
            "kept_segment_count": len(kept),
            "path_osm_way_ids": list(dict.fromkeys(graph["way_ids"][index] for index in path)),
            "kept_osm_way_ids": list(dict.fromkeys(graph["way_ids"][index] for index in kept)),
        })
        if kept:
            kept_lines = unary_union([transform(to_metres, LineString(graph["segments"][index])) for index in kept])
            record["hospital_distance_to_kept_segments_m"] = round(float(site.distance(kept_lines)), 1)
            buffers.append(transform(to_degrees, kept_lines.buffer(buffer_m)))
        else:
            record["hospital_distance_to_kept_segments_m"] = None
    corridor = unary_union([aoi_02, *buffers])
    for record in records:
        if record["found_in_osm_extract"]:
            record["way_polygon_inside_corridor"] = bool(corridor.covers(polygons[record["osm_way"]]))
    return corridor, records


def facility_counts(destinations: list[dict[str, Any]], routing: Any,
                    dga_path: Path | None, ddpm_path: Path | None) -> dict[str, Any]:
    """Count the facilities of open item OI-06 inside the routing context. Counts only."""

    from pyproj import Transformer
    from shapely import STRtree, points
    from shapely.geometry import Point, shape
    from shapely.ops import transform

    to_metres = Transformer.from_crs(4326, 32647, always_xy=True).transform
    named = [row["facility_id"] for row in destinations if row["name"] == MAE_SAI_HOSPITAL_NAME_TH]
    counts: dict[str, Any] = {
        "osm_hospitals": len(destinations),
        "mae_sai_hospital_facility_ids_by_osm_name": named,
        "dga_matched_hospitals": None,
        "located_ddpm_shelters": None,
        "corroborated_shelters": None,
        "corroborated_shelters_note": "Not measured here: it needs the DDPM file, the shelter match distance in "
                                      "protocol v1b and an extract of OSM buildings and amenities "
                                      "(corroborated_shelter_counts).",
    }
    if dga_path is not None:
        records = json.loads(dga_path.read_text(encoding="utf-8"))["features"]
        lon = [feature["geometry"]["coordinates"][0] for feature in records]
        lat = [feature["geometry"]["coordinates"][1] for feature in records]
        x, y = to_metres(lon, lat)
        tree = STRtree(points(x, y))
        matched = 0
        for row in destinations:
            site = transform(to_metres, shape(row["source_geometry"]))
            matched += int(len(tree.query(site, predicate="dwithin", distance=HOSPITAL_MATCH_DISTANCE_M)) > 0)
        counts["dga_matched_hospitals"] = matched
        counts["dga_match_rule"] = ("An OSM hospital is matched when a DGA record lies within 150 m of its OSM "
                                    "footprint or point, measured in EPSG:32647.")
        counts["dga_records_read"] = len(records)
        counts["dga_file_sha256"] = sha256_file(dga_path)
    if ddpm_path is not None:
        rows = read_ddpm_shelters(ddpm_path)
        inside = [row for row in rows if row["latitude"] is not None and row["longitude"] is not None
                  and routing.covers(Point(row["longitude"], row["latitude"]))]
        summary = summarise(inside)
        counts["located_ddpm_shelters"] = summary["located_rows"]
        counts["ddpm_rows_with_a_coordinate_in_the_routing_context"] = summary
        counts["ddpm_location_rule"] = ("A coordinate shared by at least 3 rows of the national file is a placeholder "
                                        "and those rows are not located. Located means status " + LOCATED + ".")
        counts["ddpm_file_sha256"] = sha256_file(ddpm_path)
        counts["ddpm_publication_level"] = "pitch"
    return counts


def corroborated_shelter_counts(ddpm_path: Path, routing: Any, match_objects: list[tuple[frozenset[str], Any]],
                                distance_m: float) -> dict[str, Any]:
    """Count the located DDPM rows in the routing context that an OSM building or amenity corroborates.

    The rows are those ``facility_counts`` counts as located in the routing
    context. Counts only; no row leaves this function.
    """

    from shapely.geometry import Point

    rows = read_ddpm_shelters(ddpm_path)
    inside = [row for row in rows if row["latitude"] is not None and row["longitude"] is not None
              and routing.covers(Point(row["longitude"], row["latitude"]))]
    return corroborate_shelters(inside, match_objects, distance_m=distance_m)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


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


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Run the spike and return the receipt; the corridor and the join log are written beside it at the end."""

    import pyogrio
    from shapely.geometry import box, mapping, shape
    from shapely.ops import transform, unary_union
    from pyproj import Transformer

    run_started_utc, run_started_local = _utc_now(), _local_now()
    machine = machine_description()
    v1a = json.loads(PROTOCOL_V1A.read_text(encoding="utf-8"))
    v1b = json.loads(PROTOCOL_V1B.read_text(encoding="utf-8"))
    of_record = is_run_of_record(args.variant, args.compute_window, v1b)
    labels = run_labels(args.variant, of_record, v1b)
    paths = output_paths(args.variant, of_record)
    supersedes = None
    if of_record and paths["receipt"].exists():
        if not (args.supersede_record and args.supersede_record.strip()):
            raise ValueError("a run of record exists; pass --supersede-record with the reason to replace it")
        earlier = json.loads(paths["receipt"].read_text(encoding="ascii"))
        supersedes = {
            "receipt_sha256": sha256_file(paths["receipt"]),
            "generated_at_utc": earlier["generated_at_utc"],
            "reason": args.supersede_record.strip(),
        }
    construction = v1b["corridor_polygon"]["construction"]
    acceptance = v1b["corridor_polygon"]["acceptance"]
    shelter_distance = v1b["facility_sets"]["sets"][1].get("shelter_match_distance_m")
    hospital_ways = {row["osm_way"]: row["name"] for row in construction["hospital_destinations"]}
    tambons = v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"]
    aoi_path = ROOT / construction["base"]
    if sha256_file(aoi_path) != construction["base_sha256"]:
        raise ValueError("AOI-02 differs from the file protocol v1b names")
    aoi_02 = unary_union([shape(f["geometry"]) for f in json.loads(aoi_path.read_text(encoding="utf-8"))["features"]])
    boundaries_sha256 = sha256_file(args.boundaries)
    if boundaries_sha256 not in construction["boundary_source"]:
        raise ValueError("the boundary file is not the one protocol v1b names")
    pbf = args.context_root / "open_context" / "osm_geofabrik" / "thailand-latest.osm.pbf"
    pbf_sha256 = sha256_file(pbf)
    reviewed_document = json.loads(args.reviewed_junctions.read_text(encoding="utf-8")) if args.reviewed_junctions else {}
    reviewed = reviewed_document.get("reviewed_junctions", []) if isinstance(reviewed_document, dict) else reviewed_document

    west, south, east, north = aoi_02.bounds
    window = box(west - SEARCH_MARGIN_DEG, south - SEARCH_MARGIN_DEG, east + SEARCH_MARGIN_DEG, north + SEARCH_MARGIN_DEG)
    admin3 = pyogrio.read_dataframe(args.boundaries, layer="tha_admin3", columns=["adm3_pcode"], bbox=window.bounds)
    thailand_in_window = unary_union(list(admin3.geometry)).intersection(window)

    started = time.perf_counter()
    search_dir = args.work_dir / "route_search"
    search_dir.mkdir(parents=True, exist_ok=True)
    roads, areas = _extract_osm(pbf, window.bounds, search_dir, pbf_sha256, hashlib.sha256(window.wkb).hexdigest())
    corridor, hospital_routes = build_corridor(roads, areas, aoi_02, thailand_in_window, hospital_ways,
                                               float(construction["buffer_m"]), VARIANTS[args.variant])
    del roads, areas
    route_seconds = time.perf_counter() - started
    peak_after_route = peak_memory_gib()
    if not corridor.is_valid or corridor.geom_type != "Polygon":
        raise ValueError("the corridor must be one valid polygon")

    to_metres = Transformer.from_crs(4326, 32647, always_xy=True).transform
    in_corridor = admin3[admin3.geometry.intersects(corridor)]
    reporting = unary_union(list(in_corridor.geometry))
    frame = admin3[admin3["adm3_pcode"].isin(tambons)]
    if sorted(frame["adm3_pcode"]) != sorted(tambons):
        raise ValueError("the eight Mae Sai tambons were not all found")
    tambon_union = unary_union(list(frame.geometry))
    demand = tambon_union.intersection(aoi_02)
    outside_m2 = transform(to_metres, tambon_union.difference(aoi_02)).area

    # The comparison is always with the previous candidate run of the same rule.
    previous = previous_run(args.variant)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    context_dir = args.work_dir / "context_vehicle"
    gc.collect()
    build_started = time.perf_counter()
    with MemorySampler() as build_memory:
        context = build_context_inputs(
            args.context_root, mapping(demand), mapping(corridor), [], context_dir,
            reporting_geometry=mapping(reporting), travel_mode="legacy_vehicle", reviewed_junctions=reviewed,
        )
    build_seconds = time.perf_counter() - build_started
    peak_after_build = peak_memory_gib()
    osm_retrieved_at = context["source_metadata"]["osm"]["retrieved_at_utc"]

    hospitals = [row for row in context["osm_facilities"] if row["service_type"] == "hospital"]
    destinations = [row for row in hospitals
                    if row.get("candidate_destination_eligible") is True and row.get("within_routing_context") is True]
    by_id = {row["facility_id"]: row for row in hospitals}
    named = {
        str(way_id): bool(by_id.get(f"OSM-way-{way_id}", {}).get("within_routing_context"))
        for way_id in acceptance["ways_within_routing_context"]
    }
    access_started = time.perf_counter()
    unjoined = calculate_total_access(context["population"], context["edges"], destinations)
    joined_edges, joins = apply_grade_joins(context)
    joined = calculate_total_access(context["population"], joined_edges, destinations)
    access_seconds = time.perf_counter() - access_started
    routing_context = corridor.intersection(reporting)
    facilities = facility_counts(destinations, routing_context, args.dga_facilities, args.ddpm_shelters)
    # The figures of the E0 record are taken here, before the corroboration step below.
    peak = peak_memory_gib()

    corroboration_seconds = None
    peak_after_corroboration = None
    corroborated = False
    if args.ddpm_shelters is not None and shelter_distance is not None:
        corroboration_started = time.perf_counter()
        bounds = routing_context.bounds
        bounds = (bounds[0] - MATCH_OBJECT_MARGIN_DEG, bounds[1] - MATCH_OBJECT_MARGIN_DEG,
                  bounds[2] + MATCH_OBJECT_MARGIN_DEG, bounds[3] + MATCH_OBJECT_MARGIN_DEG)
        match_objects, extract_info = extract_match_objects(pbf, bounds, args.work_dir / "osm_buildings_amenities")
        counts = corroborated_shelter_counts(args.ddpm_shelters, routing_context, match_objects, float(shelter_distance))
        del match_objects
        if counts["located_rows"] != facilities["located_ddpm_shelters"]:
            raise ValueError("the corroboration step saw a different set of located shelters")
        facilities["corroborated_shelters"] = counts["corroborated_rows"]
        facilities.pop("corroborated_shelters_note", None)
        facilities["shelter_corroboration"] = {**counts, "osm_extract": extract_info}
        corroboration_seconds = time.perf_counter() - corroboration_started
        peak_after_corroboration = peak_memory_gib()
        corroborated = True

    review = context["connectivity_review"]
    share_unjoined, share_joined = no_route_share(unjoined), no_route_share(joined)
    breakdown = hospital_breakdown(destinations)
    hospital_count = breakdown["distinct_named_hospitals"] if of_record else len(destinations)
    wall_minutes = (route_seconds + build_seconds) / 60
    aoi_counts = load_aois_counts()
    criteria_met = {
        "hospitals_in_context_min": hospital_count >= acceptance["hospitals_in_context_min"],
        "named_ways_within_routing_context": all(named.values()),
        "baseline_vehicle_no_route_share_max":
            share_joined["share"] <= acceptance["baseline_vehicle_no_route_share_max"],
        "declared_compute_window": bool(args.compute_window),
    }
    corridor_geometry = json.loads(json.dumps(mapping(corridor)))
    corridor_geometry_sha256 = geometry_sha256(corridor_geometry)
    compared = reproducibility(previous, {
        "context_canonical_sha256": context["canonical_sha256"],
        "corridor_geometry_sha256": corridor_geometry_sha256,
        "joins_sha256": joins_sha256(joins),
        "edge_count": len(context["edges"]),
        "join_count": len(joins),
    })
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)

    # Every file of the run carries the same generation time; they are written last, together.
    generated_at = _utc_now()
    corridor_feature = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "id": paths["corridor"].stem,
                "status": labels["file_status"],
                "status_note": labels["status_note"],
                "generated_at_utc": generated_at,
                "source_timestamp": osm_retrieved_at,
                "source_timestamp_note": "Retrieval time of the OpenStreetMap extract the routes were found on. "
                                         "AOI-02 and the boundaries are named by their SHA-256.",
                "confidence_class": "low",
                "confidence_basis": labels["confidence_basis"],
                "assumptions": [labels["rule_assumption"], *CORRIDOR_ASSUMPTIONS[1:]],
                "route_rule_variant": args.variant,
                "route_rule": ROUTE_RULES[args.variant],
                "base": construction["base"],
                "base_sha256": construction["base_sha256"],
                "buffer_m": construction["buffer_m"],
                "osm_pbf_sha256": pbf_sha256,
                "boundaries_sha256": boundaries_sha256,
                "geometry_sha256": corridor_geometry_sha256,
                "official_warning": False,
                "operational_status": "non_operational",
            },
            "geometry": corridor_geometry,
        }],
    }
    corridor_bytes = encode(corridor_feature)
    log_bytes = encode(join_log(
        joins, context_canonical_sha256=context["canonical_sha256"], status=labels["log_status"],
        status_note=labels["status_note"], source_timestamp=osm_retrieved_at, generated_at_utc=generated_at,
    ))
    record_key = "e0_spike_record" if of_record else "e0_spike_record_candidate"
    hospital_assumption = (
        "hospital_count counts distinct named hospitals, the unit the owners chose (acceptance.hospital_count_unit, "
        "owner choice 22): OSM objects with the same name are one hospital and an unnamed object is not counted. "
        "hospital_count_breakdown gives the number of OSM objects too; every object is a destination."
        if of_record else
        "hospital_count counts OSM objects. Two objects can describe one hospital, and an unnamed object may not "
        "be a hospital; hospital_count_breakdown says how many there are of each."
    )
    assumptions = [
        labels["rule_assumption"],
        "The route-selection graph joins ways at every shared vertex coordinate, whatever their grade tags. The "
        "context graph does not: it keeps grade-separated vertices apart and joins them only under decision D13.",
        "Road times are fixed class speeds on an undirected graph. One-way rules, turn restrictions and road "
        "condition are not represented.",
        "A hospital is an OSM object tagged as a hospital. Its operation, entrance and capacity are not verified.",
        "A grade join shows that two ways end at the same OSM coordinate. It does not show the transition can be driven.",
        hospital_assumption,
    ]
    if corroborated:
        assumptions.append(
            "A corroborated shelter is a located DDPM row with an OSM building or amenity within the match distance. "
            "That shows a mapped structure near the listed coordinate, not that the structure is the shelter or that "
            "it was open. OSM building coverage is not complete, and in a built-up area almost any point has a "
            "building nearby; the match rate is reported for that reason."
        )
    limitations = [
        "One build on one day on one machine. The context file is not kept; its canonical SHA-256 names it."
        if of_record else
        "This is one build on one day. It is a measurement for the owners, not the context of record.",
        "Facility counts are counts of map and list records. No hospital and no shelter was checked on the ground.",
    ]
    if not corroborated:
        limitations.append("The number of corroborated shelters is not measured.")
    run_finished_utc, run_finished_local = _utc_now(), _local_now()
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "protocol_item": "planning_protocol_v1b open items OI-01, OI-03, OI-04 and OI-06 (plan 5 item 1, task E0)",
        "run_kind": "run_of_record" if of_record else "candidate",
        "status": labels["receipt_status"],
        "status_note": labels["receipt_status_note"],
        "route_rule_variant": args.variant,
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "One baseline vehicle context. No flood layer, no closure, no access loss, no FPPS, no A-E class, "
                    "no ensemble, and no figure for a single tambon.",
        "source_timestamp": osm_retrieved_at,
        "source_timestamps": {
            "osm_retrieved_at_utc": osm_retrieved_at,
            "population_year_represented": 2020,
            "boundaries_valid_on": "2022-01-22",
        },
        "confidence_class": "low",
        "confidence_basis": labels["confidence_basis"],
        "route_rule": ROUTE_RULES[args.variant],
        "search_window_wgs84": [round(value, 4) for value in window.bounds],
        "hospital_routes": hospital_routes,
        "corridor": {
            "path": paths["corridor"].relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(corridor_bytes).hexdigest(),
            "geometry_sha256": corridor_geometry_sha256,
            "area_km2": round(transform(to_metres, corridor).area / 1e6, 2),
            "aoi_02_area_km2": round(transform(to_metres, aoi_02).area / 1e6, 2),
            "thai_adm3_units_intersecting": int(len(in_corridor)),
        },
        "context_call": {
            "function": "floodguard.evidence_context.build_context_inputs (unchanged)",
            "aoi_geometry": "Union of the eight Mae Sai tambons, clipped to AOI-02.",
            "aoi_geometry_note": "The unclipped union lies partly outside AOI-02, and the builder refuses a demand "
                                 "area that the routing polygon does not contain.",
            "tambon_union_outside_aoi_02_m2": round(outside_m2, 1),
            "routing_geometry": "the corridor of record" if of_record else "the corridor candidate",
            "reporting_geometry": "union of the Thai COD-AB ADM3 polygons that intersect the corridor",
            "travel_mode": "legacy_vehicle",
            "facilities_supplied": 0,
            "reviewed_junctions_supplied": len(reviewed),
            "reviewed_junctions_applied": len(context["coverage"]["reviewed_shared_node_junctions_applied"]),
        },
        record_key: {
            "hospital_count": hospital_count,
            "within_routing_context_for_named_ways": all(named.values()),
            "edge_count": len(context["edges"]),
            "wall_time_minutes": round(wall_minutes, 2),
            "peak_ram_gib": _round(peak),
            "grade_split_count": review["shared_coordinate_grade_split_count"],
            "baseline_vehicle_no_route_share": round(share_joined["share"], 6),
        },
        "hospital_count_unit": acceptance["hospital_count_unit"] if of_record else "OSM objects",
        "acceptance": {
            "hospitals_in_context_min": acceptance["hospitals_in_context_min"],
            "hospitals_in_context_met": hospital_count >= acceptance["hospitals_in_context_min"],
            "named_ways_within_routing_context": named,
            "named_ways_met": all(named.values()),
            "baseline_vehicle_no_route_share_max": acceptance["baseline_vehicle_no_route_share_max"],
            "no_route_share_met_with_grade_joins": share_joined["share"] <= acceptance["baseline_vehicle_no_route_share_max"],
            "no_route_share_met_without_grade_joins": share_unjoined["share"] <= acceptance["baseline_vehicle_no_route_share_max"],
            "compute_window": {
                "plan_rule": v1b["corridor_polygon"]["compute_window"],
                "declared_by_the_operator": args.compute_window,
                "met": bool(args.compute_window),
                "run_started_at_utc": run_started_utc,
                "run_started_at_local": run_started_local,
                "run_finished_at_utc": run_finished_utc,
                "run_finished_at_local": run_finished_local,
                "note": "Met only when the operator passes --compute-window with the declaration. This script "
                        "cannot see what else runs on the machine.",
            },
            "criteria_met": criteria_met,
            "all_criteria_met": all(criteria_met.values()),
            "load_aois_counts": aoi_counts,
            "load_aois_still_returns_6": all(value == 6 for value in aoi_counts.values()),
            "criteria_note": "The PII whitelist test is checked by the test suite, not here. load_aois was called on "
                             "both AOI folders during this run.",
        },
        "hospital_count_breakdown": breakdown,
        "edge_counts": edge_tag_counts(context["edges"]),
        "reproducibility": compared,
        "baseline_no_route": {
            "definition": "Residents on graph-connected demand cells with no modelled vehicle route to any OSM hospital "
                          "in the routing context, divided by all residents on graph-connected demand cells.",
            "with_grade_joins": {key: round(value, 6) for key, value in share_joined.items()},
            "without_grade_joins": {key: round(value, 6) for key, value in share_unjoined.items()},
            "value_recorded_in_candidate": "with_grade_joins (the planning context applies decision D13)",
        },
        "grade_joins": {
            "rule_version": joins[0]["rule_version"] if joins else None,
            "coincidence_tolerance_m": 0.0,
            "join_count": len(joins),
            "grade_split_count": review["shared_coordinate_grade_split_count"],
            "possible_endpoint_transition_count": review["possible_endpoint_transition_count"],
            "joins_where_every_node_is_an_endpoint": sum(join["all_nodes_at_coordinate_are_endpoints"] for join in joins),
            "joins_sha256": joins_sha256(joins),
            "log_path": paths["log"].relative_to(ROOT).as_posix(),
            "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        },
        "context": {
            "canonical_sha256": context["canonical_sha256"],
            "road_nodes": context["coverage"]["road_nodes"],
            "connected_components": context["coverage"]["connected_components"],
            "segments_omitted_at_routing_boundary_or_degenerate":
                context["coverage"]["segments_omitted_at_routing_boundary_or_degenerate"],
            "population_cells": context["coverage"]["population_cells"],
            "modelled_population_2020": round(context["coverage"]["modelled_population_2020"], 1),
            "population_snap_coverage_fraction": round(context["coverage"]["population_snap_coverage_fraction"], 6),
            "retained": False,
            "retained_note": (
                "The context of record was written outside Git and not kept. Its canonical SHA-256 names it; a "
                "rebuild from the same inputs gives the same hash (reproducibility compares it with the candidate "
                "run of the same rule)."
                if of_record else
                "The context file is a spike product and was not kept; plan task E4 builds the context of record."
            ),
        },
        "hospitals_in_routing_context": [
            {
                "facility_id": row["facility_id"],
                "name": row["name"],
                "source_geometry_type": row["source_geometry_type"],
                "snapped_to_graph": row["node_id"] is not None,
            }
            for row in destinations
        ],
        "hospitals_outside_routing_context": sum(row.get("within_routing_context") is not True for row in hospitals),
        ("facility_counts" if of_record else "facility_counts_candidate"): facilities,
        "timing_seconds": {
            "route_search_and_corridor": round(route_seconds, 1),
            "context_build": round(build_seconds, 1),
            "baseline_access_twice": round(access_seconds, 1),
            "shelter_corroboration": _round(corroboration_seconds, 1),
        },
        "peak_memory_gib_so_far": {
            "after_route_search_and_corridor": _round(peak_after_route),
            "after_context_build": _round(peak_after_build),
            "after_baseline_access_and_facility_counts": _round(peak),
            "after_shelter_corroboration": _round(peak_after_corroboration),
        },
        "context_build_memory": {
            "sampled_peak_gib": _round(build_memory.peak_gib),
            "at_start_gib": _round(build_memory.start_gib),
            "samples": build_memory.samples,
            "sample_interval_seconds": MEMORY_SAMPLE_SECONDS,
            "note": "Current working set of this Python process, sampled while build_context_inputs ran. It "
                    "includes memory the route search had not yet returned to the operating system (see "
                    "at_start_gib), it can miss a short spike, and it leaves out the ogr2ogr child processes. "
                    "peak_ram_gib in the record above is the peak of the whole process, route search included.",
        },
        "timing_note": "wall_time_minutes is the route search plus the context build. "
                       + ("The operator declared a compute window for this run (acceptance.compute_window). "
                          if args.compute_window else
                          "No compute window was declared for this run, so the timing and memory figures are not "
                          "the ones the plan asks for and cannot close open item OI-03. ")
                       + "peak_ram_gib is the peak working set of this Python process from the start of the run "
                         "through the route search, the context build, the two baseline access runs and the "
                         "facility counts; it leaves out the ogr2ogr child processes. The shelter corroboration "
                         "step runs after that and is timed and measured apart.",
        "machine": machine,
        "input_hashes": {
            "osm_pbf_sha256": pbf_sha256,
            "worldpop_2020_sha256": context["input_hashes"]["worldpop"],
            "boundaries_sha256": boundaries_sha256,
            "aoi_02_sha256": construction["base_sha256"],
            "reviewed_junctions_sha256": sha256_file(args.reviewed_junctions) if args.reviewed_junctions else None,
        },
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "builder_sha256": sha256_file(Path(__file__)),
            "evidence_context_sha256": sha256_file(ROOT / "src" / "floodguard" / "evidence_context.py"),
            "grade_join_sha256": sha256_file(ROOT / "src" / "floodguard" / "grade_join.py"),
            "shelter_corroboration_sha256": sha256_file(ROOT / "src" / "floodguard" / "shelter_corroboration.py"),
        },
        "assumptions": assumptions,
        "limitations": limitations,
    }
    if supersedes is not None:
        receipt["supersedes"] = supersedes
    paths["corridor"].write_bytes(corridor_bytes)
    paths["log"].write_bytes(log_bytes)
    return receipt


def main() -> int:
    """Run the spike and write the receipt."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--context-root", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--reviewed-junctions", type=Path)
    parser.add_argument("--dga-facilities", type=Path)
    parser.add_argument("--ddpm-shelters", type=Path)
    parser.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument(
        "--compute-window",
        help="the operator's declaration that this run is serial, in a declared compute window with no concurrent "
             "SNAP jobs: who declared it and when. Leave it out for any other run.",
    )
    parser.add_argument(
        "--supersede-record",
        help="the reason for replacing an existing run of record; without it a run of record is never replaced.",
    )
    args = parser.parse_args()
    if args.work_dir.resolve().is_relative_to(ROOT):
        parser.error("the work folder must be outside Git")
    receipt = run(args)
    output = output_paths(args.variant, receipt["run_kind"] == "run_of_record")["receipt"]
    output.write_bytes(encode(receipt))
    record_key = "e0_spike_record" if receipt["run_kind"] == "run_of_record" else "e0_spike_record_candidate"
    print(json.dumps({"variant": args.variant, "run_kind": receipt["run_kind"], record_key: receipt[record_key],
                      "acceptance": receipt["acceptance"], "receipt_path": output.relative_to(ROOT).as_posix(),
                      "receipt_sha256": sha256_file(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
