"""Learning a water rule from labels, one chip left out at a time: the features, the folds and the rule of the plan."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import theos2_water_label_ml as ml

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "theos2_water_label_ml" / "result_v1.json"
PLAN = ROOT / "docs" / "proposal_execution" / "theos2_water_label_ml_plan_v1.md"


def chip(scale: float, seed: int) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """A chip of 40 by 40 pixels: water (dark in near infrared) on the left half, land on the right, at a brightness scale."""

    generator = np.random.default_rng(seed)
    water = np.zeros((40, 40), dtype=bool)
    water[:, :20] = True
    noise = lambda: generator.normal(1.0, 0.03, size=water.shape)  # noqa: E731
    bands = {
        "blue": scale * 80 * noise(), "green": scale * 90 * noise(),
        "red": scale * np.where(water, 70, 60) * noise(), "nir": scale * np.where(water, 30, 200) * noise(),
    }
    return bands, water


def labelled_points() -> tuple[list[dict], np.ndarray, dict[str, str | None]]:
    points, rows, labels = [], [], {}
    for number, (name, scale) in enumerate((("a", 1.0), ("b", 3.0), ("c", 0.5))):
        bands, water = chip(scale, seed=number)
        generator = np.random.default_rng(100 + number)
        row, column = generator.integers(2, 38, size=30), generator.integers(2, 38, size=30)
        rows.append(ml.features(bands, row, column))
        for index, (r, c) in enumerate(zip(row, column)):
            point_id = f"{name}{index:02d}"
            points.append({"id": point_id, "chip": name, "group": "water_inside" if water[r, c] else "land_inside"})
            labels[point_id] = ml.WATER if water[r, c] else ml.NOT_WATER
    return points, np.vstack(rows), labels


def test_features_are_twelve_and_do_not_depend_on_the_brightness_of_a_scene() -> None:
    bands, _ = chip(1.0, seed=0)
    bright = {name: band * 4.0 for name, band in bands.items()}
    rows, columns = [5, 5, 30], [3, 30, 30]
    first, second = ml.features(bands, rows, columns), ml.features(bright, rows, columns)
    assert first.shape == (3, len(ml.FEATURES)) == (3, 12)
    assert second == pytest.approx(first)
    index = ml.FEATURES.index("red_nir_index")
    assert first[0, index] < 0 < first[1, index]  # Water is darker in near infrared than in red; land is brighter.
    with pytest.raises(ml.LabelLearningError):
        ml.features({name: band for name, band in bands.items() if name != "nir"}, rows, columns)
    with pytest.raises(ml.LabelLearningError):
        ml.features(bands, [40], [0])
    with pytest.raises(ml.LabelLearningError):
        ml.features({**bands, "red": bands["red"][:10]}, rows, columns)


def test_each_point_is_predicted_by_models_that_never_saw_its_chip() -> None:
    points, matrix, labels = labelled_points()
    labels["a00"] = None  # A point without a majority label is predicted but never fitted on.
    result = ml.leave_one_chip_out(points, matrix, labels)
    assert set(result["answers"]) == set(ml.MODELS)
    assert result["folds"]["a"]["points_fitted_on"] == 60 and result["folds"]["b"]["points_fitted_on"] == 59
    for name in ml.MODELS:
        answers = result["answers"][name]
        assert set(answers) == {point["id"] for point in points}
        right = sum(1 for point_id, label in labels.items() if label is not None and answers[point_id] == label)
        assert right >= 85, name  # The synthetic water is easy: every model reads it on a chip it never saw.
    weighted = ml.leave_one_chip_out(points, matrix, labels, {point["id"]: 2.0 for point in points})
    assert weighted["answers"]["one_index"] == result["answers"]["one_index"]  # One weight for all changes nothing.
    assert ml.columns_of("one_index") == [ml.FEATURES.index("red_nir_index")] and len(ml.columns_of("forest")) == 12


def test_bad_inputs_are_refused() -> None:
    points, matrix, labels = labelled_points()
    with pytest.raises(ml.LabelLearningError):
        ml.leave_one_chip_out(points, matrix[:, :5], labels)
    with pytest.raises(ml.LabelLearningError):
        ml.leave_one_chip_out([point for point in points if point["chip"] == "a"], matrix[:30], labels)
    one_label = {point_id: ml.WATER for point_id in labels}
    with pytest.raises(ml.LabelLearningError):
        ml.leave_one_chip_out(points, matrix, one_label)
    with pytest.raises(ml.LabelLearningError):
        ml.make_model("deep_net")


def test_area_weights_and_the_rule_for_better() -> None:
    points = [{"id": "p1", "chip": "a", "group": "g"}, {"id": "p2", "chip": "a", "group": "g"}, {"id": "p3", "chip": "a", "group": "h"}]
    assert ml.area_weights(points, {("a", "g"): 100, ("a", "h"): 7}) == {"p1": 50.0, "p2": 50.0, "p3": 7.0}
    # Four comparisons share the 95% level: 2.50 standard errors, not 1.96.
    assert ml.COMPARISONS == len(ml.MODELS) == 4 and ml.SHARED_LEVEL_Z == pytest.approx(2.4977)
    assert ml.shown_better({"estimate": 0.05, "standard_error": 0.019}) is True
    assert ml.shown_better({"estimate": 0.05, "standard_error": 0.021}) is False  # Above zero at 1.96, not at 2.50.
    assert ml.shown_better({"estimate": -0.02, "standard_error": 0.001}) is False
    assert ml.shown_better({"estimate": None, "standard_error": None}) is False


# --- the committed result ------------------------------------------------------------------------------------------------


def test_the_result_was_made_under_the_committed_plan_and_keeps_its_labels() -> None:
    import hashlib

    result = json.loads(RESULT.read_text(encoding="utf-8"))
    assert result["plan"]["sha256"] == hashlib.sha256(PLAN.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert result["official_warning"] is False and result["can_feed_decision_layer"] is False and result["confidence_class"] == "low"
    assert result["source_timestamp"] and result["limits"] and result["features"] == list(ml.FEATURES)
    assert result["points"]["all"] == 300 and set(result["folds"]) == {"sukhothai", "chip_003", "chip_001"}
    # Every fold fits on the labelled points of the other two chips only.
    assert sum(fold["points_predicted"] for fold in result["folds"].values()) == 300
    decision = result["decision"]
    assert decision["set"] == "three_chips_together" and decision["rule_that_reads_mae_sai"] == "rule v2, unchanged"
    main = result["models_scored"]["area_weighted"]
    for name in ml.MODELS:
        difference = main[name]["three_chips_together"]["minus_rule_v2"]
        assert decision["shown_better_than_rule_v2"][name] == ml.shown_better(difference), name
        for run in result["models_scored"].values():
            assert 0 <= run[name]["three_chips_together"]["share_answered_and_alike"]["estimate"] <= 1
    flat = json.dumps(result)
    assert "Users" not in flat and "Downloads" not in flat, "no machine path"
    assert not any(key in flat for key in ("fpps", "action_class"))


# --- amendment 1: features that need no scaling by chip --------------------------------------------------------------------


def test_the_features_of_amendment_1_are_ratios_that_no_brightness_and_no_mix_of_a_scene_changes() -> None:
    bands, water = chip(1.0, seed=0)
    rows, columns = [5, 5, 30], [3, 30, 30]
    first = ml.features_amendment_1(bands, rows, columns)
    assert first.shape == (3, len(ml.FEATURES_AMENDMENT_1)) == (3, 8)
    assert ml.features_amendment_1({name: band * 4.0 for name, band in bands.items()}, rows, columns) == pytest.approx(first)
    # The fault of the first run: a chip that is nearly all water has another median, and the scaled index moved with it.
    # A ratio of the bands as read does not: the same water pixel has the same value whatever the rest of the chip holds.
    mostly_water = {name: band.copy() for name, band in bands.items()}
    for name in mostly_water:
        mostly_water[name][:, 20:36] = bands[name][:, 0:16]
    index = ml.FEATURES_AMENDMENT_1.index("red_nir_index")
    assert ml.features_amendment_1(mostly_water, [5], [3])[0, index] == pytest.approx(first[0, index])
    scaled = ml.FEATURES.index("red_nir_index")
    assert ml.features(mostly_water, [5], [3])[0, scaled] != pytest.approx(ml.features(bands, [5], [3])[0, scaled], abs=0.05)
    with pytest.raises(ml.LabelLearningError):
        ml.features_amendment_1(bands, [40], [0])


def test_the_second_run_uses_its_own_columns_and_a_higher_bar() -> None:
    assert ml.columns_of("one_index", ml.FEATURES_AMENDMENT_1) == [1] and len(ml.columns_of("forest", ml.FEATURES_AMENDMENT_1)) == 8
    assert ml.SHARED_LEVEL_Z_AMENDMENT_1 == pytest.approx(2.7344) and ml.SHARED_LEVEL_Z_AMENDMENT_1 > ml.SHARED_LEVEL_Z
    difference = {"estimate": 0.05, "standard_error": 0.019}
    assert ml.shown_better(difference) is True and ml.shown_better(difference, ml.SHARED_LEVEL_Z_AMENDMENT_1) is False
    points, _, labels = labelled_points()
    rows = []
    for number, (name, scale) in enumerate((("a", 1.0), ("b", 3.0), ("c", 0.5))):
        bands, _ = chip(scale, seed=number)
        generator = np.random.default_rng(100 + number)
        row, column = generator.integers(2, 38, size=30), generator.integers(2, 38, size=30)
        rows.append(ml.features_amendment_1(bands, row, column))
    result = ml.leave_one_chip_out(points, np.vstack(rows), labels, None, ml.FEATURES_AMENDMENT_1)
    for name in ml.MODELS:
        assert sum(1 for point_id, label in labels.items() if result["answers"][name][point_id] == label) >= 85, name


# --- the committed result of the second run -------------------------------------------------------------------------------


def test_the_second_result_names_the_first_and_keeps_the_stricter_bar() -> None:
    import hashlib

    first_bytes = RESULT.read_bytes()
    second = json.loads((RESULT.parent / "result_v2.json").read_text(encoding="utf-8"))
    amendment = ROOT / "docs" / "proposal_execution" / "theos2_water_label_ml_plan_v1_amendment_1.md"
    assert second["first_run"]["sha256"] == hashlib.sha256(first_bytes.replace(b"\r\n", b"\n")).hexdigest()
    assert second["amendment"]["sha256"] == hashlib.sha256(amendment.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert second["features"] == list(ml.FEATURES_AMENDMENT_1) and second["features_scaled_by_chip"] is False
    assert "second run" in second["run"] and "2.7344" in second["decision"]["rule"] and "8 comparisons" in second["decision"]["rule"]
    main = second["models_scored"]["area_weighted"]
    for name in ml.MODELS:
        difference = main[name]["three_chips_together"]["minus_rule_v2"]
        assert second["decision"]["shown_better_than_rule_v2"][name] == ml.shown_better(difference, ml.SHARED_LEVEL_Z_AMENDMENT_1), name
    # What the account says: no model is called better; the one learned index is close to rule v2; the others are worse.
    assert not any(second["decision"]["shown_better_than_rule_v2"].values())
    assert abs(main["one_index"]["three_chips_together"]["minus_rule_v2"]["estimate"]) < 0.05
    for name in ("logistic", "forest", "boosting"):
        assert main[name]["three_chips_together"]["minus_rule_v2"]["interval_95"][1] < 0, name
    # Rule v2 is within the range of a team member against the other two.
    people = [entry["three_chips_together"]["share_answered_and_alike"]["estimate"] for entry in second["each_team_member_against_the_other_two"].values()]
    rule_v2 = second["rules_on_the_same_points"]["rule_v2"]["three_chips_together"]["share_answered_and_alike"]["estimate"]
    assert min(people) - 0.01 <= rule_v2 <= max(people) + 0.01
    assert second["decision"]["rule_that_reads_mae_sai"] == "rule v2, unchanged" and second["official_warning"] is False
