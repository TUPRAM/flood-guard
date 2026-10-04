# Planning assessment overlay (schema 1.0)

The planning assessment overlay is the file the planning engine writes for one case and every screen reads
(restructuring plan v2, section 7.1, task E11). This page says what is in it, who refuses what, and where each rule
comes from. The rules are those of the two signed planning protocols; this page adds none.

An overlay is planning guidance for preparedness and post-event prioritisation. It is not an official warning, it is
non-operational, and class E never means safe.

## Files

| File | What it is |
|---|---|
| `packages/contracts/schemas/planning-assessment-overlay.schema.json` | The JSON schema (draft 2020-12, closed objects, every field required; an absent value is `null`). |
| `src/floodguard/planning_overlay.py` | The strict validator, loader and writer. |
| `apps/web/src/lib/planning-assessment-overlay.ts` | The TypeScript types and the strict parser for the screens. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.fixture.json` | The fixture: an invented case with invented units. A fixture, not a place. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.fixture.summary.json` | What Python counts in the fixture, with the file hash and a content digest. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.refusals.json` | The refusal cases both test suites read. |
| `apps/web/scripts/planning-overlay-fixture.py` | Writes the fixture and its summary. |

To rebuild the fixture, run `python apps/web/scripts/planning-overlay-fixture.py` from the repository root.
`tests/test_planning_overlay.py` fails when the committed fixture is not what Python writes today, so a change in
`confidence.py`, `normalisation.py`, `scoring.py` or a protocol file shows up there first.

## What one overlay holds

The header carries the case, the SHA-256 of both protocol files, the rule versions, the frame header exactly as
`normalisation.frame_record` returns it (weights, anchors, leave-one-component-out weights and the sentence that one
flood input drives 4 of 5 components), `publication_eligibility`, the lineage inputs with their hashes and rights
levels, `source_timestamp`, `generated_at` and `assumptions`. `official_warning` is `false`, `operational_status` is
`non_operational`, and `accepted_fpps` and `accepted_action_class` are `null`.

One row is one unit in one lane with one flood input.

| Field | Meaning | Source |
|---|---|---|
| `tier`, `lane` | T0 with ENG, T1 with SCN or SCN-ENV, T2 and T3 with OBS, T4 with no lane | v1a `evidence_tier_model` |
| `temporal_relation` | `event_aligned`, `dated_other` or `season_window`, for the flood input of the row | v1a `date_rule` |
| `scenario` | The declaration of a T1 row | v1a tier T1 |
| `lineage` | The one flood input, the one routing context and the one closure rule of the row | v1a guardrail GR3, v1b `closure_rule_v1` |
| `components` | The five records as `normalisation.py` returns them, with their echoed inputs; `null` when the protocol states no value for the unit | v1a `scoring_frame` |
| `fpps_0_100` | The weighted sum, rounded to two decimals; `null` when a component is not computed | v1a `scoring_frame.formula` |
| `confidence` | The record `confidence.derive_confidence` returns: class, kind, basis of C1 to C8, failed conditions, reason code, the GR1 record, measurements and thresholds | v1a `confidence_rule_v1` |
| `action_class`, `action_reason_code` | The binding class (rule v1) and its reason code | v1a `class_rules.v1` |
| `would_be_class` | The scorer rerun with confidence medium, for low-confidence rows. Never binding | v1a `class_rules.v1.would_be_class` |
| `class_v2` | The v2 result, labelled `secondary`, with `binding: false` and the evidence of the five triggers | v1a `class_rules.v2`, decision D6 |
| `leave_one_component_out` | For each component, the FPPS and the v1 class without it | v1a `scoring_frame.leave_one_component_out` |
| `headline_stability` | `not_evaluated`, `headline_eligible` or `unstable_verify`, with the class retention | v1a guardrail GR8 |
| `source_timestamp`, `assumptions` | Per row, as AGENTS.md asks of every output | AGENTS.md |

Row kinds:

- **T0 (ENG)**: synthetic component values and a declared confidence. No flood input, no lineage, no v2 class.
- **T1 (SCN, SCN-ENV)**: scenario confidence (`confidence_kind: scenario`). It is never observed confidence.
- **T2 and T3 (OBS)**: observed confidence. A T2 row stays at E unless the skill condition passes.
- **T4**: locked in this release. The row is a placeholder and carries no value.

## What is refused

Both parsers give the same code for the same refusal. The Python validator also reruns the scorer, and, when it is
given the two protocol files in force, recomputes every component record and every confidence record from the inputs
the record echoes.

| Refusal | Code | Source |
|---|---|---|
| A tier that is not T0 to T4 | `unknown_tier` | v1a `evidence_tier_model.tiers` |
| A class above E without medium confidence | `class_above_e_without_medium_confidence` | v1a invariants at every tier |
| A non-null `accepted_fpps` or `accepted_action_class` | `accepted_value_not_null` | v1a invariants at every tier |
| An OBS row that is not `event_aligned` with a binding class above E | `temporal_honesty_gr7` | v1a guardrail GR7 |
| `official_warning` not false, or a status other than `non_operational` | `official_warning_not_false`, `operational_status_not_non_operational` | v1a invariants at every tier |
| Confidence `high` | `high_confidence_not_assigned` | v1a `confidence_rule_v1.high` |
| A value on a T4 row | `t4_locked_row_carries_values` | v1a tier T4 |
| A unit under 100 residents with a class, a would-be class or a v2 class | `gr1_no_class` | v1a guardrail GR1, reading DR-A09 |
| Low confidence without class E and reason `low_confidence` | `low_confidence_forces_e` | v1a `class_rules.v1` |
| A reason code that does not belong to the class | `reason_code_mismatch` | v1a `class_rules.v1.reason_codes` |
| A would-be class on a row that is not low, or none on one that is | `would_be_class_mismatch` | v1a `class_rules.v1.would_be_class` |
| A v2 result that is not the first trigger met in the order E, A, B, C, D | `v2_result_inconsistent` | v1a `class_rules.v2.evaluation`, reading DR-A08 |
| An assumed component in a row | `assumed_component_in_a_row` | v1a reading DR-A05 |
| An FPPS that is not the weighted sum; a leave-one-out value that is not either | `fpps_mismatch`, `leave_one_component_out_mismatch` | v1a `scoring_frame` |
| A headline status that does not follow from the retention | `headline_stability_inconsistent` | v1a guardrail GR8 |
| A rights level above the minimum of the lineage | `publication_eligibility_not_lineage_minimum` | v1a guardrail GR6 |
| A product 4009 input without CC BY-SA 4.0, the credit and a change notice | `product_4009_licence_missing` | decision D2, `rights_basis_4009_v1.json` |
| A class the scorer does not give (Python only) | `class_rule_mismatch` | v1a `class_rules.v1.rules` |
| A component or confidence record that is not what the modules compute (Python, with the protocol files) | `component_not_frame_record`, `confidence_not_rule_record` | v1a guardrail GR2, `confidence_rule_v1` |

`planning_overlay.write_overlay` writes under `apps/web/public` only when `publication_eligibility` is `public`, and
writes an overlay with product 4009 in its lineage there only with the rights record confirmed by the owners.

## What the fixture can and cannot show

The fixture has 26 rows on 21 invented units: every tier, every reason code, every failed condition C1 to C8, the
would-be classes A to E, every v2 result including "no v2 trigger met", an OBS row that is `dated_other`, a unit
under guardrail GR1, a row with a component that is not computed, the three states of the headline slot and the
three rights levels. Its dates are in 2030.

Two states cannot be built from invented units, because the signed protocol ties them to real names:

- condition C3 `by_construction` (product 4009 in the eight units of the Mae Sai reporting frame only);
- a T2 row that passes the skill condition (two named detectors only).

The v2 results and the headline values in the fixture are invented: no v2 wrapper and no ensemble exist yet.

## Points the protocols leave open

These are shape choices this schema had to make. Each needs an owner answer before task E8 writes a real overlay.

1. **T4 rows.** The protocols say T4 is locked and not reached; they do not say whether an overlay has a T4 row.
   The schema admits one as a placeholder with no value, so the locked state can be shown from data.
2. **Engine rows.** For tier T0 the protocols say "declared per row" and "any A-E". The schema gives an engine row
   synthetic component values, a declared confidence and no v2 class. Whether an engine row gets a v2 class, and
   whether it can be declared `high`, is not stated; `high` is refused everywhere.
3. **A component with no protocol value.** `normalisation.py` raises for a unit with no land, no resident or nobody
   with baseline access. The row then has no FPPS, no would-be class and no leave-one-out; its confidence is low
   (C5) and its class is E by the first rule of class rule v1. The protocols do not describe this row.
4. **Leave-one-out under GR1.** GR1 names the binding, would-be and v2 classes. The schema also leaves the
   leave-one-out class empty for such a unit and keeps the FPPS values.
5. **`temporal_relation` of rows without a flood input.** It is `null` for T0 and T4 rows.
6. **v2 when a trigger cannot be evaluated.** v1b notes that the recurrence flag cannot be computed where the JRC
   tile is not on disk. The schema requires all five triggers with a true or false outcome.
7. **No overlay-level confidence.** Plan 7.1 lists the common metadata fields, which include one
   `confidence_class` for the whole file. Rule v1 applies per unit and lane, and scenario confidence is never
   counted with observed confidence, so the header carries none.
8. **Blocks of plan 7.1 not in schema 1.0.** `age_exposure`, `access`, `travel_minutes`, `equity`,
   `shelter_2sfca`, the ensemble outputs other than the headline slot, and `display_context_package_sha256`. Their
   modules are tasks E5, E9 and E10. Adding them is a schema version change.
9. **Where a would-be class may be shown.** v1a allows it in Command "only for T3 rows that are low because of a
   non-evidence condition" and does not list those conditions. The overlay carries the would-be class and the
   failed conditions; it does not say which surface may show them.
10. **The skill caption of a T2 row.** v1a asks for a "mandatory skill caption" beside a T2 would-be class and gives
    no wording. The overlay carries the T2 skill record (status, conditions, measurements, metric wording) and no
    caption text.
11. **Names.** Plan 7.1 names the schema `planning-assessment.schema.json` and puts the types in
   `packages/contracts/src/`. Task E11 as issued names `planning-assessment-overlay.schema.json` and
   `apps/web/src/lib`; that is what was built. `tests/test_contract_schemas.py` and `packages/contracts/src/index.ts`
   are unchanged.
