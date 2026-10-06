"""Statistics of the abstention diagnosis (restructuring plan v2, section 4.2, row A1).

Plan row A1 asks why threshold-only change detection failed at the Sentinel-1 pass of 15 September 2024,
23:16 UTC (16 September, 06:16 in Thailand), with team-owned or cleared numbers only. This module holds the
arithmetic of those figures and nothing else. Each function takes arrays or plain values, so it can be
tested on invented data; the scripts under ``scripts/diagnostics/`` read the real files, call these
functions and write a receipt (:mod:`floodguard.diagnosis_run`).

What the figures are, and are not:

* The **between-class variance fraction** is the share of a histogram's variance that an Otsu split
  explains. The retired M2 method asked for at least 0.72 of it in every window
  (``AdaptiveOtsuConfig.min_between_variance_fraction``). A single normal (bell-shaped) population split at
  its mean explains 2/pi of its variance (0.637), so it does not pass. That holds for a normal population
  only: a single flat-topped (uniform) population explains 3/4 of its variance and does pass, so a window
  that passed the gate is not shown to hold two populations.
* The **rank statistic** (:func:`rank_auc`, the area under the ROC curve) says how often a cell inside a
  mapped layer has a larger feature value than a cell outside it. 0.5 is no separation. It is a measure of
  separation against that layer, **not** a measure of how correct a method is, and the layer it is computed
  against here is a season envelope, not an event map.

Nothing here computes an FPPS, an A-E class, a flood candidate or a value for a single tambon.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import math
import re
from statistics import NormalDist
from typing import Any

import numpy as np

from floodguard.label_factory.sentinel1_processing import AdaptiveOtsuConfig, _otsu_threshold

GAUSSIAN_BVF_THEORY = 2.0 / math.pi
"""Between-class variance fraction of a normal population split at its mean: (E|x|)^2 / var = 2/pi."""

UNIFORM_BVF_THEORY = 0.75
"""Between-class variance fraction of a flat-topped (uniform) population of width R split at its mean:
(R/4)^2 / (R^2/12) = 3/4."""

UNIMODAL_REASON = "unimodal_or_unstable_histogram"
"""The reason code the M2 kernel gives a window that fails the between-class variance gate only."""

THAILAND_UTC_OFFSET = timedelta(hours=7)
"""Indochina Time (ICT), the time zone of Thailand: UTC+7, with no daylight saving."""


class DiagnosisError(ValueError):
    """Raised when a diagnosis figure cannot be computed from what it was given."""


# ---------------------------------------------------------------------------
# Between-class variance fraction: theory, and the frozen M2 kernel
# ---------------------------------------------------------------------------


def m2_gate() -> float:
    """Return the between-class variance fraction the frozen M2 kernel requires of a window (0.72)."""

    return float(AdaptiveOtsuConfig().min_between_variance_fraction)


def clipped_gaussian_bvf(lower_quantile: float = 0.01, upper_quantile: float = 0.99) -> float:
    """Return the between-class variance fraction of a normal population clipped at two symmetric quantiles.

    The M2 kernel clips a window's samples at their 1st and 99th percentiles before it measures the variance.
    For a normal population clipped at ``-c`` and ``+c`` and split at zero, the mean of each half is
    ``E|x_c|`` and the between-class variance is its square; this function divides it by the variance of the
    clipped population. No histogram is involved, so the kernel itself gives a slightly different value.

    Raises:
        DiagnosisError: when the two quantiles are not symmetric about one half, or not inside (0.5, 1).
    """

    if not (0.5 < upper_quantile < 1.0) or not math.isclose(lower_quantile, 1.0 - upper_quantile, abs_tol=1e-12):
        raise DiagnosisError("the clip quantiles must be symmetric, for example 0.01 and 0.99")
    normal = NormalDist()
    clip = normal.inv_cdf(upper_quantile)
    tail = 1.0 - upper_quantile
    mean_abs = 2.0 * (normal.pdf(0.0) - normal.pdf(clip)) + 2.0 * clip * tail
    variance = (2.0 * upper_quantile - 1.0) - 2.0 * clip * normal.pdf(clip) + 2.0 * clip * clip * tail
    return mean_abs * mean_abs / variance


def kernel_decision(samples: Any, config: AdaptiveOtsuConfig | None = None) -> dict[str, Any]:
    """Pass one window of change values through the frozen M2 Otsu kernel, unchanged.

    Returns:
        ``threshold_db`` (None when the kernel declines), ``reason`` (None when it accepts) and the kernel's
        quality figures: ``between_variance_fraction``, ``class_fraction_min`` and ``mean_separation_db``.
    """

    threshold, reason, qc = _otsu_threshold(np.asarray(samples, dtype="float64"), config or AdaptiveOtsuConfig())
    return {"threshold_db": threshold, "reason": reason, **qc}


def simulate_unimodal(sample_sizes: Sequence[int], *, repeats: int, seed: int, sigma_db: float = 2.0) -> list[dict[str, Any]]:
    """Draw windows of pure normal noise and return what the frozen M2 kernel says of them.

    Each window is ``size`` independent draws from a normal population with standard deviation
    ``sigma_db``: one population, no flood class. The result does not depend on ``sigma_db`` as long as the
    1st-to-99th percentile range stays above the kernel's 1.5 dB minimum.

    Raises:
        DiagnosisError: for no repeat or a window below the kernel's minimum number of samples.
    """

    config = AdaptiveOtsuConfig()
    if repeats < 1 or any(size < config.min_valid_samples for size in sample_sizes):
        raise DiagnosisError("each simulated window needs at least the kernel's minimum of valid samples, and one repeat")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for size in sample_sizes:
        fractions: list[float] = []
        reasons: Counter[str] = Counter()
        for _ in range(repeats):
            decision = kernel_decision(rng.normal(0.0, sigma_db, int(size)), config)
            fractions.append(float(decision["between_variance_fraction"]))
            reasons[str(decision["reason"])] += 1
        rows.append({
            "samples_per_window": int(size),
            "windows": int(repeats),
            "between_variance_fraction_min": round(min(fractions), 6),
            "between_variance_fraction_mean": round(float(np.mean(fractions)), 6),
            "between_variance_fraction_max": round(max(fractions), 6),
            "windows_passing_the_gate": int(sum(value >= config.min_between_variance_fraction for value in fractions)),
            "reason_counts": dict(sorted(reasons.items())),
        })
    return rows


def simulate_uniform(sample_sizes: Sequence[int], *, repeats: int, seed: int, sigma_db: float = 2.0) -> list[dict[str, Any]]:
    """Draw windows of one flat-topped (uniform) population and return what the frozen M2 kernel says of them.

    Each window is ``size`` independent draws from one uniform population with standard deviation
    ``sigma_db`` (width ``sigma_db * sqrt(12)``), the spread of the windows of :func:`simulate_unimodal`. It is
    one population with no flood class, and it is not bell-shaped.

    Raises:
        DiagnosisError: for no repeat or a window below the kernel's minimum number of samples.
    """

    config = AdaptiveOtsuConfig()
    if repeats < 1 or any(size < config.min_valid_samples for size in sample_sizes):
        raise DiagnosisError("each simulated window needs at least the kernel's minimum of valid samples, and one repeat")
    rng = np.random.default_rng(seed)
    half_width = sigma_db * math.sqrt(3.0)
    rows: list[dict[str, Any]] = []
    for size in sample_sizes:
        fractions: list[float] = []
        reasons: Counter[str] = Counter()
        accepted = 0
        for _ in range(repeats):
            decision = kernel_decision(rng.uniform(-half_width, half_width, int(size)), config)
            fractions.append(float(decision["between_variance_fraction"]))
            reasons["accepted" if decision["reason"] is None else str(decision["reason"])] += 1
            accepted += decision["threshold_db"] is not None
        rows.append({
            "samples_per_window": int(size),
            "windows": int(repeats),
            "between_variance_fraction_min": round(min(fractions), 6),
            "between_variance_fraction_mean": round(float(np.mean(fractions)), 6),
            "between_variance_fraction_max": round(max(fractions), 6),
            "windows_passing_the_gate": int(sum(value >= config.min_between_variance_fraction for value in fractions)),
            "windows_the_kernel_accepts": int(accepted),
            "reason_counts": dict(sorted(reasons.items())),
        })
    return rows


def mixture_fraction(weight: float, separation: float, *, size: int, repeats: int, rng: np.random.Generator) -> dict[str, Any]:
    """Return the kernel's mean between-class variance fraction for a two-population window.

    The window holds ``weight`` of its cells in a second normal population whose mean lies ``separation``
    standard deviations above the first; both have the same standard deviation.

    Raises:
        DiagnosisError: when the weight is not inside (0, 1) or the separation is negative.
    """

    if not 0.0 < weight < 1.0 or separation < 0.0:
        raise DiagnosisError("the second population needs a weight inside (0, 1) and a separation of zero or more")
    config = AdaptiveOtsuConfig()
    fractions: list[float] = []
    accepted = 0
    for _ in range(repeats):
        second = rng.random(size) < weight
        values = rng.normal(0.0, 2.0, size) + np.where(second, separation * 2.0, 0.0)
        decision = kernel_decision(values, config)
        fractions.append(float(decision.get("between_variance_fraction", 0.0)))
        accepted += decision["threshold_db"] is not None
    return {
        "second_population_share": weight,
        "separation_in_standard_deviations": round(float(separation), 3),
        "between_variance_fraction_mean": round(float(np.mean(fractions)), 6),
        "windows": int(repeats),
        "windows_the_kernel_accepts": int(accepted),
    }


def separation_needed(weights: Sequence[float], separations: Sequence[float], *, size: int, repeats: int, seed: int) -> list[dict[str, Any]]:
    """For each share of a second population, find the smallest separation at which the kernel accepts a window.

    The separations are tried in ascending order. ``first_separation_passing_the_gate`` is the first one whose
    mean between-class variance fraction reaches the gate; ``first_separation_every_window_accepted`` is the
    first one at which the kernel accepted every simulated window (its other two tests included). Either is
    None when no separation tried reaches it.
    """

    gate = m2_gate()
    ordered = sorted(float(value) for value in separations)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for weight in weights:
        tried = [mixture_fraction(float(weight), separation, size=size, repeats=repeats, rng=rng) for separation in ordered]
        passing = next((row for row in tried if row["between_variance_fraction_mean"] >= gate), None)
        accepted = next((row for row in tried if row["windows_the_kernel_accepts"] == row["windows"]), None)
        rows.append({
            "second_population_share": float(weight),
            "first_separation_passing_the_gate": None if passing is None else passing["separation_in_standard_deviations"],
            "first_separation_every_window_accepted": None if accepted is None else accepted["separation_in_standard_deviations"],
            "fraction_with_no_separation": tried[0]["between_variance_fraction_mean"] if ordered and ordered[0] == 0.0 else None,
            "fraction_at_the_largest_separation_tried": tried[-1]["between_variance_fraction_mean"],
            "largest_separation_tried": ordered[-1],
        })
    return rows


def summarise_fractions(fractions: Iterable[float], *, gate: float, marks: Sequence[float] = ()) -> dict[str, Any]:
    """Summarise the between-class variance fractions of a set of windows against the gate.

    Raises:
        DiagnosisError: when no window is given.
    """

    values = np.asarray(list(fractions), dtype="float64")
    if values.size == 0:
        raise DiagnosisError("no window to summarise")
    summary: dict[str, Any] = {
        "windows": int(values.size),
        "windows_at_or_above_the_gate": int((values >= gate).sum()),
        "gate": float(gate),
        "between_variance_fraction_min": round(float(values.min()), 6),
        "between_variance_fraction_median": round(float(np.median(values)), 6),
        "between_variance_fraction_max": round(float(values.max()), 6),
    }
    for mark in marks:
        summary[f"windows_at_or_above_{mark:.2f}"] = int((values >= mark).sum())
    return summary


# ---------------------------------------------------------------------------
# Separation of a feature against a mapped layer
# ---------------------------------------------------------------------------


def rank_auc(score: Any, inside: Any) -> dict[str, Any]:
    """Return the area under the ROC curve of ``score`` for the cells ``inside`` a layer against those outside.

    The value is the probability that a cell inside the layer has a larger score than a cell outside it,
    counting a tie as one half (the Mann-Whitney statistic divided by the number of pairs). Cells whose score
    is not finite are left out and counted.

    Raises:
        DiagnosisError: when the two arrays differ in shape, or every finite cell is on one side.
    """

    values = np.asarray(score, dtype="float64").ravel()
    member = np.asarray(inside, dtype=bool).ravel()
    if values.shape != member.shape:
        raise DiagnosisError("the score and the layer membership must have one shape")
    finite = np.isfinite(values)
    values, member = values[finite], member[finite]
    positives = int(member.sum())
    negatives = int(member.size - positives)
    if positives == 0 or negatives == 0:
        raise DiagnosisError("the rank statistic needs cells inside the layer and cells outside it")
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    starts = np.concatenate(([0], np.flatnonzero(ordered[1:] != ordered[:-1]) + 1))
    ends = np.concatenate((starts[1:], [ordered.size]))
    # Tied cells share the mean of the ranks they span (ranks start at 1).
    ranks = np.repeat((starts + ends + 1) / 2.0, ends - starts)
    rank_sum = float(ranks[member[order]].sum())
    auc = (rank_sum - positives * (positives + 1) / 2.0) / (float(positives) * float(negatives))
    return {
        "auc": round(auc, 6),
        "cells_inside_the_layer": positives,
        "cells_outside_the_layer": negatives,
        "cells_left_out_for_no_value": int((~finite).sum()),
    }


def boxcar_mean(values: Any, size: int) -> np.ndarray:
    """Return the mean of each cell's ``size`` by ``size`` neighbourhood, ignoring cells with no value.

    The window is cut at the edge of the array. A cell whose window holds a value in half its cells or
    fewer gets no value (NaN).

    Raises:
        DiagnosisError: when ``size`` is not an odd whole number of at least 1, or the array is not 2-D.
    """

    array = np.asarray(values, dtype="float64")
    if array.ndim != 2 or size < 1 or size % 2 != 1:
        raise DiagnosisError("the boxcar needs a 2-D array and an odd window")
    finite = np.isfinite(array)
    half = size // 2

    def window_sum(layer: np.ndarray) -> np.ndarray:
        padded = np.pad(layer, ((half + 1, half), (half + 1, half)))
        table = padded.cumsum(axis=0).cumsum(axis=1)
        return table[size:, size:] - table[:-size, size:] - table[size:, :-size] + table[:-size, :-size]

    total = window_sum(np.where(finite, array, 0.0))
    count = window_sum(finite.astype("float64"))
    return np.where(count > 0.5 * size * size, total / np.maximum(count, 1.0), np.nan)


def block_mean(values: Any, factor: int) -> np.ndarray:
    """Average a 2-D array over blocks of ``factor`` by ``factor`` cells, ignoring cells with no value.

    Raises:
        DiagnosisError: when the array is not 2-D or its shape is not a multiple of ``factor``.
    """

    array = np.asarray(values, dtype="float64")
    if array.ndim != 2 or factor < 1 or array.shape[0] % factor or array.shape[1] % factor:
        raise DiagnosisError("the array must be 2-D with both sides a multiple of the block size")
    blocks = array.reshape(array.shape[0] // factor, factor, array.shape[1] // factor, factor)
    finite = np.isfinite(blocks)
    count = finite.sum(axis=(1, 3))
    total = np.where(finite, blocks, 0.0).sum(axis=(1, 3))
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def darkening_db(before_linear: Any, after_linear: Any) -> np.ndarray:
    """Return how much the backscatter fell between two dates, in dB: positive where the later image is darker.

    Both arrays are linear backscatter. A cell with no value, or a value of zero or less, on either date has
    no result (NaN).
    """

    before = np.asarray(before_linear, dtype="float64")
    after = np.asarray(after_linear, dtype="float64")
    if before.shape != after.shape:
        raise DiagnosisError("the two dates must have one shape")
    valid = np.isfinite(before) & np.isfinite(after) & (before > 0) & (after > 0)
    result = np.full(before.shape, np.nan, dtype="float64")
    result[valid] = 10.0 * np.log10(before[valid]) - 10.0 * np.log10(after[valid])
    return result


def slope_degrees(elevation_m: Any, cell_m: float) -> np.ndarray:
    """Return the slope of an elevation grid in degrees, from central differences over cells of ``cell_m``."""

    elevation = np.asarray(elevation_m, dtype="float64")
    if elevation.ndim != 2 or min(elevation.shape) < 2 or not cell_m > 0:
        raise DiagnosisError("the slope needs a 2-D elevation grid of at least two cells each way and a positive cell size")
    north, east = np.gradient(elevation, cell_m)
    return np.degrees(np.arctan(np.hypot(east, north)))


def separation_against_layer(features: Mapping[str, Any], inside: Any, domain: Any) -> dict[str, Any]:
    """Return, for each feature, its rank statistic against a layer over the cells of ``domain``.

    Beside each statistic stand the medians of the feature inside and outside the layer, so that a value
    below 0.5 can be read: the cells inside the layer then tend to have the smaller feature value.

    Raises:
        DiagnosisError: when a feature, the layer and the domain do not share one shape.
    """

    member = np.asarray(inside, dtype=bool)
    cells = np.asarray(domain, dtype=bool)
    if member.shape != cells.shape:
        raise DiagnosisError("the layer and the domain must have one shape")
    result: dict[str, Any] = {}
    for name, feature in features.items():
        values = np.asarray(feature, dtype="float64")
        if values.shape != cells.shape:
            raise DiagnosisError(f"feature {name} does not have the shape of the domain")
        used = cells & np.isfinite(values)
        statistic = rank_auc(values[used], member[used])
        statistic["cells_left_out_for_no_value"] = int((cells & ~np.isfinite(values)).sum())
        statistic["median_inside_the_layer"] = round(float(np.median(values[used & member])), 4)
        statistic["median_outside_the_layer"] = round(float(np.median(values[used & ~member])), 4)
        result[str(name)] = statistic
    return result


# ---------------------------------------------------------------------------
# Passes of a satellite over a point
# ---------------------------------------------------------------------------


def parse_utc(text: str) -> datetime:
    """Parse a UTC time such as ``2024-09-15T23:16:01.675690Z``.

    Raises:
        DiagnosisError: when the text is not a UTC time.
    """

    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise DiagnosisError(f"not a UTC time: {text!r}") from error
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise DiagnosisError(f"not a UTC time: {text!r}")
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _thailand(moment: datetime) -> str:
    return (moment.astimezone(timezone.utc) + THAILAND_UTC_OFFSET).strftime("%Y-%m-%d %H:%M ICT")


def pass_gap(acquisition_times: Iterable[str], *, after: str, before: str) -> dict[str, Any]:
    """List the distinct passes in a set of catalogue rows and the passes that fall between two instants.

    A catalogue lists one acquisition several times (one row for each product made from it), so rows with
    the same start time are one pass. The interval is open: a pass at ``after`` or at ``before`` is one of
    its two ends, not a pass between them.

    Returns:
        The distinct passes in UTC and in Thailand time, the gaps between neighbouring passes, the longest
        gap, and the passes strictly between ``after`` and ``before`` with whether both ends are passes.

    Raises:
        DiagnosisError: for no row, or an interval that is empty or reversed.
    """

    passes = sorted({parse_utc(text) for text in acquisition_times})
    start, end = parse_utc(after), parse_utc(before)
    if not passes or not start < end:
        raise DiagnosisError("the pass list is empty, or the interval is not in order")
    truncated = [moment.replace(microsecond=0) for moment in passes]
    gaps = [{
        "from_utc": _stamp(earlier), "to_utc": _stamp(later),
        "hours": round((later - earlier).total_seconds() / 3600.0, 3),
        "days": round((later - earlier).total_seconds() / 86400.0, 3),
    } for earlier, later in zip(passes[:-1], passes[1:])]
    between = [moment for moment in passes if start < moment.replace(microsecond=0) < end]
    return {
        "passes": [{"start_utc": _stamp(moment), "start_in_thailand": _thailand(moment)} for moment in passes],
        "pass_count": len(passes),
        "gaps_between_neighbouring_passes": gaps,
        "longest_gap": max(gaps, key=lambda gap: gap["hours"]) if gaps else None,
        "interval": {"after_utc": _stamp(start), "before_utc": _stamp(end),
                     "hours": round((end - start).total_seconds() / 3600.0, 3),
                     "days": round((end - start).total_seconds() / 86400.0, 3)},
        "passes_strictly_inside_the_interval": [_stamp(moment) for moment in between],
        "interval_starts_at_a_pass": start in truncated,
        "interval_ends_at_a_pass": end in truncated,
    }


_MONTHS = {name: number for number, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}
_KEYFRAME_TIME = re.compile(r"(?<![0-9])(\d{1,2}) (" + "|".join(_MONTHS) + r") (\d{2}):(\d{2}) ICT")
_KEYFRAME_T = re.compile(r"`t = ([0-9]+(?:\.[0-9]+)?) d,")
_SOURCE_YEARS = re.compile(r"^\| Source timestamp \| `(\d{4})-\d{2}-\d{2}T[0-9:]+Z/(\d{4})-\d{2}-\d{2}T[0-9:]+Z` \|\s*$", re.MULTILINE)


def replay_keyframe(replay_numbers: str, key: str) -> dict[str, Any]:
    """Read one keyframe of the Mae Sai replay from the text of ``docs/demo/replay_numbers.md``.

    The row of ``key`` states the keyframe in Thailand time (for example ``10 Sep 18:15 ICT``) and its
    position on the replay's own clock (``t = 1.760417 d``). The year is the one of the file's source
    timestamp. The keyframe is an illustrative scenario value of the replay, not an observation.

    Returns:
        ``key``, ``in_thailand`` (as the file states it), ``utc`` and ``replay_days``.

    Raises:
        DiagnosisError: when the file has no single row for the key, the row states no time or no replay
            day, or the source timestamp does not give one year.
    """

    rows = [line for line in replay_numbers.splitlines() if line.startswith(f"| `{key}` |")]
    if len(rows) != 1:
        raise DiagnosisError(f"the replay figures hold {len(rows)} rows for the key {key}; one is needed")
    years = _SOURCE_YEARS.search(replay_numbers)
    if years is None or years.group(1) != years.group(2):
        raise DiagnosisError("the replay figures do not state a source timestamp inside one year")
    stated, position = _KEYFRAME_TIME.search(rows[0]), _KEYFRAME_T.search(rows[0])
    if stated is None or position is None:
        raise DiagnosisError(f"the row of {key} states no time in Thailand or no replay day")
    day, month, hour, minute = int(stated.group(1)), _MONTHS[stated.group(2)], int(stated.group(3)), int(stated.group(4))
    try:
        local = datetime(int(years.group(1)), month, day, hour, minute, tzinfo=timezone(THAILAND_UTC_OFFSET))
    except ValueError as error:
        raise DiagnosisError(f"the row of {key} states no valid time") from error
    return {"key": key, "in_thailand": stated.group(0), "utc": _stamp(local), "replay_days": float(position.group(1))}


def keyframes_agree(first: Mapping[str, Any], second: Mapping[str, Any], *, tolerance_seconds: float = 60.0) -> bool:
    """Say whether two keyframes lie as far apart in stated time as on the replay's own clock."""

    stated = (parse_utc(second["utc"]) - parse_utc(first["utc"])).total_seconds()
    clock = (float(second["replay_days"]) - float(first["replay_days"])) * 86400.0
    return abs(stated - clock) <= tolerance_seconds


# ---------------------------------------------------------------------------
# Share of a layer that a grid leaves out
# ---------------------------------------------------------------------------


def share_outside(total_area: float, area_inside: float) -> dict[str, float]:
    """Return the shares of an area that lie inside and outside a grid.

    Raises:
        DiagnosisError: when the total is not positive or the part is negative or larger than the total.
    """

    if not total_area > 0 or area_inside < 0 or area_inside > total_area * (1 + 1e-9):
        raise DiagnosisError("the part must lie between zero and the total, and the total must be positive")
    inside = min(1.0, area_inside / total_area)
    return {"share_inside": round(inside, 6), "share_outside": round(1.0 - inside, 6)}
