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
gates and output checks pass. Those flags are necessary but not sufficient for
`aggregate_probability_cells`: that function accepts a caller-supplied iterable
and therefore cannot independently prove that the values came from the
receipt-bound raster or the named area's zonal mask. It remains report-only and
rejects promotion even for a schema-complete receipt.

Decision-eligible aggregation instead uses
`floodguard.trusted_zonal_adapter`. The adapter opens a verified raster source
descriptor once, hashes its bytes while copying them to a private temporary
snapshot, and makes rasterio parse that snapshot rather than reopening the
mutable source path. It likewise parses authoritative GeoJSON from the exact
in-memory byte buffer used for its checksum. This prevents a
substitute-read-restore race from producing statistics for bytes other than
those named by the signed hashes. The adapter binds the actual
CRS/grid/nodata metadata to the model-run receipt, validates and reprojects
non-overlapping administrative polygons, derives cells with a fixed
pixel-centre rule, and emits deterministic zonal statistics in a canonical
HMAC-SHA256 receipt. The signing key is supplied externally and is never
serialized. Downstream consumers must verify the signature, key ID, complete
model/raster lineage, geometry receipt, and statistic consistency before the
result may feed FPPS. Fixture and candidate sources remain blocked from this
path. GeoPackage input is intentionally not claimed in the root dependency
profile because no vector GPKG reader is required by or installed for normal
FloodGuard tests.

The non-interactive entry point is:

```text
python -m floodguard.trusted_zonal_cli \
  --probability-raster <probability.tif> \
  --authoritative-geometry <areas.geojson> \
  --model-run-manifest <model-run.json> \
  --probability-raster-receipt <raster-receipt.json> \
  --authoritative-geometry-receipt <geometry-receipt.json> \
  --output <external-workspace/receipt.json> \
  --key-id <managed-key-id> \
  --generated-at <RFC-3339-time>
```

The HMAC key is never accepted on the command line. The CLI reads a
hex-encoded key of at least 32 bytes from
`FLOODGUARD_ZONAL_SIGNING_KEY_HEX` (or an explicitly named environment
variable), writes only outside the repository, and uses exclusive creation so
an existing receipt is never overwritten. Its stdout receipt evidence contains
only the canonical output hash, non-secret signing key ID, and area count; no input or
output path is emitted. Model-run, probability-raster, and authoritative-
geometry receipt JSON is read from one regular non-symlink descriptor per
file; parsing consumes the exact in-memory bytes captured from that descriptor.
Descriptor size/modification metadata is checked across the read, duplicate or
non-finite JSON is rejected, and receipt content containing private absolute
paths is rejected. The CLI never performs a path check followed by a separate
`read_text` reopen.

HMAC provides integrity and shared-secret authentication, not public-key
non-repudiation: any holder of the secret can create a valid receipt. A bounded
pilot must therefore keep the secret in an external secret manager, restrict
which runtime identity can access it, rotate key IDs, retain audit evidence for
each use, and replace or augment HMAC with agency-managed asymmetric signing if
legal non-repudiation becomes an acceptance requirement. The adapter requires
`dataset_mode=official_input` and complete `can_feed_decision_layer=true`
evidence because signing cannot repair missing licences, product identity,
reference-mask qualification, spatial validation, or other upstream gates.

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
