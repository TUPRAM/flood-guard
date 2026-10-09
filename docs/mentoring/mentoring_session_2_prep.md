# Mentoring Session II: preparation pack

- Written: 7 October 2026, from the repository at `master` `c21694e` plus the
  THEOS-2 cross-check of the same day.
- For: Rachmania, Putu and Callixta. Drafted by the AI coding agent; the team
  decides what is said.
- Sources: the organisers' "Mentoring Session II: Management and Mentor Guide"
  (v2), Davide Nitti's Session I slides of 16 September 2026, the submitted
  proposal, and the files named in each row.
- Every figure below is a planning figure from a model or a scenario. None is
  an observation of a flood, and FloodGuard is not an official warning system.

The guide asks each team to arrive with **the latest output, draft visuals and
a five-minute draft pitch**. Sections 3 to 5 are those three things.

**The session is on 16 October 2026** (decision log R27). What the team has to
check before then is listed on the team page `/studio/validation-check/`, where
each member records accept, change or reject (`docs/validation/README.md`).

## 1. Where the project stands, against the three judging criteria

| Criterion | What we can show today | What is thin |
|---|---|---|
| Geo-intelligence quality (40%) | A scored case on eight real tambons (case SE1, the 2024 season-envelope scenario). It gives a result a flood map alone does not: **Ko Chang ranks above Mae Sai town because of lost road access, not flooded area.** An hour-by-hour replay of September 2024 with shelters, access and reported depths. A shelter-capacity gap. | The roads that cut Ko Chang off are now listed with a map (`docs/ko_chang_road_check.md`, 8 October), but nobody who knows the place has looked at them. The equity gap is not computed by age. No practitioner has read the result. |
| GeoAI methodology (35%) | A documented pipeline with receipts and hashes; three radar methods tested and reported as they came out, including failures; a diagnosis of why they failed at Mae Sai; a 90-run uncertainty ensemble; a first check against THEOS-2. Since 8 October: a table of how the result changes with the flood input (`docs/flood_input_comparison.md`), and the proposal's method 2 run once, a Random Forest and boosted trees beside a one-feature baseline, fitted on Mae Sai and tested on three districts it never saw (`docs/flood_susceptibility_model.md`). Both wait for the team's word (items V-16, V-18). | The trained model is a screening layer and feeds no score: on unseen districts the simplest model held and the trees did not beat it. The radar candidates feed nothing. No model is fitted to a dated flood yet; that waits for the THEOS-2 scene or the UNOSAT data. |
| Communication and impact (25%) | Three views of one evidence base, bilingual, offline; a policy page; an exercise replay for coordinators; a demo video. | No five-minute pitch. The policy page still leads with an old example. Pages carry more caveats than findings. No stated call to action. |

## 2. Session I follow-up: each question the mentor asked, and the answer today

The mentor said a written summary would follow Session I. It is not in the
repository. **If the team has it, check this table against it before the
session.**

| Session I question | Answer today | Evidence | Still open |
|---|---|---|---|
| Which stages work together on one real event? | Flood input, exposure, road closure, access loss, age share, score, class and uncertainty run end to end for Mae Sai on the UNOSAT/GISTDA season layer (case SE1). | `outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json`; `/command/` | Our own radar is not in that chain (case O1 is not issued). |
| Is the Mae Sai evaluation plan fixed, with promotion criteria? | Yes. Protocols v1a and v1b are signed and hashed (2 and 3 October). | `docs/proposal_execution/planning_protocol_v1a.json`, `…v1b.json`, `RECEIPTS.jsonl` | — |
| Which of the eight validation gates are done? | None of the human-review gates. The team chose an automated track. No qualified reference for Mae Sai exists. | `docs/proposal_execution/STATUS.md`, `UNRESOLVED.md` | Say this plainly; it is the main limit. |
| Progress per flood method? | Adaptive Otsu (M2): declined all 81 windows; diagnosed. UN-SPIDER practice: 9.4 km². M1-literal: 114.5 km² (over-flags). M1-v2: 3.0 km², no answer for 77% of cells. Skill bar not met. | `outputs/planning_v1/radar_o1_mae_sai_v1.json`; `docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md` | Random Forest / XGBoost and U-Net: not run on labelled events. |
| What limits evaluation? | No Sentinel-1 pass between 6 and 15 September 2024; the pass used came 3.8 days after the modelled peak. No reference with reuse rights. | `outputs/a1_diagnosis/sentinel1_pass_gap.json` | — |
| Is there a labelled training set? How many events? | No. One foreign labelled sample (GEOID-Flood) was used as a benchmark only: M1-v2 IoU 0.41, not distinguishable from the 0.40 bar, 68% of cells without an answer. | `outputs/geoid_m1_benchmark_v2_summary.json` | — |
| How is THEOS-2 used? Does it include flood-map validation? | **New.** Yes, on one sample scene. See section 6. | `docs/theos2_radar_cross_check.md` | No THEOS-2 scene over Mae Sai or Hat Yai has been delivered. |
| Road disruption tested against independent passability information? | **New.** Yes, on the same THEOS-2 scene: the closure rule at its central level agrees with roads seen under water for about four in five. | same | One scene, 52 flooded road edges. Not Mae Sai. |
| Speeds, penalties and thresholds fixed and documented? | Yes, in protocol v1b (closure rule v1, three levels; hospital 30 min, main road 15 min). | `planning_protocol_v1b.json` | — |
| Facility and capacity data? | Hospitals from OpenStreetMap. Shelters: 19 reported in 2024 news, 15 located; DDPM list held locally. Capacity is estimated from building footprints, not listed. 2SFCA is not run. | `outputs/mae_sai_reported_shelters_2024.json`; replay `r4` | A local contact for the shelter sheet. |
| Age-resolved population in the Mae Sai context? | Yes, WorldPop 2024 at 1 km feeds the vulnerability component. | `outputs/planning_v1/age_exposure_mae_sai_v1.json` | **The age mix is the same in almost every cell of the district** (0.4055 in five of eight tambons). It cannot show which tambon has more older people. |
| Which Planning View values are measured, which illustrative? | Every value is modelled. The page labels the scenario, the confidence and "stability not evaluated". | `/command/` | — |
| Planning View tested with planners? | No. | — | **Open since the proposal timeline (late September).** |
| What did sensitivity show? | Ko Chang keeps class B in 70 of 90 runs and is D in the others. Half of the 180 runs a public result needs were made. | `outputs/planning_v1/e10_uncertainty_ensemble_se1_mae_sai.json` | The other 90 runs. |
| Can one Mae Sai run be reproduced from its inputs? | Yes. Each stage has `--verify`; the result file names both protocol hashes and its input hashes. | `outputs/planning_v1/README.md` | A run on a second machine was never made. |
| Hat Yai? | A candidate case exists (uncalibrated radar change, closure sensitivity). No reference, no score. | `docs/proposal_execution/hat_yai_transfer.md` | Say "stretch, not completed". |
| Lower Chao Phraya / Bangkok? | Baseline access context for two areas. No flood input. | evidence library | Say "roadmap only". |

## 3. Session II, segment by segment

Times are those of the guide for a 120-minute slot.

### 0:00 to 0:10, welcome and framing

One sentence from the team: "Since Session I we fixed the evaluation plan,
produced the first scored case on real tambons, and checked our radar and our
road rule against THEOS-2. We want your help on the pitch and on what a
district office would do with the result."

### 0:10 to 0:25, follow-up on technical mentoring (Putu, Rachmania)

Show three things, five minutes each. Use section 2 as the backup table.

1. **Pipeline status in one picture**: the twelve stages of proposal figure 4,
   each marked "runs on Mae Sai", "runs, low confidence" or "not done".
2. **GeoAI decisions**: why the decision chain reads the UNOSAT/GISTDA layer
   and not our own radar. The Sentinel-1 gap, the three methods, the skill bar
   not met, and the THEOS-2 check (section 6).
3. **Uncertainty**: what the page says when evidence is weak (class E for low
   confidence; "stability not evaluated"; 70 of 90).

Blockers to raise, as questions:

- Is a supervised model (Random Forest or XGBoost on labelled events) worth
  two days before the freeze, or is "tested, reported, not promoted" the
  stronger position? See section 7.
- Can the THEOS-2 scene of 16 September 2024 over Mae Sai be released to us?
- The age data cannot separate tambons. Is the honest statement enough, or is
  there a Thai source at village level we may use?

### 0:25 to 0:40, team output walkthrough: pixel, insight, policy, impact (Callixta drives, Rachmania speaks)

One path, no detours. Rehearse it with the links.

1. **Pixel** (2 min). Studio replay, `/studio/cases/mae-sai-2024/`: the
   flood rising over Mae Sai hour by hour, with the satellite images and the
   agency season layer beside the model.
2. **Insight** (5 min). Planning, `/command/`: the eight tambons. Read the
   table in section 4 aloud for two rows only, Mae Sai and Ko Chang.
3. **Policy** (4 min). The case card of Ko Chang: class B, "keep routes open",
   the three checks for a team. Then the shelter numbers of the replay.
4. **Impact** (4 min). Public view on a phone, Thai first. Then the policy
   page table of who decides what.

### 0:40 to 1:00, policy translation workshop

Bring section 5 as a one-page table and ask the mentors to attack it. Three
questions to put to them:

1. Who would own this in a province: the DDPM provincial office, the district,
   or the local administrative organisation?
2. Is "keep routes open" for Ko Chang something a district can act on before
   the season, and what would the action be called in their own plan?
3. What would make an office distrust the result at first sight?

### 1:00 to 1:20, visualisation review

Bring the visuals of section 6.1, each on one slide, each with one sentence
that says what the viewer should conclude. Ask for one thing to remove from
each.

### 1:25 to 1:55, pitch practice

Section 4. One speaker for the first round. Time it. In the second round
change only the opening and the call to action.

### 1:55 to 2:00, wrap-up

Write down, for each action: what, who, by when, and whether it needs anyone
outside the team.

## 4. The spatial insight, and a five-minute pitch

### 4.1 The result to lead with

Case SE1: the area UNOSAT and GISTDA mapped as water at any time in the 2024
season, treated as flooded at once. A scenario, not a day of 2024.

| Tambon | Land flooded | Residents inside the extent | Lose the hospital within 30 min | Lose every route | Score | Class |
|---|---:|---:|---:|---:|---:|---|
| Ko Chang | 47% | 2,500 of 6,700 | all 5,710 who had it | all 5,970 who had one | 78 | B, keep routes open |
| Mae Sai | 58% | 10,100 of 17,900 | 12,070 of 17,450 | 11,610 of 17,450 | 71 | D |
| Si Mueang Chum | 52% | 3,050 of 7,160 | 2,870 of 6,530 | 2,900 of 6,560 | 59 | D |
| Ban Dai | 31% | 960 of 5,040 | 2,650 of 3,790 | 360 of 4,010 | 50 | D |
| Pong Pha, Pong Ngam, Wiang Phang Kham, Huai Khrai | 0 to 15% | under 10% | not listed here | under 9% | 5 to 32 | E |

Source: `apps/web/public/planning-overlays/mae-sai-2024/se1.json`, counts
rounded here. Residents are WorldPop modelled counts. Closures are modelled
from the flood layer.

**The sentence.** A flood map puts Mae Sai town first: most water, most people
in it. FloodGuard puts Ko Chang first, because in the scenario every resident
there who has a road to a hospital or a main road loses it.

**Two cautions to keep.** (1) Mae Sai town is class D under the signed rule
although about 12,000 of its residents lose hospital access in the model. A
judge who knows 2024 will ask. The answer: the class names a type of action,
not a size of harm; the score beside it is 71, the second highest; and the
proposal's own class wording (section 5.2) is run as a second reading that is
not finished. Decide before the final whether to finish it (section 7).
(2) Ko Chang's class rests on modelled closures. The roads are listed on a
desk sheet (`docs/ko_chang_road_check.md`): one unnamed road of 1.24 km in the
next tambon, Si Mueang Chum, carries 56% of the result, and only five road
pieces in Ko Chang carry a bridge tag. Nobody has looked at them on the ground
or on an image.

**A second finding, from the replay.** At the modelled peak the homes of about
14,200 residents are in water. The eight shelter sites of the default plan
have 7,580 of them within walking reach and room for roughly 500 to 1,050
(estimated from building footprints). Source: decision log, follow-up 7.

### 4.2 Draft pitch, five minutes, for a policy audience

About 650 words. Screens are in brackets.

> **[Mae Sai, September 2024, satellite image]**
> In September 2024 the Sai River flooded Mae Sai. Thailand had the satellite
> maps within days. GISTDA and UNOSAT mapped the water. But a map of water
> does not tell a district officer which village is cut off, or where to send
> the one boat he has.
>
> **[FloodGuard: one line]**
> We are TeamBits. FloodGuard takes the flood map that already exists and
> answers the next question: who loses access, and where do you act first?
>
> **[The eight tambons, two rows highlighted]**
> Here is what it found for Mae Sai district, using the area UNOSAT and GISTDA
> mapped as flooded in the 2024 season. Mae Sai town has the most water and
> the most people in it: about ten thousand. Any flood map puts it first.
>
> FloodGuard puts Ko Chang first. Ko Chang has a quarter as many people in the
> water. But when we close the roads that the flood crosses, every resident of
> Ko Chang who had a road out loses it. About six thousand people, none of
> them with a way to a hospital or a main road by vehicle. That is not visible on a flood map.
> It is visible when you connect the flood to the road network and to where
> people live.
>
> **[Ko Chang case card: class B]**
> So the tool does not say "Ko Chang is flooded". It says "keep the routes to
> Ko Chang open": check those roads before the season, decide where a boat or
> a high vehicle waits, agree who calls it.
>
> **[Shelter numbers]**
> A second finding. At the peak of our reconstruction, about fourteen thousand
> residents have water at home. The eight shelter sites of the plan have room
> for about a thousand at most: fewer than one in thirteen. That is a planning
> number a local administration can act on in the dry season.
>
> **[Pipeline in four boxes: flood map, roads and people, access loss, action]**
> How does it work? Four steps. A flood extent, from an agency or from radar.
> Open data on roads, hospitals and population. A routing model that compares
> travel before and after. And a published score with five parts that anyone
> can re-weight.
>
> **[What we tested, honestly]**
> We tested our own radar detection and we report what we found. At Mae Sai
> the satellite passed almost four days after the peak, and our three methods
> did not meet our own bar. So for decisions the system uses the agency map
> and marks our own radar as low confidence. Low confidence can never raise an
> alarm in FloodGuard: it becomes "monitor and verify".
>
> Then we used the THEOS-2 imagery GISTDA gave us. On a flood scene at half a
> metre we could see which roads were under water. Our road rule agreed with
> the image for four roads in five. Our 10-metre radar could not tell which
> road was flooded. That is the case for THEOS-2 in this chain: it sees the
> road.
>
> **[What it is not]**
> This is a planning tool. It is not a warning system and it does not replace
> DDPM or TMD. The Ko Chang result is a scenario and its roads still need a
> check on the ground.
>
> **[Call to action: three lines]**
> We ask for three things. From the DDPM office in Chiang Rai: one afternoon
> to check the Ko Chang roads with us before the next season. From GISTDA:
> the THEOS-2 scene of 16 September 2024 over Mae Sai, taken four hours after
> the radar pass, so we can repeat the road check on the real event. And from
> any province that wants it: a boundary, a road network and a population
> grid are all it takes to run this for your district. The code is open.
>
> A flood map shows where the water is. FloodGuard shows who it cuts off.
> Thank you.

Rules for whoever speaks: say "scenario" once per figure, not in every
sentence. Round every number. Never say "real-time", "validated" or
"accurate".

## 5. Policy translation table

| Who | Decision | What FloodGuard gives | So what, in Mae Sai |
|---|---|---|---|
| DDPM provincial office, district chief | Where to place boats, vehicles and teams before the season | Tambons by class and score, with the reason | Ko Chang: plan for loss of all road access, not only for water |
| Local administrative organisation | Which shelters to open and how many more are needed | Residents with water at home against shelter room within walking reach | Room for 500 to 1,050 of about 14,200 at the modelled peak with the eight default sites |
| Department of Highways, Rural Roads | Which links to inspect, raise or keep clear | The closed links in the scenario, ranked by residents who depend on them | A short list for a field check (not yet produced as a map) |
| Ministry of Public Health, hospital | Who loses the hospital within 30 minutes | Count per tambon, before and after | About 12,000 residents of Mae Sai town in the scenario |
| GISTDA | How a flood product becomes a decision product | A layer that reads GISTDA extents and returns access loss; a use for THEOS-2 that radar cannot fill | The road check of section 6 |
| ONWR, planners | Where repeated flooding and access loss coincide | Class D tambons with their scores | Mae Sai, Si Mueang Chum, Ban Dai |

Not claimed: a feed into Cell Broadcast. The proposal names it as an ambition.
Nothing was built or agreed. If asked, say it is a later step that belongs to
DDPM.

## 6. THEOS-2: what was done, and what to ask for

**Until 7 October** THEOS-2 was in no result: a metadata inventory and three
thumbnails. None of the sample scenes covers Mae Sai or Hat Yai. A request to
GISTDA for Mae Sai scenes was drafted on 17 September and nothing was
delivered.

**Done on 7 October**: `docs/theos2_radar_cross_check.md`. One "Disaster"
sample (Sukhothai, 30 July 2025, 0.5 m, a 9 km² chip) shows a real flood.
Sentinel-1 passed 44 hours later. A validation tile, not a new study area.

| Question | Result |
|---|---|
| Where the radar flags water, is it water on THEOS-2? | Mostly: 61 to 76% |
| How much of the THEOS-2 water does the radar flag? | 22 to 50% |
| Closure rule, central level, given the THEOS-2 extent: closures that are roads under water | 82% (41 of 50) |
| The same with a radar candidate as the extent | 5 to 16% |

Agreement between two sensors 44 hours apart; not accuracy.

**Ask at the session** (a GISTDA facilitator may attend):

1. The THEOS-2 scene `SC_T2V_202409160336066_VXB_E100N20_000640`, 16 September
   2024, 03:36 UTC, 21% cloud, over Mae Sai. It was taken 4 h 20 min after the
   Sentinel-1 pass of the project. With it the same check runs on the study
   event.
2. Written terms for the sample imagery: may a reduced overview picture and
   derived figures be shown in the final pitch?

### 6.1 Visuals to bring

| Visual | Where | State |
|---|---|---|
| The eight tambons with class and score | `/command/` | Live. Needs one headline sentence on the page. |
| Hour-by-hour replay | `/studio/cases/mae-sai-2024/` | Live. Demo video in `docs/demo/`. |
| Ko Chang case card with its three checks | `/command/` | Live. The checklist is a team draft. |
| Shelter room against need | replay, shelter panel | Live. |
| THEOS-2 against radar | `docs/mentoring/visuals/theos2_check_slide.png` (made by `scripts/build_theos2_slide.py` from the committed figure and result) | Slide drawn on 8 October, 16:9: three panels and the three figures. It shows a reduced picture of the sample image; the question to GISTDA on the terms for showing it (section 6) is still open. |
| Pipeline in four boxes | `docs/mentoring/visuals/pipeline_four_boxes.svg` | Drawn on 8 October, 16:9. Opens in a browser; drag it onto a slide. |
| Policy page | `/policy/` | Leads with case SE1 since 8 October: the eight tambons, the finding on Ko Chang and the four cautions. The earlier example is an appendix. |
| Public view on a phone | `/public/` | Live. |

## 7. What is missing, in order

### Before Session II

1. Rehearse the pitch of section 4.2 aloud, timed, with the screens.
2. ~~Put the SE1 result at the top of the policy page; move the old example
   down or out.~~ Done on 8 October (decision log R32).
3. ~~Draw the four-box pipeline and one slide of the THEOS-2 result.~~ Both are in `docs/mentoring/visuals/` since 8 October.
4. Ko Chang on a map (plan task V1). **The desk sheet is done (8 October):**
   `docs/ko_chang_road_check.md`, item V-10 of the team page. It lists the
   closed road pieces that cut Ko Chang off and the eight roads to look at
   first. Still open: someone who knows the place, or an image of September
   2024, to say whether road 1 is raised or stayed passable (Rachmania).
5. Find the mentor's written summary of Session I and tick it off.
6. Decide the three questions of section 3 to put to the mentor.

### Before the feature freeze (18 October)

7. **Equity gap by age.** Compute the difference and the ratio for residents
   aged 60 and over and under 15, as the proposal defines them, and report
   what the data allow. Expect a ratio near 1 in every tambon, because the age
   grid has one age mix per district. Say that, and name the data that would
   change it. Do not lead the pitch with equity.
8. **A printable brief for case SE1**, Thai and English, one page, with the
   class, the reason, source time, confidence and the planning-only line. The
   proposal promises it; the published briefs are for the older candidate
   cases and carry no score.
9. **The other 90 ensemble runs**, so that a class can be called stable or
   not.
10. **Our own radar through the chain (case O1).** Confirm the Sentinel-1
    rights record (open data), issue the case, and show that low confidence
    gives class E for all eight tambons. This is the proposal's worked example
    and the plain demonstration of "fail closed". With it, a table of how the
    result changes with the flood input. **The table is done (8 October,
    `docs/flood_input_comparison.md`, item V-16).** Whether the formal case is
    still issued is item V-21; the recommendation is no.
11. **A decision on a trained model.** The proposal's method 2 is a calibrated
    Random Forest or XGBoost. Either run it as a report-only experiment on the
    labelled events that are on disk, with grouped hold-out, a calibration
    curve and feature contributions, or state in the pitch that it was not
    run and why. Leaving it unmentioned is the weakest choice under a 35%
    criterion that asks whether the AI approach is credible. **Run on 8
    October (`docs/flood_susceptibility_model.md`, item V-18):** three models,
    spatial block folds, calibration, a test on three unseen districts. The
    one-feature baseline is the model to cite; say so in the pitch.
12. **The second class reading** (proposal section 5.2), if Mae Sai town as
    class D is to be answered with more than words.
13. **One outside reader.** A planner, a DDPM contact, or the GISTDA
    facilitator: fifteen minutes with the Planning page, and three written
    lines on what they understood. The proposal promised a stakeholder review.
14. **Offline rehearsal on a second laptop.**

### Say, do not build

- Hat Yai: a candidate case, no reference, not scored. Stretch, not completed.
- Lower Chao Phraya and Bangkok: roadmap.
- 2SFCA, deep segmentation, forecasting, citizen reports, Cell Broadcast:
  conditional or roadmap in the proposal, not done.

## 8. One page to hand the mentors

- Prototype: https://flood-guard-tau.vercel.app/ (Planning at `/command/`,
  Studio replay at `/studio/cases/mae-sai-2024/`, policy page at `/policy/`).
- Source: https://github.com/TUPRAM/flood-guard
- Result file: `apps/web/public/planning-overlays/mae-sai-2024/se1.json`
- Protocols: `docs/proposal_execution/planning_protocol_v1a.json`, `…v1b.json`
- Radar results: `outputs/planning_v1/radar_o1_mae_sai_v1.json`
- THEOS-2 check: `docs/theos2_radar_cross_check.md`
- Decisions: `docs/decision-log-d1-d16.md`

## 8. Added on 8 and 9 October: results to bring, each with its caveat

| Result | Where | One sentence for the session |
|---|---|---|
| Radar rules against a dated agency layer at Mae Sai | `docs/dated_radar_check.md` | The image taken as "before" decides what a change rule sees: 70% of the mapped water with a dry-season image, almost none with a wet-season one. The agency layer may come from the same radar pass. |
| A trained radar classifier | `docs/radar_flood_classifier.md` | Trained on agency labels, tested on an independent THEOS-2 tile: the full model did not carry over; a single backscatter threshold did better than our rules. |
| Work on the detection, with a held-out test | `docs/radar_detection_improvement.md` | It improved on open land in development; on a held-out flooded town nothing we built sees more than a quarter of the water, so the fixed rules stay. |
| The September pass read again | `docs/radar_detection_improvement.md`, section 3 | Read with a better detector, the radar pass cuts off 290 of Ko Chang's 5,972 residents; the total loss belongs to the season scenario. Unchecked: no dated reference for September. |
| Ko Chang roads at three closure levels | `docs/ko_chang_road_check.md` | The same road is the first to keep passable at every level. |
| Access loss by age | `docs/equity_by_age.md` | Computed; the open age data cannot show a gap inside a tambon. |
| The proposal's own class wording | `docs/class_v2_reading.md` | As a secondary reading, Mae Sai town is "protect essential services". The binding classes do not change. |
| The stability of the classes over all 180 cells | `docs/uncertainty_ensemble_rescaled_demand.md` | Seven of eight classes hold, Ko Chang's in 78% of the cells. Mae Sai town's D holds in 50%: it is D with the 2020 population product and A, B or C with the 2024 totals. Report-only; the published file still says "not evaluated". |
| Access loss by age | `docs/equity_by_age.md`, the two sections added on 9 October | The direction depends on the age data. With the modelled age grid no gap of a point or more for the district; with registered age counts by tambon (DOPA) older residents lose hospital access 1.10 to 1.13 times as often. The registered ages leave out two residents in five. |
| The run of record of the ensemble | `outputs/planning_v1/README.md`, plan task E10, third update | Of record since 9 October: seven classes hold over 180 cells and Mae Sai's D is "unstable: verify". Not yet on any page. |
| Shelters: access on foot and listed places | `docs/shelter_capacity.md` (figures in the pitch note outside the repository) | Pitch level only, label "listed planned capacity; scenario". Capacities are listed planning figures; nobody verified that a shelter was open. |
| A printable brief of case SE1 | `outputs/planning_brief/se1_mae_sai_brief.html` | One page, Thai and English, made from the published result. The Thai is not reviewed by a native speaker. |
| THEOS-2 on the study event | `docs/proposal_execution/theos2_study_event_check_plan_v1.md` | The plan is committed and the radar readings are frozen before any image arrives; the comparison runs once per scene when GISTDA delivers. |

Each is on the team page for the team's word (items V-17, V-19 and V-22 to
V-32). None changes a published class or enters a planning score.
