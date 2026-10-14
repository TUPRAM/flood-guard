# A sturdier THEOS-2 water rule: plan v1

Written on 11 October 2026, while two team members label the 300 points of
the label check (`theos2_water_label_check_plan_v1.md`) and before any of
their labels has been read by anybody but themselves. It says on which points
a second water rule is developed, how one rule is chosen and frozen, and how
it is scored.

## 1. Why

The water rule of the THEOS-2 checks (rule v1) splits the water index of each
image into three groups and calls the upper group water. It has three known
weak points:

1. **It always finds water.** On a chip without a flood (`chip_001`) the upper
   group was bare soil, and the chip had to be set aside by a person.
2. **It sets a large area aside.** Bright objects are unobservable: 19 percent
   of the chip of the flooded town. Some of that may be water or roofs a
   person can tell.
3. **It was set by eye.** One rectangle at Sukhothai, and the sizes of the
   bright-object and small-object rules.

GISTDA has offered images of September 2024 over Mae Sai. The plan for those
(`theos2_study_event_check_plan_v1.md`, section 4) reads them with rule v1.
A rule that does not invent water on a dry scene, and whose error is
measured, should be ready before they arrive.

## 2. Two sets of points that never mix

| Set | Points | Labelled by | Used for |
|---|---:|---|---|
| **Test** | 300, seed 20261011 | Two team members | Scoring only. The rule is never changed on them |
| **Development** | 240, seed 20261012 | The agent that builds the rule (an AI model), from the same three pictures and the same three labels | Trying changes and choosing one rule |

The development points are drawn like the test points: the same three chips,
the same six groups cut from rule v1, at random inside each group.

| Chip | `water_inside` | `water_edge` | `dropped_small_object` | `land_edge` | `land_inside` | `unobservable` | Points |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sukhothai` | 16 | 16 | 12 | 16 | 24 | 12 | 96 |
| `chip_003` | 16 | 16 | 12 | 16 | 24 | 12 | 96 |
| `chip_001` | 8 | 8 | 6 | 8 | 12 | 6 | 48 |

No development point lies within 20 m of a test point or a practice point.
The agent labels them without the group of a point in view: the sheets it
looks at show a number and three pictures. Its labels are committed with the
freeze. **They are development data, not a reference**: nobody is scored
against them outside this plan, and they are the reading of a model, not of
a person.

## 3. What may be tried

Anything that is computed from the four bands of the image alone, at the 2 m
of rule v1 or finer: another split of the water index, a second index, a
shadow or cloud rule, a check whether the image holds a water group at all,
or a small trained classifier on features of a pixel and its surroundings.
No radar, no land-cover map, no elevation: the rule has to stand as an
optical reading that the radar can be compared with.

Every candidate must give each pixel one of three answers (water, not water,
unobservable) and must run on a new image with **no setting made by eye**.

## 4. How one rule is chosen

For each candidate and each chip, on the development points:

> **Share answered and alike**: of the area where the development label is
> water or not water, the share where the candidate gives an answer and the
> answer is the label. Area the candidate calls unobservable counts as not
> alike. Each group is weighted by its number of pixels.

A candidate with fitted parameters is scored on each chip by a version
fitted **without the points of that chip**. That is the nearest thing to a
new image these three chips allow.

The candidate with the highest mean of this share over the three chips is
chosen. A candidate within 0.01 of the best that has fewer fitted parameters
is preferred. If no candidate is more than 0.01 above rule v1, rule v1 stays
and that is the result. The chosen candidate is then fitted on the
development points of all three chips and **frozen**: its code, its
parameters and the SHA-256 of the water raster it writes for each chip are
committed (`outputs/theos2_water_rule_v2/freeze_v1.json`), with the score of
every candidate that was tried.

## 5. The order

1. This plan is committed.
2. The development points are drawn and labelled by the agent.
3. Candidates are tried; one is frozen and committed.
4. **Only then** are the figures of the label check computed, for rule v1 as
   planned and, in the same run, for the frozen rule: figures a to d and the
   share answered and alike, on the 300 test points.

If the two label files arrive before step 3 is done, they are kept unread
until it is. The agent does not open a label file of a team member before
the freeze is committed.

## 6. What is written, whatever the figures

1. The share answered and alike of rule v1 and of the frozen rule on the test
   points, for each chip and for the two reference chips together, with
   intervals.
2. For `chip_001`: how much of the chip each rule calls water, beside what the
   labels say.
3. If the frozen rule is not better than rule v1 on the test points by more
   than its interval allows to say, that sentence: "not shown to be better".
4. **No earlier figure is replaced.** The radar comparisons at Sukhothai and
   on the held-out chip stay as they were reported, against rule v1. A second
   comparison against the frozen rule may be given beside them, marked as
   made afterwards.
5. Whether the images of Mae Sai are read with rule v1 or with the frozen
   rule is decided after step 4, by an amendment of the plan for those images
   that is committed before any of them is opened.

## 7. Limits known before the start

- The test points lie on the same three images the rule is developed on.
  They measure the rule on those images. How it does on a new image is only
  estimated by leaving one chip out, on labels by the agent.
- 240 development points are few for a trained classifier. A simple rule is
  preferred for that reason.
- The agent's labels may share a blind spot with the rule: both read the same
  four bands.
- Three chips of two days in one region. None covers Mae Sai, and none shows
  a mountain valley with shadow and cloud, which the images of Mae Sai will.
