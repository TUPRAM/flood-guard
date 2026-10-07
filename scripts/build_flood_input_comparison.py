"""How the decision inputs of Mae Sai change with the flood input (work package 2).

Plan: ``docs/proposal_execution/flood_input_comparison_plan_v1.md``. The script reads the season layer of product
4009 as plan task E1 wrote it and the three radar candidates of the height-aware run of 4 October 2026, and
computes for each, with the unchanged functions of plan tasks E1, E4 and E5: flooded land, residents inside the
extent, closed road edges and residents who lose access. It then sets each radar input beside the season layer.

It computes counts only: no component, no FPPS, no A-E class. It issues no case and does not touch the rights
registry. Nothing here is an official warning. The layers it reads stay outside Git.

Example::

    python scripts/build_flood_input_comparison.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, flood_inputs  # noqa: E402
from floodguard import flood_input_comparison as fic  # noqa: E402

PLAN = "docs/proposal_execution/flood_input_comparison_plan_v1.md"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = "outputs/flood_input_comparison"
RESULT_NAME = "mae_sai_v1.json"
RECEIPT_NAME = "mae_sai_v1_receipt.json"
PLANNING = Path("proposal_execution") / "planning_v1"
SEASON_FOLDER = PLANNING / "se1_mae_sai" / "e1_flood_input"
WATER_FILE = PLANNING / "mae_sai_frame" / "e1_flood_input" / "permanent_water__reporting_frame.geojson"
RADAR_FOLDER = PLANNING / "o1_mae_sai" / "radar_o1_v1_height_aware_sensitivity"
E1_RECEIPT = "outputs/planning_v1/e1_flood_inputs_mae_sai.json"
E5_TABLE = "outputs/planning_v1/e5_access_diff_se1_mae_sai_public_services.json"
RADAR_RECEIPT = "outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json"
RADAR_TABLE = "outputs/planning_v1/radar_o1_mae_sai_v1.json"
RADAR_ENCODING = {"flood": 1, "not_flood": 0, "no_answer": 255}
RASTER_POLYGON_CONNECTIVITY = 4
SEASON_CORRIDOR, SEASON_FRAME = "season_layer_whole_corridor", "season_layer_in_frame"
RADAR_METHODS = {"un_spider": "UN-SPIDER reproduction", "m1_literal": "M1-literal", "m1_v2": "M1-v2"}
COMPARED_LEVEL = "central"
SOURCE_TIMESTAMP = "2024-08-01/2024-10-12 (season layer); 2024-09-15T23:16:01Z (radar pass)"

ASSUMPTIONS = [
    "A road closure is modelled from a flood extent with closure rule v1: a flood intersection does not prove a closure.",
    "Residents are modelled counts (WorldPop 2020). A resident is inside an extent when the centre of the population cell is.",
    "A radar cell with no answer is not flooded and not dry. It closes no road here.",
    "Radar flood cells are made into polygons with the 4-neighbour rule and polygons under 5 cells are dropped; "
    "protocol v1b gives the 5 cells and not the neighbourhood.",
    "The radar layers are those of the height-aware run, which is not the run of record of plan task A4.",
]
LIMITS = [
    "No input is a reference for another: the season layer covers August to October 2024, a radar candidate one "
    "pass 3.8 days after the modelled peak.",
    "This is not case O1 of protocol v1a. No rights record for the Sentinel-1 data is in the registry, and no run "
    "of plan tasks E1, E5 and E8 was made for a radar candidate.",
    "No component, no FPPS and no A-E class is computed. An own radar candidate that does not meet the skill bar "
    "has low confidence under confidence rule v1, and low confidence gives class E whatever these counts are.",
    "The radar candidates are unqualified own candidates of tier T2. Nothing here was checked against a flood map.",
]


class BuildError(RuntimeError):
    """The comparison cannot be made on these inputs."""


def load_script(name: str) -> Any:
    """Load a script of the repository as a module, registered before it runs (its dataclasses look it up by name)."""

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
    # LF bytes on every platform: the receipt binds this file by SHA-256 (.gitattributes, D-41).
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def bound_layer(path: Path, receipt_text: str, what: str) -> tuple[Any, dict[str, Any]]:
    """Read a layer written by plan task E1 and check that the committed E1 receipt names its SHA-256."""

    digest = sha256_file(path)
    if digest not in receipt_text:
        raise BuildError(f"{path.name} is not a layer the committed E1 receipt binds ({what})")
    geometry, _properties = flood_inputs.decode_layer(path.read_bytes())
    return geometry, {"file": path.name, "sha256": digest, "what": what}


def unit_counts(extent: Any, units_metres: dict[str, Any], water: Any, cells: list[dict[str, Any]],
                centres: dict[str, tuple[float, float]]) -> dict[str, dict[str, float]]:
    """Flooded land outside permanent water and residents inside the extent, for each unit (extent in EPSG:32647)."""

    import shapely

    inside: dict[str, float] = {unit: 0.0 for unit in units_metres}
    residents: dict[str, float] = {unit: 0.0 for unit in units_metres}
    wgs84 = flood_inputs.project(extent, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    assigned = [cell for cell in cells if cell["unit_id"] in units_metres]
    if assigned:
        xs = [centres[cell["population_id"]][0] for cell in assigned]
        ys = [centres[cell["population_id"]][1] for cell in assigned]
        shapely.prepare(wgs84)
        flags = shapely.contains_xy(wgs84, xs, ys) if not wgs84.is_empty else [False] * len(assigned)
        for cell, flag in zip(assigned, flags):
            residents[cell["unit_id"]] += cell["residents"]
            if flag:
                inside[cell["unit_id"]] += cell["residents"]
    rows = {}
    for unit, geometry in units_metres.items():
        areas = flood_inputs.flooded_land_areas(geometry, extent, water)
        land = areas["non_permanent_water_land_area"]
        flooded = areas["flooded_non_permanent_water_land_area"]
        rows[unit] = {
            "land_km2": round(land / 1e6, 4),
            "flooded_land_km2": round(flooded / 1e6, 4),
            "flooded_share_of_land": round(flooded / land, 6) if land else None,
            "residents": round(residents[unit], 3),
            "residents_inside_extent": round(inside[unit], 3),
        }
    return rows


def access_counts(entry: dict[str, Any]) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Pull the counts the plan names out of one run of ``case_runs`` (one closure level)."""

    def of(row: dict[str, Any]) -> dict[str, float]:
        hospital = row["access"][access_diff.HOSPITAL]["thresholds_minutes"]["30"]
        road = row["access"][access_diff.MAIN_ROAD_ENTRY]["thresholds_minutes"]["15"]
        routes = row["road_criticality_inputs"]
        return {
            "residents_with_hospital_within_30_min_before": round(hospital["baseline_access_residents"], 3),
            "residents_newly_losing_hospital_within_30_min": round(hospital["newly_lost_residents"], 3),
            "residents_with_main_road_within_15_min_before": round(road["baseline_access_residents"], 3),
            "residents_newly_losing_main_road_within_15_min": round(road["newly_lost_residents"], 3),
            "residents_with_a_route_before": round(routes["residents_with_baseline_route"], 3),
            "residents_losing_every_route": round(routes["residents_losing_all_routes"], 3),
        }

    table = entry["public_services"] if "public_services" in entry else entry
    units = {row["unit_id"]: of(row) for row in table["units"]}
    return units, of(table["whole_frame"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = Path(arguments.external_root)
    result_path = ROOT / OUTPUT_DIR / RESULT_NAME
    if result_path.exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the result exists; a second run needs --replace and --reason")

    import shapely

    bad = load_script("build_access_diff")
    clock = time.perf_counter()
    rules = flood_inputs.load_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")
    v1a = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    v1b = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    services = [rule for rule in access_diff.service_rules(v1a, v1b)
                if rule.publication_level == access_diff.PUBLIC_LEVEL and rule.mode == access_diff.VEHICLE]
    closure = access_diff.closure_arguments(v1b)
    context, context_record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    graphs = {access_diff.VEHICLE: graph}
    boundaries = external / bad.BOUNDARY_RELATIVE_PATH
    if sha256_file(boundaries) != rules.boundary_file_sha256:
        raise BuildError("the boundary file is not the one protocol v1b names")
    units, _summary = bad.read_units(boundaries, rules.reporting_units)
    unit_ids = [unit_id for unit_id, _geometry in units]
    units_metres = {unit_id: flood_inputs.project(geometry, flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS)
                    for unit_id, geometry in units}
    assignment = access_diff.assign_cells(graph.population, units)
    cells = access_diff.demand_cells(graph.population, assignment)
    centres = {row["population_id"]: (float(row["longitude"]), float(row["latitude"])) for row in graph.population}
    baselines = {access_diff.VEHICLE: bad.baseline_runs(graph, services)}
    print(f"context, units and baseline runs: {time.perf_counter() - clock:.0f} s", flush=True)

    e1_text = (ROOT / E1_RECEIPT).read_text(encoding="utf-8")
    radar_receipt_text = (ROOT / RADAR_RECEIPT).read_text(encoding="utf-8")
    water, water_record = bound_layer(external / WATER_FILE, e1_text, "permanent water of the reporting frame")
    frame_metres = shapely.union_all(list(units_metres.values()))

    extents: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    corridor, record = bound_layer(external / SEASON_FOLDER / "flood_extent__as_provided__routing_context.geojson",
                                   e1_text, "season layer, as provided, routing context")
    extents[SEASON_CORRIDOR] = corridor
    inputs[SEASON_CORRIDOR] = {"kind": "agency_season_layer", "layer": record,
                               "label": "2024 season layer of UNOSAT and GISTDA, whole routing corridor (the SE1 input)"}
    in_frame, record = bound_layer(external / SEASON_FOLDER / "flood_extent__as_provided__reporting_frame.geojson",
                                   e1_text, "season layer, as provided, reporting frame")
    extents[SEASON_FRAME] = in_frame
    inputs[SEASON_FRAME] = {"kind": "agency_season_layer", "layer": record,
                            "label": "2024 season layer of UNOSAT and GISTDA, inside the eight tambons only"}
    for name, label in RADAR_METHODS.items():
        path = external / RADAR_FOLDER / f"{name}_candidate.tif"
        digest = sha256_file(path)
        if digest not in radar_receipt_text:
            raise BuildError(f"{path.name} is not a raster the committed radar receipt binds")
        grid = flood_inputs.read_candidate_raster(path, RADAR_ENCODING)
        extent, dropped = flood_inputs.drop_small_polygons(
            grid["flood"], grid["transform"], minimum_px=rules.raster_minimum_polygon_px, connectivity=RASTER_POLYGON_CONNECTIVITY)
        extents[name] = extent
        answered = int((~grid["no_answer"]).sum())
        inputs[name] = {
            "kind": "own_radar_candidate_tier_t2", "label": f"{label}, height-aware run of 4 October 2026",
            "raster": {"file": path.name, "sha256": digest}, "cell_m": grid["cell_m"],
            "flood_cells": int(grid["flood"].sum()), "polygons": dropped,
            "cells_with_an_answer": answered,
            "answered_share_of_frame": round(answered * grid["cell_m"] ** 2 / float(frame_metres.area), 6),
            "attribution": "Contains modified Copernicus Sentinel data 2024",
        }

    results: dict[str, Any] = {}
    closed_central: dict[str, set[str]] = {}
    for name, extent in extents.items():
        clock = time.perf_counter()
        land = unit_counts(extent, units_metres, water, cells, centres)
        runs = bad.case_runs("comparison", name, {"as_provided": extent}, graphs, baselines, services, closure, cells, unit_ids)
        by_level: dict[str, Any] = {}
        for entry in runs["runs"]:
            level = entry["closure_level"]
            per_unit, frame = access_counts(entry)
            vehicle = entry["closure"][access_diff.VEHICLE]
            by_level[level] = {
                "closure": {key: vehicle[key] for key in vehicle if isinstance(vehicle[key], (int, float))},
                "frame": frame, "units": per_unit,
            }
            if level == COMPARED_LEVEL:
                wgs84 = flood_inputs.project(extent, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
                intersections = bad.closure_rules.edge_intersections(graph.edges, graph.node_coordinates, wgs84)
                _changed, applied = access_diff.flooded_edges(level, graph.edges, intersections, flood_input_id=name, arguments=closure)
                closed_central[name] = set(applied["closed_edge_ids"])
        results[name] = {
            **inputs[name],
            "closure_basis": f"modelled_from_{name}",
            "frame": {
                "land_km2": round(math.fsum(row["land_km2"] for row in land.values()), 4),
                "flooded_land_km2": round(math.fsum(row["flooded_land_km2"] for row in land.values()), 4),
                "residents": round(math.fsum(row["residents"] for row in land.values()), 3),
                "residents_inside_extent": round(math.fsum(row["residents_inside_extent"] for row in land.values()), 3),
            },
            "units": land,
            "by_closure_level": by_level,
        }
        print(f"{name}: {time.perf_counter() - clock:.0f} s", flush=True)

    # The method check of the plan: the whole-corridor season layer must reproduce the committed SE1 table.
    committed = json.loads((ROOT / E5_TABLE).read_text(encoding="utf-8"))
    reproduction = {"table": E5_TABLE, "sha256": sha256_file(ROOT / E5_TABLE), "levels": {}}
    for entry in committed["runs"]:
        expected_units, expected_frame = access_counts(entry)
        level = entry["closure_level"]
        mine = results[SEASON_CORRIDOR]["by_closure_level"][level]
        same = mine["units"] == expected_units and mine["frame"] == expected_frame
        reproduction["levels"][level] = same
    reproduction["same"] = all(reproduction["levels"].values()) and len(reproduction["levels"]) == 3
    if not reproduction["same"]:
        raise BuildError(f"the whole-corridor run does not reproduce the committed SE1 table: {reproduction['levels']}")

    def comparable(name: str) -> dict[str, dict[str, float]]:
        level = results[name]["by_closure_level"][COMPARED_LEVEL]["units"]
        return {unit: {"flooded_land_km2": results[name]["units"][unit]["flooded_land_km2"],
                       "residents_inside_extent": results[name]["units"][unit]["residents_inside_extent"],
                       "residents_losing_every_route": level[unit]["residents_losing_every_route"]} for unit in unit_ids}

    comparisons = {
        f"{name}_against_{SEASON_FRAME}": fic.compare_inputs(
            comparable(name), comparable(SEASON_FRAME), closed_first=closed_central[name], closed_second=closed_central[SEASON_FRAME])
        for name in RADAR_METHODS
    }
    comparisons[f"{SEASON_FRAME}_against_{SEASON_CORRIDOR}"] = fic.compare_inputs(
        comparable(SEASON_FRAME), comparable(SEASON_CORRIDOR),
        closed_first=closed_central[SEASON_FRAME], closed_second=closed_central[SEASON_CORRIDOR])

    radar_table = json.loads((ROOT / RADAR_TABLE).read_text(encoding="utf-8"))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope = {
        "generated_at_utc": generated, "source_timestamp": SOURCE_TIMESTAMP, "confidence_class": "low",
        "confidence_basis": "Modelled closures on an unvalidated agency layer and on unqualified own radar candidates; "
                            "nothing was checked on the ground.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "plan": {"path": PLAN, "sha256": sha256_file(ROOT / PLAN)},
        "protocol_sha256": flood_inputs.protocol_hashes(rules),
    }
    result = {
        "schema": "floodguard.flood_input_comparison.result.v1", **envelope,
        "what_this_is": "Counts of flooded land, residents and closed road edges in the eight Mae Sai tambons under five "
                        "flood inputs, and figures that set each radar input beside the season layer. Counts only.",
        "not_computed": ["any component of the planning score", "any planning score", "any action class", "case O1 of protocol v1a"],
        "unit_ids": unit_ids,
        "compared_closure_level": COMPARED_LEVEL,
        "raster_polygon_rule": {"minimum_cells": rules.raster_minimum_polygon_px, "connectivity": RASTER_POLYGON_CONNECTIVITY},
        "what_the_confidence_rule_says_of_a_radar_input": {
            "source": RADAR_TABLE,
            "outcome_of_record": radar_table["t2_skill_bar"].get("outcome_of_record"),
            "meaning": "An own radar candidate that does not meet the skill bar of protocol v1a has low confidence, and "
                       "low confidence gives class E (monitor and verify). Class E never means safe.",
        },
        "reproduction_of_the_se1_table": reproduction,
        "inputs": results,
        "comparisons_at_the_central_level": comparisons,
        "credits": [
            "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard: repaired, "
            "projected, clipped, and set against roads and residents. Figures derived from it are shared under CC BY-SA 4.0.",
            "Contains modified Copernicus Sentinel data 2024.",
            "Roads and hospitals © OpenStreetMap contributors (ODbL 1.0).",
            "Residents: WorldPop 2020 (CC BY 4.0). Land cover: ESA WorldCover 2021 v200 (CC BY 4.0).",
        ],
        "assumptions": ASSUMPTIONS, "limits": LIMITS,
    }
    if result_path.exists():
        old = json.loads(result_path.read_text(encoding="utf-8"))
        result["supersedes"] = {"reason": arguments.reason, "generated_at_utc": old.get("generated_at_utc"),
                                "figures_same": {key: old.get(key) == result.get(key) for key in ("inputs", "comparisons_at_the_central_level")}}
    write_json(result_path, result)
    receipt = {
        "schema": "floodguard.flood_input_comparison.receipt.v1", **envelope,
        "inputs": {
            "context_of_record": context_record,
            "boundaries": {"file": boundaries.name, "sha256": rules.boundary_file_sha256},
            "permanent_water": water_record,
            "e1_receipt": {"path": E1_RECEIPT, "sha256": sha256_file(ROOT / E1_RECEIPT)},
            "radar_receipt": {"path": RADAR_RECEIPT, "sha256": sha256_file(ROOT / RADAR_RECEIPT)},
            "radar_table": {"path": RADAR_TABLE, "sha256": sha256_file(ROOT / RADAR_TABLE)},
            "flood_inputs": {name: inputs[name].get("layer") or inputs[name].get("raster") for name in inputs},
        },
        "parameters": {"closure": {"length_thresholds_m": closure["length_thresholds_m"], "strict_delays": closure["strict_delays"]},
                       "services": [rule.as_record() for rule in services]},
        "outputs": {f"{OUTPUT_DIR}/{RESULT_NAME}": {"sha256": sha256_file(result_path)}},
        "libraries": {"python": sys.version.split()[0], "shapely": shapely.__version__},
    }
    write_json(ROOT / OUTPUT_DIR / RECEIPT_NAME, receipt)

    print(json.dumps({"reproduction": reproduction["levels"]}))
    for name in results:
        frame = results[name]["frame"]
        central = results[name]["by_closure_level"][COMPARED_LEVEL]
        print(f"{name:30s} flooded {frame['flooded_land_km2']:8.2f} km2 | inside {frame['residents_inside_extent']:9.0f} | "
              f"closed {len(closed_central[name]):5d} | lose hospital {central['frame']['residents_newly_losing_hospital_within_30_min']:9.0f} | "
              f"lose every route {central['frame']['residents_losing_every_route']:9.0f}")


if __name__ == "__main__":
    try:
        main()
    except BuildError as error:
        raise SystemExit(f"refused: {error}") from error
