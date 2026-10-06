"""Verify downloaded Hat Yai originals and register external, immutable source files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.geometry import shape
from shapely.ops import unary_union

from floodguard.evidence_catalog import canonical_bytes, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--external-data-root", type=Path, required=True)
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "outputs/cdse_hat_yai_acquisition_manifest.csv"
    previous = {}
    if output.is_file():
        with output.open(encoding="utf-8") as stream:
            previous = {row["product_id"]: row for row in csv.DictReader(stream)}
    if args.external_data_root.resolve().is_relative_to(root) or args.receipt.resolve().is_relative_to(root):
        parser.error("Raw files and intake receipt must remain outside Git")
    aoi = unary_union([shape(f["geometry"]) for f in json.loads((root / "resources/aoi/upload/aoi-03_hat_yai_core.geojson").read_bytes())["features"]])
    destination = args.external_data_root / "sentinel1_original_safe"
    destination.mkdir(parents=True, exist_ok=True)
    rows, checks = [], []
    for phase in ("before", "after"):
        product = json.loads((args.catalog_dir / ("cdse_" + phase + ".txt")).read_bytes())
        name = product["Name"]
        if Path(name).name != name or "_COG" in name or not name.startswith("S1A_IW_GRDH_1SDV_202511"):
            raise ValueError("Unexpected original product identity")
        source = args.downloads / (name + ".zip")
        if source.stat().st_size != product["ContentLength"]:
            raise ValueError("Download size differs from catalogue: " + name)
        digest = hashlib.md5(usedforsecurity=False)
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        expected = next(c["Value"] for c in product["Checksum"] if c["Algorithm"] == "MD5")
        if digest.hexdigest() != expected:
            raise ValueError("Download checksum differs from catalogue: " + name)
        if not shape(product["GeoFootprint"]).covers(aoi):
            raise ValueError("Product does not fully cover Hat Yai core")
        with zipfile.ZipFile(source) as archive:
            if archive.testzip() is not None:
                raise ValueError("Corrupt SAFE ZIP")
            manifest = ET.fromstring(archive.read(name + "/manifest.safe"))
            values = lambda tag: sorted({e.text for e in manifest.iter() if e.tag.split("}")[-1] == tag and e.text})
            check = {"product_id": product["Id"], "relative_orbit": values("relativeOrbitNumber"), "pass": values("pass"), "mode": values("mode"), "polarizations": values("transmitterReceiverPolarisation"), "full_aoi_coverage": True, "zip_crc": "passed", "catalog_md5": expected}
            if check["mode"] != ["IW"] or check["polarizations"] != ["VH", "VV"] or not check["relative_orbit"] or not check["pass"]:
                raise ValueError("Unexpected SAFE acquisition metadata")
        digest256 = sha256_file(source)
        target = destination / source.name
        if target.exists() and sha256_file(target) != digest256:
            raise ValueError("Refusing to replace a different source archive")
        if not target.exists():
            shutil.copyfile(source, target)
        if sha256_file(target) != digest256:
            raise ValueError("External source copy differs")
        checks.append(check)
        rows.append({"product_id": product["Id"], "product_name": name, "candidate_role": phase,
            "acquisition_date": product["ContentDate"]["Start"],
            "download_url": f"https://download.dataspace.copernicus.eu/odata/v1/Products({product['Id']})/$value",
            "local_path_hint": "<external_data_workspace>/sentinel1_original_safe/" + source.name,
            "sha256": digest256, "file_size_bytes": target.stat().st_size,
            "source_license_status": "confirmed_copernicus_sentinel_legal_notice", "reference_mask_status": "unresolved",
            "processing_allowed": False, "reason_blocked": "Qualified-reference and accepted-decision processing remains blocked; separate low-confidence non-operational candidate experiment only.",
            "retrieved_at_utc": previous[product["Id"]]["retrieved_at_utc"]
            if previous.get(product["Id"], {}).get("sha256") == digest256
            else datetime.now(timezone.utc).isoformat()})
    if any(checks[0][key] != checks[1][key] for key in ("relative_orbit", "pass", "mode", "polarizations")):
        raise ValueError("Original SAFE pair has incompatible acquisition geometry")
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(canonical_bytes({"schema_version": "1.0", "checks": checks, "manifest_sha256": sha256_file(output), "qualified_for_validation": False}))
    print(json.dumps({"registered": len(rows), "checks": checks}))


if __name__ == "__main__":
    main()
