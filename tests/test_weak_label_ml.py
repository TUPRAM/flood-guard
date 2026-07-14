from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.weak_label_ml import (
    WEAK_LABEL_ML_WARNING,
    WeakLabelMLError,
    build_weak_label_ml_summary,
    run_weak_label_ml_experiment,
    write_weak_label_ml_outputs,
)


def test_weak_label_ml_compares_against_spatial_holdout_baseline() -> None:
    features = _features(baseline_mode="all_dry")

    _predictions, metrics, manifest = run_weak_label_ml_experiment(
        features,
        _feature_manifest(),
        holdout_block_size=2,
        epochs=500,
    )

    row = metrics.iloc[0]
    assert row["split_strategy"] == "spatial_block_holdout"
    assert row["label_status"] == "weak_label_not_official_not_field_validated"
    assert row["ml_f1_dice"] > row["baseline_f1_dice"]
    assert row["ml_iou"] > row["baseline_iou"]
    assert row["can_feed_decision_layer"] == False
    assert manifest.iloc[0]["can_feed_decision_layer"] == False
    assert row["ml_improves_baseline"] == True
    assert manifest.iloc[0]["pre_product_id"] == "pre-product"
    assert manifest.iloc[0]["post_product_id"] == "post-product"


def test_weak_label_ml_does_not_feed_when_baseline_is_not_improved() -> None:
    features = _features(baseline_mode="perfect")

    _predictions, metrics, manifest = run_weak_label_ml_experiment(
        features,
        _feature_manifest(),
        holdout_block_size=2,
        epochs=500,
    )

    row = metrics.iloc[0]
    assert row["baseline_f1_dice"] == 1.0
    assert row["can_feed_decision_layer"] == False
    assert manifest.iloc[0]["can_feed_decision_layer"] == False


def test_weak_label_ml_rejects_missing_columns() -> None:
    with pytest.raises(WeakLabelMLError, match="vh_ratio"):
        run_weak_label_ml_experiment(
            _features().drop(columns=["vh_ratio"]),
            _feature_manifest(),
            holdout_block_size=2,
        )


def test_weak_label_ml_rejects_one_class_reference_labels() -> None:
    features = _features()
    features["reference_flood_extent"] = 0

    with pytest.raises(WeakLabelMLError, match="both weak-label classes"):
        run_weak_label_ml_experiment(
            features,
            _feature_manifest(),
            holdout_block_size=2,
        )


def test_weak_label_ml_summary_preserves_warning_language() -> None:
    _predictions, metrics, manifest = run_weak_label_ml_experiment(
        _features(baseline_mode="all_dry"),
        _feature_manifest(),
        holdout_block_size=2,
        epochs=500,
    )

    summary = build_weak_label_ml_summary(metrics, manifest)

    assert "weak-label experiment" in summary.lower()
    assert "Not official labels" in summary
    assert "Not field validation" in summary
    assert "Non-ML baseline" in summary
    assert "not eligible to feed the decision layer" in summary


def test_write_weak_label_ml_outputs_writes_compact_outputs(tmp_path: Path) -> None:
    written = write_weak_label_ml_outputs(
        _features(baseline_mode="all_dry"),
        _feature_manifest(),
        metrics_output_path=tmp_path / "metrics.csv",
        prediction_manifest_output_path=tmp_path / "prediction_manifest.csv",
        summary_output_path=tmp_path / "summary.md",
    )

    assert written["metrics"].exists()
    assert written["prediction_manifest"].exists()
    assert written["summary"].exists()
    assert WEAK_LABEL_ML_WARNING in written["summary"].read_text(encoding="utf-8")


def _features(baseline_mode: str = "all_dry") -> pd.DataFrame:
    rows = []
    for row in range(8):
        for col in range(8):
            label = int(row + col >= 7)
            signal = 5.0 if label else 0.3
            baseline = 0 if baseline_mode == "all_dry" else label
            rows.append(
                {
                    "pixel_id": f"PX-{row}-{col}",
                    "row": row,
                    "col": col,
                    "pre_vv_db": 10.0,
                    "post_vv_db": 10.0 - signal,
                    "pre_vh_db": 8.0,
                    "post_vh_db": 8.0 - signal,
                    "vv_drop": signal,
                    "vh_drop": signal + (0.1 if row % 2 == 0 else -0.1),
                    "vv_ratio": 0.2 if label else 0.95,
                    "vh_ratio": 0.15 if label else 0.9,
                    "combined_sar_change_score": signal,
                    "flood_probability_0_1": 0.9 if label else 0.05,
                    "binary_flood_extent": baseline,
                    "reference_flood_extent": label,
                }
            )
    return pd.DataFrame(rows)


def _feature_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "study_area": "Chiang Rai / Mae Sai 2024",
                "pre_product_id": "pre-product",
                "post_product_id": "post-product",
                "reference_product_id": "MANUAL-QGIS-MAE-SAI-2024",
                "reference_status": "weak_reference_candidate",
                "source_timestamp": "2024-09-15T23:16:01Z",
            }
        ]
    )
