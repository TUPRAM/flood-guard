# Lower Chao Phraya routing-context comparison

Status: **PASS for the bounded walking-context experiment; PARTIAL for M4/M10 product repair.** This run changes the road and destination search radius around each AOI while keeping the 2020 residential demand cells and Thai reporting-unit assignments fixed. It does not supply a dated 2024 or 2025 flood observation, historical passability, verified hospital operation, a surveyed entrance, or an accepted access result.

## Evidence and method

- Source base: reviewed `14df822e8161cef4edd253f371a89c09d0e5fac9` (`HEAD^{tree}` `7817fb8f58d77028dc8e59f99bbd44e592efb715`) plus the uncommitted comparison script whose exact run SHA-256 is `961edabd552616f78062cf12071c5ed5b0f479e0844e0e648e3a248bc24b5a7e`. The script and its tests belong to the implementation worktree; the run did not modify source files or the old shared-case package.
- Inputs: Geofabrik Thailand OSM PBF `b7f46018249638413b1d318bc86519f140c27af20cac7c00d42fe03775b7add1` and WorldPop Thailand 2020 count raster `fb39d85dd150c45c7b25771f29bcd548e611afa0967224ac6d8ca05727230e20`. Both files have the recorded retrieval timestamp `2026-07-10T02:46:49Z`; that is **not** an OSM edit time or a 2024/2025 observation time. The source manifest permits context processing, with ODbL attribution/share-alike obligations for OSM and citation for WorldPop. The reporting-unit file SHA-256 is `013194e107f14258dc51b6bb1bbc3d5df02b7566432b06ea5ee8b827e5ae2a9a`.
- AOI demand and unit assignments reproduce the legacy 0 km context exactly by population-cell ID, coordinates and fractional count. The script rejects a changed roster. The surrounding routing polygon is a 5, 10 or 15 km EPSG:32647 buffer of the original demand rectangle; the same rectangle remains the demand denominator. The old reporting-unit union fully covers both rectangles. The expanded graph uses the same Thailand OSM PBF without the old rectangular road/destination clip. Walking remains an assumed 5 km/h, with the existing 100 m facility and 250 m population connector limits. No extra connector or junction is invented.
- Hospital candidates remain OSM map records. A contained point is excluded only when it shares a normalized name or Wikidata ID with its enclosing mapped site. This is source-object deduplication, not proof of one operating service or an entrance. `hospital_source_objects` in the raw JSON counts the extraction bounding box; the table below uses **eligible candidate destinations** within the actual routing polygon and connector limit.
- The external run at `C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/2026-09-23-lower-basin-context-v1/` contains separate context inputs, source-object reviews, metrics and comparisons. `run_manifest.json` lists 48 original output paths, sizes and hashes (SHA-256 `31b240f209db2ceca2ce21deb652c9a833d53bc635e2a7d8cbf9e434e9264941`). The append-only `provenance_addendum.json` binds those comparisons to source timestamps, rights and assumptions (SHA-256 `214d217e2de3338716e492d515700a1098f4eeec0a9b8056920f1f0e12e47407`). No existing immutable output was overwritten.

## Results

Counts below are modelled residents in the fixed AOI, rounded only for this table. `No route` excludes residents without an accepted connector. It is a graph result, not observed isolation. The hospital column counts eligible OSM candidate destinations after the source-object rule, not unique operating hospitals.

| AOI | Radius | Eligible hospital candidates | No accepted connector | Connected, no hospital route | Within 15 min | Within 30 min | Within 60 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bang Ban/Sena | legacy rectangle | 1 | 3,383 | 37,043 | 2,533 | 6,351 | 9,636 |
| Bang Ban/Sena | 5 km | 3 | 3,292 | 37,135 | 2,533 | 6,351 | 9,636 |
| Bang Ban/Sena | 10 km | 10 | 3,292 | 37,135 | 2,533 | 6,351 | 9,636 |
| Bang Ban/Sena | 15 km | 17 | 3,292 | 37,135 | 2,533 | 6,351 | 9,636 |
| Rangsit | legacy rectangle | 8 | 2,783 | 340,173 | 55,588 | 108,758 | 159,488 |
| Rangsit | 5 km | 17 | 2,702 | 320,906 | 58,024 | 115,238 | 171,114 |
| Rangsit | 10 km | 25 | 2,702 | 290,214 | 58,024 | 115,238 | 171,114 |
| Rangsit | 15 km | 42 | 2,702 | 290,214 | 58,024 | 115,238 | 171,114 |

The denominators stay at 50,467.255 modelled residents for Bang Ban/Sena and 564,292.557 for Rangsit. Bang Ban/Sena's 30-minute and total no-destination population is stable from 5 to 15 km. The apparent 91-person rise in its **connected** no-route count at 5 km is matched by 91 fewer people without a connector, so it is a coverage-category change, not newly lost access. Rangsit's 30-minute reach rises by about 6,480 residents at 5 km and then plateaus through 15 km; its connected no-route count falls by about 49,959 from the legacy rectangle to 10 km and then plateaus. The further 5-to-10 km change creates routes longer than 30 minutes for some demand. Stability across these tested radii is a bounded sensitivity result, not proof that the network or facility inventory is complete.

The Rangsit 10/15 km review excludes OSM node `1402895609` from candidate counting because it is contained in same-named OSM way `1436320285`; both IDs and source URLs are in each `hospital_duplicate_review.json`. No other point/site pair met that evidence rule. Other nearby objects remain separate **unreviewed** source candidates; names, roles, entrances and operating status still require independent review. The historical 10 km inventory counted 10 Bang Ban/Sena and 26 Rangsit hospital-tagged objects by source-geometry distance. This run's eligible destination counts use representative points, routing containment and the 100 m connector rule, so the Rangsit counts need not equal that inventory.

The comparison files are `aoi-05_chao_phraya_bang_ban_sena/comparison.json` (SHA-256 `7c57967820347e7059fc0ba7e9bbd2cbaa9de1a32b8f7ed146d9d2448af0f2da`) and `aoi-06_chao_phraya_rangsit/comparison.json` (SHA-256 `bb3fc93ebff95eb96e8484684d411e4c6486592ffdb227964063b1fb8a5d947b`). Their internal comparison identities are `8728e79f5dc353f41f83190c3642fd7a43bea74a6476c9e9f13f62cf7aabc22e` and `38703961be6c389367290f3067a1ea8506c6a9e655621d85cfcb1ac658ba229f`, respectively. The fixed-demand roster hashes differ by AOI as expected and are recorded in each comparison.

## Verification and next dependencies

`python -m pytest tests/test_lower_basin_context.py tests/test_evidence_context.py tests/test_evidence_case_review.py tests/test_evidence_connectivity.py -q` passed **38 tests**; Python compilation and `git diff --check` passed. The script completed both 0/5/10/15 km walking comparisons and checked the source hashes and exact demand roster before each expanded result. The 2024 and 2025 event selections have **no distinct flood layers**; the same static context applies to both. No accepted FPPS, flood impact, age equity, safe route or operational hospital claim follows from this run.

The release-bound study packages still carry the older rectangular graph. Before replacing them, review the consequential Rangsit disconnected components, road levels and destination roles/entrances; rerun the modelled-vehicle mode separately; bind the chosen radius and checksums into a new case package; and repeat public/export checks. Those dependencies keep M4/M10 product repair **PARTIAL**. A source-backed 10/15 km walking context is now available for that work.

To reproduce into a **new** external output directory, from the verified implementation worktree with the project geo dependencies installed:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
$python = 'C:\Users\iputu\Documents\Flood Guard\.venv\Scripts\python.exe'
$contextRoot = 'C:\Users\iputu\Documents\FloodGuard_external_data'
$baselineRoot = 'C:\Users\iputu\Documents\Project Support\FloodGuard\evidence-demo\2026-09-22-shared-cases'
$reportingUnits = Join-Path $baselineRoot 'event_review\reporting_units.geojson'
$newRun = 'C:\Users\iputu\Documents\Project Support\FloodGuard\research-runs\lower-basin-context-reproduction'
foreach ($aoi in @('aoi-05_chao_phraya_bang_ban_sena', 'aoi-06_chao_phraya_rangsit')) {
  & $python scripts/compare_lower_basin_context.py --context-root $contextRoot --baseline-root $baselineRoot --reporting-units $reportingUnits --output-dir (Join-Path $newRun $aoi) --aoi-id $aoi --radii-km 5 10 15
}
```

The script refuses an existing output directory. On another computer, replace these external roots with their verified local equivalents; no laptop path is embedded in application code.
