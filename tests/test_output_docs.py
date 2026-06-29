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


def test_readme_documents_no_download_cdse_output_workflow() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "--profile mae_sai_2024 --output outputs/cdse_mae_sai_2024_metadata.csv" in text
    assert "--profile hat_yai_2025 --output outputs/cdse_hat_yai_2025_metadata.csv" in text
    assert "docs/live_metadata_snapshot_review_checklist.md" in text
    assert "docs/ml_readiness_plan.md" in text
    assert "They do not download Sentinel-1 assets" in text
    assert "build_ingestion_manifest.py" in text


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
