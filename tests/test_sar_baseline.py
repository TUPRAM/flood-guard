from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.sar_baseline import (
    MASK_METRIC_COLUMNS,
    SARBaselineError,
    compute_mask_validation_metrics,
    run_gated_real_sar_change_baseline,
    run_threshold_sar_baseline,
    validate_real_sar_baseline_readiness,
    validate_threshold_sar_baseline,
)
from floodguard.ingestion import (
    build_ingestion_manifest,
    default_mae_sai_file_manifest_sources,
)

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures"


def load_sar_pixels() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "sample_sar_pixels.csv")


def test_threshold_sar_baseline_produces_probability_and_binary_mask() -> None:
    baseline = run_threshold_sar_baseline(load_sar_pixels())

    assert list(baseline["pixel_id"]) == [
        "PX-001",
        "PX-002",
        "PX-003",
        "PX-004",
        "PX-005",
    ]
    assert list(baseline["flood_probability_0_1"]) == [1.0, 0.943, 0.143, 1.0, 0.0]
    assert list(baseline["binary_flood_extent"]) == [1, 1, 0, 1, 0]
    assert list(baseline["reference_flood_extent"]) == [1, 1, 1, 0, 0]
    assert baseline["assumptions"].str.contains("not real Sentinel-1 processing").all()


def test_mask_validation_metrics_cover_iou_f1_precision_recall_and_area_error() -> None:
    baseline = run_threshold_sar_baseline(load_sar_pixels())

    metrics = compute_mask_validation_metrics(
        baseline["binary_flood_extent"],
        baseline["reference_flood_extent"],
    )

    assert metrics["true_positive"] == 2
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["true_negative"] == 1
    assert metrics["iou"] == 0.5
    assert metrics["f1_dice"] == pytest.approx(0.666667)
    assert metrics["precision"] == pytest.approx(0.666667)
    assert metrics["recall"] == pytest.approx(0.666667)
    assert metrics["area_error_ratio"] == 0.0


def test_validate_threshold_sar_baseline_returns_metric_frame() -> None:
    metric_frame = validate_threshold_sar_baseline(load_sar_pixels())

    assert list(metric_frame.columns) == list(MASK_METRIC_COLUMNS)
    assert len(metric_frame) == 1
    assert metric_frame.loc[0, "iou"] == 0.5
    assert metric_frame.loc[0, "area_error_ratio"] == 0.0


def test_sar_baseline_rejects_missing_columns() -> None:
    pixels = load_sar_pixels().drop(columns=["post_vv_db"])

    with pytest.raises(SARBaselineError, match="post_vv_db"):
        run_threshold_sar_baseline(pixels)


def test_sar_baseline_rejects_invalid_probability_threshold() -> None:
    with pytest.raises(SARBaselineError, match="probability_threshold"):
        run_threshold_sar_baseline(load_sar_pixels(), probability_threshold=1.5)


def test_mask_validation_metrics_reject_unequal_lengths() -> None:
    with pytest.raises(SARBaselineError, match="equal length"):
        compute_mask_validation_metrics([1, 0, 1], [1, 0])


def test_mask_validation_metrics_reject_non_binary_values() -> None:
    with pytest.raises(SARBaselineError, match="binary 0/1"):
        compute_mask_validation_metrics([1, 2, 0], [1, 0, 0])


def test_real_sar_baseline_readiness_blocks_current_mae_sai_manifest() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())

    with pytest.raises(SARBaselineError, match="ingestion gates"):
        validate_real_sar_baseline_readiness(manifest)


def test_gated_real_sar_change_baseline_runs_only_after_manifest_ready() -> None:
    source = default_mae_sai_file_manifest_sources().iloc[[0, 1, 2]].copy()
    source.loc[:, "geometry_access_status"] = "confirmed"
    source.loc[:, "license_status"] = "confirmed"
    source.loc[:, "redistribution_status"] = "reference_only"
    source.loc[:, "local_path"] = [
        "D:/FloodGuardData/mae_sai/reference_mask.geojson",
        "D:/FloodGuardData/mae_sai/pre_s1.tif",
        "D:/FloodGuardData/mae_sai/post_s1.tif",
    ]
    source.loc[:, "sha256"] = ["a" * 64, "b" * 64, "c" * 64]
    source.loc[:, "source_license_status"] = "confirmed"
    source.loc[:, "reference_mask_status"] = "confirmed"
    manifest = build_ingestion_manifest(source)

    baseline = run_gated_real_sar_change_baseline(load_sar_pixels(), manifest)

    assert list(baseline["binary_flood_extent"]) == [1, 1, 0, 1, 0]
    assert baseline["assumptions"].str.contains("Gated real-data non-ML SAR").all()
