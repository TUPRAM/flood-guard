# FloodGuard Thailand

FloodGuard Thailand is a reproducible geospatial decision-support prototype that converts flood extent or flood probability into subdistrict-level action priorities for flood preparedness and rapid post-event planning in Thailand.

The core product is not another flood map. It is a decision layer that turns flood pixels into exposed population, likely road disruption, access loss, equity gaps, shelter demand, a Flood Preparedness Priority Score, and an A-E action class.

## MVP Focus

1. Chiang Rai / Mae Sai 2024 - validation tile.
2. Hat Yai / Songkhla 2025 - story and stress-test tile.
3. Lower Chao Phraya / Greater Bangkok - scale target.

FloodGuard is not an official warning system, a guaranteed real-time flood detector, or a live evacuation navigator. Fixture and candidate modes are non-operational and always set `official_warning=false`.

## Role-Specific Platform

The repository now keeps five boundaries explicit:

```text
apps/web                Next.js/TypeScript responsive PWA
services/api            FastAPI artifact and deterministic scenario API
services/geoai-runner   isolated Python 3.12 GeoAI candidate environment
packages/contracts      JSON Schema and TypeScript contracts
src/floodguard          preserved, tested decision engine
```

The responsive competition application has three deliberately different routes:

- `/public` is Thai-first, mobile-first preparedness guidance using a reduced Mae Sai public projection, verified official contact links, and no evacuation commands or unverified facility locations.
- `/command` is a map-first planning workspace with fixed A-E/FPPS policy, evidence panels, verification tasks, and canonical planning exports.
- `/studio` is a read-only validation and evidence report. It preserves exact evidence identities, blockers, and authorization state without implying an approval workflow.

The competition release is scoped to Mae Sai district, Chiang Rai, using historical September 2024 flood context. It does not claim current conditions or nationwide coverage. `role_visibility` is enforced as an evidence-presentation and safety-governance boundary in the unauthenticated competition build; it is not an authentication or confidentiality boundary.

Run the offline judging application:

```powershell
# One-time setup when `pnpm` is not recognized on Windows:
corepack enable
corepack prepare pnpm@11.9.0 --activate

pnpm install --frozen-lockfile
pnpm verify:frontend
pnpm --filter @floodguard/web dev
```

Two static deployment profiles keep entry behavior and offline caching explicit:

```powershell
# Competition: / is the three-role chooser and all open competition surfaces are packaged.
pnpm --filter @floodguard/web build:competition

# Public production: / is the Public experience; staff routes and staff geospatial payloads are removed.
pnpm --filter @floodguard/web build:public
```

The public-production profile is the deployable public boundary. A future staff deployment must add authenticated authorization and a separate cache policy before it can carry operational or confidential data.

Then open `http://localhost:3000/public`,
`http://localhost:3000/command`, or `http://localhost:3000/studio`. If the
PowerShell execution policy blocks a generated script wrapper, use `pnpm.cmd`
in the same commands. The role-surface product plan and privacy/safety boundary
are documented in `docs/role-surface-development-plan.md`.

`pnpm verify:frontend` includes a real-browser offline navigation smoke. The
verification scripts prefer the pinned Playwright Chromium build and fall back
to an installed Chrome channel. Install the pinned browser once with
`pnpm exec playwright install chromium`; the smoke blocks every external
request except the three explicitly approved map-background providers.

Run the API in its separate environment from the repository root:

```powershell
uv sync --project services/api --group dev
uv run --project services/api uvicorn floodguard_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000
```

In a second PowerShell window, connect the web application to that API:

```powershell
$env:NEXT_PUBLIC_FLOODGUARD_API_URL="http://127.0.0.1:8000"
pnpm.cmd --filter @floodguard/web exec next dev --hostname 127.0.0.1
```

The three role surfaces request one immutable Mae Sai evidence context. Public receives only the approved reporting-area projection and never requests, caches, attributes, or exports the staff road, facility-candidate, access, model-registry, evaluation, or observation-product records. Command may inspect the open-data planning layers with neutral, verification-first semantics. Studio shows the same evidence package, reports that no model evaluation is bound when a matching evaluation record does not exist, and may separately display redacted report-only registry records with their exact blocker and lineage. When the API is absent, each surface uses its role-filtered, checksummed offline projection; multi-megabyte geospatial responses are not written to `localStorage`. `outputs/dashboard.html` remains a reproducible internal fallback used by the decision-engine test lane and is not part of the public-production deployment.

With both development servers running, verify the real API-to-browser path:

```powershell
pnpm.cmd --filter @floodguard/web test:live-api
```

The API validates CSV, GeoJSON, and Markdown artifact structure before advertising data as ready. Missing or malformed artifacts return explicit unavailable/blocked states while `/api/v1/health` continues to report service-process health independently.

GeoAI is optional and isolated. Normal root tests, API tests, and web tests do not install or import the heavy GeoAI runner. See `services/geoai-runner/README.md` and `docs/geoai-system-design-v1.md`; no real-data training is allowed until the repository's provenance, licensing, timing, checksum, reference-mask, reviewer, partition, and spatial-validation gates pass. The additive v2 model-run, observation-product, evaluation, and study-area registry contracts are deliberately report-only until those gates and a separately signed promotion chain pass. The Mae Sai Studio fallback is generated from the same API registry builder, includes its exact ModelRun v2 document, and uses materialized checksum-bound JSON descriptors—not pretend rasters—for the all-abstain product:

```powershell
uv run --project services/api --with shapely==2.1.2 python apps/web/scripts/build-mae-sai-offline-bundle.py
```

Studio performs structural/cross-record checks but explicitly reports that browser cryptographic status is not verified. Canonical digest, public test-HMAC, and safety-gate verification belongs to the API/core resolver. Trusted zonal receipts are schema 2.0 and bind authoritative geometry to the exact model-run study area; unbound legacy 1.0 receipts are rejected.

## Preserved Decision Engine

The tested domain package implements the decision-layer components used by the application:

- validates subdistrict priority inputs
- computes the default Flood Preparedness Priority Score
- assigns A-E action classes
- generates a short top reason
- computes nearest-facility shortest-path access loss at fixed time thresholds (not capacity-aware 2SFCA)
- computes equity and road-risk evidence
- writes reproducible CSV, GeoJSON, Markdown, and static-dashboard artifacts

## Run The System Locally

Use this path when you want to regenerate the fixture-backed FloodGuard system and open the dashboard yourself.

```powershell
Set-Location "<repository-root>"
uv sync --extra dev --extra theos2
uv run pytest
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
uv run python scripts/smoke_dashboard.py
start outputs\dashboard.html
```

The dashboard is static. It has no backend, no build step, and no browser-side `fetch` call. Leaflet, the decision vectors, and a map text equivalent are embedded in the HTML; optional OpenStreetMap tiles fail over to a visible offline-basemap status. Opening `outputs\dashboard.html` is enough for the fixture demo and the embedded Mae Sai weak-reference candidate mode.

Dashboard v11 includes an English/Thai interface, semantic regional/detail map density, selected-ADM3 focus, compact Sentinel-1 evidence and provenance, and a judge presentation mode. In Mae Sai mode, select an ADM3 unit to zoom into detailed candidate roads and typed facilities. Judge mode removes secondary controls while keeping the weak-reference warning and provenance visible.

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

The generated `outputs/real_data_ingestion_manifest.csv` and `outputs/mae_sai_real_data_file_manifest.csv` bind the active original-SAFE pair and the manual cross-border reference to outside-Git paths and SHA-256 checksums. That evidence permits the explicitly labeled, non-operational weak-reference candidate baseline only. Qualified Mae Sai validation, ML-label use, decision promotion, and official use remain blocked until reference authority, permitted uses, redistribution/reference-only status, reviewer qualification, and immutable spatial-holdout gates pass. `scripts/check_real_data_gates.py` checks the formal reference-mask permissions, while `scripts/validate_mae_sai_file_manifest.py --allow-blocked` reports the remaining qualified-use blockers without invalidating the completed candidate calibration lane. `outputs/theos2_local_metadata_manifest.csv` records user-reported hackathon free-use status for THEOS-2 samples from `docs/theos2_usage_terms_log.md`, but selected files still need SHA-256 checksums before reproducible pixel-processing outputs are generated.

`docs/manual_reference_mask_protocol.md` defines the QGIS manual weak-reference fallback. `outputs/manual_reference_mask_manifest.csv` records the redacted path hint, SHA-256, GeoPackage layer metadata, required field check, and allowed/not-allowed uses. It can support candidate validation metrics after the manual GeoPackage exists, but it does not clear official validation truth, official warning, redistribution, or unqualified ML-label gates.

After the weak-reference SAR, validation, and decision-bridge outputs exist, regenerate the first bilingual Mae Sai candidate action brief with:

```powershell
uv run python scripts/build_mae_sai_real_context.py
uv run python scripts/build_mae_sai_decision_inputs.py
uv run python scripts/generate_mae_sai_action_brief.py
```

The real-context builder validates checksum-tracked outside-Git files, derives eight HDX COD-AB Mae Sai ADM3 rows, joins WorldPop exposure, OSM road/facility routing, and Copernicus DEM terrain context, and writes source-quality evidence. It also writes compact dashboard layers for candidate road risk, candidate facilities, and modeled access hotspots. The final command writes the current highest-priority ADM3 brief, currently `outputs/mae_sai_action_brief_TH570903.md` for Ko Chang, from committed derived evidence only. The brief remains non-operational, not an official warning, and for planning/demo use only.

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

The active-learning label-factory foundation is documented in `docs/label_factory_protocol.md`, `docs/label_factory_data_contract.md`, `docs/label_factory_runbook.md`, and `docs/label_factory_implementation_status.md`. It treats the existing manual polygon as weak positive-unlabeled evidence, keeps uncertain, unobservable, and unreviewed states out of binary training, generates an internal-only operator queue plus model-blinded reviewer packages, and permanently marks query-model artifacts as ineligible for the decision layer, FPPS, and warnings. Canonical grids require an immutable `floodguard.processing_alignment_receipt.v1` that re-hashes the processed raster plus coverage, valid-data, and registration evidence and binds them to the exact source registry/common affine; source metadata alone cannot clear the grid. Known label-factory/query artifacts are rejected at current decision ingresses; a future operational flood-input contract must additionally require positive approved-model provenance. The repository now contains tested fail-closed contracts, immutable artifact writers, reviewer-agreement gates, a logistic-plus-boosted query committee, Round 0 and 60/20/20 selection logic, and an equal-cost evaluation scaffold. The controlled Mae Sai workspace now also contains the real processing/alignment receipt, a 20-tile/854-core canonical grid, 874,496 aligned `sar_change_v2` pool cells, governed static strata, and a batch positive-unlabeled weak-query summary. It does **not** contain completed human reviews, an adjudicated training release, a trained real-data query committee, a real selected operator queue, additional processed Thailand development events, or evidence that active learning is more efficient than random review. Those remain external evidence gates and are never fabricated.

### Reviewer A practice workbench

The local Reviewer A Workbench provides a real painting-and-review interface for the 20 synthetic 32 x 32 teaching cases. It includes evidence-layer switching, multiclass cell painting, undo/redo, timing, confidence and ambiguity recording, local draft recovery, irreversible first-attempt locking, post-lock feedback, and practice-only export. It does not open the formal 12-query calibration or any of the 854 real Mae Sai cores, and its output cannot enter the canonical annotation log, model training, the decision layer, FPPS, or warnings.

Set `FLOODGUARD_EXTERNAL_WORKSPACE` to the operator-managed external-data
directory, build from the checksum-verified synthetic package, then open the
generated `index.html`:

```powershell
$pilot = Join-Path $env:FLOODGUARD_EXTERNAL_WORKSPACE "label_factory\mae_sai_pilot_v1"
$createdUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

uv run python scripts/build_reviewer_a_practice_workspace.py `
  --source-directory "$pilot\human_coordination_v2\synthetic_cases_v1" `
  --output-directory "$pilot\human_coordination_v2\reviewer_a_practice_workspace_v1" `
  --reviewer-display-name "I Putu Pramana Putra" `
  --created-at-utc $createdUtc `
  --formal-hold-path "$pilot\human_coordination_v2\FORMAL_REVIEW_HOLD.json"

Start-Process "$pilot\human_coordination_v2\reviewer_a_practice_workspace_v1\index.html"
```

Read `docs/reviewer_a_workbench_guide.md` before reviewing. It explains the practice/formal boundary, label taxonomy, evidence rules, human roles, calibration gates, first-20 workflow, adjudication, label release, and the later active-learning evaluation.

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
