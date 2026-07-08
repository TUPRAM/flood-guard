# Sentinel Asia / MBRSC Product Terms Review

Status: terms unresolved; keep as `reference_candidate`, not validation truth and not ML labels.

## Reviewed Source

- Event page: https://sentinel-asia.org/EO/2024/article20240910TH.html
- Selected product: `MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- Product description on event page: `DETECTED FLOOD WATER IN NORTHERN PROVINCES OF THAILAND`, observed by Sentinel-1 image on 15 September 2024.
- Local file: outside Git at `<external_data_workspace>/sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip`
- SHA-256: recorded in `outputs/public_reference_file_inspection_manifest.csv`

## What Is Clear

- The Sentinel Asia event page is public and lists downloadable products for the Northern Thailand flood event.
- The selected MBRSC product is a public shapefile ZIP link on the event page.
- The event page states the disaster type is flood, the country is Thailand, the occurrence date is 10 September 2024, and the requester is GISTDA.
- The selected product is described as detected flood water in northern provinces of Thailand from a 15 September 2024 Sentinel-1 image.
- QGIS/GDAL inspection confirms the ZIP contains a polygon shapefile over northern Thailand with Mae Sai review-bbox overlap.

## What Is Not Clear

- No product-level license text was found in the event page or embedded shapefile metadata during this review.
- Reuse for published validation metrics is not explicitly cleared.
- Screenshot/demo use is not explicitly cleared.
- Redistribution or reference-only status is not explicitly cleared.
- Use as ML labels is not explicitly cleared.
- Provider citation text and disclaimer wording are not locked.

## Current Decision

Use the MBRSC shapefile as the first public Mae Sai reference-candidate lane for geometry review and planning.

Do not use it yet as:

- a final validation mask
- a redistributed data layer
- supervised ML labels
- an official flood observation
- an official warning product

## Required Next Action

1. Open the layer in QGIS and complete human visual QA against a basemap and known Mae Sai flood context.
2. Confirm product-level terms with Sentinel Asia / MBRSC / JAXA or a public license source.
3. If local validation metrics are allowed, update `docs/reference_mask_licensing_log.md`.
4. If redistribution is reference-only, keep the source ZIP and any derived clipped geometry outside Git.
5. If ML-label use is not explicitly allowed, keep any model experiment scoped as weak-label research only or do not train on this source.

## Decision Fields

| Use | Current status | Reason |
| --- | --- | --- |
| Geometry review | allowed as local candidate review | Public product file is accessible and checksum-tracked outside Git. |
| Local validation metrics | unresolved | Product-level terms were not found. |
| Screenshots/demo | unresolved | Product-level terms were not found. |
| Derived metrics | unresolved | Product-level terms were not found. |
| Redistribution | unresolved | Product-level terms were not found. |
| ML-label use | blocked/unresolved | Explicit label-use permission was not found. |

