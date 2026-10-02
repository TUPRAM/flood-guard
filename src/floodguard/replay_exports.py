"""Export pack of the Mae Sai case replay for spreadsheet and GIS users.

District and DDPM staff work in spreadsheets and GIS, not in a web replay. This
module turns the replay's modelled blocks into files they can open: three shelter
plan tables, one GeoJSON of the sites, modelled road inundation by hour, modelled
access loss by hour, a shelter-candidate verification sheet and a licence README.

Everything here is pure: the functions take plain data and return rows or bytes;
``scripts/build_mae_sai_flood_timeline.py`` supplies the data and writes the
files. Nothing computes a Flood Preparedness Priority Score or an action class.

Where the provenance sits
-------------------------
Every CSV starts with provenance lines (``# key,value``) and only then the column
header. A sidecar file would keep spreadsheet import trivial, but it is lost the
moment a table is forwarded on its own, and the risk of this pack is exactly that
a modelled table is read as an operational record. So the tier, the confidence,
the timestamps, the assumptions and the licence travel inside the file. Excel and
LibreOffice open such a file as it is (the lines show as rows above the header);
QGIS and pandas skip the number of lines the second line states. A GeoJSON file
cannot hold comments, so it carries the same fields in a top-level ``metadata``
member written before the features.

Licences
--------
One share-alike lineage per file: every file is OpenStreetMap-derived and stays
under ODbL 1.0; the other inputs are attribution-only. No file holds HII rain
values (CC BY-NC) or anything from a source without a stated licence, and nothing
from UNOSAT/GISTDA product 4009. :func:`licence_problems` enforces this.

The tables are a T1 scenario (model) on a reconstructed flood: modelled, not
observed, not a forecast and not an official warning.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
import re
from typing import Any

import numpy as np

from floodguard.evacuation_access import NEVER_LOST, NO_BASELINE_ACCESS
from floodguard.flood_timeline import road_state

EXPORT_FOLDER = "exports"
"""Sub-folder of the replay revision that holds the pack."""

EXPORT_TIER = ("T1 scenario (model) replay of a reconstructed 2024 event for preparedness planning and exercises; illustrative stage "
               "keyframes; not a forecast, not an observed closure record, not an official warning; non_operational; accepted_* null")
"""The standard sentence every export header carries."""

EXPORT_TIER_TH = ("การย้อนดูสถานการณ์จำลองระดับ T1 (แบบจำลอง) ของเหตุการณ์ปี 2567 (2024) ที่จำลองขึ้นใหม่ เพื่อการวางแผนเตรียมความพร้อมและการฝึกซ้อม "
                  "ใช้จุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่การพยากรณ์ ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง ไม่ใช่การเตือนภัยอย่างเป็นทางการ "
                  "ไม่ใช้ในการปฏิบัติการ และไม่มีคะแนนหรือระดับการดำเนินการที่ยอมรับ (accepted_* เป็น null)")

SCENARIO_TIER = "T1 scenario (model)"
CONFIDENCE_CLASS = "low"
CONFIDENCE_REASON = ("The tables come from a terrain-model reconstruction with illustrative stages, WorldPop 2020 residents, OpenStreetMap roads "
                     "and sites, and unverified capacity estimates; nothing was checked on the ground.")
CONFIDENCE_REASON_TH = ("ตารางมาจากการจำลองด้วยแบบจำลองภูมิประเทศและระดับน้ำสมมุติ ผู้อยู่อาศัยตาม WorldPop 2020 ถนนและสถานที่จาก OpenStreetMap "
                        "และค่าประมาณความจุที่ยังไม่ได้ตรวจสอบ ยังไม่มีการตรวจสอบในพื้นที่")
CONFIDENCE_REASON_CHECKED = ("The tables come from a terrain-model reconstruction with illustrative stages, WorldPop 2020 residents, OpenStreetMap "
                             "roads and sites, and unverified capacity estimates. A local check of some shelter candidates was returned "
                             "(reported by role, not an official register) and is not used in these tables; nothing else was checked on the ground.")
CONFIDENCE_REASON_CHECKED_TH = ("ตารางมาจากการจำลองด้วยแบบจำลองภูมิประเทศและระดับน้ำสมมุติ ผู้อยู่อาศัยตาม WorldPop 2020 ถนนและสถานที่จาก OpenStreetMap "
                                "และค่าประมาณความจุที่ยังไม่ได้ตรวจสอบ มีผลการตรวจสอบสถานที่บางแห่งในพื้นที่ส่งกลับมาแล้ว (รายงานตามบทบาท ไม่ใช่ทะเบียนทางการ) "
                                "แต่ตารางเหล่านี้ไม่ได้ใช้ผลดังกล่าว และยังไม่มีการตรวจสอบสิ่งอื่นใดในพื้นที่")


def confidence_reason(conducted: bool) -> tuple[str, str]:
    """Why the pack's confidence is low, in English and Thai.

    Until a verification sheet is returned it says nothing was checked on the ground. Afterwards it says a local
    check exists, that the tables do not use it and that nothing else was checked: the sentence must not go on
    denying a check the same pack reports.
    """
    return (CONFIDENCE_REASON_CHECKED, CONFIDENCE_REASON_CHECKED_TH) if conducted else (CONFIDENCE_REASON, CONFIDENCE_REASON_TH)


CAPACITY_BASIS_TH: Mapping[str, str] = {
    "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified": "พื้นที่อาคารใน OSM x 0.5 / 3.5 ตร.ม. ต่อคน (Sphere) ยังไม่ได้ตรวจสอบ",
    "unknown": "ไม่ทราบ",
}
"""Thai wording of the two capacity-basis phrases, for the ``capacity_basis_th`` companion column."""
OPERATIONAL_STATUS = "non_operational"
ACCEPTED_NULL = "accepted_fpps=null; accepted_action_class=null (no priority score and no action class is computed)"
NOT_INCLUDED = ("No HII rain values (CC BY-NC), nothing from a source without a stated licence and nothing from UNOSAT/GISTDA "
                "product 4009 is in this file.")
NOT_INCLUDED_TH = ("ไฟล์นี้ไม่มีค่าปริมาณฝนของ สสน. (CC BY-NC) ไม่มีข้อมูลจากแหล่งที่ไม่ระบุสัญญาอนุญาต "
                   "และไม่มีข้อมูลใดจากผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA")
VERIFICATION_LABEL = "Checked by <role> on <date>; not an official shelter register"
VERIFICATION_LABEL_TH = "ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ"

BOM = "﻿".encode("utf-8")
"""UTF-8 byte-order mark: with it Excel reads the Thai text of a CSV correctly."""

LEGACY_ROAD_COLUMNS: tuple[str, ...] = ("road_disruption_probability_0_1", "candidate_status", "confidence_class")
"""Columns of ``outputs/mae_sai_road_risk.geojson`` from the superseded Sentinel-1 change heuristic; never exported."""

EXPORT_LICENCE = "ODbL 1.0"
EXPORT_LICENCE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
SHARE_ALIKE_SOURCE = "osm"
"""The one share-alike source an export may derive from."""

FORBIDDEN_SOURCES: frozenset[str] = frozenset({"hii-rain", "viirs", "unosat-4009"})
"""Sources that may never feed an export: CC BY-NC rain, a product with no stated licence, and product 4009."""

_FORBIDDEN_COLUMN = re.compile(r"rain|_mm(?![a-z])|unosat|4009|viirs|fpps|action[_-]?class|priority[_-]?score", re.IGNORECASE)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_HEADER_KEY = re.compile(r"^# ?([A-Za-z0-9_]+)$")


class ReplayExportError(ValueError):
    """Raised when an export would break its header, licence or content rules."""


# --- Small data types -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    """One table column: a stable English key, its Thai label and what it holds."""

    key: str
    th: str
    en: str

    @property
    def label(self) -> str:
        """The bilingual header cell: the English key, then the Thai label in brackets."""
        return f"{self.key} ({self.th})"


@dataclass(frozen=True)
class ExportFile:
    """One file of the pack, ready to write, with what the manifest says about it."""

    id: str
    name: str
    media_type: str
    data: bytes
    title: Mapping[str, str]
    lanes: tuple[str, ...]
    sources: tuple[str, ...]
    rows: int | None
    header_lines: int | None
    columns: tuple[Column, ...] = ()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def record(self, href_prefix: str) -> dict[str, Any]:
        """The manifest record of the file: where it is, its hash and size, its lanes, licence and lineage."""
        record: dict[str, Any] = {
            "id": self.id, "name": self.name, "href": f"{href_prefix}{self.name}", "sha256": self.sha256, "bytes": len(self.data),
            "media_type": self.media_type, "title": dict(self.title), "lanes": list(self.lanes),
            "licence": EXPORT_LICENCE, "source_ids": list(self.sources),
        }
        if self.rows is not None:
            record["rows"] = self.rows
        if self.header_lines is not None:
            record["header_lines"] = self.header_lines
        return record


@dataclass(frozen=True)
class ExportContext:
    """Everything the pack is written from. The bake fills it; the tests fill it with small synthetic data.

    ``inputs`` are the input receipt's rows (``root``, ``path``, ``bytes``, ``sha256``) and ``sources`` the
    manifest's source list (``id``, ``name``, ``licence``, ``attribution``). ``ways`` holds one mapping per
    OpenStreetMap way (``road_id``, ``road_name``, ``road_class``, ``bridge_flag``, ``tambon_id``, ``length_m`` and
    ``pieces``, each piece ``(lowest effective HAND or None, depth factor, inside the model)``).
    ``node_tambon`` is the 1-based index into ``tambons`` per resident node (0 = none), ``cut_codes`` the per-node
    cut codes of the two shelter sets (``reported_2024`` and the knee plan).
    """

    study_id: str
    revision: str
    generated_at: str
    generated_by: str
    receipt_path: str
    repo_folder: str
    inputs: Sequence[Mapping[str, Any]]
    sources: Sequence[Mapping[str, Any]]
    hourly_stages: Sequence[float]
    event_start: str
    osm_extract_date: str
    reported_compiled: str
    impassable_depth_m: float
    road_classes: Sequence[str]
    ways: Sequence[Mapping[str, Any]]
    tambons: Sequence[Mapping[str, str]]
    node_tambon: np.ndarray
    node_population: np.ndarray
    cut_codes: Mapping[str, np.ndarray]
    level_step_m: float
    knee_k: int
    candidates: Sequence[Mapping[str, Any]]
    plan: Sequence[Mapping[str, Any]]
    capacitated: Mapping[str, Any]
    robust_core: Sequence[str]
    reported: Sequence[Mapping[str, Any]]
    peak_stage_m: float
    walk_limit_m: float
    freeboard_m: float
    snap_max_m: float
    licence_overrides: Mapping[str, Sequence[str]] = field(default_factory=dict)
    """Tests only: replace the source ids of a file to show that :func:`licence_problems` refuses a bad mix."""
    verification_status: str = "not_conducted"
    """``conducted`` once a returned verification sheet has been imported; the blank sheet and the README then stop
    saying that no check has been conducted. The checked rows themselves are in the manifest, never in the sheet."""


# --- Hours ---------------------------------------------------------------------------------------------------


def hour_local_time(hour: int, event_start: str) -> str:
    """ISO 8601 local time of a replay hour (hour 0 is ``event_start``, which carries its UTC offset)."""
    return (datetime.fromisoformat(event_start) + timedelta(hours=int(hour))).isoformat()


def impassable_hours(pieces: Iterable[Sequence[Any]], stages: Sequence[float], cache: dict | None = None) -> np.ndarray:
    """Boolean mask over ``stages``: the hours at which a way is impassable somewhere.

    A piece counts only when it is inside the model and has a usable height. The rule is
    ``floodguard.flood_timeline.road_state`` itself, so the hours agree with the page's road states.
    """
    mask = np.zeros(len(stages), dtype=bool)
    memo = cache if cache is not None else {}
    for hand, factor, modelled, *_ in pieces:
        if not modelled or hand is None:
            continue
        key = (float(hand), float(factor))
        if key not in memo:
            memo[key] = np.array([road_state(key[0], float(stage), key[1]) == "impassable" for stage in stages], dtype=bool)
        mask |= memo[key]
    return mask


def impassable_interval(mask: np.ndarray) -> tuple[int | None, int | None, int]:
    """First impassable hour, the hour the way is passable again, and the number of impassable hours.

    The passable-again hour is the first hour after the last impassable one; it is ``None`` when the way is still
    impassable at the last hour, or was never impassable.
    """
    hours = np.flatnonzero(np.asarray(mask, dtype=bool))
    if hours.size == 0:
        return None, None, 0
    last = int(hours[-1])
    return int(hours[0]), (last + 1 if last + 1 < len(mask) else None), int(hours.size)


# --- Rows ----------------------------------------------------------------------------------------------------

ROAD_COLUMNS: tuple[Column, ...] = (
    Column("road_id", "รหัสทาง OSM", "OpenStreetMap way id"),
    Column("road_name", "ชื่อถนน", "Road name in OpenStreetMap (blank when the way has none)"),
    Column("road_class", "ประเภทถนน", "Road class (trunk, primary, secondary, tertiary, unclassified, residential)"),
    Column("bridge_flag", "เป็นสะพาน", "yes when OpenStreetMap tags the way as a bridge; the deck is not modelled, so read its hours as unknown"),
    Column("tambon_id", "รหัสตำบล", "Subdistrict code (COD-AB ADM3)"),
    Column("tambon_name_th", "ชื่อตำบล", "Subdistrict name in Thai"),
    Column("tambon_name_en", "ชื่อตำบลภาษาอังกฤษ", "Subdistrict name in English"),
    Column("length_m", "ความยาว ม.", "Length of the way in metres"),
    Column("in_model_area", "อยู่ในพื้นที่แบบจำลอง",
           "yes when at least one part of the way lies inside the water model (a way on high ground is inside it and never impassable)"),
    Column("modelled_first_impassable_hour", "ชั่วโมงแรกที่สัญจรไม่ได้ตามแบบจำลอง",
           "First replay hour at which the modelled depth reaches the impassable depth somewhere on the way (blank: never)"),
    Column("modelled_first_impassable_local_time", "เวลาท้องถิ่นของชั่วโมงแรกที่สัญจรไม่ได้", "That hour as local time (ICT, UTC+7)"),
    Column("modelled_passable_again_hour", "ชั่วโมงที่กลับมาสัญจรได้ตามแบบจำลอง",
           "First replay hour after the last impassable hour (blank: never impassable, or still impassable at the end of the replay)"),
    Column("modelled_passable_again_local_time", "เวลาท้องถิ่นของชั่วโมงที่กลับมาสัญจรได้", "That hour as local time (ICT, UTC+7)"),
    Column("modelled_impassable_hours", "จำนวนชั่วโมงที่สัญจรไม่ได้ตามแบบจำลอง", "Number of replay hours at which the way is impassable"),
)


def road_inundation_rows(ways: Sequence[Mapping[str, Any]], stages: Sequence[float], tambons: Sequence[Mapping[str, str]],
                         event_start: str) -> list[dict[str, Any]]:
    """One row per OpenStreetMap way: identity, and the modelled first-impassable and passable-again replay hours.

    The source file's legacy candidate columns are not read. Rows are sorted by ``road_id``.
    """
    names = {tambon["id"]: tambon for tambon in tambons}
    cache: dict = {}
    rows = []
    for way in sorted(ways, key=lambda item: (len(str(item["road_id"])), str(item["road_id"]))):
        pieces = list(way["pieces"])
        first, again, count = impassable_interval(impassable_hours(pieces, stages, cache))
        tambon = names.get(way.get("tambon_id"), {})
        rows.append({
            "road_id": str(way["road_id"]), "road_name": way.get("road_name") or "", "road_class": way["road_class"],
            "bridge_flag": bool(way.get("bridge_flag")), "tambon_id": way.get("tambon_id") or "",
            "tambon_name_th": tambon.get("th", ""), "tambon_name_en": tambon.get("en", ""),
            "length_m": int(round(float(way["length_m"]))),
            "in_model_area": any(bool(piece[2]) for piece in pieces),
            "modelled_first_impassable_hour": first,
            "modelled_first_impassable_local_time": None if first is None else hour_local_time(first, event_start),
            "modelled_passable_again_hour": again,
            "modelled_passable_again_local_time": None if again is None else hour_local_time(again, event_start),
            "modelled_impassable_hours": count,
        })
    return rows


def access_columns(knee_k: int) -> tuple[Column, ...]:
    """Columns of the access-loss table for a knee plan of ``knee_k`` sites."""
    plan_th = f"แผน {knee_k} แห่งแรก"
    plan_en = f"the first {knee_k} sites of the modelled coverage ranking"
    return (
        Column("tambon_id", "รหัสตำบล", "Subdistrict code (COD-AB ADM3)"),
        Column("tambon_name_th", "ชื่อตำบล", "Subdistrict name in Thai"),
        Column("tambon_name_en", "ชื่อตำบลภาษาอังกฤษ", "Subdistrict name in English"),
        Column("replay_hour", "ชั่วโมงของการย้อนดู", "Replay hour (0 = 9 Sep 2024 00:00 ICT)"),
        Column("local_time", "เวลาท้องถิ่น", "That hour as local time (ICT, UTC+7)"),
        Column("modelled_stage_m", "ระดับน้ำสมมุติ ม.", "Assumed stage at the start of the hour, metres (illustrative keyframes)"),
        Column("residents", "ผู้อยู่อาศัยที่จุดถนน", "Modelled residents at road nodes in the subdistrict (WorldPop 2020)"),
        Column("reported_2024_within_reach_before_flood", "ชุดที่มีรายงานปี 2567 (2024): ผู้อยู่อาศัยที่เข้าถึงได้ก่อนน้ำท่วม",
               "Residents with a shelter of the reported 2024 set within reach before the flood"),
        Column("reported_2024_lost_access", "ชุดที่มีรายงานปี 2567 (2024): ผู้อยู่อาศัยที่สูญเสียการเข้าถึง",
               "Of those, residents who have lost access at this hour"),
        Column("knee_plan_within_reach_before_flood", f"{plan_th}: ผู้อยู่อาศัยที่เข้าถึงได้ก่อนน้ำท่วม",
               f"Residents with a site of {plan_en} within reach before the flood"),
        Column("knee_plan_lost_access", f"{plan_th}: ผู้อยู่อาศัยที่สูญเสียการเข้าถึง", "Of those, residents who have lost access at this hour"),
    )


def _level_index(stage_m: float, level_step_m: float) -> int:
    return int(math.floor(stage_m / level_step_m + 1e-6))


def access_loss_rows(tambons: Sequence[Mapping[str, str]], node_tambon: np.ndarray, node_population: np.ndarray,
                     cut_codes: Mapping[str, np.ndarray], stages: Sequence[float], event_start: str, level_step_m: float,
                     knee_set: str, reported_set: str = "reported_2024") -> list[dict[str, Any]]:
    """One row per subdistrict and replay hour: residents within reach before the flood and residents who lost it.

    Both shelter sets are counted against their own baseline, side by side; nothing here grades a set. Sums are
    exactly rounded (``math.fsum``) and published to one decimal, because the residents are modelled.
    """
    population = np.asarray(node_population, dtype=float)
    index = np.asarray(node_tambon).astype(int)
    if population.shape != index.shape or population.ndim != 1:
        raise ReplayExportError("node population and node tambon index must be one value per node")
    sets = {"reported_2024": reported_set, "knee_plan": knee_set}
    for label, set_id in sets.items():
        if set_id not in cut_codes or np.asarray(cut_codes[set_id]).shape != population.shape:
            raise ReplayExportError(f"cut codes of the {label} set ({set_id}) are missing or do not match the nodes")
    levels = [_level_index(float(stage), level_step_m) for stage in stages]
    rows = []
    for position, tambon in enumerate(tambons, start=1):
        inside = index == position
        residents = math.fsum(population[inside].tolist())
        figures: dict[str, tuple[float, dict[int, float]]] = {}
        for label, set_id in sets.items():
            codes = np.asarray(cut_codes[set_id]).astype(int)
            with_baseline = inside & (codes != NO_BASELINE_ACCESS)
            can_lose = with_baseline & (codes != NEVER_LOST)
            by_code = {int(code): math.fsum(population[can_lose & (codes == code)].tolist()) for code in np.unique(codes[can_lose])}
            figures[label] = (math.fsum(population[with_baseline].tolist()), by_code)
        for hour, (stage, level) in enumerate(zip(stages, levels)):
            row: dict[str, Any] = {"tambon_id": tambon["id"], "tambon_name_th": tambon.get("th", ""), "tambon_name_en": tambon.get("en", ""),
                                   "replay_hour": hour, "local_time": hour_local_time(hour, event_start),
                                   "modelled_stage_m": round(float(stage), 3), "residents": round(residents, 1)}
            for label, (baseline, by_code) in figures.items():
                lost = math.fsum(value for code, value in by_code.items() if code <= level)
                row[f"{label}_within_reach_before_flood"] = round(baseline, 1)
                row[f"{label}_lost_access"] = round(lost, 1)
            rows.append(row)
    return rows


_BASIS_TH_COLUMN = Column("capacity_basis_th", "ที่มาของค่าความจุ ภาษาไทย", "The same phrase in Thai")

_SITE_COLUMNS: tuple[Column, ...] = (
    Column("candidate_id", "รหัสสถานที่", "Candidate id in this revision"),
    Column("kind", "ประเภท", "school, worship, government or community"),
    Column("name", "ชื่อ", "Name in OpenStreetMap (blank when it has none)"),
    Column("lat", "ละติจูด", "Latitude, WGS 84"),
    Column("lon", "ลองจิจูด", "Longitude, WGS 84"),
)

PLAN_COLUMNS: tuple[Column, ...] = (
    Column("rank", "ลำดับ", "Position in the modelled coverage ranking: the plan of k sites is the first k rows"),
    *_SITE_COLUMNS,
    Column("osm_source", "ที่มาใน OSM", "OpenStreetMap element the candidate comes from"),
    Column("in_knee_plan", "อยู่ในแผนที่แสดง", "yes for the first k sites the replay shows by default"),
    Column("added_flooded_home_residents", "ผู้อยู่อาศัยในบ้านที่น้ำท่วมที่เพิ่มขึ้น",
           "Residents of homes that flood at the modelled peak whom this site adds within the walk"),
    Column("cumulative_flooded_home_residents", "ผู้อยู่อาศัยในบ้านที่น้ำท่วมสะสม", "Running total of those residents"),
    Column("cumulative_share", "สัดส่วนสะสม", "Running total as a share of all residents whose homes flood at the modelled peak"),
    Column("late_cumulative_share", "สัดส่วนสะสมเมื่ออพยพช้า", "The same share on the roads still passable at a 1.0 m stage"),
    Column("estimated_capacity", "ความจุโดยประมาณ", "Unverified estimate from the mapped building footprint (blank: unknown)"),
    Column("capacity_basis", "ที่มาของค่าความจุ", "How the estimate was made, or unknown"),
    _BASIS_TH_COLUMN,
    Column("in_robust_core", "อยู่ในแกนที่คงทน", "yes when the site is among the first k at every what-if level"),
)

CAPACITATED_COLUMNS: tuple[Column, ...] = (
    Column("rank", "ลำดับ", "Position in the capacity-aware ranking: the plan of k sites is the first k rows"),
    *_SITE_COLUMNS,
    Column("osm_source", "ที่มาใน OSM", "OpenStreetMap element the candidate comes from"),
    Column("estimated_capacity", "ความจุโดยประมาณ", "Unverified estimate from the mapped building footprint (blank: unknown)"),
    Column("capacity_basis", "ที่มาของค่าความจุ", "How the estimate was made, or unknown"),
    _BASIS_TH_COLUMN,
    Column("upper_capacity_basis", "ที่มาของความจุในขอบเขตบน", "estimate, kind_median or all_kinds_median: what the upper bound counts for this site"),
    Column("flooded_home_residents_within_reach", "ผู้อยู่อาศัยในบ้านที่น้ำท่วมในระยะเดิน", "Residents of flooded homes within the walk of the first k sites"),
    Column("lower_capacity", "ความจุ ขอบเขตล่าง", "Capacity counted in the lower bound: a site without a mapped footprint holds nobody (not a minimum)"),
    Column("lower_load", "จำนวนที่จัดให้ ขอบเขตล่าง", "Residents this site adds in the lower bound"),
    Column("lower_cumulative_fit", "จำนวนที่รองรับได้สะสม ขอบเขตล่าง", "Residents who fit in the first k sites, lower bound"),
    Column("lower_overflow", "จำนวนที่ไม่มีที่รองรับ ขอบเขตล่าง", "Demand minus the residents who fit, lower bound"),
    Column("upper_capacity", "ความจุ ขอบเขตบน",
           "Capacity counted in the upper bound: a site without a mapped footprint holds the median of its kind (not a maximum: a footprint estimate can be too low)"),
    Column("upper_load", "จำนวนที่จัดให้ ขอบเขตบน", "Residents this site adds in the upper bound"),
    Column("upper_cumulative_fit", "จำนวนที่รองรับได้สะสม ขอบเขตบน", "Residents who fit in the first k sites, upper bound"),
    Column("upper_overflow", "จำนวนที่ไม่มีที่รองรับ ขอบเขตบน", "Demand minus the residents who fit, upper bound"),
)

REPORTED_COLUMNS: tuple[Column, ...] = (
    Column("site_id", "รหัสสถานที่", "Id of the reported site in this revision"),
    Column("name_th", "ชื่อ", "Name in Thai, as reported"),
    Column("name_en", "ชื่อภาษาอังกฤษ", "Name in English"),
    Column("type", "ประเภท", "Kind of site"),
    Column("tambon_as_reported", "ตำบลตามรายงาน", "Subdistrict as the sources give it"),
    Column("lat", "ละติจูด", "Latitude, WGS 84 (blank: not located)"),
    Column("lon", "ลองจิจูด", "Longitude, WGS 84 (blank: not located)"),
    Column("location_method", "วิธีระบุตำแหน่ง", "How the point was found"),
    Column("location_confidence", "ความเชื่อมั่นของตำแหน่ง", "high, medium or low"),
    Column("role", "บทบาท", "shelter, or relief and command centre"),
    Column("first_use", "วันที่เริ่มใช้ตามรายงาน", "First reported use"),
    Column("first_use_th", "วันที่เริ่มใช้ตามรายงาน ภาษาไทย", "The same in Thai"),
    Column("counted_in_access_set", "นับในชุดการเข้าถึง", "yes when the reported 2024 access set counts the site"),
    Column("access_set_note", "เหตุผลที่นับหรือไม่นับ", "Why the site is, or is not, counted"),
    Column("access_set_note_th", "เหตุผลที่นับหรือไม่นับ ภาษาไทย", "The same reason in Thai"),
    Column("evidence_strength", "น้ำหนักของหลักฐาน", "official, multiple_media or single_media"),
    Column("source_urls", "ลิงก์แหล่งข้อมูล", "Public sources, separated by a space"),
    Column("modelled_in_model_area", "อยู่ในพื้นที่แบบจำลอง", "Model check: yes when the point lies inside the water model"),
    Column("modelled_floods_at_peak", "น้ำถึงสถานที่ที่ระดับสูงสุดตามแบบจำลอง", "Model check: yes when the modelled peak reaches the site"),
    Column("modelled_freeboard_m", "ระยะพ้นน้ำตามแบบจำลอง ม.", "Model check: height of the site above the modelled peak, metres (blank: high ground or unknown)"),
)

SHEET_PREFILLED: tuple[Column, ...] = (
    *_SITE_COLUMNS,
    Column("estimated_capacity", "ความจุโดยประมาณ", "Unverified estimate from the mapped building footprint (blank: unknown)"),
    Column("capacity_basis", "ที่มาของค่าความจุ", "How the estimate was made, or unknown"),
    _BASIS_TH_COLUMN,
)
SHEET_CHECKER: tuple[Column, ...] = (
    Column("usable_as_shelter", "ใช้เป็นที่พักพิงได้หรือไม่", "For the checker: yes or no"),
    Column("verified_capacity", "ความจุที่ตรวจสอบแล้ว", "For the checker: people the site can hold, a whole number"),
    Column("access_notes", "หมายเหตุการเข้าถึง", "For the checker: access by road, stairs, gates; no names of people, phone or ID numbers"),
    Column("checked_by_role", "บทบาทของผู้ตรวจสอบ", "For the checker: a role code, never a name"),
    Column("checked_on", "วันที่ตรวจสอบ", "For the checker: the date of the check, YYYY-MM-DD"),
)
SHEET_COLUMNS: tuple[Column, ...] = (*SHEET_PREFILLED, *SHEET_CHECKER)
"""The verification sheet's whitelist: eight prefilled columns and five empty ones for the checker."""

CHECKER_ROLES: Mapping[str, Mapping[str, str]] = {
    "ddpm_officer": {"en": "DDPM officer", "th": "เจ้าหน้าที่ ปภ.", "by": "a DDPM officer"},
    "local_government_officer": {"en": "tambon or municipality officer", "th": "เจ้าหน้าที่ อบต. หรือเทศบาล", "by": "a tambon or municipality officer"},
    "village_leader": {"en": "village head or kamnan", "th": "ผู้ใหญ่บ้านหรือกำนัน", "by": "a village head or kamnan"},
    "site_staff": {"en": "staff of the site", "th": "เจ้าหน้าที่ของสถานที่", "by": "staff of the site"},
    "project_team": {"en": "FloodGuard project team", "th": "ทีมโครงการ FloodGuard", "by": "the FloodGuard project team"},
    "other_local_contact": {"en": "other local contact", "th": "ผู้ประสานงานในพื้นที่อื่น ๆ", "by": "another local contact"},
}
"""Role codes a checker may give. A role, never a name: the import script refuses anything else. ``by`` is the wording
of the label "Checked by <role> on <date>"."""


def _capacity_basis(site: Mapping[str, Any], estimate_basis: str, unknown_basis: str) -> str:
    return unknown_basis if site.get("capacity_est") is None else estimate_basis


def capacity_basis_th(basis: str) -> str:
    """The Thai wording of a capacity-basis phrase. A phrase without one stops the export: prose cells are bilingual."""
    if basis not in CAPACITY_BASIS_TH:
        raise ReplayExportError(f"no Thai wording for the capacity basis {basis!r}")
    return CAPACITY_BASIS_TH[basis]


_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def first_use_th(value: str) -> str:
    """``first_use`` for the Thai companion column: a date stays as it is, ``<date> or earlier`` is translated."""
    if not value or _ISO_DAY.match(value):
        return value
    if value.endswith(" or earlier") and _ISO_DAY.match(value[: -len(" or earlier")]):
        return value[: -len(" or earlier")] + " หรือก่อนหน้า"
    raise ReplayExportError(f"no Thai wording for the first reported use {value!r}")


def access_set_note_th(site: Mapping[str, Any]) -> str:
    """The Thai rendering of a reported site's access-set note, as compiled with the site. A note without one stops the export."""
    note, thai = site.get("access_set_note") or "", site.get("access_set_note_th") or ""
    if note and not thai:
        raise ReplayExportError(f"reported site {site.get('id')}: access_set_note has no Thai rendering (access_set_note_th)")
    return thai


def _site_cells(site: Mapping[str, Any]) -> dict[str, Any]:
    return {"candidate_id": site["id"], "kind": site["kind"], "name": site.get("name") or "", "lat": site["lat"], "lon": site["lon"]}


def plan_rows(ctx: ExportContext) -> list[dict[str, Any]]:
    """The coverage ranking, one row per ranked site (rank 1..N)."""
    sites = {site["id"]: site for site in ctx.candidates}
    basis = ctx.capacitated["capacity_basis"]
    rows = []
    for rank, entry in enumerate(ctx.plan, start=1):
        site = sites[entry["candidate_id"]]
        rows.append({"rank": rank, **_site_cells(site), "osm_source": site.get("source") or "", "in_knee_plan": rank <= ctx.knee_k,
                     "added_flooded_home_residents": round(float(entry["marginal_demand"]), 1),
                     "cumulative_flooded_home_residents": round(float(entry["cumulative_demand"]), 1),
                     "cumulative_share": entry["cumulative_share"], "late_cumulative_share": entry.get("late_cumulative_share"),
                     "estimated_capacity": site.get("capacity_est"),
                     "capacity_basis": _capacity_basis(site, basis["estimate"], basis["unknown"]),
                     "capacity_basis_th": capacity_basis_th(_capacity_basis(site, basis["estimate"], basis["unknown"])),
                     "in_robust_core": site["id"] in set(ctx.robust_core)})
    return rows


def capacitated_rows(ctx: ExportContext) -> list[dict[str, Any]]:
    """The capacity-aware ranking, one row per ranked site, with both capacity bounds."""
    sites = {site["id"]: site for site in ctx.candidates}
    rows = []
    for rank, entry in enumerate(ctx.capacitated["plan"], start=1):
        site = sites[entry["candidate_id"]]
        row = {"rank": rank, **_site_cells(site), "osm_source": site.get("source") or "", "estimated_capacity": entry["capacity_est"],
               "capacity_basis": entry["capacity_basis"], "capacity_basis_th": capacity_basis_th(entry["capacity_basis"]),
               "upper_capacity_basis": entry["upper_capacity_basis"],
               "flooded_home_residents_within_reach": entry.get("within_reach")}
        for bound in ("lower", "upper"):
            row[f"{bound}_capacity"] = entry[bound]["capacity"]
            row[f"{bound}_load"] = entry[bound]["load"]
            row[f"{bound}_cumulative_fit"] = entry[bound]["served"]
            row[f"{bound}_overflow"] = entry[bound]["overflow"]
        rows.append(row)
    return rows


def reported_rows(ctx: ExportContext) -> list[dict[str, Any]]:
    """The sites reported in use in September 2024, with the model check beside the reported facts.

    Occupancy counts and capacities are left out on purpose: no listed capacity is published in this pack.
    """
    rows = []
    for site in ctx.reported:
        check = site.get("model_check") or {}
        located = site.get("lat") is not None and site.get("lon") is not None
        rows.append({
            "site_id": site["id"], "name_th": site.get("name_th") or "", "name_en": site.get("name_en") or "", "type": site.get("type") or "",
            "tambon_as_reported": site.get("tambon") or "", "lat": site.get("lat"), "lon": site.get("lon"),
            "location_method": site.get("location_method") or "", "location_confidence": site.get("location_confidence") or "",
            "role": site.get("role") or "", "first_use": site.get("first_use") or "", "first_use_th": first_use_th(site.get("first_use") or ""),
            "counted_in_access_set": bool(site.get("in_access_set")), "access_set_note": site.get("access_set_note") or "",
            "access_set_note_th": access_set_note_th(site),
            "evidence_strength": site.get("evidence_strength") or "",
            "source_urls": " ".join(source["url"] for source in site.get("sources") or [] if source.get("url")),
            "modelled_in_model_area": check.get("m") if located else None,
            "modelled_floods_at_peak": check.get("floods_at_modelled_peak") if located else None,
            "modelled_freeboard_m": check.get("freeboard_m") if located else None,
        })
    return rows


def sheet_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The candidates a checker is asked about: the eligible ones, in id order."""
    return sorted((site for site in candidates if site.get("eligible")), key=lambda site: site["id"])


def candidate_set_sha256(candidates: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint of the sheet's candidate list (id, kind and position), so a returned sheet can be matched to it.

    Candidate ids are renumbered when the OpenStreetMap extract changes; a check returned for another list must
    not be applied to this one.
    """
    lines = [f"{site['id']}|{site['kind']}|{float(site['lon']):.6f}|{float(site['lat']):.6f}" for site in sheet_candidates(candidates)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def sheet_rows(ctx: ExportContext) -> list[dict[str, Any]]:
    """The verification sheet: prefilled whitelisted columns, and the checker's columns left empty."""
    basis = ctx.capacitated["capacity_basis"]
    rows = []
    for site in sheet_candidates(ctx.candidates):
        row = {**_site_cells(site), "estimated_capacity": site.get("capacity_est"),
               "capacity_basis": _capacity_basis(site, basis["estimate"], basis["unknown"]),
               "capacity_basis_th": capacity_basis_th(_capacity_basis(site, basis["estimate"], basis["unknown"]))}
        row.update({column.key: None for column in SHEET_CHECKER})
        rows.append(row)
    return rows


SITE_FIELDS: tuple[Column, ...] = (
    Column("site_set", "ชุดสถานที่", "candidate (OpenStreetMap public building, modelled screening) or reported_2024 (reported in use in September 2024)"),
    Column("id", "รหัสสถานที่", "Candidate id or reported-site id in this revision"),
    Column("name", "ชื่อ", "Name (Thai where the source gives one)"),
    Column("name_en", "ชื่อภาษาอังกฤษ", "English name of a reported site"),
    Column("kind", "ประเภท", "Kind of site"),
    Column("osm_source", "ที่มาใน OSM", "OpenStreetMap element of a candidate"),
    Column("modelled_eligible", "เข้าเกณฑ์ตามแบบจำลอง", "Candidate keeps its freeboard at the modelled peak and has a road within reach"),
    Column("modelled_ineligible_reasons", "เหตุผลที่ไม่เข้าเกณฑ์", "Why a candidate is not eligible"),
    Column("coverage_rank", "ลำดับในการจัดอันดับความครอบคลุม", "Rank in the coverage ranking (null: not ranked)"),
    Column("in_knee_plan", "อยู่ในแผนที่แสดง", "Among the first k sites the replay shows by default"),
    Column("in_robust_core", "อยู่ในแกนที่คงทน", "Among the first k at every what-if level"),
    Column("capacity_rank", "ลำดับในการจัดอันดับแบบคิดความจุ", "Rank in the capacity-aware ranking (null: not ranked)"),
    Column("estimated_capacity", "ความจุโดยประมาณ", "Unverified footprint estimate (null: unknown)"),
    Column("capacity_basis", "ที่มาของค่าความจุ", "How the estimate was made, or unknown"),
    _BASIS_TH_COLUMN,
    Column("counted_in_access_set", "นับในชุดการเข้าถึง", "Reported site counted by the reported 2024 access set"),
    Column("location_confidence", "ความเชื่อมั่นของตำแหน่ง", "Reported site: high, medium or low"),
    Column("modelled_floods_at_peak", "น้ำถึงสถานที่ที่ระดับสูงสุดตามแบบจำลอง", "Model check: the modelled peak reaches the site"),
    Column("modelled_freeboard_m", "ระยะพ้นน้ำตามแบบจำลอง ม.", "Model check: height above the modelled peak, metres"),
)


def site_features(ctx: ExportContext) -> list[dict[str, Any]]:
    """GeoJSON point features: every shelter candidate, then every located reported site."""
    basis = ctx.capacitated["capacity_basis"]
    coverage_rank = {entry["candidate_id"]: rank for rank, entry in enumerate(ctx.plan, start=1)}
    capacity_rank = {entry["candidate_id"]: rank for rank, entry in enumerate(ctx.capacitated["plan"], start=1)}
    core = set(ctx.robust_core)
    features = []
    for site in sorted(ctx.candidates, key=lambda item: item["id"]):
        rank = coverage_rank.get(site["id"])
        floods = False if site.get("high_ground") else None if site.get("freeboard_m") is None else bool(site["freeboard_m"] < 0)
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [site["lon"], site["lat"]]}, "properties": {
            "site_set": "candidate", "id": site["id"], "name": site.get("name") or "", "name_en": None, "kind": site["kind"],
            "osm_source": site.get("source") or "", "modelled_eligible": bool(site.get("eligible")),
            "modelled_ineligible_reasons": ";".join(site.get("ineligible_reasons") or []),
            "coverage_rank": rank, "in_knee_plan": rank is not None and rank <= ctx.knee_k, "in_robust_core": site["id"] in core,
            "capacity_rank": capacity_rank.get(site["id"]), "estimated_capacity": site.get("capacity_est"),
            "capacity_basis": _capacity_basis(site, basis["estimate"], basis["unknown"]),
            "capacity_basis_th": capacity_basis_th(_capacity_basis(site, basis["estimate"], basis["unknown"])),
            "counted_in_access_set": None, "location_confidence": None,
            "modelled_floods_at_peak": floods, "modelled_freeboard_m": site.get("freeboard_m")}})
    for site in ctx.reported:
        if site.get("lat") is None or site.get("lon") is None:
            continue
        check = site.get("model_check") or {}
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [site["lon"], site["lat"]]}, "properties": {
            "site_set": "reported_2024", "id": site["id"], "name": site.get("name_th") or "", "name_en": site.get("name_en") or "",
            "kind": site.get("type") or "", "osm_source": None, "modelled_eligible": None, "modelled_ineligible_reasons": None,
            "coverage_rank": None, "in_knee_plan": None, "in_robust_core": None, "capacity_rank": None, "estimated_capacity": None,
            "capacity_basis": None, "capacity_basis_th": None, "counted_in_access_set": bool(site.get("in_access_set")),
            "location_confidence": site.get("location_confidence") or "",
            "modelled_floods_at_peak": check.get("floods_at_modelled_peak"), "modelled_freeboard_m": check.get("freeboard_m")}})
    return features


# --- Header ---------------------------------------------------------------------------------------------------


def input_set_sha256(inputs: Iterable[Mapping[str, Any]]) -> str:
    """One hash for the whole input receipt: SHA-256 of its sorted ``root:path:bytes:sha256`` lines."""
    lines = sorted(f"{row['root']}:{row['path']}:{row['bytes']}:{row['sha256']}" for row in inputs)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _direct_inputs(ctx: ExportContext, paths: Sequence[str]) -> str:
    found = {row["path"]: row for row in ctx.inputs}
    missing = [path for path in paths if path not in found]
    if missing:
        raise ReplayExportError(f"export inputs are not in the input receipt: {missing}")
    return "; ".join(f"{found[path]['root']}:{path}={found[path]['sha256']}" for path in paths)


def _source(ctx: ExportContext, source_id: str) -> Mapping[str, Any]:
    for source in ctx.sources:
        if source["id"] == source_id:
            return source
    raise ReplayExportError(f"unknown source id: {source_id}")


def _licence(source: Mapping[str, Any]) -> str:
    """A source's licence wording without a closing full stop, so it can sit inside a sentence."""
    return str(source["licence"]).rstrip(". ")


def licence_problems(name: str, source_ids: Sequence[str], sources: Sequence[Mapping[str, Any]]) -> list[str]:
    """Why ``source_ids`` may not feed one export file (empty when the lineage is clean).

    A file derives from OpenStreetMap (share-alike, ODbL), from facts matched to OpenStreetMap and from
    attribution-only sources. It may not also derive from a second share-alike licence (CC BY-SA), from a
    non-commercial one (CC BY-NC), from a source without a stated licence, or from product 4009.
    """
    known = {source["id"]: source for source in sources}
    problems = []
    if SHARE_ALIKE_SOURCE not in source_ids:
        problems.append(f"{name}: an export is OpenStreetMap-derived and must name the osm source")
    for source_id in source_ids:
        if source_id in FORBIDDEN_SOURCES or re.search(r"4009", source_id):
            problems.append(f"{name}: source {source_id} may not feed an export")
            continue
        source = known.get(source_id)
        if source is None:
            problems.append(f"{name}: unknown source {source_id}")
            continue
        licence = str(source.get("licence", ""))
        if re.search(r"BY-SA", licence, re.IGNORECASE):
            problems.append(f"{name}: {source_id} ({licence}) is a second share-alike lineage (CC BY-SA beside ODbL); it needs its own file")
        if re.search(r"(?<![A-Za-z])NC(?![A-Za-z])|non-?commercial", licence, re.IGNORECASE):
            problems.append(f"{name}: {source_id} ({licence}) is non-commercial and stays out of every export")
        if re.search(r"no licence stated", licence, re.IGNORECASE):
            problems.append(f"{name}: {source_id} has no stated licence and stays out of every export")
    return problems


def column_problems(name: str, keys: Iterable[str]) -> list[str]:
    """Columns an export may not carry: the legacy candidate columns, rain, product 4009, a score or an action class."""
    problems = []
    for key in keys:
        if key in LEGACY_ROAD_COLUMNS:
            problems.append(f"{name}: legacy column {key} comes from the superseded candidate lane")
        elif _FORBIDDEN_COLUMN.search(key):
            problems.append(f"{name}: column {key} is not allowed in an export")
    return problems


def header_fields(ctx: ExportContext, spec: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The provenance fields of one file, in order, as ``(key, value)``. The same list heads every format."""
    source_ids: Sequence[str] = ctx.licence_overrides.get(spec["name"], spec["sources"])
    problems = licence_problems(spec["name"], source_ids, ctx.sources)
    if problems:
        raise ReplayExportError("; ".join(problems))
    sources = [_source(ctx, source_id) for source_id in source_ids]
    reason, reason_th = confidence_reason(ctx.verification_status == "conducted")
    fields: list[tuple[str, str]] = [
        ("title", spec["title"]["en"]),
        ("title_th", spec["title"]["th"]),
        ("tier", EXPORT_TIER),
        ("tier_th", EXPORT_TIER_TH),
        ("operational_status", OPERATIONAL_STATUS),
        ("confidence_class", CONFIDENCE_CLASS),
        ("confidence_reason", reason),
        ("confidence_reason_th", reason_th),
        ("lanes", ", ".join(spec["lanes"])),
        ("source_timestamp", spec["source_timestamp"]),
        ("generated_at", ctx.generated_at),
        ("generated_by", ctx.generated_by),
        ("study", f"{ctx.study_id} {ctx.revision}"),
        ("accepted", ACCEPTED_NULL),
        ("licence", f"{EXPORT_LICENCE} ({EXPORT_LICENCE_URL}): OpenStreetMap-derived, attribution and share-alike"),
        ("licence_th", f"{EXPORT_LICENCE}: ดัดแปลงจาก OpenStreetMap ต้องแสดงที่มาและเผยแพร่งานดัดแปลงภายใต้สัญญาอนุญาตเดียวกัน"),
        ("attribution", "; ".join(str(source["attribution"]) for source in sources)),
        ("licence_inputs", "; ".join(f"{source['name']}: {_licence(source)}" for source in sources)),
        ("not_included", NOT_INCLUDED),
        ("not_included_th", NOT_INCLUDED_TH),
    ]
    for index, assumption in enumerate(spec["assumptions"], start=1):
        fields.append((f"assumption_{index}", assumption["en"]))
        fields.append((f"assumption_{index}_th", assumption["th"]))
    fields += [
        ("input_receipt", f"{ctx.receipt_path} lists every input file of the bake with its SHA-256 (also timeline.json input_sha256); "
                          f"input_set_sha256={input_set_sha256(ctx.inputs)}"),
        ("input_sha256", _direct_inputs(ctx, spec["inputs"])),
        ("git_commit", "null: a file cannot hold the hash of the commit that adds it; "
                       f"git log -1 --format=%H -- {ctx.repo_folder}/{spec['name']}"),
    ]
    for key, value in spec.get("extra", ()):
        fields.append((key, value))
    return fields


def _cell(value: Any) -> str:
    """One CSV cell: blank for None, yes/no for booleans, and no cell that a spreadsheet would run as a formula."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReplayExportError("a table cell must be a finite number")
        return repr(value)
    text = str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if text.startswith(_FORMULA_START) and not _NUMBER.match(text):
        return "'" + text
    return text


def csv_bytes(name: str, fields: Sequence[tuple[str, str]], columns: Sequence[Column], rows: Sequence[Mapping[str, Any]]) -> tuple[bytes, int]:
    """A CSV file as bytes (UTF-8 with BOM, LF line ends) and the number of provenance lines before the column header."""
    problems = column_problems(name, (column.key for column in columns))
    if problems:
        raise ReplayExportError("; ".join(problems))
    header_lines = len(fields) + 2
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["# floodguard_export", name])
    writer.writerow(["# header_lines", str(header_lines),
                     f"The first {header_lines} lines are provenance and the column header is on line {header_lines + 1}. A spreadsheet "
                     f"shows them as rows; in QGIS discard {header_lines} header lines, in pandas use skiprows={header_lines}.",
                     f"{header_lines} บรรทัดแรกเป็นข้อมูลกำกับ และหัวคอลัมน์อยู่ที่บรรทัด {header_lines + 1} โปรแกรมตารางคำนวณจะแสดงเป็นแถว "
                     f"ใน QGIS ให้ข้าม {header_lines} บรรทัดแรก"])
    for key, value in fields:
        writer.writerow([f"# {key}", value])
    writer.writerow([column.label for column in columns])
    keys = [column.key for column in columns]
    for row in rows:
        unknown = set(row) - set(keys)
        if unknown:
            raise ReplayExportError(f"{name}: a row carries columns outside the table: {sorted(unknown)}")
        writer.writerow([_cell(row.get(key)) for key in keys])
    return BOM + buffer.getvalue().encode("utf-8"), header_lines


def geojson_bytes(name: str, fields: Sequence[tuple[str, str]], columns: Sequence[Column], features: Sequence[Mapping[str, Any]]) -> bytes:
    """A GeoJSON FeatureCollection as bytes, with the provenance in a ``metadata`` member before the features."""
    keys = [column.key for column in columns]
    problems = column_problems(name, keys)
    for feature in features:
        if list(feature["properties"]) != keys:
            problems.append(f"{name}: a feature's properties differ from the declared fields")
            break
    if problems:
        raise ReplayExportError("; ".join(problems))
    metadata: dict[str, Any] = {"floodguard_export": name, **dict(fields),
                                "fields": [{"key": column.key, "th": column.th, "en": column.en} for column in columns]}
    head = json.dumps({"type": "FeatureCollection", "name": name.rsplit(".", 1)[0], "metadata": metadata}, ensure_ascii=False, indent=1)
    body = ",\n".join("  " + json.dumps(feature, ensure_ascii=False, separators=(",", ":")) for feature in features)
    return f"{head[:-2]},\n \"features\": [\n{body}\n ]\n}}\n".encode("utf-8")


def read_export_csv(data: bytes) -> tuple[dict[str, str], list[str], list[dict[str, str]]]:
    """Read an export CSV back: ``(provenance fields, column keys, rows keyed by column key)``.

    The provenance lines are those whose first cell starts with ``#``; the next line is the column header, whose
    cells are ``key (Thai label)``.
    """
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    fields: dict[str, str] = {}
    keys: list[str] | None = None
    rows: list[dict[str, str]] = []
    for cells in reader:
        if keys is None:
            match = _HEADER_KEY.match(cells[0]) if cells else None
            if match:
                fields[match.group(1)] = cells[1] if len(cells) > 1 else ""
                continue
            keys = [cell.split(" (", 1)[0].strip() for cell in cells]
            continue
        rows.append(dict(zip(keys, cells)))
    if keys is None:
        raise ReplayExportError("the file has no column header")
    return fields, keys, rows


# --- The pack -------------------------------------------------------------------------------------------------

_DEM = ("open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif",
        "open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E100_00_DEM.tif")
_OSM_PBF = "open_context/osm_geofabrik/thailand-latest.osm.pbf"
_ROADS = "outputs/mae_sai_road_risk.geojson"
_EDGES = "outputs/mae_sai_access_edges.csv"
_NODES = "outputs/mae_sai_population_nodes.csv"
_ADMIN = "outputs/mae_sai_admin_context.geojson"
_FACILITIES = "outputs/mae_sai_facilities.geojson"
_REPORTED = "outputs/mae_sai_reported_shelters_2024.json"

_A_WATER = {"en": "The water is a HAND terrain-model reconstruction driven by illustrative stage keyframes (no gauge record was used): modelled, not observed.",
            "th": "น้ำเป็นการจำลองจากแบบจำลองภูมิประเทศ HAND ด้วยจุดกำหนดระดับน้ำเพื่อการอธิบาย (ไม่ได้ใช้ข้อมูลจากสถานีวัดน้ำ) เป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้"}
_A_HOURS = {"en": "Hours are replay hours on an hourly grid: hour 0 is 9 Sep 2024 00:00 ICT (UTC+7) and hour 263 is 19 Sep 2024 23:00; the assumed stage is sampled at the start of each hour.",
            "th": "ชั่วโมงคือชั่วโมงของการย้อนดูแบบรายชั่วโมง ชั่วโมง 0 คือ 9 ก.ย. 2567 (2024) 00:00 น. เวลาประเทศไทย (UTC+7) และชั่วโมง 263 คือ 19 ก.ย. 2567 (2024) 23:00 น. ใช้ระดับน้ำสมมุติ ณ ต้นชั่วโมง"}
_A_CANDIDATES = {"en": "The sites are candidates to verify on the ground, not a list of sites to open. They are OpenStreetMap public buildings and grounds (schools, places of worship, government offices, community centres).",
                 "th": "สถานที่เหล่านี้เป็นสถานที่ที่ควรตรวจสอบในพื้นที่ ไม่ใช่รายชื่อสถานที่ที่ต้องเปิด เป็นอาคารและพื้นที่สาธารณะใน OpenStreetMap (โรงเรียน ศาสนสถาน หน่วยงานราชการ ศูนย์ชุมชน)"}
_A_CAPACITY = {"en": "Capacity is an unverified estimate from mapped building footprints (footprint x 0.5 usable share / 3.5 m2 per person, Sphere) and is unknown for most candidates. No listed capacity from a shelter register is used or published here.",
               "th": "ความจุเป็นค่าประมาณที่ยังไม่ได้ตรวจสอบ คำนวณจากขอบเขตอาคารในแผนที่ (พื้นที่อาคาร x สัดส่วนใช้สอย 0.5 / 3.5 ตร.ม. ต่อคน ตามมาตรฐาน Sphere) และไม่ทราบค่าสำหรับสถานที่ส่วนใหญ่ ไม่มีการใช้หรือเผยแพร่ความจุจากทะเบียนที่พักพิงใด ๆ ในไฟล์นี้"}


_A_BRIDGES = {"en": "Bridge decks are not modelled. A row with bridge_flag = yes reflects the ground at the bridge's approaches and beside it, so a raised deck can stay passable while the table shows the way impassable: read the hours of a bridge row as unknown.",
              "th": "ไม่ได้จำลองพื้นสะพาน แถวที่ bridge_flag = yes สะท้อนระดับพื้นดินบริเวณคอสะพานและข้างสะพาน พื้นสะพานที่ยกสูงจึงอาจยังสัญจรได้แม้ตารางระบุว่าสัญจรไม่ได้ ให้ถือว่าชั่วโมงของแถวที่เป็นสะพานเป็นค่าที่ไม่ทราบ"}
_A_BOUNDS = {"en": "Neither bound is a limit on who fits. Both count a site with a mapped footprint at its estimate, which is too low where buildings are unmapped, so more residents may fit than the upper bound gives; and a site may turn out unusable, so fewer may fit than the lower bound gives.",
             "th": "ทั้งสองขอบเขตไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้ ทั้งสองขอบเขตนับสถานที่ที่มีขอบเขตอาคารในแผนที่ตามค่าประมาณ ซึ่งต่ำกว่าจริงในบริเวณที่อาคารยังไม่ถูกทำแผนที่ จึงอาจรองรับได้มากกว่าขอบเขตบน และสถานที่อาจใช้ไม่ได้จริง จึงอาจรองรับได้น้อยกว่าขอบเขตล่าง"}
_A_CHECK_NOT_USED = {"en": "A local check of some candidates has been returned for this revision (reported by role, not an official register). This file does not use it: a site reported not usable is still listed and ranked, and a reported capacity does not replace the footprint estimate. The checked rows are on the replay page.",
                     "th": "มีผลการตรวจสอบสถานที่บางแห่งในพื้นที่ส่งกลับมาแล้วสำหรับข้อมูลรุ่นนี้ (รายงานตามบทบาท ไม่ใช่ทะเบียนทางการ) ไฟล์นี้ไม่ได้ใช้ผลดังกล่าว สถานที่ที่รายงานว่าใช้ไม่ได้ยังคงอยู่ในรายการและการจัดอันดับ และความจุที่รายงานไม่ได้แทนค่าประมาณจากขอบเขตอาคาร แถวที่ตรวจสอบแล้วแสดงอยู่ในหน้าการย้อนดู"}


def _specs(ctx: ExportContext) -> dict[str, dict[str, Any]]:
    """Title, lanes, lineage, source timestamp, assumptions and direct inputs of every file of the pack."""
    osm = f"OpenStreetMap extract {ctx.osm_extract_date}"
    model = "illustrative stage keyframes for 2024-09-09/2024-09-19 ICT on the Copernicus DEM (2011-2015 acquisitions)"
    peak = "reconstructed peak 2024-09-12 ICT"
    classes = ", ".join(ctx.road_classes)
    walk_km = ctx.walk_limit_m / 1000
    if ctx.verification_status not in ("not_conducted", "conducted"):
        raise ReplayExportError(f"unknown verification status: {ctx.verification_status}")
    conducted = ctx.verification_status == "conducted"
    not_used = (_A_CHECK_NOT_USED,) if conducted else ()
    sheet_title = {"en": "Shelter-candidate verification sheet: a blank checklist for a local checker" + ("" if conducted else " (no check has been conducted)"),
                   "th": "แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง: รายการตรวจที่ยังว่างสำหรับผู้ตรวจสอบในพื้นที่" + ("" if conducted else " (ยังไม่มีการตรวจสอบ)")}
    sheet_state = ({"en": "The last five columns are for a local checker and are empty in this blank copy. A check has been returned for this revision: its rows are in the replay manifest (shelters.verification), not in this file.",
                    "th": "ห้าคอลัมน์สุดท้ายเว้นว่างไว้สำหรับผู้ตรวจสอบในพื้นที่ในสำเนาเปล่านี้ มีผลการตรวจสอบส่งกลับมาแล้วสำหรับข้อมูลรุ่นนี้ โดยแถวที่ตรวจสอบอยู่ในไฟล์กำกับของการย้อนดู (shelters.verification) ไม่ได้อยู่ในไฟล์นี้"}
                   if conducted else
                   {"en": "The last five columns are for a local checker and are empty: no check has been conducted for this revision, and no result is implied.",
                    "th": "ห้าคอลัมน์สุดท้ายเว้นว่างไว้สำหรับผู้ตรวจสอบในพื้นที่ ยังไม่มีการตรวจสอบสำหรับข้อมูลรุ่นนี้ และไม่มีผลใดบ่งบอกไว้ล่วงหน้า"})
    screening = {"en": f"A candidate is eligible when it keeps {ctx.freeboard_m} m of freeboard at the modelled peak ({ctx.peak_stage_m} m stage) and a road node lies within {ctx.snap_max_m:.0f} m.",
                 "th": f"สถานที่เข้าเกณฑ์เมื่อยังสูงกว่าระดับน้ำสูงสุดตามแบบจำลอง (ระดับ {ctx.peak_stage_m} ม.) อย่างน้อย {ctx.freeboard_m} ม. และมีจุดถนนภายในระยะ {ctx.snap_max_m:.0f} ม."}
    return {
        "roads": {
            "name": "modelled_road_inundation_by_hour.csv",
            "title": {"en": "Modelled road inundation by hour, one row per OpenStreetMap way (modelled, not observed)",
                      "th": "ถนนที่น้ำท่วมตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อหนึ่งเส้นทางใน OpenStreetMap (ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้)"},
            "lanes": ("SCN",), "sources": ("osm", "copernicus-dem", "cod-ab"),
            "source_timestamp": f"{osm} (roads); {model}",
            "inputs": (_ROADS, *_DEM),
            "assumptions": (
                _A_WATER, _A_HOURS,
                {"en": f"One row per OpenStreetMap way of the classes the replay models ({classes}); service roads and tracks are not modelled and not listed.",
                 "th": f"หนึ่งแถวต่อหนึ่งเส้นทางใน OpenStreetMap เฉพาะประเภทถนนที่การย้อนดูจำลอง ({classes}) ถนนบริการและทางลำลองไม่ได้จำลองและไม่อยู่ในตาราง"},
                {"en": f"A way is impassable when the modelled depth reaches {ctx.impassable_depth_m} m at any 10 m sample along it; river-channel samples on bridges are ignored. The passable-again hour is the first hour after the last impassable hour.",
                 "th": f"เส้นทางสัญจรไม่ได้เมื่อความลึกตามแบบจำลองถึง {ctx.impassable_depth_m} ม. ที่จุดตัวอย่างใดก็ตามซึ่งห่างกันทุก 10 ม. ไม่นับจุดตัวอย่างในร่องน้ำใต้สะพาน ชั่วโมงที่กลับมาสัญจรได้คือชั่วโมงแรกหลังชั่วโมงสุดท้ายที่สัญจรไม่ได้"},
                _A_BRIDGES,
                {"en": "Not an observed closure record: no closure, reopening or traffic report was used. Flow velocity, debris, mud and damage are not modelled, so a real road can stay shut after the water falls.",
                 "th": "ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง ไม่ได้ใช้รายงานการปิดถนน การเปิดถนน หรือการจราจร ไม่ได้จำลองความเร็วกระแสน้ำ เศษวัสดุ โคลน และความเสียหาย ถนนจริงจึงอาจยังใช้ไม่ได้หลังน้ำลด"},
                {"en": "The candidate columns of the source road file (an earlier Sentinel-1 change heuristic, now superseded) are not carried.",
                 "th": "ไม่ได้นำคอลัมน์ความเสี่ยงเบื้องต้นของไฟล์ถนนต้นทาง (วิธีประมาณจากการเปลี่ยนแปลงของ Sentinel-1 รุ่นก่อน ซึ่งเลิกใช้แล้ว) มาใส่ในตารางนี้"},
            ),
        },
        "access": {
            "name": "modelled_access_loss_by_hour.csv",
            "title": {"en": "Modelled loss of walking access to a shelter by hour, one row per subdistrict and replay hour",
                      "th": "การสูญเสียการเข้าถึงที่พักพิงด้วยการเดินตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อตำบลและชั่วโมงของการย้อนดู"},
            "lanes": ("SCN",), "sources": ("osm", "worldpop", "cod-ab", "copernicus-dem", "reported-shelters"),
            "source_timestamp": f"{osm} (roads and sites); WorldPop 2020; reported shelters compiled {ctx.reported_compiled}; {model}",
            "inputs": (_EDGES, _NODES, _ADMIN, _REPORTED, _OSM_PBF, _FACILITIES, *_DEM),
            "assumptions": (
                _A_WATER, _A_HOURS,
                {"en": "Residents are WorldPop 2020 modelled residents at road nodes, not the 2024 population, tourists or traders.",
                 "th": "ผู้อยู่อาศัยคือประชากรตามแบบจำลอง WorldPop 2020 ที่จุดถนน ไม่ใช่ประชากรปี 2567 (2024) นักท่องเที่ยว หรือผู้ค้า"},
                {"en": f"A resident has access when a dry shelter of the set is within a {walk_km:g} km walk on roads that are still passable. 'Within reach before the flood' is the set's own baseline; 'lost access' counts residents of that baseline who no longer have it at that hour.",
                 "th": f"ผู้อยู่อาศัยเข้าถึงได้เมื่อมีที่พักพิงที่ไม่ถูกน้ำท่วมของชุดนั้นภายในระยะเดิน {walk_km:g} กม. บนถนนที่ยังสัญจรได้ 'เข้าถึงได้ก่อนน้ำท่วม' คือฐานของชุดนั้นเอง ส่วน 'สูญเสียการเข้าถึง' นับผู้อยู่อาศัยในฐานนั้นที่ไม่มีที่พักพิงในระยะเดินแล้ว ณ ชั่วโมงนั้น"},
                {"en": f"Two shelter sets are given side by side: the sites reported in use in September 2024 and the first {ctx.knee_k} sites of the modelled coverage ranking. Each has its own baseline and the figures do not grade either set.",
                 "th": f"แสดงที่พักพิงสองชุดเคียงกัน คือสถานที่ที่มีรายงานว่าใช้ในเดือนกันยายน 2567 (2024) และ {ctx.knee_k} แห่งแรกของการจัดอันดับความครอบคลุมตามแบบจำลอง แต่ละชุดมีฐานของตัวเอง ตัวเลขไม่ได้ตัดสินว่าชุดใดเหนือกว่า"},
                {"en": "Every shelter is assumed usable for the whole replay unless the modelled water reaches it; opening times, capacity and vehicles are not modelled in this table.",
                 "th": "สมมุติว่าที่พักพิงทุกแห่งใช้ได้ตลอดช่วงการย้อนดู เว้นแต่น้ำตามแบบจำลองจะถึงสถานที่นั้น ตารางนี้ไม่ได้จำลองเวลาเปิด ความจุ และการใช้ยานพาหนะ"},
            ),
            "extra": (("knee_k", str(ctx.knee_k)),),
        },
        "plan": {
            "name": "shelter_plan_k.csv",
            # The page keeps the symbol k for the plan size out of its Sources panel, so the title says it in words.
            "title": {"en": "Modelled shelter coverage ranking, sites 1 to N: a plan of any size is its first rows (candidates to verify)",
                      "th": "การจัดอันดับความครอบคลุมของที่พักพิงตามแบบจำลอง ลำดับ 1 ถึง N แผนขนาดใดก็ตามคือแถวแรกตามจำนวนนั้น (สถานที่ที่ควรตรวจสอบ)"},
            "lanes": ("SCN",), "sources": ("osm", "worldpop", "copernicus-dem"),
            "source_timestamp": f"{osm} (sites, building footprints and roads); WorldPop 2020; {peak}",
            "inputs": (_OSM_PBF, _FACILITIES, _EDGES, _NODES, *_DEM),
            "assumptions": (
                _A_WATER, _A_CANDIDATES, screening,
                {"en": f"The ranking is greedy maximal coverage of residents whose homes flood at the modelled peak, within a {walk_km:g} km walk on normal roads before the water rises. A rank is the order in which a site joins, not a grade of the site.",
                 "th": f"การจัดอันดับเลือกทีละแห่งให้ครอบคลุมผู้อยู่อาศัยในบ้านที่น้ำท่วม ณ ระดับสูงสุดตามแบบจำลองให้มากที่สุด ภายในระยะเดิน {walk_km:g} กม. บนถนนสภาพปกติก่อนน้ำขึ้น ลำดับคือลำดับที่สถานที่เข้าสู่แผน ไม่ใช่การให้คะแนนสถานที่"},
                _A_CAPACITY,
                {"en": "The robust core is the set of sites among the first k at every what-if level (2.5 m, 3.5 m and 4.0 m): levels around an illustrative peak, not return periods.",
                 "th": "แกนที่คงทนคือสถานที่ที่อยู่ใน k แห่งแรกที่ทุกระดับสมมุติ (2.5 ม. 3.5 ม. และ 4.0 ม.) ซึ่งเป็นระดับรอบค่าสูงสุดเพื่อการอธิบาย ไม่ใช่คาบการเกิดซ้ำ"},
                *not_used,
            ),
            "extra": (("knee_k", str(ctx.knee_k)),),
        },
        "capacitated": {
            "name": "shelter_plan_capacitated.csv",
            "title": {"en": "Capacity-aware shelter ranking under two capacity bounds: who fits (candidates to verify)",
                      "th": "การจัดอันดับที่พักพิงแบบคิดความจุภายใต้ขอบเขตล่างและขอบเขตบน: รองรับได้กี่คน (สถานที่ที่ควรตรวจสอบ)"},
            "lanes": ("SCN",), "sources": ("osm", "worldpop", "copernicus-dem"),
            "source_timestamp": f"{osm} (sites, building footprints and roads); WorldPop 2020; {peak}",
            "inputs": (_OSM_PBF, _FACILITIES, _EDGES, _NODES, *_DEM),
            "assumptions": (
                _A_WATER, _A_CANDIDATES, _A_CAPACITY,
                {"en": f"Demand is every resident of a home that floods at the modelled peak ({ctx.capacitated['demand_people']:,} residents), an upper bound: many people stay with relatives or on an upper floor.",
                 "th": f"ความต้องการคือผู้อยู่อาศัยทุกคนในบ้านที่น้ำท่วม ณ ระดับสูงสุดตามแบบจำลอง ({ctx.capacitated['demand_people']:,} คน) ซึ่งเป็นค่าสูงสุดที่เป็นไปได้ เพราะหลายคนไปอาศัยกับญาติหรืออยู่ชั้นบน"},
                {"en": "Two bounds: an unknown capacity counts as 0 (lower) or as the median estimate of its site kind (upper). A load is the number of residents a site adds when it joins; overflow is demand minus the residents who fit.",
                 "th": "มีสองขอบเขต ความจุที่ไม่ทราบนับเป็น 0 (ขอบเขตล่าง) หรือใช้ค่ามัธยฐานของสถานที่ประเภทเดียวกัน (ขอบเขตบน) จำนวนที่จัดให้คือผู้อยู่อาศัยที่เพิ่มขึ้นเมื่อสถานที่นั้นเข้าสู่การจัดอันดับ ส่วนจำนวนที่ไม่มีที่รองรับคือความต้องการลบด้วยจำนวนที่รองรับได้"},
                _A_BOUNDS,
                {"en": "Everyone is assumed to walk before the water rises and to accept any site within the limit; households are not kept together.",
                 "th": "สมมุติว่าทุกคนเดินเท้าก่อนน้ำขึ้นและยอมไปสถานที่ใดก็ได้ภายในระยะที่กำหนด ไม่ได้จัดให้ครัวเรือนอยู่ด้วยกัน"},
                *not_used,
            ),
        },
        "reported": {
            "name": "shelter_plan_reported_2024.csv",
            "title": {"en": "Shelters reported in use in Mae Sai in September 2024, with a model check of each located site (not an official register)",
                      "th": "ที่พักพิงที่มีรายงานว่าใช้ในแม่สายเดือนกันยายน 2567 (2024) พร้อมผลเทียบกับแบบจำลองของสถานที่ที่ระบุตำแหน่งได้ (ไม่ใช่ทะเบียนทางการ)"},
            "lanes": ("REP", "SCN"), "sources": ("osm", "reported-shelters", "copernicus-dem"),
            "source_timestamp": f"reports dated 2024-09-11 to 2024-10-11, compiled {ctx.reported_compiled}; {osm} (locations); {peak} (model check)",
            "inputs": (_REPORTED, _EDGES, *_DEM),
            "assumptions": (
                {"en": "Reported use compiled by the FloodGuard team from public reporting; not an official register and not independently verified in this study.",
                 "th": "การใช้งานตามรายงานที่ทีม FloodGuard รวบรวมจากแหล่งข้อมูลสาธารณะ ไม่ใช่ทะเบียนทางการ และยังไม่ได้ตรวจสอบอย่างอิสระในการศึกษานี้"},
                {"en": "Coordinates are OpenStreetMap matches where possible; low-confidence locations are approximate, and a site without coordinates could not be located.",
                 "th": "พิกัดจับคู่กับ OpenStreetMap เท่าที่ทำได้ ตำแหน่งที่มีความเชื่อมั่นต่ำเป็นค่าประมาณ และสถานที่ที่ไม่มีพิกัดคือสถานที่ที่ระบุตำแหน่งไม่ได้"},
                {"en": "Columns starting with modelled_ are a T1 scenario (model) check of the site against the reconstructed peak, not an observation of whether the site flooded.",
                 "th": "คอลัมน์ที่ขึ้นต้นด้วย modelled_ เป็นผลเทียบสถานที่กับระดับน้ำสูงสุดที่จำลองขึ้น (สถานการณ์จำลองระดับ T1) ไม่ใช่การสังเกตว่าสถานที่นั้นถูกน้ำท่วมจริงหรือไม่"},
                {"en": "Occupancy counts and capacities are left out of this table; the public reports that give them are linked in source_urls.",
                 "th": "ตารางนี้ไม่มีจำนวนผู้เข้าพักและความจุ รายงานสาธารณะที่ระบุตัวเลขเหล่านั้นอยู่ในลิงก์ของคอลัมน์ source_urls"},
                _A_WATER,
            ),
        },
        "sites": {
            "name": "shelter_sites.geojson",
            "title": {"en": "Shelter sites as points: every modelled candidate and every located site reported in use in September 2024",
                      "th": "ตำแหน่งที่พักพิงแบบจุด: สถานที่ที่เป็นไปได้ทุกแห่งตามแบบจำลอง และสถานที่ที่มีรายงานว่าใช้ในเดือนกันยายน 2567 (2024) ที่ระบุตำแหน่งได้"},
            "lanes": ("SCN", "REP"), "sources": ("osm", "worldpop", "copernicus-dem", "reported-shelters"),
            "source_timestamp": f"{osm} (sites and roads); WorldPop 2020; reported shelters compiled {ctx.reported_compiled}; {peak}",
            "inputs": (_OSM_PBF, _FACILITIES, _REPORTED, _EDGES, _NODES, *_DEM),
            "assumptions": (
                _A_WATER, _A_CANDIDATES, screening, _A_CAPACITY,
                {"en": "site_set tells the lane of a point: candidate is a modelled screening of an OpenStreetMap building; reported_2024 is reported use from public sources, not an official register.",
                 "th": "site_set บอกประเภทของจุด: candidate คือการคัดกรองอาคารใน OpenStreetMap ด้วยแบบจำลอง ส่วน reported_2024 คือการใช้งานตามรายงานจากแหล่งข้อมูลสาธารณะ ไม่ใช่ทะเบียนทางการ"},
                *not_used,
            ),
            "extra": (("knee_k", str(ctx.knee_k)), ("crs", "WGS 84 (EPSG:4326), longitude then latitude")),
        },
        "sheet": {
            "name": "shelter_candidate_verification_sheet.csv",
            "title": sheet_title,
            "lanes": ("SCN",), "sources": ("osm", "copernicus-dem"),
            "source_timestamp": f"{osm} (sites and building footprints); {peak}",
            "inputs": (_OSM_PBF, _FACILITIES, _EDGES, *_DEM),
            "assumptions": (
                sheet_state,
                {"en": f"A returned check is labelled '{VERIFICATION_LABEL}'.",
                 "th": f"ผลที่ส่งกลับมาจะระบุว่า '{VERIFICATION_LABEL_TH}'"},
                {"en": "Do not add names of people, phone numbers or ID numbers, and do not add columns. Give a role code, never a name; the import script refuses a file that carries personal data.",
                 "th": "โปรดอย่าใส่ชื่อบุคคล หมายเลขโทรศัพท์ หรือเลขประจำตัว และอย่าเพิ่มคอลัมน์ ให้ระบุรหัสบทบาท ไม่ใช่ชื่อ โปรแกรมนำเข้าจะปฏิเสธไฟล์ที่มีข้อมูลส่วนบุคคล"},
                {"en": "Keep the lines that start with # and the first eight columns exactly as they are, and fill in only the last five. They tie each answer to its site: candidate ids are renumbered when the map data changes, so a file without them cannot be matched and is refused.",
                 "th": "โปรดคงบรรทัดที่ขึ้นต้นด้วย # และแปดคอลัมน์แรกไว้ตามเดิมทุกประการ และกรอกเฉพาะห้าคอลัมน์สุดท้าย ข้อมูลส่วนนี้ผูกคำตอบแต่ละแถวกับสถานที่ รหัสสถานที่จะเปลี่ยนเมื่อข้อมูลแผนที่เปลี่ยน ไฟล์ที่ไม่มีข้อมูลส่วนนี้จึงจับคู่กับสถานที่ไม่ได้และจะถูกปฏิเสธ"},
                {"en": "Access notes are for the project team only: they are never published and never kept in the project's files; only the fact that a note was given is recorded.",
                 "th": "หมายเหตุการเข้าถึงใช้ภายในทีมโครงการเท่านั้น จะไม่ถูกเผยแพร่และไม่ถูกเก็บไว้ในไฟล์ของโครงการ บันทึกไว้เพียงว่ามีการให้หมายเหตุหรือไม่"},
                {"en": "usable_as_shelter: yes or no. verified_capacity: a whole number of people. checked_on: the date of the check as YYYY-MM-DD. checked_by_role: one of " + ", ".join(CHECKER_ROLES) + ".",
                 "th": "usable_as_shelter: yes หรือ no · verified_capacity: จำนวนคนเป็นจำนวนเต็ม · checked_on: วันที่ตรวจสอบในรูปแบบ YYYY-MM-DD (ปี ค.ศ.) · checked_by_role: " + " · ".join(f"{code} = {label['th']}" for code, label in CHECKER_ROLES.items())},
                _A_CANDIDATES, screening, _A_CAPACITY,
            ),
            "extra": (("verification_status", ctx.verification_status), ("verification_label", VERIFICATION_LABEL),
                      ("verification_label_th", VERIFICATION_LABEL_TH), ("candidate_set_sha256", candidate_set_sha256(ctx.candidates))),
        },
    }


README_NAME = "README_licences.txt"
README_TITLE = {"en": "Licences, attributions and reading notes of the export pack (read this first)",
                "th": "สัญญาอนุญาต การแสดงที่มา และข้อควรรู้ในการอ่านชุดไฟล์ส่งออก (โปรดอ่านก่อน)"}


def readme_bytes(ctx: ExportContext, files: Sequence[ExportFile], specs: Mapping[str, Mapping[str, Any]]) -> bytes:
    """``README_licences.txt``: what the pack is, the licence and attribution of every file, and how to open it."""
    used = list(dict.fromkeys(source_id for file in files for source_id in file.sources))
    fields = header_fields(ctx, {
        "name": README_NAME,
        "title": README_TITLE,
        "lanes": tuple(dict.fromkeys(lane for file in files for lane in file.lanes)),
        "sources": tuple(used),
        "source_timestamp": f"OpenStreetMap extract {ctx.osm_extract_date}; WorldPop 2020; reported shelters compiled {ctx.reported_compiled}; "
                            "illustrative stage keyframes for 2024-09-09/2024-09-19 ICT",
        "inputs": (),
        "assumptions": (_A_WATER, _A_HOURS),
    })
    fields = [(key, value) for key, value in fields if key != "input_sha256"]
    conducted = ctx.verification_status == "conducted"
    sheet_state_en = ("A check has been returned for this revision and is listed on the replay page; this file stays blank." if conducted
                      else "No check has been conducted for this revision.")
    sheet_state_th = ("มีผลการตรวจสอบส่งกลับมาแล้วสำหรับข้อมูลรุ่นนี้และแสดงอยู่ในหน้าการย้อนดู ไฟล์นี้ยังคงเป็นแบบเปล่า" if conducted
                      else "ยังไม่มีการตรวจสอบสำหรับข้อมูลรุ่นนี้")
    ground_en = ("Confidence is low. A local check of some shelter candidates was returned (reported by role, not an official register);\n"
                 "the tables do not use it, and nothing else was checked on the ground." if conducted
                 else "Confidence is low and nothing was checked on the ground.")
    ground_th = ("ความเชื่อมั่นอยู่ในระดับต่ำ มีผลการตรวจสอบสถานที่บางแห่งในพื้นที่ส่งกลับมาแล้ว (รายงานตามบทบาท ไม่ใช่ทะเบียนทางการ)\n"
                 "แต่ตารางเหล่านี้ไม่ได้ใช้ผลดังกล่าว และยังไม่มีการตรวจสอบสิ่งอื่นใดในพื้นที่" if conducted
                 else "ความเชื่อมั่นอยู่ในระดับต่ำ และยังไม่มีการตรวจสอบในพื้นที่")
    lines = [f"# floodguard_export: {README_NAME}"] + [f"# {key}: {value}" for key, value in fields] + [""]
    lines += [
        "FLOODGUARD MAE SAI SEPTEMBER 2024 REPLAY: EXPORT PACK",
        "ชุดไฟล์ส่งออกของการย้อนดูน้ำท่วมแม่สาย กันยายน 2567 (2024) โดย FloodGuard",
        "",
        "1. WHAT THIS IS / ไฟล์ชุดนี้คืออะไร",
        "",
        "Tables and one map layer written from a model replay of the September 2024 flood in Mae Sai District. They are for",
        "preparedness planning and exercises. Every table is modelled, not observed: it is not a forecast, not an observed",
        "closure record and not an official warning, and it must not be used for emergency response or evacuation orders.",
        *ground_en.split("\n"),
        "",
        "ตารางและชั้นข้อมูลแผนที่หนึ่งชั้นที่เขียนจากการย้อนดูด้วยแบบจำลองของเหตุการณ์น้ำท่วมอำเภอแม่สายเดือนกันยายน 2567 (2024)",
        "ใช้สำหรับการวางแผนเตรียมความพร้อมและการฝึกซ้อม ทุกตารางเป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้ ไม่ใช่การพยากรณ์",
        "ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ ห้ามใช้ในการตอบสนองเหตุฉุกเฉินหรือการสั่งอพยพ",
        *ground_th.split("\n"),
        "",
        "Bridges: the deck of a bridge is not modelled. In the road table a row with bridge_flag = yes reflects the ground at the",
        "bridge's approaches, so read its hours as unknown. Capacity bounds: neither the lower nor the upper bound is a limit on",
        "who fits; a footprint estimate can be too low where buildings are unmapped.",
        "",
        "สะพาน: ไม่ได้จำลองพื้นสะพาน ในตารางถนน แถวที่ bridge_flag = yes สะท้อนระดับพื้นดินบริเวณคอสะพาน ให้ถือว่าชั่วโมงของแถวนั้นเป็นค่าที่ไม่ทราบ",
        "ขอบเขตความจุ: ทั้งขอบเขตล่างและขอบเขตบนไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้ ค่าประมาณจากขอบเขตอาคารอาจต่ำกว่าจริงในบริเวณที่อาคารยังไม่ถูกทำแผนที่",
        "",
        "2. FILES / รายการไฟล์",
        "",
    ]
    for file in files:
        spec = next(item for item in specs.values() if item["name"] == file.name)
        size = f"{len(file.data):,} bytes"
        rows = "" if file.rows is None else f"; {file.rows:,} {'features' if file.header_lines is None else 'rows'}"
        skip = "" if file.header_lines is None else f"; {file.header_lines} provenance lines before the column header"
        lines += [
            file.name,
            f"  {spec['title']['en']}",
            f"  {spec['title']['th']}",
            f"  {size}{rows}{skip}; SHA-256 {file.sha256}",
            f"  Lanes: {', '.join(file.lanes)}. Licence: {EXPORT_LICENCE}. Derived from: "
            + "; ".join(f"{_source(ctx, source_id)['name']} ({_licence(_source(ctx, source_id))})" for source_id in file.sources) + ".",
            "",
        ]
    lines += [
        "3. LICENCE AND ATTRIBUTION / สัญญาอนุญาตและการแสดงที่มา",
        "",
        "Every file in this folder is derived from the OpenStreetMap database and is made available under the Open Database License",
        f"(ODbL) 1.0, {EXPORT_LICENCE_URL}",
        "You may copy, share and adapt the files if you keep the attributions below and offer any adapted database under the same",
        "licence. Each file has one licence lineage: OpenStreetMap (share-alike) plus the attribution-only inputs listed for it.",
        "",
        "ทุกไฟล์ในโฟลเดอร์นี้ดัดแปลงจากฐานข้อมูล OpenStreetMap และเผยแพร่ภายใต้สัญญาอนุญาต Open Database License (ODbL) 1.0",
        "ท่านคัดลอก เผยแพร่ และดัดแปลงไฟล์ได้ หากคงข้อความแสดงที่มาด้านล่างไว้ และเผยแพร่ฐานข้อมูลที่ดัดแปลงภายใต้สัญญาอนุญาตเดียวกัน",
        "แต่ละไฟล์มีสายสัญญาอนุญาตเดียว คือ OpenStreetMap (ต้องใช้สัญญาอนุญาตแบบเดียวกัน) ร่วมกับข้อมูลที่กำหนดเพียงให้แสดงที่มาตามที่ระบุไว้ของไฟล์นั้น",
        "",
        "Attributions to keep / ข้อความแสดงที่มาที่ต้องคงไว้:",
    ]
    for source_id in used:
        source = _source(ctx, source_id)
        lines.append(f"  - {source['name']}: {_licence(source)}. {source['attribution']}.")
    lines += [
        "  - Model and tables: FloodGuard Thailand, Mae Sai September 2024 flood replay (terrain-model reconstruction).",
        "",
        "4. WHAT IS NOT IN THIS FOLDER / สิ่งที่ไม่มีในโฟลเดอร์นี้",
        "",
        "  - No rain values. The HII rain gauge data shown on the replay page are CC BY-NC and stay out of every table here.",
        "  - Nothing from a source without a stated licence (the VIIRS daily flood maps shown on the page).",
        "  - Nothing from UNOSAT/GISTDA product 4009.",
        "  - No listed capacity from a shelter register, no occupancy count and no personal data.",
        "  - No Flood Preparedness Priority Score and no action class: the replay computes neither.",
        "",
        "  - ไม่มีค่าปริมาณฝน ข้อมูลสถานีวัดฝนของ สสน. ที่แสดงในหน้าการย้อนดูใช้สัญญาอนุญาต CC BY-NC จึงไม่อยู่ในตารางใดในโฟลเดอร์นี้",
        "  - ไม่มีข้อมูลจากแหล่งที่ไม่ระบุสัญญาอนุญาต (แผนที่น้ำท่วมรายวันของ VIIRS ที่แสดงในหน้าเว็บ)",
        "  - ไม่มีข้อมูลใดจากผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA",
        "  - ไม่มีความจุจากทะเบียนที่พักพิง ไม่มีจำนวนผู้เข้าพัก และไม่มีข้อมูลส่วนบุคคล",
        "  - ไม่มีคะแนนลำดับความสำคัญด้านการเตรียมความพร้อมรับน้ำท่วม และไม่มีระดับการดำเนินการ การย้อนดูไม่ได้คำนวณทั้งสองอย่าง",
        "",
        "5. HOW TO OPEN THE FILES / วิธีเปิดไฟล์",
        "",
        "The CSV files are UTF-8 with a byte-order mark, so Excel shows the Thai text correctly when you open them directly. Each",
        "CSV starts with provenance lines (the first cell starts with #): they say what the table is and is not, and they stay",
        "with the table when it is forwarded. The second line gives their number. The column header follows; each header cell is",
        "the English key and then the Thai label in brackets. In QGIS (Add Delimited Text Layer) set 'Number of header lines to",
        "discard' to that number; in pandas pass skiprows. The GeoJSON file opens in QGIS as it is and carries the same fields",
        "in its metadata member. Values yes and no are written in English; an empty cell means unknown or not applicable.",
        "",
        "ไฟล์ CSV เข้ารหัสแบบ UTF-8 พร้อมเครื่องหมาย BOM โปรแกรม Excel จึงแสดงข้อความภาษาไทยได้เมื่อเปิดไฟล์โดยตรง ทุกไฟล์ CSV",
        "เริ่มด้วยบรรทัดข้อมูลกำกับ (ช่องแรกขึ้นต้นด้วย #) ซึ่งบอกว่าตารางคืออะไรและไม่ใช่อะไร และจะติดไปกับตารางเมื่อส่งต่อ",
        "บรรทัดที่สองบอกจำนวนบรรทัดดังกล่าว จากนั้นเป็นหัวคอลัมน์ ซึ่งแต่ละช่องเป็นชื่อคอลัมน์ภาษาอังกฤษตามด้วยคำอธิบายภาษาไทยในวงเล็บ",
        "ใน QGIS ให้กำหนดจำนวนบรรทัดหัวตารางที่ต้องข้ามตามจำนวนนั้น ส่วนไฟล์ GeoJSON เปิดใน QGIS ได้ทันที",
        "ค่า yes และ no เขียนเป็นภาษาอังกฤษ ช่องว่างหมายถึงไม่ทราบหรือไม่เกี่ยวข้อง",
        "",
        "6. THE SHELTER-CANDIDATE VERIFICATION SHEET / แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง",
        "",
        "shelter_candidate_verification_sheet.csv is a blank checklist. " + sheet_state_en,
        "A local checker fills in the last five columns and returns the file to the project team; a returned check is labelled",
        f"'{VERIFICATION_LABEL}'. Give a role code, never a name: " + ", ".join(CHECKER_ROLES) + ".",
        "Do not add names of people, phone numbers, ID numbers or new columns. Keep the lines that start with # and the first",
        "eight columns as they are: they tie each answer to its site, and a file without them is refused. The returned file is",
        "kept outside the project's repository; only its hash and the checked columns are kept. Access notes are never published",
        "or kept: only the fact that a note was given is recorded.",
        "",
        "ไฟล์ shelter_candidate_verification_sheet.csv เป็นรายการตรวจที่ยังว่าง " + sheet_state_th,
        "ผู้ตรวจสอบในพื้นที่กรอกห้าคอลัมน์สุดท้าย",
        f"แล้วส่งไฟล์กลับให้ทีมโครงการ ผลที่ส่งกลับมาจะระบุว่า '{VERIFICATION_LABEL_TH}'",
        "โปรดระบุรหัสบทบาท ไม่ใช่ชื่อ: " + " · ".join(f"{code} = {label['th']}" for code, label in CHECKER_ROLES.items()),
        "โปรดอย่าใส่ชื่อบุคคล หมายเลขโทรศัพท์ เลขประจำตัว หรือเพิ่มคอลัมน์ โปรดคงบรรทัดที่ขึ้นต้นด้วย # และแปดคอลัมน์แรกไว้ตามเดิม",
        "เพราะข้อมูลส่วนนี้ผูกคำตอบแต่ละแถวกับสถานที่ ไฟล์ที่ไม่มีข้อมูลส่วนนี้จะถูกปฏิเสธ ไฟล์ที่ส่งกลับจะเก็บไว้นอกคลังรหัสของโครงการ",
        "เก็บไว้เพียงค่าแฮชและคอลัมน์ที่ตรวจสอบ หมายเหตุการเข้าถึงจะไม่ถูกเผยแพร่หรือเก็บไว้ บันทึกเพียงว่ามีการให้หมายเหตุหรือไม่",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def export_pack(ctx: ExportContext) -> list[ExportFile]:
    """Every file of the pack, in a fixed order, with the README last. Raises when a file breaks a rule."""
    specs = _specs(ctx)
    tables: dict[str, tuple[tuple[Column, ...], list[dict[str, Any]]]] = {
        "roads": (ROAD_COLUMNS, road_inundation_rows(ctx.ways, ctx.hourly_stages, ctx.tambons, ctx.event_start)),
        "access": (access_columns(ctx.knee_k), access_loss_rows(ctx.tambons, ctx.node_tambon, ctx.node_population, ctx.cut_codes,
                                                                ctx.hourly_stages, ctx.event_start, ctx.level_step_m, f"plan_{ctx.knee_k}")),
        "reported": (REPORTED_COLUMNS, reported_rows(ctx)),
        "plan": (PLAN_COLUMNS, plan_rows(ctx)),
        "capacitated": (CAPACITATED_COLUMNS, capacitated_rows(ctx)),
        "sheet": (SHEET_COLUMNS, sheet_rows(ctx)),
    }
    ids = {"roads": "modelled_road_inundation_by_hour", "access": "modelled_access_loss_by_hour", "reported": "shelter_plan_reported_2024",
           "plan": "shelter_plan_k", "capacitated": "shelter_plan_capacitated", "sites": "shelter_sites",
           "sheet": "shelter_candidate_verification_sheet"}
    files: list[ExportFile] = []
    for key in ("reported", "plan", "capacitated", "sites", "roads", "access", "sheet"):
        spec = specs[key]
        fields = header_fields(ctx, spec)
        source_ids = tuple(ctx.licence_overrides.get(spec["name"], spec["sources"]))
        if key == "sites":
            features = site_features(ctx)
            data = geojson_bytes(spec["name"], fields, SITE_FIELDS, features)
            files.append(ExportFile(ids[key], spec["name"], "application/geo+json", data, spec["title"], spec["lanes"], source_ids,
                                    len(features), None, SITE_FIELDS))
            continue
        columns, rows = tables[key]
        data, header_lines = csv_bytes(spec["name"], fields, columns, rows)
        files.append(ExportFile(ids[key], spec["name"], "text/csv", data, spec["title"], spec["lanes"], source_ids, len(rows),
                                header_lines, columns))
    used = tuple(dict.fromkeys(source_id for file in files for source_id in file.sources))
    lanes = tuple(dict.fromkeys(lane for file in files for lane in file.lanes))
    files.append(ExportFile("readme_licences", README_NAME, "text/plain", readme_bytes(ctx, files, specs), README_TITLE, lanes, used, None, None))
    names = [file.name for file in files]
    if len(set(names)) != len(names):
        raise ReplayExportError("export file names must be unique")
    return files
