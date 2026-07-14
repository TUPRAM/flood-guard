# Real-data and ML learning guide for Mae Sai

Status: beginner learning design and report-only analysis. This guide does not
authorize formal review, label release, model training, FPPS use, or warning
use.

## 1. The honest next step

FloodGuard has enough verified real Mae Sai data for a useful **unlabelled SAR
orientation and data-quality lab now**. It does not yet have the released human
labels required for a genuine logistic-versus-HGB experiment.

That distinction matters:

- the real feature pool contains radar measurements and lineage, not flood
  truth;
- the weak polygon is positive-unlabelled evidence, so its exterior is
  unreviewed rather than dry;
- a classifier needs a target; inventing dry targets from the weak polygon's
  exterior would teach the model an unsupported assumption;
- the first genuine query committee remains blocked until consensus, release
  QA, a frozen labelset, revalidation, and the release-bound training join all
  exist.

The immediate learning path is therefore two-stage:

1. run the real-data orientation sections without creating a target or model;
2. keep the same notebook ready to unlock the logistic/HGB sections only when a
   verified release-bound training manifest is supplied.

This is not lost time. Most bad ML projects fail before model fitting because
the target, split, grain, or lineage is wrong. The orientation stage teaches
how to detect those failures.

## 2. Protect the proposed Reviewer A role

The project operator is currently a proposed Reviewer A, not an appointed or
calibrated formal reviewer. Real-data ML analysis can create prior exposure that
cannot later be removed by hiding fields.

Use one of these lanes and record the choice before opening row-level operator
evidence:

| Lane | What the operator may see | Consequence |
| --- | --- | --- |
| `reviewer_a_safe` (default) | aggregate feature distributions, anonymised spatial-group aliases, fixed-stretch full-scene orientation, and no weak mask, scores, priority, formal query ids, or answer geometry | Preserves the strongest available case for later Reviewer A consideration, subject to the Reference Authority's explicit prior-exposure decision |
| `excluded_scratch` | a Reference-Authority-designated real scratch area permanently excluded from calibration, training, development, and test | Permits deeper learning on that area; nothing learned there is formal evidence |
| `ml_operator` | weak overlap, query identities, model scores, disagreement, selection priority, and operator queue | The operator must not later review those Mae Sai queries as a blinded Reviewer A |

Do not silently move between lanes. In particular, an operator queue and a
reviewer bundle are different products. Model scores, uncertainty, weak overlap,
and priority are operator-only and must never be shown to a formal reviewer.

## 3. Verified inputs available now

Controlled external root:

```text
C:\Users\iputu\Documents\FloodGuard_external_data\label_factory\mae_sai_pilot_v1
```

The learning notebook should resolve that root through one visible parameter,
not hard-code it in reusable source code.

| Input | Grain and observed size | Learning use | Hard boundary |
| --- | --- | --- | --- |
| `features/sar_change_v2_pool_v1/sar_change_v2_cells.csv` | 874,496 cells, 854 queries, 20 tiles/spatial groups, 1,024 cells per query | real SAR data QA, distributions, query aggregation, and later released-label model features | contains no labels; query-model-only |
| `features/sar_change_v2_pool_v1/sar_change_v2_derivation.json` | one self-hashed derivation receipt | verify source, grid, formula, row count, and file identity before analysis | proves declared lineage, not flood truth |
| `query_support/supported_query_pool_v2/supported_query_evidence.csv` | 854 query rows | projected bounds, context fractions, slope, and context-only strata | context is not event-time truth |
| `weak_seed/manual_weak_query_summary_v2/weak_query_summary.csv` | 854 query rows; 4 have weak-positive centres, 850 are wholly unreviewed | positive-unlabelled limitation lesson; operator-only unless the role decision permits it | polygon exterior is never a negative label |
| `weak_seed/manual_weak_query_summary_v2/weak_query_summary_manifest.json` | one self-hashed manifest | verify the repair and weak-source lineage | the recorded `make_valid` repair does not create truth |
| `grids/canonical_supported_pool_v1/canonical_query_regions.csv` | 854 canonical query rows | query geometry, role, and stable spatial grouping | query identity must stay hidden in `reviewer_a_safe` mode |

Verified feature-pool identity recorded in `CURRENT_FEATURE_POOL.md`:

```text
cell CSV SHA-256:
01993f8649798cc9f41a8dd7e9ad1b8f46987692bccb1a1af872fd31490568be

derivation file SHA-256:
b52f14f419444a8c254840cc9cb030e6da2cc70f4ff81bfc030a65ace3d6ffa0

grid-contract SHA-256:
ac6cdfe99431fa5b855831017ec324d06ca529c26c997e894df5c52e4140c634
```

Observed data checks on 2026-07-13:

- all 874,496 feature rows have finite values;
- `valid_data_fraction` is 1.0 for every included cell;
- `vv_change_db = pre_vv_db - event_vv_db` to floating-point tolerance;
- `vh_change_db = pre_vh_db - event_vh_db` to floating-point tolerance;
- median VV change is approximately -0.205 dB and median VH change is
  approximately +0.011 dB;
- the 5th-to-95th percentile ranges are approximately -4.531 to +4.116 dB for
  VV change and -4.685 to +4.777 dB for VH change;
- the context-only Round 0 strata contain 634 steep-terrain, 135 urban, 68
  forest, 5 cropland, 4 WorldCover-water-edge, 2 permanent-water-edge, and 6
  other-context queries.

Those context counts show why raw overall accuracy would be misleading: the
pilot is dominated by steep-terrain queries and contains very small water-edge
and cropland slices.

## 4. What the canonical features mean

The required `sar_change_v2` model order is:

```text
pre_vv_db
event_vv_db
pre_vh_db
event_vh_db
vv_change_db
vh_change_db
valid_data_fraction
```

Positive change means the event-time return became darker because FloodGuard
uses `pre - event`. Negative change means the event-time return became brighter.
Neither direction is a flood label. Open water often darkens, while urban
double-bounce or flooded vegetation can brighten.

Three interpretation cautions belong in the notebook:

1. the change fields are exact arithmetic differences of the four raw
   backscatter fields, so the required columns are linearly dependent;
2. `valid_data_fraction` is constant in the current supported pool, so it
   carries no within-pool discrimination even though it remains an important
   contract field;
3. logistic coefficients over this exact dependency are not unique physical or
   causal effects. Read coefficient direction only as a model diagnostic, and
   use a separately versioned ablation design before changing the production
   feature contract.

The historical weak-label experiment used a different legacy schema with VV/VH
ratios and a combined score. Do not mix those columns or its approximate
georeferencing assumptions into `sar_change_v2`.

## 5. Proposed notebook contract

Proposed artifact:

```text
notebooks/03_mae_sai_real_data_ml_orientation.ipynb
```

Notebook mode: tutorial plus reproducible analysis. It should execute from top
to bottom in `reviewer_a_safe` mode. The model section must fail closed with a
plain-language blocked receipt when a verified release-bound training manifest
does not exist; it must not manufacture a target to keep running.

### Section 0 - `## Goal and current decision`

State the question:

> What does the governed real Mae Sai SAR pool contain, which change patterns
> and context strata require human attention, and is a released-label
> logistic/HGB comparison authorized yet?

Display the selected exposure lane, analysis timestamp, allowed output use, and
the fixed result boundary:

```text
report_only = true
formal_review_authorized = false
eligible_for_decision_layer = false
eligible_for_fpps = false
eligible_for_warning = false
```

### Section 1 - `## Setup`

Keep one parameter cell containing:

- external data root;
- exposure lane, defaulting to `reviewer_a_safe`;
- expected feature, derivation, grid, context, and weak-summary hashes;
- fixed random seed;
- chunk size for the 628 MB cell CSV;
- optional release-bound training CSV and derivation-manifest paths, both null
  by default.

Print package versions and do not install packages inside the notebook.

### Section 2 - `## Verify governed inputs`

Before any chart:

1. hash the exact input files;
2. verify the derivation manifest self-hash and declared feature CSV hash;
3. verify row count, column order, dataset role, schema version, event, grid, and
   source/processing hashes;
4. require 854 unique queries and exactly 1,024 unique cells per query;
5. require 20 spatial groups and exactly one group per query;
6. require finite numeric features and a `valid_data_fraction` in [0, 1];
7. recompute both change formulas and report maximum absolute residual;
8. verify one-to-one query-level joins to context and weak-summary tables;
9. confirm every decision/FPPS/warning flag is false.

Stop on a failed identity, grain, formula, join, or safety check. Do not continue
with a warning banner after a foundational failure.

### Section 3 - `## Understand the data grain`

Show a small dictionary with four kinds of fields:

- identifiers and lineage;
- model features;
- context-only analysis fields;
- labels or model outputs, which should be absent now.

Exercise: identify the observational unit. The answer is one canonical cell,
but the independent validation unit is a spatial group, not a cell. The 874,496
rows are not 874,496 independent examples.

### Section 4 - `## Explore real SAR change without labels`

Load only needed columns, preferably in chunks, and produce bounded aggregate
tables. Show quantiles rather than dumping rows.

Required visuals:

1. side-by-side histograms for VV and VH change with zero marked;
2. a density or hexbin plot of VV change against VH change;
3. pre-versus-event density plots for each polarization with the equality line;
4. query-level median and interquartile change distributions, using anonymised
   query aliases in `reviewer_a_safe` mode;
5. small-multiple box plots of VV/VH change by context stratum.

Every title must say `SAR change`, `backscatter`, or `context`; do not call a
darkening tail a flood distribution.

Exercises:

- explain what positive and negative change mean in the project convention;
- name two flood-compatible and two non-flood explanations for each tail;
- find a query with strong VV darkening but weak VH change and write two
  competing physical explanations without assigning a class.

### Section 5 - `## Check context coverage and imbalance`

Create a query-level table with:

- query count by `round0_stratum`;
- permanent-water, urban, forest, cropland, and steep-terrain fractions;
- slope p90;
- number of distinct tiles/spatial groups represented in each stratum.

Required visuals:

1. ordered bar chart of query counts by stratum with exact counts;
2. heatmap of stratum by anonymised spatial group;
3. box plots of slope p90 and context fractions by stratum.

Flag any error slice with fewer than 20 queries or fewer than 2 spatial groups
as descriptive only. Do not hide the two-query permanent-water-edge slice in an
overall average.

### Section 6 - `## Learn why the weak mask is not a target`

This section is operator-only. In `reviewer_a_safe` mode, show only the governed
aggregate fact that the weak source is positive-unlabelled; do not load query ids
or overlap values.

In an authorized operator or excluded-scratch lane, show:

- 4 queries with some weak-positive cell centres;
- 1,435 weak-positive centres;
- 850 wholly unreviewed queries;
- the recorded invalid-geometry repair;
- a diagram of `known weak positive` versus `unknown`, with no `known dry`
  category.

Learning exercise: write the confusion matrix denominator that would be needed
for precision and recall. Then explain why false positives and true negatives
cannot be identified from the weak polygon exterior.

Do not train logistic regression or HGB from these four positive queries. Do not
calculate flood IoU, Dice, precision, recall, ROC-AUC, or PR-AUC against the weak
summary as if it were truth.

### Section 7 - `## Build the spatial split before the model`

Use `spatial_group_id`, which currently maps the 20 parent tiles to 20 groups.
Create repeated deterministic grouped folds using the repository's
`make_repeated_spatial_group_folds` only after released labels exist. Before
then, demonstrate fold assignment without fitting.

Required leakage checks:

- no spatial group appears in both train and validation within a fold;
- no query appears in both train and validation;
- every training complement contains released positive and negative classes;
- reviewed training queries are absent from the unreviewed scoring pool;
- preprocessing statistics are learned from each training fold only;
- no weak, label, model-score, entropy, priority, or post-selection column is a
  feature;
- the untouched future event is not opened or summarized;
- results are described as within-event development because all current groups
  come from the same Mae Sai event.

Learning exercise after release: compare a random-cell split with the governed
grouped split. The random-cell result is an intentional leakage demonstration,
not evidence. Explain why neighbouring cells from the same 32 x 32 core make
the random result optimistic.

### Section 8 - `## Training gate`

The gate must require all of the following exact evidence:

- a frozen labelset and passing revalidation receipt;
- a release-bound training CSV;
- a valid training-derivation manifest binding that CSV, the frozen labelset,
  and the `sar_change_v2` feature pool;
- at least two explicit binary classes after mapping;
- enough spatial groups for the declared number of folds;
- no overlap between reviewed training queries and the unreviewed pool.

The label mapping is:

| Released class | Binary target treatment |
| --- | --- |
| `dry_land` (0) | 0 |
| `temporary_flood` (1) | 1 |
| `permanent_or_preexisting_water` (2) | 0, retained as a separate error slice |
| `uncertain_water_change` (3) | excluded |
| `unobservable_or_artifact` (4) | excluded |
| `unreviewed` (255) | excluded |

Current expected notebook result: `blocked_missing_released_training_labels`.
That is a successful, honest execution state.

### Section 9 - `## Logistic baseline and shallow HGB challenger`

Unlock only after Section 8 passes. Call the governed committee implementation
rather than reimplementing production fitting in the notebook:

```text
src/floodguard/label_factory/committee.py
scripts/train_query_committee.py
```

Use repeated spatial-group cross-validation, initially 5 folds x 3 repeats when
class/group coverage supports it. Reduce folds only through a recorded design
decision; never fall back silently to random cells. HGB must keep
`early_stopping=False` because its random internal validation split would violate
the spatial design.

Model roles:

- logistic regression is the transparent linear baseline;
- shallow histogram gradient boosting is the modest nonlinear challenger;
- neither model is flood truth;
- their output is a continuous query-ranking score, not a calibrated operational
  flood probability and not a selected flood cutoff.

### Section 10 - `## Evaluate out-of-fold score behaviour`

Use only out-of-fold scores for model comparisons. Aggregate each metric by
repeat and show mean, standard deviation, and the number of groups, queries,
cells, positives, and negatives.

Primary score diagnostics:

- average precision / PR-AUC, because temporary flood may be rare;
- ROC-AUC as a secondary ranking diagnostic;
- log loss and Brier score as score-quality diagnostics, with an explicit note
  that they do not establish calibration;
- score distributions by released class;
- result stability across repeats and spatial groups.

Thresholded teaching diagnostics may show precision, recall, Dice/ F1, IoU,
false-positive count, false-negative count, and area-bias ratio at one
predeclared learning-only threshold. The threshold must not be optimized on the
same validation fold, persisted as a production cutoff, or presented as a
decision-layer gate.

Do not use raw accuracy as the headline metric.

Required visuals:

1. OOF precision-recall curves for logistic and HGB;
2. OOF ROC curves as secondary context;
3. score histograms by released class;
4. fold/repeat metric dot plots rather than one aggregate number;
5. logistic standardized coefficients with the exact-dependency caveat;
6. group-respecting HGB permutation importance, not training impurity
   importance.

### Section 11 - `## Inspect uncertainty and committee disagreement`

Use the repository definitions:

- committee mean score;
- normalized binary entropy of that mean;
- absolute logistic/HGB disagreement;
- Jensen-Shannon disagreement;
- distance from the neutral 0.5 score.

Aggregate cell evidence to queries using the existing candidate builder's
declared top-tail rule rather than averaging away small difficult regions.

Required visuals:

1. logistic score versus HGB score with the equality line;
2. entropy versus absolute disagreement, coloured by context stratum;
3. the top-tail uncertainty distribution by stratum;
4. a small operator-only table of highest-priority queries with location fields
   suppressed in `reviewer_a_safe` mode.

Interpretation exercise:

- high entropy, low disagreement means both models are near the neutral score;
- low entropy, high disagreement means their average may look decisive while
  the models disagree strongly;
- low entropy and low disagreement means agreement, not correctness;
- high disagreement can expose a nonlinear interaction that the logistic model
  cannot represent, or HGB instability from sparse labels.

### Section 12 - `## Error slices and failure analysis`

After released labels exist, report metrics separately for:

- permanent/pre-existing water;
- steep terrain;
- urban/built-up context;
- forest/flooded vegetation context;
- cropland/wet-soil context;
- weak-boundary context for operator analysis only;
- reviewed uncertain and unobservable cells as excluded-count diagnostics.

For every slice show the denominator, distinct spatial groups, released class
counts, precision, recall, Dice, IoU, score distribution, and reviewer agreement
where available. Mark small slices as insufficient rather than ranking them.

The notebook should contain a bounded error gallery with pre/event VV/VH,
change, permanent water, slope, and land cover. It must use released evidence
only, preserve uncertainty, and stay outside formal reviewer delivery.

### Section 13 - `## Active versus random at equal human cost`

Do not claim annotation efficiency from model metrics. Efficiency requires real
review time and matched lanes.

For each evaluated round report:

- active and stratified-random review minutes;
- relative cost difference;
- label yield and critical-stratum coverage;
- active and random IoU/Dice on the fixed evaluation design;
- gain active minus random;
- reviewer Dice and unresolved-conflict rate;
- the existing stop-rule result.

Use `src/floodguard/label_factory/evaluation.py`. At least three comparable
rounds are required before concluding that active selection wins or fails to
win.

### Section 14 - `## Takeaways and blocked receipt`

End with four separate lists:

1. verified observations from real measurements;
2. interpretations that still need human evidence;
3. blockers before model fitting or evaluation;
4. the exact next executable action.

The orientation run should normally conclude:

> The canonical real-data pool is structurally analyzable and reveals
> heterogeneous SAR-change and context strata. It contains no released flood
> labels, so no genuine logistic/HGB comparison or flood-accuracy claim was
> produced. The next model-unlocking artifact is a verified release-bound
> training table, not a pseudo-label.

## 6. Beginner exercises and expected answers

| Exercise | Expected learning |
| --- | --- |
| Recompute `pre - event` for five cells | Feature formulas are testable contracts, not magic model inputs |
| Compare VV and VH change signs | Different polarizations can react differently; sign is not a class |
| Explain why 874,496 rows are not independent | Nearby cells share scene, terrain, weather, processing, and query context |
| Treat the weak exterior as dry, then identify the assumption | The apparent negative class was invented, so normal classification metrics become circular |
| Map 20 groups into folds and test overlap | The split must be designed before fitting |
| Contrast random-cell and spatial-group results after release | Spatial leakage usually makes random-cell results optimistic |
| Compare logistic and HGB on OOF rows | Model complexity is useful only when gains persist across spatial groups |
| Find high-agreement errors | Committee agreement does not guarantee correctness |
| Find high-disagreement cases | Those cases may be valuable for human review, not automatically flood |
| Compare active and random lanes at equal minutes | Selection efficiency is a human-cost result, not just a model-score result |

## 7. Minimal implementation plan

Keep the first implementation reviewable:

1. add one notebook generator and one executed notebook;
2. reuse existing validators and committee functions; do not duplicate model
   fitting in `src/floodguard/`;
3. add a small read-only orientation helper only if chunked validation and
   aggregation would otherwise be duplicated in multiple artifacts;
4. write orientation outputs to a new, non-overwriting external `learning/`
   directory, never into the governed feature, label, committee, or review
   directories;
5. emit only aggregate CSV/JSON/PNG outputs in `reviewer_a_safe` mode;
6. add tests for hash mismatch, wrong row grain, incomplete joins, spatial-group
   overlap, accidental weak-target construction, and false safety flags;
7. execute the notebook top to bottom and verify all displayed counts against
   the governed inputs.

No change to the dashboard, FPPS, flood aggregation, active-learning selection,
or model contracts is needed for this learning milestone.

## 8. Promotion boundary

Even after the first real committee is trained, its direct output remains
report-only query-selection evidence:

```text
allowed: prioritize model-blinded human review
not allowed: create flood truth
not allowed: replace dashboard flood likelihood
not allowed: feed exposure, access, equity, FPPS, or action class
not allowed: issue an alert or warning
```

A later flood-detection promotion programme would need separately frozen
within-event validation, multiple Thailand development events, an untouched
geographic test, calibration analysis, robustness evidence, and explicit
decision-layer approval. Query-selection success does not supply that evidence.
