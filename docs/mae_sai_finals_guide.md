# Mae Sai finals demonstration and claim register

This is the active presentation guide for the evidence demonstration, not a
certification that the project meets the organizer's requirements. Use the release
handoff's Git SHA, package hashes and preview URL. Do not copy numbers from an
older screenshot or from the research archive into the current brief.

## The decision story

> FloodGuard compares local access interventions under a stated flood observation
> or scenario, explains who the model covers, and exposes the evidence that could
> change the recommendation.

The primary view is `/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024`.
The evidence library supports inspection; the older Command and GeoAI outputs
are research comparisons. Accepted event FPPS, action class and affected
population remain unavailable when their required evidence is unavailable.

The default presentation question is access to a named service for the
Thailand-side Mae Sai population in the selected AOI. Walking and modelled
vehicle assumptions must be named. A historical September 2024 event context
combined with 2020 population, 2022 boundaries and later OSM acquisition is a
mixed-vintage scenario, not a complete historical reconstruction.

The brief uses a compact route workspace. Select the study area/event, service,
travel mode, public starting place and imposed change above the map. **Both /
Before / After** switches the displayed paths; the two result cards retain the
comparison. Supporting detail opens without changing those selections:

- **Route details:** starting-place source, pin and entrance limitations,
  selection rationale, route-time breakdown, changed IDs and ordered road edges.
- **Population:** service-wide baseline coverage and subdistrict verification
  briefs. These counts are distinct from the selected pin's journey.
- **Interventions:** service-wide experiments and speed sensitivity, kept
  separate from the prepared route example.
- **Evidence:** input years, flood timeline, destination/topology reviews,
  capacity assumptions and accepted-claim limitations.
- **Sources and downloads:** package identity, source timestamps, assumptions,
  input hashes and downloadable reports.

The Population, Interventions and Evidence sections share a detail panel. Use its
tabs to switch sections and **Close** or **Escape** to return to the map. Long
content scrolls inside the panel; small or zoomed viewports may reflow to keep
controls and text accessible. The full evidence library remains available from
the navigation and Evidence panel.

## Prepared public-place case

Start at **Mae Sai Municipal Office**, using its official public site marker at
**20.4265478° N, 99.8843238° E**. The municipality's
[official website](https://www.maesai.go.th/?page=home) links the location. This
is a familiar civic starting place with public source evidence, chosen to make
the route comparison understandable. It is not a verified entrance, private
resident location or an independently sampled evaluation point.

Choose **Hospital care → Walking model → Close a baseline route link**. The
prepared calculation reaches the candidate **Mae Sai Hospital** in **11.2872
minutes** before the imposed change and **12.8422 minutes** afterwards: a
**1.555-minute modelled increase**. The interface rounds these to readable values.
The closure targets the longest edge of this origin's baseline path, with a
stable ID tie-break; that rule is applied before calculating the closure effect.
The case was not selected to claim a dramatic delay or an optimal intervention.

The hospital destination comes from its OSM site polygon, represented by a site
point/centroid. Neither that point nor the origin marker establishes a usable
entrance, safe connector, event-time operation or present passability. The
[hospital's official site](https://www.maesaihospital.com/maesai/?stat=history)
supports public identity/location review. Its official marker is a second
prepared starting-place option; it is distinct from the OSM routing site point.

The map's green baseline and purple after-change path use the same source
snapshot, service definition and travel assumptions. **Before/after means a
controlled scenario, not actual historical routes before and after the flood.**
Orange identifies the imposed road-link closure; dotted segments are assumed
connectors. Path distance and time are model outputs, not travel instructions.

Interpret the controls and outcomes as follows:

- Changing the service changes the eligible destination set. Clinics and
  pharmacies do not satisfy hospital access, and none becomes a shelter by
  substitution.
- Removing the baseline hospital can produce **no modelled route** because the
  reviewed Thai-side set has only one eligible hospital. This does not establish
  that no other hospital exists or that residents were actually isolated.
- An unavailable shelter comparison means the package has no eligible shelter
  destination. It does not mean zero real shelter capacity.
- A zero time difference remains a valid model outcome; it is not evidence that
  an actual closure would be harmless.
- A missing route has null time and null time difference, never zero. The
  explanatory text distinguishes an invalid connector, an absent eligible
  service and a graph-connected origin with no route.
- Walking and vehicle results answer different conditional questions. The
  route case uses the unscaled baseline speed assumptions; the service-wide
  sensitivity tables in **Interventions** test 0.75×, 1× and 1.25× network
  speeds separately.

Keep the service-wide closure shortlist separate from the public-origin route
example. At the 1× walking assumption, its two hospital closure candidates are
segments 0 and 1 of **OSM way 934550386**, near the single hospital site's assumed
connection. Each produces approximately **15,453 modelled residents losing
30-minute access**. That large effect can be dominated by one unverified hospital
entrance/connection. Present it as a **connection-review priority**, not observed
isolation or validated impact. Verify the real entrances and their road links
before using that magnitude to recommend a road intervention.

Use the current package and release receipt when presenting these quantities.
If reviewed inputs change, rebuild a new package and update this worked example
only after checking the new results; do not mix old times with new paths.

## Reproduce the prepared calculation and public package

Run from the verified non-main checkout with the locked Python environment and
GDAL/OGR context extraction available. Set the four external-root environment
variables below to the acquired bundle, recorded inventory directory, existing
OSM/WorldPop context and prepared local evidence output, respectively. No personal
filesystem path is embedded in the commands.

The evidence output must be outside Git, disjoint from immutable raw inputs, and
contain the reviewed `event_review/`, `review/`, `public_review/`, `acquisition/`
and facility-review records supplied with this release. In particular, preserve
the reporting-unit geometries/crosswalk, junction review and public-origin
receipts. These source/review decisions are inputs, not facts that the scripts
can recreate from an empty directory. Use a separate versioned output for a new
review; preserve the released output and raw assets.

```powershell
$ErrorActionPreference = 'Stop'
$repository = (Get-Location).Path
$bundleRoot = $env:FLOODGUARD_BUNDLE_ROOT
$inventoryRoot = $env:FLOODGUARD_INVENTORY_ROOT
$contextRoot = $env:FLOODGUARD_CONTEXT_ROOT
$outputRoot = $env:FLOODGUARD_EVIDENCE_OUTPUT
foreach ($externalRoot in @($bundleRoot, $inventoryRoot, $contextRoot, $outputRoot)) {
    if ([string]::IsNullOrWhiteSpace($externalRoot) -or
        -not (Test-Path -LiteralPath $externalRoot -PathType Container)) {
        throw 'Set each external-root variable to its existing release input directory.'
    }
}
$contextData = $contextRoot
if (Test-Path -LiteralPath (Join-Path $contextRoot 'open_context') -PathType Container) {
    $contextData = Join-Path $contextRoot 'open_context'
}
$publicDirectory = Join-Path $repository 'apps/web/public/evidence-library'
$reportingDirectory = Join-Path $outputRoot 'event_review'
$junctionReview = Join-Path $outputRoot 'review/osm_junction_review.json'
$publicOrigins = Join-Path $outputRoot 'public_review/public_origins.json'
$boundaryArchive = Join-Path $contextData 'hdx_cod_ab/tha_admin_boundaries.gdb.zip'
$generatedAt = '2026-09-21T13:44:35Z'

uv sync --locked --all-extras
if ($LASTEXITCODE -ne 0) { throw 'Locked Python setup failed.' }
uv run --locked python scripts/build_mae_sai_finals.py `
    --context-root $contextRoot `
    --reporting-dir $reportingDirectory `
    --output-dir (Join-Path $outputRoot 'finals') `
    --timeline resources/finals/mae_sai_timeline.json `
    --reviewed-junctions $junctionReview `
    --public-origins $publicOrigins `
    --generated-at $generatedAt
if ($LASTEXITCODE -ne 0) { throw 'Finals calculation failed; do not publish.' }

uv run --locked python scripts/build_evidence_library.py `
    --bundle-root $bundleRoot `
    --locations-csv (Join-Path $inventoryRoot 'dataset_file_locations.csv') `
    --inventory-csv (Join-Path $inventoryRoot 'expanded_data_inventory.csv') `
    --context-root $contextRoot `
    --boundary-archive $boundaryArchive `
    --output-dir $outputRoot `
    --public-dir $publicDirectory `
    --generated-at $generatedAt `
    --reuse-normalized
if ($LASTEXITCODE -ne 0) { throw 'Public evidence build failed; do not publish.' }

uv run --locked python scripts/verify_evidence_library.py `
    --public-dir $publicDirectory `
    --local-dir $outputRoot `
    --output-receipt (Join-Path $outputRoot 'qa/rebuilt-export-verification.json')
if ($LASTEXITCODE -ne 0) { throw 'Export verification failed; do not publish.' }
```

The shared generation value is release metadata, not an observation timestamp.
`build_evidence_library.py` discovers the finals receipt at
`$outputRoot/finals/build_receipt.json`; both builds must use the same generation
value, source bytes and reporting boundaries. `--reuse-normalized` permits only
validated normalization reuse; it is not permission to reuse changed source
inputs. Omit it to recompute normalization. Do not add `--check-public-routes`
while reproducing a frozen package: a fresh website review is a new acquisition
version and may change identities.

After export verification, run the frontend checks and the competition build:

```powershell
pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
pnpm verify:frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend verification failed.' }
pnpm build:web
if ($LASTEXITCODE -ne 0) { throw 'Competition build failed.' }
```

`pnpm verify:frontend` exercises both deployment profiles and the browser/offline
checks. The final `pnpm build:web` explicitly restores a competition export for
Preview publication. Keep the hosted API URL unset. These commands do not deploy,
promote production, submit competition files or establish human/field acceptance.

Package that verified competition export with the explicit finals mode:

```powershell
uv run --locked python scripts/build_offline_demo_bundle.py --finals --generated-at $generatedAt
if ($LASTEXITCODE -ne 0) { throw 'Finals offline packaging failed.' }
```

This writes `dist/FloodGuard_Mae_Sai_Finals_Offline_Demo.zip`. Extract the whole ZIP,
run its `serve-demo.ps1` or `python serve-demo.py`, then open
`http://127.0.0.1:8000/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024`.
The launcher verifies the packaged hashes before serving. Record the Git commit,
ZIP hash and extracted-package rehearsal receipt alongside the release receipt.
Without `--finals`, the builder retains the proposal fixture mode and entrypoint.

## Claim register

| Claim | Current permitted wording | Evidence or remaining requirement |
|---|---|---|
| September flooding | A September 15 satellite candidate and September documentary evidence can provide context within their dates and footprints. | Candidate lineage and observation timeline; accepted extent/footprint and independent evaluation remain separate gates. |
| UNOSAT September product | The public publication describes September 13–19 cumulative water; preliminary, not field validated. | [Publication](https://thailand.un.org/en/280291-satellite-detected-water-extents-13-19-september-2024-over-mea-sai-district-chiang-rai); do not imply a downloaded, licensed validation vector from the publication alone. |
| October products | Historical context or an October observation. | Preserve October 12/22 accumulated-date conflict; no per-patch dates means no September extraction. |
| Flood probability / accuracy | A method-dependent candidate signal; no Thailand-side accuracy claim from the cross-border weak reference. | Qualified labels, processing QA and independent evaluation are required for stronger claims. |
| Hospital access | Conditional shortest-path access to the eligible hospital destination set. | Facility identity, geometry role, graph connector, service type, travel mode and temporal availability. Pharmacies cannot satisfy hospital access. |
| Shelter access | Only a supported shelter destination set or an explicitly hypothetical site. | Dated occupancy reports are not capacity; generic OSM shelters may be bus shelters. |
| People | Modelled residential population unless a separately accepted exposure or demand calculation is explicitly identified. | Source year, Thai-side selection, AOI/subdistrict intersection and excluded coverage. |
| Intervention benefit | A comparison with the same baseline, service and travel assumptions. | Exact edge/site IDs, hashes, selection rationale, thresholds, travel-time denominator and sensitivity results. |
| Road closure | An imposed closure experiment unless dated location evidence establishes an observed closure. | Flood intersection, bridge proximity and absence from a bulletin do not prove passability. |
| Capacity | Demand allocation under declared participation and site-capacity assumptions. | Mass conservation, common site identity where linked, unknown capacity distinct from zero. |
| Age equity | Unavailable until compatible group counts or a valid explicit demographic scenario exists. | Reconcile definitions, denominators, source errors, missing 2024 data and administrative units. |
| Accepted score | Unavailable where any required component is missing. | Original weights and low-confidence Class E rule remain intact. Complete hypothetical scores remain scenario results. |
| Archived Ko Chang score/class | Earlier report-only arithmetic, not an accepted action recommendation. | Raw archive asserts `can_feed_decision_layer=false`; retained unchanged for inspection. |
| Hat Yai | A scenario/evidence demonstration exists; independent event validation is a separate question. | Current library and package receipts, not the outdated proposal's "future only" wording. |
| Production readiness | Public static research preview, not an official warning service. | Actual release QA receipt; never turn software test counts into model accuracy or operational acceptance. |

## Three-minute rehearsal

1. **Question and place — 30 seconds.** Open the current Mae Sai brief and the
   prepared public starting pin. Set the service and travel mode using the
   visible controls; the published place identity does not establish a verified
   entrance or safe connection.
2. **Route change — 60 seconds.** Show the baseline route and impose the stated
   road-link closure or destination removal. Switch **Both / Before / After**
   and compare the paths, destinations, times and distances. **Route details**
   explains the inputs and changed IDs. Explain that "before/after" refers to a
   controlled assumption, not measured before/after flood conditions. A zero
   change or missing route remains visible. Disclose this is an explanatory
   selection, not an independently selected performance-evaluation case.
3. **Who else could be affected — 40 seconds.** Open **Population** to show
   residential population, reachable population and unknown coverage separately
   for the same service and mode. State the mixed input vintages and
   AOI/subdistrict intersection. An unresolved graph connection is a verification
   priority, not observed isolation.
4. **What could change the conclusion — 30 seconds.** Switch to **Interventions**
   for speed sensitivity and **Evidence** for the most consequential unresolved
   facility or road-connection fact. Keep actual shelter capacity and evacuation
   demand distinct from scenarios.
5. **Evidence and boundary — 20 seconds.** Show the accepted-claim limitations in
   **Evidence**; **Sources and downloads** provides the package identity and
   reports. Close the panel to return to the same route. State that accepted
   event scoring/accuracy remain pending where qualified evidence is missing.

Use this timing as an internal rehearsal aid only. The official
[GeoHackathon site](https://geohackathon.gistda.or.th/) publishes Final Pitching on
**31 October 2026** at Thailand Space Expo, with Round 2 weights of **40% Geo
Intelligence Quality, 35% GeoAI Methodology, and 25% Communication & Impact**.
The public-site review did not establish pitch/Q&A duration, final upload cutoff
or file-format requirements. Do not reuse the August application deadline as the
final-round deadline. Recheck organizer instructions before submission.

## Questions the presenter should be able to answer

- **Is this what happened in September 2024?** Identify which items were observed
  then and which are later inputs, model estimates or imposed scenarios.
- **Why does the old page have a score while this one does not?** The archive
  retained research arithmetic; it is not authorized to replace accepted inputs.
- **Why is there little change at 30 minutes?** Explain the baseline distribution,
  reachable denominator and changes at other fixed thresholds without tuning them.
- **Is that hospital or shelter actually usable?** Show identity/location evidence
  and event availability separately. Say unknown when the latter is unknown.
- **Are these flood victims?** Residential population is context. Actual flood
  exposure, evacuation participation and shelter demand require separate evidence.
- **Why not just fix every disconnected road?** Different levels, rivers and
  barriers can make a proximity connection false; changes need evidence.
- **What is the practical next action?** Inspect a named consequential connection
  or destination, or compare a stated conditional option. Do not imply an order.

## Internal acceptance checklist

- [ ] One package identity and release SHA underpin all slide, brief and report numbers.
- [ ] Event observation time, footprint, processing and reuse status accompany flood layers.
- [ ] The headline names the service and travel mode; incompatible destinations are excluded.
- [ ] The selected geography and all population exclusions are visible and reconciled.
- [ ] Road/site reviews record evidence and unknowns; no false review approval is assigned.
- [ ] Intervention selection is justified independently of a desire for a larger effect.
- [ ] The conclusion survives stated sensitivity cases or visibly states where it changes.
- [ ] Capacity/site/demand identities align; actual capacity and equity remain null where unsupported.
- [ ] A nontechnical reviewer can identify priority, driver, population, intervention and uncertainty after one minute.
- [ ] The tested static export and extracted offline package reproduce the same story.
- [ ] A second-machine offline rehearsal is recorded; local/browser smoke tests alone do not fulfill it.
- [ ] Current organizer rules and owner-supplied team/contact fields are verified.

Check items only against actual evidence. Public-source gaps do not justify
inventing dates, validation, capacities, demographic counts or completed human
review. The original proposal files are retained submission history; do not
present their old metadata or numerical examples as a current finals release.
