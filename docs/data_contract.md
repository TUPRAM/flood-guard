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
- recommended action

Default selection uses the highest actionable class order `A > B > C > D > E`, then highest FPPS.

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
- `outputs/action_brief_FG-TB-001.md`

It embeds GeoJSON and Markdown directly in the file and uses Leaflet from CDN for map rendering. It has no backend or build step.

## Study-Area Inventory Output

`docs/study_area_inventory.md` records real-data acquisition planning only. It may include exact candidate metadata, product ids, licensing notes, and blockers, but this repository change does not download real imagery or implement remote-sensing model code.

## GeoJSON Fixtures

GeoJSON fixtures should use WGS84 coordinates (`EPSG:4326`) and small synthetic geometries unless source licensing is explicitly documented.
