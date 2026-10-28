# Learning the water rule from the team's labels: amendment 1 to plan v1

Written 12 October 2026, after the one run of plan v1
(`outputs/theos2_water_label_ml/result_v1.json`) and before any second fit.
Plan v1 is not edited: the result of the first run names it by SHA-256.

## What the first run gave

Share of the labelled area where the map gives the label at least two of
three team members gave, the three chips together:

| Map | Share |
|---|---|
| Rule v1 | 0.72 |
| Rule v2 | 0.85 |
| One index, learned | 0.59 |
| Logistic regression, twelve features | 0.43 |
| Random forest | 0.53 |
| Boosted trees | 0.53 |

By the rule of the plan no model is better than rule v2. Every one is worse
by 0.25 to 0.42, far outside its interval.

## Why, and whose mistake

The plan divided each band by the median of that band over the chip, "so
that the two acquisition days are on one scale". That was the assistant's
choice and it was wrong. A median over a chip depends on what the chip
holds. The flooded-town chip is mostly water, so its near infrared median is
a water value; the no-flood chip's median is a land value. After the
division the same water has a different value on each chip, and an index
computed from the divided bands shifts with it. The clearest sign: the model
that learns one threshold on the index of rule v2 finds 73% of the labelled
water on one chip and none of it on the flooded-town chip, where rule v2,
reading the same index without the division, finds about two thirds of it.

So the first run does not answer the question of the plan. It answers
another one: features that depend on the make-up of a scene do not carry
from scene to scene. That is worth keeping, and it stays on record as run 1.

## The second run

One thing changes: the features. They are computed from the bands as read,
with no scaling by chip. Only ratios of two bands are used, because a ratio
does not change when both bands are brighter or darker by the same factor.
The raw band values and their mean are dropped for that reason.

1. (green − NIR) / (green + NIR)
2. (NIR − red) / (NIR + red), the index of rule v2
3. (blue − NIR) / (blue + NIR)
4. (red − green) / (red + green)
5. and 6. mean and standard deviation of feature 2 in the 5 by 5 pixels
7. and 8. mean and standard deviation of feature 1 in the 5 by 5 pixels

Everything else is as in plan v1: the label, the four models and their
settings, the seed, one chip left out at a time, the area-weighted main run
with the equal-weight run beside it, the score, and the human figure.

## The rule for reading it, made stricter

This is a second attempt made after seeing a result, so it has to clear a
higher bar. Eight comparisons with rule v2 have now been made or planned
(four in each run). A model of the second run is called better than rule v2
only if its difference with rule v2, in the main run over the three chips
together, is above zero by more than 2.73 standard errors (the 95% level
shared over eight comparisons).

One more reading is fixed now, because the first run showed it matters: each
team member agrees with the label of the other two on 0.83 to 0.88 of the
area. A map at that level is as close to the labels as the labellers are to
each other. Rule v2 is at 0.85. So even a model that passes the bar above
would be better at copying these labels, not shown to be better at finding
water.

Unchanged: rule v2 stays the rule that reads the images of Mae Sai, and the
result is written up whichever way it comes out. Output:
`outputs/theos2_water_label_ml/result_v2.json`.
