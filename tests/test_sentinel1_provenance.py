from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.ingestion import (
    build_ingestion_manifest,
    default_mae_sai_file_manifest_sources,
)
from floodguard.sar_baseline import SARBaselineError, run_gated_real_sar_change_baseline
from floodguard.sentinel1_provenance import (
    SENTINEL1_RESOLVED_COLUMNS,
    Sentinel1ProvenanceError,
    build_sentinel1_local_provenance_report,
    parse_sentinel1_product_name,
    resolve_sentinel1_provenance,
    validate_sentinel1_provenance_ready_for_baseline,
    write_sentinel1_provenance_outputs,
)


def test_parse_canonical_sentinel1_name_extracts_timing_and_product_type() -> None:
    parsed = parse_sentinel1_product_name(
        "S1A_IW_GRDH_1SDV_20240906T113106_20240906T113131_"
        "055544_06C73C_B53D_COG.SAFE"
    )

    assert parsed["parse_status"] == "canonical_sentinel1_product_name"
    assert parsed["platform"] == "S1A"
    assert parsed["product_type"] == "GRDH_1SDV"
    assert parsed["acquisition_datetime"] == "2024-09-06T11:31:06Z"
    assert parsed["relative_orbit"] == "055544"
    assert parsed["product_storage_type"] == "COG"


def test_parse_local_placeholder_name_does_not_infer_acquisition_time() -> None:
    parsed = parse_sentinel1_product_name(
        "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    )

    assert parsed["parse_status"] == "local_tile_placeholder_name"
    assert parsed["acquisition_datetime"] == ""
    assert "placeholder numeric offsets" in parsed["filename_evidence"]


def test_resolve_sentinel1_provenance_keeps_placeholder_file_blocked(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"not-a-real-tiff-but-present")

    resolved = resolve_sentinel1_provenance(
        input_dir=tmp_path,
        selected_manifest=_selected_manifest(selected),
        zip_members=_zip_members(),
        provider_notes=_provider_notes(tmp_path),
    )

    assert list(resolved.columns) == list(SENTINEL1_RESOLVED_COLUMNS)
    row = resolved.iloc[0]
    assert row["file_name"] == selected
    assert row["resolved_product_id"] == "unresolved"
    assert row["acquisition_datetime"] == "unresolved"
    assert row["candidate_role"] == "unresolved"
    assert row["event_timing_status"] == "timing_unresolved"
    assert row["provenance_status"] == "unresolved_placeholder_filename"
    assert row["timing_confidence"] == "low"
    assert row["provenance_confidence"] == "low"
    assert bool(row["processing_allowed"]) is False
    assert "acquisition timing unresolved" in row["still_blocked_reason"]
    assert "reference mask not confirmed" in row["still_blocked_reason"]
    assert "no exact selected-file match" in row["zip_member_evidence"]
    assert "no acquisition date" in row["provider_note_evidence"]


def test_validate_sentinel1_provenance_blocks_unresolved_rows(tmp_path: Path) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"not-a-real-tiff-but-present")
    resolved = resolve_sentinel1_provenance(
        input_dir=tmp_path,
        selected_manifest=_selected_manifest(selected),
        zip_members=_zip_members(),
    )

    with pytest.raises(Sentinel1ProvenanceError, match="missing pre_event_candidate"):
        validate_sentinel1_provenance_ready_for_baseline(resolved)


def test_unresolved_provenance_cannot_be_promoted_into_real_sar_baseline(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"not-a-real-tiff-but-present")
    resolved = resolve_sentinel1_provenance(
        input_dir=tmp_path,
        selected_manifest=_selected_manifest(selected),
        zip_members=_zip_members(),
    )

    with pytest.raises(SARBaselineError, match="Sentinel-1 provenance gates"):
        run_gated_real_sar_change_baseline(
            _sar_pixels(),
            _ready_file_manifest(),
            sentinel1_provenance=resolved,
        )


def test_write_sentinel1_provenance_outputs_writes_csv_and_report(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"not-a-real-tiff-but-present")
    selected_path = tmp_path / "selected.csv"
    members_path = tmp_path / "members.csv"
    _selected_manifest(selected).to_csv(selected_path, index=False)
    _zip_members().to_csv(members_path, index=False)
    output_path = tmp_path / "outputs" / "sentinel1_provenance_resolved_manifest.csv"
    report_path = tmp_path / "docs" / "sentinel1_local_provenance.md"

    written, report = write_sentinel1_provenance_outputs(
        input_dir=tmp_path,
        selected_manifest_path=selected_path,
        output_path=output_path,
        zip_members_path=members_path,
        report_path=report_path,
    )

    assert written == output_path
    assert report == report_path
    assert written.exists()
    assert report_path.exists()
    assert "timing unresolved; processing remains blocked" in report_path.read_text(
        encoding="utf-8"
    )


def test_build_sentinel1_local_provenance_report_mentions_not_real_baseline(
    tmp_path: Path,
) -> None:
    selected = "Sentinel1_Thailand-0000000000-0000000000-002.tif"
    (tmp_path / selected).write_bytes(b"not-a-real-tiff-but-present")
    resolved = resolve_sentinel1_provenance(
        input_dir=tmp_path,
        selected_manifest=_selected_manifest(selected),
        zip_members=_zip_members(),
    )

    report = build_sentinel1_local_provenance_report(resolved)

    assert "not process pixels" in report
    assert "cannot be called pre-event, post-event, or event-window yet" in report
    assert "Task 43 - DEM Readiness Lane" in report


def _selected_manifest(file_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_name": "Hackathon-provided Sentinel-1 Thailand raster",
                "file_name": file_name,
                "local_path_hint": f"<input_dir>/{file_name}",
                "sha256": "a" * 64,
                "sha256_status": "recorded",
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
                "source_license_status": "user_reported_hackathon_free_use",
                "reference_mask_status": "unresolved",
            }
        ]
    )


def _zip_members() -> pd.DataFrame:
    names = [
        "Sentinel1_Thailand-0000023296-0000000000.tif",
        "Sentinel1_Thailand-0000000000-0000023296.tif",
        "Sentinel1_Thailand-0000046592-0000000000.tif",
    ]
    return pd.DataFrame(
        [
            {
                "container_name": "drive-download-20260705T102948Z-3-001.zip",
                "member_name": name,
                "member_kind": "image_tiff",
                "library_group": "sentinel1_sar",
            }
            for name in names
        ]
    )


def _provider_notes(tmp_path: Path) -> Path:
    path = tmp_path / "usage.md"
    path.write_text(
        "The project owner reported hackathon-provided data can be used freely.",
        encoding="utf-8",
    )
    return path


def _ready_file_manifest() -> pd.DataFrame:
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
    return build_ingestion_manifest(source)


def _sar_pixels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pixel_id": "PX-001",
                "row": 0,
                "col": 0,
                "pre_vv_db": -7.0,
                "post_vv_db": -12.0,
                "pre_vh_db": -13.0,
                "post_vh_db": -17.0,
                "reference_flood_extent": 1,
            }
        ]
    )
