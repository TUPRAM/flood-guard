"""The reported runs of the uncertainty ensemble for the Mae Sai cases (plan task E10).

These tests read the two committed receipts, the receipts of the earlier tasks they stand on and the README of the
output folder. They compute no component, no FPPS and no class. The per-unit results are outside Git (their lineage
is below the public level); one test compares them with the receipts when the external data root is at hand
(``FLOODGUARD_EXTERNAL_DATA``) and is skipped anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import pytest

from floodguard import uncertainty_ensemble as ue
from floodguard.wording_lint import find_violations, json_strings, load_rules, markdown_section

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "planning_v1"
REGISTER = OUTPUTS / "run_register"
DOCS = ROOT / "docs" / "proposal_execution"
CASES = ("SE1", "O2")
RECEIPTS = {case: OUTPUTS / f"e10_uncertainty_ensemble_{case.lower()}_mae_sai.json" for case in CASES}
E8_RECEIPTS = {case: OUTPUTS / f"e8_planning_assessment_{case.lower()}_mae_sai.json" for case in CASES}
E5_RECEIPT = OUTPUTS / "e5_access_diff_mae_sai.json"
EXTERNAL_LABEL = "<external_data_workspace>"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
SECTION_HEADING = "### Plan task E10: the uncertainty ensemble of the Mae Sai cases"
MAE_SAI_UNITS = ["TH570901", "TH570902", "TH570903", "TH570904", "TH570905", "TH570906", "TH570908", "TH570909"]
PRODUCT_4009_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
CLASSES = ("A", "B", "C", "D", "E")
FACILITY_SET_NAME = "corroborated"
"""The name protocol v1b gives its second facility set. The shared lint keeps that word for one claim it refuses (a
season envelope said to support a model); as the identifier of a level in a receipt it is the protocol's own word."""
LEVEL_NAME_PATHS = re.compile(
    r"\$\.parameters\.grid\.axes\[2\]\.(?:levels|levels_as_protocol_v1b_states_them)\[1\]"
    r"|\$\.parameters\.levels_not_run\[0\]\.level")
"""The places of a receipt that hold the name of that facility set as an identifier and nothing else."""
CELL_ID_PATHS = re.compile(r"\$\.cells\.(?:run|not_run\.[a-z0-9_+]+)\[\d+\]")
"""The places of a receipt that hold a cell identifier: six level names joined by a bar."""
QUOTED_CUT_LINE_PATH = "$.parameters.grid.declared_cuts.cut_line_8"
"""The one sentence of protocol v1b with that word that a receipt quotes, with the grid."""
FIRST_RUN_RECEIPTS = {"SE1": "cac28f7352b276c8f550faea0375e0ae19f9a82ce246875e18cc796b58191ee3",
                      "O2": "e59b86c5c68559eeb574142273c9fde1c9221ffda15720b8ad10a76454e869fe"}
"""The SHA-256 of the receipt of the first run of each case (4 October 2026; both are in the Git history, commit b9ecf25)."""
SECOND_RUN_RECEIPTS = {"SE1": "5d432b0b71b6f90e2b65d9d322e95dec2f7b32775aad5a117b1cd5e64217089e",
                       "O2": "270b0c5b024379b76bd4e5bdae5a4e1e98112af65f2e3c9f52e0f14a2f067e95"}
"""The SHA-256 of the receipt of the second run of each case (4 October 2026, after the review; in the Git history, commit 487d29a)."""

pytestmark = pytest.mark.skipif(not all(path.is_file() for path in RECEIPTS.values()),
                                reason="the uncertainty ensemble has not been run on this checkout")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(case: str) -> dict[str, Any]:
    return json.loads(RECEIPTS[case].read_text(encoding="ascii"))


def _files(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    return list(receipt["outputs"]["ensemble"]["files"])


def _section() -> str:
    """The README section of this task: from its heading to the next heading of the same level, and no further."""

    readme = (OUTPUTS / "README.md").read_text(encoding="utf-8")
    assert readme.count(SECTION_HEADING) == 1
    return markdown_section(readme, SECTION_HEADING)


def _short(sha256: str) -> str:
    """A SHA-256 as the README writes it: the first eight and the last four characters."""

    return f"`{sha256[:8]}…{sha256[-4:]}`"


def _classes(counts: dict[str, int]) -> str:
    """Class counts as the README writes them: the classes that appear, each with its count."""

    return ", ".join(f"{name} {counts[name]:,}" for name in (*CLASSES, "no_class") if counts.get(name)) or "none"


@pytest.fixture(scope="module")
def grid() -> ue.EnsembleGrid:
    return ue.load_grid(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")


def test_the_readme_section_of_this_task_ends_where_the_next_section_starts() -> None:
    """A section a later task appends, with a tambon code in it, is not read as part of this one."""

    readme = (OUTPUTS / "README.md").read_text(encoding="utf-8")
    later = readme.rstrip("\n") + "\n\n### Plan task E99: an invented later section\n\nTH570901 in a table of that task.\n"
    assert markdown_section(later, SECTION_HEADING).rstrip() == _section().rstrip()
    assert "TH570901" not in markdown_section(later, SECTION_HEADING) and _section().startswith(SECTION_HEADING)


@pytest.mark.parametrize("case", CASES)
def test_each_receipt_is_registered_names_the_protocols_and_names_no_tambon_beside_a_value(case: str) -> None:
    path = RECEIPTS[case]
    receipt = _receipt(case)
    entry = json.loads((REGISTER / path.name).read_text(encoding="ascii"))
    assert entry == {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}, "every run is registered"
    assert receipt["protocol_sha256"] == {f"planning_protocol_{name}": _sha256(DOCS / f"planning_protocol_{name}.json")
                                          for name in ("v1a", "v1b")}
    assert receipt["status"] == "run_receipt" and receipt["official_warning"] is False
    assert receipt["operational_status"] == "non_operational" and receipt["can_feed_decision_layer"] is False
    assert receipt["plan_task"].startswith("E10:") and "540 cells per lane reported" in receipt["plan_task"]
    parameters = receipt["parameters"]
    assert (parameters["case_id"], parameters["frame_set"], parameters["level"]) == (case, "mae_sai", "public")
    assert parameters["unit_ids"] == MAE_SAI_UNITS and parameters["services"] == ["hospital", "main_road_entry"]
    assert parameters["headline_rule"]["class_retention_min"] == 0.6
    # The tambon codes are in the parameters, and nowhere else: the receipt in Git names no unit beside a value.
    without_the_list = json.loads(json.dumps(receipt))
    del without_the_list["parameters"]["unit_ids"]
    assert not re.search(r"TH\d{6}", json.dumps(without_the_list))
    # Guardrail GR6: the lineage is below the public level, and the per-unit results are outside Git.
    rights = receipt["rights"]
    assert rights["publication_eligibility"] == "local" and rights["written_under_apps_web_public"] is False
    assert rights["lineage_levels"]["e7_age_exposure_table"] == "local"
    declared = rights["figures_of_local_level_layers_in_this_receipt"]
    assert declared["figures"], "the counts of a local lineage are declared"
    # No tambon is named beside a value. That is not the same as holding no value of a single tambon, and the receipt
    # does not say it is: it counts the counts that state the class of one tambon (open point E10-OP10).
    assert "names no unit beside a value" in declared["what"] and "puts no unit beside a value" not in json.dumps(receipt)
    assert "E10-OP10" in declared["for_the_owners"] and "E10-OP10" in declared["what_the_counts_give_away"]
    single = declared["counts_that_state_a_value_of_a_single_unit"]
    by_cell = receipt["result"]["summary"]["class_counts_by_cell"]
    default = by_cell["as_provided|central|public|worldpop_2020|P10_P90|default"]
    alone = sorted(name for name, count in default.items() if count == 1)
    assert single["states_a_value_of_a_single_unit"] is True, "true of both cases, for another reason in each"
    assert single["classes_one_unit_alone_holds_in_the_default_cell"] == alone
    assert single["cells_in_which_such_a_class_has_another_count"] == sum(
        1 for counts in by_cell.values() if any(counts.get(name, 0) != 1 for name in alone))
    assert single["cells_whose_class_counts_differ_from_the_default_cell"] == sum(1 for counts in by_cell.values() if counts != default)
    assert single["cells_in_which_every_unit_has_one_class"] == sum(1 for counts in by_cell.values() if max(counts.values()) == 8)
    assert single == {**receipt["result"]["summary"]["counts_that_state_a_value_of_a_single_unit"], **{
        key: single[key] for key in ("where", "who_can_read_them", "cannot_be_rebuilt_from_committed_files")}}
    if case == "SE1":
        # One tambon alone is class B in the default cell; the count of class B follows it through the 90 cells.
        assert alone == ["B"] and single["cells_in_which_such_a_class_has_another_count"] == 20
        assert single["cells_whose_class_counts_differ_from_the_default_cell"] == 23
        assert single["cells_in_which_every_unit_has_one_class"] == 0 and single["units_with_more_than_one_class_over_the_cells_run"] == 2
    else:
        # All eight tambons are class E in every cell: each count states the class of each tambon.
        assert alone == [] and single["cells_in_which_every_unit_has_one_class"] == 90
        assert single["cells_whose_class_counts_differ_from_the_default_cell"] == 0
    files = _files(receipt)
    assert [item["what"] for item in files] == ["uncertainty_ensemble_units", "licence_notice"]
    assert all(item["path"].startswith(EXTERNAL_LABEL + "/") and item["in_git"] is False for item in files)
    assert all(f"/{case.lower()}_mae_sai/e10_uncertainty_ensemble/" in item["path"] for item in files)
    assert files[0]["units"] == 8 and files[0]["cells_run"] == 90
    public = ROOT / "apps" / "web" / "public"
    assert not list(public.rglob("uncertainty_ensemble_*")) if public.is_dir() else True
    assert receipt["lane_purity"]["result"] == "PASS"
    assert [dict(point) for point in receipt["open_points"]] == [dict(point) for point in ue.OPEN_POINTS]
    assert len(receipt["open_points"]) == 12
    assert receipt["development_reads"]["reads"], "the reads made before the run are listed"
    # The distance of the minus and plus levels is the one protocol v1b states and task E1 wrote its levels with.
    pixel = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))["ensemble_grid"]["core_axes"][0]["one_pixel_m"]
    stated = parameters["one_pixel_m"]
    assert stated["minus"] == stated["plus"] == stated["input_record_of_task_e1"] == pixel["minus"] == pixel["plus"] == 20
    assert parameters["grid"]["one_pixel_m"] == 20 and any("shrunk and grown by 20 m (one pixel" in line for line in receipt["assumptions"])


@pytest.mark.parametrize("case", CASES)
def test_each_receipt_is_a_superseding_run_whose_cells_are_those_of_the_first_run(case: str) -> None:
    """The second runs replaced the first after a review; the third followed the E8 runs of 6 October 2026 (R20).

    No FPPS and no class of a cell changed in either step. The third runs rest on E8 rows whose class_v2 block has
    the format of overlay schema 1.1; this table keeps its own two fields for the secondary class as they were.
    """

    receipt = _receipt(case)
    assert receipt["schema_version"] == "floodguard.uncertainty_ensemble_run_receipt.v2" and receipt["run_kind"] == "superseding_run"
    supersedes = receipt["supersedes"]
    history = receipt["run_history"]
    assert [item["receipt_sha256"] for item in history] == [FIRST_RUN_RECEIPTS[case], SECOND_RUN_RECEIPTS[case]]
    assert supersedes["receipt_sha256"] == SECOND_RUN_RECEIPTS[case] and "decision log R20" in supersedes["reason"]
    assert supersedes["unit_cells_same"] is True, "every FPPS, class, reason code and leave-one-out of every cell is the same"
    assert supersedes["access_unit_rows_same"] is True
    assert supersedes["units_same"] is True and supersedes["result_same"] is True and supersedes["summary_same"] is True
    assert supersedes["unit_record_fields_that_differ"] == [] and supersedes["summary_fields_that_differ"] == []
    assert all(item["unit_cells_same_as_the_run_that_replaced_it"] is True for item in history)
    assert len(receipt["development_reads"]["reads"]) == 1
    assert all(item["copied"] is True and item["path"].startswith(EXTERNAL_LABEL + "/") for item in supersedes["copies_kept_outside_git"])
    assert [item["what"] for item in supersedes["copies_kept_outside_git"]].count("receipt") == 1
    for earlier in history:
        assert _short(earlier["receipt_sha256"]) in _section(), "the README names the receipt of every earlier run"


@pytest.mark.parametrize("case", CASES)
def test_each_receipt_carries_the_licence_the_credit_and_a_change_notice_for_product_4009(case: str) -> None:
    licence = _receipt(case)["licence"]
    e8_licence = json.loads(E8_RECEIPTS[case].read_text(encoding="ascii"))["licence"]
    assert licence["name"] == "CC BY-SA 4.0" and licence["credit"] == PRODUCT_4009_CREDIT
    assert licence["change_notice"].startswith("Changed by FloodGuard") and "In plan task E10" in licence["change_notice"]
    assert "shrunk and grown by 20 m" in licence["change_notice"] and licence["change_notice"].endswith("CC BY-SA 4.0.")
    assert "FloodGuard did not validate it" in licence["standard_sentence"]
    # The block is the one the task E8 receipt carries, carried on by the step of this task.
    carried = {"applies_to", "change_notice", "where_the_values_are"}
    assert {key: value for key, value in licence.items() if key not in carried} == {
        key: value for key, value in e8_licence.items() if key not in carried}
    assert licence["rights_record"]["path"] == "docs/proposal_execution/rights_basis_4009_v1.json"
    assert licence["rights_record"]["sha256"] == _sha256(ROOT / licence["rights_record"]["path"])


@pytest.mark.parametrize("case", CASES)
def test_each_receipt_reports_every_cell_of_the_grid_protocol_v1b_states(case: str, grid: ue.EnsembleGrid) -> None:
    receipt = _receipt(case)
    assert receipt["parameters"]["grid"] == ue.grid_record(grid), "the grid is the one the protocol files in force state"
    every = [ue.cell_id(cell) for cell in ue.cells(grid)]
    cells = receipt["cells"]
    not_run = [identifier for identifiers in cells["not_run"].values() for identifier in identifiers]
    assert len(every) == 540 and sorted([*cells["run"], *not_run]) == sorted(every), "540 cells per lane reported"
    assert len(cells["run"]) == 90 and len(not_run) == 450
    assert all(identifier.split("|")[2:4] == ["public", "worldpop_2020"] for identifier in cells["run"])
    assert {reason: len(identifiers) for reason, identifiers in cells["not_run"].items()} == receipt["result"]["summary"]["cells_not_run_by_reason"]
    assert sorted(len(identifiers) for identifiers in cells["not_run"].values()) == [90, 180, 180]
    levels = receipt["parameters"]["levels_not_run"]
    assert [(item["axis"], item["level"]) for item in levels] == [
        ("facilities", FACILITY_SET_NAME), ("facilities", "all_listed"), ("population_vintage", "rescaled_2024")]
    assert all("not approximated" in item["reason"] and item["open_points"] for item in levels)
    assert receipt["parameters"]["levels_run"]["facilities"] == ["public"]
    assert receipt["parameters"]["levels_run"]["population_vintage"] == ["worldpop_2020"]
    assert receipt["parameters"]["levels_run"]["weights"] == list(grid.axis("weights").levels), "weight presets are never cut"


@pytest.mark.parametrize("case", CASES)
def test_the_access_runs_reproduce_the_e5_table_and_the_default_cell_is_the_e8_rows(case: str) -> None:
    receipt = _receipt(case)
    access = receipt["access_runs"]
    assert [(run["flood_level"], run["closure_level"]) for run in access["runs"]] == [
        (flood, level) for flood in ("minus", "as_provided", "plus") for level in ("strict", "central", "permissive")]
    checks = access["checks"]
    assert checks["as_provided_runs_against_the_e5_table"]["result"] == "PASS"
    assert checks["against_calculate_total_access_all_same"] is True and checks["shorter_routes_in_a_flooded_run"] == 0
    assert checks["residents_gaining_access"] == 0.0 and checks["intersected_edges_not_fewer_at_a_larger_flood_level"] is True
    # The whole-frame counts at the flood level as provided are those the committed E5 receipt holds.
    e5 = json.loads(E5_RECEIPT.read_text(encoding="ascii"))
    stated = {run["closure_level"]: run for run in e5["results"][case]["runs"]}
    for run in access["runs"]:
        if run["flood_level"] != "as_provided":
            continue
        other = stated[run["closure_level"]]
        for key in ("closure", "residents", "access_gap_inputs", "road_criticality_inputs"):
            assert run[key] == other[key], (run["closure_level"], key)
    assert receipt["inputs"]["access_table_as_provided"]["e5_receipt"]["sha256"] == _sha256(E5_RECEIPT)
    # A larger flood level never closes fewer edges at the permissive level, which closes every intersected edge.
    closed = [run["closure"]["vehicle"]["closed_edges"] for run in access["runs"] if run["closure_level"] == "permissive"]
    assert closed == sorted(closed)
    measured = receipt["measurement_checks"]
    assert measured["combinations_measured"] == 9 and measured["default_combination_is_the_measurement_of_task_e8"] is True
    assert measured["residents_and_baseline_counts_same_in_every_access_run"] is True
    # The checks of the flood levels read the measurements that were handed to the ensemble.
    assert measured["each_combination_carries_the_flood_measurements_of_its_own_level"] is True
    assert measured["flooded_land_not_smaller_at_a_larger_flood_level_in_every_unit"] is True
    assert measured["residents_inside_not_fewer_at_a_larger_flood_level_in_every_unit"] is True
    # The default cell: the rows the registered task E8 receipt records, by their SHA-256.
    e8 = json.loads(E8_RECEIPTS[case].read_text(encoding="ascii"))
    check = receipt["result"]["default_cell_against_the_e8_rows"]
    assert check["result"] == "PASS" and check["rows"] == 8 and check["rows_sha256"] == e8["result"]["rows_sha256"]
    assert receipt["inputs"]["e8_run"]["receipt"]["sha256"] == _sha256(E8_RECEIPTS[case])
    assert receipt["inputs"]["e8_run"]["rows_file"]["sha256"] == e8["outputs"]["overlay"]["files"][0]["sha256"]
    assert receipt["lineage_input_sha256"] == e8["lineage_input_sha256"], "the lineage is that of the task E8 run"


@pytest.mark.parametrize("case", CASES)
def test_the_counts_of_each_receipt_add_up_and_no_class_is_headlined(case: str) -> None:
    receipt = _receipt(case)
    result = receipt["result"]
    assert result["computed"] is True and result["not_computed_because"] is None and len(result["units_sha256"]) == 64
    counts = result["summary"]
    assert (counts["units"], counts["core_cells_per_lane"], counts["cells_run"], counts["cells_not_run"]) == (8, 540, 90, 450)
    assert counts["cells_of_the_protocol_set_for_retention"] == 180, "the public facility set of protocol v1b"
    assert counts["unit_cells_run"] == counts["unit_cells_with_a_result"] == 720 and counts["unit_cells_failed"] == 0
    assert counts["cells_run_with_a_failed_unit"] == 0 and counts["unit_cells_with_a_component_not_computed"] == 0
    assert counts["cells_ranked"] == 90 and counts["units_without_a_default_cell_result"] == 0
    by_cell = counts["class_counts_by_cell"]
    assert sorted(by_cell) == sorted(receipt["cells"]["run"]) and all(sum(item.values()) == 8 for item in by_cell.values())
    overall = counts["class_counts_over_every_unit_cell"]
    assert sum(overall.values()) == 720
    assert {name: sum(item.get(name, 0) for item in by_cell.values()) for name in overall} == overall
    # The default cell holds the binding classes of the task E8 run.
    e8 = json.loads(E8_RECEIPTS[case].read_text(encoding="ascii"))["result"]
    e8_counts = (e8["summary"] or e8["rows_as_computed"]["summary"])["binding_class_by_lane_column"]
    column = "SCN" if case == "SE1" else "OBS"
    assert {name: counts["reference_class_counts"][name] for name in CLASSES} == {name: e8_counts[column][name] for name in CLASSES}
    assert by_cell["as_provided|central|public|worldpop_2020|P10_P90|default"] == {
        name: count for name, count in counts["reference_class_counts"].items() if count}
    kept = counts["retention_over_the_cells_run"]
    assert (kept["units_keeping_the_class_in_at_least_the_minimum_share"] + kept["units_keeping_the_class_in_less_than_the_minimum_share"]
            + kept["units_without_a_class_to_keep"]) == 8
    assert kept["units_keeping_the_class_in_every_cell_run"] <= kept["units_keeping_the_class_in_at_least_the_minimum_share"]
    # Guardrail GR8: half of the 180 cells of the protocol's set were not run, so no class is headlined.
    assert counts["headline_status_counts"] == {"not_evaluated": 8, "headline_eligible": 0, "unstable_verify": 0}
    assert sum(counts["outcome_fixed_by_the_bounds_counts"].values()) == 8
    assert counts["outcome_fixed_by_the_bounds_counts"]["at_or_above_the_minimum"] == 0, "90 of 180 cells cannot reach 0.6 alone"
    after_cut = counts["after_declared_cut_line_6"]
    assert after_cut["cells"] == 45 and after_cut["units_at_or_above_the_minimum"] + after_cut["units_below_the_minimum"] == 8
    # Cut line 6 does not say which level of its two axes stays (E10-OP12): the levels of the default cell, and the others.
    assert after_cut["levels_kept"] == {"population_vintage": "worldpop_2020", "vulnerability_anchors": "P10_P90"}
    others = after_cut["other_levels_the_cut_could_keep"]
    assert [tuple(item["levels_kept"].values()) for item in others] == [
        ("worldpop_2020", "P5_P95"), ("rescaled_2024", "P10_P90"), ("rescaled_2024", "P5_P95")]
    assert others[0]["units_at_or_above_the_minimum"] + others[0]["units_below_the_minimum"] == 8
    assert all(item["units_without_a_class_in_every_one_of_those_cells"] == 8 for item in others[1:]), "the 2024 demand was not run"
    # The other reading of the protocol's set (E10-OP11): over the 540 core cells no outcome is fixed either.
    other = counts["other_reading_of_the_protocol_set"]
    assert other["cells"] == 540 and other["outcome_fixed_by_the_bounds_counts"] == {
        "at_or_above_the_minimum": 0, "below_the_minimum": 0, "not_fixed": 8}


def test_the_readme_reports_the_runs_as_the_receipts_hold_them() -> None:
    section = _section()
    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert find_violations(section, rules, "outputs README, plan task E10") == []
    assert not re.search(r"TH\d{6}", section), "the section gives counts for the whole case and names no tambon"
    receipts = {case: _receipt(case) for case in CASES}
    for case, receipt in receipts.items():
        assert f"`{RECEIPTS[case].name}`" in section
        assert _short(_sha256(RECEIPTS[case])) in section and _short(_files(receipt)[0]["sha256"]) in section
        assert receipt["timestamps"]["run_started_at_utc"][11:] in section
        assert _short(receipt["result"]["default_cell_against_the_e8_rows"]["rows_sha256"]) in section
    se1, o2 = (receipts[case]["result"]["summary"] for case in CASES)

    def row(label: str, value: Any) -> str:
        return f"| {label} | {value(se1)} | {value(o2)} |"

    kept = "retention_over_the_cells_run"
    for line in (
        row("Cells of the lane: run / not run", lambda s: f"{s['cells_run']} / {s['cells_not_run']}"),
        row("Tambon-cells with a result / failed", lambda s: f"{s['unit_cells_with_a_result']} / {s['unit_cells_failed']}"),
        row("Classes in the default cell (the rows of task E8)", lambda s: _classes(s["reference_class_counts"])),
        row("Classes over every tambon-cell", lambda s: _classes(s["class_counts_over_every_unit_cell"])),
        row("Tambons that keep the class of the default cell in every cell run", lambda s: s[kept]["units_keeping_the_class_in_every_cell_run"]),
        row("Tambons that keep it in at least 60% of the cells run", lambda s: s[kept]["units_keeping_the_class_in_at_least_the_minimum_share"]),
        row("Tambons that keep it in less than 60% of the cells run", lambda s: s[kept]["units_keeping_the_class_in_less_than_the_minimum_share"]),
        row("Tambons whose FPPS lies on both sides of 35 over the cells run", lambda s: s["units_whose_fpps_lies_on_both_sides_of_the_class_e_threshold"]),
        row("Tambons whose class changes in the default cell when one component is left out",
            lambda s: s["units_whose_class_changes_under_leave_one_component_out_in_the_default_cell"]),
        row("Tambons whose retention over the 180 cells cannot reach 0.6 whatever the cells not run give",
            lambda s: s["outcome_fixed_by_the_bounds_counts"]["below_the_minimum"]),
        row("After declared cut line 6, keeping WorldPop 2020 and P10 / P90 (45 cells): tambons at or above 0.6 / below",
            lambda s: f"{s['after_declared_cut_line_6']['units_at_or_above_the_minimum']} / {s['after_declared_cut_line_6']['units_below_the_minimum']}"),
        row("The same, keeping WorldPop 2020 and P5 / P95 (45 cells)",
            lambda s: (f"{s['after_declared_cut_line_6']['other_levels_the_cut_could_keep'][0]['units_at_or_above_the_minimum']} / "
                       f"{s['after_declared_cut_line_6']['other_levels_the_cut_could_keep'][0]['units_below_the_minimum']}")),
        row("Tambons that keep the class in every one of those 45 cells: P10 / P90 kept; P5 / P95 kept",
            lambda s: (f"{s['after_declared_cut_line_6']['units_keeping_the_class_in_every_one_of_those_cells']}; "
                       f"{s['after_declared_cut_line_6']['other_levels_the_cut_could_keep'][0]['units_keeping_the_class_in_every_one_of_those_cells']}")),
        row("Tambons whose retention over the 540 core cells is fixed by the bounds (the other reading, E10-OP11)",
            lambda s: 8 - s["other_reading_of_the_protocol_set"]["outcome_fixed_by_the_bounds_counts"]["not_fixed"]),
        row("Headline status", lambda s: f"not evaluated for all {s['headline_status_counts']['not_evaluated']}"),
    ):
        assert line in section, line
    # The access runs, as the receipts hold them for the whole frame.
    for case, receipt in receipts.items():
        for run in receipt["access_runs"]["runs"]:
            closure = run["closure"]["vehicle"]
            gap = run["access_gap_inputs"]
            line = (f"| {case}, {run['flood_level'].replace('_', ' ')}, {run['closure_level']} | "
                    f"{closure['intersected_edges']:,} / {closure['closed_edges']:,} / {closure['delayed_edges']:,} | "
                    f"{gap['hospital']['newly_lost_residents']:,.0f} | {gap['main_road_entry']['newly_lost_residents']:,.0f} | "
                    f"{run['road_criticality_inputs']['residents_losing_all_routes']:,.0f} |")
            assert line in section, line
    assert "CC BY-SA 4.0" in section and PRODUCT_4009_CREDIT in section and "Changed by FloodGuard" in section
    assert "It is not an official warning" in section and "Class E never means safe" in section
    assert "is not a probability" in section and "**No class is headlined.**" in section
    for point in ue.OPEN_POINTS:
        assert f"**{point['id']}," in section, point["id"]
    # The section says of case SE1, as of case O2, that its counts are statements about single tambons.
    single = receipts["SE1"]["rights"]["figures_of_local_level_layers_in_this_receipt"]["counts_that_state_a_value_of_a_single_unit"]
    assert "**These counts are statements about single tambons.**" in section
    assert f"no tambon is class B in {single['cells_in_which_such_a_class_has_another_count']} cells" in section
    assert f"{single['cells_whose_class_counts_differ_from_the_default_cell']} of the 90 cells" in section
    # Guardrail GR8 has two displays; the section does not tell a page to show a class without the second.
    assert "without a stability claim" not in section and "stable against" not in section
    assert "Otherwise it is shown as unstable: verify" in section


def _lint_findings(receipt: dict[str, Any], grid: ue.EnsembleGrid) -> tuple[list[str], int]:
    """Lint every string of a receipt; return what is left after the three places that hold the protocol's own word.

    The name protocol v1b gives its second facility set is let through where it stands as an identifier (the
    level lists of the grid, the level of a reason, a cell identifier) and in the sentence on declared cut line 8
    that the receipt quotes from the protocol, and only there, and only when the string is exactly that
    identifier, cell or sentence. Anywhere else the word is a finding like any other.
    """

    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    cut_line_8 = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))["ensemble_grid"]["declared_cuts"]["cut_line_8"]
    cell_ids = {ue.cell_id(cell) for cell in ue.cells(grid)}
    left, let_through = [], 0
    for path, text in json_strings(receipt):
        found = find_violations(text, rules, path)
        only_the_name = bool(found) and all(finding.match.lower() == FACILITY_SET_NAME for finding in found)
        if only_the_name and ((LEVEL_NAME_PATHS.fullmatch(path) and text == FACILITY_SET_NAME)
                              or (CELL_ID_PATHS.fullmatch(path) and text in cell_ids)
                              or (path == QUOTED_CUT_LINE_PATH and text == cut_line_8)):
            let_through += 1
            continue
        left.extend(finding.describe() for finding in found)
    return left, let_through


@pytest.mark.parametrize("case", CASES)
def test_the_text_of_each_receipt_passes_the_shared_wording_lint(case: str, grid: ue.EnsembleGrid) -> None:
    receipt = _receipt(case)
    left, let_through = _lint_findings(receipt, grid)
    assert left == []
    assert let_through == 3 + 1 + 180, "two level lists, one level of a reason, one quoted sentence and 180 cell identifiers"
    # The same word in a sentence of the receipt is a finding: the first receipts carried one, in the reason of a level.
    assert all(FACILITY_SET_NAME not in item["reason"] for item in receipt["parameters"]["levels_not_run"])
    for place in ("reason", "code"):
        changed = json.loads(json.dumps(receipt))
        changed["parameters"]["levels_not_run"][0][place] = "The corroborated facility set adds shelters."
        assert len(_lint_findings(changed, grid)[0]) == 1, place
    changed = json.loads(json.dumps(receipt))
    changed["limitations"].append("The season envelope is corroborated by the ensemble.")
    assert len(_lint_findings(changed, grid)[0]) == 1
    # A cell identifier that is not a cell of the grid, or a changed quote of the protocol, is not let through.
    changed = json.loads(json.dumps(receipt))
    changed["cells"]["run"][0] = "minus|strict|corroborated|worldpop_2020|P10_P90|approved"
    changed["parameters"]["grid"]["declared_cuts"]["cut_line_8"] += " The ensemble corroborated the set."
    assert len(_lint_findings(changed, grid)[0]) == 3
    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert find_violations("The ensemble validates the classes.", rules), "the lint does see a claim"


@pytest.mark.parametrize("case", CASES)
def test_the_results_outside_git_are_the_files_the_receipt_binds(case: str) -> None:
    """Skipped unless the external data root is at hand: the per-unit results are outside Git."""

    external = os.environ.get(EXTERNAL_DATA_VARIABLE)
    receipt = _receipt(case)
    bound = _files(receipt)[0]
    path = Path(external) / bound["path"][len(EXTERNAL_LABEL) + 1:] if external else None
    if path is None or not path.is_file():
        pytest.skip(f"the per-unit results are outside Git; set {EXTERNAL_DATA_VARIABLE} to compare them with the receipt")
    assert _sha256(path) == bound["sha256"], "the file is the one the receipt binds"
    document = json.loads(path.read_text(encoding="ascii"))
    assert document["publication_eligibility"] == "local" and document["official_warning"] is False
    assert document["generated_at_utc"] == receipt["generated_at_utc"] and document["protocol_sha256"] == receipt["protocol_sha256"]
    assert document["licence"]["credit"] == PRODUCT_4009_CREDIT and "In plan task E10" in document["licence"]["change_notice"]
    canonical = json.dumps(document["units"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == receipt["result"]["units_sha256"]
    assert document["summary"] == receipt["result"]["summary"]
    units = document["units"]
    assert [unit["unit_id"] for unit in units] == MAE_SAI_UNITS and all(len(unit["cells"]) == 90 for unit in units)
    assert len(document["cells"]) == 540 and len(document["access_runs"]["runs"]) == 6
    for unit in units:
        headline = unit["headline_stability"]
        classes = [cell["action_class"] for cell in unit["cells"]]
        assert headline["status"] == "not_evaluated" and headline["class_retention"] is None
        assert headline["cells_of_the_protocol_set"] == 180 and headline["cells_with_a_class"] == 90
        assert headline["cells_keeping_the_reference_class"] == classes.count(unit["reference_cell"]["action_class"])
        assert unit["class_counts"] == {name: classes.count(name) for name in CLASSES} | {"no_class": 0}
        assert unit["fpps_0_100"]["count"] == 90 and 1 <= unit["rank"]["best"] <= unit["rank"]["worst"] <= 8
    # The counts the README gives "from the file outside Git": they are in no receipt, so they are checked here.
    section = _section()
    changed = {anchor: sum(1 for unit in units for item in unit["one_at_a_time"]["flood_likelihood_anchor"]
                           if item["flood_anchor"] == anchor and item["action_class"] != unit["reference_cell"]["action_class"])
               for anchor in (0.1, 0.3)}
    v2 = [(unit["one_at_a_time"]["class_rule_v1_and_v2"]["v2_status"], unit["one_at_a_time"]["class_rule_v1_and_v2"]["v2_result"])
          for unit in units]
    spans = sorted(unit["rank"]["worst"] - unit["rank"]["best"] for unit in units)
    by_largest = [unit["fpps_swing"]["largest_by_the_largest_fpps_swing"] for unit in units]
    by_mean = [unit["fpps_swing"]["largest_by_the_mean_fpps_swing"] for unit in units]
    if case == "SE1":
        assert changed == {0.1: 2, 0.3: 0} and "**two of the four class-E tambons are class D**" in section
        assert "with 0.30 no class changes" in section
        assert all(unit["reference_cell"]["action_class"] == "E" for unit in units for item in unit["one_at_a_time"]["flood_likelihood_anchor"]
                   if item["action_class"] != unit["reference_cell"]["action_class"])
        assert v2.count(("evaluated", "E")) == 4 and v2.count(("not_evaluated", None)) == 4
        assert "The v2 result is E for four tambons and not evaluated for four" in section
        assert spans == [0, 0, 0, 0, 1, 1, 1, 1] and "the other four move by one place" in section
        assert (by_largest.count("flood_input_single_state"), by_largest.count("weights")) == (4, 4)
        assert (by_mean.count("flood_input_single_state"), by_mean.count("weights")) == (3, 5)
        assert ("on the flood-level axis for four tambons and on the weight axis for four; taken as a mean over the other axes, "
                "for three and for five") in section
        # The tambon that is B in the default cell: D with the minus level under the strict or the central closure level.
        moving = next(unit for unit in units if unit["reference_cell"]["action_class"] == "B")
        other = {tuple(cell["cell_id"].split("|")[:2]) for cell in moving["cells"] if cell["action_class"] != "B"}
        assert other == {("minus", "strict"), ("minus", "central")}
        for item in moving["routing_combinations"]:
            components = item["components"]
            smaller = (item["flood_input_single_state"], item["passability"]) in other
            assert (components["road_criticality_0_100"] < 75) is smaller and components["access_gap_0_100"] >= 55
        # The class-E tambon that is D in 3 cells is the class-E tambon with the highest FPPS in the default cell, which
        # is how the README says a reader of the committed files can tell which one it is (open point E10-OP10).
        class_e = [unit for unit in units if unit["reference_cell"]["action_class"] == "E"]
        mover = next(unit for unit in class_e if unit["class_counts"]["D"])
        assert mover["unit_id"] == max(class_e, key=lambda unit: unit["reference_cell"]["fpps_0_100"])["unit_id"]
        assert (mover["class_counts"]["E"], mover["class_counts"]["D"]) == (87, 3)
        assert "which class-E tambon has the highest FPPS there" in section

        # After cut line 6, for the two tambons that move: the levels of the default cell kept, and P5 / P95 kept.
        def kept_after_the_cut(unit: dict[str, Any]) -> tuple[int, int]:
            cut = unit["headline_stability"]["after_declared_cut_line_6"]
            other_pair = cut["other_levels_the_cut_could_keep"][0]
            assert (cut["cells"], other_pair["cells"], other_pair["levels_kept"]["vulnerability_anchors"]) == (45, 45, "P5_P95")
            return cut["cells_keeping_the_reference_class"], other_pair["cells_keeping_the_reference_class"]

        assert kept_after_the_cut(moving) == (35, 35) and kept_after_the_cut(mover) == (45, 42)
        assert ("the tambon that is class B keeps its class in 35 of the 45 cells under either pair, and the class-E tambon that "
                "moves keeps class E in all 45 under P10 / P90 and in 42 under P5 / P95") in section
        # The bounds under both readings of the protocol's set, for a tambon that keeps its class in all 90 cells run.
        steady = [unit["headline_stability"] for unit in units if unit["headline_stability"]["cells_keeping_the_reference_class"] == 90]
        assert len(steady) == 6
        for headline in steady:
            assert headline["bounds_over_the_protocol_set"] == {"lower": 0.5, "upper": 1.0, "cells_without_a_class": 90}
            assert headline["other_reading_of_the_protocol_set"]["bounds"] == {"lower": 90 / 540, "upper": 1.0, "cells_without_a_class": 450}
        assert "between 0.5 and 1.0" in section and "between 0.167 and 1.0" in section
    else:
        assert changed == {0.1: 0, 0.3: 0} and v2.count(("evaluated", "E")) == 8
        assert {(cell["action_class"], cell["action_reason_code"]) for unit in units for cell in unit["cells"]} == {("E", "low_priority_score")}
        assert max(unit["fpps_0_100"]["max"] for unit in units) < 35 and "no FPPS reaches 35 in any of them" in section
        assert all(not any(item["action_class"] != "E" for item in unit["reference_cell"]["leave_one_component_out"].values())
                   for unit in units)
