"""Metadata-only inventory helpers for local THEOS-2 sample imagery."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import math
import re
import struct
from typing import BinaryIO
import zipfile

import pandas as pd

THEOS2_FILENAME_PATTERN = re.compile(
    r"IMG_T2V_(?P<date>\d{8})(?P<time>\d{6})_"
    r"(?P<processing_level>[A-Z0-9]+)_"
    r"(?P<sensor_product>[A-Z0-9+]+)_"
    r"(?P<tile_id>[A-Z0-9_]+)"
    r"(?:-(?P<sequence_id>\d+))?",
    re.IGNORECASE,
)

THEOS2_MANIFEST_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "entry_kind",
    "container_name",
    "zip_member_count",
    "zip_categories",
    "category",
    "file_size_bytes",
    "file_size_gb",
    "acquisition_date",
    "acquisition_time_utc",
    "processing_level",
    "sensor_product",
    "tile_id",
    "sequence_id",
    "tiff_version",
    "image_width",
    "image_height",
    "samples_per_pixel",
    "bits_per_sample",
    "compression",
    "pixel_size_m",
    "crs_hint",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "floodguard_relevance",
    "license_status",
    "sha256_status",
    "processing_allowed",
    "reason_blocked",
)

TIFF_TAGS: dict[int, str] = {
    256: "image_width",
    257: "image_height",
    258: "bits_per_sample",
    259: "compression",
    277: "samples_per_pixel",
    33550: "model_pixel_scale",
    33922: "model_tiepoint",
    34737: "geo_ascii_params",
}

TIFF_TYPE_SIZES: dict[int, int] = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    6: 1,
    7: 1,
    8: 2,
    9: 4,
    10: 8,
    11: 4,
    12: 8,
    16: 8,
    17: 8,
    18: 8,
}

MAE_SAI_POINT = (99.88, 20.43)
HAT_YAI_POINT = (100.47, 7.01)


class THEOS2InventoryError(ValueError):
    """Raised when THEOS-2 inventory metadata cannot be parsed safely."""


@dataclass(frozen=True)
class TIFFHeader:
    """Small parsed TIFF header subset. This never includes pixel values."""

    tiff_version: str
    image_width: int | None
    image_height: int | None
    samples_per_pixel: int | None
    bits_per_sample: str
    compression: int | None
    pixel_size_m: float | None
    crs_hint: str
    bbox_lon_min: float | None
    bbox_lat_min: float | None
    bbox_lon_max: float | None
    bbox_lat_max: float | None


def parse_theos2_filename(file_name: str) -> dict[str, str]:
    """Parse THEOS-2 naming metadata from a local file or zip member name."""

    match = THEOS2_FILENAME_PATTERN.search(Path(file_name).name)
    if not match:
        return {
            "acquisition_date": "",
            "acquisition_time_utc": "",
            "processing_level": "",
            "sensor_product": "",
            "tile_id": "",
            "sequence_id": "",
        }
    return {
        "acquisition_date": match.group("date"),
        "acquisition_time_utc": match.group("time"),
        "processing_level": match.group("processing_level").upper(),
        "sensor_product": match.group("sensor_product").upper(),
        "tile_id": match.group("tile_id").upper(),
        "sequence_id": match.group("sequence_id") or "",
    }


def build_theos2_local_manifest(input_dir: str | Path) -> pd.DataFrame:
    """Build a metadata-only manifest for local THEOS-2 sample files."""

    root = Path(input_dir)
    if not root.exists():
        raise THEOS2InventoryError(f"THEOS-2 input directory does not exist: {root}")
    rows: list[dict[str, object]] = []
    category_index = _zip_category_index(root)
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name.startswith("theos-2 sample images-") and lower_name.endswith(".zip"):
            rows.append(_zip_package_row(path, root))
        elif lower_name.startswith("img_t2v_") and _is_theos2_sidecar_or_image(path):
            rows.append(_local_file_row(path, root, category_index))
    return pd.DataFrame(rows, columns=THEOS2_MANIFEST_COLUMNS)


def write_theos2_local_manifest(
    input_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Write the local THEOS-2 metadata-only manifest CSV."""

    manifest = build_theos2_local_manifest(input_dir)
    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise THEOS2InventoryError("THEOS-2 manifest output must be a CSV file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False)
    return target


def parse_tiff_header(path: str | Path) -> TIFFHeader:
    """Parse selected TIFF/GeoTIFF header tags without reading image pixels."""

    with Path(path).open("rb") as handle:
        return _parse_tiff_header(handle)


def _parse_tiff_header(handle: BinaryIO) -> TIFFHeader:
    header = handle.read(16)
    if len(header) < 8:
        raise THEOS2InventoryError("TIFF header is incomplete.")
    if header[:2] == b"II":
        endian = "<"
    elif header[:2] == b"MM":
        endian = ">"
    else:
        raise THEOS2InventoryError("File does not start with a TIFF byte-order marker.")

    version = struct.unpack(endian + "H", header[2:4])[0]
    if version == 43:
        if len(header) < 16:
            raise THEOS2InventoryError("BigTIFF header is incomplete.")
        offset_size, zero = struct.unpack(endian + "HH", header[4:8])
        if offset_size != 8 or zero != 0:
            raise THEOS2InventoryError("Unsupported BigTIFF header layout.")
        ifd_offset = struct.unpack(endian + "Q", header[8:16])[0]
        handle.seek(ifd_offset)
        entry_count = struct.unpack(endian + "Q", handle.read(8))[0]
        bigtiff = True
        entry_size = 20
    elif version == 42:
        ifd_offset = struct.unpack(endian + "I", header[4:8])[0]
        handle.seek(ifd_offset)
        entry_count = struct.unpack(endian + "H", handle.read(2))[0]
        bigtiff = False
        entry_size = 12
    else:
        raise THEOS2InventoryError(f"Unsupported TIFF version: {version}")

    tags: dict[str, object] = {}
    for _ in range(min(int(entry_count), 500)):
        entry = handle.read(entry_size)
        if len(entry) != entry_size:
            break
        if bigtiff:
            tag_id, type_id, count, value_or_offset = struct.unpack(endian + "HHQQ", entry)
            inline_bytes = entry[12:20]
        else:
            tag_id, type_id, count, value_or_offset_32 = struct.unpack(endian + "HHII", entry)
            value_or_offset = value_or_offset_32
            inline_bytes = entry[8:12]
        tag_name = TIFF_TAGS.get(tag_id)
        if tag_name is None:
            continue
        raw = _read_tiff_tag_value(
            handle,
            endian,
            type_id,
            count,
            value_or_offset,
            inline_bytes,
        )
        tags[tag_name] = _decode_tiff_value(raw, endian, type_id, count)

    width = _as_int(tags.get("image_width"))
    height = _as_int(tags.get("image_height"))
    samples = _as_int(tags.get("samples_per_pixel"))
    bit_depth = _format_bits(tags.get("bits_per_sample"))
    pixel_scale = _as_number_list(tags.get("model_pixel_scale"))
    tiepoint = _as_number_list(tags.get("model_tiepoint"))
    pixel_size_m = float(pixel_scale[0]) if pixel_scale else None
    crs_hint = _crs_hint(str(tags.get("geo_ascii_params", "")))
    bbox = _bbox_from_geotiff_tags(width, height, pixel_scale, tiepoint)
    return TIFFHeader(
        tiff_version="BigTIFF" if bigtiff else "ClassicTIFF",
        image_width=width,
        image_height=height,
        samples_per_pixel=samples,
        bits_per_sample=bit_depth,
        compression=_as_int(tags.get("compression")),
        pixel_size_m=pixel_size_m,
        crs_hint=crs_hint,
        bbox_lon_min=bbox[0],
        bbox_lat_min=bbox[1],
        bbox_lon_max=bbox[2],
        bbox_lat_max=bbox[3],
    )


def _local_file_row(
    path: Path,
    root: Path,
    category_index: dict[str, set[str]],
) -> dict[str, object]:
    parsed = parse_theos2_filename(path.name)
    header = _empty_header()
    entry_kind = _entry_kind(path.name)
    if entry_kind == "image_tiff":
        try:
            header = parse_tiff_header(path)
        except THEOS2InventoryError:
            header = _empty_header()
    categories = sorted(category_index.get(_normalized_theos2_key(path.name), set()))
    category = "|".join(categories) if categories else "unclassified_local_file"
    overlap = _mvp_overlap(header)
    row = _base_row(
        file_name=path.name,
        local_path_hint=f"<input_dir>/{path.name}",
        entry_kind=entry_kind,
        container_name="",
        file_size_bytes=path.stat().st_size,
        category=category,
        parsed=parsed,
    )
    row.update(_header_dict(header))
    row["mvp_overlap"] = overlap
    row["floodguard_relevance"] = _relevance(entry_kind, category, overlap)
    return row


def _zip_package_row(path: Path, root: Path) -> dict[str, object]:
    categories: Counter[str] = Counter()
    member_count = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for member_name in archive.namelist():
                member_count += 1
                category = _zip_category(member_name)
                if category:
                    categories[category] += 1
    except zipfile.BadZipFile as exc:
        raise THEOS2InventoryError(f"Invalid THEOS-2 zip package: {path.name}") from exc
    row = _base_row(
        file_name=path.name,
        local_path_hint=f"<input_dir>/{path.name}",
        entry_kind="zip_package",
        container_name="",
        file_size_bytes=path.stat().st_size,
        category="package",
        parsed=parse_theos2_filename(path.name),
    )
    row.update(_header_dict(_empty_header()))
    row["zip_member_count"] = member_count
    row["zip_categories"] = ";".join(
        f"{name}={count}" for name, count in sorted(categories.items())
    )
    row["mvp_overlap"] = "unknown_package_not_georeferenced"
    row["floodguard_relevance"] = (
        "metadata package for THEOS-2 optical context; inspect contained files before use"
    )
    return row


def _base_row(
    file_name: str,
    local_path_hint: str,
    entry_kind: str,
    container_name: str,
    file_size_bytes: int,
    category: str,
    parsed: dict[str, str],
) -> dict[str, object]:
    return {
        "source_name": "THEOS-2 hackathon sample imagery",
        "file_name": file_name,
        "local_path_hint": local_path_hint,
        "entry_kind": entry_kind,
        "container_name": container_name,
        "zip_member_count": "",
        "zip_categories": "",
        "category": category,
        "file_size_bytes": file_size_bytes,
        "file_size_gb": round(file_size_bytes / 1_000_000_000, 3),
        **parsed,
        "license_status": "user_reported_hackathon_free_use",
        "sha256_status": "not_recorded",
        "processing_allowed": False,
        "reason_blocked": (
            "hackathon-provided THEOS-2 samples reported free to use by project owner; "
            "sha256 checksum not recorded; imagery remains outside Git"
        ),
    }


def _header_dict(header: TIFFHeader) -> dict[str, object]:
    return {
        "tiff_version": header.tiff_version,
        "image_width": header.image_width or "",
        "image_height": header.image_height or "",
        "samples_per_pixel": header.samples_per_pixel or "",
        "bits_per_sample": header.bits_per_sample,
        "compression": header.compression or "",
        "pixel_size_m": header.pixel_size_m or "",
        "crs_hint": header.crs_hint,
        "bbox_lon_min": header.bbox_lon_min if header.bbox_lon_min is not None else "",
        "bbox_lat_min": header.bbox_lat_min if header.bbox_lat_min is not None else "",
        "bbox_lon_max": header.bbox_lon_max if header.bbox_lon_max is not None else "",
        "bbox_lat_max": header.bbox_lat_max if header.bbox_lat_max is not None else "",
    }


def _read_tiff_tag_value(
    handle: BinaryIO,
    endian: str,
    type_id: int,
    count: int,
    value_or_offset: int,
    inline_bytes: bytes,
) -> bytes:
    byte_count = TIFF_TYPE_SIZES.get(type_id, 1) * count
    if byte_count <= len(inline_bytes):
        return inline_bytes[:byte_count]
    current = handle.tell()
    handle.seek(value_or_offset)
    raw = handle.read(min(byte_count, 8192))
    handle.seek(current)
    return raw


def _decode_tiff_value(raw: bytes, endian: str, type_id: int, count: int) -> object:
    if type_id == 2:
        return raw.split(b"\x00")[0].decode("utf-8", "replace")
    if type_id in (3, 8):
        length = min(count, len(raw) // 2)
        format_char = "H" if type_id == 3 else "h"
        values = struct.unpack(endian + format_char * length, raw[: length * 2])
        return values[0] if count == 1 else list(values)
    if type_id in (4, 9):
        length = min(count, len(raw) // 4)
        format_char = "I" if type_id == 4 else "i"
        values = struct.unpack(endian + format_char * length, raw[: length * 4])
        return values[0] if count == 1 else list(values)
    if type_id in (16, 17, 18):
        length = min(count, len(raw) // 8)
        format_char = "Q" if type_id in (16, 18) else "q"
        values = struct.unpack(endian + format_char * length, raw[: length * 8])
        return values[0] if count == 1 else list(values)
    if type_id == 12:
        length = min(count, len(raw) // 8)
        values = struct.unpack(endian + "d" * length, raw[: length * 8])
        rounded = [round(value, 10) for value in values]
        return rounded[0] if count == 1 else rounded
    return raw.hex()


def _zip_category_index(root: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for path in sorted(root.glob("THEOS-2 Sample Images-*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                for member_name in archive.namelist():
                    category = _zip_category(member_name)
                    key = _normalized_theos2_key(Path(member_name).name)
                    if category and key:
                        index.setdefault(key, set()).add(category)
        except zipfile.BadZipFile:
            continue
    return index


def _zip_category(member_name: str) -> str:
    parts = member_name.split("/")
    if len(parts) >= 3 and parts[0] == "THEOS-2 Sample Images":
        return parts[1]
    return ""


def _normalized_theos2_key(file_name: str) -> str:
    match = THEOS2_FILENAME_PATTERN.search(file_name)
    if not match:
        return ""
    return (
        f"{match.group('date')}_{match.group('time')}_"
        f"{match.group('processing_level').upper()}_"
        f"{match.group('sensor_product').upper()}_"
        f"{match.group('tile_id').upper()}"
    )


def _entry_kind(file_name: str) -> str:
    lower_name = file_name.lower()
    if lower_name.endswith((".tif", ".tiff")):
        return "image_tiff"
    if lower_name.endswith(".ovr"):
        return "overview"
    if lower_name.endswith(".tfw"):
        return "world_file"
    if lower_name.endswith(".xml"):
        return "xml_sidecar"
    if lower_name.endswith(".imd"):
        return "imd_metadata"
    return "sidecar"


def _is_theos2_sidecar_or_image(path: Path) -> bool:
    lower_name = path.name.lower()
    return lower_name.endswith((".tif", ".tiff", ".ovr", ".tfw", ".xml", ".imd"))


def _empty_header() -> TIFFHeader:
    return TIFFHeader(
        tiff_version="",
        image_width=None,
        image_height=None,
        samples_per_pixel=None,
        bits_per_sample="",
        compression=None,
        pixel_size_m=None,
        crs_hint="",
        bbox_lon_min=None,
        bbox_lat_min=None,
        bbox_lon_max=None,
        bbox_lat_max=None,
    )


def _format_bits(value: object) -> str:
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return "" if value is None else str(value)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _as_number_list(value: object) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value if isinstance(item, (int, float))]
    if isinstance(value, (int, float)):
        return [float(value)]
    return []


def _crs_hint(geo_ascii_params: str) -> str:
    if not geo_ascii_params:
        return ""
    if "WGS_1984_UTM_Zone_47N" in geo_ascii_params:
        return "WGS84 / UTM Zone 47N"
    return geo_ascii_params[:120]


def _bbox_from_geotiff_tags(
    width: int | None,
    height: int | None,
    pixel_scale: Sequence[float],
    tiepoint: Sequence[float],
) -> tuple[float | None, float | None, float | None, float | None]:
    if width is None or height is None or len(pixel_scale) < 2 or len(tiepoint) < 6:
        return None, None, None, None
    min_x = tiepoint[3]
    max_y = tiepoint[4]
    max_x = min_x + width * pixel_scale[0]
    min_y = max_y - height * pixel_scale[1]
    min_lat, min_lon = _utm47n_to_latlon(min_x, min_y)
    max_lat, max_lon = _utm47n_to_latlon(max_x, max_y)
    return (
        round(min_lon, 6),
        round(min_lat, 6),
        round(max_lon, 6),
        round(max_lat, 6),
    )


def _utm47n_to_latlon(easting: float, northing: float) -> tuple[float, float]:
    # WGS84 inverse Transverse Mercator for UTM Zone 47N.
    semi_major = 6378137.0
    flattening = 1 / 298.257223563
    k0 = 0.9996
    eccentricity = math.sqrt(flattening * (2 - flattening))
    e1 = (1 - math.sqrt(1 - eccentricity**2)) / (
        1 + math.sqrt(1 - eccentricity**2)
    )
    x = easting - 500000.0
    m = northing / k0
    mu = m / (
        semi_major
        * (
            1
            - eccentricity**2 / 4
            - 3 * eccentricity**4 / 64
            - 5 * eccentricity**6 / 256
        )
    )
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    eccentricity_prime_sq = eccentricity**2 / (1 - eccentricity**2)
    c1 = eccentricity_prime_sq * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = semi_major / math.sqrt(1 - eccentricity**2 * math.sin(phi1) ** 2)
    r1 = (
        semi_major
        * (1 - eccentricity**2)
        / (1 - eccentricity**2 * math.sin(phi1) ** 2) ** 1.5
    )
    d = x / (n1 * k0)
    latitude = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * eccentricity_prime_sq)
        * d**4
        / 24
        + (
            61
            + 90 * t1
            + 298 * c1
            + 45 * t1**2
            - 252 * eccentricity_prime_sq
            - 3 * c1**2
        )
        * d**6
        / 720
    )
    central_meridian = math.radians(99.0)
    longitude = central_meridian + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (
            5
            - 2 * c1
            + 28 * t1
            - 3 * c1**2
            + 8 * eccentricity_prime_sq
            + 24 * t1**2
        )
        * d**5
        / 120
    ) / math.cos(phi1)
    return math.degrees(latitude), math.degrees(longitude)


def _mvp_overlap(header: TIFFHeader) -> str:
    if None in (
        header.bbox_lon_min,
        header.bbox_lat_min,
        header.bbox_lon_max,
        header.bbox_lat_max,
    ):
        return "unknown_no_bbox"
    bbox = (
        float(header.bbox_lon_min),
        float(header.bbox_lat_min),
        float(header.bbox_lon_max),
        float(header.bbox_lat_max),
    )
    overlaps: list[str] = []
    if _point_in_bbox(MAE_SAI_POINT, bbox):
        overlaps.append("mae_sai_2024_point")
    if _point_in_bbox(HAT_YAI_POINT, bbox):
        overlaps.append("hat_yai_2025_point")
    return "|".join(overlaps) if overlaps else "none_of_current_mvp_points"


def _point_in_bbox(point_lonlat: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    lon, lat = point_lonlat
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _relevance(entry_kind: str, category: str, overlap: str) -> str:
    if overlap in {"mae_sai_2024_point", "hat_yai_2025_point"}:
        return "candidate optical context for current MVP study point after checksum tracking"
    if "Disaster" in category:
        return "THEOS-2 disaster sample; useful for optical context and future optical-water experiments"
    if any(label in category for label in ("LULC", "Agri", "Urban", "Coastal")):
        return "useful for land-cover, exposure, and visual-context methods after checksum tracking"
    if entry_kind == "zip_package":
        return "metadata package for THEOS-2 optical context; inspect contained files before use"
    return "generic THEOS-2 optical sample; not a current Mae Sai/Hat Yai validation input"
