# Planning protocol v1a and v1b: reading guide and signing procedure

For Putu and Rachmania. Drafted by an AI coding agent on 1 October 2026, on owner go-ahead R5, and revised the same day after a review of the first draft.

**Status on 3 October 2026: v1a is signed and in force. v1b is still an incomplete draft.**

- **v1a** was signed in commit `04bca20`, and its SHA-256 (`b6dc549c...a954`) is the last line of `RECEIPTS.jsonl` (commit `6ad6f00`). It must not be edited again; a change needs `planning_protocol_v2`.
- **How it was signed.** Putu told the AI coding agent, in a Claude Code session, that Putu and Rachmania both approve v1a and attest the four statements. The agent typed both signature entries and appended the receipt on that instruction. The file says so in `signature_block.amendments_at_signing`. Rachmania did not type her entry; she can add her own confirmation in a later commit that does not touch v1a.
- **Left open at signing.** Putu answered "not sure", for both owners, to whether any M1-v2 tuning on GEOID tiles has been run. Rachmania is to state it.
- **v1b** has 16 open items left: OI-11 closed when v1a was recorded, and OI-08 (the national anchors) closed on 3 October. Both owners approved v1b in principle (decision log R11). That is not a signature, and no signature entry is filled in.
- **What the owners asked for under R11 is done as far as an agent can do it.** The engineering runs are in section 6. Every choice that only the owners can make is in `planning_protocol_v1b_owner_choices.md`, one short entry each, most important first. All 16 open items wait on those answers, directly or through the route rule (OI-02). OI-09 also waits on the pf-07 frame from Rachmania.
- No FPPS, class or ensemble may be computed for a real unit until v1b is signed and recorded. None was computed in the engineering runs.

The rule for the rest of this guide stands: agents draft, humans sign. For v1b an agent fills a signature entry or appends the receipt only on the owners' explicit instruction, and the file must say that it did.

| File | What it is | Status |
|---|---|---|
| `planning_protocol_v1a.json` | Decision rules (plan row G7a) | `signed` and in force; 11 drafter readings confirmed, DR-A11 amended |
| `planning_protocol_v1b.json` | Engineering addendum (plan row G7b) | `incomplete_draft`: 16 open items (OI-08 and OI-11 closed) and 9 drafter readings |
| `planning_protocol_v1b_owner_choices.md` | The decisions v1b still needs from the owners, with options and a recommendation each | For the owners to answer |
| `planning_protocol_v1a.schema.json`, `planning_protocol_v1b.schema.json` | Shape checks for the two files | n/a |
| `tests/test_planning_protocol.py` | Tests that tie the files to the signed decisions, to `scoring.py` and to the receipt | n/a |
| `scripts/record_planning_protocol_receipt.py` | Checks a signed file and prints its receipt line | n/a |
| `outputs/planning_v1/` | Receipts of the engineering runs made after R11: national anchors, closure regression, SE2-blind district, and the E0 spike with its two candidate corridors and join logs | Evidence for v1b; candidates are marked as such |

Both files are a "declared protocol after exploratory analysis". They are never called preregistered or confirmatory.

## 1. What v1a decides

- **Evidence tiers and lanes.** T0 engine test, T1 scenario, T2 own detector, T3 dated agency map, T4 qualified (locked). Lanes OBS, SCN, SCN-ENV and ENG, and what each may and may not claim.
- **Date rule (D3).** An input counts as observed only within ±3 days of the case date. The accumulated 4009 layer is a season-envelope scenario only. The 22 Oct layer is its own case, O2.
- **Confidence rule v1.** Eight conditions for "medium". "High" is never assigned in this release. Rights are not part of confidence.
- **Scoring frame (D4).** Weights 0.30 / 0.25 / 0.20 / 0.15 / 0.10. Flood anchor 0.20, with 0.10 and 0.30 as sensitivity and the disclosure that 0.20 was chosen after seeing the data. Share-only exposure. National P10/P90 vulnerability anchors. WorldCover class 80 for permanent water.
- **Class rules (D6).** v1 is the unchanged `scoring.py` and is binding. v2 is a labelled secondary axis.
- **Nine guardrails** from plan section 2.3, including the blinding rule: no FPPS, class or ensemble until v1b is in force. Each guardrail now says whether anything enforces it yet. Eight of the nine are not built on this lineage.
- **Cases (D7)** and the case-selection disclosure for SE2.
- **GEOID split, the T2 skill bar and the demo-tambon rule.**
- **Exploratory-knowledge disclosure.** 18 items the team had already seen, where each lives and which rule it could have shaped.
- **Change control.** After signing, any change needs a v2 with a written reason, and every run is reported.

## 2. What v1b decides

The corridor polygon, the grade-join policy (D13), closure rule v1, the facility sets and the corroboration rule, critical-link selection, the national vulnerability anchors, the ensemble grid (540 cells per lane), the selection rules for the scenario and engine cells, and the inputs that class rule v2 needs.

Values the plan states are filled in. Where the plan is silent, the slot is empty and an open item names it (section 6). Where the drafting agent had to pick a reading to fill a value, it is listed as a drafter reading (section 5). A test checks that every empty slot in the file is named by an open item. No test can show that no other unstated choice remains, so add any you find.

## 3. What changed after the review

- **v1b can no longer be signed on status strings.** Each open item lists the exact parameters it must fill. The schema refuses `draft_for_signature` or `signed` while any of them is empty or any section is still open. It also requires the plan's acceptance values: at least 4 hospitals, the three named hospital ways in context, no-route share of at most 10%, and an exact match in the closure regression.
- **A recorded file is tied to its hash.** Once a receipt names a protocol file, a test fails if the file's bytes change, if the signing commit is no longer in the branch history, or if two different hashes were recorded.
- **Two different people must sign.** The schema requires "Putu" in the first entry and "Rachmania" in the second. The receipt script refuses the same name twice.
- **Seven more open items in v1b** (OI-12 to OI-18) for choices the plan leaves unstated.
- **Twenty drafter readings are now marked** in the files (12 in v1a, 8 in v1b). A signed file must have each one set to `confirmed` or `amended`. A ninth v1b reading, DR-B09, was added on 3 October with the national anchors.
- **The disclosure says more.** Item EK-R1 now states that would-be classes A to D were shown for real tambons, after the plan's blinding rule. Two items were added (Hat Yai closure sweep; replay evacuation, shelter and equity panels). Guards that named controls which do not exist yet now say so.

## 4. What to check before signing v1a

1. **Read the exploratory-knowledge disclosure first.** Add anything you have seen that is not listed. This is the section a critic will read. Look hardest at EK-R1: it records a departure from the blinding rule. If you remember which class each tambon was shown, add it.
2. **Go through the drafter readings in section 5.** For each one, set `status` to `confirmed`, or change the rule and set `amended`.
3. **Check one figure.** Plan section 3.4 says the 0.05 anchor saturated in "5 of 8" tambons. The envelope shares in the scratch file `whatif.py` put six tambons above 5%. The file now says both. Correct the sentence in `scoring_frame.components.flood_likelihood_0_100.anchor_disclosure` (reading DR-A11).
4. **State whether any M1-v2 tuning on GEOID tiles has already been run.** The plan wants the split declared before tuning. If tuning has started, add it to the disclosure.
5. **Open decisions.** D5, D8, D10 and D14–D16 were withdrawn on 2 Oct 2026 (decision log R9) and are recorded as withdrawn in v1a.
6. **Rachmania signs her own entry.** The decision log records her signature through Putu. This file needs her own. A name typed into a file does not prove who typed it, so it is better if she makes or co-authors the signing commit from her own git identity.
7. **Schedule.** The plan had v1a on 28 Sep. This draft is dated 1 Oct, and the disclosure lists what was seen in between.
8. **Guardrails.** Eight of nine are marked `not_built`. Signing declares the rules; it does not build the checks. Decide who builds each before scoring starts.

## 5. Readings the drafting agent made

The plan is silent, or says two things, on each of these. The draft picks one reading so the rule is usable. None has authority until you confirm it. "Sensitive" means the reading can change a class or a headline.

### In v1a

| ID | Where | What the plan says | What the draft says | Sensitive |
|---|---|---|---|---|
| DR-A07 | `confidence_rule_v1.scenario_rows` | Condition C1 needs tier T3 or a skill-passing T2. Every scenario row is tier T1. Scenario confidence is called both "derived" and "declared". | For scenario rows, C1 is judged on the base flood input: satisfied for an agency product used as provided, failed for an own T2 candidate. C2 is replaced by the scenario declaration. Read literally, every scenario class would be E. | **Yes, the most** |
| DR-A08 | `class_rules.v2.evaluation` | Five v2 triggers, no order, no fallback. | Order E, A, B, C, D; first match wins; a unit that matches nothing is reported as "no v2 trigger met". | Yes |
| DR-A09 | guardrail GR1, `precedence` | Fewer than 100 residents: "no class" (2.3), low confidence so class E (3.3), and a would-be class shown for denominator failures (5 item 10). | GR1 wins: no class, no would-be class, no v2 class. | Yes |
| DR-A06 | guardrail GR5, `rule` | No FPPS, class or ensemble before the v1b receipt. No qualifier. | Adds "for any real unit", because the existing tests score synthetic fixtures. This does not excuse the 28 Sep replay scores (EK-R1). | Yes |
| DR-A04 | `demo_tambon_rule.rule` | Highest-FPPS headline-eligible unit "in SCN-ENV". No case named. | Restricted to case SE1, using the FPPS of the v1b reference cell. | Yes |
| DR-A01 | `geoid_split.rule` | 29 tiles by tile ID, 15 / 14. No list. | Sorted ascending: first 15 development (9–33), last 14 test (35–50). | Yes |
| DR-A02 | `scoring_frame.leave_one_component_out.rule` | Leave-one-component-out on every row. Weights not stated. | Dropped weight set to 0; the other four renormalised. | No |
| DR-A03 | `demo_tambon_rule.tie_break` | No tie-break. | Lowest `subdistrict_id`. | No |
| DR-A05 | `evidence_tier_model.no_assumed_components_in_obs_or_scn` | No assumed component "in the OBS or SCN lanes"; assumed completions only as T1 arithmetic. | Plan wording restored. Reading: assumed-completion arithmetic is a separate labelled table, never a case row or scenario cell. | No |
| DR-A10 | `date_rule.product_4009.accumulated_layer` | Union spans 1 Aug–22 Oct (plan 0), "1 Aug–12/22 Oct" (plan 4.1), "Aug–Oct" (decisions). | Records the layer name `CHIANGRAI_20240801_20241012_AccumulatedFlood` as it is. | No |
| DR-A11 | flood-anchor disclosure | "5 of 8" tambons saturated. | Quotes the plan and states that the retained shares show 6 of 8. | No |
| DR-A12 | case H1, `case_reference_date` | H1 is an OBS case with no reference date. | Self-dated on its post-event acquisition: 2025-11-24. | No |

### In v1b

| ID | Where | What the plan says | What the draft says | Sensitive |
|---|---|---|---|---|
| DR-B01 | closure levels and the passability axis | "strict / central / permissive, with delay penalty k = 2 / 4 / 6"; delay formula stated for central only. | k = 2 with strict, 4 with central, 6 with permissive (540 cells). The other reading gives 1,620 cells. | Yes |
| DR-B03 | critical-link ranking | "Demand-weighted SPT flow". No demand layer, no tie-break. | WorldPop 2020 residents per origin node; ties on stable edge ID. | Yes |
| DR-B06 | scenario S3 | "Top-3 pre-ranked critical links per tambon". No rule for assigning a link to a tambon. | By where the edge lies; a boundary-crossing edge goes by its midpoint. | Yes |
| DR-B07 | `blinding` | Context, access and closure builds may run before v1b. | Also allows the baseline critical-link ranking (E6) and the national percentiles. | Yes |
| DR-B02 | closure geometry | No measurement rule; "any intersection" undefined. | Straight node-to-node segment; intersected when more than 1e-6 m is inside the extent, as in the finals code. | No |
| DR-B04 | national anchors, `allocation` | No rule for assigning 1 km cells to tambons. | Projected-area fraction. | No |
| DR-B05 | `ensemble_grid.one_at_a_time` | Terrain proxy listed under axis 4. | Run one at a time on O1, outside the 540 cells. | No |
| DR-B08 | scenario S8 base | O2 (plan 6.2) or O1 only (plan 3.4). | O1. | No |
| DR-B09 | national anchors, unit set and percentile rule | "National tambon percentiles". No unit set, no percentile rule. | Every unit with at least 100 modelled residents, each counted once; linear interpolation; six decimal places. Added on 3 October with the anchor values. | **Yes**: weighting units by residents would put P10 at 0.258 in place of 0.351 |

## 6. Open items in v1b

v1b cannot be signed until all 18 are closed and every parameter they name is filled in. None needs a download. Items OI-12 to OI-18 were added after review.

On 3 October 2026 two items are closed, six are partly filled or measured (OI-01, OI-03, OI-04, OI-05, OI-06, OI-09), and the rest wait for an owner decision. The decisions are set out in `planning_protocol_v1b_owner_choices.md`.

| ID | What is missing | What produces it | Who | State on 3 October |
|---|---|---|---|---|
| OI-01 | The corridor polygon file and its SHA-256 | E0 spike, then E4 | Agent with Putu | Open. Two candidate polygons are built; waits on OI-02 |
| OI-02 | The rule that picks the trunk/primary routes to the three hospitals (a proposal is in the file) | Owner decision | Putu | Open. The spike shows the proposal as written fails the plan's acceptance (see below) |
| OI-03 | E0 spike values: hospitals (≥4), the three hospital ways in context, edges, time, RAM, grade splits, no-route share (≤10%) | E0 spike | Agent with Putu | Open. Measured for two route rules; waits on OI-02 |
| OI-04 | Grade-join tolerance (proposal: 0 m) and the logged join list | E4 | Agent with Putu | Open. The tolerance is filled in (0 m, from D13). `grade_join.py` is written and a candidate log exists for each corridor; the log of record waits on OI-02 |
| OI-05 | Closure rule: length thresholds for motorway, residential and unclassified roads; the delay rule under "strict"; the regression result (1,824 walking / 1,738 vehicle, exact match) | Owner decision; E3 | Putu; agent | Open. The regression is recorded: exact match. The two rule points are owner decisions |
| OI-06 | Main-road entry definition; shelter match distance; facility counts in the corridor; Mae Sai Hospital's OSM ID | Owner decision; E4 | Putu; agent | Open. The hospital's OSM ID is filled in. Counts are measured as candidates, except corroborated shelters. The two definitions are owner decisions |
| OI-07 | Destination set for the critical-link ranking; whether the ranking is bound here or in the first run receipt | Owner decision; E6 | Putu; agent, Rachmania reviews | Open: owner decision |
| OI-08 | National anchors P5, P10, P75, P90, P95; the tambon set and percentile method; the output receipt | E2 (run once) | Agent, Putu reviews | **Closed** on 3 October; reading DR-B09 awaits confirmation |
| OI-09 | The Mueang Chiang Rai frame pf-07 (file, tambon list, routing and hospitals); the SE2-blind district | P1; a population ranking | Rachmania; agent | Open. The SE2-blind district is filled in. The pf-07 frame is Rachmania's |
| OI-10 | Three unstated points: reference cell for class retention, k for S3b, selection rule for E3 | Owner decision | Putu, Rachmania | Open: owner decision |
| OI-11 | The recorded SHA-256 of the signed v1a | Signing v1a | Putu, Rachmania | **Closed** on 2 October |
| OI-12 | The terrain / remoteness proxy: definition and anchor. It is an ensemble level and the S8 cell, and the plan defines neither | Owner decision | Putu, Rachmania | Open: owner decision |
| OI-13 | The formula for "2024-rescaled demand" | Owner decision | Putu, Rachmania | Open: owner decision |
| OI-14 | Flood-state levels for M1-literal, UN-SPIDER and A6′, and the threshold that turns the A6′ probability into an extent | Owner decision | Rachmania; Putu confirms | Open: owner decision |
| OI-15 | "One pixel" in metres for the plus level and for vector agency products (confidence condition C4 depends on it) | Owner decision | Putu | Open: owner decision |
| OI-16 | How DDPM shelters enter a vehicle-only ensemble: mode, threshold, publication level, and retention for public overlays | Owner decision | Putu, Rachmania | Open: owner decision |
| OI-17 | Scenario S5: a slot for the add_destination node list, and which class decides "A or B tambon" | Owner decision; E4 | Putu; agent | Open: owner decision |
| OI-18 | Class rule v2 inputs: when a link "isolates" residents, which facility "serves" a unit, how JRC occurrence becomes a unit flag | Owner decision | Putu, Rachmania | Open: owner decision |

### What the engineering runs found

All runs are context, access or closure builds, or national constants, which the blinding rule allows before v1b. Each wrote a receipt under `outputs/planning_v1/` with its input hashes, a source timestamp, a confidence class and its assumptions. None wrote a value for a single tambon.

**National anchors (OI-08, closed).** P5 0.313095, P10 0.351416, P75 0.454083, P90 0.477677, P95 0.494407, over 7,425 `tha_admin3` units; none had fewer than 100 residents. Receipt `national_vulnerability_anchors_v1.json`, SHA-256 `6d59270a…c816`. A second run with `--verify` reproduced the values and the hash of the per-unit table. Two things to know before confirming DR-B09:

- Weighting units by residents would move P10 to 0.258 and P90 to 0.458. The plan says "tambon percentiles", so the file counts every unit once.
- P10 and P90 are only 0.126 apart. A difference of 1.3 points of dependent share moves the vulnerability component by 10 of its 100 points.

**Closure regression (OI-05, recorded).** The permissive level of the new `closure_rules.py` gives 1,824 walking and 1,738 vehicle closed edges on the AOI-01 finals contexts. Both lists equal the finals lists exactly, with the same intersection lengths. Receipt `closure_rule_v1_regression.json`, SHA-256 `3659efc2…9953`.

**E0 spike (OI-01, OI-03, OI-04, OI-06: candidates).** The vehicle context was built once for each of two route rules.

| | Proposal as written: buffer the trunk and primary segments of the fastest path | Whole path: buffer every segment of the fastest path |
|---|---|---|
| Three named hospital ways in context | **No**: Mae Fa Luang (way 549948901) is outside | Yes |
| Hospital objects in context (plan: at least 4) | 4: three named hospitals and one unnamed OSM object | 6: four named hospitals, one duplicate node of Mae Fa Luang and one unnamed OSM object |
| Edges | 57,727 | 65,328 |
| Wall time, peak RAM | 2.64 min, 0.55 GiB | 2.96 min, 2.44 GiB |
| Grade splits; endpoint joins under D13 | 345; 319 | 371; 345 |
| Baseline no-route share (plan: at most 10%) | 0.075% with joins, 1.41% without | 0.075% with joins, 1.41% without |
| Corridor area | 683 km² | 827 km² |
| OSM hospitals with a DGA record within 150 m | 4 of 4 | 6 of 6 |
| Located DDPM shelters in the routing context | 78 | 82 |

- **The proposal as written cannot be signed.** The fastest road to Mae Fa Luang hospital has no trunk or primary segment (15.7 km secondary, 14.9 km tertiary), so no buffer reaches it. The schema requires the three named ways in context.
- Timing was taken on a machine with other sessions running, not in the declared compute window. Peak RAM is the Python process only. The 2.44 GiB of the whole-path run is reached while the spike buffers the path, before the context build starts; the run on the smaller corridor never exceeds 0.55 GiB.
- Each corridor was built twice. Both times it gave the same polygon, the same join log and the same context hash.
- About 8% of the frame's residents (6,610 of 81,837) are more than 250 m from a road node and are not connected to the graph. They are outside the no-route share by definition.
- The union of the eight tambons is 214 m² larger than AOI-02 allows, and the unchanged builder refuses that. Both runs clipped the union to AOI-02, which matches the declared tolerance. The wording of `context_call.aoi_geometry` needs that correction when OI-01 closes.
- The corroborated-shelter count is not measured: it needs the match distance (an owner decision) and an OSM building extract.

**SE2-blind district (OI-09, filled in).** Phan (TH5705) is the most populous Chiang Rai district after Mueang Chiang Rai, by WorldPop 2020; Mae Chan is second, 5.3% behind. No flood layer was read. The plan gives no rule for which tambons are the "amphoe seat".

**Mae Sai Hospital (OI-06, filled in).** OSM way 371233866.

### What happens after the owners answer

1. The agent writes each chosen value into its parameter and closes the item, as in "Steps for v1b" below. The owners' answers are quoted in each closure.
2. OI-01 and OI-03 close from the spike receipt of the chosen route rule.
3. OI-04 and the counts of OI-06 are taken from the E4 context build of record. The same inputs give the same context, so the join count will equal the candidate's. E4 also adds the corroborated-shelter count.
4. OI-09 still needs the pf-07 frame from Rachmania.
5. Only then can the status move to `draft_for_signature`.

On OI-07 and OI-17: plan row G7b lists only E0 and E4 as dependencies, but plan 6.3 says links and nodes are fixed before any scoring. Choose one and write it in the `binding` field: `bound_here` (build the list before signing and record its SHA-256 in v1b) or `bound_in_first_run_receipt` (sign with the rule alone; the SHA-256 goes into the first run receipt, before any scoring).

If a case is dropped under the plan's cut lines (SE2-blind, for example), write that in its parameter instead of leaving it empty. An empty parameter always blocks signing.

The proposals in OI-18 contain two numbers, 100 residents and 10 percent, that the drafting agent made up to have something to react to. They have no data behind them.

### Inputs for the national anchors

The WorldPop 2024 1 km age rasters are **not** under `C:/Users/iputu/Documents/FloodGuard_external_data`. They are already on disk at `C:/Users/iputu/Documents/Project Support/FloodGuard/open-data/2026-09-23-worldpop-age-2024-r2025a-1km-ua/`: 20 files `tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif`, 51,593,135 bytes, manifest SHA-256 `f7a16987…8356c`, status PASS. The national tambon boundaries (COD-AB `tha_admin3`) are under `FloodGuard_external_data/open_context/hdx_cod_ab/`. **No download is needed for the anchors.**

### Downloads that need your approval

None is needed to close a v1b open item. Each is needed later. To approve or refuse one, an owner sets `approved` to `true` or `false` and fills `approved_by` and `approved_on` in the same entry.

| ID | File | Source | Size | Needed for |
|---|---|---|---|---|
| DL-1 | JRC Global Surface Water v1.4 `occurrence_90E_20Nv1_4_2021.tif` (seasonality optional) | JRC download page | about 70–100 MB (+30 MB) | JRC sensitivity note and v2 class D fallback south of 20°N (SE2) |
| DL-2 | JRC `occurrence_100E_30Nv1_4_2021.tif` (seasonality optional) | JRC download page | about 70–100 MB (+30 MB) | The same, for the strip of Mae Sai east of 100°E. Not in the prep pack; found from tile bounds |
| DL-3 | `Copernicus_DSM_COG_10_N19_00_E099_00_DEM.tif` | AWS `copernicus-dem-30m` | about 40–60 MB | Terrain south of 20°N. Not used by any v1b parameter |
| DL-4 | One Sentinel-1 GRD SAFE, 18 Sep 2024 | CDSE (login) | about 1.3 GB | D12 fallback, only without a GEE account |

## 7. How to sign and record the hash

### What exists on this lineage

No script appends to `RECEIPTS.jsonl`. Its 49 lines were appended by hand, one JSON object per line, with `schema_version` `floodguard.proposal_execution_receipt.v1`. The automated track binds a protocol to a commit by reading it with `git show <commit>:<path>` (`scripts/acquire_earth_search_automated_optical_v2.py`). The procedure below follows both conventions. `scripts/record_planning_protocol_receipt.py` checks the signed file and prints the line; a person appends it.

Four rules:

- **The hash is taken over the committed JSON bytes, after the signature block is filled.** The file never contains its own hash.
- **A file is in force only when its line is in `RECEIPTS.jsonl`.** The status field alone does not make it so. Between the signing commit and the receipt commit, the tests report the file as "signed but not in force".
- **After the receipt, the file is not edited again.** One changed byte breaks the hash, and the test `test_recorded_protocol_still_has_the_bytes_its_receipt_names` fails. A change needs `planning_protocol_v2`.
- **The signing commit must stay in the branch history.** The receipt names it as `source_commit`.

### Where to sign

The decision log says the hash goes into `RECEIPTS.jsonl` on the `codex/thai-event-selection` lineage. This draft sits on `claude/planning-protocol-v1`, cut from that branch at `96fab6e`.

1. A human first brings this branch into the lineage branch, by fast-forward or with a merge commit.
2. Sign on the lineage branch.
3. Once a signing commit exists, **never squash and never rebase** the commits that hold it. A squash or rebase gives the signed file a new commit, the receipt then points at a commit that is not in the history, and the test above fails. Merge with a merge commit or a fast-forward only.

Another session also works on that lineage and may append to `RECEIPTS.jsonl`. If the file conflicts at its end when branches meet:

- Keep every line from both sides, whole and unedited.
- Put the other side's lines first and the protocol line after them.
- Do not reorder, edit or re-wrap any existing line, and leave no blank line.
- Run the protocol tests again. The receipt stays valid, because its signing commit is still in the history.

### Steps for v1a

Run from the repository root, in Git Bash. `python` means the project environment (`uv run python`, or the venv's `python.exe`).

1. **Amend and sign.** Edit `docs/proposal_execution/planning_protocol_v1a.json`:
   - Set the `status` of each entry in `drafter_readings` to `confirmed` or `amended`. For an amended one, change the rule it points to as well.
   - Make any other amendments. List each amendment, in a sentence, in `signature_block.amendments_at_signing`.
   - Set `"status": "signed"`.
   - Replace `status_note` with: `"Signed. In force only once the SHA-256 of this committed file is recorded in docs/proposal_execution/RECEIPTS.jsonl."`
   - Each signer fills their own entry: `signed_by` (full name; the first entry must contain "Putu", the second "Rachmania"), `signed_at_utc` (like `2026-10-02T03:00:00Z`) and `attestation` (one sentence confirming the four statements in `attestations_required`).
   - Keep the two-space indent, ASCII characters, LF line endings and one final newline. A test checks the exact formatting.
2. **Tell the tests.** In `tests/test_planning_protocol.py` set `EXPECTED_STATUS["v1a"]` to `"signed"`.
3. **Run the tests.**

   ```bash
   python -m pytest -q tests/test_planning_protocol.py tests/test_scoring.py tests/test_scoring_sensitivity.py
   ```

   A few tests are skipped once a file is signed. One of them reports "SIGNED BUT NOT IN FORCE". That is expected until step 7.

4. **Make the signing commit.** Only these two files. The working tree must be clean afterwards.

   ```bash
   git add docs/proposal_execution/planning_protocol_v1a.json tests/test_planning_protocol.py
   git commit -m "docs(protocol): sign planning protocol v1a"
   git status --porcelain   # must print nothing
   ```

5. **Build the receipt line.** The script takes one argument, `v1a` or `v1b`. It writes the line to a file outside the repository so you can read it before anything is appended.

   ```bash
   python scripts/record_planning_protocol_receipt.py v1a > ../v1a_receipt_line.json
   cat ../v1a_receipt_line.json     # read it: it must be one line
   ```

   The script refuses, with a line starting `REFUSED:`, unless all of these hold:
   - `git status --porcelain` is empty, and the committed bytes equal the working file;
   - the committed file has status `signed` and validates against its schema;
   - the two `signed_by` values are different people and name Putu and Rachmania;
   - no drafter reading still awaits confirmation;
   - `RECEIPTS.jsonl` does not already record a hash for this file;
   - the protocol and scoring tests pass. The script runs them itself and records the result.

   It reads the file with `git show`, so it hashes exactly what was committed. It reads the open decisions from the file. Do not hash `git show` output through PowerShell: PowerShell 5.1 re-encodes the bytes.

   `human_acceptance` stays `false`, as in every earlier receipt: in this file it means independent or downstream acceptance, which a team governance signature is not.

6. **Append the line you read.** Append it to the end of `docs/proposal_execution/RECEIPTS.jsonl` and change nothing above it.

   ```bash
   cat ../v1a_receipt_line.json >> docs/proposal_execution/RECEIPTS.jsonl
   python -c "print(list(open('docs/proposal_execution/RECEIPTS.jsonl','rb').read()[-2:]))"  # must print [125, 10]
   git diff --stat docs/proposal_execution/RECEIPTS.jsonl                              # must show 1 insertion
   ```

7. **Commit the receipt.**

   ```bash
   python -m pytest -q tests/test_planning_protocol.py -rs    # the "NOT IN FORCE" skip is gone
   git add docs/proposal_execution/RECEIPTS.jsonl
   git commit -m "docs(protocol): record the planning protocol v1a hash"
   ```

8. **Check it.** The tests now compare the file with the receipt on every run. To check by hand: the last receipt's `output_hashes.planning_protocol_v1a_sha256` must equal the SHA-256 of `git show <source_commit>:docs/proposal_execution/planning_protocol_v1a.json`, and `git merge-base --is-ancestor <source_commit> HEAD` must succeed. From this commit on, v1a is in force.

### Steps for v1b

1. **Close the open items, one at a time.** For each item, in one edit:
   - write a value into every parameter listed in its `parameter_pointers`;
   - set the item's `status` to `"closed"`;
   - add a `closure` object (`closed_on`, `closed_by`, `value_or_location`, `evidence_sha256`).

   When none of a section's items is open, set the section's `status` to `"fixed"`. The tests pass after each closure, and they fail if an item is closed while one of its parameters is still empty. Three things to know:
   - **OI-05:** record the regression result when E3 runs, even if it does not match. The file cannot be signed until `closed_edge_ids_match_exactly` is `true`.
   - **OI-08:** fill the five anchor values and close the item in the same edit, with the output receipt.
   - **OI-11:** copy the hash from the v1a receipt line into `depends_on.v1a_sha256`. A test checks it against the v1a file and the receipt.
2. **Move to "draft for signature".** Set `"status": "draft_for_signature"` in the file and set `EXPECTED_STATUS["v1b"]` to `"draft_for_signature"` in `tests/test_planning_protocol.py`. Run the tests and commit both files. The schema refuses this status while any item is open, any named parameter is empty or any section is not fixed.
3. **Sign and record.** Follow steps 1–8 above with `v1b` in place of `v1a`: resolve the eight drafter readings, sign, set `EXPECTED_STATUS["v1b"]` to `"signed"`, commit, run `python scripts/record_planning_protocol_receipt.py v1b`, append the line and commit it. For v1b the script also refuses unless every open item is closed with its parameters filled, and `depends_on.v1a_sha256` equals both the committed v1a file's hash and the v1a receipt.

**Only after the v1b receipt is committed may any FPPS, A–E class or ensemble be computed for a real unit.**

## 8. What the agent did and did not do

When the two files were drafted (1 October) the agent ran nothing. After the owners' approval in principle (R11) it did the engineering work in section 6; each receipt carries its time in UTC:

- It computed the national anchors once and closed OI-08.
- It ran the closure regression, the SE2-blind population ranking and the E0 context spike for two candidate corridors.
- It added four modules with tests (`normalisation.py`, `closure_rules.py`, `grade_join.py`, `ddpm_shelters.py`) and the four scripts that wrote the receipts. They await Putu's review.

It did not, at any point:

- append to `RECEIPTS.jsonl`, sign anything, set the v1b status to `draft_for_signature`, confirm any reading, push, merge or download;
- compute any FPPS, A–E class, ensemble cell or component value for a real unit;
- fill a parameter that is an owner decision, or close an item that depends on one;
- change one byte of the signed v1a;
- build any of the guardrail checks marked `not_built`.
