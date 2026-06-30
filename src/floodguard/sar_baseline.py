"""Synthetic SAR baseline helpers for ML-readiness testing.

The functions in this module operate on tiny tabular fixtures only. They do not
read Sentinel-1 products, raster files, or any real remote-sensing assets.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

SAR_INPUT_COLUMNS: tuple[str, ...] = (
    "pixel_id",
    "row",
    "col",
    "pre_vv_db",
    "post_vv_db",
    "pre_vh_db",
    "post_vh_db",
    "reference_flood_extent",
)

SAR_OUTPUT_COLUMNS: tuple[str, ...] = (
    "pixel_id",
    "row",
    "col",
    "pre_vv_db",
    "post_vv_db",
    "pre_vh_db",
    "post_vh_db",
    "vv_drop_db",
    "vh_drop_db",
    "combined_drop_db",
    "flood_probability_0_1",
    "binary_flood_extent",
    "reference_flood_extent",
    "confidence_class",
    "assumptions",
)

MASK_METRIC_COLUMNS: tuple[str, ...] = (
    "true_positive",
    "false_positive",
    "false_negative",
    "true_negative",
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "area_error_ratio",
)


class SARBaselineError(ValueError):
    """Raised when SAR baseline inputs violate the synthetic contract."""


def run_threshold_sar_baseline(
    pixels: pd.DataFrame,
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
) -> pd.DataFrame:
    """Run a deterministic non-ML flood baseline on synthetic SAR pixels.

    The baseline treats a larger pre/post backscatter drop as more likely flood
    signal. It is deliberately simple so validation metrics and downstream
    decision-layer wiring can be tested before real imagery is licensed.
    """

    if not 0 <= probability_threshold <= 1:
        raise SARBaselineError("probability_threshold must be between 0 and 1.")
    if flood_change_db <= dry_change_db:
        raise SARBaselineError("flood_change_db must be greater than dry_change_db.")

    _validate_columns(pixels, SAR_INPUT_COLUMNS, "SAR pixel")
    frame = pixels.copy()
    numeric_columns = (
        "row",
        "col",
        "pre_vv_db",
        "post_vv_db",
        "pre_vh_db",
        "post_vh_db",
        "reference_flood_extent",
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise SARBaselineError(f"{column} must be numeric.")
    _validate_binary(frame["reference_flood_extent"], "reference_flood_extent")

    frame["vv_drop_db"] = frame["pre_vv_db"] - frame["post_vv_db"]
    frame["vh_drop_db"] = frame["pre_vh_db"] - frame["post_vh_db"]
    frame["combined_drop_db"] = 0.6 * frame["vv_drop_db"] + 0.4 * frame["vh_drop_db"]
    frame[["vv_drop_db", "vh_drop_db", "combined_drop_db"]] = frame[
        ["vv_drop_db", "vh_drop_db", "combined_drop_db"]
    ].round(3)
    frame["flood_probability_0_1"] = (
        (frame["combined_drop_db"] - dry_change_db) / (flood_change_db - dry_change_db)
    ).clip(lower=0.0, upper=1.0)
    frame["flood_probability_0_1"] = frame["flood_probability_0_1"].round(3)
    frame["binary_flood_extent"] = (
        frame["flood_probability_0_1"] >= probability_threshold
    ).astype(int)
    frame["reference_flood_extent"] = frame["reference_flood_extent"].astype(int)
    frame["confidence_class"] = frame["flood_probability_0_1"].map(_confidence_class)
    frame["assumptions"] = (
        "Synthetic non-ML SAR threshold fixture; not real Sentinel-1 processing."
    )
    return frame.loc[:, SAR_OUTPUT_COLUMNS]


def compute_mask_validation_metrics(
    predicted_mask: Sequence[int | bool] | pd.Series,
    reference_mask: Sequence[int | bool] | pd.Series,
) -> dict[str, float | int]:
    """Compute binary flood-mask metrics from predicted and reference masks."""

    predicted = _to_binary_series(predicted_mask, "predicted_mask")
    reference = _to_binary_series(reference_mask, "reference_mask")
    if len(predicted) != len(reference):
        raise SARBaselineError("predicted_mask and reference_mask must have equal length.")

    true_positive = int(((predicted == 1) & (reference == 1)).sum())
    false_positive = int(((predicted == 1) & (reference == 0)).sum())
    false_negative = int(((predicted == 0) & (reference == 1)).sum())
    true_negative = int(((predicted == 0) & (reference == 0)).sum())
    predicted_area = true_positive + false_positive
    reference_area = true_positive + false_negative

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "iou": _safe_ratio(true_positive, true_positive + false_positive + false_negative),
        "f1_dice": _safe_ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative),
        "precision": _safe_ratio(true_positive, true_positive + false_positive),
        "recall": _safe_ratio(true_positive, true_positive + false_negative),
        "area_error_ratio": _safe_ratio(predicted_area - reference_area, reference_area),
    }


def validate_threshold_sar_baseline(pixels: pd.DataFrame) -> pd.DataFrame:
    """Run the synthetic baseline and return one row of validation metrics."""

    baseline = run_threshold_sar_baseline(pixels)
    metrics = compute_mask_validation_metrics(
        baseline["binary_flood_extent"],
        baseline["reference_flood_extent"],
    )
    return pd.DataFrame([metrics], columns=MASK_METRIC_COLUMNS)


def _confidence_class(probability: float) -> str:
    if probability <= 0.2 or probability >= 0.8:
        return "high"
    return "medium"


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0 if numerator == 0 else float("nan")
    return round(float(numerator) / float(denominator), 6)


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise SARBaselineError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _validate_binary(values: pd.Series, column_name: str) -> None:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        raise SARBaselineError(f"{column_name} must contain only binary 0/1 values.")
    invalid_values = sorted(set(numeric.dropna().astype(float)) - {0.0, 1.0})
    if invalid_values:
        raise SARBaselineError(
            f"{column_name} must contain only binary 0/1 values."
        )


def _to_binary_series(
    values: Sequence[int | bool] | pd.Series,
    column_name: str,
) -> pd.Series:
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    _validate_binary(series, column_name)
    return series.astype(int)
