"""The label check of the THEOS-2 water rule: groups, draw, scoring label and the stratified figures."""

from __future__ import annotations

import math

import numpy as np
import pytest

from floodguard import theos2_cross_check as cc
from floodguard import theos2_water_labels as wl


def small_raster() -> tuple[np.ndarray, np.ndarray]:
    """A 40 by 40 raster: a block of water, a dropped object, an unobservable corner."""

    water = np.zeros((40, 40), dtype="uint8")
    above = np.zeros((40, 40), dtype=bool)
    water[5:25, 5:25] = cc.WATER_YES
    above[5:25, 5:25] = True
    above[32:34, 32:34] = True  # above the threshold and not kept: a dropped small object
    water[0:4, 30:40] = cc.WATER_UNOBSERVABLE
    return water, above


def test_groups_cover_every_pixel_and_follow_the_plan() -> None:
    water, above = small_raster()
    groups = wl.groups_of(water, above)
    sizes = wl.group_sizes(groups)
    assert sum(sizes.values()) == water.size
    # Water: a block of 20 by 20; the three outer rings are within three pixels of land.
    assert sizes["water_inside"] == 14 * 14
    assert sizes["water_edge"] == 20 * 20 - 14 * 14
    assert sizes["dropped_small_object"] == 4
    assert sizes["unobservable"] == 40
    # Land within three pixels of the block: a ring of width three around it.
    assert sizes["land_edge"] == 26 * 26 - 20 * 20
    assert sizes["land_inside"] == water.size - sum(sizes[name] for name in wl.GROUPS if name != "land_inside")
    name = lambda row, column: wl.GROUPS[groups[row, column]]  # noqa: E731
    assert name(15, 15) == "water_inside" and name(5, 5) == "water_edge"
    assert name(3, 15) == "land_edge" and name(38, 2) == "land_inside"
    assert name(32, 32) == "dropped_small_object" and name(0, 39) == "unobservable"


def test_groups_refuse_a_mask_of_another_raster() -> None:
    water, above = small_raster()
    above[10, 10] = False
    with pytest.raises(wl.LabelCheckError, match="below the threshold"):
        wl.groups_of(water, above)
    with pytest.raises(wl.LabelCheckError, match="one two-dimensional shape"):
        wl.groups_of(water, above[:-1])


def test_planned_points_add_up_and_a_short_group_gives_its_points_away() -> None:
    assert [sum(points) for points in wl.PLANNED_POINTS.values()] == [120, 120, 60]
    assert all(len(points) == len(wl.GROUPS) for points in wl.PLANNED_POINTS.values())
    sizes = {"water_inside": 500, "water_edge": 500, "dropped_small_object": 500, "land_edge": 500, "land_inside": 500,
             "unobservable": 0}
    points = wl.points_per_group(sizes, wl.PLANNED_POINTS["chip_001"])
    assert points["unobservable"] == 0 and points["land_inside"] == 15 + 7 and sum(points.values()) == 60
    with pytest.raises(wl.LabelCheckError, match="too few pixels"):
        wl.points_per_group({**sizes, "land_inside": 3}, wl.PLANNED_POINTS["chip_001"])


def test_the_draw_is_inside_the_groups_without_repeats_and_repeats_itself() -> None:
    water, above = small_raster()
    groups = wl.groups_of(water, above)
    points = {"water_inside": 10, "water_edge": 10, "dropped_small_object": 4, "land_edge": 10, "land_inside": 10, "unobservable": 5}
    first = wl.draw(groups, points, seed=7, chip_number=0)
    assert first == wl.draw(groups, points, seed=7, chip_number=0)
    assert first != wl.draw(groups, points, seed=7, chip_number=1)
    assert len(first) == sum(points.values())
    assert len({(point["row"], point["column"]) for point in first}) == len(first)
    for point in first:
        assert wl.GROUPS[groups[point["row"], point["column"]]] == point["group"]
    with pytest.raises(wl.LabelCheckError, match="fewer pixels"):
        wl.draw(groups, {**points, "dropped_small_object": 5}, seed=7, chip_number=0)

    practice = wl.draw_practice(groups, [(point["row"], point["column"]) for point in first], seed=7)
    taken = {(point["row"], point["column"]) for point in first}
    # Every pixel of the dropped object was drawn, so that group has no practice point left.
    assert [point["group"] for point in practice] == [name for name in wl.GROUPS if name != "dropped_small_object"]
    assert all((point["row"], point["column"]) not in taken for point in practice)


def test_one_order_names_the_points_without_telling_the_group() -> None:
    points = [{"group": name, "row": index, "column": 0} for index, name in enumerate(wl.GROUPS * 5)]
    ordered = wl.in_one_order(points, seed=wl.SEED)
    assert [point["id"] for point in ordered] == [f"p{number:03d}" for number in range(1, 31)]
    assert sorted(point["row"] for point in ordered) == list(range(30))
    assert [point["group"] for point in ordered] != [point["group"] for point in points]
    assert ordered == wl.in_one_order(points, seed=wl.SEED)


def label_file(labels: dict[str, str], **changes: object) -> dict[str, object]:
    return {"sample_id": "abc", "labeller": "Ana", "labels": {point: {"label": label, "seconds": 5.0} for point, label in labels.items()},
            **changes}


def test_a_label_file_is_checked_against_the_draw() -> None:
    ids = ["p001", "p002", "p003"]
    labels = {"p001": wl.WATER, "p002": wl.NOT_WATER, "p003": wl.CANNOT_TELL}
    assert wl.check_labels(label_file(labels), sample_id="abc", point_ids=ids) == labels
    with pytest.raises(wl.LabelCheckError, match="another draw"):
        wl.check_labels(label_file(labels), sample_id="other", point_ids=ids)
    with pytest.raises(wl.LabelCheckError, match="names no labeller"):
        wl.check_labels(label_file(labels, labeller=" "), sample_id="abc", point_ids=ids)
    with pytest.raises(wl.LabelCheckError, match="misses 1 points and holds 0"):
        wl.check_labels(label_file({"p001": wl.WATER, "p002": wl.WATER}), sample_id="abc", point_ids=ids)
    with pytest.raises(wl.LabelCheckError, match="misses 0 points and holds 1"):
        wl.check_labels(label_file({**labels, "p999": wl.WATER}), sample_id="abc", point_ids=ids)
    with pytest.raises(wl.LabelCheckError, match="not one of the three"):
        wl.check_labels(label_file({**labels, "p003": "maybe"}), sample_id="abc", point_ids=ids)


def test_the_scoring_label_is_the_one_both_gave() -> None:
    first = {"a": wl.WATER, "b": wl.WATER, "c": wl.NOT_WATER, "d": wl.CANNOT_TELL, "e": wl.CANNOT_TELL}
    second = {"a": wl.WATER, "b": wl.NOT_WATER, "c": wl.NOT_WATER, "d": wl.CANNOT_TELL, "e": wl.WATER}
    assert wl.agreed(first, second) == {"a": wl.WATER, "b": None, "c": wl.NOT_WATER, "d": None, "e": None}
    assert wl.alone(first) == {"a": wl.WATER, "b": wl.WATER, "c": wl.NOT_WATER, "d": None, "e": None}
    with pytest.raises(wl.LabelCheckError):
        wl.agreed(first, {"a": wl.WATER})


def test_agreement_between_two_labellers() -> None:
    # 20 + 15 alike of 50; kappa from the margins: chance = (25*30 + 25*20) / 2500 = 0.5; kappa = (0.7 - 0.5) / 0.5.
    first = {f"p{i}": (wl.WATER if i < 25 else wl.NOT_WATER) for i in range(50)}
    second = {f"p{i}": (wl.WATER if i < 20 or i >= 40 else wl.NOT_WATER) for i in range(50)}
    result = wl.between_labellers(first, second)
    assert result["points"] == 50 and result["share_same_label"] == 0.7
    assert result["share_same_by_chance"] == 0.5 and result["cohens_kappa"] == 0.4
    assert result["table_first_by_second"][wl.WATER] == {wl.WATER: 20, wl.NOT_WATER: 5, wl.CANNOT_TELL: 0}
    alike = wl.between_labellers(first, first)
    assert alike["share_same_label"] == 1.0 and alike["cohens_kappa"] == 1.0
    one_label = {point: wl.WATER for point in first}
    assert wl.between_labellers(one_label, one_label)["cohens_kappa"] is None


def test_stratified_ratio_against_a_sum_by_hand() -> None:
    # Two strata. Stratum 1: 100 pixels, 4 points, y = 1,1,1,0 and x = 1 for all. Stratum 2: 300 pixels, 5 points,
    # y = 0,0,0,0,1 and x = 1 for all. Ratio = (100 * 0.75 + 300 * 0.2) / 400.
    strata = [wl.Stratum(100, (1, 1, 1, 0), (1, 1, 1, 1)), wl.Stratum(300, (0, 0, 0, 0, 1), (1, 1, 1, 1, 1))]
    result = wl.stratified_ratio(strata)
    assert result["estimate"] == round((75 + 60) / 400, 4) and result["points"] == 9
    variance = (100**2 * (1 - 4 / 100) * 0.25 / 4 + 300**2 * (1 - 5 / 300) * 0.2 / 5) / 400**2
    assert result["standard_error"] == round(math.sqrt(variance), 4)
    low, high = result["interval_95"]
    assert low < result["estimate"] < high and low >= 0.0 and high <= 1.0


def test_stratified_ratio_with_a_denominator_that_varies() -> None:
    # y = rule water and label water, x = label water: the share of labelled water that the rule finds.
    # Water stratum (N 200): labels 1,1,1,0 -> y = 1,1,1,0; x = 1,1,1,0. Land stratum (N 800): labels 0,0,0,1 -> y = 0; x = 0,0,0,1.
    strata = [wl.Stratum(200, (1, 1, 1, 0), (1, 1, 1, 0)), wl.Stratum(800, (0, 0, 0, 0), (0, 0, 0, 1))]
    result = wl.stratified_ratio(strata)
    ratio = (200 * 0.75) / (200 * 0.75 + 800 * 0.25)
    assert result["estimate"] == round(ratio, 4)
    s2 = 0.25  # the sample variance of 1,1,1,0 and of 0,0,0,1
    first = 200**2 * (1 - 4 / 200) * (s2 + ratio**2 * s2 - 2 * ratio * s2) / 4
    second = 800**2 * (1 - 4 / 800) * (ratio**2 * s2) / 4
    assert result["standard_error"] == round(math.sqrt(first + second) / (200 * 0.75 + 800 * 0.25), 4)


def test_stratified_ratio_reports_what_it_cannot_use() -> None:
    result = wl.stratified_ratio([wl.Stratum(50, (), ()), wl.Stratum(50, (1,), (1,)), wl.Stratum(0, (), ())])
    assert result["estimate"] == 1.0 and result["strata_without_a_scored_point"] == 1 and result["strata_with_one_point"] == 1
    assert wl.stratified_ratio([wl.Stratum(50, (0, 0), (0, 0))])["estimate"] is None
    with pytest.raises(wl.LabelCheckError, match="more points than pixels"):
        wl.stratified_ratio([wl.Stratum(1, (1, 0), (1, 1))])


def test_wilson_interval() -> None:
    result = wl.wilson(8, 10)
    assert result["share"] == 0.8 and result["interval_95"] == [0.4902, 0.9433]
    assert wl.wilson(0, 0)["share"] is None
    assert wl.wilson(0, 15)["interval_95"][0] == 0.0 and wl.wilson(15, 15)["interval_95"][1] == 1.0
    with pytest.raises(wl.LabelCheckError):
        wl.wilson(3, 2)


def designed_points() -> tuple[list[dict[str, str]], dict[str, str | None], dict[tuple[str, str], int]]:
    """One chip with four points in each group and labels chosen so that every figure can be worked out by hand."""

    water_labels = {
        "water_inside": [wl.WATER] * 4,
        "water_edge": [wl.WATER, wl.WATER, wl.NOT_WATER, wl.NOT_WATER],
        "dropped_small_object": [wl.WATER, wl.NOT_WATER, wl.NOT_WATER, None],
        "land_edge": [wl.WATER, wl.NOT_WATER, wl.NOT_WATER, wl.NOT_WATER],
        "land_inside": [wl.NOT_WATER] * 4,
        "unobservable": [wl.WATER, wl.NOT_WATER, None, None],
    }
    points, scoring = [], {}
    for group, labels in water_labels.items():
        for index, label in enumerate(labels):
            name = f"{group}_{index}"
            points.append({"id": name, "chip": "one", "group": group})
            scoring[name] = label
    sizes = {("one", "water_inside"): 600, ("one", "water_edge"): 200, ("one", "dropped_small_object"): 30,
             ("one", "land_edge"): 200, ("one", "land_inside"): 1000, ("one", "unobservable"): 100}
    return points, scoring, sizes


def test_figures_of_the_plan_on_a_case_worked_by_hand() -> None:
    points, scoring, sizes = designed_points()
    result = wl.figures(points, scoring, sizes, ("one",))
    assert result["points"] == 24 and result["points_scored"] == 21
    assert result["points_left_out_by_group"]["dropped_small_object"] == 1 and result["points_left_out_by_group"]["unobservable"] == 2
    # a: (600 * 1 + 200 * 0.5) / 800
    assert result["a_share_of_rule_water_labelled_water"]["estimate"] == 0.875
    # b: rule water that is water = 700; water the rule misses = 30 * 1/3 + 200 * 0.25 = 60
    assert result["b_share_of_labelled_water_the_rule_finds"]["estimate"] == round(700 / 760, 4)
    # c: same answer on 600 + 100 (water) + 20 (dropped) + 150 (land edge) + 1000 of 2030 pixels
    assert result["c_share_of_answered_area_where_both_say_the_same"]["estimate"] == round(1870 / 2030, 4)
    assert result["d_water_share_of_answered_area"]["by_the_rule"] == round(800 / 2030, 4)
    assert result["d_water_share_of_answered_area"]["by_the_labels"]["estimate"] == round(760 / 2030, 4)
    assert result["e_dropped_small_objects"]["labelled_water"]["count"] == 1
    assert result["e_dropped_small_objects"]["labelled_water"]["of"] == 3 and result["e_dropped_small_objects"]["left_out"] == 1
    assert result["f_unobservable"]["labelled_water"]["of"] == 2
    edges = result["g_edges"]
    assert edges["a_without_the_edge_groups"]["estimate"] == 1.0
    assert edges["b_without_the_edge_groups"]["estimate"] == round(600 / 610, 4)
    # At the edges the two differ on 100 of the 200 water-edge pixels and 50 of the 200 land-edge pixels.
    assert edges["share_of_edge_area_where_rule_and_labels_differ"]["estimate"] == round(150 / 400, 4)
    low, high = edges["share_of_edge_area_where_rule_and_labels_differ"]["interval_95"]
    assert low <= 0.375 <= high


def test_figures_keep_chips_apart_and_count_labels() -> None:
    points, scoring, sizes = designed_points()
    other = [{**point, "id": f"x_{point['id']}", "chip": "two"} for point in points]
    scoring.update({point["id"]: wl.NOT_WATER for point in other})
    sizes.update({("two", group): size for (_chip, group), size in list(sizes.items())})
    alone = wl.figures(points + other, scoring, sizes, ("one",))
    assert alone["points"] == 24 and alone["a_share_of_rule_water_labelled_water"]["estimate"] == 0.875
    both = wl.figures(points + other, scoring, sizes, ("one", "two"))
    assert both["points"] == 48 and both["a_share_of_rule_water_labelled_water"]["estimate"] == 0.4375
    labels = {point["id"]: (scoring[point["id"]] or wl.CANNOT_TELL) for point in points + other}
    counts = wl.label_counts(points + other, labels, ("one",))
    assert counts["unobservable"] == {wl.WATER: 1, wl.NOT_WATER: 1, wl.CANNOT_TELL: 2}
    assert sum(sum(row.values()) for row in counts.values()) == 24


def test_the_scoring_label_of_three_labellers() -> None:
    first = {"a": wl.WATER, "b": wl.WATER, "c": wl.NOT_WATER, "d": wl.CANNOT_TELL, "e": wl.WATER, "f": wl.CANNOT_TELL}
    second = {"a": wl.WATER, "b": wl.NOT_WATER, "c": wl.NOT_WATER, "d": wl.CANNOT_TELL, "e": wl.NOT_WATER, "f": wl.WATER}
    third = {"a": wl.WATER, "b": wl.WATER, "c": wl.CANNOT_TELL, "d": wl.WATER, "e": wl.CANNOT_TELL, "f": wl.NOT_WATER}
    assert wl.majority([first, second, third]) == {"a": wl.WATER, "b": wl.WATER, "c": wl.NOT_WATER, "d": None, "e": None, "f": None}
    assert wl.unanimous([first, second, third]) == {"a": wl.WATER, "b": None, "c": None, "d": None, "e": None, "f": None}
    # With two labellers the majority is the label both gave.
    assert wl.majority([first, second]) == wl.agreed(first, second) == wl.unanimous([first, second])
    with pytest.raises(wl.LabelCheckError):
        wl.majority([first, {"a": wl.WATER}])
    with pytest.raises(wl.LabelCheckError):
        wl.unanimous([])
