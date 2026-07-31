# Mae Sai calibration-reference procedure v1

Document version: `calibration_reference_procedure_v1`  
Protocol version: `label_factory_protocol_v1`  
Taxonomy version: `flood_label_v1`  
Status: **fixed proposal awaiting attributable Reference Authority approval**

This procedure defines how the confidential reference for the 12-query Mae Sai
reviewer calibration is created and frozen. It does not create a reference,
select a query, approve a display, authorize calibration, release a label, train
a model, or support FloodGuard's decision layer, FPPS, or warnings.

## 1. Preconditions

Do not begin reference construction until all of these exist and validate:

1. an immutable pre-calibration human-role package with an accepted, qualified
   Reference Authority, two distinct proposed reviewers, and Adjudicator C;
2. an attributable Reference Authority design-decision package approving one
   whole-parent-tile reserve candidate and this exact document hash;
3. a new immutable canonical grid release assigning sufficient spatial blocks to
   `dataset_role=reviewer_calibration`, while preserving separate fresh-retest
   capacity;
4. a fixed, rights-cleared processing/alignment receipt and approved reviewer-
   evidence design;
5. an immutable 12-query calibration manifest drawn only from the approved
   reserve, with no weak-label, model, entropy, disagreement, acquisition-rank,
   reviewer-answer, or future-test evidence; and
6. access controls that keep the authority reference hidden from Reviewers A and
   B until both calibration submissions are locked.

The 12 calibration queries and the fresh-retest queries must be disjoint. Neither
set may later enter training, development, active selection, or the first 20.

## 2. Evidence the authority may see

The Reference Authority may use only the fixed evidence package approved for this
version:

- pre-event VV dB and event-time VV dB with the same fixed display parameters;
- pre-event VH dB and event-time VH dB with the same fixed display parameters;
- any explicitly approved, lineage-bound VV/VH change or fixed composite;
- JRC permanent-water context, ESA WorldCover, slope, and hillshade as context;
- the core boundary and a fixed surrounding context halo; and
- the source timestamps, processing/alignment receipt, confidence limitations,
  and declared assumptions.

The authority must not see the Mae Sai weak polygon, logistic/boosted predictions,
model probabilities, uncertainty/disagreement scores, acquisition ranks, active-
learning reasons, reviewer work, or the first-20 selection. Static context is not
event-time flood truth.

## 3. Canonical states

Every reference cell uses exactly one state:

| Code | State | Procedure meaning |
| ---: | --- | --- |
| 0 | `dry_land` | Observable land without persuasive event-time inundation |
| 1 | `temporary_flood` | Persuasive event-time inundation absent or materially lower before the event |
| 2 | `permanent_or_preexisting_water` | Water already present or supported as normal/pre-existing water |
| 3 | `uncertain_water_change` | Observable change whose flood meaning cannot be resolved |
| 4 | `unobservable_or_artifact` | No-data, shadow/layover, failed support, misalignment, or uninterpretable evidence |
| 255 | `unreviewed` | Outside a deliberately partial reviewed extent only |

Codes 3, 4, and 255 must never be mapped to dry. Code 255 is not a drawable
decision. For a full 32 x 32 reviewed core, no cell may remain 255.

## 4. Geometry and completeness

For each query, the authority creates one locked annotation and a geometry-control
record under the canonical multipart contract.

- The reviewed extent must be explicit and contained by the 32 x 32 core.
- Drawable class geometry uses only codes 0, 1, 2, 3, and 4.
- Different classes may not claim the same canonical cell centre.
- Every cell inside the reviewed extent must be explicitly drawn or covered by an
  explicit primary-class fill rule.
- Cells outside a justified partial reviewed extent remain 255; they are not dry.
- A 255-only query, missing query, extra query, out-of-core geometry, class overlap,
  or silent unpainted area fails reference construction.
- Boundaries follow the fixed cell-centre rasterization rule. Displayed raster
  edges or visual antialiasing do not change canonical membership.

When evidence is ambiguous, use code 3. When the ground cannot be interpreted,
use code 4. Do not make the reference more complete by forcing unsupported 0/1/2
decisions.

## 5. Lock, rasterize, inspect, and freeze

1. The Reference Authority records actual start/finish/lock UTC times, confidence,
   evidence used, assumptions, ambiguity reasons, and an attributable identity.
2. Lock the authority annotation log and geometry parts; later corrections append
   a new revision and never overwrite prior bytes.
3. Run `scripts/rasterize_calibration_reference.py` against the exact 12-query
   manifest and attributable role-evidence file.
4. Verify the self-hashed rasterization lineage, exact query coverage, grid/source
   hashes, annotation-content hashes, geometry hash, cell counts, class counts,
   confidentiality, and all negative safety flags.
5. The authority visually inspects the rasterized cells against the approved
   evidence package. Any error returns to a new locked authority revision.
6. Run `scripts/freeze_label_factory_calibration_reference.py` once to create the
   immutable reference cell CSV and self-hashed reference manifest.
7. Revalidate the frozen reference from copied bytes before reviewer delivery.

The reference is best-available expert/adjudicated evidence, not absolute ground
truth. Its manifest must state temporal, alignment, SAR-physics, context, and
boundary limitations.

## 6. Confidentiality and reviewer independence

- Reviewers A and B receive identical approved evidence designs but separate
  writable return areas.
- Neither reviewer receives the reference, authority geometry, weak mask, model
  output, selection evidence, or the other reviewer's work.
- The operator does not open one reviewer's return while the other is still able
  to edit. Each return is locked and checksummed on receipt.
- Any accidental exposure is recorded immediately. The Reference Authority
  decides whether the affected query or entire calibration must be replaced with
  fresh unseen reserve material.
- The reference may be opened for scoring only after all 24 expected reviewer-
  query submissions (12 per reviewer) are locked.

## 7. Calibration scoring and failure

The fixed minimum gates are:

- temporary-flood Dice: `>= 0.75`;
- Cohen's kappa: `>= 0.75`;
- mean boundary F1: `>= 0.70`; and
- critical-stratum Dice: `>= 0.65`.

Both named reviewers must satisfy the receipt contract on the exact same hidden
reference and query set. A failing result creates only a failure diagnostic. It
does not authorize formal review. Remediation uses documented feedback and a
fresh, previously unseen retest set; it never edits the failed submissions or
reuses the exposed answer set as unseen calibration.

## 8. Permanent exclusions

Calibration queries, fresh-retest queries, authority reference cells, reviewer
calibration labels, failure diagnostics, and calibration metrics are permanently
ineligible for query-model training, active selection, development/test scoring,
the first 20, the decision layer, FPPS, and warnings.

Only a cryptographically valid passing reviewer-calibration receipt for the exact
appointed A/B role IDs can support a later post-calibration human-role package.
Only that later package can open the separate first-20 bundle gate.

## 9. Required approval statement

The appointed Reference Authority must approve or reject this exact document
version and SHA-256 in an attributable email export, signed PDF, or message
export. The decision must include UTC time and rationale, and confirm:

- the reserve uses static non-label context only;
- the 12 calibration and fresh-retest queries remain unseen and unselected at
  design-approval time;
- the reference remains hidden until both reviewers lock;
- uncertainty, unobservability, and code 255 are preserved as specified;
- no model, weak-label, training, FPPS, warning, or operational claim is created;
  and
- approval permits only the next separate reserve/reference construction step,
  not a reviewer bundle or calibration execution.
