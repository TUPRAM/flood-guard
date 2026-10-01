"""Evacuation Equity Gap of the Mae Sai replay, with its null rule.

The replay page compares how often two groups of modelled residents lose walking access to a dry shelter:
the proxy-vulnerable group and everyone else. ``floodguard.equity`` (unchanged, plan section 5.6) returns a
ratio of 1.0 when nobody loses access and has no minimum group size. For the replay that reads as a finding
where there is none, so this module is the replay's own rule set:

* no ratio, reason ``insufficient_group_denominator``, when either group has fewer than
  :data:`MINIMUM_GROUP_SIZE` residents (plan section 2.3-1: a ratio needs at least 50 people per group);
* no ratio, reason ``no_loss``, when both loss rates are zero;
* no ratio, reason ``undefined_ratio``, when only the proxy-vulnerable group loses access;
* otherwise the same rates, ratio, band limits and rounding as ``floodguard.equity``.

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
"""Fewest residents a group needs before a ratio of loss rates is stated."""

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


class ReplayEquityError(ValueError):
    """Raised when an input is negative or not a finite number."""


@dataclass(frozen=True)
class ReplayEquityGap:
    """Result of :func:`replay_equity_gap`.

    ``reason`` is ``None`` exactly when ``ratio`` is a number. A rate is ``None`` only for a group with no
    residents; for a group that is too small it is still given, so the page can show the counts.
    """

    status: str
    reason: str | None
    vulnerable_rate: float | None
    non_vulnerable_rate: float | None
    ratio: float | None
    band: str | None
    interpretation: str
    vulnerable_total: float
    non_vulnerable_total: float
    minimum_group_size: int

    def as_dict(self) -> dict[str, object]:
        """The result as a plain dictionary (for JSON fixtures and tables)."""
        return asdict(self)


def _rate(lost: float, total: float) -> float | None:
    return None if total == 0 else round(lost / total, 4)


def _checked(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ReplayEquityError(f"{name} must be a non-negative finite number, got {value!r}")
    return number


def replay_equity_gap(
    vulnerable_lost: float,
    vulnerable_total: float,
    non_vulnerable_lost: float,
    non_vulnerable_total: float,
    *,
    minimum_group_size: int = MINIMUM_GROUP_SIZE,
) -> ReplayEquityGap:
    """Compare the access-loss rates of proxy-vulnerable residents and everyone else.

    Rates are ``lost / total`` rounded to four decimals and the ratio is ``vulnerable rate / other rate``
    rounded to three, as in ``floodguard.equity``. The ratio is withheld (``None``) with a reason when a group
    has fewer than ``minimum_group_size`` residents, when neither group has lost access, or when only the
    proxy-vulnerable group has. The group-size rule is applied first because it does not depend on the hour.

    Args:
        vulnerable_lost: Proxy-vulnerable residents who have lost access.
        vulnerable_total: All proxy-vulnerable residents counted.
        non_vulnerable_lost: Other residents who have lost access.
        non_vulnerable_total: All other residents counted.
        minimum_group_size: Fewest residents per group for a ratio (default 50).

    Returns:
        The rates, the ratio or the reason it is withheld, the band and an English sentence.

    Raises:
        ReplayEquityError: If an input is negative, infinite or not a number.
    """
    v_lost = _checked(vulnerable_lost, "vulnerable_lost")
    v_total = _checked(vulnerable_total, "vulnerable_total")
    o_lost = _checked(non_vulnerable_lost, "non_vulnerable_lost")
    o_total = _checked(non_vulnerable_total, "non_vulnerable_total")
    v_rate = _rate(v_lost, v_total)
    o_rate = _rate(o_lost, o_total)

    def result(status: str, ratio: float | None, band: str | None, interpretation: str) -> ReplayEquityGap:
        return ReplayEquityGap(
            status=status,
            reason=None if status == STATUS_RATIO else status,
            vulnerable_rate=v_rate,
            non_vulnerable_rate=o_rate,
            ratio=ratio,
            band=band,
            interpretation=interpretation,
            vulnerable_total=v_total,
            non_vulnerable_total=o_total,
            minimum_group_size=minimum_group_size,
        )

    if v_total < minimum_group_size or o_total < minimum_group_size:
        return result(
            REASON_INSUFFICIENT_GROUP, None, None,
            f"Equity gap not computed: a group has fewer than {minimum_group_size} residents.",
        )
    if v_rate == 0 and o_rate == 0:
        return result(REASON_NO_LOSS, None, None, "Equity gap not computed: neither group has lost access.")
    if o_rate == 0:
        return result(
            REASON_UNDEFINED_RATIO, None, None,
            "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.",
        )
    ratio = round(v_rate / o_rate, 3)
    if ratio > HIGHER_ABOVE:
        return result(STATUS_RATIO, ratio, "higher", f"Vulnerable residents are {ratio:.3g} times more likely to lose access.")
    if ratio < LOWER_BELOW:
        return result(STATUS_RATIO, ratio, "lower", f"Vulnerable residents are {ratio:.3g} times as likely to lose access.")
    return result(STATUS_RATIO, ratio, "similar", "Access-loss rates are broadly similar between groups.")
