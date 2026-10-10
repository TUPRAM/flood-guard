"""The age comparison with the registered age mix of each tambon, over the 180 cells of the ensemble. Report-only.

``scripts/build_equity_registration_check.py`` gave every tambon its registered age mix (DOPA, December 2024) and
compared the age groups at three closure levels with the 2020 demand. This script does the same in every cell of
the public facility set: three flood levels, three closure levels and two demands, 18 different counts that each
stand for 10 cells, and applies the rule of protocol v1a with the smallest size of decision log R41.

It makes no access run: the residents of each tambon who had a hospital within 30 minutes and who lose it come from
the cache of ``scripts/build_cell_outcomes.py``, which is checked against the runs of record. Everyone in a tambon
is given the loss rate of the tambon, so a gap can only come from differences between the eight tambons. The
registered ages cover Thai nationals named in a house register only. No tambon is ranked by its age mix, and
nothing here is an official warning.

Example::

    python scripts/build_equity_registration_ensemble.py --external-data <external data root> --extract <folder>/mae_sai_rows_5_year_bands.txt
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

from floodguard import equity_by_age as eba  # noqa: E402

CACHE_RECEIPT = "outputs/cell_outcomes/se1_mae_sai_v1_receipt.json"
FIRST_CHECK = "outputs/equity_by_age/se1_mae_sai_registration_check_v1.json"
OUTPUT = "outputs/equity_by_age/se1_mae_sai_registration_ensemble_v1.json"
EXTERNAL_LABEL = "<external_data_workspace>"
HOSPITAL_MINUTES = 30
CELLS_PER_COUNT = 10
VINTAGES = {"worldpop_2020": "residents_worldpop_2020", "rescaled_2024": "residents_rescaled_2024"}


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
    """The cache or the extract is not what the comparison needs."""


def spread(values: list[float | None]) -> dict[str, Any] | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return {"lowest": round(min(known), 6), "median": round(float(np.median(known)), 6), "highest": round(max(known), 6)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    parser.add_argument("--extract", type=Path, required=True)
    arguments = parser.parse_args()
    check = load_script("build_equity_registration_check")
    registered = check.read_extract(arguments.extract)
    first = json.loads((ROOT / FIRST_CHECK).read_text(encoding="utf-8"))
    if hashlib.sha256(arguments.extract.read_bytes()).hexdigest() != first["source"]["extract_outside_git_sha256"]:
        raise BuildError("the extract is not the one the first registration check was made from")
    receipt = json.loads((ROOT / CACHE_RECEIPT).read_text(encoding="utf-8"))
    cache_path = arguments.external_data / receipt["cache_outside_git"]["path"][len(EXTERNAL_LABEL) + 1:]
    if hashlib.sha256(cache_path.read_bytes()).hexdigest() != receipt["cache_outside_git"]["sha256"]:
        raise BuildError("the cache is not the file its receipt binds")
    cache = np.load(cache_path)
    unit_of = cache["unit_id"]
    had = cache["connected"] & (cache["hospital_before"] <= HOSPITAL_MINUTES)
    shares = {}
    for unit, ages in registered.items():
        with_an_age = check.with_an_age(ages)
        child, older = ages["children_0_14"] / with_an_age, ages["older_60_plus"] / with_an_age
        shares[unit] = {"children_0_14": child, "15_plus": 1 - child, "older_60_plus": older, "under_60": 1 - older}

    counts = []
    for number, run in enumerate(str(name) for name in cache["runs"]):
        lost = had & ~(cache["hospital_after"][number] <= HOSPITAL_MINUTES)
        for vintage, key in VINTAGES.items():
            people = cache[key]
            base = {name: 0.0 for name in ("children_0_14", "15_plus", "older_60_plus", "under_60")}
            gone = dict(base)
            for unit, mix in shares.items():
                here = unit_of == unit
                for name, share in mix.items():
                    base[name] += share * float(people[here & had].sum())
                    gone[name] += share * float(people[here & lost].sum())
            counts.append({
                "flood_input_single_state": run.split("|")[0], "passability": run.split("|")[1], "population_vintage": vintage,
                "stands_for_cells": CELLS_PER_COUNT,
                "loses_a_hospital_within_30_minutes": {comparison: eba.compare(base[group], gone[group], base[others], gone[others])
                                                       for comparison, (group, others) in eba.COMPARISONS.items()}})
    if len(counts) != 18:
        raise BuildError("the cache does not hold nine runs")
    # The three counts of the first check (flood level as provided, 2020 demand) must come out the same.
    for count in counts:
        if count["flood_input_single_state"] == "as_provided" and count["population_vintage"] == "worldpop_2020":
            stated = first["loses_a_hospital_within_30_minutes"][count["passability"]]
            for comparison in eba.COMPARISONS:
                if abs(count["loses_a_hospital_within_30_minutes"][comparison]["difference_of_rates"] - stated[comparison]["difference_of_rates"]) > 2e-6:
                    raise BuildError(f"{count['passability']}, {comparison}: the difference is not the one of the first registration check")

    def read(comparison: str, field: str, vintage: str | None = None) -> list[float | None]:
        return [count["loses_a_hospital_within_30_minutes"][comparison][field] for count in counts
                if vintage is None or count["population_vintage"] == vintage]

    summary = {comparison: {
        "rule_with_the_smallest_size": eba.gap_statement(
            [value for value in read(comparison, "difference_of_rates") for _cell in range(CELLS_PER_COUNT)], min_abs_difference=eba.MIN_GAP_SHARE),
        "difference_of_rates": spread(read(comparison, "difference_of_rates")),
        "ratio_of_rates": spread(read(comparison, "ratio_of_rates")),
        "by_demand": {vintage: {"difference_of_rates": spread(read(comparison, "difference_of_rates", vintage)),
                                "ratio_of_rates": spread(read(comparison, "ratio_of_rates", vintage))} for vintage in VINTAGES},
    } for comparison in eba.COMPARISONS}
    result = {
        "schema": "floodguard.equity_registration_ensemble.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": "flood layer 2024-08-01/2024-10-12; registration counts of December 2024; residents of 2020, in half the cells rescaled to 2024 totals",
        "confidence_class": "low",
        "confidence_basis": first["confidence_basis"],
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "The age comparison of case SE1 with the registered age mix of each tambon, in every cell of the public facility set of the uncertainty ensemble. Report-only.",
        "ensemble": {"cells": len(counts) * CELLS_PER_COUNT, "different_counts": len(counts),
                     "why": "The anchors and the weights change a score, not a count of residents: each count of a flood level, a closure level and a demand stands for 10 cells."},
        "rule": {"of_the_protocol": "bounds that exclude zero and at least 60 percent sign retention across the ensemble",
                 "smallest_size_share": eba.MIN_GAP_SHARE, "smallest_size_decided_in": "decision log R41"},
        "source": first["source"],
        "age_mix_by_tambon": first["age_mix_by_tambon"],
        "made_from": {"cache_receipt": {"path": CACHE_RECEIPT, "sha256": hashlib.sha256((ROOT / CACHE_RECEIPT).read_bytes()).hexdigest()},
                      "first_registration_check": {"path": FIRST_CHECK, "sha256": hashlib.sha256((ROOT / FIRST_CHECK).read_bytes()).hexdigest()}},
        "checks": {"the_three_counts_of_the_first_check_come_out_the_same": True},
        "loses_a_hospital_within_30_minutes": summary,
        "counts": counts,
        "assumptions": first["assumptions"],
        "limits": ["Registered is not resident: people are registered where their house register is, not where they stay.",
                   "About two registered residents in five in this district are not Thai nationals and have no age in the source.",
                   "Everyone in a tambon is given the loss rate of the tambon: the comparison cannot see a difference inside a tambon.",
                   "The lowest and the highest of 18 counts of a scenario are not a statistical interval.",
                   "No tambon is ranked by its age mix. Figures are for the district; they say nothing of what the people of a place can or cannot do."],
    }
    (ROOT / OUTPUT).write_bytes((json.dumps(result, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    for comparison, block in summary.items():
        print(comparison, block["rule_with_the_smallest_size"]["may_state_a_gap"], block["difference_of_rates"], block["ratio_of_rates"], block["by_demand"])


if __name__ == "__main__":
    main()
