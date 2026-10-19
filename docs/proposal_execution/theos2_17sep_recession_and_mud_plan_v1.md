# THEOS-2 of 17 September 2024: the replay's recession and the mud the flood left, plan v1

Written on 19 October 2026. The scene GISTDA delivered was unpacked and its
metadata and raster headers were read that day
(`outputs/theos2_delivery/delivery_20240917_v1.json`). **Nobody has looked at
a pixel of it**: the owner said so on 19 October, and the agent that wrote
this plan has read no pixel. This plan says what two more questions will
compare, by which rules, in which order, and which sentences will be written
whatever the figures turn out to be.

It stands beside the frozen check of the radar
(`theos2_study_event_check_plan_v1.md` and its amendment 1), which asks of the
same scene how much of its water the radar flagged (question 1) and which
roads of the Ko Chang road sheet are under water on it (question 2). That
check is not changed by this plan. The two questions here are numbered 3 and 4.

## 1. The scene

| | |
|---|---|
| Satellite and product | THEOS-2, ORTHO PMS, four bands (red, green, blue, near infrared), 16-bit counts with radiometric processing BASIC, 0.5 m, EPSG:32647 |
| Taken | 17 September 2024, 03:54:20 UTC (10:54 local time) |
| After the Sentinel-1 pass of record | 28.6 hours (pass of 15 September 2024, 23:16 UTC) |
| After the modelled peak | about five days (the replay's peak is 12 September) |
| Delivered | two orders, each cut in two overlapping products: `AWG_20261014_bc7a15`, the town box (about 99.84 to 99.95 E, 20.37 to 20.46 N) and `AWG_20261014_417d92`, the west edge of the Ko Chang box (about 99.92 to 99.98 E, 20.37 to 20.47 N) |
| Footprint | 106 km² of the 305 km² district: all of the tambons Mae Sai and Wiang Phang Kham, about 40 percent of Ko Chang, Pong Pha and Si Mueang Chum. Roads 1, 3, 4, 5 and 7 of the Ko Chang road sheet have their centre inside; roads 2, 6 and 8 do not |
| Cloud | 0 to 8.5 percent by GISTDA's figures |
| Position | The upper-left corner the metadata states lies 0.0 to 1.9 m east of the one in the image file; the image file is used |
| Not delivered | 16 September, 21 September, January 2025, the rest of the district |

All four products lie on one 2 m grid. Where two products overlap, the
product that comes first in the order of its product name is used and the
pixels where the two give another answer are counted and reported.

The first road of the road sheet (OSM way 206803562, near 20.397 N,
99.948 E) lies just east of the town box; only order `417d92` covers it.

## 2. Why

**Question 3, the recession.** The flood replay (revision r5, the current
one) says the water had left the plain by the time of the image. At 10:54
local time on 17 September its stage is 0.042 m, below its first step of
0.05 m above the channel, so only channel cells are wet. The replay was never
tuned to, and nobody who tuned it knew, any image of 17 September. The scene
is therefore an independent test of the tail of the replay, the first one it
has.

**Question 4, the mud.** Five days after the peak, the clearest trace of the
flood on an image of 0.5 m is likely not water but the mud and sand it left
on streets, yards and fields. Mud is evidence that the water reached a place.
It answers in part what the water of the image cannot: question 2 can only
say that a road was under water on 17 September; mud on a road says the water
reached it at the peak. It can also show the extent of the flood inside Mae
Sai town, where the Sentinel-2 mud line the replay was fitted to never judged
a cell (that rule judges only ground that was green before).

## 3. Question 3: did the water leave when the replay says?

**The water of the image** is the 2 m raster of rule v2 that the reference
stage of the frozen check writes (amendment 1). Nothing new is computed from
the image for this question.

**The replay at the hour of the image.** The replay's own rule, on its own
grid (`hand-codes.png` of revision r5, bound by SHA-256): a cell is wet when
its code is the channel code or its code times 0.05 m is below the stage, the
stage being the linear interpolation of the replay's stage knots at the time
of the image. The water share of the image is averaged onto the replay grid,
and a cell is compared and wet by the rule of the frozen check
(`reference_cells`: compared at 90 percent observable or more, wet at a water
share of one half or more).

**Left out of every count:** channel cells, cells that never flood, cells of
permanent water (as in the frozen check), cells outside the district, cells
the image does not show.

**Counted, on the compared cells:** the water of the image in km², by the
replay's height above the channel (code 1 alone, which is the next step the
replay would wet, then 0.1 to 0.5 m, 0.5 to 1 m, 1 to 2 m, 2 to 5 m, above
5 m) and by WorldCover class, with cropland apart: paddy fields hold water
as part of farming, and water there is not counted as flood.

**Sentences fixed now:**

- **The test.** "The image contradicts the replay's recession" when the water
  of the image outside the channel, outside permanent water and outside
  cropland, in the compared part of the district, is **0.25 km² or more**.
  Otherwise: "the image does not contradict the replay's recession on the
  part of the district it shows".
- **The step.** "The replay's answer at that hour turns on one step: had the
  image been taken before 06:00 local time that morning, five hours earlier,
  the replay would wet the cells of its first step, about 13 km² of the
  district." The water of the image on the
  cells of code 1 is given beside this sentence.
- **Not a confirmation of timing.** A dry image says the water had gone by
  10:54 on 17 September. It does not say when it went.
- If the test is met, the replay is **not** retuned in this competition. A
  later revision that used the scene would list it under
  `exploratory_knowledge` as used for tuning.

## 4. Question 4: where did the mud lie?

### 4.1 What counts as mud

A square of 2 m more than half covered by a fresh deposit of the flood: brown
or grey mud, silt or sand on the ground, on a road, in a yard or on a field,
without plants over it, also a film of mud on pavement. Not mud: any roof,
clean pavement, plants, water, a shadow. Bare ground that could be mud or a
ploughed or long-bare field is its own label (section 4.4).

### 4.2 The candidates, fixed now

Every candidate gives each 2 m pixel one of three answers: mud, not mud,
unobservable. The answer of every candidate is unobservable on:

- cloud and water: what rule v2 marks unobservable or water;
- roofs: the outlines of the Google Open Buildings v3 and Microsoft file used
  by the project (`buildings_in_water`), widened by 1 m;
- pixels outside the four products.

The image's counts are not reflectance, so the colours of a rule written for
reflectance cannot be applied to them as they are. **Each band of the image
is first put on the scale of Sentinel-2 surface reflectance** by one fixed
procedure: the image is averaged onto the 10 m cells of the Sentinel-2 L2A
scene of 15 September 2024 (two days earlier, the scene of the replay's mud
line); 20,000 cells are drawn at random (seed 20261019) among the cells that
are clear on that scene (scene classes 4, 5, 6, 7, 11, as in the river fit),
observable and not water by rule v2, and outside building outlines; for each
band a straight line is fitted by the Theil-Sen estimator from the counts to
the reflectance of the matching Sentinel-2 band (red B04, green B03, blue
B02, near infrared B08). The four lines are recorded and applied to the 2 m
pixels.

| Candidate | Rule on the 2 m pixel, after the scaling |
|---|---|
| `mud_s0` | The colour rule of the replay's mud line, unchanged: NDVI 0.25 or less, red above 1.08 times green and above 1.3 times blue |
| `mud_s1` | `mud_s0`, and the 10 m Sentinel-2 cell under the pixel was green on 5 September 2024 (NDVI 0.45 or more) or lies within 10 m of a mapped road or in WorldCover built-up: bare where it was not bare, or on paved ground |
| `mud_s2` | `mud_s1` with its three limits chosen on the development points from NDVI 0.15, 0.20, 0.25, 0.30 by red/green 1.00, 1.04, 1.08, 1.12 by red/blue 1.1, 1.2, 1.3, 1.4 |

For each candidate, mud objects of fewer than 5 pixels (20 m²) are dropped.

### 4.3 How one candidate is chosen, on development points

- **160 development points**, seed 20261019, drawn at random inside five
  groups made by `mud_s0` alone: `mud_inside` (mud, more than 6 m from a pixel
  that is not), `mud_edge`, `near_mud` (not mud, within 6 m of mud),
  `ground_far` (observable, not mud, further away), `unobservable`; 40, 30, 30,
  45 and 15 points, half in each order where a group allows. A group with fewer
  pixels than its points gives the rest to `ground_far`.
- They are labelled by the agent that builds the rule (an AI model) from
  sheets of three pictures per point, as for rule v2: the 64 m around the
  point at 0.5 m in true colour and in false colour, and the 320 m around it
  at 1 m. The sheets show a number and the pictures, never the group. **These
  labels are development data, not a reference.**
- The score of a candidate is the **area-weighted F1** of the label mud on
  the points labelled mud or not mud: each group weighted by its number of
  pixels. Unobservable counts as not mud. The thresholds of `mud_s2` are
  chosen on the points of one order and scored on the points of the other, in
  both directions; its score is the mean of the two.
- **Choice:** the candidate with the highest score, but a candidate with
  fewer choices made on the points (`mud_s0`, then `mud_s1`, then `mud_s2`)
  is kept unless the other is better by **0.02 or more**. The chosen one is
  fitted on all development points if it is `mud_s2`, then frozen: its code,
  its limits, the four scaling lines and the SHA-256 of its 2 m raster go
  into `outputs/theos2_17sep_mud/freeze_v1.json`, committed before any test
  point is drawn.

### 4.4 The test, by three people

- **150 test points**, seed 20261020, drawn after the freeze in the five
  groups of the frozen rule: 45, 30, 25, 40, 10. No test point lies within
  20 m of a development point.
- **Three team members** label every point alone, on a page like that of the
  water label check: the same three pictures, the square outlined, no answer
  of the rule, no group, no order of the products. Labels: **Mud** (4.1),
  **Bare, mud or not cannot be told**, **Not mud**, **Cannot tell**. The page
  and the key stay outside Git; the page holds pixels of the scene and stays
  outside Git for good.
- **Scored once**, on the label at least two of three gave, each labeller
  and each pair beside it, area-weighted by group: the share of the area
  labelled mud that the rule calls mud, the share of the area the rule calls
  mud that is labelled mud, and the same with "Bare, cannot tell" counted as
  mud.
- **The bar.** The mud raster is used as a map for section 4.5 only if the
  share of the area the rule calls mud that is labelled mud is **0.60 or
  more**. Below that the result is: "the mud rule does not read the image as
  people do; no map of the mud is used", and section 4.5 reports the
  labelled points alone, per road and per tambon where they fall.

### 4.5 What the frozen mud raster is set against, each run once

**4a. Roads.** Every piece of the vehicle network of the planning context
inside the products, the eight roads of the road sheet listed first: the
metres of centreline with a mud pixel within 4 m, the metres the image shows.
A piece "shows mud" with 20 m of centreline or more (the length the closure
check uses for water).

- Mud on a road piece: "the water reached this piece at the peak". It does
  not give the depth; a shallow flow leaves a film too.
- No mud: "not shown". Streets may have been cleared of mud in the five days
  after the peak. **No mud never means the road stayed dry or passable.**
- A piece the image does not show is "not observable".

**4b. The replay's peak.** The replay's largest extent over the event (the
highest stage, by its own rule). On the compared ground: the share of the mud
inside that extent, the mud outside it in km² by tambon, and the replay's
height above the channel of the mud outside it. Each figure is given in two
strata:

- **cells the river fit judged** (clear on both Sentinel-2 scenes and green on
  5 September): the replay was fitted to the Sentinel-2 mud line there, so
  agreement there is **not independent**, and that is said;
- **cells it did not judge** (most of them built-up or road): the replay never
  saw mud there, so agreement there is an independent check.

**4c. Case SE1.** The water of the season scenario of case SE1 (the
accumulated layer of product 4009, cut to the district): the share of the mud
inside it, per tambon the products cover. Report-only.

**4d. Buildings reached.** The building outlines with a mud pixel within 4 m,
per tambon the products cover. No resident figure is derived from them.

## 5. Order of the commits

1. This plan, with the delivery record, before anybody looks at the image.
2. The reference of the frozen check (rule v2 and rule v1), with the look
   written down; then its comparison (questions 1 and 2), once.
3. Question 3, once.
4. The development points and their sheets; the agent's labels; the freeze
   record of the mud rule.
5. The test points and the page; three labels; the test score, once.
6. Section 4.5, once.

Each run checks the SHA-256 of this plan and of the records before it.

## 6. What this will not do

- It qualifies no flood map and opens none of the gates of the signed
  protocols. Report-only: no published class changes, nothing enters a
  planning score, case SE1 stays a scenario.
- It retunes nothing in this competition: not the replay, not the radar
  readings, not rule v2.
- The only choices made on the scene are the choice among three mud
  candidates and the limits of `mud_s2`, on the development points.
- The imagery, the sheets and the label page stay outside Git. Figures
  derived from the image are shared; a picture of the image is shown only if
  GISTDA says it may be.
- Nothing here is an observation in real time or an official warning.

## 7. Known weaknesses, stated before the result

- The counts are not reflectance, and the scaling borrows the Sentinel-2
  scene of two days earlier; ground that changed in between bends the lines.
- Streets in town may have been cleared of mud before the image; a clean street is
  silent, not dry.
- Red and brown roofs missing from the building outlines, dirt roads and
  building sites look like mud.
- Terrain shadow in the hills to the west of the town; the scene was taken
  at a viewing angle of about 28 degrees.
- The replay's answer at the hour of the image sits just under its first
  step of 0.05 m.
- The development labels are the reading of an AI model, and three people
  agreed with each other on 57 percent of the water points of the label
  check; mud is harder to tell than water.
- The scene covers the town, its west and the west edge of Ko Chang, not the
  district: every figure is for the part the products cover.
