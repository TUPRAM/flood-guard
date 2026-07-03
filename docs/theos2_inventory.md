# THEOS-2 Metadata-Only Inventory

This document explains how local THEOS-2 hackathon sample imagery can support FloodGuard without bypassing the project's data-readiness gates.

## Current Status

Status: metadata-only inventory created.

The repository does not commit THEOS-2 imagery, overview files, or zip packages. The generated manifest records only file names, redacted path hints, file sizes, filename metadata, TIFF header metadata, zip package summaries, and blocking status.

Generated manifest:

- `outputs/theos2_local_metadata_manifest.csv`

Generator:

- `scripts/build_theos2_local_manifest.py`

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
- redistributable source data unless hackathon terms explicitly allow redistribution
- an official warning product

## Current Study-Area Fit

The parsed local image bboxes do not currently overlap the Mae Sai 2024 or Hat Yai 2025 MVP points used elsewhere in the project.

That means the current local THEOS-2 sample set is useful for optical-context and method-development lanes, but not as the first real validation input for Mae Sai or Hat Yai.

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

Every current row remains blocked:

- `license_status = hackathon_terms_unverified`
- `sha256_status = not_recorded`
- `processing_allowed = False`

Processing may be enabled only after:

- hackathon license terms are recorded
- allowed use is clear for local analysis, derived metrics, demo screenshots, and redistribution or reference-only use
- SHA-256 checksums are recorded for files selected for processing
- imagery remains outside Git
- any generated derivative outputs are clearly labeled non-operational

## Next Work

1. Record the hackathon THEOS-2 license or usage terms.
2. Decide whether these samples are permitted for public demo screenshots and derived metrics.
3. Compute SHA-256 checksums only for selected files, not the full sample folder by default.
4. Add a preview-generation workflow that creates small, non-sensitive thumbnails or map tiles only if license terms allow.
5. Later, add optional optical feature extraction for land-cover/exposure support, separate from the Sentinel-1 SAR flood-validation lane.

