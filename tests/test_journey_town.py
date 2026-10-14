"""Tests for the journey town pack (``scripts/build_journey_town.py`` and ``apps/web/public/journey/town/``).

Every test reads the committed pack, the committed replay r5 and the committed receipt, so none needs the external
data. Only the byte-for-byte re-bake (``--verify``) is skipped when ``FLOODGUARD_EXTERNAL_DATA`` is not set.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TOWN = ROOT / "apps" / "web" / "public" / "journey" / "town"
MANIFEST = TOWN / "mae-sai-town.json"
RECEIPT = ROOT / "docs" / "journey_town_input_receipt.json"
R5 = ROOT / "apps" / "web" / "public" / "studies" / "mae-sai-2024-timeline" / "r5"
PRACTICE_TS = ROOT / "apps" / "web" / "src" / "lib" / "public-practice-scenarios.ts"
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|/Users/|\\Users\\|/home/|%20")
EXPECTED_FILES = {"LICENSE.txt", "mae-sai-town.json", "mae-sai-town-cells.png", "mae-sai-town-relief.png",
                  "mae-sai-town-cover.png", "mae-sai-town-backdrop.png"}
EXPECTED_STAGES = {12: 0.0, 40: 0.1, 46: 1.2612902426637274, 48: 1.8806463600440977, 84: 3.5, 132: 0.9}
ORIGIN_LAT, ORIGIN_LON = 20.44042, 99.88718
M_PER_DEG_LON = 111320 * math.cos(math.radians(ORIGIN_LAT))
M_PER_DEG_LAT = 110540


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def timeline() -> dict[str, Any]:
    return json.loads((R5 / "timeline.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def receipt() -> dict[str, Any]:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(values: list[int]) -> np.ndarray:
    """One delta-encoded run of decimetre pairs to absolute metres."""
    return np.cumsum(np.asarray(values, dtype=np.int64).reshape(-1, 2), axis=0) / 10.0


def decode_runs(starts: list[int], coords: list[int]) -> list[np.ndarray]:
    """Rings or lines: ``starts`` are vertex indices (count + 1); each run's first vertex is absolute."""
    flat = np.asarray(coords, dtype=np.int64).reshape(-1, 2)
    return [np.cumsum(flat[a:b], axis=0) / 10.0 for a, b in zip(starts[:-1], starts[1:])]


def merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def r5_cell(timeline: dict[str, Any], lat: float, lon: float) -> tuple[int, int]:
    """(row, col) of the r5 HAND raster for a point: linear in longitude and in Web Mercator y over the rounded bounds."""
    (south, west), (north, east) = timeline["bounds"]
    col = math.floor((lon - west) / (east - west) * timeline["hand"]["width"])
    row = math.floor((merc_y(north) - merc_y(lat)) / (merc_y(north) - merc_y(south)) * timeline["hand"]["height"])
    return row, col


def cell_depth(code: int, stage: float, factor_byte: int, scale: float) -> float | None:
    """The app's ``cellDepth`` rule (flood-timeline.ts)."""
    k = factor_byte / 255 * scale
    if code == 0:
        return k * max(0.0, stage)
    if code == 255 or not code * 0.05 < stage:
        return None
    return k * (stage - code * 0.05)


def parse_practice() -> tuple[dict[str, tuple[float, float]], list[dict[str, Any]]]:
    """Practice homes and scenarios from the app's TypeScript source (independent of the bake's parser)."""
    text = PRACTICE_TS.read_text(encoding="utf-8")
    homes_block = text[text.index("PRACTICE_HOMES"):text.index("export interface PracticeScenario")]
    homes = {}
    for name in ("dry", "flooded"):
        match = re.search(name + r":\s*\{\s*latitude:\s*([-\d.]+),\s*longitude:\s*([-\d.]+)", homes_block)
        assert match, name
        homes[name] = (float(match.group(1)), float(match.group(2)))
    scenario_block = text[text.index("export const PRACTICE_SCENARIOS"):text.index("export function practiceScenario")]
    scenarios = [{"id": m.group(1), "home": m.group(2), "hour": int(m.group(3))}
                 for m in re.finditer(r'id:\s*"(\w+)",\s*home:\s*"(\w+)",\s*hour:\s*(\d+)', scenario_block)]
    return homes, scenarios


def load_bake():
    """Import the bake script by file, with ``scripts/`` and ``src/`` importable."""
    for dependency in ("PIL", "pyogrio", "rasterio", "scipy", "shapely"):
        pytest.importorskip(dependency)
    for path in (SCRIPTS, ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("build_journey_town", SCRIPTS / "build_journey_town.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Provenance and guard fields -----------------------------------------------------------------------------------


def test_manifest_guard_fields(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    assert manifest["schema"] == "floodguard.journey-town.v1"
    assert manifest["generated_by"] == "scripts/build_journey_town.py"
    assert manifest["data_mode"] == "historical_reconstruction"
    assert manifest["real_time"] is False and manifest["official_warning"] is False
    assert manifest["operational_status"] == "non_operational" and manifest["can_feed_decision_layer"] is False
    assert manifest["confidence"] == "low"
    reason = manifest["confidence_reason"]
    assert timeline["confidence_reason"] in reason and "earlier years" in reason and "illustrative" in reason
    assert manifest["source_timestamp"] == timeline["source_timestamp"]
    assert manifest["generated_at"]["basis"] == "declared"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", manifest["generated_at"]["value"])
    assert len(manifest["assumptions"]) >= 5 and len(manifest["limitations"]) >= 5
    assert any("not a real-time" in text.lower() or "official warning" in text for text in manifest["limitations"])
    assert manifest["licence"]["database"] == "ODbL-1.0"
    for source in manifest["sources"]:
        assert set(source) >= {"id", "name", "licence", "attribution", "timestamp"} and all(source.values())


def test_every_referenced_file_matches_its_hash(manifest: dict[str, Any]) -> None:
    assert {path.name for path in TOWN.iterdir()} == EXPECTED_FILES
    referenced = [manifest[key] for key in ("cells", "relief", "cover", "backdrop", "licence")]
    assert {entry["href"].rsplit("/", 1)[1] for entry in referenced} == EXPECTED_FILES - {"mae-sai-town.json"}
    for entry in referenced:
        assert entry["href"].startswith("/journey/town/")
        path = TOWN / entry["href"].rsplit("/", 1)[1]
        assert sha256(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]


def test_replay_hashes_equal_the_committed_r5_files(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    replay = manifest["replay"]
    assert replay["timeline_sha256"] == sha256(R5 / "timeline.json")
    assert replay["hand_sha256"] == sha256(R5 / "hand-codes.png") == timeline["hand"]["sha256"]
    assert replay["access_nodes_sha256"] == sha256(R5 / "access-nodes.bin") == timeline["access"]["nodes"]["sha256"]
    assert (replay["study_id"], replay["revision"], replay["data_version"]) == (timeline["study_id"], timeline["revision"], timeline["data_version"])
    assert replay["stage_anchors"] == timeline["stage_anchors"]
    assert replay["impassable_depth_m"] == timeline["impassable_depth_m"] == 0.3
    assert replay["hand"] == {"step_m": 0.05, "byte_scale": timeline["hand"]["depth_factor"]["byte_scale"], "channel_code": 0,
                              "never_code": 255, "low_confidence_min_byte": 128}
    assert replay["epoch"] == "2024-09-09T00:00:00+07:00"


# --- Cells, relief, cover, backdrop --------------------------------------------------------------------------------


def test_cells_png_is_the_r5_crop_cell_for_cell(manifest: dict[str, Any]) -> None:
    from PIL import Image

    cells = manifest["cells"]
    with Image.open(TOWN / "mae-sai-town-cells.png") as image:
        assert image.mode == "RGB"
        crop = np.asarray(image)
    with Image.open(R5 / "hand-codes.png") as image:
        r5 = np.asarray(image.convert("RGB"))
    assert crop.shape == (cells["rows"], cells["cols"], 3)
    source = r5[cells["row0"]:cells["row0"] + cells["rows"], cells["col0"]:cells["col0"] + cells["cols"]]
    assert np.array_equal(crop[..., 0], source[..., 0]) and np.array_equal(crop[..., 1], source[..., 1])
    low = np.where((source[..., 2] >= 128) & (source[..., 0] != 0), 255, 0)
    assert np.array_equal(crop[..., 2], low)


def test_cell_affine_reproduces_the_home_and_neighbour_cells(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    cells = manifest["cells"]
    assert cells["max_affine_error_m"] < 1.0
    homes, _ = parse_practice()
    expected = {"dry": (380, 550, 76), "flooded": (374, 546, 55)}
    from PIL import Image

    with Image.open(TOWN / "mae-sai-town-cells.png") as image:
        crop = np.asarray(image)
    for name, (lat, lon) in homes.items():
        row, col, code = expected[name]
        assert r5_cell(timeline, lat, lon) == (row, col)
        x, z = (lon - ORIGIN_LON) * M_PER_DEG_LON, (ORIGIN_LAT - lat) * M_PER_DEG_LAT
        c = math.floor((x - (cells["x0"] - cells["dx"] / 2)) / cells["dx"])
        r = math.floor((z - (cells["z0"] - cells["dz"] / 2)) / cells["dz"])
        assert (cells["row0"] + r, cells["col0"] + c) == (row, col)
        assert int(crop[r, c, 0]) == code
    # Every crop cell centre lies within the recorded error of the exact Web Mercator mapping.
    (south, west), (north, east) = timeline["bounds"]
    cols = np.arange(cells["cols"])
    rows = np.arange(cells["rows"])
    lon = west + (cells["col0"] + cols + 0.5) / 1610 * (east - west)
    y = merc_y(north) - (cells["row0"] + rows + 0.5) / 1753 * (merc_y(north) - merc_y(south))
    lat = np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)
    ex = np.abs(cells["x0"] + cols * cells["dx"] - (lon - ORIGIN_LON) * M_PER_DEG_LON).max()
    ez = np.abs(cells["z0"] + rows * cells["dz"] - (ORIGIN_LAT - lat) * M_PER_DEG_LAT).max()
    assert math.hypot(ex, ez) <= cells["max_affine_error_m"] + 1e-3


def test_relief_and_backdrop_encodings(manifest: dict[str, Any]) -> None:
    from PIL import Image

    cells, relief = manifest["cells"], manifest["relief"]
    with Image.open(TOWN / "mae-sai-town-cells.png") as image:
        code = np.asarray(image)[..., 0]
    with Image.open(TOWN / "mae-sai-town-relief.png") as image:
        assert image.mode == "RGB"
        rgb = np.asarray(image).astype(np.int64)
    assert rgb.shape == (cells["rows"], cells["cols"], 3) and not rgb[..., 2].any()
    value = rgb[..., 0] * 256 + rgb[..., 1]
    never = code == 255
    assert not value[~never].any()
    height = (value[never] - 2000) / 10
    assert height.min() >= relief["clamp_min_m"] - 0.05 and int(never.sum()) == relief["never_cells"]
    assert 300 < relief["datum_m"] < 500
    backdrop = manifest["backdrop"]
    with Image.open(TOWN / "mae-sai-town-backdrop.png") as image:
        assert image.mode == "RGB"
        b = np.asarray(image).astype(np.int64)
    assert b.shape == (backdrop["rows"], backdrop["cols"], 3) and backdrop["cell_m"] == 60
    heights = (b[..., 0] * 256 + b[..., 1] - 2000) / 10
    assert heights.min() == pytest.approx(backdrop["height_range_m"][0], abs=0.1)
    assert heights.max() == pytest.approx(backdrop["height_range_m"][1], abs=0.1)
    frame = manifest["frame"]["backdrop"]
    assert backdrop["x0"] - 30 == frame["x_min"] and backdrop["z0"] - 30 == frame["z_min"]
    assert (frame["x_min"] + frame["x_max"]) / 2 == -300 and (frame["z_min"] + frame["z_max"]) / 2 == 500


def test_cover_classes(manifest: dict[str, Any]) -> None:
    from PIL import Image

    cover = manifest["cover"]
    with Image.open(TOWN / "mae-sai-town-cover.png") as image:
        assert image.mode == "L"
        data = np.asarray(image)
    assert data.shape == (cover["rows"], cover["cols"]) == (650, 600) and cover["cell_m"] == 4
    assert [c["id"] for c in cover["classes"]] == ["open_ground", "water", "road", "building", "green", "field"]
    assert int(data.max()) <= 5
    assert {c["id"]: int(np.count_nonzero(data == c["value"])) for c in cover["classes"]} == cover["counts"]
    assert cover["precedence"][:3] == ["water", "building", "road"]


# --- Beats, homes and the walk --------------------------------------------------------------------------------------


def test_beat_stages_equal_numpy_interp_exactly(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    ts = [a["t"] for a in timeline["stage_anchors"]]
    stages = [a["stage_m"] for a in timeline["stage_anchors"]]
    hours = [beat["hour"] for beat in manifest["beats"]]
    assert hours == [12, 40, 46, 48, 49, 84, 132]
    for beat in manifest["beats"]:
        assert beat["t"] == beat["hour"] / 24
        assert beat["stage_m"] == float(np.interp(beat["hour"] / 24, ts, stages))
        if beat["hour"] in EXPECTED_STAGES:
            assert beat["stage_m"] == EXPECTED_STAGES[beat["hour"]]
        day, hour = divmod(beat["hour"], 24)
        assert beat["time_local"] == f"2024-09-{9 + day:02d}T{hour:02d}:00:00+07:00"


def test_home_dry_at_every_beat_and_neighbour_wet_at_hour_84(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    scale = timeline["hand"]["depth_factor"]["byte_scale"]
    places = {p["id"]: p for p in manifest["places"]}
    home, neighbour = places["home"]["cell"], places["neighbour"]["cell"]
    assert (home["row"], home["col"], home["code"]) == (380, 550, 76)
    assert (neighbour["row"], neighbour["col"], neighbour["code"]) == (374, 546, 55)
    for beat in manifest["beats"]:
        assert beat["home_depth_m"] is None
        assert cell_depth(home["code"], beat["stage_m"], home["factor_byte"], scale) is None
        expected = cell_depth(neighbour["code"], beat["stage_m"], neighbour["factor_byte"], scale)
        assert (beat["neighbour_depth_m"] is None) == (expected is None)
        if expected is not None:
            assert beat["neighbour_depth_m"] == pytest.approx(expected, abs=1e-4)
        assert 0 <= beat["wet_share_450m"] <= 1
    by_hour = {beat["hour"]: beat for beat in manifest["beats"]}
    assert by_hour[84]["neighbour_depth_m"] == 0.75


def test_route_open_at_48_cut_at_84_and_consistent_with_the_app(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    route = manifest["route"]
    by_hour = {beat["hour"]: beat for beat in manifest["beats"]}
    assert by_hour[48]["route_open"] is True and by_hour[84]["route_open"] is False
    assert route["destination"] == "R01" and route["length_m"] <= 2000
    closures = [edge[2] for edge in route["edges"] if edge[2] is not None]
    assert route["cut_stage_m"] == min(closures) == route["first_cut"]["closure_stage_m"]
    for beat in manifest["beats"]:
        assert beat["route_open"] is (route["cut_stage_m"] > beat["stage_m"])
        if beat["best_path"] is not None:
            assert beat["best_path"]["length_m"] <= 2000
    assert by_hour[84]["best_path"] is None and by_hour[48]["best_path"]["destination"] == "R01"
    points = decode(route["points"])
    places = {p["id"]: p for p in manifest["places"]}
    assert tuple(points[0]) == (0.0, 0.0)
    assert points[-1] == pytest.approx([places["R01"]["x"], places["R01"]["z"]], abs=0.06)
    assert all(0 <= a < b < len(points) for a, b, _ in route["edges"])
    # The app's figures, recomputed from the committed access nodes.
    app = route["app"]
    access = timeline["access"]
    layout = {item["name"]: item for item in access["nodes"]["layout"]}
    raw = (R5 / "access-nodes.bin").read_bytes()
    count = access["nodes"]["count"]
    lon = np.frombuffer(raw, "<f4", count, layout["lon"]["offset"]).astype(float)
    lat = np.frombuffer(raw, "<f4", count, layout["lat"]["offset"]).astype(float)
    distance = np.hypot((lon - ORIGIN_LON) * M_PER_DEG_LON, (lat - ORIGIN_LAT) * M_PER_DEG_LAT)
    node = int(np.argmin(distance))
    assert app["node_index"] == node and distance[node] <= 150
    set_index = access["sets"].index("reported_2024")
    shape = layout["cut_codes"]["shape"]
    cut = np.frombuffer(raw, "u1", shape[0] * shape[1], layout["cut_codes"]["offset"]).reshape(shape)
    assert app["set_index"] == set_index and app["cut_code"] == int(cut[set_index, node])
    assert app["cut_level_m"] == access["levels"][app["cut_code"]]
    assert app["home_code"] == int(np.frombuffer(raw, "u1", count, layout["home_code"]["offset"])[node])
    assert app["home_k_byte"] == int(np.frombuffer(raw, "u1", count, layout["home_k"]["offset"])[node])
    assert abs(route["cut_stage_m"] - app["cut_level_m"]) <= 0.25
    assert by_hour[48]["stage_m"] < app["cut_level_m"] < by_hour[84]["stage_m"]


def r5_closure_stage(code: np.ndarray, k: np.ndarray) -> float:
    """The replay's road rule (``sample_road`` then ``closure_stage``) on one edge's samples, written out again here.

    Channel and never-flood samples are ignored; the lowest HAND ``h`` and an equivalent factor capped at 1 give the
    stage at which some sample reaches the impassable 0.3 m.
    """
    use = (code != 0) & (code != 255)
    if not use.any():
        return math.inf
    hand = code[use] * 0.05
    with np.errstate(divide="ignore"):
        lowest = float(np.min(hand + 0.3 / k[use]))
    h = round(float(hand.min()), 2)
    k_eq = round(min(0.3 / max(lowest - h, 0.3), 1.0), 4)
    return round(h + 0.3 / k_eq, 6)


def test_walk_recomputed_from_the_network_and_r5_cells(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    """Access loss of the usual walk, recomputed without the bake: scipy Dijkstra on the committed network, closures
    from 10 m samples on the r5 cells, and the open or cut state and best shelter at every beat."""
    from PIL import Image

    pytest.importorskip("scipy")
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

    route = manifest["route"]
    (south, west), (north, east) = timeline["bounds"]
    scale = timeline["hand"]["depth_factor"]["byte_scale"]
    with Image.open(R5 / "hand-codes.png") as image:
        rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    with (ROOT / route["network"]).open(encoding="utf-8", newline="") as stream:
        pairs = [(row["from_node"], row["to_node"]) for row in csv.DictReader(stream)]
    ids = sorted({node for pair in pairs for node in pair})
    index = {node: i for i, node in enumerate(ids)}
    lonlat = np.array([[float(v) for v in node.split("-")[1:3]] for node in ids])
    x = (lonlat[:, 0] - ORIGIN_LON) * M_PER_DEG_LON
    z = (ORIGIN_LAT - lonlat[:, 1]) * M_PER_DEG_LAT
    u = np.array([index[a] for a, _ in pairs])
    v = np.array([index[b] for _, b in pairs])
    length = np.hypot(x[v] - x[u], z[v] - z[u])
    # Edges are straight segments between nodes, so a walk of at most 2 km stays within 2 km of the home node.
    home = int(np.argmin(np.hypot(x, z)))
    near = np.hypot(x - x[home], z - z[home]) <= 2000.0 + 1e-6
    keep = near[u] & near[v]
    assert len({(min(a, b), max(a, b)) for a, b in zip(u[keep], v[keep])}) == int(keep.sum())  # No parallel edges to merge.
    top = merc_y(north)
    span = top - merc_y(south)
    close = np.full(len(pairs), math.inf)
    for e in np.flatnonzero(keep):
        steps = np.linspace(0.0, 1.0, max(2, int(length[e] // 10) + 2))
        lon = lonlat[u[e], 0] + steps * (lonlat[v[e], 0] - lonlat[u[e], 0])
        lat = lonlat[u[e], 1] + steps * (lonlat[v[e], 1] - lonlat[u[e], 1])
        col = np.floor((lon - west) / (east - west) * width).astype(np.int64)
        row = np.floor((top - np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))) / span * height).astype(np.int64)
        close[e] = r5_closure_stage(rgb[row, col, 0].astype(np.int64), rgb[row, col, 1] / 255 * scale)
    shelters = {}
    for record in timeline["shelters"]["reported"]:
        if record.get("in_access_set") and record.get("lat") is not None:
            sx, sz = (record["lon"] - ORIGIN_LON) * M_PER_DEG_LON, (ORIGIN_LAT - record["lat"]) * M_PER_DEG_LAT
            shelters[record["id"]] = int(np.argmin(np.hypot(x - sx, z - sz)))

    def best(stage: float) -> tuple[float, str, np.ndarray] | None:
        open_edges = keep & (close > stage)
        graph = coo_matrix((np.maximum(length[open_edges], 1e-9), (u[open_edges], v[open_edges])), shape=(len(ids), len(ids))).tocsr()
        dist, pred = dijkstra(graph, directed=False, indices=home, return_predecessors=True, limit=2000.0 + 1e-6)
        options = sorted((float(dist[n]), sid) for sid, n in shelters.items() if np.isfinite(dist[n]) and dist[n] <= 2000.0 + 1e-6)
        return (*options[0], pred) if options else None

    assert route["from"]["node"] == ids[home]
    usual = best(0.0)
    assert usual is not None
    walk_m, destination, pred = usual
    assert destination == route["destination"] and abs(walk_m - route["length_m"]) <= 0.01 * walk_m
    path = [shelters[destination]]
    while path[-1] != home:
        path.append(int(pred[path[-1]]))
    path.reverse()
    edge_of = {(min(a, b), max(a, b)): e for e, (a, b) in enumerate(zip(u.tolist(), v.tolist()))}
    closures = [close[edge_of[(min(a, b), max(a, b))]] for a, b in zip(path[:-1], path[1:])]
    assert len(closures) == len(route["edges"])
    for mine, (_, _, stored) in zip(closures, route["edges"]):
        assert (stored is None and math.isinf(mine)) or abs(mine - stored) <= 1e-4
    cut_stage = float(min(closures))
    assert abs(cut_stage - route["cut_stage_m"]) <= 0.05
    for beat in manifest["beats"]:
        assert beat["route_open"] is (cut_stage > beat["stage_m"])
        found = best(beat["stage_m"])
        if found is None:
            assert beat["best_path"] is None, beat["hour"]
        else:
            assert beat["best_path"] is not None and beat["best_path"]["destination"] == found[1], beat["hour"]
            assert abs(beat["best_path"]["length_m"] - found[0]) <= 0.01 * found[0], beat["hour"]


def test_first_cut_low_point_is_the_sample_that_closes_the_walk(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    """The scene pins its 'low point' and 'walk cut' labels here: on the first closing edge, on a cell that closes at the
    walk's cut stage (not at the edge's start, which can be dry when the walk is already cut)."""
    from PIL import Image

    route = manifest["route"]
    first = route["first_cut"]
    low = first["low_point"]
    assert first["along_m"][0] <= low["along_m"] <= first["along_m"][1]
    points = decode(route["points"])
    a, b = points[first["edge"] + 1], points[first["edge"] + 2]
    t = (low["along_m"] - first["along_m"][0]) / (first["along_m"][1] - first["along_m"][0])
    assert [low["x"], low["z"]] == pytest.approx(list(a + t * (b - a)), abs=0.3)
    scale = timeline["hand"]["depth_factor"]["byte_scale"]
    with Image.open(R5 / "hand-codes.png") as image:
        rgb = np.asarray(image.convert("RGB"))
    row, col = r5_cell(timeline, ORIGIN_LAT - low["z"] / M_PER_DEG_LAT, ORIGIN_LON + low["x"] / M_PER_DEG_LON)
    code, k = np.array([int(rgb[row, col, 0])]), np.array([rgb[row, col, 1] / 255 * scale])
    assert r5_closure_stage(code, k) == pytest.approx(route["cut_stage_m"], abs=1e-3)
    # The edge's start is a higher cell that is still dry at hour 49, when the walk is already cut.
    row0, col0 = r5_cell(timeline, ORIGIN_LAT - first["z"] / M_PER_DEG_LAT, ORIGIN_LON + first["x"] / M_PER_DEG_LON)
    assert int(rgb[row0, col0, 0]) > code[0]


def test_wet_share_recomputed_from_the_cells(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    """Share of r5 cells within 450 m of the home with water at each beat (the app's cellDepth rule, exact centres)."""
    from PIL import Image

    cells = manifest["cells"]
    scale = timeline["hand"]["depth_factor"]["byte_scale"]
    with Image.open(TOWN / "mae-sai-town-cells.png") as image:
        crop = np.asarray(image).astype(np.int64)
    (south, west), (north, east) = timeline["bounds"]
    cols, rows = np.arange(cells["cols"]), np.arange(cells["rows"])
    lon = west + (cells["col0"] + cols + 0.5) / 1610 * (east - west)
    y = merc_y(north) - (cells["row0"] + rows + 0.5) / 1753 * (merc_y(north) - merc_y(south))
    lat = np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)
    xx, zz = np.meshgrid((lon - ORIGIN_LON) * M_PER_DEG_LON, (ORIGIN_LAT - lat) * M_PER_DEG_LAT)
    near = np.hypot(xx, zz) <= 450.0
    codes, factors = crop[..., 0][near], crop[..., 1][near]
    for beat in manifest["beats"]:
        wet = sum(1 for c, f in zip(codes.tolist(), factors.tolist())
                  if (d := cell_depth(c, beat["stage_m"], f, scale)) is not None and d > 0)
        assert beat["wet_share_450m"] == round(wet / int(near.sum()), 4), beat["hour"]


def test_places(manifest: dict[str, Any], timeline: dict[str, Any]) -> None:
    places = {p["id"]: p for p in manifest["places"]}
    assert places["home"]["kind"] == places["neighbour"]["kind"] == "example_home"
    assert (places["home"]["practice_home"], places["neighbour"]["practice_home"]) == ("dry", "flooded")
    reported = {r["id"]: r for r in timeline["shelters"]["reported"]}
    for pid, place in places.items():
        assert place["name"]["en"] and place["name"]["th"] and place["cell"]["code"] in range(256)
        if place["kind"] == "reported_site":
            assert place["in_access_set"] == reported[pid]["in_access_set"] and place["role"] == reported[pid]["role"]
    assert places["R05"]["role"] == "relief_command_centre"
    r04 = places["R04"]
    assert r04["in_access_set"] is False and r04["cell"]["code"] == 182
    assert r04["model_vs_report"]["model_dry_at_peak"] is True and "11-12 Sep 2024" in r04["model_vs_report"]["reported"]
    assert places["sai_river"]["kind"] == "river_label"


# --- Vectors --------------------------------------------------------------------------------------------------------


def test_vector_arrays_are_consistent(manifest: dict[str, Any]) -> None:
    b = manifest["buildings"]
    n = b["count"]
    assert n > 5000 and len(b["ring_start"]) == n + 1 and len(b["coords"]) == 2 * b["ring_start"][-1]
    for key in ("kind", "floors", "front", "rect", "area_m2", "compound", "conf", "src"):
        assert len(b[key]) == n, key
    assert len(b["obb"]) == 5 * n
    floors = {"shophouse": (2, 4), "house": (1, 2), "large": (1, 2), "shed": (1, 1), "temple": (1, 1),
              "government": (2, 3), "school": (2, 3), "market": (1, 1)}
    assert b["kinds"] == list(floors)
    rings = decode_runs(b["ring_start"], b["coords"])
    for i, ring in enumerate(rings):
        x, z = ring[:, 0], ring[:, 1]
        area = 0.5 * float(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1)))
        assert len(ring) >= 3 and area > 0 and 0 <= b["front"][i] < len(ring)
        lo, hi = floors[b["kinds"][b["kind"][i]]]
        assert lo <= b["floors"][i] <= hi
        assert 0 <= b["rect"][i] <= 100 and 0 <= b["obb"][5 * i + 4] < 18000
        assert -1 <= b["compound"][i] < len(manifest["places"])
    for key in ("home", "neighbour", "district_office", "municipality_office"):
        assert isinstance(b[key], int) and 0 <= b[key] < n
    assert b["kinds"][b["kind"][b["district_office"]]] == "government"
    r = manifest["roads"]
    assert len(r["line_start"]) == r["count"] + 1 and len(r["coords"]) == 2 * r["line_start"][-1]
    for key in ("class", "width_dm", "bridge", "osm_id", "name"):
        assert len(r[key]) == r["count"], key
    assert r["classes"][0] == "trunk" and max(r["class"]) < len(r["classes"])
    t = manifest["trees"]
    assert 0 < t["count"] <= 5000 and len(t["coords"]) == 2 * t["count"]
    assert len(t["kind"]) == len(t["scale"]) == t["count"] and max(t["kind"]) < len(t["kinds"])
    trees = decode(t["coords"])
    order = np.lexsort((trees[:, 0], trees[:, 1]))
    assert np.array_equal(order, np.arange(len(trees)))


def test_all_coordinates_fall_inside_their_extent(manifest: dict[str, Any]) -> None:
    detail = manifest["frame"]["detail"]
    assert (detail["x_min"], detail["x_max"], detail["z_min"], detail["z_max"]) == (-1500, 900, -800, 1800)

    def inside(points: np.ndarray) -> bool:
        return bool(len(points) == 0 or (points[:, 0].min() >= detail["x_min"] and points[:, 0].max() <= detail["x_max"]
                                         and points[:, 1].min() >= detail["z_min"] and points[:, 1].max() <= detail["z_max"]))

    b, r = manifest["buildings"], manifest["roads"]
    assert all(inside(ring) for ring in decode_runs(b["ring_start"], b["coords"]))
    assert all(inside(line) for line in decode_runs(r["line_start"], r["coords"]))
    assert inside(decode(manifest["trees"]["coords"]))
    assert inside(decode(manifest["route"]["points"]))
    for beat in manifest["beats"]:
        if beat["best_path"]:
            assert inside(decode(beat["best_path"]["points"]))
    assert inside(np.array([[p["x"], p["z"]] for p in manifest["places"]]))
    obb = np.asarray(b["obb"]).reshape(-1, 5)[:, :2] / 10.0
    assert inside(obb)


# --- Files, rights and budget ---------------------------------------------------------------------------------------


def test_json_receipt_and_licence_are_lf_with_a_trailing_newline() -> None:
    for path in (MANIFEST, RECEIPT, TOWN / "LICENSE.txt"):
        data = path.read_bytes()
        assert b"\r" not in data and data.endswith(b"\n") and not data.endswith(b"\n\n"), path.name
    assert MANIFEST.read_bytes().count(b"\n") == 1  # Compact JSON: one line.


def test_no_machine_paths() -> None:
    for path in (MANIFEST, RECEIPT, TOWN / "LICENSE.txt", SCRIPTS / "build_journey_town.py"):
        text = path.read_text(encoding="utf-8")
        assert not LOCAL_PATH.search(text), path.name


def test_size_budget() -> None:
    for name in EXPECTED_FILES:
        size = (TOWN / name).stat().st_size
        if name.endswith(".png"):
            assert size <= 400 * 1024, name
    assert MANIFEST.stat().st_size <= 1.6 * 1024 * 1024
    assert sum(path.stat().st_size for path in TOWN.iterdir()) <= 2.6 * 1024 * 1024


def test_credits_name_every_source(manifest: dict[str, Any]) -> None:
    licence = (TOWN / "LICENSE.txt").read_text(encoding="utf-8")
    for text in (manifest["credits"]["en"], manifest["credits"]["th"], licence):
        for name in ("Open Buildings", "OpenStreetMap", "Copernicus", "VIDA"):
            assert name in text
    assert "ODbL" in manifest["credits"]["en"] and "CC BY 4.0" in manifest["credits"]["en"]
    assert "not a legal clearance" in licence and "Open Database License 1.0" in licence


def test_practice_homes_and_hours_match_the_app(manifest: dict[str, Any]) -> None:
    homes, scenarios = parse_practice()
    assert homes["dry"] == (ORIGIN_LAT, ORIGIN_LON)
    assert manifest["frame"]["origin"] == {"lat": ORIGIN_LAT, "lon": ORIGIN_LON}
    places = {p["id"]: p for p in manifest["places"]}
    lat, lon = homes["flooded"]
    assert places["neighbour"]["x"] == round((lon - ORIGIN_LON) * M_PER_DEG_LON, 2)
    assert places["neighbour"]["z"] == round((ORIGIN_LAT - lat) * M_PER_DEG_LAT, 2)
    beats = {beat["hour"]: beat for beat in manifest["beats"]}
    assert {s["hour"] for s in scenarios} <= set(beats)
    for hour, beat in beats.items():
        assert beat["practice"] == [{"id": s["id"], "home": s["home"]} for s in scenarios if s["hour"] == hour]
    assert beats[49]["practice"] == []


def test_receipt_records_inputs_outputs_and_code(manifest: dict[str, Any], receipt: dict[str, Any]) -> None:
    assert receipt["schema"] == "floodguard.bake_input_receipt.v1" and receipt["generated_by"] == "scripts/build_journey_town.py"
    assert receipt["generated_at"] == {"value": manifest["generated_at"]["value"], "basis": "declared"}
    assert receipt["confidence"] == "low" and receipt["source_timestamp"] == manifest["source_timestamp"]
    assert {row["root"] for row in receipt["inputs"]} == {"external", "repo"}
    repo_inputs = {row["path"]: row for row in receipt["inputs"] if row["root"] == "repo"}
    assert set(repo_inputs) == {
        "apps/web/public/studies/mae-sai-2024-timeline/r5/timeline.json", "apps/web/public/studies/mae-sai-2024-timeline/r5/hand-codes.png",
        "apps/web/public/studies/mae-sai-2024-timeline/r5/access-nodes.bin", "outputs/mae_sai_access_edges.csv",
        "outputs/buildings_in_water/outlines_v1.json"}
    for path, row in repo_inputs.items():
        assert sha256(ROOT / path) == row["sha256"], path
    external = {row["path"] for row in receipt["inputs"] if row["root"] == "external"}
    assert "proposal_execution/buildings_in_water/mae_sai_outlines.gpkg" in external
    assert "open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif" in external
    outputs = receipt["outputs"]
    assert outputs["folder"] == "apps/web/public/journey/town"
    assert {row["name"]: row["sha256"] for row in outputs["files"]} == {name: sha256(TOWN / name) for name in EXPECTED_FILES}


def test_bake_sources_cover_every_repository_module_the_bake_imports() -> None:
    bake = load_bake()
    listed = set(bake.BAKE_SOURCES)
    assert all((ROOT / path).is_file() for path in listed) and bake.GENERATED_BY in listed
    seen: set[str] = set()
    queue = [bake.GENERATED_BY]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                if name.startswith("floodguard."):
                    queue.append(f"src/{name.replace('.', '/')}.py")
                elif name.startswith("mae_sai_timeline_"):
                    queue.append(f"scripts/{name}.py")
    assert seen <= listed, f"imported by the bake but not hashed in the receipt: {sorted(seen - listed)}"


def test_bake_helpers() -> None:
    bake = load_bake()
    assert bake.delta_encode(np.array([[10, -5], [12, -5], [12, 0]])) == [10, -5, 2, 0, 0, 5]
    assert bake.normalise_time("2026-10-14T19:00:00+07:00") == "2026-10-14T12:00:00Z"
    with pytest.raises(ValueError):
        bake.normalise_time("2026-10-14T12:00:00")
    assert bake.cell_depth(55, 3.5, 102, 2.5) == pytest.approx(0.75)
    assert bake.cell_depth(76, 3.5, 102, 2.5) is None and bake.cell_depth(255, 9.0, 102, 2.5) is None
    assert bake.cell_depth(0, 0.0, 102, 2.5) == 0.0
    grid = bake.HandGrid(20.255543, 99.808141, 20.491672, 100.039491, 1610, 1753)
    assert tuple(int(v) for v in grid.cell(99.88718, 20.44042)) == (380, 550)
    assert tuple(int(v) for v in grid.cell(99.88662, 20.44126)) == (374, 546)
    assert bake.road_class("primary_link") == "primary" and bake.road_class("steps") == "footway" and bake.road_class("bus_stop") is None
    assert bake.road_width_dm("residential", {}) == 50 and bake.road_width_dm("primary", {"lanes": "4"}) == 130
    assert bake.road_width_dm("primary", {"width": "7.5"}) == 75
    bake.check_extent("inside", [-1500.0, 900.0], [-800.0, 1800.0])
    with pytest.raises(AssertionError, match="outside its extent"):
        bake.check_extent("outside", [0.0, 900.1], [0.0, 0.0])
    practice = bake.practice_constants()
    homes, scenarios = parse_practice()
    assert practice.homes == homes and practice.scenarios == scenarios, "copy PRACTICE_HOMES and PRACTICE_SCENARIOS into the bake"


@pytest.mark.skipif(not os.environ.get("FLOODGUARD_EXTERNAL_DATA"), reason="FLOODGUARD_EXTERNAL_DATA is not set")
def test_verify_rebakes_the_committed_pack_byte_for_byte(capsys: pytest.CaptureFixture[str]) -> None:
    bake = load_bake()
    assert bake.main(["--verify"]) == 0
    assert "verify: PASS" in capsys.readouterr().out
