# Manual QGIS Reference Mask Protocol

Status: manual weak-reference lane implemented; a checksum-bound cross-border
geometry exists for candidate calibration only. No in-area qualified Thailand
event reference exists, and the current geometry cannot clear validation or
ML-label gates.

This protocol defines how FloodGuard may use a project-owned manual QGIS flood mask when official/reference-mask provider clearance is too slow for the hackathon timeline.

The manual mask is a weak reference candidate. It is not official validation truth, not an official warning, and not a redistribution claim for provider source data.

## Intended Use

Manual reference mask status:

```text
weak_reference_candidate
```

Allowed use:

- candidate validation metrics
- visual QA
- non-operational demo reporting

Not allowed use:

- official validation truth
- official warning
- redistributed source data claim
- unqualified ML labels

Recommended language:

```text
Real Sentinel-1 non-ML baseline evaluated against a manually digitized weak-reference candidate. Non-operational. Not an official warning. Not field validated.
```

## QGIS Creation Steps

Create one small polygon layer outside Git:

```text
<external-data-workspace>/manual_reference/mae_sai_2024/
```

Suggested file:

```text
mae_sai_manual_flood_reference.gpkg
```

Suggested layer name:

```text
manual_flood_extent
```

Required fields:

| Field | Required value guidance |
| --- | --- |
| `reference_id` | Stable id such as `MS-MANUAL-001`. |
| `confidence` | Use `low`, `medium`, or `high`; prefer `medium` unless review is repeated. |
| `source_basis` | Describe the visual basis, such as Sentinel-1 pre/post interpretation, OSM/DEM context, and UNOSAT report area sanity check. |
| `digitized_by` | Use the reviewer name or `[blank]` while preparing the demo. |
| `digitized_at` | Use ISO date or timestamp, such as `2026-07-09`. |
| `notes` | Describe inclusion/exclusion rules and uncertainty. |
| `not_official` | Must be `true` for every feature. |

Example feature attributes:

```text
reference_id = MS-MANUAL-001
confidence = medium
source_basis = Sentinel-1 pre/post visual interpretation; OSM/DEM context; UNOSAT report area sanity check
digitized_by = [blank]
digitized_at = 2026-07-09
notes = obvious floodplain/water-like polygons only; uncertain areas excluded
not_official = true
```

## Digitizing Guidance

- Digitize only obvious floodplain or water-like polygons.
- Exclude uncertain patches instead of over-labeling.
- Keep polygons focused around the Mae Sai review area.
- Use CDSE Sentinel-1 pre/post products as primary visual evidence once opened locally.
- Use Sentinel-2, THEOS-2, DEM, OSM, and UNOSAT public report evidence as context only.
- Do not copy, clip, or commit provider source geometry into the repo.
- Save the manual GeoPackage outside Git.

## Label-factory Import Semantics

The legacy weak-reference baseline rasterizes polygon interiors as `1` and the surrounding extraction window as `0` for historical candidate-metric reproducibility. That surrounding `0` is not an explicitly reviewed dry label.

When this GeoPackage enters the active-learning label factory:

- polygon interior becomes `weak_positive`;
- polygon exterior becomes `unreviewed` (`255`), never `dry_land`;
- an optional polygon-boundary buffer becomes `weak_uncertain`; and
- only a later explicit human review may assign dry, temporary flood, permanent water, uncertain, or unobservable classes.

The legacy binary raster must not be used as an unqualified training labelset.

## Inspection Workflow

After creating the GeoPackage, run:

```powershell
uv run python scripts/inspect_manual_reference_mask.py --require-existing
uv run python scripts/build_mae_sai_file_manifest.py
uv run python scripts/validate_mae_sai_file_manifest.py --allow-blocked
```

The inspection writes:

```text
outputs/manual_reference_mask_manifest.csv
```

The Mae Sai file manifest then includes an additional row:

```text
FloodGuard manual QGIS Mae Sai weak-reference candidate
```

That row may become ready for candidate metrics, but it must not set the official `reference_mask_status` to `confirmed`.

## Gate Rule

The manual weak-reference lane does not clear the existing official real-data gate.

Current intended states:

- `reference_mask_status=weak_reference_candidate`
- `candidate_validation_metrics_allowed=True` only after the GeoPackage exists, has a SHA-256 checksum, has required fields, contains features, and every feature has `not_official=true`
- `processing_allowed=False` in the official file-level manifest
- `official_validation_truth_allowed=False`
- `unqualified_ml_label_allowed=False`

## Next Development Step

The separate weak-reference baseline and batch query-summary paths are now
implemented. The current GeoPackage has one polygon self-intersection near
`99.8222022E, 20.4875101N`. The batch builder therefore fails closed unless the
operator explicitly requests a recorded geometry repair:

```powershell
uv run python scripts/build_weak_query_summary.py `
  --weak-vector <external_data_workspace>/manual_reference/mae_sai_2024/mae_sai_manual_flood_reference.gpkg `
  --vector-layer manual_flood_extent `
  --repair-invalid-geometry `
  --weak-source-manifest outputs/manual_reference_mask_manifest.csv `
  --query-manifest <external_data_workspace>/label_factory/mae_sai_pilot_v1/grids/canonical_supported_pool_v1/canonical_query_regions.csv `
  --output-directory <external_data_workspace>/label_factory/mae_sai_pilot_v1/weak_seed/manual_weak_query_summary_v2
```

The manifest records the original validity reason and
`repair_method=shapely.make_valid`. This is a reproducibility repair for weak
context, not evidence that the repaired shape is correct flood truth. The
current result covers 854 queries: four contain weak-positive cell centres and
850 remain wholly unreviewed.
