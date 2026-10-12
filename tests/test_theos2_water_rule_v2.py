"""The second THEOS-2 water rule: the rule itself, figures for any map, and the committed freeze."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from floodguard import theos2_water_labels as wl
from floodguard import theos2_water_rule_v2 as v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/theos2_water_rule_v2"
SHA = re.compile(r"^[0-9a-f]{64}$")


def scene() -> tuple[np.ndarray, ...]:
    """A 200 by 200 image: plants, muddy and clear water, a wide cloud, a small roof, bright muddy water."""

    red = np.full((200, 200), 300.0)
    green = np.full((200, 200), 320.0)
    blue = np.full((200, 200), 330.0)
    nir = np.full((200, 200), 800.0)            # plants: near infrared far above red

    def paint(rows: slice, columns: slice, values: tuple[float, float, float, float]) -> None:
        for band, value in zip((red, green, blue, nir), values):
            band[rows, columns] = value

    paint(slice(10, 40), slice(10, 40), (700, 480, 440, 500))        # muddy water
    paint(slice(10, 40), slice(60, 90), (330, 320, 400, 260))        # clear, dark water
    paint(slice(80, 150), slice(20, 90), (800, 800, 800, 800))       # cloud, 70 px wide
    paint(slice(20, 30), slice(150, 160), (800, 800, 800, 800))      # a white roof, 10 px wide
    paint(slice(100, 180), slice(110, 190), (900, 700, 600, 650))    # bright muddy water, 80 px wide
    return red, green, blue, nir


def test_the_index_is_below_zero_where_near_infrared_is_below_red() -> None:
    index = v2.red_nir_index(np.array([[700.0, 300.0, 0.0]]), np.array([[500.0, 800.0, 0.0]]))
    assert index[0, 0] == pytest.approx(-200 / 1200) and index[0, 1] == pytest.approx(500 / 1100)
    assert np.isnan(index[0, 2])
    with pytest.raises(v2.WaterRuleError):
        v2.red_nir_index(np.zeros((2, 2)), np.zeros((3, 2)))


def test_rule_v2_on_a_painted_scene() -> None:
    red, green, blue, nir = scene()
    water, summary = v2.water_v2(red, green, blue, nir, nir > 0)
    assert water.dtype == np.uint8
    assert water[25, 25] == v2.WATER_YES and water[25, 75] == v2.WATER_YES      # muddy and clear water
    assert water[60, 180] == v2.WATER_NO                                        # plants
    assert water[115, 55] == v2.WATER_UNOBSERVABLE                              # the cloud
    assert water[25, 155] == v2.WATER_NO                                        # a roof too narrow to be cloud: answered
    assert water[140, 150] == v2.WATER_YES                                      # bright muddy water stays water
    assert summary["water_pixels"] == int((water == v2.WATER_YES).sum())
    assert summary["water_pixels_inside_bright_objects"] >= 80 * 80
    assert summary["unobservable_cloud_pixels"] >= 70 * 70
    assert summary["observable_pixels"] + summary["unobservable_cloud_pixels"] == summary["valid_pixels"] == 200 * 200
    assert summary["configuration"] == {
        "index_water_max": -0.01, "index_cloud_min": -0.04, "bright_brightness_min": 520.0, "bright_nir_min": 560.0,
        "cloud_min_width_px": 40, "cloud_margin_px": 10,
    }


def test_rule_v2_finds_no_water_on_a_scene_of_plants_and_soil() -> None:
    # The failure of rule v1: an image without water must come back without water.
    rng = np.random.default_rng(3)
    red = rng.uniform(220, 450, (120, 120))
    nir = red + rng.uniform(60, 600, (120, 120))
    water, summary = v2.water_v2(red, red, red + 40, nir, nir > 0)
    assert summary["water_pixels"] == 0 and not (water == v2.WATER_UNOBSERVABLE).any()


def test_rule_v2_refuses_arrays_and_limits_that_do_not_fit() -> None:
    red, green, blue, nir = scene()
    with pytest.raises(v2.WaterRuleError, match="one two-dimensional shape"):
        v2.water_v2(red, green, blue, nir[:-1], nir > 0)
    with pytest.raises(v2.WaterRuleError, match="index_cloud_min"):
        v2.water_v2(red, green, blue, nir, nir > 0, v2.WaterRuleV2(index_water_max=-0.05, index_cloud_min=-0.01))
    invalid = nir > 0
    invalid[0:5, :] = False
    assert (v2.water_v2(red, green, blue, nir, invalid)[0][0:5, :] == v2.WATER_UNOBSERVABLE).all()


def test_pixels_near_a_test_point_are_kept_out_of_the_development_draw() -> None:
    free = v2.away_from((50, 50), [(0, 0), (25, 25)], 10)
    assert not free[0:11, 0:11].any() and not free[15:36, 15:36].any()
    assert free[11, 11] and free[14, 25] and free[36, 25] and free[49, 49]
    assert int((~free).sum()) == 11 * 11 + 21 * 21
    assert v2.DEVELOPMENT_SEED != wl.SEED
    assert [sum(points) for points in v2.DEVELOPMENT_POINTS.values()] == [96, 96, 48]


def designed() -> tuple[list[dict[str, str]], dict[str, str | None], dict[tuple[str, str], int]]:
    labels = {
        "water_inside": [wl.WATER] * 4,
        "water_edge": [wl.WATER, wl.WATER, wl.NOT_WATER, wl.NOT_WATER],
        "dropped_small_object": [wl.WATER, wl.NOT_WATER, wl.NOT_WATER, None],
        "land_edge": [wl.WATER, wl.NOT_WATER, wl.NOT_WATER, wl.NOT_WATER],
        "land_inside": [wl.NOT_WATER] * 4,
        "unobservable": [wl.WATER, wl.NOT_WATER, None, None],
    }
    points, scoring = [], {}
    for group, given in labels.items():
        for index, label in enumerate(given):
            points.append({"id": f"{group}_{index}", "chip": "one", "group": group})
            scoring[f"{group}_{index}"] = label
    sizes = {("one", "water_inside"): 600, ("one", "water_edge"): 200, ("one", "dropped_small_object"): 30,
             ("one", "land_edge"): 200, ("one", "land_inside"): 1000, ("one", "unobservable"): 100}
    return points, scoring, sizes


def test_figures_for_any_map_agree_with_the_figures_of_rule_v1() -> None:
    points, scoring, sizes = designed()
    answers = wl.answers_of_rule_v1(points)
    assert answers["water_edge_0"] == wl.WATER and answers["land_inside_0"] == wl.NOT_WATER
    assert answers["unobservable_0"] == wl.UNOBSERVABLE
    old = wl.figures(points, scoring, sizes, ("one",))
    new = wl.figures_of_a_map(points, scoring, answers, sizes, ("one",))
    for old_name, new_name in (
        ("a_share_of_rule_water_labelled_water", "a_share_of_map_water_labelled_water"),
        ("b_share_of_labelled_water_the_rule_finds", "b_share_of_labelled_water_the_map_finds"),
        ("c_share_of_answered_area_where_both_say_the_same", "c_share_of_answered_area_where_both_say_the_same"),
    ):
        assert new[new_name]["estimate"] == old[old_name]["estimate"]
        assert new[new_name]["standard_error"] == old[old_name]["standard_error"]
    assert new["d_water_share_of_answered_area"]["by_the_labels"]["estimate"] == old["d_water_share_of_answered_area"]["by_the_labels"]["estimate"]
    # Alike on 1870 of the 2030 answered pixels; the 100 set-aside pixels count as not alike.
    assert new["share_answered_and_alike"]["estimate"] == round(1870 / 2130, 4)
    assert new["share_of_labelled_area_the_map_answers"]["estimate"] == round(2030 / 2130, 4)


def test_a_map_that_answers_the_set_aside_area_is_credited_for_it() -> None:
    points, scoring, sizes = designed()
    first = wl.answers_of_rule_v1(points)
    second = {**first, "unobservable_0": wl.WATER, "unobservable_1": wl.NOT_WATER, "land_edge_0": wl.WATER}
    better = wl.figures_of_a_map(points, scoring, second, sizes, ("one",))
    # 100 more pixels alike in the set-aside group and 50 more at the land edge.
    assert better["share_answered_and_alike"]["estimate"] == round((1870 + 100 + 50) / 2130, 4)
    difference = wl.difference_of_two_maps(points, scoring, first, second, sizes, ("one",))
    assert difference["estimate"] == round(150 / 2130, 4)
    low, high = difference["interval_95"]
    assert low < difference["estimate"] < high
    same = wl.difference_of_two_maps(points, scoring, first, first, sizes, ("one",))
    assert same["estimate"] == 0.0 and same["interval_95"] == [0.0, 0.0]
    worse = wl.difference_of_two_maps(points, scoring, second, first, sizes, ("one",))
    assert worse["estimate"] == -difference["estimate"] and worse["interval_95"][0] < 0


# ---------------------------------------------------------------------------
# The committed records
# ---------------------------------------------------------------------------

FREEZE = json.loads((OUT / "freeze_v1.json").read_text(encoding="utf-8"))
POINTS = json.loads((OUT / "development_points_v1.json").read_text(encoding="utf-8"))
LABELS = json.loads((OUT / "development_labels_v1.json").read_text(encoding="utf-8"))


def test_the_freeze_carries_the_fields_of_every_output() -> None:
    assert FREEZE["schema"] == "floodguard.theos2_water_rule_v2.freeze.v1"
    assert FREEZE["source_timestamp"] and FREEZE["generated_at_utc"].endswith("Z")
    assert FREEZE["confidence_class"] == "low" and FREEZE["confidence_basis"]
    assert FREEZE["operational_status"] == "non_operational"
    assert FREEZE["official_warning"] is False and FREEZE["can_feed_decision_layer"] is False
    assert (ROOT / FREEZE["plan"]["path"]).exists() and SHA.match(FREEZE["plan"]["sha256"])
    assert FREEZE["limits"] and FREEZE["test_labels_read_before_this_freeze"] is False


def test_the_development_points_are_apart_from_the_test_points_and_labelled_by_the_agent() -> None:
    assert POINTS["seed"] == v2.DEVELOPMENT_SEED and POINTS["kept_away_from_test_points_m"] == 20.0
    assert len(POINTS["points"]) == 240 and len({point["id"] for point in POINTS["points"]}) == 240
    assert set(LABELS["labels"]) == {point["id"] for point in POINTS["points"]}
    assert set(LABELS["labels"].values()) <= set(wl.LABELS)
    assert "AI model" in LABELS["labeller"] and "not a reference" in LABELS["what_this_is"]
    assert sum(LABELS["counts"].values()) == 240 and FREEZE["development_labels"]["counts"] == LABELS["counts"]
    assert set(LABELS["cannot_tell_because"]) == {point for point, label in LABELS["labels"].items() if label == wl.CANNOT_TELL}
    for chip in wl.CHIPS:
        assert POINTS["chips"][chip]["points"] == sum(v2.DEVELOPMENT_POINTS[chip])


def test_the_choice_follows_the_rule_of_the_plan() -> None:
    candidates = FREEZE["candidates"]
    assert candidates[0]["name"] == "rule_v1" and len({entry["name"] for entry in candidates}) == len(candidates)
    best = max(candidates, key=lambda entry: entry["mean"])
    near = [entry for entry in candidates if best["mean"] - entry["mean"] <= 0.01]
    chosen = min(near, key=lambda entry: (entry["fitted_parameters"], -entry["mean"]))
    choice = FREEZE["choice"]
    assert choice["chosen"] == chosen["name"] == "index_at_or_below_a_fitted_limit"
    assert choice["mean_of_the_chosen_with_one_chip_left_out"] - choice["mean_of_rule_v1"] > 0.01
    for entry in candidates:
        assert set(entry["by_chip"]) == set(wl.CHIPS)
        assert entry["mean"] == round(sum(entry["by_chip"].values()) / 3, 4)
    limits = next(entry for entry in candidates if entry["name"] == chosen["name"])["limits_on_all_three_chips"]
    assert max(limits, key=lambda limit: limits[limit]) == str(choice["limit_fitted_on_all_three_chips"])


def test_the_frozen_rule_is_the_rule_in_the_code() -> None:
    frozen = FREEZE["frozen_rule"]
    config = v2.WaterRuleV2()
    assert frozen["code"] == "floodguard.theos2_water_rule_v2.water_v2"
    assert frozen["configuration"]["index_water_max"] == config.index_water_max == FREEZE["choice"]["limit_fitted_on_all_three_chips"]
    assert frozen["configuration"]["index_cloud_min"] == config.index_cloud_min
    assert frozen["configuration"]["cloud_min_width_px"] == config.cloud_min_width_px
    for chip in wl.CHIPS:
        record = frozen["chips"][chip]
        assert SHA.match(record["raster_outside_git"]["sha256"])
        assert record["rule_v2"]["water_pixels"] / record["rule_v2"]["pixels"] == pytest.approx(
            record["water_share_of_the_chip"]["rule_v2"], abs=1e-4)
    # The chip without a flood: rule v1 called a fifth of it water, the frozen rule next to nothing.
    shares = frozen["chips"]["chip_001"]["water_share_of_the_chip"]
    assert shares["rule_v1"] > 0.2 and shares["rule_v2"] < 0.001
    assert not list(OUT.glob("*.tif")) and not list(OUT.glob("*.npz"))


def test_the_cloud_rule_is_said_to_be_outside_the_score() -> None:
    cloud = FREEZE["cloud"]
    assert "addition to the plan" in cloud["why_outside_the_score"]
    names = [entry["name"] for entry in cloud["variants"]]
    assert cloud["frozen"] in names and names[0] == "no_cloud_rule"
    frozen = next(entry for entry in cloud["variants"] if entry["name"] == cloud["frozen"])
    none = cloud["variants"][0]
    assert frozen["mean"] >= none["mean"] and frozen["cloud_points_set_aside"] > none["cloud_points_set_aside"]
    assert cloud["cloud_points_set_aside_by_the_frozen_rule"] == frozen["cloud_points_set_aside"]
    assert frozen["cloud_points"] == sum(1 for kind in LABELS["cannot_tell_because"].values() if kind == "cloud")
