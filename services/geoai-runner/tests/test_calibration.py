"""Tests for probability calibration and reliability metrics (T1.3).

Two classes of guarantee are under test. First, the arithmetic: Brier, log loss,
ECE/MCE, isotonic (PAVA) and Platt must be correct against hand-computable
cases, because these are the numbers a promotion decision would rest on. Second,
the role rule: a calibration fitted on the training or final-evaluation role is
not a calibration, and must be refused rather than warned about.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from geoai_runner.realpipeline.calibration import (
    CalibrationError,
    brier_score,
    expected_calibration_error,
    fit_calibration,
    fit_isotonic,
    fit_platt,
    log_loss,
    reliability_curve,
)


def _miscalibrated(n=4000, seed=0):
    """An over-confident detector: true rate is the square of what it claims.

    This is the realistic failure shape for a thresholded SAR ramp -- it reports
    high probabilities far more often than the outcome justifies.
    """

    rng = np.random.default_rng(seed)
    claimed = rng.uniform(0.0, 1.0, n)
    truth = rng.uniform(0.0, 1.0, n) < claimed**2
    return claimed, truth.astype("uint8")


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def test_brier_matches_hand_computation():
    p = np.array([0.0, 1.0, 0.5, 0.5])
    r = np.array([0, 1, 1, 0])
    assert brier_score(p, r) == pytest.approx((0.0 + 0.0 + 0.25 + 0.25) / 4)


def test_perfect_prediction_scores_zero():
    p = np.array([0.0, 1.0, 0.0, 1.0])
    r = np.array([0, 1, 0, 1])
    assert brier_score(p, r) == pytest.approx(0.0)
    assert log_loss(p, r) == pytest.approx(0.0, abs=1e-9)


def test_log_loss_is_finite_at_the_extremes():
    """Clipping must keep a confidently wrong prediction finite, not infinite."""

    value = log_loss(np.array([0.0, 1.0]), np.array([1, 0]))
    assert np.isfinite(value)
    assert value > 10.0


def test_reliability_curve_bins_are_populated_and_ordered():
    p, r = _miscalibrated()
    curve = reliability_curve(p, r, n_bins=10)
    assert len(curve) == 10
    assert all(row["n"] > 0 for row in curve)
    assert [row["bin_lo"] for row in curve] == sorted(row["bin_lo"] for row in curve)
    assert sum(row["n"] for row in curve) == len(p)


def test_quantile_bins_beat_uniform_on_a_skewed_distribution():
    """Flood probability piles up near zero; uniform bins would mostly be empty."""

    rng = np.random.default_rng(1)
    p = np.clip(rng.exponential(0.02, 5000), 0, 1)
    r = (rng.uniform(size=5000) < p).astype("uint8")
    quantile = reliability_curve(p, r, n_bins=10, strategy="quantile")
    uniform = reliability_curve(p, r, n_bins=10, strategy="uniform")
    assert len(quantile) > len(uniform)


def test_ece_is_zero_for_a_perfectly_calibrated_predictor():
    rng = np.random.default_rng(2)
    p = rng.uniform(0.0, 1.0, 40_000)
    r = (rng.uniform(size=40_000) < p).astype("uint8")
    ece, mce = expected_calibration_error(reliability_curve(p, r, n_bins=10))
    assert ece < 0.02
    assert mce < 0.05


def test_ece_detects_overconfidence():
    p, r = _miscalibrated()
    ece, mce = expected_calibration_error(reliability_curve(p, r, n_bins=10))
    assert ece > 0.1
    assert mce >= ece


def test_empty_curve_yields_zero():
    assert expected_calibration_error([]) == (0.0, 0.0)


# --------------------------------------------------------------------------- #
# Mappers
# --------------------------------------------------------------------------- #
def test_isotonic_is_monotone_non_decreasing():
    p, r = _miscalibrated()
    mapper = fit_isotonic(p, r)
    grid = np.linspace(0.0, 1.0, 200)
    mapped = mapper(grid)
    assert np.all(np.diff(mapped) >= -1e-9)


def test_isotonic_recovers_a_known_distortion():
    """Claimed p with true rate p^2 must map back toward p^2."""

    p, r = _miscalibrated(n=20_000, seed=3)
    mapper = fit_isotonic(p, r)
    for probe in (0.2, 0.5, 0.8):
        assert float(mapper(np.array([probe]))[0]) == pytest.approx(probe**2, abs=0.06)


def test_isotonic_pools_adjacent_violators():
    """A strictly decreasing target must be pooled to a single flat value."""

    p = np.array([0.1, 0.2, 0.3, 0.4])
    r = np.array([1, 1, 0, 0])
    mapper = fit_isotonic(p, r)
    assert float(mapper(np.array([0.1]))[0]) == pytest.approx(0.5)
    assert float(mapper(np.array([0.4]))[0]) == pytest.approx(0.5)


def test_platt_fits_a_logistic_distortion():
    rng = np.random.default_rng(4)
    p = rng.uniform(0.0, 1.0, 20_000)
    true = 1.0 / (1.0 + np.exp(-(3.0 * p - 1.5)))
    r = (rng.uniform(size=20_000) < true).astype("uint8")
    mapper = fit_platt(p, r)
    assert mapper.a == pytest.approx(3.0, abs=0.3)
    assert mapper.b == pytest.approx(-1.5, abs=0.3)


def test_mappers_preserve_nan():
    p, r = _miscalibrated(n=500)
    for mapper in (fit_isotonic(p, r), fit_platt(p, r)):
        out = mapper(np.array([0.3, np.nan, 0.7]))
        assert np.isnan(out[1])
        assert np.isfinite(out[0]) and np.isfinite(out[2])


def test_mapper_output_stays_in_unit_interval():
    p, r = _miscalibrated()
    for mapper in (fit_isotonic(p, r), fit_platt(p, r)):
        out = mapper(np.linspace(0.0, 1.0, 100))
        assert float(np.nanmin(out)) >= 0.0
        assert float(np.nanmax(out)) <= 1.0


# --------------------------------------------------------------------------- #
# The role rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["train", "test", "final_holdout"])
def test_forbidden_roles_are_refused(role):
    p, r = _miscalibrated(n=1000)
    with pytest.raises(CalibrationError, match="must not be fitted"):
        fit_calibration(
            p, r, role_mask=np.ones(p.shape, dtype=bool),
            fitted_on_role=role, reference_name="fixture",
        )


def test_unknown_role_is_refused():
    p, r = _miscalibrated(n=1000)
    with pytest.raises(CalibrationError, match="unknown calibration role"):
        fit_calibration(
            p, r, role_mask=np.ones(p.shape, dtype=bool),
            fitted_on_role="development", reference_name="fixture",
        )


def test_calibration_role_is_accepted_and_recorded():
    p, r = _miscalibrated()
    result = fit_calibration(
        p, r, role_mask=np.ones(p.shape, dtype=bool),
        fitted_on_role="val", reference_name="fixture",
    )
    assert result.fitted_on_role == "val"
    assert result.reference == "fixture"


# --------------------------------------------------------------------------- #
# End-to-end fit
# --------------------------------------------------------------------------- #
def test_calibration_improves_brier_and_ece():
    p, r = _miscalibrated(n=20_000, seed=5)
    result = fit_calibration(
        p, r, role_mask=np.ones(p.shape, dtype=bool),
        fitted_on_role="val", reference_name="synthetic_overconfident",
    )
    assert result.improved
    assert result.brier_after < result.brier_before
    assert result.ece_after < result.ece_before
    assert result.n == 20_000
    assert result.n_positive > 0


def test_role_mask_restricts_the_fit():
    p, r = _miscalibrated(n=4000)
    mask = np.zeros(p.shape, dtype=bool)
    mask[:1000] = True
    result = fit_calibration(
        p, r, role_mask=mask, fitted_on_role="val", reference_name="fixture",
    )
    assert result.n == 1000


def test_too_few_positives_is_refused():
    """A reliability curve from a handful of positives is noise, not evidence."""

    p = np.full(2000, 0.3)
    r = np.zeros(2000, dtype="uint8")
    r[:5] = 1
    with pytest.raises(CalibrationError, match="reference positives"):
        fit_calibration(
            p, r, role_mask=np.ones(p.shape, dtype=bool),
            fitted_on_role="val", reference_name="fixture",
        )


def test_partial_reference_is_flagged_in_the_receipt():
    """JRC permanent water constrains one end of the curve and cannot certify the other."""

    p, r = _miscalibrated()
    result = fit_calibration(
        p, r, role_mask=np.ones(p.shape, dtype=bool),
        fitted_on_role="val", reference_name="jrc_permanent_water_partial",
        reference_is_partial=True,
    )
    payload = result.to_dict()
    assert payload["reference_is_partial"] is True
    assert "partial reference" in payload["assumptions"]


def test_receipt_carries_every_evaluation_v2_field(tmp_path):
    p, r = _miscalibrated()
    result = fit_calibration(
        p, r, role_mask=np.ones(p.shape, dtype=bool),
        fitted_on_role="val", reference_name="fixture",
    )
    payload = json.loads(result.write(tmp_path / "calibration.json").read_text(encoding="utf-8"))
    for key in ("brier", "log_loss", "ece", "mce", "reliability_before", "reliability_after",
                "mapper", "fitted_on_role", "reference", "n", "n_positive"):
        assert key in payload, key
    assert payload["mapper"]["kind"] == "isotonic"


def test_platt_method_is_selectable():
    p, r = _miscalibrated()
    result = fit_calibration(
        p, r, role_mask=np.ones(p.shape, dtype=bool),
        fitted_on_role="val", reference_name="fixture", method="platt",
    )
    assert result.method == "platt"
    assert result.to_dict()["mapper"]["kind"] == "platt"


def test_unknown_method_is_refused():
    p, r = _miscalibrated(n=1000)
    with pytest.raises(CalibrationError, match="method must be"):
        fit_calibration(
            p, r, role_mask=np.ones(p.shape, dtype=bool),
            fitted_on_role="val", reference_name="fixture", method="spline",
        )


def test_empty_role_is_refused():
    p, r = _miscalibrated(n=1000)
    with pytest.raises(CalibrationError, match="no valid pixels"):
        fit_calibration(
            p, r, role_mask=np.zeros(p.shape, dtype=bool),
            fitted_on_role="val", reference_name="fixture",
        )


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #
def test_out_of_range_probability_is_refused():
    with pytest.raises(CalibrationError, match=r"\[0, 1\]"):
        brier_score(np.array([0.5, 1.7]), np.array([0, 1]))


def test_non_finite_probability_is_refused():
    with pytest.raises(CalibrationError, match="non-finite"):
        brier_score(np.array([0.5, np.nan]), np.array([0, 1]))


def test_shape_mismatch_is_refused():
    with pytest.raises(CalibrationError, match="does not match"):
        brier_score(np.array([0.5, 0.5]), np.array([0, 1, 1]))
