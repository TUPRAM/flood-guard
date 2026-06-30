# Mae Sai Sentinel-1 Pair Decision Note

This note locks the current planning pair for the first Mae Sai non-ML SAR baseline. It is not a download authorization and not a processing clearance.

## Decision Status

Status: planning pair selected; final processing remains blocked.

Reason processing remains blocked:

- UNOSAT/UNITAR reference-mask geometry is not acquired.
- Reference-mask license and redistribution terms are unresolved.
- Local Sentinel-1 product paths are not recorded.
- SHA-256 checksums are not recorded.
- `processing_allowed=True` is not allowed in the ingestion manifest yet.

## Selected Planning Pair

| Role | Acquisition date | Product name | CDSE product id | Reason |
| --- | --- | --- | --- | --- |
| Pre-event COG | 2024-09-06 11:31:06Z | `S1A_IW_GRDH_1SDV_20240906T113106_20240906T113131_055544_06C73C_B53D_COG.SAFE` | `b09f96ca-4a60-43e7-9b8d-158022f0e5bf` | Later clean pre-event candidate before the likely flood window; COG form preferred for first processing. |
| Post-event COG primary | 2024-09-15 23:16:01Z | `S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_82A9_COG.SAFE` | `20a9c3b8-37df-46d5-81d8-d63c7e460225` | First post-event COG candidate currently selected for the baseline. |
| Post-event COG fallback | 2024-09-18 11:31:07Z | `S1A_IW_GRDH_1SDV_20240918T113107_20240918T113132_055719_06CE27_00F2_COG.SAFE` | `6a02d487-68fa-4be7-9628-f312b9049967` | Use only if the confirmed reference-mask date or flood peak is closer to the later acquisition. |

## Decision Rule

Use the September 15 post-event COG as the first baseline target unless the legally usable reference mask indicates that September 18 better matches the mapped flood extent. Prefer COG products for the first reproducible workflow, keep SAFE alternatives documented, and do not download any product until the legal/reference-mask gate is cleared.

## Required Update After Reference-Mask Response

When the reference mask is legally available, update this note with:

- reference-mask source and product id
- reference-mask timestamp or mapped event date
- whether September 15 or September 18 is the final post-event acquisition
- reason for the final choice
- local paths and SHA-256 checksums, stored outside Git
- final `processing_allowed` status in the file-level ingestion manifest

