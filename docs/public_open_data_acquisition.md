# Public Open-Data Acquisition Lane

Status: metadata and public-link inventory created. No source imagery, product ZIPs, GeoTIFFs, SAFE packages, NetCDF, GRIB, or raw mask files are committed.

This lane exists because UNOSAT/GISTDA replies may be slow. It lets FloodGuard move forward with public/open sources while keeping the repository clean and the real validation gates honest.

## What Was Captured

Generated outputs:

- `outputs/public_reference_candidate_manifest.csv`
- `outputs/sentinel_asia_public_product_links.csv`
- `outputs/public_reference_file_inspection_manifest.csv`
- `outputs/cems_product_candidate_manifest.csv`
- `outputs/mae_sai_reference_candidate_decision.md`
- `outputs/open_context_data_file_manifest.csv`
- `outputs/cdse_mae_sai_2024_metadata.csv`
- `outputs/cdse_hat_yai_2025_metadata.csv`
- `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv`
- `outputs/cdse_hat_yai_2025_sentinel2_metadata.csv`

Current generated row counts:

| Output | Rows | Notes |
| --- | ---: | --- |
| `public_reference_candidate_manifest.csv` | 48 | Seed rows plus Sentinel Asia public product-link rows. |
| `sentinel_asia_public_product_links.csv` | 33 | Direct public links from the Northern Thailand 2024 Sentinel Asia event page. |
| `public_reference_file_inspection_manifest.csv` | 1 | External Sentinel Asia shapefile ZIP inspection result. |
| `cems_product_candidate_manifest.csv` | 46 | CEMS EMSR754/EMSR756 AOI/product metadata rows. |
| `mae_sai_reference_candidate_decision.md` | 1 note | Current public reference-candidate comparison and gate decision. |
| `open_context_data_file_manifest.csv` | 4 | Planned WorldPop, HDX COD-AB, Geofabrik OSM, and Copernicus DEM context rows. |
| `cdse_mae_sai_2024_metadata.csv` | 8 | Sentinel-1 Mae Sai event-window product metadata. |
| `cdse_hat_yai_2025_metadata.csv` | 10 | Sentinel-1 Hat Yai event-window product metadata. |
| `cdse_mae_sai_2024_sentinel2_metadata.csv` | 5 | Sentinel-2 L2A Mae Sai optical-context metadata. |
| `cdse_hat_yai_2025_sentinel2_metadata.csv` | 4 | Sentinel-2 L2A Hat Yai optical-context metadata. |

## Source Handling Rules

- CDSE Sentinel-1 and Sentinel-2 rows are product metadata only. They are not downloaded imagery.
- CEMS EMSR754 and EMSR756 rows are activation candidates. The public viewer page does not expose simple product links in static HTML, so exact product downloads remain a follow-up probe.
- CEMS API inspection resolved product rows for EMSR754 and EMSR756. Current rows do not cover Mae Sai, so CEMS is not the first Mae Sai reference candidate.
- Sentinel Asia Northern Thailand 2024 rows include public direct links, including JPG map/quicklook files, GIS ZIP candidates, and one shapefile ZIP candidate. These links are not automatically validation masks.
- The selected Sentinel Asia shapefile ZIP is downloaded outside Git and inspected. Current header/record metadata shows WGS84 polygon geometry, `6506` DBF records, bbox `98.85665264, 18.96695786, 100.73372049, 20.58158308`, the Mae Sai point inside the bbox, and parsed polygon record bboxes overlapping the Mae Sai review bbox.
- UNOSAT/UNITAR public pages remain report/citation evidence unless redistributable geometry and derivative-use terms are confirmed.
- NASA flood products are coarse context/proxy candidates, not subdistrict/road-scale validation labels.
- WorldPop, OSM/Geofabrik, Copernicus DEM, and HDX COD-AB are decision-layer context sources, not flood labels.
- THEOS-2, local Sentinel-1, and local DEM assets remain in their existing local metadata/readiness lanes.

## Commands

Build the public/open source manifests:

```powershell
uv run python scripts/build_public_reference_manifest.py
uv run python scripts/inspect_sentinel_asia_reference_candidate.py
uv run python scripts/resolve_cems_products.py
uv run python scripts/build_mae_sai_reference_decision.py
uv run python scripts/build_open_context_manifest.py
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
2. Use `outputs/public_reference_file_inspection_manifest.csv` as the first public Mae Sai reference-candidate evidence. It is useful because it is WGS84 polygon geometry whose bbox contains Mae Sai, but it remains blocked for validation until product terms and geometry quality are reviewed.
3. Use Sentinel-2 metadata only for optical context and cloud-screened visual support. It is not a flood label.
4. Use WorldPop, OSM, Copernicus DEM, and HDX COD-AB as open context layers after they are added to file-level manifests with local paths and checksums outside Git.

## Current Boundaries

The public source manifests are not operational products and not official warnings. They do not prove real flood-detection accuracy, and they do not clear ML-label gates. Real validation still requires a legal flood reference geometry, local paths, SHA-256 checksums, and processing gates.

The public source manifest does not clear ML-label gates by itself.
