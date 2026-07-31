# MBRSC Reference-Mask Clearance Memo

Status: not cleared for validation metrics, derived reporting, redistribution, or ML labels; specifically, not cleared for ML labels.

Original decision date: 2026-07-09

Primary-source recheck: 2026-07-20

## Purpose

This memo records whether the Sentinel Asia / MBRSC
`MBRSC_THAILAND_FLOOD-MAP-SHP.zip` product can be used to produce the Mae Sai
2024 validation reference for FloodGuard. The ZIP itself is vector geometry; it
is not the single-band binary raster required by the controlled experiment.

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

## 2026-07-20 Primary-Source Recheck

| Primary source | Verified finding | Decision impact |
| --- | --- | --- |
| [Copernicus Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice) | Lawful reproduction, distribution, public communication, adaptation, modification, and combination of Sentinel data are permitted. Unmodified data require `Copernicus Sentinel data 2024`; adapted products require `Contains modified Copernicus Sentinel data 2024`. | Clears the source-rights basis for the product-identified Sentinel-1 input pair with attribution. It does not transfer rights in MBRSC's separate value-added geometry and is not an independently keyed authority receipt. |
| [Copernicus Data Space terms](https://dataspace.copernicus.eu/terms-and-conditions) | Sentinel product data are governed by the Sentinel legal notice; other portal content has separate restrictions. | The selected SAFE product bytes can use the Sentinel notice, but portal-wide wording must not be generalized to unrelated content. |
| [Sentinel Asia Northern Thailand event page](https://sentinel-asia.org/EO/2024/article20240910TH.html) | The page publicly lists the MBRSC detected-flood-water product as observed from Sentinel-1 on 15 September 2024 and links the shapefile ZIP. | Confirms public product identity and candidate timing only. A download link is not product-specific permission for ML labels, validation metrics, derived reporting, screenshots, or redistribution. |
| [Sentinel Asia DPN procedure](https://sentinel-asia.org/e-learning/SentinelAsiaProcedures/PDPN.pdf) | Supplying-agency copyright applies; copyright marks are required; outputs are limited to humanitarian, academic, and non-commercial use; DPN-provided data may be restricted from third-party distribution. | Reinforces the need for a product-owner decision. It does not clear FloodGuard as a designated analyst or resolve product-specific derivative/redistribution rights. |
| [UNOSAT Product 3991](https://unosat.org/products/3991) | The public page currently exposes a PDF, describes cumulative satellite-detected water for 13–19 September 2024, and states that the analysis is preliminary and not yet field-validated. | Useful independent event context, but not a qualified pixel/cell reference, not an immutable GIS mask exposed by the page, and not a substitute for MBRSC clearance. |
| [GISTDA disaster open API](https://disaster.gistda.or.th/services/open-api) and [dataset record](https://opendata.gistda.or.th/th/dataset/disasters-03) | Public flood endpoints expose rolling 1-, 3-, 7-, and 30-day windows. | A current rolling response is not an immutable September 2024 Mae Sai reference. Qualification requires a historical product ID, observation interval, frozen bytes/checksum, licence, and authority decision. |

The inspected Sentinel-1 source pair and the MBRSC geometry therefore have
different rights chains. Open Sentinel source rights cannot be used to infer
permission over the MBRSC value-added product.

## Provider Source Versus Qualified Reference Artifact

The provider ZIP and the controlled experiment's `reference_mask` are different
artifacts with different checksums and review obligations:

| Artifact | Permitted current role | Controlled-experiment status |
| --- | --- | --- |
| `MBRSC_THAILAND_FLOOD-MAP-SHP.zip` (SHA-256 `6cb146e92306611be433b52b63832b4721040a399b50c4c3d217c50798b642b7`) | Outside-Git provider provenance, metadata inspection, and candidate-geometry planning | Blocked for validation truth, ML labels, derived reporting, screenshots, and redistribution until product-specific rights are attributable |
| Future qualified event-reference GeoTIFF | Exact executable `reference_mask` bound into acquisition, reviewer, partition, and reference-cell receipts | Missing; it must be immutable, single-band, georeferenced, binary `0/1`, use explicit distinct nodata, match the frozen equal-area CRS, cover every frozen cell centre, and have its own product/version identity and SHA-256 |

Rasterizing the MBRSC polygons would create a derived artifact; it would not
resolve the missing rights, timing, uncertainty, reviewer-calibration, or
scientific-qualification evidence. The vector ZIP's checksum must never be used
as the checksum of a derived raster.

## Use Decision

Do not use it yet as validation truth, redistributed geometry, supervised ML labels, official flood observation, or an official warning product.

| Use case | Decision | Reason |
| --- | --- | --- |
| Keep source ZIP outside Git | allowed | The file is public and already checksum-tracked outside Git. |
| Inspect package metadata and geometry locally | allowed | Local inspection is necessary to decide whether the product is a useful reference candidate. |
| Use as planning/reference candidate | allowed with caveats | Public page and geometry support candidate status, but not validation truth and not the executable `reference_mask`. |
| Compute private exploratory metrics | not cleared | Current policy evidence does not explicitly authorize non-designated third-party analysis or derived validation metrics. |
| Publish/report IoU, F1/Dice, precision, recall, area error | blocked | Derived validation reporting is not explicitly cleared for this product. |
| Use screenshots or demo maps from this layer | unresolved/blocked | General policy requires copyright marks, but product-specific screenshot/demo permission is not clear. |
| Redistribute source, clipped, or simplified geometry | blocked | General policy says some DPN data may not be distributed to third parties; this product's redistribution/reference-only status is not explicit. |
| Use as supervised ML labels | blocked | No explicit ML-label permission exists. |
| Treat as official flood observation or warning | blocked | FloodGuard is non-operational and not an official warning system. |

## Gate Decision

Do not substitute the MBRSC ZIP into the pending qualified-raster row and do not
set that row's `processing_allowed=True` from the current evidence.
Do not set `processing_allowed=True` for an MBRSC-derived reference artifact
until both the full rights matrix and independent scientific qualification pass.

Do not change `blocking_decision` to `cleared_for_local_validation`.

Keep current status:

- `local_analysis_allowed=unresolved`
- `derived_metrics_allowed=unresolved`
- `screenshots_demo_allowed=unresolved`
- `redistribution_allowed=unresolved`
- `ml_label_use_allowed=unresolved`
- `blocking_decision=blocked_product_terms_unresolved`
- `reference_mask_status=candidate_geometry_inspected_not_cleared`

No independently keyed acquisition/licensing authority receipt covering all
three controlled-experiment input roles can be issued from the evidence currently
available. The Sentinel input rows have a defensible public-terms basis, but the
reference-mask row does not. An internal HMAC, self-attestation, filled request,
public URL, or checksum would provide integrity or traceability only; none would
manufacture missing provider permission or scientific qualification.

An HMAC also is not a public or legally non-repudiable agency signature. In the
repository workflow it is only an integrity mechanism when each named role holds
a distinct trusted secret. Formal cross-organization acceptance requires the
original provider decision plus an externally verifiable asymmetric or managed
signature whose signer identity and authority can be independently checked.

This means the controlled Mae Sai comparison and any reference-dependent
validation metrics remain blocked, even though the CDSE Sentinel-1 pre/post
source files are downloaded outside Git and checksum-tracked. Independent
Sentinel preprocessing, if performed under its own approved scope, is not a
substitute for this missing reference gate.

## What Would Clear The Gate

One of these is required:

1. Written reply from Sentinel Asia, MBRSC, JAXA, or another authorized product
   owner confirming the complete requested use matrix, including local analysis,
   ML/model development, validation metrics, derived reporting, screenshots,
   and redistribution or reference-only handling.
2. A public product-specific licence or terms page that explicitly allows the
   same uses for the MBRSC shapefile and its intended rasterized/adjudicated
   derivative.
3. A replacement reference source with clearer terms that permits local
   analysis, ML/model development, validation metrics, derived reporting,
   screenshots/demo use, and an explicit redistribution or reference-only
   policy.

Whichever source is approved must then be converted, reviewed, and signed as a
new immutable binary raster. Rights clearance alone does not qualify scientific
truth, and reviewer qualification alone does not grant rights.

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
- May FloodGuard create and retain an immutable rasterized/adjudicated derivative
  for controlled evaluation, and what attribution must that derivative carry?

Use the machine-fillable request at
`docs/controlled-experiment/external_authority_decision_request.template.json`.
It requires exact product identities and hashes, permission-by-use decisions,
signer identity and authority, issue/expiry, attribution, and a non-approval
default. Do not change `decision_status` until attributable external evidence is
returned and independently checked against the structured transcription.

## Interim Work Allowed

While waiting for clearance:

- Keep the MBRSC source ZIP outside Git.
- Keep only redacted path hints, SHA-256 checksums, feature counts, bbox metadata, QA notes, and decision records in the repo.
- Continue preparing extractor code against synthetic fixtures or blocked dry-run manifests.
- Do not read the MBRSC geometry as validation truth in real baseline code.
- Do not compute or publish real validation metrics against MBRSC.
- Do not train ML on MBRSC geometry.
