# Licensing Outreach Status

This tracker converts the request templates into send-ready outreach tasks. No email or web-form request has been sent by this repository automation. Sending requires the project owner's name, institution, email address, and authority to contact the source.

## Send-Ready Requests

| Source | Template section | Request status | Request sent date | Response date | Current blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| UNOSAT/UNITAR Mae Sai reference target | `docs/licensing_request_templates.md` - UNOSAT/UNITAR Request | ready_to_send_not_sent | not_sent | no_response | sender identity and contact channel required | send first; this is the preferred Mae Sai reference-mask target |
| GISTDA official flood product candidate | `docs/licensing_request_templates.md` - GISTDA Request | ready_to_send_not_sent | not_sent | no_response | sender identity and event-specific contact channel required | send after confirming preferred GISTDA contact route |
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

Then update any file-level ingestion manifest rows. Do not set `processing_allowed=True` until the legal response, local file path, SHA-256 checksum, and reference-mask status are all confirmed.

## Current Decision

The first outreach priority is UNOSAT/UNITAR for the Mae Sai 2024 reference mask. GISTDA is second because it may provide official national context, but the exact product/contact route is not locked. Charter and Sentinel Asia are important for Hat Yai / Songkhla 2025, not the first Mae Sai validation tile.

