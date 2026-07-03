# Mae Sai Real-Data File Manifest V2

This note defines the next file-level manifest step after a legally usable Mae Sai reference mask is acquired. It is not authorization to download or process data.

## Current Status

Status: blocked.

Reasons:

- UNOSAT/UNITAR and GISTDA provider responses are still pending.
- No Mae Sai flood reference-mask file is locally acquired.
- No local Sentinel-1 source paths are recorded.
- No SHA-256 checksums are recorded for the reference mask or Sentinel-1 files.
- `processing_allowed=True` is not allowed yet for the Mae Sai real-data baseline.

In plain terms: processing_allowed=True is not allowed yet.

## Required Rows

`outputs/mae_sai_real_data_file_manifest.csv` must include one ready row for each role:

- `reference flood mask for validation`
- `pre-event SAR source for non-ML baseline`
- `post-event SAR source for non-ML baseline`

Each row must include:

- `product_id`
- `local_path`
- `sha256`
- `source_license_status=confirmed`
- `reference_mask_status=confirmed`
- `geometry_access_status=confirmed` or `available`
- `license_status=confirmed`
- `redistribution_status=redistributable` or `reference_only`
- `processing_allowed=True`

## Source File Rule

The actual reference mask and Sentinel-1 files must remain outside Git. Do not commit `.SAFE`, `.tif`, `.tiff`, `.jp2`, `.zip`, NetCDF, GRIB, or provider product packages.

## Next Command Sequence After Legal Acquisition

1. Place source files in a private local data directory outside the repository.
2. Compute SHA-256 checksums.
3. Update a local manifest source table with product ids, paths, checksums, and license/reference status.
4. Run `scripts/build_mae_sai_file_manifest.py` or a future v2 source-table wrapper.
5. Run `scripts/generate_mae_sai_validation_summary.py`.
6. Run the real non-ML SAR baseline only if the manifest validator reports all required rows ready.

## ML Gate

The first ML experiment remains blocked until the real non-ML SAR baseline produces IoU, F1/Dice, precision, recall, and area error against the cleared reference mask.
