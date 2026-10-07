# THEOS-2 optical cross-check of the radar flood candidates: result

**What this is.** The first check of FloodGuard's radar flood candidates and of
its road-closure rule against an independent sensor: a THEOS-2 image at 0.5 m
that GISTDA provided for the hackathon. It is one chip of 9 km² at Sukhothai
from one event. It is a validation tile, not a study area: no FPPS, no A-E
class and no exposure or access figure is computed for it, and it is not an
official warning.

**How to read every figure.** The radar pass came 43.6 hours after the THEOS-2
image. Each figure is agreement between two sensors at two times. None is
accuracy.

- Plan, written before the comparison: `docs/proposal_execution/theos2_cross_check_plan_v1.md`
- Reference record: `outputs/theos2_cross_check/sukhothai_20250730_reference_v1.json`
- Result and receipt: `outputs/theos2_cross_check/sukhothai_20250730_v1.json`, `…_v1_receipt.json`
- Overview figure: `outputs/theos2_cross_check/sukhothai_20250730_v1_overview.png`
- Code: `src/floodguard/theos2_cross_check.py`, `scripts/build_theos2_radar_cross_check.py`
- Source timestamp: THEOS-2, 30 July 2025, 03:33 UTC. Confidence: low.

## Inputs

| | |
|---|---|
| THEOS-2 | `IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif`, pan-sharpened ortho, 4 bands, 0.5 m, 30 July 2025 03:33 UTC, "Disaster" sample. The valid imagery is one chip of 3 km by 3 km on the north side of Sukhothai town |
| Sentinel-1 | S1A, relative orbit 62, descending, terrain-corrected gamma0 at 10 m: before 19 July 2025 23:08 UTC, after 31 July 2025 23:08 UTC |
| Context | ESA WorldCover 2021 (permanent water, land cover), Copernicus DEM GLO-30 (slope), OpenStreetMap roads |

The three radar methods are the ones of the Mae Sai runs, unchanged: the
UN-SPIDER practice (quotient 1.25), M1-literal and the frozen M1-v2. Nothing
was tuned for this tile.

## The optical reference

Water on the THEOS-2 image is NDWI (green and near-infrared) at 2 m, above the
upper threshold of a three-class Otsu split (-0.045). The plan named the
two-class threshold (-0.14); on the image that value marks roads, roofs and
bare ground as water, so it was replaced once, before any radar candidate was
computed, as the plan allows. Cloud, large bright roofs and one corner of thin
cloud are unobservable. Water objects under 1,000 m² are dropped (mostly
roofs).

On the 10 m radar grid, 80,988 cells are compared (8.10 km², outside permanent
water). 29,298 of them are wet on the THEOS-2 image (2.93 km², 36%).

## Result 1: the radar candidates against THEOS-2 water

| Method | Candidate cells that are optical water (precision) | Optical water the method flags (recall) | IoU | Cells with an answer |
|---|---:|---:|---:|---:|
| UN-SPIDER reproduction | 0.72 | 0.29 | 0.26 | 100% |
| M1-literal | 0.61 | 0.50 | 0.38 | 100% |
| M1-v2 (frozen) | 0.76 | 0.22 | 0.21 | 99.3% |

In cropland, which holds 87% of the optical water: precision 0.79, 0.74 and
0.83; recall 0.30, 0.52 and 0.24. In built-up cells the image shows almost no
standing water (0.02 km²), and most radar candidates there are not water on
the image (precision 0.16, 0.06 and 0.18).

What this says:

1. **Where the methods flag water, the image mostly agrees.** Six to eight of
   ten flagged cells are water on the THEOS-2 image.
2. **They miss most of the water the image shows.** Between half and
   three-quarters of the optical water is not flagged. Three causes are likely
   and were not separated: water that drained in the 44 hours between the two
   acquisitions; water standing under rice and other plants, which does not
   darken the radar signal; and fields that already held water on 19 July (a
   change method cannot see water that was there before).
3. **M1-v2 answered here.** At Mae Sai it gave no answer for 77% of the cells.
   On this lowland tile it answered 99.3%, and it is the most cautious of the
   three.
4. **Built-up ground stays a blind spot** for all three, as the proposal's
   risk table expected.

## Result 2: the road-closure rule against roads seen under water

857 road edges (43.9 km) have a centreline that the image shows. On 52 of them
(3.3 km) at least 20 m of the centreline lies on optical water: these are
"seen under water".

**The rule, given a good flood extent.** With the THEOS-2 wet cells (at 10 m)
as the flood extent, closure rule v1 was compared with those 52 edges:

| Level | Edges the rule closes | Of those, seen under water | Of the 52 seen under water, closed by the rule |
|---|---:|---:|---:|
| Strict | 42 | 88% | 71% |
| Central (used for the planning scores) | 50 | 82% | 79% |
| Permissive (any intersection) | 102 | 48% | 94% |

The central level closes about the right roads: four of five closures are
roads under water on the image, and it finds four of five flooded roads. The
permissive level closes twice as many roads as the image shows under water.
Roads on embankments cross flooded fields and stay dry, and "any intersection"
does not know that. This test uses one water map on both sides, so it tests
the rule and the 10 m cell size, not the water map.

**The rule, given a radar candidate.** With a radar candidate as the flood
extent, at the central level:

| Flood extent | Edges the rule closes | Of those, seen under water | Of the 52 seen under water, closed |
|---|---:|---:|---:|
| UN-SPIDER reproduction | 50 | 8% | 8% |
| M1-literal | 157 | 16% | 48% |
| M1-v2 | 37 | 5% | 4% |

A 10 m radar candidate does not say which road is under water. It flags open
fields, and the closure rule then closes the field roads that run through
them, while the flooded roads lie mostly in cells the radar does not flag.

## What follows for the project

- **The planning scores are right to use an agency flood extent and not our
  own radar candidate.** The proposal says: use a qualified external extent
  where there is one, otherwise a Sentinel-1 candidate with low confidence. On
  this tile a radar candidate cannot carry a road-level statement. That
  supports keeping own-radar cases at low confidence, which gives class E.
- **The closure rule has its first outside check.** At the central level it
  agrees with what a 0.5 m image shows for about four roads in five, on 52
  flooded edges of one scene. The permissive level should be read as an upper
  bound.
- **The season-envelope scenario (case SE1) needs the same care.** Its Ko
  Chang result rests on modelled closures. This check suggests that the
  central level is a fair reading when the extent is good; it does not check
  the Mae Sai extent or the Mae Sai roads.
- **For GISTDA: THEOS-2 can do what Sentinel-1 cannot.** One 0.5 m image shows
  which road is under water. A THEOS-2 acquisition over Mae Sai exists for
  16 September 2024, 03:36 UTC, 4 hours 20 minutes after the Sentinel-1 pass
  the project uses (`docs/proposal_execution/automated_track/independent_evidence_candidates_v2.md`).
  With that scene the same check could be made on the study area itself.

## Limits

- One chip, one event, 52 flooded road edges. No method is selected or tuned
  on it, and it qualifies no candidate for Mae Sai. The skill bar of protocol
  v1a is unchanged.
- The optical water is a rule on four uncalibrated bands, checked by eye, not
  on the ground. It shows water, not flood: paddy water counts.
- Tree crowns and roofs hide roads, and OpenStreetMap centrelines can lie
  metres off. "Seen under water" is an under-count.
- The radar input is gamma0 where the Mae Sai runs used sigma0. The before
  image was assumed free of flood water.
- The THEOS-2 file is a 15.9 km canvas of no-data around the 3 km chip. The
  footprints in `outputs/theos2_local_metadata_manifest.csv` describe the
  canvas.

## Credits

THEOS-2 imagery © GISTDA, sample provided for GeoHackathon 2026; the imagery
is kept outside Git. Contains modified Copernicus Sentinel data 2025. ESA
WorldCover 2021 v200 (CC BY 4.0). Copernicus DEM GLO-30. Roads © OpenStreetMap
contributors (ODbL 1.0).

## To run it again

```bash
python scripts/build_theos2_radar_cross_check.py reference --theos2 <downloads>/IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif --work-dir <external-data-root>/theos2_cross_check/sukhothai_20250730_v1 --replace
```

```bash
python scripts/build_theos2_radar_cross_check.py compare --work-dir <external-data-root>/theos2_cross_check/sukhothai_20250730_v1 --osm-pbf <external-data-root>/open_context/osm_geofabrik/thailand-latest.osm.pbf --replace
```

The comparison is run once (plan, section 6). A second run needs `--replace`
and `--reason`. Both stages were run twice on 7 October 2026: the first records
were written with CRLF line ends, so their SHA-256 values did not hold for the
bytes Git stores. The second run writes LF bytes; every figure is the same
(`supersedes` in each record).
