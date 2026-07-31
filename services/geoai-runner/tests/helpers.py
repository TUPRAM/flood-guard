from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_origin

from geoai_runner.contract import (
    BandTransformContract,
    GeoAIRunContract,
    InputManifestRow,
    PreprocessingContract,
    SpatialPartitionContract,
    ValidationMetricsContract,
)
from geoai_runner.environment import EXPECTED_GEOAI_COMMIT
from geoai_runner.preprocess import DEFAULT_TRANSFORMS, encode_feature_geotiff

FLOODGUARD_COMMIT = "58cb508acbfac43a21cf347259cf6d12beef533c"


def build_synthetic_workspace(tmp_path: Path) -> dict[str, Any]:
    workspace = tmp_path / "external-workspace"
    workspace.mkdir()
    physical = workspace / "physical-stack.tif"
    encoded = workspace / "encoded-stack.tif"
    sidecar = workspace / "transform.json"
    mask = workspace / "mask.tif"
    checkpoint = workspace / "model.ckpt"
    lineage_manifest = workspace / "prepared-tile-manifest.json"
    probability = workspace / "flood-probability.tif"

    write_physical_stack(physical)
    encoding = encode_feature_geotiff(physical, encoded, sidecar)
    write_mask(mask)
    checkpoint.write_bytes(b"synthetic checkpoint for mocked GeoAI proof\n")
    lineage_manifest.write_text(
        '{"run_id":"geoai-synthetic-proof-001","tiles":[]}\n',
        encoding="utf-8",
    )
    contract = make_contract(
        workspace,
        sidecar_sha256=encoding.sidecar_sha256,
        encoded_feature_sha256=sha256(encoded),
        reference_mask_sha256=sha256(mask),
        checkpoint_sha256=sha256(checkpoint),
    )
    inference_contract = replace(
        contract,
        run_status="completed",
        prepared_tile_manifest_sha256=sha256(lineage_manifest),
    )
    inference_contract.validate()
    return {
        "workspace": workspace,
        "physical": physical,
        "encoded": encoded,
        "sidecar": sidecar,
        "mask": mask,
        "checkpoint": checkpoint,
        "lineage_manifest": lineage_manifest,
        "probability": probability,
        "encoding": encoding,
        "contract": contract,
        "inference_contract": inference_contract,
    }


def write_physical_stack(path: Path) -> None:
    height = width = 8
    row, column = np.mgrid[0:height, 0:width]
    values = np.stack(
        [
            -10.0 - row * 0.2,
            -14.0 - column * 0.1,
            -18.0 - row * 0.15,
            -21.0 - column * 0.1,
            4.0 + row * 0.1,
            3.0 + column * 0.1,
            row.astype(np.float32) * 2.0,
            ((row + column) % 2).astype(np.float32),
        ]
    ).astype(np.float32)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": len(DEFAULT_TRANSFORMS),
        "dtype": "float32",
        "crs": "EPSG:32647",
        "transform": from_origin(600000.0, 2200080.0, 10.0, 10.0),
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as target:
        target.write(values)
        for index, transform in enumerate(DEFAULT_TRANSFORMS, start=1):
            target.set_band_description(index, transform.name)


def write_mask(path: Path, *, transform_shift: float = 0.0) -> None:
    row, column = np.mgrid[0:8, 0:8]
    values = ((row + column) % 2).astype(np.uint8)
    values[0, 0] = 255
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=1,
        dtype="uint8",
        crs="EPSG:32647",
        transform=from_origin(600000.0 + transform_shift, 2200080.0, 10.0, 10.0),
        nodata=255,
    ) as target:
        target.write(values, 1)
        target.set_band_description(1, "flood_class")


def make_contract(
    workspace: Path,
    *,
    sidecar_sha256: str = "b" * 64,
    encoded_feature_sha256: str = "e" * 64,
    reference_mask_sha256: str = "f" * 64,
    checkpoint_sha256: str = "c" * 64,
    **overrides: Any,
) -> GeoAIRunContract:
    contract = GeoAIRunContract(
        run_id="geoai-synthetic-proof-001",
        study_area="synthetic_contract_grid",
        run_status="blocked",
        geoai_version="0.41.1",
        geoai_commit=EXPECTED_GEOAI_COMMIT,
        model_id="floodguard/synthetic-unet",
        model_revision="contract-proof-1",
        model_sha256=checkpoint_sha256,
        architecture="unet",
        encoder="resnet34",
        encoder_weights=None,
        preprocessing=PreprocessingContract(
            method="clip_linear_uint8_v1",
            channel_names=tuple(item.name for item in DEFAULT_TRANSFORMS),
            transforms=tuple(
                BandTransformContract(
                    name=item.name,
                    physical_min=item.physical_min,
                    physical_max=item.physical_max,
                    units=item.units,
                    description=item.description,
                )
                for item in DEFAULT_TRANSFORMS
            ),
            sidecar_sha256=sidecar_sha256,
        ),
        channel_count=len(DEFAULT_TRANSFORMS),
        encoded_feature_sha256=encoded_feature_sha256,
        reference_mask_sha256=reference_mask_sha256,
        prepared_tile_manifest_sha256=None,
        spatial_partitions=(
            SpatialPartitionContract(
                spatial_group_id="train-zone-01",
                split="train",
                bounds=(600000.0, 2200000.0, 600040.0, 2200080.0),
            ),
            SpatialPartitionContract(
                spatial_group_id="holdout-zone-01",
                split="holdout",
                bounds=(600040.0, 2200000.0, 600080.0, 2200080.0),
            ),
        ),
        input_manifest_rows=(
            InputManifestRow(
                role="pre_event_sar",
                product_id="SYNTHETIC-PRE-001",
                sha256="a" * 64,
                source_timestamp="2024-09-10T00:00:00Z",
                processing_allowed=True,
            ),
            InputManifestRow(
                role="post_event_sar",
                product_id="SYNTHETIC-POST-001",
                sha256="d" * 64,
                source_timestamp="2024-09-15T23:16:01Z",
                processing_allowed=True,
            ),
            InputManifestRow(
                role="reference_mask",
                product_id="SYNTHETIC-MASK-001",
                sha256=reference_mask_sha256,
                source_timestamp="2024-09-16T00:00:00Z",
                processing_allowed=True,
            ),
            InputManifestRow(
                role="terrain_slope",
                product_id="SYNTHETIC-SLOPE-001",
                sha256="1" * 64,
                source_timestamp="2024-09-01T00:00:00Z",
                processing_allowed=True,
            ),
            InputManifestRow(
                role="permanent_water",
                product_id="SYNTHETIC-WATER-001",
                sha256="2" * 64,
                source_timestamp="2024-09-01T00:00:00Z",
                processing_allowed=True,
            ),
        ),
        reference_mask_id="SYNTHETIC-MASK-001",
        reference_mask_status="confirmed_for_model_purpose",
        target_crs="EPSG:32647",
        resolution=(10.0, 10.0),
        bounds=(600000.0, 2200000.0, 600080.0, 2200080.0),
        tile_size=4,
        overlap=1,
        stride=3,
        batch_size=1,
        device="cpu",
        flood_class_index=1,
        probability_threshold=0.5,
        external_output_workspace=workspace,
        source_timestamp="2024-09-15T23:16:01Z",
        source_name="Synthetic GeoAI contract proof",
        data_version="geoai-synthetic-proof-v1",
        confidence_class="low",
        assumptions=(
            "Synthetic inputs prove integration wiring and do not establish flood accuracy.",
        ),
        processing_scope="synthetic_contract_proof_only",
        processing_allowed=True,
        can_feed_decision_layer=False,
        reason_blocked="Synthetic candidate proof cannot feed the decision layer.",
        validation_metrics=ValidationMetricsContract(
            iou=None,
            f1_dice=None,
            precision=None,
            recall=None,
            area_error_ratio=None,
            brier_score=None,
            expected_calibration_error=None,
        ),
        floodguard_commit=FLOODGUARD_COMMIT,
        spatial_holdout_ids=("holdout-zone-01",),
    )
    if overrides:
        contract = replace(contract, **overrides)
    contract.validate()
    return contract


def write_contract_json(contract: GeoAIRunContract, path: Path) -> None:
    payload = asdict(contract)
    payload["external_output_workspace"] = str(contract.external_output_workspace)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
