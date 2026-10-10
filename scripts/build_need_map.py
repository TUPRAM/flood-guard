"""Draw the need map of case SE1: 500 m squares by the need type most residents fall in, and the mix of each tambon.

One picture for the pitch. The left panel is the district on squares of 500 m, coloured by the need type most
residents of the square fall in, paler where few residents are, with a diagonal stroke where that type changes
with the flood level or the closure level. The right panel is the same counts as a bar for each tambon.

Every figure comes from ``outputs/need_mix/`` (bound by SHA-256). The picture is planning guidance: a scenario of
the 2024 season layer, modelled residents and modelled closures, not an official warning, and a need type is not
a planning class.

Example::

    python scripts/build_need_map.py --external-data <external data root>
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import flood_inputs  # noqa: E402
from floodguard import need_mix as nm  # noqa: E402

MIX = "outputs/need_mix/se1_mae_sai_v1.json"
SQUARES = "outputs/need_mix/se1_mae_sai_squares_500m_v1.json"
PICTURE = "outputs/need_mix/se1_mae_sai_need_map_v1.png"
RECORD = "outputs/need_mix/se1_mae_sai_need_map_v1.json"
WIDTH, HEIGHT = 2400, 1500
SURFACE, INK, INK_SECONDARY, MUTED, HAIRLINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
COLOURS = {nm.IN_THE_WATER: "#2a78d6", nm.DRY_CUT_OFF: "#eb6834", nm.DRY_LOSES_HOSPITAL: "#1baf7a",
           nm.NOT_AFFECTED: "#b9b8b0", nm.NOT_ASSESSED: "#dcdad1"}
"""The three kinds of need take the first three slots of the default categorical palette, in order (checked for colour
vision deficiency with the palette validator of the visualization guide); the two kinds without a need are neutral."""
LEGEND = {nm.IN_THE_WATER: "In the water", nm.DRY_CUT_OFF: "Dry, every road cut", nm.DRY_LOSES_HOSPITAL: "Dry, hospital out of reach",
          nm.NOT_AFFECTED: "Not affected in the scenario", nm.NOT_ASSESSED: "Access not assessed"}
CLASS_WORDS = {"A": "protect lives now", "B": "keep routes open", "C": "protect essential services", "D": "build resilience", "E": "monitor and verify"}


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rgb(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def blend(colour: str, share: float) -> tuple[int, int, int]:
    """The colour laid over the surface at ``share`` (0 the surface, 1 the colour)."""

    return tuple(round(back + (front - back) * share) for front, back in zip(rgb(colour), rgb(SURFACE)))  # type: ignore[return-value]


def ink_on(colour: tuple[int, int, int]) -> str:
    red, green, blue = (value / 255 for value in colour)
    return INK if 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.47 else "#ffffff"


def font(size: int, bold: bool = False) -> Any:
    from PIL import ImageFont

    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-data", type=Path, required=True)
    arguments = parser.parse_args()

    import numpy as np
    from PIL import Image, ImageDraw

    mix = json.loads((ROOT / MIX).read_text(encoding="utf-8"))
    squares_file = json.loads((ROOT / SQUARES).read_text(encoding="utf-8"))
    if squares_file["made_from"]["need_mix"]["sha256"] != hashlib.sha256((ROOT / MIX).read_bytes()).hexdigest():
        raise RuntimeError("the squares were not made from this need mix")
    squares = [item for item in squares_file["squares"] if item["residents"] >= 1.0]
    side = float(squares_file["grid"]["side_m"])

    bad = load_script("build_access_diff")
    rules = flood_inputs.load_rules(bad.DOCS / "planning_protocol_v1a.json", bad.DOCS / "planning_protocol_v1b.json", bad.DOCS / "RECEIPTS.jsonl")
    units, _summary = bad.read_units(arguments.external_data / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    outlines = {unit_id: flood_inputs.project(geometry, flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS) for unit_id, geometry in units}

    image = Image.new("RGB", (WIDTH, HEIGHT), SURFACE)
    draw = ImageDraw.Draw(image)
    margin, top, bottom = 60, 150, 150
    map_width = 1380
    west = min(geometry.bounds[0] for geometry in outlines.values())
    south = min(geometry.bounds[1] for geometry in outlines.values())
    east = max(geometry.bounds[2] for geometry in outlines.values())
    north = max(geometry.bounds[3] for geometry in outlines.values())
    scale = min(map_width / (east - west), (HEIGHT - top - bottom) / (north - south))
    left = margin + (map_width - (east - west) * scale) / 2

    def place(x: float, y: float) -> tuple[float, float]:
        return left + (x - west) * scale, top + (north - y) * scale

    # --- title ------------------------------------------------------------------------------------------------------
    draw.text((margin, 36), "Where each need sits: Mae Sai district, 2024 season scenario", font=font(44, True), fill=INK)
    draw.text((margin, 96), "Residents by what the scenario does to them, on 500 m squares. A need type is not a planning class.",
              font=font(26), fill=INK_SECONDARY)

    # --- the squares --------------------------------------------------------------------------------------------------
    reference = float(np.percentile([item["residents"] for item in squares], 95))
    changing = 0
    for item in squares:
        x0, y0 = place(item["x_min"], item["y_min"] + side)
        x1, y1 = place(item["x_min"] + side, item["y_min"])
        strength = 0.28 + 0.72 * min(1.0, math.sqrt(item["residents"] / reference))
        fill = blend(COLOURS[item["leading_type"]], strength)
        draw.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=fill)  # a 2 px gap of surface between squares
        if not item["leading_type_is_the_same_in_all_nine_runs"]:
            changing += 1
            draw.line([x0 + 3, y1 - 3, x1 - 3, y0 + 3], fill=SURFACE, width=3)

    # --- the tambons: outline, name and binding class ------------------------------------------------------------------
    for unit_id, geometry in outlines.items():
        for part in getattr(geometry, "geoms", [geometry]):
            draw.line([place(x, y) for x, y in part.exterior.coords], fill=INK_SECONDARY, width=3)
    label_font = font(24, True)
    for unit_id, geometry in outlines.items():
        entry = mix["by_tambon"][unit_id]
        text = f"{entry['unit_name_en']} · {entry['binding_class_v1_of_the_published_file']}"
        point = geometry.representative_point()
        x, y = place(point.x, point.y)
        box = draw.textbbox((0, 0), text, font=label_font)
        width, height = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle([x - width / 2 - 8, y - height / 2 - 6, x + width / 2 + 8, y + height / 2 + 10], radius=6, fill=SURFACE)
        draw.text((x - width / 2, y - height / 2 - 4), text, font=label_font, fill=INK)

    # --- scale bar --------------------------------------------------------------------------------------------------
    bar_x, bar_y = margin + 10, HEIGHT - bottom + 24
    draw.line([bar_x, bar_y, bar_x + 5000 * scale, bar_y], fill=INK, width=4)
    draw.text((bar_x, bar_y + 10), "5 km · north is up · tambon name and its binding class", font=font(22), fill=INK_SECONDARY)

    # --- the bars: the same counts for each tambon -----------------------------------------------------------------------
    panel_x, panel_width = margin + map_width + 70, WIDTH - (margin + map_width + 70) - margin
    draw.text((panel_x, top - 6), "The mix of each tambon (share of residents)", font=font(28, True), fill=INK)
    def with_a_need(unit_id: str) -> float:
        by_type = mix["by_tambon"][unit_id]["worldpop_2020"]["in_the_published_run"]["by_type"]
        return sum(by_type[name]["share"] or 0.0 for name in (nm.IN_THE_WATER, nm.DRY_CUT_OFF, nm.DRY_LOSES_HOSPITAL))

    order = sorted(mix["by_tambon"], key=lambda unit_id: (-with_a_need(unit_id), unit_id))
    row_height, thickness = 104, 24
    for number, unit_id in enumerate(order):
        entry = mix["by_tambon"][unit_id]
        published = entry["worldpop_2020"]["in_the_published_run"]
        y = top + 58 + number * row_height
        letter = entry["binding_class_v1_of_the_published_file"]
        draw.text((panel_x, y), entry["unit_name_en"], font=font(25, True), fill=INK)
        name_width = draw.textbbox((0, 0), entry["unit_name_en"], font=font(25, True))[2]
        draw.text((panel_x + name_width + 14, y + 3), f"class {letter}, {CLASS_WORDS[letter]} · {published['residents']:,.0f} residents",
                  font=font(21), fill=INK_SECONDARY)
        x = float(panel_x)
        for name in nm.NEED_TYPES:
            share = published["by_type"][name]["share"] or 0.0
            width = share * panel_width
            if width < 1:
                continue
            colour = rgb(COLOURS[name])
            if width >= 10:
                draw.rounded_rectangle([x + 1, y + 40, x + width - 1, y + 40 + thickness], radius=4, fill=colour)
            else:  # too thin for rounded ends; a sliver still shows that the kind is there
                draw.rectangle([x + 1, y + 40, max(x + 2, x + width - 1), y + 40 + thickness], fill=colour)
            text = f"{round(100 * share)}%"
            box = draw.textbbox((0, 0), text, font=font(19, True))
            if name in (nm.IN_THE_WATER, nm.DRY_CUT_OFF, nm.DRY_LOSES_HOSPITAL) and box[2] - box[0] + 12 <= width:
                draw.text((x + 7, y + 40), text, font=font(19, True), fill=ink_on(colour))
            x += width

    # --- legend -------------------------------------------------------------------------------------------------------
    legend_y = top + 58 + len(order) * row_height + 16
    for number, name in enumerate(nm.NEED_TYPES):
        x = panel_x + (number % 2) * (panel_width / 2)
        y = legend_y + (number // 2) * 44
        draw.rounded_rectangle([x, y + 4, x + 30, y + 30], radius=4, fill=rgb(COLOURS[name]))
        draw.text((x + 42, y + 2), LEGEND[name], font=font(23), fill=INK)
    note_y = legend_y + 3 * 44 + 6
    draw.rectangle([panel_x, note_y + 4, panel_x + 30, note_y + 30], fill=blend(COLOURS[nm.IN_THE_WATER], 0.9))
    draw.line([panel_x + 3, note_y + 27, panel_x + 27, note_y + 7], fill=SURFACE, width=3)
    draw.text((panel_x + 42, note_y + 2), "Stroke: the kind changes with the flood level or closure level", font=font(21), fill=INK_SECONDARY)
    draw.text((panel_x + 42, note_y + 36), "Paler square: fewer residents", font=font(21), fill=INK_SECONDARY)

    # --- footer -------------------------------------------------------------------------------------------------------
    footer = ["Planning guidance, not an official warning. A scenario: every area mapped as flooded between 1 August and 12 October 2024, taken at once. "
              "Road closures and residents are modelled; nothing was checked on the ground.",
              "Flood layer: UNOSAT and GISTDA, FL20240912THA, product 4009 (CC BY-SA 4.0), changed by FloodGuard. Residents: WorldPop 2020 (CC BY 4.0). "
              "Roads © OpenStreetMap contributors (ODbL). Squares say nothing about a household."]
    for number, line in enumerate(footer):
        draw.text((margin, HEIGHT - 78 + number * 32), line, font=font(20), fill=MUTED)

    (ROOT / PICTURE).parent.mkdir(parents=True, exist_ok=True)
    image.save(ROOT / PICTURE, optimize=True)
    record = {
        "schema": "floodguard.need_map_record.v1",
        "source_timestamp": mix["source_timestamp"], "confidence_class": mix["confidence_class"],
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "The record of the need map of case SE1: what the picture was drawn from.",
        "picture": {"path": PICTURE, "sha256": hashlib.sha256((ROOT / PICTURE).read_bytes()).hexdigest(), "pixels": [WIDTH, HEIGHT]},
        "made_from": {"need_mix": {"path": MIX, "sha256": hashlib.sha256((ROOT / MIX).read_bytes()).hexdigest()},
                      "squares": {"path": SQUARES, "sha256": hashlib.sha256((ROOT / SQUARES).read_bytes()).hexdigest()}},
        "drawn": {"squares_with_a_resident": len(squares), "squares_whose_leading_type_changes_over_the_nine_runs": changing,
                  "strength_of_colour": "from 28% for the fewest residents to 100% at the 95th percentile of residents per square, by the square root",
                  "colours": COLOURS, "order_of_the_bars": "largest share of residents with one of the three needs first"},
        "assumptions": mix["assumptions"], "limits": mix["limits"],
    }
    (ROOT / RECORD).write_bytes((json.dumps(record, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(record["drawn"]["squares_with_a_resident"], changing)


if __name__ == "__main__":
    main()
