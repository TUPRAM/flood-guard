"""Tests for Component B's role-scoped partition, preprocessing and evaluation.

These cover every part of the T0.1b refactor that does not need torch/geoai, so
they run in the runner's dependency-light base environment. The training call
itself is exercised by the opt-in ``geoai_smoke`` suite.

The invariants under test are the ones whose violation is silent: preprocessing
fitted on held-out pixels, a threshold chosen on the same role it is reported
from, and a metric published off a handful of positives.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")

from affine import Affine

from geoai_runner.realpipeline import water_unet
from geoai_runner.realpipeline.blocks import assign_spatial_blocks
from geoai_runner.realpipeline.raster_io import read_geotiff, write_geotiff
from geoai_runner.realpipeline.water_unet import (
    ChannelStats,
    WaterUnetError,
    evaluate_roles,
    fit_channel_stats,
)

# A ~3.4 km synthetic window: small enough to keep tests fast, and it forces the
# geometry to be stated explicitly rather than inheriting Mae Sai's defaults.
SIZE = 256
RES_DEG = 0.00012
LON_LEFT, LAT_TOP = 99.865, 20.440
TRANSFORM = Affine.translation(LON_LEFT, LAT_TOP) * Affine.scale(RES_DEG, -RES_DEG)

GEOMETRY = {"tile_size_px": 32, "buffer_m": 200.0, "latitude": 20.4, "min_blocks": 9}


@pytest.fixture(scope="module")
def assignment():
    return assign_spatial_blocks((SIZE, SIZE), TRANSFORM, seed=0, **GEOMETRY)


@pytest.fixture()
def scene(tmp_path, assignment):
    """A 6-band raster whose held-out blocks have a deliberately different scale.

    If preprocessing statistics were fitted over the whole scene instead of the
    training role, the fitted mean would be pulled away from the training mean --
    which is precisely what the assertions below detect.
    """

    rng = np.random.default_rng(11)
    stack = rng.normal(0.20, 0.02, size=(6, SIZE, SIZE)).astype("float32")
    held_out = ~assignment.mask("train")
    stack[:, held_out] += 5.0  # extreme, so any leakage is unmistakable

    labels = np.zeros((SIZE, SIZE), dtype="uint8")
    labels[40:120, 40:200] = 1  # a broad water body spanning several blocks
    labels[170:230, 30:210] = 1

    image_path = tmp_path / "s2.tif"
    label_path = tmp_path / "labels.tif"
    write_geotiff(image_path, stack, TRANSFORM, "EPSG:4326")
    write_geotiff(label_path, labels, TRANSFORM, "EPSG:4326", dtype="uint8")
    return image_path, label_path, stack, labels


# --------------------------------------------------------------------------- #
# Preprocessing is fitted on the training role only (leakage control #6)
# --------------------------------------------------------------------------- #
def test_channel_stats_rejects_non_training_role(scene, assignment):
    image_path, _, _, _ = scene
    for role in ("val", "test"):
        with pytest.raises(WaterUnetError, match="training role"):
            fit_channel_stats(image_path, assignment, role=role)


def test_channel_stats_ignore_held_out_pixels(scene, assignment):
    image_path, _, stack, _ = scene
    stats = water_unet.fit_channel_stats(image_path, assignment, role="train")
    train_mask = assignment.mask("train")
    for band in range(stack.shape[0]):
        expected = float(stack[band][train_mask].mean())
        assert stats.mean[band] == pytest.approx(expected, abs=1e-4)
    # The +5.0 offset lives only outside the training role, so a whole-scene fit
    # would land far above the training mean.
    assert max(stats.mean) < 1.0
    assert stats.fitted_on_role == "train"
    assert stats.n_pixels == int(train_mask.sum())


def test_standardised_raster_normalises_the_training_role(scene, assignment, tmp_path):
    image_path, _, _, _ = scene
    stats = water_unet.fit_channel_stats(image_path, assignment, role="train")
    out = water_unet.write_standardised_raster(image_path, stats, tmp_path / "std.tif")
    standardised, _, _ = read_geotiff(out)
    train_mask = assignment.mask("train")
    for band in range(standardised.shape[0]):
        values = standardised[band][train_mask]
        assert values.mean() == pytest.approx(0.0, abs=1e-3)
        assert values.std() == pytest.approx(1.0, abs=1e-3)


def test_standardisation_rejects_band_count_mismatch(scene, tmp_path, assignment):
    image_path, _, _, _ = scene
    wrong = ChannelStats(mean=(0.0, 0.0), std=(1.0, 1.0), fitted_on_role="train", n_pixels=1)
    with pytest.raises(WaterUnetError, match="bands"):
        water_unet.write_standardised_raster(image_path, wrong, tmp_path / "bad.tif")


def test_class_weights_come_from_the_training_prior(scene, assignment):
    _, label_path, _, _ = scene
    background, water = water_unet.inverse_frequency_class_weights(label_path, assignment)
    assert background == 1.0
    assert 1.0 < water <= 30.0
    labels, _, _ = read_geotiff(label_path)
    rate = float(labels[0].astype(bool)[assignment.mask("train")].mean())
    assert water == pytest.approx(min(30.0, (1 - rate) / rate), rel=1e-6)


# --------------------------------------------------------------------------- #
# Tiling
# --------------------------------------------------------------------------- #
def test_role_tiles_are_written_and_disjoint(scene, assignment, tmp_path):
    image_path, label_path, _, _ = scene
    partition = water_unet.prepare_role_tiles(
        image_path, label_path, tmp_path / "tiles", assignment,
        tile_size=32, stride=16, min_train_tiles=1,
    )
    assert set(partition.directories) == {"train", "val", "test"}
    for role, (images_dir, labels_dir) in partition.directories.items():
        assert len(list(images_dir.glob("*.tif"))) == partition.counts[role]
        assert len(list(labels_dir.glob("*.tif"))) == partition.counts[role]
    assert partition.counts["train"] > 0
    assert partition.assignment_sha256 == assignment.assignment_sha256


def test_insufficient_training_tiles_fails_closed(scene, assignment, tmp_path):
    image_path, label_path, _, _ = scene
    with pytest.raises(WaterUnetError, match="minimum"):
        water_unet.prepare_role_tiles(
            image_path, label_path, tmp_path / "tiles", assignment,
            tile_size=32, stride=16, min_train_tiles=10_000,
        )


def test_tiling_rejects_mismatched_assignment(scene, tmp_path):
    image_path, label_path, _, _ = scene
    # A partition built for a different grid size must never be silently applied
    # to this raster -- that would misalign every role boundary.
    other = assign_spatial_blocks(
        (192, 192), TRANSFORM, seed=0, tile_size_px=16, buffer_m=100.0, latitude=20.4
    )
    with pytest.raises(WaterUnetError, match="does not match"):
        water_unet.prepare_role_tiles(
            image_path, label_path, tmp_path / "tiles", other, tile_size=32, stride=16
        )


# --------------------------------------------------------------------------- #
# Role-scoped evaluation
# --------------------------------------------------------------------------- #
def _probability_from(labels: np.ndarray, noise: float, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = labels.astype("float32") * 0.8 + 0.1
    return np.clip(base + rng.normal(0.0, noise, size=labels.shape), 0.0, 1.0).astype("float32")


def test_threshold_is_selected_on_validation_only(scene, assignment):
    _, _, _, labels = scene
    result = evaluate_roles(
        _probability_from(labels, 0.10), labels, assignment, min_positive=None
    )
    assert result["threshold_selection"]["selected_on_role"] == "val"
    assert 0.0 < result["threshold_selection"]["selected_threshold"] < 1.0
    assert result["headline_role"] == "test"
    assert set(result["metrics_by_role"]) == {"train", "val", "test"}


def test_explicit_threshold_is_recorded_as_caller_supplied(scene, assignment):
    _, _, _, labels = scene
    result = evaluate_roles(
        _probability_from(labels, 0.10), labels, assignment, threshold=0.5, min_positive=None
    )
    assert result["threshold_selection"]["selected_on_role"] == "caller_supplied"
    assert result["threshold_selection"]["selected_threshold"] == 0.5


def test_low_positive_support_blocks_the_metric(scene, assignment):
    _, _, _, labels = scene
    sparse = np.zeros_like(labels)
    sparse[0, 0] = 1  # one positive pixel scene-wide
    result = evaluate_roles(
        _probability_from(labels, 0.05), sparse, assignment, threshold=0.5, min_positive=2_000
    )
    for role, entry in result["metrics_by_role"].items():
        assert entry["blocked_reason"] == "insufficient_positive_support", role
        assert "iou" not in entry


def test_clean_signal_is_diagnosed_as_reproduced(scene, assignment):
    _, _, _, labels = scene
    result = evaluate_roles(
        _probability_from(labels, 0.02), labels, assignment, min_positive=None
    )
    assert result["metrics_by_role"]["test"]["iou"] > 0.85
    assert result["generalisation_diagnosis"] == "target_reproduced_on_held_out_blocks"


def test_diagnosis_names_each_failure_mode():
    assert water_unet._diagnose(0.38, 0.36) == "optimisation_failure_train_and_test_both_low"
    assert water_unet._diagnose(0.95, 0.60) == "overfitting_train_much_higher_than_test"
    assert water_unet._diagnose(0.90, 0.88) == "target_reproduced_on_held_out_blocks"
    assert water_unet._diagnose(0.80, 0.75) == "underfitting_or_task_limited"
    assert water_unet._diagnose(None, 0.9) == "indeterminate_insufficient_support"


def test_unknown_role_is_rejected(scene, assignment):
    _, _, _, labels = scene
    with pytest.raises(WaterUnetError, match="unknown role"):
        evaluate_roles(
            _probability_from(labels, 0.05), labels, assignment,
            threshold=0.5, roles=("train", "holdout"),
        )
