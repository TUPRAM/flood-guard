# Learning the water rule from the team's 300 labels

Written 12 October 2026. Plan:
`docs/proposal_execution/theos2_water_label_ml_plan_v1.md` and its amendment
1. Figures: `outputs/theos2_water_label_ml/result_v1.json` (first run) and
`result_v2.json` (second run).

**Label of everything on this page:** report only, confidence low. The
figures say how often a map of an image gives the label team members gave
when they looked at the same image. They are not a check on the ground. A
water map of an image is not an observation of a flood and not an official
warning, and nothing here enters a planning score.

## What the three label files had been used for

Callixta, Putu and Rachmania each labelled the same 300 points on three
THEOS-2 chips as water, not water or cannot tell. Until now the labels did
one job: they were the test. Two hand-written rules were read at the 300
points and compared with the label at least two of the three gave
(`docs/theos2_water_label_check.md`).

No machine learning was involved in that. It was arithmetic: count where
rule and label agree, weight each point by the area it stands for, and give
an interval.

No model had been trained on the labels either, on purpose. A test that is
also the training material tests nothing. The classifiers tried earlier for
rule v2 were trained on other labels, made by the assistant on other points.

## What was done now

The question: can a classifier that learns from the team's labels read
water better than rule v2?

To let the same labels train and test, one chip is left out at a time. A
model learns from the labelled points of two chips and is asked about the
third, which it has never seen. Each chip is left out once. This is the
weakest honest design 300 points on three chips allow.

Four models, fixed before any fit, with no setting searched:

| Model | What it is |
|---|---|
| One index | The index of rule v2, with its threshold learned from the labels instead of set by hand |
| Logistic regression | A weighted sum of all features |
| Random forest | 500 decision trees |
| Boosted trees | Trees built one after another, each correcting the last |

## Result

Share of the labelled area where the map gives the label at least two of
the three team members gave. Second run, main fit, 275 points with a label.

| Map | Three chips together | Sukhothai | Flooded town | No flood |
|---|---|---|---|---|
| Rule v1 (hand-written) | 0.72 | 0.79 | 0.60 | 0.78 |
| **Rule v2 (hand-written)** | **0.85** (0.81 to 0.89) | 0.82 | 0.74 | 0.99 |
| One index, learned | 0.87 | 0.78 | 0.85 | 0.99 |
| Logistic regression | 0.72 | 0.77 | 0.40 | 0.99 |
| Random forest | 0.73 | 0.80 | 0.40 | 0.99 |
| Boosted trees | 0.73 | 0.86 | 0.37 | 0.96 |

Difference with rule v2, three chips together:

| Model | Difference | 95% interval | Called better by the rule of the plan? |
|---|---|---|---|
| One index, learned | +0.02 | −0.01 to +0.06 | no |
| Logistic regression | −0.13 | −0.17 to −0.09 | no: worse |
| Random forest | −0.12 | −0.15 to −0.08 | no: worse |
| Boosted trees | −0.12 | −0.16 to −0.07 | no: worse |

For scale: each team member, scored the same way against the label the
other two agree on, reaches 0.83, 0.83 and 0.88.

## Reading

1. **No trained model is shown to be better than rule v2.** Rule v2 stays.
2. **Learning the threshold gives about what setting it by hand gave.** The
   learned threshold is more generous: it finds 85% of the labelled water
   where rule v2 finds 69%, and 81% of what it calls water is labelled
   water where rule v2 has 88%. It does better on the flooded town and
   worse at Sukhothai. The two-point gain is inside its interval.
3. **The richer models do not carry to a chip they have not seen.** With
   the flooded town left out they find 9% to 16% of its labelled water.
   What Sukhothai and the no-flood chip teach about water does not hold in
   a flooded town, where the water is muddy and lies between buildings. On
   Sukhothai, which resembles the training chips more, they are as good as
   the rules. This is the same lesson as the radar classifier and the
   earlier optical trials: with three scenes, a simple rule carries further
   than a model with many inputs.
4. **Rule v2 is already as close to the labels as the labellers are to each
   other** (0.85 against 0.83 to 0.88). Above that level a model would be
   copying these labels better, not finding water better. More modelling on
   these 300 points cannot show much more. Better labels could: more
   chips, and a ground check.

## The first run, and a mistake of the assistant's

The plan divided each band by its median over the chip, to put the two
acquisition days on one scale. That was wrong. A chip's median depends on
what the chip holds: the flooded-town chip is mostly water, the no-flood
chip is land. After the division the same water had a different value on
each chip. In that first run every model was far worse than rule v2 (0.43
to 0.59 against 0.85), and the model with one learned threshold found none
of the flooded town's labelled water.

The first run stays on record. The amendment, written before any second
fit, changed the features only (ratios of two bands as read, which need no
scaling) and raised the bar for calling a model better, because a second
attempt after seeing a result deserves less trust: 2.73 standard errors,
the 95% level shared over the eight comparisons of both runs. A test on
invented chips now shows the fault and that the new features do not have
it.

## Can labelling be automated?

Partly, and this result says where.

- A rule or a model can label the easy points. On the no-flood chip every
  map but rule v1 is right on 96% to 99% of the area.
- The hard points are the ones people disagree on: all three gave the same
  label on 57% of the 300 points, and the disagreement is at edges, in mud
  and between buildings. A model trained on the majority label inherits
  that, and here the models were worst exactly there.
- A sensible use of machine help is the one proposed before: let rule v2
  label everything, and have people look only where the rule is near its
  threshold or where two rules disagree. That cuts the work without making
  the machine its own judge.

## What this does not show

- All three team members gave the same label on 57% of the points. The
  "label" is a majority reading of an image, not ground truth.
- Three chips make three folds: one image of one place on one day each.
  None covers Mae Sai.
- The points were drawn in groups cut from rule v1, with more points at
  edges and small objects. Area weights correct the estimate; they do not
  put points where rule v1 never looked.
- Eight comparisons were made in two runs. The one positive difference is
  small and is not read as a finding.

## What follows

- Rule v2 reads the images of Mae Sai when they arrive, as already frozen.
- The learned threshold is not adopted. If the team wants a more generous
  rule for flooded towns, the way is a plan with new points on a flooded
  town, not these labels again.
- For the pitch: "We tried to beat our simple rule with three trained
  models on our own labels. They did not carry to a scene they had not
  seen. The simple rule is as close to our labels as we are to each other."

## To make the figures again

```text
python scripts/build_theos2_water_label_ml.py --theos2-dir <folder of the THEOS-2 files> --external-root <external data root>
python scripts/build_theos2_water_label_ml.py --amendment-1 --theos2-dir <...> --external-root <...>
```

A result that exists is computed again only with `--replace --reason`. The
scenes stay outside Git; the results hold no pixel of them.
