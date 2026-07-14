# Flood-label factory readiness

Status: engineering foundation only; human and independent-data gates remain explicit.

## Checks

| Check | Phase | Status | Severity | Blocker |
| --- | --- | --- | --- | --- |
| weak_reference_seed_scope | phase_0 | ready_for_seed_only | high | None for seed selection; official validation and unqualified labels remain blocked. |
| cleared_training_labels | phase_1 | blocked | critical | A weak-reference manifest cannot clear training labels, even if a legacy flag is relaxed; a verified labelset validation receipt is required. |
| canonical_projected_grid | phase_1 | ready | critical | - |
| reviewer_calibration_complete | phase_1 | blocked | critical | Provide a verified passing reviewer-calibration receipt; calibration cells remain ineligible for model training. |
| blind_double_review | phase_1 | blocked | critical | Human review is incomplete, unpaired, unlocked, not independently blinded, or not bound to exact agreement and provenance hashes. |
| immutable_training_labelset | phase_1 | blocked | critical | No verified training-eligible labelset validation receipt exists. |
| query_model_safety_boundary | phase_2 | blocked | critical | The legacy gate is hardened, but no query committee can be trained until reviewed training labels exist. |
| geographic_generalization | phase_3 | blocked | critical | More cells from the same scene do not establish event or basin transfer. |

## Decision

The label factory is not training- or decision-ready. 6 critical or legacy-safety checks remain blocked.

Query-model and annotation outputs remain non-operational, not field validation, not an official warning, and ineligible for FPPS.
