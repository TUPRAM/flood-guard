# The THEOS-2 water rule against labels by two people

**State on 11 October 2026: the points are drawn; nobody has labelled yet.**
The figures are added here when two label files exist.

Plan: `docs/proposal_execution/theos2_water_label_check_plan_v1.md`.
Record of the draw: `outputs/theos2_water_labels/sample_v1.json`.

## What this is for

Three results of the project compare something with "the water THEOS-2
shows": the three radar rules at Sukhothai, the road-closure rule on the same
image, and the one test of the improved radar detector. That water is read
from the image by one rule, which was looked at and never measured. This
check measures it: two team members say, for 300 squares of 2 m drawn at
random, whether the square is water, and the rule is scored against them.

It is not a ground check. The labels come from the same image the rule
reads. The figures will say whether the rule reads the image as a person
does.

## The draw

| Chip | Pixels of 2 m | The rule calls water | Points |
|---|---:|---:|---:|
| `sukhothai`, 30 July 2025 | 2,253,001 | 755,945 | 120 |
| `chip_003`, 31 July 2025 (flooded town) | 2,251,500 | 856,147 | 120 |
| `chip_001`, 31 July 2025 (no flood; set aside) | 2,251,500 | 520,714 | 60 |

Each chip is cut into six groups by the rule alone (water away from an edge,
water at an edge, small objects the rule drops, land at an edge, land away
from one, and the area the rule sets aside), and points are drawn at random
inside each. The record holds the size of every group. It does not hold
where a point is or which group it is in: that key stays outside Git until
the figures are computed, because the repository is public and the labellers
read it. Its SHA-256 is in the record, so the key that is published later can
be checked against the draw.

## How to label (two team members, about an hour each)

1. Get the page: `label_page_v1.html` (20 MB), in the external data folder
   under `proposal_execution/theos2_water_labels_v1/`. It is one file and
   needs no internet. It holds pixels of the THEOS-2 samples, so it is passed
   between team members and not put in the repository or on a public link.
2. Open it in Chrome or Edge on a laptop, type your first name, press Start.
3. For each point press **W** (water), **N** (not water) or **U** (cannot
   tell). The rule for the square is on the first screen: more than half of
   the yellow square decides. **H** hides the outline, the left arrow goes
   back. The first six points are practice.
4. You can close the page and come back in the same browser.
5. At the end press "Save the label file" and pass the file
   (`floodguard_water_labels_<name>.json`) to the person who runs the
   scoring.

Label alone. Do not look at the water maps in the docs while you label, and
do not compare single points with the other labeller before both files
exist.

## What is computed afterwards

Once, from both files (`scripts/build_theos2_water_labels.py score`):

- of the area the rule calls water, the share both labellers call water;
- of the area both call water, the share the rule finds;
- whether the rule makes the water area larger or smaller than the labels;
- whether the small objects the rule drops are roofs, as it assumes;
- whether the error sits at the edges;
- how far the two labellers agree with each other.

Each comes with an interval, for each chip and for the two reference chips
together. The result, the key and both label files are then committed, and
the figures are set beside every comparison of radar with THEOS-2 water in
the docs. No radar figure is changed with them.

## Limits

- Same image for the rule and the labels; no ground check.
- Team members, not trained image interpreters.
- Three chips of two days in one region; none covers Mae Sai.
- 120 points a chip give wide intervals; the two reference chips together
  are the figure to read.
