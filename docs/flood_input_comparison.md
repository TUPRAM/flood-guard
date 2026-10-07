# How the decision inputs of Mae Sai change with the flood input: result

**What this is.** The same roads, residents and closure rule, read under five
flood inputs: the 2024 season layer of UNOSAT and GISTDA (twice) and the
project's three radar candidates for the Sentinel-1 pass of 15 September 2024.
It answers the question "what would change if we read our own radar and not the
agency layer?". It counts land, residents and road edges. It computes no part
of the planning score, no score and no action class, and it is not an official
warning.

**How to read it.** No input is a reference for another. The season layer
holds every area mapped as water between August and October 2024. A radar
candidate describes one pass, 3.8 days after the modelled peak, and is an
unqualified own candidate. A difference between two inputs is not an error of
either.

- Plan, committed before the run: `docs/proposal_execution/flood_input_comparison_plan_v1.md`
- Result and receipt: `outputs/flood_input_comparison/mae_sai_v1.json`, `…_v1_receipt.json`
- Code: `scripts/build_flood_input_comparison.py`, `src/floodguard/flood_input_comparison.py`
- Source time: season layer 1 August to October 2024; radar pass 15 September 2024, 23:16 UTC. Confidence: low.

**Check on the method.** Run on the whole routing corridor, the script
reproduces the committed table of the SE1 run of record to the last resident,
at all three closure levels. It writes nothing unless it does.

## The five inputs

| Name | What it is |
|---|---|
| Season layer, whole corridor | The input of the SE1 result: the season layer over the whole routing corridor |
| Season layer, district only | The same layer inside the eight tambons. The radar rasters cover only the eight tambons, so this is what a radar input is set beside |
| UN-SPIDER | The UN-SPIDER recommended practice, quotient 1.25 |
| M1-literal | The literal change method |
| M1-v2 | The frozen second version. It gives an answer for 22.7% of the district and none for the rest |

The radar rasters are those of the height-aware run of 4 October 2026, which
places the layers within about 10 m. Flood cells become polygons, and polygons
under 5 cells are dropped, as protocol v1b says for a raster.

## Result 1: the whole district, central closure level

The district has 81,837 modelled residents. Before any flood, 74,597 reach a
hospital within 30 minutes by vehicle and 75,171 have a road route.

| Flood input | Flooded land | Residents inside the extent | Road edges closed | Newly lose the hospital within 30 min | Lose every route |
|---|---:|---:|---:|---:|---:|
| Season layer, whole corridor | 77.2 km² | 17,930 | 7,926 | 24,510 | 21,800 |
| Season layer, district only | 77.2 km² | 17,930 | 5,372 | 23,740 | 21,710 |
| UN-SPIDER | 8.3 km² | 1,030 | 149 | 1,370 | 730 |
| M1-literal | 115.6 km² | 32,860 | 13,475 | 74,070 | 66,810 |
| M1-v2 | 3.0 km² | 370 | 27 | 700 | 210 |

**The flood input moves the answer by more than two orders of magnitude.**
Residents who lose every route: about 210 under M1-v2, 21,700 under the season
layer, 66,800 under M1-literal.

**The closure level moves it far less.** Under the season layer, residents who
lose every route are 21,330 at the strict level and 22,110 at the permissive
level. Which flood map is read matters much more than how the road rule is
set.

## Result 2: each radar input beside the season layer (district only)

| | UN-SPIDER | M1-literal | M1-v2 |
|---|---:|---:|---:|
| Flooded land, as a share of the season layer's | 11% | 150% | 4% |
| Closed road edges: in both / radar only / season layer only | 148 / 1 / 5,224 | 2,174 / 11,301 / 3,198 | 27 / 0 / 5,345 |
| Do the eight tambons come in the same order by flooded land? (rank correlation) | 0.86 | -0.05 | 0.39 |
| …by residents inside the extent? | 0.86 | -0.36 | 0.27 |
| …by residents who lose every route? | 0.80 | 0.12 | 0.10 |
| Tambon with most residents losing every route | Si Mueang Chum (370) | Wiang Phang Kham (16,360) | Si Mueang Chum (180) |

Under the season layer that tambon is Mae Sai (11,610).

What this says:

1. **UN-SPIDER sees the same places, much smaller.** It orders the tambons
   much as the season layer does and nearly every road it closes is also
   closed under the season layer (148 of 149), at about a thirtieth of the
   residents. That is what residual water days after the peak would look
   like. It cannot be told from an under-detection on these figures.
2. **M1-literal would send help to the wrong places.** It marks 38% of the
   district as flooded, including Huai Khrai (41%) and Wiang Phang Kham (46%),
   which the season layer shows almost dry. Its order of tambons has nothing
   in common with the season layer's.
3. **M1-v2 is silent where it matters.** It answers for less than a quarter of
   the district and marks no water in Mae Sai town or Ko Chang.

## Result 3: Ko Chang, the lead result of case SE1

Residents of Ko Chang who lose every route, of 5,972 who have one:

| Season layer, whole corridor | Season layer, district only | UN-SPIDER | M1-literal | M1-v2 |
|---:|---:|---:|---:|---:|
| 5,972 | 5,933 | 262 | 5,933 | 0 |

**Ko Chang's isolation does not depend on water outside the district.** With
the season layer cut to the eight tambons, 5,933 of 5,972 still lose every
route. For Ban Dai it is different: residents who newly lose the hospital fall
from 2,650 to 1,890 when water outside the district is left out.

**It does depend on the flood input.** The class B of Ko Chang in case SE1 is
a statement about the season layer. Under the radar pass of 15 September, as
UN-SPIDER reads it, 262 residents of Ko Chang lose every route.

## What follows for the project

- **The evidence gate is doing real work.** If the project read M1-literal as
  the flood, it would report three times the isolation and a different first
  tambon. If it read M1-v2, it would report almost none. The proposal says
  that an unqualified model output must not become a recommendation; these
  counts show what would happen if it did.
- **What the rule says of our own radar is already recorded.** None of the
  three candidates meets the skill bar of protocol v1a
  (`outputs/planning_v1/radar_o1_mae_sai_v1.json`). Under confidence rule v1
  an input like that has low confidence, and low confidence gives class E,
  monitor and verify, whatever the counts are. Class E never means safe.
- **The flood input is the main uncertainty of the chain**, ahead of the
  closure level. That is where a dated reference for September 2024 would
  help most: the THEOS-2 scene of 16 September 2024 and the GIS data of UNOSAT
  product 3991, both asked for on 7 October.
- **Say "scenario" with the Ko Chang result.** It holds for the season layer,
  inside the district and over the corridor. It was not seen in the one radar
  pass the project has.

## What this is not

- **Not case O1.** Protocol v1a names a case for the project's own radar. It
  needs a confirmed rights record for the Sentinel-1 data in the rights
  registry, and runs of plan tasks E1, E5 and E8 for each candidate. None of
  that was done, the registry is untouched, and no result of this file is on
  a page.
- **Not a check against the ground.** Nothing here was compared with what
  happened.
- A radar cell with no answer closes no road here. For M1-v2 that is 77% of
  the district.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed
by FloodGuard: repaired, projected, clipped and set against roads and
residents; the figures derived from it are shared under CC BY-SA 4.0. Contains
modified Copernicus Sentinel data 2024. Roads and hospitals © OpenStreetMap
contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0). Land cover: ESA
WorldCover 2021 v200 (CC BY 4.0).

## To run it again

```bash
python scripts/build_flood_input_comparison.py --external-root <external-data-root> --replace --reason "<why>"
```

It takes about 40 minutes. The run of 7 October 2026 was made twice: the first
result gave no skill-bar outcome and an answered share slightly above one; the
second corrects both fields and changes no count (`supersedes` in the result).
