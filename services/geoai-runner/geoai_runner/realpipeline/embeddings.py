"""Component F -- Label-scarce generalization via satellite embeddings.

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 16 "Satellite Embeddings". The
book's workflow: instead of training a network from raw pixels, reuse a
foundation model's precomputed embedding per location and fit a lightweight
classifier (k-NN, Random Forest, logistic regression) on a handful of labels.

Honest scope for this offline build: real embeddings (Clay / AlphaEarth /
TESSERA) must be downloaded from Hugging Face / Earth Engine, which is not
possible here. To still demonstrate the *few-shot classifier* half of the
workflow, we compute a local per-pixel feature vector (spectral bands + simple
neighbourhood texture) as a stand-in "embedding" and fit a Random Forest on a
handful of labelled pixels. The published caveat (Kaushik et al., 2026) that
foundation models trail on SAR vs optical is carried in the registry and
proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from geoai_runner.realpipeline.raster_io import read_geotiff


@dataclass
class EmbeddingClassifierResult:
    predicted_mask: np.ndarray
    metrics: dict[str, float]
    artifact: Path | None = None


def _local_embedding(stack: np.ndarray) -> np.ndarray:
    """Build a per-pixel feature vector: bands + 3x3 mean + local std (texture)."""

    bands = stack.astype("float32")
    feats = [bands]
    # Cheap neighbourhood statistics as texture features.
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
    *,
    n_labels_per_class: int = 25,
    seed: int = 42,
) -> EmbeddingClassifierResult:
    """Fit a lightweight classifier on a handful of labels (few-shot demo)."""

    try:
        from sklearn.ensemble import RandomForestClassifier
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for the embeddings demo.") from exc

    stack, _, _ = read_geotiff(feature_stack_path)
    ref, _, _ = read_geotiff(reference_mask_path)
    ref = ref[0].astype("uint8")
    shape = ref.shape

    features = _local_embedding(stack)
    labels = ref.reshape(-1)

    rng = np.random.default_rng(seed)
    pos_idx = np.flatnonzero(labels == 1)
    neg_idx = np.flatnonzero(labels == 0)
    n = min(n_labels_per_class, len(pos_idx), len(neg_idx))
    train_idx = np.concatenate(
        [rng.choice(pos_idx, n, replace=False), rng.choice(neg_idx, n, replace=False)]
    )

    clf = RandomForestClassifier(n_estimators=60, max_depth=12, random_state=seed, n_jobs=1)
    clf.fit(features[train_idx], labels[train_idx])
    pred = clf.predict(features).reshape(shape).astype("uint8")

    metrics = _mask_metrics(pred, ref)
    metrics["n_training_labels"] = int(2 * n)
    metrics["assumptions"] = (
        "Few-shot classifier on locally-computed feature vectors (stand-in for "
        "downloaded foundation-model embeddings). Demonstrates the Ch. 16 few-shot "
        "workflow; real Clay/AlphaEarth/TESSERA embeddings require network access."
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd

        rows, cols = np.indices(shape)
        pd.DataFrame(
            {
                "row": rows.ravel()[::37],
                "col": cols.ravel()[::37],
                "predicted_flood": pred.ravel()[::37],
                "reference_flood": ref.ravel()[::37],
            }
        ).to_parquet(output_path, index=False)
        artifact = output_path
    except Exception:  # pragma: no cover - parquet optional
        artifact = None

    return EmbeddingClassifierResult(predicted_mask=pred, metrics=metrics, artifact=artifact)


def _mask_metrics(predicted: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    p = predicted.astype(bool).ravel()
    r = reference.astype(bool).ravel()
    tp = int(np.sum(p & r)); fp = int(np.sum(p & ~r)); fn = int(np.sum(~p & r))

    def ratio(a, b):
        return round(a / b, 4) if b else 0.0

    return {
        "iou": ratio(tp, tp + fp + fn),
        "f1_dice": ratio(2 * tp, 2 * tp + fp + fn),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
    }
