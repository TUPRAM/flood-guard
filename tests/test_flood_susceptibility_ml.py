"""Tests of the trained flood-susceptibility model: the pure parts on invented cells, and the committed records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import flood_susceptibility_ml as ml

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "flood_susceptibility"
FREEZE = OUTPUTS / "mae_sai_model_v1_freeze.json"
RESULT = OUTPUTS / "mae_sai_model_v1.json"
RECEIPT = OUTPUTS / "mae_sai_model_v1_receipt.json"


def invented_cells(count: int = 6000, seed: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Cells on a 12 km square: low ground near a river floods, with noise; one feature is pure noise."""

    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 12_000, count)
    y = rng.uniform(0, 12_000, count)
    height = np.abs(x - 6_000) / 400 + rng.normal(0, 1.0, count)
    noise = rng.normal(0, 1, count)
    probability = 1 / (1 + np.exp(1.2 * (height - 4)))
    label = rng.uniform(0, 1, count) < probability
    return x, y, np.column_stack([height, noise]), label


def test_block_folds_keep_a_block_together_and_depend_on_the_seed_only() -> None:
    x, y, _features, _label = invented_cells()
    folds = ml.block_folds(x, y)
    assert set(np.unique(folds)) == set(range(ml.FOLDS))
    blocks = np.floor(x / ml.BLOCK_M).astype(int) * 1000 + np.floor(y / ml.BLOCK_M).astype(int)
    for block in np.unique(blocks):
        assert np.unique(folds[blocks == block]).size == 1
    assert np.array_equal(folds, ml.block_folds(x, y))
    order = np.random.default_rng(1).permutation(x.size)
    assert np.array_equal(ml.block_folds(x[order], y[order]), folds[order])
    with pytest.raises(ml.SusceptibilityError):
        ml.block_folds(np.array([1.0, 2.0]), np.array([1.0, 2.0]))


def test_out_of_fold_values_come_from_models_that_did_not_see_the_fold() -> None:
    x, y, features, label = invented_cells(3000)
    folds = ml.block_folds(x, y)
    raw = ml.out_of_fold(ml.BASELINE, None, features[:, :1], label, folds)
    assert np.isfinite(raw).all() and 0 <= raw.min() and raw.max() <= 1
    # A label shuffled within each fold cannot be learned from another fold: the ranking falls to chance.
    from sklearn.metrics import roc_auc_score

    assert roc_auc_score(label, raw) > 0.8
    shuffled = label.copy()
    np.random.default_rng(0).shuffle(shuffled)
    assert abs(roc_auc_score(shuffled, ml.out_of_fold(ml.BASELINE, None, features[:, :1], shuffled, folds)) - 0.5) < 0.08


def test_select_settings_keeps_the_best_and_reports_every_trial() -> None:
    x, y, features, label = invented_cells(3000)
    folds = ml.block_folds(x, y)
    selection, raw = ml.select_settings(ml.GRADIENT_BOOSTING, ml.GRADIENT_BOOSTING_GRID, features, label, folds)
    assert len(selection.trials) == 4 and selection.settings in [dict(item) for item in ml.GRADIENT_BOOSTING_GRID]
    best = max(trial["mean_average_precision"] for trial in selection.trials)
    kept = next(trial for trial in selection.trials if trial["settings"] == selection.settings)
    assert kept["mean_average_precision"] == best and raw.shape == label.shape


def test_calibration_figures() -> None:
    probability = np.array([0.05, 0.05, 0.15, 0.95, 0.95, 0.85, 0.5, 0.5])
    label = np.array([0, 0, 0, 1, 1, 1, 0, 1])
    table = ml.reliability_table(probability, label)
    assert sum(row["cells"] for row in table) == 8 and table[0]["cells"] == 2 and table[5]["flooded_share"] == 0.5
    assert ml.expected_calibration_error(np.array([0.25, 0.25, 0.25, 0.25]), np.array([1, 0, 0, 0])) == 0.0
    assert ml.expected_calibration_error(np.array([0.9, 0.9]), np.array([0, 0])) == pytest.approx(0.9)
    answered = ml.abstention(probability, label)
    assert answered["cells_with_an_answer"] == 6 and answered["agreement_on_answered_cells"] == 1.0
    curve = ml.risk_coverage(probability, label, steps=4)
    assert curve[0]["agreement"] == 1.0 and curve[-1]["cells"] == 8
    assert [row["agreement"] for row in curve] == sorted((row["agreement"] for row in curve), reverse=True)


def test_scores_and_the_rule_for_which_model_is_cited() -> None:
    x, y, features, label = invented_cells()
    folds = ml.block_folds(x, y)
    raw = ml.out_of_fold(ml.BASELINE, None, features[:, :1], label, folds)
    figures = ml.scores(ml.fit_isotonic(raw, label).predict(raw), label, training_prevalence=float(label.mean()))
    assert figures["roc_auc"] > 0.8 and figures["brier_skill"] > 0 and figures["expected_calibration_error"] < 0.05
    assert ml.scores(np.array([0.2, 0.3]), np.array([0, 0]), training_prevalence=0.1)["note"].startswith("one class")

    def test_set(auc: float, precision: float) -> dict[str, float]:
        return {"roc_auc": auc, "average_precision": precision}

    close = ml.cite_decision({ml.BASELINE: test_set(0.80, 0.50), ml.RANDOM_FOREST: test_set(0.81, 0.60),
                              ml.GRADIENT_BOOSTING: test_set(0.83, 0.51)})
    assert close["model_to_cite"] == ml.BASELINE  # each tree model misses the margin on one of the two figures
    clear = ml.cite_decision({ml.BASELINE: test_set(0.80, 0.50), ml.RANDOM_FOREST: test_set(0.85, 0.58),
                              ml.GRADIENT_BOOSTING: test_set(0.86, 0.57)})
    assert clear["model_to_cite"] == ml.RANDOM_FOREST and clear["against_the_baseline"][ml.GRADIENT_BOOSTING]["meets_the_margin"]


def test_unknown_model_kind_is_refused() -> None:
    with pytest.raises(ml.SusceptibilityError):
        ml.make_model("deep_network")


@pytest.mark.parametrize("path", [FREEZE, RESULT, RECEIPT])
def test_committed_records_carry_the_required_fields(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.name} has not been written")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False and record["confidence_class"] == "low"
    assert record["generated_at_utc"].endswith("Z") and record["source_timestamp"]
    assert record["plan"]["path"] == "docs/proposal_execution/flood_susceptibility_model_plan_v1.md"
    assert b"\r" not in path.read_bytes()
    if path != RECEIPT:
        assert record["assumptions"] and record["limits"]


def test_the_test_districts_were_read_after_the_freeze_and_the_result_is_bound() -> None:
    if not RESULT.exists():
        pytest.skip("the test stage has not been run")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert freeze["label"]["districts_read"] == ["TH5709"]
    assert receipt["inputs"]["label"]["districts_read"] == ["TH5707", "TH5708", "TH5715"]
    assert result["freeze_record"]["sha256"] == hashlib.sha256(FREEZE.read_bytes()).hexdigest()
    assert freeze["generated_at_utc"] < result["generated_at_utc"]
    assert "not accuracy" in result["label"]
    recorded = receipt["outputs"]["outputs/flood_susceptibility/mae_sai_model_v1.json"]["sha256"]
    assert hashlib.sha256(RESULT.read_bytes()).hexdigest() == recorded
    assert result["which_model_is_cited"]["model_to_cite"] in (ml.BASELINE, ml.RANDOM_FOREST, ml.GRADIENT_BOOSTING)

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    assert not {key for key in keys(result) if "fpps" in key.lower() or "action_class" in key.lower()}
