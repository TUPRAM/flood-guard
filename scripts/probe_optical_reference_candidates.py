"""Probe open optical imagery that a Reference Authority could qualify as an independent flood reference.

Research tier only. The probe reads the Sentinel-2 L2A scene-classification (SCL)
band over a small window and lists Sentinel-1 GRD acquisitions with a Sentinel-2
scene nearby in time. It never labels water, selects a reference, signs a
decision, or feeds the decision layer. Every output carries
``official_warning=false`` and ``evidence_tier=research_hypothesis``.

Subcommands:

``aoi``   SCL observability of each Sentinel-2 L2A scene over one AOI polygon.
``scan``  Sentinel-1/Sentinel-2 near-coincidences over candidate Thai flood
          episodes, with the SCL clear fraction inside each episode box.

Network sources: Element84 Earth Search (Sentinel-2 L2A COGs, anonymous) and
Microsoft Planetary Computer (Sentinel-1 GRD metadata, anonymous signing).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
PLANETARY_COMPUTER_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

SCL_CLASSES: dict[int, str] = {
    0: "no_data",
    1: "saturated_or_defective",
    2: "dark_area_or_topographic_shadow",
    3: "cloud_shadow",
    4: "vegetation",
    5: "not_vegetated",
    6: "water",
    7: "unclassified",
    8: "cloud_medium_probability",
    9: "cloud_high_probability",
    10: "thin_cirrus",
    11: "snow_or_ice",
}
SCL_UNOBSERVABLE = (0, 3, 8, 9, 10)

ASSUMPTIONS = [
    "SCL is the ESA Sen2Cor scene classification; its cloud and shadow classes are used only as an observability screen.",
    "SCL 'water' is not a flood label: turbid floodwater is often classed as not_vegetated or unclassified.",
    "A clear-sky fraction says a scene could be interpreted, not that it shows the flood peak or that a reference exists.",
    "Episode boxes are small illustrative windows around flooded towns, not declared study areas.",
    "Temporal proximity to a Sentinel-1 pass does not by itself establish independence or date fitness; a Reference Authority must decide both.",
]


@dataclass(frozen=True)
class Episode:
    """A candidate Thai flood episode window to scan."""

    episode_id: str
    name: str
    bbox: tuple[float, float, float, float]
    window: str


DEFAULT_EPISODES: tuple[Episode, ...] = (
    Episode("mae_sai_2024", "Mae Sai, Chiang Rai (Sai River)", (99.838, 20.370, 99.944, 20.456), "2024-09-08/2024-09-22"),
    Episode("chiang_mai_2024", "Chiang Mai city (Ping River)", (98.960, 18.740, 99.030, 18.820), "2024-09-25/2024-10-12"),
    Episode("nan_2024", "Nan city (Nan River)", (100.740, 18.750, 100.800, 18.820), "2024-08-18/2024-09-01"),
    Episode("sukhothai_2024", "Sukhothai (Yom River)", (99.780, 16.980, 99.880, 17.060), "2024-08-22/2024-09-20"),
    Episode("narathiwat_2024", "Sungai Kolok / Tak Bai, Narathiwat", (101.900, 6.000, 102.100, 6.300), "2024-11-25/2024-12-12"),
    Episode("hat_yai_2025", "Hat Yai, Songkhla (U-Taphao canal)", (100.420, 6.960, 100.520, 7.050), "2025-11-20/2025-12-06"),
    Episode("ayutthaya_2022", "Phra Nakhon Si Ayutthaya (Chao Phraya)", (100.500, 14.300, 100.620, 14.400), "2022-10-01/2022-10-25"),
    Episode("chaiyaphum_2021", "Chaiyaphum city (Storm Dianmu)", (101.990, 15.770, 102.080, 15.850), "2021-09-24/2021-10-10"),
    Episode("ubon_2019", "Warin Chamrap / Ubon Ratchathani (Mun River)", (104.800, 15.180, 104.920, 15.280), "2019-09-01/2019-09-22"),
)


def summarize_scl(values: np.ndarray) -> dict[str, Any]:
    """Summarize SCL pixel values into class fractions and an observability split.

    Args:
        values: One-dimensional array of SCL codes for pixels inside the area.

    Returns:
        Pixel count, per-class fractions (only classes present), the unobservable
        fraction (no data, cloud shadow, medium/high cloud, cirrus) and the
        remaining clear-observable fraction, each rounded to four decimals.
    """

    flat = np.asarray(values).ravel()
    n = int(flat.size)
    if n == 0:
        raise ValueError("no SCL pixels inside the area")
    fractions = {
        SCL_CLASSES.get(int(code), f"code_{int(code)}"): round(int(count) / n, 4)
        for code, count in zip(*np.unique(flat, return_counts=True))
    }
    unobservable = float(np.isin(flat, SCL_UNOBSERVABLE).sum()) / n
    return {
        "pixels": n,
        "scl_fractions": fractions,
        "unobservable_fraction": round(unobservable, 4),
        "clear_observable_fraction": round(1.0 - unobservable, 4),
    }


def match_coincident(
    sar: Sequence[tuple[str, datetime]],
    optical: Sequence[tuple[str, datetime]],
    max_hours: float,
) -> list[dict[str, Any]]:
    """Pair SAR and optical acquisitions whose time difference is within ``max_hours``.

    Args:
        sar: ``(item_id, acquisition_time)`` for each SAR acquisition.
        optical: ``(item_id, acquisition_time)`` for each optical acquisition.
        max_hours: Inclusive absolute time tolerance in hours.

    Returns:
        One record per pair, sorted by absolute gap, with ``hours_optical_minus_sar``
        signed so that negative means the optical scene came first.
    """

    if max_hours < 0:
        raise ValueError("max_hours must be non-negative")
    pairs = []
    for sar_id, sar_time in sar:
        for opt_id, opt_time in optical:
            gap = (opt_time - sar_time).total_seconds() / 3600.0
            if abs(gap) <= max_hours:
                pairs.append(
                    {
                        "sar_item": sar_id,
                        "sar_utc": sar_time.isoformat(),
                        "optical_item": opt_id,
                        "optical_utc": opt_time.isoformat(),
                        "hours_optical_minus_sar": round(gap, 1),
                    }
                )
    return sorted(pairs, key=lambda p: (abs(p["hours_optical_minus_sar"]), p["sar_item"], p["optical_item"]))


def _envelope(extra: dict[str, Any], sources: Iterable[str]) -> dict[str, Any]:
    return {
        "evidence_tier": "research_hypothesis",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "grants_reference_authority": False,
        "confidence": "research probe; observability screen only, not a flood label or reference decision",
        "processed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sorted(set(sources)),
        "assumptions": ASSUMPTIONS,
        **extra,
    }


def _scl_inside(href: str, geometry_wgs84: Any) -> np.ndarray:
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from shapely.geometry import mapping
    from shapely.ops import transform

    with rasterio.open(href) as ds:
        projected = transform(Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform, geometry_wgs84)
        window = from_bounds(*projected.bounds, transform=ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=window, boundless=True, fill_value=0)
        inside = geometry_mask(
            [mapping(projected)], out_shape=arr.shape, transform=ds.window_transform(window), invert=True
        )
    return arr[inside]


def _s2_items(geometry_wgs84: Any, window: str) -> list[Any]:
    import pystac_client
    from shapely.geometry import mapping

    client = pystac_client.Client.open(EARTH_SEARCH_URL)
    items = client.search(collections=["sentinel-2-l2a"], intersects=mapping(geometry_wgs84), datetime=window)
    return sorted(items.item_collection(), key=lambda item: item.datetime)


def _s1_items(geometry_wgs84: Any, window: str) -> list[Any]:
    import planetary_computer
    import pystac_client
    from shapely.geometry import mapping

    client = pystac_client.Client.open(PLANETARY_COMPUTER_URL, modifier=planetary_computer.sign_inplace)
    items = client.search(collections=["sentinel-1-grd"], intersects=mapping(geometry_wgs84), datetime=window)
    return sorted(items.item_collection(), key=lambda item: item.datetime)


def probe_aoi(aoi_path: Path, window: str) -> dict[str, Any]:
    """Measure SCL observability over an AOI polygon for every Sentinel-2 L2A scene in ``window``."""

    from shapely.geometry import shape
    from shapely.ops import unary_union

    raw = aoi_path.read_bytes()
    geojson = json.loads(raw.decode("utf-8"))
    features = geojson["features"] if geojson.get("type") == "FeatureCollection" else [geojson]
    aoi = unary_union([shape(feature["geometry"]) for feature in features])
    scenes = []
    for item in _s2_items(aoi, window):
        summary = summarize_scl(_scl_inside(item.assets["scl"].href, aoi))
        scenes.append(
            {
                "item": item.id,
                "sensing_utc": item.datetime.isoformat(),
                "tile_cloud_cover_percent": item.properties.get("eo:cloud_cover"),
                "s2_product_id": item.properties.get("s2:product_uri"),
                **summary,
            }
        )
    return _envelope(
        {
            "probe": "sentinel2_scl_aoi_observability",
            "aoi_file": aoi_path.as_posix(),
            "aoi_file_sha256": hashlib.sha256(raw).hexdigest(),
            "aoi_bounds_wgs84": [round(b, 5) for b in aoi.bounds],
            "window": window,
            "source_timestamp": window,
            "scenes": scenes,
        },
        [EARTH_SEARCH_URL],
    )


def scan_episodes(episodes: Sequence[Episode], max_hours: float) -> dict[str, Any]:
    """List Sentinel-1/Sentinel-2 near-coincidences and box clear fractions for each episode."""

    from shapely.geometry import box

    records = []
    for episode in episodes:
        area = box(*episode.bbox)
        s1 = _s1_items(area, episode.window)
        s2 = _s2_items(area, episode.window)
        clear: dict[str, float | None] = {}
        for item in s2:
            try:
                clear[item.id] = summarize_scl(_scl_inside(item.assets["scl"].href, area))["clear_observable_fraction"]
            except Exception:  # noqa: BLE001 - a failed read is recorded, never guessed
                clear[item.id] = None
        pairs = match_coincident(
            [(item.id, item.datetime) for item in s1], [(item.id, item.datetime) for item in s2], max_hours
        )
        s1_meta = {item.id: item for item in s1}
        for pair in pairs:
            sar = s1_meta[pair["sar_item"]]
            pair["sar_orbit_state"] = sar.properties.get("sat:orbit_state")
            pair["sar_relative_orbit"] = sar.properties.get("sat:relative_orbit")
            pair["optical_box_clear_fraction"] = clear.get(pair["optical_item"])
        records.append(
            {
                "episode_id": episode.episode_id,
                "name": episode.name,
                "bbox_wgs84": list(episode.bbox),
                "window": episode.window,
                "n_sentinel1_grd": len(s1),
                "n_sentinel2_l2a": len(s2),
                "sentinel2_box_clear_fraction": clear,
                "pairs": pairs,
            }
        )
    return _envelope(
        {
            "probe": "thai_sentinel1_sentinel2_coincidence_scan",
            "max_hours": max_hours,
            "source_timestamp": [episode.window for episode in episodes],
            "episodes": records,
        },
        [EARTH_SEARCH_URL, PLANETARY_COMPUTER_URL],
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the requested probe and write its JSON output."""

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    aoi = sub.add_parser("aoi", help="SCL observability over one AOI polygon")
    aoi.add_argument("--aoi", type=Path, required=True)
    aoi.add_argument("--window", default="2024-09-01/2024-09-25")
    aoi.add_argument("--output", type=Path, required=True)
    scan = sub.add_parser("scan", help="Sentinel-1/Sentinel-2 coincidences over Thai episodes")
    scan.add_argument("--max-hours", type=float, default=48.0)
    scan.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    result = probe_aoi(args.aoi, args.window) if args.command == "aoi" else scan_episodes(DEFAULT_EPISODES, args.max_hours)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
