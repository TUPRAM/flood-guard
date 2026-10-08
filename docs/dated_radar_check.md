# Radar candidates against the dated agency layer of 22 October 2024 at Mae Sai: result

**What this is.** The first comparison of FloodGuard's three radar methods on
the study district itself with a reference that has a date: the layer UNOSAT
and GISTDA dated 22 October 2024. Work package 3. No planning score, no class
and no exposure or access figure is computed, and it is not an official
warning.

**How to read every figure.** The agency layer was not checked in the field,
and it may have been made from the same Sentinel-1 pass (taken on 22 October
at 06:16 Thai time). Each figure is agreement with that layer. None is
accuracy. The layer shows late-season residual water, 3.6 km²; it says
nothing of the September flood.

- Plan, committed before any radar of that date was read: `docs/proposal_execution/dated_radar_check_plan_v1.md`
- Reference record, committed before the comparison: `outputs/dated_radar_check/mae_sai_20241022_reference_v1.json`
- Result and receipt: `outputs/dated_radar_check/mae_sai_20241022_v1.json`, `…_v1_receipt.json`
- Code: `src/floodguard/dated_radar_check.py`, `scripts/build_dated_radar_check.py`
- Source time: agency layer of 22 October 2024; Sentinel-1 of 21 October 2024, 23:16 UTC. Confidence: low.
- The layer is held at the `local` level (decision log R33). The rasters and the picture stay outside Git; the figures here are for the whole district.

## The frame

| | |
|---|---:|
| Cells compared (Mae Sai district, 10 m, outside permanent water) | 3,045,629 (304.6 km²) |
| Of them, agency water | 36,189 (3.62 km², 1.2%) |
| Agency water on cropland | 98% |
| Agency water that lies inside the 2024 season layer | 99% |

## Result: the image before decides everything

The methods compare the image of 21 October with an image before. The plan
named two: 22 August 2024 as the primary reading, and 12 April 2024, in the
dry season, as a second reading.

**Primary reading: before = 22 August 2024.**

| Method | Flagged | Of the flagged, agency water | Of the agency water, flagged | IoU | Cells with an answer |
|---|---:|---:|---:|---:|---:|
| UN-SPIDER reproduction | 0.57 km² | 0.9% | 0.1% | 0.001 | 100% |
| M1-literal | 105.8 km² | 0.5% | 14.0% | 0.005 | 100% |
| M1-v2 (frozen) | 0.004 km² | 0% | 0% | 0 | 0.4% |

**Second reading: before = 12 April 2024, dry season.**

| Method | Flagged | Of the flagged, agency water | Of the agency water, flagged | IoU | Cells with an answer |
|---|---:|---:|---:|---:|---:|
| UN-SPIDER reproduction | 6.61 km² | 38.2% | 69.8% | 0.33 | 100% |
| M1-literal | 102.1 km² | 3.5% | 98.5% | 0.035 | 100% |
| M1-v2 (frozen) | 0 km² | no figure | 0% | 0 | 0% |

Leaving out the cells at the edge of the layer changes little (UN-SPIDER,
second reading: 35% and 76%).

**The sentences the plan fixed beforehand, applied as written:**

- UN-SPIDER and M1-literal: the two readings differ by far more than a factor
  of two. The choice of the image before decides the result, and neither
  reading is preferred after the fact.
- M1-v2 flags less than a tenth of the agency water in both readings: it does
  not see the residual water of that date. It gave no answer for almost every
  cell.

## What this says

1. **With an image from the wet season as "before", the rules see nothing.**
   Against 22 August, UN-SPIDER flags one cell in a thousand of the agency
   water. A likely reason, not tested here: the fields that held water on
   22 October were already wet in August, and a change rule cannot see water
   that was there before. Almost all of the agency water lies inside the area
   mapped as flooded at some time since 1 August.
2. **With a dry-season image, the simplest rule agrees well.** UN-SPIDER
   flags 70% of the agency water, and 38% of what it flags is agency water.
   An intersection over union of 0.33 is the best agreement any of our
   methods has had with an agency layer on the study district. On cropland,
   where the water is, it is 70% and 40%.
3. **M1-literal is not usable as an extent.** In both readings it flags a
   third of the district, about 100 km² against 3.6 km² of agency water.
4. **M1-v2 declines.** Its safeguards refuse to answer on these tiles. That
   is the method failing closed, as designed; it is also a method that gave
   no reading on either date at Mae Sai.

## What follows for the project

- **The reference image is a method choice that must be stated.** The runs of
  record for September 2024 used the pass of 3 September as "before": a
  wet-season image, twelve days before the event. This result suggests the
  same test should be made there with a dry-season image. That is a new run
  with its own plan and is not done here; without a dated reference for
  September it could not be judged anyway (the THEOS-2 scene and the UNOSAT
  data were asked for on 7 October).
- **For the pitch.** One honest sentence is now available: on the study
  district, against a dated agency layer, the standard UN-SPIDER practice
  with a dry-season reference flags 70% of the mapped water; with a
  wet-season reference it flags almost none. It has to be said with the
  caveat that the agency layer may come from the same radar pass.
- **For the classifier of work package 7.** Its plan fixed 22 August as the
  image before, and was committed before this result was read. This result
  says that the change features will carry little in its training data. The
  plan is not changed; it declared a model without the image before for this
  reason.
- **Nothing here feeds a score.** The radar candidates stay outside every
  planning score, as before.

## Limits

- One district, one date, 3.6 km² of reference water, almost all on cropland.
- The agency's sensor and method are not documented in the file, and the
  layer has no "not observed" class: where the agency mapped no water, the
  cell counts as dry. Water the agency missed counts against a method that
  found it.
- The images before and after are 60 days (primary) and 192 days (second
  reading) apart. Over half a year, harvest and soil moisture change the
  radar signal too; part of what UN-SPIDER flags outside the layer may be
  that.
- Two readings were declared and both are reported. No third image was tried.

## Credits

UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0). Changed
by FloodGuard: repaired, projected and put on a 10 m grid over Mae Sai
district; the figures derived from it are shared under CC BY-SA 4.0. Contains
modified Copernicus Sentinel data 2024, processed by Microsoft Planetary
Computer (terrain-corrected gamma0). ESA WorldCover 2021 v200 (CC BY 4.0).
Copernicus DEM GLO-30. Boundaries: HDX Thailand COD-AB.

## To run it again

The comparison refuses to run a second time without `--replace` and a reason.

```bash
python scripts/build_dated_radar_check.py reference --external-root <external-data-root>
```

```bash
python scripts/build_dated_radar_check.py compare --external-root <external-data-root>
```
