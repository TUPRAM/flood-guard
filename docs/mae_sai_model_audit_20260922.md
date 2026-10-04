# Mae Sai analytical correction and candidate-flood scenario

This supersedes the numerical examples in the September 22 development brief.
It does not supersede reference qualification, scientific acceptance or official
warning gates. All population figures below are WorldPop 2020 model estimates
for Thai reporting-boundary intersections with AOI-01. They are not flood victims,
observed isolation, full-tambon totals or a historical reconstruction.

## 1. Connectivity finding

The walking graph has **14,643 graph bridge edges and 13,877 articulation nodes**,
over 255 connected components. These are graph-theoretic objects, including
degree-two road vertices and dead ends, not counts of physical bridges or errors.
The audit computes the modelled residents losing all hospital routes for every
single edge and articulation-node removal. Impacts overlap and must not be summed.
Parallel edges are retained. Already-unreachable and unsnapped demand is excluded
from new route-loss counts. Full results are in the public finals model database.

The earlier 41,379-resident dependency on `osm-way-934550386-segment-0` and `-1`
was dominated by the hospital point's single assumed connector. Original OSM
way **934550386** is a short spur wholly inside hospital site **371233866**.
It joins Tessaban Road 15, way **1388175295**, at node **484222068**. Tessaban
Road 15 crosses the hospital polygon boundary twice; the spur does not. This
does not establish the actual number, position or event-time state of entrances.

The revised scenario uses two existing nodes on Tessaban Road 15:
**8661331590** and **484222069**, approximately 79.6 m and 91.3 m from the
original site point. Both connector lines stay inside the hospital polygon and
within the fixed 100 m limit. No road edge, crossing or topology is invented.
The source-bound review is `resources/finals/mae_sai_facility_connections.json`.
These are geometry-checked **assumed connectors**, not surveyed entrances or
confirmed walkable paths. The relevant road geometry was mapped in 2025; it
does not establish September 2024 access.

For the **same two original spur closures**, walking all-route loss changes from
41,379.4 to **15.8** modelled residents. The graph and population are unchanged;
the destination connection assumption changes. This is a correction to the model's
single-point dependence, not proof that the revised routes are safe or historical.

Public OSM evidence: [spur](https://www.openstreetmap.org/way/934550386),
[hospital polygon](https://www.openstreetmap.org/way/371233866),
[Tessaban Road 15](https://www.openstreetmap.org/way/1388175295).
The review records API snapshot hashes and node identities. Raw OSM editor
metadata remains outside the public export.

## 2. Flood now enters the experiment

The original Sentinel-1 SAFE acquisitions of **3 and 15 September 2024 UTC** (4 and 16 September at about 06:16 in Thailand) are
checksum-verified again. A separate candidate uses the existing amplitude-change
approach: a fixed **2.25 dB** decrease in a **0.4 VV + 0.6 VH** combination,
on a 20 m EPSG:32647 grid. Second-order GCP warping with bilinear resampling
provides alignment; this is **uncalibrated amplitude**, without radiometric or
terrain correction, speckle filtering or permanent-water exclusion. It is not a
calibrated probability, accepted extent or independent validation reference.
No cross-border human labels or weak-reference accuracy metrics enter this build.

Candidate area is approximately **6.07 km²**, within a jointly valid observation
footprint of approximately **104.62 km²**. Empty candidate, unobserved coverage
and missing data remain distinct. Source products, observation timestamps, grid,
threshold, method, rights, geometry hashes and implementation hash are published
with the candidate. Reuse follows the
[Copernicus Sentinel legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice):
**Contains modified Copernicus Sentinel data (2024), processed by FloodGuard.**

The closure rule is fixed before computing impact: close each road segment with
a positive-length centreline intersection with the candidate, using a 1e-6 m
numerical tolerance. This includes mapped bridges and is deliberately a stress
assumption, not a finding of impassability. Roads outside the footprint remain
unchanged by assumption, not because they were observed dry.

| Walking scenario quantity | Result |
|---|---:|
| Candidate-overlap residents, by raster cell centre | 2,044.2 |
| Imposed segment closures | 1,824 |
| Newly lose 15-minute hospital access | 2,197.4 |
| Newly lose 30-minute hospital access | 11,199.3 |
| Newly lose 60-minute hospital access | 16,910.6 |
| Newly lose all hospital routes | 29,642.5 |

Network consequences can extend beyond the candidate-overlap population. Threshold
loss and losing every route answer different questions and must not be added.
The 30-minute loss excludes people already beyond 30 minutes. The route map is an
illustration from a prepared origin; the headline is the population experiment.

Three normalized components now compute from the same candidate and access model:
exposure is candidate-overlap residents / all in-scope residents; access gap is
graph-connected residents beyond 30 minutes or without a route / graph-connected
residents; road criticality is new all-route loss / baseline residents with a route.
Each ratio is multiplied by 100. Undefined denominators or incomplete observation
coverage produce nulls, not zeros. These are versioned scenario definitions.

**Accepted FPPS and action class remain null for named reasons:** calibrated flood
likelihood and compatible vulnerability/context are missing. Some reporting
intersections also lack a baseline route denominator. Fixed-weight arithmetic
bounds and explicit 0/50/100 completions are published per intersection; every
complete scenario passes through the unchanged scorer and returns **Class E**
because confidence is low. No weight, threshold, gate or `official_warning` changes.

## 3. Service network and placement

The same national OSM snapshot was searched over the core AOI plus a **10 km
geometric buffer**, including points, buildings and sites. It contains **one
hospital-class object**, already present in the district routing context. This
is a bounded inventory finding, not proof that only one real hospital serves the
area. Primary care and pharmacies are distinct services and never substitute
for hospital or shelter access. The reproducible audit records every candidate,
distance from the demand AOI, inclusion status and exclusion reason.

The two hypothetical additions are selected by demand assigned to a single
snapped node, then person-minutes and stable IDs. This is not an optimization of
regional hospital coverage. Small disconnected components can cap their benefit;
the audit reports each selected node's component size and population. Here both selected components have four nodes, containing 98.2 and 215.7 modelled residents respectively. That explains the previously small benefits; these are isolation experiments, not defensible new-hospital locations. The rule
and original comparisons remain visible rather than choosing a dramatic outcome.

## 4. Population, shelter and imagery intake

**DOPA 2024 acquisition is blocked on the public source.** The official catalogue
is reachable, but its linked year-67 resource and age/month/year service attempts
timed out. The [catalogue record](https://gdcatalog.go.th/dataset/gdpublish-statbyagemonth-66)
points to `statByMooBan.php?year=67`; catalogue metadata is not a table of age
counts. No 2024 tambon totals, verified code crosswalk or age reweighting is claimed.
WorldPop 2020 remains the explicit denominator; age equity remains unavailable.
Future reweighting must conserve a **whole tambon's** control total before clipping
to the AOI and must establish children/60+ definitions and registration coverage.
Never allocate a full tambon total into its partial AOI intersection.

`packages/contracts/schemas/facility-verification-v1.schema.json` and
`scripts/verify_facility_records.py` accept stable facility identity, role,
coordinates, entrance, capacity, effective interval, verification method/status,
and individually checksum-bound evidence for each claim. Status defaults to
unverified. Role, location and entrance evidence are distinct from event activation
and capacity; unknown capacity differs from zero. OSM or imagery alone cannot
establish shelter designation or operation. Personal contact fields are rejected.
Validated records are intake/review outputs, not automatic publication approval.
The current package contains no newly verified shelter; its service stays disabled.

`scripts/build_theos2_selected_manifest.py --delivery-metadata ...` adds a strict
delivery path alongside the existing sample inventory. It records file SHA-256,
scene ID, timezone-aware acquisition time, product level, band order, densified
raster footprint, actual AOI polygon/hash and overlap fraction. **Processing stays
false** without a checksum-matched written-terms file and an explicit permission.
Hosted display/download permissions are separate. Footprint coverage is not
cloud-free or valid-pixel coverage. Intake reads raster metadata, not image pixels;
no delivered THEOS-2 scene has been claimed or processed by this release.

## Reproduce locally

Use an external `$data` root containing the existing acquisitions and an external
`$run` root holding the normalized September 21 bundle and its copied review inputs.
Raw files stay unchanged outside Git. The guide's earlier library intake commands
still apply. Run from the repository, with the locked all-extras environment:

```powershell
uv sync --locked --all-extras
uv run python scripts/build_mae_sai_flood_candidate.py --external-data-root $data --output-dir "$run/flood_candidate" --generated-at 2026-09-22T06:00:00Z
uv run python scripts/build_mae_sai_finals.py --context-root $data --reporting-dir "$run/event_review" --output-dir "$run/finals" --reviewed-junctions "$run/review/osm_junction_review.json" --public-origins "$run/public_review/public_origins.json" --facility-connections resources/finals/mae_sai_facility_connections.json --flood-candidate "$run/flood_candidate" --generated-at 2026-09-22T06:00:00Z
uv run python scripts/audit_mae_sai_destinations.py --pbf "$data/open_context/osm_geofabrik/thailand-latest.osm.pbf" --finals-dir "$run/finals" --output-dir "$run/destinations"
uv run python scripts/verify_facility_records.py --input "$run/facility-intake.json" --event-date 2024-09-15 --output "$run/facility-intake-validated.json"
uv run python scripts/build_theos2_selected_manifest.py --input-dir $deliveredScenes --delivery-metadata $deliveryMetadata --aoi-dir resources/aoi/upload --output "$run/theos2_delivery_manifest.csv"
```

Facility input is a JSON list; a minimal safe record is
`{"facility_id":"immutable-source-record-id","verification_status":"unverified"}`.
Delivered-scene metadata has `schema_version: floodguard.theos2_delivery.v1` and
a `scenes` list. Each scene requires `scene_id`, relative `file`,
`acquisition_datetime`, `product_level`, `band_order`; optional `sha256`, `aoi_ids`,
`license_description`, `written_terms: {file, sha256}` and `permissions` with
`local_processing`, `hosted_display`, `downloadable_derivatives` booleans. Files
and terms resolve inside `$deliveredScenes`; unsafe paths are rejected. Supply
actual metadata and written terms, never infer them from an expected delivery.

## Technical verification boundaries

Windows path-stat and descriptor-stat exposed different meanings of `ctime`.
The repair compares consistent descriptor snapshots while retaining path identity,
size, modification and birth-time checks. It does not delete timestamp guards.
Tests cover unchanged rewrites, content changes and replacement with preserved
size/modification time.

Dependency auditing now exports locked third-party requirements without local
project distributions. Root and API audits run separately with strict checking;
CI retains JSON receipts instead of suppressing audit failures. JavaScript and API
dependency patches address the reported advisories. A zero-advisory receipt is
only a database-based dependency scan at its recorded time, not a security audit
of application logic, geospatial methods or deployment configuration.

Still required for stronger claims: independent flood reference/processing QA,
surveyed hospital entrances and passability, a more complete service inventory,
usable DOPA records, dated shelter activation/capacity, and a second-machine human
rehearsal. This release is a candidate decision-analysis demonstration.
