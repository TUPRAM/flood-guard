from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.ingestion import (
    INGESTION_OUTPUT_COLUMNS,
    IngestionPlanError,
    assert_metadata_only_output_path,
    build_ingestion_manifest,
    default_reference_mask_sources,
    write_ingestion_manifest,
)

REPO_ROOT = Path(__file__).parents[1]


def test_default_reference_mask_sources_build_metadata_only_manifest() -> None:
    manifest = build_ingestion_manifest(default_reference_mask_sources())

    assert list(manifest.columns) == list(INGESTION_OUTPUT_COLUMNS)
    assert len(manifest) == 5
    assert set(manifest["ingestion_stage"]) == {"metadata_only"}
    assert set(manifest["download_permitted_by_skeleton"]) == {False}
    assert set(manifest["ready_for_processing"]) == {False}
    assert manifest["blocked_reason"].str.contains("license not confirmed").all()
    assert set(manifest["source_name"]) >= {
        "UNOSAT/UNITAR Mae Sai reference target",
        "GISTDA official flood product candidate",
        "International Charter Activation 1004",
        "Sentinel Asia Southern Thailand 2025",
        "Academic or manual reference mask",
    }


def test_write_ingestion_manifest_writes_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "real_data_ingestion_manifest.csv"

    written = write_ingestion_manifest(default_reference_mask_sources(), output_path)

    assert written == output_path
    rows = pd.read_csv(output_path)
    assert len(rows) == 5
    assert set(rows["ingestion_stage"]) == {"metadata_only"}


@pytest.mark.parametrize(
    "filename",
    [
        "mae_sai_reference_mask.tif",
        "sentinel_product.SAFE",
        "hat_yai_scene.zip",
        "era5_precipitation.grib",
        "flood_depth.nc",
    ],
)
def test_metadata_only_output_path_rejects_binary_or_imagery_targets(
    tmp_path: Path,
    filename: str,
) -> None:
    with pytest.raises(IngestionPlanError, match="refuses imagery/product|metadata outputs"):
        assert_metadata_only_output_path(tmp_path / filename)


def test_write_ingestion_manifest_rejects_imagery_output_path(tmp_path: Path) -> None:
    output_path = tmp_path / "blocked_reference_mask.tif"

    with pytest.raises(IngestionPlanError, match="imagery/product output"):
        write_ingestion_manifest(default_reference_mask_sources(), output_path)


def test_ingestion_skeleton_script_has_no_network_download_calls() -> None:
    script_source = (REPO_ROOT / "scripts" / "build_ingestion_manifest.py").read_text(
        encoding="utf-8"
    )
    module_source = (REPO_ROOT / "src" / "floodguard" / "ingestion.py").read_text(
        encoding="utf-8"
    )

    for token in ("urlopen(", "requests.", "urlretrieve(", "rasterio.open", "gdal."):
        assert token not in script_source
        assert token not in module_source


def test_build_ingestion_manifest_rejects_missing_columns() -> None:
    frame = default_reference_mask_sources().drop(columns=["license_status"])

    with pytest.raises(IngestionPlanError, match="license_status"):
        build_ingestion_manifest(frame)
