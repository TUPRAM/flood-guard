# Model Contract

## 1. Flood Preparedness Priority Score

Input table: one row per subdistrict.

Required columns:

- `subdistrict_id`
- `subdistrict_name`
- `flood_likelihood_0_100`
- `exposure_0_100`
- `access_gap_0_100`
- `road_criticality_0_100`
- `vulnerability_context_0_100`
- `confidence_class`

Default formula:

```text
FPPS =
  0.30 * flood_likelihood_0_100 +
  0.25 * exposure_0_100 +
  0.20 * access_gap_0_100 +
  0.15 * road_criticality_0_100 +
  0.10 * vulnerability_context_0_100
```

Output:

- `fpps_0_100`
- `action_class`
- `top_reason`
- `confidence_class`

## 2. Action Class Logic

Class A - Protect Lives Now:
High exposure and high access loss, especially where vulnerable groups are affected.

Class B - Keep Routes Open:
Critical road or bridge disruption causes isolation.

Class C - Protect Essential Services:
Hospitals, clinics, schools, or emergency facilities are exposed or unreachable.

Class D - Build Resilience:
Recurrent exposure but not immediate crisis.

Class E - Monitor and Verify:
Low exposure or high model uncertainty.

Initial implementation rule priority:

1. `E` when `confidence_class` is `low` or FPPS is below 35.
2. `A` when exposure is at least 70 and access gap is at least 70.
3. `B` when road criticality is at least 75 and access gap is at least 55.
4. `C` when exposure is at least 65 and access gap is at least 50.
5. `D` for all remaining subdistricts.

These thresholds are intentionally simple for the MVP and should be sensitivity-tested later.

## 2b. GeoAI Component Scales (versioned anchors)

When `flood_likelihood_0_100` and `exposure_0_100` are produced by the GeoAI
runner they must use **fixed, versioned, event-independent anchors**. Scaling a
component by the maximum observed within a batch is prohibited: it makes the
value a within-batch rank rather than a level, so it cannot be compared across
events, study areas, or time, and the top unit scores near the ceiling even when
nothing is happening.

`fpps_flood_anchor_v1`:

```text
observed_term = min(1, flooded_share / 0.05)
prior_term    = clip(0.5 + 1.85 * (susceptibility_mean - 0.65), 0, 1)
flood_likelihood_0_100 = 100 * (0.70 * observed_term + 0.30 * prior_term)
```

`fpps_exposure_anchor_v1`:

```text
exposure_0_100 = 100 * min(1, population_per_km2 / 1000)
```

Every row must carry `flood_anchor_version` and `exposure_anchor_version`.
Changing an anchor requires a new version identifier; anchors must not be edited
in place, because previously published numbers cite them.

`confidence_class` for these rows is the gap between the two normalised terms
above (`< 0.35` high, `< 0.65` medium, else low), so confidence and score are
derived from the same quantities. A row whose population context is missing is
`low` regardless of gap.

### Exposure basis change

`exposure_0_100` was previously derived from OpenStreetMap building density. It
is now **WorldPop population density**. The reason is measurable rather than
stylistic: across Mae Sai's eight tambons, OSM building coverage is 0.9%-5.1% of
the population-implied expectation and exactly zero in two of them, so the old
value substantially encoded OpenStreetMap contributor activity rather than
exposure while carrying 25% of the FPPS weight.

OSM building counts remain in the output as diagnostics only, with
`osm_building_count`, `osm_completeness_ratio` and `osm_completeness_flag`
(`usable` | `severely_incomplete` | `unknown_no_population`). They must not enter
any score while flagged `severely_incomplete`.

Absent population must yield a null exposure and a `low` confidence class, never
a zero: missing data is not an absence of people.

### Non-AI components

`access_gap_0_100`, `road_criticality_0_100` and `vulnerability_context_0_100`
must be joined from decision-layer outputs, not synthesised from the AI signals
(which double-counts the flood term). When real context is unavailable the row
records `context_source="placeholder"` and its confidence is forced to `low`.

## 3. Evacuation Equity Gap

For each subdistrict:

```text
vulnerable_access_loss_rate =
  vulnerable_population_losing_access / total_vulnerable_population

non_vulnerable_access_loss_rate =
  non_vulnerable_population_losing_access / total_non_vulnerable_population

equity_gap_ratio =
  vulnerable_access_loss_rate / non_vulnerable_access_loss_rate
```

Handle division by zero explicitly.

Output:

- `vulnerable_access_loss_rate`
- `non_vulnerable_access_loss_rate`
- `equity_gap_ratio`
- `interpretation_text`

Zero-denominator behavior:

- If there is no vulnerable denominator, vulnerable rate and ratio are null.
- If there is no non-vulnerable denominator, non-vulnerable rate and ratio are null.
- If non-vulnerable loss rate is zero while vulnerable loss exists, ratio is null and marked undefined.
- If both groups have zero loss, ratio is `1.0`.

## 4. Road-Disruption Probability

Road disruption probability is a fixture-level heuristic, not an observed road-closure claim.

```text
road_disruption_probability_0_1 =
  0.65 * mean_flood_probability_0_1
  + 0.20 * surrounding_inundation_0_1
  + 0.10 * road_class_factor
  + 0.05 * bridge_factor
```

The result is clamped to `0.0-1.0` and rounded to three decimals.

Road class factors:

- `motorway`, `trunk`, `primary`: `1.0`
- `secondary`: `0.75`
- `tertiary`: `0.55`
- `local`, `residential`, `unclassified`: `0.35`

Bridge factor:

- `1.0` when `bridge_flag` is true
- `0.0` when `bridge_flag` is false

## 5. Access-Loss Prototype

The fixture access model compares shortest travel time to any selected facility under two networks:

- normal network, using `normal_minutes`
- disrupted network, using `disrupted_minutes`

Blank disrupted edge times mean the edge is closed in the disrupted scenario.

A population node counts as losing X-minute access only when it had normal access within X minutes and disrupted access is missing or greater than X minutes.

This is nearest-facility shortest-path threshold analysis, not full 2SFCA.
Facility capacity and competing catchment demand are not modeled. Do not label
the current output as 2SFCA unless a later capacity-aware extension and its
contract tests are implemented.

## 6. Scenario Mode

Scenario mode reruns access loss and equity gap on fixture data only.

Current scenarios:

- `add_temporary_shelter`: append a temporary shelter at node `P2A`.
- `close_road`: close the disrupted edge between `P2B` and `F1` unless overridden.

Scenario summaries compare baseline and scenario 30-minute access loss and max numeric equity-gap ratio.

Dashboard-ready priority GeoJSON must include per-subdistrict scenario comparison fields for baseline, temporary shelter, and road closure 30-minute access loss and equity-gap ratios. Scenario deltas are calculated as scenario value minus baseline value.

## 7. FPPS Weight Sensitivity

Sensitivity analysis reruns FPPS with deterministic weight scenarios:

- `default`
- `access_heavy`
- `exposure_heavy`
- `road_heavy`
- `vulnerability_heavy`

Weights are normalized before scoring. Rank instability is flagged when a subdistrict's rank range across scenarios is at least 2. Sensitivity does not override action class or confidence.

Validation summaries should report stable/unstable rank counts and disclose when the highest numeric FPPS row is low confidence and is not selected as the top actionable brief target.

## 8. Action Brief And Dashboard Presentation

Action briefs are compact Markdown decision products, not official warnings. Briefs should use bilingual Thai/English section labels for:

- Priority / ลำดับความสำคัญ
- Access Loss / การสูญเสียการเข้าถึง
- Equity Gap / ช่องว่างความเสมอภาคในการอพยพ
- Likely Road Risks / ความเสี่ยงถนนที่อาจถูกตัดขาด
- Recommended Action / ข้อเสนอการปฏิบัติ
- Assumptions / สมมติฐาน

The static dashboard is a fixture-backed presentation artifact generated from GeoJSON/Markdown outputs. It should embed its data directly, use no backend, and preserve the non-operational warning boundary.

Dashboard v2 adds subdistrict selection, A-E filtering, and scenario-delta highlighting. Negative 30-minute access-loss deltas indicate improvement, positive deltas indicate worsening, and zero or null deltas are neutral/unavailable.

Action brief v3 generates default briefs for actionable A/B/C subdistricts and includes recommended actions in both English and Thai. D/E brief generation remains available only through explicit single-brief selection.

Dashboard v3 adds two global scenario summary cards:

- Best intervention effect: the most negative temporary-shelter 30-minute access-loss delta.
- Worst road-closure stress case: the most positive road-closure 30-minute access-loss delta.

Dashboard v4 adds static export controls:

- Download the currently selected embedded action brief as Markdown.
- Download the currently filtered priority GeoJSON from embedded feature data.

These controls must run entirely in the browser and must not require `fetch`, a backend, or a build step.

## 9. CDSE Metadata Planning

CDSE metadata querying is catalogue-only. It records candidate Sentinel-1 product metadata from OData and must not download product assets.

Current query profiles:

- `mae_sai_2024`: `POINT(99.88 20.43)`, `SENTINEL-1`, `IW_GRDH_1SDV`, 2024-09-01 through 2024-09-25.
- `hat_yai_2025`: `POINT(100.47 7.01)`, `SENTINEL-1`, `IW_GRDH_1SDV`, 2025-11-17 through 2025-12-05.

Mae Sai reference-mask target v1 is UNOSAT/UNITAR planning evidence only until geometry access and redistribution/license terms are confirmed.

## 10. Metadata-Only Real-Data Ingestion Skeleton

The first ingestion skeleton records source metadata, licensing blockers, and next actions only. It must not download real source data, run remote-sensing model code, or mark any row processing-ready until geometry, license, and redistribution status are confirmed.

The skeleton must also reject output paths that look like imagery, product packages, or binary remote-sensing assets. Metadata-only outputs may use `.csv`, `.json`, `.md`, or `.txt`.

File-level readiness fields:

- `product_id`
- `local_path`
- `sha256`
- `source_license_status`
- `reference_mask_status`
- `processing_allowed`
- `reason_blocked`

`processing_allowed=True` is allowed only when geometry, license, redistribution/reference-only status, product id, local path, SHA-256 checksum, source license, and reference-mask gates are all confirmed.

## 11. ML Readiness

FloodGuard is not ready for real-data ML until these gates pass:

1. A legally usable flood reference mask is confirmed.
2. A pre/post Sentinel-1 pair is locked against the flood peak or reference-mask date.
3. Any live CDSE metadata snapshot has passed the snapshot review checklist.
4. Source files are tracked outside Git with paths, checksums, product IDs, and access terms.
5. A deterministic non-ML baseline can report IoU, F1/Dice, precision, recall, area error, and calibration caveats.

The first real-data ML step is the report-only label factory: it ranks regions for human review and cannot feed flood probability, FPPS, action classes, or warnings. A later flood-model promotion programme is separate and remains blocked until label quality, licensing, calibration, and untouched geographic validation are credible.

## 12. Synthetic SAR Baseline

The current SAR baseline is a non-ML synthetic fixture, not real Sentinel-1 processing.

Fixture formula:

```text
vv_drop_db = pre_vv_db - post_vv_db
vh_drop_db = pre_vh_db - post_vh_db
combined_drop_db = 0.60 * vv_drop_db + 0.40 * vh_drop_db
flood_probability_0_1 = clamp((combined_drop_db - 0.5) / (4.0 - 0.5), 0, 1)
binary_flood_extent = flood_probability_0_1 >= 0.5
```

This formula is now explicitly versioned as `legacy_synthetic_sar_v1`. The real Mae Sai weak-reference extractor historically used `0.40 * vv_drop_db + 0.60 * vh_drop_db`; that behavior is preserved as `legacy_real_weak_sar_v1` so existing outputs remain reproducible. The two legacy schemas must not be mixed in one training or evaluation table.

The flood-label factory uses `sar_change_v2`. Its trainable SAR core retains pre/post VV/VH and separate VV/VH dB drops. Ratio columns are deterministic transformations of the drops and a combined score is diagnostic only, not an additional independent signal. Every label-factory feature table, query model, and label release must record `feature_schema_version`.

Validation metrics:

- IoU
- F1/Dice
- precision
- recall
- area error ratio

This baseline is the required benchmark before any first ML experiment.
