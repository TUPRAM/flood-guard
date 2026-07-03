# Mae Sai Real-Data Validation Summary

Status: blocked until reference-mask and file-level ingestion gates pass.

This report is non-operational and must not be used as an official warning.

## Ingestion Gate

- Processing allowed: false
- Blocking reason: UNOSAT/UNITAR Mae Sai reference mask file candidate: processing_allowed is not true, license_status is not confirmed, source_license_status is not confirmed, reference_mask_status is not confirmed, local_path is not recorded, sha256 is not recorded; CDSE Sentinel-1 Mae Sai pre-event COG: processing_allowed is not true, reference_mask_status is not confirmed, local_path is not recorded, sha256 is not recorded; CDSE Sentinel-1 Mae Sai post-event COG primary: processing_allowed is not true, reference_mask_status is not confirmed, local_path is not recorded, sha256 is not recorded
- Real IoU, F1/Dice, precision, recall, and area error are pending.

## Required Next Action

- Log UNOSAT/UNITAR or GISTDA provider response.
- Record legal reference-mask status.
- Record local paths and SHA-256 checksums outside Git.
- Rebuild `outputs/mae_sai_real_data_file_manifest.csv`.
