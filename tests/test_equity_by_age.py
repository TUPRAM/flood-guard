"""Tests of access loss by age group: the rules of the protocol on invented cells, and the committed record."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from floodguard import equity_by_age as eba

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "outputs" / "equity_by_age" / "se1_mae_sai_v1.json"


def test_group_counts_split_every_cell_by_its_shares() -> None:
    groups = eba.group_counts(np.array([100.0, 50.0]), np.array([0.2, 0.1]), np.array([0.3, 0.2]))
    assert groups["children_0_14"].tolist() == [20.0, 5.0] and groups["15_plus"].tolist() == [80.0, 45.0]
    assert groups["older_60_plus"].tolist() == [30.0, 10.0] and groups["under_60"].tolist() == [70.0, 40.0]
    with pytest.raises(eba.EquityByAgeError):
        eba.group_counts(np.array([1.0]), np.array([0.7]), np.array([0.6]))
    with pytest.raises(eba.EquityByAgeError):
        eba.group_counts(np.array([-1.0]), np.array([0.1]), np.array([0.1]))


def test_compare_counts_only_residents_with_baseline_access_and_keeps_the_ratio_rules() -> None:
    row = eba.compare(200.0, 100.0, 800.0, 200.0)
    assert row["group_loss_rate"] == 0.5 and row["others_loss_rate"] == 0.25
    assert row["difference_of_rates"] == 0.25 and row["ratio_of_rates"] == 2.0 and row["ratio_not_given_because"] is None
    small = eba.compare(49.0, 49.0, 800.0, 200.0)
    assert small["ratio_of_rates"] is None and small["ratio_not_given_because"] == eba.RATIO_NULL_SMALL_GROUP
    assert small["difference_of_rates"] == 0.75  # the difference is still given
    none_lost = eba.compare(100.0, 0.0, 100.0, 0.0)
    assert none_lost["ratio_not_given_because"] == eba.RATIO_NULL_NO_LOSS and none_lost["difference_of_rates"] == 0.0
    assert eba.compare(100.0, 10.0, 100.0, 0.0)["ratio_not_given_because"] == eba.RATIO_NULL_ZERO_DENOMINATOR
    assert eba.compare(0.0, 0.0, 100.0, 10.0)["difference_of_rates"] is None
    with pytest.raises(eba.EquityByAgeError):
        eba.compare(10.0, 11.0, 100.0, 10.0)


def test_outcome_by_age_finds_a_gap_only_where_cells_with_another_mix_have_another_outcome() -> None:
    residents = np.array([1000.0, 1000.0])
    had = np.array([True, True])
    lost = np.array([True, False])
    same_mix = eba.group_counts(residents, np.array([0.2, 0.2]), np.array([0.3, 0.3]))
    assert eba.outcome_by_age(same_mix, had, lost)["60_plus_vs_under_60"]["difference_of_rates"] == 0.0
    older_where_lost = eba.group_counts(residents, np.array([0.2, 0.2]), np.array([0.4, 0.2]))
    gap = eba.outcome_by_age(older_where_lost, had, lost)["60_plus_vs_under_60"]
    assert gap["group_loss_rate"] == pytest.approx(400 / 600, abs=1e-6) and gap["difference_of_rates"] > 0.2
    inside_one_cell = eba.outcome_by_age(older_where_lost, had, lost, np.array([True, False]))["60_plus_vs_under_60"]
    assert inside_one_cell["difference_of_rates"] == 0.0  # one cell, one outcome
    with pytest.raises(eba.EquityByAgeError):
        eba.outcome_by_age(same_mix, np.array([False, True]), np.array([True, False]))


def test_gap_statement_needs_one_sign_a_range_off_zero_and_every_run() -> None:
    stable = eba.gap_statement([0.02, 0.03, 0.05])
    assert stable["may_state_a_gap"] and stable["sentence"] is None and stable["sign_retention"] == 1.0
    mixed = eba.gap_statement([0.02, -0.01, 0.03])
    assert not mixed["may_state_a_gap"] and mixed["sentence"] == eba.FIXED_SENTENCE and not mixed["range_excludes_zero"]
    assert eba.gap_statement([0.0, 0.0])["sentence"] == eba.FIXED_SENTENCE
    assert eba.gap_statement([0.02, None, 0.03])["sentence"] == eba.FIXED_SENTENCE
    assert eba.gap_statement([None])["sentence"] == eba.FIXED_SENTENCE
    with pytest.raises(eba.EquityByAgeError):
        eba.gap_statement([])


def test_committed_record_keeps_its_labels_and_its_arithmetic() -> None:
    if not RESULT.exists():
        pytest.skip("the result has not been written")
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["can_feed_decision_layer"] is False
    assert record["confidence_class"] == "low" and record["source_timestamp"] and record["assumptions"] and record["limits"]
    assert "not observed" in record["label"] and "three runs" in record["not_the_ensemble_of_the_protocol"]
    assert b"\r" not in RESULT.read_bytes()
    assert set(record["closure_levels"]) == {"strict", "central", "permissive"}
    for level in record["closure_levels"].values():
        assert level["reproduces_case_se1_for_every_tambon"] is True and len(level["by_tambon"]) == 8
        for outcome, block in level["whole_frame"].items():
            for name, entry in block.items():
                again = eba.compare(entry["group_residents_with_baseline_access"], entry["group_residents_who_lose_it"],
                                    entry["others_with_baseline_access"], entry["others_who_lose_it"])
                assert again["difference_of_rates"] == pytest.approx(entry["difference_of_rates"], abs=2e-5)
                tambons = [unit[outcome][name] for unit in level["by_tambon"].values()]
                assert sum(row["group_residents_who_lose_it"] for row in tambons) == pytest.approx(entry["group_residents_who_lose_it"], abs=1.0)
    for outcome, block in record["rule_applied_to_the_three_runs"].items():
        for name, statement in block.items():
            differences = [record["closure_levels"][level]["whole_frame"][outcome][name]["difference_of_rates"]
                           for level in ("strict", "central", "permissive")]
            assert eba.gap_statement(differences) == statement
    text = json.dumps(record).lower()
    assert "fpps" not in text and "action_class" not in text
