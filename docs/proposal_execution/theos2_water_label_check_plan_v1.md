# The THEOS-2 water rule against labels by two people: plan v1

Written on 11 October 2026, before any point was drawn and before anybody
labelled anything. It says which points are drawn, what a labeller sees and
decides, which figures are computed, and which sentences are written whatever
the figures turn out to be.

## 1. Why

Three results of the project stand on "the water THEOS-2 shows": the check of
the three radar rules at Sukhothai, the check of the road-closure rule on the
same image, and the one test of the improved radar detector on the chips of
31 July 2025. In all three the water is read from the image by one rule (a
water index with a threshold found on each image, bright objects set aside,
small objects dropped). That rule was looked at beside its image and never
measured. On one chip it failed in plain sight: with no flood on the image it
marked bare soil as water, and the chip was set aside.

This check gives the rule a measured figure: how often it says what a person
says who looks at the same image at full detail.

**What it is not.** Nobody went to the ground. The labels come from the same
image the rule reads, so the figures say whether the rule reads the image as
a person does, not what was on the ground on that day. They are agreement
between a rule and two readers, and they qualify no radar method.

## 2. The images and the rule

| Key | Scene | Rule setting | Role so far |
|---|---|---|---|
| `sukhothai` | `IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif`, 30 July 2025 | As in the cross-check, with its one rectangle set by eye | Reference of the cross-check; development data of the detector |
| `chip_003` | `IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif`, 31 July 2025 | No setting made by eye | Reference of the one held-out test |
| `chip_001` | `IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif`, 31 July 2025 | No setting made by eye | Set aside: no flood on the image |

The rule is run again from the scene files, on the 2 m raster it was written
for (the mean of 4 by 4 pixels of 0.5 m). The run stops unless the number of
water pixels and the number of pixels dropped by the size rule are the ones
the committed records hold. The unit that is sampled and labelled is one
pixel of that raster: a square of 2 m.

## 3. The points

Every pixel of a chip falls in one of six groups, all of them known from the
rule alone:

| Group | Pixels of the rule that are |
|---|---|
| `water_inside` | water, more than 6 m from any pixel that is not water |
| `water_edge` | water, within 6 m of a pixel that is not water |
| `dropped_small_object` | above the threshold of the water index, in an object under 1,000 square metres: the rule drops it and calls it not water |
| `land_edge` | not water, within 6 m of a water pixel |
| `land_inside` | not water, further away |
| `unobservable` | set aside by the rule (bright objects, the rectangle at Sukhothai) |

"Within 6 m" is three pixels in any direction, a square neighbourhood.

Points are drawn at random inside each group, without drawing a pixel twice:

| Chip | `water_inside` | `water_edge` | `dropped_small_object` | `land_edge` | `land_inside` | `unobservable` | Points |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sukhothai` | 20 | 20 | 15 | 20 | 30 | 15 | 120 |
| `chip_003` | 20 | 20 | 15 | 20 | 30 | 15 | 120 |
| `chip_001` | 10 | 10 | 8 | 10 | 15 | 7 | 60 |

A group with fewer pixels than its points gives its points to `land_inside`
of the same chip (`chip_001` has no unobservable pixel). The edges get more
points than their area because that is where a threshold errs; the estimates
of section 6 weight every group by its area, so this does not tilt them.

The random numbers come from the seed 20261011 with the number of the chip
and of the group. The 300 points are then put in one random order and named
`p001` to `p300`, so that neither the name nor the place in the order tells
the group or the chip. Six more points, one of each group at Sukhothai and
none of them among the 300, come first as practice; their labels are not
kept.

## 4. What a labeller sees and decides

A page that opens in a browser, one point at a time, with three pictures:

- the 64 m around the point at the full 0.5 m, in true colour;
- the same 64 m in false colour (near infrared shown as red), in which
  plants are red, clear water is dark and muddy water is blue-green;
- the 320 m around the point at 1 m, for context.

The square of 2 m is outlined in the middle of the first two pictures; a key
hides the outline. The brightness of the pictures is fixed for a chip, the
same for every point. **The page does not hold the answer of the rule**, the
group of a point or its chip.

The labeller gives one of three labels:

| Label | When |
|---|---|
| **Water** | More than half of the square is a water surface that can be seen: river, canal, pond, flood water, a field under water. Muddy water is water |
| **Not water** | More than half of the square is anything else: plants (also a crop or a tree standing in water when leaves cover the surface), bare soil, a roof, a road, a shadow on land |
| **Cannot tell** | Cloud, haze, a shadow too deep to see into, or no decision after looking at the three pictures |

**Amended on 11 October 2026, after the draw and before anybody labelled.**
The first text of this section and of the page said that open water is dark
in false colour. The six practice points, looked at by the agent who built
the page, show muddy flood water blue-green there. The sentence on the page
was corrected; the points, the pictures and the three labels are unchanged.

Two team members label all 300 points, each alone. They do not look at the
water map of the rule while they label and do not speak about single points
until both files exist. The page writes a file with the labels, the name the
labeller typed and the seconds spent on each point.

## 5. The order

1. This plan is committed.
2. The points are drawn. A record in Git
   (`outputs/theos2_water_labels/sample_v1.json`) holds the size of every
   group, the number of points and the SHA-256 of the key (which point is
   which pixel of which group) and of the page. **The key and the page stay
   outside Git** until step 4: the repository is public and the labellers
   read it. The page holds pixels of the THEOS-2 samples and stays outside
   Git for good.
3. Two people label.
4. The figures of section 6 are computed once. The key, the two label files
   and the result are committed together.

A second draw needs a reason written into the record that replaces the first,
and is not made once a label file exists. The figures are computed again only
with a reason, and every result is kept.

## 6. The figures

**The label a point is scored with** is the label both people gave, where
both gave "water" or both gave "not water". A point on which they differ, or
which one of them could not tell, is left out of figures a to d and counted.
The same figures are given beside it for each labeller alone.

For each chip, and for `sukhothai` and `chip_003` together (the two chips
that served as a reference; `chip_001` is reported alone):

| | Figure | In words |
|---|---|---|
| a | Of the area the rule calls water, the share the labels call water | How much of the rule's water is water |
| b | Of the area the labels call water, the share the rule calls water | How much of the water the rule finds |
| c | Of the area the rule gave an answer for, the share where rule and labels say the same | |
| d | The water share of that area by the labels, beside the share by the rule | Does the rule make the flood larger or smaller |
| e | Of the points in `dropped_small_object`, the number labelled water | Is the size rule right that these are mostly roofs |
| f | Of the points in `unobservable`, the numbers labelled water, not water, cannot tell | What the set-aside area holds |
| g | Figures a and b with the edge groups left out, and the share of edge points where rule and labels differ | Is the error at the edges |
| h | The share of all points on which the two people gave the same label, the table of their labels, and Cohen's kappa | How far two readers agree |

Figures a to d weight each group by its number of pixels (the estimators for
a stratified random sample of Stehman 2014, with the groups as strata; they
hold for any map, also one that is not the map the groups were cut from).
Each comes with a 95 percent interval from the same paper. Figures e and f
are counts of one group, with a Wilson interval. Points left out are taken to
be missing at random inside their group; the result says how many they are in
each group, so a reader can see where that is doubtful.

## 7. What is written, whatever the figures

1. One sentence with figures a and b for the two reference chips together and
   the number of points the two people agreed on, and one with figure h.
2. The same for `chip_001`, as the case where the rule is known to fail.
3. The figures are set beside every comparison of radar with THEOS-2 water in
   `docs/theos2_radar_cross_check.md` and
   `docs/radar_detection_improvement.md`. **No radar figure is changed or
   corrected with them.**
4. If figure a or figure b is below 0.80 for the two reference chips
   together, those documents and the pitch stop calling the THEOS-2 water a
   reference without the figure in the same sentence.

## 8. What the labels may be used for afterwards

They are a test set. The rule is not changed on them. A better water rule,
if one is built, is developed on other points (a new draw with another seed,
labelled the same way), frozen, and then scored once on these 300 points.
Because the estimators do not need the map to be the one the groups were cut
from, the same points can score a later rule.

## 9. Limits known before the start

- The labels come from the same image as the rule, in true and false colour.
  A person who sees dark in the near infrared will tend to say water, as the
  index does. Muddy water, wet soil and shadow are where both can be wrong
  together.
- The labellers are team members, not trained image interpreters, and one of
  them has seen the picture of the rule's water at Sukhothai in the docs.
- 120 points on a chip give wide intervals: about 10 points either way for a
  share near 0.9 in one group. The two chips together are the figure to read.
- Three chips, two days, one season, one region. Nothing here says how the
  rule does on the images of Mae Sai that GISTDA has offered.
- A square of 2 m at the edge of water is often mixed; "more than half" is a
  judgement.

## References

- Olofsson, P., Foody, G. M., Herold, M., Stehman, S. V., Woodcock, C. E.,
  Wulder, M. A. (2014). Good practices for estimating area and assessing
  accuracy of land change. *Remote Sensing of Environment* 148, 42-57.
- Stehman, S. V. (2014). Estimating area and map accuracy for stratified
  random sampling when the strata are different from the map classes.
  *International Journal of Remote Sensing* 35(13), 4923-4939.
