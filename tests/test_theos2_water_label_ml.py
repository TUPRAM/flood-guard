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
