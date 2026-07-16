# ADR 0001: Role-specific PWA and isolated GeoAI runner

- Status: Accepted
- Date: 2026-07-16
- Decision owners: FloodGuard Thailand maintainers

## Context

FloodGuard already has a tested Python decision engine for flood aggregation,
road disruption, nearest-facility access loss, equity analysis, FPPS scoring,
exports, and a reproducible static dashboard. The competition rework needs to
serve three audiences whose information needs and safety boundaries differ:

- citizens need a mobile-first preparedness view with plain bilingual copy;
- government users need a map-first command view with dense decision evidence;
- researchers need data gates, model cards, validation, and blocked reasons.

The current access implementation compares shortest travel time to the nearest
eligible facility against configured thresholds. It is not a complete 2SFCA
implementation and must not be described as one.

The proposed `opengeos/geoai` integration has a much larger Python, geospatial,
and ML dependency surface than the FloodGuard core. It also consumes
checksum-tracked external rasters and writes model weights and large raster
outputs that do not belong in Git. Model execution must not weaken FloodGuard's
licensing, reference-mask, timing, product-ID, checksum, provenance, or
promotion gates.

## Decision

Use one shared responsive Next.js PWA with three role-specific routes:
`/public`, `/command`, and `/studio`. Share visual primitives, bilingual content
keys, typed contracts, and a local offline bundle, while keeping the information
architecture and available controls specific to each role.

Keep `src/floodguard` as the domain engine. Add a FastAPI service as a typed,
sanitized boundary around generated artifacts and approved deterministic
scenarios. Artifact readers validate content, not only file existence, and map
malformed evidence to explicit unavailable/blocked states without changing
service-health reporting. Preserve the existing static dashboard as a
reproducible fallback.

When the API succeeds, the browser may persist one path-sanitized last-known
snapshot. A later API failure marks that snapshot stale/offline and disables
scenario execution. If no valid cached snapshot exists, the application uses
the committed fixture bundle and identifies it as a bundled fixture rather
than mislabelling it as last-known operational data.

Run GeoAI only from `services/geoai-runner`, with its own Python 3.12 project,
lockfile, and pinned `geoai-py==0.41.1`. The root FloodGuard environment must
remain importable and testable without GeoAI, PyTorch, a GPU, network access, or
large binary fixtures. Communication across this boundary uses validated,
redacted manifests and external-workspace artifacts, not Python imports from the
root package.

JSON Schema is the source of truth for versioned API payloads. The
`@floodguard/contracts` package exposes corresponding TypeScript types and
runtime enum constants. Contract drift tests validate examples and ensure the
shared common fields and enum values remain aligned.

## Safety and operational boundary

FloodGuard is preparedness and planning decision support. Fixture and candidate
data are non-operational, are never official warnings, and must be visibly
labelled with source time, confidence, and assumptions. The product is not a
guaranteed real-time detector, an official warning system, or a live evacuation
navigator.

GeoAI produces an upstream candidate flood-probability artifact. It does not
own road-risk, access-loss, equity, FPPS, action-class, or public-action logic.
Candidate and blocked model outputs may be summarized for research reporting
only when that mode is explicitly requested. They cannot be marked eligible for
the decision layer. Promotion requires both `processing_allowed=true` and
`can_feed_decision_layer=true` on an official-input run after all underlying
gates and output checks pass. Those flags are necessary but not sufficient at
the current integration boundary: `aggregate_probability_cells` accepts a
caller-supplied iterable and therefore cannot independently prove that the
values came from the receipt-bound raster or the named area's zonal mask. It
remains report-only and rejects promotion even for a schema-complete receipt.
A future trusted raster-and-zonal extraction adapter must read and hash the
raster bytes itself, apply the authoritative area geometry, and bind the
selected cells to that receipt before any model output can feed FPPS.

## Alternatives considered

### Separate native mobile and desktop applications

Rejected for the competition scope. It would duplicate contracts, state,
accessibility work, offline behavior, and release pipelines without improving
the tested decision engine. A responsive PWA covers the required viewports and
can later coexist with a native client if agency requirements justify one.

### One dashboard with role-based hiding

Rejected. The public surface is not a smaller command dashboard, and the studio
surface must expose research evidence without leaking experimental controls or
private paths into citizen workflows. Explicit routes make these boundaries
testable.

### Install GeoAI in the root Python project

Rejected. It would make routine tests and core imports depend on a large,
platform-sensitive ML stack, blur the model/decision boundary, and increase the
risk of accidental real-data execution.

### Reimplement the decision engine in TypeScript

Rejected. It would duplicate tested safety-critical formulas and create drift.
Scenarios and decision outputs remain server-owned and deterministic.

## Consequences

Positive consequences:

- one deployable web application can serve all roles and viewports;
- core tests remain fast, offline, and independent of GeoAI;
- typed payloads make provenance and non-operational status mandatory;
- model outputs cross a fail-closed, reviewable promotion boundary;
- the static dashboard remains available if the new services are unavailable.

Trade-offs:

- local development has multiple runtimes and lockfiles;
- schema/type drift tests and example maintenance become required work;
- offline judging requires committed, small, locally served map and data assets;
- production agency use still needs authentication, authorization, audit logs,
  signed manifests, retention policy, monitored feeds, and approved wording.

## Verification

The decision is upheld when root tests run without GeoAI installed, all schema
examples validate, TypeScript constants match schema enums, candidate warning
claims are rejected, candidate/blocked probability summaries are report-only,
and all three web routes work without external network calls in judging mode.
