# Controlled-model promotion review policy

## Purpose and authority boundary

This policy layer reviews a completed controlled comparison; it does not train
models and it does not promote a raster into FloodGuard's decision layer. Its
only positive outcome is `candidate_selected`, meaning that one model satisfied
a predeclared report-only policy and ranked first under its deterministic
tie-break. Both possible outputs remain:

- `operational_status=non_operational`;
- `official_warning=false`;
- `can_feed_decision_layer=false`; and
- `requires_separate_decision_layer_acceptance=true`.

A selected candidate still needs a separate, independently reviewed acceptance
receipt before it can supply flood probability to zonal aggregation or FPPS.

## Evidence contract

The review accepts only the following immutable chain:

1. An HMAC-SHA256 signed, expiry-bound policy issued before the result. The
   policy explicitly names the experiment, study area, all three required model
   families, filenames, minimum IoU/Dice/precision/recall, maximum absolute
   area-error ratio/Brier/ECE, the complete error-category set, the minimum
   measured cell count required in every category, and a deterministic
   tie-break ending in model ID.
2. An independently HMAC-SHA256 signed, expiry-bound controlled comparison
   receipt. It must be `completed_report_only`, non-operational, not an official
   warning, and decision-layer ineligible. A result that already claims a
   selected/promoted candidate is rejected.
3. The exact receipt-bound files for metrics, reliability-bin calibration,
   error categories, and phase-level runtime. Both filename and SHA-256 must
   match the policy and result receipt.

The metrics file must contain exactly the deterministic SAR baseline,
weak-label logistic model, and GeoAI candidate evaluated on the same untouched
final spatial holdout. Its schema is exact: each row binds the signed model-run
threshold, final-holdout group and cell counts, equal-area cell size, confusion
counts, predicted and reference areas, signed and absolute area errors, IoU,
Dice/F1, precision, recall, Brier score, ECE, and decision-layer ineligibility.
The reviewer independently recomputes all confusion-derived and physical-area
fields and requires the same holdout population and grid for all three rows.
Unexpected columns fail closed. Calibration bins must cover `[0,1]`, be
contiguous, use the identical ordered bin grid for all three models, and
reproduce each reported ECE. Error evidence must contain false-positive and
false-negative counts for `all`, permanent water, wet soil/agriculture, radar
shadow, layover/double-bounce, steep terrain, urban surface, speckle,
narrow-channel, boundary-disagreement, temporal land-cover change, noisy input,
reference-label uncertainty, and geometry-mismatch strata for every model.
Runtime evidence has one row per signed model identity with finite phase times,
total time no shorter than the measured phases, positive peak memory, and
device and hardware-class descriptions.

All receipts are self-hashed and HMAC signed with runtime-supplied,
role-separated internal integrity keys.
Private absolute paths, symbolic-link evidence, checksum or filename
substitution, missing fields, duplicated rows, untrusted keys, expired evidence,
and existing output paths fail closed.

## Policy authoring rule

There are intentionally no default thresholds in source code or documentation.
Scientific and safety reviewers must predeclare the numerical limits for the
specific controlled experiment, sign them before the comparison result exists,
and document why those limits are appropriate. Test fixtures use synthetic
numbers only and are not FloodGuard acceptance criteria.

The CLI reads HMAC keys only from environment variables:

```text
python scripts/build_controlled_model_promotion_decision.py policy --help
python scripts/build_controlled_model_promotion_decision.py recommend --help
```

## Current integration state

The promotion-review contract and controlled-result v4 writer are integrated.
The result writer emits a separately HMAC-signed, expiry-bound receipt plus
checksum-bound metrics, calibration, reliability SVG, error-stratum, runtime,
and summary artifacts. It constructs and re-verifies the complete bundle in a
unique sibling staging directory, then publishes the directory with one rename;
any serialization, render, signing, or checksum failure removes staging and
leaves no partial final-named bundle. This is software capability only: the
current Mae Sai gate remains blocked, no qualified controlled result exists,
and no model has been selected or promoted.
