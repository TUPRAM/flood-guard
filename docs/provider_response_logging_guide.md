# Provider Response Logging Guide

UNOSAT/UNITAR and GISTDA requests were reported sent by the project owner on 2026-07-03. Until a provider response is received and logged, real flood validation, real Sentinel-1 processing, and real-data ML remain blocked.

## When UNOSAT/UNITAR Replies

Update `docs/reference_mask_licensing_log.md` first:

- `request_status`: `response_received`
- `response_date`: exact response date
- `geometry_access`: `available`, `web_only`, `pdf_only`, or `unavailable`
- `local_analysis_allowed`: `yes`, `no`, or `unclear`
- `derived_metrics_allowed`: `yes`, `no`, or `unclear`
- `redistribution_allowed`: `redistributable`, `reference_only`, `no`, or `unclear`
- `citation_required`: exact citation/disclaimer if provided
- `blocking_decision`: `cleared_for_local_validation`, `reference_only_public_metrics_allowed`, or a blocked status

Then update `docs/licensing_outreach_status.md`:

- `Request status`: `response_received`
- `Response date`: exact response date
- `Current blocker`: remaining blocker or `none_for_local_validation`
- `Next action`: acquire file outside Git, record checksum, and rebuild manifest

## When GISTDA Replies

Record the same fields, plus:

- exact product names
- event dates and acquisition dates
- source satellite or analysis method if provided
- access route, account requirement, or fee
- screenshot/public demo permission
- ML-label permission if explicitly addressed

## Do Not Infer Missing Rights

If a response says only "you may use this data" but does not address local analysis, derived metrics, screenshots, redistribution/reference-only status, or ML labels, keep the blocking decision as `blocked_terms_incomplete`.

## File Handling Rule

Provider files, Sentinel-1 products, reference masks, and THEOS-2 source imagery stay outside Git. The repository stores only:

- product id
- local path
- SHA-256 checksum
- license/reference-mask status
- processing gate status
