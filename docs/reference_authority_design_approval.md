# Reference Authority design approval gate

Status: implemented fail-closed contract. No real Mae Sai Reference Authority
decision or approval package has been created.

This gate freezes one attributable Reference Authority decision before any
canonical calibration-reserve or calibration-reference construction. It binds:

1. an evidence-complete, immutable **pre-calibration** human-role package with
   exactly one accepted `reference_authority` appointment;
2. one verified `floodguard.calibration_reserve_design.v1` receipt and one
   candidate id from its `candidate_reserve_combinations.csv`;
3. an explicit `approved`, `rejected`, or `not_submitted` decision for the
   optional `floodguard.review_derivative_lineage_receipt.v1`; and
4. the exact SHA-256 and version of the fixed reference-procedure document.

The resulting schema is
`floodguard.reference_authority_design_approval.v1`. The package is immutable,
self-hashed, internally file-manifested, and self-contained: it copies the
validated human-role package, provisional reserve-design package, decision
evidence, fixed procedure, and optional derivative receipt. Source packages
are read and re-hashed but never changed.

## Evidence boundary

Accepted evidence types are a local email export, signed PDF, or message
export. The request records the exact evidence SHA-256, decision UTC, capture
UTC, declared sender, recipient, and appointed sender person id. The builder
requires this ordering:

```text
accepted appointment <= frozen role package <= reserve/derivative receipt
                                              <= authority decision
                                              <= evidence capture
                                              <= approval-package creation
```

The software verifies local bytes, hashes, UTC ordering, declared attribution,
and artifact consistency. It does **not** authenticate the human sender,
validate a PDF signature, certify qualifications, or understand whether an
opaque email/PDF/message semantically agrees with the structured request. A
second human must compare the exported message with the request before build.

## Required decisions

The reserve and procedure decisions are each exactly `approved` or `rejected`.
The derivative decision is exactly `approved`, `rejected`, or `not_submitted`:

- `approved`/`rejected` requires the exact derivative lineage receipt and its
  self-hash;
- `not_submitted` requires no receipt and a null receipt hash; and
- derivative approval governs only whether the bound display may be considered
  by the next separate construction step. It never authorizes reviewer
  delivery.

An `approved_next_construction_only` result occurs only when both the reserve
candidate and fixed reference procedure are approved. Derivative rejection or
absence does not block reserve/reference construction; it keeps the display
excluded. Any reserve/procedure rejection produces
`rejected_no_construction_authority`.

## Request shape

Use exact `YYYY-MM-DDTHH:MM:SSZ` timestamps and lower-case SHA-256 values. The
following is a shape example only, not evidence and not a real approval:

```json
{
  "schema": "floodguard.reference_authority_design_decision_request.v1",
  "package_id": "mae_sai_reference_authority_decision_v1",
  "event_id": "TH-MAESAI-2024-09",
  "created_at_utc": "<UTC-after-evidence-capture>",
  "reference_authority_role_id": "FG-RA-NNN",
  "reference_authority_person_id": "FG-HUM-NNN",
  "decision_evidence": {
    "evidence_id": "FG-RA-DEC-NNN",
    "evidence_type": "email_export",
    "local_path": "authority_decision.eml",
    "sha256": "<64-lowercase-hex>",
    "decision_at_utc": "<UTC-from-message>",
    "captured_at_utc": "<UTC-of-export>",
    "attributable_sender": "<sender shown by export>",
    "attributable_recipient": "<recipient shown by export>",
    "attributable_sender_person_id": "FG-HUM-NNN"
  },
  "reserve_design_decision": {
    "design_id": "mae_sai_reserve_design_v1",
    "chosen_candidate_id": "CALRES-XXXXXXXXXXXX",
    "decision": "approved",
    "rationale": "<authority rationale for the static-context tradeoff>"
  },
  "review_derivative_decision": {
    "decision": "not_submitted",
    "receipt_sha256": null,
    "rationale": "No change display is proposed for this version."
  },
  "reference_procedure_decision": {
    "document_version": "reference_procedure_v1",
    "document_sha256": "<64-lowercase-hex>",
    "decision": "approved",
    "rationale": "<authority rationale>"
  },
  "authority_attestations": {
    "reserve_uses_static_non_label_context_only": true,
    "reserve_candidate_is_not_flood_truth": true,
    "calibration_and_retest_queries_remain_unselected_and_unseen": true,
    "reference_procedure_is_fixed_to_the_bound_hash_and_version": true,
    "derivative_decision_governs_display_inclusion_only": true,
    "no_bundle_calibration_or_formal_review_is_authorized": true,
    "human_role_evidence_limitation_is_acknowledged": true
  },
  "assumptions": "Authority decision only; no query, label, model, or operational claim."
}
```

## Build and revalidate

Do not run this command until a real appointed authority has returned the
attributable decision and the operator has checked the structured transcription
against that export.

```powershell
uv run python scripts/build_reference_authority_approval.py build `
  --request-json <restricted_coordination_workspace>/ra_decision_request_v1.json `
  --evidence-root <restricted_coordination_workspace>/authority_evidence `
  --human-role-package <restricted_coordination_workspace>/human_roles_precalibration_vN `
  --calibration-reserve-design-package <external_data_workspace>/label_factory/calibration_reserve_design_vN `
  --reference-procedure docs/<fixed_reference_procedure>.md `
  --review-derivative-lineage-receipt <optional_exact_receipt.json> `
  --output <restricted_coordination_workspace>/ra_design_approval_v1

uv run python scripts/build_reference_authority_approval.py validate `
  --package <restricted_coordination_workspace>/ra_design_approval_v1
```

Omit `--review-derivative-lineage-receipt` only when the request records
`decision=not_submitted` and `receipt_sha256=null`.

## Hard safety boundary

Every package fixes all training, decision, FPPS, warning, annotation,
review-queue, calibration-execution, bundle, and formal-review flags to false.
It contains empty calibration/retest query-id arrays. Even an approved package
only allows later code to start a **separate** canonical reserve/reference
construction. That later artifact must have its own validator and must still
not authorize calibration execution or formal review. A passing reviewer
calibration receipt and a later post-calibration human-role package remain the
only route toward the first 20 formal reviews.
