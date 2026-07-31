from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.evaluation import (
    ActiveLearningEvaluationError,
    compare_active_and_random_rounds,
    evaluate_active_learning_stopping_rule,
    write_active_learning_evaluation,
)


def _evidence(active_ious: list[float], random_ious: list[float]) -> pd.DataFrame:
    rows = []
    for index, (active_iou, random_iou) in enumerate(
        zip(active_ious, random_ious, strict=True), start=1
    ):
        for policy, iou in (("active", active_iou), ("stratified_random", random_iou)):
            rows.append(
                {
                    "round_id": f"R{index}",
                    "event_id": "TH-MAESAI-2024-09",
                    "round_order": index,
                    "acquisition_policy": policy,
                    "review_minutes": 100.0,
                    "iou": iou,
                    "dice": min(1.0, iou + 0.1),
                    "reviewer_dice": 0.85,
                    "reviewer_kappa": 0.82,
                    "area_bias_ratio": 0.10,
                    "uncovered_critical_strata_count": 0,
                    "source_timestamp": "2024-09-15T23:16:01Z",
                    "assumptions": "Equal-cost research comparison.",
                }
            )
    return pd.DataFrame(rows)


def test_three_equal_cost_nonwins_pause_active_acquisition() -> None:
    comparisons = compare_active_and_random_rounds(
        _evidence([0.40, 0.41, 0.42], [0.42, 0.42, 0.43])
    )
    decision = evaluate_active_learning_stopping_rule(comparisons)

    assert decision.status == "pause_active_nonwins"
    assert decision.continue_active_acquisition is False
    assert decision.trailing_nonwins == 3


def test_one_win_allows_query_only_collection_to_continue() -> None:
    comparisons = compare_active_and_random_rounds(
        _evidence([0.40, 0.41, 0.50], [0.42, 0.42, 0.43])
    )
    decision = evaluate_active_learning_stopping_rule(comparisons)

    assert decision.status == "continue_query_only_collection"
    assert decision.to_dict()["eligible_for_fpps"] is False


def test_reviewer_agreement_and_critical_strata_override_model_gains() -> None:
    evidence = _evidence([0.50], [0.40])
    evidence["reviewer_dice"] = 0.70
    comparisons = compare_active_and_random_rounds(evidence)
    assert (
        evaluate_active_learning_stopping_rule(comparisons).status
        == "pause_reviewer_agreement"
    )

    evidence = _evidence([0.50], [0.40])
    evidence["uncovered_critical_strata_count"] = 2
    comparisons = compare_active_and_random_rounds(evidence)
    assert (
        evaluate_active_learning_stopping_rule(comparisons).status
        == "pause_critical_strata_coverage"
    )


def test_unequal_cost_is_not_claimed_as_active_learning_evidence() -> None:
    evidence = _evidence([0.50], [0.40])
    evidence.loc[evidence["acquisition_policy"].eq("active"), "review_minutes"] = 150
    comparisons = compare_active_and_random_rounds(evidence)
    decision = evaluate_active_learning_stopping_rule(comparisons)

    assert comparisons.loc[0, "equal_cost_comparable"] == False
    assert decision.status == "pause_incomparable_cost"


def test_missing_random_control_comparator_fails_closed() -> None:
    evidence = _evidence([0.50], [0.40])
    evidence = evidence[evidence["acquisition_policy"].eq("active")]

    with pytest.raises(ActiveLearningEvaluationError, match="exactly active"):
        compare_active_and_random_rounds(evidence)


def test_evaluation_outputs_are_immutable(tmp_path: Path) -> None:
    _, _, written = write_active_learning_evaluation(
        _evidence([0.50], [0.40]),
        comparison_output_path=tmp_path / "comparisons.csv",
        summary_output_path=tmp_path / "summary.md",
    )

    with pytest.raises(ActiveLearningEvaluationError, match="cannot be overwritten"):
        write_active_learning_evaluation(
            _evidence([0.50], [0.40]),
            comparison_output_path=written["comparisons"],
            summary_output_path=written["summary"],
        )
