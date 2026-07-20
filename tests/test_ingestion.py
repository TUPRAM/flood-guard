from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from floodguard.ingestion import (
    INGESTION_OUTPUT_COLUMNS,
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
    IngestionPlanError,
    assert_metadata_only_output_path,
    build_ingestion_manifest,
    default_mae_sai_file_manifest_sources,
    default_reference_mask_sources,
    validate_mae_sai_file_manifest_ready,
    write_ingestion_manifest,
)

REPO_ROOT = Path(__file__).parents[1]
_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "build_mae_sai_file_manifest",
    REPO_ROOT / "scripts" / "build_mae_sai_file_manifest.py",
)
assert _SCRIPT_SPEC is not None
assert _SCRIPT_SPEC.loader is not None
build_mae_sai_file_manifest = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(build_mae_sai_file_manifest)


def test_default_reference_mask_sources_build_metadata_only_manifest() -> None:
    manifest = build_ingestion_manifest(default_reference_mask_sources())

    assert list(manifest.columns) == list(INGESTION_OUTPUT_COLUMNS)
    assert len(manifest) == 5
    assert set(manifest["ingestion_stage"]) == {"metadata_only"}
    assert set(manifest["download_permitted_by_skeleton"]) == {False}
    assert set(manifest["ready_for_processing"]) == {False}
    assert set(manifest["processing_allowed"]) == {False}
    assert manifest["blocked_reason"].str.contains("license not confirmed").all()
    assert manifest["reason_blocked"].equals(manifest["blocked_reason"])
    for field in (
        "product_id",
        "local_path",
        "sha256",
        "source_license_status",
        "reference_mask_status",
        "processing_allowed",
        "reason_blocked",
    ):
        assert field in manifest.columns
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
    output_bytes = output_path.read_bytes()
    assert b"\r\n" not in output_bytes
    assert output_bytes.endswith(b"\n")


def test_file_level_manifest_marks_ready_only_when_all_gates_pass() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_name": "Licensed local Sentinel-1 pair",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "source_url": "local metadata record",
                "candidate_use": "non-ML baseline input",
                "geometry_access_status": "confirmed",
                "license_status": "confirmed",
                "redistribution_status": "reference_only",
                "product_id": "S1A_SYNTHETIC_PAIR",
                "local_path": "D:/FloodGuardData/mae_sai/s1_pair",
                "sha256": "a" * 64,
                "source_license_status": "confirmed",
                "reference_mask_status": "confirmed",
                "next_action": "run non-ML baseline validation",
            }
        ]
    )

    manifest = build_ingestion_manifest(frame)

    assert bool(manifest.loc[0, "processing_allowed"]) is True
    assert bool(manifest.loc[0, "ready_for_processing"]) is True
    assert manifest.loc[0, "ingestion_stage"] == "file_ready_metadata"
    assert "sha256 checksum not recorded" not in manifest.loc[0, "reason_blocked"]


def test_mae_sai_file_manifest_sources_are_blocked_until_files_are_acquired() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())

    assert len(manifest) == 3
    assert set(manifest["processing_allowed"]) == {False}
    assert set(manifest["ready_for_processing"]) == {False}
    assert {
        "UNOSAT-3991",
        MAE_SAI_BASELINE_PRE_PRODUCT_ID,
        MAE_SAI_BASELINE_POST_PRODUCT_ID,
    } == set(manifest["product_id"])
    assert not manifest["source_name"].str.contains("COG", case=False).any()
    assert manifest["reason_blocked"].str.contains("local path not recorded").all()
    assert manifest["reason_blocked"].str.contains("sha256 checksum not recorded").all()
    assert manifest["reason_blocked"].str.contains("reference mask not confirmed").all()

    with pytest.raises(IngestionPlanError, match="processing_allowed is not true"):
        validate_mae_sai_file_manifest_ready(manifest)


def test_mae_sai_manifest_absorbs_cdse_acquisition_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    pd.DataFrame(
        [
            {
                "product_id": MAE_SAI_BASELINE_PRE_PRODUCT_ID,
                "product_name": (
                    "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_"
                    "055507_06C5C9_72F7.SAFE"
                ),
                "candidate_role": "pre-event original SAFE",
                "acquisition_date": "2024-09-03T23:16:00.776136Z",
                "download_url": (
                    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products("
                    f"{MAE_SAI_BASELINE_PRE_PRODUCT_ID})/$value"
                ),
                "local_path_hint": "<external_data_workspace>/cdse/mae_sai_2024/pre.zip",
                "sha256": "b" * 64,
                "sha256_status": "recorded",
                "file_size_bytes": "123",
                "download_attempted": "True",
                "download_status": "downloaded_outside_git",
                "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
                "reference_mask_status": "unresolved",
                "processing_allowed": "False",
                "reason_blocked": "reference mask status remains unresolved",
                "retrieved_at_utc": "2026-07-08T00:00:00Z",
            }
        ]
    ).to_csv(outputs_dir / "cdse_mae_sai_acquisition_manifest.csv", index=False)
    monkeypatch.setattr(build_mae_sai_file_manifest, "REPO_ROOT", tmp_path)

    sources = build_mae_sai_file_manifest._with_cdse_acquisition_rows(
        default_mae_sai_file_manifest_sources()
    )
    manifest = build_ingestion_manifest(sources)
    row = manifest[
        manifest["product_id"] == MAE_SAI_BASELINE_PRE_PRODUCT_ID
    ].iloc[0]

    assert row["local_path"] == "<external_data_workspace>/cdse/mae_sai_2024/pre.zip"
    assert row["sha256"] == "b" * 64
    assert row["source_license_status"] == "confirmed"
    assert bool(row["processing_allowed"]) is False
    assert "reference mask not confirmed" in row["reason_blocked"]


def test_mae_sai_manifest_does_not_activate_retired_cog_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    retired_cog_id = "b09f96ca-4a60-43e7-9b8d-158022f0e5bf"
    pd.DataFrame(
        [
            {
                "product_id": retired_cog_id,
                "local_path_hint": "<external_data_workspace>/retired/pre-cog.zip",
                "sha256": "d" * 64,
                "sha256_status": "recorded",
                "download_status": "downloaded_outside_git",
                "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
                "reference_mask_status": "weak_reference_candidate",
            }
        ]
    ).to_csv(outputs_dir / "cdse_mae_sai_acquisition_manifest.csv", index=False)
    monkeypatch.setattr(build_mae_sai_file_manifest, "REPO_ROOT", tmp_path)

    sources = build_mae_sai_file_manifest._with_cdse_acquisition_rows(
        default_mae_sai_file_manifest_sources()
    )

    assert retired_cog_id not in set(sources["product_id"])
    assert set(sources["product_id"]) == {
        "UNOSAT-3991",
        MAE_SAI_BASELINE_PRE_PRODUCT_ID,
        MAE_SAI_BASELINE_POST_PRODUCT_ID,
    }
    assert set(sources["local_path"]) == {"not_acquired"}


def test_mae_sai_file_manifest_ready_returns_required_rows_when_gates_pass() -> None:
    source = default_mae_sai_file_manifest_sources().iloc[[0, 1, 2]].copy()
    source.loc[:, "geometry_access_status"] = "confirmed"
    source.loc[:, "license_status"] = "confirmed"
    source.loc[:, "redistribution_status"] = "reference_only"
    source.loc[:, "local_path"] = [
        "D:/FloodGuardData/mae_sai/reference_mask.geojson",
        "D:/FloodGuardData/mae_sai/pre_s1.tif",
        "D:/FloodGuardData/mae_sai/post_s1.tif",
    ]
    source.loc[:, "sha256"] = ["a" * 64, "b" * 64, "c" * 64]
    source.loc[:, "source_license_status"] = "confirmed"
    source.loc[:, "reference_mask_status"] = "confirmed"
    manifest = build_ingestion_manifest(source)

    ready = validate_mae_sai_file_manifest_ready(manifest)

    assert len(ready) == 3
    assert set(ready["candidate_use"]) == {
        "reference flood mask for validation",
        "pre-event SAR source for non-ML baseline",
        "post-event SAR source for non-ML baseline",
    }


def test_mae_sai_file_manifest_readiness_recomputes_file_level_gates() -> None:
    manifest = build_ingestion_manifest(default_mae_sai_file_manifest_sources())
    manifest.loc[:, "processing_allowed"] = True

    with pytest.raises(
        IngestionPlanError,
        match="local_path is not recorded|sha256 is not recorded|reference_mask_status",
    ):
        validate_mae_sai_file_manifest_ready(manifest)


def test_file_level_manifest_blocks_missing_checksum_and_reference_mask() -> None:
    frame = default_reference_mask_sources().iloc[[0]].copy()
    frame.loc[:, "geometry_access_status"] = "confirmed"
    frame.loc[:, "license_status"] = "confirmed"
    frame.loc[:, "redistribution_status"] = "reference_only"
    frame.loc[:, "product_id"] = "UNOSAT-MAE-SAI-REFERENCE"
    frame.loc[:, "local_path"] = "D:/FloodGuardData/reference/mae_sai_mask.geojson"
    frame.loc[:, "sha256"] = "not_acquired"
    frame.loc[:, "source_license_status"] = "confirmed"
    frame.loc[:, "reference_mask_status"] = "unresolved"

    manifest = build_ingestion_manifest(frame)

    assert bool(manifest.loc[0, "processing_allowed"]) is False
    assert "sha256 checksum not recorded" in manifest.loc[0, "reason_blocked"]
    assert "reference mask not confirmed" in manifest.loc[0, "reason_blocked"]


def test_file_level_manifest_rejects_forced_processing_override() -> None:
    frame = default_reference_mask_sources().iloc[[0]].copy()
    frame.loc[:, "processing_allowed"] = True

    with pytest.raises(IngestionPlanError, match="cannot be forced true"):
        build_ingestion_manifest(frame)


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


def test_mae_sai_file_manifest_script_has_no_download_calls() -> None:
    script_source = (REPO_ROOT / "scripts" / "build_mae_sai_file_manifest.py").read_text(
        encoding="utf-8"
    )

    for token in ("urlopen(", "requests.", "urlretrieve(", "rasterio.open", "gdal."):
        assert token not in script_source
    assert "manual_reference_mask_manifest.csv" in script_source


def test_build_ingestion_manifest_rejects_missing_columns() -> None:
    frame = default_reference_mask_sources().drop(columns=["license_status"])

    with pytest.raises(IngestionPlanError, match="license_status"):
        build_ingestion_manifest(frame)
