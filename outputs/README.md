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
- `sample_sar_baseline.csv`
- `sample_sar_validation_metrics.csv`
- `real_data_ingestion_manifest.csv`
- `mae_sai_real_data_file_manifest.csv`
- `local_data_library_manifest.csv`
- `local_data_library_zip_members.csv`
- `sentinel1_selected_file_manifest.csv`
- `sentinel1_provenance_resolved_manifest.csv`
- `dem_selected_file_manifest.csv`
- `theos2_local_metadata_manifest.csv`
- `theos2_selected_file_manifest.csv`
- `theos2_previews/*.svg`
- `theos2_thumbnail_manifest.csv`
- `theos2_thumbnails/*.png`
- `theos2_landcover_exposure_features.csv`
- `theos2_visual_review_checklist.csv`
- `mae_sai_validation_summary.md`

Optional live metadata snapshots, generated only when intentionally run and reviewed:

- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`

Before committing optional live metadata snapshots, complete `docs/live_metadata_snapshot_review_checklist.md`.

`dashboard.html` includes static export buttons for downloading the currently selected action brief and the currently filtered priority GeoJSON. These browser downloads are generated from embedded fixture data only.

`theos2_selected_file_manifest.csv` and `theos2_previews/*.svg` are THEOS-2 optical-context artifacts. They are checksum-backed and non-operational, but they are not flood masks, validation labels, or official warning products. Source THEOS-2 TIFF/overview files remain outside Git.

`theos2_thumbnail_manifest.csv` and `theos2_thumbnails/*.png` are small true thumbnail outputs generated from checksum-backed selected files with an optional raster reader. They are optical context only and never full-resolution imagery.

`theos2_landcover_exposure_features.csv` is a non-ML metadata-derived context table. `theos2_visual_review_checklist.csv` is a pending manual-review worksheet for visible water context, built-up area context, road context, cloud/haze, and exposure-explanation usefulness. It is not a flood-label file.

`local_data_library_manifest.csv` and `local_data_library_zip_members.csv` catalog all currently provided local hackathon data files and package members. They are metadata-only and keep all source TIFF/ZIP/overview assets outside Git.

`sentinel1_selected_file_manifest.csv` records the checksum-backed selected Sentinel-1 readiness row for the standalone VV/VH TIFF that overlaps the Mae Sai MVP point. It is not a pre/post pair lock and not processing authorization; provenance, event timing, and reference-mask status remain blocked with `processing_allowed=False`.

`sentinel1_provenance_resolved_manifest.csv` records the metadata-only provenance resolver result for the selected Sentinel-1 row. Current status is `candidate_role=unresolved`, `event_timing_status=timing_unresolved`, and `processing_allowed=False`; the local file must not feed the real Mae Sai SAR baseline until provenance, acquisition timing, and reference-mask status are resolved.

`dem_selected_file_manifest.csv` records package-level checksums for local Copernicus DEM/elevation-slope ZIP packages and catalogs their DEM TIFF members without extraction. Rows remain `processing_allowed=False` and are terrain/slope context only, not flood observations, not flood labels, and not reference masks.

`mae_sai_validation_summary.md` remains blocked until provider responses, local paths, checksums, and reference-mask gates pass.
