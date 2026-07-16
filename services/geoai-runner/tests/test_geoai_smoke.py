from __future__ import annotations

import os
from dataclasses import replace
from inspect import signature
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from geoai_runner.contract import SpatialPartitionContract
from geoai_runner.environment import EXPECTED_GEOAI_COMMIT, inspect_environment
from geoai_runner.infer import run_prediction
from geoai_runner.prepare import export_training_tiles, file_sha256
from geoai_runner.train import package_trained_checkpoint

from .helpers import build_synthetic_workspace


@pytest.mark.geoai_smoke
def test_real_geoai_export_and_bound_checkpoint_inference_path(tmp_path: Path) -> None:
    if os.environ.get("RUN_GEOAI_SMOKE") != "1":
        pytest.skip("Set RUN_GEOAI_SMOKE=1 in the isolated GeoAI environment.")

    receipt = inspect_environment(declared_geoai_commit=EXPECTED_GEOAI_COMMIT)
    assert receipt.geoai_version == "0.41.1"

    evidence = build_synthetic_workspace(tmp_path)
    large_feature = evidence["workspace"] / "large-encoded-stack.tif"
    large_mask = evidence["workspace"] / "large-mask.tif"
    _write_large_inference_grid(evidence, large_feature, large_mask)
    reference_rows = tuple(
        replace(row, sha256=file_sha256(large_mask)) if row.role == "reference_mask" else row
        for row in evidence["contract"].input_manifest_rows
    )
    preparation_contract = replace(
        evidence["contract"],
        encoded_feature_sha256=file_sha256(large_feature),
        reference_mask_sha256=file_sha256(large_mask),
        input_manifest_rows=reference_rows,
        bounds=(600000.0, 2199760.0, 600320.0, 2200080.0),
        spatial_partitions=(
            SpatialPartitionContract(
                spatial_group_id="train-zone-01",
                split="train",
                bounds=(600000.0, 2199760.0, 600160.0, 2200080.0),
            ),
            SpatialPartitionContract(
                spatial_group_id="holdout-zone-01",
                split="holdout",
                bounds=(600160.0, 2199760.0, 600320.0, 2200080.0),
            ),
        ),
    )
    preparation_contract.validate()
    output = evidence["workspace"] / "real-geoai-tiles"
    export_receipt = export_training_tiles(
        preparation_contract,
        large_feature,
        large_mask,
        evidence["sidecar"],
        output,
    )
    assert export_receipt.training_tile_count > 0
    assert export_receipt.holdout_tile_count > 0
    assert export_receipt.rejected_boundary_tile_count > 0
    assert list((output / "images").glob("*.tif"))
    training_labels = list((output / "labels").glob("*.tif"))
    assert training_labels
    assert any(_label_has_real_nodata(path) for path in training_labels)

    import torch
    from geoai.train import get_smp_model, train_segmentation_model

    assert "ignore_index" in signature(train_segmentation_model).parameters

    model = get_smp_model(
        architecture=preparation_contract.architecture,
        encoder_name=preparation_contract.encoder,
        encoder_weights=None,
        in_channels=preparation_contract.channel_count,
        classes=2,
        activation=None,
    )
    model_dir = evidence["workspace"] / "real-model"
    model_dir.mkdir()
    raw_state = model_dir / "best_model.pth"
    torch.save(model.state_dict(), raw_state)
    training_contract = replace(
        preparation_contract,
        run_status="running",
        prepared_tile_manifest_sha256=export_receipt.prepared_manifest_sha256,
    )
    training_contract.validate()
    packaged = package_trained_checkpoint(
        training_contract,
        raw_state,
        model_dir / "floodguard_model.pth",
        prepared_manifest_path=output / export_receipt.prepared_manifest_relative_path,
    )
    inference_contract = replace(
        training_contract,
        run_status="completed",
        model_sha256=packaged.packaged_checkpoint_sha256,
        tile_size=32,
        overlap=0,
        stride=32,
    )
    inference_contract.validate()

    result = run_prediction(
        inference_contract,
        encoded_feature_path=large_feature,
        sidecar_path=evidence["sidecar"],
        checkpoint_path=packaged.packaged_checkpoint_path,
        output_path=evidence["probability"],
        prepared_manifest_path=output / export_receipt.prepared_manifest_relative_path,
    )
    assert result.descriptions == ("flood_probability_0_1",)
    with rasterio.open(evidence["probability"]) as source:
        probability = source.read(1, masked=True)
        assert source.crs.to_string() == inference_contract.target_crs
        assert tuple(source.transform) == result.transform
        assert source.tags()["source_timestamp"] == inference_contract.source_timestamp
        assert source.tags()["official_warning"] == "false"
    assert probability.count() > 0
    assert float(probability.min()) >= 0
    assert float(probability.max()) <= 1


def _label_has_real_nodata(path: Path) -> bool:
    with rasterio.open(path) as source:
        values = set(np.unique(source.read(1)).tolist())
        assert source.nodata == 255
        assert values.issubset({0, 1, 255})
    return 255 in values


def _write_large_inference_grid(
    evidence: dict[str, object],
    feature_path: Path,
    mask_path: Path,
) -> None:
    transform = from_origin(600000.0, 2200080.0, 10.0, 10.0)
    with rasterio.open(Path(evidence["encoded"])) as source:
        feature = np.tile(source.read(), (1, 4, 4))
        feature_profile = source.profile.copy()
        descriptions = source.descriptions
    feature_profile.update(width=32, height=32, transform=transform)
    with rasterio.open(feature_path, "w", **feature_profile) as target:
        target.write(feature)
        for index, description in enumerate(descriptions, start=1):
            target.set_band_description(index, description)
    with rasterio.open(Path(evidence["mask"])) as source:
        mask = np.tile(source.read(), (1, 4, 4))
        mask_profile = source.profile.copy()
        description = source.descriptions[0]
    mask_profile.update(width=32, height=32, transform=transform)
    with rasterio.open(mask_path, "w", **mask_profile) as target:
        target.write(mask)
        target.set_band_description(1, description)
