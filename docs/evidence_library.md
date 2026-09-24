# Local evidence library and scenario demonstration

The evidence library connects the 17 acquired dataset selections to six study AOIs and eight AOI/event packages. Four AOIs (01, 03, 05 and 06) run the full context-based scenario demonstration. AOI-02 (Mae Sai district) and AOI-04 (U Taphao basin) provide coverage-only evidence packages and surrounding routing context for the two core demonstrations; they do not have district-wide or basin-wide access results. The library supports a traceable, non-operational research demonstration while event references, facility availability, road conditions and some reuse permissions remain unresolved. `/studio/brief/` leads with review priorities, modelled access and three consequential intervention comparisons. `/studio/library/` retains the detailed evidence review; the existing `/studio/` validation report remains available. No brief fabricates an accepted event impact or FPPS.

The local research package contains normalized observations, quality reviews and candidate geometry. The web package contains a separate, explicitly allowlisted projection. A file being downloadable from an official website does not, by itself, establish permission to redistribute it or suitability as an event reference. No private agency export or agency contact is required by this workflow.

## Inputs and installation

Run commands from the repository root. Use Python 3.10 or later, `uv`, and the repository's pinned pnpm version from `package.json`. Synchronize the committed Python and JavaScript dependencies:

```powershell
uv sync --locked --all-extras
pnpm install --frozen-lockfile
```

The `evidence` Python extra supplies Rasterio, Pillow and Requests. The geospatial and development extras supply the spatial processing and test dependencies. `uv.lock` records the Python dependency resolution; `pnpm-lock.yaml` records the web dependency resolution.

Keep the acquired bundle and durable generated outputs outside Git. Configure these environment variables to absolute local directories before running the example below. They are operator conveniences passed to the CLI, rather than automatically discovered application settings.

| Variable | Directory contents |
| --- | --- |
| `FLOODGUARD_BUNDLE_ROOT` | Immutable acquired bundle, including `FILES_SHA256.csv` and its source subdirectories. |
| `FLOODGUARD_REPORTS_ROOT` | `dataset_file_locations.csv` and `expanded_data_inventory.csv`. |
| `FLOODGUARD_EVIDENCE_OUTPUT` | Writable durable output directory, separate from and outside the immutable bundle. |
| `FLOODGUARD_CONTEXT_ROOT` | Existing open-context collection, either containing `open_context/` or pointing to that directory itself. Required for the actual AOI context scenarios described below. |

The existing context collection must contain `osm_geofabrik/thailand-latest.osm.pbf` and `worldpop_population/tha_ppp_2020.tif`. The pipeline verifies their identities against `outputs/open_context_data_file_manifest.csv`. It reuses these inputs; it does not download OSM or WorldPop again. A different source snapshot requires a deliberate manifest and provenance update.

QGIS/GDAL's `ogr2ogr` is also required for extracting the existing OSM context. Installing the Python extras does not install this executable. On Windows, discovery checks `FLOODGUARD_QGIS_BIN`, then `ogr2ogr` on `PATH`, then QGIS installations under `ProgramFiles`. If automatic discovery fails, set `FLOODGUARD_QGIS_BIN` to the QGIS `bin` directory. The evidence CLI has no `--qgis-bin` argument. This diagnostic checks the same discovery helper:

```powershell
uv run --all-extras python -c "from floodguard.open_context_extract import find_qgis_bin; print(find_qgis_bin())"
```

## Build and rebuild

The example uses a fixed UTC generation timestamp so repeated builds of the same frozen inputs do not acquire a new report timestamp. This is package-generation metadata, not a source observation time. Change it deliberately for a new evidence release.

```powershell
$requiredVariables = @(
    'FLOODGUARD_BUNDLE_ROOT',
    'FLOODGUARD_REPORTS_ROOT',
    'FLOODGUARD_EVIDENCE_OUTPUT',
    'FLOODGUARD_CONTEXT_ROOT'
)
foreach ($variableName in $requiredVariables) {
    if (-not [Environment]::GetEnvironmentVariable($variableName)) {
        throw "Configure $variableName before building the evidence library."
    }
}

$contextData = $env:FLOODGUARD_CONTEXT_ROOT
if (Test-Path -LiteralPath (Join-Path $contextData 'open_context') -PathType Container) {
    $contextData = Join-Path $contextData 'open_context'
}
$evidenceArguments = @(
    'scripts/build_evidence_library.py',
    '--bundle-root', $env:FLOODGUARD_BUNDLE_ROOT,
    '--locations-csv', (Join-Path $env:FLOODGUARD_REPORTS_ROOT 'dataset_file_locations.csv'),
    '--inventory-csv', (Join-Path $env:FLOODGUARD_REPORTS_ROOT 'expanded_data_inventory.csv'),
    '--output-dir', $env:FLOODGUARD_EVIDENCE_OUTPUT,
    '--public-dir', (Join-Path (Get-Location) 'apps/web/public/evidence-library'),
    '--aoi-dir', (Join-Path (Get-Location) 'resources/aoi/upload'),
    '--context-root', $env:FLOODGUARD_CONTEXT_ROOT,
    '--boundary-archive', (Join-Path $contextData 'hdx_cod_ab/tha_admin_boundaries.gdb.zip'),
    '--generated-at', '2026-09-21T11:05:43Z',
    '--reuse-normalized'
)
uv run --all-extras python @evidenceArguments
```

`--reuse-normalized` is safe for a first build. It reuses a previous normalization only when the source manifest, AOI hashes, adapter implementation hashes and recorded runtime identity match. It also verifies the saved hashes of the normalized outputs. A changed normalized output is an error; a changed cache key causes normalization to run again. Remove this flag to force fresh normalization and scenario calculations from the immutable sources.

Omitting `--context-root` produces clearly labelled illustrative synthetic scenarios for AOIs 01, 03, 05 and 06; AOIs 02 and 04 remain coverage-only. Synthetic scenarios test mechanics and are not results for the actual local road network or population. Supply the existing context collection for the four AOI demonstrations.

To perform bounded public-website checks and acquire the published DWR context again, append the optional flag:

```powershell
uv run --all-extras python @evidenceArguments --check-public-routes
```

This flag makes network requests and saves new responses under the external output's `acquisition/` directory. The ordinary build uses the existing local acquisition receipts. A successful HTTP response is reviewed separately from whether it contains a usable dataset. Rechecking mutable websites is a new acquisition run, not a byte-for-byte reproduction of an earlier response. It does not contact agencies, submit requests, or obtain private exports.

If `facility_review/public_identity_reviews.json` is present in the external output, the build consumes those explicit reviews. The identity crosswalk can be regenerated without that file, but then all identity decisions remain unresolved. Preserve this review file and its provenance with the local handoff when reproducing the reviewed snapshot.

## Catalog, lineage and output boundaries

The catalog uses schema version `1.0` and transformation version `evidence-demo-1`. A package version is derived from registry content, evidence implementation hashes, runtime identity and the existing-context configuration/manifest. Runtime identity includes the dependency lock and relevant installed Python/native geospatial versions; a changed geospatial runtime can change floating-point calculations and therefore creates a new package identity. Reproduce the recorded environment when comparing bytes. Individual AOIs, inputs and output packages also have hashes. Source dates, acquisition dates, source-layer temporal assertions and package-generation dates remain separate fields. Registry enrichment links derived records back to verified source assets, including source archives where available.

The original 17 selections are retained, even where two selections share physical files. In particular, the two Chiang Rai age selections use year filters on the same three source CSVs. Additional entries for existing OSM, existing WorldPop and project-owned scenarios describe supporting inputs, not newly acquired datasets.

| Selection | Acquired data | Principal role |
| ---: | --- | --- |
| 1 | Mae Sai accumulated flood extent and analysis footprint | Historical cumulative exposure; outside the footprint remains unobserved. |
| 2 | Mae Sai 22 October 2024 flood extent | Separate single-date October observation. |
| 3 | Ayutthaya/Pathum Thani HII observations, September–November 2024 | Gauge context with explicit gaps. |
| 4 | Ayutthaya/Pathum Thani HII observations, September–November 2025 | Gauge context with explicit gaps. |
| 5 | Hat Yai/U Taphao HII observations, November 2025 | Gauge timing and regional context. |
| 6 | Chiang Rai district age categories, 2018–2023 | Earlier demographic context. |
| 7 | Chiang Rai district age categories, 2025 | Later demographic context. |
| 8 | Chiang Rai district registered population totals, 2022–2025 | Denominator reconciliation. |
| 9 | Pathum Thani provincial age bands, 2018–2024 | Provincial age structure. |
| 10 | Songkhla district population by sex, 2019–2025 | District totals; no age bands. |
| 11 | Songkhla village population, households and codes, 2023–2025 | Administrative joins and coverage review. |
| 12 | DDPM planned shelter inventory | Historical candidate destinations; activation and available capacity unknown. |
| 13 | DGA CITIZENinfo-derived healthcare inventory, 2020 | Historical candidate healthcare locations. |
| 14 | Copernicus GLO-30 surface elevation | Static terrain context. |
| 15 | HydroRIVERS river network | Generalized drainage context. |
| 16 | 11 September 2024 northern road bulletin and six transcribed incidents | Documentary road evidence. |
| 17 | 27 November 2025 Hat Yai restoration announcement | Documentary recovery timeline. |

The six AOIs produce eight packages: two Mae Sai AOIs for September 2024, two Hat Yai AOIs for November 2025, and two lower Chao Phraya AOIs for each of the 2024 and 2025 events. Six event packages contain scenarios for the four analytical AOIs; the district and basin each have one coverage-only package. Search AOIs are not automatically administrative reporting units.

| AOI | Package scope | Routing boundary for scenarios |
| --- | --- | --- |
| 01 — Mae Sai core | Full historical-context scenario demonstration | AOI-02 district |
| 02 — Mae Sai district | Evidence coverage and gaps; no district-wide access/capacity result | Supplies AOI-01 routing context |
| 03 — Hat Yai core | Full historical-context scenario demonstration | AOI-04 basin |
| 04 — U Taphao basin | Evidence coverage and gaps; no basin-wide access/capacity result | Supplies AOI-03 routing context |
| 05 — Bang Ban/Sena, Ayutthaya | Full historical-context scenario demonstration, associated with 2024 and 2025 packages | AOI-05 |
| 06 — Rangsit, Pathum Thani | Full historical-context scenario demonstration, associated with 2024 and 2025 packages | AOI-06 |

The lower Chao Phraya packages reuse the same historical OSM/WorldPop scenario calculations for both event years. The event selection changes the associated evidence inventory, not the scenario source vintage. Differences between 2024 and 2025 are not inferred from that reused context.

The external output contains the following logical artifacts:

| Artifact | Purpose |
| --- | --- |
| `evidence_registry.json` | Dataset selections, verified physical assets, source lineage, temporal assertions and rights decisions. |
| `adapter_summary.json` | Dataset and AOI quality summaries. |
| `normalization_receipt.json` | Cache key and output-integrity checks. |
| `build_runtime.json` | Locked dependency identity, actual Python/native geospatial versions and external OGR identity. |
| `normalized/` | Local normalized CSV, GeoJSON, raster and gauge-series artifacts. |
| `context/<aoi>/context_inputs.json` | Existing road graph, population, candidate facilities, coverage and input identities for AOIs 01, 03, 05 and 06. |
| `context/<aoi>/local_facility_scenarios.json` | Local experiments using supplied facility candidates for those four analytical AOIs. |
| `context/<aoi>/osm_context_scenarios.json` | Historical OSM-destination experiments and associated cache receipt for those four analytical AOIs. |
| `scenarios/<aoi>.json` | Detailed scenario inputs/results for analytical AOIs; explicit coverage-only status for AOIs 02 and 04. |
| `packages/` | Local AOI/event packages, including permitted local research detail. |
| `facility_review/` | Stable-record crosswalk and public identity-review receipts. |
| `acquisition/gap_register.json` | Public-route outcomes, missing data and analytical fallbacks. |
| `acquisition/ngis/context_manifest.json` | Newly downloaded DWR layers, URLs, hashes, counts and unresolved terms. |
| `local_evidence_report.html` | Local review with gauge segments, candidate records and links to normalized files. |
| `public_evidence_report.html` | Copy of the allowlisted report suitable for reviewing the web projection. |
| `public_export_report.json` | Export receipt and public-file checks. |

The web export under `apps/web/public/evidence-library/` contains `catalog.json`, eight packages, six terrain previews, `report.html` and, when existing context is supplied, four downloadable OSM/WorldPop derived routing databases for AOIs 01, 03, 05 and 06. District/basin coverage-only packages have no standalone scenario database download. The exporter checks for disallowed fields, local paths, non-finite numbers and geometry without an accepted derivative policy. Raw downloaded files and private contact fields are not web assets.

The current hosted projection uses Copernicus terrain previews with attribution, project-owned scenarios and the already licensed OSM/WorldPop context with ODbL/CC BY notices and a derived-database download. HII observations and unresolved-rights flood, population, DDPM, historical healthcare, HydroRIVERS and documentary road details remain local; their metadata and limitations can be displayed publicly. DWR/NGIS geometry also remains local until its reuse terms are resolved. Preserve source notices and the saved rights evidence with any handoff; changing the rights policy requires a new evidence review.

## Source quality findings in the acquired snapshot

These are checks on the frozen 21 September 2026 acquisition bundle. They are not assertions that the underlying public services are current or complete.

### Flood products and gauges

The accumulated flood product's description ends on 22 October 2024 while its layer name ends on 12 October. Both assertions are retained. The dissolved accumulated geometry has no dates for individual flooded patches, so it cannot yield a September-only extent. The October 22 extent stays separate. The analysis footprint covers approximately 81% of each Mae Sai AOI; the remaining area is unobserved, not dry. No independent September event reference has been accepted from these products.

The HII parser processes 106 station-month CSVs from 28 stations: 462,816 rows, 427,018 numeric observations and 35,798 null/sentinel observations. It recognizes the source's 12-header/15-field schema mismatch without shifting the reliable observation fields. Raw timestamps and retrieval-time normalization are retained separately; observation timezone remains unconfirmed and is not silently assumed to be UTC or Thai local time.

The adapter preserves missing measurements, daily coverage and contiguous measured segments. It does not connect a hydrograph across a missing interval or interpolate an event peak. The `999999` sentinel occurs in 112 rows and is treated as missing rather than as water level. ATG092 is wholly missing in September and October 2024 and has only one valid November observation; CPY010 is wholly missing in October 2025.

For November 20–28, 2025, each Hat Yai station has 1,296 expected ten-minute slots. Missing counts are 520 for SLA001, 841 for SLA002, 301 for SLA007 and 51 for ONE037. ONE037 lies outside the uploaded basin AOI and is regional context. Station proximity does not establish hydrological equivalence; missing local stations are not replaced automatically. The public MYA004 September 2024 path returned 404 in the recorded check.

### Population

Seven CSVs produce 4,467 normalized rows with original labels, Buddhist Era years, Common Era conversions, source row identity and geographic level preserved. Chiang Rai's available age years are 2018–2023 and 2025; observed 2024 age counts are absent. The 2024 district total does not fill that gap.

The review retains 90 elderly-table sex-total arithmetic mismatches. Mae Sai's selected 2025 age categories sum to 133,531 against a district total of 133,568, a difference of 37. Child and working-age definitions require reconciliation, and overlapping 60+ and 65+ categories must not be summed. Provincial Pathum Thani age bands and district/village Songkhla counts do not become subdistrict ages through a join alone.

The proposed 2023/2025 age sensitivity comparison remains blocked until age definitions, denominators and administrative coverage are compatible. No local 2024 age estimate, local age-based equity result or vulnerability score is silently substituted. Existing modelled population can support explicitly labelled general access experiments.

### Shelters and healthcare

The four-province shelter subset contains 1,166 records, including 16 invalid coordinates and 42 unknown capacity values. Its 1,150 valid points occupy 996 distinct coordinates. Mae Sai core contains 13 records at four coordinates, including ten records at the same hall coordinate. Coordinate clusters are review groups, not automatic duplicates or proof of distinct capacity. Stable IDs incorporate source identity and logical CSV record numbers, which can differ from physical line numbers when fields contain newlines. Derived records remove personal contact fields.

The DDPM catalog's 6 May 2024 source-update date and the CSV's 9 August 2024 modification date are both retained. Neither date proves that a shelter was open during a flood or that a planned capacity was available. Unknown capacity remains null, not zero. Unreconciled records are excluded from accepted capacity calculations.

The healthcare source contains 10,622 points but only five distinct values in its nominal ID field. Stable internal IDs therefore retain the original feature index and source identity. The source's 2020 reference year remains visible; candidate locations do not establish current operation or event-time service.

The saved core-area identity review covers 41 records: three names/addresses have support from current official MOPH pages and 38 remain unresolved. The matches concern Mae Sai Hospital, Hat Yai Hospital and a Mae Sai primary healthcare facility. A supported identity does not verify the supplied coordinates, historical activation, service availability or capacity. Those fields remain unknown. The review records whether evidence was inspected as a public webpage rather than saved as a successful HTML download; a generic HTTP 403 is not proof that an account is required.

### Terrain, drainage and road documents

Copernicus inputs are approximately one-arcsecond surface models. Slope review reprojects to EPSG:32647 at 30 m resolution; it does not compute metre-based gradients directly in geographic degrees. Negative values remain visible for review, including the Rangsit minimum of approximately −13.75 m. Buildings, vegetation and potential artifacts limit fine-scale hydraulic interpretation. These values are not flood depths.

HydroRIVERS clips preserve source identities and recompute clipped lengths. Counts across AOIs 01–06 are 12, 40, 16, 86, 11 and 18 reaches. Links to downstream reaches outside a clip are not automatically source corruption. The network is generalized and does not establish local canal, culvert, levee or urban-drain completeness.

Six transcribed 11 September road incidents retain the original traffic wording: five describe difficult passage and one describes impassability. Route, district and chainage conflicts remain visible. No accepted segment geometry is produced from these descriptions, and absence of a closure does not mean a road was open. The Hat Yai November 27 announcement remains narrative recovery evidence rather than a segment-level condition log.

## Additional official website checks

The published NGIS ArcGIS directory exposes DWR stream and waterbody services. Bounded AOI queries acquired 12 GeoJSON layers, with separate count checks and no missing or invalid geometries in the saved responses. The 3,318 feature references include overlap between nested AOIs and are not a count of unique features across Thailand.

| AOI | Streams | Waterbodies |
| --- | ---: | ---: |
| 01 — Mae Sai core | 340 | 9 |
| 02 — Mae Sai district | 1,823 | 65 |
| 03 — Hat Yai core | 51 | 23 |
| 04 — U Taphao basin | 333 | 180 |
| 05 — Ayutthaya | 176 | 97 |
| 06 — Rangsit/Pathum Thani | 162 | 59 |

The responses retain complete intersecting source features, rather than clipping every geometry to the AOI boundary. `context_manifest.json` records query URLs, hashes, counts and this spatial meaning. Source epoch and reuse terms are unresolved, so these are local static context only. They are not event flood polygons, a complete drainage inventory or measurements of drainage capacity. The NGIS hospital service exposed OSM-derived fields and was not substituted for an official healthcare register.

The recorded UNOSAT product 3991 response supplies product metadata but no downloadable SHP/KML/WMS reference asset. The MYA004 path returned 404; the bounded DOPA/DRR attempts did not yield usable missing tables or road-condition files. The MOPH bulk CSV returned 403 with no established cause, while a few ordinary official facility pages supported identity review. These outcomes stay in the gap register and do not prevent local development.

The inspected Hat Yai Sentinel-1 metadata identifies a compatible November 11/23, 2025 pair with relative orbit 164, descending acquisition, VV/VH polarization and full coverage of the uploaded core and basin AOIs. Metadata availability does not mean the original SAFE archives were acquired. The originals remain absent locally; any account-dependent original download and candidate flood processing remain separate work. No metadata-only record is promoted to a flood candidate, reference, training label or accuracy result.

The existing checksum-bound Mae Sai satellite package remains available through the linked `/studio/` validation report. Its baseline uses `20 * log10(amplitude)` on uncalibrated Sentinel-1 amplitude, and its manually digitized cross-border weak reference does not measure Thailand-side event accuracy. This integration preserves that package and its restrictions; it does not feed its weak-reference metrics into the new evidence assessments or silently replace the qualified-reference gate. Candidate extraction, threshold selection and independent evaluation remain separate.

## Scenario definitions and interpretation

When existing context is supplied, the four analytical AOIs use the historical OSM network and WorldPop 2020 pixel demand. Positive pixel centres inside each analytical AOI are included without fractional boundary allocation. The network context expands to Mae Sai district for Mae Sai core and to the U Taphao basin for Hat Yai core. District/basin routing context can contribute paths and candidate destinations to a core analysis, but does not establish access results for the district/basin population. Paths outside the selected context are unavailable, so boundary restrictions and excluded demand remain visible.

The graph is undirected with fixed road-class speeds. It connects compatible shared source vertices and does not create a junction merely because two drawn lines cross. Layer, bridge and tunnel distinctions can leave conservative disconnections. One-way restrictions, turn restrictions and event-time passability are not represented.

| Model road class | Assumed speed, km/h |
| --- | ---: |
| Motorway | 80 |
| Trunk | 70 |
| Primary | 60 |
| Secondary | 50 |
| Tertiary | 40 |
| Residential | 25 |
| Unclassified | 25 |
| Local/service/other supported local classes | 20 |

Facilities connect to the graph only within 100 m; population points connect only within 250 m. Both connector types use 5 km/h walking time. Distance alone does not prove that a connector crosses a walkable surface or avoids a barrier. Failed connectors contribute to excluded coverage rather than being treated as reachable or as zero demand.

Access is evaluated at 15, 30 and 60 minutes, with 30 minutes used for the primary scenario comparison. Baseline access, people already without access, people newly losing access and demand excluded for inadequate network coverage remain separate outputs. The deterministic stress tests close an edge adjacent to the largest connected demand cell, remove a stably selected connected destination, or add a hypothetical destination at the chosen demand node. These are repeatable imposed changes, not observed closures, optimal interventions or evacuation instructions.

Local scenario files can use the supplied shelter/healthcare candidates while retaining their unresolved status. The hosted context demonstration uses OSM healthcare candidates such as hospitals, clinics, doctors and pharmacies. Generic OSM `amenity=shelter` is excluded as an evacuation-shelter authority because it can describe a bus or rest shelter. Candidate health facilities do not supply shelter beds or capacities.

Capacity experiments use a deterministic maximum-flow allocation of modelled demand. They maximize served demand without claiming a minimum-travel assignment or an individual evacuation plan. Shared demand is not counted twice, and unmet demand is separated into capacity limits, unreachable destinations, excluded coverage and unknown capacity.

No supplied shelter currently passes the identity/eligibility gate for accepted capacity use. The fallback therefore creates one explicitly hypothetical temporary destination with 50, 100 or 200 places. These are scenario assumptions. If a future shelter has a reconciled identity and a numeric planned capacity, separate 25%, 50% and 100% planned-capacity experiments can be considered; a planned value still does not establish actual availability.

## Scoring and scientific acceptance

The existing FPPS definition and weights are unchanged:

```text
FPPS = 0.30 Flood likelihood
     + 0.25 Exposure
     + 0.20 Access gap
     + 0.15 Road criticality
     + 0.10 Vulnerability/context
```

The primary assessment has unavailable component values where qualified inputs are absent. Unknown values are not replaced with zero and weights are not redistributed. In the present packages, primary FPPS and the primary action class are null. Fixed-weight lower/upper arithmetic sensitivity bounds are not statistical confidence intervals.

Explicit completed score scenarios pass through the existing scorer. Their low confidence keeps the action class at E, “Monitor and Verify.” Scenario calculations do not upgrade the primary assessment. A modelled access gap derived from historical context does not become an observed event access gap.

Existing primary-source, training-label, reference-acceptance and production gates remain unchanged. Neither a successful local build nor a visually plausible map establishes validated event-specific flood accuracy, real shelter availability or safe road passage. Future event references still require suitable timing, independent provenance, spatial coverage and accepted use terms.

## Open the candidate and verify it

For development:

```powershell
pnpm --filter @floodguard/web dev
```

Open the development server's `/studio/library/` route. Select an AOI and event, inspect source dates and missingness, compare labelled scenarios and download the generated report. Use the external `local_evidence_report.html` for detailed gauge observations and local candidate geometry that is intentionally absent from the hosted projection.

For the static competition candidate and its relevant checks:

```powershell
uv run --locked --all-extras pytest tests/test_evidence_catalog.py tests/test_evidence_adapters.py tests/test_evidence_review.py tests/test_evidence_acquisition.py tests/test_evidence_context.py tests/test_evidence_scenarios.py tests/test_evidence_local_report.py tests/test_evidence_export_validation.py tests/test_evidence_reproducibility.py tests/test_evidence_event_review.py tests/test_evidence_population_review.py tests/test_evidence_interventions.py tests/test_evidence_decision_brief.py tests/test_access.py tests/test_scoring.py tests/test_equity.py
uv run --locked --all-extras python scripts/verify_evidence_library.py --public-dir apps/web/public/evidence-library --local-dir $env:FLOODGUARD_EVIDENCE_OUTPUT --output-receipt (Join-Path $env:FLOODGUARD_EVIDENCE_OUTPUT 'qa/export-integrity.json')
pnpm lint
pnpm typecheck
pnpm test:contracts
pnpm test:web
pnpm --filter @floodguard/web test:evidence-assets
pnpm build:web
pnpm --filter @floodguard/web test:evidence-browser
pnpm test:offline
pnpm test:csp
pnpm --filter @floodguard/web verify:profiles
git diff --check
```

The browser checks use a locally available browser through the repository helper. If no compatible browser is installed, install Playwright Chromium using `pnpm --filter @floodguard/web exec playwright install chromium`, or set `FLOODGUARD_BROWSER_EXECUTABLE` to an available supported executable. Browser checks must target a completed static competition build; a development-server pass does not establish offline behavior.

`test:evidence-browser` checks the eight packages, unavailable primary scores, language switching, report download, invalid package selection and offline use. The offline candidate uses same-origin precomputed assets and does not require a live geospatial API. This is a candidate offline workflow, not a claim that an uncached first visit works without a connection.

`verify:profiles` builds `public-production`, verifies its artifact/browser restrictions, builds the competition profile and checks the same-origin profile transition. The `public-production` build prunes the entire Studio route and evidence-library assets; this work does not publish the evidence library on the public production profile. `pnpm build:public` produces that restricted profile explicitly, while `pnpm build:web` produces the competition candidate.

The commands above define the required verification, not a claim that a particular handoff passed them. Final suite counts, live browser receipts, commit identity and publication status belong in the final verified task receipt. Until that receipt is recorded, treat whole-project verification and release acceptance as pending.

## Local handoff and remaining work

Hand off the immutable bundle, both input inventory CSVs, the existing context collection and the durable external output as separately identified directories. Preserve `FILES_SHA256.csv`, `evidence_registry.json`, `normalization_receipt.json`, the facility-review evidence and acquisition manifests. Use logical filenames and hashes in shared documentation; personal absolute paths and credentials are not part of the repository or hosted package.

The next data work remains bounded to published websites: recover a usable suitably dated flood reference if one is actually exposed; obtain missing gauge observations if a public archive provides them; reconcile population definitions and administrative coverage; verify facility identity and coordinates; and look for geocoded documentary road conditions and local drainage detail with usable terms. Until those checks succeed, retain the existing explicit gaps and scenario assumptions. No agency-contact task is a prerequisite for running or reviewing this prototype.


## Decision brief and reviewed public evidence

The decision brief is an additive version 1.0 contract. It does not modify `AreaDecision`, the scorer, the legacy comparator or qualified-reference ingestion. Accepted priority/action class and affected population remain null. The visible review priority explains what to verify next. Invalid AOI/event choices remain unavailable. EN/TH headings and comparison labels share the same package; source quotations and analyst review findings retain their original language.

For the reviewed release, preserve the external output's `review/population_definition_evidence.json`, `review/public_identity_reviews.json`, their `review/acquisition/` receipts and `acquisition/event_review/` snapshots. These are curated inputs, not generated substitutes. The builder hashes them, reruns population/destination review and binds the results into package identity. `--boundary-archive` also requires the saved official HDX metadata and exact CC BY 3.0 IGO legal text. Without that optional argument, administrative reporting stays unavailable; search polygons never substitute for subdistricts. The source archive is SHA-bound and retains its 2022-01-22 vintage, attribution and unverified event-era currency. Crosswalk areas use equal-area EPSG:6933; travel calculations retain EPSG:32647. Web geometry uses EPSG:4326.

Full official ADM3 geometries are selected by intersection with the AOI. Every brief labels full/partial reporting scope, and joins population-cell centroids to unique subdistrict codes. Shared-boundary or overlapping membership stays unassigned. No-data population remains unknown; AOI totals and subdistrict intersection totals are not interchangeable. Mae Sai study windows include land outside the Thai reporting source.

The event review retains the October 12/22 conflict, distinguishes the dated September UNOSAT publication from a usable vector, and records the downloaded EOS-RS November 23 Hat Yai proxy as a local/citation asset with unresolved source-specific terms and no analysis footprint. No present product passes event-context or independent-validation acceptance. No flood exposure is calculated from an inadmissible mask.

## Consequential access experiments and demand assumptions

The scenario selector uses the baseline network, before evaluating outcomes. It ranks one closure by baseline-route residential demand; one removal by residents served by a nearest destination; and one hypothetical addition by residents lacking 30-minute access. Stable IDs break ties; the top ten candidates, exact selection reason and single-outcome-evaluation bound are recorded. These are reproducible experiments, not optimal interventions or observed disruptions. The review never automatically joins same-coordinate grade splits or creates crossings from proximity.

Results separate five resident categories: within 30 minutes, connected with a route beyond 30 minutes, connected with no route to a candidate destination, no accepted graph connection, and population unavailable because of source nodata (unknown count reported in coverage). The first four conserve known modelled residential population. Travel-time comparisons include only residents with finite routes in both cases; newly reachable/unreachable counts are separate. Zero threshold change can coexist with nonzero travel-time change.

Capacity demand is an explicit 10% residential-participation scenario, with 5%/10%/25% sensitivity. It does not equate all residential population or all flood-exposed population with evacuation need. Hypothetical 50/100/200-place capacity settings remain separate from source capacity. The hypothetical capacity mechanics site is deliberately distinct from the underserved-access addition: it uses a node in the largest connected residential component to test capacity constraints. Neither site is accepted as safe, feasible or activated. Assigned demand, capacity-limited demand, unreachable demand, missing graph coverage and unknown capacity are mutually exclusive allocation outcomes. Actual capacity and actual evacuation demand remain null.

Chiang Rai district children/working-age numerical bounds remain unresolved; 60+ and 65+ overlap. The owner catalog's provincial elderly subgroup definitions are not silently applied to district columns. The 2024 gap and arithmetic failures remain visible. Pathum Thani's 17 explicit age bands support a provincial distribution relative to that table's sum, not a local demographic allocation. Repeated Songkhla village keys remain unaggregated. Current healthcare name/address matches and dated Mae Sai shelter-activity reports improve identity review without confirming historical point geometry, continuous operation or event capacity. Demographic equity remains unavailable.

The downloadable report includes the concise briefs and a reproducibility appendix. Public exports contain approved boundaries, OSM/WorldPop scenario derivatives, terrain context and source metadata. Restricted flood/facility/gauge geometry or observations remain outside the actual static build.
