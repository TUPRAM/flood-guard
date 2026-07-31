"""Tests for the temporal SAR baseline and deviation detection (T1.2).

The synthetic series here is built to encode the physics the method relies on:
a stable land background, a seasonal offset that a naive annual baseline would
mistake for flooding, historical flood dates hiding inside the archive, and one
event date to detect. If the implementation ever regresses to a mean/std
baseline or to unbinned statistics, these tests fail.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from geoai_runner.realpipeline.sar_temporal import (
    SEASON_BINS_MONTHLY,
    SEASON_BINS_WET_DRY,
    S1SceneRef,
    S1Series,
    TemporalSarError,
    build_seasonal_baseline,
    detect_temporal_flood,
    flood_zscore,
    inundation_frequency,
    inundation_history,
    to_db,
    zscore_to_probability,
)

SHAPE = (32, 32)
BBOX = (99.80, 20.25, 100.04, 20.48)

# Linear gamma0 levels chosen so the dB contrast matches real C-band VH:
# land ~ -12 dB, open water ~ -22 dB.
LAND_LINEAR = 10 ** (-12.0 / 10.0)
WATER_LINEAR = 10 ** (-22.0 / 10.0)
WET_SEASON_OFFSET_DB = 3.0  # vegetation/moisture brightening, May-Oct


def _scene(item_id, date, *, water=None, rng=None, orbit=26):
    """Build one synthetic acquisition with a realistic seasonal offset."""

    month = int(date[5:7])
    rng = rng or np.random.default_rng(abs(hash(date)) % (2**32))
    base_db = -12.0 + (WET_SEASON_OFFSET_DB if 5 <= month <= 10 else 0.0)
    db = np.full(SHAPE, base_db, dtype="float64")
    db += rng.normal(0.0, 0.5, SHAPE)  # speckle after multi-looking
    if water is not None:
        db[water] = -22.0 + rng.normal(0.0, 0.5, SHAPE)[water]
    linear = (10 ** (db / 10.0)).astype("float32")
    return S1SceneRef(
        item_id=item_id,
        datetime=f"{date}T23:16:00+00:00",
        relative_orbit=orbit,
        orbit_direction="descending",
        arrays={"vh": linear, "vv": linear * 2.0},
    )


def _dates(start_year=2018, end_year=2024):
    """12-day repeat, the real Sentinel-1 single-orbit cadence."""

    out = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            for day in (3, 15, 27):
                out.append(f"{year}-{month:02d}-{day:02d}")
    return out


@pytest.fixture(scope="module")
def series():
    """A multi-year archive containing historical floods, as a real one would."""

    rng = np.random.default_rng(7)
    historical_flood = np.zeros(SHAPE, dtype=bool)
    historical_flood[8:16, 8:24] = True
    # Past flood dates live *inside* the archive -- the median must ignore them.
    flooded_dates = {"2019-09-15", "2020-09-03", "2022-08-27"}
    scenes = tuple(
        _scene(f"S1_{d}", d, water=historical_flood if d in flooded_dates else None, rng=rng)
        for d in _dates()
    )
    return S1Series(
        scenes=scenes, bbox=BBOX, out_shape=SHAPE,
        relative_orbit=26, orbit_direction="descending",
    )


@pytest.fixture(scope="module")
def baseline(series):
    return build_seasonal_baseline(series, polarisation="vh", row_chunk=16)


# --------------------------------------------------------------------------- #
# Series handling
# --------------------------------------------------------------------------- #
def test_mixed_orbits_are_rejected(series):
    """Incidence angle varies by several dB across orbits, so mixing is invalid."""

    mixed = S1Series(
        scenes=series.scenes[:10] + (_scene("other", "2023-01-03", orbit=99),),
        bbox=BBOX, out_shape=SHAPE, relative_orbit=26, orbit_direction="descending",
    )
    with pytest.raises(TemporalSarError, match="mixes relative orbits"):
        build_seasonal_baseline(mixed)


def test_empty_series_is_rejected():
    empty = S1Series(scenes=(), bbox=BBOX, out_shape=SHAPE, relative_orbit=26,
                     orbit_direction="descending")
    with pytest.raises(TemporalSarError, match="empty series"):
        build_seasonal_baseline(empty)


def test_excluding_dates_removes_them_and_records_the_count(series):
    reduced = series.excluding(["2019-09-15", "2020-09-03"])
    assert len(reduced) == len(series) - 2
    assert reduced.discarded["excluded_dates"] == 2
    assert all(s.date not in {"2019-09-15", "2020-09-03"} for s in reduced.scenes)


def test_series_manifest_reports_coverage(series):
    payload = series.to_dict()
    assert payload["n_scenes"] == len(series)
    assert payload["relative_orbit"] == 26
    assert set(payload["scenes_per_year"]) == set(range(2018, 2025))


# --------------------------------------------------------------------------- #
# The baseline
# --------------------------------------------------------------------------- #
def test_baseline_recovers_the_seasonal_offset(baseline):
    """A single annual baseline would smear wet and dry together; binning must not."""

    dry = baseline.median_db[SEASON_BINS_WET_DRY[1]]
    wet = baseline.median_db[SEASON_BINS_WET_DRY[7]]
    assert float(np.median(dry)) == pytest.approx(-12.0, abs=0.4)
    assert float(np.median(wet)) == pytest.approx(-12.0 + WET_SEASON_OFFSET_DB, abs=0.4)


def test_median_is_unmoved_by_historical_floods(baseline):
    """Three flood dates in the archive must not drag the wet-season median down.

    This is the property that lets the method stay label-free: it never needs to
    know which past acquisitions were floods.
    """

    wet = baseline.median_db[SEASON_BINS_WET_DRY[9]]
    previously_flooded = wet[8:16, 8:24]
    never_flooded = wet[24:32, :]
    assert float(np.median(previously_flooded)) == pytest.approx(
        float(np.median(never_flooded)), abs=0.5
    )


def test_mad_floor_is_enforced(baseline):
    assert float(baseline.mad_db.min()) >= baseline.mad_floor_db


def test_observation_counts_are_recorded(baseline):
    # 7 years x 6 dry months x 3 acquisitions = 126 per dry-season pixel.
    assert int(np.median(baseline.n_obs[SEASON_BINS_WET_DRY[1]])) == 126
    assert all(share == 1.0 for share in baseline.coverage().values())


def test_monthly_binning_is_used_when_the_archive_supports_it(series):
    monthly = build_seasonal_baseline(
        series, season_of_month=SEASON_BINS_MONTHLY, row_chunk=16
    )
    assert len(monthly.season_labels) == 12
    # 7 years x 3 acquisitions per month = 21, comfortably above min_obs_per_bin.
    assert int(np.median(monthly.n_obs[0])) == 21


def test_short_archive_falls_back_to_wet_dry(series):
    """Monthly bins need ~8 observations each; a two-year archive cannot support them."""

    short = S1Series(
        scenes=tuple(s for s in series.scenes if s.date[:4] in {"2023", "2024"}),
        bbox=BBOX, out_shape=SHAPE, relative_orbit=26, orbit_direction="descending",
    )
    result = build_seasonal_baseline(
        short, season_of_month=SEASON_BINS_MONTHLY, min_obs_per_bin=20, row_chunk=16
    )
    assert len(result.season_labels) == 2  # fell back rather than emitting a weak baseline


def test_unsupportable_archive_fails_closed(series):
    tiny = S1Series(
        scenes=series.scenes[:4], bbox=BBOX, out_shape=SHAPE,
        relative_orbit=26, orbit_direction="descending",
    )
    with pytest.raises(TemporalSarError, match="too short or too gappy"):
        build_seasonal_baseline(tiny, min_obs_per_bin=50, row_chunk=16)


def test_excluded_dates_are_carried_into_the_manifest(series):
    result = build_seasonal_baseline(
        series, exclude_dates=["2024-09-15"], row_chunk=16
    )
    assert result.to_dict()["excluded_dates"] == ["2024-09-15"]


def test_chunking_does_not_change_the_result(series):
    coarse = build_seasonal_baseline(series, row_chunk=32)
    fine = build_seasonal_baseline(series, row_chunk=4)
    assert np.allclose(coarse.median_db, fine.median_db, equal_nan=True)
    assert np.allclose(coarse.mad_db, fine.mad_db, equal_nan=True)


# --------------------------------------------------------------------------- #
# Deviation
# --------------------------------------------------------------------------- #
def test_flooded_pixels_are_strongly_negative(series, baseline):
    rng = np.random.default_rng(99)
    event_water = np.zeros(SHAPE, dtype=bool)
    event_water[20:28, 4:20] = True
    event = _scene("S1_event", "2024-09-15", water=event_water, rng=rng)

    z = flood_zscore(to_db(event.read("vh")), baseline, month=9)
    assert float(np.nanmean(z[event_water])) < -5.0
    assert abs(float(np.nanmean(z[~event_water]))) < 2.0


def test_seasonal_binning_prevents_a_false_wet_season_alarm(series, baseline):
    """An ordinary wet-season scene must not read as flooded.

    Without seasonal bins the +3 dB monsoon offset would make every dry-season
    pixel look anomalous, or vice versa. This is the failure the binning exists
    to prevent.
    """

    ordinary = _scene("S1_ordinary_wet", "2023-07-15")
    z = flood_zscore(to_db(ordinary.read("vh")), baseline, month=7)
    assert abs(float(np.nanmean(z))) < 1.5


def test_undersampled_pixels_return_nan_not_zero(series, baseline):
    """A pixel with too little history is unknown, not normal.

    Real archives have partial coverage at swath edges, so this is the realistic
    case: some pixels are well observed and some are not, within one baseline.
    Substituting zero for the under-observed ones would assert "behaving
    normally" about pixels we know nothing about.
    """

    thin = replace(baseline, n_obs=baseline.n_obs.copy())
    thin.n_obs[:, :8, :] = 2  # top rows barely observed

    z = flood_zscore(to_db(series.scenes[0].read("vh")), thin, month=1)
    assert np.isnan(z[:8, :]).all()
    assert np.isfinite(z[8:, :]).all()
    assert not np.any(np.nan_to_num(z[:8, :], nan=0.0) != 0.0)


def test_shape_mismatch_is_rejected(baseline):
    with pytest.raises(TemporalSarError, match="does not match baseline"):
        flood_zscore(np.zeros((8, 8), dtype="float32"), baseline, month=1)


def test_unknown_month_is_rejected(baseline):
    with pytest.raises(TemporalSarError, match="season map"):
        flood_zscore(np.zeros(SHAPE, dtype="float32"), baseline, month=13)


# --------------------------------------------------------------------------- #
# Probability mapping
# --------------------------------------------------------------------------- #
def test_gaussian_mixture_separates_water_without_any_reference(series, baseline):
    rng = np.random.default_rng(5)
    event_water = np.zeros(SHAPE, dtype=bool)
    event_water[20:28, 4:20] = True
    event = _scene("S1_event", "2024-09-15", water=event_water, rng=rng)
    z = flood_zscore(to_db(event.read("vh")), baseline, month=9)

    probability, info = zscore_to_probability(z, method="gaussian_mixture")
    assert info["method"] == "gaussian_mixture"
    assert info["dark_mean"] < info["bright_mean"]
    assert float(np.nanmean(probability[event_water])) > 0.9
    assert float(np.nanmean(probability[~event_water])) < 0.1


def test_gaussian_mixture_is_deterministic(series, baseline):
    z = flood_zscore(to_db(series.scenes[10].read("vh")), baseline, month=1)
    first, info_a = zscore_to_probability(z, method="gaussian_mixture")
    second, info_b = zscore_to_probability(z, method="gaussian_mixture")
    assert np.allclose(first, second, equal_nan=True)
    assert info_a["dark_mean"] == info_b["dark_mean"]


def test_logistic_requires_fitted_coefficients():
    z = np.linspace(-8, 4, 100).astype("float32")
    with pytest.raises(TemporalSarError, match="fitted"):
        zscore_to_probability(z, method="logistic")


def test_logistic_is_monotone_decreasing_in_z():
    z = np.linspace(-8, 4, 50).astype("float32")
    probability, _ = zscore_to_probability(z, method="logistic", params={"a": 1.0, "b": -2.0})
    assert np.all(np.diff(probability) <= 1e-6)


def test_unknown_method_is_rejected():
    with pytest.raises(TemporalSarError, match="method must be"):
        zscore_to_probability(np.zeros(10, dtype="float32"), method="magic")


def test_nan_zscores_stay_nan_in_probability():
    z = np.array([np.nan, -6.0, 0.0, np.nan], dtype="float32")
    probability, _ = zscore_to_probability(z, method="logistic", params={"a": 1.0, "b": 0.0})
    assert np.isnan(probability[0]) and np.isnan(probability[3])
    assert np.isfinite(probability[1]) and np.isfinite(probability[2])


# --------------------------------------------------------------------------- #
# Event detection
# --------------------------------------------------------------------------- #
def test_detect_temporal_flood_reports_open_water_and_brightening(series, baseline):
    rng = np.random.default_rng(3)
    event_water = np.zeros(SHAPE, dtype=bool)
    event_water[20:28, 4:20] = True
    event = _scene("S1_event", "2024-09-15", water=event_water, rng=rng)

    result = detect_temporal_flood(to_db(event.read("vh")), baseline, month=9)
    detected = result.open_water.astype(bool)
    overlap = (detected & event_water).sum() / max(1, event_water.sum())
    assert overlap > 0.9
    assert result.metrics["season_bin"] == "wet_may_oct"
    assert "baseline" in result.metrics
    # Darkening must not be reported as flooded vegetation.
    assert result.possible_flooded_vegetation[event_water].sum() == 0


def test_permanent_water_is_suppressed(series, baseline):
    rng = np.random.default_rng(4)
    event_water = np.zeros(SHAPE, dtype=bool)
    event_water[20:28, 4:20] = True
    event = _scene("S1_event", "2024-09-15", water=event_water, rng=rng)
    permanent = np.zeros(SHAPE, dtype=bool)
    permanent[20:24, 4:20] = True

    result = detect_temporal_flood(
        to_db(event.read("vh")), baseline, month=9, permanent_water=permanent
    )
    assert result.open_water[permanent].sum() == 0


# --------------------------------------------------------------------------- #
# Inundation history -- the product a pre/post pair cannot make
# --------------------------------------------------------------------------- #
def test_inundation_history_tracks_known_flood_dates(series, baseline):
    flooded_area = np.zeros(SHAPE, dtype=bool)
    flooded_area[8:16, 8:24] = True
    dry_area = np.zeros(SHAPE, dtype=bool)
    dry_area[24:32, :] = True

    subset = S1Series(
        scenes=tuple(
            s for s in series.scenes
            if s.date in {"2019-09-15", "2020-09-03", "2021-09-15", "2022-08-27"}
        ),
        bbox=BBOX, out_shape=SHAPE, relative_orbit=26, orbit_direction="descending",
    )
    history = inundation_history(
        subset, baseline, {"flood_zone": flooded_area, "upland": dry_area}
    )
    assert len(history) == len(subset) * 2

    summary = inundation_frequency(history, threshold=0.5)
    # Three of the four sampled dates were flood dates in the fixture.
    assert summary["flood_zone"]["n_inundated"] == 3
    assert summary["upland"]["n_inundated"] == 0
    assert summary["flood_zone"]["inundation_frequency"] == pytest.approx(0.75)


def test_inundation_history_rejects_mismatched_masks(series, baseline):
    subset = S1Series(
        scenes=series.scenes[:2], bbox=BBOX, out_shape=SHAPE,
        relative_orbit=26, orbit_direction="descending",
    )
    with pytest.raises(TemporalSarError, match="does not match"):
        inundation_history(subset, baseline, {"bad": np.ones((8, 8), dtype=bool)})


def test_to_db_maps_nonpositive_to_nan():
    values = np.array([0.0, -1.0, 1.0], dtype="float32")
    db = to_db(values)
    assert np.isnan(db[0]) and np.isnan(db[1])
    assert db[2] == pytest.approx(0.0)
