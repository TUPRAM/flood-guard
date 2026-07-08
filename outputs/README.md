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
- `judge_demo_readme.md`
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
- `sentinel1_quicklook_manifest.csv`
- `sentinel1_quicklook_vv.png`
- `sentinel1_quicklook_vh.png`
- `dem_selected_file_manifest.csv`
- `dem_quicklook_manifest.csv`
- `dem_quicklook.png`
- `theos2_local_metadata_manifest.csv`
- `theos2_selected_file_manifest.csv`
- `theos2_previews/*.svg`
- `theos2_thumbnail_manifest.csv`
- `theos2_thumbnails/*.png`
- `theos2_landcover_exposure_features.csv`
- `theos2_visual_review_checklist.csv`
- `mae_sai_validation_summary.md`
- `public_reference_candidate_manifest.csv`
- `sentinel_asia_public_product_links.csv`
- `public_reference_file_inspection_manifest.csv`
- `cems_product_candidate_manifest.csv`
- `mae_sai_reference_candidate_decision.md`
- `open_context_data_file_manifest.csv`
- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`
- `cdse_mae_sai_2024_sentinel2_metadata.csv`
- `cdse_hat_yai_2025_sentinel2_metadata.csv`

Optional live metadata snapshots, generated only when intentionally run and reviewed:

- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`
- `cdse_mae_sai_2024_sentinel2_metadata.csv`
- `cdse_hat_yai_2025_sentinel2_metadata.csv`

Before committing optional live metadata snapshots, complete `docs/live_metadata_snapshot_review_checklist.md`.

`public_reference_candidate_manifest.csv` is the public/open data fallback inventory. It records source candidates for CDSE Sentinel-1/Sentinel-2, CEMS EMSR754/EMSR756, Sentinel Asia Northern Thailand 2024, UNOSAT/UN Thailand public reports, NASA flood products, WorldPop, OSM/Geofabrik, Copernicus DEM, HDX COD-AB, and local hackathon lanes. It is metadata-only and contains no source imagery or product packages.

`sentinel_asia_public_product_links.csv` records public product URLs scraped from the Sentinel Asia Northern Thailand 2024 event page. These links are event evidence and possible geometry candidates, not automatically validation masks or ML labels. Product files must be downloaded outside Git, checksummed, inspected, and legally reviewed before any use beyond metadata.

`public_reference_file_inspection_manifest.csv` records the selected Sentinel Asia MBRSC shapefile ZIP inspection. The ZIP itself is outside Git. The manifest stores a redacted local path hint, SHA-256 checksum, ZIP members, shapefile CRS, geometry type, bbox, DBF fields, and Mae Sai overlap status. It remains `processing_allowed=False` and `can_use_for_ml_labels=not_cleared_for_ml_labels`.

`cems_product_candidate_manifest.csv` records public CEMS AOI/product rows for EMSR754 and EMSR756. It contains product names, AOIs, product types, public package URLs where the API exposes them, dates, layer names, and Mae Sai relevance. No CEMS product package is downloaded into Git.

`mae_sai_reference_candidate_decision.md` compares Sentinel Asia, CEMS, UNOSAT public report evidence, and NASA coarse flood products. Current decision: Sentinel Asia MBRSC shapefile is the first practical public reference-candidate lane, not a cleared validation mask.

`open_context_data_file_manifest.csv` records planned context-source rows for WorldPop Thailand 100m, HDX Thailand COD-AB, Geofabrik Thailand OSM, and Copernicus DEM GLO-30. These rows are context only and remain blocked until local paths and SHA-256 checksums are recorded outside Git.

`dashboard.html` includes static export buttons for downloading the currently selected action brief and the currently filtered priority GeoJSON. These browser downloads are generated from embedded fixture data only.

`dashboard.html` also includes a Local Data Library panel with embedded metadata summaries for Sentinel-1, DEM, and THEOS-2 readiness lanes. It shows counts, key blocker statuses, and relative CSV links only; source files remain outside Git and processing remains gated.

`dashboard.html` now includes a `Read This First` status narrative. It explains what the fixture demo can answer, what remains blocked, and the Real Mae Sai Gate Update needed before real validation or real-data ML can proceed. The narrative must continue to say that context layers are not flood labels, not reference masks, and not agency flood products.

`dashboard.html` v8 uses a judge-demo command-center layout: app header, KPI strip, three-zone workspace, primary map panel with embedded legends, right-side decision/context/readiness panel, and a below-workspace report section. The layout is still static HTML with embedded data, no backend, and no browser-side `fetch`.

`judge_demo_readme.md` is a short judge-facing narrative pack. It explains what the fixture demo proves, what it does not prove, how FPPS/access/equity/road-risk/scenario outputs connect, and why real validation and ML remain blocked until provider/legal and file-level gates clear.

`theos2_selected_file_manifest.csv` and `theos2_previews/*.svg` are THEOS-2 optical-context artifacts. They are checksum-backed and non-operational, but they are not flood masks, validation labels, or official warning products. Source THEOS-2 TIFF/overview files remain outside Git.

`theos2_thumbnail_manifest.csv` and `theos2_thumbnails/*.png` are small true thumbnail outputs generated from checksum-backed selected files with an optional raster reader. They are optical context only and never full-resolution imagery.

`theos2_landcover_exposure_features.csv` is a non-ML metadata-derived context table. `theos2_visual_review_checklist.csv` is a pending manual-review worksheet for visible water context, built-up area context, road context, cloud/haze, and exposure-explanation usefulness. It is not a flood-label file.

`local_data_library_manifest.csv` and `local_data_library_zip_members.csv` catalog all currently provided local hackathon data files and package members. They are metadata-only and keep all source TIFF/ZIP/overview assets outside Git.

`sentinel1_selected_file_manifest.csv` records the checksum-backed selected Sentinel-1 readiness row for the standalone VV/VH TIFF that overlaps the Mae Sai MVP point. It is not a pre/post pair lock and not processing authorization; provenance, event timing, and reference-mask status remain blocked with `processing_allowed=False`.

`sentinel1_provenance_resolved_manifest.csv` records the metadata-only provenance resolver result for the selected Sentinel-1 row. Current status is `candidate_role=unresolved`, `event_timing_status=timing_unresolved`, and `processing_allowed=False`; the local file must not feed the real Mae Sai SAR baseline until provenance, acquisition timing, and reference-mask status are resolved.

`sentinel1_quicklook_manifest.csv`, `sentinel1_quicklook_vv.png`, and `sentinel1_quicklook_vh.png` are small non-operational SAR context artifacts generated only after a selected Sentinel-1 SHA-256 record exists. They are not flood detection, not validation, not an official warning, and event timing remains unresolved unless provenance is solved. The source Sentinel-1 TIFF remains outside Git.

`dem_selected_file_manifest.csv` records package-level checksums for local Copernicus DEM/elevation-slope ZIP packages and catalogs their DEM TIFF members without extraction. Rows remain `processing_allowed=False` and are terrain/slope context only, not flood observations, not flood labels, and not reference masks.

`dem_quicklook_manifest.csv` and `dem_quicklook.png` are small non-operational terrain-context artifacts generated only after a selected DEM package checksum exists, a DEM TIFF member is extracted outside Git, and a member-level SHA-256 checksum is provided. They are terrain context only, not flood observation, not flood label, not reference mask, and not an official warning.

`mae_sai_validation_summary.md` remains blocked until provider responses, local paths, checksums, and reference-mask gates pass.
