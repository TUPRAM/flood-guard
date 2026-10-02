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

Its outputs are CANDIDATES: they close nothing until the owners pick a rule.
The corridor file and the join log say so themselves, and each carries its
source timestamp, a confidence class and its assumptions.

The plan asks for builds to run serially in a declared compute window with no
concurrent SNAP jobs. A run counts as made in such a window only when the
operator passes ``--compute-window`` with the declaration; otherwise the receipt
records that criterion as not met. A run compares itself with the previous run
of the same variant found in ``outputs/planning_v1`` and records whether the
polygon, the joins and the context are the same.

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
        --work-dir <a scratch folder outside Git>
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

SCHEMA_VERSION = "floodguard.e0_context_spike.v1"
PROTOCOL_V1A = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1a.json"
PROTOCOL_V1B = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
SEARCH_MARGIN_DEG = 0.45
HOSPITAL_SNAP_LIMIT_M = 100.0
HOSPITAL_MATCH_DISTANCE_M = 150.0
MAE_SAI_HOSPITAL_NAME_TH = "โรงพยาบาลแม่สาย"
UNNAMED_FACILITY = "Unnamed OSM candidate"
MEMORY_SAMPLE_SECONDS = 0.2
CANDIDATE_STATUS_NOTE = (
    "Candidate: open item OI-02 (the route rule) is an owner decision that has not been made. This file is not "
    "the corridor or the join log of record."
)
CONFIDENCE_BASIS = (
    "OSM roads and hospitals are unverified map records; travel times are modelled class speeds on an undirected "
    "graph; the timing was taken on a shared machine."
)
CORRIDOR_ASSUMPTIONS = [
    "The route rule is a candidate for open item OI-02; it is not an owner decision.",
    "The fastest path is found on fixed class speeds on an undirected graph that joins ways at every shared "
    "vertex coordinate. One-way rules, turn restrictions and road condition are not represented.",
    "The polygon is AOI-02 plus 3 km buffers measured in EPSG:32647. It is a routing context, not a hazard zone, "
    "an evacuation zone or a flood extent.",
    "OSM hospital ways are map records. Their operation, entrance and capacity are not verified.",
]
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
        "corroborated_shelters_note": "Not measured: it needs the shelter match distance (an owner decision) and an "
                                      "extract of OSM buildings, which this spike does not make.",
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


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Run the spike and return the receipt; candidate files are written beside it."""

    import pyogrio
    from shapely.geometry import box, mapping, shape
    from shapely.ops import transform, unary_union
    from pyproj import Transformer

    v1a = json.loads(PROTOCOL_V1A.read_text(encoding="utf-8"))
    v1b = json.loads(PROTOCOL_V1B.read_text(encoding="utf-8"))
    construction = v1b["corridor_polygon"]["construction"]
    acceptance = v1b["corridor_polygon"]["acceptance"]
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

    previous = previous_run(args.variant)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    corridor_path = OUTPUT_DIR / f"corridor_candidate_{args.variant}.geojson"
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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

    # Round-trip through JSON so the hash is taken over exactly what the file holds.
    corridor_geometry = json.loads(json.dumps(mapping(corridor)))
    corridor_geometry_sha256 = geometry_sha256(corridor_geometry)
    corridor_feature = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "id": f"corridor_candidate_{args.variant}",
                "status": "candidate",
                "status_note": CANDIDATE_STATUS_NOTE,
                "generated_at_utc": generated_at,
                "source_timestamp": osm_retrieved_at,
                "source_timestamp_note": "Retrieval time of the OpenStreetMap extract the routes were found on. "
                                         "AOI-02 and the boundaries are named by their SHA-256.",
                "confidence_class": "low",
                "confidence_basis": CONFIDENCE_BASIS,
                "assumptions": CORRIDOR_ASSUMPTIONS,
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
    corridor_path.write_bytes(encode(corridor_feature))

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
    facilities = facility_counts(destinations, corridor.intersection(reporting), args.dga_facilities,
                                 args.ddpm_shelters)
    log_path = OUTPUT_DIR / f"grade_join_log_candidate_{args.variant}.json"
    log_path.write_bytes(encode(join_log(
        joins, context_canonical_sha256=context["canonical_sha256"], status="candidate",
        status_note=CANDIDATE_STATUS_NOTE, source_timestamp=osm_retrieved_at, generated_at_utc=generated_at,
    )))

    review = context["connectivity_review"]
    share_unjoined, share_joined = no_route_share(unjoined), no_route_share(joined)
    hospital_count = len(destinations)
    wall_minutes = (route_seconds + build_seconds) / 60
    peak = peak_memory_gib()
    criteria_met = {
        "hospitals_in_context_min": hospital_count >= acceptance["hospitals_in_context_min"],
        "named_ways_within_routing_context": all(named.values()),
        "baseline_vehicle_no_route_share_max":
            share_joined["share"] <= acceptance["baseline_vehicle_no_route_share_max"],
        "declared_compute_window": bool(args.compute_window),
    }
    compared = reproducibility(previous, {
        "context_canonical_sha256": context["canonical_sha256"],
        "corridor_geometry_sha256": corridor_geometry_sha256,
        "joins_sha256": joins_sha256(joins),
        "edge_count": len(context["edges"]),
        "join_count": len(joins),
    })
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "protocol_item": "planning_protocol_v1b open items OI-01, OI-03, OI-04 and OI-06 (plan 5 item 1, task E0)",
        "status": "candidate_measurement",
        "status_note": "The corridor is built under one candidate for open item OI-02 (the route rule), which is an "
                       "owner decision. Nothing here closes an open item until the owners pick a rule.",
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
        "confidence_basis": CONFIDENCE_BASIS,
        "route_rule": ROUTE_RULES[args.variant],
        "search_window_wgs84": [round(value, 4) for value in window.bounds],
        "hospital_routes": hospital_routes,
        "corridor": {
            "path": corridor_path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(corridor_path),
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
            "routing_geometry": "the corridor candidate",
            "reporting_geometry": "union of the Thai COD-AB ADM3 polygons that intersect the corridor",
            "travel_mode": "legacy_vehicle",
            "facilities_supplied": 0,
            "reviewed_junctions_supplied": len(reviewed),
            "reviewed_junctions_applied": len(context["coverage"]["reviewed_shared_node_junctions_applied"]),
        },
        "e0_spike_record_candidate": {
            "hospital_count": hospital_count,
            "within_routing_context_for_named_ways": all(named.values()),
            "edge_count": len(context["edges"]),
            "wall_time_minutes": round(wall_minutes, 2),
            "peak_ram_gib": None if peak is None else round(peak, 2),
            "grade_split_count": review["shared_coordinate_grade_split_count"],
            "baseline_vehicle_no_route_share": round(share_joined["share"], 6),
        },
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
                "note": "Met only when the operator passes --compute-window with the declaration. This script "
                        "cannot see what else runs on the machine.",
            },
            "criteria_met": criteria_met,
            "all_criteria_met": all(criteria_met.values()),
            "criteria_note": "The PII whitelist test and the load_aois count are checked by the test suite, not here.",
        },
        "hospital_count_breakdown": hospital_breakdown(destinations),
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
            "log_path": log_path.relative_to(ROOT).as_posix(),
            "log_sha256": sha256_file(log_path),
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
            "retained_note": "The context file is a spike product and was not kept; plan task E4 builds the context of record.",
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
        "facility_counts_candidate": facilities,
        "timing_seconds": {
            "route_search_and_corridor": round(route_seconds, 1),
            "context_build": round(build_seconds, 1),
            "baseline_access_twice": round(access_seconds, 1),
        },
        "peak_memory_gib_so_far": {
            "after_route_search_and_corridor": None if peak_after_route is None else round(peak_after_route, 2),
            "after_context_build": None if peak_after_build is None else round(peak_after_build, 2),
            "at_the_end": None if peak is None else round(peak, 2),
        },
        "context_build_memory": {
            "sampled_peak_gib": None if build_memory.peak_gib is None else round(build_memory.peak_gib, 2),
            "at_start_gib": None if build_memory.start_gib is None else round(build_memory.start_gib, 2),
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
                       + "Peak RAM is the peak working set of this Python process, read at the end of the run; it "
                         "leaves out the ogr2ogr child processes.",
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
        },
        "assumptions": [
            "The route rule is a candidate for open item OI-02; it is not an owner decision.",
            "The route-selection graph joins ways at every shared vertex coordinate, whatever their grade tags. The "
            "context graph does not: it keeps grade-separated vertices apart and joins them only under decision D13.",
            "Road times are fixed class speeds on an undirected graph. One-way rules, turn restrictions and road "
            "condition are not represented.",
            "A hospital is an OSM object tagged as a hospital. Its operation, entrance and capacity are not verified.",
            "A grade join shows that two ways end at the same OSM coordinate. It does not show the transition can be driven.",
            "hospital_count counts OSM objects. Two objects can describe one hospital, and an unnamed object may not "
            "be a hospital; hospital_count_breakdown says how many there are of each.",
        ],
        "limitations": [
            "This is one build on one day. It is a measurement for the owners, not the context of record.",
            "Facility counts are counts of map and list records. No hospital and no shelter was checked on the ground.",
            "The number of corroborated shelters is not measured.",
        ],
    }
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
    args = parser.parse_args()
    if args.work_dir.resolve().is_relative_to(ROOT):
        parser.error("the work folder must be outside Git")
    receipt = run(args)
    output = OUTPUT_DIR / f"e0_context_spike_{args.variant}.json"
    output.write_bytes(encode(receipt))
    print(json.dumps({"variant": args.variant, "e0_spike_record_candidate": receipt["e0_spike_record_candidate"],
                      "acceptance": receipt["acceptance"], "receipt_sha256": sha256_file(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
