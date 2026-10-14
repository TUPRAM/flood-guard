"""One 16:9 slide of the Nan case for the pitch: the class of each tambon beside the three figures of the test.

Left, a small map of the frame's tambons coloured by their N1 class, drawn from the frame's unit raster (the 20 m
grid of ``outputs/nan_case/frame_v1.json``, file ``frame/n1_units_20m.tif`` in the work folder) and the N1 result
file: a binding class is solid, a would-be class (low confidence, class in effect E) is striped. Right, three figures
of the test record ``outputs/nan_case/test_result_v1.json``: test 1 (IoU with its reference named), the dry control
share and the town figures of test 2, and one sentence of what they mean. A footer names the sources and says that
every figure is agreement with another map, not accuracy.

No JAXA, GFM or THEOS-2 map is drawn or opened: the Sentinel Asia terms allow no modification of the materials, and
only figures computed by the test stage are shown. The slide reads the result file, the test record, the frame
record and the unit raster, and nothing behind the firewall of the case. The PNG carries its source times,
confidence and assumptions as text chunks. Planning guidance only; not an official warning.

Example (from the repository root, after the chain has written the N1 result)::

    python scripts/build_nan_case_slide.py --external-root <external data root>
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load_script(name: str) -> Any:
    """Load a script of the repository as a module, once (the brief's readers and checks are used unchanged)."""

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


brief = _load_script("build_n1_brief")

FRAME_RECORD = "outputs/nan_case/frame_v1.json"
SLIDE = "docs/mentoring/visuals/nan_case_slide.png"
EXTERNAL_PLACEHOLDER = "<external_data_workspace>"
SIZE = (1600, 900)
MAP_BOX = (60, 172, 680, 492)
"""Left, top, largest width and largest height of the map on the slide."""
RIGHT_X, RIGHT_W = 780, 760
INK = (23, 35, 29)
MUTED = (68, 82, 74)
TEAL = (8, 127, 140)
CAUTION = (114, 81, 36)
PAPER = (248, 247, 241)
LINE = (174, 190, 176)
BORDER = (44, 56, 50)
NO_CLASS_RGB = (196, 198, 192)
NO_UNIT, SEVERAL_UNITS = 0, 255
LABEL_MIN_PIXELS = 120
STRIPE_PX = 3
EXIT_DONE, EXIT_REFUSED = 0, 2


class SlideError(brief.N1BriefError):
    """An input of the slide is refused; nothing has been drawn."""


def rgb(colour: str) -> tuple[int, int, int]:
    """``#RRGGBB`` as a tuple."""

    value = colour.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


CLASS_RGB: dict[str, tuple[int, int, int]] = {letter: rgb(colour) for letter, colour in brief.CLASS_COLOURS.items()}
"""The class colours of the site's map, as on the brief."""


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# The frame and the map
# ---------------------------------------------------------------------------


def unit_lookup(frame: Mapping[str, Any]) -> dict[int, str]:
    """Raster value to unit identifier, from the frame record's units.

    Raises:
        SlideError: for a raster value that is used twice, or one of the reserved codes 0 and 255.
    """

    lookup: dict[int, str] = {}
    for unit in frame.get("units") or []:
        value = int(unit["raster_value"])
        if value in (NO_UNIT, SEVERAL_UNITS) or value in lookup:
            raise SlideError(f"raster value {value} of the frame record is reserved or used twice")
        lookup[value] = str(unit["adm3_pcode"])
    if not lookup:
        raise SlideError("the frame record names no unit")
    return lookup


def unit_raster_path(frame: Mapping[str, Any], external_root: Path) -> Path:
    """The unit raster the frame record names, in the external data root."""

    stated = str((frame.get("unit_raster") or {}).get("path") or "")
    if not stated.startswith(EXTERNAL_PLACEHOLDER + "/"):
        raise SlideError("the frame record does not name its unit raster in the work folder")
    return Path(external_root).joinpath(*stated[len(EXTERNAL_PLACEHOLDER) + 1:].split("/"))


def read_unit_raster(path: Path, frame: Mapping[str, Any]) -> np.ndarray:
    """The unit raster, checked against the frame record: its SHA-256, its grid and its coordinate system.

    Raises:
        SlideError: for a path behind the firewall, other bytes, another grid or another coordinate system.
    """

    brief.refuse_behind_the_firewall([path])
    record = frame.get("unit_raster") or {}
    if record.get("sha256") and sha256_file(path) != record["sha256"]:
        raise SlideError(f"{Path(path).name} is not the unit raster the frame record names (its SHA-256 differs)")
    import rasterio

    grid = record.get("grid") or {}
    with rasterio.open(path) as source:
        if source.crs is None or source.crs.to_epsg() != int(grid.get("epsg", 32647)):
            raise SlideError(f"{Path(path).name}: the unit raster is in EPSG:{grid.get('epsg', 32647)}")
        if grid and ((source.height, source.width) != (int(grid["rows"]), int(grid["cols"])) or
                     any(abs(a - b) > 1e-6 for a, b in zip((source.transform.c, source.transform.f, source.transform.a, -source.transform.e),
                                                           (float(grid["west"]), float(grid["north"]), float(grid["cell_m"]), float(grid["cell_m"]))))):
            raise SlideError(f"{Path(path).name}: the unit raster is not on the frame's grid")
        return source.read(1)


def classes_of(overlay: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Each unit's class on the map: the class shown, and whether it is binding, would-be or none."""

    return {row["unit_id"]: row for row in brief.n1_rows(overlay)}


def _erode(mask: np.ndarray) -> np.ndarray:
    inner = mask.copy()
    inner[1:, :] &= mask[:-1, :]
    inner[:-1, :] &= mask[1:, :]
    inner[:, 1:] &= mask[:, :-1]
    inner[:, :-1] &= mask[:, 1:]
    inner[0, :] = inner[-1, :] = False
    inner[:, 0] = inner[:, -1] = False
    return inner


def label_point(mask: np.ndarray) -> tuple[int, int] | None:
    """A point well inside a unit: the pixel nearest the centre of what is left after eroding it as far as it goes."""

    rows, cols = np.nonzero(mask)
    if rows.size < LABEL_MIN_PIXELS:
        return None
    top, left = rows.min(), cols.min()
    part = mask[top:rows.max() + 1, left:cols.max() + 1]
    part = np.pad(part, 1)
    last = part
    while True:
        inner = _erode(last)
        if not inner.any():
            break
        last = inner
    ys, xs = np.nonzero(last)
    cy, cx = ys.mean(), xs.mean()
    nearest = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
    return int(xs[nearest]) + left - 1, int(ys[nearest]) + top - 1


def render_map(values: np.ndarray, lookup: Mapping[int, str], classes: Mapping[str, Mapping[str, Any]], *,
               max_size: tuple[int, int] = (MAP_BOX[2], MAP_BOX[3]), cell_m: float = 20.0) -> tuple[Image.Image, dict[str, Any]]:
    """The tambons coloured by class: solid for a binding class, striped for a would-be class, grey for none.

    Raises:
        SlideError: when the raster holds no unit, or a unit of the raster has no row in the result.
    """

    valid = np.isin(values, list(lookup))
    if not valid.any():
        raise SlideError("the unit raster holds no unit of the frame record")
    missing = sorted(lookup[value] for value in np.unique(values[valid]).tolist() if lookup[int(value)] not in classes)
    if missing:
        raise SlideError(f"the result file holds no row for {', '.join(missing[:5])}")
    rows, cols = np.nonzero(valid)
    top, bottom, left, right = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    crop = np.where(valid[top:bottom, left:right], values[top:bottom, left:right], 0).astype(np.uint8)
    scale = min(max_size[0] / crop.shape[1], max_size[1] / crop.shape[0])
    width, height = max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))
    small = np.asarray(Image.fromarray(crop, mode="L").resize((width, height), Image.NEAREST))
    picture = np.empty((height, width, 3), dtype=np.uint8)
    picture[:] = PAPER
    yy, xx = np.mgrid[0:height, 0:width]
    stripes = ((xx + yy) // STRIPE_PX) % 2 == 0
    drawn: dict[str, str] = {}
    for value, unit_id in lookup.items():
        mask = small == value
        if not mask.any():
            continue
        row = classes[unit_id]
        if row["kind"] == brief.NO_CLASS or row["shown"] is None:
            picture[mask] = NO_CLASS_RGB
        elif row["kind"] == brief.WOULD_BE:
            colour = np.array(CLASS_RGB[row["shown"]], dtype=float)
            tint = (colour * 0.35 + 255 * 0.65).astype(np.uint8)
            picture[mask & stripes] = CLASS_RGB[row["shown"]]
            picture[mask & ~stripes] = tint
        else:
            picture[mask] = CLASS_RGB[row["shown"]]
        drawn[unit_id] = row["kind"]
    edge = np.zeros(small.shape, dtype=bool)
    edge[:, :-1] |= small[:, :-1] != small[:, 1:]
    edge[:-1, :] |= small[:-1, :] != small[1:, :]
    picture[edge] = BORDER
    image = Image.fromarray(picture, mode="RGB")
    draw = ImageDraw.Draw(image)
    labelled = 0
    for value, unit_id in lookup.items():
        row = classes[unit_id]
        letter = row["shown"]
        point = None if letter is None else label_point(small == value)
        if point is None:
            continue   # a tambon with no class is grey and carries no letter; a tiny one is left unlabelled
        dark = row["kind"] == brief.BINDING and letter in ("A", "B")
        draw.text(point, letter, font=font(15), fill=(255, 255, 255) if dark else INK, anchor="mm",
                  stroke_width=2, stroke_fill=INK if dark else (255, 255, 255))
        labelled += 1
    metres_per_pixel = cell_m * crop.shape[1] / width
    return image, {"metres_per_pixel": metres_per_pixel, "units_drawn": drawn, "units_labelled": labelled,
                   "crop_cells": [int(crop.shape[0]), int(crop.shape[1])]}


# ---------------------------------------------------------------------------
# The words of the slide
# ---------------------------------------------------------------------------


def reference_kind(outcome: Mapping[str, Any]) -> str:
    return "a same-pass map (not independent)" if outcome["fallback"] else "another satellite's map"


def headline_of(outcome: Mapping[str, Any]) -> str:
    if not outcome["test_1_run"]:
        return "Our own radar map could not be tested against another map"
    if outcome["passed"]:
        return "Our own radar map met the bar we fixed before the test"
    return "Our own radar map fell short of the bar we fixed before the test"


def meaning_of(outcome: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    """One sentence of what the three figures mean for the classes."""

    tail = "so no class binds: every tambon is E (low confidence), its would-be class shown striped."
    if not outcome["test_1_run"]:
        return "Test 1 could not be run, " + tail
    if not outcome["test_1_passes"]:
        return (f"Our map reached IoU {brief.figure_text(outcome['iou'])} against {reference_kind(outcome)}, under the bar of "
                f"{brief.NAN_TEST_IOU_MIN:.2f} fixed before the test, " + tail)
    if not outcome["dry_control_passes"]:
        return (f"Our map flagged {brief.share_text(outcome['dry_share'])} of dry hills, over the bar of "
                f"{brief.DRY_CONTROL_MAX_SHARE:.0%} fixed before the test, " + tail)
    binding = sum(1 for row in rows if row["kind"] == brief.BINDING and row["confidence"] == "medium")
    town = outcome["town"] or {}
    found = f"; in town it flagged {brief.share_text(town.get('water_found'))} of the water THEOS-2 shows" if town else ""
    return (f"Our map met the bar fixed before the test against {reference_kind(outcome)} and flagged "
            f"{brief.share_text(outcome['dry_share'])} of dry hills, so a class binds wherever a tambon's own radar answer is "
            f"good enough: {binding} of {len(rows)} tambons here{found}.")


def _date_of(text: Any) -> str:
    when = brief.parse_utc(text)
    return "n/a" if when is None else f"{when.day} {when:%B %Y}"


def cards_of(outcome: Mapping[str, Any]) -> list[dict[str, str]]:
    """The three figure cards: test 1, the dry control and the town figures of test 2."""

    verdict = {True: "PASSES", False: "DOES NOT PASS"}
    if outcome["test_1_run"]:
        interval = outcome["interval"]
        span = "" if not interval else f"  ·  95% interval {brief.figure_text(interval[0])} to {brief.figure_text(interval[1])}"
        first = {"tag": f"TEST 1  ·  {verdict[outcome['test_1_passes']]}", "big": brief.figure_text(outcome["iou"]),
                 "line_1": f"IoU with {outcome['reference']}",
                 "line_2": ("the same Sentinel-1 pass (Copernicus GFM): not independent of our map" if outcome["fallback"]
                            else "another satellite (ALOS-2, L-band radar), over the frame's land"),
                 "small": (f"bar fixed before the test: at least {brief.NAN_TEST_IOU_MIN:.2f}  ·  no answer on "
                           f"{brief.share_text(outcome['no_answer_share'])} of compared cells{span}")}
    else:
        first = {"tag": "TEST 1  ·  NOT RUN", "big": "n/a", "line_1": "Test 1 could not be run",
                 "line_2": str(outcome["test_1_not_run"] or "no reference could be read"), "small": "no class of the case binds"}
    answered = outcome["dry_answered_cells"]
    second = {"tag": f"DRY CONTROL  ·  {verdict[outcome['dry_control_passes']]}", "big": brief.share_text(outcome["dry_share"]),
              "line_1": "of the answered cells flagged on dry hills with no flood",
              "line_2": f"a THEOS-2 chip of 31 July 2025, radar pass of {_date_of(outcome['dry_pass'])}",
              "small": (f"bar fixed before the test: at most {brief.DRY_CONTROL_MAX_SHARE:.0%}"
                        + ("" if answered is None else f"  ·  {int(answered):,} answered cells"))}
    town = outcome["town"]
    if town:
        hours = town.get("hours_after_theos2")
        points = town.get("points_with_a_label")
        third = {"tag": "TEST 2  ·  REPORTED, NOT BINDING", "big": brief.share_text(town.get("water_found")),
                 "line_1": "of the water THEOS-2 shows in Wiang Sa town is flagged by our map",
                 "line_2": ((f"radar {float(hours):.0f} h after THEOS-2 (0.5 m)  ·  " if hours is not None else "")
                            + f"{brief.share_text(town.get('flags_on_water'))} of our flags are THEOS-2 water"),
                 "small": (f"IoU {brief.figure_text(town.get('iou'))}"
                           + ("" if points is None else f"  ·  {brief.share_text(town.get('points_share'))} of {int(points)} "
                              "labelled points agree with our map"))}
    else:
        third = {"tag": "TEST 2  ·  REPORTED, NOT BINDING", "big": "n/a", "line_1": "the test record holds no town figures",
                 "line_2": "", "small": ""}
    return [first, second, third]


def footer_of(outcome: Mapping[str, Any], result_name: str) -> tuple[str, str]:
    """The sources line and the caution line."""

    reference = ("Copernicus EMS Global Flood Monitoring (GFM)" if outcome["fallback"]
                 else "JAXA ALOS-2 Flood Proxy Map, Provided by JAXA (Sentinel Asia)")
    sources = (f"Sources: Copernicus Sentinel-1 (2025, Microsoft Planetary Computer RTC), processed by FloodGuard (M1-z, frozen "
               f"before the test). Figures only, no map drawn: {reference}; THEOS-2 of 31 July 2025 (GISTDA sample). Tambons: "
               f"HDX COD-AB. Classes: {result_name}.")
    caution = "Agreement with another map, not accuracy. One event, one frame. Planning guidance, not an official warning."
    return sources, caution


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def wrap(draw: ImageDraw.ImageDraw, text: str, size: int, width: int) -> list[str]:
    """Words of ``text`` in lines no wider than ``width`` pixels at ``size``."""

    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font(size)) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def fit(draw: ImageDraw.ImageDraw, text: str, size: int, width: int, smallest: int = 12) -> int:
    """The largest size down from ``size`` at which ``text`` fits on one line of ``width`` pixels."""

    while size > smallest and draw.textlength(text, font=font(size)) > width:
        size -= 1
    return size


def swatch(slide: Image.Image, box: tuple[int, int, int, int], colour: tuple[int, int, int], *, striped: bool = False) -> None:
    """A legend sample, striped as the map stripes a would-be class."""

    left, top, right, bottom = box
    sample = np.empty((bottom - top, right - left, 3), dtype=np.uint8)
    sample[:] = colour
    if striped:
        yy, xx = np.mgrid[0:bottom - top, 0:right - left]
        gaps = ((xx + yy) // STRIPE_PX) % 2 == 1
        sample[gaps] = tuple(int(value * 0.35 + 255 * 0.65) for value in colour)
    slide.paste(Image.fromarray(sample, mode="RGB"), (left, top))
    ImageDraw.Draw(slide).rectangle([left, top, right - 1, bottom - 1], outline=BORDER)


def draw_legend(slide: Image.Image, draw: ImageDraw.ImageDraw, top: int, rows: Sequence[Mapping[str, Any]]) -> int:
    """The legend under the map; returns the y below it."""

    from floodguard import planning_brief

    x, y = MAP_BOX[0], top
    for letter, (name, _thai) in planning_brief.CLASS_NAMES.items():
        label = f"{letter} {name}"
        width = 22 + int(draw.textlength(label, font=font(15))) + 18
        if x + width > MAP_BOX[0] + MAP_BOX[2]:
            x, y = MAP_BOX[0], y + 24
        swatch(slide, (x, y + 2, x + 16, y + 18), CLASS_RGB[letter])
        draw.text((x + 22, y + 1), label, font=font(15), fill=MUTED)
        x += width
    y += 26
    x = MAP_BOX[0]
    items = [(CLASS_RGB["B"], False, "solid: binding class"),
             (CLASS_RGB["B"], True, "striped: would-be class (in effect E, low confidence)")]
    if any(row["kind"] == brief.NO_CLASS for row in rows):
        items.append((NO_CLASS_RGB, False, "grey: no class"))
    for colour, striped, label in items:
        swatch(slide, (x, y + 2, x + 16, y + 18), colour, striped=striped)
        draw.text((x + 22, y + 1), label, font=font(15), fill=MUTED)
        x += 22 + int(draw.textlength(label, font=font(15))) + 22
    return y + 24


def draw_card(draw: ImageDraw.ImageDraw, top: int, card: Mapping[str, str], height: int = 150) -> None:
    left, width = RIGHT_X, RIGHT_W
    draw.rectangle([left, top, left + width - 1, top + height], fill=(255, 255, 255), outline=LINE)
    draw.text((left + 20, top + 12), card["tag"], font=font(15), fill=TEAL)
    draw.text((left + 20, top + 32), card["big"], font=font(40), fill=INK)
    text_left = left + 20 + max(150, int(draw.textlength(card["big"], font=font(40))) + 24)
    room = left + width - 20 - text_left
    for offset, key, size, colour in ((42, "line_1", 19, INK), (70, "line_2", 17, MUTED)):
        if card.get(key):
            draw.text((text_left, top + offset), card[key], font=font(fit(draw, card[key], size, room)), fill=colour)
    if card.get("small"):
        draw.text((left + 20, top + 112), card["small"], font=font(fit(draw, card["small"], 15, width - 40, 11)), fill=TEAL)


def draw_slide(map_image: Image.Image, map_info: Mapping[str, Any], outcome: Mapping[str, Any],
               rows: Sequence[Mapping[str, Any]], *, result_name: str, districts: Sequence[str], pass_text: str) -> Image.Image:
    """The whole slide."""

    slide = Image.new("RGB", SIZE, PAPER)
    draw = ImageDraw.Draw(slide)
    draw.text((60, 38), f"THE NAN CASE  ·  NAN RIVER FLOODS, JULY 2025  ·  CASE N1, {len(rows)} TAMBONS", font=font(19), fill=TEAL)
    headline = headline_of(outcome)
    draw.text((60, 68), headline, font=font(fit(draw, headline, 40, SIZE[0] - 120, 28)), fill=INK)

    where = f" ({', '.join(districts)})" if districts else ""
    title = f"Class of each tambon from our radar map{where}"
    draw.text((MAP_BOX[0], 140), title, font=font(fit(draw, title, 19, MAP_BOX[2], 14)), fill=INK)
    left = MAP_BOX[0] + (MAP_BOX[2] - map_image.width) // 2
    slide.paste(map_image, (left, MAP_BOX[1]))
    draw.rectangle([left - 1, MAP_BOX[1] - 1, left + map_image.width, MAP_BOX[1] + map_image.height], outline=LINE)
    # A scale bar of 10 km (5 km when that is too long for the map).
    metres = 10_000 if 10_000 / map_info["metres_per_pixel"] < map_image.width / 2 else 5_000
    bar = int(round(metres / map_info["metres_per_pixel"]))
    base_y = MAP_BOX[1] + map_image.height - 14
    draw.rectangle([left + 12, base_y - 4, left + 12 + bar, base_y], fill=INK)
    draw.text((left + 12 + bar + 8, base_y - 12), f"{metres // 1000} km  ·  north up", font=font(14), fill=INK,
              stroke_width=2, stroke_fill=(255, 255, 255))
    below = draw_legend(slide, draw, MAP_BOX[1] + map_image.height + 12, rows)
    caption = f"Radar pass {pass_text}. Drawn from the frame's tambon grid and the N1 result file."
    draw.text((MAP_BOX[0], below + 4), caption, font=font(fit(draw, caption, 15, MAP_BOX[2], 12)), fill=MUTED)

    top = 140
    for card in cards_of(outcome):
        draw_card(draw, top, card)
        top += 162
    meaning = meaning_of(outcome, rows)
    y = top + 4
    for line in wrap(draw, meaning, 22, RIGHT_W):
        draw.text((RIGHT_X, y), line, font=font(22), fill=INK)
        y += 29

    draw.line([(60, 812), (SIZE[0] - 60, 812)], fill=LINE, width=1)
    sources, caution = footer_of(outcome, result_name)
    y = 820
    for line in wrap(draw, sources, 14, SIZE[0] - 120)[:2]:
        draw.text((60, y), line, font=font(14), fill=MUTED)
        y += 18
    draw.text((60, 862), caution, font=font(17), fill=CAUTION)
    return slide


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def build(result_path: Path, test_path: Path, frame_path: Path, unit_raster: Path, out_path: Path, *,
          generated_at: str | None = None) -> dict[str, Any]:
    """Check the inputs against each other, draw the slide and write it as a PNG with its record as text chunks.

    Raises:
        SlideError: for a path behind the firewall, inputs that are not of one run or one frame, or a fixture result
            written over the slide of the repository.
    """

    brief.refuse_behind_the_firewall([result_path, test_path, frame_path, unit_raster, out_path])
    overlay, result_sha = brief.read_json(result_path)
    brief.check_result(overlay)
    test, test_sha = brief.read_json(test_path)
    outcome = brief.outcome_of_the_test(test)
    brief.check_together(overlay, outcome, None, test_sha256=test_sha)
    if (overlay.get("case") or {}).get("fixture_notice") and Path(out_path).resolve() == (ROOT / SLIDE).resolve():
        raise SlideError("a fixture result is never drawn over the slide of the repository")
    frame, frame_sha = brief.read_json(frame_path)
    lookup = unit_lookup(frame)
    classes = classes_of(overlay)
    if set(classes) != set(lookup.values()):
        raise SlideError("the result file and the frame record do not hold the same tambons")
    values = read_unit_raster(unit_raster, frame)
    cell_m = float(((frame.get("unit_raster") or {}).get("grid") or {}).get("cell_m", 20.0))
    map_image, map_info = render_map(values, lookup, classes, cell_m=cell_m)
    rows = list(classes.values())
    districts = list((((frame.get("protocol") or {}).get("frame_rules") or {}).get("district_names")) or [])
    words = brief.pass_words(outcome, overlay)
    slide = draw_slide(map_image, map_info, outcome, rows, result_name=Path(result_path).name, districts=districts,
                       pass_text=f"{words['utc']} UTC ({words['platform']})")
    record = {
        "generated_at_utc": generated_at or now_utc(),
        "source_timestamp": str(brief.flood_input_of(overlay).get("source_timestamp")),
        "confidence_class": "low" if any(row["confidence"] == "low" for row in rows) else "medium",
        "assumptions": json.dumps(["Every figure is agreement with another map, not accuracy.",
                                   "The classes are those of the N1 result file; a would-be class is never binding.",
                                   "No JAXA, GFM or THEOS-2 map is drawn; only figures of the test record are shown."]),
        "official_warning": "false",
        "operational_status": "non_operational",
        "made_from": json.dumps({"result_file": {"name": Path(result_path).name, "sha256": result_sha},
                                 "test_record": {"name": Path(test_path).name, "sha256": test_sha},
                                 "frame_record": {"name": Path(frame_path).name, "sha256": frame_sha},
                                 "unit_raster": {"name": Path(unit_raster).name, "sha256": sha256_file(unit_raster)}}),
    }
    info = PngInfo()
    info.add_text("Title", "The Nan case, N1: classes and test figures")
    info.add_text("Description", meaning_of(outcome, rows))
    for key, value in record.items():
        info.add_text(key, value)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    slide.save(out_path, pnginfo=info, optimize=True)
    return {"path": out_path, "size": slide.size, "sha256": sha256_file(out_path), "map": map_info, "record": record}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and draw the slide; 0 when written, 2 when an input was refused."""

    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--result", type=Path, help="the N1 result file (default: as the brief finds it)")
    parser.add_argument("--test-result", type=Path, default=ROOT / brief.TEST_RESULT)
    parser.add_argument("--frame-record", type=Path, default=ROOT / FRAME_RECORD)
    parser.add_argument("--unit-raster", type=Path, help="the frame's unit raster (default: the one the frame record names)")
    parser.add_argument("--external-root", type=Path, help="the external data root, where the frame record's unit raster lies")
    parser.add_argument("--out", type=Path, default=ROOT / SLIDE)
    args = parser.parse_args(argv)
    try:
        result = brief.find_result(args.result)
        raster = args.unit_raster
        if raster is None:
            if args.external_root is None:
                raise SlideError("give --external-root (or --unit-raster) to read the frame's unit raster")
            raster = unit_raster_path(brief.read_json(args.frame_record)[0], args.external_root)
        summary = build(result, args.test_result, args.frame_record, raster, args.out)
    except (brief.N1BriefError, OSError, json.JSONDecodeError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"wrote {brief.label_of(summary['path'])}: {summary['size']}, SHA-256 {summary['sha256']}, "
          f"{len(summary['map']['units_drawn'])} tambons drawn")
    return EXIT_DONE


if __name__ == "__main__":
    raise SystemExit(main())
