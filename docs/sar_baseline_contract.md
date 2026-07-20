# SAR Baseline Contract

This contract defines the non-ML Sentinel-1 flood-mapping baseline that must remain available before any qualified real-data ML experiment. FloodGuard now has both a synthetic fixture lane and a checksum-bound, non-operational weak-reference candidate lane.

## Status

Current status: the synthetic baseline, gated qualified-data entry point, local Sentinel-1 provenance resolver, direct raster extractor, and weak-reference candidate baseline are implemented. The active candidate run reads the selected original-SAFE pre/post pair and manual reference GeoPackage outside Git, verifies their recorded identities and SHA-256 checksums before raster access, and publishes only derived CSV/Markdown evidence.

That candidate lane is calibration evidence only. Its manual geometry is cross-border and does not overlap the Thailand ADM3 reporting polygons; its metrics are not qualified Mae Sai accuracy, field validation, ML labels, or permission to feed a decision layer. Qualified/official processing remains blocked until acquisition authority, reference permitted uses, reviewer qualification, immutable spatial holdouts, and promotion-policy gates pass.

The gated entry point is `run_gated_real_sar_change_baseline`. It accepts a pre-extracted pixel/object table only after `outputs/mae_sai_real_data_file_manifest.csv` has ready rows for:

- reference flood mask for validation
- pre-event SAR source for non-ML baseline
- post-event SAR source for non-ML baseline

This does not bypass raster/file gates and does not train ML. The separate `weak_reference_baseline` path accepts only the explicit weak-reference status and still requires source identity, checksums, timing, geometry, and candidate-use disclosures.

When real-data provenance is supplied, the same entry point also validates `outputs/sentinel1_provenance_resolved_manifest.csv`. Unresolved rows with `candidate_role=unresolved`, `event_timing_status=timing_unresolved`, or `processing_allowed=False` must be rejected before the baseline can run.

## Purpose

The SAR baseline is the bridge between real flood evidence and the existing FloodGuard decision layer. It should eventually produce a flood probability or binary flood extent that can feed:

- subdistrict flood likelihood
- exposure
- road-disruption probability
- access loss
- Evacuation Equity Gap
- FPPS scoring
- dashboard and action briefs

## Qualified Real-Data Inputs

One row or pixel/object record should ultimately include:

- `pixel_id` or stable cell/object id
- `row`
- `col`
- `pre_vv_db`
- `post_vv_db`
- `pre_vh_db`
- `post_vh_db`
- `reference_flood_extent`
- source product ids for pre-event and post-event Sentinel-1 data
- reference-mask source id
- source timestamp
- assumptions

A qualified implementation must use one locked pre/post Sentinel-1 pair and one legally usable, reviewer-qualified flood reference mask with immutable spatial partitions. The current candidate pair is locked, but the manual cross-border reference does not meet the qualified-mask contract.

## Current Weak-Reference Candidate

The candidate implementation lives in `src/floodguard/sar_raster_extract.py` and `src/floodguard/weak_reference_baseline.py`. It writes:

- `outputs/mae_sai_weak_sar_feature_manifest.csv`;
- `outputs/mae_sai_weak_baseline_metrics.csv`; and
- `outputs/mae_sai_weak_baseline_summary.md`.

The inspected GDAL SAFE view supplies uncalibrated Sentinel-1 amplitude. FloodGuard applies the explicit `20 * log10(amplitude)` transform and records `sentinel1_uncalibrated_amplitude`, `20_log10_amplitude`, and `not_sigma0_beta0_or_gamma0_calibrated` in the output contract. The result must not be described as calibrated backscatter in dB.

## Synthetic Fixture Inputs

The current fixture uses `tests/fixtures/sample_sar_pixels.csv` with:

- `pixel_id`
- `row`
- `col`
- `pre_vv_db`
- `post_vv_db`
- `pre_vh_db`
- `post_vh_db`
- `reference_flood_extent`

## Non-ML Baseline Formula

The synthetic baseline computes:

```text
vv_drop_db = pre_vv_db - post_vv_db
vh_drop_db = pre_vh_db - post_vh_db
combined_drop_db = 0.60 * vv_drop_db + 0.40 * vh_drop_db
flood_probability_0_1 = clamp((combined_drop_db - dry_change_db) / (flood_change_db - dry_change_db), 0, 1)
binary_flood_extent = flood_probability_0_1 >= probability_threshold
```

Default fixture parameters:

- `dry_change_db = 0.5`
- `flood_change_db = 4.0`
- `probability_threshold = 0.5`

This is a toy threshold baseline, not a production flood detector.

## Required Outputs

`outputs/sample_sar_baseline.csv`:

- `pixel_id`
- `row`
- `col`
- `vv_drop_db`
- `vh_drop_db`
- `combined_drop_db`
- `flood_probability_0_1`
- `binary_flood_extent`
- `reference_flood_extent`
- `confidence_class`
- `assumptions`

`outputs/sample_sar_validation_metrics.csv`:

- `true_positive`
- `false_positive`
- `false_negative`
- `true_negative`
- `iou`
- `f1_dice`
- `precision`
- `recall`
- `area_error_ratio`

## Validation Metrics

The baseline must report:

- IoU
- F1/Dice
- precision
- recall
- area error ratio

The same metric definitions are used for synthetic tests and the completed weak-reference candidate calibration. The published candidate metrics remain non-operational and non-qualified. Real Mae Sai validation remains blocked until the reference-mask authority, permitted-use, reviewer, spatial-holdout, and promotion gates are cleared.

## Non-Goals

- No source raster, SAFE, ZIP, GeoPackage, or model-weight files committed to Git.
- No claim that the weak-reference calibration measures qualified Mae Sai accuracy.
- No deep learning model.
- No operational warning claim.
- No replacement for official flood products or local agency judgment.
