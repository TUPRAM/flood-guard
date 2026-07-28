"""Tests for Component E's grid alignment and built-up change (T3.1).

The regression these lock down is the silent-stretch bug: the previous flow
nearest-neighbour resized a full-district susceptibility raster onto a
town-subset change grid. Different ground, no error, plausible-looking output.
It only stayed invisible because the change mask was empty.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")

from affine import Affine

from geoai_runner.realpipeline.encroachment import (
    CHANGESTAR_NULL_RESULT,
    GridMismatchError,
    builtup_change,
    reproject_to_grid,
)
from geoai_runner.realpipeline.raster_io import write_geotiff

# Full district vs a town subset -- the two extents that were silently conflated.
DISTRICT = (99.799, 20.250, 100.044, 20.475)
TOWN = (99.860, 20.420, 99.900, 20.460)
FAR_AWAY = (100.900, 21.400, 101.000, 21.500)


def _grid(bounds, shape):
    left, bottom, right, top = bounds
    height, width = shape
    return Affine.translation(left, top) * Affine.scale(
        (right - left) / width, (bottom - top) / height
    )


def _write(path, bounds, shape, value=None):
    transform = _grid(bounds, shape)
    data = np.full(shape, 60.0, dtype="float32") if value is None else value.astype("float32")
    write_geotiff(path, data, transform, "EPSG:4326")
    return path, transform


# --------------------------------------------------------------------------- #
# Grid alignment
# --------------------------------------------------------------------------- #
def test_reprojection_onto_a_contained_subset_succeeds(tmp_path):
    """A district raster fully covers a town subset -- this must work."""

    source, _ = _write(tmp_path / "district.tif", DISTRICT, (256, 256))
    out = reproject_to_grid(source, _grid(TOWN, (128, 128)), (128, 128), "EPSG:4326")
    assert out.shape == (128, 128)
    assert np.allclose(out, 60.0)


def test_non_overlapping_extents_raise_instead_of_stretching(tmp_path):
    """The actual bug: two grids describing different ground must not resample."""

    source, _ = _write(tmp_path / "elsewhere.tif", FAR_AWAY, (128, 128))
    with pytest.raises(GridMismatchError, match="covers only"):
        reproject_to_grid(source, _grid(TOWN, (128, 128)), (128, 128), "EPSG:4326")


def test_partial_overlap_below_threshold_is_rejected(tmp_path):
    source, _ = _write(tmp_path / "corner.tif", (99.895, 20.455, 99.935, 20.495), (128, 128))
    with pytest.raises(GridMismatchError):
        reproject_to_grid(
            source, _grid(TOWN, (128, 128)), (128, 128), "EPSG:4326", min_overlap=0.9
        )


def test_overlap_threshold_is_configurable(tmp_path):
    source, _ = _write(tmp_path / "corner.tif", (99.895, 20.455, 99.935, 20.495), (128, 128))
    out = reproject_to_grid(
        source, _grid(TOWN, (128, 128)), (128, 128), "EPSG:4326", min_overlap=0.0
    )
    assert out.shape == (128, 128)


def test_reprojection_preserves_spatial_position(tmp_path):
    """Values must land on the correct ground, not merely fill the array."""

    values = np.zeros((256, 256), dtype="float32")
    values[:128, :] = 100.0  # northern half hot
    source, _ = _write(tmp_path / "half.tif", DISTRICT, (256, 256), values)
    # A subset covering only the far north must come back hot throughout.
    north = (99.85, 20.44, 99.95, 20.47)
    out = reproject_to_grid(source, _grid(north, (64, 64)), (64, 64), "EPSG:4326")
    assert out.mean() > 90.0


# --------------------------------------------------------------------------- #
# Built-up change
# --------------------------------------------------------------------------- #
def _epochs(tmp_path, shape=(64, 64)):
    t1 = np.zeros(shape, dtype="float32")
    t2 = np.zeros(shape, dtype="float32")
    t2[10:30, 10:30] = 0.4  # new built-up in the north-west
    t2[40:60, 40:60] = 0.01  # below-threshold noise in the south-east
    p1, _ = _write(tmp_path / "t1.tif", TOWN, shape, t1)
    p2, _ = _write(tmp_path / "t2.tif", TOWN, shape, t2)
    return p1, p2


def test_growth_is_detected_above_threshold(tmp_path):
    p1, p2 = _epochs(tmp_path)
    result = builtup_change(p1, p2, tmp_path / "out", t1_year=2015, t2_year=2025)
    assert result.metrics["growth_cell_fraction"] == pytest.approx(400 / 4096, abs=1e-4)
    assert result.metrics["mean_builtup_delta"] > 0


def test_sub_threshold_change_is_not_counted(tmp_path):
    p1, p2 = _epochs(tmp_path)
    result = builtup_change(
        p1, p2, tmp_path / "out", change_threshold=0.5, t1_year=2015, t2_year=2025
    )
    assert result.metrics["growth_cell_fraction"] == 0.0


def test_floodplain_intersection_uses_real_reprojection(tmp_path):
    p1, p2 = _epochs(tmp_path)
    # Susceptibility high only in the north-west, matching where growth occurs.
    susceptibility = np.zeros((256, 256), dtype="float32")
    susceptibility[:128, :128] = 80.0
    susc_path, _ = _write(tmp_path / "susc.tif", TOWN, (256, 256), susceptibility)

    result = builtup_change(
        p1, p2, tmp_path / "out", susceptibility_path=susc_path, t1_year=2015, t2_year=2025
    )
    assert result.metrics["floodplain_share_of_growth"] == pytest.approx(1.0, abs=0.05)
    assert (
        result.metrics["mean_delta_in_floodplain"]
        > result.metrics["mean_delta_outside_floodplain"]
    )
    assert result.artifacts["floodplain_growth"].exists()


def test_mismatched_floodplain_extent_fails_closed(tmp_path):
    """The original bug, reproduced: susceptibility from the wrong extent."""

    p1, p2 = _epochs(tmp_path)
    susc_path, _ = _write(tmp_path / "wrong.tif", FAR_AWAY, (256, 256))
    with pytest.raises(GridMismatchError):
        builtup_change(p1, p2, tmp_path / "out", susceptibility_path=susc_path)


def test_epoch_shape_mismatch_is_rejected(tmp_path):
    p1, _ = _write(tmp_path / "a.tif", TOWN, (64, 64), np.zeros((64, 64), dtype="float32"))
    p2, _ = _write(tmp_path / "b.tif", TOWN, (32, 32), np.zeros((32, 32), dtype="float32"))
    with pytest.raises(GridMismatchError, match="different shapes"):
        builtup_change(p1, p2, tmp_path / "out")


def test_percent_scaled_products_are_normalised(tmp_path):
    """GHSL publishes surface fraction in percent; both scalings must agree."""

    shape = (64, 64)
    t1 = np.zeros(shape, dtype="float32")
    t2 = np.zeros(shape, dtype="float32")
    t2[10:30, 10:30] = 40.0  # percent scale
    p1, _ = _write(tmp_path / "t1pct.tif", TOWN, shape, t1)
    p2, _ = _write(tmp_path / "t2pct.tif", TOWN, shape, t2)
    result = builtup_change(p1, p2, tmp_path / "out")
    assert result.metrics["growth_cell_fraction"] == pytest.approx(400 / 4096, abs=1e-4)


# --------------------------------------------------------------------------- #
# The retained ChangeStar null
# --------------------------------------------------------------------------- #
def test_changestar_null_is_preserved_as_a_citable_record():
    assert CHANGESTAR_NULL_RESULT["executed"] is True
    assert CHANGESTAR_NULL_RESULT["change_fraction"] == 0.0
    assert CHANGESTAR_NULL_RESULT["outcome"] == "null_result_resolution_limited"
    assert "sub-metre" in CHANGESTAR_NULL_RESULT["interpretation"]
    assert CHANGESTAR_NULL_RESULT["superseded_by"] == "ghsl_built_s_multitemporal"


def test_change_metrics_carry_the_superseded_method(tmp_path):
    p1, p2 = _epochs(tmp_path)
    result = builtup_change(p1, p2, tmp_path / "out")
    assert result.metrics["superseded_method"]["change_fraction"] == 0.0
