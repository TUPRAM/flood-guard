# THEOS-2 Metadata-Only Inventory

This document explains how local THEOS-2 hackathon sample imagery can support FloodGuard without bypassing the project's data-readiness gates.

## Current Status

Status: metadata-only inventory created; usage permission reported by project owner.

The project owner reported on 2026-07-03 that the hackathon-provided THEOS-2 data and other provided local hackathon data can be used freely for the project. The repository still does not commit THEOS-2 imagery, overview files, or zip packages. The generated manifest records only file names, redacted path hints, file sizes, filename metadata, TIFF header metadata, zip package summaries, and processing-readiness status.

Usage log:

- `docs/theos2_usage_terms_log.md`

Generated manifest:

- `outputs/theos2_local_metadata_manifest.csv`
- `outputs/theos2_selected_file_manifest.csv`
- `outputs/theos2_previews/*.svg`
- `outputs/theos2_landcover_exposure_features.csv`
- `outputs/theos2_thumbnail_manifest.csv`
- `outputs/theos2_thumbnails/*.png`
- `outputs/theos2_visual_review_checklist.csv`

Generator:

- `scripts/build_theos2_local_manifest.py`
- `scripts/build_theos2_selected_manifest.py`
- `scripts/generate_theos2_previews.py`
- `scripts/generate_theos2_features.py`
- `scripts/generate_theos2_true_thumbnails.py`
- `scripts/generate_theos2_visual_review_checklist.py`

## What The Local Inventory Found

The local Downloads scan found:

- 13 standalone THEOS-2 image TIFF files
- 3 standalone overview files
- 12 THEOS-2 zip packages

The image TIFFs are high-resolution optical files:

- mostly `ORTHO_PMS`
- 4 bands
- 16-bit
- 0.5 m pixel size for orthorectified images
- mostly BigTIFF
- CRS hint: WGS84 / UTM Zone 47N where GeoTIFF tags are present

The zip packages include sample categories such as:

- `Disaster`
- `Urban`
- `Agri`
- `Coastal`
- `LULC`
- `Miscellaneous`
- `RAW Data (PAN+MS)`

## FloodGuard Uses

THEOS-2 can support FloodGuard as:

- optical context imagery for dashboard and action-brief interpretation
- visual verification support for roads, rivers, canals, built-up areas, agriculture, and coastlines
- land-cover and exposure feature-development samples
- future optical water or flood-proxy experiments when imagery is cloud-free and temporally relevant
- future optical/SAR comparison and false-positive analysis

THEOS-2 should not be treated as:

- the legal flood reference mask
- the first Mae Sai Sentinel-1 SAR baseline input
- official validation evidence
- committed source data; keep original imagery outside Git even when hackathon use is allowed
- an official warning product

## Current Study-Area Fit

The parsed local image bboxes do not currently overlap the Mae Sai 2024 or Hat Yai 2025 MVP points used elsewhere in the project.

That means the current local THEOS-2 sample set is useful for optical-context and method-development lanes, but not as the first real validation input for Mae Sai or Hat Yai.

## Usage-Terms Status

Current logged status:

- `license_status = user_reported_hackathon_free_use`
- `sha256_status = not_recorded`
- `processing_allowed = False`

This is enough to plan THEOS-2 derived demo work, but selected files still need SHA-256 checksums before pixel-processing outputs are treated as reproducible artifacts. If written organizer terms later narrow the permission, update this document and the manifest before publishing screenshots or derived outputs.

## Manifest Fields

`outputs/theos2_local_metadata_manifest.csv` includes:

- `file_name`
- `local_path_hint`
- `entry_kind`
- `zip_member_count`
- `zip_categories`
- `category`
- `file_size_bytes`
- `file_size_gb`
- `acquisition_date`
- `acquisition_time_utc`
- `processing_level`
- `sensor_product`
- `tile_id`
- `sequence_id`
- `tiff_version`
- `image_width`
- `image_height`
- `samples_per_pixel`
- `bits_per_sample`
- `compression`
- `pixel_size_m`
- `crs_hint`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `mvp_overlap`
- `floodguard_relevance`
- `license_status`
- `sha256_status`
- `processing_allowed`
- `reason_blocked`

`local_path_hint` intentionally uses `<input_dir>/...` instead of committing absolute local paths.

## Processing Gate

Every current row remains blocked for reproducible pixel-processing outputs until checksums are recorded:

- `sha256_status = not_recorded`
- `processing_allowed = False`

Processing may be enabled only after:

- SHA-256 checksums are recorded for files selected for processing
- imagery remains outside Git
- any generated derivative outputs are clearly labeled non-operational
- public screenshots or derived outputs stay within the user-reported hackathon permission
- any later written organizer terms are checked for local analysis, derived metrics, demo screenshots, and redistribution or reference-only use

THEOS-2 is now the best immediate data lane while UNOSAT/UNITAR and GISTDA reference-mask replies are pending. It can support optical context, land-cover/exposure interpretation, and future optical-water experiments, but it does not unblock real flood-mask validation or real-data ML labels by itself.

## Selected-File Readiness

`outputs/theos2_selected_file_manifest.csv` records SHA-256 checksums for the curated selected disaster/context candidates:

- `IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif`
- `IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif`
- `IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif`

These rows use:

- `sha256_status = recorded`
- `processing_scope = theos2_optical_context_preview_only`
- `reference_mask_status = not_reference_mask`
- `processing_allowed = True`

This permission is intentionally narrow. It allows checksum-backed optical-context preview work. It does not turn THEOS-2 into a flood reference mask, does not authorize real flood-label ML, and does not allow source imagery to be committed to Git.

## Preview Use In Dashboard And Briefs

`outputs/theos2_previews/*.svg` are small non-operational preview cards generated from selected-file metadata and checksums. They do not contain source image pixels. The static dashboard can reference these cards as THEOS-2 optical context while keeping flood validation and action-class scoring separate.

Action briefs may cite THEOS-2 only as optical context or local interpretation support. They should not say THEOS-2 proves flood extent unless a separate legally usable flood reference mask or validated flood product is available.

## Optional True Thumbnail Lane

`scripts/generate_theos2_true_thumbnails.py` can generate small PNG thumbnails only when an optional raster reader is available:

- rasterio
- GDAL

If neither reader is available, the command fails cleanly and does not create thumbnail outputs. The fallback SVG preview cards remain valid dashboard context.

True thumbnails are guarded by:

- `sha256_status = recorded`
- `processing_scope = theos2_optical_context_preview_only`
- `reference_mask_status = not_reference_mask`
- `processing_allowed = True`

They must remain small PNG previews. Do not generate full-resolution exports or source-image tiles in this lane.

Current true-thumbnail output was generated with `rasterio` after verifying selected-file SHA-256 checksums. The source TIFFs remain outside Git.

## Visual Review Checklist

`outputs/theos2_visual_review_checklist.csv` initializes one pending manual-review row per selected THEOS-2 preview. It tracks:

- visible water context
- built-up area context
- road context
- cloud/haze status
- usefulness for exposure explanation

The checklist is deliberately initialized as `not_reviewed`. It is not a flood-label file, not a validation mask, and not an official warning input.

## Non-ML Feature Prototype

`outputs/theos2_landcover_exposure_features.csv` records tiny metadata-derived context features:

- disaster/LULC/urban/agri/coastal flags
- rough footprint area
- built-up exposure interpretation note
- water/coastal context note
- FloodGuard use note

These fields can support FPPS explanation text and action-brief context, but they are not flood labels and are not a validation mask.

## Next Work

1. Fill `outputs/theos2_visual_review_checklist.csv` manually for selected previews.
2. Use THEOS-2 optical context in generated action briefs without calling it flood validation.
3. Expand land-cover/exposure feature experiments from selected THEOS-2 samples.
4. Keep optical context layers in the dashboard clearly separate from flood-reference validation.
5. Later, add optional optical feature extraction for land-cover/exposure support, separate from the Sentinel-1 SAR flood-validation lane.
