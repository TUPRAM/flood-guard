"""Inventory a NASA MCDWD HDF4 granule on a declared CRS84 study polygon.

Run with ``uv run --with pyhdf python scripts/inspect_nasa_mcdwd.py ...``.
This reads native reference classes only; it never loads a radar prediction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from shapely.geometry import shape

LAYERS = ("FloodCS_1Day_250m", "Flood_1Day_250m")
CLASS_MEANINGS = {
    "0": "no_water",
    "1": "expected_surface_water",
    "2": "recurring_flood",
    "3": "unusual_flood",
    "255": "insufficient_data",
}


def file_hashes(path: Path) -> tuple[int, str, str]:
    """Return byte count, MD5 for provider matching, and SHA-256 for lineage."""
    md5, sha256 = hashlib.md5(), hashlib.sha256()  # Provider MD5 is only an integrity check.
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            count += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return count, md5.hexdigest(), sha256.hexdigest()


def metadata_value(metadata: str, key: str) -> str:
    """Read one scalar VALUE from an HDF-EOS metadata OBJECT."""
    block = re.search(
        rf"\bOBJECT\s*=\s*{re.escape(key)}\b(.*?)\bEND_OBJECT\s*=\s*{re.escape(key)}\b",
        metadata, flags=re.DOTALL,
    )
    match = re.search(r'\bVALUE\s*=\s*"([^"]+)"', block.group(1)) if block else None
    if match is None:
        raise ValueError(f"Missing HDF metadata: {key}")
    return match.group(1)


def native_grid(metadata: str) -> tuple[int, int, Affine]:
    """Use the HDF structural WGS84 grid, refusing unsupported projections."""
    required = (
        "Projection=GCTP_GEO", "SphereCode=12", "GridOrigin=HDFE_GD_UL",
        "PixelRegistration=HDFE_CORNER",
    )
    if any(value not in metadata for value in required):
        raise ValueError("Unsupported MCDWD native georeferencing")
    dims = []
    for name in ("XDim", "YDim"):
        match = re.search(rf"\b{name}=(\d+)", metadata)
        if match is None:
            raise ValueError(f"Missing grid dimension {name}")
        dims.append(int(match.group(1)))
    corners = []
    for name in ("UpperLeftPointMtrs", "LowerRightMtrs"):
        match = re.search(rf"\b{name}=\((-?[\d.]+),(-?[\d.]+)\)", metadata)
        if match is None:
            raise ValueError(f"Missing grid corner {name}")
        corners.append(tuple(float(x) / 1_000_000 for x in match.groups()))
    width, height = dims
    (west, north), (east, south) = corners
    if width <= 0 or height <= 0 or not (west < east and south < north):
        raise ValueError("Invalid native grid bounds")
    return width, height, Affine((east - west) / width, 0, west, 0, (south - north) / height, north)


def aoi_window(aoi_path: Path, width: int, height: int, transform: Affine) -> tuple[tuple[int, int, int, int], np.ndarray]:
    """Select pixel centres inside the complete declared CRS84 AOI."""
    document = json.loads(aoi_path.read_text(encoding="utf-8"))
    if document.get("crs", {}).get("properties", {}).get("name") != "urn:ogc:def:crs:OGC:1.3:CRS84":
        raise ValueError("AOI must declare CRS84")
    geometries = [shape(feature["geometry"]) for feature in document["features"]]
    if not geometries or any(geometry.is_empty or not geometry.is_valid for geometry in geometries):
        raise ValueError("AOI geometry is empty or invalid")
    west = min(geometry.bounds[0] for geometry in geometries)
    south = min(geometry.bounds[1] for geometry in geometries)
    east = max(geometry.bounds[2] for geometry in geometries)
    north = max(geometry.bounds[3] for geometry in geometries)
    tile_east = transform.c + width * transform.a
    tile_south = transform.f + height * transform.e
    if west < transform.c or east > tile_east or south < tile_south or north > transform.f:
        raise ValueError("Complete AOI must fit inside the MCDWD tile")
    col0 = max(0, math.floor((west - transform.c) / transform.a))
    col1 = min(width, math.ceil((east - transform.c) / transform.a))
    row0 = max(0, math.floor((north - transform.f) / transform.e))
    row1 = min(height, math.ceil((south - transform.f) / transform.e))
    if not (col0 < col1 and row0 < row1):
        raise ValueError("AOI does not overlap the MCDWD tile")
    window_transform = transform * Affine.translation(col0, row0)
    inside = geometry_mask(
        geometries, out_shape=(row1 - row0, col1 - col0),
        transform=window_transform, invert=True, all_touched=False,
    )
    if not inside.any():
        raise ValueError("AOI has no native pixel centres in the tile")
    return (row0, row1, col0, col1), inside


def canonical_sha256(value: dict[str, Any]) -> str:
    """Hash the receipt content without its own digest field."""
    encoded = json.dumps(
        {key: item for key, item in value.items() if key != "receipt_sha256"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inspect_granule(source: Path, aoi: Path, expected_bytes: int, expected_md5: str, source_url: str) -> dict[str, Any]:
    """Verify a granule and inventory both native one-day flood layers."""
    from pyhdf.SD import (  # Opt-in HDF4 dependency, not needed by normal installs.
        SD,
        SDC,
    )

    count, md5, sha256 = file_hashes(source)
    if count != expected_bytes or md5.lower() != expected_md5.lower():
        raise ValueError("Granule size or provider MD5 mismatch")
    hdf = SD(str(source), SDC.READ)
    try:
        attributes = hdf.attributes()
        width, height, transform = native_grid(str(attributes["StructMetadata.0"]))
        window, inside = aoi_window(aoi, width, height, transform)
        row0, row1, col0, col1 = window
        core = str(attributes["CoreMetadata.0"])
        day_start = f"{metadata_value(core, 'RANGEBEGINNINGDATE')}T{metadata_value(core, 'RANGEBEGINNINGTIME')}"
        day_end = f"{metadata_value(core, 'RANGEENDINGDATE')}T{metadata_value(core, 'RANGEENDINGTIME')}"
        pointers_match = re.search(
            r"\bOBJECT\s*=\s*INPUTPOINTER\s+.*?\bVALUE\s*=\s*\((.*?)\)\s+END_OBJECT\s*=\s*INPUTPOINTER",
            core, flags=re.DOTALL,
        )
        if pointers_match is None:
            raise ValueError("Missing HDF input pointers")
        pointers = re.findall(r'"([^"]+)"', pointers_match.group(1))
        histograms: dict[str, dict[str, int]] = {}
        for layer in LAYERS:
            dataset = hdf.select(layer)
            if tuple(dataset.info()[2]) != (height, width):
                raise ValueError(f"Unexpected native dimensions for {layer}")
            values = dataset[row0:row1, col0:col1][inside]
            labels, counts = np.unique(values, return_counts=True)
            histogram = {str(int(label)): int(total) for label, total in zip(labels, counts, strict=True)}
            if any(label not in CLASS_MEANINGS for label in histogram):
                raise ValueError(f"Unknown {layer} class code")
            histograms[layer] = {code: histogram.get(code, 0) for code in CLASS_MEANINGS}
    finally:
        hdf.end()
    _, aoi_md5, aoi_sha256 = file_hashes(aoi)
    del aoi_md5
    receipt: dict[str, Any] = {
        "schema": "floodguard.nasa_mcdwd_native_aoi_inventory.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "product_id": source.name, "url": source_url, "edition": "NASA_LAADS_MCDWD_L3_061_standard",
            "bytes": count, "provider_md5": md5, "sha256": sha256,
            "day_begin_metadata": day_start, "day_end_metadata": day_end,
            "pge_version_metadata": metadata_value(core, "PGEVERSION"),
            "timezone_metadata": "not_explicit_in_hdf",
            "input_pointers": pointers,
        },
        "aoi": {"file": aoi.name, "sha256": aoi_sha256, "native_pixel_centres": int(inside.sum())},
        "native_grid": {
            "projection": "GCTP_GEO", "sphere_code": 12, "crs": "WGS84_from_HDF_structural_metadata",
            "width": width, "height": height,
            "upper_left_lon_lat": [transform.c, transform.f],
            "pixel_size_lon_lat": [transform.a, transform.e],
            "window_row_col_exclusive": list(window),
        },
        "class_meanings": CLASS_MEANINGS,
        "class_counts": histograms,
        "rights_basis": {
            "holder": "NASA",
            "policy_url": "https://modaps.modaps.eosdis.nasa.gov/services/faq/LAADS_Data-Use_Citation_Policies.pdf",
            "product_url": "https://www.earthdata.nasa.gov/global-flood-product",
            "product_doi": "10.5067/MODIS/MCDWD_L3.061",
            "subsequent_use_and_redistribution": "unrestricted_under_LAADS_policy",
            "research_comparison_allowed": True,
            "derived_aggregate_publication_allowed": True,
            "publication_attribution": (
                "MODIS Aqua+Terra Global Flood Product MCDWD_L3 "
                "(Reprocessed Archive), NASA LAADS DAAC, doi:10.5067/MODIS/MCDWD_L3.061."
            ),
            "interpretation": "Allowed uses follow from unrestricted subsequent use; NASA requests citation and acknowledgment for published derived results.",
        },
        "limitations": [
            "Automated MODIS optical map, not field truth or radar accuracy.",
            "Native cells are coarse relative to a 10 m radar candidate.",
            "The HDF does not provide exact per-pixel acquisition time or an explicit timezone suffix.",
            "No radar prediction, reference agreement, or study eligibility is evaluated by this inventory.",
        ],
        "event_selected": False,
        "human_reviewed": False,
        "accepted_observation": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def main() -> None:
    """Run one source-only AOI inventory and write a small receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--aoi", type=Path, required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--expected-md5", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = inspect_granule(args.source, args.aoi, args.expected_bytes, args.expected_md5, args.source_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Inventory: {args.output} ({receipt['receipt_sha256']})")


if __name__ == "__main__":
    main()
