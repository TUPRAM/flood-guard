#!/usr/bin/env python
"""Build the Mae Sai September 2024 day-by-day flood timeline assets for the web Studio.

Inputs
------
* External files (kept outside Git), under ``--external-root`` or ``FLOODGUARD_EXTERNAL_DATA``:
  - ``open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif`` and
    ``..._N20_00_E100_00_DEM.tif`` (both tiles: the east tile covers the Ruak and the east of the district)
  - ``earth_search/mae_sai_2024/S2B_47QNC_{20240905,20240915}_0_L2A/{red,green,blue,swir16,scl}.tif`` (true colour;
    green, short-wave infrared and the scene classification also feed the Sentinel-2 water check)
  - ``cdse/mae_sai_2024/S1A_IW_GRDH_1SDV_*_COG.SAFE.zip`` (6 and 15 September 2024 UTC)
  - ``open_context/worldpop_population/tha_ppp_2020.tif``
  - ``open_context/osm_geofabrik/thailand-latest.osm.pbf`` (shelter candidate sites: the bake reads the
    multipolygons and points inside the replay area straight from the extract on every run and keeps no cache)
  - ``viirs_flood/2024_09/WATER_COM_VIIRS_Prj_SVI_d*_001day_090.tif.zip`` (10 to 18 September 2024)
  - ``hii_rain/2024_09/{MOU189,DIWO}.csv`` and the two ``*_0all_stn_metadata.csv`` station lists
  - ``unosat/unosat_4009_chiang_rai_2024/FL20240912THA_GDB.zip`` (UNOSAT/GISTDA product 4009: only its layer
    ``CHIANGRAI_20240801_20241012_AccumulatedFlood`` is read, as the 2024 season envelope)
* In-repo files: ``outputs/mae_sai_admin_context.geojson``, ``outputs/mae_sai_road_risk.geojson``,
  ``outputs/mae_sai_facilities.geojson``, ``outputs/mae_sai_access_edges.csv``,
  ``outputs/mae_sai_population_nodes.csv``, ``outputs/mae_sai_reported_shelters_2024.json`` and
  ``docs/proposal_execution/rights_basis_4009_v1.json`` (the rights record of UNOSAT/GISTDA product 4009: the
  bake stops unless the owners have confirmed it, and the licence, the credit and the change notice of the derived
  files come from it). When a local check of the
  shelter candidates has been returned and imported (``scripts/import_shelter_validation.py``), the bake also reads
  ``outputs/mae_sai_shelter_validation.json``; without that file the manifest says the check was not conducted.

Outputs (``apps/web/public/studies/mae-sai-2024-timeline/r4/``): a HAND code raster, dated
Sentinel-1/2 image layers, a hillshade, VIIRS daily maps, a residents raster, the access node file,
sampled road/facility/tambon vectors and ``timeline.json``; and, in ``exports/``, the export pack for
spreadsheet and GIS users (``floodguard.replay_exports``): three shelter plan tables, one GeoJSON of the
sites, modelled road inundation and modelled access loss by hour, the shelter-candidate verification sheet
and a licence README. The export files are listed in the manifest with their hashes, are covered by
``--verify`` and sit outside the replay's precache budget. ``timeline.json`` also holds the Sentinel-2 water check
(``s2_crosscheck``): water or saturated mud (MNDWI above 0) on the clear pixels of the 5 Sep and 15 Sep scenes inside
the district, with the modelled water at the 15 Sep acquisition time beside it. It writes no raster; the comparison
is indicative and the block says so.

The season-envelope stage (``scripts/mae_sai_timeline_unosat4009.py``) writes three more files into their own folder,
``unosat4009/``: ``envelope.png`` (product 4009's accumulated water, August to October 2024, clipped to the district
and drawn on the water grid as a 1-bit raster), ``envelope.json`` (its areas and the plausibility comparison with the
modelled water) and ``LICENSE`` (CC BY-SA 4.0, the credit and the change notice). They are a scenario layer (SCN-ENV),
never an observation for a replay day. ``timeline.json`` names them by address, hash and size only: no figure derived
from the product is in the manifest or in the export pack.

Evidence fields
---------------
``timeline.json`` follows ``packages/contracts/schemas/case-replay-timeline.schema.json``. Besides the
data it says what the data is: ``operational_status`` (non-operational), ``accepted_fpps`` and
``accepted_action_class`` (both null: the replay computes no score and no action class),
``evidence_blocks`` (lane, tier, temporal relation and source timestamp for every part),
``exploratory_knowledge`` (which external figures were used or known while the model was tuned),
``publication_eligibility`` (a licence per input) and ``input_sha256`` (the input receipt's hashes).
The bake refuses to write a manifest that breaks these rules (``floodguard.replay_manifest``).

Reproducibility
---------------
Every bake writes an input receipt (``docs/mae_sai_timeline_r4_input_receipt.json``): the path relative
to its root, the size and the SHA-256 of every input file the bake opened, plus library versions and
the SHA-256 of the bake's own source files. ``--verify`` bakes again into a temporary folder and
compares it byte for byte with the committed revision folder. It never writes to that folder and
exits non-zero on any difference.

``generated_at`` is never read from the machine clock, because a clock value would make a
byte-for-byte rebuild impossible. It is declared with ``--generated-at`` and recorded in the input
receipt. ``--verify`` carries the recorded value. A plain bake without the argument carries it only when
the bake reproduces every recorded output file byte for byte; when any output differs (an input, a bake
source or a library changed) the bake stops, writes nothing and asks for ``--generated-at``, because the
recorded time would no longer be true. With no recorded value the bake uses the newest dated input.
``git_commit`` is null in the manifest: a file
cannot hold the hash of the commit that adds it, so the receipt identifies the bake sources by content
and ``git log -1 -- <file>`` names the commit.

The daily water surface is a HAND threshold reconstruction driven by illustrative stage keyframes.
It is not an observation, a validated flood extent, a real-time product or an official warning.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
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

from floodguard.bake_receipt import (  # noqa: E402
    RECEIPT_SCHEMA,
    InputReceipt,
    compare_directories,
    directory_listing,
    input_differences,
    library_versions,
    source_differences,
    source_hashes,
    version_differences,
)
from floodguard.flood_timeline import (  # noqa: E402
    DEPTH_FACTOR_EXPONENT,
    DEPTH_FACTOR_FLOOR,
    HAND_STEP_M,
    IMPASSABLE_DEPTH_M,
    KEYFRAMES,
    CHANNEL_CODE,
    NEVER_CODE,
    decode_hand,
    encode_hand,
    flooded_area_km2,
    sentinel2_l2a_reflectance,
    stage_anchors,
    stage_at,
    road_state,
    depth_factor,
)
import floodguard.replay_exports as replay_exports  # noqa: E402
import floodguard.shelter_validation as shelter_validation  # noqa: E402
from floodguard.replay_manifest import (  # noqa: E402
    LANES,
    SCENARIO_FIELDS_KEY,
    SCENARIO_TIER,
    ReplayManifestError,
    evidence_problems,
    newest_timestamp,
    normalise_timestamp,
    schema_problems,
    season_envelope_problems,
    shelter_plan_problems,
)
from floodguard.rights_basis import (  # noqa: E402
    RIGHTS_BASIS_4009_PATH,
    file_sha256,
    load_rights_basis,
    owner_confirmed,
    require_owner_confirmation,
    unconfirmed_product_citations,
)
from floodguard.season_envelope import COMPARISON_ROLE, ENVELOPE_LANE  # noqa: E402
import mae_sai_timeline_evacuation as evac  # noqa: E402
import mae_sai_timeline_observations as obs  # noqa: E402
import mae_sai_timeline_unosat4009 as unosat4009  # noqa: E402

REVISION = "r4"
STUDY_ID = "mae-sai-2024-flood-timeline"
OUT_REL = Path(f"apps/web/public/studies/mae-sai-2024-timeline/{REVISION}")
RECEIPT_REL = Path(f"docs/mae_sai_timeline_{REVISION}_input_receipt.json")
SCHEMA_REL = Path("packages/contracts/schemas/case-replay-timeline.schema.json")
SCHEMA_ID = "https://floodguard.th/contracts/case-replay-timeline.schema.json"
RIGHTS_RECORD = ROOT / RIGHTS_BASIS_4009_PATH
"""The product 4009 rights record the bake reads. The bake stops unless the owners have confirmed it."""
ENVELOPE_CHECK_ID = "unosat-4009-season-envelope"
BOUNDARY_SOURCE = "the eight subdistricts of HDX Thailand COD-AB v01"
BOUNDARY_SOURCE_THAI = "ตำบลทั้งแปดตาม HDX Thailand COD-AB v01"
GENERATED_BY = "scripts/build_mae_sai_flood_timeline.py"
Track = Callable[[Path], Path]
HREF_PREFIX = f"/studies/mae-sai-2024-timeline/{REVISION}/"
# A pixel with any visible band at or above this reflectance is left out of the display stretch. r3 wrote 0.25 but
# applied it to (DN - 1000) / 10000, so the cut it really made was DN 3500 = 0.35; r4 keeps that cut and the same picture.
S2_CLOUD_REFLECTANCE = 0.35
SAI_REFERENCE_LONLAT = (99.8826, 20.4460)  # Sai River at the Mae Sai border bridges (main-stem reference reach).
REPORTED_SHELTERS = Path("outputs/mae_sai_reported_shelters_2024.json")
# Written by scripts/import_shelter_validation.py once a local checker returns the verification sheet. Absent: not conducted.
SHELTER_VALIDATION = Path("outputs/mae_sai_shelter_validation.json")
REPLAY_HOURS = 11 * 24  # The replay's hourly grid: 9 Sep 00:00 to 19 Sep 23:00 ICT.
EVENT_START = "2024-09-09T00:00:00+07:00"  # Replay origin (t = 0).
EVENT_END = "2024-09-20T00:00:00+07:00"  # End of the replay and of the last rain hour (19 Sep 24:00 ICT).
OSM_EXTRACT_DATE = "2026-07-09"
OSM_PBF_REL = "open_context/osm_geofabrik/thailand-latest.osm.pbf"
CHRONOLOGY_COMPILED = "2026-09-27"
# tha_ppp_2020.tif is WorldPop's unconstrained top-down grid: every land cell in the replay area holds a positive value.
WORLDPOP_SOURCE = "WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020)"
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
S1_STAMPS = {"s1-20240906": "2024-09-06T11:31:06Z", "s1-20240915": "2024-09-15T23:16:01Z"}
S1_PAIR = f"{S1_STAMPS['s1-20240906']}/{S1_STAMPS['s1-20240915']}"
# The Sentinel-2 water check: the scene before the flood and the first scene after the river fell.
S2_CHECK_PRE, S2_CHECK_EVENT = "s2-20240905", "s2-20240915"
S2_CHECK_PAIR = f"{S2_SCENES[S2_CHECK_PRE][1]}/{S2_SCENES[S2_CHECK_EVENT][1]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def untracked(path: Path) -> Path:
    """Default ``track`` callback: open the input without recording it."""
    return path


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


def sentinel2_rgb(scene_dir: Path, grid: Grid, track: Track = untracked) -> np.ndarray:
    bands = []
    for name in ("red", "green", "blue"):
        with rasterio.open(track(scene_dir / f"{name}.tif")) as src:
            aoi = transform_bounds(grid.crs, src.crs, *grid.bounds, densify_pts=21)
            win = window_from_bounds(*aoi, transform=src.transform).round_offsets().round_lengths()
            win = Window(win.col_off - 8, win.row_off - 8, win.width + 16, win.height + 16)
            dn = src.read(1, window=win)
            # Earth Search L2A COGs already have the baseline-04.00 offset removed: reflectance = DN / 10000.
            bands.append(warp(sentinel2_l2a_reflectance(dn), src.window_transform(win), src.crs, grid))
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


def build(external: Path, out_dir: Path, track: Track = untracked) -> dict:
    """Bake every asset into ``out_dir``. ``track`` is called with each input file as it is opened.

    The product 4009 rights record is read first: unless the owners have confirmed it, the bake stops before it
    opens any other input or writes any file (``floodguard.rights_basis.RightsNotConfirmedError``).
    """
    rights = load_rights_basis(track(RIGHTS_RECORD))
    require_owner_confirmation(rights)
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
            [track(external / "open_context/copernicus_dem_glo30" / tile) for tile in DEM_TILES], Path(tmp))

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
    rgb = {key: sentinel2_rgb(external / "earth_search/mae_sai_2024" / scene, display, track) for key, (scene, _) in S2_SCENES.items()}
    clear = np.all(rgb["s2-20240905"] < S2_CLOUD_REFLECTANCE, axis=0)  # Stretch on cloud-free land so clouds do not darken it.
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
        s1[key], s1_meta[key] = sentinel1_vv(track(external / "cdse/mae_sai_2024" / name), display)
    db_lo, db_hi = np.nanpercentile(s1["s1-20240906"], [2, 98])
    s1_stamps = S1_STAMPS
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
    layers.append(emit("s1-change-rgb.webp", buf.read(), id="s1-change", kind="sentinel-1-change", date=S1_PAIR))

    # --- Vectors --------------------------------------------------------------------------
    admin = json.loads(track(ROOT / "outputs/mae_sai_admin_context.geojson").read_text(encoding="utf-8"))
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

    roads_src = json.loads(track(ROOT / "outputs/mae_sai_road_risk.geojson").read_text(encoding="utf-8"))
    road_features = []
    ways = []  # One record per OpenStreetMap way, for the export pack; the legacy candidate columns are never read.
    peak_road_stage = max(k.stage_m for k in KEYFRAMES)
    for f in roads_src["features"]:
        props = f["properties"]
        cls = props.get("road_class")
        if cls not in ROAD_CLASSES:
            continue
        line = shp_transform(to_utm, shape(f["geometry"]))
        pieces = max(1, math.ceil(line.length / ROAD_PIECE_M))
        way = {"road_id": props["road_id"], "road_name": props.get("road_name") or "", "road_class": cls,
               "bridge_flag": bool(props.get("bridge_flag")), "tambon_id": props["subdistrict_id"], "length_m": line.length, "pieces": []}
        ways.append(way)
        for p in range(pieces):
            piece = substring(line, p * line.length / pieces, (p + 1) * line.length / pieces)
            if not isinstance(piece, LineString) or piece.length == 0:
                continue
            steps = np.linspace(0, piece.length, max(2, int(piece.length // 10) + 1))
            pts = np.array([piece.interpolate(d).coords[0] for d in steps])
            h, kf = evac.sample_road(codes_aoi, k_aoi, aoi, pts[:, 0], pts[:, 1])
            modelled = sample_mask(valid_aoi, aoi, pts[:, 0], pts[:, 1])
            way["pieces"].append((h, kf, modelled))
            if cls not in ROAD_KEEP_ALWAYS and (not modelled or h is None or h > ROAD_MAX_HAND_M):
                # A piece the page does not draw must never be impassable, or the export would disagree with the page.
                if modelled and h is not None and road_state(h, peak_road_stage, kf) == "impassable":
                    raise ReplayManifestError(f"a piece of way {props['road_id']} is left off the page but is impassable at the modelled peak")
                continue
            coords = [[round(x, 5), round(y, 5)] for x, y in (to_ll(*c) for c in piece.coords)]
            road_features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                                  "properties": {"c": cls, "h": h, "k": kf, "m": modelled, "len": round(piece.length), "t": props["subdistrict_id"],
                                                 **({"n": props["road_name"]} if props.get("road_name") and cls in ROAD_CLASSES[:4] else {})}})
    roads = {"type": "FeatureCollection", "features": road_features}

    fac_src = json.loads(track(ROOT / "outputs/mae_sai_facilities.geojson").read_text(encoding="utf-8"))
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
    worldpop = track(external / "open_context/worldpop_population/tha_ppp_2020.tif")
    coarse_pop, pop10 = evac.population_grid(worldpop, aoi)
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
    graph = evac.build_graph(ROOT, to_utm, codes_aoi, k_aoi, aoi, track)
    # Shelter candidates come straight from the Geofabrik extract, cut to the replay area on every run. No derived
    # cache is kept: a cached cut can outlive a change of the replay area and cannot be rebuilt byte for byte.
    import pyogrio
    pbf = track(external / OSM_PBF_REL)
    osm_bbox = transform_bounds(UTM, "EPSG:4326", *AOI_UTM, densify_pts=21)
    sites = evac.shelter_candidates(pyogrio.read_dataframe(pbf, layer="multipolygons", bbox=osm_bbox),
                                    pyogrio.read_dataframe(pbf, layer="points", bbox=osm_bbox),
                                    track(ROOT / "outputs/mae_sai_facilities.geojson"), to_utm)
    evac.evaluate_sites(sites, graph, codes_aoi, k_aoi, aoi, peak_stage, valid_aoi)
    reported_doc = json.loads(track(ROOT / REPORTED_SHELTERS).read_text(encoding="utf-8")) if (ROOT / REPORTED_SHELTERS).exists() else {"shelters": []}
    reported_all = reported_doc["shelters"]
    located = [r for r in reported_all if r.get("lat") is not None and r.get("lon") is not None]
    for r in located:
        r["x"], r["y"] = to_utm(r["lon"], r["lat"])
    evac.evaluate_sites(located, graph, codes_aoi, k_aoi, aoi, peak_stage, valid_aoi)
    counted = [r for r in located if r.get("in_access_set", True)]
    access = evac.plan_and_access(sites, counted, graph, peak_stage)
    coverage_order = [entry["candidate_id"] for entry in access["ranking"]]
    capacitated = evac.capacity_aware_plan(sites, graph, peak_stage, coverage_order)
    if capacitated["demand_people"] != access["demand_people"]:
        raise ReplayManifestError("the capacity-aware plan and the coverage ranking count a different demand")
    robustness = evac.what_if_plans(sites, graph, codes_aoi, k_aoi, aoi, valid_aoi, evac.WHAT_IF_STAGES_M, peak_stage, coverage_order)
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
                                                 "in_access_set", "access_set_note", "access_set_note_th")},
                        "model_check": None if r.get("lat") is None else {
                            "h": r.get("h"), "k": r.get("k"), "freeboard_m": r.get("freeboard_m"), "snap_m": r.get("snap_m"),
                            "m": r.get("m"), "high_ground": r.get("m", True) and r.get("flood_stage") == float("inf"),
                            "floods_at_modelled_peak": (r.get("freeboard_m") is not None and r["freeboard_m"] < 0) or r.get("flood_stage") == 0.0}}
                       for r in reported_all]

    sites_public = [site_public(x) for x in sites]
    candidate_set = replay_exports.candidate_set_sha256(sites_public)
    validation_path = ROOT / SHELTER_VALIDATION
    verification = shelter_check(json.loads(track(validation_path).read_text(encoding="utf-8")) if validation_path.exists() else None,
                                 sites_public, candidate_set)

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
        record, codes_v, transform_v = obs.viirs_comparison(track(matches[0]), day, district_ll, model_wet_fraction, stage_at(t_pass), viirs_bounds)
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
    rain = obs.rainfall(external / "hii_rain/2024_09", 11 * 24, track)

    # --- Sentinel-2 water check: MNDWI on clear pixels, before the flood and after the river fell ------------
    s2_dirs = {key: external / "earth_search/mae_sai_2024" / scene for key, (scene, _) in S2_SCENES.items()}
    s2_t = replay_days(S2_SCENES[S2_CHECK_EVENT][1])
    s2_stage = stage_at(s2_t)
    aoi_codes = codes_aoi.astype(int)
    s2_model_wet = (aoi_codes != CHANNEL_CODE) & (aoi_codes != NEVER_CODE) & (aoi_codes * HAND_STEP_M < s2_stage)
    # Permanent water is the model's own rule: mapped drainage-channel cells are left out, as in every flooded area.
    s2_check = obs.sentinel2_water_check(s2_dirs[S2_CHECK_PRE], s2_dirs[S2_CHECK_EVENT], UTM, AOI_UTM, zones > 0,
                                         codes_aoi == CHANNEL_CODE, s2_model_wet, AOI_RES, track)
    s2_check["model_at_event_scene"] = {"model_t": round(s2_t, 4), "model_stage_m": round(s2_stage, 3), **s2_check["model_at_event_scene"]}

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

    # --- Season envelope (UNOSAT/GISTDA product 4009, SCN-ENV): a scenario layer and a plausibility comparison ---
    # Its figures leave this function only for the stage's own files; nothing of them reaches timeline.json or the exports.
    envelope_data = unosat4009.season_envelope(
        external, rights, admin["features"], statistics_grid=aoi, raster_grid=water, codes=codes_aoi, zones=zones, tambon_ids=tambon_ids,
        low_confidence=lowconf_aoi, residents=pop10, population=worldpop, channel_code=CHANNEL_CODE, never_code=NEVER_CODE,
        hand_step_m=HAND_STEP_M,
        stages=[{"id": "modelled_peak", "model_stage_m": max(k.stage_m for k in KEYFRAMES),
                 "model_extent": "The modelled peak (illustrative stage, 12 Sep 2024)", "model_residents_in_water": peak_people},
                {"id": "largest_extent_13_19_sep", "model_stage_m": window_stage,
                 "model_extent": "Largest modelled extent within 13-19 Sep ICT"}],
        clip_source=BOUNDARY_SOURCE, track=track)

    south, west = to_ll_3857(display.bounds[0], display.bounds[1])
    north, east = to_ll_3857(display.bounds[2], display.bounds[3])
    return {"rights_4009": rights_status(rights), "season_envelope_data": {"figures": envelope_data, "rights": rights,
                                                                          "raster_cell_m": water.res / MERCATOR_SCALE},
            "layers": layers, "hand": hand_record, "vectors": vectors, "days": days, "histograms": histograms,
            "bounds": [[south, west], [north, east]], "display": {"width": display.width, "height": display.height},
            "s1_meta": s1_meta, "s1_anchor": anchor, "coverage": coverage,
            "reported_meta": {k: reported_doc.get(k) for k in ("status", "compiled", "access_set_rule", "licence_note")},
            "viirs_days": viirs_days, "rainfall": rain, "low_confidence_share": low_confidence_share, "s2_check": s2_check,
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
            "export_data": {
                "ways": ways, "tambons": [dict(f["properties"]) for f in tambons["features"]],
                "node_tambon": node_tambon, "node_population": pop_df["total_population"].to_numpy("<f4").astype(float),
                "cut_codes": {set_id: access["node_codes"][index] for index, set_id in enumerate(access["set_ids"])
                              if set_id in ("reported_2024", f"plan_{access['knee_k']}")},
                "reported_licence": reported_doc.get("licence_note")},
            "shelters": {"candidates": sites_public, "plan": access["ranking"], "knee_k": access["knee_k"],
                         "demand_people": access["demand_people"], "uncoverable_people": access["uncoverable_people"],
                         "eligible_count": access["eligible_count"], "reported": reported_public,
                         "capacitated": capacitated, "robustness": robustness, "verification": verification,
                         "method": {"evacuation_stage_m": evac.EVACUATION_STAGE_M, "late_evacuation_stage_m": evac.LATE_EVACUATION_STAGE_M, "threshold_m": evac.ACCESS_THRESHOLD_M,
                                    "freeboard_m": evac.SHELTER_FREEBOARD_M, "peak_stage_m": peak_stage,
                                    "m2_per_person": evac.SPHERE_M2_PER_PERSON, "usable_floor_share": evac.USABLE_FLOOR_SHARE,
                                    "max_plan_sites": evac.MAX_PLAN_SITES, "snap_max_m": evac.SNAP_MAX_M}}}


VERIFICATION_NOT_CONDUCTED = ("No verification sheet has been returned: the local check of the shelter candidates was not conducted. "
                              "Every capacity is an unverified estimate and every site is a candidate to verify on the ground.")
VERIFICATION_NOT_USED = ("The coverage ranking, the capacity-aware plan, the what-if levels and the download tables were computed without this "
                         "check: a site reported not usable is still ranked, and a reported capacity does not replace the footprint estimate.")
"""Said with every conducted check until a plan restricted to checked sites exists (roadmap P2-8)."""


def shelter_check(document: dict | None, candidates: list[dict], candidate_set: str) -> dict:
    """What the manifest says about the local check of the shelter candidates.

    ``document`` is the file ``scripts/import_shelter_validation.py`` writes from a returned sheet, or ``None`` when
    no sheet has been returned: the check was then not conducted, and no result is implied. A document that answers
    another candidate list, or holds anything outside the whitelist, stops the bake. A conducted check carries the
    document's confidence, its reason and its assumptions, and says that the plans do not use it. Free-text notes are
    never copied: only whether a note was given.
    """
    listed = replay_exports.sheet_candidates(candidates)
    base = {"label_template": replay_exports.VERIFICATION_LABEL, "sheet": "shelter_candidate_verification_sheet",
            "candidate_set_sha256": candidate_set, "candidates_listed": len(listed)}
    if document is None:
        return {"status": shelter_validation.STATUS_NOT_CONDUCTED, **base, "statement": VERIFICATION_NOT_CONDUCTED, "checked": []}
    problems = shelter_validation.document_problems(document, [site["id"] for site in listed], candidate_set)
    if problems:
        raise ReplayManifestError(f"{SHELTER_VALIDATION.as_posix()} cannot be published:\n  " + "\n  ".join(problems))
    checked = [{**{key: row[key] for key in shelter_validation.DERIVED_KEYS},
                "label": shelter_validation.check_label(row["checked_by_role"], row["checked_on"])} for row in document["rows"]]
    return {"status": shelter_validation.STATUS_CONDUCTED, **base,
            "statement": (f"A local check of {len(checked)} of the {len(listed)} candidates was returned and imported on {document['imported_on']}. "
                          "It is reported by role and is not an official shelter register; a candidate without a row was not checked."),
            "confidence": document["confidence"], "confidence_reason": document["confidence_reason"],
            "assumptions": [*document["assumptions"], VERIFICATION_NOT_USED],
            "source_timestamp": document["source_timestamp"], "imported_on": document["imported_on"],
            "returned_file_sha256": document["returned_file"]["sha256"], "counts": dict(document["counts"]), "checked": checked}


def export_sources(reported_licence: str | None) -> list[dict]:
    """The manifest's sources plus the reported-shelter list, with the licence each export header quotes."""
    return [*SOURCES, {"id": "reported-shelters", "name": "Shelters reported in use in September 2024 (FloodGuard desk research)",
                       "licence": reported_licence or "Facts with citations",
                       "attribution": "FloodGuard desk research of public reporting, sources linked per site"}]


def write_exports(result: dict, out_dir: Path, generated_at: str, inputs: list[dict]) -> dict:
    """Write the export pack into ``out_dir/exports`` and return what the manifest lists about it.

    The files are written by ``floodguard.replay_exports`` from the build result: nothing here reads the rain
    gauges, the VIIRS maps or product 4009, and a file that breaks a header, licence or column rule is not written.
    """
    data, shelters = result["export_data"], result["shelters"]
    knee_k = shelters["knee_k"]
    context = replay_exports.ExportContext(
        study_id=STUDY_ID, revision=REVISION, generated_at=generated_at, generated_by=GENERATED_BY,
        receipt_path=RECEIPT_REL.as_posix(),
        repo_folder=(OUT_REL / replay_exports.EXPORT_FOLDER).as_posix(), inputs=inputs,
        sources=export_sources(data["reported_licence"]),
        hourly_stages=[stage_at(hour / 24) for hour in range(REPLAY_HOURS)], event_start=EVENT_START,
        osm_extract_date=OSM_EXTRACT_DATE, reported_compiled=result["reported_meta"]["compiled"],
        impassable_depth_m=IMPASSABLE_DEPTH_M, road_classes=ROAD_CLASSES, ways=data["ways"], tambons=data["tambons"],
        node_tambon=data["node_tambon"], node_population=data["node_population"], cut_codes=data["cut_codes"],
        level_step_m=evac.LEVELS[1] - evac.LEVELS[0], knee_k=knee_k, candidates=shelters["candidates"], plan=shelters["plan"],
        capacitated={**capacitated_meta(shelters["verification"]), **shelters["capacitated"]},
        robust_core=shelters["robustness"]["core_by_k"][knee_k - 1], reported=shelters["reported"],
        peak_stage_m=shelters["method"]["peak_stage_m"], walk_limit_m=evac.ACCESS_THRESHOLD_M,
        freeboard_m=evac.SHELTER_FREEBOARD_M, snap_max_m=evac.SNAP_MAX_M,
        verification_status=shelters["verification"]["status"])
    files = replay_exports.export_pack(context)
    folder = out_dir / replay_exports.EXPORT_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for file in files:
        (folder / file.name).write_bytes(file.data)
    prefix = f"{HREF_PREFIX}{replay_exports.EXPORT_FOLDER}/"
    return {"folder": prefix, "file_count": len(files), "bytes": sum(len(file.data) for file in files),
            "files": [file.record(prefix) for file in files]}


def write_season_envelope(result: dict, out_dir: Path, generated_at: str) -> dict[str, dict]:
    """Write the three product 4009 files into ``out_dir/unosat4009`` and return what the manifest says about them.

    The files are written by ``scripts/mae_sai_timeline_unosat4009.py`` under CC BY-SA 4.0, with the credit and a change
    notice from the rights record. The manifest gets each file's address, SHA-256 and size and nothing else: every
    figure derived from the product stays in ``envelope.json``.
    """
    data = result["season_envelope_data"]
    return unosat4009.write_files(
        data["figures"], out_dir, rights=data["rights"],
        rights_record={"path": RIGHTS_BASIS_4009_PATH.as_posix(), "sha256": file_sha256(RIGHTS_RECORD),
                       "confirmed_on": data["rights"]["owner_confirmation"]["confirmed_on"]},
        study_id=STUDY_ID, revision=REVISION, generated_at=generated_at, href_prefix=HREF_PREFIX, bounds=result["bounds"],
        raster_cell_m=data["raster_cell_m"], worldpop_source=WORLDPOP_SOURCE, sources=SOURCES, clip_geometry_thai=BOUNDARY_SOURCE_THAI)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def short_date(iso_date: str) -> str:
    """``2026-09-30`` as ``30 Sep 2026`` (fixed English month names, whatever the machine's locale)."""
    year, month, day = (int(part) for part in iso_date.split("-"))
    return f"{day} {MONTHS[month - 1]} {year}"


def rights_status(record: dict) -> dict:
    """What the manifest says about product 4009, read from its rights record (``floodguard.rights_basis``)."""
    confirmation = record["owner_confirmation"]
    return {"confirmed": owner_confirmed(record), "confirmed_on": confirmation.get("confirmed_on"),
            "signed_on": record["signed_decision"]["signed_on"], "licence": record["licence"]["name"],
            "licence_url": record["licence"]["url"], "credit": record["required_attribution_text"],
            "product_url": record["product"]["product_url"], "dataset_url": record["hdx"]["dataset_url"],
            "source_timestamp": record["source_timestamp"],
            "reply_quote": record["provider_reply"]["quote"], "reply_relayed_on": record["provider_reply"]["relayed_on"],
            "record": RIGHTS_BASIS_4009_PATH.as_posix()}


def replay_days(stamp: str) -> float:
    """Days from the replay origin (9 Sep 2024 00:00 ICT) to an ISO 8601 instant."""
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (moment - datetime.fromisoformat(EVENT_START)).total_seconds() / 86400


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
    {"id": "copernicus-dem", "name": "Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100)", "licence": "Copernicus DEM licence (free, attribution)",
     "timestamp": "2021 release (DSM from 2011-2015 acquisitions)",
     "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA"},
    {"id": "sentinel-2", "name": "Sentinel-2 L2A via Earth Search (tile 47QNC)", "licence": "Copernicus Sentinel data terms (free, full and open)",
     "timestamp": "2024-09-05 / 2024-09-15", "attribution": "Contains modified Copernicus Sentinel data [2024]"},
    {"id": "sentinel-1", "name": "Sentinel-1A IW GRD via Copernicus Data Space Ecosystem", "licence": "Copernicus Sentinel data terms (free, full and open)",
     "timestamp": "2024-09-06 / 2024-09-15 UTC", "attribution": "Contains modified Copernicus Sentinel data [2024]"},
    {"id": "osm", "name": "OpenStreetMap roads and candidate facilities (Geofabrik extract)", "licence": "ODbL 1.0",
     "timestamp": "2026-07-09", "attribution": "© OpenStreetMap contributors"},
    {"id": "worldpop", "name": WORLDPOP_SOURCE, "licence": "CC BY 4.0",
     "timestamp": "2020 estimate", "attribution": "WorldPop (www.worldpop.org), University of Southampton"},
    {"id": "cod-ab", "name": "HDX Thailand COD-AB subdistrict boundaries v01", "licence": "CC BY-IGO",
     "timestamp": "valid from 2022-01-22", "attribution": "OCHA / HDX Thailand COD-AB"},
    {"id": "viirs", "name": "NOAA/GMU VIIRS 375 m daily flood-water fraction (10-18 Sep 2024)", "licence": "No licence stated by the provider; attribution given",
     "timestamp": "2024-09-10 / 2024-09-18 daily", "attribution": "VIIRS flood product: NOAA JPSS / George Mason University"},
    {"id": "hii-rain", "name": "HII ThaiWater hourly rain gauges MOU189 and DIWO", "licence": "CC BY-NC",
     "timestamp": "2024-09-09 / 2024-09-19 hourly", "attribution": "Hydro-Informatics Institute (HII), ThaiWater"},
    {"id": "chronology", "name": "Event chronology (phases and narrative)", "licence": "Project summary text",
     "timestamp": "compiled 2026-09-27", "attribution": "FloodGuard team summary of public reporting; not independently verified in this study"},
]

ENVELOPE_SOURCE_ID = "unosat-4009"
ENVELOPE_SOURCE_NAME = "UNOSAT/GISTDA product 4009: water extents 1 Aug-22 Oct 2024, Chiang Rai"


def envelope_source(rights: dict) -> dict:
    """The manifest's source line for product 4009 (never among the export pack's sources)."""
    return {"id": ENVELOPE_SOURCE_ID, "name": ENVELOPE_SOURCE_NAME, "licence": rights["licence"],
            "timestamp": "2024-08-01 / 2024-10-22 (season envelope; no date per patch)", "attribution": rights["credit"]}


ASSUMPTIONS = [
    "Daily water surfaces are a HAND (height above nearest drainage) threshold reconstruction, not observations.",
    "Stage keyframes (metres above the mapped channel) are illustrative values shaped to the event chronology; no gauge record was used. The stage is held at 0 through 9 Sep and rises through the night of 10 Sep.",
    "The stage is the assumed Sai main-stem level at the Mae Sai bridges; tributaries rise k x stage (see the next assumption). Real water levels still differed reach by reach.",
    "Drainage channels are cells with at least 25 km² of upstream area on the 30 m Copernicus DSM; buildings and trees in the DSM bias HAND upward in town.",
    "Roads are impassable when reconstructed depth reaches 0.3 m at any 10 m sample along a 120 m piece (per-sample depth factor; the exported k makes h + 0.3/k equal the earliest sample closure); river-channel samples on bridges are ignored.",
    "Bridge decks are not modelled: a bridge's road state reflects the ground at its approaches and beside it, so a raised deck can stay passable while the model shows the way impassable. Read a bridge's impassable hours as unknown.",
    "Road pieces whose lowest HAND exceeds 4 m never flood under these keyframes and are omitted, except trunk, primary and secondary roads.",
    "The recession keyframes were re-tuned to the 16 September 06:16 ICT Sentinel-1 pass (best-fit stage 0.10 m), so that radar comparison is calibration-informed, not an independent check. It constrains the size of the late-recession extent only; the two radar passes use different orbit directions.",
    "The onset is shaped by GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (about 9.9 km2 flooded in Mae Sai) and reports of an overnight surge; the 11 Sep 02:00 knot (2.5 m) is illustrative. The model's smallest non-zero extent (flat land within 5 cm of channel level) already exceeds 9.9 km2, so the 18:15 knot is set to the closest level (0.1 m).",
    "Cells that drain off the hydrology domain before meeting a mapped channel use their outlet on the domain edge as the HAND reference (the edge lies outside the replay area).",
    "Where flow routing leaves no path to a channel (large flats), HAND falls back to height above the nearest channel cell.",
    "Stage varies along the river: each cell's water rise is scaled by k = clip((A / A_Sai) ** 0.3, 0.35, 1), where A is the upstream area of its drainage channel and A_Sai the Sai main stem at the Mae Sai bridges (downstream hydraulic geometry). The Ruak east of Mae Sai is inside the hydrology domain (DEM tiles N20E099 + N20E100).",
    "People in water uses WorldPop 2020 (100 m, spread evenly over 10 m cells); it is modelled residential population, not the 2024 population or tourists and traders at the border market.",
    "Evacuation access uses the repo road graph and walking distance: a resident node has access when an open, dry shelter is within 2 km along roads still passable (about 30 minutes on foot); a road closes at 0.3 m of reconstructed depth and a shelter stops serving once water reaches it. Levels are evaluated every 0.05 m of stage.",
    "Shelter candidates are OpenStreetMap public buildings and grounds (schools, places of worship, government offices, community centres; OSM amenity=shelter huts are excluded). A candidate is eligible only if it keeps 0.5 m freeboard at the modelled peak and a road node lies within 400 m. Ranking is greedy maximal coverage of residents whose homes are wet at the peak, within 2 km walking on normal roads (pre-emptive evacuation); late_cumulative_share repeats the check on roads still open at 1.0 m stage.",
    "Shelter capacity = mapped OSM building footprint within the site x 0.5 usable share / 3.5 m² per person (Sphere minimum covered space); OSM building coverage in Mae Sai is sparse, so many capacities are unknown or underestimated.",
    "The capacity-aware plan assigns residents of homes that flood at the modelled peak to eligible sites within the 2 km walk without exceeding a site's capacity. It gives two bounds: an unknown capacity counts as 0 (lower) or as the median estimate of its site kind (upper). Demand is an upper bound (many people stay with relatives) and the sites are candidates to verify.",
    "The two capacity bounds differ only in what a site without a mapped footprint is assumed to hold. Neither is a limit on who fits: a site with a footprint counts at its estimate in both, and that estimate is too low where buildings are unmapped.",
    "Plan robustness repeats the coverage ranking at 2.5 m, 3.5 m and 4.0 m: what-if levels around an illustrative peak, not return periods.",
    "VIIRS daily flood maps (375 m) are compared with the reconstruction only in clear-sky pixels at a nominal 13:30 ICT; they cannot see flooding under cloud or at street scale.",
    "Filled pits and dead-flat ground in the elevation model that end up less than 0.1 m above their channel (flagged in the raster's B channel) read as wet at almost any stage; they are shown as low-confidence water.",
    "Flash-flood velocity, debris and mud deposition are not modelled.",
    "The Sentinel-2 water check counts water or saturated mud (MNDWI above 0) on the clear pixels of the 5 Sep and 15 Sep scenes, inside the district and outside mapped channels; its comparison with the model is indicative.",
]

ENVELOPE_ASSUMPTIONS = [
    ("The 2024 season envelope (UNOSAT/GISTDA product 4009) is a scenario layer with its own toggle: accumulated water from August to "
     "October 2024, never an observation for a replay day. Setting the modelled water beside it is a plausibility comparison, not a validation."),
    unosat4009.DSM_ASSUMPTION,
]
"""Added to the manifest's assumptions when the season envelope ships."""

NO_PONDING_LIMITATION = ("No ponding or storage after the river falls: the terrain-only model dries every cell as soon as the assumed river level "
                         "drops below it, so water or saturated mud left behind after the river falls is not reconstructed.")


CONFIDENCE_REASON = ("Water extents are a terrain-model reconstruction with illustrative stages; the late-recession size was tuned to "
                     "one radar pass rather than checked independently, and spatial agreement there is weak.")
PERMITTED_USE = ("Preparedness learning, planning exercises and post-event prioritisation discussion in competition and preview builds. "
                 "Not for emergency response, evacuation orders or any operational decision; not an official warning.")
REASON_BLOCKED = ("Not a protocol case (decision D7): the replay is a narrative surface. Protocol v1b is not hashed, so no Flood Preparedness "
                  "Priority Score and no A-E action class is computed here; the accepted score and class stay null and the replay cannot feed "
                  "the decision layer. Confidence is low and ")
FIELD_CHECK = {
    False: "nothing was field-checked.",
    True: ("nothing was field-checked apart from a local check of some shelter candidates, reported by role (shelters.verification); the "
           "water, the roads and the residents were not checked."),
}
"""How the manifest says what was checked on the ground: before, and after, a verification sheet has been returned."""


def check_conducted(verification: dict) -> bool:
    """True once a returned verification sheet has been imported (``shelters.verification.status`` is ``conducted``)."""
    return verification.get("status") == shelter_validation.STATUS_CONDUCTED


def sentence(text: str) -> str:
    """``text`` with its first letter in upper case."""
    return text[:1].upper() + text[1:]
GIT_COMMIT_REASON = ("self_reference: a file cannot hold the hash of the commit that adds it. The input receipt identifies the bake sources "
                     "by SHA-256, and git_commit_lookup names the commit.")
GENERATED_AT_NOTES = {
    "declared": "Declared with --generated-at when the revision was baked and recorded in the input receipt. It is not read from the machine clock, so --verify rebuilds the same bytes.",
    "newest_input_timestamp": "No bake time was declared: this is the newest dated input, not the time the files were written. It is not read from the machine clock, so --verify rebuilds the same bytes.",
}
S1_BEST_FIT_STAGE_M = 0.10  # Stated in the assumptions and the disclosure; compose_manifest refuses to write another value.

EXPLORATORY_KNOWLEDGE = {
    "purpose": "Which external figures were used, or already known, while the stage keyframes and the depth factor were set. A figure used or known during tuning cannot serve as an independent check.",
    "items": [
        {"id": "gistda-radarsat2-20240910", "relation": "used_for_tuning", "known_during_tuning": True,
         "statement": "GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (9.9 km2 flooded in Mae Sai) was used on purpose to set the onset stage knot (10 Sep 18:15, 0.1 m)."},
        {"id": "sentinel-1-20240916", "relation": "used_for_tuning", "known_during_tuning": True,
         "statement": "The Sentinel-1 pass of 16 Sep 06:16 ICT was used to re-tune the recession keyframes (best-fit stage 0.10 m), so the radar size comparison is calibration-informed, not an independent check."},
        {"id": "unosat-3991", "relation": "known_during_tuning", "known_during_tuning": True,
         "statement": "UNOSAT 3991 (about 70 km2 over 13-19 Sep) was known while the stage keyframes were tuned, so its size comparison is calibration-informed, not independent."},
        {"id": "viirs-daily", "relation": "not_used_for_tuning", "known_during_tuning": None,
         "statement": ("The VIIRS daily comparison was not used for tuning. It was first computed in the change of 29 Sep 2026 (commit 129ff03) "
                       "that also moved the 10 Sep 18:15 knot from 0.12 m to 0.1 m, the model's closest level to GISTDA's figure. The build "
                       "history does not record which came first within that change, so the comparison is not presented as an independent check.")},
        {"id": "unosat-4009", "relation": "computed_after_keyframes_final", "known_during_tuning": False,
         "statement": ("The comparison with UNOSAT/GISTDA product 4009 was computed after the keyframes were final and was not used for tuning. "
                       "Recorded rule: no keyframe or elevation change is tuned to product 4009 afterwards; if one is, the comparison is "
                       "relabelled as calibration.")},
        {"id": "sentinel-2-water-check", "relation": "computed_after_keyframes_final", "known_during_tuning": False,
         "statement": ("The Sentinel-2 water check (MNDWI on the 5 Sep and 15 Sep scenes) was computed after the keyframes were final and was not "
                       "used for tuning: the last keyframe change is commit 129ff03 of 29 Sep 2026, and the check entered the bake on 2 Oct 2026. "
                       "The two true-colour images have been on the page since the first revision, so they were seen while the keyframes were "
                       "set, but no water area had been derived from them.")},
    ],
    "depth_factor": (f"The depth factor k = clip((A / A_Sai) ** {DEPTH_FACTOR_EXPONENT}, {DEPTH_FACTOR_FLOOR}, 1) was added on 28 Sep 2026, when the GISTDA and "
                     "UNOSAT 3991 figures were already known. Its exponent and floor follow a hydraulic-geometry rule of thumb; the build history records no fit to an external figure."),
    "rule": "No keyframe, depth-factor or terrain change may be tuned to VIIRS, the Sentinel-2 water check or product 4009 from here on; if one is, that comparison is relabelled calibration-informed.",
}

CAPACITY_CONFIDENCE_REASON = {
    False: ("Capacity is a footprint estimate from sparse OpenStreetMap buildings, unverified, and unknown for most candidates; "
            "demand is a modelled upper bound; nothing was checked on the ground."),
    True: ("Capacity is a footprint estimate from sparse OpenStreetMap buildings, unverified, and unknown for most candidates; "
           "demand is a modelled upper bound; the local check that was returned is reported by role and is not used in these figures."),
}
"""Why the capacity-aware figures have low confidence: before, and after, a verification sheet has been returned."""

CAPACITATED_META = {
    "scenario_tier": SCENARIO_TIER,
    "confidence": "low",
    "confidence_reason": CAPACITY_CONFIDENCE_REASON[False],
    "source_timestamp": f"OSM extract {OSM_EXTRACT_DATE} (building footprints and sites); WorldPop 2020; reconstructed peak 2024-09-12 ICT",
    "demand_basis": ("Every resident of a home that floods at the modelled peak (WorldPop 2020 residents at road nodes). An upper bound on "
                     "shelter demand: many people stay with relatives or on an upper floor."),
    "capacity_basis": {"estimate": evac.CAPACITY_ESTIMATE_BASIS, "unknown": evac.CAPACITY_UNKNOWN_BASIS},
    "bounds": {"lower": "An unknown capacity counts as 0.",
               "upper": ("An unknown capacity takes the median estimate of the same site kind (kind_median), or the median of every estimate "
                         "when no site of that kind has one (all_kinds_median). Medians use every candidate with an estimate."),
               "note": ("The bounds differ only in what a site without a mapped footprint is assumed to hold. Neither is a limit on who "
                        "fits: a site with a footprint counts at its estimate in both, and that estimate is too low where buildings are "
                        "unmapped, so more residents may fit than the upper bound gives.")},
    "method": ("Residents are assigned to eligible sites within the walking limit on normal roads without exceeding a site's capacity, serving "
               "as many as possible (a maximum flow, solved in thousandths of a resident and published in whole residents). The capacity-aware "
               "ranking adds, at each step, the site that lets the most additional residents fit under the upper bound; it stops at the plan-size "
               f"limit or when a site adds less than {evac.CAPACITY_MIN_GAIN_SHARE:.1%} of demand. Both bounds use that one site order, and a "
               "site's load is the number it adds when it joins. coverage_plan counts the existing coverage ranking the same way. "
               "overflow = demand_people - served."),
    "assumptions": [
        "T1 scenario (model) on the reconstructed peak; not an observation of who sheltered where.",
        "Demand is every resident of a home that floods at the modelled peak, an upper bound: many people stay with relatives or on an upper floor.",
        "Capacity is an unverified estimate from mapped building footprints (footprint x 0.5 usable share / 3.5 m2 per person, Sphere); most candidates have no mapped footprint.",
        "The sites are candidates to verify on the ground, not a list of sites to open.",
        "The planning overlay's shelter-capacity figures use listed capacities from a different source (DDPM); none of those values is used or published here, so the two sets of figures differ.",
        "Everyone is assumed to walk before the water rises (normal roads) and to accept any site within the limit; households are not kept together.",
        "Neither bound is a limit on who fits: both count a site with a mapped footprint at its estimate, which is too low where buildings are unmapped.",
    ],
}
"""Wording and provenance of ``shelters.capacitated`` while no local check has been returned (the figures come from the build)."""


def capacitated_meta(verification: dict) -> dict:
    """:data:`CAPACITATED_META` for this bake: once a local check has been returned it stops saying nothing was checked,
    and says instead that the figures do not use the check."""
    conducted = check_conducted(verification)
    meta = {**CAPACITATED_META, "confidence_reason": CAPACITY_CONFIDENCE_REASON[conducted]}
    if conducted:
        meta["assumptions"] = [*CAPACITATED_META["assumptions"], VERIFICATION_NOT_USED]
    return meta

ROBUSTNESS_META = {
    "scenario_tier": SCENARIO_TIER,
    "label": "What-if levels around an illustrative peak, not return periods.",
    "confidence": "low",
    "confidence_reason": "The peak stage is illustrative (no gauge record); the levels show how the ranking moves if it were lower or higher.",
    "source_timestamp": f"OSM extract {OSM_EXTRACT_DATE}; WorldPop 2020; what-if design stages around the illustrative 2024-09-12 ICT peak",
    "method": ("At each level the demand is the residents whose homes are wet at that level and a candidate is eligible if it keeps its "
               "freeboard there; the same greedy coverage ranking is then repeated. core_by_k[k - 1] lists the sites among the first k "
               "at every level (the robust core for a plan of k sites)."),
    "assumptions": [
        "The levels are what-if stages around the illustrative 3.5 m peak, not return periods and not observed levels.",
        "Reach is the same 2 km walk on normal roads at every level; only the demand and the eligible sites change.",
        "A site in the robust core is still a candidate to verify on the ground.",
    ],
}
"""Wording and provenance of ``shelters.robustness`` (the figures come from the build)."""

EXPORTS_META = {
    "scenario_tier": SCENARIO_TIER,
    "tier": replay_exports.EXPORT_TIER,
    "confidence": "low",
    "confidence_reason": replay_exports.confidence_reason(False)[0],
    "purpose": ("Tables and one map layer for spreadsheet and GIS users, written from the modelled blocks of this manifest: modelled, not "
                "observed. Not a forecast, not an observed closure record and not an official warning."),
    "licence": replay_exports.EXPORT_LICENCE,
    "licence_rule": ("One licence lineage per file: every file is OpenStreetMap-derived (ODbL 1.0, attribution and share-alike) with "
                     "attribution-only inputs. No file holds rain values (CC BY-NC) or anything from a source without a stated licence."),
    "header": {
        "csv": ("UTF-8 with a byte-order mark and LF line ends. Each file starts with provenance lines (first cell starts with #) and "
                "then the column header; header_lines of each file gives their number. Header cells are the English key and the Thai "
                "label in brackets."),
        "geojson": "The same provenance fields sit in a top-level metadata member, before the features.",
        "why_in_the_file": ("A sidecar file is lost when a table is forwarded on its own, so the tier, the confidence, the timestamps, the "
                            "assumptions and the licence travel inside each file."),
    },
    "offline": "Saved with the replay's offline copy; outside the replay's precache budget, under a budget of their own.",
    "assumptions": [
        "Every table is a T1 scenario (model) on the reconstructed water; the reported-shelter table adds reported facts, kept apart in their own columns.",
        "Hours are replay hours on the hourly grid (hour 0 = 9 Sep 2024 00:00 ICT); the assumed stage is sampled at the start of each hour.",
        "The modelled road table lists one row per OpenStreetMap way of the classes the replay models; the legacy candidate columns of the source road file are not carried.",
        "Bridge decks are not modelled: a row flagged as a bridge reflects the ground at its approaches, and its hours are best read as unknown.",
        "No listed capacity from a shelter register, no occupancy count and no personal data is in any file.",
    ],
}
"""Wording and provenance of the manifest's ``exports`` block (the file list and the source timestamp come from the bake)."""


def exports_source_timestamp(reported_compiled: str) -> str:
    """Source timestamp of the export pack: the dated inputs its tables are written from."""
    return (f"OSM extract {OSM_EXTRACT_DATE}; WorldPop 2020; reported shelters compiled {reported_compiled}; "
            "illustrative stage keyframes for 2024-09-09/2024-09-19 ICT")

S2_CHECK_META = {
    "product": "Sentinel-2B MSI Level-2A via Earth Search (tile 47QNC): green band (B03), short-wave infrared band (B11) and scene classification (SCL)",
    "licence": "Copernicus Sentinel data terms (free, full and open)",
    "attribution": "Contains modified Copernicus Sentinel data [2024]",
    "label": "water or saturated mud",
    "confidence": "low",
    "confidence_reason": ("One index threshold on two partly cloudy scenes, with no field check: a positive index also flags saturated mud and wet "
                          "sediment, the scene classification can miss thin cloud and cloud shadow, and the ground under cloud was not seen."),
    "source_timestamp": S2_CHECK_PAIR,
    "index": ("MNDWI = (green - swir16) / (green + swir16) on surface reflectance (digital number / 10000, nothing subtracted). The 10 m green "
              "band is averaged onto the 20 m grid of the short-wave infrared band."),
    "water_rule": "A clear pixel counts as water or saturated mud when its MNDWI is above 0.",
    "clear_rule": ("A pixel is clear when its scene classification is not no data (0), cloud shadow (3), cloud (8, 9) or thin cirrus (10), and "
                   "both bands hold data."),
    "permanent_water_rule": ("Mapped drainage-channel cells are left out on both dates: the same out-of-channel rule as the model's flooded area. "
                             "No land-cover map is used, so ponds and reservoirs count on both dates; the new-water figure leaves them out."),
    "scope": "The eight Mae Sai subdistricts, on the replay's 10 m grid.",
    "comparison": "indicative",
    "comparison_rule": ("The model figures are the modelled out-of-channel water at the acquisition time of the 15 Sep scene, counted in the pixels "
                        "that scene saw clearly. The overlap ratio says how far the two areas coincide, not which one is right."),
    "caveat": ("A positive MNDWI also flags saturated mud and wet sediment, so the area is water or saturated mud, not a flood extent. The scene "
               "classification can miss thin cloud and cloud shadow, and cloud hid part of the district on both dates. The comparison with the "
               "model is indicative only."),
    "reading": ("The larger observed area is consistent with water or saturated mud left after the river fell; the terrain-only "
                "model cannot hold water once the river level drops."),
    "model_fields": {"paths": ["model_at_event_scene", "sensitivity[].model_agreement_iou"], "evidence_tier": SCENARIO_TIER,
                     "note": "Model output on the reconstructed water, placed beside the observation for comparison; not part of the Sentinel-2 data."},
    "assumptions": [
        "Reflectance = digital number / 10000 for the Earth Search L2A files, which already have the baseline-04.00 offset removed.",
        "An MNDWI above 0 is read as water or saturated mud. The threshold was not tuned and nothing was checked on the ground; the sensitivity rows give 0.1 and 0.2.",
        "Clear pixels follow the provider's scene classification. Unclassified and dark pixels are kept; the strict_clear sensitivity row drops them.",
        "New water needs both dates clear. Water already there on 5 Sep, before the flood, is not counted as new.",
        "The model is sampled at the acquisition time of the 15 Sep scene. No keyframe was tuned to this check.",
        "No land-cover map is an input, so the check does not say what kind of land the water or saturated mud lies on.",
    ],
}
"""Wording and provenance of the manifest's ``s2_crosscheck`` block (the figures come from the build)."""

S2_FOLLOWING_DAY_READING = ("A day later the VIIRS map shows less flood water than the model in its clear pixels, so the larger area on the "
                            "day of the scene is consistent with saturated mud or short-lived water rather than lasting ponding.")
"""Added to the block only when the next VIIRS day with clear sky shows less flood water than the model (see
:func:`following_viirs_day`); the figures themselves stay in ``viirs_daily.days``."""


def following_viirs_day(viirs_days: list[dict], event_local_time: str) -> dict | None:
    """The first VIIRS day after the local date of the event scene on which the sky over the district was partly clear."""
    event_date = event_local_time[:10]
    for day in sorted(viirs_days, key=lambda item: item["date"]):
        if day["date"] > event_date and day["clear_km2"] > 0:
            return day
    return None

S2_MODEL_PATHS = tuple(S2_CHECK_META["model_fields"]["paths"])
"""Paths inside ``s2_crosscheck`` that hold model output placed beside the observation (the evidence block's scenario fields)."""


def model_key_paths(value, path: str = "") -> list[str]:
    """Paths of every key that starts with ``model_`` inside ``value``; list items are written ``[]``."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            if key.startswith("model_"):
                found.append(here)
            found.extend(model_key_paths(item, here))
    elif isinstance(value, list):
        for item in value:
            found.extend(model_key_paths(item, f"{path}[]"))
    return sorted(set(found))


def s2_crosscheck_block(check: dict, viirs_days: list[dict] | tuple = ()) -> dict:
    """The manifest's ``s2_crosscheck`` block: observed areas per scene, the change, the model beside it and a caveat.

    Model output may sit only under the paths in :data:`S2_MODEL_PATHS`; a ``model_`` key anywhere else stops the
    bake, because the evidence block would file it as observed. ``viirs_days`` are the manifest's VIIRS rows: when
    the next clear VIIRS day shows less flood water than the model, the block names that day (``following_day``)
    and says what that is consistent with, so the reading of the scene's day is not left standing alone.
    """
    local = {observation["id"]: observation["local"] for observation in OBSERVATIONS}
    scenes = [{"id": key, "role": role, "scene": S2_SCENES[key][0], "source_timestamp": S2_SCENES[key][1], "local_time": local[key],
               **check["scenes"][role]} for role, key in (("pre_event", S2_CHECK_PRE), ("event", S2_CHECK_EVENT))]
    block = {**S2_CHECK_META, "resolution_m": check["resolution_m"], "threshold": check["threshold"],
             "district_km2": check["district_km2"], "permanent_water_km2": check["permanent_water_km2"], "scenes": scenes,
             "change": {"pre_event_scene": S2_CHECK_PRE, "event_scene": S2_CHECK_EVENT, **check["change"]},
             "model_at_event_scene": {"model_local_time": local[S2_CHECK_EVENT], **check["model_at_event_scene"]},
             "sensitivity": check["sensitivity"]}
    following = following_viirs_day(list(viirs_days), local[S2_CHECK_EVENT])
    if following is not None and following["viirs_flood_km2_clear"] < following["model_flood_km2_clear"]:
        block["following_day"] = {"viirs_date": following["date"], "reading": S2_FOLLOWING_DAY_READING}
    figures = {key: value for key, value in block.items() if key != "model_fields"}
    unnamed = [path for path in model_key_paths(figures)
               if not any(path == allowed or path.startswith(allowed + ".") for allowed in S2_MODEL_PATHS)]
    if unnamed:
        raise ReplayManifestError(f"the Sentinel-2 water check carries model fields the evidence block does not name: {unnamed}")
    not_model = [key for key in block["model_at_event_scene"] if not key.startswith("model_")]
    if not_model:
        raise ReplayManifestError(f"model_at_event_scene holds a field that is not named as model output: {not_model}")
    return block


VIIRS_MODEL_FIELDS = ("model_stage_m", "model_flood_km2_clear", "model_flood_km2_district")
"""Fields of every ``viirs_daily.days[]`` row that are model output placed beside the agency product."""


def rights_wording(rights: dict) -> dict:
    """The sentences about product 4009 for a confirmed rights record: it is shown, as a season envelope scenario layer.

    The bake never reaches this with an unconfirmed record (``build`` stops first); asking for the wording of one is an error.
    """
    if not rights["confirmed"]:
        raise ReplayManifestError("product 4009 is shown only when the owners have confirmed its rights record")
    reply = (f"The {rights['licence']} rights decision (D2) was signed on {short_date(rights['signed_on'])} and UNOSAT replied "
             f"\"{rights['reply_quote']}\" (relayed by a project owner on {short_date(rights['reply_relayed_on'])})")
    confirmed = f"the owners confirmed the rights record on {short_date(rights['confirmed_on'])}"
    return {"status": f"Shown as a season envelope scenario layer; {confirmed}.",
            "condition": (f"UNOSAT/GISTDA product 4009 ({rights['licence']}) is shown as a season envelope scenario layer: its derived files "
                          f"keep their own folder, credit, licence and change notice; {confirmed}."),
            "block_note": f"Never an observation for a replay day. Shown as a scenario layer with its own toggle, credit and change notice; {confirmed}.",
            "rights_note": f"Season envelope (scenario per decision D3). {reply}; {confirmed}. Shown from this revision as a scenario layer."}


def publication_eligibility(reported_licence: str | None, rights: dict) -> dict:
    """Licence and display status per input; product 4009 is shown as a season envelope scenario layer, in its own files."""
    wording = rights_wording(rights)
    def entry(source_id: str, terms: str, **extra) -> dict:
        source = next(s for s in SOURCES if s["id"] == source_id)
        return {"id": source_id, "name": source["name"], "licence": source["licence"], "licence_stated": True, "shown": True, "terms": terms, **extra}

    return {
        "status": "conditional",
        "scope": "Competition and preview builds, non-commercial, with the attributions listed in sources.",
        "conditions": [
            "HII rain data are CC BY-NC: the replay as a whole is for non-commercial use, and rain values stay out of any combined table or export.",
            "The VIIRS provider states no licence: the maps are shown with attribution, and reuse beyond this page is not cleared.",
            "OpenStreetMap-derived files (roads, facilities, shelter candidates and the access node positions) stay under ODbL 1.0: attribution and share-alike.",
            wording["condition"],
        ],
        "inputs": [
            entry("copernicus-dem", "Use under the Copernicus DEM licence terms, with the DLR and Airbus attribution."),
            entry("sentinel-2", "Use under the Copernicus Sentinel data terms, with the modified-data notice."),
            entry("sentinel-1", "Use under the Copernicus Sentinel data terms, with the modified-data notice."),
            entry("osm", "Attribution and share-alike: files derived from the OpenStreetMap database stay under ODbL 1.0."),
            entry("worldpop", "Attribution."),
            entry("cod-ab", "Attribution to OCHA / HDX."),
            {**entry("viirs", "Shown with attribution; reuse beyond this page is not cleared."),
             "licence": "No licence stated by the provider", "licence_stated": False},
            entry("hii-rain", "Non-commercial use with attribution; keep rain values out of any combined table or export."),
            {"id": "reported-shelters", "name": "Shelters reported in use in September 2024 (FloodGuard desk research)",
             "licence": reported_licence or "Facts with citations", "licence_stated": True, "shown": True,
             "terms": "Facts quoted with their sources; coordinates matched to OpenStreetMap stay under ODbL 1.0."},
            entry("chronology", "Team summary of public reporting, shown with its compile date."),
            {"id": "external-figures", "name": "GISTDA 10 Sep 2024 and UNOSAT 3991 reported figures", "licence": "Cited figures with links; no data copied",
             "licence_stated": False, "shown": True, "terms": "Quoted as reported, with a link to each source."},
            {"id": ENVELOPE_SOURCE_ID, "name": ENVELOPE_SOURCE_NAME, "licence": rights["licence"],
             "licence_stated": True, "shown": True, "status": wording["status"],
             "rights_record": rights["record"],
             "terms": "Attribution, share-alike and a change notice on every derived file; kept in its own folder."},
        ],
    }


def evidence_blocks(result: dict) -> list[dict]:
    """Lane, tier, temporal relation and source timestamp for every part of the manifest (see ``floodguard.replay_manifest``)."""
    compiled = result["reported_meta"]["compiled"]
    verification = result["shelters"]["verification"]
    viirs = result["viirs_days"]
    s2 = {key: stamp for key, (_, stamp) in S2_SCENES.items()}
    scenario = {"lane": "SCN", "evidence_tier": SCENARIO_TIER}
    imagery = {"lane": "OBS", "evidence_tier": "Observed image, shown as acquired; no flood extent is derived from it"}
    blocks = [
        {"id": "water_reconstruction", **scenario, "temporal_relation": "event_window_reconstruction",
         "covers": ["hand", "impassable_depth_m", "pixel_area_m2", "stage_anchors", "tambon_coverage", "model_coverage", "tambon_histograms", "days",
                    "facilities_count", "roads_not_modelled_km", "vectors.roads", "vectors.facilities"],
         "source_timestamp": f"Copernicus DEM (2011-2015 acquisitions); OSM roads and facilities {OSM_EXTRACT_DATE}; illustrative stage keyframes for 2024-09-09/2024-09-19 ICT",
         "note": "HAND threshold reconstruction with illustrative stage keyframes: modelled water, road and facility impacts; not an observation."},
        {"id": "residents_in_water", **scenario, "temporal_relation": "static_context", "covers": ["population"],
         "source_timestamp": "WorldPop 2020 estimate",
         "note": "Modelled 2020 residents on the reconstructed water; not the 2024 population."},
        {"id": "evacuation_access", **scenario, "temporal_relation": "event_window_reconstruction", "covers": ["access"],
         "source_timestamp": f"OSM roads and sites {OSM_EXTRACT_DATE}; WorldPop 2020; water model 2024-09-09/2024-09-19 ICT",
         "note": "Walking access to an open, dry shelter on the reconstructed water; not observed evacuation outcomes."},
        {"id": "shelter_plan", **scenario, "temporal_relation": "event_window_reconstruction", "covers": ["shelters"],
         "source_timestamp": f"OSM extract {OSM_EXTRACT_DATE}; reconstructed peak 2024-09-12 ICT",
         "note": "Candidate screening and ranked plan on the reconstructed peak; the reported sites inside this block sit in the reported lane."},
        {"id": "capacity_aware_plan", **scenario, "temporal_relation": "event_window_reconstruction", "covers": ["shelters.capacitated"],
         "source_timestamp": f"OSM extract {OSM_EXTRACT_DATE} (building footprints and sites); WorldPop 2020; reconstructed peak 2024-09-12 ICT",
         "note": ("Who fits where under two capacity bounds, on the reconstructed peak. Demand is every resident of a home that floods at the "
                  "peak; capacity is an unverified footprint estimate. Candidates to verify, not a list of sites to open.")},
        {"id": "plan_robustness", **scenario, "temporal_relation": "what_if_levels", "covers": ["shelters.robustness"],
         "source_timestamp": f"OSM extract {OSM_EXTRACT_DATE}; WorldPop 2020; what-if design stages around the illustrative 2024-09-12 ICT peak",
         "note": "The coverage ranking repeated at what-if levels around an illustrative peak, not return periods."},
        {"id": "reported_shelters", "lane": "REP", "evidence_tier": "Reported use from public sources; not an official register",
         "temporal_relation": "post_event_compilation", "covers": ["shelters.reported"],
         "source_timestamp": f"reports dated 2024-09-11 to 2024-10-11; compiled {compiled}"},
        {"id": "shelter_candidate_check", "lane": "REP", "evidence_tier": "Local check reported by role; not an official shelter register",
         "temporal_relation": "post_event_compilation", "covers": ["shelters.verification"],
         "source_timestamp": verification.get("source_timestamp", "not conducted: no verification sheet had been returned when these files were generated"),
         "note": verification["statement"]},
        {"id": "event_chronology", "lane": "REP", "evidence_tier": "Team summary of public reporting; not independently verified in this study",
         "temporal_relation": "post_event_compilation", "covers": ["phases"], "source_timestamp": f"compiled {CHRONOLOGY_COMPILED}"},
        {"id": "viirs_daily", "lane": "OBS", "evidence_tier": "Agency flood product, used as provided; unvalidated here",
         "temporal_relation": "event_aligned", "covers": ["viirs_daily"],
         "source_timestamp": f"{viirs[0]['nominal_local_time']}/{viirs[-1]['nominal_local_time']} (daily composites, nominal pass time)" if viirs else "no VIIRS day in this bake",
         SCENARIO_FIELDS_KEY: [f"viirs_daily.days[].{field}" for field in VIIRS_MODEL_FIELDS],
         "note": ("375 m optical flood-water fraction; each day carries its own nominal time and cloud share. The model_* fields of each day "
                  f"are {SCENARIO_TIER} values computed for the comparison, not part of the agency product.")},
        {"id": "sentinel2_20240905", **imagery, "temporal_relation": "pre_event",
         "covers": ["observations[s2-20240905]", "layers[s2-20240905]"], "source_timestamp": s2["s2-20240905"]},
        {"id": "sentinel2_20240915", **imagery, "temporal_relation": "event_aligned",
         "covers": ["observations[s2-20240915]", "layers[s2-20240915]"], "source_timestamp": s2["s2-20240915"]},
        *([{"id": "sentinel2_water_check", "lane": "OBS",
            "evidence_tier": "Optical water index on observed images, clear pixels only: water or saturated mud; unvalidated here",
            "temporal_relation": "pre_event_to_event_pair", "covers": ["s2_crosscheck"], "source_timestamp": S2_CHECK_PAIR,
            SCENARIO_FIELDS_KEY: [f"s2_crosscheck.{path}" for path in S2_MODEL_PATHS],
            "note": ("MNDWI above 0 on the clear pixels of two Sentinel-2 L2A scenes; each scene carries its own acquisition time and clear "
                     f"share. model_at_event_scene and the model_ field of each sensitivity row are {SCENARIO_TIER} values computed for the "
                     "comparison, which is indicative only.")}] if "s2_check" in result else []),
        {"id": "sentinel1_20240906", **imagery, "temporal_relation": "pre_event",
         "covers": ["observations[s1-20240906]", "layers[s1-20240906]"], "source_timestamp": S1_STAMPS["s1-20240906"]},
        {"id": "sentinel1_20240915", **imagery, "temporal_relation": "event_aligned",
         "covers": ["observations[s1-20240915]", "layers[s1-20240915]"], "source_timestamp": S1_STAMPS["s1-20240915"]},
        {"id": "sentinel1_change", "lane": "OBS", "evidence_tier": "Observed image pair shown as a colour composite; no flood extent is derived from it",
         "temporal_relation": "pre_event_to_event_pair", "covers": ["layers[s1-change]"], "source_timestamp": S1_PAIR},
        {"id": "rainfall", "lane": "OBS", "evidence_tier": "Gauge record, used as provided", "temporal_relation": "event_aligned",
         "covers": ["rainfall"], "source_timestamp": f"{EVENT_START}/{EVENT_END} (hourly)",
         "note": "Observed rainfall (forcing), not flooding."},
        {"id": "sentinel1_size_comparison", "lane": "CAL", "evidence_tier": "Calibration-informed size comparison; not an independent check",
         "temporal_relation": "event_aligned", "covers": ["s1_anchor"], "source_timestamp": S1_PAIR,
         "note": "The recession keyframes were re-tuned to this pass."},
        {"id": "gistda_onset_anchor", "lane": "CAL", "evidence_tier": "Calibration anchor; the model agrees with it by construction",
         "temporal_relation": "event_aligned", "covers": ["external_checks[gistda-radarsat2-20240910]"],
         "source_timestamp": "2024-09-10T18:15 (time zone not stated by GISTDA; assumed ICT)"},
        {"id": "unosat_3991_size_comparison", "lane": "CAL", "evidence_tier": "Calibration-informed magnitude check; not an independent check",
         "temporal_relation": "event_window_cumulative", "covers": ["external_checks[unosat-3991]"],
         "source_timestamp": "2024-09-13/2024-09-19 (cumulative window)"},
        *([{"id": "unosat_4009_season_envelope", "lane": ENVELOPE_LANE, "evidence_tier": unosat4009.EVIDENCE_TIER,
            "temporal_relation": "season_envelope", "covers": ["season_envelope", f"external_checks[{ENVELOPE_CHECK_ID}]"],
            "source_timestamp": result["rights_4009"]["source_timestamp"], "season_window": unosat4009.SEASON_WINDOW, "shown": True,
            "note": rights_wording(result["rights_4009"])["block_note"]}] if "season_envelope" in result else []),
        {"id": "terrain_shading", "lane": "CTX", "evidence_tier": "Reference data", "temporal_relation": "static_context",
         "covers": ["layers[hillshade]"], "source_timestamp": "Copernicus DEM (2011-2015 acquisitions)"},
        {"id": "subdistrict_boundaries", "lane": "CTX", "evidence_tier": "Reference data", "temporal_relation": "static_context",
         "covers": ["vectors.tambons"], "source_timestamp": "COD-AB valid from 2022-01-22"},
        {"id": "other_references", "lane": "REF", "evidence_tier": "Cited source; not ingested in this revision", "temporal_relation": "not_ingested",
         "covers": ["external_references[unosat-3969]", "external_references[charter-912]", "external_references[hii-event-page]"],
         "source_timestamp": "event reports of September 2024"},
    ]
    if "exports" in result:
        blocks.append({"id": "export_pack", **scenario, "temporal_relation": "event_window_reconstruction", "covers": ["exports"],
                       "source_timestamp": exports_source_timestamp(compiled),
                       "note": ("Download files written from the modelled blocks above; each file names its own lanes. The reported-shelter table "
                                "and the reported points of the site layer repeat reported facts (block reported_shelters) beside a model check.")})
    return blocks


def dated_inputs(result: dict) -> list[str]:
    """Dates of the newest content of each dated input group (the default ``generated_at`` is their maximum)."""
    stamps = [stamp for _, stamp in S2_SCENES.values()] + list(S1_STAMPS.values()) + [EVENT_END, OSM_EXTRACT_DATE, CHRONOLOGY_COMPILED]
    stamps += [day["nominal_local_time"] for day in result.get("viirs_days", [])]
    if result.get("reported_meta", {}).get("compiled"):
        stamps.append(result["reported_meta"]["compiled"])
    return stamps


def generated_stamp(result: dict, generated_at: str | None) -> tuple[str, str]:
    """The ``generated_at`` value and its basis: the declared time, or else the newest dated input (never the clock)."""
    if generated_at:
        return normalise_timestamp(generated_at), "declared"
    return newest_timestamp(dated_inputs(result)), "newest_input_timestamp"


def compose_manifest(result: dict, inputs: list[dict] | None = None, generated_at: str | None = None) -> dict:
    """Assemble ``timeline.json`` with provenance, confidence, evidence lanes and assumptions.

    ``inputs`` are the input receipt's rows (root, path, bytes, SHA-256). ``generated_at`` is the declared bake
    time; without it the newest dated input is used, never the machine clock.
    """
    anchor = result["s1_anchor"]
    if round(anchor["best_fit_stage_m"], 2) != S1_BEST_FIT_STAGE_M:
        raise ReplayManifestError(f"the disclosure states a Sentinel-1 best-fit stage of {S1_BEST_FIT_STAGE_M:.2f} m, but this bake found {anchor['best_fit_stage_m']} m")
    stamp, basis = generated_stamp(result, generated_at)
    conducted = check_conducted(result["shelters"]["verification"])
    first_image = min(stamp_ for _, stamp_ in S2_SCENES.values())
    blocks = evidence_blocks(result)
    rights = result["rights_4009"]
    unknown_model_fields = sorted({key for day in result["viirs_days"] for key in day if key.startswith("model_")} - set(VIIRS_MODEL_FIELDS))
    if unknown_model_fields:
        raise ReplayManifestError(f"VIIRS day rows carry model fields the evidence block does not name: {unknown_model_fields}")
    manifest = {
        "study_id": STUDY_ID, "revision": REVISION, "schema_version": 2, "schema_id": SCHEMA_ID,
        "generated_by": GENERATED_BY,
        "generated_at": stamp, "generated_at_basis": basis, "generated_at_note": GENERATED_AT_NOTES[basis],
        "git_commit": None, "git_commit_reason": GIT_COMMIT_REASON,
        "git_commit_lookup": f"git log -1 --format=%H -- {OUT_REL.as_posix()}/timeline.json",
        "data_version": f"{STUDY_ID}-{REVISION}",
        "dataset_mode": "historical_reconstruction", "data_mode": "historical_reconstruction",
        "operational_status": "non_operational",
        "official_warning": False, "real_time": False, "can_feed_decision_layer": False,
        "accepted_fpps": None, "accepted_action_class": None,
        "protocol_sha256": None, "protocol_sha256_reason": "not_a_protocol_case",
        "permitted_use": PERMITTED_USE, "reason_blocked": REASON_BLOCKED + FIELD_CHECK[conducted],
        "confidence": "low", "confidence_class": "low",
        "confidence_reason": CONFIDENCE_REASON,
        "confidence_basis": [
            "Terrain: HAND on the 30 m Copernicus DSM; buildings and trees bias HAND upward in town.",
            "Stage: illustrative keyframes shaped to the event chronology; no gauge record.",
            "Tuning: the onset knot uses GISTDA's 10 Sep figure, the recession keyframes use the 16 Sep Sentinel-1 pass and UNOSAT 3991 was known, so no size comparison is independent.",
            f"Spatial agreement with the Sentinel-1 newly water-like area is weak (IoU {anchor['iou_at_best_fit']:.2f}).",
            "Onset and peak extents were not observed: no high-resolution image for 10-14 Sep, and VIIRS was mostly under cloud.",
            sentence(FIELD_CHECK[conducted]),
        ],
        "source_name": "FloodGuard Mae Sai September 2024 flood replay: terrain-model reconstruction with dated observations and reported facts",
        "event_time": {"start": EVENT_START, "end": EVENT_END, "timezone": "Asia/Bangkok",
                       "note": "Replay window in local time (ICT, UTC+7): 9 Sep 00:00 to 19 Sep 24:00."},
        "source_timestamp": f"{first_image}/{normalise_utc(EVENT_END)}",
        "source_timestamp_note": ("Span of the dated event observations shown: from the Sentinel-2 image of 5 Sep 03:58 UTC to the end of the last HII rain hour "
                                  "(19 Sep 24:00 ICT). Sentinel-1 (6 and 15 Sep UTC) and VIIRS (10-18 Sep) fall inside it. Inputs dated outside the event "
                                  f"(elevation 2011-2015, WorldPop 2020, boundaries 2022, OpenStreetMap {OSM_EXTRACT_DATE}, reported shelters compiled "
                                  f"{result['reported_meta']['compiled']}) are dated per evidence block and in sources."),
        "timezone": "Asia/Bangkok (ICT, UTC+7)",
        "area": {"en": "Mae Sai District, Chiang Rai, Thailand (the image footprint also covers Tachileik, Myanmar)",
                 "th": "อำเภอแม่สาย จังหวัดเชียงราย (ภาพครอบคลุมท่าขี้เหล็ก เมียนมาด้วย)"},
        "bounds": result["bounds"],
        "lanes": {lane: LANES[lane] for lane in dict.fromkeys(block["lane"] for block in blocks)},
        "evidence_blocks": blocks,
        "exploratory_knowledge": EXPLORATORY_KNOWLEDGE,
        "publication_eligibility": publication_eligibility(result["reported_meta"].get("licence_note"), rights),
        "input_sha256": [dict(row) for row in (inputs or [])],
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
        "s1_anchor": {**anchor, "reconstruction_stage_at_pass_m": round(stage_at(7 + 6.27 / 24), 3),
                      "role": "calibration_informed_magnitude_check", "source_timestamp": S1_PAIR,
                      "use": "Calibration-informed, not an independent check: the recession keyframes were re-tuned to this pass (best-fit stage 0.10 m). It constrains size only, not location."},
        "population": {**result["population"], "source": WORLDPOP_SOURCE,
                       "licence": "CC BY 4.0", "timestamp": "2020 estimate",
                       "note": "Modelled residential population, not a census count or the 2024 population."},
        "access": {**result["access"], "scenario_tier": "T1 scenario (model), not observed evacuation outcomes",
                   "confidence": "low",
                   "confidence_reason": "Built on the reconstructed water, WorldPop 2020 residents at road nodes, an OSM road graph with assumed walking access and shelters assumed open for the whole replay.",
                   "source_timestamp": "OSM roads and sites 2026-07-09; WorldPop 2020; water model 2024-09-09/2024-09-19 ICT",
                   "definition": "A resident node loses access when no open, dry shelter of the chosen set is reachable within the threshold on roads that are still passable, having been reachable before the flood."},
        "shelters": {**result["shelters"],
                     "capacitated": {**capacitated_meta(result["shelters"]["verification"]), **result["shelters"]["capacitated"]},
                     "robustness": {**ROBUSTNESS_META, **result["shelters"]["robustness"]},
                     "confidence": "low",
                     "confidence_reason": "Candidates are OSM public buildings with sparse footprints; eligibility and coverage use the reconstructed peak and walking distance, not site surveys.",
                     "source_timestamp": "OSM extract 2026-07-09; reported shelters compiled 2026-09-27 from reports dated 2024-09-11 to 2024-10-11",
                     "reported_status": result["reported_meta"]["status"], "reported_compiled": result["reported_meta"]["compiled"],
                     "reported_access_set_rule": result["reported_meta"]["access_set_rule"]},
        **({"exports": {**EXPORTS_META, "confidence_reason": replay_exports.confidence_reason(conducted)[0],
                        "source_timestamp": exports_source_timestamp(result["reported_meta"]["compiled"]), **result["exports"]}}
           if "exports" in result else {}),
        "external_checks": [*result["external_checks"], *([envelope_check(result["season_envelope"], rights)] if "season_envelope" in result else [])],
        **({"season_envelope": season_envelope_block(result["season_envelope"], rights)} if "season_envelope" in result else {}),
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
            "model_fields": {"names": list(VIIRS_MODEL_FIELDS), "evidence_tier": SCENARIO_TIER,
                             "note": "Model output on the reconstructed water, placed beside each day for comparison; not part of the VIIRS product."},
            "days": result["viirs_days"],
        },
        **({"s2_crosscheck": s2_crosscheck_block(result["s2_check"], result["viirs_days"])} if "s2_check" in result else {}),
        "rainfall": {**result["rainfall"], "source": "HII ThaiWater open data, hourly rain gauges",
                     "source_url": "https://tiservice.hii.or.th/opendata/", "licence": "CC BY-NC (per the HII open-data catalogue)",
                     "units": "mm per hour; index 0 = 9 Sep 00:00-01:00 ICT", "note": "Observed rainfall (forcing), not flooding."},
        "external_references": [
            {"id": "unosat-3969", "name": "UNOSAT 3969: preliminary flood impact assessment, Mae Sai (Pleiades 15 Sep)", "url": "https://unosat.org/static/unosat_filesystem/3969/UNOSAT_Preliminary_Assessment_Report_TC20240912THA_ChiangRai_16Sep2024.pdf"},
            {"id": "charter-912", "name": "International Charter activation 912 (Typhoon Yagi, Thailand)", "url": "https://disasterscharter.org/activations/flood-in-thailand-activation-912-"},
            {"id": "hii-event-page", "name": "HII ThaiWater September 2024 Chiang Rai flood event page (rainfall and Kok River hydrographs)", "url": "https://www.thaiwater.net/uploads/contents/current/2024/FloodChiangrai_Sep2024/"}],
        "gauge_note": "No public hourly Sai River water-level record for Sep 2024 was found (HII MYA004 installed 2025; RID Kh.50 closed; DWR Ban Mae Sai EWS unverified), so stage values remain illustrative.",
        "sources": [*SOURCES, *([envelope_source(rights)] if "season_envelope" in result else [])],
        "assumptions": [*ASSUMPTIONS, *(ENVELOPE_ASSUMPTIONS if "season_envelope" in result else [])],
        "limitations": [
            "Not a real-time product or an official warning; for preparedness learning and post-event prioritisation only.",
            "No high-resolution satellite image exists for 10-14 September over Mae Sai in these inputs; VIIRS (375 m) was cloud-covered on 10-11 Sep and mostly cloud-covered on 12-14 Sep, so onset and peak extents are not observed.",
            "Statistics cover only the modelled parts of the eight Mae Sai subdistricts (see model_coverage); roads and facilities outside the model are flagged m=false and excluded.",
            NO_PONDING_LIMITATION,
        ],
    }
    return manifest


def season_envelope_block(files: dict[str, dict], rights: dict) -> dict:
    """The manifest's ``season_envelope`` block: what the layer is, its licence and credit, and its three files.

    The files are named by address, SHA-256 and size only. Every figure derived from product 4009 (areas, the
    comparison with the model, residents) is in the statistics file, under the product's own licence; the bake
    refuses a manifest whose block holds any other number (``floodguard.replay_manifest.season_envelope_problems``).
    """
    return {
        "id": ENVELOPE_SOURCE_ID, "lane": ENVELOPE_LANE, "evidence_tier": unosat4009.EVIDENCE_TIER, "shown": True,
        "label": unosat4009.LABEL, "caption": unosat4009.CAPTION, "standard_sentence": unosat4009.STANDARD_SENTENCE,
        "day_independent": True,
        "day_rule": "The layer has its own toggle: no replay day selects it, and it is not among the day observations.",
        "temporal_relation": "season_envelope", "season_window": unosat4009.SEASON_WINDOW, "source_timestamp": rights["source_timestamp"],
        "licence": rights["licence"], "licence_url": rights["licence_url"], "credit": rights["credit"],
        "map_credit": unosat4009.map_credit(rights["licence"]),
        "rights_record": rights["record"], "rights_note": rights_wording(rights)["rights_note"],
        "confidence": "low", "confidence_reason": unosat4009.CONFIDENCE_REASON,
        "assumptions": ENVELOPE_ASSUMPTIONS,
        "urls": [rights["product_url"], rights["dataset_url"]],
        "files_rule": ("Derived files keep their own folder and licence. This manifest names them by address, hash and size only; "
                       "every figure derived from the product is in the statistics file."),
        "files": {key: {name: files[key][name] for name in ("href", "sha256", "bytes")} for key in ("raster", "statistics", "licence")},
    }


def envelope_check(files: dict[str, dict], rights: dict) -> dict:
    """The season-envelope comparison as an external check: a role, a use and the statistics file, with no figure."""
    return {"id": ENVELOPE_CHECK_ID,
            # Never "observed": the envelope is a scenario layer, not the observed side of a check (decision D3).
            "compared_with": ("UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; "
                              "the product is described to 22 Oct); a scenario layer, not an observation for any replay day"),
            "role": COMPARISON_ROLE, "title": unosat4009.COMPARISON_TITLE, "scope": "Mae Sai district",
            "statistics": {name: files["statistics"][name] for name in ("href", "sha256", "bytes")},
            "use": unosat4009.COMPARISON_USE, "tuning_rule": unosat4009.TUNING_RULE,
            "urls": [rights["product_url"], rights["dataset_url"]]}


def normalise_utc(value: str) -> str:
    """Return an ISO 8601 date-time as UTC with a ``Z`` suffix."""
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_problems(manifest: dict) -> list[str]:
    """Evidence-contract, rights and JSON-schema problems of a composed manifest (empty when it may be written).

    While the owners have not confirmed the product 4009 rights record, a manifest that names a file for the
    product, or marks it as shown, is refused. Once it ships, its block may hold the three files' addresses, hashes
    and sizes and no other number, and nothing of it may sit among the day observations
    (``floodguard.replay_manifest.season_envelope_problems``). The shelter plan's sub-blocks are checked too
    (``floodguard.replay_manifest.shelter_plan_problems``): each needs its own evidence block in its lane, the
    capacity figures must add up, and no participation share or listed capacity may be published.
    """
    schema = json.loads((ROOT / SCHEMA_REL).read_text(encoding="utf-8"))
    rights = [] if owner_confirmed(load_rights_basis(RIGHTS_RECORD)) else unconfirmed_product_citations(manifest)
    return (evidence_problems(manifest) + shelter_plan_problems(manifest) + season_envelope_problems(manifest) + rights
            + schema_problems(manifest, schema))


RECEIPT_ASSUMPTIONS = [
    "Input paths are relative to the external data root (FLOODGUARD_EXTERNAL_DATA) or to the repository root; no machine path is recorded.",
    "The same inputs give the same bytes only with the same library versions: another GDAL, PROJ, WebP, zlib or pysheds build can change bytes without changing the method.",
    "The OpenStreetMap input is the Geofabrik PBF itself: the bake reads the replay area's multipolygons and points from it on every run and keeps no derived cache, so no intermediate file stands between the receipt and the result.",
    "The receipt lists files, not their meaning: it does not make the reconstruction an observation.",
    "generated_at is a declared value (or the newest dated input), not a clock reading; a bake that changes any output file must declare a new one, and the commit that carries the revision records when the files were written.",
    "Bake sources are hashed with CRLF read as LF, so a Windows checkout gives the same hashes.",
]


BAKE_SOURCES = (
    GENERATED_BY,
    "scripts/mae_sai_timeline_evacuation.py",
    "scripts/mae_sai_timeline_observations.py",
    "scripts/mae_sai_timeline_unosat4009.py",
    "src/floodguard/bake_receipt.py",
    "src/floodguard/evacuation_access.py",
    "src/floodguard/flood_timeline.py",
    "src/floodguard/optical_water_check.py",
    "src/floodguard/replay_exports.py",
    "src/floodguard/replay_manifest.py",
    "src/floodguard/rights_basis.py",
    "src/floodguard/season_envelope.py",
    "src/floodguard/shelter_validation.py",
    SCHEMA_REL.as_posix(),
)
"""This script, the repository modules it imports and the schema the manifest must follow (a unit test checks the imports)."""


def bake_sources() -> list[dict]:
    """Line-ending-neutral SHA-256 of every file in :data:`BAKE_SOURCES`, for the input receipt."""
    return source_hashes([ROOT / path for path in BAKE_SOURCES], ROOT)


def bake(external: Path, out_dir: Path, generated_at: str | None = None) -> tuple[dict, dict, InputReceipt]:
    """Run the whole bake into ``out_dir`` and return ``(manifest, build result, input receipt)``.

    ``generated_at`` is the declared bake time (see :func:`compose_manifest`). A manifest that breaks the evidence
    contract or the JSON schema is not written.
    """
    receipt = InputReceipt({"external": external, "repo": ROOT})
    result = build(external, out_dir, receipt.track)
    if "export_data" in result:
        # The export pack carries the same generation time and input hashes as the manifest that lists it.
        result["exports"] = write_exports(result, out_dir, generated_stamp(result, generated_at)[0], receipt.entries())
    if "season_envelope_data" in result:
        # The product 4009 files carry the same generation time as the manifest that names them.
        result["season_envelope"] = write_season_envelope(result, out_dir, generated_stamp(result, generated_at)[0])
    manifest = compose_manifest(result, inputs=receipt.entries(), generated_at=generated_at)
    problems = manifest_problems(manifest)
    if problems:
        raise ReplayManifestError("timeline.json breaks its evidence contract:\n  " + "\n  ".join(problems))
    (out_dir / "timeline.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest, result, receipt


def receipt_document(manifest: dict, receipt: InputReceipt, out_dir: Path) -> dict:
    """Assemble the input receipt for a finished bake in ``out_dir``."""
    inputs = receipt.entries()
    outputs = directory_listing(out_dir)
    return {
        "schema": RECEIPT_SCHEMA,
        "study_id": manifest["study_id"], "revision": manifest["revision"], "generated_by": GENERATED_BY,
        "purpose": "Every input file the bake opened, so the published revision can be rebuilt and compared byte for byte (--verify).",
        "generated_at": {"value": manifest.get("generated_at"), "basis": manifest.get("generated_at_basis")},
        "source_timestamp": manifest["source_timestamp"],
        "confidence": manifest["confidence"],
        "confidence_reason": "Confidence of the baked reconstruction, copied from timeline.json. The receipt itself is an exact file record.",
        "assumptions": RECEIPT_ASSUMPTIONS,
        "official_warning": False, "operational_status": "non_operational", "can_feed_decision_layer": False,
        "roots": {"external": "FLOODGUARD_EXTERNAL_DATA or --external-root (kept outside Git)", "repo": "repository root"},
        "input_count": len(inputs), "input_bytes": sum(row["bytes"] for row in inputs),
        "inputs": inputs,
        "outputs": {"folder": OUT_REL.as_posix(), "file_count": len(outputs), "bytes": sum(row["bytes"] for row in outputs), "files": outputs},
        "code": bake_sources(),
        "libraries": library_versions(),
        "platform": {"system": platform.system(), "machine": platform.machine()},
    }


def write_receipt(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def default_receipt_path(out_dir: Path) -> Path:
    """The committed receipt for the committed revision folder; a sibling file for any other output folder."""
    if out_dir.resolve() == (ROOT / OUT_REL).resolve():
        return ROOT / RECEIPT_REL
    return out_dir.parent / f"{out_dir.name}_input_receipt.json"


def recorded_receipt(receipt_path: Path) -> dict:
    """The receipt written by an earlier bake, or an empty mapping when there is none."""
    return json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}


def resolve_generated_at(argument: str | None, recorded: dict) -> tuple[str | None, str]:
    """Return the ``generated_at`` to bake with and where it came from.

    Order: the ``--generated-at`` argument; else the value an earlier bake declared and recorded in the receipt;
    else ``None``, which makes the bake use the newest dated input. The machine clock is never read. A plain bake
    may keep a carried value only when :func:`carry_blockers` finds nothing (see :func:`main`).
    """
    if argument:
        return normalise_timestamp(argument), "declared with --generated-at"
    carried = recorded.get("generated_at") if isinstance(recorded.get("generated_at"), dict) else None
    if carried and carried.get("basis") == "declared" and carried.get("value"):
        return normalise_timestamp(carried["value"]), "carried from the recorded receipt (pass --generated-at to declare a new time)"
    return None, "newest dated input (no time was declared)"


def carry_blockers(document: dict, recorded: dict) -> list[str]:
    """Why a bake may not carry the recorded ``generated_at``: every output file that differs from the recorded bake.

    ``document`` is the receipt of the fresh bake, ``recorded`` the receipt of the earlier one. A declared time
    describes the files of the bake that declared it; a bake that writes other bytes needs a new one.
    """
    recorded_files = {row["name"]: row["sha256"] for row in recorded.get("outputs", {}).get("files", [])}
    fresh_files = {row["name"]: row["sha256"] for row in document["outputs"]["files"]}
    if not recorded_files:
        return ["the recorded receipt lists no output files"]
    notes = []
    for name in sorted(fresh_files.keys() | recorded_files.keys()):
        if name not in recorded_files:
            notes.append(f"new file: {name}")
        elif name not in fresh_files:
            notes.append(f"no longer written: {name}")
        elif fresh_files[name] != recorded_files[name]:
            notes.append(f"different bytes: {name}")
    return notes


def verify(external: Path, committed: Path, receipt_path: Path, work_root: Path | None = None, generated_at: str | None = None) -> int:
    """Bake into a temporary folder and byte-compare it with ``committed``; return 0 only when every file matches.

    Nothing is written to ``committed`` or to ``receipt_path``. Differences in inputs, bake sources or library
    versions against the recorded receipt are reported to explain a mismatch; only the byte comparison decides the
    exit code. ``generated_at`` defaults to the value recorded in the receipt.
    """
    if not committed.is_dir():
        print(f"verify: the committed folder does not exist: {committed.name}")
        return 1
    recorded = recorded_receipt(receipt_path)
    stamp, origin = resolve_generated_at(generated_at, recorded)
    with tempfile.TemporaryDirectory(prefix="mae-sai-timeline-verify-", dir=work_root) as tmp:
        fresh = Path(tmp) / committed.name
        if fresh.resolve() == committed.resolve():
            raise RuntimeError("--verify must never bake into the committed folder")
        manifest, _, receipt = bake(external, fresh, generated_at=stamp)
        comparison = compare_directories(fresh, committed)
        document = receipt_document(manifest, receipt, fresh)
    print(f"verify: generated_at {manifest.get('generated_at')} ({origin})")
    print(f"verify: {comparison.summary()} ({committed.name}, {document['outputs']['bytes']:,} bytes in the fresh bake)")
    for label, names in (("different bytes", comparison.different), ("committed but not baked", comparison.missing_from_fresh),
                         ("baked but not committed", comparison.extra_in_fresh)):
        for name in names:
            print(f"verify: {label}: {name}")
    if recorded:
        for note in input_differences(document["inputs"], recorded.get("inputs", [])):
            print(f"verify: input note: {note}")
        for note in source_differences(document["code"], recorded.get("code", [])):
            print(f"verify: code note: {note}")
        for note in version_differences(document["libraries"], recorded.get("libraries", {})):
            print(f"verify: library note: {note}")
    else:
        print("verify: no recorded input receipt to compare with")
    print("verify: PASS" if comparison.matches else "verify: FAIL")
    return 0 if comparison.matches else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--external-root", default=os.environ.get("FLOODGUARD_EXTERNAL_DATA"),
                        help="Folder holding the external rasters (or set FLOODGUARD_EXTERNAL_DATA).")
    parser.add_argument("--out", default=str(ROOT / OUT_REL),
                        help="Folder to bake into; with --verify, the committed folder to compare against (never written).")
    parser.add_argument("--receipt", default=None,
                        help="Input receipt to write (or, with --verify, to compare with). Defaults to the committed receipt for the committed folder.")
    parser.add_argument("--generated-at", default=None,
                        help="Bake time to record as generated_at (ISO 8601 with a UTC offset, e.g. 2026-10-01T21:00:00+07:00). "
                             "Without it the value in the recorded receipt is carried, which a plain bake may do only when it reproduces the "
                             "recorded output files; with neither, the newest dated input is used. The machine clock is never read.")
    parser.add_argument("--verify", action="store_true",
                        help="Bake into a temporary folder and byte-compare with --out; exit non-zero on any difference.")
    args = parser.parse_args(argv)
    if not args.external_root:
        parser.error("--external-root or FLOODGUARD_EXTERNAL_DATA is required")
    out_dir = Path(args.out)
    receipt_path = Path(args.receipt) if args.receipt else default_receipt_path(out_dir)
    if args.verify:
        return verify(Path(args.external_root), out_dir, receipt_path, generated_at=args.generated_at)
    recorded = recorded_receipt(receipt_path)
    stamp, origin = resolve_generated_at(args.generated_at, recorded)
    if stamp is not None and not args.generated_at:
        # A carried time is true only for the files it was declared for: bake aside first, and publish the result
        # only when it reproduces every recorded output file.
        with tempfile.TemporaryDirectory(prefix="mae-sai-timeline-bake-") as tmp:
            staging = Path(tmp) / out_dir.name
            manifest, result, receipt = bake(Path(args.external_root), staging, generated_at=stamp)
            document = receipt_document(manifest, receipt, staging)
            blockers = carry_blockers(document, recorded)
            if blockers:
                print(f"generated_at: the recorded time {stamp} cannot be carried, because this bake does not reproduce the recorded files.",
                      file=sys.stderr)
                notes = [*blockers,
                         *(f"input note: {note}" for note in input_differences(document["inputs"], recorded.get("inputs", []))),
                         *(f"code note: {note}" for note in source_differences(document["code"], recorded.get("code", []))),
                         *(f"library note: {note}" for note in version_differences(document["libraries"], recorded.get("libraries", {})))]
                for note in notes:
                    print(f"  {note}", file=sys.stderr)
                print("Declare when these files are generated with --generated-at (ISO 8601 with a UTC offset). Nothing was written.",
                      file=sys.stderr)
                return 2
            shutil.copytree(staging, out_dir, dirs_exist_ok=True)
    else:
        manifest, result, receipt = bake(Path(args.external_root), out_dir, generated_at=stamp)
    write_receipt(receipt_path, receipt_document(manifest, receipt, out_dir))
    print(f"generated_at: {manifest.get('generated_at')} ({origin})")
    print(json.dumps(manifest["s1_anchor"], indent=1))
    for d in result["days"]:
        s = d["stats"]
        print(d["date"], d["phase"], d["stage_m"], s["flooded_km2"], s["road_km_impassable"], s["road_km_wet"], s["facilities_wet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
