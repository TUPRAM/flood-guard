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
| `dashboard.html` | Standalone Leaflet dashboard with embedded GeoJSON, action briefs, validation summary, controls, and scenario cards. |
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

## Metadata Planning Outputs

Files: `real_data_ingestion_manifest.csv` and `mae_sai_real_data_file_manifest.csv`

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

`mae_sai_real_data_file_manifest.csv` is a blocked planning manifest for the first real non-ML SAR baseline. It includes the UNOSAT reference-mask target, the selected September 6 pre-event Sentinel-1 COG, the selected September 15 post-event Sentinel-1 COG, and the September 18 fallback post-event COG. No local paths or checksums are recorded yet, so all rows remain `processing_allowed=False`.

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

This report is blocked until the legal reference mask, local paths, SHA-256 checksums, and file-level processing gates pass. Once ready, it reports IoU, F1/Dice, precision, recall, and area error for the non-ML SAR baseline.
