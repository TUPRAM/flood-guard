"""Which road gives the most cut-off residents a route back, across the eight tambons of case SE1. Report-only.

The Ko Chang road sheet (``scripts/build_ko_chang_road_sheet.py``) asked this for one tambon. This script asks it for
the district: in the scenario, at the central closure level, which closed roads, kept passable along their whole
closed length, would give the most residents a road route back, one road on its own and one road after another.

It is a what-if on the model graph. A road here is an OpenStreetMap way; "kept passable" says nothing about how, or
whether it can be done. Closures are modelled from the season layer, not observed, and nothing was checked on the
ground. Before it writes, the script checks that its cut-off residents per tambon are those of the committed access
table, and that it gives the first road of the Ko Chang sheet the residents the sheet gives it. Not an official
warning.

Example::

    python scripts/build_road_reconnection.py --external-root <external data root>
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, flood_inputs  # noqa: E402

OUTPUT = "outputs/road_reconnection/se1_mae_sai_v1.json"
KO_CHANG_SHEET = "outputs/ko_chang_road_check/ko_chang_roads_se1_v1.json"
LEVEL = "central"
STEPS = 10
LISTED_ALONE = 10
POPULATION_SNAP_LIMIT_M = 250.0


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


class BuildError(RuntimeError):
    """The what-if cannot be made, or it does not reproduce the runs it stands on."""


def parts_of(network: Any, open_edges: np.ndarray) -> np.ndarray:
    """The label of the connected part of every node, using the open edges only."""

    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    count = len(network.index)
    matrix = coo_matrix((np.ones(int(open_edges.sum()), dtype="int8"), (network.start[open_edges], network.end[open_edges])), shape=(count, count))
    _number, labels = connected_components(matrix, directed=False)
    return labels


def gain_of(pairs: list[tuple[int, int]], served: np.ndarray, waiting: np.ndarray) -> np.ndarray:
    """Residents by tambon who get a route back when the parts joined by ``pairs`` are joined.

    ``pairs`` are the labels of the two parts at the ends of each closed piece of one road; ``served`` says which
    parts hold a destination; ``waiting`` holds, per part and tambon, the cut-off residents. Parts joined into a
    group that holds a destination get a route.
    """

    parent: dict[int, int] = {}

    def find(item: int) -> int:
        while parent.setdefault(item, item) != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for first, second in pairs:
        a, b = find(first), find(second)
        if a != b:
            parent[a] = b
    groups: dict[int, list[int]] = {}
    for item in list(parent):
        groups.setdefault(find(item), []).append(item)
    gained = np.zeros(waiting.shape[1])
    for members in groups.values():
        if any(served[member] for member in members):
            for member in members:
                if not served[member]:
                    gained += waiting[member]
    return gained


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    arguments = parser.parse_args()
    external = Path(arguments.external_root)

    bad = load_script("build_access_diff")
    docs = sheet.DOCS
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    units, _summary = bad.read_units(external / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    unit_ids = [unit_id for unit_id, _geometry in units]
    assignment = access_diff.assign_cells(graph.population, units)

    extent_sha = sheet.sha256_file(external / sheet.SEASON_EXTENT)
    if extent_sha not in (ROOT / sheet.E1_RECEIPT).read_text(encoding="utf-8"):
        raise BuildError("the season extent is not the layer the committed E1 receipt binds")
    cache = external / sheet.WORK / f"edge_intersections_{extent_sha[:16]}.json"
    if not cache.exists():
        raise BuildError("run scripts/build_ko_chang_road_sheet.py first: it caches the edge intersections")
    intersections = json.loads(cache.read_text(encoding="utf-8"))
    _changed, applied = access_diff.flooded_edges(LEVEL, graph.edges, intersections, flood_input_id="season_layer", arguments=closure)
    closed_ids = set(applied["closed_edge_ids"])

    destination_nodes = {row["node_id"] for name in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY) for row in graph.destinations[name]}
    network = sheet.Network(graph.edges, destination_nodes)
    closed = np.array([edge_id in closed_ids for edge_id in network.edge_ids])
    length = np.array([float(edge["length_m"]) for edge in graph.edges])
    way = np.array([str(edge.get("osm_way_id")) if edge.get("osm_way_id") is not None else "" for edge in graph.edges])

    # --- the demand cells: node, tambon, residents, and whether they had a route before the flood ---------------------
    node, tambon, people = [], [], []
    for row in graph.population:
        unit_id = assignment[row["population_id"]]["unit_id"]
        snap = row.get("snap_distance_m")
        if unit_id is None or row.get("node_id") not in network.index or snap is None or snap > POPULATION_SNAP_LIMIT_M:
            continue
        node.append(network.index[row["node_id"]])
        tambon.append(unit_ids.index(unit_id))
        people.append(float(row["total_population"]))
    node, tambon, people = np.array(node), np.array(tambon), np.array(people)
    had_route = network.with_a_route(np.ones(len(graph.edges), dtype=bool))[node]

    def cut_off(open_edges: np.ndarray) -> np.ndarray:
        waiting = had_route & ~network.with_a_route(open_edges)[node]
        return np.bincount(tambon[waiting], weights=people[waiting], minlength=len(unit_ids))

    start_open = ~closed
    cut_at_the_start = cut_off(start_open)
    table = json.loads((ROOT / sheet.E5_TABLE).read_text(encoding="utf-8"))
    run = next(entry for entry in table["runs"] if entry["closure_level"] == LEVEL and entry.get("flood_level") == "as_provided")
    for number, unit_id in enumerate(unit_ids):
        wanted = next(item for item in run["units"] if item["unit_id"] == unit_id)["road_criticality_inputs"]["residents_losing_all_routes"]
        if abs(cut_at_the_start[number] - wanted) > 0.01:
            raise BuildError(f"{unit_id}: {cut_at_the_start[number]} cut-off residents, the access table holds {wanted}")

    pieces_of: dict[str, list[int]] = {}
    for piece in np.flatnonzero(closed).tolist():
        if way[piece]:
            pieces_of.setdefault(str(way[piece]), []).append(piece)
    candidates = sorted(pieces_of)

    def state(open_edges: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        labels = parts_of(network, open_edges)
        served = np.zeros(labels.max() + 1, dtype=bool)
        served[labels[network.destinations]] = True
        waiting_cells = had_route & ~served[labels[node]]
        waiting = np.zeros((labels.max() + 1, len(unit_ids)))
        np.add.at(waiting, (labels[node][waiting_cells], tambon[waiting_cells]), people[waiting_cells])
        return labels, served, waiting

    def gains(open_edges: np.ndarray) -> dict[str, np.ndarray]:
        labels, served, waiting = state(open_edges)
        result = {}
        for name in candidates:
            pieces = [piece for piece in pieces_of[name] if not open_edges[piece]]
            if pieces:
                found = gain_of([(int(labels[network.start[piece]]), int(labels[network.end[piece]])) for piece in pieces], served, waiting)
                if found.sum() > 0:
                    result[name] = found
        return result

    clock = time.perf_counter()
    alone = gains(start_open)
    # The fast count must be the count of a full relabelling, for the road that helps most.
    best_alone = max(alone, key=lambda name: (alone[name].sum(), name))
    full = cut_at_the_start - cut_off(start_open | (closed & (way == best_alone)))
    if np.abs(full - alone[best_alone]).max() > 1e-6:
        raise BuildError("the count by joined parts is not the count of a full relabelling of the graph")
    ko_chang = json.loads((ROOT / KO_CHANG_SHEET).read_text(encoding="utf-8"))
    first = ko_chang["what_if_one_road_stays_passable"]["best"][0]
    mine = alone.get(str(first["osm_way_id"]))
    position = unit_ids.index(ko_chang["unit"]["unit_id"])
    if mine is None or abs(mine[position] - first["residents_who_get_a_route_back"]) > 0.06:
        raise BuildError("the first road of the Ko Chang sheet does not get the residents the sheet gives it")

    names = sheet.way_names(external / sheet.OSM_PBF, tuple(context["routing_bounds"]) if "routing_bounds" in context else
                            (min(c[0] for c in graph.node_coordinates.values()), min(c[1] for c in graph.node_coordinates.values()),
                             max(c[0] for c in graph.node_coordinates.values()), max(c[1] for c in graph.node_coordinates.values())))
    published = json.loads((ROOT / "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json").read_text(encoding="utf-8"))
    unit_names = {row["unit_id"]: row["unit_name_en"] for row in published["rows"]}

    def road(name: str, open_edges: np.ndarray) -> dict[str, Any]:
        pieces = np.flatnonzero(closed & ~open_edges & (way == name))
        found = names.get(name, {})
        coordinates = [graph.node_coordinates[graph.edges[piece][end]] for piece in pieces for end in ("from_node", "to_node")]
        return {"osm_way_id": name, "name": found.get("name", ""), "name_en": found.get("name_en", ""), "ref": found.get("ref", ""),
                "highway": found.get("highway", ""), "look_at": f"https://www.openstreetmap.org/way/{name}",
                "closed_pieces": int(pieces.size), "closed_length_m": round(float(length[pieces].sum()), 1),
                "centre_of_the_closed_pieces_lonlat": [round(float(np.mean([c[0] for c in coordinates])), 5),
                                                       round(float(np.mean([c[1] for c in coordinates])), 5)]}

    def by_tambon(values: np.ndarray) -> dict[str, float]:
        return {unit_ids[number]: round(float(value), 1) for number, value in enumerate(values) if value > 0.05}

    listed_alone = [{**road(name, start_open), "residents_who_get_a_route_back": round(float(alone[name].sum()), 1),
                     "by_tambon": by_tambon(alone[name])}
                    for name in sorted(alone, key=lambda item: (-alone[item].sum(), item))[:LISTED_ALONE]]

    open_edges = start_open.copy()
    steps = []
    remaining = cut_at_the_start.copy()
    for step in range(1, STEPS + 1):
        found = gains(open_edges)
        if not found:
            break
        name = max(found, key=lambda item: (found[item].sum(), item))
        entry = road(name, open_edges)
        open_edges = open_edges | (closed & (way == name))
        now = cut_off(open_edges)
        if np.abs((remaining - now) - found[name]).max() > 1e-6:
            raise BuildError(f"step {step}: the count by joined parts is not the count of a full relabelling")
        remaining = now
        steps.append({"step": step, **entry, "residents_who_get_a_route_back_at_this_step": round(float(found[name].sum()), 1),
                      "by_tambon_at_this_step": by_tambon(found[name]),
                      "residents_still_cut_off_after_this_step": round(float(remaining.sum()), 1),
                      "share_of_the_cut_off_residents_with_a_route_back": round(float(1 - remaining.sum() / cut_at_the_start.sum()), 4)})
        print(step, name, entry["name_en"] or entry["name"], entry["highway"], round(float(found[name].sum()), 1), by_tambon(found[name]), flush=True)
    print(f"what-if: {time.perf_counter() - clock:.0f} s; candidate roads: {len(candidates)}; roads that help on their own: {len(alone)}", flush=True)

    result = {
        "schema": "floodguard.road_reconnection.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": sheet.SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "A what-if on a modelled road graph (OpenStreetMap) with closures assumed from an agency season layer that was not checked in the field, and modelled residents.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "For case SE1 at the central closure level: the closed roads that, kept passable along their whole closed length, give the most cut-off residents of the eight tambons a road route back. Report-only; a what-if on the model graph.",
        "label": "Modelled, not observed. A scenario of the 2024 season layer, not a flood of any day. A road named here was not looked at on the ground.",
        "closure_level": LEVEL,
        "cut_off_in_the_scenario": {"residents": round(float(cut_at_the_start.sum()), 1),
                                    "by_tambon": {unit_id: {"unit_name_en": unit_names[unit_id], "residents": round(float(cut_at_the_start[number]), 1)}
                                                  for number, unit_id in enumerate(unit_ids)}},
        "roads": {"osm_ways_with_a_closed_piece": len(candidates), "that_give_a_resident_a_route_back_on_their_own": len(alone)},
        "one_road_on_its_own": {"what": "Each closed road kept passable on its own: the residents who get a route back. The ten that help most.", "best": listed_alone},
        "one_road_after_another": {
            "what": "At each step the one road is added that gives the most residents a route back, given the roads added before.",
            "steps": steps,
            "still_cut_off_after_the_last_step": {"residents": round(float(remaining.sum()), 1), "by_tambon": by_tambon(remaining)}},
        "checks": {"cut_off_residents_per_tambon_are_those_of_the_access_table": True,
                   "the_count_by_joined_parts_is_the_count_of_a_full_relabelling_at_every_step": True,
                   "the_first_road_of_the_ko_chang_sheet_gets_the_residents_the_sheet_gives_it": {
                       "osm_way_id": str(first["osm_way_id"]), "residents_of_ko_chang": first["residents_who_get_a_route_back"]}},
        "made_from": {"access_table": {"path": sheet.E5_TABLE, "sha256": hashlib.sha256((ROOT / sheet.E5_TABLE).read_bytes()).hexdigest()},
                      "ko_chang_sheet": {"path": KO_CHANG_SHEET, "sha256": hashlib.sha256((ROOT / KO_CHANG_SHEET).read_bytes()).hexdigest()},
                      "season_extent_sha256": extent_sha},
        "credits": ["Roads © OpenStreetMap contributors (ODbL 1.0).",
                    "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard; the figures derived from it are shared under CC BY-SA 4.0.",
                    "Residents: WorldPop 2020 (CC BY 4.0)."],
        "assumptions": ["A closure is a modelled assumption of closure rule v1 at the central level, not an observed closure.",
                        "A road is an OpenStreetMap way. Kept passable means every closed piece of it is taken as open; nothing is said about how.",
                        "A resident has a route when the cell is joined to a part of the graph that holds a hospital or a main-road entry.",
                        "The order of the steps is greedy: the best single road at each step, not the best set of roads."],
        "limits": ["A what-if on a model: no road was surveyed, and a road that helps here may be a track, a dyke road or a bridge approach that cannot be kept open.",
                   "One closure level and the flood layer as provided. The Ko Chang sheet shows how its first road fares at the other levels.",
                   "A road outside a tambon can be the one that reconnects it; the centre of its closed pieces says where to look.",
                   "Planning guidance only. Nothing here is a route to take in a flood."],
    }
    (ROOT / OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / OUTPUT).write_bytes((json.dumps(result, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps(result["cut_off_in_the_scenario"], ensure_ascii=False))


if __name__ == "__main__":
    main()
