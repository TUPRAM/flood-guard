"""Read windows of terrain-corrected Sentinel-1 scenes from an open catalogue, in parallel and with a cache.

The scenes are the ``sentinel-1-rtc`` collection of Microsoft Planetary Computer: gamma0 at 10 m on a UTM grid,
read anonymously with a short-lived token. The host is slow per connection, so a window is read in strips of rows
with several connections at once. A pass that was read once is kept as a GeoTIFF with a small record beside it and
is not fetched again.

Nothing here detects water. The functions return linear gamma0 (VV, VH) on the grid they were asked for, and the
record says which scenes the values came from and when they were taken.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any
import urllib.request
import warnings

import numpy as np

STAC_ITEMS = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/"
STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc"
COLLECTION = "sentinel-1-rtc"
BANDS: tuple[str, ...] = ("vv", "vh")
READ_THREADS = 16
READ_ROWS = 512
MOSAIC_RULE = "first valid value in the listed order; a later scene is read only where earlier ones left gaps"

Grid = tuple[float, float, int, int]
"""West, north, rows, columns of a north-up grid."""

Resolver = Callable[[str], dict[str, Any]]
"""Turns a scene id into ``{"datetime": ..., "assets": {"vv": href, "vh": href}}`` with hrefs that can be opened."""


class S1RtcError(RuntimeError):
    """A scene cannot be read onto the grid."""


def fetch_json(url: str, *, body: dict[str, Any] | None = None, tries: int = 12, timeout: float = 90.0) -> dict[str, Any]:
    """GET (or POST ``body``) a JSON document; the catalogue times out now and then, so it is retried."""

    for attempt in range(tries):
        try:
            if body is None:
                request: Any = url
            else:
                request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                                 headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001 - retried, then raised
            if attempt == tries - 1:
                raise
            time.sleep(min(60, 10 * (attempt + 1)))
    raise S1RtcError("unreachable")


def catalogue_resolver() -> Resolver:
    """A resolver that asks the catalogue for a scene and signs its asset addresses with one token."""

    token: dict[str, str] = {}

    def resolve(item_id: str) -> dict[str, Any]:
        if "value" not in token:
            token["value"] = fetch_json(SAS_TOKEN)["token"]
        item = fetch_json(STAC_ITEMS + item_id)
        properties = item["properties"]
        return {"datetime": properties["datetime"], "platform": properties.get("platform"),
                "relative_orbit": properties.get("sat:relative_orbit"), "orbit_state": properties.get("sat:orbit_state"),
                "assets": {band: f"{item['assets'][band]['href']}?{token['value']}" for band in BANDS}}

    return resolve


def search_passes(bbox: Sequence[float], start: str, end: str, *, relative_orbit: int | None = None) -> list[dict[str, Any]]:
    """Scenes of the collection that touch ``bbox`` (lon/lat) between two UTC times, oldest first."""

    body: dict[str, Any] = {"collections": [COLLECTION], "bbox": [float(value) for value in bbox],
                            "datetime": f"{start}/{end}", "limit": 200}
    if relative_orbit is not None:
        body["query"] = {"sat:relative_orbit": {"eq": int(relative_orbit)}}
    features = fetch_json(STAC_SEARCH, body=body)["features"]
    return sorted(({"item": feature["id"], "datetime": feature["properties"]["datetime"], "bbox": feature["bbox"],
                    "relative_orbit": feature["properties"].get("sat:relative_orbit")} for feature in features),
                  key=lambda entry: entry["datetime"])


def grid_bounds(grid: Grid, cell_m: float) -> tuple[float, float, float, float]:
    west, north, rows, columns = grid
    return (west, north - rows * cell_m, west + columns * cell_m, north)


def read_window_parallel(href: str, grid: Grid, *, epsg: int, cell_m: float, threads: int = READ_THREADS,
                         strip_rows: int = READ_ROWS) -> np.ndarray:
    """Read band 1 of a raster on ``grid``, in strips of rows read at the same time.

    The raster must be on the grid's projection and cell size and aligned to it. Cells outside the raster come
    back as NaN.
    """

    import rasterio
    from rasterio.windows import Window, from_bounds

    west, north, rows, columns = grid
    if rows <= 0 or columns <= 0 or threads <= 0 or strip_rows <= 0:
        raise S1RtcError("the grid, the number of threads and the strip height must be positive")
    options = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "6", "GDAL_HTTP_RETRY_DELAY": "4"}
    with rasterio.Env(**options):
        with rasterio.open(href) as source:
            if source.crs is None or source.crs.to_epsg() != epsg or source.res != (cell_m, cell_m):
                raise S1RtcError(f"the raster is not on the {cell_m} m EPSG:{epsg} grid")
            whole = from_bounds(*grid_bounds(grid, cell_m), transform=source.transform)
    column, row = int(round(whole.col_off)), int(round(whole.row_off))
    if abs(whole.col_off - column) > 1e-6 or abs(whole.row_off - row) > 1e-6:
        raise S1RtcError("the raster is not aligned to the grid")

    def strip(start: int) -> np.ndarray:
        with rasterio.Env(**options):
            with rasterio.open(href) as source:
                return source.read(1, window=Window(column, row + start, columns, min(strip_rows, rows - start)),
                                   boundless=True, fill_value=np.nan).astype("float32")

    with ThreadPoolExecutor(threads) as pool:
        return np.vstack(list(pool.map(strip, range(0, rows, strip_rows))))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_window(path: Path, bands: Sequence[np.ndarray], grid: Grid, *, epsg: int, cell_m: float) -> None:
    """Write float32 bands on ``grid`` as a compressed GeoTIFF with NaN as no-data."""

    import rasterio
    from rasterio.transform import from_origin

    west, north, rows, columns = grid
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=len(bands), dtype="float32",
                       nodata=float("nan"), crs=f"EPSG:{epsg}", compress="deflate", tiled=True,
                       transform=from_origin(west, north, cell_m, cell_m)) as target:
        for index, band in enumerate(bands, start=1):
            target.write(np.asarray(band, dtype="float32"), index)


def fetch_pass(work: Path, grid: Grid, items: Sequence[str], name: str, *, epsg: int, cell_m: float,
               resolve: Resolver | None = None, threads: int = READ_THREADS) -> dict[str, Any]:
    """One Sentinel-1 pass on ``grid``: VV and VH, linear gamma0, mosaicked from its scenes and cached.

    Returns the record of the cached window: the scenes that were read with their times, the file and its SHA-256.
    Values that are not finite or not above zero are no-data.
    """

    if not items:
        raise S1RtcError("a pass needs at least one scene")
    west, north, rows, columns = grid
    path, record_path = Path(work) / f"{name}.tif", Path(work) / f"{name}.json"
    if not (path.exists() and record_path.exists()):
        lookup = resolve or catalogue_resolver()
        image = np.full((len(BANDS), rows, columns), np.nan, dtype="float32")
        sources = []
        for item_id in items:
            if sources and np.isfinite(image).all():
                break
            scene = lookup(item_id)
            sources.append({key: scene.get(key) for key in ("datetime", "platform", "relative_orbit", "orbit_state")} | {"item": item_id})
            for band, asset in enumerate(BANDS):
                block = read_window_parallel(scene["assets"][asset], grid, epsg=epsg, cell_m=cell_m, threads=threads)
                block[~(np.isfinite(block) & (block > 0))] = np.nan
                image[band] = np.where(np.isfinite(image[band]), image[band], block)
        write_window(path, list(image), grid, epsg=epsg, cell_m=cell_m)
        record = {"fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": sources,
                  "mosaic_rule": MOSAIC_RULE, "valid_share": round(float(np.isfinite(image).all(axis=0).mean()), 6)}
        record_path.write_bytes((json.dumps(record, indent=1) + "\n").encode("utf-8"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    return {**record, "window_file": path.name, "window_sha256": sha256_file(path)}


def median_of_passes(paths: Sequence[Path], *, strip_rows: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """Per cell and band: the median and the spread, in dB, of the passes that have a value there.

    Returns ``(median_db, spread_db)``, each ``(2, H, W)`` float32. The spread is the standard deviation of the dB
    values; a cell seen by one pass only has a spread of zero, and a cell seen by none is NaN in both.
    """

    import rasterio
    from rasterio.windows import Window

    if not paths:
        raise S1RtcError("a baseline needs at least one pass")
    with rasterio.open(paths[0]) as first:
        rows, columns, count = first.height, first.width, first.count
    median = np.full((count, rows, columns), np.nan, dtype="float32")
    spread = np.full((count, rows, columns), np.nan, dtype="float32")
    sources = [rasterio.open(path) for path in paths]
    try:
        if any(source.height != rows or source.width != columns or source.count != count for source in sources):
            raise S1RtcError("the passes of a baseline must be on one grid")
        for start in range(0, rows, strip_rows):
            window = Window(0, start, columns, min(strip_rows, rows - start))
            stack = np.stack([source.read(window=window).astype("float64") for source in sources])
            with np.errstate(invalid="ignore", divide="ignore"):
                decibel = np.where(np.isfinite(stack) & (stack > 0), 10.0 * np.log10(stack), np.nan)
            seen = np.isfinite(decibel).any(axis=0)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # a cell that no pass saw: all-NaN slice
                middle = np.nanmedian(decibel, axis=0)
                deviation = np.nanstd(decibel, axis=0)
            rows_here = slice(start, start + window.height)
            median[:, rows_here] = np.where(seen, middle, np.nan)
            spread[:, rows_here] = np.where(seen, deviation, np.nan)
    finally:
        for source in sources:
            source.close()
    return median, spread
