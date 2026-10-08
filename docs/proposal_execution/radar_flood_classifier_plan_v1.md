# A supervised radar flood classifier: plan v1

Written on 9 October 2026. Work package 7 of the order the team accepted
(item V-15); its result becomes item V-19. Written while the comparison of
work package 3 was running and before its result was read. No classifier has
been fitted and no training label has been set against a radar value.

## 1. Question

The three radar methods of the project are fixed rules on the change between
two images. On the THEOS-2 tile at Sukhothai they flagged a quarter to a half
of the water the image shows.

Can a classifier that is trained on a dated agency layer read water from a
Sentinel-1 image pair better than those rules, on ground and on an event it
never saw, when an independent sensor is the judge?

## 2. What it is and is not

- An **observation** model: every feature comes from the radar pair, or is a
  mask the fixed rules use as well (slope, land cover). No feature says where
  water usually stands: no elevation, no height above a stream, no distance
  to a river, no coordinate. That keeps it apart from the susceptibility model
  of work package 4.
- Report-only. It feeds no component, no planning score and no class. A use
  in the planning chain would need a new protocol version and is not proposed.
- Not an official warning, and not a map of the September 2024 flood.

## 3. Data

| Role | Where | Label | Radar pair |
|---|---|---|---|
| Training | Eight districts of northern Chiang Rai: Chiang Saen, Mae Chan, Khun Tan, Phaya Mengrai, Chiang Khong, Doi Luang, Wiang Chiang Rung, Wiang Chai | Layer of UNOSAT and GISTDA dated 22 October 2024 | 22 August 2024 and 21 October 2024 |
| Test A | Mae Sai district | The same layer | The same pair |
| Test B | The THEOS-2 tile at Sukhothai, 30 July 2025 | Water read from the THEOS-2 image (the committed reference of the cross-check) | 19 July 2025 and 31 July 2025 |

- Mueang Chiang Rai and Phan are reserved for cases SE2 and SE2-blind and are
  not read. Thoeng lies partly outside the radar frame, Mae Fa Luang and the
  districts further south hold no water in the layer; they are left out to
  keep the work small.
- Cells of permanent water (WorldCover class 80) are left out everywhere.
- Test A is agreement with the agency layer on a district the model never
  saw. The agency layer may come from the same radar pass, so test A cannot
  show that the model sees water; it shows that the model learned the
  agency's reading and carries it to another district.
- **Test B is the one that counts.** Another province, another year, and a
  reference from another sensor.

## 4. Features, per 10 m cell

1. Backscatter after, VV and VH, in dB, as a 5 by 5 mean.
2. Backscatter before, VV and VH, in dB, as a 5 by 5 mean.
3. Change, after minus before, VV and VH.
4. VH minus VV after.
5. Spread of VH after inside the 5 by 5 window.
6. Slope in degrees (Copernicus DEM).
7. Land cover (ESA WorldCover 2021 class).

A second, smaller feature set leaves out everything that needs the image
before (items 2 and 3). It is declared now because the pairs differ: 60 days
apart in training, 12 days apart at Sukhothai.

## 5. Models

| Name | What |
|---|---|
| Baseline | Logistic regression on one feature: VH after |
| **Primary** | Gradient-boosted trees (scikit-learn `HistGradientBoostingClassifier`) on all features |
| Comparison 1 | Random forest on all features |
| Comparison 2 | Gradient-boosted trees on the features without the image before |
| Fixed rules | UN-SPIDER practice, M1-literal, M1-v2, as recorded in work package 3 and in the THEOS-2 cross-check |

- Training sample: at most 150,000 agency-water cells and 450,000 other
  cells, drawn at random with a fixed seed, in proportion to each district's
  share. Weights put the true share of water back for calibration and for
  every figure.
- Tuning inside the training districts only, on spatial blocks of 3 km in
  5 folds. Small grids, every trial reported.
- Calibration: isotonic, on the out-of-fold values of the training districts.
- The cut that turns a value into "water" is the one with the highest
  intersection over union on the out-of-fold values. It is frozen with the
  models.

## 6. Order of work

1. This plan is committed.
2. Features and labels of the training districts are built. Mae Sai's labels
   and the Sukhothai tile are not touched.
3. The models are tuned, fitted, calibrated and frozen; the freeze record is
   committed.
4. The test runs once on test A and test B. A second run needs `--replace`
   and a reason, and the first stays in the record.

## 7. Figures

For each model and each test: ROC AUC, average precision, and at the frozen
cut the share of flagged cells that is reference water, the share of
reference water flagged, and intersection over union. For test A also the
Brier score and the calibration error. For test B the same by land cover.
For the primary model: which features carry it (permutation on test B), and
the share of cells left without an answer when values between 0.3 and 0.7
are withheld.

## 8. What will be said, fixed beforehand

- "Better than a fixed rule" on a test means: intersection over union higher
  by 0.03 or more than that rule's on the same cells.
- **The classifier is named as an improvement only if the primary model is
  better than all three fixed rules on test B.** Test A alone is not enough.
- If the primary model is not better on test B and a comparison model is,
  the text says so and does not rename the comparison model as the result.
- If no model is better on test B, the text says that a classifier trained
  on agency labels of one date did not carry over, and the fixed rules stay
  the project's radar reading.
- Whatever comes out, the model stays outside every planning score.

## 9. Rights and where things are kept

As in work package 3 (decision log R33): the dated layer is held at the
`local` level. Rasters, feature tables, the fitted models and any picture of
the layer stay outside Git. The records in Git hold figures by district or
for the whole frame. The THEOS-2 sample is used under the terms of the
hackathon as in the cross-check.

## 10. What was already seen

- The result of the THEOS-2 cross-check at Sukhothai, for the three fixed
  rules (decision log R26). The classifier has never been run there.
- The area of the dated layer by district (R33).
- Not seen when this plan was written: the result of work package 3 at Mae
  Sai, any radar value of 2024 beside a label, any fitted classifier.

## 11. Limits known beforehand

- One date of training labels, late in the season: shallow residual water on
  fields. The model may learn "dark fields in October", which is not the
  same as a flood.
- The agency's method is not documented in the file, and the layer has no
  "not observed" class.
- At Sukhothai the radar came 44 hours after the THEOS-2 image, and water
  under rice does not darken the radar signal. No classifier can flag water
  the radar did not record.
- The share of water differs a great deal: about 1% of the training
  districts, 36% of the Sukhothai tile. Calibrated values will not carry
  over; ranking and the frozen cut are what is tested.
