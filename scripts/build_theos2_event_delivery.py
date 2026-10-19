"""The THEOS-2 scene of 17 September 2024 over Mae Sai as GISTDA delivered it: unpacked outside Git and recorded.

GISTDA produced it on 14 October 2026 in two orders (``AWG_20261014_bc7a15``, the town box, and
``AWG_20261014_417d92``, the west edge of the Ko Chang box), each cut in two overlapping products, and sent it as two
zips of nested zips. Two stages:

``extract``
    Unpacks every product under ``<external root>/theos2_delivery/20240917_v1/`` with the SHA-256 of each zip.
``record``
    Reads the product metadata (DIM XML) and the raster headers, never a pixel, and writes
    ``outputs/theos2_delivery/delivery_20240917_v1.json``: acquisition time, cloud figures, footprints, the pixel
    grid of each product, and which tambons and which roads of the Ko Chang road sheet each footprint covers.

Nobody has looked at the image when this runs; the record says so. The imagery stays outside Git.

    python scripts/build_theos2_event_delivery.py extract --external-root <root> --zips <zip> <zip>
    python scripts/build_theos2_event_delivery.py record --external-root <root>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import theos2_event_delivery as delivery  # noqa: E402

WORK = Path("theos2_delivery") / "20240917_v1"
OUTPUT = "outputs/theos2_delivery/delivery_20240917_v1.json"
EXTRACT_RECEIPT = "extract_receipt.json"


class BuildError(RuntimeError):
    """The delivery is not what this script expects."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF bytes on every platform: receipts bind these files by SHA-256.
    path.write_bytes((json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def stage_extract(arguments: argparse.Namespace) -> None:
    work = Path(arguments.external_root) / WORK
    receipt_path = work / EXTRACT_RECEIPT
    if receipt_path.exists():
        raise BuildError(f"{receipt_path} exists: the delivery is unpacked once")
    work.mkdir(parents=True, exist_ok=True)
    outer_rows, product_rows = [], []
    for outer in sorted(Path(name) for name in arguments.zips):
        outer_rows.append({"name": outer.name, "bytes": outer.stat().st_size, "sha256": sha256_file(outer)})
        with zipfile.ZipFile(outer) as archive:
            for member in archive.infolist():
                if not member.filename.lower().endswith(".zip"):
                    continue
                order = delivery.order_of(member.filename)
                inner_path = work / "zips" / Path(member.filename).name
                inner_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, inner_path.open("wb") as target:
                    shutil.copyfileobj(source, target, 16 * 1024 * 1024)
                product = work / order / inner_path.stem
                with zipfile.ZipFile(inner_path) as inner:
                    delivery.check_member_names([item.filename for item in inner.infolist()])
                    inner.extractall(product)
                product_rows.append({"order": order, "product": inner_path.stem, "from_zip": outer.name,
                                     "inner_zip_bytes": inner_path.stat().st_size, "inner_zip_sha256": sha256_file(inner_path)})
                inner_path.unlink()
                print(f"unpacked {order}/{inner_path.stem}", flush=True)
    (work / "zips").rmdir()
    write_json(receipt_path, {"unpacked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "outer_zips": outer_rows, "products": product_rows})


def stage_record(arguments: argparse.Namespace) -> None:
    import rasterio

    external = Path(arguments.external_root)
    work = external / WORK
    receipt = json.loads((work / EXTRACT_RECEIPT).read_text(encoding="utf-8"))
    products = []
    for row in receipt["products"]:
        folder = work / row["order"] / row["product"]
        image = delivery.single(folder.glob("VOL_*/IMG_*/IMG_*.TIF"), "image")
        dim = delivery.single(folder.glob("VOL_*/IMG_*/DIM_*.XML"), "DIM metadata")
        cloud = delivery.single(folder.glob("VOL_*/IMG_*/CLD_MASK_*.TIF"), "cloud mask")
        metadata = delivery.parse_dim(dim.read_bytes())
        with rasterio.open(image) as source:
            header = {"crs_epsg": source.crs.to_epsg() if source.crs else None, "width": source.width, "height": source.height,
                      "count": source.count, "dtype": source.dtypes[0], "nodata": source.nodata,
                      "transform": list(source.transform)[:6], "bounds": list(source.bounds),
                      "band_colours": [source.tags(band).get("COLOR", "") for band in range(1, source.count + 1)]}
        header["dim_minus_geotiff_upper_left_m"] = [round(metadata["upper_left_m_stated"][0] - header["transform"][2], 3),
                                                    round(metadata["upper_left_m_stated"][1] - header["transform"][5], 3)]
        products.append({**row, "image": {"path": image.relative_to(work).as_posix(), "bytes": image.stat().st_size,
                                          "sha256": sha256_file(image)},
                         "cloud_mask": {"path": cloud.relative_to(work).as_posix(), "sha256": sha256_file(cloud)},
                         "dim": {"path": dim.relative_to(work).as_posix(), "sha256": sha256_file(dim)},
                         "metadata": metadata, "header": header})
    delivery.check_one_scene(products)
    grid = delivery.common_grid([product["header"] for product in products])
    context = delivery.coverage_context(ROOT)
    record = {
        "schema": "floodguard.theos2_event_delivery.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": f"THEOS-2 {products[0]['metadata']['acquired_utc']}",
        "confidence_class": "not_applicable",
        "confidence_basis": "A record of files and their metadata; it reads no pixel and states no finding.",
        "what_this_is": "The THEOS-2 scene of 17 September 2024 over Mae Sai as GISTDA delivered it, recorded from its metadata and raster headers before anybody looked at the image.",
        "pixels_read": False,
        "image_looked_at": False,
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "work_folder_outside_git": WORK.as_posix(),
        "outer_zips": receipt["outer_zips"],
        "products": products,
        "one_pixel_grid": grid,
        "coverage": delivery.coverage(products, context),
        "licence": "THEOS-2 imagery provided by GISTDA for GeoHackathon 2026. The imagery stays outside Git; derived figures are shared. Showing the image itself waits for GISTDA's answer.",
        "assumptions": ["Footprints are the product footprints the DIM metadata states; the valid pixels inside them are not read here.",
                        "Cloud figures are GISTDA's, from the metadata; the cloud masks are recorded, not read."],
        "limits": ["One scene, 28.6 hours after the Sentinel-1 pass of record and about five days after the modelled peak."],
    }
    write_json(ROOT / OUTPUT, record)
    print(json.dumps(record["coverage"], indent=1, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stage", choices=("extract", "record"))
    parser.add_argument("--external-root", required=True)
    parser.add_argument("--zips", nargs="*", default=[])
    arguments = parser.parse_args()
    if arguments.stage == "extract" and not arguments.zips:
        raise BuildError("the extract stage needs --zips")
    {"extract": stage_extract, "record": stage_record}[arguments.stage](arguments)


if __name__ == "__main__":
    main()
