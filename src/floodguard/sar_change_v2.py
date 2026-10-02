"""Sentinel-1 temporal change detection: M1-literal and M1-v2 (plan task A3).

Two versioned radar candidates, both research-only:

* **M1-literal** follows the proposal's "Method 1. Sentinel-1 temporal change
  detection" as written: speckle control, dB conversion, delta-VV, delta-VH and
  the VV/VH ratio, an Otsu threshold on the valid delta-VH pixels of the image,
  strong negative change as the candidate, and removal of isolated speckle.
* **M1-v2** is the restructuring plan's revision: a refined-Lee speckle filter,
  split-based selection of bimodal image blocks (Ashman D above 2), a global
  Kittler-Illingworth threshold on the pooled histogram of the selected
  blocks, an Otsu comparator, and one-sided or bidirectional change.

Everything here is a pure function of arrays. Nothing reads a label, a file
or the clock. The functions use NumPy only.

Inputs are linear sigma0 backscatter with VV before VH, shape ``(2, H, W)``.
Outputs use the codes 0 (not a candidate), 1 (flood candidate) and 255
(abstained: unsupported radiometry, or the method declined to set a
threshold). A candidate is not an observation and never a warning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np

CANDIDATE_NO: int = 0
CANDIDATE_YES: int = 1
CANDIDATE_ABSTAIN: int = 255

CHANNELS: tuple[str, ...] = ("vh", "vv", "mean_vv_vh")
DIRECTIONS: tuple[str, ...] = ("darkening", "bidirectional")
THRESHOLD_SCOPES: tuple[str, ...] = ("per_tile", "pooled_run")
THRESHOLD_METHODS: tuple[str, ...] = ("kittler_illingworth", "otsu")
SIDES: tuple[str, ...] = ("darkening", "brightening")

# Sentinel-1 IW GRD high-resolution products have about 4.4 equivalent looks
# (ESA Sentinel-1 product definition). Fixed here, never tuned.
SENTINEL1_IW_GRDH_LOOKS: float = 4.4


class SarChangeError(ValueError):
    """The arrays or the configuration cannot support the method."""


@dataclass(frozen=True)
class HistogramSpec:
    """Fixed dB histogram used by every threshold in this module."""

    lower_db: float = -25.0
    upper_db: float = 25.0
    bin_width_db: float = 0.1

    @property
    def bins(self) -> int:
        return int(round((self.upper_db - self.lower_db) / self.bin_width_db))


@dataclass(frozen=True)
class M1LiteralConfig:
    """Fixed reading of the proposal's Method 1. Nothing here is tuned."""

    speckle_filter: str = "lee_local_statistics"
    speckle_window_pixels: int = 5
    equivalent_looks: float = SENTINEL1_IW_GRDH_LOOKS
    threshold_feature: str = "delta_vh_db_post_minus_pre"
    threshold_method: str = "otsu_on_all_valid_pixels_of_the_image"
    candidate_rule: str = "delta_vh_below_threshold_and_below_zero"
    isolated_speckle_cleaning: str = "majority_3x3_at_least_5_of_9"
    histogram: HistogramSpec = HistogramSpec()


@dataclass(frozen=True)
class M1V2Config:
    """One M1-v2 configuration. The tuned fields are marked in the docs."""

    channel: str = "vh"
    direction: str = "darkening"
    block_pixels: int = 128
    threshold_scope: str = "per_tile"
    threshold_method: str = "kittler_illingworth"
    speckle_filter: str = "refined_lee_7x7"
    equivalent_looks: float = SENTINEL1_IW_GRDH_LOOKS
    ashman_d_min: float = 2.0
    min_component_weight: float = 0.1
    min_block_valid_fraction: float = 0.5
    min_threshold_class_fraction: float = 0.01
    isolated_speckle_cleaning: str = "majority_3x3_at_least_5_of_9"
    histogram: HistogramSpec = HistogramSpec()

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise SarChangeError(f"Unknown channel: {self.channel}")
        if self.direction not in DIRECTIONS:
            raise SarChangeError(f"Unknown direction: {self.direction}")
        if self.threshold_scope not in THRESHOLD_SCOPES:
            raise SarChangeError(f"Unknown threshold scope: {self.threshold_scope}")
        if self.threshold_method not in THRESHOLD_METHODS:
            raise SarChangeError(f"Unknown threshold method: {self.threshold_method}")
        if self.block_pixels < 16:
            raise SarChangeError("block_pixels must be at least 16")
        if self.equivalent_looks <= 0:
            raise SarChangeError("equivalent_looks must be positive")

    def sides(self) -> tuple[str, ...]:
        """Change directions that this configuration thresholds."""

        return SIDES if self.direction == "bidirectional" else ("darkening",)


@dataclass(frozen=True)
class TwoGaussianFit:
    """Two-component Gaussian mixture, ordered by mean."""

    weight_low: float
    mean_low: float
    std_low: float
    weight_high: float
    mean_high: float
    std_high: float

    @property
    def ashman_d(self) -> float:
        return ashman_d(self.mean_low, self.std_low, self.mean_high, self.std_high)


@dataclass(frozen=True)
class FilteredPair:
    """Speckle-filtered pre and post backscatter in dB with a validity mask."""

    pre_db: np.ndarray
    post_db: np.ndarray
    valid: np.ndarray


# ---------------------------------------------------------------------------
# Radiometry and speckle filters
# ---------------------------------------------------------------------------


def valid_radiometry(pre: np.ndarray, post: np.ndarray) -> np.ndarray:
    """Return the cells where all four linear sigma0 values are usable.

    A cell is valid when pre VV, pre VH, post VV and post VH are all finite
    and strictly positive. Both inputs must be real arrays of shape
    ``(2, H, W)`` with VV before VH.
    """

    pre_values = np.asarray(pre)
    post_values = np.asarray(post)
    if (
        pre_values.ndim != 3
        or pre_values.shape[0] != 2
        or pre_values.shape[1] < 1
        or pre_values.shape[2] < 1
        or post_values.shape != pre_values.shape
        or not np.issubdtype(pre_values.dtype, np.number)
        or not np.issubdtype(post_values.dtype, np.number)
        or np.issubdtype(pre_values.dtype, np.complexfloating)
        or np.issubdtype(post_values.dtype, np.complexfloating)
    ):
        raise SarChangeError("pre and post must be real numeric arrays of shape (2, H, W)")
    with np.errstate(invalid="ignore"):
        return np.all(
            np.isfinite(pre_values)
            & np.isfinite(post_values)
            & (pre_values > 0)
            & (post_values > 0),
            axis=0,
        )


def _window_sum(padded: np.ndarray, offsets: list[tuple[int, int]], pad: int) -> np.ndarray:
    """Sum ``padded`` over a set of (row, column) offsets around each cell."""

    height = padded.shape[0] - 2 * pad
    width = padded.shape[1] - 2 * pad
    total = np.zeros((height, width), dtype="float64")
    for row_offset, column_offset in offsets:
        total += padded[
            pad + row_offset : pad + row_offset + height,
            pad + column_offset : pad + column_offset + width,
        ]
    return total


def _square_offsets(radius: int) -> list[tuple[int, int]]:
    return [
        (row, column)
        for row in range(-radius, radius + 1)
        for column in range(-radius, radius + 1)
    ]


def _mmse_estimate(
    value: np.ndarray, mean: np.ndarray, variance: np.ndarray, equivalent_looks: float
) -> np.ndarray:
    """Lee's minimum-mean-square-error estimate for multiplicative speckle."""

    noise = 1.0 / equivalent_looks
    signal_variance = np.maximum(variance - mean * mean * noise, 0.0) / (1.0 + noise)
    weight = np.divide(
        signal_variance, variance, out=np.zeros_like(variance), where=variance > 0
    )
    np.clip(weight, 0.0, 1.0, out=weight)
    return mean + weight * (value - mean)


def lee_filter(
    linear: np.ndarray,
    valid: np.ndarray,
    *,
    window_pixels: int = 5,
    equivalent_looks: float = SENTINEL1_IW_GRDH_LOOKS,
) -> np.ndarray:
    """Apply the Lee (1980) local-statistics speckle filter to linear power.

    Local mean and variance come from the valid cells of a square window.
    Invalid cells are returned as NaN and never enter a neighbour's
    statistics. ``linear`` and ``valid`` share the shape ``(H, W)``.
    """

    values = np.asarray(linear, dtype="float64")
    mask = np.asarray(valid, dtype=bool)
    if values.ndim != 2 or mask.shape != values.shape:
        raise SarChangeError("linear and valid must share a two-dimensional shape")
    if window_pixels < 3 or window_pixels % 2 == 0:
        raise SarChangeError("window_pixels must be an odd number of at least 3")
    if equivalent_looks <= 0:
        raise SarChangeError("equivalent_looks must be positive")
    radius = window_pixels // 2
    clean = np.where(mask, values, 0.0)
    offsets = _square_offsets(radius)
    count = _window_sum(np.pad(mask.astype("float64"), radius), offsets, radius)
    total = _window_sum(np.pad(clean, radius), offsets, radius)
    squares = _window_sum(np.pad(clean * clean, radius), offsets, radius)
    safe = np.maximum(count, 1.0)
    mean = total / safe
    variance = np.maximum(squares / safe - mean * mean, 0.0)
    filtered = _mmse_estimate(clean, mean, variance, equivalent_looks)
    return np.where(mask, filtered, np.nan)


def _half_window_offsets() -> list[list[tuple[int, int]]]:
    """The eight edge-aligned 28-cell half windows of the refined-Lee filter.

    Order: west, east, north, south, north-east, south-west, north-west,
    south-east. Rows grow downwards, so north means a negative row offset.
    """

    square = _square_offsets(3)
    rules = (
        lambda row, column: column <= 0,
        lambda row, column: column >= 0,
        lambda row, column: row <= 0,
        lambda row, column: row >= 0,
        lambda row, column: column >= row,
        lambda row, column: column <= row,
        lambda row, column: column + row <= 0,
        lambda row, column: column + row >= 0,
    )
    return [[offset for offset in square if rule(*offset)] for rule in rules]


def refined_lee_filter(
    linear: np.ndarray,
    valid: np.ndarray,
    *,
    equivalent_looks: float = SENTINEL1_IW_GRDH_LOOKS,
) -> np.ndarray:
    """Apply the refined-Lee (Lee 1981) edge-preserving filter, 7 by 7.

    Nine 3 by 3 sub-window means inside the 7 by 7 window give four edge
    gradients. The strongest gradient picks an edge orientation, and the side
    whose mean is closer to the centre mean picks one of eight 28-cell half
    windows. Local mean and variance from that half window feed Lee's
    minimum-mean-square-error estimate. Where the sub-window means are not
    all defined (invalid neighbours or the image border), the whole 7 by 7
    window is used instead. Invalid cells are returned as NaN.
    """

    values = np.asarray(linear, dtype="float64")
    mask = np.asarray(valid, dtype=bool)
    if values.ndim != 2 or mask.shape != values.shape:
        raise SarChangeError("linear and valid must share a two-dimensional shape")
    if equivalent_looks <= 0:
        raise SarChangeError("equivalent_looks must be positive")
    pad = 3
    clean = np.where(mask, values, 0.0)
    weights = np.pad(mask.astype("float64"), pad)
    padded = np.pad(clean, pad)
    padded_squares = np.pad(clean * clean, pad)

    # Nine 3 by 3 sub-window means, sampled two cells apart around each cell.
    three = _square_offsets(1)
    sub_count = _window_sum(np.pad(weights, 1), three, 1)
    sub_total = _window_sum(np.pad(padded, 1), three, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        sub_mean_padded = np.where(sub_count > 0, sub_total / sub_count, np.nan)
    # Cells outside the image have no mean: mark them undefined.
    outside = np.ones_like(weights, dtype=bool)
    outside[pad:-pad, pad:-pad] = False
    sub_mean_padded[outside] = np.nan
    height, width = values.shape

    def sub_mean(row: int, column: int) -> np.ndarray:
        return sub_mean_padded[
            pad + 2 * row : pad + 2 * row + height,
            pad + 2 * column : pad + 2 * column + width,
        ]

    north_west, north, north_east = sub_mean(-1, -1), sub_mean(-1, 0), sub_mean(-1, 1)
    west, centre, east = sub_mean(0, -1), sub_mean(0, 0), sub_mean(0, 1)
    south_west, south, south_east = sub_mean(1, -1), sub_mean(1, 0), sub_mean(1, 1)
    gradients = np.stack(
        [
            np.abs((north_east + east + south_east) - (north_west + west + south_west)),
            np.abs((north + north_east + east) - (west + south_west + south)),
            np.abs((north_west + north + north_east) - (south_west + south + south_east)),
            np.abs((north_west + north + west) - (east + south + south_east)),
        ]
    )
    defined = np.isfinite(gradients).all(axis=0)
    strongest = np.argmax(np.where(np.isfinite(gradients), gradients, -1.0), axis=0)
    first_side = (west, north_east, north, north_west)
    second_side = (east, south_west, south, south_east)
    # Half-window index: orientation k chooses between window 2k and 2k + 1.
    choice = np.full(values.shape, 8, dtype="int8")
    for orientation in range(4):
        selected = defined & (strongest == orientation)
        with np.errstate(invalid="ignore"):
            first_closer = np.abs(first_side[orientation] - centre) <= np.abs(
                second_side[orientation] - centre
            )
        choice[selected & first_closer] = 2 * orientation
        choice[selected & ~first_closer] = 2 * orientation + 1
    # The diagonal orientations are stored in the order used by
    # _half_window_offsets: 0 west, 1 east, 2 north-east, 3 south-west,
    # 4 north, 5 south, 6 north-west, 7 south-east.
    window_for_choice = (0, 1, 4, 5, 2, 3, 6, 7)

    mean = np.zeros(values.shape, dtype="float64")
    variance = np.zeros(values.shape, dtype="float64")
    half_windows = _half_window_offsets()
    windows = [half_windows[index] for index in window_for_choice] + [_square_offsets(3)]
    for index, offsets in enumerate(windows):
        selected = choice == index
        if not selected.any():
            continue
        count = np.maximum(_window_sum(weights, offsets, pad), 1.0)
        local_mean = _window_sum(padded, offsets, pad) / count
        local_variance = np.maximum(
            _window_sum(padded_squares, offsets, pad) / count - local_mean * local_mean,
            0.0,
        )
        mean[selected] = local_mean[selected]
        variance[selected] = local_variance[selected]
    filtered = _mmse_estimate(clean, mean, variance, equivalent_looks)
    return np.where(mask, filtered, np.nan)


def filter_pair(
    pre: np.ndarray,
    post: np.ndarray,
    *,
    speckle_filter: str,
    equivalent_looks: float = SENTINEL1_IW_GRDH_LOOKS,
    window_pixels: int = 5,
) -> FilteredPair:
    """Speckle-filter both dates in linear power and convert them to dB.

    ``speckle_filter`` is ``"lee_local_statistics"`` (square window of
    ``window_pixels``) or ``"refined_lee_7x7"``. Cells that fail
    :func:`valid_radiometry` are NaN in both outputs.
    """

    valid = valid_radiometry(pre, post)
    pre_db = np.full(np.asarray(pre).shape, np.nan, dtype="float32")
    post_db = np.full(np.asarray(post).shape, np.nan, dtype="float32")
    for source, target in ((pre, pre_db), (post, post_db)):
        for band in range(2):
            band_values = np.asarray(source[band], dtype="float64")
            if speckle_filter == "lee_local_statistics":
                filtered = lee_filter(
                    band_values,
                    valid,
                    window_pixels=window_pixels,
                    equivalent_looks=equivalent_looks,
                )
            elif speckle_filter == "refined_lee_7x7":
                filtered = refined_lee_filter(
                    band_values, valid, equivalent_looks=equivalent_looks
                )
            else:
                raise SarChangeError(f"Unknown speckle filter: {speckle_filter}")
            with np.errstate(divide="ignore", invalid="ignore"):
                target[band][valid] = (10.0 * np.log10(filtered[valid])).astype("float32")
    return FilteredPair(pre_db=pre_db, post_db=post_db, valid=valid)


# ---------------------------------------------------------------------------
# Histograms, thresholds and bimodality
# ---------------------------------------------------------------------------


def histogram_db(samples: np.ndarray, spec: HistogramSpec = HistogramSpec()) -> np.ndarray:
    """Count finite samples in the fixed dB bins; out-of-range values are dropped."""

    values = np.asarray(samples, dtype="float64").ravel()
    values = values[np.isfinite(values)]
    counts, _ = np.histogram(values, bins=spec.bins, range=(spec.lower_db, spec.upper_db))
    return counts.astype("int64")


def _bin_centres(spec: HistogramSpec) -> np.ndarray:
    edges = np.linspace(spec.lower_db, spec.upper_db, spec.bins + 1)
    return (edges[:-1] + edges[1:]) / 2.0


def _class_moments(
    counts: np.ndarray, spec: HistogramSpec
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Cumulative class probabilities, means and variances for every split."""

    centres = _bin_centres(spec)
    probability = counts.astype("float64") / counts.sum()
    cumulative = np.cumsum(probability)[:-1]
    first = np.cumsum(probability * centres)
    second = np.cumsum(probability * centres * centres)
    low_weight = cumulative
    high_weight = 1.0 - cumulative
    with np.errstate(divide="ignore", invalid="ignore"):
        low_mean = first[:-1] / low_weight
        high_mean = (first[-1] - first[:-1]) / high_weight
        low_variance = second[:-1] / low_weight - low_mean * low_mean
        high_variance = (second[-1] - second[:-1]) / high_weight - high_mean * high_mean
    return low_weight, high_weight, low_mean, high_mean, low_variance, high_variance


def otsu_threshold(counts: np.ndarray, spec: HistogramSpec = HistogramSpec()) -> float | None:
    """Otsu (1979): the split that maximises the between-class variance.

    Returns the upper edge of the last bin of the lower class, in dB, or
    ``None`` when the histogram has fewer than two occupied bins.
    """

    counts = np.asarray(counts)
    if counts.shape != (spec.bins,):
        raise SarChangeError("counts must match the histogram specification")
    if int((counts > 0).sum()) < 2:
        return None
    low_weight, high_weight, low_mean, high_mean, _, _ = _class_moments(counts, spec)
    usable = (low_weight > 0) & (high_weight > 0)
    between = np.where(
        usable, low_weight * high_weight * (high_mean - low_mean) ** 2, -np.inf
    )
    split = int(np.argmax(between))
    return float(round(spec.lower_db + (split + 1) * spec.bin_width_db, 6))


def kittler_illingworth_threshold(
    counts: np.ndarray,
    spec: HistogramSpec = HistogramSpec(),
    *,
    min_class_fraction: float = 0.01,
) -> float | None:
    """Kittler and Illingworth (1986) minimum-error threshold.

    Minimises ``1 + 2 (P1 ln s1 + P2 ln s2) - 2 (P1 ln P1 + P2 ln P2)`` over
    the splits where both classes hold at least ``min_class_fraction`` of the
    samples. One twelfth of the squared bin width is added to each class
    variance so a class inside one bin stays finite. Returns ``None`` when no
    split is admissible.
    """

    counts = np.asarray(counts)
    if counts.shape != (spec.bins,):
        raise SarChangeError("counts must match the histogram specification")
    if not 0 < min_class_fraction < 0.5:
        raise SarChangeError("min_class_fraction must lie between 0 and 0.5")
    if int((counts > 0).sum()) < 2:
        return None
    low_weight, high_weight, _, _, low_variance, high_variance = _class_moments(counts, spec)
    floor = spec.bin_width_db**2 / 12.0
    usable = (low_weight >= min_class_fraction) & (high_weight >= min_class_fraction)
    if not usable.any():
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        criterion = (
            1.0
            + low_weight * np.log(np.maximum(low_variance, 0.0) + floor)
            + high_weight * np.log(np.maximum(high_variance, 0.0) + floor)
            - 2.0 * (low_weight * np.log(low_weight) + high_weight * np.log(high_weight))
        )
    criterion = np.where(usable & np.isfinite(criterion), criterion, np.inf)
    split = int(np.argmin(criterion))
    if not np.isfinite(criterion[split]):
        return None
    return float(round(spec.lower_db + (split + 1) * spec.bin_width_db, 6))


def ashman_d(mean_a: float, std_a: float, mean_b: float, std_b: float) -> float:
    """Ashman's D: ``sqrt(2) |mean_a - mean_b| / sqrt(std_a^2 + std_b^2)``.

    Values above 2 indicate a clean separation of two Gaussian modes
    (Ashman, Bird and Zepf 1994). Two zero spreads give infinity when the
    means differ and zero when they coincide.
    """

    if std_a < 0 or std_b < 0:
        raise SarChangeError("standard deviations must not be negative")
    spread = float(np.hypot(std_a, std_b))
    separation = abs(float(mean_a) - float(mean_b))
    if spread == 0.0:
        return float("inf") if separation > 0 else 0.0
    return float(np.sqrt(2.0) * separation / spread)


def fit_two_gaussians(
    counts: np.ndarray,
    spec: HistogramSpec = HistogramSpec(),
    *,
    max_iterations: int = 500,
    tolerance: float = 1e-9,
) -> TwoGaussianFit | None:
    """Fit a two-component Gaussian mixture to a histogram by EM.

    The start is deterministic: the two classes of the Otsu split. Ashman's D
    must come from fitted components, not from the two halves of a split: the
    halves of a single Gaussian are narrow and far apart (D about 2.65), so
    truncated moments would call every unimodal histogram bimodal. Returns
    ``None`` when the histogram cannot be split.
    """

    counts = np.asarray(counts, dtype="float64")
    if counts.shape != (spec.bins,):
        raise SarChangeError("counts must match the histogram specification")
    total = counts.sum()
    start = otsu_threshold(counts, spec)
    if total <= 0 or start is None:
        return None
    centres = _bin_centres(spec)
    floor = spec.bin_width_db**2 / 12.0
    low = centres < start
    weights = np.empty(2)
    means = np.empty(2)
    variances = np.empty(2)
    for index, members in enumerate((low, ~low)):
        mass = counts[members].sum()
        if mass <= 0:
            return None
        weights[index] = mass / total
        means[index] = (counts[members] * centres[members]).sum() / mass
        variances[index] = (
            (counts[members] * (centres[members] - means[index]) ** 2).sum() / mass + floor
        )
    previous = -np.inf
    for _ in range(max_iterations):
        density = (
            weights[:, None]
            / np.sqrt(2.0 * np.pi * variances[:, None])
            * np.exp(-0.5 * (centres[None, :] - means[:, None]) ** 2 / variances[:, None])
        )
        mixture = np.maximum(density.sum(axis=0), 1e-300)
        likelihood = float((counts * np.log(mixture)).sum())
        responsibility = density / mixture
        mass = (responsibility * counts[None, :]).sum(axis=1)
        if np.any(mass <= 0):
            return None
        weights = mass / total
        means = (responsibility * counts[None, :] * centres[None, :]).sum(axis=1) / mass
        variances = (
            (responsibility * counts[None, :] * (centres[None, :] - means[:, None]) ** 2).sum(
                axis=1
            )
            / mass
            + floor
        )
        if abs(likelihood - previous) <= tolerance * total:
            break
        previous = likelihood
    order = np.argsort(means, kind="stable")
    return TwoGaussianFit(
        weight_low=float(weights[order[0]]),
        mean_low=float(means[order[0]]),
        std_low=float(np.sqrt(variances[order[0]])),
        weight_high=float(weights[order[1]]),
        mean_high=float(means[order[1]]),
        std_high=float(np.sqrt(variances[order[1]])),
    )


def block_is_bimodal(
    fit: TwoGaussianFit | None, *, ashman_d_min: float, min_component_weight: float
) -> tuple[bool, str | None]:
    """Decide whether a block's change histogram separates change from no change.

    The block's score is positive in the direction of interest. It qualifies
    when the fitted components are separated (Ashman D above ``ashman_d_min``),
    neither is negligible (weight at least ``min_component_weight``), the
    upper component is a change in the direction of interest (mean above
    zero) and the lower component is the one closer to no change.
    """

    if fit is None:
        return False, "no_two_component_fit"
    if fit.ashman_d <= ashman_d_min:
        return False, "ashman_d_not_above_minimum"
    if min(fit.weight_low, fit.weight_high) < min_component_weight:
        return False, "component_weight_below_minimum"
    if fit.mean_high <= 0:
        return False, "upper_component_is_not_a_change_in_this_direction"
    if abs(fit.mean_low) >= abs(fit.mean_high):
        return False, "lower_component_is_not_the_unchanged_one"
    return True, None


def select_bimodal_blocks(
    score: np.ndarray, valid: np.ndarray, config: M1V2Config
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Split an image into square blocks and keep the bimodal ones.

    Returns the pooled histogram of the selected blocks and one receipt per
    block. Blocks do not overlap; a partial block at the right or bottom
    border is used when enough of it is valid.
    """

    values = np.asarray(score)
    mask = np.asarray(valid, dtype=bool)
    if values.ndim != 2 or mask.shape != values.shape:
        raise SarChangeError("score and valid must share a two-dimensional shape")
    spec = config.histogram
    pooled = np.zeros(spec.bins, dtype="int64")
    receipts: list[dict[str, Any]] = []
    size = config.block_pixels
    for row in range(0, values.shape[0], size):
        for column in range(0, values.shape[1], size):
            window = np.s_[row : row + size, column : column + size]
            block_valid = mask[window]
            receipt: dict[str, Any] = {
                "row": row,
                "column": column,
                "valid_fraction": round(float(block_valid.sum()) / (size * size), 6),
                "selected": False,
            }
            if block_valid.sum() < config.min_block_valid_fraction * size * size:
                receipt["reason"] = "too_few_valid_cells"
                receipts.append(receipt)
                continue
            counts = histogram_db(values[window][block_valid], spec)
            fit = fit_two_gaussians(counts, spec)
            selected, reason = block_is_bimodal(
                fit,
                ashman_d_min=config.ashman_d_min,
                min_component_weight=config.min_component_weight,
            )
            receipt["selected"] = selected
            receipt["reason"] = reason
            if fit is not None:
                receipt["ashman_d"] = round(fit.ashman_d, 4)
                receipt["fit"] = {key: round(value, 4) for key, value in asdict(fit).items()}
            if selected:
                pooled += counts
            receipts.append(receipt)
    return pooled, receipts


def threshold_from_histogram(counts: np.ndarray, config: M1V2Config) -> float | None:
    """Threshold the pooled histogram; a threshold at or below zero is refused.

    The score is positive in the direction of change, so a threshold that is
    not positive would flag cells that did not change in that direction.
    """

    if int(np.asarray(counts).sum()) == 0:
        return None
    if config.threshold_method == "kittler_illingworth":
        threshold = kittler_illingworth_threshold(
            counts, config.histogram, min_class_fraction=config.min_threshold_class_fraction
        )
    else:
        threshold = otsu_threshold(counts, config.histogram)
    if threshold is None or threshold <= 0:
        return None
    return threshold


def majority_filter(candidate: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Remove isolated candidate cells: keep a candidate with 5 of 9 neighbours.

    A candidate cell stays only if at least five of the nine cells of its
    3 by 3 neighbourhood (itself included) are valid candidates. The filter
    removes cells and never adds one.
    """

    flags = np.asarray(candidate, dtype=bool) & np.asarray(valid, dtype=bool)
    if flags.ndim != 2:
        raise SarChangeError("candidate must be two-dimensional")
    support = _window_sum(np.pad(flags.astype("float64"), 1), _square_offsets(1), 1)
    return flags & (support >= 5)


# ---------------------------------------------------------------------------
# M1-literal
# ---------------------------------------------------------------------------


def m1_literal_from_filtered(
    filtered: FilteredPair, config: M1LiteralConfig = M1LiteralConfig()
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply the proposal's threshold and cleaning steps to a filtered pair."""

    valid = filtered.valid
    delta_vv = filtered.post_db[0] - filtered.pre_db[0]
    delta_vh = filtered.post_db[1] - filtered.pre_db[1]
    ratio_pre = filtered.pre_db[0] - filtered.pre_db[1]
    ratio_post = filtered.post_db[0] - filtered.post_db[1]
    candidate = np.full(valid.shape, CANDIDATE_ABSTAIN, dtype="uint8")
    counts = histogram_db(delta_vh[valid], config.histogram)
    threshold = otsu_threshold(counts, config.histogram) if counts.sum() else None
    summary: dict[str, Any] = {
        "method": "m1_literal",
        "configuration": asdict(config),
        "total_cells": int(valid.size),
        "valid_cells": int(valid.sum()),
        "invalid_cells": int((~valid).sum()),
        "otsu_threshold_delta_vh_db": threshold,
        "abstained": threshold is None,
        "abstention_reason": None if threshold is not None else "no_threshold",
    }
    if threshold is None:
        summary.update(candidate_cells=0, cells_removed_by_cleaning=0)
        return candidate, summary
    with np.errstate(invalid="ignore"):
        raw = valid & (delta_vh < threshold) & (delta_vh < 0)
    cleaned = majority_filter(raw, valid)
    candidate[valid] = CANDIDATE_NO
    candidate[cleaned] = CANDIDATE_YES

    def median(values: np.ndarray) -> float | None:
        return round(float(np.median(values[valid])), 4) if valid.any() else None

    summary.update(
        candidate_cells=int(cleaned.sum()),
        cells_removed_by_cleaning=int(raw.sum() - cleaned.sum()),
        median_delta_vv_db=median(delta_vv),
        median_delta_vh_db=median(delta_vh),
        median_vv_vh_ratio_db_pre=median(ratio_pre),
        median_vv_vh_ratio_db_post=median(ratio_post),
    )
    return candidate, summary


def m1_literal_predict(
    pre: np.ndarray, post: np.ndarray, config: M1LiteralConfig = M1LiteralConfig()
) -> tuple[np.ndarray, dict[str, Any]]:
    """Run M1-literal on one image pair of linear sigma0 VV/VH.

    Steps, in the proposal's order: Lee speckle filter; dB conversion;
    delta-VV, delta-VH (post minus pre) and the VV/VH ratio; an Otsu threshold
    on all valid delta-VH cells of the image; cells below the threshold and
    below zero become candidates; isolated candidates are removed. The steps
    that need a DEM, a permanent-water layer or the acquisition geometry
    (terrain correction, permanent-water and steep-terrain removal, shadow
    and layover flags) are not part of this function.
    """

    filtered = filter_pair(
        pre,
        post,
        speckle_filter=config.speckle_filter,
        equivalent_looks=config.equivalent_looks,
        window_pixels=config.speckle_window_pixels,
    )
    return m1_literal_from_filtered(filtered, config)


# ---------------------------------------------------------------------------
# M1-v2
# ---------------------------------------------------------------------------


def change_score(filtered: FilteredPair, channel: str, side: str) -> np.ndarray:
    """Change in dB, positive in the direction of ``side``.

    ``channel`` picks delta-VH, delta-VV or their mean (post minus pre).
    ``side`` is ``"darkening"`` (the score is minus the change) or
    ``"brightening"`` (the score is the change).
    """

    delta_vv = filtered.post_db[0] - filtered.pre_db[0]
    delta_vh = filtered.post_db[1] - filtered.pre_db[1]
    if channel == "vh":
        delta = delta_vh
    elif channel == "vv":
        delta = delta_vv
    elif channel == "mean_vv_vh":
        delta = (delta_vv + delta_vh) / np.float32(2)
    else:
        raise SarChangeError(f"Unknown channel: {channel}")
    if side == "darkening":
        return -delta
    if side == "brightening":
        return delta
    raise SarChangeError(f"Unknown side: {side}")


BlockSelection = tuple[np.ndarray, list[dict[str, Any]]]


def select_blocks_for_side(
    filtered: FilteredPair, config: M1V2Config, side: str
) -> BlockSelection:
    """Select the bimodal blocks of one image for one change direction.

    The result depends only on the channel, the side, the block size and the
    fixed selection parameters, so callers may reuse it across configurations
    that share them.
    """

    return select_bimodal_blocks(
        change_score(filtered, config.channel, side), filtered.valid, config
    )


def m1_v2_predict_filtered(
    tiles: Mapping[str, FilteredPair],
    config: M1V2Config,
    *,
    selections: Mapping[str, Mapping[str, BlockSelection]] | None = None,
) -> dict[str, tuple[np.ndarray, dict[str, Any]]]:
    """Run M1-v2 on speckle-filtered image pairs.

    ``tiles`` maps an image name to its filtered pair. With the scope
    ``"per_tile"`` every image sets its own threshold from its own bimodal
    blocks and abstains (code 255 everywhere) when it has none. With
    ``"pooled_run"`` the selected blocks of all images in the call share one
    histogram and one threshold, so the result depends on which images are
    passed together. With the bidirectional direction each side has its own
    threshold and a cell is a candidate when either side flags it; an image
    is classified when at least one side has a threshold.

    ``selections`` may carry block selections already computed with
    :func:`select_blocks_for_side` for the same channel, block size and
    selection parameters; it changes the cost, never the result.
    """

    names = sorted(tiles)
    sides = config.sides()
    scores = {
        name: {side: change_score(tiles[name], config.channel, side) for side in sides}
        for name in names
    }
    selection = {
        name: {
            side: (
                selections[name][side]
                if selections is not None
                else select_bimodal_blocks(scores[name][side], tiles[name].valid, config)
            )
            for side in sides
        }
        for name in names
    }
    thresholds: dict[str, dict[str, float | None]] = {name: {} for name in names}
    for side in sides:
        if config.threshold_scope == "pooled_run":
            pooled = np.zeros(config.histogram.bins, dtype="int64")
            for name in names:
                pooled += selection[name][side][0]
            shared = threshold_from_histogram(pooled, config)
            for name in names:
                thresholds[name][side] = shared
        else:
            for name in names:
                thresholds[name][side] = threshold_from_histogram(
                    selection[name][side][0], config
                )

    results: dict[str, tuple[np.ndarray, dict[str, Any]]] = {}
    for name in names:
        valid = tiles[name].valid
        candidate = np.full(valid.shape, CANDIDATE_ABSTAIN, dtype="uint8")
        active = [side for side in sides if thresholds[name][side] is not None]
        raw = np.zeros(valid.shape, dtype=bool)
        for side in active:
            with np.errstate(invalid="ignore"):
                raw |= valid & (scores[name][side] >= thresholds[name][side])
        cleaned = majority_filter(raw, valid) if active else raw
        if active:
            candidate[valid] = CANDIDATE_NO
            candidate[cleaned] = CANDIDATE_YES
        block_summary = {}
        for side in sides:
            receipts = selection[name][side][1]
            reasons: dict[str, int] = {}
            for receipt in receipts:
                if not receipt["selected"]:
                    reasons[receipt["reason"]] = reasons.get(receipt["reason"], 0) + 1
            block_summary[side] = {
                "blocks": len(receipts),
                "selected_blocks": sum(receipt["selected"] for receipt in receipts),
                "rejection_reasons": dict(sorted(reasons.items())),
                "threshold_db": thresholds[name][side],
            }
        results[name] = (
            candidate,
            {
                "method": "m1_v2",
                "total_cells": int(valid.size),
                "valid_cells": int(valid.sum()),
                "invalid_cells": int((~valid).sum()),
                "abstained": not active,
                "abstention_reason": None if active else "no_bimodal_block_or_no_threshold",
                "active_sides": active,
                "sides": block_summary,
                "candidate_cells": int(cleaned.sum()),
                "cells_removed_by_cleaning": int(raw.sum() - cleaned.sum()),
            },
        )
    return results


def m1_v2_predict(
    pairs: Mapping[str, tuple[np.ndarray, np.ndarray]], config: M1V2Config
) -> dict[str, tuple[np.ndarray, dict[str, Any]]]:
    """Run M1-v2 on raw linear sigma0 image pairs.

    ``pairs`` maps an image name to ``(pre, post)``, each ``(2, H, W)`` with
    VV before VH. See :func:`m1_v2_predict_filtered` for the decision rule.
    """

    filtered = {
        name: filter_pair(
            pre,
            post,
            speckle_filter=config.speckle_filter,
            equivalent_looks=config.equivalent_looks,
        )
        for name, (pre, post) in pairs.items()
    }
    return m1_v2_predict_filtered(filtered, config)


def config_to_json(config: M1V2Config | M1LiteralConfig) -> dict[str, Any]:
    """Plain, JSON-ready form of a configuration."""

    return asdict(config)


def m1_v2_config_from_json(value: Mapping[str, Any]) -> M1V2Config:
    """Rebuild a configuration from :func:`config_to_json` output."""

    fields = dict(value)
    histogram = fields.pop("histogram", None)
    if histogram is not None:
        fields["histogram"] = HistogramSpec(**histogram)
    return M1V2Config(**fields)
