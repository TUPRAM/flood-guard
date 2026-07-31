"""Tests for Component F's role-aware few-shot classifier.

The fitting path needs scikit-learn (part of the ``realpipeline`` extra), so it
is skipped in the base environment. The configuration guards run everywhere,
because those are the checks that stop a misaligned partition being applied
silently.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")

from affine import Affine

from geoai_runner.realpipeline.blocks import assign_spatial_blocks
from geoai_runner.realpipeline.embeddings import EmbeddingError, few_shot_flood_classifier
from geoai_runner.realpipeline.raster_io import write_geotiff

SIZE = 256
RES_DEG = 0.00012
TRANSFORM = Affine.translation(99.865, 20.440) * Affine.scale(RES_DEG, -RES_DEG)
GEOMETRY = {"tile_size_px": 32, "buffer_m": 200.0, "latitude": 20.4, "min_blocks": 9}


@pytest.fixture(scope="module")
def assignment():
    return assign_spatial_blocks((SIZE, SIZE), TRANSFORM, seed=0, **GEOMETRY)


@pytest.fixture()
def scene(tmp_path):
    rng = np.random.default_rng(5)
    stack = rng.normal(0.2, 0.03, size=(6, SIZE, SIZE)).astype("float32")
    labels = np.zeros((SIZE, SIZE), dtype="uint8")
    labels[30:130, 30:220] = 1
    labels[160:240, 20:200] = 1
    # Make water spectrally separable: high green, low SWIR1 -> MNDWI positive.
    stack[1][labels.astype(bool)] += 0.25
    stack[4][labels.astype(bool)] -= 0.12
    image_path = tmp_path / "s2.tif"
    label_path = tmp_path / "labels.tif"
    write_geotiff(image_path, stack, TRANSFORM, "EPSG:4326")
    write_geotiff(label_path, labels, TRANSFORM, "EPSG:4326", dtype="uint8")
    return image_path, label_path


# --------------------------------------------------------------------------- #
# Configuration guards (no sklearn needed)
# --------------------------------------------------------------------------- #
def test_mismatched_assignment_is_rejected(scene, tmp_path):
    image_path, label_path = scene
    other = assign_spatial_blocks(
        (192, 192), TRANSFORM, seed=0, tile_size_px=16, buffer_m=100.0, latitude=20.4
    )
    with pytest.raises(EmbeddingError, match="does not match"):
        few_shot_flood_classifier(image_path, label_path, tmp_path / "o.parquet", other)


def test_unknown_role_is_rejected(scene, assignment, tmp_path):
    image_path, label_path = scene
    with pytest.raises(EmbeddingError, match="unknown role"):
        few_shot_flood_classifier(
            image_path, label_path, tmp_path / "o.parquet", assignment,
            roles=("train", "holdout"),
        )


# --------------------------------------------------------------------------- #
# Fitting behaviour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("_", [None])
def test_labels_come_only_from_training_blocks(scene, assignment, tmp_path, _):
    pytest.importorskip("sklearn")
    image_path, label_path = scene
    result = few_shot_flood_classifier(
        image_path, label_path, tmp_path / "out.parquet", assignment,
        n_labels_per_class=25, min_positive=None,
    )
    assert result.metrics["labels_drawn_from_role"] == "train"
    assert result.metrics["n_training_labels"] == 50
    assert set(result.metrics["metrics_by_role"]) == {"train", "val", "test"}
    assert result.metrics["headline_role"] == "test"


def test_tautology_and_scope_flags_are_emitted(scene, assignment, tmp_path):
    pytest.importorskip("sklearn")
    image_path, label_path = scene
    result = few_shot_flood_classifier(
        image_path, label_path, tmp_path / "out.parquet", assignment, min_positive=None
    )
    # These flags are what stop a downstream surface presenting an in-scene index
    # re-derivation as evidence of few-shot generalisation.
    assert result.metrics["feature_contains_target_inputs"] is True
    assert result.metrics["is_foundation_model_embedding"] is False
    assert result.metrics["is_cross_district_transfer"] is False


def test_partition_provenance_travels_with_the_metrics(scene, assignment, tmp_path):
    pytest.importorskip("sklearn")
    image_path, label_path = scene
    result = few_shot_flood_classifier(
        image_path, label_path, tmp_path / "out.parquet", assignment, min_positive=None
    )
    partition = result.metrics["partition"]
    assert partition["is_sealed_multi_event_partition"] is False
    assert partition["assignment_sha256"] == assignment.assignment_sha256


def test_low_support_blocks_the_role_metric(scene, assignment, tmp_path):
    pytest.importorskip("sklearn")
    image_path, label_path = scene
    result = few_shot_flood_classifier(
        image_path, label_path, tmp_path / "out.parquet", assignment,
        min_positive=10_000_000,
    )
    for entry in result.metrics["metrics_by_role"].values():
        assert entry["blocked_reason"] == "insufficient_positive_support"
