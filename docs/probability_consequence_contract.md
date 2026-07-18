# Probability-raster road and facility consequence contract

## Purpose

`floodguard.probability_consequences` is the governed bridge from one immutable
class-1 flood-probability raster to road-corridor and facility-point evidence.
It is separate from area zonal aggregation and does not change FloodGuard road
risk, access loss, equity, FPPS weights, or A–E classes.

The bridge produces modeled probability evidence. It does **not** establish an
observed road closure, a safe route, a facility's operating status, or a
facility's suitability as an evacuation destination.

## Required lineage

The caller supplies:

- the probability raster and its raster receipt;
- the exact model-run manifest;
- road and facility GeoJSON plus separate geometry receipts;
- projected metre-based CRS/grid metadata;
- explicit road and facility buffer distances;
- an external HMAC-SHA256 signing key and public key ID.

The adapter reads each source from one stable descriptor, checks SHA-256 bytes,
validates the raster CRS, transform, bounds, dimensions, nodata, band name,
dtype and `[0,1]` range, and binds every result to canonical hashes of the
model, raster, and geometry receipts. No local absolute path or signing key is
serialized.

Both road and facility geometry receipts must carry the same non-empty
`study_area` as the model-run manifest. The signed consequence receipt records
that study area and verification repeats the equality check, so geometry from
another dataset cannot be substituted merely because its CRS and bounds happen
to overlap.

Road geometry must be `LineString` or `MultiLineString`; facility geometry must
be `Point`. Feature IDs must be unique, every feature must carry an area join
ID, and all features must intersect or lie strictly inside the raster. A
facility point over nodata is rejected rather than inferred from surrounding
pixels.

## Sampling semantics

- Road evidence uses probability pixels whose centers fall inside the explicit
  metric road buffer.
- Facility evidence records the exact containing pixel and statistics for an
  explicit metric facility buffer.
- `all_touched=false` and linear P90 interpolation are fixed in schema `1.0`.
- Bridge evidence is reported separately, but always retains
  `observed_closure_status=not_observed`.
- Facility evidence always retains
  `safe_destination_status=not_determined_by_probability_model`.
- Only an `agency_verified` facility with
  `emergency_role=designated_evacuation` receives
  `agency_verified_designated_role=true`. This records a verified designation,
  not current operation, reachability, capacity, or safety. Probability alone
  never grants this state.

## Fail-closed eligibility

Normal execution requires:

- `run_status=completed` and `processing_allowed=true`;
- a model and raster receipt with exact run/grid/checksum binding;
- decision-eligible `official_input` probability evidence for decision use;
- both geometry receipts marked `authoritative_for_study_area` for decision
  use.

`fixture_demo` runs are rejected. A `candidate` model or
`provenance_tracked_candidate` geometry can be processed only when the caller
explicitly passes `allow_report_only=True`. Such a receipt always contains:

```text
aggregation_status=report_only
can_feed_decision_layer=false
eligible_for_decision_layer=false
official_warning=false
reason_blocked=<exact gate reasons>
```

Changing a source raster, road file, facility file, study-area identity,
lineage receipt, result statistic, eligibility field, safety wording, or
signature causes verification to fail.

## CLI

Raster execution requires the root `geo` and `theos2` optional dependencies
(`rasterio`, `Shapely`, and their normal geospatial stack). Importing the root
FloodGuard package still does not import or require GeoAI, PyTorch, a GPU, or
network access.

Keep the signing secret external and write large raster inputs outside the
repository:

```powershell
$env:FLOODGUARD_CONSEQUENCE_SIGNING_KEY = '<external secret of at least 32 bytes>'
$env:FLOODGUARD_CONSEQUENCE_SIGNING_KEY_ID = 'consequence-authority-v1'

uv run python scripts/build_probability_consequences.py `
  --probability-raster <external-probability.tif> `
  --model-run-manifest <model-run.json> `
  --probability-raster-receipt <probability-receipt.json> `
  --roads <roads.geojson> `
  --road-geometry-receipt <roads-receipt.json> `
  --facilities <facilities.geojson> `
  --facility-geometry-receipt <facilities-receipt.json> `
  --road-buffer-m 15 `
  --facility-buffer-m 100 `
  --generated-at 2026-07-18T10:00:00Z `
  --output <external-receipt.json>
```

The CLI refuses to overwrite an existing receipt. Add `--allow-report-only`
only for explicitly labeled candidate analysis.

## Current Mae Sai state

The repository's current Mae Sai roads and facilities are provenance-tracked
open-context candidates, and the controlled real-data model experiment remains
blocked. Therefore this adapter is implemented and synthetically tested, but
no committed Mae Sai receipt may claim decision eligibility. The existing OSM
facility candidates remain unverified for emergency role, current operation,
capacity, accessibility, and safe-destination use.
