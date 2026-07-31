# Human-role evidence package

The human-role package is the fail-closed bridge between recruitment records and
the FloodGuard calibration/formal-review workflow. It is not a people-search
result, a qualification certificate, a flood label, or a calibration receipt.

No package has been created for the Mae Sai pilot by adding this code. The files
under external `human_coordination_v2` remain planning and recruitment material
until real people reply, attributable evidence is saved locally, decisions are
made, and this validator succeeds.

## Evidence boundary

Public profiles and papers may support `candidate_research`, but every candidate
row is emitted with all of these fields set to false:

- `confers_nomination`
- `confers_acceptance`
- `confers_identity_verification`
- `confers_qualification_certification`

The strict candidate-id contract accepts the existing planning forms
`FG-CAND-B-NNN` and `FG-CAND-RA-NNN` (plus the legacy neutral
`FG-CAND-NNN`). Candidate ids are research identifiers, never person or role
identifiers.

An appointment is a separate record. Each of the four role categories must have
an accepted appointment and four local, checksum-matched evidence records:

1. attributable role acceptance;
2. conflict disclosure plus the owner's conflict decision;
3. participant data-use and annotation-use terms; and
4. the documented qualification basis.

An evidence record identifies its role and opaque person id, its local path below
the operator-selected evidence root, lowercase SHA-256, UTC capture time,
attributable sender and recipient, and the exact status
`local_copy_hash_verified_only`. URLs, a name typed into JSON, a public shortlist,
and an outreach draft cannot replace the local bytes.

The frozen package always preserves this limitation: checksum and declaration
validation does not independently verify legal identity, qualifications,
independence, actual blinding conduct, or competence. A qualification document
is a basis for accountable human assessment, not software certification.

## Required role separation

There must be exactly one appointment in each category:

| Category | Stable role-id form |
|---|---|
| Reference Authority | `FG-RA-NNN` |
| Reviewer A | `FG-RV-A-NNN` |
| Reviewer B | `FG-RV-B-NNN` |
| Adjudicator C | `FG-ADJ-C-NNN` |

Every human has an opaque `FG-HUM-NNN` person id. A and B must be different
people. The Reference Authority and C must both be distinct from A and B. The
same person may be Reference Authority and C only when the request explicitly
sets `reference_authority_adjudicator_dual_role_allowed=true`. No other dual
assignment is accepted.

A role id may never be reassigned to another person in a child package. A real
replacement therefore receives a new role id, for example `FG-RV-B-002`, and
must complete the applicable evidence and calibration again.

## Operator exposure and blinding

The validator does not force the project operator to be Reviewer A. The strongest
design uses two external, distinct, genuinely blinded A/B reviewers:

```text
project_operator=false
prior_prohibited_evidence_exposure=false
review_lane=independent_blinded
```

Reviewer B must always meet that independent-lane contract.

If the operator serves as A after seeing FloodGuard weak-label, model, or
selection evidence, the request must not call that lane independent. It must
record:

```text
project_operator=true
prior_prohibited_evidence_exposure=true
conflict_declared=true
review_lane=authority_approved_mitigated_non_independent
```

It also needs substantive conflict and independence controls plus a separate
local `independence_mitigation_approval` record attributable to the appointed
Reference Authority. The resulting package always reports
`genuinely_blinded_double_review=false` and, if all later gates pass, uses the
status `formal_review_gate_open_mitigated_non_independent_a`. This keeps the
exposure visible even if the authority permits the limited research lane.

## Participation and data-use decisions

The package requires one explicit participation mode:

- `volunteer`; or
- `paid_by_time`.

Payment is for honest time, never agreement or a calibration pass. Every
appointment's compensation basis must match the package decision.

The package also requires one annotation-use scope:

- `internal_research_only`; or
- `potentially_publishable_with_explicit_terms`.

Each participant must accept matching terms, including public-release
permission, a future UTC retention end, and withdrawal terms. A separate project
release decision remains mandatory even when participant terms permit potential
publication.

## Calibration and formal-review gate

An evidence-complete pre-calibration package may be frozen, but it has:

```text
formal_review_authorized=false
formal_review_authorized_from_utc=null
```

Formal authorization requires all of the following:

1. the owner explicitly requests it in a later package version;
2. a local reviewer-calibration receipt is supplied with an exact file SHA-256;
3. the calibration module verifies the receipt's schema, passing metrics,
   lineage, safety fields, and self-hash;
4. the receipt reviewer ids exactly equal the appointed A and B role ids;
5. protocol and taxonomy versions match;
6. all role acceptances, conflict decisions, and data terms predate calibration
   completion; and
7. package creation is not earlier than the receipt's formal-review not-before
   timestamp.

A failure diagnostic is not a receipt and cannot open this gate. A receipt for
different reviewer ids cannot be reused after replacing A or B.

## Separate reviewer-evidence design approval

This package governs people, attributable role evidence, and the calibration
gate. It intentionally does not duplicate the processing/alignment and review-
derivative lineage contracts owned by the review-bundle workflow. A technically
valid processing receipt or VV/VH derivative receipt proves reproducible lineage;
it does **not** prove that the Reference Authority approved those layers for
calibration or reviewer display.

Before calibration, the fixed reviewer-evidence design must separately bind the
exact processing receipt, every admitted derivative receipt, display parameters,
and attributable Reference Authority approval. The present lineage-valid change-
display candidate remains a candidate until that human approval exists. The role
package cannot convert it into an authority-approved display.

## Immutable package and safety

Package versions are positive integers. Version 1 has no parent; every child is
exactly parent version plus one and binds the parent id and manifest hash. The
writer copies evidence into the package, verifies it again after copying, writes
a canonical self-hashed manifest, validates the completed temporary directory,
and refuses to overwrite an existing output directory.

Every package permanently carries:

```text
eligible_for_model_training=false
eligible_for_query_model_training=false
eligible_for_decision_layer=false
eligible_for_fpps=false
eligible_for_warning=false
```

## CLI

Build only after real evidence exists:

```powershell
python scripts/build_label_factory_human_roles.py build `
  --request-json C:\private\human-role-request-v1.json `
  --evidence-root C:\private\human-role-evidence `
  --output C:\private\human_roles_v1
```

Attach a passing receipt only when requesting the post-calibration gate:

```powershell
python scripts/build_label_factory_human_roles.py build `
  --request-json C:\private\human-role-request-v2.json `
  --evidence-root C:\private\human-role-evidence `
  --parent-package C:\private\human_roles_v1 `
  --calibration-receipt C:\private\reviewer_calibration_receipt.json `
  --output C:\private\human_roles_v2
```

Revalidate a frozen package:

```powershell
python scripts/build_label_factory_human_roles.py validate `
  --package C:\private\human_roles_v1
```

The command exits with code 2 and prints `BLOCKED:` for any missing evidence,
hash mismatch, role collision, unsafe path, undisclosed operator conflict,
lineage error, or invalid calibration binding.
