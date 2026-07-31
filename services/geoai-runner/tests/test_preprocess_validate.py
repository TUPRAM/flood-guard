from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import rasterio

from geoai_runner.preprocess import (
    DEFAULT_TRANSFORMS,
    PreprocessingError,
    encode_feature_geotiff,
    encode_physical_stack,
    geoai_uint8_preprocess,
    sidecar_payload,
    validate_transform_sidecar,
)
from geoai_runner.validate import (
    RasterValidationError,
    compute_validation_metrics,
    validate_aligned_feature_and_mask,
    validate_grid_matches_contract,
)

from .helpers import build_synthetic_workspace, write_mask, write_physical_stack


def test_physical_values_are_clipped_and_encoded_in_declared_order() -> None:
    stack = np.zeros((8, 2, 2), dtype=np.float32)
    for index, transform in enumerate(DEFAULT_TRANSFORMS):
        stack[index] = np.array(
            [
                [transform.physical_min - 1, transform.physical_min],
                [transform.physical_max, transform.physical_max + 1],
            ]
        )
    encoded = encode_physical_stack(stack)
    assert encoded.dtype == np.uint8
    assert encoded.shape == stack.shape
    assert np.all(encoded[:, 0, :] == 0)
    assert np.all(encoded[:, 1, :] == 255)


def test_sidecar_documents_stock_training_and_inference_symmetry() -> None:
    payload = sidecar_payload()
    assert payload["encoded_dtype"] == "uint8"
    assert payload["encoded_range"] == [0, 255]
    assert "divides values by 255" in payload["training_loader_contract"]
    assert [channel["name"] for channel in payload["channels"]] == [
        transform.name for transform in DEFAULT_TRANSFORMS
    ]


def test_sidecar_bytes_and_typed_transform_statistics_are_both_bound(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    assert (
        validate_transform_sidecar(
            evidence["sidecar"],
            evidence["contract"].preprocessing,
        )
        == evidence["contract"].preprocessing.sidecar_sha256
    )
    first, *remaining = evidence["contract"].preprocessing.transforms
    mismatched = replace(
        evidence["contract"].preprocessing,
        transforms=(replace(first, physical_min=-31.0), *remaining),
    )
    with pytest.raises(PreprocessingError, match="statistics"):
        validate_transform_sidecar(evidence["sidecar"], mismatched)
    evidence["sidecar"].write_text(
        evidence["sidecar"].read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(PreprocessingError, match="checksum"):
        validate_transform_sidecar(
            evidence["sidecar"],
            evidence["contract"].preprocessing,
        )


def test_inference_preprocess_accepts_geoai_float_cast_but_rejects_raw_values() -> None:
    encoded_float = np.full((8, 2, 2), 128.0, dtype=np.float32)
    transformed = geoai_uint8_preprocess(encoded_float)
    assert transformed.dtype == np.float32
    assert transformed[0, 0, 0] == pytest.approx(128 / 255)

    with pytest.raises(PreprocessingError, match="pre-encoded"):
        geoai_uint8_preprocess(np.full((8, 2, 2), -12.5, dtype=np.float32))
    with pytest.raises(PreprocessingError, match="exact uint8"):
        geoai_uint8_preprocess(np.full((8, 2, 2), 0.5, dtype=np.float32))


def test_encoding_writes_georeferenced_uint8_stack_and_sidecar(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    receipt = evidence["encoding"]
    assert len(receipt.feature_sha256) == 64
    assert len(receipt.sidecar_sha256) == 64
    assert receipt.grid.crs == "EPSG:32647"
    assert receipt.grid.dtypes == ("uint8",) * 8
    assert receipt.grid.nodata is None
    assert receipt.grid.descriptions == tuple(transform.name for transform in DEFAULT_TRANSFORMS)
    assert evidence["sidecar"].is_file()


def test_encoding_rejects_band_order_and_actual_nodata(tmp_path: Path) -> None:
    physical = tmp_path / "physical.tif"
    write_physical_stack(physical)
    with rasterio.open(physical, "r+") as raster:
        raster.set_band_description(1, "wrong")
    with pytest.raises(PreprocessingError, match="channel order"):
        encode_feature_geotiff(
            physical,
            tmp_path / "encoded.tif",
            tmp_path / "sidecar.json",
        )

    write_physical_stack(physical)
    with rasterio.open(physical, "r+") as raster:
        first = raster.read(1)
        first[0, 0] = -9999.0
        raster.write(first, 1)
    with pytest.raises(PreprocessingError, match="contains nodata"):
        encode_feature_geotiff(
            physical,
            tmp_path / "encoded.tif",
            tmp_path / "sidecar.json",
        )


def test_encoding_refuses_to_overwrite_input_or_raster_with_sidecar(
    tmp_path: Path,
) -> None:
    physical = tmp_path / "physical.tif"
    write_physical_stack(physical)
    with pytest.raises(PreprocessingError, match="must be distinct"):
        encode_feature_geotiff(
            physical,
            physical,
            tmp_path / "sidecar.json",
        )
    with pytest.raises(PreprocessingError, match="must be distinct"):
        encode_feature_geotiff(
            physical,
            tmp_path / "encoded.tif",
            tmp_path / "encoded.tif",
        )


def test_alignment_and_contract_grid_are_hard_gates(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    grid = validate_aligned_feature_and_mask(evidence["encoded"], evidence["mask"])
    validate_grid_matches_contract(grid, evidence["contract"])

    shifted = evidence["workspace"] / "shifted-mask.tif"
    write_mask(shifted, transform_shift=10.0)
    with pytest.raises(RasterValidationError, match="transform|bounds"):
        validate_aligned_feature_and_mask(evidence["encoded"], shifted)


def test_mask_requires_explicit_binary_class_mapping(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    mask = evidence["mask"]
    with rasterio.open(mask, "r+") as raster:
        raster.write(np.zeros((8, 8), dtype=np.uint8), 1)
    with pytest.raises(RasterValidationError, match="both class 0 and class 1"):
        validate_aligned_feature_and_mask(evidence["encoded"], mask)


def test_validation_metrics_include_brier_calibration_and_absolute_area_error() -> None:
    probabilities = np.array([[0.9, 0.8], [0.7, 0.2]], dtype=np.float32)
    reference = np.array([[1, 0], [0, 0]], dtype=np.uint8)
    metrics = compute_validation_metrics(probabilities, reference, threshold=0.5)
    assert metrics["iou"] == pytest.approx(1 / 3, abs=1e-6)
    assert metrics["f1_dice"] == pytest.approx(0.5)
    assert metrics["precision"] == pytest.approx(1 / 3, abs=1e-6)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["area_error_ratio"] == pytest.approx(2.0)
    assert metrics["brier_score"] == pytest.approx(0.295)
    assert 0 <= metrics["expected_calibration_error"] <= 1


def test_validation_metrics_reject_misalignment_and_invalid_controls() -> None:
    probabilities = np.array([[0.9, 0.1]], dtype=np.float32)
    reference = np.array([[1]], dtype=np.uint8)
    with pytest.raises(RasterValidationError, match="shapes differ"):
        compute_validation_metrics(probabilities, reference, threshold=0.5)
    with pytest.raises(RasterValidationError, match="Threshold"):
        compute_validation_metrics(reference, reference, threshold=float("nan"))
    with pytest.raises(RasterValidationError, match="Threshold"):
        compute_validation_metrics(reference, reference, threshold=0.5, calibration_bins=True)
