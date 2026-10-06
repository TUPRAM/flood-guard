# Form 2: four-role appointment worksheet

**Status: EMPTY.** This worksheet collects what
`scripts/build_label_factory_human_roles.py` needs. The exact request schema
and rules are in `docs/human_role_package.md`. The builder reads local evidence
files; a name typed here is not evidence.

## Roles and separation rules

| Role | Role id | Person id | Rules |
| --- | --- | --- | --- |
| Reference Authority | `FG-RA-001` | `FG-HUM-___` | Distinct from A and B. May also be C only if the request sets `reference_authority_adjudicator_dual_role_allowed=true`. |
| Reviewer A | `FG-RV-A-001` | `FG-HUM-___` | Distinct from B. If A is the project operator and has seen weak labels or model output, the lane must be `authority_approved_mitigated_non_independent`. |
| Reviewer B | `FG-RV-B-001` | `FG-HUM-___` | Always `independent_blinded`, `project_operator=false`, `prior_prohibited_evidence_exposure=false`. |
| Adjudicator C | `FG-ADJ-C-001` | `FG-HUM-___` | Distinct from A and B. |

## Evidence each person supplies (four local files per role)

Save each file under your private evidence root and record its SHA-256, UTC
capture time, sender and recipient.

1. **Role acceptance.** An email, signed PDF or message in which the person
   accepts this exact role.
2. **Conflict disclosure** and the owner's conflict decision.
3. **Participant data-use and annotation-use terms**, including the
   public-release permission, the retention end date (UTC) and withdrawal terms.
4. **Qualification basis**, for example a CV extract or a record of prior
   flood-mapping or remote-sensing work.

## Project owner decisions

| Decision | Choose one |
| --- | --- |
| Participation mode | `volunteer` / `paid_by_time` (payment is for time, never for agreement or passing) |
| Annotation-use scope | `internal_research_only` / `potentially_publishable_with_explicit_terms` |

## What the reviewers will look at

With the Sentinel-2 route, A and B label from the 15 September 2024
Sentinel-2 bands only (true colour and B11/B8A/B4 false colour). They do not
see the SAR candidate, GFM, or each other's labels until both are locked.
Using an optical display needs the authority-approved display described in
`README.md`, contract gap 2.
