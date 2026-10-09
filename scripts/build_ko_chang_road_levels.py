"""The Ko Chang road sheet at the three closure levels, with a terrain look at the road that carries most of it.

The road sheet (``scripts/build_ko_chang_road_sheet.py``) reads closure rule v1 at the central level. This script
asks two things the sheet left open:

* Does the same road stay the key road at the strict and the permissive level?
* Does the open elevation model show that road standing above the ground beside it?

It reproduces the committed count of case SE1 for Ko Chang at each level before it writes anything. Everything is
modelled from a scenario: nothing was looked at on the ground, no FPPS and no A-E class is computed, and it is
not an official warning.

Example::

    python scripts/build_ko_chang_road_levels.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, flood_inputs  # noqa: E402

RESULT_NAME = "ko_chang_roads_se1_levels_v1.json"
KEY_WAY = "206803562"
STEPS = 3
RING_INNER_M, RING_OUTER_M = 60.0, 150.0
DEM_NOTE = ("Copernicus DEM GLO-30: a surface model with cells of about 30 m and a stated vertical accuracy of about "
            "4 m. It cannot show an embankment a few metres high and a road's width across.")


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sheet = load_script("build_ko_chang_road_sheet")


def greedy(network: Any, open_edges: np.ndarray, closed_by_way: dict[str, list[str]], count_routes: Any, steps: int) -> list[dict[str, Any]]:
    """At each step, the one road whose closed pieces, kept passable, give the most residents a route back."""

    current = open_edges.copy()
    reached = count_routes(current)
    candidates = dict(closed_by_way)
    result = []
    for _ in range(steps):
        best: tuple[float, str] | None = None
        for way, edge_ids in candidates.items():
            trial = current.copy()
            trial[[network.position[edge_id] for edge_id in edge_ids]] = True
            gain = count_routes(trial) - reached
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, way)
        if best is None:
            break
        gain, way = best
        current[[network.position[edge_id] for edge_id in candidates.pop(way)]] = True
        reached += gain
        result.append({"osm_way_id": way, "residents_who_get_a_route_back_at_this_step": round(gain, 1),
                       "residents_with_a_route_after_this_step": round(reached, 1)})
    return result


def terrain_look(external: Path, points_lonlat: list[tuple[float, float]]) -> dict[str, Any]:
    """Elevation at points of a road against the ground in a ring around each (60 to 150 m)."""

    import rasterio
    from pyproj import Transformer

    dated = load_script("build_dated_radar_check")
    folder = external / dated.WORK
    height = None
    transform = None
    for index in range(len(dated.DEM_URLS)):
        with rasterio.open(folder / f"dem_{index}_10m.tif") as source:
            part = source.read(1)
            transform = source.transform
        part = np.where(part == -9999.0, np.nan, part)
        height = part if height is None else np.where(np.isfinite(height), height, part)
    to_utm = Transformer.from_crs(4326, dated.EPSG, always_xy=True).transform
    cell = dated.CELL_M
    inner, outer = int(round(RING_INNER_M / cell)), int(round(RING_OUTER_M / cell))
    offsets = [(dr, dc) for dr in range(-outer, outer + 1) for dc in range(-outer, outer + 1)
               if inner * inner <= dr * dr + dc * dc <= outer * outer]
    differences, road_heights = [], []
    for lon, lat in points_lonlat:
        x, y = to_utm(lon, lat)
        column, row = int((x - transform.c) / cell), int((transform.f - y) / cell)
        if not (outer <= row < height.shape[0] - outer and outer <= column < height.shape[1] - outer):
            continue
        ring = np.array([height[row + dr, column + dc] for dr, dc in offsets])
        if not np.isfinite(height[row, column]) or not np.isfinite(ring).any():
            continue
        road_heights.append(float(height[row, column]))
        differences.append(float(height[row, column] - np.nanmedian(ring)))
    if not differences:
        return {"points": 0, "note": "the elevation model does not cover the road"}
    values = np.array(differences)
    return {
        "points": int(values.size), "road_elevation_m": {"lowest": round(min(road_heights), 1), "highest": round(max(road_heights), 1)},
        "road_minus_ground_in_a_ring_of_60_to_150_m": {
            "median_m": round(float(np.median(values)), 2), "lowest_m": round(float(values.min()), 2),
            "highest_m": round(float(values.max()), 2),
            "points_more_than_2_m_above": int((values > 2.0).sum())},
        "elevation_model": DEM_NOTE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    arguments = parser.parse_args()
    external = Path(arguments.external_root)
    work = external / sheet.WORK

    bad = sheet.load_script("build_access_diff")
    docs = sheet.DOCS
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    units, _summary = bad.read_units(external / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    assignment = access_diff.assign_cells(graph.population, units)

    extent_path = external / sheet.SEASON_EXTENT
    extent_sha = sheet.sha256_file(extent_path)
    if extent_sha not in (ROOT / sheet.E1_RECEIPT).read_text(encoding="utf-8"):
        raise sheet.BuildError("the season extent is not the layer the committed E1 receipt binds")
    cache = work / f"edge_intersections_{extent_sha[:16]}.json"
    if not cache.exists():
        raise sheet.BuildError("run scripts/build_ko_chang_road_sheet.py first: it caches the edge intersections")
    intersections = json.loads(cache.read_text(encoding="utf-8"))

    destination_nodes = {row["node_id"] for name in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY) for row in graph.destinations[name]}
    network = sheet.Network(graph.edges, destination_nodes)
    residents_at: dict[int, float] = defaultdict(float)
    for row in graph.population:
        if assignment[row["population_id"]]["unit_id"] != sheet.UNIT:
            continue
        snap = row.get("snap_distance_m")
        if row.get("node_id") in network.index and snap is not None and snap <= sheet.POPULATION_SNAP_LIMIT_M:
            residents_at[network.index[row["node_id"]]] += float(row["total_population"])
    nodes = np.array(sorted(residents_at), dtype="int64")
    weights = np.array([residents_at[node] for node in nodes])

    def count_routes(open_edges: np.ndarray) -> float:
        return float(weights[network.with_a_route(open_edges)[nodes]].sum())

    before = count_routes(np.ones(len(graph.edges), dtype=bool))
    committed = json.loads((ROOT / sheet.E5_TABLE).read_text(encoding="utf-8"))
    edge_by_id = {edge["edge_id"]: edge for edge in graph.edges}
    levels: dict[str, Any] = {}
    key_points: list[tuple[float, float]] = []
    for level in closure_rules.LEVELS:
        _changed, applied = access_diff.flooded_edges(level, graph.edges, intersections, flood_input_id="season_layer", arguments=closure)
        closed = set(applied["closed_edge_ids"])
        open_edges = np.array([edge_id not in closed for edge_id in network.edge_ids], dtype=bool)
        after = count_routes(open_edges)
        run = next(entry for entry in committed["runs"] if entry["closure_level"] == level)
        row = next(item for item in run["units"] if item["unit_id"] == sheet.UNIT)["road_criticality_inputs"]
        check = {"with_a_route_before": {"this_sheet": round(before, 3), "case_se1": round(row["residents_with_baseline_route"], 3)},
                 "losing_every_route": {"this_sheet": round(before - after, 3), "case_se1": round(row["residents_losing_all_routes"], 3)}}
        check["same"] = all(abs(item["this_sheet"] - item["case_se1"]) < 0.01 for item in check.values())
        if not check["same"]:
            raise sheet.BuildError(f"level {level} does not reproduce case SE1 for {sheet.UNIT}: {check}")
        closed_by_way: dict[str, list[str]] = defaultdict(list)
        for edge_id in closed:
            way = edge_by_id[edge_id].get("osm_way_id")
            if way is not None:
                closed_by_way[str(way)].append(edge_id)
        key_edges = closed_by_way.get(KEY_WAY, [])
        if key_edges:
            trial = open_edges.copy()
            trial[[network.position[edge_id] for edge_id in key_edges]] = True
            key_gain = count_routes(trial) - after
        else:
            key_gain = 0.0
        if level == sheet.LEVEL:
            key_points = [tuple(graph.node_coordinates[edge_by_id[edge_id][end]][:2]) for edge_id in key_edges for end in ("from_node", "to_node")]
        steps = greedy(network, open_edges, closed_by_way, count_routes, STEPS)
        levels[level] = {
            "reproduction_of_case_se1": check,
            "closed_road_pieces_in_the_graph": len(closed),
            "residents_with_a_route_before": round(before, 1),
            "residents_with_a_route_in_the_scenario": round(after, 1),
            "share_losing_every_route": round((before - after) / before, 4),
            "key_road": {"osm_way_id": KEY_WAY, "closed_pieces": len(key_edges),
                         "residents_who_get_a_route_back_if_it_alone_stays_passable": round(key_gain, 1),
                         "share_of_residents_with_a_route_before": round(key_gain / before, 4)},
            "roads_one_after_another": steps,
            "the_key_road_is_the_first_step": bool(steps and steps[0]["osm_way_id"] == KEY_WAY),
        }
        print(level, levels[level]["share_losing_every_route"], levels[level]["key_road"], [step["osm_way_id"] for step in steps], flush=True)

    result = {
        "schema": "floodguard.ko_chang_road_levels.v1",
        "generated_at_utc": sheet.datetime.now(sheet.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": sheet.SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Modelled closures on an agency season layer that was not checked in the field; an elevation model too coarse to show a raised road.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "The Ko Chang road sheet at the three levels of closure rule v1, and a terrain look at the road that carries most of the result.",
        "unit": {"unit_id": sheet.UNIT, "name_en": "Ko Chang"},
        "closure_levels": levels,
        "terrain_look_at_the_key_road": terrain_look(external, key_points),
        "inputs": {"road_sheet": {"path": f"{sheet.OUTPUT_DIR}/{sheet.RESULT_NAME}",
                                  "sha256": sheet.sha256_file(ROOT / sheet.OUTPUT_DIR / sheet.RESULT_NAME)},
                   "case_se1_table": {"path": sheet.E5_TABLE, "sha256": sheet.sha256_file(ROOT / sheet.E5_TABLE)},
                   "season_extent_sha256": extent_sha},
        "assumptions": sheet.ASSUMPTIONS,
        "limits": [*sheet.LIMITS, "The terrain look cannot confirm or rule out a raised road; it can only show a large difference, and it shows what it shows."],
    }
    sheet.write_json(ROOT / sheet.OUTPUT_DIR / RESULT_NAME, result)
    print(json.dumps(result["terrain_look_at_the_key_road"], indent=1))


if __name__ == "__main__":
    main()
