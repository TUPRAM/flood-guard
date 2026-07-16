"""Redacted, shared-contract model-run manifests for Studio and the API."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import jsonschema
from jsonschema import FormatChecker

from .contract import PRIVATE_PATH_RE, GeoAIRunContract
from .prepare import require_within_workspace

REQUIRED_METRICS = (
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "area_error_ratio",
    "brier_score",
    "expected_calibration_error",
)


class ManifestError(ValueError):
    """Raised when public model evidence is incomplete or unsafe."""


def build_public_model_run(
    contract: GeoAIRunContract,
    *,
    validation_metrics: Mapping[str, float | None] | None = None,
    error_categories: Iterable[str] = (),
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Project an internal run contract into the shared model-run schema."""

    contract.validate()
    metric_source = (
        contract.validation_metrics.as_dict() if validation_metrics is None else validation_metrics
    )
    metrics = _validated_metrics(metric_source)
    if contract.can_feed_decision_layer:
        bound_metrics = _validated_metrics(contract.validation_metrics.as_dict())
        if any(value is None for value in metrics.values()) or metrics != bound_metrics:
            raise ManifestError(
                "Decision-layer output requires complete metrics bound to the run contract."
            )
    categories = _validated_categories(error_categories)
    created = generated_at or datetime.now(UTC)
    if created.tzinfo is None or created.utcoffset() is None:
        raise ManifestError("generated_at must include a timezone.")

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "dataset_mode": contract.dataset_mode,
        "operational_status": contract.operational_status,
        "source_timestamp": contract.source_timestamp,
        "generated_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "confidence_class": contract.confidence_class,
        "source_name": contract.source_name,
        "assumptions": list(contract.assumptions),
        "official_warning": False,
        "data_version": contract.data_version,
        "git_commit": contract.floodguard_commit,
        "run_id": contract.run_id,
        "study_area": contract.study_area,
        "model_family": "geoai",
        "run_status": contract.run_status,
        "geoai_version": contract.geoai_version,
        "geoai_commit": contract.geoai_commit,
        "model_id": contract.model_id,
        "model_revision": contract.model_revision,
        "model_sha256": contract.model_sha256,
        "architecture": contract.architecture,
        "encoder": contract.encoder,
        "encoder_weights": contract.encoder_weights,
        "num_channels": contract.channel_count,
        "channel_names": list(contract.preprocessing.channel_names),
        "preprocessing": {
            "method": contract.preprocessing.method,
            "value_domain": "uint8_0_255",
            "sidecar_sha256": contract.preprocessing.sidecar_sha256,
            "transforms": [
                {
                    "name": transform.name,
                    "physical_min": transform.physical_min,
                    "physical_max": transform.physical_max,
                    "units": transform.units,
                    "description": transform.description,
                }
                for transform in contract.preprocessing.transforms
            ],
        },
        "input_manifest_rows": [
            {
                "product_id": row.product_id,
                "role": row.role,
                "sha256": row.sha256,
                "source_timestamp": row.source_timestamp,
                "processing_allowed": row.processing_allowed,
            }
            for row in contract.input_manifest_rows
        ],
        "encoded_feature_sha256": contract.encoded_feature_sha256,
        "reference_mask_sha256": contract.reference_mask_sha256,
        "prepared_tile_manifest_sha256": contract.prepared_tile_manifest_sha256,
        "spatial_holdout_ids": list(contract.spatial_holdout_ids),
        "spatial_partitions": [
            {
                "spatial_group_id": partition.spatial_group_id,
                "split": partition.split,
                "bounds": list(partition.bounds),
            }
            for partition in contract.spatial_partitions
        ],
        "reference_mask_id": contract.reference_mask_id,
        "reference_mask_status": contract.reference_mask_status,
        "target_crs": contract.target_crs,
        "resolution": list(contract.resolution),
        "bounds": list(contract.bounds),
        "tile_size": contract.tile_size,
        "overlap": contract.overlap,
        "stride": contract.stride,
        "batch_size": contract.batch_size,
        "device": contract.device,
        "flood_class_index": contract.flood_class_index,
        "probability_threshold": contract.probability_threshold,
        "external_output_workspace": f"external-workspace/{contract.run_id}",
        "processing_scope": contract.processing_scope,
        "processing_allowed": contract.processing_allowed,
        "can_feed_decision_layer": contract.can_feed_decision_layer,
        "reason_blocked": contract.reason_blocked,
        "validation_metrics": metrics,
        "error_categories": categories,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if PRIVATE_PATH_RE.search(serialized):
        raise ManifestError("Public model-run manifest contains a private absolute path.")
    _validate_shared_schema(payload)
    return payload


def write_public_model_run(
    path: Path,
    contract: GeoAIRunContract,
    *,
    validation_metrics: Mapping[str, float | None] | None = None,
    error_categories: Iterable[str] = (),
    generated_at: datetime | None = None,
) -> str:
    """Write canonical public JSON inside the external workspace and return SHA-256."""

    output = require_within_workspace(path, contract.external_output_workspace)
    payload = build_public_model_run(
        contract,
        validation_metrics=validation_metrics,
        error_categories=error_categories,
        generated_at=generated_at,
    )
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output)
    return hashlib.sha256(encoded).hexdigest()


def _validated_metrics(
    values: Mapping[str, float | None] | None,
) -> dict[str, float | None]:
    if values is not None and not isinstance(values, Mapping):
        raise ManifestError("validation_metrics must be an object.")
    supplied = {} if values is None else values
    if any(not isinstance(name, str) for name in supplied):
        raise ManifestError("Validation metric names must be strings.")
    unknown = sorted(set(supplied) - set(REQUIRED_METRICS))
    if unknown:
        raise ManifestError("Unknown validation metric(s): " + ", ".join(unknown))
    result: dict[str, float | None] = {}
    for name in REQUIRED_METRICS:
        raw = supplied.get(name)
        if raw is None:
            result[name] = None
            continue
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise ManifestError(f"{name} must be numeric or null.")
        value = float(raw)
        if not math.isfinite(value):
            raise ManifestError(f"{name} must be finite or null.")
        if name == "area_error_ratio":
            if value < 0:
                raise ManifestError("area_error_ratio must be non-negative.")
        elif not 0 <= value <= 1:
            raise ManifestError(f"{name} must be between 0 and 1.")
        result[name] = value
    return result


def _validated_categories(values: Iterable[str]) -> list[str]:
    if isinstance(values, str | bytes) or not isinstance(values, Iterable):
        raise ManifestError("error_categories must be an array of strings.")
    categories: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise ManifestError("Error categories must be non-empty strings.")
        value = raw.strip()
        if value not in categories:
            categories.append(value)
    return categories


def _validate_shared_schema(payload: dict[str, object]) -> None:
    try:
        schema = json.loads(
            files("geoai_runner")
            .joinpath("schemas/model-run.schema.json")
            .read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(payload)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
        raise ManifestError(f"Public model-run manifest violates the shared schema: {exc}") from exc
