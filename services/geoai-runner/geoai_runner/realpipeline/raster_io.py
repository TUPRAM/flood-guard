"""Small GeoTIFF read/write helpers for the GeoAI pipeline.

These wrap rasterio so the model modules stay focused on the science. rasterio
is an optional dependency (``pip install -e ".[geoai]"``); importing this module
without it raises a clear message.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class RasterIOUnavailableError(RuntimeError):
    """Raised when rasterio is required but not installed."""


def _require_rasterio():
    try:
        import rasterio  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RasterIOUnavailableError(
            "rasterio is required for the GeoAI pipeline. Install with "
            'pip install -e ".[geoai]" (or conda install rasterio).'
        ) from exc
    return rasterio


def write_geotiff(
    path: str | Path,
    array: np.ndarray,
    transform,
    crs: str,
    *,
    nodata: float | None = None,
    dtype: str | None = None,
) -> Path:
    """Write a 2D or 3D (bands, H, W) array to a GeoTIFF."""

    rasterio = _require_rasterio()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(array)
    if data.ndim == 2:
        data = data[None, :, :]
    count, height, width = data.shape
    out_dtype = dtype or str(data.dtype)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=out_dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data.astype(out_dtype))
    return path


def read_geotiff(path: str | Path) -> tuple[np.ndarray, object, str]:
    """Read a GeoTIFF, returning (array[bands,H,W], transform, crs)."""

    rasterio = _require_rasterio()
    with rasterio.open(path) as src:
        return src.read(), src.transform, str(src.crs)


def array_to_png(
    path: str | Path,
    array: np.ndarray,
    *,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
) -> Path:
    """Render a 2D array (or 3-band RGB in [0,1]) to a small PNG preview."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(array)
    fig, ax = plt.subplots(figsize=(4, 4), dpi=110)
    if data.ndim == 3 and data.shape[0] == 3:
        ax.imshow(np.clip(np.transpose(data, (1, 2, 0)), 0, 1))
    else:
        ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return path
