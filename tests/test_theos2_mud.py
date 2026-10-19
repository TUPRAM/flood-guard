"""The mud track of the THEOS-2 scene of 17 September 2024: scaling, candidates, groups, draw and choice, on invented arrays."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard import theos2_mud as mud


def test_theil_sen_is_exact_and_matches_scipy() -> None:
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(3)
    x = rng.integers(200, 900, 700).astype(float)
    y = 0.0004 * x - 0.03 + rng.normal(0, 0.01, x.size)
    y[:40] += 0.5  # outliers move a least-squares line, not this one
    ours = mud.theil_sen(x, y, chunk=97)
    slope, intercept, _low, _high = stats.theilslopes(y, x)
    assert ours["slope"] == pytest.approx(slope, rel=1e-12) and ours["intercept"] == pytest.approx(intercept, rel=1e-9)
    assert ours["pairs"] == int(((x[:, None] != x[None, :]).sum()) // 2)
    with pytest.raises(mud.MudError):
        mud.theil_sen([1.0, 1.0], [2.0, 3.0])


def test_the_colour_rule_of_the_mud_line() -> None:
    limits = mud.MudLimits()
    red, green, blue = np.array([0.20, 0.20, 0.20, 0.20]), np.array([0.15, 0.19, 0.15, 0.15]), np.array([0.10, 0.10, 0.18, 0.10])
    nir = np.array([0.25, 0.25, 0.25, 0.40])
    # mud; red not above 1.08 green; red not above 1.3 blue; plants (NDVI 0.33)
    assert mud.colour_rule(red, green, blue, nir, limits).tolist() == [True, False, False, False]


def test_small_objects_are_dropped_and_unobservable_stays_unobservable() -> None:
    colour = np.zeros((6, 8), dtype=bool)
    colour[0:2, 0:3] = True  # six pixels: kept
    colour[4, 6:8] = True  # two pixels: dropped
    observable = np.ones((6, 8), dtype=bool)
    observable[0, 0] = False
    result = mud.answer(colour, observable)
    assert result[0, 0] == mud.MUD_UNOBSERVABLE and result[1, 1] == mud.MUD_YES and result[4, 6] == mud.MUD_NO
    before = np.ones((6, 8), dtype=bool)
    before[1, :] = False
    assert (mud.answer(colour, observable, before) == mud.MUD_YES).sum() == 0, "two pixels left after the condition: dropped"


def test_groups_follow_the_six_metre_edge() -> None:
    answers = np.zeros((1, 16), dtype="uint8")
    answers[0, :9] = mud.MUD_YES
    answers[0, 15] = mud.MUD_UNOBSERVABLE
    found = mud.groups(answers)
    names = [mud.GROUPS[i] for i in found[0]]
    assert names[:6] == ["mud_inside"] * 6 and names[6:9] == ["mud_edge"] * 3
    assert names[9:12] == ["near_mud"] * 3 and names[12:15] == ["ground_far"] * 3 and names[15] == "unobservable"


def test_allocation_halves_each_group_and_spills_a_shortfall() -> None:
    available = {(g, o): 1000 for g in mud.GROUPS for o in ("a", "b")}
    available[("mud_inside", "b")] = 5
    available[("unobservable", "a")] = 0
    available[("unobservable", "b")] = 3
    taken = mud.allocate(available, mud.DEVELOPMENT_POINTS, ("a", "b"))
    assert taken[("mud_inside", "a")] == 35 and taken[("mud_inside", "b")] == 5
    assert taken[("unobservable", "b")] == 3 and taken[("unobservable", "a")] == 0
    assert sum(taken.values()) == sum(mud.DEVELOPMENT_POINTS.values()), "the unobservable shortfall went to ground_far"


def test_the_draw_is_reproducible_and_keeps_to_its_group_and_order() -> None:
    group = np.repeat(np.arange(5, dtype="uint8"), 20).reshape(5, 20)
    order = np.zeros((5, 20), dtype="uint8")
    order[:, 10:] = 1
    counts = {(g, o): 2 for g in mud.GROUPS for o in ("a", "b")}
    first = mud.draw(group, order, ("a", "b"), counts, seed=7)
    assert first == mud.draw(group, order, ("a", "b"), counts, seed=7) and len(first) == 20
    for point in first:
        assert mud.GROUPS[group[point["row"], point["column"]]] == point["group"] and ("a", "b")[order[point["row"], point["column"]]] == point["order"]
    with pytest.raises(mud.MudError):
        mud.draw(group, order, ("a", "b"), {("mud_inside", "a"): 11}, seed=7)


def test_weighted_f1_and_the_choice_with_its_margin() -> None:
    points = [{"group": "mud_inside", "order": "a", "label": "mud"}, {"group": "ground_far", "order": "a", "label": "not_mud"},
              {"group": "ground_far", "order": "a", "label": "mud"}, {"group": "near_mud", "order": "a", "label": "cannot_tell"}]
    weights = {("mud_inside", "a"): 10.0, ("ground_far", "a"): 100.0, ("near_mud", "a"): 5.0}
    result = mud.weighted_f1(points, [True, False, False, True], weights)
    assert result["points"] == 3 and result["f1"] == pytest.approx(2 * 10 / (2 * 10 + 0 + 100), abs=1e-4)
    assert mud.choose({"mud_s0": 0.50, "mud_s1": 0.519, "mud_s2": 0.60}) == "mud_s2"
    assert mud.choose({"mud_s0": 0.50, "mud_s1": 0.52, "mud_s2": 0.535}) == "mud_s1"
    assert mud.choose({"mud_s0": 0.50, "mud_s1": 0.51, "mud_s2": 0.515}) == "mud_s0"
    assert len(mud.threshold_grid()) == 64 and mud.threshold_grid()[0] == mud.MudLimits(0.15, 1.00, 1.1)


def test_the_mud_records_were_made_in_the_order_of_the_plan() -> None:
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    folder = root / "outputs" / "theos2_17sep_mud"
    points_path = folder / "development_points_v1.json"
    if not points_path.exists():
        pytest.skip("the development points have not been drawn")
    plan = root / "docs" / "proposal_execution" / "theos2_17sep_recession_and_mud_plan_v1.md"
    points = json.loads(points_path.read_text(encoding="utf-8"))
    assert points["plan"]["sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert points["official_warning"] is False and points["can_feed_decision_layer"] is False and points["source_timestamp"]
    assert points["confidence_class"] == "low" and points["assumptions"] and points["limits"]
    assert sum(points["points_per_group"].values()) == sum(mud.DEVELOPMENT_POINTS.values())
    assert set(points["scaling"]["lines"]) == {"red", "green", "blue", "nir"} and points["scaling"]["seed"] == mud.SCALING_SEED
    freeze_path = folder / "freeze_v1.json"
    if not freeze_path.exists():
        return
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["points_record"]["sha256"] == hashlib.sha256(points_path.read_bytes()).hexdigest()
    assert freeze["chosen"] in mud.CANDIDATES and len(freeze["labels"]["by_point"]) == sum(mud.DEVELOPMENT_POINTS.values())
    assert set(freeze["labels"]["by_point"].values()) <= set(mud.LABELS)
    assert not (folder / "test_points_v1.json").exists() or freeze_path.stat().st_size > 0
