"""Tests for the Sentinel-2 water check: MNDWI on reflectance, the scene-classification clear mask and the area sums.

The check labels its result "water or saturated mud" and its comparison with the model "indicative"; these tests
pin the arithmetic behind those figures. Fixtures are small synthetic arrays, not imagery.
"""

from __future__ import annotations

import numpy as np
import pytest

from floodguard.flood_timeline import SENTINEL2_L2A_QUANTIFICATION, sentinel2_l2a_reflectance
from floodguard.optical_water_check import (
    MNDWI_THRESHOLD,
    SCL_CLASSES,
    SCL_NOT_CLEAR,
    SCL_STRICT_CLEAR,
    class_areas,
    mndwi,
    model_overlap,
    new_water_areas,
    scene_areas,
    scl_clear_mask,
    upsample,
    wet_surface,
)

CELL_KM2 = 1.0  # One square kilometre per cell keeps the expected areas whole numbers.


# --- MNDWI ----------------------------------------------------------------------------------------------------


def test_mndwi_on_known_reflectances() -> None:
    green = np.array([0.10, 0.06, 0.05, 0.20, 0.03])
    swir16 = np.array([0.02, 0.06, 0.25, 0.05, 0.09])
    assert mndwi(green, swir16).tolist() == pytest.approx([(0.10 - 0.02) / 0.12, 0.0, (0.05 - 0.25) / 0.30, 0.6, -0.5])
    # Open water absorbs short-wave infrared (positive index); vegetation and dry soil reflect it (negative index).
    assert mndwi(np.array([0.08]), np.array([0.01]))[0] > 0 > mndwi(np.array([0.06]), np.array([0.22]))[0]


def test_mndwi_is_nan_without_data_and_never_divides_by_zero() -> None:
    green = np.array([np.nan, 0.1, 0.0, 0.1, -0.05])
    swir16 = np.array([0.1, np.nan, 0.0, np.inf, 0.02])
    with np.errstate(all="raise"):  # No warning, no division by zero.
        out = mndwi(green, swir16)
    assert np.isnan(out).all()
    with pytest.raises(ValueError, match="one shape"):
        mndwi(np.zeros((2, 2)), np.zeros((2, 3)))


def test_reflectance_is_dn_over_10000_and_subtracting_1000_would_change_the_index() -> None:
    """Earth Search L2A files already have the baseline-04.00 offset removed: nothing is subtracted."""
    assert SENTINEL2_L2A_QUANTIFICATION == 10000.0
    green_dn = np.array([[592, 1400, 0]], dtype=np.uint16)
    swir_dn = np.array([[1800, 300, 900]], dtype=np.uint16)
    surface = wet_surface(green_dn, swir_dn, np.array([[4, 6, 4]], dtype=np.uint8))
    assert sentinel2_l2a_reflectance(green_dn)[0, :2].tolist() == pytest.approx([0.0592, 0.14])
    assert surface.index[0, :2].tolist() == pytest.approx([(592 - 1800) / (592 + 1800), (1400 - 300) / (1400 + 300)])
    assert np.isnan(surface.index[0, 2])  # DN 0 is no data.
    # With the offset wrongly subtracted the same pixels would read (DN - 1000) / 10000: a different index, and a
    # negative green reflectance for ordinary vegetation (DN 592). This test fails if the code ever subtracts it.
    wrong = mndwi((green_dn[0, :2] - 1000.0) / 10000.0, (swir_dn[0, :2] - 1000.0) / 10000.0)
    assert not np.allclose(surface.index[0, :2], wrong, equal_nan=True)
    assert (green_dn[0, 0] - 1000.0) / 10000.0 < 0
    # A turbid-water pixel (green 0.14, swir 0.03) is wet under DN / 10000; with the offset its swir turns negative,
    # the two bands no longer sum to a positive value and the pixel would have no index at all.
    assert surface.wet[0, 1] and np.isnan(wrong[1])


# --- Scene classification ---------------------------------------------------------------------------------------


def test_scl_clear_mask_drops_shadow_cloud_cirrus_and_no_data() -> None:
    scl = np.arange(12, dtype=np.uint8)
    clear = scl_clear_mask(scl)
    assert SCL_NOT_CLEAR == frozenset({0, 3, 8, 9, 10})
    assert [int(value) for value in scl[~clear]] == [0, 3, 8, 9, 10]
    assert [SCL_CLASSES[int(value)] for value in scl[clear]] == [
        "saturated_or_defective", "dark_area", "vegetation", "not_vegetated", "water", "unclassified", "snow_or_ice"]
    # A value outside the SCL range is not a class: it is treated as no data.
    assert not scl_clear_mask(np.array([12, 200, 255], dtype=np.uint8)).any()
    # The stricter reading keeps vegetation, bare ground and water only.
    strict = scl_clear_mask(scl, not_clear=set(SCL_CLASSES) - SCL_STRICT_CLEAR)
    assert [int(value) for value in scl[strict]] == [4, 5, 6]


def test_wet_surface_needs_a_clear_class_data_in_both_bands_and_a_positive_index() -> None:
    green = np.array([[1400, 1400, 1400, 0, 600, 1400, 1000]], dtype=np.uint16)
    swir = np.array([[300, 300, 300, 300, 2000, 0, 1000]], dtype=np.uint16)
    scl = np.array([[6, 9, 3, 6, 4, 6, 5]], dtype=np.uint8)
    surface = wet_surface(green, swir, scl)
    #                                   water  cloud  shadow no-green dry-veg no-swir index == 0
    assert surface.clear.tolist() == [[True, False, False, False, True, False, True]]
    assert surface.wet.tolist() == [[True, False, False, False, False, False, False]]
    assert MNDWI_THRESHOLD == 0.0 and surface.index[0, 6] == 0.0  # The threshold is strict: an index of 0 is not wet.
    assert wet_surface(green, swir, scl, threshold=0.7).wet.sum() == 0  # (1400 - 300) / 1700 = 0.647.
    with pytest.raises(ValueError, match="same grid"):
        wet_surface(green, swir, scl[:, :3])


def test_upsample_repeats_cells_onto_the_finer_grid() -> None:
    mask = np.array([[True, False], [False, True]])
    assert upsample(mask, 2).tolist() == [[True, True, False, False], [True, True, False, False],
                                          [False, False, True, True], [False, False, True, True]]
    assert upsample(mask, 1).tolist() == mask.tolist()
    with pytest.raises(ValueError):
        upsample(mask, 0)


# --- Area sums ---------------------------------------------------------------------------------------------------


def grid(rows: list[str]) -> np.ndarray:
    return np.array([[cell == "#" for cell in row] for row in rows])


def test_scene_areas_count_clear_cells_in_the_area_and_leave_permanent_water_out() -> None:
    area = grid(["####", "####", "...."])       # 8 cells
    clear = grid(["###.", "##..", "####"])      # 5 clear cells inside the area
    wet = grid(["##..", "#...", "#..."])        # 3 wet cells inside the area, 1 outside
    permanent = grid(["#...", "....", "...."])  # 1 permanent cell, which is wet and clear
    out = scene_areas(wet, clear, area, permanent, CELL_KM2)
    assert out == {"clear_km2": 5.0, "clear_share": 0.625, "water_km2": 2.0}
    # Areas are published to 0.01 km2 and shares to 0.001: a 10 m cell (0.0001 km2) alone rounds to nothing.
    assert scene_areas(wet, clear, area, permanent, 0.0001)["water_km2"] == 0.0
    assert scene_areas(upsample(wet, 10), upsample(clear, 10), upsample(area, 10), upsample(permanent, 10), 0.0001)["water_km2"] == 0.02
    # Nothing clear: nothing was observed, which is not the same as no water.
    hidden = scene_areas(np.zeros_like(wet), np.zeros_like(clear), area, permanent, CELL_KM2)
    assert hidden == {"clear_km2": 0.0, "clear_share": 0.0, "water_km2": None}
    with pytest.raises(ValueError, match="clear cell"):
        scene_areas(grid(["...#", "....", "...."]), clear, area, permanent, CELL_KM2)
    with pytest.raises(ValueError, match="empty"):
        scene_areas(wet, clear, np.zeros_like(area), permanent, CELL_KM2)
    with pytest.raises(ValueError, match="one grid"):
        scene_areas(wet[:2], clear, area, permanent, CELL_KM2)


def test_new_water_needs_both_dates_clear() -> None:
    area = grid(["#####"])
    permanent = grid(["#...."])
    event_clear = grid(["####."])
    pre_clear = grid(["###.#"])
    event_wet = grid(["####."])
    pre_wet = grid(["#.#.."])
    out = new_water_areas(event_wet, event_clear, pre_wet, pre_clear, area, permanent, 1.0)
    # Both clear and not permanent: cells 1 and 2. Cell 1 is new; cell 2 was already wet; cell 3 was under cloud before.
    assert out == {"both_clear_km2": 2.0, "event_water_km2": 2.0, "pre_event_water_km2": 1.0, "new_water_km2": 1.0, "no_longer_water_km2": 0.0}
    gone = new_water_areas(pre_wet, pre_clear, event_wet, event_clear, area, permanent, 1.0)
    assert (gone["new_water_km2"], gone["no_longer_water_km2"]) == (0.0, 1.0)
    never = new_water_areas(event_wet, event_clear, pre_wet, ~event_clear & ~area, area, permanent, 1.0)
    assert never == {"both_clear_km2": 0.0, "event_water_km2": None, "pre_event_water_km2": None, "new_water_km2": None, "no_longer_water_km2": None}


def test_model_overlap_is_counted_in_clear_cells_and_every_key_is_named_as_model_output() -> None:
    area = grid(["########"])
    permanent = grid(["#......."])
    clear = grid(["######.."])
    wet = grid(["#####..."])        # Observed: cells 1-4 once the permanent cell is left out.
    model = grid(["#..####."])      # Model: cells 3-6; cells 3-5 are clear; cell 0 is permanent and never counted.
    out = model_overlap(wet, clear, model, area, permanent, 1.0)
    assert all(key.startswith("model_") for key in out)
    assert out["model_flood_km2_district"] == 4.0 and out["model_flood_km2_clear"] == 3.0
    assert out["model_overlap_km2"] == 2.0 and out["model_union_km2"] == 5.0
    assert out["model_agreement_iou"] == pytest.approx(0.4)
    assert out["model_share_of_observed_water_reached"] == pytest.approx(0.5)
    assert out["model_share_inside_observed_water"] == pytest.approx(0.667)
    empty = model_overlap(np.zeros_like(wet), clear, np.zeros_like(model), area, permanent, 1.0)
    assert empty["model_agreement_iou"] is None and empty["model_share_of_observed_water_reached"] is None
    assert empty["model_share_inside_observed_water"] is None and empty["model_overlap_km2"] == 0.0
    # Identical masks coincide fully; disjoint masks not at all.
    same = model_overlap(wet, clear, wet, area, permanent, 1.0)
    assert same["model_agreement_iou"] == 1.0
    apart = model_overlap(grid(["###....."]), clear, grid(["....##.."]), area, permanent, 1.0)
    assert apart["model_agreement_iou"] == 0.0 and apart["model_overlap_km2"] == 0.0


def test_model_area_where_both_scenes_are_clear_is_the_figure_beside_the_new_water() -> None:
    wet, clear, model = grid(["###....."]), grid(["######.."]), grid([".#####.#"])
    area, permanent = grid(["########"]), grid(["........"])
    # Without the earlier scene's clear mask the result has no both-clear figure: it would be a guess.
    assert "model_flood_km2_both_clear" not in model_overlap(wet, clear, model, area, permanent, 1.0)
    earlier = grid([".####..#"])  # Cloud hid the first cell and two more on the earlier date.
    out = model_overlap(wet, clear, model, area, permanent, 1.0, earlier_clear=earlier)
    # Model cells 1-5 are clear on the event date; cells 1-4 are clear on both dates.
    assert (out["model_flood_km2_clear"], out["model_flood_km2_both_clear"]) == (5.0, 4.0)
    assert out["model_flood_km2_both_clear"] <= out["model_flood_km2_clear"] <= out["model_flood_km2_district"]
    assert all(key.startswith("model_") for key in out)
    # It is counted in the same cells as the new water: both dates clear, inside the area, outside permanent water.
    pre_wet = grid([".#......"])
    change = new_water_areas(wet, clear, pre_wet, earlier, area, permanent, 1.0)
    assert (change["both_clear_km2"], change["new_water_km2"]) == (4.0, 1.0)
    channel = grid(["..#....."])
    assert model_overlap(wet, clear, model, area, channel, 1.0, earlier_clear=earlier)["model_flood_km2_both_clear"] == 3.0
    with pytest.raises(ValueError, match="share one grid"):
        model_overlap(wet, clear, model, area, permanent, 1.0, earlier_clear=grid(["####"]))


def test_class_areas_name_every_class_present_in_the_area() -> None:
    scl = np.array([[4, 4, 6, 9], [3, 7, 4, 200]], dtype=np.uint8)
    area = np.array([[True, True, True, True], [True, True, False, True]])
    out = class_areas(scl, area, 0.5)
    assert out == {"cloud_shadow": 0.5, "vegetation": 1.0, "water": 0.5, "unclassified": 0.5, "cloud_high_probability": 0.5, "no_data": 0.5}
    assert sum(out.values()) == pytest.approx(area.sum() * 0.5)
