# Planning assessment (plan task E8)

The planning assessment turns the measurements of the earlier tasks into the overlay rows of one case: for each
reporting unit, the five components, the confidence record, the FPPS and the classes. This page says what the
code does, where each rule comes from, what a run refuses, and what is still open. The overlay file itself is
described in `docs/planning_assessment_overlay.md` (task E11).

An assessment is planning guidance for preparedness and post-event prioritisation. It is not an official warning
and not an observation of a flood. A road closure in it is a modelled assumption. Class E never means safe.

**Status on 5 October 2026.** The first runs on real units were made on 4 October 2026 (UTC), for the three Mae Sai
cases. They are reported in `outputs/planning_v1/README.md`, section "Plan task E8", with their receipts:

- **Case SE1** (the 2024 season envelope scenario): the overlay was not written. Four of the eight rows have a v2
  result that depends on triggers nobody evaluated (open point E8-OP1). The eight rows are reported as computed in a
  file outside Git that is not an overlay (open point E8-OP6).
- **Case O2** (the layer of 22 October 2024): the overlay was written and verified. It is outside Git, because its
  lineage is `local`.
- **Case O1** (own radar candidates): refused. Nothing was computed.

The counts above for cases SE1 and O2 are derived from UNOSAT/GISTDA product 4009 and are shared under CC BY-SA 4.0.
Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009. Changed by FloodGuard: each layer was repaired,
projected to EPSG:32647 and clipped to the frames of task E1; road segments were measured against it and closure
rule v1 was applied (task E5); the shares and counts of each tambon were then turned into component values and
planning classes (task E8). The layers are unvalidated preliminary agency extents (Field_Validation=0), used as
provided; FloodGuard did not validate them.

No overlay is in Git and `outputs/planning_v1/overlays/` does not exist: every lineage is below the public level
today (see "Rights levels today").

Reads of the real inputs made while the code was written, on 4 October 2026 (UTC). None measured a unit, computed
a component or wrote a file. The receipts of the runs list them (`development_reads`).

- The shape of the E5 public table of case SE1, the E7 table and receipt, the E1 receipt, the two E1 input
  records, the properties of the permanent-water layer and the E4 receipt was read with every number masked, and
  the field names of the boundary layer were listed.
- `--check-inputs` ran for case SE1 at 17:05:50Z (it stopped at the boundary layer: the Thai name field is
  `adm3_name1`, which was then corrected) and from 17:06:33Z to 17:06:48Z, and for case O2 from 17:06:55Z to
  17:07:01Z. Every input was the file its receipt binds, and the lane-purity comparison passed for both cases.
- `--check-inputs --level pitch` for case SE1 and a run of case O1 were both refused, as they should be.

## Files

| File | What it is |
|---|---|
| `src/floodguard/planning_assessment.py` | The rows of a case from measurements, the guardrail report, the writer and the verifier. It reads no file besides the protocol files. |
| `scripts/build_planning_assessment.py` | The run: it checks every input against the file that names it, measures each unit, calls the module, writes the overlay and the receipt, and registers the receipt. |
| `tests/test_planning_assessment.py` | Every component from invented counts against a hand calculation, class rule v1 at each boundary, the confidence rule, guardrail GR1, class rule v2 with its FPPS gate at 35, the verifier. |
| `tests/test_build_planning_assessment.py` | A run from start to end on an invented frame in a temporary folder, every refusal of the script, a run whose rows fail a check after they were scored, a superseding run, and the exit codes through the command line. |
| `tests/test_planning_assessment_runs.py` | The committed receipts of the runs on real units and the README section that reports them. It computes nothing. |

## How to run it

```
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --check-inputs
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root>
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --verify
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --replace --reason "<why>"
```

The external data root can also come from `FLOODGUARD_EXTERNAL_DATA`. The exit codes:

| Code | Meaning | What is written |
|---|---|---|
| 0 | The overlay was written (or `--check-inputs` passed, or `--verify` found everything the same) | The overlay, the receipt and its register entry |
| 1 | `--verify` found a difference | Nothing |
| 2 | An input check refused the run **before any unit was measured against the flood input** | Nothing |
| 3 | Units were measured and no overlay was written: a v2 result nobody can state, or a guardrail, a check of the whole case, the overlay parser or a measurement that refused the rows | The receipt and its register entry, and a report outside Git |

Every run on real units is reported. From the first measurement of a unit against the flood input, a run always
ends in a registered receipt. A run that scored every unit and then failed a guardrail does not return 2 and does
not go unreported: its receipt says `overlay_written: false`, names the stage (`unit_measurements`, `row_assembly`,
`guardrail_report` or `whole_case_checks`) and a code (`measurement_refused`, `guardrail_failed`,
`whole_case_check_failed` or `overlay_refused_by_the_validator`), and counts the units measured and the rows
scored. The message of the check may name units, so it is in the report outside Git, not in the receipt.

`--check-inputs` makes every check a run makes before it measures a unit against the flood input: every input
against the file that names it, the rights registry, the comparison of the stages (guardrail GR3) with its
unit-by-unit part, and the stored-ratio check of every unit row. It lays no flood layer over a unit, computes no
component and writes nothing. It does sum the residents of each unit from the demand cells of the planning
context, to compare them with the access table. It prints the lineage with its SHA-256 values and rights levels,
and where the overlay would go.

## What a row holds, and where each rule comes from

| Part of the row | How it is computed | Source |
|---|---|---|
| Flood likelihood | `100 x min(1, flooded share of the unit's land outside permanent water / 0.20)`. The two areas are measured by polygon overlay in EPSG:32647 from the E1 extent as provided (reporting frame) and the E1 permanent-water layer (ESA WorldCover 2021 v200, class 80). The record also carries the value at the anchors 0.10 and 0.30. | v1a `scoring_frame.components.flood_likelihood_0_100`, decision D4; `normalisation.flood_likelihood` |
| Exposure | `100 x residents whose cell centre is inside the extent / unit residents`. The cells are the WorldPop 2020 demand cells of the E4 context; a cell counts for the unit whose polygon holds its centre. Share only: no headcount or density anchor. | v1a `scoring_frame.components.exposure_0_100`; `normalisation.exposure` |
| Access gap | From the **counts** of the E5 table at the closure level of the row: for each service, residents with baseline access and residents newly losing it. At the public level the services are hospital (vehicle, 30 minutes) and main-road entry (vehicle, 15 minutes). The shelter service is pitch level only. | v1a `scoring_frame.components.access_gap_0_100`; `normalisation.access_gap` |
| Road criticality | From the two route counts of the same E5 row. | v1a `scoring_frame.components.road_criticality_0_100`; `normalisation.road_criticality` |
| Vulnerability | From the three age counts of the E7 table, on the national P10 and P90 of protocol v1b. The record also carries the value on P5 and P95. The share the table states is not read. | v1a `scoring_frame.components.vulnerability_context_0_100`, v1b `national_vulnerability_anchors`; `normalisation.vulnerability_context` |
| Confidence | `confidence.derive_confidence` (rule v1) with these measurements: the two dates; coverage (by construction for product 4009 in the Mae Sai frame, measured from the product footprint anywhere else); the exposure at the plus and the minus level of the flood input (C4); the component status (C5); the unit residents (C6); the baseline vehicle connected-no-route share (C7); the hospitals reachable at baseline (C8). | v1a `confidence_rule_v1`, readings DR-A07 and DR-A09 |
| FPPS, binding class, reason code | The unchanged scorer, `scoring.score_subdistricts`. Class rule v1 is binding. Low confidence gives class E with reason `low_confidence`. | v1a `scoring_frame.formula`, `class_rules.v1`, decision D6 |
| Would-be class | The scorer rerun with confidence medium, for a low-confidence row with all five components that is not under GR1. Never binding. | v1a `class_rules.v1.would_be_class` |
| Class v2 | A secondary axis, labelled `secondary`, `binding: false`. See below. | v1a `class_rules.v2`, reading DR-A08; v1b `class_rule_v2_inputs` |
| Leave-one-component-out | For each component, the FPPS and the v1 class with that weight at 0 and the other four renormalised. | v1a `scoring_frame.leave_one_component_out`, reading DR-A02 |
| Headline slot | `not_evaluated`, retention `null`. The ensemble is task E10. | v1a guardrail GR8 |

Nothing is scaled by the other units of a batch: each record is a function of its own unit and of declared
constants, and the guardrail check recomputes every record from the inputs it echoes (v1a guardrail GR2).

A row that stores a ratio is refused. The first E5 table held `share_losing_all_routes`, which is the road
criticality divided by 100. `access_counts_from_e5_row` refuses any key that names a share, a ratio, a rate or a
value on the 0-100 scale.

Where the protocol states no value for a unit (no land outside permanent water, no resident, nobody with baseline
access), the component is left out. Rule v1 then records C5 as failed, the row is class E with reason
`low_confidence`, and it has no FPPS, no would-be class and no leave-one-out.

### Each row is the default cell

A row uses the flood input as provided, the closure level that the reference cell of protocol v1b names
(`ensemble_grid.headline_rule.reference_cell`: central passability), the public services, WorldPop 2020, the P10
and P90 anchors and the default weights. The script reads the level from that sentence and stops if the sentence
does not name exactly one level (open point E8-OP2).

### Class rule v2

The triggers are evaluated in the order E, A, B, C, D, and the first one met gives the class. Trigger E (low
confidence, exposure under 10, or FPPS under 35) and trigger A (the v1 class is A and the dependent share is at or
above the national P75) are computed from the row. The outcomes of B, C and D are **inputs** of the module
(`V2TriggerInputs`), and no stage computes them yet:

- B needs each top-20 critical link that intersects the extent closed on its own (task E6 ran no such closure);
- C needs the serving-facility test, and the protocols do not say when a facility "loses all vehicle routes";
- D needs the recurrence flag, and the JRC tiles for the east of the Mae Sai frame are not on disk.

Where trigger E or A is met, the result is stated and a trigger that was not evaluated is written with `met: false`
and evidence that starts with "Not evaluated". Where the result would depend on a trigger nobody evaluated, the
protocols state no result, and schema 1.0 has no way to say "not evaluated". The overlay is then **not written**
(open point E8-OP1). The rows are reported as the run computed them, in a report that is not an overlay (see "What
a run writes"; open point E8-OP6). A unit under GR1 has no v2 class.

## Guardrails

| Guardrail | What the code does |
|---|---|
| GR1 | A unit with fewer than 100 residents gets no binding class, no would-be class, no v2 class and no leave-one-out class. Reason `insufficient_denominator`. Its confidence is still recorded as low with C6 failed, and its FPPS is still stated. |
| GR2 | `normalisation.reject_batch_scaled_components` recomputes every record of every complete row. |
| GR3 | Before any unit is measured against the flood input, the script compares what task E1 and task E5 say of the one flood input, routing context and closure rule: the input identifier and name, the SHA-256 of the closure extent, the canonical SHA-256 of the context, the closure basis, the rule version and the lane. Still among the input checks, it compares, unit by unit, the residents the context holds with the residents the access table counted, and the hospital routes of the table with the graph. Any difference stops the run with exit code 2, and `--check-inputs` reports it. Every row names the same lineage. |
| GR5 | Every rule object comes from `load_assessment_rules`, which refuses a protocol file that is not in force. Every run writes a receipt and registers it. |
| GR6 | The rights level of the overlay is the minimum across its lineage inputs. A pitch-level access gap cannot sit in a public overlay. The script writes nothing under `apps/web/public`. |
| GR7 | An OBS row that is not event-aligned fails C2, so it is class E. The module also refuses such a row with a class above E. |
| GR8 | Every headline slot is `not_evaluated` until the ensemble exists. |

The verifier (`verify_assessment`, and `--verify`) reads the written file back through `planning_overlay.load_overlay`,
bound to the two protocol files, runs the guardrail report, checks that every reporting unit of the case has exactly one
row ("Every cell of every case is reported whatever it shows", v1a `case_portfolio`), and checks that the overlay
names the SHA-256 of the inputs it was computed from. `--verify` also computes the overlay again and compares it
byte for byte with the file the receipt binds. For a run that wrote no overlay, `--verify` computes the report again
and compares it byte for byte in the same way.

`--verify` compares the receipt too, and not only its result block: the whole body except the fields that belong to
one run (the run times, `timing_seconds`, `implementation`, `development_reads`, the kind of run and what it
superseded), and the outputs block. A receipt whose body the code of today would not write does not verify
(`receipt_body_same`, with the fields that differ). The SHA-256 of the builder and of each module is compared with
the receipt and reported (`code_changed_since_the_run`); that alone does not fail the verification, because the
comparison of the body shows whether the change matters.

Every run also checks the rows of the whole case (`whole_case_checks` in the receipt): every component value and
every FPPS lies between 0 and 100; each FPPS is the weighted sum of its five component values; leave-one-component-out
follows from the FPPS (without a component of weight w and value v, the FPPS f becomes (f - w v) / (1 - w), up to the
rounding of the two scores); and the residents of the rows add up to the residents the access table counted for the
same units. A check that does not hold means that no overlay is written and no row is reported; the run itself is
still reported, by its receipt and a register entry, and returns 3 (see "How to run it").

## What the script refuses

A refusal happens before any unit is measured against the flood input and before any component is computed, and
nothing is written (exit code 2). `--check-inputs` makes every one of these checks.

| Refusal | Why |
|---|---|
| A protocol file that is not in force | v1a guardrail GR5 |
| The E1 receipt, the E5 receipt, the E7 receipt or the E7 table missing from the run register, or with other bytes than the register holds | Every input is the file its registered receipt binds |
| A flood extent, the permanent-water layer or the input record that is not the bytes the E1 receipt binds; an access table that is not the bytes the E5 receipt binds | The same |
| A planning context that is not the one protocol v1b names (checked as task E5 checks it), a national-anchor receipt that is not the one v1b names, a boundary file that is not the one the E1 receipt names | The same |
| A flood layer with no rights record, with a record the owners did not confirm, or with a record other than the one the flood input names | `floodguard.rights` |
| An access table that says `usable_by_task_e8: false` (today: both pitch-services tables, open point E5-OP5) | The table's own statement |
| An access table computed from another flood input, other extent bytes or another context; a table whose unit residents differ from the context's, or whose hospital routes contradict the graph; a table with no row for a unit | v1a guardrail GR3 |
| An access table with a unit row that stores a ratio | Components are computed from counts |
| Case O1 | Read at the time of the run, not a fixed sentence: the registered E1 receipt binds no flood input of the case, the registered E5 receipt binds no access table of it, and the rights registry holds no record of Sentinel-1 data (open point E1-OP2). The refusal names what is missing. When all three exist, it says what the builder does not do yet: read the T2 skill measurements of each unit and choose among the candidates |
| The pitch level, also with a pitch-services table that says it is usable | A pitch overlay has to name the walking context and the DDPM shelter list in its lineage, and guardrail GR3 has to compare the walking context. The builder reads and compares the vehicle context only |
| A second run without `--replace --reason` | Every run is reported |

## What a run writes

- **The overlay.** A public overlay goes to `outputs/planning_v1/overlays/`. An overlay below the public level
  stays outside Git, under `<external data root>/proposal_execution/planning_v1/<case>/e8_planning_assessment/`,
  with the licence notice of the rights record beside it when the flood input is product 4009.
- **The receipt**, `outputs/planning_v1/e8_planning_assessment_<case>_<frame>.json`: the inputs with their
  SHA-256, the parameters, both protocol hashes, the lane-purity comparison, the guardrail report, the checks of the
  whole case, the counts of the overlay for the whole case, the SHA-256 of the overlay, the SHA-256 of the rows alone
  (`result.rows_sha256`), the SHA-256 of every lineage input (`lineage_input_sha256`), the times, and every earlier
  run under `run_history`.
- **One register entry**, `outputs/planning_v1/run_register/<receipt name>`, with the path and SHA-256 of the receipt.

A level other than `public` is part of every name: the receipt is `..._<frame>_pitch.json`, the overlay
`..._<frame>_pitch.json` and the folder outside Git `e8_planning_assessment_pitch/`. A run at one level therefore
never supersedes the receipt of another level and never deletes its files. (No pitch run is possible today.)

**A superseding run** (`--replace --reason`). Its receipt names the receipt it replaces by SHA-256 and compares the two
runs under `supersedes`:

- `counts_same`: whether an overlay was written, why not, and the rows by class, reason code and confidence class;
- `rows_same`: the SHA-256 of the rows alone. A row holds every value of a unit and no generation time, commit or
  header text, so this comparison covers every component value and every FPPS. The rows of the replaced run are read
  back from the file its receipt bound, after that file was checked against the SHA-256 the receipt names;
- `lineage_inputs_same`: the SHA-256 of every lineage input;
- `result_same`: true only when the counts and the rows are the same.

The replaced receipt and every file it bound are copied to
`<external data root>/proposal_execution/planning_v1/<case>/e8_planning_assessment/superseded_runs/<time of that run>/`
before anything is written over them, and the copies are listed with their SHA-256 (`copies_kept_outside_git`).

**Licence, credit and change notice.** Product 4009 content ships only under CC BY-SA 4.0 with its credit and a
change notice. When the flood input is a product 4009 layer, the receipt carries a `licence` block: the licence by
name and SPDX identifier, the credit "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009", the standard sentence
of protocol v1a (an unvalidated preliminary agency extent, used as provided; FloodGuard did not validate it), a change
notice that names what tasks E1, E5 and E8 did to the layer, the rights record by path and SHA-256, and the other
inputs with their licences. The report of a run that wrote no overlay carries the same block at its top level. In an
overlay, the change notice of the flood input is the notice task E1 wrote, carried on by the step of this task.

**What the counts in the receipt give away.** The receipt is committed and holds counts for the whole case. A count
that covers every row (all eight rows in one class) states that class for each unit the receipt lists, and a count of
zero states for each unit that it does not have that value. The receipt names the counts that cover every row
(`rights.figures_of_local_level_layers_in_this_receipt.counts_that_cover_every_row`) and says that keeping the rows
outside Git separates nothing for them (open point E8-OP7).

When units were measured and the overlay cannot be written, the receipt is still written and registered. It
says `overlay_written: false`, gives the reason, and binds a report outside Git (`overlay_not_written.json`). For a
v2 result nobody can state, the receipt gives the number of rows concerned and the triggers that were not evaluated,
and the report names the units; the receipt in Git does not. For rows that a check refused, the receipt gives the
stage and the code, and the report gives the message of the check and no row: a row that fails a check is not
reported as a result (open point E8-OP6). The script returns 3.

**Rows as computed** (open point E8-OP6). A run that computed an FPPS and a class for real units reports them. When
the reason is a v2 result that nobody can state, the report also holds every row as the run computed it
(`rows_as_computed`, schema name `floodguard.planning_assessment_rows_as_computed.v1`): the components, the
confidence record, the FPPS, the binding class of class rule v1 with its reason code, the would-be class and
leave-one-component-out, exactly as an overlay row would carry them. Class rule v1 is binding and does not depend on
the v2 axis. The v2 axis of a row concerned carries no `result`: it says `status: not_evaluated`, lists the triggers
that were not evaluated, and gives `met: null` for each of them. Before the report is written:

- every row is checked by `floodguard.planning_overlay` against the two protocol files, on a copy held in memory in
  which the v2 axis of a row concerned is filled in so that the parser can read the row. That copy is never written;
- the guardrail report and the checks of the whole case run on the rows as computed;
- the receipt in Git takes the counts for the whole case (`result.rows_as_computed.summary`), with the rows concerned
  counted under `not_evaluated` in the v2 counts.

The report is **not an overlay**: it names another schema, `floodguard.planning_overlay` refuses it, and no page and
no later task reads it as one. When the flood input is product 4009, the licence notice of the rights record is
written beside it.

## Rights levels today

The flood layer takes its level from the rights registry: `public` for the accumulated layer of product 4009,
`local` for the layer of 22 October 2024. The access table takes the level the table states. An input with no
rights record takes the level the script states for it, with the basis in the receipt:

| Input | Level | Basis |
|---|---|---|
| Planning context, WorldPop 2020, COD-AB boundaries, WorldCover permanent water | `public` | The reading task E5 already uses for its public table |
| WorldPop 2024 age counts (task E7 table) | `local` | Protocol v1b says of the age rasters: "Public derivatives require purpose-specific review." No such review is recorded. |

**Consequence:** every overlay that carries a vulnerability record is `local` today, also for case SE1, and stays
outside Git. One recorded owner decision on that review changes the level; the run is then repeated with
`--replace --reason`.

## Choices this task made that are not rules of the protocols

- **Identifiers.** The overlay schema takes lower-case input identifiers without a colon. The flood input that
  task E1 names `unosat_4009:CHIANGRAI_...` is written `unosat_4009.chiangrai_...`; the overlay and the receipt
  say so. The closure basis of a row names the same identifier.
- **Scenario of a season-envelope row.** Its identifier is the lane (`SCN-ENV`) and its declaration is the
  definition protocol v1a gives that lane, joined to "Shown as: " and the lane's display text. The protocols name no
  field called scenario declaration.
- **Base of a scenario.** For every scenario case of the portfolio, condition C1 is judged on an agency product used
  as provided (`scenario_base`), because SE1 is built on product 4009. A scenario case built on another kind of input
  would need its own value; the builder does not read it from the protocols.
- **Tolerances.** Two sums of the same resident counts by two stages may differ by 0.000001 residents (guardrail GR3,
  and the check of the whole case). A score rounded to two decimals may differ from its recombination by 0.011
  points (the weighted sum and leave-one-component-out in the checks of the whole case). Both are in the receipt
  (`parameters.tolerances`); neither is a number of the protocols.
- **A trigger nobody evaluated, on a row whose v2 result an earlier trigger gives.** It is written `met: false` with
  evidence that starts with "Not evaluated", because schema 1.0 takes true or false only. A reader of `met` alone
  cannot tell it from a measured false (open point E8-OP1; point 11 of the overlay page). In the O2 overlay this is
  trigger B on all eight rows.
- **Rows the protocols do not describe.** A row with a component that is not computed has no FPPS and no
  leave-one-component-out, although protocol v1a says leave-one-component-out is required on every row. A unit under
  guardrail GR1 keeps its FPPS and its five leave-one-out FPPS values, with no leave-one-out class (open point
  E8-OP9; points 3 and 5 of the overlay page).
- **What condition C8 counts.** A hospital counts as reachable for a unit when it snaps to the same connected part
  of the undirected baseline vehicle graph as one or more populated cells of the unit that snap to a road. No travel
  time limits it. The no-route share of condition C7 is 1 for a unit where nobody is connected to the graph, so such
  a unit fails C7 (open point E8-OP3).
- **A run whose rows fail a check.** It is reported by its receipt, with no row (open point E8-OP6).
- **Source timestamp.** The schema takes an instant; the overlay states the last date of the flood input's source
  period at 00:00:00 UTC and says so (open point E8-OP4).
- **Where a public overlay sits.** `outputs/planning_v1/overlays/`. The web folder is written by a later task.
- **Rows of a case overlay.** One row for each reporting unit in the lane of the case. No engine row and no locked
  T4 row is added: the protocols do not say which overlay carries them (points 1 and 10 of the overlay page).
- **Thai case titles.** Written by the AI agent. No Thai speaker of the team has checked them: on 5 October 2026 an
  owner left the Thai wording to the agent, because the team has nobody to check it. The agent read both titles
  again and corrected one: the title of case O2 said น้ำค้าง for residual water, which is the Thai word for dew; it
  now says น้ำที่ยังเหลืออยู่ปลายฤดู (water that still remains late in the season), the wording the replay page uses
  for a remaining extent. The Thai unit names are those of HDX COD-AB (`adm3_name1`, where `lang1` says `th`).

## Points the protocols leave open

They are in `planning_assessment.OPEN_POINTS` and in every receipt. None is decided by the code.

| Id | Point | For the owners |
|---|---|---|
| E8-OP1 | A v2 result that depends on a trigger nobody evaluated. The overlay is not written in that case. Where an earlier trigger gives the result, a trigger nobody evaluated is written `met: false`. | Allow "not evaluated" for the v2 axis of a row (a schema change), or build the inputs of B, C and D first. Say whether `met: false` may stand for "not evaluated". |
| E8-OP2 | Which closure level the overlay row uses. The code takes the default cell of v1b. | Confirm that the row is the default cell. |
| E8-OP3 | The measurements of C7 and C8 for one unit: the hospital service for C7; for C8, OSM hospital objects in the same connected part of the graph, with no time limit. | Confirm or amend; say what "reachable" means in C8 and what the no-route share of a unit with no connected resident is. |
| E8-OP4 | The source timestamp of an overlay whose flood input has no time of day. | Whether the schema should take a date or a period. |
| E8-OP5 | The rights level of an input that has no rights record, and the review of the 2024 age rasters. The age table of task E7 is held at `local` as a lineage input and has been in Git since task E7 wrote it. | Record the review, say whether open-licence inputs need a registry record, and cover the age table that is in Git. |
| E8-OP6 | What a run reports when its overlay cannot be written. The rows go into the report outside Git as computed, with no v2 result for the rows concerned. A run whose rows fail a check reports no row. | Whether such rows may be shown or used before the overlay exists, and under which label; whether rows that fail a check should be reported. |
| E8-OP7 | A figure whose own lineage is public, inside an output whose level is below public. The output goes outside Git as a whole; the receipt holds counts for the whole case. The separation is nominal: a count that covers every row is a statement about each unit, and with the public-lineage components, the age table and the anchors in Git, the vulnerability component, the FPPS and the binding class of each unit can be worked out from committed files. | Whether a per-unit figure computed from public inputs only may be committed while the file it was read from stays outside Git, and whether a level below public is meant to keep such values out of the repository at all. |
| E8-OP8 | The shelter part of v2 trigger C in a public overlay. The DDPM rows are pitch level. Nothing is evaluated yet. | Whether a public overlay evaluates C on hospitals alone. |
| E8-OP9 | Leave-one-component-out and the FPPS of a row with a component that is not computed, and of a unit under GR1. | Whether leave-one-component-out is wanted over the components that exist, and whether a unit under GR1 states an FPPS. |

## Not built here

- The evaluators of v2 triggers B, C and D.
- The ensemble and the headline (E10); equity, shelter supply and travel times (E9); the public projection (E12).
- **The thinned GeoJSON layers of plan stage P8** ("overlay JSON + thinned GeoJSON layers (at most 5 MB per case)").
  This task writes the overlay JSON only. No layer for a map is written, and nothing here makes one.
- **A pitch-level overlay.** It needs a walking context of record first (open point E5-OP5). Its lineage would then
  have to name that walking context and the DDPM shelter list, and guardrail GR3 would have to compare the walking
  context too. The builder refuses the pitch level until that is built, also when a pitch-services table says it is
  usable. The level is already part of the receipt, overlay and folder names.
- **An overlay of case O1.** Beside the inputs that are missing today, the builder does not read the T2 skill
  measurements of each unit from the radar candidate table, and nothing chooses among the three candidates.
- The 5 x 3 class-coverage table of protocol v1a.
