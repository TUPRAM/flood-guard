# What is under a class: the need mix inside each tambon of case SE1

**What this is.** A planning class is one letter for a whole tambon. Inside a
tambon the residents do not all fare alike in the scenario: some are in the
water, some stay dry and lose every road, some keep a road and lose the
hospital. This page counts them, tambon by tambon, and shows where each kind
sits on squares of 500 m.

**How to read it.** Report-only. **A need type is not a planning class**: it
uses no score, no threshold of the class rule and no confidence, and it
changes no class. The binding class of each tambon is the one of the
published result. The case is a scenario (every area mapped as flooded between
1 August and 12 October 2024, taken at once), not a flood of any day; closures
and residents are modelled; nothing was checked on the ground. A square or a
cell says nothing about a household. It is not an official warning.

- Result: `outputs/need_mix/se1_mae_sai_v1.json`
- Squares: `outputs/need_mix/se1_mae_sai_squares_500m_v1.json`
- Picture: `outputs/need_mix/se1_mae_sai_need_map_v1.png`
- Code: `src/floodguard/need_mix.py`, `scripts/build_cell_outcomes.py`,
  `scripts/build_need_mix.py`, `scripts/build_need_map.py`
- Source time: season layer of 1 August to 12 October 2024; residents of 2020.
  Confidence: low.

![The need map of Mae Sai district](../outputs/need_mix/se1_mae_sai_need_map_v1.png)

## The kinds

Every 100 m cell takes the first kind that fits, so each resident is counted
once.

| Order | Kind | What it means |
|---:|---|---|
| 1 | In the water | The centre of the cell lies inside the flood layer |
| 2 | Dry, every road cut | Outside the layer; had a road route to a hospital or a main road, and has none in the scenario |
| 3 | Dry, hospital out of reach | Outside the layer, still with a road route; reached a hospital within 30 minutes before, and does not in the scenario |
| 4 | Not affected | Outside the layer, and neither loss |
| 5 | Access not assessed | Outside the layer, and not joined to the road graph or without a route even before the flood |

They are the same counts the exposure, the road criticality and the access gap
of the planning score are built from, seen before they are summed.

## Result, in the run the published result rests on

| Tambon | Binding class | Residents | In the water | Dry, every road cut | Dry, hospital out of reach | Not affected | Not assessed |
|---|---|---:|---:|---:|---:|---:|---:|
| Ko Chang | B, keep routes open | 6,708 | 37% | **58%** | 0% | 0% | 5% |
| Mae Sai | D, build resilience | 17,893 | **56%** | 15% | 0% | 28% | 1% |
| Ban Dai | D, build resilience | 5,036 | 19% | 0% | **44%** | 26% | 10% |
| Si Mueang Chum | D, build resilience | 7,158 | **43%** | 10% | 0% | 44% | 3% |
| Pong Pha | E, monitor and verify | 9,349 | 10% | 1% | 0% | 83% | 6% |
| Pong Ngam | E, monitor and verify | 7,249 | 5% | 0% | 0% | 82% | 12% |
| Huai Khrai | E, monitor and verify | 8,912 | 0% | 0% | 2% | 79% | 19% |
| Wiang Phang Kham | E, monitor and verify | 19,532 | 0% | 0% | 0% | 98% | 2% |
| **District** | | **81,837** | **22%** (17,928) | **9%** (7,510) | **3%** (2,447) | 60% | 6% |

Of the 17,928 residents in the water, 14,288 are also cut off from every
road; the order of the test counts them once, in the water.

## What this says

1. **The three tambons of class D need three different things.** In Mae Sai
   most residents are in the water. In Ban Dai the largest group is dry and on
   the road network with the hospital out of reach. In Si Mueang Chum the
   water and no need at all are about even. One letter, "build resilience",
   stands for all three.
2. **Ko Chang is the one tambon where nobody is unaffected.** A third of its
   residents are in the water and nearly all the rest are dry with every road
   cut. That is what its class B says, and the map shows where.
3. **Class E is not "nothing here".** About 910 residents of Pong Pha and 380
   of Pong Ngam are in the water in the scenario. Class E never means safe.
4. **The kind depends on the assumptions in one place above all: Ko Chang.**
   Across the nine runs of the ensemble the share of its residents who are dry
   with every road cut runs from 4% to 62%. Where its roads stay open (the
   smaller flood level with the strict or the central closure level) those
   residents are dry and lose the hospital. On the map, 220 of the 1,263
   squares with residents change their leading kind across the nine runs; they
   carry a stroke.
5. **The population product moves the sizes, not the picture.** With the 2020
   counts rescaled to 2024 totals, Mae Sai has 70% of its residents in the
   water, Ko Chang 71% dry with every road cut, Ban Dai 57% with the hospital
   out of reach.

## What may be said, and what may not

- "Under each class there is a mix, and here it is" may be said, with the
  words "scenario" and "modelled".
- A need type may not be called a class, a priority or a recommendation, and
  no tambon may be given a second letter from it.
- A square may not be read as a street or a household. The squares are 500 m
  because the resident counts are modelled on 100 m cells and the two
  population products disagree inside a kilometre.
- Nothing here says that a place is safe.

## What was checked before anything was written

- The cells behind the counts were computed once
  (`outputs/cell_outcomes/se1_mae_sai_v1_receipt.json`). At the flood level as
  provided their sums per tambon are the committed access table; for every
  tambon, flood level, closure level and demand, the exposure and the road
  criticality that follow from them are the components of the registered
  ensemble run (288 values).
- In the published run, the residents of every tambon, those inside the flood
  layer, those who lose every road route and those who lose a hospital within
  30 minutes are the counts of the published result file.

## Readings made here

- The order of the test: the water first. A resident in the water who is also
  cut off is counted in the water, and the overlap is given.
- "Dry, every road cut" and "dry, hospital out of reach" follow the vehicle
  network, the hospital within 30 minutes and any road route, as the planning
  score counts them. Shelters are not part of it.
- On the map a square takes the kind most of its residents fall in; a tie goes
  to the kind earlier in the order.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed
by FloodGuard, and the figures and the picture derived from it are shared
under CC BY-SA 4.0. Residents: WorldPop 2020 (CC BY 4.0), in the second demand
rescaled to WorldPop 2024 totals. Roads © OpenStreetMap contributors (ODbL
1.0). Boundaries: HDX Thailand COD-AB.

## To run it again

```bash
python scripts/build_cell_outcomes.py --external-data <external-data-root> --age-dir <folder of the age rasters>
python scripts/build_need_mix.py --external-data <external-data-root>
python scripts/build_need_map.py --external-data <external-data-root>
```

The first step takes about 30 minutes; the other two a few seconds.
