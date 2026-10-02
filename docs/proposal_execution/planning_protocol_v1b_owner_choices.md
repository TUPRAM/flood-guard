# Protocol v1b: the choices that are yours

For Putu and Rachmania. Written by an AI coding agent on 3 October 2026, after decision-log entry R11 (v1b approved in principle; the agent closes the engineering items and writes one proposal for each owner choice).

**Nothing on this sheet is decided.** Each entry gives a question, the options, the option the agent recommends and why. A recommendation is not a decision. Tick an option or write your own. The agent then writes your answer into `planning_protocol_v1b.json`, quotes it in the item's closure, and closes the item.

**"Sensitive"** means the choice can change a class, a headline or a confidence level for a real tambon. No FPPS, class or ensemble has been computed, so nobody knows which way any of these choices would move a result. Please answer them before anyone looks.

## Where v1b stands

- **Closed:** OI-08 (national anchors) and OI-11 (v1a hash).
- **Engineering done, waiting on you:** the E0 spike (OI-01, OI-03, OI-04, counts of OI-06), the closure regression (OI-05) and the SE2-blind district (OI-09). Results are in section 6 of `planning_protocol_v1_signing.md`.
- **Yours:** the 19 choices below. Choices 1 to 8 are the ones that matter most.

| # | Item | Question | Recommended | Sensitive |
|---|---|---|---|---|
| 1 | OI-02 | Which roads make the corridor to the three hospitals? | Buffer the whole fastest path | Yes |
| 2 | OI-15 | How many metres is "one pixel"? | 20 m everywhere | **Yes, high** |
| 3 | OI-10 | Which cell is the reference for class retention? | The default cell | **Yes, high** |
| 4 | OI-05 | Closure thresholds for residential, unclassified and motorway roads | 30 m, 30 m, 50 m | **Yes, high** |
| 5 | OI-05 | Is an edge delayed under the strict level? | Yes, with k = 2 | Yes |
| 6 | DR-B09 | Anchors: count each tambon once, or weight by residents? | Each tambon once (as filled in) | **Yes, high** |
| 7 | OI-16 | How do shelters enter a vehicle-only ensemble? | Walking, 30 min, pitch level | Yes |
| 8 | OI-06 | What is a "main-road entry"? | Nearest node on a trunk or primary road | Yes |
| 9 | OI-07 | Destinations for the critical-link ranking | Hospitals and main-road entry | Yes |
| 10 | OI-07 | Fix the ranking before signing, or in the first run receipt? | First run receipt | No |
| 11 | OI-18 | Class rule v2: three definitions (two numbers were made up) | See entry | Yes, secondary axis only |
| 12 | OI-13 | Formula for "2024-rescaled demand" | Rescale within each 1 km cell | Yes |
| 13 | OI-12 | Terrain / remoteness proxy: definition and anchor | Code definition, no anchor | Low |
| 14 | OI-14 | Flood-state levels for three detectors; A6′ threshold (Rachmania) | The proposals in the file | Moderate |
| 15 | OI-09 | pf-07 unit list and routing; SE2-blind tambons (Rachmania) | All 16 tambons; seat tambon and its neighbours | Yes for SE2 |
| 16 | OI-17 | Scenario S5: when is the node list fixed, and which class picks the tambons? | First run receipt; binding v1 class | Scenario only |
| 17 | OI-10 | k for scenario S3b | 3 per tambon | Scenario only |
| 18 | OI-10 | Selection rule for engine cell E3 | Smallest total raise | No |
| 19 | OI-06 | Match distance for corroborated shelters | 150 m | Low |

---

## 1. Which roads make the corridor to the three hospitals? (OI-02, Putu)

The plan says "3 km corridor buffers along the trunk and primary routes" to the Mae Chan, Chiang Saen and Mae Fa Luang hospitals. It does not say how a route is picked. The draft proposed: take the fastest vehicle path and buffer its trunk and primary segments.

**The spike shows that proposal cannot be signed.** The fastest road to Mae Fa Luang hospital is 31 km of secondary and tertiary road with no trunk or primary segment. Nothing is buffered, the hospital stays outside the corridor, and the schema refuses a file where the three named hospitals are not all in context.

- **A. Proposal as written** (trunk and primary segments only). Fails the plan's acceptance. 683 km², 57,727 edges.
- **B. Buffer the whole fastest path, whatever the road class.** Passes: all three hospitals in context, no-route share 0.075%. 827 km², 65,328 edges, 2.96 min to build.
- **C. Drop Mae Fa Luang as a named destination.** Keeps the plan's wording, but leaves three named hospitals and changes plan 1.1 and the acceptance list.

**Recommended: B.** It is the smallest change that meets the plan's own acceptance, it uses one rule for all three hospitals, and no road is picked by hand. The rule uses no flood input.

- **Downstream:** OI-01 and OI-03 close from the spike receipt. OI-04 and the counts of OI-06 follow from the E4 build. Plan 1.1's words "trunk and primary routes" become "fastest routes".
- **Sensitive:** yes. It decides which hospitals are destinations and how large the road graph is. Mae Fa Luang is 42 modelled minutes from the edge of AOI-02, so it matters for "any route" and the 60-minute threshold more than for 30 minutes.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 2. How many metres is "one pixel"? (OI-15, Putu)

The flood-state axis grows and shrinks each flood input by one pixel. The plan gives 20 m for shrinking only. It gives nothing for growing, and nothing for vector agency products, which have no pixel.

- **A. 20 m for shrinking and growing, for every input.** A vector product gets a 20 m buffer inwards or outwards.
- **B. Each product's own pixel** (for example 10 m for a Sentinel-1 agency layer, 20 m for the team's grid).
- **C. 20 m for rasters, 10 m for vector products.**

**Recommended: A.** 20 m is the only distance in the plan (section 5 item 11, axis 1) and it is the team's grid. One distance keeps the two sides symmetric and the lanes comparable.

- **Downstream:** the three flood-state levels of every ensemble cell, and confidence condition C4 in v1a.
- **Sensitive: yes, high.** C4 asks whether exposure moves by more than 15 points between the grown and the shrunk input. If it does, the unit is low confidence and is forced to class E. A larger distance makes more units low.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 3. Which cell is the reference for class retention? (OI-10, Putu with Rachmania)

A class is headlined only if at least 60% of the ensemble cells keep it. "Keep" needs a reference class, and the plan names none.

- **A. The default cell:** flood input as provided, central closure, public facilities, WorldPop 2020, P10/P90 anchors, default weights. Retention is the share of the 540 cells with the same v1 class.
- **B. The most common class across the cells.** No reference cell is needed, and retention is never below the largest share.
- **C. The cell with the median FPPS.**

**Recommended: A.** The plan's words are "% of runs keeping the class", and the class a unit is reported with is the one from the default settings signed in D4.

- **Downstream:** the headline rule, the demo-tambon rule in v1a, and scenario S5 (entry 16).
- **Sensitive: yes, high.** It decides whether a class is shown or replaced by "unstable: verify".
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 4. Closure thresholds for the three road classes the plan leaves out (OI-05, Putu)

Under the central level a road closes when the flooded length reaches a threshold: 50 m for trunk, primary and secondary, 30 m for tertiary and local. The plan gives no threshold for motorway, residential and unclassified roads. In the spike context **those classes are 60% of all edges** (residential 50%, unclassified 10%, motorway none).

- **A. Motorway 50 m; residential 30 m; unclassified 30 m.**
- **B. All three 30 m.**
- **C. All three 50 m.**

**Recommended: A.** It follows the grouping already in `road_risk.py`, where residential and unclassified share the factor of local roads and motorway shares the factor of trunk and primary. A and B give the same result here, because the corridor has no motorway.

- **Downstream:** every central-level closure, and so access loss, road criticality and classes.
- **Sensitive: yes, high.** The v1a disclosure (EK-13) already records that 20 m and 50 m rules were tried on Hat Yai.
- **In the draft:** a proposal, which is option A. The new `closure_rules.py` refuses to run the central level on these classes until you answer.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 5. Is an edge delayed under the strict level? (OI-05, Putu)

The plan says strict means "fraction ≥ 0.5 only", gives the delay formula for the central level only, and lists delay factors k = 2 / 4 / 6 beside strict / central / permissive.

- **A. Yes.** An edge with at least 20 m flooded and less than half its length flooded is slowed by (1 + 2 × f).
- **B. No.** Under strict an edge is either closed or untouched. Then k = 2 never acts, just as k = 6 never acts under permissive.

**Recommended: A.** Reading DR-B01 pairs k = 2 with strict; with B that pairing would mean nothing. This is a judgement: the plan's text supports either.

- **Downstream:** travel times under the strict level, so 15, 30 and 60 minute access in a third of the ensemble cells.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ other: ________

## 6. National anchors: count each tambon once, or weight by residents? (DR-B09, both)

OI-08 is closed with the anchors P5 0.313, P10 0.351, P75 0.454, P90 0.478, P95 0.494. The plan says "national tambon percentiles" and names no rule. The agent used the two proposals that were already in the file. This is the one value it filled in that rests on a reading, so it is a new reading, DR-B09, for you to confirm at signing.

- **A. Each of the 7,425 units counts once** (as filled in). No unit has fewer than 100 residents, so that part of the rule changes nothing.
- **B. Weight each unit by its residents.** P10 becomes 0.258 and P90 becomes 0.458, because large city units have few children and few older adults.

**Recommended: A.** It is what "percentile across tambons" says.

- **Downstream:** the vulnerability component of every unit in every case, and trigger A of class rule v2 (P75).
- **Sensitive: yes, high.** Under B the lower anchor drops by 9 points, which raises the component for most units. Note also that P10 and P90 are only 12.6 points apart: 1.3 points of dependent share move the component by 10 of its 100 points.
- **In the draft:** filled in as A, marked DR-B09.

Your answer: ☐ confirm A ☐ amend to B ☐ other: ________

## 7. How do DDPM shelters enter a vehicle-only ensemble? (OI-16, both)

The ensemble runs in vehicle mode. Two of its three facility levels add DDPM shelters, whose access is defined as walking, 30 minutes, and whose data may only be shown at pitch level (D8b).

- **A.** Inside the ensemble the shelter service is walking, 30 minutes; hospital and main-road entry stay vehicle. Cells that use DDPM data are pitch level. For a public overlay, retention is counted over the 180 cells of the public facility set only, and the overlay says so.
- **B.** Shelters by vehicle, 30 minutes, inside the ensemble.

**Recommended: A.** It keeps the plan's own definition (section 3.4: "Pitch level: adds DDPM located shelter (walking, 30 min)") and D8b.

- **Downstream:** the access-gap component in 360 of the 540 cells; what a public overlay may report.
- **Sensitive:** yes. A tambon can be headlined in the pitch overlay and "unstable" in the public one, or the reverse, because they count different cells.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ other: ________

## 8. What is a "main-road entry"? (OI-06, Putu)

Main-road entry is one of the two public services (vehicle, 15 minutes). The plan does not say where the entry is.

- **A. The nearest node on a trunk or primary road, links included, inside the routing context.**
- **B. The same, with secondary roads added.**
- **C. Trunk roads only** (Highway 1).

**Recommended: A.** The file already names the source as the "OSM trunk and primary network". In the spike context trunk and primary are 3% of edges and secondary 6%, so B would make a main road much easier to reach.

- **Downstream:** the access-gap and road-criticality components at the public level; the destination set of entry 9.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 9. Destinations for the critical-link ranking (OI-07, Putu; Rachmania reviews)

Links are ranked by how many residents' baseline routes use them. Routes to what?

- **A. The public set: OSM hospitals and main-road entry.**
- **B. Hospitals only.**
- **C. Every listed facility, DDPM shelters included.**

**Recommended: A.** It matches the road-criticality definition in plan 3.4 ("a baseline route to any hospital or main road") and keeps the ranking free of pitch-level DDPM data.

- **Downstream:** the top 20 links, scenarios S3 and S3b, and trigger B of class rule v2.
- **Sensitive:** yes.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 10. Fix the ranking before signing, or in the first run receipt? (OI-07, Putu)

Plan 6.3 wants links fixed before any scoring. Plan row G7b schedules the ranking (E6) after v1b.

- **A. Sign with the rule. The ranking's SHA-256 goes into the receipt of the first run, before any scoring.**
- **B. Run E6 first and record the ranking's SHA-256 in v1b.** Signing then waits for the E4 build and E6.

**Recommended: A.** The ranking uses no flood input, so the rule fixes it. Both options satisfy plan 6.3.

- **Sensitive:** no, as long as the rule is fixed.
- **In the draft:** both options are described; none is chosen.

Your answer: ☐ A ☐ B

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

Your answers: (a) ☐ A ☐ B   (b) ☐ A ☐ B   (c) ☐ A ☐ B ☐ C   other: ________

## 12. Formula for "2024-rescaled demand" (OI-13, both)

The population axis compares WorldPop 2020 with "2024-rescaled demand". The plan says only "2024/2020 1 km rescale".

- **A.** Inside each 1 km cell of the 2024 grid, multiply every 2020 100 m count by (2024 cell total ÷ sum of the 2020 counts in the cell). Where 2020 has nobody, nothing is added, and the 2024 residents left out are reported as unallocated.
- **B.** One ratio per tambon (2024 total ÷ 2020 total).
- **C.** Cut the axis now (cut line 6 would cut it anyway; 540 cells become 270).

**Recommended: A.** It matches the plan's words and the way `bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells.

- **Sensitive:** yes. It changes exposure shares and every access denominator in half the cells.
- **In the draft:** a proposal, which is option A.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 13. Terrain / remoteness proxy: definition and anchor (OI-12, both)

The proxy replaces age-based vulnerability in one sensitivity run on case O1 and in scenario S8. The plan defines neither the proxy nor its anchor.

- **A.** The definition in `mae_sai_context.py` (a cell counts when its slope is at least 8 degrees or the nearest drivable road is at least 750 m away), and **no anchor**: the component is 100 × the share of the unit's residents in such cells.
- **B.** The same definition with an anchor of 0.25. The replay used 0.25 with its results in view (disclosure items EK-R1, EK-R5).
- **C.** Drop the proxy. S8 and the sensitivity run are reported as "not attempted".

**Recommended: A.** Plan 3.4 says the national anchors exist to replace "the unexplained 0.25/0.30", and D4 made exposure share-only for the same reason.

- **Sensitive:** low. O1 rows are tier T2 and are forced to E unless a detector passes the skill bar. It decides what S8 shows.
- **In the draft:** the definition is proposed; no anchor is proposed.

Your answer: ☐ A ☐ B ☐ C ☐ other: ________

## 14. Flood-state levels for three detectors, and the A6′ threshold (OI-14, Rachmania; Putu confirms)

The plan defines the three levels for M1-v2 and the legacy mask only.

| Input | Proposal in the file |
|---|---|
| M1-literal | Otsu threshold −1 / 0 / +1 dB |
| UN-SPIDER reproduction | shrink / as provided / grow by one pixel; the ratio 1.25 is not tuned |
| A6′ classifier | calibrated probability 0.4 / 0.5 / 0.6 |
| A6′ extent threshold | 0.5 on the calibrated probability, set on GEOID development tiles before any Mae Sai run |

- **A. Accept all four.**
- **B. Change one or more** (write which).

**Recommended: A.** M1-literal mirrors M1-v2's ±1 dB. The plan calls the UN-SPIDER ratio "untuned", so its levels have to be spatial. 0.5 is the natural cut of a calibrated probability and needs no tuning. Whatever you choose for A6′ must be chosen with no Mae Sai result in view.

- **Sensitive:** moderate. O1 is forced to E unless a detector passes the skill bar; these levels move the ensemble spread, the would-be classes and the divergence matrix.

Your answer: ☐ A ☐ B: ________

## 15. The pf-07 frame and the SE2-blind tambons (OI-09, Rachmania)

**(a) Unit list of pf-07 (case SE2).**
- **A. All 16 tambons of Mueang Chiang Rai district.**
- **B. A hand list of the tambons along the Kok River** (Rim Kok, Rop Wiang, Ban Du and others), with the rule that picked them written down.

Recommended: A. SE2 is already disclosed as chosen with the outcome in view. A list picked tambon by tambon would add to that; a whole district does not.

**(b) Routing geometry and hospitals of SE2.** Recommended: the union of the pf-07 tambons with a 3 km buffer, clipped to Thailand; every OSM hospital inside it. The plan says nothing here, so please write your own if you disagree.

**(c) Which tambons of the blind district?** The population rule picks **Phan** (TH5705); Mae Chan is second, 5.3% behind. The plan says "amphoe-seat tambons" and gives no rule for them.
- **A. The tambon that holds the district office.** One unit. The agent expects this to be Mueang Phan (TH570513) but has not checked it against a source; please confirm.
- **B. That tambon and every tambon that touches it.**
- **C. All 15 tambons of Phan.**

Recommended: B. It is the closest reading of the plan's plural that still gives more than one unit. It has no other basis.

**Still needed from Rachmania, whatever you choose:** the frame file `resources/planning_frames/pf-07_mueang_chiang_rai.geojson`.

- **Sensitive:** yes for SE2 (which units can show a class). SE2-blind is blind by rule, not by ignorance: flooded shares for all 124 Chiang Rai tambons were seen in exploration (EK-09).

Your answers: (a) ☐ A ☐ B   (b) ☐ as recommended ☐ other: ________   (c) ☐ A ☐ B ☐ C

## 16. Scenario S5 (OI-17, Putu)

S5 adds a temporary shelter at a pre-declared node in each tambon that is class A or B.

**(a) When is the node list fixed?** ☐ **A. In the first run receipt, before any scoring** (recommended, for the same reason as entry 10) ☐ B. In v1b, after the E4 build.

**(b) Which class decides "A or B"?** ☐ **A. The binding v1 scenario class of the SE1 reference cell** (recommended; it follows D6 and entry 3) ☐ B. The v2 class ☐ C. A or B in any ensemble cell.

- **Sensitive:** scenario cells only. Cut line 5 drops S5 first.

## 17. k for scenario S3b (OI-10, Putu with Rachmania)

S3b fails "the top-k bridge edges". ☐ **A. 3 per tambon**, to match S3 (recommended) ☐ B. Another number: ________

- **Sensitive:** scenario cells only.

## 18. Selection rule for engine cell E3 (OI-10, Putu with Rachmania)

E3 changes one real O2 row as little as possible to show a counterfactual class C, and labels it synthetic.

- **A. (proposal)** Take the unit with the highest exposure and raise the one component that is furthest below the class C thresholds.
- **B.** Take the unit that needs the smallest total raise to meet class C (exposure ≥ 65 and access gap ≥ 50 in `scoring.py`), raise only the components that fall short, to the threshold; ties go to the lower unit ID.

**Recommended: B.** Class C needs two components. If both are short, A raises only one and never reaches C.

- **Sensitive:** no. The row is labelled synthetic and counted in the ENG column.

Your answer: ☐ A ☐ B ☐ other: ________

## 19. Match distance for corroborated shelters (OI-06, Putu)

A DDPM shelter is "corroborated" when it matches an OSM building or amenity. The plan gives 150 m for hospitals and nothing for shelters.

- **A. 150 m, as for hospitals.**
- **B. 50 m.**

**Recommended: A**, because it is the only distance the plan states. Be aware that in a town almost every point is within 150 m of some building, so this level may differ little from "all listed". The E4 build will report the match rate. Cut line 8 drops this level first.

- **Sensitive:** low.

Your answer: ☐ A ☐ B ☐ other: ________

---

## Readings to confirm or amend at signing

These are not new questions. Each is a value the drafting agent filled in where the plan is silent; the file cannot be signed until each is marked `confirmed` or `amended`. The engineering runs bear on three of them.

| ID | Reading | What the runs add |
|---|---|---|
| DR-B01 | k = 2 / 4 / 6 paired with strict / central / permissive (540 cells) | See entry 5 |
| DR-B02 | Edge = straight node-to-node segment; "any intersection" = more than 1e-6 m | The regression matched the finals edge lists exactly under this reading |
| DR-B03 | Critical links weighted by WorldPop 2020 residents; ties on edge ID | Nothing new |
| DR-B04 | 1 km cells assigned to tambons by projected-area fraction | Used for the anchors; 99.6% of the raster's residents fall inside a tambon |
| DR-B05 | Terrain proxy run one at a time, outside the 540 cells | Nothing new |
| DR-B06 | A link belongs to the tambon that holds its midpoint | Nothing new |
| DR-B07 | The critical-link ranking and the national percentiles may run before v1b | The percentiles were run (plan 3.4 also asks for them in v1b). The ranking was not run |
| DR-B08 | Scenario S8 is based on O1 | Nothing new |
| DR-B09 | Anchor unit set and percentile rule | See entry 6 |

## Three corrections the agent will make when the related item closes

Say so if you object to any of them.

1. **Demand area.** The file says the demand area is the union of the eight tambons. That union is 214 m² larger than AOI-02, and the context builder refuses it. The spike used the union clipped to AOI-02, which is what the declared tolerance (coverage ≥ 0.999) already implies. The wording of `context_call.aoi_geometry` will say "clipped to AOI-02".
2. **Hospital count.** The plan asks for at least 4 hospitals. The count is of OSM objects. With the whole-path corridor there are 6: four named hospitals (Mae Sai, Mae Chan, Chiang Saen, Mae Fa Luang), a second OSM object for Mae Fa Luang (a node inside the same site) and one unnamed object tagged as a hospital. The record will state that breakdown.
3. **Culverts.** The closure rule names `culvert=*`. The context builder carries the bridge and tunnel tags only, and the plan says the builder is unchanged. The central level will see `bridge=yes` (192 edges in the spike) and `tunnel=culvert` (none); the file will say that `culvert=*` is not read.

## Needed from a person, not a choice

- **Rachmania:** the pf-07 frame file (entry 15), and the statement left open at the v1a signing on whether any M1-v2 tuning on GEOID tiles has been run.
- **Putu:** review of the four new modules (`normalisation.py`, `closure_rules.py`, `grade_join.py`, `ddpm_shelters.py`), and a declared compute window for the E4 build. The spike was timed with other sessions running.
- **Either owner:** approval of downloads DL-1 and DL-2 before any v2 class D or JRC note. Neither blocks signing.
- **A human:** bring `claude/planning-protocol-v1` into `codex/thai-event-selection` with a merge commit, never a squash, before v1b is signed.

## Where the plan says two things

Each of these is handled above or already marked as a reading. They are listed so that nobody is surprised later.

1. **Corridor.** Plan 1.1 puts the corridor along "trunk and primary routes" to three hospitals and requires all three in context. The road to Mae Fa Luang has no trunk or primary segment (entry 1).
2. **Demand area.** Plan 3.1 takes the eight-tambon union as the demand area and AOI-02 as the base of the routing polygon; the union is not inside AOI-02 (correction 1).
3. **When links are fixed.** Row G7b makes v1b depend on E0 and E4 only and schedules the ranking (E6) after v1b; section 6.3 wants links and nodes fixed before any scoring (entries 10 and 16).
4. **Delay factors.** Section 5 item 11 lists k = 2 / 4 / 6 for the three levels; item 2 states a delay for the central level only, and under permissive no delay can act (entry 5, DR-B01).
5. **Terrain proxy.** It is listed inside axis 4, but 540 cells leave no room for it (DR-B05); section 6.2 bases S8 on O2 and section 3.4 restricts the proxy to O1 (DR-B08).
6. **SE2-blind.** It is to be "computed before any overlay", but flooded shares for every Chiang Rai tambon were already seen (EK-09). The selection rule itself uses population only. Also, "all 124 Chiang Rai tambons inside the 4009 analysis extent" is the whole province: Chiang Rai has 124 tambons.
7. **Culverts.** The closure rule reads a tag that the unchanged context builder does not carry (correction 3).
8. **Schedule.** The plan had the E0 spike on 26–27 September, the E4 build done by 1 October and v1b recorded on 2 October. The spike ran on 2 October and E4 has not started, so the first results (plan: 7 October) move with it.
