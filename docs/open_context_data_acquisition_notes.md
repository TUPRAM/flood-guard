# Open Context Data Acquisition Notes

This lane records real context data that can improve FloodGuard decision quality while keeping source files outside Git.

Current status: file-level manifest rows are expected in `outputs/open_context_data_file_manifest.csv`. The manifest stores redacted local path hints and SHA-256 checksums only. Source rasters, OSM extracts, boundary packages, and DEM files must not be committed.

## External Workspace

Default outside-Git workspace:

```text
<external-data-workspace>/open_context/
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
| Copernicus DEM GLO-30 Mae Sai tile | `Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif` | Terrain, slope, and false-positive review context | Public GLO-30 context tile; not flood observation, not flood label, not reference mask. |

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
<external-data-workspace>/open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif
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

## Implemented Mae Sai Integration

Run:

```powershell
uv run python scripts/build_mae_sai_real_context.py
uv run python scripts/generate_mae_sai_action_brief.py
```

The integration now:

1. verifies all four outside-Git source checksums;
2. extracts eight Mae Sai COD-AB ADM3 polygons and bounded OSM roads/facilities outside Git through QGIS/GDAL;
3. summarizes real Sentinel-1 candidate change by ADM3 without treating admin polygons as flood labels;
4. aggregates WorldPop 2020 population and Copernicus DEM terrain context;
5. computes heuristic road risk, modeled access loss, proxy equity gap, and FPPS inputs;
6. writes only compact derived CSV, GeoJSON, Markdown, and manifest outputs into the repo.

The original local DEM package was rejected for Mae Sai because its footprint was near 103.6-105.6E. The selected public GLO-30 N20/E099 tile covers Mae Sai west of 100E; eastern-edge DEM coverage remains partial and is reported explicitly.
