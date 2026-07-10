# FloodGuard Thailand

FloodGuard Thailand is a reproducible GeoAI decision-support prototype that converts flood extent or flood probability into subdistrict-level action priorities for flood preparedness and rapid post-event response in Thailand.

The core product is not another flood map. It is a decision layer that turns flood pixels into exposed population, likely road disruption, access loss, equity gaps, shelter demand, a Flood Preparedness Priority Score, and an A-E action class.

## MVP Focus

1. Chiang Rai / Mae Sai 2024 - validation tile.
2. Hat Yai / Songkhla 2025 - story and stress-test tile.
3. Lower Chao Phraya / Greater Bangkok - scale target.

## Current Vertical Slice

This scaffold implements the first testable decision-layer component:

- validates subdistrict priority inputs
- computes the default Flood Preparedness Priority Score
- assigns A-E action classes
- generates a short top reason
- writes a sample priority CSV from fixture data

## Run The System Locally

Use this path when you want to regenerate the fixture-backed FloodGuard system and open the dashboard yourself.

```powershell
cd "C:\Users\iputu\Documents\Flood Guard"
uv sync --extra dev --extra theos2
uv run pytest
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
uv run python scripts/smoke_dashboard.py
start outputs\dashboard.html
```

The dashboard is static. It has no backend, no build step, and no browser-side `fetch` call. Opening `outputs\dashboard.html` is enough for the fixture demo.

If your browser blocks direct file rendering or you prefer a local URL, serve the `outputs/` folder:

```powershell
uv run python -m http.server 8000 -d outputs
```

Then open:

```text
http://localhost:8000/dashboard.html
```

Recommended local operating loop:

1. Edit code or fixtures.
2. Run `uv run pytest`.
3. Run `uv run python scripts/generate_sample_decision_outputs.py`.
4. Run `uv run python scripts/smoke_dashboard.py`.
5. Open or refresh `outputs\dashboard.html`.

Do not commit source TIFF, ZIP, SAFE, JP2, NetCDF, GRIB, or overview files. The repo commits only small generated outputs, manifests, docs, tests, and code.

## Quick Start

```powershell
uv sync --extra dev
uv run pytest
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
```

The sample outputs are written to `outputs/`, including the standalone dashboard, action briefs, GeoJSON exports, and `outputs/data_dictionary.md`.

If you are not using `uv`, install with `python -m pip install -e ".[dev]"` and run the same commands with `python -m pytest` and `python scripts/generate_sample_priority.py`.

## Metadata-Only Real-Data Planning

CDSE metadata queries are no-download catalogue queries. Use dry-run first to inspect the exact OData URL:

```powershell
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --dry-run
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --dry-run
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024_sentinel2 --dry-run
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025_sentinel2 --dry-run
```

Only run the `--output` form when you intentionally want to create and review a live metadata snapshot for commit:

```powershell
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024_sentinel2 --output outputs/cdse_mae_sai_2024_sentinel2_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025_sentinel2 --output outputs/cdse_hat_yai_2025_sentinel2_metadata.csv
```

Before committing any `outputs/cdse_*_metadata.csv` file, complete `docs/live_metadata_snapshot_review_checklist.md` and record the row count, command, dry-run URL review, and reason for committing the snapshot. Committed snapshot decisions are logged in `docs/live_metadata_snapshot_review_log.md`.

These CDSE metadata commands write metadata rows only. They do not download Sentinel-1 assets, flood masks, GISTDA products, Charter products, Sentinel Asia products, or any remote-sensing model inputs.

The public open-data fallback inventory can be refreshed with:

```powershell
uv run python scripts/build_public_reference_manifest.py
uv run python scripts/inspect_sentinel_asia_reference_candidate.py
uv run python scripts/review_sentinel_asia_geometry_quality.py
uv run python scripts/resolve_cems_products.py
uv run python scripts/build_mae_sai_reference_decision.py
uv run python scripts/build_open_context_file_manifest.py
uv run python scripts/build_mae_sai_file_manifest.py
uv run python scripts/acquire_cdse_mae_sai_sentinel1.py
uv run python scripts/inspect_manual_reference_mask.py
```

This writes `outputs/public_reference_candidate_manifest.csv`, `outputs/sentinel_asia_public_product_links.csv`, `outputs/public_reference_file_inspection_manifest.csv`, `outputs/sentinel_asia_geometry_quality_review.csv`, `outputs/cems_product_candidate_manifest.csv`, `outputs/mae_sai_reference_candidate_decision.md`, `outputs/open_context_data_file_manifest.csv`, `outputs/cdse_mae_sai_acquisition_manifest.csv`, and `outputs/manual_reference_mask_manifest.csv`. The Sentinel Asia shapefile ZIP is downloaded only to an external data workspace such as `<external_data_workspace>/sentinel_asia/`; the repo commits only redacted path hints, SHA-256 checksums, file lists, CRS, bbox, QGIS/GDAL summary metadata, embedded metadata findings, and blocker status. CDSE product downloads require `CDSE_ACCESS_TOKEN` or `CDSE_USERNAME`/`CDSE_PASSWORD`; without credentials the acquisition manifest records `blocked_missing_cdse_credentials`, and with credentials the selected Sentinel-1 products are downloaded outside Git with SHA-256 checksums recorded. The open-context workflow may download WorldPop, HDX COD-AB, and Geofabrik OSM files only to the external data workspace, then commits only redacted path hints and SHA-256 checksums. The manual QGIS weak-reference lane writes metadata only and expects `mae_sai_manual_flood_reference.gpkg` to stay outside Git. The workflow does not download product ZIPs, JPG maps, GeoTIFFs, SAFE packages, NASA rasters, WorldPop rasters, OSM extracts, DEM source assets, or manual GeoPackage source data into the repo; it only downloads selected allowed files outside Git when a dedicated acquisition script says so. The current approach is documented in `docs/public_open_data_acquisition.md`, `docs/open_context_data_acquisition_notes.md`, and `docs/mbrsc_reference_mask_clearance_memo.md`.

The metadata-first ingestion skeleton can build a blocked planning manifest:

```powershell
uv run python scripts/build_ingestion_manifest.py
uv run python scripts/build_mae_sai_file_manifest.py
uv run python scripts/build_local_data_library.py
uv run python scripts/build_theos2_local_manifest.py
uv run python scripts/build_theos2_selected_manifest.py
uv run python scripts/generate_theos2_previews.py
uv run python scripts/generate_theos2_features.py
uv run python scripts/build_sentinel1_selected_manifest.py
uv run python scripts/resolve_sentinel1_provenance.py
uv run python scripts/generate_sentinel1_quicklooks.py --check-reader
uv run python scripts/build_dem_selected_manifest.py
uv run python scripts/generate_dem_quicklook.py --check-reader
uv run python scripts/generate_mae_sai_validation_summary.py
uv run python scripts/check_real_data_gates.py --allow-blocked
uv run python scripts/validate_mae_sai_file_manifest.py --allow-blocked
```

The generated `outputs/real_data_ingestion_manifest.csv` and `outputs/mae_sai_real_data_file_manifest.csv` remain blocked for flood-reference processing until geometry, license, redistribution/reference-only status, local paths, checksums, and reference-mask status are confirmed. `scripts/check_real_data_gates.py` confirms whether provider responses clear reference-mask use for local validation and separately whether ML-label use is allowed. `scripts/validate_mae_sai_file_manifest.py` explains exactly which file-level rows block the real Mae Sai non-ML baseline. `outputs/theos2_local_metadata_manifest.csv` records user-reported hackathon free-use status for THEOS-2 samples from `docs/theos2_usage_terms_log.md`, but selected files still need SHA-256 checksums before reproducible pixel-processing outputs are generated.

`docs/manual_reference_mask_protocol.md` defines the QGIS manual weak-reference fallback. `outputs/manual_reference_mask_manifest.csv` records the redacted path hint, SHA-256, GeoPackage layer metadata, required field check, and allowed/not-allowed uses. It can support candidate validation metrics after the manual GeoPackage exists, but it does not clear official validation truth, official warning, redistribution, or unqualified ML-label gates.

After the weak-reference SAR, validation, and decision-bridge outputs exist, regenerate the first bilingual Mae Sai candidate action brief with:

```powershell
uv run python scripts/build_mae_sai_decision_inputs.py
uv run python scripts/generate_mae_sai_action_brief.py
```

The command writes `outputs/mae_sai_action_brief_MS-WR-001.md` from derived CSV evidence only. Missing real road, access, and equity context remains explicitly unavailable; the brief is non-operational, not an official warning, and for planning/demo use only.

`outputs/theos2_selected_file_manifest.csv` records SHA-256 checksums for only the curated selected THEOS-2 files. `outputs/theos2_previews/*.svg` are small non-operational optical-context preview cards generated from checksum-backed metadata. They are not flood masks, not validation labels, and not official warning products. Source TIFFs and overview files remain outside Git.

`outputs/sentinel1_selected_file_manifest.csv` records the SHA-256 checksum and raster metadata for the standalone local Sentinel-1 TIFF that overlaps the Mae Sai MVP point. It is a readiness manifest only: provenance, event timing, and reference-mask status remain unresolved, so `processing_allowed=False` until the next Sentinel-1 provenance and timing resolver clears those gates. The source TIFF remains outside Git.

`outputs/sentinel1_provenance_resolved_manifest.csv` and `docs/sentinel1_local_provenance.md` record the current Sentinel-1 provenance finding. The standalone local TIFF has VV/VH bands and Mae Sai overlap, but the filename uses placeholder numeric offsets, TIFF tags do not expose acquisition timing or a product id, ZIP members are tiled companions only, and no CDSE snapshot match is committed. It remains `candidate_role=unresolved`, `event_timing_status=timing_unresolved`, and `processing_allowed=False`.

Optional Sentinel-1 SAR quicklooks require `rasterio` or GDAL and a recorded SHA-256 row in `outputs/sentinel1_selected_file_manifest.csv`. They are small context PNGs only:

```powershell
uv run python scripts/generate_sentinel1_quicklooks.py
```

The command writes `outputs/sentinel1_quicklook_vv.png`, `outputs/sentinel1_quicklook_vh.png`, and `outputs/sentinel1_quicklook_manifest.csv`. These quicklooks are SAR context only: not flood detection, not validation, not an official warning, and event timing remains unresolved unless provenance is solved. The source Sentinel-1 TIFF remains outside Git.

`outputs/dem_selected_file_manifest.csv` records package-level SHA-256 checksums for the two local Copernicus DEM/elevation-slope ZIP packages and one row per DEM TIFF member. It is terrain context only: no ZIP extraction is committed, member-level checksums wait until controlled extraction, and DEM rows are not flood observations, not flood labels, and not reference masks.

Optional DEM terrain quicklooks require `rasterio` or GDAL, an extracted DEM TIFF outside Git, and an explicit member-level SHA-256 checksum. The command stays blocked unless those gates are provided:

```powershell
uv run python scripts/generate_dem_quicklook.py --check-reader
uv run python scripts/generate_dem_quicklook.py --extracted-dem-path <outside-git-dem.tif> --member-name <selected-member-name> --member-sha256 <sha256> --local-path-hint <external_data_workspace>/<selected-member-name>
```

The command writes `outputs/dem_quicklook.png` and `outputs/dem_quicklook_manifest.csv`. These are DEM terrain context only: not flood observation, not flood label, not reference mask, and not an official warning. Extracted DEM source TIFFs remain outside Git.

Optional true THEOS-2 thumbnails require `rasterio` or GDAL. Check availability first:

```powershell
uv sync --extra theos2
uv run python scripts/generate_theos2_true_thumbnails.py --check-reader
```

If a reader is available, generate small PNG thumbnails only from checksum-backed selected files:

```powershell
uv run python scripts/generate_theos2_true_thumbnails.py --verify-checksum
uv run python scripts/generate_theos2_visual_review_checklist.py
```

If no reader is available, the command exits cleanly with a blocked message and the SVG context previews remain the dashboard fallback.

ML on real data should wait until the gates in `docs/ml_readiness_plan.md` are satisfied: legally usable reference mask, locked Sentinel-1 pair, reviewed metadata snapshot, source files tracked outside Git with checksums, and a reproducible non-ML baseline.

The first ML-readiness bridge is documented in `docs/sar_baseline_contract.md` and `docs/first_ml_experiment_plan.md`. The current SAR baseline is synthetic only and writes toy outputs to `outputs/sample_sar_baseline.csv` and `outputs/sample_sar_validation_metrics.csv`; it does not read or download real Sentinel-1 imagery.

## Repository Layout

```text
docs/                 Project, data, model, validation, and demo contracts.
tasks/                Codex-ready backlog and task briefs.
src/floodguard/       Production Python package code.
tests/                Unit tests and open sample fixtures.
notebooks/            Exploratory notebooks only.
outputs/              Generated sample and demo outputs.
scripts/              Small reproducible utility scripts.
```

## Safety Boundary

FloodGuard is for preparedness and rapid post-event prioritization. It is not an official emergency warning system, not a guaranteed real-time flood detector, and not a replacement for GISTDA, DDPM, TMD, RID, ONWR, or local agency judgment.
