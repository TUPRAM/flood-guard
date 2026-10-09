"""Access loss by age group over the cells of the uncertainty ensemble: the protocol's rule for a gap sentence.

Protocol v1a (``equity_statement_rule``) allows a sentence about an age-group gap only when, across the ensemble,
the bounds of the difference exclude zero and at least 60 percent of the cells carry the sign of the median.
``scripts/build_equity_by_age.py`` computed the two comparisons at three closure levels and said that those are not
the ensemble. This script computes them in every cell of the public facility set (decision log R40).

Anchors and weights change a score, not a count of residents, so the 180 cells hold 18 different counts: three
flood levels, three closure levels and two demands (WorldPop 2020, and the 2020 counts rescaled to 2024 totals as
decision log R38 reads the formula). Each of the 18 stands for 10 cells.

Report-only. It reads the case through the checks of the registered ensemble builder, and before it writes it
checks that the runs at the flood level as provided reproduce the committed access table for every tambon. The
age shares are modelled on 1 km cells, not observed. Nothing here is an official warning, and a figure is for a
tambon or the whole frame, never for the people of a place.

Example::

    python scripts/build_equity_ensemble.py --external-data <external data root> --age-dir <folder of the age rasters>
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

from floodguard import access_diff, closure_rules, demand_rescale, flood_inputs  # noqa: E402
from floodguard import equity_by_age as eba  # noqa: E402

OUTPUT = "outputs/equity_by_age/se1_mae_sai_ensemble_v1.json"
CASE, FRAME = "SE1", "mae_sai"
HOSPITAL_MINUTES = 30
CELLS_PER_COUNT = 10
OUTCOMES = ("loses_a_hospital_within_30_minutes", "loses_every_road_route")
VINTAGES = ("worldpop_2020", demand_rescale.RESCALED_LEVEL)


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))  # LF bytes


def spread(values: list[float | None]) -> dict[str, Any] | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return {"lowest": round(min(known), 6), "median": round(float(np.median(known)), 6), "highest": round(max(known), 6),
            "counts_with_a_value": len(known)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--age-dir", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--reason", default="")
    arguments = parser.parse_args()
    external = arguments.external_data
    if (ROOT / OUTPUT).exists() and not (arguments.replace and arguments.reason):
        raise BuildError("the record exists; a second run needs --replace and --reason")

    runner = load_script("build_uncertainty_ensemble")
    side = load_script("build_ensemble_rescaled_demand")
    by_age = load_script("build_equity_by_age")
    e5_builder = runner.e5_builder
    frame_set = runner.FRAME_SETS[FRAME]
    found = runner.prepare(CASE, frame_set, external, external / runner.BOUNDARY_RELATIVE_PATH)
    v1a = json.loads(found.v1a_path.read_text(encoding="utf-8"))
    v1b = json.loads(found.v1b_path.read_text(encoding="utf-8"))
    registered = json.loads(runner.receipt_path_for(CASE, frame_set).read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    graph = found.graph
    services = [rule for rule in access_diff.service_rules(v1a, v1b)
                if rule.mode == access_diff.VEHICLE and rule.service in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY)]
    rescaled, rescale_record = side.rescaled_residents(found, external, arguments.age_dir, v1b, registered)

    baseline = e5_builder.baseline_runs(graph, services)
    covered = set(baseline[access_diff.HOSPITAL])
    position = {row["population_id"]: row for row in graph.population}
    cells = [cell for cell in found.counted.cells if cell["unit_id"] is not None and cell["population_id"] in covered]
    identifiers = [cell["population_id"] for cell in cells]
    unit_of = np.array([str(cell["unit_id"]) for cell in cells])
    unit_ids = sorted(found.unit_ids)
    lon = np.array([float(position[identifier]["longitude"]) for identifier in identifiers])
    lat = np.array([float(position[identifier]["latitude"]) for identifier in identifiers])
    residents = {"worldpop_2020": np.array([float(cell["residents"]) for cell in cells]),
                 demand_rescale.RESCALED_LEVEL: np.array([rescaled[str(identifier)] for identifier in identifiers])}

    def minutes(run: dict[str, dict[str, float | None]], service: str) -> np.ndarray:
        return np.array([np.nan if run[service][identifier] is None else run[service][identifier] for identifier in identifiers])

    hospital_before = minutes(baseline, access_diff.HOSPITAL)
    entry_before = minutes(baseline, access_diff.MAIN_ROAD_ENTRY)
    had_hospital = hospital_before <= HOSPITAL_MINUTES
    had_route = np.isfinite(hospital_before) | np.isfinite(entry_before)

    child_share, older_share, known, age_source = by_age.age_shares(
        arguments.age_dir, v1b["national_vulnerability_anchors"]["inputs"]["age_rasters"]["manifest_sha256"], lon, lat)
    # A cell whose 1 km age cell holds no count takes the shares of its tambon's other cells, weighted by 2020 residents.
    for unit_id in unit_ids:
        inside = unit_of == unit_id
        fill = inside & ~known
        if fill.any():
            weight = residents["worldpop_2020"][inside & known]
            child_share[fill] = float(np.average(child_share[inside & known], weights=weight))
            older_share[fill] = float(np.average(older_share[inside & known], weights=weight))
    groups = {vintage: eba.group_counts(residents[vintage], child_share, older_share) for vintage in VINTAGES}

    committed = {(run["flood_level"], run["closure_level"]): run for run in found.access_table["runs"]}
    counts: list[dict[str, Any]] = []
    clock = time.perf_counter()
    for flood_level, extent_metres in found.closure_extents.items():
        extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
        intersections = closure_rules.edge_intersections(graph.edges, graph.node_coordinates, extent)
        for level in closure_rules.LEVELS:
            edges, _applied = access_diff.flooded_edges(level, graph.edges, intersections,
                                                        flood_input_id=str(found.record["input_id"]), arguments=closure)
            flooded = {rule.service: access_diff.cell_minutes(graph.population, edges, graph.destinations[rule.service],
                                                              baseline_nodes=graph.nodes) for rule in services}
            hospital_after = minutes(flooded, access_diff.HOSPITAL)
            entry_after = minutes(flooded, access_diff.MAIN_ROAD_ENTRY)
            lost_hospital = had_hospital & ~(hospital_after <= HOSPITAL_MINUTES)
            lost_route = had_route & ~(np.isfinite(hospital_after) | np.isfinite(entry_after))
            stated = committed.get((flood_level, level))
            if stated is not None:  # the committed access table holds the flood level as provided
                rows = {str(row["unit_id"]): row for row in stated["units"]}
                for unit_id in unit_ids:
                    inside = unit_of == unit_id
                    wanted = (rows[unit_id]["access"]["hospital"]["thresholds_minutes"][str(HOSPITAL_MINUTES)]["newly_lost_residents"],
                              rows[unit_id]["road_criticality_inputs"]["residents_losing_all_routes"])
                    got = (float(residents["worldpop_2020"][inside & lost_hospital].sum()),
                           float(residents["worldpop_2020"][inside & lost_route].sum()))
                    if any(abs(a - b) > 0.01 for a, b in zip(got, wanted)):
                        raise BuildError(f"{flood_level}/{level}, unit {unit_id}: {got} does not reproduce the access table {wanted}")
            for vintage in VINTAGES:
                lost = {OUTCOMES[0]: (had_hospital, lost_hospital), OUTCOMES[1]: (had_route, lost_route)}
                counts.append({
                    "flood_input_single_state": flood_level, "passability": level, "population_vintage": vintage,
                    "stands_for_cells": CELLS_PER_COUNT,
                    "reproduces_the_committed_access_table": True if stated is not None and vintage == "worldpop_2020" else None,
                    "whole_frame": {name: eba.outcome_by_age(groups[vintage], had, gone) for name, (had, gone) in lost.items()},
                    "by_tambon": {unit_id: {name: eba.outcome_by_age(groups[vintage], had, gone, unit_of == unit_id)
                                            for name, (had, gone) in lost.items()} for unit_id in unit_ids},
                })
            print(flood_level, level, f"{time.perf_counter() - clock:.0f} s", flush=True)
    checked = sum(1 for count in counts if count["reproduces_the_committed_access_table"])
    if len(counts) != 18 or checked != len(closure_rules.LEVELS):
        raise BuildError(f"{len(counts)} counts and {checked} checked against the access table; 18 and 3 are expected")

    def statement(values: list[float | None]) -> dict[str, Any]:
        return eba.gap_statement([value for value in values for _cell in range(CELLS_PER_COUNT)])

    def read(block: str, unit_id: str | None, outcome: str, comparison: str, field: str) -> list[float | None]:
        return [(count["whole_frame"] if unit_id is None else count["by_tambon"][unit_id])[outcome][comparison][field] for count in counts]

    def summary(unit_id: str | None) -> dict[str, Any]:
        return {outcome: {comparison: {
            "rule": statement(read("", unit_id, outcome, comparison, "difference_of_rates")),
            "difference_of_rates": spread(read("", unit_id, outcome, comparison, "difference_of_rates")),
            "ratio_of_rates": spread(read("", unit_id, outcome, comparison, "ratio_of_rates")),
            "group_loss_rate": spread(read("", unit_id, outcome, comparison, "group_loss_rate")),
            "others_loss_rate": spread(read("", unit_id, outcome, comparison, "others_loss_rate")),
            "group_residents_who_lose_it": spread(read("", unit_id, outcome, comparison, "group_residents_who_lose_it")),
        } for comparison in eba.COMPARISONS} for outcome in OUTCOMES}

    names = dict(found.names)
    result = {
        "schema": "floodguard.equity_by_age_ensemble.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": str(found.record["source_timestamp"]),
        "source_timestamps": {"flood_input": str(found.record["source_timestamp"]), "population_year_represented": 2020,
                              "population_rescaled_to_year": 2024, "age_counts_year_represented": age_source.get("year_represented")},
        "confidence_class": "low",
        "confidence_basis": "Modelled access on OpenStreetMap roads, modelled residents and modelled age shares at 1 km; closures assumed from an agency season layer that was not checked in the field.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "Access loss by age group for case SE1 in every cell of the public facility set of the uncertainty ensemble, with the protocol's rule for a gap sentence applied. Report-only.",
        "label": "Modelled, not observed. A scenario, not a flood of any day.",
        "ensemble": {"cells": len(counts) * CELLS_PER_COUNT, "different_counts": len(counts),
                     "why": "The anchors and the weights change a score, not a count of residents: each count of a flood level, a closure level and a demand stands for 10 cells.",
                     "not_run": "The 360 cells of the two facility sets that add shelters, as in the report-only ensemble run (decision log R38)."},
        "rule": {"source": "planning_protocol_v1a.json /equity_statement_rule",
                 "gap_sentence_requires": "bounds that exclude zero and at least 60 percent sign retention across the ensemble",
                 "otherwise": eba.FIXED_SENTENCE},
        "comparisons": {"60_plus_vs_under_60": "residents of 60 and over against residents under 60",
                        "0_14_vs_15_plus": "children of 0 to 14 against residents of 15 and over"},
        "definitions": {"loss_rate": "of the residents of a group who had the access before the flood, the share who lose it",
                        "difference_of_rates": "group loss rate minus the others' loss rate, in share points",
                        "ratio_of_rates": "group loss rate divided by the others'; not given under 50 residents in a group or when both rates are zero"},
        "age_shares": {**age_source, "rule": "every 100 m demand cell takes the age shares of the 1 km age cell its centre lies in",
                       "demand_cells": int(unit_of.size), "cells_whose_age_cell_holds_no_count": int((~known).sum()),
                       "filled_with": "the resident-weighted shares of the tambon's other cells",
                       "share_of_children_lowest_and_highest": [round(float(child_share.min()), 4), round(float(child_share.max()), 4)],
                       "share_of_60_plus_lowest_and_highest": [round(float(older_share.min()), 4), round(float(older_share.max()), 4)]},
        "rescaled_demand": {key: rescale_record[key] for key in ("rules", "demand_residents_2020", "demand_residents_rescaled",
                                                                 "demand_residents_kept_at_2020")},
        "checks": {"runs_as_provided_reproduce_the_committed_access_table_for_every_tambon": True, "runs_checked": checked},
        "whole_frame": summary(None),
        "by_tambon": {unit_id: {"unit_name_en": names[unit_id][0], **summary(unit_id)} for unit_id in unit_ids},
        "tambons_where_a_gap_may_be_stated": sorted(
            f"{unit_id}:{outcome}:{comparison}" for unit_id in unit_ids for outcome in OUTCOMES for comparison in eba.COMPARISONS
            if statement(read("", unit_id, outcome, comparison, "difference_of_rates"))["may_state_a_gap"]),
        "counts": [{key: count[key] for key in ("flood_input_single_state", "passability", "population_vintage", "stands_for_cells",
                                               "reproduces_the_committed_access_table", "whole_frame")} for count in counts],
        "credits": ["Age counts: WorldPop (www.worldpop.org), University of Southampton; DOI 10.5258/SOTON/WP00842 (CC BY 4.0). Modelled, not observed.",
                    "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard; the figures derived from it are shared under CC BY-SA 4.0.",
                    "Residents: WorldPop 2020 (CC BY 4.0), in half the cells rescaled to WorldPop 2024 totals. Roads © OpenStreetMap contributors (ODbL 1.0)."],
        "assumptions": ["A closure is a modelled assumption of closure rule v1, not an observed closure.",
                        "Everyone in a 1 km cell is given that cell's age mix, and a cell's residents share one outcome: within a cell, age groups cannot differ in access.",
                        *demand_rescale.RULES],
        "limits": ["The age mix varies only between 1 km cells. A gap can arise only where cells with different age mixes have different outcomes.",
                   "Four of the eight tambons take age counts from cells that straddle the national border (decision log R21).",
                   "Report-only: the ensemble behind it is the report-only run of decision log R38, not a registered run.",
                   "No tambon is ranked by its age mix. Figures are for a tambon or the whole frame; they say nothing of what the people of a place can or cannot do."],
    }
    write_json(ROOT / OUTPUT, result)
    for outcome in OUTCOMES:
        for comparison in eba.COMPARISONS:
            block = result["whole_frame"][outcome][comparison]
            print(outcome, comparison, block["rule"], block["ratio_of_rates"], flush=True)
    print("tambons where a gap may be stated:", result["tambons_where_a_gap_may_be_stated"])


if __name__ == "__main__":
    main()
