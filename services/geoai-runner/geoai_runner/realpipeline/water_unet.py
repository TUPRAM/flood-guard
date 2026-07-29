"""Component B -- Water-mask refinement (semantic segmentation, U-Net).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 9 "Semantic Segmentation",
Sec. 9.6 "Surface Water Mapping". The book trains a U-Net with a ResNet encoder
to map surface water and reports IoU ~0.71 / F1 ~0.80 on a global 2,841-pair
waterbody dataset.

What changed and why
--------------------
The previous version of this module tiled the whole scene with overlapping
windows, let ``geoai.train_segmentation_model`` take a *random* 20% validation
split out of those overlapping tiles, then inferred over the same full raster
and scored against the same label mask it had trained on. The published
IoU 0.38 was therefore a training-set number with three stacked leaks, on a
target (``MNDWI > 0``) that is a closed-form function of two of the model's own
input channels. A score that low on a task that easy is a symptom of broken
optimisation, not a hard problem -- but the leaks made it impossible to tell.

This module now:

* fits every preprocessing statistic on the **training role only**, which is
  leakage control #6 in ``docs/immutable-multi-event-partitions-v1.md``;
* trains on tiles lying wholly inside training blocks;
* reports metrics separately for train / val / test, so an optimisation failure
  (all three low) is distinguishable from a generalisation failure (train high,
  test low) -- the D0 diagnostic;
* selects its operating threshold on the **validation** role and reports the
  result on **test**, never the reverse.

The headline number is the test-role score. The train-role score is retained
deliberately: the gap between them is the diagnostic, and hiding it would throw
away the only evidence that distinguishes the two failure modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline import DATA_MODE_SYNTHETIC, SYNTHETIC_ASSUMPTION
from geoai_runner.realpipeline.blocks import ROLE_CODES, BlockAssignment, tiles_for_role
from geoai_runner.realpipeline.metrics import (
    DEFAULT_MIN_POSITIVE,
    binary_mask_metrics,
    sweep_threshold,
)
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff


class WaterUnetError(RuntimeError):
    """Raised when a training or evaluation configuration is unsafe."""


# --------------------------------------------------------------------------- #
# Preprocessing statistics -- fitted on the training role only
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChannelStats:
    """Per-channel standardisation statistics and the role they were fitted on."""

    mean: tuple[float, ...]
    std: tuple[float, ...]
    fitted_on_role: str
    n_pixels: int

    def to_dict(self) -> dict[str, object]:
        """Return manifest-friendly fields."""

        return {
            "mean": [round(v, 6) for v in self.mean],
            "std": [round(v, 6) for v in self.std],
            "fitted_on_role": self.fitted_on_role,
            "n_pixels": self.n_pixels,
        }


def fit_channel_stats(
    image_path: str | Path,
    assignment: BlockAssignment,
    *,
    role: str = "train",
    min_std: float = 1e-4,
) -> ChannelStats:
    """Fit per-channel mean/std over one partition role.

    Sentinel-2 L2A reflectance arrives as ``clip(DN / 10000, 0, 1)``, so SWIR over
    bright land sits near 0.3-0.4 and water near 0.01-0.05. An ImageNet-pretrained
    ResNet encoder expects roughly unit-variance input; feeding it six channels of
    near-zero-variance reflectance is a well-known way to get a network that never
    moves far off its initialisation. This is the D1 fix, and the primary suspect
    for Component B's under-segmentation.

    Fitting on ``role="train"`` is mandatory, not stylistic: statistics fitted
    across the whole scene would leak held-out distribution into training, which
    is exactly the preprocessing-chronology failure the partition contract names.
    """

    if role != "train":
        raise WaterUnetError(
            f"preprocessing must be fitted on the training role; got {role!r}. "
            "Fitting on val/test leaks held-out distribution into the model."
        )
    stack, _, _ = read_geotiff(image_path)
    stack = np.asarray(stack, dtype="float64")
    mask = assignment.mask(role)
    if mask.shape != stack.shape[1:]:
        raise WaterUnetError(
            f"assignment grid {mask.shape} does not match raster {stack.shape[1:]}."
        )
    # Exclude mosaic gaps: a pixel with no reflectance in any band was never observed.
    observed = np.any(stack > 0.0, axis=0)
    selector = mask & observed
    if not selector.any():
        raise WaterUnetError(f"role {role!r} contains no observed pixels to fit statistics on.")

    means: list[float] = []
    stds: list[float] = []
    for band in range(stack.shape[0]):
        values = stack[band][selector]
        means.append(float(values.mean()))
        stds.append(float(max(values.std(), min_std)))
    return ChannelStats(
        mean=tuple(means),
        std=tuple(stds),
        fitted_on_role=role,
        n_pixels=int(selector.sum()),
    )


def write_standardised_raster(
    image_path: str | Path,
    stats: ChannelStats,
    out_path: str | Path,
) -> Path:
    """Standardise every band and write a new raster.

    Training tiles and inference input are both cut from this same file, so there
    is no train/serve skew: whatever transform the model learned on is exactly
    the transform applied at inference.
    """

    stack, transform, crs = read_geotiff(image_path)
    stack = np.asarray(stack, dtype="float32")
    if stack.shape[0] != len(stats.mean):
        raise WaterUnetError(
            f"raster has {stack.shape[0]} bands but stats describe {len(stats.mean)}."
        )
    mean = np.asarray(stats.mean, dtype="float32")[:, None, None]
    std = np.asarray(stats.std, dtype="float32")[:, None, None]
    return write_geotiff(out_path, (stack - mean) / std, transform, crs, dtype="float32")


def inverse_frequency_class_weights(
    mask_path: str | Path,
    assignment: BlockAssignment,
    *,
    role: str = "train",
    cap: float = 30.0,
) -> tuple[float, float]:
    """Return ``(background, water)`` weights from the training-role prior.

    The previous hard-coded ``(1.0, 25.0)`` was guesswork against a ~6% water
    prior whose natural inverse-frequency weight is closer to 15. Computing it
    from the training role removes the guess and makes the value auditable.
    """

    mask, _, _ = read_geotiff(mask_path)
    labels = mask[0].astype(bool)[assignment.mask(role)]
    if labels.size == 0:
        raise WaterUnetError(f"role {role!r} contains no labelled pixels.")
    positive_rate = float(labels.mean())
    if positive_rate <= 0.0 or positive_rate >= 1.0:
        return (1.0, 1.0)
    return (1.0, float(min(cap, (1.0 - positive_rate) / positive_rate)))


# --------------------------------------------------------------------------- #
# Role-scoped tiling
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TilePartition:
    """Per-role tile directories cut from spatially disjoint blocks."""

    directories: dict[str, tuple[Path, Path]]
    counts: dict[str, int]
    tile_size: int
    stride: int
    assignment_sha256: str
    channel_stats: ChannelStats | None = None

    @property
    def train(self) -> tuple[Path, Path]:
        """Return ``(images_dir, labels_dir)`` for the training role."""

        return self.directories["train"]

    def to_dict(self) -> dict[str, object]:
        """Return manifest-friendly fields."""

        payload: dict[str, object] = {
            "tile_size": self.tile_size,
            "stride": self.stride,
            "tiles_by_role": dict(self.counts),
            "assignment_sha256": self.assignment_sha256,
        }
        if self.channel_stats is not None:
            payload["channel_standardisation"] = self.channel_stats.to_dict()
        return payload


def prepare_role_tiles(
    image_path: str | Path,
    mask_path: str | Path,
    out_dir: str | Path,
    assignment: BlockAssignment,
    *,
    tile_size: int = 128,
    stride: int = 32,
    roles: tuple[str, ...] = ("train", "val", "test"),
    channel_stats: ChannelStats | None = None,
    min_train_tiles: int = 16,
) -> TilePartition:
    """Cut tiles that lie wholly inside each role's blocks.

    Whole-tile containment (enforced in :func:`blocks.tiles_for_role`) is what
    guarantees a training tile never contains a held-out label, independent of
    how wide the buffer is.
    """

    from affine import Affine

    out_dir = Path(out_dir)
    image, transform, crs = read_geotiff(image_path)
    mask, _, _ = read_geotiff(mask_path)
    mask = mask[0]
    if mask.shape != assignment.role_grid.shape:
        raise WaterUnetError(
            f"assignment grid {assignment.role_grid.shape} does not match label {mask.shape}."
        )

    directories: dict[str, tuple[Path, Path]] = {}
    counts: dict[str, int] = {}
    for role in roles:
        images_dir = out_dir / role / "images"
        labels_dir = out_dir / role / "labels"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        origins = tiles_for_role(assignment, role, tile_size=tile_size, stride=stride)
        for index, (row, col) in enumerate(origins):
            tile_transform = transform * Affine.translation(col, row)
            write_geotiff(
                images_dir / f"tile_{index:04d}.tif",
                image[:, row : row + tile_size, col : col + tile_size],
                tile_transform,
                crs,
            )
            write_geotiff(
                labels_dir / f"tile_{index:04d}.tif",
                mask[row : row + tile_size, col : col + tile_size].astype("uint8"),
                tile_transform,
                crs,
                dtype="uint8",
            )
        directories[role] = (images_dir, labels_dir)
        counts[role] = len(origins)

    if counts.get("train", 0) < min_train_tiles:
        raise WaterUnetError(
            f"training role yielded only {counts.get('train', 0)} tiles (minimum "
            f"{min_train_tiles}). The block geometry, tile size or stride cannot "
            "support training; fix the geometry rather than relaxing the partition."
        )
    return TilePartition(
        directories=directories,
        counts=counts,
        tile_size=tile_size,
        stride=stride,
        assignment_sha256=assignment.assignment_sha256,
        channel_stats=channel_stats,
    )


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def train_water_unet(
    partition: TilePartition,
    output_dir: str | Path,
    *,
    num_channels: int = 6,
    encoder_name: str = "resnet18",
    encoder_weights: str | None = "imagenet",
    num_epochs: int = 120,
    batch_size: int = 8,
    learning_rate: float = 3e-4,
    target_size: tuple[int, int] = (128, 128),
    class_weights: tuple[float, float] | None = None,
) -> Path:
    """Train a U-Net water-segmentation model on the training role only.

    ``geoai.train_segmentation_model`` accepts a single image/label directory
    pair plus a ``val_split`` float; it cannot be handed an explicit validation
    directory. Passing a deliberately tiny ``val_split`` therefore looks wrong
    but is correct here: that internal split is used *only* as a loss monitor for
    checkpoint selection, and every number this project publishes comes from
    :func:`evaluate_roles`, which scores spatially disjoint blocks that the model
    never saw. Giving geoai a larger split would just remove training data while
    producing a leaky score we would then have to ignore.

    Defaults reflect the D4 diagnostic: 30 epochs at ``lr=1e-3`` over ~100 tiles
    is roughly 375 optimiser steps, which badly undertrains a stem that must
    adapt from 3-channel ImageNet weights to 6-band reflectance.
    """

    import geoai

    images_dir, labels_dir = partition.train
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
        # Loss monitor only -- see the docstring. Not a reported metric.
        val_split=0.05,
        target_size=target_size,
        class_weights=list(class_weights) if class_weights is not None else None,
        verbose=False,
    )
    return output_dir / "best_model.pth"


# --------------------------------------------------------------------------- #
# Inference and role-scoped evaluation
# --------------------------------------------------------------------------- #
@dataclass
class WaterSegmentationResult:
    """Outputs of the U-Net water-segmentation component."""

    water_mask: np.ndarray
    confidence: np.ndarray
    metrics: dict[str, object]
    model_path: Path | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)


def infer_water_probability(
    model_path: str | Path,
    image_path: str | Path,
    output_dir: str | Path,
    *,
    num_channels: int = 6,
    encoder_name: str = "resnet18",
    window_size: int = 128,
    overlap: int = 32,
) -> tuple[np.ndarray, np.ndarray, object, str, dict[str, Path]]:
    """Run full-scene sliding-window inference.

    Inference deliberately covers the whole scene rather than only the evaluated
    role: a sliding window needs surrounding context to produce sensible edges.
    Role restriction is applied at *metric* time, in :func:`evaluate_roles`,
    which is where it actually matters.
    """

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
        probability = prob[-1].astype("float32")  # water-class probability band
    except Exception:  # pragma: no cover - probability optional
        probability = mask.astype("float32")
    return (
        mask,
        probability,
        transform,
        crs,
        {
            "water_mask": mask_path,
            "water_probability": prob_path,
        },
    )


def evaluate_roles(
    probability: np.ndarray,
    reference_mask: np.ndarray,
    assignment: BlockAssignment,
    *,
    threshold: float | None = None,
    min_positive: int | None = DEFAULT_MIN_POSITIVE,
    roles: tuple[str, ...] = ("train", "val", "test"),
) -> dict[str, object]:
    """Score each partition role, selecting the threshold on validation only.

    Returns ``metrics_by_role`` plus the threshold provenance. Retaining the
    train-role score is intentional: ``train ~= test ~= low`` means optimisation
    failed, whereas ``train high, test low`` means the model overfits. Publishing
    only the test number would discard the evidence that tells them apart.
    """

    for role in roles:
        if role not in ROLE_CODES:
            raise WaterUnetError(f"unknown role {role!r}.")

    selection: dict[str, object]
    if threshold is None:
        if "val" not in roles:
            raise WaterUnetError(
                "threshold selection requires the 'val' role; pass an explicit "
                "threshold or include 'val'."
            )
        selection = sweep_threshold(
            probability, reference_mask, mask=assignment.mask("val"), objective="f1_dice"
        )
        threshold = float(selection["selected_threshold"])
    else:
        selection = {
            "selected_threshold": float(threshold),
            "selected_on_role": "caller_supplied",
            "objective": None,
            "curve": [],
        }

    predicted = probability >= threshold
    metrics_by_role = {
        role: binary_mask_metrics(
            predicted,
            reference_mask,
            mask=assignment.mask(role),
            min_positive=min_positive,
            counts=True,
        )
        for role in roles
    }
    train_iou = metrics_by_role.get("train", {}).get("iou")
    test_iou = metrics_by_role.get("test", {}).get("iou")
    diagnosis = _diagnose(train_iou, test_iou)
    return {
        "metrics_by_role": metrics_by_role,
        "headline_role": "test",
        "threshold_selection": selection,
        "generalisation_diagnosis": diagnosis,
    }


def _diagnose(train_iou: object, test_iou: object) -> str:
    """Name the failure mode implied by the train/test gap (the D0 diagnostic)."""

    if not isinstance(train_iou, int | float) or not isinstance(test_iou, int | float):
        return "indeterminate_insufficient_support"
    if train_iou < 0.6 and test_iou < 0.6:
        return "optimisation_failure_train_and_test_both_low"
    if train_iou - test_iou > 0.25:
        return "overfitting_train_much_higher_than_test"
    if test_iou >= 0.85:
        return "target_reproduced_on_held_out_blocks"
    return "underfitting_or_task_limited"


def finalise_water_result(
    water_mask: np.ndarray,
    probability: np.ndarray,
    transform,
    crs: str,
    output_dir: str | Path,
    evaluation: dict[str, object],
    *,
    model_path: str | Path | None = None,
    artifacts: dict[str, Path] | None = None,
    data_mode: str = DATA_MODE_SYNTHETIC,
    source_timestamp: str = "2024-09-16T05:00:00Z",
) -> WaterSegmentationResult:
    """Vectorise the mask and assemble the component result with provenance."""

    output_dir = Path(output_dir)
    vector_path = _vectorize(water_mask, transform, crs, output_dir / "water_bodies.geojson")
    metrics: dict[str, object] = dict(evaluation)
    metrics["data_mode"] = data_mode
    metrics["source_timestamp"] = source_timestamp
    metrics["assumptions"] = (
        SYNTHETIC_ASSUMPTION
        if data_mode == DATA_MODE_SYNTHETIC
        else (
            "U-Net trained on real Sentinel-2 with labels derived from the real MNDWI "
            "water index (weak supervision from a physical index, not hand annotation). "
            "Metrics measure agreement with that index on spatially disjoint held-out "
            "blocks, not against a gold human mask. Non-operational; not an official warning."
        )
    )
    merged = dict(artifacts or {})
    merged["water_vector"] = vector_path
    return WaterSegmentationResult(
        water_mask=water_mask,
        confidence=probability,
        metrics=metrics,
        model_path=Path(model_path) if model_path is not None else None,
        artifacts=merged,
    )


def _vectorize(binary: np.ndarray, transform, crs: str, out_path: Path) -> Path:
    import json

    from rasterio.features import shapes

    feats = []
    for geom, value in shapes(
        binary.astype("int32"), mask=binary.astype(bool), transform=transform
    ):
        if value == 1:
            feats.append({"type": "Feature", "properties": {"class": "water"}, "geometry": geom})
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
