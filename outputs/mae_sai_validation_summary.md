# Mae Sai Real-Data Validation Summary

Status: blocked until reference-mask and file-level ingestion gates pass.

This report is non-operational and must not be used as an official warning.

## Ingestion Gate

- Processing allowed: false
- Blocking reason: Sentinel Asia MBRSC Mae Sai public shapefile candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai pre-event COG: processing_allowed is not true, reference_mask_status is not confirmed; CDSE Sentinel-1 Mae Sai post-event COG primary: processing_allowed is not true, reference_mask_status is not confirmed
- Real IoU, F1/Dice, precision, recall, and area error are pending.

## Required Next Action

- Log UNOSAT/UNITAR or GISTDA provider response.
- Record legal reference-mask status.
- Record local paths and SHA-256 checksums outside Git.
- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.

## Weak-Reference Candidate Baseline

- Status: candidate metrics generated against a manually digitized weak-reference mask.
- These are not official validation metrics and must not be used as emergency-warning evidence.
- IoU: 0.006079
- F1/Dice: 0.012085
- precision: 0.038494
- recall: 0.007167
- area error ratio: -0.813809
- Sample pixels: 65536
- Manual weak-reference positive pixels: 12557
- Pre-event Sentinel-1 product id: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product id: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Manual reference id: `MANUAL-QGIS-MAE-SAI-2024`
- Georeferencing method: sentinel1_safe_gcps_affine_fit
- Manual mask not-official status: confirmed_true
- Manual mask readiness: ready_for_candidate_metrics

### Weak-Reference Failure Modes

- SAR layover/shadow.
- Permanent water confusion.
- Urban double-bounce.
- Manual mask uncertainty.
- Date mismatch between manual interpretation and Sentinel-1 acquisition.

### Weak-Reference Safety Note

- Not official.
- Not real-time.
- Not field validated.
- Not an emergency warning.
