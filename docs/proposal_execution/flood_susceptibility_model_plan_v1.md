# A trained flood-susceptibility model for the Mae Sai area: plan v1

**Status: plan, committed before any feature of the test districts was built
and before any model was fitted.** It follows the proposal's method 2
(calibrated Random Forest and gradient-boosted trees) and its rule of
pre-specification (section 3.6.5). The result is report-only. It feeds no
component, no FPPS and no A-E class, and it is not an official warning.

- Written: 8 October 2026, by the AI coding agent (work package 4; decision
  log R27, item V-15 of the team page, accepted by all three members on
  8 October). The owners can overturn it.

## 1. What the model is, and what it is not

The proposal says of method 2: "With timestamp-matched labels they can refine
event probability, without them they remain a susceptibility layer and cannot
replace current flood extent." The project has no dated, rights-cleared flood
map of September 2024. It has the season layer of UNOSAT and GISTDA (product
4009, CC BY-SA 4.0): every area mapped as water between 1 August and October
2024, without a date for each patch.

So the model answers one question: **given the terrain and the land cover of
a place, how likely is it to lie inside the area that was mapped as water in
the 2024 season?** That is susceptibility. It is not a flood map of any day,
it is not a detector, and a high value is not a forecast.

## 2. Areas, fixed here

| Role | District | Why |
|---|---|---|
| Training, tuning and calibration | Mae Sai (TH5709) | The study area |
| Test, never used for fitting | Mae Chan (TH5707), Chiang Saen (TH5708), Mae Fa Luang (TH5715) | The three districts that border Mae Sai. All lie inside the analysis extent of product 4009 |

Mueang Chiang Rai and Phan are not read. They are the frames of cases SE2 and
SE2-blind of protocol v1a, and their flood layer stays unopened for those
cases.

The flood layer of the three test districts is read once, after the model, its
settings and its calibration are fixed on Mae Sai. Nothing is refitted after
the test figures are seen.

## 3. Cells and label

- Grid: 30 m cells in EPSG:32647, the grid of the terrain model.
- A cell counts for a district when its centre is inside it (2022 COD-AB
  boundaries, the file protocol v1b names).
- Cells of permanent water (ESA WorldCover 2021 v200, class 80) are left out.
- Label: 1 when the cell centre is inside the accumulated layer of product
  4009, as provided and repaired (`make_valid`), 0 otherwise.

The label is an unvalidated preliminary agency extent, made mostly from radar.
Radar sees open water on fields better than water under trees or between
buildings, so the label under-counts there. The model learns the label, with
that bias.

## 4. Features, fixed here

All from open data already used by the project. No feature comes from an image
of the 2024 flood.

| Feature | Source |
|---|---|
| Elevation (m) | Copernicus DEM GLO-30 |
| Slope (degrees) | from the same DEM at 30 m |
| Height above the nearest drainage, main streams (m) | the DEM, with flow routing (pysheds); a stream is a cell with at least 25 km² upstream, or mapped permanent water |
| Height above the nearest drainage, small streams (m) | the same with 1 km² upstream |
| Distance to the nearest main stream, and to the nearest small stream (m) | the same stream cells |
| Upstream area (log10 of km²) | the same flow routing |
| Distance to permanent water (m) | ESA WorldCover class 80 |
| Land cover | ESA WorldCover 2021: tree cover, shrubland, grassland, cropland, built-up, bare, wetland, other (one column each) |

The hydrology is computed on one window that holds the four districts and
reaches north to 20.85° N. Upstream area is cut at the window edge, so a river
that enters from outside (the Sai, the Ruak, the Mekong) is under-counted
until it is mapped as permanent water. That is why permanent water counts as a
stream.

## 5. Models and settings, fixed here

1. **Baseline:** logistic regression on one feature, the height above the
   nearest main stream. This is "low ground near a river floods".
2. **Random forest** (scikit-learn): 300 trees; minimum leaf size chosen from
   20 and 100.
3. **Gradient-boosted trees** (scikit-learn `HistGradientBoostingClassifier`,
   the same family as XGBoost and LightGBM; neither of those two libraries is
   used): 200 rounds; learning rate from 0.05 and 0.1; leaves per tree from 15
   and 31; L2 penalty 1.0.

- Selection: grouped cross-validation inside Mae Sai. Cells are grouped into
  blocks of 3 km and the blocks into 5 folds, so that a fold is tested on
  ground it has not seen next door. The setting with the highest mean average
  precision is kept.
- Calibration: isotonic regression on the out-of-fold predictions of Mae Sai.
- No class weights and no resampling: the output is to be read as a share.
- Random seed 20261008 everywhere.

## 6. Figures reported, fixed here

On each test district and on the three together:

- ROC AUC and average precision;
- Brier score, and the Brier score of always answering the share of flooded
  cells in Mae Sai;
- expected calibration error (10 bins of equal width) and the reliability
  table;
- abstention: cells with a calibrated value from 0.3 to 0.7 get no answer;
  the share of cells with an answer and the agreement on them. And the whole
  risk-coverage table by distance from 0.5.

**The comparison that decides what is cited.** The proposal promotes "only the
least complex model that produces a measurable, defensible improvement". A
tree model is cited ahead of the baseline only if, on the three test districts
together, it is at least 0.02 higher in ROC AUC and in average precision. If
not, the baseline is the model to cite.

**What each feature contributes.** Permutation importance on the test cells
(drop in ROC AUC, 5 repeats). The proposal names SHAP; that package is not
installed, and permutation importance is reported in its place.

**One sensitivity run.** The chosen tree model without the land-cover columns,
because the label comes from radar, which sees open land best.

**For Mae Sai itself:** the mean out-of-fold value of each tambon beside its
flooded share in the season layer. In-sample by area, out-of-fold by cell.

## 7. What the result may and may not be used for

- It may be cited as the project's trained model, with its test figures, as
  "agreement with the 2024 season layer on three districts the model never
  saw".
- It is not an accuracy against the ground: the label is not ground truth.
- It feeds nothing. Using it in a planning score (for a preparedness reading
  without a flood event) would need a new protocol version.
- No class, no ranking of tambons for action, no statement about a day.

## 8. Outputs

- `outputs/flood_susceptibility/mae_sai_model_v1.json`: settings, figures,
  tables, with `generated_at_utc`, `source_timestamp`, `confidence_class`,
  `assumptions`, `limits`, `official_warning: false` and
  `operational_status: non_operational`.
- A receipt with the SHA-256 of every input and of this plan, and one figure.
- `docs/flood_susceptibility_model.md`: the result in plain words.
- The feature rasters, the cell tables and the fitted model stay outside Git.

Credits: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0;
figures derived from it are shared under the same licence). Copernicus DEM
GLO-30. ESA WorldCover 2021 v200 (CC BY 4.0). Boundaries: HDX Thailand COD-AB.
