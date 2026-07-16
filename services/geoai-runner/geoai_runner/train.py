"""GeoAI training wrapper with a separate, immutable spatial holdout."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from .contract import GeoAIRunContract
from .prepare import (
    file_sha256,
    require_file_sha256,
    require_within_workspace,
    validate_prepared_tile_manifest,
)
from .preprocess import validate_transform_sidecar


@dataclass(frozen=True, slots=True)
class TrainingReceipt:
    """Stock trainer result plus a metadata-bound checkpoint receipt."""

    trainer_result: Any
    raw_state_sha256: str
    packaged_checkpoint_path: Path
    packaged_checkpoint_sha256: str


def train_segmentation_candidate(
    contract: GeoAIRunContract,
    train_images_dir: Path,
    train_labels_dir: Path,
    output_dir: Path,
    *,
    prepared_manifest_path: Path,
    sidecar_path: Path,
    trainer: Callable[..., Any] | None = None,
    checkpoint_loader: Callable[[Path], Any] | None = None,
    checkpoint_saver: Callable[[dict[str, Any], Path], None] | None = None,
    epochs: int = 20,
) -> TrainingReceipt:
    """Train on non-holdout tiles; GeoAI's random split is monitoring only.

    Exact tile membership and spatial groups come from a checksum-bound manifest.
    Metrics from GeoAI's internal random training split are never promotion evidence.
    """

    contract.validate()
    if not contract.processing_allowed:
        raise PermissionError("Run contract blocks training.")
    if contract.run_status not in {"prepared", "running"}:
        raise ValueError("Training requires a prepared or running run contract.")
    if contract.encoder_weights is not None:
        raise ValueError(
            "SAR candidates start with encoder_weights=None unless separately justified."
        )
    if type(epochs) is not int or epochs <= 0:
        raise ValueError("epochs must be positive.")
    images = require_within_workspace(
        train_images_dir,
        contract.external_output_workspace,
    )
    labels = require_within_workspace(
        train_labels_dir,
        contract.external_output_workspace,
    )
    sidecar = require_within_workspace(
        sidecar_path,
        contract.external_output_workspace,
    )
    validate_transform_sidecar(sidecar, contract.preprocessing)
    validate_prepared_tile_manifest(
        contract,
        images,
        labels,
        prepared_manifest_path,
    )
    output = require_within_workspace(output_dir, contract.external_output_workspace)
    output.mkdir(parents=True, exist_ok=True)
    if trainer is None:
        trainer = import_module("geoai.train").train_segmentation_model
    trainer_result = trainer(
        images_dir=str(images),
        labels_dir=str(labels),
        output_dir=str(output),
        input_format="directory",
        architecture=contract.architecture,
        encoder_name=contract.encoder,
        encoder_weights=None,
        num_channels=contract.channel_count,
        num_classes=2,
        ignore_index=255,
        batch_size=contract.batch_size,
        num_epochs=epochs,
        val_split=0.2,
        device=contract.device,
        seed=42,
        save_best_only=True,
    )
    return package_trained_checkpoint(
        contract,
        output / "best_model.pth",
        output / "floodguard_model.pth",
        trainer_result=trainer_result,
        prepared_manifest_path=prepared_manifest_path,
        checkpoint_loader=checkpoint_loader,
        checkpoint_saver=checkpoint_saver,
    )


def package_trained_checkpoint(
    contract: GeoAIRunContract,
    raw_state_path: Path,
    packaged_path: Path,
    *,
    trainer_result: Any = None,
    prepared_manifest_path: Path,
    checkpoint_loader: Callable[[Path], Any] | None = None,
    checkpoint_saver: Callable[[dict[str, Any], Path], None] | None = None,
) -> TrainingReceipt:
    """Wrap stock GeoAI state_dict output in a reproducible FloodGuard envelope."""

    contract.validate()
    if contract.run_status not in {"prepared", "running"}:
        raise ValueError("Checkpoint packaging requires a prepared or running contract.")
    prepared_manifest = require_within_workspace(
        prepared_manifest_path,
        contract.external_output_workspace,
    )
    if contract.prepared_tile_manifest_sha256 is None:
        raise ValueError("Checkpoint packaging requires a prepared manifest receipt.")
    require_file_sha256(
        prepared_manifest,
        contract.prepared_tile_manifest_sha256,
        "Prepared tile manifest",
    )
    raw = require_within_workspace(
        raw_state_path,
        contract.external_output_workspace,
    )
    packaged = require_within_workspace(
        packaged_path,
        contract.external_output_workspace,
    )
    if raw in {packaged, prepared_manifest} or not raw.is_file():
        raise ValueError("Stock GeoAI best_model.pth is required for checkpoint packaging.")
    if packaged.exists():
        raise FileExistsError("Packaged checkpoint already exists; use a fresh output directory.")
    loader = checkpoint_loader or _load_torch_state
    raw_payload = loader(raw)
    state_dict = (
        raw_payload["model_state_dict"]
        if isinstance(raw_payload, Mapping) and "model_state_dict" in raw_payload
        else raw_payload
    )
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ValueError("Stock GeoAI checkpoint must contain a non-empty model state_dict.")
    raw_receipt = file_sha256(raw)
    envelope = {
        "floodguard_checkpoint_schema": "1.1",
        "model_state_dict": state_dict,
        "source_state_sha256": raw_receipt,
        "model_id": contract.model_id,
        "model_revision": contract.model_revision,
        "architecture": contract.architecture,
        "encoder_name": contract.encoder,
        "num_channels": contract.channel_count,
        "num_classes": 2,
        "geoai_version": contract.geoai_version,
        "geoai_commit": contract.geoai_commit,
        "floodguard_commit": contract.floodguard_commit,
        **contract.training_lineage_receipts(),
    }
    packaged.parent.mkdir(parents=True, exist_ok=True)
    temporary = packaged.with_suffix(packaged.suffix + ".tmp")
    saver = checkpoint_saver or _save_torch_state
    saver(envelope, temporary)
    if not temporary.is_file():
        raise ValueError("Checkpoint saver did not create the packaged model file.")
    temporary.replace(packaged)
    return TrainingReceipt(
        trainer_result=trainer_result,
        raw_state_sha256=raw_receipt,
        packaged_checkpoint_path=packaged,
        packaged_checkpoint_sha256=file_sha256(packaged),
    )


def _load_torch_state(path: Path) -> Any:
    torch = import_module("torch")
    return torch.load(str(path), map_location="cpu", weights_only=True)


def _save_torch_state(payload: dict[str, Any], path: Path) -> None:
    torch = import_module("torch")
    torch.save(payload, str(path))
