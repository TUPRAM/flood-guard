# Radar candidates against the dated agency layer of 22 October 2024 at Mae Sai: plan v1

Written on 9 October 2026, before any radar candidate was computed for October
2024 and before the dated layer was set against any radar cell. Work package 3
of the order the team accepted (item V-15); its result becomes item V-17.

## 1. Question

At Mae Sai itself, on a date for which an agency published a single-date flood
layer, how do FloodGuard's three radar methods compare with that layer?

Until now the methods were compared at Mae Sai only with a season layer
(a scenario with no date) and, on a tile at Sukhothai, with a THEOS-2 image.
This is the first comparison on the study district with a dated reference.

## 2. What it is not

- Not a test of the September 2024 flood. The layer of 22 October is
  late-season residual water, 3.7 km² in the district.
- Not accuracy. The reference is an agency layer that was not checked in the
  field (`Field_Validation = 0`). Every figure is agreement with it.
- Not independent of our radar. The Sentinel-1 pass used here was taken on
  21 October at 23:16 UTC, which is 22 October 06:16 in Thailand. The agency
  layer is dated 22 October and its sensor code (42) is not explained in the
  file. It may have been made from this same pass. If so, the figures say how
  our methods read the same radar picture as the agency did.
- No planning score, no class, no exposure or access figure is computed, and
  nothing here is an official warning.

## 3. Inputs

| | |
|---|---|
| Reference | UNOSAT and GISTDA, FL20240912THA (UNOSAT product 4009), layer `CHIANGRAI_20241022_FloodExtent`, as provided, geometry repaired |
| Radar, after | Sentinel-1A, relative orbit 135, descending, terrain-corrected gamma0 at 10 m (Microsoft Planetary Computer, collection `sentinel-1-rtc`): `S1A_IW_GRDH_1SDV_20241021T231602_20241021T231627_056207_06E178_rtc` |
| Radar, before (primary) | Same orbit, 22 August 2024: `S1A_IW_GRDH_1SDV_20240822T231600_20240822T231625_055332_06BF48_rtc` |
| Radar, before (second reading) | Same orbit, 12 April 2024, dry season: `S1A_IW_GRDH_1SDV_20240412T231601_20240412T231626_053407_067A69_rtc` |
| Context | ESA WorldCover 2021 v200 (permanent water, land cover), Copernicus DEM GLO-30 (slope), HDX COD-AB boundaries (Mae Sai district, TH5709) |

**Why 22 August as the image before.** The runs of record for September used
the pass of 3 September 2024. The open terrain-corrected catalogue does not
hold that pass for the frame over Mae Sai. 22 August is the last pass of the
same orbit before the September flood that it does hold.

**Why a second reading.** August 2024 was already wet at Mae Sai, and rice
fields change between August and October. Water that stood on 22 August
cannot show as a change. The dry-season image of 12 April is therefore run as
a second reading. Both readings are reported in full. The primary reading is
named here and is not changed after the results are seen.

## 4. Method

1. **Grid.** The 10 m lattice of the radar runs (EPSG:32647), over the lattice
   tiles that the district of Mae Sai touches.
2. **Compared cells.** Cells whose centre lies in the district, outside
   permanent water (WorldCover class 80), with a valid radar value in the
   image after.
3. **Reference cells.** A compared cell is "agency water" when its centre lies
   inside the dated layer. A second count leaves out cells at the edge of the
   layer (any of the eight neighbours differs).
4. **Radar candidates.** The three methods of the Mae Sai runs, unchanged and
   with their recorded parameters: the UN-SPIDER practice, M1-literal and the
   frozen M1-v2. Nothing is tuned for this date.
5. **Figures, per method and reading.** Cells flagged; of those, the share
   that is agency water; of the agency water, the share flagged; intersection
   over union; the share of cells with an answer. The same by land cover
   (built-up, cropland, tree cover, other).
6. **Context figures.** How much of the dated layer in the district lies
   inside the season layer; how many agency-water cells are permanent water
   and so not compared.

## 5. How the result will be read

No threshold decides a pass. The result is written as counts and shares, with
these sentences fixed beforehand:

- If a method flags less than a tenth of the agency water in both readings,
  the text says that the method does not see the residual water of that date.
- If the two readings differ by more than a factor of two in the share of
  agency water flagged, the text says that the choice of the image before
  decides the result, and that neither reading is preferred after the fact.
- Whatever comes out, the radar candidates stay outside every planning score.

## 6. Rights and where things are kept

The dated layer belongs to product 4009 (CC BY-SA 4.0). The project's rights
record names the season layer only; every other layer of the archive is held
at the `local` level (owner sheet, question Q6, not answered). In line with
what plan tasks E1 and E5 do for local-level inputs:

- the rasters, the figure and any table by tambon stay outside Git;
- the result and receipt in Git hold whole-district counts and shares, and say
  so;
- nothing is written under `apps/web/public/`.

Mueang Chiang Rai and Phan are reserved for cases SE2 and SE2-blind and are
not read here: the frame is Mae Sai district only.

## 7. Order of work and what was already seen

1. This plan is committed.
2. Stage `reference`: the grid, the compared cells and the reference cells,
   from the layer and the context alone. Its record is committed.
3. Stage `compare`: the radar is fetched and the candidates computed, once.
   A second run needs `--replace` and a reason, and the first stays in the
   record.

**Seen before this plan was written.** While planning, the area of the dated
layer was summed by district for the whole province (58.4 km² in all, 3.7 km²
in Mae Sai, and 3.3 and 0.5 km² in the two reserved districts), and the share
of the layer inside the season layer (57.9 of 58.4 km²). The catalogue was
listed to find the passes. No location of the layer was looked at and no
radar value was read.

## 8. Limits known beforehand

- One district, one date, 3.7 km² of reference water.
- Residual water in October is mostly shallow water on fields; the agency's
  own method and sensor are not documented in the file.
- The layer has no "not observed" class: where the agency did not map water,
  the cell counts as dry.
- The image before and the image after are 60 days (primary) or 192 days
  (second reading) apart; crops and soil moisture change in between.
