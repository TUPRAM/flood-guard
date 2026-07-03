from __future__ import annotations

from pathlib import Path
import struct
import zipfile

import pytest

from floodguard.theos2_inventory import (
    THEOS2InventoryError,
    build_theos2_local_manifest,
    parse_theos2_filename,
    parse_tiff_header,
    write_theos2_local_manifest,
)


def test_parse_theos2_filename_extracts_acquisition_and_product_fields() -> None:
    parsed = parse_theos2_filename("IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif")

    assert parsed == {
        "acquisition_date": "20250730",
        "acquisition_time_utc": "033331",
        "processing_level": "ORTHO",
        "sensor_product": "PMS",
        "tile_id": "32",
        "sequence_id": "004",
    }


def test_parse_tiff_header_reads_metadata_without_pixels(tmp_path: Path) -> None:
    tiff_path = tmp_path / "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    _write_minimal_geotiff_header(tiff_path)

    header = parse_tiff_header(tiff_path)

    assert header.tiff_version == "ClassicTIFF"
    assert header.image_width == 20
    assert header.image_height == 10
    assert header.samples_per_pixel == 4
    assert header.bits_per_sample == "16|16|16|16"
    assert header.pixel_size_m == 0.5
    assert header.crs_hint == "WGS84 / UTM Zone 47N"
    assert header.bbox_lon_min is not None
    assert header.bbox_lat_min is not None


def test_build_theos2_manifest_tracks_permission_and_redacts_paths(tmp_path: Path) -> None:
    image_path = tmp_path / "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    _write_minimal_geotiff_header(image_path)
    with zipfile.ZipFile(tmp_path / "THEOS-2 Sample Images-20260620T002637Z-3-017.zip", "w") as archive:
        archive.writestr(
            "THEOS-2 Sample Images/Disaster/"
            "IMG_T2V_20250730033331_ORTHO_PMS_32.tif.aux.xml",
            "<PAMDataset />",
        )

    manifest = build_theos2_local_manifest(tmp_path)

    assert len(manifest) == 2
    image_row = manifest.loc[manifest["entry_kind"] == "image_tiff"].iloc[0]
    zip_row = manifest.loc[manifest["entry_kind"] == "zip_package"].iloc[0]
    assert image_row["local_path_hint"] == "<input_dir>/IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif"
    assert str(tmp_path) not in image_row["local_path_hint"]
    assert image_row["category"] == "Disaster"
    assert bool(image_row["processing_allowed"]) is False
    assert image_row["license_status"] == "user_reported_hackathon_free_use"
    assert "sha256 checksum not recorded" in image_row["reason_blocked"]
    assert zip_row["zip_member_count"] == 1
    assert zip_row["zip_categories"] == "Disaster=1"


def test_write_theos2_manifest_rejects_non_csv_output(tmp_path: Path) -> None:
    with pytest.raises(THEOS2InventoryError, match="CSV"):
        write_theos2_local_manifest(tmp_path, tmp_path / "manifest.json")


def _write_minimal_geotiff_header(path: Path) -> None:
    entries: list[tuple[int, int, int, bytes]] = []
    external = bytearray()

    def add_external(data: bytes) -> int:
        offset = 8 + 2 + 12 * 10 + 4 + len(external)
        external.extend(data)
        return offset

    def pack_entry(tag: int, type_id: int, count: int, value: int | bytes) -> None:
        if isinstance(value, int):
            value_bytes = struct.pack("<I", value)
        else:
            value_bytes = value
        entries.append((tag, type_id, count, value_bytes))

    pack_entry(256, 4, 1, 20)
    pack_entry(257, 4, 1, 10)
    bits_offset = add_external(struct.pack("<HHHH", 16, 16, 16, 16))
    pack_entry(258, 3, 4, bits_offset)
    pack_entry(259, 3, 1, struct.pack("<H", 1) + b"\x00\x00")
    pack_entry(277, 3, 1, struct.pack("<H", 4) + b"\x00\x00")
    pixel_scale_offset = add_external(struct.pack("<ddd", 0.5, 0.5, 0.0))
    pack_entry(33550, 12, 3, pixel_scale_offset)
    tiepoint_offset = add_external(
        struct.pack("<dddddd", 0.0, 0.0, 0.0, 578176.0, 1891344.0, 0.0)
    )
    pack_entry(33922, 12, 6, tiepoint_offset)
    ascii_value = b"PCS Name = WGS_1984_UTM_Zone_47N|\x00"
    ascii_offset = add_external(ascii_value)
    pack_entry(34737, 2, len(ascii_value), ascii_offset)
    # Two filler entries keep the IFD size stable for external offsets.
    pack_entry(262, 3, 1, struct.pack("<H", 1) + b"\x00\x00")
    pack_entry(284, 3, 1, struct.pack("<H", 1) + b"\x00\x00")

    with path.open("wb") as handle:
        handle.write(b"II")
        handle.write(struct.pack("<H", 42))
        handle.write(struct.pack("<I", 8))
        handle.write(struct.pack("<H", len(entries)))
        for tag, type_id, count, value in entries:
            handle.write(struct.pack("<HHI", tag, type_id, count))
            handle.write(value[:4])
        handle.write(struct.pack("<I", 0))
        handle.write(external)
