"""Shared binary-mask metrics with role scoping and a positive-support floor.

``sar_flood``, ``water_unet`` and ``embeddings`` each carried a private
``_mask_metrics`` with the same body. Consolidating them here is not only
de-duplication: role-scoped evaluation needs one definition of "what counts as
enough evidence to publish a number", and three copies would drift.

The positive-support floor exists because Mae Sai's positive rates are tiny
(~0.2% flood, ~6% water). A held-out block that happens to contain 40 water
pixels can produce an IoU of 0.9 or 0.1 depending on a handful of boundary
pixels. Rather than publish that and caveat it in prose, the metric refuses to
report and states why -- the same fail-closed discipline the rest of the
repository applies to evidence, applied to a metric.
"""

from __future__ import annotations

import numpy as np

# Below this many reference-positive pixels a role's metrics are not reportable.
DEFAULT_MIN_POSITIVE = 2_000

# Recall floor below which a segmentation metric is not a measurement.
#
# A model that has collapsed to the majority class still produces a finite IoU,
# and that number reads exactly like a result. Observed 2026-07-30: Component B
# trained on a 0.33%-water label for 120 epochs returned IoU 0.0023 with recall
# 0.0024 -- it had learned to predict almost no water at all. The 20-epoch run
# of the same configuration returned IoU 0.2448 purely by being under-fit.
# Publishing either as an accuracy figure would be misleading in opposite
# directions.
#
# Flagging rather than suppressing: the numbers stay visible for diagnosis, but
# they carry `degenerate=True` so no consumer can mistake them for a measurement.
DEGENERATE_RECALL_FLOOR = 0.05


def binary_mask_metrics(
    predicted: np.ndarray,
    reference: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    min_positive: int | None = DEFAULT_MIN_POSITIVE,
    counts: bool = False,
) -> dict[str, float | int | str]:
    """Return IoU / F1 / precision / recall over ``mask``, or a blocked reason.

    Args:
        predicted: Binary (or truthy) prediction array.
        reference: Binary (or truthy) reference array of the same shape.
        mask: Optional boolean selector; only these pixels are scored. Use this
            to restrict scoring to one partition role.
        min_positive: Refuse to report when the reference has fewer than this
            many positive pixels inside ``mask``. Pass ``None`` to always report.
        counts: Include raw confusion counts in the result.

    Returns:
        A dict with ``iou``/``f1_dice``/``precision``/``recall`` plus support
        fields, or ``{"blocked_reason": ...}`` with the support fields and no
        metrics when the positive floor is not met.
    """

    predicted = np.asarray(predicted)
    reference = np.asarray(reference)
    if predicted.shape != reference.shape:
        raise ValueError(f"predicted shape {predicted.shape} != reference shape {reference.shape}.")

    if mask is None:
        p = predicted.astype(bool).ravel()
        r = reference.astype(bool).ravel()
    else:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != predicted.shape:
            raise ValueError(f"mask shape {mask.shape} != data shape {predicted.shape}.")
        p = predicted.astype(bool)[mask]
        r = reference.astype(bool)[mask]

    n_pixels = int(r.size)
    n_positive = int(np.count_nonzero(r))
    support: dict[str, float | int | str] = {
        "n_pixels": n_pixels,
        "n_reference_positive": n_positive,
        "positive_rate": round(n_positive / n_pixels, 6) if n_pixels else 0.0,
    }

    if n_pixels == 0:
        support["blocked_reason"] = "empty_evaluation_region"
        return support
    if min_positive is not None and n_positive < int(min_positive):
        support["blocked_reason"] = "insufficient_positive_support"
        support["min_positive_required"] = int(min_positive)
        return support

    tp = int(np.count_nonzero(p & r))
    fp = int(np.count_nonzero(p & ~r))
    fn = int(np.count_nonzero(~p & r))
    tn = n_pixels - tp - fp - fn

    def ratio(numerator: float, denominator: float) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    recall = ratio(tp, tp + fn)
    support.update(
        {
            "iou": ratio(tp, tp + fp + fn),
            "f1_dice": ratio(2 * tp, 2 * tp + fp + fn),
            "precision": ratio(tp, tp + fp),
            "recall": recall,
        }
    )

    # A metric from a collapsed model is not a measurement. See
    # DEGENERATE_RECALL_FLOOR.
    if tp + fp == 0:
        support["degenerate"] = True
        support["degenerate_reason"] = "model_predicted_no_positives"
    elif recall < DEGENERATE_RECALL_FLOOR:
        support["degenerate"] = True
        support["degenerate_reason"] = "predictions_collapsed_to_majority_class"
        support["degenerate_recall_floor"] = DEGENERATE_RECALL_FLOOR

    if counts:
        support.update(
            {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn}
        )
    return support


def sweep_threshold(
    probability: np.ndarray,
    reference: np.ndarray,
    *,
    mask: np.ndarray,
    thresholds: np.ndarray | None = None,
    objective: str = "f1_dice",
) -> dict[str, object]:
    """Pick the probability threshold maximising ``objective`` inside ``mask``.

    This must only ever be called with a **validation** role mask. Selecting an
    operating point on the same pixels a metric is reported from is exactly the
    leak this package is being restructured to remove, so the caller is required
    to pass the mask explicitly rather than defaulting to the full scene.
    """

    if objective not in {"f1_dice", "iou"}:
        raise ValueError(f"objective must be 'f1_dice' or 'iou'; got {objective!r}.")
    probability = np.asarray(probability, dtype="float64")
    mask = np.asarray(mask, dtype=bool)
    if thresholds is None:
        thresholds = np.round(np.arange(0.05, 0.96, 0.05), 2)

    rows: list[dict[str, float]] = []
    best: dict[str, float] | None = None
    for threshold in thresholds:
        scored = binary_mask_metrics(
            probability >= threshold, reference, mask=mask, min_positive=None
        )
        row = {
            "threshold": float(threshold),
            "iou": float(scored.get("iou", 0.0)),
            "f1_dice": float(scored.get("f1_dice", 0.0)),
            "precision": float(scored.get("precision", 0.0)),
            "recall": float(scored.get("recall", 0.0)),
        }
        rows.append(row)
        if best is None or row[objective] > best[objective]:
            best = row
    if best is None:  # pragma: no cover - thresholds is never empty in practice
        raise ValueError("threshold sweep produced no candidates.")
    return {
        "selected_threshold": best["threshold"],
        "selected_on_role": "val",
        "objective": objective,
        "objective_value": best[objective],
        "curve": rows,
    }
