# Mae Sai Weak-Reference Sentinel-1 Baseline

Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated.

## Data Status

- Sentinel-1 pre/post source files were read from local paths outside Git.
- The reference layer is a manually digitized weak-reference candidate.
- Official Mae Sai validation and ML-label gates remain blocked.

## Source Products

- Pre-event Sentinel-1 product id: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product id: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Reference candidate id: `MANUAL-QGIS-MAE-SAI-2024`
- Source timestamp: 2024-09-15T23:16:01Z

## Method Assumptions

- VV/VH amplitude samples are converted to dB using `10 * log10(value)`.
- `vv_drop` and `vh_drop` are pre-event dB minus post-event dB.
- Ratios are post-event amplitude divided by pre-event amplitude.
- Combined change score weights VH at 0.60 and VV at 0.40.
- SAFE GCPs are fit to an affine transform for this first weak-reference clip.

## Candidate Metrics

- IoU: 0.006079
- F1/Dice: 0.012085
- Precision: 0.038494
- Recall: 0.007167
- Area error ratio: -0.813809
- Sample pixels: 65536
- Reference positive pixels: 12557
- Predicted positive pixels: 2338

## Failure Modes

- SAR layover and terrain shadow can look water-like.
- Permanent water can be confused with event flooding.
- Urban double-bounce can hide or invert flood signals.
- The manual mask is uncertain and intentionally conservative.
- Pre/post acquisition dates may not match peak flood extent.
- This first extractor is not terrain-corrected beyond SAFE GCP approximation.

## Safety Note

- Not official.
- Not real-time.
- Not field validated.
- Not an emergency warning.
