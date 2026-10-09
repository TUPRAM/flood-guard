"""Shelter access on foot and listed shelter places against the residents in reach, for case SE1. Report-only.

The proposal names "shelter capacity versus reachable demand"; protocol v1b fixes how (``facility_sets.two_step_access``):
binary 2SFCA at 15, 30 and 60 minutes on the located DDPM rows, participation of 5, 10 and 25 percent, labelled
"listed planned capacity; scenario", not an input of the planning score, at the pitch level.

What this script does:

* reads the vehicle context of record and the walking context beside it, through the checks of the task E5 builder;
* computes the walking minutes from every demand cell to every located shelter, at baseline and under the three
  levels of closure rule v1 on the flood layer as provided;
* checks, before it writes, that its minutes to the nearest shelter are those of the engine
  (``floodguard.access_diff.cell_minutes``) and that its counts per tambon are those of the task E5 shelter table;
* computes shelter access, the nearest-shelter count of each shelter and the 2SFCA readings.

**Where the figures go.** Shelter figures are pitch level (protocol v1b; decision D8b: participation sweeps and
listed capacity stay out of public files). The result and the pitch note are written outside Git, under the
external data root; a receipt with their SHA-256 and no figure of the service is written in Git.

The walking context is a candidate build (open point E5-OP5). The owner accepted it for report-only shelter figures
on 9 October 2026 (decision log R40); the registered task E5 receipt still calls it a candidate. A closure is a
modelled assumption, a capacity is a listed planning figure, and nothing here is an official warning.

Example::

    python scripts/build_shelter_capacity.py --external-data <external data root>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, critical_links, flood_inputs  # noqa: E402
from floodguard import shelter_capacity as capacity  # noqa: E402

CASE, FRAME = "SE1", "mae_sai"
RECEIPT = "outputs/shelter_capacity/se1_mae_sai_v1_receipt.json"
WORK_FOLDER = "shelter_capacity"
RESULT_NAME, NOTE_NAME = "shelter_capacity_se1_v1.json", "shelter_capacity_se1_v1_pitch_note.md"
SHELTER = access_diff.DDPM_LOCATED_SHELTER
LIMIT_MINUTES = float(max(capacity.THRESHOLDS_MINUTES))
BASELINE = "baseline"
DRY_ONLY = "central_with_shelters_inside_the_layer_left_out"


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


class BuildError(RuntimeError):
    """The run cannot be made, or one of its checks failed."""


def encode(value: Any) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")  # LF bytes


def minutes_matrix(edges: list[dict[str, Any]], nodes: list[str], sites: list[dict[str, Any]], population: list[dict[str, Any]],
                   identifiers: list[Any]) -> np.ndarray:
    """Walking minutes from every demand cell (row) to every shelter (column) on one set of edges; ``inf`` beyond the limit."""

    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    index = {node: number for number, node in enumerate(nodes)}
    lowest: dict[tuple[int, int], float] = {}
    for edge in edges:
        a, b = index[edge["from_node"]], index[edge["to_node"]]
        if a == b:
            continue
        key = (a, b) if a < b else (b, a)
        cost = critical_links._edge_minutes(edge)
        if cost < lowest.get(key, np.inf):
            lowest[key] = cost
    rows = np.fromiter((key[0] for key in lowest), dtype="int64", count=len(lowest))
    columns = np.fromiter((key[1] for key in lowest), dtype="int64", count=len(lowest))
    costs = np.fromiter(lowest.values(), dtype="float64", count=len(lowest))
    if (costs == 0).any():
        # an edge of no length (a grade join) must stay an edge: the sparse graph keeps an explicit, tiny cost for it
        costs = np.where(costs == 0, 1e-12, costs)
    graph = csr_matrix((costs, (rows, columns)), shape=(len(nodes), len(nodes)))

    by_id = {row["population_id"]: row for row in population}
    cell_node = np.full(len(identifiers), -1, dtype="int64")
    cell_connector = np.zeros(len(identifiers))
    for number, identifier in enumerate(identifiers):
        row = by_id[identifier]
        node, snap = row.get("node_id"), row.get("snap_distance_m")
        if node is None or snap is None or snap > access_diff.POPULATION_SNAP_LIMIT_M or node not in index:
            continue
        cell_node[number] = index[node]
        cell_connector[number] = snap / 1000 / access_diff.CONNECTOR_SPEED_KMH * 60
    result = np.full((len(identifiers), len(sites)), np.inf)
    connected = cell_node >= 0
    for column, site in enumerate(sites):
        best = np.full(int(connected.sum()), np.inf)
        for connection in critical_links.facility_connectors(site):
            node, snap = connection.get("node_id"), connection.get("snap_distance_m")
            if node not in index or snap is None or snap > access_diff.FACILITY_SNAP_LIMIT_M:
                continue
            distances = dijkstra(graph, directed=False, indices=index[node], limit=LIMIT_MINUTES + 1.0)
            best = np.minimum(best, distances[cell_node[connected]] + snap / 1000 / critical_links.CONNECTOR_SPEED_KMH * 60)
        result[connected, column] = best + cell_connector[connected]
    return result


def check_against_the_engine(matrix: np.ndarray, engine: dict[Any, float | None], identifiers: list[Any], state: str) -> float:
    """The minutes to the nearest shelter must be those ``access_diff.cell_minutes`` gives, wherever either is within the limit."""

    mine = matrix.min(axis=1) if matrix.shape[1] else np.full(matrix.shape[0], np.inf)
    theirs = np.array([np.inf if engine.get(identifier) is None else float(engine[identifier]) for identifier in identifiers])
    near = (mine <= LIMIT_MINUTES) | (theirs <= LIMIT_MINUTES)
    worst = float(np.max(np.abs(mine[near] - theirs[near]))) if near.any() else 0.0
    if not np.isfinite(worst) or worst > 1e-6:
        raise BuildError(f"{state}: the minutes to the nearest shelter differ from the engine's by up to {worst}")
    return worst


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = arguments.external_data
    if (ROOT / RECEIPT).exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the receipt exists; a second run needs --replace and --reason")

    runner = load_script("build_uncertainty_ensemble")
    bad = runner.e5_builder
    frame_set = runner.FRAME_SETS[FRAME]
    found = runner.prepare(CASE, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH)
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    stated = v1b["facility_sets"]["two_step_access"]
    if list(stated["participation_percent"]) != list(capacity.PARTICIPATION_PERCENT) or stated["label"] != capacity.LABEL:
        raise BuildError("protocol v1b states another participation sweep or another label than this script applies")

    vehicle_context, vehicle_record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    walking_path = bad.find_walking_context(external, bad.FRAME_SETS[FRAME]["context_folder"], None)
    if walking_path is None:
        raise BuildError("no walking context is beside the vehicle context")
    walking, walking_record, _build_receipt = bad.load_walking_context(walking_path, vehicle_context, vehicle_record, external,
                                                                     bad.OUTPUT_DIR, ROOT)
    del vehicle_context
    graph = bad.mode_graph(access_diff.WALKING, walking)
    facility = {row["facility_id"]: row for row in walking["facilities"]}
    sites = sorted((site for site in graph.destinations[SHELTER]
                    if any(link.get("node_id") in graph.nodes and link.get("snap_distance_m") is not None
                           and link["snap_distance_m"] <= access_diff.FACILITY_SNAP_LIMIT_M
                           for link in critical_links.facility_connectors(site))), key=lambda row: row["facility_id"])
    places = np.array([float(facility[site["facility_id"]]["capacity"] or 0.0) for site in sites])
    del walking

    cells = [cell for cell in found.counted.cells if cell["unit_id"] is not None]
    identifiers = [cell["population_id"] for cell in cells]
    residents = np.array([float(cell["residents"]) for cell in cells])
    unit_of = np.array([str(cell["unit_id"]) for cell in cells])
    unit_ids = sorted(found.unit_ids)
    names = dict(found.names)
    nodes = sorted(graph.nodes)

    import shapely
    from pyproj import Transformer

    transformer = Transformer.from_crs(flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS, always_xy=True)
    layer = found.closure_extents[flood_inputs.AS_PROVIDED]
    points = [transformer.transform(float(facility[site["facility_id"]]["longitude"]), float(facility[site["facility_id"]]["latitude"]))
              for site in sites]
    shapely.prepare(layer)
    inside_layer = np.array(shapely.covers(layer, shapely.points([p[0] for p in points], [p[1] for p in points])), dtype=bool)

    clock = time.perf_counter()
    extent = flood_inputs.project(layer, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    intersections = closure_rules.edge_intersections(graph.edges, graph.node_coordinates, extent)
    print(f"edge intersections: {time.perf_counter() - clock:.0f} s; shelters: {len(sites)}; cells: {len(cells)}", flush=True)

    states: dict[str, np.ndarray] = {}
    worst: dict[str, float] = {}
    edges_of = {BASELINE: graph.edges}
    for level in closure_rules.LEVELS:
        edges_of[level], _applied = access_diff.flooded_edges(level, graph.edges, intersections,
                                                              flood_input_id=str(found.record["input_id"]), arguments=closure)
    for state, edges in edges_of.items():
        clock = time.perf_counter()
        states[state] = minutes_matrix(edges, nodes, sites, graph.population, identifiers)
        engine = access_diff.cell_minutes(graph.population, edges, sites, baseline_nodes=graph.nodes)
        worst[state] = check_against_the_engine(states[state], engine, identifiers, state)
        print(state, f"{time.perf_counter() - clock:.0f} s, largest difference from the engine {worst[state]:.2e} min", flush=True)
    dry = states["central"].copy()
    dry[:, inside_layer] = np.inf
    states[DRY_ONLY] = dry

    # --- the counts per tambon must be those of the task E5 shelter table -----------------------------------------
    table_path = runner.stage_folder(CASE, frame_set, external).parent / bad.STAGE_FOLDER / "access_diff_units__pitch_services.json"
    table = json.loads(table_path.read_text(encoding="utf-8"))
    compared = 0
    for run in table["runs"]:
        if run["flood_level"] != flood_inputs.AS_PROVIDED:
            continue
        rows = {str(row["unit_id"]): row for row in run["units"]}
        for unit_id in unit_ids:
            inside = unit_of == unit_id
            for threshold in capacity.THRESHOLDS_MINUTES:
                wanted = rows[unit_id]["access"][SHELTER]["thresholds_minutes"][str(threshold)]
                got = (float(residents[inside & (states[BASELINE].min(axis=1) <= threshold)].sum()),
                       float(residents[inside & (states[run["closure_level"]].min(axis=1) <= threshold)].sum()))
                if abs(got[0] - wanted["baseline_access_residents"]) > 0.01 or abs(got[1] - wanted["flooded_access_residents"]) > 0.01:
                    raise BuildError(f"{run['closure_level']}, {unit_id}, {threshold} min: {got} does not reproduce the task E5 shelter table")
                compared += 2
    if compared != 2 * len(unit_ids) * len(capacity.THRESHOLDS_MINUTES) * len(closure_rules.LEVELS):
        raise BuildError("the task E5 shelter table does not hold the three closure levels at the flood level as provided")

    def access(state: str, where: np.ndarray | None = None) -> dict[str, Any]:
        inside = np.ones(residents.shape, dtype=bool) if where is None else where
        nearest_minutes = states[state].min(axis=1)
        return {str(threshold): round(float(residents[inside & (nearest_minutes <= threshold)].sum()), 1)
                for threshold in capacity.THRESHOLDS_MINUTES}

    def two_step_block(state: str, supply: np.ndarray) -> dict[str, Any]:
        block: dict[str, Any] = {}
        for threshold in capacity.THRESHOLDS_MINUTES:
            run = capacity.two_step(states[state], residents, supply, threshold)
            block[str(threshold)] = {
                "whole_frame": capacity.reading(run["origin_accessibility"], run["origin_reaches_a_site"], residents),
                "by_tambon": {unit_id: capacity.reading(run["origin_accessibility"], run["origin_reaches_a_site"], residents,
                                                        where=unit_of == unit_id) for unit_id in unit_ids},
            }
        return block

    in_reach = (states[BASELINE][residents > 0] <= LIMIT_MINUTES).any(axis=0)
    supply_of = {state: places for state in (BASELINE, *closure_rules.LEVELS)}
    supply_of[DRY_ONLY] = np.where(inside_layer, 0.0, places)
    primary = capacity.PRIMARY_THRESHOLD_MINUTES
    shelters = []
    for column, site in enumerate(sites):
        row: dict[str, Any] = {"facility_id": site["facility_id"], "listed_places": places[column],
                               "point_inside_the_flood_layer_as_provided": bool(inside_layer[column])}
        for state in (BASELINE, "central", DRY_ONLY):
            nearest = capacity.nearest_site(states[state], primary)
            assigned = capacity.assigned_demand(nearest, residents, len(sites))[column]
            run = capacity.two_step(states[state], residents, supply_of[state], primary)
            row[state] = {
                "residents_whose_nearest_shelter_within_30_minutes_this_is": round(float(assigned), 1),
                "share_of_them_the_listed_places_hold": None if assigned == 0 else round(float(supply_of[state][column] / assigned), 4),
                "residents_within_30_minutes": round(float(run["site_catchment_demand"][column]), 1),
            }
        shelters.append(row)

    result = {
        "schema": "floodguard.shelter_capacity.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": str(found.record["source_timestamp"]),
        "source_timestamps": {"flood_input": str(found.record["source_timestamp"]), "population_year_represented": 2020,
                              "shelter_list": "DDPM listed shelters, open data of 21 September 2026",
                              "walking_context_generated_at": walking_record.get("context_generated_at")},
        "confidence_class": "low",
        "confidence_basis": "Modelled walking routes on OpenStreetMap, modelled residents, listed planning capacities whose operating status nobody verified, and closures assumed from an agency season layer that was not checked in the field.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "fpps_input": False,
        "publication_level": "pitch",
        "label": capacity.LABEL,
        "what_this_is": "Shelter access on foot and listed shelter places against the residents in reach, for case SE1. Report-only, pitch level: not for a public file.",
        "walking_context": {"status": walking_record["status"], "canonical_sha256": walking_record["canonical_sha256"],
                            "accepted_for": "report-only shelter figures, by the owner on 9 October 2026 (decision log R40); the registered task E5 receipt still calls it a candidate"},
        "method": {"source": "planning_protocol_v1b.json /facility_sets/two_step_access", "measure": "binary 2SFCA",
                   "thresholds_minutes": list(capacity.THRESHOLDS_MINUTES), "primary_threshold_minutes": primary,
                   "participation_percent": list(capacity.PARTICIPATION_PERCENT),
                   "ratio": "listed places in reach of a resident, shared among everyone in reach of each shelter who would seek a place; under 1 means fewer places than people seeking them",
                   "allocation": False},
        "shelters": {"where": "the routing context, which is wider than the eight tambons",
                     "located_and_joined_to_the_walking_graph": len(sites), "listed_places": float(places.sum()),
                     "within_60_minutes_on_foot_of_a_resident_of_the_tambons": int(in_reach.sum()),
                     "listed_places_of_those": float(places[in_reach].sum()),
                     "with_their_point_inside_the_flood_layer_among_those": int((inside_layer & in_reach).sum()),
                     "with_their_point_inside_the_flood_layer": int(inside_layer.sum()),
                     "listed_places_of_those_inside_the_layer": float(places[inside_layer].sum())},
        "residents": {"in_the_eight_tambons": round(float(residents.sum()), 1), "demand_cells": int(residents.size)},
        "checks": {"minutes_to_the_nearest_shelter_are_those_of_the_engine": {"result": "PASS", "largest_difference_minutes": worst},
                   "counts_per_tambon_are_those_of_the_task_e5_shelter_table": {"result": "PASS", "values_compared": compared}},
        "states": {BASELINE: "no flood", "strict": "closure rule v1, strict level", "central": "closure rule v1, central level",
                   "permissive": "closure rule v1, permissive level",
                   DRY_ONLY: "central level, and a shelter whose point lies inside the flood layer offers no place and is no destination"},
        "access_on_foot": {
            "what": "residents with a located shelter within the minutes named, by state",
            "whole_frame": {state: access(state) for state in states},
            "by_tambon": {unit_id: {"unit_name_en": names[unit_id][0], "residents": round(float(residents[unit_of == unit_id].sum()), 1),
                                    **{state: access(state, unit_of == unit_id) for state in states}} for unit_id in unit_ids},
        },
        "two_step": {state: two_step_block(state, supply_of[state]) for state in (BASELINE, "central", DRY_ONLY)},
        "by_shelter": shelters,
        "credits": ["Shelters: DDPM open catalogue (listed shelters). Roads © OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0).",
                    "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard; the figures derived from it are shared under CC BY-SA 4.0."],
        "assumptions": ["Everyone walks at the speeds of the walking context; nobody is driven or carried.",
                        "A closure is a modelled assumption of closure rule v1, not an observed closure.",
                        "A listed capacity is a planning figure. Whether a shelter was open, and for how many, was not verified.",
                        "The participation shares of 5, 10 and 25 percent are assumptions, not estimates of who would go.",
                        "A shelter is a destination wherever it stands; only the last state leaves out the shelters whose point the flood layer covers."],
        "limits": ["Pitch level: not for a public file (protocol v1b; decision D8b).",
                   "The walking context is a candidate build without a declared compute window (open point E5-OP5).",
                   "2SFCA is not promoted: it is no input of the planning score and changes no class.",
                   "A scenario of the 2024 season layer, not a flood of any day. Class E never means safe, and a shelter in reach is not a shelter that is open."],
    }
    work = runner.stage_folder(CASE, frame_set, external).parent / WORK_FOLDER
    work.mkdir(parents=True, exist_ok=True)
    result_bytes = encode(result)
    (work / RESULT_NAME).write_bytes(result_bytes)

    whole = result["access_on_foot"]["whole_frame"]
    lines = [
        "# Shelters in case SE1: pitch note (not for a public file)", "",
        f"Label on every figure: **{capacity.LABEL}**. Planning guidance, not an official warning.", "",
        f"- Residents of the eight tambons: {residents.sum():,.0f}. Located shelters within 60 minutes on foot of any of them: {int(in_reach.sum())}, "
        f"with {places[in_reach].sum():,.0f} listed places. (The routing context around the district holds {len(sites)} located shelters.)",
        f"- Of those in reach, shelters whose point the flood layer covers: {int((inside_layer & in_reach).sum())}, "
        f"with {places[inside_layer & in_reach].sum():,.0f} listed places.",
        f"- Residents with a shelter within 30 minutes on foot: {whole[BASELINE]['30']:,.0f} before, {whole['central']['30']:,.0f} in the scenario (central closure level), "
        f"{whole[DRY_ONLY]['30']:,.0f} when shelters inside the layer are left out.", "",
        "| Tambon | Residents | Within 30 min, before | In the scenario | With flooded shelters left out |", "|---|---:|---:|---:|---:|"]
    for unit_id in unit_ids:
        row = result["access_on_foot"]["by_tambon"][unit_id]
        lines.append(f"| {row['unit_name_en']} | {row['residents']:,.0f} | {row[BASELINE]['30']:,.0f} | {row['central']['30']:,.0f} | {row[DRY_ONLY]['30']:,.0f} |")
    lines += ["", "## Listed places against the people who would seek one (2SFCA, 30 minutes)", "",
              "| State | Participation | People seeking a place | Residents in reach with under one listed place per person seeking | Share of those in reach |", "|---|---:|---:|---:|---:|"]
    for state in (BASELINE, "central", DRY_ONLY):
        reading = result["two_step"][state][str(primary)]["whole_frame"]
        for percent in capacity.PARTICIPATION_PERCENT:
            entry = reading["participation"][str(percent)]
            share = "" if entry["share_of_the_residents_in_reach"] is None else f"{100 * entry['share_of_the_residents_in_reach']:.0f}%"
            lines.append(f"| {state} | {percent}% | {entry['people_seeking_a_place']:,.0f} | "
                         f"{entry['residents_in_reach_with_under_one_listed_place_per_person_seeking']:,.0f} | {share} |")
    lines += ["", "Capacities are listed planning figures; operating status was not verified. Participation shares are assumptions.",
              "The walking network is a candidate build. A scenario of the 2024 season layer, not a flood of any day.", ""]
    note_bytes = ("\n".join(lines)).encode("utf-8")
    (work / NOTE_NAME).write_bytes(note_bytes)

    import hashlib

    receipt = {
        "schema": "floodguard.shelter_capacity_receipt.v1",
        "generated_at_utc": result["generated_at_utc"],
        "source_timestamp": result["source_timestamp"],
        "confidence_class": "low",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "fpps_input": False,
        "what_this_is": "The receipt of a report-only run: shelter access on foot and listed shelter places against the residents in reach, for case SE1.",
        "why_no_figure_is_here": "Shelter figures are pitch level (protocol v1b, facility_sets; decision D8b). This file is in a public repository, so it holds no figure of the shelter service: no count of residents, no capacity and no ratio. The result and the pitch note are outside Git and are bound here by SHA-256.",
        "publication_level_of_the_result": "pitch",
        "label_of_the_result": capacity.LABEL,
        "case_id": CASE, "frame_set": FRAME,
        "protocol_sha256": found.hashes,
        "method": result["method"],
        "states": result["states"],
        "walking_context": result["walking_context"],
        "checks": {"minutes_to_the_nearest_shelter_are_those_of_the_engine": "PASS",
                   "counts_per_tambon_are_those_of_the_task_e5_shelter_table": {"result": "PASS", "values_compared": compared}},
        "outputs_outside_git": [
            {"path": f"{runner.EXTERNAL_LABEL}/{(work / RESULT_NAME).relative_to(external).as_posix()}", "sha256": hashlib.sha256(result_bytes).hexdigest(), "bytes": len(result_bytes)},
            {"path": f"{runner.EXTERNAL_LABEL}/{(work / NOTE_NAME).relative_to(external).as_posix()}", "sha256": hashlib.sha256(note_bytes).hexdigest(), "bytes": len(note_bytes)}],
        "assumptions": result["assumptions"],
        "limits": result["limits"],
    }
    (ROOT / RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / RECEIPT).write_bytes(encode(receipt))
    print((work / NOTE_NAME).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
