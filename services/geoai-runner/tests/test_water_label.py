"""Component B's label must be selectable, grid-bound, and honestly captioned."""

from __future__ import annotations

import numpy as np
import pytest

from geoai_runner.realpipeline.water_label import (
    LABEL_METHODS,
    WaterLabelError,
    build_water_label,
    label_assumptions,
)

SHAPE = (32, 32)


def _stack() -> np.ndarray:
    """A 6-band stack where a known patch is unambiguously water.

    Water: high green, low NIR, low SWIR1 -> both MNDWI and NDWI positive.
    Land:  moderate green, high NIR and SWIR1 -> both negative.
    """

    stack = np.zeros((6, *SHAPE), dtype="float32")
    stack[1] = 0.10  # B3 green
    stack[3] = 0.30  # B8 NIR
    stack[4] = 0.35  # B11 SWIR1
    stack[1, 4:12, 4:12] = 0.30
    stack[3, 4:12, 4:12] = 0.05
    stack[4, 4:12, 4:12] = 0.04
    return stack


def test_methods_are_exactly_the_three_supported() -> None:
    assert LABEL_METHODS == ("mndwi", "ndwi", "external")


@pytest.mark.parametrize("method", ["mndwi", "ndwi"])
def test_index_labels_find_the_water_patch(method: str) -> None:
    label, prov = build_water_label(_stack(), method=method)
    assert label.dtype == np.uint8
    assert label.shape == SHAPE
    assert label[4:12, 4:12].all(), "the water patch should be labelled water"
    assert not label[20:, 20:].any(), "dry land should not be labelled water"
    assert prov["label_method"] == method
    assert prov["label_is_distillation"] is False
    assert prov["label_water_fraction"] == pytest.approx(64 / 1024, abs=1e-4)


def test_mndwi_default_reproduces_the_historical_threshold() -> None:
    """A run without --water-label must reproduce the published baseline."""

    _, prov = build_water_label(_stack())
    assert prov["label_method"] == "mndwi"
    assert prov["label_threshold"] == 0.0


def test_threshold_override_changes_the_label() -> None:
    loose, _ = build_water_label(_stack(), method="mndwi", threshold=0.0)
    strict, _ = build_water_label(_stack(), method="mndwi", threshold=0.95)
    assert int(strict.sum()) < int(loose.sum())


def test_unknown_method_is_refused() -> None:
    with pytest.raises(WaterLabelError, match="unknown water-label method"):
        build_water_label(_stack(), method="otsu")


def test_malformed_stack_is_refused() -> None:
    with pytest.raises(WaterLabelError, match="6-band stack"):
        build_water_label(np.zeros((2, *SHAPE), dtype="float32"))


# --------------------------------------------------------------------------- #
# external: the distillation path
# --------------------------------------------------------------------------- #


def test_external_without_a_raster_is_refused_with_instructions() -> None:
    with pytest.raises(WaterLabelError, match="build_owm_label"):
        build_water_label(_stack(), method="external")


def test_external_missing_file_is_refused() -> None:
    with pytest.raises(WaterLabelError, match="not found"):
        build_water_label(_stack(), method="external", external_raster="nope.tif")


def test_external_grid_mismatch_is_refused(tmp_path) -> None:
    """A label from another grid would train B against misaligned pixels."""

    rasterio = pytest.importorskip("rasterio")
    from affine import Affine

    wrong = tmp_path / "wrong_grid.tif"
    data = np.zeros((16, 16), dtype="uint8")
    with rasterio.open(
        wrong, "w", driver="GTiff", height=16, width=16, count=1,
        dtype="uint8", crs="EPSG:4326", transform=Affine.identity(),
    ) as dst:
        dst.write(data, 1)

    with pytest.raises(WaterLabelError, match="does not match the Sentinel-2"):
        build_water_label(_stack(), method="external", external_raster=wrong)


def test_external_label_is_bound_by_sha256(tmp_path) -> None:
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine

    path = tmp_path / "owm.tif"
    mask = np.zeros(SHAPE, dtype="uint8")
    mask[4:12, 4:12] = 1
    with rasterio.open(
        path, "w", driver="GTiff", height=SHAPE[0], width=SHAPE[1], count=1,
        dtype="uint8", crs="EPSG:4326", transform=Affine.identity(),
    ) as dst:
        dst.write(mask, 1)

    label, prov = build_water_label(_stack(), method="external", external_raster=path)
    assert label[4:12, 4:12].all()
    assert prov["label_is_distillation"] is True
    assert len(str(prov["label_source_sha256"])) == 64


# --------------------------------------------------------------------------- #
# The published caveat
# --------------------------------------------------------------------------- #


def test_external_caption_says_distillation_not_accuracy() -> None:
    _, prov = build_water_label(_stack(), method="mndwi")
    prov = {**prov, "label_method": "external", "label_source_path": "owm.tif",
            "label_source_sha256": "a" * 64}
    text = label_assumptions(prov)
    assert "DISTILLATION FIDELITY" in text
    assert "NOT an accuracy claim" in text


def test_mndwi_caption_states_the_label_is_known_poor() -> None:
    _, prov = build_water_label(_stack(), method="mndwi")
    text = label_assumptions(prov)
    assert "KNOWN TO BE" in text and "POOR" in text
    assert "8.7x" in text, "the measured over-detection must be stated, not implied"
    assert "must not be read" in text


def test_ndwi_caption_reports_its_measured_position() -> None:
    _, prov = build_water_label(_stack(), method="ndwi")
    text = label_assumptions(prov)
    assert "0.154" in text and "not an accuracy claim" in text
