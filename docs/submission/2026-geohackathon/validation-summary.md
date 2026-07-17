# FloodGuard proposal-stage validation summary

## Overall decision

FloodGuard is ready to demonstrate its role-specific fixture application,
tested decision contracts, FastAPI artifact boundary, and isolated synthetic
GeoAI wiring. It is not ready to claim real flood-detection accuracy,
decision-eligible GeoAI output, official warning capability, or agency
operational status.

| Evidence lane | Current status | What it proves | What it does not prove |
|---|---|---|---|
| Decision engine | Implemented; final suite receipt pending | Deterministic FPPS, A-E class, road risk, nearest-facility access, equity, exports and dashboard logic | Accuracy of an upstream real flood product |
| Static web/PWA | Implemented; final visual/offline receipts pending | Three role-specific fixture routes and offline fallback | Live data, operational navigation or public warning |
| FastAPI | Implemented; final suite receipt pending | Pydantic artifact/scenario contracts, explicit data states and path safety | Production hosting or agency acceptance |
| GeoAI synthetic proof | Implemented; final opt-in smoke receipt pending | Actual tile export, model construction, tiled prediction, explicit class-1 probability, grid validation and report-only aggregation | Training convergence or real flood accuracy |
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

1. missing externally signed catalog/license authority receipt;
2. reference-mask permissions and qualification not confirmed;
3. reference temporal alignment not confirmed;
4. missing reviewer-calibration receipt;
5. missing signed spatial holdout and cell membership;
6. missing externally signed qualified reference cells; and
7. missing complete three-model evidence manifest.

No code or editable CSV may override these blockers.

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

## Final proposal verification still required

Exact suite counts are intentionally absent here. Before release, the team
must generate JUnit receipts for root, API, contract, frontend and normal GeoAI
tests; run the opt-in real GeoAI smoke; run offline browser smoke; build the
static web app; inspect all required screenshots; and update the checksummed
proposal evidence manifest. A stale historical count is not acceptable.
