# Reference-Mask Licensing Log

This log tracks candidate flood reference-mask sources before real data ingestion. It is planning documentation only. Do not download, redistribute, or process reference-mask geometry until access, license, attribution, and redistribution status are confirmed.

| Source | Study area | Candidate use | URL | Geometry access status | License / access status | Redistribution status | Attribution / citation status | Current blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | Chiang Rai / Mae Sai 2024 | Reference flood mask target | https://unosat.org/products/3991 | Product page identified; GIS geometry not acquired in this repo | request sent by project owner on 2026-07-03; provider response pending | unresolved | UNOSAT/UNITAR citation required if used; exact citation text not locked | geometry file and redistribution terms not confirmed | log provider response and confirm product file access, license, local validation, derived metrics, screenshots, redistribution, and ML-label use |
| GISTDA official flood product candidate | Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025 | Official flood reference candidate | https://www.gistda.or.th/ | event-specific product not acquired | request sent by project owner on 2026-07-03; provider response pending | unresolved | GISTDA attribution likely required; exact terms not locked | exact event product and usage terms not confirmed | log provider response and confirm event product access, license, local validation, derived metrics, screenshots, redistribution, and ML-label use |
| International Charter Activation 1004 | Hat Yai / Songkhla 2025 | Crisis mapping reference candidate | https://disasterscharter.org/activations/flood-in-thailand-activation-1004- | product geometry access not confirmed | access and attribution terms apply; details not locked | unresolved | Charter attribution required if products are used; exact citation not locked | product geometry and redistribution status not confirmed | confirm available products, access route, license, and citation terms |
| Sentinel Asia Southern Thailand 2025 | Hat Yai / Songkhla 2025 | Event detected-water or flood-proxy context | https://sentinel-asia.org/EO/2025/article20251119TH.html | product geometry access not confirmed | access and attribution terms apply; details not locked | unresolved | Sentinel Asia attribution required if products are used; exact citation not locked | product file access and redistribution status not confirmed | confirm product files, terms of use, and citation requirements |
| Academic or manual reference mask | Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025 | Fallback validation or manual reference candidate | to be identified | not identified | unresolved | unresolved | source-specific citation required once identified | no candidate mask selected | search only after official/event source status is logged |

## Current Rule

All rows remain blocked for processing. The first real-data ingestion skeleton may create metadata manifests from these rows, but it must not download source data or run flood-detection/model code.

## Licensing Tracker V2

This execution tracker is the operational gate for reference-mask use. A source is not usable for real-data validation until `blocking_decision` is `cleared_for_local_validation` or a similarly explicit approved status. A source is not usable for ML labels until `ml_label_use_allowed` is explicitly `yes`. Blank dates mean no request or response has been recorded in this repository. Column names in downstream trackers should preserve `request_status`, `request_sent_date`, `response_date`, `geometry_access`, `local_analysis_allowed`, `derived_metrics_allowed`, `screenshots_demo_allowed`, `redistribution_allowed`, `citation_required`, `ml_label_use_allowed`, and `blocking_decision`.

| Source | Request status | Request sent date | Response date | Geometry access | Local analysis allowed | Derived metrics allowed | Screenshots/demo allowed | Redistribution allowed | Citation required | ML-label use allowed | Blocking decision | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | sent_waiting_response | 2026-07-03 | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_provider_response_pending | log reply and confirm GIS geometry access before any reference-mask processing |
| GISTDA official flood product candidate | sent_waiting_response | 2026-07-03 | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_provider_response_pending | log reply and confirm event-specific product access and terms |
| International Charter Activation 1004 | draft_not_sent | not_sent | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_activation_product_terms_unconfirmed | request product access and reuse terms |
| Sentinel Asia Southern Thailand 2025 | draft_not_sent | not_sent | no_response | unresolved | unresolved | unresolved | unresolved | unresolved | yes_expected | unresolved | blocked_product_file_terms_unconfirmed | request detected-water/flood-proxy product terms |
| Academic or manual reference mask | not_started | not_sent | no_response | not_identified | unresolved | unresolved | unresolved | unresolved | source_specific | unresolved | blocked_no_candidate_selected | search only after official/event source status is logged |

## Processing Gate

The real-data ingestion manifest may set `processing_allowed=True` only when all of the following are true:

- source license status is `confirmed`
- reference mask status is `confirmed`
- geometry access status is `confirmed` or `available`
- redistribution status is `redistributable` or `reference_only`
- product id is recorded
- local path is recorded outside the repository
- SHA-256 checksum is recorded

The current tracker does not clear any source for real-data ML.

Run the current gate check after any provider response update:

```powershell
uv run python scripts/check_real_data_gates.py --allow-blocked
uv run python scripts/validate_mae_sai_file_manifest.py --allow-blocked
```

The first command checks legal/reference-mask permission fields. The second command checks file-level product id, local path, SHA-256, source license, and reference-mask status. Both must pass without `--allow-blocked` before real Mae Sai non-ML validation can start.
