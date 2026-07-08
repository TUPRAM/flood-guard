# Public Open-Data Acquisition Lane

Status: metadata and public-link inventory created. No source imagery, product ZIPs, GeoTIFFs, SAFE packages, NetCDF, GRIB, or raw mask files are committed.

This lane exists because UNOSAT/GISTDA replies may be slow. It lets FloodGuard move forward with public/open sources while keeping the repository clean and the real validation gates honest.

## What Was Captured

Generated outputs:

- `outputs/public_reference_candidate_manifest.csv`
- `outputs/sentinel_asia_public_product_links.csv`
- `outputs/cdse_mae_sai_2024_metadata.csv`
- `outputs/cdse_hat_yai_2025_metadata.csv`
- `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv`
- `outputs/cdse_hat_yai_2025_sentinel2_metadata.csv`

Current generated row counts:

| Output | Rows | Notes |
| --- | ---: | --- |
| `public_reference_candidate_manifest.csv` | 48 | Seed rows plus Sentinel Asia public product-link rows. |
| `sentinel_asia_public_product_links.csv` | 33 | Direct public links from the Northern Thailand 2024 Sentinel Asia event page. |
| `cdse_mae_sai_2024_metadata.csv` | 8 | Sentinel-1 Mae Sai event-window product metadata. |
| `cdse_hat_yai_2025_metadata.csv` | 10 | Sentinel-1 Hat Yai event-window product metadata. |
| `cdse_mae_sai_2024_sentinel2_metadata.csv` | 5 | Sentinel-2 L2A Mae Sai optical-context metadata. |
| `cdse_hat_yai_2025_sentinel2_metadata.csv` | 4 | Sentinel-2 L2A Hat Yai optical-context metadata. |

## Source Handling Rules

- CDSE Sentinel-1 and Sentinel-2 rows are product metadata only. They are not downloaded imagery.
- CEMS EMSR754 and EMSR756 rows are activation candidates. The public viewer page does not expose simple product links in static HTML, so exact product downloads remain a follow-up probe.
- Sentinel Asia Northern Thailand 2024 rows include public direct links, including JPG map/quicklook files, GIS ZIP candidates, and one shapefile ZIP candidate. These links are not automatically validation masks.
- UNOSAT/UNITAR public pages remain report/citation evidence unless redistributable geometry and derivative-use terms are confirmed.
- NASA flood products are coarse context/proxy candidates, not subdistrict/road-scale validation labels.
- WorldPop, OSM/Geofabrik, Copernicus DEM, and HDX COD-AB are decision-layer context sources, not flood labels.
- THEOS-2, local Sentinel-1, and local DEM assets remain in their existing local metadata/readiness lanes.

## Commands

Build the public/open source manifests:

```powershell
uv run python scripts/build_public_reference_manifest.py
```

Run without live page scraping when you only want deterministic seed rows:

```powershell
uv run python scripts/build_public_reference_manifest.py --offline
```

Refresh CDSE no-download metadata snapshots:

```powershell
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024_sentinel2 --output outputs/cdse_mae_sai_2024_sentinel2_metadata.csv
uv run python scripts/query_cdse_metadata.py --profile hat_yai_2025_sentinel2 --output outputs/cdse_hat_yai_2025_sentinel2_metadata.csv
```

Use dry-run first when reviewing the OData URLs:

```powershell
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024 --dry-run
uv run python scripts/query_cdse_metadata.py --profile mae_sai_2024_sentinel2 --dry-run
```

## What To Use First

1. Use `outputs/cdse_mae_sai_2024_metadata.csv` to keep the existing Mae Sai Sentinel-1 pre/post planning pair grounded in live CDSE metadata.
2. Inspect `outputs/sentinel_asia_public_product_links.csv` for GIS/shapefile ZIP candidates. If one looks relevant, download it outside Git, record checksum and terms, inspect whether it contains flood geometry, then update the reference-mask gates.
3. Use Sentinel-2 metadata only for optical context and cloud-screened visual support. It is not a flood label.
4. Use WorldPop, OSM, Copernicus DEM, and HDX COD-AB as open context layers after they are added to file-level manifests with local paths and checksums outside Git.

## Current Boundaries

The public source manifests are not operational products and not official warnings. They do not prove real flood-detection accuracy, and they do not clear ML-label gates. Real validation still requires a legal flood reference geometry, local paths, SHA-256 checksums, and processing gates.

The public source manifest does not clear ML-label gates by itself.
