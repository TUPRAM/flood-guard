"""Optional raster-backed THEOS-2 thumbnail generation.

This module is intentionally optional. It imports raster readers only inside
reader-specific functions, so the main FloodGuard package does not depend on
GDAL or rasterio.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
import struct
import zlib

import pandas as pd

from floodguard.theos2_readiness import compute_sha256

THUMBNAIL_MANIFEST_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "license_status",
    "processing_scope",
    "reference_mask_status",
    "processing_allowed",
    "thumbnail_path",
    "thumbnail_format",
    "thumbnail_width",
    "thumbnail_height",
    "raster_reader",
    "assumptions",
)

THUMBNAIL_REQUIRED_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "license_status",
    "processing_scope",
    "reference_mask_status",
    "processing_allowed",
)


class THEOS2ThumbnailError(ValueError):
    """Raised when THEOS-2 thumbnail generation is not permitted or possible."""


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
        raise THEOS2ThumbnailError(
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
        "true THEOS-2 thumbnails; metadata/SVG previews remain available.",
    )


def write_theos2_true_thumbnails(
    input_dir: str | Path,
    selected_manifest: str | Path | pd.DataFrame,
    output_dir: str | Path,
    *,
    preferred_reader: str = "auto",
    image_format: str = "png",
    max_size: int = 512,
    verify_checksum: bool = False,
) -> pd.DataFrame:
    """Write small true thumbnails for checksum-backed selected THEOS-2 rows."""

    if max_size < 64 or max_size > 2048:
        raise THEOS2ThumbnailError("max_size must be between 64 and 2048 pixels.")
    if image_format.lower() != "png":
        raise THEOS2ThumbnailError("Only PNG thumbnails are currently supported.")

    reader_status = detect_raster_reader(preferred_reader)
    if not reader_status.available:
        raise THEOS2ThumbnailError(reader_status.message)

    root = Path(input_dir)
    if not root.exists():
        raise THEOS2ThumbnailError(f"THEOS-2 input directory does not exist: {root}")
    frame = _coerce_frame(selected_manifest)
    _require_columns(frame, THUMBNAIL_REQUIRED_COLUMNS)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        _validate_selected_row(row)
        source_path = root / str(row["file_name"])
        if not source_path.exists():
            raise THEOS2ThumbnailError(
                f"Selected THEOS-2 source file does not exist: {row['file_name']}"
            )
        if verify_checksum:
            actual_sha256 = compute_sha256(source_path)
            if actual_sha256.lower() != str(row["sha256"]).lower():
                raise THEOS2ThumbnailError(
                    f"SHA-256 mismatch for selected THEOS-2 file: {row['file_name']}"
                )

        image = _read_thumbnail_rgb(source_path, reader_status.reader_name, max_size)
        thumbnail_path = target_dir / f"theos2_thumbnail_{_safe_stem(str(row['file_name']))}.png"
        _write_png(thumbnail_path, image)
        rows.append(
            {
                "file_name": row["file_name"],
                "source_timestamp": row["source_timestamp"],
                "category": row["category"],
                "local_path_hint": row["local_path_hint"],
                "sha256": row["sha256"],
                "sha256_status": row["sha256_status"],
                "license_status": row["license_status"],
                "processing_scope": row["processing_scope"],
                "reference_mask_status": row["reference_mask_status"],
                "processing_allowed": True,
                "thumbnail_path": f"{target_dir.name}/{thumbnail_path.name}",
                "thumbnail_format": "png",
                "thumbnail_width": image.width,
                "thumbnail_height": image.height,
                "raster_reader": reader_status.reader_name,
                "assumptions": (
                    "Small non-operational THEOS-2 optical thumbnail; not flood "
                    "validation; source imagery remains outside Git"
                ),
            }
        )
    return pd.DataFrame(rows, columns=THUMBNAIL_MANIFEST_COLUMNS)


def write_theos2_thumbnail_manifest(
    input_dir: str | Path,
    selected_manifest_path: str | Path,
    thumbnail_dir: str | Path,
    output_path: str | Path,
    *,
    preferred_reader: str = "auto",
    max_size: int = 512,
    verify_checksum: bool = False,
) -> Path:
    """Write true PNG thumbnails and a thumbnail manifest CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise THEOS2ThumbnailError("THEOS-2 thumbnail manifest output must be CSV.")
    manifest = write_theos2_true_thumbnails(
        input_dir=input_dir,
        selected_manifest=selected_manifest_path,
        output_dir=thumbnail_dir,
        preferred_reader=preferred_reader,
        max_size=max_size,
        verify_checksum=verify_checksum,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False)
    return target


def _read_thumbnail_rgb(path: Path, reader_name: str, max_size: int) -> RGBImage:
    if reader_name == "rasterio":
        return _read_with_rasterio(path, max_size)
    if reader_name == "gdal":
        return _read_with_gdal(path, max_size)
    raise THEOS2ThumbnailError(f"Unsupported raster reader: {reader_name}")


def _read_with_rasterio(path: Path, max_size: int) -> RGBImage:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as dataset:
        window = _valid_rasterio_window(dataset, max_size)
        width, height = _fit_size(int(window.width), int(window.height), max_size)
        indexes = _rasterio_rgb_indexes(dataset)
        data = dataset.read(
            indexes,
            window=window,
            out_shape=(len(indexes), height, width),
            resampling=Resampling.bilinear,
            masked=True,
        )
    return _normalize_to_rgb(np.ma.filled(data.astype("float32"), np.nan), width, height)


def _read_with_gdal(path: Path, max_size: int) -> RGBImage:
    import numpy as np
    from osgeo import gdal

    dataset = gdal.Open(str(path))
    if dataset is None:
        raise THEOS2ThumbnailError(f"GDAL could not open THEOS-2 source: {path.name}")
    width, height = _fit_size(dataset.RasterXSize, dataset.RasterYSize, max_size)
    band_count = min(dataset.RasterCount, 3)
    if band_count <= 0:
        raise THEOS2ThumbnailError(f"THEOS-2 source has no raster bands: {path.name}")
    bands = []
    indexes = [3, 2, 1] if band_count >= 3 else list(range(1, band_count + 1))
    for index in indexes:
        band = dataset.GetRasterBand(index)
        array = band.ReadAsArray(
            buf_xsize=width,
            buf_ysize=height,
            resample_alg=gdal.GRIORA_Bilinear,
        )
        nodata = band.GetNoDataValue()
        if nodata is not None:
            array = np.asarray(array, dtype="float32")
            array[array == nodata] = np.nan
        bands.append(array)
    data = np.stack(bands, axis=0)
    return _normalize_to_rgb(data, width, height)


def _valid_rasterio_window(dataset: object, max_size: int) -> object:
    import numpy as np
    from rasterio.enums import Resampling
    from rasterio.windows import Window

    sample_width, sample_height = _fit_size(dataset.width, dataset.height, max_size)
    mask = dataset.read_masks(
        1,
        out_shape=(sample_height, sample_width),
        resampling=Resampling.nearest,
    )
    valid_rows, valid_cols = np.where(mask > 0)
    if valid_rows.size == 0 or valid_cols.size == 0:
        return Window(0, 0, dataset.width, dataset.height)
    scale_x = dataset.width / sample_width
    scale_y = dataset.height / sample_height
    col_off = max(0, int(valid_cols.min() * scale_x) - 2)
    row_off = max(0, int(valid_rows.min() * scale_y) - 2)
    col_stop = min(dataset.width, int((valid_cols.max() + 1) * scale_x) + 2)
    row_stop = min(dataset.height, int((valid_rows.max() + 1) * scale_y) + 2)
    return Window(col_off, row_off, max(1, col_stop - col_off), max(1, row_stop - row_off))


def _rasterio_rgb_indexes(dataset: object) -> list[int]:
    try:
        names = [str(value).lower() for value in dataset.colorinterp]
    except AttributeError:
        names = []
    if {"red", "green", "blue"}.issubset(set(names)):
        return [
            names.index("red") + 1,
            names.index("green") + 1,
            names.index("blue") + 1,
        ]
    if dataset.count >= 3:
        return [3, 2, 1]
    return [1]


def _normalize_to_rgb(data: object, width: int, height: int) -> RGBImage:
    import numpy as np

    array = np.asarray(data, dtype="float32")
    if array.ndim == 2:
        array = array.reshape((1, array.shape[0], array.shape[1]))
    if array.shape[0] == 1:
        array = np.repeat(array, 3, axis=0)
    if array.shape[0] > 3:
        array = array[:3, :, :]
    rgb = np.zeros((height, width, 3), dtype="uint8")
    for channel in range(3):
        band = np.asarray(array[channel], dtype="float32")
        band[~np.isfinite(band)] = np.nan
        if np.isnan(band).all():
            scaled = np.zeros_like(band, dtype="uint8")
        else:
            low = float(np.nanpercentile(band, 2))
            high = float(np.nanpercentile(band, 98))
            if high <= low:
                scaled = np.zeros_like(band, dtype="uint8")
            else:
                scaled = np.clip((band - low) / (high - low), 0.0, 1.0)
                scaled = np.nan_to_num(scaled, nan=0.0)
                scaled = (scaled * 255).astype("uint8")
        rgb[:, :, channel] = scaled
    return RGBImage(width=width, height=height, pixels=rgb.tobytes())


def _write_png(path: Path, image: RGBImage) -> None:
    if len(image.pixels) != image.width * image.height * 3:
        raise THEOS2ThumbnailError("RGB image byte length does not match dimensions.")
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


def _validate_selected_row(row: dict[str, object]) -> None:
    if not _truthy(row["processing_allowed"]):
        raise THEOS2ThumbnailError(
            f"THEOS-2 row is not processing allowed: {row['file_name']}"
        )
    if row["sha256_status"] != "recorded" or not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        str(row["sha256"]),
    ):
        raise THEOS2ThumbnailError(
            f"THEOS-2 row is missing a recorded SHA-256: {row['file_name']}"
        )
    if row["processing_scope"] != "theos2_optical_context_preview_only":
        raise THEOS2ThumbnailError(
            f"THEOS-2 processing scope is not preview-only: {row['file_name']}"
        )
    if row["reference_mask_status"] != "not_reference_mask":
        raise THEOS2ThumbnailError(
            f"THEOS-2 row must not be treated as a reference mask: {row['file_name']}"
        )


def _fit_size(width: int, height: int, max_size: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise THEOS2ThumbnailError("Raster width and height must be positive.")
    scale = min(max_size / width, max_size / height, 1.0)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(frame: pd.DataFrame, required_columns: tuple[str, ...]) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise THEOS2ThumbnailError(
            f"Selected THEOS-2 manifest is missing required columns: {', '.join(missing)}"
        )


def _safe_stem(file_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(file_name).stem)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
