"""The printable brief of case N1, tested on an invented N1 result shaped like the published SE1 file.

Nothing here is a place or a result of the Nan case: the rows are SE1's published rows with invented units, names,
scores, classes and confidence, and the test record and the ensemble record are invented to fit them. No Nan map,
reference or result is read.
"""

from __future__ import annotations

import copy
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest

from floodguard import planning_brief
from floodguard.wording_lint import find_violations, load_rules, python_strings

ROOT = Path(__file__).resolve().parents[1]
SE1 = ROOT / "apps" / "web" / "public" / "planning-overlays" / "mae-sai-2024" / "se1.json"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
IOU_PASS, IOU_FAIL = 0.47, 0.31


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


brief = load_script("build_n1_brief")

# (unit, English name, Thai name, score, confidence, class in effect, reason code, would-be class, failed conditions,
#  no-answer share, headline status, headline retention, would-be retention)
SPECS: tuple[tuple[Any, ...], ...] = (
    ("FX-N-01", "Fixture One", "ทดสอบหนึ่ง", 71.25, "medium", "B", "critical_route_access", None, [], 0.05,
     "headline_eligible", 0.9, None),
    ("FX-N-02", "Fixture Two", "ทดสอบสอง", 80.5, "low", "E", "low_confidence", "A", ["C1_tier", "C4_input_uncertainty"], 0.34,
     "headline_eligible", 1.0, 0.85),
    ("FX-N-03", "Fixture Three", "ทดสอบสาม", 55.0, "low", "E", "low_confidence", "D", ["C1_tier"], 0.25,
     "headline_eligible", 1.0, 0.4),
    ("FX-N-04", "Fixture Four", "ทดสอบสี่", 20.4, "medium", "E", "low_priority_score", None, [], 0.02,
     "headline_eligible", 0.7, None),
    ("FX-N-05", "Fixture Five", "ทดสอบห้า", 40.0, "low", None, "insufficient_denominator", None, ["C1_tier", "C6_residents"], 0.1,
     "not_evaluated", None, None),
)
FAILED_CASE_WOULD_BE = {"FX-N-01": "B", "FX-N-04": "E"}


def invented_result(*, passed: bool = True, fallback: bool = False, iou: float | None = None) -> dict[str, Any]:
    """An invented N1 result in the schema of se1.json: five tier T2 rows, binding and would-be (fixture, not a place)."""

    overlay = copy.deepcopy(json.loads(SE1.read_text(encoding="utf-8")))
    reference_date, pass_time = ("2025-07-31", "2025-07-31T23:08:00Z") if fallback else ("2025-07-28", "2025-07-28T11:21:00Z")
    overlay.update(dataset_mode="fixture_demo", generated_at="2026-10-20T01:02:03Z", source_timestamp=pass_time,
                   source_name="Invented N1 result (fixture, not a place)", publication_eligibility="public")
    overlay["case"] = {"case_id": "N1", "kind": "fixture", "title_en": "Case N1: an invented result (fixture, not a place)",
                       "title_th": "กรณี N1: ผลลัพธ์สมมติ (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)", "frame": "Invented frame (fixture, not a place)",
                       "case_reference_date": reference_date,
                       "fixture_notice": "Fixture, not a place: every unit, input, count and date of this file is invented."}
    flood = overlay["inputs"][0]
    flood.update(input_id="fx_nan_m1z_central", name="Invented M1-z map (fixture, not a place)", acquisition_date=pass_time[:10],
                 attribution="Contains modified Copernicus Sentinel data (2025), processed by FloodGuard",
                 licence="Copernicus Sentinel data, free, full and open access (Copernicus data policy)", source_timestamp=pass_time)
    templates = overlay["rows"]
    rows = []
    for index, spec in enumerate(SPECS):
        unit, name_en, name_th, score, level, action, reason, would_be, failed, no_answer, status, retention, _ = spec
        if not passed and level == "medium":
            level, would_be, action, reason, failed = "low", FAILED_CASE_WOULD_BE[unit], "E", "low_confidence", ["C1_tier"]
        elif not passed and "C1_tier" not in failed:
            failed = ["C1_tier", *failed]
        row = copy.deepcopy(templates[index % len(templates)])
        row.update(unit_id=unit, unit_name_en=name_en, unit_name_th=name_th, tier="T2", lane="OBS", fpps_0_100=score,
                   action_class=action, action_reason_code=reason, would_be_class=would_be)
        row["row_id"] = f"N1:{unit}:OBS"
        confidence = row["confidence"]
        confidence.update(unit_id=unit, tier="T2", lane="OBS", confidence_class=level, failed_conditions=list(failed),
                          reason_code=None if level == "medium" else reason)
        confidence["measurements"].update(t2_abstention_fraction=no_answer, unit_valid_coverage=1.0 - no_answer)
        confidence["t2_skill_condition"] = {
            "flood_input": "Invented M1-z map (fixture, not a place)",
            "status": "evaluated" if passed else "declared_unable_to_meet",
            "passes": passed and "C1_tier" not in failed, "conditions": {}, "failed_conditions": [],
            "measurements": {"geoid_held_out_test_iou": iou if iou is not None else IOU_PASS if passed else IOU_FAIL,
                             "abstention_fraction": no_answer,
                             "unit_valid_coverage": 1.0 - no_answer, "recency_days": 0},
            "thresholds": {"geoid_held_out_test_iou_min": 0.4, "mae_sai_abstention_fraction_max": 0.2,
                           "mae_sai_unit_coverage_min": 0.8, "recency_window_days": 3.0},
            "metric_wording": "agreement with an invented reference map (fixture, not a place), not accuracy"}
        row["headline_stability"] = {"guardrail": "GR8_headline_stability", "status": status, "class_retention": retention,
                                     "class_retention_min": 0.6}
        rows.append(row)
    overlay["rows"] = rows
    return overlay


def invented_test(*, passed: bool = True, dry_passes: bool = True, fallback: bool = False, run: bool = True) -> dict[str, Any]:
    """An invented test record in the shape scripts/nan_case_method.py writes (fixture, not a place)."""

    pass_time = "2025-07-31T23:08:00Z" if fallback else "2025-07-28T11:21:00Z"
    iou = IOU_PASS if passed else IOU_FAIL
    reference = ("GFM ensemble flood extent of the Sentinel-1A pass of 2025-07-31 (fallback)" if fallback
                 else "JAXA ALOS-2 Flood Proxy Map of 2025-07-28")
    test_1: dict[str, Any] = {"reference": None, "not_run": "an invented reason the reference could not be read", "passes": False}
    if run:
        test_1 = {"reference": reference, "passes": passed,
                  "central": {"compared_cells": 9000, "iou_no_answer_as_not_flagged": iou, "iou_answered_cells": iou + 0.05,
                              "flagged_that_is_reference_water": 0.72, "reference_water_flagged_no_answer_as_not_flagged": 0.55,
                              "no_answer_share": 0.12},
                  "central_interval_95": {"interval": {"iou_no_answer_as_not_flagged": [round(iou - 0.06, 6), round(iou + 0.05, 6)]}},
                  "jaxa_usability": {"why": "an invented reason: no observation-area geometry in the files" if fallback else "covered"}}
    return {
        "schema": "floodguard.nan_case_test_result.v1", "generated_at_utc": "2026-10-19T22:00:00Z",
        "source_timestamp": "invented passes (fixture, not a place)", "confidence_class": "low",
        "assumptions": ["Invented for a test (fixture, not a place)."], "official_warning": False,
        "operational_status": "non_operational", "can_feed_decision_layer": False,
        "test_1": test_1,
        "test_2": {"hours_after_theos2": 19.28, "pass": {"time_utc": "2025-07-31T23:08:00Z"},
                   "central": {"iou_no_answer_as_not_flagged": 0.29, "flagged_that_is_reference_water": 0.78,
                               "reference_water_flagged_no_answer_as_not_flagged": 0.33, "no_answer_share": 0.21},
                   "labelled_points": {"agreement": {"central": {"share_agreed_no_answer_as_not_flagged": 0.81, "points_with_a_label": 118}}}},
        "dry_control": {"pass": {"time_utc": "2025-07-31T23:08:00Z"}, "passes": dry_passes,
                        "central": {"cells": 22500, "answered_cells": 20000, "flagged_cells": 240 if dry_passes else 2400,
                                    "flagged_share_of_answered": 0.012 if dry_passes else 0.12}},
        "binding": {"test_1_passes": passed and run, "dry_control_passes": dry_passes,
                    "case_reference_date": "2025-07-31" if fallback else "2025-07-28",
                    "flood_input_of_case_N1": {"file": "fx_pass.tif", "time_utc": pass_time, "relative_orbit": 62 if fallback else 99,
                                               "platform": "Sentinel-1A" if fallback else "Sentinel-1C", "label": "fx_pass",
                                               "map": {"name": "m1z_fx_pass.tif", "sha256": "0" * 64},
                                               "days_from_the_case_reference_date_thai_calendar": 0}},
    }


def invented_run_record(overlay: dict[str, Any], *, result_sha256: str, test_sha256: str, cells: int = 90) -> dict[str, Any]:
    """An invented run record of the chain, its ensemble section fitting the rows (fixture, not a place)."""

    by_unit = {spec[0]: spec for spec in SPECS}
    headlines, would_be = {}, {}
    for row in overlay["rows"]:
        slot = row["headline_stability"]
        headlines[row["unit_id"]] = {"status": slot["status"], "class_retention": slot["class_retention"], "cells_run": cells}
        share = by_unit[row["unit_id"]][12] if row["would_be_class"] else None
        would_be[row["unit_id"]] = {"class_with_confidence_medium_in_the_default_cell": row["would_be_class"] or row["action_class"],
                                    "cells": cells, "cells_keeping_it": None if share is None else round(share * cells),
                                    "share": share, "note": "Report-only."}
    return {"schema_version": "floodguard.nan_case_chain_record.v1", "generated_at_utc": overlay["generated_at"],
            "source_timestamp": overlay["source_timestamp"], "confidence_class": "low", "assumptions": ["Invented."],
            "official_warning": False, "operational_status": "non_operational", "can_feed_decision_layer": False,
            "case": {"case_id": "N1", "tier": "T2", "lane": "OBS", "kind": "fixture"},
            "case_outcome": {"test_1_passed": overlay["rows"][0]["confidence"]["t2_skill_condition"]["status"] == "evaluated",
                             "dry_control_passed": True,
                             "read_from": {"test_result": {"path": "outputs/nan_case/test_result_v1.json", "sha256": test_sha256}}},
            "ensemble": {"summary": {"cells_run": cells}, "headline_over": f"the {cells} invented cells", "headlines": headlines,
                         "would_be_retention": would_be},
            "outputs": [{"what": "result_file", "path": "outputs/nan_case/planning_result_n1_nan_v1.json", "sha256": result_sha256}]}


def dump(path: Path, value: Any) -> str:
    data = (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def written_inputs(folder: Path, *, passed: bool = True, dry_passes: bool = True, fallback: bool = False,
                   cells: int = 90) -> tuple[Path, Path, Path]:
    """The three invented files in a folder: the result, the test record and the run record beside the result."""

    result, test, record = folder / "planning_result_n1_nan_v1.json", folder / "test_result_v1.json", folder / "planning_result_n1_nan_v1_record.json"
    overlay = invented_result(passed=passed and dry_passes, fallback=fallback, iou=IOU_PASS if passed else IOU_FAIL)
    result_sha = dump(result, overlay)
    test_sha = dump(test, invented_test(passed=passed, dry_passes=dry_passes, fallback=fallback))
    run_record = invented_run_record(overlay, result_sha256=result_sha, test_sha256=test_sha, cells=cells)
    run_record["case_outcome"].update(test_1_passed=passed, dry_control_passed=dry_passes)
    dump(record, run_record)
    return result, test, record


def views(passed: bool = True, fallback: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    overlay = invented_result(passed=passed, fallback=fallback)
    outcome = brief.outcome_of_the_test(invented_test(passed=passed, fallback=fallback))
    record = invented_run_record(overlay, result_sha256="a" * 64, test_sha256="b" * 64)
    return overlay, outcome, brief.ensemble_view(record, overlay, result_sha256="a" * 64)


MADE_FROM = [{"what": "result_file", "path": "invented/result.json", "sha256": "1" * 64}]


def visible_text(page: str) -> str:
    """The words of an HTML page, as a reader sees them."""

    return html.unescape(re.sub(r"<style>.*?</style>|<[^>]+>", " ", page, flags=re.S))


# ---------------------------------------------------------------------------
# The rows
# ---------------------------------------------------------------------------


def test_each_row_says_whether_its_class_is_binding_or_would_be() -> None:
    overlay, _outcome, ensemble = views()
    rows = {row["unit_id"]: row for row in brief.n1_rows(overlay, ensemble)}
    assert [row["unit_id"] for row in brief.n1_rows(overlay, ensemble)] == ["FX-N-02", "FX-N-01", "FX-N-03", "FX-N-05", "FX-N-04"]
    assert (rows["FX-N-01"]["kind"], rows["FX-N-01"]["shown"], rows["FX-N-01"]["holds"]) == ("binding", "B", 0.9)
    assert (rows["FX-N-02"]["kind"], rows["FX-N-02"]["shown"], rows["FX-N-02"]["class_in_effect"]) == ("would_be", "A", "E")
    assert rows["FX-N-02"]["holds"] == 0.85 and rows["FX-N-02"]["holds_ok"] is True
    assert rows["FX-N-03"]["holds"] == 0.4 and rows["FX-N-03"]["holds_ok"] is False, "a would-be class under 60% is marked"
    assert (rows["FX-N-04"]["kind"], rows["FX-N-04"]["shown"]) == ("binding", "E")
    assert (rows["FX-N-05"]["kind"], rows["FX-N-05"]["shown"], rows["FX-N-05"]["holds"]) == ("no_class", None, None)
    assert brief.reason_of(rows["FX-N-01"]) == ("route access", "การเข้าถึงเส้นทาง")
    assert brief.reason_of(rows["FX-N-02"]) == ("C1 C4", "C1 C4") and brief.reason_of(rows["FX-N-05"]) == ("C1 C6", "C1 C6")
    assert brief.reason_of(rows["FX-N-04"])[0] == "score under 35"
    # Without the ensemble record a would-be class has no stability figure; a binding class keeps its headline slot.
    bare = {row["unit_id"]: row for row in brief.n1_rows(overlay)}
    assert bare["FX-N-02"]["holds"] is None and bare["FX-N-01"]["holds"] == 0.9


def test_a_row_that_breaks_the_class_rules_is_refused() -> None:
    overlay = invented_result()
    overlay["rows"][0]["would_be_class"] = "A"   # a would-be class beside a medium-confidence row
    with pytest.raises(brief.N1BriefError, match="would-be"):
        brief.n1_rows(overlay)
    overlay = invented_result()
    overlay["rows"][1]["action_class"] = "B"     # a low-confidence row whose class in effect is not E
    with pytest.raises(brief.N1BriefError, match="class E"):
        brief.n1_rows(overlay)
    overlay = invented_result()
    overlay["rows"][0]["action_class"] = "F"
    with pytest.raises(brief.N1BriefError, match="outside A to E"):
        brief.n1_rows(overlay)


# ---------------------------------------------------------------------------
# What the brief says
# ---------------------------------------------------------------------------


def test_both_forms_carry_every_part_the_brief_promises() -> None:
    overlay, outcome, ensemble = views()
    for text in (brief.render_markdown(overlay, outcome, ensemble, made_from=MADE_FROM),
                 visible_text(brief.render_html(overlay, outcome, ensemble, made_from=MADE_FROM))):
        # What the case is, and the test outcome in one line.
        assert "our own radar flood map" in text and "tested once against another satellite's map" in text
        assert "JAXA ALOS-2 Flood Proxy Map of 2025-07-28" in text and "แผนที่จากดาวเทียมอีกดวงหนึ่ง" in text
        assert "Test outcome: both tests met the bars fixed before the test" in text and "IoU 0.47" in text
        assert "95% interval 0.41 to 0.52" in text and "no answer on 12% of the compared cells" in text
        assert "Dry control on hills with no flood: 1.2% of the answered cells flagged" in text
        assert "ผลการทดสอบ:" in text and "ไม่ใช่ความแม่นยำ" in text
        # Each tambon: name in both languages, score, class, binding or would-be, reason, confidence.
        for spec in SPECS:
            assert spec[1] in text and spec[2] in text
        assert "71.2" in text and "80.5" in text and "would-be" in text and "จะได้" in text and "binding" in text and "มีผล" in text
        assert "route access" in text and "C1 C4" in text and "C4: the share of residents inside the mapped water" in text
        assert "C6: fewer than 100 modelled residents." in text
        assert "Confidence: 2 of 5 tambons medium, 3 low; 2 binding classes, 2 would-be classes; 1 with no class" in text
        # Source times, stability, the planning-only line, the official line and the Thai note.
        assert "radar pass 2025-07-28 11:21 UTC (2025-07-28 18:21 Thai time), Sentinel-1C, relative orbit 99" in text
        assert "Test run 2026-10-19T22:00:00Z" in text and "Result made 2026-10-20T01:02:03Z" in text
        assert "OpenStreetMap retrieved 2026-07-10T02:46:49Z" in text
        assert "Stability over the ensemble (report-only): 90 runs of the chain" in text and "no population axis" in text
        assert "holds in at least 60% of the runs for 3 of 4 tambons with a figure; it does not for Fixture Three" in text
        assert "85%" in text and "40%*" in text
        assert "Planning guidance. Not an official warning, and not real-time" in text and "ไม่ใช่คำเตือนอย่างเป็นทางการ" in text
        assert "Class E never means safe" in text and planning_brief.OFFICIAL[0] in text
        assert planning_brief.THAI_NOTE[0] in text and planning_brief.THAI_NOTE[1] in text
        assert "Provided by JAXA" in text and "no part of the map" in text and "1" * 64 in text
        assert "Fixture, not a place" in text
        assert "\r" not in text


def test_with_all_180_runs_the_population_axis_is_named() -> None:
    overlay = invented_result()
    record = invented_run_record(overlay, result_sha256="a" * 64, test_sha256="b" * 64, cells=180)
    lines = brief.stability_lines(brief.n1_rows(overlay), brief.ensemble_view(record, overlay, result_sha256="a" * 64))
    assert "180 runs" in lines[0][0] and "the population data (2: WorldPop 2020 and its 2024 rescale)" in lines[0][0]


def test_many_tambons_whose_class_does_not_hold_are_marked_in_the_table_not_listed() -> None:
    rows = [{"name_en": f"Fixture {index}", "name_th": f"ทดสอบ {index}", "holds": 0.3, "holds_ok": False, "holds_min": 0.6}
            for index in range(brief.UNSTABLE_NAMES_MAX + 1)]
    lines = brief.stability_lines(rows, None)
    assert "the other 6 are marked * in the table: verify before use." in lines[1][0] and "Fixture 0" not in lines[1][0]
    assert "อีก 6 ตำบลมีเครื่องหมาย * ในตาราง" in lines[1][1]


def test_the_fallback_is_worded_as_a_same_pass_map_not_another_satellite() -> None:
    overlay, outcome, ensemble = views(fallback=True)
    text = brief.render_markdown(overlay, outcome, ensemble, made_from=MADE_FROM)
    assert "the Copernicus Emergency Management Service map of the same Sentinel-1 pass" in text
    assert "not independent of ours" in text and "another satellite's map" not in text and "Provided by JAXA" not in text
    assert "Global Flood Monitoring (GFM): only figures computed from it are shown" in text
    assert "2025-07-31 23:08 UTC" in text and "case reference date 2025-07-31" in text


def test_a_failed_case_test_makes_every_class_e_with_its_would_be_class() -> None:
    overlay = invented_result(passed=False)
    outcome = brief.outcome_of_the_test(invented_test(passed=False))
    text = brief.render_markdown(overlay, outcome, None, made_from=MADE_FROM)
    assert "Test outcome: test 1 did not meet its bar, so every class is E (low confidence), with its would-be class beside it." in text
    assert "IoU 0.31" in text and "การทดสอบที่ 1 ไม่ผ่านเกณฑ์" in text
    rows = brief.n1_rows(overlay)
    assert all(row["kind"] in ("would_be", "no_class") for row in rows)
    assert "the ensemble record was not given to this brief" in text
    dry = brief.outcome_of_the_test(invented_test(passed=True, dry_passes=False))
    assert brief.verdict(dry)[0].startswith("the dry control did not meet its bar")
    neither = brief.outcome_of_the_test(invented_test(passed=False, dry_passes=False))
    assert brief.verdict(neither)[0].startswith("neither test met its bar")
    not_run = brief.outcome_of_the_test(invented_test(run=False))
    assert brief.verdict(not_run)[0].startswith("test 1 could not be run")
    assert "could not be run (an invented reason" in brief.case_line(not_run, invented_result())[0]


def test_the_page_is_one_self_contained_a4_landscape_document() -> None:
    overlay, outcome, ensemble = views()
    page = brief.render_html(overlay, outcome, ensemble, made_from=MADE_FROM)
    assert page.startswith("<!doctype html>") and "size: A4 landscape" in page and '<meta charset="utf-8">' in page
    assert "<script" not in page and "http://" not in page and "https://" not in page and "<link" not in page and "@import" not in page
    assert page.count("<table>") == 2, "the rows are printed in two tables side by side"
    assert 'class="class would_be cA"' in page and 'class="class binding cB"' in page


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_a_file_that_is_not_a_public_n1_result_is_refused() -> None:
    cases = [({"official_warning": True}, "official warning"), ({"operational_status": "operational"}, "official warning"),
             ({"publication_eligibility": "local"}, "public level"), ({"accepted_fpps": 50.0}, "accepted_fpps"),
             ({"can_feed_decision_layer": True}, "decision layer"), ({"rows": []}, "no row")]
    for change, words in cases:
        with pytest.raises(brief.N1BriefError, match=words):
            brief.check_result({**invented_result(), **change})
    n2 = invented_result()
    n2["case"]["case_id"] = "N2"
    with pytest.raises(brief.N1BriefError, match="case N2 stay in the work folder"):
        brief.check_result(n2)
    with pytest.raises(brief.N1BriefError, match="test record is"):
        brief.outcome_of_the_test({**invented_test(), "schema": "another"})
    with pytest.raises(brief.N1BriefError, match="test 1 passed while"):
        record = invented_test()
        record["test_1"]["central"]["iou_no_answer_as_not_flagged"] = 0.3
        brief.outcome_of_the_test(record)


def test_files_that_are_not_of_one_run_are_refused() -> None:
    overlay, outcome, _ensemble = views()
    later = copy.deepcopy(overlay)
    later["case"]["case_reference_date"] = "2025-07-31"
    with pytest.raises(brief.N1BriefError, match="case reference date"):
        brief.check_together(later, outcome, None, test_sha256="b" * 64)
    moved = copy.deepcopy(overlay)
    moved["inputs"][0]["source_timestamp"] = "2025-07-26T23:16:00Z"
    with pytest.raises(brief.N1BriefError, match="radar pass"):
        brief.check_together(moved, outcome, None, test_sha256="b" * 64)
    other_figure = copy.deepcopy(overlay)
    other_figure["rows"][0]["confidence"]["t2_skill_condition"]["measurements"]["geoid_held_out_test_iou"] = 0.52
    with pytest.raises(brief.N1BriefError, match="test 1 figure"):
        brief.check_together(other_figure, outcome, None, test_sha256="b" * 64)
    other_verdict = copy.deepcopy(overlay)
    other_verdict["rows"][0]["confidence"]["t2_skill_condition"]["status"] = "declared_unable_to_meet"
    with pytest.raises(brief.N1BriefError, match="another case-level test outcome"):
        brief.check_together(other_verdict, outcome, None, test_sha256="b" * 64)
    record = invented_run_record(overlay, result_sha256="a" * 64, test_sha256="b" * 64)
    with pytest.raises(brief.N1BriefError, match="another result file"):
        brief.ensemble_view(record, overlay, result_sha256="c" * 64)
    shifted = copy.deepcopy(record)
    shifted["ensemble"]["headlines"]["FX-N-01"]["class_retention"] = 0.5
    with pytest.raises(brief.N1BriefError, match="not the one of its row"):
        brief.ensemble_view(shifted, overlay, result_sha256="a" * 64)
    view = brief.ensemble_view(record, overlay, result_sha256="a" * 64)
    with pytest.raises(brief.N1BriefError, match="read another test record"):
        brief.check_together(overlay, outcome, view, test_sha256="d" * 64)
    work = {"case_id": "N1", "generated_at_utc": "2026-10-21T00:00:00Z", "official_warning": False,
            "operational_status": "non_operational", "headlines": record["ensemble"]["headlines"], "ensemble": {"summary": {}}}
    with pytest.raises(brief.N1BriefError, match="another run of the chain"):
        brief.ensemble_view(work, overlay, result_sha256="a" * 64)
    work["generated_at_utc"] = overlay["generated_at"]
    assert brief.ensemble_view(work, overlay, result_sha256="a" * 64)["cells_run"] == 90
    with pytest.raises(brief.N1BriefError, match="not N1"):
        brief.ensemble_view({**work, "case_id": "N2"}, overlay, result_sha256="a" * 64)


def test_the_firewall_of_the_case_is_kept(tmp_path: Path) -> None:
    for path in (tmp_path / "jaxa_sealed" / "JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip",
                 tmp_path / "water_v2_chip_003_2m.tif", tmp_path / "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif"):
        with pytest.raises(brief.N1BriefError, match="never opens it"):
            brief.build(path, tmp_path / "test.json", None, tmp_path / "out")
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_the_build_writes_the_brief_and_its_record(tmp_path: Path) -> None:
    result, test, record = written_inputs(tmp_path / "in")
    summary = brief.build(result, test, record, tmp_path / "out", generated_at="2026-10-21T00:00:00Z")
    names = [item["name"] for item in summary["files"]]
    assert names == ["n1_nan_brief.md", "n1_nan_brief.html", "n1_nan_brief_record.json"]
    for item in summary["files"]:
        data = (tmp_path / "out" / item["name"]).read_bytes()
        assert b"\r" not in data and hashlib.sha256(data).hexdigest() == item["sha256"] and len(data) == item["bytes"]
    written = json.loads((tmp_path / "out" / "n1_nan_brief_record.json").read_text(encoding="utf-8"))
    for key in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert written[key]
    assert written["official_warning"] is False and written["operational_status"] == "non_operational"
    assert written["can_feed_decision_layer"] is False and written["confidence_class"] == "low"
    assert written["source_timestamp"] == "2025-07-28T11:21:00Z" and written["ensemble_record"]["cells_run"] == 90
    assert [item["what"] for item in written["made_from"]] == ["result_file", "test_record", "ensemble_record"]
    assert written["made_from"][0]["sha256"] == hashlib.sha256(result.read_bytes()).hexdigest()
    assert written["classes_on_the_brief"]["FX-N-02"] == {"class_in_effect": "E", "would_be_class": "A", "shown": "A",
                                                          "kind": "would_be", "confidence_class": "low"}
    page = (tmp_path / "out" / "n1_nan_brief.html").read_text(encoding="utf-8")
    assert hashlib.sha256(test.read_bytes()).hexdigest() in page
    # Nothing it read was changed.
    assert written["made_from"][1]["sha256"] == hashlib.sha256(test.read_bytes()).hexdigest()


def test_the_command_line_finds_the_run_record_and_refuses_with_code_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result, test, _record = written_inputs(tmp_path / "in")
    assert brief.main(["--result", str(result), "--test-result", str(test), "--out-dir", str(tmp_path / "out")]) == 0
    written = json.loads((tmp_path / "out" / "n1_nan_brief_record.json").read_text(encoding="utf-8"))
    assert written["made_from"][2]["what"] == "ensemble_record", "the run record beside the result file is read"
    assert brief.main(["--result", str(result), "--test-result", str(test), "--no-ensemble", "--out-dir", str(tmp_path / "bare")]) == 0
    assert "was not given to this brief" in (tmp_path / "bare" / "n1_nan_brief.md").read_text(encoding="utf-8")
    # A fixture is never written into the brief folder of the repository.
    assert brief.main(["--result", str(result), "--test-result", str(test)]) == 2
    assert "never written into outputs/planning_brief" in capsys.readouterr().err
    committed = ROOT / "outputs" / "planning_brief" / "n1_nan_brief.md"
    assert not committed.exists() or "Fixture, not a place" not in committed.read_text(encoding="utf-8")


def test_the_fallback_and_the_full_ensemble_go_through_the_build(tmp_path: Path) -> None:
    result, test, record = written_inputs(tmp_path / "in", fallback=True, cells=180)
    brief.build(result, test, record, tmp_path / "out")
    text = (tmp_path / "out" / "n1_nan_brief.md").read_text(encoding="utf-8")
    assert "same Sentinel-1 pass" in text and "180 runs" in text
    result, test, record = written_inputs(tmp_path / "failed", passed=False)
    brief.build(result, test, record, tmp_path / "out_failed")
    assert "test 1 did not meet its bar" in (tmp_path / "out_failed" / "n1_nan_brief.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Wording, and SE1 unchanged
# ---------------------------------------------------------------------------


def lint(text: str, source: str) -> list[str]:
    # "agreement with <reference>, not accuracy" is the wording the case asks for; the replay page's rules have no
    # allowance for it, so it is taken out before the rest is checked (as in tests/test_nan_case_m1z.py).
    return [finding.describe() for finding in find_violations(text.replace("not accuracy", ""), RULES, source)]


def test_the_wording_passes_the_shared_lint() -> None:
    strings = python_strings((ROOT / "scripts" / "build_n1_brief.py").read_text(encoding="utf-8"))
    assert [finding for text in strings for finding in lint(text, "build_n1_brief.py")] == []
    for passed, fallback in ((True, False), (False, False), (True, True)):
        overlay, outcome, ensemble = views(passed=passed, fallback=fallback)
        for name, text in (("md", brief.render_markdown(overlay, outcome, ensemble, made_from=MADE_FROM)),
                           ("html", visible_text(brief.render_html(overlay, outcome, ensemble, made_from=MADE_FROM)))):
            assert lint(text, name) == []
            for word in ("accurate", "validated", "precision", "recall", "real-time detection", "forecast"):
                assert word not in text.lower()


def test_the_se1_brief_is_unchanged() -> None:
    """The SE1 brief, made again from its published file with the reused module, has the bytes of the committed files."""

    se1 = load_script("build_se1_brief")
    record_path = ROOT / se1.OUTPUT_DIR / f"{se1.NAME}_record.json"
    if not record_path.exists():
        pytest.skip("the SE1 brief has not been written")
    source = ROOT / se1.PUBLISHED
    overlay = json.loads(source.read_text(encoding="utf-8"))
    note = None
    if (ROOT / se1.STABILITY).exists():
        note = se1.stability_note(overlay, json.loads((ROOT / se1.STABILITY).read_text(encoding="utf-8")))
    arguments = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "source_path": se1.PUBLISHED, "stability_note": note}
    folder = ROOT / se1.OUTPUT_DIR
    assert planning_brief.render_markdown(overlay, **arguments).encode("utf-8") == (folder / f"{se1.NAME}.md").read_bytes()
    assert planning_brief.render_html(overlay, **arguments).encode("utf-8") == (folder / f"{se1.NAME}.html").read_bytes()
