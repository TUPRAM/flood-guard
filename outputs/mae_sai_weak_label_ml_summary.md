# Mae Sai Historical Weak-Label ML Experiment (Retired Source Pair)

Weak-label experiment against manually digitized weak-reference mask. Non-operational. Not official labels. Not field validation. Ineligible for the decision layer, FPPS, action classes, or warnings.

## Data Status

- Artifact status: historical retired-source screening evidence only.
- The experiment used the retired September 6 / September 15 COG pair.
- It is not comparable to the active same-track original-SAFE baseline and must not be regenerated as current evidence.
- Labels come from the manual weak-reference mask, not official labels.
- This is not field validation and not an emergency warning.

## Model

- Model family: logistic_regression_from_scratch
- Features: vv_drop|vh_drop|vv_ratio|vh_ratio|combined_sar_change_score
- Split strategy: spatial_block_holdout
- Train samples: 49152
- Holdout samples: 16384
- Decision threshold: 0.440

## Baseline Comparison

| Metric | Non-ML baseline | Weak-label ML | Delta |
| --- | ---: | ---: | ---: |
| IoU | 0.004681 | 0.223282 | +0.218601 |
| F1/Dice | 0.009318 | 0.365054 | +0.355736 |
| Precision | 0.024963 | 0.235426 | +0.210463 |
| Recall | 0.005728 | 0.812332 | +0.806604 |
| Area error ratio | -0.770553 | 2.450472 | +3.221025 |

## Hard Safety Boundary

- ML improves baseline: True
- ML complements baseline: True
- Can feed candidate decision layer: False
- The ML probability is not eligible to feed the decision layer, FPPS, action classes, or warnings. Baseline improvement does not override weak-label provenance.

## Source Products

- Pre-event Sentinel-1 product id: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product id: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Reference candidate id: `MANUAL-QGIS-MAE-SAI-2024`
- Reference status: weak_reference_candidate
- Source timestamp: 2024-09-15T23:16:01Z

## Safety Note

- Weak-label experiment.
- Not official labels.
- Not field validation.
- Not official flood validation.
- Not an emergency warning.
