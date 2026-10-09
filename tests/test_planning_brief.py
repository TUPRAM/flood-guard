"""The printable brief of a published planning result: every value is a value of the published file."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from floodguard import planning_brief

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "outputs" / "planning_v1" / "overlays" / "planning_assessment_overlay_se1_mae_sai.json"
FOLDER = ROOT / "outputs" / "planning_brief"
OVERLAY = json.loads(PUBLISHED.read_text(encoding="utf-8"))
ARGUMENTS = {"source_sha256": "0" * 64, "source_path": "invented/path.json"}


def test_every_row_of_the_brief_is_a_row_of_the_published_file() -> None:
    rows = planning_brief.rows_of(OVERLAY)
    published = {row["unit_id"]: row for row in OVERLAY["rows"]}
    assert [row["unit_id"] for row in rows] == [row["unit_id"] for row in sorted(OVERLAY["rows"], key=lambda item: -item["fpps_0_100"])]
    for row in rows:
        source = published[row["unit_id"]]
        assert row["class"] == source["action_class"] and row["score"] == source["fpps_0_100"]
        assert row["confidence"] == source["confidence"]["confidence_class"]
        assert row["lose_routes"] == source["components"]["road_criticality_0_100"]["inputs"]["residents_losing_all_routes"]


def test_both_forms_carry_the_status_the_source_time_the_confidence_and_the_assumptions() -> None:
    for text in (planning_brief.render_markdown(OVERLAY, **ARGUMENTS), planning_brief.render_html(OVERLAY, **ARGUMENTS)):
        assert "Not an official warning" in text and "ไม่ใช่คำเตือนอย่างเป็นทางการ" in text
        assert "2024-08-01 to 2024-10-12" in text and OVERLAY["generated_at"] in text
        assert "Class E never means safe" in text and "not evaluated in the published result" in text
        assert "not reviewed by a native speaker" in text and "CC BY-SA 4.0" in text and "0" * 64 in text
        for english, thai in planning_brief.ASSUMPTIONS:
            assert english in text and thai in text
        for row in OVERLAY["rows"]:
            assert row["unit_name_en"] in text and row["unit_name_th"] in text
        assert "\r" not in text


def test_the_page_is_one_self_contained_document() -> None:
    page = planning_brief.render_html(OVERLAY, **ARGUMENTS)
    assert page.startswith("<!doctype html>") and "A4 landscape" in page
    assert "<script" not in page and "http://" not in page and "https://" not in page, "nothing is loaded from outside"


def test_a_report_only_note_is_added_beside_the_published_status_never_in_place_of_it() -> None:
    text = planning_brief.render_markdown(OVERLAY, stability_note=("An invented note.", "หมายเหตุสมมติ"), **ARGUMENTS)
    assert "An invented note." in text and "not evaluated in the published result" in text


def test_a_file_that_is_not_a_planning_result_is_refused() -> None:
    warning = {**OVERLAY, "official_warning": True}
    with pytest.raises(planning_brief.PlanningBriefError):
        planning_brief.rows_of(warning)
    classless = copy.deepcopy(OVERLAY)
    classless["rows"][0]["action_class"] = None
    with pytest.raises(planning_brief.PlanningBriefError):
        planning_brief.rows_of(classless)
    with pytest.raises(planning_brief.PlanningBriefError):
        planning_brief.rows_of({**OVERLAY, "rows": []})


def test_the_committed_brief_is_the_brief_of_the_published_file() -> None:
    record_path = FOLDER / "se1_mae_sai_brief_record.json"
    if not record_path.exists():
        pytest.skip("the brief has not been written")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False and record["source_timestamp"] and record["assumptions"]
    assert hashlib.sha256(PUBLISHED.read_bytes()).hexdigest() == record["made_from"]["sha256"], "the published file is unchanged"
    assert record["classes_on_the_brief"] == {row["unit_id"]: row["action_class"] for row in OVERLAY["rows"]}
    for item in record["files"]:
        data = (FOLDER / item["name"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"] and b"\r" not in data
    note = record["stability_note_from"]
    if note is not None:
        assert hashlib.sha256((ROOT / note["path"]).read_bytes()).hexdigest() == note["sha256"]
        assert "not part of the published result" in (FOLDER / "se1_mae_sai_brief.md").read_text(encoding="utf-8")
