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

- Mae Sai Sentinel-1 metadata still includes selected planning candidates `b09f96ca-4a60-43e7-9b8d-158022f0e5bf` and `20a9c3b8-37df-46d5-81d8-d63c7e460225`.
- Sentinel Asia product scrape found public product links only; source product ZIPs/JPGs were not downloaded.
- CEMS EMSR754/EMSR756 were recorded as activation candidates, not downloaded product rows, because the public page is viewer-backed.
- Sentinel-2 metadata rows are optical context only and not flood labels.

Commit decision: acceptable to commit because all outputs are metadata CSVs with source URLs, no secrets, no account tokens, and no raw source assets.
