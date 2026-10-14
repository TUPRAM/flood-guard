"""Buildings in the water against residents in the water: the pure functions."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard import buildings_in_water as bw


def test_outlines_are_used_on_area_and_on_confidence_where_one_is_given() -> None:
    area = [9.9, 10.0, 50.0, 50.0, 50.0, 50.0, 50.0]
    confidence = [0.9, 0.9, 0.69, 0.70, None, float("nan"), -1.0]
    assert bw.used(area, confidence).tolist() == [False, True, False, True, True, True, True]
    with pytest.raises(bw.BuildingsError):
        bw.used([10.0], [0.9, 0.8])


def two_buildings() -> np.ndarray:
    labels = np.zeros((30, 40), dtype="int32")
    labels[10:14, 8:12] = 1
    labels[10:14, 22:26] = 2
    return labels


def test_the_ring_is_the_ground_two_to_eight_metres_from_the_nearest_building() -> None:
    labels = two_buildings()
    ring = bw.rings(labels)
    assert ring.shape == labels.shape and not ring[labels > 0].any()
    # One pixel from the wall is beside the building and not ground; two to four pixels away is.
    assert ring[12, 12] == 0 and ring[12, 13] == 1 and ring[12, 15] == 1
    assert ring[12, 21] == 0 and ring[12, 20] == 2 and ring[12, 18] == 2
    # The two stand ten pixels apart: the ground half way is in neither ring.
    assert ring[12, 16] == 0 and ring[12, 17] == 0
    # Five pixels out is past the ring.
    assert ring[12, 3] == 0 and ring[12, 4] == 1 and ring[5, 9] == 0 and ring[6, 9] == 1
    assert set(np.unique(ring)) == {0, 1, 2}
    # Two buildings five pixels apart share the ground between them: each pixel goes to the nearer one.
    close = np.zeros((30, 40), dtype="int32")
    close[10:14, 8:12] = 1
    close[10:14, 17:21] = 2
    between = bw.rings(close)[12, 12:17].tolist()
    assert between[0] == 0 and between[1] == 1 and between[2] in (1, 2) and between[3] == 2 and between[4] == 0
    assert not bw.rings(np.zeros((5, 5), dtype="int32")).any()
    with pytest.raises(bw.BuildingsError):
        bw.rings(labels, inner_px=4, outer_px=4)


def test_a_building_stands_in_water_by_the_ground_around_it() -> None:
    labels = two_buildings()
    ring = bw.rings(labels)
    water = np.zeros(labels.shape, dtype="uint8")
    water[:, :15] = bw.WATER_YES                    # the west of the scene is water: building 1 stands in it
    water[10:14, 8:12] = bw.WATER_NO                # its roof is not water
    counts = bw.ring_counts(ring, water, 2)
    assert counts["ring_px"].tolist() == [int((ring == 1).sum()), int((ring == 2).sum())]
    assert counts["answered_px"].tolist() == counts["ring_px"].tolist()
    assert bw.assessed(counts).tolist() == [True, True]
    assert bw.in_water(counts).tolist() == [True, False]
    share = counts["water_px"] / counts["answered_px"]
    assert 0.9 < share[0] < 1.0 and share[1] == 0.0
    assert bw.in_water(counts, 0.99).tolist() == [False, False]


def test_a_building_under_cloud_is_not_assessed() -> None:
    labels = two_buildings()
    ring = bw.rings(labels)
    water = np.full(labels.shape, bw.WATER_YES, dtype="uint8")
    water[:, 18:] = bw.WATER_UNOBSERVABLE           # the east is under cloud
    counts = bw.ring_counts(ring, water, 2)
    assert bw.assessed(counts).tolist() == [True, False]
    assert bw.in_water(counts).tolist() == [True, False]
    # A building at the corner of the raster has too small a ring.
    corner = np.zeros((6, 6), dtype="int32")
    corner[0:5, 0:5] = 1
    small = bw.ring_counts(bw.rings(corner), np.zeros((6, 6), dtype="uint8"), 1)
    assert small["ring_px"][0] < bw.MIN_RING_PX and not bw.assessed(small)[0]
    with pytest.raises(bw.BuildingsError):
        bw.ring_counts(ring, water[:-1], 2)


def test_the_three_readings_of_residents_in_the_water() -> None:
    # Four cells. Cell 0: centre wet, half its area wet, 1 of 4 buildings in the water.
    # Cell 1: centre dry, a fifth wet, 2 of 2 buildings in the water. Cell 2: no building. Cell 3: centre under cloud.
    residents = np.array([100.0, 50.0, 30.0, 20.0])
    centre = np.array([1.0, 0.0, 1.0, np.nan])
    area = np.array([0.5, 0.2, 1.0, 0.3])
    held = np.array([4, 2, 0, 3])
    wet = np.array([1, 2, 0, 3])
    result = bw.residents_in_water(residents, centre, area, held, wet)
    assert result["cells_with_residents"] == 4 and result["residents"] == 200
    assert result["cells_compared"] == 2 and result["residents_compared"] == 150
    assert result["residents_in_cells_without_an_assessed_building"] == 30
    assert result["centre_rule"] == {"residents": 100, "share": round(100 / 150, 4)}
    assert result["area"] == {"residents": 60, "share": 0.4}
    assert result["buildings"] == {"residents": 75, "share": 0.5}
    assert result["buildings_minus_centre_rule_points"] == round((0.5 - 100 / 150) * 100, 1)
    without_area = bw.residents_in_water(residents, np.nan_to_num(centre), None, held, wet)
    assert "area" not in without_area and without_area["cells_compared"] == 3
    with pytest.raises(bw.BuildingsError, match="more buildings in the water"):
        bw.residents_in_water(residents, centre, area, held, held + 1)
    empty = bw.residents_in_water(np.zeros(2), np.zeros(2), None, np.zeros(2), np.zeros(2))
    assert empty["centre_rule"]["share"] is None and empty["buildings_minus_centre_rule_points"] is None


def test_the_sentence_on_the_centre_rule() -> None:
    assert bw.verdict(None) == "no cell could be compared"
    assert "within 5 points" in bw.verdict(-5.0) and "within 5 points" in bw.verdict(3.2)
    assert bw.verdict(-12.5) == "the buildings reading is lower than the centre rule by 12.5 points"
    assert bw.verdict(6.0) == "the buildings reading is higher than the centre rule by 6 points"
