"""Validation report helpers for FloodGuard outputs."""

from __future__ import annotations

from collections.abc import Sequence
import math
from pathlib import Path
import re

import pandas as pd

from floodguard.ingestion import (
    IngestionPlanError,
    validate_mae_sai_file_manifest_ready,
)
from floodguard.sar_baseline import MASK_METRIC_COLUMNS
from floodguard.sar_raster_extract import (
    SAR_LOG_TRANSFORM,
    SAR_MEASUREMENT_DOMAIN,
    SAR_RADIOMETRIC_CALIBRATION_STATUS,
)

ACTION_PRIORITY: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
ACCESS_THRESHOLDS: tuple[int, ...] = (15, 30, 60)

PRIORITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "fpps_0_100",
    "action_class",
    "confidence_class",
)

ROAD_RISK_REQUIRED_COLUMNS: tuple[str, ...] = (
    "road_id",
    "subdistrict_id",
    "road_disruption_probability_0_1",
)

ACCESS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "people_losing_15_min_access",
    "people_losing_30_min_access",
    "people_losing_60_min_access",
)

EQUITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "equity_gap_ratio",
)

RANK_INSTABILITY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "default_rank",
    "best_rank",
    "worst_rank",
    "rank_range",
    "default_action_class",
    "confidence_class",
    "ranking_unstable",
)

FUTURE_METRIC_PLACEHOLDERS: tuple[str, ...] = (
    "IoU",
    "F1/Dice",
    "precision",
    "recall",
    "area error",
    "Brier score",
    "calibration",
    "road closure precision/recall",
    "score sensitivity",
)


class ValidationReportError(ValueError):
    """Raised when validation-report inputs violate the report contract."""


_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def build_validation_summary(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    rank_instability: pd.DataFrame | None = None,
) -> str:
    """Build a Markdown validation summary from fixture-backed outputs."""

    _validate_columns(priority, PRIORITY_REQUIRED_COLUMNS, "priority")
    _validate_columns(road_risk, ROAD_RISK_REQUIRED_COLUMNS, "road_risk")
    _validate_columns(access_loss, ACCESS_REQUIRED_COLUMNS, "access_loss")
    _validate_columns(equity_gap, EQUITY_REQUIRED_COLUMNS, "equity_gap")

    priority_frame = priority.copy()
    priority_frame["fpps_0_100"] = pd.to_numeric(
        priority_frame["fpps_0_100"],
        errors="coerce",
    )
    if priority_frame["fpps_0_100"].isna().any():
        raise ValidationReportError("priority fpps_0_100 must be numeric.")

    top_actionable = _select_top_actionable(priority_frame)
    action_counts = _ordered_counts(priority_frame["action_class"], ("A", "B", "C", "D", "E"))
    confidence_counts = _ordered_counts(
        priority_frame["confidence_class"],
        ("high", "medium", "low"),
    )

    road_probability = pd.to_numeric(
        road_risk["road_disruption_probability_0_1"],
        errors="coerce",
    )
    if road_probability.isna().any():
        raise ValidationReportError(
            "road_risk road_disruption_probability_0_1 must be numeric."
        )
    high_risk_road_count = int((road_probability >= 0.7).sum())

    access_totals = {
        threshold: float(access_loss[f"people_losing_{threshold}_min_access"].sum())
        for threshold in ACCESS_THRESHOLDS
    }
    worst_access = access_loss.sort_values(
        ["people_losing_30_min_access", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]

    numeric_equity = pd.to_numeric(equity_gap["equity_gap_ratio"], errors="coerce")
    if numeric_equity.notna().any():
        strongest_equity = equity_gap.loc[numeric_equity.idxmax()]
        max_equity_ratio = float(numeric_equity.max())
        strongest_equity_label = (
            f"{strongest_equity['subdistrict_id']} / "
            f"{strongest_equity['subdistrict_name']}"
        )
    else:
        max_equity_ratio = float("nan")
        strongest_equity_label = "unavailable"

    sensitivity_lines = _build_sensitivity_lines(priority_frame, rank_instability)

    lines = [
        "# FloodGuard Validation Summary",
        "",
        "Generated from fixture-backed outputs. This is not a real flood validation report.",
        "",
        "## Decision Narrative",
        "",
        (
            "- Current status: fixture-backed decision demo for prioritization, "
            "scenario comparison, access loss, equity gap, road risk, and action briefs."
        ),
        (
            "- The dashboard and this report show the decision layer working end to end, "
            "but they do not prove real flood-detection accuracy."
        ),
        "- This output is non-operational, not an official warning, and not a real-time sensor.",
        "",
        "## What The Fixture Proves",
        "",
        "- FPPS scoring, A-E action class assignment, and top-reason generation are deterministic.",
        "- Road-risk, access-loss, equity-gap, scenario, and sensitivity outputs can be joined into dashboard-ready GeoJSON.",
        "- Actionable brief selection favors A/B/C decision classes over a low-confidence numeric score leader.",
        "",
        "## Data Readiness Narrative",
        "",
        (
            "- Local THEOS-2, Sentinel-1, and DEM assets are cataloged as context/readiness "
            "lanes with checksums or blocker states where available."
        ),
        (
            "- Sentinel-1 and DEM context quicklooks are not flood labels, not reference masks, "
            "and not agency flood products."
        ),
        (
            "- Qualified Mae Sai validation is blocked because provider response pending items "
            "still control reference-mask use, validation, ML-label use, derived reporting, and "
            "redistribution/reference-only terms."
        ),
        "",
        "## What Remains Blocked",
        "",
        "- Qualified Thailand event-reference IoU, F1/Dice, precision, recall, and area error remain blocked until an eligible reference mask exists.",
        "- A checksum-bound, non-operational cross-border weak-reference Sentinel-1 baseline exists; it is calibration evidence, not Mae Sai Thailand validation.",
        "- Current-pair real-data ML remains blocked until qualified labels, reviewer calibration, and immutable spatial partitions pass.",
        "",
        "## Real Mae Sai Gate Update",
        "",
        "- Required before real validation: geometry access, local validation permission, derived metrics permission, screenshots/demo permission, redistribution or reference-only status, ML-label use status, citation, and disclaimers.",
        "- Provider response pending: update `docs/reference_mask_licensing_log.md` and `docs/licensing_outreach_status.md` when UNOSAT/UNITAR or GISTDA replies arrive.",
        "",
        "## Fixture Coverage",
        "",
        f"- Priority rows: {len(priority_frame)}",
        f"- Road-risk rows: {len(road_risk)}",
        f"- Access-loss rows: {len(access_loss)}",
        f"- Equity-gap rows: {len(equity_gap)}",
        "",
        "## Priority Score Summary",
        "",
        (
            f"- Top actionable subdistrict: {top_actionable['subdistrict_id']} / "
            f"{top_actionable['subdistrict_name']}"
        ),
        f"- Top actionable class: {top_actionable['action_class']}",
        f"- Top actionable FPPS: {float(top_actionable['fpps_0_100']):.2f}",
        f"- Max FPPS: {float(priority_frame['fpps_0_100'].max()):.2f}",
        f"- Mean FPPS: {float(priority_frame['fpps_0_100'].mean()):.2f}",
        f"- Action-class counts: {_format_counts(action_counts)}",
        f"- Confidence counts: {_format_counts(confidence_counts)}",
        "",
        "## Road Risk Summary",
        "",
        f"- High-risk road count (>= 0.70): {high_risk_road_count}",
        f"- Max road risk: {float(road_probability.max()):.3f}",
        f"- Mean road risk: {float(road_probability.mean()):.3f}",
        "",
        "## Access Loss Summary",
        "",
        f"- People losing 15-minute access: {access_totals[15]:.0f}",
        f"- People losing 30-minute access: {access_totals[30]:.0f}",
        f"- People losing 60-minute access: {access_totals[60]:.0f}",
        (
            "- Worst 30-minute access-loss subdistrict: "
            f"{worst_access['subdistrict_id']} / {worst_access['subdistrict_name']} "
            f"({float(worst_access['people_losing_30_min_access']):.0f} people)"
        ),
        "",
        "## Equity Gap Summary",
        "",
        f"- Max numeric equity-gap ratio: {_format_float(max_equity_ratio, 3)}",
        f"- Strongest equity-gap subdistrict: {strongest_equity_label}",
        "",
        "## Sensitivity Summary",
        "",
        *sensitivity_lines,
        "",
        "## Future Validation Metrics",
        "",
    ]
    for placeholder in FUTURE_METRIC_PLACEHOLDERS:
        if placeholder == "score sensitivity":
            lines.append(
                "- score sensitivity: implemented for fixtures; real calibration remains pending."
            )
        else:
            lines.append(f"- {placeholder}: pending real reference data.")
    lines.extend(
        [
            "",
            "## Assumptions",
            "",
            "- Current metrics are generated from synthetic fixtures only.",
            "- Road-risk outputs are heuristic probabilities, not observed closures.",
            "- Flood extent metrics remain placeholders until real reference masks exist.",
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_summary(
    priority: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    output_path: str | Path,
    rank_instability: pd.DataFrame | None = None,
) -> Path:
    """Write a Markdown validation summary and return the output path."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_validation_summary(
            priority,
            road_risk,
            access_loss,
            equity_gap,
            rank_instability=rank_instability,
        ),
        encoding="utf-8",
    )
    return target


def build_real_data_validation_summary(
    file_manifest: pd.DataFrame,
    sar_metrics: pd.DataFrame | None = None,
    weak_reference_metrics: pd.DataFrame | None = None,
    weak_reference_feature_manifest: pd.DataFrame | None = None,
    manual_reference_manifest: pd.DataFrame | None = None,
    context_quality_manifest: pd.DataFrame | None = None,
    title: str = "Mae Sai Real-Data Validation Summary",
) -> str:
    """Build a Mae Sai real-data report with official and weak-reference status."""

    gate_allowed = True
    gate_error = ""
    try:
        ready_rows = validate_mae_sai_file_manifest_ready(file_manifest)
    except IngestionPlanError as exc:
        gate_allowed = False
        gate_error = str(exc)
        ready_rows = pd.DataFrame()

    weak_available = weak_reference_metrics is not None and not weak_reference_metrics.empty
    if weak_available:
        _validate_columns(
            weak_reference_metrics,
            MASK_METRIC_COLUMNS,
            "weak_reference_metrics",
        )
        _validate_weak_reference_metric_lineage(
            file_manifest,
            weak_reference_metrics,
            weak_reference_feature_manifest,
            manual_reference_manifest,
        )
    if sar_metrics is not None:
        _validate_columns(sar_metrics, MASK_METRIC_COLUMNS, "sar_metrics")
        if sar_metrics.empty:
            raise ValidationReportError("sar_metrics must contain at least one row.")
        if not gate_allowed:
            raise ValidationReportError(
                "Official SAR metrics were supplied while the official ingestion gate "
                "is blocked. Candidate metrics must use the weak-reference lane."
            )
        if len(sar_metrics) != 1:
            raise ValidationReportError("sar_metrics must contain exactly one row.")
        _validate_metric_arithmetic(sar_metrics.iloc[0], "sar_metrics")

    integrity_verified = weak_available
    status_line = (
        "Weak-reference candidate metrics are integrity-bound; official validation remains blocked."
        if weak_available and integrity_verified and not gate_allowed
        else (
            "Weak-reference candidate metric rows are present, but their supplied manifest "
            "does not record verified source integrity; official validation remains blocked."
        )
        if weak_available and not gate_allowed
        else "Official validation gate is open and metric rows can be reported."
        if gate_allowed
        else "Official validation remains blocked and weak-reference metrics are pending."
    )

    lines = [
        f"# {title}",
        "",
        f"Report status: {status_line}",
        "",
        (
            "Strict use statement: Cross-border calibration metrics against a "
            "manually digitized weak-reference mask; not Mae Sai Thailand ADM3 "
            "validation. Non-operational. Not official validation. Not field validated."
        ),
        "",
        "## Data Status",
        "",
        f"- Official processing allowed: {str(gate_allowed).lower()}",
    ]

    if gate_allowed:
        lines.extend(
            [
                f"- Ready official source rows: {len(ready_rows)}",
                "- Reference mask and Sentinel-1 rows passed file-level gates.",
            ]
        )
    else:
        lines.extend(
            [
                f"- Official blocking reason: {gate_error}",
                "- Official IoU, F1/Dice, precision, recall, and area error remain pending.",
            ]
        )
    lines.extend(
        [
            f"- Weak-reference candidate metrics available: {str(weak_available).lower()}",
            f"- Weak-reference source integrity verified: {str(integrity_verified).lower()}",
            "- Source imagery and manual GeoPackage files stay outside Git; this report stores only derived metadata and metrics.",
            "- Real-data ML remains blocked because the weak-reference mask is not an official or cleared label source.",
            "",
        ]
    )

    _append_sentinel1_product_section(lines, file_manifest, weak_reference_feature_manifest)
    _append_integrity_and_spatial_scope_section(
        lines,
        weak_reference_feature_manifest,
        manual_reference_manifest,
        context_quality_manifest,
    )
    _append_manual_reference_metadata_section(lines, manual_reference_manifest)
    _append_method_assumptions_section(lines, weak_reference_feature_manifest)
    _append_candidate_metrics_section(lines, weak_reference_metrics, sar_metrics)
    _append_failure_modes_section(lines)
    _append_safety_note_section(lines)
    _append_official_gate_detail_section(lines, gate_allowed, gate_error, ready_rows)
    return "\n".join(lines)


def write_real_data_validation_summary(
    file_manifest: pd.DataFrame,
    output_path: str | Path,
    sar_metrics: pd.DataFrame | None = None,
    weak_reference_metrics: pd.DataFrame | None = None,
    weak_reference_feature_manifest: pd.DataFrame | None = None,
    manual_reference_manifest: pd.DataFrame | None = None,
    context_quality_manifest: pd.DataFrame | None = None,
    title: str = "Mae Sai Real-Data Validation Summary",
) -> Path:
    """Write the real-data validation status/metric report."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_real_data_validation_summary(
            file_manifest,
            sar_metrics=sar_metrics,
            weak_reference_metrics=weak_reference_metrics,
            weak_reference_feature_manifest=weak_reference_feature_manifest,
            manual_reference_manifest=manual_reference_manifest,
            context_quality_manifest=context_quality_manifest,
            title=title,
        ),
        encoding="utf-8",
    )
    return target


def _append_sentinel1_product_section(
    lines: list[str],
    file_manifest: pd.DataFrame,
    weak_reference_feature_manifest: pd.DataFrame | None,
) -> None:
    lines.extend(["## Sentinel-1 Product IDs", ""])

    if weak_reference_feature_manifest is not None and not weak_reference_feature_manifest.empty:
        feature = weak_reference_feature_manifest.iloc[0]
        lines.extend(
            [
                f"- Pre-event Sentinel-1 product id: `{_cell(feature, 'pre_product_id', 'unavailable')}`",
                f"- Post-event Sentinel-1 product id: `{_cell(feature, 'post_product_id', 'unavailable')}`",
                f"- Post-event source timestamp: {_cell(feature, 'source_timestamp', 'unavailable')}",
                f"- Pre-event source name: {_cell(feature, 'pre_source_name', 'unavailable')}",
                f"- Post-event source name: {_cell(feature, 'post_source_name', 'unavailable')}",
                (
                    "- Source integrity recorded by run manifest: "
                    f"{_cell(feature, 'source_integrity_status', 'unavailable')}"
                ),
                "",
            ]
        )
        return

    sentinel_rows = file_manifest[
        file_manifest.astype(str).apply(
            lambda row: row.str.contains("Sentinel-1|sentinel-1", regex=True).any(),
            axis=1,
        )
    ]
    if sentinel_rows.empty:
        lines.extend(["- Sentinel-1 product rows: unavailable.", ""])
        return
    for _, row in sentinel_rows.iterrows():
        lines.append(
            f"- {_cell(row, 'source_name', 'Sentinel-1 source')}: "
            f"`{_cell(row, 'product_id', 'unavailable')}`"
        )
    lines.append("")


def _validate_weak_reference_metric_lineage(
    file_manifest: pd.DataFrame,
    weak_reference_metrics: pd.DataFrame,
    weak_reference_feature_manifest: pd.DataFrame | None,
    manual_reference_manifest: pd.DataFrame | None,
) -> None:
    """Bind candidate metrics to one checked source/reference feature run.

    A report is evidence, not a CSV viewer.  Metric rows therefore fail closed
    unless their confusion matrix is internally coherent and their source,
    reference, sample-count, timestamp, threshold, and spatial-scope fields all
    reconcile with the immutable source and feature manifests.
    """

    if len(weak_reference_metrics) != 1:
        raise ValidationReportError(
            "weak_reference_metrics must contain exactly one evidence row."
        )
    if weak_reference_feature_manifest is None or len(weak_reference_feature_manifest) != 1:
        raise ValidationReportError(
            "Weak-reference metrics require exactly one feature-manifest row."
        )
    if manual_reference_manifest is None or len(manual_reference_manifest) != 1:
        raise ValidationReportError(
            "Weak-reference metrics require exactly one manual-reference manifest row."
        )

    metric_required = (
        "study_area",
        "processing_scope",
        "reference_status",
        "metric_status",
        "pre_source_sha256",
        "post_source_sha256",
        "reference_sha256",
        "source_integrity_status",
        "measurement_domain",
        "log_transform",
        "radiometric_calibration_status",
        "reference_spatial_relation",
        "reference_in_study_area_overlap",
        "reference_distance_to_study_area_km",
        "sample_pixel_count",
        "reference_positive_pixel_count",
        "predicted_positive_pixel_count",
        "probability_threshold",
        "source_timestamp",
        "confidence_class",
        "warning_text",
        "assumptions",
    )
    feature_required = (
        "study_area",
        "processing_scope",
        "pre_product_id",
        "post_product_id",
        "reference_product_id",
        "reference_status",
        "pre_source_sha256",
        "post_source_sha256",
        "reference_sha256",
        "source_integrity_status",
        "measurement_domain",
        "log_transform",
        "radiometric_calibration_status",
        "reference_spatial_relation",
        "reference_in_study_area_overlap",
        "reference_distance_to_study_area_km",
        "sample_pixel_count",
        "reference_positive_pixel_count",
        "predicted_positive_pixel_count",
        "sample_width",
        "sample_height",
        "probability_threshold",
        "source_timestamp",
        "confidence_class",
    )
    manual_required = (
        "study_area",
        "reference_id",
        "confidence",
        "source_basis",
        "digitized_by",
        "digitized_at",
        "notes",
        "sha256",
        "sha256_status",
        "reference_mask_status",
        "candidate_readiness_status",
        "candidate_validation_metrics_allowed",
        "not_official_status",
        "attribute_values_status",
        "spatial_relation",
        "in_study_area_overlap",
        "distance_to_study_area_km",
        "spatial_relation_status",
    )
    file_required = ("study_area", "product_id", "sha256")
    _validate_columns(weak_reference_metrics, metric_required, "weak_reference_metrics")
    _validate_columns(
        weak_reference_feature_manifest,
        feature_required,
        "weak_reference_feature_manifest",
    )
    _validate_columns(
        manual_reference_manifest,
        manual_required,
        "manual_reference_manifest",
    )
    _validate_columns(file_manifest, file_required, "file_manifest")

    metric = weak_reference_metrics.iloc[0]
    feature = weak_reference_feature_manifest.iloc[0]
    manual = manual_reference_manifest.iloc[0]
    _validate_metric_arithmetic(metric, "weak_reference_metrics")

    exact_metric_feature_fields = (
        "study_area",
        "processing_scope",
        "reference_status",
        "pre_source_sha256",
        "post_source_sha256",
        "reference_sha256",
        "source_integrity_status",
        "measurement_domain",
        "log_transform",
        "radiometric_calibration_status",
        "reference_spatial_relation",
        "reference_in_study_area_overlap",
        "reference_distance_to_study_area_km",
        "sample_pixel_count",
        "reference_positive_pixel_count",
        "predicted_positive_pixel_count",
        "probability_threshold",
        "source_timestamp",
        "confidence_class",
    )
    for field in exact_metric_feature_fields:
        if _normalized_cell(metric, field) != _normalized_cell(feature, field):
            raise ValidationReportError(
                f"Weak-reference metric {field} does not match the feature manifest."
            )

    if (
        _normalized_cell(metric, "processing_scope")
        != "weak_reference_real_sentinel1_non_ml_candidate"
        or _normalized_cell(metric, "reference_status")
        != "weak_reference_candidate"
        or _normalized_cell(metric, "metric_status")
        != "candidate_cross_border_calibration_metrics"
        or _normalized_cell(metric, "source_integrity_status")
        != "verified_sha256_before_raster_read"
        or _normalized_cell(metric, "measurement_domain") != SAR_MEASUREMENT_DOMAIN
        or _normalized_cell(metric, "log_transform") != SAR_LOG_TRANSFORM
        or _normalized_cell(metric, "radiometric_calibration_status")
        != SAR_RADIOMETRIC_CALIBRATION_STATUS
        or _normalized_cell(metric, "reference_spatial_relation")
        != "cross_border_calibration_only"
        or _strict_report_bool(
            metric["reference_in_study_area_overlap"],
            "reference_in_study_area_overlap",
        )
        is not False
    ):
        raise ValidationReportError(
            "Weak-reference metrics do not preserve the verified cross-border "
            "candidate scope and source-integrity status."
        )

    for field in ("pre_source_sha256", "post_source_sha256", "reference_sha256"):
        _validated_sha256(metric[field], f"weak-reference metric {field}")
    if not str(metric["source_timestamp"]).strip():
        raise ValidationReportError("Weak-reference metric source_timestamp is blank.")
    warning = str(metric["warning_text"]).lower()
    if not all(
        phrase in warning
        for phrase in ("cross-border", "non-operational", "not official", "not field validated")
    ):
        raise ValidationReportError(
            "Weak-reference metric warning_text is missing mandatory safety language."
        )
    if not str(metric["assumptions"]).strip():
        raise ValidationReportError("Weak-reference metric assumptions are blank.")

    if (
        _normalized_cell(manual, "study_area") != _normalized_cell(feature, "study_area")
        or _normalized_cell(manual, "reference_id")
        != _normalized_cell(feature, "reference_product_id")
        or _normalized_cell(manual, "reference_mask_status")
        != _normalized_cell(feature, "reference_status")
        or _normalized_cell(manual, "sha256")
        != _normalized_cell(feature, "reference_sha256")
        or _normalized_cell(manual, "spatial_relation")
        != _normalized_cell(feature, "reference_spatial_relation")
        or _normalized_cell(manual, "in_study_area_overlap")
        != _normalized_cell(feature, "reference_in_study_area_overlap")
        or _normalized_cell(manual, "distance_to_study_area_km")
        != _normalized_cell(feature, "reference_distance_to_study_area_km")
    ):
        raise ValidationReportError(
            "Manual-reference identity, checksum, or spatial scope does not match "
            "the feature manifest."
        )
    if (
        str(manual["sha256_status"]).strip() not in {"recorded", "verified"}
        or str(manual["candidate_readiness_status"]).strip()
        != "ready_for_candidate_metrics"
        or not _strict_report_bool(
            manual["candidate_validation_metrics_allowed"],
            "candidate_validation_metrics_allowed",
        )
        or str(manual["not_official_status"]).strip() != "confirmed_true"
        or str(manual["attribute_values_status"]).strip() != "valid"
        or str(manual["spatial_relation_status"]).strip()
        != "verified_geometry_intersection"
    ):
        raise ValidationReportError(
            "Manual-reference manifest is not eligible for cross-border candidate metrics."
        )
    _validated_sha256(manual["sha256"], "manual-reference sha256")

    source_bindings = (
        ("pre_product_id", "pre_source_sha256"),
        ("post_product_id", "post_source_sha256"),
        ("reference_product_id", "reference_sha256"),
    )
    for product_field, hash_field in source_bindings:
        product_id = str(feature[product_field]).strip()
        matches = file_manifest[
            file_manifest["product_id"].astype(str).str.strip() == product_id
        ]
        if len(matches) != 1:
            raise ValidationReportError(
                f"Feature-manifest {product_field} must match exactly one source row."
            )
        source = matches.iloc[0]
        if (
            _normalized_cell(source, "study_area")
            != _normalized_cell(feature, "study_area")
            or _normalized_cell(source, "sha256")
            != _normalized_cell(feature, hash_field)
        ):
            raise ValidationReportError(
                f"Feature-manifest {product_field} checksum or study area was substituted."
            )
        _validated_sha256(source["sha256"], f"{product_id} source sha256")

    sample_count = _nonnegative_int(metric["sample_pixel_count"], "sample_pixel_count")
    width = _positive_int(feature["sample_width"], "sample_width")
    height = _positive_int(feature["sample_height"], "sample_height")
    if sample_count > width * height:
        raise ValidationReportError(
            "Weak-reference sample count exceeds the declared feature grid."
        )


def _validate_metric_arithmetic(metric: pd.Series, label: str) -> None:
    counts = {
        field: _nonnegative_int(metric[field], f"{label} {field}")
        for field in (
            "true_positive",
            "false_positive",
            "false_negative",
            "true_negative",
        )
    }
    tp = counts["true_positive"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    tn = counts["true_negative"]
    expected = {
        "iou": _safe_report_ratio(tp, tp + fp + fn),
        "f1_dice": _safe_report_ratio(2 * tp, 2 * tp + fp + fn),
        "precision": _safe_report_ratio(tp, tp + fp),
        "recall": _safe_report_ratio(tp, tp + fn),
        "area_error_ratio": _safe_report_ratio((tp + fp) - (tp + fn), tp + fn),
    }
    for field, expected_value in expected.items():
        try:
            observed = float(metric[field])
        except (TypeError, ValueError) as exc:
            raise ValidationReportError(f"{label} {field} must be numeric.") from exc
        if not math.isfinite(observed) or not math.isclose(
            observed,
            expected_value,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValidationReportError(
                f"{label} {field} does not match its confusion-matrix counts."
            )
    sample_count = tp + fp + fn + tn
    if "sample_pixel_count" in metric.index and _nonnegative_int(
        metric["sample_pixel_count"], "sample_pixel_count"
    ) != sample_count:
        raise ValidationReportError(
            f"{label} sample_pixel_count does not match confusion-matrix counts."
        )
    if "reference_positive_pixel_count" in metric.index and _nonnegative_int(
        metric["reference_positive_pixel_count"], "reference_positive_pixel_count"
    ) != tp + fn:
        raise ValidationReportError(
            f"{label} reference_positive_pixel_count does not match confusion-matrix counts."
        )
    if "predicted_positive_pixel_count" in metric.index and _nonnegative_int(
        metric["predicted_positive_pixel_count"], "predicted_positive_pixel_count"
    ) != tp + fp:
        raise ValidationReportError(
            f"{label} predicted_positive_pixel_count does not match confusion-matrix counts."
        )


def _safe_report_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0 if numerator == 0 else math.nan
    return round(float(numerator) / float(denominator), 6)


def _nonnegative_int(value: object, label: str) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationReportError(f"{label} must be a non-negative integer.") from exc
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValidationReportError(f"{label} must be a non-negative integer.")
    return int(numeric)


def _positive_int(value: object, label: str) -> int:
    parsed = _nonnegative_int(value, label)
    if parsed <= 0:
        raise ValidationReportError(f"{label} must be positive.")
    return parsed


def _validated_sha256(value: object, label: str) -> str:
    digest = str(value).strip()
    if not _SHA256_RE.fullmatch(digest):
        raise ValidationReportError(f"{label} must be a lowercase SHA-256 digest.")
    return digest


def _strict_report_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValidationReportError(f"{label} must be explicit true or false.")


def _normalized_cell(row: pd.Series, field: str) -> str:
    value = row[field]
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).strip()
    if text.lower() in {"true", "false"}:
        return text.lower()
    try:
        numeric = float(text)
    except ValueError:
        return text
    if math.isfinite(numeric):
        return format(numeric, ".15g")
    return text


def _append_integrity_and_spatial_scope_section(
    lines: list[str],
    weak_reference_feature_manifest: pd.DataFrame | None,
    manual_reference_manifest: pd.DataFrame | None,
    context_quality_manifest: pd.DataFrame | None,
) -> None:
    lines.extend(["## Integrity And Spatial Scope", ""])
    if weak_reference_feature_manifest is None or weak_reference_feature_manifest.empty:
        lines.extend(
            [
                "- Source integrity status: unavailable; this report does not infer it.",
                "- Pre/post/reference checksum lineage: unavailable.",
            ]
        )
    else:
        feature = weak_reference_feature_manifest.iloc[0]
        lines.extend(
            [
                (
                    "- Source integrity status: "
                    f"{_cell(feature, 'source_integrity_status', 'unavailable')}"
                ),
                f"- Pre-event SHA-256: `{_cell(feature, 'pre_source_sha256', 'unavailable')}`",
                f"- Post-event SHA-256: `{_cell(feature, 'post_source_sha256', 'unavailable')}`",
                f"- Reference SHA-256: `{_cell(feature, 'reference_sha256', 'unavailable')}`",
            ]
        )

    if manual_reference_manifest is None or manual_reference_manifest.empty:
        lines.append("- Manual-mask attribute integrity: unavailable.")
    else:
        manual = manual_reference_manifest.iloc[0]
        lines.extend(
            [
                (
                    "- Manual-mask attribute integrity: "
                    f"{_cell(manual, 'attribute_values_status', 'unavailable')}"
                ),
                (
                    "- Manual-mask attribute blockers: "
                    f"{_cell(manual, 'attribute_value_blockers', 'none recorded')}"
                ),
                (
                    "- Manual-mask spatial relation: "
                    f"{_cell(manual, 'spatial_relation', 'unavailable')}"
                ),
                (
                    "- Manual-mask in-study-area overlap: "
                    f"{_cell(manual, 'in_study_area_overlap', 'unavailable')}"
                ),
                (
                    "- Manual-mask distance to study area: "
                    f"{_cell(manual, 'distance_to_study_area_km', 'unavailable')} km"
                ),
            ]
        )

    if context_quality_manifest is None or context_quality_manifest.empty:
        lines.extend(
            [
                "- Thailand ADM3 candidate overlap: unavailable; this report does not infer spatial overlap.",
                "- Cross-border status: unavailable from the supplied context manifest.",
                "",
            ]
        )
        return

    context = context_quality_manifest.iloc[0]
    overlap = _as_bool(
        context.get("manual_reference_overlaps_thailand_adm3_candidate", pd.NA)
    )
    if overlap is False:
        lines.extend(
            [
                "- Thailand ADM3 candidate overlap: false.",
                "- Cross-border status: nearby cross-border calibration evidence only.",
                "- Interpretation: these weak-reference metrics do not validate flood extent inside Mae Sai Thailand ADM3 reporting polygons.",
            ]
        )
    elif overlap is True:
        lines.extend(
            [
                "- Thailand ADM3 candidate overlap: true.",
                "- Cross-border status: no cross-border non-overlap recorded by the supplied context manifest.",
            ]
        )
    else:
        lines.extend(
            [
                "- Thailand ADM3 candidate overlap: unresolved in the supplied context manifest.",
                "- Cross-border status: unresolved; no spatial qualification is inferred.",
            ]
        )
    lines.extend(
        [
            f"- Context-manifest assumptions: {_cell(context, 'assumptions', 'unavailable')}",
            "",
        ]
    )


def _append_manual_reference_metadata_section(
    lines: list[str],
    manual_reference_manifest: pd.DataFrame | None,
) -> None:
    lines.extend(["## Manual Reference Mask Metadata", ""])
    if manual_reference_manifest is None or manual_reference_manifest.empty:
        lines.extend(
            [
                "- Manual weak-reference manifest: unavailable.",
                "- Candidate metrics cannot be interpreted without manual-mask metadata.",
                "",
            ]
        )
        return

    manual = manual_reference_manifest.iloc[0]
    bbox = _format_bbox(
        manual,
        ("bbox_lon_min", "bbox_lat_min", "bbox_lon_max", "bbox_lat_max"),
    )
    lines.extend(
        [
            f"- Reference id: `{_cell(manual, 'reference_id', 'unavailable')}`",
            f"- Study area: {_cell(manual, 'study_area', 'unavailable')}",
            f"- Confidence: {_cell(manual, 'confidence', 'unavailable')}",
            f"- Source basis: {_cell(manual, 'source_basis', 'unavailable')}",
            f"- Digitized by: {_cell(manual, 'digitized_by', 'unavailable')}",
            f"- Digitized at: {_cell(manual, 'digitized_at', 'unavailable')}",
            f"- Notes: {_cell(manual, 'notes', 'unavailable')}",
            f"- Layer name: {_cell(manual, 'layer_name', 'unavailable')}",
            f"- Geometry type: {_cell(manual, 'geometry_type', 'unavailable')}",
            f"- CRS: {_cell(manual, 'crs', 'unavailable')}",
            f"- Feature count: {_cell(manual, 'feature_count', 'unavailable')}",
            f"- Bounding box: {bbox}",
            f"- SHA-256 status: {_cell(manual, 'sha256_status', 'unavailable')}",
            f"- Not-official status: {_cell(manual, 'not_official_status', 'unavailable')}",
            f"- Reference-mask status: {_cell(manual, 'reference_mask_status', 'unavailable')}",
            f"- Candidate readiness: {_cell(manual, 'candidate_readiness_status', 'unavailable')}",
            (
                "- Candidate validation metrics allowed: "
                f"{_cell(manual, 'candidate_validation_metrics_allowed', 'unavailable')}"
            ),
            f"- Allowed use: {_cell(manual, 'allowed_use', 'unavailable')}",
            f"- Not allowed use: {_cell(manual, 'not_allowed_use', 'unavailable')}",
            (
                "- Identity disclosure: `[blank]` means the digitizer identity was "
                "explicitly not recorded; it is not reviewer qualification."
            ),
            "",
        ]
    )


def _append_method_assumptions_section(
    lines: list[str],
    weak_reference_feature_manifest: pd.DataFrame | None,
) -> None:
    lines.extend(["## Method Assumptions", ""])
    lines.extend(
        [
            "- Method type: non-ML Sentinel-1 pre/post SAR change baseline.",
            "- Inputs: pre-event VV/VH and post-event VV/VH from local CDSE Sentinel-1 products outside Git.",
            "- Reference: manually digitized weak-reference flood polygon from QGIS.",
            "- Interpretation: candidate engineering metric only, not official accuracy.",
        ]
    )
    if weak_reference_feature_manifest is not None and not weak_reference_feature_manifest.empty:
        feature = weak_reference_feature_manifest.iloc[0]
        lines.extend(
            [
                f"- Window strategy: {_cell(feature, 'window_strategy', 'unavailable')}",
                f"- Sample size: {_cell(feature, 'sample_width', '?')} x {_cell(feature, 'sample_height', '?')} pixels",
                f"- Georeferencing method: {_cell(feature, 'georeferencing_method', 'unavailable')}",
                f"- Measurement domain: {_cell(feature, 'measurement_domain', 'unavailable')}",
                f"- Log transform: {_cell(feature, 'log_transform', 'unavailable')}",
                (
                    "- Radiometric calibration: "
                    f"{_cell(feature, 'radiometric_calibration_status', 'unavailable')}"
                ),
                f"- Probability threshold: {_cell(feature, 'probability_threshold', 'unavailable')}",
                f"- Dry-change threshold: {_cell(feature, 'dry_change_db', 'unavailable')} dB",
                f"- Flood-change threshold: {_cell(feature, 'flood_change_db', 'unavailable')} dB",
                f"- Confidence class: {_cell(feature, 'confidence_class', 'unavailable')}",
                f"- Assumptions: {_cell(feature, 'assumptions', 'unavailable')}",
            ]
        )
    lines.extend(
        [
            "- Terrain correction, calibration refinement, permanent-water masking, and threshold tuning remain future work.",
            "",
        ]
    )


def _append_candidate_metrics_section(
    lines: list[str],
    weak_reference_metrics: pd.DataFrame | None,
    sar_metrics: pd.DataFrame | None,
) -> None:
    lines.extend(["## Candidate Metrics", ""])

    if weak_reference_metrics is None or weak_reference_metrics.empty:
        lines.extend(
            [
                "- Weak-reference candidate metrics: pending.",
                "- No weak-reference candidate metrics were supplied.",
                "",
            ]
        )
    else:
        metrics = weak_reference_metrics.iloc[0]
        lines.extend(
            [
                "- Status: cross-border calibration metrics generated against a manually digitized weak-reference mask.",
                "- Metric status: candidate cross-border calibration metrics, not Mae Sai Thailand ADM3 validation.",
                f"- IoU: {float(metrics['iou']):.6f}",
                f"- F1/Dice: {float(metrics['f1_dice']):.6f}",
                f"- precision: {float(metrics['precision']):.6f}",
                f"- recall: {float(metrics['recall']):.6f}",
                f"- area error ratio: {float(metrics['area_error_ratio']):.6f}",
            ]
        )
        for column, label in (
            ("true_positive", "True positive pixels"),
            ("false_positive", "False positive pixels"),
            ("false_negative", "False negative pixels"),
            ("true_negative", "True negative pixels"),
            ("sample_pixel_count", "Sample pixels"),
            ("reference_positive_pixel_count", "Manual weak-reference positive pixels"),
            ("predicted_positive_pixel_count", "Predicted positive pixels"),
        ):
            if column in weak_reference_metrics.columns:
                lines.append(f"- {label}: {int(float(metrics[column]))}")
        lines.extend(
            [
                f"- Source timestamp: {_cell(metrics, 'source_timestamp', 'unavailable')}",
                f"- Confidence class: {_cell(metrics, 'confidence_class', 'unavailable')}",
                f"- Warning text: {_cell(metrics, 'warning_text', 'unavailable')}",
                "",
            ]
        )

    if sar_metrics is not None and not sar_metrics.empty:
        official = sar_metrics.iloc[0]
        lines.extend(
            [
                "### Officially Gated Metrics",
                "",
                f"- IoU: {float(official['iou']):.6f}",
                f"- F1/Dice: {float(official['f1_dice']):.6f}",
                f"- precision: {float(official['precision']):.6f}",
                f"- recall: {float(official['recall']):.6f}",
                f"- area error ratio: {float(official['area_error_ratio']):.6f}",
                "",
            ]
        )


def _append_failure_modes_section(lines: list[str]) -> None:
    lines.extend(
        [
            "## Failure Modes",
            "",
            "- SAR layover/shadow can look like water or hide flood signal in steep terrain.",
            "- Permanent water confusion can inflate flood detections if baseline water is not masked.",
            "- Urban double-bounce can make built-up flood areas brighter or inconsistent across VV/VH.",
            "- Manual mask uncertainty affects every candidate metric because the reference is not field validated.",
            "- Date mismatch can occur if the manual interpretation and Sentinel-1 acquisition do not capture the same flood stage.",
            "",
        ]
    )


def _append_safety_note_section(lines: list[str]) -> None:
    lines.extend(
        [
            "## Safety Note",
            "",
            "- Not official.",
            "- Not real-time.",
            "- Not field validated.",
            "- Not an emergency warning.",
            "- Do not use this report for public alerting, evacuation orders, insurance decisions, or operational response without official validation.",
            "",
        ]
    )


def _append_official_gate_detail_section(
    lines: list[str],
    gate_allowed: bool,
    gate_error: str,
    ready_rows: pd.DataFrame,
) -> None:
    lines.extend(["## Official Gate Details", "", "### Ingestion Gate", ""])
    if gate_allowed:
        lines.extend(
            [
                "- Processing allowed: true",
                f"- Ready source rows: {len(ready_rows)}",
                "- Official flood-mask metrics may be generated only for these gated rows.",
                "",
                "### Source Rows",
                "",
            ]
        )
        for _, row in ready_rows.iterrows():
            lines.append(
                f"- {_cell(row, 'source_name', 'source')}: product_id "
                f"`{_cell(row, 'product_id', 'unavailable')}`"
            )
        lines.append("")
        return

    lines.extend(
        [
            "- Processing allowed: false",
            f"- Blocking reason: {gate_error}",
            "- Real IoU, F1/Dice, precision, recall, and area error are pending for official validation.",
            "",
            "### Required Next Action",
            "",
            "- Log UNOSAT/UNITAR or GISTDA provider response.",
            "- Record legal reference-mask status.",
            "- Acquire and checksum-bind the future qualified reference artifact outside Git; the active SAFE pair and cross-border manual reference are already checksum-bound.",
            "- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.",
            "",
        ]
    )


def _cell(row: pd.Series, column: str, default: str) -> str:
    if column not in row.index:
        return default
    value = row[column]
    if pd.isna(value) or str(value).strip() == "":
        return default
    return str(value)


def _format_bbox(row: pd.Series, columns: tuple[str, str, str, str]) -> str:
    values: list[str] = []
    for column in columns:
        text = _cell(row, column, "")
        if text == "":
            return "unavailable"
        try:
            values.append(f"{float(text):.6f}")
        except ValueError:
            return "unavailable"
    return f"{values[0]}, {values[1]}, {values[2]}, {values[3]}"


def _append_weak_reference_section(
    lines: list[str],
    weak_reference_metrics: pd.DataFrame | None,
    weak_reference_feature_manifest: pd.DataFrame | None,
    manual_reference_manifest: pd.DataFrame | None,
) -> None:
    if weak_reference_metrics is None:
        lines.extend(
            [
                "## Weak-Reference Candidate Baseline",
                "",
                "- Status: pending. No weak-reference candidate metrics were supplied.",
                "- This section will use the manual QGIS weak-reference lane only for candidate metrics, not official validation.",
                "",
            ]
        )
        return
    _validate_columns(weak_reference_metrics, MASK_METRIC_COLUMNS, "weak_reference_metrics")
    if weak_reference_metrics.empty:
        raise ValidationReportError("weak_reference_metrics must contain at least one row.")
    metrics = weak_reference_metrics.iloc[0]
    lines.extend(
        [
            "## Weak-Reference Candidate Baseline",
            "",
            (
                "- Status: candidate metrics generated against a manually digitized "
                "weak-reference mask."
            ),
            "- These are not official validation metrics and must not be used as emergency-warning evidence.",
            f"- IoU: {float(metrics['iou']):.6f}",
            f"- F1/Dice: {float(metrics['f1_dice']):.6f}",
            f"- precision: {float(metrics['precision']):.6f}",
            f"- recall: {float(metrics['recall']):.6f}",
            f"- area error ratio: {float(metrics['area_error_ratio']):.6f}",
        ]
    )
    if "sample_pixel_count" in weak_reference_metrics.columns:
        lines.append(f"- Sample pixels: {int(metrics['sample_pixel_count'])}")
    if "reference_positive_pixel_count" in weak_reference_metrics.columns:
        lines.append(
            f"- Manual weak-reference positive pixels: {int(metrics['reference_positive_pixel_count'])}"
        )
    if weak_reference_feature_manifest is not None and not weak_reference_feature_manifest.empty:
        feature = weak_reference_feature_manifest.iloc[0]
        if {"pre_product_id", "post_product_id", "reference_product_id"}.issubset(
            set(weak_reference_feature_manifest.columns)
        ):
            lines.extend(
                [
                    f"- Pre-event Sentinel-1 product id: `{feature['pre_product_id']}`",
                    f"- Post-event Sentinel-1 product id: `{feature['post_product_id']}`",
                    f"- Manual reference id: `{feature['reference_product_id']}`",
                ]
            )
        if "georeferencing_method" in weak_reference_feature_manifest.columns:
            lines.append(f"- Georeferencing method: {feature['georeferencing_method']}")
    if manual_reference_manifest is not None and not manual_reference_manifest.empty:
        manual = manual_reference_manifest.iloc[0]
        if "not_official_status" in manual_reference_manifest.columns:
            lines.append(f"- Manual mask not-official status: {manual['not_official_status']}")
        if "candidate_readiness_status" in manual_reference_manifest.columns:
            lines.append(
                f"- Manual mask readiness: {manual['candidate_readiness_status']}"
            )
    lines.extend(
        [
            "",
            "### Weak-Reference Failure Modes",
            "",
            "- SAR layover/shadow.",
            "- Permanent water confusion.",
            "- Urban double-bounce.",
            "- Manual mask uncertainty.",
            "- Date mismatch between manual interpretation and Sentinel-1 acquisition.",
            "",
            "### Weak-Reference Safety Note",
            "",
            "- Not official.",
            "- Not real-time.",
            "- Not field validated.",
            "- Not an emergency warning.",
            "",
        ]
    )


def _select_top_actionable(priority: pd.DataFrame) -> pd.Series:
    unknown_actions = sorted(set(priority["action_class"].astype(str)) - set(ACTION_PRIORITY))
    if unknown_actions:
        raise ValidationReportError(
            f"Unknown action_class value(s): {', '.join(unknown_actions)}"
        )
    ranked = priority.copy()
    ranked["action_rank"] = ranked["action_class"].map(ACTION_PRIORITY)
    return ranked.sort_values(
        ["action_rank", "fpps_0_100", "subdistrict_id"],
        ascending=[True, False, True],
    ).iloc[0]


def _build_sensitivity_lines(
    priority_frame: pd.DataFrame,
    rank_instability: pd.DataFrame | None,
) -> list[str]:
    numeric_top = priority_frame.sort_values(
        ["fpps_0_100", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]
    top_actionable = _select_top_actionable(priority_frame)
    disclosure = (
        f"- Top numeric FPPS row: {numeric_top['subdistrict_id']} / "
        f"{numeric_top['subdistrict_name']} "
        f"(class {numeric_top['action_class']}, confidence {numeric_top['confidence_class']})."
    )
    if str(numeric_top["subdistrict_id"]) != str(top_actionable["subdistrict_id"]):
        disclosure += " It is not used as the top actionable brief target."

    if rank_instability is None:
        return [
            "- Rank-instability rows: unavailable.",
            "- Fixture sensitivity CSV was not supplied to this report run.",
            disclosure,
        ]

    _validate_columns(rank_instability, RANK_INSTABILITY_REQUIRED_COLUMNS, "rank_instability")
    rank_frame = rank_instability.copy()
    rank_frame["rank_range"] = pd.to_numeric(rank_frame["rank_range"], errors="coerce")
    if rank_frame["rank_range"].isna().any():
        raise ValidationReportError("rank_instability rank_range must be numeric.")
    unstable_flags = rank_frame["ranking_unstable"].map(_as_bool)
    if unstable_flags.isna().any():
        raise ValidationReportError(
            "rank_instability ranking_unstable must be boolean-like."
        )
    unstable_bool = unstable_flags.astype(bool)

    unstable_count = int(unstable_bool.sum())
    stable_count = int((~unstable_bool).sum())
    max_rank_range = int(rank_frame["rank_range"].max())
    lines = [
        f"- Stable rank count: {stable_count}",
        f"- Unstable rank count: {unstable_count}",
        f"- Max rank range: {max_rank_range}",
    ]
    if max_rank_range == 0:
        lines.append("- All fixture ranks are stable because every rank_range is 0.")
    else:
        most_variable = rank_frame.sort_values(
            ["rank_range", "subdistrict_id"],
            ascending=[False, True],
        ).iloc[0]
        lines.append(
            "- Most variable rank: "
            f"{most_variable['subdistrict_id']} / "
            f"{most_variable['subdistrict_name']} "
            f"(rank_range {int(most_variable['rank_range'])})."
        )
    lines.append(disclosure)
    return lines


def _as_bool(value: object) -> bool | object:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return pd.NA


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValidationReportError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _ordered_counts(values: pd.Series, order: Sequence[str]) -> dict[str, int]:
    counts = values.astype(str).str.lower().value_counts().to_dict()
    result: dict[str, int] = {}
    for label in order:
        result[label] = int(counts.get(label.lower(), 0))
    return result


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def _format_float(value: float, places: int) -> str:
    if pd.isna(value):
        return "unavailable"
    return f"{value:.{places}f}"
