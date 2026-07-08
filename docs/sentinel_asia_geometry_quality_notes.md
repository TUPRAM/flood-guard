# Sentinel Asia Geometry Quality Notes

Status: reference candidate, not validation truth and not ML labels.

## QGIS/GDAL Inspection

- Tool: `GDAL 3.13.0 "Iowa City", released 2026/05/04`
- Layer: `Thailand_flood`
- Geometry: `Polygon`
- CRS: `4326`
- Attribute fields: `Id: Integer64 (10.0)|gridcode: Integer64 (10.0)|Area: Real (13.11)`
- DBF update date: `2024-09-16`

## Spatial Findings

- Full layer features: 6506
- Full layer area field sum: 464.234 km2
- Mae Sai review bbox: `99.72,20.3,100.03,20.56`
- Mae Sai-intersecting features: 514
- Mae Sai-intersecting area field sum: 47.164 km2
- Gridcode values: `1`

## Interpretation

- The layer is much broader than Mae Sai, but it contains many polygon features intersecting the Mae Sai review bbox.
- The shapefile metadata lineage indicates a raster-to-polygon flood workflow and an area field calculated in square meters.
- This supports treating the file as a practical public flood-water reference candidate for Mae Sai review, not as cleared validation truth.

## Remaining Blockers

- Product-level terms for validation metrics, screenshots, derived metrics, redistribution, and ML-label use are unresolved.
- Human visual QA in QGIS should inspect polygon alignment against basemap, river corridor, and known Mae Sai flood reports.
- Do not run the real non-ML SAR baseline until the Mae Sai file manifest passes without `--allow-blocked`.

## How To Open In QGIS

1. Open QGIS.
2. Add vector layer from the external ZIP path:
   `<external_data_workspace>/sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip`.
3. Select layer `Thailand_flood`.
4. Add an OpenStreetMap or other allowed basemap.
5. Zoom to Mae Sai around `99.88, 20.43`.
6. Confirm whether polygons align with plausible flood-water areas, not only broad event extents.
