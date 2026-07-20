# FloodGuard proposal-stage validation summary

## Overall decision

FloodGuard is ready to demonstrate its role-specific fixture application,
tested decision contracts, FastAPI artifact boundary, and isolated synthetic
GeoAI wiring. It is not ready to claim real flood-detection accuracy,
decision-eligible GeoAI output, official warning capability, or agency
operational status.

| Evidence lane | Current status | What it proves | What it does not prove |
|---|---|---|---|
| Decision engine | Passed: 1,212 tests; 1 skipped | Deterministic FPPS, A-E class, road risk, nearest-facility access, equity, exports and dashboard logic | Accuracy of an upstream real flood product |
| Static web/PWA | Passed: lint, typecheck, 5 contract tests, 58 web-unit tests, static build, offline route/browser checks and six visual-QA viewports | Three role-specific fixture routes and offline fallback | Live data, operational navigation or public warning |
| FastAPI | Passed: 86 tests | Pydantic artifact/scenario contracts, explicit data states and path safety | Production hosting or agency acceptance |
| GeoAI synthetic proof | Passed: 84 normal tests plus 1 opt-in real-GeoAI smoke | Actual tile export, model construction, tiled prediction, explicit class-1 probability, grid validation and report-only aggregation | Training convergence or real flood accuracy |
| Trusted zonal adapter | Implemented and substitution-tested | Fail-closed official-input raster/geometry/checksum/statistics/receipt boundary | Acceptance of any current candidate raster |
| Mae Sai weak-reference analysis | Candidate screening evidence | A real-data engineering orientation and known failure modes | Official, field or qualified reference validation |
| Controlled three-model experiment | Blocked | Gate evaluation is functioning and honest | Comparative real-data metrics or model promotion |
| Agency pilot | Non-operational default | Bounded architecture, acceptance, identity/audit/retention controls in code/docs | Formal agency acceptance or production readiness |

## Synthetic GeoAI validation

The opt-in proof validates:

- GeoAI version `0.41.1` in isolated Python 3.12;
- eight ordered encoded bands and preprocessing sidecar lineage;
- feature/mask CRS, transform, dimensions, resolution and bounds;
- label values `0`, `1`, and `255` nodata;
- georeferenced training, holdout and rejected-boundary tile partitioning;
- U-Net construction with `encoder_weights=None`;
- one-band class-1 `flood_probability_0_1` output;
- finite probability values in `[0,1]`;
- provenance tags and checksum-bound input/model/manifest lineage; and
- report-only FloodGuard aggregation with decision eligibility false.

The proof currently records `training_execution=model_construction_only`.
Therefore the proposal must not claim completed training.

## Mae Sai evidence boundary

The repository contains checksum-tracked Sentinel-1 product evidence and a
manual cross-border weak-reference candidate used for non-operational
engineering metrics. The reference does not qualify as official/adjudicated
truth and does not overlap the authoritative Thailand ADM3 geometry used by
the planning brief. Existing threshold and weak-label metrics demonstrate
failure modes and the need for better reference evidence; they are not
promotion evidence.

The Mae Sai action brief remains Class E / low confidence and tells reviewers
to monitor and verify. Its road, access and vulnerability values are modeled
candidate context, not observed emergency impacts.

## Controlled three-model blockers

The current signed/checksummed gate receipt sets:

- `gate_status=blocked`;
- `experiment_executed=false`;
- `processing_allowed=false`;
- `can_feed_decision_layer=false`; and
- `official_warning=false`.

Blocking evidence includes:

1. missing externally signed product-specific authority decision and matching
   internal integrity receipt;
2. reference-mask permissions and qualification not confirmed;
3. reference temporal alignment not confirmed;
4. missing reviewer-calibration receipt;
5. missing signed spatial holdout and cell membership;
6. missing HMAC-signed internal integrity receipt for qualified reference
   cells; and
7. missing signed predeclared promotion policy.

The complete three-model evidence manifest is correctly deferred until the
pre-execution gates authorize a bounded run; it is not a circular prerequisite
for starting that run. It becomes mandatory before a report-only candidate
selection. No code or editable CSV may override either the prerequisites or
the post-execution evidence requirement.

## Required future metrics

When every gate passes, evaluate all three model lanes on the same frozen
spatial holdout and report:

- IoU;
- Dice/F1;
- precision;
- recall;
- physical area error and finite area-error ratio;
- Brier score;
- calibration / expected calibration error;
- threshold sensitivity; and
- named error-category counts and examples.

The zero-division convention and cell-area calculation remain the controlled
experiment contract, not a presentation-layer choice.

## Verification receipt and remaining release blockers

The machine-readable test receipt is bound to tested source commit
`62a4336759de55116b1bd238a5afd60ca7496895`. It records 1,212 root Python
passes with one explicit skip, 86 API passes, 5 contract passes, 58 web-unit
passes, a passed full frontend/offline gate, 84 normal isolated-runner passes,
and one passed opt-in real-GeoAI smoke. The static build and browser smoke made
zero external runtime requests, and all six required viewports passed the
automated overflow, map-control, Thai, focus, disclosure and private-path
checks.

Submission release remains blocked until owner-supplied team/contact facts,
the deployed demo URL, verified portal constraints, the final source-derived
proposal PDF, and the release tag are present. These blockers do not invalidate
the tested proposal-stage software candidate, but they prevent a truthful final
submission build.
