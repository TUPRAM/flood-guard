"""Lay out unmodified scene renders on a labeled, shareable review board."""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs/landing-v2-assets"
PAPER = (250, 248, 242, 255)


def main():
    board = Image.new("RGBA", (2400, 748), PAPER)
    draw = ImageDraw.Draw(board)
    font_path = Path(os.environ.get("WINDIR", "")) / "Fonts/segoeui.ttf"
    font = ImageFont.truetype(str(font_path), 26) if font_path.exists() else ImageFont.load_default(size=26)
    small = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default(size=18)
    draw.text((32, 20), "FloodGuard  |  One editable neighborhood, three illustrative water states", fill="#152b29", font=font)
    for index, (state, title) in enumerate((("w0", "01  Everyday connections"), ("w1", "02  Conditions change"), ("w2", "03  The connection is affected"))):
        render = Image.open(OUTPUT / "renders" / (state + ".png")).convert("RGBA")
        render.thumbnail((800, 600), Image.Resampling.LANCZOS)
        board.alpha_composite(render, (index * 800, 86))
        draw.text((index * 800 + 32, 700), title, fill="#006f78", font=small)
    board.convert("RGB").save(OUTPUT / "neighborhood-states.png")
    print(OUTPUT / "neighborhood-states.png")


if __name__ == "__main__":
    main()
