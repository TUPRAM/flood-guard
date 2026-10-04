"""Explain the frozen M2 abstention without reading reference labels or retuning it."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject, transform_geom


class DiagnosticError(ValueError):
    """The supplied candidate evidence cannot support this diagnostic."""


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of a local file without loading it all at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict[str, Any]) -> str:
    """Hash JSON in the same canonical form as the M2 processing receipt."""

    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def optical_receipt_sha256(value: dict[str, Any]) -> str:
    """Hash an optical receipt using its Unicode-preserving canonical form."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarize_windows(receipt: dict[str, Any]) -> dict[str, Any]:
    """Summarize frozen window decisions and identify the actual vetoes."""

    windows = receipt["window_receipts"]
    config = receipt["configuration"]
    reasons = Counter(window["reason"] for window in windows)
    variance = [window["qc"]["between_variance_fraction"] for window in windows]
    valid_samples = [window["valid_samples"] for window in windows]
    sole_variance_veto = sum(
        window["status"] == "abstained"
        and window["reason"] == "unimodal_or_unstable_histogram"
        and window["valid_samples"] >= config["min_valid_samples"]
        and window["qc"]["class_fraction_min"] >= config["min_class_fraction"]
        and window["qc"]["mean_separation_db"] >= config["min_mean_separation_db"]
        and window["qc"]["between_variance_fraction"] < config["min_between_variance_fraction"]
        for window in windows
    )
    return {
        "total_windows": len(windows),
        "qualified_windows": sum(window["status"] == "qualified_candidate_window" for window in windows),
        "reason_counts": dict(sorted(reasons.items())),
        "valid_samples_min": min(valid_samples),
        "valid_samples_max": max(valid_samples),
        "between_variance_fraction_min": min(variance),
        "between_variance_fraction_max": max(variance),
        "frozen_min_between_variance_fraction": config["min_between_variance_fraction"],
        "sole_variance_veto_windows": sole_variance_veto,
    }


def aoi_reason_counts(
    abstention_path: Path, target_grid: dict[str, Any], aoi_path: Path, receipt: dict[str, Any]
) -> dict[str, int]:
    """Count candidate abstention codes on the receipt grid without optical label data."""

    output = receipt["outputs"]["abstention_code"]
    if output["file_name"] != abstention_path.name or file_sha256(abstention_path) != output["sha256"]:
        raise DiagnosticError("Abstention raster differs from the frozen M2 receipt")
    with rasterio.open(abstention_path) as source:
        source_grid = receipt["grid"]
        target_crs = target_grid["crs"]
        target_transform = rasterio.Affine(*target_grid["transform"])
        target_width = target_grid["width"]
        target_height = target_grid["height"]
        if (
            source.count != 1
            or str(source.crs) != source_grid["crs"]
            or source.width != source_grid["width"]
            or source.height != source_grid["height"]
            or list(tuple(source.transform)[:6]) != source_grid["transform"]
            or target_crs != "EPSG:32647"
            or str(source.crs) != target_crs
            or source.nodata != 255
        ):
            raise DiagnosticError("Candidate or target grid is inconsistent")
        if (
            target_transform.a <= 0 or target_transform.e >= 0
            or target_transform.b != 0 or target_transform.d != 0
        ):
            raise DiagnosticError("Target grid must be north-up and unrotated")
        aligned = np.full((target_height, target_width), 255, dtype=np.uint8)
        reproject(
            source=rasterio.band(source, 1),
            destination=aligned,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=255,
            dst_transform=target_transform,
            dst_crs=target_crs,
            dst_nodata=255,
            resampling=Resampling.nearest,
            num_threads=1,
        )
        aoi = json.loads(aoi_path.read_text(encoding="utf-8"))
        if aoi.get("type") != "FeatureCollection" or not aoi.get("features"):
            raise DiagnosticError("AOI must be a nonempty GeoJSON FeatureCollection")
        geometries = [
            transform_geom("EPSG:4326", target_crs, feature["geometry"])
            for feature in aoi["features"]
        ]
        inside = rasterize(
            [(geometry, 1) for geometry in geometries],
            out_shape=aligned.shape,
            transform=target_transform,
            fill=0,
            dtype=np.uint8,
        ).astype(bool)
        x_centres = target_transform.c + target_transform.a * (np.arange(target_width) + 0.5)
        y_centres = target_transform.f + target_transform.e * (np.arange(target_height) + 0.5)
        in_source_footprint = (
            (y_centres > source.bounds.bottom) & (y_centres <= source.bounds.top)
        )[:, None] & (
            (x_centres >= source.bounds.left) & (x_centres < source.bounds.right)
        )[None, :]
    codes = aligned[inside]
    if not set(np.unique(codes).tolist()) <= {0, 1, 2, 3, 255}:
        raise DiagnosticError("Abstention raster contains unknown codes inside the AOI")
    return {
        "aoi_cells": int(codes.size),
        "classified_cells": int((codes == 0).sum()),
        "permanent_water_abstained_cells": int((codes == 1).sum()),
        "terrain_abstained_cells": int((codes == 2).sum()),
        "histogram_abstained_cells": int((codes == 3).sum()),
        "unsupported_inside_source_footprint_cells": int((inside & in_source_footprint & (aligned == 255)).sum()),
        "outside_source_footprint_cells": int((inside & ~in_source_footprint).sum()),
    }


def diagnose(
    receipt_path: Path, expected_receipt_sha256: str, reference_receipt_path: Path,
    aoi_path: Path,
) -> dict[str, Any]:
    """Verify the M2 receipt and return a non-operational, reference-blind diagnosis."""

    actual_hash = file_sha256(receipt_path)
    if actual_hash != expected_receipt_sha256:
        raise DiagnosticError("M2 receipt hash differs from the frozen pre-registration")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    self_hash = receipt.pop("manifest_sha256", None)
    if self_hash != canonical_sha256(receipt):
        raise DiagnosticError("M2 receipt self-hash is invalid")
    if (
        receipt.get("artifact_schema") != "floodguard.sentinel1_adaptive_otsu_candidate.v1"
        or receipt.get("result_status") != "abstained_no_classified_cells"
    ):
        raise DiagnosticError("This diagnostic requires a fully abstaining M2 candidate")
    reference_receipt_sha256 = file_sha256(reference_receipt_path)
    reference_receipt = json.loads(reference_receipt_path.read_text(encoding="utf-8"))
    reference_self_hash = reference_receipt.pop("receipt_sha256", None)
    if (
        reference_self_hash != optical_receipt_sha256(reference_receipt)
        or reference_receipt.get("schema") != "floodguard.automated_optical_reference.v1"
        or reference_receipt.get("reference_kind") != "automated_optical_reference"
    ):
        raise DiagnosticError("Optical reference receipt self-hash is invalid")
    if reference_receipt["grid"]["aoi_sha256"] != file_sha256(aoi_path):
        raise DiagnosticError("AOI differs from the optical reference receipt")
    optical_observed_at_utc = reference_receipt["source_timestamp"]
    abstention_path = receipt_path.parent / receipt["outputs"]["abstention_code"]["file_name"]
    if abstention_path.parent != receipt_path.parent:
        raise DiagnosticError("Abstention raster must be beside the receipt")
    mask_record = receipt["outputs"]["candidate_mask"]
    mask_path = receipt_path.parent / mask_record["file_name"]
    if mask_path.parent != receipt_path.parent or file_sha256(mask_path) != mask_record["sha256"]:
        raise DiagnosticError("Candidate mask differs from the frozen M2 receipt")
    with rasterio.open(mask_path) as mask_dataset:
        mask = mask_dataset.read(1)
        source_grid = receipt["grid"]
        if (
            mask_dataset.count != 1
            or str(mask_dataset.crs) != source_grid["crs"]
            or mask_dataset.width != source_grid["width"]
            or mask_dataset.height != source_grid["height"]
            or list(tuple(mask_dataset.transform)[:6]) != source_grid["transform"]
            or not np.all(mask == 255)
        ):
            raise DiagnosticError("The candidate mask is not entirely abstained")
    optical_time = datetime.fromisoformat(optical_observed_at_utc.replace("Z", "+00:00"))
    sar_time = datetime.fromisoformat(receipt["post_observed_at_utc"].replace("Z", "+00:00"))
    if optical_time.tzinfo is None or sar_time.tzinfo is None or sar_time <= optical_time:
        raise DiagnosticError("Optical and SAR post acquisition times must be ordered UTC values")
    result = {
        "schema": "floodguard.sar_m2_abstention_diagnostic.v1",
        "source_receipt_sha256": actual_hash,
        "source_receipt_self_hash_verified": True,
        "source_candidate_mask_sha256": mask_record["sha256"],
        "candidate_non_abstained_cells": 0,
        "aoi_sha256": file_sha256(aoi_path),
        "source_reference_receipt_sha256": reference_receipt_sha256,
        "target_grid_metadata": {
            key: reference_receipt["grid"][key]
            for key in ("crs", "transform", "width", "height")
        },
        "optical_observed_at_utc": optical_observed_at_utc,
        "sar_post_observed_at_utc": receipt["post_observed_at_utc"],
        "optical_to_sar_seconds": round((sar_time - optical_time).total_seconds(), 6),
        "window_summary": summarize_windows(receipt),
        "pilot_grid_counts": receipt["counts"],
        "aoi_counts": aoi_reason_counts(
            abstention_path, reference_receipt["grid"], aoi_path, receipt,
        ),
        "reference_label_values_accessed": False,
        "candidate_rethresholded": False,
        "human_reviewed": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "limitations": [
            "Histogram QC failure explains abstention, not whether flood was present.",
            "The AOI counts describe abstention reasons, not agreement or accuracy against optical labels.",
            "The optical-to-SAR time gap permits scene change; it does not prove recession or progression.",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    return result


def main() -> int:
    """Run a read-only diagnosis and write one small, self-hashed JSON receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--reference-receipt", type=Path, required=True)
    parser.add_argument("--aoi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(
        args.candidate_receipt, args.expected_receipt_sha256,
        args.reference_receipt, args.aoi,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
