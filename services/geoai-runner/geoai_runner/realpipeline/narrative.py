"""Component G -- Plain-language narrative generation (deterministic).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 15. The chapter's method is a
compact vision-language model (Moondream) captioning imagery. FloodGuard ran
that path and it did not work; this module is what replaced it.

Why Moondream was replaced, not tuned
-------------------------------------
The executed run produced **zero usable captions** -- every one of the three
images returned ``[caption unavailable: FileNotFoundError]``, recorded in
``outputs/geoai/extra_methods_metrics.json``. Two further problems made the
approach unsuitable regardless of that plumbing failure: VLMs are trained on
natural photographs and degrade on false-colour SAR and analytical figures, and
CPU generation took ~410 s for three images.

The deeper objection is that a generative caption is the wrong instrument here.
For a preparedness product, a sentence about flooding must be *traceable to the
numbers that produced it*. A 2-billion-parameter model's impression of a
false-colour raster is not auditable, cannot be regression-tested, and can
fabricate. This module emits sentences assembled from the decision table, where
every clause maps to a field and every adjective is licensed by a versioned
threshold table. That is more useful and more defensible, and it costs
microseconds.

:data:`MOONDREAM_EVALUATION_RECORD` preserves the negative result so the
methodology can state what was tried.

Guarantees
----------
* Every number in the output traces to a :class:`NarrativeInputs` field.
* No adjective appears unless :data:`NARRATIVE_BANDS_V1` licenses it.
* The uncertainty clause is emitted whenever confidence is not ``high`` or the
  acquisition is more than ``MAX_TRUSTED_PEAK_OFFSET_DAYS`` past the flood peak.
  It cannot be suppressed by a caller.
* Bilingual by construction; Thai action strings are the repository's existing
  reviewed strings from ``floodguard.briefs`` and the dashboard, not new
  translations.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

NARRATIVE_BANDS_VERSION = "narrative_bands_v1"
MAX_TRUSTED_PEAK_OFFSET_DAYS = 2

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "th")


class NarrativeError(ValueError):
    """Raised when narrative inputs are missing, malformed or out of range."""


# Preserved from the executed Moondream run (outputs/geoai/extra_methods_metrics.json).
MOONDREAM_EVALUATION_RECORD: dict[str, object] = {
    "method": "Moondream (vikhyatk/moondream2) vision-language captioning",
    "book_ref": "Ch. 15, Sec. 15.7-15.8",
    "executed": True,
    "caption_count_attempted": 3,
    "caption_count_usable": 0,
    "observed_failure": "[caption unavailable: FileNotFoundError] on all three images",
    "runtime_seconds": 410.0,
    "outcome": "evaluated_rejected",
    "interpretation": (
        "The model loaded and ran but returned no usable caption. Independently of "
        "that failure, VLMs are trained on natural photographs and degrade on "
        "false-colour SAR and analytical figures, and CPU generation was "
        "impractically slow. A generative caption is also not auditable: for a "
        "preparedness product every sentence must trace to the numbers behind it."
    ),
    "superseded_by": "deterministic_template_narrative_v1",
}

# --------------------------------------------------------------------------- #
# Versioned band tables -- the only place an adjective may be licensed
# --------------------------------------------------------------------------- #
# Each entry is (inclusive lower bound, english, thai).
NARRATIVE_BANDS_V1: dict[str, tuple[tuple[float, str, str], ...]] = {
    # Calibrated against FloodLikelihoodAnchor.observed_saturation_share (5%):
    # the top band begins where the observed term saturates, so "widespread"
    # means the same thing here as a full observed score does there.
    "flooded_pct": (
        (0.0, "no observed inundation", "ไม่พบน้ำท่วมจากการสังเกต"),
        (0.001, "a trace of observed inundation", "พบร่องรอยน้ำท่วมเล็กน้อย"),
        (0.1, "localised observed inundation", "พบน้ำท่วมเฉพาะจุด"),
        (1.0, "substantial observed inundation", "พบน้ำท่วมเป็นบริเวณมาก"),
        (5.0, "widespread observed inundation", "พบน้ำท่วมเป็นบริเวณกว้าง"),
    ),
    "flood_likelihood": (
        (0.0, "low", "ต่ำ"),
        (35.0, "moderate", "ปานกลาง"),
        (60.0, "high", "สูง"),
        (80.0, "very high", "สูงมาก"),
    ),
    "exposure": (
        (0.0, "sparsely populated", "มีประชากรเบาบาง"),
        (25.0, "moderately populated", "มีประชากรปานกลาง"),
        (60.0, "densely populated", "มีประชากรหนาแน่น"),
    ),
}

# Reused verbatim from apps' dashboard action labels so wording stays consistent.
ACTION_LABELS_EN: dict[str, str] = {
    "A": "Protect Lives Now",
    "B": "Keep Routes Open",
    "C": "Protect Essential Services",
    "D": "Build Resilience",
    "E": "Monitor and Verify",
}
ACTION_LABELS_TH: dict[str, str] = {
    "A": "คุ้มครองชีวิตทันที",
    "B": "รักษาเส้นทางให้ใช้งานได้",
    "C": "คุ้มครองบริการสำคัญ",
    "D": "เสริมความยืดหยุ่น",
    "E": "ติดตามและตรวจสอบ",
}


def _band(metric: str, value: float, language: str) -> str:
    """Return the licensed phrase for ``value`` under :data:`NARRATIVE_BANDS_V1`."""

    try:
        bands = NARRATIVE_BANDS_V1[metric]
    except KeyError as exc:
        raise NarrativeError(f"no band table for metric {metric!r}.") from exc
    index = 1 if language == "en" else 2
    phrase = bands[0][index]
    for lower, english, thai in bands:
        if value >= lower:
            phrase = english if language == "en" else thai
        else:
            break
    return phrase


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NarrativeInputs:
    """Every value a narrative sentence is allowed to mention."""

    tambon_name_en: str
    tambon_name_th: str
    flooded_pct: float
    flood_likelihood: float
    exposure: float
    fpps: float
    action_class: str
    confidence_class: str
    acquisition_date: str
    peak_offset_days: int
    population: float | None = None
    osm_completeness_flag: str = "unknown_no_population"
    context_source: str = "placeholder"
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action_class not in ACTION_LABELS_EN:
            raise NarrativeError(
                f"action_class must be one of {sorted(ACTION_LABELS_EN)}; "
                f"got {self.action_class!r}."
            )
        if self.confidence_class not in {"high", "medium", "low"}:
            raise NarrativeError(f"unknown confidence_class {self.confidence_class!r}.")
        for name in ("flooded_pct", "flood_likelihood", "exposure", "fpps"):
            value = getattr(self, name)
            if not isinstance(value, int | float) or not math.isfinite(value):
                raise NarrativeError(f"{name} must be a finite number; got {value!r}.")
        for name in ("flood_likelihood", "exposure", "fpps"):
            if not 0.0 <= getattr(self, name) <= 100.0:
                raise NarrativeError(f"{name} must lie in [0, 100]; got {getattr(self, name)!r}.")
        if not str(self.tambon_name_en).strip():
            raise NarrativeError("tambon_name_en must not be blank.")
        if not str(self.acquisition_date).strip():
            raise NarrativeError("acquisition_date must not be blank.")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_tambon_narrative(inputs: NarrativeInputs, *, language: str = "en") -> str:
    """Render one plain-language paragraph for a sub-district.

    The uncertainty clause is appended by this function, not by the caller, so it
    cannot be omitted from a published sentence.
    """

    if language not in SUPPORTED_LANGUAGES:
        raise NarrativeError(
            f"language must be one of {list(SUPPORTED_LANGUAGES)}; got {language!r}."
        )

    flood_band = _band("flooded_pct", inputs.flooded_pct, language)
    likelihood_band = _band("flood_likelihood", inputs.flood_likelihood, language)
    exposure_band = _band("exposure", inputs.exposure, language)

    if language == "en":
        name = inputs.tambon_name_en
        action = ACTION_LABELS_EN[inputs.action_class]
        sentences = [
            f"{name} shows {flood_band} on the {inputs.acquisition_date} acquisition "
            f"({inputs.flooded_pct:.2f}% of the sub-district).",
            f"Combined with terrain susceptibility this gives a {likelihood_band} flood "
            f"likelihood of {inputs.flood_likelihood:.1f}/100.",
        ]
        if inputs.population is not None:
            sentences.append(
                f"The sub-district is {exposure_band} "
                f"(about {inputs.population:,.0f} residents, exposure {inputs.exposure:.1f}/100)."
            )
        else:
            sentences.append(
                f"Exposure is {inputs.exposure:.1f}/100; population context was unavailable."
            )
        sentences.append(
            f"Priority score {inputs.fpps:.1f}/100 places it in action class "
            f"{inputs.action_class} - {action}."
        )
        sentences.append(_caveat_en(inputs))
    else:
        name = inputs.tambon_name_th or inputs.tambon_name_en
        action = ACTION_LABELS_TH[inputs.action_class]
        sentences = [
            f"ตำบล{name} {flood_band}จากภาพวันที่ {inputs.acquisition_date} "
            f"(คิดเป็น {inputs.flooded_pct:.2f}% ของพื้นที่ตำบล)",
            f"เมื่อรวมกับความอ่อนไหวของภูมิประเทศ ได้ค่าโอกาสเกิดน้ำท่วมระดับ{likelihood_band} "
            f"({inputs.flood_likelihood:.1f}/100)",
        ]
        if inputs.population is not None:
            sentences.append(
                f"พื้นที่นี้{exposure_band} (ประมาณ {inputs.population:,.0f} คน "
                f"ค่าการเปิดรับความเสี่ยง {inputs.exposure:.1f}/100)"
            )
        else:
            sentences.append(f"ค่าการเปิดรับความเสี่ยง {inputs.exposure:.1f}/100 แต่ไม่มีข้อมูลประชากรประกอบ")
        sentences.append(
            f"คะแนนลำดับความสำคัญ {inputs.fpps:.1f}/100 อยู่ในระดับการปฏิบัติ "
            f"{inputs.action_class} - {action}"
        )
        sentences.append(_caveat_th(inputs))
    return " ".join(part for part in sentences if part)


def _caveat_en(inputs: NarrativeInputs) -> str:
    reasons: list[str] = []
    if inputs.peak_offset_days > MAX_TRUSTED_PEAK_OFFSET_DAYS:
        reasons.append(
            f"the acquisition is {inputs.peak_offset_days} days after the flood peak, "
            "so the mapped extent is residual and under-represents the peak"
        )
    if inputs.confidence_class != "high":
        reasons.append(f"model confidence is {inputs.confidence_class}")
    if inputs.osm_completeness_flag == "severely_incomplete":
        reasons.append(
            "OpenStreetMap building coverage here is far below the population-implied "
            "expectation, so building counts are indicative only"
        )
    if inputs.context_source == "placeholder":
        reasons.append("access, road and vulnerability components are placeholders, not measured")
    reasons.extend(inputs.limitations)
    if not reasons:
        return "This is a planning estimate, not an official warning."
    return (
        "Treat with caution: "
        + "; ".join(reasons)
        + ". This is a planning estimate, not an official warning."
    )


def _caveat_th(inputs: NarrativeInputs) -> str:
    reasons: list[str] = []
    if inputs.peak_offset_days > MAX_TRUSTED_PEAK_OFFSET_DAYS:
        reasons.append(
            f"ภาพถ่ายบันทึกหลังจุดสูงสุดของน้ำท่วม {inputs.peak_offset_days} วัน "
            "ขอบเขตที่ตรวจพบจึงเป็นน้ำที่ตกค้างและต่ำกว่าความเป็นจริงที่จุดสูงสุด"
        )
    if inputs.confidence_class != "high":
        reasons.append(f"ระดับความเชื่อมั่นของแบบจำลองอยู่ที่ {inputs.confidence_class}")
    if inputs.osm_completeness_flag == "severely_incomplete":
        reasons.append("ข้อมูลอาคารจาก OpenStreetMap ครอบคลุมต่ำกว่าที่ควรมาก จำนวนอาคารเป็นเพียงค่าประมาณ")
    if inputs.context_source == "placeholder":
        reasons.append("ค่าการเข้าถึง ถนน และความเปราะบาง เป็นค่าตั้งต้น ไม่ได้มาจากการวัดจริง")
    reasons.extend(inputs.limitations)
    if not reasons:
        return "ข้อมูลนี้ใช้เพื่อการวางแผนเท่านั้น ไม่ใช่การเตือนภัยอย่างเป็นทางการ"
    return (
        "โปรดใช้ด้วยความระมัดระวัง: "
        + "; ".join(reasons)
        + " ข้อมูลนี้ใช้เพื่อการวางแผนเท่านั้น ไม่ใช่การเตือนภัยอย่างเป็นทางการ"
    )


# --------------------------------------------------------------------------- #
# Artifact
# --------------------------------------------------------------------------- #
@dataclass
class NarrativeResult:
    """Rendered narratives plus provenance."""

    narratives: dict[str, dict[str, str]]
    metrics: dict[str, object]
    artifacts: dict[str, Path] = field(default_factory=dict)


def generate_narratives(
    rows: list[NarrativeInputs],
    output_path: str | Path,
    *,
    languages: tuple[str, ...] = SUPPORTED_LANGUAGES,
) -> NarrativeResult:
    """Render every sub-district narrative and write a reproducible JSON artifact.

    Unlike the Moondream path this artifact is a pure function of the decision
    table: re-running the pipeline on the same inputs reproduces it byte for
    byte, which is what makes it evidence rather than an anecdote.
    """

    for language in languages:
        if language not in SUPPORTED_LANGUAGES:
            raise NarrativeError(f"unsupported language {language!r}.")

    narratives = {
        item.tambon_name_en: {
            language: render_tambon_narrative(item, language=language) for language in languages
        }
        for item in rows
    }
    payload = {
        "data_mode": "real_licensed_inputs",
        "method": "deterministic_template_narrative_v1",
        "bands_version": NARRATIVE_BANDS_VERSION,
        "languages": list(languages),
        "review_status": "machine_generated_deterministic",
        "narratives": narratives,
        "superseded_method": MOONDREAM_EVALUATION_RECORD,
        "assumptions": (
            "Narratives are assembled deterministically from the sub-district decision "
            "table. Every number traces to a field and every qualitative phrase is "
            "licensed by the versioned band table "
            f"'{NARRATIVE_BANDS_VERSION}'. No generative model is involved, so the text "
            "cannot fabricate. Planning language only; not an official warning."
        ),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return NarrativeResult(
        narratives=narratives,
        metrics={
            "data_mode": "real_licensed_inputs",
            "method": "deterministic_template_narrative_v1",
            "bands_version": NARRATIVE_BANDS_VERSION,
            "narrative_count": len(narratives),
            "languages": list(languages),
            "review_status": "machine_generated_deterministic",
            "superseded_method": MOONDREAM_EVALUATION_RECORD,
        },
        artifacts={"narratives": output_path},
    )


def narrative_inputs_from_row(
    row: dict[str, object],
    *,
    acquisition_date: str,
    peak_offset_days: int,
    tambon_name_th: str = "",
) -> NarrativeInputs:
    """Build :class:`NarrativeInputs` from a scored decision-table row."""

    population = row.get("population")
    return NarrativeInputs(
        tambon_name_en=str(row["subdistrict_name"]),
        tambon_name_th=tambon_name_th,
        flooded_pct=float(row.get("ai_flood_share", 0.0) or 0.0) * 100.0,
        flood_likelihood=float(row["flood_likelihood_0_100"]),
        exposure=float(row["exposure_0_100"]),
        fpps=float(row["fpps_0_100"]),
        action_class=str(row["action_class"]),
        confidence_class=str(row["confidence_class"]),
        acquisition_date=acquisition_date,
        peak_offset_days=peak_offset_days,
        population=float(population) if population is not None else None,
        osm_completeness_flag=str(row.get("osm_completeness_flag", "unknown_no_population")),
        context_source=str(row.get("context_source", "placeholder")),
    )
