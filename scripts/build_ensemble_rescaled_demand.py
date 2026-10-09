"""The uncertainty ensemble of a case with the 2024-rescaled demand added: a report-only run beside the run of record.

The registered run of plan task E10 runs 90 of the 180 cells a public result needs: the cells of the WorldPop 2020
demand. The other 90 use the 2024-rescaled demand, which no stage built (open point E10-OP2). This script builds
that demand with the two rules of ``floodguard.demand_rescale`` (decision log R38) and runs all 180 cells.

It changes nothing of record. It reads the case through the checks of the registered builder
(``build_uncertainty_ensemble.prepare``), makes the nine access runs with the unchanged task E5 runner, which now
also counts each run on the rescaled demand, and scores every cell with ``floodguard.uncertainty_ensemble``. Before
it writes it checks that:

* the default cell is the rows the registered task E8 receipt records (their SHA-256);
* every one of the 90 cells of the 2020 demand has, for every unit, the planning score and the class of the
  registered task E10 run.

The registered E10 receipt, the run register and the published result file are not touched: the published file
still says that the stability of its classes is not evaluated. An ensemble is planning guidance. It is not an
official warning, a closure is a modelled assumption, and class E never means safe.

Example::

    python scripts/build_ensemble_rescaled_demand.py --case SE1 --frame mae_sai --external-data <external data root> \\
        --age-dir <folder of the 20 WorldPop 2024 age rasters>
"""

from __future__ import annotations

import argparse
from dataclasses import replace
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

from floodguard import access_diff, age_exposure, flood_inputs, planning_assessment  # noqa: E402
from floodguard import demand_rescale  # noqa: E402
from floodguard import uncertainty_ensemble as ensemble  # noqa: E402

OUTPUT_DIR = "outputs/uncertainty_ensemble_rescaled"
POPULATION_2020 = Path("open_context") / "worldpop_population" / "tha_ppp_2020.tif"
RESCALED = demand_rescale.RESCALED_LEVEL
CLASSES = ("A", "B", "C", "D", "E")


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


runner = load_script("build_uncertainty_ensemble")
e8_builder, e5_builder = runner.e8_builder, runner.e5_builder


class RunError(RuntimeError):
    """The report-only run cannot be made, or one of its checks failed."""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))  # LF bytes


def rescaled_residents(found: Any, external: Path, age_dir: Path, v1b: dict[str, Any], registered: dict[str, Any]
                       ) -> tuple[dict[str, float], dict[str, Any]]:
    """The 2024-rescaled resident count of every demand cell of the planning context, with the record of the rescale."""

    import rasterio
    from rasterio.windows import Window

    population_path = external / POPULATION_2020
    stated = (registered.get("lineage_input_sha256") or {}).get("worldpop_2020_100m")
    population_sha = e8_builder.sha256_file(population_path)
    if population_sha != stated:
        raise RunError("the WorldPop 2020 raster is not the file the registered run names")
    anchors = load_script("build_national_vulnerability_anchors")
    manifest, paths, _hashes = anchors.check_age_sources(age_dir, v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"])

    rows = list(found.graph.population)
    lon = np.array([float(row["longitude"]) for row in rows])
    lat = np.array([float(row["latitude"]) for row in rows])
    residents = np.array([float(row["total_population"]) for row in rows])
    rasters = {band: rasterio.open(paths[band]) for band in age_exposure.AGE_BANDS}
    try:
        first = rasters[age_exposure.AGE_BANDS[0]]
        grid = first.transform
        if grid.b != 0 or grid.d != 0 or first.crs.to_epsg() != 4326:
            raise RunError("the 2024 age grid is not a north-up grid in EPSG:4326")
        geometry = {"west": grid.c, "north": grid.f, "cell_width": grid.a, "cell_height": -grid.e, "rows": first.height, "columns": first.width}
        cells_of_demand = demand_rescale.cell_index(lon, lat, **geometry)
        if (cells_of_demand < 0).any():
            raise RunError("a demand cell lies outside the 2024 age grid")
        cell_rows, cell_columns = cells_of_demand // first.width, cells_of_demand % first.width
        row0, row1 = max(0, int(cell_rows.min()) - 1), min(first.height, int(cell_rows.max()) + 2)
        column0, column1 = max(0, int(cell_columns.min()) - 1), min(first.width, int(cell_columns.max()) + 2)
        window = Window(column0, row0, column1 - column0, row1 - row0)
        totals_grid, _dependants, valid = age_exposure.read_grid_counts(rasters, window)
    finally:
        for source in rasters.values():
            source.close()
    totals: dict[int, float | None] = {}
    for row in range(row0, row1):
        for column in range(column0, column1):
            total = float(totals_grid[row - row0, column - column0])
            totals[row * geometry["columns"] + column] = total if bool(valid[row - row0, column - column0]) else None

    west, north = geometry["west"] + column0 * geometry["cell_width"], geometry["north"] - row0 * geometry["cell_height"]
    east, south = geometry["west"] + column1 * geometry["cell_width"], geometry["north"] - row1 * geometry["cell_height"]
    with rasterio.open(population_path) as source:
        fine = source.transform
        if fine.b != 0 or fine.d != 0 or source.crs.to_epsg() != 4326:
            raise RunError("the WorldPop 2020 raster is not a north-up grid in EPSG:4326")
        first_column = int(math.floor((west - fine.c) / fine.a))
        last_column = int(math.ceil((east - fine.c) / fine.a))
        first_row = int(math.floor((fine.f - north) / -fine.e))
        last_row = int(math.ceil((fine.f - south) / -fine.e))
        counts = source.read(1, window=Window(first_column, first_row, last_column - first_column, last_row - first_row),
                             boundless=True, fill_value=0).astype("float64")
        nodata = source.nodata
    counts[~np.isfinite(counts) | (counts < 0) | ((counts == nodata) if nodata is not None else False)] = 0.0
    fine_west, fine_north = fine.c + first_column * fine.a, fine.f + first_row * fine.e
    x = fine_west + (np.arange(counts.shape[1]) + 0.5) * fine.a
    y = fine_north + (np.arange(counts.shape[0]) + 0.5) * fine.e
    grid_x, grid_y = np.meshgrid(x, y)
    ids = demand_rescale.cell_index(grid_x, grid_y, **geometry)
    in_window = np.isin(ids, np.fromiter(totals.keys(), dtype="int64"))
    counts = np.where(in_window, counts, 0.0)  # pixels of 1 km cells that are not read whole are left out
    rescaled = demand_rescale.rescale_counts(counts, np.where(in_window, ids, -1), totals)

    pixel_column = np.floor((lon - fine_west) / fine.a).astype("int64")
    pixel_row = np.floor((fine_north - lat) / -fine.e).astype("int64")
    values = demand_rescale.demand_values(counts, rescaled["counts"], pixel_row, pixel_column, residents)
    kept = rescaled["kept_at_2020"][pixel_row, pixel_column]
    record = {
        **rescaled["record"],
        "scope_of_the_counts_above": "every 2020 100 m count of the 1 km cells that hold a demand cell of the planning context, and one ring of cells around them",
        "demand_cells": int(residents.size), "demand_residents_2020": math.fsum(residents.tolist()),
        "demand_residents_rescaled": math.fsum(values.tolist()),
        "demand_cells_kept_at_2020": int(kept.sum()), "demand_residents_kept_at_2020": math.fsum(residents[kept].tolist()),
        "sources": {"worldpop_2020": {"file": POPULATION_2020.as_posix(), "sha256": population_sha},
                    "worldpop_2024_age_counts": {"product": manifest.get("product"), "year_represented": manifest.get("year_represented"),
                                                 "manifest_sha256": v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"],
                                                 "total": "the sum of the 20 age bands of a 1 km cell; no total where a band has no valid count"}},
    }
    return {str(row["population_id"]): float(value) for row, value in zip(rows, values)}, record


def rescaled_measurements(found: Any, runs: list[dict[str, Any]], measurements: dict[Any, Any], cells_24: list[dict[str, Any]]
                          ) -> tuple[dict[Any, Any], dict[Any, Any], dict[str, Any]]:
    """The measurements of every unit for the nine combinations of the rescaled demand, built as the builder builds the 2020 ones."""

    flood = found.flood
    residents = planning_assessment.residents_by_unit(cells_24)
    inside = {level: planning_assessment.residents_by_unit(cells_24, flood.extents[level]) for level in flood_inputs.LEVELS}
    result: dict[Any, Any] = {}
    losing: dict[Any, Any] = {}
    differing: list[str] = []
    for run in runs:
        of_2020 = measurements[(run["flood_level"], run["closure_level"], runner.LEVEL, runner.VINTAGE_RUN)]
        rows = {str(row["unit_id"]): row for row in run[e5_builder.ALTERNATE_DEMAND][RESCALED]["units"]}
        listed, lost = [], {}
        for unit in of_2020:
            counts = planning_assessment.access_counts_from_e5_row(rows[unit.unit_id], found.services)
            total = residents.get(unit.unit_id, 0.0)
            if abs(counts["residents"] - total) > runner.RESIDENT_TOLERANCE:
                differing.append(f"{unit.unit_id} at {run['flood_level']}/{run['closure_level']}")
            base = replace(
                unit, unit_residents=total,
                residents_inside_flood_extent={level: inside[level].get(unit.unit_id, 0.0) for level in flood_inputs.LEVELS},
                residents_connected_to_the_graph=counts["residents_connected_to_the_graph"],
                connected_residents_without_a_hospital_route=counts["connected_residents_without_a_hospital_route"])
            listed.append(ensemble.cell_measurements(
                base, flooded_non_permanent_water_land_area=unit.flooded_non_permanent_water_land_area,
                residents_inside_flood_extent=inside[run["flood_level"]].get(unit.unit_id, 0.0),
                access_gap_inputs=counts["access_gap_inputs"],
                residents_losing_all_routes=counts["residents_losing_all_routes"],
                residents_with_baseline_route=counts["residents_with_baseline_route"]))
            lost[unit.unit_id] = {
                service: float(detail["thresholds_minutes"][str(ensemble.THIRTY_MINUTES)]["newly_lost_residents"])
                for service, detail in rows[unit.unit_id]["access"].items()
                if str(ensemble.THIRTY_MINUTES) in detail["thresholds_minutes"]}
        key = (run["flood_level"], run["closure_level"], runner.LEVEL, RESCALED)
        result[key], losing[key] = listed, lost
    if differing:
        raise RunError(f"an access run counts other rescaled residents for a unit than the rescaled demand holds: {differing}")
    return result, losing, {"combinations_measured": len(result), "unit_residents_same_in_the_demand_and_the_access_tables": True}


def unit_record(unit: dict[str, Any]) -> dict[str, Any]:
    """What the report says of one unit: its reference cell, its classes over the cells by demand, and the headline rule."""

    by_vintage: dict[str, dict[str, int]] = {}
    for cell in unit["cells"]:
        counts = by_vintage.setdefault(cell["population_vintage"], {**{letter: 0 for letter in CLASSES}, "no_class": 0})
        counts[cell["action_class"] if cell.get("action_class") in CLASSES else "no_class"] += 1
    return {
        "unit_id": unit["unit_id"], "unit_name_en": unit["unit_name_en"],
        "reference_cell": {key: unit["reference_cell"][key] for key in ("cell_id", "fpps_0_100", "action_class", "action_reason_code")},
        "cells_run": unit["cells_run"], "fpps_0_100": unit["fpps_0_100"], "class_counts": unit["class_counts"],
        "class_counts_by_demand": by_vintage, "headline_stability": unit["headline_stability"], "rank": unit["rank"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--frame", choices=sorted(runner.FRAME_SETS), required=True)
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--age-dir", type=Path, required=True)
    parser.add_argument("--rescale-only", action="store_true", help="build the rescaled demand, print its record and stop")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = arguments.external_data
    frame_set = runner.FRAME_SETS[arguments.frame]
    name = f"{arguments.case.lower()}_{arguments.frame}_v1"
    result_path = ROOT / OUTPUT_DIR / f"{name}.json"
    if result_path.exists() and not (arguments.replace and arguments.reason):
        raise RunError("the report exists; a second run needs --replace and --reason")

    clock = time.perf_counter()
    found = runner.prepare(arguments.case, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH)
    grid, rules = found.grid, found.rules
    if RESCALED not in grid.axis(ensemble.VINTAGE_AXIS).levels:
        raise RunError(f"the grid of the protocols has no population level named {RESCALED}")
    receipt_path = runner.receipt_path_for(arguments.case, frame_set)
    registered = json.loads(receipt_path.read_text(encoding="utf-8"))
    v1a = json.loads(found.v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    print(f"inputs checked: {time.perf_counter() - clock:.0f} s", flush=True)

    by_cell, rescale_record = rescaled_residents(found, external, arguments.age_dir, v1b, registered)
    cells_20 = [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": cell["residents"]} for cell in found.counted.cells]
    cells_24 = [{**cell, "residents": by_cell[str(cell["population_id"])]} for cell in found.counted.cells]
    alternate = {RESCALED: [{"population_id": cell["population_id"], "unit_id": cell["unit_id"], "residents": cell["residents"]} for cell in cells_24]}
    print(json.dumps({key: rescale_record[key] for key in ("demand_residents_2020", "demand_residents_rescaled", "demand_cells_kept_at_2020",
                                                           "demand_residents_kept_at_2020", "ratio_lowest_median_highest",
                                                           "kept_at_2020_because_the_1km_cell_has_no_2024_total",
                                                           "residents_2024_in_1km_cells_with_no_2020_count")}), flush=True)
    if arguments.rescale_only:
        units = planning_assessment.residents_by_unit(cells_24)
        print(json.dumps({unit_id: [round(found.counted.residents.get(unit_id, 0.0), 1), round(units.get(unit_id, 0.0), 1)] for unit_id in sorted(found.unit_ids)}))
        return

    services = access_diff.service_rules(v1a, v1b)
    closure = access_diff.closure_arguments(v1b)
    clock = time.perf_counter()
    baselines = {access_diff.VEHICLE: e5_builder.baseline_runs(found.graph, services)}
    computed = e5_builder.case_runs(arguments.case, str(found.record["input_id"]), found.closure_extents, {access_diff.VEHICLE: found.graph},
                                    baselines, services, closure, cells_20, list(found.unit_ids), alternate_cells=alternate)
    runs = computed["runs"]
    print(f"access runs: {time.perf_counter() - clock:.0f} s", flush=True)
    as_provided = runner.check_as_provided_runs(runs, found.access_table)
    measurements, losing, checks_20 = runner.measurements_of_the_cells(found, runs)
    measurements_24, losing_24, checks_24 = rescaled_measurements(found, runs, measurements, cells_24)
    not_run = [item for item in found.not_run if item.axis != ensemble.VINTAGE_AXIS]
    result = ensemble.run_ensemble(grid, rules, found.case, found.flood_spec, {**measurements, **measurements_24},
                                   routing_context_id=found.context_id, level=runner.LEVEL, not_run=not_run,
                                   people_losing_access={**losing, **losing_24})

    # --- the two checks against the run of record ----------------------------------------------------------------
    digest = e8_builder.rows_sha256(result["reference_rows"])
    if digest != found.e8_run["rows_sha256"]:
        raise RunError("the rows of the default cell do not have the SHA-256 the registered task E8 receipt records")
    registered_units = json.loads(runner.results_path(arguments.case, frame_set, external).read_text(encoding="utf-8"))["units"]
    recorded = {(unit["unit_id"], cell["cell_id"]): (cell["fpps_0_100"], cell["action_class"]) for unit in registered_units for cell in unit["cells"]}
    compared, different = 0, []
    for unit in result["units"]:
        for cell in unit["cells"]:
            if cell["population_vintage"] != runner.VINTAGE_RUN:
                continue
            compared += 1
            if recorded.get((unit["unit_id"], cell["cell_id"])) != (cell["fpps_0_100"], cell["action_class"]):
                different.append(f"{unit['unit_id']} {cell['cell_id']}")
    if different or compared != len(recorded):
        raise RunError(f"{len(different)} unit cell(s) of the 2020 demand differ from the registered run ({compared} compared, {len(recorded)} registered)")

    units_24 = planning_assessment.residents_by_unit(cells_24)
    work = runner.stage_folder(arguments.case, frame_set, external) / "rescaled_demand_report"
    work.mkdir(parents=True, exist_ok=True)
    units_file = work / f"{name}_units.json"
    write_json(units_file, {"what": "Every cell of every unit of the report-only run with the rescaled demand.", "units": result["units"]})

    summary = result["summary"]
    report = {
        "schema": "floodguard.uncertainty_ensemble_rescaled_demand_report.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": str(found.record["source_timestamp"]),
        "source_timestamps": {"flood_input": str(found.record["source_timestamp"]), "population_year_represented": 2020,
                              "population_rescaled_to_year": 2024, "age_counts": found.age_read.get("source_timestamp")},
        "confidence_class": "low",
        "confidence_basis": runner.CONFIDENCE_BASIS,
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "The uncertainty ensemble of the case over the 180 cells of the public facility set: the 90 cells of the WorldPop 2020 demand and the 90 cells of the 2024-rescaled demand. Report-only.",
        "not_of_record": "This is not the registered run of plan task E10. The registered receipt, the run register and the published result file are unchanged; the published file still says that the stability of its classes is not evaluated. Putting a status on a published class needs a registered run and a new publication.",
        "case_id": arguments.case, "frame_set": arguments.frame, "level": runner.LEVEL,
        "protocol_sha256": found.hashes,
        "rescaled_demand": {**rescale_record,
                            "residents_by_unit": {unit_id: {"worldpop_2020": round(found.counted.residents.get(unit_id, 0.0), 3),
                                                            RESCALED: round(units_24.get(unit_id, 0.0), 3)} for unit_id in sorted(found.unit_ids)}},
        "levels_not_run": [item.as_record() for item in not_run],
        "checks": {
            "default_cell_against_the_e8_rows": {"result": "PASS", "rows_sha256": digest},
            "cells_of_the_2020_demand_against_the_registered_run": {
                "result": "PASS", "unit_cells_compared": compared, "what": "The planning score and the class of every unit in every cell of the 2020 demand are those of the registered run.",
                "registered_receipt": {"path": receipt_path.relative_to(ROOT).as_posix(), "sha256": e8_builder.sha256_file(receipt_path)}},
            "as_provided_runs_against_the_e5_table": as_provided,
            "measurements_2020": {key: value for key, value in checks_20.items() if isinstance(value, (bool, int, float))},
            "measurements_rescaled": checks_24,
        },
        "summary": {key: summary[key] for key in ("units", "core_cells_per_lane", "cells_run", "cells_not_run", "cells_not_run_by_reason",
                                                 "cells_of_the_protocol_set_for_retention", "unit_cells_run", "unit_cells_with_a_result",
                                                 "unit_cells_failed", "reference_class_counts", "class_counts_over_every_unit_cell",
                                                 "headline_status_counts") if key in summary},
        "units": [unit_record(unit) for unit in result["units"]],
        "units_file_outside_git": {"name": units_file.name, "sha256": e8_builder.sha256_file(units_file)},
        "credits": ["UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard; the figures derived from it are shared under CC BY-SA 4.0.",
                    "Residents: WorldPop 2020 (CC BY 4.0), rescaled to WorldPop 2024 totals. Age counts: WorldPop, DOI 10.5258/SOTON/WP00842 (CC BY 4.0). Modelled, not observed.",
                    "Roads © OpenStreetMap contributors (ODbL 1.0)."],
        "assumptions": [*demand_rescale.RULES,
                        "Travel times do not depend on the demand: the nine access runs are the same for both demands, and only the resident counts of the cells differ.",
                        "The age counts of a unit, and so its vulnerability component, are the same for both demands.",
                        "A closure is a modelled assumption of closure rule v1, not an observed closure."],
        "limits": ["Report-only: not a registered run of the protocol. Its rules for the rescale are the agent's reading of the owners' choice (decision log R38).",
                   "The two facility sets that add shelters are still not run; they are not part of the set a public result is judged on.",
                   "The confidence of a unit is that of the registered task E8 run and uses no ensemble output.",
                   "Planning guidance only. Class E never means safe."],
    }
    write_json(result_path, report)
    print(json.dumps(report["summary"]))
    for unit in report["units"]:
        headline = unit["headline_stability"]
        print(unit["unit_id"], unit["unit_name_en"], unit["reference_cell"]["action_class"], unit["class_counts"], headline["status"], headline.get("class_retention"), flush=True)


if __name__ == "__main__":
    main()
