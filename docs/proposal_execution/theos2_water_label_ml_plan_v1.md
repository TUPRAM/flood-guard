# Learning the water rule from the team's labels: plan v1

Written 12 October 2026, before any model was fitted on the labels and before
any feature was read at a labelled point. On Putu's word of 12 October: "is
there any machine learning process that involved in this process? If not, can
you work on that for me".

Label of everything this plan produces: report only, confidence low. A water
map of an image is not an observation of a flood and not an official warning.
Nothing here enters a planning score.

## 1. Where the labels stand

Three team members labelled 300 points on three THEOS-2 chips as water, not
water or cannot tell (`docs/theos2_water_label_check.md`). The labels were
used for one thing: to measure two hand-written rules. Rule v1 gives the
label at least two of the three gave on 69% of the labelled area, rule v2 on
78%.

No model has been trained on these labels. That was on purpose. The points
were the test, and a test that is also the training material tests nothing.
The classifiers of `docs/theos2_water_rule_v2.md` were trained on other
labels (made by the assistant on other points) and lost to the simple rule.

## 2. The question

Can a classifier that learns from the team's labels read water from the four
THEOS-2 bands better than rule v2 does?

## 3. How the labels can train and test at once

By leaving one chip out at a time. A model is fitted on the labelled points
of two chips and predicts the points of the third. Each chip is left out
once, so every point is predicted by a model that never saw its chip. The
three sets of predictions are scored together.

This is the weakest honest design the data allow: 300 points, three chips,
two acquisition days, one region and one season. It says whether a learned
rule carries from two chips to a third. It does not say that it carries to
Mae Sai.

## 4. What is fixed before any fit

**Label.** The label at least two of the three gave, where it is water or
not water. A point without such a label is left out of the fit and of the
score, as in the label check.

**Features of a point**, from the scene read at 2 m as the rules read it.
Each band is first divided by the median of that band over the chip, so that
the two acquisition days are on one scale.

1. to 4. blue, green, red, near infrared
5. (green − NIR) / (green + NIR)
6. (NIR − red) / (NIR + red), the index of rule v2
7. (blue − NIR) / (blue + NIR)
8. the mean of the four bands
9. and 10. mean and standard deviation of near infrared in the 5 by 5 pixels
   (10 m) around the point
11. and 12. mean and standard deviation of feature 6 in the same 5 by 5 pixels

**Models**, with no setting searched:

| Name | What it is |
|---|---|
| one index | Logistic regression on feature 6 alone: the threshold of rule v2, learned from the labels instead of set by hand |
| logistic | Logistic regression on the twelve features, standardised, C = 1 |
| forest | Random forest, 500 trees, at least 5 points in a leaf |
| boosting | Gradient-boosted trees (histogram), depth 3, 200 rounds, learning rate 0.1 |

Seed 20261012 for every model.

**Weights in the fit.** The sample is drawn in six groups and over-draws the
hard places (edges, small objects). In the main run each point counts for the
area it stands for (pixels of its group over points of its group), so the fit
is for the image and not for the sample. Beside it, one run where every point
counts the same.

**Score.** The figure the label check used to compare two rules: of the area
with a label, the share where the map gives an answer and the answer is the
label, estimated with the six groups of each chip as strata (Stehman 2014).
For each model the difference with rule v2 on the same points, with its
standard error. A model answers at every point; rule v2 sets some points
aside as unobservable and they count against it, as before.

**A human figure beside it.** Each team member scored the same way against
the label the other two agree on. A model that reaches that figure is at the
limit of what these labels can show.

## 5. The rule for reading the result

Four models are compared with rule v2, so one of four can look better by
chance. A model is called better than rule v2 only if, in the main run and
over the three chips together, its difference with rule v2 is above zero by
more than 2.50 standard errors (the 95% level shared over four comparisons).
Anything less is written as "not shown to be better".

Whatever the result:

- Rule v2 stays the rule that reads the images of Mae Sai. That choice was
  frozen on 12 October before this plan and an amendment would be needed to
  change it.
- If a model is better by the rule above, the next step is a plan to test it
  on new points, not to use it.
- The result is written up whichever way it comes out, including "the simple
  rule is as good".

## 6. What this cannot show

- The labels disagree: all three gave the same label on 57% of the points. A
  model learns the majority's reading, with its mistakes.
- Three chips make three folds. The spread between folds is large and is
  reported, not averaged away.
- The points were drawn in groups cut from rule v1. Area weights correct the
  estimate; they do not put points where rule v1 never looked.
- No ground check exists for any of the three chips.

## 7. Files

- `src/floodguard/theos2_water_label_ml.py`: the features, the folds, the fit.
- `scripts/build_theos2_water_label_ml.py`: one run; a second needs
  `--replace --reason`.
- `outputs/theos2_water_label_ml/result_v1.json`: the figures.
- `docs/theos2_water_label_ml.md`: the account.

The scenes stay outside Git. The result holds no pixel of them.
