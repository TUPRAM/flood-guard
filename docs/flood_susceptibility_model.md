# A trained flood-susceptibility model for the Mae Sai area: result

**What this is.** The proposal's method 2, run for the first time: a Random
Forest and gradient-boosted trees, with a one-feature baseline beside them,
fitted on Mae Sai district and tested once on the three districts that border
it. The model says how likely a 30 m cell is to lie inside the area that
UNOSAT and GISTDA mapped as water in the 2024 season. That is susceptibility.
It is not a flood map of any day and not a forecast, it feeds no part of the
planning score, and it is not an official warning.

**How to read every figure.** The label is an agency season layer made mostly
from radar and not checked in the field. Each figure is agreement with that
layer on ground the model never saw. None is accuracy against the ground.

- Plan, committed before any model was fitted: `docs/proposal_execution/flood_susceptibility_model_plan_v1.md`
- Freeze record, committed before the test districts were read: `outputs/flood_susceptibility/mae_sai_model_v1_freeze.json`
- Result, receipt and map: `outputs/flood_susceptibility/mae_sai_model_v1.json`, `…_v1_receipt.json`, `…_v1_map.png`
- Code: `src/floodguard/flood_susceptibility_ml.py`, `scripts/build_flood_susceptibility_model.py`
- Source time: season layer of 1 August to October 2024. Confidence: low.

## What was done

| Step | What |
|---|---|
| Cells | 30 m cells outside permanent water. Mae Sai: 338,421 cells, 25.4% inside the season layer. Test districts: 2,043,031 cells, 5.8% inside |
| Features | Elevation, slope, height above the nearest drainage (main and small streams), distance to those streams and to permanent water, upstream area, land cover. No feature comes from an image of the flood |
| Models | Baseline: logistic regression on one feature, the height above the nearest main stream. Random forest, 300 trees. Gradient-boosted trees, 200 rounds |
| Tuning | Inside Mae Sai only, by cross-validation on blocks of 3 km in 5 folds |
| Calibration | Isotonic, on the out-of-fold values of Mae Sai |
| Test | Mae Chan, Chiang Saen and Mae Fa Luang. Their flood layer was read once, after the models were frozen |

## Result 1: inside Mae Sai, the tree models look much better

Out of fold, on blocks the model did not see:

| Model | ROC AUC | Average precision |
|---|---:|---:|
| Baseline, one feature | 0.795 | 0.480 |
| Random forest | 0.896 | 0.778 |
| Gradient-boosted trees | 0.892 | 0.775 |

## Result 2: on the districts they never saw, they do not

The three test districts together:

| Model | ROC AUC | Average precision | Brier score | Calibration error |
|---|---:|---:|---:|---:|
| Baseline, one feature | 0.923 | 0.298 | 0.049 | 0.046 |
| Random forest | 0.921 | 0.358 | 0.075 | 0.077 |
| Gradient-boosted trees | 0.925 | 0.317 | 0.086 | 0.078 |

A lower Brier score and a lower calibration error are better. Always answering
Mae Sai's share of 25.4% gives a Brier score of 0.093.

By district:

| District | Cells inside the layer | Baseline AUC | Random forest AUC | Boosted trees AUC |
|---|---:|---:|---:|---:|
| Mae Chan | 6.9% | 0.868 | 0.841 | 0.872 |
| Chiang Saen | 12.6% | 0.896 | 0.905 | 0.870 |
| Mae Fa Luang | none | no figure | no figure | no figure |

Mae Fa Luang is hill country with no cell inside the season layer, so it gives
no ranking figure of its own. Its 730,000 dry cells are easy, and they lift the
figures of the three districts together above those of the two that flooded.

**Which model is cited.** The plan fixed the rule before the test: a tree
model is cited ahead of the baseline only if it is at least 0.02 higher in
both ROC AUC and average precision on the three districts together. The random
forest is 0.002 lower in ROC AUC (and 0.060 higher in average precision); the
boosted trees are 0.002 higher in ROC AUC and 0.019 higher in average
precision. Neither meets the rule. **The model to cite is the baseline: the
height above the nearest main stream.**

That is the proposal's own principle, "promote only the least complex model
that produces a measurable, defensible improvement", applied as written.

## Why the tree models did not carry over

1. **They learned Mae Sai's elevations.** Shuffling elevation costs the random
   forest 0.042 of ROC AUC on the test cells, four times more than any other
   feature. A height above sea level that marks the Sai plain says little in
   the next valley. Slope and the distance to a main stream made the test
   figures slightly worse.
2. **They say "flooded" too readily elsewhere.** Mae Sai has 25% of its cells
   inside the layer, the test districts 6%. Of the cells the random forest
   scores at 0.9 or more, 44% are inside the layer. Its Brier score in Chiang
   Saen is worse than always answering 25%.
3. Leaving land cover out changes little (ROC AUC 0.919 against 0.921), so the
   radar's preference for open land is not what the trees mainly learned.

## Result 3: what the cited model can and cannot say

The baseline never gives a value above 0.6. It cannot say "this floods". What
it can do is clear ground:

- It gives 85% of the test cells a value below 0.3, and 98.6% of those cells
  are outside the season layer.
- The remaining 15% of cells hold 80% of the layer's water cells. About 30% of
  them are inside the layer.

Read as a planning aid: **low ground near a main river is where to look, and
it is about a seventh of the land.** Where exactly the water goes inside that
seventh is not something terrain alone decides.

## Result 4: Mae Sai's tambons

Mean out-of-fold value of the cited model beside the share of each tambon
inside the season layer:

| Tambon | Inside the season layer | Mean model value |
|---|---:|---:|
| Mae Sai | 58% | 0.20 |
| Si Mueang Chum | 52% | 0.39 |
| Ko Chang | 47% | 0.33 |
| Ban Dai | 31% | 0.41 |
| Pong Pha | 15% | 0.27 |
| Pong Ngam | 10% | 0.14 |
| Wiang Phang Kham | 0.5% | 0.10 |
| Huai Khrai | 0% | 0.15 |

The model orders the wet and the dry tambons roughly right and **misses Mae
Sai town**, the worst-hit place of 2024. The town was flooded by the Sai
River, which rises in Myanmar and enters the model's window at the border. A
terrain model of the Thai side cannot see that water coming.

## What follows for the project

- **The project now has a trained and tested model to name**, and the honest
  statement about it: three models were trained, the simplest one is the one
  that holds outside the district it was fitted on, and it is a screening
  layer.
- **It supports the design of the decision chain.** Susceptibility says where
  to look; it does not replace a flood observation. That is what the proposal
  says of method 2 without dated labels.
- **It is not in any score.** Using it for a preparedness reading without a
  flood event would need a new protocol version and is not proposed here.
- **A dated reference would change this.** With the GIS data of UNOSAT product
  3991 or a THEOS-2 scene of September 2024, the same code could be fitted to
  a dated extent, which is what method 2 asks for before it may refine an
  event probability. Both were asked for on 7 October; no reply yet.

## Limits

- One season, one province, three test districts, of which one has no water in
  the layer.
- The label under-counts water under trees and between buildings, and the
  model inherits that.
- Upstream area is cut at the edge of the hydrology window; rivers that enter
  from outside are under-counted until they are mapped as permanent water.
- The calibration is that of Mae Sai. The test shows that it does not carry
  over for the tree models and only partly for the baseline (its values near
  0.5 are inside the layer 31% of the time).
- Permutation importance is reported where the proposal names SHAP; that
  package is not installed.
- "Gradient-boosted trees" is scikit-learn's `HistGradientBoostingClassifier`,
  not the XGBoost library.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed
by FloodGuard: repaired, projected, cut to four districts and put on a 30 m
grid; the figures derived from it are shared under CC BY-SA 4.0. Copernicus
DEM GLO-30. ESA WorldCover 2021 v200 (CC BY 4.0). Boundaries: HDX Thailand
COD-AB.

## To run it again

The `features` stage needs pysheds. The `test` stage refuses to run a second
time: the test districts are read once.

```bash
python scripts/build_flood_susceptibility_model.py features --external-root <external-data-root>
```

```bash
python scripts/build_flood_susceptibility_model.py fit --external-root <external-data-root> --replace --reason "<why>"
```
