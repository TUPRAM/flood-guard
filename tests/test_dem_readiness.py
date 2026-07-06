from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.dem_readiness import (
    DEM_SELECTED_COLUMNS,
    REQUIRED_LIBRARY_COLUMNS,
    REQUIRED_MEMBER_COLUMNS,
    DEMReadinessError,
    build_dem_selected_file_manifest,
    compute_sha256,
    write_dem_selected_file_manifest,
)


def test_build_dem_selected_manifest_records_package_checksums_and_blocks_processing(
    tmp_path: Path,
) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"
    (tmp_path / package).write_bytes(b"fake-dem-package")

    manifest = build_dem_selected_file_manifest(
        input_dir=tmp_path,
        local_library=_local_library([package]),
        zip_members=_zip_members(package),
        selected_packages=[package],
    )

    assert list(manifest.columns) == list(DEM_SELECTED_COLUMNS)
    assert len(manifest) == 2
    assert set(manifest["package_name"]) == {package}
    assert manifest["package_sha256"].eq(compute_sha256(tmp_path / package)).all()
    assert manifest["package_sha256_status"].eq("recorded").all()
    assert manifest["checksum_strategy"].str.contains("package-level checksum").all()
    assert manifest["checksum_strategy"].str.contains("member-level checksum only if extracted").all()
    assert manifest["candidate_use"].str.contains("terrain/slope context").all()
    assert manifest["reference_mask_status"].eq("not_reference_mask").all()
    assert manifest["flood_observation_status"].eq("not_flood_observation").all()
    assert manifest["flood_label_status"].eq("not_flood_label").all()
    assert manifest["processing_scope"].eq("dem_terrain_context_readiness_only").all()
    assert manifest["processing_status"].eq(
        "blocked_until_member_extraction_and_scope_review"
    ).all()
    assert manifest["processing_allowed"].eq(False).all()
    assert manifest["reason_blocked"].str.contains("not flood observation").all()
    assert manifest["reason_blocked"].str.contains("not a flood label").all()
    assert str(tmp_path) not in "|".join(manifest["local_package_path_hint"])


def test_write_dem_selected_manifest_writes_csv_without_extracting_members(
    tmp_path: Path,
) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"
    input_dir = tmp_path / "downloads"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / package).write_bytes(b"fake-dem-package")
    library_path = tmp_path / "library.csv"
    members_path = tmp_path / "members.csv"
    _local_library([package]).to_csv(library_path, index=False)
    _zip_members(package).to_csv(members_path, index=False)

    written = write_dem_selected_file_manifest(
        input_dir=input_dir,
        local_library_path=library_path,
        zip_members_path=members_path,
        output_path=output_dir / "dem_selected_file_manifest.csv",
        selected_packages=[package],
    )

    assert written.exists()
    assert not list(output_dir.glob("*.tif"))
    assert not list(output_dir.glob("*.zip"))
    assert not (output_dir / "CopernicusDEM_Elevation_Slope_Thailand-0000000000-0000000000.tif").exists()


def test_build_dem_selected_manifest_fails_when_package_missing_from_library(
    tmp_path: Path,
) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"
    (tmp_path / package).write_bytes(b"fake-dem-package")

    with pytest.raises(DEMReadinessError, match="missing from local data library"):
        build_dem_selected_file_manifest(
            input_dir=tmp_path,
            local_library=_local_library([]),
            zip_members=_zip_members(package),
            selected_packages=[package],
        )


def test_build_dem_selected_manifest_fails_when_package_missing_from_disk(
    tmp_path: Path,
) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"

    with pytest.raises(DEMReadinessError, match="missing from input directory"):
        build_dem_selected_file_manifest(
            input_dir=tmp_path,
            local_library=_local_library([package]),
            zip_members=_zip_members(package),
            selected_packages=[package],
        )


def test_build_dem_selected_manifest_rejects_non_dem_package(tmp_path: Path) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"
    (tmp_path / package).write_bytes(b"fake-dem-package")
    library = _local_library([package])
    library.loc[:, "library_group"] = "sentinel1_sar"

    with pytest.raises(DEMReadinessError, match="not cataloged as Copernicus DEM"):
        build_dem_selected_file_manifest(
            input_dir=tmp_path,
            local_library=library,
            zip_members=_zip_members(package),
            selected_packages=[package],
        )


def test_build_dem_selected_manifest_requires_dem_tiff_members(tmp_path: Path) -> None:
    package = "drive-download-20260705T104354Z-3-001.zip"
    (tmp_path / package).write_bytes(b"fake-dem-package")
    members = _zip_members(package)
    members.loc[:, "library_group"] = "documentation_image"

    with pytest.raises(DEMReadinessError, match="no Copernicus DEM TIFF members"):
        build_dem_selected_file_manifest(
            input_dir=tmp_path,
            local_library=_local_library([package]),
            zip_members=members,
            selected_packages=[package],
        )


def _local_library(packages: list[str]) -> pd.DataFrame:
    rows = []
    for package in packages:
        rows.append(
            {
                "source_name": "Hackathon-provided Copernicus DEM Thailand raster",
                "file_name": package,
                "local_path_hint": f"<input_dir>/{package}",
                "entry_kind": "zip_package",
                "library_group": "copernicus_dem",
                "candidate_use": (
                    "candidate elevation/slope context for flood false-positive "
                    "review and exposure explanation"
                ),
                "file_size_bytes": 16,
                "file_size_gb": 0.0,
                "zip_member_count": 2,
                "license_status": "user_reported_hackathon_free_use",
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_LIBRARY_COLUMNS)


def _zip_members(package: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "container_name": package,
                "member_name": (
                    "CopernicusDEM_Elevation_Slope_Thailand-"
                    f"0000000000-000000000{index}.tif"
                ),
                "member_path_hint": (
                    f"<input_dir>/{package}::"
                    "CopernicusDEM_Elevation_Slope_Thailand-"
                    f"0000000000-000000000{index}.tif"
                ),
                "member_kind": "image_tiff",
                "library_group": "copernicus_dem",
                "member_size_bytes": 100 + index,
                "member_size_gb": 0.0,
                "candidate_use": (
                    "candidate elevation/slope context for flood false-positive "
                    "review and exposure explanation"
                ),
            }
            for index in range(2)
        ],
        columns=REQUIRED_MEMBER_COLUMNS,
    )
