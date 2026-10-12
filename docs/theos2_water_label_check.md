# The THEOS-2 water rule against labels by two people

**State on 12 October 2026: done. Three team members labelled; the figures
were computed once and are below.**

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
together.

The same run scores a second water rule on the same 300 points
(`docs/theos2_water_rule_v2.md`). That rule was developed on 240 other points
and frozen on 11 October, before anybody but the labeller had seen a label
of a team member. The run refuses to start without that freeze, so that
nothing learnt from your labels can find its way into the rule.

The result, the key and both label files are then committed, and the figures
are set beside every comparison of radar with THEOS-2 water in the docs. No radar figure is changed with them.

## The result (12 October 2026)

Record: `outputs/theos2_water_labels/result_v1.json`, with the key and the
three label files beside it.

**Three people labelled, not two.** Callixta, Putu and Rachmania each labelled
all 300 points. The plan asked for two and was amended before any figure was
computed: a point is scored with the label at least two of the three gave.
The figures for every pair, for all three agreeing and for each labeller
alone are in the record.

### How far three readers of one image agree

| | |
|---|---|
| All three gave the same label | 57% of the points (48% at Sukhothai, 54% in the flooded town, 80% on the chip without a flood) |
| Cohen's kappa, by pair | 0.41, 0.47, 0.53 |
| Points labelled water, of 300 | Callixta 180, Putu 133, Rachmania 93 |
| Median time on a point | 1.1 s, 1.3 s, 2.2 s |

**This is the first thing the check says: "water" on these images is not one
thing.** Three team members who looked at the same pictures differ by a factor
of two in how much water they see. The labels were given fast. Every figure
below has to be read with that.

### Rule v1, on the two chips that served as a reference

216 of 240 points have a scoring label.

| | Figure | 95% interval | Over the other ways of scoring |
|---|---:|---:|---:|
| Of the area the rule calls water, the share that is water to the labellers | **90%** | 83 to 96 | 81 to 98 |
| Of the water the labellers see, the share the rule finds | **71%** | 64 to 77 | 54 to 87 |
| Of the area the rule answers, the share where both say the same | 80% | 75 to 86 | 64 to 92 |
| Water share of that area: by the rule, by the labels | 41%, 53% | labels 47 to 58 | labels 41 to 70 |

- **What the rule calls water is water. But it misses about three tenths of
  the water people see**, and it makes the flooded area smaller than they do.
- **The small objects it drops are not mostly roofs**: 17 of 28 are water to
  the labellers. The size rule throws water away.
- **Half of what it sets aside as bright is water**: 12 of 22 points.
- **The error sits at the edges**: rule and labels differ on 39% of the area
  within 6 m of a water edge (29 to 50). Away from the edges the rule's water
  is water in 95% and it finds 77%.
- On the chip that was set aside, 5% (0 to 16) of the area the rule calls
  water is water. By the labels 1% of that chip is water; the rule says 23%.

By the rule of the plan (section 7): the share of the water the rule finds is
below 0.80, so the documents and the pitch do not call this water a reference
without the figure in the same sentence.

### Rule v1 against rule v2

The share of the labelled area where a rule gives an answer and the answer is
the label; area a rule sets aside counts against it.

| Chips | Rule v1 | Rule v2 | Difference |
|---|---:|---:|---:|
| The two reference chips together | 69% (65 to 74) | **78%** (72 to 83) | **+8 points (4 to 13)** |
| Sukhothai | 79% (73 to 85) | 82% (75 to 89) | +3 (-1 to 7): not shown to be better |
| Flooded town | 60% (53 to 67) | 74% (65 to 82) | +14 (6 to 21) |
| No flood | 78% (76 to 81) | 99% (96 to 100) | +21 (16 to 25) |

- **Rule v2 is better on these points**, by 6 to 9 points on the two reference
  chips whichever labellers are used, and every one of those intervals stays
  above zero.
- It is not shown to be better at Sukhothai alone.
- Where it answers, rule v2 is no better at finding water: 88% (82 to 94) of
  its water is water, and it finds 70% (62 to 77). Its gain is that it answers
  almost everywhere (it sets aside 3% of the two chips, where rule v1 sets
  aside 14%) and that it does not invent water on a dry scene.
- On the chip without a flood it finds none of the little water the
  labellers saw there.
- **The estimate made in development was too rosy.** On the agent's own
  labels rule v2 scored 0.97 and rule v1 0.78. On the team's labels they
  score 0.78 and 0.69. The gain is real and less than half as large.

### What this says of the earlier radar figures

The radar rules found 22 to 50 percent of the water of rule v1 at Sukhothai,
and the frozen detector 24 percent in the flooded town. Rule v1 itself finds
about seven tenths of the water people see. So the radar's share of the water
people see is lower than those figures, not higher. **No radar figure is
changed**; this is said beside them in `docs/theos2_radar_cross_check.md` and
`docs/radar_detection_improvement.md`.

## Limits

- Three readers agree on 57% of the points and labelled in one to two seconds
  a point. The figures measure the rule against a fast human reading.
- Same image for the rule and the labels; no ground check.
- Team members, not trained image interpreters.
- Three chips of two days in one region; none covers Mae Sai.
- 120 points a chip give wide intervals; the two reference chips together
  are the figure to read.
