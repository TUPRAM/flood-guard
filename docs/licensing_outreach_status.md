# Licensing Outreach Status

This tracker converts the request templates into outreach tasks. Repository automation does not send email or web-form requests. The project owner reported sending the UNOSAT/UNITAR and GISTDA requests on 2026-07-03; provider responses are still pending.

## Send-Ready Requests

| Source | Template section | Request status | Request sent date | Response date | Current blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | `docs/licensing_request_templates.md` - UNOSAT/UNITAR Request | sent_waiting_response | 2026-07-03 | no_response | provider response pending; geometry and reuse terms unresolved | log reply and confirm GIS geometry access, local validation, derived metrics, screenshots, redistribution, and ML-label use |
| GISTDA official flood product candidate | `docs/licensing_request_templates.md` - GISTDA Request | sent_waiting_response | 2026-07-03 | no_response | provider response pending; event-specific product and reuse terms unresolved | log reply and confirm event products, local validation, derived metrics, screenshots, redistribution, and ML-label use |
| International Charter Activation 1004 | `docs/licensing_request_templates.md` - International Charter Request | ready_to_send_not_sent | not_sent | no_response | sender identity and access contact route required | send for Hat Yai / Songkhla 2025 story tile |
| Sentinel Asia Southern Thailand 2025 | `docs/licensing_request_templates.md` - Sentinel Asia Request | ready_to_send_not_sent | not_sent | no_response | sender identity and product contact route required | send for Hat Yai / Songkhla 2025 event product terms |

## Required Sender Details

Before sending, replace placeholders in the templates with:

- project owner name
- institution or affiliation
- email address
- intended hackathon/demo context
- whether the request is for private validation only or public demo publication
- citation format requested by the provider, if known

UNOSAT/UNITAR and GISTDA have been marked as sent from the project owner side, but this file does not store the sender identity. Keep email copies outside the repository unless they contain no private contact information.

## Response Logging Rule

When a provider replies, update `docs/reference_mask_licensing_log.md` first. Record:

- `request_status`
- `request_sent_date`
- `response_date`
- `geometry_access`
- `local_analysis_allowed`
- `derived_metrics_allowed`
- `redistribution_allowed`
- `citation_required`
- `blocking_decision`

Then update any file-level ingestion manifest rows. Do not set `processing_allowed=True` for flood-reference processing until the legal response, local file path, SHA-256 checksum, and reference-mask status are all confirmed.

## Current Decision

UNOSAT/UNITAR and GISTDA are now waiting on provider responses. Charter and Sentinel Asia remain send-ready for the Hat Yai / Songkhla 2025 story tile. While those responses are pending, THEOS-2 hackathon samples can move into an optical-context lane based on user-reported free-use permission, with imagery still kept outside Git and selected files checksum-tracked before processing.
