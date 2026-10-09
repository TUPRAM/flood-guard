"""Access loss by age group for case SE1: the two comparisons of the protocol, at the three closure levels.

For every demand cell the script computes, as plan task E5 does, whether its residents had a hospital within
30 minutes and a road route before the flood, and whether they keep them in the season-layer scenario. It
reproduces the committed counts of case SE1 for every tambon and level before it writes anything. It then splits
each cell's residents by the modelled age shares of the 1 km age cell they lie in, and compares the loss rates of
residents of 60 and over with those under 60, and of children of 0 to 14 with residents of 15 and over.

Report-only. The three runs are the three closure levels on the layer as provided; they are not the ensemble the
protocol asks for before a gap may be stated, and the output says so. The age counts are modelled, not observed.
No FPPS and no A-E class is computed, and nothing here is an official warning.

Example::

    python scripts/build_equity_by_age.py --external-root <external-data-root> --age-dir <folder of the age rasters>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, closure_rules, flood_inputs  # noqa: E402
from floodguard import equity_by_age as eba  # noqa: E402
from floodguard.evidence_age_surface import AGE_BANDS, CHILD_BANDS, OLDER_BANDS  # noqa: E402

OUTPUT = "outputs/equity_by_age/se1_mae_sai_v1.json"
HOSPITAL_MINUTES = 30


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


def age_shares(age_dir: Path, manifest_sha256: str, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """The share of children (0 to 14) and of residents of 60 and over in the 1 km age cell of every point."""

    import rasterio

    anchors = load_script("build_national_vulnerability_anchors")
    manifest, paths, _hashes = anchors.check_age_sources(age_dir, manifest_sha256)
    total = np.zeros(lon.size)
    children = np.zeros(lon.size)
    older = np.zeros(lon.size)
    valid = np.ones(lon.size, dtype=bool)
    for band in AGE_BANDS:
        with rasterio.open(paths[band]) as source:
            values = np.array([value[0] for value in source.sample(zip(lon.tolist(), lat.tolist()))], dtype="float64")
            nodata = source.nodata
        good = np.isfinite(values) & (values >= 0) & ((values != nodata) if nodata is not None else True)
        valid &= good
        clean = np.where(good, values, 0.0)
        total += clean
        if band in CHILD_BANDS:
            children += clean
        if band in OLDER_BANDS:
            older += clean
    known = valid & (total > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        child_share = np.where(known, children / total, np.nan)
        older_share = np.where(known, older / total, np.nan)
    return child_share, older_share, known, {"product": manifest.get("product"), "year_represented": manifest.get("year_represented"),
                                              "manifest_sha256": manifest_sha256}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--age-dir", required=True)
    arguments = parser.parse_args()
    external = Path(arguments.external_root)

    bad = sheet.load_script("build_access_diff")
    docs = sheet.DOCS
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    v1a = json.loads((docs / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    units, _summary = bad.read_units(external / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    assignment = access_diff.assign_cells(graph.population, units)
    services = [rule for rule in access_diff.service_rules(v1a, v1b)
                if rule.mode == access_diff.VEHICLE and rule.service in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY)]

    extent_sha = sheet.sha256_file(external / sheet.SEASON_EXTENT)
    if extent_sha not in (ROOT / sheet.E1_RECEIPT).read_text(encoding="utf-8"):
        raise sheet.BuildError("the season extent is not the layer the committed E1 receipt binds")
    cache = external / sheet.WORK / f"edge_intersections_{extent_sha[:16]}.json"
    if not cache.exists():
        raise sheet.BuildError("run scripts/build_ko_chang_road_sheet.py first: it caches the edge intersections")
    intersections = json.loads(cache.read_text(encoding="utf-8"))

    baseline = bad.baseline_runs(graph, services)
    covered = set(baseline[access_diff.HOSPITAL])
    cells = [row for row in graph.population if row["population_id"] in covered and assignment[row["population_id"]]["unit_id"] is not None]
    identifiers = [row["population_id"] for row in cells]
    residents = np.array([float(row["total_population"]) for row in cells])
    unit_of = np.array([assignment[identifier]["unit_id"] for identifier in identifiers])
    lon = np.array([float(row["longitude"]) for row in cells])
    lat = np.array([float(row["latitude"]) for row in cells])
    unit_ids = [unit_id for unit_id, _geometry in units]

    def minutes(run: dict[str, dict[str, float | None]], service: str) -> np.ndarray:
        return np.array([np.nan if run[service][identifier] is None else run[service][identifier] for identifier in identifiers])

    hospital_before = minutes(baseline, access_diff.HOSPITAL)
    entry_before = minutes(baseline, access_diff.MAIN_ROAD_ENTRY)
    had_hospital = hospital_before <= HOSPITAL_MINUTES
    had_route = np.isfinite(hospital_before) | np.isfinite(entry_before)

    child_share, older_share, known, age_source = age_shares(
        Path(arguments.age_dir), v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"], lon, lat)
    # A cell whose 1 km age cell holds no count takes the shares of its tambon's other cells, weighted by residents.
    for unit_id in unit_ids:
        inside = unit_of == unit_id
        fill = inside & ~known
        if fill.any():
            weight = residents[inside & known]
            child_share[fill] = float(np.average(child_share[inside & known], weights=weight))
            older_share[fill] = float(np.average(older_share[inside & known], weights=weight))
    groups = eba.group_counts(residents, child_share, older_share)

    committed = json.loads((ROOT / sheet.E5_TABLE).read_text(encoding="utf-8"))
    levels: dict[str, Any] = {}
    for level in closure_rules.LEVELS:
        edges, _applied = access_diff.flooded_edges(level, graph.edges, intersections, flood_input_id="season_layer", arguments=closure)
        flooded = {rule.service: access_diff.cell_minutes(graph.population, edges, graph.destinations[rule.service],
                                                          baseline_nodes=graph.nodes) for rule in services}
        hospital_after = minutes(flooded, access_diff.HOSPITAL)
        entry_after = minutes(flooded, access_diff.MAIN_ROAD_ENTRY)
        lost_hospital = had_hospital & ~(hospital_after <= HOSPITAL_MINUTES)
        lost_route = had_route & ~(np.isfinite(hospital_after) | np.isfinite(entry_after))
        run = next(entry for entry in committed["runs"] if entry["closure_level"] == level and entry.get("flood_level") == "as_provided")
        for unit_id in unit_ids:
            inside = unit_of == unit_id
            row = next(item for item in run["units"] if item["unit_id"] == unit_id)
            wanted = (row["access"]["hospital"]["thresholds_minutes"][str(HOSPITAL_MINUTES)]["newly_lost_residents"],
                      row["road_criticality_inputs"]["residents_losing_all_routes"])
            got = (float(residents[inside & lost_hospital].sum()), float(residents[inside & lost_route].sum()))
            if any(abs(a - b) > 0.01 for a, b in zip(got, wanted)):
                raise sheet.BuildError(f"level {level}, unit {unit_id}: {got} does not reproduce case SE1 {wanted}")
        levels[level] = {
            "reproduces_case_se1_for_every_tambon": True,
            "whole_frame": {"loses_a_hospital_within_30_minutes": eba.outcome_by_age(groups, had_hospital, lost_hospital),
                            "loses_every_road_route": eba.outcome_by_age(groups, had_route, lost_route)},
            "by_tambon": {unit_id: {
                "loses_a_hospital_within_30_minutes": eba.outcome_by_age(groups, had_hospital, lost_hospital, unit_of == unit_id),
                "loses_every_road_route": eba.outcome_by_age(groups, had_route, lost_route, unit_of == unit_id)} for unit_id in unit_ids},
        }
        frame = levels[level]["whole_frame"]
        print(level, {outcome: {name: (entry["difference_of_rates"], entry["ratio_of_rates"]) for name, entry in block.items()}
                      for outcome, block in frame.items()}, flush=True)

    statements = {
        outcome: {name: eba.gap_statement([levels[level]["whole_frame"][outcome][name]["difference_of_rates"] for level in closure_rules.LEVELS])
                  for name in eba.COMPARISONS}
        for outcome in ("loses_a_hospital_within_30_minutes", "loses_every_road_route")}
    result = {
        "schema": "floodguard.equity_by_age.v1",
        "generated_at_utc": sheet.datetime.now(sheet.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": sheet.SOURCE_TIMESTAMP,
        "source_timestamps": {"flood_input": "2024-08-01/2024-10-12", "population_year_represented": 2020, "age_counts_year_represented": 2024},
        "confidence_class": "low",
        "confidence_basis": "Modelled access on OpenStreetMap roads, modelled residents and modelled age shares at 1 km; closures assumed from an agency season layer that was not checked in the field.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "Access loss by age group for case SE1, at the three levels of closure rule v1 on the season layer as provided. Report-only.",
        "label": "Modelled, not observed. A scenario, not a flood of any day.",
        "not_the_ensemble_of_the_protocol": "The protocol allows a gap sentence only on the ensemble of plan task E10. These are three runs. The rule is applied to them for orientation; the protocol's sentence stays the fixed one until the ensemble is run.",
        "comparisons": {"60_plus_vs_under_60": "residents of 60 and over against residents under 60",
                        "0_14_vs_15_plus": "children of 0 to 14 against residents of 15 and over"},
        "definitions": {"loss_rate": "of the residents of a group who had the access before the flood, the share who lose it",
                        "difference_of_rates": "group loss rate minus the others' loss rate, in share points",
                        "ratio_of_rates": "group loss rate divided by the others'; not given under 50 residents in a group or when both rates are zero"},
        "age_shares": {**age_source, "rule": "every 100 m demand cell takes the age shares of the 1 km age cell its centre lies in",
                       "demand_cells": int(residents.size), "cells_whose_age_cell_holds_no_count": int((~known).sum()),
                       "residents_in_those_cells": round(float(residents[~known].sum()), 1),
                       "filled_with": "the resident-weighted shares of the tambon's other cells",
                       "distinct_child_shares_in_the_frame": int(np.unique(np.round(child_share, 4)).size),
                       "share_of_children_lowest_and_highest": [round(float(child_share.min()), 4), round(float(child_share.max()), 4)],
                       "share_of_60_plus_lowest_and_highest": [round(float(older_share.min()), 4), round(float(older_share.max()), 4)]},
        "closure_levels": levels,
        "rule_applied_to_the_three_runs": statements,
        "credits": ["Age counts: WorldPop (www.worldpop.org), University of Southampton; DOI 10.5258/SOTON/WP00842 (CC BY 4.0). Modelled, not observed.",
                    *json.loads((ROOT / sheet.OUTPUT_DIR / sheet.RESULT_NAME).read_text(encoding="utf-8"))["credits"]],
        "assumptions": [*sheet.ASSUMPTIONS[:2],
                        "Residents are WorldPop 2020 counts on 100 m cells; the age shares are WorldPop 2024 on 1 km cells. Everyone in a 1 km cell is given that cell's age mix.",
                        "A cell's residents share one outcome: within a cell, age groups cannot differ in access."],
        "limits": ["The age mix varies only between 1 km cells. A gap can arise only where cells with different age mixes have different outcomes.",
                   "Four of the eight tambons take age counts from cells that straddle the national border (decision log R21).",
                   "Three runs at three closure levels, on the layer as provided. Not the ensemble of the protocol.",
                   "Figures are for a tambon or the whole frame. They say nothing of what the people of a place can or cannot do."],
    }
    sheet.write_json(ROOT / OUTPUT, result)
    print(json.dumps(statements, indent=1))
    print(json.dumps(result["age_shares"], indent=1))


if __name__ == "__main__":
    main()
