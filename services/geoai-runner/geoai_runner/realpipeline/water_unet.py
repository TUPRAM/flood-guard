"""Component B -- Water-mask refinement (semantic segmentation, U-Net).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 9 "Semantic Segmentation",
Sec. 9.6 "Surface Water Mapping". The book trains a U-Net with a ResNet
encoder to map surface water and reports IoU ~0.71 / F1 ~0.80 on a global
2,841-pair waterbody dataset.

This module runs the *exact* ``geoai`` training and inference pipeline
(``geoai.train_segmentation_model`` + ``geoai.semantic_segmentation``) on the
synthetic Sentinel-2 stack. Because there is no network access to fetch
ImageNet weights, the encoder is initialised randomly (``encoder_weights=None``)
and trained from scratch on a handful of tiles -- enough to prove the
architecture executes end to end and produces a georeferenced, vectorisable
water mask with a per-pixel confidence (softmax) layer. On real hardware with
internet, set ``encoder_weights="imagenet"`` and point the loaders at real
Sentinel-2 tiles; nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline import DATA_MODE_SYNTHETIC, SYNTHETIC_ASSUMPTION
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff


@dataclass
class WaterSegmentationResult:
    """Outputs of the U-Net water-segmentation component."""

    water_mask: np.ndarray
    confidence: np.ndarray
    metrics: dict[str, float]
    model_path: Path | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)


def prepare_training_tiles(
    image_path: str | Path,
    mask_path: str | Path,
    out_dir: str | Path,
    *,
    tile_size: int = 64,
    stride: int = 24,
) -> tuple[Path, Path, int]:
    """Slice an image raster and its label mask into paired training tiles.

    Returns (images_dir, labels_dir, n_tiles). Each tile keeps its own
    georeferencing so the loaders read real GeoTIFFs, matching the book.
    """

    from affine import Affine

    out_dir = Path(out_dir)
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    image, transform, crs = read_geotiff(image_path)
    mask, _, _ = read_geotiff(mask_path)
    mask = mask[0]
    _, height, width = image.shape

    n = 0
    for row in range(0, height - tile_size + 1, stride):
        for col in range(0, width - tile_size + 1, stride):
            img_tile = image[:, row : row + tile_size, col : col + tile_size]
            mask_tile = mask[row : row + tile_size, col : col + tile_size]
            tile_transform = transform * Affine.translation(col, row)
            write_geotiff(
                images_dir / f"tile_{n:03d}.tif", img_tile, tile_transform, crs
            )
            write_geotiff(
                labels_dir / f"tile_{n:03d}.tif",
                mask_tile.astype("uint8"),
                tile_transform,
                crs,
                dtype="uint8",
            )
            n += 1
    return images_dir, labels_dir, n


def train_water_unet(
    images_dir: str | Path,
    labels_dir: str | Path,
    output_dir: str | Path,
    *,
    num_channels: int = 6,
    encoder_name: str = "resnet18",
    encoder_weights: str | None = None,
    num_epochs: int = 45,
    batch_size: int = 8,
    learning_rate: float = 0.003,
    target_size: tuple[int, int] = (64, 64),
    val_split: float = 0.2,
    class_weights: tuple[float, float] | None = (1.0, 8.0),
) -> Path:
    """Train a U-Net water segmentation model with ``geoai`` (real training).

    ``class_weights`` upweights the minority water class so the model does not
    collapse to all-background under the ~6% water prior (a real segmentation
    concern the book raises implicitly via IoU/recall). Returns the path to
    ``best_model.pth``.
    """

    import geoai

    output_dir = Path(output_dir)
    geoai.train_segmentation_model(
        images_dir=str(images_dir),
        labels_dir=str(labels_dir),
        output_dir=str(output_dir),
        architecture="unet",
        encoder_name=encoder_name,
        encoder_weights=encoder_weights,
        num_channels=num_channels,
        num_classes=2,
        batch_size=batch_size,
        num_epochs=num_epochs,
        learning_rate=learning_rate,
        val_split=val_split,
        target_size=target_size,
        class_weights=list(class_weights) if class_weights is not None else None,
        verbose=False,
    )
    return output_dir / "best_model.pth"


def infer_water_mask(
    model_path: str | Path,
    image_path: str | Path,
    output_dir: str | Path,
    *,
    num_channels: int = 6,
    encoder_name: str = "resnet18",
    window_size: int = 64,
    overlap: int = 16,
    reference_mask_path: str | Path | None = None,
    data_mode: str = DATA_MODE_SYNTHETIC,
    source_timestamp: str = "2024-09-16T05:00:00Z",
) -> WaterSegmentationResult:
    """Run sliding-window inference and write ``water_mask_refined.tif``."""

    import geoai

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mask_path = output_dir / "water_mask_refined.tif"
    prob_path = output_dir / "water_mask_probability.tif"

    geoai.semantic_segmentation(
        input_path=str(image_path),
        output_path=str(mask_path),
        model_path=str(model_path),
        architecture="unet",
        encoder_name=encoder_name,
        num_channels=num_channels,
        num_classes=2,
        window_size=window_size,
        overlap=overlap,
        batch_size=4,
        probability_path=str(prob_path),
    )

    mask, transform, crs = read_geotiff(mask_path)
    mask = (mask[0] > 0).astype("uint8")
    try:
        prob, _, _ = read_geotiff(prob_path)
        confidence = prob[-1].astype("float32")  # water-class probability band
    except Exception:  # pragma: no cover - probability optional
        confidence = mask.astype("float32")

    metrics: dict[str, float] = {}
    if reference_mask_path is not None:
        ref, _, _ = read_geotiff(reference_mask_path)
        metrics = _mask_metrics(mask, ref[0].astype("uint8"))

    _vectorize(mask, transform, crs, output_dir / "water_bodies.geojson")

    metrics["data_mode"] = data_mode
    metrics["source_timestamp"] = source_timestamp
    metrics["assumptions"] = (
        SYNTHETIC_ASSUMPTION if data_mode == DATA_MODE_SYNTHETIC else
        "Real Sentinel-2 U-Net water mask; non-operational preparedness product."
    )
    return WaterSegmentationResult(
        water_mask=mask,
        confidence=confidence,
        metrics=metrics,
        model_path=Path(model_path),
        artifacts={
            "water_mask": mask_path,
            "water_probability": prob_path,
            "water_vector": output_dir / "water_bodies.geojson",
        },
    )


def _mask_metrics(predicted: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    p = predicted.astype(bool).ravel()
    r = reference.astype(bool).ravel()
    tp = int(np.sum(p & r))
    fp = int(np.sum(p & ~r))
    fn = int(np.sum(~p & r))

    def ratio(num: float, den: float) -> float:
        return round(num / den, 4) if den else 0.0

    return {
        "iou": ratio(tp, tp + fp + fn),
        "f1_dice": ratio(2 * tp, 2 * tp + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
    }


def _vectorize(binary: np.ndarray, transform, crs: str, out_path: Path) -> Path:
    import json

    from rasterio.features import shapes

    feats = []
    for geom, value in shapes(
        binary.astype("int32"), mask=binary.astype(bool), transform=transform
    ):
        if value == 1:
            feats.append(
                {"type": "Feature", "properties": {"class": "water"}, "geometry": geom}
            )
    out_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "water_bodies",
                "crs": {"type": "name", "properties": {"name": crs}},
                "features": feats,
            }
        ),
        encoding="utf-8",
    )
    return out_path
