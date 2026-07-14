# Active-learning and flood-label-factory task audit

Status date: 2026-07-12 UTC

## Overall assessment

The software foundation now satisfies the requested active-learning design at
the implementation-and-test level, including a dedicated internal operator
package. The real Mae Sai data preparation is substantially complete: source
VV/VH, canonical queries, `sar_change_v2` pool features, static context strata,
and positive-unlabeled weak-query summaries exist.

The project does **not** yet satisfy the task as a completed real active-learning
experiment. No released human labelset, trained real query committee, selected
model-based round, real operator queue, paired formal reviews, or measured
active-versus-random efficiency result exists. Those outputs cannot be created
honestly before the human calibration and release gates pass.

## Requirement matrix

| Requirement | Current status | Evidence and limitation |
| --- | --- | --- |
| Pre/event Sentinel-1 VV and VH | Real and verified | September 3/15 descending SAFE products, four terrain-corrected aligned dB rasters, processing/alignment receipt v2 |
| VV/VH drop/change | Real and verified | 874,496 `sar_change_v2` pool rows contain direct pre-minus-event VV/VH dB change |
| VV/VH ratio and combined change | Legacy diagnostic only | Present in the historical weak-label experiment; deliberately excluded from canonical v2 because ratios are redundant with dB change and two conflicting legacy combined formulas exist |
| Mae Sai weak-reference mask | Real, now integrated safely | 854 per-query summaries; 4 weak-positive/boundary queries, 850 wholly unreviewed; exterior never becomes dry land |
| Additional unlabeled Mae Sai tiles | Real and verified | 20 parent tiles, 854 supported non-overlapping 32 x 32 cores |
| Other Thailand flood events | Missing | Hat Yai has metadata candidates only; no second processed pair/grid/pool |
| Permanent water, terrain, urban, forest strata | Real and verified | JRC, Copernicus DEM, and WorldCover context; current strata include steep terrain, urban, forest, cropland, water edges, and other context |
| Logistic baseline | Implemented and tested | Transparent persisted query model; no real human-release training run yet |
| Shallow gradient-boosted challenger | Implemented and tested | Shallow histogram gradient boosting; no real human-release training run yet |
| Repeated spatial-block CV | Implemented and tested | Deterministic grouped folds, default 5 splits x 3 repeats; no real OOF evidence yet |
| Ensemble disagreement | Implemented and tested | Absolute and Jensen-Shannon disagreement at cell/query level |
| Entropy or threshold distance | Implemented and tested | Normalized entropy plus explicit committee distance from 0.5 |
| Diversity sampling | Implemented and tested | Spatial separation, near-duplicate checks, stratum/event caps, greedy diversity, 60/20/20 active/hard/random lanes |
| Second review and agreement | Implemented, no real evidence | Separate blinded A/B lanes, agreement/boundary/critical-stratum metrics, adjudication; no completed formal reviews |
| Internal review package fields | Implemented | Operator package joins location, model means, entropy/disagreement, context, positive-unlabeled weak evidence, priority, and optional checksum-verified preview |
| Reviewer blinding | Implemented and tested | Model, weak, score, rank, priority, operator, and preview fields are denied from reviewer-visible output |
| Report-only/no FPPS | Fully enforced | Fixed safety flags plus decision-layer ingress rejection |

## Work completed in the 2026-07-12 audit run

1. Materialized and revalidated the real Mae Sai feature pool:
   `features/sar_change_v2_pool_v1/sar_change_v2_cells.csv`.
2. Added the batch GPKG-to-query positive-unlabeled bridge:
   `src/floodguard/label_factory/weak_query_summary.py` and
   `scripts/build_weak_query_summary.py`.
3. Materialized `weak_seed/manual_weak_query_summary_v2` for all 854 cores.
4. Preserved query-level mean logistic, boosted, and committee predictions plus
   the distance from 0.5 in the region candidate bridge.
5. Added a write-once, self-hashed internal operator queue package:
   `src/floodguard/label_factory/operator_queue.py` and
   `scripts/build_active_learning_operator_queue.py`.
6. Expanded reviewer-field deny-lists to prevent leakage of every new internal
   score, weak, priority, operator, and preview field.
7. Refreshed `outputs/label_factory_readiness.csv` and Markdown against the real
   governed grid. The grid is now correctly shown as ready while six human,
   release, committee, and generalization checks remain blocked.

## Current real Mae Sai evidence locations

Controlled external root:
`C:\Users\iputu\Documents\FloodGuard_external_data\label_factory\mae_sai_pilot_v1`

- Source/governance: `governance_cleared_v2`
- Processing receipt: `receipts/processing_alignment_v2.json`
- Canonical pool: `grids/canonical_supported_pool_v1`
- Context evidence: `query_support/supported_query_pool_v2`
- Feature pool pointer: `CURRENT_FEATURE_POOL.md`
- Weak-summary pointer: `CURRENT_WEAK_SUMMARY.md`
- Feature pool: `features/sar_change_v2_pool_v1`
- Weak summary: `weak_seed/manual_weak_query_summary_v2`
- Authority-pending display candidate:
  `review_context/mae_sai_change_display_candidate_v1`
- Formal hold: `human_coordination_v2/FORMAL_REVIEW_HOLD.json`

Repository implementation:

- Committee: `src/floodguard/label_factory/committee.py`
- Candidate bridge: `src/floodguard/label_factory/candidate_builder.py`
- Acquisition/diversity: `src/floodguard/label_factory/acquisition.py` and
  `sampling.py`
- Operator package: `src/floodguard/label_factory/operator_queue.py`
- Blinded reviewer package: `src/floodguard/label_factory/review_bundle.py`
- Weak query summary: `src/floodguard/label_factory/weak_query_summary.py`
- Decision/FPPS guard: `src/floodguard/decision_safety.py`

## Exact remaining blockers

1. Accepted Reference Authority, Reviewer A, distinct Reviewer B, and independent
   Adjudicator C.
2. Authority-approved unseen calibration reserve/reference procedure and display
   decision.
3. Genuine locked A/B calibration reviews and a passing calibration receipt.
4. The first 20 formal cores independently double-reviewed after that receipt.
5. Human adjudication of every required conflict.
6. Code-generated consensus, release QA, frozen labelset, and revalidation.
7. Release-bound training join from the existing feature pool.
8. First real logistic/HGB committee, model-scored pool, selected later round,
   and real operator package.
9. Measured active/random review cost and at least three evaluated rounds.
10. Additional processed Thailand development events and one untouched future
    geographic test.

Until these are real, the allowed conclusion is engineering readiness for the
human-evidence phase—not improved flood detection, reduced annotation cost, an
operational flood map, an FPPS input, or a warning capability.
