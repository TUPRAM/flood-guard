"""The committed equity/access parity fixture must be what the Python code computes today.

The web tests check ``flood-timeline-evacuation.ts`` against
``apps/web/src/lib/__fixtures__/mae-sai-equity-access-parity.json``. That only proves parity with Python if
the fixture is current, so this test regenerates it in memory and compares. When it fails, a rule changed in
``floodguard.replay_equity``, ``floodguard.shelter_set_comparison``, ``floodguard.equity`` or
``scripts/mae_sai_timeline_evacuation.py`` (or the served manifest changed): run
``python apps/web/scripts/equity-access-parity-fixture.py`` and let the web tests judge the TypeScript side.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "apps" / "web" / "scripts" / "equity-access-parity-fixture.py"
FIXTURE = ROOT / "apps" / "web" / "src" / "lib" / "__fixtures__" / "mae-sai-equity-access-parity.json"
TOO_SMALL = "Equity gap not computed: a group has fewer than 50 residents with a shelter within reach before the flood."
NO_LOSS = "Equity gap not computed: neither group has lost access."


@pytest.fixture(scope="module")
def generator():
    pytest.importorskip("rasterio")  # The builder stage the generator loads imports it.
    spec = importlib.util.spec_from_file_location("equity_access_parity_fixture", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_fixture_equals_a_fresh_python_computation(generator) -> None:
    committed = FIXTURE.read_bytes()
    assert b"\r" not in committed
    assert generator.fixture_text() == committed.decode("utf-8")


def test_fixture_is_labelled_as_a_scenario_with_a_vulnerability_proxy() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["scenario_tier"].startswith("T1 scenario (model)")
    assert "vulnerable = terrain/remoteness proxy" in fixture["vulnerable_definition"]
    assert fixture["confidence"] == "low" and fixture["source_timestamp"] and len(fixture["assumptions"]) >= 3
    assert fixture["official_warning"] is False
    # Access and equity figures only: no priority score and no action class.
    assert not any("fpps" in key.lower() or "action_class" in key.lower() for key in fixture)


def edge_rows(generator) -> dict[str, list]:
    inputs = generator.EQUITY_EDGE_INPUTS
    return {name: row for (name, *_), row in zip(inputs, generator.equity_rows([row[1:] for row in inputs]))}


def test_edge_cases_pin_both_band_limits_and_every_undefined_result(generator) -> None:
    rows = edge_rows(generator)
    band = lambda name: rows[name][7]  # noqa: E731
    assert band("ratio exactly 1.2 (upper limit of similar)") == "similar" and band("ratio 1.201 (just above 1.2)") == "higher"
    assert band("ratio exactly 0.8 (lower limit of similar)") == "similar" and band("ratio 0.799 (just below 0.8)") == "lower"
    assert rows["only vulnerable loss"][6:] == [None, None, "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.", "undefined_ratio"]
    assert rows["no vulnerable residents"][4:8] == [None, 0.1, None, None]
    assert rows["no other residents"][4:8] == [0.1, None, None, None]


def test_edge_cases_cover_both_null_reasons_of_the_replay_rule(generator) -> None:
    rows = edge_rows(generator)
    no_loss = [None, None, "Equity gap not computed: neither group has lost access.", "no_loss"]
    too_small = [None, None, TOO_SMALL, "insufficient_group_denominator"]
    # Nobody has lost access: no ratio (never the 1.0 that floodguard.equity states), with the reason.
    for name in ("no loss in either group", "no loss, both groups large", "no loss, groups of exactly 50"):
        assert rows[name][4:] == [0.0, 0.0, *no_loss], name
        assert (rows[name][0], rows[name][2]) == (0.0, 0.0), name
    # A loss too small for the rounded rate is still a loss: a ratio from the unrounded rates, never "no loss".
    assert rows["both rates round to zero"][4:] == [0.0, 0.0, 1.0, "similar", "Access-loss rates are broadly similar between groups.", None]
    assert rows["small loss in a large group, no vulnerable loss"][4:] == [0.0, 0.0, 0.0, "lower", "Vulnerable residents are 0 times as likely to lose access.", None]
    assert rows["small loss in both large groups"][4:] == [0.0001, 0.0, 3.479, "higher", "Vulnerable residents are 3.48 times more likely to lose access.", None]
    assert rows["only the non-vulnerable rate rounds to zero"][6:8] == [1250.0, "higher"]
    assert rows["small vulnerable loss only, large groups"][6:] == [None, None, "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.", "undefined_ratio"]
    # A group below 50 residents within reach before the flood: no ratio, with the reason, whatever was lost.
    for name in ("vulnerable group of 49.99 (too small)", "vulnerable group of 49 (too small)", "other group of 49 (too small)",
                 "both groups too small", "one resident in the vulnerable group", "too small and no loss (group size is the reason)",
                 "too small and only vulnerable loss (group size is the reason)", "no vulnerable residents", "no other residents",
                 "no residents at all", "no vulnerable residents and no other loss",
                 "nobody in the vulnerable group within reach (the default view)",
                 "27 vulnerable residents within reach, all lost (too small)"):
        assert rows[name][6:] == too_small, name
        assert min(rows[name][1], rows[name][3]) < 50, name
    # Exactly 50 is enough.
    assert rows["vulnerable group of exactly 50 (enough)"][6:] == [2.0, "higher", "Vulnerable residents are 2 times more likely to lose access.", None]
    assert rows["other group of exactly 50 (enough)"][6:] == [0.5, "lower", "Vulnerable residents are 0.5 times as likely to lose access.", None]
    reasons = {row[9] for row in rows.values()}
    assert reasons == {None, "insufficient_group_denominator", "no_loss", "undefined_ratio"}


def test_fixture_records_the_null_rule_and_no_ratio_before_the_water_rises() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["equity_minimum_group"] == 50
    assert fixture["equity_null_reasons"] == ["insufficient_group_denominator", "no_loss", "undefined_ratio"]
    assert fixture["equity_columns"][-1] == "reason" and fixture["access_level_columns"][-1] == "reason"
    assert fixture["equity_denominator"] == "within_reach_before_flood"
    assert fixture["equity_columns"][:4] == ["vulnerable_lost", "vulnerable_within_reach", "non_vulnerable_lost", "non_vulnerable_within_reach"]
    for group in fixture["access"]:
        reach = group["within_reach"]
        if min(reach["vulnerable"], reach["non_vulnerable"]) < 50:
            # The group-size rule comes first, so the reason is the same at every level.
            assert {row[9] for row in group["levels"]} == {"insufficient_group_denominator"}
        else:
            # Level 0 is the state before the flood: nobody has lost access, so there is no ratio to state.
            assert group["levels"][0][6:] == [None, None, NO_LOSS, "no_loss"]
        for row in group["levels"]:
            assert (row[9] is None) == (row[6] is not None)


def test_fixture_divides_by_the_residents_within_reach_before_the_flood() -> None:
    """Owner decision R8, option B: lost / within reach before the flood, never lost / all residents counted."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_key = {(group["set"], group["scope"]): group for group in fixture["access"]}
    peak = round(fixture["peak_stage_m"] / fixture["level_step_m"])
    for group in fixture["access"]:
        reach, totals = group["within_reach"], group["totals"]
        assert reach["population"] + group["no_baseline_access"] == pytest.approx(totals["population"], abs=1e-6)
        assert reach["vulnerable"] <= totals["vulnerable"] and reach["non_vulnerable"] <= totals["non_vulnerable"]
        for row in group["levels"]:
            # Columns: level, people lost, vulnerable lost, other lost, vulnerable rate, other rate, ...
            for lost, within, rate in ((row[2], reach["vulnerable"], row[4]), (row[3], reach["non_vulnerable"], row[5])):
                assert lost <= within + 1e-6
                assert rate == (None if within == 0 else round(lost / within, 4))
    # Plan of 8 sites at the 3.5 m peak, all residents: 320 of 373 against 13,109 of 24,537, about 1.6 ("higher").
    plan = by_key[("plan_8", "all")]
    assert (round(plan["within_reach"]["vulnerable"]), round(plan["within_reach"]["non_vulnerable"])) == (373, 24537)
    assert (round(plan["totals"]["vulnerable"]), round(plan["totals"]["non_vulnerable"])) == (7152, 74647)
    row = plan["levels"][peak]
    assert (round(row[2]), round(row[3])) == (320, 13109)
    assert row[4:] == [0.8577, 0.5342, 1.606, "higher", "Vulnerable residents are 1.61 times more likely to lose access.", None]
    # Reported 2024 set, all residents: none of the 2,440 proxy-vulnerable residents within reach lost access.
    reported = by_key[("reported_2024", "all")]
    assert round(reported["within_reach"]["vulnerable"]) == 2440
    assert (reported["levels"][peak][2], reported["levels"][peak][6], reported["levels"][peak][7]) == (0.0, 0.0, "lower")
    # The default view (reported set, residents whose homes flood): 103 proxy-vulnerable residents counted, none of
    # them within reach of a reported site before the flood, so no ratio at any level.
    default = by_key[("reported_2024", "flooded")]
    assert (default["within_reach"]["vulnerable"], round(default["totals"]["vulnerable"])) == (0.0, 103)
    assert default["levels"][peak][4:] == [None, 0.9476, None, None, TOO_SMALL, "insufficient_group_denominator"]
    # Among residents whose homes flood the default plan has 27 proxy-vulnerable residents within reach: too few.
    wet_plan = by_key[("plan_8", "flooded")]
    assert round(wet_plan["within_reach"]["vulnerable"]) == 27
    assert wet_plan["levels"][peak][6:] == [None, None, TOO_SMALL, "insufficient_group_denominator"]


def test_fixture_holds_the_shelter_set_comparison_for_every_set_and_scope() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "apps" / "web" / "public" / fixture["manifest"].lstrip("/")).read_text(encoding="utf-8"))
    groups = fixture["set_comparison"]
    assert [(group["set"], group["scope"]) for group in groups] == [(set_id, scope) for set_id in manifest["access"]["sets"] for scope in ("all", "flooded")]
    assert fixture["cutoff_coverage_share"] == 0.5
    by_key = {(group["set"], group["scope"]): group for group in groups}
    whole = lambda value: round(value)  # noqa: E731
    # The eight figures of the roadmap critic at the 3.5 m peak (P2-4), recomputed by Python.
    reported_all, reported_wet = by_key[("reported_2024", "all")], by_key[("reported_2024", "flooded")]
    plan_all, plan_wet = by_key[("plan_8", "all")], by_key[("plan_8", "flooded")]
    assert fixture["peak_stage_m"] == 3.5
    assert (whole(reported_all["baseline"]), whole(reported_all["at_peak"]["lost"]), round(reported_all["at_peak"]["lost_share"] * 100)) == (34525, 7086, 21)
    assert (whole(reported_wet["baseline"]), whole(reported_wet["at_peak"]["keeping"])) == (5698, 299)
    assert (whole(plan_all["baseline"]), whole(plan_all["at_peak"]["lost"]), round(plan_all["at_peak"]["lost_share"] * 100)) == (24910, 13429, 54)
    assert (whole(plan_wet["baseline"]), whole(plan_wet["at_peak"]["keeping"])) == (7580, 460)
    # Proxy-vulnerable residents lost: 0 of 2,440 with the reported set, 320 of 373 with the plan of 8.
    assert (whole(reported_all["at_peak"]["vulnerable_lost"]), whole(reported_all["vulnerable_baseline"])) == (0, 2440)
    assert (whole(plan_all["at_peak"]["vulnerable_lost"]), whole(plan_all["vulnerable_baseline"])) == (320, 373)
    # Neither set leads on both ways of counting.
    assert reported_all["baseline"] > plan_all["baseline"] and plan_wet["baseline"] > reported_wet["baseline"]
    for group in groups:
        assert group["at_peak"]["keeping"] + group["at_peak"]["lost"] == pytest.approx(group["baseline"], abs=1e-6)
        assert (group["cutoff_hour"] is None) == (group["cutoff_status"] != "reached")
        assert not any("rank" in key or "score" in key or "fpps" in key or "class" in key for key in group)
