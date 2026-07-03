# Data Contract

## Common Output Fields

Every analytical output should include these fields when applicable:

- `source_name`
- `source_timestamp`
- `confidence_class`
- `assumptions`

`confidence_class` should use one of:

- `high`
- `medium`
- `low`

## Subdistrict Priority Input

One row per subdistrict.

Required columns:

- `subdistrict_id`
- `subdistrict_name`
- `flood_likelihood_0_100`
- `exposure_0_100`
- `access_gap_0_100`
- `road_criticality_0_100`
- `vulnerability_context_0_100`
- `confidence_class`

Recommended columns:

- `source_name`
- `source_timestamp`
- `assumptions`

## Subdistrict Priority Output

Required columns:

- `subdistrict_id`
- `subdistrict_name`
- `fpps_0_100`
- `action_class`
- `top_reason`
- `confidence_class`

The implementation may preserve additional columns from the input.

## Road-Risk Input

Road features are keyed by `road_id`.

Required road columns:

- `road_id`
- `road_class`
- `bridge_flag`
- `subdistrict_id`
- `surrounding_inundation_0_1`

Required flood-probability columns:

- `subdistrict_id`
- `mean_flood_probability_0_1`
- `confidence_class`
- `source_name`
- `source_timestamp`

## Road-Risk Output

Required columns:

- `road_id`
- `subdistrict_id`
- `road_disruption_probability_0_1`
- `confidence_class`
- `top_risk_reason`
- `source_name`
- `source_timestamp`
- `assumptions`

## Access-Loss Input

Required edge columns:

- `from_node`
- `to_node`
- `normal_minutes`
- `disrupted_minutes`

Required population-node columns:

- `node_id`
- `subdistrict_id`
- `total_population`
- `vulnerable_population`
- `non_vulnerable_population`

Required facility columns:

- `facility_id`
- `facility_type`
- `node_id`

Blank `disrupted_minutes` means the edge is closed or unreachable in the disrupted network.

## Access-Loss Output

One row per subdistrict.

Required fields for each configured threshold:

- `people_losing_15_min_access`
- `people_losing_30_min_access`
- `people_losing_60_min_access`
- `vulnerable_population_losing_15_min_access`
- `vulnerable_population_losing_30_min_access`
- `vulnerable_population_losing_60_min_access`
- `non_vulnerable_population_losing_15_min_access`
- `non_vulnerable_population_losing_30_min_access`
- `non_vulnerable_population_losing_60_min_access`

## Equity-Gap Output

Required columns:

- `subdistrict_id`
- `subdistrict_name`
- `vulnerable_access_loss_rate`
- `non_vulnerable_access_loss_rate`
- `equity_gap_ratio`
- `interpretation_text`
- `confidence_class`

## Dashboard GeoJSON Outputs

Dashboard-ready GeoJSON exports are generated from fixture outputs and geometries:

- `outputs/priority_subdistricts.geojson`, keyed by `subdistrict_id`
- `outputs/road_risk.geojson`, keyed by `road_id`

Exports must preserve `source_timestamp`, `confidence_class`, and `assumptions` where available.

`outputs/priority_subdistricts.geojson` also carries fixture scenario-comparison fields:

- `baseline_people_losing_30_min_access`
- `baseline_equity_gap_ratio`
- `temporary_shelter_people_losing_30_min_access`
- `temporary_shelter_change_people_losing_30_min_access`
- `temporary_shelter_equity_gap_ratio`
- `temporary_shelter_change_equity_gap_ratio`
- `road_closure_people_losing_30_min_access`
- `road_closure_change_people_losing_30_min_access`
- `road_closure_equity_gap_ratio`
- `road_closure_change_equity_gap_ratio`

Scenario comparison rows must cover every exported priority subdistrict before GeoJSON export.

## Validation Summary Output

`outputs/validation_summary.md` summarizes fixture-backed priority, road-risk, access-loss, and equity-gap outputs.

Required report sections:

- Fixture Coverage
- Priority Score Summary
- Road Risk Summary
- Access Loss Summary
- Equity Gap Summary
- Sensitivity Summary
- Future Validation Metrics
- Assumptions

The future metrics section must explicitly reserve placeholders for IoU, F1/Dice, precision, recall, area error, Brier score, calibration, road closure precision/recall, and score sensitivity. Fixture score sensitivity is implemented; real calibration remains pending.

## Action Brief Output

`outputs/action_brief_<subdistrict_id>.md` is a one-page Markdown brief for a selected subdistrict.

Required content:

- bilingual Thai/English section labels
- FPPS, action class, top reason, and confidence
- access-loss counts
- equity-gap ratio and interpretation
- likely road-risk rows for the subdistrict
- assumptions
- recommended action in English and Thai

Default selection uses the highest actionable class order `A > B > C > D > E`, then highest FPPS.

Default batch generation writes briefs for actionable `A/B/C` subdistricts only. Manual single-brief generation may still produce `D/E` briefs when explicitly requested.

## Scenario Outputs

Fixture scenarios compare baseline access/equity against an intervention or stress toggle.

Current scenarios:

- `add_temporary_shelter`
- `close_road`

Outputs:

- `sample_scenario_<scenario>_access_loss.csv`
- `sample_scenario_<scenario>_equity_gap.csv`
- `sample_scenario_summary.csv`

## Sensitivity Outputs

`sample_fpps_sensitivity.csv` contains one scored row per subdistrict per weight scenario.

`sample_fpps_rank_instability.csv` contains:

- `subdistrict_id`
- `subdistrict_name`
- `default_rank`
- `best_rank`
- `worst_rank`
- `rank_range`
- `default_action_class`
- `confidence_class`
- `ranking_unstable`

## Static Dashboard Output

`outputs/dashboard.html` is a standalone HTML dashboard generated from:

- `outputs/priority_subdistricts.geojson`
- `outputs/road_risk.geojson`
- `outputs/validation_summary.md`
- `outputs/action_brief_<subdistrict_id>.md` files

It embeds GeoJSON and Markdown directly in the file and uses Leaflet from CDN for map rendering. It has no backend or build step.

Dashboard v2 required controls:

- subdistrict selector
- A-E action-class filters
- scenario selector with `baseline`, `temporary shelter delta`, and `road closure delta`
- scenario-delta highlighting for priority polygons
- embedded action briefs keyed by `subdistrict_id`

Dashboard v3 also includes summary cards for:

- best intervention effect, using the most negative temporary-shelter 30-minute access-loss delta
- worst road-closure stress case, using the most positive road-closure 30-minute access-loss delta

Dashboard v4 adds browser-only export buttons:

- `Download current brief`, which downloads the selected embedded Markdown action brief
- `Download filtered GeoJSON`, which downloads a FeatureCollection containing priority polygons that match the active A-E filters

The export buttons must use embedded page data only. They must not call `fetch`, require a backend, or write server-side files.

Dashboard THEOS-2 optical context uses:

- `outputs/theos2_selected_file_manifest.csv`
- `outputs/theos2_previews/*.svg`

These artifacts are optical context only. They must not be described as flood validation, flood reference masks, or official warnings.

## CDSE Metadata Query Output

The CDSE metadata query script is no-download and metadata-only. It must not download Sentinel product assets.

Required CSV columns:

- `acquisition_date`
- `product_name`
- `cdse_product_id`
- `online_status`
- `mission_platform_prefix`
- `product_storage_type`
- `candidate_role`
- `query_profile`
- `source_url`
- `blocker_note`

Supported profiles:

- `mae_sai_2024`
- `hat_yai_2025`

Live metadata snapshots may be written as:

- `outputs/cdse_mae_sai_2024_metadata.csv`
- `outputs/cdse_hat_yai_2025_metadata.csv`

These files should only be committed after intentional review using `docs/live_metadata_snapshot_review_checklist.md`.

## Metadata-Only Ingestion Manifest

`outputs/real_data_ingestion_manifest.csv` is the first real-data ingestion skeleton. It records source planning rows and blockers only.

Required columns:

- `source_name`
- `study_area`
- `source_url`
- `candidate_use`
- `geometry_access_status`
- `license_status`
- `redistribution_status`
- `next_action`
- `product_id`
- `local_path`
- `sha256`
- `source_license_status`
- `reference_mask_status`
- `ingestion_stage`
- `download_permitted_by_skeleton`
- `ready_for_processing`
- `processing_allowed`
- `blocked_reason`
- `reason_blocked`

Current rows must remain `metadata_only`, with `download_permitted_by_skeleton=False` and `ready_for_processing=False`.

The ingestion skeleton may only write metadata outputs with explicit metadata suffixes such as `.csv`, `.json`, `.md`, or `.txt`. It must reject binary or imagery/product paths such as `.SAFE`, `.tif`, `.tiff`, `.jp2`, `.zip`, `.nc`, and `.grib`.

`processing_allowed=True` is permitted only when source license status, reference-mask status, local path, product id, and SHA-256 checksum gates all pass. Manual overrides that force processing before those gates pass must fail.

## Synthetic SAR Baseline Output

The current SAR baseline is a synthetic, non-ML fixture used to test validation wiring. It does not read real Sentinel-1 imagery.

`outputs/sample_sar_baseline.csv` required columns:

- `pixel_id`
- `row`
- `col`
- `pre_vv_db`
- `post_vv_db`
- `pre_vh_db`
- `post_vh_db`
- `vv_drop_db`
- `vh_drop_db`
- `combined_drop_db`
- `flood_probability_0_1`
- `binary_flood_extent`
- `reference_flood_extent`
- `confidence_class`
- `assumptions`

`outputs/sample_sar_validation_metrics.csv` required columns:

- `true_positive`
- `false_positive`
- `false_negative`
- `true_negative`
- `iou`
- `f1_dice`
- `precision`
- `recall`
- `area_error_ratio`

## Study-Area Inventory Output

`docs/study_area_inventory.md` records real-data acquisition planning only. It may include exact candidate metadata, product ids, licensing notes, and blockers, but this repository change does not download real imagery or implement remote-sensing model code.

`docs/reference_mask_licensing_log.md` records candidate reference-mask licensing status before processing or redistribution.

`docs/licensing_request_templates.md` contains copy-ready request templates for UNOSAT/UNITAR, GISTDA, International Charter, and Sentinel Asia.

`docs/ml_readiness_plan.md` defines the gates that must pass before real-data ML work starts: usable reference mask, locked Sentinel-1 pair, reviewed metadata snapshot, source files tracked outside Git, reproducible non-ML baseline, and scoped validation metrics.

`docs/sar_baseline_contract.md` defines the first non-ML Sentinel-1 baseline contract. `docs/first_ml_experiment_plan.md` defines when the first real-data ML experiment is allowed.

`docs/licensing_outreach_status.md` tracks provider requests. Repository automation does not send emails or web forms. The project owner reported sending the UNOSAT/UNITAR and GISTDA requests on 2026-07-03; those rows remain blocked until provider responses confirm geometry access, local validation, derived metrics, screenshot, redistribution, and ML-label terms.

`docs/mae_sai_pair_decision_note.md` records the selected Mae Sai planning pair and the fallback post-event acquisition. It is a planning lock, not processing authorization.

## THEOS-2 Metadata-Only Inventory

`outputs/theos2_local_metadata_manifest.csv` records local THEOS-2 hackathon sample metadata only. It must not include source imagery pixels or committed absolute local paths.

Required columns include:

- `file_name`
- `local_path_hint`
- `entry_kind`
- `zip_member_count`
- `zip_categories`
- `category`
- `file_size_bytes`
- `file_size_gb`
- `acquisition_date`
- `acquisition_time_utc`
- `processing_level`
- `sensor_product`
- `tile_id`
- `sequence_id`
- `tiff_version`
- `image_width`
- `image_height`
- `samples_per_pixel`
- `bits_per_sample`
- `compression`
- `pixel_size_m`
- `crs_hint`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `mvp_overlap`
- `floodguard_relevance`
- `license_status`
- `sha256_status`
- `processing_allowed`
- `reason_blocked`

Current THEOS-2 rows use `license_status=user_reported_hackathon_free_use` based on project-owner reporting on 2026-07-03, logged in `docs/theos2_usage_terms_log.md`. Rows still remain `processing_allowed=False` until SHA-256 checksums are recorded for selected files. THEOS-2 is an optical context and feature-development lane, not the legal flood reference-mask lane.

## THEOS-2 Selected-File Manifest

`outputs/theos2_selected_file_manifest.csv` records only selected local THEOS-2 files that have been SHA-256 checksum tracked. It must not include absolute local paths or source pixels.

Required columns include:

- `file_name`
- `local_path_hint`
- `entry_kind`
- `category`
- `file_size_bytes`
- `file_size_gb`
- `source_timestamp`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `license_status`
- `checksum_algorithm`
- `sha256`
- `sha256_status`
- `processing_scope`
- `reference_mask_status`
- `processing_allowed`
- `preview_path`
- `assumptions`
- `reason_blocked`

Rows may set `processing_allowed=True` only for `processing_scope=theos2_optical_context_preview_only` after `license_status=user_reported_hackathon_free_use` and `sha256_status=recorded`. This is not permission to use THEOS-2 as a flood reference mask or real-data ML label source.

## THEOS-2 Preview Artifacts

`outputs/theos2_previews/*.svg` are small non-operational SVG preview cards generated from checksum-backed metadata. They do not contain source imagery pixels and are intended for dashboard/action-brief context only.

## GeoJSON Fixtures

GeoJSON fixtures should use WGS84 coordinates (`EPSG:4326`) and small synthetic geometries unless source licensing is explicitly documented.
