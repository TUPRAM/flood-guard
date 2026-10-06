"""The reported runs of the planning assessment for the Mae Sai cases (plan task E8, part 2).

These tests read the two committed receipts and the README of the output folder. They compute no component, no
FPPS and no class. The overlay of case O2 and the report of case SE1 are outside Git (their lineage is below the
public level); one test compares the README with the SE1 report when the external data root is at hand
(``FLOODGUARD_EXTERNAL_DATA``) and is skipped anywhere else.

Both receipts are superseding runs made after a review of the task: they carry the licence, the credit and a
change notice for UNOSAT/GISTDA product 4009, the SHA-256 of the rows alone, and the counts that cover every row.
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
E8_RECEIPTS = sorted(OUTPUTS.glob("e8_planning_assessment_*.json"))
PRODUCT_4009_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
RIGHTS_RECORD_4009 = "docs/proposal_execution/rights_basis_4009_v1.json"
FIRST_SE1_RECEIPT = "098ac3b104a4c6da5b12867d378e99d398ef1741d5c36db3191ba2940262adee"
SECOND_SE1_RECEIPT = "d8d8a569cf7a4a2fcbd747cb71e3d4e0cff89a6c91be75c3e30dcf288ce3eed5"
"""The first SE1 receipt (commit 317434d), which the receipt here supersedes."""
SECOND_O2_RECEIPT = "2ea03b0cf950ce7378dd7a6e169c31233bc6398f64fa6742e311d7a66ac02e6f"
"""The second O2 receipt (commit 317434d), which the receipt here supersedes."""
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
    assert receipt["open_points"] == [dict(point) for point in planning_assessment.OPEN_POINTS]
    assert receipt["development_reads"]["reads"], "the reads made before the run are listed"
    # The SHA-256 of the rows alone and of each lineage input: what a later run is compared with.
    assert re.fullmatch(r"[0-9a-f]{64}", receipt["result"]["rows_sha256"])
    assert set(receipt["lineage_input_sha256"]) == set(rights["lineage_levels"])
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in receipt["lineage_input_sha256"].values())
    # A superseding run: the rows are those of the run it replaced, read back from the file that run wrote.
    supersedes = receipt["supersedes"]
    assert receipt["run_kind"] == "superseding_run" and "decision log R20" in supersedes["reason"]
    assert (supersedes["counts_same"], supersedes["rows_same"], supersedes["lineage_inputs_same"], supersedes["result_same"]) == (
        True, True, True, True)
    assert supersedes["rows_sha256_of_the_superseded_run"] == supersedes["rows_sha256_of_this_run"] == receipt["result"]["rows_sha256"]
    assert "read back with the SHA-256 that receipt names" in supersedes["rows_of_the_superseded_run_read_from"]
    kept = supersedes["copies_kept_outside_git"]
    assert kept[0] == {"path": kept[0]["path"], "sha256": supersedes["receipt_sha256"], "what": "receipt"}
    assert all(f"/{case.lower()}_mae_sai/e8_planning_assessment/superseded_runs/" in item["path"] for item in kept)
    assert {item["sha256"] for item in kept[1:]} == set(supersedes["outputs_of_the_superseded_run"].values())
    assert receipt["run_history"][-1]["receipt_sha256"] == supersedes["receipt_sha256"]
    assert receipt["parameters"]["tolerances"]["residents_between_two_stages"] == 1e-6
    assert receipt["measurement_checks"]["compared_before_any_flood_layer_was_read_for_a_unit"] is True


@pytest.mark.parametrize("path", E8_RECEIPTS, ids=lambda path: path.name)
def test_every_e8_receipt_whose_lineage_holds_product_4009_carries_its_licence_credit_and_change_notice(path: Path) -> None:
    """Product 4009 content ships only under CC BY-SA 4.0 with its credit and a change notice (plan 7.1)."""

    receipt = json.loads(path.read_text(encoding="ascii"))
    holds_product_4009 = receipt["inputs"]["rights_record"]["input_id"] == "unosat_4009" or any(
        name.startswith("unosat_4009") for name in receipt["rights"]["lineage_levels"])
    licence = receipt.get("licence")
    if not holds_product_4009:
        assert licence is None
        return
    assert licence is not None, f"{path.name} holds figures derived from product 4009 and states no licence"
    assert (licence["name"], licence["spdx_id"]) == ("CC BY-SA 4.0", "CC-BY-SA-4.0")
    assert licence["full_name"] == "Creative Commons Attribution-ShareAlike 4.0 International" and licence["url"].startswith("https://")
    assert licence["credit"] == PRODUCT_4009_CREDIT and licence["not_legal_advice"] is True
    v1a = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    assert licence["standard_sentence"] == v1a["wording"]["standard_4009_sentence"]
    notice = licence["change_notice"]
    layer = receipt["inputs"]["rights_record"]["layer"]
    assert notice.startswith(f"Changed by FloodGuard: the layer {layer} was repaired")
    assert "(plan task E5)" in notice and "In plan task E8" in notice and "planning classes" in notice
    assert notice.endswith(f"Source: {PRODUCT_4009_CREDIT}, CC BY-SA 4.0.")
    record = licence["rights_record"]
    assert record["path"] == RIGHTS_RECORD_4009 == receipt["inputs"]["rights_record"]["path"]
    assert record["sha256"] == _sha256(ROOT / RIGHTS_RECORD_4009) == receipt["inputs"]["rights_record"]["sha256"]
    assert record["record_status"] == "confirmed" and record["confirmed_by"]
    assert licence["publication_level"] == receipt["rights"]["publication_eligibility"]
    assert licence["flood_input_rights_level"] == receipt["rights"]["flood_layer"]["rights_level"]
    assert (ROOT / licence["licence_notice_file"]).is_file()
    assert {item["id"] for item in licence["other_inputs"]} == {
        "osm", "worldpop-2020", "cod-ab", "esa-worldcover-2021", "worldpop-2024-age-counts"}
    assert "product 4009" in licence["applies_to"] and "this receipt binds" in licence["where_the_values_are"]
    text = path.read_text(encoding="ascii")
    assert "FL20240912THA" in text and "Changed by FloodGuard" in text


def test_the_receipts_name_the_counts_that_cover_every_row_and_say_what_they_give_away() -> None:
    """A count that covers all eight rows is a statement about each tambon, whatever file the rows are kept in."""

    declared = {case: _receipt(case)["rights"]["figures_of_local_level_layers_in_this_receipt"] for case in RECEIPTS}
    for block in declared.values():
        assert "states that value for each unit" in block["what_the_counts_give_away"]
        assert "E8-OP7" in block["for_the_owners"] and "E1-OP1" in block["for_the_owners"]
    assert declared["O2"]["counts_that_cover_every_row"] == [
        "binding_class_by_lane_column.OBS.E",
        "confidence_class_by_lane_column.OBS.medium",
        "headline_status_by_lane_column.OBS.not_evaluated",
        "reason_code_by_lane_column.OBS.low_priority_score",
        "v2_result_by_lane_column.OBS.E",
        "would_be_class_by_lane_column.OBS.none",
    ]
    # In case SE1 the classes differ between the tambons, so the counts of the classes do not cover every row.
    assert declared["SE1"]["counts_that_cover_every_row"] == [
        "confidence_class_by_lane_column.SCN.medium",
        "headline_status_by_lane_column.SCN.not_evaluated",
        "would_be_class_by_lane_column.SCN.none",
    ]
    assert declared["SE1"]["figures"][0]["where"] == "result.summary"
    assert declared["O2"]["figures"][0]["where"] == "result.summary"


def test_the_two_cases_count_the_same_residents_as_the_access_tables() -> None:
    """One routing context and one population serve both cases: 81,837 modelled residents in the eight tambons."""

    totals = {case: _receipt(case)["whole_case_checks"]["residents_of_the_rows"] for case in RECEIPTS}
    assert totals["SE1"] == totals["O2"] == pytest.approx(81836.889, abs=0.001)
    e5 = json.loads((OUTPUTS / "e5_access_diff_se1_mae_sai_public_services.json").read_text(encoding="ascii"))
    run = next(run for run in e5["runs"] if (run["flood_level"], run["closure_level"]) == ("as_provided", "central"))
    assert sum(row["residents"] for row in run["units"]) == pytest.approx(totals["SE1"], abs=1e-6)


def test_the_se1_run_wrote_its_overlay_outside_git_under_schema_1_1() -> None:
    receipt = _receipt("SE1")
    result = receipt["result"]
    assert (receipt["parameters"]["lane"], receipt["parameters"]["tier"]) == ("SCN-ENV", "T1")
    # The runs of 4 October 2026 wrote no overlay (open point E8-OP1). Decision log R20 answered it; the two runs of
    # 6 October 2026 wrote the overlay, and the second lists the reads made before it.
    history = receipt["run_history"]
    assert [item["receipt_sha256"] for item in history[:2]] == [FIRST_SE1_RECEIPT, SECOND_SE1_RECEIPT] and len(history) == 3
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["receipt_sha256"] == history[-1]["receipt_sha256"]
    assert receipt["supersedes"]["rows_same"] is True, "the two runs of 6 October 2026 gave the same rows"
    assert history[1]["result_same_as_the_run_that_replaced_it"] is False, "the class_v2 block changed with schema 1.1"
    assert "decision log R20" in receipt["supersedes"]["reason"] and len(receipt["development_reads"]["reads"]) == 2
    assert result["overlay_written"] is True and result["not_written_because"] is None and result["rows_as_computed"] is None
    counts = result["summary"]
    assert counts["row_count"] == counts["unit_count"] == 8
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
    assert [item["what"] for item in files] == ["planning_assessment_overlay", "licence_notice"] and files[0]["rows"] == 8
    assert files[0]["path"].endswith("/se1_mae_sai/e8_planning_assessment/planning_assessment_overlay_se1_mae_sai.json")
    assert files[0]["in_git"] is False and files[0]["publication_eligibility"] == "local"


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
    # The second run changed a Thai word in the overlay header, the third added the licence block after a review;
    # neither changed a row. The two runs of 6 October 2026 wrote the class_v2 block of overlay schema 1.1.
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["rows_same"] is True
    assert len(receipt["run_history"]) == 4 and receipt["supersedes"]["receipt_sha256"] == receipt["run_history"][-1]["receipt_sha256"]
    assert receipt["run_history"][2]["result_same_as_the_run_that_replaced_it"] is False, "the class_v2 block changed with schema 1.1"
    first, second = receipt["run_history"][:2]
    assert "Thai title" in first["superseded_because"] and first["generated_at_utc"] == "2026-10-04T17:53:46Z"
    assert second["receipt_sha256"] == SECOND_O2_RECEIPT and second["generated_at_utc"] == "2026-10-04T17:59:18Z"
    assert first["generated_at_utc"] < second["generated_at_utc"] < receipt["generated_at_utc"]
    assert first["result_same_as_the_run_that_replaced_it"] is True and second["result_same_as_the_run_that_replaced_it"] is True
    assert receipt["run_history"][-1]["rows_sha256"] == result["rows_sha256"], "the rows of the run before, read back from its overlay"


def test_the_readme_reports_the_runs_as_the_receipts_hold_them() -> None:
    section = _section()
    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert find_violations(section, rules, "outputs README, plan task E8") == []
    se1, o2 = _receipt("SE1"), _receipt("O2")
    for case, receipt in (("SE1", se1), ("O2", o2)):
        assert f"`{RECEIPTS[case].name}`" in section
        assert _short(_bound(receipt)[0]["sha256"]) in section, "the file outside Git is named by its SHA-256"
        assert receipt["timestamps"]["run_started_at_utc"][11:] in section
    assert _short(_sha256(RECEIPTS["SE1"])) in section and _short(_sha256(RECEIPTS["O2"])) in section
    for receipt in (se1, o2):
        assert _short(receipt["supersedes"]["receipt_sha256"]) in section, "the superseded receipt is named"
        assert _short(next(iter(receipt["supersedes"]["outputs_of_the_superseded_run"].values()))) in section
        for earlier in receipt["run_history"]:
            assert _short(earlier["receipt_sha256"]) in section, "every earlier run is named"
    # Which classes appear, and which do not, in the words of the receipt's counts.
    classes = se1["result"]["summary"]["binding_class_by_lane_column"]["SCN"]
    appear = ", ".join(f"{name} {TIMES[classes[name]]}" for name in ACTION_CLASSES if classes[name])
    assert appear == "B once, D three times, E four times"
    assert f"**Binding classes of class rule v1: {appear}.**" in section and "**Classes A and C do not appear.**" in section
    assert "**Update, 6 October 2026: overlay schema 1.1; the overlay of case SE1 is written, outside Git.**" in section
    assert "that held until this update" in section
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
    assert "not in the receipts" not in section, "every open point of this section is in the receipts since the review"
    # What the separation by rights level does not keep out of Git is said plainly, for both cases.
    assert "**They can be worked out from committed files all the same.**" in section
    assert "is nominal for case SE1" in section and "**The separation is nominal**" in section
    assert "`age_exposure_mae_sai_v1.json`" in section and "E8-OP5" in section and "E8-OP7" in section
    # The review and the runs after it are in the runs table.
    assert "**The review.**" in section and "18:29:48Z to 18:30:16Z" in section and "18:50:22Z to 18:50:31Z" in section
    assert "38 tamper attempts" in section and "twelve command-line refusals" in section
    assert "the thinned GeoJSON layers that plan stage P8 names" in section
    # One table holds values of single tambons: the eight rows of case SE1. Nothing of case O2 is given per tambon.
    rows = [line for line in section.splitlines() if re.match(r"\| TH\d{6} ", line)]
    assert [line.split()[1] for line in rows] == MAE_SAI_UNITS
    codes_outside_the_table = [line for line in section.splitlines() if re.search(r"TH\d{6}", line) and line not in rows]
    assert all("E7-OP1" in line for line in codes_outside_the_table), codes_outside_the_table
    o2_part = section.split("**Case O2: the overlay was written, outside Git.**", 1)[1].split("**Case O1: refused.**", 1)[0]
    assert not re.search(r"TH\d{6}", o2_part) and "| " not in o2_part
    assert "**The four statements above are statements about each tambon all the same.**" in o2_part
    assert "No per-tambon value of case O2 is in this file" not in section
    residents = sum(float(line.split("|")[2].replace(",", "")) for line in rows)
    assert residents == pytest.approx(se1["whole_case_checks"]["residents_of_the_rows"], abs=4.0), "eight rounded counts"


def test_the_readme_table_of_case_se1_repeats_the_report_the_receipt_binds() -> None:
    """Skipped unless the external data root is at hand: the report is outside Git."""

    external = os.environ.get(EXTERNAL_DATA_VARIABLE)
    bound = _bound(_receipt("SE1"))[0]
    report = Path(external) / bound["path"][len(EXTERNAL_LABEL) + 1:] if external else None
    if report is None or not report.is_file():
        pytest.skip(f"the SE1 overlay is outside Git; set {EXTERNAL_DATA_VARIABLE} to compare the README with it")
    assert _sha256(report) == bound["sha256"], "the report is the file the receipt binds"
    document = json.loads(report.read_text(encoding="ascii"))
    assert document["publication_eligibility"] == "local" and document["official_warning"] is False
    # Since overlay schema 1.1 (decision log R20) the file the receipt binds is the overlay itself.
    assert document["schema_version"] == "1.1" and document["case"]["case_id"] == "SE1"
    # The receipt in Git records the SHA-256 of these rows alone.
    canonical = json.dumps(document["rows"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == _receipt("SE1")["result"]["rows_sha256"]
    expected = []
    for row in document["rows"]:
        components = row["components"]
        values = [f"{components[name]['value_0_100']:.2f}" for name in (
            "flood_likelihood_0_100", "exposure_0_100", "access_gap_0_100", "road_criticality_0_100")]
        confidence = row["confidence"]
        expected.append(f"| {row['unit_id']} {row['unit_name_en']} | {confidence['measurements']['unit_residents']:,.0f} | "
                        + " | ".join(values)
                        + f" | {confidence['confidence_class']} | {', '.join(confidence['failed_conditions']) or 'none'} |")
    rows = [line for line in _section().splitlines() if re.match(r"\| TH\d{6} ", line)]
    assert rows == expected
    assert sum(1 for row in document["rows"] if row["class_v2"]["result"] == "not_evaluated") == 4
