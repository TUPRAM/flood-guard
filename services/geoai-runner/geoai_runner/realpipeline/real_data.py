"""Real-data GeoAI for Mae Sai: Sentinel-1 flood mapping + Thai gov layers.

Unlike the synthetic demo scene, this module reads **real** data over Mae Sai
District, Chiang Rai:

* Sentinel-1 RTC (radiometric terrain-corrected, analysis-ready gamma0) from
  Microsoft Planetary Computer -- windowed COG reads, no full-scene download.
* Thai authoritative vector layers from the NGIS/GISTDA ArcGIS services
  (DOPA sub-districts, DWR rivers, highway centrelines) as GeoJSON.

Component A (SAR change detection) is applied to the real pre/post pair to map
the September-2024 Mae Sai flood, then aggregated over the real sub-districts to
drive the Flood Preparedness Priority Score.

Honest caveats (carried into every artifact):
* Sentinel-1 has a ~12-day revisit; the closest post-event same-orbit scene is
  2024-09-15, ~4 days after the ~Sep-11 flood peak, so the detected extent is
  *residual* flooding and under-represents the peak. This is a real limitation
  of single-snapshot SAR and is exactly why susceptibility modelling (Component
  C) complements it.
* C-band VH over vegetated terrain gives a subtle, speckly flood signal;
  multi-look filtering + morphology reduce but do not remove this.
* Nothing here is an official flood warning.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
MAE_SAI_BBOX = (99.83, 20.33, 99.97, 20.49)  # lon/lat
DEFAULT_PRE = "2024-08-22"  # same descending orbit as post (clean geometry)
DEFAULT_POST = "2024-09-15"  # nearest post-event same-orbit acquisition

# TLS context for Thai NGIS/GISTDA ArcGIS fetches (D-01).
#
# This previously set `check_hostname = False` and `verify_mode = CERT_NONE`,
# so authoritative administrative boundaries and river networks were fetched
# over an unauthenticated channel. A MITM could substitute geometry and
# silently corrupt HAND, susceptibility, and every zonal aggregate downstream —
# which directly contradicts this project's provenance claims. Authoritative
# sourcing cannot be asserted over a channel that was never authenticated.
#
# The chain was assumed broken. It is not. Probed 2026-07-29:
#
#     host      ngis.go.th
#     protocol  TLSv1.3
#     subject   *.ngis.go.th        SAN: *.ngis.go.th, ngis.go.th
#     issuer    RapidSSL TLS RSA CA G1
#     notAfter  Sep  4 23:59:59 2026 GMT
#     GET /arcgis/rest/services/Hosted?f=json -> HTTP 200
#
# Verification succeeds against the system trust store with no pinning, so
# CERT_NONE was development convenience rather than a workaround. Use the
# default verifying context.
#
# If this ever starts failing, the certificate above expires 2026-09-04.
# Renewal is the likely cause. Do NOT restore CERT_NONE: pin the CA explicitly
# with `load_verify_locations` and record why in docs/source_registry.md.
_SSL = ssl.create_default_context()


class RealDataError(RuntimeError):
    """Raised when a real-data fetch or process step fails."""


# --------------------------------------------------------------------------- #
# Sentinel-1 (Planetary Computer)
# --------------------------------------------------------------------------- #
@dataclass
class RealFloodResult:
    flood_binary: np.ndarray  # EPSG:4326 grid
    flood_probability: np.ndarray
    permanent_water: np.ndarray
    transform: object
    crs: str
    metrics: dict
    artifacts: dict[str, Path] = field(default_factory=dict)


def _pc_client():
    """Open a signed Planetary Computer STAC client.

    Deliberately not ``geoai.pc_stac_search`` / ``geoai.pc_stac_download``
    (D-34). Those helpers fetch whole assets; a Sentinel-1 RTC scene is
    multi-gigabyte and Mae Sai is a 0.14 x 0.16 degree box. Driving
    ``pystac_client`` directly lets :func:`_read_band` do a windowed COG read
    through ``rasterio.windows.from_bounds``, which is the difference between
    a few megabytes and a full scene download per band per date.

    Keeping this hand-rolled also means the pipeline does not require
    ``geoai-py`` merely to locate imagery -- acquisition stays usable in the
    dependency-light environment. Use the ``search-stac`` skill for
    exploration; use this for the governed run.
    """

    try:
        import planetary_computer as pc
        import pystac_client
    except Exception as exc:  # pragma: no cover
        raise RealDataError(
            "pystac_client + planetary_computer are required for real Sentinel-1."
        ) from exc
    return pystac_client.Client.open(PC_STAC, modifier=pc.sign_inplace)


def _find_rtc_scene(bbox, date: str):
    cat = _pc_client()
    items = sorted(
        cat.search(collections=["sentinel-1-rtc"], bbox=list(bbox), datetime=date).items(),
        key=lambda i: i.datetime,
    )
    if not items:
        raise RealDataError(f"No Sentinel-1 RTC scene found for {date} over {bbox}.")
    return items[0]


def _read_band(item, pol: str, bbox, out_shape):
    import os

    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(item.assets[pol].href) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(left, bottom, right, top, transform=src.transform)
        data = src.read(1, window=win, out_shape=out_shape, boundless=True, fill_value=0)
        return data.astype("float32"), str(src.crs)


def fetch_sentinel1_rtc_pair(
    bbox=MAE_SAI_BBOX,
    pre_date: str = DEFAULT_PRE,
    post_date: str = DEFAULT_POST,
    out_shape: tuple[int, int] = (1024, 1024),
) -> dict:
    """Fetch a real pre/post Sentinel-1 RTC VV+VH pair over the bbox."""

    pre = _find_rtc_scene(bbox, pre_date)
    post = _find_rtc_scene(bbox, post_date)
    bands = {}
    for tag, item in (("pre", pre), ("post", post)):
        for pol in ("vv", "vh"):
            arr, utm_crs = _read_band(item, pol, bbox, out_shape)
            bands[f"{tag}_{pol}"] = arr
    return {
        "bands": bands,
        "pre_id": pre.id,
        "post_id": post.id,
        "pre_datetime": pre.datetime.isoformat(),
        "post_datetime": post.datetime.isoformat(),
        "utm_crs": utm_crs,
        "bbox": bbox,
        "out_shape": out_shape,
    }


def _to_db(x):
    x = np.where(x > 0, x, np.nan)
    return 10.0 * np.log10(x)


def _boxcar(a, k=5):
    a = np.nan_to_num(a, nan=0.0)
    p = k // 2
    ap = np.pad(a, p, mode="edge")
    out = np.zeros_like(a)
    for dy in range(k):
        for dx in range(k):
            out += ap[dy : dy + a.shape[0], dx : dx + a.shape[1]]
    return out / (k * k)


def _open_close(mask, iters=1):
    def ero(x):
        xp = np.pad(x, 1)
        o = x.copy()
        for dy in range(3):
            for dx in range(3):
                o = o & xp[dy : dy + x.shape[0], dx : dx + x.shape[1]]
        return o

    def dil(x):
        xp = np.pad(x, 1)
        o = x.copy()
        for dy in range(3):
            for dx in range(3):
                o = o | xp[dy : dy + x.shape[0], dx : dx + x.shape[1]]
        return o

    for _ in range(iters):
        mask = ero(mask)
    for _ in range(iters):
        mask = dil(mask)
    return mask


def real_sar_flood_extent(
    pair: dict,
    output_dir: str | Path,
    *,
    drop_threshold_db: float = 2.5,
    post_water_db: float = -15.0,
    permanent_water_db: float = -20.0,
    multilook: int = 5,
) -> RealFloodResult:
    """Run Component A change detection on a real Sentinel-1 pair.

    Writes ``real_flood_extent.tif`` (EPSG:4326), a probability raster, and a
    GeoJSON polygon layer.
    """

    import rasterio
    from affine import Affine
    from rasterio.features import shapes

    b = pair["bands"]
    pre_vh = _to_db(_boxcar(b["pre_vh"], multilook))
    post_vh = _to_db(_boxcar(b["post_vh"], multilook))
    pre_vv = _to_db(_boxcar(b["pre_vv"], multilook))
    post_vv = _to_db(_boxcar(b["post_vv"], multilook))
    vh_drop = pre_vh - post_vh
    vv_drop = pre_vv - post_vv
    combined = 0.6 * vh_drop + 0.4 * vv_drop

    permanent_water = (pre_vh < permanent_water_db) & (post_vh < permanent_water_db)
    prob = np.clip((combined - drop_threshold_db) / (6.0 - drop_threshold_db), 0, 1)
    prob = np.where(np.isfinite(prob), prob, 0.0)
    flood = (prob >= 0.5) & (post_vh < post_water_db) & (~permanent_water)
    flood = _open_close(flood, 1).astype("uint8")

    # Build EPSG:4326 transform for the read window (bbox / out_shape).
    left, bottom, right, top = pair["bbox"]
    h, w = pair["out_shape"]
    transform = Affine.translation(left, top) * Affine.scale((right - left) / w, (bottom - top) / h)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = dict(
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        crs="EPSG:4326",
        transform=transform,
        compress="deflate",
    )
    flood_path = output_dir / "real_flood_extent.tif"
    with rasterio.open(flood_path, "w", dtype="uint8", nodata=0, **profile) as dst:
        dst.write(flood, 1)
    prob_path = output_dir / "real_flood_probability.tif"
    with rasterio.open(prob_path, "w", dtype="float32", **profile) as dst:
        dst.write(prob.astype("float32"), 1)

    feats = []
    for geom, val in shapes(flood.astype("int32"), mask=flood.astype(bool), transform=transform):
        if val == 1:
            feats.append({"type": "Feature", "properties": {"class": "flood"}, "geometry": geom})
    vec_path = output_dir / "real_flood_extent.geojson"
    vec_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8"
    )

    metrics = {
        "data_mode": "real_licensed_inputs",
        "source": "Sentinel-1 RTC (Microsoft Planetary Computer)",
        "pre_id": pair["pre_id"],
        "post_id": pair["post_id"],
        "pre_datetime": pair["pre_datetime"],
        "post_datetime": pair["post_datetime"],
        "flood_fraction": round(float(flood.mean()), 4),
        "permanent_water_fraction": round(float(permanent_water.mean()), 4),
        "vh_drop_p90_db": round(float(np.nanpercentile(vh_drop, 90)), 2),
        "vh_drop_p97_db": round(float(np.nanpercentile(vh_drop, 97)), 2),
        "assumptions": (
            "Real Sentinel-1 RTC change detection over Mae Sai. Post scene "
            f"({pair['post_datetime'][:10]}) is ~4 days after the ~Sep-11 flood peak, "
            "so this maps RESIDUAL flooding and under-represents the peak (SAR 12-day "
            "revisit). Non-operational; not an official warning."
        ),
    }
    return RealFloodResult(
        flood_binary=flood,
        flood_probability=prob.astype("float32"),
        permanent_water=permanent_water,
        transform=transform,
        crs="EPSG:4326",
        metrics=metrics,
        artifacts={"flood": flood_path, "probability": prob_path, "vector": vec_path},
    )


# --------------------------------------------------------------------------- #
# Sentinel-1 time series (single relative orbit, disk-cached)
# --------------------------------------------------------------------------- #
def _relative_orbit(item) -> int | None:
    """Read the relative orbit from whichever STAC property carries it."""

    for key in ("sat:relative_orbit", "sat:relative_orbit_number", "s1:relative_orbit"):
        value = item.properties.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):  # pragma: no cover - malformed metadata
                continue
    return None


def fetch_sentinel1_rtc_series(
    bbox=MAE_SAI_BBOX,
    *,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    relative_orbit: int | None = None,
    orbit_direction: str | None = None,
    out_shape: tuple[int, int] = (1024, 1024),
    cache_dir: str | Path | None = None,
    polarisations: tuple[str, ...] = ("vh",),
    max_scenes: int | None = None,
):
    """Fetch a Sentinel-1 RTC time series over ``bbox`` on a **single** orbit.

    Why one orbit only: Sentinel-1's incidence angle spans roughly 30-46 degrees
    across the swath and backscatter varies by several dB with it, so a per-pixel
    baseline built across orbits is bimodal and its deviations are not
    interpretable. This selects the most-populated qualifying relative orbit and
    records how many acquisitions it discarded, rather than silently mixing them.

    Scenes are cached as windowed GeoTIFFs under ``cache_dir`` (~2 MB each at
    1024x1024) and re-reads skip anything already present, so a run interrupted
    part-way through ~180 network reads resumes rather than restarting. The
    returned :class:`~geoai_runner.realpipeline.sar_temporal.S1Series` holds
    paths, never pixels: the full cube would be ~1.5 GB in memory.

    Args:
        relative_orbit: Force a specific orbit; ``None`` picks the most populated.
        orbit_direction: Restrict to ``"ascending"``/``"descending"`` before
            choosing.
        polarisations: Bands to cache. ``vh`` alone is enough for the water
            baseline and halves the download.
        max_scenes: Cap for smoke runs; the manifest records the truncation.

    Returns:
        An ``S1Series`` ready for :func:`sar_temporal.build_seasonal_baseline`.
    """

    from geoai_runner.realpipeline.sar_temporal import S1SceneRef, S1Series

    cache_dir = Path(cache_dir) if cache_dir is not None else Path("s1_series_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    catalogue = _pc_client()
    items = list(
        catalogue.search(
            collections=["sentinel-1-rtc"], bbox=list(bbox), datetime=f"{start}/{end}"
        ).items()
    )
    if not items:
        raise RealDataError(f"no Sentinel-1 RTC scenes for {start}/{end} over {bbox}.")

    discarded: dict[str, int] = {"total_found": len(items)}
    if orbit_direction is not None:
        before = len(items)
        items = [
            item
            for item in items
            if str(item.properties.get("sat:orbit_state", "")).lower() == orbit_direction.lower()
        ]
        discarded["other_orbit_direction"] = before - len(items)

    grouped: dict[int, list] = {}
    missing_orbit = 0
    for item in items:
        orbit = _relative_orbit(item)
        if orbit is None:
            missing_orbit += 1
            continue
        grouped.setdefault(orbit, []).append(item)
    if missing_orbit:
        discarded["missing_relative_orbit"] = missing_orbit
    if not grouped:
        raise RealDataError("no Sentinel-1 scene carried a usable relative-orbit property.")

    chosen = (
        relative_orbit
        if relative_orbit is not None
        else max(grouped, key=lambda orbit: len(grouped[orbit]))
    )
    if chosen not in grouped:
        raise RealDataError(
            f"relative orbit {chosen} has no scenes; available: "
            f"{ {k: len(v) for k, v in sorted(grouped.items())} }."
        )
    selected = sorted(grouped[chosen], key=lambda item: item.datetime)
    discarded["other_relative_orbit"] = sum(len(v) for k, v in grouped.items() if k != chosen)
    if max_scenes is not None and len(selected) > max_scenes:
        discarded["truncated_by_max_scenes"] = len(selected) - max_scenes
        selected = selected[:max_scenes]

    direction = str(selected[0].properties.get("sat:orbit_state", "unknown")).lower()
    scenes: list[S1SceneRef] = []
    failed = 0
    for item in selected:
        paths: dict[str, Path] = {}
        try:
            for pol in polarisations:
                destination = cache_dir / f"{item.id}_{pol}.tif"
                if not destination.exists():
                    array, _ = _read_band(item, pol, bbox, out_shape)
                    _write_cached_band(destination, array, bbox, out_shape)
                paths[pol] = destination
        except Exception:  # pragma: no cover - transient asset/network failure
            failed += 1
            continue
        scenes.append(
            S1SceneRef(
                item_id=item.id,
                datetime=item.datetime.isoformat(),
                relative_orbit=int(chosen),
                orbit_direction=direction,
                paths=paths,
            )
        )
    if failed:
        discarded["unreadable_scenes"] = failed
    if not scenes:
        raise RealDataError("every Sentinel-1 scene in the selected orbit failed to read.")

    return S1Series(
        scenes=tuple(scenes),
        bbox=tuple(bbox),
        out_shape=tuple(out_shape),
        relative_orbit=int(chosen),
        orbit_direction=direction,
        cache_dir=cache_dir,
        discarded=discarded,
    )


def _write_cached_band(path: Path, array, bbox, out_shape) -> Path:
    """Write one windowed band to the series cache in EPSG:4326."""

    import rasterio
    from affine import Affine

    left, bottom, right, top = bbox
    height, width = out_shape
    transform = Affine.translation(left, top) * Affine.scale(
        (right - left) / width, (bottom - top) / height
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(np.asarray(array, dtype="float32"), 1)
    return path


# --------------------------------------------------------------------------- #
# Other real Planetary Computer layers (Sentinel-2, Copernicus DEM, JRC water)
# --------------------------------------------------------------------------- #
S2_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")  # blue,green,red,nir,swir1,swir2


def _read_asset(item, asset_key: str, bbox, out_shape, resampling="bilinear"):
    import os

    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(item.assets[asset_key].href) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(left, bottom, right, top, transform=src.transform)
        return src.read(
            1,
            window=win,
            out_shape=out_shape,
            boundless=True,
            fill_value=0,
            resampling=getattr(Resampling, resampling),
        ).astype("float32")


def fetch_sentinel2_composite(
    bbox=MAE_SAI_BBOX,
    datetime_range: str = "2024-01-15/2024-03-15",
    max_cloud: float = 10.0,
    out_shape: tuple[int, int] = (1024, 1024),
) -> dict:
    """Fetch the least-cloudy real Sentinel-2 L2A 6-band composite over bbox.

    Monsoon skies are cloudy, so the default window is the clear dry season --
    which is itself the honest reason SAR (not optical) is the primary
    all-weather flood sensor.
    """

    cat = _pc_client()
    items = sorted(
        cat.search(
            collections=["sentinel-2-l2a"],
            bbox=list(bbox),
            datetime=datetime_range,
            query={"eo:cloud_cover": {"lt": max_cloud}},
        ).items(),
        key=lambda i: i.properties.get("eo:cloud_cover", 100),
    )
    if not items:
        raise RealDataError(f"No Sentinel-2 scene <{max_cloud}% cloud in {datetime_range}.")
    # A single S2 tile often clips the study area, so mosaic every tile from the
    # SAME acquisition date (same-date tiles are radiometrically consistent, so
    # this avoids seams that mixing dates would introduce).
    best = items[0]
    best_day = best.datetime.date()
    same_day = [it for it in items if it.datetime.date() == best_day]
    layers = []
    for it in same_day:
        try:
            layers.append(np.stack([_read_asset(it, b, bbox, out_shape) for b in S2_BANDS]))
        except Exception:  # skip tiles that fail to read
            continue
    if not layers:
        raise RealDataError("Sentinel-2 tiles could not be read for the study area.")
    mosaic = layers[0]
    for extra in layers[1:]:
        mosaic = np.where(mosaic <= 0, extra, mosaic)  # fill gaps from other tiles
    stack = np.clip(mosaic / 10000.0, 0, 1)  # L2A scale factor -> reflectance
    coverage = float((stack.sum(axis=0) > 0).mean())
    return {
        "stack": stack.astype("float32"),
        "item_id": best.id,
        "datetime": best.datetime.isoformat(),
        "cloud_cover": float(best.properties.get("eo:cloud_cover", -1)),
        "tiles_mosaicked": len(layers),
        "coverage": round(coverage, 4),
        "bands": S2_BANDS,
        "bbox": bbox,
        "out_shape": out_shape,
    }


def fetch_copernicus_dem(bbox=MAE_SAI_BBOX, out_shape: tuple[int, int] = (1024, 1024)) -> dict:
    """Fetch the real Copernicus DEM GLO-30 elevation over bbox (metres)."""

    cat = _pc_client()
    items = list(cat.search(collections=["cop-dem-glo-30"], bbox=list(bbox)).items())
    if not items:
        raise RealDataError("No Copernicus DEM GLO-30 tile found for bbox.")
    tiles = [_read_asset(it, "data", bbox, out_shape) for it in items]
    dem = np.nanmax(np.stack(tiles), axis=0)  # mosaic overlapping tiles
    return {
        "dem": dem.astype("float32"),
        "item_ids": [i.id for i in items],
        "bbox": bbox,
        "out_shape": out_shape,
    }


def fetch_jrc_surface_water(
    bbox=MAE_SAI_BBOX,
    out_shape: tuple[int, int] = (1024, 1024),
    asset: str = "occurrence",
) -> dict:
    """Fetch real JRC Global Surface Water (Pekel et al. 2016) occurrence 0-100."""

    cat = _pc_client()
    items = list(cat.search(collections=["jrc-gsw"], bbox=list(bbox)).items())
    if not items:
        raise RealDataError("No JRC Global Surface Water tile found for bbox.")
    tiles = [_read_asset(it, asset, bbox, out_shape, resampling="nearest") for it in items]
    occ = np.nanmax(np.stack(tiles), axis=0)
    occ = np.where(occ > 100, 0, occ)  # 255 = nodata
    return {
        "occurrence": occ.astype("float32"),
        "item_ids": [i.id for i in items],
        "bbox": bbox,
        "out_shape": out_shape,
    }


OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def fetch_osm_buildings(
    bbox=MAE_SAI_BBOX,
    max_features: int = 4000,
    cache_path: str | Path | None = None,
) -> list[dict]:
    """Fetch real OpenStreetMap building footprint centroids for the bbox.

    Overpass is a free public service and intermittently returns 429/504. We try
    each mirror, and fall back to a previously-cached real response so a
    transient outage does not silently drop Component D.

    On ``geoai.download_overture_buildings`` (D-34): Overture is a genuinely
    useful *second* source, not a replacement. Component D's 463 footprints are
    currently published with a coverage caveat that no measurement backs.
    Fetching the same bbox from Overture and reporting the agreement rate would
    turn that caveat into a number. Deliberately not done here -- an
    independent source belongs in ``research/`` first (ADR-I), and adding it to
    the governed path would change a published figure without an evaluation to
    justify it. Use ``/geoai-skills:overture-data building --bbox ...``.
    """

    query = (
        f"[out:json][timeout:120];"
        f'(way["building"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}););'
        f"out center {max_features};"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    for url in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": "FloodGuard/1.0 (hackathon research)"}
            )
            payload = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
            out = [
                {
                    "id": el.get("id"),
                    "lon": float(el["center"]["lon"]),
                    "lat": float(el["center"]["lat"]),
                    "tags": el.get("tags", {}),
                }
                for el in payload.get("elements", [])
                if el.get("center")
            ]
            if out and cache_path:
                Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cache_path).write_text(json.dumps(out), encoding="utf-8")
            return out
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if cache_path and Path(cache_path).exists():
        cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        if cached:
            return cached
    raise RealDataError("Overpass building query failed on all mirrors: " + "; ".join(errors))


def fetch_overture_buildings(
    bbox=MAE_SAI_BBOX,
    cache_path: str | Path | None = None,
) -> list[dict]:
    """Fetch building footprint centroids from Overture Maps.

    Component D's primary source since 2026-07-29. Overture aggregates OSM with
    ML-derived footprints from Microsoft and Google, so it covers areas OSM has
    never been mapped in -- which is most of Mae Sai district.

    Why the source changed, measured rather than assumed:

    | source                       | buildings in the 8 tambons |
    |------------------------------|----------------------------|
    | OSM via Overpass             |                        397 |
    | JRC-corroborated expectation | severely incomplete (~1 %) |
    | Overture                     |                     54,978 |

    The old path also stopped working: ``overpass-api.de`` is serving an expired
    certificate and the kumi.systems mirror closes the connection, while the
    documented cache fallback lives under gitignored ``outputs/geoai/work/`` and
    so does not exist on a clean clone.

    Uses ``overturemaps`` directly rather than ``geoai.download_overture_buildings``
    so acquisition stays independent of the optional ``geoai`` extra, matching
    the rationale on :func:`_pc_client`.

    Returns the same ``{id, lon, lat, tags}`` centroid shape as
    :func:`fetch_osm_buildings`, so downstream Component D code is unchanged.
    """

    try:
        import overturemaps
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RealDataError(
            "Component D needs the 'overturemaps' package. Install the "
            "realpipeline extra: uv sync --project services/geoai-runner "
            "--extra realpipeline"
        ) from exc

    try:
        gdf = overturemaps.geodataframe("building", bbox=tuple(bbox))
    except Exception as exc:
        if cache_path and Path(cache_path).exists():
            cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            if cached:
                return cached
        raise RealDataError(f"Overture building fetch failed for {bbox}: {exc}") from exc

    if gdf is None or len(gdf) == 0:
        raise RealDataError(f"Overture returned no buildings for {bbox}.")

    def _clean(value: object) -> str:
        """Overture leaves `class` null for most footprints; pandas renders that
        as the float nan, which would otherwise reach the output as "nan"."""

        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() in {"nan", "none", "<na>"} else text

    centroids = gdf.geometry.representative_point()
    out = [
        {
            "id": str(row_id),
            "lon": float(point.x),
            "lat": float(point.y),
            "tags": {"source": "overture", "class": _clean(cls)},
        }
        for row_id, point, cls in zip(
            gdf.get("id", range(len(gdf))),
            centroids,
            gdf.get("class", [None] * len(gdf)),
            strict=False,
        )
    ]
    if out and cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(out), encoding="utf-8")
    return out


def fetch_buildings(
    bbox=MAE_SAI_BBOX,
    cache_path: str | Path | None = None,
) -> tuple[list[dict], str]:
    """Component D's building source, Overture first with OSM as a fallback.

    Returns ``(buildings, source_name)``. The source is returned rather than
    assumed so it can be recorded in the run metrics -- a published building
    count means nothing without knowing which source produced it.
    """

    try:
        return fetch_overture_buildings(bbox, cache_path=cache_path), "overture"
    except RealDataError as overture_error:
        try:
            return fetch_osm_buildings(bbox, cache_path=cache_path), "openstreetmap_overpass"
        except RealDataError as osm_error:
            raise RealDataError(
                f"Both building sources failed. Overture: {overture_error}; "
                f"OSM/Overpass: {osm_error}"
            ) from overture_error


def rasterize_lines(features: dict, transform, shape) -> np.ndarray:
    """Rasterize a GeoJSON line layer (e.g. DWR rivers) onto a grid."""

    from rasterio.features import rasterize

    geoms = [(f["geometry"], 1) for f in features.get("features", []) if f.get("geometry")]
    if not geoms:
        return np.zeros(shape, dtype="uint8")
    return rasterize(
        geoms, out_shape=shape, transform=transform, fill=0, all_touched=True, dtype="uint8"
    )


def terrain_features(dem: np.ndarray, river_mask: np.ndarray, pixel_m: float) -> dict:
    """Derive real HAND, slope, distance-to-river and TWI from a real DEM.

    HAND (Height Above Nearest Drainage) uses a nearest-drainage lookup against
    the real river network rather than full flow routing -- a standard, defensible
    approximation at this scale.
    """

    from scipy import ndimage

    if river_mask.sum() == 0:  # fall back to lowest-percentile cells as drainage
        river_mask = (dem <= np.percentile(dem, 2)).astype("uint8")
    dist_px, (iy, ix) = ndimage.distance_transform_edt(river_mask == 0, return_indices=True)
    distance_m = (dist_px * pixel_m).astype("float32")
    hand = np.clip(dem - dem[iy, ix], 0, None).astype("float32")
    gy, gx = np.gradient(dem, pixel_m)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2))).astype("float32")
    upslope = (distance_m.max() - distance_m) + pixel_m
    twi = np.log(upslope / (np.tan(np.radians(slope)) + 0.02)).astype("float32")
    return {"hand": hand, "slope": slope, "distance_to_river": distance_m, "twi": twi}


# --------------------------------------------------------------------------- #
# Thai authoritative vector layers (NGIS / GISTDA ArcGIS)
# --------------------------------------------------------------------------- #
def fetch_arcgis_featurelayer(
    layer_url: str,
    bbox=MAE_SAI_BBOX,
    *,
    where: str = "1=1",
    out_fields: str = "*",
    max_records: int = 2000,
) -> dict:
    """Query an ArcGIS FeatureServer layer for features intersecting bbox.

    Returns a GeoJSON FeatureCollection (WGS84). Handles the envelope spatial
    filter so Thai field names are not needed.
    """

    env = {
        "xmin": bbox[0],
        "ymin": bbox[1],
        "xmax": bbox[2],
        "ymax": bbox[3],
        "spatialReference": {"wkid": 4326},
    }
    params = {
        "where": where,
        "geometry": json.dumps(env),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "outSR": 4326,
        "returnGeometry": "true",
        "resultRecordCount": max_records,
        "f": "geojson",
    }
    url = layer_url.rstrip("/") + "/query?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FloodGuard"})
    try:
        raw = urllib.request.urlopen(req, timeout=60, context=_SSL).read()
    except Exception as exc:
        raise RealDataError(f"ArcGIS query failed for {layer_url}: {exc}") from exc
    gj = json.loads(raw.decode("utf-8"))
    if gj.get("type") != "FeatureCollection":
        raise RealDataError(f"Unexpected ArcGIS response for {layer_url}: {list(gj)[:5]}")
    return gj


NGIS = "https://ngis.go.th/arcgis/rest/services/Hosted"

# NGIS publishes these two services under percent-encoded Thai names. Naming the
# segments keeps the URLs readable and records what each one actually is; the
# encoded bytes are unchanged.
_SVC_SUBDISTRICTS = (  # ขอบเขตตำบล_DOPA -- DOPA sub-district (tambon) boundaries
    "%E0%B8%82%E0%B8%AD%E0%B8%9A%E0%B9%80%E0%B8%82%E0%B8%95"
    "%E0%B8%95%E0%B8%B3%E0%B8%9A%E0%B8%A5_DOPA"
)
_SVC_HIGHWAYS = (  # ทางหลวงแผ่นดิน -- national highway centrelines
    "%E0%B8%97%E0%B8%B2%E0%B8%87%E0%B8%AB%E0%B8%A5%E0%B8%A7%E0%B8%87"
    "%E0%B9%81%E0%B8%9C%E0%B9%88%E0%B8%99%E0%B8%94%E0%B8%B4%E0%B8%99"
)

LAYERS = {
    "subdistricts": f"{NGIS}/{_SVC_SUBDISTRICTS}/FeatureServer/0",
    "rivers": f"{NGIS}/NAT_STREAM_DWR/FeatureServer/0",
    "highways": f"{NGIS}/{_SVC_HIGHWAYS}/FeatureServer/0",
}


# Mae Sai district (code 5709) tambons -> standard romanised names. The DOPA
# layer only populates Thai names, so we attach the official romanisation
# (matching the FloodGuard dashboard's real ADM3 table).
MAE_SAI_TAMBON_NAMES = {
    "570901": "Mae Sai",
    "570902": "Huai Khrai",
    "570903": "Ko Chang",
    "570904": "Pong Pha",
    "570905": "Si Mueang Chum",
    "570906": "Wiang Phang Kham",
    "570908": "Ban Dai",
    "570909": "Pong Ngam",
}


def fetch_mae_sai_subdistricts(bbox=MAE_SAI_BBOX) -> dict:
    """Fetch DOPA sub-districts, filtered to Mae Sai district (code 5709)."""

    gj = fetch_arcgis_featurelayer(LAYERS["subdistricts"], bbox)
    feats = []
    for f in gj.get("features", []):
        p = f["properties"]
        tid = str(p.get("tambon_id") or "").strip()
        if not tid.startswith("5709"):  # keep only Mae Sai district
            continue
        p["subdistrict_id"] = tid
        p["subdistrict_name_th"] = str(p.get("tambon_t") or "").strip()
        p["subdistrict_name"] = (
            MAE_SAI_TAMBON_NAMES.get(tid) or str(p.get("tambon_e") or tid).strip()
        )
        feats.append(f)
    if not feats:
        raise RealDataError("No Mae Sai (5709) sub-districts returned by DOPA layer.")
    return {"type": "FeatureCollection", "features": feats}
