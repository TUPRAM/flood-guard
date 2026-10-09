# The stability of the SE1 classes over all 180 cells: result

**What this is.** Protocol v1b judges a published class by one rule: across
the 180 cells of the uncertainty ensemble that a public result is judged on, a
tambon must keep the class of its default cell in at least 60% of them. The
registered run of case SE1 made 90 of the 180: the cells that count residents
with WorldPop 2020. The other 90 count them with the 2020 counts rescaled to
WorldPop 2024 totals, a demand that no stage had built. It is built here, and
all 180 cells are run.

**How to read it.** Report-only. This is **not the registered run** of the
ensemble: the registered receipt, the run register and the published result
file are unchanged, and the published file still says that the stability of
its classes is not evaluated. The case is a scenario (the season layer of
1 August to 12 October 2024), not a flood of any day; closures are modelled;
resident counts are modelled, not observed. It is not an official warning,
and class E never means safe.

- Result: `outputs/uncertainty_ensemble_rescaled/se1_mae_sai_v1.json`
- Code: `src/floodguard/demand_rescale.py`,
  `scripts/build_ensemble_rescaled_demand.py`
- Source time: season layer of 1 August to 12 October 2024; residents of 2020,
  rescaled to 2024 totals in half the cells. Confidence: low.

## Result

| Tambon | Binding class | Keeps it in | By the rule | The other cells |
|---|---|---:|---|---|
| Ko Chang | B, keep routes open | 140 of 180 (78%) | holds | D in 40 |
| **Mae Sai** | D, build resilience | **90 of 180 (50%)** | **does not hold: "unstable: verify"** | A in 30, B in 40, C in 20 |
| Si Mueang Chum | D, build resilience | 180 of 180 | holds | |
| Ban Dai | D, build resilience | 180 of 180 | holds | |
| Pong Pha | E, monitor and verify | 177 of 180 (98%) | holds | D in 3 |
| Huai Khrai, Wiang Phang Kham, Pong Ngam | E, monitor and verify | 180 of 180 | holds | |

Seven of the eight classes hold. One does not.

## What this says

1. **Ko Chang's class holds, and the population product does not move it.**
   It is B in 70 of the 90 cells of each demand. The 40 cells where it reads D
   are all at the smaller flood level with the strict or the central closure
   level: there some of its roads stay open. What the class depends on is the
   flood extent and the closure rule, as the road sheet already showed.
2. **Mae Sai town's class D does not hold.** It is D in every one of the 90
   cells that count residents with WorldPop 2020, and in none of the 90 cells
   that use the rescaled demand. There it is A (protect lives now) in the 30
   cells of the larger flood level, B in 40 and C in 20. Every cell that
   leaves D moves to a more urgent class.
3. **Why the town moves.** The 2024 product places 31,648 residents in the
   tambon against 17,893 in the 2020 product, and more of them in the part of
   town the layer covers. At the default flood and closure level:

   | Component (0 to 100) | WorldPop 2020 | Rescaled to 2024 | The rule asks |
   |---|---:|---:|---|
   | Exposure | 56.2 | 69.6 | 70 for A, 65 for C |
   | Access gap | 67.9 | 79.2 | 70 for A, 55 for B, 50 for C |
   | Road criticality | 66.5 | 78.2 | 75 for B |

   With the 2020 counts no trigger of A, B or C is met and the town falls to
   D. With the rescaled counts the road trigger is met, and the exposure
   trigger is missed by less than half a point; at the larger flood level it
   is met too.
4. **This is a difference between two population models, not four years of
   growth.** Over the eight tambons the rescaled demand holds 95,472
   residents against 81,837. Inside single 1 km cells the ratio of the two
   products runs from 0.003 to 60, with a median of 0.38: most cells hold
   fewer people than in the 2020 product and a few hold many more. Si Mueang
   Chum goes from 7,158 to 4,605 residents and Ban Dai from 5,036 to 3,409.
   Neither product was checked against a count on the ground.

## What may be said, and what may not

- **Nothing published changes.** The published result of case SE1 still shows
  Mae Sai as D and says that stability is not evaluated. Putting a status on
  a published class needs a registered run and a new publication, which is
  the owners' decision.
- **In the pitch, this is the second half of the answer to "why is the
  worst-hit town only class D".** The first half is the second class reading
  (`docs/class_v2_reading.md`). The second: the D rests on the 2020 population
  product; with the 2024 totals the town reads A, B or C, and by the
  protocol's own rule the D would be shown as "unstable: verify".
- **Ko Chang's B may be called stable across the public set** (78%), with the
  condition named: it turns to D when the flood extent is drawn one pixel
  smaller and closures are not permissive.
- Not to be said: that the town "is class A". A is one reading in 30 of 180
  cells, at the larger flood level only.

## What was checked before anything was written

- The default cell of this run has the SHA-256 of the rows the registered
  score run records.
- In all 90 cells of the 2020 demand, every tambon has the planning score and
  the class of the registered ensemble run (720 values compared).
- The three access runs at the flood level as provided are the registered
  access table, value for value.
- Every demand cell carries the count of the 2020 pixel it was looked up at.

## Readings made here that the protocol leaves open (decision log R38)

- A 100 m count belongs to the 1 km cell that holds the centre of its 100 m
  cell.
- A positive 2020 count whose 1 km cell has no 2024 total keeps its 2020
  value. This touches 1,153 of the 81,837 residents (1.4%).
- 23 residents of the 2024 product lie in 1 km cells with no 2020 count and
  are left out, as the protocol says.
- Travel times do not depend on the demand, so the nine access runs serve both
  demands. The age counts of a tambon, and so its vulnerability component,
  are the same for both.

## Not done

- The 360 cells of the two facility sets that add shelters. They need a
  walking context of record and are not part of the set a public result is
  judged on.
- Case O2. Its lineage is held below the public level.
- A registered run. The registered builder still lists the rescaled demand as
  not built.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed
by FloodGuard, and the figures derived from it are shared under CC BY-SA 4.0.
Residents: WorldPop 2020 (CC BY 4.0), rescaled to WorldPop 2024 totals; age
counts: WorldPop, DOI 10.5258/SOTON/WP00842 (CC BY 4.0). Roads ©
OpenStreetMap contributors (ODbL 1.0).

## To run it again

```bash
python scripts/build_ensemble_rescaled_demand.py --case SE1 --frame mae_sai --external-data <external-data-root> --age-dir <folder of the WorldPop 2024 age rasters>
```

The run takes about 40 minutes. A second run needs `--replace --reason`.
