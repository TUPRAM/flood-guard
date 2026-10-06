# Mae Sai SAR physical baseline and threshold candidate

Status: **PARTIAL, candidate research only**. This note records the method and
the September 23, 2026 local execution. It does not establish a qualified flood
observation, model accuracy, affected population, road closure, FPPS, an action
class, or an official warning.

## Physical source and method

The existing `resources/snap/sentinel1_grd_rtc_v1.xml` uses SNAP 13.0.0. It
applies precise orbit files and thermal-noise removal to the original Sentinel-1A
IW GRD VV/VH SAFE products. SNAP Calibration emits **Beta0**, Terrain-Flattening
uses the external DEM and emits **Gamma0**, and Range-Doppler Terrain-Correction
orthorectifies Gamma0 VV/VH to a 10 m EPSG:32647 grid. The canonical extractor
uses bilinear interpolation for continuous intensity and angle bands, nearest
neighbour for the categorical layover/shadow band, and converts supported Gamma0
intensity to dB. It preserves invalid SAR and layover/shadow as unsupported.

This is **Gamma0, not the proposal's literal Sigma0**. Physical radiometric
calibration is not empirical flood-probability calibration. The graph contains
**no speckle-filter node**. The threshold experiment below did not apply a
filter, so it cannot be described as a filtered SAR method. A change to Sigma0,
filtering, or other radiometry requires a versioned method comparison and new
processing receipts, not a change to a display label.

The graph declares the Copernicus GLO-30 DEM as EGM2008 orthometric heights but
uses SNAP's bundled EGM96 geoid conversion. That is an approximation, not a
verified vertical datum transformation. Its `externalDEMNoDataValue=0` can
discard genuine sea-level terrain in other areas. The source DEM reports no
nodata tag; a read of the source window enclosing this 1280 × 1280 pilot grid
found 185,592 source pixels, none masked or exactly zero, with values about
380.49–1596.60 m. This reduces the immediate zero-elevation concern for this
grid only. The graph must be corrected or an explicit DEM validity mask proved
before transferring it to low-elevation areas.

The July canonical processing receipts bind the selected 3 and 15 September
2024 UTC SAFE pair, SNAP/graph bytes, precise orbit auxiliaries, DEM, output
bands, and the common 10 m grid. On September 23 the original ZIP SHA-256 values
were rechecked as `42433d6cfb55118abe21e6faabef56343cefc9f28817cd31eb9386d32f56543d`
(pre) and `ff4a604f57c9eb88421904659c7201d07b54b35a3bff6f3447ee548c40f6755b`
(post). Each ZIP contains one SAFE manifest and one VV and VH measurement. The
external DEM SHA-256 is `8965f85514b577b4b606c658412bfe3d713c0abf478d237539af309d8edb3757`.
The separate existing registration diagnostic reports 50 accepted windows and
0.138392 pixel error, below its 0.5 pixel contract limit. Scene correlation is
not independent geodetic validation, and the diagnostic cannot establish flood
truth.

## Versioned deterministic threshold experiment

`floodguard.sentinel1_adaptive_otsu_candidate.v1` accepts four already
processed, exactly aligned Gamma0 dB rasters, two layover/shadow masks, a
checksum-bound aligned JRC likely-permanent-water mask, and a checksum-bound
aligned DEM slope raster. It verifies the processing and context manifest
self-hashes, raster file hashes and source product IDs before processing. The
context builder and SAR processor use different *hash algorithms for grid
identity*; the baseline retains both tags and independently requires identical
CRS, affine, width and height. Missing or incompatible inputs fail closed.

The candidate feature is `0.4 × (pre VV dB − post VV dB) + 0.6 × (pre VH dB −
post VH dB)`. Positive values indicate darkening, not flood probability. Every
eligible pixel must have finite values on both dates and polarizations, a clear
layover/shadow code on both dates, known 0/1 permanent-water context, and valid
0–90° slope. Likely permanent water and slope above 20° abstain; missing context
and invalid SAR are unsupported. A potential candidate must darken in both VV
and VH and exceed the local composite threshold.

The frozen exploratory window rule is 256 × 256 pixels, stride 128, at least
4096 eligible samples, 64 Otsu histogram bins between the local 1st and 99th
percentiles, at least 8% in each split class, at least 1.5 dB class-mean
separation, and between-class variance at least 72% of clipped total variance.
Qualified overlapping-window thresholds are averaged at shared pixels; a pixel
without a qualified window abstains. Sparse, narrow, unbalanced and unstable
distributions abstain. These are **candidate QC settings**, not scientific
accuracy or promotion thresholds. No final reference was used to select them.
The masks encode unsupported, permanent-water abstention, steep-terrain
abstention and histogram abstention separately. A whole-scene abstention has
`candidate_grid_area_km2=null`, never zero observed flood.

The CLI is `scripts/build_sentinel1_threshold_baseline.py`. It requires all
eight raster paths, both processing manifests, the context-alignment manifest,
actual pre/post UTC acquisition times, event and grid IDs, and a new output
directory. Its receipt records input/output hashes, grid and context identities,
window-level thresholds or abstention reasons, counts, approximate projected
grid area, elapsed time, an estimated working-array memory bound and explicit
null measured peak process memory. It writes five GeoTIFFs and a self-hashed
JSON receipt atomically into an immutable new directory. The raster outputs
are not imported into an accepted decision or Public bundle.

From the repository root, the local replay command is below. Replace the two
external roots with locations on the current machine; the output directory
must not exist. The timestamp values come from the selected acquisition
manifest and must continue to match the SAFE product IDs.

```powershell
$dataRoot = '<external-data-root>/label_factory/mae_sai_pilot_v1'
$outputRoot = '<new-external-output-root>/mae_sai_2024_gamma0_otsu_v1'
$inputs = @(
  '--pre-vv-db', (Join-Path $dataRoot 'processing/pre_20240903_rtc_v1/pre_20240903_vv_db.tif'),
  '--pre-vh-db', (Join-Path $dataRoot 'processing/pre_20240903_rtc_v1/pre_20240903_vh_db.tif'),
  '--post-vv-db', (Join-Path $dataRoot 'processing/event_20240915_rtc_v1/event_20240915_vv_db.tif'),
  '--post-vh-db', (Join-Path $dataRoot 'processing/event_20240915_rtc_v1/event_20240915_vh_db.tif'),
  '--pre-layover-shadow', (Join-Path $dataRoot 'processing/pre_20240903_rtc_v1/pre_20240903_layover_shadow_mask.tif'),
  '--post-layover-shadow', (Join-Path $dataRoot 'processing/event_20240915_rtc_v1/event_20240915_layover_shadow_mask.tif'),
  '--permanent-water', (Join-Path $dataRoot 'context/context_alignment_v2_jrc50/permanent_water_context.tif'),
  '--terrain-slope-degrees', (Join-Path $dataRoot 'context/context_alignment_v2_jrc50/slope.tif'),
  '--pre-processing-manifest', (Join-Path $dataRoot 'processing/pre_20240903_rtc_v1/pre_20240903_processing_run.json'),
  '--post-processing-manifest', (Join-Path $dataRoot 'processing/event_20240915_rtc_v1/event_20240915_processing_run.json'),
  '--context-alignment-manifest', (Join-Path $dataRoot 'context/context_alignment_v2_jrc50/context_alignment_manifest.json')
)
uv run --extra evidence python scripts/build_sentinel1_threshold_baseline.py @inputs `
  --pre-observed-at-utc '2024-09-03T23:16:00.776136Z' `
  --post-observed-at-utc '2024-09-15T23:16:01.675690Z' `
  --event-id mae_sai_2024 `
  --study-area-id mae_sai_label_factory_pilot_grid `
  --output-directory $outputRoot
```

## Actual Mae Sai pilot-grid result

The current receipt is `proposal_execution/mae_sai_2024_gamma0_otsu_v1_20260923r3/candidate_receipt.json`
under the configured external data root, SHA-256
`7814cfb5f936952a581ab72c40bde7ab14f638715834f39974dddfa81c5394fe`.
The self-hash and all five output hashes passed independent recomputation.
The earlier `...20260923/` and `...20260923r2/` trials are superseded.
The first exposed a misleading numeric zero-area field during whole-scene
abstention; the final revision also adds source stability checks and runtime
versions. Their bytes remain outside Git for audit. Do not consume those trials.

| Pilot-grid result | Value |
| --- | ---: |
| Total 10 m cells | 1,638,400 |
| Unsupported inputs or geometry | 30,034 |
| Likely permanent-water abstention | 25 |
| Slope abstention | 671,955 |
| Histogram abstention | 936,386 |
| Classified candidate / classified non-candidate | 0 / 0 |
| Qualified Otsu windows | 0 of 81 |
| Candidate area | **Unknown (`null`)** |

All 81 windows passed sample support but failed the predeclared bimodality
check. Their between-class variance fractions were 0.598–0.651, below 0.72.
This is an informative failure of this conservative method on these source
rasters, **not an observed absence of flood**. The output is an abstention
diagnostic; there is no flood polygon, footprint for an accepted observation,
clipped AOI area, boundary-repair lineage, or independent error metric to
report. The grid is a rectangular label-factory pilot extent, not the AOI-01
administrative intersection. Estimated working arrays are about 105 MB; peak
process memory was not measured. The prior full SNAP processing was not rerun.

## Next evidence dependencies

1. Review physical quality and false-positive strata, especially urban double
   bounce, wet soil, permanent-water edges, steep terrain, shadow, narrow
   channels and speckle. If a documented speckle filter or different physical
   feature is justified, version the method and compare it on a predeclared
   development partition. Never relax histogram QC merely to obtain plausible
   looking closure geometry.
2. Revalidate the SNAP DEM datum and zero-nodata behavior for each transferred
   area. Measure radiometric, geometric and temporal uncertainty, and bind any
   new SNAP run to the exact SAFE, orbit, DEM and auxiliary bytes.
3. Obtain a purpose-qualified independent in-area reference and the existing
   partition/holdout authority before final observation metrics. Training-label
   qualification, report-only model selection, and downstream decision
   acceptance are separate gates. Only then consider AOI clipping, vector
   repair lineage and downstream exposure/access comparison.

All outputs remain non-operational with `official_warning=false`. The
deterministic Otsu baseline is geospatial analysis, not a trained GeoAI model.
