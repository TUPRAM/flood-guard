"""Inspect downloaded public reference candidates without committing source files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import struct
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

import pandas as pd

MAE_SAI_POINT = (99.88, 20.43)
HAT_YAI_POINT = (100.47, 7.01)
MAE_SAI_REVIEW_BBOX = (99.72, 20.30, 100.03, 20.56)
DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL = (
    "https://sentinel-asia.org/EO/2024/article20240910TH/MBRSC/"
    "MBRSC_THAILAND_FLOOD-MAP-SHP.zip"
)
DEFAULT_EXTERNAL_DATA_DIR = Path.home() / "Documents" / "FloodGuard_external_data"

PUBLIC_REFERENCE_FILE_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_group",
    "study_area",
    "source_url",
    "selected_reason",
    "local_path_hint",
    "sha256",
    "file_size_bytes",
    "zip_member_count",
    "zip_members",
    "shapefile_name",
    "shapefile_shape_type",
    "geometry_type",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mae_sai_point_in_bbox",
    "hat_yai_point_in_bbox",
    "feature_bbox_count",
    "mae_sai_review_bbox",
    "mae_sai_review_bbox_feature_count",
    "dbf_record_count",
    "dbf_fields",
    "flood_water_extent_evidence",
    "flood_water_extent_geometry_assessment",
    "reference_candidate_status",
    "can_use_for_validation",
    "can_use_for_ml_labels",
    "processing_allowed",
    "reason_blocked",
    "next_action",
    "retrieved_at_utc",
)


class PublicReferenceFileError(ValueError):
    """Raised when a public reference file cannot be safely inspected."""


@dataclass(frozen=True)
class ShapefileHeader:
    """Minimal shapefile metadata parsed from the `.shp` and `.dbf` headers."""

    shapefile_name: str
    shape_type: int
    geometry_type: str
    bbox: tuple[float, float, float, float]
    crs: str
    dbf_record_count: int | str
    dbf_fields: str
    feature_bbox_count: int
    mae_sai_review_bbox_feature_count: int


def download_public_reference_candidate(
    url: str = DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
) -> Path:
    """Download one public candidate ZIP into an external data workspace."""

    target_dir = Path(external_data_dir) / "sentinel_asia"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = Path(urlparse(url).path).name
    if not file_name.lower().endswith(".zip"):
        raise PublicReferenceFileError("Public reference candidate must be a ZIP file.")
    target = target_dir / file_name
    request = Request(url, headers={"User-Agent": "FloodGuard-public-reference/0.1"})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - public URL
        target.write_bytes(response.read())
    return target


def inspect_public_reference_zip(
    zip_path: str | Path,
    *,
    source_url: str = DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL,
    local_path_hint: str | None = None,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Inspect a public shapefile ZIP and return one manifest row."""

    path = Path(zip_path)
    if not path.exists():
        raise PublicReferenceFileError(f"Reference ZIP does not exist: {path}")
    if path.suffix.lower() != ".zip":
        raise PublicReferenceFileError("Reference candidate must be a ZIP file.")

    with zipfile.ZipFile(path) as archive:
        members = [info.filename for info in archive.infolist() if not info.is_dir()]
        header = _read_first_shapefile_header(archive, members)

    sha256 = _sha256(path)
    bbox = header.bbox
    mae_sai_overlap = _point_in_bbox(MAE_SAI_POINT, bbox)
    hat_yai_overlap = _point_in_bbox(HAT_YAI_POINT, bbox)
    flood_evidence = _flood_evidence(path.name, members, header)
    geometry_assessment = _geometry_assessment(mae_sai_overlap, header)
    status = (
        "candidate_geometry_intersects_mae_sai_bbox"
        if mae_sai_overlap
        and header.mae_sai_review_bbox_feature_count > 0
        and "flood" in flood_evidence.lower()
        else "candidate_geometry_needs_manual_review"
    )
    row = {
        "source_name": "Sentinel Asia Northern Thailand 2024 MBRSC flood shapefile",
        "source_group": "sentinel_asia_product",
        "study_area": "Chiang Rai / Mae Sai 2024",
        "source_url": source_url,
        "selected_reason": (
            "Most promising public Sentinel Asia row because it is the only scraped "
            "shapefile ZIP candidate and its filename indicates flood-map geometry."
        ),
        "local_path_hint": local_path_hint or f"<external_data_workspace>/sentinel_asia/{path.name}",
        "sha256": sha256,
        "file_size_bytes": path.stat().st_size,
        "zip_member_count": len(members),
        "zip_members": "|".join(members),
        "shapefile_name": header.shapefile_name,
        "shapefile_shape_type": header.shape_type,
        "geometry_type": header.geometry_type,
        "crs": header.crs,
        "bbox_lon_min": round(bbox[0], 8),
        "bbox_lat_min": round(bbox[1], 8),
        "bbox_lon_max": round(bbox[2], 8),
        "bbox_lat_max": round(bbox[3], 8),
        "mae_sai_point_in_bbox": mae_sai_overlap,
        "hat_yai_point_in_bbox": hat_yai_overlap,
        "feature_bbox_count": header.feature_bbox_count,
        "mae_sai_review_bbox": ",".join(str(value) for value in MAE_SAI_REVIEW_BBOX),
        "mae_sai_review_bbox_feature_count": header.mae_sai_review_bbox_feature_count,
        "dbf_record_count": header.dbf_record_count,
        "dbf_fields": header.dbf_fields,
        "flood_water_extent_evidence": flood_evidence,
        "flood_water_extent_geometry_assessment": geometry_assessment,
        "reference_candidate_status": status,
        "can_use_for_validation": "candidate_after_geometry_quality_and_terms_review",
        "can_use_for_ml_labels": "not_cleared_for_ml_labels",
        "processing_allowed": False,
        "reason_blocked": (
            "public candidate geometry inspected, but product-level license, "
            "redistribution status, geometry quality, and ML-label terms are not cleared"
        ),
        "next_action": (
            "inspect geometry visually/outside Git, confirm product terms, then update "
            "Mae Sai file manifest gates before real baseline processing"
        ),
        "retrieved_at_utc": retrieved_at_utc
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    return pd.DataFrame([row], columns=PUBLIC_REFERENCE_FILE_COLUMNS)


def write_public_reference_file_inspection_manifest(
    zip_path: str | Path,
    output_path: str | Path,
    *,
    source_url: str = DEFAULT_SENTINEL_ASIA_SHAPEFILE_URL,
    local_path_hint: str | None = None,
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write the public reference file inspection manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise PublicReferenceFileError("File inspection manifest must be CSV.")
    frame = inspect_public_reference_zip(
        zip_path,
        source_url=source_url,
        local_path_hint=local_path_hint,
        retrieved_at_utc=retrieved_at_utc,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def _read_first_shapefile_header(
    archive: zipfile.ZipFile,
    members: list[str],
) -> ShapefileHeader:
    shp_members = [member for member in members if member.lower().endswith(".shp")]
    if not shp_members:
        raise PublicReferenceFileError("ZIP does not contain a .shp member.")
    shp_name = shp_members[0]
    data = archive.read(shp_name)
    if len(data) < 100:
        raise PublicReferenceFileError("Shapefile header is incomplete.")
    file_code = struct.unpack(">i", data[0:4])[0]
    if file_code != 9994:
        raise PublicReferenceFileError("Invalid shapefile file code.")
    shape_type = struct.unpack("<i", data[32:36])[0]
    bbox = struct.unpack("<4d", data[36:68])
    base = str(Path(shp_name).with_suffix(""))
    prj = _read_text_member(archive, members, base + ".prj")
    dbf = _read_dbf_metadata(archive, members, base + ".dbf")
    feature_bboxes = _read_shape_record_bboxes(data)
    mae_sai_bbox_matches = sum(
        1 for feature_bbox in feature_bboxes if _bbox_intersects(feature_bbox, MAE_SAI_REVIEW_BBOX)
    )
    return ShapefileHeader(
        shapefile_name=shp_name,
        shape_type=shape_type,
        geometry_type=_shape_type_name(shape_type),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        crs=_crs_summary(prj),
        dbf_record_count=dbf[0],
        dbf_fields=dbf[1],
        feature_bbox_count=len(feature_bboxes),
        mae_sai_review_bbox_feature_count=mae_sai_bbox_matches,
    )


def _read_shape_record_bboxes(data: bytes) -> list[tuple[float, float, float, float]]:
    """Read polygon/polyline record bounding boxes without decoding geometry fully."""

    bboxes: list[tuple[float, float, float, float]] = []
    offset = 100
    while offset + 12 <= len(data):
        content_words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        content_bytes = content_words * 2
        record_start = offset + 8
        record_end = record_start + content_bytes
        if content_bytes < 4 or record_end > len(data):
            break
        shape_type = struct.unpack("<i", data[record_start : record_start + 4])[0]
        if shape_type in {3, 5, 13, 15, 23, 25} and content_bytes >= 36:
            bboxes.append(struct.unpack("<4d", data[record_start + 4 : record_start + 36]))
        offset = record_end
    return [(float(xmin), float(ymin), float(xmax), float(ymax)) for xmin, ymin, xmax, ymax in bboxes]


def _read_text_member(
    archive: zipfile.ZipFile,
    members: list[str],
    member_name: str,
) -> str:
    match = next((member for member in members if member.lower() == member_name.lower()), "")
    if not match:
        return ""
    return archive.read(match).decode("utf-8", errors="replace")


def _read_dbf_metadata(
    archive: zipfile.ZipFile,
    members: list[str],
    member_name: str,
) -> tuple[int | str, str]:
    match = next((member for member in members if member.lower() == member_name.lower()), "")
    if not match:
        return "", ""
    data = archive.read(match)
    if len(data) < 32:
        return "", ""
    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    fields: list[str] = []
    offset = 32
    while offset + 32 <= header_length - 1:
        descriptor = data[offset : offset + 32]
        if descriptor[0] == 13:
            break
        name = descriptor[:11].split(b"\x00", maxsplit=1)[0].decode(
            "ascii",
            errors="replace",
        )
        field_type = chr(descriptor[11])
        length = descriptor[16]
        fields.append(f"{name}:{field_type}{length}")
        offset += 32
    return record_count, "|".join(fields)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shape_type_name(shape_type: int) -> str:
    names = {
        0: "Null Shape",
        1: "Point",
        3: "PolyLine",
        5: "Polygon",
        8: "MultiPoint",
        11: "PointZ",
        13: "PolyLineZ",
        15: "PolygonZ",
        18: "MultiPointZ",
        21: "PointM",
        23: "PolyLineM",
        25: "PolygonM",
        28: "MultiPointM",
    }
    return names.get(shape_type, f"Unknown({shape_type})")


def _crs_summary(prj: str) -> str:
    if not prj:
        return "missing_prj"
    compact = " ".join(prj.split())
    if "WGS_1984" in compact or "WGS 84" in compact:
        return "GCS_WGS_1984"
    return compact[:180]


def _point_in_bbox(
    point: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> bool:
    lon, lat = point
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _bbox_intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_min_lon, first_min_lat, first_max_lon, first_max_lat = first
    second_min_lon, second_min_lat, second_max_lon, second_max_lat = second
    return not (
        first_max_lon < second_min_lon
        or first_min_lon > second_max_lon
        or first_max_lat < second_min_lat
        or first_min_lat > second_max_lat
    )


def _flood_evidence(
    package_name: str,
    members: list[str],
    header: ShapefileHeader,
) -> str:
    tokens = " ".join([package_name, *members, header.dbf_fields]).lower()
    evidence: list[str] = []
    if "flood" in tokens:
        evidence.append("filename/member names include flood")
    if header.geometry_type in {"Polygon", "PolygonZ", "PolygonM"}:
        evidence.append("geometry is polygonal")
    if str(header.dbf_record_count).isdigit():
        evidence.append(f"dbf has {header.dbf_record_count} records")
    return "; ".join(evidence) if evidence else "no explicit flood evidence in headers"


def _geometry_assessment(mae_sai_overlap: bool, header: ShapefileHeader) -> str:
    if not mae_sai_overlap:
        return "shapefile_bbox_does_not_cover_mae_sai_point"
    if header.mae_sai_review_bbox_feature_count > 0:
        return (
            "polygon_record_bboxes_overlap_mae_sai_review_bbox; inspect geometry "
            "quality and terms before validation"
        )
    return "overall_bbox_covers_mae_sai_but_no_record_bbox_overlap_detected"
