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

## Metadata Planning Outputs

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
| `ingestion_stage` | Always `metadata_only` in the current ingestion skeleton. |
| `download_permitted_by_skeleton` | Always `False`; the skeleton does not permit downloads. |
| `ready_for_processing` | Always `False` until geometry, license, and redistribution status are confirmed. |
| `blocked_reason` | Human-readable reason the row is not processing-ready. |
