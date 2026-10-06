"""The replay's Evacuation Equity Gap, its denominator and its null rule (``floodguard.replay_equity``).

The rule (owner decision R8, option B): each group's loss rate is, of its residents who had a shelter within
reach before the flood, the share who lost it. No ratio when a group has fewer than 50 such residents
(``insufficient_group_denominator``) or when nobody has lost access (``no_loss``); otherwise the same figures
as ``floodguard.equity_v1`` gives for the same numerators and denominators. ``floodguard.equity_v1`` is metric
version 1, kept unchanged; ``floodguard.equity`` (version 2.0) is not the reference. The inputs are
(vulnerable lost, vulnerable within reach, other lost, other within reach); all are small synthetic numbers
unless a test says otherwise; "vulnerable" is the terrain/remoteness proxy.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import math

import pandas as pd
import pytest

# The replay's rule is checked against equity metric version 1, the code it was written beside;
# floodguard.equity itself is version 2.0 since the scoring line was merged in.
from floodguard import equity_v1 as equity, replay_equity
from floodguard.replay_equity import (
    DENOMINATOR,
    MINIMUM_GROUP_SIZE,
    NULL_REASONS,
    REASON_INSUFFICIENT_GROUP,
    REASON_NO_LOSS,
    REASON_UNDEFINED_RATIO,
    ReplayEquityError,
    ReplayEquityGap,
    replay_equity_gap,
)


def reference(vulnerable_lost: float, vulnerable_total: float, other_lost: float, other_total: float) -> pd.Series:
    """The unchanged ``floodguard.equity_v1`` result for the same four numbers (its totals take the within-reach residents)."""
    frame = pd.DataFrame({
        "subdistrict_id": ["case"], "subdistrict_name": ["case"], "confidence_class": ["low"],
        "total_vulnerable_population": [vulnerable_total], "vulnerable_population_losing_access": [vulnerable_lost],
        "total_non_vulnerable_population": [other_total], "non_vulnerable_population_losing_access": [other_lost],
    })
    return equity.compute_equity_gap(frame).iloc[0]


# --- A ratio, where one can be stated ----------------------------------------------------------------


def test_ratio_of_loss_rates_with_bands_and_wording() -> None:
    higher = replay_equity_gap(20, 100, 10, 100)
    assert (higher.status, higher.reason) == ("ratio", None)
    assert (higher.vulnerable_rate, higher.non_vulnerable_rate, higher.ratio, higher.band) == (0.2, 0.1, 2.0, "higher")
    assert higher.interpretation == "Vulnerable residents are 2 times more likely to lose access."
    lower = replay_equity_gap(34.3, 7151.6, 5671, 74646.9)
    assert (lower.vulnerable_rate, lower.non_vulnerable_rate, lower.ratio, lower.band) == (0.0048, 0.076, 0.063, "lower")
    assert lower.interpretation == "Vulnerable residents are 0.063 times as likely to lose access."
    similar = replay_equity_gap(11, 100, 10, 100)
    assert (similar.ratio, similar.band) == (1.1, "similar")
    assert similar.interpretation == "Access-loss rates are broadly similar between groups."


@pytest.mark.parametrize(
    ("vulnerable_lost", "band"),
    [(1200, "similar"), (1201, "higher"), (1199, "similar"), (800, "similar"), (799, "lower"), (801, "similar")],
)
def test_band_limits_are_above_1_2_and_below_0_8(vulnerable_lost: int, band: str) -> None:
    assert replay_equity_gap(vulnerable_lost, 10000, 1000, 10000).band == band


def test_no_vulnerable_loss_is_a_ratio_of_zero_not_a_missing_value() -> None:
    gap = replay_equity_gap(0, 2440, 7086, 32085)
    assert (gap.status, gap.reason, gap.ratio, gap.band) == ("ratio", None, 0.0, "lower")


# --- The denominator: residents within reach before the flood (R8, option B) ---------------------------


def test_each_rate_divides_by_the_residents_within_reach_before_the_flood() -> None:
    assert DENOMINATOR == "within_reach_before_flood"
    # 1,000 proxy-vulnerable residents are counted, 100 of them had a shelter within reach and 80 lost it;
    # of 10,000 others, 4,000 had one within reach and 2,000 lost it. The rates are 80/100 and 2,000/4,000.
    gap = replay_equity_gap(80, 100, 2000, 4000)
    assert (gap.vulnerable_rate, gap.non_vulnerable_rate, gap.ratio, gap.band) == (0.8, 0.5, 1.6, "higher")
    assert (gap.vulnerable_within_reach, gap.non_vulnerable_within_reach, gap.denominator) == (100.0, 4000.0, DENOMINATOR)
    # Over all residents counted (80/1,000 and 2,000/10,000) the direction would flip; that is another input.
    assert replay_equity_gap(80, 1000, 2000, 10000).band == "lower"


def test_the_served_figures_at_the_peak_read_higher_for_the_plan_of_eight() -> None:
    # Mae Sai r4 at the 3.5 m peak, all residents, rounded to whole residents (the parity fixture holds the
    # unrounded sums): plan of 8 sites 320 of 373 against 13,109 of 24,537; reported set 0 of 2,440.
    plan = replay_equity_gap(320, 373, 13109, 24537)
    assert (plan.ratio, plan.band, plan.reason) == (1.606, "higher", None)
    assert plan.interpretation == "Vulnerable residents are 1.61 times more likely to lose access."
    reported = replay_equity_gap(0, 2440, 7086, 32085)
    assert (reported.ratio, reported.band, reported.reason) == (0.0, "lower", None)
    # The default view: nobody of the proxy-vulnerable group within reach of a reported site before the flood.
    default = replay_equity_gap(0, 0, 5400, 5698)
    assert (default.reason, default.ratio, default.vulnerable_rate) == (REASON_INSUFFICIENT_GROUP, None, None)


@pytest.mark.parametrize(
    "inputs",
    [(101, 100, 10, 100), (10, 100, 100.5, 100), (1, 0, 10, 100), (320, 26.5, 100, 7553.2)],
)
def test_more_residents_lost_than_were_within_reach_is_refused(inputs: tuple[float, float, float, float]) -> None:
    # Only a resident who had a shelter within reach can lose it; a larger count means the wrong denominator.
    with pytest.raises(ReplayEquityError, match="within_reach"):
        replay_equity_gap(*inputs)


def test_float_noise_between_two_sums_of_the_same_residents_is_tolerated() -> None:
    # Everyone within reach lost access, and the two sums differ in the last bits.
    gap = replay_equity_gap(26.540000000000003, 26.54, 7093.5, 7553.2)
    assert gap.reason == REASON_INSUFFICIENT_GROUP
    assert replay_equity_gap(373.0000001, 373, 24537, 24537).ratio == 1.0


# --- The null rule -----------------------------------------------------------------------------------


def test_no_loss_gives_no_ratio_with_a_reason() -> None:
    gap = replay_equity_gap(0, 50, 0, 100)
    assert gap.ratio is None and gap.band is None
    assert (gap.status, gap.reason) == (REASON_NO_LOSS, "no_loss")
    assert (gap.vulnerable_rate, gap.non_vulnerable_rate) == (0.0, 0.0)
    assert gap.interpretation == "Equity gap not computed: neither group has lost access."
    # floodguard.equity_v1 states 1.0 for the same input; the replay does not.
    assert float(reference(0, 50, 0, 100)["equity_gap_ratio"]) == 1.0


def test_a_loss_too_small_for_the_rounded_rate_is_still_a_loss() -> None:
    # Three residents lost in a group of 74,647 is a rate of 0.0000. The rule reads the lost counts, so this is
    # neither "nobody has lost access" nor "only vulnerable residents have".
    other_only = replay_equity_gap(0, 7152, 3, 74647)
    assert (other_only.vulnerable_rate, other_only.non_vulnerable_rate) == (0.0, 0.0)
    assert (other_only.status, other_only.reason, other_only.ratio, other_only.band) == ("ratio", None, 0.0, "lower")
    assert (other_only.vulnerable_lost, other_only.non_vulnerable_lost) == (0.0, 3.0)
    # floodguard.equity_v1 reads the same input as zero loss in both groups.
    assert float(reference(0, 7152, 3, 74647)["equity_gap_ratio"]) == 1.0
    # Both groups lost a little: the ratio comes from the unrounded rates, (1 / 7152) / (3 / 74647).
    both = replay_equity_gap(1, 7152, 3, 74647)
    assert (both.vulnerable_rate, both.non_vulnerable_rate, both.ratio, both.band) == (0.0001, 0.0, 3.479, "higher")
    assert both.interpretation == "Vulnerable residents are 3.48 times more likely to lose access."
    assert replay_equity_gap(0.004, 100, 0.004, 100).ratio == 1.0
    # Only the other group's rate rounds to zero: a ratio, not "undefined".
    small_other = replay_equity_gap(5, 100, 0.004, 100)
    assert (small_other.reason, small_other.ratio, small_other.band) == (None, 1250.0, "higher")
    assert pd.isna(reference(5, 100, 0.004, 100)["equity_gap_ratio"])
    # A vulnerable rate that rounds to zero beside a large other loss stays a ratio of 0.0, as before.
    assert (replay_equity_gap(0.3, 7152, 5671, 74647).ratio, replay_equity_gap(0.3, 7152, 5671, 74647).band) == (0.001, "lower")
    # With no loss at all in the other group the ratio stays undefined, however small the vulnerable loss.
    assert replay_equity_gap(2, 7152, 0, 74647).reason == REASON_UNDEFINED_RATIO
    assert replay_equity_gap(0, 7152, 0, 74647).reason == REASON_NO_LOSS


@pytest.mark.parametrize(
    "inputs",
    [(10, 49, 100, 1000), (10, 49.99, 100, 1000), (100, 1000, 10, 49), (1, 3, 1, 7), (1, 1, 100, 1000), (0, 0, 5, 50), (5, 50, 0, 0), (0, 0, 0, 0)],
)
def test_fewer_than_50_residents_within_reach_in_a_group_gives_no_ratio_with_a_reason(inputs: tuple[float, float, float, float]) -> None:
    gap = replay_equity_gap(*inputs)
    assert gap.ratio is None and gap.band is None
    assert (gap.status, gap.reason) == (REASON_INSUFFICIENT_GROUP, "insufficient_group_denominator")
    assert gap.interpretation == "Equity gap not computed: a group has fewer than 50 residents with a shelter within reach before the flood."
    assert gap.minimum_group_size == MINIMUM_GROUP_SIZE == 50
    assert (gap.vulnerable_within_reach, gap.non_vulnerable_within_reach) == (inputs[1], inputs[3])


def test_exactly_50_residents_per_group_is_enough() -> None:
    assert replay_equity_gap(10, 50, 100, 1000).ratio == 2.0
    assert replay_equity_gap(100, 1000, 10, 50).ratio == 0.5
    assert replay_equity_gap(0, 50, 0, 50).reason == REASON_NO_LOSS


def test_a_small_group_still_reports_its_rates_and_an_empty_group_has_none() -> None:
    small = replay_equity_gap(10, 49, 100, 1000)
    assert (small.vulnerable_rate, small.non_vulnerable_rate) == (0.2041, 0.1)
    assert (replay_equity_gap(0, 0, 5, 50).vulnerable_rate, replay_equity_gap(0, 0, 5, 50).non_vulnerable_rate) == (None, 0.1)
    assert (replay_equity_gap(5, 50, 0, 0).vulnerable_rate, replay_equity_gap(5, 50, 0, 0).non_vulnerable_rate) == (0.1, None)


def test_group_size_is_checked_before_loss_so_the_reason_does_not_change_with_the_hour() -> None:
    assert replay_equity_gap(0, 26.5, 0, 7553.2).reason == REASON_INSUFFICIENT_GROUP
    assert replay_equity_gap(5, 26.5, 0, 7553.2).reason == REASON_INSUFFICIENT_GROUP
    assert replay_equity_gap(5, 26.5, 100, 7553.2).reason == REASON_INSUFFICIENT_GROUP
    assert NULL_REASONS == (REASON_INSUFFICIENT_GROUP, REASON_NO_LOSS, REASON_UNDEFINED_RATIO)


def test_only_vulnerable_loss_is_undefined() -> None:
    gap = replay_equity_gap(5, 50, 0, 100)
    assert (gap.status, gap.reason, gap.ratio, gap.band) == (REASON_UNDEFINED_RATIO, "undefined_ratio", None, None)
    assert gap.interpretation == str(reference(5, 50, 0, 100)["interpretation_text"])


def test_the_minimum_group_size_can_be_set_for_another_study() -> None:
    assert replay_equity_gap(10, 49, 100, 1000, minimum_group_size=30).ratio == 2.041
    gap = replay_equity_gap(10, 49, 100, 1000, minimum_group_size=100)
    assert gap.reason == REASON_INSUFFICIENT_GROUP and "fewer than 100 residents with a shelter within reach" in gap.interpretation
    # An empty group never gives a ratio, whatever the minimum, and a minimum below 1 is refused.
    empty = replay_equity_gap(0, 0, 5, 100, minimum_group_size=1)
    assert (empty.reason, empty.ratio, empty.vulnerable_rate) == (REASON_INSUFFICIENT_GROUP, None, None)
    for bad in (0, -1, 0.5, float("nan"), True):
        with pytest.raises(ReplayEquityError, match="minimum_group_size"):
            replay_equity_gap(0, 0, 5, 100, minimum_group_size=bad)


def test_reason_is_none_exactly_when_there_is_a_ratio() -> None:
    cases = [(20, 100, 10, 100), (0, 100, 10, 100), (0, 100, 0, 100), (5, 100, 0, 100), (1, 10, 1, 100), (0, 0, 0, 0), (50, 50, 100, 100)]
    for case in cases:
        gap = replay_equity_gap(*case)
        assert (gap.reason is None) == (gap.ratio is not None), case
        assert (gap.band is None) == (gap.ratio is None), case
        assert gap.status == (gap.reason or "ratio"), case


# --- Agreement with the unchanged floodguard.equity_v1 -------------------------------------------------


@pytest.mark.parametrize(
    "inputs",
    [
        (1200, 10000, 1000, 10000), (1201, 10000, 1000, 10000), (799, 10000, 1000, 10000), (500, 10000, 500, 10000),
        (100, 300, 100, 700), (200, 300, 100, 700), (5000, 10000, 4, 10000), (1, 10000, 5000, 10000),
        (5, 100000, 1000, 10000), (15, 100000, 1000, 10000), (12345, 100000, 1000, 10000), (0.004, 100, 10, 100),
        (0, 2440, 7086, 32085), (50, 50, 100, 100), (34.3, 7151.6, 5671, 74646.9), (5, 50, 0, 100),
    ],
)
def test_same_rates_ratio_and_wording_as_floodguard_equity_wherever_a_ratio_or_undefined_is_stated(inputs: tuple[float, ...]) -> None:
    gap = replay_equity_gap(*inputs)
    base = reference(*inputs)
    assert gap.vulnerable_rate == float(base["vulnerable_access_loss_rate"])
    assert gap.non_vulnerable_rate == float(base["non_vulnerable_access_loss_rate"])
    assert gap.interpretation == str(base["interpretation_text"])
    if gap.reason is None:
        assert gap.ratio == float(base["equity_gap_ratio"])
    else:
        assert gap.reason == REASON_UNDEFINED_RATIO and pd.isna(base["equity_gap_ratio"])


def test_floodguard_equity_is_not_wrapped_or_imported() -> None:
    # Plan section 5.6 kept the equity module unchanged (that code is now equity_v1.py); the replay's rule is its
    # own function, not a wrapper of either version.
    source = inspect.getsource(replay_equity)
    assert "import pandas" not in source and "from floodguard.equity" not in source and "import equity" not in source
    assert float(reference(0, 100, 0, 100)["equity_gap_ratio"]) == 1.0


# --- Inputs and output shape ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), -0.001])
def test_negative_or_non_finite_inputs_are_refused(bad: float) -> None:
    for position in range(4):
        values = [10.0, 100.0, 10.0, 100.0]
        values[position] = bad
        with pytest.raises(ReplayEquityError):
            replay_equity_gap(*values)


def test_result_is_a_frozen_record_that_serialises_to_json_without_a_score_or_class() -> None:
    gap = replay_equity_gap(20, 100, 10, 100)
    assert isinstance(gap, ReplayEquityGap)
    with pytest.raises(dataclasses.FrozenInstanceError):
        gap.ratio = 1.0  # type: ignore[misc]
    record = json.loads(json.dumps(gap.as_dict()))
    assert record["ratio"] == 2.0 and record["reason"] is None and record["minimum_group_size"] == 50
    assert record["denominator"] == "within_reach_before_flood"
    assert (record["vulnerable_within_reach"], record["non_vulnerable_within_reach"]) == (100.0, 100.0)
    assert "vulnerable_total" not in record and "non_vulnerable_total" not in record
    assert not any("fpps" in key or "action_class" in key or "score" in key for key in record)
    assert json.loads(json.dumps(replay_equity_gap(0, 0, 0, 0).as_dict()))["vulnerable_rate"] is None
    assert not math.isnan(gap.ratio)


def test_module_states_what_the_figures_are() -> None:
    text = " ".join(replay_equity.__doc__.split())
    assert "T1 scenario" in text and "not an observed evacuation outcome" in text
    assert "terrain and remoteness proxy" in text
    assert "Of the residents in the group who had a shelter within reach before the flood, the share who lost it." in text
    assert "owner decision R8, option B" in text
    assert "No priority score and no action class" in text
