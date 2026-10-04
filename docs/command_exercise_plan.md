# Command exercise replay: detailed plan (Mae Sai, September 2024)

## Owner decisions, 5 Oct 2026

These decisions were given by the owner on 5 Oct 2026. Where the plan below says something else, the decisions win.

1. **Purpose approved.** The page is an "exercise and after-action tool for rescue coordinators". The banner reads: "Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning".
2. **Thai text.** No native reviewer is available for the hackathon, and the owner trusts the assistant with the Thai text. The assistant writes careful, natural, plain Thai itself, in the register Thai disaster agencies use in public notices, with Thai place names first. The page's information drawer says that the Thai text was not reviewed by a native speaker. This replaces the "draft until a Thai speaker signs it" rule in sections 8 and 11 and the reviewer named in decision 8 of section 12.
3. **Choices 2 to 6 of section 12** proceed as recommended. They are provisional until the owner answers each one.
4. **Choice 7 of section 12 is not approved.** Place records that paraphrase a plea appear as ordinary place records, with no "plea" tag.
5. **The optional SOS practice mark is not built.**

Build notes that follow from the decisions (set by the build brief, not by the owner):

- The new page is built at the temporary route `/command/exercise/`, with the root element `main.command-page[data-command-exercise]`. Today's `/command/` page and its sub-routes stay untouched; the swap to `/command/` described in section 11 is a later change.
- The Studio replay component is not reshaped. Three small map helpers and their popup styles move to a shared file (`apps/web/src/components/mae-sai-map-kit.tsx`), as section 11 describes.
- Five phrases of the plan were reworded on 5 Oct 2026 so that the shared wording lint can scan this file (`tests/test_replay_wording_lint.py` lists it). The meaning is unchanged: the banner note in section 1, "location tolerance" in section 6, "sit in neutral chips" in section 8, "to the day" in section 9 and "a callsign rule" in the critic's list. The local folder name in the opening paragraph was replaced by the branch name, because the project rules keep local paths out of the repo.

## Build status

**Stage 1 (5 Oct 2026): the shell and the map, at `/command/exercise/`.** Built: regions A, B1, C, E, F, G, H and I of section 3. B2 is a reserved card and D is not built. Files, under `apps/web/src/`:

- `app/command/exercise/page.tsx` (the route);
- `components/mae-sai-command-exercise.tsx` with its style sheet (the shell), `mae-sai-command-map.tsx`, `mae-sai-command-situation.tsx` (B1), `mae-sai-command-timebar.tsx` (F) and `mae-sai-command-chrome.tsx` (banner, drawer, navigation, tools, legend, credits, notice, help);
- `lib/flood-timeline-command-replay.ts` (replay state, keys, the hour in the address), `flood-timeline-command-map.ts` (water tones, label points, veil, scale bar) and `flood-timeline-command-data.ts` (loader);
- `clearRect` in `lib/flood-timeline-layout.ts`, beside `popupFit`: the clear rectangle that every fit, zoom and popup uses.

Where the build differs from the plan:

- **Sizes.** At 1440 x 800 the clock card is 213 px tall in English and 264 px in Thai, not 164 px. It carries the "Model · low confidence" tag and a fixed two-line slot for the "what changed" line and the model-limit chip, so that no panel moves while the replay plays. The table card takes the rest of the column: 423 px in English and 372 px in Thai.
- **Water outside the district is not drawn.** The terrain grid reaches past the eight subdistricts. The water layer and the terrain shading are clipped to them, so the veil reads "not modelled" everywhere outside.
- **The replay hour** stands beside the card's label, not beside the replay time: the Thai replay time needs the whole line.
- **The town view** of the fit tool is the located place records and the command centre, with about 500 m around them.
- **Start hour.** Without an hour in the address the page opens on 10 Sep 12:00 (replay hour 36), the midday before the river rises.
- **Legend.** It lists what the map draws. The r4 data holds no road outside the model and no reported site in modelled water, so those two entries stay out until the data has them.

Not in this stage: the page is not in the offline list, the route swap of section 11 is not done, the event buttons stop at the phase starts and the peak hour only, and find-a-place is a disabled button.

Prepared 4 Oct 2026 for Putu and Rachmania; corrected by the critic the same day. The repo was read only on the branch `claude/unify-lineages`, in a local checkout; nothing was edited, built or run. All paths below are relative to the repo root.

Terms used in this plan:

- **HUD**: the floating panels drawn on top of a full-screen map.
- **Tambon**: subdistrict. Mae Sai district has eight in the data.
- **Lane**: the kind of evidence an item is (model, observed, reported, calibration, scenario). Every item on screen wears its lane as a short tag.
- **Protocol case**: one of the signed scoring cases shown here: O1 (own radar candidates of 16 Sep 2024), O2 (agency layer of 22 Oct 2024), SE1 (Aug-Oct 2024 season envelope scenario).
- **FPPS**: the Flood Preparedness Priority Score, 0-100.
- **Inject**: an invented call or report scripted into an exercise so a team can practise.
- **Lost shelter access**: the replay's own measure. A resident had a shelter of the chosen set within a 2 km walk on passable roads before the flood and has lost it at this hour. It is not a count of people stranded.
- **PDPA**: Thailand's Personal Data Protection Act.
- **CSP**: the site's browser security rule listing which hosts the page may contact.
- **Agent-hour**: one hour of a coding agent's working session, including its own tests; human review is extra.

## 1. What it is, and what it is not

1. The new Command is a full-screen map of Mae Sai district that replays the September 2024 flood hour by hour (9 to 19 September, 264 hourly steps). People who coordinate rescue use it to practise reading a situation and tasking teams.
2. At each replay hour it shows modelled water, roads modelled as impassable, residents in modelled water, residents who lost shelter access, the shelters reported in use in 2024, and what had been reported or observed by that hour.
3. One table of the eight tambons shows two rankings side by side that are never merged. The left is a count from the replay model that changes with the hour. The right is the planning score and A-E class from the signed protocol's cases, fixed in time.
4. Reports and calls for help appear on the map as markers that open a short card. In this release they are 2024 place records from news, invented exercise calls tagged as such, and reports saved on the same device.
5. From a selected marker or tambon the operator sees an access hint and the nearest counted shelters, assigns an exercise team, shares a short Thai brief, and closes the item. All of it is stored on that device only.

What it is not:

- **Not real-time.** It is a reconstruction of a 2024 event. Every modelled figure is low confidence: the river stage is an illustrative curve, because no public hourly Sai River record for September 2024 was found (`timeline.json` `gauge_note`).
- **Not an official warning and not a dispatcher.** FloodGuard receives no calls. 1784, 1669 and 191 remain the official routes. Nothing a member of the public does on the Public page reaches a responder through FloodGuard today.
- **Not for operational decisions.** `timeline.json` `permitted_use` reads: "Preparedness learning, planning exercises and post-event prioritisation discussion in competition and preview builds. Not for emergency response, evacuation orders or any operational decision; not an official warning." So the page is a training and after-action tool. It does not task real boats. This conflicts with "help them coordinate the rescue" read literally, and is decision 1 in section 12.
- **Not a scored case.** Decision D7 says the replay is the narrative surface for O1 and SE1 and "is not a new case". The data file itself has `accepted_fpps: null`, `accepted_action_class: null` and `can_feed_decision_layer: false`. No FPPS or A-E class is computed per hour.

Banner wording. The owner's sketch denied that the page shows what is happening now, in a short phrase built on one bare word. The shared wording lint (`apps/web/src/lib/replay-wording-rules.json`, its second rule) bans that word and has no allowance for its negation, so the banner reads:

- EN: `Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning`
- TH (draft, needs native review): `ฝึกซ้อมย้อนดูเหตุการณ์ · แม่สาย ก.ย. 2567 (2024) · สร้างขึ้นใหม่จากแบบจำลอง ไม่ใช่ข้อมูลเรียลไทม์ · ไม่ใช่คำเตือนทางการ`

I checked both strings against the lint's allow patterns (`not_real_time`, `not_forecast_or_warning`, `th_not_real_time_or_warning`, `th_not_warning`). If this plan is saved under a linted docs path, the owner's original phrase must stay out of it.

## 2. Who uses it, and the three jobs it must make fast

Who "rescue teams" are in Thailand (general background, not from the repo; names to confirm with a Thai partner):

- The Department of Disaster Prevention and Mitigation (DDPM, hotline 1784) and its provincial office.
- The district incident command centre under the District Chief.
- The municipality or subdistrict organisation and its civil-defence volunteers.
- Military units.
- Emergency medical services (1669) and police (191).
- Charity rescue foundations with their own radio desks.

Under the Disaster Prevention and Mitigation Act 2007 the Local Director (mayor) and the District Director (district chief) lead first.

From the repo: in 2024 the incident command centre at the Mae Sai district office split the flood area into five zones (Hua Fai/Sai Lom Joy, Ko Sai, Mueang Daeng, Mai Lung Khon, Piyaporn) and made every arriving unit register there first. The source is quoted in `timeline.json` `shelters.reported[]` record R05.

The exercise users are:

- **Situation officer** at a district or municipal command centre: keeps the picture.
- **Coordinator**: shares teams out across places.
- **Facilitator**: sets up and runs the replay for a training session.

What went wrong in 2024:

- From the place records in the repo: a fast current, and rescuers who could not reach buildings.
- From the scouts' news chronology, not re-checked: crews could not find addresses, calls exceeded capacity, and some people waited 30 hours or more.

| # | Job | Question the screen must answer | Target |
|---|---|---|---|
| 1 | See the whole picture | Where is it worst at this hour, and is it getting worse? | 5 seconds, no tap, for someone who has seen the layout once |
| 2 | Turn one request into a tasked team | For this call or this place: how deep, how do we get near, where do people go, who goes? | Brief on screen in 4 taps after selecting the marker (Assign, callsign, Brief), handed to an app with the 5th. 45 seconds after two practice runs; 30 seconds is the stretch goal. |
| 3 | Know what is known | What had been reported or observed by this hour, what is only model, and what is missing? | One tap; the first screen of the feed answers within 15 seconds |

The original targets (30 seconds and 4 taps to a sendable brief; 10 seconds for job 3) did not survive a tap count. The path is select, Assign, callsign, Brief, then Share or Copy. The roster must already exist.

Acceptance test on Friday: two people on a tablet answer five timed questions. The facilitator sets the clock first, or 10 seconds are added when a question includes a time jump. An example is "at 06:00 on 11 Sep, which tambon has the most residents who lost shelter access, and what had been reported there by then?" The pass mark is 15 seconds per answer.

## 3. Screen layout

The pattern is copied from the GISTDA screenshot: a pale full-bleed map, one card column on the left, a thin column of round tools on the right, a nav pill top right, a legend chip bottom right, and nothing in the centre. GISTDA's red "approximate, not site-inspected" line becomes our permanent banner. We copy the layout, not the branding.

Design sizes are 1440 x 800 for desktop and 1024 x 700 for a tablet in landscape (a 1024 x 768 screen less browser bars). Panels are opaque white, 12 px radius, on an 8 px grid, with 12 px margins. Every touch control has a hit area of at least 44 px; the banner's (i) button reaches that by extending into the margin.

| Region | Position | Desktop 1440 | Tablet 1024 | Shows | When collapsed |
|---|---|---|---|---|---|
| A. Banner | Top, full width | 1440 x 36 | 1024 x 44 (Thai may wrap to 56) | The exercise line from section 1; an (i) button opening assumptions, limits, sources and licences | Never collapses, never dismissible |
| B1. Clock and figures | Top of left column | 420 x 164 | 320 x 116 | Replay time (ICT), replay hour n of 264, phase, assumed stage, three model figures, open exercise items, one "what changed" line (desktop only) | One 44 px line in focus mode |
| B2. Tambon table | Under B1 | 420 x 472 (8 rows of 50 px) | 320 x 416 (8 two-line rows of 44 px) | The two rankings (section 5) | 44 px header showing the top row only |
| C. Nav pill | Top right, under banner | about 400 x 44 | one 44 px menu button | Public, Command, Studio, language, help | n/a |
| D. Right card | Left of the tool rail, under C | 340 wide, up to 520 tall | does not exist; its tabs join the left column | Two tabs: Detail (inspector) and Known by now (feed) | A chip "Known by now (n)", 168 x 36 |
| E. Tool rail | Right edge, vertically centred, fixed (it never moves) | 7 buttons of 44 px | 6 buttons | View preset, basemap, zoom in, zoom out, fit (town or district), find place, focus mode | n/a |
| F. Time dock | Bottom, full width | 1416 x 88 | 1000 x 72 (rain row hidden) | Section 9 | 44 px (play, time, slider) in focus mode |
| G. Legend | Bottom right, above F | chip 120 x 36; open 280 x 240, left of the rail | same | The marker grammar as a grid, water and road keys, credits | Chip. The legend and the right card are never open together. |
| H. Watermark and attribution | Tiled across the map | n/a | n/a | Faint "EXERCISE · ฝึกซ้อม" repeated about every 400 px, so any cropped photo keeps the label; map credits and a scale bar above F | Never hidden |
| I. Toast line | Top centre, under A | one line | one line | Undo, "order held", offline note, "new exercise call (n)" | n/a |

Map coverage (arithmetic from the sizes above, not measured in a browser):

| State | 1440 x 900 | 1440 x 800 | 1024 x 768 | 1024 x 700 |
|---|---|---|---|---|
| At rest | 37.6% covered, 62.4% clear | 42.3% / 57.7% | 39.0% / 61.0% | 42.8% / 57.2% |
| Right card open (desktop only) | 50.8% / 49.2% | 57.1% / 42.9% | n/a | n/a |
| Legend open | 42.4% / 57.6% | 47.8% / 52.2% | 47.0% / 53.0% | 51.6% / 48.4% |
| Thai banner on two lines (tablet) | n/a | n/a | 40.6% / 59.4% | 44.5% / 55.5% |
| Focus mode | 15.0% / 85.0% | 16.9% / 83.1% | 17.4% / 82.6% | 19.1% / 80.9% |

Clear rectangle, used for every pan, fit and popup:

- Desktop at rest: 928 x 688 at 1440 x 900, and 928 x 588 at 1440 x 800.
- Desktop with the right card open: 576 px wide.
- Tablet: 612 x 616 at 1024 x 768, and 612 x 548 at 1024 x 700.

With the detail card open, less than half of a desktop screen is clear map. Focus mode (key F) is the answer when the map matters more than the panels.

The left column fits vertically with an 8 px gap above the time dock in both design sizes, including the two-line Thai banner on the tablet.

Every pan, fit and popup uses the measured clear rectangle. This needs a new helper beside `popupFit` in `apps/web/src/lib/flood-timeline-layout.ts`, so a selected thing is never under a panel. The map moves only in answer to a tap, a key or a selection.

Portrait tablets and phones are out of scope this week. Below 900 px wide the page shows the map, banner and time dock, and the table as a simple bottom sheet.

Desktop wireframe (1440 x 800, right card open on an invented exercise call; the model figures are the values I recomputed for 12 Sep 12:00, replay hour 84):

```
+--------------------------------------------------------------------------------------------------+
| EXERCISE REPLAY | Mae Sai, Sep 2024 | reconstructed, not real-time | not an official warning (i) |
+--------------------------------------------------------------------------------------------------+
| +--B1---------------------------+                              +--C----------------------------+ |
| | REPLAY TIME          [REPLAY] |                              | Public  Command  Studio  TH ? | |
| | 12 Sep 2024 12:00 ICT  h 84   |                              +-------------------------------+ |
| | Peak | assumed stage 3.5 m    |                       +--D--------------------------+ +-E-+   |
| | ~7,100     ~16,100   ~164 km  |                       | Detail | Known by now (n)   | |Vw |   |
| | lost acc.  in water  roads    |                       |-----------------------------| |Map|   |
| | of ~34,500 in reach | 3 open  |                       | [EX] Call for help, invented| | + |   |
| +--B2---------------------------+        M  A  P        | !! Life at risk | new       | | - |   |
| | THIS HOUR, MODEL    | PLAN, FIXED                     | Ko Sai community, +/-150 m  | |Fit|   |
| | # tambon    lost   wet | O1 SE1 #                     | Chest-deep, 6 people        | |Fnd|   |
| | 1 Mae Sai  ~5,700 ~5,900| -  -  -                     | Waiting 3 h (replay)        | |Foc|   |
| | 2 Pong Pha   ~560 ~1,900| -  -  -                     | Model here {d} m; current   | +---+   |
| | 3 Ko Chang   ~460 ~1,700| -  -  -                     |   not modelled              |         |
| | 4 Si M.Chum  ~410 ~3,500| -  -  -                     | 3 nearest counted shelters  |         |
| | 5 Ban Dai    <10+ ~2,300| -  -  -                     | [Assign] [Brief] [Done]     |         |
| | 6 Pong Ngam    0+   ~430| -  -  -                     +-----------------------------+         |
| | 7 Huai Khrai   0+   ~200| -  -  -                                                             |
| | 8 Wiang P.K.   0    ~100| -  -  -      EXERCISE . (tiled watermark)               [Legend ^]  |
| +-------------------------------+                                                                |
| +----------------------------------------------------------------------------------------------+ |
| | [< > >] -1h +1h speed | 9 10 11 12 13 ... | marks | phases | rain | /// not yet known ///    | |
| +----------------------------------------------------------------------------------------------+ |
+--------------------------------------------------------------------------------------------------+
```

In the wireframe:

- "+" marks a tambon where most residents had no reported shelter within a 2 km walk even before the flood (section 5).
- "-" in the plan cells is the truthful state today: no class has been issued for any Mae Sai tambon.

Tablet wireframe (1024 x 700):

```
+------------------------------------------------------------------------------+
| EXERCISE REPLAY | Mae Sai Sep 2024 | not real-time | not an official warning |
+------------------------------------------------------------------------------+
| +--B1--------------------+                                          [Mnu]    |
| | 12 Sep 12:00 ICT REPLAY|                                                   |
| | ~7,100  ~16,100  ~164  |                                          +-E-+    |
| +--B2--------------------+                                          |Vw |    |
| | Queue | Detail | Known |              M  A  P                     | + |    |
| | 1 Mae Sai ~5,700 ~5,900|                                          | - |    |
| |   O1 -  SE1 -  # -     |                                          |Fit|    |
| | 2 Pong Pha  ~560 ~1,900|                                          |Fnd|    |
| | ... 8 rows, 44 px      |                                          +---+    |
| +------------------------+                                                   |
| +--F-----------------------------------------------------------------------+ |
| | > | -1h | +1h | 12 Sep 12:00 | 9 10 11 [12] 13 .. /// not yet known ///  | |
| +--------------------------------------------------------------------------+ |
+------------------------------------------------------------------------------+
```

## 4. Every element on screen

`timeline.json` means `apps/web/public/studies/mae-sai-2024-timeline/r4/timeline.json`; the other r4 files sit beside it. "Lib" means `apps/web/src/lib/`. "Verified" means I read the file or field this session.

| Element | What it shows | Data source | Label it carries | Change with the time bar |
|---|---|---|---|---|
| Banner and (i) drawer | Exercise line; drawer lists permitted use, 26 assumptions, 4 limitations, 10 sources, build date | `timeline.json`: `permitted_use`, `assumptions[]`, `limitations[]`, `sources[]`, `generated_at`, `source_timestamp`, `confidence` (verified) | Applies to the whole page | None |
| Replay clock | Date and time in ICT, replay hour n of 264, phase, assumed river stage | Lib `flood-timeline.ts`: `dateFromT`, `phaseAt`, `stageAt`, `formatMoment` (verified) | "Replay time" plus a static REPLAY tag; stage is model, illustrative | Every hour |
| Figure 1: lost shelter access | Residents who lost a 2 km walk on passable roads to a shelter of the set, shown with its base "of ~34,500 who had one in reach" | `parseAccessNodes`, `summarizeAccessSets`, `accessSnapshot` in lib `flood-timeline-evacuation.ts` over `access-nodes.bin`; set `reported_2024`; scope: all residents at road nodes (verified: 7,086 at hour 84) | Model, low confidence | Every hour |
| Figure 2: residents in water | Residents whose home cell is in modelled water | `peopleInWaterStats()`; `population.tambon_histograms` (verified: 16,060 at hour 84) | Model, low confidence | Every hour |
| Figure 3: road km impassable | Kilometres of road modelled at 0.3 m or more, of 306.8 km shipped | `districtStats()`; `roads.geojson` props `h`, `k`, `m`, `len` (verified: 163.8 km at hour 84) | Model, low confidence | Every hour |
| Figure 4: open exercise items | Open injects, with the count at "life at risk" | Injects file and exercise log; neither exists yet | Exercise, simulated | As injects arrive and are closed |
| "What changed" line | Differences against one hour earlier, with the named roads that became impassable | The three figures; `roadCutGroups` and `namedRoadLengths` (660 of 2,979 road pieces carry a name) | Model | Every hour |
| Model-limit chip | From 13 Sep: "The model dries as the river falls; standing water and mud are not reconstructed" | `limitations[3]` (verified) | Model limit | Shown in the Receding and Mostly receded phases |
| Water layer | Modelled water in two tones of one blue (under 0.3 m; 0.3 m or more), hatched where confidence is lowest | `hand-codes.png` (R = height code, G = depth factor, B = low-confidence flag; verified in `hand`); painters in lib `flood-timeline.ts` and `flood-timeline-water.ts`; the two-tone ramp is new | Model, low confidence | Every hour; repaint throttled as on the Studio replay |
| Outside-district veil | Grey veil outside the eight tambons (including the Myanmar side), so blank ground is not read as dry | `tambons.geojson`; new | "Not modelled" | Static |
| Roads | Dry (thin grey), wet (dashed amber), impassable (thick red), not modelled (dotted grey) | `roads.geojson`; `roadState(h, stage, 0.3, k)` (verified) | Model; bridge decks are not modelled | Every hour |
| Tambon outlines and names | Eight tambons, Thai name first | `tambons.geojson` props `id`, `th`, `en` (verified); a label point per tambon is computed at load (new) | Context | Static |
| Reported shelters (star) | The 14 located shelter sites reported in use in 2024; whether each is dry in the model at this stage; occupancy text as written, with its dates | `shelters.reported[]`: `name_th`, `name_en`, `lat`, `lon`, `period_used`, `first_use`, `in_access_set`, `reported_capacity_or_occupancy`, `sources[]`, `model_check` (verified). 19 records: 18 shelters and the command centre. 4 shelters have no coordinates (R09, R13, R14, R17) and appear in a list only. | Reported, not surveyed; the dry or wet state is model | Position static. In trainee mode a site is outlined and reads "not yet reported at this replay hour" before its first source date. The access figures assume every counted site is open for the whole replay. |
| Command centre (diamond) | Mae Sai District Office, incident command centre | `shelters.reported[]` id R05, `role` `relief_command_centre`, `first_use` 2024-09-11 (verified) | Reported | Appears from 11 Sep in trainee mode |
| Candidate shelter sites | 113 candidate sites and the ranked plan (12 entries; 8 sites at the knee) | `shelters.candidates[]`, `shelters.plan[]`, `knee_k` (verified) | Scenario; candidates to verify, not a list of sites to open | Hidden by default (Evidence view) |
| Facilities | 42 points: 9 schools, 6 health, 6 emergency service, 4 community, 17 shelter candidates; in water or not | `facilities.geojson` prop `type`; `facilityWet()` (verified) | Context; state is model | State per hour |
| 2024 place records | Water depth reported in news at a named place. 21 records from 17 statements in 14 articles. 12 have a point; they sit on 9 map points, so 9 markers with a count. | `reported_depths.reports[]`: `place`, `point`, `location_tolerance_m` (100 to 400 m), `depth`, `time`, `source`, `consistency`; grouping by `reportedDepthPlaces()` (verified) | Reported, anecdotal, not surveyed | In trainee mode a marker appears at the earliest `source.published` of its records (section 9) |
| "Model dry at the point" badge | Marks a place where the model shows dry ground at the reported time | `reports[].consistency` = `model_dry` (9 of the 12 located records; verified) | Reported against model | With the marker |
| Exercise injects | Invented calls for help and reports | `apps/web/public/exercises/mae-sai-2024/injects.v1.json`; does not exist yet | Exercise, simulated; "EX" tag | Each appears at its replay hour |
| Device reports sign | Count of reports saved by the Public page in this browser, per tambon; a sign at the tambon label that opens a popup | localStorage key `floodguard:public-reports:v1`; `planning_area_id` holds the tambon code TH5709xx (verified in `public-report.ts` and the public bundle); a `storage` listener shows a report saved in another tab of the same browser | "This device · today's date · not part of the 2024 replay · tambon only" | None; it is outside the replay clock |
| Tambon table, left group | Per tambon: lost shelter access, in water, and a mark where most residents had no shelter in reach before the flood | `accessSnapshot().lostByTambon` and `.neverByTambon`; `peopleInWater()` over `population.tambon_histograms[id]` (verified) | Model, low confidence | Every hour, with the rules in section 5 |
| Tambon table, right group | Class per protocol case and planning position | Planning overlay rows (`fpps_0_100`, `action_class`, `lane`, `tier`, `confidence`, `headline_stability`). No overlay exists for Mae Sai (task E8 not built). The parser is on the unmerged branch `claude/engine-e11-overlay-schema` (verified: `planning-assessment-overlay.ts`, 1,765 lines). The position is derived by sorting `fpps_0_100` within one case; it is not a field. | Protocol case, fixed; each chip names its lane | Never |
| Inspector: tambon | This hour's figures, road km impassable in the tambon, facilities in water, peak summary, located place records in the tambon, one card per protocol case with the class name and action text | As above; sums by props `t`; `exports/tambon_replay_summary.json`; point-in-polygon of place-record points (new); `ACTION_TEXT` in `apps/web/src/components/command-workspace.tsx` lines 27-33, which is not exported today | Model for the top half; protocol case for the cards | Top half hourly; cards fixed |
| Inspector: incident | The item's fields, access hint, nearest counted shelters, action bar (section 7) | Marker source; `access-nodes.bin`; `shelters.reported[]`; `hand-codes.png` | Mixed, each line tagged | Access hint per hour |
| Known-by-now feed | Dated items up to the playhead | Section 9 | Each row tagged with its lane | Grows with time |
| Rain gauges | Hourly rain at two gauges (MOU189 and DIWO, 264 hours each, none missing) | `rainfall.stations[]`, `rainfall.hourly_mm` (verified) | Observed gauge (HII, CC BY-NC) | Value at the hour |
| Season envelope | Water mapped at some time in Aug-Oct 2024 | `unosat4009/envelope.png`, `envelope.json` (verified) | Scenario; with the credit "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" and the standard sentence from the manifest | Not time-dependent; shown only in hindsight mode |
| Satellite images | Four scenes. Two are pre-event (Sentinel-2 on 5 Sep, Sentinel-1 on 6 Sep), before the replay window. Two fall inside it: Sentinel-2 on 15 Sep 10:58 and Sentinel-1 on 16 Sep 06:16. | `s1-*.webp`, `s2-*.webp`; `observations[]` (verified) | Observed; "acquired", not "known". The 16 Sep radar pass was used to tune the model, so it carries the calibration tag. | Available from the acquisition hour; Evidence view only |
| Find place | A search box over the names the data holds: tambons, reported shelters, place records, named facilities, named roads, candidate sites | Built at load from the r4 files; new. No village or soi gazetteer exists in the repo. | Context | None |
| Staging points | Pick-list for "where the team starts": R05, R01, or a tap on the map | `shelters.reported[]`; two of the six OSM emergency-service points are unnamed and one is a forest-fire station, so they are not offered | Reported, or set by the facilitator | Static |
| Exercise roster and setup | Team callsigns, staging point, start hour, mode, speed | Device storage; does not exist yet | Exercise | n/a |
| Basemap | Grey street map; hillshade when offline | OpenStreetMap tiles; `hillshade.webp` | Context | None |
| Data line | "Data r4 · built 3 Oct 2026 · sources 3-19 Sep 2024" | `timeline.json` `revision`, `generated_at`, `source_timestamp` (verified) | n/a | None |

## 5. The tambon table: two rankings side by side

It is one table with one row per tambon, so nobody has to match names across two lists. A divider and a tinted background separate the two column groups.

**Left group, header "This hour · model"**

- Columns: position, Thai name with the romanised name under it, lost shelter access (for example `~5,700`, with a thin single-blue bar on a fixed scale and a change arrow with its number), and residents in water at the same size.
- The words "score", "priority" and "class" never appear in this group, and the bar never uses class colours. That keeps D7.

Three facts about this ranking that the owners should know before Friday (I recomputed them from `access-nodes.bin`):

- **The order rarely changes.** Over the 264 hours the order of the non-zero rows changes 9 times. Mae Sai is first whenever any row is above zero. Only Pong Pha, Ko Chang and Si Mueang Chum trade places below it.
- **Most hours are all zeros.** Every row is zero up to and including hour 43, and again from hour 153: 155 of the 265 hourly positions. The numbers and bars carry the movement; the reordering does not.
- **58% of residents can never count as "lost".** 47,273 of the 81,799 residents at road nodes had no reported shelter within a 2 km walk even before the flood. The share is 100% in Huai Khrai, 99.9% in Ban Dai, 83% in Pong Ngam and 78% in Si Mueang Chum. At the peak Ban Dai shows about 3 who lost access while 2,312 residents are in modelled water. That is why "in water" is a full column and why such rows carry the "+" mark with a one-line footer.

Peak values (hour 84) for reference:

| Tambon | Lost shelter access | In modelled water |
|---|---|---|
| Mae Sai | 5,660 | 5,920 |
| Pong Pha | 558 | 1,922 |
| Ko Chang | 458 | 1,706 |
| Si Mueang Chum | 407 | 3,466 |
| Ban Dai | 3 | 2,312 |
| Pong Ngam | 0 | 435 |
| Huai Khrai | 0 | 197 |
| Wiang Phang Kham | 0 | 102 |

Three more points on the left group:

- **Place records per row.** Each row shows the number of located place records in the tambon (by point-in-polygon; the nine unlocated records stay district-level). Wiang Phang Kham reads 0 lost and about 100 in water, yet holds the Sai Lom Joy market records where news reported more than 2 m. A low model figure must not read as "fine". The drawer carries the manifest's own sentence: "The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated."
- **Scope.** The figures count all residents at road nodes. This matches the baked day figures and the export table. The Studio replay's default scope is homes that flood at the peak, which gives 5,400 instead of 7,086 at hour 84. The header names the scope, and the link to Studio carries `pop=all`.
- **Shelter set.** The order depends on the set. The default is the 12 located sites counted in the 2024 set. A switch offers the first 8 sites of the ranked plan, with a note that the figures change with the set and that no set is graded.

**Right group, header "Plan · fixed" with a lock glyph**

The full line under the table reads: "Planning class from the signed protocol. Fixed in time. Not computed from this replay hour."

- Each row shows two chips and one planning position.
- `O1` is the observed lane. By protocol rule it shows E in Command, on an amber chip. The inspector card reads "Own model candidate: verify before action" (v1a display rule, verified).
- `SE1` is the scenario lane, on a hatched chip. The card reads "Scenario: what-if (2024 season envelope)".
- O2 (agency map, blue chip) appears as a third card in the inspector when it becomes publishable.
- The lane is carried by the column header and the chip pattern, never by colour alone.
- The planning position comes from one case at a time, chosen by the control "Planning position from: O1 | SE1". The two cases are never averaged or counted together.
- Any score shown carries its tier, protocol version and anchors in the inspector card (decision-log rule R2).
- Wherever an E appears, "Class E never means safe" is printed.
- A chip is filled only when the overlay marks the class `headline_eligible`. It is outlined with "stability not evaluated" otherwise, and reads "unstable: verify" when the overlay says so.
- A unit under 100 residents gets no class (guardrail GR1). No Mae Sai tambon is that small, so the rule never fires here.

**Honest empty state.** Today no class exists for any Mae Sai tambon, so each chip shows a dash and the card says "Not issued yet (task E8)". The E11 fixture has invented units and never appears on the page. Tests use its invented units on both sides, so no invented class is ever attached to a real tambon.

**Controls above the table**

- "Order rows by: this hour | planning".
- "Planning position from: O1 | SE1".
- There is no mark that compares the two rankings. A derived "differs" signal would be a blend of the hourly count and the protocol output.

**Reorder rules, so a row never moves under a finger**

1. Sort by lost shelter access, highest first.
2. A row overtakes another only when it leads by at least 25 residents. This stops the Pong Pha and Ko Chang flicker at hours 117-118 (311 against 308).
3. Ties, including all zero rows, are ordered by residents in water, then by tambon code.
4. While the pointer or keyboard focus is inside the table, or the time thumb is being dragged, numbers update but the order is frozen. A slim bar says "Order held".
5. Rows have a fixed height. With only 9 order changes in the whole replay, the slide animation and the "moves pending" counter are not built this week.

**On select.** The row is highlighted, the map fits that tambon inside the clear rectangle, and the inspector opens on it. Time does not change. Escape deselects.

## 6. Reports and SOS on the map

### Marker design

Each meaning has at least two cues, so colour is never the only signal.

| Meaning | Cues |
|---|---|
| Kind and lane | Speech bubble with a count = 2024 place records from news at that point. Octagon = exercise call for help. Rounded square = exercise report (depth or road). Sign on the tambon name = reports saved on this device. Every inject also carries an "EX" tag and an id starting "EX-". |
| Urgency (injects only) | Symbol, size and colour together. Life at risk: "!!", 36 px, vermillion `#D55E00` with a white halo. Urgent: "!", 30 px, orange `#E69F00` with a black symbol. Information: "i", 26 px, blue `#0072B2`. |
| Handling state | Dashed outline = new. Solid outline with the callsign under the marker = acknowledged or assigned. Grey with a tick = done or dropped. |
| Age | Open exercise items show a waiting clock in replay time ("waiting 6 h"). It never fades. Device reports show their real date. |
| Location tolerance | A faint dashed circle of the stated tolerance (100 to 400 m on the place records), drawn on selection. |
| Clustering | Below zoom 13, markers within 40 px merge into a count mark. A cluster that holds a life-at-risk item shows "!!" and that count beside the total. Tapping a cluster zooms to it. It is hand-rolled; the repo has Leaflet 1.9.4 and no clustering library. All nine place points lie inside about 2.5 km of town, so at district zoom they are always one cluster. |

Three design choices sit behind this grammar:

- **Colours.** The palette is colour-blind safe and deliberately not the red, yellow, green and white of medical triage codes, so medics do not read a marker as a patient's condition.
- **Urgency.** It is written into each inject by its author under a visible rule from stated facts, never by the model: people on a roof, water at chest or above with people present, an infant or bedridden person, or no food for a day. The operator can raise or lower it with one tap, which is logged. Device reports and place records carry no urgency.
- **Wording.** Nothing is "verified" and that word is not used. The states are "new", "acknowledged", "assigned", "done" and "dropped".

### Popup

Popups are built from text nodes only, with the replay's existing builder (`popupElement`, today inside the Studio component), so user text never becomes HTML.

Inject and device popups have at most six lines and two buttons:

1. Lane tag and kind, for example `[EXERCISE · invented] Call for help`.
2. Place in Thai and romanised, tambon, and location tolerance.
3. What: depth band, number of people, needs.
4. When: replay time received and waiting time; or, for a device report, today's date.
5. Model here: modelled depth at this hour, always with "current not modelled".
6. Handling state, then **Assign** and **Details**.

Place-record popups use the existing linted builder `reportedDepthPopup`, one section per record at that point. It gives eight or more lines and a source link, and scrolls inside the popup. It already states the comparison with the model, so no extra line is added. In trainee mode only the records published by the playhead are listed.

### The honest data path

**Stage A: now, for the exercise (ships this week)**

| Source | Real or simulated | How it is labelled | Where it appears |
|---|---|---|---|
| 2024 place records: 21 records from 17 statements in 14 articles; 12 have a point, on 9 map points | Real 2024 news content, paraphrased; anecdotal, not surveyed. All are depth statements. By my reading about seven paraphrase a plea for help that a news outlet reprinted (ms-c2-04, -10, -11, -12, -13, -18, -20); none carries a name or phone number. None was sent to FloodGuard. | "Reported in news (not surveyed)" | 9 markers for the 12 located records; all 21 in the feed |
| Exercise injects: about 14 scripted items | Simulated. Invented by the team; no real person, name, phone number, soi or house. Placed on the place-record community points with a tolerance circle. An inject never copies the details of a real 2024 plea. | "EX" tag; id "EX-nn"; first popup line says invented; excluded from every count of real reports | Markers at their replay hour |
| Reports saved by the Public page on this same device | Real entries by whoever used this browser, dated today | "This device · today · not part of the 2024 replay · tambon only" | A sign on the tambon name, never a dot at a point |
| SOS | Nothing exists: the SOS page only opens the phone or SMS app and stores nothing | n/a | SOS markers are injects only, unless decision 4 adds the practice mark below |

The Public report has no coordinates, so a dot would send a team to the middle of a tambon. It also carries today's date, so it cannot sit on the 2024 clock.

The Public report page promises today: "This note is not sent to an agency or shared with others." Showing the report on Command on the same device sends nothing. In the competition build the page gains one sentence: "It also appears on this device's Command exercise map."

Optional in stage A (decision 4; first item to cut): an SOS practice mark.

- It sits under a collapsed "For exercises" line below the real call buttons, off by default, and never delays them.
- It stores the tambon and the time only, under a new device key. It stores no name, phone, coordinates or household needs; needs such as medicine or mobility can be health data.
- Its text on the SOS page: "Practice only. Nothing is sent. Rescue teams cannot see this. Call 1784."
- On Command it is a neutral device sign, not the life-at-risk style, with the popup line "SOS screen used on this device · today · nothing was sent to anyone".
- It is dropped after 24 hours and exists in the competition build only.

**Stage B: next (not this week)**

An opt-in relay through the project's API, so a Command on another device can see a report. It needs:

- a report contract in `packages/contracts`;
- report endpoints in `services/api` (the service has routes for scenario runs and the agency pilot, none for reports), with storage, a rate limit and a host;
- a `connect-src` change in `vercel.json` and CORS settings;
- consent text in both languages with a version number, replacing the Public page's current promise that nothing is sent;
- a named data controller and a contact for deletion;
- a stated retention period (proposed: 72 hours, then deletion; delete on request with a report token);
- a legal check of explicit consent for health-related needs and of storage outside Thailand;
- a confirmation screen that says a relay does not replace calling 1784, 1669 or 191, and that nobody watches the map around the clock.

Minimal fields: tambon, an optional coarse 250 m cell chosen by the reporter, depth, needs categories, a people-count band, time and consent version. Free-text notes are dropped or held until moderated.

**Stage C: later**

Checking and hand-off: an operator calls back, marks the item checked, and hands it to 1784 or the DDPM LINE account. This needs sign-in, an audit trail and an agreement with an agency. FloodGuard never replaces 1784.

### Privacy rules

Never collected or shown at any stage:

- name;
- national ID or passport;
- house number or exact address;
- precise GPS;
- the photo file (only a yes or no is stored today);
- nationality or immigration status;
- device identifiers.

Phone number: never in stages A and B. In stage C it is collected only if the reporter opts in for a call-back, and it is masked until tapped.

Command has no login in the competition build, so everything on it is public. Therefore:

- Free-text notes of device reports stay hidden behind a tap and never enter a brief, a CSV or a snapshot.
- The roster accepts callsigns only: at most 12 characters, and any entry with seven or more digits is refused.
- The exercise log stores roles and callsigns, not names.
- A brief built from a place record carries the place, the depth class and the publisher, not the statement text.
- "Reset exercise" clears every Command key on the device.

## 7. From seeing to acting

The inspector has a fixed action bar: **Assign**, **Brief**, **Done**. There are no confirmation dialogs; each action shows a 10-second Undo.

| Step | In the browser this week | Only possible later |
|---|---|---|
| 1. Select an incident or a tambon | One tap. The map pans it into the clear rectangle. | n/a |
| 2. Where do people go | The three nearest of the 12 located sites counted in the 2024 set, by straight line. Each shows distance, bearing, "dry in the model at this stage", "reported in use by 15 Sep 2024; opening time not known", and the occupancy text with its dates. One line from the access model for the nearest resident node (within 300 m, else "no node near"): access kept, lost at this stage, or none within 2 km even before the flood. | Which shelter is reachable and how full it is per hour. The browser has no per-shelter reachability and no hourly occupancy. |
| 3. How to get near | Facts only: modelled depth at the point and "current not modelled"; whether the point is at or over the 0.3 m level at which roads count as impassable; the nearest road piece under 0.3 m in the model, with distance and name, labelled "not checked for a connected way out; bridge decks not modelled"; the named roads impassable in that tambon this hour; a dashed straight line from the staging point labelled "straight line, not a route". The page gives no team-type advice. | A path on the road network. The shipped `roads.geojson` cannot be routed (195 disconnected parts by shared vertices, verified). The bake's graph (`outputs/mae_sai_access_edges.csv`, 30,443 edges, 4.2 MB) would have to be packed for the browser with its own offline budget. The line would be labelled "modelled passable path at this replay hour", never a safe route. |
| 4. Assign a team | Pick a callsign from the exercise roster typed on this device (type: boat, wading, vehicle, medical). The marker shows the callsign. | A roster shared between devices; real unit data (the repo has none). |
| 5. Share a brief | A sheet with Share (the device's own share sheet, which reaches LINE), Copy and SMS. The SMS link never has a recipient filled in, so an exercise brief cannot go to 1784 by a slip. FloodGuard sends nothing and no CSP change is needed. | n/a |
| 6. Close | States: New, Acknowledged, Assigned, Done, Dropped (duplicate or could not reach). | Shared state and hand-off to 1784 (stage C). |

**Brief template** (Thai by default, at most 9 lines; the Thai is a draft for native review):

```
[ฝึกซ้อม – ไม่ใช่เหตุจริง] {id}
เหตุ: {kind} · น้ำ{depth band}
ที่: {place} ต.{tambon} (±{tolerance} ม.) {lat},{lon}
คน: {people} · {needs}
เข้าถึง: แบบจำลองน้ำลึก ~{depth} ม. · ถนนที่น้ำต่ำกว่า 0.3 ม. ใกล้สุด ~{distance} ม. · ไม่ทราบความแรงกระแสน้ำ
ที่พักพิงใกล้สุด (เส้นตรง): {shelter} ~{km} กม.
เวลาในการย้อนดู: {replay time}
ที่มา: {lane} · แบบจำลองความเชื่อมั่นต่ำ
[ฝึกซ้อม – ไม่ใช่เหตุจริง]
```

- The exercise tag is the first and the last line, so it survives forwarding and trimming.
- A Thai text message holds 70 characters, or 67 per part when joined (the standard for non-Latin text; carriers not tested). The full brief is six or seven parts, so SMS offers a two-line version of at most 134 characters with the part count shown.
- Rain values never go into a brief or export, because the rain data are CC BY-NC.
- A one-tap "situation brief" gives the three model figures, the top three tambons and the roads newly impassable.

**Facilitator setup** (one sheet, opened from the menu): roster, staging point, start hour, trainee or hindsight mode, injects on or off, speed, and "pause when a life-at-risk inject arrives" (on by default).

**Exercise log.** Every action is stored on the device with replay time, device time, role and callsign. It is shown as a short history, can be exported as CSV with a `simulated` column, and has a "Reset exercise" button. A chip says "Saved on this device only".

## 8. Clarity rules

- **Always visible:** replay time and phase; lost shelter access with its base; residents in water; road km impassable; open exercise items. Nothing else is promised at a glance.
- **Rounding:** model figures pass through one helper: a tilde, nearest 10 below 1,000, nearest 100 above, "<10" for tiny values. Counted things (injects, reports) use plain digits.
- **Colour budget:** most of the screen stays neutral. Water is one blue in two tones. Class letters sit in neutral chips with a pattern. The phase band is blues and greys with the phase name printed in it, because red already means impassable roads.
- **Uncertainty without paragraphs:**
  - dashed or hatched means modelled or new; solid means observed or acknowledged;
  - one short lane tag per card; the one-sentence caveat lives in the banner drawer;
  - missing things are drawn as missing: a dash chip, dotted "not modelled" roads, the veil outside the district;
  - the situation card carries the line "Place records with a point: 12. At the point, the model is consistent with 1, wet at 2 and dry at 9", so nobody trusts the smooth blue layer over a person's report;
  - a tambon with residents in water but no report or inject gets a grey "no reports received" mark, and a tambon with place records but little modelled water shows the record count, because neither silence nor a dry model is safety.
- **Hidden until asked:** the full layer list sits behind view presets. Rescue is the default; Evidence adds candidates, satellite images and the envelope. A Planning preset appears only when an overlay exists; it pauses the replay and shows class letters at the tambon labels under a "fixed in time · not this replay hour" ribbon, never as a fill beside moving water. Also hidden: methods, licences and report notes.
- **Never:** a pulsing dot, the device's own clock beside the replay clock, map movement the user did not ask for, sound.
- **Thai first:**
  - place names show Thai first with the romanised name smaller;
  - briefs default to Thai;
  - dates read `11 ก.ย. 2567 (2024)` using the existing helpers, with Western digits and 24-hour time;
  - Thai body text has line height 1.5 and no fixed heights that clip tone marks;
  - components are sized for the longer of the two strings, and table headers use the short forms from section 5, because the long Thai headers do not fit;
  - the interface language follows the shared toggle;
  - all new Thai is labelled draft until a Thai speaker signs it; the lint's own Thai list is unsigned until 22 Oct 2026 (roadmap H12).
- **Keyboard:** existing keys stay (Space, arrows for 1 hour, Shift+arrows for 1 day). New keys: `[` and `]` for previous and next event, F for focus mode, Escape to close, `?` for help.

## 9. The time bar and the "known by now" feed

**Time bar (region F), left to right**

- Controls: previous event, play or pause, next event, minus one hour, plus one hour, speed.
- Speeds: 1 replay hour per second, 4 per second, and a drill speed of 1 replay hour per real minute, so a team has time to act.
- A row of eleven day chips (9 to 19) jumps to a day.
- The track holds 264 hours at about 4 px per hour on desktop and under 3 px on a tablet. That is too fine for a finger, which is why the steppers and day chips exist.
- The track has three thin rows:
  1. Event marks. Filled marks are observed or reported items; hollow marks are model events (first hour a tambon loses access, the peak). Marks closer than 6 px merge into one with a count. Marks are not touch targets; the event buttons and the keys reach them. A tap on the track seeks to the nearest hour and snaps to an event within 3 hours.
  2. The five-phase band with phase names.
  3. Hourly rain bars for the two gauges (desktop), with night hours lightly shaded (approximate).
- Everything to the right of the playhead is hatched and labelled "not yet known at this hour".
- The hour is kept in the address bar with the same `t` parameter as the Studio replay (`lib/flood-timeline-link.ts`, verified), so a moment can be shared.

**Two modes**

- **Trainee** (default): the future is hidden.
- **Hindsight**: shows everything, including the season envelope and the cumulative agency figure.

**The feed**

The feed is one pure function `knownBy(t)` over `timeline.json`. Rows are newest first, grouped by day, two lines each: lane tag, headline, time and age in the replay, a place link that moves the map, and a source link.

| Item | Time used | Source field |
|---|---|---|
| Place records from news | Publication time; for the two date-only entries, the end of that day | `reported_depths.reports[].source.published` (verified) |
| Rain | Threshold crossings only, not every hour | `rainfall.hourly_mm` (gauge MOU189 has 14 hours at 10 mm or more; DIWO has 1) |
| Satellite passes | Acquisition time, worded "acquired … ; would have reached responders later". The two pre-event scenes are listed as "held at the start". | `observations[].local` |
| VIIRS daily maps | 13:30 each day, one text line with the cloud share: 100% on 10 and 11 Sep; 82%, 69% and 98% on 12 to 14 Sep; 4% on 15 Sep, the first mostly clear day | `viirs_daily.days[].cloud_share` (verified) |
| GISTDA RADARSAT-2 figure | Acquisition, 10 Sep 18:15 (9.9 km²), tagged "calibration: used to set the model; acquired, published later" | `external_checks[]` has no time field; the time is a constant copied from its `observed` text and covered by a test |
| UNOSAT 3991 | Hindsight mode only: it is a cumulative product for 13 to 19 Sep and the data hold no publication time | `external_checks[]` |
| Reported shelters | First dated 2024 source, to the day; "accessed 2026" entries are ignored | `shelters.reported[].sources[].date`, `first_use` |
| Model events | The hour they occur in the model, tagged model | Computed per hour |

- The rain thresholds are display rules, not hazard levels.
- A fixed first line states what is missing: "No public hourly river-level record for the Sai was found."
- If the user has scrolled, playing does not auto-scroll; a "Jump to newest (n)" button appears.

**One rule change to approve (decision 6).** On the Studio replay the place-record markers do not follow the clock. On Command, in trainee mode, they appear at their publication time. The Studio page stays as it is.

## 10. What is deliberately left out, and why

| Left out | Reason |
|---|---|
| Any FPPS, class or "priority score" per hour; any blend or derived comparison of the two rankings | Decision D7; `timeline.json` `reason_blocked`; guardrail GR5 (no score for a real unit outside the signed protocol); the overlay never counts across lanes |
| The banned word for "happening now", a pulsing indicator, "now" without "in the replay" | AGENTS.md and the wording lint |
| A fill bar per shelter per hour | The data hold only a few dated occupancy counts in free text; opening times on 10-12 Sep are not modelled |
| "Nearest reachable shelter" as a fact | The browser has no per-shelter reachability; we show straight-line distance plus the access model's yes or no |
| A route line this week, and the online walking router | No routable network in the browser; the online router is not flood-aware and would draw through modelled water |
| Any team-type advice, including "boat or wading" | The model has depth only, no current, and current was the main obstacle in 2024; the trainee decides |
| The E11 fixture on the page; the O2 layer on the map | Invented units; O2 is held at rights level "local" (GR6; from the scouts, not re-checked) |
| A would-be class for O1 rows | Protocol: shown only in the Studio verification queue |
| The top-20 critical links as a default layer | Unreviewed candidates (from the scouts, not re-checked) |
| VIIRS maps on the Command map | The provider states no licence; reuse beyond the replay page is not cleared (`publication_eligibility`, verified) |
| Rain values in briefs and CSV | CC BY-NC licence |
| Real 2024 help posts taken from social media | They contain names, addresses and phone numbers. The news paraphrases already in the place records hold none. |
| The five 2024 command zones as outlines | Boundaries were never published. The five names are in the data (R05's source) and four have a place-record point, so zone labels are possible after Friday. |
| An SOS that reaches responders; cross-device reports; login; Burmese | Need a deployed API, consent, a controller and an agency agreement (stages B and C) |
| Night theme, PNG snapshot, reorder animation | The site is light-only today (`color-scheme: light`); new token work does not fit the week |
| Sound, automatic map jumps, phone layout | Dispatch practice rejects the first two; the third is out of this week's scope |

## 11. Build plan (Sun 4 Oct to Fri 9 Oct 2026)

**Approach**

- Build a new, slimmer map for Command from the replay's existing pure libraries (`lib/flood-timeline*.ts`). Do not reshape the 255 KB Studio component, which carries 48 component tests.
- The one change to that component is to move three small helpers (canvas overlay, popup builder, keyboard popup) and their popup styles into a shared file that both pages import. `popupFit` already lives in the lib.
- New files are named `mae-sai-command-*.tsx` and `flood-timeline-command*.ts`. The wording lint picks up those name patterns automatically (`replaySourceFiles()`, verified). It does not pick up the injects JSON or the rendered Command panels; both must be added to the lint test by hand, and its fixed counts updated.
- Replace `/command/` on Monday, not at the end. I found 17 script files (57 lines) under `apps/web/scripts/` that name `/command/`, several with selectors of the old page, plus about 13 source files and their tests. Doing the swap first, against a stable root (`main.command-page[data-command-exercise]`, the banner and the clock), gives four days of checks on the final address.

**Effort.** The hours are estimates, not measured. The scouts costed the full wish-list at 19 to 22 developer-days, so this week covers the must-ship items only.

| Phase | Ships | Files to create or change (under `apps/web/` unless stated) | Tests | Agent-hours | Depends on |
|---|---|---|---|---|---|
| 0. Sun 4 Oct: decisions | The decisions in section 12; a decision-log entry in lint-safe wording; a request to the engine lane to merge E11; a named Thai reviewer | `docs/decision-log-d1-d16.md` | Python wording lint | 3 | Owners |
| 1a. Mon 5 Oct: route move (second agent, in parallel) | Today's text page moves intact to `/command/planning/`; `/command/` serves the new root; header, policy card, landing links, offline list and CSP route list updated | Change: `src/app/command/page.tsx`, new `src/app/command/planning/page.tsx`, `src/app/layout.tsx` (status pill), `src/components/workspace-header.tsx` and test, `policy-page.tsx`, the 16 smoke and QA scripts, `scripts/write-offline-assets.mjs`, `scripts/build-case-briefs.mjs` link text | `pnpm verify:frontend`; profile smokes | 8 | Decision 2 |
| 1b. Mon 5 Oct: map, clock, banner | Full-screen shell; water, roads, tambons, veil, shelters; banner and drawer; clock and three model figures; time dock with play, steppers, day chips, speeds; `t` in the address | New: `src/components/mae-sai-command-exercise.tsx` and `.module.css`, `mae-sai-command-map.tsx`, `mae-sai-command-situation.tsx`, `mae-sai-command-timebar.tsx`, `mae-sai-map-kit.tsx`, `src/lib/flood-timeline-command.ts` | Unit: figures at hour 84 equal the export table (Mae Sai 5,660; district 7,086; 16,060 in water; 163.8 km). Rounding helper. Wording lint on source and rendered text. | 20 | Decision 1. May spill into Tuesday morning. |
| 2. Tue 6 Oct: the table | Both column groups; hysteresis and hold rules; tambon inspector with place-record counts; class cards with the "not issued yet" state; find-place box | New: `mae-sai-command-queue.tsx`, `mae-sai-command-inspector.tsx`. From E11 once merged: `src/lib/planning-assessment-overlay.ts` and `planning-protocol-binding.json` | Unit: order, ties, the 25-resident rule, hold, the order-change count over 264 hours. Component: empty states; "Class E never means safe" printed with every E (on fixture units) | 14 | E11 merged for the parser; if not, ship the empty state on a small typed stub and do not copy the parser. Real classes need E8, E1 and E5, and the O1 and O2 rights points. |
| 3. Wed 7 Oct: incidents and feed | Marker grammar and legend grid; popups; clusters; injects file; device reports sign with the `storage` listener; feed and event marks; "model dry" badge; report-page sentence | New: `mae-sai-command-markers.tsx`, `mae-sai-command-feed.tsx`, `src/lib/flood-timeline-command-feed.ts`, `flood-timeline-command-incidents.ts`, `public/exercises/mae-sai-2024/injects.v1.json`. Change: `src/components/public-report-page.tsx` (one sentence, competition build) | Unit: `knownBy(t)` never returns a future item; every marker state; the injects file passes the wording lint, holds no phone-number pattern and every id starts "EX-" | 18 | Decisions 4 to 7; a Thai speaker for the injects |
| 4. Thu 8 Oct: see to act | Access hint; nearest counted shelters; staging point; setup sheet and roster; states and waiting clock; brief sheet; exercise log and CSV | New: `mae-sai-command-brief.tsx`, `src/lib/flood-timeline-command-brief.ts`, `flood-timeline-command-log.ts`. Optional: the SOS practice mark in `src/components/public-sos-page.tsx` | Unit: brief starts and ends with the exercise tag, never contains rain values or report notes, and the SMS link has no recipient; state machine; nearest-node lookup; callsign rule | 14 | Phase 3 |
| 5. Fri 9 Oct: tablet, offline, check | 1024 px layout pass; help sheet; replay data kept from Command; injects file in the install list; hillshade fallback; timed five-question test; Thai string review | CSS module; the page posts the worker's existing `FLOODGUARD_CACHE_CASE_REPLAY` message; `scripts/write-offline-assets.mjs`; the offline smokes | Full `pnpm verify:frontend`; the browser offline smoke on `/command/`; the timed test with two people | 14 | Thai reviewer; a tablet that finished the offline install on Wi-Fi |

Total: about 91 agent-hours, plus roughly 7 human hours (decisions, a daily review, Thai review, timed test). Monday is the heaviest day and needs two agents.

**Cut order if a day slips:**

1. The SOS practice mark.
2. Share and SMS on the brief (keep Copy).
3. The find-place box.
4. The envelope layer in hindsight mode.
5. Event marks on the track (keep the feed).

The owner's four decisions (two rankings, both cases labelled, `/command/` replaced, reports on the map) all land by Wednesday; nothing in the cut list touches them.

**Known gaps on Friday**

- The planning columns will show "not issued yet" unless E8 delivers an overlay with publication level "public".
- "Works offline on a tablet" holds only after the site's full offline install, which the merge report puts at 301 MB because of the evidence library (`docs/unified_lineage_merge_report.md`, item 12). A 12 MB budget module exists (`scripts/offline-install-budget.mjs`) but only its own test imports it. The replay's 6.2 MB of data is kept on request after the page has rendered online once. The street basemap is never cached.
- Command exists only in the competition build; the public-production build prunes the whole `command` route folder.
- One device, one operator: nothing is shared between devices in stage A.
- All Thai strings are drafts until reviewed.

**After Friday, in order**

1. Fill the planning columns from E8, SE1 first (a few hours once the files exist), and the Planning preset.
2. The road network for the browser and a modelled path.
3. Stage B relay.
4. Night theme and snapshot.
5. A shared map engine for Studio and Command.
6. Zone labels and reported command decisions, as a cited file.

## 12. Decisions for the owners

| # | Decision | Recommendation |
|---|---|---|
| 1 | Purpose and banner wording. The page is described as helping rescue teams coordinate, but the data's permitted use excludes emergency response. | Frame it as an exercise and after-action tool for rescue coordinators on the 2024 case. Use "not real-time" in the banner. Changing the permitted use would mean changing a signed data file and the project rules. |
| 2 | Routes and names. What happens to today's planning text page, to `/command/archive/` and `/command/cases/`, and what the header link is called (today "Planning" / "การวางแผน"). | Move today's text page to `/command/planning/` on Monday. Keep the other two and link them from the menu and the inspector. Name the header link "Command (exercise)"; the Thai term needs the reviewer (draft: ฝึกซ้อมสั่งการ). |
| 3 | Defaults for the two rankings. | Left: sort by lost shelter access for the shelters counted in 2024, all residents at road nodes, ties by residents in water, with "in water" as an equal column. Accept that this order changes only 9 times in the replay. Right: take the planning position from SE1, labelled as a scenario, because it is the only case likely to be publishable soon. Always show both chips. |
| 4 | Reports and SOS this week. | Ship stage A only: place records, injects, and same-device reports as tambon signs, with one added sentence on the report page. Treat the SOS practice mark as optional and first to cut; if kept, it follows the limits in section 6. No cross-device relay this week. |
| 5 | Exercise injects: who writes them and how many. | About 14, written by the team and reviewed by a Thai speaker: 2 life at risk, 4 urgent, 8 information. No real person's details, none copied from a real 2024 plea, each tagged "EX", never counted with real reports. |
| 6 | What the exercise shows of the future. | Trainee mode by default: place records appear at their publication time and the future is hatched. Hindsight mode is one switch away. The Studio replay's rule stays unchanged. |
| 7 | The 2024 pleas that news outlets reprinted (about seven place records). | Show them as place records with a "plea reported in news" tag, from a short reviewed id list, never as calls received. They describe real people without names, so the owners should approve the tag. |
| 8 | People. | Name the Thai reviewer now (the week depends on it), and the data controller before any stage B work. |

## What was checked for this plan

Read or recomputed directly this session by the critic:

- the GISTDA screenshot;
- `replay-wording-rules.json` (rules and allow list; both banner strings checked by hand);
- `timeline.json`: header, permitted use, phases, stage anchors, days, observations, lanes, access, shelters (all 19 records), reported depths (all 21 records), rainfall, VIIRS days, external checks, limitations, publication eligibility;
- `access-nodes.bin`: per-tambon figures for every hour, both scopes;
- `roads.geojson` (properties and connectivity), `facilities.geojson`, `tambons.geojson`, `exports/tambon_replay_summary.json`;
- the exported functions of the `flood-timeline*` libs, `flood-timeline-layout.ts`, `public-report.ts`, `use-public-reports.ts`, `public-sos-page.tsx`, `public-report-page.tsx`, `workspace-header.tsx`, `command/page.tsx`;
- the lint's file list, `vercel.json`, the offline scripts, every script line naming `/command/`;
- decision D7, guardrails GR3, GR5 and GR6, the lane display rules in `planning_protocol_v1a.json`;
- the E11 branch's file list and overlay document.

Taken from the scout reports without re-checking:

- the 2024 news chronology beyond what `timeline.json` quotes;
- the O2 rights level;
- the critical-links review state;
- the status of E8.

Not verified by anyone:

- the layout in a browser (all coverage figures are arithmetic);
- Thai SMS behaviour on Thai carriers;
- the size of a packed road network;
- the Thai strings, which are drafts;
- the names of the Thai rescue organisations in section 2;
- whether the new strings pass the lint when built (checked by hand against the patterns only).

---

## Changes made by the critic

**Data sources corrected**

1. Place records: the 12 located records sit on 9 map points, not 12. Tolerance is 100 to 400 m, not 150 to 400. The existing popup builder gives eight or more lines and already states the model comparison, so the six-line cap and the extra "dry ground" line were dropped for them.
2. "These are depth reports, not requests for help" was wrong: about seven records paraphrase pleas that news reprinted. I added decision 7 and a rule that injects never copy them.
3. Reported shelters: 19 records, 4 without coordinates, 12 counted in the access set. R04 was first used on 21 Sep, after the replay. "Nearest shelters" now uses the counted set, and a site is flagged before its first reported date.
4. Access scope named: 7,086 is the all-residents scope; Studio's default scope gives 5,400.
5. Added the base of the count: 58% of residents had no reported shelter in reach before the flood and can never count as lost. "In water" became an equal column.
6. Reported that the hourly order changes only 9 times in 264 hours and is all zeros for 155 of the 265 hourly positions. The slide animation and pending-moves counter were removed; decision 3 was updated.
7. Feed times: two of the four satellite scenes pre-date the replay; the agency figures have no time field; UNOSAT 3991 cannot be "known from 13 Sep" and moved to hindsight; VIIRS cloud shares corrected; the calibration tag added where the item was used to tune the model.
8. Staging pick-list reduced, because the OSM emergency points are partly unnamed.
9. `ACTION_TEXT` is at lines 27-33 and not exported. `popupFit` already lives in the lib, so three helpers move, not four.
10. GR5 is the blinding rule, not a ban on blending. Citations now name D7, `reason_blocked` and the overlay's no-cross-lane rule. The planning position is derived, not a field.
11. Scripts naming `/command/`: 17 files and 57 lines, not nine. The injects file and rendered panels are not linted automatically.
12. Offline: the 301 MB figure is confirmed in the merge report; the 12 MB budget module is not wired; the worker message to reuse is named.

**Honesty and safety**

13. Removed the "boat or wading" advice and relabelled the "nearest passable road" hint (no connectivity check, no bridge decks).
14. SOS practice mark: it now stores no household needs, sits below the real call buttons, uses a neutral sign and plain "nothing was sent" wording, expires in 24 hours and is first to cut. The line "This person was directed to 1784" was removed.
15. The exercise brief carries its tag on the first and last line, the SMS link has no recipient, and notes and place-record statements are excluded. The CSV gains a `simulated` column and inject ids start "EX-".
16. The watermark is tiled so any crop keeps it.
17. Removed the "differs" mark, which was a derived blend of the two rankings. The Planning preset now pauses the replay and never colours tambons beside moving water.
18. Added the model-limit chip for the recession days, the veil outside the district, the town-underestimate sentence, and a place-record count per tambon row.
19. "Cut off" renamed "lost shelter access" and defined. The invented "T+60 h" clock was replaced by the replay hour.
20. Privacy: a callsign rule, a reset that clears all keys, a report-page sentence in the competition build, and stage B consent, retention (72 hours proposed), controller and legal checks made concrete.

**Layout and targets**

21. Coverage computed from the original plan's own sizes:
    - 1440 x 900: 35.6% covered at rest; 49.9% with the right card open; 54.7% with the legend open too.
    - 1024 x 768: 38.3% covered at rest; 39.8% with the two-line Thai banner.
    - The original gave no open-card figure.
22. Two overlaps found in the original sizes: on a 1024 x 700 tablet with the Thai banner the left column ran 8 px into the time dock, and at 1440 x 800 the right card ran 4 px into the legend chip.
23. The table row content did not fit 380 px, and the Thai captions did not fit a 148 px card. Sizes were revised (left column 420 and 320, B1 164, rows 50 and 44, right card 520, fixed tool rail, legend and card never open together), and coverage was recomputed for both screen sizes.
24. Urgency and road state are no longer signalled by colour alone (symbol and size; line pattern). Short Thai table headers were specified.
25. Time-bar marks are not touch targets. Pixel density corrected (about 4 px per hour on desktop, under 3 on a tablet). Day chips and a drill speed added.
26. Targets made plausible: job 2 is 5 taps and 45 seconds; job 3 is 15 seconds; the acceptance test no longer hides the time jump.

**Build plan**

27. The route swap is its own Monday task with a second agent. The total rose from 75 to about 91 agent-hours. Night theme and snapshot moved out of the week. Find-place, the facilitator setup sheet and the scale bar were added as things a coordinator needs. The cut order protects the owner's four decisions.