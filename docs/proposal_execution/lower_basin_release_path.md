# Lower Chao Phraya context release path

Status: **corrected source-bound AOI-05/06 local finals PASS; combined EvidenceLibrary/public release PARTIAL.** `src/floodguard/lower_basin_release_context.py` chooses a versioned 10 km EPSG:32647 routing buffer for AOI-05 Bang Ban/Sena and AOI-06 Rangsit while retaining the original AOI demand and reporting identities. The corrected `scripts/build_study_area_finals.py` passes `reporting_geometry=None` to the context builder for these two cases so that reporting boundaries do not clip the routing buffer; it then binds and checks the original demand roster and reporting assignments. Its source-bound builder SHA-256 is `c617cf941156024c8ffa068ca37038fbb02c4cb116ee6c8d17fc43ab4e5a1b4d`; a later code change needs a new receipt.

## Implemented boundary and review policy

The **old** released AOI-05/06 packages used the demand rectangle as routing context and passed the reporting-unit union to `build_context_inputs`, which clipped both routing and demand. On the verified shared-case reporting units, that union covers only about **27.45%** of AOI-05's 10 km buffer and **41.89%** of AOI-06's. Keeping that clip with a new buffer would silently cut away most of the expanded graph.

For AOI-05/06, the current builder passes the unchanged AOI as demand geometry and the helper's full buffered routing geometry as routing geometry. It reads the verified old case's walking context and `build_receipt.json` through `--lower-basin-baseline-root`, checks AOI/reporting/source hashes, then uses `bind_fixed_demand_roster` to preserve cell ID, coordinates, modelled resident count and baseline reporting-unit ID. Changed or ambiguous demand fails. The reporting-unit union and crosswalk still define *identity/brief* scope, but do not reduce routing reach or add demand outside the AOI. The builder runs walking and modelled vehicle separately and stores routing selection, fixed-demand roster, baseline context and source-object review hashes in their new contexts/receipt. Passing the buffer without these baseline and review inputs is rejected.

`review_hospital_source_duplicates` reproduces the source-object rule used in the comparison: only an OSM hospital-tagged point contained in a same-name or same-Wikidata polygon/site is a duplicate; multiple possible parents remain ambiguous. `validate_documented_hospital_review` requires the recomputed review to exactly equal the supplied review and OSM SHA before any point is excluded. The verified AOI-06 10 km review excludes `OSM-node-1402895609` as a duplicate of `OSM-way-1436320285` under the same-name/containment rule; the two source URLs are in `hospital_duplicate_review.json`. AOI-05 has no documented exclusion. The builder applies an eligible documented exclusion to the context before access, dependency review and route projections, and rehashes that context. This is map-object deduplication only. It does not verify hospital operation, role, entrance, capacity or event-time availability.

## Verified inputs and commands for a new external run

The source root is `C:/Users/iputu/Documents/FloodGuard_external_data`. `build_context_inputs` reads:

- `open_context/osm_geofabrik/thailand-latest.osm.pbf` — 325,044,304 bytes, recorded SHA-256 `b7f46018249638413b1d318bc86519f140c27af20cac7c00d42fe03775b7add1`.
- `open_context/worldpop_population/tha_ppp_2020.tif` — 296,024,584 bytes, recorded SHA-256 `fb39d85dd150c45c7b25771f29bcd548e611afa0967224ac6d8ca05727230e20`.
- Source permissions and retrieval metadata from the current repository `outputs/open_context_data_file_manifest.csv`; processing checks rehash both source files. OSM has ODbL attribution/share-alike obligations; WorldPop needs citation. The retrieval time is not an event observation time.

The shared baseline root is `C:/Users/iputu/Documents/Project Support/FloodGuard/evidence-demo/2026-09-22-shared-cases`. The exact `--reporting-dir` is its `event_review` directory, containing `reporting_units.geojson` (SHA-256 `013194e107f14258dc51b6bb1bbc3d5df02b7566432b06ea5ee8b827e5ae2a9a`) and `reporting_crosswalk.json`. The **required** `--lower-basin-baseline-root` is its `study_finals` directory, with `<aoi-id>/build_receipt.json` and `<aoi-id>/contexts/walking/context_inputs.json`. The **required** `--lower-basin-review-root` is `C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/2026-09-23-lower-basin-context-v1`, with `<aoi-id>/radius_10km/hospital_duplicate_review.json`. The AOI geometries come from `resources/aoi/upload/`, and the timeline is `resources/finals/chao_phraya_timeline.json`. On another computer, resolve these verified inputs from its configured external roots; these laptop paths are documentation only, not product defaults.

The builder requires both lower-basin inputs. The corrected local finals were written into the immutable external `execution/2026-09-23/proposal-release-staging-v1/study_finals` stage. The AOI-05 `build_receipt.json` SHA-256 is `ce4c781120465bc56057eb6f7e0e64854126fa1c4bf36c3d3dfed35bd728833a`; AOI-06 is `0be8cb624b7fc6d344465f75d88e6f0685edd193a585860ea11268c8308f7b38`. Their listed outputs rehashed **8/8** each, and their fixed cell assignments match the verified baseline **20,677** and **17,083** respectively. Walking and modelled-vehicle context hashes are separate in each receipt. `replication_resources.md` reports measured single-machine time, sampled working set and disk size. For a **new** external output version, after verifying the source and baseline hashes, run from the implementation worktree:

```powershell
$sourceRoot = 'C:/Users/iputu/Documents/FloodGuard_external_data'
$sharedRoot = 'C:/Users/iputu/Documents/Project Support/FloodGuard/evidence-demo/2026-09-22-shared-cases'
$reportDir = Join-Path $sharedRoot 'event_review'
$baselineRoot = Join-Path $sharedRoot 'study_finals'
$reviewRoot = 'C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/2026-09-23-lower-basin-context-v1'
$newRun = 'C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/<new-unique-lower-basin-release>'
$generatedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
foreach ($aoi in @('aoi-05_chao_phraya_bang_ban_sena', 'aoi-06_chao_phraya_rangsit')) {
  uv run --extra geo python scripts/build_study_area_finals.py --context-root $sourceRoot --reporting-dir $reportDir --lower-basin-baseline-root $baselineRoot --lower-basin-review-root $reviewRoot --output-dir (Join-Path $newRun $aoi) --timeline resources/finals/chao_phraya_timeline.json --aoi-id $aoi --generated-at $generatedAt
}
```

The example placeholders are intentionally not the completed destination or time. Do not overwrite the 2026-09-22 shared-case package, September 23 comparison or corrected stage. On another machine, resolve these external roots to verified equivalents and recheck hashes/rights. The completed local finals still need consequential road/destination review, public-export rights/allowlist checks and offline/Preview alignment. For the integrated stage-copy and catalog commands, use `REPRODUCE.md`.

## Migration risks and claims

- The bounded 10–15 km **walking** comparison stabilized selected 30-minute and no-route metrics. The corrected finals now compute and hash separate modelled-vehicle context as well. Neither plateau nor local build proves complete topology, surveyed connectors or verified facilities.
- The old public/study packages are bound to the older rectangular graph. Reusing their case hash, brief, downloads or offline asset with the new context would mix versions; regenerate them together after the new receipts pass.
- The 2024 and 2025 lower-basin selections still share static access context and have no distinct accepted event flood layers. The new context does not create a year-on-year flood comparison, observed road closure or accepted FPPS.
- Source-object dedup may change candidate destination counts but must not be described as a count of unique operating hospitals. Unknown capacity remains unknown.

Verification for the helper: `uv run --extra geo pytest -q tests/test_lower_basin_release_context.py` and `uvx ruff check src/floodguard/lower_basin_release_context.py tests/test_lower_basin_release_context.py`. A read-only check against the existing AOI-06 10 km context exactly reproduced its documented duplicate review. The corrected source builder and three finals receipts have been rehashed locally; the combined eight-case EvidenceLibrary catalog, independent staged/public verification, 24-file repository copy, projections and bilingual briefs passed their precommit source-bound checks. Exact-release UI/browser/offline/Preview and consequential human/service reviews remain separate gates.
