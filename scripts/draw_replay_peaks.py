"""Draw the modelled peak of two revisions of the Mae Sai replay side by side, and print their peak figures.

Reads only committed files: the two revision folders under ``apps/web/public/studies/mae-sai-2024-timeline/``. Writes
``docs/replay_river_fit_peaks.jpg`` (the peak of the archived revision, the peak of the live one, and where they
differ) and prints the table ``docs/replay_river_fit.md`` shows. A modelled peak is a scenario reconstruction with low
confidence, not an observation of a flood and not an official warning.

    python scripts/draw_replay_peaks.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "apps" / "web" / "public" / "studies" / "mae-sai-2024-timeline"
OUT = ROOT / "docs" / "replay_river_fit_peaks.jpg"
ARCHIVED, LIVE = "r4", "r5"
LAND, WATER, GAINED, LOST, LINE = (238, 236, 228), (52, 120, 190), (224, 132, 38), (128, 72, 160), (60, 60, 60)
SCALE = 0.5
"""The picture is drawn at half the size of the model grid."""


def revision(name: str) -> tuple[dict, np.ndarray]:
    """The manifest of a revision and its cells that are wet at the modelled peak."""

    manifest = json.loads((STUDY / name / "timeline.json").read_text(encoding="utf-8"))
    hand = manifest["hand"]
    codes = np.array(Image.open(STUDY / name / Path(hand["href"]).name))[..., 0]
    peak = max(anchor["stage_m"] for anchor in manifest["stage_anchors"])
    # The page's rule: a cell is wet when its effective height above the channel is below the stage.
    wet = (codes != hand["never_code"]) & (codes * hand["step_m"] < peak)
    return manifest, wet


def peak_day(manifest: dict) -> dict:
    return max(manifest["days"], key=lambda day: day["stage_m"])["stats"]


def outlines(draw: ImageDraw.ImageDraw, manifest: dict, size: tuple[int, int]) -> None:
    """The subdistrict outlines, placed by the bounds of the model grid."""

    (south, west), (north, east) = manifest["bounds"]
    collection = json.loads((STUDY / manifest["revision"] / "tambons.geojson").read_text(encoding="utf-8"))
    for feature in collection["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                points = [((lon - west) / (east - west) * size[0], (north - lat) / (north - south) * size[1]) for lon, lat in ring]
                draw.line(points, fill=LINE, width=1)


def panel(colours: np.ndarray) -> Image.Image:
    image = Image.fromarray(colours)
    return image.resize((round(image.width * SCALE), round(image.height * SCALE)), Image.Resampling.BILINEAR)


def main() -> None:
    old_manifest, old = revision(ARCHIVED)
    new_manifest, new = revision(LIVE)
    if old.shape != new.shape or old_manifest["bounds"] != new_manifest["bounds"]:
        raise SystemExit("The two revisions are not on the same grid.")

    def coloured(mask: np.ndarray) -> np.ndarray:
        picture = np.empty((*mask.shape, 3), dtype=np.uint8)
        picture[:] = LAND
        picture[mask] = WATER
        return picture

    change = coloured(old & new)
    change[new & ~old] = GAINED
    change[old & ~new] = LOST
    panels = [panel(coloured(old)), panel(coloured(new)), panel(change)]
    width, height = panels[0].size
    gap, head = 12, 46
    sheet = Image.new("RGB", (3 * width + 2 * gap, height + head), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 17)
    except OSError:
        font = ImageFont.load_default()
    titles = [
        f"Revision {ARCHIVED} (archive): modelled peak",
        f"Revision {LIVE}: peak fitted to the 15 Sep 2024 image",
        f"Orange: wet only in {LIVE}. Purple: wet only in {ARCHIVED}.",
    ]
    for index, (picture, title) in enumerate(zip(panels, titles)):
        left = index * (width + gap)
        sheet.paste(picture, (left, head))
        draw.text((left + 4, 4), title, fill=(20, 20, 20), font=font)
        draw.text((left + 4, 24), "Scenario reconstruction, low confidence. Not observed.", fill=(90, 90, 90), font=font)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        outlines(ImageDraw.Draw(overlay), new_manifest, (width, height))
        sheet.paste(overlay, (left, head), overlay)
    sheet.save(OUT, quality=88)

    # The cell of the served raster, from its bounds (the manifest's `pixel_area_m2` is the cell of the histograms).
    (south, west), (north, east) = old_manifest["bounds"]
    rows, columns = old.shape
    cell_km2 = ((north - south) * 110.7 / rows) * ((east - west) * 111.32 * np.cos(np.radians((north + south) / 2)) / columns)
    print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({OUT.stat().st_size:,} bytes)")
    print(f"about: wet in both {(old & new).sum() * cell_km2:.0f} km2; only in {LIVE} {(new & ~old).sum() * cell_km2:.0f} km2; "
          f"only in {ARCHIVED} {(old & ~new).sum() * cell_km2:.0f} km2 (the whole model grid, both banks of the border)")
    before, after = peak_day(old_manifest), peak_day(new_manifest)
    names = {feature["properties"]["id"]: feature["properties"]["en"]
             for feature in json.loads((STUDY / LIVE / "tambons.geojson").read_text(encoding="utf-8"))["features"]}
    print(f"\n| At the modelled peak | {ARCHIVED} | {LIVE} |\n|---|---|---|")
    print(f"| Flooded area in the district | {before['flooded_km2']:.1f} km² | {after['flooded_km2']:.1f} km² |")
    print(f"| Residents in water | {before['people_in_water']:,} | {after['people_in_water']:,} |")
    print(f"| Road impassable | {before['road_km_impassable']:.1f} km | {after['road_km_impassable']:.1f} km |")
    print(f"| Residents whose homes flood (shelter demand) | {old_manifest['shelters']['demand_people']:,} | {new_manifest['shelters']['demand_people']:,} |")
    print(f"\n| Subdistrict | Flooded km², {ARCHIVED} | Flooded km², {LIVE} | Residents in water, {ARCHIVED} | Residents in water, {LIVE} |\n|---|---|---|---|---|")
    for code in sorted(names, key=lambda key: -after["tambon_flooded_km2"][key]):
        print(f"| {names[code]} | {before['tambon_flooded_km2'][code]:.1f} | {after['tambon_flooded_km2'][code]:.1f} | "
              f"{round(before['tambon_people_in_water'][code]):,} | {round(after['tambon_people_in_water'][code]):,} |")


if __name__ == "__main__":
    main()
