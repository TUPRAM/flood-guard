# Outputs

Generated sample and demo outputs belong here.

Current expected MVP output:

- `sample_priority_scores.csv`
- `data_dictionary.md`
- `sample_road_risk.csv`
- `sample_access_loss.csv`
- `sample_equity_gap.csv`
- `priority_subdistricts.geojson`
- `road_risk.geojson`
- `validation_summary.md`
- `action_brief_FG-TB-001.md`
- `action_brief_FG-TB-002.md`
- `action_brief_FG-TB-003.md`
- `dashboard.html`
- `sample_scenario_add_temporary_shelter_access_loss.csv`
- `sample_scenario_add_temporary_shelter_equity_gap.csv`
- `sample_scenario_close_road_access_loss.csv`
- `sample_scenario_close_road_equity_gap.csv`
- `sample_scenario_summary.csv`
- `sample_fpps_sensitivity.csv`
- `sample_fpps_rank_instability.csv`
- `real_data_ingestion_manifest.csv`

Optional live metadata snapshots, generated only when intentionally run and reviewed:

- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`

Before committing optional live metadata snapshots, complete `docs/live_metadata_snapshot_review_checklist.md`.

`dashboard.html` includes static export buttons for downloading the currently selected action brief and the currently filtered priority GeoJSON. These browser downloads are generated from embedded fixture data only.
