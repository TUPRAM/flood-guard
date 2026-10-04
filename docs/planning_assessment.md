# Planning assessment (plan task E8)

The planning assessment turns the measurements of the earlier tasks into the overlay rows of one case: for each
reporting unit, the five components, the confidence record, the FPPS and the classes. This page says what the
code does, where each rule comes from, what a run refuses, and what is still open. The overlay file itself is
described in `docs/planning_assessment_overlay.md` (task E11).

An assessment is planning guidance for preparedness and post-event prioritisation. It is not an official warning
and not an observation of a flood. A road closure in it is a modelled assumption. Class E never means safe.

**Status on 5 October 2026.** The code exists and is tested on invented units only. No run on a real unit has been
made with it, so `outputs/planning_v1/` holds no assessment yet.

Reads of the real inputs made while the code was written, on 4 October 2026 (UTC). None measured a unit, computed
a component or wrote a file. The first run on real units lists them in its receipt (`--development-read`).

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
| `tests/test_planning_assessment.py` | Every component from invented counts against a hand calculation, class rule v1 at each boundary, the confidence rule, guardrail GR1, class rule v2, the verifier. |
| `tests/test_build_planning_assessment.py` | A run from start to end on an invented frame in a temporary folder, and every refusal of the script. |

## How to run it

```
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --check-inputs
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root>
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --verify
python scripts/build_planning_assessment.py --case SE1 --frame mae_sai --external-data <external data root> --replace --reason "<why>"
```

The external data root can also come from `FLOODGUARD_EXTERNAL_DATA`. The script returns 0 when the overlay was
written, 2 when it refused to run (nothing is computed and nothing is written), and 3 when it computed the rows
and could not write the overlay (the receipt is still written, and the rows are reported as computed, see below).

`--check-inputs` checks every input against the file that names it, asks the rights registry and compares the
stages (guardrail GR3). It measures no unit, computes no component and writes nothing. It prints the lineage with
its SHA-256 values and rights levels, and where the overlay would go.

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
| GR3 | Before any unit is measured, the script compares what task E1 and task E5 say of the one flood input, routing context and closure rule: the input identifier and name, the SHA-256 of the closure extent, the canonical SHA-256 of the context, the closure basis, the rule version and the lane. It then compares, unit by unit, the residents the context holds with the residents the access table counted, and the hospital routes. Any difference stops the run. Every row names the same lineage. |
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

Every run also checks the rows of the whole case (`whole_case_checks` in the receipt): every component value and
every FPPS lies between 0 and 100; each FPPS is the weighted sum of its five component values; leave-one-component-out
follows from the FPPS (without a component of weight w and value v, the FPPS f becomes (f - w v) / (1 - w), up to the
rounding of the two scores); and the residents of the rows add up to the residents the access table counted for the
same units. A check that does not hold stops the run before anything is written.

## What the script refuses

A refusal happens before any value of a unit is computed, and nothing is written.

| Refusal | Why |
|---|---|
| A protocol file that is not in force | v1a guardrail GR5 |
| The E1 receipt, the E5 receipt, the E7 receipt or the E7 table missing from the run register, or with other bytes than the register holds | Every input is the file its registered receipt binds |
| A flood extent, the permanent-water layer or the input record that is not the bytes the E1 receipt binds; an access table that is not the bytes the E5 receipt binds | The same |
| A planning context that is not the one protocol v1b names (checked as task E5 checks it), a national-anchor receipt that is not the one v1b names, a boundary file that is not the one the E1 receipt names | The same |
| A flood layer with no rights record, with a record the owners did not confirm, or with a record other than the one the flood input names | `floodguard.rights` |
| An access table that says `usable_by_task_e8: false` (today: both pitch-services tables, open point E5-OP5) | The table's own statement |
| An access table computed from another flood input, other extent bytes or another context; a table whose unit residents differ from the context's | v1a guardrail GR3 |
| An access table whose rows store a ratio | Components are computed from counts |
| Case O1 | Task E1 has no flood input for it and task E5 no table; the rights registry holds no record of Sentinel-1 data (open point E1-OP2) |
| A second run without `--replace --reason` | Every run is reported |

## What a run writes

- **The overlay.** A public overlay goes to `outputs/planning_v1/overlays/`. An overlay below the public level
  stays outside Git, under `<external data root>/proposal_execution/planning_v1/<case>/e8_planning_assessment/`,
  with the licence notice of the rights record beside it when the flood input is product 4009.
- **The receipt**, `outputs/planning_v1/e8_planning_assessment_<case>_<frame>.json`: the inputs with their
  SHA-256, the parameters, both protocol hashes, the lane-purity comparison, the guardrail report, the checks of the
  whole case, the counts of the overlay for the whole case (no value of a single unit), the SHA-256 of the overlay,
  the times, and every earlier run under `run_history`. A receipt that supersedes another says whether the result
  is the same (`supersedes.result_same`); the comparison leaves out the content hash of the overlay, which changes
  with the generation time alone.
- **One register entry**, `outputs/planning_v1/run_register/<receipt name>`, with the path and SHA-256 of the receipt.

When the rows were computed and the overlay cannot be written, the receipt is still written and registered. It
says `overlay_written: false`, gives the reason, the number of rows concerned and the triggers that were not
evaluated, and binds a report outside Git (`overlay_not_written.json`). The report names the units; the receipt in
Git does not. The script returns 3.

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
  definition and the display text protocol v1a gives that lane.
- **Source timestamp.** The schema takes an instant; the overlay states the last date of the flood input's source
  period at 00:00:00 UTC and says so (open point E8-OP4).
- **Where a public overlay sits.** `outputs/planning_v1/overlays/`. The web folder is written by a later task.
- **Rows of a case overlay.** One row for each reporting unit in the lane of the case. No engine row and no locked
  T4 row is added: the protocols do not say which overlay carries them (points 1 and 10 of the overlay page).
- **Thai case titles.** Written by the AI agent. No team language check has been made. The Thai unit names are
  those of HDX COD-AB (`adm3_name1`, where `lang1` says `th`).

## Points the protocols leave open

They are in `planning_assessment.OPEN_POINTS` and in every receipt. None is decided by the code.

| Id | Point | For the owners |
|---|---|---|
| E8-OP1 | A v2 result that depends on a trigger nobody evaluated. The overlay is not written in that case. | Allow "not evaluated" for the v2 axis of a row (a schema change), or build the inputs of B, C and D first. |
| E8-OP2 | Which closure level the overlay row uses. The code takes the default cell of v1b. | Confirm that the row is the default cell. |
| E8-OP3 | The measurements of C7 and C8 for one unit: the hospital service for C7, OSM hospital objects for C8. | Confirm or amend. |
| E8-OP4 | The source timestamp of an overlay whose flood input has no time of day. | Whether the schema should take a date or a period. |
| E8-OP5 | The rights level of an input that has no rights record, and the review of the 2024 age rasters. | Record the review, and say whether open-licence inputs need a registry record. |
| E8-OP6 | What a run reports when its overlay cannot be written. The rows go into the report outside Git as computed, with no v2 result for the rows concerned. | Whether such rows may be shown or used before the overlay exists, and under which label. |
| E8-OP7 | A figure whose own lineage is public, inside an output whose level is below public. The output goes outside Git as a whole; the receipt holds counts for the whole case. | Whether a per-unit figure computed from public inputs only may be committed while the file it was read from stays outside Git. |

## Not built here

The evaluators of v2 triggers B, C and D; the ensemble and the headline (E10); equity, shelter supply and travel
times (E9); the public projection (E12); a pitch-level overlay (it needs a walking context of record first).
