# The replay's flood model: the river where it is, and a level fitted to the mud line. Plan v1

Written on 12 October 2026, after a diagnosis that compared the published
peak with the Sentinel-2 images (nothing was fitted in it) and before any
change to the model. The owner asked for it on 12 October: the modelled peak
should come as close to the mud of the 15 September image as an improved
model can bring it, on both banks of the border river.

## 1. What the diagnosis showed

The replay floods a cell when it lies lower than a water level above the
channel it drains to. The channels come from a 30 m surface model.

- **The model's main river is in the wrong place.** It routes the Sai, with
  its full catchment of 877 km², through the middle of the plain. The real
  Sai and Ruak follow the border; the model has that course as a side stream
  and gives it about half the water level.
- In the strip along the border the published peak covers 66 percent of the
  ground that turned to mud or stayed wet. A level of 10 m instead of 3.5 m
  would cover 92 percent and flood nearly twice the area: one level for the
  whole plain cannot do it.
- The surface model includes tree tops, which along a river adds metres to
  the ground the model sees.
- The agency layer the scored case uses covers 93 percent of that ground in
  the district. **The scored case and its classes are not concerned.**

## 2. The evidence: ground that turned to mud or stayed wet

From the two Sentinel-2 scenes the replay already shows (5 and 15 September
2024), on the 10 m grid:

- **Judged**: clear on both dates (scene classification 4, 5, 6, 7 or 11) and
  green on 5 September (NDVI of 0.45 or more).
- **Evidence**: judged, and on 15 September either brown without plants
  (NDVI of 0.25 or less, red above 1.08 times green and above 1.3 times blue)
  or still wet (MNDWI above 0).

It is a lower bound of the flood: a field that was under water for a day and
stayed green is not evidence, cloud hides 46 percent of the area on one date
or the other, and ground that was already bare on 5 September (the floods of
August left some) cannot be judged. The definition is the one of the
diagnosis and is not changed after the fit is seen.

## 3. Step 1: the river where it is

The lines OpenStreetMap maps as rivers (`waterway=river`; canals are not
used) are cut 20 m into the surface model **for the routing of flow only**.
Heights above the channel are still taken from the surface model as it was.
The upstream area of each channel, and with it the factor that scales the
water level, then follows the mapped rivers.

## 4. Step 2: the level of each stretch fitted to the mud line

For each channel cell, the stretch is every channel cell within 1 km of it.

- The **fitted peak level** of a stretch is the height above the channel
  that 90 percent of the evidence draining to that stretch lies below.
- A stretch with fewer than 50 evidence cells of 30 m (4.5 hectares) is not
  fitted. It keeps the rule of the published model: the peak level at the
  Sai bridges scaled by upstream area.
- The fitted level is not allowed above 8 m. Levels are averaged along the
  channel over 500 m, so that a fitted stretch runs into an unfitted one
  without a step.
- A cell floods at the peak when it lies lower than the level of the stretch
  it drains to. On the other days the level of every stretch rises and falls
  in step with the level at the bridges, as in the published model.

The 90 percent is fixed here and not chosen after seeing results.

## 5. Step 3: stretches held back

The fit uses the image, so the image is no longer a check of the fitted
model. One honest figure is kept:

- The area is cut into squares of 2 km. A channel cell belongs to the square
  it lies in, and the squares alternate like a chessboard between "fit" and
  "held back".
- The model is fitted once on the evidence of the fit squares only. On the
  held-back squares its levels come from neighbouring fit squares or from
  the unfitted rule.
- Reported for the held-back squares, beside the published model on the same
  cells: the share of the evidence the peak covers, and the share of the
  judged area inside the peak that shows evidence.
- The replay then uses a fit on all squares. The figures for the held-back
  squares come from the split run and are said to do so.

## 6. What is written, whatever the figures

1. The two shares of section 5 for the published model, for step 1 alone and
   for steps 1 and 2, on the held-back squares; and the same for the border
   strip.
2. The flooded area and the residents in the water at the peak, before and
   after, for the district.
3. The replay says in its own words that the peak is **fitted to the
   15 September image**, as it already says that the level of 10 September
   is anchored to GISTDA's figure.
4. If the fitted model does not cover more of the held-back evidence than
   the published one, that is the result and the published model stays.

## 7. What does not change

- The replay stays a modelled scenario: not an observation of the flood, not
  a forecast and not a warning. It computes no score and no class.
- The water is drawn on both banks. Every count (residents, roads, shelters,
  tambons) stays for Mae Sai district.
- The scored case SE1, its classes and the published result file.

## 8. Limits known before the start

- A level fitted to mud follows the mud: where the flood left none, the fit
  cannot see it, and where tree tops raise the surface model the fitted
  level is too high in metres although the outline is right.
- A height rule has no flow in it. It cannot hold water behind a road
  embankment or say when a place flooded.
- OpenStreetMap's river lines are where a mapper drew them.
- Every figure of the replay changes with the model. The earlier revision
  and its figures stay in the history of the repository.

## 9. Amended on 12 October 2026, after the prototype: what failed, and what the owner chose

Three things came out of a prototype that changed no published file.

**Step 1 is dropped.** With the mapped rivers cut in, the peak covered 63
percent of the evidence where the published model covers 73. The image shows
why: the flood also ran through the middle of the plain, along the course the
surface model takes for the main river. The published routing has a channel
on both courses and is kept. Section 3 is not carried out.

**Step 2 works where the image sees.** Fitted on the published routing, the
peak covers 89 percent of the evidence in the replay area (published: 73)
and 94 percent along the border river (published: 54).

**Step 3 fails by the rule of section 6, point 4.** Fitted on the fit
squares only, the model covers 62 percent of the evidence of the held-back
squares; the published model covers 73. A fitted level does not carry over
to a stretch two kilometres away that has no evidence of its own. By the
rule as written, the published model would stay.

**The owner chose the fitted model all the same** (12 October, after the
rule and its failure were put to him), for three reasons that are his and
the agent's to answer for:

1. The purpose is a replay that agrees with what the satellite saw, not a
   claim that the model predicts a flood better. The rule guards the second.
2. In the replay the model is fitted wherever the image sees, which is three
   quarters of the channels; the held-back test hides half of them.
3. The layer of UNOSAT and GISTDA, which the fit does not use and which also
   sees under cloud, agrees better with the fitted peak on both counts: 79
   percent of the layer lies inside the peak (published: 70) and 62 percent
   of the peak lies inside the layer (published: 60), in the district. That
   comparison was known when the choice was made, so it is recorded as known
   during tuning and is no longer an independent check of the replay.

**What follows from the failure, and is written into the replay:**

- The peak is **fitted to the Sentinel-2 image of 15 September**. Where the
  image sees no evidence (cloud, ground already bare, floods that left no
  mud) a stretch keeps the published rule.
- **The fitted levels do not carry over to places the image cannot see**;
  the held-back figures (62 against 73 percent) are given with the model.
- The Sentinel-2 water check of the replay shares the scene the fit uses. It
  is relabelled calibration-informed, as the replay's own rule on tuning
  requires.
- Nobody calls the fitted replay validated, more accurate or a better
  forecast.

A variant that never lowers a level below the published rule passed the
held-back test (75 against 73 percent) and floods more. It was designed
after the failure was seen and is not used.

The revision of the replay before this change stays reachable as an archive
(tag `replay-r4` in Git, and a page of the site).
