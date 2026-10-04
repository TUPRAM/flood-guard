"""The reported runs of the planning assessment for the Mae Sai cases (plan task E8, part 2).

These tests read the two committed receipts and the README of the output folder. They compute no component, no
FPPS and no class. The overlay of case O2 and the report of case SE1 are outside Git (their lineage is below the
public level); one test compares the README with the SE1 report when the external data root is at hand
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

from floodguard import planning_assessment
from floodguard.wording_lint import find_violations, load_rules

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "planning_v1"
REGISTER = OUTPUTS / "run_register"
DOCS = ROOT / "docs" / "proposal_execution"
RECEIPTS = {case: OUTPUTS / f"e8_planning_assessment_{case.lower()}_mae_sai.json" for case in ("SE1", "O2")}
EXTERNAL_LABEL = "<external_data_workspace>"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
SECTION_HEADING = "### Plan task E8: the planning assessment of the Mae Sai cases"
MAE_SAI_UNITS = ["TH570901", "TH570902", "TH570903", "TH570904", "TH570905", "TH570906", "TH570908", "TH570909"]
ACTION_CLASSES = ("A", "B", "C", "D", "E")
TIMES = {1: "once", 2: "twice", 3: "three times", 4: "four times", 5: "five times", 6: "six times", 7: "seven times",
         8: "eight times"}

pytestmark = pytest.mark.skipif(not all(path.is_file() for path in RECEIPTS.values()),
                                reason="the planning assessment has not been run on this checkout")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(case: str) -> dict[str, Any]:
    return json.loads(RECEIPTS[case].read_text(encoding="ascii"))


def _bound(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    return list(receipt["outputs"]["overlay"]["files"])


def _section() -> str:
    readme = (OUTPUTS / "README.md").read_text(encoding="utf-8")
    assert readme.count(SECTION_HEADING) == 1
    return readme.split(SECTION_HEADING, 1)[1]


def _short(sha256: str) -> str:
    """A SHA-256 as the README writes it: the first eight and the last four characters."""

    return f"`{sha256[:8]}…{sha256[-4:]}`"


@pytest.mark.parametrize("case", sorted(RECEIPTS))
def test_each_receipt_is_registered_names_the_protocols_and_holds_no_value_of_a_single_tambon(case: str) -> None:
    path = RECEIPTS[case]
    receipt = _receipt(case)
    entry = json.loads((REGISTER / path.name).read_text(encoding="ascii"))
    assert entry == {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}, "every run is registered"
    assert receipt["protocol_sha256"] == {f"planning_protocol_{name}": _sha256(DOCS / f"planning_protocol_{name}.json")
                                          for name in ("v1a", "v1b")}
    assert receipt["status"] == "run_receipt" and receipt["official_warning"] is False
    assert receipt["operational_status"] == "non_operational" and receipt["can_feed_decision_layer"] is False
    parameters = receipt["parameters"]
    assert (parameters["case_id"], parameters["frame_set"], parameters["level"]) == (case, "mae_sai", "public")
    assert parameters["unit_ids"] == MAE_SAI_UNITS and parameters["services"] == ["hospital", "main_road_entry"]
    assert parameters["closure_rule"]["level"] == "central" and parameters["flood_level"] == "as_provided"
    # The tambon codes are in the parameters, and nowhere else: the receipt in Git names no unit beside a value.
    without_the_list = json.loads(json.dumps(receipt))
    del without_the_list["parameters"]["unit_ids"]
    assert not re.search(r"TH\d{6}", json.dumps(without_the_list))
    # Guardrail GR6: the lineage is below the public level, so nothing the run wrote is in Git.
    rights = receipt["rights"]
    assert rights["publication_eligibility"] == "local" and rights["written_under_apps_web_public"] is False
    assert rights["lineage_levels"]["e7_age_exposure_table"] == "local"
    assert rights["figures_of_local_level_layers_in_this_receipt"]["figures"], "the counts of a local lineage are declared"
    files = _bound(receipt)
    assert files and all(item["path"].startswith(EXTERNAL_LABEL + "/") and item["in_git"] is False for item in files)
    assert all(f"/{case.lower()}_mae_sai/e8_planning_assessment/" in item["path"] for item in files)
    assert any(item["what"] == "licence_notice" for item in files), "product 4009 values go with their licence notice"
    assert not (OUTPUTS / "overlays").exists(), "no overlay is public today, so none is in Git"
    assert not list((ROOT / "apps" / "web" / "public").rglob("planning_assessment_overlay_*")) if (ROOT / "apps" / "web" / "public").is_dir() else True
    # The guardrails and the checks of the whole frame.
    assert all(item["result"] == "PASS" for item in receipt["guardrails"].values())
    assert receipt["guardrails"]["every_reporting_unit_has_one_row"]["units"] == 8
    assert receipt["guardrails"]["GR2_no_max_normalisation"]["components_checked"] == 40
    assert receipt["lane_purity"]["result"] == "PASS"
    whole = receipt["whole_case_checks"]
    assert whole["result"] == "PASS" and (whole["rows"], whole["component_values"], whole["rows_with_an_fpps"]) == (8, 40, 8)
    assert whole["every_component_value_within_0_100"] and whole["every_fpps_within_0_100"]
    assert whole["leave_one_component_out_consistent_with_the_fpps"] and whole["rows_with_leave_one_component_out"] == 8
    assert whole["residents_same_as_the_access_table"] is True
    assert whole["residents_of_the_rows"] == receipt["measurement_checks"]["residents_in_the_units"]
    assert receipt["measurement_checks"]["demand_cells"] == receipt["measurement_checks"]["cells_in_one_unit"] == 36765
    # A receipt lists the open points the module had when it ran; points written down since stand after them.
    listed = [point["id"] for point in receipt["open_points"]]
    assert listed == [point["id"] for point in planning_assessment.OPEN_POINTS][:len(listed)] and len(listed) >= 7
    assert receipt["development_reads"]["reads"], "the reads made before the run are listed"


def test_the_two_cases_count_the_same_residents_as_the_access_tables() -> None:
    """One routing context and one population serve both cases: 81,837 modelled residents in the eight tambons."""

    totals = {case: _receipt(case)["whole_case_checks"]["residents_of_the_rows"] for case in RECEIPTS}
    assert totals["SE1"] == totals["O2"] == pytest.approx(81836.889, abs=0.001)
    e5 = json.loads((OUTPUTS / "e5_access_diff_se1_mae_sai_public_services.json").read_text(encoding="ascii"))
    run = next(run for run in e5["runs"] if (run["flood_level"], run["closure_level"]) == ("as_provided", "central"))
    assert sum(row["residents"] for row in run["units"]) == pytest.approx(totals["SE1"], abs=1e-6)


def test_the_se1_run_wrote_no_overlay_and_reports_its_rows_as_computed() -> None:
    receipt = _receipt("SE1")
    result = receipt["result"]
    assert receipt["run_kind"] == "first_run" and (receipt["parameters"]["lane"], receipt["parameters"]["tier"]) == ("SCN-ENV", "T1")
    assert result["overlay_written"] is False and result["summary"] is None
    refusal = result["not_written_because"]
    assert (refusal["code"], refusal["open_point"], refusal["rows"]) == ("v2_result_not_evaluable", "E8-OP1", 4)
    assert refusal["triggers_not_evaluated"] == ["B", "C", "D"]
    reported = result["rows_as_computed"]
    assert reported["schema_version"] == planning_assessment.ROWS_AS_COMPUTED_SCHEMA
    assert reported["checked_by_the_overlay_parser"]["result"] == "PASS" and reported["checked_by_the_overlay_parser"]["rows"] == 8
    counts = reported["summary"]
    assert counts["row_count"] == counts["unit_count"] == 8 and counts["rows_without_a_v2_result"] == 4
    assert counts["rows_by_lane"]["SCN-ENV"] == 8 and counts["rows_by_temporal_relation"]["season_window"] == 8
    # Scenario classes are counted in the SCN column, and in no other.
    classes = counts["binding_class_by_lane_column"]
    assert classes["SCN"] == {"A": 0, "B": 1, "C": 0, "D": 3, "E": 4, "none": 0}
    assert all(not any(classes[column].values()) for column in classes if column != "SCN")
    reasons = counts["reason_code_by_lane_column"]["SCN"]
    assert (reasons["low_priority_score"], reasons["critical_route_access"], reasons["resilience"]) == (4, 1, 3)
    assert reasons["low_confidence"] == reasons["insufficient_denominator"] == 0
    assert counts["confidence_class_by_lane_column"]["SCN"] == {"low": 0, "medium": 8, "none": 0}
    assert counts["rows_by_confidence_kind"]["scenario"] == 8 and counts["rows_by_confidence_kind"]["observed"] == 0
    assert not any(counts["failed_conditions_by_lane_column"]["SCN"].values())
    assert counts["would_be_class_by_lane_column"]["SCN"]["none"] == 8, "a would-be class exists for a low-confidence row only"
    v2 = counts["v2_result_by_lane_column"]["SCN"]
    assert (v2["E"], v2["not_evaluated"]) == (4, 4) and sum(v2.values()) == 8
    assert counts["headline_status_by_lane_column"]["SCN"]["not_evaluated"] == 8 and counts["rows_under_gr1"] == 0
    assert counts["inputs_by_rights_level"] == {"local": 1, "pitch": 0, "public": 7, "none": 0}
    files = _bound(receipt)
    assert [item["what"] for item in files] == ["overlay_not_written_report", "licence_notice"]
    assert files[0]["holds_rows_as_computed"] is True and files[0]["path"].endswith("/overlay_not_written.json")


def test_the_o2_run_wrote_its_overlay_outside_git_and_every_row_is_class_e() -> None:
    receipt = _receipt("O2")
    result = receipt["result"]
    assert (receipt["parameters"]["lane"], receipt["parameters"]["tier"]) == ("OBS", "T3")
    assert receipt["parameters"]["case_reference_date"] == "2024-10-22"
    assert result["overlay_written"] is True and result["not_written_because"] is None and result["rows_as_computed"] is None
    counts = result["summary"]
    assert counts["row_count"] == 8 and counts["rows_by_lane"]["OBS"] == 8 and counts["rows_by_tier"]["T3"] == 8
    assert counts["rows_by_temporal_relation"]["event_aligned"] == 8 and counts["obs_rows_not_event_aligned"] == 0
    assert counts["binding_class_by_lane_column"]["OBS"] == {"A": 0, "B": 0, "C": 0, "D": 0, "E": 8, "none": 0}
    assert counts["reason_code_by_lane_column"]["OBS"]["low_priority_score"] == 8
    assert counts["confidence_class_by_lane_column"]["OBS"] == {"low": 0, "medium": 8, "none": 0}
    assert counts["rows_by_confidence_kind"]["observed"] == 8
    assert counts["would_be_class_by_lane_column"]["OBS"]["none"] == 8
    assert counts["v2_result_by_lane_column"]["OBS"]["E"] == 8 and counts["headline_status_by_lane_column"]["OBS"]["not_evaluated"] == 8
    assert counts["inputs_by_rights_level"]["local"] == 3, "the layer of 22 October, its access table and the age table"
    files = _bound(receipt)
    assert [item["what"] for item in files] == ["planning_assessment_overlay", "licence_notice"] and files[0]["rows"] == 8
    # The second run changed a Thai word in the overlay header and nothing in the result.
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["result_same"] is True
    assert "Thai title" in receipt["supersedes"]["reason"] and len(receipt["run_history"]) == 1
    earlier = receipt["run_history"][0]
    assert earlier["receipt_sha256"] == receipt["supersedes"]["receipt_sha256"] and earlier["generated_at_utc"] < receipt["generated_at_utc"]
    assert earlier["result_same_as_the_run_that_replaced_it"] is True


def test_the_readme_reports_the_runs_as_the_receipts_hold_them() -> None:
    section = _section()
    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert find_violations(section, rules, "outputs README, plan task E8") == []
    se1, o2 = _receipt("SE1"), _receipt("O2")
    for case, receipt in (("SE1", se1), ("O2", o2)):
        assert f"`{RECEIPTS[case].name}`" in section
        assert _short(_bound(receipt)[0]["sha256"]) in section, "the file outside Git is named by its SHA-256"
        assert receipt["timestamps"]["run_started_at_utc"][11:] in section
    assert _short(_sha256(RECEIPTS["SE1"])) in section
    assert _short(o2["supersedes"]["receipt_sha256"]) in section, "the superseded O2 receipt is named"
    assert _short(next(iter(o2["supersedes"]["outputs_of_the_superseded_run"].values()))) in section
    # Which classes appear, and which do not, in the words of the receipt's counts.
    classes = se1["result"]["rows_as_computed"]["summary"]["binding_class_by_lane_column"]["SCN"]
    appear = ", ".join(f"{name} {TIMES[classes[name]]}" for name in ACTION_CLASSES if classes[name])
    assert appear == "B once, D three times, E four times"
    assert f"**Binding classes of class rule v1: {appear}.**" in section and "**Classes A and C do not appear.**" in section
    assert "**The overlay of case SE1 was not written**" in section and "which is not an overlay" in section
    assert "**Binding class E for all eight rows, each with the reason `low_priority_score`.**" in section
    assert "**Classes A, B, C and D do not appear.**" in section
    assert "scenario result under the 2024 season envelope, not an observation" in section
    assert "It is not an official warning" in section and "Class E never means safe" in section
    assert "One flood input drives 4 of 5 components (90% of weight)" in section
    assert "CC BY-SA 4.0" in section and "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" in section and "Changed by FloodGuard" in section
    # Case O1 is refused, in the builder's own words.
    assert "**Case O1: refused.**" in section and "the rights registry holds no record of Sentinel-1 data (open point E1-OP2)" in section
    # Every open point of the receipts is listed, and one more that was written down after the runs.
    for point in planning_assessment.OPEN_POINTS:
        assert f"**{point['id']}," in section, point["id"]
    assert "**E8-OP8," in section and "not in the receipts" in section
    # One table holds values of single tambons: the eight rows of case SE1. Nothing of case O2 is given per tambon.
    rows = [line for line in section.splitlines() if re.match(r"\| TH\d{6} ", line)]
    assert [line.split()[1] for line in rows] == MAE_SAI_UNITS
    codes_outside_the_table = [line for line in section.splitlines() if re.search(r"TH\d{6}", line) and line not in rows]
    assert all("E7-OP1" in line for line in codes_outside_the_table), codes_outside_the_table
    o2_part = section.split("**Case O2: the overlay was written, outside Git.**", 1)[1].split("**Case O1: refused.**", 1)[0]
    assert not re.search(r"TH\d{6}", o2_part) and "| " not in o2_part
    residents = sum(float(line.split("|")[2].replace(",", "")) for line in rows)
    assert residents == pytest.approx(se1["whole_case_checks"]["residents_of_the_rows"], abs=4.0), "eight rounded counts"


def test_the_readme_table_of_case_se1_repeats_the_report_the_receipt_binds() -> None:
    """Skipped unless the external data root is at hand: the report is outside Git."""

    external = os.environ.get(EXTERNAL_DATA_VARIABLE)
    bound = _bound(_receipt("SE1"))[0]
    report = Path(external) / bound["path"][len(EXTERNAL_LABEL) + 1:] if external else None
    if report is None or not report.is_file():
        pytest.skip(f"the SE1 report is outside Git; set {EXTERNAL_DATA_VARIABLE} to compare the README with it")
    assert _sha256(report) == bound["sha256"], "the report is the file the receipt binds"
    document = json.loads(report.read_text(encoding="ascii"))
    assert document["publication_eligibility"] == "local" and document["official_warning"] is False
    as_computed = document["rows_as_computed"]
    assert as_computed["schema_version"] == planning_assessment.ROWS_AS_COMPUTED_SCHEMA
    expected = []
    for row in as_computed["rows"]:
        components = row["components"]
        values = [f"{components[name]['value_0_100']:.2f}" for name in (
            "flood_likelihood_0_100", "exposure_0_100", "access_gap_0_100", "road_criticality_0_100")]
        confidence = row["confidence"]
        expected.append(f"| {row['unit_id']} {row['unit_name_en']} | {confidence['measurements']['unit_residents']:,.0f} | "
                        + " | ".join(values)
                        + f" | {confidence['confidence_class']} | {', '.join(confidence['failed_conditions']) or 'none'} |")
    rows = [line for line in _section().splitlines() if re.match(r"\| TH\d{6} ", line)]
    assert rows == expected
    assert planning_assessment.rows_without_a_v2_result(as_computed) == [
        item["unit_id"] for item in document["not_written_because"]["rows"]]
