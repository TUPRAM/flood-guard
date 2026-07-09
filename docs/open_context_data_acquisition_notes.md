# Open Context Data Acquisition Notes

This lane records real context data that can improve FloodGuard decision quality while keeping source files outside Git.

Current status: file-level manifest rows are expected in `outputs/open_context_data_file_manifest.csv`. The manifest stores redacted local path hints and SHA-256 checksums only. Source rasters, OSM extracts, boundary packages, and DEM files must not be committed.

## External Workspace

Default outside-Git workspace:

```text
C:\Users\iputu\Documents\FloodGuard_external_data\open_context\
```

Committed manifests redact that root as:

```text
<external_data_workspace>/
```

## Selected Sources

| Source | Selected file | Role | Use boundary |
| --- | --- | --- | --- |
| WorldPop Thailand 100m | `tha_ppp_2020.tif` | Population exposure and reachable-demand denominator | Context only; not a flood label or reference mask. |
| HDX Thailand COD-AB | `tha_admin_boundaries.gdb.zip` | Administrative boundary aggregation geometry | Context only; boundary vintage must be verified before public claims. |
| OpenStreetMap Thailand via Geofabrik | `thailand-latest.osm.pbf` | Roads, bridges, facilities, and candidate routing graph | ODbL attribution/share-alike obligations apply; not official infrastructure truth. |
| Current local Copernicus DEM Thailand tile | `CopernicusDEM_Elevation_Slope_Thailand-0000046592-0000023296.tif` | Terrain, slope, and false-positive review context | Terrain context only; not flood observation, not flood label, not reference mask. |

## Command

Build or refresh the manifest from existing outside-Git files:

```powershell
uv run python scripts/build_open_context_file_manifest.py
```

Download the selected public context files outside Git and then write the manifest:

```powershell
uv run python scripts/build_open_context_file_manifest.py --download
```

The script downloads only remote WorldPop, HDX, and Geofabrik files. The DEM row uses an existing outside-Git TIFF by default:

```text
C:\Users\iputu\Documents\FloodGuard_external_data\open_context\copernicus_dem_glo30\CopernicusDEM_Elevation_Slope_Thailand-0000046592-0000023296.tif
```

Use a different DEM TIFF if needed:

```powershell
uv run python scripts/build_open_context_file_manifest.py --dem-path "C:\path\outside_git\dem_tile.tif"
```

## Manifest Meaning

`processing_allowed=True` means the file is ready for context processing only. It does not mean the layer is a flood label, validation mask, official warning, or operational source.

Rows should be treated as ready only when:

- `sha256_status=recorded`
- `acquisition_status=available_outside_git`
- `local_path` is redacted under `<external_data_workspace>/`
- `processing_scope` explicitly says the file is context only

## Next Integration Steps

1. Clip WorldPop to Mae Sai and aggregate population to the selected admin or review polygon.
2. Read HDX COD-AB boundaries and choose the administrative level used for reporting.
3. Extract OSM roads, bridge tags, and candidate facilities from the Geofabrik PBF.
4. Sample DEM/elevation/slope around weak-reference flood candidates for terrain and SAR false-positive review.
5. Feed derived context tables into FPPS, road risk, access loss, and equity modules.

These are follow-up processing steps. This acquisition lane only proves that context files are locally available and checksum-tracked outside Git.
