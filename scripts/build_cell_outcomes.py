"""What the scenario of case SE1 does to every 100 m demand cell, in each of the nine access runs. A cache, report-only.

The registered runs keep counts per tambon. Three pieces of work need the cell below the tambon: the need mix inside
a tambon, the need map, and the age comparison with another age mix. This script computes, once, for every demand
cell of the eight tambons: whether its centre lies inside the flood layer at each of the three flood levels, and its
modelled minutes to the nearest hospital and to the nearest main-road entry before the flood and in each of the nine
runs (three flood levels by three levels of closure rule v1). It writes them outside Git and a receipt in Git.

It changes nothing of record and computes no score and no class. Before it writes it checks its cells against the
runs of record:

* at the flood level as provided, the residents of every tambon who lose a hospital within 30 minutes and who lose
  every road route are those of the committed task E5 table, at each closure level;
* for every tambon, flood level, closure level and demand, the exposure and the road criticality that follow from
  the cells are the components of the registered ensemble run (its file of per-unit results, bound by SHA-256).

A closure is a modelled assumption, residents are modelled counts, and the case is a scenario of the 2024 season
layer, not a flood of any day. Nothing here is an official warning.

Example::

    python scripts/build_cell_outcomes.py --external-data <external data root> --age-dir <folder of the age rasters>
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

from floodguard import access_diff, closure_rules, demand_rescale, flood_inputs  # noqa: E402

CASE, FRAME = "SE1", "mae_sai"
RECEIPT = "outputs/cell_outcomes/se1_mae_sai_v1_receipt.json"
WORK_FOLDER = "cell_outcomes"
CACHE_NAME = "cell_outcomes_se1_mae_sai_v1.npz"
HOSPITAL_MINUTES = 30
VINTAGES = ("worldpop_2020", demand_rescale.RESCALED_LEVEL)
TOLERANCE = 1e-6


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
    """The cache cannot be built, or its cells do not add up to the runs of record."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--age-dir", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = arguments.external_data
    if (ROOT / RECEIPT).exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the receipt exists; a second run needs --replace and --reason")

    import shapely

    runner = load_script("build_uncertainty_ensemble")
    e5_builder = runner.e5_builder
    frame_set = runner.FRAME_SETS[FRAME]
    found = runner.prepare(CASE, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH, age_dir=arguments.age_dir)
    v1a = json.loads(found.v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    graph = found.graph
    services = [rule for rule in access_diff.service_rules(v1a, v1b)
                if rule.mode == access_diff.VEHICLE and rule.service in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY)]

    # --- the registered ensemble run this cache is checked against ------------------------------------------------
    registered_path = runner.receipt_path_for(CASE, frame_set)
    registered = json.loads(registered_path.read_text(encoding="ascii"))
    units_path = runner.results_path(CASE, frame_set, external)
    bound = registered["outputs"]["ensemble"]["files"][0]
    if sha256_file(units_path) != bound["sha256"]:
        raise BuildError("the file of per-unit results is not the one the registered ensemble receipt binds")
    of_record = json.loads(units_path.read_text(encoding="ascii"))["units"]

    cells = [cell for cell in found.counted.cells if cell["unit_id"] is not None]
    identifiers = [cell["population_id"] for cell in cells]
    position = {row["population_id"]: row for row in graph.population}
    unit_of = np.array([str(cell["unit_id"]) for cell in cells])
    unit_ids = sorted(found.unit_ids)
    x = np.array([float(cell["x"]) for cell in cells])
    y = np.array([float(cell["y"]) for cell in cells])
    residents = {VINTAGES[0]: np.array([float(cell["residents"]) for cell in cells]),
                 VINTAGES[1]: np.array([found.rescaled.by_cell[str(identifier)] for identifier in identifiers])}

    points = shapely.points(x, y)
    inside = {}
    for level in flood_inputs.LEVELS:
        extent = found.flood.extents[level]
        shapely.prepare(extent)
        inside[level] = np.asarray(shapely.covers(extent, points), dtype=bool)

    baseline = e5_builder.baseline_runs(graph, services)
    connected = np.array([identifier in baseline[access_diff.HOSPITAL] for identifier in identifiers])

    def minutes(run: dict[str, dict[str, float | None]], service: str) -> np.ndarray:
        table = run[service]
        return np.array([np.inf if table.get(identifier) is None else float(table[identifier]) for identifier in identifiers])

    hospital_before, entry_before = minutes(baseline, access_diff.HOSPITAL), minutes(baseline, access_diff.MAIN_ROAD_ENTRY)
    had_hospital = connected & (hospital_before <= HOSPITAL_MINUTES)
    had_route = connected & (np.isfinite(hospital_before) | np.isfinite(entry_before))

    committed = {(run["flood_level"], run["closure_level"]): run for run in found.access_table["runs"]}
    record_rows = {(unit["unit_id"], item["flood_input_single_state"], item["passability"], item["population_vintage"]): item["components"]
                   for unit in of_record for item in unit["routing_combinations"]}
    runs: list[tuple[str, str]] = []
    hospital_after: list[np.ndarray] = []
    entry_after: list[np.ndarray] = []
    compared = {"e5_table_values": 0, "ensemble_components": 0}
    clock = time.perf_counter()
    for flood_level, extent_metres in found.closure_extents.items():
        extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
        intersections = closure_rules.edge_intersections(graph.edges, graph.node_coordinates, extent)
        for level in closure_rules.LEVELS:
            edges, _applied = access_diff.flooded_edges(level, graph.edges, intersections,
                                                        flood_input_id=str(found.record["input_id"]), arguments=closure)
            flooded = {rule.service: access_diff.cell_minutes(graph.population, edges, graph.destinations[rule.service],
                                                              baseline_nodes=graph.nodes) for rule in services}
            hospital, entry = minutes(flooded, access_diff.HOSPITAL), minutes(flooded, access_diff.MAIN_ROAD_ENTRY)
            lost_hospital = had_hospital & ~(hospital <= HOSPITAL_MINUTES)
            lost_route = had_route & ~(np.isfinite(hospital) | np.isfinite(entry))
            stated = committed.get((flood_level, level))
            for unit_id in unit_ids:
                here = unit_of == unit_id
                if stated is not None:
                    row = next(item for item in stated["units"] if str(item["unit_id"]) == unit_id)
                    wanted = (row["access"]["hospital"]["thresholds_minutes"][str(HOSPITAL_MINUTES)]["newly_lost_residents"],
                              row["road_criticality_inputs"]["residents_losing_all_routes"])
                    got = (float(residents[VINTAGES[0]][here & lost_hospital].sum()), float(residents[VINTAGES[0]][here & lost_route].sum()))
                    if any(abs(a - b) > 0.01 for a, b in zip(got, wanted)):
                        raise BuildError(f"{flood_level}/{level}, {unit_id}: {got} does not reproduce the task E5 table {wanted}")
                    compared["e5_table_values"] += 2
                for vintage in VINTAGES:
                    people = residents[vintage]
                    components = record_rows[(unit_id, flood_level, level, vintage)]
                    exposure = 100.0 * float(people[here & inside[flood_level]].sum()) / float(people[here].sum())
                    with_route = float(people[here & had_route].sum())
                    criticality = 100.0 * float(people[here & lost_route].sum()) / with_route if with_route > 0 else 0.0
                    if abs(exposure - components["exposure_0_100"]) > TOLERANCE or abs(criticality - components["road_criticality_0_100"]) > TOLERANCE:
                        raise BuildError(f"{flood_level}/{level}/{vintage}, {unit_id}: exposure {exposure} and road criticality {criticality} "
                                         f"are not the components of the registered ensemble run ({components['exposure_0_100']}, "
                                         f"{components['road_criticality_0_100']})")
                    compared["ensemble_components"] += 2
            runs.append((flood_level, level))
            hospital_after.append(hospital)
            entry_after.append(entry)
            print(flood_level, level, f"{time.perf_counter() - clock:.0f} s", flush=True)
    if len(runs) != 9 or compared["e5_table_values"] != 2 * 3 * len(unit_ids) or compared["ensemble_components"] != 2 * 2 * 9 * len(unit_ids):
        raise BuildError(f"the checks did not cover nine runs and both demands: {compared}")

    work = runner.stage_folder(CASE, frame_set, external).parent / WORK_FOLDER
    work.mkdir(parents=True, exist_ok=True)
    cache = work / CACHE_NAME
    np.savez_compressed(
        cache, population_id=np.array([str(identifier) for identifier in identifiers]), unit_id=unit_of, x=x, y=y,
        longitude=np.array([float(position[identifier]["longitude"]) for identifier in identifiers]),
        latitude=np.array([float(position[identifier]["latitude"]) for identifier in identifiers]),
        residents_worldpop_2020=residents[VINTAGES[0]], residents_rescaled_2024=residents[VINTAGES[1]], connected=connected,
        hospital_before=hospital_before, entry_before=entry_before,
        **{f"inside_{level}": inside[level] for level in flood_inputs.LEVELS},
        runs=np.array([f"{flood_level}|{level}" for flood_level, level in runs]),
        hospital_after=np.stack(hospital_after), entry_after=np.stack(entry_after))
    receipt = {
        "schema": "floodguard.cell_outcomes_receipt.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": str(found.record["source_timestamp"]),
        "source_timestamps": {"flood_input": str(found.record["source_timestamp"]), "population_year_represented": 2020, "population_rescaled_to_year": 2024},
        "confidence_class": "low",
        "confidence_basis": "Modelled access on OpenStreetMap roads and modelled residents; closures assumed from an agency season layer that was not checked in the field.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "The receipt of a cache: for every 100 m demand cell of the eight tambons of case SE1, whether it lies inside the flood layer at each flood level and its modelled minutes to a hospital and to a main-road entry before the flood and in each of the nine access runs. Report-only; no score and no class.",
        "case_id": CASE, "frame_set": FRAME, "protocol_sha256": found.hashes,
        "cells": {"demand_cells": int(unit_of.size), "connected_to_the_road_graph": int(connected.sum()),
                  "residents_worldpop_2020": round(float(residents[VINTAGES[0]].sum()), 1),
                  "residents_rescaled_2024": round(float(residents[VINTAGES[1]].sum()), 1),
                  "residents_in_cells_not_connected_to_the_graph_2020": round(float(residents[VINTAGES[0]][~connected].sum()), 1)},
        "runs": [{"flood_input_single_state": flood_level, "passability": level} for flood_level, level in runs],
        "checks": {
            "as_provided_runs_against_the_e5_table": {"result": "PASS", "values_compared": compared["e5_table_values"],
                                                      "what": "per tambon and closure level: residents who lose a hospital within 30 minutes, and residents who lose every road route"},
            "every_run_against_the_registered_ensemble": {
                "result": "PASS", "values_compared": compared["ensemble_components"], "tolerance": TOLERANCE,
                "what": "per tambon, flood level, closure level and demand: the exposure and the road criticality that follow from the cells are the components of the registered run",
                "registered_receipt": {"path": registered_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(registered_path)},
                "file_of_per_unit_results_sha256": bound["sha256"]},
        },
        "cache_outside_git": {"path": f"{runner.EXTERNAL_LABEL}/{cache.relative_to(external).as_posix()}", "sha256": sha256_file(cache), "bytes": cache.stat().st_size},
        "assumptions": ["A closure is a modelled assumption of closure rule v1, not an observed closure.",
                        "A cell is inside the flood layer when its centre is; a cell is connected when it snaps to the vehicle graph within 250 m.",
                        *demand_rescale.RULES],
        "limits": ["A 100 m cell holds a modelled count of residents; it says nothing about a household or a building.",
                   "The scenario is the season layer of 1 August to 12 October 2024 with every mapped area flooded at once, not a flood of any day.",
                   "Report-only. The registered receipts and the published result file are unchanged."],
    }
    (ROOT / RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / RECEIPT).write_bytes((json.dumps(receipt, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({"cells": receipt["cells"], "checks": {key: value["values_compared"] for key, value in receipt["checks"].items()}}))


if __name__ == "__main__":
    main()
