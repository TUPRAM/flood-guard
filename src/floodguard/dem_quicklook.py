"""Optional DEM terrain-context quicklook generation.

DEM quicklooks are small, non-operational terrain previews. They require an
explicitly extracted local DEM TIFF outside the repository and a member-level
SHA-256 checksum before any raster pixels are read.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
import struct
import zlib

import pandas as pd

from floodguard.dem_readiness import compute_sha256

DEM_QUICKLOOK_WARNING = (
    "DEM terrain context only; not flood observation; not flood label; not "
    "reference mask; not an official warning."
)

DEM_QUICKLOOK_COLUMNS: tuple[str, ...] = (
    "source_name",
    "package_name",
    "member_name",
    "package_sha256_prefix",
    "package_sha256_status",
    "member_sha256_prefix",
    "member_sha256_status",
    "local_extracted_path_hint",
    "quicklook_path",
    "quicklook_format",
    "quicklook_width",
    "quicklook_height",
    "quicklook_file_size_bytes",
    "raster_reader",
    "reference_mask_status",
    "flood_observation_status",
    "flood_label_status",
    "processing_scope",
    "warning_text",
    "assumptions",
)

DEM_SELECTED_REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "package_name",
    "member_name",
    "package_sha256",
    "package_sha256_status",
    "member_kind",
    "source_license_status",
    "reference_mask_status",
    "flood_observation_status",
    "flood_label_status",
    "processing_scope",
)


class DEMQuicklookError(ValueError):
    """Raised when DEM quicklook generation is blocked."""


@dataclass(frozen=True)
class RasterReaderStatus:
    """Availability status for optional raster readers."""

    available: bool
    reader_name: str
    message: str


@dataclass(frozen=True)
class RGBImage:
    """Small RGB image container for PNG writing."""

    width: int
    height: int
    pixels: bytes


def detect_raster_reader(preferred: str = "auto") -> RasterReaderStatus:
    """Detect an optional raster reader without importing heavy modules."""

    normalized = preferred.lower()
    if normalized not in {"auto", "rasterio", "gdal"}:
        raise DEMQuicklookError(
            "preferred raster reader must be one of: auto, rasterio, gdal."
        )
    candidates = ("rasterio", "gdal") if normalized == "auto" else (normalized,)
    for candidate in candidates:
        if candidate == "rasterio" and importlib.util.find_spec("rasterio") is not None:
            return RasterReaderStatus(True, "rasterio", "rasterio is available")
        if candidate == "gdal" and importlib.util.find_spec("osgeo") is not None:
            return RasterReaderStatus(True, "gdal", "GDAL is available")
    return RasterReaderStatus(
        False,
        "",
        "No optional raster reader available. Install rasterio or GDAL to generate "
        "DEM terrain-context quicklooks.",
    )


def write_dem_quicklook(
    selected_manifest: str | Path | pd.DataFrame,
    extracted_dem_path: str | Path,
    output_path: str | Path,
    *,
    quicklook_path: str | Path | None = None,
    member_name: str | None = None,
    member_sha256: str | None = None,
    local_extracted_path_hint: str | None = None,
    repo_root: str | Path | None = None,
    preferred_reader: str = "auto",
    max_size: int = 512,
    verify_checksum: bool = True,
) -> Path:
    """Write a small DEM context PNG and its metadata manifest."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise DEMQuicklookError("DEM quicklook manifest output must be CSV.")
    if max_size < 64 or max_size > 2048:
        raise DEMQuicklookError("max_size must be between 64 and 2048 pixels.")

    reader_status = detect_raster_reader(preferred_reader)
    if not reader_status.available:
        raise DEMQuicklookError(reader_status.message)

    source_path = Path(extracted_dem_path)
    _validate_extracted_path(source_path, repo_root)
    row = _select_dem_row(_coerce_frame(selected_manifest), member_name)
    _validate_selected_row(row)
    _validate_member_checksum(
        source_path=source_path,
        member_sha256=member_sha256,
        verify_checksum=verify_checksum,
    )

    image = _read_dem_rgb(source_path, reader_status.reader_name, max_size)
    image_path = Path(quicklook_path) if quicklook_path is not None else target.parent / "dem_quicklook.png"
    _write_png(image_path, image)

    manifest = pd.DataFrame(
        [
            {
                "source_name": row["source_name"],
                "package_name": row["package_name"],
                "member_name": row["member_name"],
                "package_sha256_prefix": str(row["package_sha256"])[:12],
                "package_sha256_status": row["package_sha256_status"],
                "member_sha256_prefix": str(member_sha256)[:12],
                "member_sha256_status": "recorded",
                "local_extracted_path_hint": local_extracted_path_hint
                or f"<external_data_workspace>/{source_path.name}",
                "quicklook_path": _quicklook_manifest_path(target.parent, image_path),
                "quicklook_format": "png",
                "quicklook_width": image.width,
                "quicklook_height": image.height,
                "quicklook_file_size_bytes": image_path.stat().st_size,
                "raster_reader": reader_status.reader_name,
                "reference_mask_status": "not_reference_mask",
                "flood_observation_status": "not_flood_observation",
                "flood_label_status": "not_flood_label",
                "processing_scope": "dem_terrain_context_quicklook_only",
                "warning_text": DEM_QUICKLOOK_WARNING,
                "assumptions": (
                    "Small non-operational DEM terrain-context quicklook; not flood "
                    "observation, not flood label, not reference mask, not an official "
                    "warning; extracted DEM source remains outside Git."
                ),
            }
        ],
        columns=DEM_QUICKLOOK_COLUMNS,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False)
    return target


def _read_dem_rgb(path: Path, reader_name: str, max_size: int) -> RGBImage:
    if reader_name == "rasterio":
        return _read_with_rasterio(path, max_size)
    if reader_name == "gdal":
        return _read_with_gdal(path, max_size)
    raise DEMQuicklookError(f"Unsupported raster reader: {reader_name}")


def _read_with_rasterio(path: Path, max_size: int) -> RGBImage:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as dataset:
        if dataset.count < 1:
            raise DEMQuicklookError(f"DEM source has no raster bands: {path.name}")
        width, height = _fit_size(dataset.width, dataset.height, max_size)
        data = dataset.read(
            1,
            out_shape=(height, width),
            resampling=Resampling.bilinear,
            masked=True,
        )
    return _normalize_grayscale_to_rgb(np.ma.filled(data.astype("float32"), np.nan), width, height)


def _read_with_gdal(path: Path, max_size: int) -> RGBImage:
    import numpy as np
    from osgeo import gdal

    dataset = gdal.Open(str(path))
    if dataset is None:
        raise DEMQuicklookError(f"GDAL could not open DEM source: {path.name}")
    if dataset.RasterCount < 1:
        raise DEMQuicklookError(f"DEM source has no raster bands: {path.name}")
    width, height = _fit_size(dataset.RasterXSize, dataset.RasterYSize, max_size)
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray(
        buf_xsize=width,
        buf_ysize=height,
        resample_alg=gdal.GRIORA_Bilinear,
    )
    nodata = band.GetNoDataValue()
    data = np.asarray(array, dtype="float32")
    if nodata is not None:
        data[data == nodata] = np.nan
    return _normalize_grayscale_to_rgb(data, width, height)


def _normalize_grayscale_to_rgb(data: object, width: int, height: int) -> RGBImage:
    import numpy as np

    array = np.asarray(data, dtype="float32")
    array[~np.isfinite(array)] = np.nan
    if array.shape != (height, width):
        raise DEMQuicklookError("DEM quicklook array shape does not match dimensions.")
    if np.isnan(array).all():
        gray = np.zeros((height, width), dtype="uint8")
    else:
        low = float(np.nanpercentile(array, 2))
        high = float(np.nanpercentile(array, 98))
        if high <= low:
            gray = np.zeros((height, width), dtype="uint8")
        else:
            scaled = np.clip((array - low) / (high - low), 0.0, 1.0)
            scaled = np.nan_to_num(scaled, nan=0.0)
            gray = (scaled * 255).astype("uint8")
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    return RGBImage(width=width, height=height, pixels=rgb.tobytes())


def _write_png(path: Path, image: RGBImage) -> None:
    if len(image.pixels) != image.width * image.height * 3:
        raise DEMQuicklookError("RGB image byte length does not match dimensions.")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + image.pixels[row * image.width * 3 : (row + 1) * image.width * 3]
        for row in range(image.height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=6))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _select_dem_row(frame: pd.DataFrame, member_name: str | None) -> dict[str, object]:
    _require_columns(frame, DEM_SELECTED_REQUIRED_COLUMNS, "selected DEM manifest")
    if member_name is None:
        if len(frame) != 1:
            raise DEMQuicklookError(
                "member_name is required when the selected DEM manifest has multiple rows."
            )
        return frame.iloc[0].to_dict()
    matches = frame[frame["member_name"].astype(str) == member_name]
    if matches.empty:
        raise DEMQuicklookError(f"Selected DEM member is missing from manifest: {member_name}")
    if len(matches) > 1:
        raise DEMQuicklookError(f"Selected DEM member has duplicate rows: {member_name}")
    return matches.iloc[0].to_dict()


def _validate_selected_row(row: dict[str, object]) -> None:
    if row["package_sha256_status"] != "recorded" or not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        str(row.get("package_sha256", "")),
    ):
        raise DEMQuicklookError(
            f"DEM package-level checksum is not recorded: {row['package_name']}"
        )
    if row["member_kind"] != "image_tiff":
        raise DEMQuicklookError(f"Selected DEM member is not a TIFF: {row['member_name']}")
    if row["source_license_status"] != "user_reported_hackathon_free_use":
        raise DEMQuicklookError(
            f"DEM source license status is unresolved: {row['package_name']}"
        )
    if row["reference_mask_status"] != "not_reference_mask":
        raise DEMQuicklookError("DEM quicklook input must not be a reference mask.")
    if row["flood_observation_status"] != "not_flood_observation":
        raise DEMQuicklookError("DEM quicklook input must not be a flood observation.")
    if row["flood_label_status"] != "not_flood_label":
        raise DEMQuicklookError("DEM quicklook input must not be a flood label.")
    if row["processing_scope"] != "dem_terrain_context_readiness_only":
        raise DEMQuicklookError("DEM selected manifest must be terrain-readiness scoped.")


def _validate_extracted_path(path: Path, repo_root: str | Path | None) -> None:
    if not path.exists():
        raise DEMQuicklookError(f"Extracted DEM TIFF path is unresolved or missing: {path}")
    if path.suffix.lower() not in {".tif", ".tiff"}:
        raise DEMQuicklookError("Extracted DEM path must point to a TIFF file.")
    if repo_root is not None and _is_relative_to(path.resolve(), Path(repo_root).resolve()):
        raise DEMQuicklookError("Extracted DEM TIFF must live outside the Git repository.")


def _validate_member_checksum(
    *,
    source_path: Path,
    member_sha256: str | None,
    verify_checksum: bool,
) -> None:
    if not member_sha256 or not re.fullmatch(r"[0-9a-fA-F]{64}", member_sha256):
        raise DEMQuicklookError("DEM member-level SHA-256 checksum is absent.")
    if verify_checksum:
        actual_sha256 = compute_sha256(source_path)
        if actual_sha256.lower() != member_sha256.lower():
            raise DEMQuicklookError("DEM member-level SHA-256 checksum mismatch.")


def _fit_size(width: int, height: int, max_size: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise DEMQuicklookError("Raster width and height must be positive.")
    scale = min(max_size / width, max_size / height, 1.0)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _quicklook_manifest_path(manifest_dir: Path, quicklook_path: Path) -> str:
    try:
        return quicklook_path.relative_to(manifest_dir).as_posix()
    except ValueError:
        if quicklook_path.parent == manifest_dir:
            return quicklook_path.name
        return f"{quicklook_path.parent.name}/{quicklook_path.name}"


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise DEMQuicklookError(f"{label} is missing required columns: {', '.join(missing)}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
