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
