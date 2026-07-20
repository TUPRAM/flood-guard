# Controlled three-model experiment gate status

Gate status: **BLOCKED**

FloodGuard did not run a real three-model experiment unless every gate below was cryptographically bound and verified. This report is non-operational, is not field validation, and is not an official warning.
Catalog/licence approval requires an externally verifiable Ed25519 authority decision. Holdout, reference, model, and evaluation evidence require role-separated HMAC-signed internal integrity receipts; editable CSV claims are not authority.

## Acquisition evidence

| Role | Product ID | Checksum status | Processing allowed |
| --- | --- | --- | --- |
| post_event_sar | `5251b74b-0bbd-4365-9eb4-fa33292e175a` | verified | true |
| pre_event_sar | `aaaef3af-fa49-4115-bf0f-f54175e7aedf` | verified | true |
| reference_mask | `PENDING-QUALIFIED-MAE-SAI-2024-REFERENCE-RASTER` | missing | false |

## Gate evidence

- Acquisition and byte integrity: `blocked`
- Reviewer calibration: `missing`
- Immutable spatial holdout: `missing`
- Signed qualified reference cells: `missing`
- Predeclared promotion policy: `missing`
- Post-execution model evidence (informational): `not_expected_before_execution`

## Exact blockers

- acquisition_authority: externally signed product-specific authority decision and internal integrity receipt are missing
- promotion_policy: signed predeclared policy is missing
- reference_cells: signed mask-derived cells, calibration projection, or error-strata evidence is missing
- reference_mask: ML-label/model use permission is not confirmed
- reference_mask: checksum status is not verified
- reference_mask: derived metrics permission is not confirmed
- reference_mask: license is not confirmed for this experiment
- reference_mask: local analysis permission is not confirmed
- reference_mask: local artifact is missing
- reference_mask: processing_allowed is false
- reference_mask: redistribution/reference-only status is unresolved
- reference_mask: reference mask is not qualified expert/adjudicated truth
- reference_mask: temporal alignment is not confirmed
- reviewer_calibration: dual-signed qualification is missing
- spatial_holdout: signed polygon and frozen cell-membership receipt is missing

## Official-source acquisition path

- Sentinel-1 products are catalogued and downloaded through the official [Copernicus Data Space OData API](https://documentation.dataspace.copernicus.eu/APIs/OData.html).
- [Copernicus Data Space terms](https://dataspace.copernicus.eu/terms-and-conditions) state that Sentinel data are free, full, and open, subject to the Sentinel legal notice and attribution requirements.
- [UNOSAT product 3991](https://unosat.org/products/3991) is useful event context for Mae Sai but its published PDF is preliminary analysis, not a qualified pixel-level reference mask.
- The inspected Sentinel Asia / MBRSC geometry remains a reference candidate because product-specific validation, derived-metric, screenshot, redistribution, and ML-label permissions are unresolved.

## Integrity finding

The controlled manifest uses the independently re-hashed original SAFE pair. It does not reuse the older COG acquisition receipt: the current external COG archive bytes do not match the hashes recorded in `outputs/cdse_mae_sai_acquisition_manifest.csv`. Those COG files require controlled re-registration before any future use.

Spatial evaluation membership is re-derived from descriptor-bound bytes, immutable train/calibration/final-holdout polygons, and a signed grid contract on a projected metre-based equal-area CRS. Physical cell area comes only from the grid affine determinant; the complete cell-ID, row/column, and affine-center membership must match exactly. Any relabelled, missing, out-of-polygon, boundary-ambiguous, grid-mismatched, or checksum-substituted cell fails closed. Each signed model-run receipt must bind a strict lane-specific model contract and a threshold fixed from the signed calibration partition before final-holdout evaluation.

Zero-division convention: `finite: 0/0=0.0; nonzero/0=1.0; otherwise numerator/denominator`. Physical area error is reported in square metres as well as a finite ratio.

## Decision

No real training or three-model result was produced. Existing weak-reference metrics remain candidate screening evidence and are not substituted for this controlled experiment.

Receipt SHA-256: `0a1a164c0bf90d5ffd1087da9dc9c1dad954506eb5b0d15b0234b57866e11e61`
