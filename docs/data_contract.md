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

Dashboard v5 displays compact THEOS-2 optical-context cards. When `outputs/theos2_thumbnail_manifest.csv` exists, cards should use `outputs/theos2_thumbnails/*.png`; otherwise they fall back to `outputs/theos2_previews/*.svg`.

Dashboard v6 displays a compact Local Data Library panel. It embeds summary counts and blocker states from:

- `outputs/local_data_library_manifest.csv`
- `outputs/sentinel1_selected_file_manifest.csv`
- `outputs/sentinel1_provenance_resolved_manifest.csv`
- optionally `outputs/sentinel1_quicklook_manifest.csv`
- `outputs/dem_selected_file_manifest.csv`
- optionally `outputs/dem_quicklook_manifest.csv`
- `outputs/theos2_selected_file_manifest.csv`
- optionally `outputs/theos2_thumbnail_manifest.csv`

The panel must clearly separate `sentinel1_sar`, `copernicus_dem`, and `theos2_optical`, show `timing_unresolved` for unresolved Sentinel-1 provenance, show DEM as terrain context only, and show THEOS-2 as optical context only. It must not call `fetch`, require a backend, expose absolute local paths, or imply local metadata assets are official flood products.

Dashboard v7 adds a dashboard status narrative. It must include:

- `Read This First`
- `What this dashboard can answer`
- `What remains blocked`
- `Next gate`
- `Real Mae Sai Gate Update`

The narrative must state that the current dashboard is a fixture-backed decision demo, that context layers are not flood labels or agency flood products, that real Mae Sai validation is blocked while provider response items remain pending, and that real-data ML is blocked until legal reference-mask and file-level gates pass.

Dashboard v8 defines the judge-demo command-center layout. It must include:

- `app-header` with `Fixture demo`, `Non-operational`, and `Real validation blocked` status chips
- `kpi-strip` for selected subdistrict, FPPS, action class, confidence, access loss, equity gap, and scenario deltas
- `dashboard-workspace` with `control-panel`, `map-panel`, and `decision-panel`
- `map-panel` as the primary workspace canvas with explicit viewport-safe sizing and embedded action/scenario legends
- `context-readiness-panel` inside the decision panel for SAR, DEM, THEOS-2, and local data readiness summaries
- `report-section` below the first viewport for the embedded validation summary and action brief

The v8 layout must avoid a long overloaded left rail, avoid disconnected legends, call Leaflet `invalidateSize()` after initialization, and preserve all no-backend/no-`fetch` constraints.

Dashboard QA and judge-demo narrative support:

- `scripts/smoke_dashboard.py` must serve `outputs/dashboard.html` through a local static server and report pass/fail for page identity, embedded data, map/rendering landmarks, label overlap guards, validation/action summary visibility, export buttons, strict non-operational wording, and absence of absolute local source paths.
- `docs/dashboard_demo_qa_checklist.md` must document the required judge-demo viewports: `1536x1024`, `2048x1152`, and `1440x900`.
- `docs/dashboard_visual_qa_notes.md` records manual viewport QA notes after a run. It should save notes only, not committed screenshot evidence, unless the project owner explicitly asks for screenshot artifacts.
- `outputs/judge_demo_readme.md` must explain what the fixture demo proves, what it does not prove, why FloodGuard is more than a flood map, and why real validation/ML remain blocked.
- `docs/demo_walkthrough.md` must provide a 3-5 minute path and a 10 minute expanded path that starts with `FG-TB-001 / River Market`, shows A/B/C briefs, toggles temporary-shelter and road-closure scenarios, and ends with the real-data readiness blocker.

Dashboard THEOS-2 optical context uses:

- `outputs/theos2_selected_file_manifest.csv`
- `outputs/theos2_previews/*.svg`
- optionally `outputs/theos2_thumbnail_manifest.csv` and `outputs/theos2_thumbnails/*.png` when rasterio or GDAL is available

These artifacts are optical context only. They must not be described as flood validation, flood reference masks, or official warnings.

Dashboard Sentinel-1 SAR context uses:

- `outputs/sentinel1_quicklook_manifest.csv`
- `outputs/sentinel1_quicklook_vv.png`
- `outputs/sentinel1_quicklook_vh.png`

These artifacts are SAR context only. They must not be described as flood detection, flood validation, reference masks, official warnings, or evidence that event timing is resolved.

Dashboard DEM terrain context uses:

- `outputs/dem_quicklook_manifest.csv`
- `outputs/dem_quicklook.png`

These artifacts are terrain context only. They must not be described as flood observations, flood labels, reference masks, official warnings, or real validation evidence.

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
- `mae_sai_2024_sentinel2`
- `hat_yai_2025_sentinel2`

Live metadata snapshots may be written as:

- `outputs/cdse_mae_sai_2024_metadata.csv`
- `outputs/cdse_hat_yai_2025_metadata.csv`
- `outputs/cdse_mae_sai_2024_sentinel2_metadata.csv`
- `outputs/cdse_hat_yai_2025_sentinel2_metadata.csv`

These files should only be committed after intentional review using `docs/live_metadata_snapshot_review_checklist.md`.

## Public Reference Candidate Manifest

`outputs/public_reference_candidate_manifest.csv` records public/open fallback source candidates while provider responses are pending. It must remain metadata-only and must not download or commit source products.

Required columns:

- `source_name`
- `source_group`
- `study_area`
- `source_url`
- `data_or_product_type`
- `candidate_role`
- `access_route`
- `license_status`
- `geometry_status`
- `redistribution_status`
- `can_use_for_validation`
- `can_use_for_ml_labels`
- `download_action`
- `repo_storage`
- `processing_scope`
- `confidence_class`
- `blocker`
- `next_action`
- `retrieved_at_utc`

Current source groups include:

- `cdse_sentinel1`
- `cdse_sentinel2`
- `cems_rapid_mapping`
- `sentinel_asia_event`
- `sentinel_asia_product`
- `unosat_public_report`
- `nasa_nrt_flood`
- `worldpop_population`
- `osm_geofabrik`
- `copernicus_dem`
- `hdx_cod_ab`
- `theos2_optical`
- `local_sentinel1_sar`
- `local_copernicus_dem`

`outputs/sentinel_asia_public_product_links.csv` uses the same columns and contains only public product-link rows scraped from the Sentinel Asia Northern Thailand 2024 page. The shapefile/GIS ZIP rows are possible geometry candidates only. They must not become validation masks or ML labels until product-level license, geometry, checksum, and processing gates are clear.

## Public Reference File Inspection Manifest

`outputs/public_reference_file_inspection_manifest.csv` records one selected public reference-candidate file after it has been downloaded outside Git. The current selected candidate is the Sentinel Asia / MBRSC Northern Thailand flood shapefile ZIP.

Required columns:

- `source_name`
- `source_group`
- `study_area`
- `source_url`
- `selected_reason`
- `local_path_hint`
- `sha256`
- `file_size_bytes`
- `zip_member_count`
- `zip_members`
- `shapefile_name`
- `shapefile_shape_type`
- `geometry_type`
- `crs`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `mae_sai_point_in_bbox`
- `hat_yai_point_in_bbox`
- `feature_bbox_count`
- `mae_sai_review_bbox`
- `mae_sai_review_bbox_feature_count`
- `dbf_record_count`
- `dbf_fields`
- `flood_water_extent_evidence`
- `flood_water_extent_geometry_assessment`
- `reference_candidate_status`
- `can_use_for_validation`
- `can_use_for_ml_labels`
- `processing_allowed`
- `reason_blocked`
- `next_action`
- `retrieved_at_utc`

The ZIP source file must remain outside Git, normally under an external workspace such as `<external_data_workspace>/sentinel_asia/`. The manifest may record a SHA-256 checksum and redacted path hint, but it must keep `processing_allowed=False` until product-level terms, geometry quality, redistribution/reference-only status, local path, and reference-mask status are cleared.

The current geometry inspection is metadata/header based plus shapefile record-bbox overlap counting. It does not assert that every polygon is flood water, and it does not clear ML-label use.

## CEMS Product Candidate Manifest

`outputs/cems_product_candidate_manifest.csv` records CEMS public API AOI/product metadata for EMSR754 and EMSR756 without downloading product packages.

Required columns:

- `activation_code`
- `activation_name`
- `countries`
- `event_time`
- `activation_time`
- `aoi_number`
- `aoi_name`
- `aoi_bbox_lon_min`
- `aoi_bbox_lat_min`
- `aoi_bbox_lon_max`
- `aoi_bbox_lat_max`
- `mae_sai_point_in_aoi_bbox`
- `hat_yai_point_in_aoi_bbox`
- `product_id`
- `product_name`
- `product_type`
- `monitoring`
- `monitoring_number`
- `version_number`
- `version_status`
- `delivery_time`
- `download_url`
- `product_date`
- `sensor_names`
- `layer_names`
- `observed_event_layer_present`
- `flood_layer_present`
- `candidate_role`
- `mae_sai_reference_relevance`
- `download_performed`
- `processing_allowed`
- `reason_blocked`
- `source_url`
- `retrieved_at_utc`

Current EMSR754 and EMSR756 rows do not cover Mae Sai and are not better Mae Sai reference candidates. Any future CEMS row may become a reference candidate only after AOI/date/product coverage and product terms are verified, with source files stored outside Git.

## Open Context Data File Manifest

`outputs/open_context_data_file_manifest.csv` is a planned file manifest for open context sources that can support exposure, road-risk, terrain review, and aggregation after files are acquired outside Git.

Required columns:

- `source_name`
- `source_group`
- `study_area`
- `source_url`
- `candidate_use`
- `data_type`
- `license_status`
- `local_path`
- `sha256`
- `processing_scope`
- `processing_allowed`
- `reason_blocked`
- `next_action`
- `retrieved_at_utc`

Current rows cover WorldPop Thailand 100m, HDX Thailand COD-AB, OpenStreetMap Thailand via Geofabrik, and Copernicus DEM GLO-30. These are context layers only. They are not flood labels, reference masks, official warnings, or real validation outputs.

## Mae Sai Reference Candidate Decision

`outputs/mae_sai_reference_candidate_decision.md` compares the currently inspected public reference candidates:

- Sentinel Asia / MBRSC public shapefile ZIP
- CEMS EMSR754 and EMSR756 product metadata
- UNOSAT/UN Thailand public report evidence
- NASA coarse flood products

The current decision selects Sentinel Asia / MBRSC as the first practical public reference-candidate lane, not a cleared validation mask and not ML labels. Real non-ML SAR baseline processing remains blocked until file-level and reference-mask gates pass.

## Dashboard v9 Dataset Mode Switch

Dashboard v9 adds a static dataset mode selector:

- `fixture demo`
- `public-data Mae Sai candidate`
- `blocked/metadata-only view`

The selector changes dashboard narrative text only. It does not substitute real data for fixture outputs, and it does not imply that public reference candidates are validated flood products.

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

`scripts/check_real_data_gates.py` provides a no-download reference-mask gate check. It must keep local validation blocked unless provider responses clearly resolve:

- geometry access
- local analysis permission
- derived metrics permission
- screenshots/demo permission
- redistribution or reference-only status
- citation requirement
- blocking decision

ML-label use is a separate gate. It may only be marked allowed when `ml_label_use_allowed=yes`.

`scripts/validate_mae_sai_file_manifest.py` provides a no-download dry-run file-manifest validator. It must explain which reference-mask, pre-event SAR, or post-event SAR row blocks the real Mae Sai non-ML baseline. It may exit successfully in the current blocked state only when run with `--allow-blocked`.

## Local Data Library Manifest

`outputs/local_data_library_manifest.csv` catalogs local hackathon-provided files without copying or processing source assets.

Required columns include:

- `source_name`
- `file_name`
- `local_path_hint`
- `asset_scope`
- `container_name`
- `entry_kind`
- `library_group`
- `candidate_use`
- `file_size_bytes`
- `file_size_gb`
- `zip_member_count`
- `zip_total_uncompressed_bytes`
- `raster_width`
- `raster_height`
- `raster_count`
- `raster_dtypes`
- `band_descriptions`
- `crs`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `mvp_overlap`
- `license_status`
- `sha256_status`
- `processing_allowed`
- `reason_blocked`
- `library_notes`

`outputs/local_data_library_zip_members.csv` catalogs contained ZIP members without extraction.

Required columns include:

- `container_name`
- `member_name`
- `member_path_hint`
- `member_kind`
- `library_group`
- `member_size_bytes`
- `member_size_gb`
- `candidate_use`
- `license_status`
- `sha256_status`
- `processing_allowed`
- `reason_blocked`

All local data library rows must remain `processing_allowed=False` until selected into a stricter file-level manifest with recorded SHA-256 checksums and processing gates.

## Sentinel-1 Selected-File Manifest

`outputs/sentinel1_selected_file_manifest.csv` records the selected local Sentinel-1 file that is ready for provenance and timing review. It must not copy, crop, resample, or process source pixels.

Required columns include:

- `file_name`
- `local_path_hint`
- `sha256`
- `sha256_status`
- `raster_width`
- `raster_height`
- `raster_count`
- `band_descriptions`
- `crs`
- `bbox_lon_min`
- `bbox_lat_min`
- `bbox_lon_max`
- `bbox_lat_max`
- `mvp_overlap`
- `candidate_use`
- `source_license_status`
- `provenance_status`
- `event_timing_status`
- `reference_mask_status`
- `processing_scope`
- `processing_allowed`
- `reason_blocked`

Current selected rows are checksum-backed but remain blocked:

- `sha256_status=recorded`
- `mvp_overlap=mae_sai_2024_point`
- `source_license_status=user_reported_hackathon_free_use`
- `provenance_status=unresolved_placeholder_filename`
- `event_timing_status=unresolved_no_acquisition_date`
- `reference_mask_status=unresolved`
- `processing_scope=sentinel1_sar_context_readiness_only`
- `processing_allowed=False`

The next required step is Sentinel-1 provenance and timing resolution. Processing may not start until product provenance, acquisition timing, and reference-mask status are clear. The source Sentinel-1 TIFF must remain outside Git.

## Sentinel-1 Provenance-Resolved Manifest

`outputs/sentinel1_provenance_resolved_manifest.csv` extends the selected-file manifest with metadata-only provenance evidence. It must not read raster pixels, extract ZIP members, download CDSE assets, or promote unresolved rows into the real SAR baseline.

Required columns include:

- `file_name`
- `sha256`
- `sha256_status`
- `resolved_product_id`
- `source_package`
- `acquisition_datetime`
- `orbit_direction`
- `relative_orbit`
- `platform`
- `product_type`
- `candidate_role`
- `provenance_status`
- `event_timing_status`
- `timing_confidence`
- `provenance_confidence`
- `tiff_tag_summary`
- `filename_evidence`
- `zip_member_evidence`
- `cdse_match_evidence`
- `provider_note_evidence`
- `reference_mask_status`
- `processing_scope`
- `processing_allowed`
- `still_blocked_reason`
- `assumptions`

Allowed `candidate_role` values:

- `pre_event_candidate`
- `post_event_candidate`
- `context_only`
- `unresolved`

Current local finding:

- `resolved_product_id=unresolved`
- `acquisition_datetime=unresolved`
- `candidate_role=unresolved`
- `provenance_status=unresolved_placeholder_filename`
- `event_timing_status=timing_unresolved`
- `timing_confidence=low`
- `provenance_confidence=low`
- `processing_scope=sentinel1_provenance_resolution_only`
- `processing_allowed=False`

The real SAR baseline gate must reject unresolved Sentinel-1 provenance. A row may only become baseline-ready when provenance is confirmed, event timing is confirmed, reference-mask status is confirmed, a resolved product id exists, and the row is classified as `pre_event_candidate` or `post_event_candidate`.

## Sentinel-1 Context Quicklook Manifest

`outputs/sentinel1_quicklook_manifest.csv` records small PNG quicklooks derived from the selected checksum-backed Sentinel-1 TIFF. The quicklook workflow may read source pixels only to create small context previews after `sha256_status=recorded`; it must not copy source TIFFs into Git and must not authorize flood detection, validation, or real baseline processing.

Required columns include:

- `file_name`
- `sha256_prefix`
- `sha256_status`
- `mvp_overlap`
- `event_timing_status`
- `provenance_status`
- `band`
- `band_description`
- `quicklook_path`
- `quicklook_format`
- `quicklook_width`
- `quicklook_height`
- `quicklook_file_size_bytes`
- `raster_reader`
- `processing_scope`
- `warning_text`
- `assumptions`

Current quicklook rows must remain:

- `sha256_status=recorded`
- `mvp_overlap=mae_sai_2024_point`
- `event_timing_status=timing_unresolved`
- `provenance_status=unresolved_placeholder_filename`
- `band=VV` or `band=VH`
- `quicklook_format=png`
- `processing_scope=sentinel1_sar_context_quicklook_only`
- `warning_text=SAR context only; not flood detection; not validation; not an official warning; event timing unresolved unless proven otherwise.`

The PNG quicklooks should be small dashboard artifacts, currently `outputs/sentinel1_quicklook_vv.png` and `outputs/sentinel1_quicklook_vh.png`. Source Sentinel-1 TIFF files remain outside Git.

## DEM Selected-File Manifest

`outputs/dem_selected_file_manifest.csv` records selected local Copernicus DEM/elevation-slope ZIP packages and their contained DEM TIFF member names without extracting source data.

Required columns include:

- `source_name`
- `package_name`
- `member_name`
- `local_package_path_hint`
- `member_path_hint`
- `package_sha256`
- `package_sha256_status`
- `package_file_size_bytes`
- `package_file_size_gb`
- `zip_member_count`
- `member_size_bytes`
- `member_size_gb`
- `member_kind`
- `checksum_strategy`
- `candidate_use`
- `source_license_status`
- `reference_mask_status`
- `flood_observation_status`
- `flood_label_status`
- `processing_scope`
- `processing_status`
- `processing_allowed`
- `reason_blocked`
- `assumptions`

Current DEM rows must remain:

- `package_sha256_status=recorded`
- `checksum_strategy=package-level checksum recorded first`
- `candidate_use=terrain/slope context for false-positive review and exposure explanation`
- `reference_mask_status=not_reference_mask`
- `flood_observation_status=not_flood_observation`
- `flood_label_status=not_flood_label`
- `processing_scope=dem_terrain_context_readiness_only`
- `processing_status=blocked_until_member_extraction_and_scope_review`
- `processing_allowed=False`

DEM packages are terrain context only. They must not be used as flood observations, flood reference masks, or ML labels. The `member-level checksum` values may only be recorded later if members are extracted into a controlled local data workspace outside Git.

## DEM Context Quicklook Manifest

`outputs/dem_quicklook_manifest.csv` records a small PNG terrain preview from a selected DEM TIFF member. Generation is allowed only after the selected DEM package has `package_sha256_status=recorded`, the DEM member is extracted to a local workspace outside Git, and a member-level SHA-256 checksum is supplied and verified.

Required columns include:

- `source_name`
- `package_name`
- `member_name`
- `package_sha256_prefix`
- `package_sha256_status`
- `member_sha256_prefix`
- `member_sha256_status`
- `local_extracted_path_hint`
- `quicklook_path`
- `quicklook_format`
- `quicklook_width`
- `quicklook_height`
- `quicklook_file_size_bytes`
- `raster_reader`
- `reference_mask_status`
- `flood_observation_status`
- `flood_label_status`
- `processing_scope`
- `warning_text`
- `assumptions`

Current DEM quicklook rows must remain:

- `package_sha256_status=recorded`
- `member_sha256_status=recorded`
- `local_extracted_path_hint=<external_data_workspace>/...`
- `quicklook_path=dem_quicklook.png`
- `quicklook_format=png`
- `reference_mask_status=not_reference_mask`
- `flood_observation_status=not_flood_observation`
- `flood_label_status=not_flood_label`
- `processing_scope=dem_terrain_context_quicklook_only`
- `warning_text=DEM terrain context only; not flood observation; not flood label; not reference mask; not an official warning.`

The extracted DEM TIFF must remain outside Git. The committed PNG is a small dashboard artifact and must not be treated as a source DEM product.

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

`docs/provider_response_logging_guide.md` defines exactly how to log UNOSAT/UNITAR and GISTDA replies. `docs/mae_sai_file_manifest_v2.md` defines the required file-level rows before real non-ML SAR processing.

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

`outputs/theos2_thumbnail_manifest.csv` and `outputs/theos2_thumbnails/*.png` are optional true-thumbnail artifacts. They may be generated only when:

- `outputs/theos2_selected_file_manifest.csv` has recorded checksums
- `processing_scope=theos2_optical_context_preview_only`
- `reference_mask_status=not_reference_mask`
- an optional raster reader, either rasterio or GDAL, is available

True thumbnails must be small PNG outputs and must not be full-resolution imagery or map tiles.

`outputs/theos2_visual_review_checklist.csv` is a pending manual-review worksheet for selected THEOS-2 previews or thumbnails.

Required columns include:

- `file_name`
- `source_timestamp`
- `category`
- `preview_path`
- `preview_source`
- `visible_water_context`
- `built_up_area_context`
- `road_context`
- `cloud_haze_status`
- `exposure_explanation_usefulness`
- `review_status`
- `reviewer`
- `review_date`
- `review_notes`
- `flood_label_claim`
- `assumptions`

Default values should remain `not_reviewed` or blank until a human reviewer fills them. `flood_label_claim` must remain `not_allowed`; the checklist is optical context only and must not become a flood-label or validation-mask source.

## THEOS-2 Land-Cover/Exposure Feature Prototype

`outputs/theos2_landcover_exposure_features.csv` is a tiny non-ML feature table derived from selected THEOS-2 metadata and preview context.

Required columns include:

- `file_name`
- `source_timestamp`
- `category`
- `has_disaster_context`
- `has_lulc_context`
- `has_urban_context`
- `has_agri_context`
- `has_coastal_context`
- `rough_bbox_area_sq_km`
- `mvp_overlap`
- `built_up_exposure_note`
- `water_context_note`
- `floodguard_use`
- `confidence_class`
- `assumptions`

These are not flood labels and must not be used as real-data ML targets.

## GeoJSON Fixtures

GeoJSON fixtures should use WGS84 coordinates (`EPSG:4326`) and small synthetic geometries unless source licensing is explicitly documented.
