# Weak-reference Plans 1-9 implementation status

## Decision

This receipt records what FloodGuard can substantiate for the requested
weak-reference Plans 1-9. It replaces checklist completion based only on file
presence with evidence-based status.

This is an engineering status receipt, not source authority, legal permission,
reference qualification, reviewer acceptance, or an operational promotion
decision. Those decisions require the external evidence and named human or
agency approvals listed below.

All outputs in this lane remain:

- `dataset_mode=candidate`;
- `operational_status=non_operational`;
- `official_warning=false`;
- not official validation;
- not field validated; and
- not an emergency warning.

The active Mae Sai reference polygon is not inside the eight Thailand ADM3
candidate reporting geometries. It is nearby cross-border calibration evidence
only. Candidate metrics against it must never be described as Mae Sai Thailand
accuracy.

## Plan status

| Plan | Implemented result | Evidence boundary | Status |
|---|---|---|---|
| 1. Manual weak-reference mask | GeoPackage attributes, layer, geometry, checksum, required values, `not_official`, and spatial relation are validated | One valid MultiPolygon feature with four components is 5.965378 km from the Thailand ADM3 candidate geometry and has no overlap | **Candidate calibration ready; in-area Mae Sai reference still missing** |
| 2. Real Sentinel-1 deterministic baseline | Active source selection uses the checksum-bound same-track original SAFE pair; hashes are verified before GDAL access and PAM writes are disabled | Metrics are cross-border calibration only; original archives remain outside Git | **Implemented and reproducible in candidate scope** |
| 3. Validation report V3 | Product IDs, hashes, mask metadata, assumptions, metrics, failure modes, spatial scope, and safety boundaries are rendered | Official metrics remain blocked | **Implemented** |
| 4. Flood-to-decision bridge | Sentinel-1 candidate probabilities aggregate to eight HDX COD-AB ADM3 candidate units and feed the unchanged FPPS engine with open context | Calibration reference does not validate the Thailand-area probabilities; all outputs remain low-confidence candidates | **Implemented as non-operational candidate evidence** |
| 5. Dataset-mode dashboard | Fixture, Mae Sai weak-reference candidate, and metadata/blocker modes are separate; real-coordinate roads, facilities, access points, provenance, metrics, and briefs are embedded offline | No mode is an official warning; candidate scenarios remain separately governed | **Implemented** |
| 6. Open context | WorldPop, HDX COD-AB, Geofabrik OSM, and Copernicus DEM sources remain outside Git and are checksum-tracked | Boundaries, facilities, modeled population, and modeled consequences still need authority/field confirmation | **Implemented for open-context analysis** |
| 7. First small ML experiment | Historical logistic/spatial-holdout outputs are retained and permanently ineligible for the decision layer | The historical run used the retired COG pair. A current-pair run is blocked because the manual reference records `unqualified_ml_label_allowed=false` | **Historical evidence retained; new run correctly blocked** |
| 8. Mae Sai action brief | A bilingual brief is generated for the current highest-priority candidate unit, Ko Chang (`TH570903`), from the active source lineage and real context | Planning/demo only; roads, facilities, access, equity, and flood evidence are modeled candidates | **Implemented** |
| 9. Hat Yai / Songkhla story tile | A self-hashed readiness receipt locks a same-platform 12-day original-SAFE pair at metadata level and exposes exact blockers | Source assets, checksums, grid validation, reference rights/mask, metrics, decisions, and story mode are absent | **Fail-closed foundation implemented; experiment and story remain blocked** |

## Source-integrity correction

The earlier Mae Sai September 6 / September 15 COG pair was not safe to retain
as the active baseline:

- it mixed different acquisition tracks;
- the COG conversion has a calibration warning in the inspected processing
  path; and
- GDAL PAM metadata had changed the local ZIP bytes after the recorded hashes,
  invalidating the old receipt.

The retired COG identifiers remain in provenance documentation only. Active
processing accepts only:

- pre-event original SAFE `aaaef3af-fa49-4115-bf0f-f54175e7aedf`, SHA-256
  `42433d6cfb55118abe21e6faabef56343cefc9f28817cd31eb9386d32f56543d`;
- post-event original SAFE `5251b74b-0bbd-4365-9eb4-fa33292e175a`, SHA-256
  `ff4a604f57c9eb88421904659c7201d07b54b35a3bff6f3447ee548c40f6755b`; and
- manual reference `MS-MANUAL-CROSSBORDER-001`, SHA-256
  `d64e8441dd08ce42323ae283398e5dc1a7225282caa040d0f5981b3a9c8637ce`.

The active GDAL view exposes Sentinel-1 uncalibrated amplitude. FloodGuard
therefore records `sentinel1_uncalibrated_amplitude`, applies
`20_log10_amplitude` explicitly, and marks the result
`not_sigma0_beta0_or_gamma0_calibrated`; it does not present these values as
calibrated backscatter.

The unit tests mutate the bytes of each checksum-bound pre-event archive,
post-event archive, and reference file in turn and verify rejection before a
SAFE band or reference geometry is opened. Separate identity tests reject the
retired COG product IDs. This demonstrates the tested pre-read checksum and
identity guards; it does not make external storage immutable, grant source
authority, or eliminate filesystem race conditions outside the bounded run.
Raster opens run with `GDAL_PAM_ENABLED=NO` so the tested read path does not
write PAM sidecars into source archives.

## Active cross-border calibration metrics

The deterministic threshold baseline currently records:

| Metric | Value |
|---|---:|
| IoU | 0.086835 |
| F1 / Dice | 0.159795 |
| Precision | 0.188113 |
| Recall | 0.138887 |
| Area error ratio | -0.261687 |
| Sample pixels | 65,536 |
| Reference-positive pixels | 12,557 |
| Predicted-positive pixels | 9,271 |

These low values are useful engineering evidence: they show that the current
threshold method substantially under-detects this manual polygon. They are not
a claim about flood-detection accuracy inside Mae Sai, model fitness, or
operational readiness.

## Hat Yai locked metadata pair

- Pre-event: `4e473302-943c-4798-8bfc-8287167792ed`, 11 November 2025.
- Post-event: `d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc`, 23 November 2025.
- State: `locked_metadata_only`.
- `processing_allowed=false`.
- `candidate_metrics_available=false`.
- `decision_outputs_available=false`.
- `dashboard_story_available=false`.
- `can_feed_decision_layer=false`.

The static dashboard shows this receipt only as blocked data-library readiness;
it does not expose a Hat Yai flood story or decision layer.

## Outstanding external evidence and authority gates

1. A named data owner or authorized provider must supply or approve an in-area
   Mae Sai reference and document local analysis, validation, derived-reporting,
   ML-label, and redistribution permissions.
2. Qualified reviewers must complete blind calibration and adjudication, then
   sign the immutable non-overlapping train, calibration, and final-holdout
   membership receipts before any new model comparison.
3. An authorized operator must acquire and checksum the locked Hat Yai source
   pair outside Git, validate its footprint/grid, and bind it to a legally
   usable reference before metrics or a story tile can be generated.
