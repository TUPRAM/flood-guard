# Flood-label factory data contract

Status: implemented Phase 0-3 engineering contract. Raw imagery, reviewer drawings, full reviewed-cell artifacts, and any real trained-model workspace remain outside Git. No human label release currently exists in the repository.

## 1. Artifact map and grain

| Artifact | Format and grain | Role |
| --- | --- | --- |
| Event registry | `events.csv`, one event | Temporal target, projected grid, dataset role, rights, allowed uses |
| Source registry | `source_assets.csv`, one source asset | Product identity, UTC acquisition, orbit/polarization, checksum, rights, preprocessing/alignment evidence |
| Processing/alignment receipt | self-hashed JSON, one receipt with one row per non-static source | Byte-backed terrain-correction, coverage, valid-data, registration, and common-grid evidence |
| Tile assignments | CSV, one requested tile index | Explicit role, overlap group, feature schema, source quality |
| Canonical tiles | `tiles.csv`, one 256 x 256 storage/display core | Stable projected-grid tile contract |
| Canonical queries | `query_regions.csv`, one selectable non-overlapping query core | Review state and fail-closed selection eligibility |
| Weak seed | cell CSV plus JSON manifest, one query seed | Positive-unlabeled interpretation of the legacy polygon |
| Weak-query summary | CSV plus self-hashed JSON, one canonical query | Batch-reprojected positive-unlabeled overlap for internal operator context |
| Internal acquisition | CSV, one round/query candidate | Model or Round 0 evidence; never reviewer-visible |
| Operator queue package | write-once CSV plus self-hashed JSON, one selected query | Consolidated internal score/location/context/weak/preview audit; never reviewer-visible |
| Blinded bundle | directory of CSV/Markdown files | Reviewer-visible region/context allow-list and blank annotation form |
| Completed review batch | CSV, one locked reviewer/query revision | Import interchange only; not the canonical audit log |
| Annotation log | hash-chained JSONL, one immutable review record | Canonical append-only human evidence |
| Geometry parts | CSV, one annotation/class geometry part | Deterministic cell rasterization controls |
| Reviewer cell raster | CSV plus JSON manifest, one annotation/cell | Agreement-only rasterized review evidence |
| Agreement evidence | JSON plus per-query CSV | A/B cell metrics, boundaries, and critical-stratum slices |
| Adjudication queue | immutable CSV, one review conflict | Required reason and source annotation hashes |
| Adjudication log | hash-chained JSONL, one resolution | Immutable human resolution; never overwrites reviews |
| Canonical final cells | `canonical_cell_csv_v1`, one released query/cell | Reviewed/adjudicated cell truth used at labelset freeze |
| Raster lineage | JSON object | Binds final cells to grid, reviewers, adjudications, checksums, and class counts |
| Labelset manifest | content-addressed JSON, one release | Authoritative immutable release and parent lineage |
| Committee run | new directory of JSON/CSV artifacts, one training run | Query-only logistic/boosted audit evidence |
| Region candidates | CSV, one query | Cell-score aggregation for selection |
| Active-learning evaluation | comparison CSV plus Markdown | Equal-cost active-versus-random evidence and stop decision |
| QA findings and receipt | Deterministic CSV plus self-hashed JSON, one entity/check and one release | Raw-file-bound provenance, split, annotation, query-safety, and label eligibility evidence |

The authoritative labelset manifest is JSON, not CSV. `freeze_label_factory_labelset.py` writes this JSON exactly once and `validate_label_factory_labelset.py` revalidates every bound artifact, then writes a separate self-hashed `floodguard.labelset_validation_receipt.v1` JSON. Readiness and committee training accept only that verified receipt; compact self-reported CSV release claims are rejected. The legacy readiness option name `--labelset-manifest` remains only as an alias for the validation-receipt path.

## 2. Dataset roles and isolation

Every event/tile/query is assigned exactly one role before acquisition:

```text
reviewer_calibration
training_and_query_pool
fixed_within_event_development
untouched_geographic_test
```

Only `training_and_query_pool` may enter active selection or query-model training after human review. Development may support fixed within-event evaluation and method selection under a declared protocol. Untouched geographic test data must not influence selection, calibration, thresholds, protocol revision, hyperparameters, or model choice. Overlap groups cannot span roles.

## 3. Stable identifiers and grid identity

Illustrative identifiers:

```text
event_id: TH-MAESAI-2024-09
grid_id: UTM47N_10M_G<10-character-contract-digest>
tile_id: TH-MAESAI-2024-09_UTM47N_10M_G<digest>_X00123_Y00087
query_region_id: TH-MAESAI-2024-09_UTM47N_10M_G<digest>_X00123_Y00087_R02_C01_S64
annotation_id: ANN_TH-MAESAI-2024-09_000123_RV-A_V1
```

Identifiers derive from event id, projected-grid contract, tile indices, query row/column, and query size. They do not depend on export order or active-learning round.

The complete `grid_contract_sha256` is the canonical identity of CRS, resolution, tile width/height, query size, and grid origin. The short digest in `grid_id` is for readable ids; artifact validation uses the full SHA-256.

## 4. Event registry

Required event fields:

```text
event_id
event_name
country
study_area
event_start_utc
event_end_utc
pre_acquisition_utc
post_acquisition_utc
analysis_crs
analysis_resolution_m
grid_origin_x
grid_origin_y
tile_size_pixels
query_size_pixels
dataset_role
label_status
source_rights_status
processing_allowed
ml_label_derivation_allowed
validation_allowed
source_timestamp
confidence_class
assumptions
```

The pre acquisition must precede the event/post acquisition. CRS must be a supported projected metre CRS. Resolution and grid dimensions must be positive, and the tile size must be divisible by the query size. Rights for processing, label derivation, and validation are explicit booleans rather than inferred from one generic license status.

## 5. Source-asset registry

Required source fields:

```text
asset_id
event_id
sensor
platform
product_id
acquisition_time_utc
event_relative_role
orbit_direction
relative_orbit
polarizations
processing_level
crs
pixel_spacing_m
local_path_hint
sha256
sha256_status
license_status
processing_allowed
ml_label_derivation_allowed
redistribution_status
georegistration_method
georegistration_error_pixels
source_timestamp
confidence_class
assumptions
```

`event_relative_role` distinguishes pre-event and event-time evidence. `local_path_hint` must be redacted and must not be an absolute local path. The complete source asset stays in the controlled external data workspace. Processing, label derivation, validation, and redistribution remain separate decisions.

Canonical builds require every registered analysis asset to match the event CRS and pixel spacing and to report residual georegistration error no greater than `0.5` pixel. The declared pre/event SAR pair must also have compatible orbit direction, relative orbit, and polarization set; harmless polarization order/case and zero-padded orbit formatting are normalized, while a real acquisition mismatch blocks the build. This metadata gate does not itself prove terrain correction or common affine alignment. The implemented processing-receipt gate below is therefore mandatory. The current Mae Sai receipt and its real files live in the controlled external workspace rather than Git.

## 5.1. Processing and common-grid receipt

`build_label_factory_processing_receipt.py` consumes a semantically validated
`governance_cleared_vN` package, its exact event/source registries, and a v1
processing-evidence CSV. The two supplied registry files must be byte-identical
to the copies sealed by the governance package. The CSV has one and only one
row for every non-static source asset and records:

```text
asset_id, processed_artifact_id, processed_file_path, processed_file_sha256
processing_software, processing_software_version, rtc_terrain_correction_method
output_crs, affine_a, affine_b, affine_c, affine_d, affine_e, affine_f
width_pixels, height_pixels, pixel_size_x_m, pixel_size_y_m, nodata_convention
resampling_method, coverage_fraction, valid_data_fraction
coverage_evidence_path, coverage_evidence_sha256
valid_data_evidence_path, valid_data_evidence_sha256
registration_method, registration_error_pixels
registration_evidence_path, registration_evidence_sha256
grid_contract_sha256, source_timestamp, confidence_class, assumptions
query_model_only, eligible_for_decision_layer, eligible_for_fpps,
eligible_for_warning
```

The builder opens and hashes the processed, coverage, valid-data, and
registration evidence files. It derives product id, acquisition UTC, event
role, source checksum/status, license, processing/derivation rights, and
redistribution status from the source registry rather than trusting duplicated
CSV values. It requires exact source coverage, rights-cleared processing,
full declared coverage, nonzero valid support, registration error at or below
0.5 pixel, a projected-metre CRS, and one common north-up affine/dimension/
pixel-size/nodata/grid contract per event. Version 1 deliberately rejects
per-asset tiling exceptions; a future schema would need an explicit justified
tiling contract.

Production receipt, grid-build, grid-validation, raw-grid-readiness,
review-bundle, and formal annotation-import CLIs all require the same governance
package. The validated chain is:

```text
sealed rights package -> exact events/source registries -> processing receipt
-> canonical grid manifests -> governance-bearing grid receipt
-> governance-bearing blinded bundle -> formal annotation import
```

The receipt schema remains `floodguard.processing_alignment_receipt.v1`; the
governance binding is revalidated transitively at every production command.
Synthetic low-level tests can omit governance only by setting the explicit
`allow_ungoverned_fixture=True` API flag, which cannot bypass registries marked
`approved_with_provider_conditions` and is not exposed by production CLIs.
Grid receipts use `floodguard.grid_validation_receipt.v3` and permanently record
whether the binding is `validated` or `synthetic_fixture_only`; only the former
can set `production_readiness_eligible=true`. Allowlisted grids also record the
exact `supported_query_derivation_sha256`, and receipt generation requires the
same derivation to reproduce the canonical manifests.

The output schema is `floodguard.processing_alignment_receipt.v1`. It stores
path-free evidence file names and SHA-256 values, exact source/grid bindings,
timestamp, confidence, assumptions, fixed query-only safety fields, and a
canonical self-hash. The immutable writer refuses overwrite. A self-hash is an
integrity check, not a digital signature or proof of flood truth.

## 6. Tile assignment and canonical grid manifests

Tile-assignment input requires:

```text
event_id
x_index
y_index
dataset_role
overlap_group_id
valid_data_fraction
feature_schema_version
source_timestamp
confidence_class
assumptions
```

Canonical tile output adds stable ids, the full grid hash, projected bounds, CRS, resolution, grid origin, pixel dimensions, query size, and fixed safety flags.

Canonical query output contains:

```text
query_region_id
tile_id
event_id
grid_id
grid_contract_sha256
source_registry_sha256
processing_alignment_receipt_sha256
pre_source_asset_ids
event_source_asset_ids
pre_product_ids
event_product_ids
pre_acquisition_utc
event_acquisition_utc
pre_source_sha256s
event_source_sha256s
query_row
query_col
query_size_pixels
resolution_m
bbox_min_x
bbox_min_y
bbox_max_x
bbox_max_y
crs
dataset_role
overlap_group_id
feature_schema_version
review_status
selected
eligible_for_human_annotation
eligible_for_active_selection
eligible_for_review_queue
eligible_for_query_model_training
eligible_for_training_after_human_review
query_model_only
eligible_for_decision_layer
eligible_for_fpps
eligible_for_warning
source_timestamp
confidence_class
assumptions
```

Canonical label-factory grid rows require `feature_schema_version=sar_change_v2`. Every tile/query row binds the exact processing receipt hash, and grid validation requires the receipt's processed extent to cover every tile. Unreviewed rows have `eligible_for_query_model_training=false`; the training/query role grants active-selection eligibility, not a label. Calibration, development, and untouched-test rows may be human-annotation eligible under their explicit non-acquisition review purpose while remaining ineligible for active selection and query-model training. Query cores must not overlap. The manifest writers refuse to overwrite existing canonical output paths.

## 7. Label and weak-seed codes

Canonical human labels:

| Code | Class | Binary target |
| ---: | --- | ---: |
| 0 | `dry_land` | 0 |
| 1 | `temporary_flood` | 1 |
| 2 | `permanent_or_preexisting_water` | 0 |
| 3 | `uncertain_water_change` | Excluded |
| 4 | `unobservable_or_artifact` | Excluded |
| 255 | `unreviewed` | Excluded |

Weak-seed codes retain separate provenance:

| Code | Weak meaning |
| ---: | --- |
| 1 | `weak_positive` |
| 3 | `weak_uncertain` boundary buffer |
| 255 | `unreviewed` exterior |

A weak code of 1 is not thereby reviewed `temporary_flood`. Downstream artifacts must retain the seed id, source GeoJSON checksum, event/grid/query lineage, query-manifest checksum, timestamp, and assumptions.

### Batch weak-query summary

`build_weak_query_summary.py` bridges the real GeoPackage source to every
canonical core. It verifies the weak-source manifest and source checksum,
reprojects the vector into the one declared query CRS, and tests canonical cell
centres. Its output fields include:

```text
query_region_id, event_id, tile_id, grid_contract_sha256
weak_label
weak_positive_fraction, weak_uncertain_fraction, weak_unreviewed_fraction
weak_boundary_query
weak_source_type, weak_source_sha256, weak_source_manifest_sha256
query_manifest_sha256, weak_summary_manifest_sha256
source_timestamp, confidence_class, assumptions
operator_internal_only, selection_creates_flood_truth
eligible_for_query_model_training, model_purpose
query_model_only, eligible_for_review_queue
eligible_for_training_after_human_review
eligible_for_decision_layer, eligible_for_fpps, eligible_for_warning
```

`weak_label=unreviewed` outside the polygon never means dry land. Invalid source
geometry fails closed unless the caller explicitly requests `shapely.make_valid`;
the manifest then records the original validity reason and repair method. That
repair is geometry hygiene for low-confidence weak context, not new truth.

## 8. Feature schemas

| Schema | Contract |
| --- | --- |
| `legacy_synthetic_sar_v1` | Reproduction-only synthetic baseline with its historical 0.60 VV + 0.40 VH score |
| `legacy_real_weak_sar_v1` | Reproduction-only weak-reference extractor with its historical 0.40 VV + 0.60 VH score and ratios |
| `sar_change_v2` | Canonical label-factory model schema |

Required `sar_change_v2` feature order:

```text
pre_vv_db
event_vv_db
pre_vh_db
event_vh_db
vv_change_db
vh_change_db
valid_data_fraction
```

Optional schema-declared features include local change quantiles/standard deviations, elevation, slope, permanent-water and land-cover fractions, building fraction, river distance, incidence angle, and alignment error.

`combined_sar_change_score` is not a `sar_change_v2` feature. If emitted for reviewer display or diagnostics, it stays outside the training feature order. Exact feature order, schema version, labelset id, and labelset-manifest SHA-256 are recorded on every committee run.

## 9. Blinded review bundle

`review_regions.csv` exposes only the review geometry plus exact registered source lineage:

```text
query_region_id, tile_id, event_id, grid_id, grid_contract_sha256
source_registry_sha256, pre_source_asset_ids, event_source_asset_ids
processing_alignment_receipt_sha256
pre_product_ids, event_product_ids, pre_acquisition_utc, event_acquisition_utc
pre_source_sha256s, event_source_sha256s
feature_schema_version, query_size_pixels, resolution_m, dataset_role, review_purpose
bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y, geometry_wkt, crs
review_status, source_timestamp, confidence_class, assumptions
```

The required `context_layers.csv` uses:

```text
context_layer_id, event_id, layer_role, source_registry_sha256
source_asset_id, source_product_id, acquisition_time_utc, source_sha256
processed_layer_sha256, display_name, path_hint, crs
allowed_for_blinded_review, confidence_class, assumptions
```

For each event it must contain pre/event VV and VH, permanent-water context, land cover, and DEM hillshade or slope. Raw SAR rows must match the query and processing-receipt lineage exactly, including the processed-file checksum. Static JRC, WorldCover, and Copernicus DEM rows must match the sealed `aligned_context_inventory.csv` by event, layer id, role, path hint, processed hash, source hash, CRS, and safety status. A context role outside the currently governed SAR/static/derivative set is rejected until its own rights and lineage are added. The bundle includes a canonical `processing_alignment_receipt.json`, itself checksum-bound by `bundle_manifest.csv`.

VV/VH change displays are optional and require all three roles:

```text
vv_change
vh_change
fixed_stretch_change_composite
```

They are admitted only with a verified
`floodguard.review_derivative_lineage_receipt.v1`. That receipt binds the exact
pre/event VV/VH processed source hashes, governed polarization/band mappings, source/event/processing/governance/grid
identity, canonical `pre_db - event_db` transformations, fixed non-dynamic
display parameters, three output hashes, and immutable safety fields. The three
context rows must exactly match the receipt, which is copied into the bundle as
`review_derivative_lineage_receipt.json`. `bundle_manifest.csv` repeats the
receipt self-hash, copied-file hash, and a governed-derivatives flag on every
row. Formal annotation import revalidates the receipt rather than trusting the
manifest alone. See `docs/review_derivative_lineage.md` for the exact build-spec
and context-row mapping.

Candidate generation records
`authority_approval_status=authority_approval_pending`. The derivative
receipt's `production_review_eligible=true` means only that source governance
and technical lineage passed; it does not mean the display was approved by the
Reference Authority. Pending candidates are not eligible to enter
`context_layers.csv` or any reviewer bundle. Authority approval is a separate
attributable human artifact.

The implemented authority artifact is
`floodguard.reference_authority_design_approval.v1`. It is an immutable,
self-hashed, internally manifested package that revalidates and copies the
complete pre-calibration human-role package, provisional reserve-design
package, attributable decision export, fixed reference procedure, and optional
derivative receipt. It binds the appointed Reference Authority role/person ids,
decision/capture UTCs, exact hashes, one reserve candidate id, procedure
version, and explicit derivative decision. Its evidence status is limited to
local-copy hash and declared attribution; software does not authenticate the
sender or interpret opaque evidence.

Its only possible positive scope fields are
`may_start_separate_canonical_reserve_construction` and
`may_start_separate_reference_construction`. It cannot change dataset roles,
select query ids, create reference labels, run calibration, authorize a bundle
or formal review, train a model, feed the decision layer/FPPS, or issue a
warning. A derivative approval only allows the exact receipt to be considered
by that later construction; it is not a production context release. See
`docs/reference_authority_design_approval.md`.

Every bundle has one projected CRS, one event, and one explicit purpose:
`acquisition_primary`, `reviewer_calibration`, or `fixed_evaluation`. A
production bundle also consumes a checksum-validated, immutable human-role
package and names one appointed target reviewer:

| Bundle purpose | Required human-role package | Time gate |
| --- | --- | --- |
| `reviewer_calibration` | Evidence-complete pre-calibration package; target `reviewer_a` for `primary` or `reviewer_b` for `secondary`; no calibration receipt; `formal_review_authorized=false` | Planned start is at or after the frozen package `created_at_utc` |
| `acquisition_primary` | Post-calibration package for the same target lane with a passing receipt and `formal_review_authorized=true` | Planned start is at or after both package creation and `formal_review_authorized_from_utc` |
| `fixed_evaluation` | Same post-calibration gate as acquisition | Same formal-review time gate |

The package event, protocol, and taxonomy must equal the bundle values. The
writer rejects a target id that is not the exact appointed role id, prefills
that id in `annotation_template.csv`, and records the human-role package id,
manifest and file hashes, gate status, target lane, planned start, effective
not-before time, and any calibration-receipt hashes in every
`bundle_manifest.csv` row. A synthetic fixture may omit this binding only by an
explicit internal test flag; the production CLI has no such escape.

A review-derivative lineage receipt remains insufficient to authorize a
production bundle even after a design review. Until a separate canonical
derivative-context release artifact and validator are implemented, the
production writer fails closed whenever a derivative receipt is supplied.
Synthetic lineage fixtures remain available solely for contract tests.

Model scores, entropy, disagreement, boundary/impurity, diversity, weak-label overlap, rank, lane, and selection reason are prohibited from reviewer-visible files. `bundle_manifest.csv` records file checksums, safety fields, governance package ID, package-manifest hash, package-seal self-hash, aligned-context inventory hash, processing-receipt self-hash, optional derivative-receipt hashes, human-role binding, and production-review eligibility. Synthetic fixture bundles are marked `synthetic_fixture_only` and are rejected by production annotation import. A bundle directory is write-once.

## 10. Completed annotation interchange and canonical log

The generated `annotation_template.csv` and completed import CSV use these fields:

```text
annotation_id
event_id
tile_id
query_region_id
reviewer_id
review_revision
review_stage
review_purpose
primary_class
class_code
confidence
ambiguity_reason_codes
evidence_layers_used
review_complete
reviewed_extent_status
reviewed_extent
geometry_wkt
review_started_at_utc
review_finished_at_utc
protocol_version
tool_version
model_predictions_visible
other_reviewer_annotations_visible
created_at_utc
locked_at_utc
supersedes_annotation_id
source_timestamp
assumptions
```

The class name and numeric code must agree. The reviewer id and all lock/timing fields are explicit; the importer invents none of them. Formal records require complete review, a nonblank reviewed extent, and independent blinding. Revised work appends a new record that names the superseded annotation. Import also checks event/tile/query identity and WKT containment against the original `review_regions.csv`.

The canonical annotation store is a hash-chained JSONL log. The completed CSV is only a validated interchange batch.

## 11. Geometry parts and reviewer rasterization

Geometry-part input fields:

```text
annotation_id
geometry_part_id
class_code
geometry_wkt
fill_unpainted_with_primary_class
```

Every locked annotation needs a geometry-control row. Geometry must be a valid polygon or multipolygon, stay inside the reviewed extent/query core, and not assign different classes to the same cell. Blank geometry is accepted only for an explicit primary-class fill control. Unpainted cells outside the reviewed extent remain 255.

The reviewer cell CSV records annotation/event/tile/query/reviewer/stage, stable cell id, row/column, label code/class, projected cell centre, CRS, grid id, timestamp, assumptions, and safety fields. Its JSON manifest binds the query and geometry-part row hashes to the output checksum. These individual reviewer cells are eligible for agreement but not query-model training.

### Reviewer-calibration reference and receipt

Calibration uses at least eight unique canonical queries whose fixed
`dataset_role` is `reviewer_calibration`. The expert/adjudicated reference cell
CSV contains the complete canonical cell grid for those queries. Its
`floodguard.calibration_reference_cells.v1` manifest binds the authority type
and id, protocol, `flood_label_v1` taxonomy, query-manifest checksum,
reference-cell checksum, exact query set, cell count, grid/source checksums,
source timestamps, safety flags, and its own canonical self-hash.

Before freeze, `floodguard.calibration_reference_geometry_raster.v1` binds a
named authority's locked geometry to the freezer-ready seven-column cell input.
It records the attributable role-evidence filename/checksum, exact authority
annotation ids/content hashes, query-manifest and geometry-part checksums,
output filename/checksum, exact query/grid/source lineage, cell and label-code
counts, confidentiality, and a canonical self-hash. Rasterization uses the
normal cell-centre contract: drawable codes are 0/1/2/3/4, code 255 is preserved
outside a partial reviewed extent, cross-class cell overlap is rejected, and
every reviewed cell must be explicitly drawn or filled. The raster-lineage
artifact is not itself the frozen reference; the normal reference freeze is
still mandatory.

`floodguard.reviewer_calibration_receipt.v1` binds:

```text
reviewer_ids, protocol_version, taxonomy_version
calibration_completed_at_utc, formal_review_not_before_utc
query_manifest_sha256, query_region_ids
annotation_sha256_by_id, annotation_ids_by_reviewer
reviewer_cell_sha256_by_reviewer
reviewer_cell_manifest_sha256_by_reviewer
calibration_reference_manifest_sha256
calibration_reference_cells_sha256
grid_contract_sha256_by_query, source_registry_sha256_by_query
source_timestamp_by_query, query_strata_sha256
metrics_by_reviewer, thresholds, receipt_sha256
```

Every reviewer/query assignment must resolve to a latest locked, complete,
independently blinded annotation and a checksum-verified canonical reviewer-cell
artifact. No reviewer or reference query may be 255-only. The default minimums
are temporary-flood Dice 0.75, Cohen's kappa 0.75, mean boundary F1 0.70, and
temporary-flood Dice 0.65 in every declared critical stratum. The receipt,
reference, and reviewer-calibration cells always declare query-model-training,
decision-layer, FPPS, and warning eligibility false. Freeze and revalidation
require the exact formal reviewer identities, protocol, taxonomy, and a formal
review start time at or after `formal_review_not_before_utc`; the receipt SHA is
also bound into release QA, release metadata, and the final validation receipt.

If valid calibration evidence fails one or more thresholds,
`floodguard.reviewer_calibration_failure_diagnostic.v1` may preserve the exact
reviewer/artifact/reference/query lineage, metrics, thresholds, and measured
failure reasons. It must declare `calibration_passed=false`,
`formal_review_authorized=false`, and `confidential=true`; it has its own
canonical self-hash and every downstream eligibility flag is false. It cannot
be created when every reviewer passes, is not accepted anywhere a passing
receipt is required, and belongs in restricted coordination storage because it
contains individual performance evidence.

## 12. Agreement and critical strata

Agreement JSON contains explicit reviewer A/B ids, `measurement_unit=canonical_cell_labels`, query and cell counts, boundary-metric query count, aggregate multiclass metrics, per-query boundary metrics, and a nonempty mapping of critical-stratum temporary-flood Dice.

The `query_strata` input maps every query id to one or more critical strata. Release validation requires temporary-flood Dice at least 0.80, IoU at least 0.67, Cohen's kappa at least 0.80, mean boundary F1 at least 0.75 with coverage for every query, and every critical-stratum Dice at least 0.70.

## 13. Adjudication contracts

Queue rows name both annotation ids and content hashes, query identity, explicit reason codes, UTC creation time, and `status=open`. Valid reasons cover class, geometry, reviewed-extent, low-confidence, uncertain, and unobservable disagreements.

Adjudication JSONL records include:

```text
adjudication_id, queue_id, event_id, tile_id, query_region_id
reviewer_a_annotation_id, reviewer_b_annotation_id
reviewer_a_sha256, reviewer_b_sha256
adjudicator_id, outcome, final_primary_class, final_geometry
resolution_reason_codes, notes, protocol_version
resolved_at_utc, locked_at_utc
```

Every resolution references and hashes the two immutable sources. Open items block freeze.

## 14. Canonical reviewed-cell lineage

The release validator currently accepts named artifacts in `canonical_cell_csv_v1` format. Each CSV requires:

```text
query_region_id
cell_id
row_index
column_index
label_code
source_annotation_id
source_adjudication_id
grid_contract_sha256
```

Every row references exactly one source annotation or one source adjudication. Query/cell pairs are unique. Codes must be in `{0,1,2,3,4,255}`. The complete grid hash must match the release lineage.

The companion raster-lineage JSON uses `artifact_schema=floodguard.reviewed_label_cells.v1` and records:

```text
grid_contract_sha256
rasterizer_version
source_annotation_ids
source_adjudication_ids
rasters: {
  <name>: {
    format: canonical_cell_csv_v1
    sha256: <64 hex>
    cell_count: <integer>
    class_counts: {<label_code>: <count>}
  }
}
```

The freeze command derives ordered `label_content` from these validated cells and requires an exact match with the supplied label-content JSON. A renamed or mutated raster, changed class count, unknown lineage id, grid mismatch, or altered label order blocks release.

`build_label_factory_consensus_cells.py` writes the canonical cell CSV, raster-lineage JSON, ordered label-content JSON, and a self-hashed `floodguard.consensus_builder_receipt.v1` JSON exactly once. Every successful build embeds the receipt in raster lineage. Freeze requires and revalidates it across direct consensus and every adjudication branch against the locked annotation/adjudication evidence, derivation rules, final-cell bytes, grid, and named raster hash. The standalone receipt is retained for audit; no branch authorizes training by itself.

## 15. QA release gate

The structured QA report must be nonempty, have no blocking failure, and include passing results for the current release check-id registry:

```text
source_product_id
source_acquisition_time
rights_processing
rights_label_derivation
pre_post_pair_present
pre_before_post
dataset_role_known
entity_single_dataset_role
overlap_group_single_dataset_role
untouched_test_isolation
binary_training_label_known
binary_training_label_eligible
binary_training_target_mapping
```

Annotation QA additionally defines checks for nonblank reviewer id, reviewed extent, model blinding, reviewer blinding, completion, and lock status. A release-specific QA build must preserve these results and the provenance of the entities inspected. Later active-learning round QA separately requires both `random_control_lane_present` and `random_control_sampling_design`; those checks are not prerequisites for the model-independent Round 0 labelset.

Release QA is assembled only from exact files. The required raw roles are:

```text
source_assets
dataset_assignments
usage_records
annotations
binary_training_rows
```

`query_models` and `query_records` are additional roles whenever those artifacts
are in release scope. Query records are audited both for their sampling design
and for the same fixed query-only, decision=false, FPPS=false, warning=false
contract as query models. An empty binary-candidate file is explicit evidence
that the label release has no eligible 0/1/2 candidate rows; it does not block
the label release, but it supplies no model-training evidence.

`build_label_factory_release_qa.py` writes a deterministic findings CSV and a
self-hashed `floodguard.label_factory_qa_receipt.v1`. The receipt preserves the
existing calibration, agreement, reviewer-cell, raster-lineage, and final-raster
bindings and additionally records:

```text
qa_assembler_version
qa_validator and qa_validator_version
qa_report_schema_version
qa_report_sha256 and qa_report_file_sha256
raw_input_roles_in_scope
raw_input_artifacts[role].file_name
raw_input_artifacts[role].schema_version
raw_input_artifacts[role].sha256
raw_input_artifacts[role].row_count
query_models_in_scope and query_records_in_scope
eligible_for_decision_layer = false
eligible_for_fpps = false
eligible_for_warning = false
receipt_sha256
```

Freeze and revalidation require the QA CSV plus every raw path, recompute all
hashes and findings, and require the QA CSV bytes to match the deterministic
assembler output. The annotations role must be the exact annotation-log path
used to rebuild consensus. A self-consistent hand-authored passing report is
therefore insufficient release evidence.

## 16. Labelset JSON and semantic versioning

An authoritative labelset manifest contains:

```text
labelset_name
version
labelset_id
change_kind
parent_labelset_id
parent_manifest_sha256
label_content_sha256
metadata_sha256
semantics_sha256
source_annotation_ids
raster_sha256_by_name
created_at_utc
manifest_sha256
```

The metadata hash incorporates adjudication ids, QA readiness/count, zero open adjudications, agreement-evidence hash, raster-lineage hash, query-model-training eligibility, and the fixed decision/FPPS/warning prohibitions. The manifest is written with exclusive-create semantics and cannot be overwritten.

Version rules:

- initial release: no parent and `change_kind=initial`;
- major: target/taxonomy/grid/semantics change;
- minor: label content or reviewed coverage change; and
- patch: metadata-only correction with unchanged label content and semantics.

## 17. Query committee and candidate artifacts

The committee output directory is new and immutable. It contains:

```text
logistic_query_model.json
logistic_query_model.manifest.json
boosted_query_model.manifest.json
grouped_oof_scores.csv
query_pool_scores.csv
committee_run_manifest.json
```

The logistic artifact is executable numeric JSON. The boosted artifact is a non-executable manifest only; no pickle is written. The run manifest binds inputs, labelset id/hash, feature order/schema, split policy, output checksums, timestamps, assumptions, and fixed query-only safety fields.

Cell scores are aggregated into one candidate row per query. Required query metadata includes the grid hash, schema, resolution/query size, projected bounds/CRS, role, review status, timestamp, confidence, assumptions, and fixed safety flags. Candidate evidence includes mean logistic, boosted, and committee probabilities, distance from the neutral 0.5 score, top-tail uncertainty, absolute and Jensen-Shannon disagreement, boundary impurity, hard-stratum flag, major land-cover stratum, explicit diversity summaries, supported-cell count, top-tail fraction, and aggregation rule.

## 18. Internal operator queue package

The write-once `floodguard.active_learning_operator_queue.v1` CSV is built only
after an acquisition manifest has selected queries. It may join the governed
context evidence, the weak-query summary, and an optional checksum-bearing
preview manifest by the exact query/event/tile/grid identity. It normalizes the
two model score summaries and contains, when supplied:

```text
event_id, tile_id, query_region_id, grid_id, grid_contract_sha256
projected bounds, WGS84 bounds, CRS
mean_logistic_query_score, mean_boosted_query_score
mean_committee_query_score, entropy_score
absolute_disagreement, jensen_shannon_disagreement, active_score
context fractions, slope_p90_degrees, context_stratum
weak_label and positive-unlabeled fractions
preview_path, preview_sha256, preview_manifest_sha256
selection_lane, selection_order, recommended_review_priority
source lineage, timestamp, confidence, assumptions, fixed safety fields
```

The package manifest re-hashes the queue and every supplied input and carries
its own canonical self-hash. `operator_internal_only=true` and
`reviewer_delivery_allowed=false` are invariants. The separately generated
blinded review bundle remains the only reviewer-delivery artifact and rejects
operator/model/weak/priority fields.

## 19. Fixed safety fields

Every query-ranking, candidate, and acquisition artifact is constrained to:

```text
model_purpose = query_ranking
eligible_for_review_queue = true
eligible_for_training_after_human_review = conditional
query_model_only = true
eligible_for_decision_layer = false
eligible_for_fpps = false
eligible_for_warning = false
selection_creates_flood_truth = false
```

These are semantic invariants, not thresholds. Weak evidence, uncertainty, model agreement, or high evaluation scores cannot promote an artifact into the FloodGuard decision layer.
