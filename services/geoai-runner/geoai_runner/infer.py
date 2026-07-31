"""Tiled GeoAI inference with explicit class-1 probability extraction."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
from numpy.typing import NDArray

from .contract import GeoAIRunContract
from .prepare import require_file_sha256, require_within_workspace
from .preprocess import geoai_uint8_preprocess, validate_transform_sidecar
from .validate import (
    RasterGrid,
    read_grid,
    validate_grid_matches_contract,
    validate_probability_raster,
)

OUTPUT_NODATA = -9999.0


@dataclass(frozen=True, slots=True)
class VerifiedLoadedModel:
    """A model object cryptographically and structurally bound to its checkpoint."""

    model: Any
    checkpoint_sha256: str
    model_revision: str
    architecture: str
    encoder: str
    channel_count: int
    prepared_tile_manifest_sha256: str
    preprocessing_sidecar_sha256: str
    encoded_feature_stack_sha256: str
    reference_mask_sha256: str
    input_manifest_sha256: str


def class1_probability_from_logits(logits: NDArray[np.floating]) -> NDArray[np.float32]:
    """Apply stable softmax and return an explicit `(1,H,W)` flood probability."""

    values = np.asarray(logits, dtype=np.float64)
    if values.ndim != 3 or values.shape[0] != 2:
        raise ValueError("Binary GeoAI output must contain two logit channels.")
    valid = np.all(values != OUTPUT_NODATA, axis=0)
    result = np.full((1, values.shape[1], values.shape[2]), OUTPUT_NODATA, dtype=np.float32)
    if valid.any():
        valid_logits = values[:, valid]
        shifted = valid_logits - valid_logits.max(axis=0, keepdims=True)
        exponent = np.exp(shifted)
        probability = exponent[1] / exponent.sum(axis=0)
        result[0, valid] = probability.astype(np.float32)
    return result


def run_prediction(
    contract: GeoAIRunContract,
    encoded_feature_path: Path,
    sidecar_path: Path,
    checkpoint_path: Path,
    output_path: Path,
    *,
    prepared_manifest_path: Path,
    model_loader: Callable[..., VerifiedLoadedModel] | None = None,
    predictor: Callable[..., Any] | None = None,
    replace_output: bool = False,
) -> RasterGrid:
    """Invoke `geoai.inference.predict_geotiff` without implicit raw-value scaling."""

    contract.validate()
    contract.public_dict()
    if not contract.processing_allowed:
        raise PermissionError("Run contract blocks inference.")
    if contract.run_status != "completed":
        raise ValueError("Inference requires a completed run contract.")
    if type(replace_output) is not bool:
        raise ValueError("replace_output must be a strict boolean.")
    feature = require_within_workspace(
        encoded_feature_path,
        contract.external_output_workspace,
    )
    checkpoint = require_within_workspace(
        checkpoint_path,
        contract.external_output_workspace,
    )
    sidecar = require_within_workspace(
        sidecar_path,
        contract.external_output_workspace,
    )
    prepared_manifest = require_within_workspace(
        prepared_manifest_path,
        contract.external_output_workspace,
    )
    output = require_within_workspace(output_path, contract.external_output_workspace)
    if output in {feature, checkpoint, sidecar, prepared_manifest}:
        raise ValueError("Inference output cannot overwrite an input or training-lineage artifact.")
    if output.exists() and not replace_output:
        raise FileExistsError(
            "Inference output already exists; set replace_output=True explicitly to replace it."
        )
    validate_transform_sidecar(sidecar, contract.preprocessing)
    lineage = contract.training_lineage_receipts()
    require_file_sha256(
        prepared_manifest,
        lineage["prepared_tile_manifest_sha256"],
        "Prepared tile manifest",
    )
    require_file_sha256(
        feature,
        contract.encoded_feature_sha256,
        "Encoded feature",
    )
    if contract.model_sha256 is None:
        raise ValueError("Checkpoint checksum is missing from the run contract.")
    checkpoint_receipt = require_file_sha256(
        checkpoint,
        contract.model_sha256,
        "Checkpoint",
    )
    loader = model_loader or _load_verified_geoai_model
    loaded = loader(
        checkpoint_path=checkpoint,
        checkpoint_sha256=checkpoint_receipt,
        architecture=contract.architecture,
        encoder=contract.encoder,
        channel_count=contract.channel_count,
        model_id=contract.model_id,
        model_revision=contract.model_revision,
        geoai_version=contract.geoai_version,
        geoai_commit=contract.geoai_commit,
        floodguard_commit=contract.floodguard_commit,
        device=contract.device,
        **lineage,
    )
    _validate_loaded_model(loaded, contract, checkpoint_receipt)
    feature_grid = read_grid(feature)
    if (
        not 6 <= feature_grid.count <= 8
        or set(feature_grid.dtypes) != {"uint8"}
        or feature_grid.nodata is not None
    ):
        raise ValueError("Inference input must be the aligned, fully-valid uint8 feature stack.")
    validate_grid_matches_contract(feature_grid, contract)
    output.parent.mkdir(parents=True, exist_ok=True)
    if predictor is None:
        predictor = import_module("geoai.inference").predict_geotiff
    temporary = output.with_name(f".{output.stem}.{uuid4().hex}.partial{output.suffix}")
    try:
        predictor(
            model=loaded.model,
            input_raster=str(feature),
            output_raster=str(temporary),
            tile_size=contract.tile_size,
            overlap=contract.overlap,
            batch_size=contract.batch_size,
            input_bands=list(range(1, contract.channel_count + 1)),
            num_classes=2,
            output_dtype="float32",
            output_nodata=OUTPUT_NODATA,
            blend_mode="spline",
            preprocess_fn=geoai_uint8_preprocess,
            postprocess_fn=class1_probability_from_logits,
            device=contract.device,
            verbose=False,
        )
        provenance = _probability_provenance(contract)
        with rasterio.open(temporary, "r+") as destination:
            if destination.count != 1:
                raise ValueError("Postprocessed GeoAI output must contain one probability band.")
            destination.set_band_description(1, "flood_probability_0_1")
            destination.update_tags(**provenance)
        verified_grid = validate_probability_raster(
            temporary,
            feature_grid,
            expected_tags=provenance,
        )
        if output.exists() and not replace_output:
            raise FileExistsError(
                "Inference output appeared during processing; replacement was not authorized."
            )
        temporary.replace(output)
        return verified_grid
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _probability_provenance(contract: GeoAIRunContract) -> dict[str, str]:
    """Return stable public provenance plus an output-generation timestamp."""

    if contract.model_sha256 is None or contract.prepared_tile_manifest_sha256 is None:
        raise ValueError("Completed inference requires model and tile-manifest receipts.")
    return {
        "schema_version": "1.0",
        "run_id": contract.run_id,
        "dataset_mode": contract.dataset_mode,
        "operational_status": contract.operational_status,
        "source_timestamp": contract.source_timestamp,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "confidence_class": contract.confidence_class,
        "source_name": contract.source_name,
        "assumptions": json.dumps(
            list(contract.assumptions),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "official_warning": "false",
        "data_version": contract.data_version,
        "git_commit": contract.floodguard_commit,
        "model_sha256": contract.model_sha256,
        **contract.training_lineage_receipts(),
        "can_feed_decision_layer": str(contract.can_feed_decision_layer).lower(),
        "reason_blocked": contract.reason_blocked,
    }


def _validate_loaded_model(
    loaded: VerifiedLoadedModel,
    contract: GeoAIRunContract,
    checkpoint_sha256: str,
) -> None:
    if not isinstance(loaded, VerifiedLoadedModel):
        raise ValueError("Model loader must return a VerifiedLoadedModel receipt.")
    expected = (
        checkpoint_sha256,
        contract.model_revision,
        contract.architecture,
        contract.encoder,
        contract.channel_count,
        contract.prepared_tile_manifest_sha256,
        contract.preprocessing.sidecar_sha256,
        contract.encoded_feature_sha256,
        contract.reference_mask_sha256,
        contract.input_manifest_sha256,
    )
    actual = (
        loaded.checkpoint_sha256,
        loaded.model_revision,
        loaded.architecture,
        loaded.encoder,
        loaded.channel_count,
        loaded.prepared_tile_manifest_sha256,
        loaded.preprocessing_sidecar_sha256,
        loaded.encoded_feature_stack_sha256,
        loaded.reference_mask_sha256,
        loaded.input_manifest_sha256,
    )
    if actual != expected:
        raise ValueError("Loaded model receipt does not match the verified checkpoint contract.")


def _load_verified_geoai_model(
    *,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    architecture: str,
    encoder: str,
    channel_count: int,
    model_id: str,
    model_revision: str,
    geoai_version: str,
    geoai_commit: str,
    floodguard_commit: str,
    device: str,
    prepared_tile_manifest_sha256: str,
    preprocessing_sidecar_sha256: str,
    encoded_feature_stack_sha256: str,
    reference_mask_sha256: str,
    input_manifest_sha256: str,
) -> VerifiedLoadedModel:
    """Construct the declared architecture and load a metadata-bound checkpoint."""

    train_module = import_module("geoai.train")
    torch = import_module("torch")
    payload = torch.load(
        str(checkpoint_path),
        map_location=device,
        weights_only=True,
    )
    if not isinstance(payload, dict) or "model_state_dict" not in payload:
        raise ValueError("Checkpoint must use the FloodGuard metadata-bound model envelope.")
    expected_metadata = {
        "floodguard_checkpoint_schema": "1.1",
        "model_id": model_id,
        "architecture": architecture,
        "encoder_name": encoder,
        "num_channels": channel_count,
        "num_classes": 2,
        "model_revision": model_revision,
        "geoai_version": geoai_version,
        "geoai_commit": geoai_commit,
        "floodguard_commit": floodguard_commit,
        "prepared_tile_manifest_sha256": prepared_tile_manifest_sha256,
        "preprocessing_sidecar_sha256": preprocessing_sidecar_sha256,
        "encoded_feature_stack_sha256": encoded_feature_stack_sha256,
        "reference_mask_sha256": reference_mask_sha256,
        "input_manifest_sha256": input_manifest_sha256,
    }
    if any(payload.get(name) != value for name, value in expected_metadata.items()):
        raise ValueError("Checkpoint model metadata does not match the run contract.")
    model = train_module.get_smp_model(
        architecture=architecture,
        encoder_name=encoder,
        encoder_weights=None,
        in_channels=channel_count,
        classes=2,
        activation=None,
    )
    model.load_state_dict(payload["model_state_dict"])
    model.to(device)
    model.eval()
    return VerifiedLoadedModel(
        model=model,
        checkpoint_sha256=checkpoint_sha256,
        model_revision=model_revision,
        architecture=architecture,
        encoder=encoder,
        channel_count=channel_count,
        prepared_tile_manifest_sha256=prepared_tile_manifest_sha256,
        preprocessing_sidecar_sha256=preprocessing_sidecar_sha256,
        encoded_feature_stack_sha256=encoded_feature_stack_sha256,
        reference_mask_sha256=reference_mask_sha256,
        input_manifest_sha256=input_manifest_sha256,
    )
