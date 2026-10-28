# THEOS-2 of 17 September 2024, the mud: amendment 1 to plan v1

Written on 19 October 2026, **after** the mud rule was frozen once
(`outputs/theos2_17sep_mud/freeze_v1.json`, decision log R57) and **after its
development scores were seen**, and **before any test point was drawn or
labelled**. The plan itself is not edited; this file stands beside it. The
owner asked for it: "write the mud amendment (water-before mask, cloud-only
mask, larger minimum object, about 40 new development points in the unmasked
area), commit it before any test point, then rescore and freeze again."

## What was seen, and why this changes the rule

On the 160 development points the agent labelled, `mud_s0` was kept with an
area-weighted F1 of 0.23. It found 19 of the 22 points labelled mud, but most
of what it called mud was not mud:

- **turbid ponds**: brown rectangular fish ponds with sun glint, which the
  colour rule reads as mud and rule v2 does not read as water;
- **edges**: pieces of roofs and roadsides at the edge of the mud objects
  (21 of the 30 points of `mud_edge` labelled not mud);
- and, from the plan's own mask, **a blind spot**: ground rule v2 calls water
  is unobservable for every candidate, so the largest deposit of the scene,
  east of the clouds in the north-east, which rule v2 calls water, cannot be
  read as mud (R56, R57).

These are known only because the development scores were seen. That is what
development points are for; the test stays untouched. **The 150 test points
are not drawn yet, and the bar of 0.60 and the margin of 0.02 do not change.**

## What changes

### New masks for the new candidates

| Mask | In plan v1 | In this amendment |
|---|---|---|
| Cloud | what rule v2 calls unobservable **or water** | what rule v2 calls unobservable only |
| Water before the flood | none | new: the 10 m Sentinel-2 cell under the pixel centre was water on 5 September 2024 (scene class 6, or a clear class with MNDWI above 0, from B03 and B11), **or** the pixel lies in an OSM polygon tagged `natural=water`, `water=*` or `landuse` aquaculture, reservoir or basin, **or** in the permanent water of the 10 m lattice of the district |
| Roofs | outlines widened by 1 m | unchanged |
| Smallest mud object | 5 pixels (20 m²) | **25 pixels (100 m²)**, 8-connected |

A pond that held water before the flood is set aside even if it is full of
mud now: the rule cannot tell, and the labels say most such ponds are water.

### Two new candidates

| Candidate | Rule |
|---|---|
| `mud_s3` | The colour rule of `mud_s0`, unchanged limits, on the new masks, objects of 25 pixels or more |
| `mud_s4` | `mud_s3` with its three limits chosen from the same grid of 64 as `mud_s2`, fitted on one order and scored on the other, in both directions |

### Forty new development points, in the ground the new masks open

The **opened ground** is every pixel observable under the new masks and not
under the masks of plan v1: in practice what rule v2 called water and that was
not water before the flood. **40 points** (seed 20261021) are drawn there:
20 where `mud_s3` says mud and 20 where it says not mud, half in each order
where the ground allows; a shortfall goes to the other order, then to the other
half. No point lies within 20 m of a development point of plan v1. They are
labelled by the agent from sheets made as before (a number and three pictures,
never the group), with the conventions of the first label file unchanged.

### Scoring and the choice

- **Strata.** Each development point stands for the pixels of its stratum.
  The strata of plan v1 (the groups of `mud_s0` in each order) are kept
  outside the opened ground; the opened ground makes two new strata in each
  order (`mud_s3` mud, `mud_s3` not mud). A point of plan v1 that lies in the
  opened ground moves to the new stratum it falls in. Weights are pixels of the
  stratum over its points.
- **The same 200 points** score every candidate: `mud_s0` again, `mud_s3`,
  `mud_s4`. Score: area-weighted F1 of the label mud on the points labelled
  mud or not mud, mean of the two orders.
- **Choice.** `mud_s0`, the rule frozen in R57, stays unless `mud_s3` is
  better by **0.02 or more**; the one kept stays unless `mud_s4` is better
  than it by 0.02 or more. The chosen rule is frozen in
  `outputs/theos2_17sep_mud/freeze_v2.json`, which supersedes `freeze_v1.json`
  for the test; `freeze_v1.json` stays in Git as it is.

## What does not change

- The test of section 4.4: 150 points, three team members, the bar of 0.60,
  drawn only after `freeze_v2.json` is committed, in the groups of the rule it
  freezes.
- Section 4.5, the order of the commits, and everything in sections 6 and 7.
- No height above the river or any part of the replay enters a mud rule: the
  replay's peak is what the mud is set against in section 4.5b.

## Known before the rescore

- The development labels are the reading of an AI model, and the agent has now
  seen which kinds of ground the first rule got wrong. The new points sit in
  ground it has not labelled before; the old points are scored again as they
  were labelled, with no label changed.
- Sentinel-2 of 5 September has cloud in places; where it is not clear, only
  OSM and the permanent water can set a pond aside.
- A pond missing from OSM and clouded on 5 September still reads as mud.
