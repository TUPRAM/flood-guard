# Sentinel Asia / MBRSC Mae Sai Visual QA Notes

Status: visual QA complete for reference-candidate planning; not validation truth and not ML labels.

## Scope

This review checks whether the Sentinel Asia / MBRSC public shapefile looks like flood-water extent geometry over the Mae Sai review area, or whether it looks like broad event polygons/noise.

Source layer:

- Event page: https://sentinel-asia.org/EO/2024/article20240910TH.html
- Product: `MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- Layer: `Thailand_flood`
- Local source file: outside Git at `<external_data_workspace>/sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- Review bbox: `99.72,20.30,100.03,20.56`
- Mae Sai point: `99.88,20.43`

Temporary review artifacts were created under `<temp>/floodguard_qgis_visual_qa/` and were not committed. No shapefile copy, clipped geometry, screenshot, or source imagery is committed.

## Method

- Opened the external ZIP through the installed QGIS/GDAL stack using `/vsizip/.../Thailand_flood.shp`.
- Clipped a temporary review GeoJSON to the Mae Sai review bbox outside the repository.
- Rendered a temporary vector overlay of the MBRSC polygons against OSM waterway/water-body vectors.
- Used QGIS/GDAL `ogrinfo` SQL checks for local point/core/floodplain counts.

Tools:

- QGIS/GDAL: `GDAL 3.13.0 "Iowa City", released 2026/05/04`
- OSM vector comparison: temporary Overpass water-feature extract, not committed

## Spatial QA Findings

| Check | Result |
| --- | --- |
| Exact Mae Sai point `99.88,20.43` intersects MBRSC polygon | no |
| Small core box `99.84,20.40,99.92,20.46` | 16 features, about 0.329 km2 area-field sum |
| East/southeast floodplain box `99.90,20.30,100.03,20.56` | 477 features, about 46.449 km2 area-field sum |
| Western review box `99.72,20.30,99.84,20.56` | 0 features |
| Full Mae Sai review bbox | 514 features, about 47.164 km2 area-field sum |

## Interpretation

- The layer does not look like a single broad event boundary. It is made of many raster-to-polygon flood-water candidate polygons.
- The strongest concentration is east and southeast of the Mae Sai point, broadly aligned with the floodplain and waterway network visible in the OSM water-vector comparison.
- The exact Mae Sai point is not inside a flood polygon, so this source should not be interpreted as "Mae Sai town point flooded" without more local context.
- The layer includes many small fragmented polygons. Some likely represent valid water/inundated lowland patches, but some may be SAR speckle, field-water, or extraction noise.
- The source covers broader northern Thailand, not only Mae Sai. Any validation use would need clipping, manual QA, and clear product terms.

## QA Decision

Use the MBRSC shapefile as a practical public reference-candidate lane for Mae Sai planning and weak/manual QA.

Do not use it yet as:

- a final validation mask
- a redistributed data layer
- supervised ML labels
- an official flood observation
- an official warning product

## Remaining Blockers

- Product-level terms for validation metrics, screenshots/demo, derived metrics, redistribution, and ML-label use are still unresolved.
- Human QA should be repeated in the QGIS GUI with any locally approved basemap before final local validation.
- CDSE Sentinel-1 pre/post source files are downloaded outside Git and SHA-256 checksums are recorded, but they still cannot be used for the real baseline until reference-mask status clears.
- `outputs/mae_sai_real_data_file_manifest.csv` still fails the real baseline gate.

## Next Action

1. Confirm product-level reuse terms with Sentinel Asia / MBRSC / JAXA or another public license source.
2. If local validation metrics and derived reporting are allowed, update `docs/reference_mask_licensing_log.md` to a cleared validation status.
3. Acquire CDSE Sentinel-1 source files outside Git with credentials/token and record SHA-256 checksums.
4. Rerun `uv run python scripts/validate_mae_sai_file_manifest.py` without `--allow-blocked`.
5. Start real non-ML SAR extraction only after the manifest passes.
