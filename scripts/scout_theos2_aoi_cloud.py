"""Measure AOI-clipped Sentinel-2 cloud fraction for the THEOS-2 request windows.

GISTDA's THEOS-2 ordering portal asks for an AOI, a date range, and a maximum
cloud cover percentage. This script narrows those date ranges with evidence
instead of a generic dry-season guess.

For every AOI in `resources/aoi/floodguard_theos2_aoi_v1.geojson` and every
candidate window, it queries the Microsoft Planetary Computer STAC API for
Sentinel-2 L2A scenes, reads the Scene Classification (SCL) band **windowed to
the AOI**, and reports the fraction of the AOI obscured by cloud, cirrus, or
cloud shadow.

Scene-level `eo:cloud_cover` is deliberately not used as the answer: a 110 km
Sentinel-2 tile can be 70 percent cloudy while a 10 km AOI inside it is clear.
It is recorded alongside for comparison.

This is an acquisition-planning aid only. Sentinel-2 is used purely as a cloud
climatology proxy for THEOS-2 tasking. It produces no flood mask, no validation
label, no reference mask, and no FloodGuard decision input. No imagery is
retained; only small windowed reads are performed and only summary rows are
written.

Usage:
    python scripts/scout_theos2_aoi_cloud.py
    python scripts/scout_theos2_aoi_cloud.py --aoi AOI-01 --aoi AOI-03
    python scripts/scout_theos2_aoi_cloud.py --workers 8 --output outputs/scout.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds as window_from_bounds

REPO_ROOT = Path(__file__).resolve().parents[1]
AOI_PATH = REPO_ROOT / "resources" / "aoi" / "floodguard_theos2_aoi_v1.geojson"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "theos2_aoi_cloud_scout.csv"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

# Sentinel-2 Scene Classification values treated as obscured.
SCL_OBSCURED = (3, 8, 9, 10)  # cloud shadow, cloud medium, cloud high, thin cirrus
SCL_NODATA = 0

# Cap each windowed read so an overview level is used instead of full resolution.
MAX_READ_PIXELS = 160

# Pad event windows so a near-miss just outside the proposed range is visible.
EVENT_WINDOW_PAD_DAYS = 14

OUTPUT_COLUMNS = [
    "aoi_id",
    "aoi_slug",
    "priority",
    "event_id",
    "window_id",
    "window_label",
    "window_start",
    "window_end",
    "requested_max_cloud_pct",
    "in_requested_window",
    "date",
    "aoi_cloud_pct",
    "aoi_valid_coverage_pct",
    "scene_cloud_pct",
    "n_scenes",
]


@dataclass(frozen=True)
class Target:
    aoi_id: str
    aoi_slug: str
    priority: str
    event_id: str
    bbox: tuple[float, float, float, float]
    window_id: str
    window_label: str
    window_start: str
    window_end: str
    requested_max_cloud_pct: int

    @property
    def is_event_window(self) -> bool:
        return "event" in self.window_id.lower()

    def search_range(self) -> tuple[str, str]:
        """Search range, padded for event windows to expose near misses."""
        if not self.is_event_window:
            return self.window_start, self.window_end
        pad = timedelta(days=EVENT_WINDOW_PAD_DAYS)
        start = date.fromisoformat(self.window_start) - pad
        end = date.fromisoformat(self.window_end) + pad
        return start.isoformat(), end.isoformat()


def load_targets(aoi_filter: set[str] | None) -> list[Target]:
    doc = json.loads(AOI_PATH.read_text(encoding="utf-8"))
    targets: list[Target] = []
    for feature in doc["features"]:
        props = feature["properties"]
        if aoi_filter and props["aoi_id"] not in aoi_filter:
            continue
        bbox = tuple(props["bbox_wgs84"])  # type: ignore[assignment]
        for window in props["requested_windows"]:
            targets.append(
                Target(
                    aoi_id=props["aoi_id"],
                    aoi_slug=props["slug"],
                    priority=props["priority"],
                    event_id=props["event_id"],
                    bbox=bbox,
                    window_id=window["window_id"],
                    window_label=window["label"],
                    window_start=window["start"],
                    window_end=window["end"],
                    requested_max_cloud_pct=window["max_cloud_pct"],
                )
            )
    return targets


def read_scl_counts(
    href: str, bbox: tuple[float, float, float, float]
) -> tuple[int, int, int] | None:
    """Return (obscured, valid, total) SCL pixel counts inside the AOI."""
    try:
        with rasterio.open(href) as src:
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src.crs, *bbox, densify_pts=21
            )
            window = window_from_bounds(left, bottom, right, top, transform=src.transform)
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            if window.width < 1 or window.height < 1:
                return None
            out_h = max(1, min(MAX_READ_PIXELS, int(window.height)))
            out_w = max(1, min(MAX_READ_PIXELS, int(window.width)))
            data = src.read(1, window=window, out_shape=(out_h, out_w))
    except Exception:
        return None

    total = int(data.size)
    valid = int(np.count_nonzero(data != SCL_NODATA))
    obscured = int(np.count_nonzero(np.isin(data, SCL_OBSCURED)))
    return obscured, valid, total


def scout(target: Target, client) -> list[dict[str, object]]:
    start, end = target.search_range()
    search = client.search(
        collections=[COLLECTION],
        bbox=list(target.bbox),
        datetime=f"{start}/{end}",
    )
    items = list(search.items())
    if not items:
        return []

    # Group by acquisition date; an AOI can straddle two MGRS tiles.
    by_date: dict[str, list] = {}
    for item in items:
        by_date.setdefault(item.datetime.date().isoformat(), []).append(item)

    rows: list[dict[str, object]] = []
    for day, day_items in sorted(by_date.items()):
        obscured = valid = total = 0
        scene_clouds: list[float] = []
        for item in day_items:
            asset = item.assets.get("SCL")
            if asset is None:
                continue
            counts = read_scl_counts(asset.href, target.bbox)
            if counts is None:
                continue
            o, v, t = counts
            obscured += o
            valid += v
            total += t
            cloud = item.properties.get("eo:cloud_cover")
            if cloud is not None:
                scene_clouds.append(float(cloud))

        if valid == 0 or total == 0:
            continue

        in_window = target.window_start <= day <= target.window_end
        rows.append(
            {
                "aoi_id": target.aoi_id,
                "aoi_slug": target.aoi_slug,
                "priority": target.priority,
                "event_id": target.event_id,
                "window_id": target.window_id,
                "window_label": target.window_label,
                "window_start": target.window_start,
                "window_end": target.window_end,
                "requested_max_cloud_pct": target.requested_max_cloud_pct,
                "in_requested_window": in_window,
                "date": day,
                "aoi_cloud_pct": round(100.0 * obscured / valid, 1),
                "aoi_valid_coverage_pct": round(100.0 * valid / total, 1),
                "scene_cloud_pct": (
                    round(sum(scene_clouds) / len(scene_clouds), 1) if scene_clouds else ""
                ),
                "n_scenes": len(day_items),
            }
        )
    return rows


def summarise(rows: Iterable[dict[str, object]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((str(row["aoi_id"]), str(row["window_id"])), []).append(row)

    for (aoi_id, window_id), group in sorted(grouped.items()):
        head = group[0]
        usable = [
            r
            for r in group
            if float(r["aoi_valid_coverage_pct"]) >= 60.0
        ]
        usable.sort(key=lambda r: float(r["aoi_cloud_pct"]))
        print()
        print(
            f"{aoi_id} {head['priority']} {head['aoi_slug']} | {window_id} "
            f"{head['window_label']} | requested {head['window_start']} -> "
            f"{head['window_end']} @ <={head['requested_max_cloud_pct']}%"
        )
        if not usable:
            print("    no Sentinel-2 date with >=60% AOI coverage")
            continue
        for row in usable[:6]:
            flag = "" if row["in_requested_window"] else "  [outside requested window]"
            print(
                f"    {row['date']}  AOI cloud {float(row['aoi_cloud_pct']):5.1f}%"
                f"  coverage {float(row['aoi_valid_coverage_pct']):5.1f}%"
                f"  scene {row['scene_cloud_pct']}%{flag}"
            )
        clear = [r for r in usable if float(r["aoi_cloud_pct"]) <= 10.0]
        print(f"    dates at <=10% AOI cloud: {len(clear)} of {len(usable)} observed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aoi",
        action="append",
        default=None,
        help="Limit to one or more AOI ids, e.g. --aoi AOI-01.",
    )
    parser.add_argument("--workers", type=int, default=12, help="Parallel COG readers.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        import planetary_computer
        from pystac_client import Client
    except ImportError:
        print(
            "pystac-client and planetary-computer are required:\n"
            "    pip install pystac-client planetary-computer rasterio",
            file=sys.stderr,
        )
        return 2

    targets = load_targets(set(args.aoi) if args.aoi else None)
    if not targets:
        print("No AOI/window targets matched.", file=sys.stderr)
        return 1

    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)

    print(f"Scouting {len(targets)} AOI/window combinations via {STAC_URL}")
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for target, result in zip(
            targets, pool.map(lambda t: scout(t, client), targets)
        ):
            print(f"  {target.aoi_id} {target.window_id}: {len(result)} dates")
            rows.extend(result)

    rows.sort(key=lambda r: (str(r["aoi_id"]), str(r["window_id"]), str(r["date"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    summarise(rows)
    print()
    print(f"Wrote {args.output} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
