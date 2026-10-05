# Owner decision sheet, 5 October 2026

Status: **PENDING** (questions for both owners; nothing on this sheet is decided)

For Putu and Rachmania. Written by an AI coding agent on 5 October 2026. The team rule is "agents draft, humans
sign": this sheet is not a decision, and no code reads it. It gathers every point that waits for you, from the
files listed at the end, so that you can answer in one sitting. Nothing was computed for it. Every figure is copied
from one of those files.

## Summary in ten lines

1. The first planning scores for real tambons exist. They are for case SE1, the 2024 season-envelope scenario: class B once, D three times, E four times. They are scenario results, not an observation of any day.
2. No page can show them yet. Two answers stand in the way: **A1** (open point E8-OP1), which lets the result file be written, and **A2** (E8-OP5), the review of the age data that keeps every score below the public level.
3. Three record drafts wait for you in `docs/proposal_execution/`: the Sentinel-1 rights record (A4), the age-data review (A2) and the walking-build window (A5). Each is pending, and no code reads any of them.
4. No class can be called stable yet. 90 of the 180 re-runs the stability rule needs cannot be made until **A3** is answered. Until then a class can at most be shown as "unstable: verify".
5. The radar case O1 cannot be scored. It needs A4 (rights) and A6 (where the radar pixels sit on the map). Its rows would be class E anyway: the radar method gave no answer for 77.3% of the area, and the limit is 20%.
6. The new Command page is built at a temporary address. Choices 2 to 6 of its plan are built as recommended and wait for your yes (group B). Choice 7 is not applied.
7. Group C names 81 of the 96 open points of the engine, radar and file-format tasks: places where the signed protocols are silent. For most the recommended answer is "keep what the code did", and one reply settles a whole group.
8. Eight possible changes are marked **v2**: they cannot be answered here, because they would change a signed rule after the scores were seen. They need a new protocol version with a written reason.
9. Group D can wait until after the pitch (31 October 2026 in the plan). A last table lists things only a person can do, with their plan dates.
10. A recommendation is not a decision. Nothing changes until your answer is a new row in the decision log, after R18.

## How many items, and how to answer

| Group | What it holds | Items | Open points of the engine, radar and file-format tasks named in it | Other points in it | Answer with the id and one word |
|---|---|---|---|---|---|
| A | The few answers that unblock the most | 7 | 15 | decision R18: read the results | A1, A3, A5, A6, A7 (A2 and A4 need a page checked first) |
| B | The new Command page | 10 | 0 | plan choices 2 to 7; R17 part 1 and points a to g; ten build choices | B2 to B10 (B1 is "look at the preview") |
| C | Reading rules the protocols leave open | 14 | 81 | download DL-2; six choices of task E8; the register of later runs | all fourteen |
| D | Can wait until after the pitch (items D-1 to D-21) | 21 | 9 | plan choice 8, second half; nine items of the merge report; three downloads; 20 rows of replay follow-ups | all, or `D yes` for the whole group |
| | Things only a person can do (not questions) | 14 | | | none: they are actions |

Those tasks have 96 open points in all: 72 with an id in `outputs/planning_v1/README.md` and the 24 numbered points
of `docs/planning_assessment_overlay.md`, written here as E11-1 to E11-24. Each is in one item at least. Some are
split over two or three groups, so the column adds up to 105.

**How to answer.** Reply with the item id and a word, for example `A1 yes`. "Yes" always means "as recommended". A
letter or a number picks another option: `A2 B`, `A6 4`. Several at once is fine: `C5 yes, C6 yes, C7 yes`. Where
one word is not enough, the item says what else is needed (a provider page to check, a date, a name).

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

**If you have ten minutes:** A1, A2, A3, A7 and B1. **If you have half an hour:** all of A and B, then each C item
with one `yes`.

## Words used

| Word | Meaning here |
|---|---|
| Tambon | Subdistrict. The Mae Sai frame has eight. |
| FPPS | Flood Preparedness Priority Score, 0 to 100, from five components. |
| Class, rule v1 | The A to E class that counts (the binding one). |
| Class, rule v2 | A second-opinion class, always labelled "secondary", never binding (decision D6). It tests five triggers in the order E, A, B, C, D. |
| Case SE1 | The 2024 season envelope as a scenario: every area mapped as water at some time from August to October, treated as flooded at once. |
| Case O2 | The agency layer of 22 October 2024: late-season residual water. It does not describe the September flood. |
| Case O1 | The team's own radar flood candidates from the Sentinel-1 pass of 16 September 2024. |
| Overlay | The one result file of a case that every page reads. |
| Rights level | `local` (team only), `pitch` or `public`. A result takes the lowest level among its inputs. |
| Ensemble, re-run | The same calculation repeated with one declared choice changed (flood layer 20 m smaller or larger, a stricter closure rule, other weights). 540 re-runs per case; 180 of them count for a public result. |
| Retention, headline | Retention is the share of re-runs in which a tambon keeps its class. A class may be shown as a headline only at 60% or more; otherwise it is shown as "unstable: verify". |
| Receipt | The small file every run writes: inputs and outputs by SHA-256 (a fingerprint of the bytes), parameters, times. |
| Of record | The one run or build that later steps may rest on. Anything else is a candidate. |
| Compute window | A few minutes in which no other FloodGuard job runs on the machine, written into the receipt. |
| Geocoding | Giving each radar pixel its position on the ground. |

## A. The few answers that unblock the most

**The first real planning scores exist, and they cannot reach a page yet.** Plan task E8 computed them on
4 October 2026 for the season-envelope scenario (SE1) and for the layer of 22 October (O2). What stands between
the SE1 scores and a page:

| Step | Waits for |
|---|---|
| The SE1 result file (overlay) is written | **A1** (E8-OP1) |
| Its rights level is `public` | **A2** (E8-OP5) |
| A class may be shown, and with which words | **A3** |
| You have read the results | **A7** (decision R18) |
| A page reads the file (Command columns, public band, briefs) | engineering after the four answers; no further owner answer |

Three record drafts were prepared for you on 5 October 2026 in `docs/proposal_execution/`. Each is marked pending,
and a test fails if any code treats one as confirmed:

- `rights_basis_sentinel1_v1.json` with `rights_basis_sentinel1_v1_NOTICE.txt`: the Sentinel-1 rights record (A4);
- `age_data_purpose_review_v1.md`: the review of the 2024 age data (A2);
- `walking_build_compute_window_v1.md`: the compute window of a walking build (A5).

### A1 (E8-OP1, E11-11). May a result row say "not evaluated" for its second-opinion class?

| | |
|---|---|
| Question | Rule v2 tests five triggers in the order E, A, B, C, D. Nothing yet tests B, C or D. May a row say "not evaluated" there? |
| Why it matters | For four of the eight SE1 tambons the second-opinion class depends on B, C or D. The file format (overlay schema 1.0) cannot say "not evaluated", so the SE1 overlay was not written. Without it no page, brief or Command column can read the scores. |
| Options | (a) Allow "not evaluated" on the secondary class. That changes the file format (schema 1.1), not a protocol rule. (b) Build the tests for B, C and D first: B waits for C3, C needs a rule the protocols do not give (v2), D needs a download (C4). (c) Do (a) now and fill in each trigger when it becomes possible. |
| Recommended | **(c).** Also write "not evaluated", never "false", for a trigger nobody measured. Today trigger B is written "false" on all eight O2 rows although nobody measured it. |
| Reason | It is the true state. The binding class does not depend on the second one. The protocols state no result for a trigger nobody tested. |
| Risk | At the pitch the secondary class of SE1 reads E for four tambons and "not evaluated" for four. Rule v2 is a predeclared axis (decision D6), so the gap has to be said out loud. The format change touches both parsers, the fixture and the 113 shared refusal cases. |
| After a yes | The format change is made and tested on invented units. The SE1 run is repeated with `--replace --reason` (a run on real tambons, reported; the same eight rows are expected) and writes the overlay. The O2 overlay is rewritten the same way. Whether SE1 may then go to a page depends on A2, A3 and A7. |
| Who | Both |
| Reply | `A1 yes` |

### A2 (E8-OP5). May results that use the 2024 age data be shown outside the team?

| | |
|---|---|
| Question | One of the five score components uses WorldPop's 2024 age counts (modelled people per 1 km cell, by age). Protocol v1b says of them: "Public derivatives require purpose-specific review." No review is recorded. Do you record one, and with which answer? |
| Why it matters | Until you answer, every score and class is held at `local`, also for SE1, whose other inputs are public. Nothing with a score can go on a page or into the pitch. The age table of the eight tambons is already in Git since 4 October, so your answer has to cover it too. |
| Options | The draft `docs/proposal_execution/age_data_purpose_review_v1.md`, section 7: **A** public use, **B** pitch use only, **C** decline. Five conditions can be attached to A or B. |
| Recommended | **A with all five conditions**, after one of you has checked the three licence points of the draft's section 2 on WorldPop's product page. |
| Reason | The data are coarse, modelled and openly catalogued (CC BY 4.0, as the repository records it). The smallest tambon has 3,197 modelled residents in the age table. The design already gives tambon-level output only, the words "modelled, not observed", and the class without this component beside every class. |
| Risk | Four of the eight tambons take counts from cells that straddle the national border, so a public "vulnerability" label rests partly on people who are not their residents. Nobody has checked the licence points against the provider's page. If either worries you, B keeps the pitch whole. With C no score can be shown at all, and taking the component out of the score is **v2**. |
| After a yes | A decision-log row. A reviewed code change sets the level of the age counts and cites the row. The SE1 run of E8 is repeated, then E10 (real tambons, reported). With A the SE1 result is `public` and its per-tambon table can be committed. |
| Who | Both |
| Reply | Needs more than a word: `A2 A, conditions 1 to 5, licence checked on <date>` (or `A2 B`, `A2 C`) |

### A3 (E10-OP1, E10-OP2, E10-OP11, E10-OP12). When may a class be shown as stable?

| | |
|---|---|
| Question | The protocol shows a class as a headline only if the tambon keeps it in at least 60% of a fixed set of re-runs: 180 for a public result. Only 90 can be made today. The other 90 need the "2024-rescaled demand" (2020 residents scaled to 2024 totals), and its formula leaves two details open. What do we do meanwhile, and how do we get the missing 90? |
| Why it matters | No class of SE1 or O2 can be called stable. The demo tambon of protocol v1a is then "the highest-FPPS unit, shown as unstable: verify". |
| Options | Four sub-answers. **(a) Words on a page until the rule can be evaluated:** show the class as "unstable: verify" with the note "stability not evaluated yet: 90 of 180 re-runs made", or show no class. **(b) E10-OP2, the two open details of the rescale:** take them from the script that the reason of your own choice 12 names (a 2020 cell belongs to the 1 km cell that holds its centre; 2020 residents whose 1 km cell has no usable 2024 count are reported as a figure of their own, neither set to zero nor rescaled), or state other rules. **(c) E10-OP11, which re-runs count for a result that is not a public overlay:** the protocol's words (540 in general, 180 for a public overlay), with both reported and no status set until the result is a public overlay. **(d) E10-OP12, declared cut line 6** (drop two axes; 45 public re-runs remain, and with WorldPop 2020 kept all of them have been made): invoke it now, or not. |
| Recommended | **(a)** show with "unstable: verify" and the note. **(b)** yes, the two rules of that script. **(c)** as the protocol words it. **(d)** do not invoke the cut now. If the rescaled demand cannot be built before the number freeze, invoke it then, keep the levels of the default cell (WorldPop 2020, anchors P10 and P90), and say that it was invoked after the counts were known. |
| Reason | (a) Guardrail GR8 knows two displays, and "unstable: verify" is the cautious one. (b) Entry 12 of the owner choices (decision R12) recommends its option because it "matches the plan's words and the way `bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells". With the two rules the missing re-runs need no new access run. (c) and (d) add no rule. |
| Risk | (a) A reader may take "unstable" for a measured finding; the note says it is not measured yet. (b) Protocol v1b does not name the script, so this is a reading recorded after 90 re-runs were seen; every output must say so. (d) After the cut all eight tambons are at or above 60% in both cases, whichever anchors are kept; invoking it now would look like picking the rule that passes. **Not offered:** taking retention over only the re-runs that can be made. That changes the signed rule and is **v2**. |
| After a yes | A decision-log row. The rescaled demand is built and tested on invented data, then the 90 missing public re-runs of each case are made (real tambons, reported). The headline rule is then evaluated as written, for a public overlay. |
| Who | Both |
| Reply | `A3 yes` (all four as recommended), or one by one: `A3a no class shown` |

### A4 (E1-OP2 first half, A4-OP5). Do you confirm the rights record for the two Sentinel-1 radar scenes?

| | |
|---|---|
| Question | The radar candidates of case O1 are made from two Sentinel-1 scenes (3 and 15 September 2024 UTC). No signed rights record covers them, so the code refuses every O1 candidate. The draft is `docs/proposal_execution/rights_basis_sentinel1_v1.json` with its notice file. It asks three things. **(1) A4-OP5:** the July acquisition manifest marks both archives "do not run baseline yet". Decision R14 read that note as a gate on the finals baseline only, for the replay and the 3 September file. Does the same reading hold for plan tasks A2 and A4 and for the 15 September file? **(2)** Five points to check on the Copernicus legal notice page (the draft lists them). **(3)** Scope: **A** the `local` level only, or **B** also a publication scope. |
| Why it matters | Without the record O1 can never be loaded. The radar tables and the diagnosis figures of 4 October were made from these two scenes before any signed record existed. |
| Options | (1) yes or no. (2) checked, with corrections if the page says something else. (3) A or B. B needs a new version of the record and a reviewed change to the rights code before it has any effect. |
| Recommended | **(1) yes. (2) check. (3) A now**, and B later if a radar layer is to be published. |
| Reason | (1) It is the same note on the same image pair that R14 already read this way; the note was written because the status of a reference mask was unresolved in July. (3) A needs nothing beyond registering the record. |
| Risk | The runs of 4 October were made and committed before this answer. A "no" to (1) means they were made without your permission, and that has to be written down. Under scope A the per-tambon radar tables already in Git sit above their level (see C1). |
| After a yes | Two reviewed changes: the record is marked confirmed, with a decision-log row, and then registered in the rights code. The loader then accepts a candidate. Still missing for an O1 score: the geocoding (A6), the delivery of the candidates to the flood-input step, and a builder that reads the radar skill measurements. Every O1 row would be low confidence and class E under rule v1, because the skill bar is recorded as not met at Mae Sai. |
| Who | Both (a rights record needs both names) |
| Reply | Needs more than a word: `A4 yes, scope A, notice checked on <date>` |

### A5 (E5-OP5, E10-OP3 first step). Do you accept one compute window for a walking build of record?

| | |
|---|---|
| Question | The shelter part of the planning work needs a road network built for walking. One exists, built on 4 October without a declared compute window, so it is a candidate only. Do you accept one window for one walking build of record, on the terms you accepted for the vehicle build in R13? |
| Why it matters | Until then the shelter tables may not feed the scores. A walking build of record is the first step for the shelter service, for 360 of the 540 re-runs of each case, and for a pitch-level result file. It is not needed for a public headline (A3). |
| Options | The draft `docs/proposal_execution/walking_build_compute_window_v1.md`, section 7: **A** accept in advance, **B** you name the window, **C** no walking build of record. |
| Recommended | **A**, keeping the condition that the build must reproduce the candidate: the same network fingerprint, 359 grade joins, 69,095 edges, and 81 of the 82 located shelters snapped. |
| Reason | The terms are those of R13. The candidate build took 2.38 minutes. The condition catches any drift, and any difference comes back to you. |
| Risk | About ten quiet minutes on the machine. Two small fixes come first (the builder's receipt must name both protocols; the access step must refuse a walking network whose receipt names no authority). The middle shelter set still has no access table, and half of the 360 re-runs also wait for A3. |
| After a yes | A decision-log row. The two fixes, tested on invented data. The one build, the four-line comparison, then commit and register, or stop and come back to you. The agent asks again before it reruns the access tables (about 20 minutes), E8 or E10. |
| Who | Both |
| Reply | `A5 A` |

### A6 (A4-OP1; A1-OP3 follows it). Which radar layers does case O1 use?

| | |
|---|---|
| Question | The plan's fallback geocoding was used for the radar run of record. It puts the radar layers about 680 m from where they belong. A second run gives every cell a terrain height and leaves about 10 m, but its method is not in the plan. Which layers does case O1 use? |
| Why it matters | Roads are narrow. With a shift of 680 m no road closure can be modelled from the radar layers; they are good for tambon totals only. One diagnosis figure follows the same choice (A1-OP3). |
| Options | **(1)** the run of record, totals only. **(2)** the height-aware sensitivity run. **(3)** a warp through the control points (not run). **(4)** SNAP terrain correction, the method the plan names first; SNAP is not installed, and installing it is a download only a person can make. |
| Recommended | **(2)**, named as what it is ("a terrain height per cell; not SNAP terrain correction"), with the run of record kept beside it as reported. Rachmania reviews both runs first: the result page says she has not yet reviewed them. |
| Reason | It is the only run on disk that is fit for use at road level. The skill-bar outcome is the same in both runs: the method declined the same six of nine tiles. |
| Risk | The choice is made after both results were seen (candidate areas 9.42 against 8.30 km², 114.50 against 116.36, 3.01 against 3.04) and has to be disclosed as such. Radar shadow and layover stay unflagged. If you would rather hold to the plan's named method, answer 4: O1 then waits for SNAP. |
| After a yes | A decision-log row. A superseding run (`--replace --reason`, reported) labels the chosen layers as the O1 input and corrects the label of the fallback run (A4-OP7, in C10). Nothing is delivered to the scoring chain before A4. |
| Who | Rachmania |
| Reply | `A6 2` (or `A6 1`, `A6 3`, `A6 4`) |

### A7 (decision R18; E8-OP6 first half). Have you read the first results, and may SE1 go to a page?

| | |
|---|---|
| Question | R18 says that no result of the planning assessment is shown on any page before the owners have read it. Have you read them, and may SE1 be shown once A1 to A3 are in place? |
| Where to read | `outputs/planning_v1/README.md`, sections "Plan task E8" and "Plan task E10". The per-tambon scores and classes are in two files outside Git that the receipts bind. |
| What they say, for the whole case | **SE1:** class B once, D three times, E four times; scenario confidence medium for all eight. The one class B is kept in 70 of the 90 re-runs that could be made; the README says to read it as "B or D, depending on 20 m and the closure level". Two of the four E results are D if the disclosed flood anchor is 0.10 in place of 0.20. **O2:** class E for all eight, in every re-run. That says the score is low on late-season residual water, not that a tambon was safe. |
| Options | (a) Allow SE1 on pages, labelled "scenario: 2024 season envelope" and "unstable: verify". (b) Allow it in the pitch only. (c) Hold. |
| Recommended | **(a)**, after one desk check: the README says the access figures of the tambon whose access gap and road criticality are both 100 should "be checked at a desk before anyone repeats it". Nothing is shown from the report file of the first run; a page reads the overlay only (E8-OP6). |
| Reason | Each run was computed again to the same bytes, and a reviewer's own script recomputed all eight rows of both cases with no difference. Every value is labelled as a scenario result. |
| Risk | One flood input drives four of the five components (90% of the weight). A scenario class is easily repeated as a fact about September 2024. The class B rests on modelled road closures, not on an observed closure. |
| After a yes | With A1, A2 (option A) and A3 the SE1 overlay is `public`. The planning columns of Command fill for SE1, and the public band (plan task E12) and the briefs can be built on it. O2 waits for C2. |
| Who | Both |
| Reply | `A7 yes`, after reading |

## B. The new Command page

Decision R18 approved the purpose ("exercise and after-action tool for rescue coordinators" on the Mae Sai 2024
case) and left the Thai text to the assistant. The page is built on branch `claude/command-exercise` at the
temporary address `/command/exercise/`; `/command/` is unchanged. Choices 2 to 6 of the plan
(`docs/command_exercise_plan.md` on that branch, section 12) are built as recommended and are provisional.
Putu gave the Command answers that R17 and R18 record, so Putu is named below; Rachmania is welcome on any of them.

### B1 (decision R18). Have you looked at the preview?

| | |
|---|---|
| Question | Have you looked at the new page's preview? R18 says `/command/` stays as it is until you have, and that PR #43 waits for you to look at its preview. |
| Why it matters | Every other answer in this group is easier with the page in front of you. |
| Options | Look and answer B2 to B10; look and list changes; not yet. |
| Recommended | Look at it on a laptop and on a tablet, in English and in Thai, then answer the rest of this group in one go. |
| Risk | None in looking. No native speaker has read the Thai text (R18); the page's information drawer says so. |
| After | The address change of B2. |
| Who | Putu |
| Reply | `B1 seen`, with any changes you want |

### B2 (plan choice 2). Addresses and the name of the header link

| | |
|---|---|
| Question | May the new page take the address `/command/`? The plan moves today's text page to `/command/planning/`, keeps `/command/archive/` and `/command/cases/` behind menu links, and names the header link "Command (exercise)" (Thai draft: ฝึกซ้อมสั่งการ). |
| Why it matters | Until the change, the landing page and the policy page link to the old page, and the new one has only its temporary address. |
| Options | Yes as planned; yes with another name; keep the temporary address for the pitch. |
| Recommended | **Yes as planned**, after B1. |
| Reason | One address for Command, and the old pages stay reachable. |
| Risk | The plan counts 17 script files and about 13 source files that name `/command/`, so the change needs its own checks. Command exists in the competition build only; the public-production build leaves the whole route out. |
| After a yes | The change is made as its own reviewed step: header, policy card, landing links and the offline list. |
| Who | Putu |
| Reply | `B2 yes` |

### B3 (plan choice 3; decision R17, part 1). The two rankings and the class form to keep

| | |
|---|---|
| Question | The table of the eight tambons shows two rankings side by side that are never merged. Left: this replay hour's count (residents who lost shelter access; ties by residents in modelled water). Right: the protocol's planning class, fixed in time, with one chip for the radar case O1 and one for the scenario SE1. R17 says both class forms are built for now, each labelled, and one is chosen later. Is the default order right, and which form stays? |
| Why it matters | It is the first thing a coordinator reads. |
| Options | Keep both chips; keep the scenario chip only; keep the observed chip only. |
| Recommended | **Keep both chips, each with its label. Default order: the left ranking. Planning position from SE1, labelled "scenario".** Do not choose one form until O1 has a result. |
| Reason | SE1 is the only case that can reach the public level soon (A1, A2). Two labelled chips say more than one. |
| Risk | A scenario class beside a replay of September can be read as "what happened". The chip says scenario and the table footer says "Fixed in time; not computed from this hour". Today both chips are dashes ("Not issued yet"). The O1 chip stays a dash until O1 can be scored, and will then read E. |
| After a yes | Nothing changes now. The SE1 chips fill once A1, A2, A3 and A7 are in place. |
| Who | Putu |
| Reply | `B3 yes` |

### B4 (plan choice 4). What the map shows as reports this week

| | |
|---|---|
| Question | Three kinds of report are built: 2024 place records from news; invented exercise calls tagged "EX"; and reports saved on this same device, shown as a count on the tambon. Nothing travels between devices, and the SOS practice mark is not built. Is that the right limit? |
| Why it matters | R17 asked the agent to try to show public reports and SOS on the map, and says the page must not read as a feed of incoming reports or calls. |
| Options | Confirm; add the SOS practice mark; remove the same-device reports. |
| Recommended | **Confirm, and leave the SOS practice mark unbuilt.** |
| Reason | A public report is stored only on the reporter's own device, and SOS only opens the phone's dialler (R17). Nothing more can honestly be shown. |
| Risk | A viewer may still think that reports reach responders. The plan has the page say that FloodGuard receives no calls and that 1784, 1669 and 191 remain the official routes. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `B4 yes` |

### B5 (plan choice 5). The invented exercise calls

| | |
|---|---|
| Question | 14 invented items are built: 2 with life at risk, 4 urgent, 8 for information, in English and Thai. Each id starts "EX-". None holds a real person's details, none copies a real 2024 plea, and none is counted with real records. Do you accept them? |
| Why it matters | They are the script of the exercise, and the only "calls" on the page. |
| Options | Accept; accept with edits; cut the number. |
| Recommended | **One of you reads all 14, then accept.** They are in `apps/web/public/exercises/mae-sai-2024/injects.v1.json` on the branch. |
| Reason | The plan asked for a set written by the team and read by a Thai speaker. R18 leaves the Thai to the assistant, so your reading is the only human check. |
| Risk | An invented call can still read like a real case. The parser refuses text shaped like a phone number, a house number or a person's title, and a test checks that no item shares a run of five words with a place record. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `B5 yes`, after reading |

### B6 (plan choice 6). The future is hidden by default

| | |
|---|---|
| Question | In "trainee mode", the default, a place record appears at its publication time and later hours are hatched. "Hindsight mode" is one switch away. The Studio replay keeps its own rule. Is trainee mode the right default? |
| Why it matters | A trainee should not see what was not known yet. |
| Options | Trainee by default; hindsight by default. |
| Recommended | **Trainee by default.** |
| Risk | Markers follow the clock on Command and do not on the Studio replay. The two pages differ by design, and a visitor may notice. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `B6 yes` |

### B7 (plan choice 7). A tag on the 2024 pleas that news outlets reprinted

| | |
|---|---|
| Question | About seven place records paraphrase a plea for help that news reprinted in 2024. The plan proposed a tag "plea reported in news", from a short reviewed list. The tag is not applied: the records appear as ordinary place records. Should it stay that way? |
| Why it matters | These records describe real people, without names. |
| Options | (a) No tag, as built. (b) Add the tag from a reviewed list of record ids. |
| Recommended | **(a) for the pitch.** |
| Reason | A tag singles out real pleas. It needs a list that someone has reviewed and Thai wording that nobody on the team can check. |
| Risk | Without a tag a trainee cannot tell a depth report from a plea. The records are never shown as calls received either way. |
| One thing to settle | The decision log (R18) records "not applied" as a build choice, not as your decision. The plan file on the branch lists it under "Owner decisions" as "not approved". Please say which is right, so that the two files agree. |
| Who | Putu |
| Reply | `B7 a` and one word on the record: `decided` or `build choice` |

### B8 (decision R17, point g; merge report item 11). The ranking that still stands on `/command/archive/`

| | |
|---|---|
| Question | You said yes to taking the GeoAI research report's score table off Command. The map workspace at `/command/archive/` still shows its own retained ranking: a research FPPS and a class for each of the eight subdistricts, from before the signed protocol. Its values differ from the report's. Should it leave the page too? |
| Why it matters | Once SE1 scores of the protocol reach Command, the same eight tambons would carry scores from different sources on Command pages. R17 says this question was not put to you. |
| Options | (a) It stays until Command is replaced, with its notice. (b) Take it off now and keep it only in Studio's archive, labelled as historical research, like the report's table. |
| Recommended | **(b), before any protocol score appears on Command.** |
| Reason | It is the reasoning of your yes on the report's table, applied to the second table. |
| Risk | The map workspace loses its ranking rail, its readout and its A to E legend, and the offline check that lists its eight retained values has to change with it. |
| After a yes | A reviewed change to the page and its checks. |
| Who | Putu |
| Reply | `B8 b` |

### B9 (decision R17, points a to f; merge report item 12). Limits of "saved when opened"

| | |
|---|---|
| Question | You approved that each study area of the evidence library is saved for offline use when someone opens it. Six limits were chosen while building. Do you confirm them? **(a)** The offline installation may not exceed 12 MB; above it the build fails. **(b)** An area larger than 20 MB is saved only with its button: Bang Ban and Sena (31.0 MB) and Rangsit (51.3 MB). **(c)** Nothing is saved on open when the browser asks sites to use less data, and a copy the reader removed is not saved again until the reader asks. **(d)** A file is stored only when its SHA-256 matches; a saved area survives a new deployment and can be removed. **(e)** The database archives offered for download (188.8 MB) are never part of a saved copy. **(f)** The historical report's page is not in the installation, so it needs a connection. |
| Why it matters | The installation is 10.5 MB in place of 301 MB. The limits decide what works without a connection at a venue. |
| Options | Confirm all six; change a number; save the two large areas on open as well. |
| Recommended | **Confirm all six.** |
| Reason | They keep the first install small and never use a reader's data plan unasked. |
| Risk | Rangsit and Bang Ban and Sena are not available offline unless someone uses their button while connected. For an offline demo that step has to be on the checklist. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `B9 yes` |

### B10 (build notes of the plan on the branch). Ten small choices made while building the page

| | |
|---|---|
| Question | The build notes list choices the plan did not make. Do you accept them? (1) Urgency has two steps: life at risk for people on a roof, or water at chest height or above with people present; urgent for an infant or a bedridden person, or no food for a day; information otherwise. (2) In trainee mode a shelter counts from the start of the day it is first reported. (3) The clock card states a model limit at every hour ("the current is not modelled"). (4) Roads that are passable again are not named while the river falls. (5) The table footer is short; the full sentence is one tap away. (6) At district zoom a shelter star is a 28 px target, where every other control has 44 px. (7) A device starts with five example callsigns that name no real unit. (8) A closed item can be reopened. (9) In trainee mode a shelter's occupancy counts are held back. (10) A report saved on this device has no Assign and no brief. |
| Why it matters | They shape what a trainee sees and does. None computes a score or a class. |
| Options | Accept all; list the ones to change. |
| Recommended | **Accept all, after B1.** |
| Risk | (1) is a rule about invented items only, but a trainee may carry it into real work. (6) is a small target on a tablet. |
| After a yes | Nothing changes. |
| Who | Putu |
| Reply | `B10 yes` |

## C. Reading rules the protocols leave open

Each item groups points that one answer can settle. "Keep" means: confirm what the code did, as your reading of a
point on which the signed files are silent. It is recorded in the decision log and named in the outputs. It does not
edit a signed file. If you want a reading written into the protocol text itself, that is v2.

### C1. What does `local` keep out of the repository?

| | |
|---|---|
| Question | A result is `local` when one of its inputs is not cleared for publication. The signed rule (guardrail GR6) says only that such a result may not be written under the public website folder. It does not say whether its numbers may be in Git. What do you want `local` to mean? |
| Why it matters | Today layers and per-tambon tables below `public` stay outside Git, while the committed receipts and the README hold figures for a whole case. The README itself calls this separation "nominal": the SE1 score and class of each tambon can be worked out from committed files, and a count such as "E for all eight" states the class of each tambon. |
| Options | (a) `local` keeps things out of the public website folder only; figures may be committed with credit and licence. (b) `local` means not in Git: the figures leave the receipts and the README, and stay in the Git history. (c) Today's middle way stays, with its note. |
| Recommended | **(c), and fix the cause input by input:** A2 for the age data, C2 for the layer of 22 October, A4 for Sentinel-1. Leave what is committed where it is. Commit no new per-tambon file below `public`. |
| Reason | GR6's words stop at the website folder, so (c) adds no rule. Taking a figure out of a file does not take it out of the history, and the history must keep the signing commits (R16). After A2 (option A) and C2 the SE1 and O2 results are `public`, and the question is gone for them. |
| Risk | If anyone outside the team can read the repository, figures of layers still marked `local` can be read until A2, A4 and C2 are answered. The product 4009 and radar figures carry their credit and licence; the age table in Git has no licence line of its own yet, as the age review says. Putu knows whether the repository is public; if it is, answer A2 and C2 first. |
| After a yes | A decision-log row. The sentences of the README that say "undecided" are reworded at the next run. Nothing is moved. |
| Who | Both |
| Reply | `C1 yes` (or `C1 a`, `C1 b`) |

| Point | What it asks | Under the recommended answer |
|---|---|---|
| E1-OP1 (second half) | May a figure derived from a `local` layer be committed? The receipts of E1 and E5 hold whole-frame figures of the layer of 22 October and of the analysis extent. | They stay. |
| E8-OP7 | The README quotes four components per tambon for SE1 from a `local` file, because their own inputs are public. | The table stays, with its note. |
| E10-OP10 | The class counts of each re-run state the class of single tambons. | They stay, with the note. |
| E10-OP8 | The SE1 access tables of the smaller and larger flood levels have public inputs of their own and are outside Git. | Commit them after A2 (option A); until then they stay outside. |
| E5-OP8 (second half) | The first SE1 access table, which held ratios, is in the Git history. | The note in the receipt that replaced it is enough. |
| A1-OP5 | Whole-area radar statistics were committed with the Copernicus credit before any signed record. | They stay; A4 covers the use from then on. |
| E8-OP5 (part) | Do open-licence inputs with no rights record (WorldPop 2020, boundaries, WorldCover, the road context) need a registry entry? | Not now: the code treats them as `public` and writes their credit. Short entries follow after the pitch (D-18). |

### C2. One new version of the rights record for product 4009

| | |
|---|---|
| Question | The confirmed rights record for UNOSAT/GISTDA product 4009 names one layer: the accumulated layer of August to October 2024, the season envelope. The code also reads two more layers of the same product: the layer of 22 October 2024 (case O2) and the "analysis extent" (the outline of the area the product looked at). Both are held at `local`. Should a new version of the record name them? |
| Why it matters | While they are `local`, no O2 result can be shown outside the team, not even in the pitch, and the O2 tables stay outside Git. |
| Options | (a) The agent drafts version 2 of the record for both of you to confirm, as you confirmed version 1 (R6). (b) Leave it: O2 stays team-only. |
| Recommended | **(a).** |
| Reason | Decision D2 and UNOSAT's reply (R4) concern the product. Decision D3 makes the layer of 22 October its own observed case. The plan expects one record for both flood layers. |
| Risk | R6 allows publication "as a season envelope only". Version 2 widens that, so it is a new decision of yours, not a reading. The layer of 22 October is late-season residual water and must never be shown as the September flood. UNOSAT's reply names no licence version (R4). |
| After a yes | The agent drafts the record and its notice, pending, with a test that holds it pending. You read and confirm it. A reviewed change registers it. E1 is run again so that each layer carries its new level (the geometry does not change), then E5, E8 and E10 for O2. |
| Who | Both |
| Reply | `C2 yes` (it means "draft it"; confirming the record is a second step) |

| Point | What it asks | In version 2 of the record |
|---|---|---|
| E1-OP1 (first half) | Does the record cover the layer of 22 October and the analysis extent? | Both are named, each with its use. |
| E1-OP10 | The footprint layer the code reads (`CHIANGRAI_20240801_20241022_AnalysisExtent`) is named by no signed file. | It is named. |
| E1-OP8 | The change-notice template is written for a raster; the vector layers word their own notice. | A template for vector layers is added. |
| A1-OP6 | A diagnosis comparison is not among the listed uses. | "Comparison layer, labelled 'vs a season envelope, not an event map'" is added. It is never a reference. |
| E1-OP9 | The plan would let an unconfirmed record be used at `local`; the registry refuses any use. | No change: keep refusing. Nothing is refused today. |

### C3. The critical-link ranking stays as recorded

| | |
|---|---|
| Question | A critical link is a piece of road that many residents' routes depend on. The ranking of all links was computed on 4 October, and its SHA-256 was recorded "before any scoring", as protocol v1b asks. Three open points could change that table. Do you keep it as recorded? |
| Why it matters | Trigger B of the secondary class reads the 20 highest-ranked links. Scores have been computed since the ranking was recorded. |
| Options | (a) Keep the recorded table. (b) Another reading of E6-OP1 or E6-OP5, which gives another table: **v2**. |
| Recommended | **(a).** |
| Reason | The table was fixed before scoring so that no result could shape it. None of the 20 highest-ranked links is a connector, and none of the 200 highest-ranked is a graph bridge. |
| Risk | Under (a) trigger B cannot fire at Mae Sai, by the README's own reasoning: closing one link that is not a graph bridge cuts nobody off. If you meant graph bridges to enter the 20 so that B can fire, that is a rule change after results. The 20 links (20 consecutive pieces of one street) stay "unreviewed candidates" until Rachmania's desk check. |
| After a yes | A decision-log row. Trigger B can then be computed from the recorded table (C4). |
| Who | Rachmania (the plan gives her the review of critical links), with Putu |
| Reply | `C3 yes` |

| Point | What it asks | Keep |
|---|---|---|
| E6-OP1 | May a grade-join connector (a zero-length joint the builder adds between road ends that coincide, decision D13) be a critical link? | It is ranked like any road piece. |
| E6-OP5 | "Add graph bridges": added to what? A graph bridge is a road piece whose removal cuts the network in two. | Nothing is added. A bridge is flagged and ranked by its flow. |
| E6-OP6 | May a later run change the recorded ranking? | No. Another ranking is v2. |
| E6-OP2 | What does the full reroute of the 200 highest-ranked links write? | Nothing was run. Decide when scenario S3 is built (D-3). |
| E6-OP3 | Is the bridge flag the graph bridge or the map tag `bridge=yes`? | Both are written. |
| E6-OP4 | The tambon of a link whose midpoint lies in no tambon or in two. | The midpoint rule; no such link occurred. |
| E6-OP7 | A zero-minute road piece between two destinations. | The route goes on to the destination with the smaller ID. 40 such nodes, no resident on them. |

### C4. The three untested triggers of the secondary class

| | |
|---|---|
| Question | After A1, what is done about triggers B, C and D? |
| Why it matters | It decides how much of the secondary class is filled by the pitch. |
| Options | For each trigger: build it now, wait, or leave it out. |
| Recommended | **B: compute it now from the recorded ranking. C: leave "not evaluated" and define it in v2. D: approve download DL-2, then compute it.** |
| Reason | B needs only C3. D is fully defined in protocol v1b and lacks one data tile. C lacks a definition, and the SE1 results are known, so a definition written now would be written with the outcome in view. |
| Risk | The four SE1 rows that are "not evaluated" stay so until C exists, unless B fires, which C3 says it cannot at Mae Sai: the order is E, A, B, C, D, and D cannot decide a row while C is unknown. So B and D complete the record more than the picture. |
| After a yes | Trigger B is computed (a small run on real tambons, reported). A person downloads the JRC surface-water tile for the east of the frame (about 70 to 100 MB, from the JRC Global Surface Water download page), then D is computed. C waits. |
| Who | Both |
| Reply | `C4 yes` |

| Point | What it asks | Under the recommended answer |
|---|---|---|
| E8-OP1 (second part) | Build the inputs of B, C and D. | B now; D after DL-2; C in v2. |
| E8-OP8 | Trigger C names a hospital or a shelter. The shelter list is pitch level. Does a public overlay test C on hospitals alone? | Not answered here: it belongs to the definition of C in v2, with the question of when a facility "loses all vehicle routes". |
| DL-2 | The JRC tile `occurrence_100E_30Nv1_4_2021.tif` is not on disk. Protocol v1b lists the download as needing an owner's approval. | Approve. It also serves the JRC sensitivity note on permanent water (decision D4). |
| E11-12 | The overlay holds only part of the inputs of triggers A, C and D, so the parsers can check them one way only. | Accept for format 1.1; carry the evidence when the triggers are built. |
| E11-13 | The secondary class has trigger evidence and no reason code of its own. | Keep: v1a says no new reason code is added for v2. |

### C5. Flood inputs and access tables: keep what the code did

Why it matters: these readings sit under every access figure. Reason: each was made before or while the first scores
were computed, and follows the nearest signed rule. Risk: E5-OP4 keeps some residents "with access" whom another
reading would count as lost, and E5-OP3 means that the access figures say nothing about 8.1% of residents. Both have
to be named wherever an access gap is shown. Changing either now is **v2**. After a yes: a decision-log row; no run.
Who: Putu for access, Rachmania for flood inputs. Reply: `C5 yes`.

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
| E5-OP8 (first half) | Should the access step also write each service's "newly lost" share? | No. The tables hold counts only; shares come with the components in E8. |

### C6. The age table: keep the signed reading

Why it matters: the age table feeds the vulnerability component. Reason: the national anchors in the signed
protocol were computed the same way. Risk: for TH570901 the border cells move the share by 0.0149, where the two
anchors are 0.1263 apart; that has to be said beside the component. After a yes: a decision-log row; no run.
Who: Putu. Reply: `C6 yes`.

| Point | What it asks | Keep | Anything else |
|---|---|---|---|
| E7-OP1 | 31 one-kilometre cells lie partly across the national border. Their age mix may include people whose homes are on the other side. | Reading DR-B04 as written: the tambon takes the cell's counts by its share of the cell's area. | Another treatment changes the method behind the signed anchors: **v2**. |
| E7-OP2 | Should a low-to-high range of the share enter the component? | No. The table shows three allocations for information only. | A range in the component is a new rule: **v2**. |
| E7-OP3 | Is a tambon's share rounded before it enters the component? | No. E8 computes the component from the three age counts. | |

### C7. The planning assessment: keep what the code did

Why it matters: these readings decide how one row of the overlay is formed. Reason: no reading changed a class in
the runs of 4 October. Risk: E8-OP3 would matter in a frame where a tambon has few connected residents; every Mae Sai
tambon passed both conditions by a wide margin. After a yes: a decision-log row; no run. Who: Putu. Reply: `C7 yes`.

| Point | What it asks | Keep |
|---|---|---|
| E8-OP2 | Which closure level does a tambon's row use? | The default cell of v1b: the flood layer as provided and the central closure level. |
| E8-OP3 | How are confidence conditions C7 and C8 measured for one tambon? | C7 on the hospital service; a tambon where nobody is connected would fail it. C8: a hospital counts when it is in the same connected part of the road network as a populated cell of the tambon, with no time limit. Every tambon passed both by a wide margin. |
| E8-OP4 | The flood layer has a date and no time of day; the format wants an instant. | The last date of the source period at 00:00:00 UTC, said in the file. |
| E8-OP6 (second half) | Should rows that fail a check be reported? | No. The receipt gives the stage and a code, and no row. |
| E8-OP9 | What does a row get when a component cannot be computed, or the tambon has under 100 residents? | No score and no leave-one-out for the first. For the second the score is kept, with no leave-one-out class. Neither occurred. |
| E8 choices | Six choices listed in `docs/planning_assessment.md`: the scenario wording is v1a's lane definition; condition C1 of a scenario is judged on the agency product it is built on; two rounding tolerances; lower-case identifiers; public overlays under `outputs/planning_v1/overlays/`; no engine row and no locked row is added. | All six. |

### C8. The ensemble: keep what the code did

Why it matters: these readings decide what each re-run reports. Reason: each is the plainest reading of a short
phrase in protocol v1b. Risk: none changed a class; a later reader may expect a single "axis with the largest
swing" and find none named. After a yes: a decision-log row; no run. Who: Putu. Reply: `C8 yes`.

| Point | What it asks | Keep |
|---|---|---|
| E10-OP4 | Each re-run reads a confidence class. Which one? | The tambon's own, derived as in E8. Recommended for later: it does not follow the population year either, because v1a says confidence uses no ensemble output. |
| E10-OP5 | "Best and worst rank": ranked by what? | By FPPS among the eight tambons, highest first; a tie goes to the lower code. |
| E10-OP6 | "The axis with the largest swing" is not defined. | The FPPS range along each axis is reported, and no axis is named. |
| E10-OP7 | "People losing 30-minute access": to which service? | Both public services are reported. |
| E10-OP9 | "One at a time": varied from which re-run? | From the default cell alone. |

### C9. The result file format: keep what was built

Why it matters: both parsers refuse a file that departs from these choices. Reason: each is a choice of shape, not
of a number. Risk: E11-22 is the one change: today the gate would let the invented-unit fixture be written under the
public website folder, and an invented unit on a public page can be taken for a place. After a yes: a decision-log
row, and one small reviewed change for E11-22. Who: Putu (the plan gives the review of contracts to Callixta).
Reply: `C9 yes`.

| Point (number on the overlay page) | What it asks | Keep |
|---|---|---|
| E11-1 | May a file hold a row for the locked tier T4? | Yes, as a placeholder with no value. |
| E11-2 | Engine (synthetic test) rows: a secondary class, a "high" confidence? | No secondary class; "high" is refused everywhere. |
| E11-3, E11-5 | A row with a missing component; a tambon under 100 residents. | As E8-OP9 in C7. |
| E11-6 | Must the residents of the age record equal the residents the row is scored on? | Not required: the two come from different years. |
| E11-7, E11-8 | The date relation of a row. | Empty for a row with no flood input; "dated_other" and "season_window" are derived from the dates. |
| E11-9 | The date of the layer of 22 October. | 2024-10-22, v1a's reference date for that case. |
| E11-10 | Which rows does a case file carry? | The case's own rows. Scenario cells, engine rows and the T4 placeholder are not compared with the case. |
| E11-14 | One confidence class for the whole file? | No. Confidence is per tambon and case. |
| E11-16, E11-17 | The list of input roles; the guard "a public flood input declares its source product". | Both. The guard was added in review and is not a protocol rule. |
| E11-18 | One row per tambon, lane, flood input and scenario. | Yes. The 540 re-runs are not rows. |
| E11-19 | Columns of the summary. | Observed, scenario and engine, never a total across them. |
| E11-22 | May the invented-unit fixture be written under the public website folder? | **Change: never.** |
| E11-23 | Instants are checked by pattern only. | Yes. |
| E11-24 | The file names differ from plan 7.1. | The built names. |

### C10. Radar readings

Why it matters: these decide what the radar candidates are and how they enter case O1. Reason: the radar method was
frozen before any Mae Sai run, and its result is known; nothing is tuned afterwards. Risk: two answers hold the run
to less than a sentence of protocol v1a promises (A4-OP2) or decline a pass that one reading would give (A4-OP3);
both have to be stated with the result. After a yes: a decision-log row; the label fix at the next superseding run.
Who: Rachmania. Reply: `C10 yes`.

| Point | What it asks | Recommended |
|---|---|---|
| A4-OP2 | Protocol v1a says a terrain mask (height above the nearest stream, and slope) "is applied on Mae Sai" for the frozen method, and gives no source and no limit. | No mask was applied. Keep, and say plainly that the run departs from that sentence. Limits chosen now, after the result, are a new rule: **v2**. |
| A4-OP3 | The skill bar: does "coverage" mean valid radar input or cells with an answer, and is "no answer" judged per tambon or for the frame? | The outcome of record stays "not met" for the frame, and no pass is of record for one tambon. A single-tambon pass, chosen after seeing that one tambon passes, is **v2**. |
| A4-OP4 | Who removes permanent water: the candidate raster or the flood-input step? | The rasters stay as the frozen method returns them; areas are given both ways. |
| A4-OP6 | How is the frame cut into tiles for the frozen method? | The GEOID tile lattice in UTM zone 47N. No other was tried, and none is tried now. |
| A4-OP7 | The label of the layers says "GCP affine". What ran is a second-order polynomial. | Reword the label at the next superseding run. No rerun as a true affine fit. |
| A4-OP9 | The +1 dB level of M1-literal is cut at 0 dB by the second clause of its rule. | Keep the clause. The rule is unchanged. |
| A2-OP1 | The steps of the UN-SPIDER practice were written without a copy of its script, and two layers were replaced by layers on disk. | Rachmania checks the steps against the published script. The replacements stay, as disclosed. |
| A2-OP2, E1-OP5 | The smaller and larger "one pixel" levels of a raster candidate: made how, and by whom? | By the flood-input step: the cells become polygons and get the same 20 m buffer as a vector product (owner choice 2: 20 m for every input). |
| E1-OP6 | "Polygons under 5 pixels are dropped": do two pixels that touch only at a corner form one polygon? | No: the four-neighbour rule, which the loader already uses when it turns cells into polygons. No closure extent of O1 has been built, so no result is in view. |
| E1-OP11 | Should a candidate's receipt carry its three thresholds as numbers, so that the loader can check them? | Yes. |

### C11. The diagnosis figures: several readings, none "of record"

| | |
|---|---|
| Question | The diagnosis ("Why threshold-only change detection failed at the 16 Sep pass") gives some figures under several readings, because the plan names none. May it stay that way? |
| Why it matters | A slide wants one number. The plan's own 0.421 is the value of one smoothing window among six (0.467 with no smoothing, 0.299 with the widest). |
| Options | Keep every reading and name none; or name one of each as the figure of record. |
| Recommended | **Keep every reading and name none.** A slide quotes the range with the label "vs a season envelope, not an event map". After A6 the darkening figure is quoted first under the chosen geocoding. |
| Reason | Naming one now means choosing with every value in view. |
| Risk | A range is harder to say in a pitch. The terrain features repeat an exploratory script whose values had been seen before, which the result page discloses. |
| After a yes | A decision-log row; no run. |
| Who | Rachmania |
| Reply | `C11 yes` |

| Point | What is left open | What is given |
|---|---|---|
| A1-OP1 | The plan names no terrain feature. | Low elevation and low slope. The height above the nearest stream was not computed. |
| A1-OP2 | The plan gives 0.421 and no definition. | The definition rebuilt from cleared files, with six smoothing windows. |
| A1-OP3 | Which geocoding (follows A6). | Both. |
| A1-OP4 | Which permanent water a diagnosis leaves out. | Three readings; they differ in the third decimal at most. |
| A1-OP10 | On which cells a rank statistic is taken. | All cells, and cells with a slope under 5 degrees. |

### C12. The guard for the two flood products the team has no grant for

Guardrail GR9 of protocol v1a names the two products. It asks for a test before each commit that fails when a
script reads either of them without a recorded grant, and for none of their numbers in code or on a public page.
The guard is built as a test of the suite and as a command.

Why it matters: it is the team's proof that no figure of those products is used. Reason: the guard does what GR9
can be made to check; the one gap to the signed words is the missing hook. Risk: the guard does not see a path read
from a manifest, a name split across strings, or new code inside an old function. The signed v1a still says
"not_built" for GR9, because the file cannot be edited. After a yes: a decision-log row; each person installs the
hook. Who: Putu, and each person for the hook. Reply: `C12 yes`.

| Point | What it asks | Recommended |
|---|---|---|
| A1-OP7 | What is a "grant receipt", and where is it recorded? | The guard reads the rights registry. No grant exists. Older code is listed in a baseline, which is not a grant. Keep. |
| A1-OP8 | How far can "no number" be checked? | In the files of the diagnosis task. Older committed files that name a product as a blocked record were not changed. Keep. |
| A1-OP9 | The plan says the scripts "moved". New ones were written, and four older scripts stay where documents and tests name them. | Keep. |
| A1-OP11 | GR9 says "pre-commit". No Git hook is installed. | Install the hook on each machine that commits (a local setting only a person can change). Until then, say "runs in the test suite and as a command, not before each commit". |

### C13. Where runs made after the signing are registered

| | |
|---|---|
| Question | Protocol v1b says every run is reported. It was signed on 3 October and cannot list a later run, and it does not say where one is registered. Today each later run writes a receipt into `outputs/planning_v1/`, and the receipt is registered by path and SHA-256 in a test list and in `run_register/`. Is that the rule for all later runs? |
| Why it matters | The README says this practice holds only "until the owners agree one rule". |
| Options | Confirm; or name another place. |
| Recommended | **Confirm.** |
| Reason | A file that is neither listed in v1b nor registered already fails the tests, and so does a registered receipt whose bytes change. |
| Risk | The register is a test file, so adding a run means editing a test. That is deliberate: the change is visible in review. |
| After a yes | A decision-log row; the README sentence is reworded at the next run. |
| Who | Putu |
| Reply | `C13 yes` |

### C14 (A4-OP8). A check to allow: are the replay's radar images in the right place?

| | |
|---|---|
| Question | The Mae Sai replay shows Sentinel-1 images made with the same warp as the radar run of record, which is displaced by about 680 m. The replay's layers were never measured. May the agent measure them? |
| Why it matters | The replay is in production and is the demo. If its radar images are displaced, a viewer who compares image and map is misled. |
| Options | (a) The agent measures them against mapped permanent water, reading only, and reports. Nothing is baked or changed. (b) Leave it. |
| Recommended | **(a), this week.** If the layers are displaced, you choose between a caveat on the page and a new bake. |
| Reason | The measurement is cheap, and the answer is not known. |
| Risk | A new bake changes `docs/demo/replay_numbers.md`, and one diagnosis figure then has to be run again. |
| After a yes | One read-only measurement with a short report. No file of the replay changes. |
| Who | Putu |
| Reply | `C14 yes` |

## Where the answer is a new protocol version (v2)

None of these is recommended now. Each is listed so that nobody answers it by accident. Each would need
`planning_protocol_v2`, with a written reason and the outputs it affects, and every earlier run stays reported.

| Change | Where it comes up |
|---|---|
| Taking retention over only the re-runs that can be made | A3 |
| Taking the vulnerability component out of the score | A2, option C |
| Another critical-link ranking, or graph bridges among the 20 | C3 |
| A definition of when a facility "loses all vehicle routes" (trigger C), and trigger C on hospitals alone | C4 |
| Counting a destination inside the flood extent as lost, or adding the unconnected residents to the access counts | C5 |
| A range in the vulnerability component, or another treatment of border cells | C6 |
| A terrain mask with limits for the frozen radar method | C10 |
| A pass of the radar skill bar for one tambon alone | C10 |

## D. Can wait until after the pitch

None of these blocks a score, a page or the Command week. `D yes` accepts every recommendation in both tables. The
items are written with a hyphen (D-1 to D-21), so that nobody takes one for a decision D1 to D16 of the decision log.

| Id | Question | Recommended | Why it can wait | Who |
|---|---|---|---|---|
| D-1 (E1-OP2, second half) | Does a candidate of the supervised radar classifier need a rights record for its training data? | Yes; draft it when the classifier is taken up. | R16 defers the classifier. | Both |
| D-2 (E1-OP7) | Is the three-day date rule counted in Thailand time or in UTC? | Leave open. The first case within a day of the edge stops and asks. | No case is near the edge. | Rachmania |
| D-3 (E6-OP2) | What does the full reroute of the 200 highest-ranked links write? | Decide when scenario S3 is built. | Nothing was run. | Rachmania |
| D-4 (E11-4) | Case SE2-dist has two components and no class, and fits no row of the overlay. A new kind of row, or another file? | Decide with SE2. | R16 defers SE2. | Putu |
| D-5 (E11-15) | The blocks of plan 7.1 that the format does not carry (equity, shelter supply, travel minutes, more ensemble outputs). | Add them in a later format version, with plan tasks E9 and E12. | Their modules are not built. | Putu |
| D-6 (E11-20, E11-21) | Where may a would-be class be shown, and what does the skill caption beside a radar would-be class say? | Studio's verification queue only, as v1a says, until O1 has rows. | O1 has no row. | Both |
| D-7 (E10-OP3, rest) | After the walking build: build the access table of the middle shelter set, or invoke declared cut line 8, which drops that set? | Decide after A5. | Not needed for a public headline. | Both |
| D-8 (plan choice 8, second half) | Reports that travel between devices need a deployed service, consent wording, a retention period (the plan proposes 72 hours), a named data controller and an agreement with an agency. | Nothing before the pitch. Name the data controller before any such work. | The plan puts it after stage A. | Both |
| D-9 (merge report 3) | The address of the candidate report, and whether the study library lists the scoring pages. | Keep `/studio/candidate-report/`; add the library links after the pitch. | No page is broken. | Putu |
| D-10 (merge report 4) | Should the replay follow equity 2.0? | Not before the pitch. | The replay's equity rule (R8, option B) is built and in production; a change needs a new parity fixture and new wording. | Both |
| D-11 (merge report 5) | The scoring line's landing page is not served. Keep it, or remove it with its assets and the seven packages only it uses? | Remove after the pitch. | Nothing serves it. | Putu |
| D-12 (merge report 6) | The site moved to Next 16.3.5 and the tests to Vitest 4.1.11; all checks pass. | Confirm. | Already in use. | Putu |
| D-13 (merge report 7) | The referrer header is `strict-origin-when-cross-origin`; the stricter `no-referrer` would also work. | The stricter one, after the pitch, with a preview check. | A header change before a demo is a risk for no gain on the day. | Putu |
| D-14 (merge report 9, 14, 15) | Duplicate files of the two lines, stale addresses in older documents, and three overlaps of a few pixels on the Public page map. | Clean up after the pitch. | None breaks a page. | Putu |
| D-15 (merge report 13) | The "Studio" link in the eight case briefs opens the study library and ignores the case. A fix rebuilds the briefs and changes their pinned SHA-256 values. | Fix after the pitch, to `/studio/candidate-report/`. | The briefs are pinned for the release. | Putu |
| D-16 (DL-1, DL-3, DL-4) | Three downloads that protocol v1b lists as needing approval: a JRC tile and a terrain tile for SE2, and the Sentinel-1 pass of 18 September 2024 (about 1.3 GB; decision D12). | None now. | SE2 is deferred (R16), and the UN-SPIDER reproduction ran on the pair on disk. | Both |
| D-17 (follows A6) | Install SNAP for a terrain-corrected radar run that supersedes the chosen one. | After the pitch, if A6 is answered 2. | The skill-bar outcome is the same in both runs on disk. | Rachmania |
| D-18 (E8-OP5, part) | Short registry entries for the open-licence inputs. | After the pitch. | The code already writes their credit. | Both |
| D-19 (decision log, last section) | The log says Rachmania has not signed it directly, and its section "Rachmania's confirmation" is empty. R11 to R15 were given by Putu for both owners. | Add one dated line. It costs a minute and can be done any day. | Optional in the log's own words. | Rachmania |
| D-20 (lane report) | About 440 MB of rasters of the first radar runs lie beside the current ones, outside Git. | Keep them until after the pitch. | Disk space only. | Rachmania |
| D-21 | The replay follow-ups of the decision log (next table). | As in the table. | The replay is in production and none of these blocks it. | see table |

**D-21, the replay follow-ups still open in the decision log.** The number is the follow-up's number in
`docs/decision-log-d1-d16.md`. Two rows have a date before the pitch: FU5 and FU8a. The Thai language check
(roadmap item H12) is not asked again: R18 says it stays unsigned for the hackathon.

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
| FU13a | Which exposure rule does SE1 use, so that the replay page leads with the same count? | Protocol v1a already states it: residents whose population cell has its centre inside the extent. The page leads with that count, as built, and gives the replay's own count beside it, which also settles point b of follow-up 12. The cross-check waits for the overlay (A1). | Rachmania |
| FU13b, FU13c | The longer caption under the map (92 to 128 px on a wide screen), and the wording of the export credit with its change note. | Keep the caption; read and approve the credit. | Putu |
| FU13d | The "other inputs" section of the licence notice (a caution, not legal advice). | Rachmania reads it. | Rachmania |
| FU13e | Should an unused sentence of the Python equity module also name the denominator? It would then differ from the unchanged module. | Leave it: the sentence is on no page. | Both |
| FU12f, FU13f | The hatch of the envelope layer, a hatch drawn at screen resolution at street zoom, and the review of the export pack (follow-up 8). | Callixta's design review, after the pitch. | Callixta |
| FU13h | A tool that reads the envelope check must read the key `compared_with`. | No decision: a note for whoever writes such a tool. | nobody |

## Things only a person can do

These are actions, not questions. Logins, emails, downloads and installs are done by people; the agent only drafts.
Dates are those of restructuring plan v2 (sections 8 and 9).

| # | What | Who | Plan date | If it does not happen |
|---|---|---|---|---|
| P1 | Look at the Command preview and at PR #43 (B1). | Putu | this week | `/command/` stays the old page. |
| P2 | Check three licence points on WorldPop's product page (A2) and five on the Copernicus legal notice (A4). | Both | with A2 and A4 | Both drafts stay pending. |
| P3 | Read the first SE1 results (A7). | Both | before any page shows them | R18: nothing is shown. |
| P4 | When the unified branch is merged: "Create a merge commit". Never squash and never rebase (merge report item 1; R10, R16). | Putu | at the merge | The signing commits leave the history and the protocol tests fail on master. |
| P5 | Desk check of the 20 highest-ranked critical links (plan task V1). | Rachmania | Thu 15 Oct | They are shown as "unreviewed candidates". |
| P6 | Review the radar run and the steps of the UN-SPIDER reproduction (A6, C10). | Rachmania | before O1 is used | The result page keeps saying that the run is not yet reviewed. |
| P7 | Outreach: a flood product from GISTDA dated to the event (with its Repeated Flood Areas), the AIT/JAXA permission, the UNOSAT 3991 vector. Log any reply as `docs/provider_response_logging_guide.md` says. File UNOSAT's original "we approve the use" message (R4; follow-ups 1 and 4). | Rachmania; Putu for the UNOSAT message | Sat 10 Oct, the plan's cut-off | The plan's fallbacks: the observed lane stays as it is, trigger D uses JRC, no AIT processing, 3991 is cited as context only. |
| P8 | Ask the organisers: the length of pitch and questions, whether the website may be shown running, the date of Mentoring II. | Callixta, in the plan | was due Fri 2 Oct | A 10-minute and a 5-minute version; the offline ZIP by default. |
| P9 | The list of documented 2024 impacts for the Level-5 check (plan task V4). The plan wanted it fixed before scoring. No such list is in the repository, and scores exist since 4 October. | Rachmania | before the pitch | Either write it now and say that scores already existed and whether its author had seen them, or mark the check "not conducted". Recommended: write it, with that sentence. |
| P10 | A practitioner review of about 30 minutes with a logged form (plan task V5). | Rachmania's network or the mentors | Sat 24 Oct | "Not conducted" on the Level-5 row. |
| P11 | A second laptop for a rerun from a clean clone (plan task R2b). | Callixta or Rachmania | Mon 26 Oct | "Second-machine reproduction not run" in the claims. |
| P12 | Install the `requests` package locally (`uv sync --all-extras`), so that two tests run outside CI (merge report item 10). | Whoever runs the suite | any day | Two known failures stay. |
| P13 | Look at the site size on the first preview deployment: the evidence library is 278 MB and the studies are 119 MB (merge report item 8). | Putu | at the first preview | Unknown until someone looks. |
| P14 | Download the JRC tile of DL-2, if C4 is a yes. | A person | after C4 | Trigger D is not computed. |

Dates of the plan that both of you hold: Wed 14 Oct, the Mae Sai completion check (V2); Sun 18 Oct, feature
freeze; Fri 23 Oct, number freeze; Tue 27 Oct, the single release; Sat 31 Oct, the pitch.

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

- **Sources.** In the repository, on branch `claude/owner-unblockers` at commit `d587afd`:
  `outputs/planning_v1/README.md`; `docs/planning_assessment.md`; `docs/planning_assessment_overlay.md`;
  `docs/unified_lineage_merge_report.md`, section 8; `docs/decision-log-d1-d16.md` through R18;
  `docs/proposal_execution/automated_track/MAE_SAI_RADAR_CANDIDATES_RESULT.md` and `WHY_THRESHOLD_ONLY_FAILED.md`;
  the three drafts named in group A; the two signed protocol files, read only. On branch `claude/command-exercise`
  at commit `7453751`: `docs/command_exercise_plan.md`. Not in the repository: restructuring plan v2 (sections 8
  and 9) and the reports of the engine and radar lanes of 4 and 5 October 2026.
- **Source timestamp.** The state of those files on 5 October 2026. The runs they describe were made on 3 and
  4 October 2026 (UTC). The flood layers are of 2024: the season envelope of August to October, the layer of
  22 October, and the Sentinel-1 pass of 15 September 23:16 UTC.
- **Confidence.** Medium that the list is complete for the committed sources: every open-point id of the README and
  every numbered point of the overlay page is placed in one item, and a test holds that list
  (`tests/test_owner_decision_sheet.py`). Low for the recommendations: they are a desk reading by an AI coding
  agent. No owner has read them, no provider page was opened, and the Command page was not looked at in a browser
  for this sheet.
- **Assumptions.** The decision log is complete through R18. The pitch is on 31 October 2026, as the plan says.
  The drafter does not know whether the repository can be read from outside the team. The build notes on the
  Command branch describe what is built. Where this sheet names who should answer, it follows the review lanes of
  the plan and the names the decision log records; neither of you has agreed to that split.
- This sheet is not legal advice and not an official warning. It computes no FPPS, no class and no value for a
  tambon, and it names no tambon beside a score or a class.
