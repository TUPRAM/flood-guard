# Controlled three-model experiment operator runbook

Status: **fail-closed preparation workflow**. This runbook does not grant data
rights, qualify reference truth, appoint reviewers, authorize an operational
model, or publish real-event performance by itself.

FloodGuard remains `non_operational`, `official_warning=false`, and
`can_feed_decision_layer=false`. Do not run a real model lane until the signed
pre-execution gate and a separate bounded execution authorization both verify.

## Current stop condition

The controlled experiment is blocked. The repository has product-identified,
checksum-tracked pre/post Sentinel-1 SAFE archives, but it does **not** have:

- an attributable authority decision covering every intended use of the event
  reference source and its derived raster;
- a qualified, immutable single-band binary event-reference raster;
- passing blind reviewer calibration plus completed independent adjudication;
- signed error-strata evidence and qualified reference cells;
- frozen non-overlapping `train`, `calibration`, and `final_holdout` polygons
  and complete cell membership;
- a signed experiment-specific promotion policy and execution authorization;
- three completed, receipt-bound model lanes.

Therefore the correct current action is to maintain blocked evidence and
practice only with synthetic or explicitly weak-reference data. Do not produce
or publish qualified IoU, Dice/F1, precision, recall, area error, Brier score,
calibration, or champion claims from the current candidate geometry.

## Non-negotiable artifact boundary

`MBRSC_THAILAND_FLOOD-MAP-SHP.zip` is a checksummed vector reference candidate
and provider-provenance artifact. It is **not** the executable `reference_mask`
accepted by the controlled experiment.

The `reference_mask` acquisition role must bind a different artifact: the final
qualified, immutable single-band georeferenced raster used for evaluation. It
must:

- use exactly `0` for non-flood and `1` for flood;
- declare finite nodata distinct from `0` and `1`;
- exactly match the frozen projected equal-area CRS;
- cover every frozen analysis-cell centre without implicit reprojection;
- carry its own stable product/version ID, observation interval, filename, and
  SHA-256;
- be derived only after source rights and scientific review permit that use.

Rasterizing or adjudicating the provider vector creates new bytes and therefore
a new checksum. Never copy the vector ZIP checksum onto the derived raster.
Keep the provider ZIP outside Git and retain its checksum in the licensing
record as provenance only.

## Receipt roles and trust boundary

The workflow requires distinct signing identities and distinct credential
bytes for independent roles. Acquisition has two separate trust functions:

- an **external authority** signs the completed product-specific decision with
  Ed25519; this is the only signature that can evidence licensing authority or
  qualification;
- an **internal receipt custodian** signs the FloodGuard acquisition receipt
  with HMAC-SHA256 after the external decision, detached signature, public key,
  exact artifacts, and evidence bytes verify. This HMAC proves internal receipt
  integrity only and cannot grant rights or qualify reference truth.

The remaining independent roles are:

1. reviewer authority;
2. adjudicator;
3. spatial-holdout authority;
4. reference-cell authority;
5. model-promotion policy authority;
6. bounded execution authority;
7. model executor (prefer one identity per lane);
8. comparison-result authority;
9. promotion-recommendation authority.

For internal HMAC receipts, pass trusted verification keys as repeated
`--trusted-key KEY_ID=ENVIRONMENT_VARIABLE` arguments. Pass a new receipt's
signing identity with its explicit `--signing-key-id` and
`--signing-key-env` arguments. For the external acquisition decision, pass the
public verification key as
`--trusted-external-authority-key KEY_ID=PUBLIC_KEY_PATH`; the key ID must equal
`authorized_signer.signing_key_id` in the completed decision. Do not reuse one
secret under different key IDs. Keep all secret values outside Git.

Repository-internal receipts use HMAC-SHA256 for controlled-environment
integrity. HMAC does not provide public non-repudiation and is not proof that a
provider or agency granted rights. The acquisition issuer therefore additionally
requires a detached Ed25519 signature over the completed external decision and
a runtime-trusted public key. Preserve original provider correspondence,
identity evidence, detached signature, and public-key custody record.

## Required evidence order

The order is deliberate and must not be rearranged:

1. Obtain attributable licensing/authority evidence for the exact pre-event
   SAFE, post-event SAFE, provider reference source, and intended qualified
   binary raster.
2. Create and externally qualify the immutable binary event-reference raster;
   update the acquisition manifest with its real product identity and checksum.
3. Issue the acquisition-authority receipt over the exact three executable
   input artifacts and their catalog/licence evidence.
4. Freeze a model-independent blind calibration release.
5. Collect two independent model-hidden reviewer returns; independently
   adjudicate every disagreement; retain failed attempts and any fresh retest.
6. Dual-sign the reviewer-qualification receipt and its complete error-strata
   evidence.
7. Freeze non-overlapping `train`, `calibration`, and `final_holdout` polygons,
   grid contract, and exact cell membership.
8. Derive signed full reference cells plus a separate calibration-only
   projection directly from the qualified raster.
9. Sign the experiment-specific promotion policy before model results exist.
10. Run the pre-execution audit. It verifies prerequisites; completed model
    evidence is informational and is not required for readiness.
11. Issue a separate expiry-bound execution authorization.
12. For each model, train on `train`, generate calibration predictions, and
    select/sign the threshold using only the calibration projection.
13. After threshold signing, run final inference once on `final_holdout`; sign
    the model-run receipt and runtime evidence.
14. Compare the three identically scoped lanes and sign the report-only result.
15. Apply the predeclared policy and sign either `candidate_selected` or
    `no_candidate_qualified`.

No receipt in this chain permits an official warning or automatically promotes
a probability raster into FPPS.

## 1. Clear rights and qualify the raster

Start from the non-authorizing questionnaire
`docs/controlled-experiment/external_authority_decision_request.template.json`,
then transfer only attributable completed evidence into the exact executable
shape in
`docs/controlled-experiment/external_authority_completed_decision.template.json`.
The request file is deliberately not accepted by the receipt issuer. The
completed template is also non-authorizing while it contains placeholders or
lacks a valid detached signature. Use `docs/reference_mask_licensing_log.md` as
the evidence ledger. An attributable authority decision
must cover, at minimum:

- local analysis and retention;
- use as model input and supervised ML labels;
- validation and metric calculation;
- derived reports, tables, charts, and calibration/error analyses;
- screenshots and demonstration display;
- source redistribution, derived redistribution, or explicit reference-only
  storage;
- required attribution, citation, disclaimer, and expiry;
- signer identity and the basis of their authority.

Licensing and scientific qualification are separate. After rights are clear,
the Reference Authority must define how candidate geometry, contextual evidence,
reviewer decisions, uncertainty, and adjudication produce the binary raster.
The completed raster must pass CRS, class, nodata, coverage, timing, and checksum
inspection before the manifest row changes from pending to qualified.

The completed decision must contain exactly the three executable roles in the
final acquisition manifest: `pre_event_sar`, `post_event_sar`, and
`reference_mask`. Copy each manifest-bound value exactly and hash the exact
catalog, licence, artifact, signer-identity, and public-key bytes. Set
`source_redistribution` to `true` only when that row's
`redistribution_status` is exactly `redistributable`; otherwise set it to
`false` and retain explicit reference-only storage permission. All other listed
permissions and all signer attestations must be literal JSON `true`.

The detached Ed25519 signature covers canonical UTF-8 JSON produced with
sorted keys, ASCII escaping, and compact separators: Python equivalent
`json.dumps(payload, ensure_ascii=True, sort_keys=True,
separators=(",", ":")).encode("utf-8")`. Store the detached 64-byte signature
as hexadecimal or base64 text. Formatting whitespace in the decision file does
not affect verification; semantic substitutions do.

## 2. Issue acquisition authority

Update
`docs/validation/controlled_three_model_acquisition_manifest.csv` only from
verified external evidence. The `reference_mask` row must identify the final
binary raster, not the MBRSC ZIP. The default audit workspace expects that
raster at
`<external_data_workspace>/qualified_reference/mae_sai_event_reference_mask.tif`.

```powershell
uv run python scripts/issue_controlled_acquisition_authority_receipt.py `
  --manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --catalog-evidence pre_event_sar=<external>/pre-catalog-export.json `
  --catalog-evidence post_event_sar=<external>/post-catalog-export.json `
  --catalog-evidence reference_mask=<external>/qualified-reference-record.json `
  --license-evidence pre_event_sar=<external>/copernicus-legal-notice.pdf `
  --license-evidence post_event_sar=<external>/copernicus-legal-notice.pdf `
  --license-evidence reference_mask=<external>/provider-and-derivative-permission.pdf `
  --external-authority-decision <external>/completed-external-authority-decision.json `
  --external-authority-signature <external>/completed-external-authority-decision.sig `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --receipt-signing-key-id <internal-acquisition-receipt-key-id> `
  --receipt-signing-key-env FLOODGUARD_ACQUISITION_RECEIPT_HMAC_KEY `
  --output <external>/acquisition-authority-receipt.json
```

Set `FLOODGUARD_ACQUISITION_RECEIPT_HMAC_KEY` in the approved secret store. It is
an internal integrity secret, not external authority. The command refuses to
write a receipt if any product, checksum, evidence digest, permission, signer
identity, signature, validity interval, qualification, or
`processing_allowed` field is blocked. A key never overrides a blocker. Success
output reports only the receipt basename so private external-workspace paths do
not leak into logs.

## 3. Freeze the blind calibration release

The release must be model- and label-independent. It freezes 12 initial queries
and 12 disjoint fresh-retest queries with whole-parent-tile isolation.

```powershell
uv run python scripts/build_label_factory_calibration_release.py build `
  --reference-authority-approval-package <external>/reference-authority-approval `
  --canonical-grid-directory <external>/canonical-grid-release `
  --output <external>/calibration-membership-release-v1 `
  --release-id mae_sai_calibration_release_v1 `
  --created-at-utc <YYYY-MM-DDTHH:MM:SSZ>

uv run python scripts/build_label_factory_calibration_release.py validate `
  --package <external>/calibration-membership-release-v1
```

This does not create reviewer answers, pass calibration, assign reference
classes, or authorize formal model execution.

## 4. Complete blind review and dual-sign qualification

Follow `docs/label_factory_runbook.md` and
`docs/calibration_reference_procedure_v1.md`. Two distinct reviewers must finish
the same model-hidden calibration set before seeing one another's answers or any
model suggestion. A distinct adjudicator resolves every disagreement. A failed
attempt remains failed; use only the pre-frozen fresh retest for a later attempt.

The reviewer-calibration receipt, adjudication evidence, and error-strata CSV
must describe the same release, event, mask checksum, reviewer identities, and
cell/query set. Qualification reopens the selected immutable
`calibration_queries.csv` or `fresh_retest_queries.csv` from that validated
release and requires the reviewer receipt's query-manifest SHA-256 to match the
exact file bytes. It also compares every query's grid-contract hash,
source-registry hash, and normalized source timestamp. Reusing the same query
IDs with substituted geometry, grid, source, or time therefore fails closed.
The adjudication evidence uses
`floodguard.controlled_adjudication_evidence.v3`. Qualification reopens both
exact reviewer-cell CSVs, verifies their hashes against the calibration
receipt, derives a canonical decision hash per reviewer and query, and computes
the exact disagreement set. Every disagreement then has one unique ID, an
approved query-region ID, both derived reviewer-decision hashes, a protocol
outcome (`accept_a`, `accept_b`, `redraw`, `uncertain`, `unobservable`, or
`reject`), and a non-empty resolution reason. Arbitrary decision strings and
resolutions for agreeing queries are rejected. Formal adjudication cannot start
before reviewer calibration completes. The signed qualification binds the
complete reviewer-cell, adjudication, and resolution manifests. Then dual-sign
qualification:

```powershell
uv run python scripts/sign_controlled_reviewer_qualification.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --calibration-release-package <external>/calibration-membership-release-v1 `
  --reviewer-calibration-receipt <external>/reviewer-calibration-receipt.json `
  --reviewer-cell <reviewer-a-id>=<external>/reviewer-a-cells.csv `
  --reviewer-cell <reviewer-b-id>=<external>/reviewer-b-cells.csv `
  --calibration-attempt initial `
  --adjudication-evidence <external>/adjudication-evidence.json `
  --error-strata <external>/reference-error-strata.csv `
  --qualified-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --expires-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --trusted-key <acquisition-key-id>=FLOODGUARD_ACQUISITION_RECEIPT_HMAC_KEY `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --reviewer-signing-key-id <reviewer-key-id> `
  --reviewer-signing-key-env FLOODGUARD_REVIEWER_KEY `
  --adjudicator-signing-key-id <adjudicator-key-id> `
  --adjudicator-signing-key-env FLOODGUARD_ADJUDICATOR_KEY `
  --output <external>/reviewer-qualification-receipt.json
```

The qualification fails if disagreements remain, the query set differs, fixed
calibration thresholds do not pass, adjudication starts before calibration
finishes, a resolution record is missing or substituted,
identities/credentials are reused, or any lineage hash changes.

## 5. Freeze three-way spatial partitions

The input GeoJSON must declare a projected metre-based equal-area CRS in its
top-level `floodguard_crs` field. Each non-overlapping Polygon/MultiPolygon has a
unique `spatial_group_id` and exactly one split:

- `train`;
- `calibration`;
- `final_holdout`.

```powershell
uv run python scripts/freeze_controlled_spatial_partitions.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event-product `
  --artifact post_event_sar=<external>/post-event-product `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --trusted-key <acquisition-key-id>=FLOODGUARD_ACQUISITION_RECEIPT_HMAC_KEY `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --geometry <external>/spatial-partitions.geojson `
  --grid-contract <external>/equal-area-grid-contract.json `
  --cell-grid <external>/equal-area-cells.csv `
  --membership-output <external>/spatial-membership.csv `
  --receipt-output <external>/spatial-partition-receipt.json `
  --target-crs <equal-area-EPSG-code> `
  --frozen-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --assumptions "<authority-approved partition rationale>" `
  --signing-key-id <holdout-key-id> `
  --signing-key-env FLOODGUARD_HOLDOUT_KEY
```

Every grid-cell centre must belong to exactly one split. Changing geometry,
membership, acquisition manifest or authority receipt, CRS, affine, or a single
byte invalidates the receipt. The command re-verifies both the internal receipt
integrity signature and the external authority's detached Ed25519 decision at
the declared freeze time, then derives experiment/study-area scope from that
lineage. Do not choose or modify the final holdout after inspecting model
results. The holdout key ID and credential must be distinct from the acquisition
receipt authority.

## 6. Derive signed reference cells and calibration projection

This command reads the exact qualified raster. It writes:

- complete reference cells for governed final evaluation;
- a separate calibration-only projection for threshold selection;
- a receipt binding the mask, reviewer qualification, partitions, grid, error
  strata, outputs, and hashes.

```powershell
uv run python scripts/sign_controlled_reference_cells.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-mask <external>/qualified-reference-mask.tif `
  --error-strata <external>/reference-error-strata.csv `
  --reference-cells-output <external>/qualified-reference-cells.csv `
  --calibration-reference-output <external>/calibration-reference.csv `
  --derived-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --derivation-method "<qualified raster and adjudication procedure>" `
  --assumptions "<known reference limitations>" `
  --trusted-key <acquisition-key-id>=FLOODGUARD_ACQUISITION_RECEIPT_HMAC_KEY `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --trusted-key <reviewer-key-id>=FLOODGUARD_REVIEWER_KEY `
  --trusted-key <adjudicator-key-id>=FLOODGUARD_ADJUDICATOR_KEY `
  --trusted-key <holdout-key-id>=FLOODGUARD_HOLDOUT_KEY `
  --signing-key-id <reference-key-id> `
  --signing-key-env FLOODGUARD_REFERENCE_KEY `
  --receipt-output <external>/qualified-reference-cells-receipt.json
```

Do not give the full reference-cell CSV to a model-training or
threshold-selection process. Those steps receive only the signed calibration
projection. The model-run binder may verify the full reference lineage only
after the final prediction is immutable; the governed comparison then opens the
full reference to calculate final metrics.

## 7. Predeclare policy, audit prerequisites, and authorize execution

Scientific and safety reviewers must sign experiment-specific minimum metrics,
maximum area/calibration error, required measured error categories, minimum
category cell counts, deterministic tie-breaks, and expiry **before** any final
result exists.

```powershell
uv run python scripts/build_controlled_model_promotion_decision.py policy --help
```

Run the audit with the acquisition receipt, dual-signed reviewer qualification,
partitions, reference receipt/evidence, calibration projection, error strata,
promotion policy, and every role key. Omit `--allow-blocked`:

```powershell
uv run python scripts/audit_controlled_three_model_experiment.py `
  --external-workspace <external> `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-cell-receipt <external>/qualified-reference-cells-receipt.json `
  --reference-cell-evidence <external>/qualified-reference-cells.csv `
  --calibration-reference <external>/calibration-reference.csv `
  --error-strata <external>/reference-error-strata.csv `
  --promotion-policy <external>/promotion-policy.json `
  --trusted-key <role-key-id>=<ROLE_KEY_ENV> `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --receipt-output <external>/pre-execution-gate-receipt.json `
  --report-output <external>/pre-execution-gate-report.md
```

This is a **pre-execution readiness gate**. Existing model evidence, when
supplied, is informational; missing completed lanes do not create circular
readiness blockers. If this gate is `blocked`, stop.

After it is `ready`, issue a separate expiry-bound authorization:

```powershell
uv run python scripts/issue_controlled_execution_authorization_receipt.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-cell-receipt <external>/qualified-reference-cells-receipt.json `
  --reference-cell-evidence <external>/qualified-reference-cells.csv `
  --calibration-reference <external>/calibration-reference.csv `
  --error-strata <external>/reference-error-strata.csv `
  --promotion-policy <external>/promotion-policy.json `
  --expires-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --trusted-key <role-key-id>=<ROLE_KEY_ENV> `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --signing-key-id <execution-key-id> `
  --signing-key-env FLOODGUARD_EXECUTION_KEY `
  --output <external>/execution-authorization-receipt.json
```

`processing_allowed=true` in this receipt authorizes only the bounded experiment
described by its hashes and expiry. It still records `experiment_executed=false`,
`can_feed_decision_layer=false`, and `official_warning=false`.

## 8. Run each lane and freeze its calibration threshold

Run exactly these required families on identical acquisition, partition, and
reference lineage:

- `deterministic_sar_baseline`;
- `weak_label_logistic`;
- `geoai_candidate` (U-Net or FPN through the isolated runner).

Each lane contract must bind the execution-authorization manifest. Training may
read `train`; threshold selection may read only `calibration-reference.csv`.
Generate a calibration prediction CSV, then select and sign its threshold:

```powershell
uv run python scripts/select_controlled_model_threshold.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-cell-receipt <external>/qualified-reference-cells-receipt.json `
  --calibration-reference <external>/calibration-reference.csv `
  --promotion-policy <external>/promotion-policy.json `
  --execution-authorization-receipt <external>/execution-authorization-receipt.json `
  --model-id <immutable-model-id> `
  --model-family <required-family> `
  --model-artifact <external>/model-artifact `
  --model-contract <external>/model-contract.json `
  --calibration-prediction <external>/calibration-prediction.csv `
  --execution-started-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --training-started-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --training-completed-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --trusted-key <role-key-id>=<ROLE_KEY_ENV> `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --signing-key-id <model-executor-key-id> `
  --signing-key-env <MODEL_EXECUTOR_KEY_ENV> `
  --output <external>/threshold-selection-receipt.json
```

The selector recomputes a fixed-grid calibration-only threshold and records
`final_holdout_reference_opened=false`. It does not accept a caller-supplied
threshold. Only after this receipt is immutable may the lane generate final
holdout probabilities.

Then sign the completed model run using the exact threshold receipt, calibration
predictions, final prediction, model bytes, contract, authorization, and runtime
profile. Repeat once per family:

```powershell
uv run python scripts/sign_controlled_model_run.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-cell-receipt <external>/qualified-reference-cells-receipt.json `
  --reference-cell-evidence <external>/qualified-reference-cells.csv `
  --calibration-reference <external>/calibration-reference.csv `
  --error-strata <external>/reference-error-strata.csv `
  --promotion-policy <external>/promotion-policy.json `
  --execution-authorization-receipt <external>/execution-authorization-receipt.json `
  --model-id <immutable-model-id> `
  --model-family <required-family> `
  --model-artifact <external>/model-artifact `
  --model-contract <external>/model-contract.json `
  --calibration-prediction <external>/calibration-prediction.csv `
  --threshold-selection-receipt <external>/threshold-selection-receipt.json `
  --prediction <external>/final-holdout-prediction.csv `
  --runtime-profile <external>/runtime-profile.json `
  --inference-started-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --completed-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --assumptions "<model and execution limitations>" `
  --trusted-key <role-key-id>=<ROLE_KEY_ENV> `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --signing-key-id <same-model-executor-key-id-as-threshold> `
  --signing-key-env <MODEL_EXECUTOR_KEY_ENV> `
  --output <external>/signed-model-run.json
```

The seven-field runtime profile records training, calibration, inference, and
total seconds; peak memory; device; and hardware class. Runtime remains
operator-reported signed evidence unless an independent process monitor is
bound.

## 9. Run the governed comparison

Create a three-row model-evidence manifest that binds each family to its model
ID, prediction, calibration prediction, threshold receipt, model artifact,
model contract, and signed run receipt. Repeat every family mapping exactly
three times, once for each required family:

```powershell
uv run python scripts/run_controlled_three_model_experiment.py `
  --acquisition-manifest docs/validation/controlled_three_model_acquisition_manifest.csv `
  --acquisition-authority-receipt <external>/acquisition-authority-receipt.json `
  --artifact pre_event_sar=<external>/pre-event.SAFE.zip `
  --artifact post_event_sar=<external>/post-event.SAFE.zip `
  --artifact reference_mask=<external>/qualified-reference-mask.tif `
  --reviewer-qualification-receipt <external>/reviewer-qualification-receipt.json `
  --holdout-receipt <external>/spatial-partition-receipt.json `
  --holdout-geometry <external>/spatial-partitions.geojson `
  --holdout-grid-contract <external>/equal-area-grid-contract.json `
  --holdout-membership <external>/spatial-membership.csv `
  --reference-cell-receipt <external>/qualified-reference-cells-receipt.json `
  --reference-cell-evidence <external>/qualified-reference-cells.csv `
  --calibration-reference <external>/calibration-reference.csv `
  --error-strata <external>/reference-error-strata.csv `
  --promotion-policy <external>/promotion-policy.json `
  --execution-authorization-receipt <external>/execution-authorization-receipt.json `
  --model-evidence-manifest <external>/three-model-evidence.csv `
  --prediction <family>=<external>/final-holdout-prediction.csv `
  --calibration-prediction <family>=<external>/calibration-prediction.csv `
  --threshold-selection-receipt <family>=<external>/threshold-selection-receipt.json `
  --model-artifact <family>=<external>/model-artifact `
  --model-contract <family>=<external>/model-contract.json `
  --model-run-manifest <family>=<external>/signed-model-run.json `
  --trusted-key <role-key-id>=<ROLE_KEY_ENV> `
  --trusted-external-authority-key <external-authority-key-id>=<external>/authority-public-key `
  --result-signing-key-id <result-key-id> `
  --result-signing-key-env FLOODGUARD_RESULT_KEY `
  --result-expires-at-utc <YYYY-MM-DDTHH:MM:SSZ> `
  --output-directory <external>/controlled-three-model-result-v1
```

Supply all trusted role keys and use a distinct comparison-result signer.

The comparison re-verifies the complete chain and computes only from the common
immutable final holdout. The output directory must not already exist. FloodGuard
builds and verifies the complete signed bundle in a sibling staging directory,
publishes it with one rename, and removes staging on any failure; operators must
never recover or treat partial staging files as evidence. It emits:

- IoU, Dice/F1, precision, and recall;
- signed physical area error and absolute area error ratio;
- Brier score, reliability bins, expected calibration error, and an accessible
  calibration curve;
- the 13 required error categories, including explicit measured-cell coverage;
- per-model runtime/resources;
- a signed expiry-bound result receipt.

The result is report-only and remains `can_feed_decision_layer=false`.
Every metrics row must reproduce its signed run threshold and physical-area
evidence. All three rows must share one final-holdout sample count, group count,
and equal-area cell size, and all three calibration curves must use the exact
same ordered bin grid.

## 10. Issue the report-only promotion recommendation

Apply the policy to the exact receipt-bound metrics, calibration, error-category,
and runtime artifacts:

```powershell
uv run python scripts/build_controlled_model_promotion_decision.py recommend `
  --policy <external>/promotion-policy.json `
  --result-receipt <external>/controlled-result/three_model_result_receipt.json `
  --metrics <external>/controlled-result/three_model_metrics.csv `
  --calibration <external>/controlled-result/three_model_calibration.csv `
  --error-categories <external>/controlled-result/three_model_error_categories.csv `
  --runtime <external>/controlled-result/three_model_runtime.csv `
  --trusted-key <policy-key-id>=FLOODGUARD_POLICY_KEY `
  --trusted-key <result-key-id>=FLOODGUARD_RESULT_KEY `
  --signing-key-id <recommendation-key-id> `
  --signing-key-env FLOODGUARD_RECOMMENDATION_KEY `
  --output <external>/model-promotion-recommendation.json
```

The only outcomes are `candidate_selected` and `no_candidate_qualified`.
Missing error-category coverage, stale/expired evidence, a substituted artifact,
or a threshold/runtime inconsistency disqualifies the affected lane or blocks
the recommendation. Selection is not operational acceptance and does not
authorize a decision-layer probability, FPPS change, public warning, or route
advice.

## Failure and retention rules

- Any missing, expired, unverifiable, scope-mismatched, checksum-mismatched, or
  role-reused receipt fails closed.
- Do not silently fall back to weak labels, random-pixel validation, another
  event, another raster, or a cached result.
- Preserve failed calibration attempts, disagreement/adjudication history,
  rejected policies, and `no_candidate_qualified` results.
- Store SAFE archives, GeoTIFFs, model weights, full predictions, personal
  reviewer material, and signing secrets outside Git.
- Commit only redacted relative identifiers, small receipts/reports, tests, and
  permitted derived evidence.
- Never expose absolute local paths or secret values in logs, receipts, Studio,
  screenshots, or public downloads.
- The root FloodGuard suite must remain independent of GeoAI, PyTorch, GPU, and
  network access. Real GeoAI execution stays isolated under
  `services/geoai-runner` and opt-in verification.
