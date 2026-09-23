# Reproduce the non-operational candidate release

This is a **command recipe**, checked against the current script `--help` output and `.github/workflows/ci.yml` on 23 September 2026. It is not an assertion that each command below has already run at the final source SHA. `STATUS.md` and `RECEIPTS.jsonl` record completed runs. The staged eight-case EvidenceLibrary, independent v4 export verifier, 24-file repository copy and eight projection/brief pairs have completed; exact-source profile/browser/CI, offline ZIP, Preview URL and deployed commit/tree remain **pending** until the final release receipt is written. Use a new output root for a replay; do not overwrite a prior immutable research run or the ordinary protected checkout.

All output remains non-operational, with `official_warning=false`. The Mae Sai Gamma0 Otsu experiment abstained; this release uses separately labelled candidate amplitude/scenario evidence, not a qualified flood observation. Modelled ages, assumed closures and candidate Class E are not accepted event equity or FPPS.

## 1. Resolve roots and inspect source

Run in the **registered Codex-managed worktree**, after reading the handoff `WORK_SPECIFICATION.md`, current `AGENTS.md`, source/rights register and `REGISTER_FINALIZATION.md`. Set these variables to the equivalent verified roots on this computer. The external stage-copy receipt and every large/raw source file must exist; do not substitute a different file or treat an absent file as zero.

```powershell
$repo = (git rev-parse --show-toplevel).Trim()
$branch = (git branch --show-current).Trim()
git worktree list --porcelain
git remote -v
git status --short
if ($branch -ne 'codex/open-data-evidence-demo') { throw 'Inspect the current registered implementation branch before replay.' }

$required = @(
  'FLOODGUARD_BUNDLE_ROOT',               # source bundle used by the EvidenceLibrary adapters
  'FLOODGUARD_REPORTS_ROOT',              # dataset_file_locations.csv and expanded_data_inventory.csv
  'FLOODGUARD_CONTEXT_ROOT',              # verified OSM/WorldPop/HDX open-context collection
  'FLOODGUARD_BOUNDARY_ARCHIVE',          # exact reviewed Thai COD-AB ZIP
  'FLOODGUARD_PUBLIC_INVENTORY_ROOT',     # 363-file public inventory root with FILES_SHA256.csv
  'FLOODGUARD_PRIOR_CASE_RUN',            # audited 2026-09-22 shared-case external run
  'FLOODGUARD_LOWER_REVIEW_ROOT',         # immutable 0/5/10/15 km comparison root
  'FLOODGUARD_STAGE_COPY_RECEIPT',        # 226-file copy manifest for the prior run
  'FLOODGUARD_AGE_2024_DIR',              # exact 2024 1 km acquisition directory, or new output directory
  'FLOODGUARD_AGE_2025_DIR',              # exact 2025 1 km acquisition directory, or new output directory
  'FLOODGUARD_MAE_SAI_FINALS_ROOT',       # existing 2026-09-21 Mae Sai finals directory
  'FLOODGUARD_MAE_SAI_REPORTING_UNITS',   # units from that exact Mae Sai finals run
  'FLOODGUARD_RELEASE_RUN_ROOT'           # NEW external output root for this replay
)
foreach ($name in $required) {
  if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Set $name to a verified local path." }
}
$bundleRoot = $env:FLOODGUARD_BUNDLE_ROOT
$reportsRoot = $env:FLOODGUARD_REPORTS_ROOT
$contextRoot = $env:FLOODGUARD_CONTEXT_ROOT
$boundaryArchive = $env:FLOODGUARD_BOUNDARY_ARCHIVE
$inventoryRoot = $env:FLOODGUARD_PUBLIC_INVENTORY_ROOT
$priorRun = $env:FLOODGUARD_PRIOR_CASE_RUN
$lowerReviewRoot = $env:FLOODGUARD_LOWER_REVIEW_ROOT
$stageCopyReceipt = $env:FLOODGUARD_STAGE_COPY_RECEIPT
$age2024Dir = $env:FLOODGUARD_AGE_2024_DIR
$age2025Dir = $env:FLOODGUARD_AGE_2025_DIR
$maeSaiFinals = $env:FLOODGUARD_MAE_SAI_FINALS_ROOT
$maeSaiUnits = $env:FLOODGUARD_MAE_SAI_REPORTING_UNITS
$releaseRoot = $env:FLOODGUARD_RELEASE_RUN_ROOT
$stageRoot = Join-Path $releaseRoot 'evidence-stage'
$stagePublic = Join-Path $releaseRoot 'public-evidence-library'
$generatedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
if (Test-Path -LiteralPath $releaseRoot) { throw 'Choose a new external release run root.' }
if ([Environment]::GetEnvironmentVariable('NEXT_PUBLIC_FLOODGUARD_API_URL')) { throw 'Keep the hosted API URL unset for the finals Preview.' }
New-Item -ItemType Directory -Path $releaseRoot | Out-Null
```

`$generatedAt` is package metadata, not an observation timestamp. Reusing the same input bytes with a different generation value may produce a different output hash; bind the actual value in the run receipt. `FLOODGUARD_*` roots above are shell inputs for this recipe, not new product-code defaults or credentials.

## 2. Reopen public sources and age bands

The previously verified inventory manifest SHA-256 is `bc322bf3b6cbd92f9f92e56d68f0197db616ae4be362f733915c493d8ba01779` (363 files, 616,159,975 bytes). A fresh receipt must go into the new external release root.

```powershell
$inventoryManifest = Join-Path $inventoryRoot 'FILES_SHA256.csv'
if ((Get-FileHash -LiteralPath $inventoryManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'bc322bf3b6cbd92f9f92e56d68f0197db616ae4be362f733915c493d8ba01779') { throw 'Public source inventory identity changed.' }
uv run python scripts/verify_public_source_inventory.py --root $inventoryRoot --manifest $inventoryManifest --receipt (Join-Path $releaseRoot 'public-source-inventory.json')
if ($LASTEXITCODE -ne 0) { throw 'Public source bytes failed verification.' }
```

`acquire_worldpop_age.py` accepts `--resolution 1km`; this selects the official `1km_ua` Thailand files. The current exact-year 20-band manifests are `f7a169877177a374bc461724dcb93b6ec96d76451347cd2e98dc2fc7b0f8356c` for 2024 and `b114341a95a7fa6dba153fb2edaa41536c2a44576c19ff86d6ea0285b02bb633` for 2025. For an **exact-source replay**, copy those complete acquisition directories and reverify both manifest and 20 TIFF hashes. A fresh public download has new retrieval timestamps and may have a different manifest hash even if TIFF bytes match. The acquisition commands below prepare a **new** source run; a manifest mismatch stops exact-release reproduction and requires a new, separately identified release decision. To acquire a missing year, point its `$ageYearDir` at a *new* external directory; use `--resume-incomplete --workers 1` only after a documented partial attempt, retaining its attempt manifest.

```powershell
if (-not (Test-Path -LiteralPath (Join-Path $age2024Dir 'acquisition_manifest.json'))) {
  uv run python scripts/acquire_worldpop_age.py --year 2024 --resolution 1km --workers 2 --output $age2024Dir
  if ($LASTEXITCODE -ne 0) { throw '2024 age acquisition incomplete; inspect the partial receipt before resuming.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $age2025Dir 'acquisition_manifest.json'))) {
  uv run python scripts/acquire_worldpop_age.py --year 2025 --resolution 1km --workers 2 --output $age2025Dir
  if ($LASTEXITCODE -ne 0) { throw '2025 age acquisition incomplete; inspect the partial receipt before resuming.' }
}
$age2024Manifest = Join-Path $age2024Dir 'acquisition_manifest.json'
$age2025Manifest = Join-Path $age2025Dir 'acquisition_manifest.json'
if ((Get-FileHash -LiteralPath $age2024Manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f7a169877177a374bc461724dcb93b6ec96d76451347cd2e98dc2fc7b0f8356c') { throw '2024 age source differs from this candidate release.' }
if ((Get-FileHash -LiteralPath $age2025Manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b114341a95a7fa6dba153fb2edaa41536c2a44576c19ff86d6ea0285b02bb633') { throw '2025 age source differs from this candidate release.' }

$maeSaiAgeReview = Join-Path $releaseRoot 'age-review-mae-sai-2024'
$hatYaiAgeReview = Join-Path $releaseRoot 'age-review-hat-yai-2025'
uv run --extra geo python scripts/build_worldpop_age_review.py --acquisition-manifest $age2024Manifest --units outputs/mae_sai_admin_context.geojson --aoi resources/aoi/aoi-01_mae_sai_core.geojson --output $maeSaiAgeReview
if ($LASTEXITCODE -ne 0) { throw 'Mae Sai age review failed.' }
uv run --extra geo python scripts/build_worldpop_age_review.py --acquisition-manifest $age2025Manifest --units (Join-Path $priorRun 'event_review/reporting_units.geojson') --unit-id-field adm3_pcode --aoi resources/aoi/aoi-03_hat_yai_core.geojson --output $hatYaiAgeReview
if ($LASTEXITCODE -ne 0) { throw 'Hat Yai age review failed.' }

$maeSaiAgeBridge = Join-Path $releaseRoot 'mae-sai-age-access-sensitivity'
uv run --extra geo python scripts/bridge_worldpop_age_access.py --acquisition-manifest $age2024Manifest --age-review (Join-Path $maeSaiAgeReview 'age_review.json') --age-review-units outputs/mae_sai_admin_context.geojson --aoi resources/aoi/aoi-01_mae_sai_core.geojson --reporting-units $maeSaiUnits --finals-dir $maeSaiFinals --output-dir $maeSaiAgeBridge
if ($LASTEXITCODE -ne 0) { throw 'Age/access sensitivity failed.' }
```

Both reviews write `age_review.json` and `receipt.json` *inside* the `--output` directory. The bridge writes `age_access_sensitivity.json`, a source-cell ledger and its own receipt. These detailed results remain external pending product-specific public derivative rights. Children are ages **0–14 inclusive**; older adults are 60+. The bridge combines 2024 modelled age cells with fixed 2020 demand nodes and modern routes, so it is a mixed-vintage hypothetical sensitivity, not accepted event equity.

Age review and bridge JSON include new generation timestamps, so their complete-file SHA-256 values can change on a faithful replay. Compare verified source-cell/geometry inputs and scientific values under the same code/tree; record new output hashes and timestamps rather than overwriting the original receipts. A fresh source manifest is a new lineage, even when its raster bytes happen to match.

## 3. Stage audited inputs, then build Hat Yai and lower-basin finals

The existing stage-copy receipt SHA-256 is `a59d5d0f14a3e67d54dfa9b370d3fec02dd3ca76a6561a34846017b36b5c9e2b`. It lists **226** source/review/normalized files, totalling **792,099,296** bytes. It includes the old Mae Sai finals and Hat Yai candidate but intentionally **excludes the old study finals**. Rebind its relative paths to the verified local `$priorRun`; do not reuse its laptop-specific `source_root` or `target_root` strings as new roots.

```powershell
if ((Get-FileHash -LiteralPath $stageCopyReceipt -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a59d5d0f14a3e67d54dfa9b370d3fec02dd3ca76a6561a34846017b36b5c9e2b') { throw 'Stage-copy manifest identity changed.' }
$copyPlan = Get-Content -LiteralPath $stageCopyReceipt -Raw | ConvertFrom-Json
if ($copyPlan.verified_files -ne 226 -or $copyPlan.verified_bytes -ne 792099296) { throw 'Stage-copy inventory differs.' }
if (Test-Path -LiteralPath $stageRoot) { throw 'Use a fresh stage root.' }
New-Item -ItemType Directory -Path $stageRoot | Out-Null
foreach ($entry in $copyPlan.files) {
  $relative = [string]$entry.relative_path
  if ($relative -match '(^[/\\]|^[A-Za-z]:|(^|[/\\])\.\.([/\\]|$))') { throw "Unsafe staged relative path: $relative" }
  $source = Join-Path $priorRun $relative
  $target = Join-Path $stageRoot $relative
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing staged source: $relative" }
  if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Changed staged source: $relative" }
  New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
  Copy-Item -LiteralPath $source -Destination $target
  if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Stage copy failed: $relative" }
}
```

The corrected case builder verifies the old fixed-demand roster and documented 10 km OSM hospital-object review. It uses a 10 km EPSG:32647 routing buffer for AOI-05/06, keeps original AOI demand and reporting assignments, and runs walking and modelled vehicle separately. The required baseline root is `$priorRun/study_finals`; the required review root contains `<aoi-id>/radius_10km/hospital_duplicate_review.json`. A point/site duplicate exclusion is a map-object decision, not verified hospital operation or entrance. The Hat Yai case retains its own November candidate, destination review and timeline.

```powershell
$reportingDir = Join-Path $stageRoot 'event_review'
$oldStudyFinals = Join-Path $priorRun 'study_finals'
$hatYaiCandidate = Join-Path $stageRoot 'flood_candidates/aoi-03_hat_yai_core'
uv run --extra geo python scripts/build_study_area_finals.py --context-root $contextRoot --reporting-dir $reportingDir --output-dir (Join-Path $stageRoot 'study_finals/aoi-03_hat_yai_core') --timeline resources/finals/hat_yai_timeline.json --aoi-id aoi-03_hat_yai_core --destination-review resources/finals/hat_yai_destinations.json --flood-candidate $hatYaiCandidate --generated-at $generatedAt
if ($LASTEXITCODE -ne 0) { throw 'Hat Yai finals failed.' }
foreach ($aoi in @('aoi-05_chao_phraya_bang_ban_sena','aoi-06_chao_phraya_rangsit')) {
  uv run --extra geo python scripts/build_study_area_finals.py --context-root $contextRoot --reporting-dir $reportingDir --output-dir (Join-Path $stageRoot "study_finals/$aoi") --timeline resources/finals/chao_phraya_timeline.json --aoi-id $aoi --lower-basin-baseline-root $oldStudyFinals --lower-basin-review-root $lowerReviewRoot --generated-at $generatedAt
  if ($LASTEXITCODE -ne 0) { throw "Lower-basin finals failed: $aoi" }
}
```

Record each new `build_receipt.json`, `routing_selection.json`, `hospital_duplicate_review.json`, analysis and two context hashes. The old AOI-05/06 packages cannot be relabelled as corrected. Distinct 2024/2025 lower-basin event extents and observed passability remain absent.

## 4. Rebuild and verify a staged EvidenceLibrary

The stage output is new and external. Use the `geo` extra for this rebuild to match the normalized context runtime; the later all-extras sync belongs to the full CI check, not this source-bound replay. Do not pass `--check-public-routes` during an exact-byte replay: it makes new mutable network acquisitions. `--reuse-normalized` is guarded by source, adapter/runtime and saved output hashes; it is not permission to reuse changed files. `--require-lower-basin-context` fails if either new 10 km case is absent or has the wrong policy.

```powershell
if (Test-Path -LiteralPath $stagePublic) { throw 'Use a new empty public staging directory.' }
uv run --extra geo python scripts/build_evidence_library.py --bundle-root $bundleRoot --locations-csv (Join-Path $reportsRoot 'dataset_file_locations.csv') --inventory-csv (Join-Path $reportsRoot 'expanded_data_inventory.csv') --output-dir $stageRoot --public-dir $stagePublic --context-root $contextRoot --boundary-archive $boundaryArchive --generated-at $generatedAt --reuse-normalized --require-lower-basin-context
if ($LASTEXITCODE -ne 0) { throw 'Staged EvidenceLibrary build failed.' }
uv run --extra geo python scripts/verify_evidence_library.py --public-dir $stagePublic --local-dir $stageRoot --output-receipt (Join-Path $releaseRoot 'staged-export-verification.json')
if ($LASTEXITCODE -ne 0) { throw 'Staged public export failed verification.' }
```

**Publication into the repository completed for the current source-bound candidate stage** with external copy receipt SHA-256 `1ad017bb49b8707049c8befce8698713deec28efedf81271e01f69d12463c2e7`, after independent v4 verifier receipt SHA-256 `5c3ec28328ecdc77173b8212e596ad78382fbc196c79f1afa6172e78e9a9221e` passed. The command below is the gated replay step, **not the original execution log**. It compares the exact relative-file set in `$stageRoot/public_export_report.json` with both `$stagePublic` and `apps/web/public/evidence-library`, then copies only hashed allowlisted files. Stop if the sets differ; review source rights and the discrepancy before any copy. It does not delete anything. Record each replay's actual command, file count and before/after hashes in its new receipt.

```powershell
$publicEvidence = Join-Path $repo 'apps/web/public/evidence-library'
$export = Get-Content -LiteralPath (Join-Path $stageRoot 'public_export_report.json') -Raw | ConvertFrom-Json
$expected = @($export.files.PSObject.Properties.Name | Sort-Object)
$stageFiles = @(Get-ChildItem -LiteralPath $stagePublic -Recurse -File | ForEach-Object { [IO.Path]::GetRelativePath($stagePublic,$_.FullName).Replace('\','/') } | Sort-Object)
$currentFiles = @(Get-ChildItem -LiteralPath $publicEvidence -Recurse -File | ForEach-Object { [IO.Path]::GetRelativePath($publicEvidence,$_.FullName).Replace('\','/') } | Sort-Object)
if (Compare-Object $expected $stageFiles) { throw 'Staged export inventory differs from its allowlist.' }
if (Compare-Object $expected $currentFiles) { throw 'Current public inventory differs; review before publication.' }
foreach ($relative in $expected) {
  $source = Join-Path $stagePublic $relative
  $target = Join-Path $publicEvidence $relative
  $pinned = [string]$export.files.PSObject.Properties[$relative].Value
  if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pinned) { throw "Staged export hash mismatch: $relative" }
  Copy-Item -LiteralPath $source -Destination $target -Force
  if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pinned) { throw "Published export hash mismatch: $relative" }
}
```

Do not copy local `packages/`, review/source rasters, detailed age outputs, `.env`, `.vercel` or external stage receipts into public assets. If the staged file set has changed, make a separate reviewed migration plan instead of silently deleting the old export.

## 5. Regenerate projections and bilingual briefs from the published catalog

Only after the repository public EvidenceLibrary passes verification, derive the new catalog SHA from its **actual bytes**. The candidate exporter rejects accepted-looking score/action fields and checks source package hashes and rights. Its eight case files must match the new catalog; inspect and reject stale extra files before the release build. The brief generator writes eight Thai/English HTML/PDF pairs and a catalog bound to the projection SHA.

```powershell
$publicEvidence = Join-Path $repo 'apps/web/public/evidence-library'
uv run --extra geo python scripts/verify_evidence_library.py --public-dir $publicEvidence --local-dir $stageRoot --output-receipt (Join-Path $releaseRoot 'committed-export-verification.json')
if ($LASTEXITCODE -ne 0) { throw 'Repository public evidence differs from the verified stage.' }
$evidenceCatalogSha = (Get-FileHash -LiteralPath (Join-Path $publicEvidence 'catalog.json') -Algorithm SHA256).Hash.ToLowerInvariant()
uv run --locked python scripts/build_public_case_projections.py --public-dir apps/web/public --output-dir apps/web/public/public-case-projections --catalog-sha256 $evidenceCatalogSha
if ($LASTEXITCODE -ne 0) { throw 'Public case projection failed.' }
$projectionSha = (Get-FileHash -LiteralPath 'apps/web/public/public-case-projections/catalog.json' -Algorithm SHA256).Hash.ToLowerInvariant()
Push-Location apps/web
try {
  node scripts/build-case-briefs.mjs --public-dir public --output-dir public/briefs --catalog-sha256 $projectionSha
  if ($LASTEXITCODE -ne 0) { throw 'Bilingual brief generation failed.' }
} finally { Pop-Location }
```

Update `CLAIMS.md`, the ten-minute pitch and every downloadable headline from these **new** hashes and packages. The research age bridge is deliberately excluded from hosted/downloadable outputs pending product-specific derivative review.

## 6. Exact-source tests, competition build, offline bundle and Preview

First review and commit the approved code, generated EvidenceLibrary, projections, briefs and docs to the non-main branch. Record `git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'`, and confirm no tracked change remains. The current CI workflow uses the gates below. Run them **at that exact commit**; if a fix changes the tree, create a new commit and rerun the affected gates. The dependency-audit CI job is advisory; inspect its actual receipts rather than treating a green workflow as zero advisories.

```powershell
uv sync --locked --all-extras
uv run pytest --junitxml=.tmp/proposal-evidence/root.xml
uv run python scripts/verify_evidence_library.py --public-dir apps/web/public/evidence-library --output-receipt (Join-Path $releaseRoot 'exact-source-export-verification.json')
pnpm install --frozen-lockfile
pnpm --filter @floodguard/web exec playwright install chromium
pnpm verify:frontend
uv sync --project services/api --locked --group dev
uv run --project services/api ruff check services/api/src services/api/tests
uv run --project services/api pytest services/api/tests --junitxml=.tmp/proposal-evidence/api.xml
uv sync --project services/geoai-runner --locked --group test
uv run --project services/geoai-runner ruff check services/geoai-runner/geoai_runner services/geoai-runner/tests
uv run --project services/geoai-runner pytest services/geoai-runner/tests -m 'not geoai_smoke' --junitxml=.tmp/proposal-evidence/geoai-normal.xml
uv sync --project services/geoai-runner --extra geoai --extra realpipeline --extra sam --dry-run
uv pip compile services/geoai-runner/requirements-research.txt --python-version 3.12 --quiet --output-file (Join-Path $releaseRoot 'research-resolution.txt')
```

The Linux CI job wraps `pnpm verify:frontend` with `scripts/run_check_with_junit.py` to save `.tmp/proposal-evidence/frontend.xml`. On this Windows host `pnpm` resolves to `pnpm.cmd`; call it directly from PowerShell and retain the terminal result instead of assuming the Linux wrapper's executable lookup behaves identically.

The bounded case browser check can also be replayed separately from the `apps/web` directory. The first command covers offline case/brief selection and representative routes; the second covers the full bounded online/offline matrix. The 23 September precommit external QA receipt for these commands is `qa/browser-evidence-qa-precommit-v1.json` (SHA-256 `d2db2db770668c44617e6d806e1f0f5a76c34c1b7ccdbc8ef7380b4fbf216beb`). It is not an exact-commit receipt.

```powershell
Push-Location apps/web
try {
  node scripts/browser-evidence-library-smoke.mjs --offline-only
  node scripts/browser-evidence-library-smoke.mjs
} finally {
  Pop-Location
}
```

Build the **competition** profile again after `pnpm verify:frontend`, because profile verification also builds public-production and may leave `apps/web/out` in that profile. The API URL must remain unset. Check Thai/English, desktop/mobile/keyboard, deep links, restricted export boundaries and offline behavior against the same case identity.

```powershell
$releaseSha = (git rev-parse HEAD).Trim()
$releaseTree = (git rev-parse 'HEAD^{tree}').Trim()
git status --porcelain=v1
if ([Environment]::GetEnvironmentVariable('NEXT_PUBLIC_FLOODGUARD_API_URL')) { throw 'Hosted API URL must remain unset.' }
pnpm --filter @floodguard/web build:competition
if ($LASTEXITCODE -ne 0) { throw 'Competition build failed.' }
pnpm --filter @floodguard/web test:profile
if ($LASTEXITCODE -ne 0) { throw 'Competition artifact profile smoke failed.' }
$offlineZip = Join-Path $releaseRoot 'FloodGuard_Candidate_Finals_Offline.zip'
uv run python scripts/build_offline_demo_bundle.py --site-root apps/web/out --template-root packaging/offline-demo --output $offlineZip --generated-at $generatedAt --git-commit $releaseSha --finals
if ($LASTEXITCODE -ne 0) { throw 'Offline finals bundle failed.' }
$offlineSha = (Get-FileHash -LiteralPath $offlineZip -Algorithm SHA256).Hash.ToLowerInvariant()
```

Extract the ZIP into a **new** external directory, run its `FloodGuard_Offline_Demo/serve-demo.py` local server, and open the printed localhost route. The server validates every manifest file hash before serving. Record the ZIP/manifest hashes and local route results. A browser context on this laptop does **not** count as the requested second-machine rehearsal; leave that check NOT RUN until a real second device/person tests it.

The current candidate EvidenceLibrary catalog SHA-256 is `3123d15ba78c1390647b0e27a8bbe75620d49efcdf148108b011929fc7120a7d`, projection catalog SHA-256 `041562b2870f2c970d9d2b0a9f34f5207ca3a05d7fe3149e5a027c7a3ce49771`, and **precommit source-bound** bilingual brief catalog SHA-256 `f8df20dba1b40624829f55939389650694d1109f1ba62dccedb17359e5e262b5`. The earlier brief SHA-256 `574ac0ccce2a67476b44ba279e81cb6b00375a9e402591f5a9af8b011ccbb9db` is a historical pre-copy-correction receipt, not the current manifest. After the TSX claim-copy corrections and current profile builds, an independent rehash confirmed those three catalog hashes and all 16 HTML/PDF files against the brief manifest. These are source-bound worktree outputs, **not** final exact-commit deployment evidence. The final commit/tree, offline ZIP hash and READY anonymous Vercel Preview URL remain pending. The branch may be pushed and a competition Preview published under the user's authorization, but do not merge, change production settings/branch, promote the deployment, contact agencies or send files to organizers. After the Preview is READY, verify its deployed source SHA and anonymous URL, then append an external release receipt and update the R/AC registers according to `REGISTER_FINALIZATION.md`. No accepted observation, FPPS, A–E action class, learned-model result or operational warning follows from a software release.
