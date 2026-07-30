"""A metric from a collapsed model must not read as a measurement.

Observed 2026-07-30 on Component B trained against a 0.33%-water label:

    20 epochs   IoU 0.2448  precision 0.279   recall 0.666
    120 epochs  IoU 0.0023  precision 0.0667  recall 0.0024

The 120-epoch model had collapsed to the majority class -- with 352 positive
training pixels against 436,786, longer training drove it to predict almost no
water. Both numbers are misleading, in opposite directions: one from under-
fitting, one from collapse. Neither is an accuracy figure, and an IoU of 0.0023
published without qualification looks exactly like a poor-but-real result.

The guard flags rather than suppresses, so the numbers stay available for
diagnosis while carrying `degenerate=True`.
"""

from __future__ import annotations

import numpy as np

from geoai_runner.realpipeline.metrics import (
    DEGENERATE_RECALL_FLOOR,
    binary_mask_metrics,
)

SHAPE = (200, 200)


def _reference() -> np.ndarray:
    ref = np.zeros(SHAPE, dtype=bool)
    ref[50:150, 50:60] = True  # 1,000 positive pixels
    return ref


def test_a_model_predicting_nothing_is_flagged() -> None:
    ref = _reference()
    pred = np.zeros(SHAPE, dtype=bool)
    out = binary_mask_metrics(pred, ref, min_positive=None)
    assert out["degenerate"] is True
    assert out["degenerate_reason"] == "model_predicted_no_positives"


def test_the_observed_collapse_is_flagged() -> None:
    """Reproduce the 120-epoch failure: a handful of correct pixels, recall ~0."""

    ref = _reference()
    pred = np.zeros(SHAPE, dtype=bool)
    pred[50:52, 50:51] = True  # 2 true positives out of 1,000
    out = binary_mask_metrics(pred, ref, min_positive=None)
    assert out["recall"] < DEGENERATE_RECALL_FLOOR
    assert out["degenerate"] is True
    assert out["degenerate_reason"] == "predictions_collapsed_to_majority_class"
    assert out["degenerate_recall_floor"] == DEGENERATE_RECALL_FLOOR
    # The numbers survive for diagnosis.
    assert out["iou"] is not None and out["precision"] is not None


def test_a_healthy_model_is_not_flagged() -> None:
    ref = _reference()
    pred = ref.copy()
    pred[50:60, 50:60] = False  # lose 100 of 1,000 -> recall 0.9
    out = binary_mask_metrics(pred, ref, min_positive=None)
    assert out["recall"] >= 0.85
    assert "degenerate" not in out
    assert "degenerate_reason" not in out


def test_a_poor_but_real_model_is_not_flagged() -> None:
    """Only collapse is flagged, not merely bad performance."""

    ref = _reference()
    pred = np.zeros(SHAPE, dtype=bool)
    pred[50:150, 55:75] = True  # over-predicts: low precision, high recall
    out = binary_mask_metrics(pred, ref, min_positive=None)
    assert out["recall"] > DEGENERATE_RECALL_FLOOR
    assert out["precision"] < 0.5
    assert "degenerate" not in out, "low precision alone is a real result, not collapse"


def test_the_insufficient_support_guard_still_takes_precedence() -> None:
    """Too few reference positives blocks before degeneracy is even considered."""

    ref = np.zeros(SHAPE, dtype=bool)
    ref[0:10, 0:10] = True  # 100 positives
    out = binary_mask_metrics(np.zeros(SHAPE, dtype=bool), ref, min_positive=2_000)
    assert out["blocked_reason"] == "insufficient_positive_support"
    assert "iou" not in out
    assert "degenerate" not in out
