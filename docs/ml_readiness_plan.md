# ML Readiness Plan

Status as of 2026-07-03: not ready for real-data ML yet. FloodGuard is ready to plan, catalog, gate real data, and use THEOS-2 as optical context, but not to train or run a flood-mapping model on real imagery.

## Readiness Gates

## Gate 1 - Reference Mask Is Legally Usable

Required before ML:

- at least one flood reference mask has confirmed geometry access
- license terms allow local analysis
- redistribution or reference-only status is documented
- citation and disclaimer requirements are recorded

Current status: blocked. UNOSAT/UNITAR and GISTDA requests were reported sent on 2026-07-03, but provider responses, geometry access, and redistribution/reference-only terms are unresolved.

## Gate 2 - Sentinel-1 Pair Is Locked

Required before ML:

- pre-event and post-event Sentinel-1 products selected from the CDSE metadata inventory
- flood peak date or reference-mask date is confirmed
- product storage type and acquisition timing are documented
- metadata snapshot review checklist is complete if a live snapshot is committed

Current status: partially planned. Mae Sai has a provisional CDSE pre/post COG pair, but the final post-event choice depends on the reference-mask date. The local hackathon Sentinel-1 TIFF has checksum-backed readiness metadata, but `outputs/sentinel1_provenance_resolved_manifest.csv` currently labels it `candidate_role=unresolved` and `event_timing_status=timing_unresolved`; it cannot replace the locked CDSE pair yet.

## Gate 3 - Source Files Are Tracked Outside The Repo

Required before ML:

- downloaded imagery and masks are stored outside Git, or in a controlled data workspace
- file paths, checksums, product IDs, and acquisition commands are documented
- the ingestion manifest changes from `metadata_only` only after license and geometry gates pass
- binary imagery outputs remain excluded from repository commits

Current status: blocked for flood-reference processing. The current ingestion skeleton intentionally refuses imagery/product output paths. THEOS-2 selected files have checksum-backed optical-context preview scope only and remain `reference_mask_status=not_reference_mask`.

## Gate 4 - Baseline Non-ML Flood Mapping Is Reproducible

Required before supervised ML:

- deterministic baseline exists for Sentinel-1 pre/post change detection
- candidate features are documented, such as VV/VH backscatter difference, ratio, texture proxy, slope, elevation, and permanent-water mask
- baseline validation reports IoU, F1/Dice, precision, recall, area error, and calibration caveats

Current status: gated entry point added. `run_gated_real_sar_change_baseline` can run the non-ML SAR formula on a pre-extracted pixel/object table only after Mae Sai file-level and Sentinel-1 provenance gates pass. Direct Sentinel-1 raster extraction remains blocked.

The non-ML baseline remains the required benchmark before any supervised flood model is trained.

## Gate 5 - First ML Experiment Is Scoped

Start ML only after Gates 1-4 pass. The first model should be deliberately small:

- input: one selected Sentinel-1 pre/post pair plus a legally usable reference mask
- baseline: threshold or rule-based SAR change detector
- first ML candidate: lightweight tabular classifier on pixel/object features
- validation: hold out spatial tiles or polygons; report IoU, F1/Dice, precision, recall, area error, and false positives around permanent water and radar shadow
- output: flood probability or binary extent that feeds the existing decision layer

Do not start with a deep model. The project risk is not model ambition; it is whether the reference labels, licensing, and validation evidence are strong enough.

## What ML Will Feed

The ML output is only one upstream input. It should produce a flood probability or extent layer that can drive:

- subdistrict flood likelihood
- exposed population and facilities
- road-disruption probability
- access loss
- Evacuation Equity Gap
- Flood Preparedness Priority Score
- dashboard and action briefs

The decision layer already exists in fixture form. The real-data ML milestone is ready when it can replace fixture flood probability with a documented, validated real flood layer.

## Immediate Next ML-Adjacent Work

1. Log UNOSAT/UNITAR and GISTDA replies using `docs/provider_response_logging_guide.md`.
2. Complete `docs/live_metadata_snapshot_review_checklist.md` before committing any live CDSE snapshot.
3. Confirm a redistributable or reference-only Mae Sai 2024 flood mask.
4. Lock the Mae Sai pre/post Sentinel-1 pair against the reference-mask date.
5. Add local storage paths and checksum fields in `outputs/mae_sai_real_data_file_manifest.csv`, still without model code.
6. Generate `outputs/mae_sai_validation_summary.md` and keep it blocked until real metrics exist.
