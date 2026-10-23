"""The study-event check: the counts, the sentences fixed in the plan, and the order of its records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import theos2_study_event as study

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "proposal_execution" / "theos2_study_event_check_plan_v1.md"
OUTPUT = ROOT / "outputs" / "theos2_study_event_check"
WET = np.array([[1, 1, 0, 0], [1, 0, 0, 0]], dtype=bool)
COMPARED = np.array([[1, 1, 1, 1], [1, 1, 1, 0]], dtype=bool)


def scores_with(**iou: float | None) -> dict:
    return {name: {"iou": iou.get(name, 0.1)} for name in study.READINGS}


def test_a_reading_is_counted_on_the_compared_cells_only() -> None:
    flag = np.array([[1, 0, 1, 0], [1, 0, 0, 1]], dtype=bool)
    result = study.score(flag, WET, COMPARED, cell_km2=0.5)
    assert result["cells"] == {"both": 2, "radar_only": 1, "image_only": 1, "neither": 3}, "the flag on a cell that is not compared is not counted"
    assert result["flagged_km2"] == 1.5 and result["reference_water_km2"] == 1.5
    assert result["flags_on_reference_water"] == pytest.approx(0.6667) and result["reference_water_flagged"] == pytest.approx(0.6667)
    assert result["iou"] == 0.5


def test_empty_denominators_give_no_share() -> None:
    nothing = study.score(np.zeros_like(WET), np.zeros_like(WET), COMPARED, cell_km2=1.0)
    assert nothing["iou"] is None and nothing["flags_on_reference_water"] is None and nothing["reference_water_flagged"] is None


def test_water_outside_the_compared_cells_and_other_shapes_are_refused() -> None:
    with pytest.raises(study.StudyEventError):
        study.score(WET, WET, np.zeros_like(WET), cell_km2=1.0)
    with pytest.raises(study.StudyEventError):
        study.score(WET[:1], WET, COMPARED, cell_km2=1.0)


def test_every_frozen_reading_is_scored_also_by_stratum() -> None:
    readings = {name: WET for name in study.READINGS}
    left = np.array([[1, 1, 0, 0], [1, 1, 0, 0]], dtype=bool)
    scored = study.score_readings(readings, WET, COMPARED, cell_km2=1.0, strata={"left": left, "right": ~left})
    assert set(scored) == set(study.READINGS) and scored["frozen_detector"]["iou"] == 1.0
    assert scored["frozen_detector"]["by_stratum"]["left"]["cells"]["both"] == 3
    assert scored["frozen_detector"]["by_stratum"]["right"]["iou"] is None
    with pytest.raises(study.StudyEventError, match="missing"):
        study.score_readings({"frozen_detector": WET}, WET, COMPARED, cell_km2=1.0)


def test_a_new_reading_is_named_only_with_the_margin_over_the_best_fixed_rule() -> None:
    named = study.statement(scores_with(frozen_detector=0.42, m1_literal_last_pass_before=0.40, un_spider_last_pass_before=0.30), hours_after_the_pass=28.6)
    assert named["named_better"] == ["frozen_detector"] and named["best_fixed_rule"] == "m1_literal_last_pass_before"
    assert "not replaced" in named["sentence"] and "28.6 hours" in named["time_gap"] and "lower bound" in named["time_gap"]
    short = study.statement(scores_with(frozen_detector=0.419, m1_literal_last_pass_before=0.40), hours_after_the_pass=4.3)
    assert short["named_better"] == [] and short["sentence"].endswith("The fixed rules stay.")


def test_nothing_is_named_when_a_fixed_rule_has_no_figure() -> None:
    result = study.statement(scores_with(frozen_detector=0.9, m1_v2_last_pass_before=None), hours_after_the_pass=28.6)
    assert result["named_better"] == [] and "nothing is named" in result["sentence"]


def test_a_dry_road_is_never_called_passable() -> None:
    dry = study.road_reading([{"length_m": 100.0, "observable_m": 100.0, "water_m": 0.0, "seen_under_water": False}])
    assert dry["reading"] == "no piece seen under water on the image" and "cannot show that a road stayed passable" in dry["caution"]
    wet = study.road_reading([{"length_m": 100.0, "observable_m": 80.0, "water_m": 40.0, "seen_under_water": True},
                              {"length_m": 50.0, "observable_m": 50.0, "water_m": 0.0, "seen_under_water": False}])
    assert wet["pieces_seen_under_water"] == 1 and wet["share_of_the_observable_length_on_water"] == pytest.approx(0.3077)
    assert "very likely under water at the peak" in wet["caution"]
    hidden = study.road_reading([{"length_m": 100.0, "observable_m": 0.0, "water_m": 0.0, "seen_under_water": False}])
    assert hidden["reading"] == "not observable on the image"
    with pytest.raises(study.StudyEventError):
        study.road_reading([{"length_m": 10.0, "observable_m": 5.0, "water_m": 6.0, "seen_under_water": True}])


def test_the_plan_names_the_readings_the_margin_and_the_order() -> None:
    plan = PLAN.read_text(encoding="utf-8")
    for name in study.READINGS:
        assert f"`{name}`" in plan
    assert "0.02 or more" in plan and "cannot show that a road stayed passable" in plan and "No setting is made by eye" in plan
    assert plan.index("The radar freeze record") < plan.index("the reference record (stage `reference`)") < plan.index("the comparison (stage `compare`)")


def test_the_records_were_made_in_the_order_of_the_plan() -> None:
    freeze_path = OUTPUT / "radar_freeze_v1.json"
    if not freeze_path.exists():
        pytest.skip("the radar readings have not been frozen")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["official_warning"] is False and freeze["can_feed_decision_layer"] is False and freeze["no_image_of_the_event_was_read"] is True
    assert freeze["confidence_class"] == "low" and freeze["source_timestamp"] and freeze["assumptions"] and freeze["limits"]
    assert freeze["plan"]["sha256"] == hashlib.sha256(PLAN.read_bytes()).hexdigest(), "the plan is the one the readings were frozen under"
    assert list(freeze["readings"]) == list(study.READINGS) and len(freeze["raster_outside_git"]["sha256"]) == 64
    freeze_sha = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    for reference_path in OUTPUT.glob("reference_*.json"):
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        assert reference["radar_read"] is False and reference["radar_freeze"]["sha256"] == freeze_sha and reference["looked_at"].strip()
    for comparison_path in OUTPUT.glob("comparison_*.json"):
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        assert comparison["radar_freeze"]["sha256"] == freeze_sha
        assert (ROOT / comparison["reference"]["path"]).exists()


def test_a_2m_pixel_is_the_mean_of_16_pixels_and_valid_only_when_all_have_counts() -> None:
    block = np.arange(1, 1 + 4 * 4 * 8, dtype="uint16").reshape(4, 4, 8)
    block[2, 0, 5] = 0  # one pixel of the second 2 m pixel has no count in one band: outside a footprint
    mean, valid = study.block_mean(block)
    assert mean.shape == (4, 1, 2) and valid.tolist() == [[True, False]]
    assert mean[0, 0, 0] == pytest.approx(block[0, :, :4].mean()) and (mean[:, 0, 1] == 0).all()
    with pytest.raises(study.StudyEventError):
        study.block_mean(np.ones((4, 3, 4), dtype="uint16"))


def test_where_products_overlap_the_first_one_stays_and_its_disagreements_are_counted() -> None:
    mosaic = np.full((3, 4), 255, dtype="uint8")
    covered = np.zeros((3, 4), dtype=bool)
    first = np.array([[1, 0], [0, 0]], dtype="uint8")
    assert study.place_first_valid(mosaic, covered, first, np.ones((2, 2), dtype=bool), 0, 0) == 0
    second = np.array([[1, 1], [1, 1]], dtype="uint8")
    valid = np.array([[True, True], [False, True]])
    assert study.place_first_valid(mosaic, covered, second, valid, 0, 1) == 1, "pixel (0, 1) said 0 first and 1 now"
    assert mosaic.tolist() == [[1, 0, 1, 255], [0, 0, 1, 255], [255, 255, 255, 255]]
    assert covered.sum() == 6
    with pytest.raises(study.StudyEventError):
        study.place_first_valid(mosaic, covered, second, valid, 2, 3)


def test_the_reference_stage_reads_rule_v2_with_rule_v1_beside_it_as_amendment_1_says() -> None:
    script = (ROOT / "scripts" / "build_theos2_study_event_check.py").read_text(encoding="utf-8")
    amendment = (ROOT / "docs" / "proposal_execution" / "theos2_study_event_check_plan_v1_amendment_1.md").read_text(encoding="utf-8")
    assert 'RULES = ("rule_v2", "rule_v1")' in script and "theos2_study_event_check_plan_v1_amendment_1.md" in script
    assert '"reference_rule": "rule_v2"' in script and "rule_v1_left_out" in script
    # The pictures are made before the look is written: a draft outside Git first, the record only with --looked-at.
    assert "def finish_reference" in script and "_draft.json" in script and "changed after the draft was written" in script
    assert "rule v2" in amendment and "names this amendment with its SHA-256" in amendment
