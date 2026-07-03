from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.theos2_readiness import (
    REQUIRED_LOCAL_MANIFEST_COLUMNS,
    THEOS2ReadinessError,
    build_theos2_selected_file_manifest,
    compute_sha256,
    write_theos2_preview_svgs,
)


def test_build_selected_manifest_hashes_only_selected_files(tmp_path: Path) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    ignored = "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")
    (tmp_path / ignored).write_bytes(b"ignored-theos2-bytes")

    manifest = build_theos2_selected_file_manifest(
        tmp_path,
        _local_manifest([selected, ignored]),
        selected_files=[selected],
    )

    assert len(manifest) == 1
    row = manifest.iloc[0]
    assert row["file_name"] == selected
    assert row["sha256"] == compute_sha256(tmp_path / selected)
    assert row["sha256_status"] == "recorded"
    assert bool(row["processing_allowed"]) is True
    assert row["processing_scope"] == "theos2_optical_context_preview_only"
    assert row["reference_mask_status"] == "not_reference_mask"
    assert row["local_path_hint"] == f"<input_dir>/{selected}"
    assert str(tmp_path) not in row["local_path_hint"]
    assert "Non-operational THEOS-2 optical context only" in row["assumptions"]
    assert row["reason_blocked"] == ""


def test_build_selected_manifest_fails_when_selected_file_missing_from_manifest(
    tmp_path: Path,
) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")

    with pytest.raises(THEOS2ReadinessError, match="missing from local manifest"):
        build_theos2_selected_file_manifest(
            tmp_path,
            _local_manifest([]),
            selected_files=[selected],
        )


def test_build_selected_manifest_fails_when_selected_file_missing_from_disk(
    tmp_path: Path,
) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"

    with pytest.raises(THEOS2ReadinessError, match="missing from input directory"):
        build_theos2_selected_file_manifest(
            tmp_path,
            _local_manifest([selected]),
            selected_files=[selected],
        )


def test_write_preview_requires_processing_allowed(tmp_path: Path) -> None:
    manifest = pd.DataFrame(
        [
            {
                "file_name": "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
                "category": "Disaster",
                "acquisition_date": "20250730",
                "source_timestamp": "2025-07-30T03:33:31Z",
                "bbox_lon_min": 99.7,
                "bbox_lat_min": 16.9,
                "bbox_lon_max": 99.8,
                "bbox_lat_max": 17.1,
                "sha256": "",
                "processing_allowed": False,
                "preview_path": "theos2_previews/theos2_preview_blocked.svg",
                "assumptions": "Non-operational THEOS-2 optical context only",
            }
        ]
    )

    with pytest.raises(THEOS2ReadinessError, match="checksum gate"):
        write_theos2_preview_svgs(manifest, tmp_path)


def test_write_preview_svgs_writes_small_non_operational_cards(tmp_path: Path) -> None:
    selected = "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    (tmp_path / selected).write_bytes(b"selected-theos2-bytes")
    manifest = build_theos2_selected_file_manifest(
        tmp_path,
        _local_manifest([selected]),
        selected_files=[selected],
    )

    written = write_theos2_preview_svgs(manifest, tmp_path / "previews")

    assert len(written) == 1
    svg = written[0].read_text(encoding="utf-8")
    assert written[0].suffix == ".svg"
    assert written[0].stat().st_size < 10_000
    assert "THEOS-2 Optical Context" in svg
    assert selected in svg
    assert "Non-operational THEOS-2 optical context only" in svg
    assert "not flood validation" in svg


def _local_manifest(file_names: list[str]) -> pd.DataFrame:
    rows = []
    for file_name in file_names:
        rows.append(
            {
                "source_name": "THEOS-2 hackathon sample imagery",
                "file_name": file_name,
                "local_path_hint": f"<input_dir>/{file_name}",
                "entry_kind": "image_tiff",
                "category": "Disaster",
                "file_size_bytes": 21,
                "file_size_gb": 0.0,
                "acquisition_date": "20250730",
                "acquisition_time_utc": "033331",
                "processing_level": "ORTHO",
                "sensor_product": "PMS",
                "tile_id": "32",
                "sequence_id": "004",
                "image_width": 20,
                "image_height": 10,
                "samples_per_pixel": 4,
                "bits_per_sample": "16|16|16|16",
                "pixel_size_m": 0.5,
                "crs_hint": "WGS84 / UTM Zone 47N",
                "bbox_lon_min": 99.734272,
                "bbox_lat_min": 16.961463,
                "bbox_lon_max": 99.883844,
                "bbox_lat_max": 17.104638,
                "mvp_overlap": "none_of_current_mvp_points",
                "floodguard_relevance": "THEOS-2 disaster sample",
                "license_status": "user_reported_hackathon_free_use",
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_LOCAL_MANIFEST_COLUMNS)
