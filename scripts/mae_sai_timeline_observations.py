"""Observation stages for the Mae Sai timeline bake: VIIRS daily flood maps, a Sentinel-2 water check and HII rain gauges.

Imported by ``scripts/build_mae_sai_flood_timeline.py``. VIIRS flood fraction (NOAA/GMU, 375 m) is optical and
cloud-limited; it is compared with the reconstruction only inside clear-sky pixels, at the nominal early-afternoon
overpass. The Sentinel-2 water check counts water or saturated mud (MNDWI > 0) on the clear pixels of two L2A
scenes; its comparison with the model is indicative. Rain gauges are observations of forcing, not of flooding.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
import zipfile

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds as window_from_bounds

import floodguard.optical_water_check as water_check

VIIRS_CLOUD = 30
VIIRS_LAND = 17
VIIRS_WATER = 99
VIIRS_FLOOD_MIN, VIIRS_FLOOD_MAX = 100, 200  # value - 100 = flood-water fraction (%)
VIIRS_OVERPASS_LOCAL_HOUR = 13.5  # NOAA-20 / S-NPP daytime passes around 13:30 local solar time
REPLAY_START = datetime(2024, 9, 9)  # 00:00 ICT
S2_CHECK_RES_M = 20.0  # The Sentinel-2 water check runs at the resolution of its coarser band (B11, short-wave infrared).
S2_THRESHOLD_SENSITIVITY = (0.1, 0.2)  # Stricter MNDWI thresholds reported beside the main one (0).
RAIN_STATIONS = {
    "MOU189": {"catalog": "mou", "name_en": "Tham Luang - Khun Nam Nang Non NP office (Pong Pha)", "name_th": "อุทยานแห่งชาติถ้ำหลวง-ขุนน้ำนางนอน (โป่งผา)"},
    "DIWO": {"catalog": "main", "name_en": "Wiang Phang Kham Subdistrict Municipality", "name_th": "เทศบาลตำบลเวียงพางคำ"},
}


def viirs_day(zip_path: Path, bounds_ll: tuple[float, float, float, float]) -> tuple[np.ndarray, rasterio.Affine]:
    """Read the VIIRS daily code raster for the lon/lat box (with a one-pixel margin)."""
    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".tif"))
    with rasterio.open(f"/vsizip/{zip_path.as_posix()}/{member}") as src:
        win = window_from_bounds(*bounds_ll, transform=src.transform).round_offsets().round_lengths()
        win = rasterio.windows.Window(win.col_off - 1, win.row_off - 1, win.width + 2, win.height + 2)
        return src.read(1, window=win, boundless=True, fill_value=0), src.window_transform(win)


def viirs_classes(codes: np.ndarray) -> dict[str, np.ndarray]:
    flood = (codes > VIIRS_FLOOD_MIN) & (codes <= VIIRS_FLOOD_MAX)
    return {
        "cloud": codes == VIIRS_CLOUD,
        "clear": (codes == VIIRS_LAND) | (codes == VIIRS_WATER) | ((codes >= VIIRS_FLOOD_MIN) & (codes <= VIIRS_FLOOD_MAX)),
        "water": codes == VIIRS_WATER,
        "flood_fraction": np.where(flood, (codes.astype(float) - VIIRS_FLOOD_MIN) / 100.0, 0.0),
    }


def pixel_area_km2(transform: rasterio.Affine, shape: tuple[int, int]) -> np.ndarray:
    rows = np.arange(shape[0])
    lat = transform.f + (rows + 0.5) * transform.e
    dx = abs(transform.a) * 111.32 * np.cos(np.radians(lat))
    dy = abs(transform.e) * 110.57
    return np.repeat((dx * dy)[:, None], shape[1], axis=1)


def viirs_comparison(zip_path: Path, day: datetime, district_geoms_ll: list, model_wet_fraction, stage: float,
                     bounds_ll: tuple[float, float, float, float]) -> dict:
    """Clear-sky comparison of VIIRS flood area with the model's wet fraction on the VIIRS grid, district only.

    ``model_wet_fraction(dst_transform, dst_shape, stage)`` returns the modelled wet fraction per VIIRS pixel
    (out-of-channel water only).
    """
    codes, transform = viirs_day(zip_path, bounds_ll)
    cls = viirs_classes(codes)
    district = rasterize([(g, 1) for g in district_geoms_ll], out_shape=codes.shape, transform=transform, fill=0,
                         all_touched=False, dtype="uint8").astype(bool)
    area = pixel_area_km2(transform, codes.shape)
    model = model_wet_fraction(transform, codes.shape, stage)
    clear = cls["clear"] & district & ~cls["water"]
    in_district = district.sum()
    return {
        "date": day.strftime("%Y-%m-%d"),
        "nominal_local_time": (day + timedelta(hours=VIIRS_OVERPASS_LOCAL_HOUR)).strftime("%Y-%m-%dT%H:%M+07:00"),
        "t": round((day - REPLAY_START).total_seconds() / 86400 + VIIRS_OVERPASS_LOCAL_HOUR / 24, 4),
        "cloud_share": round(float((cls["cloud"] & district).sum()) / float(in_district), 3) if in_district else None,
        "clear_km2": round(float(area[clear].sum()), 1),
        "viirs_flood_km2_clear": round(float((cls["flood_fraction"] * area)[clear].sum()), 2),
        "model_stage_m": round(stage, 3),
        "model_flood_km2_clear": round(float((model * area)[clear].sum()), 2),
        "model_flood_km2_district": round(float((model * area)[district].sum()), 2),
    }, codes, transform


def viirs_png_codes(codes: np.ndarray) -> np.ndarray:
    """Compact display classes: 0 no data/outside, 1 cloud, 2 clear land, 3 permanent water, 4+ flood fraction bins."""
    out = np.zeros(codes.shape, dtype=np.uint8)
    out[codes == VIIRS_CLOUD] = 1
    out[codes == VIIRS_LAND] = 2
    out[codes == VIIRS_WATER] = 3
    frac = np.clip(codes.astype(int) - VIIRS_FLOOD_MIN, 0, 100)
    flood = (codes > VIIRS_FLOOD_MIN) & (codes <= VIIRS_FLOOD_MAX)
    out[flood] = 4 + np.minimum(frac[flood] // 25, 3)  # 4: 1-24 %, 5: 25-49 %, 6: 50-74 %, 7: 75-100 %
    return out


def sentinel2_band(path: Path, crs: str, transform: rasterio.Affine, shape: tuple[int, int], resampling: Resampling) -> np.ndarray:
    """Read one Sentinel-2 L2A band onto a north-up grid as digital numbers (0 = no data).

    Only the part of the file that covers the grid is read. Reflectance bands are averaged (``Resampling.average``,
    no-data cells left out); the scene classification is copied with ``Resampling.nearest``.
    """
    height, width = shape
    bounds = (transform.c, transform.f + height * transform.e, transform.c + width * transform.a, transform.f)
    with rasterio.open(path) as src:
        box = transform_bounds(crs, src.crs, *bounds, densify_pts=21)
        win = window_from_bounds(*box, transform=src.transform).round_offsets().round_lengths()
        win = rasterio.windows.Window(win.col_off - 4, win.row_off - 4, win.width + 8, win.height + 8)
        dn = src.read(1, window=win, boundless=True, fill_value=0).astype(np.float32)
        out = np.zeros(shape, dtype=np.float32)
        reproject(dn, out, src_transform=src.window_transform(win), src_crs=src.crs, dst_transform=transform, dst_crs=crs,
                  resampling=resampling, src_nodata=0, dst_nodata=0)
    return out


def sentinel2_wet_surface(scene_dir: Path, crs: str, transform: rasterio.Affine, shape: tuple[int, int],
                          track=lambda path: path) -> tuple[water_check.WetSurface, np.ndarray]:
    """MNDWI water-or-saturated-mud mask and scene classification of one L2A scene on a 20 m grid.

    The 10 m green band is averaged onto the grid of the 20 m short-wave infrared band, so the index is computed
    at the resolution of its coarser band. ``track`` is called with each input file as it is opened.
    """
    green = sentinel2_band(track(scene_dir / "green.tif"), crs, transform, shape, Resampling.average)
    swir16 = sentinel2_band(track(scene_dir / "swir16.tif"), crs, transform, shape, Resampling.nearest)
    scl = np.rint(sentinel2_band(track(scene_dir / "scl.tif"), crs, transform, shape, Resampling.nearest)).astype(np.uint8)
    return water_check.wet_surface(green, swir16, scl), scl


def sentinel2_water_check(pre_dir: Path, event_dir: Path, crs: str, bounds: tuple[float, float, float, float], district: np.ndarray,
                          permanent: np.ndarray, model_wet: np.ndarray, cell_m: float, track=lambda path: path) -> dict:
    """Water or saturated mud in two Sentinel-2 L2A scenes (MNDWI > 0 on clear pixels) and the model beside the later one.

    ``district``, ``permanent`` and ``model_wet`` are masks on the replay's north-up grid of ``cell_m`` metres over
    ``bounds``; the index is computed on the 20 m grid that nests in it. ``permanent`` holds the cells left out of
    the water area on both dates, and ``model_wet`` is the modelled water at the acquisition time of the event
    scene. The result holds figures only: an observed part (``scenes``, ``change``), a model part
    (``model_at_event_scene``) and a sensitivity list. It is an indicative comparison, not a flood extent.
    """
    factor = S2_CHECK_RES_M / cell_m
    if factor < 1 or factor != int(factor) or any(size % int(factor) for size in district.shape):
        raise ValueError("the replay grid must nest in the 20 m Sentinel-2 grid")
    factor = int(factor)
    shape = (district.shape[0] // factor, district.shape[1] // factor)
    transform = from_origin(bounds[0], bounds[3], S2_CHECK_RES_M, S2_CHECK_RES_M)
    cell_km2 = cell_m**2 / 1e6
    up = lambda mask: water_check.upsample(mask, factor)  # noqa: E731
    pre, pre_scl = sentinel2_wet_surface(pre_dir, crs, transform, shape, track)
    event, event_scl = sentinel2_wet_surface(event_dir, crs, transform, shape, track)

    def scene(surface: water_check.WetSurface, scl: np.ndarray) -> dict:
        return {**water_check.scene_areas(up(surface.wet), up(surface.clear), district, permanent, cell_km2),
                "scl_class_km2": water_check.class_areas(up(scl), district, cell_km2)}

    def variant(name: str, rule: str, pre_surface: water_check.WetSurface, event_surface: water_check.WetSurface) -> dict:
        event_areas = water_check.scene_areas(up(event_surface.wet), up(event_surface.clear), district, permanent, cell_km2)
        pre_areas = water_check.scene_areas(up(pre_surface.wet), up(pre_surface.clear), district, permanent, cell_km2)
        change = water_check.new_water_areas(up(event_surface.wet), up(event_surface.clear), up(pre_surface.wet), up(pre_surface.clear),
                                             district, permanent, cell_km2)
        overlap = water_check.model_overlap(up(event_surface.wet), up(event_surface.clear), model_wet, district, permanent, cell_km2)
        return {"id": name, "rule": rule, "event_clear_share": event_areas["clear_share"], "event_water_km2": event_areas["water_km2"],
                "pre_event_clear_share": pre_areas["clear_share"], "pre_event_water_km2": pre_areas["water_km2"],
                "new_water_km2": change["new_water_km2"], "model_agreement_iou": overlap["model_agreement_iou"]}

    def with_threshold(surface: water_check.WetSurface, threshold: float) -> water_check.WetSurface:
        return water_check.WetSurface(surface.index, surface.clear, surface.clear & (surface.index > threshold))

    def strict(surface: water_check.WetSurface, scl: np.ndarray) -> water_check.WetSurface:
        clear = surface.clear & np.isin(scl, sorted(water_check.SCL_STRICT_CLEAR))
        return water_check.WetSurface(surface.index, clear, surface.wet & clear)

    sensitivity = [variant("strict_clear", "Only scene-classification classes 4 (vegetation), 5 (not vegetated) and 6 (water) count as clear.",
                           strict(pre, pre_scl), strict(event, event_scl))]
    sensitivity += [variant(f"threshold_{threshold:.1f}".replace(".", "_"), f"A clear pixel counts when MNDWI > {threshold:.1f}.",
                            with_threshold(pre, threshold), with_threshold(event, threshold)) for threshold in S2_THRESHOLD_SENSITIVITY]
    return {
        "resolution_m": S2_CHECK_RES_M, "threshold": water_check.MNDWI_THRESHOLD,
        "district_km2": round(float(np.count_nonzero(district)) * cell_km2, 2),
        "permanent_water_km2": round(float(np.count_nonzero(permanent & district)) * cell_km2, 2),
        "scenes": {"pre_event": scene(pre, pre_scl), "event": scene(event, event_scl)},
        "change": water_check.new_water_areas(up(event.wet), up(event.clear), up(pre.wet), up(pre.clear), district, permanent, cell_km2),
        "model_at_event_scene": water_check.model_overlap(up(event.wet), up(event.clear), model_wet, district, permanent, cell_km2,
                                                          earlier_clear=up(pre.clear)),
        "sensitivity": sensitivity,
    }


def rainfall(folder: Path, hours: int, track=lambda path: path) -> dict:
    """Hourly rain (mm) per station for the replay hours (index 0 = 9 Sep 00:00 ICT, the hour ending at +1 h).

    ``track`` is called with each input file as it is opened (the bake records them in its input receipt).
    """
    meta: dict[str, dict] = {}
    for catalog, name in (("mou", "mou_0all_stn_metadata.csv"), ("main", "main_0all_stn_metadata.csv")):
        path = folder / name
        if not path.exists():
            continue
        with track(path).open(encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                code = row.get("Station_Code")
                if code in RAIN_STATIONS:
                    meta[code] = row
    stations = []
    series: dict[str, list[float | None]] = {}
    for code, info in RAIN_STATIONS.items():
        path = folder / f"{code}.csv"
        if not path.exists():
            continue
        values: list[float | None] = [None] * hours
        with track(path).open(encoding="utf-8-sig", errors="replace") as handle:
            for row in csv.DictReader(handle):
                try:  # The monthly files repeat their header line; skip anything that is not a data row.
                    stamp = datetime.strptime(row["measure_datetime"], "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    continue
                index = int((stamp - REPLAY_START).total_seconds() // 3600)
                if 0 <= index < hours and row.get("rainfall_1h") not in (None, ""):
                    values[index] = float(row["rainfall_1h"])
        m = meta.get(code, {})
        lat, lon = m.get("Latitude"), m.get("Longitude")
        stations.append({"code": code, **{k: v for k, v in info.items() if k != "catalog"},
                         "lat": float(lat) if lat else None, "lon": float(lon) if lon else None,
                         "total_mm": round(sum(v for v in values if v is not None), 1),
                         "max_hour_mm": max((v for v in values if v is not None), default=None),
                         "missing_hours": sum(v is None for v in values)})
        series[code] = values
    return {"stations": stations, "hourly_mm": series}
