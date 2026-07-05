from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.theos2_thumbnails import (
    RGBImage,
    RasterReaderStatus,
    THEOS2ThumbnailError,
    detect_raster_reader,
    write_theos2_true_thumbnails,
)


def test_detect_raster_reader_reports_missing_optional_reader() -> None:
    status = detect_raster_reader("auto")

    assert status.available in {True, False}
    if not status.available:
        assert "Install rasterio or GDAL" in status.message


def test_true_thumbnail_generation_blocks_without_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")
    monkeypatch.setattr(
        "floodguard.theos2_thumbnails.detect_raster_reader",
        lambda preferred: RasterReaderStatus(
            False,
            "",
            "No optional raster reader available. Install rasterio or GDAL.",
        ),
    )

    with pytest.raises(THEOS2ThumbnailError, match="No optional raster reader|rasterio"):
        write_theos2_true_thumbnails(
            tmp_path,
            _selected_manifest(tmp_path, selected),
            tmp_path / "thumbs",
            preferred_reader="rasterio",
        )


def test_true_thumbnail_generation_requires_preview_only_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")
    manifest = _selected_manifest(tmp_path, selected)
    manifest.loc[:, "processing_scope"] = "not_allowed"
    monkeypatch.setattr(
        "floodguard.theos2_thumbnails.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(THEOS2ThumbnailError, match="preview-only"):
        write_theos2_true_thumbnails(tmp_path, manifest, tmp_path / "thumbs")


def test_true_thumbnail_generation_writes_small_png_with_mocked_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")
    monkeypatch.setattr(
        "floodguard.theos2_thumbnails.detect_raster_reader",
        lambda preferred: _reader_status(),
    )
    monkeypatch.setattr(
        "floodguard.theos2_thumbnails._read_thumbnail_rgb",
        lambda path, reader_name, max_size: RGBImage(
            width=2,
            height=2,
            pixels=bytes(
                [
                    255,
                    0,
                    0,
                    0,
                    255,
                    0,
                    0,
                    0,
                    255,
                    255,
                    255,
                    255,
                ]
            ),
        ),
    )

    manifest = write_theos2_true_thumbnails(
        tmp_path,
        _selected_manifest(tmp_path, selected),
        tmp_path / "thumbs",
    )

    row = manifest.iloc[0]
    thumbnail = tmp_path / row["thumbnail_path"]
    assert row["thumbnail_format"] == "png"
    assert row["thumbnail_width"] == 2
    assert row["thumbnail_height"] == 2
    assert row["raster_reader"] == "stub"
    assert thumbnail.exists()
    assert thumbnail.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert thumbnail.stat().st_size < 1000


def _reader_status():
    from floodguard.theos2_thumbnails import RasterReaderStatus

    return RasterReaderStatus(True, "stub", "stub available")


def _selected_manifest(tmp_path: Path, file_name: str) -> pd.DataFrame:
    from floodguard.theos2_readiness import compute_sha256

    return pd.DataFrame(
        [
            {
                "file_name": file_name,
                "source_timestamp": "2025-07-30T03:33:31Z",
                "category": "Disaster",
                "local_path_hint": f"<input_dir>/{file_name}",
                "sha256": compute_sha256(tmp_path / file_name),
                "sha256_status": "recorded",
                "license_status": "user_reported_hackathon_free_use",
                "processing_scope": "theos2_optical_context_preview_only",
                "reference_mask_status": "not_reference_mask",
                "processing_allowed": True,
            }
        ]
    )
