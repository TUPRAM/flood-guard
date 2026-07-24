"""Component C -- Flood susceptibility surface (pixel-level regression).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 13 "Pixel-Level Regression".
The book adapts an encoder-decoder (U-Net) to output a *continuous* value per
pixel instead of a class. FloodGuard's Component C predicts a continuous 0-100
flood-susceptibility value per pixel from terrain + hydrology features.

Two paths are provided:

1. :func:`compute_susceptibility_index` -- a transparent, physically-motivated
   weighted logistic combination of HAND, slope, distance-to-river and TWI.
   It needs no training, runs instantly, is fully interpretable, and is the
   default surface used by the demo. This is the honest "always available"
   product: a hydrological susceptibility index.

2. :func:`train_susceptibility_regressor` / :func:`predict_susceptibility` --
   the book's learned pixel-regression path via ``geoai.train_pixel_regressor``
   and ``geoai.predict_raster``, targeting a water-recurrence surface (the
   real project targets JRC Global Surface Water Recurrence, which needs no
   manual labels). Optional in the demo because CPU training is slow; provided
   so the learned upgrade is a data step, not a code rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline import DATA_MODE_SYNTHETIC, SYNTHETIC_ASSUMPTION
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff

# Physically-motivated weights: HAND dominates flood susceptibility (low ground
# near drainage floods first), then proximity to river, wetness, and flatness.
DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "hand": 0.45,
    "distance_to_river": 0.25,
    "twi": 0.20,
    "slope": 0.10,
}


@dataclass
class SusceptibilityResult:
    """Outputs of the flood-susceptibility component."""

    susceptibility_0_100: np.ndarray
    metrics: dict[str, float]
    artifacts: dict[str, Path] = field(default_factory=dict)


def _normalise(array: np.ndarray, invert: bool = False, clip_pct: float = 2.0) -> np.ndarray:
    """Percentile min-max normalise to [0, 1], optionally inverted."""

    a = np.asarray(array, dtype="float64")
    lo, hi = np.nanpercentile(a, clip_pct), np.nanpercentile(a, 100 - clip_pct)
    if hi <= lo:
        norm = np.zeros_like(a)
    else:
        norm = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
    return 1.0 - norm if invert else norm


def compute_susceptibility_index(
    hand_path: str | Path,
    slope_path: str | Path,
    dist_to_river_path: str | Path,
    twi_path: str | Path,
    output_dir: str | Path,
    *,
    weights: dict[str, float] | None = None,
    reference_flood_path: str | Path | None = None,
    data_mode: str = DATA_MODE_SYNTHETIC,
    source_timestamp: str = "2024-09-16T00:00:00Z",
) -> SusceptibilityResult:
    """Compute a 0-100 flood-susceptibility surface from terrain/hydrology."""

    weights = {**DEFAULT_FACTOR_WEIGHTS, **(weights or {})}
    output_dir = Path(output_dir)

    hand, transform, crs = read_geotiff(hand_path)
    slope, _, _ = read_geotiff(slope_path)
    dist, _, _ = read_geotiff(dist_to_river_path)
    twi, _, _ = read_geotiff(twi_path)

    # Low HAND, low slope, short distance-to-river, high TWI => more susceptible.
    # HAND and slope use *physical* scales (metres / degrees) rather than
    # percentile stretches: on real terrain a percentile stretch saturates
    # (everything looks "near a river") and destroys discrimination.
    hand_m = np.asarray(hand[0], dtype="float64")
    slope_deg = np.asarray(slope[0], dtype="float64")
    dist_m = np.asarray(dist[0], dtype="float64")
    factors = {
        # ~1 at HAND 0 m, ~0.5 at 8 m, ~0 above ~25 m.
        "hand": 1.0 / (1.0 + np.exp((hand_m - 8.0) / 3.5)),
        # ~1 within 100 m of a channel, decaying to ~0 by ~1.5 km.
        "distance_to_river": np.exp(-dist_m / 600.0),
        "twi": _normalise(twi[0], invert=False),
        # ~1 on flat ground, ~0 above ~12 degrees.
        "slope": 1.0 / (1.0 + np.exp((slope_deg - 5.0) / 2.0)),
    }
    total_weight = sum(weights[k] for k in factors)
    linear = sum(weights[k] * factors[k] for k in factors) / total_weight
    # Logistic sharpening centres the decision boundary and spreads the tails.
    susceptibility = 1.0 / (1.0 + np.exp(-(linear - 0.5) * 6.0))
    surface = (susceptibility * 100.0).astype("float32")

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "susceptibility": write_geotiff(
            output_dir / "flood_susceptibility.tif", surface, transform, crs
        )
    }

    metrics: dict[str, float] = {}
    if reference_flood_path is not None:
        ref, _, _ = read_geotiff(reference_flood_path)
        metrics = _rank_metrics(surface, ref[0].astype("uint8"))

    metrics["data_mode"] = data_mode
    metrics["source_timestamp"] = source_timestamp
    metrics["weights"] = weights
    metrics["assumptions"] = (
        SYNTHETIC_ASSUMPTION if data_mode == DATA_MODE_SYNTHETIC else
        "Hydrological susceptibility index from HAND/slope/distance/TWI; not flood depth."
    )
    return SusceptibilityResult(
        susceptibility_0_100=surface, metrics=metrics, artifacts=artifacts
    )


def _rank_metrics(surface: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    """AUC-style separability of the continuous surface vs the flood mask."""

    s = surface.astype("float64").ravel()
    r = reference.astype(bool).ravel()
    if r.sum() == 0 or (~r).sum() == 0:
        return {"auc": 0.0, "mean_susc_flood": 0.0, "mean_susc_dry": 0.0}
    # Mann-Whitney U -> AUC without SciPy.
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty_like(order, dtype="float64")
    ranks[order] = np.arange(1, len(s) + 1)
    pos_ranks = ranks[r].sum()
    n_pos, n_neg = int(r.sum()), int((~r).sum())
    auc = (pos_ranks - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return {
        "auc": round(float(auc), 4),
        "mean_susc_flood": round(float(s[r].mean()), 2),
        "mean_susc_dry": round(float(s[~r].mean()), 2),
    }


def make_recurrence_proxy(
    hand_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Create a 0-1 water-recurrence proxy target (stands in for JRC GSW).

    The real project regresses toward JRC Global Surface Water Recurrence, which
    requires no manual labels. Here we synthesise a physically-plausible
    recurrence surface from HAND so the regression pipeline has a continuous
    target to learn. Clearly a proxy, not a measurement.
    """

    hand, transform, crs = read_geotiff(hand_path)
    recurrence = 1.0 / (1.0 + np.exp((hand[0] - 5.0) / 1.4))
    return write_geotiff(output_path, recurrence.astype("float32"), transform, crs)


def train_susceptibility_regressor(
    feature_stack_path: str | Path,
    target_path: str | Path,
    output_dir: str | Path,
    *,
    encoder_name: str = "resnet18",
    num_epochs: int = 30,
    tile_size: int = 64,
    stride: int = 32,
):
    """Train the book's pixel regressor (``geoai.train_pixel_regressor``).

    Optional deep path. Returns the trained model object.
    """

    import geoai

    output_dir = Path(output_dir)
    image_paths, target_paths = geoai.create_regression_tiles(
        input_raster=str(feature_stack_path),
        target_raster=str(target_path),
        output_dir=str(output_dir / "reg_tiles"),
        tile_size=tile_size,
        stride=stride,
        target_band=1,
        min_valid_ratio=0.5,
        target_min=0.0,
        target_max=1.0,
    )
    split = max(1, int(len(image_paths) * 0.8))
    import rasterio

    with rasterio.open(str(feature_stack_path)) as src:
        in_channels = src.count
    return geoai.train_pixel_regressor(
        train_image_paths=image_paths[:split],
        train_target_paths=target_paths[:split],
        val_image_paths=image_paths[split:] or image_paths[:1],
        val_target_paths=target_paths[split:] or target_paths[:1],
        encoder_name=encoder_name,
        architecture="unet",
        in_channels=in_channels,
        output_dir=str(output_dir / "reg_model"),
        batch_size=8,
        num_epochs=num_epochs,
        learning_rate=1e-3,
        num_workers=0,
        loss_type="mse",
        verbose=False,
    )
