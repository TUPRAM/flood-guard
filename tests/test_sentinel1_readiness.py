from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.sentinel1_readiness import (
    REQUIRED_LIBRARY_COLUMNS,
    Sentinel1ReadinessError,
    build_sentinel1_selected_file_manifest,
    compute_sha256,
    write_sentinel1_selected_file_manifest,
)


def test_build_sentinel1_selected_manifest_records_checksum_and_keeps_blocked(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    ignored = "Sentinel1_Thailand-0000023296-0000000000.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    (tmp_path / ignored).write_bytes(b"ignored-sentinel1-bytes")

    manifest = build_sentinel1_selected_file_manifest(
        tmp_path,
        _local_library([selected, ignored]),
        selected_files=[selected],
    )

    assert len(manifest) == 1
    row = manifest.iloc[0]
    assert row["file_name"] == selected
    assert row["sha256"] == compute_sha256(tmp_path / selected)
    assert row["sha256_status"] == "recorded"
    assert row["raster_width"] == 23296
    assert row["raster_height"] == 23296
    assert row["raster_count"] == 2
    assert row["band_descriptions"] == "VV|VH"
    assert row["crs"] == "EPSG:4326"
    assert row["mvp_overlap"] == "mae_sai_2024_point"
    assert row["source_license_status"] == "user_reported_hackathon_free_use"
    assert row["provenance_status"] == "unresolved_placeholder_filename"
    assert row["event_timing_status"] == "unresolved_no_acquisition_date"
    assert row["reference_mask_status"] == "unresolved"
    assert row["processing_scope"] == "sentinel1_sar_context_readiness_only"
    assert bool(row["processing_allowed"]) is False
    assert "Sentinel-1 provenance unresolved" in row["reason_blocked"]
    assert "event timing unresolved" in row["reason_blocked"]
    assert "reference mask not confirmed" in row["reason_blocked"]
    assert str(tmp_path) not in row["local_path_hint"]
    assert row["local_path_hint"] == f"<input_dir>/{selected}"
    assert "source TIFF remains outside Git" in row["assumptions"]


def test_build_sentinel1_selected_manifest_fails_when_missing_from_library(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")

    with pytest.raises(Sentinel1ReadinessError, match="missing from local data library"):
        build_sentinel1_selected_file_manifest(
            tmp_path,
            _local_library([]),
            selected_files=[selected],
        )


def test_write_sentinel1_selected_manifest_writes_csv_without_copying_source(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    input_dir = tmp_path / "downloads"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / selected).write_bytes(b"selected-sentinel1-bytes")
    library_path = tmp_path / "local_data_library_manifest.csv"
    _local_library([selected]).to_csv(library_path, index=False)

    written = write_sentinel1_selected_file_manifest(
        input_dir=input_dir,
        local_library_path=library_path,
        output_path=output_dir / "sentinel1_selected_file_manifest.csv",
        selected_files=[selected],
    )

    assert written == output_dir / "sentinel1_selected_file_manifest.csv"
    assert written.exists()
    assert not (output_dir / selected).exists()
    assert not list(output_dir.glob("*.tif"))


def test_build_sentinel1_selected_manifest_fails_when_missing_from_disk(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"

    with pytest.raises(Sentinel1ReadinessError, match="missing from input directory"):
        build_sentinel1_selected_file_manifest(
            tmp_path,
            _local_library([selected]),
            selected_files=[selected],
        )


def test_build_sentinel1_selected_manifest_rejects_non_sentinel_group(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    library = _local_library([selected])
    library.loc[:, "library_group"] = "theos2_optical"

    with pytest.raises(Sentinel1ReadinessError, match="not cataloged as Sentinel-1"):
        build_sentinel1_selected_file_manifest(
            tmp_path,
            library,
            selected_files=[selected],
        )


def test_build_sentinel1_selected_manifest_requires_vv_vh_bands(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    library = _local_library([selected])
    library.loc[:, "band_descriptions"] = "VV"

    with pytest.raises(Sentinel1ReadinessError, match="VV\\|VH"):
        build_sentinel1_selected_file_manifest(
            tmp_path,
            library,
            selected_files=[selected],
        )


def test_build_sentinel1_selected_manifest_requires_mae_sai_overlap(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"selected-sentinel1-bytes")
    library = _local_library([selected])
    library.loc[:, "mvp_overlap"] = "none_of_current_mvp_points"

    with pytest.raises(Sentinel1ReadinessError, match="overlap Mae Sai"):
        build_sentinel1_selected_file_manifest(
            tmp_path,
            library,
            selected_files=[selected],
        )


def _local_library(file_names: list[str]) -> pd.DataFrame:
    rows = []
    for file_name in file_names:
        rows.append(
            {
                "source_name": "Hackathon-provided Sentinel-1 Thailand raster",
                "file_name": file_name,
                "local_path_hint": f"<input_dir>/{file_name}",
                "library_group": "sentinel1_sar",
                "candidate_use": (
                    "candidate Mae Sai SAR context or gated baseline input after "
                    "checksum and event-date review"
                ),
                "file_size_bytes": 34,
                "file_size_gb": 0.0,
                "raster_width": 23296,
                "raster_height": 23296,
                "raster_count": 2,
                "raster_dtypes": "float32|float32",
                "band_descriptions": "VV|VH",
                "crs": "EPSG:4326",
                "bbox_lon_min": 97.3436,
                "bbox_lat_min": 14.187003,
                "bbox_lon_max": 103.621746,
                "bbox_lat_max": 20.465149,
                "mvp_overlap": "mae_sai_2024_point",
                "license_status": "user_reported_hackathon_free_use",
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_LIBRARY_COLUMNS)
