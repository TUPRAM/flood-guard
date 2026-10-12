"""Case SE1 with residents spread over buildings: the need mix and the 90 cells of the ensemble. Report-only.

Plan: docs/proposal_execution/buildings_in_water_plan_v1.md, section 7.

The residents of each tambon are spread evenly over the buildings of that tambon. With that demand the script makes
the need mix of the case and runs the 90 cells of the uncertainty ensemble through the code of the registered run.
Before it writes it checks that the 90 cells of the 2020 demand come out as the registered run has them.

It changes nothing of record: the published result file, the registered receipts and the run register are not
touched. An ensemble is planning guidance, a closure is a modelled assumption, and class E never means safe.

    python scripts/build_buildings_demand_run.py --external-data <external data root>
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

from floodguard import access_diff, buildings_in_water as bw  # noqa: E402
from floodguard import need_mix as nm  # noqa: E402
from floodguard import uncertainty_ensemble as ensemble  # noqa: E402

CASE, FRAME = "SE1", "mae_sai"
PLAN = "docs/proposal_execution/buildings_in_water_plan_v1.md"
OUTPUT = "outputs/buildings_in_water/se1_mae_sai_buildings_demand_v1.json"
DISTRICT_RECORD = "outputs/buildings_in_water/se1_mae_sai_v1.json"
CLASSES = ("A", "B", "C", "D", "E")
DEMANDS = ("worldpop_2020", "spread_over_buildings")


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


rescaled = load_script("build_ensemble_rescaled_demand")
buildings = load_script("build_buildings_in_water")
need_mix_builder = load_script("build_need_mix")
runner, e5_builder, e8_builder = rescaled.runner, rescaled.e5_builder, rescaled.e8_builder
RunError = rescaled.RunError
SLOT = rescaled.RESCALED  # the name the access runner counts a second demand under


def spread_over_buildings(cells: list[dict[str, Any]], building_x: np.ndarray, building_y: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """The residents of every cell when the residents of each tambon are spread evenly over its buildings."""

    from scipy.spatial import cKDTree

    in_district = np.array([cell["unit_id"] is not None for cell in cells])
    x = np.array([float(cell["x"]) for cell in cells])
    y = np.array([float(cell["y"]) for cell in cells])
    residents = np.array([float(cell["residents"]) for cell in cells])
    unit = np.array([str(cell["unit_id"]) for cell in cells])
    places = np.flatnonzero(in_district)
    distance, nearest = cKDTree(np.column_stack([x[places], y[places]])).query(np.column_stack([building_x, building_y]))
    held = np.bincount(places[nearest[distance <= bw.CELL_REACH_M]], minlength=len(cells)).astype("float64")
    spread = residents.copy()  # cells outside the district keep what they hold; they count for no tambon
    by_unit: dict[str, Any] = {}
    for code in sorted(set(unit[in_district])):
        mine = in_district & (unit == code)
        total, count = float(residents[mine].sum()), float(held[mine].sum())
        if count == 0:
            raise RunError(f"{code} holds no building to spread its residents over")
        spread[mine] = held[mine] * total / count
        by_unit[code] = {"residents": round(total, 1), "buildings": int(count), "residents_per_building": round(total / count, 3),
                         "cells": int(mine.sum()), "cells_with_a_building": int((mine & (held > 0)).sum())}
    return spread, {"buildings_in_a_cell_of_the_district": int(held[in_district].sum()), "by_unit": by_unit}


def unit_view(unit: dict[str, Any]) -> dict[str, Any]:
    """What the report says of one unit with one demand: its default cell and its classes over the cells."""

    reference = unit["reference_cell"]
    counts = {letter: 0 for letter in CLASSES} | {"no_class": 0}
    for cell in unit["cells"]:
        counts[cell["action_class"] if cell.get("action_class") in CLASSES else "no_class"] += 1
    return {
        "default_cell": {key: reference.get(key) for key in ("fpps_0_100", "action_class", "action_reason_code")},
        "cells_run": unit["cells_run"],
        "class_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = arguments.external_data
    output = ROOT / OUTPUT
    if output.exists() and not (arguments.replace and arguments.reason):
        raise RunError("the report exists; a second run needs --replace and --reason")

    clock = time.perf_counter()
    frame_set = runner.FRAME_SETS[FRAME]
    found = runner.prepare(CASE, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH)
    v1a = json.loads(found.v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    print(f"inputs checked: {time.perf_counter() - clock:.0f} s", flush=True)

    # --- the demand ---------------------------------------------------------------------------------------------------
    outlines = buildings.read_outlines(external, "mae_sai")
    centre = outlines.geometry.centroid
    all_cells = list(found.counted.cells)
    spread, demand_record = spread_over_buildings(all_cells, centre.x.to_numpy(), centre.y.to_numpy())
    district_record = json.loads((ROOT / DISTRICT_RECORD).read_text(encoding="utf-8"))
    if demand_record["buildings_in_a_cell_of_the_district"] != district_record["buildings"]["in_a_demand_cell"]:
        raise RunError("the buildings in a cell of the district are not as many as the committed record of the district holds")
    cells_20 = [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": cell["residents"]} for cell in all_cells]
    cells_b = [{**cell, "residents": float(value)} for cell, value in zip(all_cells, spread)]
    alternate = {SLOT: [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": cell["residents"]} for cell in cells_b]}

    # --- the nine access runs, each counted on both demands ---------------------------------------------------------------
    services = access_diff.service_rules(v1a, v1b)
    closure = access_diff.closure_arguments(v1b)
    clock = time.perf_counter()
    baselines = {access_diff.VEHICLE: e5_builder.baseline_runs(found.graph, services)}
    computed = e5_builder.case_runs(CASE, str(found.record["input_id"]), found.closure_extents, {access_diff.VEHICLE: found.graph},
                                    baselines, services, closure, cells_20, list(found.unit_ids), alternate_cells=alternate)
    runs = computed["runs"]
    print(f"access runs: {time.perf_counter() - clock:.0f} s", flush=True)
    as_provided = runner.check_as_provided_runs(runs, found.access_table)
    measurements, losing, _checks = runner.measurements_of_the_cells(found, runs)
    in_slot, losing_in_slot, checks_b = rescaled.rescaled_measurements(found, runs, measurements, cells_b)

    def as_the_only_demand(values: dict[Any, Any]) -> dict[Any, Any]:
        return {(flood, closure_level, level, runner.VINTAGE_RUN): value for (flood, closure_level, level, _slot), value in values.items()}

    def run(of: dict[Any, Any], lost: dict[Any, Any]) -> dict[str, Any]:
        return ensemble.run_ensemble(found.grid, found.rules, found.case, found.flood_spec, of, routing_context_id=found.context_id,
                                     level=runner.LEVEL, not_run=found.not_run, people_losing_access=lost)

    result_20 = run(measurements, losing)
    result_b = run(as_the_only_demand(in_slot), as_the_only_demand(losing_in_slot))

    # --- the 2020 demand must come out as the registered run has it ---------------------------------------------------
    digest = e8_builder.rows_sha256(result_20["reference_rows"])
    if digest != found.e8_run["rows_sha256"]:
        raise RunError("the rows of the default cell do not have the SHA-256 the registered task E8 receipt records")
    receipt_path = runner.receipt_path_for(CASE, frame_set)
    registered_units = json.loads(runner.results_path(CASE, frame_set, external).read_text(encoding="utf-8"))["units"]
    recorded = {(unit["unit_id"], cell["cell_id"]): (cell["fpps_0_100"], cell["action_class"])
                for unit in registered_units for cell in unit["cells"] if cell["population_vintage"] == runner.VINTAGE_RUN}
    compared, different = 0, []
    for unit in result_20["units"]:
        for cell in unit["cells"]:
            compared += 1
            if recorded.get((unit["unit_id"], cell["cell_id"])) != (cell["fpps_0_100"], cell["action_class"]):
                different.append(f"{unit['unit_id']} {cell['cell_id']}")
    if different or compared != len(recorded):
        raise RunError(f"{len(different)} unit cell(s) of the 2020 demand differ from the registered run ({compared} compared, {len(recorded)} registered)")

    # --- the need mix with each demand ------------------------------------------------------------------------------
    receipt = json.loads((ROOT / need_mix_builder.CACHE_RECEIPT).read_text(encoding="utf-8"))
    cache_path = external / receipt["cache_outside_git"]["path"][len(need_mix_builder.EXTERNAL_LABEL) + 1:]
    if e8_builder.sha256_file(cache_path) != receipt["cache_outside_git"]["sha256"]:
        raise RunError("the cache of the cells is not the file its receipt binds")
    cache = np.load(cache_path)
    by_id = {str(cell["population_id"]): float(value) for cell, value in zip(all_cells, spread)}
    people = {DEMANDS[0]: cache["residents_worldpop_2020"].astype("float64"),
              DEMANDS[1]: np.array([by_id[str(identifier)] for identifier in cache["population_id"]])}
    if abs(float(people[DEMANDS[0]].sum()) - float(people[DEMANDS[1]].sum())) > 0.5:
        raise RunError("the two demands do not hold the same residents in the district")
    unit_of, connected = cache["unit_id"], cache["connected"]
    hospital_before, entry_before = cache["hospital_before"], cache["entry_before"]
    had_route = connected & (np.isfinite(hospital_before) | np.isfinite(entry_before))
    had_hospital = connected & (hospital_before <= need_mix_builder.HOSPITAL_MINUTES)
    names = [str(name) for name in cache["runs"]]

    def state(name: str) -> tuple[np.ndarray, ...]:
        number = names.index(name)
        hospital, entry = cache["hospital_after"][number], cache["entry_after"][number]
        return (cache[f"inside_{name.split('|')[0]}"], connected, had_route, had_route & (np.isfinite(hospital) | np.isfinite(entry)),
                had_hospital, had_hospital & (hospital <= need_mix_builder.HOSPITAL_MINUTES))

    labels = {name: nm.label_cells(*state(name)) for name in names}
    published = need_mix_builder.PUBLISHED_RUN

    def mixes(where: np.ndarray | None) -> dict[str, Any]:
        return {demand: {"in_the_published_run": {**nm.mix(labels[published], values, where),
                                                  "hidden_by_the_order": nm.overlaps(*state(published), values, where)},
                         "over_the_nine_runs": nm.mix_range([nm.mix(labels[name], values, where) for name in names])}
                for demand, values in people.items()}

    need = {"district": mixes(None), "by_tambon": {code: mixes(unit_of == code) for code in sorted(found.unit_ids)}}

    # --- the report ----------------------------------------------------------------------------------------------------
    views = {DEMANDS[0]: {unit["unit_id"]: unit_view(unit) for unit in result_20["units"]},
             DEMANDS[1]: {unit["unit_id"]: unit_view(unit) for unit in result_b["units"]}}
    unit_names = {unit["unit_id"]: unit["unit_name_en"] for unit in result_20["units"]}
    changed = [f"{unit_names[code]}: {views[DEMANDS[0]][code]['default_cell']['action_class']} with the 2020 grid, "
               f"{views[DEMANDS[1]][code]['default_cell']['action_class']} with residents spread over buildings"
               for code in sorted(unit_names)
               if views[DEMANDS[0]][code]["default_cell"]["action_class"] != views[DEMANDS[1]][code]["default_cell"]["action_class"]]
    report = {
        "schema": "floodguard.buildings_in_water.buildings_demand_run.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": str(found.record["source_timestamp"]),
        "source_timestamps": {"flood_input": str(found.record["source_timestamp"]), "population_year_represented": 2020,
                              "building_outlines": "file of 26 August 2024, images of earlier years"},
        "confidence_class": "low",
        "confidence_basis": runner.CONFIDENCE_BASIS,
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "label": "scenario, not an observation",
        "plan": {"path": PLAN, "section": 7, "sha256": e8_builder.sha256_file(ROOT / PLAN)},
        "what_this_is": "Case SE1 with the residents of each tambon spread evenly over the buildings of that tambon, beside the "
                        "same case with the population grid of 2020: the need mix, and the 90 cells of the uncertainty ensemble. "
                        "Report-only.",
        "not_of_record": "This is not a registered run. The published result file, the registered receipts and the run register "
                         "are unchanged, and the classes of record are those of the published result.",
        "case_id": CASE, "frame_set": FRAME, "level": runner.LEVEL, "protocol_sha256": found.hashes,
        "demand": {"rule": "The residents of each tambon, as the 2020 grid counts them, spread evenly over the buildings of the "
                           "tambon; a building belongs to the cell whose centre is nearest, within 75 m; a cell without a "
                           "building holds nobody.",
                   "outlines": {"path": f"{buildings.OUTPUT_DIR}/{buildings.OUTLINES_NAME}",
                                "sha256": e8_builder.sha256_file(ROOT / buildings.OUTPUT_DIR / buildings.OUTLINES_NAME)},
                   **demand_record},
        "checks": {
            "default_cell_of_the_2020_demand_against_the_e8_rows": {"result": "PASS", "rows_sha256": digest},
            "cells_of_the_2020_demand_against_the_registered_run": {
                "result": "PASS", "unit_cells_compared": compared,
                "registered_receipt": {"path": receipt_path.relative_to(ROOT).as_posix(), "sha256": e8_builder.sha256_file(receipt_path)}},
            "as_provided_runs_against_the_e5_table": as_provided,
            "measurements_with_the_buildings_demand": checks_b,
            "residents_of_the_district_same_in_both_demands": True,
        },
        "default_cell_classes_that_differ": changed,
        "units": [{"unit_id": code, "unit_name_en": unit_names[code], **{demand: views[demand][code] for demand in DEMANDS}}
                  for code in sorted(unit_names)],
        "need_mix": need,
        "credits": [buildings.CREDIT,
                    "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard; the figures derived from it are shared under CC BY-SA 4.0.",
                    "Residents: WorldPop 2020 (CC BY 4.0). Modelled, not observed.", "Roads © OpenStreetMap contributors (ODbL 1.0)."],
        "assumptions": [
            "Every building counts as one home of the same size.",
            "The share of children and older residents of a tambon, and so its vulnerability component, is the same for both demands.",
            "Travel times do not depend on the demand: the nine access runs are the same, and only the residents of the cells differ.",
            "A closure is a modelled assumption of closure rule v1, not an observed closure.",
        ],
        "limits": [
            "Report-only: not a registered run of the protocol, and one way of many to spread residents over buildings.",
            "The outlines are drawn by a model on images of earlier years; sheds, shops and temples count like houses.",
            "The cells of the 2024-rescaled demand are not run here: 90 cells, not the 180 a public result is judged on.",
            "Planning guidance only. Class E never means safe.",
        ],
    }
    if output.exists():
        old = json.loads(output.read_text(encoding="utf-8"))
        report["supersedes"] = {"reason": arguments.reason, "generated_at_utc": old.get("generated_at_utc")}
    output.write_bytes((json.dumps(report, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({"changed": changed}, ensure_ascii=False))
    for unit in report["units"]:
        first, second = unit[DEMANDS[0]], unit[DEMANDS[1]]
        print(unit["unit_name_en"], first["default_cell"]["action_class"], first["default_cell"]["fpps_0_100"], first["class_counts"], "|",
              second["default_cell"]["action_class"], second["default_cell"]["fpps_0_100"], second["class_counts"], flush=True)


if __name__ == "__main__":
    main()
