"""Optional Sentinel-1 SAR context quicklook generation.

This module writes small, non-operational PNG quicklooks only after the
selected Sentinel-1 manifest records a SHA-256 checksum. It does not authorize
real flood detection, validation, or official warning use.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
import struct
import zlib

import pandas as pd

from floodguard.sentinel1_readiness import compute_sha256

SENTINEL1_QUICKLOOK_WARNING = (
    "SAR context only; not flood detection; not validation; not an official "
    "warning; event timing unresolved unless proven otherwise."
)

SENTINEL1_QUICKLOOK_COLUMNS: tuple[str, ...] = (
    "file_name",
    "sha256_prefix",
    "sha256_status",
    "mvp_overlap",
    "event_timing_status",
    "provenance_status",
    "band",
    "band_description",
    "quicklook_path",
    "quicklook_format",
    "quicklook_width",
    "quicklook_height",
    "quicklook_file_size_bytes",
    "raster_reader",
    "processing_scope",
    "warning_text",
    "assumptions",
)

SENTINEL1_SELECTED_REQUIRED_COLUMNS: tuple[str, ...] = (
    "file_name",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "band_descriptions",
    "mvp_overlap",
)


class Sentinel1QuicklookError(ValueError):
    """Raised when Sentinel-1 quicklook generation is blocked."""


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
        raise Sentinel1QuicklookError(
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
        "Sentinel-1 SAR context quicklooks.",
    )


def write_sentinel1_quicklooks(
    input_dir: str | Path,
    selected_manifest: str | Path | pd.DataFrame,
    output_dir: str | Path,
    *,
    provenance_manifest: str | Path | pd.DataFrame | None = None,
    preferred_reader: str = "auto",
    max_size: int = 512,
    verify_checksum: bool = False,
) -> pd.DataFrame:
    """Write small Sentinel-1 VV/VH context quicklooks from gated local files."""

    if max_size < 64 or max_size > 2048:
        raise Sentinel1QuicklookError("max_size must be between 64 and 2048 pixels.")

    reader_status = detect_raster_reader(preferred_reader)
    if not reader_status.available:
        raise Sentinel1QuicklookError(reader_status.message)

    root = Path(input_dir)
    if not root.exists():
        raise Sentinel1QuicklookError(f"Sentinel-1 input directory does not exist: {root}")

    selected = _coerce_frame(selected_manifest)
    _require_columns(
        selected,
        SENTINEL1_SELECTED_REQUIRED_COLUMNS,
        "selected Sentinel-1 manifest",
    )
    provenance = _optional_frame(provenance_manifest)

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    one_source = len(selected) == 1
    for selected_row in selected.to_dict(orient="records"):
        _validate_selected_row(selected_row)
        file_name = str(selected_row["file_name"])
        source_path = root / file_name
        if not source_path.exists():
            raise Sentinel1QuicklookError(
                f"Selected Sentinel-1 source path is unresolved or missing: {file_name}"
            )
        if verify_checksum:
            actual_sha256 = compute_sha256(source_path)
            if actual_sha256.lower() != str(selected_row["sha256"]).lower():
                raise Sentinel1QuicklookError(
                    f"SHA-256 mismatch for selected Sentinel-1 file: {file_name}"
                )

        provenance_row = _matching_provenance_row(file_name, provenance)
        for band, index in _vv_vh_band_indexes(str(selected_row["band_descriptions"])):
            image = _read_quicklook_rgb(
                source_path,
                band_index=index,
                reader_name=reader_status.reader_name,
                max_size=max_size,
            )
            output_name = _quicklook_file_name(file_name, band, one_source=one_source)
            quicklook_file = target_dir / output_name
            _write_png(quicklook_file, image)
            rows.append(
                {
                    "file_name": file_name,
                    "sha256_prefix": str(selected_row["sha256"])[:12],
                    "sha256_status": selected_row["sha256_status"],
                    "mvp_overlap": selected_row["mvp_overlap"],
                    "event_timing_status": _event_timing_status(
                        selected_row,
                        provenance_row,
                    ),
                    "provenance_status": _provenance_status(
                        selected_row,
                        provenance_row,
                    ),
                    "band": band,
                    "band_description": band,
                    "quicklook_path": _quicklook_manifest_path(target_dir, quicklook_file),
                    "quicklook_format": "png",
                    "quicklook_width": image.width,
                    "quicklook_height": image.height,
                    "quicklook_file_size_bytes": quicklook_file.stat().st_size,
                    "raster_reader": reader_status.reader_name,
                    "processing_scope": "sentinel1_sar_context_quicklook_only",
                    "warning_text": SENTINEL1_QUICKLOOK_WARNING,
                    "assumptions": (
                        "Small non-operational Sentinel-1 SAR context quicklook; "
                        "not flood detection, not validation, not an official warning; "
                        "source TIFF remains outside Git."
                    ),
                }
            )
    return pd.DataFrame(rows, columns=SENTINEL1_QUICKLOOK_COLUMNS)


def write_sentinel1_quicklook_manifest(
    input_dir: str | Path,
    selected_manifest_path: str | Path,
    quicklook_dir: str | Path,
    output_path: str | Path,
    *,
    provenance_manifest_path: str | Path | None = None,
    preferred_reader: str = "auto",
    max_size: int = 512,
    verify_checksum: bool = False,
) -> Path:
    """Write Sentinel-1 quicklook PNGs and a quicklook manifest CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise Sentinel1QuicklookError("Sentinel-1 quicklook manifest output must be CSV.")
    manifest = write_sentinel1_quicklooks(
        input_dir=input_dir,
        selected_manifest=selected_manifest_path,
        output_dir=quicklook_dir,
        provenance_manifest=provenance_manifest_path if _path_exists(provenance_manifest_path) else None,
        preferred_reader=preferred_reader,
        max_size=max_size,
        verify_checksum=verify_checksum,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(target, index=False)
    return target


def _read_quicklook_rgb(
    path: Path,
    *,
    band_index: int,
    reader_name: str,
    max_size: int,
) -> RGBImage:
    if reader_name == "rasterio":
        return _read_with_rasterio(path, band_index, max_size)
    if reader_name == "gdal":
        return _read_with_gdal(path, band_index, max_size)
    raise Sentinel1QuicklookError(f"Unsupported raster reader: {reader_name}")


def _read_with_rasterio(path: Path, band_index: int, max_size: int) -> RGBImage:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as dataset:
        if band_index > dataset.count:
            raise Sentinel1QuicklookError(
                f"Sentinel-1 source does not contain band {band_index}: {path.name}"
            )
        width, height = _fit_size(dataset.width, dataset.height, max_size)
        data = dataset.read(
            band_index,
            out_shape=(height, width),
            resampling=Resampling.bilinear,
            masked=True,
        )
    array = np.ma.filled(data.astype("float32"), np.nan)
    return _normalize_grayscale_to_rgb(array, width, height)


def _read_with_gdal(path: Path, band_index: int, max_size: int) -> RGBImage:
    import numpy as np
    from osgeo import gdal

    dataset = gdal.Open(str(path))
    if dataset is None:
        raise Sentinel1QuicklookError(f"GDAL could not open Sentinel-1 source: {path.name}")
    if band_index > dataset.RasterCount:
        raise Sentinel1QuicklookError(
            f"Sentinel-1 source does not contain band {band_index}: {path.name}"
        )
    width, height = _fit_size(dataset.RasterXSize, dataset.RasterYSize, max_size)
    band = dataset.GetRasterBand(band_index)
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
        raise Sentinel1QuicklookError("Quicklook array shape does not match dimensions.")
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
        raise Sentinel1QuicklookError("RGB image byte length does not match dimensions.")

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
    if row["sha256_status"] != "recorded" or not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        str(row.get("sha256", "")),
    ):
        raise Sentinel1QuicklookError(
            f"Selected Sentinel-1 row is missing a recorded SHA-256: {row['file_name']}"
        )
    if str(row.get("mvp_overlap", "")) != "mae_sai_2024_point":
        raise Sentinel1QuicklookError(
            f"Selected Sentinel-1 row must overlap Mae Sai MVP point: {row['file_name']}"
        )
    _vv_vh_band_indexes(str(row.get("band_descriptions", "")))


def _vv_vh_band_indexes(band_descriptions: str) -> list[tuple[str, int]]:
    descriptions = [part.strip().upper() for part in band_descriptions.split("|")]
    bands: list[tuple[str, int]] = []
    for index, description in enumerate(descriptions, start=1):
        if description in {"VV", "VH"}:
            bands.append((description, index))
    found = {band for band, _ in bands}
    if found != {"VV", "VH"}:
        raise Sentinel1QuicklookError("Selected Sentinel-1 manifest must include VV|VH bands.")
    return bands


def _fit_size(width: int, height: int, max_size: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise Sentinel1QuicklookError("Raster width and height must be positive.")
    scale = min(max_size / width, max_size / height, 1.0)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _quicklook_file_name(file_name: str, band: str, *, one_source: bool) -> str:
    if one_source:
        return f"sentinel1_quicklook_{band.lower()}.png"
    return f"sentinel1_quicklook_{_safe_stem(file_name)}_{band.lower()}.png"


def _quicklook_manifest_path(target_dir: Path, quicklook_file: Path) -> str:
    if target_dir.name == "outputs":
        return quicklook_file.name
    return f"{target_dir.name}/{quicklook_file.name}"


def _matching_provenance_row(
    file_name: str,
    provenance: pd.DataFrame | None,
) -> dict[str, object]:
    if provenance is None or provenance.empty or "file_name" not in provenance.columns:
        return {}
    matches = provenance[provenance["file_name"].astype(str) == file_name]
    if matches.empty:
        return {}
    return matches.iloc[0].to_dict()


def _event_timing_status(
    selected_row: dict[str, object],
    provenance_row: dict[str, object],
) -> str:
    value = str(
        provenance_row.get("event_timing_status")
        or selected_row.get("event_timing_status")
        or "timing_unresolved"
    )
    if value == "unresolved_no_acquisition_date":
        return "timing_unresolved"
    return value


def _provenance_status(
    selected_row: dict[str, object],
    provenance_row: dict[str, object],
) -> str:
    return str(
        provenance_row.get("provenance_status")
        or selected_row.get("provenance_status")
        or "unresolved"
    )


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _optional_frame(source: str | Path | pd.DataFrame | None) -> pd.DataFrame | None:
    if source is None:
        return None
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    path = Path(source)
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise Sentinel1QuicklookError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _safe_stem(file_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(file_name).stem)


def _path_exists(path: str | Path | None) -> bool:
    return path is not None and Path(path).exists()
