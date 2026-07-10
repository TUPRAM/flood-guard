"""Weak-label ML experiment for Mae Sai Sentinel-1 candidate features.

This module intentionally stays dependency-light and auditable. It trains a
small logistic classifier from the weak-reference SAR feature table and reports
candidate metrics against a spatial holdout. The labels remain manual
weak-reference labels, not official flood validation truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from floodguard.sar_baseline import MASK_METRIC_COLUMNS, compute_mask_validation_metrics

WEAK_LABEL_ML_WARNING = (
    "Weak-label experiment against manually digitized weak-reference mask. "
    "Non-operational. Not official labels. Not field validation."
)

WEAK_LABEL_FEATURE_COLUMNS: tuple[str, ...] = (
    "vv_drop",
    "vh_drop",
    "vv_ratio",
    "vh_ratio",
    "combined_sar_change_score",
)

WEAK_LABEL_ML_PREDICTION_COLUMNS: tuple[str, ...] = (
    "pixel_id",
    "row",
    "col",
    "split",
    "weak_label_ml_probability_0_1",
    "weak_label_ml_binary_flood_extent",
    "baseline_binary_flood_extent",
    "reference_flood_extent",
)

WEAK_LABEL_ML_METRIC_COLUMNS: tuple[str, ...] = (
    "experiment_name",
    "study_area",
    "model_family",
    "label_source",
    "label_status",
    "split_strategy",
    "feature_columns",
    "train_sample_count",
    "holdout_sample_count",
    "decision_threshold",
    "baseline_iou",
    "ml_iou",
    "delta_iou",
    "baseline_f1_dice",
    "ml_f1_dice",
    "delta_f1_dice",
    "baseline_precision",
    "ml_precision",
    "delta_precision",
    "baseline_recall",
    "ml_recall",
    "delta_recall",
    "baseline_area_error_ratio",
    "ml_area_error_ratio",
    "delta_area_error_ratio",
    "ml_improves_baseline",
    "ml_complements_baseline",
    "can_feed_decision_layer",
    "source_timestamp",
    "confidence_class",
    "warning_text",
    "assumptions",
)

WEAK_LABEL_ML_PREDICTION_MANIFEST_COLUMNS: tuple[str, ...] = (
    "study_area",
    "processing_scope",
    "model_family",
    "pre_product_id",
    "post_product_id",
    "reference_product_id",
    "reference_status",
    "sample_pixel_count",
    "train_sample_count",
    "holdout_sample_count",
    "feature_columns",
    "decision_threshold",
    "mean_ml_flood_probability_0_1",
    "holdout_mean_ml_flood_probability_0_1",
    "ml_predicted_positive_pixel_count",
    "baseline_predicted_positive_pixel_count",
    "reference_positive_pixel_count",
    "split_strategy",
    "can_feed_decision_layer",
    "source_timestamp",
    "confidence_class",
    "warning_text",
    "assumptions",
)


class WeakLabelMLError(ValueError):
    """Raised when the weak-label ML experiment cannot run."""


def run_weak_label_ml_experiment(
    features: pd.DataFrame,
    feature_manifest: pd.DataFrame | None = None,
    *,
    feature_columns: Sequence[str] = WEAK_LABEL_FEATURE_COLUMNS,
    holdout_block_size: int = 32,
    epochs: int = 700,
    learning_rate: float = 0.08,
    l2: float = 0.001,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train and evaluate a small logistic model on weak-reference labels.

    Evaluation uses a spatial block holdout. The non-ML threshold baseline
    (`binary_flood_extent`) is evaluated on the same holdout and remains the
    benchmark for the ML candidate.
    """

    import numpy as np

    if holdout_block_size <= 0:
        raise WeakLabelMLError("holdout_block_size must be positive.")
    if epochs <= 0:
        raise WeakLabelMLError("epochs must be positive.")
    if learning_rate <= 0:
        raise WeakLabelMLError("learning_rate must be positive.")
    if l2 < 0:
        raise WeakLabelMLError("l2 must be non-negative.")

    frame = _validated_feature_frame(features, feature_columns)
    split = _spatial_holdout_split(frame, holdout_block_size=holdout_block_size)
    train_mask = split == "train"
    holdout_mask = split == "holdout"

    x_train = frame.loc[train_mask, list(feature_columns)].to_numpy(dtype=float)
    y_train = frame.loc[train_mask, "reference_flood_extent"].to_numpy(dtype=float)
    x_holdout = frame.loc[holdout_mask, list(feature_columns)].to_numpy(dtype=float)
    y_holdout = frame.loc[holdout_mask, "reference_flood_extent"].to_numpy(dtype=int)

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    train_scaled = (x_train - mean) / std
    holdout_scaled = (x_holdout - mean) / std

    weights = _fit_weighted_logistic_regression(
        train_scaled,
        y_train,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
    )
    train_probabilities = _predict_logistic_probability(train_scaled, weights)
    holdout_probabilities = _predict_logistic_probability(holdout_scaled, weights)
    threshold = _select_probability_threshold(train_probabilities, y_train.astype(int))
    holdout_prediction = (holdout_probabilities >= threshold).astype(int)

    predictions = frame.loc[:, ["pixel_id", "row", "col"]].copy()
    predictions["split"] = split
    all_scaled = (frame.loc[:, list(feature_columns)].to_numpy(dtype=float) - mean) / std
    predictions["weak_label_ml_probability_0_1"] = _predict_logistic_probability(
        all_scaled,
        weights,
    ).round(6)
    predictions["weak_label_ml_binary_flood_extent"] = (
        predictions["weak_label_ml_probability_0_1"] >= threshold
    ).astype(int)
    predictions["baseline_binary_flood_extent"] = frame["binary_flood_extent"].astype(int)
    predictions["reference_flood_extent"] = frame["reference_flood_extent"].astype(int)

    baseline_holdout = (
        frame.loc[holdout_mask, "binary_flood_extent"].astype(int).to_numpy()
    )
    baseline_metrics = compute_mask_validation_metrics(baseline_holdout, y_holdout)
    ml_metrics = compute_mask_validation_metrics(holdout_prediction, y_holdout)
    source_timestamp = _manifest_value(
        feature_manifest,
        "source_timestamp",
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    metrics_frame = _build_metric_frame(
        baseline_metrics,
        ml_metrics,
        train_sample_count=int(train_mask.sum()),
        holdout_sample_count=int(holdout_mask.sum()),
        decision_threshold=threshold,
        feature_columns=feature_columns,
        source_timestamp=source_timestamp,
    )
    prediction_manifest = _build_prediction_manifest(
        predictions,
        feature_manifest,
        feature_columns=feature_columns,
        decision_threshold=threshold,
        train_sample_count=int(train_mask.sum()),
        holdout_sample_count=int(holdout_mask.sum()),
        can_feed_decision_layer=bool(metrics_frame.iloc[0]["can_feed_decision_layer"]),
        source_timestamp=source_timestamp,
    )
    return (
        predictions.loc[:, WEAK_LABEL_ML_PREDICTION_COLUMNS],
        metrics_frame,
        prediction_manifest,
    )


def write_weak_label_ml_outputs(
    features: pd.DataFrame,
    feature_manifest: pd.DataFrame | None = None,
    *,
    metrics_output_path: str | Path,
    prediction_manifest_output_path: str | Path,
    summary_output_path: str | Path,
    feature_columns: Sequence[str] = WEAK_LABEL_FEATURE_COLUMNS,
) -> dict[str, Path]:
    """Run the weak-label ML experiment and write compact derived outputs."""

    _assert_csv(metrics_output_path, "Weak-label ML metrics")
    _assert_csv(prediction_manifest_output_path, "Weak-label ML prediction manifest")
    summary_path = Path(summary_output_path)
    if summary_path.suffix.lower() != ".md":
        raise WeakLabelMLError("Weak-label ML summary output must be Markdown.")

    _predictions, metrics, prediction_manifest = run_weak_label_ml_experiment(
        features,
        feature_manifest,
        feature_columns=feature_columns,
    )
    metrics_path = Path(metrics_output_path)
    manifest_path = Path(prediction_manifest_output_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(metrics_path, index=False)
    prediction_manifest.to_csv(manifest_path, index=False)
    summary_path.write_text(
        build_weak_label_ml_summary(metrics, prediction_manifest),
        encoding="utf-8",
    )
    return {
        "metrics": metrics_path,
        "prediction_manifest": manifest_path,
        "summary": summary_path,
    }


def build_weak_label_ml_summary(
    metrics: pd.DataFrame,
    prediction_manifest: pd.DataFrame,
    *,
    title: str = "Mae Sai Weak-Label ML Experiment",
) -> str:
    """Build a judge-readable weak-label ML experiment summary."""

    _require_columns(metrics, WEAK_LABEL_ML_METRIC_COLUMNS, "weak-label ML metrics")
    _require_columns(
        prediction_manifest,
        WEAK_LABEL_ML_PREDICTION_MANIFEST_COLUMNS,
        "weak-label ML prediction manifest",
    )
    if metrics.empty or prediction_manifest.empty:
        raise WeakLabelMLError("Metrics and prediction manifest must not be empty.")

    metric = metrics.iloc[0]
    manifest = prediction_manifest.iloc[0]
    can_feed = bool(metric["can_feed_decision_layer"])
    feed_text = (
        "The ML probability may feed a candidate decision-layer run because it "
        "improves or complements the non-ML threshold baseline."
        if can_feed
        else "The ML probability is not eligible to feed the decision layer because "
        "it does not improve or complement the non-ML threshold baseline."
    )
    lines = [
        f"# {title}",
        "",
        WEAK_LABEL_ML_WARNING,
        "",
        "## Data Status",
        "",
        "- Sentinel-1 features come from the weak-reference real-data SAR baseline.",
        "- Labels come from the manual weak-reference mask, not official labels.",
        "- This is not field validation and not an emergency warning.",
        "",
        "## Model",
        "",
        f"- Model family: {metric['model_family']}",
        f"- Features: {metric['feature_columns']}",
        f"- Split strategy: {metric['split_strategy']}",
        f"- Train samples: {int(metric['train_sample_count'])}",
        f"- Holdout samples: {int(metric['holdout_sample_count'])}",
        f"- Decision threshold: {float(metric['decision_threshold']):.3f}",
        "",
        "## Baseline Comparison",
        "",
        "| Metric | Non-ML baseline | Weak-label ML | Delta |",
        "| --- | ---: | ---: | ---: |",
        _metric_row(metric, "IoU", "iou"),
        _metric_row(metric, "F1/Dice", "f1_dice"),
        _metric_row(metric, "Precision", "precision"),
        _metric_row(metric, "Recall", "recall"),
        _metric_row(metric, "Area error ratio", "area_error_ratio"),
        "",
        "## Decision-Layer Eligibility",
        "",
        f"- ML improves baseline: {metric['ml_improves_baseline']}",
        f"- ML complements baseline: {metric['ml_complements_baseline']}",
        f"- Can feed candidate decision layer: {metric['can_feed_decision_layer']}",
        f"- {feed_text}",
        "",
        "## Source Products",
        "",
        f"- Pre-event Sentinel-1 product id: `{manifest['pre_product_id']}`",
        f"- Post-event Sentinel-1 product id: `{manifest['post_product_id']}`",
        f"- Reference candidate id: `{manifest['reference_product_id']}`",
        f"- Reference status: {manifest['reference_status']}",
        f"- Source timestamp: {manifest['source_timestamp']}",
        "",
        "## Safety Note",
        "",
        "- Weak-label experiment.",
        "- Not official labels.",
        "- Not field validation.",
        "- Not official flood validation.",
        "- Not an emergency warning.",
        "",
    ]
    return "\n".join(lines)


def _validated_feature_frame(
    features: pd.DataFrame,
    feature_columns: Sequence[str],
) -> pd.DataFrame:
    required_columns = (
        "pixel_id",
        "row",
        "col",
        "binary_flood_extent",
        "reference_flood_extent",
        *tuple(feature_columns),
    )
    _require_columns(features, required_columns, "weak-label ML feature table")
    frame = features.copy()
    for column in ("row", "col", "binary_flood_extent", "reference_flood_extent", *feature_columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise WeakLabelMLError(f"{column} must be numeric.")
    for column in ("binary_flood_extent", "reference_flood_extent"):
        values = set(frame[column].astype(int).unique())
        if not values.issubset({0, 1}):
            raise WeakLabelMLError(f"{column} must contain only 0/1 values.")
        frame[column] = frame[column].astype(int)
    if frame["reference_flood_extent"].nunique() < 2:
        raise WeakLabelMLError(
            "reference_flood_extent must include both weak-label classes."
        )
    return frame


def _spatial_holdout_split(
    frame: pd.DataFrame,
    *,
    holdout_block_size: int,
) -> pd.Series:
    row_span = int(frame["row"].max() - frame["row"].min() + 1)
    col_span = int(frame["col"].max() - frame["col"].min() + 1)
    grid_extent = max(row_span, col_span)
    effective_block_size = min(holdout_block_size, max(1, grid_extent // 4))
    block_row = (frame["row"].astype(int) // effective_block_size).astype(int)
    block_col = (frame["col"].astype(int) // effective_block_size).astype(int)
    block_key = block_row + 2 * block_col
    best_split: pd.Series | None = None
    best_score = -1
    for pattern in range(4):
        holdout = block_key % 4 == pattern
        train = ~holdout
        if not holdout.any() or not train.any():
            continue
        train_labels = set(frame.loc[train, "reference_flood_extent"].astype(int))
        holdout_labels = set(frame.loc[holdout, "reference_flood_extent"].astype(int))
        score = len(train_labels) + len(holdout_labels)
        if train_labels == {0, 1} and holdout_labels == {0, 1}:
            split = pd.Series("train", index=frame.index, dtype="object")
            split.loc[holdout] = "holdout"
            return split
        if score > best_score and train_labels == {0, 1} and 1 in holdout_labels:
            best_split = pd.Series("train", index=frame.index, dtype="object")
            best_split.loc[holdout] = "holdout"
            best_score = score
    if best_split is not None:
        return best_split
    raise WeakLabelMLError(
        "Could not create a spatial holdout with weak-label positives in train and holdout."
    )


def _fit_weighted_logistic_regression(
    x_train: object,
    y_train: object,
    *,
    epochs: int,
    learning_rate: float,
    l2: float,
) -> object:
    import numpy as np

    x = np.asarray(x_train, dtype=float)
    y = np.asarray(y_train, dtype=float)
    if y.sum() == 0 or y.sum() == len(y):
        raise WeakLabelMLError("Training split must contain both weak-label classes.")
    design = np.column_stack([np.ones(len(x)), x])
    weights = np.zeros(design.shape[1], dtype=float)
    positive_count = float(y.sum())
    negative_count = float(len(y) - positive_count)
    sample_weights = np.where(
        y == 1,
        len(y) / (2.0 * positive_count),
        len(y) / (2.0 * negative_count),
    )
    sample_weights = sample_weights / sample_weights.mean()
    for _epoch in range(epochs):
        logits = np.clip(design @ weights, -40.0, 40.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        errors = (probabilities - y) * sample_weights
        gradient = (design.T @ errors) / len(y)
        gradient[1:] += l2 * weights[1:]
        weights -= learning_rate * gradient
    return weights


def _predict_logistic_probability(x_values: object, weights: object) -> object:
    import numpy as np

    x = np.asarray(x_values, dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    logits = np.clip(design @ np.asarray(weights, dtype=float), -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-logits))


def _select_probability_threshold(probabilities: object, labels: object) -> float:
    import numpy as np

    probs = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=int)
    best_threshold = 0.5
    best_score = (-1.0, -1.0, -1.0)
    for threshold in np.linspace(0.05, 0.95, 91):
        predicted = (probs >= threshold).astype(int)
        metrics = compute_mask_validation_metrics(predicted, y)
        score = (
            float(metrics["f1_dice"]),
            float(metrics["iou"]),
            float(metrics["precision"]),
        )
        if score > best_score:
            best_score = score
            best_threshold = round(float(threshold), 3)
    return best_threshold


def _build_metric_frame(
    baseline_metrics: dict[str, float | int],
    ml_metrics: dict[str, float | int],
    *,
    train_sample_count: int,
    holdout_sample_count: int,
    decision_threshold: float,
    feature_columns: Sequence[str],
    source_timestamp: str,
) -> pd.DataFrame:
    improves = (
        float(ml_metrics["f1_dice"]) > float(baseline_metrics["f1_dice"])
        or float(ml_metrics["iou"]) > float(baseline_metrics["iou"])
    )
    complements = _ml_complements_baseline(baseline_metrics, ml_metrics)
    can_feed = improves or complements
    row = {
        "experiment_name": "mae_sai_weak_label_logistic_v1",
        "study_area": "Chiang Rai / Mae Sai 2024",
        "model_family": "logistic_regression_from_scratch",
        "label_source": "manual weak-reference mask",
        "label_status": "weak_label_not_official_not_field_validated",
        "split_strategy": "spatial_block_holdout",
        "feature_columns": "|".join(feature_columns),
        "train_sample_count": train_sample_count,
        "holdout_sample_count": holdout_sample_count,
        "decision_threshold": decision_threshold,
        **_metric_delta_columns("iou", baseline_metrics, ml_metrics),
        **_metric_delta_columns("f1_dice", baseline_metrics, ml_metrics),
        **_metric_delta_columns("precision", baseline_metrics, ml_metrics),
        **_metric_delta_columns("recall", baseline_metrics, ml_metrics),
        **_metric_delta_columns("area_error_ratio", baseline_metrics, ml_metrics),
        "ml_improves_baseline": bool(improves),
        "ml_complements_baseline": bool(complements),
        "can_feed_decision_layer": bool(can_feed),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "warning_text": WEAK_LABEL_ML_WARNING,
        "assumptions": (
            "Logistic regression trained on manual weak-reference labels with "
            "a spatial holdout. Candidate metrics only; not official labels or "
            "field validation."
        ),
    }
    return pd.DataFrame([row], columns=WEAK_LABEL_ML_METRIC_COLUMNS)


def _build_prediction_manifest(
    predictions: pd.DataFrame,
    feature_manifest: pd.DataFrame | None,
    *,
    feature_columns: Sequence[str],
    decision_threshold: float,
    train_sample_count: int,
    holdout_sample_count: int,
    can_feed_decision_layer: bool,
    source_timestamp: str,
) -> pd.DataFrame:
    row = {
        "study_area": _manifest_value(
            feature_manifest,
            "study_area",
            "Chiang Rai / Mae Sai 2024",
        ),
        "processing_scope": "weak_label_ml_candidate",
        "model_family": "logistic_regression_from_scratch",
        "pre_product_id": _manifest_value(feature_manifest, "pre_product_id", ""),
        "post_product_id": _manifest_value(feature_manifest, "post_product_id", ""),
        "reference_product_id": _manifest_value(feature_manifest, "reference_product_id", ""),
        "reference_status": _manifest_value(feature_manifest, "reference_status", ""),
        "sample_pixel_count": int(len(predictions)),
        "train_sample_count": train_sample_count,
        "holdout_sample_count": holdout_sample_count,
        "feature_columns": "|".join(feature_columns),
        "decision_threshold": decision_threshold,
        "mean_ml_flood_probability_0_1": round(
            float(predictions["weak_label_ml_probability_0_1"].mean()),
            6,
        ),
        "holdout_mean_ml_flood_probability_0_1": round(
            float(
                predictions.loc[
                    predictions["split"] == "holdout",
                    "weak_label_ml_probability_0_1",
                ].mean()
            ),
            6,
        ),
        "ml_predicted_positive_pixel_count": int(
            predictions["weak_label_ml_binary_flood_extent"].sum()
        ),
        "baseline_predicted_positive_pixel_count": int(
            predictions["baseline_binary_flood_extent"].sum()
        ),
        "reference_positive_pixel_count": int(predictions["reference_flood_extent"].sum()),
        "split_strategy": "spatial_block_holdout",
        "can_feed_decision_layer": bool(can_feed_decision_layer),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "warning_text": WEAK_LABEL_ML_WARNING,
        "assumptions": (
            "Compact manifest only. No raw Sentinel-1 rasters, source GeoPackage, "
            "or full per-pixel prediction table is written to Git."
        ),
    }
    return pd.DataFrame([row], columns=WEAK_LABEL_ML_PREDICTION_MANIFEST_COLUMNS)


def _metric_delta_columns(
    metric_name: str,
    baseline_metrics: dict[str, float | int],
    ml_metrics: dict[str, float | int],
) -> dict[str, float]:
    baseline = float(baseline_metrics[metric_name])
    ml_value = float(ml_metrics[metric_name])
    return {
        f"baseline_{metric_name}": round(baseline, 6),
        f"ml_{metric_name}": round(ml_value, 6),
        f"delta_{metric_name}": round(ml_value - baseline, 6),
    }


def _ml_complements_baseline(
    baseline_metrics: dict[str, float | int],
    ml_metrics: dict[str, float | int],
) -> bool:
    baseline_precision = float(baseline_metrics["precision"])
    baseline_recall = float(baseline_metrics["recall"])
    ml_precision = float(ml_metrics["precision"])
    ml_recall = float(ml_metrics["recall"])
    precision_gain = (
        ml_precision > baseline_precision
        and ml_recall >= 0.5 * baseline_recall
    )
    recall_gain = (
        ml_recall > baseline_recall
        and ml_precision >= 0.5 * baseline_precision
    )
    return precision_gain or recall_gain


def _metric_row(metric: pd.Series, label: str, key: str) -> str:
    return (
        f"| {label} | {float(metric[f'baseline_{key}']):.6f} | "
        f"{float(metric[f'ml_{key}']):.6f} | "
        f"{float(metric[f'delta_{key}']):+.6f} |"
    )


def _manifest_value(
    manifest: pd.DataFrame | None,
    column: str,
    default: str,
) -> str:
    if manifest is None or manifest.empty or column not in manifest.columns:
        return default
    value = str(manifest.iloc[0][column])
    return value if value and value.lower() != "nan" else default


def _assert_csv(output_path: str | Path, label: str) -> None:
    if Path(output_path).suffix.lower() != ".csv":
        raise WeakLabelMLError(f"{label} output must be CSV.")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise WeakLabelMLError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )
