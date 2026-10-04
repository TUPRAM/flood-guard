# Radar flood candidates for the eight Mae Sai tambons (plan tasks A2 and A4)

**Status: three own candidates of Tier 2. Verify before action.** A candidate is
not an observation of a flood and not an official warning. The layers are not
validated: nothing here was checked against a reference, so no figure in this
document says how correct a layer is. No FPPS, no A-E class and no ensemble was
computed. No candidate was compared with UNOSAT/GISTDA product 4009 (guardrail
GR4).

Source timestamp: Sentinel-1 pass of 15 September 2024, 23:16:01 UTC, which is
16 September 06:16 in Thailand (post-event image), paired with the pass of
3 September 2024, 23:16:00 UTC, on the same track (descending, relative orbit
135). Computed on 4 October 2026 (fourth run, after a review of the third; no
figure for the frame or for a tambon changed). Confidence: low. Rachmania owns
this lane and has not yet reviewed the run.

## Result in brief

The frame is the eight tambons of protocol v1a: 305.56 km2, 3,055,567 cells of
10 m. "Candidate area" is the area of the cells a method flagged from the change
in backscatter. It is not an area that was seen under water.

| Method | Candidate area, km2 | Outside permanent water, km2 | Share of the frame | Valid radar input | Cells with an answer | Cells without an answer |
|---|---:|---:|---:|---:|---:|---:|
| UN-SPIDER reproduction (A2) | 9.42 | 9.42 | 3.1% | 100.0% | 100.0% | 0.0% |
| M1-literal (A4) | 114.50 | 114.08 | 37.5% | 100.0% | 100.0% | 0.0% |
| M1-v2, frozen (A4) | 3.01 | 3.00 | 1.0% | 100.0% | 22.7% | 77.3% |

Label of every layer of the run of record: "(approximate geocoding: GCP affine,
no DEM terrain correction)". The label is the plan's. The warp that ran is a
second-order polynomial, not an affine fit (open point A4-OP7).

1. **A2.** Reproduces UN-SPIDER practice; 9.42 km2 of residual water at 16 Sep
   06:16 ICT; the published 93.38% OA does not transfer. The 9.42 km2 are cells
   whose smoothed VH quotient passed 1.25. Most of them are cropland (7.57 km2).
2. **A4, M1-literal.** It flags 37.5% of the frame. Its Otsu threshold lies
   between -1.9 and +0.1 dB in the nine tiles, so in most tiles the rule amounts
   to "VH fell at all". Protocol v1a declares it unable to meet the T2 skill bar.
3. **A4, M1-v2.** The frozen method gave no answer for six of the nine tiles:
   77.3% of the frame's cells. Where it answered it flagged 3.01 km2.
4. **T2 skill bar for M1-v2: not met.** For the frame as a whole, 0.773 of the
   cells have no answer, against a maximum of 0.20. Read tambon by tambon, the
   abstention condition and the coverage condition (by cells with an answer)
   fail in seven of the eight tambons and pass in one, Ban Dai (TH570908). The
   recency condition passes. M1-v2 therefore stays at low confidence (Tier 2,
   no demonstrated skill) for the frame and for seven tambons; whether one
   tambon can pass on its own is an open point for the owners (A4-OP3). The
   table says `outcome_of_record: not_met` and lists Ban Dai as undecided: no
   pass is of record for any tambon.
   Beside this, as decision R15 requires: the GEOID result (0.411) is not
   distinguishable from 0.40 on 14 tiles; 67.9% of the GEOID test cells had no
   answer; and the GEOID figure measures agreement with a same-pass CEMS map,
   not an independent check.
5. **The geocoding of the plan's fallback displaces the radar layers by about
   680 m.** Measured against mapped permanent water, the radar content lies
   670 m west and 130 m north of where it belongs. Two things cause it and add
   up: the height of the control points, and the misfit of the polynomial that
   GDAL fits to them. See "Geocoding".
6. **The two images of the run of record are offset from each other by about
   9 m.** The pre-event content lies 8.8 m east and 1.5 m south of the
   post-event content; a cell is 10 m. All three methods compare the two dates
   cell by cell. What the offset does to the candidates was not measured.

## What was run, and where each rule comes from

| Step | What the run does | Rule |
|---|---|---|
| Frame and case | Eight tambons TH570901 to TH570906, TH570908, TH570909; case O1, lane OBS, tier T2, reference date 15 September 2024 | Protocol v1a, `case_portfolio` |
| Image pair | Local SAFE files of 3 and 15 September 2024, relative orbit 135 | Plan 4.2 rows A2 and A4; decision D12 |
| Radiometry | Sigma0 = DN squared over the `sigmaNought` table squared, from the SAFE annotation. Never the uncalibrated amplitude. Thermal noise is not removed | Plan 4.2 row A4, fallback (no SNAP is installed) |
| Geocoding | The product's ground control points, fitted by GDAL's GCP polynomial, each date on its own. No order is asked for; GDAL chooses the second order. No terrain model; bilinear resampling to a 10 m grid in EPSG:32647 | Plan 4.2 row A4, fallback, with its label. The plan gives no polynomial order (open point A4-OP7) |
| UN-SPIDER | VH; focal mean of 50 m radius on dB; after divided by before; quotient above 1.25; perennial water removed; groups of fewer than 8 connected cells removed; slopes of 5 degrees or more removed | Plan 4.2 row A2 ("ratio 1.25, untuned") |
| M1-literal | Lee filter 5 by 5; Otsu threshold on delta-VH per tile; below the threshold and below zero; 3 by 3 majority | `floodguard.sar_change_v2`, as scored on GEOID (plan A3, A4) |
| M1-v2 | The frozen configuration, unchanged: refined-Lee, 64-cell blocks, Kittler-Illingworth threshold per tile, darkening of VH | Freeze receipt of 2 October 2026; guard `require_frozen_m1_v2` |
| Tiles | 1024 by 1024 cells of 10 m on the lattice of the GEOID sample (corners at multiples of 10,240 m), in UTM zone 47N. Nine tiles hold part of the frame | Not in the protocol: open point A4-OP6 |
| Permanent water | ESA WorldCover 2021, class 80 | Protocol v1a, `scoring_frame` (flood likelihood) |
| Threshold levels | The threshold of M1-literal and of M1-v2 moved by -1, 0 and +1 dB. The +1 dB level of M1-literal is cut at 0 dB (open point A4-OP9). The minus and plus one-pixel levels of the UN-SPIDER reproduction are not written (open point A2-OP2) | Protocol v1b, `ensemble_grid`, T2 levels (`t2_levels_by_input`) |
| Coverage and abstention | Per tambon: valid radar input, cells with an answer, cells without an answer, with a reason code | Plan 4.2 row A4; protocol v1a, C3 and C4 |
| T2 skill bar | `floodguard.confidence.t2_skill_condition`, per tambon and once for the input as a whole. The outcome is in a field of its own; a pass for one tambon alone is not written as a pass | Protocol v1a, `t2_skill_bar`; decision R15. The protocol does not say whether one tambon can pass on its own (open point A4-OP3) |

M1-v2 was bound before it was run: frozen configuration SHA-256
`2bfcb0c6ebf4b79402afa63c56209f2c5cda26491f08883d67908195b6c64a68`,
`sar_change_v2.py` `3127b370303b08902dc545442f7aa5a2aa54d283b471c0d65f5899c9c19e1134`.
Both protocol hashes are in the receipts.

Median sigma0 over the frame: VV -8.9 dB before and -9.0 dB after; VH -15.3 dB
before and -15.2 dB after. All cells of the frame have valid radar input on
both dates.

## A2: UN-SPIDER reproduction

| Tambon | Area, km2 | Valid radar input | Cells without an answer | Candidate area, km2 |
|---|---:|---:|---:|---:|
| TH570901 Mae Sai | 21.56 | 100.0% | 0.0% | 0.19 |
| TH570902 Huai Khrai | 44.34 | 100.0% | 0.0% | 0.00 |
| TH570903 Ko Chang | 47.42 | 100.0% | 0.0% | 3.63 |
| TH570904 Pong Pha | 43.62 | 100.0% | 0.0% | 0.47 |
| TH570905 Si Mueang Chum | 41.89 | 100.0% | 0.0% | 3.06 |
| TH570906 Wiang Phang Kham | 30.34 | 100.0% | 0.0% | 0.00 |
| TH570908 Ban Dai | 33.78 | 100.0% | 0.0% | 1.48 |
| TH570909 Pong Ngam | 42.61 | 100.0% | 0.0% | 0.57 |
| Frame | 305.56 | 100.0% | 0.0% | 9.42 |

Coverage is 100% in all eight tambons, so no tambon carries a reason code. The
practice has no way to decline: it answers every cell with valid input.

Steps, in cells of 100 m2: 97,268 above the quotient of 1.25; 508 removed as
perennial water; 493 removed as groups of fewer than 8; 2,102 removed by the
slope rule; 94,165 left.

The published 93.38% is an agreement with 80 ground points that the threshold
was chosen against, on images of 1 to 9 and 11 to 20 September 2024 (windows
that hold both dates of this pair; `GATE_RESEARCH_DOSSIER.md`) and with Earth
Engine's terrain-corrected data. It says nothing about this layer. Protocol v1a
declares the UN-SPIDER reproduction unable to meet the T2 skill bar.

Protocol v1b gives this candidate two more levels: minus and plus one pixel
(20 m) on the output extent. They are not written here. The protocol does not
say how 20 m is taken on a 10 m raster, nor who makes the two levels (open
point A2-OP2).

Differences from the published practice:

- Sigma0 from the SAFE table with a control-point warp, not Earth Engine's
  terrain-corrected backscatter with thermal noise removed.
- Perennial water is WorldCover class 80, not JRC seasonality of 10 months or
  more: the JRC tile on disk ends at 100 E and the frame reaches 100.04 E.
  On the 96.5% of the frame that the tile covers, the JRC layer gives 7.13 km2
  and WorldCover 7.09 km2.
- Slope is Copernicus GLO-30 averaged to 3 arc-seconds, not the HydroSHEDS DEM.
- One image per date, not a mosaic over a date range.
- No copy of the practice's script is in the repository. Its steps were written
  from the published script as the agent knows it; Rachmania should check them
  (open point A2-OP1).

## A4: M1-literal

| Tambon | Valid radar input | Cells without an answer | Candidate area, km2 | Outside permanent water, km2 |
|---|---:|---:|---:|---:|
| TH570901 Mae Sai | 100.0% | 0.0% | 6.87 | 6.83 |
| TH570902 Huai Khrai | 100.0% | 0.0% | 17.94 | 17.89 |
| TH570903 Ko Chang | 100.0% | 0.0% | 21.09 | 20.96 |
| TH570904 Pong Pha | 100.0% | 0.0% | 16.67 | 16.61 |
| TH570905 Si Mueang Chum | 100.0% | 0.0% | 15.93 | 15.87 |
| TH570906 Wiang Phang Kham | 100.0% | 0.0% | 13.55 | 13.53 |
| TH570908 Ban Dai | 100.0% | 0.0% | 4.50 | 4.48 |
| TH570909 Pong Ngam | 100.0% | 0.0% | 17.95 | 17.89 |
| Frame | 100.0% | 0.0% | 114.50 | 114.08 |

Coverage is 100% in all eight tambons. The area is not a flood extent: 29.66 km2
of it lie on slopes of 5 degrees or more, where water does not stand, and
43.93 km2 under tree cover. On GEOID the same method flagged about five times the
mapped flood area.

## A4: M1-v2 (frozen)

| Tambon | Valid radar input | Cells with an answer | Cells without an answer | Candidate area, km2 | Coverage at least 0.80 | Reason code |
|---|---:|---:|---:|---:|---|---|
| TH570901 Mae Sai | 100.0% | 0.0% | 100.0% | 0.00 | no | method_declined_for_the_tile |
| TH570902 Huai Khrai | 100.0% | 8.1% | 91.9% | 0.00 | no | method_declined_for_the_tile |
| TH570903 Ko Chang | 100.0% | 0.3% | 99.7% | 0.02 | no | method_declined_for_the_tile |
| TH570904 Pong Pha | 100.0% | 26.4% | 73.6% | 0.27 | no | method_declined_for_the_tile |
| TH570905 Si Mueang Chum | 100.0% | 34.3% | 65.7% | 1.26 | no | method_declined_for_the_tile |
| TH570906 Wiang Phang Kham | 100.0% | 0.0% | 100.0% | 0.00 | no | method_declined_for_the_tile |
| TH570908 Ban Dai | 100.0% | 98.7% | 1.3% | 1.07 | yes | none |
| TH570909 Pong Ngam | 100.0% | 15.4% | 84.6% | 0.39 | no | method_declined_for_the_tile |
| Frame | 100.0% | 22.7% | 77.3% | 3.01 | | |

"Coverage at least 0.80" is read here as cells with an answer. By valid radar
input all eight tambons reach it. The protocol does not say which is meant
(open point A4-OP3). A candidate area of 0.00 km2 in a tambon without an answer
means "no answer", not "no flood".

**How the tiles were cut.** M1-v2 declines a whole tile at a time, as it did on
GEOID. The frame is cut on the lattice of the GEOID sample: tiles of 1024 by
1024 cells of 10 m whose corners are multiples of 10,240 m, here in UTM zone
47N. Each tile is run whole, with the land outside the eight tambons that it
holds, and the result is cut to the frame afterwards.

| Tile | Frame cells in the tile | Tambons (last two digits) | Blocks kept of 256 | Threshold, dB | Result |
|---|---:|---|---:|---:|---|
| E058N221 | 1,229 | 03 | 11 | 5.1 | answered |
| E057N220 | 434,946 | 01, 04, 06, 09 | 0 | none | declined: no bimodal block |
| E058N220 | 890,130 | 01, 03, 04, 05, 06 | 33 | none | declined: blocks kept, no accepted threshold |
| E059N220 | 112,911 | 03, 05 | 28 | none | declined: blocks kept, no accepted threshold |
| E057N219 | 810,018 | 02, 04, 06, 08, 09 | 1 | none | declined: blocks kept, no accepted threshold |
| E058N219 | 687,376 | 02, 04, 05, 08, 09 | 57 | 5.2 | answered |
| E059N219 | 6,247 | 05 | 15 | 4.7 | answered |
| E057N218 | 100,840 | 02 | 3 | none | declined: blocks kept, no accepted threshold |
| E058N218 | 11,870 | 02 | 6 | none | declined: blocks kept, no accepted threshold |

"No accepted threshold" means that the pooled histogram of the kept blocks had
no interior Kittler-Illingworth minimum between its two fitted modes above
0 dB, which is the rule of amendment 1 of the GEOID benchmark. The tile that
holds most of Mae Sai town, Ko Chang and Si Mueang Chum (E058N220) is one of
them. Ban Dai passes because 98.7% of it lies in one tile that answered
(E058N219).

**Uncertainty: threshold levels** (protocol v1b: the threshold moved by 1 dB
each way; areas over the frame).

| Method | Strictest, km2 | Central (the method), km2 | Loosest, km2 |
|---|---:|---:|---:|
| M1-literal | 55.81 | 114.50 | 131.62 |
| M1-v2 (frozen) | 1.87 | 3.01 | 4.46 |

A tile that M1-v2 declined has no threshold to move, so it stays without an
answer at all three levels.

The loosest level of M1-literal is not the Otsu threshold moved by +1 dB in
most tiles. M1-literal flags a cell only where delta-VH is below the threshold
and below 0 dB. The run keeps that second clause at every level, so a moved
threshold above 0 dB is cut at 0 dB. Only two of the nine tiles get the full
shift; in five the loosest level is the central level again, cell for cell.

| Tile | Otsu threshold, dB | Shift that took effect at the +1 dB level, dB | The +1 dB level |
|---|---:|---:|---|
| E058N221 | 0.1 | 0.0 | identical to the central level |
| E057N220 | 0.0 | 0.0 | identical to the central level |
| E058N220 | -0.2 | 0.2 | cut at 0 dB |
| E059N220 | -1.3 | 1.0 | full shift |
| E057N219 | 0.1 | 0.0 | identical to the central level |
| E058N219 | -1.9 | 1.0 | full shift |
| E059N219 | -0.6 | 0.6 | cut at 0 dB |
| E057N218 | 0.0 | 0.0 | identical to the central level |
| E058N218 | 0.1 | 0.0 | identical to the central level |

The band of M1-literal (55.81, 114.50 and 131.62 km2) is therefore narrower
above the central level than below it by construction, not because of the
data. Protocol v1b says "Otsu threshold -1 / 0 / +1 dB" and does not say what
happens to the second clause. The rule was not changed here; it is open point
A4-OP9.

**Validity: candidate area by slope class** (slope from GLO-30 at 3
arc-seconds; areas over the frame).

| Slope class | Frame, km2 | UN-SPIDER, km2 | M1-literal, km2 | M1-v2, km2 |
|---|---:|---:|---:|---:|
| below 5 degrees | 242.4 | 9.42 | 84.84 | 3.01 |
| 5 to below 10 degrees | 8.2 | 0.00 | 3.83 | 0.00 |
| 10 to below 20 degrees | 24.8 | 0.00 | 11.75 | 0.00 |
| 20 degrees or more | 30.2 | 0.00 | 14.08 | 0.00 |

No HAND or slope mask was applied to M1-literal or M1-v2 (open point A4-OP2).
The three tiles that M1-v2 answered hold frame cells below 5 degrees only.

## The T2 skill bar of protocol v1a for M1-v2

Protocol v1a: a T2 input is low confidence unless four conditions all pass. One
is the GEOID condition. The other three concern Mae Sai and are evaluated here
with `floodguard.confidence.t2_skill_condition`.

| Condition | Threshold | Measured | Result |
|---|---|---|---|
| Abstention | at most 0.20 | Frame: 0.773. Per tambon: 0.013 to 1.000 | Fails for the frame and in 7 of 8 tambons; passes in Ban Dai (0.013) |
| Coverage | at least 0.80 | By cells with an answer: 0.000 to 0.987. By valid radar input: 1.000 in all eight | By cells with an answer it fails in 7 of 8 tambons; by valid radar input it passes in all eight |
| Recency | within 3 days of 15 September 2024 | 16 September in Thailand (1 day); 15 September in UTC (0 days) | Passes |

**Result: M1-v2 does not meet the T2 skill bar at Mae Sai.** It stays at low
confidence, Tier 2, with no demonstrated skill, for the frame and for seven of
the eight tambons. Protocol v1a gives a T2 input that does not pass a binding
class of E with the reason `low_confidence`. Classes belong to the planning
assessment (plan task E8); none was assigned here.

Ban Dai is the one tambon in which the Mae Sai conditions pass. With the GEOID
point estimate, the rule as `floodguard.confidence` applies it per tambon would
then evaluate to "pass" for Ban Dai alone. The protocol does not say whether
the conditions are taken per tambon or for the frame. This document does not
decide it (open point A4-OP3).

So that a later lane cannot take that reading for a decision, the table states
the outcome in a field of its own. For M1-v2: `outcome_of_record: not_met`,
`per_unit_reading: undecided (open point A4-OP3)` and
`units_whose_outcome_is_undecided: [TH570908]`. The outcome is `not_met`
because the input as a whole fails under every reading: the four conditions,
applied to the frame-wide share without an answer and to the smallest coverage
of any tambon, do not pass. A pass for one tambon alone is never written as a
plain pass: it is `passes_if_read_per_unit` in the tambon's row, and the list
is named `units_passing_only_if_the_conditions_are_read_per_unit`. No pass is
of record for any tambon. In the sensitivity table `outcome_of_record` is
empty and the outcome is under `outcome_of_this_evaluation`.

The GEOID condition, said as decision R15 requires every time:

- The GEOID result (0.411) is not distinguishable from 0.40 on 14 tiles.
- 67.9% of the GEOID test cells had no answer.
- The GEOID figure measures agreement with a same-pass CEMS map, not an
  independent check.

M1-literal and the UN-SPIDER reproduction are declared unable to meet the bar
by protocol v1a, whatever their figures are.

## Geocoding

The fallback of plan row A4 warps each image with the product's ground control
points, fitted by GDAL's GCP polynomial. Two things displace a cell along the
range direction, and they add up.

1. **The height of the control points.** They sit at the heights of a coarse
   terrain model. Interpolated over the frame those heights are 685 m (median;
   573 to 801 m from the 5th to the 95th percentile), where the median height
   of the frame is 382 m. A cell lower than the control points around it is
   placed too far from the radar. The one control point nearest the centre of
   the grid is at 785 m; the three next nearest are at 550, 685 and 610 m.
2. **The misfit of the polynomial.** The warp asks GDAL for no order. GDAL then
   chooses the second order for the 210 control points of each product, and
   does not report it; the run finds it by fitting each order and comparing
   (order 2 reproduces GDAL's transform to 0.0 image cells, an affine fit lies
   up to 82 cells from it). A second-order polynomial does not pass through the
   control points. For the pre-event image it lies 272 m from them along the
   range (root mean square over the 210 points; 1,012 m at most), and 150,
   419, 239 and 289 m from the four control points nearest the frame. Over the
   frame it reads the image 261 m nearer to the sensor (median; 137 to 394 m)
   than a spline that passes through every control point. For the post-event
   image the same figures are 273 m, 1,002 m and 271 m.

| Along-range displacement over the frame (heights read as ellipsoidal) | Median | 5th to 95th percentile | Mean |
|---|---:|---:|---:|
| Part from the height of the control points | 414 m | -174 to 537 m | 355 m |
| Part from the misfit of the polynomial | 261 m | 137 to 394 m | 259 m |
| Whole: the two mappings apart | 713 m | -14 to 727 m | 614 m |

The two parts add up to the whole for every cell, and so do the means. The
medians need not, because the height part shrinks and changes sign on the
hills. A warp that passes through the control points would take away the
polynomial part; the height part would stay. Such a warp is not in the plan
and was not run (open point A4-OP1).

| Check on the pre-event VH image against WorldCover permanent water | East | North |
|---|---:|---:|
| Control-point warp (the run of record), whole grid | -670 m | +130 m |
| The same, in the six tiles with enough mapped water | -650 to -730 m | +130 to +140 m |
| Mapping with a DEM height per cell, heights read as ellipsoidal | -10 m | +10 m |
| The same mapping, heights read as above sea level | -60 m | +20 m |

The geometry alone gives the same answer: the two mappings place a cell of the
frame 713 m apart along the range direction (median; bearing 280.5 degrees,
incidence 36.9 degrees). On the hills of Huai Khrai, Pong Ngam and Wiang Phang
Kham the displacement shrinks and changes sign with height.

**The two dates are not registered to each other.** Each date has its own
control points and so its own polynomial. Over the frame the post-event
polynomial reads the image 9.9 m nearer to the sensor than the pre-event one
(median; 8.8 to 12.6 m), each measured against its own control points, so the
content it shows lies that far further along the range. At a bearing of 280.5
degrees that puts the pre-event content 9.7 m east and 1.8 m south of the
post-event content. The images say the same:

| Pre-event content relative to post-event content, measured on the VH images | East | North | Correlation as the methods read the images | Correlation at the best shift |
|---|---:|---:|---:|---:|
| Run of record, whole grid | +8.8 m | -1.5 m | 0.642 | 0.665 |
| Run of record, frame cells only | +8.6 m | -1.4 m | 0.589 | 0.608 |
| Sensitivity run, whole grid | +0.1 m | -0.1 m | 0.692 | 0.692 |

The offsets are estimates to a fraction of a cell (the vertex of a parabola
through the correlation peak); another estimator can differ by a metre or two.
A cell is 10 m, so the two images of the run of record are almost one cell
apart east-west. All three methods compare the two dates cell by cell. An
offset of that size adds change that is not on the ground wherever the
backscatter has an edge, in the run of record only. What it does to the
candidates was not measured. The sensitivity run has no such offset, but it
differs from the run of record in the whole geocoding, so the two runs do not
isolate it.

**The label and the transform.** Every layer of the run of record carries the
plan's label, "approximate geocoding: GCP affine, no DEM terrain correction".
The plan prescribes it, so it is kept word for word. It names a transform that
was not run: the warp is a second-order polynomial. The plan gives no order,
and the order was GDAL's own choice (open point A4-OP7).

**The replay.** `scripts/build_mae_sai_flood_timeline.py` warps the
Sentinel-1 layers of the replay with the same call: the product's control
points, moved into the image window, fitted by GDAL's polynomial. Its layers
are probably displaced by a similar distance. That is an inference from the
identical warp: the replay's layers were not measured, and its bake was not
changed or rerun in this lane (open point A4-OP8).

What the displacement does to the run of record:

- Every candidate cell lies about 680 m west-north-west of the ground it
  describes. The layers must not be laid over roads, buildings or population
  cells.
- The tambon totals are displaced too: a tambon receives the radar content of a
  strip of its eastern neighbour and loses a strip in the west.
- The masks of the UN-SPIDER practice meet the wrong cells: the slope rule
  removed 2,102 cells where it removes 21,438 when the layers are aligned.

**Sensitivity run (not in the plan).** The three methods were run a second time
with the mapping that uses a DEM height for every cell
(`floodguard.sentinel1_sigma0.HeightAwareMapping`). This is not SNAP terrain
correction and not the plan's fallback. It replaces nothing: the run of record
is the fallback, and the owners decide which layers case O1 uses (open point
A4-OP1). The role of each run was fixed in the committed code before any
candidate was computed.

| Method | Run of record, km2 | Sensitivity run, km2 | Without an answer, record | Without an answer, sensitivity |
|---|---:|---:|---:|---:|
| UN-SPIDER reproduction | 9.42 | 8.30 | 0.0% | 0.0% |
| M1-literal | 114.50 | 116.36 | 0.0% | 0.0% |
| M1-v2 (frozen) | 3.01 | 3.04 | 77.3% | 77.3% |

| Tambon | UN-SPIDER, record | UN-SPIDER, sensitivity | M1-v2, record | M1-v2, sensitivity | M1-v2 without an answer (both runs) |
|---|---:|---:|---:|---:|---:|
| TH570901 Mae Sai | 0.19 | 0.16 | 0.00 | 0.00 | 100.0% |
| TH570902 Huai Khrai | 0.00 | 0.00 | 0.00 | 0.00 | 91.9% |
| TH570903 Ko Chang | 3.63 | 3.06 | 0.02 | 0.01 | 99.7% |
| TH570904 Pong Pha | 0.47 | 0.32 | 0.27 | 0.25 | 73.6% |
| TH570905 Si Mueang Chum | 3.06 | 2.83 | 1.26 | 1.27 | 65.7% |
| TH570906 Wiang Phang Kham | 0.00 | 0.01 | 0.00 | 0.00 | 100.0% |
| TH570908 Ban Dai | 1.48 | 1.72 | 1.07 | 1.36 | 1.3% |
| TH570909 Pong Ngam | 0.57 | 0.20 | 0.39 | 0.15 | 84.6% |

M1-v2 declined the same six tiles in both runs, so the outcome of the T2 skill
bar is the same. The areas of single tambons move by up to 0.6 km2.

## Limits

- One pair of images, twelve days apart. The second was taken on 16 September
  2024 at 06:16 in Thailand, several days after the flood peak: residual water
  only. Nothing here describes the peak.
- Approximate geocoding in the run of record: no cell-level or road-level use
  until the displacement is removed.
- The two images of the run of record are not registered to each other: the
  pre-event content lies about 9 m east and about 2 m south of the post-event
  content, and a cell is 10 m. The offset adds change that is not on the
  ground wherever the backscatter has an edge. What that does to the
  candidates was not measured.
- No qualified reference exists for Mae Sai. The layers are not validated, and
  no figure here says how correct a layer is.
- Tier 2 own candidates: verify before action.
- Radar shadow and layover are not flagged; that needs the terrain-corrected
  geometry of the SNAP path.
- Urban areas, wet soil, crops that changed between the two dates and wind on
  water all change the backscatter. A candidate cell is a cell that became
  darker, not a cell that was seen under water. Most of the UN-SPIDER and M1-v2
  area is cropland in September, when paddy fields change quickly.
- Thermal noise is not removed, so VH over open water sits at the noise floor
  and a fall in VH is understated there.
- The UN-SPIDER practice divides one dB value by another. Where the smoothed
  pre-event VH is above 0 dB its quotient means the opposite of what it means
  elsewhere. That is no cell in the run of record and 77 flagged cells in the
  sensitivity run.

## Open points for the owners

Nothing below was decided by the run. Each is in `open_points` of the tables.

| Id | Point | What the run did |
|---|---|---|
| A4-OP1 | The fallback geocoding displaces the layers by about 680 m, from two causes (the height of the control points, 414 m, and the misfit of the polynomial, 261 m; medians along the range), and leaves the two dates about 9 m apart. Which layers case O1 uses: the run of record, the sensitivity run, a warp through the control points, or SNAP | Ran the fallback as the run of record, measured the displacement, its two parts and the offset between the dates, and added a sensitivity run with a mapping the plan does not name. The effect of the offset on the candidates was not measured |
| A4-OP2 | Protocol v1a says a HAND and slope mask "is applied on Mae Sai" for M1-v2 and gives no HAND source, no HAND limit and no slope limit | Applied no mask; reported the area by slope class |
| A4-OP3 | Whether coverage means valid radar input or cells with an answer, and whether abstention is per tambon or for the frame | Reported and evaluated every reading |
| A4-OP4 | Whether the candidate raster or the flood-input reader removes permanent water | Left the rasters as the frozen functions return them; gave every area both ways |
| A4-OP5 | The July acquisition manifest marks both SAFE files "do not run baseline yet"; decision R14 lifts that for the replay | Read both files, as plan rows A2 and A4 name them |
| A4-OP6 | How a frame that is not made of GEOID tiles is cut for M1-v2 | Used the GEOID lattice in UTM zone 47N; tried no other |
| A4-OP7 | The plan's label says "GCP affine"; the plan gives no polynomial order, and the warp that ran is GDAL's second-order polynomial | Kept the label word for word, found the order and recorded it with its misfit; ran no affine warp |
| A4-OP8 | The Sentinel-1 layers of the replay are made with the same warp, so they are probably displaced as well | Nothing to the replay: its layers were not measured, and its bake was not changed or rerun. For the owners of the replay to measure |
| A4-OP9 | Protocol v1b moves the Otsu threshold of M1-literal by +1 dB and does not say what happens to the rule's second clause (delta-VH below 0 dB) | Kept the clause, so the +1 dB level is cut at 0 dB; said for every tile what took effect. The rule was not changed |
| A2-OP1 | The JRC tile east of 100 E and the HydroSHEDS DEM are not on disk; no copy of the practice's script is in the repository | Used WorldCover and GLO-30 and said so; gave the JRC figure where the tile reaches |
| A2-OP2 | Protocol v1b gives the UN-SPIDER reproduction a minus and a plus level of one pixel (20 m) on the output extent, and does not say how 20 m is taken on a 10 m raster or who makes the levels | Wrote the as-provided extent only; listed the two levels under `not_computed` |

## Every run, reported

All on 4 October 2026, with protocol v1a and v1b in force.

| Time (UTC) | Run | What it wrote |
|---|---|---|
| before 12:20 | Two checks of the geometry: annotation heights against the DEM, and the control-point fit. No backscatter was read | Nothing |
| before 12:20 | Two checks of the inputs on the real pair: sigma0 medians, and the displacement of the pre-event image against permanent water under both mappings. No change image and no candidate was computed | Nothing |
| 12:23:20 | First run of the run of record | Table `fe9686d9...d0d`, receipt `1ed082fd...fa6`; superseded, never committed |
| 12:26:45 | First sensitivity run | Table `9c141c16...b51`, receipt `3f84f14b...e39`; superseded, never committed |
| 12:35:23 | Second run of the run of record | Table `37ba5482...641`, receipt `4562b3b7...814`; superseded, never committed |
| 12:38:41 | Second sensitivity run | Table `e9ea731c...958`, receipt `8c73f98b...8e3`; superseded, never committed |
| 12:49:35 | Third run of the run of record | Table `9324f88b...bb5`, receipt `86f4d3c5...6a1`; superseded, committed in `c6d0cec` |
| 12:52:26 | Third sensitivity run | Table `5c3f0846...30b`, receipt `351342ba...3f8`; superseded, committed in `c6d0cec` |
| 13:50 to 13:54 | Three checks after a review of the third runs. They read the stored sigma0 rasters of both third runs and the control points of both SAFE files: the offset between the two dates to a fraction of a cell, the order of GDAL's polynomial, and its residuals at the control points. No change image and no candidate was computed | Nothing |
| 14:06 to 14:08 | One check: both dates calibrated and geocoded under both geocodings, and the geolocation check alone. No change image and no candidate was computed | Nothing |
| 14:24:38 | Fourth run of the run of record | The table and the receipt in `outputs/planning_v1/` |
| 14:27:47 | Fourth sensitivity run | The sensitivity table and its receipt in `outputs/planning_v1/` |
| after 14:28 | One check: the 32 GeoTIFFs of the fourth runs read beside the copies of the third runs | Nothing |

The second runs corrected one sentence (a limit that said the post-event image
was twelve days after the flood began) and the file names, which held a word
the outputs test reserves. The third runs changed wording only: three denials
were not in the form the shared wording lint lists. The fourth runs followed a
review of the third. They added what the tables did not say: the offset
between the two dates, the order and the misfit of the polynomial with the two
parts of the displacement, a stated outcome of the T2 skill bar, the cut of
the +1 dB level of M1-literal, and four open points (A4-OP7, A4-OP8, A4-OP9,
A2-OP2), with A4-OP1 reworded. No method and no input was changed.

No run changed a figure: every figure for the frame and for each tambon is the
same in all four. The 32 rasters have the same bytes in the first three runs.
In the fourth, the 16 rasters of the sensitivity run still have those bytes.
The 16 rasters of the run of record hold the same cell values, but their
`assumptions` tag now names the order of the polynomial, so their SHA-256
changed. The superseded tables and receipts are kept outside Git under
`<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_superseded_runs/`,
and each receipt names what it supersedes by SHA-256, back to the first run.
The first run's rasters are still in `radar_candidates_v1/` and
`radar_candidates_v1_height_aware_sensitivity/` beside the current folders;
they are byte-identical copies of the rasters of the third runs. The tests run
the builder on synthetic inputs only.

## Files

| File | What it is |
|---|---|
| `outputs/planning_v1/radar_o1_mae_sai_v1.json` | Run of record: every figure above, the tile results, the displacement check with the polynomial and the offset between the dates (`geolocation_check`), the T2 skill bar with its outcome of record |
| `outputs/planning_v1/radar_o1_mae_sai_v1_receipt.json` | Its receipt: inputs and outputs by SHA-256, parameters, both protocol hashes, run times |
| `outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity.json` | Sensitivity run |
| `outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json` | Its receipt; it names the run of record by SHA-256 |
| `outputs/planning_v1/run_register/a2_a4_*.json` | The four register entries, rewritten by the fourth runs |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1/` | 16 GeoTIFFs of the run of record, outside Git |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1_height_aware_sensitivity/` | 16 GeoTIFFs of the sensitivity run, outside Git |
| `scripts/build_mae_sai_radar_candidates.py` | The builder |
| `src/floodguard/sentinel1_sigma0.py`, `src/floodguard/radar_candidates.py` | Calibration, geocoding, the three methods on tiles, counts per tambon |

**The O1 flood inputs.** No flood-inputs module (plan task E1) is on this
branch. Each candidate is therefore a GeoTIFF mask with its table and receipt:
`<method>_candidate.tif` (1 flood candidate, 0 not a candidate, 255 no answer),
`<method>_reason.tif` (why a cell has no answer), `<method>_score.tif` (the
change score), and for M1-literal and M1-v2 `<method>_threshold_levels.tif`.
`frame_units.tif` holds the tambon of every cell. Every GeoTIFF carries its
source timestamp, confidence, assumptions and label as tags. Tier T2; temporal
relation `event_aligned`; acquisition 2024-09-15T23:16:01Z; attribution
"Contains modified Copernicus Sentinel data 2024".

## Reproduce

```text
python scripts/build_mae_sai_radar_candidates.py --external-data <root> --replace --reason "<why>"
python scripts/build_mae_sai_radar_candidates.py --external-data <root> --geocoding annotation_grid_with_cell_height --replace --reason "<why>"
```

A run of this script is a run on real units: it writes a new receipt that
names the one it supersedes, and it rewrites its register entries.
