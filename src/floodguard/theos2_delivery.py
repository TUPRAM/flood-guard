"""Metadata-only intake of delivered scenes with written, purpose-specific rights."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import rasterio
from pyproj import Transformer
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform, unary_union

from .evidence_catalog import safe_asset_path, sha256_file


def write_delivery_manifest(
    input_dir: Path, metadata_path: Path, aoi_dir: Path, output: Path
) -> Path:
    """Checksum scenes and test actual AOI polygons; default processing is false.

    Reads raster headers only. Coverage is raster footprint, not valid-pixel or
    cloud-free coverage. Written rights evidence must be present and checksum-bound
    before a positive local-processing decision can be recorded.
    """
    document = json.loads(metadata_path.read_bytes())
    if document.get("schema_version") != "floodguard.theos2_delivery.v1":
        raise ValueError("Unsupported THEOS-2 delivery metadata schema")
    aois = {}
    for path in sorted(aoi_dir.glob("*.geojson")):
        data = json.loads(path.read_bytes())
        geometry = unary_union([shape(f["geometry"]) for f in data["features"]])
        if not geometry.is_valid or geometry.is_empty:
            raise ValueError("Invalid AOI polygon")
        aois[path.stem] = (geometry, sha256_file(path))
    if not aois:
        raise ValueError("No AOI polygons found")
    rows, identifiers = [], set()
    to_metres = Transformer.from_crs(4326, 32647, always_xy=True).transform
    for scene in document["scenes"]:
        identifier = scene["scene_id"]
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or identifier in identifiers
        ):
            raise ValueError("Scene IDs must be nonempty and unique")
        identifiers.add(identifier)
        timestamp = datetime.fromisoformat(
            scene["acquisition_datetime"].replace("Z", "+00:00")
        )
        if timestamp.tzinfo is None:
            raise ValueError("Scene acquisition timestamp must include a timezone")
        path = safe_asset_path(input_dir, scene["file"])
        before = sha256_file(path)
        if scene.get("sha256") and before != scene["sha256"]:
            raise ValueError("Delivered scene checksum differs")
        with rasterio.Env(GDAL_PAM_ENABLED="NO"), rasterio.open(path) as raster:
            if raster.crs is None:
                raise ValueError(
                    "Scene needs georeferencing before AOI coverage can be established"
                )
            bands = scene["band_order"]
            if (
                len(bands) != raster.count
                or len(set(bands)) != len(bands)
                or any(not isinstance(b, str) or not b.strip() for b in bands)
            ):
                raise ValueError("Declared band order must match raster band count")
            # Densify edges before CRS conversion; corners alone can misstate coverage.
            pixels = []
            for i in range(33):
                fraction = i / 32
                pixels.append((raster.width * fraction, 0))
            for i in range(1, 33):
                pixels.append((raster.width, raster.height * i / 32))
            for i in range(1, 33):
                pixels.append((raster.width * (1 - i / 32), raster.height))
            for i in range(1, 33):
                pixels.append((0, raster.height * (1 - i / 32)))
            footprint = transform(
                Transformer.from_crs(raster.crs, 4326, always_xy=True).transform,
                Polygon([raster.transform * xy for xy in pixels]),
            )
        if not footprint.is_valid or footprint.is_empty:
            raise ValueError("Invalid delivered raster footprint")
        permissions = scene.get("permissions", {})
        terms = scene.get("written_terms")
        allowed, reason, terms_hash = (
            False,
            "Written terms and local-processing decision are unresolved",
            None,
        )
        if terms is not None:
            terms_path = safe_asset_path(input_dir, terms["file"])
            terms_hash = sha256_file(terms_path)
            if terms_hash != terms["sha256"]:
                raise ValueError("Written licence evidence checksum differs")
            if permissions.get("local_processing") is True:
                allowed, reason = True, ""
        requested = scene.get("aoi_ids", list(aois))
        if not requested or set(requested) - aois.keys():
            raise ValueError("Scene refers to unknown or missing AOIs")
        footprint_m = transform(to_metres, footprint)
        for aoi_id in requested:
            geometry, aoi_hash = aois[aoi_id]
            aoi_m = transform(to_metres, geometry)
            fraction = min(1.0, footprint_m.intersection(aoi_m).area / aoi_m.area)
            covered = footprint_m.buffer(0.01).covers(aoi_m)
            rows.append(
                {
                    "scene_id": identifier,
                    "file_name": scene["file"],
                    "sha256": before,
                    "acquisition_datetime": timestamp.isoformat(),
                    "product_level": scene["product_level"],
                    "band_order": json.dumps(bands),
                    "footprint_geojson": json.dumps(
                        mapping(footprint), separators=(",", ":")
                    ),
                    "aoi_id": aoi_id,
                    "aoi_sha256": aoi_hash,
                    "aoi_coverage_fraction": fraction,
                    "aoi_fully_covered": covered,
                    "coverage_basis": "raster_footprint_not_cloud_or_valid_pixel_coverage",
                    "license_terms_sha256": terms_hash,
                    "license_description": scene.get("license_description"),
                    "processing_allowed": allowed,
                    "hosted_display_allowed": allowed
                    and permissions.get("hosted_display") is True,
                    "downloadable_derivatives_allowed": allowed
                    and permissions.get("downloadable_derivatives") is True,
                    "reason_blocked": reason,
                    "metadata_sha256": sha256_file(metadata_path),
                }
            )
        if sha256_file(path) != before:
            raise ValueError("Scene changed during inventory")
    if not rows:
        raise ValueError("Delivery contains no scenes")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return output
