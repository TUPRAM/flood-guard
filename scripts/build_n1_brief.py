"""Write the printable Thai and English brief of case N1 from its result file, its test record and its ensemble record.

Case N1 of the Nan protocol (``docs/proposal_execution/nan_case_protocol_v1.json``, decision log R51 and R52) puts
the project's own radar flood map, frozen before the test and tested once against another map, through the planning
chain to a score and a class per tambon. This script makes the one-page brief of that result from three files and
from nothing else:

* the result file of case N1, in the planning-overlay schema of
  ``apps/web/public/planning-overlays/mae-sai-2024/se1.json`` (written by ``scripts/nan_case_chain.py nan --case N1``);
* the test record ``outputs/nan_case/test_result_v1.json`` (written by ``scripts/nan_case_method.py test``);
* the ensemble record: the run record the chain writes beside the result file (its ``ensemble`` section), or the
  ensemble document of the work folder (``score_chain/ensemble_n1.json``). Without it the brief says so.

It writes ``outputs/planning_brief/n1_nan_brief.md``, the same brief as one self-contained HTML page that prints on
one sheet (A4, landscape), and ``n1_nan_brief_record.json`` (what the brief was made from). The brief carries what the
case is, the test outcome in one line, each tambon's score, class, whether the class is binding or would-be (low
confidence) and its reason, the source times, the confidence, the stability over the ensemble, the planning-only
line and the line that the Thai text is not reviewed by a native speaker. It reuses ``floodguard.planning_brief``
(the brief of case SE1) and changes nothing of it.

The three files are checked against each other before anything is written: the same case reference date, the same
radar pass, the same test 1 figure, and an ensemble record of this result file. A result of case N2 is refused (its
per-tambon results stay in the work folder, protocol ``rights_in_git``), as is any path behind the firewall of the
case. Every figure is agreement with another map, not accuracy. Planning guidance only; not an official warning.

Example (from the repository root, after the chain has written the N1 result)::

    python scripts/build_n1_brief.py
    python scripts/build_n1_brief.py --result outputs/nan_case/planning_result_n1_nan_v1.json \\
        --test-result outputs/nan_case/test_result_v1.json \\
        --ensemble outputs/nan_case/planning_result_n1_nan_v1_record.json
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import planning_brief  # noqa: E402
from floodguard.nan_case_chain import (  # noqa: E402
    NAN_ANSWERED_SHARE_MIN,
    NAN_NO_ANSWER_SHARE_MAX,
    NAN_PASS_WINDOW_DAYS,
    NAN_TEST_IOU_MIN,
    firewall_refusal,
)

RESULT_CANDIDATES: tuple[str, ...] = ("outputs/nan_case/n1_result_v1.json", "outputs/nan_case/planning_result_n1_nan_v1.json")
"""Where the N1 result file is looked for, in this order: the name of the task, then the name the chain writes."""
TEST_RESULT = "outputs/nan_case/test_result_v1.json"
OUTPUT_DIR = "outputs/planning_brief"
NAME = "n1_nan_brief"
CASE_ID = "N1"
TEST_SCHEMA = "floodguard.nan_case_test_result.v1"
FALLBACK_REFERENCE_DATE = "2025-07-31"
"""The case reference date under the fallback of test 1 (the GFM map of the same pass)."""
DRY_CONTROL_MAX_SHARE = 0.05
"""Protocol ``tests.test_2_town_and_dry_control.dry_control``: our map flags at most 0.05 of the dry chip's answered cells."""
PASS_TIME_TOLERANCE_MINUTES = 60
THAI_OFFSET = timedelta(hours=7)
EXIT_DONE, EXIT_REFUSED = 0, 2

BINDING, WOULD_BE, NO_CLASS = "binding", "would_be", "no_class"
"""How the class of a row is read: the class in effect at its confidence; a would-be class beside a binding E (low
confidence); no class (guardrail GR1, fewer residents than the minimum)."""
KIND_LABELS: dict[str, tuple[str, str]] = {
    BINDING: ("binding", "มีผล"),
    WOULD_BE: ("would-be", "จะได้"),
    NO_CLASS: ("no class", "ไม่มีระดับ"),
}
REASON_SHORT: dict[str, tuple[str, str]] = {
    "life_safety_exposure": ("life safety", "ความปลอดภัยของชีวิต"),
    "critical_route_access": ("route access", "การเข้าถึงเส้นทาง"),
    "essential_service_access": ("essential services", "บริการจำเป็น"),
    "resilience": ("no urgent trigger", "ไม่มีเงื่อนไขเร่งด่วน"),
    "low_priority_score": ("score under 35", "คะแนนต่ำกว่า 35"),
}
"""The reason code of a binding class, in a few words (``floodguard.scoring.ACTION_REASON_CODES``)."""
CLASS_COLOURS: dict[str, str] = {"A": "#08519C", "B": "#3182BD", "C": "#6BAED6", "D": "#BDD7E7", "E": "#F59E0B"}
"""The class colours of the site's map (``apps/web/src/components/geo-map.tsx``)."""
CONDITION_ORDER: tuple[str, ...] = ("C1_tier", "C2_recency", "C3_coverage", "C4_input_uncertainty", "C5_components",
                                    "C6_residents", "C7_baseline_no_route", "C8_hospital")

STATUS = ("Planning guidance. Not an official warning, and not real-time: one radar pass, tested once against another map "
          "before it fed the score.",
          "ข้อมูลประกอบการวางแผน ไม่ใช่คำเตือนอย่างเป็นทางการ และไม่ใช่ข้อมูลแบบเรียลไทม์ ใช้ภาพเรดาร์รอบเดียว "
          "ซึ่งทดสอบกับแผนที่อื่นหนึ่งครั้งก่อนนำมาคำนวณคะแนน")
NEVER_SAFE = ("Class E never means safe. It means lower relative priority, or low confidence, in this case.",
              "ระดับ E ไม่ได้หมายความว่าปลอดภัย หมายถึงลำดับความสำคัญต่ำกว่าเมื่อเทียบกัน หรือความเชื่อมั่นต่ำ ในกรณีนี้")
BINDING_NOTE = ("Binding: the class stands at its confidence. Would-be (striped): confidence is low, so the class in effect "
                "is E; the class shown is what the score would give at medium confidence, never binding. Check on the "
                "ground first.",
                "มีผล: ระดับนี้ใช้ได้ตามความเชื่อมั่นที่ระบุ  จะได้ (ลายทาง): ความเชื่อมั่นต่ำ ระดับที่มีผลจึงเป็น E "
                "ส่วนระดับที่แสดงคือระดับที่คะแนนจะให้หากความเชื่อมั่นปานกลาง ไม่มีผลบังคับใช้ ควรตรวจสอบในพื้นที่ก่อน")
ASKS: dict[str, tuple[str, str]] = {
    **planning_brief.CLASS_ASKS,
    "D": ("No urgent trigger on this radar pass. Plan drainage, routes and shelters before the season.",
          "ไม่มีเงื่อนไขเร่งด่วนจากภาพเรดาร์รอบนี้ วางแผนระบบระบายน้ำ เส้นทาง และศูนย์พักพิงก่อนถึงฤดูฝน"),
    "E": ("Lower relative priority on this radar pass, or low confidence. Keep watching and check on the ground.",
          "ลำดับความสำคัญต่ำกว่าเมื่อเทียบกันจากภาพเรดาร์รอบนี้ หรือความเชื่อมั่นต่ำ เฝ้าติดตามและตรวจสอบในพื้นที่"),
}
"""What each class asks: the SE1 brief's wording for A to C, and D and E said of one radar pass, not of a season scenario."""
ASSUMPTIONS: tuple[tuple[str, str], ...] = (
    ("Road closures are modelled from the radar map by closure rule v1. No closure was observed.",
     "การปิดถนนเป็นการจำลองจากแผนที่เรดาร์ตามกฎการปิดถนน v1 ไม่ใช่การปิดถนนที่สังเกตได้จริง"),
    planning_brief.ASSUMPTIONS[1],
    ("The radar map is the project's own map, frozen before the test and used as computed. Where the radar gives no "
     "answer, a cell counts as not flooded.",
     "แผนที่เรดาร์เป็นแผนที่ของโครงการเอง ตรึงค่าไว้ก่อนการทดสอบและใช้ตามที่คำนวณได้ เซลล์ที่เรดาร์ไม่มีคำตอบนับว่าไม่ท่วม"),
    ("Radar does not see water under trees, between buildings or under crops, nor water that drained before the pass.",
     "เรดาร์มองไม่เห็นน้ำใต้ต้นไม้ ระหว่างอาคาร หรือใต้พืชผล และน้ำที่ระบายไปแล้วก่อนดาวเทียมโคจรผ่าน"),
    ("Every figure is agreement with another map, not accuracy. The score is not accepted for decisions "
     "(accepted_fpps stays null).",
     "ทุกตัวเลขเป็นความสอดคล้องกับแผนที่อื่น ไม่ใช่ความแม่นยำ คะแนนนี้ยังไม่ได้รับการยอมรับให้ใช้ตัดสินใจ (accepted_fpps เป็นค่าว่าง)"),
)
COLUMNS: tuple[tuple[str, str], ...] = (
    ("Tambon", "ตำบล"), ("FPPS", "คะแนน"), ("Class", "ระดับ"), ("Binding or would-be", "มีผลหรือจะได้"),
    ("Confidence", "ความเชื่อมั่น"), ("No answer", "ไม่มีคำตอบ"), ("Reason", "เหตุผล"), ("Holds", "คงเดิม"),
)
HOLDS_NOTE = ("Holds: the share of the ensemble's runs that keep the class shown (a would-be class: at medium confidence). "
              "* under {minimum}: verify before use.",
              "คงเดิม: สัดส่วนของรอบการคำนวณที่ให้ระดับเดียวกับที่แสดง (ระดับที่จะได้: เมื่อความเชื่อมั่นปานกลาง) "
              "* ต่ำกว่า {minimum}: ควรตรวจสอบก่อนใช้งาน")
NO_ANSWER_NOTE = ("No answer: the share of the tambon's land outside permanent water where the radar map gives no answer, "
                  "such as trees or buildings on low ground.",
                  "ไม่มีคำตอบ: สัดส่วนพื้นที่ของตำบล (ไม่รวมแหล่งน้ำถาวร) ที่แผนที่เรดาร์ไม่ให้คำตอบ เช่น ต้นไม้หรือสิ่งปลูกสร้างบนที่ต่ำ")
UNSTABLE_NAMES_MAX = 5
"""Up to this many tambons whose class does not hold are named in the stability line; beyond it the table's * marks them."""


class N1BriefError(planning_brief.PlanningBriefError):
    """The files do not hold what the brief of case N1 needs, or they do not belong together."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def label_of(path: Path, external_root: Path | None = None) -> str:
    """Name a file without a machine path: relative to the repository, to the external data root, or by its name."""

    resolved = Path(path).resolve()
    for base, prefix in ((ROOT, ""), (external_root, "<external data root>/")):
        if base is None:
            continue
        try:
            return prefix + resolved.relative_to(Path(base).resolve()).as_posix()
        except ValueError:
            continue
    return resolved.name


def refuse_behind_the_firewall(paths: Sequence[Path | None]) -> None:
    """Refuse a path behind the firewall of the Nan case before anything is opened.

    Raises:
        N1BriefError: for a path in the sealed JAXA folder or a THEOS-2 file of 31 July 2025 or derived from it.
    """

    for path in paths:
        if path is None:
            continue
        why = firewall_refusal(path)
        if why is not None:
            raise N1BriefError(why.replace("the chain never opens it", "the brief never opens it"))


def read_json(path: Path) -> tuple[Any, str]:
    """A JSON file and the SHA-256 of its bytes."""

    data = Path(path).read_bytes()
    return json.loads(data.decode("utf-8")), sha256_bytes(data)


def share_text(value: float | None) -> str:
    """A share as a percentage: one decimal under 10%, whole numbers above; ``n/a`` when missing."""

    if value is None:
        return "n/a"
    percent = 100.0 * float(value)
    return f"{percent:.1f}%" if percent < 10.0 else f"{percent:.0f}%"


def figure_text(value: float | None) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def parse_utc(text: Any) -> datetime | None:
    """An instant written as ``2025-07-28T11:21:00Z`` (or with an offset), or ``None``."""

    if not text:
        return None
    try:
        value = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# The three files
# ---------------------------------------------------------------------------


def check_result(overlay: Mapping[str, Any]) -> None:
    """Refuse a file that is not a non-operational, public result of case N1.

    Raises:
        N1BriefError: for an official warning or an operational file, another case (N2 stays outside Git), a level
            below public, an accepted score or class, a file that may feed the decision layer, or a file with no row.
    """

    if overlay.get("official_warning") is not False or overlay.get("operational_status") != "non_operational":
        raise N1BriefError("a brief is made only from a result that says it is not operational and not an official warning")
    case = overlay.get("case") or {}
    if case.get("case_id") != CASE_ID:
        raise N1BriefError(f"this brief is of case N1; the file is of case {case.get('case_id')!r} (the per-tambon results of "
                           "case N2 stay in the work folder)")
    if overlay.get("publication_eligibility") != "public":
        raise N1BriefError("the brief is published: its result file must be at the public level (guardrail GR6)")
    if overlay.get("accepted_fpps") is not None or overlay.get("accepted_action_class") is not None:
        raise N1BriefError("accepted_fpps and accepted_action_class stay null in the Nan case")
    if overlay.get("can_feed_decision_layer") is not False:
        raise N1BriefError("a result of the Nan case never feeds the decision layer")
    if not overlay.get("rows"):
        raise N1BriefError("the result file holds no row")


def flood_input_of(overlay: Mapping[str, Any]) -> Mapping[str, Any]:
    """The lineage record of the flood input of a result file."""

    for item in overlay.get("inputs") or []:
        if item.get("role") == "flood_input":
            return item
    raise N1BriefError("the result file names no flood input")


def outcome_of_the_test(test: Mapping[str, Any]) -> dict[str, Any]:
    """The figures of the test record the brief and the slide read.

    Raises:
        N1BriefError: for a file that is not the test record of the case, or whose verdict does not fit its figures.
    """

    if test.get("schema") != TEST_SCHEMA:
        raise N1BriefError(f"the test record is {TEST_SCHEMA}; the file is {test.get('schema')!r}")
    if test.get("official_warning") is not False or test.get("operational_status") != "non_operational":
        raise N1BriefError("the test record must say it is not operational and not an official warning")
    try:
        binding = test["binding"]
        reference_date = str(binding["case_reference_date"])
        test_1_passes = bool(binding["test_1_passes"])
        dry_passes = bool(binding["dry_control_passes"])
    except (KeyError, TypeError) as error:
        raise N1BriefError(f"the test record holds no binding outcome: {error!r}") from error
    test_1 = test.get("test_1") or {}
    central = test_1.get("central") or {}
    iou = central.get("iou_no_answer_as_not_flagged")
    if test_1_passes and (iou is None or float(iou) < NAN_TEST_IOU_MIN):
        raise N1BriefError("the test record says test 1 passed while its figure is missing or under the bar")
    interval = ((test_1.get("central_interval_95") or {}).get("interval") or {}).get("iou_no_answer_as_not_flagged")
    dry = test.get("dry_control") or {}
    dry_central = dry.get("central") or {}
    town = test.get("test_2") or {}
    town_central = town.get("central") or {}
    points = (((town.get("labelled_points") or {}).get("agreement") or {}).get("central")) or {}
    flood = dict(binding.get("flood_input_of_case_N1") or {})
    flood.pop("map", None)
    return {
        "reference": test_1.get("reference"),
        "test_1_run": bool(central),
        "test_1_not_run": test_1.get("not_run"),
        "jaxa_why": (test_1.get("jaxa_usability") or {}).get("why"),
        "fallback": reference_date == FALLBACK_REFERENCE_DATE,
        "test_1_passes": test_1_passes,
        "dry_control_passes": dry_passes,
        "passed": test_1_passes and dry_passes,
        "iou": None if iou is None else float(iou),
        "interval": interval,
        "no_answer_share": central.get("no_answer_share"),
        "water_found": central.get("reference_water_flagged_no_answer_as_not_flagged"),
        "dry_share": dry_central.get("flagged_share_of_answered"),
        "dry_answered_cells": dry_central.get("answered_cells"),
        "dry_pass": (dry.get("pass") or {}).get("time_utc"),
        "case_reference_date": reference_date,
        "pass": flood,
        "town": {
            "iou": town_central.get("iou_no_answer_as_not_flagged"),
            "water_found": town_central.get("reference_water_flagged_no_answer_as_not_flagged"),
            "flags_on_water": town_central.get("flagged_that_is_reference_water"),
            "no_answer_share": town_central.get("no_answer_share"),
            "points_share": points.get("share_agreed_no_answer_as_not_flagged"),
            "points_with_a_label": points.get("points_with_a_label"),
            "hours_after_theos2": town.get("hours_after_theos2"),
            "pass": (town.get("pass") or {}).get("time_utc"),
        } if town_central else None,
        "generated_at_utc": test.get("generated_at_utc"),
    }


def ensemble_view(document: Mapping[str, Any], overlay: Mapping[str, Any], *, result_sha256: str) -> dict[str, Any]:
    """The stability figures of an ensemble record, checked to be those of this result file.

    The record is the run record the chain writes beside the result file (``ensemble`` section, ``outputs`` naming the
    result file) or the ensemble document of the work folder (``headlines`` at the top, the run's time as the result
    file's ``generated_at``).

    Raises:
        N1BriefError: for another case or run, a record without headlines, or a headline that is not the row's.
    """

    if document.get("official_warning") is not False or document.get("operational_status") != "non_operational":
        raise N1BriefError("the ensemble record must say it is not operational and not an official warning")
    if isinstance(document.get("headlines"), Mapping):
        kind, section = "ensemble document of the work folder", document
        case = document.get("case_id")
        summary = (document.get("ensemble") or {}).get("summary") or {}
        if document.get("generated_at_utc") != overlay.get("generated_at"):
            raise N1BriefError("the ensemble document is of another run of the chain (its time is not the result file's)")
    elif isinstance(document.get("ensemble"), Mapping) and isinstance(document["ensemble"].get("headlines"), Mapping):
        kind, section = "run record of the chain", document["ensemble"]
        case = (document.get("case") or {}).get("case_id")
        summary = section.get("summary") or {}
        named = [item for item in document.get("outputs") or [] if item.get("what") == "result_file"]
        if named and named[0].get("sha256") != result_sha256:
            raise N1BriefError("the run record names another result file (its SHA-256 differs)")
        if not named and document.get("generated_at_utc") != overlay.get("generated_at"):
            raise N1BriefError("the run record is of another run of the chain (its time is not the result file's)")
    else:
        raise N1BriefError("the ensemble record holds no headline of the ensemble")
    if case != CASE_ID:
        raise N1BriefError(f"the ensemble record is of case {case!r}, not N1")
    headlines = section["headlines"]
    for row in overlay["rows"]:
        record = headlines.get(row["unit_id"])
        if record is None:
            raise N1BriefError(f"the ensemble record holds no headline of {row['unit_id']}")
        slot = row.get("headline_stability") or {}
        if record.get("status") != slot.get("status") or not _same(record.get("class_retention"), slot.get("class_retention")):
            raise N1BriefError(f"the headline of {row['unit_id']} in the ensemble record is not the one of its row")
    cells = summary.get("cells_run")
    if cells is None:
        cells = next((record.get("cells_run") for record in headlines.values() if record.get("cells_run") is not None), None)
    return {"kind": kind, "cells_run": cells, "headlines": dict(headlines),
            "would_be": dict(section.get("would_be_retention") or {}),
            "headline_over": section.get("headline_over"), "case_outcome": document.get("case_outcome")}


def check_together(overlay: Mapping[str, Any], outcome: Mapping[str, Any], ensemble: Mapping[str, Any] | None, *,
                   test_sha256: str) -> None:
    """Refuse a result file, a test record and an ensemble record that are not of one run.

    Raises:
        N1BriefError: when the case reference dates differ, the radar passes lie more than an hour apart, a row
            carries another test 1 figure or another case-level verdict, or the run record read another test record.
    """

    stated = (overlay.get("case") or {}).get("case_reference_date")
    if stated != outcome["case_reference_date"]:
        raise N1BriefError(f"the result file's case reference date {stated!r} is not the test record's "
                           f"{outcome['case_reference_date']!r}")
    flood_time = parse_utc(flood_input_of(overlay).get("source_timestamp"))
    pass_time = parse_utc(outcome["pass"].get("time_utc"))
    if flood_time is not None and pass_time is not None and abs(flood_time - pass_time) > timedelta(minutes=PASS_TIME_TOLERANCE_MINUTES):
        raise N1BriefError("the radar pass of the result file is not the flood input the test record names for case N1")
    expected_status = "evaluated" if outcome["passed"] else "declared_unable_to_meet"
    for row in overlay["rows"]:
        skill = (row.get("confidence") or {}).get("t2_skill_condition")
        if not isinstance(skill, Mapping):
            continue
        figure = (skill.get("measurements") or {}).get("geoid_held_out_test_iou")
        if figure is not None and outcome["iou"] is not None and not _same(figure, outcome["iou"]):
            raise N1BriefError(f"row {row['unit_id']} carries a test 1 figure that is not the test record's")
        if skill.get("status") in ("evaluated", "declared_unable_to_meet") and skill["status"] != expected_status:
            raise N1BriefError(f"row {row['unit_id']} was judged by another case-level test outcome")
    if ensemble is None:
        return
    record = ensemble.get("case_outcome")
    if isinstance(record, Mapping):
        if (record.get("test_1_passed") is not None and bool(record["test_1_passed"]) != outcome["test_1_passes"]) or (
                record.get("dry_control_passed") is not None and bool(record["dry_control_passed"]) != outcome["dry_control_passes"]):
            raise N1BriefError("the run record holds another case-level test outcome than the test record")
        read_from = record.get("read_from")
        if isinstance(read_from, Mapping):
            named = (read_from.get("test_result") or {}).get("sha256")
            if named is not None and named != test_sha256:
                raise N1BriefError("the run record read another test record (its SHA-256 differs)")


# ---------------------------------------------------------------------------
# The rows of the brief
# ---------------------------------------------------------------------------


def n1_rows(overlay: Mapping[str, Any], ensemble: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """The values of the brief for every tambon of the N1 result, highest score first (no score last).

    Raises:
        N1BriefError: for a class outside A to E, a would-be class beside a row that is not low confidence, or a
            low-confidence row whose class in effect is not E.
    """

    listed = []
    for row in overlay["rows"]:
        confidence = row.get("confidence") or {}
        level = confidence.get("confidence_class")
        action, would_be = row.get("action_class"), row.get("would_be_class")
        for value in (action, would_be):
            if value is not None and value not in planning_brief.CLASS_NAMES:
                raise N1BriefError(f"unit {row.get('unit_id')} has a class outside A to E")
        if level not in planning_brief.CONFIDENCE_TH:
            raise N1BriefError(f"unit {row.get('unit_id')} has no confidence class")
        if would_be is not None and level != "low":
            raise N1BriefError(f"unit {row.get('unit_id')}: a would-be class stands only beside a low-confidence row")
        if level == "low" and action not in (None, "E"):
            raise N1BriefError(f"unit {row.get('unit_id')}: a low-confidence row is class E")
        kind = WOULD_BE if would_be is not None else NO_CLASS if action is None else BINDING
        shown = would_be if kind == WOULD_BE else action
        slot = row.get("headline_stability") or {}
        minimum = float(slot.get("class_retention_min") or 0.6)
        if kind == WOULD_BE:
            retention = ((ensemble or {}).get("would_be") or {}).get(row["unit_id"]) or {}
            if retention and retention.get("class_with_confidence_medium_in_the_default_cell") not in (None, would_be):
                raise N1BriefError(f"unit {row['unit_id']}: the ensemble record's would-be class is not the row's")
            holds = retention.get("share")
        elif kind == BINDING:
            holds = slot.get("class_retention")
        else:
            holds = None
        measurements = confidence.get("measurements") or {}
        listed.append({
            "unit_id": row["unit_id"], "name_en": row["unit_name_en"], "name_th": row["unit_name_th"],
            "score": None if row.get("fpps_0_100") is None else float(row["fpps_0_100"]),
            "class_in_effect": action, "would_be_class": would_be, "shown": shown, "kind": kind,
            "confidence": level, "reason_code": row.get("action_reason_code"),
            "failed_conditions": [name for name in CONDITION_ORDER if name in (confidence.get("failed_conditions") or [])],
            "no_answer_share": measurements.get("t2_abstention_fraction"),
            "holds": None if holds is None else float(holds), "holds_min": minimum,
            "holds_ok": None if holds is None else float(holds) >= minimum,
            "headline_status": slot.get("status"),
        })
    return sorted(listed, key=lambda item: (item["score"] is None, -(item["score"] or 0.0), item["unit_id"]))


def reason_of(row: Mapping[str, Any]) -> tuple[str, str]:
    """The reason of a row in a few words: the class rule of a binding class, or the conditions a low row does not meet."""

    if row["kind"] == BINDING and row["confidence"] != "low":
        return REASON_SHORT.get(str(row["reason_code"]), (str(row["reason_code"]), str(row["reason_code"])))
    codes = " ".join(name.split("_")[0] for name in row["failed_conditions"]) or str(row["reason_code"])
    return codes, codes


def holds_text(row: Mapping[str, Any]) -> str:
    if row["holds"] is None:
        return "n/a"
    return share_text(row["holds"]) + ("" if row["holds_ok"] else "*")


def table_cells(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The cells of one row, each in English and Thai (equal where the cell holds no words)."""

    level = row["confidence"]
    score = "n/a" if row["score"] is None else f"{row['score']:.1f}"
    shown = row["shown"] or "–"
    holds = holds_text(row)
    no_answer = share_text(row["no_answer_share"])
    return [(row["name_en"], row["name_th"]), (score, score), (shown, shown), KIND_LABELS[row["kind"]],
            (level, planning_brief.CONFIDENCE_TH[level]), (no_answer, no_answer), reason_of(row), (holds, holds)]


# ---------------------------------------------------------------------------
# The lines of the brief
# ---------------------------------------------------------------------------


def pass_words(outcome: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, str]:
    """The radar pass of the flood input: its time in UTC and Thai time, platform and relative orbit."""

    flood = flood_input_of(overlay)
    when = parse_utc(outcome["pass"].get("time_utc")) or parse_utc(flood.get("source_timestamp"))
    platform = str(outcome["pass"].get("platform") or "Sentinel-1")
    return {"utc": "n/a" if when is None else when.strftime("%Y-%m-%d %H:%M"),
            "thai": "n/a" if when is None else (when + THAI_OFFSET).strftime("%Y-%m-%d %H:%M"),
            "platform": platform, "orbit": str(outcome["pass"].get("relative_orbit") or "n/a"),
            "days": "n/a" if outcome["pass"].get("days_from_the_case_reference_date_thai_calendar") is None
            else str(outcome["pass"]["days_from_the_case_reference_date_thai_calendar"])}


def case_line(outcome: Mapping[str, Any], overlay: Mapping[str, Any]) -> tuple[str, str]:
    """What the case is: our own radar map, tested against another map before it fed the score."""

    words = pass_words(outcome, overlay)
    own_en = (f"What this case is: our own radar flood map (method M1-z on one Copernicus {words['platform']} pass), frozen "
              "before any reference was opened, ")
    own_th = (f"กรณีนี้คืออะไร: แผนที่น้ำท่วมจากเรดาร์ของโครงการเอง (วิธี M1-z จากภาพ Copernicus {words['platform']} หนึ่งรอบ) "
              "ตรึงค่าวิธีไว้ก่อนเปิดดูแผนที่อ้างอิงใดๆ ")
    reference = str(outcome["reference"] or "")
    if not outcome["test_1_run"]:
        why = str(outcome["test_1_not_run"] or "no reference could be read")
        return (own_en + f"but the test against another map could not be run ({why}), so no class of this case binds.",
                own_th + f"แต่ไม่สามารถทดสอบกับแผนที่อื่นได้ ({why}) ระดับในกรณีนี้จึงไม่มีผลบังคับ")
    if outcome["fallback"]:
        why = str(outcome["jaxa_why"] or "it did not say where ALOS-2 looked")
        return (own_en + f"then tested once against {reference}, the Copernicus Emergency Management Service map of the "
                f"same Sentinel-1 pass, before it fed the score. JAXA's map could not be used ({why}); a same-pass map is "
                "not independent of ours.",
                own_th + f"แล้วทดสอบหนึ่งครั้งกับ {reference} ซึ่งเป็นแผนที่ของ Copernicus Emergency Management Service "
                f"จากภาพ Sentinel-1 รอบเดียวกัน ก่อนนำมาคำนวณคะแนน ไม่สามารถใช้แผนที่ของ JAXA ได้ ({why}) "
                "และแผนที่จากภาพรอบเดียวกันไม่เป็นอิสระจากแผนที่ของเรา")
    return (own_en + f"then tested once against another satellite's map ({reference}, L-band radar) before it fed the score.",
            own_th + f"แล้วทดสอบหนึ่งครั้งกับแผนที่จากดาวเทียมอีกดวงหนึ่ง ({reference} เรดาร์ย่าน L) ก่อนนำมาคำนวณคะแนน")


def verdict(outcome: Mapping[str, Any]) -> tuple[str, str]:
    """What the case-level test outcome means for the classes."""

    every_e = ("so every class is E (low confidence), with its would-be class beside it.",
               "ทุกตำบลจึงได้ระดับ E (ความเชื่อมั่นต่ำ) โดยแสดงระดับที่จะได้ไว้ข้างกัน")
    if not outcome["test_1_run"]:
        return ("test 1 could not be run, " + every_e[0], "ไม่สามารถทำการทดสอบที่ 1 ได้ " + every_e[1])
    if outcome["passed"]:
        return ("both tests met the bars fixed before the test, so a class binds wherever the tambon's own conditions hold.",
                "ผ่านเกณฑ์ที่กำหนดไว้ก่อนการทดสอบทั้งสองข้อ ระดับของตำบลจึงมีผลในตำบลที่ผ่านเงื่อนไขของตนเอง")
    if not outcome["test_1_passes"] and not outcome["dry_control_passes"]:
        return ("neither test met its bar, " + every_e[0], "ไม่ผ่านเกณฑ์ทั้งสองการทดสอบ " + every_e[1])
    if not outcome["test_1_passes"]:
        return ("test 1 did not meet its bar, " + every_e[0], "การทดสอบที่ 1 ไม่ผ่านเกณฑ์ " + every_e[1])
    return ("the dry control did not meet its bar, " + every_e[0], "พื้นที่ควบคุมที่แห้งไม่ผ่านเกณฑ์ " + every_e[1])


def outcome_line(outcome: Mapping[str, Any]) -> tuple[str, str]:
    """The test outcome in one line, in each language."""

    head_en, head_th = verdict(outcome)
    dry = share_text(outcome["dry_share"])
    dry_en = f" Dry control on hills with no flood: {dry} of the answered cells flagged (bar ≤ {DRY_CONTROL_MAX_SHARE:.0%})."
    dry_th = f" พื้นที่ควบคุมบนเนินเขาที่ไม่มีน้ำท่วม: ระบุเป็นน้ำ {dry} ของเซลล์ที่มีคำตอบ (เกณฑ์ ≤ {DRY_CONTROL_MAX_SHARE:.0%})"
    if not outcome["test_1_run"]:
        return (f"Test outcome: {head_en}" + dry_en, f"ผลการทดสอบ: {head_th}" + dry_th)
    interval = outcome["interval"]
    span_en = "" if not interval else f", 95% interval {figure_text(interval[0])} to {figure_text(interval[1])}"
    span_th = "" if not interval else f" ช่วง 95% {figure_text(interval[0])} ถึง {figure_text(interval[1])}"
    reference = str(outcome["reference"])
    return (f"Test outcome: {head_en} Test 1, agreement with {reference}, not accuracy: IoU {figure_text(outcome['iou'])}"
            f"{span_en} (bar ≥ {NAN_TEST_IOU_MIN:.2f}), no answer on {share_text(outcome['no_answer_share'])} of the "
            f"compared cells (bar ≤ {NAN_NO_ANSWER_SHARE_MAX:.0%})." + dry_en,
            f"ผลการทดสอบ: {head_th} การทดสอบที่ 1 ความสอดคล้องกับ {reference} ไม่ใช่ความแม่นยำ: IoU "
            f"{figure_text(outcome['iou'])}{span_th} (เกณฑ์ ≥ {NAN_TEST_IOU_MIN:.2f}) ไม่มีคำตอบใน "
            f"{share_text(outcome['no_answer_share'])} ของเซลล์ที่เปรียบเทียบ (เกณฑ์ ≤ {NAN_NO_ANSWER_SHARE_MAX:.0%})" + dry_th)


def source_times(outcome: Mapping[str, Any], overlay: Mapping[str, Any]) -> tuple[str, str]:
    """The source times: the radar pass, the case reference date, the test, the result, the roads and the residents."""

    words = pass_words(outcome, overlay)
    roads = next((str(item.get("source_timestamp")) for item in overlay.get("inputs") or [] if item.get("role") == "routing_context"), "")
    found = re.search(r"retrieved (\S+?)(?:;|$)", roads)
    osm = found.group(1) if found else "n/a"
    test_time = str(outcome["generated_at_utc"] or "n/a")
    made = str(overlay.get("generated_at") or "n/a")
    return (f"Source times: radar pass {words['utc']} UTC ({words['thai']} Thai time), {words['platform']}, relative orbit "
            f"{words['orbit']}, {words['days']} days from the case reference date {outcome['case_reference_date']}. Test run "
            f"{test_time}. Result made {made}. Roads: OpenStreetMap retrieved {osm}. Residents: WorldPop 2020 (modelled).",
            f"เวลาของข้อมูล: ภาพเรดาร์ {words['utc']} UTC ({words['thai']} เวลาประเทศไทย) {words['platform']} วงโคจรสัมพัทธ์ "
            f"{words['orbit']} ห่างจากวันอ้างอิงของกรณี ({outcome['case_reference_date']}) {words['days']} วัน ทดสอบเมื่อ "
            f"{test_time} จัดทำผลเมื่อ {made} ถนน: OpenStreetMap ดึงข้อมูลเมื่อ {osm} ผู้อยู่อาศัย: WorldPop 2020 (ค่าจากแบบจำลอง)")


def confidence_line(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """How many tambons are at each confidence class."""

    count = {level: sum(1 for row in rows if row["confidence"] == level) for level in ("medium", "low")}
    none = sum(1 for row in rows if row["kind"] == NO_CLASS)
    binding = sum(1 for row in rows if row["kind"] == BINDING)
    would_be = sum(1 for row in rows if row["kind"] == WOULD_BE)
    extra_en = f"; {none} with no class (fewer residents than the minimum)" if none else ""
    extra_th = f" ไม่มีระดับ {none} ตำบล (ผู้อยู่อาศัยน้อยกว่าเกณฑ์ขั้นต่ำ)" if none else ""
    return (f"Confidence: {count['medium']} of {len(rows)} tambons medium, {count['low']} low; {binding} binding classes, "
            f"{would_be} would-be classes{extra_en}. High confidence is never given in this release.",
            f"ความเชื่อมั่น: ปานกลาง {count['medium']} ตำบล ต่ำ {count['low']} ตำบล จากทั้งหมด {len(rows)} ตำบล "
            f"ระดับที่มีผล {binding} ตำบล ระดับที่จะได้ {would_be} ตำบล{extra_th} รุ่นนี้ไม่มีการให้ความเชื่อมั่นระดับสูง")


def ensemble_axes(cells: Any) -> tuple[str, str]:
    """The choices the ensemble's runs combine (Nan protocol ``ensemble``: 180 runs, or 90 without the population axis)."""

    head_en = "every combination of the flood map (3 levels), the closure level (3), "
    head_th = "ทุกชุดค่าผสมของแผนที่น้ำท่วม (3 ระดับ) ระดับการปิดถนน (3) "
    tail_en = "the vulnerability anchors (2) and the weights (5)"
    tail_th = "เกณฑ์ความเปราะบาง (2) และชุดน้ำหนัก (5)"
    if cells == 180:
        return (head_en + "the population data (2: WorldPop 2020 and its 2024 rescale), " + tail_en,
                head_th + "ข้อมูลประชากร (2: WorldPop 2020 และที่ปรับเป็นปี ค.ศ. 2024) " + tail_th)
    if cells == 90:
        return (head_en + tail_en + "; no population axis, as the 2024 rescale was not built for the frame",
                head_th + tail_th + " ไม่มีแกนข้อมูลประชากร เพราะไม่ได้สร้างข้อมูลที่ปรับเป็นปี ค.ศ. 2024 สำหรับพื้นที่นี้")
    return ("over the declared choices of the Nan protocol that were run", "ตามทางเลือกที่ประกาศไว้ในโพรโทคอลของกรณีน่านที่ได้คำนวณ")


def stability_lines(rows: Sequence[Mapping[str, Any]], ensemble: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """What the brief says of stability over the ensemble (guardrail GR8, report-only for a would-be class)."""

    minimum = next((row["holds_min"] for row in rows), 0.6)
    measured = [row for row in rows if row["holds"] is not None]
    unstable = [row for row in measured if not row["holds_ok"]]
    if ensemble is None:
        lead = ("Stability over the ensemble: the ensemble record was not given to this brief; a binding class shows the "
                "headline slot of the result file and a would-be class shows n/a.",
                "ความเสถียรจากชุดการคำนวณ: ไม่ได้รับบันทึกชุดการคำนวณ ระดับที่มีผลแสดงค่าจากไฟล์ผลลัพธ์ "
                "ส่วนระดับที่จะได้แสดงเป็น n/a")
    else:
        axes_en, axes_th = ensemble_axes(ensemble["cells_run"])
        cells = ensemble["cells_run"] if ensemble["cells_run"] is not None else "n/a"
        lead = (f"Stability over the ensemble (report-only): {cells} runs of the chain, {axes_en}.",
                f"ความเสถียรจากชุดการคำนวณ (รายงานเท่านั้น): คำนวณซ้ำ {cells} รอบ {axes_th}")
    held_en = (f"The class shown holds in at least {minimum:.0%} of the runs for {len(measured) - len(unstable)} of "
               f"{len(measured)} tambons with a figure")
    held_th = (f"ระดับที่แสดงคงเดิมอย่างน้อย {minimum:.0%} ของรอบใน {len(measured) - len(unstable)} จาก {len(measured)} "
               "ตำบลที่มีค่า")
    if unstable and len(unstable) <= UNSTABLE_NAMES_MAX:
        held_en += f"; it does not for {', '.join(row['name_en'] for row in unstable)}: verify before use."
        held_th += f" ส่วนตำบล{' '.join(row['name_th'] for row in unstable)}ไม่คงเดิม ควรตรวจสอบก่อนใช้งาน"
    elif unstable:
        held_en += f"; the other {len(unstable)} are marked * in the table: verify before use."
        held_th += f" อีก {len(unstable)} ตำบลมีเครื่องหมาย * ในตาราง ควรตรวจสอบก่อนใช้งาน"
    else:
        held_en += "."
    return [lead, (held_en, held_th)]


def condition_lines(rows: Sequence[Mapping[str, Any]], overlay: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The conditions of confidence that some row does not meet, in words, with the thresholds of the rule."""

    first = next((row.get("confidence") or {} for row in overlay["rows"] if row.get("confidence")), {})
    limits = first.get("thresholds") or {}
    skill = (first.get("t2_skill_condition") or {}).get("thresholds") or {}
    no_answer = float(skill.get("mae_sai_abstention_fraction_max", NAN_NO_ANSWER_SHARE_MAX))
    answered = float(skill.get("mae_sai_unit_coverage_min", limits.get("unit_valid_coverage_min", NAN_ANSWERED_SHARE_MIN)))
    days = float(skill.get("recency_window_days", limits.get("recency_window_days", NAN_PASS_WINDOW_DAYS)))
    points = float(limits.get("exposure_plus_minus_one_pixel_max_points", 15.0))
    residents = float(limits.get("unit_residents_min", 100.0))
    no_route = float(limits.get("baseline_vehicle_no_route_share_max", 0.1))
    hospitals = float(limits.get("hospitals_reachable_at_baseline_min", 1.0))
    words = {
        "C1_tier": (f"C1: the case test, or the tambon's own radar answer: no answer on over {no_answer:.0%} of its land, "
                    f"an answer on under {answered:.0%}, or a pass over {days:g} days from the case reference date.",
                    f"C1: ผลการทดสอบของกรณี หรือคำตอบจากเรดาร์ของตำบลเอง: ไม่มีคำตอบเกิน {no_answer:.0%} ของพื้นที่ "
                    f"มีคำตอบน้อยกว่า {answered:.0%} หรือภาพเรดาร์ห่างจากวันอ้างอิงของกรณีเกิน {days:g} วัน"),
        "C2_recency": (f"C2: the radar pass is more than {days:g} days from the case reference date.",
                       f"C2: ภาพเรดาร์ห่างจากวันอ้างอิงของกรณีเกิน {days:g} วัน"),
        "C3_coverage": (f"C3: less than {answered:.0%} of the tambon's land has an answer.",
                        f"C3: พื้นที่ของตำบลที่มีคำตอบน้อยกว่า {answered:.0%}"),
        "C4_input_uncertainty": (f"C4: the share of residents inside the mapped water moves by over {points:g} points when "
                                 "the map grows or shrinks by one 20 m cell.",
                                 f"C4: สัดส่วนผู้อยู่อาศัยในพื้นที่น้ำท่วมเปลี่ยนเกิน {points:g} จุด เมื่อขยายหรือหดแผนที่หนึ่งเซลล์ (20 ม.)"),
        "C5_components": ("C5: a component of the score could not be computed.", "C5: องค์ประกอบบางส่วนของคะแนนคำนวณไม่ได้"),
        "C6_residents": (f"C6: fewer than {residents:g} modelled residents.", f"C6: ผู้อยู่อาศัยจากแบบจำลองน้อยกว่า {residents:g} คน"),
        "C7_baseline_no_route": (f"C7: more than {no_route:.0%} of the connected residents have no modelled road route to a "
                                 "hospital even without flooding.",
                                 f"C7: ผู้อยู่อาศัยที่เชื่อมกับโครงข่ายถนนเกิน {no_route:.0%} ไม่มีเส้นทางถนนไปโรงพยาบาลตามแบบจำลองแม้ไม่มีน้ำท่วม"),
        "C8_hospital": (f"C8: fewer than {hospitals:g} hospital reachable by road even without flooding.",
                        f"C8: เดินทางถึงโรงพยาบาลทางถนนได้น้อยกว่า {hospitals:g} แห่งแม้ไม่มีน้ำท่วม"),
    }
    present = [name for name in CONDITION_ORDER if any(name in row["failed_conditions"] for row in rows)]
    return [words[name] for name in present]


def classes_on_the_brief(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The letters whose asks the brief lists: every class shown, and E whenever a would-be class stands beside it."""

    letters = {row["shown"] for row in rows if row["shown"]} | {row["class_in_effect"] for row in rows if row["class_in_effect"]}
    return sorted(letters)


def credits_of(overlay: Mapping[str, Any], outcome: Mapping[str, Any]) -> list[str]:
    """The attribution of the flood input, of the test references (figures only) and of the open data beside them."""

    flood = flood_input_of(overlay)
    listed = [f"Flood map: {flood.get('attribution')} ({flood.get('licence')})."]
    if outcome["test_1_run"] and outcome["fallback"]:
        listed.append("Test 1 reference: Copernicus Emergency Management Service, Global Flood Monitoring (GFM): only figures "
                      "computed from it are shown, no part of the map.")
    elif outcome["test_1_run"]:
        listed.append("Test 1 reference: JAXA ALOS-2 Flood Proxy Map, Provided by JAXA (Sentinel Asia): only figures computed "
                      "from it are shown, no part of the map.")
    listed.append("Dry control: the area of a THEOS-2 image of 31 July 2025 (GISTDA sample), figures only.")
    listed.append("Roads © OpenStreetMap contributors (ODbL 1.0); residents WorldPop 2020 and age counts 2024 (CC BY 4.0); "
                  "permanent water ESA WorldCover 2021 (CC BY 4.0); boundaries HDX Thailand COD-AB.")
    return listed


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _pieces(overlay: Mapping[str, Any], outcome: Mapping[str, Any], ensemble: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = n1_rows(overlay, ensemble)
    minimum = next((row["holds_min"] for row in rows), 0.6)
    return {
        "rows": rows, "case": overlay["case"], "status": STATUS, "what": case_line(outcome, overlay),
        "outcome": outcome_line(outcome), "times": source_times(outcome, overlay), "confidence": confidence_line(rows),
        "letters": classes_on_the_brief(rows), "conditions": condition_lines(rows, overlay),
        "stability": stability_lines(rows, ensemble),
        "holds_note": (HOLDS_NOTE[0].format(minimum=f"{minimum:.0%}"), HOLDS_NOTE[1].format(minimum=f"{minimum:.0%}")),
        "credits": credits_of(overlay, outcome),
    }


def render_markdown(overlay: Mapping[str, Any], outcome: Mapping[str, Any], ensemble: Mapping[str, Any] | None, *,
                    made_from: Sequence[Mapping[str, str]]) -> str:
    """The brief as Markdown."""

    parts = _pieces(overlay, outcome, ensemble)
    case = parts["case"]
    lines = [f"# {case['title_en']}", f"## {case['title_th']}", ""]
    if case.get("fixture_notice"):
        lines += [f"**{case['fixture_notice']}**", ""]
    lines += [f"> **{STATUS[0]}**", ">", f"> **{STATUS[1]}**", "",
              f"{parts['what'][0]}", "", f"{parts['what'][1]}", "",
              f"**{parts['outcome'][0]}**", "", f"**{parts['outcome'][1]}**", "",
              f"- {parts['times'][0]}", f"- {parts['times'][1]}", f"- {parts['confidence'][0]} / {parts['confidence'][1]}", "",
              "| " + " | ".join(f"{english} / {thai}" for english, thai in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for row in parts["rows"]:
        cells = [english if english == thai else f"{english} / {thai}" for english, thai in table_cells(row)]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", f"- {BINDING_NOTE[0]} / {BINDING_NOTE[1]}", f"- {parts['holds_note'][0]} / {parts['holds_note'][1]}",
              f"- {NO_ANSWER_NOTE[0]} / {NO_ANSWER_NOTE[1]}", "", "### What each class asks / แต่ละระดับหมายถึงอะไร", ""]
    lines += [f"- **{letter}: {planning_brief.CLASS_NAMES[letter][0]} / {planning_brief.CLASS_NAMES[letter][1]}.** "
              f"{ASKS[letter][0]} / {ASKS[letter][1]}" for letter in parts["letters"]]
    lines += ["", f"**{NEVER_SAFE[0]}** / **{NEVER_SAFE[1]}**", ""]
    if parts["conditions"]:
        lines += ["### Conditions not met / เงื่อนไขที่ไม่ผ่าน", ""]
        lines += [f"- {english} / {thai}" for english, thai in parts["conditions"]]
        lines += [""]
    lines += ["### Stability / ความเสถียร", ""]
    lines += [f"- {english} / {thai}" for english, thai in parts["stability"]]
    lines += ["", "### Assumptions / สมมติฐาน", ""]
    lines += [f"- {english} / {thai}" for english, thai in ASSUMPTIONS]
    lines += ["", f"{planning_brief.OFFICIAL[0]} / {planning_brief.OFFICIAL[1]}", "", "---", ""]
    lines += [f"Credits: {' '.join(parts['credits'])}", ""]
    lines += ["Made from " + "; ".join(f"`{item['path']}` (SHA-256 `{item['sha256']}`)" for item in made_from) + ".",
              "", f"{planning_brief.THAI_NOTE[0]} / {planning_brief.THAI_NOTE[1]}", ""]
    return "\n".join(lines)


def _html_table(rows: Sequence[Mapping[str, Any]]) -> str:
    escape = html.escape
    head = "".join(f"<th>{escape(english)}<br><span lang=\"th\">{escape(thai)}</span></th>" for english, thai in COLUMNS)
    body = []
    for row in rows:
        cells = table_cells(row)
        out = []
        for index, (english, thai) in enumerate(cells):
            text = escape(english) if english == thai else f"{escape(english)} <span lang=\"th\">{escape(thai)}</span>"
            if index == 2:
                css = f"class {row['kind']}" + (f" c{row['shown']}" if row["shown"] else "")
            elif index in (1, 5, 7):
                css = "number"
            else:
                css = "name"
            out.append(f'<td class="{css}">{text}</td>')
        body.append("<tr>" + "".join(out) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(overlay: Mapping[str, Any], outcome: Mapping[str, Any], ensemble: Mapping[str, Any] | None, *,
                made_from: Sequence[Mapping[str, str]]) -> str:
    """The brief as one self-contained page that prints on one sheet of A4, landscape."""

    parts = _pieces(overlay, outcome, ensemble)
    case = parts["case"]
    escape = html.escape

    def pair(text: tuple[str, str], tag: str = "p", css: str = "") -> str:
        return f'<{tag}{css}><span lang="en">{escape(text[0])}</span><br><span lang="th">{escape(text[1])}</span></{tag}>'

    def key(title: tuple[str, str], items: Sequence[tuple[str, str]], joiner: str = " ") -> str:
        """A titled paragraph that runs the whole width: the English items, then the Thai items."""

        english = joiner.join(escape(item[0]) for item in items)
        thai = joiner.join(escape(item[1]) for item in items)
        return (f'<p class="key"><strong>{escape(title[0])} / {escape(title[1])}.</strong> <span lang="en">{english}</span>'
                f'<br><span lang="th">{thai}</span></p>')

    rows = parts["rows"]
    half = (len(rows) + 1) // 2
    tables = _html_table(rows[:half]) + (_html_table(rows[half:]) if rows[half:] else "")
    asks = [(f"{letter} {planning_brief.CLASS_NAMES[letter][0]}: {ASKS[letter][0]}",
             f"{letter} {planning_brief.CLASS_NAMES[letter][1]}: {ASKS[letter][1]}") for letter in parts["letters"]]
    reading = [BINDING_NOTE, parts["holds_note"], NO_ANSWER_NOTE, *parts["conditions"]]
    fixture = f'<p class="fixture">{escape(str(case["fixture_notice"]))}</p>' if case.get("fixture_notice") else ""
    sources = "; ".join(f"{escape(item['path'])} (SHA-256 {escape(item['sha256'])})" for item in made_from)
    swatches = "\n".join(
        f".c{letter} {{ background: {colour}; color: {'#fff' if letter in 'AB' else '#111'}; }}\n"
        f".would_be.c{letter} {{ background: repeating-linear-gradient(135deg, {colour} 0 2.2px, #fff 2.2px 4.4px); "
        f"color: #111; text-shadow: 0 0 2px #fff, 0 0 2px #fff; }}"
        for letter, colour in CLASS_COLOURS.items())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(case['title_en'])}</title>
<style>
@page {{ size: A4 landscape; margin: 6mm; }}
* {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }}
body {{ font-family: "Noto Sans Thai", "Sarabun", "Leelawadee UI", Tahoma, Arial, sans-serif; font-size: 7pt; line-height: 1.22; color: #111; margin: 0 auto; max-width: 285mm; padding: 0.5mm; background: #fff; }}
h1 {{ font-size: 11pt; margin: 0; }} h2 {{ font-size: 9pt; margin: 0; font-weight: 600; }}
p {{ margin: 0.6mm 0; }}
.head {{ display: grid; grid-template-columns: 0.85fr 1.15fr; gap: 3mm; align-items: center; }}
.status {{ border: 1.2pt solid #111; padding: 0.8mm 2mm; font-weight: 700; }}
.outcome {{ border-left: 2.5pt solid #087f8c; padding: 0.4mm 2mm; margin: 0.8mm 0; }}
.outcome span[lang="en"] {{ font-weight: 700; }}
.fixture {{ border: 1pt dashed #725124; padding: 0.6mm 2mm; font-weight: 700; }}
.meta {{ font-size: 6.4pt; color: #333; }}
.key {{ font-size: 6.2pt; line-height: 1.17; margin: 0.7mm 0; }}
.strong {{ font-weight: 700; }}
.foot {{ font-size: 5.8pt; color: #333; overflow-wrap: anywhere; }}
.tables {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2mm; align-items: start; margin: 0.8mm 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 6.2pt; line-height: 1.1; }}
th, td {{ border: 0.4pt solid #777; padding: 0.12mm 0.7mm; vertical-align: top; white-space: nowrap; }}
th {{ background: #eee; font-size: 5.9pt; text-align: left; font-weight: 600; }}
td.number {{ text-align: right; }}
td.class {{ text-align: center; font-weight: 700; }}
{swatches}
@media screen and (max-width: 800px) {{ .head, .tables {{ grid-template-columns: 1fr; }} .tables {{ overflow-x: auto; }} body {{ font-size: 9pt; }} .key, .meta {{ font-size: 8pt; }} table {{ font-size: 8pt; }} th, td {{ white-space: normal; }} }}
</style>
</head>
<body>
<div class="head"><div><h1>{escape(case['title_en'])}</h1><h2 lang="th">{escape(case['title_th'])}</h2></div>{pair(STATUS, "div", ' class="status"')}</div>
{fixture}{pair(parts['what'], "p", ' class="what"')}
{pair(parts['outcome'], "div", ' class="outcome"')}
<p class="meta">{escape(parts['times'][0])}<br><span lang="th">{escape(parts['times'][1])}</span><br>{escape(parts['confidence'][0])} <span lang="th">{escape(parts['confidence'][1])}</span></p>
<div class="tables">{tables}</div>
{key(("What each class asks", "แต่ละระดับหมายถึงอะไร"), asks, " · ")}
{key(("How to read the table", "วิธีอ่านตาราง"), reading)}
{key(("Stability", "ความเสถียร"), parts['stability'])}
{key(("Assumptions", "สมมติฐาน"), ASSUMPTIONS)}
{pair((NEVER_SAFE[0] + " " + planning_brief.OFFICIAL[0], NEVER_SAFE[1] + " " + planning_brief.OFFICIAL[1]), "p", ' class="key strong"')}
<p class="foot">Credits: {escape(' '.join(parts['credits']))}<br>Made from {sources}. {escape(planning_brief.THAI_NOTE[0])} / {escape(planning_brief.THAI_NOTE[1])}</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def find_result(given: Path | None) -> Path:
    """The result file: the one given, or the first of :data:`RESULT_CANDIDATES` that exists.

    Raises:
        N1BriefError: when none exists, or when both names exist with different bytes.
    """

    if given is not None:
        return given
    found = [ROOT / name for name in RESULT_CANDIDATES if (ROOT / name).is_file()]
    if not found:
        raise N1BriefError(f"no N1 result file: looked for {', '.join(RESULT_CANDIDATES)} (the chain has not run on Nan)")
    if len(found) > 1 and len({path.read_bytes() for path in found}) > 1:
        raise N1BriefError(f"both {found[0].name} and {found[1].name} exist and differ: name the result file with --result")
    return found[0]


def find_ensemble(result: Path) -> Path | None:
    """The run record beside the result file, if the chain wrote one."""

    for candidate in (result.with_name(result.stem + "_record.json"), ROOT / "outputs" / "nan_case" / "planning_result_n1_nan_v1_record.json"):
        if candidate.is_file():
            return candidate
    return None


def write_text(path: Path, text: str) -> dict[str, Any]:
    """Write a text file with LF line ends and return its name, SHA-256 and size."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    data = path.read_bytes()
    return {"name": path.name, "sha256": sha256_bytes(data), "bytes": len(data)}


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(result_path: Path, test_path: Path, ensemble_path: Path | None, out_dir: Path, *,
          external_root: Path | None = None, generated_at: str | None = None) -> dict[str, Any]:
    """Check the three files against each other, then write the brief (Markdown, HTML) and its record.

    Raises:
        N1BriefError: for a path behind the firewall, a file that is not what the brief needs, files that are not of
            one run, or a fixture result written into the brief folder of the repository.
    """

    refuse_behind_the_firewall([result_path, test_path, ensemble_path, out_dir])
    overlay, result_sha = read_json(result_path)
    check_result(overlay)
    test, test_sha = read_json(test_path)
    outcome = outcome_of_the_test(test)
    ensemble, ensemble_sha = None, None
    if ensemble_path is not None:
        document, ensemble_sha = read_json(ensemble_path)
        ensemble = ensemble_view(document, overlay, result_sha256=result_sha)
    check_together(overlay, outcome, ensemble, test_sha256=test_sha)
    if (overlay.get("case") or {}).get("fixture_notice") and Path(out_dir).resolve() == (ROOT / OUTPUT_DIR).resolve():
        raise N1BriefError("a fixture result is never written into outputs/planning_brief")
    made_from = [{"what": "result_file", "path": label_of(result_path, external_root), "sha256": result_sha},
                 {"what": "test_record", "path": label_of(test_path, external_root), "sha256": test_sha}]
    if ensemble_path is not None:
        made_from.append({"what": "ensemble_record", "path": label_of(ensemble_path, external_root), "sha256": str(ensemble_sha)})
    out_dir = Path(out_dir)
    files = [write_text(out_dir / f"{NAME}.md", render_markdown(overlay, outcome, ensemble, made_from=made_from)),
             write_text(out_dir / f"{NAME}.html", render_html(overlay, outcome, ensemble, made_from=made_from))]
    rows = n1_rows(overlay, ensemble)
    levels = sorted({row["confidence"] for row in rows})
    record = {
        "schema": "floodguard.planning_brief_record.v1",
        "what_this_is": "The record of the printable brief of case N1: what it was made from, and that it changes nothing it read.",
        "generated_at_utc": generated_at or now_utc(),
        "source_timestamp": str(flood_input_of(overlay).get("source_timestamp")),
        "result_generated_at": overlay.get("generated_at"),
        "confidence_class": "low" if "low" in levels else "medium",
        "confidence_basis": "The lowest confidence class of the rows on the brief; each row's class is printed beside it.",
        "confidence_classes_of_the_rows": levels,
        "assumptions": [english for english, _thai in ASSUMPTIONS],
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "made_from": made_from,
        "ensemble_record": None if ensemble is None else {"kind": ensemble["kind"], "cells_run": ensemble["cells_run"]},
        "test_outcome": {key: outcome[key] for key in ("reference", "fallback", "test_1_passes", "dry_control_passes", "iou",
                                                       "no_answer_share", "dry_share", "case_reference_date")},
        "files": files,
        "classes_on_the_brief": {row["unit_id"]: {"class_in_effect": row["class_in_effect"], "would_be_class": row["would_be_class"],
                                                  "shown": row["shown"], "kind": row["kind"], "confidence_class": row["confidence"]}
                                 for row in rows},
        "thai_text": planning_brief.THAI_NOTE[0],
        "how_to_print": "Open the HTML file in a browser and print: A4, landscape, one sheet, background graphics on.",
        "wording": "Every figure is agreement with another map, not accuracy. Planning guidance only.",
    }
    record_text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    record_file = write_text(out_dir / f"{NAME}_record.json", record_text)
    return {"files": [*files, record_file], "rows": len(rows), "record": record}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and write the brief; 0 when written, 2 when an input was refused."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--result", type=Path, help=f"the N1 result file (default: the first of {', '.join(RESULT_CANDIDATES)})")
    parser.add_argument("--test-result", type=Path, default=ROOT / TEST_RESULT, help="the test record of the case")
    parser.add_argument("--ensemble", type=Path, help="the run record of the chain or the ensemble document of the work folder "
                        "(default: the run record beside the result file)")
    parser.add_argument("--no-ensemble", action="store_true", help="make the brief without an ensemble record (it says so)")
    parser.add_argument("--out-dir", type=Path, default=ROOT / OUTPUT_DIR)
    parser.add_argument("--external-root", type=Path, help="the external data root, to name files of the work folder")
    args = parser.parse_args(argv)
    try:
        result = find_result(args.result)
        ensemble = None if args.no_ensemble else (args.ensemble or find_ensemble(result))
        if ensemble is None and not args.no_ensemble:
            print("note: no ensemble record found beside the result file; the brief says the ensemble was not given", file=sys.stderr)
        summary = build(result, args.test_result, ensemble, args.out_dir, external_root=args.external_root)
    except (N1BriefError, planning_brief.PlanningBriefError, OSError, json.JSONDecodeError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    for item in summary["files"]:
        print(f"wrote {item['name']} ({item['bytes']} bytes, SHA-256 {item['sha256']})")
    return EXIT_DONE


if __name__ == "__main__":
    raise SystemExit(main())
