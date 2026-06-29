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

Build the first testable policy-product slice:

- sample subdistrict priority fixture
- deterministic FPPS score
- A-E action class
- top reason
- confidence passthrough
- generated sample CSV
- passing tests

## Near-Term Decision

The project should continue with equity and access modules before remote-sensing model complexity. This preserves the differentiator: converting flood extent into access, equity, prioritization, and action.
