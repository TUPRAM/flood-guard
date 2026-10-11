# Buildings in the water against residents in the water

Report-only, 11 October 2026. No published figure changes.

Plan: `docs/proposal_execution/buildings_in_water_plan_v1.md`.
Records: `outputs/buildings_in_water/` (`outlines_v1.json`,
`theos2_chips_v1.json`, `se1_mae_sai_v1.json`).

## The question

The planning score counts "residents in the water" from a population grid: a
cell of about 100 m counts as flooded, with all its modelled residents, when
its centre lies in the flood layer. For case SE1 that is 17,927 residents,
22 percent of Mae Sai district. People live in buildings, not at cell
centres, and the count had never been set against buildings.

## The outlines

Building outlines from Google Open Buildings v3 and Microsoft, combined by
VIDA and hosted by Source Cooperative (open licences; the credit is at the
end). Only the outlines of three areas were read; they stay outside Git.

| Area | Outlines read | Used (10 m² or more; confidence 0.70 or more where given) |
|---|---:|---:|
| Sukhothai chip | 3,049 | 2,718 |
| Chip of the flooded town | 5,784 | 5,106 |
| Bounding box of Mae Sai district | 133,374 | 115,897, of which 88,942 lie in a cell of the district |

A model drew them on satellite images of earlier years. They are not a
survey and not a register of dwellings: a shed, a shop and a temple count
like a house.

## Case SE1: the main finding

**Where a cell holds a building, the centre rule is sound.** On those cells
the centre rule puts 19.3 percent of residents in the water and the buildings
put 18.2 percent. No tambon differs by more than 5 points.

**But the grid puts 39 percent of the district's residents in cells that
hold no building at all**, and those cells lie in the flood layer more often.
Every one of the 36,765 cells of the district holds residents, the smallest
a quarter of a person: the grid spreads people over fields. Of the 31,585
residents in cells without a building, 26 percent are in the water by the
centre rule.

| Tambon | Buildings | Buildings in the layer | Residents in the water (published, centre rule) | Residents in cells without a building |
|---|---:|---:|---:|---:|
| Mae Sai | 15,168 | 52% | 56% | 20% |
| **Ko Chang** | 10,937 | **15%** | **37%** | 60% |
| **Si Mueang Chum** | 6,629 | **11%** | **43%** | 65% |
| **Ban Dai** | 5,042 | **6%** | **19%** | 70% |
| Pong Pha | 14,821 | 5% | 10% | 46% |
| Pong Ngam | 9,368 | 1% | 5% | 50% |
| Wiang Phang Kham | 17,340 | 0.1% | 0.4% | 18% |
| Huai Khrai | 9,637 | 0% | 0% | 49% |
| **District** | 88,942 | **13%** | **22%** | 39% |

In the town (Mae Sai tambon) the two agree: about half of the buildings and
of the residents are in the layer. In the three rural tambons along the
river the published share of residents in the water is two to four times the
share of buildings in the layer.

With the narrower and the wider flood layer of the ensemble the picture is
the same: 12, 13 and 15 percent of buildings against 20, 22 and 24 percent of
residents.

**One figure computed after the result was seen, and not in the plan.** If
the residents of each tambon stood where the buildings of that tambon stand,
about 12,000 residents (15 percent) would be in the layer, not 17,900
(22 percent). It shows how much the count depends on where the grid puts
people. It is not a second exposure count.

### What this means, and what it does not

- The published "residents in the water" is likely too high in Ko Chang,
  Si Mueang Chum and Ban Dai, because the grid counts people in flooded
  fields where no building stands.
- It does not show that the buildings in the layer were flooded. There is no
  image in this comparison.
- It was not computed whether the residents who would leave "in the water"
  are then "dry with every road cut". The need mix of those tambons rests on
  the same grid.
- No class was recomputed. Exposure is one of five components of the score.
- **The planning score keeps the centre rule.** Whether a later run should
  spread residents over buildings is for the owners to decide. A report-only
  run of the need mix and of the ensemble with such a demand is possible
  with what is now on disk.

## On two THEOS-2 images: buildings that stand in water

A roof is not water also when the house stands in a metre of it, so a
building is judged by the ground around it: it is in the water when at least
half of the ground 2 to 8 m from its outline is water in the image. Both
water rules are given; neither has been scored on the test points yet.

| Chip | Water rule | Buildings assessed | In the water | Residents in the water: centre rule | by area | by buildings |
|---|---|---:|---:|---:|---:|---:|
| Flooded town | v1 | 3,862 | 1,017 (26%) | 33% | 33% | 26% |
| Flooded town | v2 | 4,094 | 956 (23%) | 29% | 31% | 23% |
| Sukhothai | v1 | 1,848 | 39 (2%) | 9% | 8% | 2% |
| Sukhothai | v2 | 2,121 | 263 (12%) | 25% | 22% | 14% |

- **About a thousand buildings stand in water in the flooded town**, a
  quarter of those that could be judged, by either rule.
- **The buildings reading is lower than the centre rule on both chips and by
  both rules**, by 6 to 12 points: the same direction as in case SE1.
- At Sukhothai the two water rules disagree sixfold. Rule v2 marks roads and
  concrete as water in the town in the south of the chip
  (`docs/theos2_water_rule_v2.md`), which is exactly the ground around
  houses, so its 263 is probably too high. Rule v1 set much of the same town
  aside. This count waits for the test of the two rules.
- Between 15 and 26 percent of the buildings could not be judged: ring under
  cloud or set aside.
- Tree crowns hide water and count as not water, so buildings in the water
  are under-counted where houses stand under trees.

## Limits

- One model against another: outlines drawn by a model, residents spread by
  a model. Neither is a count of people.
- The outlines are of earlier years; buildings put up or washed away since
  are wrong in them.
- A confidence cut of 0.70 leaves out 13 percent of the outlines of the
  district. With a lower cut there would be more buildings, also in fields.
- The chips are not Mae Sai. When GISTDA's images of Mae Sai arrive, the
  count of buildings in the water can be made there; that needs an amendment
  of the plan for those images.

## Credits

Building outlines: Google Open Buildings v3 (CC BY 4.0) and Microsoft
building footprints (ODbL), combined by VIDA and hosted by Source
Cooperative. Residents: WorldPop (CC BY 4.0). Flood layer: UNOSAT and GISTDA,
FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0), changed by FloodGuard.
THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026.
