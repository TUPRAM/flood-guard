# Baseline — 2026-07-30 run 1

The first **internally consistent** GeoAI artifact set: one execution of
`run_real`, one signed receipt, frozen together.

## Why this replaces the previous baseline

The artifacts previously committed under `outputs/geoai/` were assembled from at
least three separate executions across three commits:

```
geoai_metrics.json              b07bebd  2026-07-23
extra_methods_metrics.json      095c39e  2026-07-24
geoai_subdistrict_priority.csv  debe413  2026-07-28
subdistricts.geojson            b07bebd  2026-07-23
geoai_component_summary.csv     b07bebd  2026-07-23
```

No single run of any version of the pipeline would reproduce that set together,
so it could not serve as a reference. Comparing against it produced an apparent
`max|dFPPS| = 3.39` "regression" that was not one — Sentinel-1 and the
Copernicus DEM were both verified byte-deterministic across repeated fetches,
and the SAR code and thresholds were unchanged across every commit.

## Reproducibility, demonstrated

Two consecutive 120-epoch passes with identical configuration:

- every non-Component-B metric **identical**
- `FPPS max|delta| = 0.000000`
- all 8 action classes identical

## Run configuration

```
--water-label external
--water-label-raster research/skills/owm_label/water_label_owm.tif
120 epochs · torch 2.13.0+cu126 · RTX 3060 Laptop
```

## Known state of this baseline

- **Component B's metric is flagged `degenerate`.** The OmniWaterMask label is
  correct (0.325 % vs JRC 0.371 %) but too sparse: 352 positive pixels in the
  train role against a 2,000 floor. `train` and `val` are unscoreable and the
  `test` figure collapsed to the majority class. It is recorded, not published
  as accuracy. See `docs/run_plan_governed_rerun_v1.md` §12.2–12.4.
- `osm_completeness_flag` is `over_expectation_review_needed` for all 8 tambons:
  Overture returns ~2.7x the population-implied building count and that has not
  been validated.
- `can_feed_decision_layer` is `false`. This is candidate evidence.

## Updating

If a change is *intended* to move FPPS, re-freeze here in the same commit and
say why in the message. `test_decision_layer_invariance.py` compares against
this directory; editing its tolerance to make a run pass defeats the point.
