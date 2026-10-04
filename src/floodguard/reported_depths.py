"""Reported flood depths (news, not surveyed) and their consistency with the replay's modelled depth.

Roadmap item C-2. News reports of 10-13 Sep 2024 gave flood depths at named places in Mae Sai: a few numbers, all
lower bounds ("more than 1.5 m") or ranges ("2-3 m in places"), and more often a storey or a body reference ("up to
the chest", "the ground floor under water"). ``outputs/mae_sai_reported_depths_2024.json`` holds them, paraphrased and
cited, with a point only where the location confidence is medium or high. Their status is "reported (anecdotal, not
surveyed)".

Each entry of the file is a place record: one statement of one article about one place. A statement that names several
communities is recorded once per community, and those records share a ``statement_id``; so the counts are given per
place record and, separately, once per statement (a statement whose places read differently counts as "mixed").

This module has the pure parts:

* :func:`document_problems`: the data file's contract, including a copyright guard (a cited title is short, a
  paraphrase shares no long run of characters with its source title, a record quotes at most one short phrase) and the
  rule that records of one statement share its source, depth and time window;
* :func:`window_max_stage`, :func:`cell_depth`, :func:`first_wet_hour` and :func:`point_model`: the model at a report's
  point over the report's time window, on the replay's own grid and stage curve;
* :func:`consistency_status`, :func:`consistency_counts` and :func:`statement_counts`: whether the model reaches a
  reported lower bound (a number) or has the place wet (a storey or body reference, whose depth is never compared), and
  the counts per outcome, per place record and per statement;
* :func:`cause_figures` and :func:`likely_causes`: the likely causes of the misses, with every count in them taken from
  the reports at bake time;
* :func:`manifest_block`: the ``reported_depths`` block of ``timeline.json``.

The comparison is a consistency check, never a validation, and the reports are never used to tune the model: no
keyframe, depth-factor or terrain change may be set from them. Nothing here computes a Flood Preparedness Priority
Score or an action class.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from floodguard.flood_timeline import CHANNEL_CODE, HAND_STEP_M, NEVER_CODE

REPORTED_DEPTHS_PATH = Path("outputs/mae_sai_reported_depths_2024.json")
"""The data file, relative to the repository root."""

SCHEMA_PATH = Path("packages/contracts/schemas/reported-depths-2024.schema.json")
STATUS = "reported (anecdotal, not surveyed)"
LANE = "REP"
LOCATED_CONFIDENCE: tuple[str, ...] = ("medium", "high")
"""Location confidences that get a point; a low-confidence report has none and is not compared."""

DEPTH_CLASSES: tuple[str, ...] = (
    "waist_deep", "chest_deep", "neck_deep", "over_head", "ground_floor_submerged", "above_ground_floor", "roof_level_refuge", "not_stated",
)
"""Classes for a storey or body reference; a class is never turned into a number."""

NUMERIC_KINDS: tuple[str, ...] = ("lower_bound", "range")
BASES: tuple[str, ...] = ("numeric", "qualitative")
STATUSES: tuple[str, ...] = ("consistent", "model_shallower", "model_wet", "model_dry", "not_comparable")
"""Outcomes of the consistency check, in display order. ``consistent`` and ``model_shallower`` compare a number with its
lower bound; ``model_wet`` is a storey or body reference where the model has water (its depth is not compared), so it
is never counted as consistent."""
APPLIES: Mapping[str, tuple[str, ...]] = {
    "numeric": ("consistent", "model_shallower", "model_dry", "not_comparable"),
    "qualitative": ("model_wet", "model_dry", "not_comparable"),
}
"""The outcomes each comparison basis can have."""
MIXED = "mixed"
"""A statement recorded at several places whose places have different outcomes."""
STATEMENT_OUTCOMES: tuple[str, ...] = (*STATUSES, MIXED)
EARLY_STAGE_M = 0.1
"""The assumed river level the model holds through the morning and midday of 10 Sep, before its rise (likely cause
"timing")."""
HIGH_GROUND_M = 2.0
"""A report point this far or more above its channel in the model counts as raised ground (likely cause "surface_model")."""

TITLE_MAX_CHARS = 160
"""A cited article title may be at most this long."""
COPY_RUN_CHARS = 20
"""A paraphrase may share no run of this many characters (white space collapsed) with its source title."""
QUOTE_MAX_WORDS = 15
"""A quoted phrase in a record is shorter than this many words, and a record quotes at most one phrase per source."""

NEVER_TUNE = "never used to tune"
"""Words the use rule must say: the reports are a consistency check, never a tuning target."""

ICT = timezone(timedelta(hours=7))
_WHITE_SPACE = re.compile(r"\s+")
_QUOTED = re.compile(r"[\"“”]([^\"“”]{1,400})[\"“”]|(?<![A-Za-z])'([^']{2,200})'(?![A-Za-z])")


class ReportedDepthsError(ValueError):
    """Raised when the reported-depths data or the block written from it breaks its rules."""


# --- The data file ----------------------------------------------------------------------------------------


def comparison_basis(depth: Mapping[str, Any]) -> str:
    """``numeric`` for a lower bound or a range (its lower end is the lower bound), ``qualitative`` for a class."""
    return "numeric" if depth.get("kind") in NUMERIC_KINDS else "qualitative"


def lower_bound(depth: Mapping[str, Any]) -> float | None:
    """The reported lower bound in metres, or ``None`` for a class (a storey or body reference has no number)."""
    return float(depth["lower_bound_m"]) if comparison_basis(depth) == "numeric" else None


def _flat(text: str) -> str:
    return _WHITE_SPACE.sub(" ", text).strip()


def copied_runs(text: str, source: str, run: int = COPY_RUN_CHARS) -> list[str]:
    """Runs of ``run`` characters that ``text`` shares with ``source`` (white space collapsed); empty when none."""
    flat_text, flat_source = _flat(text), _flat(source)
    if len(flat_source) < run:
        return []
    windows = {flat_source[index:index + run] for index in range(len(flat_source) - run + 1)}
    found = {flat_text[index:index + run] for index in range(max(0, len(flat_text) - run + 1)) if flat_text[index:index + run] in windows}
    return sorted(found)


def quoted_phrases(text: str) -> list[str]:
    """Phrases inside double quotes, or single quotes that are not apostrophes, in ``text``."""
    return [first or second for first, second in _QUOTED.findall(text)]


def _record_texts(report: Mapping[str, Any]) -> list[str]:
    """Every text of a report the project wrote (the paraphrase and the notes), not the cited title or the address."""
    texts = [report["depth"]["statement"]["en"], report["depth"]["statement"]["th"], report["time"]["text"]["en"], report["time"]["text"]["th"],
             report["location_basis"], report["event_date_basis"], report["checker_corrections"], report["time"]["window_basis"],
             report["place"]["en"], report["place"]["th"], report["tambon"]["en"], report["tambon"]["th"]]
    return [text for text in texts if isinstance(text, str) and text] + ([report["tambon_note"]] if report.get("tambon_note") else [])


def copyright_problems(document: Mapping[str, Any]) -> list[str]:
    """The copyright guard of the data file (empty when it holds).

    A cited title is at most :data:`TITLE_MAX_CHARS` characters; the paraphrase and every note of a report share no run
    of :data:`COPY_RUN_CHARS` characters with the report's source title; and the reports that cite one source quote at
    most one phrase from it, of fewer than :data:`QUOTE_MAX_WORDS` words.
    """
    problems: list[str] = []
    quotes: dict[str, set[str]] = {}
    for report in document.get("reports", ()):
        name = report.get("id")
        title = str(report.get("source", {}).get("title", ""))
        if len(title) > TITLE_MAX_CHARS:
            problems.append(f"{name}: the cited title is longer than {TITLE_MAX_CHARS} characters")
        for text in _record_texts(report):
            runs = copied_runs(text, title)
            if runs:
                problems.append(f"{name}: a paraphrase repeats {len(runs[0])} characters of the source title ({runs[0]!r})")
            for phrase in quoted_phrases(text):
                if len(phrase.split()) >= QUOTE_MAX_WORDS:
                    problems.append(f"{name}: a quoted phrase has {len(phrase.split())} words")
                quotes.setdefault(str(report.get("source", {}).get("url")), set()).add(phrase)
    problems.extend(f"{url}: {len(found)} different quoted phrases from one source" for url, found in sorted(quotes.items()) if len(found) > 1)
    return problems


def document_problems(document: Mapping[str, Any]) -> list[str]:
    """Every way the data file breaks its rules beyond its JSON schema (empty when it holds).

    The status is "reported (anecdotal, not surveyed)", the confidence is low and the use rule says the reports are never
    used to tune the model. Report ids are unique. A point is given exactly where the location confidence is medium or
    high, with a tolerance; a low-confidence report has neither. A lower bound or a range has a number (a range's upper
    end above its lower end) and no class; a class has no number. A window ends after it starts, and a numeric report
    or a located report has a window. The copyright guard (:func:`copyright_problems`) holds.
    """
    problems: list[str] = []
    if document.get("status") != STATUS:
        problems.append(f"status must be {STATUS!r}")
    if document.get("confidence") != "low":
        problems.append("confidence must be low")
    if NEVER_TUNE not in str(document.get("use_rule", "")):
        problems.append(f"use_rule must say the reports are {NEVER_TUNE} the model")
    classes = {item.get("id") for item in document.get("depth_classes", ())}
    if not set(DEPTH_CLASSES) <= classes:
        problems.append("depth_classes must define every class the reports may use")
    reports = list(document.get("reports", ()))
    if not reports:
        problems.append("reports must list at least one report")
    ids = [report.get("id") for report in reports]
    if len(set(ids)) != len(ids):
        problems.append("report ids must be unique")
    for report in reports:
        name = report.get("id")
        located = report.get("location_confidence") in LOCATED_CONFIDENCE
        if located != (report.get("point") is not None):
            problems.append(f"{name}: a point is given exactly where the location confidence is medium or high")
        if located != (report.get("location_tolerance_m") is not None):
            problems.append(f"{name}: a located report needs a location tolerance, and only a located report has one")
        depth = report.get("depth", {})
        kind = depth.get("kind")
        if kind in NUMERIC_KINDS:
            if not isinstance(depth.get("lower_bound_m"), (int, float)) or depth.get("class") is not None:
                problems.append(f"{name}: a lower bound or a range needs a number and no class")
            if kind == "range" and not (isinstance(depth.get("upper_m"), (int, float)) and depth["upper_m"] > depth.get("lower_bound_m", math.inf)):
                problems.append(f"{name}: a range needs an upper end above its lower end")
        elif kind == "class":
            if depth.get("class") not in DEPTH_CLASSES or depth.get("lower_bound_m") is not None or depth.get("upper_m") is not None:
                problems.append(f"{name}: a class has no number, and its class must be one of the listed classes")
        else:
            problems.append(f"{name}: unknown depth kind {kind!r}")
        window = report.get("time", {})
        start, end = window.get("window_start"), window.get("window_end")
        if (start is None) != (end is None):
            problems.append(f"{name}: a window has both ends or neither")
        elif start is not None and local_instant(end) <= local_instant(start):
            problems.append(f"{name}: the window must end after it starts")
        if located and start is None:
            problems.append(f"{name}: a located report needs a time window to be compared")
    problems += statement_problems(reports)
    if len(document.get("assumptions_th") or ()) != len(document.get("assumptions") or ()):
        problems.append("assumptions_th must give one Thai assumption per English assumption")
    return problems + copyright_problems(document)


def _statement_key(report: Mapping[str, Any]) -> tuple:
    """What every place record of one statement shares: its source, its depth and its time window."""
    depth, window = report.get("depth") or {}, report.get("time") or {}
    return ((report.get("source") or {}).get("url"), depth.get("kind"), depth.get("lower_bound_m"), depth.get("upper_m"), depth.get("class"),
            window.get("window_start"), window.get("window_end"))


def statement_groups(reports: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Place records by ``statement_id``, in the order of each statement's first record."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for report in reports:
        groups.setdefault(str(report.get("statement_id")), []).append(report)
    return groups


def statement_problems(reports: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every way the place records break the statement rule (empty when it holds).

    A record's ``statement_id`` is the id of the first record of its statement, so the first record of a statement
    carries its own id; the records of one statement share its source, depth and time window (one statement recorded once
    per community it names).
    """
    problems: list[str] = []
    for statement, members in statement_groups(reports).items():
        if members[0].get("id") != statement:
            problems.append(f"statement {statement}: its first place record must be the one whose id it carries")
        if len({_statement_key(member) for member in members}) != 1:
            problems.append(f"statement {statement}: its place records must share one source, depth and time window")
    return problems


# --- The model at a report's point --------------------------------------------------------------------------


def local_instant(value: str) -> datetime:
    """An ISO 8601 date-time with an offset as an aware instant."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ReportedDepthsError(f"a window time needs a UTC offset: {value!r}")
    return moment


def window_max_stage(start_days: float, end_days: float, anchors: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """The highest assumed stage between ``start_days`` and ``end_days`` (days since the replay origin) and when.

    The stage is the linear interpolation between ``anchors`` (``(t, stage_m)``, held constant outside them), so its
    maximum over a window lies at one end of the window or at an anchor inside it. Ties keep the earliest time.
    """
    if end_days < start_days:
        raise ReportedDepthsError("a window must not end before it starts")
    knots = sorted(anchors)
    ts, values = [t for t, _ in knots], [value for _, value in knots]
    candidates = [start_days, *(t for t in ts if start_days < t < end_days), end_days]
    best_t, best = candidates[0], float(np.interp(candidates[0], ts, values))
    for t in candidates[1:]:
        stage = float(np.interp(t, ts, values))
        if stage > best + 1e-12:
            best_t, best = t, stage
    return best, best_t


def cell_depth(code: int, factor: float, stage_m: float, step_m: float = HAND_STEP_M) -> float | None:
    """Modelled water depth (m) of one out-of-channel cell at ``stage_m``: ``k * (stage - HAND_eff)``, never below 0.

    ``code`` is the effective HAND code (HAND / k in steps of ``step_m``) and ``factor`` the depth factor k. A cell
    above the encoded range (:data:`NEVER_CODE`) is dry at every stage. A channel cell is the river itself and has no
    depth to compare with a street: ``None``.
    """
    if code == CHANNEL_CODE:
        return None
    if code == NEVER_CODE:
        return 0.0
    return max(0.0, round(factor * (stage_m - code * step_m), 6))


def first_wet_hour(code: int, hourly_stages: Sequence[float], step_m: float = HAND_STEP_M) -> int | None:
    """The first replay hour (index into ``hourly_stages``) at which the cell is wet, or ``None`` when it never is."""
    if code in (CHANNEL_CODE, NEVER_CODE):
        return None
    for hour, stage in enumerate(hourly_stages):
        if stage > code * step_m:
            return hour
    return None


def point_model(codes: np.ndarray, factors: np.ndarray, valid: np.ndarray, row: int, col: int, cell_m: float, tolerance_m: float,
                stage_m: float, peak_stage_m: float, hourly_stages: Sequence[float], step_m: float = HAND_STEP_M) -> dict[str, Any]:
    """The model at a report's point: its depth at ``stage_m`` (the highest stage of the report's window), at the modelled
    peak, the first hour the cell is wet, and the deepest out-of-channel cell within ``tolerance_m`` (a sensitivity).

    ``codes`` (effective HAND codes), ``factors`` (depth factor k) and ``valid`` (inside the terrain model) share one
    north-up grid of ``cell_m`` cells; ``row`` and ``col`` are the point's cell. A point on a mapped channel cell is the
    river itself, so the nearest out-of-channel cell within the tolerance stands in for it, and the distance moved is
    recorded. Returns ``{"comparable": False, "reason": ...}`` when the point is outside the grid or the terrain model, or
    when no out-of-channel cell lies within the tolerance.
    """
    height, width = codes.shape
    if not (0 <= row < height and 0 <= col < width) or not bool(valid[row, col]):
        return {"comparable": False, "reason": "outside_model"}
    radius = max(0, int(math.floor(tolerance_m / cell_m)))
    r0, r1, c0, c1 = max(0, row - radius), min(height, row + radius + 1), max(0, col - radius), min(width, col + radius + 1)
    rows, cols = np.mgrid[r0:r1, c0:c1]
    distance = np.hypot(rows - row, cols - col) * cell_m
    window_codes = codes[r0:r1, c0:c1].astype(int)
    usable = (distance <= tolerance_m + 1e-9) & valid[r0:r1, c0:c1].astype(bool) & (window_codes != CHANNEL_CODE)
    cell, moved = "point", 0.0
    target = (row, col)
    if int(codes[row, col]) == CHANNEL_CODE:
        if not usable.any():
            return {"comparable": False, "reason": "channel_only_within_tolerance"}
        flat = int(np.argmin(np.where(usable, distance, np.inf)))
        target = (r0 + flat // (c1 - c0), c0 + flat % (c1 - c0))
        cell, moved = "nearest_out_of_channel", float(distance.flat[flat])
    code, factor = int(codes[target]), float(factors[target])
    depth = cell_depth(code, factor, stage_m, step_m)
    nearby = [cell_depth(int(c), float(k), stage_m, step_m) for c, k in zip(window_codes[usable], factors[r0:r1, c0:c1][usable])]
    return {
        "comparable": True, "cell": cell, "moved_m": round(moved, 1),
        "height_above_channel_m": None if code == NEVER_CODE else round(code * step_m * factor, 2),
        "depth_m": round(float(depth), 2),
        "peak_depth_m": round(float(cell_depth(code, factor, peak_stage_m, step_m)), 2),
        "first_wet_hour": first_wet_hour(code, hourly_stages, step_m),
        "max_within_tolerance_m": round(max((value for value in nearby if value is not None), default=0.0), 2),
    }


# --- Consistency ------------------------------------------------------------------------------------------------


def consistency_status(basis: str, reported_lower_bound_m: float | None, model_depth_m: float | None) -> str:
    """Whether the model is consistent with one report.

    ``not_comparable`` without a modelled depth (no point, no window, or a point the model cannot read); ``model_dry``
    when the model has no water there at any time in the window; for a numeric report ``consistent`` when the modelled
    depth reaches the reported lower bound and ``model_shallower`` when it is wet but shallower; for a class (a storey or
    body reference) ``model_wet`` when the model has the place wet. A class is never turned into a number, so its depth is
    not compared and it is never ``consistent``: 0.01 m of modelled water beside "over head height" is wet, nothing more.
    """
    if basis not in BASES:
        raise ReportedDepthsError(f"unknown comparison basis {basis!r}")
    if model_depth_m is None:
        return "not_comparable"
    if model_depth_m <= 0:
        return "model_dry"
    if basis == "qualitative":
        return "model_wet"
    if reported_lower_bound_m is None:
        raise ReportedDepthsError("a numeric report needs its lower bound")
    return "consistent" if model_depth_m + 1e-9 >= reported_lower_bound_m else "model_shallower"


def consistency_counts(rows: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Counts per outcome for ``(basis, status)`` pairs: one row per basis and their total (``all``).

    A status a basis cannot have (:data:`APPLIES`) is refused, so the ``consistent`` count of ``all`` holds numbers only.
    """
    counts = {basis: dict.fromkeys(STATUSES, 0) for basis in (*BASES, "all")}
    for basis, status in rows:
        if basis not in BASES or status not in APPLIES[basis]:
            raise ReportedDepthsError(f"unknown basis or status: {basis!r}, {status!r}")
        counts[basis][status] += 1
        counts["all"][status] += 1
    return counts


def statement_counts(rows: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Counts per outcome with each statement counted once, from ``(statement_id, status)`` pairs of place records.

    A statement recorded at one place keeps that place's outcome; one recorded at several places keeps their outcome when
    they all agree and counts as :data:`MIXED` when they do not.
    """
    outcomes: dict[str, set[str]] = {}
    for statement, status in rows:
        if status not in STATUSES:
            raise ReportedDepthsError(f"unknown status: {status!r}")
        outcomes.setdefault(statement, set()).add(status)
    counts = dict.fromkeys(STATEMENT_OUTCOMES, 0)
    for found in outcomes.values():
        counts[next(iter(found)) if len(found) == 1 else MIXED] += 1
    return counts


# --- The manifest block ------------------------------------------------------------------------------------------


COMPARISON_RULE = {
    "en": ("For each report with a point, the model is read at that point over the report's time window, on the replay's 10 m grid "
           "and hourly stage curve, and the deepest modelled water in the window is kept. A number is compared with its lower bound "
           "(consistent when the model reaches it, model shallower when it is wet but shallower); a storey or body reference is "
           "compared only as wet or dry (model wet or model dry), so its depth is never compared and it is never counted as "
           "consistent. A point on the mapped river channel is read at the nearest cell outside it. A report without a point or "
           "a window is not comparable."),
    "th": ("รายงานที่มีตำแหน่งจะอ่านค่าจากแบบจำลอง ณ จุดนั้นตลอดช่วงเวลาของรายงาน บนตารางกริด 10 ม. และเส้นระดับน้ำรายชั่วโมงของการย้อนดู "
           "แล้วเก็บความลึกมากที่สุดในช่วงนั้น ค่าที่เป็นตัวเลขเทียบกับค่าขั้นต่ำที่รายงาน (สอดคล้องเมื่อแบบจำลองลึกถึงค่านั้น แบบจำลองตื้นกว่า"
           "เมื่อมีน้ำแต่ตื้นกว่า) ส่วนการอ้างอิงชั้นของอาคารหรือระดับร่างกายเทียบเพียงว่ามีน้ำหรือแห้ง (แบบจำลองมีน้ำหรือแบบจำลองแห้ง) "
           "จึงไม่ได้เทียบความลึกและไม่นับเป็นสอดคล้อง จุดที่ตกบนร่องน้ำของแม่น้ำในแผนที่"
           "จะอ่านจากช่องที่ใกล้ที่สุดนอกร่องน้ำ รายงานที่ไม่มีตำแหน่งหรือไม่มีช่วงเวลาเทียบไม่ได้"),
}
TOLERANCE_RULE = {
    "en": ("Sensitivity, not part of the counts above: the same check with the deepest out-of-channel cell within each report's location "
           "tolerance instead of its point, since a community or street point can lie a few hundred metres from the reported spot."),
    "th": ("การทดสอบความไว ไม่นับรวมในตัวเลขข้างต้น: ตรวจแบบเดียวกันโดยใช้ช่องนอกร่องน้ำที่ลึกที่สุดภายในระยะคลาดเคลื่อนของตำแหน่งของแต่ละรายงาน"
           "แทนจุดของรายงาน เพราะจุดของชุมชนหรือถนนอาจห่างจากจุดที่รายงานไว้หลายร้อยเมตร"),
}
USE_RULE = {
    "en": ("A consistency check of anecdotal reports, never a validation: the reports were not surveyed and the model is illustrative. "
           "The reports are never used to tune the model: no keyframe, depth-factor or terrain change may be set from them."),
    "th": ("เป็นการตรวจความสอดคล้องกับรายงานที่เป็นคำบอกเล่า ไม่ใช่การยืนยันความถูกต้อง: รายงานไม่ได้ผ่านการสำรวจ และแบบจำลองใช้ค่าเพื่อการอธิบาย "
           "รายงานเหล่านี้ไม่ถูกนำไปใช้ปรับแบบจำลองเลย จะไม่มีการกำหนดจุดระดับน้ำ ตัวคูณความลึก หรือภูมิประเทศจากรายงานเหล่านี้"),
}
LOCAL_DRAINAGE_CAUSE = {
    "en": ("Local drainage: water came over the barrier under Friendship Bridge 1 and ran along streets and market lanes; a "
           "terrain-only model with one assumed river level has no such inflow paths, blocked drains or fast current."),
    "th": ("การระบายน้ำในพื้นที่: น้ำข้ามแนวกั้นใต้สะพานมิตรภาพแห่งที่ 1 แล้วไหลไปตามถนนและซอยในตลาด แบบจำลองที่ใช้เพียงภูมิประเทศ"
           "และระดับน้ำสมมุติระดับเดียวไม่มีเส้นทางน้ำไหลเข้าแบบนี้ ท่อระบายน้ำที่อุดตัน หรือกระแสน้ำที่ไหลแรง"),
}
THAI_MONTHS = {9: "ก.ย."}


def early_stage_until(anchors: Sequence[tuple[float, float]], origin: datetime, stage_m: float = EARLY_STAGE_M) -> datetime:
    """The instant the assumed stage first rises above ``stage_m`` (``anchors`` as ``(days since origin, stage_m)``).

    Up to that instant the model holds the river at or below ``stage_m``: reports of those hours see a dry town in the
    model (likely cause "timing"). The stage is linear between anchors, so the crossing is interpolated on its segment.
    """
    knots = sorted(anchors)
    for (t0, s0), (t1, s1) in zip(knots, knots[1:]):
        if s0 <= stage_m < s1:
            return origin + timedelta(days=t0 + (t1 - t0) * (stage_m - s0) / (s1 - s0))
        if s0 > stage_m:
            return origin + timedelta(days=t0)
    raise ReportedDepthsError(f"the assumed stage never rises above {stage_m} m")


def cause_figures(reports: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The counts the likely causes state, taken from the place records of a ``reported_depths`` block.

    * ``timing``: located numbers and located storey or body references (records with model values) and how many of each
      have a window whose highest assumed stage is at most :data:`EARLY_STAGE_M` (before the modelled rise), how many of
      those the model reads dry, and the latest end of their windows;
    * ``surface_model``: distinct report points with model values, how many sit :data:`HIGH_GROUND_M` or more above their
      channel, and how many above the highest level the model encodes;
    * ``location``: statements recorded at more than one place, and how many place records they make.
    """
    located = [report for report in reports if report.get("model") is not None]
    early = [report for report in located if report["model"]["window_max_stage_m"] <= EARLY_STAGE_M + 1e-9]
    numbers = [report for report in located if report["depth"]["basis"] == "numeric"]
    references = [report for report in located if report["depth"]["basis"] == "qualitative"]
    heights: dict[tuple[float, float], float | None] = {}
    for report in located:
        heights.setdefault((report["point"]["lat"], report["point"]["lon"]), report["model"]["height_above_channel_m"])
    shared = [members for members in statement_groups(reports).values() if len(members) > 1]
    return {
        "timing": {
            "located_numbers": len(numbers),
            "located_numbers_before_rise": sum(1 for report in early if report["depth"]["basis"] == "numeric"),
            "located_references": len(references),
            "located_references_before_rise": sum(1 for report in early if report["depth"]["basis"] == "qualitative"),
            "before_rise_model_dry": sum(1 for report in early if report["consistency"] == "model_dry"),
            "before_rise_last_window_end": max((report["time"]["window_end"] for report in early), key=local_instant, default=None),
        },
        "surface_model": {
            "points": len(heights),
            "points_raised": sum(1 for height in heights.values() if height is not None and height >= HIGH_GROUND_M),
            "points_above_encoded_range": sum(1 for height in heights.values() if height is None),
        },
        "location": {"shared_statements": len(shared), "records_in_shared_statements": sum(len(members) for members in shared)},
    }


def _clock(moment: datetime, language: str) -> str:
    local = moment.astimezone(ICT)
    if language == "th":
        return f"{local.day} {THAI_MONTHS[local.month]} {local:%H:%M} น."
    return f"{local.day} {local:%b} {local:%H:%M} ICT"


def _sit(count: int) -> str:
    return "sits" if count == 1 else "sit"


def likely_causes(figures: Mapping[str, Mapping[str, Any]], until: datetime) -> list[dict[str, Any]]:
    """Likely causes of the misses, said plainly: neither the model nor the reports are judged.

    Every count in the text comes from ``figures`` (:func:`cause_figures`) and ``until`` is when the assumed stage first
    rises above :data:`EARLY_STAGE_M` (:func:`early_stage_until`), so the sentences follow the place records they describe.
    """
    timing, ground, location = figures["timing"], figures["surface_model"], figures["location"]
    early = timing["located_numbers_before_rise"] + timing["located_references_before_rise"]
    last_end = local_instant(timing["before_rise_last_window_end"]) if timing["before_rise_last_window_end"] else until
    dry_en = (f"all {early} of these read dry" if timing["before_rise_model_dry"] == early
              else f"{timing['before_rise_model_dry']} of these {early} read dry")
    dry_th = (f"แบบจำลองแห้งที่ทั้ง {early} รายการนี้" if timing["before_rise_model_dry"] == early
              else f"แบบจำลองแห้งที่ {timing['before_rise_model_dry']} จาก {early} รายการนี้")
    shared_en = (f"{location['shared_statements']} statement names several communities and is recorded once per community"
                 if location["shared_statements"] == 1
                 else f"{location['shared_statements']} statements each name several communities and are recorded once per community")
    return [
        {"id": "timing", "figures": {**timing, "early_stage_m": EARLY_STAGE_M, "early_stage_until": local_iso(until)},
         "text": {"en": (f"Timing: {timing['located_numbers_before_rise']} of the {timing['located_numbers']} located numbers and "
                         f"{timing['located_references_before_rise']} of the {timing['located_references']} located storey or body references "
                         f"have a time window that ends by {_clock(last_end, 'en')}. The model's assumed river level stays at or below "
                         f"{EARLY_STAGE_M} m until {_clock(until, 'en')}, the level set to GISTDA's district-wide area figure for that "
                         f"evening, and rises mainly overnight, so riverside streets are dry in the model at those hours even where it "
                         f"floods them later; {dry_en}."),
                  "th": (f"เวลา: ตัวเลขที่มีตำแหน่ง {timing['located_numbers_before_rise']} จาก {timing['located_numbers']} รายการ "
                         f"และการอ้างอิงชั้นอาคารหรือระดับร่างกายที่มีตำแหน่ง {timing['located_references_before_rise']} จาก "
                         f"{timing['located_references']} รายการ มีช่วงเวลาที่สิ้นสุดไม่เกิน {_clock(last_end, 'th')} "
                         f"ระดับน้ำสมมุติของแบบจำลองไม่เกิน {EARLY_STAGE_M} ม. จนถึง {_clock(until, 'th')} ซึ่งเป็นระดับที่ตั้งตามตัวเลข"
                         "พื้นที่น้ำท่วมทั้งอำเภอของ GISTDA ในเย็นวันนั้น และสูงขึ้นส่วนใหญ่ในช่วงกลางคืน ถนนริมน้ำในแบบจำลองจึงยังแห้ง"
                         f"ในชั่วโมงเหล่านั้น แม้จะมีน้ำท่วมในภายหลัง {dry_th}")}},
        {"id": "surface_model", "figures": dict(ground),
         "text": {"en": ("Town ground: the 30 m surface model includes buildings and trees, so it raises the ground of the market and the "
                         f"riverside lanes; in the model {ground['points_raised']} of the {ground['points']} report points "
                         f"{_sit(ground['points_raised'])} {HIGH_GROUND_M:g} m or more above their channel, and "
                         f"{ground['points_above_encoded_range']} {_sit(ground['points_above_encoded_range'])} above the highest level "
                         "the model encodes."),
                  "th": ("ระดับพื้นในเมือง: แบบจำลองพื้นผิวความละเอียด 30 ม. รวมอาคารและต้นไม้ไว้ด้วย จึงทำให้พื้นของตลาดและซอยริมน้ำสูงขึ้น "
                         f"ในแบบจำลอง จุดของรายงาน {ground['points_raised']} จาก {ground['points']} จุดอยู่สูงจากร่องน้ำตั้งแต่ "
                         f"{HIGH_GROUND_M:g} ม. ขึ้นไป และ {ground['points_above_encoded_range']} จุดอยู่สูงกว่าระดับสูงสุดที่แบบจำลองบันทึกไว้")}},
        {"id": "local_drainage", "text": dict(LOCAL_DRAINAGE_CAUSE)},
        {"id": "location", "figures": dict(location),
         "text": {"en": ("Location: community points are the middle of mapped streets or a nearby landmark, and several statements cover a "
                         f"whole community (in places), so the reported spot can lie a few hundred metres from the point. {shared_en} "
                         f"({location['records_in_shared_statements']} place records), so one statement can read differently at its places."),
                  "th": ("ตำแหน่ง: จุดของชุมชนคือกึ่งกลางของถนนในแผนที่หรือสถานที่ใกล้เคียง และหลายข้อความกล่าวถึงทั้งชุมชน (บางจุด) "
                         "จุดที่รายงานจึงอาจห่างจากจุดบนแผนที่หลายร้อยเมตร "
                         f"มี {location['shared_statements']} ข้อความที่กล่าวถึงหลายชุมชนและบันทึกแยกหนึ่งรายการต่อหนึ่งชุมชน "
                         f"({location['records_in_shared_statements']} รายการตามสถานที่) ข้อความเดียวจึงอาจให้ผลต่างกันในแต่ละสถานที่")}},
    ]

LABEL = {"en": "Reported depths (news, not surveyed)", "th": "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)"}
EVIDENCE_TIER = "Reported (anecdotal, not surveyed): news reports of depth at named places, paraphrased and cited; not an official record"
MODEL_FIELDS_NOTE = ("T1 scenario (model) values read at each report's point for the comparison; they are not part of the reports.")


def local_iso(moment: datetime) -> str:
    """``moment`` in ICT as ``YYYY-MM-DDTHH:MM:SS+07:00``."""
    return moment.astimezone(ICT).replace(microsecond=0).isoformat()


def statement_summary(reports: Sequence[Mapping[str, Any]]) -> tuple[dict[str, int], dict[str, int], list[dict[str, Any]]]:
    """What the place records add up to: how many records, statements and articles (``counted``), the outcomes with each
    statement counted once (:func:`statement_counts`), and every statement recorded at more than one place with its
    records and their outcomes (``shared_statements``)."""
    groups = statement_groups(reports)
    counted = {"place_records": len(reports), "statements": len(groups),
               "articles": len({report["source"]["url"] for report in reports})}
    by_statement = statement_counts((str(report["statement_id"]), str(report["consistency"])) for report in reports)
    shared = [{"statement_id": statement, "reports": [member["id"] for member in members],
               "outcomes": [member["consistency"] for member in members]}
              for statement, members in groups.items() if len(members) > 1]
    return counted, by_statement, shared


def manifest_block(document: Mapping[str, Any], models: Mapping[str, dict[str, Any] | None], *, origin: datetime, data_file: Mapping[str, Any],
                   window_stage: Callable[[float, float], tuple[float, float]], peak_stage_m: float, early_until: datetime) -> dict[str, Any]:
    """The ``reported_depths`` block of the replay manifest.

    ``models`` maps a report id to :func:`point_model`'s result for its point at the highest stage of its window (absent
    or ``None`` for a report without a point or a window). ``origin`` is the replay's t = 0, ``window_stage`` gives the
    highest stage of a window and when (:func:`window_max_stage` over the replay's anchors), ``early_until`` is when the
    assumed stage first rises above :data:`EARLY_STAGE_M` (:func:`early_stage_until`) and ``data_file`` names the data
    file by path and SHA-256. Each place record keeps what the page shows (place, paraphrase, time, source, location
    confidence), its statement and its outcome; the model's values sit under ``model`` and are T1 scenario values. The
    counts are given per place record and once per statement, and the likely causes take their counts from the records.
    """
    reports = []
    rows: list[tuple[str, str]] = []
    rows_tolerance: list[tuple[str, str]] = []
    for report in document["reports"]:
        depth = report["depth"]
        basis = comparison_basis(depth)
        bound = lower_bound(depth)
        start, end = report["time"]["window_start"], report["time"]["window_end"]
        result = models.get(report["id"]) if report["point"] is not None and start is not None else None
        model = None
        if result is not None and result.get("comparable"):
            days = lambda value: (local_instant(value) - origin).total_seconds() / 86400  # noqa: E731
            stage, at = window_stage(days(start), days(end))
            model = {
                "cell": result["cell"], "moved_m": result["moved_m"], "height_above_channel_m": result["height_above_channel_m"],
                "window_max_stage_m": round(stage, 3), "window_max_at": local_iso(origin + timedelta(days=at)),
                "depth_m": result["depth_m"], "peak_depth_m": result["peak_depth_m"],
                "first_wet": None if result["first_wet_hour"] is None else local_iso(origin + timedelta(hours=result["first_wet_hour"])),
                "max_within_tolerance_m": result["max_within_tolerance_m"],
            }
            # The outcome follows from the published (rounded) figures, so a reader can redo it from the block.
            status = consistency_status(basis, bound, model["depth_m"])
            status_tolerance = consistency_status(basis, bound, model["max_within_tolerance_m"])
        else:
            status = status_tolerance = "not_comparable"
        rows.append((basis, status))
        rows_tolerance.append((basis, status_tolerance))
        reports.append({
            "id": report["id"], "statement_id": report["statement_id"], "place": report["place"], "tambon": report["tambon"],
            "point": report["point"], "location_confidence": report["location_confidence"],
            "location_tolerance_m": report["location_tolerance_m"],
            "depth": {"basis": basis, **{key: depth[key] for key in ("kind", "lower_bound_m", "upper_m", "class", "statement")}},
            "time": {key: report["time"][key] for key in ("text", "window_start", "window_end")},
            "source": {key: report["source"][key] for key in ("title", "publisher", "url", "published", "language")},
            "model": model,
            "consistency": status,
            "consistency_within_tolerance": status_tolerance,
        })
    published = sorted(local_instant(report["source"]["published"] if "T" in report["source"]["published"]
                                     else f"{report['source']['published']}T00:00:00+07:00") for report in document["reports"])
    counted, by_statement, shared = statement_summary(reports)
    return {
        "id": "reported-depths-2024",
        "label": LABEL,
        "status": STATUS,
        "lane": LANE,
        "evidence_tier": EVIDENCE_TIER,
        "confidence": "low",
        "confidence_reason": {"en": document["confidence_reason"],
                              "th": ("รายงานข่าวที่เป็นคำบอกเล่า ไม่ใช่การสำรวจ: ความลึกเป็นค่าขั้นต่ำ ช่วงค่า หรือการอ้างอิงชั้นของอาคารและระดับร่างกาย "
                                     "หลายข้อความกล่าวถึงมากกว่าหนึ่งชุมชน เวลาเป็นเวลาของข่าว ไม่ใช่เวลาที่วัด และตำแหน่งส่วนใหญ่เป็นจุดของชุมชนหรือถนน")},
        "source_timestamp": (f"reports published {local_iso(published[0])}/{local_iso(published[-1])}; compiled {document['compiled']}"),
        "compiled": document["compiled"],
        "data_file": dict(data_file),
        "use_rule": USE_RULE,
        "assumptions": {"en": list(document["assumptions"]), "th": list(document["assumptions_th"])},
        "comparison_rule": COMPARISON_RULE,
        "tolerance_rule": TOLERANCE_RULE,
        "peak_stage_m": peak_stage_m,
        "depth_classes": document["depth_classes"],
        "counted": counted,
        "counts": consistency_counts(rows),
        "counts_within_tolerance": consistency_counts(rows_tolerance),
        "counts_by_statement": by_statement,
        "shared_statements": shared,
        "likely_causes": likely_causes(cause_figures(reports), early_until),
        "model_fields": {"paths": ["reports[].model"], "evidence_tier": "T1 scenario (model)", "note": MODEL_FIELDS_NOTE},
        "left_out": {"dropped": len(document["left_out"]["dropped"]), "excluded": document["left_out"]["excluded_count"]},
        "reports": reports,
    }


def block_problems(block: Mapping[str, Any]) -> list[str]:
    """Every way a ``reported_depths`` block breaks its rules (empty when it holds).

    The block is "reported (anecdotal, not surveyed)" in lane REP; its use rule says the reports are never used to tune
    the model and that the check is never a validation; a report has a point only at medium or high location confidence;
    a report without a point, or without model values, is not comparable; every outcome follows from the report's lower
    bound or class and the modelled depth; and the counts are the tallies of the outcomes.
    """
    problems: list[str] = []
    if block.get("status") != STATUS or block.get("lane") != LANE:
        problems.append(f"reported_depths must be {STATUS!r} in lane {LANE}")
    rule = block.get("use_rule") or {}
    if NEVER_TUNE not in str(rule.get("en", "")) or "never a validation" not in str(rule.get("en", "")):
        problems.append("reported_depths.use_rule must say the reports are never used to tune the model and the check is never a validation")
    rows, rows_tolerance = [], []
    for report in block.get("reports") or ():
        name = f"reported_depths.reports[{report.get('id')}]"
        located = report.get("location_confidence") in LOCATED_CONFIDENCE
        if located != (report.get("point") is not None):
            problems.append(f"{name}: a point is given exactly where the location confidence is medium or high")
        depth = report.get("depth") or {}
        basis = comparison_basis(depth)
        if depth.get("basis") != basis:
            problems.append(f"{name}: its comparison basis must follow its depth kind")
        model = report.get("model")
        if model is not None and report.get("point") is None:
            problems.append(f"{name}: a report without a point has no model values")
        expected = consistency_status(basis, lower_bound(depth), None if model is None else model.get("depth_m"))
        expected_tolerance = consistency_status(basis, lower_bound(depth), None if model is None else model.get("max_within_tolerance_m"))
        if report.get("consistency") != expected:
            problems.append(f"{name}: consistency {report.get('consistency')!r} does not follow from its figures ({expected!r})")
        if report.get("consistency_within_tolerance") != expected_tolerance:
            problems.append(f"{name}: consistency_within_tolerance does not follow from its figures")
        rows.append((basis, str(report.get("consistency"))))
        rows_tolerance.append((basis, str(report.get("consistency_within_tolerance"))))
    try:
        if block.get("counts") != consistency_counts(rows):
            problems.append("reported_depths.counts must be the tallies of the reports' outcomes")
        if block.get("counts_within_tolerance") != consistency_counts(rows_tolerance):
            problems.append("reported_depths.counts_within_tolerance must be the tallies of the reports' outcomes")
    except ReportedDepthsError as exc:
        problems.append(f"reported_depths: {exc}")
    problems += _statement_and_cause_problems(block)
    assumptions = block.get("assumptions") or {}
    if not assumptions.get("en") or len(assumptions.get("en") or ()) != len(assumptions.get("th") or ()):
        problems.append("reported_depths.assumptions must give every assumption of the data file in English and Thai")
    return problems


def _statement_and_cause_problems(block: Mapping[str, Any]) -> list[str]:
    """The statement rule, the per-statement counts and the likely causes' counts of a block (empty when they hold)."""
    reports = list(block.get("reports") or ())
    if not all(isinstance(report, Mapping) and report.get("statement_id") for report in reports):
        return ["reported_depths: every place record must name its statement"]
    problems = [f"reported_depths: {line}" for line in statement_problems(reports)]
    try:
        counted, by_statement, shared = statement_summary(reports)
    except (KeyError, ReportedDepthsError) as exc:
        return [*problems, f"reported_depths: {exc}"]
    if block.get("counted") != counted:
        problems.append("reported_depths.counted must count the place records, statements and articles of the reports")
    if block.get("counts_by_statement") != by_statement:
        problems.append("reported_depths.counts_by_statement must count each statement once")
    if block.get("shared_statements") != shared:
        problems.append("reported_depths.shared_statements must list every statement recorded at more than one place")
    causes = list(block.get("likely_causes") or ())
    timing = next((cause for cause in causes if isinstance(cause, Mapping) and cause.get("id") == "timing"), None)
    try:
        until = local_instant(str(((timing or {}).get("figures") or {}).get("early_stage_until")))
        expected = likely_causes(cause_figures(reports), until)
    except (KeyError, TypeError, ValueError) as exc:
        return [*problems, f"reported_depths.likely_causes cannot be rebuilt from the reports: {exc}"]
    if causes != expected:
        problems.append("reported_depths.likely_causes must take every count from the reports (rebuilt causes differ)")
    return problems
