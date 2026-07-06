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
```

Only run the `--output` form when you intentionally want to create and review a live metadata snapshot for commit:

```powershell
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv
```

Before committing either `outputs/cdse_*_metadata.csv` file, complete `docs/live_metadata_snapshot_review_checklist.md` and record the row count, command, dry-run URL review, and reason for committing the snapshot.

These commands write metadata rows only. They do not download Sentinel-1 assets, flood masks, GISTDA products, Charter products, Sentinel Asia products, or any remote-sensing model inputs.

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
uv run python scripts/build_dem_selected_manifest.py
uv run python scripts/generate_mae_sai_validation_summary.py
```

The generated `outputs/real_data_ingestion_manifest.csv` and `outputs/mae_sai_real_data_file_manifest.csv` remain blocked for flood-reference processing until geometry, license, redistribution/reference-only status, local paths, checksums, and reference-mask status are confirmed. `outputs/theos2_local_metadata_manifest.csv` records user-reported hackathon free-use status for THEOS-2 samples from `docs/theos2_usage_terms_log.md`, but selected files still need SHA-256 checksums before reproducible pixel-processing outputs are generated.

`outputs/theos2_selected_file_manifest.csv` records SHA-256 checksums for only the curated selected THEOS-2 files. `outputs/theos2_previews/*.svg` are small non-operational optical-context preview cards generated from checksum-backed metadata. They are not flood masks, not validation labels, and not official warning products. Source TIFFs and overview files remain outside Git.

`outputs/sentinel1_selected_file_manifest.csv` records the SHA-256 checksum and raster metadata for the standalone local Sentinel-1 TIFF that overlaps the Mae Sai MVP point. It is a readiness manifest only: provenance, event timing, and reference-mask status remain unresolved, so `processing_allowed=False` until the next Sentinel-1 provenance and timing resolver clears those gates. The source TIFF remains outside Git.

`outputs/sentinel1_provenance_resolved_manifest.csv` and `docs/sentinel1_local_provenance.md` record the current Sentinel-1 provenance finding. The standalone local TIFF has VV/VH bands and Mae Sai overlap, but the filename uses placeholder numeric offsets, TIFF tags do not expose acquisition timing or a product id, ZIP members are tiled companions only, and no CDSE snapshot match is committed. It remains `candidate_role=unresolved`, `event_timing_status=timing_unresolved`, and `processing_allowed=False`.

`outputs/dem_selected_file_manifest.csv` records package-level SHA-256 checksums for the two local Copernicus DEM/elevation-slope ZIP packages and one row per DEM TIFF member. It is terrain context only: no ZIP extraction is committed, member-level checksums wait until controlled extraction, and DEM rows are not flood observations, not flood labels, and not reference masks.

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
