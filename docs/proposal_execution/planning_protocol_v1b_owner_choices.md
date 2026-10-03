# Protocol v1b: the choices that are yours

For Putu and Rachmania. Written by an AI coding agent on 3 October 2026, after decision-log entry R11 (v1b approved in principle; the agent closes the engineering items and writes one proposal for each owner choice). Corrected the same day after a review; what changed is listed at the end.

**Answered on 3 October 2026.** Putu and Rachmania approved all 23 choices exactly as recommended, including the readings DR-B01 to DR-B08 (decision log R12, relayed by Putu). The recommended box of every entry is ticked below, and each entry says where the answer was written. For the four outcome-aware entries (4, 6, 13 and 15) the owners gave no reason of their own; the protocol says so and quotes the recommendation's reason.

**Every entry is now answered (R12).** Each entry gives a question, the options, the option the agent recommended and why, and the recorded answer. Until R12 nothing here was decided: a recommendation is not a decision. The agent wrote each answer into `planning_protocol_v1b.json`, quoted it in the item's closure, and closed every item that needed nothing else.

**"Sensitive"** means the choice can change a class, a headline or a confidence level for a real tambon. No FPPS, class or ensemble has been computed under this protocol. For most entries nobody has seen which way the choice would move a result, so please answer them before anyone looks.

**That is not true of every entry.** Some entries are **outcome-aware**: values for real tambons that bear on the choice were already seen in exploration and are listed in the v1a disclosure. At least these four are: entry 4 (EK-02, EK-13), entry 6 (EK-04), entry 13 (EK-R1, EK-R5) and entry 15 (EK-09). EK-02 (access gap and road criticality seen under four closure variants, one of them a 10 m erosion and one with bridges left out) also touches entries 2, 5 and 23, to a lesser degree. Entry 6 is the clearest case: read its warning before you answer. An outcome-aware choice must not be described as blind in the proposal or the deck.

**Numbers quoted here** come from the receipts in `outputs/planning_v1/`. Each entry names the receipt and the key.

## Where v1b stands

- **Closed (all 18).** First, after R12: OI-02, OI-05, OI-07, OI-08, OI-09, OI-10, OI-11, OI-12, OI-13, OI-14, OI-15, OI-16, OI-17 and OI-18. Each closure names the owner choice it answers and R12. OI-08 holds rule A, copied from the anchors receipt. OI-09 holds the pf-07 frame and the SE2-blind units, which the agent built from the decided rules (entry 15).
- **Closed last, from the run of record (3 October 2026):** OI-01 (demand area and corridor file), OI-03 (hospital-count unit and spike figures), OI-04 (grade-join tolerance and join log) and OI-06 (main-road entry, shelter match distance and facility counts). Each keeps what you answered under `owner_answer`. The run of the whole-path rule was made in a compute window that the agent declared under R12; every acceptance value of the plan is met. v1b is now `draft_for_signature`.
- **Readings DR-B01 to DR-B08:** approved as written in R12. The file keeps them `awaiting_owner_confirmation` while it is a draft; the signers mark them `confirmed` in the signing edit, after reading the closures.
- **Still yours:** accept or reject the compute window the agent declared (`corridor_polygon.run_of_record.compute_window`); Rachmania reviews the pf-07 build; read the closures (`planning_protocol_v1b_closures_summary.md`); sign.

| # | Item | Question | Recommended, and answered in R12 | Sensitive |
|---|---|---|---|---|
| 1 | OI-02 | Which roads make the corridor to the three hospitals? | Buffer the whole fastest path | Yes |
| 2 | OI-15 | How many metres is "one pixel"? | 20 m everywhere | **Yes, high** |
| 3 | OI-10 | Which cell is the reference for class retention? | The default cell | **Yes, high** |
| 4 | OI-05 | Closure thresholds for residential, unclassified and motorway roads | 30 m, 30 m, 50 m | **Yes, high**; outcome-aware |
| 5 | OI-05 | Is an edge delayed under the strict level? | Yes, with k = 2 | Yes |
| 6 | OI-08 | Anchors: which units, and count each once or weight by residents? | Every unit once, khwaeng included | **Yes, high; outcome-aware** |
| 7 | OI-16 | How do shelters enter a vehicle-only ensemble? | Walking, 30 min, pitch level | Yes |
| 8 | OI-06 | What is a "main-road entry"? | Nearest node on a trunk or primary road | Yes |
| 9 | OI-07 | Destinations for the critical-link ranking | Hospitals and main-road entry | Yes |
| 10 | OI-07 | Fix the ranking before signing, or in the first run receipt? | First run receipt | No |
| 11 | OI-18 | Class rule v2: three definitions (two numbers were made up) | See entry | Yes, secondary axis only |
| 12 | OI-13 | Formula for "2024-rescaled demand" | Rescale within each 1 km cell | Yes |
| 13 | OI-12 | Terrain / remoteness proxy: definition and anchor | Code definition, no anchor | Low; outcome-aware |
| 14 | OI-14 | Flood-state levels for three detectors; A6′ threshold (Rachmania). The numbers were made up | The proposals in the file | Moderate |
| 15 | OI-09 | pf-07 unit list and routing; SE2-blind tambons (Rachmania) | All 16 tambons; seat tambon and its neighbours | Yes for SE2; outcome-aware |
| 16 | OI-17 | Scenario S5: when is the node list fixed, and which class picks the tambons? | First run receipt; binding v1 class | Scenario only |
| 17 | OI-10 | k for scenario S3b | 3 per tambon | Scenario only |
| 18 | OI-10 | Selection rule for engine cell E3 | Smallest raise that gives class C | No |
| 19 | OI-06 | Match distance for corroborated shelters | 150 m | Low |
| 20 | OI-04 | Coincidence tolerance for grade joins | 0 m | Yes |
| 21 | OI-01 | Demand area: the eight tambons as they are, or clipped to AOI-02? | Clipped to AOI-02 | No |
| 22 | OI-03 | What counts as one hospital for the "at least 4" test? | Distinct named hospitals | Low |
| 23 | OI-05 | The `culvert=*` tag, which the context builder does not carry | Not read, and say so | Low as far as measured |

---

## 1. Which roads make the corridor to the three hospitals? (OI-02, Putu)

The plan says "3 km corridor buffers along the trunk and primary routes" to the Mae Chan, Chiang Saen and Mae Fa Luang hospitals. It does not say how a route is picked. The draft proposed: take the fastest vehicle path and buffer its trunk and primary segments.

**The spike shows that proposal cannot be signed.** The fastest road to Mae Fa Luang hospital is 31 km of secondary and tertiary road with no trunk or primary segment (`hospital_routes` in `e0_context_spike_proposal.json`). Nothing is buffered, the hospital stays outside the corridor, and the schema refuses a file where the three named hospitals are not all in context.

- **A. Proposal as written** (trunk and primary segments only). Fails the plan's acceptance. 683 km², 57,727 edges.
- **B. Buffer the whole fastest path, whatever the road class.** All three hospitals in context, no-route share 0.075%. 827 km², 65,328 edges, 2.96 min to build.
- **C. Drop Mae Fa Luang as a named destination.** Keeps the plan's wording, but leaves two of the plan's three named destinations and changes plan 1.1 and the acceptance list.

**Recommended: B.** It is the smallest change that meets the three measured acceptance criteria, it uses one rule for all three hospitals, and no road is picked by hand. The rule uses no flood input.

**What you approve with B.** The text below is what would be written into `route_selection_rule.rule`. It fixes more than "buffer the whole path". Each numbered point is a choice the agent made to get a rule that can be run; none is in the plan. Strike or change any of them.

> For each of the three hospitals: build an undirected vehicle graph from every OSM road in the search window that lies inside Thailand, joining ways wherever they share a vertex coordinate; use the modelled class speeds; snap the hospital to the road vertex nearest to its OSM way polygon; take the fastest path from that vertex to the first road vertex inside AOI-02 (the vertex of AOI-02 with the smallest travel time); keep every segment of that path, whatever its road class; buffer the path by 3 km in EPSG:32647; and union the three buffers with AOI-02.

1. **Where the path ends.** At the road vertex inside AOI-02 that is quickest to reach from the hospital. Not at Mae Sai town, not at a tambon centre.
2. **The route graph ignores grade.** Ways are joined wherever they share a vertex coordinate, whatever their bridge, tunnel or layer tags. The routing context does not do that (entry 20). So the route search can pass a junction that the context later treats as apart.
3. **Thailand only.** Roads in Myanmar and Laos are not used, even where they are shorter.
4. **Search window.** The bounding box of AOI-02 widened by 0.45 degrees on each side (99.36–100.49°E, 19.81–20.92°N). A faster route that leaves this box would not be found.
5. **Speeds.** The fixed class speeds of `evidence_scenarios.py`: motorway 80, trunk 70, primary 60, secondary 50, tertiary 40, residential and unclassified 25, local 20 km/h. Undirected: one-way rules and turn restrictions are not modelled.
6. **Excluded roads.** Ways tagged `access` or `motor_vehicle` = `no` or `private`.
7. **Hospital snap.** The nearest road vertex to the hospital's OSM polygon; the snap distances were 0 m, 0 m and 4 m.

- **Downstream:** OI-01 (the polygon) can close from the spike receipt of the chosen rule once entry 21 is answered. OI-03 cannot: it needs one run of the chosen rule in a compute window that you declare (see "Needed from a person"). OI-04 and the counts of OI-06 follow from the E4 build. Plan 1.1's words "trunk and primary routes" become "fastest routes".
- **Sensitive:** yes. It decides which hospitals are destinations and how large the road graph is. Mae Fa Luang is 42 modelled minutes from the edge of AOI-02, so it matters for "any route" and the 60-minute threshold more than for 30 minutes.
- **In the draft:** a proposal, which is option A. The slot is empty.

Your answer: ☐ A ☒ B as written above ☐ B with changes: ________ ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** B as written, with its seven sub-rules. Written into `corridor_polygon.route_selection_rule.rule` and `.sub_rules`; OI-02 is closed.

## 2. How many metres is "one pixel"? (OI-15, Putu)

The flood-state axis grows and shrinks each flood input by one pixel. The plan gives 20 m for shrinking only. It gives nothing for growing, and nothing for vector agency products, which have no pixel.

- **A. 20 m for shrinking and growing, for every input.** A vector product gets a 20 m buffer inwards or outwards.
- **B. Each product's own pixel** (for example 10 m for a Sentinel-1 agency layer, 20 m for the team's grid).
- **C. 20 m for rasters, 10 m for vector products.**

**Recommended: A.** 20 m is the only distance in the plan (section 5 item 11, axis 1) and it is the team's grid. One distance keeps the two sides symmetric and the lanes comparable.

- **Downstream:** the three flood-state levels of every ensemble cell, and confidence condition C4 in v1a.
- **Sensitive: yes, high.** C4 asks whether exposure moves by more than 15 points between the grown and the shrunk input. If it does, the unit is low confidence and is forced to class E. A larger distance makes more units low.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** 20 m everywhere. Written into `ensemble_grid.core_axes[0].one_pixel_m`; OI-15 is closed.

## 3. Which cell is the reference for class retention? (OI-10, Putu with Rachmania)

A class is headlined only if at least 60% of the ensemble cells keep it. "Keep" needs a reference class, and the plan names none.

- **A. The default cell:** flood input as provided, central closure, public facilities, WorldPop 2020, P10/P90 anchors, default weights. Retention is the share of the 540 cells with the same v1 class.
- **B. The most common class across the cells.** No reference cell is needed, and retention is never below the largest share.
- **C. The cell with the median FPPS.**

**Recommended: A.** The plan's words are "% of runs keeping the class", and the class a unit is reported with is the one from the default settings signed in D4.

- **Downstream:** the headline rule, the demo-tambon rule in v1a, and scenario S5 (entry 16).
- **Sensitive: yes, high.** It decides whether a class is shown or replaced by "unstable: verify".
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** The default cell. Written into `ensemble_grid.headline_rule.reference_cell`; OI-10 is closed (with entries 17 and 18).

## 4. Closure thresholds for the three road classes the plan leaves out (OI-05, Putu)

Under the central level a road closes when the flooded length reaches a threshold: 50 m for trunk, primary and secondary, 30 m for tertiary and local. The plan gives no threshold for motorway, residential and unclassified roads. In the whole-path spike context **those classes are 60% of all edges**: residential 32,928 of 65,328 (50.4%), unclassified 6,499 (9.9%), motorway none (`edge_counts.by_road_class` in `e0_context_spike_whole_path.json`).

- **A. Motorway 50 m; residential 30 m; unclassified 30 m.**
- **B. All three 30 m.**
- **C. All three 50 m.**

**Recommended: A.** It follows the grouping already in `road_risk.py`, where residential and unclassified share the factor of local roads and motorway shares the factor of trunk and primary. A and B give the same result here, because the corridor has no motorway.

- **Downstream:** every central-level closure, and so access loss, road criticality and classes.
- **Sensitive: yes, high, and outcome-aware.** The v1a disclosure records that access gap and road criticality for the Mae Sai tambons were seen under four closure variants (EK-02) and that 20 m and 50 m rules were tried on Hat Yai (EK-13).
- **In the draft:** a proposal, which is option A. The new `closure_rules.py` refuses to run the central level on these classes until you answer.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Motorway 50 m, residential 30 m, unclassified 30 m. Written into `closure_rule_v1.unassigned_road_classes.length_threshold_m`; OI-05 is closed (with entries 5 and 23). Your reason: none given. Because this choice is outcome-aware (EK-02, EK-13), the closure says that no reason was given and quotes the recommendation's reason.

## 5. Is an edge delayed under the strict level? (OI-05, Putu)

The plan says strict means "fraction ≥ 0.5 only", gives the delay formula for the central level only, and lists delay factors k = 2 / 4 / 6 beside strict / central / permissive.

- **A. Yes.** An edge with at least 20 m flooded and less than half its length flooded is slowed by (1 + 2 × f).
- **B. No.** Under strict an edge is either closed or untouched. Then k = 2 never acts, just as k = 6 never acts under permissive.

**Recommended: A.** Reading DR-B01 pairs k = 2 with strict; with B that pairing would mean nothing. This is a judgement: the plan's text supports either.

- **Downstream:** travel times under the strict level, so 15, 30 and 60 minute access in a third of the ensemble cells.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Delayed with k = 2. Written into `closure_rule_v1.delay_under_strict.rule`.

## 6. National anchors: which units, and count each once or weight by residents? (OI-08, both)

The plan says the vulnerability anchors are "national tambon percentiles" of the dependent share. It names no unit set and no percentile rule. The agent computed the anchors under four rules. All four are in one receipt, `outputs/planning_v1/national_vulnerability_anchors_v1.json` (`values` and `alternatives_for_review`), and in `national_vulnerability_anchors.anchor_candidates` in the protocol.

> **This choice is not blind.** Disclosure item EK-04 of v1a records that the age dependent shares of six Mae Sai tambons were seen in exploration. With those shares and the anchors below, the vulnerability component of those tambons can be worked out under each rule before you choose. Please choose by what the plan's words mean, write your reason beside your answer, and do not look the shares up first. The protocol records this as disclosure item EK-B01, and the proposal must not call the anchors a blind choice.

Two questions, four combinations:

| Rule | Units | Each unit counts | P5 | P10 | P75 | P90 | P95 |
|---|---|---|---|---|---|---|---|
| **A** (proposal in the draft) | all 7,425 `tha_admin3` units | once | 0.313 | 0.351 | 0.454 | 0.478 | 0.494 |
| **B** | all 7,425 | by its residents | 0.223 | 0.258 | 0.432 | 0.458 | 0.475 |
| **C** | 7,256: without the 169 Bangkok khwaeng | once | 0.323 | 0.357 | 0.455 | 0.478 | 0.495 |
| **D** | 7,256 | by its residents | 0.223 | 0.286 | 0.438 | 0.463 | 0.477 |

- **Once or by residents.** Weighting by residents lowers P10 by 9 points (A to B), because large city units have few children and few older adults. A lower P10 raises the component for most units.
- **Khwaeng in or out.** A khwaeng is Bangkok's counterpart of a tambon, and COD-AB lists the 169 of them in the same layer. "National" reads as including them; "tambon" reads as leaving them out. Leaving them out raises P5 by 1.0 point and P10 by 0.5 points, and moves the other anchors by less than 0.1 point (A to C).
- No unit has fewer than 100 residents, so the minimum-denominator part of the rule changes nothing.

**Recommended: A.** Counting each unit once is what "percentile across tambons" says, and "national" covers Bangkok. This is the drafting agent's reading of four words; it is not evidence, and C is a fair reading too.

- **Downstream:** the vulnerability component of every unit in every case, and trigger A of class rule v2 (P75).
- **Sensitive: yes, high, and outcome-aware.** Note also that under A, P10 and P90 are only 12.6 points apart: 1.3 points of dependent share move the component by 10 of its 100 points.
- **In the draft:** the four rules are candidates. The slots for the values, the unit set and the percentile rule are empty. An earlier edit had filled them in as A and closed OI-08 (as reading DR-B09); that was undone after review, and DR-B09 no longer exists.
- **After you answer:** for A, B, C or D the agent copies that rule's values from the receipt and closes OI-08 with your answer and your reason quoted. For any other rule the builder is changed and run again with `--replace --reason`, and the new receipt names the one it replaces.

Your answer: ☒ A ☐ B ☐ C ☐ D ☐ other: ________   Reason: none given

**Answered 3 Oct 2026 as recommended (R12).** Rule A. The agent copied rule A's values from the receipt (key `values`) into `national_vulnerability_anchors.values`, with the unit set, the percentile rule and the receipt, and closed OI-08. Your reason: none given. The closure and `national_vulnerability_anchors.owner_decision` say so, quote the recommendation's reason, and record that the choice is outcome-aware (EK-04, EK-B01) and must not be called blind.

## 7. How do DDPM shelters enter a vehicle-only ensemble? (OI-16, both)

The ensemble runs in vehicle mode. Two of its three facility levels add DDPM shelters, whose access is defined as walking, 30 minutes, and whose data may only be shown at pitch level (D8b).

- **A.** Inside the ensemble the shelter service is walking, 30 minutes; hospital and main-road entry stay vehicle. Cells that use DDPM data are pitch level. For a public overlay, retention is counted over the 180 cells of the public facility set only, and the overlay says so.
- **B.** Shelters by vehicle, 30 minutes, inside the ensemble.

**Recommended: A.** It keeps the plan's own definition (section 3.4: "Pitch level: adds DDPM located shelter (walking, 30 min)") and D8b.

- **Downstream:** the access-gap component in 360 of the 540 cells; what a public overlay may report.
- **Sensitive:** yes. A tambon can be headlined in the pitch overlay and "unstable" in the public one, or the reverse, because they count different cells.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `facility_sets.shelters_in_the_ensemble`; OI-16 is closed.

## 8. What is a "main-road entry"? (OI-06, Putu)

Main-road entry is one of the two public services (vehicle, 15 minutes). The plan does not say where the entry is.

- **A. The nearest node on a trunk or primary road, links included, inside the routing context.**
- **B. The same, with secondary roads added.**
- **C. Trunk roads only** (Highway 1).

**Recommended: A.** The file already names the source as the "OSM trunk and primary network". In the whole-path spike context trunk and primary are 1,977 of 65,328 edges (3.0%) and secondary 4,122 (6.3%) (`edge_counts.by_road_class` in `e0_context_spike_whole_path.json`), so B would make a main road much easier to reach.

- **Downstream:** the access-gap and road-criticality components at the public level; the destination set of entry 9.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `facility_sets.services.main_road_entry.definition`. OI-06 stays open for the facility counts of the corridor of record (`owner_answer` lists this answer and entry 19's).

## 9. Destinations for the critical-link ranking (OI-07, Putu; Rachmania reviews)

Links are ranked by how many residents' baseline routes use them. Routes to what?

- **A. The public set: OSM hospitals and main-road entry.**
- **B. Hospitals only.**
- **C. Every listed facility, DDPM shelters included.**

**Recommended: A.** It matches the road-criticality definition in plan 3.4 ("a baseline route to any hospital or main road") and keeps the ranking free of pitch-level DDPM data.

- **Downstream:** the top 20 links, scenarios S3 and S3b, and trigger B of class rule v2.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `critical_link_selection.destination_set_for_ranking`; OI-07 is closed (with entry 10).

## 10. Fix the ranking before signing, or in the first run receipt? (OI-07, Putu)

Plan 6.3 wants links fixed before any scoring. Plan row G7b schedules the ranking (E6) after v1b.

- **A. Sign with the rule. The ranking's SHA-256 goes into the receipt of the first run, before any scoring.**
- **B. Run E6 first and record the ranking's SHA-256 in v1b.** Signing then waits for the E4 build and E6.

**Recommended: A.** The ranking uses no flood input, so the rule fixes it. Both options satisfy plan 6.3.

- **Sensitive:** no, as long as the rule is fixed.
- **In the draft:** both options are described; none is chosen.

Your answer: ☒ A ☐ B

**Answered 3 Oct 2026 as recommended (R12).** Written into `critical_link_selection.ranking_output.binding` as `bound_in_first_run_receipt`.

## 11. Class rule v2: three definitions (OI-18, both)

v2 is the secondary axis; v1 stays binding (D6). The proposals below came from the drafting agent. **Two of their numbers, 100 residents and 10 percent, were made up to give you something to react to. No data is behind them.**

**(a) When does a critical link "isolate" residents?**
- **A.** Each top-20 link that crosses the flood extent is closed on its own. The trigger fires when at least 500 residents of the unit (the 500 is in v1a) lose every vehicle route to a hospital or main-road entry.
- **B.** All top-20 links in the extent are closed together.

Recommended: A. It is the literal reading of "a top-20 critical link ... isolates".

**(b) Which facility "serves" a unit?**
- **A.** A facility that is the nearest of its kind, by baseline vehicle time, for at least 100 of the unit's residents.
- **B.** The one facility of each kind that is nearest for the most residents of the unit. No number needed.

Recommended: A, with the 100 tied to guardrail GR1, which already uses 100 residents as the smallest group the protocol will say anything about. That is a reuse of a signed number, not evidence.

**(c) How does JRC water occurrence become a flag for a whole unit?**
- **A.** At least 10 percent of the unit's land (outside permanent water) has JRC occurrence of 25 percent or more. The 10 percent is made up.
- **B.** The same test at 20 percent, the flooded-share anchor signed in D4, with 10 and 30 percent reported beside it.
- **C.** No flag from JRC. Class D under v2 is reported as "not evaluable" unless GISTDA Repeated Flood Areas arrives.

Recommended: B. **No defensible value exists** in the plan or in any data the team has. B at least adds no new free number. Either way the JRC tiles for the east of Mae Sai and for SE2 are not on disk (downloads DL-1 and DL-2), so the flag cannot be computed there until you approve them.

- **Sensitive:** yes, for the v2 axis only.

Your answers: (a) ☒ A ☐ B   (b) ☒ A ☐ B   (c) ☐ A ☒ B ☐ C   other: ________

**Answered 3 Oct 2026 as recommended (R12).** (a) A, (b) A with the 100 tied to guardrail GR1, (c) B. Written into `class_rule_v2_inputs`; OI-18 is closed. The JRC flag still cannot be computed for the east of Mae Sai and for SE2 until downloads DL-1 and DL-2 are approved.

## 12. Formula for "2024-rescaled demand" (OI-13, both)

The population axis compares WorldPop 2020 with "2024-rescaled demand". The plan says only "2024/2020 1 km rescale".

- **A.** Inside each 1 km cell of the 2024 grid, multiply every 2020 100 m count by (2024 cell total ÷ sum of the 2020 counts in the cell). Where 2020 has nobody, nothing is added, and the 2024 residents left out are reported as unallocated.
- **B.** One ratio per tambon (2024 total ÷ 2020 total).
- **C.** Cut the population axis now. This is not what the plan's cut line does. Cut line 6 reads "Population-vintage and vulnerability-anchor axes (540 → 135 cells)": it cuts two axes together, it is the sixth conditional cut in order, and it applies only if the schedule forces it. Cutting the population axis alone would leave 270 cells and would be a new cut that you declare.

**Recommended: A.** It matches the plan's words and the way `bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells.

- **Sensitive:** yes. It changes exposure shares and every access denominator in half the cells.
- **In the draft:** a proposal, which is option A.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `ensemble_grid.core_axes[3].rescale_formula`; OI-13 is closed.

## 13. Terrain / remoteness proxy: definition and anchor (OI-12, both)

The proxy replaces age-based vulnerability in one sensitivity run on case O1 and in scenario S8. The plan defines neither the proxy nor its anchor.

- **A.** The definition in `mae_sai_context.py` (a cell counts when its slope is at least 8 degrees or the nearest drivable road is at least 750 m away), and **no anchor**: the component is 100 × the share of the unit's residents in such cells.
- **B.** The same definition with an anchor of 0.25. The replay used 0.25 with its results in view (disclosure items EK-R1, EK-R5).
- **C.** Drop the proxy. S8 and the sensitivity run are reported as "not attempted".

**Recommended: A.** Plan 3.4 says the national anchors exist to replace "the unexplained 0.25/0.30", and D4 made exposure share-only for the same reason.

- **Sensitive:** low. O1 rows are tier T2 and are forced to E unless a detector passes the skill bar. It decides what S8 shows. Outcome-aware for option B.
- **In the draft:** the definition is proposed; no anchor is proposed.

Your answer: ☒ A ☐ B ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** The code definition, no anchor. Written into `ensemble_grid.terrain_remoteness_proxy`; OI-12 is closed. Your reason: none given; the closure says so and quotes the recommendation's reason (outcome-aware for option B only).

## 14. Flood-state levels for three detectors, and the A6′ threshold (OI-14, Rachmania; Putu confirms)

The plan defines the three levels for M1-v2 and the legacy mask only. **None of the four proposals below is in the plan, and the numbers in them were made up by the drafting agent: ±1 dB for M1-literal, and 0.4, 0.5 and 0.6 for A6′. No data is behind them.** They give you something to react to.

| Input | Proposal in the file | Where the numbers come from |
|---|---|---|
| M1-literal | Otsu threshold −1 / 0 / +1 dB | Copied from the plan's ±1 dB for M1-v2. The plan does not say it applies to M1-literal |
| UN-SPIDER reproduction | shrink / as provided / grow by one pixel; the ratio 1.25 is not tuned | The plan calls the ratio "untuned", so the levels are spatial. The distance is entry 2 |
| A6′ classifier | calibrated probability 0.4 / 0.5 / 0.6 | **Made up.** 0.5 ± 0.1 has no basis in the plan or in any result |
| A6′ extent threshold | 0.5 on the calibrated probability, set on GEOID development tiles before any Mae Sai run | **Made up.** 0.5 is the usual cut of a calibrated probability, not a tuned or cited value |

- **A. Accept all four.**
- **B. Change one or more** (write which). For A6′, one alternative that adds no free number is to take the threshold that maximises IoU on the GEOID development tiles, with the levels at that threshold ± a step you name.

**Recommended: A, as a default and nothing more.** M1-literal mirrors M1-v2. The UN-SPIDER levels have to be spatial. For A6′ the agent has no ground for 0.4 and 0.6 over any other pair; Rachmania owns this lane and should set them. Whatever you choose for A6′ must be chosen with no Mae Sai result in view.

- **Sensitive:** moderate. O1 is forced to E unless a detector passes the skill bar; these levels move the ensemble spread, the would-be classes and the divergence matrix.

Your answer: ☒ A ☐ B: ________

**Answered 3 Oct 2026 as recommended (R12).** All four proposals, as a default and nothing more. Written into `ensemble_grid.core_axes[0].t2_levels_by_input` and `a6_prime_extent_threshold`; OI-14 is closed. The status beside them still says that the numbers were made up and that Rachmania may amend them at signing.

## 15. The pf-07 frame and the SE2-blind tambons (OI-09, Rachmania)

**(a) Unit list of pf-07 (case SE2).**
- **A. All 16 tambons of Mueang Chiang Rai district.**
- **B. A hand list of the tambons along the Kok River** (Rim Kok, Rop Wiang, Ban Du and others), with the rule that picked them written down.

Recommended: A. SE2 is already disclosed as chosen with the outcome in view. A list picked tambon by tambon would add to that; a whole district does not.

**(b) Routing geometry and hospitals of SE2.** Recommended: the union of the pf-07 tambons with a 3 km buffer, clipped to Thailand; every OSM hospital inside it. The plan says nothing here, so please write your own if you disagree.

**(c) Which tambons of the blind district?** The population rule picks **Phan** (TH5705); Mae Chan is second, 5.3% behind (`se2_blind_district_ranking.json`). The plan says "amphoe-seat tambons" and gives no rule for them. The protocol now has two empty slots for this, `se2_frame.se2_blind_unit_rule` and `se2_frame.se2_blind_unit_list`, and OI-09 cannot close while either is empty.
- **A. The tambon that holds the district office.** One unit. The agent expects this to be Mueang Phan (TH570513) but has not checked it against a source; please confirm.
- **B. That tambon and every tambon that touches it.**
- **C. All 15 tambons of Phan.**
- **D. Drop SE2-blind** under cut line 4 (SE2-dist stays). Both slots then say so.

Recommended: B. It is the closest reading of the plan's plural that still gives more than one unit. It has no other basis.

**Still needed from Rachmania, whatever you choose:** the frame file `resources/planning_frames/pf-07_mueang_chiang_rai.geojson`. *(Overtaken by R12: with the rule decided, the agent built the file from the rule; Rachmania reviews it. See below.)*

- **Sensitive:** yes for SE2 (which units can show a class). SE2-blind is blind by rule, not by ignorance: flooded shares for all 124 Chiang Rai tambons were seen in exploration (EK-09). That makes (a) and (c) outcome-aware.

Your answers: (a) ☒ A ☐ B   (b) ☒ as recommended ☐ other: ________   (c) ☐ A ☒ B ☐ C ☐ D

**Answered 3 Oct 2026 as recommended (R12).** Your reason: none given; the closure of OI-09 says so and quotes the recommendation's reasons for (a) and (c). What the agent then did (`scripts/build_planning_frames.py`, receipt `resources/planning_frames/planning_frames_v1_receipt.json`):

- **(a) pf-07:** the 16 COD-AB tambons of Mueang Chiang Rai district (TH570101 to TH570121), written to `resources/planning_frames/pf-07_mueang_chiang_rai.geojson`, SHA-256 `2bdf946b6ff759f0950d4d7e0fcf9319cc42391db15a9af30a7ae87f417cf0ba`. A rebuild gives the same bytes.
- **(b) Routing and hospitals:** the union buffered by 3 km and clipped to Thailand, about 2,422 km² (`pf-07_mueang_chiang_rai_routing.geojson`). Every OSM hospital inside it: 17 objects, 15 distinct named hospitals and 2 unnamed objects. The buffer reaches Mae Chan hospital in the next district, and some objects are small (health-promoting hospitals, a traditional-medicine clinic, a dental school). The rule takes them all; please say if any should leave the facility set.
- **(c) The district office, checked:** OSM node 3840722494, named "ที่ว่าการอำเภอพาน" (Phan district office), tagged `office=administrative`, at 99.7405302 E, 19.5538862 N. It lies in **TH570513 (Mueang Phan)**, as the agent had expected. No object tagged `amenity=townhall` or `office=government` carries that name; the rule accepts any `office=*` tag. An area named "สำนักงานอำเภอพาน" (district office), tagged `landuse=commercial`, lies in the same tambon and corroborates it.
- **SE2-blind units (rule B):** TH570513 and the five Phan tambons that share a boundary with it: TH570504 (Santi Suk), TH570506 (Hua Ngom), TH570508 (Pa Hung), TH570509 (Muang Kham) and TH570511 (San Klang). No tambon of another district touches it.
- **Rachmania:** please review the frame, the routing geometry, the hospital list and the office lookup. OI-09 is closed on the build; a correction would be a re-run of the script and a new closure.

## 16. Scenario S5 (OI-17, Putu)

S5 adds a temporary shelter at a pre-declared node in each tambon that is class A or B.

**(a) When is the node list fixed?** ☒ **A. In the first run receipt, before any scoring** (recommended, for the same reason as entry 10) ☐ B. In v1b, after the E4 build.

**(b) Which class decides "A or B"?** ☒ **A. The binding v1 scenario class of the SE1 reference cell** (recommended; it follows D6 and entry 3) ☐ B. The v2 class ☐ C. A or B in any ensemble cell.

- **Sensitive:** scenario cells only. Cut line 5 drops S5 first.

**Answered 3 Oct 2026 as recommended (R12).** Written into scenario S5 (`add_destination_nodes.binding`, `class_used_for_selection`); OI-17 is closed.

## 17. k for scenario S3b (OI-10, Putu with Rachmania)

S3b fails "the top-k bridge edges". ☒ **A. 3 per tambon**, to match S3 (recommended) ☐ B. Another number: ________

- **Sensitive:** scenario cells only.

**Answered 3 Oct 2026 as recommended (R12).** k = 3, written into scenario S3b.

## 18. Selection rule for engine cell E3 (OI-10, Putu with Rachmania)

E3 changes one real O2 row as little as possible to show a counterfactual class C, and labels it synthetic.

`scoring.assign_action_class` returns C only when **all** of these hold: confidence is not low; FPPS is at least 35; exposure is at least 65 and access gap at least 50; rule A (exposure ≥ 70 and access gap ≥ 70) does not fire; and rule B (road criticality ≥ 75 and access gap ≥ 55) does not fire. Exposure 65 with access gap 50 gives only 26.25 FPPS points (0.25 × 65 + 0.20 × 50), so the two thresholds alone do not reach 35.

- **A. (proposal in the file)** Take the unit with the highest exposure and raise the one component that is furthest below the class C thresholds. **This can fail:** if both components are short it raises only one.
- **B.** Take the unit that needs the smallest total raise to reach exposure 65 and access gap 50, and raise only those two. **This can fail too:** the row stays E if its FPPS is still below 35 or its confidence is low, and it becomes B if its road criticality is 75 or more and its access gap 55 or more.
- **C.** Take, among the O2 units for which it is possible, the one that needs the fewest added component points for `assign_action_class` to return C, and add only those points: exposure up to 65 and access gap up to 50 where they fall short, then flood likelihood up to the value that brings FPPS to 35 if it is still below. The synthetic row carries confidence "medium" and says that this was set. A unit is not eligible when rule A or B of `scoring.py` would fire first. Ties go to the lower unit ID. If no unit is eligible, E3 is reported as "no counterfactual C produced".

**Recommended: C.** It is the only one of the three that is sure to do what E3 is for, or to say that it could not. Raising flood likelihood for the FPPS shortfall is the agent's choice (it has the largest weight, so it needs the fewest points); change it if you prefer another component.

- **Sensitive:** no. The row is labelled synthetic and counted in the ENG column. The rule is fixed here so that nobody picks the row after seeing the scores.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☒ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Rule C, with flood likelihood raised for an FPPS shortfall. Written into scenario E3 `selection_rule`.

## 19. Match distance for corroborated shelters (OI-06, Putu)

A DDPM shelter is "corroborated" when it matches an OSM building or amenity. The plan gives 150 m for hospitals and nothing for shelters.

- **A. 150 m, as for hospitals.**
- **B. 50 m.**

**Recommended: A**, because it is the only distance the plan states. Be aware that in a town almost every point is within 150 m of some building, so this level may differ little from "all listed". The E4 build will report the match rate. Cut line 8 drops this level first.

- **Sensitive:** low.

Your answer: ☒ A ☐ B ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** 150 m. Written into `facility_sets.sets[1].shelter_match_distance_m`. **Measured in the run of record:** 48 of the 82 located shelters in the routing context have an OSM building or amenity within 150 m (match rate 0.585); 20 of them have a building, 28 an amenity only. OSM building coverage around the corridor is sparse (1,134 objects tagged as buildings in the extract box), so this level is not close to "all listed" here, against the expectation above. OI-06 is closed.

## 20. Coincidence tolerance for grade joins (OI-04, Putu)

The context builder keeps two road vertices apart when they sit at the same coordinate with different bridge, tunnel or layer tags, so a bridge is cut off from its approach roads. D13 allows "endpoint-only coincident joins", logged. D13 does not say how close "coincident" is.

- **A. 0 m.** Two nodes are joined only when their OSM coordinates are identical (to 1e-7 degree) and each is the end of at least one way. This is what `grade_join.py` does.
- **B. A distance above 0 m** (write it). Nearness would then create joins, which the finals rule forbids.
- **C. No automatic join.** Only the 20 reviewed AOI-01 junctions connect; every other candidate stays apart until someone reviews it.

**Recommended: A.** It is the narrowest rule that reconnects bridges. With it the baseline no-route share is 0.075%; without any join it is 1.41% (`baseline_no_route` in the spike receipts). Both are under the plan's 10%.

**What to weigh.** The context builder's own review text says that equal coordinates and endpoint tags "do not establish shared OSM node identity or traversability". Rule A joins on exactly that. It made 345 joins in the whole-path context (319 in the other), and none was looked at by a person. Each join is logged with `passability: unknown`.

- **Downstream:** every access result. A wrong join lets a route cross where no junction exists.
- **Sensitive:** yes.
- **In the draft:** a proposal of 0 m; the slot is empty. An earlier edit had filled it in as "from D13"; that was undone after review, because D13 names no tolerance.

Your answer: ☒ A ☐ B: ____ m ☐ C ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** 0 m. Written into `grade_join_policy.coincidence_tolerance_m`. The run of record logged 345 joins (`outputs/planning_v1/grade_join_log_of_record.json`); OI-04 is closed.

## 21. Demand area: the eight tambons as they are, or clipped to AOI-02? (OI-01, Putu)

Plan 3.1 takes the union of the eight tambons as the demand area and AOI-02 as the base of the routing polygon. The union is 214.5 m² larger than AOI-02 (`context_call.tambon_union_outside_aoi_02_m2` in the spike receipts), and the unchanged context builder refuses a demand area that the routing polygon does not contain.

- **A. The union clipped to AOI-02.** Both spike runs did this. It matches the declared tolerance (coverage of at least 0.999 counts as full).
- **B. The union as it is, and a routing polygon enlarged to contain it.** This changes the base of the corridor.

**Recommended: A.** A sliver of 214.5 m² on the edge of a 542 km² district does not justify changing the base of the corridor.

- **Sensitive:** no.
- **In the draft:** `context_call.aoi_geometry` keeps the plan's wording; `context_call.demand_area_rule` is empty with A as its proposal.

Your answer: ☒ A ☐ B ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `corridor_polygon.context_call.demand_area_rule`. The run of record used it and wrote `outputs/planning_v1/corridor_of_record.geojson`; OI-01 is closed.

## 22. What counts as one hospital for the "at least 4" test? (OI-03, Putu)

The plan's acceptance asks for at least 4 hospitals in the context. The spike counted OSM objects. In the whole-path context there are 6 objects: four named hospitals (Mae Sai, Mae Chan, Chiang Saen, Mae Fa Luang), a second object for Mae Fa Luang (a node with the same name as the hospital's way) and one hospital-tagged way with no name (`hospital_count_breakdown` and `hospitals_in_routing_context` in `e0_context_spike_whole_path.json`).

| | Whole path | Proposal as written |
|---|---|---|
| A. OSM objects | 6 | 4 |
| B. Distinct named hospitals | 4 | 3 |
| C. Distinct named hospitals plus unnamed objects | 5 | 4 |

**Recommended: B.** A count that a duplicate OSM object can raise is not a count of hospitals, and nothing shows that the unnamed object is one. Under B the whole-path corridor meets the test with exactly 4. The record then gives both numbers.

**Also note:** all six objects are destinations in the baseline access run, because the facility set is "OSM hospitals inside the routing context". If the unnamed object should not be a destination, say so here; that would be a change to the facility set (OI-06).

- **Sensitive:** low. It decides whether a corridor passes acceptance, not a score.
- **In the draft:** `acceptance.hospital_count_unit` is empty, with B as its proposal.

Your answer: ☐ A ☒ B ☐ C ☐ other: ________   Unnamed object a destination? ☒ yes ☐ no

**Answered 3 Oct 2026 as recommended (R12).** Written into `corridor_polygon.acceptance.hospital_count_unit`. The second question carried no recommendation to drop the unnamed object, so nothing was changed: it stays a destination, and the box above records that reading, not a separate answer. Say so if you meant otherwise. The run of record, made in a declared compute window, has 4 distinct named hospitals (6 OSM objects) and meets the test with exactly 4; OI-03 is closed.

## 23. The `culvert=*` tag (OI-05, Putu)

The plan's central closure level closes bridges and culverts at a lower flooded fraction (0.25), and names three tags: `bridge=yes`, `tunnel=culvert`, `culvert=*`. The context builder, which the plan keeps unchanged, carries the bridge, tunnel and layer tags on each edge. It does not carry a culvert tag. So as built, the central level cannot see `culvert=*`.

- **A. `culvert=*` is not read.** The 0.25 fraction applies to `bridge=yes` and `tunnel=culvert` edges only, and every closure output says so. The plan's tag list stays in the protocol beside that statement.
- **B. Carry the culvert tag into the planning context in task E4.** That changes the builder the plan calls unchanged, and E4 grows.

**Recommended: A.** In the whole-path spike context 192 edges are tagged `bridge=yes` and none `tunnel=culvert` (179 and none in the other context; `edge_counts` in the spike receipts). How many ways carry only `culvert=*` is **not measured**, because the builder drops the tag. The agent's understanding is that OSM mappers put `tunnel=culvert` on the waterway under a road, not on the road, so few road edges would carry either tag; that is general knowledge of OSM practice, not a count.

- **Sensitive:** low as far as measured. It can only matter for edges that carry `culvert=*` and are flooded for between a quarter and a half of their length.
- **In the draft:** `closure_rule_v1.culvert_tag_handling.rule` is empty, with A as its proposal. `bridge_culvert_note` describes the limitation and says it awaits your decision.

Your answer: ☒ A ☐ B ☐ other: ________

**Answered 3 Oct 2026 as recommended (R12).** Written into `closure_rule_v1.culvert_tag_handling.rule`.

---

## Readings to confirm or amend at signing

These are not new questions. Each is a value the drafting agent filled in where the plan is silent; the file cannot be signed until each is marked `confirmed` or `amended`. There are eight. The engineering runs bear on some of them.

**Approved as written in R12.** The schema keeps every reading `awaiting_owner_confirmation` while the file is a draft, so the agent did not change their status. The signers set each to `confirmed` in the signing edit, after reading the closures.

| ID | Reading | What the runs add |
|---|---|---|
| DR-B01 | k = 2 / 4 / 6 paired with strict / central / permissive (540 cells) | See entry 5 |
| DR-B02 | Edge = straight node-to-node segment; "any intersection" = more than 1e-6 m | The regression matched the finals edge lists exactly under this reading |
| DR-B03 | Critical links weighted by WorldPop 2020 residents; ties on edge ID | Nothing new |
| DR-B04 | 1 km cells assigned to tambons by projected-area fraction | Used for the anchor candidates; 99.6% of the raster's residents fall inside a unit (`allocation_totals` in the anchors receipt) |
| DR-B05 | Terrain proxy run one at a time, outside the 540 cells | Nothing new |
| DR-B06 | A link belongs to the tambon that holds its midpoint | Nothing new |
| DR-B07 | The critical-link ranking and the national percentiles may run before v1b | The percentiles were run (plan 3.4 also asks for them in v1b). The ranking was not run |
| DR-B08 | Scenario S8 is based on O1 | Nothing new |

DR-B09 (the anchor unit set and percentile rule) was withdrawn on 3 October: it is no longer a filled-in value to confirm but an empty slot to decide (entry 6).

## Needed from a person, not a choice

- **Rachmania:** review of the pf-07 frame, routing geometry, hospital list and district office lookup that the agent built from the decided rule (entry 15, `resources/planning_frames/`), and the statement left open at the v1a signing on whether any M1-v2 tuning on GEOID tiles has been run.
- **Putu:** review of the four new modules (`normalisation.py`, `closure_rules.py`, `grade_join.py`, `ddpm_shelters.py`). And **the compute window**: plan 5 item 1 asks for builds to run serially with no concurrent SNAP jobs. On 3 October the agent declared one under R12 (10:36:18 to 10:40:20 +08:00), checked the machine with tasklist, ran the chosen corridor once with `--compute-window` while a process monitor sampled the machine, and closed OI-01, OI-03, OI-04 and OI-06 from that run. Read `corridor_polygon.run_of_record.compute_window` and say if you do not accept it. A later E4 build needs its own window.
- **Either owner:** approval of downloads DL-1 and DL-2 before any v2 class D or JRC note. Neither blocks signing.
- **A human:** bring `claude/planning-protocol-v1` into `codex/thai-event-selection` with a merge commit, never a squash, before v1b is signed.

## Where the plan says two things

Each of these is handled above or already marked as a reading. They are listed so that nobody is surprised later.

1. **Corridor.** Plan 1.1 puts the corridor along "trunk and primary routes" to three hospitals and requires all three in context. The road to Mae Fa Luang has no trunk or primary segment (entry 1).
2. **Demand area.** Plan 3.1 takes the eight-tambon union as the demand area and AOI-02 as the base of the routing polygon; the union is not inside AOI-02 (entry 21).
3. **When links are fixed.** Row G7b makes v1b depend on E0 and E4 only and schedules the ranking (E6) after v1b; section 6.3 wants links and nodes fixed before any scoring (entries 10 and 16).
4. **Delay factors.** Section 5 item 11 lists k = 2 / 4 / 6 for the three levels; item 2 states a delay for the central level only, and under permissive no delay can act (entry 5, DR-B01).
5. **Terrain proxy.** It is listed inside axis 4, but 540 cells leave no room for it (DR-B05); section 6.2 bases S8 on O2 and section 3.4 restricts the proxy to O1 (DR-B08).
6. **SE2-blind.** It is to be "computed before any overlay", but flooded shares for every Chiang Rai tambon were already seen (EK-09). The selection rule itself uses population only. Also, "all 124 Chiang Rai tambons inside the 4009 analysis extent" is the whole province: Chiang Rai has 124 tambons.
7. **Culverts.** The closure rule reads a tag that the unchanged context builder does not carry (entry 23).
8. **Compute window.** The plan wants the spike numbers from a serial run in a declared compute window. The spike ran four times on a shared machine without one.
9. **Schedule.** The plan had the E0 spike on 26–27 September, the E4 build done by 1 October and v1b recorded on 2 October. The spike ran on 2 October and E4 has not started, so the first results (plan: 7 October) move with it.

## What changed on this sheet after the review of 3 October

- The sentence that nobody knows which way any choice would move a result was wrong for entry 6, and is replaced by the list of outcome-aware entries.
- Entry 6 is now an open item (OI-08) with four candidate rules, the khwaeng question and the EK-04 warning. It was a reading to confirm.
- Entries 20 to 23 are new. Entry 20 was a value the agent had filled in. Entries 21 to 23 were listed as "corrections the agent will make" unless you objected; each is now a choice with its own empty slot in the protocol.
- Entry 1 prints the full rule text of option B and names its seven sub-rules. Entry 14 says which numbers were made up. Entry 18 states what class C needs and adds option C. Entry 12 quotes cut line 6 as written. Entry 15(c) has its own slots and option D.
- The road-class shares, bridge counts and hospital breakdown now come from the spike receipts, and each receipt compares its run with the one before it.

## What changed on this sheet after the owners answered (R12, 3 October 2026)

- Every recommended box is ticked, and each entry says where its answer was written in `planning_protocol_v1b.json` and whether its item closed.
- Entries 4, 6, 13 and 15 say that you gave no reason of your own. The protocol quotes the recommendation's reason instead and keeps each choice marked outcome-aware.
- Entry 15 records what the agent built from the decided rules, the result of the Phan district office check and the SE2-blind unit list. The request to Rachmania for the frame file became a request to review it.
- Entry 22's second question had no recommendation; the box records that nothing was changed.
- The readings section says that R12 approved them and that the signers mark them at signing.

## What changed on this sheet after the run of record (3 October 2026)

- "Where v1b stands" says that all 18 items are closed and v1b is `draft_for_signature`.
- Entries 19 to 22 say what the run of record measured and that their item is closed. Entry 19 reports the match rate, which is lower than the entry expected because OSM buildings are sparse around the corridor.
- "Needed from a person" asks the owners to accept or reject the compute window the agent declared, instead of declaring one.
