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


def test_amendment_1_objects_of_100_square_metres_and_the_new_choice_order() -> None:
    colour = np.zeros((10, 10), dtype=bool)
    colour[0:4, 0:6] = True  # 24 pixels: kept at 5, dropped at 25
    colour[6:10, 3:10] = True  # 28 pixels: kept at both
    observable = np.ones((10, 10), dtype=bool)
    assert (mud.answer(colour, observable) == mud.MUD_YES).sum() == 52
    assert (mud.answer(colour, observable, None, mud.MIN_OBJECT_PX_V2) == mud.MUD_YES).sum() == 28
    order = ("mud_s0", "mud_s3", "mud_s4")
    assert mud.choose({"mud_s0": 0.23, "mud_s3": 0.40, "mud_s4": 0.41}, order=order) == "mud_s3"
    assert mud.choose({"mud_s0": 0.23, "mud_s3": 0.24, "mud_s4": 0.30}, order=order) == "mud_s4"
    assert mud.choose({"mud_s0": 0.23, "mud_s3": 0.24, "mud_s4": 0.24}, order=order) == "mud_s0"


def test_a_shortfall_in_the_opened_ground_goes_to_the_other_order_then_to_the_other_half() -> None:
    available = {("opened_mud", "a"): 3, ("opened_mud", "b"): 4, ("opened_not_mud", "a"): 500, ("opened_not_mud", "b"): 500}
    taken = mud.allocate(available, mud.OPENED_POINTS, ("a", "b"), mud.OPENED_STRATA, spill_to="opened_not_mud")
    assert taken[("opened_mud", "a")] == 3 and taken[("opened_mud", "b")] == 4
    assert sum(taken.values()) == 40 and taken[("opened_not_mud", "a")] + taken[("opened_not_mud", "b")] == 33


def test_the_second_freeze_follows_amendment_1() -> None:
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    folder = root / "outputs" / "theos2_17sep_mud"
    freeze_path = folder / "freeze_v2.json"
    if not freeze_path.exists():
        pytest.skip("the second freeze has not been made")
    amendment = root / "docs" / "proposal_execution" / "theos2_17sep_recession_and_mud_plan_v1_amendment_1.md"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    points = json.loads((folder / "development_points_v2.json").read_text(encoding="utf-8"))
    assert freeze["amendment"]["sha256"] == hashlib.sha256(amendment.read_bytes()).hexdigest() == points["amendment"]["sha256"]
    assert freeze["supersedes"]["sha256"] == hashlib.sha256((folder / "freeze_v1.json").read_bytes()).hexdigest()
    assert freeze["chosen"] in ("mud_s0", "mud_s3", "mud_s4") and len(freeze["labels"]["by_point_new"]) == 40
    assert sum(points["points_per_stratum"].values()) == 40 and points["seed"] == mud.NEW_DEVELOPMENT_SEED
    assert freeze["official_warning"] is False and freeze["source_timestamp"] and freeze["confidence_class"] == "low"


def test_the_test_points_come_after_the_second_freeze_and_hold_no_answer() -> None:
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    folder = root / "outputs" / "theos2_17sep_mud"
    record_path = folder / "test_points_v1.json"
    if not record_path.exists():
        pytest.skip("the test points have not been drawn")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["freeze"]["sha256"] == hashlib.sha256((folder / "freeze_v2.json").read_bytes()).hexdigest()
    assert record["points"] == sum(mud.TEST_POINTS.values()) == sum(record["points_per_group"].values()) and record["seed"] == mud.TEST_SEED
    assert record["page_outside_git"]["holds_the_answer_of_the_rule"] is False and record["labels"] == list(mud.LABELS)
    template = root / record["page_outside_git"]["template"]["path"]
    assert record["page_outside_git"]["template"]["sha256"] == hashlib.sha256(template.read_bytes()).hexdigest()
    page = template.read_text(encoding="utf-8")
    for label in mud.LABELS:
        assert f'data-label="{label}"' in page, label
    assert "/*POINTS*/[]" in page and "/*PRACTICE*/[]" in page


# ---------------------------------------------------------------------------
# Section 4.4: the score of the test (written and tested before any label file was read)
# ---------------------------------------------------------------------------


def _label_file(labels: dict[str, str], **changes: object) -> dict[str, object]:
    return {"schema": mud.LABEL_SCHEMA, "sample_id": "abc", "labeller": "Somchai", "saved_at_utc": "2026-10-20T00:00:00Z",
            "points": len(labels), "labels": labels, **changes}


def test_a_label_file_must_belong_to_the_draw_and_label_every_point() -> None:
    ids = ["t001", "t002"]
    good = {"t001": "mud", "t002": "bare_cannot_tell"}
    assert mud.check_label_file(_label_file(good), "abc", ids) == good
    # The label page stores each answer with the seconds spent on it.
    as_the_page_saves = {"t001": {"label": "mud", "seconds": 4.2}, "t002": {"label": "bare_cannot_tell", "seconds": 7}}
    assert mud.check_label_file(_label_file(as_the_page_saves), "abc", ids) == good
    assert mud.seconds_of(_label_file(as_the_page_saves)) == [4.2, 7.0]
    with pytest.raises(mud.MudError):
        mud.check_label_file(_label_file({"t001": {"label": "maybe", "seconds": 1}, "t002": {"label": "mud"}}), "abc", ids)
    for bad in (_label_file(good, schema="other"), _label_file(good, sample_id="xyz"), _label_file(good, labeller=" "),
                _label_file({"t001": "mud"}), _label_file({**good, "t999": "mud"}), _label_file({"t001": "mud", "t002": "maybe"}),
                {**_label_file(good), "labels": ["mud", "mud"]}):
        with pytest.raises(mud.MudError):
            mud.check_label_file(bad, "abc", ids)


def test_the_label_two_of_three_gave_and_the_label_a_pair_shares() -> None:
    assert mud.majority_label(["mud", "not_mud", "mud"]) == "mud"
    assert mud.majority_label(["cannot_tell", "cannot_tell", "cannot_tell"]) == "cannot_tell"
    assert mud.majority_label(["mud", "not_mud", "bare_cannot_tell"]) is None
    assert mud.agreed_label(["not_mud", "not_mud"]) == "not_mud" and mud.agreed_label(["mud", "not_mud"]) is None
    with pytest.raises(mud.MudError):
        mud.majority_label(["mud", "mud"])


def test_the_two_shares_of_section_4_4_on_invented_points() -> None:
    points = [{"id": "p1", "group": "mud_inside", "order": "a"}, {"id": "p2", "group": "mud_edge", "order": "a"},
              {"id": "p3", "group": "ground_far", "order": "a"}, {"id": "p4", "group": "unobservable", "order": "a"},
              {"id": "p5", "group": "near_mud", "order": "a"}, {"id": "p6", "group": "mud_inside", "order": "a"},
              {"id": "p7", "group": "mud_edge", "order": "a"}]
    labels = {"p1": "mud", "p2": "not_mud", "p3": "mud", "p4": "mud", "p5": "bare_cannot_tell", "p6": "cannot_tell", "p7": None}
    weights = {("mud_inside", "a"): 10.0, ("mud_edge", "a"): 30.0, ("ground_far", "a"): 100.0, ("unobservable", "a"): 50.0,
               ("near_mud", "a"): 20.0}
    plain = mud.area_shares(points, labels, weights)
    # Of the area the rule calls mud (p1, p2 answered), 10 of 40 is labelled mud; of the area labelled mud (p1, p3, p4),
    # 10 of 160 is called mud by the rule (unobservable counts as the rule not calling it mud).
    assert plain == {"points_used": 4, "rule_mud_points": 2, "labelled_mud_points": 3,
                     "share_of_rule_mud_labelled_mud": 0.25, "share_of_labelled_mud_the_rule_calls_mud": 0.0625}
    bare = mud.area_shares(points, labels, weights, bare_as_mud=True)
    assert bare["points_used"] == 5 and bare["share_of_rule_mud_labelled_mud"] == 0.25
    assert bare["share_of_labelled_mud_the_rule_calls_mud"] == pytest.approx(10 / 180, abs=1e-4)
    assert mud.area_shares(points[2:5], labels, weights)["share_of_rule_mud_labelled_mud"] is None


def test_weights_count_every_drawn_point_so_a_left_out_label_does_not_reweight_its_group() -> None:
    points = [{"id": f"p{i}", "group": "mud_inside", "order": "a"} for i in range(4)] + [{"id": "q", "group": "mud_edge", "order": "a"}]
    weights = mud.point_weights({("mud_inside", "a"): 400, ("mud_edge", "a"): 100}, points)
    assert weights == {("mud_inside", "a"): 100.0, ("mud_edge", "a"): 100.0}
    labels = {"p0": "mud", "p1": "mud", "p2": "cannot_tell", "p3": "not_mud", "q": "not_mud"}
    assert mud.area_shares(points, labels, weights)["share_of_rule_mud_labelled_mud"] == 0.5


def test_the_bootstrap_interval_is_reproducible_and_holds_the_score() -> None:
    rng = np.random.default_rng(5)
    points, labels = [], {}
    for index in range(60):
        group = mud.GROUPS[index % 4]
        points.append({"id": f"t{index:03d}", "group": group, "order": "ab"[index % 2]})
        labels[f"t{index:03d}"] = "mud" if rng.random() < (0.7 if mud.RULE_SAYS[group] == "mud" else 0.2) else "not_mud"
    weights = mud.point_weights({(g, o): 1000 for g in mud.GROUPS for o in "ab"}, points)
    first = mud.bootstrap_share(points, labels, weights, draws=300)
    assert first == mud.bootstrap_share(points, labels, weights, draws=300)
    score = mud.area_shares(points, labels, weights)["share_of_rule_mud_labelled_mud"]
    assert first["low"] <= score <= first["high"] and first["draws_with_a_value"] == 300


def test_the_bar_and_its_two_sentences() -> None:
    assert mud.bar_sentence(0.60) == mud.SENTENCE_BAR_MET and mud.bar_sentence(0.75) == mud.SENTENCE_BAR_MET
    assert mud.bar_sentence(0.5999) == mud.SENTENCE_BAR_MISSED and mud.bar_sentence(None) == mud.SENTENCE_BAR_MISSED
    assert mud.TEST_BAR == 0.60 and set(mud.RULE_SAYS) == set(mud.GROUPS)


def test_the_score_record_follows_the_draw_and_the_bar() -> None:
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    folder = root / "outputs" / "theos2_17sep_mud"
    score_path = folder / "test_score_v1.json"
    if not score_path.exists():
        pytest.skip("the test has not been scored")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    record = json.loads((folder / "test_points_v1.json").read_text(encoding="utf-8"))
    assert score["test_points"]["sha256"] == hashlib.sha256((folder / "test_points_v1.json").read_bytes()).hexdigest()
    assert score["sample_id"] == record["sample_id"] and score["freeze"] == record["freeze"]
    assert len(score["labels_received"]) == 3 and len({item["labeller"].casefold() for item in score["labels_received"]}) == 3
    assert len(score["labels_by_point"]) == record["points"]
    share = score["result"]["labels_of_the_plan"]["share_of_rule_mud_labelled_mud"]
    assert score["bar"]["share"] == share and score["bar"]["met"] == (share is not None and share >= mud.TEST_BAR)
    assert score["sentence"] == mud.bar_sentence(share)
    assert score["official_warning"] is False and score["can_feed_decision_layer"] is False and score["source_timestamp"]
    assert score["confidence_class"] == "low" and score["key_stays_outside_git"] is True


# ---------------------------------------------------------------------------
# Section 4.5: roads, the replay's peak, case SE1 and buildings (written and tested before the run)
# ---------------------------------------------------------------------------


def test_the_four_metre_disk_on_the_two_metre_grid_and_within() -> None:
    footprint = mud.disk(4.0, 2.0)
    assert footprint.shape == (5, 5) and footprint.sum() == 13, "centres within 4 m: the cross of radius 2 and the inner ring"
    assert not footprint[0, 0] and footprint[0, 2] and footprint[1, 1]
    mask = np.zeros((9, 9), dtype=bool)
    mask[4, 4] = True
    near = mud.within(mask, 4.0, 2.0)
    assert near.sum() == 13 and near[4, 6] and near[2, 4] and not near[1, 4] and not near[6, 6]
    assert not mud.within(np.zeros((3, 3), dtype=bool), 4.0, 2.0).any()


def test_a_piece_is_read_every_metre_and_classed_by_the_twenty_metre_rule() -> None:
    xs, ys, each = mud.sample_segment(0.0, 0.0, 30.0, 40.0)
    assert len(xs) == 50 and each == pytest.approx(1.0) and xs[0] == pytest.approx(0.3) and ys[-1] == pytest.approx(39.6)
    xs, _ys, each = mud.sample_segment(0.0, 0.0, 2.5, 0.0)
    assert len(xs) == 3 and each == pytest.approx(2.5 / 3)
    assert mud.piece_class(80.0, 80.0, 20.0) == "shows_mud"
    assert mud.piece_class(80.0, 10.0, 25.0) == "shows_mud", "mud within 4 m counts even where the road itself is hidden"
    assert mud.piece_class(80.0, 79.0, 19.9) == "not_shown"
    assert mud.piece_class(80.0, 39.0, 0.0) == "not_observable" and mud.piece_class(0.0, 0.0, 0.0) == "not_observable"
    assert mud.piece_class(12.0, 12.0, 12.0) == "not_shown", "a piece shorter than 20 m never shows mud"
    assert set(mud.ROAD_SENTENCES) == {"shows_mud", "not_shown", "not_observable"}
    assert "never means the road stayed dry or passable" in mud.ROAD_SENTENCES["not_shown"]


def test_the_replays_own_wet_rule_and_the_height_bins() -> None:
    from floodguard import flood_timeline

    codes = np.array([flood_timeline.CHANNEL_CODE, 1, 69, 70, 100, 254, flood_timeline.NEVER_CODE])
    assert mud.replay_wet(codes, 3.5).tolist() == [True, True, True, False, False, False, False]
    assert flood_timeline.HAND_STEP_M == 0.05
    bins = mud.height_bins(np.array([70, 99, 100, 199, 200, 399, 400, 255]))
    assert bins == {"0_to_5_m": 2, "5_to_10_m": 2, "10_to_20_m": 2, "20_m_or_more": 1, "no_height": 1}


def test_the_section_4_5_record_follows_the_score_and_lists_the_road_sheet_first() -> None:
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    folder = root / "outputs" / "theos2_17sep_mud"
    path = folder / "section_4_5_v1.json"
    if not path.exists():
        pytest.skip("section 4.5 has not run")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["inputs"]["test_score"]["sha256"] == hashlib.sha256((folder / "test_score_v1.json").read_bytes()).hexdigest()
    assert record["inputs"]["freeze"]["sha256"] == hashlib.sha256((folder / "freeze_v2.json").read_bytes()).hexdigest()
    roads = record["roads_4a"]
    assert list(roads)[1] == "the_eight_roads_of_the_road_sheet" and [road["road"] for road in roads["the_eight_roads_of_the_road_sheet"]] == list(range(1, 9))
    assert roads["the_eight_roads_of_the_road_sheet"][0]["osm_way_id"] == "206803562"
    for road in roads["the_eight_roads_of_the_road_sheet"]:
        assert sum(value["pieces"] for value in road["by_class"].values()) == road["pieces_inside_the_products"]
    strata = record["replay_peak_4b"]["strata"]
    assert strata["judged_by_the_river_fit"]["independent"] is False and strata["not_judged_by_the_river_fit"]["independent"] is True
    assert record["buildings_4d"]["no_resident_figure"] is True
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
