# GEOID radar benchmark for M1-literal and M1-v2 (plan task A3)

**Status: research benchmark.** Every score in this document is agreement
with a same-pass CEMS map, not independent accuracy. Nothing here is an
accepted observation or an official warning. No FPPS and no A-E class was
computed, and nothing was run on Mae Sai.

Source timestamp: Sentinel-1 pass of 3 January 2024, 05:34 UTC (post-event
image of activation EMSR712-3). Scored on 2 October 2026. Confidence: low
(one foreign event, a spatial split by tile, a reference drawn from the
input pass). Rachmania has not yet reviewed the tuning or this result.

Revised on 3 October 2026 after a review. The revision corrects wording and
adds checks computed from the committed counts. No score, no configuration
and no line of the frozen method code changed. See "Review corrections".

## Decisions for the owners

Read these before the numbers.

1. **The 14 held-out test tiles are used up for this configuration.** The
   held-out scores were computed on 2 October at 16:35 UTC, less than six
   minutes after the freeze was committed (16:30 UTC) and before the review
   that owner decision R11 attaches to the tuning ("for Rachmania to
   review").
   Rachmania's review can therefore do one of two things: accept the frozen
   M1-v2 with the limits written here, or open a new version. A new version
   has no unseen tile left in this sample. It would need held-out data that
   is not on disk, which means a download and a change to the scope freeze
   (decision D11).
2. **The choice she is asked to review rests on a thin margin and one
   amendment.** The frozen run leads the next three by 0.007 to 0.012 of
   development IoU (0.441 against 0.434, 0.429, 0.429). Amendment 1 was
   written after development scores had been seen, and it replaced the
   choice the first session would have frozen (run 29).
3. **How to read the GEOID condition of the T2 skill bar.** The point
   estimate is 0.411 against a minimum of 0.40, with 67.9% of the test cells
   left without an answer. It is not distinguishable from 0.40 on 14 tiles
   (see "The T2 skill bar"). Protocol v1a gives a minimum and no rule for
   uncertainty or for declined cells. The owners decide, in v1b, whether a
   point estimate counts as passing and whether declining needs a limit on
   this benchmark too. A rule written now is written after the score was
   seen and must say so.
4. **Record the outcome.** Rachmania's review result belongs in the decision
   log before M1-v2 is applied to Mae Sai (plan task A4).

Two smaller choices are listed under "Review corrections": whether to
correct one sentence inside a frozen code module, and whether to score a
second reading of M1-literal on the test tiles.

## Result in brief

"No answer" is the share of evaluable cells where the method gave no answer.
The strict IoU is always shown with it, because the strict reading scores a
declined tile like an answer of "no flood" (see "The T2 skill bar").

| Method | Tuning | Test IoU, strict (cells without an answer) | Test IoU, covered cells | Test coverage | Test tiles where the method declined |
| --- | --- | ---: | ---: | ---: | ---: |
| M1-literal (the proposal as written, with one added clause) | none | 0.159 (0.2% no answer) | 0.159 | 99.8% | 0 of 14 |
| M1-v2 (frozen configuration) | 15 development tiles | 0.411 (67.9% no answer) | 0.506 | 32.1% | 10 of 14 |
| M1-v2 with Otsu (comparator at the blocks chosen for M1-v2, not a candidate) | none of its own | 0.216 (1.7% no answer) | 0.216 | 98.3% | 1 of 14 |

- **M1-literal** flags about five times the mapped flood area. It finds most
  of the mapped flood (recall 0.84) and is wrong about most of what it flags
  (precision 0.16). Its rule is "delta-VH below the Otsu threshold and below
  zero". The clause "below zero" is the agent's addition to the proposal's
  words. The Otsu threshold is above zero on 23 of the 29 tiles, and there
  the Otsu threshold plays no part: the rule is "delta-VH below zero".
- **M1-v2** gives an answer on 4 of the 14 test tiles and declines on the
  other 10. Where it answers, 73% of what it flags is mapped flood. The 10
  declined tiles hold 22% of the mapped flood of the test split.
- The held-out test IoU of M1-v2 is 0.411 on the strict reading, with 67.9%
  of the test cells left without an answer, and 0.506 on the cells where it
  answered. Both point estimates are at or above the 0.40 named in the T2
  skill bar of protocol v1a. **The strict figure is not distinguishable from
  0.40 on 14 tiles:** it is 0.297 without tile 42 and 0.380 without tile 49,
  and a tile bootstrap gives a 95% range of 0.10 to 0.51 with 51% of the
  resamples at or above 0.40. This is one of four conditions and the only
  one that can be assessed here. See "The T2 skill bar" below.
- **Most of the gain over M1-literal comes from declining tiles, not from
  the threshold method.** On the four test tiles where M1-v2 answered, the
  three methods score 0.350 (M1-literal), 0.460 (Otsu comparator) and 0.506
  (M1-v2). The rest of the difference between 0.159 and 0.411 comes from
  the ten tiles M1-v2 declined: M1-literal has 1,755,423 false alarms there
  and the Otsu comparator 1,095,692, and a declined tile is charged none.
- **The Otsu comparator is shown at the configuration chosen for
  Kittler-Illingworth only.** In the declared grid, Otsu with 256-cell
  blocks on the mean of VV and VH scored 0.475 on the development tiles
  while declining 10 of 15 of them. That is higher than the frozen M1-v2
  (0.441). That Otsu run was never scored on the test tiles.
- The first tuning session exposed a defect in the threshold code. It was
  corrected on the development tiles, before the freeze, and the change is
  recorded as amendment 1. See "Tuning on the development tiles".

## Required statement

> v2 thresholds were tuned on GEOID development tiles and scored on held-out GEOID test tiles against a same-pass CEMS map (agreement, not independent accuracy). Design choices were informed by the Mae Sai diagnosis. Test tiles had been included in an earlier exploratory all-tile diagnostic (0.161 to 0.455), which is labelled exploratory.

Further disclosures:

- One foreign event (northern Germany, winter 2023-24). The split is
  spatial, by tile. Neighbouring tiles share the event, the two radar passes
  and the mapping team, so the test tiles are not independent of the
  development tiles.
- The earlier all-tile diagnostic saw the test tiles. Two things are meant.
  The exploratory single-date diagnostic of 25 September 2026 (IoU 0.161 to
  0.455, scratch scripts, results not retained) scored all 29 tiles. The
  committed M2 benchmark on this branch
  ([GEOID_SAR_BENCHMARK_V1_RESULT.md](GEOID_SAR_BENCHMARK_V1_RESULT.md)) also
  ran on all 29 tiles; it abstained everywhere, so it produced no score.
- Whether any M1-v2 tuning existed before this run is unknown to the agent
  (the owners answered "not sure" when they signed v1a). This run is the
  first tuning recorded in the repository.
- The 0.40 bar was written after the exploratory figure of 0.455 had been
  seen (protocol v1a, disclosure item EK-06).
- This is a declared protocol after exploratory analysis. It is not
  preregistered and not confirmatory.

## What was run

### Data and split

- Dataset: GEOID-Flood sample, activation EMSR712-3, 29 Sentinel-1 GRD tiles
  of 1024 by 1024 cells at 10 m, linear sigma0, VV and VH. Publisher revision
  `868407460bf3db492f50730a57585916baa71dc6`. All 116 files (58 radar, 29
  label, 29 validity) matched the publisher's SHA-256 list before any pixel
  was read.
- Pre-event pass: 8 September 2023, 17:09 UTC. Post-event pass: 3 January
  2024, 05:34 UTC. The two passes are almost four months apart and come from
  different orbit directions (evening and morning).
- Reference: the dataset's label (0 mapped background, 1 permanent water,
  2 mapped flood, 255 outside the mapped area) and its validity mask. The
  flood class is a CEMS Rapid Mapping delineation drawn from the same
  3 January pass that supplies the post-event image.
- Split, as signed in planning protocol v1a (`geoid_split`, SHA-256
  `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954`):
  development tiles 9, 10, 12, 13, 20, 21, 22, 23, 24, 25, 26, 30, 31, 32,
  33; test tiles 35, 36, 37, 38, 39, 40, 41, 42, 45, 46, 47, 48, 49, 50. The
  v1a file was read and its hash and tile lists were checked at both tuning
  sessions.

### M1-literal as implemented

The proposal defines the method in section 3.2.2, "Method 1. Sentinel-1
temporal change detection" (pages 9-10 of the proposal text; section 3.6 is
the validation section and does not define it). As implemented, on each tile:

1. Valid cells: all four backscatter values finite and above zero.
2. Speckle control: Lee (1980) filter on linear power, 5 by 5 window, 4.4
   equivalent looks.
3. Conversion to dB. delta-VV and delta-VH as post minus pre. The VV/VH ratio
   is derived and summarised; the proposal does not use it in the threshold.
4. Otsu threshold on all valid delta-VH cells of the tile.
5. Candidate: delta-VH below the threshold and below zero ("strong negative
   change").
6. Isolated speckle: a candidate cell is kept only if at least 5 of the 9
   cells of its 3 by 3 neighbourhood are candidates.

It was run once, on all 29 tiles, after the M1-v2 freeze was committed.
Nothing was tuned. Four points are the agent's reading of words the proposal
leaves open, fixed before any run: the Lee filter and its window (the
proposal says "speckle control"; the plan names Lee), the Otsu threshold
being global within each 10 km tile, "strong negative change" meaning below
both the threshold and zero, and the 3 by 3 majority rule for "clean
isolated speckle".

**The "below zero" clause is not in the proposal.** Step 4 of the proposal
reads: "Estimate the Otsu threshold on valid delta-VH pixels; strong
negative change becomes candidate temporary water." The Otsu threshold is
above zero on 23 of the 29 tiles (it is below zero only on tiles 22, 31, 32,
33, 42 and 49). On those 23 tiles the rule as
implemented is "delta-VH below zero" and the proposal's Otsu threshold has
no effect. The method scored under the name M1-literal is therefore mostly
not an Otsu method. The clause favours M1-literal: without it, the rule
flags every cell below a threshold that sits above zero, including cells
that became brighter. On the 15 development tiles the reading without the
clause scores IoU 0.088 and flags 9.2 times the mapped flood area, against
0.127 and 6.3 times with the clause
([reproduction file](../../../outputs/geoid_m1_v2_amendment_check_reproduction.json)).
The reading without the clause was not scored on the test tiles, because
the held-out scoring is computed once.

Steps of the proposal that were not run, and why:

- Orbit correction, thermal-noise removal, calibration and terrain
  correction: done by the dataset publisher. They cannot be rerun from tiles.
- Removal of permanent water: no independent permanent-water layer for this
  site is on disk, and the label's permanent-water class is reference
  information that the method must not see. The secondary comparison leaves
  permanent water out of the score instead.
- Removal of steep terrain, and shadow and layover flags: no DEM and no
  incidence-angle layer for these tiles is on disk.

### M1-v2 as implemented

1. Valid cells as above.
2. Refined-Lee filter (Lee 1981): 7 by 7 window, eight edge-aligned half
   windows, 4.4 equivalent looks.
3. Change in dB (post minus pre). The frozen configuration uses delta-VH and
   darkening only.
4. Split-based selection: the tile is cut into non-overlapping blocks (64 by
   64 cells in the frozen configuration). For each block a two-component
   Gaussian mixture is fitted to the change histogram. The block is kept when
   Ashman's D is above 2, each component holds at least 10% of the block,
   the upper component is a darkening, and the lower component is the one
   closer to no change.
5. The histograms of the kept blocks are pooled and a Kittler-Illingworth
   threshold is set on the pooled histogram. The threshold must be an
   interior minimum of the criterion between the two fitted modes
   (amendment 1) and must be above 0 dB.
6. If the tile has no such threshold, **the method declines for the whole
   tile**: every cell is "no answer", not "no flood".
7. Candidate: darkening at or above the threshold, then the same 3 by 3
   majority rule.

The Otsu comparator is the same pipeline with Otsu's threshold on the same
pooled histogram. It is reported beside M1-v2 and was never eligible to be
chosen. In the result tables it is evaluated at the configuration that the
selection rule chose for Kittler-Illingworth, not at the configuration where
Otsu itself scored best on the development tiles.

Two parts of the plan's specification are left out, as the task allows:

- **No land-cover stratification.** No land-cover layer for these tiles is
  on disk: the WorldCover tiles on disk cover Thailand only, and the dataset
  has no land-cover layer. Bidirectional change was still offered in the
  search space, without stratification. The development tiles did not
  choose it.
- **No slope or HAND mask.** No DEM for these tiles is on disk (plan A3).
  M1-v2 is frozen slope-free; on Mae Sai the HAND and slope mask will be a
  disclosed difference.

### How scores are computed

- **Primary comparison:** mapped flood against mapped background and
  permanent water, in cells with validity 1. **Secondary comparison:**
  permanent water left out.
- Counts are summed over the tiles of a split before any ratio (pooled). An
  undefined ratio is written "undefined", never zero.
- **Covered cells:** only cells where the method gave an answer.
  **Strict:** every cell without an answer counts as "no flood found", so
  declining over mapped flood costs recall. **Coverage:** share of evaluable
  cells with an answer.
- **What the strict reading does not do.** It scores a declined tile exactly
  like an answer of "no flood" everywhere. Mapped flood in the tile is
  missed, and nothing in the tile can be a false alarm. Declining a tile
  with little flood therefore raises the strict IoU. For this reason the
  strict IoU is shown with the share of cells without an answer in the same
  table cell or sentence.
- **Dice** is reported beside IoU on both readings. It is a function of the
  same counts (Dice = 2 IoU / (1 + IoU)) and adds no information.
- IoU, precision and recall are used because the reference is a labelled
  benchmark. They measure agreement with a same-pass CEMS map, not
  independent accuracy. Mapped background is not confirmed dry land.

## Order of work

| Step | Commit | What it holds |
| --- | --- | --- |
| Declaration | `7666536` | Declared benchmark protocol (search space, selection rule, metrics, strata, reading of the skill bar), code and tests. No tile scored. |
| Session 1 | (logged) | 36 runs on the development tiles. Its freeze was written but never committed, and is withdrawn. |
| Amendment 1 | `2a3fdcb` | The session 1 log, the correction to the threshold code and its test, and the amendment text in the declared protocol. |
| Session 2 and freeze | `34ff88d` | The session 2 log, the frozen configuration and its receipt. Committed before any test tile was opened. |
| Held-out scoring | `27f737f` | The summary and this document. Computed once. |
| Review corrections | the commit that adds the addendum | Addendum 1, the derived checks, the reproduction of the amendment check, this revision. No test tile opened, no score changed. |

The task asked for two commits (freeze, then result). There are four: the
declaration and the amendment were committed separately so that the order
"declare, tune, freeze, score" can be read from the history. The loader
refuses every test tile in the tuning phase, and the scoring script refuses
to run unless the frozen files equal the committed versions, and refuses to
run twice.

What the two attestations are worth. `test_tiles_opened: []` in both session
records and `test_tiles_opened_before_freeze: false` in the receipt were
written as constants by the scripts. They are not a record of what was
opened. The loader guard covers reads made through the tile store only; it
cannot stop a raster read that goes around it. What supports the claim that
tuning saw development tiles only:

- The reviewer reported that both sessions reproduce exactly from the 15
  development tiles alone, with the code of commits `7666536` and `2a3fdcb`:
  all 72 runs, including the per-tile detail, and the two choices (run 29,
  then run 1). This lane did not repeat that re-run.
- The development-only check quoted in amendment 1 was made by code that was
  not committed and is not in the log. It has now been recomputed from the
  15 development tiles through a tile store that records what it opens
  (`scripts/diagnose_geoid_m1_v2_amendment_check.py`). Every published
  value for the six tiles was recomputed exactly. The store opened 15
  development tiles and no test tile.
- The commit order is declaration 15:59:26 UTC, session 1 from 15:59:33,
  amendment 16:14:01, session 2 from 16:14:07, freeze commit 16:30:14,
  held-out summary 16:35:47 (all 2 October 2026).

So the frozen configuration follows from the development tiles, the
committed code and the declared grid. What was looked at while amendment 1
was being designed cannot be shown after the fact. From now on the tuning
script writes what its tile store recorded, not a constant.

Frozen configuration: SHA-256
`2bfcb0c6ebf4b79402afa63c56209f2c5cda26491f08883d67908195b6c64a68`, recorded
beside the v1a SHA-256 in
[geoid_m1_v2_freeze_receipt.json](geoid_m1_v2_freeze_receipt.json).

## Results by split

Primary comparison (permanent water counts as not flood):

| Method | Split | IoU, strict (cells without an answer) | IoU, covered cells | Precision | Recall, strict | Coverage | Tiles declined | Predicted area / reference area | Dice, strict | Dice, covered cells |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | 0.127 (0.2% no answer) | 0.127 | 0.131 | 0.822 | 99.8% | 0 of 15 | 6.29 | 0.225 | 0.226 |
| M1-literal | test | 0.159 (0.2% no answer) | 0.159 | 0.164 | 0.839 | 99.8% | 0 of 14 | 5.11 | 0.275 | 0.275 |
| M1-v2 (frozen) | development | 0.441 (48.7% no answer) | 0.446 | 0.592 | 0.633 | 51.3% | 9 of 15 | 1.07 | 0.612 | 0.617 |
| M1-v2 (frozen) | test | 0.411 (67.9% no answer) | 0.506 | 0.731 | 0.484 | 32.1% | 10 of 14 | 0.66 | 0.583 | 0.672 |
| M1-v2 with Otsu (comparator) | development | 0.171 (0.2% no answer) | 0.171 | 0.181 | 0.748 | 99.8% | 0 of 15 | 4.13 | 0.292 | 0.292 |
| M1-v2 with Otsu (comparator) | test | 0.216 (1.7% no answer) | 0.216 | 0.233 | 0.750 | 98.3% | 1 of 14 | 3.23 | 0.355 | 0.355 |

Secondary comparison (permanent water left out):

| Method | Split | IoU, strict (cells without an answer) | IoU, covered cells | Precision | Recall, strict | Coverage | Tiles declined | Predicted area / reference area | Dice, strict | Dice, covered cells |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | 0.130 (0.1% no answer) | 0.130 | 0.134 | 0.822 | 99.9% | 0 of 15 | 6.14 | 0.230 | 0.230 |
| M1-literal | test | 0.163 (0.1% no answer) | 0.163 | 0.168 | 0.839 | 99.9% | 0 of 14 | 5.00 | 0.280 | 0.280 |
| M1-v2 (frozen) | development | 0.443 (48.3% no answer) | 0.449 | 0.596 | 0.633 | 51.7% | 9 of 15 | 1.06 | 0.614 | 0.619 |
| M1-v2 (frozen) | test | 0.413 (67.9% no answer) | 0.508 | 0.736 | 0.484 | 32.1% | 10 of 14 | 0.66 | 0.584 | 0.674 |
| M1-v2 with Otsu (comparator) | development | 0.174 (0.1% no answer) | 0.174 | 0.185 | 0.748 | 99.9% | 0 of 15 | 4.04 | 0.297 | 0.297 |
| M1-v2 with Otsu (comparator) | test | 0.220 (1.6% no answer) | 0.220 | 0.237 | 0.750 | 98.4% | 1 of 14 | 3.16 | 0.360 | 0.361 |

Cell counts, primary comparison:

| Method | Split | Evaluable cells | Reference flood cells | Flood agreed (TP) | Flagged, not mapped flood (FP) | Mapped flood missed where the method answered | Mapped flood in cells without an answer |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | 9,197,566 | 414,165 | 340,580 | 2,266,221 | 73,079 | 506 |
| M1-literal | test | 8,598,631 | 548,591 | 460,321 | 2,344,285 | 87,688 | 582 |
| M1-v2 (frozen) | development | 9,197,566 | 414,165 | 262,256 | 180,736 | 144,690 | 7,219 |
| M1-v2 (frozen) | test | 8,598,631 | 548,591 | 265,729 | 97,693 | 161,598 | 121,264 |
| M1-v2 with Otsu (comparator) | development | 9,197,566 | 414,165 | 309,647 | 1,400,602 | 104,012 | 506 |
| M1-v2 with Otsu (comparator) | test | 8,598,631 | 548,591 | 411,663 | 1,358,204 | 136,346 | 582 |

"Cells without an answer" are the cells of declined tiles and the few cells
with unusable radar values in tiles that were answered. For M1-v2 on the
test split, 120,771 of the 121,264 cells are in the ten declined tiles.

Reading the tables:

- **M1-literal.** After filtering, the January image is brighter than the
  September image over most of the land (the median delta-VH per tile is
  +0.4 to +2.0 dB). On tiles with little or no flood the Otsu threshold is
  therefore above zero, and the rule "below the threshold and below zero"
  flags every cell that darkened at all. That is why its predicted area is
  five to six times the mapped flood.
- **M1-v2.** Higher precision, lower recall, and an answer on about half of
  the development cells and a third of the test cells. The gap between the
  strict and the covered reading on the test split (0.411 with 67.9% of the
  cells without an answer, against 0.506) is the mapped flood inside
  declined tiles.
- **Otsu comparator.** With the same 64-cell blocks, Otsu's threshold sits
  low (0.1 to 3.8 dB of darkening on the development tiles) and almost
  never declines, so it flags three to four times the mapped flood. This
  holds for the configuration chosen for Kittler-Illingworth only. With
  256-cell blocks most tiles have no bimodal block, Otsu declines on them
  too, and its development score rises: 0.475 with 10 of 15 tiles declined
  (run 29), 0.419 with 8 declined (run 35), 0.374 with 9 declined (run 5).
  Run 29 is above the frozen M1-v2 (0.441). The tuning table lists the
  comparator's score and its declined tiles for all 36 runs.
- **What the comparison does and does not show.** The table above compares
  two threshold rules at one block size. It does not show that the
  Kittler-Illingworth threshold lifts the score from about 0.2 to 0.41. On
  the tiles where M1-v2 answered, the two rules are closer: 0.446 against
  0.376 on the six development tiles and 0.506 against 0.460 on the four
  test tiles (M1-literal: 0.247 and 0.350). The larger part of the
  difference in the pooled score comes from the tiles M1-v2 declined. On
  the ten declined test tiles the Otsu comparator has 1,095,692 false
  alarms (81% of all its false alarms on the test split) and M1-v2 is
  charged none.
- Development and test scores of M1-v2 are close on the strict reading
  (0.441 with 48.7% of the cells without an answer, and 0.411 with 67.9%).
  The test split has more mapped flood (6.4% of evaluable cells against
  4.5%).

## The T2 skill bar

Protocol v1a (`t2_skill_bar`): a T2 input is low confidence unless four
conditions all pass. One of them is a GEOID held-out test IoU of at least
0.40. The other three concern Mae Sai (abstention at most 0.20, unit
coverage at least 0.80, a 3-day recency window) and cannot be assessed here.

| Reading | M1-v2 pooled test IoU, point estimate | Point estimate at least 0.40? | Lowest with one tile left out | Tile bootstrap, 95% range | Resamples at or above 0.40 |
| --- | ---: | --- | ---: | ---: | ---: |
| Strict (declined cells count as "no flood found") | 0.411 (67.9% no answer) | yes, by 0.011 | 0.297 | 0.098 to 0.513 | 51.1% |
| Covered cells only | 0.506 | yes | 0.434 | 0.284 to 0.579 | 87.1% |

v1a does not say how declined cells count. The declared benchmark protocol
fixed the reading before any tuning: both figures must reach 0.40.

**Reading: point estimate 0.411; not distinguishable from 0.40 on 14
tiles.** Both point estimates reach the minimum. The strict one does not
hold when either of two tiles is removed, and half of the tile resamples
fall below 0.40. The earlier text of this section said the condition "is
met"; that was a bare yes on a point estimate and is withdrawn. Whether a
point estimate with this spread counts as passing is for the owners to
decide in v1b (see "Decisions for the owners").

Pooled test IoU of M1-v2 with each test tile left out in turn:

| Tile left out | M1-v2 on that tile | IoU, strict | IoU, covered cells | Cells without an answer | Both readings at least 0.40? |
| ---: | --- | ---: | ---: | ---: | --- |
| 35 | declined | 0.411 | 0.506 | 66.8% | yes |
| 36 | declined | 0.412 | 0.506 | 65.1% | yes |
| 37 | declined | 0.416 | 0.506 | 63.5% | yes |
| 38 | declined | 0.427 | 0.506 | 64.4% | yes |
| 39 | declined | 0.414 | 0.506 | 65.7% | yes |
| 40 | declined | 0.414 | 0.506 | 64.9% | yes |
| 41 | declined | 0.433 | 0.506 | 64.4% | yes |
| 42 | answered | 0.297 | 0.434 | 75.9% | no |
| 45 | declined | 0.411 | 0.506 | 67.4% | yes |
| 46 | answered | 0.413 | 0.518 | 73.0% | yes |
| 47 | answered | 0.427 | 0.541 | 74.1% | yes |
| 48 | declined | 0.425 | 0.506 | 65.5% | yes |
| 49 | answered | 0.380 | 0.500 | 72.2% | no |
| 50 | declined | 0.427 | 0.506 | 67.2% | yes |

How these checks were made. They use the per-tile counts in the committed
summary and open no tile. The bootstrap draws 14 tiles with replacement,
20,000 times, with a fixed seed, pools the counts of each draw and takes the
2.5th and 97.5th percentiles. In 178 draws no answered tile was drawn; those
have no covered IoU and count as below 0.40. The tile is the resampling
unit. Neighbouring tiles are not independent, so the true spread is more
likely wider than the range shown, and 14 tiles are few for this method.
The checks were added after the score had been seen. They are a description of
how much the score rests on single tiles, not a declared pass rule. The
figures are in
[geoid_m1_benchmark_v2_derived_checks.json](../../../outputs/geoid_m1_benchmark_v2_derived_checks.json),
block `t2_skill_bar`, with the flag `robust: false`. A later lane reads that
block. The boolean `m1_v2_reaches_the_geoid_condition: true` in the summary
states the point estimate only and must not be used alone.

**Requiring both readings does not make the bar proof against declining.**
A code comment said that it does, and the declared protocol implies it. That
was wrong.
The covered reading ignores declined tiles. The strict reading scores a
declined tile like an answer of "no flood": mapped flood in it is missed,
and nothing in it can be a false alarm. Neither reading charges anything
for declining a tile with little flood. The selection rule maximises the
strict development IoU, so it favours configurations that decline such
tiles, and the frozen one declines 9 of 15 development tiles and 10 of 14
test tiles. The same pipeline with a threshold that almost never declines
(the Otsu comparator at the same blocks) scores 0.216 on the test split.

None of this makes M1-v2 qualified, promoted or a basis for any class above
E:

- It is agreement with a same-pass CEMS map on one foreign event, not
  independent accuracy.
- Two test tiles (42 and 49, both more than 23% flooded) hold 63% of the
  mapped flood of the test split and carry the score.
- On these test tiles the method declined on 10 of 14 tiles, 67.9% of the
  evaluable cells. The Mae Sai abstention condition of v1a (at most 0.20) is
  a separate test. A method that behaved there as it does here would fail
  it.
- The bar itself was written after a figure of 0.455 had been seen on these
  tiles.
- M1-literal is declared unable to meet the bar by v1a, whatever it scores.
  It scores 0.159.

## Tuning on the development tiles

### Search space, declared before the first run

Four choices, 36 combinations:

| Choice | Values | Why it is tuned |
| --- | --- | --- |
| Change that is thresholded | delta-VH; delta-VV; mean of both | The proposal uses delta-VH. Over short grass in winter VH is close to the noise floor, so VV might separate water better. |
| Direction | darkening; bidirectional | The plan asks for bidirectional change stratified by land cover. Without a land-cover layer a rise in backscatter may only be seasonal, so darkening-only is offered too. |
| Block size | 64; 128; 256 cells | Blocks must be small enough to hold both flooded and dry land. |
| Threshold scope | per tile; pooled over the tiles of the split | On Mae Sai the method will run on one scene. Both readings of "global" are tried. |

Not tuned: any dB threshold, any offset to the threshold, the filter, the
number of looks, Ashman's D (2, from the plan), the 10% component weight
(from the split-based approach of Chini et al. 2017) and the cleaning rule.

Selection rule, declared with the search space: highest pooled development
IoU on the primary comparison, strict reading, for the Kittler-Illingworth
threshold; ties by higher coverage, then by the earlier run.

### Two sessions and one amendment

**Session 1** (2 October 2026, 15:59 UTC) ran all 36 combinations. In 30 of
them the development IoU was below 0.1, with thresholds of 8 to 16 dB of
change, while the Otsu comparator on the same histograms gave 0.07 to 0.32.
A check on development tiles only showed the cause. Where the flooded and
the unchanged class overlap, the Kittler-Illingworth criterion has no
minimum between the two modes. It keeps falling to the edge of the search
range, and that edge is set by a 1% class floor in the code, not by the
data. The code returned the edge as if it were a threshold.

**Amendment 1** (commit `2a3fdcb`, before session 2): a threshold is
accepted only at an interior minimum of the criterion, between the two
fitted modes. When there is none the method declines. No fallback threshold
was added. The search space and the selection rule did not change.

This is a change made after development scores had been seen. It is tuning,
it used development tiles only, and it is the reason held-out tiles exist.
Session 1 stays in the log. Its choice (run 29, IoU 0.433) was never
committed as a freeze.

**Session 2** (16:14 UTC) reran the same 36 combinations. The log is
[geoid_m1_v2_tuning_log.jsonl](geoid_m1_v2_tuning_log.jsonl): two session
records, 72 run records with per-tile detail, two selection records.

| Run | Change | Direction | Block (cells) | Threshold scope | Session 1 IoU, strict | Session 2 IoU, strict | Session 2 IoU, covered cells | Session 2 precision | Session 2 recall, strict | Session 2 coverage | Session 2 tiles declined | Otsu comparator IoU, strict | Otsu comparator tiles declined |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **1** | delta-VH | darkening | 64 | per tile | 0.053 | **0.441** | 0.446 | 0.592 | 0.633 | 51.3% | 9 of 15 | 0.171 | 0 of 15 |
| 2 | delta-VH | darkening | 64 | pooled | 0.020 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.239 | 0 of 15 |
| 3 | delta-VH | darkening | 128 | per tile | 0.055 | 0.409 | 0.575 | 0.715 | 0.489 | 31.7% | 11 of 15 | 0.195 | 5 of 15 |
| 4 | delta-VH | darkening | 128 | pooled | 0.014 | 0.369 | 0.369 | 0.508 | 0.574 | 99.8% | 0 of 15 | 0.268 | 0 of 15 |
| 5 | delta-VH | darkening | 256 | per tile | 0.415 | 0.417 | 0.603 | 0.775 | 0.474 | 22.9% | 12 of 15 | 0.374 | 9 of 15 |
| 6 | delta-VH | darkening | 256 | pooled | 0.011 | 0.361 | 0.361 | 0.461 | 0.625 | 99.8% | 0 of 15 | 0.285 | 0 of 15 |
| 7 | delta-VH | bidirectional | 64 | per tile | 0.051 | 0.434 | 0.439 | 0.580 | 0.633 | 51.3% | 9 of 15 | 0.092 | 0 of 15 |
| 8 | delta-VH | bidirectional | 64 | pooled | 0.019 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.111 | 0 of 15 |
| 9 | delta-VH | bidirectional | 128 | per tile | 0.054 | 0.407 | 0.570 | 0.707 | 0.489 | 31.7% | 11 of 15 | 0.101 | 1 of 15 |
| 10 | delta-VH | bidirectional | 128 | pooled | 0.014 | 0.369 | 0.369 | 0.508 | 0.574 | 99.8% | 0 of 15 | 0.103 | 0 of 15 |
| 11 | delta-VH | bidirectional | 256 | per tile | 0.414 | 0.417 | 0.603 | 0.775 | 0.474 | 22.9% | 12 of 15 | 0.338 | 7 of 15 |
| 12 | delta-VH | bidirectional | 256 | pooled | 0.011 | 0.361 | 0.361 | 0.461 | 0.625 | 99.8% | 0 of 15 | 0.113 | 0 of 15 |
| 13 | delta-VV | darkening | 64 | per tile | 0.008 | 0.330 | 0.498 | 0.730 | 0.376 | 16.2% | 13 of 15 | 0.152 | 1 of 15 |
| 14 | delta-VV | darkening | 64 | pooled | 0.012 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.183 | 0 of 15 |
| 15 | delta-VV | darkening | 128 | per tile | 0.016 | 0.053 | 0.484 | 0.680 | 0.054 | 5.2% | 14 of 15 | 0.318 | 9 of 15 |
| 16 | delta-VV | darkening | 128 | pooled | 0.015 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.174 | 0 of 15 |
| 17 | delta-VV | darkening | 256 | per tile | 0.008 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.302 | 12 of 15 |
| 18 | delta-VV | darkening | 256 | pooled | 0.019 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.169 | 0 of 15 |
| 19 | delta-VV | bidirectional | 64 | per tile | 0.007 | 0.330 | 0.498 | 0.730 | 0.376 | 16.2% | 13 of 15 | 0.066 | 0 of 15 |
| 20 | delta-VV | bidirectional | 64 | pooled | 0.011 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.069 | 0 of 15 |
| 21 | delta-VV | bidirectional | 128 | per tile | 0.015 | 0.053 | 0.484 | 0.680 | 0.054 | 5.2% | 14 of 15 | 0.143 | 5 of 15 |
| 22 | delta-VV | bidirectional | 128 | pooled | 0.014 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.072 | 0 of 15 |
| 23 | delta-VV | bidirectional | 256 | per tile | 0.008 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.302 | 12 of 15 |
| 24 | delta-VV | bidirectional | 256 | pooled | 0.019 | 0.000 | undefined | undefined | 0.000 | 0.0% | 15 of 15 | 0.169 | 0 of 15 |
| 25 | mean of both | darkening | 64 | per tile | 0.394 | 0.368 | 0.491 | 0.573 | 0.507 | 49.7% | 8 of 15 | 0.222 | 2 of 15 |
| 26 | mean of both | darkening | 64 | pooled | 0.022 | 0.358 | 0.358 | 0.531 | 0.523 | 99.8% | 0 of 15 | 0.258 | 0 of 15 |
| 27 | mean of both | darkening | 128 | per tile | 0.075 | 0.394 | 0.532 | 0.622 | 0.518 | 38.5% | 10 of 15 | 0.237 | 4 of 15 |
| 28 | mean of both | darkening | 128 | pooled | 0.018 | 0.365 | 0.365 | 0.501 | 0.573 | 99.8% | 0 of 15 | 0.272 | 0 of 15 |
| 29 | mean of both | darkening | 256 | per tile | 0.433 | 0.429 | 0.618 | 0.768 | 0.493 | 23.6% | 11 of 15 | 0.475 | 10 of 15 |
| 30 | mean of both | darkening | 256 | pooled | 0.018 | 0.364 | 0.364 | 0.476 | 0.607 | 99.8% | 0 of 15 | 0.279 | 0 of 15 |
| 31 | mean of both | bidirectional | 64 | per tile | 0.380 | 0.362 | 0.477 | 0.558 | 0.507 | 58.5% | 7 of 15 | 0.097 | 0 of 15 |
| 32 | mean of both | bidirectional | 64 | pooled | 0.021 | 0.358 | 0.358 | 0.531 | 0.523 | 99.8% | 0 of 15 | 0.100 | 0 of 15 |
| 33 | mean of both | bidirectional | 128 | per tile | 0.073 | 0.391 | 0.526 | 0.613 | 0.518 | 38.5% | 10 of 15 | 0.115 | 0 of 15 |
| 34 | mean of both | bidirectional | 128 | pooled | 0.017 | 0.365 | 0.365 | 0.501 | 0.573 | 99.8% | 0 of 15 | 0.105 | 0 of 15 |
| 35 | mean of both | bidirectional | 256 | per tile | 0.432 | 0.429 | 0.618 | 0.768 | 0.493 | 23.6% | 11 of 15 | 0.419 | 8 of 15 |
| 36 | mean of both | bidirectional | 256 | pooled | 0.017 | 0.364 | 0.364 | 0.476 | 0.607 | 99.8% | 0 of 15 | 0.109 | 0 of 15 |

All figures are pooled over the 15 development tiles, primary comparison.
The Otsu comparator is the same in both sessions. The chosen run is in bold.

What the table shows:

- **The chosen run is run 1**: delta-VH, darkening only, 64-cell blocks, a
  threshold per tile. Development IoU 0.441 strict, 0.446 on covered cells,
  precision 0.592, recall 0.633, coverage 51.3%, 9 of 15 tiles declined.
- **The margin is thin.** Seven other runs are within 0.035 of it (0.434,
  0.429, 0.429, 0.417, 0.417, 0.409, 0.407). With 15 tiles, of which four
  hold 98% of the mapped flood, the choice between them is not well
  determined.
- **Direction made little difference** after the amendment: the
  brightening side obtained a threshold on at most 2 of 15 tiles in any
  run, and where it did the score fell slightly.
- **Pooled scope** gives an answer on every tile at about 0.36 to 0.37, or
  declines everywhere. **Per-tile scope** scores higher on the strict
  reading because it declines on tiles with little or no flood, where a
  pooled threshold produces false alarms.
- **delta-VV alone** declines on almost every tile.
- **The Otsu comparator scores higher the more tiles it declines.** Its
  seven best runs (0.475, 0.419, 0.374, 0.338, 0.318 and 0.302 twice) are
  per-tile runs with 256-cell or 128-cell blocks that decline 7 to 12 of
  the 15 tiles.
  Where it declines on none it scores 0.07 to 0.29. One Otsu run (run 29,
  0.475) is above the frozen Kittler-Illingworth run (0.441). The declared
  selection rule reads the Kittler-Illingworth score only, so this did not
  and could not change the choice.

## Results per tile

"Declined" means the method gave no answer on the tile. In every declined
tile some blocks were selected as bimodal; the tile was declined at the
threshold step, because the pooled histogram of those blocks gave no
acceptable Kittler-Illingworth threshold.

| Tile | Split | Reference flooded share | M1-literal IoU | M1-literal Otsu threshold (dB) | M1-v2 threshold (dB of darkening) | M1-v2 blocks selected | M1-v2 IoU, strict | M1-v2 precision | M1-v2 recall, strict | Otsu comparator IoU, strict |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 9 | development | 0.28% | 0.009 | 0.9 | declined | 12 of 256 | 0.000 | undefined | 0.000 | 0.019 |
| 10 | development | 0.00% | 0.000 | 1.2 | declined | 7 of 256 | undefined | undefined | undefined | 0.000 |
| 12 | development | 0.00% | 0.000 | 1.5 | declined | 22 of 256 | undefined | undefined | undefined | 0.000 |
| 13 | development | 0.00% | 0.000 | 2.7 | declined | 12 of 256 | undefined | undefined | undefined | 0.000 |
| 20 | development | 0.47% | 0.011 | 1.3 | 4.3 | 11 of 256 | 0.030 | 0.032 | 0.313 | 0.016 |
| 21 | development | 0.01% | 0.000 | 0.8 | 3.6 | 6 of 256 | 0.000 | 0.000 | 0.243 | 0.001 |
| 22 | development | 2.25% | 0.157 | -1.6 | 3.7 | 28 of 256 | 0.335 | 0.383 | 0.728 | 0.309 |
| 23 | development | 0.00% | 0.000 | 1.5 | declined | 8 of 256 | undefined | undefined | undefined | 0.000 |
| 24 | development | 0.06% | 0.002 | 2.0 | declined | 20 of 256 | 0.000 | undefined | 0.000 | 0.002 |
| 25 | development | 0.59% | 0.016 | 2.4 | declined | 22 of 256 | 0.000 | undefined | 0.000 | 0.018 |
| 26 | development | 0.00% | 0.000 | 2.7 | declined | 27 of 256 | undefined | undefined | undefined | 0.000 |
| 30 | development | 0.00% | 0.000 | 1.4 | declined | 51 of 256 | undefined | undefined | undefined | 0.000 |
| 31 | development | 13.62% | 0.295 | -0.6 | 5.5 | 47 of 256 | 0.350 | 0.635 | 0.438 | 0.381 |
| 32 | development | 21.62% | 0.643 | -2.9 | 3.6 | 74 of 256 | 0.658 | 0.814 | 0.774 | 0.658 |
| 33 | development | 7.51% | 0.220 | -0.3 | 4.9 | 34 of 256 | 0.497 | 0.723 | 0.614 | 0.436 |
| 35 | test | 0.00% | 0.000 | 2.1 | declined | 19 of 256 | undefined | undefined | undefined | 0.000 |
| 36 | test | 0.15% | 0.004 | 2.1 | declined | 15 of 256 | 0.000 | undefined | 0.000 | 0.005 |
| 37 | test | 0.67% | 0.016 | 2.0 | declined | 36 of 256 | 0.000 | undefined | 0.000 | 0.022 |
| 38 | test | 2.94% | 0.074 | 2.2 | declined | 26 of 256 | 0.000 | undefined | 0.000 | 0.105 |
| 39 | test | 0.97% | 0.027 | 3.3 | declined | 25 of 256 | 0.000 | undefined | 0.000 | 0.032 |
| 40 | test | 0.72% | 0.020 | 1.9 | declined | 42 of 256 | 0.000 | undefined | 0.000 | 0.025 |
| 41 | test | 3.92% | 0.111 | 1.8 | declined | 27 of 256 | 0.000 | undefined | 0.000 | 0.186 |
| 42 | test | 24.25% | 0.556 | -1.8 | 3.8 | 56 of 256 | 0.578 | 0.788 | 0.685 | 0.586 |
| 45 | test | 0.00% | 0.000 | 2.9 | declined | 3 of 256 | undefined | undefined | undefined | undefined |
| 46 | test | 6.69% | 0.157 | 1.4 | 6.2 | 25 of 256 | 0.393 | 0.697 | 0.474 | 0.290 |
| 47 | test | 6.02% | 0.141 | 1.6 | 6.0 | 31 of 256 | 0.284 | 0.424 | 0.462 | 0.227 |
| 48 | test | 3.57% | 0.085 | 0.8 | declined | 35 of 256 | 0.000 | undefined | 0.000 | 0.169 |
| 49 | test | 23.42% | 0.512 | -1.0 | 4.1 | 52 of 256 | 0.522 | 0.780 | 0.612 | 0.559 |
| 50 | test | 13.28% | 0.317 | 2.0 | declined | 17 of 256 | 0.000 | undefined | 0.000 | 0.457 |

## Failure strata

All strata use the primary comparison. "Mapped flood missed (strict)"
includes mapped flood inside declined tiles.

### By the tile's reference flooded share

| Method | Split | Stratum | Tiles | Evaluable cells | Reference flood cells | IoU, strict | Precision | Recall, strict | Coverage | Flagged, not mapped flood | Mapped flood missed (strict) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | no reference flood | 6 | 1,990,269 | 0 | 0.000 | 0.000 | undefined | 99.8% | 615,271 | 0 |
| M1-literal | development | above 0 to 1% | 5 | 4,103,882 | 9,532 | 0.007 | 0.007 | 0.820 | 99.8% | 1,180,854 | 1,713 |
| M1-literal | development | above 1% to 5% | 1 | 618,044 | 13,880 | 0.157 | 0.162 | 0.830 | 100.0% | 59,386 | 2,364 |
| M1-literal | development | above 5% to 20% | 2 | 1,469,461 | 171,067 | 0.275 | 0.289 | 0.849 | 99.8% | 356,643 | 25,847 |
| M1-literal | development | above 20% | 1 | 1,015,910 | 219,686 | 0.643 | 0.765 | 0.801 | 99.9% | 54,067 | 43,661 |
| M1-literal | test | no reference flood | 2 | 398,035 | 0 | 0.000 | 0.000 | undefined | 99.8% | 106,721 | 0 |
| M1-literal | test | above 0 to 1% | 4 | 2,984,949 | 18,326 | 0.016 | 0.016 | 0.833 | 99.6% | 928,929 | 3,055 |
| M1-literal | test | above 1% to 5% | 3 | 2,271,388 | 78,827 | 0.090 | 0.092 | 0.864 | 99.8% | 676,080 | 10,725 |
| M1-literal | test | above 5% to 20% | 3 | 1,509,760 | 107,863 | 0.169 | 0.173 | 0.876 | 99.9% | 452,272 | 13,393 |
| M1-literal | test | above 20% | 2 | 1,434,499 | 343,575 | 0.539 | 0.610 | 0.822 | 99.9% | 180,283 | 61,097 |
| M1-v2 (frozen) | development | no reference flood | 6 | 1,990,269 | 0 | undefined | undefined | undefined | 0.0% | 0 | 0 |
| M1-v2 (frozen) | development | above 0 to 1% | 5 | 4,103,882 | 9,532 | 0.009 | 0.010 | 0.091 | 39.5% | 83,213 | 8,665 |
| M1-v2 (frozen) | development | above 1% to 5% | 1 | 618,044 | 13,880 | 0.335 | 0.383 | 0.728 | 100.0% | 16,282 | 3,773 |
| M1-v2 (frozen) | development | above 5% to 20% | 2 | 1,469,461 | 171,067 | 0.380 | 0.657 | 0.474 | 99.8% | 42,452 | 89,929 |
| M1-v2 (frozen) | development | above 20% | 1 | 1,015,910 | 219,686 | 0.658 | 0.814 | 0.774 | 99.9% | 38,789 | 49,542 |
| M1-v2 (frozen) | test | no reference flood | 2 | 398,035 | 0 | undefined | undefined | undefined | 0.0% | 0 | 0 |
| M1-v2 (frozen) | test | above 0 to 1% | 4 | 2,984,949 | 18,326 | 0.000 | undefined | 0.000 | 0.0% | 0 | 18,326 |
| M1-v2 (frozen) | test | above 1% to 5% | 3 | 2,271,388 | 78,827 | 0.000 | undefined | 0.000 | 0.0% | 0 | 78,827 |
| M1-v2 (frozen) | test | above 5% to 20% | 3 | 1,509,760 | 107,863 | 0.274 | 0.524 | 0.366 | 88.1% | 35,845 | 68,435 |
| M1-v2 (frozen) | test | above 20% | 2 | 1,434,499 | 343,575 | 0.558 | 0.785 | 0.659 | 99.9% | 61,848 | 117,274 |

- M1-v2 gives an answer on the heavily flooded tiles and declines on most
  others. On the test split **every tile with up to 5% mapped flood was
  declined** (7 tiles, 97,153 mapped flood cells), and so was tile 50 with
  13% mapped flood.
- Both tiles without mapped flood in the test split, and all six in the
  development split, were declined by M1-v2. M1-literal flags 27% (test)
  and 31% (development) of the cells of those tiles, pooled by split, and
  25% to 44% per tile (tile 30 is the highest).
- M1-literal reaches 0.54 to 0.64 only where more than 20% of the tile is
  flooded. Below 5% it stays under 0.16.

### By post-event acquisition slice

| Method | Split | Stratum | Tiles | Evaluable cells | Reference flood cells | IoU, strict | Precision | Recall, strict | Coverage | Flagged, not mapped flood | Mapped flood missed (strict) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | 2024-01-03 05:33:41 UTC | 9 | 5,986,472 | 409,723 | 0.197 | 0.205 | 0.823 | 99.9% | 1,305,428 | 72,579 |
| M1-literal | development | 2024-01-03 05:34:06 UTC | 6 | 3,211,094 | 4,442 | 0.004 | 0.004 | 0.774 | 99.7% | 960,793 | 1,006 |
| M1-literal | test | 2024-01-03 05:33:41 UTC | 6 | 3,776,231 | 426,711 | 0.276 | 0.292 | 0.835 | 99.9% | 862,291 | 70,551 |
| M1-literal | test | 2024-01-03 05:34:06 UTC | 8 | 4,822,400 | 121,880 | 0.065 | 0.066 | 0.855 | 99.7% | 1,481,994 | 17,719 |
| M1-v2 (frozen) | development | 2024-01-03 05:33:41 UTC | 9 | 5,986,472 | 409,723 | 0.444 | 0.592 | 0.640 | 78.9% | 180,736 | 147,467 |
| M1-v2 (frozen) | development | 2024-01-03 05:34:06 UTC | 6 | 3,211,094 | 4,442 | 0.000 | undefined | 0.000 | 0.0% | 0 | 4,442 |
| M1-v2 (frozen) | test | 2024-01-03 05:33:41 UTC | 6 | 3,776,231 | 426,711 | 0.463 | 0.785 | 0.530 | 37.9% | 61,848 | 200,410 |
| M1-v2 (frozen) | test | 2024-01-03 05:34:06 UTC | 8 | 4,822,400 | 121,880 | 0.250 | 0.524 | 0.323 | 27.6% | 35,845 | 82,452 |

The two slices are consecutive frames of the same pass. The difference
between them follows the flood: most of the mapped flood lies in tiles of
the 05:33:41 slice.

### By distance to a reference flood edge

| Method | Split | Stratum | Evaluable cells | Reference flood cells | IoU, strict | Precision | Recall, strict | Coverage | Flagged, not mapped flood | Mapped flood missed (strict) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | within 2 cells of a reference flood edge | 140,769 | 73,533 | 0.433 | 0.644 | 0.570 | 99.8% | 23,185 | 31,620 |
| M1-literal | development | further than 2 cells from a reference flood edge | 9,056,797 | 340,632 | 0.116 | 0.118 | 0.877 | 99.8% | 2,243,036 | 41,965 |
| M1-literal | test | within 2 cells of a reference flood edge | 257,645 | 131,252 | 0.470 | 0.612 | 0.670 | 99.8% | 55,817 | 43,317 |
| M1-literal | test | further than 2 cells from a reference flood edge | 8,340,986 | 417,339 | 0.138 | 0.140 | 0.892 | 99.8% | 2,288,468 | 44,953 |
| M1-v2 (frozen) | development | within 2 cells of a reference flood edge | 140,769 | 73,533 | 0.266 | 0.727 | 0.296 | 95.9% | 8,191 | 51,758 |
| M1-v2 (frozen) | development | further than 2 cells from a reference flood edge | 9,056,797 | 340,632 | 0.469 | 0.582 | 0.706 | 50.6% | 172,545 | 100,151 |
| M1-v2 (frozen) | test | within 2 cells of a reference flood edge | 257,645 | 131,252 | 0.230 | 0.700 | 0.255 | 71.4% | 14,361 | 97,777 |
| M1-v2 (frozen) | test | further than 2 cells from a reference flood edge | 8,340,986 | 417,339 | 0.464 | 0.736 | 0.557 | 30.9% | 83,332 | 185,085 |

This is the nearest measure of boundary error the benchmark supports. On
the test split M1-v2 finds 26% of the mapped flood within two cells of a
flood edge and 56% of the mapped flood further inside. The refined-Lee
filter, the 3 by 3 majority rule and the narrow shape of many mapped flood
strips all work against the edge cells. A boundary distance in metres was
not computed.

### By pre-event VH backscatter

Without a land-cover layer, pre-event backscatter is the only surface
description the data supports. Low values are smooth surfaces (water, bare
soil, short grass); high values are woodland and built-up areas.

| Method | Split | Stratum | Evaluable cells | Reference flood cells | IoU, strict | Precision | Recall, strict | Coverage | Flagged, not mapped flood | Mapped flood missed (strict) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1-literal | development | pre-event VH below -22 dB | 646,970 | 14,871 | 0.134 | 0.147 | 0.611 | 100.0% | 52,776 | 5,791 |
| M1-literal | development | pre-event VH -22 to -18 dB | 2,400,426 | 174,415 | 0.292 | 0.315 | 0.802 | 100.0% | 303,908 | 34,583 |
| M1-literal | development | pre-event VH -18 to -14 dB | 4,004,530 | 209,719 | 0.148 | 0.151 | 0.856 | 100.0% | 1,006,421 | 30,204 |
| M1-literal | development | pre-event VH -14 dB or above | 2,129,170 | 14,654 | 0.013 | 0.013 | 0.829 | 100.0% | 903,116 | 2,501 |
| M1-literal | test | pre-event VH below -22 dB | 976,268 | 40,456 | 0.241 | 0.278 | 0.643 | 100.0% | 67,544 | 14,451 |
| M1-literal | test | pre-event VH -22 to -18 dB | 2,479,965 | 252,381 | 0.350 | 0.375 | 0.836 | 100.0% | 351,124 | 41,414 |
| M1-literal | test | pre-event VH -18 to -14 dB | 3,536,911 | 232,533 | 0.149 | 0.153 | 0.873 | 100.0% | 1,127,707 | 29,563 |
| M1-literal | test | pre-event VH -14 dB or above | 1,586,648 | 22,639 | 0.025 | 0.025 | 0.900 | 100.0% | 797,910 | 2,260 |
| M1-v2 (frozen) | development | pre-event VH below -22 dB | 646,970 | 14,871 | 0.123 | 0.852 | 0.125 | 29.6% | 324 | 13,007 |
| M1-v2 (frozen) | development | pre-event VH -22 to -18 dB | 2,400,426 | 174,415 | 0.527 | 0.869 | 0.572 | 48.6% | 14,976 | 74,677 |
| M1-v2 (frozen) | development | pre-event VH -18 to -14 dB | 4,004,530 | 209,719 | 0.535 | 0.676 | 0.719 | 52.4% | 72,127 | 58,942 |
| M1-v2 (frozen) | development | pre-event VH -14 dB or above | 2,129,170 | 14,654 | 0.091 | 0.096 | 0.674 | 59.5% | 93,309 | 4,777 |
| M1-v2 (frozen) | test | pre-event VH below -22 dB | 976,268 | 40,456 | 0.183 | 0.875 | 0.188 | 27.0% | 1,083 | 32,841 |
| M1-v2 (frozen) | test | pre-event VH -22 to -18 dB | 2,479,965 | 252,381 | 0.458 | 0.903 | 0.481 | 31.3% | 13,018 | 130,920 |
| M1-v2 (frozen) | test | pre-event VH -18 to -14 dB | 3,536,911 | 232,533 | 0.436 | 0.704 | 0.534 | 32.0% | 52,176 | 108,416 |
| M1-v2 (frozen) | test | pre-event VH -14 dB or above | 1,586,648 | 22,639 | 0.232 | 0.285 | 0.554 | 37.2% | 31,416 | 10,103 |

- **Already dark before the event (below -22 dB):** M1-v2 finds 19% of the
  mapped flood on the test split. A surface that was already dark cannot
  darken much, so change detection has little to work with.
- **Bright before the event (-14 dB or above):** precision of M1-v2 is
  0.285 on the test split. Most of what it flags there is not mapped flood.
- **Between -22 and -14 dB** the method does best: precision 0.70 to 0.90,
  recall about 0.5.

## Limits

- One event, one sensor pass pair, one mapping team. The split is spatial;
  the test tiles are neighbours of the development tiles and had been seen
  in an earlier exploratory diagnostic.
- The reference is drawn from the post-event pass itself. A method that
  thresholds that pass can agree with it for reasons that have nothing to
  do with water on the ground.
- The pooled score is carried by a few heavily flooded tiles. Tiles with
  little flood contribute mostly false alarms (M1-literal, Otsu comparator)
  or a declined answer (M1-v2).
- M1-v2 answers on a third of the test cells. A method that declines this
  often would fail the Mae Sai abstention condition if it behaved the same
  way there. Whether it does is plan task A4.
- The strict reading, which the selection rule maximises, rewards declining
  tiles with little flood. The headline strict IoU is therefore not a
  measure of how well the method maps flood where flood is sparse: on the
  seven test tiles with up to 5% mapped flood it gave no answer at all.
- The amended threshold rule declines where the flooded and the unchanged
  class overlap. That includes tile 50 with 13% mapped flood and tiles 38,
  41 and 48 with 3% to 4%. This is a property of the frozen method. It is
  recorded here and not corrected: a correction would be a new version (v3)
  and would need held-out data that has not been used.
- The pre-event image is four months older and from the opposite orbit
  direction. Mae Sai has a 12-day same-orbit pair, a monsoon landscape and
  steep terrain. Nothing here says how either method behaves there.
- The configuration was chosen among 36 runs on 15 tiles with a thin margin,
  after one amendment. The development figures are optimistic by
  construction; the test figures are the ones to quote.
- The only uncertainty estimate is the tile bootstrap and the
  leave-one-tile-out table of the held-out M1-v2 score, added after the
  score was seen. No other score has one.
- Four fields of the frozen configuration are names the code does not act
  on (see "Review corrections", item 6). The configuration SHA-256 alone
  does not pin the method.

## What could not be done, and why

- **Land-cover stratification of bidirectional change:** no land-cover layer
  for these tiles is on disk.
- **Slope or HAND mask:** no DEM for these tiles is on disk. The publisher's
  checksum list names `dem` and `permwater` folders for EMSR712-3; they were
  never downloaded, and this task downloads nothing. The owners may want to
  know that a DEM for these tiles exists upstream (decision D12).
- **Permanent-water removal inside the method:** no independent layer on
  disk; see the secondary comparison.
- **The proposal's full preprocessing chain (SNAP):** the tiles are already
  calibrated and geocoded by the publisher, and SNAP is not installed.
- **Boundary error in metres:** not computed; the edge-band stratum stands in.
- **Review by Rachmania:** not done yet. Decision R11 assigns the tuning to
  the agent "for Rachmania to review". The held-out scoring was run before
  that review. The held-out tiles are now used for this configuration. Any
  change to M1-v2 after this point is a new version, and its test score on
  these tiles would no longer be held out. See "Decisions for the owners".
- **RECEIPTS.jsonl:** the frozen configuration's SHA-256 is recorded in the
  freeze receipt and in this document, not yet in
  `docs/proposal_execution/RECEIPTS.jsonl`, which other lanes are editing.
- **Mae Sai, FPPS, A-E classes, ensembles:** out of scope by instruction
  (plan task A4; guardrail GR5, protocol v1b is not signed).

## Review corrections

A review on 3 October 2026 checked the code, the data and the plan. It
reports that a re-run with the frozen configuration reproduced every count
and candidate hash on all 29 tiles, and it found no wrong score. It found
nine defects in reporting, wording and provenance. Each was checked against
the files before it was acted on, and all nine were confirmed.

The declared protocol, the tuning log, the frozen configuration, its
receipt, the held-out summary and the two code modules named in the receipt
are bound to each other by SHA-256. They were not edited. Where one of them
is wrong or incomplete, the correction is in this document and in
[geoid_m1_benchmark_v2_addendum_1.json](geoid_m1_benchmark_v2_addendum_1.json),
which names the files it corrects by their hashes.

| # | Finding | What was done |
| ---: | --- | --- |
| 1 | The skill-bar verdict was a bare yes on a point estimate of 0.411 against 0.40 | Leave-one-tile-out figures and a tile bootstrap added beside the verdict; the verdict reworded; a derived file carries `robust: false` for later lanes |
| 2 | The Otsu comparator was shown only at the blocks chosen for Kittler-Illingworth | The brief, "Reading the tables" and the tuning table now say so, give the Otsu run that beat the frozen configuration on development (0.475) and show that most of the gain over M1-literal is declining. No further Otsu variant was scored on the test tiles |
| 3 | "Requiring both readings stops abstention from buying the bar" was false | Corrected here and in the addendum; the strict IoU is quoted with the share of cells without an answer in the headline tables and sentences |
| 4 | The tuning log and the freeze receipt lack confidence and assumptions | See the note below this table and the addendum; the tuning script writes the fields in any future session |
| 5 | The split attestations were constants, and the amendment check was not committed | The check was recomputed through a recording tile store and matches; the tuning script now writes what the store recorded. See "Order of work" |
| 6 | Four fields of the frozen configuration are names the code does not act on | Recorded as a limit; a guard, `require_frozen_m1_v2`, checks the configuration SHA-256 and both code SHA-256 values together |
| 7 | M1-literal adds a "below zero" clause the proposal does not contain | Stated in the brief and in "M1-literal as implemented"; the reading without the clause is reported for the development tiles only |
| 8 | Dice was missing from the tables; "27% to 31%" was a pooled figure, not the per-tile range | Dice added to both by-split tables; the sentence corrected to 25% to 44% per tile |
| 9 | The held-out scoring ran before Rachmania's review | Put first in "Decisions for the owners" |

**Tuning log and freeze receipt (finding 4).** Both files are bound by
hash and cannot take new fields. For
[geoid_m1_v2_tuning_log.jsonl](geoid_m1_v2_tuning_log.jsonl) (76 records,
72 of them sets of development scores) and
[geoid_m1_v2_freeze_receipt.json](geoid_m1_v2_freeze_receipt.json) the
following holds, and the addendum states it per file:

- Source timestamp: Sentinel-1 pass of 3 January 2024, 05:34:06 UTC.
- Confidence: low. One foreign event, a spatial split by tile, development
  tiles only. A development figure quoted from the log (for example 0.441 or
  0.475) is optimistic by construction, because the configuration was chosen
  on these tiles.
- Wording: every figure is agreement with a same-pass CEMS map, not
  independent accuracy.
- Assumptions: the tiles are linear sigma0 at 10 m with about 4.4 equivalent
  looks; the label was drawn from the post-event pass itself; mapped
  background is not confirmed dry land; permanent water in the label is
  modelled; no DEM, slope, HAND or land-cover layer was used; the two passes
  are almost four months apart and from different orbit directions.

**The configuration hash does not pin the method (finding 6).** The frozen
code never reads `kittler_illingworth_rule` or `isolated_speckle_cleaning`.
On the benchmark path the tile loader names the speckle filter and the
number of looks itself and ignores `speckle_filter` and `equivalent_looks`.
A configuration with another value in one of these fields would load, behave
the same and carry a different hash; a code change would alter the behaviour
under the same configuration hash. What pins the behaviour is the
configuration SHA-256 together with the two code SHA-256 values in the
freeze receipt:

- frozen configuration: `2bfcb0c6ebf4b79402afa63c56209f2c5cda26491f08883d67908195b6c64a68`
- `src/floodguard/sar_change_v2.py`: `3127b370303b08902dc545442f7aa5a2aa54d283b471c0d65f5899c9c19e1134`
- `src/floodguard/geoid_m1_benchmark.py`: `26d98f5cbdbcdcb1eeafe0b83a6e44b0ff4c9c7fb245078469952d95829e409f`

Plan task A4 must check all three before it runs M1-v2 on Mae Sai, by
calling `floodguard.geoid_m1_review.require_frozen_m1_v2`. Making the four
fields operative is a code change and belongs to a later version.

**Not done, and why.**

- The sentence "so abstaining cannot buy the bar" is still in the docstring
  of `clears_skill_bar` in `src/floodguard/geoid_m1_benchmark.py`. Editing
  that file changes its SHA-256, and that hash is one of the three that pin
  the method. The sentence is marked wrong here and in the addendum. If the
  owners prefer a corrected file, the change is one sentence and needs a new
  receipt entry that records the old and the new hash.
- The amendment check was not appended to the tuning log, because the log is
  bound by hash. Its recomputation is a separate file.
- The reading of M1-literal without the "below zero" clause was not scored
  on the test tiles. The held-out scoring is computed once. The owners can
  ask for it; it would be a second, disclosed pass over the test tiles for
  an untuned method.
- Rachmania's review outcome was not written to the decision log. That file
  belongs to another lane, and the review has not happened.

## Reproduce

Set `FLOODGUARD_EXTERNAL_DATA` to the external data root (the directory that
holds `geoid_flood/`), or pass `--external-data`.

- Tuning: `python scripts/tune_geoid_m1_v2.py`. It refuses to run now,
  because a frozen configuration exists.
- Held-out scoring: `python scripts/score_geoid_m1_benchmark.py`. It refuses
  to run now, because the summary exists. To check the numbers, delete
  `outputs/geoid_m1_benchmark_v2_summary.json` in a scratch checkout of the
  freeze commit and run it there; the result is deterministic.
- Derived checks: `python scripts/derive_geoid_m1_review_checks.py`. It
  reads the committed summary and tuning log only and writes the same bytes
  every time; `--check` compares the committed file with a fresh
  derivation.
- Amendment check: `python scripts/diagnose_geoid_m1_v2_amendment_check.py`.
  It opens the 15 development tiles only and first checks that the frozen
  files and both code modules match the freeze receipt.
- Tests: `pytest tests/test_sar_change_v2.py tests/test_geoid_m1_benchmark.py
  tests/test_geoid_m1_review.py`. They use synthetic arrays; two tests read
  a real development tile and are skipped when `FLOODGUARD_EXTERNAL_DATA`
  is unset.

## Files

| File | What it is |
| --- | --- |
| [geoid_m1_benchmark_protocol_v2.json](geoid_m1_benchmark_protocol_v2.json) | Declared benchmark protocol, with amendment 1 |
| [geoid_m1_v2_tuning_log.jsonl](geoid_m1_v2_tuning_log.jsonl) | Every tuning run of both sessions |
| [geoid_m1_v2_frozen_config.json](geoid_m1_v2_frozen_config.json) | Frozen configuration |
| [geoid_m1_v2_freeze_receipt.json](geoid_m1_v2_freeze_receipt.json) | SHA-256 of the configuration, of v1a, of the protocol, the log and the code |
| [../../../outputs/geoid_m1_benchmark_v2_summary.json](../../../outputs/geoid_m1_benchmark_v2_summary.json) | Full result: per tile, pooled, strata, input hashes, source timestamp, confidence, assumptions |
| [geoid_m1_benchmark_v2_addendum_1.json](geoid_m1_benchmark_v2_addendum_1.json) | Corrections after the review; the fields the log and the receipt lack; what a later lane must check |
| [../../../outputs/geoid_m1_benchmark_v2_derived_checks.json](../../../outputs/geoid_m1_benchmark_v2_derived_checks.json) | Leave one tile out, tile bootstrap, declined-tile accounting, Otsu across the grid, Dice. From committed counts only |
| [../../../outputs/geoid_m1_v2_amendment_check_reproduction.json](../../../outputs/geoid_m1_v2_amendment_check_reproduction.json) | The check behind amendment 1, recomputed on development tiles; M1-literal step 4 with and without the added clause |
| `src/floodguard/sar_change_v2.py` | M1-literal and M1-v2. Bound by the freeze receipt; unchanged since the freeze |
| `src/floodguard/geoid_m1_benchmark.py` | Split, loader, scoring, strata, freeze receipt. Bound by the freeze receipt; unchanged since the freeze |
| `src/floodguard/geoid_m1_review.py` | Review checks, the recording tile store, the guard `require_frozen_m1_v2` |
| `scripts/tune_geoid_m1_v2.py`, `scripts/score_geoid_m1_benchmark.py` | Thin runners |
| `scripts/derive_geoid_m1_review_checks.py`, `scripts/diagnose_geoid_m1_v2_amendment_check.py` | Review runners |

Attribution: modified Copernicus Sentinel-1 data (2023-2024); Copernicus
Emergency Management Service Rapid Mapping products, (c) European Union;
GEOID-Flood dataset, links-ads.

This benchmark is non-operational: `human_reviewed_by_floodguard=false`,
`accepted_observation=false`, `official_warning=false`,
`can_feed_decision_layer=false`.
