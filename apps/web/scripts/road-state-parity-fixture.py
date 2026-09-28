"""Write the hourly road-state parity fixture for the Mae Sai replay's TypeScript tests.

For every hour of the replay grid (9 Sep 00:00 to 19 Sep 23:00 ICT) this samples the assumed stage from the
served manifest's ``stage_anchors`` (``numpy.interp``, the same knots the page interpolates) and classifies every
modelled road piece with the Python rule, ``floodguard.flood_timeline.road_state``. The web tests then check that
the browser's ``roadState`` gives the same wet and impassable kilometres at those exact stages.

Run from the repository root (read-only on the data; it writes only the fixture):

    python apps/web/scripts/road-state-parity-fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.flood_timeline import road_state  # noqa: E402

WEB = ROOT / "apps" / "web"
MANIFEST_URL_PATTERN = 'TIMELINE_MANIFEST_URL = "'
FIXTURE = WEB / "src" / "lib" / "__fixtures__" / "mae-sai-road-state-hourly.json"
HOURS = 11 * 24


def manifest_href() -> str:
    """The one manifest URL the page serves, read from ``flood-timeline.ts``."""
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    start = source.index(MANIFEST_URL_PATTERN) + len(MANIFEST_URL_PATTERN)
    return source[start:source.index('"', start)]


def main() -> None:
    href = manifest_href()
    manifest = json.loads((WEB / "public" / href.lstrip("/")).read_text(encoding="utf-8"))
    roads = json.loads((WEB / "public" / manifest["vectors"]["roads"]["href"].lstrip("/")).read_text(encoding="utf-8"))["features"]
    knots_t = [anchor["t"] for anchor in manifest["stage_anchors"]]
    knots_s = [anchor["stage_m"] for anchor in manifest["stage_anchors"]]
    rows = []
    for hour in range(HOURS):
        stage = float(np.interp(hour / 24, knots_t, knots_s))
        lengths = {"wet": 0.0, "impassable": 0.0}
        for feature in roads:
            props = feature["properties"]
            if not props["m"] or props["h"] is None:
                continue
            state = road_state(props["h"], stage, props.get("k", 1.0))
            if state in lengths:
                lengths[state] += props["len"]
        rows.append([hour, stage, round(lengths["wet"] / 1000, 2), round(lengths["impassable"] / 1000, 2)])
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({
        "generated_by": "apps/web/scripts/road-state-parity-fixture.py (floodguard.flood_timeline.road_state)",
        "manifest": href,
        "roads_sha256": manifest["vectors"]["roads"]["sha256"],
        "columns": ["hour", "stage_m", "road_km_wet", "road_km_impassable"],
    }, indent=1)
    body = ",\n".join(f"  {json.dumps(row)}" for row in rows)
    FIXTURE.write_text(f'{header[:-2]},\n "hours": [\n{body}\n ]\n}}\n', encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)} ({len(rows)} hours)")


if __name__ == "__main__":
    main()
