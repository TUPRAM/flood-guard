"""Invented raster cells test count conservation and unavailable age evidence."""

from contextlib import ExitStack

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box

from floodguard.evidence_age_surface import AGE_BANDS, summarize_geometry


def rasters(stack, *, missing=False, shifted=False, value=1.0):
    result = {}
    for index, band in enumerate(AGE_BANDS):
        memory = stack.enter_context(MemoryFile())
        transform = from_origin(99.8 + (0.01 if shifted and index == 1 else 0), 20.4, 0.001, 0.001)
        with memory.open(driver="GTiff", width=1, height=1, count=1,
                         dtype="float32", crs="EPSG:4326", transform=transform,
                         nodata=-99999.0) as target:
            target.write(np.array([[(-99999.0 if missing else value)]], dtype="float32"), 1)
        result[band] = stack.enter_context(memory.open())
    return result


def test_fractional_cell_count_preserves_age_group_and_complement():
    with ExitStack() as stack:
        result = summarize_geometry(box(99.8, 20.399, 99.8005, 20.4), rasters(stack))
    assert result["status"] == "modelled_research_estimate"
    assert result["population_estimate"] == pytest.approx(10, rel=0.001)
    assert result["children_0_14_estimate"] == pytest.approx(2, rel=0.001)
    assert result["older_60_plus_estimate"] == pytest.approx(3.5, rel=0.001)
    assert result["other_15_59_estimate"] == pytest.approx(4.5, rel=0.001)
    assert result["source_coverage_fraction"] == pytest.approx(1, abs=0.002)


def test_valid_zero_is_distinct_from_missing_support():
    geometry = box(99.8, 20.399, 99.801, 20.4)
    with ExitStack() as stack:
        zero = summarize_geometry(geometry, rasters(stack, value=0))
    with ExitStack() as stack:
        absent = summarize_geometry(geometry, rasters(stack, missing=True))
    assert zero["status"] == "modelled_research_estimate"
    assert zero["population_estimate"] == 0
    assert absent["status"] == "unavailable_no_common_raster_support"
    assert absent["population_estimate"] is None


def test_grid_mismatch_aborts_before_counting():
    with ExitStack() as stack, pytest.raises(ValueError, match="different grid"):
        summarize_geometry(box(99.8, 20.399, 99.801, 20.4), rasters(stack, shifted=True))


def test_missing_age_band_rejected():
    with ExitStack() as stack:
        mapping = rasters(stack)
        del mapping["10"]
        with pytest.raises(ValueError, match="20 mutually exclusive"):
            summarize_geometry(box(99.8, 20.399, 99.801, 20.4), mapping)
