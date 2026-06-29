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
    assert "They do not download Sentinel-1 assets" in text
    assert "build_ingestion_manifest.py" in text
