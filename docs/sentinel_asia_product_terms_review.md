# Sentinel Asia / MBRSC Product Terms Review

Status: terms unresolved; keep as `reference_candidate`, not validation truth and not ML labels.

## Reviewed Source

- Event page: https://sentinel-asia.org/EO/2024/article20240910TH.html
- Sentinel Asia general DPN procedure: https://sentinel-asia.org/e-learning/SentinelAsiaProcedures/PDPN.pdf
- Clearance decision memo: `docs/mbrsc_reference_mask_clearance_memo.md`
- Selected product: `MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- Product description on event page: `DETECTED FLOOD WATER IN NORTHERN PROVINCES OF THAILAND`, observed by Sentinel-1 image on 15 September 2024.
- Local file: outside Git at `<external_data_workspace>/sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- SHA-256: recorded in `outputs/public_reference_file_inspection_manifest.csv`

## What Is Clear

- The Sentinel Asia event page is public and lists downloadable products for the Northern Thailand flood event.
- The selected MBRSC product is a public shapefile ZIP link on the event page.
- The event page states the disaster type is flood, the country is Thailand, the occurrence date is 10 September 2024, and the requester is GISTDA.
- The selected product is described as detected flood water in northern provinces of Thailand from a 15 September 2024 Sentinel-1 image.
- The local ZIP contains `Thailand_flood.shp.xml`; embedded metadata records ArcGIS lineage, EPSG:32647 metadata, shapefile fields, and processing history, but no license, access constraints, use constraints, redistribution terms, or ML-label permission.
- QGIS/GDAL inspection confirms the ZIP contains a polygon shapefile over northern Thailand with Mae Sai review-bbox overlap.
- QGIS/GDAL visual QA on 2026-07-09 supports treating the layer as flood-water reference-candidate geometry rather than a broad event boundary, but the layer still needs product-term clearance before validation use.
- Sentinel Asia general documentation says distributed data include satellite imagery/data permitted by the data provider and value-added images; it does not provide product-specific reuse terms for this MBRSC shapefile.
- Sentinel Asia DPN procedure says supplier copyright rules apply to data/products supplied through Sentinel Asia, copyright marks should appear on images or derived products, outputs are for humanitarian, academic, and non-commercial purposes, and some data supplied by a Data Provider Node may not be distributed to third parties. This is useful policy context, but it still does not explicitly clear FloodGuard validation metrics, screenshots/demo use, redistribution/reference-only status, or ML-label use for this MBRSC product.

## What Is Not Clear

- No product-level license text was found in the event page, embedded shapefile metadata, or general Sentinel Asia policy documents during this review.
- The general Sentinel Asia policy does not identify whether MBRSC, Sentinel Asia, JAXA, or another provider can approve this exact public shapefile for local validation metrics and derived reporting.
- Reuse for published validation metrics is not explicitly cleared.
- Screenshot/demo use is not explicitly cleared.
- Redistribution or reference-only status is not explicitly cleared.
- Use as ML labels is not explicitly cleared.
- Provider citation text and disclaimer wording are not locked.

## Current Decision

Use the MBRSC shapefile as the first public Mae Sai reference-candidate lane for geometry review and planning.

`docs/mbrsc_reference_mask_clearance_memo.md` is the current controlling project decision record. It explicitly says not to set `processing_allowed=True`, not to change `blocking_decision` to `cleared_for_local_validation`, and not to use this source for real validation metrics or ML labels until product-level terms are cleared.

Do not use it yet as:

- a final validation mask
- a source for published IoU, F1/Dice, precision, recall, or area-error metrics
- a redistributed data layer
- supervised ML labels
- an official flood observation
- an official warning product

## Required Next Action

1. Confirm product-level terms with Sentinel Asia / MBRSC / JAXA or a public license source.
2. If local validation metrics are allowed, update `docs/reference_mask_licensing_log.md`.
3. If redistribution is reference-only, keep the source ZIP and any derived clipped geometry outside Git.
4. If ML-label use is not explicitly allowed, keep any model experiment scoped as weak-label research only or do not train on this source.

## Decision Fields

| Use | Current status | Reason |
| --- | --- | --- |
| Geometry review | allowed as local candidate review | Public product file is accessible and checksum-tracked outside Git. |
| Visual QA | complete for reference-candidate planning | Polygons are concentrated east/southeast of Mae Sai and broadly align with floodplain/waterway context, but manual QA and terms remain required. |
| Local validation metrics | unresolved | General Sentinel Asia policy was found, but product-level validation-metric permission was not found. |
| Screenshots/demo | unresolved | General Sentinel Asia policy requires copyright marks but does not explicitly clear demo screenshots for this product. |
| Derived metrics | unresolved | General Sentinel Asia policy requires attribution on derived products but does not explicitly clear derived validation reporting for this product. |
| Redistribution | unresolved | General Sentinel Asia policy says some DPN-provided data may not be distributed to third parties; this product's redistribution/reference-only status is not explicit. |
| ML-label use | blocked/unresolved | Explicit label-use permission was not found. |
