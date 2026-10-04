# Signing forms: Mae Sai reference, review and evaluation gates

Prepared 24 September 2026 from `GATE_RESEARCH_DOSSIER.md`. **Nothing here is
signed, and nothing here is evidence.** Each form is pre-filled with what
research can supply. The fields that only the named person may decide are left
`null` or `<…>`: decisions, attestations, limits, names, timestamps and hashes.
Do not fill those fields for someone else.

## Order

| # | Form | Who signs | Consumed by | Unlocks |
| --- | --- | --- | --- | --- |
| 0 | *(no form)* Set `CDSE_USERNAME` / `CDSE_PASSWORD`, then run `python scripts/acquire_cdse_mae_sai_sentinel2_reference.py` | Acquisition owner | writes `outputs/cdse_mae_sai_sentinel2_reference_acquisition_manifest.csv` with SHA-256 | Byte identity of the reference imagery |
| 1 | `01_rights_owner_sentinel2.md` | Rights / acquisition owner | Human record today; see "Contract gaps" | Step 1 |
| 2 | `02_human_roles_worksheet.md` | Each of RA, A, B, C, plus the project owner | `scripts/build_label_factory_human_roles.py` (pre-calibration package) | Appointed people |
| 3 | `reference_procedure_v2_sentinel2_DRAFT.md`, then `03_reference_authority_decision_request.template.json` | Reference Authority | `scripts/build_reference_authority_approval.py` | Step 2, then the 12 + 12 calibration release |
| 4 | `04_observation_evaluation_plan.draft.json` | Evaluation lead | `scripts/evaluate_mae_sai_observation.py` (requires `status: "frozen"`) | Step 4 |

After form 3 is approved, the existing chain runs unchanged on the machine
holding the external workspace:

1. Build the 12 + 12 calibration membership release:
   `build_label_factory_calibration_release.py build` then `validate`.
2. Build the A and B calibration bundles:
   `build_label_factory_review_bundle.py --review-purpose reviewer_calibration`.
3. Record the calibration reference and receipt:
   `rasterize_calibration_reference.py`, `freeze_label_factory_calibration_reference.py`,
   then `build_reviewer_calibration_receipt.py`.
4. Formal review, adjudication, consensus and label release, following
   `docs/label_factory_runbook.md` §8–11.
5. Evaluation and the landing switches:
   `evaluate_mae_sai_observation.py --role development`, then `final_holdout`
   after the custodian opens it, then `build_landing_gate_status.py`.

## Contract gaps a person must decide before the Sentinel-2 route can run

These are deliberate fail-closed boundaries in the current code. They need a
versioned contract change approved by the Reference Authority. They were not
patched around.

1. **Rights clearance knows four sources only.**
   `label_factory/rights_clearance.py` accepts exactly `sentinel1`,
   `jrc_global_surface_water`, `esa_worldcover_2021` and `copernicus_dem_glo30`.
   Recording Sentinel-2 rights in the governed package needs a `v2` decision
   schema that adds `sentinel2_l2a`. Until then, form 1 is a signed human
   record.
2. **Review bundles reject optical context.** The production bundle writer
   admits only governed SAR, permanent-water, land-cover and terrain layers
   ("ungoverned … optical context are rejected"). Reviewers labelling from
   Sentinel-2 need an authority-approved Sentinel-2 display. That display
   should go through the same candidate → lineage receipt → authority decision
   path used for the VV/VH change display (`build_review_derivative_candidates.py`),
   extended to optical bands.
3. **Real label releases cannot validate yet.**
   `qualified_label_release` and `multi_event_preflight` stop at
   `validated_synthetic_fixture_only` until the independent release-authority
   validator exists (`ml_authorization.md`, gate 2). Until then the evaluation
   runner and the "Blind review and adjudication" landing switch stay closed,
   by design.

## Why a machine cannot fill the blanks

Each blank records an accountable human judgement: who is qualified, whether
19.5 hours is acceptable, where the pass/fail line sits, and whether A and B
really worked blind. The software checks bytes, hashes, timestamps and
consistency. It does not verify identity, competence or honesty
(`human_roles.py` `IDENTITY_STATUS = "not_independently_verified_by_software"`).
