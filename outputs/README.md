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
- `sample_sentinel2_optical_features.csv`
- `sample_optical_fusion_candidate_assessment.csv`
- `sample_sar_optical_fusion.csv`
- `sample_sar_optical_fusion_validation.csv`
- `sample_historical_susceptibility_context.csv`
- `sample_historical_susceptibility_monotonicity.csv`
- `sample_historical_basin_event_partitions.csv`
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
- `mae_sai_weak_sar_feature_manifest.csv`
- `mae_sai_weak_baseline_metrics.csv`
- `mae_sai_weak_baseline_summary.md`
- `mae_sai_weak_label_ml_metrics.csv`
- `mae_sai_weak_label_ml_prediction_manifest.csv`
- `mae_sai_weak_label_ml_summary.md`
- `mae_sai_admin_context.geojson`
- `mae_sai_adm3_sar_context.csv`
- `mae_sai_population_context.csv`
- `mae_sai_road_risk.csv`
- `mae_sai_facility_context.csv`
- `mae_sai_road_risk.geojson`
- `mae_sai_facilities.geojson`
- `mae_sai_access_hotspots.geojson`
- `mae_sai_access_loss.csv`
- `mae_sai_equity_gap.csv`
- `mae_sai_real_context_decision_inputs.csv`
- `mae_sai_context_quality_summary.csv`
- `mae_sai_context_quality_report.md`
- `mae_sai_subdistrict_flood_inputs.csv`
- `mae_sai_priority_subdistricts.geojson`
- `mae_sai_action_brief_TH570903.md`
- `public_reference_candidate_manifest.csv`
- `sentinel_asia_public_product_links.csv`
- `public_reference_file_inspection_manifest.csv`
- `sentinel_asia_geometry_quality_review.csv`
- `sentinel_asia_mbrsc_visual_qa_review.csv`
- `sentinel_asia_product_terms_review.csv`
- `cems_product_candidate_manifest.csv`
- `mae_sai_reference_candidate_decision.md`
- `open_context_data_file_manifest.csv`
- `cdse_mae_sai_acquisition_manifest.csv`
- `manual_reference_mask_manifest.csv`
- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`
- `cdse_mae_sai_2024_sentinel2_metadata.csv`
- `cdse_hat_yai_2025_sentinel2_metadata.csv`
- `hat_yai_readiness.json`
- `hat_yai_readiness.md`

Optional live metadata snapshots, generated only when intentionally run and reviewed:

- `cdse_mae_sai_2024_metadata.csv`
- `cdse_hat_yai_2025_metadata.csv`
- `cdse_mae_sai_2024_sentinel2_metadata.csv`
- `cdse_hat_yai_2025_sentinel2_metadata.csv`

Before committing optional live metadata snapshots, complete `docs/live_metadata_snapshot_review_checklist.md`.

`sample_sentinel2_optical_features.csv`, `sample_optical_fusion_candidate_assessment.csv`, `sample_sar_optical_fusion.csv`, and `sample_sar_optical_fusion_validation.csv` are synthetic research-contract evidence. They demonstrate cloud masking, pre/event optical feature changes, per-candidate gate reasons, explicit `SAR only` / `SAR + optical` modes, fail-closed quality gates, bit-equivalent SAR fallback, and separate SAR/optical/fused validation slices. The values are not trained real-event results and do not establish higher precision or cleaner boundaries.

`sample_historical_susceptibility_context.csv`, `sample_historical_susceptibility_monotonicity.csv`, and `sample_historical_basin_event_partitions.csv` are synthetic evidence for the historical-context contract. They demonstrate normalized features, explicit missingness, contributions, monotonicity, complete basin/event holdouts, and current-SAR conflict warnings. The score is uncalibrated and must be labeled `Historical susceptibility/context`, never `Current flood` or `Forecast`.

`public_reference_candidate_manifest.csv` is the public/open data fallback inventory. It records source candidates for CDSE Sentinel-1/Sentinel-2, CEMS EMSR754/EMSR756, Sentinel Asia Northern Thailand 2024, UNOSAT/UN Thailand public reports, NASA flood products, WorldPop, OSM/Geofabrik, Copernicus DEM, HDX COD-AB, and local hackathon lanes. It is metadata-only and contains no source imagery or product packages.

`sentinel_asia_public_product_links.csv` records public product URLs scraped from the Sentinel Asia Northern Thailand 2024 event page. These links are event evidence and possible geometry candidates, not automatically validation masks or ML labels. Product files must be downloaded outside Git, checksummed, inspected, and legally reviewed before any use beyond metadata.

`public_reference_file_inspection_manifest.csv` records the selected Sentinel Asia MBRSC shapefile ZIP inspection. The ZIP itself is outside Git. The manifest stores a redacted local path hint, SHA-256 checksum, ZIP members, shapefile CRS, geometry type, bbox, DBF fields, and Mae Sai overlap status. It remains `processing_allowed=False` and `can_use_for_ml_labels=not_cleared_for_ml_labels`.

`sentinel_asia_geometry_quality_review.csv` and `docs/sentinel_asia_geometry_quality_notes.md` record the QGIS/GDAL geometry quality review. Current findings: `6506` full-layer polygon features, `514` Mae Sai review-bbox intersecting features, `464.234` km2 full-layer area-field sum, and `47.164` km2 Mae Sai review-bbox area-field sum. This remains reference-candidate evidence only.

`sentinel_asia_mbrsc_visual_qa_review.csv` and `docs/sentinel_asia_mbrsc_visual_qa_notes.md` record the notes-only visual QA pass. Current finding: polygons are not a single broad event boundary; they concentrate east/southeast of the Mae Sai point and broadly align with floodplain/waterway context, but the exact Mae Sai point is not inside a flood polygon and the layer contains fragmented patches that need manual QA.

`sentinel_asia_product_terms_review.csv`, `docs/sentinel_asia_product_terms_review.md`, and `docs/mbrsc_reference_mask_clearance_memo.md` record the product-terms and clearance review. Current status: no explicit product-level terms were found in the event page, general Sentinel Asia policy, or embedded `Thailand_flood.shp.xml` metadata for validation metrics, screenshots/demo, derived metrics, redistribution, or ML-label use, so the source remains `reference_candidate_only`.

`cems_product_candidate_manifest.csv` records public CEMS AOI/product rows for EMSR754 and EMSR756. It contains product names, AOIs, product types, public package URLs where the API exposes them, dates, layer names, and Mae Sai relevance. No CEMS product package is downloaded into Git.

`mae_sai_reference_candidate_decision.md` compares Sentinel Asia, CEMS, UNOSAT public report evidence, and NASA coarse flood products. Current decision: Sentinel Asia MBRSC shapefile is the first practical public reference-candidate lane, not a cleared validation mask.

`open_context_data_file_manifest.csv` records file-level context-source rows for WorldPop Thailand 100m, HDX Thailand COD-AB, Geofabrik Thailand OSM, and the public Copernicus DEM GLO-30 N20/E099 tile. The selected files are stored outside Git with SHA-256 checksums and redacted path hints committed here. These rows are context only: population exposure, admin aggregation, road/facility extraction, and terrain review. They are not flood labels, reference masks, official warnings, or real validation outputs.

`cdse_mae_sai_acquisition_manifest.csv` records the active same-track Mae Sai Sentinel-1 source pair: original-SAFE pre-event product `aaaef3af-fa49-4115-bf0f-f54175e7aedf` and post-event product `5251b74b-0bbd-4365-9eb4-fa33292e175a`. Both archives are registered outside Git with SHA-256 checksums. The former September 6 / September 15 COG pair is historical retired-source evidence only. Qualified validation and new ML processing remain blocked by reference authority and label-use gates; source products must never be committed into Git.

`manual_reference_mask_manifest.csv` records the manual QGIS weak-reference fallback from `docs/manual_reference_mask_protocol.md`. The manual GeoPackage remains outside Git. Current rows are either a blocked skeleton when the file is missing or checksum/layer metadata when the file exists. Even when ready, this lane is only for candidate validation metrics, visual QA, and non-operational demo reporting; it is not official validation truth, not an official warning, and not unqualified ML labels.

`hat_yai_readiness.json` is a self-hashed, input-checksum-bound Plan 9 readiness receipt. It consumes the pinned Hat Yai CDSE Sentinel-1 candidate snapshot and the relevant ingestion/reference candidate rows without making network calls. `hat_yai_readiness.md` is its human-readable view. A same-platform 12-day original-SAFE pre/post pair is locked at metadata level, but the files are not acquired or checksum/grid verified. Both artifacts remain fail-closed: there is no checksum-bound external source asset, qualified or manual reference mask, candidate metric, decision output, or dashboard story. The selected IDs do not establish acquisition, scene suitability, flood accuracy, or operational readiness.

`dashboard.html` includes static export buttons for downloading the currently selected action brief and the currently filtered priority GeoJSON. These browser downloads are generated from whichever embedded decision dataset is active; they never read source files or call a backend.

`dashboard.html` also includes a Local Data Library panel with embedded metadata summaries for Sentinel-1, DEM, and THEOS-2 readiness lanes. It shows counts, key blocker statuses, and relative CSV links only; source files remain outside Git and processing remains gated.

`dashboard.html` now includes a `Read This First` status narrative. It explains what the fixture demo can answer, what remains blocked, and the Real Mae Sai Gate Update needed before real validation or real-data ML can proceed. The narrative must continue to say that context layers are not flood labels, not reference masks, and not agency flood products.

`dashboard.html` v8 uses a judge-demo command-center layout: app header, KPI strip, three-zone workspace, primary map panel with embedded legends, right-side decision/context/readiness panel, and a below-workspace report section. The layout is still static HTML with embedded data, no backend, and no browser-side `fetch`.

`dashboard.html` v9 includes dataset modes for `Fixture demo`, `Mae Sai weak-reference candidate`, and `Metadata/blocker view`. The Mae Sai weak-reference mode summarizes downloaded outside-Git CDSE Sentinel-1 pre/post product ids, manual QGIS weak-reference status, candidate metrics, flood-probability summary, and the generated weak-reference decision bridge when available. It remains non-operational, not official validation, not field validated, and not an official warning.

`dashboard.html` v10 switches the full map and decision workspace between the fixture dataset, eight real Mae Sai ADM3 candidate polygons, and the metadata/blocker state. Mae Sai mode embeds derived road-risk lines, candidate facility points, modeled access-loss hotspots, selected-unit evidence, comparison values, source-quality indicators, and provenance. An always-visible warning keeps the weak-reference boundary explicit. All layers are committed derivatives; raw Sentinel-1, WorldPop, OSM, COD-AB, DEM, and manual-reference source files remain outside Git.

`dashboard.html` v11 adds semantic Mae Sai map density and presentation controls. Regional zoom shows priority roads and ADM3 facility clusters; zoom level `12` or closer shows all candidate roads and typed facilities only in the selected ADM3 unit. Selected-unit focus dims surrounding polygons, the English/Thai toggle uses Thai-capable typography, and the Sentinel-1 drawer shows compact pre/post/change evidence from `mae_sai_adm3_sar_context.csv`. Compact provenance keeps full technical details expandable. Judge mode hides secondary controls and long report content but never hides the weak-reference warning, source quality, Sentinel-1 evidence, or provenance. These changes are visual only and do not promote candidate data to official validation.

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

`mae_sai_weak_sar_feature_manifest.csv`, `mae_sai_weak_baseline_metrics.csv`, and `mae_sai_weak_baseline_summary.md` record the first real Sentinel-1 non-ML candidate baseline against the manual QGIS weak-reference mask. These outputs read the CDSE Sentinel-1 ZIPs and manual GeoPackage from outside Git and commit only derived CSV/Markdown artifacts. They are candidate metrics only: non-operational, not official validation, not field validated, and not ML labels.

`mae_sai_weak_label_ml_metrics.csv`, `mae_sai_weak_label_ml_prediction_manifest.csv`, and `mae_sai_weak_label_ml_summary.md` record a historical, small weak-label screening experiment. The experiment trained a repo-local logistic model on SAR change features, evaluated it on a spatial holdout, and compared it against the non-ML threshold baseline. These outputs are permanently report-only: non-operational, not official labels, not field validation, not an official warning, and never eligible to feed the decision layer. Any future candidate promotion must use the separate qualified-label, immutable-holdout, calibration, and signed model-promotion workflow.

`mae_sai_admin_context.geojson`, the real-context CSVs, `mae_sai_subdistrict_flood_inputs.csv`, and `mae_sai_priority_subdistricts.geojson` bridge candidate Sentinel-1 flood probability into the FloodGuard decision layer for eight HDX COD-AB Mae Sai ADM3 candidate reporting polygons. `mae_sai_road_risk.geojson`, `mae_sai_facilities.geojson`, and `mae_sai_access_hotspots.geojson` add compact candidate map layers without source paths. WorldPop supplies modeled population, OSM supplies candidate roads/bridges/facilities and a routing graph, and Copernicus DEM supplies terrain context where the selected tile covers population points. Road disruption, access loss, and equity are modeled candidates; vulnerability is a terrain/remoteness proxy, not demographic vulnerability. Boundary authority and vintage still require agency confirmation. The nearby manual weak-reference geometry does not overlap the Thailand ADM3 candidate polygons and remains cross-border calibration evidence only.

`mae_sai_context_quality_summary.csv` and `mae_sai_context_quality_report.md` expose join quality, including reporting-unit counts, population/road/facility coverage, DEM coverage, and the manual-reference/admin mismatch. Missing context is not silently converted into confirmed zero impact.

`mae_sai_action_brief_TH570903.md` is the current highest-priority bilingual Mae Sai candidate action brief for Ko Chang. It combines FPPS with active original-SAFE Sentinel-1 evidence, modeled road risk, access loss, proxy equity, source-quality caveats, and local verification actions. The historical weak-label ML result from the retired COG pair is excluded. The brief is based on weak-reference candidate flood analysis, non-operational, not an official warning, and for planning/demo use only.

`mae_sai_validation_summary.md` remains blocked for qualified or official validation until provider authority, permitted-use, and qualified-reference gates pass. The active original-SAFE pair and cross-border manual reference already have outside-Git paths and SHA-256 checksums; a future qualified reference artifact must receive the same immutable binding. The report includes the existing weak-reference candidate metrics in a separate section without promoting them to official validation.
