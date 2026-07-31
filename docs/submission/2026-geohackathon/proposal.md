# FloodGuard Thailand

## From Flood Pixels to Equitable Local Action

**GeoHackathon 2026 project proposal**  
**Theme:** Pixel to Policy - Unlocking Insights, Accelerating Impact  
**Proposal-stage demonstration:** Chiang Rai / Mae Sai 2024 candidate evidence  
**Future transfer and stress test:** Hat Yai / Songkhla

> Thailand can already see floodwater from space. FloodGuard addresses the
> next decision: who may become cut off from help, whether access loss is
> unequal, and where limited preparedness resources should be checked first.

FloodGuard Thailand is a geospatial decision-support platform for flood
preparedness and rapid post-event prioritization. It is not an official warning
system, guaranteed real-time detector, or live evacuation navigator. Its
proposal-stage outputs are fixture or candidate evidence, are explicitly
non-operational, and set `official_warning=false`.

## 1. Problem clarity and Thai relevance

Flood maps answer where water may be present. Local authorities must also
understand which communities may lose access to hospitals, shelters, and major
roads; which road or bridge creates the greatest isolation; whether access loss
falls disproportionately on residents with fewer mobility options; and which
areas need field verification first.

FloodGuard converts a time-stamped flood extent or probability layer into:

- exposed population and facilities;
- likely road disruption;
- nearest-facility shortest-path access loss at configured time thresholds;
- an Evacuation Equity Gap comparing vulnerable and non-vulnerable access-loss
  rates;
- a transparent Flood Preparedness Priority Score (FPPS);
- an A-E recommended action class; and
- an evidence-backed bilingual action brief.

The proposal uses Mae Sai 2024 as a bounded candidate/demo story because the
repository contains checksum-tracked Sentinel-1 and open-context derivatives,
a weak-reference analysis, and explicit gate receipts. These assets support a
non-operational engineering demonstration, not official accuracy validation.
Hat Yai is a future transfer and urban stress-test location; FloodGuard does not
claim that a completed Hat Yai model or decision validation exists.

Primary institutional users are GISTDA, DDPM and provincial disaster offices,
municipalities, health services, and road agencies. Residents and community
groups receive a separate Thai-first preparedness view with simpler language.

## 2. Decision method and novelty

FloodGuard adds the decision chain after the flood layer:

```text
flood probability or extent
  -> exposed people and facilities
  -> likely road disruption
  -> normal versus disrupted access
  -> Evacuation Equity Gap
  -> FPPS and A-E action class
  -> confidence, assumptions, provenance and bilingual brief
```

The default FPPS remains transparent and tested:

```text
0.30 flood likelihood
+ 0.25 exposure
+ 0.20 access gap
+ 0.15 road criticality
+ 0.10 vulnerability/context
```

Each component is normalized to 0-100. The five action classes are A - Protect
Lives Now, B - Keep Routes Open, C - Protect Essential Services, D - Build
Resilience, and E - Monitor and Verify. A class is planning guidance, not an
automated order.

The Evacuation Equity Gap is a distributional statistic. It divides the
vulnerable-group access-loss rate by the non-vulnerable-group access-loss rate
and is always presented with its population definition, confidence,
assumptions, and source timestamp. It is not a general claim that an area or
community is equitable or inequitable.

## 3. Sound GeoAI approach

FloodGuard uses `opengeos/geoai` as an upstream probability engine while the
existing tested FloodGuard package owns road risk, access, equity, scoring, and
promotion decisions.

The isolated Python 3.12 runner pins `geoai-py==0.41.1`. The current opt-in
synthetic smoke exercises the real GeoAI tile exporter, constructs a two-class
U-Net with `encoder_weights=None`, packages a checksum-bound model state, calls
the real tiled GeoAI predictor, explicitly extracts class-1 probability, and
validates the output raster. The repository also contains a guarded wrapper for
`train_segmentation_model`; an executed optimization/training run is not
claimed by the current proof.

The candidate feature contract contains eight ordered bands:

1. pre-event VV in dB;
2. post-event VV in dB;
3. pre-event VH in dB;
4. post-event VH in dB;
5. VV change in dB;
6. VH change in dB;
7. slope in degrees; and
8. permanent-water flag.

Raw SAR and terrain values never pass through an implicit `/255` transform.
FloodGuard clips each physical band to a documented range, encodes it to
`uint8 [0,255]`, and binds the ordered transformations in a SHA-256 sidecar.
Training and inference re-hash the same sidecar. Feature and mask grids must
match in CRS, transform, resolution, bounds, dimensions, class mapping, and
nodata semantics.

The synthetic proof also demonstrates:

- georeferenced training and holdout tile partitioning;
- rejection of boundary-crossing or unassigned tiles;
- explicit `0 = non-flood`, `1 = flood`, `255 = nodata` label handling;
- one-band `float32` `flood_probability_0_1` output;
- finite `[0,1]` probability-range validation;
- model, feature, mask, manifest, and preprocessing lineage checks; and
- report-only aggregation into FloodGuard without decision-layer promotion.

For a future decision-eligible official input, the trusted probability-raster
zonal adapter independently snapshots and hashes the raster and authoritative
area geometry, validates spatial and lineage contracts, derives zonal
statistics, and writes a canonical HMAC-SHA256 receipt. Candidate and fixture
inputs are rejected. Substitution, mutation, wrong-key, private-path,
geometry-order, and coordinated read/restore race tests exercise this boundary.
No current candidate raster is claimed to have passed the official-input gate.

`geoai.water.segment_water` is not used as the Sentinel-1 event-flood model;
permanent water is not equivalent to event inundation.

## 4. Controlled model evaluation

The post-selection experiment will compare:

1. deterministic Sentinel-1 pre/post SAR change baseline;
2. weak-label logistic model; and
3. GeoAI U-Net/FPN candidate.

Evaluation will use immutable spatial holdout polygons rather than only random
pixels. Required measures are IoU, Dice/F1, precision, recall, physical area
error and area-error ratio, Brier score, calibration, and documented error
categories including permanent water, paddy fields, steep terrain, radar
shadow/layover, urban double-bounce, mixed pixels, and timing mismatch.

The controlled real-data experiment is currently blocked. The repository has
verified Sentinel-1 product bytes, but still lacks an externally signed
product-specific authority decision plus matching internal integrity receipt,
a qualified reference mask authorized for the model purpose, passing
reviewer-calibration evidence, signed immutable spatial holdout membership,
an internal integrity receipt for qualified reference cells, and a signed
predeclared promotion policy. Complete three-model evidence is deferred until
those pre-execution gates authorize the bounded run. Therefore no real
three-model result or performance claim appears in this proposal.

Existing weak-reference candidate metrics are screening evidence only and are
not substituted for the controlled experiment, official validation, field
validation, or model promotion.

## 5. Product: one platform, three role-specific surfaces

### Public preparedness PWA

- Thai-first mobile experience with an English switch;
- plain-language status, timestamp, confidence, source, and assumptions;
- preparation guidance and official hotline links;
- shelter/facility information where its status is confirmed;
- route examples labeled as preparedness rehearsal; and
- cached/offline snapshots visibly labeled stale and non-operational.

### Government command center

- map-first A-E area ranking and filters;
- flood, road, facility, access, and equity evidence;
- selected-area FPPS components and top reason;
- server-defined deterministic scenario comparison;
- provenance, confidence, assumptions, and source time; and
- bilingual brief and filtered GeoJSON download.

### Research and developer studio

- data-gate status and exact blocked reasons;
- GeoAI environment, feature, model, and run receipts;
- tile/preprocessing/probability evidence;
- validation and error-category summaries;
- explicit `processing_allowed` and `can_feed_decision_layer`; and
- no public emergency actions or private local paths.

The static web application defaults to a committed fixture bundle. It can load
all three routes without FastAPI, GeoAI, external tiles, analytics, third-party
fonts, or network calls. The FastAPI service remains a tested contract layer
for artifact and deterministic scenario access. The legacy static dashboard is
retained as another reproducible fallback.

## 6. Backend, contracts, and operational honesty

The FastAPI service exposes versioned Pydantic responses for health, status,
study areas, areas, layers, briefs, scenarios, model runs, and data readiness.
Health is separate from data freshness: a healthy process can report stale,
blocked, or unavailable artifacts. Scenario IDs and parameter ranges are
server-owned, and the frontend contains no alternative scoring formula.

Shared schemas require dataset mode, operational status, source timestamp,
generation time, confidence, source name, assumptions, official-warning state,
data version, and Git commit. Fixture and candidate objects set
`official_warning=false`. API safety checks reject private absolute paths.

The access method is nearest-facility shortest-path threshold access. A
capacity-aware 2SFCA extension is future work after trustworthy capacity and
service-area data become available.

## 7. Feasibility for a three-person team

The three complementary responsibilities are:

- product, UI, frontend, accessibility, and visual integration;
- backend, platform, contracts, evidence, CI, and release packaging; and
- geospatial engineering, GeoAI, validation, and data governance.

The proposal-stage scope deliberately reuses the existing Next.js application,
FastAPI service, contracts package, tested FloodGuard domain package, isolated
GeoAI runner, and fixture artifacts. It does not require a native application,
GPU service, production identity provider, live feed, or real-data training.

Proposal-stage deliverables are the role-specific static demo, offline bundle,
tested API and decision engine, synthetic GeoAI integration proof, model card,
validation summary, bilingual brief, and checksummed evidence manifest.

## 8. Governance, ethics, and uncertainty

- Personal vulnerability records are not displayed; decision outputs are
  aggregated.
- Fixture, candidate, and official-input modes remain visibly different.
- FloodGuard defers to official Thai warning and disaster-management agencies.
- Every decision artifact carries source time, confidence, and assumptions.
- Model and data promotion is fail-closed.
- High-impact and uncertain areas are prioritized for human verification.
- Thai public language avoids unsupported live, safe-route, or evacuation
  claims.
- Large inputs, model weights, and restricted source files remain outside Git.

## 9. Expected impact

FloodGuard is designed to help authorities and communities move from imagery
to transparent preparedness decisions: prioritize field checks, identify road
links that create isolation, compare bounded shelter or road scenarios,
protect continuity of access to essential services, and target preparedness
support where modeled access loss is greatest.

The technical-to-policy bridge is visible without claiming operational
authority: a validated probability input changes area-level exposure and
access evidence; FloodGuard explains how that evidence affects an FPPS
component, action class, and planning brief; provenance and blocked gates remain
visible throughout.

## 10. Development after proposal selection

### Finalist foundation

Harden reproducible release manifests, hosted frontend/API architecture,
identity and roles, auditable retention, deployment monitoring, and the offline
fallback.

### Qualified three-model experiment

Obtain licensed/product-identified inputs and qualified reference evidence,
freeze spatial holdouts, execute the three lanes, report all required metrics
and error categories, and promote no result that misses the predetermined
gates.

### Bounded agency pilot

Add external identity, signed manifests, append-only audit evidence, governed
artifact retention, bilingual acceptance criteria, and a field-validation
protocol. Remain non-operational until formal agency acceptance exists.

## One-paragraph pitch

Thailand can already see floodwater from space. The harder question is who may
become cut off from help, whether access loss falls disproportionately on those
with fewer mobility options, and where limited preparedness resources should
be checked first. FloodGuard Thailand uses an isolated, reproducible GeoAI
workflow to produce a provenance-bound candidate flood-probability layer, then
converts trustworthy inputs into road disruption, shelter and healthcare
access loss, an Evacuation Equity Gap, and an explainable subdistrict action
priority. A Thai-first public preparedness view, government command center, and
transparent model studio communicate the same evidence at the right level of
detail. FloodGuard moves from pixels to policy while remaining non-operational,
uncertainty-aware, and explicitly complementary to official Thai agencies.

## References

1. GISTDA. GeoHackathon 2026 competition announcement and official brief.
2. OpenGeoAI. `opengeos/geoai`, package version 0.41.1 and source documentation.
3. FloodGuard Thailand. `TUPRAM/flood-guard` repository and proposal evidence
   manifest.
4. Copernicus Data Space Ecosystem. Sentinel-1 mission, OData API, and data-use
   terms.
5. Bonafilia et al. Sen1Floods11 georeferenced Sentinel-1 flood dataset.
6. Nobre et al. Height Above the Nearest Drainage.
7. WorldPop. Thailand population products.
8. OpenStreetMap contributors and OpenStreetMap Foundation. ODbL data.
