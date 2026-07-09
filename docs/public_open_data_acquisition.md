# Public Open-Data Acquisition Lane

Status: metadata and public-link inventory created. No source imagery, product ZIPs, GeoTIFFs, SAFE packages, NetCDF, GRIB, or raw mask files are committed.

This lane exists because UNOSAT/GISTDA replies may be slow. It lets FloodGuard move forward with public/open sources while keeping the repository clean and the real validation gates honest.

## What Was Captured

Generated outputs:

- `outputs/public_reference_candidate_manifest.csv`
- `outputs/sentinel_asia_public_product_links.csv`
- `outputs/public_reference_file_inspection_manifest.csv`
- `outputs/sentinel_asia_geometry_quality_review.csv`
- `docs/sentinel_asia_geometry_quality_notes.md`
- `outputs/sentinel_asia_mbrsc_visual_qa_review.csv`
- `docs/sentinel_asia_mbrsc_visual_qa_notes.md`
- `docs/sentinel_asia_product_terms_review.md`
- `outputs/sentinel_asia_product_terms_review.csv`
- `outputs/cems_product_candidate_manifest.csv`
- `outputs/mae_sai_reference_candidate_decision.md`
- `outputs/open_context_data_file_manifest.csv`
- `outputs/cdse_mae_sai_acquisition_manifest.csv`
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
| `sentinel_asia_geometry_quality_review.csv` | 1 | QGIS/GDAL geometry quality review row. |
| `sentinel_asia_mbrsc_visual_qa_review.csv` | 1 | Notes-only visual QA row; no shapefile or image artifacts committed. |
| `sentinel_asia_product_terms_review.csv` | 1 | Conservative product-terms decision row. |
| `cems_product_candidate_manifest.csv` | 46 | CEMS EMSR754/EMSR756 AOI/product metadata rows. |
| `mae_sai_reference_candidate_decision.md` | 1 note | Current public reference-candidate comparison and gate decision. |
| `open_context_data_file_manifest.csv` | 4 | Planned WorldPop, HDX COD-AB, Geofabrik OSM, and Copernicus DEM context rows. |
| `cdse_mae_sai_acquisition_manifest.csv` | 2 | Selected pre/post Sentinel-1 acquisition rows; currently blocked without CDSE credentials. |
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
- QGIS/GDAL review confirms `6506` full-layer features, `514` Mae Sai review-bbox intersecting features, about `464.234` km2 full-layer area-field sum, and about `47.164` km2 Mae Sai review-bbox area-field sum. This is geometry QA evidence, not final validation clearance.
- Visual QA indicates the layer is not a single broad event boundary. Candidate polygons concentrate east/southeast of the Mae Sai point and broadly align with floodplain/waterway context, but fragmented patches remain and the exact Mae Sai point is not inside a candidate polygon.
- Sentinel Asia / MBRSC product terms remain unresolved for validation metrics, screenshots/demo, derived metrics, redistribution, and ML-label use. The general Sentinel Asia DPN procedure says supplying-agency copyright applies, derived products need copyright marks, outputs are humanitarian/academic/non-commercial, and some DPN-provided data may not be distributed to third parties; that is useful context but not product-specific clearance for this MBRSC shapefile.
- CDSE Sentinel-1 products are free/full/open Sentinel data, but product download through CDSE requires an access token or account credentials. The repo records a blocked acquisition manifest when credentials are absent.
- UNOSAT/UNITAR public pages remain report/citation evidence unless redistributable geometry and derivative-use terms are confirmed.
- NASA flood products are coarse context/proxy candidates, not subdistrict/road-scale validation labels.
- WorldPop, OSM/Geofabrik, Copernicus DEM, and HDX COD-AB are decision-layer context sources, not flood labels.
- THEOS-2, local Sentinel-1, and local DEM assets remain in their existing local metadata/readiness lanes.

## Commands

Build the public/open source manifests:

```powershell
uv run python scripts/build_public_reference_manifest.py
uv run python scripts/inspect_sentinel_asia_reference_candidate.py
uv run python scripts/review_sentinel_asia_geometry_quality.py
uv run python scripts/resolve_cems_products.py
uv run python scripts/build_mae_sai_reference_decision.py
uv run python scripts/build_open_context_manifest.py
uv run python scripts/acquire_cdse_mae_sai_sentinel1.py
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
2. Use `outputs/public_reference_file_inspection_manifest.csv`, `outputs/sentinel_asia_geometry_quality_review.csv`, and `outputs/sentinel_asia_mbrsc_visual_qa_review.csv` as the first public Mae Sai reference-candidate evidence. The geometry is useful because it is WGS84 polygon data, intersects the Mae Sai review bbox, has area-field metadata, and visually aligns with the east/southeast floodplain/waterway context. It remains blocked for validation until product terms are clear and the QA is repeated with any required approved basemap/source context.
3. Use Sentinel-2 metadata only for optical context and cloud-screened visual support. It is not a flood label.
4. Use WorldPop, OSM, Copernicus DEM, and HDX COD-AB as open context layers after they are added to file-level manifests with local paths and checksums outside Git.

## Current Boundaries

The public source manifests are not operational products and not official warnings. They do not prove real flood-detection accuracy, and they do not clear ML-label gates. Real validation still requires a legal flood reference geometry, local paths, SHA-256 checksums, and processing gates.

The public source manifest does not clear ML-label gates by itself.
