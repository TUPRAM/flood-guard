# Calibration-role grid preparation

FloodGuard assigns dataset roles before label acquisition. The sealed Mae Sai
`canonical_supported_pool_v1` grid is the immutable parent evidence: all 20
parent tiles and all 854 supported 32 x 32 query cores remain
`training_and_query_pool` in that release.

The calibration reserve must be allocated at parent-tile level. Copying 12
query rows and changing their role would create two roles inside the same
spatial block and would bypass canonical grid validation.

## Two-stage authority gate

1. `plan_label_factory_calibration_reserve.py` verifies the sealed parent grid,
   verifies aligned static-context hashes and grids, compares whole-parent-tile
   reserve combinations, and emits an immutable provisional design.
2. A named Reference Authority chooses or rejects a candidate. Their
   attributable approval belongs in a separate versioned evidence package.
3. Only after approval may a later command create and validate a new canonical
   grid release with the approved parent tiles assigned
   `reviewer_calibration`.
4. Final calibration query selection, reference construction, reviewer bundle
   creation, and human review happen after that grid release. They are not part
   of reserve planning.

The planner defaults to 12 first-attempt calibration queries plus 12 fresh
retest queries across at least two parent spatial blocks. Because the reserve
is tile-level, the actual reserved capacity will generally be greater than 24.

## Allowed planning evidence

The planner reads only:

- the self-hashed canonical grid release and its file manifest;
- supported-query counts and source-validity fields;
- governed aligned ESA WorldCover composition;
- governed aligned JRC permanent-water context;
- governed aligned Copernicus DEM slope and optional hillshade; and
- parent-tile grid coordinates for spatial separation.

Static context describes composition and terrain. It does not establish
temporary flood in September 2024. The planner rejects known weak-label,
reference-label, reviewer-label, selection-score, probability, prediction,
entropy, and disagreement columns.

Candidate scoring uses these fixed weights:

| Component | Weight | Meaning |
|---|---:|---|
| Capacity efficiency | 0.40 | Preserve enough unseen capacity without unnecessarily removing query-pool capacity |
| Land-cover coverage | 0.20 | Cover more of the governed WorldCover classes already present in the pool |
| Context dispersion | 0.15 | Prefer different static-context signatures between reserved parent tiles |
| Spatial separation | 0.15 | Prefer different parent spatial blocks |
| Source coverage | 0.10 | Prefer strong governed SAR support and complete static-context coverage |

The score is a deterministic design aid, not an automated scientific approval.
Candidates within 0.005 of the top score are marked as near ties. If a near-tied
candidate reserves fewer queries, the package must show the authority the
explicit tradeoff: the higher-ranked option may provide stronger static-context
or spatial dispersion, while the lower-capacity option preserves more of the
future training/query pool. The planner does not choose that governance tradeoff
on the authority's behalf.

## Provisional output contract

The output directory is write-once and contains:

- `tile_context_summary.csv`: context-only summaries for every parent tile;
- `candidate_reserve_combinations.csv`: ranked tile combinations;
- `authority_pending_role_allocation.csv`: the top candidate expressed as a
  proposed role design;
- `authority_decision_request.md`: the exact decision and confirmations the
  Reference Authority must provide;
- `README.md`: the package safety boundary; and
- `design_receipt.json`: self-hashed lineage, parameters, outputs, and safety
  state.

The role-allocation CSV deliberately says
`valid_tile_assignments_input=false`. It must never be passed to the canonical
grid builder. Every eligibility field is false, including human annotation,
active selection, review queue, query-model training, post-review training,
decision layer, FPPS, and warning.

The receipt must also retain:

```text
status = provisional_authority_approval_pending
uses_weak_or_reference_labels = false
uses_reviewer_annotations = false
uses_model_outputs = false
uses_event_time_flood_claims = false
final_calibration_query_ids = []
final_retest_query_ids = []
review_bundles_created = false
human_evidence_created = false
```

### Receipt-schema compatibility

The original immutable design v1 and v2 packages use
`floodguard.calibration_reserve_design.v1` and predate the near-tie fields.
Design v3 uses the same v1 schema with a hash-bound optional near-tie extension.
The verifier therefore treats that v1 extension atomically: the planning
threshold and authority-review object must either both exist or both be absent.
When present, the verifier validates them fully; their absence remains valid for
the self-hashed legacy packages.

All newly generated packages use
`floodguard.calibration_reserve_design.v2`. Schema v2 requires the near-tie
threshold, authority-review tradeoff, and matching candidate-table columns.
This keeps future validation strict without retroactively changing or rejecting
the frozen v1/v2 bytes.

## Command

```powershell
python scripts/plan_label_factory_calibration_reserve.py `
  --canonical-grid-directory <canonical_supported_pool_v1> `
  --context-alignment-manifest <context_alignment_manifest.json> `
  --output-directory <new-versioned-design-directory> `
  --design-id mae_sai_calibration_role_design_v1 `
  --calibration-query-count 12 `
  --retest-query-count 12 `
  --reserve-tile-count 2
```

Do not reuse an existing output directory. Do not place approval evidence into
the provisional directory. A corrected design or an authority decision creates
a new versioned directory and new hashes.

## Remaining Reference Authority decision

The authority must approve one candidate tile combination, select another
ranked candidate with a rationale, or reject every candidate and describe the
missing context or spatial coverage. Approval must explicitly acknowledge that
the context metrics are not flood truth and that the final 12 calibration and
fresh-retest query IDs are still unselected and unseen.

Until that attributable decision and a new canonical grid receipt exist, no
calibration reference, reviewer bundle, first-20 bundle, ML training table,
decision-layer input, FPPS input, or warning input may be produced from the
design.
