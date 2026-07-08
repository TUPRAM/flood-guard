from __future__ import annotations

from pathlib import Path
import struct
import zipfile

import pandas as pd

from floodguard.public_reference_files import (
    inspect_public_reference_zip,
    write_public_reference_file_inspection_manifest,
)


def test_inspect_public_reference_zip_records_shapefile_metadata(tmp_path: Path) -> None:
    zip_path = _write_minimal_shapefile_zip(tmp_path / "candidate.zip")

    frame = inspect_public_reference_zip(
        zip_path,
        local_path_hint="<external_data_workspace>/sentinel_asia/candidate.zip",
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    row = frame.iloc[0]
    assert row["geometry_type"] == "Polygon"
    assert row["crs"] == "GCS_WGS_1984"
    assert bool(row["mae_sai_point_in_bbox"]) is True
    assert bool(row["hat_yai_point_in_bbox"]) is False
    assert row["feature_bbox_count"] == 1
    assert row["mae_sai_review_bbox_feature_count"] == 1
    assert "polygon_record_bboxes_overlap_mae_sai_review_bbox" in row[
        "flood_water_extent_geometry_assessment"
    ]
    assert row["dbf_record_count"] == 2
    assert row["dbf_fields"] == "Id:N10|Area:F13"
    assert row["sha256"]
    assert row["local_path_hint"] == "<external_data_workspace>/sentinel_asia/candidate.zip"
    assert row["can_use_for_ml_labels"] == "not_cleared_for_ml_labels"
    assert bool(row["processing_allowed"]) is False
    assert "license" in row["reason_blocked"]


def test_write_public_reference_file_inspection_manifest_writes_csv(tmp_path: Path) -> None:
    zip_path = _write_minimal_shapefile_zip(tmp_path / "candidate.zip")
    output = tmp_path / "inspection.csv"

    written = write_public_reference_file_inspection_manifest(
        zip_path,
        output,
        local_path_hint="<external_data_workspace>/sentinel_asia/candidate.zip",
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    assert written == output
    rows = pd.read_csv(output)
    assert rows.loc[0, "reference_candidate_status"] == "candidate_geometry_intersects_mae_sai_bbox"
    assert "Thailand_flood.shp" in rows.loc[0, "zip_members"]


def _write_minimal_shapefile_zip(path: Path) -> Path:
    record_content = _polygon_record_content()
    record_header = bytearray(8)
    struct.pack_into(">i", record_header, 0, 1)
    struct.pack_into(">i", record_header, 4, len(record_content) // 2)

    shp_header = bytearray(100)
    struct.pack_into(">i", shp_header, 0, 9994)
    struct.pack_into(">i", shp_header, 24, (len(shp_header) + len(record_header) + len(record_content)) // 2)
    struct.pack_into("<i", shp_header, 28, 1000)
    struct.pack_into("<i", shp_header, 32, 5)
    struct.pack_into("<4d", shp_header, 36, 98.0, 18.0, 101.0, 21.0)

    fields = [
        _dbf_field("Id", "N", 10),
        _dbf_field("Area", "F", 13),
    ]
    header_len = 32 + 32 * len(fields) + 1
    dbf_header = bytearray(header_len)
    dbf_header[0] = 3
    struct.pack_into("<I", dbf_header, 4, 2)
    struct.pack_into("<H", dbf_header, 8, header_len)
    struct.pack_into("<H", dbf_header, 10, 24)
    offset = 32
    for field in fields:
        dbf_header[offset : offset + 32] = field
        offset += 32
    dbf_header[offset] = 13

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Thailand_flood.shp", bytes(shp_header + record_header + record_content))
        archive.writestr("Thailand_flood.prj", 'GEOGCS["GCS_WGS_1984"]')
        archive.writestr("Thailand_flood.dbf", bytes(dbf_header))
    return path


def _polygon_record_content() -> bytearray:
    points = [
        (99.80, 20.40),
        (99.90, 20.40),
        (99.90, 20.50),
        (99.80, 20.50),
        (99.80, 20.40),
    ]
    content = bytearray(44 + 4 + len(points) * 16)
    struct.pack_into("<i", content, 0, 5)
    struct.pack_into("<4d", content, 4, 99.80, 20.40, 99.90, 20.50)
    struct.pack_into("<i", content, 36, 1)
    struct.pack_into("<i", content, 40, len(points))
    struct.pack_into("<i", content, 44, 0)
    offset = 48
    for lon, lat in points:
        struct.pack_into("<2d", content, offset, lon, lat)
        offset += 16
    return content


def _dbf_field(name: str, field_type: str, length: int) -> bytes:
    descriptor = bytearray(32)
    descriptor[: len(name)] = name.encode("ascii")
    descriptor[11] = ord(field_type)
    descriptor[16] = length
    return bytes(descriptor)
