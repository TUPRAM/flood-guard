from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.dem_quicklook import (
    DEM_QUICKLOOK_WARNING,
    DEMQuicklookError,
    RGBImage,
    RasterReaderStatus,
    detect_raster_reader,
    write_dem_quicklook,
)


def test_detect_raster_reader_reports_missing_optional_reader() -> None:
    status = detect_raster_reader("auto")

    assert status.available in {True, False}
    if not status.available:
        assert "Install rasterio or GDAL" in status.message


def test_dem_quicklook_requires_recorded_package_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "external_dem.tif"
    source.write_bytes(b"dem-bytes")
    manifest = _selected_manifest()
    manifest.loc[:, "package_sha256_status"] = "not_recorded"
    monkeypatch.setattr(
        "floodguard.dem_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(DEMQuicklookError, match="package-level checksum"):
        write_dem_quicklook(
            manifest,
            source,
            tmp_path / "outputs" / "dem_quicklook_manifest.csv",
            member_name=_MEMBER_NAME,
            member_sha256=_sha256(source),
            repo_root=tmp_path / "repo",
        )


def test_dem_quicklook_requires_extracted_path_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "external_dem.tif"
    repo.mkdir()
    source.write_bytes(b"dem-bytes")
    monkeypatch.setattr(
        "floodguard.dem_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(DEMQuicklookError, match="outside the Git repository"):
        write_dem_quicklook(
            _selected_manifest(),
            source,
            repo / "outputs" / "dem_quicklook_manifest.csv",
            member_name=_MEMBER_NAME,
            member_sha256=_sha256(source),
            repo_root=repo,
        )


def test_dem_quicklook_requires_member_level_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "external_dem.tif"
    source.write_bytes(b"dem-bytes")
    monkeypatch.setattr(
        "floodguard.dem_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(DEMQuicklookError, match="member-level SHA-256"):
        write_dem_quicklook(
            _selected_manifest(),
            source,
            tmp_path / "outputs" / "dem_quicklook_manifest.csv",
            member_name=_MEMBER_NAME,
            member_sha256="",
            repo_root=tmp_path / "repo",
        )


def test_dem_quicklook_rejects_member_checksum_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "external_dem.tif"
    source.write_bytes(b"dem-bytes")
    monkeypatch.setattr(
        "floodguard.dem_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(DEMQuicklookError, match="checksum mismatch"):
        write_dem_quicklook(
            _selected_manifest(),
            source,
            tmp_path / "outputs" / "dem_quicklook_manifest.csv",
            member_name=_MEMBER_NAME,
            member_sha256="a" * 64,
            repo_root=tmp_path / "repo",
        )


def test_dem_quicklook_writes_small_context_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "external_dem.tif"
    source.write_bytes(b"dem-bytes")
    output = tmp_path / "outputs" / "dem_quicklook_manifest.csv"
    monkeypatch.setattr(
        "floodguard.dem_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )
    monkeypatch.setattr(
        "floodguard.dem_quicklook._read_dem_rgb",
        lambda path, reader_name, max_size: RGBImage(
            width=2,
            height=2,
            pixels=bytes(
                [
                    10,
                    10,
                    10,
                    90,
                    90,
                    90,
                    180,
                    180,
                    180,
                    240,
                    240,
                    240,
                ]
            ),
        ),
    )

    written = write_dem_quicklook(
        _selected_manifest(),
        source,
        output,
        member_name=_MEMBER_NAME,
        member_sha256=_sha256(source),
        local_extracted_path_hint=f"<external_data_workspace>/{source.name}",
        repo_root=tmp_path / "repo",
    )

    frame = pd.read_csv(written, dtype=str).fillna("")
    row = frame.iloc[0]
    quicklook = output.parent / row["quicklook_path"]
    assert row["member_name"] == _MEMBER_NAME
    assert row["member_sha256_status"] == "recorded"
    assert row["quicklook_path"] == "dem_quicklook.png"
    assert row["quicklook_format"] == "png"
    assert row["quicklook_width"] == "2"
    assert row["quicklook_height"] == "2"
    assert row["processing_scope"] == "dem_terrain_context_quicklook_only"
    assert row["reference_mask_status"] == "not_reference_mask"
    assert row["flood_observation_status"] == "not_flood_observation"
    assert row["flood_label_status"] == "not_flood_label"
    assert row["warning_text"] == DEM_QUICKLOOK_WARNING
    assert "not an official warning" in row["assumptions"]
    assert "external_data_workspace" in row["local_extracted_path_hint"]
    assert str(tmp_path) not in row["local_extracted_path_hint"]
    assert quicklook.exists()
    assert quicklook.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert quicklook.stat().st_size < 1000
    assert not list(output.parent.glob("*.tif"))
    assert not list(output.parent.glob("*.zip"))


def _reader_status() -> RasterReaderStatus:
    return RasterReaderStatus(True, "stub", "stub available")


def _sha256(path: Path) -> str:
    from floodguard.dem_readiness import compute_sha256

    return compute_sha256(path)


_MEMBER_NAME = "CopernicusDEM_Elevation_Slope_Thailand-0000046592-0000023296.tif"


def _selected_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_name": "Hackathon-provided Copernicus DEM Thailand raster",
                "package_name": "drive-download-20260705T104354Z-3-001.zip",
                "member_name": _MEMBER_NAME,
                "package_sha256": "9cb4b87c1daccc9eb8f75b80de706dce76e48fea6a21ad82fed1ab4cea7c44c3",
                "package_sha256_status": "recorded",
                "member_kind": "image_tiff",
                "source_license_status": "user_reported_hackathon_free_use",
                "reference_mask_status": "not_reference_mask",
                "flood_observation_status": "not_flood_observation",
                "flood_label_status": "not_flood_label",
                "processing_scope": "dem_terrain_context_readiness_only",
            }
        ]
    )
