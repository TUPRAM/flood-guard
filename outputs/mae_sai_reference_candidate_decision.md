# Mae Sai Public Reference Candidate Decision

Status: provisional public geometry candidate selected; real validation remains blocked.

## Selected Candidate

- Candidate: Sentinel Asia Northern Thailand 2024 MBRSC flood shapefile
- Source URL: https://sentinel-asia.org/EO/2024/article20240910TH/MBRSC/MBRSC_THAILAND_FLOOD-MAP-SHP.zip
- SHA-256: 6cb146e92306611be433b52b63832b4721040a399b50c4c3d217c50798b642b7
- Geometry type: Polygon
- CRS: GCS_WGS_1984
- Bbox: 98.85665264, 18.96695786, 100.73372049, 20.58158308
- Mae Sai point inside bbox: True

## Comparison

- Sentinel Asia: first practical public geometry candidate because the downloaded external ZIP contains WGS84 polygon shapefile members and the Mae Sai point falls inside the shapefile bbox.
- CEMS EMSR754/EMSR756: resolved through public API, but current product rows with Mae Sai relevance = 0. The inspected activations are not better Mae Sai candidates.
- UNOSAT public report: useful citation and area/population sanity check, but no redistributable GIS geometry has been confirmed.
- NASA flood products: useful coarse temporal/context evidence, but too coarse for subdistrict or road-level validation.

## Gate Decision

Use the Sentinel Asia MBRSC shapefile as the first public reference-candidate lane, not as a cleared validation mask and not as ML labels.

Processing remains blocked until product-level terms, redistribution/reference-only status, geometry quality, local-file record, and reference-mask status are explicitly cleared.