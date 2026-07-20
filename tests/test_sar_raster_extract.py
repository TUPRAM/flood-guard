from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from floodguard.ingestion import (
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
)
from floodguard.sar_baseline import compute_mask_validation_metrics
from floodguard.sar_raster_extract import (
    SAR_LOG_TRANSFORM,
    SAR_MEASUREMENT_DOMAIN,
    SAR_RADIOMETRIC_CALIBRATION_STATUS,
    SARRasterExtractError,
    SARRasterInputs,
    build_sar_feature_manifest,
    build_sentinel1_inputs_from_manifests,
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
    assert features.loc[0, "pre_vv_db"] == pytest.approx(40.0)
    assert features.loc[0, "post_vv_db"] == pytest.approx(20.0)
    assert features.loc[0, "vh_drop"] > features.loc[3, "vh_drop"]
    metrics = compute_mask_validation_metrics(
        features["binary_flood_extent"],
        features["reference_flood_extent"],
    )
    assert metrics["iou"] == 1.0
    assert metrics["f1_dice"] == 1.0


def test_extract_sar_change_features_reprojects_shifted_sources_to_one_grid(
    tmp_path: Path,
) -> None:
    from rasterio.transform import from_origin

    target_row = np.array([100.5, 101.5, 102.5, 103.5], dtype="float32")
    shifted_row = np.array([100.0, 101.0, 102.0, 103.0, 104.0], dtype="float32")
    target_values = np.repeat(target_row[None, :], 4, axis=0)
    shifted_values = np.repeat(shifted_row[None, :], 4, axis=0)
    post_vv = _write_tif(tmp_path / "post-vv.tif", target_values)
    post_vh = _write_tif(tmp_path / "post-vh.tif", target_values)
    pre_vv = _write_tif(
        tmp_path / "pre-vv-shifted.tif",
        shifted_values,
        transform=from_origin(-0.5, 4, 1, 1),
    )
    pre_vh = _write_tif(
        tmp_path / "pre-vh-shifted.tif",
        shifted_values,
        transform=from_origin(-0.5, 4, 1, 1),
    )
    geometry = {
        "type": "Polygon",
        "coordinates": [[(0, 4), (4, 4), (4, 0), (0, 0), (0, 4)]],
    }

    features = extract_sar_change_features(
        SARRasterInputs(
            pre_vv_uri=str(pre_vv),
            pre_vh_uri=str(pre_vh),
            post_vv_uri=str(post_vv),
            post_vh_uri=str(post_vh),
            reference_geometries=(geometry,),
        ),
        output_shape=(4, 4),
        dry_change_db=0.5,
        flood_change_db=4.0,
        buffer_degrees=0.0,
    )

    assert len(features) == 16
    assert features["vv_drop"].abs().max() < 0.00001
    assert features["vh_drop"].abs().max() < 0.00001
    assert features["binary_flood_extent"].sum() == 0
    assert "exact_common_grid_reprojection" in features.attrs["georeferencing_method"]


def test_extract_sar_change_features_does_not_mutate_source_rasters(
    tmp_path: Path,
) -> None:
    raster = _write_tif(tmp_path / "immutable.tif", np.full((4, 4), 100, dtype="float32"))
    geometry = {
        "type": "Polygon",
        "coordinates": [[(0, 4), (4, 4), (4, 0), (0, 0), (0, 4)]],
    }
    before = _file_identity(raster)

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

    assert _file_identity(raster) == before
    assert not list(tmp_path.glob("*.aux.xml"))


def test_build_inputs_binds_actual_checksums_before_source_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pre = tmp_path / "pre.zip"
    post = tmp_path / "post.zip"
    reference = tmp_path / "reference.gpkg"
    pre.write_bytes(b"immutable-pre")
    post.write_bytes(b"immutable-post")
    reference.write_bytes(b"immutable-reference")
    file_manifest = _file_manifest_for_paths(pre, post)
    manual_manifest = _manual_manifest_for_path(reference)
    calls: list[str] = []
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.build_sentinel1_safe_band_uri",
        lambda path, polarization: calls.append(f"safe:{polarization}")
        or f"{path}:{polarization}",
    )
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.read_manual_reference_geometries",
        lambda path: (calls.append("reference") or ([{"type": "Polygon", "coordinates": []}], "EPSG:4326")),
    )

    inputs = build_sentinel1_inputs_from_manifests(file_manifest, manual_manifest)

    assert inputs.pre_source_sha256 == _hash(pre)
    assert inputs.post_source_sha256 == _hash(post)
    assert inputs.reference_sha256 == _hash(reference)
    assert inputs.source_integrity_status == "verified_sha256_before_raster_read"
    assert calls == ["reference", "safe:VV", "safe:VH", "safe:VV", "safe:VH"]


@pytest.mark.parametrize("substituted", ["pre", "post", "reference"])
def test_build_inputs_rejects_substitution_before_any_source_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted: str,
) -> None:
    pre = tmp_path / "pre.zip"
    post = tmp_path / "post.zip"
    reference = tmp_path / "reference.gpkg"
    pre.write_bytes(b"immutable-pre")
    post.write_bytes(b"immutable-post")
    reference.write_bytes(b"immutable-reference")
    file_manifest = _file_manifest_for_paths(pre, post)
    manual_manifest = _manual_manifest_for_path(reference)
    {"pre": pre, "post": post, "reference": reference}[substituted].write_bytes(
        f"substituted-{substituted}".encode()
    )
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.build_sentinel1_safe_band_uri",
        lambda *_args, **_kwargs: pytest.fail("SAFE was opened before checksum rejection"),
    )
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.read_manual_reference_geometries",
        lambda *_args, **_kwargs: pytest.fail("reference was opened before checksum rejection"),
    )

    with pytest.raises(
        SARRasterExtractError,
        match="SHA-256 mismatch.*blocked before GDAL access",
    ):
        build_sentinel1_inputs_from_manifests(file_manifest, manual_manifest)


def test_build_inputs_rejects_retired_cog_pair_before_any_source_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pre = tmp_path / "retired-pre-cog.zip"
    post = tmp_path / "retired-post-cog.zip"
    reference = tmp_path / "reference.gpkg"
    pre.write_bytes(b"legacy-pre")
    post.write_bytes(b"legacy-post")
    reference.write_bytes(b"reference")
    file_manifest = _file_manifest_for_paths(pre, post)
    file_manifest.loc[0, "product_id"] = "b09f96ca-4a60-43e7-9b8d-158022f0e5bf"
    file_manifest.loc[1, "product_id"] = "20a9c3b8-37df-46d5-81d8-d63c7e460225"
    manual_manifest = _manual_manifest_for_path(reference)
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.build_sentinel1_safe_band_uri",
        lambda *_args, **_kwargs: pytest.fail("retired COG SAFE was opened"),
    )
    monkeypatch.setattr(
        "floodguard.sar_raster_extract.read_manual_reference_geometries",
        lambda *_args, **_kwargs: pytest.fail("reference was opened"),
    )

    with pytest.raises(
        SARRasterExtractError,
        match="approved same-track original SAFE pair.*retired COG",
    ):
        build_sentinel1_inputs_from_manifests(file_manifest, manual_manifest)


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


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"type": "Polygon", "coordinates": []}, "has no rings"),
        (
            {
                "type": "Polygon",
                "coordinates": [[(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)]],
            },
            "no positive area|self-intersects",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [[(0, 0), (1, 0), (1, float("nan")), (0, 0)]],
            },
            "not finite",
        ),
        (
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
                    [[(0.5, 0), (1.5, 0), (1.5, 1), (0.5, 1), (0.5, 0)]],
                ],
            },
            "overlap or touch|overlap",
        ),
    ],
)
def test_extract_sar_change_features_rejects_invalid_geometry_before_raster_open(
    geometry: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(SARRasterExtractError, match=message):
        extract_sar_change_features(
            SARRasterInputs(
                pre_vv_uri="missing-pre-vv.tif",
                pre_vh_uri="missing-pre-vh.tif",
                post_vv_uri="missing-post-vv.tif",
                post_vh_uri="missing-post-vh.tif",
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
        verified_inputs=_verified_inputs(),
    )

    row = manifest.iloc[0]
    assert row["processing_scope"] == "weak_reference_real_sentinel1_non_ml_candidate"
    assert row["reference_status"] == "weak_reference_candidate"
    assert row["sample_pixel_count"] == 2
    assert row["reference_positive_pixel_count"] == 1
    assert row["source_integrity_status"] == "verified_sha256_before_raster_read"
    assert row["measurement_domain"] == SAR_MEASUREMENT_DOMAIN
    assert row["log_transform"] == SAR_LOG_TRANSFORM
    assert row["radiometric_calibration_status"] == SAR_RADIOMETRIC_CALIBRATION_STATUS
    assert row["pre_source_sha256"] == "a" * 64
    assert row["post_source_sha256"] == "b" * 64
    assert row["reference_sha256"] == "c" * 64
    assert row["reference_spatial_relation"] == "cross_border_calibration_only"
    assert bool(row["reference_in_study_area_overlap"]) is False
    assert row["reference_distance_to_study_area_km"] == 5.965378
    assert "Not official validation" in row["assumptions"]


def _write_tif(path: Path, array: object, *, transform: object | None = None) -> Path:
    from rasterio.transform import from_origin

    values = np.asarray(array)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=int(values.shape[1]),
        height=int(values.shape[0]),
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform or from_origin(0, 4, 1, 1),
    ) as dataset:
        dataset.write(values, 1)
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_identity(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return _hash(path), stat.st_size, stat.st_mtime_ns


def _file_manifest_for_paths(pre: Path, post: Path) -> pd.DataFrame:
    manifest = _file_manifest()
    manifest.loc[0, "local_path"] = str(pre)
    manifest.loc[0, "sha256"] = _hash(pre)
    manifest.loc[1, "local_path"] = str(post)
    manifest.loc[1, "sha256"] = _hash(post)
    return manifest


def _manual_manifest_for_path(reference: Path) -> pd.DataFrame:
    manifest = _manual_manifest()
    manifest.loc[0, "local_path_hint"] = str(reference)
    manifest.loc[0, "sha256"] = _hash(reference)
    manifest.loc[0, "sha256_status"] = "recorded"
    manifest.loc[0, "candidate_validation_metrics_allowed"] = True
    manifest.loc[0, "spatial_relation"] = "cross_border_calibration_only"
    manifest.loc[0, "in_study_area_overlap"] = False
    manifest.loc[0, "distance_to_study_area_km"] = 2.5
    manifest.loc[0, "spatial_relation_status"] = "verified_geometry_intersection"
    return manifest


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
        reference_distance_to_study_area_km=5.965378,
    )


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
                "spatial_relation": "cross_border_calibration_only",
                "in_study_area_overlap": False,
                "distance_to_study_area_km": 5.965378,
                "spatial_relation_status": "verified_geometry_intersection",
            }
        ]
    )
