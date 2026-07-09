# Manual QGIS Reference Mask Protocol

Status: manual weak-reference lane implemented; source geometry not yet created.

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
C:\Users\iputu\Documents\FloodGuard_external_data\manual_reference\mae_sai_2024\
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

## Inspection Workflow

After creating the GeoPackage, run:

```powershell
cd "C:\Users\iputu\Documents\Flood Guard"

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

After this manifest is ready, the next implementation can add a separate weak-reference non-ML SAR baseline path. That path should report metrics as candidate metrics and keep the official validation/ML-label gates blocked.
