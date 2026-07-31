# Live Metadata Snapshot Review Log

This log records intentional live metadata snapshots committed to the repo. It is metadata-only evidence; no source imagery or product archives were downloaded.

## 2026-07-08 Public Open-Data Snapshot

Reason: build an open/public fallback acquisition lane while UNOSAT/GISTDA provider responses are pending.

Commands run:

```powershell
uv run python scripts/build_public_reference_manifest.py
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024_sentinel2 --output outputs/cdse_mae_sai_2024_sentinel2_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025_sentinel2 --output outputs/cdse_hat_yai_2025_sentinel2_metadata.csv
```

Reviewed outputs:

| Output | Row count | Download performed |
| --- | ---: | --- |
| `outputs/public_reference_candidate_manifest.csv` | 48 | no |
| `outputs/sentinel_asia_public_product_links.csv` | 33 | no |
| `outputs/cdse_mae_sai_2024_metadata.csv` | 8 | no |
| `outputs/cdse_hat_yai_2025_metadata.csv` | 10 | no |
| `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv` | 5 | no |
| `outputs/cdse_hat_yai_2025_sentinel2_metadata.csv` | 4 | no |

Spot checks:

- Mae Sai Sentinel-1 metadata contains the approved same-track original SAFE
  pair `aaaef3af-fa49-4115-bf0f-f54175e7aedf` and
  `5251b74b-0bbd-4365-9eb4-fa33292e175a`. A later source-selection review
  retired the earlier September 6 / September 15 COG pair; those COG UUIDs are
  inventory evidence only and must not be used as active baseline rows.
- Sentinel Asia product scrape found public product links only; source product ZIPs/JPGs were not downloaded.
- CEMS EMSR754/EMSR756 were recorded as activation candidates, not downloaded product rows, because the public page is viewer-backed.
- Sentinel-2 metadata rows are optical context only and not flood labels.

Commit decision: acceptable to commit because all outputs are metadata CSVs with source URLs, no secrets, no account tokens, and no raw source assets.

## 2026-07-20 Hat Yai Same-Track Pair Snapshot

Reason: widen the Hat Yai metadata-only window by one Sentinel-1 repeat cycle so the story-tile readiness gate can bind a defensible same-platform, same-time-of-day pre/post candidate pair. This snapshot does not acquire imagery or clear reference-mask rights.

Commands run:

```powershell
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --dry-run
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv
```

Review result:

- Dry-run URL inspected: yes.
- Output: `outputs/cdse_hat_yai_2025_metadata.csv`.
- Row count: 14 metadata rows; no product download was performed.
- Snapshot SHA-256: `8da3ff0ff2a16ef1e6483b5556d24981025385e6e8f7541c724f96ea9e750196`.
- Pre-event original SAFE candidate: `4e473302-943c-4798-8bfc-8287167792ed`, acquired 2025-11-11 23:03 UTC.
- Post-event original SAFE candidate: `d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc`, acquired 2025-11-23 23:03 UTC.
- Both rows are Sentinel-1A IW GRDH dual-polarization original SAFE metadata candidates on a 12-day repeat; asset checksums and local paths are absent.
- The CSV contains no credentials, tokens, cookies, or local absolute paths.
- `blocker_note` retains the unresolved Charter, Sentinel Asia, GISTDA geometry, access, and licensing boundary.

Commit decision: acceptable as metadata-only pair-lock evidence. The pair remains `locked_metadata_only`; processing, candidate metrics, decision outputs, and the Hat Yai dashboard story remain blocked until external asset and reference gates pass.
