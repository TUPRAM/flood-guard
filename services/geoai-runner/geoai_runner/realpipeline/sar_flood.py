"""Component A -- SAR flood-extent detection (traditional change detection).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 12 "Change Detection", the
traditional image-differencing / change-vector methods (Sec. 12.3-12.4). The
book names flood mapping as the textbook case for *traditional* change
detection because floodwater "rises and recedes" and the method needs no
training labels.

The core operation: take a pre-event and a post-event Sentinel-1 pair (VV+VH,
linear amplitude), convert to decibels, measure the backscatter *drop*
(open water is specular and appears dark in SAR), threshold it into a flood
probability, and vectorize. A permanent-water / HAND mask suppresses the urban
double-bounce and permanent-water false positives the book warns about
(Sec. 12.3.2).

Every function accepts GeoTIFF paths, so the same code runs on the synthetic
demo scene or on real licensed Sentinel-1 GRD products.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline import DATA_MODE_SYNTHETIC, SYNTHETIC_ASSUMPTION
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff


@dataclass
class SARFloodResult:
    """Outputs of the SAR change-detection component."""

    flood_binary: np.ndarray
    flood_probability: np.ndarray
    combined_drop_db: np.ndarray
    metrics: dict[str, float]
    artifacts: dict[str, Path] = field(default_factory=dict)


def _to_db(amplitude: np.ndarray) -> np.ndarray:
    amp = np.asarray(amplitude, dtype="float64")
    amp = np.where(amp > 0, amp, np.nan)
    return 10.0 * np.log10(amp)


def detect_sar_flood_extent(
    pre_vv_path: str | Path,
    pre_vh_path: str | Path,
    post_vv_path: str | Path,
    post_vh_path: str | Path,
    output_dir: str | Path,
    *,
    permanent_water_path: str | Path | None = None,
    reference_flood_path: str | Path | None = None,
    dry_change_db: float = 1.0,
    flood_change_db: float = 5.0,
    probability_threshold: float = 0.5,
    vh_weight: float = 0.6,
    speckle_window: int = 3,
    data_mode: str = DATA_MODE_SYNTHETIC,
    source_timestamp: str = "2024-09-15T23:16:01Z",
) -> SARFloodResult:
    """Detect flood extent from a Sentinel-1 pre/post pair via change detection.

    Args:
        pre_vv_path/pre_vh_path: Pre-event VV/VH linear amplitude GeoTIFFs.
        post_vv_path/post_vh_path: Post-event VV/VH GeoTIFFs.
        output_dir: Where ``flood_extent_binary.tif`` etc. are written.
        permanent_water_path: Optional mask (1 = permanent water) removed from
            the detected flood so only *new* inundation remains.
        reference_flood_path: Optional ground-truth mask for validation metrics.
        dry_change_db/flood_change_db: dB-drop values mapped to probability 0/1.
        probability_threshold: Threshold on flood probability for the binary map.
        vh_weight: Weight on the VH drop (VH is more water-sensitive) vs VV.

    Returns:
        A :class:`SARFloodResult` with arrays, metrics, and written artifacts.
    """

    if flood_change_db <= dry_change_db:
        raise ValueError("flood_change_db must exceed dry_change_db.")
    output_dir = Path(output_dir)

    pre_vv, transform, crs = read_geotiff(pre_vv_path)
    pre_vh, _, _ = read_geotiff(pre_vh_path)
    post_vv, _, _ = read_geotiff(post_vv_path)
    post_vh, _, _ = read_geotiff(post_vh_path)
    pre_vv, pre_vh = pre_vv[0], pre_vh[0]
    post_vv, post_vh = post_vv[0], post_vh[0]

    # Multi-look speckle reduction (boxcar mean) before differencing -- SAR is
    # dominated by multiplicative speckle, so raw pixel differences are noisy.
    pre_vv = _boxcar(pre_vv, speckle_window)
    pre_vh = _boxcar(pre_vh, speckle_window)
    post_vv = _boxcar(post_vv, speckle_window)
    post_vh = _boxcar(post_vh, speckle_window)

    vv_drop = _to_db(pre_vv) - _to_db(post_vv)
    vh_drop = _to_db(pre_vh) - _to_db(post_vh)
    combined = vh_weight * vh_drop + (1.0 - vh_weight) * vv_drop

    probability = np.clip((combined - dry_change_db) / (flood_change_db - dry_change_db), 0.0, 1.0)
    probability = np.where(np.isfinite(probability), probability, 0.0)
    binary = (probability >= probability_threshold).astype("uint8")

    # Suppress permanent water so the layer represents *new* flooding only.
    if permanent_water_path is not None:
        perm, _, _ = read_geotiff(permanent_water_path)
        perm = perm[0].astype(bool)
        binary[perm] = 0
        probability = np.where(perm, 0.0, probability)

    metrics: dict[str, float] = {}
    if reference_flood_path is not None:
        ref, _, _ = read_geotiff(reference_flood_path)
        ref = ref[0].astype("uint8")
        if permanent_water_path is not None:
            ref = ref.copy()
            ref[perm] = 0
        metrics = _mask_metrics(binary, ref)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "flood_binary": write_geotiff(
            output_dir / "flood_extent_binary.tif",
            binary,
            transform,
            crs,
            nodata=0,
            dtype="uint8",
        ),
        "flood_probability": write_geotiff(
            output_dir / "flood_extent_probability.tif",
            probability.astype("float32"),
            transform,
            crs,
        ),
        "combined_drop_db": write_geotiff(
            output_dir / "sar_combined_drop_db.tif",
            np.where(np.isfinite(combined), combined, 0.0).astype("float32"),
            transform,
            crs,
        ),
    }
    _vectorize_flood(binary, transform, crs, output_dir / "flood_extent.geojson")
    artifacts["flood_vector"] = output_dir / "flood_extent.geojson"

    result = SARFloodResult(
        flood_binary=binary,
        flood_probability=probability.astype("float32"),
        combined_drop_db=combined.astype("float32"),
        metrics=metrics,
        artifacts=artifacts,
    )
    result.metrics.setdefault("data_mode", data_mode)
    result.metrics["source_timestamp"] = source_timestamp
    result.metrics["assumptions"] = (
        SYNTHETIC_ASSUMPTION
        if data_mode == DATA_MODE_SYNTHETIC
        else "Real Sentinel-1 GRD pre/post change detection; non-operational preparedness product."
    )
    return result


def _boxcar(array: np.ndarray, window: int) -> np.ndarray:
    """Simple odd-window boxcar mean (speckle filter) without SciPy."""

    if window <= 1:
        return array.astype("float64")
    pad = window // 2
    a = np.pad(array.astype("float64"), pad, mode="edge")
    out = np.zeros_like(array, dtype="float64")
    for dy in range(window):
        for dx in range(window):
            out += a[dy : dy + array.shape[0], dx : dx + array.shape[1]]
    return out / (window * window)


def _mask_metrics(predicted: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    """IoU / F1 / precision / recall for two binary masks."""

    p = predicted.astype(bool).ravel()
    r = reference.astype(bool).ravel()
    tp = int(np.sum(p & r))
    fp = int(np.sum(p & ~r))
    fn = int(np.sum(~p & r))
    tn = int(np.sum(~p & ~r))

    def ratio(num: float, den: float) -> float:
        return round(num / den, 4) if den else 0.0

    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "iou": ratio(tp, tp + fp + fn),
        "f1_dice": ratio(2 * tp, 2 * tp + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
    }


def _vectorize_flood(binary: np.ndarray, transform, crs: str, out_path: Path) -> Path:
    """Vectorize the binary flood mask to a GeoJSON polygon layer."""

    import json

    from rasterio.features import shapes

    geoms = []
    for geom, value in shapes(
        binary.astype("int32"), mask=binary.astype(bool), transform=transform
    ):
        if value == 1:
            geoms.append({"type": "Feature", "properties": {"class": "flood"}, "geometry": geom})
    fc = {
        "type": "FeatureCollection",
        "name": "sar_flood_extent",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": geoms,
    }
    out_path.write_text(json.dumps(fc), encoding="utf-8")
    return out_path
