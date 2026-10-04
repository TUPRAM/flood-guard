"""Synthetic-array tests for the radar candidates of plan tasks A2 and A4 (no external data)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodguard import geoid_m1_review as review
from floodguard import radar_candidates as rc
from floodguard import sar_change_v2 as sar

pytest.importorskip("scipy")

ROOT = Path(__file__).resolve().parents[1]
NO_SMOOTHING = rc.UnSpiderConfig(smoothing_radius_m=0.0)


def _speckle(rng: np.random.Generator, mean: np.ndarray, looks: float = 4.4) -> np.ndarray:
    return mean * rng.gamma(looks, 1.0 / looks, size=mean.shape)


def _pair(rng: np.random.Generator, change_db: np.ndarray, base: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Speckled pre and post images (VV, VH); ``change_db`` is post minus pre in dB."""

    flat = np.full(change_db.shape, base)
    factor = 10.0 ** (change_db / 10.0)
    pre = np.stack([_speckle(rng, flat), _speckle(rng, flat * 0.25)])
    post = np.stack([_speckle(rng, flat * factor), _speckle(rng, flat * 0.25 * factor)])
    return pre.astype("float32"), post.astype("float32")


def _flooded_tile(seed: int, size: int = 128) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A tile whose left third darkened by 8 dB."""

    change = np.zeros((size, size))
    change[:, : size // 3] = -8.0
    pre, post = _pair(np.random.default_rng(seed), change)
    return pre, post, change < 0


def _linear(db: float) -> float:
    return float(10.0 ** (db / 10.0))


# --- lattice --------------------------------------------------------------


def test_lattice_is_the_geoid_lattice() -> None:
    # GEOID tile EMSR712-3-9 starts at easting 471040 and northing 5888000 in its UTM zone.
    assert 471040 % (rc.GEOID_TILE_CELLS * rc.GEOID_CELL_M) == 0
    assert 5888000 % (rc.GEOID_TILE_CELLS * rc.GEOID_CELL_M) == 0
    tiles = rc.lattice_tiles((584619.4, 2240248.1, 608177.3, 2263241.0))
    assert [tile.name for tile in tiles] == [
        "E057N221", "E058N221", "E059N221",
        "E057N220", "E058N220", "E059N220",
        "E057N219", "E058N219", "E059N219",
        "E057N218", "E058N218", "E059N218",
    ]
    first = tiles[0]
    assert (first.west, first.south, first.east, first.north) == (583680.0, 2263040.0, 593920.0, 2273280.0)


def test_lattice_handles_bounds_on_a_tile_edge_and_refuses_empty_bounds() -> None:
    tiles = rc.lattice_tiles((0.0, 0.0, 200.0, 100.0), tile_cells=10, cell_m=10.0)
    assert [tile.name for tile in tiles] == ["E000N000", "E001N000"]
    with pytest.raises(rc.RadarCandidateError, match="positive extent"):
        rc.lattice_tiles((0.0, 0.0, 0.0, 10.0))


def test_tile_window_places_a_tile_on_an_aligned_grid() -> None:
    tiles = rc.lattice_tiles((0.0, 0.0, 200.0, 200.0), tile_cells=10, cell_m=10.0)
    lower_right = next(tile for tile in tiles if tile.name == "E001N000")
    assert rc.tile_window(lower_right, 0.0, 200.0, 10.0) == (slice(10, 20), slice(10, 20))
    with pytest.raises(rc.RadarCandidateError, match="not aligned"):
        rc.tile_window(lower_right, 5.0, 200.0, 10.0)


# --- UN-SPIDER practice ---------------------------------------------------


def test_circle_kernel_of_fifty_metres_on_ten_metre_cells() -> None:
    offsets = rc.circle_offsets(5.0)
    assert len(offsets) == 81 and (0, 5) in offsets and (3, 4) in offsets and (4, 4) not in offsets
    assert rc.circle_offsets(0.0) == [(0, 0)]
    with pytest.raises(rc.RadarCandidateError):
        rc.circle_offsets(-1.0)


def test_focal_mean_uses_valid_cells_only() -> None:
    values = np.full((9, 9), 2.0)
    values[4, 4] = 1000.0
    valid = np.ones(values.shape, dtype=bool)
    valid[4, 4] = False
    mean = rc.focal_mean_circle(values, valid, 1.0)
    assert np.isnan(mean[4, 4])
    assert np.allclose(mean[valid], 2.0)
    values[0, 0] = 7.0
    mean = rc.focal_mean_circle(values, valid, 1.0)
    assert mean[0, 0] == pytest.approx((7.0 + 2.0 + 2.0) / 3.0)  # A corner has three cells in its circle.


def test_connected_groups_count_diagonal_neighbours() -> None:
    mask = np.zeros((12, 12), dtype=bool)
    for step in range(8):
        mask[step, step] = True  # Eight cells joined corner to corner.
    mask[10, 0:7] = True  # Seven cells in a row.
    kept = rc.keep_connected_groups(mask, 8)
    assert kept.sum() == 8 and kept[0, 0] and not kept[10].any()
    assert not rc.keep_connected_groups(np.zeros((4, 4), dtype=bool), 8).any()
    with pytest.raises(rc.RadarCandidateError):
        rc.keep_connected_groups(mask, 0)


def _un_spider_layers(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {
        "in_frame": np.ones(shape, dtype=bool),
        "permanent_water": np.zeros(shape, dtype=bool),
        "slope": np.zeros(shape),
    }


def test_un_spider_flags_a_quotient_above_one_point_two_five() -> None:
    shape = (30, 30)
    pre = np.full(shape, _linear(-16.0))
    post = pre.copy()
    post[2:8, 2:8] = _linear(-21.0)  # -21 / -16 = 1.3125: above the threshold.
    post[12:18, 2:8] = _linear(-19.0)  # -19 / -16 = 1.1875: below it.
    post[22:28, 2:8] = _linear(-11.0)  # Brighter: a quotient below one.
    candidate, reason, quotient, summary = rc.un_spider_candidate(
        pre, post, cell_m=10.0, config=NO_SMOOTHING, **_un_spider_layers(shape)
    )
    assert candidate[2:8, 2:8].all() and candidate.sum() == 36
    assert quotient[3, 3] == pytest.approx(1.3125) and quotient[13, 3] == pytest.approx(1.1875)
    assert (reason == rc.REASON_ANSWERED).all()
    assert summary["cells_above_threshold"] == summary["candidate_cells"] == 36
    assert summary["cells_above_threshold_with_positive_before_mean_db"] == 0
    assert summary["configuration"]["difference_threshold"] == 1.25
    assert summary["median_before_db"] == pytest.approx(-16.0)


def test_un_spider_smooths_in_db_inside_a_fifty_metre_circle() -> None:
    shape = (60, 60)
    pre = np.full(shape, _linear(-16.0))
    post = pre.copy()
    post[20:40, 20:40] = _linear(-22.0)
    post[5, 5] = _linear(-40.0)  # One very dark cell is averaged away.
    candidate, _, quotient, summary = rc.un_spider_candidate(
        pre, post, cell_m=10.0, **_un_spider_layers(shape)
    )
    assert summary["smoothing_radius_cells"] == 5.0 and summary["smoothing_kernel_cells"] == 81
    assert candidate[30, 30] == 1 and quotient[30, 30] == pytest.approx(22.0 / 16.0)
    assert candidate[5, 5] == 0
    assert quotient[5, 5] == pytest.approx((80 * -16.0 - 40.0) / 81 / -16.0)


def test_un_spider_removal_steps_run_in_the_order_of_the_practice() -> None:
    shape = (20, 40)
    pre = np.full(shape, _linear(-16.0))
    post = pre.copy()
    layers = _un_spider_layers(shape)
    # Group A: nine cells, two of them steep. The group survives the size rule first, then loses two cells.
    post[2:5, 2:5] = _linear(-22.0)
    layers["slope"][2, 2:4] = 9.0
    # Group B: nine cells, two of them perennial water. Seven are left before the size rule: all removed.
    post[2:5, 12:15] = _linear(-22.0)
    layers["permanent_water"][2, 12:14] = True
    # Group C: seven cells. Removed by the size rule.
    post[10, 2:9] = _linear(-22.0)
    # Group D: outside the area of interest.
    post[10:14, 30:34] = _linear(-22.0)
    layers["in_frame"][:, 28:] = False
    # A cell with a slope of exactly 5 is removed; the practice keeps slopes below 5 only.
    post[15:18, 2:5] = _linear(-22.0)
    layers["slope"][15, 2] = 5.0
    candidate, reason, _, summary = rc.un_spider_candidate(
        pre, post, cell_m=10.0, config=NO_SMOOTHING, **layers
    )
    assert candidate[2:5, 2:5].sum() == 7 and candidate[2, 2] == 0
    assert (reason[2, 2:4] == rc.REASON_REMOVED_SLOPE).all()
    assert candidate[2:5, 12:15].sum() == 0
    assert (reason[2, 12:14] == rc.REASON_REMOVED_PERMANENT_WATER).all()
    assert (reason[3:5, 12:15] == rc.REASON_REMOVED_SMALL_GROUP).all()
    assert (reason[10, 2:9] == rc.REASON_REMOVED_SMALL_GROUP).all()
    assert (candidate[:, 28:] == sar.CANDIDATE_ABSTAIN).all()
    assert (reason[:, 28:] == rc.REASON_OUTSIDE_FRAME).all()
    assert candidate[15:18, 2:5].sum() == 8 and reason[15, 2] == rc.REASON_REMOVED_SLOPE
    assert summary["cells_removed_as_perennial_water"] == 2
    assert summary["cells_removed_by_connected_pixel_rule"] == 14
    assert summary["cells_removed_by_slope_rule"] == 3
    assert summary["candidate_cells"] == 15 == int((candidate == 1).sum())


def test_un_spider_gives_no_answer_without_valid_radar_input() -> None:
    shape = (12, 12)
    pre = np.full(shape, _linear(-16.0))
    post = np.full(shape, _linear(-22.0))
    pre[0, 0] = np.nan
    post[0, 1] = 0.0
    candidate, reason, _, summary = rc.un_spider_candidate(
        pre, post, cell_m=10.0, config=NO_SMOOTHING, **_un_spider_layers(shape)
    )
    assert candidate[0, 0] == candidate[0, 1] == sar.CANDIDATE_ABSTAIN
    assert reason[0, 0] == reason[0, 1] == rc.REASON_NO_VALID_RADAR_INPUT
    assert summary["valid_cells"] == 142 and candidate[5, 5] == 1
    with pytest.raises(rc.RadarCandidateError, match="share one"):
        rc.un_spider_candidate(pre, post[:6], cell_m=10.0, **_un_spider_layers(shape))


def test_un_spider_counts_the_cells_where_the_db_quotient_changes_its_meaning() -> None:
    shape = (12, 12)
    pre = np.full(shape, _linear(-16.0))
    post = pre.copy()
    pre[2:6, 2:6] = _linear(2.0)  # Very bright before: a positive dB value.
    post[2:6, 2:6] = _linear(3.0)  # Brighter still, and 3 / 2 = 1.5 is above the threshold.
    candidate, _, quotient, summary = rc.un_spider_candidate(
        pre, post, cell_m=10.0, config=NO_SMOOTHING, **_un_spider_layers(shape)
    )
    assert quotient[3, 3] == pytest.approx(1.5) and candidate[3, 3] == 1
    assert summary["cells_with_positive_before_mean_db"] == 16
    assert summary["cells_above_threshold_with_positive_before_mean_db"] == 16


def test_un_spider_default_parameters_are_the_published_ones() -> None:
    config = rc.UnSpiderConfig()
    assert (config.polarisation, config.smoothing_radius_m, config.difference_threshold) == ("vh", 50.0, 1.25)
    assert (config.min_connected_cells, config.max_slope) == (8, 5.0)


# --- terrain --------------------------------------------------------------


def test_block_mean_and_slope() -> None:
    values = np.arange(36, dtype="float64").reshape(6, 6)
    assert rc.block_mean(values, 3).tolist() == [[7.0, 10.0], [25.0, 28.0]]
    assert rc.block_mean(values[:5, :4], 2).shape == (2, 2)
    columns = np.arange(10, dtype="float64")
    plane = np.broadcast_to(columns * 3.0, (8, 10))  # Rises 3 m per cell to the east.
    slope = rc.slope_degrees(plane, 30.0, 30.0)
    assert np.isnan(slope[0, 0]) and slope[4, 4] == pytest.approx(np.degrees(np.arctan(0.1)))
    per_row = rc.slope_degrees(plane, np.full(8, 60.0), 30.0)
    assert per_row[4, 4] == pytest.approx(np.degrees(np.arctan(0.05)))
    with pytest.raises(rc.RadarCandidateError):
        rc.slope_degrees(plane, 0.0, 30.0)


def test_slope_classes() -> None:
    classes, labels = rc.slope_classes(np.array([[0.0, 4.99, 5.0], [12.0, 25.0, np.nan]]), (5.0, 10.0, 20.0))
    assert classes.tolist() == [[0, 0, 1], [2, 3, 255]]
    assert labels == {
        0: "below_5_degrees", 1: "5_to_below_10_degrees", 2: "10_to_below_20_degrees", 3: "20_degrees_or_more",
    }
    with pytest.raises(rc.RadarCandidateError):
        rc.slope_classes(np.zeros((2, 2)), (5.0, 5.0))


# --- M1-literal and M1-v2 on tiles ---------------------------------------


def test_m1_literal_tile_is_the_frozen_function_with_nested_levels() -> None:
    pre, post, flooded = _flooded_tile(5)
    candidate, score, levels, summary = rc.m1_literal_tile(pre, post)
    expected, expected_summary = sar.m1_literal_predict(pre, post)
    assert np.array_equal(candidate, expected)
    assert summary["otsu_threshold_delta_vh_db"] == expected_summary["otsu_threshold_delta_vh_db"]
    assert np.array_equal(levels >= 2, candidate == 1)  # The central level is the method itself.
    cells = summary["threshold_levels"]["candidate_cells"]
    assert cells["-1_db"] <= cells["0_db"] <= cells["+1_db"]
    assert cells["0_db"] == expected_summary["candidate_cells"] == int((levels >= 2).sum())
    assert int((levels == 3).sum()) == cells["-1_db"] and int((levels >= 1).sum()) == cells["+1_db"]
    assert score.dtype == np.float32 and np.nanmedian(score[flooded]) < -6.0


def _frozen_config() -> sar.M1V2Config:
    return sar.m1_v2_config_from_json(review.require_frozen_m1_v2(ROOT)["parameters"])


def test_the_frozen_configuration_is_one_the_tile_runner_supports() -> None:
    binding = review.require_frozen_m1_v2(ROOT)
    config = _frozen_config()
    assert config.threshold_scope == "per_tile" and config.sides() == ("darkening",)
    assert config.block_pixels == 64 and config.threshold_method == "kittler_illingworth"
    assert len(binding["frozen_config_sha256"]) == 64 and set(binding["code_sha256"]) == {
        "src/floodguard/geoid_m1_benchmark.py", "src/floodguard/sar_change_v2.py",
    }


def test_m1_v2_tile_is_the_frozen_function_with_nested_levels() -> None:
    config = _frozen_config()
    pre, post, flooded = _flooded_tile(7)
    candidate, score, levels, summary = rc.m1_v2_tile(pre, post, config)
    expected, expected_summary = sar.m1_v2_predict({"tile": (pre, post)}, config)["tile"]
    assert np.array_equal(candidate, expected)
    assert summary["abstained"] is False and expected_summary["abstained"] is False
    assert summary["sides"] == expected_summary["sides"]
    assert np.array_equal(levels >= 2, candidate == 1)
    cells = summary["threshold_levels"]["candidate_cells"]
    assert cells["+1_db"] <= cells["0_db"] <= cells["-1_db"]  # A higher threshold is stricter.
    assert cells["0_db"] == expected_summary["candidate_cells"]
    assert int((levels == 3).sum()) == cells["+1_db"] and int((levels >= 1).sum()) == cells["-1_db"]
    assert np.nanmedian(score[flooded]) > 6.0  # The score is positive where the backscatter fell.
    assert (candidate[flooded] == 1).mean() > 0.9 and (candidate[~flooded] == 1).mean() < 0.02


def test_m1_v2_tile_declines_a_tile_without_change() -> None:
    config = _frozen_config()
    pre, post = _pair(np.random.default_rng(9), np.zeros((128, 128)))
    candidate, _, levels, summary = rc.m1_v2_tile(pre, post, config)
    assert summary["abstained"] is True and (candidate == sar.CANDIDATE_ABSTAIN).all()
    assert (levels == rc.LEVELS_NO_ANSWER).all()
    assert summary["threshold_levels"]["candidate_cells"] == {"+1_db": None, "0_db": None, "-1_db": None}


def test_m1_v2_tile_refuses_a_configuration_with_another_scope_or_side() -> None:
    pre, post, _ = _flooded_tile(7, size=64)
    with pytest.raises(rc.RadarCandidateError, match="per-tile scope"):
        rc.m1_v2_tile(pre, post, sar.M1V2Config(threshold_scope="pooled_run"))
    with pytest.raises(rc.RadarCandidateError, match="per-tile scope"):
        rc.m1_v2_tile(pre, post, sar.M1V2Config(direction="bidirectional"))


def test_nested_levels_refuses_extents_that_are_not_nested() -> None:
    answered = np.ones((2, 2), dtype=bool)
    strict = np.array([[True, False], [False, False]])
    loose = np.array([[False, True], [False, False]])
    with pytest.raises(rc.RadarCandidateError, match="not nested"):
        rc.nested_levels([strict, loose], answered)
    answered[1, 1] = False
    levels = rc.nested_levels([strict, strict | loose], answered)
    assert levels.tolist() == [[2, 1], [0, rc.LEVELS_NO_ANSWER]]


def test_tiles_are_run_one_at_a_time_and_put_back_on_the_grid() -> None:
    config = _frozen_config()
    size = 128
    flooded_pre, flooded_post, _ = _flooded_tile(7, size)
    quiet_pre, quiet_post = _pair(np.random.default_rng(9), np.zeros((size, size)))
    # A grid of one row and three tile columns; the third column is not run.
    pre = np.concatenate([flooded_pre, quiet_pre, quiet_pre], axis=2)
    post = np.concatenate([flooded_post, quiet_post, quiet_post], axis=2)
    pre[:, 0, 0] = np.nan
    pre[:, 0, size] = np.nan
    tiles = rc.lattice_tiles((0.0, 0.0, 2.0 * size * 10.0, size * 10.0), tile_cells=size, cell_m=10.0)
    assert [tile.name for tile in tiles] == ["E000N000", "E001N000"]
    candidate, reason, score, levels, summaries = rc.run_on_tiles(
        pre, post, tiles, lambda a, b: rc.m1_v2_tile(a, b, config),
        grid_west=0.0, grid_north=size * 10.0, cell_m=10.0,
    )
    alone, _, _, alone_summary = rc.m1_v2_tile(pre[:, :, :size], post[:, :, :size], config)
    assert np.array_equal(candidate[:, :size], alone)
    assert summaries["E000N000"]["sides"] == alone_summary["sides"]
    assert summaries["E000N000"]["abstained"] is False and summaries["E001N000"]["abstained"] is True
    assert reason[0, 0] == rc.REASON_NO_VALID_RADAR_INPUT and candidate[0, 0] == sar.CANDIDATE_ABSTAIN
    assert (reason[1:, :size] == rc.REASON_ANSWERED).all()
    assert reason[0, size] == rc.REASON_NO_VALID_RADAR_INPUT
    assert (reason[1:, size : 2 * size] == rc.REASON_METHOD_DECLINED).all()
    assert (reason[:, 2 * size :] == rc.REASON_OUTSIDE_FRAME).all()
    assert (candidate[:, size:] == sar.CANDIDATE_ABSTAIN).all()
    assert np.isnan(score[:, 2 * size :]).all() and (levels[:, size:] == rc.LEVELS_NO_ANSWER).all()

    frame = np.zeros(candidate.shape, dtype=bool)
    frame[:, 10 : size + 10] = True
    clipped, reasons, clipped_levels = rc.restrict_to_frame(candidate, reason, levels, frame)
    assert (clipped[:, :10] == sar.CANDIDATE_ABSTAIN).all() and (reasons[:, :10] == rc.REASON_OUTSIDE_FRAME).all()
    assert np.array_equal(clipped[:, 10:size], candidate[:, 10:size])
    assert clipped_levels is not None and (clipped_levels[:, :10] == rc.LEVELS_NO_ANSWER).all()

    with pytest.raises(rc.RadarCandidateError, match="outside the grid"):
        rc.run_on_tiles(pre[:, :, :size], post[:, :, :size], tiles, lambda a, b: rc.m1_v2_tile(a, b, config),
                        grid_west=0.0, grid_north=size * 10.0, cell_m=10.0)


# --- counting per unit ----------------------------------------------------


def _unit_layers() -> dict[str, np.ndarray]:
    unit_index = np.zeros((4, 10), dtype="uint8")
    unit_index[:, 0:5] = 1
    unit_index[:, 5:9] = 2  # The last column lies in no unit.
    candidate = np.zeros((4, 10), dtype="uint8")
    reason = np.zeros((4, 10), dtype="uint8")
    candidate[0, 0:3] = 1
    candidate[:, 5:8] = sar.CANDIDATE_ABSTAIN  # Unit 2: three of four columns declined.
    reason[:, 5:8] = rc.REASON_METHOD_DECLINED
    candidate[3, 4] = sar.CANDIDATE_ABSTAIN  # Unit 1: one cell without radar input.
    reason[3, 4] = rc.REASON_NO_VALID_RADAR_INPUT
    candidate[:, 9] = sar.CANDIDATE_ABSTAIN
    reason[:, 9] = rc.REASON_OUTSIDE_FRAME
    valid_input = np.ones((4, 10), dtype=bool)
    valid_input[3, 4] = False
    permanent_water = np.zeros((4, 10), dtype=bool)
    permanent_water[0, 0] = True
    return {
        "candidate": candidate, "reason": reason, "unit_index": unit_index,
        "valid_input": valid_input, "permanent_water": permanent_water,
    }


def test_unit_rows_give_coverage_abstention_and_area() -> None:
    layers = _unit_layers()
    rows = rc.unit_rows(
        layers["candidate"], layers["reason"], layers["unit_index"], ["U1", "U2"], cell_area_km2=0.0001,
        valid_input=layers["valid_input"], permanent_water=layers["permanent_water"],
        coverage_min=0.8, abstention_max=0.2,
    )
    first, second = rows
    assert first["cells"] == 20 and first["area_km2"] == 0.002
    assert first["answered_cells"] == 19 and first["cells_without_an_answer"] == 1
    assert first["input_coverage"] == first["answer_coverage"] == 0.95 and first["abstention_fraction"] == 0.05
    assert first["answer_coverage_at_least_min"] and first["abstention_at_most_max"]
    assert first["low_confidence_reason_codes"] == []
    assert first["candidate_cells"] == 3 and first["candidate_area_km2"] == 0.0003
    assert first["candidate_cells_outside_permanent_water"] == 2 and first["permanent_water_cells"] == 1
    assert first["candidate_share_of_answered_cells"] == round(3 / 19, 6)
    assert second["cells"] == 16 and second["input_coverage"] == 1.0
    assert second["answer_coverage"] == 0.25 and second["abstention_fraction"] == 0.75
    assert second["input_coverage_at_least_min"] and not second["answer_coverage_at_least_min"]
    assert not second["abstention_at_most_max"]
    assert second["low_confidence_reason_codes"] == ["method_declined_for_the_tile"]
    assert second["cells_without_an_answer_by_reason"] == {
        "method_declined_for_the_tile": 12, "no_valid_radar_input": 0,
    }
    assert first["answer_coverage"] + first["abstention_fraction"] == pytest.approx(1.0)

    totals = rc.frame_totals(rows, cell_area_km2=0.0001)
    assert totals["cells"] == 36 and totals["answered_cells"] == 23
    assert totals["abstention_fraction"] == round(13 / 36, 6)
    assert totals["units"] == 2 and totals["units_with_answer_coverage_at_least_min"] == 1
    assert totals["units_with_input_coverage_at_least_min"] == 2 and totals["units_with_abstention_at_most_max"] == 1
    assert totals["candidate_area_km2"] == 0.0003


def test_unit_rows_refuse_a_unit_with_no_cell_and_an_unlisted_unit() -> None:
    layers = _unit_layers()
    arguments = dict(
        cell_area_km2=0.0001, valid_input=layers["valid_input"], permanent_water=layers["permanent_water"],
        coverage_min=0.8, abstention_max=0.2,
    )
    with pytest.raises(rc.RadarCandidateError, match="no cell"):
        rc.unit_rows(layers["candidate"], layers["reason"], layers["unit_index"], ["U1", "U2", "U3"], **arguments)
    with pytest.raises(rc.RadarCandidateError, match="not listed"):
        rc.unit_rows(layers["candidate"], layers["reason"], layers["unit_index"], ["U1"], **arguments)


def test_level_and_strata_areas() -> None:
    layers = _unit_layers()
    levels = np.zeros((4, 10), dtype="uint8")
    levels[0, 0:3] = 2
    levels[0, 0] = 3
    levels[1, 0:2] = 1
    levels[layers["candidate"] == sar.CANDIDATE_ABSTAIN] = rc.LEVELS_NO_ANSWER
    areas = rc.level_areas(levels, layers["unit_index"], ["U1", "U2"], cell_area_km2=0.0001)
    assert areas["units_km2"]["U1"] == {"strictest": 0.0001, "central": 0.0003, "loosest": 0.0005}
    assert areas["units_km2"]["U2"] == {"strictest": 0.0, "central": 0.0, "loosest": 0.0}
    assert areas["frame_km2"] == {"strictest": 0.0001, "central": 0.0003, "loosest": 0.0005}

    classes = np.full((4, 10), 40, dtype="uint8")
    classes[0, 0] = 80
    classes[3, 0] = 99
    rows = rc.strata_areas(
        layers["candidate"], layers["unit_index"] > 0, classes, {40: "cropland", 80: "permanent_water"},
        cell_area_km2=0.0001,
    )
    by_class = {row["class"]: row for row in rows}
    assert by_class["permanent_water"]["candidate_cells"] == 1 and by_class["cropland"]["candidate_cells"] == 2
    assert by_class["cropland"]["frame_cells"] == 34 and by_class["cropland"]["answered_cells"] == 21
    assert by_class["other_or_no_value"]["frame_cells"] == 1
    assert sum(row["frame_cells"] for row in rows) == 36


def test_flood_input_names_are_the_ones_protocol_v1a_uses() -> None:
    import json

    v1a = json.loads((ROOT / "docs/proposal_execution/planning_protocol_v1a.json").read_text(encoding="utf-8"))
    named = set(v1a["t2_skill_bar"]["declared_unable_to_meet"]) | set(v1a["t2_skill_bar"]["evaluated_by_the_rule"])
    assert set(rc.FLOOD_INPUT_NAMES.values()) <= named
    assert rc.FLOOD_INPUT_NAMES["m1_v2"] in v1a["t2_skill_bar"]["evaluated_by_the_rule"]
    case = next(case for case in v1a["case_portfolio"]["cases"] if case["id"] == "O1")
    assert set(rc.FLOOD_INPUT_NAMES.values()) <= set(case["flood_inputs"])


def test_the_below_zero_clause_cuts_the_plus_level_of_m1_literal() -> None:
    # An Otsu threshold of -1 dB or lower: the +1 dB level is the threshold moved by a full dB.
    low = rc.literal_level_cut(-1.9)
    assert low["plus_level"] == rc.PLUS_LEVEL_FULL_SHIFT and low["plus_level_shift_that_took_effect_db"] == 1.0
    assert low["effective_threshold_db"] == {"-1_db": -2.9, "0_db": -1.9, "+1_db": -0.9}
    assert low["cut_at_0_db"] == {"-1_db": False, "0_db": False, "+1_db": False}
    edge = rc.literal_level_cut(-1.0)
    assert edge["plus_level"] == rc.PLUS_LEVEL_FULL_SHIFT and edge["effective_threshold_db"]["+1_db"] == 0.0
    # Between -1 and 0 dB the moved threshold is above 0 dB and the clause cuts it there.
    middle = rc.literal_level_cut(-0.2)
    assert middle["plus_level"] == rc.PLUS_LEVEL_CUT and middle["plus_level_shift_that_took_effect_db"] == 0.2
    assert middle["effective_threshold_db"]["+1_db"] == 0.0 and middle["cut_at_0_db"]["+1_db"] is True
    # At 0 dB or more the central level is itself cut at 0 dB, and the +1 dB level is the same extent.
    for threshold in (0.0, 0.1):
        high = rc.literal_level_cut(threshold)
        assert high["plus_level"] == rc.PLUS_LEVEL_SAME_AS_CENTRAL
        assert high["plus_level_shift_that_took_effect_db"] == 0.0
        assert high["effective_threshold_db"]["0_db"] == high["effective_threshold_db"]["+1_db"] == 0.0
    assert rc.literal_level_cut(0.1)["cut_at_0_db"] == {"-1_db": False, "0_db": True, "+1_db": True}
    assert rc.literal_level_cut(None)["plus_level"] is None
    assert "below 0 dB" in low["below_zero_clause"]


def test_m1_literal_tile_says_which_level_the_clause_cut() -> None:
    pre, post, _ = _flooded_tile(5)
    _, _, _, summary = rc.m1_literal_tile(pre, post)
    block = summary["threshold_levels"]
    threshold = summary["otsu_threshold_delta_vh_db"]
    assert block["effective_threshold_db"]["+1_db"] == round(min(threshold + 1.0, 0.0), 4)
    assert block == {**block, **rc.literal_level_cut(threshold)}

    # A tile without change has an Otsu threshold near 0 dB: the +1 dB level is cut there, and where the
    # threshold is 0 dB or more the +1 dB level is the central level again, cell for cell.
    flat_pre, flat_post = _pair(np.random.default_rng(13), np.zeros((128, 128)))
    _, _, levels, flat = rc.m1_literal_tile(flat_pre, flat_post)
    cut = flat["threshold_levels"]
    assert flat["otsu_threshold_delta_vh_db"] > -1.0
    assert cut["plus_level"] in (rc.PLUS_LEVEL_CUT, rc.PLUS_LEVEL_SAME_AS_CENTRAL)
    assert cut["plus_level_shift_that_took_effect_db"] < 1.0 and cut["cut_at_0_db"]["+1_db"] is True
    if cut["plus_level"] == rc.PLUS_LEVEL_SAME_AS_CENTRAL:
        assert cut["candidate_cells"]["+1_db"] == cut["candidate_cells"]["0_db"]
        assert not (levels == 1).any()  # No cell is a candidate at the loosest level only.
