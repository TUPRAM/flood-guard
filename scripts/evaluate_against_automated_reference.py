"""Evaluate both frozen Mae Sai SAR candidates against one automated optical map."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.automated_reference import (
    AutomatedReferenceError,
    validate_automated_reference_receipt,
)

from floodguard.observation_evaluation import (
    AUTOMATED_PREREG_PATH,
    ObservationEvaluationError,
    evaluate_against_automated_reference,
    validate_automated_preregistration,
    verify_automated_preregistration_commit,
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assignments(items: list[str], expected: set[str], label: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for item in items:
        identifier, separator, path = item.partition("=")
        if not separator or not path or identifier in found:
            raise ObservationEvaluationError(f"{label} needs one unique PRODUCT_ID=PATH per candidate")
        found[identifier] = Path(path)
    if set(found) != expected:
        raise ObservationEvaluationError(f"{label} must name exactly the two predeclared candidates")
    return found


def _read_reference(path: Path, plan: dict):
    import rasterio

    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None or str(dataset.crs) != plan["grid"]["crs"]:
            raise ObservationEvaluationError("automated reference has the wrong band count or CRS")
        transform = dataset.transform
        pixel = plan["grid"]["pixel_size_m"]
        if transform.a != pixel or transform.e != -pixel or transform.b != 0 or transform.d != 0:
            raise ObservationEvaluationError("automated reference has the wrong 10 m grid")
        return dataset.read(1), transform, dataset.crs


def _read_aligned_candidate(path: Path, receipt_path: Path, declared: dict, shape, transform, crs):
    import numpy as np
    import rasterio
    from rasterio.warp import Resampling, reproject

    raster_hash = _file_sha256(path)
    receipt_hash = _file_sha256(receipt_path)
    if raster_hash != declared["raster_sha256"] or receipt_hash != declared["source_receipt_sha256"]:
        raise ObservationEvaluationError(f"candidate {declared['product_id']} source hash differs from pre-registration")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None or str(dataset.crs) != "EPSG:32647":
            raise ObservationEvaluationError(f"candidate {declared['product_id']} has the wrong band count or CRS")
        affine = dataset.transform
        native = declared["native_pixel_size_m"]
        if affine.a != native or affine.e != -native or affine.b != 0 or affine.d != 0:
            raise ObservationEvaluationError(f"candidate {declared['product_id']} has the wrong native grid")
        raw = dataset.read(1)
        if raw.dtype.kind not in "ui" or not set(np.unique(raw).tolist()) <= {0, 1, 255}:
            raise ObservationEvaluationError(f"candidate {declared['product_id']} has invalid source codes")
        grid = {
            "crs": str(dataset.crs), "width": dataset.width, "height": dataset.height,
            "transform": list(tuple(affine)[:6]), "nodata": dataset.nodata,
        }
        bounds = [dataset.bounds.left, dataset.bounds.bottom, dataset.bounds.right, dataset.bounds.top]
        _validate_candidate_receipt(receipt, raster_hash, grid, declared)
        aligned = np.full(shape, 255, dtype=np.uint8)
        reproject(
            source=raw, destination=aligned, src_transform=affine, src_crs=dataset.crs,
            src_nodata=255, dst_transform=transform, dst_crs=crs, dst_nodata=255,
            resampling=Resampling.nearest, num_threads=1,
        )
    source_timestamp = receipt.get("post_observed_at_utc") or receipt.get("source_timestamp")
    if not isinstance(source_timestamp, str) or not source_timestamp:
        raise ObservationEvaluationError(f"candidate {declared['product_id']} source timestamp is missing")
    metadata = {
        "source_raster_sha256": raster_hash,
        "source_receipt_sha256": receipt_hash,
        "source_grid": grid,
        "source_bounds": bounds,
        "source_timestamp": source_timestamp,
    }
    return aligned, metadata


def _validate_candidate_receipt(receipt: dict, raster_hash: str, grid: dict, declared: dict) -> None:
    if declared["source_receipt_kind"] == "candidate_receipt.json":
        expected = receipt.get("outputs", {}).get("candidate_mask", {}).get("sha256")
        receipt_grid = receipt.get("grid", {})
        matches_grid = (
            receipt_grid.get("crs") == grid["crs"]
            and receipt_grid.get("width") == grid["width"]
            and receipt_grid.get("height") == grid["height"]
            and receipt_grid.get("transform") == grid["transform"]
        )
    else:
        expected = receipt.get("mask_sha256")
        receipt_grid = receipt.get("grid", {})
        matches_grid = (
            receipt_grid.get("crs") == grid["crs"]
            and receipt_grid.get("shape") == [grid["height"], grid["width"]]
            and receipt_grid.get("transform") == grid["transform"]
        )
        if receipt.get("threshold_db") != declared.get("existing_threshold_db"):
            raise ObservationEvaluationError("amplitude comparator threshold differs from pre-registration")
    if expected != raster_hash or not matches_grid:
        raise ObservationEvaluationError(f"candidate {declared['product_id']} receipt does not bind its raster grid and bytes")


def main(argv: list[str] | None = None) -> int:
    """Read exact inputs, run one role for both candidates and write a result once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--asset-manifest", type=Path, required=True)
    parser.add_argument("--reference-receipt", type=Path, required=True)
    parser.add_argument("--reference-raster", type=Path, required=True)
    parser.add_argument("--candidate", action="append", default=[], metavar="PRODUCT_ID=PATH")
    parser.add_argument("--candidate-source-receipt", action="append", default=[], metavar="PRODUCT_ID=PATH")
    parser.add_argument("--role", choices=("development", "final_holdout"), required=True)
    parser.add_argument("--development-result", type=Path)
    parser.add_argument("--holdout-ledger-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.output.exists():
            raise ObservationEvaluationError(f"refusing to overwrite {args.output}")
        prereg_path = REPO_ROOT / AUTOMATED_PREREG_PATH
        plan = validate_automated_preregistration(json.loads(prereg_path.read_text(encoding="utf-8")))
        verify_automated_preregistration_commit(plan, args.preregistration_commit, REPO_ROOT)
        reference = validate_automated_reference_receipt(
            args.reference_receipt, manifest=args.asset_manifest, raster_path=args.reference_raster,
        )
        reference_codes, ref_transform, ref_crs = _read_reference(args.reference_raster, plan)
        expected = {candidate["product_id"]: candidate for candidate in plan["candidate_products"]}
        raster_paths = _assignments(args.candidate, set(expected), "--candidate")
        receipt_paths = _assignments(args.candidate_source_receipt, set(expected), "--candidate-source-receipt")
        aligned, sources = {}, {}
        for identifier, declared in expected.items():
            aligned[identifier], sources[identifier] = _read_aligned_candidate(
                raster_paths[identifier], receipt_paths[identifier], declared,
                reference_codes.shape, ref_transform, ref_crs,
            )
        development = None
        if args.role == "final_holdout":
            if args.development_result is None or args.holdout_ledger_dir is None:
                raise ObservationEvaluationError("final_holdout needs --development-result and --holdout-ledger-dir")
            development = json.loads(args.development_result.read_text(encoding="utf-8"))
        elif args.development_result is not None or args.holdout_ledger_dir is not None:
            raise ObservationEvaluationError("development cannot consume or supply a final holdout")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result = evaluate_against_automated_reference(
            plan, reference, reference_codes, aligned, sources, role=args.role,
            preregistration_commit_sha=args.preregistration_commit,
            reference_raster_sha256=_file_sha256(args.reference_raster),
            development_result=development, external_ledger_dir=args.holdout_ledger_dir,
        )
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        print(f"wrote {args.output}; role={args.role}; agreement with an automated optical map, not accuracy")
        return 0
    except (OSError, ValueError, AutomatedReferenceError, ObservationEvaluationError) as error:
        raise SystemExit(f"blocked: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
