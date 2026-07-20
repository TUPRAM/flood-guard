# Reference-Mask Licensing Log

This log tracks candidate flood reference-mask sources before controlled real-data
ingestion. It is planning documentation only. Existing outside-Git candidate
bytes may be retained and inspected as recorded below, but must not be ingested
as validation truth, redistributed, or processed into ML labels until access,
licence, attribution, intended derivative use, and redistribution status are
confirmed.

Primary-source status was rechecked on **2026-07-20**. Public availability is
not an authority decision, and an editable repository entry is never permission.
The machine-fillable request for an attributable external decision is
`docs/controlled-experiment/external_authority_decision_request.template.json`.

## Artifact Identity Boundary

The controlled experiment distinguishes provider provenance from the executable
reference artifact:

- `MBRSC_THAILAND_FLOOD-MAP-SHP.zip` is a checksummed **vector reference
  candidate and provenance source**. Its SHA-256 is
  `6cb146e92306611be433b52b63832b4721040a399b50c4c3d217c50798b642b7`.
- The acquisition-manifest role `reference_mask` must bind the final qualified,
  immutable **single-band binary georeferenced raster** used by the controlled
  evaluation. Valid pixels are exactly `0` (non-flood) or `1` (flood), nodata is
  explicit and distinct from both classes, and the CRS must exactly match the
  frozen equal-area analysis grid.
- Rasterization, clipping, adjudication, or other conversion creates a new
  derived artifact with a new product/version identity and SHA-256. The provider
  ZIP checksum cannot be copied onto that raster.
- Written rights must cover both the provider source and the intended derived
  raster uses: local analysis, supervised ML/model development, validation and
  metric calculation, derived reporting, screenshots/demo use, and either
  redistribution or explicit reference-only handling.

The committed acquisition manifest therefore carries a deliberately blocked
pending-raster row. It must not point the executable `reference_mask` role at the
MBRSC ZIP merely because that ZIP is publicly downloadable or checksummed.

| Source | Study area | Candidate use | URL | Geometry access status | License / access status | Redistribution status | Attribution / citation status | Current blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | Chiang Rai / Mae Sai 2024 | Independent event context and possible future reference target | https://unosat.org/products/3991 | Public product page currently exposes a PDF only; no machine-readable GIS mask is exposed there | request sent by project owner on 2026-07-03; provider response pending | unresolved | UNOSAT/UNITAR citation required if used; exact reusable-data citation text not locked | Product 3991 says the analysis is preliminary and not yet field-validated; PDF-only publication is not a qualified cell-level reference mask | obtain an immutable GIS artifact and written use terms, then independently qualify geometry and reference uncertainty |
| GISTDA official flood product candidate | Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025 | Event-specific authoritative reference candidate | https://disaster.gistda.or.th/services/open-api | Current public flood endpoints are rolling 1-, 3-, 7-, and 30-day API windows; no immutable September 2024 Mae Sai artifact is identified | Open Data Common is shown for the current flood-extent dataset, but that does not identify or freeze a September 2024 product | unresolved for an event archive | Exact product citation, version, and observation time are not locked | a current rolling API response cannot substitute for an immutable 2024 reference mask | obtain an event-specific archived product ID, observation interval, byte snapshot/checksum, licence record, and provider/reference-authority decision |
| Sentinel Asia / MBRSC Northern Thailand 2024 public shapefile | Chiang Rai / Mae Sai 2024 | Public reference-candidate geometry | https://sentinel-asia.org/EO/2024/article20240910TH.html | Public shapefile ZIP downloaded outside Git, checksummed, QGIS/GDAL-inspected, visually QA-reviewed, and embedded `Thailand_flood.shp.xml` metadata reviewed; Mae Sai review-bbox overlap confirmed | public file access confirmed; Sentinel Asia general policy says supplier copyright applies and outputs are humanitarian/academic/non-commercial, and embedded metadata has technical lineage but no license/use constraints; product-level validation/redistribution/ML terms remain unresolved | unresolved | Sentinel Asia / MBRSC attribution expected; general policy requires copyright marks on derived products; exact citation text not locked | product-level validation, derived-metric, redistribution/reference-only, screenshot/demo, and ML-label terms not complete; `docs/mbrsc_reference_mask_clearance_memo.md` keeps the gate blocked | confirm local validation, screenshots/demo, redistribution/reference-only, derived metrics, and ML-label terms |
| International Charter Activation 1004 | Hat Yai / Songkhla 2025 | Crisis mapping reference candidate | https://disasterscharter.org/activations/flood-in-thailand-activation-1004- | product geometry access not confirmed | access and attribution terms apply; details not locked | unresolved | Charter attribution required if products are used; exact citation not locked | product geometry and redistribution status not confirmed | confirm available products, access route, license, and citation terms |
| Sentinel Asia Southern Thailand 2025 | Hat Yai / Songkhla 2025 | Event detected-water or flood-proxy context | https://sentinel-asia.org/EO/2025/article20251119TH.html | product geometry access not confirmed | access and attribution terms apply; details not locked | unresolved | Sentinel Asia attribution required if products are used; exact citation not locked | product file access and redistribution status not confirmed | confirm product files, terms of use, and citation requirements |
| Academic or manual reference mask | Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025 | Fallback validation or manual reference candidate | `docs/manual_reference_mask_protocol.md` | manual QGIS protocol identified; source GeoPackage not yet created | project-owned weak-reference candidate once digitized; not official validation truth | reference_only; source GeoPackage remains outside Git | cite as FloodGuard manual weak-reference candidate with source-basis notes | manual file not yet digitized/checksummed; weak-reference status does not clear official validation or ML-label gates | create outside-Git GeoPackage, inspect with `scripts/inspect_manual_reference_mask.py`, and use only for candidate metrics |

## Current Rule

All reference-mask candidates remain blocked for qualified validation and
real-data ML. No final qualified binary raster is currently available.
The first real-data ingestion skeleton may create metadata manifests from these
rows, but it must not promote a candidate geometry to reference truth.
The reference-mask gate skeleton must not download source data or execute
flood-detection/model code while those rows remain blocked.
For the selected MBRSC candidate, **redistribution terms not confirmed** remains
an explicit blocker alongside validation, derived-reporting, and ML-label use.
Even if those rights are later cleared, an independent reference authority must
still qualify the event interpretation, observation interval, binary raster,
uncertainty/error strata, and reviewer/adjudication evidence.

The separately acquired Copernicus Sentinel-1 pre/post source pair is different:

- The official [Copernicus Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)
  permits lawful reproduction, distribution, public communication, adaptation,
  modification, and combination of Sentinel data.
- Public or distributed unmodified data require the notice
  `Copernicus Sentinel data 2024`; adapted products require
  `Contains modified Copernicus Sentinel data 2024`.
- Those terms support local processing and model-input use of the two identified
  Sentinel archives. They do **not** grant rights in the separately produced
  MBRSC/Sentinel Asia geometry, do not make that geometry scientific truth, and
  do not create the independently keyed acquisition-authority receipt required
  by the controlled experiment.
- The [Copernicus Data Space terms](https://dataspace.copernicus.eu/terms-and-conditions)
  distinguish Sentinel product data from other portal material; the Sentinel
  legal notice governs the selected Sentinel product bytes.

## Licensing Tracker V2

This execution tracker is the operational gate for reference-mask use. A source is not usable for real-data validation until `blocking_decision` is `cleared_for_local_validation` or a similarly explicit approved status. A source is not usable for ML labels until `ml_label_use_allowed` is explicitly `yes`. Blank dates mean no request or response has been recorded in this repository. Column names in downstream trackers should preserve `request_status`, `request_sent_date`, `response_date`, `geometry_access`, `local_analysis_allowed`, `derived_metrics_allowed`, `screenshots_demo_allowed`, `redistribution_allowed`, `citation_required`, `ml_label_use_allowed`, and `blocking_decision`.

| Source | Request status | Request sent date | Response date | Geometry access | Local analysis allowed | Derived metrics allowed | Screenshots/demo allowed | Redistribution allowed | Citation required | ML-label use allowed | Blocking decision | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | sent_waiting_response_pdf_only | 2026-07-03 | no_response | pdf_only_preliminary_not_field_validated | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_no_qualified_machine_readable_reference | obtain an immutable GIS mask, written rights, and independent scientific qualification; do not rasterize the PDF as truth |
| GISTDA official flood product candidate | sent_waiting_response_rolling_api_not_event_archive | 2026-07-03 | no_response | rolling_1_3_7_30_day_api_only | unresolved_for_immutable_2024_product | unresolved_for_immutable_2024_product | unresolved_for_immutable_2024_product | unresolved_for_immutable_2024_product | yes_expected | unresolved | blocked_no_immutable_sep_2024_reference | obtain a product-identified September 2024 artifact and freeze its response bytes, observation interval, checksum, terms, and authority decision |
| Sentinel Asia / MBRSC Northern Thailand 2024 public shapefile | visual_qa_complete_terms_unresolved | 2026-07-08 | no_provider_response | available_candidate_geometry | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_product_terms_unresolved | use `docs/mbrsc_reference_mask_clearance_memo.md` as the current blocked decision and confirm product-level terms before validation or ML use |
| International Charter Activation 1004 | draft_not_sent | not_sent | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_activation_product_terms_unconfirmed | request product access and reuse terms |
| Sentinel Asia Southern Thailand 2025 | draft_not_sent | not_sent | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_product_file_terms_unconfirmed | request detected-water/flood-proxy product terms |
| Academic or manual reference mask | protocol_ready_file_missing | not_applicable | no_provider_response | unresolved | candidate_metrics_only_after_file_ready | candidate_metrics_only_after_file_ready | candidate_demo_only_after_file_ready | reference_only | yes_project_notes | no | blocked_manual_file_missing_and_not_official_truth | create the outside-Git manual GeoPackage and keep official validation/ML-label gates blocked |

## Processing Gate

Legacy real-data ingestion manifests may set `processing_allowed=True` only
when all of the following generic gates are true:

- source license status is `confirmed`
- reference mask status is `confirmed`
- geometry access status is `confirmed` or `available`
- redistribution status is `redistributable` or `reference_only`
- product id is recorded
- local path is recorded outside the repository
- SHA-256 checksum is recorded

For the controlled experiment's `reference_mask` row, all of the following are
also mandatory:

- `license_status=confirmed_for_experiment`;
- `reference_mask_status=qualified_expert_or_adjudicated`;
- `local_analysis_allowed=true`;
- `derived_metrics_allowed=true`;
- `ml_label_use_allowed=true`;
- `temporal_alignment_status=confirmed`;
- `sha256_status=verified` with the exact raster digest;
- `redistribution_status=redistributable` or `reference_only`; and
- `processing_allowed=true` only after every other controlled field and the
  separately signed authority evidence agree.

- the artifact is the exact qualified single-band binary raster, not a vector
  ZIP, PDF, screenshot, model prediction, or unreviewed rasterization;
- valid class values are exactly `0` and `1`, with explicit distinct nodata;
- its CRS and coverage support every frozen analysis-cell centre without
  implicit reprojection;
- the observation interval includes the post-event Sentinel-1 acquisition;
- blind reviewer calibration and independent adjudication pass the fixed
  protocol, and the reference authority signs the qualification chain;
- the final raster bytes and SHA-256 are bound into the acquisition-authority
  receipt before any model lane is authorized.

For the controlled three-model experiment, these editable fields are necessary
but not sufficient. A trusted external decision must also bind the exact product
IDs, artifact hashes, permissions, attribution, signer identity and authority,
issue/expiry window, and signature. A completed request template, a public
download link, an internal self-attestation, or a checksum alone must never be
interpreted as that approval.

The repository's HMAC receipts provide tamper detection only inside a controlled
environment where role-specific secrets are independently held. They are not a
public, legally attributable, non-repudiable signature and do not prove that a
provider granted rights. For agency or cross-organization acceptance, retain the
original provider correspondence and use an externally verifiable asymmetric or
managed signing service with distinct acquisition, reviewer, adjudicator,
holdout, reference, policy, execution, model, result, and recommendation roles.

## Primary Sources Rechecked 2026-07-20

- Copernicus Data Space terms: https://dataspace.copernicus.eu/terms-and-conditions
- Copernicus Sentinel Data Legal Notice: https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice
- Sentinel Asia Northern Thailand event: https://sentinel-asia.org/EO/2024/article20240910TH.html
- Sentinel Asia DPN policy: https://sentinel-asia.org/e-learning/SentinelAsiaProcedures/PDPN.pdf
- UNOSAT Product 3991: https://unosat.org/products/3991
- GISTDA disaster open API: https://disaster.gistda.or.th/services/open-api
- GISTDA flood-extent dataset record: https://opendata.gistda.or.th/th/dataset/disasters-03

The current tracker does not clear any source for real-data ML.

Run the current gate check after any provider response update:

```powershell
uv run python scripts/check_real_data_gates.py --allow-blocked
uv run python scripts/validate_mae_sai_file_manifest.py --allow-blocked
```

The first command checks legal/reference-mask permission fields. The second command checks file-level product id, local path, SHA-256, source license, and reference-mask status. Both must pass without `--allow-blocked` before real Mae Sai non-ML validation can start.
