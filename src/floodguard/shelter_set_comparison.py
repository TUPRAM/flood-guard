"""Side-by-side access figures for the shelter sets of a flood replay.

A shelter set (the sites reported in use, or the first ``k`` sites of a ranked plan) is described by four
figures, each counted for a chosen group of residents:

1. residents with a shelter of the set within reach before the flood (the set's own baseline);
2. residents of that baseline who still have one at a stage;
3. residents of that baseline who have lost it, with the share of the baseline;
4. the modelled access cut-off hour: the first replay hour at which fewer than half of the baseline
   residents still have access.

The module does not rank the sets and returns no single headline: a set that reaches more residents overall
can reach fewer of the residents whose homes flood, so both ways of counting are reported by the caller.

Inputs are the per-node cut codes written by ``floodguard.evacuation_access.cutoff_levels_for_sets`` (the
index of the first evaluated level at which the node loses access; 254 never; 255 no baseline access).
Everything here is a T1 scenario on a modelled flood. The hours come from illustrative stage keyframes and
are not observed; nothing here is a forecast, an official warning or an observed evacuation outcome, and no
priority score or action class is computed from it. It mirrors ``shelterSetComparison`` in
``apps/web/src/lib/flood-timeline-evacuation.ts``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np

from floodguard.evacuation_access import NEVER_LOST, NO_BASELINE_ACCESS

LEVEL_STEP_M = 0.05
"""Spacing of the evaluated stage levels in the Mae Sai replay."""

CUTOFF_COVERAGE_SHARE = 0.5
"""The cut-off hour is the first hour when coverage falls below this share of the baseline."""

CUTOFF_REACHED = "reached"
CUTOFF_NOT_REACHED = "not_reached"
CUTOFF_NO_BASELINE = "no_baseline"


class ShelterSetComparisonError(ValueError):
    """Raised when the node arrays do not describe the same nodes or hold invalid values."""


@dataclass(frozen=True)
class ShelterSetSummary:
    """Access figures of one shelter set for one group of residents at one stage.

    ``cutoff_hour`` is the index into the hourly stages (0 = the first replay hour) and is ``None`` unless
    ``cutoff_status`` is ``"reached"``. ``lost_share`` is ``lost / baseline`` rounded to four decimals, or
    ``None`` when nobody in the group has a shelter of the set within reach before the flood.
    """

    residents: float
    baseline: float
    keeping: float
    lost: float
    lost_share: float | None
    vulnerable_baseline: float
    vulnerable_lost: float
    cutoff_status: str
    cutoff_hour: int | None

    def as_dict(self) -> dict[str, object]:
        """The summary as a plain dictionary (for JSON fixtures and tables)."""
        return asdict(self)


def level_index(stage_m: float, level_step_m: float = LEVEL_STEP_M) -> int:
    """Index of the evaluated level in force at ``stage_m``: ``floor(stage / step + 1e-6)``."""
    return int(math.floor(stage_m / level_step_m + 1e-6))


def lost_access(cut_codes: np.ndarray, stage_m: float, level_step_m: float = LEVEL_STEP_M) -> np.ndarray:
    """Boolean mask of nodes that had baseline access and have lost it at ``stage_m``."""
    codes = np.asarray(cut_codes).astype(int)
    return (codes != NEVER_LOST) & (codes != NO_BASELINE_ACCESS) & (codes <= level_index(stage_m, level_step_m))


def access_cutoff_hour(
    baseline: float,
    keeping_by_hour: Sequence[float],
    coverage_share: float = CUTOFF_COVERAGE_SHARE,
) -> tuple[str, int | None]:
    """Find the modelled access cut-off hour.

    Args:
        baseline: Residents with a shelter of the set within reach before the flood.
        keeping_by_hour: Residents of that baseline who still have access, one value per replay hour.
        coverage_share: Share of the baseline below which access counts as cut off (default one half).

    Returns:
        ``("reached", hour)`` for the first hour whose coverage is below ``coverage_share * baseline``,
        ``("not_reached", None)`` when no hour is, or ``("no_baseline", None)`` when ``baseline`` is zero.
    """
    if not baseline > 0:
        return CUTOFF_NO_BASELINE, None
    limit = coverage_share * baseline
    for hour, keeping in enumerate(keeping_by_hour):
        if keeping < limit:
            return CUTOFF_REACHED, hour
    return CUTOFF_NOT_REACHED, None


def shelter_set_summary(
    population: np.ndarray,
    cut_codes: np.ndarray,
    stage_m: float,
    hourly_stages_m: Sequence[float],
    *,
    vulnerable_population: np.ndarray | None = None,
    mask: np.ndarray | None = None,
    level_step_m: float = LEVEL_STEP_M,
    coverage_share: float = CUTOFF_COVERAGE_SHARE,
) -> ShelterSetSummary:
    """Summarise one shelter set for one group of residents.

    Args:
        population: Residents per node.
        cut_codes: The set's cut code per node (see the module docstring).
        stage_m: Stage at which ``keeping`` and ``lost`` are counted.
        hourly_stages_m: The replay's stage at every hour, used for the cut-off hour.
        vulnerable_population: Proxy-vulnerable residents per node (terrain and remoteness proxy); zero when omitted.
        mask: Nodes to count (for example homes that flood at the modelled peak); every node when omitted.
        level_step_m: Spacing of the evaluated levels.
        coverage_share: Share of the baseline below which access counts as cut off.

    Returns:
        The set's baseline, the residents keeping and losing access at ``stage_m`` and the cut-off hour.

    Raises:
        ShelterSetComparisonError: If the arrays differ in length or hold negative or non-finite residents.
    """
    people = np.asarray(population, dtype=float)
    codes = np.asarray(cut_codes).astype(int)
    vulnerable = np.zeros(people.shape) if vulnerable_population is None else np.asarray(vulnerable_population, dtype=float)
    selected = np.ones(people.shape, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if not (people.shape == codes.shape == vulnerable.shape == selected.shape) or people.ndim != 1:
        raise ShelterSetComparisonError("population, cut codes, vulnerable population and mask must be one value per node")
    if not (np.isfinite(people).all() and (people >= 0).all() and np.isfinite(vulnerable).all() and (vulnerable >= 0).all()):
        raise ShelterSetComparisonError("residents must be non-negative finite numbers")

    # math.fsum is exactly rounded, so the figures do not depend on how a NumPy build orders additions.
    total = lambda values: math.fsum(values.tolist())  # noqa: E731
    with_baseline = selected & (codes != NO_BASELINE_ACCESS)
    baseline = total(people[with_baseline])
    can_lose = with_baseline & (codes != NEVER_LOST)
    lost_by_code = {int(code): total(people[can_lose & (codes == code)]) for code in np.unique(codes[can_lose])}

    def lost_at(index: int) -> float:
        return math.fsum(value for code, value in lost_by_code.items() if code <= index)

    by_index: dict[int, float] = {}

    def keeping_at(stage: float) -> float:
        index = level_index(stage, level_step_m)
        if index not in by_index:
            by_index[index] = baseline - lost_at(index)
        return by_index[index]

    lost_now = can_lose & (codes <= level_index(stage_m, level_step_m))
    lost = lost_at(level_index(stage_m, level_step_m))
    status, hour = access_cutoff_hour(baseline, [keeping_at(float(stage)) for stage in hourly_stages_m], coverage_share)
    return ShelterSetSummary(
        residents=total(people[selected]),
        baseline=baseline,
        keeping=baseline - lost,
        lost=lost,
        lost_share=round(lost / baseline, 4) if baseline > 0 else None,
        vulnerable_baseline=total(vulnerable[with_baseline]),
        vulnerable_lost=total(vulnerable[lost_now]),
        cutoff_status=status,
        cutoff_hour=hour,
    )
