# Mae Sai Sentinel-1 Pair Decision Note

This note locks the source identities for the Mae Sai weak-reference SAR
baseline. It is a source-selection decision, not an official-validation or
operational clearance.

## Decision Status

Status: same-track original SAFE pair selected; every processing run remains
fail-closed until its current local archives and reference mask pass the
manifest, checksum, licensing, and weak-reference gates.

The legacy September 6 / September 15 COG selection is retired because:

- the acquisitions are from different tracks, so their backscatter change is
  not a controlled like-for-like comparison;
- SNAP reports unreliable calibration metadata for the CDSE COG conversion;
- the locally held COG ZIP bytes no longer match their recorded hashes after
  GDAL PAM metadata mutation; and
- an archive whose bytes changed cannot be reused under an earlier receipt.

The COG product identities remain in the study-area inventory for provenance.
They must never occupy an active pre-event or post-event baseline role.

## Approved Active Pair

| Role | Acquisition date | Product name | CDSE product id | Selection basis |
| --- | --- | --- | --- | --- |
| Pre-event original SAFE | 2024-09-03 23:16:00Z | `S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE` | `aaaef3af-fa49-4115-bf0f-f54175e7aedf` | Original Sentinel-1A IW GRD VV/VH product selected as the same-track pre-event acquisition. |
| Post-event original SAFE | 2024-09-15 23:16:01Z | `S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_08DA.SAFE` | `5251b74b-0bbd-4365-9eb4-fa33292e175a` | Original Sentinel-1A IW GRD VV/VH product selected as the matching post-event acquisition. |

The post-event source timestamp is deterministically bound to
`2024-09-15T23:16:01Z`. The weak-reference baseline refuses to invent a
timestamp for any substituted product identity.

## Retired Exploratory Records

| Former role | Product id | Current status |
| --- | --- | --- |
| September 6 pre-event COG | `b09f96ca-4a60-43e7-9b8d-158022f0e5bf` | Retired from baseline selection; cross-track and locally checksum-invalid after PAM mutation. |
| September 15 post-event COG | `20a9c3b8-37df-46d5-81d8-d63c7e460225` | Retired from baseline selection; COG calibration warning and locally checksum-invalid after PAM mutation. |
| September 18 post-event COG fallback | `6a02d487-68fa-4be7-9628-f312b9049967` | Inventory-only alternative; not an active fallback. |

## Required Run Gates

Before any candidate metrics are regenerated:

- register the two exact original SAFE ZIPs outside Git;
- bind each local archive to its CDSE UUID and current SHA-256;
- verify complete dual-polarization SAFE structure;
- verify the manual weak-reference mask and its current checksum;
- keep candidate and fixture results `official_warning=false`; and
- retain the wording: candidate weak-reference analysis, non-operational, not
  official validation, not field validated, and not an emergency warning.

The source-selection gate rejects the retired COG UUIDs even if a caller gives
them plausible paths and checksums.
