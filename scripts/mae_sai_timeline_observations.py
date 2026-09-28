"""Observation stages for the Mae Sai timeline bake: VIIRS daily flood maps and HII hourly rain gauges.

Imported by ``scripts/build_mae_sai_flood_timeline.py``. VIIRS flood fraction (NOAA/GMU, 375 m) is optical and
cloud-limited; it is compared with the reconstruction only inside clear-sky pixels, at the nominal early-afternoon
overpass. Rain gauges are observations of forcing, not of flooding.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
import zipfile

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds as window_from_bounds

VIIRS_CLOUD = 30
VIIRS_LAND = 17
VIIRS_WATER = 99
VIIRS_FLOOD_MIN, VIIRS_FLOOD_MAX = 100, 200  # value - 100 = flood-water fraction (%)
VIIRS_OVERPASS_LOCAL_HOUR = 13.5  # NOAA-20 / S-NPP daytime passes around 13:30 local solar time
REPLAY_START = datetime(2024, 9, 9)  # 00:00 ICT
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


def rainfall(folder: Path, hours: int) -> dict:
    """Hourly rain (mm) per station for the replay hours (index 0 = 9 Sep 00:00 ICT, the hour ending at +1 h)."""
    meta: dict[str, dict] = {}
    for catalog, name in (("mou", "mou_0all_stn_metadata.csv"), ("main", "main_0all_stn_metadata.csv")):
        path = folder / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
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
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
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
