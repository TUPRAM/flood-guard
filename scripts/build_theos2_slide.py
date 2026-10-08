"""One 16:9 slide of the THEOS-2 cross-check, drawn from the committed overview figure and result file.

The slide shows three panels of the overview (the THEOS-2 image, the water read from it, and one radar method
against it) and the three figures the team accepted for the pitch. Every figure is agreement between two sensors
at two times on one tile; none is accuracy, and the slide says so.

Example::

    python scripts/build_theos2_slide.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "outputs" / "theos2_cross_check" / "sukhothai_20250730_v1_overview.png"
RESULT = ROOT / "outputs" / "theos2_cross_check" / "sukhothai_20250730_v1.json"
SLIDE = ROOT / "docs" / "mentoring" / "visuals" / "theos2_check_slide.png"

PANELS = 5
PANEL_GAP = 6
CAPTION_BAR = 16
INK = (23, 35, 29)
MUTED = (68, 82, 74)
TEAL = (8, 127, 140)
CAUTION = (114, 81, 36)
PAPER = (248, 247, 241)


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def panel(overview: Image.Image, index: int) -> Image.Image:
    """Panel `index` of the overview, without its caption bar."""

    width = (overview.width - (PANELS - 1) * PANEL_GAP) // PANELS
    left = index * (width + PANEL_GAP)
    return overview.crop((left, CAPTION_BAR, left + width, overview.height))


def percent_range(values: list[float]) -> str:
    return f"{round(min(values) * 100)} to {round(max(values) * 100)}%"


def main() -> None:
    overview = Image.open(OVERVIEW).convert("RGB")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    slide = Image.new("RGB", (1600, 900), PAPER)
    draw = ImageDraw.Draw(slide)

    draw.text((60, 44), "A FIRST CHECK AGAINST THEOS-2  ·  SUKHOTHAI, 30 JULY 2025", font=font(19), fill=TEAL)
    draw.text((60, 76), "Radar is mostly right where it flags water, and misses most of it", font=font(40), fill=INK)

    captions = [
        (0, "THEOS-2 image, 0.5 m (GISTDA sample)"),
        (1, "Water read from the image (blue)"),
        (2, "Sentinel-1 radar 44 h later (one of three methods)"),
    ]
    width = 470
    for position, (index, caption) in enumerate(captions):
        tile = panel(overview, index)
        height = round(width * tile.height / tile.width)
        left = 60 + position * (width + 20)
        draw.text((left, 150), caption, font=font(19), fill=INK)
        slide.paste(tile.resize((width, height), Image.LANCZOS), (left, 182))
        draw.rectangle([left, 182, left + width - 1, 182 + height - 1], outline=(174, 190, 176))
    bottom = 182 + round(width * (overview.height - CAPTION_BAR) / ((overview.width - (PANELS - 1) * PANEL_GAP) // PANELS))

    legend = [((34, 160, 60), "both"), ((40, 130, 235), "image only"), ((255, 150, 20), "radar only"), ((200, 80, 200), "cloud or roof: not compared")]
    x = 60
    for colour, label in legend:
        draw.rectangle([x, bottom + 16, x + 18, bottom + 34], fill=colour)
        draw.text((x + 26, bottom + 13), label, font=font(18), fill=MUTED)
        x += 26 + int(draw.textlength(label, font=font(18))) + 34

    # All compared cells; a cell without an answer counts as not flagged (the stricter reading).
    cells = [method["all_compared_cells"]["strict_no_answer_counts_as_not_a_candidate"] for method in result["methods"].values()]
    precision = [float(item["precision"]) for item in cells]
    recall = [float(item["recall"]) for item in cells]
    central = result["road_check"]["modelled_against_seen"]["theos2_optical_wet_cells_10m"]["by_level"]["central"]
    closed_and_seen = central["closed_by_rule_and_seen_under_water"]["edges"]
    closed = closed_and_seen + central["closed_by_rule_not_seen_under_water"]["edges"]
    figures = [
        ("6 to 8 in 10", "cells the radar flags are water", "on the THEOS-2 image",
         f"three radar methods: {percent_range(precision)}"),
        ("a quarter to a half", "of the water on the image", "is flagged by the radar",
         f"three radar methods: {percent_range(recall)}"),
        ("4 in 5", "roads our closure rule closes are under", "water on the image, given a good extent",
         f"{closed_and_seen} of {closed} road pieces, central level, THEOS-2 extent"),
    ]
    top = bottom + 58
    for position, (number, first, second, exact) in enumerate(figures):
        left = 60 + position * (width + 20)
        draw.rectangle([left, top, left + width - 1, top + 150], fill=(255, 255, 255), outline=(174, 190, 176))
        draw.text((left + 20, top + 12), number, font=font(36), fill=INK)
        draw.text((left + 20, top + 62), first, font=font(19), fill=MUTED)
        draw.text((left + 20, top + 88), second, font=font(19), fill=MUTED)
        draw.text((left + 20, top + 120), exact, font=font(15), fill=TEAL)

    note = ("One tile of 9 square km, one event. Agreement between two sensors at two times, not accuracy. "
            "A check tile: no score and no class is computed for it. Not an official warning.")
    draw.text((60, 866), note, font=font(17), fill=CAUTION)

    SLIDE.parent.mkdir(parents=True, exist_ok=True)
    slide.save(SLIDE, optimize=True)
    print(f"wrote {SLIDE.relative_to(ROOT).as_posix()}: {slide.size}, {percent_range(precision)}, {percent_range(recall)}, {closed_and_seen} of {closed}")


if __name__ == "__main__":
    main()
