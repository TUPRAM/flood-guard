# MBRSC Reference-Mask Clearance Memo

Status: not cleared for validation metrics, derived reporting, redistribution, or ML labels; specifically, not cleared for ML labels.

Date: 2026-07-09

## Purpose

This memo records whether the Sentinel Asia / MBRSC `MBRSC_THAILAND_FLOOD-MAP-SHP.zip` product can be used as the Mae Sai 2024 validation reference mask for FloodGuard.

It is a project decision record, not legal advice. It exists to keep the real-data gate honest before any real non-ML SAR baseline or ML experiment starts.

## Reviewed Evidence

| Evidence | Finding | Gate impact |
| --- | --- | --- |
| Sentinel Asia Northern Thailand 2024 event page | Public page lists the MBRSC product as `DETECTED FLOOD WATER IN NORTHERN PROVINCES OF THAILAND`, observed by Sentinel-1 on 2024-09-15. | Supports public reference-candidate status only. |
| Sentinel Asia general framework page | Sentinel Asia distributes satellite imagery/data permitted by data providers and value-added images; DPN data policy controls access. | Does not provide product-level permission for this MBRSC shapefile. |
| Sentinel Asia DPN procedure | Supplier copyright applies; copyright marks are required on images/derived products; Sentinel Asia outputs are humanitarian, academic, and non-commercial; some DPN-provided data may not be distributed to third parties. | Useful policy context, but not enough to clear validation metrics, demo screenshots, redistribution, or ML-label use. |
| MBRSC ZIP members | ZIP contains only shapefile components and `Thailand_flood.shp.xml`; no README, license, terms, or citation file is present. | No embedded product-level clearance found. |
| `Thailand_flood.shp.xml` embedded metadata | Metadata records ArcGIS lineage, RasterToPolygon/Merge/Project/Clip processing, EPSG:32647, fields, and feature-class metadata. It does not include use constraints, access constraints, license, redistribution, attribution text, or ML-label permission. | Confirms technical provenance, not legal clearance. |
| QGIS/GDAL spatial QA | Geometry is WGS84 polygon data with Mae Sai review-bbox overlap and floodplain-aligned candidate patches. | Supports geometry usefulness only; does not clear use terms. |
| Visual QA notes | Polygons are not one broad event boundary and broadly align east/southeast of Mae Sai, but exact Mae Sai point is not inside a candidate polygon and fragments require manual QA. | Supports reference-candidate planning only. |

## Use Decision

Do not use it yet as validation truth, redistributed geometry, supervised ML labels, official flood observation, or an official warning product.

| Use case | Decision | Reason |
| --- | --- | --- |
| Keep source ZIP outside Git | allowed | The file is public and already checksum-tracked outside Git. |
| Inspect package metadata and geometry locally | allowed | Local inspection is necessary to decide whether the product is a useful reference candidate. |
| Use as planning/reference candidate | allowed with caveats | Public page and geometry support candidate status, but not validation truth. |
| Compute private exploratory metrics | not cleared | Current policy evidence does not explicitly authorize non-designated third-party analysis or derived validation metrics. |
| Publish/report IoU, F1/Dice, precision, recall, area error | blocked | Derived validation reporting is not explicitly cleared for this product. |
| Use screenshots or demo maps from this layer | unresolved/blocked | General policy requires copyright marks, but product-specific screenshot/demo permission is not clear. |
| Redistribute source, clipped, or simplified geometry | blocked | General policy says some DPN data may not be distributed to third parties; this product's redistribution/reference-only status is not explicit. |
| Use as supervised ML labels | blocked | No explicit ML-label permission exists. |
| Treat as official flood observation or warning | blocked | FloodGuard is non-operational and not an official warning system. |

## Gate Decision

Do not set `processing_allowed=True` for the MBRSC reference-mask row.

Do not change `blocking_decision` to `cleared_for_local_validation`.

Keep current status:

- `local_analysis_allowed=unresolved`
- `derived_metrics_allowed=unresolved`
- `screenshots_demo_allowed=unresolved`
- `redistribution_allowed=unresolved`
- `ml_label_use_allowed=unresolved`
- `blocking_decision=blocked_product_terms_unresolved`
- `reference_mask_status=candidate_geometry_inspected_not_cleared`

This means real Mae Sai non-ML SAR extraction and validation metrics remain blocked, even though the CDSE Sentinel-1 pre/post source files are downloaded outside Git and checksum-tracked.

## What Would Clear The Gate

One of these is required:

1. Written reply from Sentinel Asia, MBRSC, JAXA, or another authorized product owner confirming local validation metrics and derived reporting are allowed.
2. A public product-specific license or terms page that explicitly allows local analysis, derived metrics/reporting, screenshots/demo use, and redistribution/reference-only status for the MBRSC shapefile.
3. A replacement reference mask with clearer license terms that permits local validation metrics and derived reporting.

ML-label use remains a separate gate. Even if local validation metrics are cleared, ML labels must stay blocked unless explicitly allowed.

## Exact Follow-Up Ask

Ask Sentinel Asia / MBRSC / JAXA for a written response to these fields:

- Can FloodGuard use the shapefile locally for validation metrics against Sentinel-1 derived flood outputs?
- Can FloodGuard report derived metrics such as IoU, F1/Dice, precision, recall, and area error?
- Can FloodGuard show screenshots or simplified derived maps in a non-commercial hackathon/demo presentation?
- Must the source geometry remain reference-only and outside Git?
- Is clipped/simplified derived geometry redistributable, or blocked?
- Is use as weak labels or supervised ML labels allowed?
- What exact attribution/citation text is required?
- What disclaimer text is required?

## Interim Work Allowed

While waiting for clearance:

- Keep the MBRSC source ZIP outside Git.
- Keep only redacted path hints, SHA-256 checksums, feature counts, bbox metadata, QA notes, and decision records in the repo.
- Continue preparing extractor code against synthetic fixtures or blocked dry-run manifests.
- Do not read the MBRSC geometry as validation truth in real baseline code.
- Do not compute or publish real validation metrics against MBRSC.
- Do not train ML on MBRSC geometry.
