"""The September 2024 pass at Mae Sai, read again with a dry-season baseline and put through the road and access chain.

The runs of record read the Sentinel-1 pass of 15 September 2024 against the pass of 3 September, a wet-season
image, and saw little. Work package 3 showed that the image taken as "before" decides what a change rule sees.
This script reads the same pass again, three ways, against the median of three dry-season passes:

* the detector frozen in the detection-improvement work;
* the simple threshold on VH backscatter;
* the fixed UN-SPIDER rule with the dry-season median as its image before.

Each reading becomes a flood extent inside the eight tambons and goes through closure rule v1 and the access
difference exactly as the flood inputs of work package 2 did. The question: does Ko Chang still lose its roads
when the water comes from our own reading of the radar?

Report-only, and unchecked: there is no dated reference for September 2024, so nothing here says whether a
reading is right. No FPPS and no A-E class is computed, and nothing here is an official warning.

Example::

    python scripts/build_september_reread.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
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

from floodguard import access_diff, flood_inputs  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import radar_flood_classifier as rfc  # noqa: E402

OUTPUT = "outputs/september_reread/mae_sai_20240915_v1.json"
COMPARISON = "outputs/flood_input_comparison/mae_sai_v1.json"
FREEZE = "outputs/radar_detection_improvement/freeze_v1.json"
SOURCE_TIMESTAMP = "Sentinel-1 2024-09-15T23:16:14Z; dry-season passes of 24 February, 7 March and 12 April 2024"
KO_CHANG = "TH570903"


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


improve = load_script("build_radar_detection_improvement")
comparison = load_script("build_flood_input_comparison")
dated, t2 = improve.dated, improve.t2
BuildError = t2.BuildError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = Path(arguments.external_root)
    result_path = ROOT / OUTPUT
    if result_path.exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the result exists; a second run needs --replace and --reason")

    import joblib
    import rasterio
    from rasterio.transform import from_origin

    work = external / improve.WORK
    freeze = json.loads((ROOT / FREEZE).read_text(encoding="utf-8"))
    if t2.sha256_file(work / "frozen_detector.joblib") != freeze["frozen_detector"]["file_outside_git"]["sha256"]:
        raise BuildError("frozen_detector.joblib is not the detector the freeze record binds")
    bundle = joblib.load(work / "frozen_detector.joblib")
    areas = improve.area_grids(external)
    grid = areas["mae_sai"]["grid"]
    west, north, rows, columns = grid
    folder = areas["mae_sai"]["folder"]
    after_path, dry_path = work / "s1_mae_sai_20240915.tif", work / "dry_mae_sai.tif"
    with rasterio.open(folder / "worldcover_10m.tif") as source:
        land_cover = source.read(1)
    slope = improve.read_slope(folder, [f"dem_{index}_10m.tif" for index in range(len(dated.DEM_URLS))])
    with rasterio.open(folder / "dated_reference_10m.tif") as source:
        in_district, permanent_water = source.read(2).astype(bool), source.read(3).astype(bool)
    features = improve.strip_baseline_features(after_path, dry_path, slope, land_cover)
    usable = rfc.usable_cells(features, improve.rd.FEATURES_BASELINE) & ~permanent_water

    readings: dict[str, np.ndarray] = {}
    cuts: dict[str, Any] = {}
    readings["frozen_detector"], cuts["frozen_detector"] = improve.apply_detector(bundle, features, usable, slope)
    threshold = {"base": improve.STEP_THRESHOLD, "cleaned": False, "threshold_db": bundle["threshold_db"]}
    readings["simple_threshold"], cuts["simple_threshold"] = improve.apply_detector(threshold, features, usable, slope)
    with rasterio.open(after_path) as source:
        after_vh = source.read(2).astype("float64")
    with rasterio.open(dry_path) as source:
        dry_vh = np.power(10.0, source.read(2).astype("float64") / 10.0)
    candidate, _, _, _ = rc.un_spider_candidate(dry_vh, after_vh, in_frame=np.ones(after_vh.shape, dtype=bool),
                                                permanent_water=permanent_water, slope=slope, cell_m=dated.CELL_M)
    readings["un_spider_with_the_dry_baseline"] = candidate == 1
    cuts["un_spider_with_the_dry_baseline"] = {"rule": "quotient above 1.25, image before = the dry-season median"}
    del features

    # --- the chain of work package 2 ------------------------------------------------------------------------------
    docs = comparison.DOCS
    bad = load_script("build_access_diff")
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    v1a = json.loads((docs / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    services = [rule for rule in access_diff.service_rules(v1a, v1b)
                if rule.publication_level == access_diff.PUBLIC_LEVEL and rule.mode == access_diff.VEHICLE]
    closure = access_diff.closure_arguments(v1b)
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    graphs = {access_diff.VEHICLE: graph}
    units, _summary = bad.read_units(external / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    unit_ids = [unit_id for unit_id, _geometry in units]
    units_metres = {unit_id: flood_inputs.project(geometry, flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS) for unit_id, geometry in units}
    assignment = access_diff.assign_cells(graph.population, units)
    cells = access_diff.demand_cells(graph.population, assignment)
    centres = {row["population_id"]: (float(row["longitude"]), float(row["latitude"])) for row in graph.population}
    baselines = {access_diff.VEHICLE: bad.baseline_runs(graph, services)}
    e1_text = (ROOT / comparison.E1_RECEIPT).read_text(encoding="utf-8")
    water, _water_record = comparison.bound_layer(external / comparison.WATER_FILE, e1_text, "permanent water of the reporting frame")
    transform = from_origin(west, north, dated.CELL_M, dated.CELL_M)
    cell_km2 = dated.CELL_M * dated.CELL_M / 1e6

    results: dict[str, Any] = {}
    for name, flag in readings.items():
        clock = time.perf_counter()
        inside = flag & in_district
        extent, dropped = flood_inputs.drop_small_polygons(inside, transform, minimum_px=rules.raster_minimum_polygon_px,
                                                           connectivity=comparison.RASTER_POLYGON_CONNECTIVITY)
        land = comparison.unit_counts(extent, units_metres, water, cells, centres)
        runs = bad.case_runs("september_reread", name, {"as_provided": extent}, graphs, baselines, services, closure, cells, unit_ids)
        by_level = {}
        for entry in runs["runs"]:
            per_unit, frame = comparison.access_counts(entry)
            vehicle = entry["closure"][access_diff.VEHICLE]
            by_level[entry["closure_level"]] = {"closure": {key: vehicle[key] for key in vehicle if isinstance(vehicle[key], (int, float))},
                                                "frame": frame, "units": per_unit}
        results[name] = {
            "cut": cuts[name],
            "flagged_cells_in_the_district": int(inside.sum()), "flagged_km2_in_the_district": round(int(inside.sum()) * cell_km2, 4),
            "polygons": dropped,
            "frame": {"flooded_land_km2": round(math.fsum(row["flooded_land_km2"] for row in land.values()), 4),
                      "residents": round(math.fsum(row["residents"] for row in land.values()), 3),
                      "residents_inside_extent": round(math.fsum(row["residents_inside_extent"] for row in land.values()), 3)},
            "units": land, "by_closure_level": by_level,
        }
        central = by_level["central"]
        print(f"{name}: {results[name]['flagged_km2_in_the_district']} km2, frame losing every route "
              f"{central['frame']['residents_losing_every_route']}, Ko Chang {central['units'][KO_CHANG]['residents_losing_every_route']} "
              f"of {central['units'][KO_CHANG]['residents_with_a_route_before']}, {time.perf_counter() - clock:.0f} s", flush=True)

    earlier = json.loads((ROOT / COMPARISON).read_text(encoding="utf-8"))
    record = {
        "schema": "floodguard.september_reread.v1",
        "generated_at_utc": t2.now_utc(),
        "source_timestamp": SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Our own reading of one radar pass. There is no dated reference for September 2024: nothing here says whether a reading is right.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "The Sentinel-1 pass of 15 September 2024 at Mae Sai read three ways against a dry-season baseline, each put through closure rule v1 and the access difference. Report-only and unchecked.",
        "label": "Unchecked: no dated reference for September 2024. Modelled closures; not an observation of closed roads.",
        "frozen_detector": freeze["frozen_detector"],
        "freeze_record": {"path": FREEZE, "sha256": t2.sha256_file(ROOT / FREEZE)},
        "radar": {"after": "S1A, relative orbit 135, 2024-09-15T23:16Z (16 September 06:16 in Thailand), terrain-corrected gamma0 at 10 m",
                  "dry_season_passes": sorted(improve.DRY_CHIANG_RAI), "frame": "cells inside the eight tambons of Mae Sai district"},
        "readings": results,
        "table_of_flood_inputs_of_work_package_2": {"path": COMPARISON, "sha256": t2.sha256_file(ROOT / COMPARISON),
                                                   "generated_at_utc": earlier.get("generated_at_utc")},
        "credits": ["Contains modified Copernicus Sentinel data 2024, processed by Microsoft Planetary Computer.",
                    "Roads © OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0). ESA WorldCover 2021 v200 (CC BY 4.0). Copernicus DEM GLO-30."],
        "assumptions": ["A closure is modelled with closure rule v1 from where a reading puts water on a road; a flood intersection does not prove a closure.",
                        "Each reading is cut to the eight tambons, as the radar inputs of work package 2 were.",
                        "The radar passed about four days after the peak of the flood; water that had drained is not in any reading."],
        "limits": ["No dated reference exists for September 2024. The readings cannot be scored.",
                   "The detector was developed on October 2024 residual water and on a lowland tile of July 2025.",
                   "C-band radar does not see water between buildings or under trees: Mae Sai town is where it sees least.",
                   "No component, no planning score and no class is computed."],
    }
    t2.write_json(result_path, record)


if __name__ == "__main__":
    main()
