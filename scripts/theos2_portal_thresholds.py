"""Translate AOI-clipped cloud limits into GISTDA portal scene-level filter values.

`scripts/scout_theos2_aoi_cloud.py` measures cloud **clipped to the AOI polygon**,
which is what actually determines whether an acquisition is usable. The GISTDA
ordering portal at https://awagad.gistda.or.th/v2/p filters on **scene-level**
cloud cover, which is computed over a whole satellite footprint far larger than
these AOIs.

The two diverge in both directions. Entering an AOI-level limit into a
scene-level filter silently discards usable acquisitions. This script reads the
scout results plus the revised windows in `resources/aoi/*.geojson`, and for each
window reports the minimum scene-level threshold that still returns every date we
want.

Writes `outputs/theos2_portal_cloud_thresholds.csv`.

Usage:
    python scripts/theos2_portal_thresholds.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AOI_PATH = REPO_ROOT / "resources" / "aoi" / "floodguard_theos2_aoi_v1.geojson"
SCOUT_PATH = REPO_ROOT / "outputs" / "theos2_aoi_cloud_scout.csv"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "theos2_portal_cloud_thresholds.csv"

# Portal fields are typically whole numbers; round up to a safe step.
THRESHOLD_STEP = 5

OUTPUT_COLUMNS = [
    "event_id",
    "window_id",
    "window_label",
    "window_start",
    "window_end",
    "aoi_ids",
    "aoi_cloud_limit_pct",
    "portal_scene_cloud_filter_pct",
    "adjustment",
    "wanted_dates",
    "n_wanted_dates",
    "max_scene_cloud_pct",
    "dates_lost_if_aoi_limit_used",
    "n_dates_lost",
]


def round_up(value: float, step: int = THRESHOLD_STEP) -> int:
    whole, remainder = divmod(value, step)
    return int(step * (whole + (1 if remainder else 0)))


def load_windows() -> tuple[dict, dict]:
    """Return (windows_by_event, aoi_ids_by_event) from the AOI GeoJSON."""
    doc = json.loads(AOI_PATH.read_text(encoding="utf-8"))
    windows: dict[str, list[dict]] = {}
    aoi_ids: dict[str, list[str]] = defaultdict(list)
    for feature in doc["features"]:
        props = feature["properties"]
        event = props["event_id"]
        windows.setdefault(event, props["requested_windows"])
        aoi_ids[event].append(props["aoi_id"])
    return windows, dict(aoi_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if not SCOUT_PATH.exists():
        print(f"missing {SCOUT_PATH}; run scripts/scout_theos2_aoi_cloud.py first")
        return 1

    scout_rows = list(csv.DictReader(SCOUT_PATH.open(encoding="utf-8")))
    windows_by_event, aoi_ids_by_event = load_windows()

    out_rows: list[dict[str, object]] = []
    for event, windows in windows_by_event.items():
        aoi_ids = aoi_ids_by_event[event]
        for window in windows:
            start, end = window["start"], window["end"]
            cap = float(window["max_cloud_pct"])

            wanted = [
                row
                for row in scout_rows
                if row["aoi_id"] in aoi_ids
                and start <= row["date"] <= end
                and float(row["aoi_cloud_pct"]) <= cap
                and row["scene_cloud_pct"] not in ("", None)
            ]
            if not wanted:
                out_rows.append(
                    {
                        "event_id": event,
                        "window_id": window["window_id"],
                        "window_label": window["label"],
                        "window_start": start,
                        "window_end": end,
                        "aoi_ids": " ".join(aoi_ids),
                        "aoi_cloud_limit_pct": int(cap),
                        "portal_scene_cloud_filter_pct": int(cap),
                        "adjustment": "no_usable_date_measured",
                        "wanted_dates": "",
                        "n_wanted_dates": 0,
                        "max_scene_cloud_pct": "",
                        "dates_lost_if_aoi_limit_used": "",
                        "n_dates_lost": 0,
                    }
                )
                continue

            max_scene = max(float(r["scene_cloud_pct"]) for r in wanted)
            portal = max(round_up(max_scene), int(cap))
            lost = sorted(
                {
                    r["date"]
                    for r in wanted
                    if float(r["scene_cloud_pct"]) > cap
                }
            )
            if portal > cap:
                adjustment = f"raise_from_{int(cap)}_to_{portal}"
            else:
                adjustment = "unchanged"

            out_rows.append(
                {
                    "event_id": event,
                    "window_id": window["window_id"],
                    "window_label": window["label"],
                    "window_start": start,
                    "window_end": end,
                    "aoi_ids": " ".join(aoi_ids),
                    "aoi_cloud_limit_pct": int(cap),
                    "portal_scene_cloud_filter_pct": portal,
                    "adjustment": adjustment,
                    "wanted_dates": " ".join(sorted({r["date"] for r in wanted})),
                    "n_wanted_dates": len({r["date"] for r in wanted}),
                    "max_scene_cloud_pct": round(max_scene, 1),
                    "dates_lost_if_aoi_limit_used": " ".join(lost),
                    "n_dates_lost": len(lost),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"{'window':<34} {'AOI cap':>8} {'portal':>7} {'lost if naive':>14}")
    print("-" * 68)
    for row in out_rows:
        print(
            f"{str(row['event_id'])[:16]:<17}{str(row['window_id']):<17}"
            f"{row['aoi_cloud_limit_pct']:>7}% {row['portal_scene_cloud_filter_pct']:>6}%"
            f" {row['n_dates_lost']:>13}"
        )

    total_lost = sum(int(r["n_dates_lost"]) for r in out_rows)
    safe_single = max(int(r["portal_scene_cloud_filter_pct"]) for r in out_rows)
    print()
    print(f"Dates that a naive scene-level filter would discard: {total_lost}")
    print(f"Single portal value safe for every window: {safe_single}%")
    print(f"Wrote {args.output} ({len(out_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
