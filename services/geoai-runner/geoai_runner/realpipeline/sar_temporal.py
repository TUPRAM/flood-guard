"""Temporal SAR: per-pixel seasonal baselines and deviation-based flood detection.

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 12. The book's traditional
change detection compares one *before* image to one *after* image. This module
replaces the single "before" with **the pixel's own multi-year history**.

Why this replaces the pre/post pair
-----------------------------------
Component A currently differences one pre-event scene against one post-event
scene. Two problems follow from that, and they have the same fix.

*The reference is arbitrary.* A single pre-event date carries whatever soil
moisture, vegetation state and wind roughening happened to exist that day.
Differencing against it confounds "this pixel flooded" with "this pixel was
unusually dry three weeks ago". A per-pixel median over ~180 acquisitions on a
fixed orbit removes that: the reference becomes what this pixel *normally*
looks like at this time of year, on this geometry.

*The post-event date is whatever the orbit allows.* Sentinel-1's 12-day repeat
put the nearest same-orbit scene four days past the ~11 Sept 2024 peak, so the
mapped extent is residual drainage. A time series does not fix the sampling, but
it does let the event be read as a **trajectory** rather than a snapshot: the
same machinery produces a per-tambon inundation history, so "how often does this
tambon flood?" becomes answerable from data instead of from terrain alone.

Both properties come for free in terms of labels -- this is still a zero-label
method.

Design decisions that matter
----------------------------
**One relative orbit only.** Sentinel-1 incidence angle varies ~30-46 degrees
across the swath and backscatter varies by several dB with it, so a baseline
mixing orbits is bimodal and its z-scores are meaningless. The acquisition layer
selects the single most-populated relative orbit covering the study area and
records how many scenes it discarded.

**Median and MAD, not mean and standard deviation.** Historical floods are *in*
the archive. A mean is dragged down by every past flood and a standard deviation
is inflated by them; a median over ~180 samples is unmoved by a handful. This is
precisely what lets the method stay label-free -- it never needs to know which
past dates were floods.

**Seasonal binning.** VH over rice paddy and forest swings 2-4 dB between wet
and dry season, so a single annual baseline would flag the entire monsoon as
flooded. The default splits wet (May-Oct) from dry (Nov-Apr); monthly bins are
better but need ~8 usable observations per month, so the builder falls back
automatically and records which resolution it actually used.

**Signed z-scores.** A *brightening* is diagnostic of flooded vegetation
(double-bounce) or wind roughening. Collapsing the sign would merge that with
darkening, a known SAR failure mode, so the sign is preserved and positive
deviations are exposed as a separate layer rather than discarded.

**Chunked over rows.** A per-pixel median needs the whole time axis for the
pixels being reduced, so the cube is processed in row blocks. At 180 scenes and
a 128-row chunk that is ~94 MB, versus ~1.5 GB for the full cube.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

# Wet season over northern Thailand: the southwest monsoon, roughly May-October.
SEASON_BINS_WET_DRY: dict[int, int] = {
    1: 0,
    2: 0,
    3: 0,
    4: 0,
    11: 0,
    12: 0,  # dry
    5: 1,
    6: 1,
    7: 1,
    8: 1,
    9: 1,
    10: 1,  # wet
}
SEASON_LABELS_WET_DRY: tuple[str, ...] = ("dry_nov_apr", "wet_may_oct")

SEASON_BINS_MONTHLY: dict[int, int] = {month: month - 1 for month in range(1, 13)}
SEASON_LABELS_MONTHLY: tuple[str, ...] = tuple(f"month_{m:02d}" for m in range(1, 13))

# Residual speckle after multi-looking. Below this the MAD is noise, and dividing
# by it turns ordinary jitter into an unbounded z-score -- notably over permanent
# water and smooth tarmac, where the MAD collapses toward zero.
DEFAULT_MAD_FLOOR_DB = 0.4

# MAD -> sigma for a Gaussian.
ROBUST_SCALE = 1.4826


class TemporalSarError(ValueError):
    """Raised when a time series or baseline configuration is unusable."""


# --------------------------------------------------------------------------- #
# Series types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class S1SceneRef:
    """One acquisition, readable from disk cache or from memory.

    Holding paths rather than arrays is what keeps a ~180-scene series off the
    heap. ``arrays`` exists so tests and synthetic ablations can exercise the
    same code without writing GeoTIFFs.
    """

    item_id: str
    datetime: str
    relative_orbit: int
    orbit_direction: str
    paths: dict[str, Path] = field(default_factory=dict)
    arrays: dict[str, np.ndarray] | None = None

    @property
    def date(self) -> str:
        """Return the acquisition date as ``YYYY-MM-DD``."""

        return self.datetime[:10]

    @property
    def month(self) -> int:
        """Return the acquisition month (1-12)."""

        return int(self.datetime[5:7])

    def read(self, polarisation: str, row0: int = 0, row1: int | None = None) -> np.ndarray:
        """Read ``[row0:row1]`` of one polarisation as float32 linear amplitude."""

        if self.arrays is not None and polarisation in self.arrays:
            data = np.asarray(self.arrays[polarisation], dtype="float32")
            return data[row0:row1] if row1 is not None else data[row0:]
        path = self.paths.get(polarisation)
        if path is None:
            raise TemporalSarError(
                f"scene {self.item_id} has no {polarisation!r} band cached or in memory."
            )
        import rasterio
        from rasterio.windows import Window

        with rasterio.open(path) as src:
            if row1 is None:
                row1 = src.height
            window = Window(0, row0, src.width, row1 - row0)
            return src.read(1, window=window).astype("float32")


@dataclass(frozen=True)
class S1Series:
    """A single-orbit Sentinel-1 stack, held as references rather than pixels."""

    scenes: tuple[S1SceneRef, ...]
    bbox: tuple[float, float, float, float]
    out_shape: tuple[int, int]
    relative_orbit: int
    orbit_direction: str
    cache_dir: Path | None = None
    discarded: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.scenes)

    def excluding(self, dates: tuple[str, ...] | list[str]) -> S1Series:
        """Return a copy without the given ``YYYY-MM-DD`` dates.

        Used as a leakage control: a baseline that is going to be evaluated
        against a specific event must not contain that event, or the flood
        contaminates its own reference.
        """

        blocked = {str(d)[:10] for d in dates}
        kept = tuple(scene for scene in self.scenes if scene.date not in blocked)
        discarded = dict(self.discarded)
        discarded["excluded_dates"] = len(self.scenes) - len(kept)
        return S1Series(
            scenes=kept,
            bbox=self.bbox,
            out_shape=self.out_shape,
            relative_orbit=self.relative_orbit,
            orbit_direction=self.orbit_direction,
            cache_dir=self.cache_dir,
            discarded=discarded,
        )

    def scenes_per_year(self) -> dict[int, int]:
        """Return acquisition counts by calendar year (a coverage diagnostic)."""

        counts: dict[int, int] = {}
        for scene in self.scenes:
            year = int(scene.datetime[:4])
            counts[year] = counts.get(year, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, object]:
        """Return the manifest projection."""

        dates = [scene.date for scene in self.scenes]
        return {
            "n_scenes": len(self.scenes),
            "relative_orbit": self.relative_orbit,
            "orbit_direction": self.orbit_direction,
            "bbox": list(self.bbox),
            "out_shape": list(self.out_shape),
            "first_date": min(dates) if dates else None,
            "last_date": max(dates) if dates else None,
            "scenes_per_year": self.scenes_per_year(),
            "discarded": dict(self.discarded),
        }


# --------------------------------------------------------------------------- #
# Seasonal baseline
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SeasonalBaseline:
    """Per-pixel, per-season median and MAD of backscatter in dB."""

    median_db: np.ndarray  # (S, H, W) float32
    mad_db: np.ndarray  # (S, H, W) float32
    n_obs: np.ndarray  # (S, H, W) uint16
    season_of_month: dict[int, int]
    season_labels: tuple[str, ...]
    polarisation: str
    mad_floor_db: float
    min_obs_per_bin: int
    excluded_dates: tuple[str, ...]
    series: dict[str, object]

    def bin_for_month(self, month: int) -> int:
        """Return the season bin index for a calendar month."""

        try:
            return self.season_of_month[int(month)]
        except KeyError as exc:
            raise TemporalSarError(f"month {month!r} is not in the season map.") from exc

    def coverage(self) -> dict[str, float]:
        """Return the share of pixels meeting ``min_obs_per_bin`` in each bin."""

        return {
            self.season_labels[s]: round(float((self.n_obs[s] >= self.min_obs_per_bin).mean()), 5)
            for s in range(self.n_obs.shape[0])
        }

    def to_dict(self) -> dict[str, object]:
        """Return the manifest projection."""

        return {
            "polarisation": self.polarisation,
            "season_labels": list(self.season_labels),
            "n_bins": len(self.season_labels),
            "mad_floor_db": self.mad_floor_db,
            "min_obs_per_bin": self.min_obs_per_bin,
            "excluded_dates": list(self.excluded_dates),
            "coverage_by_bin": self.coverage(),
            "median_obs_per_bin": {
                self.season_labels[s]: int(np.median(self.n_obs[s]))
                for s in range(self.n_obs.shape[0])
            },
            "series": dict(self.series),
        }


def to_db(amplitude: np.ndarray) -> np.ndarray:
    """Convert linear gamma0 to decibels, mapping non-positive values to NaN."""

    values = np.asarray(amplitude, dtype="float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(values > 0, 10.0 * np.log10(np.maximum(values, 1e-12)), np.nan).astype(
            "float32"
        )


def build_seasonal_baseline(
    series: S1Series,
    *,
    polarisation: str = "vh",
    season_of_month: dict[int, int] | None = None,
    season_labels: tuple[str, ...] | None = None,
    exclude_dates: tuple[str, ...] | list[str] = (),
    min_obs_per_bin: int = 8,
    mad_floor_db: float = DEFAULT_MAD_FLOOR_DB,
    row_chunk: int = 128,
    allow_bin_fallback: bool = True,
) -> SeasonalBaseline:
    """Compute the per-pixel, per-season median and MAD of backscatter.

    Args:
        series: A single-orbit stack. Mixing relative orbits is rejected.
        polarisation: ``"vh"`` (default; more water-sensitive) or ``"vv"``.
        season_of_month: Month -> bin index. Defaults to wet/dry.
        exclude_dates: Dates held out of the baseline, e.g. the event being
            evaluated. Recorded in the manifest as a leakage control.
        min_obs_per_bin: A bin with fewer median observations than this is not
            usable; with ``allow_bin_fallback`` the builder drops to wet/dry
            rather than emitting a baseline it cannot support.
        row_chunk: Rows reduced at a time. Bounds peak memory.

    Raises:
        TemporalSarError: if the series mixes orbits, is empty, or cannot
            support even the coarsest binning.
    """

    if len(series) == 0:
        raise TemporalSarError("cannot build a baseline from an empty series.")
    orbits = {scene.relative_orbit for scene in series.scenes}
    if len(orbits) > 1:
        raise TemporalSarError(
            f"series mixes relative orbits {sorted(orbits)}. Incidence angle varies "
            "by several dB across orbits, so a mixed baseline is bimodal and its "
            "z-scores are not interpretable."
        )
    if polarisation not in {"vv", "vh"}:
        raise TemporalSarError(f"polarisation must be 'vv' or 'vh'; got {polarisation!r}.")

    working = series.excluding(exclude_dates) if exclude_dates else series
    if len(working) == 0:
        raise TemporalSarError("every scene was excluded; nothing left to build a baseline from.")

    requested = season_of_month or SEASON_BINS_WET_DRY
    labels = season_labels or (
        SEASON_LABELS_MONTHLY if requested is SEASON_BINS_MONTHLY else SEASON_LABELS_WET_DRY
    )
    if len(requested) != 12:
        raise TemporalSarError("season_of_month must cover all twelve months.")

    baseline = _compute(
        working,
        polarisation,
        requested,
        labels,
        min_obs_per_bin,
        mad_floor_db,
        row_chunk,
        tuple(str(d)[:10] for d in exclude_dates),
    )
    weakest = min(baseline.coverage().values()) if baseline.season_labels else 0.0
    if weakest >= 0.5 or not allow_bin_fallback or requested is SEASON_BINS_WET_DRY:
        if weakest < 0.5 and requested is SEASON_BINS_WET_DRY:
            raise TemporalSarError(
                f"even wet/dry binning leaves only {weakest:.1%} of pixels with "
                f"{min_obs_per_bin}+ observations in the weakest bin. The series is too "
                "short or too gappy for a temporal baseline; acquire more scenes rather "
                "than lowering min_obs_per_bin."
            )
        return baseline
    # Requested binning is too fine for this archive: fall back and record it.
    return _compute(
        working,
        polarisation,
        SEASON_BINS_WET_DRY,
        SEASON_LABELS_WET_DRY,
        min_obs_per_bin,
        mad_floor_db,
        row_chunk,
        tuple(str(d)[:10] for d in exclude_dates),
    )


def _compute(
    series: S1Series,
    polarisation: str,
    season_of_month: dict[int, int],
    labels: tuple[str, ...],
    min_obs_per_bin: int,
    mad_floor_db: float,
    row_chunk: int,
    excluded: tuple[str, ...],
) -> SeasonalBaseline:
    height, width = series.out_shape
    n_bins = len(labels)
    median_db = np.full((n_bins, height, width), np.nan, dtype="float32")
    mad_db = np.full((n_bins, height, width), np.nan, dtype="float32")
    n_obs = np.zeros((n_bins, height, width), dtype="uint16")

    by_bin: dict[int, list[S1SceneRef]] = {b: [] for b in range(n_bins)}
    for scene in series.scenes:
        by_bin[season_of_month[scene.month]].append(scene)

    for row0 in range(0, height, row_chunk):
        row1 = min(row0 + row_chunk, height)
        for bin_index, scenes in by_bin.items():
            if not scenes:
                continue
            stack = np.stack(
                [to_db(scene.read(polarisation, row0, row1)) for scene in scenes], axis=0
            )
            with np.errstate(invalid="ignore"):
                med = np.nanmedian(stack, axis=0)
                deviation = np.abs(stack - med[None, :, :])
                mad = np.nanmedian(deviation, axis=0)
            median_db[bin_index, row0:row1] = med.astype("float32")
            mad_db[bin_index, row0:row1] = np.maximum(mad, mad_floor_db).astype("float32")
            n_obs[bin_index, row0:row1] = np.isfinite(stack).sum(axis=0).astype("uint16")

    return SeasonalBaseline(
        median_db=median_db,
        mad_db=mad_db,
        n_obs=n_obs,
        season_of_month=dict(season_of_month),
        season_labels=tuple(labels),
        polarisation=polarisation,
        mad_floor_db=float(mad_floor_db),
        min_obs_per_bin=int(min_obs_per_bin),
        excluded_dates=tuple(excluded),
        series=series.to_dict(),
    )


# --------------------------------------------------------------------------- #
# Deviation
# --------------------------------------------------------------------------- #
def flood_zscore(
    scene_db: np.ndarray,
    baseline: SeasonalBaseline,
    month: int,
    *,
    robust_scale: float = ROBUST_SCALE,
) -> np.ndarray:
    """Return the signed robust z-score of a scene against its seasonal baseline.

    Negative means the pixel is **darker than it normally is at this time of
    year** -- the open-water signature. Positive means brighter, which is
    diagnostic of flooded vegetation (double-bounce) or wind roughening, and is
    deliberately preserved rather than folded into a magnitude.

    Pixels whose bin has fewer than ``min_obs_per_bin`` observations return NaN:
    an under-sampled baseline is not evidence of normality, and substituting
    zero would silently assert "this pixel is behaving normally".
    """

    scene_db = np.asarray(scene_db, dtype="float32")
    bin_index = baseline.bin_for_month(month)
    median = baseline.median_db[bin_index]
    mad = baseline.mad_db[bin_index]
    obs = baseline.n_obs[bin_index]
    if scene_db.shape != median.shape:
        raise TemporalSarError(
            f"scene shape {scene_db.shape} does not match baseline {median.shape}."
        )

    sigma = np.maximum(mad, baseline.mad_floor_db) * robust_scale
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (scene_db - median) / sigma
    return np.where(obs >= baseline.min_obs_per_bin, z, np.nan).astype("float32")


def zscore_to_probability(
    z: np.ndarray,
    *,
    method: str = "gaussian_mixture",
    params: dict[str, float] | None = None,
    max_iterations: int = 200,
    seed: int = 0,
    fit_sample: int | None = 200_000,
) -> tuple[np.ndarray, dict[str, object]]:
    """Map signed z-scores to a flood probability in ``[0, 1]``.

    ``"logistic"`` applies ``sigmoid(a * (-z) + b)`` with supplied coefficients.
    Coefficients must come from :mod:`calibration` fitted against a reference --
    not from judgement, which is what the previous linear
    ``clip((drop - 2.5) / 3.5)`` ramp amounted to.

    ``"gaussian_mixture"`` fits a two-component 1-D Gaussian mixture to the
    z histogram and returns the posterior of the darker component. This is the
    classical Bayesian SAR water-detection approach and it needs **no reference
    at all**, which matters here because a licensed flood mask for this event is
    still pending. It is implemented with a plain EM loop rather than scikit-learn
    so it runs in the dependency-light base environment.

    Returns ``(probability, info)``; ``info`` carries the fitted parameters so a
    published probability can be reproduced.
    """

    z = np.asarray(z, dtype="float32")
    finite = np.isfinite(z)
    probability = np.zeros(z.shape, dtype="float32")

    if method == "logistic":
        if not params or "a" not in params or "b" not in params:
            raise TemporalSarError(
                "logistic mapping requires fitted 'a' and 'b'. Fit them against a "
                "reference via calibration.fit_calibration rather than choosing them."
            )
        a, b = float(params["a"]), float(params["b"])
        values = a * (-z[finite]) + b
        probability[finite] = (1.0 / (1.0 + np.exp(-values))).astype("float32")
        info: dict[str, object] = {"method": "logistic", "a": a, "b": b}
    elif method == "gaussian_mixture":
        if not finite.any():
            raise TemporalSarError("z-score array has no finite values to fit.")
        observed = z[finite]
        # Fit on a deterministic subsample: EM over ~1M pixels per scene x ~180
        # scenes dominates the runtime of a multi-year history, and a 200k sample
        # already pins a two-component 1-D mixture. The fitted parameters are then
        # applied to every pixel, so only the fit is approximated, not the output.
        if fit_sample is not None and observed.size > fit_sample:
            rng = np.random.default_rng(seed)
            sample = observed[rng.choice(observed.size, fit_sample, replace=False)]
        else:
            sample = observed
        fit = _fit_two_component_gaussian(sample, max_iterations=max_iterations, seed=seed)
        probability[finite] = _dark_posterior(observed, fit).astype("float32")
        info = {"method": "gaussian_mixture", "fit_sample_size": int(sample.size), **fit}
    else:
        raise TemporalSarError(f"method must be 'logistic' or 'gaussian_mixture'; got {method!r}.")

    info["finite_fraction"] = round(float(finite.mean()), 5)
    # NaN z (under-sampled baseline) must not read as "certainly dry".
    probability[~finite] = np.nan
    return probability, info


def _fit_two_component_gaussian(
    values: np.ndarray,
    *,
    max_iterations: int = 200,
    seed: int = 0,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Fit a two-component 1-D Gaussian mixture by EM (pure numpy, deterministic).

    Initialised from quantiles rather than randomly so repeated runs on the same
    input give the same parameters -- a published probability has to be
    reproducible.
    """

    x = np.asarray(values, dtype="float64").ravel()
    if x.size < 2:
        raise TemporalSarError("need at least two samples to fit a mixture.")
    low, high = np.quantile(x, [0.15, 0.85])
    mu = np.array([low, high], dtype="float64")
    spread = max(float(x.std()), 1e-3)
    sigma = np.array([spread, spread], dtype="float64")
    weight = np.array([0.5, 0.5], dtype="float64")

    previous = -np.inf
    for _ in range(max_iterations):
        density = np.stack(
            [
                weight[k]
                * np.exp(-0.5 * ((x - mu[k]) / sigma[k]) ** 2)
                / (sigma[k] * math.sqrt(2.0 * math.pi))
                for k in range(2)
            ]
        )
        total = density.sum(axis=0)
        total = np.where(total > 0, total, 1e-300)
        responsibility = density / total
        counts = responsibility.sum(axis=1)
        counts = np.where(counts > 0, counts, 1e-300)
        weight = counts / x.size
        mu = (responsibility * x).sum(axis=1) / counts
        variance = (responsibility * (x[None, :] - mu[:, None]) ** 2).sum(axis=1) / counts
        sigma = np.sqrt(np.maximum(variance, 1e-6))

        log_likelihood = float(np.log(total).sum())
        if abs(log_likelihood - previous) < tolerance * max(1.0, abs(previous)):
            break
        previous = log_likelihood

    dark = int(np.argmin(mu))  # the darker (more negative z) component is water
    return {
        "dark_mean": float(mu[dark]),
        "dark_sigma": float(sigma[dark]),
        "dark_weight": float(weight[dark]),
        "bright_mean": float(mu[1 - dark]),
        "bright_sigma": float(sigma[1 - dark]),
        "bright_weight": float(weight[1 - dark]),
        "log_likelihood": float(previous),
    }


def _dark_posterior(values: np.ndarray, fit: dict[str, float]) -> np.ndarray:
    """Posterior probability that each sample came from the darker component."""

    x = np.asarray(values, dtype="float64").ravel()

    def component(mean: float, sigma: float, weight: float) -> np.ndarray:
        return (
            weight * np.exp(-0.5 * ((x - mean) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))
        )

    dark = component(fit["dark_mean"], fit["dark_sigma"], fit["dark_weight"])
    bright = component(fit["bright_mean"], fit["bright_sigma"], fit["bright_weight"])
    total = dark + bright
    return np.where(total > 0, dark / np.where(total > 0, total, 1.0), 0.0)


# --------------------------------------------------------------------------- #
# Event products
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TemporalFloodResult:
    """Outputs of one temporal-deviation flood detection."""

    probability: np.ndarray
    zscore: np.ndarray
    open_water: np.ndarray
    possible_flooded_vegetation: np.ndarray
    metrics: dict[str, object]


def detect_temporal_flood(
    scene_db: np.ndarray,
    baseline: SeasonalBaseline,
    month: int,
    *,
    method: str = "gaussian_mixture",
    params: dict[str, float] | None = None,
    open_water_threshold: float = 0.5,
    brightening_z: float = 3.0,
    permanent_water: np.ndarray | None = None,
) -> TemporalFloodResult:
    """Detect flooding as deviation from the pixel's own seasonal normal."""

    z = flood_zscore(scene_db, baseline, month)
    probability, info = zscore_to_probability(z, method=method, params=params)

    open_water = (np.nan_to_num(probability, nan=0.0) >= open_water_threshold).astype("uint8")
    brightening = (np.nan_to_num(z, nan=0.0) >= brightening_z).astype("uint8")
    if permanent_water is not None:
        permanent = np.asarray(permanent_water, dtype=bool)
        open_water = np.where(permanent, 0, open_water).astype("uint8")
        brightening = np.where(permanent, 0, brightening).astype("uint8")

    valid = np.isfinite(z)
    return TemporalFloodResult(
        probability=probability,
        zscore=z,
        open_water=open_water,
        possible_flooded_vegetation=brightening,
        metrics={
            "method": f"temporal_deviation_{method}",
            "season_bin": baseline.season_labels[baseline.bin_for_month(month)],
            "open_water_fraction": round(float(open_water.mean()), 5),
            "flooded_vegetation_fraction": round(float(brightening.mean()), 5),
            "valid_fraction": round(float(valid.mean()), 5),
            "z_p01": round(float(np.nanpercentile(z, 1)), 3) if valid.any() else None,
            "z_p50": round(float(np.nanpercentile(z, 50)), 3) if valid.any() else None,
            "probability_mapping": info,
            "baseline": baseline.to_dict(),
            "assumptions": (
                "Flood detected as a robust negative deviation from the pixel's own "
                "seasonal median over a single Sentinel-1 relative orbit. Zero labels "
                "are used. Under-sampled pixels return NaN rather than 'dry'. "
                "Agricultural drainage and harvest can also darken a pixel; seasonal "
                "binning reduces but does not eliminate that. Non-operational; not an "
                "official warning."
            ),
        },
    )


def inundation_history(
    series: S1Series,
    baseline: SeasonalBaseline,
    unit_masks: dict[str, np.ndarray],
    *,
    method: str = "gaussian_mixture",
    params: dict[str, float] | None = None,
    open_water_threshold: float = 0.5,
    permanent_water: np.ndarray | None = None,
    row_chunk: int = 128,
) -> list[dict[str, object]]:
    """Return the per-unit open-water fraction for every acquisition in the series.

    This is the product a single pre/post pair cannot produce: a multi-year
    inundation frequency per reporting unit. It answers "how often does this
    tambon actually flood?" from observation rather than from terrain, and it
    gives Component C a validation target with real meaning -- does the
    susceptibility surface predict multi-year inundation frequency? -- in place
    of an AUC against one residual post-peak extent.
    """

    rows: list[dict[str, object]] = []
    for scene in series.scenes:
        scene_db = to_db(scene.read(baseline.polarisation))
        result = detect_temporal_flood(
            scene_db,
            baseline,
            scene.month,
            method=method,
            params=params,
            open_water_threshold=open_water_threshold,
            permanent_water=permanent_water,
        )
        for unit_id, mask in unit_masks.items():
            selector = np.asarray(mask, dtype=bool)
            if selector.shape != result.open_water.shape:
                raise TemporalSarError(
                    f"unit mask {unit_id} shape {selector.shape} does not match "
                    f"scene {result.open_water.shape}."
                )
            valid = np.isfinite(result.zscore) & selector
            rows.append(
                {
                    "unit_id": unit_id,
                    "date": scene.date,
                    "item_id": scene.item_id,
                    "season_bin": result.metrics["season_bin"],
                    "open_water_fraction": round(float(result.open_water[selector].mean()), 6),
                    "valid_fraction": round(float(valid.sum() / max(1, int(selector.sum()))), 5),
                }
            )
    return rows


def inundation_frequency(
    history: list[dict[str, object]], *, threshold: float = 0.01
) -> dict[str, dict[str, object]]:
    """Summarise a history into a per-unit inundation frequency.

    ``threshold`` is the open-water fraction above which an acquisition counts as
    an inundation event for that unit.
    """

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in history:
        grouped.setdefault(str(row["unit_id"]), []).append(row)

    summary: dict[str, dict[str, object]] = {}
    for unit_id, rows in grouped.items():
        fractions = [float(r["open_water_fraction"]) for r in rows]
        flagged = [f for f in fractions if f >= threshold]
        summary[unit_id] = {
            "n_acquisitions": len(rows),
            "n_inundated": len(flagged),
            "inundation_frequency": round(len(flagged) / len(rows), 4) if rows else 0.0,
            "max_open_water_fraction": round(max(fractions), 6) if fractions else 0.0,
            "median_open_water_fraction": (
                round(float(np.median(fractions)), 6) if fractions else 0.0
            ),
            "threshold": threshold,
        }
    return summary


def parse_datetime(value: str) -> datetime:
    """Parse an ISO acquisition timestamp, tolerating a trailing ``Z``."""

    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
