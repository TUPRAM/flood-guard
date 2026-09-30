#!/usr/bin/env python
"""Build the Mae Sai September 2024 day-by-day flood timeline assets for the web Studio.

Inputs
------
* External rasters (kept outside Git), under ``--external-root`` or ``FLOODGUARD_EXTERNAL_DATA``:
  - ``open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif``
  - ``earth_search/mae_sai_2024/S2B_47QNC_{20240905,20240915}_0_L2A/{red,green,blue}.tif``
  - ``cdse/mae_sai_2024/S1A_IW_GRDH_1SDV_*_COG.SAFE.zip`` (6 and 15 September 2024)
* In-repo vectors: ``outputs/mae_sai_admin_context.geojson``, ``outputs/mae_sai_road_risk.geojson``,
  ``outputs/mae_sai_facilities.geojson``.

Outputs (``apps/web/public/studies/mae-sai-2024-timeline/r3/``): a HAND code raster, dated
Sentinel-1/2 image layers, a hillshade, sampled road/facility/tambon vectors and ``timeline.json``.

The daily water surface is a HAND threshold reconstruction driven by illustrative stage keyframes.
It is not an observation, a validated flood extent, a real-time product or an official warning.
"""

from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.features import rasterize
from rasterio.transform import GCPTransformer, from_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds as window_from_bounds
from scipy import ndimage
from shapely.geometry import LineString, mapping, shape
from shapely.ops import substring, transform as shp_transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.flood_timeline import (  # noqa: E402
    HAND_STEP_M,
    IMPASSABLE_DEPTH_M,
    KEYFRAMES,
    CHANNEL_CODE,
    NEVER_CODE,
    decode_hand,
    encode_hand,
    flooded_area_km2,
    stage_anchors,
    stage_at,
    road_state,
    depth_factor,
)
import mae_sai_timeline_evacuation as evac  # noqa: E402
import mae_sai_timeline_observations as obs  # noqa: E402

OUT_REL = Path("apps/web/public/studies/mae-sai-2024-timeline/r3")
HREF_PREFIX = "/studies/mae-sai-2024-timeline/r3/"
SAI_REFERENCE_LONLAT = (99.8826, 20.4460)  # Sai River at the Mae Sai border bridges (main-stem reference reach).
REPORTED_SHELTERS = Path("outputs/mae_sai_reported_shelters_2024.json")
UTM = "EPSG:32647"
AOI_UTM = (584400.0, 2240100.0, 608400.0, 2266100.0)  # Whole Mae Sai district plus Tachileik to the north.
AOI_RES = 10.0
HYDRO_LONLAT = (99.45, 20.15, 100.15, 20.72)  # Upstream Sai catchment plus the Ruak to the east (DEM tiles N20E099 + N20E100).
DEM_TILES = ("Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif", "Copernicus_DSM_COG_10_N20_00_E100_00_DEM.tif")
HYDRO_RES = 30.0
STREAM_THRESHOLD_KM2 = 25.0
LOW_CONFIDENCE_FILL_M = 0.1  # Pits raised by more than this when filled ...
LOW_CONFIDENCE_HAND_M = 0.1  # ... that end up within this height of their channel read as wet at any stage: low confidence.
EDGE_OUTLET_KM2 = 1.0  # Domain-edge outlets used as HAND references (not drawn as channels).
MERCATOR_SCALE = 1.0 / math.cos(math.radians(20.36))  # EPSG:3857 units per ground metre at Mae Sai.
IMAGE_RES = 12.0 * MERCATOR_SCALE
WATER_RES = 15.0 * MERCATOR_SCALE
ROAD_PIECE_M = 120.0
ROAD_CLASSES = ("trunk", "primary", "secondary", "tertiary", "unclassified", "residential")
ROAD_KEEP_ALWAYS = ROAD_CLASSES[:3]
ROAD_MAX_HAND_M = 4.0  # Pieces higher than this never flood under the keyframes and are dropped (except arterials).

S2_SCENES = {
    "s2-20240905": ("S2B_47QNC_20240905_0_L2A", "2024-09-05T03:58:19Z"),
    "s2-20240915": ("S2B_47QNC_20240915_0_L2A", "2024-09-15T03:58:15Z"),
}
S1_SCENES = {
    "s1-20240906": "S1A_IW_GRDH_1SDV_20240906T113106_20240906T113131_055544_06C73C_B53D_COG.SAFE.zip",
    "s1-20240915": "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_82A9_COG.SAFE.zip",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Grid:
    """A north-up raster grid."""

    def __init__(self, crs: str, bounds: tuple[float, float, float, float], res: float, exact: bool = False):
        self.crs = crs
        self.width = int(round((bounds[2] - bounds[0]) / res))
        self.height = int(round((bounds[3] - bounds[1]) / res))
        if exact:  # Keep the bounds (pixels become very slightly non-square) so overlays share one extent.
            self.bounds = tuple(bounds)
            self.transform = from_bounds(*bounds, self.width, self.height)
            self.res = (bounds[2] - bounds[0]) / self.width
        else:
            self.res = res
            self.bounds = (bounds[0], bounds[3] - self.height * res, bounds[0] + self.width * res, bounds[3])
            self.transform = from_origin(bounds[0], bounds[3], res, res)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)


def warp(src: np.ndarray, src_transform, src_crs, grid: Grid, resampling=Resampling.bilinear, src_nodata=None, gcps=None) -> np.ndarray:
    dst = np.full(grid.shape, np.nan, dtype=np.float32)
    kwargs = dict(source=src.astype(np.float32), destination=dst, dst_transform=grid.transform, dst_crs=grid.crs,
                  resampling=resampling, src_nodata=src_nodata, dst_nodata=np.nan)
    if gcps is not None:
        kwargs.update(gcps=gcps, src_crs=src_crs)
    else:
        kwargs.update(src_transform=src_transform, src_crs=src_crs)
    reproject(**kwargs)
    return dst


def hydrology(dem_paths: list[Path], work: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, Grid, np.ndarray, float, np.ndarray]:
    """Return HAND (m), stream mask, conditioned DEM, the UTM grid, the depth factor k, the reference area and a
    low-confidence mask (filled depressions and flat-fallback cells)."""
    from pysheds.grid import Grid as ShedGrid

    bounds = transform_bounds("EPSG:4326", UTM, *HYDRO_LONLAT, densify_pts=21)
    grid = Grid(UTM, bounds, HYDRO_RES)
    from rasterio.merge import merge

    sources = [rasterio.open(path) for path in dem_paths]
    try:
        mosaic, mosaic_transform = merge(sources, bounds=HYDRO_LONLAT, nodata=-9999.0)
        dem_utm = warp(mosaic[0].astype(np.float32), mosaic_transform, sources[0].crs, grid, Resampling.bilinear, src_nodata=-9999.0)
    finally:
        for source in sources:
            source.close()
    dem_utm = np.where(np.isfinite(dem_utm), dem_utm, -9999.0).astype(np.float32)
    tmp = work / "dem_utm30.tif"
    with rasterio.open(tmp, "w", driver="GTiff", width=grid.width, height=grid.height, count=1, dtype="float32",
                       crs=UTM, transform=grid.transform, nodata=-9999.0) as dst:
        dst.write(dem_utm, 1)
    sg = ShedGrid.from_raster(str(tmp))
    raw = sg.read_raster(str(tmp))
    inflated = sg.resolve_flats(sg.fill_depressions(sg.fill_pits(raw)))
    fdir = sg.flowdir(inflated)
    acc = sg.accumulation(fdir)
    area_km2 = np.asarray(acc) * (HYDRO_RES**2) / 1e6
    stream_raster = acc * (HYDRO_RES**2) / 1e6 >= STREAM_THRESHOLD_KM2  # Keeps the pysheds Raster type.
    streams = np.asarray(stream_raster, dtype=bool)
    # Cells that drain off the domain before reaching a mapped stream would have no HAND; reference them to
    # their outlet on the domain edge instead (the domain edge lies well outside the replay area).
    nodata = dem_utm <= -9000
    edge = ndimage.binary_dilation(nodata) & ~nodata
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    stream_raster[edge & (area_km2 >= EDGE_OUTLET_KM2)] = True
    hand = np.asarray(sg.compute_hand(fdir, inflated, stream_raster), dtype=np.float32)
    drain = np.asarray(sg.compute_hand(fdir, inflated, stream_raster, return_index=True), dtype=np.int64)
    conditioned = np.asarray(inflated, dtype=np.float32)
    # Large paddy flats can end without a resolved flow path; fall back to height above the nearest channel cell.
    missing = ~np.isfinite(hand) & ~nodata
    if missing.any():
        rows, cols = ndimage.distance_transform_edt(~np.asarray(stream_raster, dtype=bool), return_distances=False, return_indices=True)
        hand[missing] = conditioned[missing] - conditioned[rows, cols][missing]
        drain[missing] = (rows * grid.width + cols)[missing]
    hand = np.where(np.isfinite(hand) & ~nodata, np.clip(hand, 0, None), np.nan)
    # Per-reach stage scaling: k from the upstream area of each cell's drainage cell, relative to the Sai main stem.
    x0, y0 = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform(*SAI_REFERENCE_LONLAT)
    r0, c0 = int((grid.bounds[3] - y0) // HYDRO_RES), int((x0 - grid.bounds[0]) // HYDRO_RES)
    near = np.zeros_like(streams)
    near[max(r0 - 50, 0):r0 + 51, max(c0 - 50, 0):c0 + 51] = True
    reference_km2 = float(area_km2[streams & near].max())
    upstream = np.where(drain >= 0, area_km2.ravel()[np.clip(drain, 0, None)], np.nan).reshape(hand.shape)
    k = np.where(np.isfinite(hand), depth_factor(np.nan_to_num(upstream, nan=reference_km2), reference_km2), np.nan)
    # Pits filled to their spill level become dead-flat with HAND ~ 0 and look wet at any stage; flag them (and the
    # flat-area fallback cells) as low confidence rather than hiding them.
    filled = (conditioned - np.asarray(raw, dtype=np.float32)) > LOW_CONFIDENCE_FILL_M
    near_zero = np.isfinite(hand) & (hand < LOW_CONFIDENCE_HAND_M)
    low_confidence = ((filled | missing) & near_zero) & ~nodata
    return hand, streams, conditioned, grid, k.astype(np.float32), reference_km2, low_confidence


def hillshade(dem: np.ndarray, res: float, azimuth: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    dy, dx = np.gradient(np.nan_to_num(dem, nan=float(np.nanmedian(dem))), res)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    az, alt = math.radians(360.0 - azimuth + 90.0), math.radians(altitude)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


def to_u8(values: np.ndarray, lo: float, hi: float, gamma: float = 1.0) -> np.ndarray:
    scaled = np.clip((values - lo) / max(hi - lo, 1e-6), 0, 1) ** gamma
    return np.nan_to_num(scaled * 255, nan=0).astype(np.uint8)


def sentinel2_rgb(scene_dir: Path, grid: Grid) -> np.ndarray:
    bands = []
    for name in ("red", "green", "blue"):
        with rasterio.open(scene_dir / f"{name}.tif") as src:
            aoi = transform_bounds(grid.crs, src.crs, *grid.bounds, densify_pts=21)
            win = window_from_bounds(*aoi, transform=src.transform).round_offsets().round_lengths()
            win = Window(win.col_off - 8, win.row_off - 8, win.width + 16, win.height + 16)
            dn = src.read(1, window=win).astype(np.float32)
            # Earth Search L2A keeps raw DN with the processing-baseline 04.00 offset of -1000.
            refl = np.where(dn > 0, (dn - 1000.0) / 10000.0, np.nan)
            bands.append(warp(refl, src.window_transform(win), src.crs, grid))
    return np.stack(bands)


def sentinel1_vv(zip_path: Path, grid: Grid) -> tuple[np.ndarray, dict]:
    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if "/measurement/" in n and "-vv-" in n)
        manifest = archive.read(next(n for n in archive.namelist() if n.endswith("manifest.safe"))).decode()
    meta = {
        "pass": re.search(r"<s1:pass>(\w+)", manifest).group(1).lower(),
        "relative_orbit": int(re.search(r'relativeOrbitNumber type="start">(\d+)', manifest).group(1)),
    }
    with rasterio.open(f"/vsizip/{zip_path.as_posix()}/{member}") as src:
        gcps, gcp_crs = src.gcps
        lon0, lat0, lon1, lat1 = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds, densify_pts=21)
        lons = [lon0 - 0.03, lon1 + 0.03, lon0 - 0.03, lon1 + 0.03]
        lats = [lat0 - 0.03, lat0 - 0.03, lat1 + 0.03, lat1 + 0.03]
        rows, cols = GCPTransformer(gcps).rowcol(lons, lats)
        r0, r1 = max(min(rows), 0), min(max(rows), src.height)
        c0, c1 = max(min(cols), 0), min(max(cols), src.width)
        dn = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float32)
    shifted = [GroundControlPoint(row=g.row - r0, col=g.col - c0, x=g.x, y=g.y, z=g.z) for g in gcps]
    intensity = ndimage.uniform_filter(dn**2, size=5)  # Light boxcar speckle smoothing for display only.
    db = np.where(dn > 0, 10 * np.log10(np.maximum(intensity, 1.0)), np.nan)
    return warp(db, None, gcp_crs, grid, gcps=shifted), meta


def write_webp(path: Path, array: np.ndarray, quality: int = 80) -> None:
    Image.fromarray(array).save(path, "WEBP", quality=quality, method=6)


def sample_codes(codes: np.ndarray, grid: Grid, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    cols = np.floor((xs - grid.bounds[0]) / grid.res).astype(int)
    rows = np.floor((grid.bounds[3] - ys) / grid.res).astype(int)
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    out = np.full(xs.shape, NEVER_CODE, dtype=np.uint8)
    out[inside] = codes[rows[inside], cols[inside]]
    return out


def sample_mask(mask: np.ndarray, grid: Grid, xs: np.ndarray, ys: np.ndarray) -> bool:
    cols = np.floor((xs - grid.bounds[0]) / grid.res).astype(int)
    rows = np.floor((grid.bounds[3] - ys) / grid.res).astype(int)
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    return bool(mask[rows[inside], cols[inside]].any())


def min_hand(samples: np.ndarray) -> float | None:
    usable = samples[(samples != CHANNEL_CODE) & (samples != NEVER_CODE)]
    return None if usable.size == 0 else round(float(usable.min()) * HAND_STEP_M, 2)


def s1_anchor(codes: np.ndarray, pre_db: np.ndarray, post_db: np.ndarray, pixel_km2: float) -> dict:
    """Match reconstruction area to Sentinel-1 newly dark (water-like) area in the low-HAND zone.

    Constrains magnitude only: the two passes use different orbit directions and the fit is spatially weak.
    """
    hand = decode_hand(codes)
    valid = (hand < 6) & (codes != CHANNEL_CODE) & np.isfinite(pre_db) & np.isfinite(post_db)
    threshold = float(np.percentile(pre_db[valid], 5))
    newly = valid & (post_db < threshold) & (pre_db >= threshold)
    best: tuple | None = None
    for stage in np.round(np.arange(0.05, 2.0001, 0.05), 2):
        model = valid & (hand < stage)
        union = int((model | newly).sum())
        cand = (abs(int(model.sum()) - int(newly.sum())), float(stage), int((model & newly).sum()) / union if union else 0.0, int(model.sum()))
        if best is None or cand[0] < best[0]:
            best = cand
    assert best is not None
    return {"threshold_db_dn": round(threshold, 2), "newly_dark_km2": round(float(newly.sum()) * pixel_km2, 2),
            "best_fit_stage_m": best[1], "best_fit_model_km2": round(best[3] * pixel_km2, 2), "iou_at_best_fit": round(best[2], 3),
            "scope": "Low-HAND zone (HAND < 6 m, channel excluded) across the full image footprint, both sides of the border."}


def build(external: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    to_utm = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform
    to_ll = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True).transform
    aoi = Grid(UTM, AOI_UTM, AOI_RES)
    extent_3857 = transform_bounds(UTM, "EPSG:3857", *AOI_UTM, densify_pts=41)
    display = Grid("EPSG:3857", extent_3857, IMAGE_RES, exact=True)
    water = Grid("EPSG:3857", extent_3857, WATER_RES, exact=True)
    layers: list[dict] = []

    def emit(name: str, data: bytes, **extra) -> dict:
        (out_dir / name).write_bytes(data)
        record = {"href": HREF_PREFIX + name, "sha256": sha256_bytes(data), "bytes": len(data), **extra}
        return record

    # --- Hydrology and HAND -------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        hand30, streams30, dem30, hgrid, k30, reference_km2, lowconf30 = hydrology(
            [external / "open_context/copernicus_dem_glo30" / tile for tile in DEM_TILES], Path(tmp))

    def hand_codes(grid: Grid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        hand = warp(np.nan_to_num(hand30, nan=-1), hgrid.transform, UTM, grid, Resampling.bilinear, src_nodata=-1)
        kk = warp(np.nan_to_num(k30, nan=-1), hgrid.transform, UTM, grid, Resampling.nearest, src_nodata=-1)
        chan = warp(streams30.astype(np.float32), hgrid.transform, UTM, grid, Resampling.nearest) > 0.5
        valid = np.isfinite(hand) & np.isfinite(kk)
        kk = np.where(valid, np.clip(kk, 0.01, 1.0), 1.0)
        effective = np.where(valid, hand / kk, 1e6)
        return encode_hand(effective, chan, valid), valid, kk.astype(np.float32)

    codes_aoi, valid_aoi, k_aoi = hand_codes(aoi)
    codes_display, _, k_display = hand_codes(water)
    lowconf_display = warp(lowconf30.astype(np.float32), hgrid.transform, UTM, water, Resampling.nearest) > 0.5
    lowconf_aoi = warp(lowconf30.astype(np.float32), hgrid.transform, UTM, aoi, Resampling.nearest) > 0.5
    buf = tempfile.SpooledTemporaryFile()
    k_u8 = np.clip(np.rint(k_display * 255), 1, 255).astype(np.uint8)
    b_u8 = np.where(lowconf_display & (codes_display != NEVER_CODE), 255, 0).astype(np.uint8)
    Image.fromarray(np.dstack([codes_display, k_u8, b_u8]), mode="RGB").save(buf, "PNG", optimize=True)
    buf.seek(0)
    hand_record = emit("hand-codes.png", buf.read(), width=water.width, height=water.height, depth_factor_channel="G",
                       low_confidence_channel="B",
                       low_confidence={"rule": f"B = 255 where the terrain was raised by more than {LOW_CONFIDENCE_FILL_M} m when filling pits (or needed the flat-area routing fallback) and ends up less than {LOW_CONFIDENCE_HAND_M} m above its channel",
                                       "meaning": "Dead-flat or filled low ground in the elevation model: HAND ~ 0, so it reads as wet at almost any stage. Real low paddies or ponds are possible, but so are elevation artefacts."},
                       depth_factor={"exponent": 0.3, "floor": 0.35, "reference_km2": round(reference_km2, 1),
                                     "reference": "Sai River main stem at the Mae Sai border bridges"})

    dem_aoi = warp(dem30, hgrid.transform, UTM, aoi, Resampling.bilinear)
    shade = hillshade(dem_aoi, AOI_RES)
    shade_display = warp(shade, aoi.transform, UTM, display, Resampling.bilinear)
    buf = tempfile.SpooledTemporaryFile()
    write_webp(buf, to_u8(shade_display, 0.0, 1.0), quality=70)  # type: ignore[arg-type]
    buf.seek(0)
    layers.append(emit("hillshade.webp", buf.read(), id="hillshade", kind="terrain", date=None))

    # --- Sentinel-2 true colour -----------------------------------------------------------
    rgb = {key: sentinel2_rgb(external / "earth_search/mae_sai_2024" / scene, display) for key, (scene, _) in S2_SCENES.items()}
    clear = np.all(rgb["s2-20240905"] < 0.25, axis=0)  # Stretch on cloud-free land so clouds do not darken it.
    lo, hi = np.nanpercentile(rgb["s2-20240905"][:, clear], [1, 99.5])
    for key, (scene, stamp) in S2_SCENES.items():
        img = np.moveaxis(to_u8(rgb[key], lo, hi, gamma=0.8), 0, -1)
        buf = tempfile.SpooledTemporaryFile()
        write_webp(buf, img, quality=78)  # type: ignore[arg-type]
        buf.seek(0)
        layers.append(emit(f"{key}.webp", buf.read(), id=key, kind="sentinel-2", date=stamp, scene=scene))

    # --- Sentinel-1 VV backscatter and change composite ------------------------------------
    s1: dict[str, np.ndarray] = {}
    s1_meta: dict[str, dict] = {}
    for key, name in S1_SCENES.items():
        s1[key], s1_meta[key] = sentinel1_vv(external / "cdse/mae_sai_2024" / name, display)
    db_lo, db_hi = np.nanpercentile(s1["s1-20240906"], [2, 98])
    s1_stamps = {"s1-20240906": "2024-09-06T11:31:06Z", "s1-20240915": "2024-09-15T23:16:01Z"}
    for key in S1_SCENES:
        buf = tempfile.SpooledTemporaryFile()
        write_webp(buf, to_u8(s1[key], db_lo, db_hi), quality=72)  # type: ignore[arg-type]
        buf.seek(0)
        layers.append(emit(f"{key}-vv.webp", buf.read(), id=key, kind="sentinel-1", date=s1_stamps[key], scene=S1_SCENES[key][:-4], **s1_meta[key]))
    s1_water = {key: warp(value, display.transform, display.crs, water, Resampling.average) for key, value in s1.items()}
    anchor = s1_anchor(codes_display, s1_water["s1-20240906"], s1_water["s1-20240915"], (water.res / MERCATOR_SCALE) ** 2 / 1e6)
    pre, post = to_u8(s1["s1-20240906"], db_lo, db_hi), to_u8(s1["s1-20240915"], db_lo, db_hi)
    buf = tempfile.SpooledTemporaryFile()
    write_webp(buf, np.dstack([pre, post, post]), quality=72)  # type: ignore[arg-type]
    buf.seek(0)
    layers.append(emit("s1-change-rgb.webp", buf.read(), id="s1-change", kind="sentinel-1-change", date="2024-09-06T11:31:06Z/2024-09-15T23:16:01Z"))

    # --- Vectors --------------------------------------------------------------------------
    admin = json.loads((ROOT / "outputs/mae_sai_admin_context.geojson").read_text(encoding="utf-8"))
    tambon_ids = [f["properties"]["subdistrict_id"] for f in admin["features"]]
    zones = rasterize(((shape(f["geometry"]).__class__(shp_transform(to_utm, shape(f["geometry"]))), i + 1) for i, f in enumerate(admin["features"])),
                      out_shape=aoi.shape, transform=aoi.transform, fill=0, dtype="uint8")
    histograms = {tid: np.bincount(codes_aoi[zones == i + 1], minlength=256).tolist() for i, tid in enumerate(tambon_ids)}
    coverage = {f["properties"]["subdistrict_id"]: {
        "modelled_km2": round(float((valid_aoi & (zones == i + 1)).sum()) * AOI_RES**2 / 1e6, 2),
        "total_km2": round(shp_transform(to_utm, shape(f["geometry"])).area / 1e6, 2)} for i, f in enumerate(admin["features"])}
    tambons = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(shape(f["geometry"]).simplify(0.0002, preserve_topology=True)),
         "properties": {"id": f["properties"]["subdistrict_id"], "en": f["properties"]["subdistrict_name"], "th": f["properties"]["subdistrict_name_th"]}}
        for f in admin["features"]]}

    roads_src = json.loads((ROOT / "outputs/mae_sai_road_risk.geojson").read_text(encoding="utf-8"))
    road_features = []
    for f in roads_src["features"]:
        props = f["properties"]
        cls = props.get("road_class")
        if cls not in ROAD_CLASSES:
            continue
        line = shp_transform(to_utm, shape(f["geometry"]))
        pieces = max(1, math.ceil(line.length / ROAD_PIECE_M))
        for p in range(pieces):
            piece = substring(line, p * line.length / pieces, (p + 1) * line.length / pieces)
            if not isinstance(piece, LineString) or piece.length == 0:
                continue
            steps = np.linspace(0, piece.length, max(2, int(piece.length // 10) + 1))
            pts = np.array([piece.interpolate(d).coords[0] for d in steps])
            h, kf = evac.sample_road(codes_aoi, k_aoi, aoi, pts[:, 0], pts[:, 1])
            modelled = sample_mask(valid_aoi, aoi, pts[:, 0], pts[:, 1])
            if cls not in ROAD_KEEP_ALWAYS and (not modelled or h is None or h > ROAD_MAX_HAND_M):
                continue
            coords = [[round(x, 5), round(y, 5)] for x, y in (to_ll(*c) for c in piece.coords)]
            road_features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                                  "properties": {"c": cls, "h": h, "k": kf, "m": modelled, "len": round(piece.length), "t": props["subdistrict_id"],
                                                 **({"n": props["road_name"]} if props.get("road_name") and cls in ROAD_CLASSES[:4] else {})}})
    roads = {"type": "FeatureCollection", "features": road_features}

    fac_src = json.loads((ROOT / "outputs/mae_sai_facilities.geojson").read_text(encoding="utf-8"))
    facility_features = []
    for f in fac_src["features"]:
        x, y = to_utm(*f["geometry"]["coordinates"][:2])
        xs = np.array([x + dx for dx in (-10, 0, 10) for _ in range(3)])
        ys = np.array([y + dy for _ in range(3) for dy in (-10, 0, 10)])
        fh, fk = evac.sample_eff(codes_aoi, k_aoi, aoi, xs, ys)
        p = f["properties"]
        facility_features.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "id": p["facility_id"], "type": p["facility_type"], "n": p.get("facility_name") or "", "t": p["subdistrict_id"], "h": fh, "k": fk,
            "m": sample_mask(valid_aoi, aoi, xs, ys)}})
    facilities = {"type": "FeatureCollection", "features": facility_features}

    # --- Population (WorldPop 2020) -------------------------------------------------------
    coarse_pop, pop10 = evac.population_grid(external / "open_context/worldpop_population/tha_ppp_2020.tif", aoi)
    pop_hist = {tid: np.round(np.bincount(codes_aoi[zones == i + 1], weights=pop10[zones == i + 1], minlength=256), 1).tolist()
                for i, tid in enumerate(tambon_ids)}
    density, density_cap = evac.density_codes(coarse_pop, aoi, water)
    buf = tempfile.SpooledTemporaryFile()
    Image.fromarray(density, mode="L").save(buf, "PNG", optimize=True)
    buf.seek(0)
    population_record = emit("population-density.png", buf.read(), width=water.width, height=water.height,
                             encoding="code = round(254 * ln(1 + p) / ln(1 + max_per_ha)); p = people per hectare",
                             max_per_ha=density_cap)

    # --- Evacuation access and shelter plan ---------------------------------------------------
    peak_stage = max(k.stage_m for k in KEYFRAMES)
    graph = evac.build_graph(ROOT, to_utm, codes_aoi, k_aoi, aoi)
    osm_dir = external / "derived_context/mae_sai_2024"
    polygons_path, points_path = osm_dir / "mae_sai_osm_multipolygons.gpkg", osm_dir / "mae_sai_osm_points_full.gpkg"
    if not polygons_path.exists() or not points_path.exists():
        import pyogrio
        pbf = external / "open_context/osm_geofabrik/thailand-latest.osm.pbf"
        bbox = transform_bounds(UTM, "EPSG:4326", *AOI_UTM, densify_pts=21)
        pyogrio.read_dataframe(pbf, layer="multipolygons", bbox=bbox).to_file(polygons_path, driver="GPKG")
        pyogrio.read_dataframe(pbf, layer="points", bbox=bbox).to_file(points_path, driver="GPKG")
    import pyogrio
    sites = evac.shelter_candidates(pyogrio.read_dataframe(polygons_path), pyogrio.read_dataframe(points_path),
                                    ROOT / "outputs/mae_sai_facilities.geojson", to_utm)
    evac.evaluate_sites(sites, graph, codes_aoi, k_aoi, aoi, peak_stage, valid_aoi)
    reported_doc = json.loads((ROOT / REPORTED_SHELTERS).read_text(encoding="utf-8")) if (ROOT / REPORTED_SHELTERS).exists() else {"shelters": []}
    reported_all = reported_doc["shelters"]
    located = [r for r in reported_all if r.get("lat") is not None and r.get("lon") is not None]
    for r in located:
        r["x"], r["y"] = to_utm(r["lon"], r["lat"])
    evac.evaluate_sites(located, graph, codes_aoi, k_aoi, aoi, peak_stage, valid_aoi)
    counted = [r for r in located if r.get("in_access_set", True)]
    access = evac.plan_and_access(sites, counted, graph, peak_stage)
    pop_df = graph["pop"]
    tambon_order = list(tambon_ids)
    node_tambon = np.array([tambon_order.index(t) + 1 if t in tambon_order else 0 for t in pop_df["subdistrict_id"]], dtype=np.uint8)
    lonlat = graph["lonlat"][graph["pop_index"]]
    blob = b"".join([
        lonlat[:, 0].astype("<f4").tobytes(), lonlat[:, 1].astype("<f4").tobytes(),
        pop_df["total_population"].to_numpy("<f4").tobytes(), pop_df["vulnerable_population"].to_numpy("<f4").tobytes(),
        node_tambon.tobytes(), graph["home_code"].astype(np.uint8).tobytes(),
        np.clip(np.rint(graph["home_k"] * 255), 1, 255).astype(np.uint8).tobytes(),
        access["node_codes"].astype(np.uint8).tobytes(),
    ])
    n_nodes = len(pop_df)
    nodes_record = emit("access-nodes.bin", blob, count=n_nodes, layout=[
        {"name": "lon", "dtype": "float32", "offset": 0}, {"name": "lat", "dtype": "float32", "offset": 4 * n_nodes},
        {"name": "population", "dtype": "float32", "offset": 8 * n_nodes}, {"name": "vulnerable_population", "dtype": "float32", "offset": 12 * n_nodes},
        {"name": "tambon_index", "dtype": "uint8", "offset": 16 * n_nodes, "note": "1-based index into access.tambons; 0 = none"},
        {"name": "home_code", "dtype": "uint8", "offset": 17 * n_nodes, "note": "effective HAND code at the node"},
        {"name": "home_k", "dtype": "uint8", "offset": 18 * n_nodes, "note": "depth factor * 255"},
        {"name": "cut_codes", "dtype": "uint8", "offset": 19 * n_nodes, "shape": [len(access["set_ids"]), n_nodes],
         "note": "set-major; index into access.levels where the node first loses access; 254 never; 255 no baseline access"}])

    def site_public(site: dict) -> dict:
        keep = {k: site.get(k) for k in ("id", "kind", "name", "lon", "lat", "source", "footprint_m2", "capacity_est", "h", "k",
                                          "freeboard_m", "snap_m", "eligible", "ineligible_reasons", "m")}
        keep["high_ground"] = site.get("m", True) and site.get("flood_stage") == float("inf")
        return keep

    reported_public = [{**{k: r.get(k) for k in ("id", "name_en", "name_th", "type", "tambon", "lon", "lat", "location_method",
                                                 "location_evidence", "location_confidence", "period_used", "evidence_strength",
                                                 "sources", "notes", "reported_capacity_or_occupancy", "role", "first_use",
                                                 "in_access_set", "access_set_note")},
                        "model_check": None if r.get("lat") is None else {
                            "h": r.get("h"), "k": r.get("k"), "freeboard_m": r.get("freeboard_m"), "snap_m": r.get("snap_m"),
                            "m": r.get("m"), "high_ground": r.get("m", True) and r.get("flood_stage") == float("inf"),
                            "floods_at_modelled_peak": (r.get("freeboard_m") is not None and r["freeboard_m"] < 0) or r.get("flood_stage") == 0.0}}
                       for r in reported_all]

    vectors = {}
    for name, fc in (("tambons", tambons), ("roads", roads), ("facilities", facilities)):
        data = json.dumps(fc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        vectors[name] = emit(f"{name}.geojson", data, features=len(fc["features"]))

    # --- Keyframe statistics (district scope: the 8 Mae Sai tambons) -------------------------
    days = []
    for index, kf in enumerate(KEYFRAMES):
        per_tambon = {tid: round(flooded_area_km2(histograms[tid], kf.stage_m, AOI_RES**2), 3) for tid in tambon_ids}
        states = [road_state(f["properties"]["h"], kf.stage_m, f["properties"]["k"]) if f["properties"]["m"] and f["properties"]["h"] is not None else "dry"
                  for f in road_features]
        km = lambda s: round(sum(f["properties"]["len"] for f, st in zip(road_features, states) if st == s) / 1000, 2)  # noqa: E731
        wet_fac = sum(1 for f in facility_features
                      if f["properties"]["m"] and f["properties"]["h"] is not None and kf.stage_m - f["properties"]["h"] > 0)
        exposed = {tid: round(flooded_area_km2(pop_hist[tid], kf.stage_m, 1e6), 1) for tid in tambon_ids}
        access_stats = {}
        for set_index, set_id in enumerate(access["set_ids"]):
            if set_id not in ("reported_2024", f"plan_{access['knee_k']}"):
                continue
            lost = evac.lost_at(access["node_codes"][set_index], kf.stage_m)
            # Same float32 values the page reads from access-nodes.bin; non-vulnerable = total - vulnerable.
            tot = pop_df["total_population"].to_numpy("<f4").astype(float)
            vul = pop_df["vulnerable_population"].to_numpy("<f4").astype(float)
            non = tot - vul
            access_stats[set_id] = {"people_lost_access": round(float(tot[lost].sum())),
                                    "vulnerable_lost": round(float(vul[lost].sum()), 1), "non_vulnerable_lost": round(float(non[lost].sum()), 1)}
        days.append({"date": kf.day.isoformat(), "index": index, "phase": kf.phase, "stage_m": kf.stage_m, "stats": {
            "flooded_km2": round(sum(per_tambon.values()), 3), "tambon_flooded_km2": per_tambon,
            "road_km_impassable": km("impassable"), "road_km_wet": km("wet"), "facilities_wet": wet_fac,
            "people_in_water": round(sum(exposed.values())), "tambon_people_in_water": exposed, "access": access_stats}})

    # --- VIIRS daily flood maps (NOAA/GMU, 375 m) and HII rain gauges --------------------------------
    district_ll = [shape(f["geometry"]) for f in admin["features"]]
    viirs_bounds = transform_bounds(UTM, "EPSG:4326", *AOI_UTM, densify_pts=21)
    wet_cache: dict[float, np.ndarray] = {}

    def model_wet_fraction(dst_transform, dst_shape, stage: float) -> np.ndarray:
        wet = wet_cache.get(stage)
        if wet is None:
            c = codes_aoi.astype(int)
            wet = ((c != CHANNEL_CODE) & (c != NEVER_CODE) & (c * HAND_STEP_M < stage)).astype(np.float32)
            wet_cache[stage] = wet
        out = np.zeros(dst_shape, dtype=np.float32)
        reproject(wet, out, src_transform=aoi.transform, src_crs=UTM, dst_transform=dst_transform, dst_crs="EPSG:4326",
                  resampling=Resampling.average)
        return out

    viirs_grid = Grid("EPSG:3857", extent_3857, 375.0 * MERCATOR_SCALE, exact=True)
    palette = {1: (205, 210, 220, 150), 3: (60, 100, 150, 200), 4: (231, 212, 232, 210), 5: (194, 165, 207, 225),
               6: (153, 112, 171, 235), 7: (118, 42, 131, 245)}
    viirs_days = []
    for day_offset in range(1, 10):  # 10-18 Sep
        day = obs.REPLAY_START + timedelta(days=day_offset)
        matches = sorted((external / "viirs_flood/2024_09").glob(f"WATER_COM_VIIRS_Prj_SVI_d{day:%Y%m%d}_d{day:%Y%m%d}_*_001day_090.tif.zip"))
        if not matches:
            continue
        t_pass = day_offset + obs.VIIRS_OVERPASS_LOCAL_HOUR / 24
        record, codes_v, transform_v = obs.viirs_comparison(matches[0], day, district_ll, model_wet_fraction, stage_at(t_pass), viirs_bounds)
        classes = warp(obs.viirs_png_codes(codes_v).astype(np.float32), transform_v, "EPSG:4326", viirs_grid, Resampling.nearest)
        classes = np.nan_to_num(classes, nan=0).astype(np.uint8)
        rgba = np.zeros((*classes.shape, 4), dtype=np.uint8)
        for value, colour in palette.items():
            rgba[classes == value] = colour
        buf = tempfile.SpooledTemporaryFile()
        Image.fromarray(rgba, mode="RGBA").save(buf, "PNG", optimize=True)
        buf.seek(0)
        record.update(emit(f"viirs-{day:%Y%m%d}.png", buf.read(), width=viirs_grid.width, height=viirs_grid.height))
        record["source_file"] = matches[0].name
        viirs_days.append(record)
    rain = obs.rainfall(external / "hii_rain/2024_09", 11 * 24)

    peak_wet = (codes_aoi != CHANNEL_CODE) & (codes_aoi != NEVER_CODE) & (codes_aoi.astype(int) * HAND_STEP_M < max(k.stage_m for k in KEYFRAMES)) & (zones > 0)
    low_confidence_share = {"peak_flooded_km2": round(float(peak_wet.sum()) * AOI_RES**2 / 1e6, 1),
                            "low_confidence_km2": round(float((peak_wet & lowconf_aoi).sum()) * AOI_RES**2 / 1e6, 1)}

    gistda_stage = stage_at(1.0 + 18.25 / 24)
    gistda_model_km2 = round(sum(flooded_area_km2(histograms[t], gistda_stage, AOI_RES**2) for t in tambon_ids), 1)
    peak_model_km2 = max(d["stats"]["flooded_km2"] for d in days)
    peak_people = max(d["stats"]["people_in_water"] for d in days)
    window_stage = max(stage_at(t / 24) for t in range(4 * 24, 11 * 24))  # Highest modelled stage in 13-19 Sep ICT.
    window_km2 = round(sum(flooded_area_km2(histograms[t], window_stage, AOI_RES**2) for t in tambon_ids), 1)
    window_people = round(sum(flooded_area_km2(pop_hist[t], window_stage, 1e6) for t in tambon_ids))

    south, west = to_ll_3857(display.bounds[0], display.bounds[1])
    north, east = to_ll_3857(display.bounds[2], display.bounds[3])
    return {"layers": layers, "hand": hand_record, "vectors": vectors, "days": days, "histograms": histograms,
            "bounds": [[south, west], [north, east]], "display": {"width": display.width, "height": display.height},
            "s1_meta": s1_meta, "s1_anchor": anchor, "coverage": coverage,
            "reported_meta": {k: reported_doc.get(k) for k in ("status", "compiled", "access_set_rule")},
            "viirs_days": viirs_days, "rainfall": rain, "low_confidence_share": low_confidence_share,
            "external_checks": [
                {"id": "gistda-radarsat2-20240910", "observed": "GISTDA RADARSAT-2 flood analysis, 10 Sep 2024 18:15 (time zone not stated; assumed ICT)",
                 "reported_km2": 9.9, "reported_text": "Mae Sai 6,182 rai", "scope": "Mae Sai district",
                 "role": "calibration_anchor", "model_km2": gistda_model_km2, "model_stage_m": round(gistda_stage, 3),
                 "use": "Calibration anchor for the 10 Sep 18:15 knot, not an independent check.",
                 "urls": ["https://gistda.or.th/news_view.php?n_id=8072&lang=TH", "https://mgronline.com/science/detail/9670000084814"]},
                {"id": "unosat-3991", "observed": "UNOSAT product 3991: cumulative satellite-detected water 13-19 Sep 2024 over Mae Sai District (Pleiades, RCM, TerraSAR-X, Sentinel, Landsat, PlanetScope)",
                 "reported_km2": 70, "reported_people": 13600, "reported_text": "about 70 km2 flood-affected within a 305 km2 analysed area; about 13,600 people exposed (WorldPop 2020); preliminary, not field-validated",
                 "role": "calibration_informed_magnitude_check", "model_km2": window_km2, "model_people_in_water": window_people,
                 "model_window": "Largest modelled extent within 13-19 Sep ICT (the start of the UNOSAT window)",
                 "model_stage_m": round(window_stage, 3), "model_peak_km2": peak_model_km2, "model_peak_people_in_water": peak_people,
                 "use": "Magnitude check over the same window only; UNOSAT is a cumulative multi-sensor observation, not a spatial validation of the model. Calibration-informed, not independent: this figure was known while the stage keyframes were tuned (owner decision, 30 Sep 2026). Its people figure is an exposure estimate, a different measure from the model's residents in water.",
                 "urls": ["https://unosat.org/products/3991"]}],
            "facilities": {"total": len(facility_features), "modelled": sum(1 for f in facility_features if f["properties"]["m"])},
            "roads_not_modelled_km": round(sum(f["properties"]["len"] for f in road_features if not f["properties"]["m"]) / 1000, 2),
            "population": {**population_record, "tambon_histograms": pop_hist,
                           "tambon_totals": {t: round(sum(h)) for t, h in pop_hist.items()}},
            "access": {"nodes": nodes_record, "levels": evac.LEVELS, "threshold_m": evac.ACCESS_THRESHOLD_M, "travel_mode": "walking on passable roads (about 30 min at 4 km/h)",
                       "tambons": tambon_order, "sets": access["set_ids"],
                       "totals": {"population": round(float(pop_df["total_population"].sum())),
                                  "vulnerable": round(float(pop_df["vulnerable_population"].sum()), 1),
                                  "non_vulnerable": round(float(pop_df["non_vulnerable_population"].sum()), 1)}},
            "shelters": {"candidates": [site_public(x) for x in sites], "plan": access["ranking"], "knee_k": access["knee_k"],
                         "demand_people": access["demand_people"], "uncoverable_people": access["uncoverable_people"],
                         "eligible_count": access["eligible_count"], "reported": reported_public,
                         "method": {"evacuation_stage_m": evac.EVACUATION_STAGE_M, "late_evacuation_stage_m": evac.LATE_EVACUATION_STAGE_M, "threshold_m": evac.ACCESS_THRESHOLD_M,
                                    "freeboard_m": evac.SHELTER_FREEBOARD_M, "peak_stage_m": peak_stage,
                                    "m2_per_person": evac.SPHERE_M2_PER_PERSON, "usable_floor_share": evac.USABLE_FLOOR_SHARE,
                                    "max_plan_sites": evac.MAX_PLAN_SITES, "snap_max_m": evac.SNAP_MAX_M}}}


def to_ll_3857(x: float, y: float) -> tuple[float, float]:
    lon, lat = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(x, y)
    return round(lat, 6), round(lon, 6)


PHASES = [
    {"id": "dry", "start": "2024-09-09", "end": "2024-09-09",
     "label": {"en": "Dry / normal", "th": "ช่วงปกติ"},
     "summary": {"en": "Normal conditions in Mae Sai. Northern Thailand had seen heavy rain since mid-August, but the Sai River stayed within safe levels.",
                 "th": "สภาพในแม่สายยังปกติ ภาคเหนือมีฝนตกหนักต่อเนื่องตั้งแต่กลางเดือนสิงหาคม แต่แม่น้ำสายยังอยู่ในระดับปลอดภัย"}},
    {"id": "onset", "start": "2024-09-10", "end": "2024-09-10",
     "label": {"en": "Onset", "th": "เริ่มท่วม"},
     "summary": {"en": "Torrential rain from the remnants of Typhoon Yagi. The Sai River rose fast and overflowed into homes and the border market during the night.",
                 "th": "ฝนตกหนักมากจากอิทธิพลที่เหลือของพายุไต้ฝุ่นยางิ แม่น้ำสายเพิ่มระดับอย่างรวดเร็วและล้นเข้าบ้านเรือนและตลาดชายแดนในช่วงกลางคืน"}},
    {"id": "peak", "start": "2024-09-11", "end": "2024-09-12",
     "label": {"en": "Peak", "th": "ระดับสูงสุด"},
     "summary": {"en": "The worst flash flooding. Very swift, deep water submerged ground floors; power was cut, hundreds of residents were stranded on rooftops and rescue boats struggled against the current.",
                 "th": "ช่วงน้ำท่วมฉับพลันรุนแรงที่สุด กระแสน้ำเชี่ยวและลึกจนท่วมชั้นล่างของอาคาร ไฟฟ้าถูกตัด ประชาชนหลายร้อยคนติดอยู่บนหลังคา และเรือกู้ภัยฝ่ากระแสน้ำได้ยาก"}},
    {"id": "receding", "start": "2024-09-13", "end": "2024-09-15",
     "label": {"en": "Receding", "th": "น้ำลด"},
     "summary": {"en": "Rain eased and the Sai River fell gradually. Main roads reopened to heavy vehicles while low-lying plains stayed under water.",
                 "th": "ฝนเริ่มซาและระดับแม่น้ำสายค่อย ๆ ลดลง ถนนสายหลักเริ่มให้รถขนาดใหญ่สัญจรได้ แต่พื้นที่ราบลุ่มต่ำยังมีน้ำท่วมขัง"}},
    {"id": "gone", "start": "2024-09-16", "end": "2024-09-19",
     "label": {"en": "Mostly receded", "th": "น้ำลดเกือบหมด"},
     "summary": {"en": "UNOSAT monitoring reported that most remaining surface water had disappeared or shrunk sharply by 19 September.",
                 "th": "การติดตามของ UNOSAT รายงานว่าน้ำผิวดินที่เหลือส่วนใหญ่หายไปหรือลดลงอย่างมากภายในวันที่ 19 กันยายน"}},
]

OBSERVATIONS = [
    {"id": "s2-20240905", "sensor": "Sentinel-2B MSI L2A", "kind": "optical", "utc": "2024-09-05T03:58:19Z", "local": "2024-09-05T10:58:19+07:00",
     "label": {"en": "Sentinel-2 true colour · 5 Sep (pre-event)", "th": "Sentinel-2 สีจริง · 5 ก.ย. (ก่อนเกิดเหตุ)"}},
    {"id": "s1-20240906", "sensor": "Sentinel-1A IW GRD VV", "kind": "radar", "utc": "2024-09-06T11:31:06Z", "local": "2024-09-06T18:31:06+07:00",
     "label": {"en": "Sentinel-1 radar · 6 Sep (pre-event)", "th": "Sentinel-1 เรดาร์ · 6 ก.ย. (ก่อนเกิดเหตุ)"}},
    {"id": "s2-20240915", "sensor": "Sentinel-2B MSI L2A", "kind": "optical", "utc": "2024-09-15T03:58:15Z", "local": "2024-09-15T10:58:15+07:00",
     "label": {"en": "Sentinel-2 true colour · 15 Sep (partly cloudy)", "th": "Sentinel-2 สีจริง · 15 ก.ย. (มีเมฆบางส่วน)"}},
    {"id": "s1-20240915", "sensor": "Sentinel-1A IW GRD VV", "kind": "radar", "utc": "2024-09-15T23:16:01Z", "local": "2024-09-16T06:16:01+07:00",
     "label": {"en": "Sentinel-1 radar · 16 Sep 06:16 ICT", "th": "Sentinel-1 เรดาร์ · 16 ก.ย. 06:16 น."}},
]

SOURCES = [
    {"id": "copernicus-dem", "name": "Copernicus DEM GLO-30 (tile N20 E099)", "licence": "Copernicus DEM licence (free, attribution)",
     "timestamp": "2021 release (DSM from 2011-2015 acquisitions)",
     "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA"},
    {"id": "sentinel-2", "name": "Sentinel-2 L2A via Earth Search (tile 47QNC)", "licence": "Copernicus Sentinel data terms (free, full and open)",
     "timestamp": "2024-09-05 / 2024-09-15", "attribution": "Contains modified Copernicus Sentinel data [2024]"},
    {"id": "sentinel-1", "name": "Sentinel-1A IW GRD via Copernicus Data Space Ecosystem", "licence": "Copernicus Sentinel data terms (free, full and open)",
     "timestamp": "2024-09-06 / 2024-09-15 UTC", "attribution": "Contains modified Copernicus Sentinel data [2024]"},
    {"id": "osm", "name": "OpenStreetMap roads and candidate facilities (Geofabrik extract)", "licence": "ODbL 1.0",
     "timestamp": "2026-07-09", "attribution": "© OpenStreetMap contributors"},
    {"id": "cod-ab", "name": "HDX Thailand COD-AB subdistrict boundaries v01", "licence": "CC BY-IGO",
     "timestamp": "valid from 2022-01-22", "attribution": "OCHA / HDX Thailand COD-AB"},
    {"id": "viirs", "name": "NOAA/GMU VIIRS 375 m daily flood-water fraction (10-18 Sep 2024)", "licence": "No licence stated; attribution given",
     "timestamp": "2024-09-10 / 2024-09-18 daily", "attribution": "VIIRS flood product: NOAA JPSS / George Mason University"},
    {"id": "hii-rain", "name": "HII ThaiWater hourly rain gauges MOU189 and DIWO", "licence": "CC BY-NC",
     "timestamp": "2024-09-09 / 2024-09-19 hourly", "attribution": "Hydro-Informatics Institute (HII), ThaiWater"},
    {"id": "chronology", "name": "Event chronology (phases and narrative)", "licence": "Project summary text",
     "timestamp": "compiled 2026-09-27", "attribution": "FloodGuard team summary of public reporting; not independently verified in this study"},
]

ASSUMPTIONS = [
    "Daily water surfaces are a HAND (height above nearest drainage) threshold reconstruction, not observations.",
    "Stage keyframes (metres above the mapped channel) are illustrative values shaped to the event chronology; no gauge record was used. The stage is held at 0 through 9 Sep and rises through the night of 10 Sep.",
    "The stage is the assumed Sai main-stem level at the Mae Sai bridges; tributaries rise k x stage (see the next assumption). Real water levels still differed reach by reach.",
    "Drainage channels are cells with at least 25 km² of upstream area on the 30 m Copernicus DSM; buildings and trees in the DSM bias HAND upward in town.",
    "Roads are impassable when reconstructed depth reaches 0.3 m at any 10 m sample along a 120 m piece (per-sample depth factor; the exported k makes h + 0.3/k equal the earliest sample closure); river-channel samples on bridges are ignored.",
    "Road pieces whose lowest HAND exceeds 4 m never flood under these keyframes and are omitted, except trunk, primary and secondary roads.",
    "The 16 September 06:16 ICT Sentinel-1 pass constrains the size of the late-recession extent only; the two radar passes use different orbit directions.",
    "The onset is shaped by GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (about 9.9 km2 flooded in Mae Sai) and reports of an overnight surge; the 11 Sep 02:00 knot (2.5 m) is illustrative. The model's smallest non-zero extent (flat land within 5 cm of channel level) already exceeds 9.9 km2, so the 18:15 knot is set to the closest level (0.1 m).",
    "Cells that drain off the hydrology domain before meeting a mapped channel use their outlet on the domain edge as the HAND reference (the edge lies outside the replay area).",
    "Where flow routing leaves no path to a channel (large flats), HAND falls back to height above the nearest channel cell.",
    "Stage varies along the river: each cell's water rise is scaled by k = clip((A / A_Sai) ** 0.3, 0.35, 1), where A is the upstream area of its drainage channel and A_Sai the Sai main stem at the Mae Sai bridges (downstream hydraulic geometry). The Ruak east of Mae Sai is inside the hydrology domain (DEM tiles N20E099 + N20E100).",
    "People in water uses WorldPop 2020 (100 m, spread evenly over 10 m cells); it is modelled residential population, not the 2024 population or tourists and traders at the border market.",
    "Evacuation access uses the repo road graph and walking distance: a resident node has access when an open, dry shelter is within 2 km along roads still passable (about 30 minutes on foot); a road closes at 0.3 m of reconstructed depth and a shelter stops serving once water reaches it. Levels are evaluated every 0.05 m of stage.",
    "Shelter candidates are OpenStreetMap public buildings and grounds (schools, places of worship, government offices, community centres; OSM amenity=shelter huts are excluded). A candidate is eligible only if it keeps 0.5 m freeboard at the modelled peak and a road node lies within 400 m. Ranking is greedy maximal coverage of residents whose homes are wet at the peak, within 2 km walking on normal roads (pre-emptive evacuation); late_cumulative_share repeats the check on roads still open at 1.0 m stage.",
    "Shelter capacity = mapped OSM building footprint within the site x 0.5 usable share / 3.5 m² per person (Sphere minimum covered space); OSM building coverage in Mae Sai is sparse, so many capacities are unknown or underestimated.",
    "VIIRS daily flood maps (375 m) are compared with the reconstruction only in clear-sky pixels at a nominal 13:30 ICT; they cannot see flooding under cloud or at street scale.",
    "Filled pits and dead-flat ground in the elevation model that end up less than 0.1 m above their channel (flagged in the raster's B channel) read as wet at almost any stage; they are shown as low-confidence water.",
    "Flash-flood velocity, debris and mud deposition are not modelled.",
]


def compose_manifest(result: dict) -> dict:
    """Assemble ``timeline.json`` with provenance, confidence and assumptions."""
    anchor = result["s1_anchor"]
    return {
        "study_id": "mae-sai-2024-flood-timeline", "revision": "r3", "schema_version": 1,
        "generated_by": "scripts/build_mae_sai_flood_timeline.py",
        "data_mode": "historical_reconstruction", "official_warning": False, "real_time": False, "can_feed_decision_layer": False,
        "confidence": "low",
        "confidence_reason": "Water extents are a terrain-model reconstruction with illustrative stages; only the late-recession size is checked against radar, and spatial agreement there is weak.",
        "source_timestamp": "2024-09-05T03:58:19Z/2024-09-15T23:16:01Z",
        "timezone": "Asia/Bangkok (ICT, UTC+7)",
        "area": {"en": "Mae Sai District, Chiang Rai, Thailand (the image footprint also covers Tachileik, Myanmar)",
                 "th": "อำเภอแม่สาย จังหวัดเชียงราย (ภาพครอบคลุมท่าขี้เหล็ก เมียนมาด้วย)"},
        "bounds": result["bounds"],
        "hand": {**result["hand"], "low_confidence_share": result["low_confidence_share"], "step_m": HAND_STEP_M, "channel_code": CHANNEL_CODE, "never_code": NEVER_CODE,
                 "stream_threshold_km2": STREAM_THRESHOLD_KM2},
        "impassable_depth_m": IMPASSABLE_DEPTH_M,
        "pixel_area_m2": AOI_RES**2,
        "stage_anchors": [{"t": round(t, 6), "stage_m": v} for t, v in stage_anchors()],
        "tambon_coverage": result["coverage"],
        "model_coverage": {"modelled_km2": round(sum(c["modelled_km2"] for c in result["coverage"].values()), 1),
                           "district_km2": round(sum(c["total_km2"] for c in result["coverage"].values()), 1),
                           "reason": "Copernicus DEM tiles N20E099 and N20E100 cover the whole district."},
        "facilities_count": result["facilities"],
        "roads_not_modelled_km": result["roads_not_modelled_km"],
        "phases": PHASES,
        "days": result["days"],
        "observations": [
            {**o, **({"pass": result["s1_meta"][o["id"]]["pass"], "relative_orbit": result["s1_meta"][o["id"]]["relative_orbit"]}
                     if o["id"] in result["s1_meta"] else {})}
            for o in OBSERVATIONS],
        "layers": result["layers"],
        "vectors": result["vectors"],
        "tambon_histograms": result["histograms"],
        "s1_anchor": {**anchor, "reconstruction_stage_at_pass_m": round(stage_at(7 + 6.27 / 24), 3)},
        "population": {**result["population"], "source": "WorldPop Thailand 100 m constrained 2020 (tha_ppp_2020)",
                       "licence": "CC BY 4.0", "timestamp": "2020 estimate",
                       "note": "Modelled residential population, not a census count or the 2024 population."},
        "access": {**result["access"], "scenario_tier": "T1 scenario (model), not observed evacuation outcomes",
                   "confidence": "low",
                   "confidence_reason": "Built on the reconstructed water, WorldPop 2020 residents at road nodes, an OSM road graph with assumed walking access and shelters assumed open for the whole replay.",
                   "source_timestamp": "OSM roads and sites 2026-07-09; WorldPop 2020; water model 2024-09-09/2024-09-19 ICT",
                   "definition": "A resident node loses access when no open, dry shelter of the chosen set is reachable within the threshold on roads that are still passable, having been reachable before the flood."},
        "shelters": {**result["shelters"], "confidence": "low",
                     "confidence_reason": "Candidates are OSM public buildings with sparse footprints; eligibility and coverage use the reconstructed peak and walking distance, not site surveys.",
                     "source_timestamp": "OSM extract 2026-07-09; reported shelters compiled 2026-09-27 from reports dated 2024-09-11 to 2024-10-11",
                     "reported_status": result["reported_meta"]["status"], "reported_compiled": result["reported_meta"]["compiled"],
                     "reported_access_set_rule": result["reported_meta"]["access_set_rule"]},
        "external_checks": result["external_checks"],
        "viirs_daily": {
            "product": "NOAA/GMU VIIRS 375 m daily flood-water fraction composite (block 090)",
            "source_url": "https://jpssflood.gmu.edu/",
            "licence": "NOAA JPSS Proving Ground product; no licence stated on the site, attribution given",
            "attribution": "VIIRS flood product: NOAA JPSS / George Mason University",
            "legend": {"1": "cloud (no observation)", "3": "normal open water", "4": "flood water 1-24 %", "5": "flood water 25-49 %",
                       "6": "flood water 50-74 %", "7": "flood water 75-100 %", "transparent": "clear, dry land or outside"},
            "nominal_overpass": "Daily composite of early-afternoon passes; compared with the model at 13:30 ICT.",
            "comparison_rule": "District only, clear-sky pixels only, permanent water excluded; VIIRS area = sum of flood fraction x pixel area; model area = modelled out-of-channel wet fraction averaged onto the same 375 m pixels.",
            "caveat": "375 m optical data under-detects narrow, shallow, urban or vegetated flooding and sees nothing under cloud; agreement or disagreement is indicative only.",
            "days": result["viirs_days"],
        },
        "rainfall": {**result["rainfall"], "source": "HII ThaiWater open data, hourly rain gauges",
                     "source_url": "https://tiservice.hii.or.th/opendata/", "licence": "CC BY-NC (per the HII open-data catalogue)",
                     "units": "mm per hour; index 0 = 9 Sep 00:00-01:00 ICT", "note": "Observed rainfall (forcing), not flooding."},
        "external_references": [
            {"name": "UNOSAT 4009: water extents 1 Aug-22 Oct 2024, Chiang Rai (GDB/SHP, HDX)", "url": "https://data.humdata.org/dataset/water-extents-from-1-aug-2024-to-22-october-2024-over-chiang-rai-province", "note": "Season envelope (scenario per decision D3); not shown until the CC BY-SA rights record (D2) is signed."},
            {"name": "UNOSAT 3969: preliminary flood impact assessment, Mae Sai (Pleiades 15 Sep)", "url": "https://unosat.org/static/unosat_filesystem/3969/UNOSAT_Preliminary_Assessment_Report_TC20240912THA_ChiangRai_16Sep2024.pdf"},
            {"name": "International Charter activation 912 (Typhoon Yagi, Thailand)", "url": "https://disasterscharter.org/activations/flood-in-thailand-activation-912-"},
            {"name": "HII ThaiWater September 2024 Chiang Rai flood event page (rainfall and Kok River hydrographs)", "url": "https://www.thaiwater.net/uploads/contents/current/2024/FloodChiangrai_Sep2024/"}],
        "gauge_note": "No public hourly Sai River water-level record for Sep 2024 was found (HII MYA004 installed 2025; RID Kh.50 closed; DWR Ban Mae Sai EWS unverified), so stage values remain illustrative.",
        "sources": SOURCES,
        "assumptions": ASSUMPTIONS,
        "limitations": [
            "Not a real-time product or an official warning; for preparedness learning and post-event prioritisation only.",
            "No high-resolution satellite image exists for 10-14 September over Mae Sai in these inputs; VIIRS (375 m) was cloud-covered on 10-11 Sep and mostly cloud-covered on 12-14 Sep, so onset and peak extents are not observed.",
            "Statistics cover only the modelled parts of the eight Mae Sai subdistricts (see model_coverage); roads and facilities outside the model are flagged m=false and excluded.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--external-root", default=os.environ.get("FLOODGUARD_EXTERNAL_DATA"),
                        help="Folder holding the external rasters (or set FLOODGUARD_EXTERNAL_DATA).")
    parser.add_argument("--out", default=str(ROOT / OUT_REL))
    args = parser.parse_args()
    if not args.external_root:
        parser.error("--external-root or FLOODGUARD_EXTERNAL_DATA is required")
    result = build(Path(args.external_root), Path(args.out))
    manifest = compose_manifest(result)
    (Path(args.out) / "timeline.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest["s1_anchor"], indent=1))
    for d in result["days"]:
        s = d["stats"]
        print(d["date"], d["phase"], d["stage_m"], s["flooded_km2"], s["road_km_impassable"], s["road_km_wet"], s["facilities_wet"])


if __name__ == "__main__":
    main()
