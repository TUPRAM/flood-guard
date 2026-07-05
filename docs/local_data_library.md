# Local Data Library

This library records the hackathon-provided files currently present on the local machine. It is metadata-only: source TIFFs, overview files, ZIP packages, and extracted ZIP members stay outside Git.

Generated outputs:

- `outputs/local_data_library_manifest.csv`
- `outputs/local_data_library_zip_members.csv`

Generator:

- `scripts/build_local_data_library.py`

## Current Inventory Summary

The current library contains 32 top-level local files:

- 2 Sentinel-1 SAR entries:
  - one standalone two-band VV/VH TIFF
  - one Google Drive ZIP containing five Sentinel-1 TIFF tiles
- 2 Copernicus DEM package entries:
  - two Google Drive ZIPs containing six DEM/elevation-slope TIFF tiles and one screenshot
- 28 THEOS-2 optical entries:
  - standalone optical TIFFs and overview files
  - THEOS-2 sample ZIP packages

The ZIP member catalog records 95 contained files:

- 5 Sentinel-1 TIFF members
- 6 Copernicus DEM/elevation-slope TIFF members
- 83 THEOS-2 package members
- 1 screenshot/documentation PNG

## Most Useful Near-Term Assets

### Standalone Sentinel-1 Thailand TIFF

`Sentinel1_Thailand-0000000000-0000000000-002.tif`

Cataloged metadata:

- CRS: `EPSG:4326`
- size: `23296 x 23296`
- bands: `2`
- band descriptions: `VV|VH`
- bbox: approximately `97.3436, 14.187003, 103.621746, 20.465149`
- MVP overlap: `mae_sai_2024_point`

This is the most important new candidate for the SAR lane because it covers the Mae Sai point and exposes VV/VH bands. It is not yet a locked real baseline input because the filename does not identify acquisition date, event timing, orbit, processing level, or whether it is a pre-event or post-event product.

Required before processing:

- SHA-256 checksum for the file
- source/license status recorded at file level
- acquisition timing or product provenance clarified
- reference-mask status cleared
- `processing_allowed=True` achieved through gates, not manual override

### Sentinel-1 Drive ZIP

`drive-download-20260705T102948Z-3-001.zip`

Contained members:

- `Sentinel1_Thailand-0000023296-0000000000.tif`
- `Sentinel1_Thailand-0000000000-0000023296.tif`
- `Sentinel1_Thailand-0000046592-0000000000.tif`
- `Sentinel1_Thailand-0000046592-0000023296.tif`
- `Sentinel1_Thailand-0000023296-0000023296.tif`

These look like tiled Sentinel-1 SAR assets. They should be treated as candidate SAR context or tile coverage until extracted, checksum-tracked, and linked to acquisition timing.

### Copernicus DEM Drive ZIPs

`drive-download-20260705T104354Z-3-001.zip` and `drive-download-20260705T104354Z-3-002.zip`

These contain DEM/elevation-slope TIFF tiles. They are useful for:

- elevation context
- slope context
- flood false-positive review
- exposure and access explanation

They are not flood observations, not reference masks, and not validation labels.

### THEOS-2 Optical Files

THEOS-2 remains the optical context lane:

- dashboard thumbnails
- visual review
- built-up/road/water context
- future optical feature experiments

THEOS-2 still must not be used as the legal flood reference mask or ML label source unless separate terms and labels are explicitly confirmed.

## Processing Gate

Every row in the local data library remains `processing_allowed=False` by default.

That is intentional. The library answers:

- what files exist locally
- what type they appear to be
- what basic header metadata is visible
- whether they overlap current MVP points
- what they might be useful for

It does not authorize processing. Before any real-data processing, a selected file must move into a file-level manifest with:

- product id or stable source id
- local path outside Git
- SHA-256 checksum
- source license status
- reference-mask status where relevant
- explicit `processing_allowed=True`
- reason why the row is no longer blocked

## Commands

Build the local library:

```powershell
uv run python scripts/build_local_data_library.py
```

Inspect top-level groups:

```powershell
Import-Csv outputs/local_data_library_manifest.csv | Group-Object library_group | Select-Object Name,Count
```

Inspect ZIP member groups:

```powershell
Import-Csv outputs/local_data_library_zip_members.csv | Group-Object library_group | Select-Object Name,Count
```

## Non-Goals

- Do not commit source TIFFs, overview files, ZIP packages, or extracted ZIP members.
- Do not treat the standalone Sentinel-1 TIFF as a pre/post flood pair until provenance and timing are clarified.
- Do not treat DEM or THEOS-2 imagery as flood labels.
- Do not train ML from this library manifest.
- Do not present any output as an official warning.
