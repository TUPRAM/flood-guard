from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def test_multimodal_and_historical_context_docs_keep_evidence_boundaries() -> None:
    feature_doc = (
        REPO_ROOT / "docs" / "multimodal_fusion_and_historical_susceptibility.md"
    ).read_text(encoding="utf-8")
    dictionary = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    output_readme = (REPO_ROOT / "outputs" / "README.md").read_text(
        encoding="utf-8"
    )
    source_registry = (REPO_ROOT / "docs" / "source_registry.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "SAR only",
        "SAR + optical",
        "modality dropout",
        "WorldFloods",
        "THEOS-2",
        "Historical susceptibility/context",
        "Not observed current flooding. Not a forecast.",
        "uncalibrated_requires_basin_event_target_corpus",
        "complete connected basin/event groups",
        "do not claim higher precision",
    ):
        assert phrase.lower() in feature_doc.lower()
    for field in (
        "sample_sentinel2_optical_features.csv",
        "sample_optical_fusion_candidate_assessment.csv",
        "sample_sar_optical_fusion.csv",
        "sample_sar_optical_fusion_validation.csv",
        "sample_historical_susceptibility_context.csv",
        "sample_historical_susceptibility_monotonicity.csv",
        "sample_historical_basin_event_partitions.csv",
        "decision_input_mode",
        "fusion_fallback_reason",
        "historical_conflict_status",
        "eligible_as_current_flood",
        "eligible_as_forecast",
        "eligible_to_replace_event_sar",
    ):
        assert field in dictionary
        if field.endswith((".csv",)):
            assert field in output_readme
    for source in (
        "Copernicus Sentinel-2 via CDSE (Level-2A)",
        "WorldFloods v2",
        "Global Flood Database v1",
        "JRC Global Surface Water",
        "ESA WorldCover",
    ):
        assert source in source_registry


def test_data_dictionary_covers_dashboard_and_metadata_fields() -> None:
    text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(encoding="utf-8")

    for field in (
        "fpps_0_100",
        "road_disruption_probability_0_1",
        "temporary_shelter_change_people_losing_30_min_access",
        "road_closure_change_people_losing_30_min_access",
        "equity_gap_ratio",
        "cdse_product_id",
        "download_permitted_by_skeleton",
        "ready_for_processing",
        "product_id",
        "local_path",
        "sha256",
        "processing_allowed",
        "reason_blocked",
        "flood_probability_0_1",
        "binary_flood_extent",
        "iou",
        "f1_dice",
        "area_error_ratio",
        "theos2_local_metadata_manifest.csv",
        "theos2_selected_file_manifest.csv",
        "theos2_previews/*.svg",
        "theos2_landcover_exposure_features.csv",
        "theos2_thumbnail_manifest.csv",
        "theos2_thumbnails/*.png",
        "theos2_visual_review_checklist.csv",
        "preview_source",
        "flood_label_claim",
        "mae_sai_validation_summary.md",
        "mae_sai_subdistrict_flood_inputs.csv",
        "mae_sai_priority_subdistricts.geojson",
        "mean_flood_probability_0_1",
        "real_open_context_joined_with_proxy_vulnerability",
        "TH570903",
        "mae_sai_context_quality_report.md",
        "dem_population_coverage_rate",
        "local_data_library_manifest.csv",
        "local_data_library_zip_members.csv",
        "sentinel1_sar",
        "copernicus_dem",
        "band_descriptions",
        "member_path_hint",
        "local_path_hint",
        "mvp_overlap",
        "user_reported_hackathon_free_use",
        "docs/theos2_usage_terms_log.md",
        "processing_scope",
        "theos2_optical_context_preview_only",
        "sentinel1_selected_file_manifest.csv",
        "sentinel1_provenance_resolved_manifest.csv",
        "sentinel1_sar_context_readiness_only",
        "sentinel1_provenance_resolution_only",
        "sentinel1_quicklook_manifest.csv",
        "sentinel1_quicklook_vv.png",
        "sentinel1_quicklook_vh.png",
        "sentinel1_sar_context_quicklook_only",
        "quicklook_path",
        "dem_selected_file_manifest.csv",
        "dem_quicklook_manifest.csv",
        "dem_quicklook.png",
        "package_sha256",
        "package_sha256_status",
        "member_sha256_status",
        "checksum_strategy",
        "dem_terrain_context_readiness_only",
        "dem_terrain_context_quicklook_only",
        "not_flood_observation",
        "not_flood_label",
        "provenance_status",
        "event_timing_status",
        "unresolved_placeholder_filename",
        "unresolved_no_acquisition_date",
        "timing_unresolved",
        "candidate_role",
        "reference_mask_status",
        "judge_demo_readme.md",
        "scripts/smoke_dashboard.py",
        "reference_validation_allowed",
        "ml_label_allowed",
        "screenshots_demo_allowed",
        "ml_label_use_allowed",
        "public_reference_candidate_manifest.csv",
        "sentinel_asia_public_product_links.csv",
        "public_reference_file_inspection_manifest.csv",
        "sentinel_asia_geometry_quality_review.csv",
        "sentinel_asia_mbrsc_visual_qa_review.csv",
        "sentinel_asia_product_terms_review.csv",
        "manual_reference_mask_manifest.csv",
        "manual_qgis_weak_reference",
        "weak_reference_candidate",
        "candidate_validation_metrics_allowed",
        "official_validation_truth_allowed",
        "unqualified_ml_label_allowed",
        "cems_product_candidate_manifest.csv",
        "mae_sai_reference_candidate_decision.md",
        "open_context_data_file_manifest.csv",
        "cdse_mae_sai_acquisition_manifest.csv",
        "dataset-mode-select",
        "qgis_tool",
        "geometry_quality_status",
        "validation_use_status",
        "ml_label_use_status",
        "terms_found",
        "validation_metrics_allowed",
        "Thailand_flood.shp.xml",
        "docs/mbrsc_reference_mask_clearance_memo.md",
        "download_status",
        "blocked_missing_cdse_credentials",
        "feature_bbox_count",
        "mae_sai_review_bbox_feature_count",
        "mae_sai_reference_relevance",
        "mae_sai_point_intersects_polygon",
        "east_southeast_floodplain_feature_count",
        "visual_alignment_assessment",
        "broad_event_noise_assessment",
        "reference_candidate_only_not_validation_truth",
        "cdse_mae_sai_2024_sentinel2_metadata.csv",
        "cdse_hat_yai_2025_sentinel2_metadata.csv",
        "source_group",
        "can_use_for_validation",
        "can_use_for_ml_labels",
        "metadata CSV only",
    ):
        assert field in text
    assert "not official warnings" in text or "not official warnings" in text.lower()


def test_reference_mask_licensing_log_has_required_rows() -> None:
    text = (
        REPO_ROOT / "docs" / "reference_mask_licensing_log.md"
    ).read_text(encoding="utf-8")

    for source in (
        "UNOSAT/UNITAR Mae Sai reference target",
        "GISTDA official flood product candidate",
        "International Charter Activation 1004",
        "Sentinel Asia Southern Thailand 2025",
        "Academic or manual reference mask",
        "Sentinel Asia / MBRSC Northern Thailand 2024 public shapefile",
    ):
        assert source in text
    assert "must not download source data" in text
    assert "redistribution terms not confirmed" in text
    assert "Licensing Tracker V2" in text
    assert "Request status" in text
    assert "Screenshots/demo allowed" in text
    assert "ML-label use allowed" in text
    assert "blocking_decision" in text
    assert "processing_allowed=True" in text
    assert "SHA-256 checksum is recorded" in text
    assert "scripts/check_real_data_gates.py" in text
    assert "mbrsc_reference_mask_clearance_memo.md" in text
    assert "manual_reference_mask_protocol.md" in text
    assert "weak-reference status does not clear official validation" in text
    assert "blocked_product_terms_unresolved" in text


def test_readme_documents_no_download_cdse_output_workflow() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Run The System Locally" in text
    assert 'Set-Location "<repository-root>"' in text
    assert "uv sync --extra dev --extra theos2" in text
    assert "uv run python scripts/generate_sample_decision_outputs.py" in text
    assert "uv run python scripts/smoke_dashboard.py" in text
    assert "start outputs\\dashboard.html" in text
    assert "uv run python -m http.server 8000 -d outputs" in text
    assert "http://localhost:8000/dashboard.html" in text
    assert "Do not commit source TIFF, ZIP, SAFE, JP2, NetCDF, GRIB, or overview files" in text
    assert "--profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv" in text
    assert "--profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv" in text
    assert "--profile mae_sai_2024_sentinel2 --output outputs/cdse_mae_sai_2024_sentinel2_metadata.csv" in text
    assert "--profile hat_yai_2025_sentinel2 --output outputs/cdse_hat_yai_2025_sentinel2_metadata.csv" in text
    assert "build_public_reference_manifest.py" in text
    assert "public_reference_candidate_manifest.csv" in text
    assert "sentinel_asia_public_product_links.csv" in text
    assert "does not download product ZIPs" in text
    assert "docs/live_metadata_snapshot_review_checklist.md" in text
    assert "docs/live_metadata_snapshot_review_log.md" in text
    assert "docs/ml_readiness_plan.md" in text
    assert "docs/sar_baseline_contract.md" in text
    assert "docs/first_ml_experiment_plan.md" in text
    assert "sample_sar_baseline.csv" in text
    assert "build_theos2_local_manifest.py" in text
    assert "generate_theos2_true_thumbnails.py --check-reader" in text
    assert "generate_theos2_true_thumbnails.py --verify-checksum" in text
    assert "generate_theos2_visual_review_checklist.py" in text
    assert "generate_theos2_features.py" in text
    assert "build_sentinel1_selected_manifest.py" in text
    assert "resolve_sentinel1_provenance.py" in text
    assert "generate_sentinel1_quicklooks.py --check-reader" in text
    assert "build_dem_selected_manifest.py" in text
    assert "generate_dem_quicklook.py --check-reader" in text
    assert "generate_mae_sai_validation_summary.py" in text
    assert "check_real_data_gates.py --allow-blocked" in text
    assert "validate_mae_sai_file_manifest.py --allow-blocked" in text
    assert "These CDSE metadata commands write metadata rows only" in text
    assert "downloaded outside Git with SHA-256 checksums recorded" in text
    assert "build_ingestion_manifest.py" in text
    assert "build_local_data_library.py" in text


def test_public_open_data_docs_and_outputs_are_metadata_only() -> None:
    doc_text = (REPO_ROOT / "docs" / "public_open_data_acquisition.md").read_text(
        encoding="utf-8"
    )
    log_text = (
        REPO_ROOT / "docs" / "live_metadata_snapshot_review_log.md"
    ).read_text(encoding="utf-8")
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    manifest_text = (
        REPO_ROOT / "outputs" / "public_reference_candidate_manifest.csv"
    ).read_text(encoding="utf-8")
    sentinel_asia_text = (
        REPO_ROOT / "outputs" / "sentinel_asia_public_product_links.csv"
    ).read_text(encoding="utf-8")

    for phrase in (
        "No source imagery",
        "mbrsc_reference_mask_clearance_memo.md",
        "manual_reference_mask_manifest.csv",
        "public_reference_candidate_manifest.csv",
        "sentinel_asia_public_product_links.csv",
        "CEMS EMSR754",
        "Current rows do not cover Mae Sai",
        "WGS84 polygon geometry",
        "QGIS/GDAL review confirms",
        "Visual QA indicates",
        "not a single broad event boundary",
        "exact Mae Sai point is not inside",
        "supplying-agency copyright applies",
        "humanitarian/academic/non-commercial",
        "Thailand_flood.shp.xml",
        "not product-specific clearance",
        "downloaded outside Git with SHA-256 checksums recorded",
        "product terms remain unresolved",
        "still blocked for processing until reference-mask status clears",
        "Sentinel-2 metadata only",
        "not automatically validation masks",
        "does not clear ML-label gates",
        "manual QGIS weak-reference lane",
        "candidate metrics only",
    ):
        assert phrase in doc_text

    assert "Download performed" in log_text
    assert "| `outputs/sentinel_asia_public_product_links.csv` | 33 | no |" in log_text
    assert "no raw source assets" in log_text
    assert "public_reference_candidate_manifest.csv" in output_text
    assert "sentinel_asia_public_product_links.csv" in output_text
    assert "public_reference_file_inspection_manifest.csv" in output_text
    assert "sentinel_asia_geometry_quality_review.csv" in output_text
    assert "sentinel_asia_mbrsc_visual_qa_review.csv" in output_text
    assert "sentinel_asia_product_terms_review.csv" in output_text
    assert "mbrsc_reference_mask_clearance_memo.md" in output_text
    assert "manual_reference_mask_manifest.csv" in output_text
    assert "mae_sai_subdistrict_flood_inputs.csv" in output_text
    assert "mae_sai_priority_subdistricts.geojson" in output_text
    assert "FloodGuard decision layer" in output_text
    assert "cems_product_candidate_manifest.csv" in output_text
    assert "mae_sai_reference_candidate_decision.md" in output_text
    assert "open_context_data_file_manifest.csv" in output_text
    assert "cdse_mae_sai_acquisition_manifest.csv" in output_text
    assert "Public Reference Candidate Manifest" in contract_text
    assert "Public Reference File Inspection Manifest" in contract_text
    assert "Sentinel Asia Geometry Quality Review" in contract_text
    assert "Sentinel Asia MBRSC Visual QA Review" in contract_text
    assert "Sentinel Asia Product Terms Review" in contract_text
    assert "MBRSC Reference-Mask Clearance Memo" in contract_text
    assert "Manual QGIS Weak-Reference Manifest" in contract_text
    assert "Mae Sai Weak-Reference Decision Input Output" in contract_text
    assert "real open context is joined" in contract_text
    assert (
        "eight Mae Sai reporting polygons from the HDX COD-AB candidate boundary "
        "context"
        in contract_text
    )
    assert "not represented as current agency-confirmed geometry" in contract_text
    assert "CEMS Product Candidate Manifest" in contract_text
    assert "CDSE Mae Sai Acquisition Manifest" in contract_text
    assert "Open Context Data File Manifest" in contract_text
    assert "Dashboard v9 Dataset Mode Switch" in contract_text
    assert "sentinel_asia_product" in contract_text
    assert "can_use_for_ml_labels" in manifest_text
    assert "not_cleared_for_ml_labels" in sentinel_asia_text
    assert "shapefile_zip" in sentinel_asia_text


def test_source_registry_and_backlog_include_public_open_data_lane() -> None:
    source_text = (REPO_ROOT / "docs" / "source_registry.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "Copernicus Sentinel-2 via CDSE",
        "Copernicus EMS Rapid Mapping EMSR754/EMSR756",
        "Sentinel Asia Northern Thailand 2024 public products",
        "NASA MODIS/VIIRS NRT Global Flood Products",
        "outputs/cdse_mae_sai_acquisition_manifest.csv",
        "QGIS/GDAL",
        "6,506 full-layer features",
        "east/southeast of the Mae Sai point",
        "exact Mae Sai point is not inside",
        "supplying-agency copyright applies",
        "Thailand_flood.shp.xml",
        "FloodGuard manual QGIS weak-reference mask",
    ):
        assert phrase in source_text

    assert "Task 51 - Public Open-Data Acquisition Lane" in backlog_text
    assert "Task 52 - Sentinel Asia Geometry Inspection Lane" in backlog_text
    assert "Task 53 - CEMS EMSR754/EMSR756 Product Resolver" in backlog_text
    assert "Task 54 - Mae Sai Public Reference Candidate Decision" in backlog_text
    assert "Task 55 - Open Context Data File Manifest" in backlog_text
    assert "Task 56 - Dashboard Dataset Mode Switch" in backlog_text
    assert "Task 57 - Sentinel Asia QGIS Geometry Quality Review" in backlog_text
    assert "Task 58 - Sentinel Asia Product Terms Review" in backlog_text
    assert "mbrsc_reference_mask_clearance_memo.md" in backlog_text
    assert "Task 59 - CDSE Sentinel-1 Mae Sai Acquisition Gate" in backlog_text
    assert "Task 60 - Mae Sai Manifest Public Reference Update" in backlog_text
    assert "Task 61 - Real Baseline And ML Gate Reminder" in backlog_text
    assert "Task 62 - Manual QGIS Weak-Reference Mask Lane" in backlog_text
    assert "outputs/public_reference_candidate_manifest.csv" in backlog_text
    assert "outputs/manual_reference_mask_manifest.csv" in backlog_text
    assert "outputs/sentinel_asia_public_product_links.csv" in backlog_text
    assert "outputs/sentinel_asia_geometry_quality_review.csv" in backlog_text
    assert "outputs/sentinel_asia_mbrsc_visual_qa_review.csv" in backlog_text
    assert "Visual QA completion must not clear validation metrics" in backlog_text
    assert "outputs/cdse_mae_sai_acquisition_manifest.csv" in backlog_text
    assert "without downloading source imagery or product packages into Git" in backlog_text


def test_licensing_request_templates_cover_priority_sources() -> None:
    text = (
        REPO_ROOT / "docs" / "licensing_request_templates.md"
    ).read_text(encoding="utf-8")

    for source in (
        "UNOSAT/UNITAR",
        "GISTDA",
        "International Charter",
        "Sentinel Asia",
    ):
        assert source in text
    for term in (
        "geometry",
        "redistribution",
        "citation",
        "not use the layer as an official warning",
    ):
        assert term in text


def test_live_metadata_snapshot_checklist_blocks_unreviewed_snapshot_commits() -> None:
    text = (
        REPO_ROOT / "docs" / "live_metadata_snapshot_review_checklist.md"
    ).read_text(encoding="utf-8")

    assert "outputs/cdse_*_metadata.csv" in text
    assert "--dry-run" in text
    assert "row count" in text.lower()
    assert "Product IDs spot-checked" in text
    assert "Download performed: no" in text
    assert "Do not download `.SAFE`, `.tif`, `.jp2`, `.zip`, NetCDF, GRIB" in text


def test_ml_readiness_plan_states_not_ready_and_required_gates() -> None:
    text = (REPO_ROOT / "docs" / "ml_readiness_plan.md").read_text(
        encoding="utf-8"
    )

    assert "not ready for a new qualified real-data ML experiment" in text
    assert "active checksum-bound original-SAFE source pair" in text
    for phrase in (
        "reference mask",
        "Sentinel-1 pair",
        "metadata snapshot",
        "checksums",
        "non-ML baseline",
        "IoU",
        "F1/Dice",
        "Do not start with a deep model",
    ):
        assert phrase in text


def test_data_dictionary_mentions_dashboard_v4_exports() -> None:
    text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )

    assert "Dashboard v4 browser-only exports" in text
    assert "Download current brief" in text
    assert "Download filtered GeoJSON" in text
    assert "Dashboard v5 THEOS-2 cards" in text
    assert "Dashboard v6 Local Data Library panel" in text
    assert "Dashboard v7 narrative panel" in text
    assert "Dashboard v8 Judge Demo Layout" in text
    assert "Dashboard QA support" in text
    assert "docs/dashboard_demo_qa_checklist.md" in text
    assert "docs/demo_walkthrough.md" in text
    assert "app-header" in text
    assert "kpi-strip" in text
    assert "dashboard-workspace" in text
    assert "map-panel" in text
    assert "decision-panel" in text
    assert "context-readiness-panel" in text
    assert "report-section" in text
    assert "Read This First" in text
    assert "What this dashboard can answer" in text
    assert "What remains blocked" in text
    assert "Real Mae Sai Gate Update" in text
    assert "provider response pending" in text
    assert "context layers are not flood labels" in text
    assert "Dashboard Sentinel-1 SAR context" in text
    assert "Dashboard DEM terrain context" in text
    assert "sentinel1_quicklook_vv.png" in text
    assert "sentinel1_quicklook_vh.png" in text
    assert "dem_quicklook.png" in text
    assert "not flood detection" in text
    assert "sentinel1_sar" in text
    assert "copernicus_dem" in text
    assert "theos2_optical" in text
    assert "true_png_thumbnail_via_rasterio" in text


def test_sar_baseline_contract_defines_non_ml_outputs_and_metrics() -> None:
    text = (REPO_ROOT / "docs" / "sar_baseline_contract.md").read_text(
        encoding="utf-8"
    )

    assert "weak-reference candidate baseline are implemented" in text
    assert "verifies their recorded identities and SHA-256 checksums before raster access" in text
    assert "run_gated_real_sar_change_baseline" in text
    assert "flood_probability_0_1" in text
    assert "binary_flood_extent" in text
    assert "sample_sar_validation_metrics.csv" in text
    for metric in ("IoU", "F1/Dice", "precision", "recall", "area error ratio"):
        assert metric in text
    assert "No source raster, SAFE, ZIP, GeoPackage, or model-weight files committed" in text
    assert "not_sigma0_beta0_or_gamma0_calibrated" in text


def test_first_ml_experiment_plan_keeps_ml_blocked_until_gates_pass() -> None:
    text = (REPO_ROOT / "docs" / "first_ml_experiment_plan.md").read_text(
        encoding="utf-8"
    )

    assert "Current status: blocked for a new real-data ML run" in text
    assert "retired COG pair" in text
    assert "qualified_expert_or_adjudicated" in text
    assert "zero unresolved disagreements" in text
    assert "immutable non-overlapping train/calibration/final-holdout membership" in text
    assert "bounded execution authorization" in text
    assert "structurally complete summary row remains insufficient" in text
    assert "floodguard.controlled_experiment" in text
    assert "If any condition fails, ML remains blocked." in text
    assert "processing_allowed=True" in text
    assert "Do not start with a deep model" in text
    assert "non-ML threshold baseline remains the benchmark" in text
    assert "outputs/mae_sai_validation_summary.md" in text


def test_licensing_outreach_status_tracks_not_sent_requests() -> None:
    text = (REPO_ROOT / "docs" / "licensing_outreach_status.md").read_text(
        encoding="utf-8"
    )

    for source in (
        "UNOSAT/UNITAR Mae Sai reference target",
        "GISTDA official flood product candidate",
        "International Charter Activation 1004",
        "Sentinel Asia / MBRSC Northern Thailand 2024 public shapefile",
        "Sentinel Asia Southern Thailand 2025",
    ):
        assert source in text
    assert "sent_waiting_response" in text
    assert "2026-07-03" in text
    assert "Repository automation does not send email" in text
    assert "provider response pending" in text
    assert "visual_qa_complete_terms_unresolved" in text
    assert "mbrsc_reference_mask_clearance_memo.md" in text
    assert "scripts/check_real_data_gates.py --allow-blocked" in text
    assert "scripts/validate_mae_sai_file_manifest.py --allow-blocked" in text


def test_judge_demo_readme_and_walkthrough_document_demo_path() -> None:
    judge_text = (REPO_ROOT / "outputs" / "judge_demo_readme.md").read_text(
        encoding="utf-8"
    )
    walkthrough_text = (REPO_ROOT / "docs" / "demo_walkthrough.md").read_text(
        encoding="utf-8"
    )
    qa_text = (REPO_ROOT / "docs" / "dashboard_demo_qa_checklist.md").read_text(
        encoding="utf-8"
    )
    qa_notes_text = (REPO_ROOT / "docs" / "dashboard_visual_qa_notes.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "fixture decision layer and a Mae Sai weak-reference candidate lane",
        "What The Fixture Demo Proves",
        "does not prove real flood-detection accuracy",
        "Official-label ML remains blocked",
        "What The Mae Sai Candidate Adds",
        "FG-TB-001 / River Market",
        "TH570903 / Ko Chang",
        "active original-SAFE SAR evidence",
        "Sentinel-1 SAR quicklooks: context only",
    ):
        assert phrase in judge_text

    for phrase in (
        "3-5 Minute Judge Path",
        "10 Minute Expanded Path",
        "temporary shelter delta",
        "road closure delta",
        "Sentinel-1 evidence",
        "Judge mode",
        "English/Thai",
        "TH570903 / Ko Chang",
        "not an official warning",
    ):
        assert phrase in walkthrough_text

    for phrase in (
        "1536x1024",
        "2048x1152",
        "1440x900",
        "scripts/smoke_dashboard.py",
        "uv run python -m http.server 8000 -d outputs",
        "no absolute local source paths",
    ):
        assert phrase in qa_text

    for phrase in (
        "Historical Dashboard Visual QA Notes",
        "not current-release visual evidence",
        "Screenshot evidence was saved outside Git; no screenshot files were committed",
        "1536x1024",
        "2048x1152",
        "1440x900",
        "Historical selected ADM3: `TH570906 / Wiang Phang Kham`",
        "eight ADM3 labels rendered with zero overlaps",
        "Action-brief and filtered-GeoJSON exports were disabled",
        "weak_reference_candidate_cross_border_calibration",
        "not official validation",
    ):
        assert phrase in qa_notes_text


def test_mae_sai_pair_decision_note_locks_planning_pair_not_processing() -> None:
    text = (REPO_ROOT / "docs" / "mae_sai_pair_decision_note.md").read_text(
        encoding="utf-8"
    )

    assert "same-track original SAFE pair selected" in text
    assert "every processing run remains" in text
    assert "fail-closed" in text
    assert "aaaef3af-fa49-4115-bf0f-f54175e7aedf" in text
    assert "5251b74b-0bbd-4365-9eb4-fa33292e175a" in text
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in text
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in text
    assert "6a02d487-68fa-4be7-9628-f312b9049967" in text
    assert "retired from baseline selection" in text.lower()
    assert "refuses to invent a" in text
    assert "timestamp for any substituted product identity" in text


def test_weak_reference_plans_status_is_fail_closed_and_source_bound() -> None:
    text = (
        REPO_ROOT / "docs" / "validation" / "weak_reference_plans_1_9_status.md"
    ).read_text(encoding="utf-8")

    assert "5.965378 km" in text
    assert "candidate_cross_border_calibration_metrics" not in text
    assert "aaaef3af-fa49-4115-bf0f-f54175e7aedf" in text
    assert "5251b74b-0bbd-4365-9eb4-fa33292e175a" in text
    assert "Historical evidence retained; new run correctly blocked" in text
    assert "locked_metadata_only" in text
    assert "dashboard_story_available=false" in text
    assert "can_feed_decision_layer=false" in text
    assert "Outstanding external evidence and authority gates" in text
    assert "verify rejection before a" in text
    assert "does not make external storage immutable" in text
    assert "eliminate filesystem race conditions" in text


def test_mbrsc_reference_mask_clearance_memo_keeps_gate_blocked() -> None:
    text = (
        REPO_ROOT / "docs" / "mbrsc_reference_mask_clearance_memo.md"
    ).read_text(encoding="utf-8")
    terms_text = (
        REPO_ROOT / "docs" / "sentinel_asia_product_terms_review.md"
    ).read_text(encoding="utf-8")
    csv_text = (
        REPO_ROOT / "outputs" / "sentinel_asia_product_terms_review.csv"
    ).read_text(encoding="utf-8")
    decision_text = (
        REPO_ROOT / "outputs" / "mae_sai_reference_candidate_decision.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "Status: not cleared for validation metrics",
        "Thailand_flood.shp.xml",
        "It does not include use constraints",
        "Do not set `processing_allowed=True`",
        "blocked_product_terms_unresolved",
        "not cleared",
        "not cleared for ML labels",
        "Do not use it yet as",
    ):
        assert phrase in text

    for phrase in (
        "mbrsc_reference_mask_clearance_memo.md",
        "Thailand_flood.shp.xml",
        "not to set `processing_allowed=True`",
        "not validation truth and not ML labels",
    ):
        assert phrase in terms_text

    assert "general_sentinel_asia_policy_and_Thailand_flood_shp_xml_reviewed" in csv_text
    assert "reference_candidate_only" in csv_text
    assert "blocked_unresolved" in csv_text
    assert "not legal clearance" in decision_text
    assert "processing_allowed=False" in decision_text


def test_data_dictionary_mentions_mae_sai_file_manifest() -> None:
    text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )

    assert "mae_sai_real_data_file_manifest.csv" in text
    assert "aaaef3af-fa49-4115-bf0f-f54175e7aedf" in text
    assert "5251b74b-0bbd-4365-9eb4-fa33292e175a" in text
    assert "Retired COG identities remain historical provenance" in text
    assert "selected September 6 pre-event Sentinel-1 COG" not in text
    assert "selected September 15 post-event Sentinel-1 COG" not in text
    assert "processing_allowed=False" in text
    assert "manual_reference_mask_manifest.csv" in text


def test_current_source_and_action_brief_docs_use_active_lineage() -> None:
    active_source_paths = (
        "docs/data_contract.md",
        "docs/mae_sai_file_manifest_v2.md",
        "docs/ml_readiness_plan.md",
        "docs/public_open_data_acquisition.md",
        "docs/source_registry.md",
        "outputs/README.md",
        "outputs/data_dictionary.md",
    )
    for relative_path in active_source_paths:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "aaaef3af-fa49-4115-bf0f-f54175e7aedf" in text
        assert "5251b74b-0bbd-4365-9eb4-fa33292e175a" in text
        assert "original-SAFE" in text

    current_brief_paths = (
        "docs/data_contract.md",
        "docs/demo_walkthrough.md",
        "outputs/README.md",
        "outputs/data_dictionary.md",
        "outputs/judge_demo_readme.md",
        "docs/submission/2026-geohackathon/bilingual-action-brief-reference.md",
    )
    for relative_path in current_brief_paths:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "TH570903" in text
        assert "Ko Chang" in text
        assert "mae_sai_action_brief_TH570906.md" not in text


def test_historical_weak_label_docs_cannot_be_read_as_current_evidence() -> None:
    summary = (
        REPO_ROOT / "outputs" / "mae_sai_weak_label_ml_summary.md"
    ).read_text(encoding="utf-8")
    dictionary = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )

    for text in (summary, dictionary):
        assert "retired" in text.lower()
        assert "not comparable" in text.lower()
    assert "Always `False` for this historical weak-label artifact" in dictionary


def test_manual_reference_mask_protocol_and_manifest_are_documented() -> None:
    protocol_text = (
        REPO_ROOT / "docs" / "manual_reference_mask_protocol.md"
    ).read_text(encoding="utf-8")
    manifest_text = (
        REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv"
    ).read_text(encoding="utf-8")
    mae_sai_manifest_text = (
        REPO_ROOT / "outputs" / "mae_sai_real_data_file_manifest.csv"
    ).read_text(encoding="utf-8")
    dictionary_text = (
        REPO_ROOT / "outputs" / "data_dictionary.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "weak_reference_candidate",
        "candidate validation metrics",
        "not official validation truth",
        "not an official warning",
        "mae_sai_manual_flood_reference.gpkg",
        "not_official",
        "scripts/inspect_manual_reference_mask.py",
    ):
        assert phrase in protocol_text

    assert (
        "missing_source_file" in manifest_text
        or "ready_for_candidate_metrics" in manifest_text
    )
    assert "manual_qgis_weak_reference" in manifest_text
    assert "official validation truth" in manifest_text
    assert "unqualified ML labels" in manifest_text
    assert "FloodGuard manual QGIS Mae Sai weak-reference candidate" in mae_sai_manifest_text
    assert (
        "manual weak-reference candidate for cross-border calibration metrics"
        in mae_sai_manifest_text
    )
    assert "candidate_validation_metrics_allowed" in dictionary_text
    assert "official_validation_truth_allowed" in dictionary_text


def test_theos2_inventory_doc_keeps_lane_metadata_only_and_blocked() -> None:
    text = (REPO_ROOT / "docs" / "theos2_inventory.md").read_text(
        encoding="utf-8"
    )

    assert "Status: metadata-only inventory created; usage permission reported" in text
    assert "outputs/theos2_local_metadata_manifest.csv" in text
    assert "does not commit THEOS-2 imagery" in text
    assert "13 standalone THEOS-2 image TIFF files" in text
    assert "12 THEOS-2 zip packages" in text
    assert "license_status = user_reported_hackathon_free_use" in text
    assert "processing_allowed = False" in text
    assert "processing_scope = theos2_optical_context_preview_only" in text
    assert "outputs/theos2_selected_file_manifest.csv" in text
    assert "outputs/theos2_previews/*.svg" in text
    assert "outputs/theos2_landcover_exposure_features.csv" in text
    assert "outputs/theos2_visual_review_checklist.csv" in text
    assert "generate_theos2_true_thumbnails.py" in text
    assert "generate_theos2_visual_review_checklist.py" in text
    assert "rasterio" in text
    assert "GDAL" in text
    assert "Current true-thumbnail output was generated with `rasterio`" in text
    assert "do not contain source image pixels" in text
    assert "not flood labels" in text
    assert "not as the first real validation input for Mae Sai or Hat Yai" in text


def test_source_registry_mentions_theos2_as_blocked_optical_context() -> None:
    text = (REPO_ROOT / "docs" / "source_registry.md").read_text(encoding="utf-8")

    assert "THEOS-2 hackathon sample imagery" in text
    assert "Optical context" in text or "optical context" in text
    assert "not the current Mae Sai/Hat Yai validation input" in text
    assert "user-reported hackathon free-use status" in text or "can be used freely" in text
    assert "Local hackathon Sentinel-1 and DEM bundles" in text
    assert "Sentinel-1 standalone TIFF overlaps the Mae Sai MVP point" in text
    assert "outputs/sentinel1_selected_file_manifest.csv" in text
    assert "outputs/sentinel1_provenance_resolved_manifest.csv" in text
    assert "outputs/dem_selected_file_manifest.csv" in text
    assert "processing_allowed=False" in text


def test_local_data_library_doc_describes_catalog_and_blockers() -> None:
    text = (REPO_ROOT / "docs" / "local_data_library.md").read_text(encoding="utf-8")

    for phrase in (
        "outputs/local_data_library_manifest.csv",
        "outputs/local_data_library_zip_members.csv",
        "Sentinel1_Thailand-0000000000-0000000000-002.tif",
        "VV|VH",
        "mae_sai_2024_point",
        "outputs/sentinel1_selected_file_manifest.csv",
        "outputs/sentinel1_provenance_resolved_manifest.csv",
        "docs/sentinel1_local_provenance.md",
        "outputs/dem_selected_file_manifest.csv",
        "build_sentinel1_selected_manifest.py",
        "resolve_sentinel1_provenance.py",
        "build_dem_selected_manifest.py",
        "sentinel1_sar_context_readiness_only",
        "timing_unresolved",
        "dem_terrain_context_readiness_only",
        "drive-download-20260705T102948Z-3-001.zip",
        "Copernicus DEM",
        "THEOS-2 optical",
        "processing_allowed=False",
        "Do not commit source TIFFs",
    ):
        assert phrase in text


def test_theos2_usage_terms_log_records_user_reported_permission() -> None:
    text = (REPO_ROOT / "docs" / "theos2_usage_terms_log.md").read_text(
        encoding="utf-8"
    )

    assert "project owner reported hackathon-provided data can be used freely" in text
    assert "allowed_by_user_report" in text
    assert "checksum_required_before_reproducible_pixel_outputs" in text
    assert "not a flood reference mask" in text


def test_gitignore_blocks_remote_sensing_source_assets() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    for pattern in ("*.tif", "*.TIF", "*.jp2", "*.SAFE", "*.ovr", "*.nc", "*.grib"):
        assert pattern in text


def test_dashboard_v10_real_dataset_contract_is_documented() -> None:
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(
        encoding="utf-8"
    )
    dictionary_text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for text in (contract_text, output_text, dictionary_text, backlog_text):
        for artifact in (
            "mae_sai_road_risk.geojson",
            "mae_sai_facilities.geojson",
            "mae_sai_access_hotspots.geojson",
        ):
            assert artifact in text

    for phrase in (
        "Dashboard v10 Real Dataset Workspace",
        "all eight HDX COD-AB Mae Sai ADM3 priority polygons",
        "persistent weak-reference",
        "selected-unit comparison",
        "source-quality indicators",
        "must not call `fetch`",
    ):
        assert phrase in contract_text

    assert "Task 66 - Dashboard V10 Real Dataset Workspace" in backlog_text
    assert "mode-warning" in dictionary_text
    assert "modeled access-loss hotspot" in dictionary_text


def test_dashboard_v11_semantic_presentation_contract_is_documented() -> None:
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(
        encoding="utf-8"
    )
    dictionary_text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "Dashboard v11 Semantic Presentation Layer",
        "zoom level `12`",
        "English/Thai",
        "Sentinel-1 drawer",
        "Judge presentation mode",
        "preserve the selected-area map view",
    ):
        assert phrase in contract_text

    for field in (
        "semanticDetailZoom",
        "map-detail-status",
        "toggle-focus",
        "facility-cluster-shell",
        "facility-marker-shell",
        "language-en",
        "language-th",
        "sar-evidence-drawer",
        "mean_combined_sar_change_score",
        "technical-provenance",
        "judge-mode-toggle",
    ):
        assert field in dictionary_text

    assert "`dashboard.html` v11" in output_text
    assert "Task 67 - Dashboard V11 Semantic Presentation Layer" in backlog_text


def test_provider_response_logging_guide_and_mae_sai_v2_docs_exist() -> None:
    provider_text = (REPO_ROOT / "docs" / "provider_response_logging_guide.md").read_text(
        encoding="utf-8"
    )
    manifest_text = (REPO_ROOT / "docs" / "mae_sai_file_manifest_v2.md").read_text(
        encoding="utf-8"
    )

    assert "UNOSAT/UNITAR and GISTDA requests were reported sent" in provider_text
    assert "blocked_terms_incomplete" in provider_text
    assert "geometry_access" in provider_text
    assert "Status: blocked." in manifest_text
    assert "reference flood mask for validation" in manifest_text
    assert "processing_allowed=True is not allowed yet" in manifest_text
    assert "outputs/sentinel1_selected_file_manifest.csv" in manifest_text
    assert "outputs/sentinel1_provenance_resolved_manifest.csv" in manifest_text
    assert "candidate_role=unresolved" in manifest_text
    assert "event_timing_status=timing_unresolved" in manifest_text


def test_sentinel1_selected_manifest_output_is_documented_and_blocked() -> None:
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for text in (output_text, contract_text, backlog_text):
        assert "sentinel1_selected_file_manifest.csv" in text
        assert "processing_allowed=False" in text

    for phrase in (
        "sha256_status=recorded",
        "mvp_overlap=mae_sai_2024_point",
        "provenance_status=unresolved_placeholder_filename",
        "event_timing_status=unresolved_no_acquisition_date",
        "Sentinel-1 provenance and timing resolution",
    ):
        assert phrase in contract_text

    assert "Task 42 - Sentinel-1 Provenance And Timing Resolver" in backlog_text


def test_sentinel1_quicklook_output_is_documented_and_context_only() -> None:
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    dictionary_text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for text in (output_text, contract_text, dictionary_text, backlog_text):
        assert "sentinel1_quicklook_manifest.csv" in text
        assert "sentinel1_quicklook_vv.png" in text
        assert "sentinel1_quicklook_vh.png" in text
        assert "not flood detection" in text
        assert "not validation" in text
        assert "not an official warning" in text

    for phrase in (
        "sha256_status=recorded",
        "event_timing_status=timing_unresolved",
        "provenance_status=unresolved_placeholder_filename",
        "processing_scope=sentinel1_sar_context_quicklook_only",
        "Source Sentinel-1 TIFF files remain outside Git",
    ):
        assert phrase in contract_text

    assert "Task 45 - Sentinel-1 Context Quicklook" in backlog_text
    assert "Task 46 - DEM Context Quicklook" in backlog_text


def test_sentinel1_provenance_report_documents_unresolved_timing() -> None:
    report_text = (REPO_ROOT / "docs" / "sentinel1_local_provenance.md").read_text(
        encoding="utf-8"
    )
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    sar_contract_text = (REPO_ROOT / "docs" / "sar_baseline_contract.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "Status: timing unresolved; processing remains blocked.",
        "TIFF tags were inspected without reading raster pixels.",
        "no exact selected-file match",
        "no Sentinel-1 sidecar metadata files found",
        "no CDSE metadata snapshot supplied",
        "cannot be called pre-event, post-event, or event-window yet",
        "Task 43 - DEM Readiness Lane",
    ):
        assert phrase in report_text

    for text in (output_text, contract_text, sar_contract_text):
        assert "sentinel1_provenance_resolved_manifest.csv" in text
        assert "timing_unresolved" in text
        assert "processing_allowed=False" in text


def test_dem_selected_manifest_output_is_documented_and_context_only() -> None:
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    dictionary_text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for text in (output_text, contract_text, dictionary_text, backlog_text):
        assert "dem_selected_file_manifest.csv" in text

    for phrase in (
        "package-level checksum",
        "member-level checksum",
        "terrain/slope context",
        "not_flood_observation",
        "not_flood_label",
        "not_reference_mask",
        "dem_terrain_context_readiness_only",
        "processing_allowed=False",
    ):
        assert phrase in contract_text

    assert "Task 44 - Local Data Library Dashboard Panel" in backlog_text


def test_dem_quicklook_output_is_documented_and_context_only() -> None:
    output_text = (REPO_ROOT / "outputs" / "README.md").read_text(encoding="utf-8")
    contract_text = (REPO_ROOT / "docs" / "data_contract.md").read_text(
        encoding="utf-8"
    )
    dictionary_text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )
    backlog_text = (REPO_ROOT / "tasks" / "codex_backlog.md").read_text(
        encoding="utf-8"
    )

    for text in (output_text, contract_text, dictionary_text, backlog_text):
        assert "dem_quicklook_manifest.csv" in text
        assert "dem_quicklook.png" in text
        assert "terrain context" in text
        assert "not flood observation" in text
        assert "not flood label" in text
        assert "not reference mask" in text
        assert "not an official warning" in text

    for phrase in (
        "package_sha256_status=recorded",
        "member_sha256_status=recorded",
        "local_extracted_path_hint=<external_data_workspace>/...",
        "processing_scope=dem_terrain_context_quicklook_only",
        "extracted DEM TIFF must remain outside Git",
    ):
        assert phrase in contract_text

    assert "Task 46 - DEM Context Quicklook" in backlog_text
    assert "Task 47 - Real Mae Sai Gate Update" in backlog_text
