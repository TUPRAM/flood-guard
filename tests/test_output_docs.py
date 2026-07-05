from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


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
        "reference_mask_status",
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
    ):
        assert source in text
    assert "must not download source data" in text
    assert "redistribution terms not confirmed" in text
    assert "Licensing Tracker V2" in text
    assert "Request status" in text
    assert "blocking_decision" in text
    assert "processing_allowed=True" in text
    assert "SHA-256 checksum is recorded" in text


def test_readme_documents_no_download_cdse_output_workflow() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "--profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv" in text
    assert "--profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv" in text
    assert "docs/live_metadata_snapshot_review_checklist.md" in text
    assert "docs/ml_readiness_plan.md" in text
    assert "docs/sar_baseline_contract.md" in text
    assert "docs/first_ml_experiment_plan.md" in text
    assert "sample_sar_baseline.csv" in text
    assert "build_theos2_local_manifest.py" in text
    assert "generate_theos2_true_thumbnails.py --check-reader" in text
    assert "generate_theos2_true_thumbnails.py --verify-checksum" in text
    assert "generate_theos2_visual_review_checklist.py" in text
    assert "generate_theos2_features.py" in text
    assert "generate_mae_sai_validation_summary.py" in text
    assert "They do not download Sentinel-1 assets" in text
    assert "build_ingestion_manifest.py" in text
    assert "build_local_data_library.py" in text


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

    assert "not ready for real-data ML yet" in text
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
    assert "true_png_thumbnail_via_rasterio" in text


def test_sar_baseline_contract_defines_non_ml_outputs_and_metrics() -> None:
    text = (REPO_ROOT / "docs" / "sar_baseline_contract.md").read_text(
        encoding="utf-8"
    )

    assert "synthetic baseline implemented; gated real-data entry point added" in text
    assert "run_gated_real_sar_change_baseline" in text
    assert "flood_probability_0_1" in text
    assert "binary_flood_extent" in text
    assert "sample_sar_validation_metrics.csv" in text
    for metric in ("IoU", "F1/Dice", "precision", "recall", "area error ratio"):
        assert metric in text
    assert "No real Sentinel-1 downloads" in text


def test_first_ml_experiment_plan_keeps_ml_blocked_until_gates_pass() -> None:
    text = (REPO_ROOT / "docs" / "first_ml_experiment_plan.md").read_text(
        encoding="utf-8"
    )

    assert "Current status: not allowed yet" in text
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
        "Sentinel Asia Southern Thailand 2025",
    ):
        assert source in text
    assert "sent_waiting_response" in text
    assert "2026-07-03" in text
    assert "Repository automation does not send email" in text
    assert "provider response pending" in text


def test_mae_sai_pair_decision_note_locks_planning_pair_not_processing() -> None:
    text = (REPO_ROOT / "docs" / "mae_sai_pair_decision_note.md").read_text(
        encoding="utf-8"
    )

    assert "planning pair selected; final processing remains blocked" in text
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in text
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in text
    assert "6a02d487-68fa-4be7-9628-f312b9049967" in text
    assert "Use the September 15 post-event COG as the first baseline target" in text
    assert "do not download any product until the legal/reference-mask gate is cleared" in text


def test_data_dictionary_mentions_mae_sai_file_manifest() -> None:
    text = (REPO_ROOT / "outputs" / "data_dictionary.md").read_text(
        encoding="utf-8"
    )

    assert "mae_sai_real_data_file_manifest.csv" in text
    assert "September 6 pre-event Sentinel-1 COG" in text
    assert "September 15 post-event Sentinel-1 COG" in text
    assert "processing_allowed=False" in text


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


def test_local_data_library_doc_describes_catalog_and_blockers() -> None:
    text = (REPO_ROOT / "docs" / "local_data_library.md").read_text(encoding="utf-8")

    for phrase in (
        "outputs/local_data_library_manifest.csv",
        "outputs/local_data_library_zip_members.csv",
        "Sentinel1_Thailand-0000000000-0000000000-002.tif",
        "VV|VH",
        "mae_sai_2024_point",
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
