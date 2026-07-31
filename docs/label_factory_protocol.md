# Flood-label factory protocol

Status: implemented engineering protocol for research, reviewer calibration, and query selection. No completed human-review corpus or training-eligible label release is claimed.

This protocol defines how FloodGuard turns weak flood evidence into explicitly reviewed, versioned labels and uses query-only machine learning to decide what humans should inspect next. It does not authorize any weak seed, review queue, annotation raster, label-factory model, or acquisition score to feed the Flood Preparedness Priority Score (FPPS), an A-E action class, the dashboard flood layer, an official warning, or an operational flood estimate.

## 1. Purpose and product separation

The label factory has four research objectives:

1. Determine whether flood-like pixels outside the conservative Mae Sai polygon are model errors, omissions from the weak polygon, alignment problems, temporal ambiguity, or SAR artefacts.
2. Identify repeatable failure modes such as urban double-bounce, shadow/layover, steep terrain, permanent-water boundaries, wet soil, flooded vegetation, and pre/event misregistration.
3. Measure whether active selection finds useful human corrections faster than stratified-random review at the same reviewer cost.
4. Establish whether reviewers agree well enough to support a later flood-model experiment.

Three products must remain separate:

| Product | What it does | What it does not do |
| --- | --- | --- |
| Review queue | Ranks or samples query cores for a human to inspect | It does not create flood truth |
| Frozen labelset | Preserves reviewed/adjudicated cell evidence and lineage | It does not become an operational flood model |
| Future flood model | Separate Phase 4 candidate trained from cleared releases | It is not part of the current label-factory authorization |

The first two products are implemented as engineering scaffolding. The third requires a separate model-promotion programme.

## 2. Temporal target and source prerequisites

The target is the reviewer's best-supported interpretation of temporary inundation at the exact event-time Sentinel-1 acquisition, relative to the declared pre-event acquisition.

It is not:

- flooding at any time during the wider disaster;
- historical susceptibility;
- an emergency activation area;
- water visible only in an unmatched-date image; or
- field-validated or official flood truth unless an independent source explicitly establishes that status.

Every formal query inherits its event id, pre/event product identities, UTC acquisition times, projected grid id and grid-contract SHA-256, feature-schema version, CRS, resolution, source timestamps, confidence class, and assumptions. Pre-event time must precede event time. Processing and ML-label-derivation rights, source checksums, and pre/event alignment must pass before formal annotation. Failed or unknown alignment is blocked or labeled `unobservable_or_artifact`; it is never converted to dry land.

The registry's initial hard tolerance is residual georegistration error at or below `0.5` pixel. The declared pre/event SAR pair must agree on pass direction, relative orbit, and polarization set. Passing these metadata checks is necessary but not sufficient. The implemented `floodguard.processing_alignment_receipt.v1` gate must re-hash the processed raster and its coverage, valid-data, and registration evidence, then verify the common affine/dimensions/grid before the first formal bundle. The repository has synthetic contract fixtures only; no real Mae Sai processing receipt exists yet.

## 3. Canonical label taxonomy

| Code | Stored class | Meaning | Temporary-flood binary target |
| ---: | --- | --- | ---: |
| 0 | `dry_land` | Reviewed, observable land with no persuasive event-time inundation | 0 |
| 1 | `temporary_flood` | Event-time inundation absent or materially lower in the pre-event evidence | 1 |
| 2 | `permanent_or_preexisting_water` | Water already present before the event or supported as normal water | 0, retained as its own error slice |
| 3 | `uncertain_water_change` | Observable change exists, but temporary flooding cannot be resolved | Excluded |
| 4 | `unobservable_or_artifact` | No-data, shadow/layover, failed alignment, or otherwise uninterpretable evidence | Excluded |
| 255 | `unreviewed` | No human decision has been made | Excluded |

Codes 3, 4, and 255 are different states. None may be silently mapped to 0. Binary training is fail-closed: only codes 0, 1, and 2 are eligible after the underlying human/adjudication lineage and label release pass all gates.

## 4. Existing Mae Sai polygon: positive-unlabeled seed

The existing manually digitized polygon remains useful, but it is not a complete binary mask:

```text
polygon interior -> weak_positive
polygon exterior -> unreviewed
optional boundary buffer -> weak_uncertain
```

The weak seed may enrich Round 0, identify boundary-review regions, and support diagnostics against later human labels. It must be hidden during blinded review. The legacy experiment that encoded every exterior cell as 0 remains reproducible under its legacy feature schema, but that raster is not training truth for the label factory.

## 5. Canonical grid and review unit

- Use an event-owned projected metre CRS, normally the local UTM zone.
- Declare the output resolution; the initial contract uses 10 m.
- Use 256 x 256 cells for a storage/display tile.
- Pilot non-overlapping 32 x 32 or 64 x 64 query cores.
- Show the surrounding tile as context, but accept labels only from the query core.
- Context may overlap; query cores may not overlap.
- Assign calibration, training/query, development, and geographic-test roles before selection.
- Derive tile/query identifiers from event, grid contract, origin, and indices, never export order.

The grid id includes a short digest derived from CRS, resolution, tile size, and grid origin. The complete `grid_contract_sha256` and exact `processing_alignment_receipt_sha256` travel with tile, query, review, and candidate artifacts. The processing receipt binds source and processed-file bytes, software/version, RTC method, full six-term affine, dimensions, pixel size, nodata and resampling conventions, coverage/valid-data evidence, registration method/error, timestamp, confidence, assumptions, and fixed decision-ineligible safety fields. A 10 m output grid does not imply statistically independent 10 m physical observations.

## 6. Feature contract

`sar_change_v2` is the only canonical label-factory feature schema. Its required model inputs, in schema order, are:

```text
pre_vv_db
event_vv_db
pre_vh_db
event_vh_db
vv_change_db
vh_change_db
valid_data_fraction
```

Optional versioned inputs include local VV/VH change quantiles and standard deviations, elevation, slope, permanent-water and land-cover fractions, building fraction, distance to river, incidence angle, and pre/event alignment error.

The legacy ratios and weighted combined score are not part of the `sar_change_v2` model feature order. A deterministic combined-change score may be retained as a reviewer or error-analysis diagnostic only; it must not be silently appended to training features. The two historical combined-score formulas remain isolated in explicitly named legacy schemas.

## 7. Reviewer-visible evidence and blinding

An approved first-pass bundle may include:

1. pre-event and event-time VV;
2. pre-event and event-time VH;
3. VV and VH change layers;
4. a fixed-stretch change composite;
5. permanent-water context;
6. DEM hillshade and slope;
7. land-cover context;
8. rivers, roads, and settlement context; and
9. lawful, timestamp-compatible optical context.

The bundle must identify source timestamps, scale, CRS, the annotatable query core, and the surrounding non-annotatable context. Approved context is checksum-tracked and referenced with redacted path hints; source rasters remain in the controlled external workspace. Formal bundle construction requires the exact processing receipt, checks that every query is covered, and requires each raw VV/VH context checksum to match the receipt's processed-file checksum. The verified receipt is copied into and checksum-bound by the write-once bundle.

VV/VH change and composite displays have an additional mandatory gate. A
`floodguard.review_derivative_lineage_receipt.v1` must re-hash the exact
pre/event processed rasters and all three output files, bind the processing
receipt, source/event registries, governance package, grid hash, acquisition
times, transformation expressions, nodata rule, output type, fixed stretches,
colour-map identifier and exact stops, gamma, renderer, resampling, and RGB channel
expressions. The canonical change convention is `pre_db - event_db`, matching
`sar_change_v2`; positive values therefore indicate a backscatter drop. The
receipt refuses automatic, percentile, histogram-derived, or other
scene-dependent stretches. Its source and output paths are used only while
re-hashing and are not persisted; path hints remain relative and redacted.

The receipt must exactly provide one `vv_change`, one `vh_change`, and one
`fixed_stretch_change_composite` layer. Each corresponding `context_layers.csv`
row must match the receipt's derivative id, set id, source-binding hash, output
hash, event-time acquisition, CRS, display name, path hint, confidence, and
assumptions. Formal bundle construction and later formal annotation import both
revalidate the copied receipt. A hash-consistent declaration proves byte and
parameter lineage, not that a derivative was scientifically interpreted
correctly; the reviewer and reference authority must still assess artifacts.
All derivative records are `formal_review_display_only=true`,
`query_model_only=true`, and ineligible for the decision layer, FPPS, and
warnings.

Candidate generation and lineage validation do not replace human evidence
approval. Every generated candidate starts as
`authority_approval_status=authority_approval_pending`. The receipt field
`production_review_eligible=true` refers only to validated source governance
and technical lineage; it is not Reference-Authority approval. Pending
candidates must not enter `context_layers.csv` or a reviewer bundle. The named
Reference Authority must issue a separate attributable, timestamped decision
on the exact candidate version first. Any requested display change creates a
new immutable version and may require new unseen calibration.

Before canonical calibration-reserve or reference construction, freeze a
`floodguard.reference_authority_design_approval.v1` package. It revalidates and
copies the pre-calibration human-role package, one reserve-design receipt and
candidate id, the fixed reference-procedure hash/version, attributable decision
evidence, and an explicit approve/reject/not-submitted derivative decision. An
approved package permits only the next separate reserve/reference construction
step. It selects no query ids, creates no labels or bundle, and keeps
calibration execution, formal review, training, decision, FPPS, and warning
authorization false. See `docs/reference_authority_design_approval.md`.

During primary and secondary independent review, the reviewer must not see:

- the weak polygon or weak-label overlap;
- logistic or boosted scores;
- entropy, disagreement, impurity, diversity, rank, or selection reason; or
- the other reviewer's annotation.

The generated bundle uses a reviewer-visible allow-list and rejects model/weak-label context roles. Formal imported records require both `model_predictions_visible=false` and `other_reviewer_annotations_visible=false`.

## 8. Review completeness, confidence, and ambiguity

An empty geometry never means the remainder is dry. Every completed submission declares whether the entire query core or an explicit `reviewed_extent` was inspected. Cells outside that extent remain code 255. Inside a reviewed extent, the reviewer must draw every class or deliberately enable primary-class fill; otherwise rasterization fails rather than inventing a negative.

Allowed confidence values are `high`, `medium`, and `low`. Confidence is an audit attribute, not a flood probability or automatic training weight. A low-confidence dry/flood decision should normally become `uncertain_water_change` unless the notes explain why a provisional class is retained.

Allowed ambiguity tags are:

```text
urban_double_bounce
urban_layover
radar_shadow
steep_terrain
wet_soil_or_agricultural_change
flooded_vegetation
permanent_water_boundary
speckle_or_isolated_response
pre_post_misregistration
temporal_mismatch
optical_cloud_or_shadow
cross_border_context
other
```

These tags support adjudication, sampling quotas, reviewer training, and stratified error analysis.

## 9. Calibration, double review, and adjudication

Before formal production review:

- select approximately 8-12 representative practice regions;
- include clear flood, clear dry, permanent water, urban, steep-terrain, and ambiguous boundary examples;
- have all reviewers annotate independently;
- reconcile differences and revise this protocol if needed; and
- keep practice labels outside formal evaluation.

For the formal unseen calibration gate, the Reference Authority's locked
multipart geometry is rasterized independently onto the complete canonical
grid before the reference is frozen. The raster lineage binds an attributable
authority-role evidence checksum but does not allow software to certify that
person's qualifications. A threshold failure produces only a confidential,
self-hashed non-pass diagnostic with `formal_review_authorized=false`; it never
produces or substitutes for a passing receipt. Remediation uses different,
permanently excluded practice material and a fresh unseen calibration set.

For the initial Mae Sai pilot, double-review every formal query. After agreement stabilizes, continue double review for every development/test query, every low-confidence or uncertain query, every critical failure stratum, every large human/model conflict, and a uniform random 20-25% of the remaining training pool.

The adjudicator initially sees both locked human records without model outputs. Allowed outcomes are `accept_a`, `accept_b`, `redraw`, `uncertain`, `unobservable`, and `reject`. Adjudication creates a new immutable, hash-linked record. It never overwrites either source review.

## 10. Rasterization and agreement

Each reviewer's locked geometry is rasterized independently by cell-centre containment on the canonical query grid. Different class geometries may not cover the same cell. Individual reviewer rasters are agreement evidence only and remain ineligible for query-model training until adjudication and freeze.

Agreement must report, at minimum:

- multiclass confusion;
- per-class IoU and Dice/F1;
- temporary-flood agreement;
- boundary F1 at a declared tolerance, initially 20 m;
- area and uncertain/unobservable differences;
- Cohen's kappa;
- per-query results; and
- temporary-flood Dice for declared critical strata.

Raw pixel accuracy is not a headline metric because dry-majority regions can hide flood-boundary disagreement.

The current release gates are provisional engineering gates:

| Gate | Required at freeze |
| --- | ---: |
| Temporary-flood Dice | at least 0.80 |
| Temporary-flood IoU | at least 0.67 |
| Mean boundary F1 | at least 0.75 |
| Boundary metric coverage | every formal query |
| Cohen's kappa | at least 0.80 |
| Temporary-flood Dice in every declared critical stratum | at least 0.70 |
| Open adjudications | 0 |
| Required critical QA failures | 0 |

If temporary-flood Dice is below approximately 0.75 or disagreement is dominated by one failure mode, stop production review and repair the protocol, source alignment, evidence package, taxonomy, or reviewer calibration before collecting more labels.

## 11. Acquisition policy

### Round 0

Round 0 is model-independent. It uses a declared `round0_stratum`, stable seeded ordering, round-robin stratum balancing, non-overlap, and optional minimum spatial separation. It records stratum population, selected quota, and inclusion probability. It must not use logistic or boosted scores.

For the small Mae Sai pilot, reviewing the entire feasible formal pool may be more scientifically useful than treating Round 0 as an efficiency claim.

### Later rounds

For a default batch of 40 query regions, the sampler requests:

- 24 active regions (60%) from uncertainty/disagreement ranking after diversity and spatial controls;
- 8 hard-stratum regions (20%); and
- 8 stratified-random control regions (20%).

The random lane is mandatory. Random-control sampling is stratified by event and major land-cover stratum and records the inclusion probability where defined. The selector also supports event/land-cover caps, minimum centre distance, overlap-group rejection, and near-duplicate filtering. If constraints prevent the requested composition, the manifest records requested and achieved quotas; it does not silently claim success.

Region acquisition evidence uses the mean of the most informative top 20% of supported cells for uncertainty and disagreement, plus a separately supplied boundary-impurity diagnostic and explicit diversity summaries. Logistic-versus-boosted disagreement is query-by-committee disagreement, not BALD.

## 12. Query committee

The committee contains:

- a transparent standardized logistic baseline persisted as JSON with coefficients, intercept, means, scales, feature order, and safety metadata; and
- a shallow `HistGradientBoostingClassifier` challenger with random early stopping disabled.

Training requires a verified frozen labelset JSON and its content hash, `sar_change_v2`, reviewed/adjudicated binary targets only, and explicit spatial groups. The default evaluation uses repeated grouped spatial cross-validation. Grouped out-of-fold scores and unreviewed-pool scores are written for audit. The boosted estimator itself is not serialized; only a non-executable manifest is persisted, so a future scorer must reproduce the declared training run rather than unpickling arbitrary code.

All committee artifacts are permanently constrained to:

```text
model_purpose = query_ranking
eligible_for_review_queue = true
eligible_for_training_after_human_review = conditional
query_model_only = true
eligible_for_decision_layer = false
eligible_for_fpps = false
eligible_for_warning = false
```

No performance metric may relax these fields.

## 13. Immutable release

A frozen labelset is an authoritative, content-addressed JSON manifest, for example `mae_sai_2024_labels_v0.1.0.json`. It records parent lineage, content/metadata/semantics hashes, latest locked A/B annotation ids, named raster hashes, creation time, and its own canonical manifest SHA-256.

Freeze additionally requires:

- complete A/B pairs and an adjudication queue that accounts for required conflicts;
- zero unresolved queue items;
- the code-generated structured QA report and self-hashed receipt reproduced
  from the exact release-scoped raw evidence files;
- agreement JSON that passes the thresholds above;
- a `floodguard.reviewed_label_cells.v1` raster-lineage JSON;
- one or more canonical reviewed-cell CSVs with exact checksums and class counts; and
- label-content JSON that exactly reproduces the ordered labels derived from those canonical cells.

Each final cell references exactly one source annotation or one source adjudication and the full grid-contract SHA-256. The current validator supports `canonical_cell_csv_v1`; it does not claim GeoTIFF release validation.

Release version meaning:

- major: temporal target, taxonomy, grid, or core semantics changed;
- minor: reviewed/adjudicated coverage or label geometry changed; and
- patch: metadata/QA correction that leaves label pixels and semantics unchanged.

Frozen manifests and named artifacts are write-once. Changed evidence requires a new version and parent link.

## 14. Evaluation and stopping

Active selection must be compared with stratified random review at equal reviewer time or interaction cost. Track fixed-development IoU/Dice, area bias, boundary F1, calibration, critical-stratum results, correction yield, reviewer time, and adjudication burden. Do not infer efficiency from a larger actively selected training set alone.

Pause active acquisition when:

- active selection fails to beat random at equal cost for three evaluated rounds;
- reviewer agreement fails its gates;
- severe area bias persists;
- important strata remain uncovered;
- test isolation or another critical QA rule fails; or
- an adjudication backlog remains open.

Once Mae Sai improvement plateaus, move to another event. More regions from one acquisition do not create geographic generalization. A complete untouched Thailand geographic test must remain sealed until the method is frozen.

## 15. Current evidence boundary

The repository implements the contracts, validators, immutable writers, review-bundle builder, rasterization/agreement logic, query committee, acquisition policy, evaluation scaffold, and readiness reporting. It does not establish that real reviewers have completed the pilot, that an adjudicated release exists, that a committee has been trained on cleared real labels, that active learning beats random review, or that any label-factory output can enter FPPS. See `docs/label_factory_implementation_status.md` for the exact implemented-versus-blocked inventory.
