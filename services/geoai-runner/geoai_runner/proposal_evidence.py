"""Small, public-safe evidence artifacts for the proposal-stage GeoAI proof."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio

from .contract import GeoAIRunContract
from .infer import OUTPUT_NODATA
from .prepare import TileExportReceipt, file_sha256


@dataclass(frozen=True, slots=True)
class ProposalProofArtifacts:
    """Paths and checksums for one small, redacted proof receipt and thumbnail."""

    receipt_path: Path
    thumbnail_path: Path
    receipt_file_sha256: str
    receipt_payload_sha256: str
    thumbnail_sha256: str
    probability_raster_sha256: str


def write_proposal_proof_artifacts(
    contract: GeoAIRunContract,
    probability_path: Path,
    export_receipt: TileExportReceipt,
    aggregation_summary: Mapping[str, object],
    output_dir: Path,
    *,
    execution_mode: Literal["real_geoai_smoke", "mocked_unit"],
    training_execution: Literal[
        "model_construction_only",
        "one_epoch_completed",
        "mocked_wrapper_only",
    ],
) -> ProposalProofArtifacts:
    """Write a checksum-bound JSON receipt and PNG without private paths.

    The proof is deliberately candidate/non-operational. A successful synthetic
    smoke validates integration wiring only and can never authorize the
    probability raster for the FloodGuard decision layer.
    """

    contract.validate()
    if contract.dataset_mode != "candidate":
        raise ValueError("Proposal proof artifacts require candidate data mode.")
    if contract.operational_status != "non_operational":
        raise ValueError("Proposal proof artifacts must remain non-operational.")
    if contract.official_warning is not False or contract.can_feed_decision_layer:
        raise ValueError("Proposal proof artifacts must remain fail-closed.")
    if not contract.reason_blocked.strip():
        raise ValueError("Proposal proof artifacts require an explicit blocked reason.")
    if execution_mode == "real_geoai_smoke" and training_execution == "mocked_wrapper_only":
        raise ValueError("Real GeoAI evidence cannot claim a mocked training execution.")
    if execution_mode == "mocked_unit" and training_execution != "mocked_wrapper_only":
        raise ValueError("Mocked unit evidence must identify its mocked training boundary.")

    probability = probability_path.resolve()
    if not probability.is_file():
        raise ValueError("Probability raster is missing.")
    with rasterio.open(probability) as source:
        if (
            source.count != 1
            or source.dtypes != ("float32",)
            or source.descriptions != ("flood_probability_0_1",)
            or source.nodata != OUTPUT_NODATA
        ):
            raise ValueError("Probability raster does not match the class-1 output contract.")
        if (
            source.crs is None
            or source.crs.to_string().casefold() != contract.target_crs.casefold()
        ):
            raise ValueError("Probability raster CRS does not match the run contract.")
        if tuple(source.bounds) != contract.bounds:
            raise ValueError("Probability raster bounds do not match the run contract.")
        if source.res != contract.resolution:
            raise ValueError("Probability raster resolution does not match the run contract.")
        values = source.read(1, masked=True)
        tags = source.tags()
        transform = list(source.transform)
        width = source.width
        height = source.height
    valid = np.asarray(values.compressed(), dtype=np.float64)
    if valid.size == 0 or not np.isfinite(valid).all() or valid.min() < 0 or valid.max() > 1:
        raise ValueError("Probability raster must contain finite valid values in [0,1].")
    required_tags = {
        "run_id": contract.run_id,
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "source_timestamp": contract.source_timestamp,
        "official_warning": "false",
        "can_feed_decision_layer": "false",
        "reason_blocked": contract.reason_blocked,
    }
    if any(tags.get(name) != expected for name, expected in required_tags.items()):
        raise ValueError("Probability raster provenance tags do not match the run contract.")

    if aggregation_summary.get("aggregation_status") != "report_only":
        raise ValueError("Synthetic proposal aggregation must be explicitly report-only.")
    if aggregation_summary.get("eligible_for_decision_layer") is not False:
        raise ValueError("Synthetic proposal aggregation cannot be decision-eligible.")
    if aggregation_summary.get("eligible_for_fpps") is not False:
        raise ValueError("Synthetic proposal aggregation cannot feed FPPS.")
    if aggregation_summary.get("sample_pixel_count") != int(valid.size):
        raise ValueError("Aggregation pixel count does not match the probability raster.")

    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    thumbnail_path = output / "geoai-probability-thumbnail.png"
    _write_probability_png(values, thumbnail_path)
    thumbnail_sha256 = file_sha256(thumbnail_path)
    probability_sha256 = file_sha256(probability)
    histogram_counts, histogram_edges = np.histogram(
        valid,
        bins=np.linspace(0.0, 1.0, 11, dtype=np.float64),
    )
    actual_calls = (
        [
            "geoai.utils.training.export_geotiff_tiles",
            "geoai.inference.predict_geotiff",
        ]
        if execution_mode == "real_geoai_smoke"
        else []
    )
    generated_at = tags.get("generated_at") or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "proof_scope": "synthetic_integration_only",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "generated_at": generated_at,
        "source_timestamp": contract.source_timestamp,
        "run_id": contract.run_id,
        "geoai_version": contract.geoai_version,
        "geoai_commit": contract.geoai_commit,
        "floodguard_commit": contract.floodguard_commit,
        "execution_mode": execution_mode,
        "actual_geoai_calls": actual_calls,
        "training_execution": training_execution,
        "model": {
            "model_id": contract.model_id,
            "model_revision": contract.model_revision,
            "model_sha256": contract.model_sha256,
            "architecture": contract.architecture,
            "encoder": contract.encoder,
            "encoder_weights": contract.encoder_weights,
        },
        "feature_stack": {
            "feature_stack_id": f"{contract.preprocessing.method}-{contract.channel_count}-band",
            "preprocessing_id": contract.preprocessing.method,
            "value_domain": "uint8_0_255",
            "channel_count": contract.channel_count,
            "channel_names": list(contract.preprocessing.channel_names),
            "input_manifest_sha256": contract.input_manifest_sha256,
            "encoded_feature_sha256": contract.encoded_feature_sha256,
            "preprocessing_sidecar_sha256": contract.preprocessing.sidecar_sha256,
        },
        "tile_export": {
            "prepared_tile_manifest_sha256": export_receipt.prepared_manifest_sha256,
            "training_tile_count": export_receipt.training_tile_count,
            "holdout_tile_count": export_receipt.holdout_tile_count,
            "rejected_boundary_tile_count": export_receipt.rejected_boundary_tile_count,
        },
        "probability": {
            "artifact_name": "external-workspace/flood-probability.tif",
            "sha256": probability_sha256,
            "band_name": "flood_probability_0_1",
            "class_index": 1,
            "dtype": "float32",
            "nodata": OUTPUT_NODATA,
            "minimum": float(valid.min()),
            "maximum": float(valid.max()),
            "mean": float(valid.mean()),
            "valid_pixel_count": int(valid.size),
            "histogram_bin_edges": [float(value) for value in histogram_edges],
            "histogram_counts": [int(value) for value in histogram_counts],
            "grid": {
                "crs": contract.target_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "bounds": list(contract.bounds),
                "resolution": list(contract.resolution),
            },
        },
        "thumbnail": {
            "relative_path": thumbnail_path.name,
            "media_type": "image/png",
            "sha256": thumbnail_sha256,
        },
        "validation_checks": {
            "crs": True,
            "transform": True,
            "shape": True,
            "nodata": True,
            "class_mapping": True,
            "probability_range": True,
            "provenance_tags": True,
        },
        "aggregation": {
            "status": "report_only",
            "sample_pixel_count": aggregation_summary["sample_pixel_count"],
            "mean_flood_probability_0_1": aggregation_summary[
                "mean_flood_probability_0_1"
            ],
            "p90_flood_probability_0_1": aggregation_summary[
                "p90_flood_probability_0_1"
            ],
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
        },
        "processing_allowed": contract.processing_allowed,
        "can_feed_decision_layer": False,
        "reason_blocked": contract.reason_blocked,
        "claim_boundary": (
            "Synthetic integration proof; not evidence of real flood-detection accuracy."
        ),
    }
    receipt_payload_sha256 = _canonical_sha256(payload)
    payload["receipt_payload_sha256"] = receipt_payload_sha256
    receipt_path = output / "geoai-proof-receipt.json"
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return ProposalProofArtifacts(
        receipt_path=receipt_path,
        thumbnail_path=thumbnail_path,
        receipt_file_sha256=file_sha256(receipt_path),
        receipt_payload_sha256=receipt_payload_sha256,
        thumbnail_sha256=thumbnail_sha256,
        probability_raster_sha256=probability_sha256,
    )


def validate_proposal_proof_receipt(path: Path) -> dict[str, object]:
    """Validate the self-checksum and every safety-significant claim boundary."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Proposal proof receipt must be a JSON object.")
    receipt_sha256 = payload.pop("receipt_payload_sha256", None)
    if not isinstance(receipt_sha256, str) or receipt_sha256 != _canonical_sha256(payload):
        raise ValueError("Proposal proof receipt checksum is invalid.")

    aggregation = payload.get("aggregation")
    probability = payload.get("probability")
    validation = payload.get("validation_checks")
    execution_mode = payload.get("execution_mode")
    if execution_mode == "real_geoai_smoke":
        execution_is_valid = (
            payload.get("training_execution") == "model_construction_only"
            and payload.get("actual_geoai_calls")
            == [
                "geoai.utils.training.export_geotiff_tiles",
                "geoai.inference.predict_geotiff",
            ]
        )
    elif execution_mode == "mocked_unit":
        execution_is_valid = (
            payload.get("training_execution") == "mocked_wrapper_only"
            and payload.get("actual_geoai_calls") == []
        )
    else:
        execution_is_valid = False

    if (
        payload.get("proof_scope") != "synthetic_integration_only"
        or payload.get("dataset_mode") != "candidate"
        or payload.get("operational_status") != "non_operational"
        or payload.get("official_warning") is not False
        or payload.get("can_feed_decision_layer") is not False
        or not isinstance(payload.get("reason_blocked"), str)
        or not payload["reason_blocked"].strip()
        or payload.get("claim_boundary")
        != "Synthetic integration proof; not evidence of real flood-detection accuracy."
        or not execution_is_valid
        or not isinstance(aggregation, Mapping)
        or aggregation.get("status") != "report_only"
        or aggregation.get("eligible_for_decision_layer") is not False
        or aggregation.get("eligible_for_fpps") is not False
        or not isinstance(probability, Mapping)
        or probability.get("class_index") != 1
        or probability.get("band_name") != "flood_probability_0_1"
        or probability.get("dtype") != "float32"
        or not isinstance(validation, Mapping)
        or not validation
        or any(value is not True for value in validation.values())
        or aggregation.get("sample_pixel_count") != probability.get("valid_pixel_count")
    ):
        raise ValueError("Proposal proof receipt is not fail-closed.")
    payload["receipt_payload_sha256"] = receipt_sha256
    return payload


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_probability_png(values: np.ma.MaskedArray, path: Path) -> None:
    """Write a dependency-free RGBA PNG for the small public evidence bundle."""

    array = np.ma.asarray(values, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError("Probability thumbnail source must be two-dimensional.")
    height, width = array.shape
    scale = max(1, 256 // max(height, width))
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    mask = np.ma.getmaskarray(array)
    clipped = np.clip(array.filled(0.0), 0.0, 1.0)
    low = np.array([7.0, 36.0, 64.0])
    high = np.array([74.0, 222.0, 201.0])
    rgba[:, :, :3] = np.rint(low + clipped[:, :, None] * (high - low)).astype(np.uint8)
    rgba[:, :, 3] = np.where(mask, 0, 255).astype(np.uint8)
    if scale > 1:
        rgba = np.repeat(np.repeat(rgba, scale, axis=0), scale, axis=1)
    png_height, png_width, _ = rgba.shape
    scanlines = b"".join(b"\x00" + row.tobytes() for row in rgba)
    content = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", png_width, png_height, 8, 6, 0, 0, 0),
        )
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(content)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
