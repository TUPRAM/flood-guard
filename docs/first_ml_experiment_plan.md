# First ML Experiment Plan

Current status: blocked for a new real-data ML run. The preserved logistic experiment is historical screening evidence from the retired COG pair; the active same-track original-SAFE inputs cannot be used for training until the signed controlled-experiment loaders verify acquisition authority, qualified reviewer evidence, immutable spatial partitions, reference cells, and bounded execution authorization.

## Start Conditions

All conditions are required:

1. A flood reference mask has confirmed geometry access.
2. The reference-mask license allows local analysis.
3. Derived validation metrics may be published or shared in the intended demo context.
4. Redistribution status is documented as `redistributable` or `reference_only`.
5. A pre-event and post-event Sentinel-1 pair is locked to the reference-mask date or flood peak.
6. Local source file paths are recorded outside Git.
7. SHA-256 checksums are recorded for source products and reference masks.
8. `processing_allowed=True` in the ingestion manifest for the relevant file-level row.
9. The non-ML SAR baseline has produced IoU, F1/Dice, precision, recall, and area error metrics.

If any condition fails, ML remains blocked.

Historical exception (closed; not authorization for a new run):

- The repository preserves one previously completed small logistic experiment against the manual weak-reference mask.
- The experiment must use a spatial holdout and must compare against the non-ML threshold baseline.
- Outputs must say `weak-label experiment`, `not official labels`, and `not field validation`.
- The historical output records `can_feed_decision_layer=False` unconditionally. Improvement against the same weak mask is screening evidence only and cannot authorize a flood input.
- This exception does not clear the official Mae Sai validation gate, does not create official labels, and does not authorize emergency-warning use.
- The exception is no longer executable. `scripts/run_mae_sai_weak_label_ml.py` rejects the current weak-reference row immediately. Even a structurally complete summary row remains insufficient because hash-shaped strings do not prove signed receipts or partition membership; the legacy writer directs qualified work to `floodguard.controlled_experiment` instead. That runner must verify a `qualified_expert_or_adjudicated` reference, source bytes and permitted uses, qualified reviewer calibration with zero unresolved disagreements, immutable non-overlapping train/calibration/final-holdout membership, and bounded execution authorization.

The current gate implementation is:

- `docs/provider_response_logging_guide.md` for provider replies.
- `docs/mae_sai_file_manifest_v2.md` for required file-level rows.
- `outputs/mae_sai_real_data_file_manifest.csv` for current blocked file status.
- `outputs/mae_sai_validation_summary.md` for the blocked or metric-backed validation report.
- `src/floodguard/sar_baseline.py::run_gated_real_sar_change_baseline` for the gated non-ML SAR formula once a legal pixel/object table exists.

## First Model Scope

The first model should be small and auditable. Do not start with a deep model.

Recommended first ML candidate:

- model family: lightweight tabular classifier
- features: VV drop, VH drop, VV ratio, VH ratio, combined drop, optional elevation/slope/permanent-water flags later
- label: legally usable binary reference flood mask
- split rule: spatial holdout by tile, polygon, or connected area; do not use random pixel splits as the only evidence
- output: `flood_probability_0_1` and `binary_flood_extent`

The non-ML threshold baseline remains the benchmark for this research comparison. Beating or clarifying it does not override weak-label provenance and does not make the ML output decision-layer eligible.

Current weak-label implementation:

- module: `src/floodguard/weak_label_ml.py`
- runner: `scripts/run_mae_sai_weak_label_ml.py`
- metrics: `outputs/mae_sai_weak_label_ml_metrics.csv`
- prediction manifest: `outputs/mae_sai_weak_label_ml_prediction_manifest.csv`
- summary: `outputs/mae_sai_weak_label_ml_summary.md`

These outputs are candidate-only and are not a substitute for the future cleared-label ML experiment.

## Minimum Metrics

Report at least:

- IoU
- F1/Dice
- precision
- recall
- area error ratio
- false positive notes near permanent water, radar shadow, steep terrain, and urban surfaces
- calibration or reliability caveat for probability output

## Promotion Rule

This weak-label ML output may not replace fixture flood probability. A separate cleared-label model-promotion programme would require:

- the reference mask is legally usable
- the ingestion manifest allows processing
- the non-ML baseline is reproducible
- ML metrics are documented against the baseline
- the output includes source timestamp, confidence, and assumptions
- the dashboard and action briefs clearly remain non-operational

## Immediate Next Work Before ML

1. Send licensing requests using `docs/licensing_request_templates.md`.
2. Complete the reference-mask licensing tracker v2 in `docs/reference_mask_licensing_log.md`.
3. Commit a reviewed CDSE metadata snapshot only if needed for a stable candidate list.
4. Add file-level ingestion rows with product ids, local paths, checksums, and licensing status once files are legally acquired.
5. Run the synthetic SAR baseline and validation metric tests to keep the contract green.
6. Generate `outputs/mae_sai_validation_summary.md`; it must remain blocked until the manifest gates pass.
