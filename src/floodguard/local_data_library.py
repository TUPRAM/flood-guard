"""Metadata-only local data library for hackathon-provided files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile

import pandas as pd

from floodguard.theos2_inventory import (
    HAT_YAI_POINT,
    MAE_SAI_POINT,
    parse_theos2_filename,
    parse_tiff_header,
)

LIBRARY_COLUMNS: tuple[str, ...] = (
    "source_name",
    "file_name",
    "local_path_hint",
    "asset_scope",
    "container_name",
    "entry_kind",
    "library_group",
    "candidate_use",
    "file_size_bytes",
    "file_size_gb",
    "zip_member_count",
    "zip_total_uncompressed_bytes",
    "acquisition_date",
    "acquisition_time_utc",
    "processing_level",
    "sensor_product",
    "tile_id",
    "sequence_id",
    "raster_width",
    "raster_height",
    "raster_count",
    "raster_dtypes",
    "band_descriptions",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "license_status",
    "sha256_status",
    "processing_allowed",
    "reason_blocked",
    "library_notes",
)

ZIP_MEMBER_COLUMNS: tuple[str, ...] = (
    "container_name",
    "member_name",
    "member_path_hint",
    "member_kind",
    "library_group",
    "member_size_bytes",
    "member_size_gb",
    "candidate_use",
    "license_status",
    "sha256_status",
    "processing_allowed",
    "reason_blocked",
)

DEFAULT_LIBRARY_FILES: tuple[str, ...] = (
    "drive-download-20260705T102948Z-3-001.zip",
    "drive-download-20260705T104354Z-3-001.zip",
    "drive-download-20260705T104354Z-3-002.zip",
    "Sentinel1_Thailand-0000000000-0000000000-002.tif",
    "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif",
    "IMG_T2V_20250731035100_ORTHO_PMS_32-003.tif",
    "IMG_T2V_20250731035100_ORTHO_PMS_32-001.tif",
    "IMG_T2V_20241203033748_ORTHO_PMS_32-015.tif",
    "IMG_T2V_20241203033748_ORTHO_PMS_32-021.tif",
    "IMG_T2V_20241203033748_ORTHO_PMS_32_2-013.tif",
    "IMG_T2V_20240821033931_ORTHO_PMS_32-020.tif",
    "IMG_T2V_20240821033931_ORTHO_PMS_32-016.tif",
    "IMG_T2V_20241219034659_ORTHO_PMS_32-024.tif",
    "IMG_T2V_20240131033325_ORTHO_PMS_32_2-008.tif",
    "IMG_T2V_20241012033956_ORTHO_PMS_32_2-025.tif",
    "IMG_T2V_20250603033815_PRIMARY_PMS_32-028.TIF",
    "IMG_T2V_20240131033325_ORTHO_PMS_32-011.tif",
    "IMG_T2V_20250730033331_ORTHO_PMS_32.tif-006.ovr",
    "IMG_T2V_20250731035100_ORTHO_PMS_32.tif-007.ovr",
    "IMG_T2V_20250731035100_ORTHO_PMS_32.tif-005.ovr",
    "THEOS-2 Sample Images-20260620T002637Z-3-027.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-026.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-014.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-002.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-009.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-022.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-019.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-010.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-018.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-012.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-023.zip",
    "THEOS-2 Sample Images-20260620T002637Z-3-017.zip",
)


class LocalDataLibraryError(ValueError):
    """Raised when the local data library cannot be built safely."""


@dataclass(frozen=True)
class RasterMetadata:
    """Small raster metadata subset read without loading full pixel arrays."""

    width: int | str = ""
    height: int | str = ""
    count: int | str = ""
    dtypes: str = ""
    descriptions: str = ""
    crs: str = ""
    bbox_lon_min: float | str = ""
    bbox_lat_min: float | str = ""
    bbox_lon_max: float | str = ""
    bbox_lat_max: float | str = ""


def build_local_data_library(
    input_dir: str | Path,
    file_names: tuple[str, ...] = DEFAULT_LIBRARY_FILES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build metadata-only rows for the requested local files and ZIP members."""

    root = Path(input_dir)
    if not root.exists():
        raise LocalDataLibraryError(f"Input directory does not exist: {root}")
    rows: list[dict[str, object]] = []
    member_rows: list[dict[str, object]] = []
    missing: list[str] = []
    for file_name in file_names:
        path = root / file_name
        if not path.exists():
            missing.append(file_name)
            continue
        rows.append(_local_file_row(path))
        if path.suffix.lower() == ".zip":
            member_rows.extend(_zip_member_rows(path))
    if missing:
        raise LocalDataLibraryError(
            f"Missing requested local data file(s): {', '.join(missing)}"
        )
    return (
        pd.DataFrame(rows, columns=LIBRARY_COLUMNS),
        pd.DataFrame(member_rows, columns=ZIP_MEMBER_COLUMNS),
    )


def write_local_data_library(
    input_dir: str | Path,
    manifest_output_path: str | Path,
    zip_members_output_path: str | Path,
    file_names: tuple[str, ...] = DEFAULT_LIBRARY_FILES,
) -> tuple[Path, Path]:
    """Write metadata-only local data library CSVs."""

    manifest_target = Path(manifest_output_path)
    members_target = Path(zip_members_output_path)
    if manifest_target.suffix.lower() != ".csv" or members_target.suffix.lower() != ".csv":
        raise LocalDataLibraryError("Local data library outputs must be CSV files.")
    manifest, members = build_local_data_library(input_dir, file_names=file_names)
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    members_target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_target, index=False)
    members.to_csv(members_target, index=False)
    return manifest_target, members_target


def _local_file_row(path: Path) -> dict[str, object]:
    stat = path.stat()
    entry_kind = _entry_kind(path.name)
    library_group = _library_group(path.name)
    if entry_kind == "zip_package" and library_group == "unknown_hackathon_local_data":
        library_group = _library_group_from_zip(path)
    parsed = _parsed_filename_metadata(path.name)
    raster = _raster_metadata(path)
    zip_member_count = ""
    zip_total_uncompressed_bytes = ""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            zip_member_count = len(infos)
            zip_total_uncompressed_bytes = sum(info.file_size for info in infos)
    return {
        "source_name": _source_name(library_group),
        "file_name": path.name,
        "local_path_hint": f"<input_dir>/{path.name}",
        "asset_scope": "local_file",
        "container_name": "",
        "entry_kind": entry_kind,
        "library_group": library_group,
        "candidate_use": _candidate_use(library_group, entry_kind, raster),
        "file_size_bytes": stat.st_size,
        "file_size_gb": round(stat.st_size / 1_000_000_000, 3),
        "zip_member_count": zip_member_count,
        "zip_total_uncompressed_bytes": zip_total_uncompressed_bytes,
        **parsed,
        "raster_width": raster.width,
        "raster_height": raster.height,
        "raster_count": raster.count,
        "raster_dtypes": raster.dtypes,
        "band_descriptions": raster.descriptions,
        "crs": raster.crs,
        "bbox_lon_min": raster.bbox_lon_min,
        "bbox_lat_min": raster.bbox_lat_min,
        "bbox_lon_max": raster.bbox_lon_max,
        "bbox_lat_max": raster.bbox_lat_max,
        "mvp_overlap": _mvp_overlap(raster),
        "license_status": "user_reported_hackathon_free_use",
        "sha256_status": "not_recorded",
        "processing_allowed": False,
        "reason_blocked": (
            "metadata-only library row; sha256 checksum not recorded for this "
            "library asset; source file remains outside Git"
        ),
        "library_notes": _library_notes(library_group, entry_kind, raster),
    }


def _zip_member_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_kind = _entry_kind(Path(info.filename).name)
            library_group = _library_group(info.filename)
            rows.append(
                {
                    "container_name": path.name,
                    "member_name": info.filename,
                    "member_path_hint": f"<input_dir>/{path.name}::{info.filename}",
                    "member_kind": member_kind,
                    "library_group": library_group,
                    "member_size_bytes": info.file_size,
                    "member_size_gb": round(info.file_size / 1_000_000_000, 3),
                    "candidate_use": _candidate_use(library_group, member_kind, RasterMetadata()),
                    "license_status": "user_reported_hackathon_free_use",
                    "sha256_status": "not_recorded",
                    "processing_allowed": False,
                    "reason_blocked": (
                        "zip member cataloged without extraction; checksum not recorded "
                        "for member; source package remains outside Git"
                    ),
                }
            )
    return rows


def _raster_metadata(path: Path) -> RasterMetadata:
    if not _looks_like_raster(path.name):
        return RasterMetadata()
    try:
        return _rasterio_metadata(path)
    except Exception:
        try:
            header = parse_tiff_header(path)
        except Exception:
            return RasterMetadata()
        return RasterMetadata(
            width=header.image_width or "",
            height=header.image_height or "",
            count=header.samples_per_pixel or "",
            dtypes=header.bits_per_sample,
            descriptions="",
            crs=header.crs_hint,
            bbox_lon_min=header.bbox_lon_min if header.bbox_lon_min is not None else "",
            bbox_lat_min=header.bbox_lat_min if header.bbox_lat_min is not None else "",
            bbox_lon_max=header.bbox_lon_max if header.bbox_lon_max is not None else "",
            bbox_lat_max=header.bbox_lat_max if header.bbox_lat_max is not None else "",
        )


def _rasterio_metadata(path: Path) -> RasterMetadata:
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as dataset:
        bounds = dataset.bounds
        crs_text = "" if dataset.crs is None else str(dataset.crs)
        if dataset.crs is not None and crs_text.upper() != "EPSG:4326":
            left, bottom, right, top = transform_bounds(
                dataset.crs,
                "EPSG:4326",
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
                densify_pts=21,
            )
        else:
            left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
        descriptions = "|".join("" if value is None else str(value) for value in dataset.descriptions)
        return RasterMetadata(
            width=dataset.width,
            height=dataset.height,
            count=dataset.count,
            dtypes="|".join(str(value) for value in dataset.dtypes),
            descriptions=descriptions,
            crs=crs_text,
            bbox_lon_min=round(float(left), 6),
            bbox_lat_min=round(float(bottom), 6),
            bbox_lon_max=round(float(right), 6),
            bbox_lat_max=round(float(top), 6),
        )


def _parsed_filename_metadata(file_name: str) -> dict[str, str]:
    if "IMG_T2V_" in Path(file_name).name.upper():
        return parse_theos2_filename(file_name)
    return {
        "acquisition_date": "",
        "acquisition_time_utc": "",
        "processing_level": "",
        "sensor_product": "",
        "tile_id": _tile_suffix(file_name),
        "sequence_id": "",
    }


def _tile_suffix(file_name: str) -> str:
    match = re.search(r"Thailand-(?P<tile>\d{10}-\d{10})(?:-\d+)?", file_name)
    return match.group("tile") if match else ""


def _source_name(library_group: str) -> str:
    if library_group == "sentinel1_sar":
        return "Hackathon-provided Sentinel-1 Thailand raster"
    if library_group == "copernicus_dem":
        return "Hackathon-provided Copernicus DEM Thailand raster"
    if library_group == "theos2_optical":
        return "THEOS-2 hackathon sample imagery"
    return "Hackathon-provided local data"


def _library_group(file_name: str) -> str:
    normalized = file_name.lower()
    if "sentinel1_thailand" in normalized:
        return "sentinel1_sar"
    if "copernicusdem_elevation_slope_thailand" in normalized:
        return "copernicus_dem"
    if "theos-2 sample images" in normalized or "img_t2v_" in normalized:
        return "theos2_optical"
    if normalized.endswith(".png"):
        return "documentation_image"
    return "unknown_hackathon_local_data"


def _library_group_from_zip(path: Path) -> str:
    groups: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            group = _library_group(info.filename)
            if group not in {"unknown_hackathon_local_data", "documentation_image"}:
                groups.add(group)
    if len(groups) == 1:
        return next(iter(groups))
    if groups == {"copernicus_dem", "sentinel1_sar"}:
        return "mixed_sar_dem"
    return "unknown_hackathon_local_data"


def _entry_kind(file_name: str) -> str:
    normalized = file_name.lower()
    if normalized.endswith(".zip"):
        return "zip_package"
    if normalized.endswith((".tif", ".tiff")):
        return "image_tiff"
    if normalized.endswith(".ovr"):
        return "overview"
    if normalized.endswith(".png"):
        return "png_image"
    return "file"


def _candidate_use(
    library_group: str,
    entry_kind: str,
    raster: RasterMetadata,
) -> str:
    if library_group == "sentinel1_sar":
        if _mvp_overlap(raster) == "mae_sai_2024_point":
            return "candidate Mae Sai SAR context or gated baseline input after checksum and event-date review"
        return "candidate Sentinel-1 SAR context after extraction and checksum review"
    if library_group == "copernicus_dem":
        return "candidate elevation/slope context for flood false-positive review and exposure explanation"
    if library_group == "theos2_optical":
        return "optical context, thumbnail, and land-cover/exposure support only"
    if library_group == "documentation_image":
        return "documentation screenshot inside provided package; not analytical data"
    return "unclassified hackathon-provided local data; inspect before use"


def _library_notes(
    library_group: str,
    entry_kind: str,
    raster: RasterMetadata,
) -> str:
    if library_group == "sentinel1_sar":
        return (
            "Sentinel-1 file is cataloged as provided data; acquisition timing is "
            "not locked from filename, so it is not yet a real pre/post flood pair."
        )
    if library_group == "copernicus_dem":
        return "DEM/elevation-slope package is context data, not a flood observation or label."
    if library_group == "theos2_optical":
        return "THEOS-2 remains optical context only unless separately selected and checksum-gated."
    if entry_kind == "png_image":
        return "Screenshot member is documentation only."
    return "Cataloged for triage; not approved for processing."


def _looks_like_raster(file_name: str) -> bool:
    normalized = file_name.lower()
    return normalized.endswith((".tif", ".tiff", ".ovr"))


def _mvp_overlap(raster: RasterMetadata) -> str:
    values = (
        raster.bbox_lon_min,
        raster.bbox_lat_min,
        raster.bbox_lon_max,
        raster.bbox_lat_max,
    )
    if any(value == "" for value in values):
        return "unknown_no_bbox"
    bbox = tuple(float(value) for value in values)
    overlaps: list[str] = []
    if _point_in_bbox(MAE_SAI_POINT, bbox):
        overlaps.append("mae_sai_2024_point")
    if _point_in_bbox(HAT_YAI_POINT, bbox):
        overlaps.append("hat_yai_2025_point")
    return "|".join(overlaps) if overlaps else "none_of_current_mvp_points"


def _point_in_bbox(
    point_lonlat: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> bool:
    lon, lat = point_lonlat
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
