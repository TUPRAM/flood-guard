# FloodGuard Thailand Plans

## Build Order

1. Repository scaffold and durable project contracts.
2. Flood Preparedness Priority Score engine.
3. Evacuation Equity Gap engine.
4. Road-disruption probability prototype.
5. Access-loss prototype.
6. Dashboard-ready CSV and GeoJSON exports.
7. Static dashboard or map demo.
8. Validation report generator.
9. One-page action brief generator.
10. Sentinel-1/GISTDA flood ingestion and validation path.

## Current Milestone

Deliver the competition-ready role-specific platform without weakening the tested policy engine:

- versioned shared schemas and drift tests
- `/public`, `/command`, and `/studio` responsive PWA surfaces
- offline judging bundle with explicit fixture/non-operational status
- FastAPI artifact and server-owned deterministic scenario boundary
- isolated, optional GeoAI 0.41.1 runner with fail-closed promotion gates
- full Python, frontend, API, schema, offline, and visual verification

The proposal role-surface UX pass is implemented. Its durable interaction,
safety, verification, and next-milestone decisions are recorded in
`docs/role-surface-development-plan.md`.

## Near-Term Decision

The decision engine remains the source of truth. The next evidence milestone is not broader UI scope: it is clearing real-input provenance and reference-mask gates, running a spatial-holdout baseline/weak-label/GeoAI comparison, and independently reviewing calibration and geographic transfer before any candidate can feed the decision layer.
