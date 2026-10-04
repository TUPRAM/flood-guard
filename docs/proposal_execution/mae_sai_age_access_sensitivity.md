# Mae Sai 2024 age grid on fixed 2020 access nodes

Status: **PASS for a local, mixed-vintage scenario sensitivity; PARTIAL for age-source coverage and BLOCKED for accepted age exposure/equity.** This run does not establish historical 2024 hospital access, an observed road closure or event-day demographics. No output is eligible for accepted FPPS or an A-E action class.

## Sources and method

The source is WorldPop Global2 R2025A v1, Thailand constrained total-sex **2024** age counts on the original 30 arc-second (~1 km) grid, published 2025-09-01. The complete 20-band acquisition manifest is `C:/Users/iputu/Documents/Project Support/FloodGuard/open-data/2026-09-23-worldpop-age-2024-r2025a-1km-ua/acquisition_manifest.json` (SHA-256 `f7a169877177a374bc461724dcb93b6ec96d76451347cd2e98dc2fc7b0f8356c`). The reviewed full-unit/AOI comparison is `C:/Users/iputu/Documents/Project Support/FloodGuard/execution/2026-09-23/worldpop-age-mae-sai-2024-1km-v1/age_review.json` (SHA-256 `a526c587e4c0bc1921b7464a3256f34cb31a6e174a558d7f2e329b1797ec6d5a`). The source's public catalog indicates CC BY 4.0, while ODbL may apply to OSM/building-derived products; purpose-specific hosted derivative rights remain for review. This run remains in local research outputs.

The access comparator is the immutable Mae Sai finals scenario package dated 2026-09-21: 2020 WorldPop demand cells, 2022-01-22 Thai reporting boundaries, later OSM roads, one candidate hospital, and modelled 5 km/h walking. The script verifies the package's file and canonical context hashes and recomputes `hospital-walking-1` baseline and its **preselected** `close_edge-1` intervention. The closure is one assumed OSM edge (`osm-way-934550386-segment-0`), chosen by the existing baseline path-tree rule before this age analysis. It is **not** tied to a flood observation or dated road closure. Recomputed 2020 30-minute newly lost access equals the stored 15,453.4572 modelled residents. Facility entrances and event-time operation remain unverified.

For each 2022 reporting unit intersected with AOI-01, the method computes projected-area overlap for each original 2024 age-source cell. Every age band's cell count is multiplied by that **unit/AOI intersection fraction**. The six selected unit geometries match those in the prior age review within 1 m² per intersection; the full 82-unit finals source is separately hash-bound. The source age groups are children **0-14**, older adults **60+**, and other ages **15-59**. Their source-cell masses are allocated to fixed positive 2020 demand nodes **within the same source cell and reporting unit** in proportion to those nodes' 2020 total-population weights. A cell with positive age mass and no 2020 demand node keeps that age mass unallocated. Invalid age-source cells are unsupported; their age count is unknown, never zero. A zero-valued valid cell remains a valid zero. No bilinear resampling or province/district share is used.

The full, source-supported 2024 age count within the AOI/reporting-unit union is the rate denominator. For each age group and 15/30/60-minute threshold, modelled new loss requires a known connected baseline route within the threshold and loss of that threshold after the assumed closure. An unsnapped/missing-connector node has unknown new-loss status. The conservative access-coverage sensitivity interval is `[known new loss / supported age total, (known new loss + unallocated age mass + missing-connector age mass) / supported age total]`, capped at 1. This is **not** a statistical confidence interval and does not bound age-model error or missing age-source cells. Group comparisons use the full-precision equity contract; zero/zero loss ratios remain null. A comparison group is explicitly an age complement, not a population measured to be otherwise non-vulnerable.

## Result and limits

The six-unit AOI intersection has 52,679.8617 modelled 2024 residents on **80.7775 km² of common valid age raster support**. Another **4.0958 km²** of selected reporting intersection lacks common valid source-cell support, so no numeric population denominator is claimed there. The AOI also has **19.8572 km² outside the selected Thai reporting units**; it is a separate geography category, not missing Thai population. The fixed 2020 routing comparator has 44,159.7846 modelled residents. These vintages and boundary rules differ; their totals are not expected to match. Of the 2020 demand, 442.4131 residents have no valid age-source support at their nodes. The 2024 age mass unallocated because its 1 km cell/unit has no 2020 node is 18.0067 children, 22.8125 older adults and 60.9523 others; additional age mass at nodes with missing graph connectors is included in the unknown access column below.

| 2024 modelled group | Supported denominator | Access unknown | New 15-min loss | New 30-min loss | New 60-min loss | New all-route loss |
|---|---:|---:|---:|---:|---:|---:|
| Children 0-14 | 9,455.7 | 72.5 | 764.2 | 3,800.2 | 6,902.9 | 9,024.2 |
| Older adults 60+ | 11,522.3 | 96.1 | 1,027.8 | 4,715.8 | 8,376.2 | 11,031.9 |
| Other ages 15-59 | 31,701.9 | 248.2 | 2,626.8 | 12,797.7 | 23,119.5 | 30,279.0 |

These are modelled, redistributed **2024 residential age counts** under a hypothetical closure on a graph with 2020 demand nodes. Threshold-loss groups can differ by threshold and cannot be added. All-route loss is a separate route-availability measure; connected graph components with no modelled route are not observed isolation. The unusually broad all-route effect is a property of this stress edge and network assumptions, not an event consequence estimate.

At 30 minutes, the source-supported AOI comparison of children versus ages 15+ gives a **-0.328 percentage-point** known-loss difference, with missing-access sensitivity **-1.125 to +0.439 points**. Older adults versus ages <60 gives **+0.600 points**, bounded **-0.180 to +1.433 points**. Both intervals include zero; this scenario cannot establish an age disparity. Several unit-level zero/zero comparisons have a null ratio with an explicit reason. The intervals still exclude the 4.0958 km² without valid age-source support and all population-model uncertainty, so they cannot establish no disparity either.

## Artifact and reproduction

The immutable external output is `C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/2026-09-23-mae-sai-age-access-v2/`:

- `age_access_sensitivity.json` SHA-256 `64724bce08dcef13297f4b8fa6915218deedcd4ef07db61d736700046daeabb0`, internal canonical identity `dc344280151d5d5efdd716c57b02a3868506e37d217c8c46e1299f62484b357f`.
- `source_cell_ledger.json` SHA-256 `2e244149364523a741456f04401350862efa906547cadcfc4a30f19de1c84a8d` records source grid row/column, area fraction, source age-group mass, 2020 support and unallocated mass for every unit-cell intersection.
- `run_receipt.json` SHA-256 `083d08e5fa0117e3e10754bba6b57299894fdab9ee7a762fd47c33f8f481f51d` lists input/output sizes and hashes, the builder hash and Git source commit/tree. A first immutable development run is retained at `2026-09-23-mae-sai-age-access-v1`; v2 is the reviewed output after adding the AOI aggregate.

The command actually run from the implementation worktree was:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'C:\Users\iputu\Documents\Flood Guard\.venv\Scripts\python.exe' scripts/bridge_worldpop_age_access.py `
  --acquisition-manifest 'C:\Users\iputu\Documents\Project Support\FloodGuard\open-data\2026-09-23-worldpop-age-2024-r2025a-1km-ua\acquisition_manifest.json' `
  --age-review 'C:\Users\iputu\Documents\Project Support\FloodGuard\execution\2026-09-23\worldpop-age-mae-sai-2024-1km-v1\age_review.json' `
  --age-review-units 'outputs\mae_sai_admin_context.geojson' `
  --aoi 'resources\aoi\aoi-01_mae_sai_core.geojson' `
  --reporting-units 'C:\Users\iputu\Documents\Project Support\FloodGuard\evidence-demo\2026-09-21-mae-sai-finals\event_review\reporting_units.geojson' `
  --finals-dir 'C:\Users\iputu\Documents\Project Support\FloodGuard\evidence-demo\2026-09-21-mae-sai-finals\finals' `
  --output-dir 'C:\Users\iputu\Documents\Project Support\FloodGuard\research-runs\2026-09-23-mae-sai-age-access-v2'
```

Reproduction must choose a **new** output directory; source files and prior receipts remain unchanged. The run validates all 20 age-source TIFF bytes, the prior review receipt, both reporting geometry lineages, final-package bytes and canonical context, and exact baseline/scenario recomputation. Focused verification: `python -m pytest tests/test_bridge_worldpop_age_access.py tests/test_equity.py tests/test_evidence_age_surface.py -q` (**23 passed**); `python -m py_compile scripts/bridge_worldpop_age_access.py` passed.

This bridge can support a labelled sensitivity in a restricted analytical view after the separate purpose/export review. Accepted Mae Sai equity still requires an eligible event observation, reviewed road/service assumptions, appropriate year/geography controls, a declared completeness decision for missing age and access coverage, and the downstream acceptance chain. Neither this run nor the WorldPop release supplies those approvals.
