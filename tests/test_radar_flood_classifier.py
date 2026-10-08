"""Tests of the supervised radar flood classifier: the pure parts on invented cells, and the committed records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import radar_flood_classifier as rfc

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "radar_flood_classifier"
FREEZE = OUTPUTS / "chiang_rai_20241022_freeze_v1.json"
RESULT = OUTPUTS / "chiang_rai_20241022_v1.json"
RECEIPT = OUTPUTS / "chiang_rai_20241022_v1_receipt.json"
PLAN = "docs/proposal_execution/radar_flood_classifier_plan_v1.md"


def test_no_feature_says_where_water_usually_stands() -> None:
    names = set(rfc.FEATURES_ALL)
    assert set(rfc.FEATURES_AFTER_ONLY) < names and set(rfc.FEATURES_BASELINE) < names
    assert not [name for name in names if any(word in name for word in ("hand", "elev", "height", "dist", "lon", "lat", "x_", "y_"))]
    assert not [name for name in rfc.FEATURES_AFTER_ONLY if "before" in name or "change" in name]
    assert rfc.MODELS[rfc.PRIMARY]["features"] == rfc.FEATURES_ALL and set(rfc.MODELS) == {rfc.BASELINE, rfc.PRIMARY, rfc.RANDOM_FOREST, rfc.AFTER_ONLY}


def test_focal_mean_ignores_missing_values_and_is_empty_where_nothing_is_valid() -> None:
    values = np.full((7, 7), 2.0)
    values[3, 3] = np.nan
    assert rfc.focal_mean(values)[3, 3] == pytest.approx(2.0)
    values[:, :] = np.nan
    assert np.isnan(rfc.focal_mean(values)).all()
    ramp = np.tile(np.arange(9, dtype="float64"), (9, 1))
    assert rfc.focal_mean(ramp)[4, 4] == pytest.approx(4.0)


def test_pair_features_read_darkening_as_a_negative_change() -> None:
    rng = np.random.default_rng(3)
    before = np.abs(rng.normal(0.1, 0.01, (2, 12, 12)))
    after = before.copy()
    after[:, 4:9, 4:9] *= 0.1  # a block that went dark: minus 10 dB
    slope = np.full((12, 12), 1.5)
    land_cover = np.full((12, 12), 40)
    features = rfc.pair_features(before, after, slope, land_cover)
    assert tuple(features) == rfc.FEATURES_ALL and all(value.dtype == np.float32 for value in features.values())
    assert features["vh_change_db"][6, 6] == pytest.approx(-10.0, abs=0.01)
    assert abs(features["vh_change_db"][0, 0]) < 0.01
    assert features["vh_after_spread_db"][6, 6] < features["vh_after_spread_db"][4, 4]  # the edge of the block is rougher
    assert rfc.usable_cells(features).all()
    after[1, 0, 0] = np.nan
    assert rfc.usable_cells(rfc.pair_features(before, after, slope, land_cover)).all()  # one missing cell is bridged by the window
    with pytest.raises(rfc.RadarClassifierError):
        rfc.pair_features(before, after[:, :6], slope, land_cover)
    with pytest.raises(rfc.RadarClassifierError):
        rfc.pair_features(before, after, slope[:6], land_cover)


def test_draw_sample_keeps_both_kinds_and_its_weights_put_the_true_share_back() -> None:
    label = np.zeros(10_000, dtype=bool)
    label[:400] = True
    index, weight = rfc.draw_sample(label, max_water=100, max_other=300)
    assert index.size == 400 and np.all(np.diff(index) > 0)
    assert int(label[index].sum()) == 100
    assert weight[label[index]].sum() == pytest.approx(400) and weight[~label[index]].sum() == pytest.approx(9_600)
    again, _ = rfc.draw_sample(label, max_water=100, max_other=300)
    assert np.array_equal(index, again)
    everything, ones = rfc.draw_sample(label, max_water=10**6, max_other=10**6)
    assert everything.size == label.size and np.all(ones == 1.0)
    with pytest.raises(rfc.RadarClassifierError):
        rfc.draw_sample(np.zeros(5, dtype=bool))


def test_flag_counts_and_the_cut() -> None:
    label = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
    flagged = np.array([1, 1, 0, 1, 0, 0, 0, 0], dtype=bool)
    counts = rfc.flag_counts(flagged, label)
    assert counts["flagged_that_is_reference_water"] == pytest.approx(2 / 3, abs=1e-6)
    assert counts["reference_water_flagged"] == pytest.approx(2 / 3, abs=1e-6) and counts["iou"] == 0.5
    weighted = rfc.flag_counts(flagged, label, np.array([1, 1, 1, 10, 10, 10, 10, 10.0]))
    assert weighted["flagged_that_is_reference_water"] == pytest.approx(2 / 12, abs=1e-6)
    assert rfc.flag_counts(np.zeros(3, dtype=bool), np.zeros(3, dtype=bool))["iou"] is None
    probability = np.array([0.9, 0.8, 0.45, 0.4, 0.2, 0.1, 0.1, 0.05])
    cut = rfc.best_cut(probability, label, np.ones(8))
    assert 0.4 < cut["cut"] <= 0.45 and cut["iou_out_of_fold"] == 1.0 and len(cut["trials"]) == len(rfc.CUTS)
    answered = rfc.withheld(probability, label)
    assert answered["cells_with_an_answer"] == 6 and answered["on_answered_cells"]["iou"] == 1.0
    assert rfc.ranking(probability, label)["roc_auc"] == 1.0
    assert rfc.ranking(probability, np.zeros(8, dtype=bool))["note"] == "one class only"


def test_weighted_isotonic_learns_the_weighted_share() -> None:
    raw = np.array([0.2, 0.2, 0.8, 0.8])
    label = np.array([0, 1, 0, 1], dtype=bool)
    weight = np.array([9.0, 1.0, 1.0, 1.0])
    calibration = rfc.weighted_isotonic(raw, label, weight)
    assert calibration.predict([0.2])[0] == pytest.approx(0.1) and calibration.predict([0.8])[0] == pytest.approx(0.5)


def test_statement_names_the_classifier_only_when_the_primary_model_beats_every_rule() -> None:
    rules = {"un_spider": 0.26, "m1_literal": 0.38, "m1_v2": 0.21}
    wins = rfc.statement({rfc.PRIMARY: 0.45, rfc.BASELINE: 0.30}, rules)
    assert wins["classifier_named_as_an_improvement"] and wins["what_is_said"].startswith("The primary model is better")
    close = rfc.statement({rfc.PRIMARY: 0.40, rfc.AFTER_ONLY: 0.50}, rules)  # 0.02 above the best rule is not enough
    assert not close["classifier_named_as_an_improvement"]
    assert close["comparison_models_better_than_all_fixed_rules"] == [rfc.AFTER_ONLY] and "not renamed" in close["what_is_said"]
    none = rfc.statement({rfc.PRIMARY: 0.30, rfc.BASELINE: None}, rules)
    assert not none["classifier_named_as_an_improvement"] and "did not carry over" in none["what_is_said"]
    assert none["better_than_each_fixed_rule"][rfc.PRIMARY] == {"un_spider": True, "m1_literal": False, "m1_v2": True}
    with pytest.raises(rfc.RadarClassifierError):
        rfc.statement({rfc.BASELINE: 0.5}, rules)
    with pytest.raises(rfc.RadarClassifierError):
        rfc.statement({rfc.PRIMARY: 0.5}, {"un_spider": None})


@pytest.mark.parametrize("path", [FREEZE, RESULT, RECEIPT])
def test_committed_records_carry_the_required_fields(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} has not been written")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["generated_at_utc"].endswith("Z") and record["source_timestamp"]
    assert record["plan"]["path"] == PLAN
    assert b"\r" not in path.read_bytes()
    if path != RECEIPT:
        assert record["assumptions"] and record["limits"] and "local level" in record["rights_note"]


def test_the_models_were_frozen_before_any_test_label_and_the_result_follows_the_plan() -> None:
    if not FREEZE.exists():
        pytest.skip("the fit stage has not been run")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["test_labels_read"] is False and freeze["primary_model"] == rfc.PRIMARY
    assert set(freeze["models"]) == set(rfc.MODELS)
    codes = {entry["adm2_pcode"] for entry in freeze["training"]["districts"]}
    assert not codes & {"TH5709", "TH5701", "TH5705"}  # the test district and the two reserved districts
    for name, entry in freeze["models"].items():
        assert entry["features"] == list(rfc.MODELS[name]["features"]) and entry["frozen_cut"] in rfc.CUTS
        assert len(entry["trials"]) == len(rfc.MODELS[name]["grid"])
    if not RESULT.exists():
        pytest.skip("the test stage has not been run")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert result["freeze_record"]["sha256"] == hashlib.sha256(FREEZE.read_bytes()).hexdigest()
    assert freeze["generated_at_utc"] < result["generated_at_utc"] and "not accuracy" in result["label"]
    assert receipt["outputs"]["outputs/radar_flood_classifier/chiang_rai_20241022_v1.json"]["sha256"] == hashlib.sha256(RESULT.read_bytes()).hexdigest()
    test_b = result["test_b_sukhothai_theos2"]
    again = rfc.statement({name: entry["at_the_frozen_cut"]["iou"] for name, entry in test_b["models"].items()},
                          {name: entry["at_its_own_rule"]["iou"] for name, entry in test_b["fixed_rules"].items()})
    assert again == result["what_the_plan_fixed"]
    for frame in (result["test_a_mae_sai_agency_layer"], test_b):
        assert set(frame["models"]) == set(rfc.MODELS) and set(frame["fixed_rules"]) == {"un_spider", "m1_literal", "m1_v2"}
        for name, entry in frame["models"].items():
            assert entry["frozen_cut"] == freeze["models"][name]["frozen_cut"]

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(result) if "fpps" in key.lower() or "action_class" in key.lower() or "adm3" in key.lower()}
