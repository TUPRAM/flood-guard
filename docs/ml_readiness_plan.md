# ML Readiness Plan

Status as of 2026-07-20: not ready for a new qualified real-data ML experiment. FloodGuard now has an active checksum-bound original-SAFE source pair and a deterministic cross-border weak-reference baseline, but it still lacks an authorized ML-label reference, reviewer-calibration evidence, and immutable qualified holdouts. THEOS-2 remains optical context only.

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

Current status: source pair locked, qualified-label processing still blocked. Mae Sai's active pair is the same-track original-SAFE pre-event product `aaaef3af-fa49-4115-bf0f-f54175e7aedf` and post-event product `5251b74b-0bbd-4365-9eb4-fa33292e175a`; both external archives are checksum-bound. The former September 6 / September 15 COG pair is retired provenance only. The local hackathon Sentinel-1 TIFF remains `candidate_role=unresolved` and `event_timing_status=timing_unresolved`, so it cannot replace the active pair.

## Gate 3 - Source Files Are Tracked Outside The Repo

Required before ML:

- downloaded imagery and masks are stored outside Git, or in a controlled data workspace
- file paths, checksums, product IDs, and acquisition commands are documented
- the ingestion manifest changes from `metadata_only` only after license and geometry gates pass
- binary imagery outputs remain excluded from repository commits

Current status: blocked for qualified flood-reference processing. The active Sentinel-1 archives and cross-border manual reference are checksum-tracked outside Git, but the manual reference does not overlap the Thailand ADM3 candidate geometry and explicitly disallows unqualified ML-label use. THEOS-2 selected files have checksum-backed optical-context preview scope only and remain `reference_mask_status=not_reference_mask`.

## Gate 4 - Baseline Non-ML Flood Mapping Is Reproducible

Required before supervised ML:

- deterministic baseline exists for Sentinel-1 pre/post change detection
- candidate features are documented, such as VV/VH backscatter difference, ratio, texture proxy, slope, elevation, and permanent-water mask
- baseline validation reports IoU, F1/Dice, precision, recall, area error, and calibration caveats

Current status: a deterministic non-ML candidate baseline has run from the active checksum-bound original-SAFE pair against the nearby cross-border manual weak reference. This proves the extraction and metric pipeline only; it is not in-area Mae Sai accuracy and does not clear qualified validation or ML-label gates.

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
