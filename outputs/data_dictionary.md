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

## Metadata Planning Outputs

Files: `real_data_ingestion_manifest.csv`, `mae_sai_real_data_file_manifest.csv`, `local_data_library_manifest.csv`, and `local_data_library_zip_members.csv`

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
