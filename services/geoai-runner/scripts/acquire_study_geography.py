"""Acquire public-domain cartographic context for the Studio event map.

This explicit network script adds no model features or labels. Tests and the web
application consume only its saved, checksummed projection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

SOURCE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
LICENCE = "https://www.naturalearthdata.com/about/terms-of-use/"


def in_ring(point: list[float], ring: list[list[float]]) -> bool:
    """Ray-cast a point in a non-antimeridian-crossing longitude/latitude ring."""
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        ax, ay = previous
        bx, by = current
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
        previous = current
    return inside


def contains(point: list[float], polygons: list) -> bool:
    """Respect polygon holes when assigning a display-only country label."""
    return any(
        in_ring(point, rings[0]) and not any(in_ring(point, ring) for ring in rings[1:])
        for rings in polygons
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Cartographic projection already exists; acquire a new revision instead of overwriting it")
    with urlopen(SOURCE, timeout=60) as response:  # noqa: S310
        original = response.read()
    geo = json.loads(original)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    features = []
    countries = {}
    for feature in geo["features"]:
        geometry = feature["geometry"]
        polygons = (
            geometry["coordinates"]
            if geometry["type"] == "MultiPolygon"
            else [geometry["coordinates"]]
        )
        name = feature["properties"]["NAME_EN"]
        paths = []
        for rings in polygons:
            for ring in rings:
                paths.append(
                    "M"
                    + "L".join(
                        f"{(lon + 180) * 2 + 30:.2f},{(90 - lat) * 2 + 20:.2f}" for lon, lat in ring
                    )
                    + "Z"
                )
        features.append({"name": name, "path": "".join(paths)})
        for event in summary["events"]:
            if contains(event["centroid_lon_lat"], polygons):
                countries[event["event_id"]] = name
    now = datetime.now(UTC).isoformat()
    result = {
        "schema_version": "floodguard.study-geography.v1",
        "study_id": "c2s-ms-20260915",
        "revision": "r1",
        "data_mode": "public_cartographic_context",
        "source_timestamp": now,
        "verified_utc": now,
        "license": "Public domain",
        "license_url": LICENCE,
        "source_url": SOURCE,
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "source_bytes": len(original),
        "can_feed_decision_layer": False,
        "aggregation_status": "report_only",
        "operational_status": "non_operational",
        "official_warning": False,
        "confidence": "cartographic_display_only_not_model_evidence",
        "assumptions": [
            "Natural Earth 1:110m outlines are display context only; not model inputs or flood evidence.",
            "Source timestamp is acquisition of the cartographic file, not imagery observation time.",
            "Country labels are inferred from the centre of each recorded event bounding box; "
            "they do not describe every chip or replace publisher metadata.",
            "Small islands and border detail may be omitted at this map scale. Unmatched centres remain unlabelled.",
            "SVG coordinates use the same equirectangular longitude/latitude transform as the Studio plot, "
            "rounded to 0.01 display units.",
        ],
        "features": features,
        "event_countries": countries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "features": len(features),
                "labelled_events": len(countries),
                "bytes": args.output.stat().st_size,
                "source_sha256": result["source_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
