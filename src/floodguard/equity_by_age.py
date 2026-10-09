"""Access loss by age group: the difference and the ratio of loss rates (protocol v1a, ``equity_statement_rule``).

Two comparisons are named by the protocol: residents of 60 and over against those under 60, and children of 0 to
14 against residents of 15 and over. For each, the loss rate of a group counts only its residents who had the
access before the flood (requirement EQ-04): of those, the share who lost it.

* the difference of the two rates (EED) is in share points;
* the ratio (EER) is not given when either group has fewer than 50 such residents, or when both rates are zero;
* a gap may be put into a sentence only when every run gives the same sign and the range excludes zero over at
  least 60 percent of the runs; otherwise the protocol's fixed sentence stands.

The age counts are modelled (WorldPop), not observed. The functions return counts and rates for a tambon or a
coarser frame; they say nothing of what the people of a place can or cannot do.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

GROUP_MIN_FOR_RATIO = 50.0
SIGN_RETENTION_MIN = 0.6
FIXED_SENTENCE = "no age-group gap distinguishable from zero under the tested assumptions"
RATIO_NULL_SMALL_GROUP = "fewer_than_50_residents_with_baseline_access_in_a_group"
RATIO_NULL_NO_LOSS = "both_rates_are_zero"
RATIO_NULL_ZERO_DENOMINATOR = "the_comparison_group_lost_nothing"

COMPARISONS: dict[str, tuple[str, str]] = {
    "60_plus_vs_under_60": ("older_60_plus", "under_60"),
    "0_14_vs_15_plus": ("children_0_14", "15_plus"),
}


class EquityByAgeError(ValueError):
    """The inputs of the age comparison do not fit together."""


def group_counts(residents: np.ndarray, child_share: np.ndarray, older_share: np.ndarray) -> dict[str, np.ndarray]:
    """Residents of every cell by age group, from the cell's residents and its modelled age shares."""

    total = np.asarray(residents, dtype="float64")
    children = np.asarray(child_share, dtype="float64")
    older = np.asarray(older_share, dtype="float64")
    if not (total.shape == children.shape == older.shape):
        raise EquityByAgeError("residents and the two shares must describe the same cells")
    if np.any(total < 0) or np.any((children < 0) | (older < 0) | (children + older > 1 + 1e-9)) or not np.isfinite(total).all():
        raise EquityByAgeError("residents must be 0 or more and the shares must lie inside 0 to 1 and sum to at most 1")
    return {"children_0_14": total * children, "15_plus": total * (1 - children),
            "older_60_plus": total * older, "under_60": total * (1 - older)}


def compare(base_a: float, lost_a: float, base_b: float, lost_b: float, *, group_min: float = GROUP_MIN_FOR_RATIO) -> dict[str, Any]:
    """Loss rates of two groups, their difference and their ratio, with the protocol's rules for an empty ratio."""

    if min(base_a, lost_a, base_b, lost_b) < 0 or lost_a > base_a + 1e-6 or lost_b > base_b + 1e-6:
        raise EquityByAgeError("lost residents must be among the residents with baseline access, and no count below 0")
    rate_a = lost_a / base_a if base_a > 0 else None
    rate_b = lost_b / base_b if base_b > 0 else None
    difference = None if rate_a is None or rate_b is None else rate_a - rate_b
    ratio, reason = None, None
    if base_a < group_min or base_b < group_min:
        reason = RATIO_NULL_SMALL_GROUP
    elif rate_a == 0 and rate_b == 0:
        reason = RATIO_NULL_NO_LOSS
    elif rate_b == 0:
        reason = RATIO_NULL_ZERO_DENOMINATOR
    else:
        ratio = rate_a / rate_b
    return {
        "group_residents_with_baseline_access": round(base_a, 1), "group_residents_who_lose_it": round(lost_a, 1),
        "others_with_baseline_access": round(base_b, 1), "others_who_lose_it": round(lost_b, 1),
        "group_loss_rate": None if rate_a is None else round(rate_a, 6),
        "others_loss_rate": None if rate_b is None else round(rate_b, 6),
        "difference_of_rates": None if difference is None else round(difference, 6),
        "ratio_of_rates": None if ratio is None else round(ratio, 4),
        "ratio_not_given_because": reason,
    }


def outcome_by_age(groups: Mapping[str, np.ndarray], had: np.ndarray, lost: np.ndarray, where: np.ndarray | None = None) -> dict[str, Any]:
    """Both comparisons of the protocol for one outcome, over the cells of ``where`` (all cells when omitted)."""

    before = np.asarray(had, dtype=bool)
    gone = np.asarray(lost, dtype=bool)
    if before.shape != gone.shape or np.any(gone & ~before):
        raise EquityByAgeError("a cell can lose only an access it had")
    inside = np.ones(before.shape, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    result = {}
    for name, (group, others) in COMPARISONS.items():
        result[name] = compare(
            float(groups[group][before & inside].sum()), float(groups[group][gone & inside].sum()),
            float(groups[others][before & inside].sum()), float(groups[others][gone & inside].sum()))
    return result


def gap_statement(differences: Sequence[float | None], *, sign_retention_min: float = SIGN_RETENTION_MIN) -> dict[str, Any]:
    """Apply the protocol's rule for a gap sentence to the differences of a set of runs.

    A gap may be stated when the smallest and the largest difference lie on one side of zero and at least
    ``sign_retention_min`` of the runs carry the sign of the median. A run without a difference counts against it.
    """

    runs = len(differences)
    if runs == 0:
        raise EquityByAgeError("a statement needs at least one run")
    known = [float(value) for value in differences if value is not None]
    if not known:
        return {"runs": runs, "runs_with_a_difference": 0, "may_state_a_gap": False, "sentence": FIXED_SENTENCE}
    low, high, middle = min(known), max(known), float(np.median(known))
    sign = 1 if middle > 0 else -1 if middle < 0 else 0
    kept = sum(1 for value in known if sign != 0 and (value > 0) == (sign > 0) and value != 0) / runs
    excludes_zero = (low > 0 and high > 0) or (low < 0 and high < 0)
    may = bool(excludes_zero and kept >= sign_retention_min and len(known) == runs)
    return {"runs": runs, "runs_with_a_difference": len(known), "lowest": round(low, 6), "highest": round(high, 6),
            "median": round(middle, 6), "range_excludes_zero": bool(excludes_zero), "sign_retention": round(kept, 4),
            "may_state_a_gap": may, "sentence": None if may else FIXED_SENTENCE}
