# Model card: FloodGuard GeoAI synthetic integration proof

## Identity and status

- Model/run role: synthetic integration proof.
- Model ID: `floodguard/synthetic-unet`.
- Model revision: `contract-proof-1`.
- Architecture: two-class U-Net.
- Encoder: ResNet-34.
- Encoder weights: `None`.
- GeoAI package: `geoai-py==0.41.1`.
- GeoAI source receipt: `6833c8b71fb18f5b8ea17d5d9f8e0745157643c2`
  as the declared reviewed source reference.
- Python: 3.12 isolated service environment.
- Dataset mode: `candidate`.
- Operational status: `non_operational`.
- Official warning: `false`.
- Processing scope: synthetic integration only.
- Decision-layer eligibility: `false`.

> Synthetic integration proof; not evidence of real flood-detection accuracy.

The source receipt is declared from the reviewed GeoAI source package. The
PyPI version and lockfile prove package resolution but do not independently
prove a Git commit-specific wheel.

## Intended use

The proof tests the integration contract between a georeferenced multiband
feature raster, GeoAI tile export/model inference, explicit binary class-1
probability, and FloodGuard report-only aggregation. It helps reviewers confirm
that the proposed GeoAI workflow is concrete and reproducible.

It is not intended for:

- operational flood detection;
- public warnings or evacuation advice;
- official or field validation;
- accuracy comparison with the deterministic or weak-label lanes;
- FPPS, action-class, road-closure, or facility decisions; or
- promotion to `official_input`.

## Inputs and preprocessing

The proof uses a temporary georeferenced eight-band synthetic raster:

1. `pre_vv_db`;
2. `post_vv_db`;
3. `pre_vh_db`;
4. `post_vh_db`;
5. `vv_change_db`;
6. `vh_change_db`;
7. `slope_degrees`; and
8. `permanent_water_flag`.

The preprocessing ID is `clip_linear_uint8_v1`. Each physical band has a
frozen minimum, maximum, unit and description. Values are clipped, linearly
encoded to `uint8 [0,255]`, and bound to a SHA-256 sidecar. Training and
inference must re-hash and use the same sidecar. This prevents raw negative SAR
dB, DEM, HAND or slope values from passing through GeoAI's stock scaling
without an auditable transformation.

The label contract is `0 = non-flood`, `1 = flood`, `255 = nodata`. Feature and
mask grids must match exactly in CRS, transform, dimensions, resolution and
bounds.

## Executed proof boundary

The opt-in smoke executes actual calls to:

- `geoai.utils.training.export_geotiff_tiles`; and
- `geoai.inference.predict_geotiff`.

It also calls GeoAI model construction, uses `encoder_weights=None`, packages a
checksum-bound model state, reopens and validates exported label tiles, and
performs explicit softmax class-1 extraction. It partitions georeferenced tiles
into training and untouched holdout groups and rejects boundary-crossing tiles.

The runner contains and tests a guarded wrapper for
`geoai.train.train_segmentation_model`, including `ignore_index=255` and
prepared-manifest binding. The current real smoke does not execute an
optimization/training epoch; `training_execution` is therefore
`model_construction_only`.

## Output contract

The probability result is one `float32` band named
`flood_probability_0_1`, with `-9999` nodata and valid values constrained to
`[0,1]`. Validation covers:

- CRS;
- transform;
- resolution, shape and bounds;
- nodata;
- class mapping;
- finite probability range; and
- provenance tags and lineage checksums.

Large rasters, tiles and weights stay in a temporary/external workspace. The
repository may retain only a path-redacted receipt, a small thumbnail,
histogram data and checksums.

## Evaluation and metrics

No synthetic IoU, Dice/F1, precision, recall, area error, Brier score or
calibration value is accepted as evidence of flood accuracy. Random model
outputs and fixture-perfect contract values are excluded from proposal
performance claims.

Real evaluation requires:

- licensed and product-identified pre/post Sentinel-1 inputs;
- signed acquisition authority;
- a qualified, temporally aligned reference mask authorized for the model
  purpose;
- passing reviewer calibration;
- immutable spatial holdout polygons and cell membership;
- thresholds fixed before holdout evaluation; and
- complete baseline, weak-label and GeoAI evidence manifests.

Required metrics are IoU, Dice/F1, precision, recall, physical area error,
area-error ratio, Brier score, calibration and threshold sensitivity. Manual
error review covers permanent water, paddy fields, steep terrain,
shadow/layover, urban double-bounce, mixed pixels and timing mismatch.

## Promotion and safety

The proof may be aggregated only through the explicit report-only path. Its
contract sets `can_feed_decision_layer=false` with the reason “Synthetic
candidate proof cannot feed the decision layer.” It cannot change FPPS or an
A-E action class.

For a future decision-eligible raster, the trusted zonal adapter must re-hash
the immutable probability raster and authoritative geometry, validate spatial
and lineage contracts, derive its own zonal statistics, and sign a canonical
receipt. Candidate/fixture sources and any substitution fail closed.

## Reproducibility evidence

- Environment: `services/geoai-runner/pyproject.toml` and `uv.lock`.
- Proof test: `services/geoai-runner/tests/test_geoai_smoke.py`.
- Generated public receipt:
  `services/geoai-runner/evidence/geoai-proof-receipt.json`.
- Probability thumbnail:
  `services/geoai-runner/evidence/geoai-probability-thumbnail.png`.
- Runner documentation: `services/geoai-runner/README.md`.

Exact pass counts belong in the final proposal evidence manifest after the
last clean verification run.
