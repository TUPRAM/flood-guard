from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.ingestion import (
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
)
from floodguard.sar_raster_extract import (
    SAR_LOG_TRANSFORM,
    SAR_MEASUREMENT_DOMAIN,
    SAR_RADIOMETRIC_CALIBRATION_STATUS,
    SARRasterExtractError,
    SARRasterInputs,
)
from floodguard.weak_reference_baseline import (
    WEAK_BASELINE_WARNING,
    WeakReferenceBaselineError,
    build_weak_reference_baseline_summary,
    run_weak_reference_sar_baseline,
    write_weak_reference_baseline_outputs,
)


def test_weak_reference_baseline_generates_candidate_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.build_sentinel1_inputs_from_manifests",
        lambda file_manifest, manual_reference_manifest: _verified_inputs(),
    )
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.extract_sar_change_features",
        lambda inputs, **kwargs: _features(),
    )

    _feature_table, metrics, feature_manifest = run_weak_reference_sar_baseline(
        _file_manifest(),
        _manual_manifest(),
    )

    row = metrics.iloc[0]
    assert row["metric_status"] == "candidate_cross_border_calibration_metrics"
    assert row["warning_text"] == WEAK_BASELINE_WARNING
    assert row["source_timestamp"] == "2024-09-15T23:16:01Z"
    assert row["iou"] == 0.5
    assert row["f1_dice"] == pytest.approx(0.666667)
    assert row["sample_pixel_count"] == 4
    assert row["reference_positive_pixel_count"] == 3
    assert row["source_integrity_status"] == "verified_sha256_before_raster_read"
    assert row["measurement_domain"] == SAR_MEASUREMENT_DOMAIN
    assert row["log_transform"] == SAR_LOG_TRANSFORM
    assert row["radiometric_calibration_status"] == SAR_RADIOMETRIC_CALIBRATION_STATUS
    assert row["pre_source_sha256"] == "a" * 64
    assert row["post_source_sha256"] == "b" * 64
    assert row["reference_sha256"] == "c" * 64
    assert row["reference_spatial_relation"] == "cross_border_calibration_only"
    assert bool(row["reference_in_study_area_overlap"]) is False
    assert row["reference_distance_to_study_area_km"] == 2.5
    assert feature_manifest.iloc[0]["reference_status"] == "weak_reference_candidate"


def test_weak_reference_baseline_surfaces_extraction_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.build_sentinel1_inputs_from_manifests",
        lambda file_manifest, manual_reference_manifest: (_ for _ in ()).throw(
            SARRasterExtractError("manual reference is not ready")
        ),
    )

    with pytest.raises(WeakReferenceBaselineError, match="manual reference is not ready"):
        run_weak_reference_sar_baseline(_file_manifest(), _manual_manifest())


def test_weak_reference_baseline_blocks_unregistered_source_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.build_sentinel1_inputs_from_manifests",
        lambda file_manifest, manual_reference_manifest: _verified_inputs(),
    )
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.extract_sar_change_features",
        lambda inputs, **kwargs: _features(),
    )
    manifest = _file_manifest()
    manifest.loc[1, "product_id"] = "substituted-post-product"

    with pytest.raises(
        WeakReferenceBaselineError,
        match="No immutable source timestamp is registered",
    ):
        run_weak_reference_sar_baseline(manifest, _manual_manifest())


def test_write_weak_reference_baseline_outputs_writes_csv_and_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.build_sentinel1_inputs_from_manifests",
        lambda file_manifest, manual_reference_manifest: _verified_inputs(),
    )
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.extract_sar_change_features",
        lambda inputs, **kwargs: _features(),
    )

    written = write_weak_reference_baseline_outputs(
        _file_manifest(),
        _manual_manifest(),
        metrics_output_path=tmp_path / "metrics.csv",
        feature_manifest_output_path=tmp_path / "features.csv",
        summary_output_path=tmp_path / "summary.md",
    )

    assert written["metrics"].exists()
    assert written["feature_manifest"].exists()
    assert written["summary"].exists()
    summary = written["summary"].read_text(encoding="utf-8")
    assert "Mae Sai Weak-Reference Sentinel-1 Baseline" in summary
    assert "Cross-border calibration metrics against a manually digitized" in summary
    assert "Not official" in summary
    assert "Not field validated" in summary
    assert "20 * log10(amplitude)" in summary
    assert "not calibrated Sigma0, Beta0, or Gamma0" in summary


def test_weak_reference_summary_requires_metrics_columns() -> None:
    with pytest.raises(WeakReferenceBaselineError, match="true_positive"):
        build_weak_reference_baseline_summary(pd.DataFrame([{}]), pd.DataFrame([{}]))


def _features() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "pixel_id": ["PX-1", "PX-2", "PX-3", "PX-4"],
            "row": [0, 0, 1, 1],
            "col": [0, 1, 0, 1],
            "pre_vv_db": [20, 20, 20, 20],
            "post_vv_db": [10, 10, 19, 10],
            "pre_vh_db": [20, 20, 20, 20],
            "post_vh_db": [10, 10, 19, 10],
            "vv_drop": [10, 10, 1, 10],
            "vh_drop": [10, 10, 1, 10],
            "vv_ratio": [0.1, 0.1, 0.9, 0.1],
            "vh_ratio": [0.1, 0.1, 0.9, 0.1],
            "combined_sar_change_score": [10, 10, 1, 10],
            "flood_probability_0_1": [1, 1, 0.1, 1],
            "binary_flood_extent": [1, 1, 0, 1],
            "reference_flood_extent": [1, 1, 1, 0],
        }
    )
    frame.attrs["bbox"] = (99.8, 20.3, 100.0, 20.5)
    frame.attrs["sample_width"] = 2
    frame.attrs["sample_height"] = 2
    frame.attrs["georeferencing_method"] = "dataset_affine_transform"
    return frame


def _file_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_name": "CDSE Sentinel-1 Mae Sai pre-event original SAFE",
                "candidate_use": "pre-event SAR source for non-ML baseline",
                "product_id": MAE_SAI_BASELINE_PRE_PRODUCT_ID,
                "local_path": "<external_data_workspace>/pre.zip",
                "sha256": "a" * 64,
                "source_license_status": "confirmed",
            },
            {
                "source_name": "CDSE Sentinel-1 Mae Sai post-event original SAFE",
                "candidate_use": "post-event SAR source for non-ML baseline",
                "product_id": MAE_SAI_BASELINE_POST_PRODUCT_ID,
                "local_path": "<external_data_workspace>/post.zip",
                "sha256": "b" * 64,
                "source_license_status": "confirmed",
            },
        ]
    )


def _manual_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "reference_id": "MANUAL-QGIS-MAE-SAI-2024",
                "reference_mask_status": "weak_reference_candidate",
            }
        ]
    )


def _verified_inputs() -> SARRasterInputs:
    return SARRasterInputs(
        pre_vv_uri="pre-vv",
        pre_vh_uri="pre-vh",
        post_vv_uri="post-vv",
        post_vh_uri="post-vh",
        reference_geometries=(),
        pre_source_sha256="a" * 64,
        post_source_sha256="b" * 64,
        reference_sha256="c" * 64,
        source_integrity_status="verified_sha256_before_raster_read",
        reference_spatial_relation="cross_border_calibration_only",
        reference_in_study_area_overlap=False,
        reference_distance_to_study_area_km=2.5,
    )
