# Mae Sai Weak-Reference Sentinel-1 Baseline

Cross-border calibration metrics against a manually digitized weak-reference mask; not Mae Sai Thailand ADM3 validation. Non-operational. Not official validation. Not field validated.

## Data Status

- Sentinel-1 pre/post source files were read from local paths outside Git.
- The reference layer is a manually digitized cross-border calibration candidate.
- It does not overlap Mae Sai Thailand ADM3 geometry and is not a Mae Sai validation mask.
- Official Mae Sai validation and ML-label gates remain blocked.

## Source Products

- Pre-event Sentinel-1 product id: `aaaef3af-fa49-4115-bf0f-f54175e7aedf`
- Post-event Sentinel-1 product id: `5251b74b-0bbd-4365-9eb4-fa33292e175a`
- Reference candidate id: `MS-MANUAL-CROSSBORDER-001`
- Source timestamp: 2024-09-15T23:16:01Z
- Input integrity: verified_sha256_before_raster_read
- Measurement domain: sentinel1_uncalibrated_amplitude
- Log transform: 20_log10_amplitude
- Radiometric calibration: not_sigma0_beta0_or_gamma0_calibrated
- Pre-event SHA-256: `42433d6cfb55118abe21e6faabef56343cefc9f28817cd31eb9386d32f56543d`
- Post-event SHA-256: `ff4a604f57c9eb88421904659c7201d07b54b35a3bff6f3447ee548c40f6755b`
- Reference SHA-256: `d64e8441dd08ce42323ae283398e5dc1a7225282caa040d0f5981b3a9c8637ce`
- Reference spatial relation: cross_border_calibration_only
- In-study-area overlap: False
- Distance to study area: 5.965 km

## Method Assumptions

- VV/VH samples are uncalibrated amplitude, converted using `20 * log10(amplitude)`.
- These values are not calibrated Sigma0, Beta0, or Gamma0 backscatter.
- `vv_drop` and `vh_drop` are pre-event dB minus post-event dB.
- Ratios are post-event amplitude divided by pre-event amplitude.
- Combined change score weights VH at 0.60 and VV at 0.40.
- SAFE GCPs are fit to an affine transform for this first weak-reference clip.

## Candidate Metrics

- IoU: 0.086835
- F1/Dice: 0.159795
- Precision: 0.188113
- Recall: 0.138887
- Area error ratio: -0.261687
- Sample pixels: 65536
- Reference positive pixels: 12557
- Predicted positive pixels: 9271

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
