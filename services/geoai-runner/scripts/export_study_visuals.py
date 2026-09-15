"""Export complete, report-only study previews from frozen local public-model evidence.

The source checkout supplies its own isolated model code and checkpoints. This
command performs inference and display downsampling only: no fitting, network,
calibration selection, benchmark replacement or decision-layer integration.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ARMS = ("sar", "context")
MODELS = ("random_forest", "xgboost", "unet")
STUDY = "c2s-ms-20260915"
REVISION = "r1"
PREFIX = f"/studies/{STUDY}/{REVISION}"
COUNTRIES = {
    "749aca10-a39b-4321-8322-100dd6f976d4": "Australia",
    "975ecc1f-bc34-4005-b2df-ef45775f116d": "Nigeria",
    "c19f5f27-2b3b-4b83-8f4a-cf9275d94cdd": "Pakistan",
}
ASSUMPTIONS = [
    "Report-only research; these outputs cannot feed exposure, roads, access, equity or FPPS.",
    "No qualified Thai reference exists; no Mae Sai accuracy is claimed.",
    "C2S-MS labels describe event-date water including permanent water, not new inundation alone.",
    "PNG previews use nearest-neighbour display downsampling only; no smoothing or seam removal.",
    "Full-resolution benchmark metrics are copied from the frozen reports, never from previews.",
    "Binary and error maps use calibrated probability >=0.5 on the arm's full-valid mask, "
    "before confidence or context abstention.",
    "The SAR and context arms can have different valid masks; grey pixels have no support.",
]
PALETTES = {
    "reference": [(0, "Non-water", "#f2f1e9"), (1, "Water", "#217fa3")],
    "binary": [(0, "Predicted non-water", "#f2f1e9"), (1, "Predicted water", "#217fa3")],
    "error": [
        (0, "TN: correct non-water", "#f2f1e9"),
        (1, "TP: correct water", "#238995"),
        (2, "FP: extra water", "#db7a28"),
        (3, "FN: missed water", "#af3e81"),
    ],
    "validity": [(0, "Invalid", "#b9b9b9"), (1, "Valid", "#dceee3")],
    "abstention": [(0, "Accepted", "#dceee3"), (1, "Abstained", "#ab4c80")],
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def receipt(path: Path, root: Path) -> dict:
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def verify(root: Path, value: dict) -> Path:
    path = (root / value["path"]).resolve()
    expected = {key: value[key] for key in ("path", "bytes", "sha256")}
    if not path.is_relative_to(root) or receipt(path, root) != expected:
        raise ValueError(f"Source receipt changed: {value['path']}")
    return path


def envelope(timestamp: str, license_value, *, dataset: str, assumptions=None) -> dict:
    return {
        "dataset": dataset,
        "data_mode": "real_public_report_only_visualization",
        "source_timestamp": timestamp,
        "license": license_value,
        "assumptions": list(assumptions or ASSUMPTIONS),
        "evidence_tier": "candidate",
        "aggregation_status": "report_only",
        "can_feed_decision_layer": False,
        "official_warning": False,
    }


def extent(grid: dict) -> list[float]:
    a, b, c, d, e, f = grid["transform"]
    if b or d or a <= 0 or e >= 0:
        raise ValueError("Expected north-up study grid")
    return [c, f + e * grid["height"], c + a * grid["width"], f]


def render_preview(
    values: np.ndarray,
    kind: str,
    path: Path,
    metadata: dict,
    public_root: Path,
    *,
    limit: int = 256,
) -> dict:
    """Render measured values, preserving categorical classes and explicit invalid pixels."""
    from matplotlib import colormaps
    from PIL import Image, PngImagePlugin

    values = np.asarray(values)
    if values.ndim != 2 or min(values.shape) < 1 or limit < 1:
        raise ValueError("Preview requires a nonempty two-dimensional raster")
    h, w = values.shape
    scale = min(1, limit / max(h, w))
    height, width = max(1, round(h * scale)), max(1, round(w * scale))
    iy = np.minimum(((np.arange(height) + 0.5) * h / height).astype(int), h - 1)
    ix = np.minimum(((np.arange(width) + 0.5) * w / width).astype(int), w - 1)
    sampled = values[np.ix_(iy, ix)]
    valid = np.isfinite(sampled)
    rgb = np.full((height, width, 3), 185, np.uint8)
    display = {
        "kind": kind,
        "resampling": "nearest_neighbour_display_only",
        "invalid_color": "#b9b9b9",
        "legend": [],
    }
    if kind in PALETTES:
        for value, label, color in PALETTES[kind]:
            rgb[valid & (sampled == value)] = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
            display["legend"].append({"value": value, "label": label, "color": color})
        if np.any(valid & ~np.isin(sampled, [entry[0] for entry in PALETTES[kind]])):
            raise ValueError("Unexpected categorical display value")
    elif kind in ("radar", "probability", "entropy"):
        minimum, maximum = (-30, -5) if kind == "radar" else (0, 1)
        palette = {"radar": "gray", "probability": "viridis", "entropy": "magma"}[kind]
        normalized = np.clip((sampled[valid] - minimum) / (maximum - minimum), 0, 1)
        rgb[valid] = colormaps[palette](normalized, bytes=True)[:, :3]
        display.update(
            min=minimum,
            max=maximum,
            palette=palette,
            units="VH dB"
            if kind == "radar"
            else "probability"
            if kind == "probability"
            else "normalized binary entropy",
        )
    else:
        raise ValueError(f"Unknown layer: {kind}")
    info = PngImagePlugin.PngInfo()
    for key, value in {**metadata, "display": display}.items():
        info.add_text(key, json.dumps(value, separators=(",", ":"), allow_nan=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path, pnginfo=info, optimize=True)
    rec = receipt(path, public_root)
    return {
        **rec,
        "url": "/" + rec["path"],
        "width": width,
        "height": height,
        "native_width": w,
        "native_height": h,
        "display": display,
    }


def binary_error(probability: np.ndarray, label: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Use the complete labelled support; abstention never removes displayed errors."""
    valid = label >= 0
    if probability.shape != label.shape or not np.isfinite(probability[valid]).all():
        raise ValueError("Probability and reference support differ")
    predicted = probability >= 0.5
    binary = np.where(valid, predicted, np.nan)
    error = np.full(label.shape, np.nan)
    error[valid & ~predicted & (label == 0)] = 0
    error[valid & predicted & (label == 1)] = 1
    error[valid & predicted & (label == 0)] = 2
    error[valid & ~predicted & (label == 1)] = 3
    return binary, error


def compact_metrics(values: dict) -> dict:
    return {key: value for key, value in values.items() if key != "reliability"}


def model_entry(report: dict, row: dict, model_metadata: dict, report_receipt: dict) -> dict:
    valid = row["calibrated"]["n_valid_pixels"]
    return {
        "status": "pending" if valid else "unavailable",
        "reason": None if valid else "no_valid_context_support",
        "source_timestamp": model_metadata["source_timestamp"],
        "model_sha256": model_metadata["checkpoint"]["sha256"],
        "checkpoint": model_metadata["checkpoint"],
        "layers": {},
        "support": {
            "n_valid_pixels": valid,
            "n_accepted_pixels": row["combined_screening"]["n_accepted_pixels"],
            "n_reference_positive": row["calibrated"]["full_valid"]["n_reference_positive"],
        },
        "benchmark": {
            "dataset": report["dataset"],
            "source": report_receipt,
            "raw": {"full_valid": compact_metrics(row["raw"]["full_valid"])},
            "calibrated": {"full_valid": compact_metrics(row["calibrated"]["full_valid"])},
            "role": "test",
            "recorded_status": row.get("status", "computed"),
        },
        "calibration": report["calibration"],
        "abstention_policy": report["abstention"],
        "evidence_tier": "candidate",
        "can_feed_decision_layer": False,
        "aggregation_status": "report_only",
    }


def load_sample(source: Path, row: dict) -> tuple[np.ndarray, np.ndarray]:
    with np.load(verify(source, row["file"]), allow_pickle=False) as sample:
        if (
            str(sample["role"].item()) != "test"
            or str(sample["event_id"].item()) != row["event_id"]
            or sample["feature_names"].tolist() != row["feature_names"]
        ):
            raise ValueError("Feature role, event or schema changed")
        features, label = sample["features"], sample["label"]
        if (
            features.shape[1:] != label.shape
            or not np.isin(label, (-1, 0, 1)).all()
            or not np.isfinite(features[:, label >= 0]).all()
        ):
            raise ValueError("Invalid prepared sample")
        return features, label


def reusable(entry: dict, public_root: Path, names: tuple[str, ...]) -> bool:
    if entry.get("status") != "available" or set(entry.get("layers", {})) != set(names):
        return False
    for layer in entry["layers"].values():
        verify(public_root, layer)
    return True


def export(source: Path, destination: Path, *, device: str = "cuda") -> Path:
    """Export all declared cases using frozen inference and recorded benchmark evidence."""
    source, destination = source.resolve(), destination.resolve()
    sys.path[:0] = [str(source / "services/geoai-runner"), str(source / "src")]
    from geoai_runner.realpipeline.flood_evaluation import PlattCalibrator

    work = source / "outputs/geoai/work/public-training"
    public = destination / "apps/web/public"
    directory = public / PREFIX.lstrip("/")
    index_path = directory / "visual-index.json"
    feature_paths = {arm: work / f"c2sms/features/{arm}/manifest.json" for arm in ARMS}
    manifests = {arm: read_json(path) for arm, path in feature_paths.items()}
    for manifest in manifests.values():
        if manifest["status"] != "complete" or len(manifest["chips"]) != 900:
            raise ValueError("Complete 900-chip feature inventories are required")
    partition_path = verify(source, manifests["sar"]["partition"])
    if manifests["context"]["partition"] != manifests["sar"]["partition"]:
        raise ValueError("Model arms use different partitions")
    partition = read_json(partition_path)
    test = {
        arm: {r["chip_id"]: r for r in manifest["chips"] if r["role"] == "test"}
        for arm, manifest in manifests.items()
    }
    if set(test["sar"]) != set(test["context"]) or len(test["sar"]) != 111:
        raise ValueError("Both arms must retain the complete 111-chip test inventory")
    source_paths = {f"features/{arm}": path for arm, path in feature_paths.items()}
    acquisition_path = verify(source, manifests["sar"]["acquisition_manifest"])
    originals = {row["chip_id"]: row for row in read_json(acquisition_path)["chips"]}
    source_paths["acquisition_manifest"] = acquisition_path
    reports, metadata, per_chip = {}, {}, {}
    for arm in ARMS:
        for name in MODELS:
            key = f"{arm}/{name}"
            report_path, model_path = work / f"results/{key}.json", work / f"models/{key}.json"
            report, model = read_json(report_path), read_json(model_path)
            if (
                report["status"] != "computed"
                or report["test_role"] != "frozen_event_disjoint_test"
                or report["model_metadata"] != model
                or model["feature_manifest"] != receipt(feature_paths[arm], source)
                or report["can_feed_decision_layer"] is not False
            ):
                raise ValueError("Computed benchmark/checkpoint binding differs")
            verify(source, model["checkpoint"])
            reports[key], metadata[key] = report, model
            per_chip[key] = {row["chip_id"]: row for row in report["per_chip"]}
            if set(per_chip[key]) != set(test[arm]):
                raise ValueError("Benchmark does not account for every frozen test chip")
            source_paths[f"benchmark/{key}"], source_paths[f"model/{key}"] = report_path, model_path
    contract = {key: receipt(path, source) for key, path in source_paths.items()}
    contract["partition"] = receipt(partition_path, source)
    previous = read_json(index_path) if index_path.exists() else None
    if previous and previous["source_receipts"] != contract:
        raise ValueError("Existing export has different frozen source receipts")
    if previous:
        index = previous
    else:
        index = {
            "schema_version": 1,
            "study_id": STUDY,
            "revision": REVISION,
            "status": "in_progress",
            "source_receipts": contract,
            "metadata": envelope(
                manifests["sar"]["source_timestamp"],
                manifests["context"]["license"],
                dataset=manifests["sar"]["dataset"],
            ),
            "display_contract": {
                "maximum_preview_dimension": 256,
                "resampling": "nearest",
                "benchmark_resolution": "original_full_resolution",
            },
            "chips": [],
            "mae_sai": {},
        }
        for chip_id in sorted(test["sar"], key=lambda key: (test["sar"][key]["event_id"], key)):
            row = test["sar"][chip_id]
            if partition["event_roles"][row["event_id"]] != "test":
                raise ValueError("Test event differs from frozen partition")
            index["chips"].append(
                {
                    "chip_id": chip_id,
                    "event_id": row["event_id"],
                    "event_name": COUNTRIES[row["event_id"]],
                    "country": COUNTRIES[row["event_id"]],
                    "source_timestamp": row["source_timestamp"],
                    "grid": row["grid"],
                    "extent": extent(row["grid"]),
                    "role": "test",
                    "sources": {},
                    "source_metadata_url": originals[chip_id]["source_metadata_url"],
                    "original_sources": {
                        key: {
                            "url": value["source_url"],
                            "sha256": value["sha256"],
                            "bytes": value["bytes"],
                        }
                        for key, value in originals[chip_id]["files"].items()
                    },
                    "source_features": {arm: test[arm][chip_id]["file"] for arm in ARMS},
                    "models": {
                        arm: {
                            name: model_entry(
                                reports[f"{arm}/{name}"],
                                per_chip[f"{arm}/{name}"][chip_id],
                                metadata[f"{arm}/{name}"],
                                contract[f"benchmark/{arm}/{name}"],
                            )
                            for name in MODELS
                        }
                        for arm in ARMS
                    },
                }
            )
            for arm_models in index["chips"][-1]["models"].values():
                for entry in arm_models.values():
                    entry["training_source_timestamp"] = entry["source_timestamp"]
                    entry["source_timestamp"] = row["source_timestamp"]
    write_json(index_path, index)
    for chip in index["chips"]:
        if chip["sources"]:
            for layer in chip["sources"].values():
                verify(public, layer)
            continue
        row = test["sar"][chip["chip_id"]]
        features, label = load_sample(source, row)
        meta = envelope(
            row["source_timestamp"], row["license"], dataset=manifests["sar"]["dataset"]
        )
        meta.update(chip_id=chip["chip_id"], grid=row["grid"], source=row["file"])
        folder = directory / "visuals/chips" / chip["chip_id"]
        for name, values in (
            ("radar", np.where(label >= 0, features[1], np.nan)),
            ("reference", np.where(label >= 0, label, np.nan)),
        ):
            chip["sources"][name] = render_preview(
                values, name, folder / f"{name}.png", meta, public
            )
    write_json(index_path, index)
    export_mae_sai(source, directory, public, index)
    write_json(index_path, index)
    for arm in ARMS:
        for name in MODELS:
            pending = [
                chip
                for chip in index["chips"]
                if chip["models"][arm][name]["status"] != "unavailable"
                and not reusable(
                    chip["models"][arm][name], public, ("probability", "binary", "error")
                )
            ]
            if not pending:
                continue
            model_metadata = metadata[f"{arm}/{name}"]
            checkpoint = verify(source, model_metadata["checkpoint"])
            if name == "unet":
                from geoai_runner.realpipeline.water_unet_sar import load_sar_unet_predictor

                model = load_sar_unet_predictor(checkpoint, device=device)
            else:
                import joblib

                model = joblib.load(checkpoint)
            calibrator = PlattCalibrator.from_dict(reports[f"{arm}/{name}"]["calibration"])
            for number, chip in enumerate(pending, 1):
                row = test[arm][chip["chip_id"]]
                features, label = load_sample(source, row)
                valid = label >= 0
                raw = np.full(label.shape, np.nan, np.float32)
                if name == "unet":
                    raw = model.predict(features, valid_mask=valid)
                else:
                    raw[valid] = model.predict_proba(features[:, valid].T)
                p = np.full_like(raw, np.nan)
                p[valid] = calibrator.predict(raw[valid])
                binary, error = binary_error(p, label)
                entry = chip["models"][arm][name]
                observed = {
                    key: int(np.count_nonzero(error == value))
                    for key, value in (
                        ("true_negative", 0),
                        ("true_positive", 1),
                        ("false_positive", 2),
                        ("false_negative", 3),
                    )
                }
                original = entry["benchmark"]["calibrated"]["full_valid"]
                if int(valid.sum()) != entry["support"]["n_valid_pixels"]:
                    raise ValueError("Preview validity differs from recorded benchmark support")
                entry["display_replay_check"] = {
                    "recorded_counts_match": all(
                        observed[key] == original[key] for key in observed
                    ),
                    "replayed_full_resolution_counts": observed,
                    "semantics": "Display provenance check; authoritative benchmark remains unchanged",
                }
                meta = envelope(
                    row["source_timestamp"],
                    row["license"],
                    dataset=reports[f"{arm}/{name}"]["dataset"],
                )
                meta.update(
                    chip_id=chip["chip_id"],
                    grid=row["grid"],
                    source=row["file"],
                    model_sha256=entry["model_sha256"],
                    arm=arm,
                    model=name,
                )
                folder = directory / "visuals/chips" / chip["chip_id"] / arm / name
                for layer, values in (("probability", p), ("binary", binary), ("error", error)):
                    entry["layers"][layer] = render_preview(
                        values, layer, folder / f"{layer}.png", meta, public
                    )
                entry["status"] = "available"
                if number % 10 == 0 or number == len(pending):
                    write_json(index_path, index)
                    print(f"{arm}/{name}: {number}/{len(pending)} chip previews", flush=True)
            verify(source, model_metadata["checkpoint"])
            del model
            gc.collect()
            if name == "unet":
                import torch

                torch.cuda.empty_cache()
    index["status"] = "complete"
    index["generated_utc"] = datetime.now(UTC).isoformat()
    index["coverage"] = {
        "n_test_chips": len(index["chips"]),
        "n_available_model_cases": sum(
            entry["status"] == "available"
            for chip in index["chips"]
            for arm in chip["models"].values()
            for entry in arm.values()
        ),
        "n_unavailable_model_cases": sum(
            entry["status"] == "unavailable"
            for chip in index["chips"]
            for arm in chip["models"].values()
            for entry in arm.values()
        ),
    }
    index["exporter"] = receipt(Path(__file__).resolve(), destination)
    write_json(index_path, index)
    return index_path


def export_mae_sai(source: Path, directory: Path, public: Path, index: dict) -> None:
    """Render all six saved inference rasters; no Thai reference or model rerun."""
    import rasterio

    work = source / "outputs/geoai/work/public-training"
    pair_path = source / "services/geoai-runner/evidence/mae_sai_rtc_pair.json"
    pair = read_json(pair_path)
    meta = envelope(
        pair["source_timestamp"],
        index["metadata"]["license"],
        dataset="Mae Sai inference; no reference labels",
        assumptions=ASSUMPTIONS
        + [
            "The 15 September acquisition is roughly four days after the 11 September "
            "peak and shows residual extent.",
            "C2S-MS GRD models transfer to RTC gamma0; Mae Sai accuracy is unavailable.",
        ],
    )
    entry = {
        "grid": pair["grid"],
        "extent": extent(pair["grid"]),
        "sources": {},
        "models": {arm: {} for arm in ARMS},
        "metadata": meta,
        "source_timestamp": pair["source_timestamp"],
        "source_pair": receipt(pair_path, source),
        "accuracy_status": "unavailable_no_qualified_Thai_reference",
    }
    for key in ("pre_vh", "post_vh"):
        with rasterio.open(verify(source, pair["files"][key])) as raster:
            values = raster.read(1, masked=True).filled(np.nan)
            values[values <= 0] = np.nan
            values = 10 * np.log10(values)
        entry["sources"][key] = render_preview(
            values,
            "radar",
            directory / f"visuals/mae-sai/{key}.png",
            {**meta, "source": pair["files"][key]},
            public,
        )
    for arm in ARMS:
        for name in MODELS:
            manifest_path = work / f"mae-sai/inference/{arm}/{name}/manifest.json"
            manifest = read_json(manifest_path)
            if (
                manifest["metrics"] is not None
                or manifest["can_feed_decision_layer"] is not False
                or manifest["grid"] != pair["grid"]
            ):
                raise ValueError("Mae Sai inference provenance must remain report-only")
            checkpoint = manifest["model_metadata"]["checkpoint"]
            verify(source, checkpoint)
            with rasterio.open(verify(source, manifest["layers"])) as raster:
                layers = raster.read()
            model = {
                "status": "available",
                "layers": {},
                "model_sha256": checkpoint["sha256"],
                "checkpoint": checkpoint,
                "source_timestamp": manifest["source_timestamp"],
                "support": {
                    "n_valid_pixels": manifest["valid_pixels"],
                    "n_accepted_pixels": manifest["accepted_pixels"],
                    "n_reference_positive": None,
                },
                "source_manifest": receipt(manifest_path, source),
                "source_raster": manifest["layers"],
                "context_screening": manifest["context_screening"],
                "metrics": None,
                "evidence_tier": "candidate",
                "can_feed_decision_layer": False,
                "aggregation_status": "report_only",
            }
            for band, layer in enumerate(("probability", "validity", "entropy", "abstention")):
                model["layers"][layer] = render_preview(
                    layers[band],
                    layer,
                    directory / f"visuals/mae-sai/{arm}/{name}/{layer}.png",
                    {**meta, "model_sha256": checkpoint["sha256"], "source": manifest["layers"]},
                    public,
                )
            entry["models"][arm][name] = model
    index["mae_sai"] = entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--device", choices=("cuda", "cpu", "auto"), default="cuda")
    args = parser.parse_args()
    print(export(args.source_root, args.output_root, device=args.device))


if __name__ == "__main__":
    main()
