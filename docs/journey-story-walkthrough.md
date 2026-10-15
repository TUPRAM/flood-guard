# FloodGuard `/journey/` — full walkthrough of the cinematic 3D story (briefing for discussion)

> Context for the reader: this describes a 3D story page that is built and working locally but is **not public yet**.
> Everything below comes from the current code on the branch `claude/cinematic-journey` (not merged). The reader cannot
> open the page, so this tries to describe exactly what a visitor would see and do.
>
> **Version 2 — character-driven.** The story now follows three fictional people (Lalita, Narin, Pim), each of whom has
> a reason to use one real FloodGuard page. Every feature a caption names was checked against the real page first; where
> the first draft of the character concept assumed a feature the page does not have, the story was changed instead
> (see section 9).

---

## 1. What FloodGuard is (the product the story is about)

FloodGuard Thailand is a geospatial decision-support prototype for flood **preparedness and rapid post-event
prioritisation**. It turns flood extent or flood probability into local decision information: exposed people and
facilities, roads likely to be cut, lost access to services (e.g. a household that can no longer reach its clinic),
an "Evacuation Equity Gap", shelter capacity versus demand, a subdistrict priority score (FPPS) and an A–E action class.

It is explicitly **not** a real-time sensor, not an official warning system and not a dispatch system. Every output
carries a timestamp, confidence and assumptions. The competition release is scoped to **Mae Sai district, Chiang Rai,
using the historical September 2024 flood**.

The web app (Next.js + TypeScript) has three real role-based surfaces, and the story connects all three:

| Real page | Route | Audience | What it is |
|---|---|---|---|
| Public app | `/public/` | Residents | Thai-first, mobile-first. Bottom tabs: **Home** (choose a planning area or search an address; historical planning priority with date and confidence), **Report** (save an observation on this device only — "not sent to an agency"; it also shows on this device's Command exercise map), **Shelter** (enter a destination you checked with an authority — "This app does not know its current capacity or operating status"; walking distance and a checklist), **Prepare** (household plan: needs such as children, older adults, regular medicine, mobility, pets, transport, each adding actions; kept on the device), **SOS** (official hotlines DDPM 1784, 1669, police; press-and-hold, then the phone's call/SMS app opens — "FloodGuard does not place the call"). |
| Case view | `/studio/cases/mae-sai-2024/` | Analysts / staff | Day-by-day replay of the Mae Sai flood, 9–19 Sept 2024: dated Sentinel-1/-2 imagery, a low-confidence terrain-model water reconstruction, hour-by-hour modelled road/facility/residents-in-water figures, walking access to shelters with its equity gap, shelters reported in 2024, a ranked shelter plan. Historical, not real time. |
| Command exercise | `/command/?t=36` | People who coordinate rescue | Full-screen map exercise / after-action replay of the same flood hour by hour (play, step, speed); a subdistrict table of this hour's modelled figures (it deliberately prints no score, priority or class; its planning-score column reads "Not issued yet"); rows where most residents had no shelter in reach before the flood; invented practice items tagged **EX** that the team assigns to team callsigns, briefs and closes; "trainee" mode (nothing later than the replay hour) vs "hindsight"; an exercise log and a situation brief; reports saved on this device. All stored on the device only. Banner on every screen: reconstruction, not real-time, not dispatch, low confidence. The story opens it at replay hour 36. |

## 2. What `/journey/` is, in one paragraph

A **scroll-/click-driven cinematic 3D story** (Three.js / WebGL) through an **illustrative, fictional Thai
neighbourhood**, told through three fictional people whose responsibilities connect:

| Person | Who | Their question | Their real page |
|---|---|---|---|
| **Lalita** | Resident; lives with her mother **Mali** (regular clinic appointments and medicine) and her daughter **Dao** (8). She takes Dao to school and Mali to her appointments. | "Can my family still get where they need to go?" | Public app — Home, Prepare, Shelter, Report, SOS |
| **Narin** | Planning officer at the district office. Has not seen every road or shelter himself; not every report is confirmed. | "What do we know, and what still needs checking?" | Case view (Mae Sai, September 2024) |
| **Pim** | District planning coordinator. Organises the team's discussion; does not hand decisions to a computer. | "What should our team review together first?" | Command exercise |

Rain and rising water cut the road between Lalita's home and her mother's clinic. Lalita makes a household plan, notes
what she sees, and calls the official hotline (simulated). In the story, requests like hers reach Narin at the district
office, who reviews the evidence; Pim then brings the team round the planning table to look at the whole district. At
four moments the camera pushes into a screen in the 3D world (Lalita's phone, Narin's monitor, Pim's planning table) and
that screen **becomes the real, working FloodGuard page**, which the visitor can then use. It is a presentation / pitch
piece that ties the three product surfaces into one narrative.

- Page title: *"FloodGuard journey: from a phone to a coordinated response"*.
- The home page `/` is unchanged; nothing links to `/journey/` yet — it is only reachable by URL.
- It is a **staff/competition-only route**: the public-production build deletes it together with `/command/` and
  `/studio/` (because the story depends on those pages). It is online-only (excluded from the offline installer).
- Bilingual: English and Thai (Thai copy still needs native review).

## 3. Structure at a glance

```
Opening
  → 01 Lalita's family     ─→ [REAL PAGE: public app on Lalita's phone, Home tab]
  → 02 Rain, and a plan    ─→ [REAL PAGE: public app, switched to the Prepare tab]
  → 03 The road · Narin    ─→ [REAL PAGE: Mae Sai 2024 case view on Narin's monitor]
  → 04 The district · Pim  ─→ [REAL PAGE: command exercise on Pim's planning table]
  → (Next from the end goes back to the start)
```

Internally the story is a timeline of 8 camera **segments** and 4 **stops** (real pages), grouped into 5 chapters:

| # | Segment / stop | Length (story units) | Chapter |
|---|---|---|---|
| 1 | `opening` | 1.0 | Opening |
| 2 | `everyday` | 1.4 | 01 Lalita's family |
| 3 | `enter-phone` | 1.0 | 01 |
| ■ | **stop `public`** → `/public/` | — | 01 |
| 4 | `conditions` | 1.6 | 02 Rain, and a plan |
| 5 | `return-phone` | 1.0 | 02 |
| ■ | **stop `public-prepare`** → `/public/` (Prepare tab) | — | 02 |
| 6 | `sos-signal` | 2.0 | 03 The road · Narin |
| 7 | `enter-monitor` | 1.0 | 03 |
| ■ | **stop `case`** → `/studio/cases/mae-sai-2024/?lang=…` | — | 03 |
| 8 | `aerial` | 2.2 | 04 The district · Pim |
| ■ | **stop `command`** → `/command/?t=36&lang=…` | — | 04 |

Total: 11.2 units. The camera moves at most 0.32 units/second, so a 1-unit segment takes at least ~3 s.

There are **15 caption "pause points"** plus the 4 real pages = **19 presses of "Next"** to go through the whole story.

## 4. The world (what is on screen)

All geometry, textures and lighting are **procedural** (generated in code at load time) except the two rigged people.

**Layout (metres; x = east, z = south):**
- A main **east–west road** (asphalt, dashed centre line, edge lines, kerbs and a raised footpath on the north side,
  concrete utility poles with crossarms and sagging wires, street lamps on every other pole).
- Six concrete side streets (sois) running north, and a back street behind the first rows of houses.
- **Lalita's home** (west, x ≈ −24): a recognisable two-storey house with a porch, garden wall and gate. Lalita stands
  at her gate facing the road, with Mali and Dao beside her.
- **The clinic** (east, x ≈ +26): reads as an essential service — raised floor, entrance portico with glazed doors,
  steps and an accessible ramp with handrails, standing-seam metal roof, a sign on the portico.
- **The swale** (x ≈ 2, between the two): a shallow drainage valley that crosses the road. This is where the road
  dips — the single weak point of the household–clinic connection.
- **A river/channel** to the south, beyond floodplain **rice paddies with bunds**.
- **Low hills** in the far north for depth in the establishing shot.
- **The district office** (the operations building) north of the neighbourhood (x ≈ 6, z ≈ −34): a modest planning office, deliberately
  *not* a sci-fi control room. Inside: timber floor, framed map board, rug, a desk with monitor, keyboard, mouse, mug,
  notepad, desk lamp, task chair, shelving with binders, a second workstation with a laptop, a plant, a whiteboard, a
  clock, a **planning table** (a large horizontal display) under a **skylight**, and warm interior lighting. It has an
  open south window that the camera flies through.
- A full neighbourhood of houses filling the blocks (hip/gable roofs with real thickness and overhangs, framed windows,
  doors with canopies, verandas, garden walls, water tanks, AC units).
- **Vegetation:** rain trees, round fruit trees (a mango tree by the home, a rain tree by the clinic), tall trees,
  coconut palms along the channel, shrubs along walls. Trees are automatically kept out of the camera's path.

**Tested spatial rule** (unit tests enforce it): the home and the clinic stay dry in every water state; the road stays
dry while water "rises"; only one stretch of road (through the swale) floods in the "affected" state. That is the whole
point of the story — *the buildings are fine, the connection between them is not.*

**Water states:** dry (−0.70 m), rising (+0.32 m), affected (+0.78 m). Water is depth-aware (shallow water is
see-through so the submerged road reads through it; deeper is opaque), muddier as it rises, with rain ripples.

**The "usual connection" overlay:** a soft teal band painted along the road lane from the home gate to the clinic steps,
with ring markers at both ends. The stretch through the swale is a separate band that floats on the water when the
road is covered and turns **amber and dashed** when the connection is affected.

**Look:** warm, muted palette from the FloodGuard brand (cream, muted green, teal, dark neutral); outdoor sky lighting
with a warm sun and soft shadows; no post-processing. Weather animates: sky goes from clear warm blue to grey overcast,
fog closes in, sun dims, rain streaks appear, the ground darkens with wetness.

**The people.** All five are rigged 3D models generated with Meshy from single images and simplified for the web
(~100k–300k → ~30k–57k triangles, ~18 MB total; Dao and Pim keep every UV seam, so they simplify less):
- **Lalita** (rigged) — a woman in warm-climate clothes at her garden gate, holding a phone in her right hand. She lowers
  and raises it during the story (a blend between a relaxed pose and a reading pose, plus breathing and small head
  movements). Her grip was rebuilt so no finger crosses the screen (the real page is drawn over the whole screen).
- **Mali** (rigged) — an older woman with grey hair in a low bun, a pale green blouse, a striped wrap skirt and a small
  cloth shoulder bag, standing just behind Lalita in the gate opening, slightly stooped, arms at her sides.
- **Dao** (rigged) — an 8-year-old in a white school blouse and navy pleated skirt, beside her mother, looking up at
  her.
- **Narin** (rigged) — a man in a teal shirt seated at the desk, hands on the keyboard, fingertips resting on the home
  row, breathing and tapping lightly, glancing at the screen.
- **Pim** (rigged) — a woman in a muted purple blouse with a plain lanyard standing at the far edge of the planning table, leaning over it
  with both hands on its edge, looking down at it.
- While the rigged models download (up to 9 s), or if one fails to load, simpler procedural figures stand in.

**Floating labels** (small cream pills projected onto 3D points): places — "Lalita's home", "Clinic", "Usual way to the
clinic", "Connection potentially affected" (amber), "District office (illustrative)", "Simulated call to hotline 1784 ·
nothing dialled" (amber); and people, while the camera is with them — "Lalita", "Mali, her mother", "Dao, her
daughter", "Narin", "Pim".

## 5. The interface layer (on top of the 3D)

- **Top bar:** "FloodGuard." wordmark (links to `/`), a **"Skip to the apps"** button, and an **EN / ไทย** toggle.
  The language is the same shared preference the real pages use.
- **Hero** (only at the very start): big two-line title *"One road. / Three people."*, subtitle *"Lalita looks after
  her mother and daughter. Narin checks what is known. Pim brings the district together. A fictional story, told
  through the real FloodGuard pages."*, buttons **Begin the story** and **Skip to the apps**, and a hint *"Scroll, swipe
  or use the arrow keys"*. A cream gradient scrim on the left keeps it readable.
- **Caption card:** a cream card with a coloured left edge for whose part of the story it is (Lalita terracotta, Narin
  teal, Pim purple), an optional uppercase eyebrow (e.g. "01 · MEET LALITA"), a small avatar circle with the person's
  initial and name, a headline sentence and 2–3 bullet points. The first caption of each person ("Meet …") also shows
  their role, "Fictional character", and their question in italics at the bottom. Designed to be read at your own pace
  *or* presented from.
- **Permanent tag:** *"Fictional people in an illustrative scenario · not a real place, not a forecast, not real-time
  data"*.
- **Over each real page:** a small closable note above the bottom bar with the person's avatar, the page name and a
  line saying whose page it is in the story (e.g. *"Real page · Prepare — Lalita's household plan. It stays on this
  device; nothing is sent."*), plus an amber warning where needed.
- **One bottom bar, always present** (also over the real pages): **←**, the chapter list (Opening, 01 Lalita's family,
  02 Rain, and a plan, 03 The road · Narin, 04 The district · Pim — current one highlighted, past ones marked done, each
  clickable), **↗** (only on a real page: open it as its own page), **→**. On a real page the → button's label becomes
  the continue action (e.g. "Continue: rain, and a plan", "Continue: the road").
- **Skip dialog:** "Go straight to a real FloodGuard page" — Public app, Case view, Command exercise; each can be
  jumped to inside the story or opened as its own page. Focus is trapped; Escape closes.
- **Loading:** "Preparing the neighbourhood…"; each real page shows "Loading the real page…" until its frame loads.

## 6. Controls and pacing ("presenter pacing")

The story **waits on every caption**. Nothing runs on by itself.

- **→ / Page Down / Space / a presentation clicker:** glide to the next caption or real page and stop there.
- **← / Page Up:** back one step. From the very start, ← wraps round to the end (the command exercise).
- **Mouse wheel / trackpad / touch swipe:** scrubs the camera, but **stops at every caption and every real page**.
  After arriving on a caption the story rests ~0.65 s and ignores the rest of that scroll gesture (trackpad momentum);
  only a new gesture after a short pause moves on. Scrolling can never pass a real page — you enter it and continue
  with an explicit button. Scrolling backwards is free.
- **↑ / ↓ arrows:** small scrub steps. **Home:** back to the start.
- **While a real page is open:** the page gets the mouse, wheel, arrows and space for itself; only Page Up / Page Down
  (and the bottom bar) move the story — so a clicker still works during a presentation.
- **Chapter buttons** jump to that chapter. Long jumps (more than 2.6 units) use a quick cream cross-fade instead of a
  long flight.
- **Address bar:** `?scene=` records where you are (`opening`, `everyday`, `conditions`, `affected`, `response`,
  `public`, `public-prepare`, `case`, `command`), so a link can open the story at any chapter or real page, and browser
  Back/Forward move through the story. Entering a real page adds a history entry.

## 7. Scene-by-scene walkthrough (what the visitor sees)

### Opening
- **Camera:** very high and far to the south-west, slowly gliding to a wide establishing view of the whole
  neighbourhood: road, houses, paddies, river, hills, the district office at the back. Sunny, warm, dry.
- **On screen:** the hero — *"One road. Three people."* As the camera settles, the teal "usual way to the clinic" line
  fades in along the road and the labels **Lalita's home**, **Clinic**, **Usual way to the clinic** appear.
- **Begin the story** glides straight to the first caption.

### Chapter 01 — Lalita's family
**Segment `everyday`**: one calm descent from the wide view to Lalita at her gate.
- **Pause 1 — Meet Lalita** (mid-descent; her house, the clinic and the teal line are labelled):
  - Eyebrow *01 · Meet Lalita*; person line *Lalita — Resident · looks after her mother and daughter · Fictional
    character*
  - **"This is Lalita's street. She lives here with her mother, Mali, and her eight-year-old daughter, Dao."**
  - *Mali has regular appointments at the clinic down the road.* / *Lalita takes Dao to school and Mali to her
    appointments.* / *The teal line is their usual way to the clinic.*
  - Question: *"Can my family still get where they need to go?"*
- The camera arrives in front of Lalita at about head height. **Mali and Dao stand with her in the gate opening**
  (labelled "Mali, her mother" and "Dao, her daughter"). Lalita raises her phone; its screen lights up and the real
  public app begins to appear on it.
- **Pause 2:** **"Heavy rain is expected. Before the rumours start, Lalita checks what is known about her area."**
  - *She opens the FloodGuard public app.* / *It helps her prepare. It is not an official warning.*

**Segment `enter-phone`**: the camera goes round her right shoulder, into an over-the-shoulder view of the phone, then
pushes straight onto the screen until the phone fills ~74% of the window height with its black border visible.
- **Pause:** **"This is the real public app: what Lalita sees on her phone."**
  - *She chooses a planning area, or searches for an address.* / *It shows a historical planning priority, with its
    date and confidence.* / *A historical priority is not a prediction that her street will flood.*

**■ Real page 1 — Public app, Home tab (`/public/`)**
- The page docks: it animates from the phone's screen out to the whole window and becomes fully interactive.
- Page note: *"Real page · Public app — Lalita's first look. The app's data covers Mae Sai district; her street in this
  story is illustrated."*
- → = **"Continue: rain, and a plan"**.

### Chapter 02 — Rain, and a plan
**Segment `conditions`**: the page goes back onto the phone; the camera pulls back past her and settles on a slightly
elevated **road shot** looking along the road toward the low dip, the home on one side and the clinic on the other. She
half-lowers the phone. Rain starts, the sky turns overcast, the ground darkens, and the water rises from dry to "rising":
the channel fills, the paddies and low ground pond, the dip pools — but the road stays dry.
- **Pause 1:** eyebrow *02 · Rain, and a plan* — **"The rain sets in. The channel rises and low ground begins to pond."**
  - *Water collects first where the ground is lowest.* / *Lalita's house stands on higher ground and stays dry.* /
    *An illustrative scenario, not a forecast.*
- **Pause 2:** **"The road is still dry. But it dips through the lowest ground, on Mali's way to the clinic."**
  - *If that stretch floods, the clinic is cut off from the house.* / *Lalita cannot control the weather.* / *She can
    make a plan before she needs one.*

**Segment `return-phone`**: the camera comes down to the gate and **holds on the family**: Lalita (phone lowered),
Dao beside her and Mali just behind, all three labelled by name, the house and its porch behind them.
- **Pause 1:** **"Lalita talks it through with Mali and Dao: what to pack, who helps whom, where they could go."**
  - *Mali needs her regular medicine with her.* / *Dao needs a grown-up she knows, and a place to meet.* / *They agree
    how they will follow official updates.*
  (These mirror real Prepare-tab actions: a medicine bag, a named child-support person and a meeting place, agreeing how
  to follow official updates.)
- Lalita raises the phone; the camera goes round her shoulder and onto the screen, which **the story has switched to
  the app's Prepare tab**.
- **Pause 2:** **"She writes it into her household plan in the app."**
  - *Prepare: a child, an older adult and regular medicine each add their own actions.* / *Shelter: she enters a place
    she has checked with the authorities. The app does not know if it is open or full.* / *SOS: the official
    hotlines, kept in one place.*

**■ Real page 2 — Public app, Prepare tab (stop `public-prepare`)**
- Same working app (whatever the visitor did at stop 1 is still there), now on **Prepare**: "Build and review my
  preparedness plan" — choose a planning area, review household needs, work through the plan's steps.
- Page note: *"Real page · Prepare — Lalita's household plan. It stays on this device; nothing is sent."*
- Amber warning: *"The SOS tab's buttons open your phone's call or message app with real hotline numbers. The story
  never uses them."*
- → = **"Continue: the road"**.

### Chapter 03 — The road · Narin
**Segment `sos-signal`**
- **Pause 1** (camera just leaving the phone): eyebrow *03 · The road* — **"Lalita notes what she sees in Report:
  water in the low part of the road."**
  - *The note stays on her phone. FloodGuard sends it nowhere.* / *Asking for help goes through official channels.*
- The camera returns to the road shot and holds while the water rises to "affected": it spreads across the dip in the
  road. The crossing section of the teal line now floats on the water and turns **amber and dashed**. Labels: Lalita's
  home, Clinic, **"Connection potentially affected"**.
- **Pause 2:** **"Now the water crosses the road. Lalita's home and the clinic stay dry; the way between them does
  not."**
  - *Both buildings stand on higher ground.* / *The low stretch of road between them is under water.* / *Lost access,
    not only flooding, is what FloodGuard looks at.*
- The camera rises to a high overview. An **amber arc** with a pulsing head travels from Lalita up over the town to the
  district office's window, labelled **"Simulated call to hotline 1784 · nothing dialled"**; the office is labelled
  **"District office (illustrative)"**. The rain starts to ease.
- **Pause 3:** **"Mali needs to see her doctor. Lalita calls the official hotline, 1784, to ask how to get her there."**
  - *Story mode: the call is simulated. Nothing is dialled.* / *The call goes through the hotline, not through
    FloodGuard.* / *In this story, requests like hers reach the district office.*
- The camera glides through the office's open window and settles behind and to the side of Narin at his desk
  (labelled "Narin").
- **Pause 4 — Meet Narin:** person line *Narin — Planning officer · district office · Fictional character*
  - **"Narin is a planning officer at the district office. Calls like Lalita's are part of what he has to make sense
    of."**
  - *He has not seen every road or shelter himself.* / *Not every report is confirmed.* / *Before anyone acts, he
    looks at the evidence.*
  - Question: *"What do we know, and what still needs checking?"*

**Segment `enter-monitor`**: over Narin's right shoulder (his hands on the keyboard and the monitor in frame), past his
shoulder, and square onto the monitor until it fills ~86% of the window; the real case view fades in on it.
- **Pause:** **"Narin opens the case view: a real, past flood in Mae Sai, September 2024. It is not Lalita's street."**
  - *He replays it day by day, with dated satellite images.* / *Modelled water, roads, facilities and residents in
    water, each marked low confidence.* / *Who could walk to a shelter, and who could not: the equity gap.*

**■ Real page 3 — Case view (`/studio/cases/mae-sai-2024/`)**
- Docks to the full window (seamless on a normal landscape desktop window).
- Page note: *"Real page · Case view — Narin's evidence. Mae Sai, September 2024: historical, reconstructed, low
  confidence. Not the illustrated street."*
- → = **"Continue: the district"**.

### Chapter 04 — The district · Pim
**Segment `aerial`**
- The camera steps back from the monitor, past Narin, to a view over the **planning table**, where **Pim** stands at the
  far edge, leaning over it with both hands on its edge (labelled "Pim").
- **Pause 1 — Meet Pim:** eyebrow *04 · Meet Pim*; person line *Pim — District planning coordinator · Fictional
  character*
  - **"Pim coordinates planning for the district. Narin's evidence is one input; she has many communities to think
    about."**
  - *Her job is to organise the discussion, not to hand it to a computer.* / *She brings the team round the planning
    table.*
  - Question: *"What should our team review together first?"*
- The camera rises **straight up through the skylight**, north-up, to a top-down map view of the area from ~92 m. The
  sky partly clears and the rain stops. Framed so the whole of Lalita's route is visible above the caption: **Lalita's
  home**, the amber **"Connection potentially affected"** crossing, the **Clinic**, and the **District office** at the top.
- **Pause 2:** **"From above, Lalita's road is one of many links between people and the services they need."**
  - *Every household–service link can be checked the same way.* / *Cut links show where help may not get through.*
- The camera comes straight back down through the skylight onto the planning table (Pim is seen from above at its top
  edge); the real command exercise fades in on the table.
- **Pause 3:** **"Pim runs it as an exercise: the team replays the flood hour by hour and practises what they would
  do."**
  - *Each subdistrict's modelled figures, hour by hour.* / *Practice incidents, marked EX, are assigned to team
    callsigns.* / *People decide. The tool dispatches no one.*

**■ Real page 4 — Command exercise (`/command/?t=36`)**
- Docks to the full window, opened at replay hour 36.
- Page note: *"Real page · Command exercise — Pim's planning table. An exercise replay for review and coordination:
  not real-time, not dispatch. Reports saved on this device appear here too."*
- → from here goes back to the start of the story (with a cross-fade).

## 8. How the "3D screen becomes the real page" trick works

- Each real page runs in its own **same-origin `<iframe>`** (so its routing, URL and state stay its own). There are
  three hosts: phone, monitor, table.
- While the camera moves, the stage projects the 3D screen's four corners to the window and the iframe is warped onto
  them with a CSS `matrix3d` **homography**, so the live page appears drawn on the phone / monitor / table in
  perspective (it fades in on cue).
- Each camera push ends at a pose where the screen sits square-on and fills a fixed share of the window
  (phone 74%, monitor/table 86%). At the stop, the iframe is **"docked"**: it animates from that rectangle to the full
  window and receives input. 3D rendering pauses while a page is docked (the last frame stays visible under the
  see-through bottom bar). Leaving reverses the animation back onto the screen.
- The public app is laid out at a real phone size while on the phone. The monitor/table pages are laid out at the
  window's size when the window is landscape (aspect 1.2–2.2), otherwise at 1280×800.
- Pages are lazy-loaded just before they are needed. Switching language never reloads a page already open.
- Security: the site headers allow same-origin framing only (`X-Frame-Options: SAMEORIGIN`, `frame-ancestors 'self'`).

## 9. Honesty and safety built into the story

- Permanent "Fictional people in an illustrative scenario · not a real place, not a forecast, not real-time data" tag;
  each person's first caption says "Fictional character".
- **Only real features.** Each feature a character uses was checked against the real page. Three points of the first
  character concept were changed because the pages do not work that way:
  1. *A simulated SOS from the app to the operations room* was dropped: the app's SOS tab only opens the phone's call
     or message app with official hotline numbers, and Report saves on the device and is "not sent to an agency".
     Instead Lalita saves a report (it stays on her phone) and **calls the official hotline 1784 (simulated)**; in the
     story, requests like hers reach the district office *through the hotline, not through FloodGuard*.
  2. *Pim reviewing FPPS scores and A–E action classes in the command exercise* was dropped: the exercise deliberately
     prints no score, priority or class (its planning score reads "Not issued yet"). Pim uses what it has: hourly
     subdistrict figures, practice items (EX) assigned to team callsigns, trainee mode.
  3. *Lalita choosing a shelter* became *entering a place she checked with the authorities*, because the app says it
     does not know a shelter's capacity or whether it is open.
- The first public-app stop says the app's data covers Mae Sai district while Lalita's street is illustrated; Narin's
  caption and page note say the case view is a separate, historical Mae Sai 2024 case, not Lalita's street.
- While the Prepare stop is open, an amber note warns that the SOS tab's buttons open the phone's call or message app
  with real hotline numbers, and that the story never uses them.
- No transition creates a report, case change or dispatch; the story never fires the real SOS.
- A test runs every story string, in both languages, through the same wording lint the real pages use (no claims of
  real time, forecasts, official warnings or validation), and checks each person is introduced before their captions
  and page.

## 10. Accessibility and fallbacks

- **Reduced motion** (OS setting): camera flights become cross-fades between discrete story beats.
- All controls are real buttons/links with visible focus; skip dialog traps focus; screen-reader announcement when a
  real page opens; captions are `aria-live`.
- **No WebGL / GPU context lost:** a text version of the story — the four chapters with their captions and a link to
  each real page.
- **Low-power devices** (window < 700 px, < 4 CPU cores or < 4 GB memory) get a lighter quality path; resolution adapts
  automatically to hold frame rate; phones use a wider field of view.

## 11. Tech summary

- Next.js app (`apps/web`), React client component + Three.js; no new dependencies were added.
- Code: `src/app/journey/page.tsx`; `src/components/journey/` (UI `journey-experience.tsx`, copy `journey-copy.ts`,
  styles) and `stage/` (camera & scene `journey-stage.ts`, `world.ts`, `architecture.ts`, `operations.ts`,
  `vegetation.ts`, `materials.ts`, `characters.ts`, `figure.ts`); pure logic in `src/lib/journey/` (`timeline.ts`,
  `terrain.ts`, `screen-projection.ts`, `reach.ts`). ~7,300 lines.
- Camera: per-segment keyframes, Catmull-Rom paths, each glide eases in and out and settles ("calm, single glides";
  no orbits or swoops).
- Tests: timeline/navigation rules, screen projection, the terrain flood rule, two-bone IK, character fitting
  (Lalita's hand never in front of the phone; Narin's fingertips on the keys, feet on the floor), and the story copy
  (wording lint in both languages; each person introduced before their part; the call stays simulated). A CSP smoke
  test loads `/journey/` and `/journey/?scene=case` under production headers.
- Performance (Intel Iris Xe laptop, 1440×900): the 3D frame costs ~2–9 ms; whole-page 20–60 fps, the remaining cost
  being the live pages inside the iframes.

## 12. Known limitations / open points (good topics to discuss)

1. **Not public:** only in the staff/competition build, not linked from anywhere, branch not merged.
2. **Characters:** Lalita and Narin are single-image AI-generated models (Meshy); licence for publishing must be
   confirmed. Phone raise is a blend between two held poses (not motion capture); typing is an in-place tap. Mali, Dao
   and Pim (Meshy, Premium plan, so owned and private) each hold one pose fitted in the scene.
3. **Phone hand-off reflow** on desktop: the public app widens from a phone column to full width when docked.
4. **Portrait phones:** monitor and table hand-offs fade rather than fly seamlessly.
5. **Hidden iframes keep running**, which lowers frame rates on low-end laptops.
6. The illustrative landscape is **not Mae Sai terrain** — the story deliberately switches from a fictional street to
   a real historical case at the case-view stop; whether that jump reads clearly is worth testing with viewers.
7. Thai copy needs native review (including the characters' names: ลลิตา, มะลิ, ดาว, นรินทร์, พิมพ์).
8. Possible upgrades: better phone model, a unified building kit, photo-scanned trees (licences permitting).
9. **Same-device link not yet shown in the story:** a report the visitor saves in the public app during the story
   really does appear on the command exercise map (same device), but the story only mentions it in Pim's page note.
10. The public app inside the story opens in its own default language (Thai) unless the visitor has switched language
    before; the story's EN/ไทย toggle sets the shared preference.
11. Lalita, Mali and Dao don't talk or gesture to each other; the "talking it through" beat is carried by the caption
    while they stand together.
