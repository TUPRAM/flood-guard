"""Component F -- Label-scarce generalization via satellite embeddings.

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 16 "Satellite Embeddings". The
book's workflow: instead of training a network from raw pixels, reuse a
foundation model's precomputed embedding per location and fit a lightweight
classifier (k-NN, Random Forest, logistic regression) on a handful of labels.

Two honest limits, both now reported in the metrics rather than left implicit
--------------------------------------------------------------------------
1. **The features contain the target's own inputs.** The label is
   ``MNDWI = (green - swir1) / (green + swir1) > 0``, and the feature vector
   includes raw green and raw SWIR1. A Random Forest fitted on those features is
   therefore re-deriving a threshold it was handed, not generalising. The result
   is emitted with ``feature_contains_target_inputs=True`` so no reader can
   mistake it for evidence of few-shot transfer.

2. **These are not foundation-model embeddings.** Real Clay / AlphaEarth /
   TESSERA vectors must be downloaded; this module computes local spectral +
   texture features as a stand-in. The published caveat (Kaushik et al., 2026)
   that foundation models trail on SAR versus optical is carried in the registry.

Both limits are dissolved by the same follow-up: real embeddings evaluated on a
**different district**. Reproducing an index inside the scene it was computed
from is a tautology no matter how few labels are used; predicting water in a
district the classifier has never seen is the actual Ch. 16 claim. Until that
runs, the number below is a workflow demonstration, not a generalisation result.

What T0.1c changed: training labels are now drawn only from training-role
blocks, and metrics are reported per role. Previously labels were sampled from
anywhere in the scene and scored everywhere, so neighbouring pixels of a
training sample -- highly autocorrelated at 25 m -- dominated the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline.blocks import ROLE_CODES, BlockAssignment
from geoai_runner.realpipeline.metrics import DEFAULT_MIN_POSITIVE, binary_mask_metrics
from geoai_runner.realpipeline.raster_io import read_geotiff


class EmbeddingError(RuntimeError):
    """Raised when a few-shot configuration is unsafe or unsatisfiable."""


@dataclass
class EmbeddingClassifierResult:
    """Outputs of the few-shot embedding classifier."""

    predicted_mask: np.ndarray
    metrics: dict[str, object]
    artifact: Path | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)


def _local_embedding(stack: np.ndarray) -> np.ndarray:
    """Build a per-pixel feature vector: bands + 3x3 mean + NDWI (texture proxy)."""

    bands = stack.astype("float32")
    feats = [bands]
    mean3 = np.zeros_like(bands)
    for b in range(bands.shape[0]):
        a = np.pad(bands[b], 1, mode="edge")
        acc = np.zeros_like(bands[b])
        for dy in range(3):
            for dx in range(3):
                acc += a[dy : dy + bands.shape[1], dx : dx + bands.shape[2]]
        mean3[b] = acc / 9.0
    feats.append(mean3)
    ndwi = (bands[1] - bands[3]) / (bands[1] + bands[3] + 1e-6)  # green-NIR
    feats.append(ndwi[None])
    stacked = np.concatenate(feats, axis=0)  # (F, H, W)
    return np.transpose(stacked, (1, 2, 0)).reshape(-1, stacked.shape[0])


def few_shot_flood_classifier(
    feature_stack_path: str | Path,
    reference_mask_path: str | Path,
    output_path: str | Path,
    assignment: BlockAssignment,
    *,
    n_labels_per_class: int = 40,
    seed: int = 42,
    min_positive: int | None = DEFAULT_MIN_POSITIVE,
    roles: tuple[str, ...] = ("train", "val", "test"),
) -> EmbeddingClassifierResult:
    """Fit a lightweight classifier on a handful of training-role labels.

    Labels are drawn exclusively from ``train`` blocks. The classifier then
    predicts over the whole scene, and metrics are reported per role so the
    held-out (``test``) number is the one that carries meaning.
    """

    # Configuration is validated before the heavy import so a misconfigured run
    # fails immediately with a useful message instead of after loading sklearn.
    stack, _, _ = read_geotiff(feature_stack_path)
    ref, _, _ = read_geotiff(reference_mask_path)
    ref = ref[0].astype("uint8")
    shape = ref.shape
    if assignment.role_grid.shape != shape:
        raise EmbeddingError(
            f"assignment grid {assignment.role_grid.shape} does not match reference {shape}."
        )
    for role in roles:
        if role not in ROLE_CODES:
            raise EmbeddingError(f"unknown role {role!r}.")
    if not assignment.mask("train").any():
        raise EmbeddingError("the training role is empty; no labels can be drawn.")

    try:
        from sklearn.ensemble import RandomForestClassifier
    except Exception as exc:  # pragma: no cover
        raise EmbeddingError("scikit-learn is required for the embeddings demo.") from exc

    features = _local_embedding(stack)
    labels = ref.reshape(-1)
    train_selector = assignment.mask("train").reshape(-1)

    rng = np.random.default_rng(seed)
    pos_idx = np.flatnonzero((labels == 1) & train_selector)
    neg_idx = np.flatnonzero((labels == 0) & train_selector)
    n = min(n_labels_per_class, len(pos_idx), len(neg_idx))
    if n == 0:
        raise EmbeddingError(
            "the training role contains no positive or no negative pixels; a "
            "few-shot classifier cannot be fitted from it."
        )
    train_idx = np.concatenate(
        [rng.choice(pos_idx, n, replace=False), rng.choice(neg_idx, n, replace=False)]
    )

    clf = RandomForestClassifier(n_estimators=60, max_depth=12, random_state=seed, n_jobs=1)
    clf.fit(features[train_idx], labels[train_idx])
    pred = clf.predict(features).reshape(shape).astype("uint8")

    metrics_by_role = {
        role: binary_mask_metrics(
            pred, ref, mask=assignment.mask(role), min_positive=min_positive, counts=True
        )
        for role in roles
    }
    metrics: dict[str, object] = {
        "metrics_by_role": metrics_by_role,
        "headline_role": "test",
        "n_training_labels": int(2 * n),
        "labels_drawn_from_role": "train",
        "partition": assignment.to_dict(),
        # The two limits named in the module docstring, machine-readable so a
        # downstream surface cannot present this as a generalisation result.
        "feature_contains_target_inputs": True,
        "is_foundation_model_embedding": False,
        "is_cross_district_transfer": False,
        "assumptions": (
            "Few-shot Random Forest on locally-computed spectral+texture features "
            "(a stand-in for downloaded Clay/AlphaEarth/TESSERA embeddings). The "
            "feature vector contains green and SWIR1, which are the same bands the "
            "MNDWI target is derived from, so this measures index re-derivation, "
            "not few-shot generalisation. Labels are drawn only from training-role "
            "blocks and the headline metric is the held-out test role. The Ch. 16 "
            "claim requires real embeddings evaluated on a different district."
        ),
    }
    result = EmbeddingClassifierResult(predicted_mask=pred, metrics=metrics)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd

        rows, cols = np.indices(shape)
        pd.DataFrame(
            {
                "row": rows.ravel()[::37],
                "col": cols.ravel()[::37],
                "role": assignment.role_grid.ravel()[::37],
                "predicted_flood": pred.ravel()[::37],
                "reference_flood": ref.ravel()[::37],
            }
        ).to_parquet(output_path, index=False)
        result.artifact = output_path
        result.artifacts["samples"] = output_path
    except Exception:  # pragma: no cover - parquet optional
        result.artifact = None
    return result
