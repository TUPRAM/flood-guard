"""Judge-readable Mae Sai weak-reference action briefs.

The brief intentionally separates derived Sentinel-1 evidence from decision
context that has not yet been joined. It must never promote a manual
weak-reference mask into official validation truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re

import pandas as pd

from floodguard.briefs import RECOMMENDED_ACTIONS, THAI_RECOMMENDED_ACTIONS


MAE_SAI_WEAK_REFERENCE_WARNING = (
    "Based on weak-reference candidate flood analysis. Non-operational. "
    "Not official warning. Use only for planning/demo."
)

PRIORITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "mean_flood_probability_0_1",
    "flood_likelihood_0_100",
    "exposure_0_100",
    "access_gap_0_100",
    "road_criticality_0_100",
    "vulnerability_context_0_100",
    "confidence_class",
    "source_name",
    "source_timestamp",
    "assumptions",
    "reference_status",
    "context_status",
    "fpps_0_100",
    "action_class",
    "top_reason",
)

FEATURE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "pre_product_id",
    "post_product_id",
    "reference_product_id",
    "reference_status",
    "pre_source_sha256",
    "post_source_sha256",
    "reference_sha256",
    "source_integrity_status",
    "reference_spatial_relation",
    "reference_in_study_area_overlap",
    "reference_distance_to_study_area_km",
    "sample_pixel_count",
    "reference_positive_pixel_count",
    "predicted_positive_pixel_count",
    "mean_flood_probability_0_1",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

BASELINE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "metric_status",
    "pre_source_sha256",
    "post_source_sha256",
    "reference_sha256",
    "source_integrity_status",
    "reference_spatial_relation",
    "reference_in_study_area_overlap",
    "reference_distance_to_study_area_km",
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "area_error_ratio",
    "sample_pixel_count",
    "reference_positive_pixel_count",
    "predicted_positive_pixel_count",
    "probability_threshold",
    "confidence_class",
    "warning_text",
    "assumptions",
)

MANUAL_REFERENCE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "reference_id",
    "reference_mask_status",
    "candidate_readiness_status",
    "not_official_status",
    "sha256",
    "attribute_values_status",
    "spatial_relation",
    "in_study_area_overlap",
    "distance_to_study_area_km",
    "geometry_type",
    "crs",
    "feature_count",
    "allowed_use",
    "not_allowed_use",
)

ML_REQUIRED_COLUMNS: tuple[str, ...] = (
    "model_family",
    "label_status",
    "split_strategy",
    "holdout_sample_count",
    "decision_threshold",
    "baseline_iou",
    "ml_iou",
    "baseline_f1_dice",
    "ml_f1_dice",
    "baseline_precision",
    "ml_precision",
    "baseline_recall",
    "ml_recall",
    "baseline_area_error_ratio",
    "ml_area_error_ratio",
    "can_feed_decision_layer",
    "confidence_class",
    "warning_text",
)

ADM3_SAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "mean_flood_probability_0_1",
    "p90_flood_probability_0_1",
    "binary_flood_share_0_1",
    "sample_pixel_count",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

ROAD_REQUIRED_COLUMNS: tuple[str, ...] = (
    "road_id",
    "subdistrict_id",
    "road_disruption_probability_0_1",
    "top_risk_reason",
)

ACCESS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "people_losing_15_min_access",
    "people_losing_30_min_access",
    "people_losing_60_min_access",
)

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "equity_gap_ratio",
    "interpretation_text",
)


class MaeSaiActionBriefError(ValueError):
    """Raised when Mae Sai action-brief evidence violates its contract."""


def build_mae_sai_action_brief(
    priority: pd.DataFrame,
    sar_feature_manifest: pd.DataFrame,
    baseline_metrics: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    weak_label_ml_metrics: pd.DataFrame | None = None,
    adm3_sar_context: pd.DataFrame | None = None,
    road_risk: pd.DataFrame | None = None,
    access_loss: pd.DataFrame | None = None,
    equity_gap: pd.DataFrame | None = None,
    subdistrict_id: str | None = None,
) -> str:
    """Build a bilingual action brief from derived Mae Sai evidence.

    Missing road, access, or equity frames are rendered as unavailable. Zero
    placeholder FPPS inputs are never described as observed zero impact.
    """

    _require_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    _require_columns(sar_feature_manifest, FEATURE_REQUIRED_COLUMNS, "SAR feature")
    _require_columns(baseline_metrics, BASELINE_REQUIRED_COLUMNS, "baseline metrics")
    _require_columns(
        manual_reference_manifest,
        MANUAL_REFERENCE_REQUIRED_COLUMNS,
        "manual reference",
    )
    _require_non_empty(priority, "priority")
    _require_single_row(sar_feature_manifest, "SAR feature")
    _require_single_row(baseline_metrics, "baseline metrics")
    _require_single_row(manual_reference_manifest, "manual reference")

    selected = _select_priority_row(priority, subdistrict_id)
    feature = sar_feature_manifest.iloc[0]
    baseline = baseline_metrics.iloc[0]
    manual = manual_reference_manifest.iloc[0]
    _validate_weak_reference_evidence(selected, feature, baseline, manual)

    ml: pd.Series | None = None
    if weak_label_ml_metrics is not None:
        _require_columns(weak_label_ml_metrics, ML_REQUIRED_COLUMNS, "weak-label ML")
        _require_single_row(weak_label_ml_metrics, "weak-label ML")
        ml = weak_label_ml_metrics.iloc[0]
        _validate_ml_evidence(ml)

    selected_id = str(selected["subdistrict_id"])
    action_class = str(selected["action_class"])
    if action_class not in RECOMMENDED_ACTIONS:
        raise MaeSaiActionBriefError(f"Unknown action_class value: {action_class}")

    adm3_sar: pd.Series | None = None
    if adm3_sar_context is not None:
        _require_columns(adm3_sar_context, ADM3_SAR_REQUIRED_COLUMNS, "ADM3 SAR")
        matches = adm3_sar_context[
            adm3_sar_context["subdistrict_id"].astype(str) == selected_id
        ]
        if len(matches) != 1:
            raise MaeSaiActionBriefError(
                f"Expected one ADM3 SAR row for {selected_id}; found {len(matches)}."
            )
        adm3_sar = matches.iloc[0]

    probability_source = (
        adm3_sar["mean_flood_probability_0_1"]
        if adm3_sar is not None
        else feature["mean_flood_probability_0_1"]
    )
    mean_probability = _bounded_float(
        probability_source,
        0.0,
        1.0,
        "mean_flood_probability_0_1",
    )
    if abs(
        mean_probability
        - _bounded_float(
            selected["mean_flood_probability_0_1"],
            0.0,
            1.0,
            "priority mean_flood_probability_0_1",
        )
    ) > 0.000001:
        raise MaeSaiActionBriefError(
            "Priority and SAR feature mean flood probabilities do not match."
        )

    road_lines = _road_risk_lines(road_risk, selected_id, selected)
    access_lines = _access_loss_lines(access_loss, selected_id, selected)
    equity_lines = _equity_gap_lines(equity_gap, selected_id, selected)
    district_signal_lines = _district_access_signal_lines(
        access_loss, equity_gap, selected_id
    )
    metric_lines = _candidate_metric_lines(baseline, ml)
    ml_summary_lines = _ml_summary_lines(ml)
    real_context_joined = str(selected["context_status"]).startswith(
        "real_open_context_joined"
    )
    if real_context_joined:
        interpretation_text = (
            "Class E means monitor and verify. Real admin, population, road, facility, "
            "terrain, access, and proxy-equity context is joined, but flood calibration "
            "and operational source verification remain low confidence."
        )
        component_lines = [
            (
                "- Component status: flood likelihood "
                f"{_number(selected['flood_likelihood_0_100'], 'flood likelihood'):.2f}/100; "
                f"relative exposure {_number(selected['exposure_0_100'], 'exposure'):.2f}/100; "
                f"modeled access gap {_number(selected['access_gap_0_100'], 'access gap'):.2f}/100; "
                f"road criticality {_number(selected['road_criticality_0_100'], 'road criticality'):.2f}/100; "
                f"proxy vulnerability {_number(selected['vulnerability_context_0_100'], 'vulnerability context'):.2f}/100."
            ),
            (
                "- These are candidate model outputs from open context sources; they "
                "are not observed emergency impacts or official operational data."
            ),
        ]
        context_action_lines = [
            (
                "- Field-verify the highest-risk OSM road and bridge candidates, and "
                "confirm that mapped facilities are valid emergency destinations."
            ),
            (
                "- ตรวจสอบถนนและสะพาน OSM ที่มีความเสี่ยงสูงในภาคสนาม "
                "และยืนยันว่าสถานที่ที่ทำแผนที่ไว้ใช้เป็นจุดหมายฉุกเฉินได้จริง"
            ),
            (
                "- Replace the terrain/remoteness vulnerability proxy with current "
                "demographic and local-service data before equity decisions."
            ),
            (
                "- แทนที่ตัวแทนความเปราะบางด้านภูมิประเทศและความห่างไกลด้วยข้อมูลประชากร "
                "และบริการท้องถิ่นปัจจุบันก่อนตัดสินใจด้านความเสมอภาค"
            ),
        ]
    else:
        interpretation_text = (
            "Class E means monitor and verify. It does not mean no flood risk; real "
            "administrative, population, road, access, and vulnerability joins are incomplete."
        )
        component_lines = [
            (
                "- Component status: flood likelihood "
                f"{_number(selected['flood_likelihood_0_100'], 'flood likelihood'):.2f}/100; "
                f"exposure proxy {_number(selected['exposure_0_100'], 'exposure'):.2f}/100."
            ),
            (
                "- Access gap, road criticality, and vulnerability/context are "
                "unjoined placeholders in this run, not measured zero impact."
            ),
        ]
        context_action_lines = [
            (
                "- Join real admin boundaries, population, roads, facilities, terrain, "
                "and vulnerability data before revising FPPS or planning routes and shelters."
            ),
            (
                "- เชื่อมข้อมูลเขตการปกครอง ประชากร ถนน สถานบริการ ภูมิประเทศ และกลุ่มเปราะบางจริง "
                "ก่อนปรับ FPPS หรือวางแผนเส้นทางและศูนย์พักพิง"
            ),
        ]
    if adm3_sar is not None:
        sample_pixel_count = _integer(adm3_sar["sample_pixel_count"], "ADM3 sample pixels")
        predicted_positive_pixel_count = round(
            _bounded_float(
                adm3_sar["binary_flood_share_0_1"],
                0.0,
                1.0,
                "ADM3 binary flood share",
            )
            * sample_pixel_count
        )
        evidence_scope = "inside the HDX COD-AB ADM3 candidate aggregation unit"
        reference_status_text = (
            "manual cross-border weak-reference candidate used for calibration only; "
            "it does not overlap the Thailand ADM3 candidate geometry"
        )
        geometry_status_text = (
            "Current geometry is an HDX COD-AB ADM3 boundary; flood calibration still "
            "depends on a nearby cross-border manual weak reference."
        )
    else:
        sample_pixel_count = _integer(feature["sample_pixel_count"], "sample pixels")
        predicted_positive_pixel_count = _integer(
            feature["predicted_positive_pixel_count"], "predicted positive pixels"
        )
        evidence_scope = "inside the weak-reference review sample"
        reference_status_text = (
            "manually digitized weak-reference candidate; not official validation "
            "truth and not field validated"
        )
        geometry_status_text = (
            "Current geometry is a weak-reference review area, not a confirmed "
            "agency-confirmed subdistrict boundary."
        )

    lines = [
        (
            "# Mae Sai Weak-Reference Action Brief - "
            f"{selected['subdistrict_name']} ({selected_id})"
        ),
        "",
        (
            "> **Safety status / สถานะความปลอดภัย:** "
            f"{MAE_SAI_WEAK_REFERENCE_WARNING}"
        ),
        "",
        "## Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ",
        "",
        (
            f"- **Decision / ข้อสรุป:** Class {action_class} - "
            f"{RECOMMENDED_ACTIONS[action_class]} FPPS is "
            f"{_number(selected['fpps_0_100'], 'fpps_0_100'):.2f}/100 with "
            f"{selected['confidence_class']} confidence."
        ),
        (
            "- **Evidence / หลักฐาน:** Real CDSE Sentinel-1 pre/post imagery "
            f"produced a mean non-ML flood-probability proxy of {mean_probability:.1%} "
            f"{evidence_scope}."
        ),
        (
            f"- **Interpretation / การตีความ:** {interpretation_text}"
        ),
        *district_signal_lines,
        "",
        "## Priority / ลำดับความสำคัญ",
        "",
        f"- FPPS: {_number(selected['fpps_0_100'], 'fpps_0_100'):.2f}/100",
        f"- Action class: {action_class}",
        f"- Confidence: {selected['confidence_class']}",
        f"- Top reason: {selected['top_reason']}",
        *component_lines,
        "",
        "## Flood Evidence / หลักฐานน้ำท่วม",
        "",
        f"- Source: {selected['source_name']}",
        f"- Pre-event Sentinel-1 product: `{feature['pre_product_id']}`",
        f"- Post-event Sentinel-1 product: `{feature['post_product_id']}`",
        f"- Observation timestamp: {selected['source_timestamp']}",
        f"- Mean flood-probability proxy: {mean_probability:.1%}",
        (
            "- Thresholded flood-positive sample: "
            f"{predicted_positive_pixel_count:,} of {sample_pixel_count:,} pixels."
        ),
        (
            "- Cross-border calibration reference-positive sample: "
            f"{_integer(feature['reference_positive_pixel_count'], 'reference positive pixels'):,} pixels."
        ),
        f"- Reference candidate: `{manual['reference_id']}` ({manual['geometry_type']}, {manual['crs']}).",
        f"- Reference status: {reference_status_text}.",
        "",
        "## Candidate Validation Metrics / ตัวชี้วัดการตรวจสอบแบบอ้างอิงอย่างอ่อน",
        "",
        *metric_lines,
        "",
        *ml_summary_lines,
        "## Likely Road Risks / ความเสี่ยงถนนที่อาจเกิดขึ้น",
        "",
        *road_lines,
        "",
        "## Access Loss / การสูญเสียการเข้าถึง",
        "",
        *access_lines,
        "",
        "## Equity Gap / ช่องว่างความเสมอภาคในการอพยพ",
        "",
        *equity_lines,
        "",
        "## Recommended Local Actions / ข้อเสนอการปฏิบัติในพื้นที่",
        "",
        f"- Policy class guidance: {RECOMMENDED_ACTIONS[action_class]}",
        f"- แนวทางตามระดับนโยบาย: {THAI_RECOMMENDED_ACTIONS[action_class]}",
        (
            "- Verify candidate flood areas against local observations and an "
            "independent reference before any operational decision."
        ),
        (
            "- ตรวจสอบพื้นที่น้ำท่วมที่เป็นผลลัพธ์เบื้องต้นกับข้อมูลภาคสนามและแหล่งอ้างอิงอิสระ "
            "ก่อนใช้ตัดสินใจเชิงปฏิบัติการ"
        ),
        *context_action_lines,
        (
            "- Do not issue warnings, closures, evacuations, or shelter decisions "
            "from this brief alone."
        ),
        (
            "- ห้ามใช้เอกสารฉบับนี้เพียงอย่างเดียวเพื่อออกคำเตือน ปิดถนน สั่งอพยพ "
            "หรือตัดสินใจเปิดศูนย์พักพิง"
        ),
        "",
        "## Assumptions And Limitations / สมมติฐานและข้อจำกัด",
        "",
        f"- {selected['assumptions']}",
        f"- SAR extraction assumption: {feature['assumptions']}",
        f"- Manual-reference allowed use: {manual['allowed_use']}.",
        f"- Manual-reference prohibited use: {manual['not_allowed_use']}.",
        (
            f"- {geometry_status_text}"
        ),
        "- SAR layover/shadow, permanent water, urban double-bounce, manual-mask uncertainty, and date mismatch may affect results.",
        "",
        f"> **Final warning / คำเตือน:** {MAE_SAI_WEAK_REFERENCE_WARNING}",
        "",
    ]
    return "\n".join(lines)


def write_mae_sai_action_brief(
    priority: pd.DataFrame,
    sar_feature_manifest: pd.DataFrame,
    baseline_metrics: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    output_dir: str | Path,
    *,
    weak_label_ml_metrics: pd.DataFrame | None = None,
    adm3_sar_context: pd.DataFrame | None = None,
    road_risk: pd.DataFrame | None = None,
    access_loss: pd.DataFrame | None = None,
    equity_gap: pd.DataFrame | None = None,
    subdistrict_id: str | None = None,
) -> Path:
    """Write one Mae Sai weak-reference action brief and return its path."""

    selected = _select_priority_row(priority, subdistrict_id)
    output_id = str(selected["subdistrict_id"])
    target = Path(output_dir) / f"mae_sai_action_brief_{output_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_mae_sai_action_brief(
            priority,
            sar_feature_manifest,
            baseline_metrics,
            manual_reference_manifest,
            weak_label_ml_metrics=weak_label_ml_metrics,
            adm3_sar_context=adm3_sar_context,
            road_risk=road_risk,
            access_loss=access_loss,
            equity_gap=equity_gap,
            subdistrict_id=output_id,
        ),
        encoding="utf-8",
    )
    return target


def _candidate_metric_lines(
    baseline: pd.Series,
    ml: pd.Series | None,
) -> list[str]:
    lines = [
        (
            "- Cross-border weak-reference full-sample non-ML threshold candidate: "
            f"IoU {_metric(baseline, 'iou'):.3f}; "
            f"F1/Dice {_metric(baseline, 'f1_dice'):.3f}; "
            f"precision {_metric(baseline, 'precision'):.3f}; "
            f"recall {_metric(baseline, 'recall'):.3f}; "
            f"area error {_metric(baseline, 'area_error_ratio'):+.1%}."
        ),
        (
            "- The negative full-sample area error means the threshold baseline "
            "substantially under-detected the manual weak-reference area."
        ),
    ]
    if ml is None:
        lines.append(
            "- Current-pair spatial-holdout ML comparison: unavailable. The legacy "
            "weak-label experiment used the retired COG pair and is intentionally "
            "excluded from this active-source brief."
        )
        return lines

    lines.extend(
        [
            "",
            (
                "- Historical retired-source experiment only: the following two "
                "holdout columns were produced together from the retired COG pair. "
                "They are not comparable to the active original-SAFE baseline above."
            ),
            "",
            "| Historical metric | Retired-pair threshold (holdout) | Retired-pair weak-label logistic (holdout) |",
            "|---|---:|---:|",
            f"| IoU | {_metric(ml, 'baseline_iou'):.3f} | {_metric(ml, 'ml_iou'):.3f} |",
            f"| F1 / Dice | {_metric(ml, 'baseline_f1_dice'):.3f} | {_metric(ml, 'ml_f1_dice'):.3f} |",
            f"| Precision | {_metric(ml, 'baseline_precision'):.3f} | {_metric(ml, 'ml_precision'):.3f} |",
            f"| Recall | {_metric(ml, 'baseline_recall'):.3f} | {_metric(ml, 'ml_recall'):.3f} |",
            (
                "| Area error | "
                f"{_metric(ml, 'baseline_area_error_ratio'):+.1%} | "
                f"{_metric(ml, 'ml_area_error_ratio'):+.1%} |"
            ),
            "",
            (
                "- Within that historical retired-pair experiment, the ML candidate "
                "improved overlap and recall, but its positive area error shows severe "
                "overprediction. It is report-only screening evidence, not a current-pair "
                "result or confirmed flood extent."
            ),
        ]
    )
    return lines


def _ml_summary_lines(ml: pd.Series | None) -> list[str]:
    if ml is None:
        return []
    can_feed = _strict_bool(
        ml["can_feed_decision_layer"], "ML can_feed_decision_layer"
    )
    return [
        "## Historical Weak-Label ML Cross-Check / การตรวจสอบด้วย ML ป้ายกำกับอย่างอ่อน (ข้อมูลเดิม)",
        "",
        f"- Model: {ml['model_family']} with {ml['split_strategy']}.",
        f"- Holdout sample: {_integer(ml['holdout_sample_count'], 'holdout sample count'):,} pixels.",
        f"- Candidate decision threshold: {_metric(ml, 'decision_threshold'):.2f}.",
        (
            "- Decision-layer eligibility flag: "
            f"{str(can_feed).lower()}; the current FPPS uses the active original-SAFE "
            "non-ML mean probability proxy and has not been rescored from this "
            "retired-pair ML output."
        ),
        f"- Warning: {ml['warning_text']}",
        "",
    ]


def _road_risk_lines(
    road_risk: pd.DataFrame | None,
    selected_id: str,
    selected: pd.Series,
) -> list[str]:
    if road_risk is None:
        return [
            "- Unavailable: no real Mae Sai road segments have been joined.",
            (
                "- The FPPS road-criticality value of "
                f"{_number(selected['road_criticality_0_100'], 'road criticality'):.2f}/100 "
                "is an unjoined placeholder, not evidence that roads are safe."
            ),
        ]
    _require_columns(road_risk, ROAD_REQUIRED_COLUMNS, "road risk")
    rows = road_risk[road_risk["subdistrict_id"].astype(str) == selected_id].copy()
    if rows.empty:
        return ["- Unavailable: no real road-risk row matches this review area."]
    rows["road_disruption_probability_0_1"] = pd.to_numeric(
        rows["road_disruption_probability_0_1"], errors="coerce"
    )
    if rows["road_disruption_probability_0_1"].isna().any():
        raise MaeSaiActionBriefError(
            "road_disruption_probability_0_1 must be numeric."
        )
    rows = rows.sort_values(
        ["road_disruption_probability_0_1", "road_id"],
        ascending=[False, True],
    )
    lines: list[str] = []
    for _, row in rows.head(3).iterrows():
        name = str(row.get("osm_name", "")).strip()
        label = (
            f"{name} (`{row['road_id']}`)"
            if name
            else f"OSM way `{row['road_id']}`"
        )
        bridge = (
            " bridge-tagged;"
            if _strict_bool(row.get("bridge_flag", False), "road bridge_flag")
            else ""
        )
        lines.append(
            f"- {label}: {float(row['road_disruption_probability_0_1']):.1%} "
            f"candidate risk;{bridge} {row['top_risk_reason']}"
        )
    return lines


def _access_loss_lines(
    access_loss: pd.DataFrame | None,
    selected_id: str,
    selected: pd.Series,
) -> list[str]:
    if access_loss is None:
        return [
            "- Unavailable: no real Mae Sai routing graph, facilities, or population nodes have been joined.",
            (
                "- The FPPS access-gap value of "
                f"{_number(selected['access_gap_0_100'], 'access gap'):.2f}/100 "
                "is an unjoined placeholder, not evidence of uninterrupted access."
            ),
        ]
    _require_columns(access_loss, ACCESS_REQUIRED_COLUMNS, "access loss")
    rows = access_loss[access_loss["subdistrict_id"].astype(str) == selected_id]
    if rows.empty:
        return ["- Unavailable: no real access-loss row matches this review area."]
    row = rows.iloc[0]
    return [
        f"- People losing 15-minute access: {_population_count(row['people_losing_15_min_access'], '15-minute access loss')}",
        f"- People losing 30-minute access: {_population_count(row['people_losing_30_min_access'], '30-minute access loss')}",
        f"- People losing 60-minute access: {_population_count(row['people_losing_60_min_access'], '60-minute access loss')}",
    ]


def _equity_gap_lines(
    equity_gap: pd.DataFrame | None,
    selected_id: str,
    selected: pd.Series,
) -> list[str]:
    if equity_gap is None:
        return [
            "- Unavailable: vulnerable and non-vulnerable access-loss denominators are not yet joined.",
            (
                "- The FPPS vulnerability/context value of "
                f"{_number(selected['vulnerability_context_0_100'], 'vulnerability context'):.2f}/100 "
                "is an unjoined placeholder, not evidence of no equity gap."
            ),
        ]
    _require_columns(equity_gap, EQUITY_REQUIRED_COLUMNS, "equity gap")
    rows = equity_gap[equity_gap["subdistrict_id"].astype(str) == selected_id]
    if rows.empty:
        return ["- Unavailable: no real equity-gap row matches this review area."]
    row = rows.iloc[0]
    ratio = "unavailable" if pd.isna(row["equity_gap_ratio"]) else f"{_number(row['equity_gap_ratio'], 'equity gap ratio'):.3f}"
    lines = [
        f"- Equity gap ratio: {ratio}",
        f"- Interpretation: {row['interpretation_text']}",
    ]
    definition = str(row.get("vulnerability_definition", "")).strip()
    if definition:
        lines.append(f"- Vulnerability basis: {definition}.")
    return lines


def _district_access_signal_lines(
    access_loss: pd.DataFrame | None,
    equity_gap: pd.DataFrame | None,
    selected_id: str,
) -> list[str]:
    if access_loss is None or equity_gap is None:
        return []
    if "people_losing_30_min_access" not in access_loss.columns:
        return []
    frame = access_loss.copy()
    frame["people_losing_30_min_access"] = pd.to_numeric(
        frame["people_losing_30_min_access"], errors="coerce"
    )
    if frame["people_losing_30_min_access"].isna().all():
        return []
    row = frame.sort_values(
        ["people_losing_30_min_access", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]
    loss = float(row["people_losing_30_min_access"])
    if loss <= 0 or str(row["subdistrict_id"]) == selected_id:
        return []
    equity_matches = equity_gap[
        equity_gap["subdistrict_id"].astype(str) == str(row["subdistrict_id"])
    ]
    ratio_text = "unavailable"
    if (
        not equity_matches.empty
        and not pd.isna(equity_matches.iloc[0]["equity_gap_ratio"])
    ):
        ratio_text = f"{float(equity_matches.iloc[0]['equity_gap_ratio']):.3f}"
    return [
        (
            "- **District cross-check / การตรวจสอบระดับอำเภอ:** "
            f"{row['subdistrict_name']} has the highest modeled 30-minute access loss "
            f"({loss:,.0f} people) and proxy equity-gap ratio {ratio_text}."
        )
    ]


def _select_priority_row(
    priority: pd.DataFrame,
    subdistrict_id: str | None,
) -> pd.Series:
    _require_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    _require_non_empty(priority, "priority")
    frame = priority.copy()
    frame["fpps_0_100"] = pd.to_numeric(frame["fpps_0_100"], errors="coerce")
    if frame["fpps_0_100"].isna().any():
        raise MaeSaiActionBriefError("priority fpps_0_100 must be numeric.")
    if subdistrict_id is None:
        return frame.sort_values(
            ["fpps_0_100", "subdistrict_id"], ascending=[False, True]
        ).iloc[0]
    matches = frame[frame["subdistrict_id"].astype(str) == subdistrict_id]
    if matches.empty:
        raise MaeSaiActionBriefError(
            f"No priority row found for subdistrict_id: {subdistrict_id}"
        )
    return matches.iloc[0]


def _validate_weak_reference_evidence(
    selected: pd.Series,
    feature: pd.Series,
    baseline: pd.Series,
    manual: pd.Series,
) -> None:
    if not str(selected["reference_status"]).startswith("weak_reference_candidate"):
        raise MaeSaiActionBriefError(
            "priority reference_status must remain a weak-reference candidate."
        )
    if str(feature["reference_status"]) != "weak_reference_candidate":
        raise MaeSaiActionBriefError(
            "SAR feature reference_status must be weak_reference_candidate."
        )
    if str(manual["reference_mask_status"]) != "weak_reference_candidate":
        raise MaeSaiActionBriefError(
            "manual reference status must be weak_reference_candidate."
        )
    if str(manual["candidate_readiness_status"]) != "ready_for_candidate_metrics":
        raise MaeSaiActionBriefError(
            "manual reference must be ready_for_candidate_metrics."
        )
    if str(manual["not_official_status"]) != "confirmed_true":
        raise MaeSaiActionBriefError(
            "manual reference not_official_status must be confirmed_true."
        )
    if str(baseline["metric_status"]) != "candidate_cross_border_calibration_metrics":
        raise MaeSaiActionBriefError(
            "baseline metric_status must be candidate_cross_border_calibration_metrics."
        )
    for column in ("pre_product_id", "post_product_id", "reference_product_id"):
        if not str(feature[column]).strip():
            raise MaeSaiActionBriefError(f"SAR feature {column} must not be blank.")
    if str(feature["reference_product_id"]) != str(manual["reference_id"]):
        raise MaeSaiActionBriefError(
            "SAR feature and manual-reference ids do not match."
        )
    if str(feature["source_integrity_status"]) != "verified_sha256_before_raster_read":
        raise MaeSaiActionBriefError(
            "SAR feature source integrity must be verified before raster reads."
        )
    if str(baseline["source_integrity_status"]) != "verified_sha256_before_raster_read":
        raise MaeSaiActionBriefError(
            "Baseline source integrity must be verified before raster reads."
        )
    for column in ("pre_source_sha256", "post_source_sha256", "reference_sha256"):
        feature_hash = _sha256(feature[column], f"SAR feature {column}")
        baseline_hash = _sha256(baseline[column], f"baseline {column}")
        if feature_hash != baseline_hash:
            raise MaeSaiActionBriefError(
                f"Baseline and SAR feature {column} lineage do not match."
            )
    if _sha256(manual["sha256"], "manual reference sha256") != _sha256(
        feature["reference_sha256"], "SAR feature reference_sha256"
    ):
        raise MaeSaiActionBriefError(
            "SAR feature and manual-reference SHA-256 values do not match."
        )
    if str(manual["attribute_values_status"]) != "valid":
        raise MaeSaiActionBriefError("Manual-reference attributes must be valid.")
    for evidence in (feature, baseline):
        if str(evidence["reference_spatial_relation"]) != "cross_border_calibration_only":
            raise MaeSaiActionBriefError(
                "Weak-reference evidence must retain cross-border calibration scope."
            )
        if _strict_bool(
            evidence["reference_in_study_area_overlap"],
            "reference_in_study_area_overlap",
        ):
            raise MaeSaiActionBriefError(
                "Cross-border weak-reference evidence cannot claim Mae Sai overlap."
            )
    if str(manual["spatial_relation"]) != "cross_border_calibration_only" or _strict_bool(
        manual["in_study_area_overlap"], "manual in_study_area_overlap"
    ):
        raise MaeSaiActionBriefError(
            "Manual reference must retain verified cross-border non-overlap status."
        )
    if str(feature["source_timestamp"]) != str(selected["source_timestamp"]):
        raise MaeSaiActionBriefError(
            "Priority and SAR feature source timestamps do not match."
        )
    sample_pixels = _integer(feature["sample_pixel_count"], "feature sample pixels")
    reference_pixels = _integer(
        feature["reference_positive_pixel_count"],
        "feature reference positive pixels",
    )
    predicted_pixels = _integer(
        feature["predicted_positive_pixel_count"],
        "feature predicted positive pixels",
    )
    if reference_pixels > sample_pixels or predicted_pixels > sample_pixels:
        raise MaeSaiActionBriefError(
            "Feature positive-pixel counts cannot exceed sample_pixel_count."
        )
    baseline_sample_pixels = _integer(
        baseline["sample_pixel_count"], "baseline sample pixels"
    )
    baseline_reference_pixels = _integer(
        baseline["reference_positive_pixel_count"],
        "baseline reference positive pixels",
    )
    baseline_predicted_pixels = _integer(
        baseline["predicted_positive_pixel_count"],
        "baseline predicted positive pixels",
    )
    if (
        baseline_sample_pixels != sample_pixels
        or baseline_reference_pixels != reference_pixels
        or baseline_predicted_pixels != predicted_pixels
    ):
        raise MaeSaiActionBriefError(
            "Baseline and SAR feature pixel counts do not reconcile."
        )
    for column in ("iou", "f1_dice", "precision", "recall", "probability_threshold"):
        _bounded_float(baseline[column], 0.0, 1.0, f"baseline {column}")
    if "not official" not in str(baseline["warning_text"]).lower():
        raise MaeSaiActionBriefError(
            "baseline warning_text must preserve not-official wording."
        )


def _validate_ml_evidence(ml: pd.Series) -> None:
    if str(ml["label_status"]) != "weak_label_not_official_not_field_validated":
        raise MaeSaiActionBriefError(
            "ML label_status must remain weak_label_not_official_not_field_validated."
        )
    warning = str(ml["warning_text"]).lower()
    if "not official labels" not in warning or "not field validation" not in warning:
        raise MaeSaiActionBriefError(
            "ML warning_text must preserve weak-label limitations."
        )
    if _strict_bool(ml["can_feed_decision_layer"], "ML can_feed_decision_layer"):
        raise MaeSaiActionBriefError(
            "Weak-label ML can_feed_decision_layer must remain false; weak-source "
            "metrics cannot authorize FPPS or decision-layer use."
        )
    for column in (
        "decision_threshold",
        "baseline_iou",
        "ml_iou",
        "baseline_f1_dice",
        "ml_f1_dice",
        "baseline_precision",
        "ml_precision",
        "baseline_recall",
        "ml_recall",
    ):
        _bounded_float(ml[column], 0.0, 1.0, f"weak-label ML {column}")
    if _integer(ml["holdout_sample_count"], "ML holdout sample count") <= 0:
        raise MaeSaiActionBriefError(
            "ML holdout_sample_count must be greater than zero."
        )


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise MaeSaiActionBriefError(
            f"Missing required {label} column(s): {', '.join(missing)}"
        )


def _require_non_empty(frame: pd.DataFrame, label: str) -> None:
    if frame.empty:
        raise MaeSaiActionBriefError(f"{label} must contain at least one row.")


def _require_single_row(frame: pd.DataFrame, label: str) -> None:
    if len(frame) != 1:
        raise MaeSaiActionBriefError(f"{label} must contain exactly one row.")


def _metric(row: pd.Series, column: str) -> float:
    return _number(row[column], column)


def _bounded_float(value: object, lower: float, upper: float, label: str) -> float:
    numeric = _number(value, label)
    if numeric < lower or numeric > upper:
        raise MaeSaiActionBriefError(
            f"{label} must be between {lower:g} and {upper:g}."
        )
    return numeric


def _number(value: object, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise MaeSaiActionBriefError(f"{label} must be numeric.") from exc
    if pd.isna(numeric):
        raise MaeSaiActionBriefError(f"{label} must be numeric.")
    return numeric


def _integer(value: object, label: str) -> int:
    numeric = _number(value, label)
    if numeric < 0 or not numeric.is_integer():
        raise MaeSaiActionBriefError(f"{label} must be a non-negative integer.")
    return int(numeric)


def _population_count(value: object, label: str) -> str:
    numeric = _number(value, label)
    if numeric < 0:
        raise MaeSaiActionBriefError(f"{label} must be non-negative.")
    return f"{numeric:,.0f}"


def _strict_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise MaeSaiActionBriefError(f"{label} must be explicit true or false.")


def _sha256(value: object, label: str) -> str:
    normalized = str(value).strip()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise MaeSaiActionBriefError(f"{label} must be a lowercase SHA-256 digest.")
    return normalized
