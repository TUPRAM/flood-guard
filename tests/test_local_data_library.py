from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from floodguard.local_data_library import (
    LocalDataLibraryError,
    RasterMetadata,
    build_local_data_library,
)


def test_local_data_library_catalogs_files_and_zip_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_zip = tmp_path / "drive-download-20260705T102948Z-3-001.zip"
    dem_zip = tmp_path / "drive-download-20260705T104354Z-3-001.zip"
    sentinel_tif = tmp_path / "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    sentinel_tif.write_bytes(b"fake sentinel bytes")
    _write_zip(
        sentinel_zip,
        {
            "Sentinel1_Thailand-0000023296-0000000000.tif": b"s1",
        },
    )
    _write_zip(
        dem_zip,
        {
            "CopernicusDEM_Elevation_Slope_Thailand-0000000000-0000000000.tif": b"dem",
            "Screenshot 2026-06-30 at 1.17.49\u202fAM.png": b"png",
        },
    )
    monkeypatch.setattr(
        "floodguard.local_data_library._raster_metadata",
        lambda path: RasterMetadata(
            width=23296,
            height=23296,
            count=2,
            dtypes="float32|float32",
            descriptions="VV|VH",
            crs="EPSG:4326",
            bbox_lon_min=97.3436,
            bbox_lat_min=14.187003,
            bbox_lon_max=103.621746,
            bbox_lat_max=20.465149,
        )
        if path.name.startswith("Sentinel1_Thailand")
        else RasterMetadata(),
    )

    manifest, members = build_local_data_library(
        tmp_path,
        file_names=(sentinel_zip.name, dem_zip.name, sentinel_tif.name),
    )

    assert len(manifest) == 3
    assert len(members) == 3
    assert set(manifest["library_group"]) == {"sentinel1_sar", "copernicus_dem"}
    sentinel_row = manifest.loc[manifest["file_name"] == sentinel_tif.name].iloc[0]
    assert sentinel_row["mvp_overlap"] == "mae_sai_2024_point"
    assert sentinel_row["band_descriptions"] == "VV|VH"
    assert bool(sentinel_row["processing_allowed"]) is False
    assert str(tmp_path) not in sentinel_row["local_path_hint"]
    assert set(members["library_group"]) == {
        "sentinel1_sar",
        "copernicus_dem",
        "documentation_image",
    }
    assert members["member_path_hint"].str.contains("<input_dir>/").all()
    assert members["processing_allowed"].eq(False).all()


def test_local_data_library_rejects_missing_requested_file(tmp_path: Path) -> None:
    with pytest.raises(LocalDataLibraryError, match="Missing requested"):
        build_local_data_library(tmp_path, file_names=("missing.zip",))


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
