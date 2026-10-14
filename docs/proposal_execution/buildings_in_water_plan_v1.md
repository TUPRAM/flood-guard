# Buildings in the water against residents in the water: plan v1

Written on 11 October 2026, after one test read of building outlines for one
chip (5,784 outlines; nothing was computed from them) and before any building
was set against water or against the flood layer.

## 1. Why

The planning score counts "residents in the water" from a population grid: a
cell of about 100 m with its modelled residents counts as flooded when its
centre lies inside the flood layer. For case SE1 that gives 17,928 residents
in the water, 22 percent of the district. Nobody lives at the centre of a
cell. People live in buildings, and in a flood plain buildings stand along
roads and on higher ground. The count has never been set against buildings.

A THEOS-2 image at 0.5 m shows what radar at 10 m cannot: whether a single
house stands in water. This is the first use of that detail for exposure.

Two questions:

1. **On a THEOS-2 image**: how many buildings stand in water, and does the
   centre rule on the population grid put the same share of residents in the
   water as the buildings do?
2. **For case SE1**: the same comparison with the flood layer of the scenario
   in place of image water, for each tambon of Mae Sai district.

## 2. The building outlines

Source: the combined Google Open Buildings v3 and Microsoft building
footprints file for Thailand that VIDA publishes on Source Cooperative
(`data.source.coop/vida/google-microsoft-open-buildings`, FlatGeobuf by
country, file of 26 August 2024). Google's outlines are under CC BY 4.0 and
ODbL, Microsoft's under ODbL. They are outlines a model drew on satellite
images of earlier years: not a survey, not a register of dwellings, and
they say nothing of who lives in a building.

Only the outlines inside the bounding boxes of the two flood chips and of
Mae Sai district are read. They stay outside Git with their SHA-256.

A building is used when its outline has 10 square metres or more and, where
the source gives a confidence (Google), a confidence of 0.70 or more.

OpenStreetMap, which the project uses for roads, holds 41 buildings on the
Sukhothai chip, 4 on the chip of the flooded town and 443 in the whole
district: too few to count with.

## 3. Question 1: a building in the water on an image

Chips: `sukhothai` and `chip_003`. The chip without a flood is not used. Both
water rules are read: rule v1 as it was run for the earlier checks, and the
rule frozen on 11 October (R44). Neither has been scored on the test points
yet, so both are reported and neither is called right.

A roof is not water, also when the house stands in a metre of it. So a
building is judged by the ground around it:

- **The ring** of a building is every 2 m pixel that is more than 2 m and at
  most 8 m from its outline, is not on or beside another building, and is
  nearer to this building than to any other.
- A building is **assessed** when its ring holds at least 6 pixels and at
  least half of them have an answer from the water rule.
- An assessed building is **in the water** when at least half of the answered
  pixels of its ring are water. The same count is given at one quarter and at
  three quarters.

Only buildings whose centre lies at least 20 m inside the chip are counted.

Tree crowns hide water and count as not water, so the count of buildings in
the water is an under-count where houses stand under trees.

**Residents.** The population grid is the 100 m WorldPop grid of 2020 the
planning score uses. For each cell whose centre lies in the chip, three
readings of "residents in the water":

| Reading | Residents of the cell counted as in the water |
|---|---|
| Centre rule (the planning score) | all, when the pixel at the centre of the cell is water |
| Area | the share of the cell's answered pixels that are water |
| Buildings | the share of the cell's assessed buildings that are in the water |

The buildings reading spreads the residents of a cell evenly over its
buildings. Cells with residents and no assessed building are counted and
left out of the comparison; the three readings are compared on the same
cells.

## 4. Question 2: case SE1

The flood layer is the one of the scenario (every area UNOSAT and GISTDA
mapped as flooded between 1 August and 12 October 2024, taken as flooded at
once), at its three levels. A building is **in the layer** when the centre of
its outline lies inside it. The cells are the demand cells of the published
run; a building belongs to the cell whose centre is nearest, within 75 m.

For the district and for each tambon: the buildings, the share in the layer,
the residents in the water by the centre rule (the published figure) and by
the buildings reading, on the cells that hold a building.

## 5. What is written, whatever the figures

1. For each chip and each water rule: buildings assessed, buildings in the
   water, and the three readings of residents in the water side by side.
2. For case SE1: the two readings for the district and each tambon, and the
   tambons where they differ by more than 5 percentage points.
3. One sentence on what the comparison says of the centre rule: that the
   buildings reading is lower, higher, or within 5 points of it.
4. **No published figure changes.** The planning score keeps the centre rule.
   Whether a later version should weight residents by buildings is a decision
   for the owners, after this is read.

## 6. Limits known before the start

- Outlines drawn by a model on images of earlier years. Buildings put up or
  washed away since are wrong in it; sheds, shops and temples count like
  houses.
- Spreading the residents of a cell evenly over its buildings is as much a
  model as the grid itself. The comparison sets one model against another;
  neither is a count of people.
- On the image, "in the water" is the water rule's reading of the ground
  around a house, 2 to 8 m from the wall. Water under trees is missed.
- The chips are not Mae Sai, and question 2 has no image: it shows where the
  buildings are against the flood layer, not that they were flooded.
- When GISTDA's images of Mae Sai arrive, question 1 can be asked there. That
  needs an amendment of the plan for those images and is not part of this
  plan.

## 7. Added on 11 October 2026: a side run with residents spread over buildings

Written after the figures of sections 3 and 4 were read (decision log R45)
and before this run was made. The owner asked for it on 11 October.

**The demand.** The residents of each tambon, as the population grid of 2020
counts them, are spread evenly over the buildings of that tambon. A cell
holds the residents of the buildings nearest to its centre; a cell without a
building holds nobody. The total of every tambon stays what it was.

**What is run with it**, beside the published figures and changing none:

1. The need mix of case SE1: residents of each tambon by need type, in the
   run the published result rests on and over the nine access runs.
2. The 90 cells of the uncertainty ensemble (three flood levels, three
   closure levels, two anchor pairs, five weight presets), through the code
   of the registered run. The run first reproduces the 90 cells of the 2020
   demand of the registered run, cell by cell, and stops if one differs.

**What is written, whatever the figures.** For each tambon: the class of the
default cell with each demand, the classes over the 90 cells with each
demand, and the need mix with each demand. If a class of the default cell
changes, that is said in the first sentence. No class of record changes: the
classes of the published result and of the registered run stand.

**Limits known before the run.** Every building counts as one home of the
same size: a shed and a block of flats weigh the same. The share of children
and older residents of a tambon is not changed by the demand. Travel times
are those of the registered run; only the residents of the cells differ.
