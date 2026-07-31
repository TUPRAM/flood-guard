# Governed reviewer-change derivative lineage

## Purpose and safety boundary

`floodguard.review_derivative_lineage_receipt.v1` supplies technical lineage
for three derived SAR displays that may later enter a blinded human-review
bundle after attributable Reference-Authority approval:

1. `vv_change`;
2. `vh_change`; and
3. `fixed_stretch_change_composite`.

It does not itself grant Reference-Authority approval and does not produce a flood label, model target, validation reference, decision
input, FPPS component, or warning. The receipt proves that named source/output
bytes and declared parameters were checked together. It does not independently
recompute the rasters or prove scientific correctness. Keep the derivative
generator, build spec, source rasters, and outputs in the controlled external
workspace.

The canonical FloodGuard change convention is:

```text
VV change = pre-event VV dB - event-time VV dB
VH change = pre-event VH dB - event-time VH dB
```

A positive result means event-time backscatter is lower than pre-event
backscatter. That can be flood-like, but it is not flood truth: radar shadow,
wet soil, agricultural change, speckle, terrain effects, temporal change, and
misregistration can create similar evidence.

## Build-spec contract

The JSON object is exact-schema: unknown and missing fields are rejected. Local
paths are used to re-hash files and are removed from the receipt. All timestamps
use UTC seconds ending in `Z`; all checksums are complete lowercase SHA-256.

`source_inputs` must exactly cover every pre/event VV/VH asset in the processing
receipt. The current Mae Sai receipt uses four single-polarization GeoTIFFs:
pre VV, pre VH, event VV, and event VH. Each row declares its exact
`polarizations` list and `band_by_polarization` mapping. File names, bytes, and
governed polarization assignments must match the processing receipt and sealed
source registry. A two-raster dual-polarization layout is supported only when
each asset genuinely supplies and declares both bands.

The three `layers` must use unique derivative ids and exactly these roles. Every
output declares the processing-receipt CRS, six-term affine, width, and height.
The receipt validates these declarations against the common grid and re-hashes
the output bytes.

```json
{
  "artifact_schema": "floodguard.review_derivative_build_spec.v1",
  "derivative_set_id": "MAE-SAI-2024-REVIEW-DERIVATIVES-V1",
  "event_id": "TH-MAESAI-2024-09",
  "generated_at_utc": "2026-07-11T00:00:00Z",
  "processing_software": "<exact generator name>",
  "processing_software_version": "<exact pinned version or commit>",
  "source_inputs": [
    {
      "asset_id": "<pre-event VV processing-receipt asset id>",
      "processed_file_path": "<local path to exact processed pre-event VV raster>",
      "processed_file_sha256": "<64 lowercase hex>",
      "polarizations": ["VV"],
      "band_by_polarization": {"VV": "<exact VV dB band identifier>"}
    },
    {
      "asset_id": "<pre-event VH processing-receipt asset id>",
      "processed_file_path": "<local path to exact processed pre-event VH raster>",
      "processed_file_sha256": "<64 lowercase hex>",
      "polarizations": ["VH"],
      "band_by_polarization": {"VH": "<exact VH dB band identifier>"}
    },
    {
      "asset_id": "<event-time VV processing-receipt asset id>",
      "processed_file_path": "<local path to exact event-time VV raster>",
      "processed_file_sha256": "<64 lowercase hex>",
      "polarizations": ["VV"],
      "band_by_polarization": {"VV": "<exact VV dB band identifier>"}
    },
    {
      "asset_id": "<event-time VH processing-receipt asset id>",
      "processed_file_path": "<local path to exact event-time VH raster>",
      "processed_file_sha256": "<64 lowercase hex>",
      "polarizations": ["VH"],
      "band_by_polarization": {"VH": "<exact VH dB band identifier>"}
    }
  ],
  "layers": [
    {
      "derivative_id": "MAE-SAI-2024-VV-CHANGE-V1",
      "layer_role": "vv_change",
      "output_file_path": "<local VV-change GeoTIFF path>",
      "output_file_sha256": "<64 lowercase hex>",
      "display_name": "VV backscatter drop, pre minus event dB, fixed stretch",
      "path_hint": "review_context/vv_change_v1.tif",
      "output_crs": "EPSG:32647",
      "affine_transform": [10.0, 0.0, "<origin x>", 0.0, -10.0, "<origin y>"],
      "width_pixels": "<positive integer>",
      "height_pixels": "<positive integer>",
      "nodata_convention": "valid only where both VV inputs are valid; nodata=<exact value>",
      "output_dtype": "float32",
      "transformation_parameters": {
        "operation": "pre_minus_event_db",
        "expression": "pre_db - event_db",
        "polarization": "VV",
        "pre_input_asset_id": "<pre-event asset id>",
        "event_input_asset_id": "<event-time asset id>",
        "pre_band": "<exact pre VV band identifier>",
        "event_band": "<exact event VV band identifier>",
        "input_units": "dB",
        "output_units": "dB_change",
        "validity_rule": "valid_where_both_inputs_valid"
      },
      "display_parameters": {
        "renderer": "single_band_fixed_stretch",
        "stretch_min": -10.0,
        "stretch_max": 10.0,
        "gamma": 1.0,
        "clamp": true,
        "color_map_id": "<versioned fixed colour-map id>",
        "color_stops": [
          {"value": -10.0, "hex": "#2166AC"},
          {"value": 0.0, "hex": "#F7F7F7"},
          {"value": 10.0, "hex": "#B2182B"}
        ],
        "resampling": "nearest"
      },
      "confidence_class": "medium",
      "assumptions": "Display-only pre-minus-event VV change; not flood truth.",
      "formal_review_display_only": true,
      "allowed_for_blinded_review": true,
      "query_model_only": true,
      "eligible_for_decision_layer": false,
      "eligible_for_fpps": false,
      "eligible_for_warning": false
    },
    {
      "derivative_id": "MAE-SAI-2024-VH-CHANGE-V1",
      "layer_role": "vh_change",
      "output_file_path": "<local VH-change GeoTIFF path>",
      "output_file_sha256": "<64 lowercase hex>",
      "display_name": "VH backscatter drop, pre minus event dB, fixed stretch",
      "path_hint": "review_context/vh_change_v1.tif",
      "output_crs": "EPSG:32647",
      "affine_transform": [10.0, 0.0, "<origin x>", 0.0, -10.0, "<origin y>"],
      "width_pixels": "<positive integer>",
      "height_pixels": "<positive integer>",
      "nodata_convention": "valid only where both VH inputs are valid; nodata=<exact value>",
      "output_dtype": "float32",
      "transformation_parameters": {
        "operation": "pre_minus_event_db",
        "expression": "pre_db - event_db",
        "polarization": "VH",
        "pre_input_asset_id": "<pre-event asset id>",
        "event_input_asset_id": "<event-time asset id>",
        "pre_band": "<exact pre VH band identifier>",
        "event_band": "<exact event VH band identifier>",
        "input_units": "dB",
        "output_units": "dB_change",
        "validity_rule": "valid_where_both_inputs_valid"
      },
      "display_parameters": {
        "renderer": "single_band_fixed_stretch",
        "stretch_min": -10.0,
        "stretch_max": 10.0,
        "gamma": 1.0,
        "clamp": true,
        "color_map_id": "<versioned fixed colour-map id>",
        "color_stops": [
          {"value": -10.0, "hex": "#2166AC"},
          {"value": 0.0, "hex": "#F7F7F7"},
          {"value": 10.0, "hex": "#B2182B"}
        ],
        "resampling": "nearest"
      },
      "confidence_class": "medium",
      "assumptions": "Display-only pre-minus-event VH change; not flood truth.",
      "formal_review_display_only": true,
      "allowed_for_blinded_review": true,
      "query_model_only": true,
      "eligible_for_decision_layer": false,
      "eligible_for_fpps": false,
      "eligible_for_warning": false
    },
    {
      "derivative_id": "MAE-SAI-2024-CHANGE-RGB-V1",
      "layer_role": "fixed_stretch_change_composite",
      "output_file_path": "<local fixed RGB GeoTIFF path>",
      "output_file_sha256": "<64 lowercase hex>",
      "display_name": "Fixed-stretch VV and VH change composite",
      "path_hint": "review_context/change_rgb_v1.tif",
      "output_crs": "EPSG:32647",
      "affine_transform": [10.0, 0.0, "<origin x>", 0.0, -10.0, "<origin y>"],
      "width_pixels": "<positive integer>",
      "height_pixels": "<positive integer>",
      "nodata_convention": "valid only where both change inputs are valid; nodata=<exact value>",
      "output_dtype": "uint8",
      "transformation_parameters": {
        "operation": "fixed_stretch_rgb_composite",
        "input_derivative_ids": [
          "MAE-SAI-2024-VV-CHANGE-V1",
          "MAE-SAI-2024-VH-CHANGE-V1"
        ],
        "red_expression": "<complete fixed numeric VV/VH expression>",
        "green_expression": "<complete fixed numeric VV/VH expression>",
        "blue_expression": "<complete fixed numeric VV/VH expression>",
        "validity_rule": "valid_where_all_inputs_valid",
        "channel_min": 0,
        "channel_max": 255
      },
      "display_parameters": {
        "renderer": "rgb_pre_stretched",
        "red_band": 1,
        "green_band": 2,
        "blue_band": 3,
        "gamma": 1.0,
        "resampling": "nearest"
      },
      "confidence_class": "medium",
      "assumptions": "Display-only fixed composite; not flood truth.",
      "formal_review_display_only": true,
      "allowed_for_blinded_review": true,
      "query_model_only": true,
      "eligible_for_decision_layer": false,
      "eligible_for_fpps": false,
      "eligible_for_warning": false
    }
  ],
  "assumptions": "Governed display lineage only; no flood truth, validation, decision, FPPS, or warning claim.",
  "formal_review_display_only": true,
  "allowed_for_blinded_review": true,
  "query_model_only": true,
  "eligible_for_decision_layer": false,
  "eligible_for_fpps": false,
  "eligible_for_warning": false
}
```

The angle-bracket values are placeholders and must be replaced with real exact
values. `width_pixels` and `height_pixels` are JSON integers in the real file,
not quoted strings. All three output grid declarations must exactly match the
processing receipt. `stretch_min` and `stretch_max` are pilot decisions; keep
them identical for both formal reviewers and do not calculate them from the
reviewed scene after looking at query contents.

Dynamic terms such as `auto`, `percentile`, `quantile`, `histogram`,
`data_min`, and `data_max` are rejected anywhere in display/composite
parameters. Use a new versioned set and recalibrate reviewers if a display
formula, stretch, colour map, source, grid, or output changes.

## Candidate generation and authority status

`scripts/build_review_derivative_candidates.py` generates the continuous
VV/VH changes and pre-stretched RGB candidate before building the lineage
receipt. It validates all four input GeoTIFFs against governance and the
processing receipt, writes into a new directory, and records
`authority_approval_status=authority_approval_pending`. Its validator then
independently recomputes every continuous change cell, every RGB channel, and
the all-input validity mask from the exact source files. After-the-fact
saturation/coverage statistics are reported but carry
`statistics_influence_display=false`.

The current conservative candidate uses a symmetric `-10..+10 dB` range,
gamma `1.0`, nearest display resampling, and fixed blue/neutral/red stops. Its
RGB channels are fixed-scaled VV change, VH change, and their mean. This choice
preserves increases, near-zero change, and drops without consulting the scene
histogram. It remains a proposal for authority review, not a scientific
recommendation or flood map.

The lineage receipt's `production_review_eligible=true` means only that its
source governance and technical lineage passed the production validator. It
does **not** mean the display is Reference-Authority approved or may be sent to
reviewers. The controlling human status is the candidate manifest's
`authority_approval_status`. A pending candidate must not be added to
`context_layers.csv` or a bundle. A separate attributable, timestamped
Reference-Authority decision is still required.

## Context-row binding

For each receipt layer, create one `context_layers.csv` row using this exact
mapping:

| Context field | Receipt value |
| --- | --- |
| `context_layer_id` | `layer.derivative_id` |
| `event_id` | `receipt.event_id` |
| `layer_role` | `layer.layer_role` |
| `source_registry_sha256` | `receipt.source_registry_sha256` |
| `source_asset_id` | `layer.derivative_id` |
| `source_product_id` | `receipt.derivative_set_id` |
| `display_name` | `layer.display_name` |
| `path_hint` | `layer.path_hint` |
| `crs` | `layer.output_crs` |
| `acquisition_time_utc` | `layer.acquisition_time_utc` |
| `source_sha256` | `receipt.source_raster_binding_sha256` |
| `processed_layer_sha256` | `layer.output_file_sha256` |
| `allowed_for_blinded_review` | `true` |
| `confidence_class` | `layer.confidence_class` |
| `assumptions` | `layer.assumptions` |

No partial derivative set is accepted. The bundle writer copies the verified
receipt as `review_derivative_lineage_receipt.json`, hashes that copy in
`bundle_manifest.csv`, and later formal annotation import repeats the semantic
checks against the exact processing receipt, review regions, context rows, and
governance package.

Do not execute that bundle step while the candidate-generation manifest says
`authority_approval_pending`. Technical lineage is necessary but not human
approval.

## Versioning and incident rules

- Never overwrite a build spec, derivative output, or receipt.
- Any source byte, output byte, transformation, display parameter, grid,
  software version, or assumption change creates a new derivative set id.
- If a reviewer has already calibrated on the old visible evidence, a material
  display change requires a new unseen calibration before formal review.
- If an external output no longer matches the receipt hash, stop delivery,
  quarantine it, and build a new version. Do not edit the receipt.
- Keep model scores, weak labels, selection metadata, and the other reviewer's
  geometry outside the derivative workspace and reviewer bundle.
