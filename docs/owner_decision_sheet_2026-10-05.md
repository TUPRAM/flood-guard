# Owner decision sheet, 5 October 2026

Status: **PENDING** (questions for both owners; nothing on this sheet is decided)

For Putu and Rachmania. Written by an AI coding agent on 5 October 2026 and revised the same day after a review
(the changes are listed at the end). The team rule is "agents draft, humans sign": this sheet is not a decision, and
no code reads it. It gathers every point that waits for you, from the files listed at the end, so that you can
answer in one sitting. Nothing was computed for it. Every figure is copied from one of those files.

## Dates first

These have a date this week or next, or are overdue. None of them is a question of parts 1 to 3, so they are easy
to miss. The full list of things only a person can do is near the end.

| When | What | Who | Where on this sheet |
|---|---|---|---|
| Overdue (was due Fri 2 Oct) | Ask the organisers: the length of pitch and questions, whether the website may be shown running, the date of Mentoring II. | Callixta, in the plan | action 11 |
| Tue 6 Oct | Who receives the check sheet for shelter candidates, and do the six role codes fit? The date is the roadmap's, as the decision log quotes it. | Both | follow-up FU8a, under Q55 |
| Sat 10 Oct | The plan's cut-off for replies to the outreach: a flood product from GISTDA dated to the event, the AIT/JAXA permission, the UNOSAT 3991 vector. | Rachmania; Putu for the UNOSAT message | action 10 |
| Wed 14 Oct | The plan's Mae Sai completion check. | Both, with Callixta | the dates under the actions |
| Thu 15 Oct | Desk check of the 20 highest-ranked critical links. | Rachmania | action 7 |

## Summary in ten lines

1. The first planning scores for real tambons exist. They are for case SE1, the 2024 season-envelope scenario: class B once, D three times, E four times. They are scenario results, not an observation of any day.
2. No page can show them yet. Four answers stand between the SE1 scores and a page: **Q1** (the result file may be written), **Q2** (the review of the age data, which keeps every score below the public level), **Q3** (the words for a class not yet shown to be stable) and **Q4** (you have read the results, decision R18). The Command page needs a fifth, **Q5**.
3. Three record drafts wait for you in `docs/proposal_execution/`: the age-data review (Q2), the Sentinel-1 rights record (Q7) and the walking-build window (Q8). Each is pending, and no code reads any of them.
4. No class can be called stable yet. 90 of the 180 re-runs the stability rule needs cannot be made until **Q3** is answered. Until then a class can at most be shown as "unstable: verify".
5. Case O2 (the layer of 22 October) is computed and is held at `local` until its rights record names that layer (**Q6**) and the age data are cleared (Q2). The radar case O1 cannot be scored: it needs Q7 (rights) and Q9 (where the radar pixels sit on the map). Its rows would be class E anyway: the radar method gave no answer for 77.3% of the area, and the limit is 20%.
6. The new Command page is built at a temporary address, on a branch that was never pushed, so no preview of it exists yet (Q11). Choices 3 to 6 of its plan are built as recommended. Of choice 2 the header name is built and the address change is not. Choice 7 is not applied.
7. Part 3 names 77 of the 96 open points of the engine, radar and file-format tasks: places where the signed protocols are silent. For most the recommended answer is "keep what the code did", and one reply settles a whole group. One item is of another kind: Q30 records a run that departs from a signed sentence.
8. Seven possible changes are marked **v2**: they cannot be answered here, because they would change a signed rule after the scores were seen. They need a new protocol version with a written reason.
9. Part 4 blocks no score and no page, and most of it can wait until after the pitch (31 October 2026 in the plan). A last table lists things only a person can do, with their dates.
10. A recommendation is not a decision. Nothing changes until your answer is a new row in the decision log, after R18.

## How many items, and how to answer

| Part | What it holds | Items | Questions | Open points of the engine, radar and file-format tasks named in it | Other points in it |
|---|---|---|---|---|---|
| 1 | The few answers that unblock the most | 9 | Q1 to Q9 | 20 | decision R18: read the results; decision R17, point g |
| 2 | The new Command page, and what decision R17 left open | 11 | Q10 to Q20 | 0 | plan choices 2 to 7; R17 part 1 and points a to f and h; ten build choices |
| 3 | Reading rules the protocols leave open | 14 | Q21 to Q34 | 77 | download DL-2; six choices of plan task E8; the register of later runs |
| 4 | Blocks no score and no page | 21 | Q35 to Q55 | 9 | plan choice 8, second half; nine items of the merge report; three downloads; 20 rows of replay follow-ups |
| | Things only a person can do (not questions) | 18 | actions 1 to 18 | | |

Those tasks have 96 open points in all: 72 with an id in `outputs/planning_v1/README.md` and the 24 numbered points
of `docs/planning_assessment_overlay.md`, written here as E11-1 to E11-24. Each is in one item at least. Some are
split over two or three parts, so the column adds up to 106.

**How to answer.** Reply with the question number and a word, for example `Q1 yes`. "Yes" always means "as
recommended". An option number picks another option: `Q9 option 4`. Several at once is fine:
`Q24 yes, Q25 yes, Q26 yes`. Where one word is not enough, the item says what else is needed (a provider page to
check, a date, a name). The questions are numbered Q1 to Q55, and options are numbered, so that nothing here can be
taken for a plan task (A4, E8), a confidence condition (C7), a class or a trigger (A to E), or a decision of the
decision log (D6, R17). A table at the end places an answer given with an id of the first version of this sheet.

**What a yes does.** The agent writes your answer into `docs/decision-log-d1-d16.md` as a new row after R18, with
the date and how it was given. Only then does a file or a line of code change, in a reviewed change. Any run on real
tambons that follows is reported with a receipt, as every run is.

**Three rules behind every recommendation.**

1. No recommendation adds a rule to the signed protocols. Where the only correct route is a new protocol version,
   the item says **v2** (`planning_protocol_v2`, with a written reason and the outputs it affects, as the change
   control of both protocols asks).
2. The scores of SE1 and O2 are known since 4 October. A reading that could move a score or a class is therefore
   not changed now. The recommended answer keeps what was run, and a different rule goes to v2.
3. No recommendation lets a page say more than the data supports. A scenario stays a scenario, class E never means
   safe, and a class is planning guidance, not an official warning.

**Where to start.** The dated list above. Then Q1 to Q6 in order: they decide whether SE1 and O2 can be shown
outside the team. Q1, Q3, Q5 and Q6 can be answered from this sheet. Q2 and Q4 cannot: Q2 needs a provider page
checked, and Q4 needs two long README sections read and one desk check, so both take reading time and not a
one-word reply.
Q7 to Q9 concern the radar case and the shelter part. By their own text they lead only to class E rows that still
need engineering, or to pitch-level tables. After that, Q10 and Q11 (see the pages), then the rest of part 2, then
each item of part 3 with one `yes`, with Q30 answered on its own.

## Words used

**General**

| Word | Meaning here |
|---|---|
| Tambon | Subdistrict. The Mae Sai frame has eight. |
| Plan; plan task | Restructuring plan v2 and its numbered jobs: E for the scoring engine, A for the radar work, U for pages, V for checks. Always written "plan task A4" here. A question of this sheet is always Q and a number. |
| Open point | A place where the signed files are silent and the code had to choose. Each has an id such as E8-OP1 (in `outputs/planning_v1/README.md`) or E11-1 to E11-24 (the numbered points of the overlay page). |
| Protocol v1a, v1b; v2 | The two signed rule files. v2 is a new version: the only way to change a signed rule, with a written reason. |
| Guardrail (GR1 to GR9) | Nine safety rules in protocol v1a. GR6 says where a result may be written, GR8 when a class may be called stable, GR9 keeps out two flood products the team has no permission for. |
| Reading (DR-…) | A "drafter reading": a choice the drafting agent made where the plan was silent, which you confirmed at signing. DR-B04: a 1 km age cell is shared among tambons by area. |
| Receipt | The small file every run writes: inputs and outputs by SHA-256 (a fingerprint of the bytes), parameters, times. |
| Of record; superseding run | "Of record" is the one run or build that later steps may rest on; anything else is a candidate. A superseding run replaces an earlier one: the builder asks for the flags `--replace --reason`, the new receipt names the old one, and the old one stays in the history. |
| Compute window | A few minutes in which no other FloodGuard job runs on the machine, written into the receipt. |
| Lineage | The list of inputs a result was made from. |
| Rights level | `local`, `pitch` or `public`. A result takes the lowest level among its inputs, and only a `public` result may be written under the website's public folder (guardrail GR6). What `local` and `pitch` allow beyond that (in Git, on a slide) is written in no signed file: Q21 asks. |
| Raster, vector | A raster is a grid of cells. A vector layer holds outlines. |
| DDPM; JRC | The Department of Disaster Prevention and Mitigation, whose national shelter list is used. The European Commission's Joint Research Centre, whose surface-water maps show how often a place was water. |

**Scores, classes and cases**

| Word | Meaning here |
|---|---|
| FPPS | Flood Preparedness Priority Score, 0 to 100, from five components: flood likelihood, exposure, access gap, road criticality, and vulnerability/context. |
| Class, rule v1 | The A to E class that counts (the binding one). |
| Class, rule v2; trigger | A second-opinion class, always labelled "secondary", never binding (decision D6). It tests five conditions, called triggers A to E, in the order E, A, B, C, D. |
| Would-be class | For a low-confidence row: the class it would have at medium confidence. Never binding. |
| Confidence conditions C1 to C8 | The eight conditions protocol v1a sets for medium confidence. C7: before the flood, at most 10% of the connected residents have no vehicle route. C8: at least one hospital can be reached before the flood. |
| Anchor | A fixed value that sets the end of a 0-to-100 scale. Flood anchor 0.20: a tambon with 20% or more of its land flooded scores 100 for flood likelihood. Vulnerability anchors P10 and P90 (or P5 and P95): the share of children and older adults that 10% and 90% (or 5% and 95%) of all Thai subdistricts stay below. P75 likewise. |
| Leave-one-out | Leave-one-component-out: the score and the class computed again with one of the five components taken out. |
| Lane | The kind of evidence a result rests on: observed, scenario, or engine test (invented units). Results of different lanes are never added together. |
| Tier T0 to T4 | How strong the evidence is. T0 invented test units, T1 a scenario, T2 the team's own candidate ("verify before action"), T3 a dated agency map, T4 a qualified reference. T4 is locked: it is never claimed. |
| Case SE1 | The 2024 season envelope as a scenario: every area mapped as water at some time from August to October, treated as flooded at once. |
| Case O2 | The agency layer of 22 October 2024: late-season residual water. It does not describe the September flood. |
| Case O1 | The team's own radar flood candidates from the Sentinel-1 pass of 16 September 2024. |
| Cases SE2, SE2-dist, SE2-blind; scenarios S3, S5, S9 | A second scenario case around Mueang Chiang Rai with two companions, and what-if runs on a case (S3 fails the three highest-ranked links of each tambon). Deferred (R16) or not built. |
| Overlay, result file | The one result file of a case that every page reads. Its format today is "schema 1.0". |
| Parser; fixture | A parser is a program that reads a result file and refuses a faulty one. There are two: one in Python for the builders, one in TypeScript for the site. The fixture is a result file of invented units, used in tests. |
| Ensemble, re-run; default cell | The same calculation repeated with one declared choice changed (flood layer 20 m smaller or larger, another closure level, other weights). A re-run is also called a cell. 540 re-runs per case; 180 of them count for a public result. The default cell has every choice at its default: its rows are the scores of plan task E8. |
| Closure level | How much of a road piece must lie in the flood extent before the model treats it as closed: strict, central (the default) or permissive (any contact). |
| Retention, headline | Retention is the share of re-runs in which a tambon keeps its class. A class may be shown as a headline only at 60% or more; otherwise it is shown as "unstable: verify". |

**Radar**

| Word | Meaning here |
|---|---|
| The pass of 15 or 16 September | One radar pass: 15 September 2024, 23:16 UTC, which is 16 September, 06:16 in Thailand. Both dates mean the same image. |
| Geocoding; warp; control points | Geocoding gives each radar pixel its position on the ground. The warp is the step that moves the image onto the map grid. Control points are positions the product supplies for that. The run of record fitted a curved surface through them (a second-order polynomial); "affine" would be a flat fit. |
| Radar shadow, layover | Places where terrain hides the ground from the radar, or folds a slope onto its foot. The image cannot be trusted there. |
| dB | Decibel, the unit of radar brightness. Open water usually looks darker. |
| UN-SPIDER, M1-literal, M1-v2 | Three radar methods: the United Nations' recommended practice (a fixed ratio between two dates), the team's first threshold method, and its tuned version, frozen before any Mae Sai run. M1-v2 may give no answer for a tile. |
| GEOID sample; UTM zone 47N | The GEOID-Flood sample is a public data set of one foreign flood, cut into square tiles, on which M1-v2 was tuned and scored. UTM zone 47N is the metric map grid of this part of Thailand. |
| Skill bar | Four conditions the team's own radar method must pass before its rows may be more than low confidence. At Mae Sai it is recorded as not met. |
| SNAP | The European Space Agency's radar software. The plan names its terrain correction first. It is not installed. |

**Site and Git**

| Word | Meaning here |
|---|---|
| Bake | Building the replay's data files from their inputs. |
| Knot | A fixed point (a time and a level) of the replay's water-level curve. |
| Parity fixture | A shared test file that holds the Python and the browser version of one rule to the same numbers. |
| Equity 2.0 | The scoring line's newer version of the equity rule. The replay uses the earlier one. |
| Referrer header | What the site lets another site know about the page a request came from. |
| Level-5 check | The last of the plan's five levels of checking: a comparison with documented 2024 impacts, and a practitioner's review. |
| Merge commit; squash, rebase | Ways of bringing a branch into master. A merge commit keeps every commit. A squash or a rebase rewrites them, and the signing commits would be lost. |
| Git hook | A small script that Git runs by itself before each commit. It is a setting of one machine. |

## Part 1. The few answers that unblock the most

**The first real planning scores exist, and they cannot reach a page yet.** Plan task E8 computed them on
4 October 2026 for the season-envelope scenario (SE1) and for the layer of 22 October (O2). What stands between
the SE1 scores and a page:

| Step | Waits for |
|---|---|
| The SE1 result file (overlay) is written | **Q1** (open point E8-OP1) |
| Its rights level is `public` | **Q2** (E8-OP5), answered with "public use" |
| A class may be shown, and with which words | **Q3** |
| You have read the results | **Q4** (decision R18) |
| The Command page shows the file | **Q5** first (the older ranking leaves the Command archive page); the page itself has to be seen and given its address (Q11, Q12) |
| The public band and the briefs show the file | engineering after Q1 to Q4: plan tasks E12 and U5 are not built |

Order of this part. Q1 to Q4 decide whether SE1 can be shown. Q5 has to be settled before any protocol score
appears on Command. Q6 is the first step for case O2, which is computed and held at `local`. Q7 to Q9 come last: they
concern the radar case and the shelter part.

Three record drafts were prepared for you on 5 October 2026 in `docs/proposal_execution/`. Each is marked pending,
and a test fails if any code treats one as confirmed:

- `age_data_purpose_review_v1.md`: the review of the 2024 age data (Q2);
- `rights_basis_sentinel1_v1.json` with `rights_basis_sentinel1_v1_NOTICE.txt`: the Sentinel-1 rights record (Q7);
- `walking_build_compute_window_v1.md`: the compute window of a walking build (Q8).

### Q1 (E8-OP1, E11-11). May a result row say "not evaluated" for its second-opinion class?

| | |
|---|---|
| Question | Rule v2 tests five triggers in the order E, A, B, C, D. Nothing yet tests triggers B, C or D. May a row say "not evaluated" there? |
| Why it matters | For four of the eight SE1 tambons the second-opinion class depends on trigger B, C or D. The file format (schema 1.0) cannot say "not evaluated", so the SE1 result file was not written. Without it no page, brief or Command column can read the scores. |
| Options | **1.** Allow "not evaluated" on the secondary class. That changes the file format (schema 1.1), not a protocol rule. **2.** Build the tests for the three triggers first: trigger B waits for Q22, trigger C needs a rule the protocols do not give (v2), trigger D needs a download (Q23). **3.** Do option 1 now and fill in each trigger when it becomes possible. |
| Recommended | **Option 3.** Also write "not evaluated", never "false", for a trigger nobody measured. Today trigger B is written "false" on all eight O2 rows although nobody measured it. |
| Reason | It is the true state. The binding class does not depend on the second one. The protocols state no result for a trigger nobody tested. |
| Risk | At the pitch the secondary class of SE1 reads E for four tambons and "not evaluated" for four. Rule v2 is a predeclared axis (decision D6), so the gap has to be said out loud. The format change touches both parsers, the fixture, and the 113 shared test cases in which a parser must refuse a file. |
| After a yes | The format change is made and tested on invented units. The SE1 run is repeated as a superseding run (a run on real tambons, reported; the same eight rows are expected) and writes the result file. The O2 file is rewritten the same way. Whether SE1 may then go to a page depends on Q2, Q3 and Q4. |
| Who | Both |
| Reply | `Q1 yes` |

### Q2 (E8-OP5). May results that use the 2024 age data be shown outside the team?

| | |
|---|---|
| Question | One of the five score components uses WorldPop's 2024 age counts (modelled people per 1 km cell, by age). Protocol v1b says of them: "Public derivatives require purpose-specific review." No review is recorded. Do you record one, and with which answer? |
| Why it matters | Until you answer, every score and class is held at `local`, also for SE1, whose other inputs are public. No page of the site can show a score. The age table of the eight tambons is already in Git since 4 October, so your answer has to cover it too. |
| What the project's own register says | `docs/proposal_execution/SOURCES_AND_RIGHTS.md`, checked 23 September 2026, has two cells on this data set. Hosted or download derivative: "Catalog states CC BY 4.0 with an ODbL caveat for some building/OSM-derived products; hosted age derivatives still await product-specific attribution/share-alike review. Age bytes and detailed results remain in configured external roots." Downstream decision: "Age-vulnerability score and accepted group access remain unavailable; a mixed-vintage scenario sensitivity may be shown only with its own label." The draft quotes the whole row, with its four other cells. The register is older than the signed protocols (2 and 3 October), which make the age mix a score component, and the age table committed on 4 October already departs from the first statement. Your answer should say whether it replaces these two statements. |
| Options | The draft `docs/proposal_execution/age_data_purpose_review_v1.md`, section 7. **1. Public use** (the draft calls it A). **2. Pitch use only** (B). **3. Decline** (C). Five conditions can be attached to option 1 or 2. The README also leaves you a fourth answer: to "say that it is not needed for these derivatives". The sheet does not offer it, because the signed sentence asks for a review. |
| What each option costs | **Option 1:** nothing is held back. **Option 2:** the age counts become `pitch`, so every SE1 score stays below `public`. Guardrail GR6 lets only `public` results be written under the website's public folder, and the new Command table refuses a result file that is not `public`. So no page of the site can read a score: not the Command columns, not the public band, not the briefs. Scores can appear on slides or screenshots only, and pitch files stay outside Git (plan 3.1). **Option 3:** no score is shown outside the team, and taking the component out of the score is **v2**. |
| Recommended | **Option 1 with all five conditions**, after one of you has checked the three licence points of the draft's section 2 on WorldPop's product page. |
| Reason | The data are coarse, modelled and openly catalogued (CC BY 4.0, as the repository records it). The smallest tambon has 3,197 modelled residents in the age table. The design already gives tambon-level output only, the words "modelled, not observed", and the class without this component beside every class. Option 1 is also the only answer under which Q4, Q5 and Q13 have anything to show on a page. |
| Risk | Four of the eight tambons take counts from cells that straddle the national border, so a public "vulnerability" label rests partly on people who are not their residents. Nobody has checked the licence points against the provider's page. If either worries you, option 2 is the cautious choice, at the cost stated above. The five national anchors are derived from the same age rasters and are already in Git inside the signed protocol; the draft says what each option means for them. |
| After a yes | A decision-log row. A reviewed code change sets the level of the age counts and cites the row. The SE1 run of plan task E8 is repeated, then the ensemble of plan task E10 (real tambons, reported). With option 1 the SE1 result is `public` and its per-tambon table can be committed. |
| Who | Both |
| Reply | Needs more than a word: `Q2 option 1, conditions 1 to 5, licence checked on <date>, replaces the register's two statements: yes` (or `Q2 option 2`, `Q2 option 3`) |

### Q3 (E10-OP1, E10-OP2, E10-OP11, E10-OP12). When may a class be shown as stable?

| | |
|---|---|
| Question | The protocol shows a class as a headline only if the tambon keeps it in at least 60% of a fixed set of re-runs: 180 for a public result. Only 90 can be made today. The other 90 need the "2024-rescaled demand" (2020 residents scaled to 2024 totals), and its formula leaves two details open. What do we do meanwhile, and how do we get the missing 90? |
| Why it matters | No class of SE1 or O2 can be called stable. The demo tambon of protocol v1a is then "the highest-FPPS unit, shown as unstable: verify". |
| Options | Five parts. **Part 1, the words on a page until the rule can be evaluated:** show the class as "unstable: verify" with the note "stability not evaluated yet: 90 of 180 re-runs made", or show no class. **Part 2 (E10-OP2), the two open details of the rescale:** take them from the script `bridge_worldpop_age_access.py` (a 2020 cell belongs to the 1 km cell that holds its centre, within its tambon; 2020 residents whose 1 km cell has no usable 2024 count are reported as a figure of their own, neither set to zero nor rescaled), or state other rules. **Part 3 (E10-OP11), which re-runs count for a result that is not a public result file:** the protocol's words (540 in general, 180 for a public one), with both reported and no status set until the result is a public file. **Part 4 (E10-OP12), declared cut line 6 of the plan** (drop two axes; 45 public re-runs remain, and with WorldPop 2020 kept all of them have been made): invoke it now, or not. **Part 5 (E10-OP1), a choice the README lists as yours:** take retention over only the re-runs that can be made. |
| Recommended | **Part 1:** show the class with "unstable: verify" and the note. **Part 2:** yes, the two rules of that script. **Part 3:** as the protocol words it. **Part 4:** do not invoke the cut now. If the rescaled demand cannot be built before the number freeze, invoke it then, keep the levels of the default cell (WorldPop 2020, anchors P10 and P90), and say that it was invoked after the counts were known. **Part 5:** no. |
| Reason | Part 1: guardrail GR8 knows two displays, and "unstable: verify" is the cautious one. Part 2: the script is named in the reason of the recommendation you approved (R12; entry 12 of the owner choices), which says its option "matches the plan's words and the way `bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells". With the two rules the missing re-runs need no new access run. Parts 3 and 4 add no rule. Part 5: the README offers it because the protocol does not say what retention is while a part of the re-runs cannot be made. The sheet advises against it because the 90 results are known: every tambon keeps its class in at least 60% of them, in both cases. Choosing the smaller set now would turn every class into a headline with the outcome in view. If you want it all the same, the drafter would write it as a v2 rule with that reason stated. |
| Risk | Part 1: a reader may take "unstable" for a measured finding; the note says it is not measured yet. Part 2: protocol v1b does not name the script, so this is a reading recorded after 90 re-runs were seen, and every output must say so. Nobody has measured whether any 2020 resident of the frame falls in a 1 km cell with no 2024 total, so you cannot tell today how many residents the second rule would set aside. The build of the rescaled demand reports that count before any re-run is made, and the sheet proposes that it comes back to you first. Part 4: the plan lists its conditional cuts "in order". Line 6 comes after lines 1 to 5 (Hat Yai, the weight sliders, the supervised classifier, the SE2-blind companion, scenarios S5 and S9). R16 defers Hat Yai and the classifier; the decision log records no cut of lines 2, 4 or 5. Invoking line 6 therefore means saying what happens to those lines too. After the cut all eight tambons are at or above 60% in both cases, whichever anchors are kept, so invoking it now would look like picking the rule that passes. |
| After a yes | A decision-log row. The rescaled demand is built and tested on invented data, then the 90 missing public re-runs of each case are made (real tambons, reported). The headline rule is then evaluated as written, for a public result file. |
| Who | Both |
| Reply | `Q3 yes` (all five as recommended), or part by part, for example `Q3 part 1: show no class` |

### Q4 (decision R18; E8-OP6 first half). Have you read the first results, and may SE1 go to a page?

| | |
|---|---|
| Question | R18 says that no result of the planning assessment is shown on any page before the owners have read it. Have you read them, and may SE1 be shown once Q1 to Q3 are in place? |
| Where to read | `outputs/planning_v1/README.md`, sections "Plan task E8" and "Plan task E10". Both are long. The per-tambon scores and classes are in two files outside Git that the receipts bind. |
| What they say, for the whole case | **SE1:** class B once, D three times, E four times; scenario confidence medium for all eight. The one class B is kept in 70 of the 90 re-runs that could be made; the README says to read it as "B or D, depending on 20 m and the closure level". Two of the four E results are D if the disclosed flood anchor is 0.10 in place of 0.20. **O2:** class E for all eight, in every re-run. That says the score is low on late-season residual water, not that a tambon was safe. |
| Options | **1.** Allow SE1 on pages, labelled "scenario: 2024 season envelope" and "unstable: verify". **2.** Allow it in the pitch only. **3.** Hold. |
| Recommended | **Option 1**, after one desk check (action 5): the README says the access figures of the tambon whose access gap and road criticality are both 100 should "be checked at a desk before anyone repeats it". Nothing is shown from the report file of the first run; a page reads the result file only (E8-OP6). |
| Reason | Each run was computed again to the same bytes, and a reviewer's own script recomputed all eight rows of both cases with no difference. Every value is labelled as a scenario result. |
| Risk | One flood input drives four of the five components (90% of the weight). A scenario class is easily repeated as a fact about September 2024. The class B rests on modelled road closures, not on a recorded closure. Option 1 has an effect only if Q2 is answered with option 1. |
| After a yes | With Q1, Q2 (option 1) and Q3 the SE1 result file is `public`. The planning columns of Command can fill for SE1 once Q5, Q11 and Q12 are settled, and the public band (plan task E12) and the briefs can be built on it. O2 waits for Q6. |
| Who | Both |
| Reply | `Q4 yes`, after reading |

### Q5 (decision R17, point g; merge report item 11). The older ranking that still stands on `/command/archive/`

| | |
|---|---|
| Question | You said yes to taking the GeoAI research report's score table off Command (R17). The map workspace at `/command/archive/` still shows its own retained ranking: a research FPPS and a class for each of the eight subdistricts, from before the signed protocol. Its values differ from the report's. Should it leave the page too? |
| Why it matters | Once SE1 scores of the protocol reach Command, the same eight tambons would carry scores from different sources on Command pages. R17 says this question was not put to you. It stands in part 1 because it has to be answered before any protocol score appears on Command. |
| Options | **1.** It stays until Command is replaced, with its notice. **2.** Take it off now and keep it only in Studio's archive, labelled as historical research, like the report's table. |
| Recommended | **Option 2, before any protocol score appears on Command.** |
| Reason | What R17 says of the report's table is also true of this ranking: a research FPPS and a class per subdistrict, from before the signed protocol, on a Command page. So the same reason applies. R17 records your yes and gives no reason of yours; this argument is the drafter's. |
| Risk | The map workspace loses its ranking rail, its readout and its A to E legend, and the offline check that lists its eight retained values has to change with it. |
| After a yes | A reviewed change to the page and its checks. |
| Who | Putu |
| Reply | `Q5 yes` |

**Note of 5 October 2026, after decision R19 (added after this sheet was drafted).** Putu asked for the two Planning
addresses to be swapped, and that is built on branch `claude/unify-lineages`. The map workspace of this question is
now the default Planning page at `/command/`; `/command/archive/` only forwards to it. So the older ranking stands
on the default Planning page again, labelled as before: its scores and classes "are retained research comparisons,
not accepted event-response priorities". The request was about the two addresses and did not mention the ranking,
so this question is still open, and R19 says so. Where this sheet says `/command/archive/` for the map workspace,
read `/command/`. Option 2 would now take the ranking rail, the readout and the A to E legend off the default
Planning page.

### Q6 (E1-OP1 first half, E1-OP10, E1-OP8, A1-OP6). One new version of the rights record for product 4009

| | |
|---|---|
| Question | The confirmed rights record for UNOSAT/GISTDA product 4009 names one layer: the accumulated layer of August to October 2024, the season envelope. The code also reads two more layers of the same product: the layer of 22 October 2024 (case O2) and the "analysis extent" (the outline of the area the product looked at). Both are held at `local`. Should a new version of the record name them? |
| Why it matters | Case O2 is computed. While these two layers are `local`, no O2 result can be read by a page, and the O2 tables stay outside Git. |
| Options | **1.** The agent drafts version 2 of the record for both of you to confirm, as you confirmed version 1 (R6). **2.** Leave it: O2 stays at `local`. |
| Recommended | **Option 1.** |
| Reason | Decision D2 and UNOSAT's reply (R4) concern the product. Decision D3 makes the layer of 22 October its own observed case. The plan expects one record for both flood layers. |
| Risk | R6 allows publication "as a season envelope only". Version 2 widens that, so it is a new decision of yours, not a reading. The layer of 22 October is late-season residual water and must never be shown as the September flood. UNOSAT's reply names no licence version (R4). O2 also uses the age data, so its results stay below `public` until Q2 is answered as well. |
| After a yes | The agent drafts the record and its notice, pending, with a test that holds it pending. You read and confirm it. A reviewed change registers it. Plan task E1 is run again so that each layer carries its new level (the geometry does not change), then E5, E8 and E10 for O2. |
| Who | Both |
| Reply | `Q6 yes` (it means "draft it"; confirming the record is a second step) |

| Point | What it asks | In version 2 of the record |
|---|---|---|
| E1-OP1 (first half) | Does the record cover the layer of 22 October and the analysis extent? | Both are named, each with its use. |
| E1-OP10 | The footprint layer the code reads (`CHIANGRAI_20240801_20241022_AnalysisExtent`) is named by no signed file. | It is named. |
| E1-OP8 | The change-notice template is written for a raster; the vector layers word their own notice. | A template for vector layers is added. |
| A1-OP6 | A diagnosis comparison is not among the listed uses. | "Comparison layer, labelled 'vs a season envelope, not an event map'" is added. It is never a reference. |

### Q7 (E1-OP2 first half, A4-OP5, E1-OP9). Do you confirm the rights record for the two Sentinel-1 radar scenes?

| | |
|---|---|
| Question | The radar candidates of case O1 are made from two Sentinel-1 scenes (3 and 15 September 2024 UTC). No signed rights record covers them, so the code refuses every O1 candidate. The draft is `docs/proposal_execution/rights_basis_sentinel1_v1.json` with its notice file. It asks four things. **Part 1 (A4-OP5):** a note in the acquisition manifest of July 2026, quoted in the next row. **Part 2:** five points to check with the provider, four on the Copernicus legal notice and one on the terms page of the Copernicus Data Space, the service the files were downloaded from (the draft lists them). **Part 3:** the scope, `local` only or also a publication scope. **Part 4 (E1-OP9):** may anything be loaded under the draft before it is confirmed? |
| Part 1: two notes, not one | The manifest exists in two copies. Both mark the two archives `processing_allowed` False, and they give different reasons. **The copy in Git** (`outputs/cdse_mae_sai_acquisition_manifest.csv`, SHA-256 `abc4cd0ea20b5c2b3e7f5e4d103b1117cb77d9ac4b9ea1010ea0d8d03b068809`) says: "qualified, official, or decision-eligible processing remains blocked because reference mask status is unresolved; the non-operational cross-border calibration baseline is governed separately". **The copy outside Git**, beside the archives (SHA-256 `6ea1b440a6c9faa35ea9c74fc036c255b5a74549b68db25d0b2355ffe23b1133`), says, as the radar receipt quotes it: "reference mask status remains unresolved; do not run baseline yet". That copy was not opened for this sheet. Decision R14 quotes the words of the copy outside Git ("processing_allowed False / do not run baseline yet") and reads them as a gate on the finals baseline only, not on rights, for the replay and the 3 September file. The sentence in Git says something R14 does not speak of: it is not about the baseline, and it blocks "decision-eligible processing". |
| What part 1 asks | **First:** does R14's reading also hold for plan tasks A2 and A4, for the diagnosis of plan task A1, and for the 15 September file? **Second:** is loading an O1 candidate into a planning score (an FPPS and a class) "decision-eligible processing" in the sense of the sentence in Git? If it is, a rights record alone does not open the way to an O1 score: the note stands until the status of the reference mask is resolved, or until you lift the note in writing. The project's register of 23 September says something close in the last cell of its row for the pair (next row). |
| What the project's own register says | `docs/proposal_execution/SOURCES_AND_RIGHTS.md`, checked 23 September 2026, before the protocols were signed. Its row for the pair, cell by cell. Identity: "Mae Sai same-track 3/15 September 2024 UTC; exact product IDs in `docs/mae_sai_pair_decision_note.md`; local archive identities are governed by the acquisition manifest". Processing: "Allowed for the existing documented research processing scope". Human label or independent final evaluation: "No qualified Thai event reference follows from the SAR source itself". Hosted or download derivative: "Candidate derivatives already subject to Copernicus notice and package export checks". Downstream decision: "Separate accepted-input receipt required". No accepted-input receipt for the pair is in the repository. Please say whether your confirmation of the record is meant to be that receipt, or whether one is still needed before an O1 candidate enters a score. |
| Why it matters | Without the record O1 can never be loaded. The radar tables and the diagnosis figures of 4 October were made from these two scenes before any signed record existed. |
| Options | Part 1: your reading of both questions. Part 2: checked, with corrections if a page says something else. Part 3: **option 1**, `local` only, or **option 2**, also a publication scope, which needs a new version of the record and a reviewed change to the rights code before it has any effect. Part 4: keep refusing until the record is confirmed, or allow the draft at `local`. |
| Recommended | **Part 1 depends on your reading, so there are two branches.** If you read the sentence in Git as not covering a planning score that is labelled Tier 2, low confidence and class E, confirm the record for all five uses it lists. If you read it as covering such a score, or if you are not sure, confirm the record for making the candidates, the tables and the diagnosis figures only, and leave "load the candidates into case O1" out until the note is lifted. The second branch is the cautious one and costs little today, because every O1 row would be class E either way. **Part 2:** check. **Part 3: option 1 now**, and option 2 when a radar layer or figure is to be shown outside the team. **Part 4:** keep refusing. |
| What scope `local` stops | The O1 chip on Command can never fill: that page reads `public` result files only (Q13). No layer or table made from the two scenes may be written under the website's public folder. Whether a radar figure may be said on a slide at `local` depends on Q21; until then the cautious reading is no, so the diagnosis figures of Q31 wait for it. The per-tambon radar tables already in Git stay above their level (Q21). The chip, the public folder and the tables need option 2. |
| One existing use to settle | The replay, which is in production, reads the 3 September archive of this record (the same file) for a radar size comparison and publishes figures made from it in `apps/web/public/studies/mae-sai-2024-timeline/r4/timeline.json`, under R14. The image itself is not published. The draft lists this as an existing use that R14 covers and that the record does not change. Under scope `local`, two rules then apply to one file. Please confirm that reading, or say that the record should cover the replay's use too, which is option 2. |
| Reason | Part 3: option 1 needs nothing beyond registering the record. Part 4: the plan's fallback "run at the `local` level" (plan 4.1) was written for the product 4009 record, which is confirmed, so nothing of product 4009 is refused today. For Sentinel-1 every candidate is refused today. The plan lists the radar candidates as "always on" and names no record for them, and the code refuses any record that is not confirmed. That is the safer rule to keep. |
| Risk | The runs of 4 October were made and committed before this answer, with no record. The plan's rows for tasks A2 and A4 name the pair; whether that was enough is yours to say. A "no" to the first question of part 1 means they were made without your permission, and that has to be written down. Nobody has checked the five provider points. |
| After a yes | Two reviewed changes: the record is marked confirmed, with a decision-log row that states your reading of part 1, and then registered in the rights code. The loader then accepts a candidate, unless you held that use back. Still missing for an O1 score: the geocoding (Q9), the delivery of the candidates to the flood-input step, and a builder that reads the radar skill measurements. Every O1 row would be low confidence and class E under rule v1, because the skill bar is recorded as not met at Mae Sai. |
| Who | Both (a rights record needs both names) |
| Reply | Needs more than a word: `Q7 part 1: first yes or no, second yes or no; part 2 checked on <date>; part 3 option 1; part 4 keep refusing; replay use as drafted` |

### Q8 (E5-OP5, E10-OP3 first step). Do you accept one compute window for a walking build of record?

| | |
|---|---|
| Question | The shelter part of the planning work needs a road network built for walking. One exists, built on 4 October without a declared compute window, so it is a candidate only. Do you accept one window for one walking build of record, on the terms you accepted for the vehicle build in R13? |
| Why it matters | Until then the shelter tables may not feed the scores. A walking build of record is the first step for the shelter service, for 360 of the 540 re-runs of each case, and for a pitch-level result file. It is not needed for a public headline (Q3). |
| Options | The draft `docs/proposal_execution/walking_build_compute_window_v1.md`, section 7. **1.** Accept in advance (the draft calls it A). **2.** You name the window (B). **3.** No walking build of record (C). |
| Recommended | **Option 1**, keeping the condition that the build must reproduce the candidate: the same network fingerprint, 359 grade joins (the joints the builder adds where road ends coincide), 69,095 road pieces, and 81 of the 82 located shelters attached to the network. |
| Reason | The terms are those of R13. The candidate build took 2.38 minutes. The condition catches any drift, and any difference comes back to you. |
| Risk | About ten quiet minutes on the machine. Two small fixes come first (the builder's receipt must name both protocols; the access step must refuse a walking network whose receipt names nobody who accepted its window). The middle one of the three shelter sets still has no access table, and half of the 360 re-runs also wait for Q3. |
| After a yes | A decision-log row. The two fixes, tested on invented data. The one build, the four-line comparison, then commit and register, or stop and come back to you. The agent asks again before it reruns the access tables (about 20 minutes), plan task E8 or plan task E10. |
| Who | Both |
| Reply | `Q8 yes` |

### Q9 (A4-OP1; A1-OP3 follows it). Which radar layers does case O1 use?

| | |
|---|---|
| Question | The plan's fallback geocoding was used for the radar run of record. It puts the radar layers about 680 m from where they belong. A second run gives every cell a terrain height and leaves about 10 m, but its method is not in the plan. Which layers does case O1 use? |
| Why it matters | Roads are narrow. With a shift of 680 m no road closure can be modelled from the radar layers; they are good for tambon totals only. One diagnosis figure follows the same choice (A1-OP3). |
| Options | **1.** The run of record, totals only. **2.** The height-aware sensitivity run. **3.** A new warp that passes through every control point (not run). **4.** SNAP terrain correction, the method the plan names first; SNAP is not installed, and installing it is a download only a person can make. |
| Recommended | **Option 2**, named as what it is ("a terrain height per cell; not SNAP terrain correction"), with the run of record kept beside it as reported. Rachmania reviews both runs first: the result page says she has not yet reviewed them. |
| Reason | It is the only run on disk without the 680 m shift. Whether its layers can be used at road level has not been reviewed: the result page makes no such claim, and it says that radar shadow and layover are not flagged. The skill-bar outcome is the same in both runs: the method declined the same six of nine tiles. |
| Risk | The choice is made after both results were seen (candidate areas 9.42 against 8.30 km², 114.50 against 116.36, 3.01 against 3.04) and has to be disclosed as such. Until the review, the layers of option 2 are for tambon totals too. If you would rather hold to the plan's named method, answer option 4: O1 then waits for SNAP. |
| After a yes | A decision-log row. A superseding run (reported) labels the chosen layers as the O1 input and corrects the label of the fallback run (A4-OP7, in Q29). Nothing is delivered to the scoring chain before Q7. |
| Who | Rachmania |
| Reply | `Q9 option 2` (or `Q9 option 1`, `Q9 option 3`, `Q9 option 4`) |

## Part 2. The new Command page, and what decision R17 left open

Decision R18 approved the purpose ("exercise and after-action tool for rescue coordinators" on the Mae Sai 2024
case) and left the Thai text to the assistant. The page is built on branch `claude/command-exercise` at the
temporary address `/command/exercise/`; `/command/` is unchanged. R18 records choices 2 to 6 of the plan
(`docs/command_exercise_plan.md` on that branch, section 12) as "built as recommended" and provisional. In detail:
choices 3 to 6 are built; of choice 2 the header name is built inside the new page, and the address change is not
made; choice 7 is not applied. Putu gave the Command answers that R17 and R18 record, so Putu is named below;
Rachmania is welcome on any of them.

Two things come before the rest of this part. Q10 is about the preview that does exist, the one of PR #43. Q11 is
about seeing the new page, of which no preview exists. Until Q11 is done, Q12 to Q17 and Q20 cannot be answered
from a preview. The older ranking on the Command archive page (R17, point g) is Q5 in part 1.

### Q10 (decision R18). Have you looked at the preview of PR #43?

| | |
|---|---|
| Question | R18 says: "PR #43 waits for the owner to look at its preview." The decision log names the PR by its number only; as the drafter understands it, PR #43 is the unified branch (`claude/unify-lineages` into master). Its preview shows the site as the merge would leave it, with today's `/command/`. It does not show the new Command page: that branch holds no `/command/exercise/` page. Have you looked at it? |
| Why it matters | The merge of the unified branch waits for this look, and so do the items of the merge report (Q43 to Q49, actions 6 and 16). |
| Options | Looked, with or without changes; not yet. |
| Recommended | Look at the pages the merge report names (`docs/unified_lineage_merge_report.md`, section 8): `/command/`, `/command/archive/`, the study library, and the Public page on a phone. |
| Risk | None in looking. |
| After | The merge itself is action 6: "Create a merge commit", never a squash and never a rebase. |
| Who | Putu |
| Reply | `Q10 seen`, with any changes you want |

### Q11 (decision R18). How do you want to see the new Command page?

| | |
|---|---|
| Question | The new Command page exists only on branch `claude/command-exercise`, on the machine it was built on. The branch was never pushed, so no preview of it exists. (Checked on the local copy of the remote branches; nothing was fetched for this sheet.) R18 says `/command/` is unchanged "until the owner has seen it". How do you want to see it? |
| Why it matters | Q12 to Q17 and Q20 are about what that page shows. |
| Options | **1.** You approve that the agent pushes the branch and opens a draft pull request, so that a preview is built for it, as PR #43 has one. The agent does not push without your approval. **2.** A local run on a machine that has the branch: `pnpm install --frozen-lockfile`, then `pnpm --filter @floodguard/web dev`, then open `http://localhost:3000/command/exercise/`. These are the commands of the repository's README; they were not run for this sheet. **3.** Not yet. |
| Recommended | **Option 1**, because a tablet can open a preview address and cannot easily open a local run. Option 2 serves for a first look today. Look on a laptop and on a tablet, in English and in Thai. |
| Risk | A preview address may be open to anyone who has it. The page is an exercise replay with invented calls, labelled as such. Whether a pushed branch gets a preview, and who can open it, depends on the deployment settings, which the drafter did not check. No native speaker has read the Thai text (R18); the page's information drawer says so. |
| After a yes | The push and the draft pull request, and nothing else. No merge. |
| Who | Putu |
| Reply | `Q11 option 1` (or `Q11 option 2`), and `Q11 seen` once you have looked |

### Q12 (plan choice 2). Addresses and the name of the header link

| | |
|---|---|
| Question | May the new page take the address `/command/`? The plan moves today's text page to `/command/planning/`, keeps `/command/archive/` and `/command/cases/` behind menu links, and names the header link "Command (exercise)" (Thai draft: ฝึกซ้อมสั่งการ). The name is built inside the new page; the address change is not made. |
| Why it matters | Until the change, the landing page and the policy page link to the old page, and the new one has only its temporary address. |
| Options | **1.** Yes as planned. **2.** Yes with another name. **3.** Keep the temporary address for the pitch. |
| Recommended | **Option 1**, after Q11. |
| Reason | One address for Command, and the old pages stay reachable. |
| Risk | The plan counts 17 script files and about 13 source files that name `/command/`, so the change needs its own checks. Command exists in the competition build only; the public-production build leaves the whole route out. |
| After a yes | The change is made as its own reviewed step: header, policy card, landing links and the offline list. |
| Who | Putu |
| Reply | `Q12 yes` |

**Note of 5 October 2026, after decision R19 (added after this sheet was drafted).** The addresses this question
names have changed on branch `claude/unify-lineages`. "Today's text page", the planning overview, is now at
`/command/ver2/`. `/command/` is the map workspace. `/command/archive/` holds one sentence with a link and forwards
to `/command/`. The plan of the new page was written before that: it moves the text page to `/command/planning/`
and keeps `/command/archive/` behind a menu link. If the new page takes `/command/`, the map workspace needs an
address of its own again, and the overview can keep only one of `/command/planning/` and `/command/ver2/`. R19
leaves both to the work on the new page (R19, point h). Nothing on branch `claude/command-exercise` was changed.
The counts of files in the Risk row are the plan's, from before the swap.

### Q13 (plan choice 3; decision R17, part 1). The two rankings and the class form to keep

| | |
|---|---|
| Question | The table of the eight tambons shows two rankings side by side that are never merged. Left: this replay hour's count (residents who lost shelter access; ties by residents in modelled water). Right: the protocol's planning class, fixed in time, with one chip for the radar case O1 and one for the scenario SE1. R17 says both class forms are built for now, each labelled, and one is chosen later. Is the default order right, and which form stays? |
| Why it matters | It is the first thing a coordinator reads. |
| Options | **1.** Keep both chips. **2.** Keep the scenario chip only. **3.** Keep the radar chip only. |
| Recommended | **Option 1: keep both chips, each with its label. Default order: the left ranking. Planning position from SE1, labelled "scenario".** Do not choose one form until O1 has a result. |
| Reason | SE1 is the only case that can reach the public level soon (Q1, Q2). Two labelled chips say more than one. |
| Risk | A scenario class beside a replay of September can be read as "what happened". The chip says scenario and the table footer says "Fixed in time; not computed from this hour". Today both chips are dashes ("Not issued yet"). The O1 chip stays a dash until an O1 result exists and is `public`. That needs Q7 with a publication scope; scope `local` is not enough. It would then read E. |
| After a yes | Nothing changes now. The SE1 chips fill once Q1 to Q5 are in place. |
| Who | Putu |
| Reply | `Q13 yes` |

### Q14 (plan choice 4). What the map shows as reports this week

| | |
|---|---|
| Question | Three kinds of report are built: 2024 place records from news; invented exercise calls tagged "EX"; and reports saved on this same device, shown as a count on the tambon. Nothing travels between devices, and the SOS practice mark is not built. Is that the right limit? |
| Why it matters | R17 asked the agent to try to show public reports and SOS on the map, and says the page must not read as a feed of incoming reports or calls. |
| Options | **1.** Keep as built. **2.** Add the SOS practice mark. **3.** Remove the same-device reports. |
| Recommended | **Option 1, and leave the SOS practice mark unbuilt.** |
| Reason | A public report is stored only on the reporter's own device, and SOS only opens the phone's dialler (R17). Nothing more can honestly be shown. |
| Risk | A viewer may still think that reports reach responders. The plan has the page say that FloodGuard receives no calls and that 1784, 1669 and 191 remain the official routes. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q14 yes` |

### Q15 (plan choice 5). The invented exercise calls

| | |
|---|---|
| Question | 14 invented items are built: 2 with life at risk, 4 urgent, 8 for information, in English and Thai. Each id starts "EX-". None holds a real person's details, none copies a real 2024 plea, and none is counted with real records. Do you accept them? |
| Why it matters | They are the script of the exercise, and the only "calls" on the page. |
| Options | **1.** Accept. **2.** Accept with edits. **3.** Cut the number. |
| Recommended | **One of you reads all 14, then option 1.** They are in `apps/web/public/exercises/mae-sai-2024/injects.v1.json` on the branch. |
| Reason | The plan asked for a set written by the team and read by a Thai speaker. R18 leaves the Thai to the assistant, so your reading is the only human check. |
| Risk | An invented call can still read like a real case. The parser of that file refuses text shaped like a phone number, a house number or a person's title, and a test checks that no item shares a run of five words with a place record. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q15 yes`, after reading |

### Q16 (plan choice 6). The future is hidden by default

| | |
|---|---|
| Question | In "trainee mode", the default, a place record appears at its publication time and later hours are hatched. "Hindsight mode" is one switch away. The Studio replay keeps its own rule. Is trainee mode the right default? |
| Why it matters | A trainee should not see what was not known yet. |
| Options | **1.** Trainee mode by default. **2.** Hindsight mode by default. |
| Recommended | **Option 1.** |
| Risk | Markers follow the clock on Command and do not on the Studio replay. The two pages differ by design, and a visitor may notice. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q16 yes` |

### Q17 (plan choice 7). A tag on the 2024 pleas that news outlets reprinted

| | |
|---|---|
| Question | About seven place records paraphrase a plea for help that news reprinted in 2024. The plan recommended showing them with a tag "plea reported in news", from a short reviewed list of record ids, and asked for your approval of the tag because the records describe real people without names. The page was built without the tag: the records appear as ordinary place records. Should it stay that way? |
| Why it matters | These records describe real people, without names. |
| Options | **1.** No tag, as built. **2.** Add the tag from a reviewed list of record ids, as the plan recommended. |
| Recommended | **Option 1 for the pitch.** This goes against the plan's own recommendation, so weigh it as such. |
| Reason | A tag singles out real pleas, and it needs a list of record ids that a person has reviewed. No such list exists yet. Once one of you has reviewed the list, option 2 is a small change. |
| Risk | Without a tag a trainee cannot tell a depth report from a plea. The records are never shown as calls received either way. |
| One thing to settle | The decision log (R18) records "not applied" as a build choice, not as your decision. The plan file on the branch lists it under "Owner decisions" as "not approved". Please say which is right, so that the two files agree. |
| Who | Putu |
| Reply | `Q17 option 1` or `Q17 option 2`, and one word on the record: `decided` or `build choice` |

### Q18 (decision R17, points a to f; merge report item 12). Limits of "saved when opened"

| | |
|---|---|
| Question | You approved that each study area of the evidence library is saved for offline use when someone opens it. Six limits were chosen while building; the letters are those of R17. Do you confirm them? **(a)** The offline installation may not exceed 12 MB; above it the build fails. **(b)** An area larger than 20 MB is saved only with its button: Bang Ban and Sena (31.0 MB) and Rangsit (51.3 MB). **(c)** Nothing is saved on open when the browser asks sites to use less data, and a copy the reader removed is not saved again until the reader asks. **(d)** A file is stored only when its SHA-256 matches; a saved area survives a new deployment and can be removed. **(e)** The database archives offered for download (188.8 MB) are never part of a saved copy. **(f)** The historical report's page is not in the installation, so it needs a connection. |
| Why it matters | The installation is 10.5 MB in place of 301 MB. The limits decide what works without a connection at a venue. |
| Options | **1.** Confirm all six. **2.** Change a number. **3.** Save the two large areas on open as well. |
| Recommended | **Option 1.** |
| Reason | They keep the first install small and never use a reader's data plan unasked. |
| Risk | Rangsit and Bang Ban and Sena are not available offline unless someone uses their button while connected. For an offline demo that step has to be on the checklist. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q18 yes` |

### Q19 (decision R17, point h; merge report item 14). The short map-background notice on the Public page

| | |
|---|---|
| Question | On the Public page a notice is shown when the map background cannot load. Its form was changed twice during the merge work. It is now one line with one button ("Map background unavailable", "Options"), placed in one column directly below the "View map results as a list" button at every width; the full sentence and the actions open behind the button. R17 says this was not a question to you and was fixed alongside the two things you approved. Do you confirm it, or do you want it changed? |
| Why it matters | It is on the page the public sees, and R17 lists it as not put to you. |
| Options | **1.** Confirm as built. **2.** Say what should change. |
| Recommended | **Option 1.** |
| Reason | Before the fix the notice lay under the search field or the list button on phones and in short laptop windows, and could not be read or tapped (merge report, item 14). After it, the merge report measures no overlap at nine screen sizes, in Thai and in English. |
| Risk | The notice shows less text until "Options" is tapped. While it is shown the map is at least 448 px tall, so a short screen scrolls 88 px further. Three small overlaps that do not involve the notice remain (Q48). |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q19 yes` |

### Q20 (build notes of the plan on the branch). Ten small choices made while building the page

| | |
|---|---|
| Question | The build notes list choices the plan did not make. Do you accept them? (1) Urgency has two steps: life at risk for people on a roof, or water at chest height or above with people present; urgent for an infant or a bedridden person, or no food for a day; information otherwise. (2) In trainee mode a shelter counts from the start of the day it is first reported. (3) The clock card states a model limit at every hour ("the current is not modelled"). (4) Roads that are passable again are not named while the river falls. (5) The table footer is short; the full sentence is one tap away. (6) At district zoom a shelter star is a 28 px target, where every other control has 44 px. (7) A device starts with five example callsigns that name no real unit. (8) A closed item can be reopened. (9) In trainee mode a shelter's occupancy counts are held back. (10) A report saved on this device has no Assign and no brief. |
| Why it matters | They shape what a trainee sees and does. None computes a score or a class. |
| Options | **1.** Accept all. **2.** List the ones to change. |
| Recommended | **Option 1, after Q11.** |
| Risk | Choice (1) is a rule about invented items only, but a trainee may carry it into real work. Choice (6) is a small target on a tablet. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `Q20 yes` |

## Part 3. Reading rules the protocols leave open

Each item groups points that one answer can settle. "Keep" means: confirm what the code did, as your reading of a
point on which the signed files are silent. It is recorded in the decision log and named in the outputs. It does not
edit a signed file. If you want a reading written into the protocol text itself, that is v2.

One item is not of that kind. Q30 is about a run that departs from a sentence the signed protocol does state. It
stands on its own so that a `yes` to a list of routine readings cannot settle it.

### Q21 (E1-OP1 second half, E8-OP7, E10-OP10 and others). What does `local` keep out of the repository, and off a slide?

| | |
|---|---|
| Question | A result is `local` when one of its inputs is not cleared for publication. The signed rule (guardrail GR6) says only that such a result may not be written under the public website folder. It does not say whether its numbers may be in Git, or on a slide. What do you want `local` to mean? |
| Why it matters | Today's practice is mixed. Most layers and per-tambon tables below `public` are outside Git. Two kinds of per-tambon table below `public` are in Git since 4 October: the age table (Q2) and the radar tables (Q7). The committed receipts and the README hold figures for a whole case. The README itself calls the separation "nominal" for SE1: the score and class of each tambon can be worked out from committed files, and a count such as "E for all eight" states the class of each tambon. |
| Options | **1.** `local` keeps things out of the public website folder only; figures may be committed, and said on a slide, with credit and licence. **2.** `local` means team only: not in Git and not on a slide. The figures leave the receipts and the README, and stay in the Git history. **3.** Today's middle way stays, with its note, and a slide shows no figure of a `local` input. |
| Recommended | **Option 3, and fix the cause input by input:** Q2 for the age data, Q6 for the layer of 22 October, Q7 for Sentinel-1. Leave what is committed where it is. Commit no new per-tambon file below `public`. |
| Reason | GR6's words stop at the website folder, so option 3 adds no rule. Taking a figure out of a file does not take it out of the history, and the history must keep the signing commits (R16). After Q2 (option 1) and Q6 the SE1 and O2 results are `public`, and the question is gone for them. |
| Risk | If anyone outside the team can read the repository, figures of layers still marked `local` can be read until Q2, Q6 and Q7 are answered. The product 4009 and radar figures carry their credit and licence; the age table in Git has no licence line of its own yet, as the age review says. Putu knows whether the repository is public; if it is, answer Q2 and Q6 first. |
| After a yes | A decision-log row. The sentences of the README that say "undecided" are reworded at the next run. Nothing is moved. |
| Who | Both |
| Reply | `Q21 yes` (or `Q21 option 1`, `Q21 option 2`) |

| Point | What it asks | Under the recommended answer |
|---|---|---|
| E1-OP1 (second half) | May a figure derived from a `local` layer be committed? The receipts of plan tasks E1 and E5 hold whole-frame figures of the layer of 22 October and of the analysis extent. | They stay. |
| E1-OP1 (the radar tables) | The per-tambon radar tables (`outputs/planning_v1/radar_o1_mae_sai_v1.json` and its sensitivity table) are in Git since 4 October with values for single tambons, made from scenes that have no confirmed record. | They stay, with their credit line; the history keeps them either way. Q7 settles their level: under scope `local` they remain above it, and the answer says so. No new per-tambon radar file is committed before Q7. |
| E8-OP5 (the age table) | The age table of the eight tambons is in Git since 4 October, and the builder treats it as `local`. | It stays. Q2 settles its level; with "public use" the question is gone. |
| E8-OP7 | The README quotes four components per tambon for SE1 from a `local` file, because their own inputs are public. | The table stays, with its note. |
| E10-OP10 | The class counts of each re-run state the class of single tambons. | They stay, with the note. |
| E10-OP8 | The SE1 access tables of the smaller and larger flood levels have public inputs of their own and are outside Git. | Commit them after Q2 (option 1); until then they stay outside. |
| E5-OP8 (second half) | The first SE1 access table, which held ratios, is in the Git history. | The note in the receipt that replaced it is enough. |
| A1-OP5 | Whole-area radar statistics were committed with the Copernicus credit before any signed record. | They stay; Q7 covers the use from then on. |
| E8-OP5 (part) | Do open-licence inputs with no rights record (WorldPop 2020, boundaries, WorldCover, the road context) need a registry entry? | Not now: the code treats them as `public` and writes their credit. Short entries follow after the pitch (Q52). |

### Q22 (E6-OP1 to E6-OP7). The critical-link ranking stays as recorded

| | |
|---|---|
| Question | A critical link is a piece of road that many residents' routes depend on. The ranking of all links was computed on 4 October, and its SHA-256 was recorded "before any scoring", as protocol v1b asks. Three open points could change that table. Do you keep it as recorded? |
| Why it matters | Trigger B of the secondary class reads the 20 highest-ranked links. Scores have been computed since the ranking was recorded. |
| Options | **1.** Keep the recorded table. **2.** Another reading of E6-OP1 or E6-OP5, which gives another table: **v2**. |
| Recommended | **Option 1.** |
| Reason | The table was fixed before scoring so that no result could shape it. None of the 20 highest-ranked links is a connector, and none of the 200 highest-ranked is a graph bridge (a road piece whose removal cuts the network in two). |
| Risk | Under option 1 trigger B cannot fire at Mae Sai, by the README's own reasoning: closing one link that is not a graph bridge cuts nobody off. If you meant graph bridges to enter the 20 so that trigger B can fire, that is a rule change after results. The 20 links (20 consecutive pieces of one street) stay "unreviewed candidates" until Rachmania's desk check. |
| After a yes | A decision-log row. Trigger B can then be computed from the recorded table (Q23). |
| Who | Rachmania (the plan gives her the review of critical links), with Putu |
| Reply | `Q22 yes` |

| Point | What it asks | Keep |
|---|---|---|
| E6-OP1 | May a grade-join connector (a zero-length joint the builder adds between road ends that coincide, decision D13) be a critical link? | It is ranked like any road piece. |
| E6-OP5 | "Add graph bridges": added to what? | Nothing is added. A bridge is flagged and ranked by its flow. |
| E6-OP6 | May a later run change the recorded ranking? | No. Another ranking is v2. |
| E6-OP2 | What does the full reroute of the 200 highest-ranked links write? | Nothing was run. Decide when scenario S3 is built (Q37). |
| E6-OP3 | Is the bridge flag the graph bridge or the map tag `bridge=yes`? | Both are written. |
| E6-OP4 | The tambon of a link whose midpoint lies in no tambon or in two. | The midpoint rule; no such link occurred. |
| E6-OP7 | A zero-minute road piece between two destinations. | The route goes on to the destination with the smaller ID. 40 such nodes, no resident on them. |

### Q23 (E8-OP1 second part, E8-OP8, E11-12, E11-13; download DL-2). The three untested triggers of the secondary class

| | |
|---|---|
| Question | After Q1, what is done about triggers B, C and D? |
| Why it matters | It decides how much of the secondary class is filled by the pitch. |
| Options | For each trigger: build it now, wait, or leave it out. |
| Recommended | **Trigger B: compute it now from the recorded ranking. Trigger C: leave "not evaluated" and define it in v2. Trigger D: approve download DL-2, then compute it.** |
| Reason | Trigger B needs only Q22. Trigger D is fully defined in protocol v1b and lacks one data tile. Trigger C lacks a definition, and the SE1 results are known, so a definition written now would be written with the outcome in view. |
| Risk | The four SE1 rows that are "not evaluated" stay so until trigger C exists, unless trigger B fires, which Q22 says it cannot at Mae Sai: the order is E, A, B, C, D, and trigger D cannot decide a row while trigger C is unknown. So triggers B and D complete the record more than the picture. |
| After a yes | Trigger B is computed (a small run on real tambons, reported). A person downloads the JRC surface-water tile for the east of the frame (about 70 to 100 MB, from the JRC Global Surface Water download page; action 17), then trigger D is computed. Trigger C waits. |
| Who | Both |
| Reply | `Q23 yes` |

| Point | What it asks | Under the recommended answer |
|---|---|---|
| E8-OP1 (second part) | Build the inputs of triggers B, C and D. | B now; D after DL-2; C in v2. |
| E8-OP8 | Trigger C names a hospital or a shelter. The shelter list is pitch level. Does a public result file test trigger C on hospitals alone? | Not answered here: it belongs to the definition of trigger C in v2, with the question of when a facility "loses all vehicle routes". |
| DL-2 | The JRC tile `occurrence_100E_30Nv1_4_2021.tif` is not on disk. Protocol v1b lists the download as needing an owner's approval. | Approve. It also serves the JRC sensitivity note on permanent water (decision D4). |
| E11-12 | The result file holds only part of the inputs of triggers A, C and D, so the parsers can check them one way only. | Accept for format 1.1; carry the evidence when the triggers are built. |
| E11-13 | The secondary class has trigger evidence and no reason code of its own. | Keep: v1a says no new reason code is added for v2. |

### Q24 (E1-OP3, E1-OP4, E5-OP1 to E5-OP4, E5-OP6 to E5-OP8). Flood inputs and access tables: keep what the code did

Why it matters: these readings sit under every access figure. Reason: each was made before or while the first scores
were computed, and follows the nearest signed rule. Risk: E5-OP4 keeps some residents "with access" whom another
reading would count as lost, and E5-OP3 means that the access figures say nothing about 8.1% of residents. Both have
to be named wherever an access gap is shown. Changing either now is **v2**. After a yes: a decision-log row; no run.
Who: Putu for access, Rachmania for flood inputs. Reply: `Q24 yes`.

| Point | What it asks | Keep |
|---|---|---|
| E1-OP3 | How does a 10 m land-cover grid become an area of permanent water? | The footprint of every water cell: 0.989 km² of the reporting frame. |
| E1-OP4 | What shape has the 20 m buffer at a corner? | Round corners, 16 segments per quarter circle. |
| E5-OP1 | Which tambon does a 100 m population cell belong to? | The tambon that holds the cell's centre, the rule protocol v1a states for exposure. Every cell fell in exactly one tambon. |
| E5-OP2 | What does a tambon get where nobody had access before the flood? | The counts and a reason code. No value is put in the place of the missing ratio. |
| E5-OP3 | 6,610 residents (8.1%) are in cells more than 250 m from any road of the network. | They are reported per tambon and are in no access count. Exposure counts every resident. |
| E5-OP4 | Is a destination still a destination when it stands inside the flood extent? | Yes. In SE1, 163 to 177 of the 1,939 main-road entries have every main-road piece at them closed, and residents whose cell snaps to one keep that entry. |
| E5-OP6 | A grade-join connector has no length. Can it be closed? | No. It is never intersected and stays open. |
| E5-OP7 | The plan names one access function, run twice. The run grows one route tree per service. | Kept, and checked against the named function: 27,487 cells, none differs. |
| E5-OP8 (first half) | Should the access step also write each service's "newly lost" share? | No. The tables hold counts only; shares come with the components in plan task E8. |

### Q25 (E7-OP1 to E7-OP3). The age table: keep the signed reading

Why it matters: the age table feeds the vulnerability component. Reason: the national anchors in the signed
protocol were computed the same way. Risk: for TH570901 the border cells move the share by 0.0149, where the two
anchors are 0.1263 apart; that has to be said beside the component. After a yes: a decision-log row; no run.
Who: Putu. Reply: `Q25 yes`.

| Point | What it asks | Keep | Anything else |
|---|---|---|---|
| E7-OP1 | 31 one-kilometre cells lie partly across the national border. Their age mix may include people whose homes are on the other side. | Reading DR-B04 as written: the tambon takes the cell's counts by its share of the cell's area. | Another treatment changes the method behind the signed anchors: **v2**. |
| E7-OP2 | Should a low-to-high range of the share enter the component? | No. The table shows three allocations for information only. | A range in the component is a new rule: **v2**. |
| E7-OP3 | Is a tambon's share rounded before it enters the component? | No. Plan task E8 computes the component from the three age counts. | |

### Q26 (E8-OP2, E8-OP3, E8-OP4, E8-OP6 second half, E8-OP9). The planning assessment: keep what the code did

Why it matters: these readings decide how one row of the result file is formed. Reason: no reading changed a class in
the runs of 4 October. Risk: E8-OP3 would matter in a frame where a tambon has few connected residents; every Mae Sai
tambon passed both conditions by a wide margin. After a yes: a decision-log row; no run. Who: Putu. Reply: `Q26 yes`.

| Point | What it asks | Keep |
|---|---|---|
| E8-OP2 | Which closure level does a tambon's row use? | The default cell of v1b: the flood layer as provided and the central closure level. |
| E8-OP3 | How are confidence conditions C7 and C8 measured for one tambon? | Condition C7 on the hospital service; a tambon where nobody is connected would fail it. Condition C8: a hospital counts when it is in the same connected part of the road network as a populated cell of the tambon, with no time limit. Every tambon passed both by a wide margin. |
| E8-OP4 | The flood layer has a date and no time of day; the format wants an instant. | The last date of the source period at 00:00:00 UTC, said in the file. |
| E8-OP6 (second half) | Should rows that fail a check be reported? | No. The receipt gives the stage and a code, and no row. |
| E8-OP9 | What does a row get when a component cannot be computed, or the tambon has under 100 residents? | No score and no leave-one-out for the first. For the second the score is kept, with no leave-one-out class. Neither occurred. |
| Six choices of plan task E8 | Listed in `docs/planning_assessment.md`: the scenario wording is v1a's lane definition; confidence condition C1 of a scenario is judged on the agency product it is built on; two rounding tolerances; lower-case identifiers; public result files under `outputs/planning_v1/overlays/`; no engine row and no locked row is added. | All six. |

### Q27 (E10-OP4 to E10-OP7, E10-OP9). The ensemble: keep what the code did

Why it matters: these readings decide what each re-run reports. Reason: each is the plainest reading of a short
phrase in protocol v1b. Risk: none changed a class; a later reader may expect a single "axis with the largest
swing" and find none named. After a yes: a decision-log row; no run. Who: Putu. Reply: `Q27 yes`.

| Point | What it asks | Keep |
|---|---|---|
| E10-OP4 | Each re-run reads a confidence class. Which one? | The tambon's own, derived as in plan task E8. Recommended for later: it does not follow the population year either, because v1a says confidence uses no ensemble output. |
| E10-OP5 | "Best and worst rank": ranked by what? | By FPPS among the eight tambons, highest first; a tie goes to the lower code. |
| E10-OP6 | "The axis with the largest swing" is not defined. | The FPPS range along each axis is reported, and no axis is named. |
| E10-OP7 | "People losing 30-minute access": to which service? | Both public services are reported. |
| E10-OP9 | "One at a time": varied from which re-run? | From the default cell alone. |

### Q28 (E11-1 to E11-3, E11-5 to E11-10, E11-14, E11-16 to E11-19, E11-22 to E11-24). The result file format: keep what was built

Why it matters: both parsers refuse a file that departs from these choices. Reason: each is a choice of shape, not
of a number. Risk: E11-22 is the one change: today the gate would let the fixture, a file of invented units, be
written under the public website folder, and an invented unit on a public page can be taken for a place. After a
yes: a decision-log row, and one small reviewed change for E11-22. Who: Putu (the plan gives the review of file
formats to Callixta). Reply: `Q28 yes`.

| Point (number on the overlay page) | What it asks | Keep |
|---|---|---|
| E11-1 | May a file hold a row for the locked tier T4? | Yes, as a placeholder with no value. |
| E11-2 | Engine rows (invented test units): a secondary class, a "high" confidence? | No secondary class; "high" is refused everywhere. |
| E11-3, E11-5 | A row with a missing component; a tambon under 100 residents. | As E8-OP9 in Q26. |
| E11-6 | Must the residents of the age record equal the residents the row is scored on? | Not required: the two come from different years. |
| E11-7, E11-8 | The date relation of a row. | Empty for a row with no flood input; "dated_other" and "season_window" are derived from the dates. |
| E11-9 | The date of the layer of 22 October. | 2024-10-22, v1a's reference date for that case. |
| E11-10 | Which rows does a case file carry? | The case's own rows. Scenario cells, engine rows and the T4 placeholder are not compared with the case. |
| E11-14 | One confidence class for the whole file? | No. Confidence is per tambon and case. |
| E11-16, E11-17 | The list of input roles; the guard "a public flood input declares its source product". | Both. The guard was added in review and is not a protocol rule. |
| E11-18 | One row per tambon, lane, flood input and scenario. | Yes. The 540 re-runs are not rows. |
| E11-19 | Columns of the summary. | Observed, scenario and engine, never a total across them. |
| E11-22 | May the fixture be written under the public website folder? | **Change: never.** |
| E11-23 | Instants are checked by pattern only. | Yes. |
| E11-24 | The file names differ from plan 7.1. | The built names. |

### Q29 (A4-OP3, A4-OP4, A4-OP6, A4-OP7, A4-OP9, A2-OP1, A2-OP2, E1-OP5, E1-OP6, E1-OP11). Radar readings

Why it matters: these decide what the radar candidates are and how they enter case O1. Reason: the radar method was
frozen before any Mae Sai run, and its result is known; nothing is tuned afterwards. Risk: one answer declines a pass
that one reading would give (A4-OP3), and that has to be stated with the result. After a yes: a decision-log row;
the label fix at the next superseding run. Who: Rachmania. Reply: `Q29 yes`. The terrain mask of the signed protocol
is not in this list: it is Q30.

| Point | What it asks | Recommended |
|---|---|---|
| A4-OP3 | The skill bar: does "coverage" mean usable radar input or cells with an answer, and is "no answer" judged per tambon or for the frame? | The outcome of record stays "not met" for the frame, and no pass is of record for one tambon. A single-tambon pass, chosen after seeing that one tambon passes, is **v2**. |
| A4-OP4 | Who removes permanent water: the candidate raster or the flood-input step? | The rasters stay as the frozen method returns them; areas are given both ways. |
| A4-OP6 | How is the frame cut into tiles for the frozen method? | On the tile grid of the GEOID sample, in UTM zone 47N. No other was tried, and none is tried now. |
| A4-OP7 | The label of the layers says "GCP affine". What ran is a second-order polynomial. | Reword the label at the next superseding run. No rerun as a true affine fit. |
| A4-OP9 | The +1 dB level of M1-literal is cut at 0 dB by the second clause of its rule. | Keep the clause. The rule is unchanged. |
| A2-OP1 | The steps of the UN-SPIDER practice were written without a copy of its script, and two layers were replaced by layers on disk. | Rachmania checks the steps against the published script. The replacements stay, as disclosed. |
| A2-OP2, E1-OP5 | The smaller and larger "one pixel" levels of a raster candidate: made how, and by whom? | By the flood-input step: the cells become outlines and get the same 20 m buffer as a vector product (owner choice 2: 20 m for every input). |
| E1-OP6 | "Polygons under 5 pixels are dropped": do two pixels that touch only at a corner form one polygon? | No: only cells that share a side belong together, the rule the loader already uses when it turns cells into outlines. No closure extent of O1 has been built, so no result is in view. |
| E1-OP11 | Should a candidate's receipt carry its three thresholds as numbers, so that the loader can check them? | Yes. |

### Q30 (A4-OP2). A run that departs from a signed sentence: the terrain mask on Mae Sai

| | |
|---|---|
| Question | Protocol v1a is signed. Among the limits of its GEOID split it says: "The GEOID sample has no DEM, HAND or slope layer. M1-v2 is fixed slope-free on GEOID and the HAND/slope mask is applied on Mae Sai as a disclosed difference." HAND is the height of a cell above the nearest stream. The protocol gives no source and no limit for that mask. The Mae Sai run of 4 October applied no mask. How do you want that recorded? |
| Why it matters | The run does not do what a signed sentence says. The first rule of this sheet is that no recommendation bends the signed protocols, so this cannot be confirmed as a routine reading. |
| Options | **1. Record the deviation.** A decision-log row says that the Mae Sai run of the frozen method applied no HAND or slope mask although protocol v1a says one is applied, and why: the protocol gives no source and no limit. Every report of the radar result carries that sentence. Nothing is rerun and no limit is chosen. **2. v2 with limits.** `planning_protocol_v2` names the source and the limits of the mask, with a written reason, and the run is repeated with it. |
| Recommended | **Option 1.** |
| Reason | Limits chosen now would be chosen after the result is known. That is a new rule, and a new rule belongs in v2. Recording the deviation changes no rule and hides nothing. |
| Risk | Under option 1 nothing is rerun, so the outcome of record stays "not met", and a signed sentence stays unfulfilled, said openly. Under option 2 the outcome of a masked run is not known. The drafter does not expect a mask to cure what fails, because the method gave no answer in six of nine tiles, but that was not tested. |
| After a yes | A decision-log row. The sentence is added to the radar result at the next superseding run. |
| Who | Both, because it concerns a signed file; Rachmania for the method |
| Reply | `Q30 option 1` (or `Q30 option 2`) |

### Q31 (A1-OP1 to A1-OP4, A1-OP10). The diagnosis figures: several readings, none "of record"

| | |
|---|---|
| Question | The diagnosis ("Why threshold-only change detection failed at the 16 Sep pass") gives some figures under several readings, because the plan names none. May it stay that way? |
| Why it matters | A slide wants one number. The plan's own 0.421 says: a cell inside the season envelope got darker than a cell outside it in 42.1% of pairs, where 50% means no separation. It is the value for one size of smoothing patch among six (0.467 with no smoothing, 0.299 with the widest). |
| Options | **1.** Keep every reading and name none. **2.** Name one of each as the figure of record. |
| Recommended | **Option 1.** A slide quotes the range with the label "vs a season envelope, not an event map", once two things are in place: Rachmania has reviewed the runs (action 9; the page says she has not), and a radar figure may be said outside the team (Q7 with a publication scope, or a Q21 answer that allows a credited figure on a slide). After Q9 the darkening figure is quoted first under the chosen geocoding. |
| Reason | Naming one now means choosing with every value in view. |
| Risk | A range is harder to say in a pitch. The terrain figures repeat an exploratory script whose values had been seen before, which the result page discloses. |
| After a yes | A decision-log row; no run. |
| Who | Rachmania |
| Reply | `Q31 yes` |

| Point | What is left open | What is given |
|---|---|---|
| A1-OP1 | The plan names no terrain feature. | Low elevation and low slope. The height above the nearest stream was not computed. |
| A1-OP2 | The plan gives 0.421 and no definition. | The definition rebuilt from cleared files, with six sizes of smoothing patch. |
| A1-OP3 | Which geocoding (follows Q9). | Both. |
| A1-OP4 | Which permanent water a diagnosis leaves out. | Three readings; they differ in the third decimal at most. |
| A1-OP10 | On which cells the comparison figures are taken. | All cells, and cells with a slope under 5 degrees. |

### Q32 (A1-OP7 to A1-OP9, A1-OP11). The guard for the two flood products the team has no grant for

Guardrail GR9 of protocol v1a names the two products (the AIT and the MBRSC flood maps). It asks for a test before
each commit that fails when a script reads either of them without a recorded grant, and for none of their numbers
in code or on a public page. The guard is built as a test of the suite and as a command.

Why it matters: it is the team's proof that no figure of those products is used. Reason: the guard does what GR9
can be made to check; the one gap to the signed words is the missing Git hook. Risk: the guard does not see a path
read from a manifest, a name split across strings, or new code inside an old function. The signed v1a still says
"not_built" for GR9, because the file cannot be edited. After a yes: a decision-log row; each person installs the
hook (action 18). Who: Putu, and each person for the hook. Reply: `Q32 yes`.

| Point | What it asks | Recommended |
|---|---|---|
| A1-OP7 | What is a "grant receipt", and where is it recorded? | The guard reads the rights registry. No grant exists. Older code is listed in a baseline, which is not a grant. Keep. |
| A1-OP8 | How far can "no number" be checked? | In the files of the diagnosis task. Older committed files that name a product as a blocked record were not changed. Keep. |
| A1-OP9 | The plan says the scripts "moved". New ones were written, and four older scripts stay where documents and tests name them. | Keep. |
| A1-OP11 | GR9 says "pre-commit". No Git hook is installed. | Install the hook on each machine that commits. Until then, say "runs in the test suite and as a command, not before each commit". |

### Q33. Where runs made after the signing are registered

| | |
|---|---|
| Question | Protocol v1b says every run is reported. It was signed on 3 October and cannot list a later run, and it does not say where one is registered. Today each later run writes a receipt into `outputs/planning_v1/`, and the receipt is registered by path and SHA-256 in a test list and in `run_register/`. Is that the rule for all later runs? |
| Why it matters | The README says this practice holds only "until the owners agree one rule". |
| Options | **1.** Confirm. **2.** Name another place. |
| Recommended | **Option 1.** |
| Reason | A file that is neither listed in v1b nor registered already fails the tests, and so does a registered receipt whose bytes change. |
| Risk | The register is a test file, so adding a run means editing a test. That is deliberate: the change is visible in review. |
| After a yes | A decision-log row; the README sentence is reworded at the next run. |
| Who | Putu |
| Reply | `Q33 yes` |

### Q34 (A4-OP8). A check to allow: are the replay's radar images in the right place?

| | |
|---|---|
| Question | The Mae Sai replay shows Sentinel-1 images made with the same warp as the radar run of record, which is displaced by about 680 m. The replay's layers were never measured. May the agent measure them? |
| Why it matters | The replay is in production and is the demo. If its radar images are displaced, a viewer who compares image and map is misled. |
| Options | **1.** The agent measures them against mapped permanent water, reading only, and reports. Nothing is baked or changed. **2.** Leave it. |
| Recommended | **Option 1, this week.** If the layers are displaced, you choose between a caveat on the page and a new bake. |
| Reason | The measurement is cheap, and the answer is not known. |
| Risk | A new bake changes `docs/demo/replay_numbers.md`, and one diagnosis figure then has to be run again. |
| After a yes | One read-only measurement with a short report. No file of the replay changes. |
| Who | Putu |
| Reply | `Q34 yes` |

## Where the answer is a new protocol version (v2)

None of these is recommended now. Each is listed so that nobody answers it by accident. Each would need
`planning_protocol_v2`, with a written reason and the outputs it affects, and every earlier run stays reported.

| Change | Where it comes up |
|---|---|
| Taking the vulnerability component out of the score | Q2, option 3 |
| Another critical-link ranking, or graph bridges among the 20 | Q22 |
| A definition of when a facility "loses all vehicle routes" (trigger C), and trigger C on hospitals alone | Q23 |
| Counting a destination inside the flood extent as lost, or adding the unconnected residents to the access counts | Q24 |
| A range in the vulnerability component, or another treatment of border cells | Q25 |
| A pass of the radar skill bar for one tambon alone | Q29 |
| A terrain mask with limits for the frozen radar method | Q30, option 2 |

One further choice is advised against and is not in this table: taking retention over only the re-runs that can be
made (Q3, part 5). The README lists it as a choice open to you, because the protocol is silent on a partly run set.

## Part 4. Blocks no score and no page

None of these blocks a score, a page or the Command week, and most can wait until after the pitch. One row has a
date before it: follow-up FU8a under Q55, Tue 6 Oct (see "Dates first"). `Part 4 yes` accepts every recommendation
in both tables.

| Id | Question | Recommended | Why it does not block | Who |
|---|---|---|---|---|
| Q35 (E1-OP2, second half) | Does a candidate of the supervised radar classifier need a rights record for its training data? | Yes; draft it when the classifier is taken up. | R16 defers the classifier. | Both |
| Q36 (E1-OP7) | Is the three-day date rule counted in Thailand time or in UTC? | Leave open. The first case within a day of the edge stops and asks. | No case is near the edge. | Rachmania |
| Q37 (E6-OP2) | What does the full reroute of the 200 highest-ranked links write? | Decide when scenario S3 is built. | Nothing was run. | Rachmania |
| Q38 (E11-4) | Case SE2-dist has two components and no class, and fits no row of the result file. A new kind of row, or another file? | Decide with case SE2. | R16 defers SE2. | Putu |
| Q39 (E11-15) | The blocks of plan 7.1 that the format does not carry (equity, shelter supply, travel minutes, more ensemble outputs). | Add them in a later format version, with plan tasks E9 and E12. | Their modules are not built. | Putu |
| Q40 (E11-20, E11-21) | Where may a would-be class be shown, and what does the skill caption beside a radar would-be class say? | Studio's verification queue only, as v1a says, until O1 has rows. | O1 has no row. | Both |
| Q41 (E10-OP3, rest) | After the walking build: build the access table of the middle shelter set, or invoke declared cut line 8, which drops that set? The plan lists its cuts "in order": line 8 comes after lines 6 and 7, and line 7 would drop a radar run that has already been made. | Decide after Q8. If line 8 is invoked, say what happens to lines 6 and 7. | Not needed for a public headline. | Both |
| Q42 (plan choice 8, second half) | Reports that travel between devices need a deployed service, consent wording, a retention period (the plan proposes 72 hours), a named data controller and an agreement with an agency. | Nothing before the pitch. Name the data controller before any such work. | The plan puts it after stage A. | Both |
| Q43 (merge report 3) | The address of the candidate report, and whether the study library lists the scoring pages. | Keep `/studio/candidate-report/`; add the library links after the pitch. | No page is broken. | Putu |
| Q44 (merge report 4) | Should the replay follow equity 2.0? | Not before the pitch. | The replay's equity rule (R8, option B) is built and in production; a change needs a new parity fixture and new wording. | Both |
| Q45 (merge report 5) | The scoring line's landing page is not served. Keep it, or remove it with its assets and the seven packages only it uses? | Remove after the pitch. | Nothing serves it. | Putu |
| Q46 (merge report 6) | The site moved to Next 16.3.5 and the tests to Vitest 4.1.11; all checks pass. | Confirm. | Already in use. | Putu |
| Q47 (merge report 7) | The referrer header is `strict-origin-when-cross-origin`; the stricter `no-referrer` would also work. | The stricter one, after the pitch, with a preview check. | A header change before a demo is a risk for no gain on the day. | Putu |
| Q48 (merge report 9, 14, 15) | Duplicate files of the two lines, stale addresses in older documents, and three overlaps of a few pixels on the Public page map that do not involve the notice of Q19. | Clean up after the pitch. | None breaks a page. | Putu |
| Q49 (merge report 13) | The "Studio" link in the eight case briefs opens the study library and ignores the case. A fix rebuilds the briefs and changes their pinned SHA-256 values. | Fix after the pitch, to `/studio/candidate-report/`. | The briefs are pinned for the release. | Putu |
| Q50 (DL-1, DL-3, DL-4) | Three downloads that protocol v1b lists as needing approval: a JRC tile and a terrain tile for case SE2, and the Sentinel-1 pass of 18 September 2024 (about 1.3 GB; decision D12). | None now. | SE2 is deferred (R16), and the UN-SPIDER reproduction ran on the pair on disk. | Both |
| Q51 (follows Q9) | Install SNAP for a terrain-corrected radar run that supersedes the chosen one. | After the pitch, if Q9 is answered with option 2. | The skill-bar outcome is the same in both runs on disk. | Rachmania |
| Q52 (E8-OP5, part) | Short registry entries for the open-licence inputs. | After the pitch. | The code already writes their credit. | Both |
| Q53 (decision log, last section) | The log says Rachmania has not signed it directly, and its section "Rachmania's confirmation" is empty. R11 to R15 were given by Putu for both owners. | Add one dated line. It costs a minute and can be done any day. | Optional in the log's own words. | Rachmania |
| Q54 (lane report) | About 440 MB of rasters of the first radar runs lie beside the current ones, outside Git. | Keep them until after the pitch. | Disk space only. | Rachmania |
| Q55 | The replay follow-ups of the decision log (next table). | As in the table. | The replay is in production and none of these blocks it. | see table |

**Q55, the replay follow-ups still open in the decision log.** FU and a number is the follow-up's number in
`docs/decision-log-d1-d16.md`. FU8a carries a date, Tue 6 Oct. The Thai language check (roadmap item H12) is not
asked again: R18 says it stays unsigned for the hackathon.

| Id | What waits | Recommended | Who |
|---|---|---|---|
| FU5 | In commit 129ff03, was the knot of 10 Sep 18:15 moved before or after the VIIRS comparison was first computed? And the review of the fields of revision r4. | Answer from memory or notes. If it is not known, keep today's wording, which does not present the comparison as independent. | Putu |
| FU6 | The wording of the rule for when the equity card shows no ratio. | Read and approve. | Putu |
| FU7 | Method review of the capacity-aware shelter plan (four choices). May the page keep naming the DDPM shelter list as the source of listed capacities? Only the source is named; none of its values is used or published. | Review. Keep naming the source. | Rachmania; both |
| FU8a | Who receives the check sheet for shelter candidates, by when (the roadmap says Tue 6 Oct), and do the six role codes fit? | Name one contact this week, or say "not conducted" at the pitch. | Both |
| FU8b | May free-text access notes ever be published? | No. As built, only the fact that a note was given is kept. | Both |
| FU8c | The licence statement of the export pack (ODbL 1.0 as a database derived from OpenStreetMap; the other inputs by attribution). | Rachmania reads it. | Rachmania |
| FU8d | The export budget of 1.0 MB, apart from the 6.5 MB data budget. | Keep. | Putu |
| FU8e | The reported-shelter list quotes occupancy figures from public reports, one of which mentions a July 2025 municipal list of about 200 places. Should that sentence leave the manifest? | Keep it until the method review; it is a quotation with its source. | Both |
| FU9 | Method review of the Sentinel-2 water check (four choices, and the 15 Sep sentence of follow-up 10). Three owner points: (e) add a land-cover input so that the page can state the cropland share; (f) may a later model change be tuned to this check; (g) bake times recorded with a UTC+7 label on a UTC+8 clock. | Review. (e) No new input before the pitch. (f) No; the manifest's rule stays: a comparison used for tuning is relabelled as calibration-informed. (g) Correct the label at the next bake. | Rachmania; both |
| FU10b | A site that a returned check reports as not usable keeps its rank, with a "Local check" line. Is that enough until a plan restricted to checked sites exists? | Yes. No sheet has been returned. | Both |
| FU10e | Bridge decks are not modelled; 14 of the 112 bridge ways show impassable hours. Keep the hours with the caveat, or blank them? | Keep, so that the table agrees with the page. | Both |
| FU10f | Should the two capacity bounds be renamed? | Rachmania decides at the method review. | Rachmania |
| FU11 | The new equity sentences in English and Thai. Should the default scope stay "residents whose homes flood", although it can show no ratio? | Read. Keep the default; the card says why no ratio is shown. | Putu; both |
| FU12 | The season envelope on the replay: method review; (a) should a bake without the layer stay possible; (c) a land-cover input; (d) the line of credits under the export buttons. | Review. (a) Not now: the rights record is confirmed, and if it were ever withdrawn the layer is taken out first. (c) With point e of FU9. (d) Keep. | Rachmania; both |
| FU13a | Which exposure rule does SE1 use, so that the replay page leads with the same count? | Protocol v1a already states it: residents whose population cell has its centre inside the extent. The page leads with that count, as built, and gives the replay's own count beside it, which also settles point b of follow-up 12. The cross-check waits for the result file (Q1). | Rachmania |
| FU13b, FU13c | The longer caption under the map (92 to 128 px on a wide screen), and the wording of the export credit with its change note. | Keep the caption; read and approve the credit. | Putu |
| FU13d | The "other inputs" section of the licence notice (a caution, not legal advice). | Rachmania reads it. | Rachmania |
| FU13e | Should an unused sentence of the Python equity module also name the denominator? It would then differ from the unchanged module. | Leave it: the sentence is on no page. | Both |
| FU12f, FU13f | The hatch of the envelope layer, a hatch drawn at screen resolution at street zoom, and the review of the export pack (follow-up 8). | Callixta's design review, after the pitch. | Callixta |
| FU13h | A tool that reads the envelope check must read the key `compared_with`. | No decision: a note for whoever writes such a tool. | nobody |

## Things only a person can do

These are actions, not questions. Logins, emails, downloads and installs are done by people; the agent only drafts.
A date is that of restructuring plan v2 (sections 8 and 9) unless it is marked "proposed": then the plan has none
and the drafter proposes one. A name marked "proposed" is the drafter's suggestion too.

| Action | What | Who | Date | If it does not happen |
|---|---|---|---|---|
| 1 | Look at the preview of PR #43 (Q10). | Putu | this week (proposed) | The merge of the unified branch waits. |
| 2 | See the new Command page: approve the push for a preview, or run it locally (Q11). | Putu | this week (proposed) | Q12 to Q17 and Q20 cannot be answered from a preview, and `/command/` stays the old page. |
| 3 | Check three licence points on WorldPop's product page (Q2), and four on the Copernicus legal notice and one on the terms page of the Copernicus Data Space (Q7). | Both | with Q2 and Q7 | Both drafts stay pending. |
| 4 | Read the first SE1 results (Q4). | Both | before any page shows them | R18: nothing is shown. |
| 5 | Desk check of the access figures of the tambon whose access gap and road criticality are both 100, which the README asks for "before anyone repeats it" (Q4). | Putu (proposed: the plan gives him the review of the planning assessment) | before Q4 is answered (proposed) | The one class B of SE1 is not repeated on a page or a slide. |
| 6 | When the unified branch is merged: "Create a merge commit". Never a squash and never a rebase (merge report item 1; R10, R16). | Putu | at the merge | The signing commits leave the history and the protocol tests fail on master. |
| 7 | Desk check of the 20 highest-ranked critical links (plan task V1). | Rachmania | Thu 15 Oct | They are shown as "unreviewed candidates". |
| 8 | Review the radar run and the steps of the UN-SPIDER reproduction (Q9, Q29). | Rachmania | before O1 is used | The result page keeps saying that the run is not yet reviewed. |
| 9 | Review the diagnosis runs. The diagnosis page says: "Rachmania owns this lane and has not yet reviewed the runs" (Q31). | Rachmania | before a diagnosis figure is said on a slide; the number freeze is Fri 23 Oct (proposed) | No diagnosis figure goes on a slide. |
| 10 | Outreach: a flood product from GISTDA dated to the event (with its Repeated Flood Areas), the AIT/JAXA permission, the UNOSAT 3991 vector. Log any reply as `docs/provider_response_logging_guide.md` says. File UNOSAT's original "we approve the use" message (R4; follow-ups 1 and 4). | Rachmania; Putu for the UNOSAT message | Sat 10 Oct, the plan's cut-off | The plan's fallbacks: the observed lane stays as it is, trigger D uses JRC, no AIT processing, 3991 is cited as context only. |
| 11 | Ask the organisers: the length of pitch and questions, whether the website may be shown running, the date of Mentoring II. | Callixta, in the plan | was due Fri 2 Oct | A 10-minute and a 5-minute version; the offline ZIP by default. |
| 12 | The list of documented 2024 impacts for the Level-5 check (plan task V4). The plan wanted it fixed before scoring. No such list is in the repository, and scores exist since 4 October. | Rachmania | before the pitch | Either write it now and say that scores already existed and whether its author had seen them, or mark the check "not conducted". Recommended: write it, with that sentence. |
| 13 | A practitioner review of about 30 minutes with a logged form (plan task V5). | Rachmania's network or the mentors | Sat 24 Oct | "Not conducted" on the Level-5 row. |
| 14 | A second laptop for a rerun from a clean clone (plan task R2b). | Callixta or Rachmania | Mon 26 Oct | "Second-machine reproduction not run" in the claims. |
| 15 | Install the `requests` package locally (`uv sync --all-extras`), so that two tests also run on your own machine and not only in the automatic checks on GitHub (merge report item 10). | Whoever runs the suite | any day | Two known failures stay. |
| 16 | Look at the site size on the first preview deployment: the evidence library is 278 MB and the studies are 119 MB (merge report item 8). | Putu | at the first preview | Unknown until someone looks. |
| 17 | Download the JRC tile of DL-2, if Q23 is a yes. | A person | after Q23 | Trigger D is not computed. |
| 18 | Install the Git hook of the guard on each machine that commits, if Q32 is a yes: the file `.git/hooks/pre-commit` calls `scripts/check_ait_mbrsc_guard.py`, as that script's own note says. | Each person who commits | after Q32; this week (proposed) | The guard runs in the test suite and as a command only, and every page that describes it has to say so. |

Dates of the plan that both of you hold: Wed 14 Oct, the Mae Sai completion check (plan task V2); Sun 18 Oct,
feature freeze; Fri 23 Oct, number freeze; Tue 27 Oct, the single release; Sat 31 Oct, the pitch.

## Already answered, and not asked again

| Point | Answered in |
|---|---|
| The purpose and banner of the new Command (plan choice 1) | R18 |
| Who reviews the Thai text (plan choice 8, first half; roadmap item H12 for the hackathon) | R18 |
| What `/command/` is; the GeoAI research table off Command; study areas saved when opened | R17 |
| The reading of the 0.40 condition; whether any M1-v2 tuning ran before the agent's | R15 |
| The compute windows of the corridor run and of the vehicle build | R13, R14 |
| The 23 owner choices of protocol v1b, with readings DR-B01 to DR-B08 | R12 |
| Decisions D5, D8, D10 and D14 to D16 | withdrawn in R9 |
| The denominator of the equity ratio (option B) | R8 |

## About this sheet

- **Sources.** In the repository, on branch `claude/owner-unblockers`: `outputs/planning_v1/README.md`;
  `docs/planning_assessment.md`; `docs/planning_assessment_overlay.md`; `docs/unified_lineage_merge_report.md`,
  section 8; `docs/decision-log-d1-d16.md` through R18;
  `docs/proposal_execution/automated_track/MAE_SAI_RADAR_CANDIDATES_RESULT.md` and `WHY_THRESHOLD_ONLY_FAILED.md`;
  `docs/proposal_execution/SOURCES_AND_RIGHTS.md`; `outputs/cdse_mae_sai_acquisition_manifest.csv` and the radar
  receipt `outputs/planning_v1/radar_o1_mae_sai_v1_receipt.json`; the replay's bake script and its published
  `timeline.json`; the three drafts named in part 1; the two signed protocol files, read only. On branch
  `claude/command-exercise` at commit `7453751`: `docs/command_exercise_plan.md` and the file that reads the
  planning result files for the Command table. Not in the repository: restructuring plan v2 (sections 8 and 9)
  and the reports of the engine and radar lanes of 4 and 5 October 2026.
- **Source timestamp.** The state of those files on 5 October 2026. The runs they describe were made on 3 and
  4 October 2026 (UTC). The flood layers are of 2024: the season envelope of August to October, the layer of
  22 October, and the Sentinel-1 pass of 15 September 23:16 UTC.
- **Confidence.** Medium that the list is complete for the committed sources: every open-point id of the README and
  every numbered point of the overlay page is placed in one item, and a test holds that list
  (`tests/test_owner_decision_sheet.py`). Low for the recommendations: they are a desk reading by an AI coding
  agent. No owner has read them, no provider page was opened, the manifest copy outside Git was not opened, and the
  Command page was not looked at in a browser for this sheet.
- **Assumptions.** The decision log is complete through R18. The pitch is on 31 October 2026, as the plan says.
  The drafter does not know whether the repository can be read from outside the team. The build notes on the
  Command branch describe what is built. PR #43 is the pull request of the unified branch. The local copy of the
  remote branches is up to date. Where this sheet names who should answer or act, it follows the review lanes of
  the plan and the names the decision log records; neither of you has agreed to that split.
- **Changes after the review of 5 October.** Q7 now quotes both manifest notes and no longer rests on "the same
  note". Q2 says what "pitch use only" costs. Q10 and Q11 separate the preview of PR #43 from the new Command page,
  of which no preview exists. The terrain mask of the signed protocol has its own item (Q30). The order changed: the
  gate of R18, the older ranking on the Command archive page and the rights record of product 4009 moved into
  part 1. Point h of R17 is asked (Q19), and open point E1-OP9 stands beside the Sentinel-1 record (Q7). A dated
  list opens the sheet, four actions were added, and the list of words was extended.
- **Notes added after decision R19 (5 October 2026).** The sheet was drafted when the decision log ended at R18.
  R19 swapped the two Planning addresses the same day: the map workspace is at `/command/`, the planning overview
  at `/command/ver2/`, and `/command/archive/` forwards. Two dated notes say what that changes, under Q5 and under
  Q12. No question, count, option or recommendation was changed. Elsewhere on the sheet, `/command/archive/` still
  names the map workspace and "today's `/command/`" the text page, as they were when it was drafted.
- **Ids of the first version.** If you already answered with an id of the first version, this table places it.

  | First version | This version |
  |---|---|
  | A1, A2, A3, A7 | Q1, Q2, Q3, Q4 |
  | A4, A5, A6 | Q7, Q8, Q9 |
  | B1 | Q10 and Q11 |
  | B2 to B7 | Q12 to Q17 |
  | B8, B9, B10 | Q5, Q18, Q20 |
  | C1, C2 | Q21, Q6 |
  | C3 to C10 | Q22 to Q29 (the terrain mask of C10 is now Q30) |
  | C11 to C14 | Q31 to Q34 |
  | D-1 to D-21 | Q35 to Q55 |
  | P1 to P14 | actions 1 to 18, renumbered; see the table of actions |

- This sheet is not legal advice and not an official warning. It computes no FPPS, no class and no value for a
  tambon, and it names no tambon beside a score or a class.
