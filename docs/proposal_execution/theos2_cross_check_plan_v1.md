# THEOS-2 optical cross-check of the radar flood candidates: plan v1

**Status: plan, written and committed before any radar candidate was computed
for this tile and before any comparison was made.** It follows the proposal's
rule of pre-specification (section 3.6.5). The result is report-only. It
computes no FPPS, no A-E class, no exposure and no access figure for any place,
and it is not an official warning.

- Written: 7 October 2026.
- Lane owner: Rachmania (remote sensing). Drafted by the AI coding agent under
  decision-log row R20; the owners can overturn it.
- Proposal scope: the data table gives THEOS-2 the role "high-resolution
  built-up extraction and urban validation", and the risk table answers urban
  radar false positives with "cross-check with THEOS-2 or Charter products
  where available". Mentoring Session I asked whether that use includes direct
  flood-map validation, and whether the road-disruption method was tested
  against independent passability information. This plan answers both with the
  THEOS-2 imagery the organisers provided.

## 1. Why this tile

None of the THEOS-2 sample scenes covers Mae Sai, Hat Yai or the two lower
Chao Phraya study areas (`docs/theos2_inventory.md`). One sample of the
"Disaster" category does show a flood: `IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif`,
acquired on 30 July 2025 at 03:33:31 UTC (10:33 in Thailand) over Sukhothai,
during the flooding that followed
Tropical Storm Wipha, which the proposal cites in section 1.2.2. Its SHA-256 is
recorded in `outputs/theos2_selected_file_manifest.csv`. The file is a 15.9 km
canvas of no-data around one chip of 3 km by 3 km (about 9 km², 99.786 to
99.814 E, 17.010 to 17.037 N); the comparison is made on that chip.

The tile is a **validation tile, not a study area**. Nothing is ranked or
scored there. Decision D11 (scope freeze) stays as it is for study areas.

## 2. Inputs, fixed here

| Input | Identity | Use |
|---|---|---|
| THEOS-2 PMS ortho, 0.5 m, 4 bands | the file above, kept outside Git | optical water at 30 July 2025, 03:33 UTC |
| Sentinel-1A IW GRD, terrain-corrected gamma0 (RTC), 10 m, from the Microsoft Planetary Computer | before: `S1A_IW_GRDH_1SDV_20250719T230832_…_060159_rtc`; after: the two frames of 31 July 2025, 23:08 UTC (`…20250731T230828…` and `…20250731T230853…_060334_rtc`), relative orbit 62, descending | the image pair of the three candidates |
| ESA WorldCover 2021 v200 | tile N15E099 | permanent water (class 80) and land-cover strata |
| Copernicus DEM GLO-30 | tiles N16E099 and N17E099 | slope for the UN-SPIDER rule |
| OpenStreetMap | the Geofabrik Thailand extract already used by the project | road centrelines |

The before image is the last pass of the same satellite on the same orbit
before Wipha's landfall. Whether the ground was free of flood water on 19 July
was not verified.

The after image was acquired **43.6 hours after** the THEOS-2 scene. Water may
have risen or fallen in between. Every figure of the result is therefore
"agreement with THEOS-2 optical water 44 hours earlier", never accuracy.

## 3. The radar side: nothing is tuned

The three candidates of plan tasks A2 and A4 are applied exactly as they were
at Mae Sai, with the functions of `floodguard.radar_candidates`:

1. the UN-SPIDER recommended practice (VH, quotient 1.25, 8 connected cells,
   slope below 5 degrees);
2. M1-literal with its default configuration;
3. M1-v2 with the frozen configuration that `geoid_m1_review.require_frozen_m1_v2`
   returns, tile by tile on the 10.24 km lattice.

No threshold, filter or rule of any method is changed for this tile, before or
after the result is seen.

**One declared deviation.** At Mae Sai the input was sigma0 from the SAFE
calibration table. Here it is terrain-corrected gamma0, because that product is
hosted with open access and is placed on the ground more exactly. M1-literal
and M1-v2 work on differences in dB between two passes of the same orbit, where
the two radiometries differ by a term that cancels. The UN-SPIDER practice
divides two dB values, so its quotient moves slightly (in the second decimal
for typical VH values). The result states this.

## 4. The reference side: THEOS-2 water, built without looking at the radar

1. Read the scene at 2 m by averaging 4 by 4 pixels.
2. Water index: NDWI = (green - NIR) / (green + NIR) on the digital numbers.
3. A pixel is unobservable when it has no data, lies in cloud, or lies in a
   deep shadow where the index cannot be read.
4. The water threshold on NDWI is set by Otsu's method on the observable
   pixels. The cloud and shadow limits are set by eye on the THEOS-2 image
   alone. All three are fixed, and written into the run receipt, **before the
   radar candidates of this tile are computed**. If the automatic threshold is
   visibly wrong on the image, it may be replaced once at this stage, and the
   receipt says so and why.
5. Put on the 10 m radar grid: the share of observable 2 m pixels that are
   water. A 10 m cell is observable when at least 90% of its 2 m pixels are.
   It is **wet** at a share of 0.5 or more and **dry** below it.
6. Cells of WorldCover class 80 (permanent water) are left out of every flood
   figure and counted on their own.

## 5. Figures reported, fixed here

For each method, over the THEOS-2 footprint:

- cells with an answer, and cells without one by reason;
- true and false positives and negatives against wet and dry;
- IoU, precision, recall and F1 in two readings, as in the GEOID benchmark:
  on the cells the method answered, and strictly (a cell without an answer
  counts as "not a candidate");
- candidate area and THEOS-2 wet area on the compared cells;
- the same counts by land cover (built-up, cropland, tree cover, other);
- a second reading that leaves out mixed cells (water share between 0.1 and 0.9).

**Road check.** For every OpenStreetMap road edge of the classes the project
routes on, inside the observable footprint:

- observed: the length of its centreline that lies on THEOS-2 water at 2 m;
  the edge counts as **seen under water** at 20 m or more, and an edge shorter
  than 40 m also at half its length or more (an edge is the piece between two
  consecutive vertices of a way, and many are shorter than 20 m);
- an edge is compared when at least 90% of its centreline lies on observable
  pixels;
- modelled: its state under closure rule v1, central level, with each radar
  candidate as the flood extent, and once with the THEOS-2 wet cells (10 m) as
  the flood extent;
- reported: how many edges the rule closes that THEOS-2 does not show under
  water, and how many it leaves open that THEOS-2 shows under water. The run
  with the THEOS-2 extent tests the rule itself: a road on an embankment can
  cross flooded fields and stay dry.

Tree crowns and buildings hide a road surface, and an OpenStreetMap centreline
can lie a few metres off the road. Both make "seen under water" an
under-count. The result says so.

## 5a. What was read before this plan was committed

- The THEOS-2 chip was looked at, and the water, cloud and object rules of
  section 4 were tried on it, on 7 October 2026. That is the reference stage,
  and it used no radar data.
- One coverage check read the VH windows of five Sentinel-1 passes over the
  chip and printed, for each, the share of valid cells and the median
  backscatter. It showed that the pair of section 2 covers the whole chip (the
  after image as two frames of one pass). No candidate, no change image and no
  comparison was computed.

## 6. What the result may and may not be used for

- It may be cited as the project's first check of its radar candidates against
  an independent sensor, with the 44-hour gap stated each time.
- It does not qualify any candidate for Mae Sai. The T2 skill bar of protocol
  v1a and its Mae Sai conditions are unchanged, whatever the figures are.
- No method is selected, tuned or promoted on this tile. It is one event and
  one scene.
- A poor or a missing figure is reported as it is.

## 7. Outputs

- `outputs/theos2_cross_check/sukhothai_20250730_v1.json`: the figures, with
  `generated_at_utc`, `source_timestamp`, `confidence_class`, `assumptions`,
  `limits`, `official_warning: false` and `operational_status: non_operational`.
- A receipt with the SHA-256 of every input and of this plan.
- One small overview figure. The THEOS-2 imagery itself stays outside Git.
- `docs/theos2_radar_cross_check.md`: the result in plain words.
