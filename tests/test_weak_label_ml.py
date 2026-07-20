from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.weak_label_ml import (
    WEAK_LABEL_ML_WARNING,
    WeakLabelMLError,
    build_weak_label_ml_summary,
    require_ml_label_authorization,
    run_weak_label_ml_experiment,
    write_weak_label_ml_outputs,
)


def test_real_data_ml_gate_rejects_candidate_metric_only_reference() -> None:
    manifest = pd.DataFrame(
        [
            {
                "reference_id": "MS-MANUAL-CROSSBORDER-001",
                "reference_mask_status": "weak_reference_candidate",
                "unqualified_ml_label_allowed": False,
                "not_official_status": "confirmed_true",
            }
        ]
    )

    with pytest.raises(WeakLabelMLError, match="not qualified_expert_or_adjudicated"):
        require_ml_label_authorization(manifest)


def test_real_data_ml_gate_rejects_structural_claim_without_signed_receipts() -> None:
    with pytest.raises(WeakLabelMLError, match="summary authorization row is not signed"):
        require_ml_label_authorization(_authorized_reference_manifest())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ml_label_use_allowed", False, "ml_label_use_allowed must be explicit true"),
        ("sha256_status", "recorded", "checksum status is not verified"),
        (
            "reviewer_qualification_status",
            "pending",
            "reviewer calibration is not qualified",
        ),
        (
            "unresolved_disagreement_count",
            1,
            "reviewer disagreements remain unresolved",
        ),
        ("spatial_holdout_status", "pending", "membership is not verified"),
        (
            "execution_authorization_status",
            "missing",
            "bounded execution authorization is missing",
        ),
    ],
)
def test_real_data_ml_gate_rejects_incomplete_evidence(
    field: str,
    value: object,
    message: str,
) -> None:
    manifest = _authorized_reference_manifest()
    manifest.loc[0, field] = value

    with pytest.raises(WeakLabelMLError, match=message):
        require_ml_label_authorization(manifest)


def test_real_data_ml_gate_rejects_reused_partition_receipt() -> None:
    manifest = _authorized_reference_manifest()
    manifest.loc[0, "final_holdout_partition_sha256"] = manifest.loc[
        0, "training_partition_sha256"
    ]

    with pytest.raises(WeakLabelMLError, match="partition receipts must be distinct"):
        require_ml_label_authorization(manifest)


def test_mae_sai_ml_cli_blocks_before_training_on_current_reference() -> None:
    repo_root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/run_mae_sai_weak_label_ml.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "not qualified_expert_or_adjudicated" in result.stderr


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


def test_weak_label_ml_summary_marks_retired_source_pair_as_historical() -> None:
    _predictions, metrics, manifest = run_weak_label_ml_experiment(
        _features(baseline_mode="all_dry"),
        _feature_manifest(),
        holdout_block_size=2,
        epochs=500,
    )
    manifest.loc[0, "pre_product_id"] = "b09f96ca-4a60-43e7-9b8d-158022f0e5bf"
    manifest.loc[0, "post_product_id"] = "20a9c3b8-37df-46d5-81d8-d63c7e460225"

    summary = build_weak_label_ml_summary(metrics, manifest)

    assert "Historical Weak-Label ML Experiment (Retired Source Pair)" in summary
    assert "historical retired-source screening evidence only" in summary
    assert "not comparable to the active same-track original-SAFE baseline" in summary


def test_write_weak_label_ml_outputs_rejects_unsigned_summary_contract(
    tmp_path: Path,
) -> None:
    with pytest.raises(WeakLabelMLError, match="summary authorization row is not signed"):
        write_weak_label_ml_outputs(
            _features(baseline_mode="all_dry"),
            _feature_manifest(),
            authorization_manifest=_authorized_reference_manifest(),
            metrics_output_path=tmp_path / "metrics.csv",
            prediction_manifest_output_path=tmp_path / "prediction_manifest.csv",
            summary_output_path=tmp_path / "summary.md",
        )

    assert not list(tmp_path.iterdir())


def test_write_weak_label_ml_outputs_cannot_bypass_authorization(
    tmp_path: Path,
) -> None:
    with pytest.raises(WeakLabelMLError, match="not qualified_expert_or_adjudicated"):
        write_weak_label_ml_outputs(
            _features(baseline_mode="all_dry"),
            _feature_manifest(),
            authorization_manifest=pd.DataFrame(
                [
                    {
                        "reference_id": "WEAK-REFERENCE",
                        "reference_mask_status": "weak_reference_candidate",
                        "not_official_status": "confirmed_true",
                    }
                ]
            ),
            metrics_output_path=tmp_path / "metrics.csv",
            prediction_manifest_output_path=tmp_path / "prediction_manifest.csv",
            summary_output_path=tmp_path / "summary.md",
        )

    assert not list(tmp_path.iterdir())


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


def _authorized_reference_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "experiment_id": "EXP-MAE-SAI-QUALIFIED-001",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "reference_id": "QUALIFIED-REFERENCE-001",
                "reference_mask_status": "qualified_expert_or_adjudicated",
                "sha256": "0" * 64,
                "sha256_status": "verified",
                "license_status": "confirmed_for_experiment",
                "local_analysis_allowed": True,
                "derived_metrics_allowed": True,
                "ml_label_use_allowed": True,
                "validation_metrics_allowed": True,
                "processing_allowed": True,
                "not_official_status": "confirmed_true",
                "official_warning_allowed": False,
                "acquisition_manifest_sha256": "1" * 64,
                "acquisition_authority_receipt_sha256": "2" * 64,
                "reviewer_qualification_status": (
                    "qualified_for_controlled_reference_derivation"
                ),
                "reviewer_qualification_manifest_sha256": "3" * 64,
                "reviewer_calibration_receipt_sha256": "4" * 64,
                "unresolved_disagreement_count": 0,
                "spatial_holdout_status": "verified_frozen_non_overlapping",
                "spatial_holdout_manifest_sha256": "5" * 64,
                "spatial_holdout_membership_sha256": "6" * 64,
                "training_partition_sha256": "7" * 64,
                "calibration_partition_sha256": "8" * 64,
                "final_holdout_partition_sha256": "9" * 64,
                "execution_authorization_status": (
                    "authorized_for_bounded_model_lane_execution"
                ),
                "execution_authorization_manifest_sha256": "a" * 64,
            }
        ]
    )
