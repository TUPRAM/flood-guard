"""Access loss by age group with the age mix of each tambon taken from registration counts. A check, report-only.

The age comparison of the project gives every 100 m cell the age mix of a modelled 1 km grid
(``scripts/build_equity_by_age.py``), and that mix hardly differs between places. The Department of Provincial
Administration (DOPA) publishes registered residents by single year of age for every tambon. This script asks one
question: if every tambon is given its registered age mix, do older residents or children lose hospital access
more often than the others in case SE1?

What it can and cannot say. Everyone in a tambon gets the loss rate of the tambon, so a gap can only come from
differences between the eight tambons. The registration counts by age hold Thai nationals named in a house
register only; in this district about two registered residents in five are not Thai nationals and have no age in
the source. Registered is not resident. The access counts are those of the committed task E5 table (WorldPop 2020
demand, flood layer as provided, three closure levels). Nothing here is an official warning, and no tambon is
ranked by its age mix.

The extract of the source stays outside Git (no licence is stated on the source pages); its SHA-256 is recorded.

Example::

    python scripts/build_equity_registration_check.py --extract <folder>/mae_sai_rows_5_year_bands.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import equity_by_age as eba  # noqa: E402

OUTPUT = "outputs/equity_by_age/se1_mae_sai_registration_check_v1.json"
E5_TABLE = "outputs/planning_v1/e5_access_diff_se1_mae_sai_public_services.json"
SOURCE_URL = "https://stat.bora.dopa.go.th/new_stat/file/6712/6712cc57.txt"
SOURCE_SHA256 = "c17023ebe6067609e3bc3abe1cc2df8539873effb7e84d3828b3b5e8bd0277dd"
TAMBONS = {"ตำบลแม่สาย": "TH570901", "ตำบลห้วยไคร้": "TH570902", "ตำบลเกาะช้าง": "TH570903", "ตำบลโป่งผา": "TH570904",
           "ตำบลศรีเมืองชุม": "TH570905", "ตำบลเวียงพางคำ": "TH570906", "ตำบลบ้านด้าย": "TH570908", "ตำบลโป่งงาม": "TH570909"}
CHILD_BANDS, OLDER_FROM_BAND = 3, 12  # 0-4, 5-9, 10-14; and 60-64 onward
GROUPS = ("children_0_14", "age_15_59", "older_60_plus")


class BuildError(RuntimeError):
    """The extract or the access table is not what the check needs."""


def read_extract(path: Path) -> dict[str, dict[str, float]]:
    """Registered residents of each tambon by age group: the district-office row plus the rows of the municipal offices."""

    totals = {unit: {**{group: 0.0 for group in GROUPS}, "not_thai_nationals": 0.0, "registered": 0.0} for unit in TAMBONS.values()}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        _number, _office, name, males, females, rest = (part.strip() for part in line.split(";"))
        if name not in TAMBONS:
            continue  # the district row
        male = [float(value) for value in males.split()[1:]]
        female = [float(value) for value in females.split()[1:]]
        other = [float(value) for value in rest.split()[1:]]
        if len(male) != 21 or len(female) != 21 or len(other) != 15:
            raise BuildError(f"the row of {name} does not hold 21 bands for each sex and 15 further fields")
        both = [m + f for m, f in zip(male, female)]
        entry = totals[TAMBONS[name]]
        entry["children_0_14"] += sum(both[:CHILD_BANDS])
        entry["age_15_59"] += sum(both[CHILD_BANDS:OLDER_FROM_BAND])
        entry["older_60_plus"] += sum(both[OLDER_FROM_BAND:])
        entry["not_thai_nationals"] += other[8]
        entry["registered"] += other[14]
    if any(entry["registered"] == 0 for entry in totals.values()):
        raise BuildError("a tambon has no row in the extract")
    return totals


def with_an_age(entry: dict[str, float]) -> float:
    return sum(entry[group] for group in GROUPS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--extract", type=Path, required=True)
    arguments = parser.parse_args()
    registered = read_extract(arguments.extract)
    table = json.loads((ROOT / E5_TABLE).read_text(encoding="utf-8"))
    readings = {}
    for run in table["runs"]:
        if run["flood_level"] != "as_provided":
            continue
        base = {name: 0.0 for name in ("children_0_14", "15_plus", "older_60_plus", "under_60")}
        lost = dict(base)
        for row in run["units"]:
            counts = row["access"]["hospital"]["thresholds_minutes"]["30"]
            ages = registered[str(row["unit_id"])]
            shares = {"children_0_14": ages["children_0_14"] / with_an_age(ages), "older_60_plus": ages["older_60_plus"] / with_an_age(ages)}
            shares["15_plus"], shares["under_60"] = 1 - shares["children_0_14"], 1 - shares["older_60_plus"]
            for name, share in shares.items():
                base[name] += share * float(counts["baseline_access_residents"])
                lost[name] += share * float(counts["newly_lost_residents"])
        readings[run["closure_level"]] = {
            comparison: eba.compare(base[group], lost[group], base[others], lost[others])
            for comparison, (group, others) in eba.COMPARISONS.items()}
    if len(readings) != 3:
        raise BuildError("the access table does not hold the three closure levels at the flood level as provided")
    district = {key: sum(entry[key] for entry in registered.values()) for key in (*GROUPS, "not_thai_nationals", "registered")}
    result = {
        "schema": "floodguard.equity_registration_check.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": "flood layer 2024-08-01/2024-10-12; registration counts of December 2024; residents of 2020",
        "confidence_class": "low",
        "confidence_basis": "Modelled access and modelled residents, with the age mix of each tambon taken from registration counts that leave out everyone who is not a Thai national in a house register.",
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "A check of the age comparison of case SE1 with the registered age mix of each tambon in place of the modelled 1 km age grid. Report-only.",
        "source": {"publisher": "Department of Provincial Administration (DOPA), Bureau of Registration Administration",
                   "table": "registered population by single year of age, Chiang Rai province, December 2567 (2024)",
                   "url": SOURCE_URL, "source_file_sha256": SOURCE_SHA256,
                   "extract_outside_git_sha256": hashlib.sha256(arguments.extract.read_bytes()).hexdigest(),
                   "licence": "none stated on the source pages that were read; cited as a published official statistic",
                   "ages_cover": "Thai nationals named in a house register only (the source says so)"},
        "registered_in_the_district": {
            "all_registered": district["registered"], "not_thai_nationals_and_without_an_age": district["not_thai_nationals"],
            "with_an_age": with_an_age(district),
            "share_of_children_0_14": round(district["children_0_14"] / with_an_age(district), 4),
            "share_of_60_plus": round(district["older_60_plus"] / with_an_age(district), 4)},
        "age_mix_by_tambon": {unit: {
            "registered": entry["registered"], "not_thai_nationals_and_without_an_age": entry["not_thai_nationals"],
            "share_of_children_0_14": round(entry["children_0_14"] / with_an_age(entry), 4),
            "share_of_60_plus": round(entry["older_60_plus"] / with_an_age(entry), 4),
        } for unit, entry in sorted(registered.items())},
        "how_the_tambons_were_put_together": "A tambon is the row of the district office plus the rows of the municipal registration offices that name it (Mae Sai and Wiang Phang Kham municipalities, Huai Khrai municipality).",
        "access_counts_from": {"path": E5_TABLE, "sha256": hashlib.sha256((ROOT / E5_TABLE).read_bytes()).hexdigest(),
                               "what": "residents with a hospital within 30 minutes before the flood, and those who lose it, per tambon"},
        "loses_a_hospital_within_30_minutes": readings,
        "rule_with_the_smallest_size_of_decision_log_r41": {name: eba.gap_statement(
            [readings[level][name]["difference_of_rates"] for level in readings], min_abs_difference=eba.MIN_GAP_SHARE)
            for name in eba.COMPARISONS},
        "assumptions": ["Everyone in a tambon is given the rate of losing access of the tambon: a gap can only come from differences between tambons.",
                        "The age mix of the registered Thai nationals of a tambon is taken for all its residents.",
                        "A closure is a modelled assumption of closure rule v1, not an observed closure."],
        "limits": ["Registered is not resident: people are registered where their house register is, not where they stay.",
                   "About two registered residents in five in this district are not Thai nationals and have no age in the source.",
                   "Three runs at the flood level as provided with the 2020 demand; not the ensemble.",
                   "No tambon is ranked by its age mix. Figures are for the district; they say nothing of what the people of a place can or cannot do."],
    }
    (ROOT / OUTPUT).write_bytes((json.dumps(result, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({"district": result["registered_in_the_district"], "by_tambon": result["age_mix_by_tambon"]}, indent=1))
    for level, block in readings.items():
        print(level, {name: (entry["group_loss_rate"], entry["others_loss_rate"], entry["difference_of_rates"], entry["ratio_of_rates"]) for name, entry in block.items()})
    print(result["rule_with_the_smallest_size_of_decision_log_r41"])


if __name__ == "__main__":
    main()
