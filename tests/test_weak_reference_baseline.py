from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.sar_raster_extract import SARRasterExtractError
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
        lambda file_manifest, manual_reference_manifest: object(),
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
    assert row["metric_status"] == "candidate_weak_reference_metrics"
    assert row["warning_text"] == WEAK_BASELINE_WARNING
    assert row["source_timestamp"] == "2024-09-15T23:16:01Z"
    assert row["iou"] == 0.5
    assert row["f1_dice"] == pytest.approx(0.666667)
    assert row["sample_pixel_count"] == 4
    assert row["reference_positive_pixel_count"] == 3
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


def test_write_weak_reference_baseline_outputs_writes_csv_and_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "floodguard.weak_reference_baseline.build_sentinel1_inputs_from_manifests",
        lambda file_manifest, manual_reference_manifest: object(),
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
    assert "Candidate metrics against manually digitized weak-reference mask" in summary
    assert "Not official" in summary
    assert "Not field validated" in summary


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
                "source_name": "CDSE Sentinel-1 Mae Sai pre-event COG",
                "candidate_use": "pre-event SAR source for non-ML baseline",
                "product_id": "pre-product",
                "local_path": "<external_data_workspace>/pre.zip",
                "sha256": "a" * 64,
                "source_license_status": "confirmed",
            },
            {
                "source_name": "CDSE Sentinel-1 Mae Sai post-event COG primary",
                "candidate_use": "post-event SAR source for non-ML baseline",
                "product_id": "20a9c3b8-37df-46d5-81d8-d63c7e460225",
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
