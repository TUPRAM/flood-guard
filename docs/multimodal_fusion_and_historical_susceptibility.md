# Multimodal Fusion And Historical Susceptibility

Status: engineering contracts, fail-closed gates, synthetic fixtures, dashboard integration, and tests are implemented. Real encoder training, calibration, and claims of improved precision or boundary quality remain blocked by event-aligned imagery, rights-cleared labels, and held-out Thai evaluation data.

FloodGuard remains a preparedness and rapid post-event prioritization tool. Neither pathway in this document is an official warning system.

## Evidence Boundaries

- Sentinel-1 remains the event-time fallback. Missing or ineligible optical evidence must not change its probability.
- `SAR + optical` means that an optical encoder probability passed the declared fusion gates. It does not mean that the optical image is flood truth.
- THEOS-2 metadata or contextual features are not pixel-level fusion inputs.
- `Historical susceptibility/context` is static or seasonally refreshed plausibility context. It is not observed current flooding and it is not a forecast.
- Historical context can raise a verification warning. It cannot replace or silently rescore event-time SAR evidence, FPPS, or an action class.

## Sentinel-2 Optical Features

`src/floodguard/optical_features.py` accepts already calibrated and co-registered Sentinel-2 Level-2A tabular pixel rows. Upstream ingestion remains responsible for reading the source rasters, checking provenance, reprojecting to the declared grid, and proving pre/event alignment.

Required pre/event inputs are B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12, the Scene Classification Layer, cloud distance, grid and pixel identifiers, source timestamps, confidence, and assumptions. Sentinel-2 Level-2A is the atmospherically corrected surface-reflectance product and includes SCL; band resolution varies between 10 m, 20 m, and 60 m, so a real pipeline must declare its resampling policy. See the [official Sentinel-2 product documentation](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel2.html).

The feature builder preserves raw input columns for lineage and emits separate cloud-masked band columns. Only the `*_masked` bands, valid indices, and valid changes belong in the optical encoder contract. It emits:

- cloud-masked pre/event reflectance and change for every required band;
- NDWI, MNDWI, NDVI, and shadow-oriented AWEIsh;
- pre/event index changes;
- phase and combined optical-valid flags;
- stable SCL, cloud-distance, and denominator reason codes;
- source timestamp, confidence, assumptions, schema version, and the explicit `not_flood_truth` status.

SCL classes 0, 1, 3, 7, 8, 9, 10, and 11 are masked, including unclassified pixels. A configurable cloud-distance floor masks pixels too close to cloud. Zero or near-zero normalized-index denominators fail safe rather than producing infinity.

WorldFloods v2 is documented only as a research/pretraining candidate for the future optical encoder. Its published documentation describes a multi-event Sentinel-2 corpus and a Creative Commons non-commercial license. Exact artifact terms must be reviewed before training, redistribution, or operational use. See the [WorldFloods dataset documentation](https://spaceml-org.github.io/ml4floods/content/worldfloods_dataset.html).

## THEOS-2 Pixel Eligibility

`evaluate_theos2_pixel_eligibility` fails closed unless all of the following are proven:

- actual pixel data exists and the record is not metadata-only;
- radiometric calibration and georeferencing are complete;
- imagery is aligned to the fusion grid;
- acquisition time is inside both the flood-event and label-validity windows;
- model-training permission is explicitly granted.

The current repo THEOS-2 manifests and metadata-derived context features do not satisfy this contract. They remain optical context only. In the synthetic fusion fixture, an ineligible THEOS-2 candidate is retained for audit while an independently eligible Sentinel-2 candidate can still be selected.

## Late-Fusion Contract

`src/floodguard/fusion.py` records separate SAR and optical encoder identifiers and feature lists. Each model-contract instance names exactly one optical source family (`sentinel2` or `theos2`), so a THEOS-2 probability cannot be attributed to a Sentinel-2 band contract. It combines already-produced probabilities only after modality-specific encoding. This module does not train either encoder.

The synthetic demonstration uses a 0.65 SAR / 0.35 optical weighted probability average and records a 0.30 optical-branch modality dropout training contract. SAR is never dropped. These are fixture parameters, not fitted production parameters.

The fixture quality policy is:

| Gate | Limit |
| --- | --- |
| Cloud plus shadow fraction | at most 0.35 |
| Absolute temporal offset | at most 72 hours |
| Valid optical fraction | at least 0.80 |
| Event overlap fraction | at least 0.90 |
| Grid alignment | `aligned_to_sar_grid` |
| Calibration | `calibrated` |
| Provenance | `verified` |
| Model-input rights | `approved_for_model_input` |

THEOS-2 also requires permission, event overlap, temporal alignment, and grid alignment to be individually confirmed.

An eligible THEOS-2 path additionally requires its own `theos2` optical encoder identifier and feature contract. A Sentinel-2 contract fails closed on a THEOS-2 candidate even when the imagery-quality gates pass.

When no candidate passes, the fusion-candidate mode is exactly `SAR only`. The output probability is copied from the SAR probability without arithmetic, and IEEE-754 bytes are checked for equality. When a candidate passes, the mode is exactly `SAR + optical`. Every row records `decision_layer_use_status=research_sidecar_not_used_by_fpps`, the selected candidate, fallback reason, quality policy and model-contract hashes, source timestamp, confidence, assumptions, and an explicit no-improvement-claim statement.

Validation is separated into:

- all SAR rows;
- SAR on the optical-eligible paired subset;
- optical-only on that same paired subset;
- fused operation on that same paired subset.

The generated fixture metrics are descriptive tests of the evaluation contract. They must not be cited as evidence that fusion improves real flood mapping.

## Historical Susceptibility Features

`src/floodguard/historical_susceptibility.py` accepts normalized 0-1 aggregate features for:

- Global Flood Database event history;
- JRC water occurrence, seasonality, and change;
- elevation and slope susceptibility derived from Copernicus DEM;
- flood-prone land-cover context derived from WorldCover;
- river proximity and drainage density;
- catchment wetness and soil runoff potential;
- rainfall climatology.

The [Global Flood Database catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1) describes 913 events from 2000 through 2018 at MODIS scale, approximately 250 m, under CC BY-NC 4.0. FloodGuard therefore treats it as broad historical context and event discovery, never as 10 m Sentinel-1 truth. JRC occurrence, seasonality, and change layers are historical water context; the exact product version must be recorded. See the [JRC Global Surface Water downloads](https://global-surface-water.appspot.com/download).

## Transparent Baseline And Missing Data

The current baseline is a positive-weight monotonic additive score. It is intentionally labeled `uncalibrated_requires_basin_event_target_corpus`. A production candidate should be a calibrated LightGBM/XGBoost model or an interpretable generalized additive model, but fitting and calibration must wait for rights-cleared targets and complete event/basin holdouts.

Default weights are:

| Normalized feature | Weight |
| --- | ---: |
| Global flood history | 0.18 |
| JRC water occurrence | 0.14 |
| JRC water seasonality | 0.06 |
| JRC water change | 0.04 |
| Elevation susceptibility | 0.11 |
| Slope susceptibility | 0.11 |
| WorldCover flood proneness | 0.08 |
| River proximity | 0.08 |
| Drainage density | 0.05 |
| Catchment wetness | 0.06 |
| Soil runoff potential | 0.04 |
| Rainfall climatology | 0.05 |

Missing features remain missing. Available weights are renormalized per row, the missing feature list and available-weight coverage are emitted, and confidence is downgraded. If available weight is below 0.60, the susceptibility score is withheld rather than treating missing context as zero.

Every output includes the 0-100 score, low/moderate/high class, per-feature contributions, top driver, coverage, missing features, source timestamp, confidence, assumptions, method, calibration status, and these machine-readable boundaries:

- `eligible_as_current_flood=false`
- `eligible_as_forecast=false`
- `eligible_to_replace_event_sar=false`

## Basin/Event Holdouts And Monotonicity

`partition_basin_event_groups` treats basin and event identifiers as a connected bipartite graph. A seeded test or calibration identifier assigns its complete connected component, producing complete connected basin/event groups. Conflicting seeds fail closed. `validate_basin_event_partition` rejects any basin or event found in more than one partition.

`run_monotonicity_checks` perturbs every available normalized susceptibility feature and verifies that its score cannot decrease. The generated fixture emits every check to CSV; all checks must pass before commit.

These checks validate the baseline mechanics. They do not substitute for target calibration, spatial generalization, basin holdouts, event holdouts, class-imbalance analysis, or independent real-data evaluation.

## Current-SAR Conflict Warnings

The default plausibility policy raises a warning when:

- current SAR probability is at least 0.75 while historical susceptibility is at most 35; or
- current SAR probability is at most 0.25 while historical susceptibility is at least 70.

The first warning asks for terrain, radar-shadow, urban-artefact, timing, and provenance review but explicitly says not to discard the current observation automatically. The second says that high susceptibility does not establish current flooding. Missing either side produces `not_evaluated`.

## Dashboard Integration

The selected-unit panel now shows:

- `Research fusion candidate`: `SAR only` or `SAR + optical`, with fallback reason, source time, confidence, and a permanent statement that it is not used by FPPS or action class;
- `Historical susceptibility/context`: score, class, top explanation, and conflict warning;
- the permanent statement `Not observed current flooding. Not a forecast.`

The new values are properties on `outputs/priority_subdistricts.geojson`, so the static dashboard remains backend-free. The GeoJSON uses `fusion_candidate_mode` rather than implying that the current FPPS decision consumed the candidate. These values do not modify `flood_likelihood_0_100`, FPPS, action class, or the scenario calculations.

## Generated Fixture Evidence

- `outputs/sample_sentinel2_optical_features.csv`
- `outputs/sample_optical_fusion_candidate_assessment.csv`
- `outputs/sample_sar_optical_fusion.csv`
- `outputs/sample_sar_optical_fusion_validation.csv`
- `outputs/sample_historical_susceptibility_context.csv`
- `outputs/sample_historical_susceptibility_monotonicity.csv`
- `outputs/sample_historical_basin_event_partitions.csv`
- `outputs/priority_subdistricts.geojson`
- `outputs/dashboard.html`

Regenerate and verify from the repo root:

```powershell
uv run python scripts/generate_sample_decision_outputs.py
uv run pytest
uv run python scripts/smoke_dashboard.py
```

## Remaining Real-Data Gates

Do not claim higher precision, cleaner boundaries, reduced artefacts, calibrated susceptibility, or no real-data degradation until all applicable gates pass:

1. Acquire event- and label-aligned Sentinel-2 Level-2A pixels with declared resampling and cloud policy.
2. Obtain aligned THEOS-2 pixels, calibration, georeferencing, event/label overlap, and explicit training permission.
3. Confirm WorldFloods terms for the intended pretraining and redistribution use.
4. Acquire rights-cleared Thai historical flood targets with event and basin identifiers.
5. Record exact Global Flood Database, JRC, DEM, WorldCover, river, drainage, soil, and rainfall source versions and timestamps.
6. Fit and calibrate the selected model on training groups only.
7. Hold out complete connected basins and events, then report calibration and discrimination by geography, event, season, terrain, land cover, and modality availability.
8. Compare SAR-all, paired SAR, optical-only, and fused operation; prove that the SAR-only fallback is unchanged.
9. Complete independent visual boundary QA and operational review before any stronger wording.
