"""Evacuation Equity Gap of the Mae Sai replay, with its denominator and its null rule.

The replay page compares how often two groups of modelled residents lose walking access to a dry shelter:
the proxy-vulnerable group and everyone else. Each group's loss rate answers one question (owner decision
R8, option B, 2 Oct 2026):

    Of the residents in the group who had a shelter within reach before the flood, the share who lost it.

So a rate is ``lost / within reach before the flood``. Residents who had no shelter of the set within reach
before the flood are not in the rate: they could not lose what they did not have, and the page counts them
separately as "already out of reach". This is how the signed scoring frame counts access loss (D4: counted
only for people with access before the flood).

``floodguard.equity_v1`` divides by whatever group totals its caller passes, returns a ratio of 1.0 when
nobody loses access and has no minimum group size. It is metric version 1, the code plan section 5.6 left
unchanged; ``floodguard.equity`` itself is metric version 2.0 since the scoring line was merged, and is not
this module's reference. For the replay a ratio of 1.0 reads as a finding where there is none, so this
module is the replay's own rule set:

* no ratio, reason ``insufficient_group_denominator``, when either group has fewer than
  :data:`MINIMUM_GROUP_SIZE` residents within reach before the flood (plan section 2.3-1: a ratio needs at
  least 50 people in each denominator);
* no ratio, reason ``no_loss``, when nobody in either group has lost access;
* no ratio, reason ``undefined_ratio``, when only the proxy-vulnerable group loses access;
* otherwise the same rates, ratio, band limits and rounding as ``floodguard.equity_v1`` gives for the same
  numerators and denominators.

"Nobody" and "only" are decided on the residents who lost access, not on the rounded rates: three residents
lost in a group of 74,647 is a rate that rounds to 0.0000, and it is still a loss. Where a rounded rate hides
such a loss the ratio is taken from the unrounded rates, because the rounded ones cannot be divided
(``floodguard.equity_v1`` reports "zero loss" or "undefined" there).

It mirrors ``evacuationEquityGap`` in ``apps/web/src/lib/flood-timeline-evacuation.ts``; the parity fixture
written by ``apps/web/scripts/equity-access-parity-fixture.py`` holds the two together.

Everything here is a T1 scenario on a modelled flood, not an observed evacuation outcome. "Vulnerable" is
the terrain and remoteness proxy (homes on slopes or far from a drivable road), not age, disability or
income. No priority score and no action class is computed from the result.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

MINIMUM_GROUP_SIZE = 50
"""Fewest residents within reach before the flood a group needs before a ratio of loss rates is stated."""

DENOMINATOR = "within_reach_before_flood"
"""What each loss rate divides by: the group's residents with a shelter within reach before the flood (R8, option B)."""

HIGHER_ABOVE = 1.2
"""A ratio above this reads "more likely to lose access"."""

LOWER_BELOW = 0.8
"""A ratio below this reads "less likely to lose access"."""

REASON_INSUFFICIENT_GROUP = "insufficient_group_denominator"
REASON_NO_LOSS = "no_loss"
REASON_UNDEFINED_RATIO = "undefined_ratio"
STATUS_RATIO = "ratio"

NULL_REASONS: tuple[str, ...] = (REASON_INSUFFICIENT_GROUP, REASON_NO_LOSS, REASON_UNDEFINED_RATIO)
"""Every reason a ratio is withheld, in the order the rules are applied."""

_SUBSET_SLACK = 1e-6
"""Relative slack when checking that the lost residents are among those within reach (the inputs are float sums)."""


class ReplayEquityError(ValueError):
    """Raised when an input is negative or not finite, or more residents are lost than were within reach."""


@dataclass(frozen=True)
class ReplayEquityGap:
    """Result of :func:`replay_equity_gap`.

    ``reason`` is ``None`` exactly when ``ratio`` is a number. A rate is ``lost / within reach`` and is
    ``None`` only for a group with nobody within reach before the flood; for a group that is too small it is
    still given, so the page can show the counts. The lost counts are kept beside the rounded rates, because
    a small loss in a large group rounds to a rate of zero.
    """

    status: str
    reason: str | None
    vulnerable_lost: float
    non_vulnerable_lost: float
    vulnerable_rate: float | None
    non_vulnerable_rate: float | None
    ratio: float | None
    band: str | None
    interpretation: str
    vulnerable_within_reach: float
    non_vulnerable_within_reach: float
    minimum_group_size: int
    denominator: str = DENOMINATOR

    def as_dict(self) -> dict[str, object]:
        """The result as a plain dictionary (for JSON fixtures and tables)."""
        return asdict(self)


def _rate(lost: float, within_reach: float) -> float | None:
    return None if within_reach == 0 else round(lost / within_reach, 4)


def _checked(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ReplayEquityError(f"{name} must be a non-negative finite number, got {value!r}")
    return number


def replay_equity_gap(
    vulnerable_lost: float,
    vulnerable_within_reach: float,
    non_vulnerable_lost: float,
    non_vulnerable_within_reach: float,
    *,
    minimum_group_size: int = MINIMUM_GROUP_SIZE,
) -> ReplayEquityGap:
    """Compare the access-loss rates of proxy-vulnerable residents and everyone else.

    Each rate is the share of a group's residents with a shelter within reach before the flood who have
    lost it: ``lost / within reach``, rounded to four decimals. The ratio is ``vulnerable rate / other rate``
    rounded to three, as in ``floodguard.equity_v1``. The ratio is withheld (``None``) with a reason when a
    group has fewer than ``minimum_group_size`` residents within reach before the flood (or none at all),
    when neither group has lost access, or when only the proxy-vulnerable group has. The group-size rule is
    applied first because it does not depend on the hour. Loss is judged on the lost counts; when a rounded
    rate is zero although residents were lost, the ratio uses the unrounded rates.

    Args:
        vulnerable_lost: Proxy-vulnerable residents who have lost access.
        vulnerable_within_reach: Proxy-vulnerable residents with a shelter of the set within reach before
            the flood. This is the denominator, not every proxy-vulnerable resident counted.
        non_vulnerable_lost: Other residents who have lost access.
        non_vulnerable_within_reach: Other residents with a shelter of the set within reach before the flood.
        minimum_group_size: Fewest residents within reach per group for a ratio (default 50; at least 1).

    Returns:
        The rates, the ratio or the reason it is withheld, the band and an English sentence.

    Raises:
        ReplayEquityError: If an input is negative, infinite or not a number, if more residents are lost
            than were within reach before the flood, or if ``minimum_group_size`` is below 1.
    """
    if not isinstance(minimum_group_size, (int, float)) or isinstance(minimum_group_size, bool) \
            or not math.isfinite(minimum_group_size) or minimum_group_size < 1:
        raise ReplayEquityError(f"minimum_group_size must be at least 1, got {minimum_group_size!r}")
    v_lost = _checked(vulnerable_lost, "vulnerable_lost")
    v_reach = _checked(vulnerable_within_reach, "vulnerable_within_reach")
    o_lost = _checked(non_vulnerable_lost, "non_vulnerable_lost")
    o_reach = _checked(non_vulnerable_within_reach, "non_vulnerable_within_reach")
    for name, lost, reach in (("vulnerable", v_lost, v_reach), ("non_vulnerable", o_lost, o_reach)):
        # Only a resident who had a shelter within reach can lose it; a larger count means the wrong denominator.
        if lost > reach + _SUBSET_SLACK * max(1.0, reach):
            raise ReplayEquityError(
                f"{name}_lost ({lost!r}) exceeds {name}_within_reach ({reach!r}): each rate divides by the "
                "residents with a shelter within reach before the flood, and only they can lose it"
            )
    v_rate = _rate(v_lost, v_reach)
    o_rate = _rate(o_lost, o_reach)

    def result(status: str, ratio: float | None, band: str | None, interpretation: str) -> ReplayEquityGap:
        return ReplayEquityGap(
            status=status,
            reason=None if status == STATUS_RATIO else status,
            vulnerable_lost=v_lost,
            non_vulnerable_lost=o_lost,
            vulnerable_rate=v_rate,
            non_vulnerable_rate=o_rate,
            ratio=ratio,
            band=band,
            interpretation=interpretation,
            vulnerable_within_reach=v_reach,
            non_vulnerable_within_reach=o_reach,
            minimum_group_size=minimum_group_size,
        )

    if v_reach < minimum_group_size or o_reach < minimum_group_size or v_rate is None or o_rate is None:
        return result(
            REASON_INSUFFICIENT_GROUP, None, None,
            f"Equity gap not computed: a group has fewer than {minimum_group_size} residents "
            "with a shelter within reach before the flood.",
        )
    if v_lost == 0 and o_lost == 0:
        return result(REASON_NO_LOSS, None, None, "Equity gap not computed: neither group has lost access.")
    if o_lost == 0:
        return result(
            REASON_UNDEFINED_RATIO, None, None,
            "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.",
        )
    # A loss too small to survive four-decimal rounding is still a loss: divide the unrounded rates there.
    hidden_by_rounding = o_rate == 0 or (v_rate == 0 and v_lost > 0)
    ratio = round((v_lost / v_reach) / (o_lost / o_reach), 3) if hidden_by_rounding else round(v_rate / o_rate, 3)
    if ratio > HIGHER_ABOVE:
        return result(STATUS_RATIO, ratio, "higher", f"Vulnerable residents are {ratio:.3g} times more likely to lose access.")
    if ratio < LOWER_BELOW:
        return result(STATUS_RATIO, ratio, "lower", f"Vulnerable residents are {ratio:.3g} times as likely to lose access.")
    return result(STATUS_RATIO, ratio, "similar", "Access-loss rates are broadly similar between groups.")
