"""Figures a deck or a speaker may quote about the Mae Sai replay (roadmap P4-1).

Every figure is read from, or computed with the page's own rules from, the files of the revision the page serves:
``timeline.json``, the season envelope's statistics file ``envelope.json``, ``access-nodes.bin`` and
``tambons.geojson``. Each file other than the manifest is checked against the SHA-256 the manifest lists for it, and
the manifest's own SHA-256 is printed in the document, so a re-bake changes the rendered document and the committed
copy (``docs/demo/replay_numbers.md``) fails its test until it is regenerated and re-read.

Figures keep their evidence lanes. Model figures are a T1 scenario with low confidence; observed figures are dated
observations shown beside the model; calibration figures were used to tune the model or were known while it was
tuned, so agreement with them is not independent; reported figures come from news and were not surveyed; and the
season-envelope figures are a scenario envelope, shared under CC BY-SA 4.0 with their own credit in a section of
their own. No priority score or action class is computed or quoted here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.replay_equity import replay_equity_gap
from floodguard.replay_exports import home_wet_mask
from floodguard.shelter_set_comparison import CUTOFF_NOT_REACHED, CUTOFF_REACHED, shelter_set_summary

ICT = timezone(timedelta(hours=7))
REPLAY_START = datetime(2024, 9, 9, tzinfo=ICT)
"""The replay origin: t = 0 is 9 Sep 2024 00:00 ICT."""
DEMO_HOURS: tuple[tuple[int, str, str], ...] = (
    (42, "the onset knot hour (GISTDA's calibration figure is for 18:15)", "ชั่วโมงของจุดเริ่มน้ำขึ้น (ตัวเลขของ GISTDA ที่ใช้ปรับแบบจำลองเป็นเวลา 18:15 น.)"),
    (46, "the onset link of the demo", "ลิงก์ช่วงเริ่มท่วมในการสาธิต"),
    (84, "the modelled peak (the peak link of the demo)", "ระดับสูงสุดของแบบจำลอง (ลิงก์ระดับสูงสุดในการสาธิต)"),
    (158, "the 15 Sep link of the demo", "ลิงก์วันที่ 15 ก.ย. ในการสาธิต"),
)
"""Replay hours of the demo's deep links (and of the onset knot), with why each is listed."""

LANES: Mapping[str, tuple[str, str]] = {
    "SCN": ("Model: T1 scenario, low confidence", "แบบจำลอง: สถานการณ์จำลองระดับ T1 ความเชื่อมั่นต่ำ"),
    "OBS": ("Observed, dated", "สังเกตการณ์ ระบุวันเวลา"),
    "CAL": ("Calibration: not an independent check", "ใช้ปรับแบบจำลอง: ไม่ใช่การตรวจสอบอิสระ"),
    "REP": ("Reported in news, not surveyed", "ตามรายงานข่าว ไม่ได้สำรวจ"),
    "SCN-ENV": ("Scenario envelope, plausibility, not validation", "ขอบเขตสถานการณ์จำลอง ดูความเป็นไปได้ ไม่ใช่การยืนยันความถูกต้อง"),
    "CTX": ("Context", "ข้อมูลประกอบ"),
}
"""What to say with a figure of each lane (English, Thai)."""


class ReplayNumbersError(ValueError):
    """Raised when the replay's files are missing, do not match the manifest or disagree with each other."""


@dataclass(frozen=True)
class Figure:
    """One quotable figure: a stable key, bilingual label, the value to quote, the exact value, lane and source."""

    key: str
    label_en: str
    label_th: str
    quote: str
    exact: str
    lane: str
    source: str


@dataclass(frozen=True)
class Table:
    """A small table of figures that belong together (one row per day, subdistrict or shelter set)."""

    key: str
    caption_en: str
    caption_th: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    lane: str
    source: str


@dataclass(frozen=True)
class Section:
    """A titled group of figures and tables with a note on how to read them."""

    key: str
    title_en: str
    title_th: str
    note_en: str
    note_th: str
    figures: tuple[Figure, ...] = ()
    tables: tuple[Table, ...] = ()
    licence: str | None = None


@dataclass(frozen=True)
class ReplayFiles:
    """The served revision's files the figures come from, with their SHA-256."""

    manifest_path: str
    manifest: Mapping[str, Any]
    manifest_sha256: str
    envelope: Mapping[str, Any] | None
    envelope_sha256: str | None
    nodes: bytes
    nodes_sha256: str
    tambons: Mapping[str, Any]
    tambons_sha256: str
    hashes_checked: tuple[str, ...] = field(default_factory=tuple)


# --- Formatting: the page's rounding (JavaScript toFixed and Math.round are half-up on the exact binary value) --------


def fixed(value: float, places: int) -> str:
    """``value`` with ``places`` decimals, rounded half-up on its exact binary value (JavaScript ``toFixed``)."""
    quantum = Decimal(1).scaleb(-places)
    return str(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP))


def whole(value: float) -> str:
    """``value`` rounded half-up to a whole number, with thousands separators (the page's resident counts)."""
    return f"{int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)):,}"


def percent(share: float, places: int = 0) -> str:
    """A share (0-1) as a percentage with ``places`` decimals."""
    return f"{fixed(share * 100, places)}%"


def exact(value: Any) -> str:
    """A stored value as written in the file (JSON spelling)."""
    return json.dumps(value, ensure_ascii=False)


def local_time(t_days: float) -> datetime:
    """Local time (ICT) of replay position ``t_days`` (days since 9 Sep 2024 00:00 ICT), to the minute."""
    return REPLAY_START + timedelta(minutes=round(t_days * 24 * 60))


def stamp(moment: datetime) -> str:
    """``10 Sep 18:15 ICT``."""
    return f"{moment.day} {moment:%b} {moment:%H:%M} ICT"


def stamp_th(moment: datetime) -> str:
    """``10 ก.ย. 18:15 น.`` (the replay's months are all September)."""
    months = {9: "ก.ย.", 10: "ต.ค.", 8: "ส.ค."}
    return f"{moment.day} {months[moment.month]} {moment:%H:%M} น."


def iso_stamp(value: str) -> str:
    """``2024-09-15T10:58:15+07:00`` as ``15 Sep 10:58 ICT``."""
    return stamp(datetime.fromisoformat(value).astimezone(ICT))


def iso_stamp_th(value: str) -> str:
    """``2024-09-15T10:58:15+07:00`` as ``15 ก.ย. 10:58 น.``."""
    return stamp_th(datetime.fromisoformat(value).astimezone(ICT))


S2_SENSITIVITY_TH: Mapping[str, str] = {
    "strict_clear": "นับเป็นพื้นที่ไม่มีเมฆเฉพาะคลาส 4 (พืช) 5 (ไม่มีพืช) และ 6 (น้ำ) ของการจำแนกฉาก",
    "threshold_0_1": "นับพิกเซลที่ไม่มีเมฆเมื่อ MNDWI > 0.1",
    "threshold_0_2": "นับพิกเซลที่ไม่มีเมฆเมื่อ MNDWI > 0.2",
}
"""Thai renderings of the Sentinel-2 check's stricter readings (the manifest states the rules in English)."""


# --- The page's rules, in Python ------------------------------------------------------------------------------------


def stage_at(t_days: float, anchors: Sequence[Mapping[str, float]]) -> float:
    """The assumed stage at ``t_days``: linear between keyframes, held outside them (the page's ``stageAt``, same arithmetic)."""
    if not anchors:
        raise ReplayNumbersError("at least one stage anchor is required")
    if t_days <= anchors[0]["t"]:
        return float(anchors[0]["stage_m"])
    if t_days >= anchors[-1]["t"]:
        return float(anchors[-1]["stage_m"])
    for a, b in zip(anchors, anchors[1:]):
        if a["t"] <= t_days < b["t"]:
            if t_days == a["t"]:
                return float(a["stage_m"])
            slope = (b["stage_m"] - a["stage_m"]) / (b["t"] - a["t"])
            return slope * (t_days - a["t"]) + a["stage_m"]
    return float(anchors[-1]["stage_m"])


def wet_sum(histogram: Sequence[float], stage: float, step: float) -> float:
    """Sum of histogram bins 1-254 whose HAND code is under ``stage`` (``code * step < stage``), as the page counts."""
    if len(histogram) != 256:
        raise ReplayNumbersError("a HAND-code histogram must have 256 bins")
    total = 0.0
    for code in range(1, 255):
        if code * step < stage:
            total += histogram[code]
    return total


def model_at_stage(manifest: Mapping[str, Any], stage: float) -> dict[str, Any]:
    """Flooded km2 and residents in flood water at ``stage``, district and per subdistrict (the page's ``districtStats``)."""
    step = float(manifest["hand"]["step_m"])
    area = float(manifest["pixel_area_m2"])
    tambon_km2 = {tid: round(wet_sum(hist, stage, step) * area / 1e6, 3) for tid, hist in manifest["tambon_histograms"].items()}
    out: dict[str, Any] = {"stage_m": stage, "flooded_km2": round(sum(tambon_km2.values()), 3), "tambon_flooded_km2": tambon_km2}
    population = manifest.get("population")
    if population:
        people = {tid: round(wet_sum(hist, stage, step), 1) for tid, hist in population["tambon_histograms"].items()}
        out["tambon_people_in_water"] = people
        out["people_in_water"] = round(sum(people.values()))
    return out


def read_nodes(data: bytes, access: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Decode ``access-nodes.bin`` with the manifest layout (little-endian float32 and uint8 columns)."""
    count = int(access["nodes"]["count"])
    out: dict[str, np.ndarray] = {}
    for column in access["nodes"]["layout"]:
        rows = column["shape"][0] if "shape" in column else 1
        dtype = np.dtype("<f4") if column["dtype"] == "float32" else np.dtype("u1")
        values = np.frombuffer(data, dtype=dtype, count=rows * count, offset=column["offset"])
        out[column["name"]] = values.reshape(rows, count) if "shape" in column else values
    return out


# --- Loading the served revision -------------------------------------------------------------------------------------


def served_manifest_path(root: Path) -> Path:
    """The manifest the page serves, from the one ``TIMELINE_MANIFEST_URL`` constant in ``flood-timeline.ts``."""
    source = (root / "apps" / "web" / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    marker = 'TIMELINE_MANIFEST_URL = "'
    start = source.index(marker) + len(marker)
    href = source[start:source.index('"', start)]
    return root / "apps" / "web" / "public" / href.lstrip("/")


def _checked_file(root: Path, reference: Mapping[str, Any], label: str) -> tuple[bytes, str]:
    path = root / "apps" / "web" / "public" / str(reference["href"]).lstrip("/")
    if not path.is_file():
        raise ReplayNumbersError(f"{label} is missing: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != reference["sha256"]:
        raise ReplayNumbersError(f"{label} does not match the SHA-256 the manifest lists ({digest} != {reference['sha256']})")
    return data, digest


def load_replay_files(root: Path) -> ReplayFiles:
    """Read the served revision's manifest and the three files the figures need, each checked against the manifest."""
    manifest_path = served_manifest_path(root)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    envelope = envelope_sha = None
    files = (manifest.get("season_envelope") or {}).get("files") or {}
    checked = []
    if "statistics" in files:
        data, envelope_sha = _checked_file(root, files["statistics"], "the season envelope's statistics file")
        envelope = json.loads(data)
        checked.append(files["statistics"]["href"])
    nodes, nodes_sha = _checked_file(root, manifest["access"]["nodes"], "access-nodes.bin")
    tambons_raw, tambons_sha = _checked_file(root, manifest["vectors"]["tambons"], "tambons.geojson")
    checked += [manifest["access"]["nodes"]["href"], manifest["vectors"]["tambons"]["href"]]
    return ReplayFiles(
        manifest_path=manifest_path.relative_to(root).as_posix(), manifest=manifest, manifest_sha256=hashlib.sha256(raw).hexdigest(),
        envelope=envelope, envelope_sha256=envelope_sha, nodes=nodes, nodes_sha256=nodes_sha,
        tambons=json.loads(tambons_raw), tambons_sha256=tambons_sha, hashes_checked=tuple(checked),
    )


# --- The figures -----------------------------------------------------------------------------------------------------


def _names(files: ReplayFiles) -> dict[str, tuple[str, str]]:
    return {feature["properties"]["id"]: (feature["properties"]["en"], feature["properties"]["th"]) for feature in files.tambons["features"]}


def _peak(manifest: Mapping[str, Any]) -> tuple[float, float, int]:
    """Stage, position (days) and replay hour of the modelled peak (the highest keyframe, first if repeated)."""
    anchors = manifest["stage_anchors"]
    best = max(anchors, key=lambda anchor: anchor["stage_m"])
    hour = math.floor(best["t"] * 24 + 1e-6)
    if abs(best["t"] * 24 - hour) > 1e-6:
        raise ReplayNumbersError("the peak keyframe is not on a whole replay hour")
    return float(best["stage_m"]), float(best["t"]), hour


def _check_day_stats(manifest: Mapping[str, Any]) -> None:
    """The Python rules must give the baked noon figures of every day exactly, or nothing else here can be trusted."""
    for day in manifest["days"]:
        stage = stage_at(day["index"] + 0.5, manifest["stage_anchors"])
        if abs(stage - day["stage_m"]) > 1e-9:
            raise ReplayNumbersError(f"{day['date']}: stage {stage} differs from the baked {day['stage_m']}")
        got = model_at_stage(manifest, stage)
        stats = day["stats"]
        if got["flooded_km2"] != stats["flooded_km2"] or got["tambon_flooded_km2"] != stats["tambon_flooded_km2"]:
            raise ReplayNumbersError(f"{day['date']}: flooded area {got['flooded_km2']} differs from the baked {stats['flooded_km2']}")
        if "people_in_water" in stats and got.get("people_in_water") != stats["people_in_water"]:
            raise ReplayNumbersError(f"{day['date']}: residents in water {got.get('people_in_water')} differ from the baked {stats['people_in_water']}")


def window_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    anchors = manifest["stage_anchors"]
    peak_stage, peak_t, peak_hour = _peak(manifest)
    rising = [anchor for anchor in anchors if anchor["t"] < peak_t]
    onset = max((anchor for anchor in rising if anchor["stage_m"] <= 0.1 + 1e-9 and anchor["stage_m"] > 0), key=lambda anchor: anchor["t"])
    start = datetime.fromisoformat(manifest["event_time"]["start"])
    end = datetime.fromisoformat(manifest["event_time"]["end"])
    hours = int((end - start).total_seconds() // 3600)
    dry_again = min((anchor for anchor in anchors if anchor["t"] > peak_t and anchor["stage_m"] == 0), key=lambda anchor: anchor["t"])
    figures = (
        Figure("replay.window", "Replay window (local time, ICT)", "ช่วงเวลาของการย้อนดู (เวลาประเทศไทย)",
               f"9 Sep 00:00 to 19 Sep 24:00 ICT ({hours} hours)", f"{manifest['event_time']['start']} / {manifest['event_time']['end']}",
               "CTX", "timeline.json $.event_time"),
        Figure("stage.onset_knot", f"Onset keyframe: assumed stage {fixed(onset['stage_m'], 2)} m at {stamp(local_time(onset['t']))}",
               f"จุดกำหนดช่วงเริ่มท่วม: ระดับน้ำสมมุติ {fixed(onset['stage_m'], 2)} ม. เวลา {stamp_th(local_time(onset['t']))}",
               f"{fixed(onset['stage_m'], 2)} m", f"t = {exact(onset['t'])} d, stage_m = {exact(onset['stage_m'])}", "SCN", "timeline.json $.stage_anchors"),
        Figure("stage.peak", f"Modelled peak: assumed stage at {stamp(local_time(peak_t))} (replay hour {peak_hour})",
               f"ระดับสูงสุดของแบบจำลอง: ระดับน้ำสมมุติเวลา {stamp_th(local_time(peak_t))} (ชั่วโมงที่ {peak_hour} ของการย้อนดู)",
               f"{fixed(peak_stage, 2)} m", f"t = {exact(peak_t)} d, stage_m = {exact(peak_stage)}", "SCN", "timeline.json $.stage_anchors"),
        Figure("stage.back_to_zero", "First keyframe back at 0 m after the peak", "จุดกำหนดแรกหลังระดับสูงสุดที่กลับเป็น 0 ม.",
               stamp(local_time(dry_again["t"])), f"t = {exact(dry_again['t'])} d", "SCN", "timeline.json $.stage_anchors"),
    )
    return Section("window", "Replay window and assumed stage", "ช่วงเวลาและระดับน้ำสมมุติ",
                   "The stage is an illustrative keyframe curve shaped to the event chronology; no gauge record exists for September 2024.",
                   "ระดับน้ำเป็นเส้นจุดกำหนดเพื่อการอธิบายที่ปรับตามลำดับเหตุการณ์ ไม่มีบันทึกจากสถานีวัดระดับน้ำสำหรับเดือนกันยายน 2567 (2024)",
                   figures=figures)


def demo_hours_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    rows = []
    for hour, why_en, why_th in DEMO_HOURS:
        stage = stage_at(hour / 24, manifest["stage_anchors"])
        got = model_at_stage(manifest, stage)
        moment = local_time(hour / 24)
        rows.append((str(hour), f"{stamp(moment)}<br>{stamp_th(moment)}", f"{why_en}<br>{why_th}", f"{fixed(stage, 2)} m",
                     f"{fixed(got['flooded_km2'], 1)} km²", whole(got["people_in_water"])))
    table = Table("model.demo_hours", "The model at the replay hours the demo opens", "แบบจำลอง ณ ชั่วโมงที่ลิงก์สาธิตเปิด",
                  ("Hour (t=)", "Local time", "Why", "Assumed stage", "Flooded (model)", "Residents in flood water (model)"), tuple(rows),
                  "SCN", "timeline.json $.stage_anchors, $.tambon_histograms, $.population.tambon_histograms (the page's districtStats)")
    return Section("demo_hours", "The model at the demo's hours", "แบบจำลอง ณ ชั่วโมงของการสาธิต",
                   "These are the figures the page's moment line shows at each link. The same rules reproduce the baked noon figure of every day exactly (checked when this file is generated).",
                   "เป็นตัวเลขเดียวกับที่บรรทัดสรุปช่วงเวลาบนหน้าแสดงที่แต่ละลิงก์ กฎเดียวกันนี้ให้ตัวเลขเที่ยงวันที่บันทึกไว้ของทุกวันตรงกันทุกค่า (ตรวจเมื่อสร้างไฟล์นี้)",
                   tables=(table,))


def peak_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    names = _names(files)
    peak_stage, peak_t, peak_hour = _peak(manifest)
    day = next(day for day in manifest["days"] if abs(day["index"] + 0.5 - peak_t) < 1e-9)
    stats = day["stats"]
    low = manifest["hand"]["low_confidence_share"]
    coverage = manifest["model_coverage"]
    facilities = manifest["facilities_count"]
    source = f"timeline.json $.days[{day['index']}].stats"
    figures = (
        Figure("peak.flooded_km2", "Flooded area at the modelled peak, Mae Sai district (out of channel)", "พื้นที่น้ำท่วม ณ ระดับสูงสุดของแบบจำลอง อำเภอแม่สาย (นอกร่องน้ำ)",
               f"{fixed(stats['flooded_km2'], 1)} km²", exact(stats["flooded_km2"]), "SCN", f"{source}.flooded_km2"),
        Figure("peak.residents_in_water", "Modelled residents in flood water at the peak (WorldPop 2020, not the 2024 population)",
               "ผู้อยู่อาศัยตามแบบจำลองในพื้นที่น้ำท่วม ณ ระดับสูงสุด (WorldPop 2020 ไม่ใช่ประชากรปี 2567 (2024))",
               whole(stats["people_in_water"]), exact(stats["people_in_water"]), "SCN", f"{source}.people_in_water"),
        Figure("peak.road_km_impassable", "Modelled impassable road at the peak (depth ≥ 0.3 m)", "ถนนที่สัญจรไม่ได้ตามแบบจำลอง ณ ระดับสูงสุด (ลึก ≥ 0.3 ม.)",
               f"{fixed(stats['road_km_impassable'], 1)} km", exact(stats["road_km_impassable"]), "SCN", f"{source}.road_km_impassable"),
        Figure("peak.road_km_wet", "Modelled wet road at the peak (under 0.3 m)", "ถนนที่มีน้ำตามแบบจำลอง ณ ระดับสูงสุด (ลึกไม่ถึง 0.3 ม.)",
               f"{fixed(stats['road_km_wet'], 1)} km", exact(stats["road_km_wet"]), "SCN", f"{source}.road_km_wet"),
        Figure("peak.facilities_wet", "Key facilities (OSM) wet at the peak", "สถานที่สำคัญ (OSM) ที่น้ำถึง ณ ระดับสูงสุด",
               f"{stats['facilities_wet']} of {facilities['total']}", f"{exact(stats['facilities_wet'])} of {exact(facilities['total'])}", "SCN",
               f"{source}.facilities_wet, $.facilities_count.total"),
        Figure("peak.low_confidence_km2", "Low-confidence water at the peak (flat or filled low ground in the elevation model), still counted in every figure",
               "น้ำที่ความเชื่อมั่นต่ำ ณ ระดับสูงสุด (พื้นที่ราบหรือแอ่งที่ถูกถมในแบบจำลองความสูง) ยังนับรวมในทุกตัวเลข",
               f"{fixed(low['low_confidence_km2'], 1)} of {fixed(low['peak_flooded_km2'], 1)} km²", exact(low), "SCN", "timeline.json $.hand.low_confidence_share"),
        Figure("model.coverage_km2", "District area inside the water model", "พื้นที่อำเภอที่อยู่ในแบบจำลองน้ำ",
               f"{fixed(coverage['modelled_km2'], 1)} of {fixed(coverage['district_km2'], 1)} km²",
               f"{exact(coverage['modelled_km2'])} of {exact(coverage['district_km2'])}", "CTX", "timeline.json $.model_coverage"),
    )
    rows = tuple(
        (f"{names[tid][0]}<br>{names[tid][1]}", tid, f"{fixed(stats['tambon_flooded_km2'][tid], 1)}", whole(stats["tambon_people_in_water"][tid]))
        for tid in manifest["access"]["tambons"]
    )
    table = Table("peak.by_subdistrict", "Each subdistrict at the modelled peak", "แต่ละตำบล ณ ระดับสูงสุดของแบบจำลอง",
                  ("Subdistrict", "Code", "Flooded km² (model)", "Residents in flood water (model)"), rows, "SCN",
                  f"{source}.tambon_flooded_km2, .tambon_people_in_water; names from tambons.geojson")
    return Section("peak", f"At the modelled peak ({stamp(local_time(peak_t))}, assumed stage {fixed(peak_stage, 2)} m)",
                   f"ณ ระดับสูงสุดของแบบจำลอง ({stamp_th(local_time(peak_t))} ระดับน้ำสมมุติ {fixed(peak_stage, 2)} ม.)",
                   "A model reconstruction from terrain at an illustrative stage: not observed. Residents are WorldPop 2020 modelled estimates.",
                   "เป็นการจำลองจากภูมิประเทศที่ระดับน้ำเพื่อการอธิบาย ไม่ใช่การสังเกตการณ์ ผู้อยู่อาศัยเป็นค่าประมาณจากแบบจำลอง WorldPop 2020",
                   figures=figures, tables=(table,))


def days_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    knee = f"plan_{manifest['shelters']['knee_k']}"
    phases = {phase["id"]: phase["label"] for phase in manifest["phases"]}
    rows = []
    for day in manifest["days"]:
        stats = day["stats"]
        access = stats.get("access", {})
        moment = REPLAY_START + timedelta(days=day["index"], hours=12)
        rows.append((f"{moment.day} Sep<br>{moment.day} ก.ย.", f"{phases[day['phase']]['en']}<br>{phases[day['phase']]['th']}", f"{fixed(day['stage_m'], 2)} m",
                     f"{fixed(stats['flooded_km2'], 1)}", whole(stats["people_in_water"]), f"{fixed(stats['road_km_impassable'], 1)}",
                     whole(access["reported_2024"]["people_lost_access"]), whole(access[knee]["people_lost_access"])))
    table = Table("days.noon", "Each day at local noon", "แต่ละวัน ณ เที่ยงวันเวลาท้องถิ่น",
                  ("Day", "Phase", "Assumed stage", "Flooded km²", "Residents in flood water", "Impassable road km",
                   "Lost walking access, shelters reported in 2024", f"Lost walking access, plan of {manifest['shelters']['knee_k']} sites"),
                  tuple(rows), "SCN", "timeline.json $.days[*] (stage_m, stats)")
    return Section("days", "Day by day (model)", "รายวัน (แบบจำลอง)",
                   "Noon figures, as the day buttons show them. Access counts all residents at road nodes who lost walking access to a shelter of the set that they had before the flood.",
                   "ตัวเลข ณ เที่ยงวัน ตามที่ปุ่มวันแสดง การเข้าถึงนับผู้อยู่อาศัยทั้งหมดที่จุดถนนที่สูญเสียการเดินไปถึงที่พักพิงของชุดนั้นซึ่งเคยไปถึงได้ก่อนน้ำท่วม",
                   tables=(table,))


def access_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    access = manifest["access"]
    shelters = manifest["shelters"]
    nodes = read_nodes(files.nodes, access)
    population = nodes["population"].astype(float)
    vulnerable = nodes["vulnerable_population"].astype(float)
    peak_stage, peak_t, _ = _peak(manifest)
    hourly = [stage_at(hour / 24, manifest["stage_anchors"]) for hour in range(int(round(manifest_hours(manifest))))]
    flooded = home_wet_mask(nodes["home_code"], peak_stage, float(manifest["hand"]["step_m"]))
    knee = int(shelters["knee_k"])
    counted = sum(1 for site in shelters["reported"] if site["in_access_set"] and site["lat"] is not None and site["lon"] is not None)
    sets = (("reported_2024", f"Shelters reported used in Sep 2024 ({counted} sites counted)", f"ที่พักพิงที่มีรายงานว่าใช้จริงในเดือน ก.ย. 2567 (2024) (นับ {counted} แห่ง)"),
            (f"plan_{knee}", f"Ranked plan, first {knee} sites", f"แผนจัดอันดับ {knee} แห่งแรก"))
    scopes = (("all", "All residents at road nodes", "ผู้อยู่อาศัยทั้งหมดที่จุดถนน", np.ones(population.shape, dtype=bool)),
              ("flooded", "Residents whose homes flood at the peak", "ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด", flooded))
    rows = []
    equity_rows = []
    peak_day = next(day for day in manifest["days"] if abs(day["index"] + 0.5 - peak_t) < 1e-9)
    for set_id, set_en, set_th in sets:
        codes = nodes["cut_codes"][access["sets"].index(set_id)]
        for scope, scope_en, scope_th, mask in scopes:
            summary = shelter_set_summary(population, codes, peak_stage, hourly, vulnerable_population=vulnerable, mask=mask)
            if scope == "all" and whole(summary.lost) != whole(peak_day["stats"]["access"][set_id]["people_lost_access"]):
                raise ReplayNumbersError(f"{set_id}: the lost count {summary.lost} differs from the baked peak figure")
            if summary.cutoff_status == CUTOFF_REACHED:
                moment = local_time(summary.cutoff_hour / 24)
                cutoff = f"{stamp(moment)} (hour {summary.cutoff_hour})<br>{stamp_th(moment)}"
            elif summary.cutoff_status == CUTOFF_NOT_REACHED:
                cutoff = "Not reached: at least half keep access at every hour<br>ไม่ถึงเกณฑ์: อย่างน้อยครึ่งหนึ่งยังเดินถึงได้ทุกชั่วโมง"
            else:
                cutoff = "No one within reach before the flood<br>ไม่มีผู้ใดอยู่ในระยะเดินก่อนน้ำท่วม"
            share = percent(summary.lost_share) if summary.lost_share is not None else "n/a"
            rows.append((f"{set_en}<br>{set_th}", f"{scope_en}<br>{scope_th}", f"{whole(summary.baseline)} of {whole(summary.residents)}",
                         whole(summary.keeping), f"{whole(summary.lost)} ({share})", cutoff))
            other_lost = summary.lost - summary.vulnerable_lost
            other_baseline = summary.baseline - summary.vulnerable_baseline
            gap = replay_equity_gap(summary.vulnerable_lost, summary.vulnerable_baseline, other_lost, other_baseline)
            result = equity_result(gap)
            vulnerable_rate = f" ({percent(gap.vulnerable_rate, 2)})" if gap.vulnerable_rate is not None and gap.vulnerable_lost > 0 else ""
            other_rate = f" ({percent(gap.non_vulnerable_rate, 2)})" if gap.non_vulnerable_rate is not None and other_lost > 0 else ""
            equity_rows.append((f"{set_en}<br>{set_th}", f"{scope_en}<br>{scope_th}",
                                f"{whole(summary.vulnerable_lost)} of {whole(summary.vulnerable_baseline)}{vulnerable_rate}",
                                f"{whole(other_lost)} of {whole(other_baseline)}{other_rate}", result))
    totals = access["totals"]
    figures = (
        Figure("access.residents_at_road_nodes", "Residents counted at road nodes (WorldPop 2020)", "ผู้อยู่อาศัยที่นับที่จุดถนน (WorldPop 2020)",
               whole(float(population.sum())), exact(totals["population"]), "SCN", "access-nodes.bin population; timeline.json $.access.totals.population"),
        Figure("access.homes_flood_at_peak", "Of those, residents whose homes flood at the modelled peak (shelter demand, an upper bound)",
               "ในจำนวนนี้ ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง (ความต้องการที่พักพิง ค่าขอบบน)",
               whole(shelters["demand_people"]), exact(shelters["demand_people"]), "SCN", "timeline.json $.shelters.demand_people"),
        Figure("access.walk_limit", "Walking limit to a shelter, on roads still passable", "ระยะเดินสูงสุดไปยังที่พักพิงบนถนนที่ยังสัญจรได้",
               f"{fixed(access['threshold_m'] / 1000, 0)} km (about 30 min)", exact(access["threshold_m"]), "SCN", "timeline.json $.access.threshold_m"),
    )
    table = Table("access.sets", "The two shelter sets side by side at the peak (no single figure ranks them)", "ที่พักพิงสองชุดเทียบกัน ณ ระดับสูงสุด (ไม่มีตัวเลขใดตัวเลขเดียวที่ใช้จัดอันดับ)",
                  ("Set", "Counted", "Within reach before the flood", "Still within reach at the peak", "Lost at the peak (share of within reach)",
                   "Modelled access cut-off hour"), tuple(rows), "SCN",
                  "access-nodes.bin cut codes with floodguard.shelter_set_comparison (the page's shelterSetComparison)")
    equity = Table("access.equity", "Evacuation Equity Gap at the peak (proxy-vulnerable = terrain and remoteness proxy)",
                   "ช่องว่างความเท่าเทียมในการอพยพ ณ ระดับสูงสุด (กลุ่มเปราะบางตามตัวแทนด้านภูมิประเทศและความห่างไกล)",
                   ("Set", "Counted", "Proxy-vulnerable: lost of those within reach before the flood", "Everyone else: lost of those within reach before the flood", "Result"),
                   tuple(equity_rows), "SCN", "access-nodes.bin with floodguard.replay_equity (the page's evacuationEquityGap)")
    return Section("access", "Walking access to a shelter (T1 scenario)", "การเดินไปถึงที่พักพิง (สถานการณ์จำลองระดับ T1)",
                   "Planning scenario, not observed evacuation outcomes. Hours come from illustrative stage keyframes, not observations. Read both columns: the reported set reaches more residents overall, the plan reaches more of those whose homes flood.",
                   "เป็นสถานการณ์เพื่อการวางแผน ไม่ใช่ผลการอพยพที่สังเกตได้ ชั่วโมงมาจากจุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่การสังเกตการณ์ ควรอ่านทั้งสองคอลัมน์: ชุดที่มีรายงานไปถึงผู้อยู่อาศัยโดยรวมได้มากกว่า ส่วนแผนไปถึงผู้ที่บ้านถูกน้ำท่วมได้มากกว่า",
                   figures=figures, tables=(table, equity))


EQUITY_REASONS: Mapping[str, tuple[str, str]] = {
    "insufficient_group_denominator": ("no ratio: a group has fewer than 50 residents within reach before the flood",
                                       "ไม่แสดงอัตราส่วน: มีกลุ่มที่มีผู้อยู่ในระยะเดินก่อนน้ำท่วมไม่ถึง 50 คน"),
    "no_loss": ("no ratio: nobody has lost access", "ไม่แสดงอัตราส่วน: ไม่มีผู้ใดสูญเสียการเข้าถึง"),
    "undefined_ratio": ("no ratio: only proxy-vulnerable residents lost access", "ไม่แสดงอัตราส่วน: มีเพียงกลุ่มเปราะบางตามตัวแทนที่สูญเสียการเข้าถึง"),
}
EQUITY_BANDS: Mapping[str, str] = {"higher": "สูงกว่า", "lower": "ต่ำกว่า", "similar": "ใกล้เคียงกัน"}


def equity_result(gap: Any) -> str:
    """The equity cell as the page reads it: the ratio and its band, or why no ratio is shown (English, then Thai)."""
    if gap.reason is not None:
        en, th = EQUITY_REASONS[gap.reason]
        return f"{en}<br>{th}"
    if gap.vulnerable_lost == 0:
        return "no proxy-vulnerable resident has lost access<br>ไม่มีผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนที่สูญเสียการเข้าถึง"
    return f"{fixed(gap.ratio, 2)}× ({gap.band})<br>{fixed(gap.ratio, 2)} เท่า ({EQUITY_BANDS.get(gap.band, gap.band)})"


def manifest_hours(manifest: Mapping[str, Any]) -> float:
    """Hours in the replay window."""
    start = datetime.fromisoformat(manifest["event_time"]["start"])
    end = datetime.fromisoformat(manifest["event_time"]["end"])
    return (end - start).total_seconds() / 3600


def capacity_section(files: ReplayFiles) -> Section:
    shelters = files.manifest["shelters"]
    cap = shelters["capacitated"]
    knee = int(shelters["knee_k"])
    demand = int(cap["demand_people"])
    coverage_row = cap["coverage_plan"][knee - 1]
    if coverage_row["candidate_id"] != shelters["plan"][knee - 1]["candidate_id"]:
        raise ReplayNumbersError("the capacity-counted coverage plan does not follow the ranked plan")
    ranked_size = min(knee, len(cap["plan"]))
    ranked_row = cap["plan"][ranked_size - 1]
    last = cap["plan"][-1]
    eligible = cap["all_eligible"]

    def row(label_en: str, label_th: str, within: float | None, counts: Mapping[str, Any]) -> tuple[str, ...]:
        return (f"{label_en}<br>{label_th}", whole(within) if within is not None else "not counted",
                whole(counts["lower"]["served"]), whole(counts["upper"]["served"]),
                f"{whole(counts['upper']['overflow'])} to {whole(counts['lower']['overflow'])}")

    rows = (
        row(f"The first {knee} sites of the ranked plan", f"{knee} แห่งแรกของแผนจัดอันดับ", shelters["plan"][knee - 1]["cumulative_demand"], coverage_row),
        row(f"The first {ranked_size} sites of the capacity-aware ranking", f"{ranked_size} แห่งแรกของการจัดอันดับที่คำนึงถึงความจุ", ranked_row.get("within_reach"), ranked_row),
        row(f"All {len(cap['plan'])} sites of the capacity-aware ranking", f"ทั้ง {len(cap['plan'])} แห่งของการจัดอันดับที่คำนึงถึงความจุ", None, last),
        row(f"Every eligible candidate ({eligible['sites']}; {eligible['sites_with_estimate']} with a capacity estimate)",
            f"สถานที่ที่เข้าเกณฑ์ทั้งหมด ({eligible['sites']} แห่ง มีค่าประมาณความจุ {eligible['sites_with_estimate']} แห่ง)", eligible["within_reach"], eligible),
    )
    table = Table("capacity.bounds", f"Who fits, of the {whole(demand)} residents whose homes flood at the peak (two bounds)",
                  f"จำนวนที่รองรับได้ จากผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด {whole(demand)} คน (สองขอบเขต)",
                  ("Sites", "Within the 2 km walk", "Fit, lower bound", "Fit, upper bound", "Without a place (upper to lower)"), rows, "SCN",
                  "timeline.json $.shelters.capacitated (coverage_plan, plan, all_eligible); $.shelters.plan[].cumulative_demand")
    medians = cap["kind_median_capacity"]
    levels = shelters["robustness"]["stages"]
    core = shelters["robustness"]["core_by_k"][knee - 1]
    figures = (
        Figure("capacity.medians", "Median capacity estimate used for a site without a footprint (upper bound)", "ค่ามัธยฐานความจุที่ใช้กับสถานที่ที่ไม่มีรูปอาคาร (ขอบเขตบน)",
               ", ".join(f"{kind} {value}" for kind, value in sorted(medians.items())) + f"; any kind {cap['all_kinds_median_capacity']}",
               exact({**medians, "all_kinds": cap["all_kinds_median_capacity"]}), "SCN", "timeline.json $.shelters.capacitated.kind_median_capacity, .all_kinds_median_capacity"),
        *(Figure(f"whatif.demand_{fixed(level['stage_m'], 1)}", f"What-if level {fixed(level['stage_m'], 1)} m: residents whose homes flood; eligible candidates",
                 f"ระดับสมมุติ {fixed(level['stage_m'], 1)} ม.: ผู้ที่บ้านถูกน้ำท่วม และสถานที่ที่เข้าเกณฑ์",
                 f"{whole(level['demand_people'])}; {level['eligible_count']} sites", f"{exact(level['demand_people'])}; {exact(level['eligible_count'])}", "SCN",
                 "timeline.json $.shelters.robustness.stages") for level in levels),
        Figure("whatif.robust_core", f"Plan sites among the first {knee} at every what-if level (robust core)", f"สถานที่ในแผนที่อยู่ใน {knee} แห่งแรกทุกระดับสมมุติ (แกนที่คงทน)",
               f"{len(core)} of {knee}", exact(core), "SCN", f"timeline.json $.shelters.robustness.core_by_k[{knee - 1}]"),
    )
    return Section("capacity", "Shelter capacity (T1 scenario)", "ความจุของที่พักพิง (สถานการณ์จำลองระดับ T1)",
                   "Capacity is an unverified estimate from mapped building footprints; neither bound is a limit on who fits. The sites are candidates to verify on the ground, not a list of sites to open. The what-if levels are not return periods.",
                   "ความจุเป็นค่าประมาณจากรูปอาคารที่ทำแผนที่ไว้และยังไม่ได้ตรวจสอบ ทั้งสองขอบเขตไม่ใช่ขีดจำกัดของจำนวนที่รองรับได้ สถานที่เหล่านี้เป็นสถานที่ที่ต้องตรวจในพื้นที่ ไม่ใช่รายชื่อสถานที่ที่ต้องเปิด ระดับสมมุติไม่ใช่คาบการเกิดซ้ำ",
                   figures=figures, tables=(table,))


def observed_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    s2 = manifest["s2_crosscheck"]
    scenes = {scene["role"]: scene for scene in s2["scenes"]}
    event, before = scenes["event"], scenes["pre_event"]
    change = s2["change"]
    model = s2["model_at_event_scene"]
    src = "timeline.json $.s2_crosscheck"
    figures = [
        Figure("s2.event_water_km2", f"Sentinel-2 L2A {iso_stamp(event['local_time'])}: water or saturated mud outside mapped channels, in clear pixels",
               f"Sentinel-2 L2A {iso_stamp_th(event['local_time'])}: น้ำหรือโคลนอิ่มน้ำนอกร่องน้ำ ในพิกเซลที่ไม่มีเมฆ",
               f"{fixed(event['water_km2'], 1)} km² ({percent(event['clear_share'])} of the district clear)", exact({"water_km2": event["water_km2"], "clear_share": event["clear_share"]}),
               "OBS", f"{src}.scenes[role=event]"),
        Figure("s2.before_water_km2", f"Sentinel-2 L2A {iso_stamp(before['local_time'])}, before the flood: the same measure",
               f"Sentinel-2 L2A {iso_stamp_th(before['local_time'])} ก่อนน้ำท่วม: วัดแบบเดียวกัน",
               f"{fixed(before['water_km2'], 1)} km² ({percent(before['clear_share'])} clear)", exact({"water_km2": before["water_km2"], "clear_share": before["clear_share"]}),
               "OBS", f"{src}.scenes[role=pre_event]"),
        Figure("s2.new_water_km2", "New water or saturated mud where both dates are clear", "น้ำหรือโคลนอิ่มน้ำที่เพิ่มขึ้นในพื้นที่ที่ไม่มีเมฆทั้งสองวัน",
               f"{fixed(change['new_water_km2'], 1)} km² (of {fixed(change['both_clear_km2'], 1)} km² clear on both dates)", exact(change), "OBS", f"{src}.change"),
        Figure("s2.model_same_pixels", f"Model at the scene time (assumed stage {fixed(model['model_stage_m'], 2)} m): flooded in the same clear pixels; in the whole district",
               f"แบบจำลอง ณ เวลาของภาพ (ระดับน้ำสมมุติ {fixed(model['model_stage_m'], 2)} ม.): น้ำท่วมในพิกเซลเดียวกันที่ไม่มีเมฆ และทั้งอำเภอ",
               f"{fixed(model['model_flood_km2_clear'], 1)} km²; {fixed(model['model_flood_km2_district'], 1)} km²",
               exact({key: model[key] for key in ("model_stage_m", "model_flood_km2_clear", "model_flood_km2_district", "model_flood_km2_both_clear")}),
               "SCN", f"{src}.model_at_event_scene"),
        Figure("s2.model_agreement", "Model and observed area: overlap; agreement (IoU); share of the observed area the model reaches. Indicative.",
               "แบบจำลองกับพื้นที่ที่สังเกตได้: ส่วนที่ซ้อนกัน ค่าความสอดคล้อง (IoU) และสัดส่วนของพื้นที่ที่สังเกตได้ที่แบบจำลองไปถึง เป็นเพียงข้อบ่งชี้",
               f"{fixed(model['model_overlap_km2'], 1)} km²; IoU {fixed(model['model_agreement_iou'], 3)}; {percent(model['model_share_of_observed_water_reached'])}",
               exact({key: model[key] for key in ("model_overlap_km2", "model_agreement_iou", "model_share_of_observed_water_reached")}), "SCN", f"{src}.model_at_event_scene"),
    ]
    for item in s2["sensitivity"]:
        figures.append(Figure(f"s2.sensitivity.{item['id']}", f"Stricter reading ({item['rule']}): water or saturated mud on 15 Sep",
                              f"การอ่านที่เข้มงวดกว่า ({S2_SENSITIVITY_TH.get(item['id'], item['id'])}): น้ำหรือโคลนอิ่มน้ำวันที่ 15 ก.ย.",
                              f"{fixed(item['event_water_km2'], 1)} km²", exact(item["event_water_km2"]), "OBS", f"{src}.sensitivity[id={item['id']}]"))
    viirs = manifest["viirs_daily"]
    rows = []
    cloudy = 0
    for day in viirs["days"]:
        moment = datetime.fromisoformat(day["date"])
        if day["cloud_share"] >= 0.5:
            cloudy += 1
        observed = day.get("viirs_flood_km2_clear")
        modelled = day.get("model_flood_km2_clear")
        no_view = day["clear_km2"] == 0
        rows.append((f"{moment.day} Sep<br>{moment.day} ก.ย.", percent(day["cloud_share"]), fixed(day["clear_km2"], 1),
                     "no observation" if no_view or observed is None else fixed(observed, 1), "no observation" if no_view or modelled is None else fixed(modelled, 1)))
    table = Table("viirs.days", f"VIIRS daily flood maps (375 m, observed) and the model in the same clear pixels; cloud hid at least half of the district on {cloudy} of {len(rows)} days",
                  f"แผนที่น้ำท่วมรายวัน VIIRS (375 ม. สังเกตการณ์) กับแบบจำลองในพิกเซลเดียวกันที่ไม่มีเมฆ เมฆบังอย่างน้อยครึ่งอำเภอใน {cloudy} จาก {len(rows)} วัน",
                  ("Day", "Cloud", "Clear km²", "VIIRS flood km² (observed)", "Model km² (same pixels)"), tuple(rows), "OBS",
                  "timeline.json $.viirs_daily.days[*] (model_* fields are T1 scenario)")
    return Section("observed", "Observed evidence: Sentinel-2 on 15 Sep and the VIIRS daily maps", "หลักฐานจากการสังเกตการณ์: Sentinel-2 วันที่ 15 ก.ย. และแผนที่รายวัน VIIRS",
                   "Observed figures are used as provided and shown beside the model. The larger observed area on 15 Sep is consistent with water or saturated mud left after the river fell; the terrain-only model cannot hold water once the river level drops. The comparison is indicative.",
                   "ตัวเลขจากการสังเกตการณ์ใช้ตามที่ได้มาและแสดงคู่กับแบบจำลอง พื้นที่ที่สังเกตได้ซึ่งใหญ่กว่าในวันที่ 15 ก.ย. สอดคล้องกับน้ำหรือโคลนอิ่มน้ำที่เหลือหลังแม่น้ำลดลง แบบจำลองที่ใช้ภูมิประเทศอย่างเดียวไม่สามารถกักน้ำไว้ได้เมื่อระดับแม่น้ำลดลง การเปรียบเทียบนี้เป็นเพียงข้อบ่งชี้",
                   figures=tuple(figures), tables=(table,))


def calibration_section(files: ReplayFiles) -> Section:
    manifest = files.manifest
    checks = {check["id"]: check for check in manifest["external_checks"]}
    gistda = next(check for check in checks.values() if check["role"] == "calibration_anchor")
    informed = [check for check in checks.values() if check["role"] == "calibration_informed_magnitude_check"]
    radar = manifest["s1_anchor"]
    figures = [
        Figure("cal.gistda", "GISTDA RADARSAT-2 analysis, 10 Sep 18:15: reported flooded area; the model at the stage tuned to it",
               "การวิเคราะห์ RADARSAT-2 ของ GISTDA วันที่ 10 ก.ย. 18:15 น.: พื้นที่น้ำท่วมที่รายงาน และแบบจำลองที่ระดับน้ำซึ่งปรับให้ตรงกับตัวเลขนี้",
               f"{fixed(gistda['reported_km2'], 1)} km² reported ({gistda['reported_text']}); model {fixed(gistda['model_km2'], 1)} km² at {fixed(gistda['model_stage_m'], 2)} m",
               exact({key: gistda[key] for key in ("reported_km2", "reported_text", "model_km2", "model_stage_m")}), "CAL", f"timeline.json $.external_checks[id={gistda['id']}]"),
    ]
    for check in informed:
        figures.append(Figure(
            f"cal.{check['id']}", "UNOSAT product 3991, 13-19 Sep: flood-affected area and people exposed (an exposure estimate, a different measure from residents in water); the model's largest extent in that window",
            "ผลิตภัณฑ์ 3991 ของ UNOSAT วันที่ 13-19 ก.ย.: พื้นที่ได้รับผลกระทบและประชากรที่อยู่ในพื้นที่น้ำท่วม (ค่าประมาณการสัมผัสน้ำ ต่างจากผู้อยู่อาศัยในน้ำ) และขอบเขตที่ใหญ่ที่สุดของแบบจำลองในช่วงนั้น",
            f"about {fixed(check['reported_km2'], 0)} km² and {whole(check['reported_people'])} people; model {fixed(check['model_km2'], 1)} km² and {whole(check['model_people_in_water'])} residents in water at {fixed(check['model_stage_m'], 2)} m",
            exact({key: check[key] for key in ("reported_km2", "reported_people", "model_km2", "model_people_in_water", "model_stage_m")}), "CAL",
            f"timeline.json $.external_checks[id={check['id']}]"))
    pair = radar["images"]
    figures.append(Figure(
        "cal.s1_same_track", f"Sentinel-1 same-track pair {iso_stamp(pair[0]['local'])} to {iso_stamp(pair[-1]['local'])} (relative orbit {pair[-1]['relative_orbit']}): newly dark area; best-fit stage; model at that stage; agreement (IoU)",
        f"ภาพ Sentinel-1 คู่วงโคจรเดียวกัน {iso_stamp_th(pair[0]['local'])} ถึง {iso_stamp_th(pair[-1]['local'])} (วงโคจรสัมพัทธ์ {pair[-1]['relative_orbit']}): พื้นที่ที่มืดลงใหม่ ระดับน้ำที่เข้ากันที่สุด แบบจำลองที่ระดับนั้น และค่าความสอดคล้อง (IoU)",
        f"{fixed(radar['newly_dark_km2'], 2)} km²; {fixed(radar['best_fit_stage_m'], 2)} m; {fixed(radar['best_fit_model_km2'], 2)} km²; IoU {fixed(radar['iou_at_best_fit'], 3)}",
        exact({key: radar[key] for key in ("newly_dark_km2", "best_fit_stage_m", "best_fit_model_km2", "iou_at_best_fit", "threshold_db_dn")}), "CAL", "timeline.json $.s1_anchor"))
    for item in radar.get("sensitivity", []):
        images = item["images"]
        figures.append(Figure(
            f"cal.s1_{item['id']}", f"Sentinel-1 cross-track pair {iso_stamp(images[0]['local'])} to {iso_stamp(images[-1]['local'])} (sensitivity): the same four figures",
            f"ภาพ Sentinel-1 คู่ต่างวงโคจร {iso_stamp_th(images[0]['local'])} ถึง {iso_stamp_th(images[-1]['local'])} (การทดสอบความไว): ตัวเลขทั้งสี่แบบเดียวกัน",
            f"{fixed(item['newly_dark_km2'], 2)} km²; {fixed(item['best_fit_stage_m'], 2)} m; {fixed(item['best_fit_model_km2'], 2)} km²; IoU {fixed(item['iou_at_best_fit'], 3)}",
            exact({key: item[key] for key in ("newly_dark_km2", "best_fit_stage_m", "best_fit_model_km2", "iou_at_best_fit", "threshold_db_dn")}), "CAL",
            f"timeline.json $.s1_anchor.sensitivity[id={item['id']}]"))
    return Section("calibration", "Calibration anchor and calibration-informed size checks", "จุดอ้างอิงที่ใช้ปรับแบบจำลองและการตรวจสอบขนาดที่มีส่วนในการปรับ",
                   "GISTDA's figure set the onset keyframe, so the model matches it by construction. UNOSAT 3991 was known while the keyframes were tuned and the recession keyframes were tuned to the 16 Sep radar pass, so neither is an independent check. The radar figures constrain size only, not location.",
                   "ตัวเลขของ GISTDA ใช้กำหนดจุดเริ่มน้ำขึ้น แบบจำลองจึงตรงกับตัวเลขนี้โดยการสร้าง ส่วน UNOSAT 3991 เป็นตัวเลขที่ทราบอยู่แล้วขณะปรับจุดกำหนด และจุดกำหนดช่วงน้ำลดปรับให้เข้ากับภาพเรดาร์วันที่ 16 ก.ย. จึงไม่ใช่การตรวจสอบอิสระทั้งคู่ ตัวเลขจากเรดาร์บอกได้เพียงขนาด ไม่ใช่ตำแหน่ง",
                   figures=tuple(figures))


def reported_section(files: ReplayFiles) -> Section:
    block = files.manifest["reported_depths"]
    reports = block["reports"]
    located = [report for report in reports if report.get("point")]
    points = {(report["point"]["lat"], report["point"]["lon"]) for report in located}
    labels = {"numeric": ("Numbers (lower bounds and ranges)", "ตัวเลข (ค่าขั้นต่ำและช่วง)"),
              "qualitative": ("Storey or body references (wet or dry only)", "อ้างอิงชั้นของอาคารหรือระดับร่างกาย (เปียกหรือแห้งเท่านั้น)"),
              "all": (f"All {len(reports)} reports", f"รายงานทั้งหมด {len(reports)} ฉบับ")}
    outcomes = ("consistent", "model_shallower", "model_dry", "not_comparable")
    rows = [tuple([f"{labels[key][0]}<br>{labels[key][1]}", *(str(block["counts"][key][outcome]) for outcome in outcomes)]) for key in ("numeric", "qualitative", "all")]
    rows.append(tuple(["Within each report's location tolerance (sensitivity), all reports<br>ภายในระยะคลาดเคลื่อนของตำแหน่งของแต่ละรายงาน (การทดสอบความไว) ทุกรายงาน",
                       *(str(block["counts_within_tolerance"]["all"][outcome]) for outcome in outcomes)]))
    table = Table("reported.counts", "Reported depths against the model", "ความลึกตามรายงานเทียบกับแบบจำลอง",
                  ("Reports", "Consistent", "Model shallower", "Model dry", "Not comparable"), tuple(rows), "REP",
                  "timeline.json $.reported_depths.counts, .counts_within_tolerance")
    figures = (
        Figure("reported.reports", "News reports of flood depth at named places, 10-13 Sep 2024", "รายงานข่าวความลึกของน้ำ ณ สถานที่ที่ระบุชื่อ 10-13 ก.ย. 2567 (2024)",
               str(len(reports)), exact(len(reports)), "REP", "timeline.json $.reported_depths.reports"),
        Figure("reported.located", "Of those, located at medium or high confidence (distinct map points)", "ในจำนวนนี้ ระบุตำแหน่งได้ที่ความเชื่อมั่นปานกลางหรือสูง (จำนวนจุดบนแผนที่)",
               f"{len(located)} ({len(points)} points)", f"{len(located)}; {len(points)}", "REP", "timeline.json $.reported_depths.reports[*].point"),
    )
    return Section("reported", "Reported depths (news, not surveyed)", "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)",
                   "Anecdotal reports, paraphrased; a consistency check, never used to tune the model and never a validation of it.",
                   "เป็นรายงานจากคำบอกเล่าที่เรียบเรียงใหม่ ใช้ตรวจความสอดคล้อง ไม่เคยใช้ปรับแบบจำลองและไม่ใช่การยืนยันความถูกต้องของแบบจำลอง",
                   figures=figures, tables=(table,))


def exports_section(files: ReplayFiles) -> Section:
    pack = files.manifest["exports"]
    rows = tuple((f"{item['title']['en']}<br>{item['title']['th']}", item["name"], "" if item.get("rows") is None else whole(item["rows"]), f"{whole(item['bytes'])}")
                 for item in pack["files"])
    table = Table("exports.files", f"The export pack: {pack['file_count']} files, {whole(pack['bytes'])} bytes, {pack['licence']}",
                  f"ชุดไฟล์ส่งออก: {pack['file_count']} ไฟล์ {whole(pack['bytes'])} ไบต์ {pack['licence']}",
                  ("File", "Name", "Rows, points or subdistricts", "Bytes"), rows, "SCN", "timeline.json $.exports.files")
    return Section("exports", "Download files (T1 scenario tables)", "ไฟล์ดาวน์โหลด (ตารางสถานการณ์จำลองระดับ T1)",
                   "Modelled, not observed; not an observed closure record and not an official warning. Each file says so in its own header.",
                   "เป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้ ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ ทุกไฟล์ระบุไว้ในส่วนหัวของตนเอง",
                   tables=(table,))


def envelope_section(files: ReplayFiles) -> Section | None:
    envelope = files.envelope
    if envelope is None:
        return None
    names = _names(files)
    comparison = envelope["comparison"]
    area = envelope["area"]
    district = {item["id"]: item for item in comparison["district"]}
    figures = [
        Figure("envelope.area_km2", "Season envelope inside the eight subdistricts (10 m grid); outside mapped channels, the area every comparison uses",
               "ขอบเขตน้ำตลอดฤดูภายในแปดตำบล (กริด 10 ม.) และส่วนที่อยู่นอกร่องน้ำซึ่งใช้ในการเปรียบเทียบทุกค่า",
               f"{fixed(area['district_km2'], 2)} km²; {fixed(district['modelled_peak']['envelope_km2'], 2)} km²",
               exact({"district_km2": area["district_km2"], "on_mapped_channels_km2": area["on_mapped_channels_km2"]}), "SCN-ENV", "envelope.json $.area"),
    ]
    for item in comparison["district"]:
        figures.append(Figure(
            f"envelope.{item['id']}", f"{item['model_extent']} ({fixed(item['model_stage_m'], 2)} m): agreement (IoU); share of the modelled water inside the envelope; share of the envelope the modelled water reaches",
            f"{'ระดับสูงสุดของแบบจำลอง' if item['id'] == 'modelled_peak' else 'ขอบเขตที่ใหญ่ที่สุดของแบบจำลองในช่วง 13-19 ก.ย.'} ({fixed(item['model_stage_m'], 2)} ม.): ค่าความสอดคล้อง (IoU) สัดส่วนน้ำจากแบบจำลองที่อยู่ในขอบเขต และสัดส่วนของขอบเขตที่น้ำจากแบบจำลองไปถึง",
            f"IoU {fixed(item['agreement_iou'], 2)}; {percent(item['containment_model_in_envelope'], 1)}; {percent(item['containment_envelope_in_model'], 1)}",
            exact({key: item[key] for key in ("agreement_iou", "containment_model_in_envelope", "containment_envelope_in_model", "model_km2", "envelope_km2", "overlap_km2")}),
            "SCN-ENV", f"envelope.json $.comparison.district[id={item['id']}]"))
    low = comparison["low_confidence"]
    figures.append(Figure("envelope.low_confidence", "Share inside the envelope: low-confidence modelled water against the other modelled water",
                          "สัดส่วนที่อยู่ในขอบเขต: น้ำจากแบบจำลองที่ความเชื่อมั่นต่ำ เทียบกับน้ำจากแบบจำลองส่วนอื่น",
                          f"{percent(low['share_inside_envelope_low_confidence'], 1)} against {percent(low['share_inside_envelope_other'], 1)}", exact(low), "SCN-ENV",
                          "envelope.json $.comparison.low_confidence"))
    residents = comparison["residents"]
    figures.append(Figure("envelope.residents", "Residents inside the envelope, district total (WorldPop 2020): by cell centre (the planning overlay's rule); by the replay's rule; the modelled peak's residents in water",
                          "ผู้อยู่อาศัยภายในขอบเขต รวมทั้งอำเภอ (WorldPop 2020): ตามจุดกึ่งกลางเซลล์ (กฎของชั้นข้อมูลวางแผน) ตามกฎของการย้อนดู และผู้อยู่อาศัยในน้ำ ณ ระดับสูงสุดของแบบจำลอง",
                          f"about {whole(residents['residents_in_envelope'])}; {whole(residents['residents_in_envelope_replay_rule'])}; {whole(residents['model_residents_in_water'])}",
                          exact({key: residents[key] for key in ("residents_in_envelope", "residents_in_envelope_replay_rule", "model_residents_in_water")}), "SCN-ENV",
                          "envelope.json $.comparison.residents"))
    by_tambon = sorted(comparison["by_tambon"], key=lambda item: -item["agreement_iou"])
    rows = tuple((f"{names[item['tambon_id']][0]}<br>{names[item['tambon_id']][1]}", fixed(item["agreement_iou"], 2), fixed(item["envelope_only_km2"], 1), fixed(item["model_only_km2"], 1))
                 for item in by_tambon)
    table = Table("envelope.by_subdistrict", "Each subdistrict at the modelled peak: where the two differ (the places to check first)",
                  "แต่ละตำบล ณ ระดับสูงสุดของแบบจำลอง: จุดที่ทั้งสองต่างกัน (จุดที่ควรตรวจก่อน)",
                  ("Subdistrict", "Agreement (IoU)", "Envelope water the model does not reach, km²", "Modelled water outside the envelope, km²"), rows, "SCN-ENV",
                  "envelope.json $.comparison.by_tambon")
    credit = envelope["credit"]
    licence = (f"Figures in this section are derived from {credit} and are shared under {envelope['licence']['name']} ({envelope['licence']['url']}). "
               f"{envelope['change_notice']} UNOSAT and GISTDA do not endorse FloodGuard or this use.")
    return Section("envelope", "Season envelope comparison (scenario; plausibility, not validation)", "การเปรียบเทียบกับขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง ดูความเป็นไปได้ ไม่ใช่การยืนยันความถูกต้อง)",
                   "Product 4009 is accumulated water from August to October 2024, a scenario layer and not an observation for any replay day; the modelled peak is illustrative. The figures say where the two differ, not which one is right. The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.",
                   "ผลิตภัณฑ์ 4009 คือน้ำสะสมตั้งแต่สิงหาคมถึงตุลาคม 2567 (2024) เป็นชั้นข้อมูลสถานการณ์จำลอง ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู และระดับสูงสุดของแบบจำลองเป็นเพียงการอธิบาย ตัวเลขบอกว่าทั้งสองต่างกันตรงไหน ไม่ได้บอกว่าอันไหนถูก "
                   "แบบจำลองพื้นผิวความละเอียด 30 ม. ทำให้ระดับพื้นดินในเขตสิ่งปลูกสร้างสูงกว่าจริง น้ำจากแบบจำลองและจำนวนผู้อยู่อาศัยในน้ำในเขตเมืองจึงน่าจะต่ำกว่าความเป็นจริง",
                   figures=tuple(figures), tables=(table,), licence=licence)


SECTION_BUILDERS: tuple[Callable[[ReplayFiles], Section | None], ...] = (
    window_section, demo_hours_section, peak_section, days_section, access_section, capacity_section,
    observed_section, calibration_section, reported_section, envelope_section, exports_section,
)


def replay_numbers(files: ReplayFiles) -> list[Section]:
    """Every section of quotable figures, after checking that the Python rules reproduce the baked day figures."""
    manifest = files.manifest
    if manifest.get("accepted_fpps") is not None or manifest.get("accepted_action_class") is not None:
        raise ReplayNumbersError("the replay must carry no accepted priority score or action class")
    _check_day_stats(manifest)
    return [section for section in (builder(files) for builder in SECTION_BUILDERS) if section is not None]


# --- Rendering -------------------------------------------------------------------------------------------------------


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(_cell(item) for item in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(item) for item in row) + " |" for row in rows]
    return lines


def render_markdown(files: ReplayFiles, sections: Sequence[Section]) -> str:
    """The quotable figures as one Markdown document (LF line endings, ending with a newline)."""
    manifest = files.manifest
    lines = [
        "# Mae Sai replay: figures to quote",
        "",
        "# ตัวเลขของการย้อนดูน้ำท่วมแม่สายสำหรับการนำเสนอ",
        "",
        "Generated by `scripts/build_replay_numbers.py` from the replay files the page serves; do not edit by hand. "
        "After any re-bake, run `.venv/Scripts/python.exe scripts/build_replay_numbers.py` and re-read every figure the deck quotes; "
        "`tests/test_replay_numbers.py` fails until this file matches the files again.",
        "",
        "สร้างโดย `scripts/build_replay_numbers.py` จากไฟล์ของการย้อนดูที่หน้าเว็บใช้ ห้ามแก้ไขด้วยมือ หลังการสร้างข้อมูลใหม่ทุกครั้ง ให้รันสคริปต์นี้แล้วอ่านตัวเลขที่ใช้ในสไลด์ใหม่ทุกตัว",
        "",
        "## Source files and status / ไฟล์ต้นทางและสถานะ",
        "",
    ]
    status = [
        ("Manifest", f"`{files.manifest_path}` (revision {manifest['revision']}, generated {manifest['generated_at']}), SHA-256 `{files.manifest_sha256}`"),
        ("Season envelope statistics", f"`{manifest['season_envelope']['files']['statistics']['href']}`, SHA-256 `{files.envelope_sha256}`" if files.envelope_sha256 else "not shipped"),
        ("Access nodes", f"`{manifest['access']['nodes']['href']}`, SHA-256 `{files.nodes_sha256}`"),
        ("Subdistrict names", f"`{manifest['vectors']['tambons']['href']}`, SHA-256 `{files.tambons_sha256}`"),
        ("Source timestamp", f"`{manifest['source_timestamp']}`"),
        ("Status", f"{manifest['operational_status']}; confidence {manifest['confidence_class']}; official_warning {exact(manifest['official_warning'])}; "
                   f"real_time {exact(manifest['real_time'])}; accepted_fpps {exact(manifest['accepted_fpps'])}; accepted_action_class {exact(manifest['accepted_action_class'])}"),
    ]
    lines += _table(("Item", "Value"), status)
    lines += ["", "Every file except the manifest was checked against the SHA-256 the manifest lists for it.",
              "",
              "No priority score and no action class is computed or quoted for the replay: those belong to the planning overlay. "
              "The figures are not a forecast, not real-time and not an official warning.",
              "",
              "ไม่มีการคำนวณหรืออ้างคะแนนลำดับความสำคัญหรือระดับการดำเนินการสำหรับการย้อนดูนี้ ซึ่งเป็นงานของชั้นข้อมูลวางแผน "
              "ตัวเลขทั้งหมดในนี้ไม่ใช่การพยากรณ์ ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่คำเตือนอย่างเป็นทางการ",
              "",
              "## What to say with each lane / สิ่งที่ต้องพูดกำกับตัวเลขแต่ละกลุ่ม",
              ""]
    lines += _table(("Lane", "Say (English)", "พูด (ไทย)"), [(key, en, th) for key, (en, th) in LANES.items()])
    for section in sections:
        lines += ["", f"## {section.title_en}", "", f"### {section.title_th}", "", section.note_en, "", section.note_th]
        if section.licence:
            lines += ["", f"**Licence and credit.** {section.licence}"]
        if section.figures:
            lines += [""]
            lines += _table(("Key", "Figure", "Quote", "Exact value in the file", "Lane", "Source"),
                            [(f"`{figure.key}`", f"{figure.label_en}<br>{figure.label_th}", figure.quote, f"`{figure.exact}`", figure.lane, figure.source)
                             for figure in section.figures])
        for table in section.tables:
            lines += ["", f"**{table.caption_en}** ({table.lane}; `{table.key}`; source: {table.source})", "", f"{table.caption_th}", ""]
            lines += _table(table.header, table.rows)
    return "\n".join(lines) + "\n"


def build(root: Path) -> str:
    """Render the document for the revision the page serves under ``root``."""
    files = load_replay_files(root)
    return render_markdown(files, replay_numbers(files))
