"""Raster-grid, probability, mask, and metric validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from numpy.typing import NDArray

from .contract import GeoAIRunContract


class RasterValidationError(ValueError):
    """Raised when a raster violates the frozen feature/output contract."""


@dataclass(frozen=True, slots=True)
class RasterGrid:
    crs: str
    transform: tuple[float, ...]
    width: int
    height: int
    bounds: tuple[float, float, float, float]
    count: int
    dtypes: tuple[str, ...]
    descriptions: tuple[str | None, ...]
    nodata: float | int | None


def read_grid(path: Path) -> RasterGrid:
    with rasterio.open(path) as source:
        if source.crs is None:
            raise RasterValidationError(f"{path.name} has no CRS.")
        return RasterGrid(
            crs=source.crs.to_string(),
            transform=tuple(source.transform),
            width=source.width,
            height=source.height,
            bounds=tuple(source.bounds),
            count=source.count,
            dtypes=tuple(source.dtypes),
            descriptions=tuple(source.descriptions),
            nodata=source.nodata,
        )


def validate_aligned_feature_and_mask(feature_path: Path, mask_path: Path) -> RasterGrid:
    """Hard-reject any grid mismatch before GeoAI's permissive tile exporter."""

    feature = read_grid(feature_path)
    mask = read_grid(mask_path)
    comparable = ("crs", "transform", "width", "height", "bounds")
    mismatches = [name for name in comparable if getattr(feature, name) != getattr(mask, name)]
    if mismatches:
        raise RasterValidationError("Feature/mask grids differ: " + ", ".join(mismatches))
    if not 6 <= feature.count <= 8 or set(feature.dtypes) != {"uint8"}:
        raise RasterValidationError("Feature raster must contain 6-8 uint8 bands.")
    missing_description = any(
        description is None or not description.strip() for description in feature.descriptions
    )
    if missing_description:
        raise RasterValidationError(
            "Feature raster requires an explicit description for every band."
        )
    if feature.nodata is not None:
        raise RasterValidationError(
            "Encoded feature raster must use a fully valid common footprint (nodata=None)."
        )
    if mask.count != 1 or mask.dtypes != ("uint8",) or mask.nodata != 255:
        raise RasterValidationError("Reference mask must be one uint8 band with nodata=255.")
    with rasterio.open(mask_path) as source:
        values = source.read(1)
    classes = set(np.unique(values).tolist())
    if not classes.issubset({0, 1, 255}) or not {0, 1}.issubset(classes):
        raise RasterValidationError(
            "Reference mask must contain both class 0 and class 1, with optional nodata 255."
        )
    return feature


def validate_grid_matches_contract(
    grid: RasterGrid,
    contract: GeoAIRunContract,
) -> None:
    """Verify encoded grid, channel order, resolution, and bounds against the run."""

    if grid.crs.upper() != contract.target_crs.upper():
        raise RasterValidationError("Feature CRS does not match the run contract.")
    resolution = (abs(float(grid.transform[0])), abs(float(grid.transform[4])))
    if not np.allclose(resolution, contract.resolution, rtol=0.0, atol=1e-9):
        raise RasterValidationError("Feature resolution does not match the run contract.")
    if not np.allclose(grid.bounds, contract.bounds, rtol=0.0, atol=1e-7):
        raise RasterValidationError("Feature bounds do not match the run contract.")
    if grid.count != contract.channel_count:
        raise RasterValidationError("Feature channel count does not match the run contract.")
    if tuple(grid.descriptions) != contract.preprocessing.channel_names:
        raise RasterValidationError("Feature channel order does not match the run contract.")


def validate_probability_raster(
    probability_path: Path,
    expected_grid: RasterGrid,
    *,
    expected_tags: Mapping[str, str],
) -> RasterGrid:
    grid = read_grid(probability_path)
    for name in ("crs", "transform", "width", "height", "bounds"):
        if getattr(grid, name) != getattr(expected_grid, name):
            raise RasterValidationError(
                f"Probability raster {name} does not match the feature grid."
            )
    if grid.count != 1 or grid.dtypes != ("float32",) or grid.nodata != -9999.0:
        raise RasterValidationError(
            "Probability output must be one float32 band with nodata=-9999."
        )
    if grid.descriptions != ("flood_probability_0_1",):
        raise RasterValidationError("Probability output band must be named flood_probability_0_1.")
    with rasterio.open(probability_path) as source:
        values = source.read(1)
        tags = source.tags()
    unexpected_tags = set(tags) - set(expected_tags) - {"AREA_OR_POINT"}
    tags_match = all(tags.get(name) == value for name, value in expected_tags.items())
    if unexpected_tags or not tags_match:
        raise RasterValidationError(
            "Probability output provenance tags do not match the run contract."
        )
    valid = values != -9999.0
    if not valid.any() or not np.isfinite(values[valid]).all():
        raise RasterValidationError("Probability output has no finite valid pixels.")
    if values[valid].min() < 0 or values[valid].max() > 1:
        raise RasterValidationError("Class-1 probability values must be in [0,1].")
    return grid


def compute_validation_metrics(
    probabilities: NDArray[np.floating],
    reference: NDArray[np.integer],
    *,
    threshold: float,
    calibration_bins: int = 10,
) -> dict[str, float]:
    """Compute required binary segmentation, area, Brier, and calibration metrics."""

    probability_array = np.asarray(probabilities, dtype=np.float64)
    truth_array = np.asarray(reference)
    if probability_array.shape != truth_array.shape:
        raise RasterValidationError("Probability and reference shapes differ.")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int | float)
        or not np.isfinite(threshold)
        or threshold < 0
        or threshold > 1
        or type(calibration_bins) is not int
        or calibration_bins <= 0
    ):
        raise RasterValidationError("Threshold and calibration_bins are invalid.")
    probability = probability_array.reshape(-1)
    truth = truth_array.reshape(-1)
    valid = truth != 255
    probability, truth = probability[valid], truth[valid]
    invalid_probability = (
        probability.size == 0
        or not np.isfinite(probability).all()
        or probability.min() < 0
        or probability.max() > 1
    )
    if invalid_probability:
        raise RasterValidationError("Metrics require finite probabilities in [0,1].")
    if not set(np.unique(truth)).issubset({0, 1}):
        raise RasterValidationError("Reference values must be binary after nodata removal.")
    prediction = probability >= threshold
    positive = truth == 1
    tp = int(np.logical_and(prediction, positive).sum())
    fp = int(np.logical_and(prediction, ~positive).sum())
    fn = int(np.logical_and(~prediction, positive).sum())
    intersection_denominator = tp + fp + fn
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    iou = tp / intersection_denominator if intersection_denominator else 1.0
    precision = tp / precision_denominator if precision_denominator else 0.0
    recall = tp / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    area_error = abs(int(prediction.sum()) - int(positive.sum())) / max(
        int(positive.sum()),
        1,
    )
    brier = float(np.mean((probability - truth) ** 2))
    ece = _expected_calibration_error(probability, truth, calibration_bins)
    return {
        "iou": round(iou, 6),
        "f1_dice": round(f1, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "area_error_ratio": round(area_error, 6),
        "brier_score": round(brier, 6),
        "expected_calibration_error": round(ece, 6),
    }


def categorize_errors(
    prediction: NDArray[np.bool_],
    reference: NDArray[np.integer],
    *,
    permanent_water: NDArray[np.bool_] | None = None,
    steep_terrain: NDArray[np.bool_] | None = None,
) -> dict[str, int]:
    """Count auditable false-positive/negative review categories."""

    pred = np.asarray(prediction, dtype=bool)
    truth = np.asarray(reference)
    if pred.shape != truth.shape:
        raise RasterValidationError("Prediction and reference shapes differ.")
    false_positive = pred & (truth == 0)
    false_negative = ~pred & (truth == 1)
    categories = {
        "false_positive_total": int(false_positive.sum()),
        "false_negative_total": int(false_negative.sum()),
    }
    if permanent_water is not None:
        if np.asarray(permanent_water).shape != pred.shape:
            raise RasterValidationError("Permanent-water mask shape differs.")
        categories["false_positive_permanent_water"] = int((false_positive & permanent_water).sum())
    if steep_terrain is not None:
        if np.asarray(steep_terrain).shape != pred.shape:
            raise RasterValidationError("Steep-terrain mask shape differs.")
        categories["false_positive_steep_terrain"] = int((false_positive & steep_terrain).sum())
    return categories


def _expected_calibration_error(
    probability: NDArray[np.float64],
    truth: NDArray[np.generic],
    bins: int,
) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = probability.size
    error = 0.0
    for index in range(bins):
        upper_inclusive = index == bins - 1
        upper_members = (
            probability <= edges[index + 1] if upper_inclusive else probability < edges[index + 1]
        )
        members = (probability >= edges[index]) & upper_members
        if members.any():
            error += (
                members.sum()
                / total
                * abs(float(probability[members].mean()) - float(truth[members].mean()))
            )
    return float(error)
