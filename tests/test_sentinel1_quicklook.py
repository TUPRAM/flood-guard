from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.sentinel1_quicklook import (
    RGBImage,
    RasterReaderStatus,
    SENTINEL1_QUICKLOOK_WARNING,
    Sentinel1QuicklookError,
    detect_raster_reader,
    write_sentinel1_quicklooks,
)


def test_detect_raster_reader_reports_missing_optional_reader() -> None:
    status = detect_raster_reader("auto")

    assert status.available in {True, False}
    if not status.available:
        assert "Install rasterio or GDAL" in status.message


def test_quicklook_generation_requires_recorded_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    manifest = _selected_manifest(tmp_path, selected)
    manifest.loc[:, "sha256_status"] = "not_recorded"
    manifest.loc[:, "sha256"] = ""
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(Sentinel1QuicklookError, match="recorded SHA-256"):
        write_sentinel1_quicklooks(tmp_path, manifest, tmp_path / "outputs")


def test_quicklook_generation_requires_resolved_source_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(Sentinel1QuicklookError, match="unresolved or missing"):
        write_sentinel1_quicklooks(
            tmp_path,
            _selected_manifest(tmp_path, selected, source_exists=False),
            tmp_path / "outputs",
        )


def test_quicklook_generation_requires_vv_vh_bands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    manifest = _selected_manifest(tmp_path, selected)
    manifest.loc[:, "band_descriptions"] = "VV"
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(Sentinel1QuicklookError, match="VV\\|VH"):
        write_sentinel1_quicklooks(tmp_path, manifest, tmp_path / "outputs")


def test_quicklook_generation_writes_small_context_pngs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook._read_quicklook_rgb",
        lambda path, band_index, reader_name, max_size: RGBImage(
            width=2,
            height=2,
            pixels=bytes(
                [
                    0,
                    0,
                    0,
                    90,
                    90,
                    90,
                    180,
                    180,
                    180,
                    255,
                    255,
                    255,
                ]
            ),
        ),
    )

    manifest = write_sentinel1_quicklooks(
        tmp_path,
        _selected_manifest(tmp_path, selected),
        tmp_path / "outputs",
        provenance_manifest=_provenance_manifest(selected),
    )

    assert list(manifest["band"]) == ["VV", "VH"]
    assert set(manifest["quicklook_path"]) == {
        "sentinel1_quicklook_vv.png",
        "sentinel1_quicklook_vh.png",
    }
    for row in manifest.to_dict(orient="records"):
        quicklook = tmp_path / "outputs" / row["quicklook_path"]
        assert quicklook.exists()
        assert quicklook.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert quicklook.stat().st_size < 1000
        assert row["quicklook_format"] == "png"
        assert row["quicklook_width"] == 2
        assert row["quicklook_height"] == 2
        assert row["event_timing_status"] == "timing_unresolved"
        assert row["provenance_status"] == "unresolved_placeholder_filename"
        assert row["processing_scope"] == "sentinel1_sar_context_quicklook_only"
        assert row["warning_text"] == SENTINEL1_QUICKLOOK_WARNING
        assert "not flood detection" in row["assumptions"]
    assert not list((tmp_path / "outputs").glob("*.tif"))
    assert not list((tmp_path / "outputs").glob("*.zip"))


def test_quicklook_generation_can_verify_checksum_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    manifest = _selected_manifest(tmp_path, selected)
    manifest.loc[:, "sha256"] = "a" * 64
    monkeypatch.setattr(
        "floodguard.sentinel1_quicklook.detect_raster_reader",
        lambda preferred: _reader_status(),
    )

    with pytest.raises(Sentinel1QuicklookError, match="SHA-256 mismatch"):
        write_sentinel1_quicklooks(
            tmp_path,
            manifest,
            tmp_path / "outputs",
            verify_checksum=True,
        )


def _reader_status() -> RasterReaderStatus:
    return RasterReaderStatus(True, "stub", "stub available")


def _selected_manifest(
    tmp_path: Path,
    file_name: str,
    *,
    source_exists: bool = True,
) -> pd.DataFrame:
    from floodguard.sentinel1_readiness import compute_sha256

    source = tmp_path / file_name
    sha256 = compute_sha256(source) if source_exists else "b" * 64
    return pd.DataFrame(
        [
            {
                "file_name": file_name,
                "local_path_hint": f"<input_dir>/{file_name}",
                "sha256": sha256,
                "sha256_status": "recorded",
                "band_descriptions": "VV|VH",
                "mvp_overlap": "mae_sai_2024_point",
                "event_timing_status": "unresolved_no_acquisition_date",
                "provenance_status": "unresolved_placeholder_filename",
            }
        ]
    )


def _provenance_manifest(file_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": file_name,
                "event_timing_status": "timing_unresolved",
                "provenance_status": "unresolved_placeholder_filename",
            }
        ]
    )
