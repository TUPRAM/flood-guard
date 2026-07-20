# Mae Sai milestones 1-5 implementation status

## Decision

This receipt records the verified software state for the first five Mae Sai
capability milestones. It deliberately separates implemented software from
external evidence that FloodGuard cannot create or approve for itself.

The current Mae Sai profile remains:

- `dataset_mode=candidate`;
- `operational_status=non_operational`;
- `official_warning=false`;
- blocked from decision-layer promotion wherever qualified evidence is absent.

FloodGuard is a preparedness and rapid post-event prioritization tool. This
receipt does not claim an official warning capability, live road closures,
verified evacuation facilities, or qualified real-event model accuracy.

## Milestone status

| Milestone | Software status | Evidence status | Decision |
|---|---|---|---|
| 1. Real Mae Sai Command map | Implemented and verified | Eight real-coordinate reporting areas, 4,458 candidate road ways, 42 unverified facility candidates, and eight modeled access points are checksum-bound | Accepted as candidate/non-operational software |
| 2. Real backend scenario foundation | Implemented and verified | 13,620 population/routing nodes and 30,443 directed graph edges are bound by an immutable manifest; both closed-registry scenarios recompute access and equity on the server | Accepted as planning-rehearsal software |
| 3. Segment-level flood consequences | Implemented and verified | Probability, road, and facility inputs are checksum/grid/CRS/study-area bound; canonical HMAC receipts reject tampering and substitution | Accepted as report-only candidate software |
| 4. Qualified label foundation | Software gates and review workflow verified | Authority, mask rights/qualification, independent reviewer calibration, signed reference cells, and immutable final holdout evidence remain missing | **Blocked on external evidence** |
| 5. Controlled model comparison | Runner and fail-closed audit verified | The required qualified baseline/logistic/GeoAI comparison was not executed because Milestone 4 gates remain blocked | **Not run; no qualified metrics or champion** |

Milestones 4 and 5 are therefore not represented as scientifically complete.
Their software foundations are ready, and the gate correctly prevents a real
experiment or promotion in the absence of independent evidence.

## Implemented product evidence

### Study-area registry and API

- `fixture_thailand_demo` and `mae_sai_candidate_v1` are separate adapters.
- A broken or substituted Mae Sai bundle returns blocked/unavailable; it never
  silently falls back to the fixture.
- The API validates manifest and artifact hashes, feature counts, geometry
  types, bounds, join keys, area identities, attribution, safety wording, and
  candidate status.
- Layer requests support bounded area, bounding-box, facility type,
  verification state, minimum-risk, and regional/detail filters.
- Canonical response hashes, strong ETags, conditional `304` responses, cache
  headers, and gzip are covered by tests.
- No API object exposes an absolute source path.

### Command map

- Command defaults to the Mae Sai candidate dataset while Public and Studio
  retain their existing deliberately scoped fixture/evidence presentations.
- The map uses stable Leaflet layer groups, real Polygon/MultiPolygon
  reporting geometry, bounded regional roads, selected-area road detail,
  clustered facility candidates, modeled access points, and a persistent
  evidence drawer.
- Selection and map state survive language, filter, drawer, and scenario
  changes.
- The offline bundle requires no basemap or external request. A linked OSM
  attribution and the remaining source attribution stay visible without
  covering the evidence drawer at the required viewports.
- Facility and road language remains explicit: facilities are unverified
  open-context candidates and roads are modeled-risk candidates, not observed
  closures.

### Server scenarios

Only the closed server registry can create a scenario run. The current
candidate rehearsals produced these deterministic results from the accepted
graph manifest:

| Scenario | Baseline modeled 30-minute access loss | Scenario loss | Delta | FPPS recalculated |
|---|---:|---:|---:|---|
| Temporary facility candidate | 190 | 13 | -177 | No |
| Candidate edge disruption | 190 | 219 | +29 | No |

The client displays the paired server result and returned map effects. It does
not contain an access, equity, road-risk, or FPPS formula.

### Probability consequences and GeoAI boundary

- The segment/facility adapter validates immutable class-1 probability output,
  model/run identity, input receipts, CRS, transform, grid, bounds, nodata,
  class mapping, value range, geometry identity, and study-area identity.
- Cross-study-area, checksum, grid, geometry, eligibility, lineage, result, and
  signature substitutions fail closed.
- Nodata cannot become a closure or exposed facility by inference.
- The opt-in isolated GeoAI smoke executes outside the root environment. The
  root package imports without importing `geoai` or `torch`.
- The synthetic smoke is integration evidence only, not flood-accuracy
  evidence and not a decision-eligible Mae Sai raster.

## Final verification record

The following commands or repository-equivalent jobs were run against the
integrated tree on 18 July 2026:

| Verification | Exact result |
|---|---|
| `uv run pytest` | `1227 passed, 1 skipped in 197.93s` |
| `uv run --project services/api pytest services/api/tests -q` | `96 passed in 53.93s` |
| API/root Ruff scope | `All checks passed!` |
| GeoAI normal tests, smoke excluded | `84 passed, 1 deselected in 5.86s` |
| Opt-in real GeoAI smoke | `1 passed in 30.67s` |
| Root import isolation | `root_import=passed`, `geoai_imported=false`, `torch_imported=false` |
| Frontend ESLint | exit `0` |
| Frontend TypeScript check | exit `0` |
| Frontend Vitest | `14 files / 75 tests` |
| Next.js 16.2.6 production build | compiled; `6/6` static pages generated |
| Static offline smoke | `4` routes, `15` assets, zero external requests |
| Offline browser smoke | Public, Command, and Studio plus versioned service-worker cache; zero external requests |
| Live API browser smoke | 8 areas; 750 regional / 4,458 total roads; selected-area detail; 42 facilities; 8 access points; scenario deltas `-177` and `+29` synchronized |
| Six-viewport visual QA | `390x844`, `430x932`, `1024x768`, `1440x900`, `1536x1024`, and `2048x1152` passed with zero external requests |
| Controlled real-data gate audit | `gate_status=blocked`; `experiment_executed=false`; `can_feed_decision_layer=false` |

The production build emitted offline cache version `112bbc3b16ae`.

## External blockers retained by design

The current gate audit lists these independent blockers:

1. no externally signed product-specific authority decision and matching
   internal integrity receipt;
2. the candidate reference-mask licence, permitted ML/metric uses,
   redistribution status, qualification, and temporal alignment are unresolved;
3. no accepted blind reviewer-calibration and adjudication receipt;
4. no signed immutable holdout polygons and frozen cell-membership receipt;
5. no HMAC-signed internal integrity receipt for qualified reference-cell
   evidence; and
6. no signed predeclared promotion policy freezing experiment-specific metric,
   calibration, error-coverage, and selection criteria.

Completed three-model evidence is a post-execution output and is correctly
`Deferred`, not a pre-execution blocker. Until the six prerequisite evidence
groups pass, FloodGuard must not start the qualified comparison. After they
pass, a completed signed result is still required before any candidate can be
selected; separate decision-layer acceptance is required before a probability
raster can be promoted. Non-operational defaults remain unchanged throughout.

## Visual evidence

- `docs/visual-qa/proposal-stage/public-390x844.png`
- `docs/visual-qa/proposal-stage/public-map-430x932.png`
- `docs/visual-qa/proposal-stage/command-1024x768.png`
- `docs/visual-qa/proposal-stage/command-1440x900.png`
- `docs/visual-qa/proposal-stage/command-1536x1024.png`
- `docs/visual-qa/proposal-stage/studio-2048x1152.png`
