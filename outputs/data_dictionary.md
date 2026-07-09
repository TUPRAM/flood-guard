# FloodGuard Output Data Dictionary

This dictionary describes the fixture-backed outputs in `outputs/`. The current outputs are non-operational demo artifacts, not official warnings or real-time flood products.

## Priority Scores

File: `sample_priority_scores.csv`

| Field | Meaning |
| --- | --- |
| `subdistrict_id` | Stable synthetic subdistrict identifier used for joins and dashboard selection. |
| `subdistrict_name` | Human-readable synthetic subdistrict name. |
| `fpps_0_100` | Flood Preparedness Priority Score, normalized from 0 to 100. |
| `action_class` | A-E action category, where A is highest life-safety priority and E is monitor/verify. |
| `top_reason` | Short explanation for the assigned score or class. |
| `confidence_class` | `high`, `medium`, or `low` confidence label. |
| `source_name` | Fixture/source label used to produce the row. |
| `source_timestamp` | Timestamp associated with the source row. |
| `assumptions` | Plain-language caveat for the fixture row. |

## Road Risk

File: `sample_road_risk.csv`

| Field | Meaning |
| --- | --- |
| `road_id` | Stable synthetic road segment identifier. |
| `subdistrict_id` | Subdistrict associated with the road segment. |
| `road_disruption_probability_0_1` | Heuristic disruption probability from 0 to 1. |
| `confidence_class` | Confidence label inherited from flood-probability context. |
| `top_risk_reason` | Short explanation for the highest road-risk driver. |
| `source_name` | Fixture/source label. |
| `source_timestamp` | Timestamp associated with the source row. |
| `assumptions` | Caveat that risk is heuristic and not an observed closure. |

## Access Loss

File: `sample_access_loss.csv`

| Field | Meaning |
| --- | --- |
| `subdistrict_id` | Stable synthetic subdistrict identifier. |
| `subdistrict_name` | Human-readable synthetic subdistrict name. |
| `total_population` | Synthetic total population represented by access nodes. |
| `total_vulnerable_population` | Synthetic vulnerable population represented by access nodes. |
| `total_non_vulnerable_population` | Synthetic non-vulnerable population represented by access nodes. |
| `people_losing_15_min_access` | People with normal 15-minute access who lose that access under disruption. |
| `people_losing_30_min_access` | People with normal 30-minute access who lose that access under disruption. |
| `people_losing_60_min_access` | People with normal 60-minute access who lose that access under disruption. |
| `vulnerable_population_losing_<threshold>_min_access` | Vulnerable people losing access at the stated threshold. |
| `non_vulnerable_population_losing_<threshold>_min_access` | Non-vulnerable people losing access at the stated threshold. |

## Equity Gap

File: `sample_equity_gap.csv`

| Field | Meaning |
| --- | --- |
| `subdistrict_id` | Stable synthetic subdistrict identifier. |
| `subdistrict_name` | Human-readable synthetic subdistrict name. |
| `total_vulnerable_population` | Vulnerable denominator used for access-loss rate. |
| `vulnerable_population_losing_access` | Vulnerable population losing access at the selected threshold. |
| `total_non_vulnerable_population` | Non-vulnerable denominator used for access-loss rate. |
| `non_vulnerable_population_losing_access` | Non-vulnerable population losing access at the selected threshold. |
| `confidence_class` | Confidence label for the equity calculation. |
| `vulnerable_access_loss_rate` | Vulnerable access-loss rate. |
| `non_vulnerable_access_loss_rate` | Non-vulnerable access-loss rate. |
| `equity_gap_ratio` | Vulnerable rate divided by non-vulnerable rate, with explicit null handling. |
| `interpretation_text` | Human-readable equity interpretation. |

## Scenario Outputs

Files: `sample_scenario_<scenario>_access_loss.csv`, `sample_scenario_<scenario>_equity_gap.csv`, and `sample_scenario_summary.csv`

| Field | Meaning |
| --- | --- |
| `scenario_name` | Scenario toggle, such as `add_temporary_shelter` or `close_road`. |
| `baseline_people_losing_30_min_access` | Baseline people losing 30-minute access before the scenario. |
| `scenario_people_losing_30_min_access` | People losing 30-minute access after the scenario. |
| `change_people_losing_30_min_access` | Scenario minus baseline 30-minute access-loss count. Negative improves access; positive worsens access. |
| `baseline_max_equity_gap_ratio` | Maximum numeric baseline equity-gap ratio. |
| `scenario_max_equity_gap_ratio` | Maximum numeric scenario equity-gap ratio. |
| `change_max_equity_gap_ratio` | Scenario minus baseline max equity-gap ratio. |

## GeoJSON Dashboard Exports

Files: `priority_subdistricts.geojson` and `road_risk.geojson`

| Field | Meaning |
| --- | --- |
| `geometry` | WGS84 fixture polygon or line geometry. |
| `baseline_people_losing_30_min_access` | Baseline 30-minute access-loss count joined into priority polygons. |
| `baseline_equity_gap_ratio` | Baseline equity-gap ratio joined into priority polygons. |
| `temporary_shelter_people_losing_30_min_access` | Scenario access-loss count after adding the temporary shelter. |
| `temporary_shelter_change_people_losing_30_min_access` | Temporary shelter scenario minus baseline. Negative means improvement. |
| `temporary_shelter_equity_gap_ratio` | Equity-gap ratio after adding the temporary shelter. |
| `temporary_shelter_change_equity_gap_ratio` | Temporary shelter equity ratio minus baseline ratio. |
| `road_closure_people_losing_30_min_access` | Scenario access-loss count after closing the selected road edge. |
| `road_closure_change_people_losing_30_min_access` | Road closure scenario minus baseline. Positive means worsening. |
| `road_closure_equity_gap_ratio` | Equity-gap ratio after the road closure stress case. |
| `road_closure_change_equity_gap_ratio` | Road closure equity ratio minus baseline ratio. |

## Dashboard And Briefs

| Artifact | Meaning |
| --- | --- |
| `dashboard.html` | Standalone Leaflet dashboard with embedded GeoJSON, action briefs, validation summary, controls, scenario cards, Sentinel-1 SAR context cards, THEOS-2 optical cards, and Local Data Library readiness panel. |
| `judge_demo_readme.md` | Judge-facing narrative pack explaining what the fixture demo proves, what it does not prove, and why real validation/ML gates remain blocked. |
| `action_brief_FG-TB-001.md` | Compact A-class action brief for River Market. |
| `action_brief_FG-TB-002.md` | Compact B-class action brief for Bridge Junction. |
| `action_brief_FG-TB-003.md` | Compact C-class action brief for Clinic Basin. |
| `validation_summary.md` | Fixture coverage, priority, road-risk, access, equity, and sensitivity summary. |

Dashboard v4 browser-only exports:

| Control | Meaning |
| --- | --- |
| Download current brief | Downloads the currently selected embedded action brief as Markdown. |
| Download filtered GeoJSON | Downloads a GeoJSON FeatureCollection containing priority polygons that match the active A-E filters. |

Dashboard THEOS-2 optical context:

| Artifact | Meaning |
| --- | --- |
| `theos2_selected_file_manifest.csv` | Checksum-backed selected-file manifest for local THEOS-2 optical context candidates. |
| `theos2_previews/*.svg` | Small non-operational optical-context preview cards generated from metadata and checksums, not source image pixels. |
| `theos2_thumbnail_manifest.csv` | Optional true-thumbnail manifest written only when rasterio or GDAL is available. |
| `theos2_thumbnails/*.png` | Optional small PNG thumbnails; never full-resolution imagery. |
| `theos2_landcover_exposure_features.csv` | Non-ML metadata-derived optical context feature table. |
| `theos2_visual_review_checklist.csv` | Pending manual-review worksheet for interpreting optical context without creating flood labels. |

Dashboard v5 THEOS-2 cards prefer `theos2_thumbnails/*.png` when a true thumbnail manifest exists, and fall back to `theos2_previews/*.svg` otherwise.

Dashboard Sentinel-1 SAR context:

| Artifact | Meaning |
| --- | --- |
| `sentinel1_quicklook_manifest.csv` | Manifest for small checksum-gated SAR context quicklooks. |
| `sentinel1_quicklook_vv.png` | Small VV-band SAR context PNG; not flood detection or validation. |
| `sentinel1_quicklook_vh.png` | Small VH-band SAR context PNG; not flood detection or validation. |
| `sentinel1_sar_context_quicklook_only` | Processing scope for quicklook previews only. |
| `event timing unresolved unless proven otherwise` | Required warning because local Sentinel-1 provenance is not solved. |

Dashboard DEM terrain context:

| Artifact | Meaning |
| --- | --- |
| `dem_quicklook_manifest.csv` | Manifest for a small extracted-member DEM terrain quicklook. |
| `dem_quicklook.png` | Small DEM terrain context PNG; not flood observation or validation. |
| `dem_terrain_context_quicklook_only` | Processing scope for DEM quicklook previews only. |
| `not_flood_observation` | DEM is terrain context, not observed flood water. |
| `not_flood_label` | DEM must not be used as an ML label or target. |
| `not_reference_mask` | DEM must not be used as the legal flood reference mask. |

Dashboard v6 Local Data Library panel:

| Item | Meaning |
| --- | --- |
| `sentinel1_sar` | Count of local Sentinel-1 library assets and selected Sentinel-1 readiness/provenance status. |
| `copernicus_dem` | Count of local DEM package assets and selected DEM terrain-context readiness status. |
| `theos2_optical` | Count of local THEOS-2 optical assets and selected optical-context readiness status. |
| `timing_unresolved` | Sentinel-1 provenance status showing local timing is not ready for real baseline use. |
| `terrain context only` | DEM use boundary; not flood observation, not label, and not reference mask. |
| `optical context only` | THEOS-2 use boundary; not flood validation and not an official warning. |

Dashboard v7 narrative panel:

| Item | Meaning |
| --- | --- |
| `Read This First` | Top-of-dashboard status narrative for judges and operators. |
| `What this dashboard can answer` | Fixture-backed questions the current demo can answer: highest actionable sample priority, scenario access-loss change, and local context asset readiness. |
| `What remains blocked` | Real validation blockers: provider response pending, context layers are not flood labels, and real-data ML is not allowed until legal/file gates pass. |
| `Next gate` | Real Mae Sai Gate Update checklist for geometry access, local validation permission, derived metrics, screenshots/demo, redistribution/reference-only terms, ML-label use, citation, and disclaimers. |
| `Real Mae Sai Gate Update` | The required legal and file-level transition before real flood validation can replace fixture-only reporting. |

Dashboard v8 Judge Demo Layout:

| Item | Meaning |
| --- | --- |
| `app-header` | Top command-center header with product name, fixture/non-operational status, and blocked real-validation state. |
| `kpi-strip` | Compact first-viewport KPI row for selected subdistrict, FPPS, action class, confidence, access loss, equity gap, and scenario deltas. |
| `dashboard-workspace` | Three-zone first-viewport workspace containing controls, the primary map canvas, and decision/context panels. |
| `map-panel` | Main Leaflet map region with embedded action-class, scenario-delta, and road-risk legends. |
| `decision-panel` | Right-side decision area for action brief summary, context assets, and data readiness. |
| `context-readiness-panel` | Compact SAR, DEM, THEOS-2, and Local Data Library readiness summary area; context only, not validation. |
| `report-section` | Below-workspace Markdown report area for validation summary and full action brief content. |

Dashboard v9 dataset mode switch:

| Item | Meaning |
| --- | --- |
| `dataset-mode-select` | Static control that lets the viewer choose `fixture demo`, `Mae Sai weak-reference candidate`, or `Metadata/blocker view` narrative mode. |
| `dataset-mode-note` | Plain-language note explaining whether the viewer is seeing fixture outputs, the Mae Sai weak-reference real-data candidate path, or blocked metadata-only readiness. |
| `fixture demo` | Current dashboard mode using synthetic fixture priority, access, equity, and road-risk outputs. |
| `Mae Sai weak-reference candidate` | Narrative mode showing downloaded outside-Git CDSE Sentinel-1 pre/post product ids, manual QGIS weak-reference status, candidate IoU/F1/Dice/precision/recall/area-error metrics, flood-probability summary, and generated weak-reference decision output when available. |
| `Metadata/blocker view` | Narrative mode emphasizing that source candidates and local file manifests alone do not authorize official validation or ML. |
| `mae-sai-weak-reference-card` | Compact status card embedded in the dashboard narrative. It must keep weak-reference wording visible and must not call the output official validation. |
| `pre_product_id` / `post_product_id` | CDSE Sentinel-1 products used by the weak-reference candidate summary; source ZIPs remain outside Git. |
| `manual_reference_status` | Manual QGIS mask status, currently `weak_reference_candidate`. |
| `candidate_readiness_status` | Whether the manual weak-reference mask is ready for candidate metrics; this does not clear official validation gates. |
| `not_official_status` | Required status confirming the manual reference is not official. |

Dashboard QA support:

| Artifact | Meaning |
| --- | --- |
| `docs/dashboard_demo_qa_checklist.md` | Manual and command-line QA checklist for judge demo sizes `1536x1024`, `2048x1152`, and `1440x900`. |
| `scripts/smoke_dashboard.py` | Dependency-light smoke check that serves `outputs/dashboard.html` locally and verifies page identity, embedded data, map/rendering landmarks, label guards, export buttons, strict wording, and absence of source paths. |
| `docs/demo_walkthrough.md` | Three-to-five-minute and ten-minute walkthrough for presenting the fixture-backed dashboard honestly. |

## Metadata Planning Outputs

Files: `real_data_ingestion_manifest.csv`, `mae_sai_real_data_file_manifest.csv`, `local_data_library_manifest.csv`, `local_data_library_zip_members.csv`, `public_reference_candidate_manifest.csv`, `sentinel_asia_public_product_links.csv`, `public_reference_file_inspection_manifest.csv`, `sentinel_asia_geometry_quality_review.csv`, `sentinel_asia_mbrsc_visual_qa_review.csv`, `sentinel_asia_product_terms_review.csv`, `docs/mbrsc_reference_mask_clearance_memo.md`, `manual_reference_mask_manifest.csv`, `cems_product_candidate_manifest.csv`, `mae_sai_reference_candidate_decision.md`, `open_context_data_file_manifest.csv`, `cdse_mae_sai_acquisition_manifest.csv`, and `cdse_*_metadata.csv`

`sentinel_asia_geometry_quality_review.csv` is the QGIS/GDAL review of the selected outside-Git MBRSC shapefile ZIP. Current values show WGS84 polygon geometry, `6506` full-layer features, `514` features intersecting the Mae Sai review bbox, `464.234` km2 full-layer area-field sum, and `47.164` km2 inside the Mae Sai review bbox. This is geometry quality evidence only; it does not clear validation metrics, screenshots/demo, derived metrics, redistribution, or ML-label use.

`sentinel_asia_mbrsc_visual_qa_review.csv` is the notes-only visual QA result. It says the MBRSC polygons are not a single broad event boundary; they concentrate east/southeast of the Mae Sai point and broadly align with floodplain/waterway context, while still containing fragmented patches that require manual QA. Current `validation_status` is `reference_candidate_only_not_validation_truth`.

`sentinel_asia_product_terms_review.csv` records the conservative product-terms decision. Current status is `reference_candidate_only` because no explicit product-level terms were found for validation metrics, screenshots/demo, derived metrics, redistribution, or ML-label use. `docs/mbrsc_reference_mask_clearance_memo.md` is the controlling decision memo and says not to set `processing_allowed=True` or `blocking_decision=cleared_for_local_validation`.

`cdse_mae_sai_acquisition_manifest.csv` records selected Mae Sai Sentinel-1 CDSE acquisition rows. Current rows are `downloaded_outside_git` with `sha256_status=recorded` for the selected pre/post COG products. Source assets remain outside Git; processing remains blocked until reference-mask status clears.

`manual_reference_mask_manifest.csv` records a project-owned QGIS manual weak-reference candidate. It can support candidate validation metrics only after the GeoPackage exists outside Git, has a SHA-256 checksum, contains required fields, contains features, and every feature has `not_official=true`. It must not be described as official validation truth, an official warning, redistributed provider source data, or unqualified ML labels.

| Field | Meaning |
| --- | --- |
| `acquisition_date` | CDSE product acquisition timestamp. |
| `product_name` | CDSE product name. |
| `cdse_product_id` | CDSE product UUID. |
| `online_status` | CDSE metadata online flag at query time. |
| `mission_platform_prefix` | Product prefix such as `S1A` or `S1C`. |
| `product_storage_type` | `COG`, `SAFE`, or `unknown` based on product name. |
| `candidate_role` | Planning role such as pre-event, post-event, or event-window candidate. |
| `query_profile` | Query profile, such as `mae_sai_2024` or `hat_yai_2025`. |
| `source_url` | CDSE OData query URL used for metadata. |
| `blocker_note` | Licensing, geometry, or no-download blocker note. |
| `download_url` | CDSE product `$value` endpoint or public product URL when exposed; source products must still stay outside Git. |
| `download_attempted` | Whether the CDSE acquisition helper attempted an asset download. Current selected CDSE rows are `True`, with assets stored outside Git. |
| `download_status` | CDSE acquisition state such as `blocked_missing_cdse_credentials`, `dry_run_no_download`, or `downloaded_outside_git`. |
| `sha256_status` | Whether a selected outside-Git file checksum is recorded. |
| `file_size_bytes` | Size of the downloaded outside-Git product when available. |
| `source_group` | Public/open source family, such as `cdse_sentinel1`, `cems_rapid_mapping`, `sentinel_asia_product`, `worldpop_population`, or `osm_geofabrik`. |
| `data_or_product_type` | Public inventory type, such as open SAR imagery, rapid mapping activation, shapefile ZIP candidate, report page, or population raster. |
| `access_route` | How the data can be accessed, such as CDSE metadata query, public event page, Earthdata registration, or external local workspace. |
| `geometry_status` | Whether machine-readable geometry exists, is unresolved, or requires external inspection. |
| `can_use_for_validation` | Conservative validation status. Values may be possible only after product coverage, geometry, license, and file gates are checked. |
| `can_use_for_ml_labels` | Conservative ML-label status. Current public candidates are not cleared as ML labels by default. |
| `download_action` | What action is allowed next. Current rows permit metadata capture and external review, not product downloads into Git. |
| `repo_storage` | Repository storage rule. Public inventory rows are metadata CSV only and must not commit source products. |
| `selected_reason` | Why one public reference-candidate file was selected for external inspection. |
| `local_path_hint` | Redacted external-workspace location for a file that must remain outside Git. |
| `zip_member_count` | Number of files inside an inspected ZIP package. |
| `zip_members` | Pipe-delimited list of inspected ZIP members. |
| `shapefile_name` | `.shp` member selected inside the inspected reference-candidate ZIP. |
| `shapefile_shape_type` | Numeric ESRI Shapefile shape type from the `.shp` header. |
| `geometry_type` | Human-readable geometry type such as `Polygon`. |
| `crs` | Coordinate reference system summary from `.prj`, currently `GCS_WGS_1984` for the inspected Sentinel Asia candidate. |
| `bbox_lon_min` / `bbox_lat_min` / `bbox_lon_max` / `bbox_lat_max` | Overall shapefile bounding box from the `.shp` header. |
| `mae_sai_point_in_bbox` | Whether the Mae Sai point falls inside the overall shapefile bbox. |
| `hat_yai_point_in_bbox` | Whether the Hat Yai point falls inside the overall shapefile bbox. |
| `feature_bbox_count` | Number of polygon/polyline record bounding boxes parsed from the shapefile records. |
| `mae_sai_review_bbox` | Small review bbox used for approximate Mae Sai geometry-overlap screening. |
| `mae_sai_review_bbox_feature_count` | Number of parsed record bboxes that overlap the Mae Sai review bbox. |
| `dbf_record_count` | Number of rows reported by the shapefile `.dbf` header. |
| `dbf_fields` | Pipe-delimited DBF field summary, for example `Id:N10|gridcode:N10|Area:F13`. |
| `flood_water_extent_evidence` | Header/member-name evidence that the candidate likely contains flood-water geometry. |
| `flood_water_extent_geometry_assessment` | Conservative geometry assessment; still requires product-term and quality review before validation. |
| `reference_candidate_status` | Candidate status such as `candidate_geometry_intersects_mae_sai_bbox`. |
| `qgis_tool` | Review tool family used for geometry QA, currently QGIS/GDAL `ogrinfo` without exposing the absolute executable path. |
| `qgis_gdal_version` | GDAL/QGIS runtime version used to inspect the shapefile. |
| `area_field_sum_km2` | Full-layer sum of the shapefile `Area` attribute converted from square meters to square kilometers. |
| `mae_sai_review_feature_count` | QGIS/GDAL count of features intersecting the Mae Sai review bbox. |
| `mae_sai_review_bbox_area_sum_km2` | Sum of the shapefile `Area` attribute for features intersecting the Mae Sai review bbox. |
| `gridcode_values` | Distinct gridcode values reported by QGIS/GDAL; current inspected layer uses `1`. |
| `geometry_quality_status` | Conservative spatial QA status; current status is useful reference-candidate geometry, not validation truth. |
| `validation_use_status` | Whether the geometry may be used for validation; current status remains terms and quality review required. |
| `ml_label_use_status` | Whether the geometry may be used as ML labels; current status is not cleared for ML labels. |
| `terms_found` | Whether explicit product-level terms were found for the inspected Sentinel Asia product. |
| `Thailand_flood.shp.xml` | Embedded MBRSC shapefile metadata reviewed for license/use constraints; current finding is technical lineage only, not legal clearance. |
| `mae_sai_point_intersects_polygon` | Visual QA result for whether the exact Mae Sai point falls inside a candidate flood polygon. Current result is `no`. |
| `mae_sai_core_feature_count` | Visual QA count for features in the small Mae Sai core bbox. |
| `east_southeast_floodplain_feature_count` | Visual QA count for features in the east/southeast floodplain bbox where most candidate geometry appears. |
| `visual_alignment_assessment` | Human-readable visual QA interpretation of floodplain/waterway alignment. |
| `broad_event_noise_assessment` | Human-readable note on whether the layer looks like a broad event boundary or fragmented flood/noise patches. |
| `validation_metrics_allowed` | Product-terms status for computing local validation metrics; current status is unresolved. |
| `screenshots_demo_allowed` | Product-terms status for screenshots/demo use; current status is unresolved. |
| `derived_metrics_allowed` | Product-terms status for derived metrics such as IoU and area statistics; current status is unresolved. |
| `ml_label_use_allowed` | Product-terms status for weak-label or ML-label use; current status is blocked or unresolved unless explicitly cleared. |
| `activation_code` | CEMS activation code such as `EMSR754` or `EMSR756`. |
| `activation_name` | CEMS activation name returned by the public API. |
| `countries` | Pipe-delimited CEMS activation country list. |
| `aoi_number` / `aoi_name` | CEMS area-of-interest identifier and name. |
| `mae_sai_point_in_aoi_bbox` | Whether the CEMS AOI bbox contains the Mae Sai point. |
| `hat_yai_point_in_aoi_bbox` | Whether the CEMS AOI bbox contains the Hat Yai point. |
| `download_url` | Public product package URL exposed by the CEMS API when available; no package is downloaded into Git. |
| `observed_event_layer_present` | Whether a CEMS product row includes an observed-event layer. |
| `flood_layer_present` | Whether a CEMS product row includes a flood-related layer name. |
| `mae_sai_reference_relevance` | CEMS relevance flag; current EMSR754/EMSR756 rows are not Mae Sai candidates. |
| `download_performed` | Must remain `False` for CEMS/public product resolver rows committed to the repo. |
| `data_type` | Planned context-source type such as `population_raster`, `admin_boundary_vector`, `osm_pbf_or_shapefile_extract`, or `dem_raster`. |
| `product_id` | File-level source or reference-mask product id once selected. |
| `local_path` | Local path for legally acquired source data, stored outside Git. |
| `sha256` | SHA-256 checksum for the locally tracked file or source package. |
| `source_license_status` | File-level license status used by the processing gate. |
| `reference_mask_status` | Reference-mask readiness status used by the processing gate. |
| `ingestion_stage` | `metadata_only` for blocked rows; `file_ready_metadata` only after file-level gates pass. |
| `download_permitted_by_skeleton` | Always `False`; the skeleton does not permit downloads. |
| `ready_for_processing` | Mirrors the file-level processing gate. Current generated rows remain `False`. |
| `processing_allowed` | `True` only when source license, reference mask, local path, product id, and checksum gates all pass. |
| `blocked_reason` | Human-readable reason the row is not processing-ready. |
| `reason_blocked` | File-level blocker text mirroring `blocked_reason` for downstream tools. |

Manual weak-reference fields:

| Field | Meaning |
| --- | --- |
| `manual_reference_mask_manifest.csv` | Output from `scripts/inspect_manual_reference_mask.py`. |
| `manual_qgis_weak_reference` | Source type for a project-owned manual QGIS weak-reference mask. |
| `weak_reference_candidate` | Reference-mask status for manual candidate geometry; not official validation truth. |
| `candidate_readiness_status` | Whether the manual GeoPackage is missing, incomplete, or ready for candidate metrics. |
| `candidate_validation_metrics_allowed` | `True` only for complete manual masks; permits candidate metrics, not official validation claims. |
| `not_official_status` | Must be `confirmed_true` before the manual lane can support candidate metrics. |
| `official_validation_truth_allowed` | Must remain `False` for the manual lane. |
| `unqualified_ml_label_allowed` | Must remain `False` for the manual lane. |

Reference-mask legal gate fields used by `scripts/check_real_data_gates.py`:

| Field | Meaning |
| --- | --- |
| `request_status` | Provider outreach state, such as `sent_waiting_response` or `response_received`. |
| `request_sent_date` | Date the provider request was sent, or `not_sent`. |
| `response_date` | Provider response date, or `no_response`. |
| `geometry_access` | Whether usable vector/raster mask geometry access is confirmed. |
| `local_analysis_allowed` | Whether local validation analysis is explicitly allowed. |
| `derived_metrics_allowed` | Whether derived metrics such as IoU, F1/Dice, precision, recall, and area error may be reported. |
| `screenshots_demo_allowed` | Whether screenshots or demo use of derived outputs is allowed. |
| `redistribution_allowed` | Whether source geometry is redistributable, reference-only, or unresolved. |
| `citation_required` | Provider citation/attribution requirement once resolved. |
| `ml_label_use_allowed` | Whether the reference mask may be used as ML labels; this must be explicit before ML starts. |
| `blocking_decision` | Final provider/legal decision. It must be cleared before real validation can start. |
| `reference_validation_allowed` | Computed gate result for local validation. |
| `ml_label_allowed` | Computed gate result for ML-label use, separate from validation. |

`mae_sai_real_data_file_manifest.csv` is a blocked planning manifest for the first real non-ML SAR baseline. After the public reference inspection lane runs, it includes the Sentinel Asia MBRSC shapefile as a checksummed public reference-candidate row, plus the selected September 6 pre-event Sentinel-1 COG, the selected September 15 post-event Sentinel-1 COG, and the September 18 fallback post-event COG. The reference candidate has geometry and checksum metadata but unresolved product terms and quality gates, so all rows remain `processing_allowed=False`.

`public_reference_candidate_manifest.csv` is the public/open fallback source inventory. It includes CDSE Sentinel-1/Sentinel-2, CEMS EMSR754/EMSR756, Sentinel Asia public product links, UNOSAT/UN Thailand report evidence, NASA flood products, WorldPop, OSM/Geofabrik, Copernicus DEM, HDX COD-AB, and local hackathon lanes. It is metadata-only and does not make any source a legal flood label by itself.

`sentinel_asia_public_product_links.csv` records public Sentinel Asia Northern Thailand 2024 product URLs. Current generated rows include JPG map/quicklook links, GIS ZIP candidates, and one shapefile ZIP candidate. These are not automatically validation masks or ML labels.

`public_reference_file_inspection_manifest.csv` records the selected Sentinel Asia / MBRSC shapefile ZIP inspection. It stores SHA-256, ZIP members, CRS, geometry type, bbox, DBF fields, feature-bbox counts, and Mae Sai overlap screening. It is a reference candidate only.

`cems_product_candidate_manifest.csv` records CEMS EMSR754/EMSR756 AOI and product metadata from the public backend API. Current rows do not provide a Mae Sai reference candidate.

`mae_sai_reference_candidate_decision.md` documents the current comparison across Sentinel Asia, CEMS, UNOSAT report evidence, and NASA coarse flood products. The current decision is to pursue Sentinel Asia / MBRSC as the first public reference-candidate lane while keeping real validation blocked.

`open_context_data_file_manifest.csv` records planned rows for WorldPop Thailand 100m, HDX COD-AB, Geofabrik OSM, and Copernicus DEM GLO-30. These are context sources for exposure, aggregation, roads, and terrain, not flood labels.

`cdse_mae_sai_2024_metadata.csv` and `cdse_hat_yai_2025_metadata.csv` are Sentinel-1 no-download CDSE product metadata snapshots. `cdse_mae_sai_2024_sentinel2_metadata.csv` and `cdse_hat_yai_2025_sentinel2_metadata.csv` are Sentinel-2 L2A optical-context metadata snapshots.

`local_data_library_manifest.csv` catalogs every currently provided local hackathon file listed for the project. It includes top-level Google Drive ZIP bundles, the standalone Sentinel-1 TIFF, standalone THEOS-2 TIFF/OVR files, and THEOS-2 sample ZIP packages.

`local_data_library_zip_members.csv` catalogs ZIP members without extracting or committing them. The current catalog includes Sentinel-1 tile TIFF members, Copernicus DEM/elevation-slope TIFF members, THEOS-2 package members, and one screenshot/documentation PNG.

Local data library fields:

| Field | Meaning |
| --- | --- |
| `asset_scope` | `local_file` for top-level files; ZIP members are recorded in the separate member catalog. |
| `entry_kind` | File kind such as `image_tiff`, `overview`, `zip_package`, or `png_image`. |
| `library_group` | Triage group such as `sentinel1_sar`, `copernicus_dem`, `theos2_optical`, or `documentation_image`. |
| `candidate_use` | Conservative use note for the asset, such as SAR context, DEM context, or optical context. |
| `zip_member_count` | Number of contained files for a top-level ZIP package. |
| `zip_total_uncompressed_bytes` | Sum of uncompressed member sizes for a ZIP package. |
| `raster_width` / `raster_height` | Raster dimensions from header metadata, when available. |
| `raster_count` | Number of raster bands from header metadata, when available. |
| `raster_dtypes` | Raster data types from header metadata, when available. |
| `band_descriptions` | Band descriptions such as `VV|VH` for the standalone Sentinel-1 TIFF. |
| `crs` | CRS string from raster metadata, when available. |
| `mvp_overlap` | Whether the cataloged bbox covers current MVP points such as `mae_sai_2024_point`. |
| `library_notes` | Human-readable triage note and caution. |
| `member_name` | Name of a file inside a ZIP package. |
| `member_path_hint` | Redacted ZIP member path such as `<input_dir>/package.zip::member.tif`. |
| `member_kind` | File kind for a ZIP member. |

## Sentinel-1 Selected File Manifest

File: `sentinel1_selected_file_manifest.csv`

This manifest is the checksum-backed readiness lane for the standalone local Sentinel-1 TIFF. It does not process pixels and does not authorize the real SAR baseline.

| Field | Meaning |
| --- | --- |
| `file_name` | Selected Sentinel-1 source file name. |
| `local_path_hint` | Redacted path hint such as `<input_dir>/filename`; absolute source paths are not committed. |
| `sha256` | SHA-256 checksum of the selected local TIFF. |
| `sha256_status` | `recorded` after the checksum is computed. |
| `file_size_bytes` / `file_size_gb` | Local source-file size recorded for review. |
| `raster_width` / `raster_height` | Raster dimensions from the local data library metadata. |
| `raster_count` | Number of raster bands; the selected standalone file has `2`. |
| `raster_dtypes` | Raster data types for the selected bands. |
| `band_descriptions` | Band labels; the selected standalone file is `VV|VH`. |
| `crs` | Coordinate reference system string; the selected standalone file is `EPSG:4326`. |
| `bbox_lon_min` / `bbox_lat_min` / `bbox_lon_max` / `bbox_lat_max` | Approximate footprint bounds. |
| `mvp_overlap` | Current MVP overlap flag; the selected standalone file overlaps `mae_sai_2024_point`. |
| `candidate_use` | Conservative use note for why the file is selected. |
| `source_license_status` | User-reported local hackathon free-use status, not full provenance resolution. |
| `provenance_status` | Current product-provenance status; now `unresolved_placeholder_filename`. |
| `event_timing_status` | Current event-timing status; now `unresolved_no_acquisition_date`. |
| `reference_mask_status` | Current reference-mask gate status; now `unresolved`. |
| `processing_scope` | Limited scope, currently `sentinel1_sar_context_readiness_only`. |
| `processing_allowed` | `False` until provenance, event timing, and reference-mask gates are clear. |
| `reason_blocked` | Human-readable blockers that prevent real processing. |
| `assumptions` | Non-operational note that the source TIFF remains outside Git. |

## Sentinel-1 Provenance Resolved Manifest

File: `sentinel1_provenance_resolved_manifest.csv`

This manifest records metadata-only provenance findings for the selected local Sentinel-1 TIFF. It answers whether acquisition timing or product identity can be recovered from current local evidence. It does not process pixels and does not authorize the real SAR baseline.

| Field | Meaning |
| --- | --- |
| `resolved_product_id` | CDSE/product id if a trusted metadata match exists; current local row is `unresolved`. |
| `source_package` | Local package or package-candidate evidence, such as the Drive ZIP containing Sentinel-1 companion tiles. |
| `acquisition_datetime` | Resolved acquisition timestamp if recoverable; current local row is `unresolved`. |
| `orbit_direction` | Orbit direction if available from product metadata or tags. |
| `relative_orbit` | Relative orbit if available from product metadata or tags. |
| `platform` | Sentinel-1 platform such as `S1A` if resolvable. |
| `product_type` | Product type such as `GRDH_1SDV` if resolvable. |
| `candidate_role` | One of `pre_event_candidate`, `post_event_candidate`, `context_only`, or `unresolved`. |
| `provenance_status` | Product identity status; current local row is `unresolved_placeholder_filename`. |
| `event_timing_status` | Acquisition/event timing gate; current local row is `timing_unresolved`. |
| `timing_confidence` | Confidence in timing evidence; current local row is `low`. |
| `provenance_confidence` | Confidence in product provenance evidence; current local row is `low`. |
| `tiff_tag_summary` | TIFF tags inspected without reading raster pixels. |
| `filename_evidence` | Explanation of what the local filename does or does not prove. |
| `zip_member_evidence` | ZIP-member-name evidence inspected without extraction. |
| `cdse_match_evidence` | CDSE metadata snapshot match evidence when a snapshot is supplied. |
| `provider_note_evidence` | Provider or hackathon note evidence; usage notes do not prove acquisition timing. |
| `processing_scope` | Limited scope, currently `sentinel1_provenance_resolution_only`. |
| `processing_allowed` | `False` until provenance, acquisition timing, and reference-mask gates pass. |
| `still_blocked_reason` | Human-readable blockers preventing real baseline use. |

Current local result: the selected TIFF overlaps Mae Sai and has VV/VH bands, but acquisition date and product id are not recoverable from committed evidence. It must not be used as a pre/post real flood baseline input yet.

## Sentinel-1 Context Quicklook Manifest

File: `sentinel1_quicklook_manifest.csv`

This manifest records small PNG quicklooks from the selected local Sentinel-1 file. It is a context-preview lane only and does not authorize flood detection, validation, official warning use, or the real Mae Sai SAR baseline.

| Field | Meaning |
| --- | --- |
| `file_name` | Selected Sentinel-1 source file name. |
| `sha256_prefix` | First 12 characters of the selected source SHA-256 checksum for review. |
| `sha256_status` | Must be `recorded`; quicklook generation refuses unrecorded checksums. |
| `mvp_overlap` | Current overlap flag; the selected file overlaps `mae_sai_2024_point`. |
| `event_timing_status` | Current timing state, still `timing_unresolved`. |
| `provenance_status` | Current provenance state, still `unresolved_placeholder_filename`. |
| `band` / `band_description` | SAR polarization shown in the quicklook, currently `VV` or `VH`. |
| `quicklook_path` | Relative PNG path used by `outputs/dashboard.html`. |
| `quicklook_format` | Output image format, currently `png`. |
| `quicklook_width` / `quicklook_height` | Small preview dimensions. |
| `quicklook_file_size_bytes` | PNG file size; output should remain small. |
| `raster_reader` | Optional local raster reader used, such as `rasterio` or GDAL. |
| `processing_scope` | `sentinel1_sar_context_quicklook_only`; not real flood processing. |
| `warning_text` | Required warning: SAR context only, not flood detection, not validation, not an official warning, and event timing unresolved unless proven otherwise. |
| `assumptions` | Source TIFF remains outside Git and the quicklook is non-operational. |

## DEM Selected File Manifest

File: `dem_selected_file_manifest.csv`

This manifest records package-level readiness for local Copernicus DEM/elevation-slope ZIP assets. It is terrain context only and does not extract or commit source DEM TIFF members.

| Field | Meaning |
| --- | --- |
| `package_name` | Local DEM ZIP package name. |
| `member_name` | DEM/elevation-slope TIFF member name inside the package. |
| `local_package_path_hint` | Redacted package path such as `<input_dir>/package.zip`. |
| `member_path_hint` | Redacted package/member hint such as `<input_dir>/package.zip::member.tif`. |
| `package_sha256` | SHA-256 checksum of the whole ZIP package. |
| `package_sha256_status` | `recorded` after the package checksum is computed. |
| `package_file_size_bytes` / `package_file_size_gb` | Local ZIP package size. |
| `zip_member_count` | Number of members in the selected ZIP package from the local data library. |
| `member_size_bytes` / `member_size_gb` | Uncompressed member size from the ZIP catalog. |
| `member_kind` | Member type, currently `image_tiff` for DEM rows. |
| `checksum_strategy` | Package-level checksum first; member-level checksum only if extracted later into a controlled workspace. |
| `candidate_use` | Terrain/slope context for false-positive review and exposure explanation. |
| `source_license_status` | User-reported local hackathon free-use status, not an operational authorization. |
| `reference_mask_status` | `not_reference_mask`; DEM is not a flood reference mask. |
| `flood_observation_status` | `not_flood_observation`; DEM is terrain context, not observed water. |
| `flood_label_status` | `not_flood_label`; DEM must not be used as an ML target. |
| `processing_scope` | Limited scope, currently `dem_terrain_context_readiness_only`. |
| `processing_status` | Current state, `blocked_until_member_extraction_and_scope_review`. |
| `processing_allowed` | `False` for current rows. |
| `reason_blocked` | Human-readable blocker explaining context-only use and no extraction. |
| `assumptions` | Non-operational note that source ZIPs remain outside Git. |

## DEM Context Quicklook Manifest

File: `dem_quicklook_manifest.csv`

This manifest records a small PNG terrain preview from one selected DEM TIFF member that was extracted outside Git and checksum-tracked. It is not a flood observation, flood label, reference mask, validation layer, or official warning product.

| Field | Meaning |
| --- | --- |
| `source_name` | Source family for the DEM package. |
| `package_name` | Local DEM ZIP package containing the selected member. |
| `member_name` | Selected DEM TIFF member name. |
| `package_sha256_prefix` | First 12 characters of the package-level SHA-256. |
| `package_sha256_status` | Must be `recorded`. |
| `member_sha256_prefix` | First 12 characters of the extracted member SHA-256. |
| `member_sha256_status` | Must be `recorded`; generation refuses absent member checksums. |
| `local_extracted_path_hint` | Redacted outside-Git path hint such as `<external_data_workspace>/member.tif`. |
| `quicklook_path` | Relative PNG path used by `outputs/dashboard.html`. |
| `quicklook_format` | Output image format, currently `png`. |
| `quicklook_width` / `quicklook_height` | Small preview dimensions. |
| `quicklook_file_size_bytes` | PNG file size; output should remain small. |
| `raster_reader` | Optional local raster reader used, such as `rasterio` or GDAL. |
| `reference_mask_status` | Must be `not_reference_mask`. |
| `flood_observation_status` | Must be `not_flood_observation`. |
| `flood_label_status` | Must be `not_flood_label`. |
| `processing_scope` | `dem_terrain_context_quicklook_only`; not real flood processing. |
| `warning_text` | Required warning: terrain context only, not flood observation, not flood label, not reference mask, and not an official warning. |
| `assumptions` | Extracted DEM source remains outside Git and the quicklook is non-operational. |

## Synthetic SAR Baseline

Files: `sample_sar_baseline.csv` and `sample_sar_validation_metrics.csv`

| Field | Meaning |
| --- | --- |
| `pixel_id` | Stable synthetic pixel/cell id. |
| `row` | Synthetic grid row. |
| `col` | Synthetic grid column. |
| `pre_vv_db` | Synthetic pre-event VV backscatter value in dB. |
| `post_vv_db` | Synthetic post-event VV backscatter value in dB. |
| `pre_vh_db` | Synthetic pre-event VH backscatter value in dB. |
| `post_vh_db` | Synthetic post-event VH backscatter value in dB. |
| `vv_drop_db` | Pre/post VV drop, positive when post-event backscatter is lower. |
| `vh_drop_db` | Pre/post VH drop, positive when post-event backscatter is lower. |
| `combined_drop_db` | Weighted synthetic drop score used by the non-ML threshold baseline. |
| `flood_probability_0_1` | Synthetic flood probability from the threshold baseline. |
| `binary_flood_extent` | Synthetic predicted flood mask using probability threshold `0.5`. |
| `reference_flood_extent` | Synthetic reference mask value for validation. |
| `true_positive` | Predicted flood and reference flood count. |
| `false_positive` | Predicted flood where reference is non-flood. |
| `false_negative` | Predicted non-flood where reference is flood. |
| `true_negative` | Predicted non-flood and reference non-flood count. |
| `iou` | Intersection over Union for the synthetic mask. |
| `f1_dice` | F1/Dice score for the synthetic mask. |
| `precision` | Synthetic flood precision. |
| `recall` | Synthetic flood recall. |
| `area_error_ratio` | Signed predicted flood area error relative to reference flood area. |

## Mae Sai Weak-Reference Sentinel-1 Baseline

Files: `mae_sai_weak_sar_feature_manifest.csv`, `mae_sai_weak_baseline_metrics.csv`, and `mae_sai_weak_baseline_summary.md`

These outputs are candidate metrics against a manually digitized weak-reference mask. They are non-operational, not official validation, not field validated, and not ML labels. Source Sentinel-1 ZIPs and the manual GeoPackage remain outside Git.

| Field | Meaning |
| --- | --- |
| `processing_scope` | `weak_reference_real_sentinel1_non_ml_candidate`; this is a candidate baseline, not official validation. |
| `pre_product_id` | CDSE Sentinel-1 pre-event product id used for the candidate run. |
| `post_product_id` | CDSE Sentinel-1 post-event product id used for the candidate run. |
| `reference_product_id` | Manual weak-reference id from the QGIS GeoPackage manifest. |
| `reference_status` | Must remain `weak_reference_candidate`; this does not clear the official reference-mask gate. |
| `sample_pixel_count` | Number of sampled pixels/cells used in the candidate metric calculation. |
| `reference_positive_pixel_count` | Number of sampled pixels marked as flood in the manual weak-reference mask. |
| `predicted_positive_pixel_count` | Number of sampled pixels predicted as flood by the non-ML SAR threshold. |
| `georeferencing_method` | Current method for locating the sample window, such as `sentinel1_safe_gcps_affine_fit`. |
| `vv_drop` / `vh_drop` | Pre-event dB minus post-event dB; positive values indicate lower post-event backscatter. |
| `vv_ratio` / `vh_ratio` | Post-event amplitude divided by pre-event amplitude. |
| `combined_sar_change_score` | Weighted SAR change score; current first baseline weights VH at 0.60 and VV at 0.40. |
| `flood_probability_0_1` | Non-ML probability proxy derived from the combined SAR change score. |
| `binary_flood_extent` | Candidate binary flood prediction using the configured probability threshold. |
| `reference_flood_extent` | Manual weak-reference mask value used for candidate metrics. |
| `true_positive` / `false_positive` / `false_negative` / `true_negative` | Binary mask comparison counts against the manual weak reference. |
| `iou` | Intersection over Union against the manual weak-reference candidate. |
| `f1_dice` | F1/Dice score against the manual weak-reference candidate. |
| `precision` | Candidate precision against the manual weak-reference candidate. |
| `recall` | Candidate recall against the manual weak-reference candidate. |
| `area_error_ratio` | Signed predicted flood area error relative to manual weak-reference area. |
| `warning_text` | Required safety wording: candidate metrics only, non-operational, not official validation, and not field validated. |

## Mae Sai Weak-Reference Decision Bridge

Files: `mae_sai_subdistrict_flood_inputs.csv` and `mae_sai_priority_subdistricts.geojson`

These outputs turn the real Sentinel-1 weak-reference probability summary into FloodGuard decision inputs. They remain weak-reference, non-operational, not official validation, not field validated, and not ML labels. Current rows are a one-feature review-area bridge, not official subdistrict aggregation.

| Field | Meaning |
| --- | --- |
| `subdistrict_id` | Review-area id used for FPPS and GeoJSON joins, currently `MS-WR-001`. |
| `subdistrict_name` | Human-readable review-area label, currently `Mae Sai Weak-Reference Review Area`. |
| `mean_flood_probability_0_1` | Mean non-ML Sentinel-1 flood probability proxy from `mae_sai_weak_sar_feature_manifest.csv`. |
| `flood_likelihood_0_100` | `mean_flood_probability_0_1 * 100`, used by FPPS. |
| `exposure_0_100` | Sampled manual weak-reference positive-pixel share. This is an inundation-share proxy, not population exposure. |
| `access_gap_0_100` | Current placeholder `0.0` until real access-loss context is joined. |
| `road_criticality_0_100` | Current placeholder `0.0` until real road-risk context is joined. |
| `vulnerability_context_0_100` | Current placeholder `0.0` until real vulnerability/population context is joined. |
| `confidence_class` | Current bridge confidence, kept `low` because context and official validation are incomplete. |
| `source_name` | Source label for the weak-reference SAR baseline feeding the decision layer. |
| `source_timestamp` | Post-event Sentinel-1 acquisition timestamp used by the weak-reference baseline. |
| `assumptions` | Required non-operational weak-reference caveat and missing-context explanation. |
| `processing_scope` | Current scope, `weak_reference_real_sentinel1_non_ml_candidate`. |
| `reference_status` | Current reference status, `weak_reference_candidate`; this does not clear the official reference-mask gate. |
| `context_status` | Explicit status showing real population, road, access, and vulnerability context is not joined; current value is `weak_sar_only_real_context_not_joined`. |
| `geometry_status` | GeoJSON property showing the polygon is a manual-reference bbox review area, not official admin geometry. |
| `reference_id` | Manual weak-reference id used to create the review-area geometry. |
| `fpps_0_100` | Flood Preparedness Priority Score computed by `scoring.py` from the weak-reference decision inputs. |
| `action_class` | A-E action class from the existing FPPS scoring contract. Current row is expected to monitor/verify because confidence is low. |
| `top_reason` | Existing FPPS reason text, preserving low-confidence monitoring language. |

## THEOS-2 Local Metadata Manifest

File: `theos2_local_metadata_manifest.csv`

Usage status source: `docs/theos2_usage_terms_log.md`

| Field | Meaning |
| --- | --- |
| `file_name` | Local THEOS-2 file or package name. |
| `local_path_hint` | Redacted path hint such as `<input_dir>/filename`, not an absolute local path. |
| `entry_kind` | File type category, such as `image_tiff`, `overview`, or `zip_package`. |
| `zip_member_count` | Number of members in a local THEOS-2 zip package. |
| `zip_categories` | Category counts discovered inside a zip package. |
| `category` | Sample category inferred from package folders, such as `Disaster`, `Urban`, `Agri`, `Coastal`, or `LULC`. |
| `file_size_bytes` | Local file size in bytes. |
| `file_size_gb` | Local file size in decimal GB. |
| `acquisition_date` | Date parsed from the THEOS-2 filename. |
| `acquisition_time_utc` | Time parsed from the THEOS-2 filename. |
| `processing_level` | Product level parsed from the filename, such as `ORTHO` or `PRIMARY`. |
| `sensor_product` | Product type parsed from the filename, such as `PMS`. |
| `tile_id` | Tile or product id fragment parsed from the filename. |
| `sequence_id` | Download or product sequence suffix when present. |
| `tiff_version` | `BigTIFF` or `ClassicTIFF` for parsed image headers. |
| `image_width` | TIFF image width from header tags. |
| `image_height` | TIFF image height from header tags. |
| `samples_per_pixel` | Number of bands/samples from TIFF header tags. |
| `bits_per_sample` | Bit depth values from TIFF header tags. |
| `compression` | TIFF compression tag value. |
| `pixel_size_m` | Pixel size in meters from GeoTIFF model pixel scale tags when present. |
| `crs_hint` | CRS text inferred from GeoTIFF metadata. |
| `bbox_lon_min` | Approximate western longitude from GeoTIFF tags. |
| `bbox_lat_min` | Approximate southern latitude from GeoTIFF tags. |
| `bbox_lon_max` | Approximate eastern longitude from GeoTIFF tags. |
| `bbox_lat_max` | Approximate northern latitude from GeoTIFF tags. |
| `mvp_overlap` | Whether the image bbox contains the current Mae Sai or Hat Yai MVP point. |
| `floodguard_relevance` | Plain-language note on how the file may support FloodGuard. |
| `license_status` | Current usage status; generated rows use `user_reported_hackathon_free_use` based on project-owner reporting. |
| `sha256_status` | Checksum status; generated rows use `not_recorded`. |
| `processing_allowed` | `False` until selected files have SHA-256 checksums recorded, even though usage permission is reported as clear. |
| `reason_blocked` | Human-readable reason this is metadata-only and blocked. |

## THEOS-2 Selected File Manifest

File: `theos2_selected_file_manifest.csv`

| Field | Meaning |
| --- | --- |
| `file_name` | Selected local THEOS-2 file name. |
| `local_path_hint` | Redacted path hint such as `<input_dir>/filename`; absolute paths are not committed. |
| `entry_kind` | Selected file type, currently `image_tiff`. |
| `category` | Sample category inferred from package folders, such as `Disaster` or `Disaster|LULC`. |
| `source_timestamp` | Acquisition timestamp parsed from the THEOS-2 filename. |
| `bbox_lon_min` / `bbox_lat_min` / `bbox_lon_max` / `bbox_lat_max` | Approximate footprint bounds parsed from GeoTIFF header metadata. |
| `license_status` | `user_reported_hackathon_free_use` based on project-owner reporting. |
| `checksum_algorithm` | Checksum algorithm, currently `sha256`. |
| `sha256` | SHA-256 checksum of the selected local source file. |
| `sha256_status` | `recorded` when the checksum has been computed. |
| `processing_scope` | Limited use scope, currently `theos2_optical_context_preview_only`. |
| `reference_mask_status` | `not_reference_mask`; THEOS-2 is not treated as the legal flood label source. |
| `processing_allowed` | `True` only for the limited optical-context preview scope after checksum recording. |
| `preview_path` | Relative SVG preview-card path used by `outputs/dashboard.html`. |
| `assumptions` | Non-operational context note. |
| `reason_blocked` | Empty for selected rows whose limited preview scope is allowed; populated if a gate fails. |

## THEOS-2 Land-Cover/Exposure Features

File: `theos2_landcover_exposure_features.csv`

| Field | Meaning |
| --- | --- |
| `file_name` | Selected THEOS-2 file used as optical context. |
| `source_timestamp` | Acquisition timestamp parsed from the file name. |
| `category` | Hackathon sample category labels. |
| `has_disaster_context` | Boolean metadata flag for disaster-context samples. |
| `has_lulc_context` | Boolean metadata flag for land-cover context. |
| `has_urban_context` | Boolean metadata flag for urban context. |
| `has_agri_context` | Boolean metadata flag for agricultural context. |
| `has_coastal_context` | Boolean metadata flag for coastal/water-edge context. |
| `rough_bbox_area_sq_km` | Approximate footprint area from parsed bounding box metadata. |
| `mvp_overlap` | Whether the footprint contains the current Mae Sai or Hat Yai MVP point. |
| `built_up_exposure_note` | Non-ML note about possible built-up exposure relevance. |
| `water_context_note` | Non-ML note about possible water/coastal context. |
| `floodguard_use` | Plain-language use in FloodGuard context. |
| `confidence_class` | Metadata-derived confidence label. |
| `assumptions` | Explicit note that these are not flood labels or validation data. |

## THEOS-2 Visual Review Checklist

File: `theos2_visual_review_checklist.csv`

| Field | Meaning |
| --- | --- |
| `file_name` | Selected THEOS-2 file being reviewed. |
| `source_timestamp` | Acquisition timestamp parsed from the file name. |
| `category` | Hackathon sample category labels. |
| `preview_path` | Relative path to the SVG preview card or true PNG thumbnail used for review. |
| `preview_source` | `metadata_svg_preview` or a true-thumbnail source such as `true_png_thumbnail_via_rasterio`. |
| `visible_water_context` | Manual note field initialized as `not_reviewed`; context only, not a flood label. |
| `built_up_area_context` | Manual note field for built-up/exposure interpretation, initialized as `not_reviewed`. |
| `road_context` | Manual note field for road/access context, initialized as `not_reviewed`. |
| `cloud_haze_status` | Manual note field for visual quality limitations, initialized as `not_reviewed`. |
| `exposure_explanation_usefulness` | Manual reviewer assessment of whether the image helps explain exposure context. |
| `review_status` | Review workflow state, initialized as `pending_manual_review`. |
| `reviewer` | Optional reviewer name or initials. |
| `review_date` | Optional manual review date. |
| `review_notes` | Optional free-text note. |
| `flood_label_claim` | Must remain `not_allowed`; THEOS-2 context is not a validation mask or ML label source. |
| `assumptions` | Explicit note that the row is optical context only and not an official warning. |

## Mae Sai Validation Summary

File: `mae_sai_validation_summary.md`

This report remains officially blocked until the legal reference mask, local paths, SHA-256 checksums, and file-level processing gates pass. When weak-reference candidate metrics exist, the report includes them in a separate section and keeps the warning that they are not official validation, not field validated, and not an emergency warning.
