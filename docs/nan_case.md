# The Nan case

Case N1: our radar flood map (M1-z) tested on the Nan River floods of July
2025 under rules fixed in advance, then fed through the unchanged planning
chain. Every test figure is agreement with a reference layer or a dated
record, and says which. Planning guidance only: not real-time and not an
official warning. Confidence: low. Sources: Sentinel-1, 16 July to 13 August
2025 (Thai time); JAXA ALOS-2 maps of 19 and 28 July 2025 ("Provided by
JAXA", Sentinel Asia); THEOS-2, 31 July 2025; OpenStreetMap; WorldPop 2020;
news records of 24 to 27 July 2025; thaiwater.net gauges. Written 15 October
2026, after every stage of the case had run (score chain 14 October, 19:32
to 20:22 UTC).

## 1. What this case is and why

Our radar map had never fed a planning score. The Nan floods of late July
2025 (Tropical Storm Wipha) are the one flood covered by our THEOS-2 images
that also has a district-wide map from another satellite and wavelength
(JAXA's ALOS-2 map of 28 July, L-band), 14 Sentinel-1 passes, and dated
reports of road cuts and of the provincial hospital under water. The frame
is the 35 tambons of Mueang Nan, Phu Phiang and Wiang Sa. N1 takes our map as
its flood input; N2 takes JAXA's, for comparison only. The rules were fixed
in Git and pushed to GitHub before the test: rules, then tuning on other
events and a freeze, then the test stage: a first run, and test 1 of record
under amendment 2. Times of 14 October 2026, UTC, from `git log`, GitHub's
activity list (pushes; Git keeps none) and the stage logs:

| UTC | Commit (pushed) | What |
|---|---|---|
| 13:38:40 to 13:38:43 | (none) | JAXA files downloaded. Their SHA-256, in the plan of 13:48, shows them unchanged since; it cannot show that they were not opened |
| 13:48:37 | `fa7a4ed` (13:48:39) | Plan and protocol with the JAXA SHA-256 (R51) |
| 17:20:01 | `71743a7` (17:20:04) | Method code and inputs; amendment 1 (R52) |
| 17:22 to 17:23 | at `71743a7` | Tuning (`method/tune.log`) |
| 17:34:01 | `db121b7` (17:34:03) | Tuning record and freeze |
| 17:59:47 | `258c2d5` (17:59:50) | Radar record of the 27 July pass (orbit 172), after the freeze |
| 18:03 to 18:10 | at `258c2d5` | First run of the test stage (GFM fallback) |
| 18:20:44 | `72ff129` (18:20:46) | Code of tests 3a, 3b and 4, the time series, the brief and the slide, committed after the first run's figures were known |
| 18:34:19 | `14ec98b` (18:34:20) | The first run's record; amendment 2 (R53) |
| 18:55:13 | `8a0c29f` (18:55:15) | Script of test 1 of record |
| 19:05:53 | `0fb28e5` (19:05:54) | Radar record of all 14 passes and the dry seasons of orbits 62, 99, 135 and 172 |
| 19:06 to 19:07 | at `0fb28e5` | Maps stage: M1-z maps of the 14 passes (`method/maps.log`) |
| 19:10 to 19:13 | at `0fb28e5` | Test 1 of record |
| 19:28:42 | `e9c6576` (19:28:43) | Its record |
| 19:32:12 to 19:32:35 | after `e9c6576` | Tests 3a, 3b and 4 |
| 19:32:50 to 20:08:28 | after `e9c6576` | Score chain of case N1 |
| 20:09:06 to 20:22:39 | after `e9c6576` | Score chain of case N2 |
| 20:24:29 | after `e9c6576` | Test 5 |

The freeze was on GitHub at 17:34:03, 29 minutes before the first run. The
radar record's entry for the 28 July pass and its orbit-99 dry season are
the same at the freeze (`db121b7`) and at `0fb28e5`.

## 2. What was fixed first, and the two amendments

The protocol fixed the method and its grid of four limits (360 candidates),
three tuning events, the selection rule, five tests with pass rules, the
binding rule, the ensemble and what stays out of Git.

**Amendment 1** (R52) came before any candidate was scored, with every
reference sealed, from terrain, land cover, dry-season radar and road data
only.

| Change | Why |
|---|---|
| No-answer constraint: at most 0.10 above each set's lowest share, not at most 0.20 | Trees and buildings on low ground, which the method does not judge, put the lowest share at 0.372, 0.063 and 0.392 (Sukhothai, Mae Sai, Chaiyaphum); nothing could be chosen |
| Sentinel-1C event passes raised by 0.79 dB | On dry ground Sentinel-1C reads 0.79 dB darker in VH (Nan orbit 62 dry season); the test 1 pass is Sentinel-1C on orbit 99, against a Sentinel-1A dry season |
| Road points and hospital placed as OpenStreetMap allows; a fifth road cut of the same Ministry list added; Mae Sai's partial cells read as recorded; JAXA usability judged from the files' layers | Nan 021 is not in OSM; the protocol was silent on partial cells; no login-free source of ALOS-2 footprints |

**Amendment 2** (R53) came after the first run. That run found no
observation area in the JAXA files, took the GFM fallback and failed. A
check then read the 28 July zip in memory and found a second layer, REGION:
the ALOS-2 strip, holding 99.96% of the flood layer and 0.739 of the frame's
land. The frozen code matched "region" only after "obs". By the protocol's
own rule JAXA is then the reference, so amendment 2 made it test 1 of
record, run once by a script that imports the frozen code unchanged. The
first run stays beside it.

It was still decided blind to our map's agreement with JAXA. We knew the GFM
figure, test 2, the dry control, the size of JAXA's flood layer and REGION's
shape; nobody had scored our map against JAXA. Method and pass rule did not
change.

One field is wrong: amendment 2's `written_utc` says 18:55 UTC, later than
its commit at 18:34:19 UTC (R53 repeats it; R54 records the correction). It
stays as written because the test record binds the file's SHA-256
(`bf0895eb…`).

## 3. The method M1-z and its tuning

M1-z sets each cell's VH on the flood day against its own dry-season mean
and spread. A cell is flagged when both anomalous and dark. Terrain answers
first: more than the HAND limit above drainage, or a slope of 5 degrees or
more, is "not flooded". Trees and buildings on low ground get no answer.

Selected by mean IoU (no answer counted as not flagged): **z ≤ -1.0, VH ≤
-18 dB, HAND 5 m, no spread limit**, 0.513. One candidate tied within 0.01
(VH ≤ -17 dB, 0.506); the tie rule took the stricter.

| Tuning set (reference) | IoU | 95% interval | No answer (ceiling) |
|---|---:|---:|---:|
| Sukhothai (THEOS-2 water) | 0.518 | 0.306 to 0.579 | 0.372 (0.472) |
| Mae Sai (UNOSAT/GISTDA, 22 Oct 2024) | 0.303 | 0.260 to 0.335 | 0.063 (0.163) |
| Chaiyaphum (Sentinel-2, 28 Sep 2021) | 0.719 | 0.654 to 0.774 | 0.392 (0.492) |

The choice sits on three edges of the grid: the least strict z, the smallest
HAND, no spread limit. A better choice may lie beyond them.

HAND 5 m was the only limit the amended constraint allowed: all 60 eligible
candidates have it. A larger limit sends more low-lying trees and buildings
to "no answer"; at 10 m Chaiyaphum's share is at least 0.501, above its
ceiling. The score barely cared: the same choice at 10 m scored 0.511.

| Comparator, same sets | Sukhothai | Mae Sai | Chaiyaphum | Mean |
|---|---:|---:|---:|---:|
| R37 frozen detector | 0.584 | 0.413 | 0.753 | 0.583 |
| M1-v2, dry-season mean | 0.496 | 0.406 | 0.653 | 0.518 |
| R37 simple threshold | 0.529 | 0.260 | 0.724 | 0.504 |
| M1-literal, dry-season mean | 0.551 | 0.082 | 0.707 | 0.447 |
| UN-SPIDER practice, dry-season mean | 0.384 | 0.188 | 0.716 | 0.429 |

The R37 frozen detector (0.583) and M1-v2 (0.518) scored higher than M1-z
(0.513) on the tuning sets; the R37 detector partly on data it was tuned on
(Mae Sai and the Sukhothai tile).

## 4. The test of record against JAXA

Our map of the Sentinel-1C pass of 28 July, 11:20 UTC (18:20 Thai time),
with the 0.79 dB offset, against JAXA's map of 28 July inside REGION:
6,643,967 cells (73.9% of frame land), 56,355 of them JAXA water. The other
26% of the frame's land feeds the N1 classes untested. The pass's scenes
cover 82% of the frame grid. Inside REGION, 12.1% of the compared cells
have no radar value on it; M1-z answers 99% of those by terrain alone, and
JAXA shows no water there. JAXA's files give no time with a zone; the member
names carry "202507281720" (17:20, no zone). Read as UTC or as Japan time,
the 28 July pass is still the nearest, but the gap between the two looks is
not known.

| Against JAXA ALOS-2, 28 July | Central | 95% interval |
|---|---:|---:|
| IoU, no answer as not flagged (binding) | 0.226 | 0.173 to 0.282 |
| IoU on answered cells | 0.243 | 0.185 to 0.305 |
| Our flags on JAXA water | 0.476 | 0.396 to 0.558 |
| JAXA water we flag | 0.301 | 0.223 to 0.390 |
| No-answer share | 0.022 | 0.019 to 0.027 |

Terrain answers almost all of the compared cells: 95.4% are "not flooded"
before the radar is read (HAND 1,074,617 cells, slope 5,263,742). The radar
decides 2.4% (156,303 cells). The no-answer share is low because terrain
answers, not because the radar saw the land.

The pass rule asks IoU ≥ 0.40 and no answer ≤ 0.20. **Test 1 does not
pass.** Lower and upper levels: 0.225 and 0.223.

| Land cover | Compared | JAXA water | IoU | No answer |
|---|---:|---:|---:|---:|
| Cropland | 497,348 | 44,603 | 0.261 | 0.004 |
| Tree cover | 5,373,929 | 9,407 | 0 | 0.024 |
| Other | 700,303 | 1,505 | 0.271 | 0.001 |
| Built-up | 72,387 | 840 | 0 | 0.270 |

Without the Sentinel-1C offset (report only): IoU 0.221, 40.5% of flags on
JAXA water.

Comparators on the same pass and cells, reported, never renamed as the
result. M1-z answers by terrain where the pass has no radar; they do not.

| Method | IoU | No answer |
|---|---:|---:|
| UN-SPIDER practice, dry-season mean | 0.510 | 0.121 |
| R37 simple threshold | 0.467 | 0.121 |
| M1-v2, dry-season mean | 0.411 | 0.731 |
| R37 frozen detector | 0.399 | 0.121 |
| **M1-z, under test** | 0.226 | 0.022 |
| M1-literal, dry-season mean | 0.138 | 0.121 |

Two comparators meet the full bar: UN-SPIDER practice (0.510) and the R37
simple threshold (0.467), each with no answer 0.121. The R37 frozen detector
misses it at 0.399; M1-v2 fails on no answer (0.731). UN-SPIDER was last in
tuning (0.429). Section 7 says what we would do with this.

**Why it missed (counted after the test, report only).** Of the JAXA water
our map does not flag, most was ruled out by the terrain screen before the
radar was read: 28,024 of 39,402 cells (71%). By our map's reason codes on
all JAXA water (`outputs/nan_case/post_test_reasons_v1.json`):

| What M1-z did with JAXA's water | Share |
|---|---:|
| Flagged | 30.1% |
| Ruled out: HAND above 5 m | 43.2% |
| Ruled out: slope 5° or more | 6.5% |
| Radar read dry | 10.8% |
| No answer (trees 8.4%, buildings 0.7%) | 9.1% |
| Small group dropped | 0.3% |

By the HAND raster, 44.5% of JAXA's water on compared cells lies more than
5 m above drainage (median 4.2 m). The tuning sets did not show this cost:
at 10 m the tuning mean was 0.511, against 0.513 at 5 m.

The same pattern holds on another reference. In Wiang Sa, the terrain
screen rules out 75% of the THEOS-2 water of test 2 (6,914 of 9,184 cells:
HAND 5,814, slope 1,100; pass of 1 August, 06:08 Thai time). That water is
read by rule v2, which finds about 70% of the water three team labellers
marked (R47).

Report only: JAXA's 19 July map covers 8.2% of the frame's land and holds no
water there; our map of the pass of 19 July 23:08 UTC (20 July 06:08 Thai
time) flagged 4 of those 738,099 cells.

## 5. The other tests and the time series

### The first run: GFM, test 2 and the dry control

**Against GFM** (same Sentinel-1A pass of 31 July, so not independent). GFM
gives a value on 8.7% of the frame's land and excludes the other 91%. IoU
0.068 (0.032 to 0.108), a fail; 8.9% of our flags on GFM water. Of the
17,133 flags off it, 16,673 are cropland. Our reading, not tested:
wet-season paddy is darker than its dry-season mean, so our baseline flags
it; GFM's flood layer leaves it out.

**Test 2, Wiang Sa town on THEOS-2** (seen image, new method; not binding):
same pass, 19 hours after THEOS-2, 20,689 cells, 9,184 water. The THEOS-2
water is read by rule v2, which finds about 70% of the water three team
labellers marked (R47); it is a team reading, not a ground check.

| Against THEOS-2 water (rule v2) | Figure |
|---|---:|
| Our flags on water | 99% |
| Water we flag | 6.5% |
| IoU | 0.065 |
| Labelled points agreed (109, majority of three) | 41% |
| Built-up cells without an answer | 29% |

Where the map flags, THEOS-2 shows water; most of that water it misses, and
terrain rules out 75% of it (section 4). Built-up cells get no flag. The 41%
comes almost all from dry points: 44 of the 45 points that agree are dry.
Of the 65 points labelled as water, the map flagged 1.

**Dry control**, hills of the same scene where the THEOS-2 image shows no
water: 8 of 21,408 answered cells flagged, 0.04% (the rule allows 5%). It
passes. But terrain answers 21,146 of those cells (98.8%: slope 19,054,
HAND 2,092). The radar decided 262 and flagged 8 of them (3.1%). The control
mostly tests the terrain screen. The 28 July pass gives the same counts (8
of 262).

### Test 3a: roads under water in the Wiang Sa chip

Closures from the pass of 1 August, 06:08 Thai time (Sentinel-1A, orbit 62),
central level, closure rule v1, against THEOS-2 water (rule v2, 2 m; it
finds about 70% of the water three team labellers marked, R47) of chip 003,
19 hours earlier. Of 1,419 road edges crossing the chip, 1,290 (48.0 km)
are compared (at least 90% of the centreline observable). Of those, 516
(23.3 km) are seen under water (20 m of centreline on water, R26).

| Closures from | Closed edges compared | Closed edges seen under water | Edges seen under water that it closes |
|---|---:|---:|---:|
| Our map | 6 | 6 of 6 (1.00) | 6 of 516 (0.012; 0.004 by km) |
| JAXA, 28 July (case N2, report only) | 123 (18 more not compared) | 88 of 123 (0.72; 0.83 by km) | 88 of 516 (0.17) |

Where our map closes a road edge, THEOS-2 shows water on it. But the 6
closed edges are 84 m of road in all, against 23.27 km seen under water: it
closes one road edge in 86 of those THEOS-2 shows under water (0.4% by
length). That is the pattern of test 2: few flags, nearly all on water.
JAXA's map is three days older than THEOS-2.

### Test 3b: the five listed road cuts

A cut is found when a vehicle edge within 300 m of the point is closed at
the central level on a pass of 20 to 31 July, Thai time (amendment 1). Six
passes fall in the window; none falls on 29 to 31 July. The fifth cut was
added by amendment 1 from the same Ministry list.

| Listed cut | Placed on OpenStreetMap | Found |
|---|---|---|
| Highway 1243 km 59+100, Wiang Sa | yes, low confidence | no |
| Nan 4020 km 31+690, Lai Nan | yes, medium | no |
| Nan 4020 km 10+500, Na Pang | yes, low; the placed part lies wholly outside the listed tambon | yes, on the 26 July pass only (Thai time) |
| Nan 021 km 0, Fai Kaeo | no: not in OpenStreetMap | no |
| Nan 3019 km 7, Mueang Chang (supplementary) | yes, medium | no |

Found: 1 of 5 (0.2), with 4 placed. The one found is placed with low
confidence, outside its listed tambon. At three of the four placed points
the terrain screen answers almost the whole buffer: only 20, 95 and 38
cells have radar data. There, "not found" mostly means the radar was not
read.

### Test 4: Nan Hospital

A check, with no pass mark. Our maps of 22 July (18:22 Thai time) and 26 July
(06:06) are set beside six dated news records of water at the hospital,
published 24 to 27 July. The site is OpenStreetMap way 315323384
(76,269 m²).

| Pass, Thai time | Cells inside the site flagged | Cells within 200 m flagged | Edges within 200 m closed |
|---|---:|---:|---:|
| 22 July 18:22 | 0 of 193 | 6 of 1,056 | 0 |
| 26 July 06:06 | 0 of 193 | 15 of 1,056 | 0 |

On both passes all 193 cells of the site are answered by terrain as not
flooded: 114 lie more than 5 m above drainage, 79 on a slope of 5° or more.
The 26 July pass falls between the records; one published 3.6 hours after
it says the water had stood for more than 40 hours. The method cannot flag
this site. Terrain answers the whole site, as it answers most of the JAXA
water missed in test 1.

### The time series

All 14 passes, central map, flagged land in the frame (3,594 km² of land,
173,145 modelled residents). Report only; not checked against a reference.
"Footprint" is the share of the frame grid the pass's scenes cover (from
the catalogue). "Radar seen" is the share of the land terrain does not
answer where the pass has radar; it is not coverage. The last column is
gauge N.1 at the pass, minus its min_bank field.

| Pass, Thai time | Orbit | Footprint | Radar seen | Flagged km² (lower to upper) | Residents in flagged cells | N.1, m |
|---|---|---:|---:|---:|---:|---:|
| 16 Jul 18:20 | S1C 99 | 0.82 | 0.98 | 11.8 (8.7 to 14.0) | 2,531 | -3.18 |
| 20 Jul 06:08 | S1A 62 | 1.00 | 1.00 | 9.9 (7.4 to 12.2) | 2,012 | -3.20 |
| 22 Jul 18:22 | S1A 99 | 0.81 | 0.98 | 7.0 (4.7 to 8.9) | 1,406 | -3.54 |
| 25 Jul 06:16 | S1A 135 | 0.10 | 0.0005 | no observation | 0 | +2.23 |
| 26 Jul 06:06 | S1C 62 | 1.00 | 1.00 | 15.9 (14.0 to 17.4) | 4,058 | +0.56 |
| 27 Jul 18:30 | S1A 172 | 0.63 | 0.92 | 10.3 (7.9 to 12.2) | 2,090 | -1.41 |
| 28 Jul 18:20 (N1 input) | S1C 99 | 0.82 | 0.98 | 14.8 (12.5 to 16.6) | 3,549 | +0.42 |
| 1 Aug 06:08 | S1A 62 | 1.00 | 1.00 | 8.3 (6.4 to 10.0) | 1,791 | -1.82 |
| 3 Aug 18:22 | S1A 99 | 0.81 | 0.98 | 7.9 (5.8 to 9.6) | 1,482 | -3.14 |
| 6 Aug 06:16 | S1A 135 | 0.10 | 0.0005 | no observation | 0 | -4.12 |
| 7 Aug 06:06 | S1C 62 | 1.00 | 1.00 | 5.7 (4.2 to 7.1) | 1,191 | -4.35 |
| 8 Aug 18:30 | S1A 172 | 0.63 | 0.92 | 6.6 (4.9 to 8.0) | 1,394 | -4.53 |
| 9 Aug 18:20 | S1C 99 | 0.82 | 0.98 | 6.6 (4.8 to 7.9) | 1,322 | -4.72 |
| 13 Aug 06:08 | S1A 62 | 1.00 | 1.00 | 6.6 (4.8 to 8.2) | 1,513 | -4.56 |

- No pass sees the gauge peaks of 24 and 25 July. The only pass then, orbit
  135, has radar on under 0.05% of the land that matters. The highest
  figure is the first full pass after the peak, 26 July.
- Compare within one orbit. Orbits differ in viewing angle and in their dry
  seasons; the 27 July dip of orbit 172 is not a coverage effect.
- Within one orbit the platform may matter too. On orbit 99 the Sentinel-1C
  pass of 16 July, before the high water, flagged 11.8 km² against 7.0 km²
  for Sentinel-1A on 22 July, at a similar gauge level (-3.18 against
  -3.54 m). The two highest totals (26 and 28 July) are both Sentinel-1C. A
  platform effect left after the 0.79 dB offset (estimated on orbit 62,
  applied to orbit 99) is not ruled out.
- Along the river in Mueang Nan and Phu Phiang the flagged land rises at the
  high water and falls back by 7 to 9 August. Tha Nao: 0.72 to 2.03 km²
  (orbit 62, 20 to 26 July). Some Wiang Sa tambons rise late, 1 to 3 August.
- On low-river days (7 to 13 August) the maps still flag 5.7 to 6.6 km².
  What that land is (paddy, ponds or false flags) is not checked.

## 6. What it means for the score and for the pitch

Our own map ran through the whole planning chain on a real Thai flood: the
pass of 28 July, 18:20 Thai time (its scenes cover 82% of the frame grid),
with the frame's roads, residents and age counts, over the 180 cells of the
ensemble. Test 1 measured 74% of the frame's land; the other 26% feeds the
classes untested. The map had failed the test written in advance. So by the
binding rule every tambon of N1 is class E, low confidence, with its
would-be class beside it. `accepted_fpps` stays null.

**Case N1, 35 tambons.** Default cell: central map, central closure,
WorldPop 2020, P10/P90 anchors, default weights. FPPS runs from 0 to 100.
No answer is the share of the tambon's land outside permanent water.
Retention is the share of the 180 ensemble cells that keep the would-be
class (report only).

| Tambon | District | FPPS | Binding | Would-be | No answer | Retention |
|---|---|---:|---|---|---:|---:|
| Nai Wiang | Mueang Nan | 4.76 | E | E | 0.355 | 1.000 |
| Bo | Mueang Nan | 3.65 | E | E | 0.007 | 1.000 |
| Pha Sing | Mueang Nan | 3.64 | E | E | 0.019 | 1.000 |
| Chai Sathan | Mueang Nan | 9.38 | E | E | 0.164 | 1.000 |
| Thuem Tong | Mueang Nan | 10.47 | E | E | 0.104 | 1.000 |
| Rueang | Mueang Nan | 5.89 | E | E | 0.011 | 1.000 |
| Na Sao | Mueang Nan | 4.33 | E | E | 0.038 | 1.000 |
| Du Tai | Mueang Nan | 9.18 | E | E | 0.098 | 1.000 |
| Kong Khwai | Mueang Nan | 10.07 | E | E | 0.058 | 1.000 |
| Bo Suak | Mueang Nan | 5.48 | E | E | 0.017 | 1.000 |
| Sanian | Mueang Nan | 3.96 | E | E | 0.010 | 1.000 |
| Klang Wiang | Wiang Sa | 15.56 | E | E | 0.069 | 1.000 |
| Khueng | Wiang Sa | 24.15 | E | E | 0.014 | 1.000 |
| Lai Nan | Wiang Sa | 9.71 | E | E | 0.006 | 1.000 |
| Tan Chum | Wiang Sa | 13.61 | E | E | 0.082 | 1.000 |
| Na Lueang | Wiang Sa | 9.55 | E | E | 0.047 | 1.000 |
| San | Wiang Sa | 9.83 | E | E | 0.017 | 1.000 |
| Nam Muap | Wiang Sa | 28.04 | E | E | 0.007 | 0.867 |
| Nam Pua | Wiang Sa | 12.21 | E | E | 0.087 | 1.000 |
| Yap Hua Na | Wiang Sa | 7.93 | E | E | 0.009 | 1.000 |
| Pong Sanuk | Wiang Sa | 9.20 | E | E | 0.020 | 1.000 |
| Ai Na Lai | Wiang Sa | 8.65 | E | E | 0.025 | 1.000 |
| Sanna Nong Mai | Wiang Sa | none | E | none | 0.002 | n/a |
| Mae Khaning | Wiang Sa | none | E | none | 0.011 | n/a |
| Mae Sakhon | Wiang Sa | 7.95 | E | E | 0.023 | 1.000 |
| Chom Chan | Wiang Sa | 10.25 | E | E | 0.006 | 1.000 |
| Mae Sa | Wiang Sa | 11.91 | E | E | 0.031 | 1.000 |
| Thung Si Thong | Wiang Sa | 7.95 | E | E | 0.019 | 1.000 |
| Muang Tuet | Phu Phiang | 24.09 | E | E | 0.137 | 1.000 |
| Na Pang | Phu Phiang | 9.21 | E | E | 0.066 | 1.000 |
| Nam Kaen | Phu Phiang | 5.34 | E | E | 0.008 | 1.000 |
| Nam Kian | Phu Phiang | 5.48 | E | E | 0.016 | 1.000 |
| Mueang Chang | Phu Phiang | 5.34 | E | E | 0.013 | 1.000 |
| Tha Nao | Phu Phiang | 22.38 | E | E | 0.058 | 1.000 |
| Fai Kaeo | Phu Phiang | 5.80 | E | E | 0.014 | 1.000 |

- Every tambon fails C1, the case test. Some fail more: C3 and C4 in Nai
  Wiang; C4 in Muang Tuet and Tha Nao; C7 in Yap Hua Na; C5 (access gap not
  computed, so no FPPS) in Sanna Nong Mai and Mae Khaning.
- The binding class E holds in all 180 cells for all 35 tambons (guardrail
  GR8 asks at least 0.60). The would-be class holds in all 33 tambons that
  have one; the lowest is Nam Muap, 156 of 180 cells.
- Counting every no-answer cell as flagged (report only) counts all trees
  and buildings on low ground as water, a high bound. It changes the class
  read in 20 tambons: 13 to would-be B, 7 to D. The highest score is then
  Muang Tuet's 81.54 (B), then Tan Chum 63.07 and Tha Nao 62.39 (B) and Nai
  Wiang 59.21 (D).

**Test 5.** N1's class read (the binding class, or the would-be class of a
low-confidence row) is set against case N2's: the same chain with JAXA's
28 July map as the flood input, run on its central level only, over 60
ensemble cells (N1: 180) and without the no-answer sensitivity run. 34 of
35 tambons agree, a share of 0.971 against a pass mark of 0.70. Test 5
passes. The share says little: N1 reads E everywhere, so it says both
chains give low scores across the frame, not that they agree on an order.
N2's classes per tambon stay in the work folder.

**What the would-be classes and N2 suggest (report only).** All 33 would-be
classes are E, and every FPPS is under 35, the line below which the class
is E. Nam Muap's 28.04 is the highest. With JAXA's map as the flood input,
the chain still gives E in 34 of 35 tambons. Our reading, not tested: one
pass of this flood puts few of the frame's residents inside mapped water,
on either map, so the score moves little. But on this pass 18,607 modelled
residents are in no-answer cells, against 3,549 in flagged cells
(`time_series_v1.json`): the low scores rest on counting no answer as not
flooded. None of this is a priority list.

**The pitch.** The rule was applied as written: all 35 tambons are E at low
confidence. It changed no class here, because the would-be classes are E
too. This case does not show the rule stopping a wrong class.

May be said:

- "We ran our own radar map through the whole chain on a real Thai flood.
  It missed the bar we set in advance (IoU 0.226 against JAXA, bar 0.40),
  so all 35 tambons are class E at low confidence (their would-be classes
  are E too)."
- "Of the JAXA water our map does not flag, most was ruled out by the
  terrain screen before the radar was read (counted after the test, report
  only)."
- On the dry hills the map flagged 0.04% of the answered cells, but terrain
  answered almost all of them; of the 262 cells the radar decided, it
  flagged 8 (3.1%). In Wiang Sa 99% of its flags lay on THEOS-2 water (rule
  v2, which finds about 70% of the water team labellers marked), but it
  found 6.5% of that water.

May not be said:

- That the map works at Nan, or anything that makes agreement sound like
  correctness: it is not validated.
- That test 5's 97% shows the chain agrees with JAXA on priorities.
- That Nam Muap or any other tambon is a priority, or that the would-be
  classes are priorities.
- That a cell with no flag, or a tambon in class E, was not flooded: news
  records report water at Nan Hospital, a site the map answers "not
  flooded" by terrain.
- That the dry control shows no false radar flags on hills: terrain
  answered 98.8% of its cells.
- That UN-SPIDER's 0.510 is our result.
- That another HAND limit would have passed: it was not tested.
- That the method saw the hospital or the road cuts: it flagged the
  hospital site on neither pass and found 1 of 5 cuts.
- Anything beyond planning guidance: it is not real-time, not a forecast and
  not an official warning.

## 7. What we would do next (no work done)

- UN-SPIDER practice with a dry-season mean as the named method, in a new
  pre-registered test on the reserve event, Ubon Ratchathani, October 2022,
  still unopened. It did best at Nan, so Nan cannot be its test.
- A HAND limit tuned on sets whose land cover allows it. Here the no-answer
  rule, which grows with the limit, chose it. Nan, spent as a test, cannot.
- A seasonal-water mask like GFM's, so wet-season paddy is not read as flood.

## 8. Limits and data rights

- One event, one frame. References are other maps and team labels, not
  ground checks. C-band radar misses water under trees, between buildings,
  under rice and drained before the pass.
- Terrain answers 96% of the frame's land before the radar is read. HAND and
  slope come from Copernicus DEM GLO-30, a surface model that includes
  buildings and trees. Our reading, not tested: that can lift a town above
  the HAND limit; at the hospital site 79 of 193 cells lie on a slope of 5°
  or more.
- Sentinel-1C passes are raised by 0.79 dB, estimated on orbit 62 and
  applied to orbit 99. A platform effect left after it is not ruled out.
- The 28 July pass covers 82% of the frame grid, and test 1 measured 74% of
  the frame's land. JAXA's acquisition time is not known.
- The dry control is mostly a test of the terrain screen (98.8% of its
  cells answered by terrain).
- JAXA: Sentinel Asia terms (scientific use, no modification, credit
  "Provided by JAXA"). The zips stay unmodified outside Git, read in memory.
  GFM: figures only. No JAXA- or GFM-derived raster, map or per-tambon table
  enters Git.
- Sentinel-1: Copernicus open data. THEOS-2: hackathon free use, originals
  outside Git. Roads: © OpenStreetMap contributors (ODbL). News: paraphrased,
  cited.

## 9. Files

- Rules: `docs/proposal_execution/nan_case_plan_v1.md`, `nan_case_protocol_v1.json` and its amendments 1 and 2; decision log R51 to R54.
- Records in `outputs/nan_case/`: `tuning_v1.json`, `freeze_v1.json`, `test_result_v1.json` (first run), `test_1_jaxa_v1.json` (test of record), `post_test_reasons_v1.json` (reason counts after the test, report only), `radar_passes_*_v1.json`, `frame_v1.json`, `consequence_points_v1.json`, `news_records_v1.json`, `planning_result_n1_nan_v1.json` and its `_record.json` (the N1 chain), `test_5_decisions_v1.json`, `consequence_tests_v1.json` (tests 3a, 3b and 4), `time_series_v1.json` and `.png`.
- Brief and slide: `outputs/planning_brief/n1_nan_brief.md`, `.html` and `_record.json`; `docs/mentoring/visuals/nan_case_slide.png`.
- Code: `src/floodguard/m1z.py` and `scripts/nan_case_method.py` (frozen), `scripts/nan_case_test1_jaxa.py`, `scripts/nan_case_post_test_reasons.py`, `scripts/nan_case_chain.py`, `scripts/nan_case_consequence_tests.py`, `scripts/nan_case_time_series.py`, `scripts/build_n1_brief.py`, `scripts/build_nan_case_slide.py`.
- Tests 3 and 4 ran through a wrapper that sets the consequence script's test record to the record of amendment 2 and calls the script unchanged. Their record says which test record it read (`order.test_result`) but not the wrapper; `order.maps_index.test_result_matches` is false, because the maps index was written under the first run's record. Test 5 was computed with `class_agreement` of `src/floodguard/nan_case_chain.py` by a stage script; the wrapper and that script are not yet in the repository.
- Outside Git, `<external data root>/proposal_execution/nan_case_v1/`: sealed JAXA zips, radar, terrain, M1-z maps, case N2 references, and case N2's result and record (`score_chain/`).
