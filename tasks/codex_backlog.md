# Codex Backlog - FloodGuard Thailand

## Task 01 - Project Scaffold

Create a Python package layout for FloodGuard. Add `pyproject.toml`, `src/floodguard/`, `tests/`, durable docs, and sample fixtures.

Acceptance: `pytest` runs successfully with at least one real scoring test.

## Task 02 - FPPS Scoring

Implement the Flood Preparedness Priority Score from `docs/model_contract.md`.

Acceptance: scoring tests pass and sample output is generated.

## Task 03 - Road-Disruption Probability

Implement a simple road-risk function using:

- flood probability
- road class
- surrounding inundation proxy
- bridge flag if available

Acceptance: outputs segment-level `road_disruption_probability_0_1` from sample fixtures.

## Task 04 - Access-Loss Prototype

Given a road graph, shelters, hospitals, and population points, compare normal versus disrupted access.

Acceptance: outputs people losing 15-, 30-, and 60-minute access from a deterministic sample graph.

## Task 05 - Evacuation Equity Gap

Implement vulnerable versus non-vulnerable access-loss rates and ratio.

Acceptance: handles zero denominators and produces interpretation text.

## Task 06 - Source Registry

Create a source registry before real study-area data ingestion.

Acceptance: documents candidate sources, licensing/access notes, resolution, time coverage, study-area relevance, and confidence notes.

## Task 07 - Action Brief Generator

Generate a Markdown one-page brief for a selected subdistrict.

Acceptance: includes score, class, reasons, confidence, and recommended actions.

## Task 08 - Dashboard-Ready Export

Export priority subdistricts and road-risk segments to GeoJSON.

Acceptance: files open in QGIS or a web-map viewer.

## Task 09 - Validation Report

Generate a simple validation summary with metrics placeholders:

- IoU
- F1/Dice
- precision
- recall
- area error
- score sensitivity

Acceptance: report can be generated from sample fixtures.

## Task 10 - Action Brief Generator

Generate a one-page Markdown action brief for the highest actionable fixture subdistrict.

Acceptance: includes score, action class, top reason, confidence, access loss, equity gap, road risks, assumptions, and recommended actions.

## Task 11 - Scenario Toggle Prototype

Implement fixture-backed `add_temporary_shelter` and `close_road` scenarios.

Acceptance: reruns access loss and equity gap and writes before/after scenario summaries.

## Task 12 - FPPS Sensitivity Analysis

Run deterministic FPPS weight scenarios and flag unstable rankings.

Acceptance: writes sensitivity rows and rank-instability summary from sample fixtures.

## Task 13 - Study-Area Data Inventory

Document real data acquisition needs for Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025.

Acceptance: inventory is source-backed and explicitly avoids real downloads or remote-sensing model work.

## Task 14 - Bilingual Action Brief V2

Add Thai/English section labels and field-ready non-operational wording to the generated one-page action brief.

Acceptance: `outputs/action_brief_FG-TB-001.md` stays compact, keeps class-specific recommended actions, and says it is not an official warning.

## Task 15 - Scenario GeoJSON Comparison

Merge baseline, temporary-shelter, and road-closure comparison fields into `priority_subdistricts.geojson`.

Acceptance: each priority subdistrict has scenario comparison fields before GeoJSON export; missing comparison rows fail clearly.

## Task 16 - Validation Summary V2

Add a sensitivity section to the validation summary.

Acceptance: `outputs/validation_summary.md` reports stable/unstable rank counts, max rank range, and the low-confidence numeric-top disclaimer.

## Task 17 - Static Dashboard Prototype

Generate a standalone Leaflet dashboard from generated GeoJSON and Markdown outputs.

Acceptance: `outputs/dashboard.html` opens from disk, embeds GeoJSON directly, has layer toggles, and requires no backend.

## Task 18 - Chiang Rai Inventory V2

Record exact candidate Sentinel-1 CDSE metadata for the Mae Sai 2024 planning tile.

Acceptance: inventory lists candidate product ids, access/license status, no-download status, and unresolved flood-mask/licensing blockers.

## Task 19 - Dashboard V2 Controls

Add subdistrict selection, A-E filters, scenario mode selection, and scenario-delta highlighting to the standalone dashboard.

Acceptance: `outputs/dashboard.html` remains backend-free, embeds GeoJSON and briefs directly, and updates the panel/map from static JS controls.

## Task 20 - Action Brief V3 Batch

Generate all actionable A/B/C action briefs and include Thai recommended-action text.

Acceptance: default generation writes briefs for FG-TB-001, FG-TB-002, and FG-TB-003 only; D/E remain manual.

## Task 21 - No-Download CDSE Metadata Query

Add reproducible CDSE metadata query helpers and a dry-run capable CLI.

Acceptance: Mae Sai and Hat Yai profiles print OData URLs without network access in dry-run mode and parse mocked OData rows in tests.

## Task 22 - Study-Area Inventory V3

Add the UNOSAT/UNITAR Mae Sai reference-mask target, provisional Mae Sai pre/post pair, and Hat Yai focused CDSE candidate products.

Acceptance: inventory documents no-download status, unresolved geometry/license blockers, and Charter/Sentinel Asia/GISTDA access notes.

## Task 23 - Output Data Dictionary

Add a judge-facing data dictionary for CSV, GeoJSON, dashboard, brief, and metadata fields.

Acceptance: `outputs/data_dictionary.md` explains the generated outputs without requiring code inspection.

## Task 24 - Dashboard V3 Summary Cards

Add global scenario summary cards for best temporary-shelter intervention effect and worst road-closure stress case.

Acceptance: dashboard cards identify the expected fixture subdistrict and access-loss delta.

## Task 25 - Reference-Mask Licensing Log

Start a reference-mask licensing log for UNOSAT, GISTDA, Charter, Sentinel Asia, and academic/manual candidates.

Acceptance: all rows remain blocked until geometry, license, redistribution, and citation terms are confirmed.

## Task 26 - Metadata-Only Ingestion Skeleton

Add a first real-data ingestion skeleton that records source metadata and blockers only.

Acceptance: generated manifest is `metadata_only`, does not permit downloads, and marks all rows not ready for processing.

## Task 27 - Licensing Request Templates

Add copy-ready request templates for UNOSAT/UNITAR, GISTDA, International Charter, and Sentinel Asia.

Acceptance: templates ask for geometry access, license terms, redistribution status, citation requirements, and permitted research/demo use without claiming operational status.

## Task 28 - Live Metadata Snapshot Checklist

Add a review checklist before committing any `outputs/cdse_*_metadata.csv` files.

Acceptance: checklist covers dry-run URL review, command, profile, row count, product ID spot checks, no product downloads, no secrets, source URL preservation, and reason for committing.

## Task 29 - Ingestion Gate Test

Prevent the metadata-only ingestion skeleton from writing imagery, binary, or product-package outputs.

Acceptance: tests fail if the skeleton accepts `.SAFE`, `.tif`, `.jp2`, `.zip`, NetCDF, GRIB, or similar output paths, and tests confirm the skeleton has no network download calls.

## Task 30 - Dashboard V4 Export Buttons

Add static dashboard buttons for downloading the current action brief and active-filter priority GeoJSON.

Acceptance: exports are generated from embedded browser data only; `outputs/dashboard.html` remains backend-free and contains no `fetch` path.

## Task 31 - ML Readiness Plan

Document when FloodGuard is ready to start ML on real data.

Acceptance: `docs/ml_readiness_plan.md` states the current not-ready status and lists gates for reference-mask licensing, Sentinel-1 pair lock, metadata snapshot review, source file checksums, non-ML baseline, and validation metrics.

## Task 32 - ML-Readiness Bridge

Add a file-level processing gate, SAR baseline contract, synthetic SAR baseline, and first ML experiment plan.

Acceptance: ingestion manifests include product id, local path, SHA-256, source license status, reference-mask status, processing allowed, and blocker fields; processing cannot be forced before gates pass.

## Task 33 - Synthetic SAR Baseline Metrics

Implement a tiny fixture-backed non-ML SAR threshold baseline and validation metrics.

Acceptance: sample SAR outputs include `flood_probability_0_1`, `binary_flood_extent`, IoU, F1/Dice, precision, recall, and area error ratio, with no real imagery downloads or raster IO.

## Task 34 - THEOS-2 Metadata-Only Inventory

Inventory local THEOS-2 hackathon sample files without processing pixels or committing imagery.

Acceptance: `outputs/theos2_local_metadata_manifest.csv` records redacted path hints, filename metadata, TIFF header metadata, zip package summaries, user-reported hackathon free-use status, and `processing_allowed=False` until selected file checksums are recorded.

## Task 35 - THEOS-2 Selected-File Readiness And Preview

Checksum only selected THEOS-2 disaster/context files and generate small non-operational optical-context preview cards.

Acceptance: `outputs/theos2_selected_file_manifest.csv` records SHA-256 checksums, `processing_scope=theos2_optical_context_preview_only`, and `reference_mask_status=not_reference_mask`; `outputs/theos2_previews/*.svg` are small dashboard-ready context artifacts; source imagery remains outside Git.

## Task 36 - THEOS-2 True Thumbnail Lane

Add an optional rasterio/GDAL-backed thumbnail workflow for selected THEOS-2 files.

Acceptance: workflow detects raster reader availability, fails cleanly when unavailable, requires checksum-backed selected rows, and writes only small PNG thumbnails plus a manifest when a reader exists.

## Task 37 - THEOS-2 Optical Context In Briefs

Add compact THEOS-2 optical context to generated action briefs.

Acceptance: A/B/C briefs include strict wording that THEOS-2 is optical context only, not flood validation, not a reference mask, and not official warning evidence.

## Task 38 - THEOS-2 Land-Cover/Exposure Feature Prototype

Build a tiny non-ML feature table from selected THEOS-2 metadata.

Acceptance: output includes disaster/LULC/urban/agri/coastal flags, rough footprint area, built-up/water context notes, and assumptions that these are not flood labels.

## Task 39 - Provider Response Logging And Mae Sai Manifest V2

Document and test the transition from sent provider requests to file-level readiness.

Acceptance: docs explain how to log UNOSAT/GISTDA replies, Mae Sai manifest gates reject current blocked rows, and validation summary remains blocked until legal local files/checksums are recorded.

## Task 40 - Local Hackathon Data Library

Catalog all currently provided local hackathon files without committing source imagery or extracting ZIP packages.

Acceptance: `outputs/local_data_library_manifest.csv` records top-level local files, redacted path hints, file groups, raster header metadata where available, MVP overlap, and processing blockers; `outputs/local_data_library_zip_members.csv` records ZIP members without extraction; source TIFF/ZIP/OVR assets remain outside Git.

## Task 41 - Selected Sentinel-1 Readiness Lane

Checksum the standalone Mae Sai-overlapping Sentinel-1 VV/VH TIFF and record file-level readiness metadata without processing pixels.

Acceptance: `outputs/sentinel1_selected_file_manifest.csv` records SHA-256, raster metadata, `mvp_overlap=mae_sai_2024_point`, and `processing_allowed=False` while provenance, event timing, and reference-mask status remain unresolved; source TIFFs remain outside Git.

## Task 42 - Sentinel-1 Provenance And Timing Resolver

Resolve the selected Sentinel-1 file provenance and event timing before any real SAR baseline processing.

Acceptance: selected Sentinel-1 readiness rows identify acquisition date/time, product provenance or source package, whether the file is pre-event/post-event/context-only, and the remaining reference-mask blocker. Processing remains blocked unless all gates pass.

## Task 43 - DEM Readiness Lane

Build a metadata-only selected-file readiness lane for the local Copernicus DEM/elevation-slope assets.

Acceptance: `outputs/dem_selected_file_manifest.csv` catalogs selected DEM ZIP members with redacted path hints, source package, package-level checksum status, terrain-context candidate use, and `processing_allowed=False` until member-level extraction/checksum and scope gates are clear. Source DEM TIFFs and ZIP packages remain outside Git.

## Task 44 - Local Data Library Dashboard Panel

Expose the local data library and selected readiness lanes in the static dashboard as a compact metadata panel.

Acceptance: `outputs/dashboard.html` shows counts and statuses for local Sentinel-1, DEM, and THEOS-2 lanes from generated manifests; it distinguishes fixture/demo outputs from local metadata readiness; it does not fetch files, expose absolute paths, or imply that local assets are official flood observations.
