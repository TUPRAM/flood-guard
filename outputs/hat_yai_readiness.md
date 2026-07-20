# Hat Yai / Songkhla 2025 Readiness Status

> **BLOCKED — candidate metadata only. Non-operational. Not an official warning.**

## Technical summary

FloodGuard has a pinned catalogue snapshot with 14 Sentinel-1 candidates and a locked metadata-only original SAFE pair. The selected files have not been acquired or checksum-bound, their grid compatibility is unverified, and no qualified/manual reference mask exists. Candidate metrics, decision outputs, and the dashboard story therefore remain unavailable.

- Dataset mode: `candidate`
- Operational status: `non_operational`
- Source timestamp: `2025-12-05T23:03:07.854162Z`
- Confidence: `low`
- Receipt SHA-256: `78450083249f573fb96737a5f9bf2e97b2ed9b563dfa4df8d401c7d8f3feba7c`

## Gate status

| Gate | Status |
| --- | --- |
| Pre/post metadata pair selection | LOCKED_METADATA_ONLY |
| Selected pair acquired outside Git | BLOCKED |
| Selected pair checksums and grid | BLOCKED |
| Checksum-bound external assets | BLOCKED |
| Qualified event reference mask | BLOCKED |
| Manual weak-reference mask | BLOCKED |
| Processing allowed | NO |
| Candidate metrics available | NO |
| Decision outputs available | NO |
| Dashboard story available | NO |
| Can feed decision layer | NO |

## Sentinel-1 catalogue candidates

These are catalogue records. The named pre/post pair is selected at metadata level only; none of these rows proves a downloaded or grid-verified model input.

| Acquisition (UTC) | Platform | Storage | Candidate role | CDSE product ID |
| --- | --- | --- | --- | --- |
| 2025-11-05T11:35:22.737251Z | S1A | COG | pre-event COG candidate | `a43b3f36-6846-4554-af5d-1f757d862851` |
| 2025-11-05T11:35:22.737251Z | S1A | SAFE | pre-event SAFE alternative | `967702e5-a008-4774-9400-e28dd1e624c8` |
| 2025-11-11T23:03:09.801147Z | S1A | SAFE | pre-event SAFE alternative | `4e473302-943c-4798-8bfc-8287167792ed` |
| 2025-11-11T23:03:09.801147Z | S1A | COG | pre-event COG candidate | `00f3fc06-bcc8-4348-8b86-a4e0fbacdc13` |
| 2025-11-23T23:03:09.290537Z | S1A | SAFE | post-event SAFE alternative | `d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc` |
| 2025-11-23T23:03:09.290537Z | S1A | COG | post-event COG candidate | `325e23d5-9ba6-439e-bac9-8d7efac83cac` |
| 2025-11-29T11:35:21.012344Z | S1A | SAFE | fallback post-event SAFE alternative | `61f1bb34-e9bd-47b5-85a3-0472b50bf620` |
| 2025-11-29T11:35:21.012344Z | S1A | COG | fallback post-event COG candidate | `77afe9fe-ad3f-4fe1-872f-01bf801c742b` |
| 2025-11-29T23:01:52.466000Z | S1C | SAFE | fallback post-event SAFE alternative | `99b5426b-8464-4691-9648-72cf37dd84c2` |
| 2025-11-29T23:01:52.466000Z | S1C | COG | fallback post-event COG candidate | `96eb3dd0-0049-411b-919a-5091c94e4406` |
| 2025-12-05T11:34:26.774000Z | S1C | SAFE | fallback post-event SAFE alternative | `95537190-81cf-4b8e-aee8-eae8a1b4d3dc` |
| 2025-12-05T11:34:26.774000Z | S1C | COG | fallback post-event COG candidate | `443e046e-4f2b-4db6-bf3b-136f25c6f901` |
| 2025-12-05T23:03:07.854162Z | S1A | COG | fallback post-event COG candidate | `386ccf2d-2253-40bc-99bd-fa19bbc3c6dd` |
| 2025-12-05T23:03:07.854162Z | S1A | SAFE | fallback post-event SAFE alternative | `e641d58b-bc6d-4463-a49d-2ecebf2b64c2` |

### Locked metadata-only pair

- Pre-event original SAFE: `4e473302-943c-4798-8bfc-8287167792ed` at `2025-11-11T23:03:09.801147Z`
- Post-event original SAFE: `d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc` at `2025-11-23T23:03:09.290537Z`
- Selection basis: same S1A platform and IW_GRDH_1SDV mode; 12-day repeat; absolute-orbit difference 175; original SAFE products selected instead of COG derivatives
- Asset state: `not_acquired`; checksum state: `not_recorded`; grid status: `not_verified_without_assets`

## Reference candidates

| Source | Current state | Next action |
| --- | --- | --- |
| Academic or manual reference mask | geometry=not_identified; license=unresolved; reference=unresolved | search only after official/event sources are logged |
| International Charter Activation 1004 | geometry=unresolved; license=unresolved; reference=unresolved | confirm product geometry access and attribution terms |
| Sentinel Asia Southern Thailand 2025 | geometry=unresolved; license=unresolved; reference=unresolved | confirm product file access and redistribution terms |

## Exact blockers

- `selected_pair_assets_not_acquired` — The locked metadata pair has not been downloaded to the controlled external workspace.
- `selected_pair_checksums_missing` — No file-level SHA-256 checksums bind the selected Hat Yai Sentinel-1 products.
- `selected_pair_grid_not_verified` — Footprint coverage, CRS, raster grid, polarization bands, and pixel alignment cannot be verified without the selected source assets.
- `reference_permissions_unresolved` — Reference geometry access, validation use, derived reporting, ML-label use, and redistribution permissions are not cleared.
- `qualified_reference_mask_missing` — No qualified Hat Yai event-flood reference mask exists in the committed evidence.
- `manual_weak_reference_mask_missing` — No checksum-bound Hat Yai manual weak-reference mask exists.

## Required next actions

1. Acquire the locked original SAFE pair outside Git (4e473302-943c-4798-8bfc-8287167792ed pre-event; d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc post-event).
2. Bind source terms, file sizes, SHA-256 checksums, footprint coverage, polarization bands, CRS, and grid alignment in a Hat Yai file manifest.
3. Obtain a qualified event reference with explicit validation, derived-reporting, ML-label, and redistribution decisions, or create a separately labeled manual weak-reference mask under the project protocol.
4. Run the deterministic baseline and spatial validation only after the applicable processing and reference gates pass.
5. Generate candidate decision inputs and enable the Hat Yai dashboard story only after traceable metrics and non-operational decision artifacts exist.

## Safety and claim boundary

- No Hat Yai flood accuracy metric has been calculated.
- No road, access, equity, FPPS, or A–E output has been generated for Hat Yai.
- Metadata-level pair selection does not prove acquisition, footprint coverage, scene alignment, flood timing, or fitness for use.
- A future manual mask may support weak-reference candidate metrics only; it cannot establish official accuracy.
- The Hat Yai tile remains a future story/stress-test location until every upstream receipt is traceable and accepted.

## Reproducibility

- `outputs/cdse_hat_yai_2025_metadata.csv` — SHA-256 `099cb6fa3f38261e546c09e3fc5c97dbca93055f820844e2ac9f3d5a0c22720b`
- `outputs/real_data_ingestion_manifest.csv` — SHA-256 `c23103f626ed14fe740a66fffa52cfcf0fcd06c9971254293f49b9e7bb941871`
