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

These commands write metadata rows only. They do not download Sentinel-1 assets, flood masks, GISTDA products, Charter products, Sentinel Asia products, or any remote-sensing model inputs.

The metadata-first ingestion skeleton can build a blocked planning manifest:

```powershell
uv run python scripts/build_ingestion_manifest.py
```

The generated `outputs/real_data_ingestion_manifest.csv` remains `metadata_only`; it does not permit downloads or processing until geometry, license, and redistribution status are confirmed.

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
