"""Weak-reference Mae Sai Sentinel-1 baseline reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from floodguard.sar_baseline import MASK_METRIC_COLUMNS, compute_mask_validation_metrics
from floodguard.sar_raster_extract import (
    SAR_FEATURE_MANIFEST_COLUMNS,
    SARRasterExtractError,
    build_sar_feature_manifest,
    build_sentinel1_inputs_from_manifests,
    extract_sar_change_features,
)

WEAK_BASELINE_WARNING = (
    "Candidate metrics against manually digitized weak-reference mask. "
    "Non-operational. Not official validation. Not field validated."
)

WEAK_BASELINE_METRIC_COLUMNS: tuple[str, ...] = (
    "study_area",
    "processing_scope",
    "reference_status",
    "metric_status",
    *MASK_METRIC_COLUMNS,
    "sample_pixel_count",
    "reference_positive_pixel_count",
    "predicted_positive_pixel_count",
    "probability_threshold",
    "source_timestamp",
    "confidence_class",
    "warning_text",
    "assumptions",
)


class WeakReferenceBaselineError(ValueError):
    """Raised when the weak-reference baseline cannot run."""


def run_weak_reference_sar_baseline(
    file_manifest: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    output_shape: tuple[int, int] = (256, 256),
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run real Sentinel-1 non-ML baseline against a manual weak reference.

    This function intentionally does not clear or use the official Mae Sai gate.
    It only permits candidate metrics when the manual reference manifest is
    complete and the Sentinel-1 source rows have local path hints and checksums.
    """

    try:
        inputs = build_sentinel1_inputs_from_manifests(
            file_manifest,
            manual_reference_manifest,
        )
        features = extract_sar_change_features(
            inputs,
            output_shape=output_shape,
            probability_threshold=probability_threshold,
            dry_change_db=dry_change_db,
            flood_change_db=flood_change_db,
        )
    except SARRasterExtractError as exc:
        raise WeakReferenceBaselineError(str(exc)) from exc

    metrics = compute_mask_validation_metrics(
        features["binary_flood_extent"],
        features["reference_flood_extent"],
    )
    source_timestamp = _source_timestamp(file_manifest)
    metric_frame = _build_metric_frame(
        metrics,
        features,
        manual_reference_manifest,
        probability_threshold=probability_threshold,
        source_timestamp=source_timestamp,
    )
    feature_manifest = build_sar_feature_manifest(
        features,
        file_manifest=file_manifest,
        manual_reference_manifest=manual_reference_manifest,
        probability_threshold=probability_threshold,
        dry_change_db=dry_change_db,
        flood_change_db=flood_change_db,
        source_timestamp=source_timestamp,
    )
    return features, metric_frame, feature_manifest


def write_weak_reference_baseline_outputs(
    file_manifest: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    metrics_output_path: str | Path,
    feature_manifest_output_path: str | Path,
    summary_output_path: str | Path,
    output_shape: tuple[int, int] = (256, 256),
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
) -> dict[str, Path]:
    """Run and write weak-reference baseline metrics, manifest, and summary."""

    _assert_csv(metrics_output_path, "Weak baseline metrics")
    _assert_csv(feature_manifest_output_path, "Weak SAR feature manifest")
    summary_path = Path(summary_output_path)
    if summary_path.suffix.lower() != ".md":
        raise WeakReferenceBaselineError("Weak baseline summary output must be Markdown.")

    _features, metrics, feature_manifest = run_weak_reference_sar_baseline(
        file_manifest,
        manual_reference_manifest,
        output_shape=output_shape,
        probability_threshold=probability_threshold,
        dry_change_db=dry_change_db,
        flood_change_db=flood_change_db,
    )
    metrics_path = Path(metrics_output_path)
    feature_path = Path(feature_manifest_output_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(metrics_path, index=False)
    feature_manifest.to_csv(feature_path, index=False)
    summary_path.write_text(
        build_weak_reference_baseline_summary(metrics, feature_manifest),
        encoding="utf-8",
    )
    return {
        "metrics": metrics_path,
        "feature_manifest": feature_path,
        "summary": summary_path,
    }


def build_weak_reference_baseline_summary(
    metrics: pd.DataFrame,
    feature_manifest: pd.DataFrame,
    *,
    title: str = "Mae Sai Weak-Reference Sentinel-1 Baseline",
) -> str:
    """Build a Markdown summary for weak-reference candidate metrics."""

    _require_columns(metrics, WEAK_BASELINE_METRIC_COLUMNS, "weak baseline metrics")
    _require_columns(feature_manifest, SAR_FEATURE_MANIFEST_COLUMNS, "feature manifest")
    if metrics.empty or feature_manifest.empty:
        raise WeakReferenceBaselineError("Metrics and feature manifest must not be empty.")
    row = metrics.iloc[0]
    feature = feature_manifest.iloc[0]
    lines = [
        f"# {title}",
        "",
        WEAK_BASELINE_WARNING,
        "",
        "## Data Status",
        "",
        "- Sentinel-1 pre/post source files were read from local paths outside Git.",
        "- The reference layer is a manually digitized weak-reference candidate.",
        "- Official Mae Sai validation and ML-label gates remain blocked.",
        "",
        "## Source Products",
        "",
        f"- Pre-event Sentinel-1 product id: `{feature['pre_product_id']}`",
        f"- Post-event Sentinel-1 product id: `{feature['post_product_id']}`",
        f"- Reference candidate id: `{feature['reference_product_id']}`",
        f"- Source timestamp: {row['source_timestamp']}",
        "",
        "## Method Assumptions",
        "",
        "- VV/VH amplitude samples are converted to dB using `10 * log10(value)`.",
        "- `vv_drop` and `vh_drop` are pre-event dB minus post-event dB.",
        "- Ratios are post-event amplitude divided by pre-event amplitude.",
        "- Combined change score weights VH at 0.60 and VV at 0.40.",
        "- SAFE GCPs are fit to an affine transform for this first weak-reference clip.",
        "",
        "## Candidate Metrics",
        "",
        f"- IoU: {float(row['iou']):.6f}",
        f"- F1/Dice: {float(row['f1_dice']):.6f}",
        f"- Precision: {float(row['precision']):.6f}",
        f"- Recall: {float(row['recall']):.6f}",
        f"- Area error ratio: {float(row['area_error_ratio']):.6f}",
        f"- Sample pixels: {int(row['sample_pixel_count'])}",
        f"- Reference positive pixels: {int(row['reference_positive_pixel_count'])}",
        f"- Predicted positive pixels: {int(row['predicted_positive_pixel_count'])}",
        "",
        "## Failure Modes",
        "",
        "- SAR layover and terrain shadow can look water-like.",
        "- Permanent water can be confused with event flooding.",
        "- Urban double-bounce can hide or invert flood signals.",
        "- The manual mask is uncertain and intentionally conservative.",
        "- Pre/post acquisition dates may not match peak flood extent.",
        "- This first extractor is not terrain-corrected beyond SAFE GCP approximation.",
        "",
        "## Safety Note",
        "",
        "- Not official.",
        "- Not real-time.",
        "- Not field validated.",
        "- Not an emergency warning.",
        "",
    ]
    return "\n".join(lines)


def _build_metric_frame(
    metrics: dict[str, float | int],
    features: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    probability_threshold: float,
    source_timestamp: str,
) -> pd.DataFrame:
    manual_row = manual_reference_manifest.iloc[0]
    row = {
        "study_area": "Chiang Rai / Mae Sai 2024",
        "processing_scope": "weak_reference_real_sentinel1_non_ml_candidate",
        "reference_status": manual_row["reference_mask_status"],
        "metric_status": "candidate_weak_reference_metrics",
        **metrics,
        "sample_pixel_count": int(len(features)),
        "reference_positive_pixel_count": int(features["reference_flood_extent"].sum()),
        "predicted_positive_pixel_count": int(features["binary_flood_extent"].sum()),
        "probability_threshold": probability_threshold,
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "warning_text": WEAK_BASELINE_WARNING,
        "assumptions": (
            "Real CDSE Sentinel-1 pre/post rasters compared against a manually "
            "digitized weak-reference candidate. Non-operational and not official."
        ),
    }
    return pd.DataFrame([row], columns=WEAK_BASELINE_METRIC_COLUMNS)


def _source_timestamp(file_manifest: pd.DataFrame) -> str:
    _require_columns(
        file_manifest,
        ("candidate_use", "source_name", "product_id"),
        "Mae Sai file manifest",
    )
    post = file_manifest[
        file_manifest["candidate_use"].astype(str)
        == "post-event SAR source for non-ML baseline"
    ]
    if not post.empty:
        name = str(post.iloc[0]["source_name"])
        product_id = str(post.iloc[0]["product_id"])
        if product_id == "20a9c3b8-37df-46d5-81d8-d63c7e460225":
            return "2024-09-15T23:16:01Z"
        if product_id == "6a02d487-68fa-4be7-9628-f312b9049967":
            return "2024-09-18T11:31:07Z"
        if "2024-09-15" in name:
            return "2024-09-15T23:16:01Z"
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_csv(output_path: str | Path, label: str) -> None:
    if Path(output_path).suffix.lower() != ".csv":
        raise WeakReferenceBaselineError(f"{label} output must be CSV.")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise WeakReferenceBaselineError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
