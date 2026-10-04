# Planning assessment overlay (schema 1.0)

The planning assessment overlay is the file the planning engine writes for one case and every screen reads
(restructuring plan v2, section 7.1, task E11). This page says what is in it, who refuses what, and where each rule
comes from. The rules are those of the two signed planning protocols. Where the protocols are silent, the choice made
here is listed at the end for the owners.

An overlay is planning guidance for preparedness and post-event prioritisation. It is not an official warning, it is
non-operational, and class E never means safe.

## Files

| File | What it is |
|---|---|
| `packages/contracts/schemas/planning-assessment-overlay.schema.json` | The JSON schema (draft 2020-12, closed objects, every field required; an absent value is `null`). The signed numbers are constants in it. |
| `src/floodguard/planning_overlay.py` | The strict validator, loader and writer. |
| `apps/web/src/lib/planning-assessment-overlay.ts` | The TypeScript types and the strict parser for the screens. |
| `apps/web/src/lib/planning-protocol-binding.json` | The constants of the two protocol files in force, written by Python for the web parser: hashes, frame header, thresholds, class rules, case list. It holds no value for any unit. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.fixture.json` | The fixture: an invented case with invented units. A fixture, not a place. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.fixture.summary.json` | What Python counts in the fixture, with the file hash and a content digest. |
| `apps/web/src/lib/__fixtures__/planning-assessment-overlay.refusals.json` | The refusal cases both test suites read. |
| `apps/web/scripts/planning-overlay-fixture.py` | Writes the fixture, its summary and the binding file. |

To rebuild the three generated files, run `python apps/web/scripts/planning-overlay-fixture.py` from the repository
root. `tests/test_planning_overlay.py` fails when a committed file is not what Python writes today, so a change in
`confidence.py`, `normalisation.py`, `scoring.py` or a protocol file shows up there first.

## What one overlay holds

The header carries the case, the SHA-256 of both protocol files, the rule versions, the frame header exactly as
`normalisation.frame_record` returns it (weights, anchors, leave-one-component-out weights and the sentence that one
flood input drives 4 of 5 components), `publication_eligibility`, the lineage inputs, `source_timestamp`,
`generated_at` and `assumptions`. `official_warning` is `false`, `operational_status` is `non_operational`, and
`accepted_fpps` and `accepted_action_class` are `null`.

Each input carries its hash, its rights level, its licence and attribution, the `source_product` it declares
(`unosat_product_4009` is UNOSAT/GISTDA product 4009) and, for a flood input, its `acquisition_date` (`null` for an
input with no single date).

One row is one unit in one lane with one flood input and one scenario.

| Field | Meaning | Source |
|---|---|---|
| `tier`, `lane` | T0 with ENG, T1 with SCN or SCN-ENV, T2 and T3 with OBS, T4 with no lane | v1a `evidence_tier_model` |
| `temporal_relation` | `event_aligned`, `dated_other` or `season_window`, as the two dates the row echoes give it | v1a `date_rule` |
| `scenario` | The declaration of a T1 row | v1a tier T1 |
| `lineage` | The one flood input, the one routing context and the one closure rule of the row; the closure basis is `modelled_from_<that flood input>` | v1a guardrail GR3, v1b `closure_rule_v1` |
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

The summary both sides compute (`summarise_overlay`, `summarisePlanningAssessmentOverlay`) counts classes, reason
codes and confidence per lane column: OBS, SCN (with SCN-ENV), ENG, and `no_lane` for tier T4. It holds no count
across the columns, because v1a counts scenario classes only in the SCN column and never counts engine classes or
scenario confidence with the observed ones.

## Who checks what

Three things read an overlay, and they agree on the refusal codes.

- **The JSON schema** fixes the shape, the vocabularies and the signed numbers: the five weights and their
  leave-one-out sets, the flood anchor 0.20, the lane sentence, the GR1 minimum of 100 residents, the confidence
  thresholds (3 days, 0.8, 15 points, 0.2, 100, 0.1, 1) and the T2 skill thresholds. A changed protocol number is a
  schema change, as v1a change control asks.
- **The Python validator** adds the cross-field rules and reruns the scorer. With the two protocol files in force
  (`load_protocol_binding`) it also re-derives every component record and every confidence record, compares the
  hashes and the frame header with the files, and compares the case header with v1a `case_portfolio`. A candidate
  overlay is refused without the protocol files; only a fixture (`fixture_demo`) is checked without them.
- **The web parser** always holds the protocol constants (`planning-protocol-binding.json`, which a test compares
  with the files in force). It applies the same rules: it recomputes every basis value, every component record and
  the A-E class from the v1a rules. It does not compare the assumptions text of a confidence record.

Both validators check that a date exists, read the end of a pattern the same way (a trailing line feed is refused)
and refuse a number that is not finite, so one file gets one answer. Without the protocol files the Python validator
checks a fixture against itself only: it does not compare the hashes with the files or re-derive the component
records.

## What is refused

Both parsers give the same code for the same refusal. The 113 refusal cases in the shared file are run by both
test suites, except the one case only Python can see (a candidate without the protocol files). Every `if` / `then` /
`else` of the schema is tripped by at least one of them.

| Refusal | Code | Source |
|---|---|---|
| A wrong shape, an unknown word, a signed number changed, a date that does not exist, a number that is not finite | `structure` | the schema; v1a for each constant |
| A tier that is not T0 to T4 | `unknown_tier` | v1a `evidence_tier_model.tiers` |
| A class above E without medium confidence | `class_above_e_without_medium_confidence` | v1a invariants at every tier |
| A non-null `accepted_fpps` or `accepted_action_class` | `accepted_value_not_null` | v1a invariants at every tier |
| An OBS row that is not `event_aligned` with a binding class above E | `temporal_honesty_gr7` | v1a guardrail GR7 |
| A temporal relation that the row's two dates do not give; a dated SCN-ENV row | `temporal_relation_mismatch` | v1a `date_rule` |
| `official_warning` not false, or a status other than `non_operational` | `official_warning_not_false`, `operational_status_not_non_operational` | v1a invariants at every tier |
| Confidence `high` | `high_confidence_not_assigned` | v1a `confidence_rule_v1.high` |
| A tier in a lane that is not its own | `tier_lane_mismatch` | v1a `evidence_tier_model.tiers` |
| A value on a T4 row | `t4_locked_row_carries_values` | v1a tier T4 |
| A unit under 100 residents with a class, a would-be class or a v2 class; a row with no class that is not such a unit | `gr1_no_class` | v1a guardrail GR1, reading DR-A09 |
| A confidence record that disagrees with its row or with itself: a basis value its measurements do not give, a resident count other than the one the row is scored on, an acquisition date other than the flood input's | `confidence_record_mismatch` | v1a `confidence_rule_v1`, guardrails GR1 and GR3 |
| Low confidence without class E and reason `low_confidence` | `low_confidence_forces_e` | v1a `class_rules.v1` |
| A class that class rule v1 does not give | `class_rule_mismatch` | v1a `class_rules.v1.rules` |
| A reason code that does not belong to the class | `reason_code_mismatch` | v1a `class_rules.v1.reason_codes` |
| A would-be class on a row that is not low, none on one that is, or one the rule does not give | `would_be_class_mismatch` | v1a `class_rules.v1.would_be_class` |
| A v2 result that is not the first trigger met in the order E, A, B, C, D, or a trigger the row contradicts | `v2_result_inconsistent` | v1a `class_rules.v2`, reading DR-A08 |
| An assumed component in a row | `assumed_component_in_a_row` | v1a reading DR-A05 |
| A component present but recorded as not computed, or a synthetic value outside an engine row | `component_mismatch` | v1a `confidence_rule_v1` C5, lane ENG |
| An FPPS that is not the weighted sum; a leave-one-out value or class that is not either | `fpps_mismatch`, `leave_one_component_out_mismatch` | v1a `scoring_frame` |
| Weights that do not sum to 1 | `scoring_frame_inconsistent` | v1a `scoring_frame.weights` |
| A headline status that does not follow from the retention | `headline_stability_inconsistent` | v1a guardrail GR8 |
| A row whose lineage names no flood input or routing context, or a closure modelled from another input | `lineage_unresolved` | v1a guardrail GR3, v1b `closure_rule_v1` |
| A repeated `row_id` or `input_id`; two rows for one unit, lane, flood input and scenario | `duplicate_id` | v1a `confidence_rule_v1.applies_per` |
| A fixture unit without the label "not a place" | `fixture_label_missing` | task E11 |
| A rights level above the minimum of the lineage | `publication_eligibility_not_lineage_minimum` | v1a guardrail GR6 |
| An input that names product 4009 (by product number, event code or layer name) without declaring it | `source_product_not_declared` | decision D2, v1a `date_rule.product_4009` |
| A product 4009 input without CC BY-SA 4.0, the credit and a change notice | `product_4009_licence_missing` | decision D2, `rights_basis_4009_v1.json` |
| A record whose hashes differ from those of its own overlay | `protocol_hash_mismatch` | v1a `change_control` |
| Hashes or a frame header that are not those of the protocol files in force | `protocol_not_in_force`, `frame_not_protocol_frame` | v1a `change_control`, `scoring_frame` |
| A component or confidence record that is not what the modules compute from the inputs it echoes | `component_not_frame_record`, `confidence_not_rule_record` | v1a guardrail GR2, `confidence_rule_v1` |
| A portfolio case that is not a case of v1a, or with another reference date, tier, lane or flood input; a fixture with the id of a v1a case | `case_not_protocol_case` | v1a `case_portfolio` |
| A product 4009 flood input that is not one of the two layers v1a names, with another date, or the accumulated layer outside lane SCN-ENV | `product_4009_layer_not_protocol_layer` | v1a `date_rule.product_4009` |
| A candidate overlay checked without the protocol files (Python only) | `protocol_binding_required` | v1a `change_control`, guardrail GR2 |
| A write under `apps/web/public` of an overlay that is not public, or with a flood input that declares no source product (Python only) | `public_write_not_eligible` | v1a guardrail GR6 |
| A write there of a product 4009 overlay without the confirmed rights record (Python only) | `product_4009_rights_not_confirmed` | `rights_basis_4009_v1.json` |

`planning_overlay.write_overlay` judges the target path as written, with every `..` collapsed, and as the file
system resolves it, so a link or junction to the public folder is the public folder.

## What the fixture can and cannot show

The fixture has 26 rows on 21 invented units: every tier, every reason code, every failed condition C1 to C8, the
would-be classes A to E, every v2 result including "no v2 trigger met", an OBS row that is `dated_other`, a unit
under guardrail GR1, a row with a component that is not computed, the three states of the headline slot and the
three rights levels. Its dates are in 2030.

The units, inputs, dates and unit numbers are invented. What is real in the fixture is what every overlay carries
unchanged from the signed protocols: the frame header (its disclosure text names the tambons of the analysis the
flood anchor was chosen on), the national vulnerability anchors with their receipt hash, and the two protocol
hashes. The fixture notice says so, and a test lists exactly that text.

Two states cannot be built from invented units, because the signed protocol ties them to real names:

- condition C3 `by_construction` (product 4009 in the eight units of the Mae Sai reporting frame only);
- a T2 row that passes the skill condition (two named detectors only).

The v2 results and the headline values in the fixture are invented: no v2 wrapper and no ensemble exist yet.

## Points the protocols leave open

These are shape choices this schema had to make, or rules the protocols do not state. Each needs an owner answer
before task E8 writes a real overlay.

1. **T4 rows.** The protocols say T4 is locked and not reached; they do not say whether an overlay has a T4 row.
   The schema admits one as a placeholder with no value, so the locked state can be shown from data.
2. **Engine rows.** For tier T0 the protocols say "declared per row" and "any A-E". The schema gives an engine row
   synthetic component values, a declared confidence and no v2 class. Whether an engine row gets a v2 class, and
   whether it can be declared `high`, is not stated; `high` is refused everywhere.
3. **A component with no protocol value.** `normalisation.py` raises for a unit with no land, no resident or nobody
   with baseline access. The row then has no FPPS, no would-be class and no leave-one-out; its confidence is low
   (C5) and its class is E by the first rule of class rule v1. The protocols do not describe this row.
4. **Case SE2-dist.** v1a makes it a MUST case with "flood likelihood and exposure only, no routing", "no FPPS and
   no class". The protocols do not say whether it is an overlay. Schema 1.0 does not carry it: every row below T4
   names a routing context and a closure rule and carries a class, and the only row without a class is a unit under
   GR1. The validators refuse a portfolio case named SE2-dist, so its 124 units cannot be written as class E. Either
   a row kind with two components and no class is added (a schema change), or another artifact carries the
   distribution; the owners decide which.
5. **Leave-one-out under GR1.** GR1 names the binding, would-be and v2 classes. The schema also leaves the
   leave-one-out class empty for such a unit and keeps the FPPS values.
6. **One resident count per row.** GR1 and C6 are judged on `confidence.measurements.unit_residents`, which must
   equal the `unit_residents` of the row's exposure record. The vulnerability record has its own `residents` (the
   1 km age counts, another vintage); the validators do not require it to match. Whether it should is not stated.
7. **`temporal_relation` of rows without a flood input.** It is `null` for T0 and T4 rows.
8. **`temporal_relation` from the dates.** v1a defines `event_aligned` (within 3 days of the reference date). The
   validators derive the other two: a dated input that is not aligned is `dated_other`, and an input with no single
   acquisition date is a `season_window`. A scenario row is judged on the dates of its base input the same way.
9. **The date of the 22 Oct layer.** v1a gives that layer its own case with reference date 2024-10-22 and calls the
   case self-dated; it has no field named acquisition date. The validators require a product 4009 flood input to
   carry one of the names v1a gives the two layers, the 22 Oct layer to be dated 2024-10-22, and the accumulated
   layer to have no date and to sit in lane SCN-ENV.
10. **What a case overlay carries.** With the protocol files, a row in lane OBS or SCN-ENV must belong to a case of
    that lane and carry its tier and one of its flood inputs, under a name v1a uses. Rows in lane SCN (the scenario
    cells S1 to S9 built on a base case), engine rows and the T4 placeholder are not compared with the case: the
    protocols do not say which overlay carries them, and a scenario cell has no case id of its own.
11. **v2 when a trigger cannot be evaluated.** v1b notes that the recurrence flag cannot be computed where the JRC
    tile is not on disk. The schema requires all five triggers with a true or false outcome.
12. **v2 triggers the overlay cannot check.** Trigger E is recomputed from the row. For A, C and D the overlay
    holds only part of the inputs (no P75 comparison, no facility, link or recurrence data), so the validators
    check only that a trigger is not met where the row rules it out. Whether the overlay should carry those inputs
    is not stated.
13. **The v2 reason code.** v1a `class_rules.v2.reason_code_mapping` maps v2 triggers to an existing reason code
    plus `trigger_evidence`. `class_v2` carries `trigger_evidence` and no reason code of its own.
14. **No overlay-level confidence.** Plan 7.1 lists the common metadata fields, which include one
    `confidence_class` for the whole file. Rule v1 applies per unit and lane, and scenario confidence is never
    counted with observed confidence, so the header carries none.
15. **Blocks of plan 7.1 not in schema 1.0.** The top-level fields `permitted_use`, `reason_blocked` and
    `event_time`; a top-level `lane` and `flood_input` (schema 1.0 has them per row) and `input_sha256[]` (the
    hashes are on the input records); `age_exposure`, `access`, `travel_minutes`, `equity`, `shelter_2sfca`, the
    ensemble outputs other than the headline slot, and `display_context_package_sha256`. Their modules are tasks
    E5, E9 and E10. Adding them is a schema version change.
16. **`inputs[].role`.** The vocabulary (flood input, routing context, population, age structure, boundaries,
    facilities, permanent water, other) is a shape choice; the protocols name no roles.
17. **`source_product`.** Only `unosat_product_4009` has a meaning; any other identifier is accepted. The rule that
    every flood input of an overlay written under `apps/web/public` declares a source product is a guard added in
    review, so that a product cannot ship unrecognised. It is not a protocol rule.
18. **One row per unit, lane, flood input and scenario.** v1a applies confidence per unit and lane. The validators
    refuse two rows with the same four values. The 540 ensemble cells of task E10 are therefore not rows of this
    overlay; only the headline slot is.
19. **Lane columns of the summary.** Counts are per OBS, SCN and ENG, as the v1a class-coverage table has them;
    SCN-ENV is counted in SCN, and T4 rows in `no_lane`.
20. **Where a would-be class may be shown.** v1a allows it in Command "only for T3 rows that are low because of a
    non-evidence condition" and does not list those conditions. The overlay carries the would-be class and the
    failed conditions; it does not say which surface may show them.
21. **The skill caption of a T2 row.** v1a asks for a "mandatory skill caption" beside a T2 would-be class and gives
    no wording. The overlay carries the T2 skill record (status, conditions, measurements, metric wording) and no
    caption text.
22. **A fixture in public files.** The write gate lets a fixture whose inputs are all public be written under
    `apps/web/public`, without the protocol files. Whether a fixture may ship at all is not stated.
23. **Timestamps.** `source_timestamp` and `generated_at` are checked by pattern only; a calendar check is applied
    to dates, not to instants.
24. **Names.** Plan 7.1 names the schema `planning-assessment.schema.json` and puts the types in
    `packages/contracts/src/`. Task E11 as issued names `planning-assessment-overlay.schema.json` and
    `apps/web/src/lib`; that is what was built. `tests/test_contract_schemas.py` and `packages/contracts/src/index.ts`
    are unchanged.
