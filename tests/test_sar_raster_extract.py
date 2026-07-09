from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from floodguard.sar_baseline import compute_mask_validation_metrics
from floodguard.sar_raster_extract import (
    SARRasterExtractError,
    SARRasterInputs,
    build_sar_feature_manifest,
    extract_sar_change_features,
    resolve_external_path_hint,
)

rasterio = pytest.importorskip("rasterio")
np = pytest.importorskip("numpy")


def test_resolve_external_path_hint_expands_workspace() -> None:
    resolved = resolve_external_path_hint(
        "<external_data_workspace>/cdse/mae_sai_2024/source.zip",
        external_data_dir="D:/FloodGuardExternal",
    )

    assert resolved == Path("D:/FloodGuardExternal") / "cdse" / "mae_sai_2024" / "source.zip"


def test_resolve_external_path_hint_rejects_unresolved() -> None:
    with pytest.raises(SARRasterExtractError, match="unresolved"):
        resolve_external_path_hint("not_acquired")


def test_extract_sar_change_features_from_tiny_rasters(tmp_path: Path) -> None:
    pre_vv = _write_tif(tmp_path / "pre_vv.tif", np.full((4, 4), 100, dtype="float32"))
    pre_vh = _write_tif(tmp_path / "pre_vh.tif", np.full((4, 4), 100, dtype="float32"))
    post_vv_array = np.full((4, 4), 90, dtype="float32")
    post_vh_array = np.full((4, 4), 90, dtype="float32")
    post_vv_array[:, :2] = 10
    post_vh_array[:, :2] = 5
    post_vv = _write_tif(tmp_path / "post_vv.tif", post_vv_array)
    post_vh = _write_tif(tmp_path / "post_vh.tif", post_vh_array)
    geometry = {
        "type": "Polygon",
        "coordinates": [[(0, 4), (2, 4), (2, 0), (0, 0), (0, 4)]],
    }

    features = extract_sar_change_features(
        SARRasterInputs(
            pre_vv_uri=str(pre_vv),
            pre_vh_uri=str(pre_vh),
            post_vv_uri=str(post_vv),
            post_vh_uri=str(post_vh),
            reference_geometries=(geometry,),
            reference_crs="EPSG:4326",
        ),
        output_shape=(4, 4),
        dry_change_db=0.5,
        flood_change_db=4.0,
        buffer_degrees=0.0,
    )

    assert len(features) == 16
    assert features["reference_flood_extent"].sum() == 16
    assert features["binary_flood_extent"].sum() == 16
    assert features.loc[0, "vh_drop"] > features.loc[3, "vh_drop"]
    metrics = compute_mask_validation_metrics(
        features["binary_flood_extent"],
        features["reference_flood_extent"],
    )
    assert metrics["iou"] == 1.0
    assert metrics["f1_dice"] == 1.0


def test_extract_sar_change_features_rejects_non_overlapping_reference(
    tmp_path: Path,
) -> None:
    raster = _write_tif(tmp_path / "raster.tif", np.full((4, 4), 100, dtype="float32"))
    geometry = {
        "type": "Polygon",
        "coordinates": [[(10, 14), (12, 14), (12, 10), (10, 10), (10, 14)]],
    }

    with pytest.raises(SARRasterExtractError, match="does not overlap"):
        extract_sar_change_features(
            SARRasterInputs(
                pre_vv_uri=str(raster),
                pre_vh_uri=str(raster),
                post_vv_uri=str(raster),
                post_vh_uri=str(raster),
                reference_geometries=(geometry,),
            ),
            output_shape=(4, 4),
            buffer_degrees=0.0,
        )


def test_build_sar_feature_manifest_records_weak_scope() -> None:
    features = pd.DataFrame(
        {
            "pixel_id": ["PX-1", "PX-2"],
            "row": [0, 0],
            "col": [0, 1],
            "pre_vv_db": [20, 20],
            "post_vv_db": [10, 19],
            "pre_vh_db": [20, 20],
            "post_vh_db": [9, 19],
            "vv_drop": [10, 1],
            "vh_drop": [11, 1],
            "vv_ratio": [0.1, 0.9],
            "vh_ratio": [0.09, 0.9],
            "combined_sar_change_score": [10.6, 1.0],
            "flood_probability_0_1": [1.0, 0.2],
            "binary_flood_extent": [1, 0],
            "reference_flood_extent": [1, 0],
        }
    )
    features.attrs["bbox"] = (99.8, 20.3, 100.0, 20.5)
    features.attrs["sample_width"] = 2
    features.attrs["sample_height"] = 1
    features.attrs["georeferencing_method"] = "dataset_affine_transform"

    manifest = build_sar_feature_manifest(
        features,
        file_manifest=_file_manifest(),
        manual_reference_manifest=_manual_manifest(),
    )

    row = manifest.iloc[0]
    assert row["processing_scope"] == "weak_reference_real_sentinel1_non_ml_candidate"
    assert row["reference_status"] == "weak_reference_candidate"
    assert row["sample_pixel_count"] == 2
    assert row["reference_positive_pixel_count"] == 1
    assert "Not official validation" in row["assumptions"]


def _write_tif(path: Path, array: object) -> Path:
    from rasterio.transform import from_origin

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 4, 1, 1),
    ) as dataset:
        dataset.write(array, 1)
    return path


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
                "product_id": "post-product",
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
