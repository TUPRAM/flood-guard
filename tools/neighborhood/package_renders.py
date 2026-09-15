"""Encode rendered neighborhood artwork and record reproducible file provenance."""

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RENDERS = ROOT / "outputs/landing-v2-assets/renders"
PUBLIC = ROOT / "apps/web/public/landing/floodguard-v2"


def encode(source, destination, width, quality):
    image = Image.open(source).convert("RGBA")
    height = round(image.height * width / image.width)
    if image.width != width:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "WEBP", quality=quality, method=6)
    return {"source": str(source.relative_to(ROOT)).replace("\\", "/"),
            "url": "/" + str(destination.relative_to(ROOT / "apps/web/public")).replace("\\", "/"),
            "width": width, "height": height, "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def main():
    records = []
    for index in range(16):
        records.append(encode(RENDERS / f"approach-{index:02}.png", PUBLIC / f"camera/approach-{index:02}.webp", 1536 if index in (0, 15) else 1152, 86))
    for state in ("w0", "w1", "w2"):
        records.append(encode(RENDERS / f"{state}.png", PUBLIC / f"plates/{state}.webp", 2048, 90))
    report = {"source": "Editable Blender 5.1 neighborhood; same geometry and lighting in every water state",
              "encoding": "Pillow WebP, Lanczos downsample, no generative image replacement",
              "files": records, "runtimeBytes": sum(record["bytes"] for record in records)}
    path = ROOT / "outputs/landing-v2-assets/asset-provenance.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"assets": len(records), "bytes": report["runtimeBytes"], "report": str(path)}))


if __name__ == "__main__":
    main()
