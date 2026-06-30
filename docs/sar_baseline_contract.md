# SAR Baseline Contract

This contract defines the first non-ML Sentinel-1 flood-mapping baseline that must exist before any real-data ML experiment. The current implementation is synthetic and fixture-backed only.

## Status

Current status: synthetic baseline implemented; real Sentinel-1 processing not implemented.

The repository must not download Sentinel-1 products, read raster imagery, or generate real flood masks until licensing, reference-mask, local-path, and checksum gates pass in the ingestion manifest.

## Purpose

The SAR baseline is the bridge between real flood evidence and the existing FloodGuard decision layer. It should eventually produce a flood probability or binary flood extent that can feed:

- subdistrict flood likelihood
- exposure
- road-disruption probability
- access loss
- Evacuation Equity Gap
- FPPS scoring
- dashboard and action briefs

## Future Real-Data Inputs

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

The first real implementation should use one locked pre/post Sentinel-1 pair and one legally usable flood reference mask.

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

These metrics are computed on synthetic masks now. Real validation remains blocked until the reference-mask licensing and ingestion gates are cleared.

## Non-Goals

- No real Sentinel-1 downloads.
- No raster IO.
- No deep learning model.
- No operational warning claim.
- No replacement for official flood products or local agency judgment.

