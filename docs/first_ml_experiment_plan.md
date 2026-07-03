# First ML Experiment Plan

Current status: not allowed yet. The first real-data ML experiment starts only after the data, licensing, reference-mask, and baseline gates pass.

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

The non-ML threshold baseline remains the benchmark. The ML model must beat or clarify the baseline before it can feed the decision layer.

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

ML output may replace fixture flood probability in the decision layer only when:

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
