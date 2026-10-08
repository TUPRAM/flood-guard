# A supervised radar flood classifier: result

**What this is.** Work package 7. Four models were trained to read water from
a Sentinel-1 image pair, with the agency layer of 22 October 2024 in eight
districts of northern Chiang Rai as labels. They were frozen and then tested
once: on Mae Sai district against the same agency layer, and on the THEOS-2
tile at Sukhothai against the water read from the image. The three fixed
radar rules of the project were counted on the same cells.

It is an observation model: every feature comes from the radar pair, or is
slope or land cover. It is report-only. It feeds no component, no planning
score and no class, and it is not an official warning.

**How to read every figure.** Each figure is agreement with a reference
layer. None is accuracy. At Mae Sai the reference is an agency layer that was
not checked in the field and may come from the same radar pass. At Sukhothai
the reference is another sensor, 44 hours earlier, on one tile of 8 km².

- Plan, committed before any model was fitted and before the result of work package 3 was read: `docs/proposal_execution/radar_flood_classifier_plan_v1.md`
- Freeze record, committed before any test label was read: `outputs/radar_flood_classifier/chiang_rai_20241022_freeze_v1.json`
- Result and receipt: `outputs/radar_flood_classifier/chiang_rai_20241022_v1.json`, `…_v1_receipt.json`
- Code: `src/floodguard/radar_flood_classifier.py`, `scripts/build_radar_flood_classifier.py`
- Source time: labels of 22 October 2024; THEOS-2 of 30 July 2025, 03:33 UTC. Confidence: low.
- The training layer is held at the `local` level (decision log R33): rasters, feature tables and models stay outside Git.

## What was done

| Step | What |
|---|---|
| Training cells | Eight districts, 35.9 million cells of 10 m outside permanent water; 270,610 of them (0.75%) inside the agency layer |
| Sample | 150,000 water cells and 450,000 others, with weights that put the true share back |
| Features | Backscatter after and before (VV, VH, 5 by 5 mean), their change, VH minus VV, the spread of VH, slope, land cover. Nothing that says where water usually stands |
| Models | **Primary:** boosted trees on all features. Comparisons: a random forest on all features; boosted trees without the image before; a baseline with one feature, VH after |
| Tuning and cut | Spatial blocks of 3 km in 5 folds inside the training districts; isotonic calibration; the cut with the best intersection over union out of fold, frozen with the model |
| Test A | Mae Sai district, 3.05 million cells, 1.2% agency water, the same radar pair |
| Test B | The THEOS-2 tile at Sukhothai, 80,988 cells, 36% water on the image, another radar pair, another year |

## Result 1: on the independent tile, the classifier of the plan is not an improvement

The plan fixed beforehand: the classifier is named as an improvement only if
the primary model is better than all three fixed rules on test B, by 0.03 or
more in intersection over union.

**Test B, THEOS-2 tile at Sukhothai:**

| | Of the flagged, water on the image | Of the water on the image, flagged | IoU |
|---|---:|---:|---:|
| **Primary: boosted trees, all features** | 92% | 11% | **0.11** |
| Random forest, all features | 89% | 11% | 0.11 |
| Boosted trees without the image before | 85% | 45% | 0.41 |
| Baseline: one feature, VH after | 83% | 64% | 0.57 |
| Fixed rule: UN-SPIDER practice | 72% | 29% | 0.26 |
| Fixed rule: M1-literal | 61% | 50% | 0.38 |
| Fixed rule: M1-v2 | 76% | 22% | 0.21 |

**The primary model is not better than any of the three fixed rules. It is
not named as an improvement.** It flags a ninth of the water the image shows.

Two comparison models are better than all three fixed rules: the one-feature
baseline and the trees without the image before. As the plan says, neither
is renamed as the result. They are reported, and what they suggest is
written below as something to test, not as something shown.

## Result 2: why the primary model fell short

1. **It ranks the cells well; its cut does not carry.** Without any cut, the
   primary model orders the cells of the tile slightly better than every
   other model (average precision 0.81 against 0.78 for the baseline). The
   cut was learned where 0.75% of the ground is water. On a tile where 36% is
   water, the same cut leaves most of the water below it. The plan named this
   limit beforehand.
2. **The features that need the image before did not travel.** In training
   the image before was 60 days older, at Sukhothai 12 days. The trees that
   use it fall to 11%; the trees that do not reach 45%.
3. **One feature carries nearly everything.** Shuffling VH after costs the
   primary model 0.33 of average precision on the tile; no other feature
   costs more than 0.03.
4. **Withholding the unsure cells does not help.** With values between 0.3
   and 0.7 withheld, 95% of the tile's cells still get an answer and almost
   none of them is "water".

## Result 3: on the study district, the trained models agree with the agency layer where the fixed rules do not

**Test A, Mae Sai district, agency layer of 22 October 2024:**

| | Of the flagged, agency water | Of the agency water, flagged | IoU |
|---|---:|---:|---:|
| Primary: boosted trees, all features | 62% | 56% | 0.42 |
| Random forest, all features | 61% | 57% | 0.41 |
| Boosted trees without the image before | 55% | 63% | 0.42 |
| Baseline: one feature, VH after | 30% | 59% | 0.24 |
| Fixed rules, same image pair | under 1% | 0% to 14% | under 0.01 |

The models were fitted on eight other districts and carried to Mae Sai with
little loss (0.51 out of fold, 0.42 at Mae Sai). The primary model's values
are well calibrated there (Brier score 0.0065, calibration error 0.002).

This shows less than it seems. The agency layer may come from the same radar
pass, so a model trained on it learns the agency's reading of that picture.
And the fixed rules stand near zero here only because their image before was
from the wet season (work package 3): with a dry-season image the UN-SPIDER
practice reaches 0.33.

## What the two comparison models suggest

The baseline is as simple as a model can be: **a cell is flagged when its VH
backscatter after the event, averaged over 5 by 5 cells, is at or below about
-18.5 dB.** One number, learned from the agency layer in Chiang Rai. On the
THEOS-2 tile it flags 64% of the water with 83% of its flags on water, where
the best fixed rule flags 50% with 61%.

That is one tile. It was not the model the plan named, and it is weaker at
Mae Sai, where it flags far more than the agency mapped (30% of its flags on
agency water). It also needs no image before, which is the thing that undid
the fixed rules at Mae Sai. **It is a candidate to test, not a result to
cite.** The test that would settle it: run the two frozen comparison models,
unchanged, on a second THEOS-2 tile (the Nan chips of 31 July 2025, work
package 5), with the plan written first.

## What follows for the project

- **For the pitch.** The honest sentence: "We trained a radar classifier on
  agency labels and tested it on an independent THEOS-2 image. The full
  model did not carry over; a single backscatter threshold did better than
  our rules, and that is what we will test next." With the susceptibility
  model this is the second time the simplest model was the one that held on
  new ground.
- **The fixed rules stay the project's radar reading**, and no radar reading
  enters a planning score.
- **Built-up ground stays a blind spot.** No model finds the little water
  the image shows in the built-up cells of the tile.
- **A dated reference for September 2024 would change what can be tested.**
  The same code could then be trained and tested on the study event. The
  THEOS-2 scene and the UNOSAT data were asked for on 7 October; no reply
  yet.

## Limits

- One date of training labels: shallow residual water on fields in October.
  The models may have learned "dark fields in October".
- One independent tile, one event, 8 km². A model that is better there by
  0.19 in intersection over union may not be better elsewhere.
- At Sukhothai the radar passed 44 hours after the THEOS-2 image. Water that
  drained in between, and water under rice, count against every model.
- The share of water differs by a factor of fifty between training and the
  tile. Calibrated values do not carry over; only the ranking and the frozen
  cut were tested.
- "Boosted trees" is scikit-learn's `HistGradientBoostingClassifier`, not the
  XGBoost library. Importance is by shuffling a feature, not SHAP.
- Thoeng, Mae Fa Luang and the districts further south were left out of
  training; Mueang Chiang Rai and Phan are reserved and were not read.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed
by FloodGuard: repaired, projected and put on a 10 m grid; the figures derived
from it are shared under CC BY-SA 4.0. THEOS-2 sample imagery: GISTDA, for the
GeoHackathon. Contains modified Copernicus Sentinel data 2024 and 2025,
processed by Microsoft Planetary Computer. ESA WorldCover 2021 v200
(CC BY 4.0). Copernicus DEM GLO-30. Boundaries: HDX Thailand COD-AB.

## To run it again

The `test` stage refuses to run a second time without `--replace` and a
reason.

```bash
python scripts/build_radar_flood_classifier.py features --external-root <external-data-root>
```

```bash
python scripts/build_radar_flood_classifier.py fit --external-root <external-data-root>
```
