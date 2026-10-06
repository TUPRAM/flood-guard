# Why threshold-only change detection failed at the 16 Sep pass

**Status: a diagnosis (plan task A1). It is not a flood map, not an observation
of a flood and not an official warning.** It explains why a single threshold on
the change in radar backscatter gave no usable answer at Mae Sai for the
Sentinel-1 pass of 15 September 2024, 23:16 UTC, which is 16 September 06:16 in
Thailand. No figure here says how correct a method is. No FPPS, no A-E class
and no flood candidate was computed.

- Source timestamp: Sentinel-1 passes of 3 and 15 September 2024, 23:16 UTC;
  season envelope of 1 August to October 2024; GEOID-Flood sample of
  3 January 2024.
- Computed on 4 October 2026 (UTC; 5 October in local time), with planning
  protocols v1a and v1b in force: first runs from 20:27 to 20:36 UTC, and,
  after a review, superseding runs of all seven figures from 22:14 to 22:16
  UTC. Section 10 lists every run.
- Confidence: low. Nothing here was checked against a qualified reference; none
  exists for Mae Sai. Rachmania owns this lane and has not yet reviewed the runs.
- Assumptions: stated with each figure, and in every figures file under
  `outputs/a1_diagnosis/`.

Three figures are measured against the accumulated layer of UNOSAT/GISTDA
product 4009. Each carries the label of plan row A1: **vs a season envelope, not
an event map**. The layer is an unvalidated preliminary agency extent (UNOSAT
product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA
4.0. FloodGuard did not validate it. Credit: UNOSAT and GISTDA, FL20240912THA,
UNOSAT product 4009. Changed by FloodGuard: the layer was repaired, projected to
EPSG:32647, clipped to AOI-01 and, for two figures, put on a 20 m grid by cell
centre; areas and rank statistics were then computed. Those figures are shared
under CC BY-SA 4.0. The radar figures contain modified Copernicus Sentinel data
2024. The terrain figure and the slope use the Copernicus DEM GLO-30.

## In brief

1. **No Sentinel-1 pass falls in the days when, by the replay's keyframes, the
   water rose and peaked.** The catalogue snapshot holds four Sentinel-1 passes
   over Mae Sai in September 2024 and none between 6 September 11:31 UTC and
   15 September 23:16 UTC: a gap of 9.49 days. The pass that was used came 3.76
   days after the keyframe the replay sets for the modelled peak. The keyframes
   are illustrative; no gauge record exists. Other radar satellites did look in
   those days (RADARSAT-2 and ALOS-2); none of their data is cleared for this
   lane.
2. **The retired M2 method asked each window for two clearly separate
   populations, and one normal (bell-shaped) population does not pass.** Its
   gate is a between-class variance fraction of 0.72. One normal population
   gives 0.637 in theory and 0.649 through the M2 kernel. All 81 windows at Mae
   Sai scored between 0.598 and 0.651, and all 1,421 windows of a labelled
   foreign flood event scored between 0.532 and 0.712. Every window was
   declined. The gate tests the shape of the histogram, not the number of
   populations: one flat-topped population would pass it (0.750).
3. **Where the M2 run looked was small.** Its pilot grid holds 42.3% of AOI-01
   and leaves out 79.7% of the 2024 season envelope inside AOI-01.
4. **At that pass, darkening does not point at the season envelope.** Under the
   definition of the exploratory run, a cell inside the envelope darkened more
   than a cell outside it in 42.1% of pairs (0.421, where 0.5 is no
   separation). That value rests on choices no signed file makes. It is 0.467
   with no smoothing and 0.299 with a 25-cell window, 0.445 on flat ground
   only, and 0.377 with the radar layers placed more exactly. Every reading is
   below one half: 0.254 to 0.478.
5. **On all of AOI-01, terrain mostly tells the plain from the hills.** Low
   ground gives 0.616 and flat ground 0.680, because 97.4% of the envelope
   cells have a slope under 5 degrees against 68.0% of the other cells. On the
   cells under 5 degrees, low ground gives 0.445 and flat ground 0.544. On the
   same cells the radar change, read as brightening, gives 0.555 and 0.614.
   None of this maps a flood, and it gives no ranking of terrain against radar.

So a threshold on darkening had little to find. A method with a quality gate
declines (M2; and M1-v2 on six of nine tiles, by a rule this page did not
examine). A method without one puts its threshold near zero and flags a third
of the frame (M1-literal).

## 1. What the pass of 16 September could and could not see

Sentinel-1A was the only satellite in the snapshot. It crossed Mae Sai on two
tracks, each every 12 days.

| Pass (UTC) | In Thailand | Track (relative orbit) | Role |
|---|---|---|---|
| 3 Sep 2024, 23:16:00 | 4 Sep, 06:16 ICT | 135 | before image of the pair |
| 6 Sep 2024, 11:31:06 | 6 Sep, 18:31 ICT | 172 | not used |
| 15 Sep 2024, 23:16:01 | 16 Sep, 06:16 ICT | 135 | after image of the pair |
| 18 Sep 2024, 11:31:07 | 18 Sep, 18:31 ICT | 172 | not used |

No Sentinel-1 pass lies between 6 September 11:31 UTC and 15 September 23:16
UTC. That gap is 227.7 hours, or 9.49 days, and it is the longest in the
snapshot.

**The snapshot holds Sentinel-1 only.** Other radar satellites did look in the
gap. Committed files name a RADARSAT-2 analysis by GISTDA of 10 September 18:15
(`docs/demo/replay_numbers.md`, key `cal.gistda`) and ALOS-2 acquisitions of 14
and 15 September (planning protocol v1a, case O4, which needs permission; the
protocol gives the dates and no time of day). None of their data is cleared for
this lane, and none was read. So this section says what Sentinel-1 could see,
not what any radar could see.

The Mae Sai replay sets two keyframes inside that gap: the onset at 10 Sep
18:15 ICT and the modelled peak at 12 Sep 12:00 ICT (`docs/demo/replay_numbers.md`,
keys `stage.onset_knot` and `stage.peak`; the script reads both rows at run
time). They are illustrative scenario keyframes shaped to the event chronology;
no gauge record exists for September 2024, so they are not observations. Set
beside the passes:

- the last pass before the onset keyframe was 95.7 hours earlier;
- the next pass came 132.0 hours (5.50 days) after the onset keyframe and
  90.3 hours (3.76 days) after the keyframe of the modelled peak.

**What the pass could see:** water still standing on open ground on the morning
of 16 September, where the ground was not already wet on 3 September.

**What it could not see:**

- the days of the gap, in which the replay's keyframes place the rise and the
  modelled peak;
- water that had already drained by 16 September;
- water under roofs or trees, which does not darken a C-band image;
- ground that was wet on both dates, which shows no change;
- any day but one. A pair of images gives one difference.

The pass times say when the radar looked. They do not say what the water did.

## 2. Why a single threshold on backscatter change abstains or fails here

A change threshold splits the cells of a window into "changed" and "not
changed" at one value. That works when the histogram of the change has two
humps: one for dry land and one for new water. Otsu's method finds the split,
and the **between-class variance fraction** says how much of the histogram's
spread the split explains.

**The gate.** The retired M2 method accepted a window only when that fraction
was at least 0.72.

**What one normal population gives.** A single normal (bell-shaped) population,
split at its mean, gives 2/pi = 0.637. That is the plan's figure. The M2 kernel
clips the values at their 1st and 99th percentiles first, which raises the
figure to 0.649. Through the unchanged kernel, 600 simulated windows of pure
noise scored between 0.635 and 0.662, and none passed. So a window that holds
one normal population does not pass the gate, whatever the land looks like.

**That holds for a normal population only.** A single flat-topped (uniform)
population gives 3/4 = 0.750 in theory, above the gate. Through the kernel,
600 of 600 simulated windows of one flat-topped population were accepted, with
fractions between 0.739 and 0.762. So the gate is a test of the shape of the
histogram. A window that passes it is not shown to hold two populations.

**What it takes to pass.** With two normal populations of equal spread, the
kernel accepts a window only when they lie far apart:

| Share of the window in the second population | Separation needed, in standard deviations |
|---:|---:|
| 50% | 2.6 |
| 30% | 3.0 |
| 20% | 3.7 (every simulated window accepted from 3.8) |
| 10% | 5.3 (every simulated window accepted from 5.4) |

A flood that fills a tenth of a window must therefore stand more than five
standard deviations away from the land around it. No window at Mae Sai showed a
second population of that kind: see the next table.

**What the windows scored.**

| Run | Windows | Accepted | Fraction, smallest / median / largest | Reason for every decline |
|---|---:|---:|---|---|
| M2 at Mae Sai, pilot grid | 81 | 0 | 0.598 / 0.639 / 0.651 | `unimodal_or_unstable_histogram` |
| M2 rule on GEOID-Flood, 29 tiles | 1,421 | 0 | 0.532 / 0.614 / 0.712 | `unimodal_or_unstable_histogram` |

At Mae Sai every one of the 81 windows passed the kernel's other two tests and
failed the gate alone. One window reached 0.65. The windows scored at or below
what one normal population scores. On GEOID-Flood, an event with a mapped flood, three windows
reached 0.70 and one reached 0.71. So the gate declines even where a flood map
exists: the failure is in the rule, not only in the Mae Sai pass.

**Abstain or fail.** A histogram without two clear humps gives two outcomes,
depending on whether a method has a quality gate.

- With a gate, the method declines. M2 declined every window. The frozen M1-v2
  has a gate of another kind and declined six of the nine tiles of the Mae Sai
  frame, 77.3% of its cells (`MAE_SAI_RADAR_CANDIDATES_RESULT.md`). This page
  measured nothing about M1-v2.
- Without a gate, Otsu still returns a split, and on a one-humped histogram the
  split falls near the middle. M1-literal put its threshold between -1.9 and
  +0.1 dB in the nine tiles and flagged 114.50 km2, 37.5% of the frame (same
  document). That is not a flood extent.

M2, M1-literal and M1-v2 do not read the same histogram: they differ in
radiometry, polarisation, filter and tiles. Only the M2 windows were examined
here.

A declined window has no answer. It is not a dry window.

## 3. The three figures against the season envelope

All three carry the label **vs a season envelope, not an event map**. The
envelope holds every area mapped as water at some time between 1 August and
October 2024, with no date per patch. It is not a reference, and these figures
are not a validation.

### 3.1 The pilot grid

| | km2 |
|---|---:|
| Season envelope inside AOI-01 | 15.337 |
| Of that, inside the M2 pilot grid | 3.111 |
| Of that, outside the M2 pilot grid | 12.225 |

The pilot grid leaves out **79.7%** of the envelope inside AOI-01 and holds
42.3% of AOI-01 (104.73 km2). The plan states "80%".

*Shows:* the M2 run looked at a part of AOI-01 that holds a fifth of the season
envelope. *Does not show:* how much of the September flood the grid left out,
or that a larger grid would have given an answer. M2 declined every window it
had.

### 3.2 Darkening of VH

The feature is VH before minus VH after, in dB, on 20 m cells, each date
smoothed with a mean over a window of cells. The figure is the rank statistic
(area under the ROC curve): the probability that a cell inside the envelope
darkened more than a cell outside it. 0.5 is no separation.

Three choices sit behind any one value, and no signed file makes them (open
points A1-OP2, A1-OP3 and A1-OP10):

- **the smoothing window.** The exploratory run used 5 by 5 cells;
- **the cells.** All cells of AOI-01 on the Thai side: 212,158 cells, 38,350 of
  them inside the envelope (18.1%). Or only the cells with a slope under 5
  degrees, the limit plan row A2 gives the UN-SPIDER practice: 155,578 cells,
  37,363 of them inside the envelope (24.0%);
- **the geocoding** of the radar layers.

**With the 5 by 5 window.**

| Geocoding of the radar layers | Cells | JRC surface water left out | WorldCover class 80 left out | Nothing left out | Median darkening inside / outside, dB |
|---|---|---:|---:|---:|---|
| Run of record (control-point warp) | all | **0.421** | 0.421 | 0.421 | -0.44 / -0.17 |
| Run of record | slope under 5 degrees | 0.445 | 0.445 | 0.445 | -0.44 / -0.25 |
| Sensitivity run (DEM height per cell) | all | 0.377 | 0.377 | 0.377 | -0.62 / -0.14 |
| Sensitivity run | slope under 5 degrees | 0.386 | 0.385 | 0.386 | -0.64 / -0.19 |

The medians are for the reading with JRC water left out. The first row follows
the definition of the exploratory run and gives 0.421149. The plan states
0.421: reproduced. The medians are negative: cells inside the envelope were
brighter on 15 September than on 3 September, by 0.44 dB against 0.17 dB
outside. Read the other way, a cell inside the envelope brightened more than a
cell outside it in 57.9% of pairs (62.3% in the sensitivity run).

**By smoothing window** (JRC surface water left out).

| Window, in 20 m cells | Run of record, all cells | Run of record, slope under 5 degrees | Sensitivity run, all cells | Sensitivity run, slope under 5 degrees |
|---:|---:|---:|---:|---:|
| 1 (no smoothing) | 0.467 | 0.478 | 0.445 | 0.451 |
| 3 | 0.442 | 0.460 | 0.405 | 0.412 |
| 5 (the exploratory run) | 0.421 | 0.445 | 0.377 | 0.386 |
| 9 | 0.386 | 0.419 | 0.338 | 0.350 |
| 15 | 0.349 | 0.391 | 0.300 | 0.317 |
| 25 | 0.299 | 0.352 | 0.254 | 0.282 |

The value falls at every step as the window grows, in all four columns. "0.421"
is therefore the value of one window, not a property of the pass. With no
smoothing the value is near one half (0.467). With a 25-cell window (500 m) the
same change, read as brightening, gives 0.701 and 0.746 on all cells.

*Shows:* at this pass, darkening alone does not tell the season envelope from
the rest of AOI-01, under any window, set of cells or geocoding tried. Taken
over all thresholds, a threshold on darkening selects a smaller share of the
cells inside the envelope than of the cells outside it. *Does not show:* that
the radar saw no water, why the envelope cells brightened (wet soil and debris
after the water has gone are one possible cause; the run did not test it), or
how correct any method is. The envelope also holds August and October water. A
large window also mixes each cell with its neighbours, so a value far from one
half at 25 cells says that broad areas differ, not single cells.

The geocoding matters. The radar layers of the run of record lie about 680 m
from where they belong (open point A4-OP1), so that row compares displaced radar
cells with the envelope. The sensitivity run removes most of the displacement,
and the value moves further from one half, not closer. Which layers case O1
uses is for the owners; no row is named the figure of record (A1-OP3).

### 3.3 Terrain

Two features of the Copernicus GLO-30 surface model on the same cells. No radar
image is read.

| Feature | Cells | JRC surface water left out | WorldCover class 80 left out | Nothing left out | Median inside / outside the envelope |
|---|---|---:|---:|---:|---|
| Low elevation | all | 0.616 | 0.617 | 0.616 | 386.8 m / 391.5 m |
| Low elevation | slope under 5 degrees | 0.445 | 0.446 | 0.445 | 386.6 m / 384.7 m |
| Low slope | all | 0.680 | 0.680 | 0.680 | 0.62 / 1.64 degrees |
| Low slope | slope under 5 degrees | 0.544 | 0.544 | 0.545 | 0.60 / 0.75 degrees |

The medians are for the reading with JRC water left out. The plan lists this
figure as "to compute" and names no feature and no set of cells (A1-OP1,
A1-OP10). All four rows are given and none is the figure of record. HAND, the
height above the nearest drainage, was not computed: no HAND raster and no
drainage rule is in the signed files or on disk.

This is the first computation from cleared files and the first recorded value.
It is not the first time the figure was seen: the exploratory script of the
plan session ranked the same two features against the same layer and printed
their values on the line that gave 0.421. Those values are in no committed
file. The two features were taken from that script (section 9).

*Shows:* on all cells, the season envelope lies on lower and flatter ground
than the rest of AOI-01. Most of that is hill against plain: 97.4% of the
envelope cells have a slope under 5 degrees, against 68.0% of the other cells.
On the cells under 5 degrees the picture changes. Low elevation gives 0.445,
below one half: there the envelope cells are slightly higher (386.6 m against
384.7 m). Low slope gives 0.544. Elevation is absolute height, not height above
the river, so low elevation can separate plain from hill as much as wet from
dry. *Does not show:* a flood, or that terrain separates the envelope better
than the radar change does. On the cells under 5 degrees the radar change of
this pass, read as brightening with the 5 by 5 window, gives 0.555 and 0.614;
low slope gives 0.544 and low elevation 0.445. Which is larger depends on the
window, the cells and the geocoding, so this page ranks neither above the
other. Terrain is the same before, during and after an event. GLO-30 is a
surface model: roofs and tree tops read as ground.

No interval is given for 3.2 or 3.3. Neighbouring cells are not independent, so
an interval from the cell count would be far too narrow.

## 4. Every number, traced

Each script is under `scripts/diagnostics/`, each figures file under
`outputs/a1_diagnosis/` and each receipt under `outputs/planning_v1/`. A receipt
holds the inputs with SHA-256, the parameters, both protocol hashes, the run
times, the SHA-256 of the figures file, the SHA-256 of the script and of the
shared modules, the library versions and every earlier run.

| Number | What it is | Plan row A1 says | Script | Figures file | Receipt |
|---|---|---|---|---|---|
| 0.637 | One normal population, theory (2/pi = 0.636620) | "a unimodal Gaussian gives 0.637 < 0.72": reproduced | `bvf_unimodal_gaussian.py` | `bvf_unimodal_gaussian.json` | `a1_diagnosis_bvf_unimodal_gaussian.json` |
| 0.649; 0.635 to 0.662; 2.6, 3.0, 3.7, 3.8, 5.3, 5.4; 0.750, 600 of 600, 0.739 to 0.762 | The same through the M2 kernel: theory with clipping (0.649065), 600 simulated windows, separation needed; one flat-topped population | not stated | same | same | same |
| 81 of 81; 0.598, 0.639, 0.651; one window at 0.65 | M2 windows at Mae Sai | protocol v1a, EK-07: "81 of 81 ... 0.598-0.651": reproduced | `m2_windows_mae_sai.py` | `m2_windows_mae_sai.json` | `a1_diagnosis_m2_windows_mae_sai.json` |
| 0 of 1,421; 0.532, 0.614, 0.712; three and one | M2 rule on GEOID-Flood | "GEOID 0/1,421 windows": reproduced | `m2_windows_geoid.py` | `m2_windows_geoid.json` | `a1_diagnosis_m2_windows_geoid.json` |
| four passes and their times; 227.7 h, 9.49 days; 95.7 h, 132.0 h, 5.50 days, 90.3 h, 3.76 days | Sentinel-1 passes, the gap, and the hours to two replay keyframes | "no pass between 6 Sep 11:31 and 15 Sep 23:16 UTC": reproduced | `sentinel1_pass_gap.py` | `sentinel1_pass_gap.json` | `a1_diagnosis_sentinel1_pass_gap.json` |
| 15.337, 3.111, 12.225 km2; 79.7%; 42.3%; 104.73 km2 | Pilot grid against the season envelope | "pilot grid misses 80% of the 4009 envelope inside AOI-01": reproduced | `pilot_grid_vs_envelope.py` | `pilot_grid_vs_envelope.json` | `a1_diagnosis_pilot_grid_vs_envelope.json` |
| 0.421 (0.421149), 0.377 and the other values of the two tables of 3.2; 57.9%, 62.3%; 0.701, 0.746; medians; cell counts; 18.1%, 24.0% | Darkening of VH against the season envelope | "darkening-dVH AUC vs the 4009 envelope 0.421": reproduced | `darkening_auc_vs_envelope.py` | `darkening_auc_vs_envelope.json` | `a1_diagnosis_darkening_auc_vs_envelope.json` |
| 0.616, 0.617, 0.680, 0.445, 0.446, 0.544, 0.545; medians; 97.4%, 68.0% | Terrain against the season envelope | "terrain AUC vs 4009 (to compute)": first computation from cleared files, first recorded value | `terrain_auc_vs_envelope.py` | `terrain_auc_vs_envelope.json` | `a1_diagnosis_terrain_auc_vs_envelope.json` |

Numbers quoted from other tasks, not computed here:

| Number | Source |
|---|---|
| M1-literal threshold -1.9 to +0.1 dB; 114.50 km2, 37.5% of the frame; M1-v2 with no answer for six of nine tiles, 77.3%; one tile with no bimodal block and five with 33, 28, 1, 3 and 6 blocks kept; 9.42 km2 of the UN-SPIDER practice; displacement of about 680 m | `outputs/planning_v1/radar_o1_mae_sai_v1.json`, described in `MAE_SAI_RADAR_CANDIDATES_RESULT.md` |
| Replay keyframes 10 Sep 18:15 ICT and 12 Sep 12:00 ICT | `docs/demo/replay_numbers.md`, keys `stage.onset_knot` and `stage.peak`; read by the pass-gap script at run time and bound by SHA-256 in its receipt |
| RADARSAT-2 analysis of 10 Sep 18:15; ALOS-2 acquisitions of 14 and 15 Sep | `docs/demo/replay_numbers.md`, key `cal.gistda`; planning protocol v1a, case O4 |
| GEOID result of M1-v2, 0.411 (section 7) | `GEOID_M1_BENCHMARK_V2_RESULT.md`; decision log R15 |

`tests/test_a1_diagnosis_outputs.py` checks the numbers of the In brief list
and of sections 1 to 3 against the figures files, the numbers quoted from tasks
A2 and A4 against `radar_o1_mae_sai_v1.json`, and the run times of section 10
against the receipts. It also checks that the script and the shared modules on
disk are the ones each receipt names. It does not check a number that appears
only in a sentence of sections 6 to 12.

## 5. Input files

`<external_data_workspace>` is the external data root, given by `--external-data`
or `FLOODGUARD_EXTERNAL_DATA`. Nothing under it is in Git.

| File | SHA-256 | Read for |
|---|---|---|
| `<external_data_workspace>/unosat/unosat_4009_chiang_rai_2024/FL20240912THA_GDB.zip` (layer `CHIANGRAI_20240801_20241012_AccumulatedFlood`) | `1fe3243c2bc986d4111bb3d82aff292abccf7fb1bb1dd722747e994618b66e85` | pilot grid, darkening, terrain |
| `docs/proposal_execution/rights_basis_4009_v1.json` | `531ab40beb2b3e80a02d6de0d4d7d791b299176af0b192bfe105ca23c7e50cb3` | pilot grid, darkening, terrain |
| `resources/aoi/aoi-01_mae_sai_core.geojson` | `d837a1b058c86739150bb6b844f9dcfdedf32feb83be99194e855430d4a613c2` | pilot grid, darkening, terrain |
| `<external_data_workspace>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip` (layer `tha_admin3`) | `09e62345481bb80030ff6779e074bfb2c16629b70ae1e373ebd31945f1c6e0d8` | darkening, terrain |
| `<external_data_workspace>/open_context/jrc_global_surface_water/seasonality_90E_30Nv1_4_2021.tif` | `4d934d022e6631e487b6f048ed5d740c9e828ba613779ecf54fa3b57fd5f9383` | darkening, terrain |
| `<external_data_workspace>/open_context/jrc_global_surface_water/occurrence_90E_30Nv1_4_2021.tif` | `885420118995cd2e1dfdfdc9aa4c029e41ca27a3efa79a7fcc5b94f7554b0309` | darkening, terrain |
| `<external_data_workspace>/open_context/esa_worldcover/ESA_WorldCover_10m_2021_v200_N18E099_Map.tif` | `e02c02859074bc0ff0cf1bed21b074520be46c4385e0071c327c173e0ec9f4eb` | darkening, terrain |
| `outputs/planning_v1/radar_o1_mae_sai_v1_receipt.json` | `62beed7f4c62d19701bc72626180aa2557d4a6f529a8b46429e94c471664b5b2` | darkening, terrain (the grid and the context files) |
| `outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json` | `5f5e1795bb2e7968fc40f1a982eee11b047240f2092fd6527f5ea3c2c6769401` | darkening |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1/sigma0_pre_20240903.tif` | `a124747c3a17416328fc1b6c84f99c8359abe9c022d652b11839e51e5e9c37c3` | darkening |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1/sigma0_post_20240915.tif` | `1d196f6759a9c1b57b52b3a73c5138536cef8a7aad09e98d7fc15a2066709d93` | darkening |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1_height_aware_sensitivity/sigma0_pre_20240903.tif` | `416a3e308ac84e1e31dce1a46a182c874f1d316e3d6d7d0d8554de2203809a17` | darkening |
| `<external_data_workspace>/proposal_execution/planning_v1/o1_mae_sai/radar_o1_v1_height_aware_sensitivity/sigma0_post_20240915.tif` | `942a7e155aed38cff04f0c34265ced975f6829cf739785119550e3c5745dc957` | darkening |
| `<external_data_workspace>/open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif` | `8965f85514b577b4b606c658412bfe3d713c0abf478d237539af309d8edb3757` | terrain; darkening (the slope that gives the cells under 5 degrees) |
| `<external_data_workspace>/proposal_execution/mae_sai_2024_gamma0_otsu_v1_20260923r3/candidate_receipt.json` | `7814cfb5f936952a581ab72c40bde7ab14f638715834f39974dddfa81c5394fe` | M2 windows at Mae Sai, pilot grid |
| `outputs/sar_m2_abstention_diagnostic_v1.json` | `911c5660eb18e2a0616fba02fcb2f6b9c4a0e43d93f3228c1e065ca8618f6126` | M2 windows at Mae Sai, pilot grid |
| `<external_data_workspace>/geoid_flood/metadata/SHA256SUMS` | `f6af34dbd56743d3f6faf6807207763fc51460167d62b1c2005bfa3df44f62f1` | GEOID windows |
| GEOID-Flood sample, EMSR712-3: 116 files, 572,940,276 bytes, each checked against the published sums (inventory hash) | `d36901396cbae4d8512f9b2a1575ec9365ac9b65edb076a69807aa8a8d7cfa57` | GEOID windows (58 radar tiles opened; labels not opened) |
| `outputs/geoid_s1grd_sigma0_benchmark_summary_v1.json` | `b5b46521d568b9aab43cbd3f2f811f6da28c71764a09781b773e7394607b98ff` | GEOID windows |
| `docs/proposal_execution/automated_track/geoid_sar_benchmark_protocol_v1.json` | `26c55475fa7e5fb9bffa1f27eef6637a4c340a43cce1f99e6e2e8085e512667f` | GEOID windows |
| `src/floodguard/geoid_radar_benchmark.py` | `1407a0e196c5ed5e6e796e2f802d218afc7e120465d3781ca8c5c40d52e20b83` | GEOID windows |
| `scripts/benchmark_geoid_flood_sar.py` | `11f17264da8914998f7e0aebd27f1eed69367752f03177a0502202e8fb4e5291` | GEOID windows (the source check) |
| `outputs/cdse_mae_sai_2024_metadata.csv` | `335b8f19e05c8436c2f48acf4e9d9de6905b7156088ecd5c335c0712bbf7fa6e` | passes |
| `docs/demo/replay_numbers.md` (rows `stage.onset_knot` and `stage.peak`) | `2b556e0474f7795b6826df459924e5013b59c5fd200e734aaf16657dfb07c1a1` | passes (the two replay keyframes) |
| `src/floodguard/label_factory/sentinel1_processing.py` | `3977d4112cde8e71aaf444518b2e635c3e8810a480728131c67aaf1c0443a590` | one population (the M2 kernel) |

Both protocol files are named by SHA-256 in every receipt:
v1a `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954`,
v1b `6ed7d7e93c86df6ed0cf30b3a3383582632b5efbb678b377ca2ee1990fb393e7`.

`docs/demo/replay_numbers.md` is written by the replay lane. If the replay is
baked again, that file changes and the pass-gap figure needs a new run; until
then its test fails.

## 6. Limits

- **One pair of images, twelve days apart, the second several days after the
  keyframe the replay sets for the modelled peak.** That keyframe is
  illustrative: no gauge record gives the time of the peak. Nothing here
  describes the peak or any other day.
- **Sentinel-1 only.** Other radar satellites looked in the gap (section 1).
  None of their data is cleared for this lane.
- **The envelope is a season product.** It holds water of August and October
  as well, it was not checked in the field, and it is not a reference. A cell
  can be inside it and dry at the pass, or wet at the pass and outside it.
- **A rank statistic is not a score of a method.** It says how one feature
  orders the cells against one layer. It applies no threshold and maps nothing.
- **The smoothing window and the set of cells are free choices.** The darkening
  value runs from 0.254 to 0.478 over the windows, cells and geocodings tried.
  The 5 by 5 window on all cells is the definition of the exploratory run,
  which is why the plan's 0.421 is reproduced under it and under no other.
- **On all cells, terrain mostly tells hill from plain.** AOI-01 holds both.
- **No interval.** The cells are not independent.
- **Geocoding.** The radar layers of the run of record are displaced by about
  680 m, and the two dates lie about 9 m apart. The sensitivity run uses a
  mapping the plan does not name.
- **Radiometry.** Sigma0 from the SAFE calibration table; thermal noise is not
  removed; no terrain flattening. The M2 windows used terrain-flattened gamma0.
- **The simulation is a model.** Real change values are not normal, and a real
  window mixes land covers. The measured windows are the evidence; the
  simulation explains them. The result "one population does not pass" holds for
  a normal population; a flat-topped one passes.
- **The pass list is a snapshot** of one catalogue, one point and one product
  type, taken on 8 July 2026. The catalogue was not queried again.
- **The replay keyframes are illustrative.** They are not gauge readings.
- **GEOID-Flood is one foreign event** (northern Germany, winter 2023-24), with
  images almost four months apart.
- **Library versions.** A rank statistic rests on a bilinear warp of the
  surface model and on nearest-cell water masks. Under another version of GDAL,
  PROJ, GEOS or numpy a value can move in its last decimals. Each receipt
  records the versions; `--verify` reports them.

## 7. What this means for the radar methods of tasks A2 to A4

The tasks are run and reported in `MAE_SAI_RADAR_CANDIDATES_RESULT.md`. This
diagnosis is consistent with that result and does not change it.

- **A2, the UN-SPIDER practice.** It has a fixed quotient of 1.25 and no way to
  decline, so it answers every cell: 9.42 km2 of candidate area, most of it
  cropland. Its rule is a darkening rule. Section 3.2 says darkening does not
  point at the season envelope at this pass, so the candidate area should be
  read as "cells that became darker", as the result page says, and not as a
  flood extent. The candidates were not compared with product 4009 there
  (guardrail GR4) and are not compared here.
- **A4, M1-literal.** It is the "fail" of section 2: Otsu without a gate on a
  one-humped histogram. Protocol v1a already declares it unable to meet the T2
  skill bar.
- **A4, M1-v2.** It keeps a gate of another kind (blocks with two populations,
  then an accepted threshold) and declined six of nine tiles, so the T2 skill
  bar is recorded as not met at Mae Sai. The diagnosis is consistent with those
  declines and did not examine them: no script here measured anything about
  M1-v2. The A2/A4 result gives two kinds of decline. One tile had no bimodal
  block. Five tiles kept bimodal blocks (33, 28, 1, 3 and 6) and found no
  accepted threshold, which is a different mechanism from the M2 gate analysed
  in section 2. Nothing here is a reason to loosen the frozen rule.
- **A3, the GEOID benchmark.** The M2 rule declined every window of a labelled
  event. The plan retires M2 as a failed first version and does not lower its
  gate (plan guardrail G24). For the later M1-v2 result on GEOID, decision R15 applies each time it is quoted: the
  result (0.411) is not distinguishable from 0.40 on 14 tiles, 67.9% of the test
  cells had no answer, and it measures agreement with a same-pass CEMS map, not
  an independent check.
- **The frame.** The pilot grid held a fifth of the envelope inside AOI-01.
  Task A4 runs on the eight-tambon union instead, which removes that limit and
  not the others.
- **The HAND and slope mask.** Protocol v1a announces one for M1-v2 on Mae Sai
  and gives no limit (A4-OP2). Section 3.3 gives no limit either. It shows that
  on all cells slope tells hill from plain, and that inside the cells under 5
  degrees slope gives 0.544. That is a reason to leave hills out of a
  comparison. It is not evidence that a slope or HAND rule maps a flood.
- **Geocoding.** A4-OP1 is still open. The darkening figure is given under both
  geocodings and moves from 0.421 to 0.377 at the 5 by 5 window.
- **Disclosure.** The M1-v2 design and the T2 conditions were shaped by what
  failed at Mae Sai (protocol v1a, EK-07), so v2 is not an independent method.
  This page is the cleared record of what was seen, with the limits of section
  9.

## 8. Open points for the owners

Nothing below was decided by the code. Each is in `open_points` of the figures
files and receipts it concerns.

| Id | Point | What was done |
|---|---|---|
| A1-OP1 | The plan says "terrain AUC vs 4009 (to compute)" and names no feature | Low elevation and low slope were measured. They are the two terrain features of the exploratory script, which printed their values and recorded none. HAND was not computed. Neither is named the terrain figure of the plan |
| A1-OP2 | The plan gives 0.421 and no definition; the exploratory script was never committed | The definition was rebuilt from cleared files. Two things differ: calibrated sigma0 in place of uncalibrated amplitudes, and the Thai side from the COD-AB boundaries in place of the product's analysis extent, which is held at the local level and was not read. The figure is the same to three decimals. The 5 by 5 window is that script's; no signed file names a window, so six windows are given and none is the window of record |
| A1-OP3 | Which geocoding a figure against a mapped layer uses (follows A4-OP1) | Both are given; neither is the figure of record |
| A1-OP4 | Which permanent water a diagnosis leaves out: protocol v1a names WorldCover class 80 for the flood-likelihood component and says nothing of a diagnosis | Three readings are given; they differ in the third decimal at most |
| A1-OP5 | No signed rights record covers the Sentinel-1 data (E1-OP2, A4-OP5); plan row A1 lists figures made from them as team-owned or cleared | Statistics for the whole area are committed with the Copernicus attribution, as the A2/A4 tables are. No radar layer is written |
| A1-OP6 | The product 4009 rights record lists its uses; a diagnosis comparison is not among them, and the record does not cover use as a qualified reference | The layer is a comparison layer only, with licence, credit, change notice and label on every figure and every receipt. No model was fitted to it |
| A1-OP7 | Guardrail GR9 says "a recorded grant receipt" and gives neither its form nor its place | The guard reads the rights registry; no grant exists. Legacy code is listed in a baseline (section 11) |
| A1-OP8 | How far "no number" of guardrail GR9 can be checked | The guard checks the files of this task. It cannot tell which number elsewhere came from the two products |
| A1-OP9 | The plan says "scripts moved to scripts/diagnostics/"; the exploratory scripts were never committed, and four older committed scripts (`scripts/diagnose_*.py`) are named by documents and tests | New scripts were written. No committed script was moved |
| A1-OP10 | On which cells a rank statistic against the envelope is taken: the plan names no domain | Each statistic is given on all cells of AOI-01 on the Thai side and on the cells with a slope under 5 degrees (the limit of plan row A2). Neither is the domain of record |
| A1-OP11 | How far the reading of a product path can be checked, and when the check runs: guardrail GR9 asks for a pre-commit test and names no mechanism | The guard reads code text and runs in the test suite and as a command. No Git hook is installed. Section 11 lists what it does not see |

Open points of other tasks that this page rests on: A4-OP1 (geocoding), A4-OP2
(HAND and slope mask), A4-OP5 and E1-OP2 (Sentinel-1 rights), E1-OP1 (what the
local level allows in Git).

## 9. Not reproduced, not recorded, and seen before

- **Every number of plan row A1 was reproduced** from files on this machine, and
  the one marked "to compute" was computed from cleared files.
- **Seen before, and not recorded: the other features of the exploratory
  script.** The exploratory script that gave 0.421 ranked seven features against
  the same layer and printed the values on one line: the darkening of VH, the
  same change read as brightening, the absolute change of VH and of VV, the
  negated VH after the event, the negated height and the negated slope. Only
  0.421 was carried into the plan; the other six values are in no committed
  file. So the two terrain features of section 3.3 and the brightening reading
  of section 3.2 were not free choices made here: they repeat features of that
  script. The absolute changes and the VH after the event are not computed
  here, because plan row A1 does not list them. The script also looked at the
  cells with a slope under 5 degrees.
- **The catalogue query was not repeated.** The pass list comes from the
  committed snapshot. A new query needs a network request, which this lane does
  not make.
- **Not computed: the "lift 0.98" of the legacy ramp** that disclosure item
  EK-07 of protocol v1a mentions. Plan row A1 does not list it.
- **Not recorded: figures against the AIT or MBRSC products.** They were seen in
  the exploratory phase (EK-07). No grant exists, so they are not computed, not
  quoted and not in any file of this task.
- **Not read: the analysis extent of product 4009.** It is held at the local
  level. The Thai side of AOI-01 is taken from the public COD-AB boundaries.

## 10. Every run, reported

All on 4 October 2026 (UTC; 5 October in local time), with both protocols in
force. The start and finish of a run are the times its receipt records
(`timestamps`). For a run that was superseded they come from `run_history` of
the receipt that replaced it. A start time marked * is not in a committed
file: it was read from the copy of the superseded receipt kept outside Git.

| Started | Finished | Run | What it wrote |
|---|---|---|---|
| about 18:00 | about 20:25 | Reads while the scripts were written: raster headers, the M2 receipt and its grid, AOI-01, the two radar receipts. The statistics were tried on invented numbers. No cell value was read | Nothing |
| 20:27:35Z * | 20:27:47Z | One population, first run | Figures and receipt; superseded at 20:35 |
| 20:28:03Z * | 20:28:03Z | Passes, first run | Figures and receipt; superseded at 20:35 |
| 20:28:05Z | 20:28:05Z | M2 windows at Mae Sai, first run | Figures and receipt; superseded at 22:14 |
| 20:28:12Z | 20:28:24Z | GEOID windows, first run | Figures and receipt; superseded at 22:15 |
| 20:28:32Z | 20:28:45Z | Pilot grid, first run | Figures and receipt; superseded at 22:15 |
| 20:28:53Z * | 20:29:11Z | Darkening, first run | Figures and receipt; superseded at 20:36 |
| 20:29:26Z * | 20:29:40Z | Terrain, first run | Figures and receipt; superseded at 20:36 |
| 20:35:24Z | 20:35:41Z | One population, second run: the shared module was reworded after the first run | Figures and receipt; same figures; superseded at 22:11 |
| 20:35:45Z | 20:35:45Z | Passes, second run: two replay keyframes added for context; the snapshot log is named and no longer bound by hash | Figures and receipt; the pass list is the same; superseded at 22:11 |
| 20:35:49Z | 20:36:06Z | Darkening, second run: each reading gained its complement and a note | Figures and receipt; every value of the first run is the same; superseded at 22:15 |
| 20:36:08Z | 20:36:23Z | Terrain, second run: two sentences reworded | Figures and receipt; same figures; superseded at 22:16 |
| about 20:41:46 | about 20:43:08 | `--verify` of all seven figures: each computed again from its inputs. No receipt records these times | Nothing. Every figure, input and parameter was the one in the receipt |
| about 20:50:03 | about 20:51:13 | The same check once more for six figures, through the test suite with the external data root set | Nothing. The same result |
| about 21:05 | about 21:38 | Runs of the review, as the review reports them: `--verify` of all seven figures; the same seven with scipy, scikit-learn, networkx, Pillow and requests blocked; a recomputation outside `floodguard` of the envelope figures, of the window counts and of the one-population theory, with the same result; trial values for other windows, for the cells under 5 degrees, for a flat-topped population and for the guard on invented files | Nothing in the worktree. Its trial values are the reason for the runs below, which reproduce each of them |
| about 21:40 | about 22:10 | Reads after the review: the committed figures files and receipts; the eight superseded copies outside Git, for their times and SHA-256; the text of five exploratory scripts. None was run. The pass list and the one-population simulation were computed once without writing, to try the changed scripts | Nothing |
| 22:11:37Z | 22:11:49Z | One population, third run: a flat-topped population measured; the receipt gains the library versions | Figures and receipt; superseded at 22:14 |
| 22:11:50Z | 22:11:50Z | Passes, third run: the keyframes read from `docs/demo/replay_numbers.md` | Figures and receipt; superseded at 22:14 |
| 22:14:30Z | 22:14:46Z | One population, fourth run: the shared module named by the third run had dated the reads of the review without a time zone | The files as they are here; same figures as the third run; the figures of the first two runs are unchanged |
| 22:14:47Z | 22:14:47Z | Passes, fourth run: the third run said the other radar acquisitions lie inside the gap; two of them are known by date only | The files as they are here; the pass list, the gaps and the keyframe hours are those of the second run |
| 22:14:49Z | 22:14:49Z | M2 windows at Mae Sai, second run: the shared modules changed | The files as they are here; same figures |
| 22:14:51Z | 22:15:03Z | GEOID windows, second run: the shared modules changed | The files as they are here; same figures |
| 22:15:08Z | 22:15:27Z | Pilot grid, second run: the receipt gains the licence block and the label | The files as they are here; same figures |
| 22:15:29Z | 22:15:47Z | Darkening, third run: six windows and the cells under 5 degrees | The files as they are here; every value of the second run is in the third, unchanged |
| 22:15:49Z | 22:16:05Z | Terrain, third run: the cells under 5 degrees; what the exploratory script had computed | The files as they are here; every value of the second run is in the third, unchanged |
| about 22:16:23 | about 22:17:48 | `--verify` of all seven figures. No receipt records these times | Nothing. Every figure, input, parameter and code hash was the one in the receipt; the library versions were the same |

Seven superseded runs are in commit `60a1aa6`: the first runs of the two window
figures and of the pilot grid, and the second runs of the other four. The first
runs of those four (20:27 to 20:29) and the third runs of one population and of
the passes (22:11) were never committed. The SHA-256 of every superseded
receipt and figures file is in `run_history` of the receipt that replaced it,
and copies of all of them are kept outside Git under
`<external_data_workspace>/proposal_execution/planning_v1/a1_diagnosis/superseded_runs/`.
The runs after these are listed in `outputs/planning_v1/README.md`.

The superseding runs of 22:14 to 22:16 were made from commit `b26e5d2`, which
holds the script and the shared modules each receipt names by SHA-256.

## 11. The guard for the two ungranted products

Protocol v1a, guardrail GR9, asks for a test that fails when a committed script
reads the paths of two flood products that no provider has granted, and for no
number of either in committed code. It was "required with plan task A1" and is
now built:

- `src/floodguard/ait_mbrsc_guard.py` holds the checks,
  `tests/test_ait_mbrsc_guard.py` runs them in the suite, and
  `scripts/check_ait_mbrsc_guard.py` runs them as a command.
- **Paths.** A code file fails unless a grant is recorded when it names either
  product: by its product identifier or file name; by its folder in the
  external data workspace; by the bare product word as an identifier or in a
  short string; or by importing a legacy module that names a product file or
  folder.
- **Legacy code.** Some code files named a product before the guard existed:
  the inspection, registration and gate code of the earlier reference work,
  which the plan keeps unchanged, with its tests and the web files that name the
  blocked record. 29 files are listed in
  `docs/proposal_execution/ait_mbrsc_guard_baseline_v2.json` with the SHA-256
  of the naming lines, so a new or changed line fails. A legacy Python file
  under `scripts/` or `src/` is also bound by the set of its functions and
  classes, so it fails when it gains one. The list is not a grant.
- **Numbers.** In the files of this task no figure may stand beside either
  product name: not in the same line or sentence, not under a JSON key that
  names a product or beside a JSON label that does, and not in a table column
  whose header names one. A year counts as a figure. The files are this page,
  the scripts, the figures files, the receipts, the three modules, their tests
  and the A1 section of `outputs/planning_v1/README.md`.
- **A grant** is a rights record of that source in the rights registry,
  confirmed by the owners and signed by a human. None exists today.

**What the guard does not see.** It is a net, not a proof.

- A path that a script reads from a JSON or CSV manifest. Only code files are
  searched.
- A name that is split across strings or built at run time.
- New code inside an existing function of a legacy file, when no naming line
  changes.
- New code in a legacy test or web file that names no product. Those files are
  bound by their naming lines only, because other lanes add tests and
  components to them.
- The folder `reference_candidates` when it is passed as a plain argument and
  not joined into a path.
- Which number elsewhere in the repository came from the two products.
- A commit made without running the suite. The repository installs no Git
  hook: the check runs in the test suite, which CI runs, and as a command.

What a grant receipt is, what happens to the legacy code and how the check
should run are open points A1-OP7, A1-OP8 and A1-OP11.

## 12. Reproduce

The scripts need the `diagnostics` extra, which the default CI sync leaves out.

```text
uv sync --extra diagnostics --extra dev
python scripts/diagnostics/<script>.py --external-data <root> --verify
```

`--verify` computes a figure again and compares it with the committed run: the
figures, the inputs, the parameters and the SHA-256 of the code. It reports the
library versions and writes nothing. A new run needs `--replace --reason
"<why>"` and the external data root: it writes a new receipt that names the one
it supersedes, keeps a copy of the superseded files outside Git and rewrites
its register entry. Without the root a new run is refused. The scripts for one
population and for the passes read no external data, so their `--verify` needs
none.
