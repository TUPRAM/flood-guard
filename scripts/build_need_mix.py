"""The need mix inside each tambon of case SE1, and the same on 500 m squares. Report-only.

A planning class is one letter for a tambon. This script shows what is under it: how many residents of the tambon
lie in the water, how many stay dry and lose every road, how many keep a road and lose the hospital, and how many
are not affected, in the run the published result rests on and across the nine runs of the uncertainty ensemble,
with both population products.

It reads the cache of ``scripts/build_cell_outcomes.py`` (bound by SHA-256) and the published result file, makes no
access run, and checks before it writes that its counts in the published run are the counts the published file
holds for every tambon. **A need type is not a class**: no score, no threshold of class rule v1, no confidence;
nothing published changes. A scenario of the 2024 season layer, not a flood of any day; not an official warning.

Example::

    python scripts/build_need_mix.py --external-data <external data root>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import need_mix as nm  # noqa: E402

CACHE_RECEIPT = "outputs/cell_outcomes/se1_mae_sai_v1_receipt.json"
PUBLISHED = "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json"
OUTPUT = "outputs/need_mix/se1_mae_sai_v1.json"
SQUARES = "outputs/need_mix/se1_mae_sai_squares_500m_v1.json"
EXTERNAL_LABEL = "<external_data_workspace>"
PUBLISHED_RUN = "as_provided|central"
HOSPITAL_MINUTES = 30
SQUARE_M = 500.0
VINTAGES = {"worldpop_2020": "residents_worldpop_2020", "rescaled_2024": "residents_rescaled_2024"}
CREDITS = ["UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed by FloodGuard: laid over modelled residents and roads and counted; "
           "the figures derived from it are shared under CC BY-SA 4.0.",
           "Residents: WorldPop 2020 (CC BY 4.0), in the second demand rescaled to WorldPop 2024 totals. Roads © OpenStreetMap contributors (ODbL 1.0). "
           "Boundaries: HDX Thailand COD-AB."]


class BuildError(RuntimeError):
    """The cache is not the one its receipt binds, or the counts are not those of the published file."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))  # LF bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    arguments = parser.parse_args()
    receipt = json.loads((ROOT / CACHE_RECEIPT).read_text(encoding="utf-8"))
    cache_path = arguments.external_data / receipt["cache_outside_git"]["path"][len(EXTERNAL_LABEL) + 1:]
    if sha256_file(cache_path) != receipt["cache_outside_git"]["sha256"]:
        raise BuildError("the cache is not the file its receipt binds")
    cache = np.load(cache_path)
    unit_of, connected = cache["unit_id"], cache["connected"]
    hospital_before, entry_before = cache["hospital_before"], cache["entry_before"]
    had_route = connected & (np.isfinite(hospital_before) | np.isfinite(entry_before))
    had_hospital = connected & (hospital_before <= HOSPITAL_MINUTES)
    runs = [str(name) for name in cache["runs"]]
    published = json.loads((ROOT / PUBLISHED).read_text(encoding="utf-8"))
    rows = {row["unit_id"]: row for row in published["rows"]}
    unit_ids = sorted(rows)

    def state(run: str) -> tuple[np.ndarray, ...]:
        number = runs.index(run)
        hospital, entry = cache["hospital_after"][number], cache["entry_after"][number]
        return (cache[f"inside_{run.split('|')[0]}"], connected, had_route, had_route & (np.isfinite(hospital) | np.isfinite(entry)),
                had_hospital, had_hospital & (hospital <= HOSPITAL_MINUTES))

    labels = {run: nm.label_cells(*state(run)) for run in runs}

    # --- the counts of the published run must be the counts the published file holds ---------------------------------
    people = cache[VINTAGES["worldpop_2020"]]
    compared = 0
    for unit_id in unit_ids:
        here = unit_of == unit_id
        hidden = nm.overlaps(*state(PUBLISHED_RUN), people, where=here)
        parts = rows[unit_id]["components"]
        hospital = next(item for item in parts["access_gap_0_100"]["services"] if item["service"] == "hospital")
        wanted = (parts["exposure_0_100"]["inputs"]["residents_inside_flood_extent"], parts["exposure_0_100"]["inputs"]["unit_residents"],
                  parts["road_criticality_0_100"]["inputs"]["residents_losing_all_routes"], hospital["newly_lost_residents"])
        got = (float(people[here & state(PUBLISHED_RUN)[0]].sum()), float(people[here].sum()),
               hidden["cut_off_in_the_water_or_dry"], hidden["losing_the_hospital_in_the_water_or_dry"])
        if any(abs(a - b) > 0.06 for a, b in zip(got, wanted)):
            raise BuildError(f"{unit_id}: {got} are not the counts of the published result file {wanted}")
        compared += 4

    def block(where: np.ndarray | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for vintage, key in VINTAGES.items():
            residents = cache[key]
            mixes = {run: nm.mix(labels[run], residents, where) for run in runs}
            result[vintage] = {
                "in_the_published_run": {**mixes[PUBLISHED_RUN], "hidden_by_the_order": nm.overlaps(*state(PUBLISHED_RUN), residents, where)},
                "over_the_nine_runs": nm.mix_range(list(mixes.values())),
            }
        return result

    columns, rows_of_squares = nm.squares(cache["x"], cache["y"], SQUARE_M)
    listed = {vintage: {run: {(item["column"], item["row"]): item for item in nm.by_square(labels[run], cache[key], columns, rows_of_squares)}
                        for run in runs} for vintage, key in VINTAGES.items()}
    square_unit: dict[tuple[int, int], str] = {}
    for key in sorted(set(zip(columns.tolist(), rows_of_squares.tolist()))):
        inside = (columns == key[0]) & (rows_of_squares == key[1])
        names, counts = np.unique(unit_of[inside], return_counts=True)
        square_unit[key] = str(names[int(np.argmax(counts))])
    squares = []
    for key, item in sorted(listed["worldpop_2020"][PUBLISHED_RUN].items()):
        leading = {run: listed["worldpop_2020"][run][key]["leading_type"] for run in runs}
        squares.append({
            "x_min": key[0] * SQUARE_M, "y_min": key[1] * SQUARE_M, "tambon_of_most_cells": square_unit[key],
            "residents": item["residents"], "leading_type": item["leading_type"], "by_type": item["by_type"],
            "leading_type_is_the_same_in_all_nine_runs": len(set(leading.values())) == 1,
            "leading_type_with_the_rescaled_demand": listed["rescaled_2024"][PUBLISHED_RUN][key]["leading_type"],
            "residents_with_the_rescaled_demand": listed["rescaled_2024"][PUBLISHED_RUN][key]["residents"],
        })

    envelope = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": receipt["source_timestamp"], "source_timestamps": receipt["source_timestamps"],
        "confidence_class": "low", "confidence_basis": receipt["confidence_basis"],
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "label": "Modelled, not observed. A scenario of the 2024 season layer, not a flood of any day.",
        "not_a_class": "A need type is not a planning class: it uses no score, no threshold of class rule v1 and no confidence, and it changes no class. The binding class of each tambon is the one of the published result file.",
        "credits": CREDITS,
    }
    result = {
        "schema": "floodguard.need_mix.v1",
        **envelope,
        "what_this_is": "For case SE1: the residents of each tambon by what the scenario does to them, in the run the published result rests on and across the nine runs of the uncertainty ensemble, with both population products. Report-only.",
        "need_types": [{"type": name, "order_of_the_test": number + 1, "what_it_is": nm.WORDS[name], "in_short": nm.ACTION_WORDS[name]}
                       for number, name in enumerate(nm.NEED_TYPES)],
        "published_run": {"flood_input_single_state": "as_provided", "passability": "central", "population_vintage": "worldpop_2020"},
        "runs": [{"flood_input_single_state": run.split("|")[0], "passability": run.split("|")[1]} for run in runs],
        "made_from": {"cache_receipt": {"path": CACHE_RECEIPT, "sha256": sha256_file(ROOT / CACHE_RECEIPT)},
                      "published_result_file": {"path": PUBLISHED, "sha256": sha256_file(ROOT / PUBLISHED)}},
        "checks": {"counts_of_the_published_run_against_the_published_file": {
            "result": "PASS", "values_compared": compared,
            "what": "per tambon: residents, residents inside the flood layer, residents who lose every road route, residents who lose a hospital within 30 minutes"}},
        "district": block(None),
        "by_tambon": {unit_id: {"unit_name_en": rows[unit_id]["unit_name_en"], "unit_name_th": rows[unit_id]["unit_name_th"],
                                "binding_class_v1_of_the_published_file": rows[unit_id]["action_class"], **block(unit_of == unit_id)}
                      for unit_id in unit_ids},
        "squares_file": {"path": SQUARES, "squares": len(squares), "side_m": SQUARE_M},
        "assumptions": ["A cell is in the water when its centre lies inside the flood layer; a resident of a cell in the water is counted there whatever else is true of the cell.",
                        "A closure is a modelled assumption of closure rule v1, not an observed closure.",
                        "Residents are modelled counts on 100 m cells (WorldPop 2020; in the second demand rescaled to 2024 totals).",
                        "The hospital is reached by vehicle within 30 minutes; a road route is a route to any hospital or main-road entry."],
        "limits": ["A need type of a cell or a square says nothing about a household, a building or a person.",
                   "The kinds follow one flood scenario and one road model; nothing was checked on the ground.",
                   "Residents not joined to the road graph are counted as not assessed for access; in the water they are counted in the water.",
                   "Report-only. No published class changes. Class E never means safe: the mix shows residents in the water in tambons of every class."],
    }
    write_json(ROOT / OUTPUT, result)
    write_json(ROOT / SQUARES, {
        "schema": "floodguard.need_mix_squares.v1", **envelope,
        "what_this_is": "The need mix of case SE1 on squares of 500 m, in the run the published result rests on (WorldPop 2020 demand). Report-only.",
        "grid": {"epsg": 32647, "side_m": SQUARE_M, "square": "x_min and y_min are the lower-left corner; a 100 m cell belongs to the square that holds its centre"},
        "need_types": list(nm.NEED_TYPES),
        "made_from": {"need_mix": {"path": OUTPUT, "sha256": sha256_file(ROOT / OUTPUT)}},
        "limits": result["limits"],
        "squares": squares,
    })
    for unit_id in unit_ids:
        entry = result["by_tambon"][unit_id]
        shares = {name: values["share"] for name, values in entry["worldpop_2020"]["in_the_published_run"]["by_type"].items()}
        print(unit_id, entry["unit_name_en"], entry["binding_class_v1_of_the_published_file"], shares, flush=True)
    print("district", {name: values["residents"] for name, values in result["district"]["worldpop_2020"]["in_the_published_run"]["by_type"].items()})
    print("squares", len(squares), "of them with one leading type in all nine runs:", sum(1 for item in squares if item["leading_type_is_the_same_in_all_nine_runs"]))


if __name__ == "__main__":
    main()
