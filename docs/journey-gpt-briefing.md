# FloodGuard `/journey/` — complete briefing with code (for discussion)

> **How to read this.** I am building a 3D story page for my FloodGuard project. It is not public yet, so you cannot
> open it. This document is everything you need to understand it as it is *today*:
>
> - **Part A** describes what a visitor sees and does, scene by scene, with every caption word for word.
> - **Part B** explains the architecture: files, how the parts talk to each other, and the rules the code enforces.
> - **Part C** is the actual source code of the important parts, copied verbatim from the repository (file and line
>   numbers given), so you can reason about real code rather than a summary.
> - **Part D** lists open questions I want to discuss.
>
> State: branch `claude/cinematic-journey`, uncommitted working tree as of 14 Oct 2026. Stack: Next.js 16 (App
> Router, Turbopack), React, TypeScript, Three.js, CSS modules, Vitest.

---

# Part A — What the visitor experiences

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

**The people.** Two are rigged 3D models (generated with Meshy from single images, simplified for the web ~300k → ~40k
triangles, ~5.5 MB total); three are simpler procedural stand-in figures until rigged models of them exist:
- **Lalita** (rigged) — a woman in warm-climate clothes at her garden gate, holding a phone in her right hand. She lowers
  and raises it during the story (a blend between a relaxed pose and a reading pose, plus breathing and small head
  movements). Her grip was rebuilt so no finger crosses the screen (the real page is drawn over the whole screen).
- **Mali** (stand-in) — an older woman with grey hair in a bun and a muted green blouse, standing just behind Lalita in
  the gate opening, slightly stooped.
- **Dao** (stand-in) — an 8-year-old in a white school shirt and navy trousers (a scaled figure with a child's larger
  head), beside her mother, looking up at her.
- **Narin** (rigged) — a man in a teal shirt seated at the desk, hands on the keyboard, fingertips resting on the home
  row, breathing and tapping lightly, glancing at the screen.
- **Pim** (stand-in) — a woman in a muted purple top standing at the far edge of the planning table, leaning over it
  with both hands on its edge, looking down at it.
- While the rigged models download (up to 9 s), procedural figures stand in for Lalita and Narin too.

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
   confirmed. Phone raise is a blend between two held poses (not motion capture); typing is an in-place tap. **Mali, Dao
   and Pim are simpler procedural stand-ins** and look noticeably less detailed; rigged models for them would replace
   them through the same pipeline.
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

---

# Part B — Architecture

## B1. Files

```
apps/web/src/
├── app/journey/page.tsx                         15 lines  Route: metadata + <JourneyExperience/>
├── components/journey/
│   ├── journey-experience.tsx                  ~890 lines  React shell: input, pacing, captions, docking real pages, history
│   ├── journey-copy.ts                         ~330 lines  ALL story text (EN/TH): people, captions, labels, stop notes
│   ├── journey-copy.test.ts                     ~75 lines  Copy tests: wording lint, people introduced in order, call simulated
│   ├── journey.module.css                      ~350 lines  Styles for the overlay UI (captions, cards, bars, notes)
│   └── stage/                                              Three.js scene (loaded lazily, client only)
│       ├── journey-stage.ts                   ~1000 lines  The stage: builds the world, camera choreography, per-frame story state
│       ├── world.ts                            ~975 lines  Terrain, water, roads, route overlay, phone, rain, sky
│       ├── architecture.ts                     ~505 lines  Procedural houses and the clinic (merged per material)
│       ├── operations.ts                       ~440 lines  The district office interior: desk, monitor, chair, planning table
│       ├── vegetation.ts                       ~420 lines  Instanced trees/palms/shrubs kept clear of the camera path
│       ├── materials.ts                        ~415 lines  Palette, procedural textures, geometry helpers
│       ├── characters.ts                       ~500 lines  Rigged GLB people (Lalita, Narin): load, fit grip/seat, pose
│       ├── characters.test.ts                  ~260 lines  Hand never in front of the phone; fingertips on keys; feet on floor
│       ├── figure.ts                           ~620 lines  Procedural people (fallbacks; stand-ins for Mali, Dao, Pim), IK
│       └── terrain-glsl.ts                      ~30 lines  GLSL copy of the terrain height function
├── lib/journey/                                            Pure logic, no DOM/Three.js, unit-tested
│   ├── timeline.ts                             ~190 lines  Segments, stops, chapters, scroll clamping, eased stepping, ?scene=
│   ├── terrain.ts                              ~115 lines  Height field + water levels; "home & clinic stay dry" rule
│   ├── screen-projection.ts                     ~80 lines  CSS matrix3d homography: page → projected 3D screen quad
│   ├── reach.ts                                 ~60 lines  Two-bone IK solver (elbow/knee placement)
│   └── journey.test.ts                         ~200 lines  Tests for the four modules above
public/journey/characters/{phone-woman,office-man}.glb      ~5.5 MB rigged models (built by scripts/build-journey-characters.mjs)
```

## B2. How the parts talk to each other

```
            wheel / touch / keys / buttons
                        │
                        ▼
  journey-experience.tsx  ── motion.target (story position, 0 … 11.2 units)
        │   each animation frame: motion.display eases toward target (max 0.32 units/s)
        │
        ├─► stage.update(display, dt) ──► journey-stage.ts
        │        • locate(t) → segment + progress p (timeline.ts)
        │        • per-segment story state: water level, rain, overcast, phone raise, labels, which screen shows a page
        │        • camera = samplePath(keysFor(segment), p)
        │        • renders WebGL; returns { screens: {phone|monitor|table: quad+opacity}, labels: [x,y,visible] }
        │
        ├─► for each screen: iframe host gets CSS matrix3d(quad) → the real page is drawn "on" the 3D phone/monitor/table
        ├─► labels (DOM pills) positioned at projected 3D points
        ├─► caption = CAPTIONS[segment] whose [from,to) contains p  (React state only changes when something visible changes)
        ├─► public-app tab: Home before stop 1, Prepare from the "return-phone" segment on (replaceState + popstate in the frame)
        └─► when display reaches a stop exactly: DOCK the iframe (animate to full window, give it input, pause 3D rendering)
                       → "Next" on a docked page: undock, glide to the next caption pause
```

Key ideas:

1. **One number drives everything.** The story is a single position on a timeline. Scrolling, keys and buttons only
   change the *target*; the displayed position eases toward it. Everything in the 3D scene (camera, water, weather,
   poses, labels) is a pure function of `(segment, progress)`, so scrubbing backwards works for free.
2. **Presenter pacing.** Every caption has a `pause` point; Next/Previous jump between pauses and real pages; scrolling
   stops at each pause and needs a fresh gesture to continue; scrolling can never pass a real page.
3. **Real pages, not mock-ups.** Each real route lives in its own same-origin iframe (lazy-mounted). It is warped onto
   a 3D screen with a homography while the camera moves; when the camera is square-on, it docks to the full window.
4. **Copy is data.** All words live in `journey-copy.ts` (typed, bilingual), so the story can be rewritten without
   touching the 3D code, and tests can lint it.
5. **Honesty is tested.** The copy test runs every string (EN and TH) through the project's shared wording lint (bans
   claims of real time, forecasting, official warnings, validation, unless negated), checks each person is introduced
   before their part, and that the hotline call stays simulated and outside FloodGuard.

## B3. Timeline numbers

| Segment / stop | Starts at | Length | Caption pauses (absolute position) |
|---|---|---|---|
| opening | 0.0 | 1.0 | — |
| everyday | 1.0 | 1.4 | 1.644 (Meet Lalita), 2.379 |
| enter-phone | 2.4 | 1.0 | 3.32 |
| **stop public** | 3.4 | — | real page |
| conditions | 3.4 | 1.6 | 4.248, 4.92 |
| return-phone | 5.0 | 1.0 | 5.45 (family shot), 5.92 |
| **stop public-prepare** | 6.0 | — | real page (Prepare tab) |
| sos-signal | 6.0 | 2.0 | 6.12, 6.94, 7.44 (hotline call), 7.97 (Meet Narin) |
| enter-monitor | 8.0 | 1.0 | 8.93 |
| **stop case** | 9.0 | — | real page |
| aerial | 9.0 | 2.2 | 9.484 (Meet Pim), 10.32 (map), 11.09 |
| **stop command** | 11.2 | — | real page |

Development builds expose `window.__journeySeek(t)` to jump the camera to any position (used for visual review).

## B4. What changed in this version (character-driven rewrite)

- `journey-copy.ts`: new `CHARACTERS` (Lalita, Narin, Pim with name, role, question); captions gained `who` and
  `meet`; all captions rewritten around the people; new person labels; stops gained `who`, `tab` and a `warning`.
- `timeline.ts`: stop `public-sos` renamed `public-prepare`.
- `journey-experience.tsx`: caption card shows the person (avatar, name, role, question); a closable note over each
  real page (whose page, what it is, warning); the public app is switched to the right tab (Home / Prepare) without
  adding browser history; the stop warning is announced to screen readers.
- `journey-stage.ts`: procedural stand-ins for Mali and Dao at Lalita's gate and Pim at the planning table (hands on
  its edge via IK); a held "family" camera shot; name labels anchored above heads; the room shot aimed to frame Pim;
  the overhead map shot moved so Lalita's whole route sits clear of the caption; the arc is now the simulated hotline call.
- `journey-copy.test.ts`: new.

---

# Part C — Source code (verbatim)

## C1. Pure story logic

#### `apps/web/src/lib/journey/timeline.ts`

The story timeline: segments, real-page stops, chapters, scroll clamping, eased stepping and `?scene=` links. Pure and unit-tested.

```ts
/**
 * The cinematic journey's story timeline: an ordered list of camera segments (scrubbed by scroll, touch or keys) and
 * stops where a real FloodGuard page takes over the viewport. Pure: no DOM, no Three.js, so the navigation rules are
 * unit-tested. Positions are in "story units"; a segment's length sets how much scrolling it takes.
 */

export type SegmentId =
  | "opening"
  | "everyday"
  | "enter-phone"
  | "conditions"
  | "return-phone"
  | "sos-signal"
  | "enter-monitor"
  | "aerial";

export type StopId = "public" | "public-prepare" | "case" | "command";

export type ChapterId = "opening" | "everyday" | "conditions" | "affected" | "response";

export type TimelineItem =
  | { kind: "segment"; id: SegmentId; length: number; chapter: ChapterId }
  | { kind: "stop"; id: StopId; chapter: ChapterId };

export const TIMELINE: readonly TimelineItem[] = [
  { kind: "segment", id: "opening", length: 1, chapter: "opening" },
  { kind: "segment", id: "everyday", length: 1.4, chapter: "everyday" },
  { kind: "segment", id: "enter-phone", length: 1, chapter: "everyday" },
  { kind: "stop", id: "public", chapter: "everyday" },
  { kind: "segment", id: "conditions", length: 1.6, chapter: "conditions" },
  { kind: "segment", id: "return-phone", length: 1, chapter: "conditions" },
  { kind: "stop", id: "public-prepare", chapter: "conditions" },
  { kind: "segment", id: "sos-signal", length: 2, chapter: "affected" },
  { kind: "segment", id: "enter-monitor", length: 1, chapter: "affected" },
  { kind: "stop", id: "case", chapter: "affected" },
  { kind: "segment", id: "aerial", length: 2.2, chapter: "response" },
  { kind: "stop", id: "command", chapter: "response" },
];

export const CHAPTERS: readonly ChapterId[] = ["opening", "everyday", "conditions", "affected", "response"];

interface Placed { item: TimelineItem; start: number; end: number }

const PLACED: readonly Placed[] = (() => {
  let at = 0;
  return TIMELINE.map((item) => {
    const start = at;
    if (item.kind === "segment") at += item.length;
    return { item, start, end: at };
  });
})();

/** Start and end of a camera segment on the timeline. */
export function segmentRange(id: SegmentId): { start: number; end: number } {
  const placed = PLACED.find((entry) => entry.item.kind === "segment" && entry.item.id === id)!;
  return { start: placed.start, end: placed.end };
}

/** Total story length in units (the position of the final stop). */
export const TIMELINE_END = PLACED[PLACED.length - 1].end;

/** Position of a stop on the timeline. */
export function stopPosition(id: StopId): number {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && entry.item.id === id);
  if (!placed) throw new Error(`Unknown stop: ${id}`);
  return placed.start;
}

/** Position where a chapter begins (its first item). */
export function chapterStart(chapter: ChapterId): number {
  const placed = PLACED.find((entry) => entry.item.chapter === chapter);
  if (!placed) throw new Error(`Unknown chapter: ${chapter}`);
  return placed.start;
}

export interface Location {
  segment: SegmentId;
  /** Progress within the segment, 0..1. */
  progress: number;
  chapter: ChapterId;
}

/** The segment and progress at timeline position `t` (clamped to the story). A stop resolves to the segment before it, at progress 1. */
export function locate(t: number): Location {
  const position = Math.min(TIMELINE_END, Math.max(0, t));
  const segments = PLACED.filter((entry): entry is Placed & { item: Extract<TimelineItem, { kind: "segment" }> } => entry.item.kind === "segment");
  for (const entry of segments) {
    if (position <= entry.end || entry === segments[segments.length - 1]) {
      const progress = entry.item.length > 0 ? (position - entry.start) / entry.item.length : 1;
      const clamped = Math.min(1, Math.max(0, progress));
      return { segment: entry.item.id, progress: clamped > 1 - 1e-9 ? 1 : clamped, chapter: entry.item.chapter };
    }
  }
  throw new Error("unreachable");
}

/** The chapter a timeline position belongs to; a stop belongs to the chapter of the segments that lead into it. */
export function chapterAt(t: number): ChapterId {
  const stop = stopAt(t);
  if (stop) return TIMELINE.find((item) => item.kind === "stop" && item.id === stop)!.chapter;
  return locate(t).chapter;
}

/** The stop exactly at `t` (within a small tolerance), if any. */
export function stopAt(t: number, tolerance = 1e-4): StopId | null {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && Math.abs(entry.start - t) <= tolerance);
  return placed && placed.item.kind === "stop" ? placed.item.id : null;
}

/** The first stop strictly after `t`, or null after the last stop. */
export function nextStopAfter(t: number, tolerance = 1e-4): StopId | null {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && entry.start > t + tolerance);
  return placed && placed.item.kind === "stop" ? placed.item.id : null;
}

/** The last stop strictly before `t`, or null before the first stop. */
export function previousStopBefore(t: number, tolerance = 1e-4): StopId | null {
  const stops = PLACED.filter((entry) => entry.item.kind === "stop" && entry.start < t - tolerance);
  const last = stops[stops.length - 1];
  return last && last.item.kind === "stop" ? last.item.id : null;
}

/**
 * Where a scroll-driven target may move to from `current`: scrolling forward cannot pass the next stop (the visitor
 * enters the real page there and continues with an explicit control); scrolling backward is free.
 */
export function clampScrollTarget(current: number, requested: number): number {
  const bounded = Math.min(TIMELINE_END, Math.max(0, requested));
  if (bounded <= current) return bounded;
  const next = nextStopAfter(current);
  if (next === null) return bounded;
  return Math.min(bounded, stopPosition(next));
}

/**
 * One animation step of the displayed position toward the target: an eased approach, capped at `maxSpeed` units per
 * second so fast scrolling or a chapter "continue" never whips the camera. Snaps when within `epsilon`.
 */
export function stepToward(display: number, target: number, dt: number, maxSpeed = 0.32, smoothing = 4, epsilon = 1e-4): number {
  const gap = target - display;
  if (Math.abs(gap) <= epsilon) return target;
  const eased = gap * (1 - Math.exp(-smoothing * Math.max(0, dt)));
  const cap = maxSpeed * Math.max(0, dt);
  const step = Math.sign(eased) * Math.min(Math.abs(eased), cap);
  // Never stall: guarantee a minimum crawl so the approach finishes.
  const minimum = Math.min(Math.abs(gap), 0.02 * Math.max(0, dt));
  return display + Math.sign(gap) * Math.max(Math.abs(step), minimum);
}

/**
 * Discrete story beats for reduced motion: each segment's start and middle, every chapter entry and every stop, in
 * order. Stepping beat to beat reaches every stop, including the last one.
 */
export function storyBeats(): number[] {
  const beats = new Set<number>();
  for (const entry of PLACED) {
    if (entry.item.kind === "segment") {
      beats.add(entry.start);
      beats.add(entry.start + entry.item.length / 2);
    } else beats.add(entry.start);
  }
  for (const chapter of CHAPTERS) beats.add(chapterEntry(chapter));
  return [...beats].map((beat) => Math.round(beat * 1e6) / 1e6).sort((a, b) => a - b);
}

/** Scene ids used in the address bar: every chapter start and every stop. */
export type SceneId = ChapterId | StopId;

const SCENE_IDS: readonly SceneId[] = [...CHAPTERS, "public", "public-prepare", "case", "command"];

export function parseScene(search: string): SceneId | null {
  const value = new URLSearchParams(search).get("scene");
  return value && (SCENE_IDS as readonly string[]).includes(value) ? (value as SceneId) : null;
}

/**
 * Where navigating to a chapter lands: its start, nudged just past a stop that sits on the boundary (stops have no
 * length, so "the start of Conditions change" would otherwise be "the public-app stop" and dock that page instead).
 */
export function chapterEntry(chapter: ChapterId): number {
  const start = chapterStart(chapter);
  return stopAt(start) ? start + 0.002 : start;
}

export function scenePosition(scene: SceneId): number {
  return (CHAPTERS as readonly string[]).includes(scene) ? chapterEntry(scene as ChapterId) : stopPosition(scene as StopId);
}

/** Scene id to record for a position: the stop if exactly at one, otherwise the chapter. */
export function sceneAt(t: number): SceneId {
  return stopAt(t) ?? chapterAt(t);
}
```

#### `apps/web/src/lib/journey/terrain.ts`

The illustrative landscape as a height field. Its rule (tested): the home and the clinic stay dry in every water state; one stretch of road floods only in the "affected" state.

```ts
/**
 * Illustrative terrain for the cinematic journey, in metres (x east, z south, y up). Pure, so the story's spatial
 * claims are unit-tested: the home and the clinic stay on dry ground in every water state, while one stretch of the
 * road between them dips through a swale that the "affected" water state covers.
 *
 * This is a fictional, explanatory landscape. It is not the Mae Sai evidence map, a forecast or measured data.
 */

export type WaterState = "dry" | "rising" | "affected";

/** Water surface elevation per state (m). The channel bed is about -2.4 m. */
export const WATER_LEVEL: Record<WaterState, number> = {
  dry: -0.7,
  rising: 0.32,
  affected: 0.78,
};

/** Road centre line runs east–west at this z. */
export const ROAD_Z = 8;
/** Centre of the swale where the road dips (x, m). */
export const SWALE_X = 2;

export const LAYOUT = {
  home: { x: -24, z: -3.6 },
  homeGate: { x: -24, z: ROAD_Z },
  resident: { x: -22.4, z: 2.9 },
  clinic: { x: 26, z: -5 },
  clinicGate: { x: 26, z: ROAD_Z },
  operations: { x: 6, z: -34 },
} as const;

/** Side streets (concrete sois) run north from the road at these x positions; a back street runs east–west. */
export const SIDE_STREETS_X: readonly number[] = [-46, -30, -14, 14, 40, 56];
export const BACK_STREET_Z = -16;

/** River centre line (z as a function of x). */
export function riverZ(x: number): number {
  return 34 + 5 * Math.sin(x / 26) + 2 * Math.sin(x / 9 + 1.3);
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/** Half-width of the flat road bench (carriageway, kerb and footpath) and where it blends back into the land. */
export const ROAD_BENCH = { flat: 5, blend: 8 } as const;

/**
 * Ground elevation (m) at (x, z). Near the road the land is graded to the road's own centre-line level (a cut/fill
 * bench), so the road sits on the ground instead of floating over a cross-slope; at the centre line the bench equals
 * the natural ground, so road heights and the flooded stretch are unchanged by it.
 */
export function terrainHeight(x: number, z: number): number {
  const natural = naturalHeight(x, z);
  const bench = 1 - smoothstep(ROAD_BENCH.flat, ROAD_BENCH.blend, Math.abs(z - ROAD_Z));
  if (bench <= 0) return natural;
  return natural + (naturalHeight(x, ROAD_Z) - natural) * bench;
}

function naturalHeight(x: number, z: number): number {
  const river = riverZ(x);
  // North plateau → slope → floodplain → channel.
  const slope = 1.7 - 1.35 * smoothstep(4, 15, z);
  const plain = 0.35 - 0.28 * smoothstep(15, river - 7, z);
  let height = z < 15 ? slope : plain;
  // Channel: smooth trough around the river line.
  const distance = Math.abs(z - river);
  height -= 2.75 * (1 - smoothstep(2.5, 7.5, distance));
  // Swale: a shallow drainage valley crossing the road; deepest near the road, fading northward.
  const across = Math.exp(-(((x - SWALE_X) / 6.5) ** 2));
  const alongNorth = smoothstep(-22, 2, z);
  height -= 0.92 * across * alongNorth * (z < 15 ? 1 : 1 - smoothstep(15, 22, z));
  // Gentle undulation so the land does not read as a tabletop.
  height += 0.08 * Math.sin(x * 0.13 + z * 0.07) + 0.05 * Math.sin(x * 0.31 - z * 0.23);
  // The far north rises into low hills (depth for the establishing shot).
  height += 6 * smoothstep(-45, -95, z) * (0.6 + 0.4 * Math.sin(x * 0.05));
  return height;
}

/** Road surface height (m) at x along the road. */
export function roadHeight(x: number): number {
  return terrainHeight(x, ROAD_Z) + 0.06;
}

/** True when the ground at (x, z) is under water in a state. */
export function isUnderWater(x: number, z: number, state: WaterState): boolean {
  return terrainHeight(x, z) < WATER_LEVEL[state];
}

/** The x range of the usual connection between the home gate and the clinic gate. */
export const CONNECTION_X: readonly [number, number] = [LAYOUT.homeGate.x, LAYOUT.clinicGate.x];

/** Sample the road along the connection and return the sub-ranges (x) that are under water. */
export function floodedRoadRanges(state: WaterState, step = 0.25): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let open: number | null = null;
  for (let x = CONNECTION_X[0]; x <= CONNECTION_X[1] + 1e-9; x += step) {
    const wet = roadHeight(x) - 0.06 < WATER_LEVEL[state];
    if (wet && open === null) open = x;
    if (!wet && open !== null) {
      ranges.push([open, x - step]);
      open = null;
    }
  }
  if (open !== null) ranges.push([open, CONNECTION_X[1]]);
  return ranges;
}

/** Smooth interpolation of the water level between two states. */
export function waterLevelBetween(from: WaterState, to: WaterState, t: number): number {
  const k = smoothstep(0, 1, t);
  return WATER_LEVEL[from] + (WATER_LEVEL[to] - WATER_LEVEL[from]) * k;
}
```

#### `apps/web/src/lib/journey/screen-projection.ts`

How a real page (iframe) is warped onto a projected 3D screen with a CSS `matrix3d` homography.

```ts
/**
 * Maps a DOM element onto a projected 3D screen quad with a CSS `matrix3d` homography, so a real page (in an iframe)
 * can sit on a phone or monitor in the WebGL scene and become the full viewport when the camera aligns with it.
 * The element must use `position: absolute; left: 0; top: 0; transform-origin: 0 0`.
 */

export interface Point { x: number; y: number }

/**
 * At the end of the push onto the phone, the page fills this share of the window height, so the whole handset (its
 * black border and frame) stays in view around the page. Shared by the 3D stage (camera end pose) and the page host
 * (docking starts from the same rectangle).
 */
export const PHONE_PAGE_FILL = 0.74;

/** The same for the monitor and the planning table: their frames stay in view, clear of the top bar. */
export const LANDSCAPE_PAGE_FILL = 0.86;

/** Corners in screen pixels: top-left, top-right, bottom-right, bottom-left. */
export type Quad = readonly [Point, Point, Point, Point];

export interface Homography { a: number; b: number; c: number; d: number; e: number; f: number; g: number; h: number }

/** Projective map of the unit square onto `quad` (Heckbert's square-to-quad), as (u, v) → quad. */
export function squareToQuad(quad: Quad): Homography {
  const [p0, p1, p2, p3] = quad;
  const dx1 = p1.x - p2.x, dx2 = p3.x - p2.x, dx3 = p0.x - p1.x + p2.x - p3.x;
  const dy1 = p1.y - p2.y, dy2 = p3.y - p2.y, dy3 = p0.y - p1.y + p2.y - p3.y;
  if (Math.abs(dx3) < 1e-9 && Math.abs(dy3) < 1e-9) {
    return { a: p1.x - p0.x, b: p3.x - p0.x, c: p0.x, d: p1.y - p0.y, e: p3.y - p0.y, f: p0.y, g: 0, h: 0 };
  }
  const det = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(det) < 1e-12) throw new Error("Degenerate quad");
  const g = (dx3 * dy2 - dx2 * dy3) / det;
  const h = (dx1 * dy3 - dx3 * dy1) / det;
  return {
    a: p1.x - p0.x + g * p1.x, b: p3.x - p0.x + h * p3.x, c: p0.x,
    d: p1.y - p0.y + g * p1.y, e: p3.y - p0.y + h * p3.y, f: p0.y,
    g, h,
  };
}

export function applyHomography(m: Homography, u: number, v: number): Point {
  const w = m.g * u + m.h * v + 1;
  return { x: (m.a * u + m.b * v + m.c) / w, y: (m.d * u + m.e * v + m.f) / w };
}

/** CSS `matrix3d(...)` that maps an element of `width` × `height` CSS pixels onto `quad`. */
export function quadToMatrix3d(width: number, height: number, quad: Quad): string {
  const m = squareToQuad(quad);
  const a = m.a / width, b = m.b / height, d = m.d / width, e = m.e / height, g = m.g / width, h = m.h / height;
  // Column-major 4x4: x' = a x + b y + c, y' = d x + e y + f, w' = g x + h y + 1.
  const values = [a, d, 0, g, b, e, 0, h, 0, 0, 1, 0, m.c, m.f, 0, 1];
  return `matrix3d(${values.map((value) => (Math.abs(value) < 1e-12 ? 0 : Number(value.toPrecision(10)))).join(",")})`;
}

/** True when a quad is a plausible on-screen shape (convex, non-degenerate, not absurdly large). */
export function quadIsDrawable(quad: Quad, viewportWidth: number, viewportHeight: number): boolean {
  const limit = 40 * Math.max(viewportWidth, viewportHeight);
  if (quad.some((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y) || Math.abs(p.x) > limit || Math.abs(p.y) > limit)) return false;
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const p = quad[i], q = quad[(i + 1) % 4], r = quad[(i + 2) % 4];
    const cross = (q.x - p.x) * (r.y - q.y) - (q.y - p.y) * (r.x - q.x);
    if (Math.abs(cross) < 1e-6) return false;
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

/** Axis-aligned bounds of a quad. */
export function quadBounds(quad: Quad): { left: number; top: number; width: number; height: number } {
  const xs = quad.map((p) => p.x), ys = quad.map((p) => p.y);
  const left = Math.min(...xs), top = Math.min(...ys);
  return { left, top, width: Math.max(...xs) - left, height: Math.max(...ys) - top };
}
```

## C2. The story text (all copy, both languages)

#### `apps/web/src/components/journey/journey-copy.ts`

Everything the visitor reads. Characters, captions (with `who`, `meet`, `pause`), labels, and the notes over each real page.

```ts
import type { ChapterId, SegmentId, StopId } from "@/lib/journey/timeline";

export type JourneyLanguage = "en" | "th";
type Text = Record<JourneyLanguage, string>;
const t = (en: string, th: string): Text => ({ en, th });

/**
 * The story follows three fictional people, each with a reason to use one real FloodGuard page: Lalita (the public
 * app), Narin (the case view) and Pim (the command exercise). Mali and Dao, Lalita's mother and daughter, give her
 * household plan its needs. None of them represents a real person.
 */
export type CharacterId = "lalita" | "narin" | "pim";

export interface Character {
  name: Text;
  role: Text;
  /** The question that brings this person to their FloodGuard page. */
  question: Text;
}

export const CHARACTERS: Record<CharacterId, Character> = {
  lalita: {
    name: t("Lalita", "ลลิตา"),
    role: t("Resident · looks after her mother and daughter", "ผู้อยู่อาศัย · ดูแลแม่และลูกสาว"),
    question: t("Can my family still get where they need to go?", "ครอบครัวของฉันยังไปในที่ที่ต้องไปได้หรือไม่"),
  },
  narin: {
    name: t("Narin", "นรินทร์"),
    role: t("Planning officer · district office", "เจ้าหน้าที่วางแผน · สำนักงานอำเภอ"),
    question: t("What do we know, and what still needs checking?", "เรารู้อะไรแล้ว และอะไรที่ยังต้องตรวจสอบ"),
  },
  pim: {
    name: t("Pim", "พิมพ์"),
    role: t("District planning coordinator", "ผู้ประสานงานวางแผนระดับอำเภอ"),
    question: t("What should our team review together first?", "ทีมควรทบทวนเรื่องใดร่วมกันก่อน"),
  },
};

export const CHAPTER_LABELS: Record<ChapterId, { number: string; title: Text }> = {
  opening: { number: "", title: t("Opening", "เริ่มต้น") },
  everyday: { number: "01", title: t("Lalita's family", "ครอบครัวของลลิตา") },
  conditions: { number: "02", title: t("Rain, and a plan", "ฝนตกและแผนรับมือ") },
  affected: { number: "03", title: t("The road · Narin", "ถนน · นรินทร์") },
  response: { number: "04", title: t("The district · Pim", "ภาพรวมอำเภอ · พิมพ์") },
};

export const UI = {
  title: t("One road.\nThree people.", "ถนนหนึ่งสาย\nคนสามคน"),
  subtitle: t(
    "Lalita looks after her mother and daughter. Narin checks what is known. Pim brings the district together. A fictional story, told through the real FloodGuard pages.",
    "ลลิตาดูแลแม่และลูกสาว นรินทร์ตรวจสอบสิ่งที่รู้แล้ว พิมพ์ประสานภาพรวมของอำเภอ เรื่องสมมุติที่เล่าผ่านหน้า FloodGuard จริง",
  ),
  begin: t("Begin the story", "เริ่มเรื่องราว"),
  skip: t("Skip to the apps", "ข้ามไปที่แอป"),
  scrollHint: t("Scroll, swipe or use the arrow keys", "เลื่อน ปัด หรือใช้ปุ่มลูกศร"),
  illustrative: t(
    "Fictional people in an illustrative scenario · not a real place, not a forecast, not real-time data",
    "ตัวละครสมมุติในสถานการณ์จำลอง · ไม่ใช่สถานที่จริง ไม่ใช่การพยากรณ์ และไม่ใช่ข้อมูลเรียลไทม์",
  ),
  fictional: t("Fictional character", "ตัวละครสมมุติ"),
  previous: t("Previous", "ก่อนหน้า"),
  next: t("Next", "ถัดไป"),
  backToStory: t("Back to the story", "กลับไปที่เรื่องราว"),
  story: t("Story", "เรื่องราว"),
  openPage: t("Open as its own page", "เปิดเป็นหน้าแยก"),
  loadingPage: t("Loading the real page…", "กำลังโหลดหน้าจริง…"),
  loadingWorld: t("Preparing the neighbourhood…", "กำลังเตรียมชุมชน…"),
  home: t("FloodGuard home", "หน้าแรก FloodGuard"),
  replay: t("Replay the story", "เล่นเรื่องราวอีกครั้ง"),
  chapters: t("Story chapters", "บทของเรื่องราว"),
  skipTitle: t("Go straight to a real FloodGuard page", "ไปที่หน้า FloodGuard จริงโดยตรง"),
  close: t("Close", "ปิด"),
  fallbackTitle: t("The 3D story could not start on this device", "ไม่สามารถเริ่มเรื่องราวแบบ 3 มิติบนอุปกรณ์นี้ได้"),
  fallbackBody: t(
    "You can still follow the story and open every real FloodGuard page below.",
    "คุณยังติดตามเรื่องราวและเปิดหน้า FloodGuard จริงทุกหน้าได้ด้านล่าง",
  ),
};

/** Labels projected onto the 3D scene: places, and the people when the camera is with them. */
export const LABELS: Record<string, Text> = {
  home: t("Lalita's home", "บ้านของลลิตา"),
  clinic: t("Clinic", "คลินิก"),
  connection: t("Usual way to the clinic", "เส้นทางปกติไปคลินิก"),
  crossing: t("Connection potentially affected", "เส้นทางที่อาจได้รับผลกระทบ"),
  operations: t("District office (illustrative)", "สำนักงานอำเภอ (จำลอง)"),
  signal: t("Simulated call to hotline 1784 · nothing dialled", "จำลองการโทรสายด่วน 1784 · ไม่มีการโทรจริง"),
  lalita: t("Lalita", "ลลิตา"),
  mali: t("Mali, her mother", "มะลิ แม่ของเธอ"),
  dao: t("Dao, her daughter", "ดาว ลูกสาวของเธอ"),
  narin: t("Narin", "นรินทร์"),
  pim: t("Pim", "พิมพ์"),
};

export interface Caption {
  from: number;
  to: number;
  eyebrow?: Text;
  /** Whose part of the story this is (shown with the caption). */
  who?: CharacterId;
  /** The caption that introduces `who`: shows their role and their question. */
  meet?: boolean;
  /** The headline sentence. */
  text: Text;
  /** A few supporting points shown under the headline (for reading at your own pace or presenting). */
  points?: Text[];
  /**
   * Where the story waits for "Next" while this caption is shown (segment progress, inside [from, to)). A caption
   * without one is read while the camera passes (it leads into the next one).
   */
  pause?: number;
}

/**
 * Captions over the 3D scene: [start, end) progress ranges within a segment. Every feature a caption names is one the
 * real page has: the public app's area overview, Prepare (household needs), Shelter (a destination the household has
 * confirmed; the app does not know capacity), Report (saved on the device, sent nowhere) and SOS (official hotlines);
 * the case view's replay and its confidence; the command exercise's hourly table, practice items and trainee mode.
 */
export const CAPTIONS: Record<SegmentId, Caption[]> = {
  opening: [],
  everyday: [
    {
      from: 0.08, to: 0.5, pause: 0.46, who: "lalita", meet: true,
      eyebrow: t("01 · Meet Lalita", "01 · พบกับลลิตา"),
      text: t(
        "This is Lalita's street. She lives here with her mother, Mali, and her eight-year-old daughter, Dao.",
        "นี่คือถนนบ้านของลลิตา เธออาศัยอยู่กับมะลิ แม่ของเธอ และดาว ลูกสาววัยแปดขวบ",
      ),
      points: [
        t("Mali has regular appointments at the clinic down the road.", "มะลิต้องไปพบแพทย์ที่คลินิกปลายถนนเป็นประจำ"),
        t("Lalita takes Dao to school and Mali to her appointments.", "ลลิตาเป็นคนพาดาวไปโรงเรียนและพามะลิไปหาหมอ"),
        t("The teal line is their usual way to the clinic.", "เส้นสีเขียวอมฟ้าคือเส้นทางปกติไปคลินิก"),
      ],
    },
    {
      from: 0.55, to: 1.01, pause: 0.985, who: "lalita",
      text: t(
        "Heavy rain is expected. Before the rumours start, Lalita checks what is known about her area.",
        "คาดว่าจะมีฝนตกหนัก ก่อนข่าวลือจะเริ่ม ลลิตาตรวจดูว่ามีข้อมูลอะไรเกี่ยวกับพื้นที่ของเธอบ้าง",
      ),
      points: [
        t("She opens the FloodGuard public app.", "เธอเปิดแอป FloodGuard สำหรับประชาชน"),
        t("It helps her prepare. It is not an official warning.", "แอปช่วยให้เธอเตรียมพร้อม แต่ไม่ใช่การแจ้งเตือนทางการ"),
      ],
    },
  ],
  "enter-phone": [
    {
      from: 0.55, to: 1.01, pause: 0.92, who: "lalita",
      text: t("This is the real public app: what Lalita sees on her phone.", "นี่คือแอปสำหรับประชาชนจริง สิ่งที่ลลิตาเห็นบนโทรศัพท์"),
      points: [
        t("She chooses a planning area, or searches for an address.", "เธอเลือกพื้นที่วางแผน หรือค้นหาที่อยู่"),
        t("It shows a historical planning priority, with its date and confidence.", "แอปแสดงลำดับความสำคัญจากข้อมูลในอดีต พร้อมวันที่และระดับความเชื่อมั่น"),
        t("A historical priority is not a prediction that her street will flood.", "ลำดับความสำคัญจากอดีตไม่ใช่การทำนายว่าถนนของเธอจะน้ำท่วม"),
      ],
    },
  ],
  conditions: [
    {
      from: 0.12, to: 0.55, pause: 0.53, who: "lalita",
      eyebrow: t("02 · Rain, and a plan", "02 · ฝนตกและแผนรับมือ"),
      text: t("The rain sets in. The channel rises and low ground begins to pond.", "ฝนเริ่มตกหนัก ระดับน้ำในลำน้ำสูงขึ้น และพื้นที่ต่ำเริ่มมีน้ำขัง"),
      points: [
        t("Water collects first where the ground is lowest.", "น้ำขังที่จุดต่ำที่สุดก่อน"),
        t("Lalita's house stands on higher ground and stays dry.", "บ้านของลลิตาตั้งอยู่บนที่สูงและยังแห้ง"),
        t("An illustrative scenario, not a forecast.", "เป็นสถานการณ์จำลอง ไม่ใช่การพยากรณ์"),
      ],
    },
    {
      from: 0.6, to: 1.01, pause: 0.95, who: "lalita",
      text: t(
        "The road is still dry. But it dips through the lowest ground, on Mali's way to the clinic.",
        "ถนนยังแห้งอยู่ แต่ถนนลาดต่ำผ่านพื้นที่ที่ต่ำที่สุด บนทางที่มะลิใช้ไปคลินิก",
      ),
      points: [
        t("If that stretch floods, the clinic is cut off from the house.", "ถ้าถนนช่วงนั้นน้ำท่วม บ้านจะไปคลินิกไม่ได้"),
        t("Lalita cannot control the weather.", "ลลิตาควบคุมสภาพอากาศไม่ได้"),
        t("She can make a plan before she needs one.", "แต่เธอวางแผนไว้ก่อนที่จะต้องใช้ได้"),
      ],
    },
  ],
  "return-phone": [
    {
      from: 0.28, to: 0.58, pause: 0.45, who: "lalita",
      text: t(
        "Lalita talks it through with Mali and Dao: what to pack, who helps whom, where they could go.",
        "ลลิตาคุยกับมะลิและดาวว่าต้องเตรียมอะไร ใครช่วยใคร และจะไปที่ไหนได้บ้าง",
      ),
      points: [
        t("Mali needs her regular medicine with her.", "มะลิต้องมียาประจำตัวติดไว้"),
        t("Dao needs a grown-up she knows, and a place to meet.", "ดาวต้องมีผู้ใหญ่ที่รู้จักคอยดูแล และมีจุดนัดพบ"),
        t("They agree how they will follow official updates.", "ทุกคนตกลงกันว่าจะติดตามข่าวทางการอย่างไร"),
      ],
    },
    {
      from: 0.62, to: 1.01, pause: 0.92, who: "lalita",
      text: t("She writes it into her household plan in the app.", "เธอบันทึกเรื่องเหล่านี้ลงในแผนของครัวเรือนในแอป"),
      points: [
        t("Prepare: a child, an older adult and regular medicine each add their own actions.", "เตรียมพร้อม: เด็ก ผู้สูงอายุ และยาประจำตัว แต่ละข้อมีสิ่งที่ต้องทำของตัวเอง"),
        t("Shelter: she enters a place she has checked with the authorities. The app does not know if it is open or full.", "ที่พักพิง: เธอใส่สถานที่ที่สอบถามกับหน่วยงานแล้ว แอปไม่รู้ว่าที่นั่นเปิดอยู่หรือเต็มแล้ว"),
        t("SOS: the official hotlines, kept in one place.", "SOS: รวมสายด่วนทางการไว้ในที่เดียว"),
      ],
    },
  ],
  "sos-signal": [
    {
      from: 0.0, to: 0.2, pause: 0.06, who: "lalita",
      eyebrow: t("03 · The road", "03 · ถนน"),
      text: t("Lalita notes what she sees in Report: water in the low part of the road.", "ลลิตาบันทึกสิ่งที่เห็นในแท็บรายงาน: น้ำเริ่มท่วมถนนช่วงที่ต่ำ"),
      points: [
        t("The note stays on her phone. FloodGuard sends it nowhere.", "บันทึกนี้อยู่ในโทรศัพท์ของเธอ FloodGuard ไม่ได้ส่งไปที่ใด"),
        t("Asking for help goes through official channels.", "การขอความช่วยเหลือต้องผ่านช่องทางทางการ"),
      ],
    },
    {
      from: 0.22, to: 0.5, pause: 0.47, who: "lalita",
      text: t(
        "Now the water crosses the road. Lalita's home and the clinic stay dry; the way between them does not.",
        "ตอนนี้น้ำท่วมข้ามถนนแล้ว บ้านของลลิตาและคลินิกยังแห้ง แต่ทางระหว่างกันไม่ได้แห้ง",
      ),
      points: [
        t("Both buildings stand on higher ground.", "อาคารทั้งสองตั้งอยู่บนที่สูง"),
        t("The low stretch of road between them is under water.", "ถนนช่วงต่ำระหว่างทั้งสองจมน้ำ"),
        t("Lost access, not only flooding, is what FloodGuard looks at.", "FloodGuard ดูการเข้าถึงที่ขาดหาย ไม่ใช่แค่น้ำท่วม"),
      ],
    },
    {
      from: 0.52, to: 0.84, pause: 0.72, who: "lalita",
      text: t(
        "Mali needs to see her doctor. Lalita calls the official hotline, 1784, to ask how to get her there.",
        "มะลิต้องไปพบแพทย์ ลลิตาโทรหาสายด่วนทางการ 1784 เพื่อถามว่าจะพาแม่ไปได้อย่างไร",
      ),
      points: [
        t("Story mode: the call is simulated. Nothing is dialled.", "โหมดเรื่องราว: เป็นการจำลอง ไม่มีการโทรจริง"),
        t("The call goes through the hotline, not through FloodGuard.", "สายนี้ผ่านสายด่วน ไม่ได้ผ่าน FloodGuard"),
        t("In this story, requests like hers reach the district office.", "ในเรื่องนี้ คำขอแบบเดียวกับของเธอส่งต่อมาถึงสำนักงานอำเภอ"),
      ],
    },
    {
      from: 0.88, to: 1.01, pause: 0.985, who: "narin", meet: true,
      eyebrow: t("Meet Narin", "พบกับนรินทร์"),
      text: t(
        "Narin is a planning officer at the district office. Calls like Lalita's are part of what he has to make sense of.",
        "นรินทร์เป็นเจ้าหน้าที่วางแผนที่สำนักงานอำเภอ สายแบบเดียวกับของลลิตาเป็นส่วนหนึ่งของสิ่งที่เขาต้องทำความเข้าใจ",
      ),
      points: [
        t("He has not seen every road or shelter himself.", "เขาไม่ได้เห็นถนนหรือที่พักพิงทุกแห่งด้วยตัวเอง"),
        t("Not every report is confirmed.", "ไม่ใช่ทุกรายงานที่ได้รับการยืนยัน"),
        t("Before anyone acts, he looks at the evidence.", "ก่อนลงมือทำอะไร เขาดูหลักฐานก่อน"),
      ],
    },
  ],
  "enter-monitor": [
    {
      from: 0.4, to: 1.01, pause: 0.93, who: "narin",
      text: t(
        "Narin opens the case view: a real, past flood in Mae Sai, September 2024. It is not Lalita's street.",
        "นรินทร์เปิดหน้าเคส: น้ำท่วมจริงในอดีตที่แม่สาย กันยายน 2024 ไม่ใช่ถนนของลลิตา",
      ),
      points: [
        t("He replays it day by day, with dated satellite images.", "เขาย้อนดูทีละวัน พร้อมภาพดาวเทียมที่ระบุวันที่"),
        t("Modelled water, roads, facilities and residents in water, each marked low confidence.", "น้ำ ถนน สถานบริการ และผู้อยู่อาศัยในน้ำจากแบบจำลอง ทั้งหมดระบุว่าความเชื่อมั่นต่ำ"),
        t("Who could walk to a shelter, and who could not: the equity gap.", "ใครเดินไปถึงที่พักพิงได้ และใครไปไม่ถึง: ช่องว่างความเท่าเทียม"),
      ],
    },
  ],
  aerial: [
    {
      from: 0.14, to: 0.3, pause: 0.22, who: "pim", meet: true,
      eyebrow: t("04 · Meet Pim", "04 · พบกับพิมพ์"),
      text: t(
        "Pim coordinates planning for the district. Narin's evidence is one input; she has many communities to think about.",
        "พิมพ์ประสานงานการวางแผนของอำเภอ หลักฐานของนรินทร์เป็นข้อมูลส่วนหนึ่ง เธอต้องคิดถึงหลายชุมชน",
      ),
      points: [
        t("Her job is to organise the discussion, not to hand it to a computer.", "งานของเธอคือจัดการการหารือ ไม่ใช่ปล่อยให้คอมพิวเตอร์ตัดสินใจ"),
        t("She brings the team round the planning table.", "เธอชวนทีมมารวมกันที่โต๊ะวางแผน"),
      ],
    },
    {
      from: 0.38, to: 0.7, pause: 0.6, who: "pim",
      text: t(
        "From above, Lalita's road is one of many links between people and the services they need.",
        "เมื่อมองจากด้านบน ถนนของลลิตาเป็นเพียงหนึ่งในหลายเส้นทางที่เชื่อมผู้คนกับบริการที่จำเป็น",
      ),
      points: [
        t("Every household–service link can be checked the same way.", "ทุกเส้นทางระหว่างครัวเรือนกับบริการตรวจได้ด้วยวิธีเดียวกัน"),
        t("Cut links show where help may not get through.", "เส้นทางที่ขาดชี้ว่าความช่วยเหลืออาจไปไม่ถึงที่ใด"),
      ],
    },
    {
      from: 0.74, to: 1.01, pause: 0.95, who: "pim",
      text: t(
        "Pim runs it as an exercise: the team replays the flood hour by hour and practises what they would do.",
        "พิมพ์จัดเป็นการฝึกซ้อม ทีมย้อนดูน้ำท่วมทีละชั่วโมงและฝึกว่าจะทำอะไร",
      ),
      points: [
        t("Each subdistrict's modelled figures, hour by hour.", "ตัวเลขจากแบบจำลองของแต่ละตำบล ทีละชั่วโมง"),
        t("Practice incidents, marked EX, are assigned to team callsigns.", "เหตุการณ์ฝึกซ้อมที่มีป้าย EX ถูกมอบหมายให้ทีมตามรหัสเรียกขาน"),
        t("People decide. The tool dispatches no one.", "คนเป็นผู้ตัดสินใจ เครื่องมือไม่ได้สั่งการใคร"),
      ],
    },
  ],
};

/** The public app's tabs a stop can open on (the app's own bottom navigation). */
export type PublicTab = "home" | "prepare";

export interface StopCopy {
  page: Text;
  note: Text;
  /** Whose page this is in the story. */
  who: CharacterId;
  href: (language: JourneyLanguage) => string;
  /** On the public app: the tab the page is switched to when the story arrives. */
  tab?: PublicTab;
  continueLabel?: Text;
  /** Shown over the real page while it is open. */
  warning?: Text;
}

export const STOPS: Record<StopId, StopCopy> = {
  public: {
    page: t("Real page · Public app", "หน้าจริง · แอปประชาชน"),
    note: t(
      "Lalita's first look. The app's data covers Mae Sai district; her street in this story is illustrated.",
      "การเปิดดูครั้งแรกของลลิตา ข้อมูลในแอปครอบคลุมอำเภอแม่สาย ส่วนถนนของเธอในเรื่องนี้เป็นภาพจำลอง",
    ),
    who: "lalita",
    href: () => "/public/",
    tab: "home",
    continueLabel: t("Continue: rain, and a plan", "ไปต่อ: ฝนตกและแผนรับมือ"),
  },
  "public-prepare": {
    page: t("Real page · Prepare", "หน้าจริง · เตรียมพร้อม"),
    note: t("Lalita's household plan. It stays on this device; nothing is sent.", "แผนของครัวเรือนของลลิตา เก็บไว้ในอุปกรณ์นี้ ไม่มีการส่งข้อมูล"),
    who: "lalita",
    href: () => "/public/?tab=prepare",
    tab: "prepare",
    continueLabel: t("Continue: the road", "ไปต่อ: ถนน"),
    warning: t(
      "The SOS tab's buttons open your phone's call or message app with real hotline numbers. The story never uses them.",
      "ปุ่มในแท็บ SOS จะเปิดแอปโทรศัพท์หรือข้อความพร้อมหมายเลขสายด่วนจริง เรื่องราวนี้ไม่ใช้ปุ่มเหล่านั้น",
    ),
  },
  case: {
    page: t("Real page · Case view", "หน้าจริง · หน้าเคส"),
    note: t(
      "Narin's evidence. Mae Sai, September 2024: historical, reconstructed, low confidence. Not the illustrated street.",
      "หลักฐานของนรินทร์ แม่สาย กันยายน 2024: ข้อมูลในอดีต สร้างขึ้นใหม่ ความเชื่อมั่นต่ำ ไม่ใช่ถนนในภาพจำลอง",
    ),
    who: "narin",
    href: (language) => `/studio/cases/mae-sai-2024/?lang=${language}`,
    continueLabel: t("Continue: the district", "ไปต่อ: ภาพรวมอำเภอ"),
  },
  command: {
    page: t("Real page · Command exercise", "หน้าจริง · แบบฝึกบัญชาการ"),
    note: t(
      "Pim's planning table. An exercise replay for review and coordination: not real-time, not dispatch. Reports saved on this device appear here too.",
      "โต๊ะวางแผนของพิมพ์ การเล่นซ้ำเพื่อฝึกทบทวนและประสานงาน ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่การสั่งการ รายงานที่บันทึกในอุปกรณ์นี้จะแสดงที่นี่ด้วย",
    ),
    who: "pim",
    href: (language) => `/command/?t=36&lang=${language}`,
  },
};

/** The iframe address for a stop: the real route, untouched. Both public-app stops share one frame at `/public/`. */
export function stopFrameSrc(stop: StopId, language: JourneyLanguage): string {
  return stop === "public-prepare" ? STOPS.public.href(language) : STOPS[stop].href(language);
}
```

#### `apps/web/src/components/journey/journey-copy.test.ts`

Tests on the copy: shared wording lint (EN + TH), people introduced before their part, the call stays simulated.

```ts
import { describe, expect, it } from "vitest";

import { TIMELINE, segmentRange, stopPosition, type SegmentId } from "@/lib/journey/timeline";
import { describeWordingFindings, findWordingViolations } from "@/lib/replay-wording-lint";

import { CAPTIONS, CHAPTER_LABELS, CHARACTERS, LABELS, STOPS, UI, type CharacterId } from "./journey-copy";

/** Every caption, with its timeline position (its pause, or its start). */
const placedCaptions = (Object.keys(CAPTIONS) as SegmentId[]).flatMap((segment) => {
  const { start, end } = segmentRange(segment);
  return CAPTIONS[segment].map((caption) => ({ caption, at: start + (end - start) * (caption.pause ?? caption.from) }));
}).sort((a, b) => a.at - b.at);

describe("journey story copy", () => {
  it("passes the shared wording lint in both languages", () => {
    const texts = [
      ...Object.values(UI), ...Object.values(LABELS), ...Object.values(CHAPTER_LABELS).map((chapter) => chapter.title),
      ...Object.values(CHARACTERS).flatMap((person) => [person.name, person.role, person.question]),
      ...placedCaptions.flatMap(({ caption }) => [caption.eyebrow, caption.text, ...(caption.points ?? [])]),
      ...Object.values(STOPS).flatMap((stop) => [stop.page, stop.note, stop.continueLabel, stop.warning]),
    ].filter((text) => text !== undefined);
    for (const language of ["en", "th"] as const) {
      const findings = texts.flatMap((text) => findWordingViolations(text[language], `journey copy (${language})`));
      expect(findings, describeWordingFindings(findings)).toEqual([]);
    }
  });

  it("introduces each person once, before any caption or real page is theirs", () => {
    const met = new Map<CharacterId, number>();
    for (const { caption, at } of placedCaptions) {
      if (!caption.meet || !caption.who) continue;
      expect(met.has(caption.who), `${caption.who} is introduced twice`).toBe(false);
      met.set(caption.who, at);
    }
    expect([...met.keys()].sort()).toEqual((Object.keys(CHARACTERS) as CharacterId[]).sort());
    for (const { caption, at } of placedCaptions) if (caption.who) expect(at).toBeGreaterThanOrEqual(met.get(caption.who)!);
    for (const item of TIMELINE) {
      if (item.kind === "stop") expect(stopPosition(item.id)).toBeGreaterThan(met.get(STOPS[item.id].who)!);
    }
  });

  it("follows Lalita, then Narin, then Pim, each with their own real page", () => {
    expect(STOPS.public.who).toBe("lalita");
    expect(STOPS["public-prepare"].who).toBe("lalita");
    expect(STOPS.case.who).toBe("narin");
    expect(STOPS.command.who).toBe("pim");
    expect(STOPS.public.tab).toBe("home");
    expect(STOPS["public-prepare"].tab).toBe("prepare");
  });

  it("keeps the request for help simulated and outside FloodGuard", () => {
    const call = placedCaptions.find(({ caption }) => caption.text.en.includes("1784"));
    expect(call).toBeDefined();
    const points = call!.caption.points!.map((point) => point.en).join(" ");
    expect(points).toMatch(/simulated/i);
    expect(points).toMatch(/not through FloodGuard/);
    expect(LABELS.signal.en).toMatch(/nothing dialled/);
    // The live public app sits inside the story: its SOS tab opens real hotline numbers, and the page says so.
    expect(STOPS["public-prepare"].warning?.en).toMatch(/real hotline numbers/);
  });
});
```

## C3. The React shell (`journey-experience.tsx`, excerpts)

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 34–120 of 889

Sizes of the real pages, the caption pause points that Next/Previous step through, and scroll clamping.

```tsx
/** Which 3D screen hosts the real page for each stop. */
const STOP_SCREEN: Record<StopId, ScreenId> = { public: "phone", "public-prepare": "phone", case: "monitor", command: "table" };
const SCREEN_STOP: Record<ScreenId, StopId> = { phone: "public", monitor: "case", table: "command" };
const FADE_MS = 260;

interface Sizes {
  width: number;
  height: number;
  mobile: boolean;
  aspects: ScreenAspects;
  /** CSS pixel size each real page is laid out at while it sits on a 3D screen. */
  css: Record<ScreenId, { width: number; height: number }>;
  /** True when docking leaves the page at exactly the size it had on the screen (no reflow). */
  exact: Record<ScreenId, boolean>;
}

export function computeSizes(width: number, height: number): Sizes {
  const ratio = width / height;
  const mobile = width < 700 || ratio < 0.9;
  const phoneAspect = mobile ? Math.min(0.62, Math.max(0.42, ratio)) : 0.4615;
  // On desktop the public app is laid out at a real phone size (at least 390 CSS px wide), whatever the window height:
  // short windows and zoomed browsers would otherwise give it a column too narrow for its layout. The projection
  // scales the page onto the 3D phone, so the CSS size need not match the window.
  const phoneWidth = Math.max(390, Math.round(height * phoneAspect));
  const landscapeExact = ratio >= 1.2 && ratio <= 2.2;
  const landscapeAspect = landscapeExact ? ratio : 1.6;
  const landscapeCss = landscapeExact ? { width, height } : { width: 1280, height: 800 };
  return {
    width,
    height,
    mobile,
    aspects: { phone: phoneAspect, monitor: landscapeAspect, table: landscapeAspect },
    css: {
      phone: mobile ? { width, height } : { width: phoneWidth, height: Math.round(phoneWidth / phoneAspect) },
      monitor: landscapeCss,
      table: landscapeCss,
    },
    exact: { phone: true, monitor: landscapeExact, table: landscapeExact },
  };
}

interface View {
  segment: SegmentId;
  caption: number;
  chapter: ChapterId;
  docked: StopId | null;
  heroVisible: boolean;
  atStart: boolean;
  atEnd: boolean;
}

/**
 * Where the story waits on each caption (its `pause`), as timeline positions. Begin, Next and Continue glide to the next
 * one and wait there; scrolling also stops at each one, so nothing runs on to the next caption by itself.
 */
const CAPTION_PAUSES: number[] = (Object.keys(CAPTIONS) as SegmentId[])
  .flatMap((segment) => {
    const { start, end } = segmentRange(segment);
    return CAPTIONS[segment].flatMap((caption) => (caption.pause === undefined ? [] : [start + (end - start) * caption.pause]));
  })
  .sort((a, b) => a - b);

/** Everything Next/Previous steps through, in order: every caption pause and every real page. */
const STEP_POINTS: number[] = [...CAPTION_PAUSES, ...(["public", "public-prepare", "case", "command"] as const).map(stopPosition)].sort((a, b) => a - b);

function nextPoint(points: number[], after: number): number | null {
  return points.find((point) => point > after + 1e-3) ?? null;
}

function previousPoint(points: number[], before: number): number | null {
  return [...points].reverse().find((point) => point < before - 1e-3) ?? null;
}

/** Scrolling stops at the next (or previous) caption pause, like it stops at a real page. */
function clampToPauses(display: number, requested: number): number {
  if (requested > display) {
    const next = nextPoint(CAPTION_PAUSES, display - 1e-3 + 1e-4);
    return next !== null && next > display + 1e-4 ? Math.min(requested, next) : requested;
  }
  const previous = previousPoint(CAPTION_PAUSES, display + 1e-3 - 1e-4);
  return previous !== null && previous < display - 1e-4 ? Math.max(requested, previous) : requested;
}

function captionIndex(segment: SegmentId, progress: number): number {
  return CAPTIONS[segment].findIndex((caption) => progress >= caption.from && progress < caption.to);
}

```

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 199–330 of 889

Real-page hosts: switching Lalita's phone to the right tab, projecting a page onto a screen, docking and undocking.

```tsx
  // --- Real-page hosts ---------------------------------------------------------------------------------------------
  const ensureMounted = useCallback((screen: ScreenId) => {
    setMounted((current) => (current[screen] ? current : { ...current, [screen]: true }));
  }, []);

  /**
   * While a real page sits on a 3D screen its own scrollbar is hidden (it would show as a grey bar on the device);
   * docked, the page is itself again. Same-origin frames, so the parent can set this on the framed document.
   */
  const setFrameScrollbar = useCallback((screen: ScreenId, visible: boolean) => {
    try {
      const root = frameRefs.current[screen]?.contentDocument?.documentElement;
      if (root) root.style.setProperty("scrollbar-width", visible ? "" : "none");
    } catch {
      /* not reachable (still loading); applied again on load */
    }
  }, []);

  /**
   * The public app's tab for this point of the story (Home for Lalita's first look, Prepare for her household plan).
   * The app reads its tab from its address, so the story replaces that address and tells the app (no history entry);
   * a frame that has not loaded yet picks the tab up when it does.
   */
  const publicTab = useRef<{ wanted: PublicTab; applied: PublicTab | null }>({ wanted: "home", applied: null });
  const syncPublicTab = useCallback(() => {
    const tab = publicTab.current;
    if (tab.applied === tab.wanted) return;
    try {
      const win = frameRefs.current.phone?.contentWindow;
      if (!win || !win.location.pathname.startsWith("/public")) return;
      const url = new URL(win.location.href);
      if (tab.wanted === "home") url.searchParams.delete("tab");
      else url.searchParams.set("tab", tab.wanted);
      if (url.href !== win.location.href) {
        win.history.replaceState(win.history.state, "", url);
        win.dispatchEvent(new (win as Window & typeof globalThis).PopStateEvent("popstate", { state: win.history.state }));
      }
      tab.applied = tab.wanted;
    } catch {
      /* not reachable yet; applied on load */
    }
  }, []);
  const wantPublicTab = useCallback((wanted: PublicTab) => {
    publicTab.current.wanted = wanted;
    syncPublicTab();
  }, [syncPublicTab]);

  /** Puts a host into "on a 3D screen" mode at its CSS layout size. */
  const projectHost = useCallback((screen: ScreenId) => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return;
    setFrameScrollbar(screen, false);
    host.dataset.mode = "screen";
    host.style.transition = "";
    host.style.left = "0px";
    host.style.top = "0px";
    host.style.width = `${size.css[screen].width}px`;
    host.style.height = `${size.css[screen].height}px`;
  }, [setFrameScrollbar]);

  /**
   * The rectangle a page occupies at the end of the push onto its screen: where it was last drawn there, or (when the
   * story opened directly at a stop) where the end pose puts it. The page keeps its layout size and is scaled.
   */
  const endRect = useCallback((screen: ScreenId) => {
    const size = sizesRef.current!;
    const css = size.css[screen];
    const quad = lastQuads.current[screen];
    if (quad && quadIsDrawable(quad, size.width, size.height)) {
      const bounds = quadBounds(quad);
      return { left: bounds.left, top: bounds.top, width: css.width, height: css.height, scale: bounds.height / css.height };
    }
    const scale = (size.height * (screen === "phone" ? PHONE_PAGE_FILL : LANDSCAPE_PAGE_FILL)) / css.height;
    return { left: (size.width - css.width * scale) / 2, top: (size.height - css.height * scale) / 2, width: css.width, height: css.height, scale };
  }, []);

  /** Docks a host: the real page becomes the viewport and receives input. */
  const dockHost = useCallback((screen: ScreenId, animate: boolean) => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return;
    // Start from exactly where the page sits at the end of the push (on the phone, inside its border), then open out
    // to the whole viewport.
    const start = endRect(screen);
    setFrameScrollbar(screen, true);
    host.dataset.mode = "docked";
    host.style.transformOrigin = "0 0";
    host.style.transform = `scale(${start.scale})`;
    host.style.opacity = "1";
    host.style.visibility = "visible";
    host.style.transition = "";
    host.style.left = `${start.left}px`;
    host.style.top = `${start.top}px`;
    host.style.width = `${start.width}px`;
    host.style.height = `${start.height}px`;
    const settle = () => {
      host.style.transition = animate ? "left 620ms cubic-bezier(.65,0,.35,1), width 620ms cubic-bezier(.65,0,.35,1), top 420ms ease, height 420ms ease, transform 620ms cubic-bezier(.65,0,.35,1)" : "";
      host.style.transform = "none";
      host.style.left = "0px";
      host.style.width = "100%";
      host.style.top = "0px";
      host.style.height = "100%";
    };
    if (!size.exact[screen] && animate) {
      host.style.opacity = "0";
      window.setTimeout(() => { settle(); host.style.transition = "opacity 220ms ease"; host.style.opacity = "1"; }, 120);
    } else if (animate) {
      requestAnimationFrame(() => requestAnimationFrame(settle));
    } else settle();
  }, [endRect, setFrameScrollbar]);

  /** Reverse of docking: back to the end-of-push rectangle, then onto the 3D screen. */
  const undockHost = useCallback((screen: ScreenId, animate: boolean): Promise<void> => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return Promise.resolve();
    if (!animate) {
      projectHost(screen);
      return Promise.resolve();
    }
    const end = endRect(screen);
    host.style.transition = "left 420ms cubic-bezier(.65,0,.35,1), width 420ms cubic-bezier(.65,0,.35,1), top 420ms cubic-bezier(.65,0,.35,1), height 420ms cubic-bezier(.65,0,.35,1), transform 420ms cubic-bezier(.65,0,.35,1)";
    host.style.transformOrigin = "0 0";
    host.style.transform = `scale(${end.scale})`;
    host.style.left = `${end.left}px`;
    host.style.top = `${end.top}px`;
    host.style.width = `${end.width}px`;
    host.style.height = `${end.height}px`;
    return new Promise((resolve) => window.setTimeout(() => { projectHost(screen); resolve(); }, 440));
  }, [endRect, projectHost]);

```

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 331–386 of 889

Navigation: animate or cross-fade to a position; what "Continue" does on a real page.

```tsx
  // --- Navigation --------------------------------------------------------------------------------------------------
  const updateHistory = useCallback((scene: SceneId, push: boolean) => {
    const url = new URL(window.location.href);
    url.searchParams.set("scene", scene);
    if (url.href === window.location.href) return;
    if (push) window.history.pushState({ scene }, "", url);
    else window.history.replaceState({ scene }, "", url);
  }, []);

  const undockIfNeeded = useCallback(async (animate: boolean) => {
    const m = motion.current;
    if (!m.docked) return;
    const screen = STOP_SCREEN[m.docked];
    m.docked = null;
    m.busy = true;
    setView((current) => ({ ...current, docked: null }));
    if (canvasRef.current) canvasRef.current.style.visibility = "visible";
    await undockHost(screen, animate);
    m.busy = false;
  }, [undockHost]);

  /** Animate (or, with reduced motion / long distances, cross-fade) to a timeline position. */
  const goTo = useCallback(async (position: number, options: { animate?: boolean } = {}) => {
    const m = motion.current;
    const destination = Math.min(TIMELINE_END, Math.max(0, position));
    const far = Math.abs(destination - m.display) > 2.6;
    const animate = options.animate ?? (!m.reduced && !far);
    await undockIfNeeded(!m.reduced);
    if (animate) {
      m.target = destination;
      return;
    }
    const fade = fadeRef.current;
    if (fade) fade.dataset.on = "true";
    // Freeze the timeline while the screen is covered, so the old position cannot re-dock the page just left.
    m.busy = true;
    await new Promise((resolve) => window.setTimeout(resolve, m.reduced ? 120 : FADE_MS));
    m.display = m.target = destination;
    m.busy = false;
    // Let one frame render at the new position before revealing it.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (fade) fade.dataset.on = "false";
  }, [undockIfNeeded]);

  const continueFrom = useCallback((stop: StopId) => {
    if (stop === "command") void goTo(0, { animate: false });
    // Glide to the next chapter's first caption and wait there (with reduced motion, fade to it).
    else void goTo(nextPoint(CAPTION_PAUSES, stopPosition(stop)) ?? stopPosition(stop) + 0.5, { animate: !motion.current.reduced });
  }, [goTo]);

  const jumpToStop = useCallback((stop: StopId) => {
    setSkipOpen(false);
    ensureMounted(STOP_SCREEN[stop]);
    void goTo(stopPosition(stop), { animate: false });
  }, [ensureMounted, goTo, setSkipOpen]);

```

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 420–545 of 889

The per-frame loop: ease the position, update the 3D stage, place pages and labels, update captions, dock at stops.

```tsx
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!stage || document.hidden) return;
      const size = sizesRef.current;
      if (!size) return;
      if (m.docked) return; // the real page owns the viewport; no 3D rendering while docked

      if (!m.busy) {
        const before = m.display;
        m.display = stepToward(m.display, m.target, dt);
        // Arriving on a caption: rest briefly, so the end of a scroll gesture does not run on past it.
        if (before !== m.display && m.display === m.target && CAPTION_PAUSES.some((pause) => Math.abs(pause - m.display) < 1e-4)) {
          m.restUntil = performance.now() + 650;
          m.freshGesture = true;
        }
      }
      const position = m.display;
      const result: StageFrame = stage.update(position, dt);

      // Real pages on the 3D screens.
      (Object.keys(result.screens) as ScreenId[]).forEach((screen) => {
        const host = hostRefs.current[screen];
        if (!host || host.dataset.mode === "docked") return;
        const info = result.screens[screen];
        const css = size.css[screen];
        if (info.quad && info.opacity > 0.005 && quadIsDrawable(info.quad, size.width, size.height)) {
          host.style.transform = quadToMatrix3d(css.width, css.height, info.quad);
          lastQuads.current[screen] = info.quad;
          host.style.opacity = String(info.opacity);
          host.style.visibility = "visible";
        } else {
          host.style.visibility = "hidden";
        }
      });

      // Projected labels.
      for (const label of result.labels) {
        const element = labelRefs.current[label.id];
        if (!element) continue;
        element.style.transform = `translate3d(${label.x.toFixed(1)}px, ${label.y.toFixed(1)}px, 0)`;
        element.dataset.visible = String(label.visible);
      }

      // Lalita's phone shows the Home tab for her first look and the Prepare tab once she makes her plan.
      if (position >= segmentRange("return-phone").start) wantPublicTab("prepare");
      else if (position <= stopPosition("public") + 1e-3) wantPublicTab("home");

      // Lazy-load the real pages a little before they are needed.
      if (position > 0.25 || m.target > 0.25) ensureMounted("phone");
      if (position > stopPosition("public") + 0.5 || m.target >= stopPosition("public-prepare")) ensureMounted("monitor");
      if (position > stopPosition("case") - 0.4 || m.target >= stopPosition("case")) ensureMounted("table");

      // View state (React only when something visible changes).
      const where = locate(position);
      const caption = captionIndex(where.segment, where.progress);
      const chapter = chapterAt(position);
      const heroVisible = where.segment === "opening" && where.progress < 0.35;
      const atStart = position < 1e-3, atEnd = position > TIMELINE_END - 1e-3;
      setView((current) => (current.segment === where.segment && current.caption === caption && current.chapter === chapter
        && current.heroVisible === heroVisible && current.atStart === atStart && current.atEnd === atEnd
        ? current
        : { ...current, segment: where.segment, caption, chapter, heroVisible, atStart, atEnd }));

      // Address bar: replace while moving, push when a real page is entered.
      const scene = sceneAt(position);
      // Stops are pushed when docked (below); replacing here would overwrite the entry Back should return to.
      if (scene !== m.lastScene && Math.abs(position - m.target) < 1e-4 && !stopAt(position)) {
        m.lastScene = scene;
        if (!m.fromPopState) updateHistory(scene, false);
      }

      // Arrived at a stop: dock the real page.
      const stop = stopAt(position);
      if (stop && Math.abs(position - m.target) < 1e-4 && !m.busy) {
        const screen = STOP_SCREEN[stop];
        ensureMounted(screen);
        m.docked = stop;
        const tab = STOPS[stop].tab;
        if (tab) wantPublicTab(tab);
        dockHost(screen, !m.reduced);
        // The 3D stays visible (its last frame) under the see-through bottom bar; rendering pauses while docked.
        setView((current) => ({ ...current, docked: stop }));
        const warning = STOPS[stop].warning;
        setAnnouncement(`${trRef.current(STOPS[stop].page)}. ${trRef.current(STOPS[stop].note)}${warning ? ` ${trRef.current(warning)}` : ""}`);
        if (!m.fromPopState) updateHistory(stop, true);
        m.fromPopState = false;
        window.setTimeout(() => frameRefs.current[screen]?.focus({ preventScroll: true }), 700);
      }
    };

    (async () => {
      try {
        const probe = document.createElement("canvas");
        const gl = probe.getContext("webgl2") ?? probe.getContext("webgl");
        if (!gl) throw new Error("WebGL unavailable");
        const lowPower = window.innerWidth < 700 || (navigator.hardwareConcurrency ?? 8) < 4 || ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) < 4;
        const { JourneyStage: Stage } = await import("./stage/journey-stage");
        if (disposed) return;
        stage = new Stage(canvas, { quality: lowPower ? "low" : "high" });
        stageRef.current = stage;
        canvas.addEventListener("webglcontextlost", onContextLost);
        applySizes();
        // The rigged people are a few megabytes: wait for them briefly so the story starts with them; if they are
        // slow, start anyway with the procedural figures and swap when they arrive.
        await Promise.race([stage.charactersReady, new Promise((resolve) => window.setTimeout(resolve, 9000))]);
        if (disposed) return;
        stage.precompile();
        stage.update(m.display, 0);
        setStatus("ready");
        last = performance.now();
        raf = requestAnimationFrame(frame);
      } catch {
        if (!disposed) setStatus("failed");
      }
    })();

    // Visual-review hook: jump the camera to a timeline position. Development only, or a production build made with
    // NEXT_PUBLIC_JOURNEY_DEBUG=1 for profiling; normal production builds do not include it.
    const debug = window as Window & { __journeySeek?: (t: number) => void; __journeyStage?: () => JourneyStage | null };
    if (process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_JOURNEY_DEBUG === "1") {
      debug.__journeySeek = (t: number) => { m.display = m.target = t; };
      debug.__journeyStage = () => stage;
    }

```

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 574–697 of 889

Input: wheel/touch/keys with presenter pacing, and the Next/Previous step.

```tsx
  // --- Input -------------------------------------------------------------------------------------------------------
  useEffect(() => {
    const m = motion.current;
    const beats = storyBeats();

    const advance = (delta: number) => {
      if (m.docked || m.busy) return;
      if (m.reduced) {
        m.wheelBuffer += delta;
        if (Math.abs(m.wheelBuffer) < 0.12) return;
        const direction = Math.sign(m.wheelBuffer);
        m.wheelBuffer = 0;
        const next = direction > 0 ? beats.find((beat) => beat > m.display + 1e-3) : [...beats].reverse().find((beat) => beat < m.display - 1e-3);
        if (next === undefined) return;
        void goTo(clampScrollTarget(m.display, next), { animate: false });
        return;
      }
      const now = performance.now();
      // Arriving on a caption ends the scroll gesture that brought the story there: what is left of it (or a
      // trackpad's momentum) is ignored, and only a new gesture, after a short pause in scrolling, moves on.
      const gap = now - m.lastWheel;
      m.lastWheel = now;
      if (now < m.restUntil) return;
      if (m.freshGesture) {
        if (gap < 450) return;
        m.freshGesture = false;
      }
      m.target = clampToPauses(m.display, clampScrollTarget(m.display, m.target + delta));
    };

    const onWheel = (event: WheelEvent) => {
      if (m.docked) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 32 : event.deltaMode === 2 ? window.innerHeight : 1;
      advance((event.deltaY * unit) / 1700);
    };
    let touchY: number | null = null;
    const onTouchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? null; };
    const onTouchMove = (event: TouchEvent) => {
      if (m.docked || touchY === null) return;
      const y = event.touches[0]?.clientY ?? touchY;
      advance(((touchY - y) * 2.2) / 1700);
      touchY = y;
    };
    const onKey = (event: KeyboardEvent) => {
      // Over a real page, only the presentation keys move the story (the page keeps arrows and space for itself).
      if (m.docked) {
        if (event.key === "PageDown" || event.key === "PageUp") {
          event.preventDefault();
          stepRef.current(event.key === "PageDown" ? 1 : -1);
        }
        return;
      }
      const active = document.activeElement;
      const interactive = active instanceof HTMLButtonElement || active instanceof HTMLAnchorElement || active instanceof HTMLInputElement;
      if (["PageDown", "ArrowRight"].includes(event.key) || (event.key === " " && !interactive)) {
        event.preventDefault();
        stepRef.current(1);
      } else if (["PageUp", "ArrowLeft"].includes(event.key)) {
        event.preventDefault();
        stepRef.current(-1);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        advance(0.35);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        advance(-0.35);
      } else if (event.key === "Home" && !interactive) {
        void goTo(0);
      }
    };
    const onPopState = () => {
      const scene = parseScene(window.location.search) ?? "opening";
      m.fromPopState = true;
      m.lastScene = scene;
      const position = scenePosition(scene);
      const stop = stopAt(position);
      if (stop) ensureMounted(STOP_SCREEN[stop]);
      void goTo(position, { animate: false }).then(() => {
        if (!stop) m.fromPopState = false;
      });
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("popstate", onPopState);
    };
  }, [ensureMounted, goTo]);

  // --- Render ------------------------------------------------------------------------------------------------------
  const caption = view.caption >= 0 ? CAPTIONS[view.segment][view.caption] : null;
  const docked = view.docked;
  const stopCopy = docked ? STOPS[docked] : null;
  const chapterIndex = CHAPTERS.indexOf(view.chapter);
  // Next / Previous: one caption (or real page) at a time, gliding and then waiting.
  const step = (direction: 1 | -1) => {
    const m = motion.current;
    if (m.docked) {
      if (direction > 0) continueFrom(m.docked);
      else {
        const back = previousPoint(STEP_POINTS, stopPosition(m.docked));
        void goTo(back ?? 0, { animate: !m.reduced });
      }
      return;
    }
    const from = Math.abs(m.target - m.display) > 1e-3 ? m.target : m.display;
    const target = direction > 0 ? nextPoint(STEP_POINTS, from) : previousPoint(STEP_POINTS, from);
    if (target !== null) void goTo(target, { animate: !m.reduced });
    // From the very start, back wraps round to the end of the story (the command exercise).
    else if (direction < 0) {
      ensureMounted("table");
      void goTo(stopPosition("command"), { animate: false });
    }
  };
  useEffect(() => {
    stepRef.current = step;
  });
```

#### `apps/web/src/components/journey/journey-experience.tsx` — lines 778–845 of 889

Rendering the caption card (with the person), the note over a real page, and the bottom bar.

```tsx
          {caption && (
            <div className={styles.caption} key={`${view.segment}-${view.caption}-${language}`} aria-live="polite" data-who={caption.who}>
              {caption.eyebrow && <span className={styles.eyebrow}>{tr(caption.eyebrow)}</span>}
              {caption.who && (
                <div className={styles.person} data-who={caption.who}>
                  <span className={styles.avatar} aria-hidden="true">{tr(CHARACTERS[caption.who].name).slice(0, 1)}</span>
                  <span>
                    <b>{tr(CHARACTERS[caption.who].name)}</b>
                    {caption.meet && <small>{tr(CHARACTERS[caption.who].role)} · {tr(UI.fictional)}</small>}
                  </span>
                </div>
              )}
              <p>{tr(caption.text)}</p>
              {caption.points && caption.points.length > 0 && (
                <ul className={styles.points}>
                  {caption.points.map((point, index) => <li key={index}>{tr(point)}</li>)}
                </ul>
              )}
              {caption.who && caption.meet && <q className={styles.question}>{tr(CHARACTERS[caption.who].question)}</q>}
            </div>
          )}

          <p className={styles.illustrative}>{tr(UI.illustrative)}</p>
        </>
      )}

      {/* Over a real page: whose page it is in the story, what it is, and any warning about the live page. */}
      {docked && stopCopy && closedNote !== docked && (
        <aside className={styles.dockNote} data-who={stopCopy.who} aria-label={tr(stopCopy.page)}>
          <p>
            <span className={styles.avatar} aria-hidden="true">{tr(CHARACTERS[stopCopy.who].name).slice(0, 1)}</span>
            <b>{tr(stopCopy.page)}</b>
            <span className={styles.dockText}>{tr(stopCopy.note)}</span>
          </p>
          <button type="button" className={styles.dockClose} onClick={() => setClosedNote(docked)} aria-label={tr(UI.close)} title={tr(UI.close)}>×</button>
          {stopCopy.warning && <p className={styles.dockWarning} role="note">{tr(stopCopy.warning)}</p>}
        </aside>
      )}

      {/* One navigation bar, always at the bottom: in the 3D story and over a real page alike. */}
      {status !== "failed" && (
          <nav className={styles.chapterNav} data-docked={docked ? "true" : "false"} aria-label={tr(UI.chapters)}>
            <button type="button" className={styles.step} onClick={() => step(-1)} aria-label={tr(UI.previous)}>←</button>
            <ol>
              {CHAPTERS.map((chapter, index) => (
                <li key={chapter}>
                  <button type="button" aria-current={chapter === view.chapter ? "step" : undefined} data-done={index < chapterIndex} onClick={() => void goTo(chapterEntry(chapter))}>
                    {CHAPTER_LABELS[chapter].number && <b>{CHAPTER_LABELS[chapter].number}</b>}
                    <span>{tr(CHAPTER_LABELS[chapter].title)}</span>
                  </button>
                </li>
              ))}
            </ol>
            {docked && stopCopy && (
              <a className={styles.step} href={stopCopy.href(language)} target="_top" aria-label={tr(UI.openPage)} title={tr(UI.openPage)}>↗</a>
            )}
            <button
              type="button"
              className={styles.step}
              disabled={view.atEnd && !docked}
              onClick={() => step(1)}
              aria-label={docked && stopCopy?.continueLabel ? tr(stopCopy.continueLabel) : tr(UI.next)}
              title={docked && stopCopy?.continueLabel ? tr(stopCopy.continueLabel) : tr(UI.next)}
            >→</button>
          </nav>
      )}

      {skipOpen && (
```

## C4. The 3D stage (`journey-stage.ts`, excerpts)

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 86–143 of 997

Camera keyframes and path sampling (each glide eases in and out and settles).

```ts
interface Key {
  at: number;
  pos: THREE.Vector3;
  target: THREE.Vector3;
  up?: THREE.Vector3;
  /** A waypoint the camera glides through without settling (it only shapes the path). */
  pass?: boolean;
}

const Y = new THREE.Vector3(0, 1, 0);
/** Where Mali and Dao stand, relative to Lalita at her gate (m). */
const LAYOUT_FAMILY = { mali: { x: 1.15, z: -0.95 }, dao: { x: 0.62, z: -0.3 } } as const;
type PersonId = "lalita" | "mali" | "dao" | "narin" | "pim";
const NORTH = new THREE.Vector3(0, 0, -1);
const PHONE_SCREEN_HEIGHT = 0.15;
const MONITOR_WIDTH = 0.66;
const TABLE_WIDTH = 2.9;

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
/** 0→1 as `value` goes from a to b, smoothed. */
const ramp = (value: number, a: number, b: number) => {
  const t = clamp01((value - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

function catmull(p0: THREE.Vector3, p1: THREE.Vector3, p2: THREE.Vector3, p3: THREE.Vector3, t: number, out: THREE.Vector3): THREE.Vector3 {
  const t2 = t * t, t3 = t2 * t;
  return out.set(
    0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
    0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
    0.5 * (2 * p1.z + (-p0.z + p2.z) * t + (2 * p0.z - 5 * p1.z + 4 * p2.z - p3.z) * t2 + (-p0.z + 3 * p1.z - 3 * p2.z + p3.z) * t3),
  );
}

/**
 * Camera pose along keyframes at segment progress p. Each glide between two keys eases in and out on its own, so the
 * camera settles on every shot (and a hold, two equal keys, lasts exactly as long as its keys say).
 */
function samplePath(keys: Key[], p: number, outPos: THREE.Vector3, outTarget: THREE.Vector3, outUp: THREE.Vector3): void {
  const x = clamp01(p);
  // Ease between the keys the camera settles on; pass-through waypoints keep the motion going.
  let s0 = 0;
  for (let k = 1; k < keys.length - 1; k += 1) if (!keys[k].pass && keys[k].at <= x) s0 = k;
  let s1 = keys.length - 1;
  for (let k = keys.length - 2; k > s0; k -= 1) if (!keys[k].pass) s1 = k;
  const span = Math.max(1e-6, keys[s1].at - keys[s0].at);
  const e = keys[s0].at + easeInOut(clamp01((x - keys[s0].at) / span)) * span;
  let i = s0;
  while (i < s1 - 1 && e > keys[i + 1].at) i += 1;
  const a = keys[i], b = keys[i + 1];
  const local = clamp01((e - a.at) / Math.max(1e-6, b.at - a.at));
  const k0 = keys[Math.max(0, i - 1)], k3 = keys[Math.min(keys.length - 1, i + 2)];
  catmull(k0.pos, a.pos, b.pos, k3.pos, local, outPos);
  catmull(k0.target, a.target, b.target, k3.target, local, outTarget);
  outUp.copy(a.up ?? Y).lerp(b.up ?? Y, local).normalize();
}
```

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 329–356 of 997

Creating the stand-in people: Mali and Dao at Lalita's gate, Pim at the planning table.

```ts
    const footShadow = (position: THREE.Vector3, size: number) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), blobMaterial);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.copy(position).add(v(0, 0.02, 0.02));
      this.scene.add(mesh);
      return mesh;
    };

    // Mali and Dao in the gate opening beside Lalita (on her left, clear of the camera's way round her right shoulder),
    // turned toward her and the road.
    this.mali = buildFigure({ skin: 0xb8876b, shirt: 0x6f8068, trousers: 0x54463f, hair: 0xb9b3aa, shoes: 0x4a3f38, sole: 0x3b332e, hairStyle: "bun", build: "f" });
    this.dao = buildFigure({ skin: 0xc99c80, shirt: 0xf1eee6, trousers: 0x2d3b5c, hair: 0x1c1512, shoes: 0x2a2a2e, sole: 0xe9e5dc, hairStyle: "short", build: "f" });
    // A child: smaller overall, with the larger head of a child's proportions.
    this.dao.root.scale.setScalar(0.74);
    this.dao.joints.head.scale.setScalar(1.2);
    for (const [figure, offset, turn] of [[this.mali, LAYOUT_FAMILY.mali, -0.75], [this.dao, LAYOUT_FAMILY.dao, -0.55]] as const) {
      const x = LAYOUT.resident.x + offset.x, z = LAYOUT.resident.z + offset.z;
      figure.root.position.set(x, terrainHeight(x, z), z);
      figure.root.rotation.y = turn;
      this.scene.add(figure.root);
      this.familyShadows.push(footShadow(figure.root.position, figure === this.dao ? 0.7 : 0.9));
    }

    // Pim stands at the north side of the planning table, facing the room (+z), her hands on its edge.
    this.pim = buildFigure({ skin: 0xb58266, shirt: 0x5d5478, trousers: 0x33363b, hair: 0x1d1714, shoes: 0x2b2826, sole: 0x2b2826, hairStyle: "bun", build: "f" });
    this.scene.add(this.pim.root);
    this.pimShadow = footShadow(new THREE.Vector3(), 0.9);

```

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 580–617 of 997

Posing the stand-ins (Pim's hands placed on the table edge with IK) and anchoring name labels above heads.

```ts

  /** Mali and Dao stand with Lalita: breathing, Mali a little stooped, Dao looking up at her mother. */
  private poseFamily(): void {
    poseStanding(this.mali, 0.12, this.time + 1.3, 0.07);
    poseStanding(this.dao, -0.16, this.time + 2.1, 0);
  }

  /** Pim leans over the planning table with her hands on its near (north) edge, looking down at it. */
  private posePim(): void {
    const table = this.screenGeometry(this.ops.tableScreen);
    const edge = table.center.z - table.height / 2 - 0.13;
    const figure = this.pim;
    figure.root.position.set(table.center.x + 0.45, this.ops.floor, edge - 0.2);
    figure.root.rotation.y = 0;
    this.pimShadow.position.copy(figure.root.position).add(v(0, 0.02, 0.02));
    poseStanding(figure, 0.5, this.time + 0.7, 0.2);
    figure.root.updateMatrixWorld(true);
    const j = figure.joints;
    const palmDown = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(v(-1, 0, 0), v(0, 0, -1), v(0, -1, 0)));
    // Facing +z, her left (+side) is world +x.
    for (const [side, shoulder, elbow, wrist] of [[1, j.shoulderL, j.elbowL, j.wristL], [-1, j.shoulderR, j.elbowR, j.wristR]] as const) {
      const target = v(figure.root.position.x + side * 0.27, this.ops.floor + 0.975, edge + 0.07);
      const s = shoulder.getWorldPosition(new THREE.Vector3());
      solveArm(shoulder, elbow, wrist, target, s.clone().add(v(side * 0.45, -0.5, -0.1)), palmDown);
    }
    setGrip(figure, "L", GRIPS.relaxed);
    setGrip(figure, "R", GRIPS.relaxed);
  }

  /** A point just above a person's head, for their name label. */
  private headAnchor(id: PersonId): THREE.Vector3 {
    const model = id === "lalita" ? this.residentModel : id === "narin" ? this.responderModel : null;
    const bone = model?.bones.get("Head");
    if (bone) return bone.getWorldPosition(new THREE.Vector3()).add(v(0, 0.32, 0));
    const figure = { lalita: this.resident, mali: this.mali, dao: this.dao, narin: this.responder, pim: this.pim }[id];
    return figure.joints.head.getWorldPosition(new THREE.Vector3()).add(v(0, id === "dao" ? 0.26 : 0.34, 0));
  }

```

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 618–657 of 997

Screens: the camera pose that makes a screen fill the window, and projecting a screen to a 2D quad.

```ts
  // --- Screens -------------------------------------------------------------------------------------------------------

  private screenGeometry(mesh: THREE.Mesh): { center: THREE.Vector3; normal: THREE.Vector3; up: THREE.Vector3; width: number; height: number } {
    mesh.updateWorldMatrix(true, false);
    const center = mesh.getWorldPosition(new THREE.Vector3());
    const quat = mesh.getWorldQuaternion(new THREE.Quaternion());
    const scale = mesh.getWorldScale(new THREE.Vector3());
    return { center, normal: v(0, 0, 1).applyQuaternion(quat), up: v(0, 1, 0).applyQuaternion(quat), width: scale.x, height: scale.y };
  }

  /** Camera pose at which a screen exactly fills the viewport height (and width, when the aspects match). */
  /** Camera pose square-on to a screen, at which it fills `fill` of the viewport height (1 = exactly). */
  private endPose(mesh: THREE.Mesh, fill = 1): Key {
    const g = this.screenGeometry(mesh);
    const distance = g.height / 2 / Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) / fill;
    return { at: 1, pos: g.center.clone().addScaledVector(g.normal, distance), target: g.center.clone(), up: g.up.clone() };
  }

  private project(point: THREE.Vector3): { x: number; y: number; inFront: boolean } {
    const camSpace = point.clone().applyMatrix4(this.camera.matrixWorldInverse);
    const ndc = point.clone().project(this.camera);
    return { x: ((ndc.x + 1) / 2) * this.viewport.width, y: ((1 - ndc.y) / 2) * this.viewport.height, inFront: camSpace.z < -this.camera.near };
  }

  private screenQuad(mesh: THREE.Mesh): Quad | null {
    const g = this.screenGeometry(mesh);
    // Hidden when the camera is behind the screen plane.
    if (this.camera.position.clone().sub(g.center).dot(g.normal) <= 0) return null;
    const right = g.normal.clone().cross(g.up).negate().normalize(); // up × normal
    const hw = g.width / 2, hh = g.height / 2;
    const corners = [
      g.center.clone().addScaledVector(right, -hw).addScaledVector(g.up, hh),
      g.center.clone().addScaledVector(right, hw).addScaledVector(g.up, hh),
      g.center.clone().addScaledVector(right, hw).addScaledVector(g.up, -hh),
      g.center.clone().addScaledVector(right, -hw).addScaledVector(g.up, -hh),
    ].map((corner) => this.project(corner));
    if (corners.some((corner) => !corner.inFront)) return null;
    return corners.map(({ x, y }) => ({ x, y })) as unknown as Quad;
  }

```

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 658–745 of 997

Camera choreography: the keyframes of every segment.

```ts
  // --- Choreography --------------------------------------------------------------------------------------------------

  private keysFor(segment: SegmentId): Key[] {
    const a = this.anchors;
    const R = a.resident;
    const ops = this.ops;
    const phoneC = this.screenGeometry(this.phoneScreen).center;
    const os = { at: 0, pos: R.clone().add(v(-0.78, 2.02, -0.5)), target: phoneC.clone() };
    const front = { at: 0, pos: R.clone().add(v(-1.9, 1.48, 3.6)), target: R.clone().add(v(0.2, 1.12, 0)) };
    const k = (at: number, base: { pos: THREE.Vector3; target: THREE.Vector3; up?: THREE.Vector3 }): Key => ({ at, pos: base.pos, target: base.target, up: base.up });
    const through = (at: number, base: { pos: THREE.Vector3; target: THREE.Vector3; up?: THREE.Vector3 }): Key => ({ ...k(at, base), pass: true });
    // Beside her, outside the garden wall: the way round to her shoulder that keeps clear of the gate post.
    const beside = { pos: R.clone().add(v(-1.05, 1.8, 1.35)), target: phoneC.clone() };
    const seat = ops.seat;
    const monitorC = this.screenGeometry(ops.monitorScreen).center;
    const tableC = this.screenGeometry(ops.tableScreen).center;
    const inside = { pos: v(seat.x - 3.6, ops.floor + 1.95, seat.z + 3.1), target: v(seat.x + 0.55, ops.floor + 1.0, seat.z) };
    // Over his right shoulder, with his hands on the keyboard and the screen both in frame; then past his shoulder
    // (he leaves the frame to the left, his hands below it) before the camera swings in front of the monitor.
    const overShoulder = { pos: seat.clone().add(v(-0.62, 1.42, 0.62)), target: monitorC.clone().lerp(ops.keyboard, 0.45) };
    const pastShoulder = { pos: seat.clone().add(v(0.2, 1.3, 0.4)), target: monitorC.clone() };
    const behind = { pos: seat.clone().add(v(-1.9, 1.75, 1.05)), target: overShoulder.target };
    // Simple camera language: a few clear shots, each reached by one smooth glide (no orbits or swoops). Holding a
    // shot is two keys with the same pose.
    const wide = { pos: v(-60, 35, 76), target: v(-6, 0, 3) };
    const road = { pos: v(-12, 9, 24), target: v(2, 0.4, 9) };
    const overview = { pos: v(-36, 42, 36), target: v(-6, 2, -10) };
    const windowFront = { pos: ops.window.clone().add(v(0, 0.9, 9)), target: ops.window.clone() };
    // The room over the planning table, aimed a little past its middle so Pim, at its far edge, is in frame.
    const roomView = { pos: tableC.clone().add(v(0, 3.4, 3.6)), target: tableC.clone().add(v(0, 0.3, -0.5)) };
    // Lalita with Mali and Dao in the gate: a step back from her, low, all three in frame.
    const family = { pos: R.clone().add(v(-0.5, 1.5, 4.7)), target: R.clone().add(v(0.6, 1.0, -0.5)) };
    const abovePlan = { pos: tableC.clone().add(v(0, 24, 0.02)), target: tableC.clone(), up: NORTH };
    // Straight down on the area, the flooded crossing right of centre (clear of the caption) and the office in view.
    const map = { pos: v(-2, 92, -7.02), target: v(-2, 0, -7), up: NORTH };
    const glide = (from: { pos: THREE.Vector3; target: THREE.Vector3 }, to: { pos: THREE.Vector3; target: THREE.Vector3 }, t: number) =>
      ({ pos: from.pos.clone().lerp(to.pos, t), target: from.target.clone().lerp(to.target, t) });
    switch (segment) {
      case "opening":
        return [k(0, { pos: v(-80, 46, 96), target: v(-2, 0, 4) }), k(1, wide)];
      case "everyday":
        // One straight descent from the neighbourhood to the resident at her gate.
        return [k(0, wide), k(0.5, glide(wide, front, 0.55)), k(1, front)];
      case "enter-phone":
        // Round her right shoulder, then straight onto the screen.
        return [k(0, front), through(0.3, beside), k(0.55, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "conditions":
        return [this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)), through(0.12, os), through(0.24, beside), k(0.6, road), k(1, road)];
      case "return-phone":
        // Down to the family at the gate and hold while they talk it through; then round her shoulder onto the phone.
        return [k(0, road), k(0.36, family), k(0.52, family), through(0.66, beside), k(0.8, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "sos-signal":
        // Back to the road view and hold while the water crosses it; rise to see the signal reach the operations
        // building; glide in through its window.
        return [
          this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)),
          through(0.08, os),
          through(0.15, beside),
          k(0.26, road),
          k(0.48, road),
          k(0.66, overview),
          through(0.86, windowFront),
          k(1, inside),
        ];
      case "enter-monitor":
        return [k(0, inside), k(0.5, overShoulder), through(0.78, pastShoulder), this.endPose(ops.monitorScreen, LANDSCAPE_PAGE_FILL)];
      case "aerial":
        // Step back from the monitor, rise straight up through the skylight to a map view of the whole area, hold,
        // then come straight back down onto the planning table.
        return [
          this.atKey(0, this.endPose(ops.monitorScreen, LANDSCAPE_PAGE_FILL)),
          through(0.04, pastShoulder),
          through(0.08, overShoulder),
          through(0.12, behind),
          k(0.22, roomView),
          through(0.34, abovePlan),
          k(0.46, map),
          k(0.74, map),
          through(0.88, abovePlan),
          { ...this.endPose(ops.tableScreen, LANDSCAPE_PAGE_FILL), up: NORTH },
        ];
    }
  }

  private atKey(at: number, key: Key): Key {
    return { ...key, at };
  }

```

#### `apps/web/src/components/journey/stage/journey-stage.ts` — lines 746–922 of 997

The per-frame story state: water, rain, overcast, phone raise, labels and which real page shows, per segment.

```ts
  // --- Frame ---------------------------------------------------------------------------------------------------------

  /** Advance the scene to timeline position `t` and render. */
  update(t: number, dt: number, render = true): StageFrame {
    this.time += dt;
    if (render && dt > 0) this.adaptResolution(dt);
    const { segment, progress: p } = locate(t);

    // Story state per segment.
    let raise = 0, glow = 0, phoneShow = 0, monitorShow = 0, tableShow = 0, rain = 0, affected = 0, attention = 0, signal = -1;
    // The connection line reads at neighbourhood scale; at human scale it would look like a pipe, so it fades out.
    let connection = 1;
    let water = WATER_LEVEL.dry, overcast = 0;
    const labels: Record<string, boolean> = {};
    switch (segment) {
      case "opening":
        labels.home = labels.clinic = labels.connection = p > 0.55;
        connection = ramp(p, 0.4, 0.6);
        break;
      case "everyday":
        raise = ramp(p, 0.62, 0.97);
        glow = ramp(p, 0.85, 1);
        phoneShow = ramp(p, 0.9, 1);
        labels.home = labels.clinic = labels.connection = p < 0.5;
        labels.mali = labels.dao = p > 0.82;
        connection = 1 - ramp(p, 0.4, 0.56);
        break;
      case "enter-phone":
        raise = 1; glow = 1; phoneShow = 1; connection = 0;
        break;
      case "conditions":
        raise = 1 - 0.5 * ramp(p, 0.05, 0.3);
        glow = 1 - ramp(p, 0.16, 0.3);
        phoneShow = 1 - ramp(p, 0.1, 0.2);
        water = waterLevelBetween("dry", "rising", ramp(p, 0.18, 0.78));
        rain = ramp(p, 0.1, 0.45) * 0.75;
        overcast = ramp(p, 0.1, 0.6) * 0.6;
        labels.home = labels.clinic = p > 0.35;
        labels.connection = p > 0.35;
        connection = ramp(p, 0.22, 0.42);
        break;
      case "return-phone":
        raise = 0.5 + 0.5 * ramp(p, 0.55, 0.85);
        glow = ramp(p, 0.76, 0.88);
        phoneShow = ramp(p, 0.86, 0.98);
        labels.lalita = labels.mali = labels.dao = p > 0.3 && p < 0.56;
        water = WATER_LEVEL.rising;
        rain = 0.75;
        overcast = 0.6;
        connection = 1 - ramp(p, 0.2, 0.4);
        break;
      case "sos-signal": {
        raise = 1;
        glow = 1 - ramp(p, 0.1, 0.2);
        phoneShow = 1 - ramp(p, 0.06, 0.12);
        water = waterLevelBetween("rising", "affected", ramp(p, 0.16, 0.46));
        affected = ramp(p, 0.3, 0.48);
        rain = 0.9 - 0.4 * ramp(p, 0.7, 0.95);
        overcast = 0.75;
        signal = p > 0.48 && p < 0.86 ? ramp(p, 0.5, 0.8) : -1;
        attention = ramp(p, 0.84, 0.98);
        labels.home = labels.clinic = labels.crossing = p > 0.24 && p < 0.6;
        labels.signal = signal >= 0;
        labels.operations = p > 0.58 && p < 0.84;
        labels.narin = p > 0.93;
        connection = ramp(p, 0.1, 0.22);
        break;
      }
      case "enter-monitor":
        water = WATER_LEVEL.affected; affected = 1; overcast = 0.75; rain = 0.5; attention = 1;
        monitorShow = ramp(p, 0.15, 0.5);
        raise = 1;
        labels.narin = p < 0.3;
        break;
      case "aerial":
        water = WATER_LEVEL.affected; affected = 1; overcast = 0.75 - 0.35 * ramp(p, 0.3, 0.7); rain = 0.5 * (1 - ramp(p, 0.25, 0.5)); attention = 1;
        monitorShow = 1 - ramp(p, 0.22, 0.3);
        tableShow = ramp(p, 0.8, 0.96);
        raise = 1;
        labels.home = labels.clinic = labels.crossing = labels.operations = p > 0.42 && p < 0.78;
        labels.pim = p > 0.15 && p < 0.3;
        break;
    }

    this.poseResident(raise, glow);
    this.poseResponder(attention);

    // Environment.
    this.water.position.y = water;
    this.waterNormal.offset.set(this.time * 0.006, this.time * 0.004);
    this.waterUniforms.uMud.value = clamp01((water - WATER_LEVEL.dry) / (WATER_LEVEL.affected - WATER_LEVEL.dry));
    this.waterUniforms.uRain.value = rain;
    this.waterUniforms.uTime.value = this.time;
    this.wet.uLevel.value = water;
    this.wet.uWet.value = clamp01(rain * 1.25 + overcast * 0.3);
    this.rain.material.uniforms.uTime.value = this.time;
    this.rain.material.uniforms.uIntensity.value = rain;
    this.rain.mesh.visible = rain > 0.01;
    const sky = this.sky.material.uniforms;
    sky.uTop.value.set("#b9cfd6").lerp(new THREE.Color("#9eaaad"), overcast);
    sky.uHorizon.value.set("#efe9dc").lerp(new THREE.Color("#d5d6d0"), overcast);
    sky.uCloud.value = 0.22 + 0.75 * overcast;
    sky.uTime.value = this.time;
    (this.scene.fog as THREE.Fog).color.set("#e9e6dc").lerp(new THREE.Color("#d2d4ce"), overcast);
    (this.scene.fog as THREE.Fog).near = 90 - 40 * overcast;
    this.sun.intensity = 3.1 - 1.9 * overcast;
    this.sun.color.set("#fff0d8").lerp(new THREE.Color("#e9eef0"), overcast);
    this.hemi.intensity = 0.42 + 0.25 * overcast;
    this.scene.environmentIntensity = 0.75 - 0.15 * overcast;
    this.connection.group.visible = connection > 0.01;
    this.connection.dryMaterial.opacity = 0.92 * connection;
    this.connection.crossingMaterial.opacity = 0.95 * connection;
    this.connection.setWaterLevel(water);
    this.connection.setAffected(affected);
    this.connection.tick(this.time);
    this.signal.tube.visible = this.signal.head.visible = signal >= 0;
    if (signal >= 0) {
      const total = (this.signal.tube.geometry.index?.count ?? 0);
      this.signal.tube.geometry.setDrawRange(Math.floor(total * Math.max(0, signal - 0.18)), Math.floor(total * Math.min(0.24, signal)));
      this.signal.head.position.copy(this.signal.curve.getPoint(signal));
      this.signal.head.scale.setScalar(0.8 + 0.25 * Math.sin(this.time * 8));
    }

    // Camera.
    const { pos, target, up } = this.scratch;
    samplePath(this.keysFor(segment), p, pos, target, up);
    this.camera.position.copy(pos);
    this.camera.up.copy(up);
    this.camera.lookAt(target);
    this.camera.updateMatrixWorld(true);
    this.rain.material.uniforms.uCenter.value.set(pos.x, Math.max(0, pos.y - 10), pos.z);
    const fp = this.ops.footprint;
    const indoors = Math.abs(pos.x - fp.x) < fp.w / 2 && Math.abs(pos.z - fp.z) < fp.d / 2 && pos.y < this.ops.floor + 5.6;
    if (indoors) this.rain.mesh.visible = false;
    this.followShadow(pos, target);
    // People cost dozens of draw calls: the responder is only drawn near the operations room, and the resident stops
    // casting a (sub-pixel) shadow from far away.
    const nearOps = pos.distanceTo(this.ops.seat) < 32;
    this.responder.root.visible = nearOps && !this.responderModel;
    if (this.responderModel) this.responderModel.root.visible = nearOps;
    const nearHome = pos.distanceTo(this.anchors.resident) < 60;
    for (const figure of [this.mali, this.dao]) figure.root.visible = nearHome;
    for (const shadow of this.familyShadows) shadow.visible = nearHome;
    if (nearHome) this.poseFamily();
    this.pim.root.visible = this.pimShadow.visible = nearOps;
    if (nearOps) this.posePim();
    this.clearCloseUps(pos);
    const opsLit = pos.distanceTo(this.ops.seat) < 48;
    for (const light of this.ops.lights) light.visible = opsLit;
    const residentCasts = pos.distanceTo(this.anchors.resident) < 45;
    if (residentCasts !== this.residentCastsShadow) {
      this.residentCastsShadow = residentCasts;
      (this.residentModel?.root ?? this.resident.root).traverse((object) => { object.castShadow = residentCasts; });
      this.phone.group.traverse((object) => { object.castShadow = residentCasts; });
    }

    // No post-processing: occlusion is baked (contact shadows, wall gradients, canopy tones), which measured several
    // times cheaper than screen-space AO on integrated graphics for a near-identical result.
    if (render) this.renderer.render(this.scene, this.camera);

    const frameLabels: LabelFrame[] = (["home", "clinic", "connection", "crossing", "operations", "signal", "lalita", "mali", "dao", "narin", "pim"] as const).map((id) => {
      const anchor = id === "signal" ? this.signal.head.position.clone().add(v(0, 1.6, 0)) : this.anchors[id] ?? this.headAnchor(id as PersonId);
      const projected = this.project(anchor);
      const onScreen = projected.inFront && projected.x > -40 && projected.x < this.viewport.width + 40 && projected.y > -40 && projected.y < this.viewport.height + 40;
      return { id, x: projected.x, y: projected.y, visible: Boolean(labels[id]) && onScreen };
    });

    return {
      screens: {
        phone: { quad: phoneShow > 0 ? this.screenQuad(this.phoneScreen) : null, opacity: phoneShow },
        monitor: { quad: monitorShow > 0 ? this.screenQuad(this.ops.monitorScreen) : null, opacity: monitorShow },
        table: { quad: tableShow > 0 ? this.screenQuad(this.ops.tableScreen) : null, opacity: tableShow },
      },
      labels: frameLabels,
    };
  }

```

## C5. Styles for the people (`journey.module.css`, excerpt)

#### `apps/web/src/components/journey/journey.module.css` — lines 290–344 of 351

```css
/* The person whose part of the story a caption tells, and the question that brings them to FloodGuard. */
.root { --lalita: #b0573a; --narin: #2f6a6c; --pim: #6a5a8e; }
.person { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.person > span:last-child { display: grid; line-height: 1.2; }
.person b { font-size: 0.92rem; }
.person small { color: var(--muted); font-size: 0.76rem; }
.avatar {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: var(--who, var(--teal));
  color: #fff;
  font-size: 0.82rem;
  font-weight: 800;
}
.root [data-who="lalita"] { --who: var(--lalita); }
.root [data-who="narin"] { --who: var(--narin); }
.root [data-who="pim"] { --who: var(--pim); }
.caption[data-who] { border-left: 4px solid var(--who); }
.question { display: block; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--who, var(--ink)); font-size: 0.95rem; font-style: italic; font-weight: 600; }

/* Over a real page: whose page it is, and what it is. Sits just above the bottom bar, clear of the page's own controls. */
.dockNote {
  position: fixed;
  z-index: 7;
  left: 16px;
  bottom: 80px;
  max-width: min(560px, calc(100vw - 32px));
  border: 1px solid rgb(21 43 41 / 12%);
  border-left: 4px solid var(--who);
  border-radius: 10px;
  background: rgb(250 248 242 / 96%);
  box-shadow: 0 8px 24px rgb(21 43 41 / 14%);
  animation: rise 420ms cubic-bezier(.2,.7,.2,1) both;
}
.dockNote p:first-child { padding-right: 36px; }
.dockClose { position: absolute; top: 4px; right: 4px; width: 28px; height: 28px; border: 0; border-radius: 999px; background: transparent; color: var(--muted); font: inherit; font-size: 1.1rem; line-height: 1; cursor: pointer; }
.dockClose:hover { background: rgb(21 43 41 / 8%); color: var(--ink); }
.dockClose:focus-visible { outline: 2px solid var(--teal); outline-offset: 1px; }
.dockNote p { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 0; padding: 7px 12px; font-size: 0.8rem; }
.dockNote .avatar { width: 22px; height: 22px; font-size: 0.7rem; }
.dockText { flex: 1 1 100%; color: var(--muted); font-size: 0.76rem; line-height: 1.35; }
.dockWarning { border-top: 1px solid #ecdcb4; border-radius: 0 0 10px 0; background: #fffaf0; color: #5b4516; }
@media (max-width: 760px) {
  .dockNote { left: 8px; right: 8px; bottom: 66px; max-width: none; }
  .dockText { display: none; }
  .question { font-size: 0.85rem; }
}
@media (prefers-reduced-motion: reduce) {
  .dockNote { animation: none; }
}

```


---

# Part D — Open questions I would like to discuss

1. **Is the story arc right?** Lalita (household) → Narin (evidence) → Pim (coordination). Does the hand-over from
   Lalita's fictional street to Narin's *real, historical* Mae Sai 2024 case read clearly, or does it confuse viewers?
2. **The help beat.** FloodGuard sends nothing (Report stays on the device; SOS only opens the phone's dialler with
   official numbers). The story therefore uses a *simulated call to hotline 1784* that reaches the district office
   "through the hotline, not through FloodGuard". Is that clear and honest enough, and is it still dramatic enough?
3. **Pim without scores.** The command exercise deliberately shows no FPPS score or action class ("Not issued yet").
   Pim's part is built on hourly figures, practice incidents (EX) and trainee mode instead. Does her chapter still show
   FloodGuard's value as a planning tool?
4. **Emotional anchor.** Should the story return to Lalita at the end (e.g. a final shot of the family, or the
   household–clinic link highlighted on the command map)?
5. **Cast quality.** Mali, Dao and Pim are simple procedural stand-ins next to two detailed rigged models. Worth
   generating rigged models for them, or keep them minimal?
6. **Same-device link.** A report saved in the public app during the story really does appear on the command exercise
   map on the same device. Should the story demonstrate this (it would mean the visitor saves a report themselves)?
7. **Length and pacing.** 15 caption pauses + 4 real pages = 19 presses of Next. Too long for a pitch? Which beats
   could merge?
8. **Copy.** Are the captions too long for a presentation? Thai copy still needs native review.
