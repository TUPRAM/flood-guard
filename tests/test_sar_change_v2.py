"""Synthetic-array tests for M1-literal and M1-v2 (no external data)."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard import sar_change_v2 as sar

SPEC = sar.HistogramSpec()


def _speckle(rng: np.random.Generator, mean: np.ndarray, looks: float = 4.4) -> np.ndarray:
    """Multiplicative gamma speckle with the given number of looks."""

    return mean * rng.gamma(looks, 1.0 / looks, size=mean.shape)


def _pair(
    rng: np.random.Generator,
    shape: tuple[int, int],
    change_db: np.ndarray,
    base: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Speckled pre and post images; ``change_db`` is post minus pre in dB."""

    flat = np.full(shape, base)
    pre = np.stack([_speckle(rng, flat), _speckle(rng, flat * 0.25)])
    factor = 10.0 ** (change_db / 10.0)
    post = np.stack([_speckle(rng, flat * factor), _speckle(rng, flat * 0.25 * factor)])
    return pre.astype("float32"), post.astype("float32")


# --- radiometry -----------------------------------------------------------


@pytest.mark.parametrize(
    ("pre_shape", "post_shape"),
    [((8, 8), (8, 8)), ((1, 8, 8), (1, 8, 8)), ((2, 8, 8), (2, 7, 8)), ((2, 0, 8), (2, 0, 8))],
)
def test_valid_radiometry_rejects_wrong_shapes(
    pre_shape: tuple[int, ...], post_shape: tuple[int, ...]
) -> None:
    with pytest.raises(sar.SarChangeError, match="shape"):
        sar.valid_radiometry(np.ones(pre_shape), np.ones(post_shape))


def test_valid_radiometry_flags_unusable_cells() -> None:
    pre = np.full((2, 4, 4), 0.1)
    post = pre.copy()
    pre[0, 0, 0] = np.nan
    pre[1, 0, 1] = np.inf
    post[0, 0, 2] = 0.0
    post[1, 0, 3] = -1.0
    valid = sar.valid_radiometry(pre, post)
    assert not valid[0].any()
    assert valid[1:].all()


# --- Lee and refined-Lee --------------------------------------------------


@pytest.mark.parametrize("name", ["lee", "refined"])
def test_filters_leave_a_constant_image_unchanged(name: str) -> None:
    image = np.full((24, 24), 0.2)
    valid = np.ones(image.shape, dtype=bool)
    out = sar.lee_filter(image, valid) if name == "lee" else sar.refined_lee_filter(image, valid)
    assert np.allclose(out, 0.2)


@pytest.mark.parametrize("name", ["lee", "refined"])
def test_filters_reduce_speckle_and_keep_the_mean(name: str) -> None:
    rng = np.random.default_rng(1)
    image = _speckle(rng, np.full((128, 128), 0.1))
    valid = np.ones(image.shape, dtype=bool)
    out = sar.lee_filter(image, valid) if name == "lee" else sar.refined_lee_filter(image, valid)
    assert out.shape == image.shape
    assert out.mean() == pytest.approx(image.mean(), rel=0.03)
    assert out.std() < image.std() / 2
    assert (out > 0).all()


@pytest.mark.parametrize("name", ["lee", "refined"])
def test_filters_keep_invalid_cells_out_of_neighbours(name: str) -> None:
    image = np.full((20, 20), 0.2)
    image[10, 10] = 1e9
    valid = np.ones(image.shape, dtype=bool)
    valid[10, 10] = False
    out = sar.lee_filter(image, valid) if name == "lee" else sar.refined_lee_filter(image, valid)
    assert np.isnan(out[10, 10])
    assert np.allclose(out[valid], 0.2)


@pytest.mark.parametrize("transpose", [False, True])
def test_refined_lee_preserves_a_step_edge(transpose: bool) -> None:
    rng = np.random.default_rng(2)
    mean = np.full((96, 96), 0.02)
    mean[:, 48:] = 0.2
    image = _speckle(rng, mean)
    if transpose:
        image = image.T.copy()
    valid = np.ones(image.shape, dtype=bool)
    refined = sar.refined_lee_filter(image, valid)
    boxcar = np.zeros_like(image)
    padded = np.pad(image, 3, mode="edge")
    for row in range(7):
        for column in range(7):
            boxcar += padded[row : row + 96, column : column + 96]
    boxcar /= 49
    # The last dark line before the edge: a 7 by 7 boxcar mixes in the bright
    # side, the refined filter averages along the edge instead.
    dark_refined = refined[47, 8:-8] if transpose else refined[8:-8, 47]
    dark_boxcar = boxcar[47, 8:-8] if transpose else boxcar[8:-8, 47]
    assert dark_boxcar.mean() > 3 * 0.02
    assert dark_refined.mean() < 2 * 0.02
    bright_refined = refined[48, 8:-8] if transpose else refined[8:-8, 48]
    assert bright_refined.mean() > 0.7 * 0.2


def test_refined_lee_preserves_a_diagonal_edge() -> None:
    rng = np.random.default_rng(3)
    rows, columns = np.indices((96, 96))
    mean = np.where(columns > rows, 0.2, 0.02)
    refined = sar.refined_lee_filter(_speckle(rng, mean), np.ones(mean.shape, dtype=bool))
    inner = slice(10, 86)
    just_dark = refined[inner, inner][np.eye(76, k=0, dtype=bool)]
    just_bright = refined[inner, inner][np.eye(76, k=1, dtype=bool)]
    assert just_dark.mean() < 2 * 0.02
    assert just_bright.mean() > 0.7 * 0.2


def test_half_windows_have_28_cells_and_contain_the_centre() -> None:
    windows = sar._half_window_offsets()
    assert len(windows) == 8
    for offsets in windows:
        assert len(offsets) == 28
        assert (0, 0) in offsets
    assert all(column <= 0 for _, column in windows[0])
    assert all(row <= 0 for row, _ in windows[2])


def test_filters_reject_bad_arguments() -> None:
    image = np.ones((8, 8))
    valid = np.ones((8, 8), dtype=bool)
    with pytest.raises(sar.SarChangeError):
        sar.lee_filter(image, valid, window_pixels=4)
    with pytest.raises(sar.SarChangeError):
        sar.lee_filter(image, valid[:4])
    with pytest.raises(sar.SarChangeError):
        sar.refined_lee_filter(image, valid, equivalent_looks=0)
    with pytest.raises(sar.SarChangeError):
        sar.refined_lee_filter(np.ones((2, 8, 8)), valid)
    with pytest.raises(sar.SarChangeError, match="speckle"):
        sar.filter_pair(np.ones((2, 8, 8)), np.ones((2, 8, 8)), speckle_filter="median")


# --- Ashman D, Otsu, Kittler-Illingworth, mixture fit ----------------------


def test_ashman_d_known_values() -> None:
    assert sar.ashman_d(0.0, 1.0, 4.0, 1.0) == pytest.approx(4.0)
    assert sar.ashman_d(0.0, 1.0, 2.0, 1.0) == pytest.approx(2.0)
    assert sar.ashman_d(3.0, 3.0, 0.0, 4.0) == pytest.approx(np.sqrt(2.0) * 3.0 / 5.0)
    assert sar.ashman_d(1.0, 0.0, 1.0, 0.0) == 0.0
    assert sar.ashman_d(1.0, 0.0, 2.0, 0.0) == float("inf")
    with pytest.raises(sar.SarChangeError):
        sar.ashman_d(0.0, -1.0, 1.0, 1.0)


def test_otsu_splits_two_spikes_and_symmetric_modes() -> None:
    counts = np.zeros(SPEC.bins, dtype="int64")
    counts[200] = 500  # centre -4.95 dB
    counts[300] = 500  # centre 5.05 dB
    threshold = sar.otsu_threshold(counts, SPEC)
    assert threshold is not None and -4.9 <= threshold <= 5.0
    rng = np.random.default_rng(4)
    sample = np.concatenate([rng.normal(-3, 1, 20000), rng.normal(5, 1, 20000)])
    # The criterion is nearly flat across the empty gap between the modes.
    assert sar.otsu_threshold(sar.histogram_db(sample, SPEC), SPEC) == pytest.approx(1.0, abs=1.0)


def test_thresholds_return_none_without_two_occupied_bins() -> None:
    counts = np.zeros(SPEC.bins, dtype="int64")
    assert sar.otsu_threshold(counts, SPEC) is None
    counts[100] = 10
    assert sar.otsu_threshold(counts, SPEC) is None
    assert sar.kittler_illingworth_threshold(counts, SPEC) is None
    assert sar.fit_two_gaussians(counts, SPEC) is None
    with pytest.raises(sar.SarChangeError):
        sar.otsu_threshold(counts[:10], SPEC)
    with pytest.raises(sar.SarChangeError):
        sar.kittler_illingworth_threshold(counts, SPEC, min_class_fraction=0.6)


def test_kittler_illingworth_is_closer_to_the_minimum_error_point_than_otsu() -> None:
    rng = np.random.default_rng(5)
    sample = np.concatenate([rng.normal(0.0, 1.0, 90000), rng.normal(8.0, 2.0, 10000)])
    counts = sar.histogram_db(sample, SPEC)
    # Minimum-error threshold: 0.9 N(t; 0, 1) = 0.1 N(t; 8, 2), between the means.
    grid = np.linspace(0.0, 8.0, 80001)
    low = 0.9 * np.exp(-0.5 * grid**2)
    high = 0.1 / 2.0 * np.exp(-0.5 * ((grid - 8.0) / 2.0) ** 2)
    optimum = float(grid[np.argmin(np.abs(low - high))])
    kittler = sar.kittler_illingworth_threshold(counts, SPEC)
    otsu = sar.otsu_threshold(counts, SPEC)
    assert kittler is not None and otsu is not None
    assert abs(kittler - optimum) < 0.3
    assert abs(kittler - optimum) < abs(otsu - optimum)


def test_kittler_illingworth_respects_the_minimum_class_fraction() -> None:
    counts = np.zeros(SPEC.bins, dtype="int64")
    counts[250] = 995
    counts[400] = 5
    assert sar.kittler_illingworth_threshold(counts, SPEC, min_class_fraction=0.01) is None
    assert sar.kittler_illingworth_threshold(counts, SPEC, min_class_fraction=0.001) is not None


def test_kittler_illingworth_edge_value_is_not_an_interior_minimum() -> None:
    """Overlapping classes: the free search runs to the edge of its range."""

    rng = np.random.default_rng(30)
    overlapping = np.concatenate([rng.normal(0.0, 2.4, 170000), rng.normal(5.5, 2.4, 30000)])
    counts = sar.histogram_db(overlapping, SPEC)
    fit = sar.fit_two_gaussians(counts, SPEC)
    assert fit is not None
    free = sar.kittler_illingworth_threshold(counts, SPEC)
    # The free result sits where the upper class shrinks to the 1 percent floor.
    assert free == pytest.approx(float(np.quantile(overlapping, 0.99)), abs=0.3)
    between = (fit.mean_low, fit.mean_high)
    assert sar.kittler_illingworth_threshold(counts, SPEC, interior_between_db=between) is None
    for method, expected_none in (("kittler_illingworth", True), ("otsu", False)):
        config = sar.M1V2Config(threshold_method=method)
        assert (sar.threshold_from_histogram(counts, config) is None) is expected_none

    separated = np.concatenate([rng.normal(0.0, 2.0, 160000), rng.normal(6.0, 2.0, 40000)])
    counts = sar.histogram_db(separated, SPEC)
    fit = sar.fit_two_gaussians(counts, SPEC)
    assert fit is not None
    between = (fit.mean_low, fit.mean_high)
    interior = sar.kittler_illingworth_threshold(counts, SPEC, interior_between_db=between)
    assert interior == sar.kittler_illingworth_threshold(counts, SPEC)
    assert fit.mean_low < interior < fit.mean_high
    assert sar.threshold_from_histogram(counts, sar.M1V2Config()) == interior
    assert sar.kittler_illingworth_threshold(counts, SPEC, interior_between_db=(8.0, 9.0)) is None
    assert sar.M1V2Config().kittler_illingworth_rule == "interior_minimum_between_fitted_modes"


def test_mixture_fit_recovers_two_modes_and_rejects_one_mode() -> None:
    rng = np.random.default_rng(6)
    two = np.concatenate([rng.normal(0.0, 1.2, 12000), rng.normal(7.0, 1.5, 4000)])
    fit = sar.fit_two_gaussians(sar.histogram_db(two, SPEC), SPEC)
    assert fit is not None
    assert fit.mean_low == pytest.approx(0.0, abs=0.1)
    assert fit.mean_high == pytest.approx(7.0, abs=0.15)
    assert fit.std_low == pytest.approx(1.2, abs=0.1)
    assert fit.weight_high == pytest.approx(0.25, abs=0.02)
    assert fit.ashman_d > 2
    for spread in (1.0, 2.5):
        one = rng.normal(0.5, spread, 16000)
        single = sar.fit_two_gaussians(sar.histogram_db(one, SPEC), SPEC)
        assert single is not None and single.ashman_d < 2


def test_truncated_halves_of_one_gaussian_would_pass_ashman_d() -> None:
    """Why the mixture is fitted: split halves look bimodal when they are not."""

    rng = np.random.default_rng(7)
    one = rng.normal(0.0, 2.0, 200000)
    low, high = one[one < 0], one[one >= 0]
    assert sar.ashman_d(low.mean(), low.std(), high.mean(), high.std()) > 2.5
    fit = sar.fit_two_gaussians(sar.histogram_db(one, SPEC), SPEC)
    assert fit is not None and fit.ashman_d < 2


def test_block_is_bimodal_reasons() -> None:
    def fit(**changes: float) -> sar.TwoGaussianFit:
        values = dict(
            weight_low=0.7, mean_low=0.2, std_low=1.0, weight_high=0.3, mean_high=7.0, std_high=1.5
        )
        values.update(changes)
        return sar.TwoGaussianFit(**values)

    rule = dict(ashman_d_min=2.0, min_component_weight=0.1)
    assert sar.block_is_bimodal(fit(), **rule) == (True, None)
    assert sar.block_is_bimodal(None, **rule)[1] == "no_two_component_fit"
    assert sar.block_is_bimodal(fit(mean_high=1.5), **rule)[1] == "ashman_d_not_above_minimum"
    assert (
        sar.block_is_bimodal(fit(weight_low=0.95, weight_high=0.05), **rule)[1]
        == "component_weight_below_minimum"
    )
    assert (
        sar.block_is_bimodal(fit(mean_low=-8.0, mean_high=-0.5), **rule)[1]
        == "upper_component_is_not_a_change_in_this_direction"
    )
    assert (
        sar.block_is_bimodal(fit(mean_low=-9.0, mean_high=1.0), **rule)[1]
        == "lower_component_is_not_the_unchanged_one"
    )


def test_select_bimodal_blocks_keeps_only_the_mixed_block() -> None:
    rng = np.random.default_rng(8)
    score = rng.normal(0.0, 1.0, (128, 128))
    score[:64, :32] = rng.normal(8.0, 1.0, (64, 32))  # half of the first block changed
    valid = np.ones(score.shape, dtype=bool)
    valid[64:, 64:] = False
    config = sar.M1V2Config(block_pixels=64)
    pooled, receipts = sar.select_bimodal_blocks(score, valid, config)
    assert [receipt["selected"] for receipt in receipts] == [True, False, False, False]
    assert receipts[3]["reason"] == "too_few_valid_cells"
    assert receipts[1]["reason"] == "ashman_d_not_above_minimum"
    assert np.array_equal(pooled, sar.histogram_db(score[:64, :64], SPEC))
    threshold = sar.threshold_from_histogram(pooled, config)
    assert threshold == pytest.approx(4.0, abs=0.6)


def test_threshold_from_histogram_refuses_a_non_positive_threshold() -> None:
    rng = np.random.default_rng(9)
    sample = np.concatenate([rng.normal(-8.0, 1.0, 5000), rng.normal(-1.0, 1.0, 5000)])
    counts = sar.histogram_db(sample, SPEC)
    for method in sar.THRESHOLD_METHODS:
        config = sar.M1V2Config(threshold_method=method)
        assert sar.threshold_from_histogram(counts, config) is None
        assert sar.threshold_from_histogram(np.zeros(SPEC.bins, dtype="int64"), config) is None


def test_majority_filter_removes_isolated_cells_and_never_adds() -> None:
    flags = np.zeros((9, 9), dtype=bool)
    flags[1, 1] = True  # isolated
    flags[4:7, 4:7] = True  # solid 3 by 3
    valid = np.ones(flags.shape, dtype=bool)
    cleaned = sar.majority_filter(flags, valid)
    assert not cleaned[1, 1]
    assert cleaned[5, 5] and cleaned[4, 5] and cleaned[5, 4]
    assert not cleaned[4, 4]  # a corner has only 4 of 9
    assert not (cleaned & ~flags).any()
    valid[5, 5] = False
    assert not sar.majority_filter(flags, valid)[5, 5]


# --- M1-literal -------------------------------------------------------------


def test_m1_literal_flags_strong_darkening_only() -> None:
    rng = np.random.default_rng(10)
    change = np.zeros((128, 128))
    change[:, :48] = -9.0  # flooded: strong darkening
    change[:, 100:] = 6.0  # brightening must never be a candidate
    pre, post = _pair(rng, change.shape, change)
    pre[0, 5, 60] = np.nan
    post[1, 6, 60] = 0.0
    candidate, summary = sar.m1_literal_predict(pre, post)
    truth = change < 0
    predicted = candidate == sar.CANDIDATE_YES
    iou = (predicted & truth).sum() / (predicted | truth).sum()
    assert candidate.dtype == np.uint8
    assert iou > 0.9
    assert not predicted[:, 100:].any()
    assert candidate[5, 60] == sar.CANDIDATE_ABSTAIN and candidate[6, 60] == sar.CANDIDATE_ABSTAIN
    assert summary["invalid_cells"] == 2 and not summary["abstained"]
    assert summary["otsu_threshold_delta_vh_db"] < 0
    assert summary["median_vv_vh_ratio_db_pre"] == pytest.approx(6.0, abs=0.5)
    assert summary["configuration"]["speckle_window_pixels"] == 5


def test_m1_literal_has_no_quality_gate() -> None:
    """Otsu always splits: an unchanged image still yields candidates."""

    rng = np.random.default_rng(11)
    pre, post = _pair(rng, (96, 96), np.zeros((96, 96)))
    candidate, summary = sar.m1_literal_predict(pre, post)
    assert not summary["abstained"]
    assert (candidate != sar.CANDIDATE_ABSTAIN).all()


def test_m1_literal_abstains_only_without_any_valid_cell() -> None:
    pre = np.zeros((2, 16, 16))
    candidate, summary = sar.m1_literal_predict(pre, pre)
    assert (candidate == sar.CANDIDATE_ABSTAIN).all()
    assert summary["abstained"] and summary["candidate_cells"] == 0


# --- M1-v2 --------------------------------------------------------------------


def _flooded_and_dry(rng: np.random.Generator) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    change = np.zeros((128, 128))
    change[:40, :] = -9.0
    change[100:, 90:] = 7.0
    return {
        "flooded": _pair(rng, change.shape, change),
        "dry": _pair(rng, (128, 128), np.zeros((128, 128))),
    }


def test_m1_v2_per_tile_detects_flood_and_abstains_on_an_unchanged_image() -> None:
    rng = np.random.default_rng(12)
    pairs = _flooded_and_dry(rng)
    config = sar.M1V2Config(channel="vh", direction="darkening", block_pixels=64)
    results = sar.m1_v2_predict(pairs, config)
    candidate, summary = results["flooded"]
    truth = np.zeros((128, 128), dtype=bool)
    truth[:40, :] = True
    predicted = candidate == sar.CANDIDATE_YES
    assert (predicted & truth).sum() / (predicted | truth).sum() > 0.9
    assert summary["active_sides"] == ["darkening"]
    assert summary["sides"]["darkening"]["selected_blocks"] == 2
    assert 2.0 < summary["sides"]["darkening"]["threshold_db"] < 7.0
    dry_candidate, dry_summary = results["dry"]
    assert dry_summary["abstained"]
    assert (dry_candidate == sar.CANDIDATE_ABSTAIN).all()
    assert dry_summary["sides"]["darkening"]["selected_blocks"] == 0


def test_m1_v2_pooled_scope_shares_one_threshold() -> None:
    rng = np.random.default_rng(13)
    pairs = _flooded_and_dry(rng)
    config = sar.M1V2Config(block_pixels=64, threshold_scope="pooled_run")
    results = sar.m1_v2_predict(pairs, config)
    flooded_threshold = results["flooded"][1]["sides"]["darkening"]["threshold_db"]
    assert results["dry"][1]["sides"]["darkening"]["threshold_db"] == flooded_threshold
    assert not results["dry"][1]["abstained"]
    assert (results["dry"][0] == sar.CANDIDATE_YES).mean() < 0.01
    alone = sar.m1_v2_predict({"dry": pairs["dry"]}, config)
    assert alone["dry"][1]["abstained"]


def test_m1_v2_bidirectional_adds_brightening() -> None:
    rng = np.random.default_rng(14)
    pairs = {"flooded": _flooded_and_dry(rng)["flooded"]}
    dark = sar.m1_v2_predict(pairs, sar.M1V2Config(block_pixels=64))["flooded"][0]
    both_candidate, both_summary = sar.m1_v2_predict(
        pairs, sar.M1V2Config(block_pixels=64, direction="bidirectional")
    )["flooded"]
    bright_region = np.s_[104:124, 94:124]
    assert (dark[bright_region] == sar.CANDIDATE_YES).mean() < 0.02
    assert (both_candidate[bright_region] == sar.CANDIDATE_YES).mean() > 0.9
    assert both_summary["active_sides"] == ["darkening", "brightening"]


@pytest.mark.parametrize("channel", sar.CHANNELS)
@pytest.mark.parametrize("method", sar.THRESHOLD_METHODS)
def test_m1_v2_every_channel_and_threshold_method_runs(channel: str, method: str) -> None:
    rng = np.random.default_rng(15)
    pairs = {"flooded": _flooded_and_dry(rng)["flooded"]}
    config = sar.M1V2Config(channel=channel, threshold_method=method, block_pixels=64)
    candidate, summary = sar.m1_v2_predict(pairs, config)["flooded"]
    assert not summary["abstained"]
    assert (candidate[:36, :] == sar.CANDIDATE_YES).mean() > 0.9


def test_m1_v2_reused_block_selection_gives_the_same_result() -> None:
    rng = np.random.default_rng(16)
    pairs = _flooded_and_dry(rng)
    config = sar.M1V2Config(block_pixels=64, direction="bidirectional")
    filtered = {
        name: sar.filter_pair(pre, post, speckle_filter=config.speckle_filter)
        for name, (pre, post) in pairs.items()
    }
    selections = {
        name: {side: sar.select_blocks_for_side(pair, config, side) for side in config.sides()}
        for name, pair in filtered.items()
    }
    direct = sar.m1_v2_predict_filtered(filtered, config)
    reused = sar.m1_v2_predict_filtered(filtered, config, selections=selections)
    for name in pairs:
        assert np.array_equal(direct[name][0], reused[name][0])
        assert direct[name][1] == reused[name][1]


def test_m1_v2_config_validation_and_round_trip() -> None:
    for bad in (
        dict(channel="hh"),
        dict(direction="up"),
        dict(threshold_scope="scene"),
        dict(threshold_method="mean"),
        dict(block_pixels=8),
        dict(equivalent_looks=0.0),
    ):
        with pytest.raises(sar.SarChangeError):
            sar.M1V2Config(**bad)
    config = sar.M1V2Config(channel="vv", direction="bidirectional", block_pixels=256)
    assert sar.m1_v2_config_from_json(sar.config_to_json(config)) == config
    assert config.sides() == ("darkening", "brightening")
    with pytest.raises(sar.SarChangeError):
        sar.change_score(
            sar.FilteredPair(np.zeros((2, 2, 2)), np.zeros((2, 2, 2)), np.ones((2, 2), bool)),
            "vv",
            "sideways",
        )
