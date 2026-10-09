"""Tests of the second round of radar detection: the pure parts on invented scenes, and the committed records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import radar_detection as rd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "radar_detection_improvement"
FREEZE = OUTPUTS / "freeze_v1.json"
REFERENCE = OUTPUTS / "held_out_reference_v1.json"
RESULT = OUTPUTS / "held_out_test_v1.json"
PLAN = "docs/proposal_execution/radar_detection_improvement_plan_v1.md"


def test_baseline_features_measure_the_image_after_against_the_dry_season() -> None:
    rng = np.random.default_rng(4)
    after = np.abs(rng.normal(0.1, 0.005, (2, 14, 14)))
    after[:, 5:10, 5:10] *= 0.1  # a block 10 dB darker than the dry season
    dry = np.full((2, 14, 14), -10.0)
    spread = np.full((2, 14, 14), 0.7)
    features = rd.baseline_features(after, dry, spread, np.full((14, 14), 2.0), np.full((14, 14), 40))
    assert tuple(features) == rd.FEATURES_BASELINE
    assert features["vh_anomaly_db"][7, 7] == pytest.approx(-10.0, abs=0.3) and abs(features["vh_anomaly_db"][1, 1]) < 0.3
    assert features["vh_dry_db"][7, 7] == pytest.approx(-10.0) and features["vh_dry_spread_db"][7, 7] == pytest.approx(0.7)
    assert not [name for name in rd.FEATURES_BASELINE if any(word in name for word in ("hand", "elev", "height", "dist", "lon", "lat"))]
    with pytest.raises(rd.RadarDetectionError):
        rd.baseline_features(after, dry[:, :7], spread, np.zeros((14, 14)), np.zeros((14, 14)))


def test_otsu_split_finds_two_groups_and_says_how_far_apart_they_stand() -> None:
    rng = np.random.default_rng(1)
    two = np.concatenate([rng.normal(-22, 1, 3000), rng.normal(-12, 1, 7000)])
    split = rd.otsu_split(two)
    assert -19 < split["threshold"] < -15 and split["share_at_or_below"] == pytest.approx(0.3, abs=0.02) and split["separation"] > 5
    one = rd.otsu_split(rng.normal(-12, 1, 5000))
    assert 2.0 < one["separation"] < rd.TILE_MIN_SEPARATION  # one group cut in the middle: about 2.65, under the bar
    assert rd.otsu_split(np.full(10, 3.0)) is None and rd.otsu_split(np.array([np.nan])) is None


def test_scene_cut_uses_the_tiles_with_two_groups_and_falls_back_without_any() -> None:
    rng = np.random.default_rng(2)
    scene = rng.normal(-12, 1, (64, 64))
    scene[:32, :24] = rng.normal(-22, 1, (32, 24))  # water in the upper tiles only
    valid = np.ones((64, 64), dtype=bool)
    found = rd.scene_cut(scene, valid, fallback=-18.5, tile_cells=32)
    assert found["tiles"] == 4 and found["tiles_with_two_groups"] == 1 and -19.5 < found["cut"] < -14.5, found
    dry = rd.scene_cut(rng.normal(-12, 1, (64, 64)), valid, fallback=-18.5, tile_cells=32)
    assert dry["tiles_with_two_groups"] == 0 and dry["cut"] == -18.5 and dry["source"].startswith("the frozen cut")
    mostly_missing = valid.copy()
    mostly_missing[:, 10:] = False
    assert rd.scene_cut(scene, mostly_missing, fallback=-18.5, tile_cells=32)["tiles_with_two_groups"] == 0
    with pytest.raises(rd.RadarDetectionError):
        rd.scene_cut(scene, valid[:10], fallback=0.0)


def test_clean_drops_slopes_and_small_groups_and_grows_into_nearly_dark_neighbours() -> None:
    flag = np.zeros((12, 12), dtype=bool)
    flag[1:5, 1:5] = True  # 16 cells: kept
    flag[8, 8] = True  # one cell: dropped
    flag[9:12, 0:3] = True  # 9 cells on a slope: dropped
    slope = np.zeros((12, 12))
    slope[9:12, 0:3] = 9.0
    kept = rd.clean(flag, slope)
    assert kept[1:5, 1:5].all() and not kept[8, 8] and not kept[9:12, 0:3].any() and kept.sum() == 16
    nearly = np.zeros((12, 12), dtype=bool)
    nearly[1:5, 5:7] = True  # touches the kept group: taken in
    nearly[7:9, 9:11] = True  # touches only the dropped cell: left out
    grown = rd.clean(flag, slope, grow_from=nearly)
    assert grown[1:5, 1:7].all() and grown.sum() == 24 and not grown[7:9, 9:11].any()
    assert not rd.clean(np.zeros((4, 4), dtype=bool), np.zeros((4, 4))).any()
    with pytest.raises(rd.RadarDetectionError):
        rd.clean(flag, slope[:5])


def test_observable_leaves_out_tree_cover_and_built_up_ground() -> None:
    cover = np.array([[10, 40, 50], [30, 80, 60]])
    assert rd.observable(cover).tolist() == [[False, True, False], [True, True, True]]


def test_a_change_is_kept_only_when_it_is_better_on_every_held_out_area() -> None:
    trail = rd.keep_changes([
        {"name": "threshold", "iou": {"mae_sai": 0.24, "sukhothai": 0.57}},
        {"name": "adaptive", "iou": {"mae_sai": 0.25, "sukhothai": 0.62}},  # better on one area only
        {"name": "trees", "iou": {"mae_sai": 0.30, "sukhothai": 0.60}},  # better on both
        {"name": "cleaned", "iou": {"mae_sai": 0.31, "sukhothai": 0.63}},  # judged against the trees: not enough
        {"name": "broken", "iou": {"mae_sai": None, "sukhothai": 0.90}},
    ])
    assert trail["kept"] == "trees" and [step["kept"] for step in trail["steps"]] == [True, False, True, False, False]
    assert trail["steps"][3]["gain_over_the_step_kept_before"] == {"mae_sai": 0.01, "sukhothai": 0.03}
    assert rd.keep_changes([{"name": "only", "iou": {"a": 0.1}}])["kept"] == "only"
    with pytest.raises(rd.RadarDetectionError):
        rd.keep_changes([{"name": "a", "iou": {"x": 0.1}}, {"name": "b", "iou": {"y": 0.2}}])
    with pytest.raises(rd.RadarDetectionError):
        rd.keep_changes([])


def figure(iou: float, precision: float) -> dict[str, float]:
    return {"iou": iou, "flagged_that_is_reference_water": precision}


def test_the_sentences_for_the_one_test_follow_the_plan() -> None:
    rules = {"un_spider": figure(0.26, 0.72), "m1_literal": figure(0.38, 0.61), "m1_v2": figure(0.21, 0.76)}
    win = rd.statement_for_the_test(figure(0.60, 0.80), figure(0.50, 0.83), rules)
    assert win["detector_the_project_names"] == "frozen_detector" and win["best_fixed_rule"] == "m1_literal"
    close = rd.statement_for_the_test(figure(0.52, 0.80), figure(0.50, 0.83), rules)
    assert close["detector_the_project_names"] == "simple_threshold" and "nothing more complex" in close["what_is_said"]
    imprecise = rd.statement_for_the_test(figure(0.60, 0.60), figure(0.39, 0.83), rules)  # too many flags off water
    assert not imprecise["frozen_detector_improved"] and imprecise["detector_the_project_names"] == "fixed_rules"
    neither = rd.statement_for_the_test(figure(0.39, 0.9), figure(0.40, 0.9), rules)
    assert neither["detector_the_project_names"] == "fixed_rules" and "fixed rules stay" in neither["what_is_said"]
    same = rd.statement_for_the_test(figure(0.50, 0.83), figure(0.50, 0.83), rules, frozen_is_the_threshold=True)
    assert same["detector_the_project_names"] == "simple_threshold"
    with pytest.raises(rd.RadarDetectionError):
        rd.statement_for_the_test(figure(0.5, 0.8), figure(0.5, 0.8), {})


@pytest.mark.parametrize("path", [FREEZE, REFERENCE, RESULT])
def test_committed_records_carry_the_required_fields(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} has not been written")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["generated_at_utc"].endswith("Z") and record["source_timestamp"]
    assert record["plan"]["path"] == PLAN and record["assumptions"] and record["limits"]
    assert b"\r" not in path.read_bytes()


def test_the_detector_was_frozen_before_the_held_out_chips_were_read() -> None:
    if not FREEZE.exists():
        pytest.skip("the develop stage has not been run")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["held_out_chips_read"] is False
    again = rd.keep_changes([{"name": step["name"], "iou": step["iou"]} for step in freeze["ladder"]["steps"]])
    assert again["kept"] == freeze["ladder"]["kept"] == freeze["frozen_detector"]["step"]
    if not (REFERENCE.exists() and RESULT.exists()):
        pytest.skip("the held-out test has not been run")
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    assert freeze["generated_at_utc"] < reference["generated_at_utc"] < result["generated_at_utc"]
    assert result["freeze_record"]["sha256"] == hashlib.sha256(FREEZE.read_bytes()).hexdigest()
    assert result["reference_record"]["sha256"] == hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    assert "not accuracy" in result["label"]
    together = result["held_out_chips_together"]
    again_said = rd.statement_for_the_test(
        together["frozen_detector"], together["simple_threshold"], together["fixed_rules"],
        frozen_is_the_threshold=freeze["frozen_detector"]["step"] == freeze["ladder"]["steps"][0]["name"])
    assert again_said == result["what_the_plan_fixed"]
