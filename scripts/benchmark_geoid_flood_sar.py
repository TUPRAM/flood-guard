"""Run the frozen GEOID S1GRD radar diagnostic without reading labels in prediction."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.geoid_radar_benchmark import predict_s1grd_sigma0
from floodguard.label_factory.sentinel1_processing import AdaptiveOtsuConfig

AOI = "EMSR712-3"
PROTOCOL_COMMIT = "65cde436967f3ea2e47c4f8b57062bb93d93f01f"
PROTOCOL_RELATIVE = (
    "docs/proposal_execution/automated_track/geoid_sar_benchmark_protocol_v1.json"
)
PREFIX = ("sample", "geoid-flood", AOI)
ROLES = ("s1grd_pre", "s1grd_post", "label", "validity")
COUNTS = ("true_positive", "false_positive", "false_negative", "true_negative")
SOURCE_PATTERN = re.compile(r"^(EMSR712-3-\d+)_s1grd_(pre|post)_(\d{8}T\d{6})\.tif$")
REFERENCE_PATTERN = re.compile(r"^(EMSR712-3-\d+)_(label|validity)\.tif$")


class BenchmarkError(ValueError):
    """The source or protocol cannot support this bounded diagnostic."""


def file_sha256(path: Path) -> str:
    """Hash source bytes without loading a raster into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict[str, Any]) -> str:
    """Hash a receipt with stable JSON serialization."""

    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_result_receipt(path: Path) -> dict[str, Any]:
    """Verify a completed receipt and every candidate raster it names."""

    receipt = json.loads(path.read_text(encoding="utf-8"))
    saved = receipt.pop("receipt_sha256", None)
    if not isinstance(saved, str) or saved != canonical_sha256(receipt):
        raise BenchmarkError("GEOID benchmark receipt self-hash is invalid")
    outputs = receipt.get("candidate_outputs")
    if not isinstance(outputs, dict) or len(outputs) != 29:
        raise BenchmarkError("GEOID benchmark candidate output inventory is incomplete")
    for relative, expected in outputs.items():
        parts = PurePosixPath(relative).parts
        if len(parts) != 2 or parts[0] != "candidates" or not parts[1].endswith(".tif"):
            raise BenchmarkError("Unsafe candidate output path")
        candidate = path.parent.joinpath(*parts)
        if not candidate.is_file() or file_sha256(candidate) != expected:
            raise BenchmarkError(f"Candidate output differs from receipt: {relative}")
    receipt["receipt_sha256"] = saved
    return receipt


def load_protocol(path: Path) -> tuple[dict[str, Any], str]:
    """Require the exact diagnostic design committed before scoring."""

    protocol = json.loads(path.read_text(encoding="utf-8"))
    if (
        protocol.get("schema") != "floodguard.geoid_sar_benchmark_protocol.v1"
        or protocol.get("dataset", {}).get("aoi_id") != AOI
        or protocol["dataset"].get("source_layer") != "s1grd"
        or protocol["dataset"].get("revision") != "868407460bf3db492f50730a57585916baa71dc6"
        or protocol["evaluation"].get("acceptance_limits") is not None
    ):
        raise BenchmarkError("Unexpected GEOID protocol or dataset selection")
    actual = protocol["prediction"]["otsu_parameters"]
    expected = vars(AdaptiveOtsuConfig())
    keys = {
        "window_pixels", "stride_pixels", "min_valid_samples", "histogram_bins",
        "min_class_fraction", "min_mean_separation_db",
        "min_between_variance_fraction",
    }
    if set(actual) != keys or actual != {key: expected[key] for key in keys}:
        raise BenchmarkError("The protocol's Otsu settings differ from the frozen M2 kernel")
    protocol_hash = file_sha256(path)
    frozen = subprocess.run(
        ["git", "show", f"{PROTOCOL_COMMIT}:{PROTOCOL_RELATIVE}"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    if hashlib.sha256(frozen).hexdigest() != protocol_hash:
        raise BenchmarkError("Protocol bytes differ from the pre-scoring commit")
    return protocol, protocol_hash


def discover_tiles(
    source_root: Path, sums_path: Path
) -> tuple[dict[str, dict[str, tuple[Path, str, str | None]]], dict[str, dict[str, Any]]]:
    """Pair every published sample AOI file and verify its published SHA-256."""

    tiles: dict[str, dict[str, tuple[Path, str, str | None]]] = {}
    inventory: dict[str, dict[str, Any]] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if "  " not in line:
            raise BenchmarkError("Malformed published SHA256SUMS line")
        expected_hash, relative = line.split("  ", 1)
        parts = PurePosixPath(relative).parts
        if parts[:3] != PREFIX or len(parts) != 5 or parts[3] not in {
            "s1grd", "label", "validity"
        }:
            continue
        folder, filename = parts[3], parts[4]
        if folder == "s1grd":
            match = SOURCE_PATTERN.fullmatch(filename)
            if match is None:
                raise BenchmarkError(f"Unexpected S1GRD file name: {filename}")
            tile, phase, acquired = match.groups()
            role = f"s1grd_{phase}"
        else:
            match = REFERENCE_PATTERN.fullmatch(filename)
            if match is None or match.group(2) != folder:
                raise BenchmarkError(f"Unexpected reference file name: {filename}")
            tile, role, acquired = match.group(1), folder, None
        if role in tiles.setdefault(tile, {}):
            raise BenchmarkError(f"Duplicate {role} for {tile}")
        path = source_root.joinpath(*parts)
        if not path.is_file() or path.is_symlink():
            raise BenchmarkError(f"Missing or linked published source: {relative}")
        actual_hash = file_sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or actual_hash != expected_hash:
            raise BenchmarkError(f"Published SHA-256 mismatch: {relative}")
        tiles[tile][role] = (path, actual_hash, acquired)
        inventory[relative] = {"sha256": actual_hash, "bytes": path.stat().st_size}
    if len(tiles) != 29 or len(inventory) != 116:
        raise BenchmarkError("Expected all 29 AOI tiles and 116 source assets")
    for tile, roles in tiles.items():
        if set(roles) != set(ROLES):
            raise BenchmarkError(f"Incomplete pre/post/label/validity set for {tile}")
        pre, post = roles["s1grd_pre"][2], roles["s1grd_post"][2]
        if pre is None or post is None or pre >= post or not post.startswith("20240103T053"):
            raise BenchmarkError(f"Unexpected source acquisition times for {tile}")
    return dict(sorted(tiles.items())), dict(sorted(inventory.items()))


def _validate_grid(pre: rasterio.DatasetReader, others: list[rasterio.DatasetReader]) -> None:
    if (
        pre.count != 2
        or pre.width != 1024
        or pre.height != 1024
        or pre.crs is None
        or pre.crs.to_epsg() not in range(32601, 32661)
        or not math.isclose(pre.transform.a, 10)
        or not math.isclose(pre.transform.e, -10)
        or pre.transform.b != 0
        or pre.transform.d != 0
    ):
        raise BenchmarkError("S1GRD must be a two-band north-up 10 m UTM tile")
    for dataset in others:
        if (
            dataset.width != pre.width
            or dataset.height != pre.height
            or dataset.crs != pre.crs
            or dataset.transform != pre.transform
        ):
            raise BenchmarkError("Paired source and reference grids differ")
    if others[0].count != 2 or any(dataset.count != 1 for dataset in others[1:]):
        raise BenchmarkError("Unexpected S1GRD or reference band count")
    for source in (pre, others[0]):
        descriptions = tuple((value or "").upper() for value in source.descriptions)
        if any(descriptions) and descriptions != ("VV", "VH"):
            raise BenchmarkError(f"Unrecognized S1GRD band order: {descriptions}")


def score_candidate(
    candidate: np.ndarray, label: np.ndarray, validity: np.ndarray, *,
    include_permanent_as_negative: bool,
) -> dict[str, Any]:
    """Measure flood agreement only on mapped, valid, non-abstaining cells."""

    if candidate.shape != label.shape or label.shape != validity.shape:
        raise BenchmarkError("Candidate, label, and validity grids differ")
    if not np.isin(candidate, (0, 1, 255)).all():
        raise BenchmarkError("Candidate contains an unknown code")
    if not np.isin(label, (0, 1, 2, 255)).all() or not np.isin(validity, (0, 1)).all():
        raise BenchmarkError("GEOID labels or validity contain unknown codes")
    evaluable = (validity == 1) & np.isin(
        label, (0, 1, 2) if include_permanent_as_negative else (0, 2)
    )
    covered = evaluable & (candidate != 255)
    flood = label == 2
    predicted = candidate == 1
    counts = {
        "true_positive": int((covered & flood & predicted).sum()),
        "false_positive": int((covered & ~flood & predicted).sum()),
        "false_negative": int((covered & flood & ~predicted).sum()),
        "true_negative": int((covered & ~flood & ~predicted).sum()),
        "evaluable_cells": int(evaluable.sum()),
        "covered_cells": int(covered.sum()),
        "reference_flood_cells": int((evaluable & flood).sum()),
        "covered_reference_flood_cells": int((covered & flood).sum()),
        "predicted_flood_cells": int((covered & predicted).sum()),
    }
    return metrics_from_counts(counts)


def metrics_from_counts(counts: dict[str, int]) -> dict[str, Any]:
    """Compute pooled metrics with null for every undefined denominator."""

    tp, fp, fn = (counts[key] for key in COUNTS[:3])

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        **{
            key: int(counts[key])
            for key in (
                *COUNTS, "evaluable_cells", "covered_cells",
                "reference_flood_cells", "covered_reference_flood_cells",
                "predicted_flood_cells",
            )
        },
        "iou": ratio(tp, tp + fp + fn),
        "dice": ratio(2 * tp, 2 * tp + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "evaluated_coverage": ratio(counts["covered_cells"], counts["evaluable_cells"]),
        "reference_flood_prevalence": ratio(
            counts["reference_flood_cells"], counts["evaluable_cells"]
        ),
    }


def run(
    source_root: Path, sums_path: Path, protocol_path: Path, output_directory: Path
) -> Path:
    """Verify all sources, predict without labels, and write an immutable research result."""

    protocol, protocol_hash = load_protocol(protocol_path)
    if output_directory.exists():
        raise BenchmarkError(f"Output directory already exists: {output_directory}")
    tiles, inventory = discover_tiles(source_root, sums_path)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(
        prefix=f".{output_directory.name}-", dir=output_directory.parent
    ))
    try:
        (staged / "candidates").mkdir()
        per_tile: list[dict[str, Any]] = []
        output_hashes: dict[str, str] = {}
        primary_counts: Counter[str] = Counter()
        secondary_counts: Counter[str] = Counter()
        overall_classes: Counter[str] = Counter()
        window_reasons: Counter[str] = Counter()
        for tile, roles in tiles.items():
            with (
                rasterio.open(roles["s1grd_pre"][0]) as pre_ds,
                rasterio.open(roles["s1grd_post"][0]) as post_ds,
                rasterio.open(roles["label"][0]) as label_ds,
                rasterio.open(roles["validity"][0]) as validity_ds,
            ):
                _validate_grid(pre_ds, [post_ds, label_ds, validity_ds])
                pre = np.asarray(pre_ds.read(masked=True).filled(np.nan), dtype="float32")
                post = np.asarray(post_ds.read(masked=True).filled(np.nan), dtype="float32")
                candidate, diagnosis = predict_s1grd_sigma0(pre, post)
                if candidate.shape != (pre_ds.height, pre_ds.width):
                    raise BenchmarkError(f"Predictor returned the wrong shape for {tile}")
                profile = pre_ds.profile.copy()
                profile.update(
                    count=1, dtype="uint8", nodata=255, compress="deflate",
                    predictor=1, tiled=True,
                )
                output_path = staged / "candidates" / f"{tile}_candidate.tif"
                with rasterio.open(output_path, "w", **profile) as destination:
                    destination.write(candidate, 1)
                    destination.update_tags(
                        method="geoid_s1grd_sigma0_m2_change_variant_v1",
                        evidence_tier="research_benchmark_diagnostic",
                    )
                output_hashes[f"candidates/{output_path.name}"] = file_sha256(output_path)
                # No reference pixels are read until the prediction is complete.
                label = label_ds.read(1)
                validity = validity_ds.read(1)
            primary = score_candidate(
                candidate, label, validity, include_permanent_as_negative=True
            )
            secondary = score_candidate(
                candidate, label, validity, include_permanent_as_negative=False
            )
            for key in (*COUNTS, "evaluable_cells", "covered_cells",
                        "reference_flood_cells", "covered_reference_flood_cells",
                        "predicted_flood_cells"):
                primary_counts[key] += primary[key]
                secondary_counts[key] += secondary[key]
            for code in (0, 1, 2, 255):
                overall_classes[str(code)] += int((label == code).sum())
            overall_classes["validity_0"] += int((validity == 0).sum())
            overall_classes["validity_1"] += int((validity == 1).sum())
            window_reasons.update(diagnosis["reason_counts"])
            pre_acquired = datetime.strptime(
                roles["s1grd_pre"][2], "%Y%m%dT%H%M%S"
            ).replace(tzinfo=timezone.utc)
            post_acquired = datetime.strptime(
                roles["s1grd_post"][2], "%Y%m%dT%H%M%S"
            ).replace(tzinfo=timezone.utc)
            per_tile.append({
                "tile_id": tile,
                "pre_acquired_at_utc": pre_acquired.isoformat().replace("+00:00", "Z"),
                "post_acquired_at_utc": post_acquired.isoformat().replace("+00:00", "Z"),
                "prediction": diagnosis,
                "primary": primary,
                "secondary": secondary,
                "candidate_file": f"candidates/{output_path.name}",
                "candidate_sha256": output_hashes[f"candidates/{output_path.name}"],
            })
        receipt: dict[str, Any] = {
            "schema": "floodguard.geoid_s1grd_sigma0_benchmark_result.v1",
            "evidence_tier": "research_benchmark_diagnostic",
            "method": "geoid_s1grd_sigma0_m2_change_variant_v1",
            "source_timestamp": max(row["post_acquired_at_utc"] for row in per_tile),
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "dataset": {
                "repository": protocol["dataset"]["repository"],
                "revision": protocol["dataset"]["revision"],
                "event_id": protocol["dataset"]["event_id"],
                "aoi_id": AOI,
                "tile_count": len(per_tile),
                "source_radiometry": "linear_sigma0_s1grd",
                "published_sha256sums_sha256": file_sha256(sums_path),
                "inputs": inventory,
            },
            "protocol_sha256": protocol_hash,
            "protocol_commit": PROTOCOL_COMMIT,
            "reference_lineage": (
                "GEOID labels combine CEMS Rapid Mapping flood delineation and modelled "
                "permanent water. AOI03 MONIT04 uses the same 2024-01-03 post-event "
                "Sentinel-1 acquisition as the benchmark S1GRD input. All 268 "
                "AOI03 MONIT04 observedEventA features cite that acquisition."
            ),
            "class_counts": dict(sorted(overall_classes.items())),
            "window_reason_counts": dict(sorted(window_reasons.items())),
            "primary_flood_vs_all_mapped_nonflood": metrics_from_counts(primary_counts),
            "secondary_flood_vs_background_only": metrics_from_counts(secondary_counts),
            "per_tile": per_tile,
            "candidate_outputs": output_hashes,
            "score_description": (
                "Agreement with CEMS-derived benchmark labels, not independent flood "
                "accuracy or Mae Sai validation."
            ),
            "limitations": [
                "The labels may use the same post-event Sentinel-1 acquisition as the input.",
                "The GEOID rasterization of the CEMS source vectors was not independently reconstructed.",
                "The sample's train and test AOIs share EMSR712, so this is not a new-event holdout.",
                "S1GRD linear Sigma0 lacks Mae Sai M2's Gamma0 terrain flattening, layover mask, slope mask, and independent permanent-water mask.",
                "Background is a mapped benchmark class, not field-confirmed dry land.",
            ],
            "human_reviewed_by_floodguard": False,
            "accepted_observation": False,
            "official_warning": False,
            "can_feed_decision_layer": False,
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        receipt_path = staged / "result.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staged.rename(output_directory)
        return output_directory / receipt_path.name
    except BaseException:
        shutil.rmtree(staged)
        raise


def main() -> None:
    """Run the diagnostic from verified local GEOID sample assets."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--sha256sums", type=Path, required=True)
    parser.add_argument(
        "--protocol", type=Path,
        default=ROOT / "docs/proposal_execution/automated_track/geoid_sar_benchmark_protocol_v1.json",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    result = run(
        arguments.source_root, arguments.sha256sums, arguments.protocol,
        arguments.output_directory,
    )
    print(result)


if __name__ == "__main__":
    main()
