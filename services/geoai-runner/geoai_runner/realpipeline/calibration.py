"""Probability calibration and reliability metrics for flood products.

Why this module exists
----------------------
Component A's "probability" was ``clip((drop_db - 2.5) / 3.5, 0, 1)`` -- a linear
ramp between two hand-picked decibel values. That produces a number in ``[0, 1]``
but not a probability: nothing about it asserts that pixels scored 0.7 are
flooded about 70% of the time. Every downstream consumer -- zonal means,
thresholds, the FPPS flood term -- has been treating it as if it were.

Model Evaluation v2 in ``docs/geoai-system-design-v1.md`` already requires a
calibration layer (Brier, NLL, ECE, calibration method) for any promotion-eligible
evaluation. Nothing in the repository produced those numbers. This module does.

Everything here is plain numpy: isotonic regression via pool-adjacent-violators
and Platt scaling via IRLS, both short and exact. That keeps calibration runnable
in the runner's dependency-light base environment and fully testable offline,
which matters because a calibration mapper is the sort of thing that must not
silently drift.

The role rule
-------------
Calibration must be fitted on a partition role that neither fitted the model nor
reports the final metric. ``fit_calibration`` refuses ``train`` and ``test``
outright: fitting on train reproduces the model's own optimism, and fitting on
test turns the held-out score into a training signal. This mirrors leakage
control #6 and the four-role table in
``docs/immutable-multi-event-partitions-v1.md``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Roles that may be used to fit a probability calibration.
CALIBRATION_ROLES: frozenset[str] = frozenset(
    {"val", "calibration", "model_probability_calibration"}
)
FORBIDDEN_CALIBRATION_ROLES: frozenset[str] = frozenset({"train", "test", "final_holdout"})

DEFAULT_RELIABILITY_BINS = 10


class CalibrationError(ValueError):
    """Raised when a calibration configuration or input is unusable."""


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def brier_score(probability: np.ndarray, reference: np.ndarray) -> float:
    """Mean squared error between predicted probability and outcome."""

    p, r = _paired(probability, reference)
    return float(np.mean((p - r) ** 2))


def log_loss(probability: np.ndarray, reference: np.ndarray, *, epsilon: float = 1e-12) -> float:
    """Negative log likelihood, with probabilities clipped away from 0 and 1."""

    p, r = _paired(probability, reference)
    p = np.clip(p, epsilon, 1.0 - epsilon)
    return float(-np.mean(r * np.log(p) + (1.0 - r) * np.log(1.0 - p)))


def reliability_curve(
    probability: np.ndarray,
    reference: np.ndarray,
    *,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    strategy: str = "quantile",
) -> list[dict[str, float]]:
    """Return per-bin predicted-vs-observed frequency.

    ``strategy="quantile"`` uses equal-mass bins, which is the right default for
    flood probability: the distribution is overwhelmingly concentrated near zero,
    so equal-width bins would leave most bins empty and make ECE meaningless.
    """

    p, r = _paired(probability, reference)
    if n_bins < 2:
        raise CalibrationError(f"n_bins must be at least 2; got {n_bins}.")

    if strategy == "quantile":
        edges = np.unique(np.quantile(p, np.linspace(0.0, 1.0, n_bins + 1)))
        if edges.size < 2:  # degenerate: a single predicted value
            edges = np.array([p.min(), p.min() + 1e-9])
    elif strategy == "uniform":
        edges = np.linspace(0.0, 1.0, n_bins + 1)
    else:
        raise CalibrationError(f"strategy must be 'quantile' or 'uniform'; got {strategy!r}.")

    rows: list[dict[str, float]] = []
    for index in range(len(edges) - 1):
        low, high = float(edges[index]), float(edges[index + 1])
        last = index == len(edges) - 2
        selector = (p >= low) & (p <= high) if last else (p >= low) & (p < high)
        count = int(selector.sum())
        if count == 0:
            continue
        rows.append(
            {
                "bin_lo": round(low, 6),
                "bin_hi": round(high, 6),
                "n": count,
                "mean_predicted": round(float(p[selector].mean()), 6),
                "observed_frequency": round(float(r[selector].mean()), 6),
            }
        )
    return rows


def expected_calibration_error(curve: list[dict[str, float]]) -> tuple[float, float]:
    """Return ``(ECE, MCE)`` from a reliability curve.

    ECE is the sample-weighted mean absolute gap between predicted and observed
    frequency; MCE is the worst single bin. MCE matters here because a flood
    product can be well calibrated on the vast dry majority while being badly
    wrong in the high-probability bins that actually drive decisions.
    """

    if not curve:
        return 0.0, 0.0
    total = sum(int(row["n"]) for row in curve)
    if total == 0:
        return 0.0, 0.0
    gaps = [abs(float(row["mean_predicted"]) - float(row["observed_frequency"])) for row in curve]
    weights = [int(row["n"]) / total for row in curve]
    ece = sum(gap * weight for gap, weight in zip(gaps, weights, strict=True))
    return round(float(ece), 6), round(float(max(gaps)), 6)


# --------------------------------------------------------------------------- #
# Mappers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IsotonicMapper:
    """A monotone step function fitted by pool-adjacent-violators."""

    thresholds: tuple[float, ...]
    values: tuple[float, ...]

    def __call__(self, probability: np.ndarray) -> np.ndarray:
        p = np.asarray(probability, dtype="float64")
        finite = np.isfinite(p)
        out = np.full(p.shape, np.nan, dtype="float32")
        if not self.thresholds:
            return out
        index = np.searchsorted(np.asarray(self.thresholds), p[finite], side="right") - 1
        index = np.clip(index, 0, len(self.values) - 1)
        out[finite] = np.asarray(self.values, dtype="float32")[index]
        return out

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable description of the mapper."""

        return {
            "kind": "isotonic",
            "n_steps": len(self.values),
            "thresholds": [round(v, 6) for v in self.thresholds],
            "values": [round(v, 6) for v in self.values],
        }


@dataclass(frozen=True)
class PlattMapper:
    """A logistic recalibration ``sigmoid(a * p + b)``."""

    a: float
    b: float

    def __call__(self, probability: np.ndarray) -> np.ndarray:
        p = np.asarray(probability, dtype="float64")
        finite = np.isfinite(p)
        out = np.full(p.shape, np.nan, dtype="float32")
        out[finite] = (1.0 / (1.0 + np.exp(-(self.a * p[finite] + self.b)))).astype("float32")
        return out

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable description of the mapper."""

        return {"kind": "platt", "a": round(self.a, 6), "b": round(self.b, 6)}


def fit_isotonic(probability: np.ndarray, reference: np.ndarray) -> IsotonicMapper:
    """Fit a monotone calibration by pool-adjacent-violators (exact, no scipy)."""

    p, r = _paired(probability, reference)
    order = np.argsort(p, kind="mergesort")
    p, r = p[order], r[order]

    # Each block holds (sum of targets, count); merge while monotonicity is violated.
    values: list[float] = []
    weights: list[float] = []
    thresholds: list[float] = []
    for value, target in zip(p, r, strict=True):
        values.append(float(target))
        weights.append(1.0)
        thresholds.append(float(value))
        while len(values) > 1 and values[-2] > values[-1]:
            total_weight = weights[-2] + weights[-1]
            merged = (values[-2] * weights[-2] + values[-1] * weights[-1]) / total_weight
            values[-2:] = [merged]
            weights[-2:] = [total_weight]
            thresholds[-2:] = [thresholds[-2]]
    return IsotonicMapper(thresholds=tuple(thresholds), values=tuple(values))


def fit_platt(
    probability: np.ndarray,
    reference: np.ndarray,
    *,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
) -> PlattMapper:
    """Fit ``sigmoid(a * p + b)`` by iteratively reweighted least squares."""

    p, r = _paired(probability, reference)
    a, b = 1.0, 0.0
    for _ in range(max_iterations):
        eta = a * p + b
        mu = 1.0 / (1.0 + np.exp(-eta))
        weight = np.maximum(mu * (1.0 - mu), 1e-9)
        residual = r - mu
        # Newton step on the 2x2 information matrix.
        s11 = float(np.sum(weight * p * p))
        s12 = float(np.sum(weight * p))
        s22 = float(np.sum(weight))
        g1 = float(np.sum(residual * p))
        g2 = float(np.sum(residual))
        determinant = s11 * s22 - s12 * s12
        if abs(determinant) < 1e-12:
            break
        da = (s22 * g1 - s12 * g2) / determinant
        db = (-s12 * g1 + s11 * g2) / determinant
        a, b = a + da, b + db
        if max(abs(da), abs(db)) < tolerance:
            break
    if not (math.isfinite(a) and math.isfinite(b)):
        raise CalibrationError("Platt fit diverged; check that the reference is binary.")
    return PlattMapper(a=float(a), b=float(b))


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CalibrationResult:
    """A fitted calibration plus the evidence required by Model Evaluation v2."""

    method: str
    fitted_on_role: str
    reference: str
    reference_is_partial: bool
    n: int
    n_positive: int
    brier_before: float
    brier_after: float
    log_loss_before: float
    log_loss_after: float
    ece_before: float
    ece_after: float
    mce_before: float
    mce_after: float
    reliability_before: list[dict[str, float]]
    reliability_after: list[dict[str, float]]
    mapper: IsotonicMapper | PlattMapper

    @property
    def improved(self) -> bool:
        """Whether calibration reduced the Brier score."""

        return self.brier_after < self.brier_before

    def to_dict(self) -> dict[str, object]:
        """Return the manifest projection for the evaluation receipt."""

        return {
            "method": self.method,
            "fitted_on_role": self.fitted_on_role,
            "reference": self.reference,
            "reference_is_partial": self.reference_is_partial,
            "n": self.n,
            "n_positive": self.n_positive,
            "brier": {"before": self.brier_before, "after": self.brier_after},
            "log_loss": {"before": self.log_loss_before, "after": self.log_loss_after},
            "ece": {"before": self.ece_before, "after": self.ece_after},
            "mce": {"before": self.mce_before, "after": self.mce_after},
            "improved": self.improved,
            "reliability_before": self.reliability_before,
            "reliability_after": self.reliability_after,
            "mapper": self.mapper.to_dict(),
            "assumptions": (
                "Calibration fitted on a held-out calibration role, never on the "
                "training or final-evaluation roles. A partial reference (for example "
                "permanent water only) constrains one end of the probability range and "
                "cannot certify the flood end; this is recorded in "
                "reference_is_partial."
            ),
        }

    def write(self, path: str | Path) -> Path:
        """Write the calibration receipt as JSON."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8", newline="\n")
        return path


def fit_calibration(
    probability: np.ndarray,
    reference: np.ndarray,
    *,
    role_mask: np.ndarray,
    fitted_on_role: str,
    reference_name: str,
    method: str = "isotonic",
    reference_is_partial: bool = False,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    min_positive: int = 50,
) -> CalibrationResult:
    """Fit and score a probability calibration on one partition role.

    Args:
        probability: Raw model probability over the full scene.
        reference: Binary reference over the full scene.
        role_mask: Boolean selector for the calibration role's pixels.
        fitted_on_role: Must be a calibration role; ``train``/``test`` are refused.
        reference_name: Provenance of the reference, carried into the receipt.
        reference_is_partial: Set when the reference constrains only part of the
            probability range (e.g. JRC permanent water, which says nothing about
            transient flooding).
        min_positive: Refuse to fit below this many reference positives -- a
            calibration curve from a handful of positives is noise presented as
            evidence.
    """

    if fitted_on_role in FORBIDDEN_CALIBRATION_ROLES:
        raise CalibrationError(
            f"calibration must not be fitted on role {fitted_on_role!r}. Fitting on "
            "'train' reproduces the model's own optimism; fitting on 'test' or "
            "'final_holdout' converts the held-out score into a training signal."
        )
    if fitted_on_role not in CALIBRATION_ROLES:
        raise CalibrationError(
            f"unknown calibration role {fitted_on_role!r}; expected one of "
            f"{sorted(CALIBRATION_ROLES)}."
        )
    if method not in {"isotonic", "platt"}:
        raise CalibrationError(f"method must be 'isotonic' or 'platt'; got {method!r}.")

    finite = np.isfinite(np.asarray(probability, dtype="float64"))
    selector = np.asarray(role_mask, dtype=bool) & finite
    p = np.asarray(probability, dtype="float64")[selector]
    r = np.asarray(reference).astype(bool).astype("float64")[selector]
    n_positive = int(r.sum())
    if p.size == 0:
        raise CalibrationError("calibration role selects no valid pixels.")
    if n_positive < min_positive:
        raise CalibrationError(
            f"calibration role has only {n_positive} reference positives (minimum "
            f"{min_positive}). A reliability curve from this few positives is noise."
        )

    mapper: IsotonicMapper | PlattMapper = (
        fit_isotonic(p, r) if method == "isotonic" else fit_platt(p, r)
    )
    calibrated = np.asarray(mapper(p), dtype="float64")

    before = reliability_curve(p, r, n_bins=n_bins)
    after = reliability_curve(calibrated, r, n_bins=n_bins)
    ece_before, mce_before = expected_calibration_error(before)
    ece_after, mce_after = expected_calibration_error(after)

    return CalibrationResult(
        method=method,
        fitted_on_role=fitted_on_role,
        reference=reference_name,
        reference_is_partial=reference_is_partial,
        n=int(p.size),
        n_positive=n_positive,
        brier_before=round(brier_score(p, r), 6),
        brier_after=round(brier_score(calibrated, r), 6),
        log_loss_before=round(log_loss(p, r), 6),
        log_loss_after=round(log_loss(calibrated, r), 6),
        ece_before=ece_before,
        ece_after=ece_after,
        mce_before=mce_before,
        mce_after=mce_after,
        reliability_before=before,
        reliability_after=after,
        mapper=mapper,
    )


def _paired(probability: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flatten, validate and align a probability/reference pair."""

    p = np.asarray(probability, dtype="float64").ravel()
    r = np.asarray(reference).astype(bool).astype("float64").ravel()
    if p.shape != r.shape:
        raise CalibrationError(f"probability shape {p.shape} does not match reference {r.shape}.")
    if p.size == 0:
        raise CalibrationError("empty probability/reference pair.")
    if not np.all(np.isfinite(p)):
        raise CalibrationError("probability contains non-finite values; mask them first.")
    if p.min() < 0.0 or p.max() > 1.0:
        raise CalibrationError(
            f"probability must lie in [0, 1]; got [{p.min():.4f}, {p.max():.4f}]."
        )
    return p, r
