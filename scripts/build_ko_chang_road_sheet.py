"""Which roads cut Ko Chang off in the season-layer scenario (a desk sheet for plan task V1).

Case SE1 gives Ko Chang class B because, in the scenario, every resident with a road route loses every route to
a hospital or a main road. This script says which closed road pieces do that, and which roads would have to stay
passable for residents to get a route back. It reads the context of record and the season layer as plan tasks E4
and E1 wrote them, applies closure rule v1 at the central level, and reproduces the committed count of case SE1
before it writes anything.

Everything here is modelled from a scenario: a flood intersection does not prove a closure, and nothing was looked
at on the ground. It computes no component, no FPPS and no A-E class, and it is not an official warning.

Example::

    python scripts/build_ko_chang_road_sheet.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, flood_inputs  # noqa: E402

DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = "outputs/ko_chang_road_check"
RESULT_NAME = "ko_chang_roads_se1_v1.json"
MAP_NAME = "ko_chang_roads_se1_v1_map.png"
PLANNING = Path("proposal_execution") / "planning_v1"
SEASON_EXTENT = PLANNING / "se1_mae_sai" / "e1_flood_input" / "flood_extent__as_provided__routing_context.geojson"
OSM_PBF = Path("open_context") / "osm_geofabrik" / "thailand-latest.osm.pbf"
WORK = PLANNING / "se1_mae_sai" / "ko_chang_road_sheet"
E1_RECEIPT = "outputs/planning_v1/e1_flood_inputs_mae_sai.json"
E5_TABLE = "outputs/planning_v1/e5_access_diff_se1_mae_sai_public_services.json"
UNIT = "TH570903"
LEVEL = "central"
POPULATION_SNAP_LIMIT_M = 250.0
REOPEN_STEPS = 8
SOURCE_TIMESTAMP = "2024-08-01/2024-10-12 (season layer of product 4009)"

ASSUMPTIONS = [
    "The flood input is the accumulated 2024 season layer of UNOSAT/GISTDA product 4009, treated as flooded at once: a scenario, not a day.",
    "A road closure is modelled with closure rule v1 at the central level: a flood intersection does not prove a closure.",
    "A road is an OpenStreetMap way. Its name and tags are as mapped; a bridge or a raised road that is not tagged is not known here.",
    "Residents are modelled counts (WorldPop 2020) at the road node their cell snaps to, within 250 m.",
]
LIMITS = [
    "Nothing was looked at on the ground or on an image. This sheet says where to look.",
    "The season layer has no water depth, so a road counts as closed whatever the depth was.",
    "'Stays passable' is a what-if on the model graph. It is not a statement that a road was or would be passable.",
    "No component, no planning score and no action class is computed here.",
]


class BuildError(RuntimeError):
    """The sheet cannot be made on these inputs."""


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise BuildError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))  # LF bytes


class Network:
    """The road graph as arrays, to label connected parts quickly with some edges taken out."""

    def __init__(self, edges: list[dict[str, Any]], destination_nodes: set[str]) -> None:
        nodes = sorted({edge["from_node"] for edge in edges} | {edge["to_node"] for edge in edges})
        self.index = {node: position for position, node in enumerate(nodes)}
        self.start = np.array([self.index[edge["from_node"]] for edge in edges], dtype="int64")
        self.end = np.array([self.index[edge["to_node"]] for edge in edges], dtype="int64")
        self.edge_ids = [edge["edge_id"] for edge in edges]
        self.position = {edge_id: position for position, edge_id in enumerate(self.edge_ids)}
        self.destinations = np.zeros(len(nodes), dtype=bool)
        for node in destination_nodes:
            if node in self.index:
                self.destinations[self.index[node]] = True

    def with_a_route(self, open_edges: np.ndarray) -> np.ndarray:
        """For every node: is it in a connected part that holds a destination, using the open edges only?"""

        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components

        count = len(self.index)
        matrix = coo_matrix((np.ones(int(open_edges.sum()), dtype="int8"), (self.start[open_edges], self.end[open_edges])), shape=(count, count))
        _parts, labels = connected_components(matrix, directed=False)
        served = np.zeros(labels.max() + 1, dtype=bool)
        served[labels[self.destinations]] = True
        return served[labels]


def way_names(pbf: Path, bounds: tuple[float, float, float, float]) -> dict[str, dict[str, str]]:
    """Name, reference and highway tag of the OpenStreetMap ways inside the bounds."""

    import pyogrio

    frame = pyogrio.read_dataframe(pbf, layer="lines", bbox=bounds, columns=["osm_id", "name", "highway", "other_tags"], read_geometry=False)
    result: dict[str, dict[str, str]] = {}
    for osm_id, name, highway, tags in zip(frame["osm_id"], frame["name"], frame["highway"], frame["other_tags"]):
        tags = tags if isinstance(tags, str) else ""
        reference = tags.split('"ref"=>"')[1].split('"')[0] if '"ref"=>"' in tags else ""
        english = tags.split('"name:en"=>"')[1].split('"')[0] if '"name:en"=>"' in tags else ""
        result[str(osm_id)] = {"name": name if isinstance(name, str) else "", "name_en": english, "ref": reference,
                               "highway": highway if isinstance(highway, str) else ""}
    return result


def draw_map(path: Path, *, unit: Any, extent: Any, edges: list[dict[str, Any]], coordinates: dict[str, Any], closed: set[str],
             frontier: set[str], reopened: list[dict[str, Any]], cells: list[tuple[float, float, float]]) -> None:
    """One picture of Ko Chang: the season layer, open and closed roads, the cut pieces and the roads of the what-if."""

    from PIL import Image, ImageDraw
    import shapely

    west, south, east, north = unit.buffer(0.012).bounds
    width = 1500
    scale = width / ((east - west) * math.cos(math.radians((south + north) / 2)))
    height = int((north - south) * scale)

    def point(lon: float, lat: float) -> tuple[float, float]:
        return ((lon - west) * math.cos(math.radians((south + north) / 2)) * scale, (north - lat) * scale)

    image = Image.new("RGB", (width, height), (250, 250, 248))
    draw = ImageDraw.Draw(image, "RGBA")
    window = shapely.box(west, south, east, north)
    water = shapely.intersection(extent, window)
    for polygon in getattr(water, "geoms", [water]):
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        draw.polygon([point(x, y) for x, y in polygon.exterior.coords], fill=(120, 175, 225, 150))
        for ring in polygon.interiors:
            draw.polygon([point(x, y) for x, y in ring.coords], fill=(250, 250, 248, 255))
    for x, y, residents in cells:
        if residents >= 3.0 and west <= x <= east and south <= y <= north:
            px, py = point(x, y)
            radius = min(4.0, 0.8 + math.sqrt(residents) / 3.0)
            draw.ellipse([px - radius, py - radius, px + radius, py + radius], fill=(90, 60, 20, 150))
    order = {False: 0, True: 1}
    numbered = {way: step for step, row in enumerate(reopened, start=1) for way in [row["osm_way_id"]]}
    for edge in sorted(edges, key=lambda item: order[item["edge_id"] in closed]):
        a, b = coordinates[edge["from_node"]], coordinates[edge["to_node"]]
        if not (west <= a[0] <= east and south <= a[1] <= north) and not (west <= b[0] <= east and south <= b[1] <= north):
            continue
        main = edge.get("road_class") in ("trunk", "primary", "secondary")
        if str(edge.get("osm_way_id")) in numbered and edge["edge_id"] in closed:
            colour, line = (20, 120, 60, 255), 5
        elif edge["edge_id"] in frontier:
            colour, line = (200, 30, 30, 255), 4
        elif edge["edge_id"] in closed:
            colour, line = (225, 120, 110, 220), 2
        else:
            colour, line = ((70, 70, 70, 255), 2) if main else ((150, 150, 150, 255), 1)
        draw.line([point(*a[:2]), point(*b[:2])], fill=colour, width=line)
    for ring in [unit.exterior] if unit.geom_type == "Polygon" else [part.exterior for part in unit.geoms]:
        draw.line([point(x, y) for x, y in ring.coords], fill=(0, 0, 0, 255), width=3)
    for row in reopened:
        lon, lat = row["centre_of_the_closed_pieces_lonlat"]
        if west <= lon <= east and south <= lat <= north:
            px, py = point(lon, lat)
            draw.ellipse([px - 11, py - 11, px + 11, py + 11], fill=(20, 120, 60, 255), outline=(255, 255, 255, 255))
            draw.text((px - 3, py - 6), str(row["step"]), fill=(255, 255, 255, 255))
    legend = [((120, 175, 225), "2024 season layer (scenario)"), ((225, 120, 110), "road closed in the model"),
              ((200, 30, 30), "closed piece at the edge of a cut-off part"), ((20, 120, 60), "road of the what-if (kept passable)"),
              ((150, 150, 150), "road open in the model"), ((90, 60, 20), "cells with 3 or more residents (modelled)")]
    draw.rectangle([10, 10, 420, 24 + 20 * len(legend)], fill=(255, 255, 255, 235), outline=(0, 0, 0, 255))
    for row, (colour, text) in enumerate(legend):
        draw.rectangle([18, 20 + 20 * row, 38, 32 + 20 * row], fill=(*colour, 255))
        draw.text((46, 19 + 20 * row), text, fill=(0, 0, 0, 255))
    draw.text((10, height - 18), "Ko Chang, Mae Sai district. Modelled from a scenario; not looked at on the ground. Not an official warning.", fill=(0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    arguments = parser.parse_args()
    external = Path(arguments.external_root)
    work = external / WORK
    work.mkdir(parents=True, exist_ok=True)

    import shapely

    bad = load_script("build_access_diff")
    rules = flood_inputs.load_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")
    v1b = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    context, context_record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    boundaries = external / bad.BOUNDARY_RELATIVE_PATH
    units, _summary = bad.read_units(boundaries, rules.reporting_units)
    unit_geometry = dict(units)[UNIT]
    assignment = access_diff.assign_cells(graph.population, units)

    extent_path = external / SEASON_EXTENT
    extent_sha = sha256_file(extent_path)
    if extent_sha not in (ROOT / E1_RECEIPT).read_text(encoding="utf-8"):
        raise BuildError("the season extent is not the layer the committed E1 receipt binds")
    extent_metres, _properties = flood_inputs.decode_layer(extent_path.read_bytes())
    extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)

    cache = work / f"edge_intersections_{extent_sha[:16]}.json"
    if cache.exists():
        intersections = json.loads(cache.read_text(encoding="utf-8"))
    else:
        clock = time.perf_counter()
        intersections = closure_rules.edge_intersections(graph.edges, graph.node_coordinates, extent)
        cache.write_text(json.dumps(intersections), encoding="utf-8")
        print(f"edge intersections: {time.perf_counter() - clock:.0f} s", flush=True)
    _changed, applied = access_diff.flooded_edges(LEVEL, graph.edges, intersections, flood_input_id="season_layer", arguments=closure)
    closed = set(applied["closed_edge_ids"])
    inside = {row["edge_id"]: row for row in intersections}

    destination_nodes = {row["node_id"] for name in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY) for row in graph.destinations[name]}
    network = Network(graph.edges, destination_nodes)
    all_open = np.ones(len(graph.edges), dtype=bool)
    flooded_open = np.array([edge_id not in closed for edge_id in network.edge_ids], dtype=bool)

    residents_at: dict[int, float] = defaultdict(float)
    cell_points: list[tuple[float, float, float]] = []
    for row in graph.population:
        if assignment[row["population_id"]]["unit_id"] != UNIT:
            continue
        cell_points.append((float(row["longitude"]), float(row["latitude"]), float(row["total_population"])))
        snap = row.get("snap_distance_m")
        if row.get("node_id") in network.index and snap is not None and snap <= POPULATION_SNAP_LIMIT_M:
            residents_at[network.index[row["node_id"]]] += float(row["total_population"])
    nodes = np.array(sorted(residents_at), dtype="int64")
    weights = np.array([residents_at[node] for node in nodes])

    def residents_with_a_route(open_edges: np.ndarray) -> float:
        return float(weights[network.with_a_route(open_edges)[nodes]].sum())

    before = residents_with_a_route(all_open)
    after = residents_with_a_route(flooded_open)
    committed = json.loads((ROOT / E5_TABLE).read_text(encoding="utf-8"))
    run = next(entry for entry in committed["runs"] if entry["closure_level"] == LEVEL)
    row = next(item for item in run["units"] if item["unit_id"] == UNIT)["road_criticality_inputs"]
    check = {"with_a_route_before": {"this_sheet": round(before, 3), "case_se1": round(row["residents_with_baseline_route"], 3)},
             "losing_every_route": {"this_sheet": round(before - after, 3), "case_se1": round(row["residents_losing_all_routes"], 3)}}
    check["same"] = all(abs(item["this_sheet"] - item["case_se1"]) < 0.01 for item in check.values())
    if not check["same"]:
        raise BuildError(f"the sheet does not reproduce case SE1 for {UNIT}: {check}")

    # The closed pieces at the edge of the cut-off parts that hold Ko Chang residents.
    served = network.with_a_route(flooded_open)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    count = len(network.index)
    matrix = coo_matrix((np.ones(int(flooded_open.sum()), dtype="int8"), (network.start[flooded_open], network.end[flooded_open])), shape=(count, count))
    _parts, labels = connected_components(matrix, directed=False)
    part_residents: dict[int, float] = defaultdict(float)
    for node, weight in zip(nodes, weights):
        if not served[node]:
            part_residents[int(labels[node])] += float(weight)
    edge_by_id = {edge["edge_id"]: edge for edge in graph.edges}
    frontier: set[str] = set()
    for edge_id in closed:
        position = network.position[edge_id]
        if int(labels[network.start[position]]) in part_residents or int(labels[network.end[position]]) in part_residents:
            frontier.add(edge_id)
    parts = sorted(part_residents.values(), reverse=True)

    lon_west, lat_south, lon_east, lat_north = unit_geometry.buffer(0.03).bounds
    names = way_names(external / OSM_PBF, (lon_west, lat_south, lon_east, lat_north))

    def describe(way: str) -> dict[str, str]:
        found = names.get(way, {})
        return {"osm_way_id": way, "name": found.get("name", ""), "name_en": found.get("name_en", ""), "ref": found.get("ref", ""),
                "highway": found.get("highway", ""), "look_at": f"https://www.openstreetmap.org/way/{way}"}

    def where(edge_ids: list[str]) -> dict[str, Any]:
        points = [graph.node_coordinates[edge_by_id[edge_id][end]][:2] for edge_id in edge_ids for end in ("from_node", "to_node")]
        lon = sum(point[0] for point in points) / len(points)
        lat = sum(point[1] for point in points) / len(points)
        centre = shapely.Point(lon, lat)
        return {"centre_of_the_closed_pieces_lonlat": [round(lon, 5), round(lat, 5)],
                "centre_lies_in_unit": next((unit_id for unit_id, geometry in units if geometry.contains(centre)), None),
                "centre_lies_in_ko_chang": bool(unit_geometry.contains(centre))}

    closed_by_way: dict[str, list[str]] = defaultdict(list)
    for edge_id in closed:
        way = edge_by_id[edge_id].get("osm_way_id")
        if way is not None:
            closed_by_way[str(way)].append(edge_id)
    frontier_ways: dict[str, dict[str, Any]] = {}
    for edge_id in frontier:
        edge = edge_by_id[edge_id]
        way = str(edge.get("osm_way_id"))
        entry = frontier_ways.setdefault(way, {**describe(way), "road_class": edge.get("road_class"), "closed_pieces_at_the_edge": 0,
                                               "closed_pieces_of_the_way": len(closed_by_way.get(way, [])),
                                               "bridge_tagged_pieces": 0, "metres_of_the_edge_pieces_inside_the_layer": 0.0})
        entry["closed_pieces_at_the_edge"] += 1
        entry["bridge_tagged_pieces"] += int(edge.get("bridge") == "yes")
        entry["metres_of_the_edge_pieces_inside_the_layer"] += float(inside[edge_id]["intersection_length_m"])

    # What-if: which single road, kept passable along its whole closed length, gives the most residents a route back?
    single: list[dict[str, Any]] = []
    for way, edge_ids in closed_by_way.items():
        if way not in frontier_ways:
            continue
        trial = flooded_open.copy()
        trial[[network.position[edge_id] for edge_id in edge_ids]] = True
        gain = residents_with_a_route(trial) - after
        if gain > 0:
            single.append({**describe(way), **where(edge_ids), "road_class": frontier_ways[way]["road_class"],
                           "closed_pieces": len(edge_ids),
                           "metres_inside_the_layer": round(sum(float(inside[e]["intersection_length_m"]) for e in edge_ids), 1),
                           "residents_who_get_a_route_back": round(gain, 1)})
    single.sort(key=lambda item: -item["residents_who_get_a_route_back"])

    # What-if, step by step: keep adding the one road that gives the most residents a route back.
    current = flooded_open.copy()
    reached = after
    steps: list[dict[str, Any]] = []
    candidates = dict(closed_by_way)
    for _step in range(REOPEN_STEPS):
        best: tuple[float, str] | None = None
        served_now = network.with_a_route(current)
        for way, edge_ids in candidates.items():
            positions = [network.position[edge_id] for edge_id in edge_ids]
            # Only a road that touches both a served and an unserved part can change anything on its own.
            touches = np.concatenate([served_now[network.start[positions]], served_now[network.end[positions]]])
            if touches.all() or not touches.any():
                continue
            trial = current.copy()
            trial[positions] = True
            gain = residents_with_a_route(trial) - reached
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, way)
        if best is None:
            break
        gain, way = best
        current[[network.position[edge_id] for edge_id in candidates.pop(way)]] = True
        reached += gain
        edge = edge_by_id[closed_by_way[way][0]]
        steps.append({"step": len(steps) + 1, **describe(way), **where(closed_by_way[way]), "road_class": edge.get("road_class"),
                      "closed_pieces": len(closed_by_way[way]),
                      "metres_inside_the_layer": round(sum(float(inside[e]["intersection_length_m"]) for e in closed_by_way[way]), 1),
                      "bridge_tagged_pieces": sum(int(edge_by_id[e].get("bridge") == "yes") for e in closed_by_way[way]),
                      "residents_who_get_a_route_back_at_this_step": round(gain, 1),
                      "residents_with_a_route_after_this_step": round(reached, 1),
                      "share_of_residents_with_a_route_before": round(reached / before, 4)})

    map_path = ROOT / OUTPUT_DIR / MAP_NAME
    draw_map(map_path, unit=unit_geometry, extent=extent, edges=graph.edges, coordinates=graph.node_coordinates, closed=closed,
             frontier=frontier, reopened=steps, cells=cell_points)
    unit_edges = [edge for edge in graph.edges if edge.get("osm_way_id") is not None and unit_geometry.contains(
        shapely.Point(graph.node_coordinates[edge["from_node"]][:2]))]
    result = {
        "schema": "floodguard.ko_chang_road_sheet.v1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": SOURCE_TIMESTAMP, "confidence_class": "low",
        "confidence_basis": "Modelled closures on an unvalidated agency season layer; nothing was looked at on the ground or on an image.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "A desk sheet for plan task V1: the closed road pieces that cut Ko Chang off in the season-layer scenario of "
                        "case SE1, and a what-if on which roads would have to stay passable.",
        "unit": {"unit_id": UNIT, "name_en": "Ko Chang", "name_th": "เกาะช้าง"},
        "closure_level": LEVEL, "closure_basis": "modelled_from_the_season_layer_of_product_4009",
        "reproduction_of_case_se1": check,
        "roads_in_the_tambon": {
            "road_pieces": len(unit_edges), "closed_road_pieces": sum(edge["edge_id"] in closed for edge in unit_edges),
            "bridge_tagged_pieces": sum(edge.get("bridge") == "yes" for edge in unit_edges),
            "closed_bridge_tagged_pieces": sum(edge.get("bridge") == "yes" and edge["edge_id"] in closed for edge in unit_edges),
        },
        "cut_off_parts": {
            "what": "Connected parts of the road graph, with the closed pieces taken out, that hold Ko Chang residents and no hospital or main-road entry.",
            "parts": len(parts), "residents_in_the_largest": [round(value, 1) for value in parts[:6]],
            "closed_pieces_at_their_edge": len(frontier), "roads_those_pieces_belong_to": len(frontier_ways),
        },
        "roads_at_the_edge_of_the_cut_off_parts": sorted(
            ({**row, "metres_of_the_edge_pieces_inside_the_layer": round(row["metres_of_the_edge_pieces_inside_the_layer"], 1)}
             for row in frontier_ways.values()),
            key=lambda item: (-item["closed_pieces_at_the_edge"], item["osm_way_id"]))[:40],
        "what_if_one_road_stays_passable": {
            "what": "Each road of the list above on its own, kept passable along its whole closed length: residents of Ko Chang who get a route back.",
            "roads_that_help_on_their_own": len(single), "best": single[:10],
        },
        "what_if_roads_stay_passable_one_after_another": {
            "what": "At each step the one road is added that gives the most residents a route back. A what-if on the model graph.",
            "residents_with_a_route_before_the_flood": round(before, 1), "residents_with_a_route_in_the_scenario": round(after, 1),
            "steps": steps,
        },
        "map": f"{OUTPUT_DIR}/{MAP_NAME}",
        "inputs": {
            "context_of_record": {key: context_record[key] for key in ("path", "canonical_sha256", "receipt")},
            "season_extent": {"file": extent_path.name, "sha256": extent_sha, "bound_by": E1_RECEIPT},
            "case_se1_table": {"path": E5_TABLE, "sha256": sha256_file(ROOT / E5_TABLE)},
            "openstreetmap_names": {"file": OSM_PBF.name, "sha256": sha256_file(external / OSM_PBF)},
            "protocol_sha256": flood_inputs.protocol_hashes(rules),
        },
        "credits": [
            "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard: repaired, projected, clipped and "
            "set against roads and residents; figures derived from it are shared under CC BY-SA 4.0.",
            "Roads and road names © OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0).",
        ],
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    result["map_sha256"] = sha256_file(map_path)
    write_json(ROOT / OUTPUT_DIR / RESULT_NAME, result)
    print(json.dumps({key: result[key] for key in ("reproduction_of_case_se1", "roads_in_the_tambon", "cut_off_parts")}, indent=1))
    print(json.dumps(result["what_if_one_road_stays_passable"]["best"][:6], ensure_ascii=False, indent=1))
    print(json.dumps(steps, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except BuildError as error:
        raise SystemExit(f"refused: {error}") from error
