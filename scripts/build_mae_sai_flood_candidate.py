"""Derive a separate non-operational SAR change candidate, never a reference label."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.sar_raster_extract import build_sentinel1_safe_band_uri


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(root):
        parser.error("Raw and intermediate rasters must remain outside Git")
    aoi_path = root / "resources/aoi/upload/aoi-01_mae_sai_core.geojson"
    aoi_json = json.loads(aoi_path.read_bytes())
    aoi = unary_union([shape(f["geometry"]) for f in aoi_json["features"]])
    to_metres = Transformer.from_crs(4326, 32647, always_xy=True).transform
    to_web = Transformer.from_crs(32647, 4326, always_xy=True).transform
    projected = transform(to_metres, aoi)
    west, south, east, north = projected.bounds
    resolution = 20
    west, south = (
        math.floor(west / resolution) * resolution,
        math.floor(south / resolution) * resolution,
    )
    east, north = (
        math.ceil(east / resolution) * resolution,
        math.ceil(north / resolution) * resolution,
    )
    grid = from_origin(west, north, resolution, resolution)
    size = (round((north - south) / resolution), round((east - west) / resolution))
    manifest_path = root / "outputs/cdse_mae_sai_acquisition_manifest.csv"
    rows = list(csv.DictReader(manifest_path.open(encoding="utf-8-sig")))
    selected = {}
    for date, role in (("2024-09-03", "pre"), ("2024-09-15", "post")):
        matches = [r for r in rows if r["acquisition_date"].startswith(date)]
        if len(matches) != 1:
            raise ValueError("Expected exactly one checksum-bound SAFE per acquisition")
        row = matches[0]
        if row["source_license_status"] != "confirmed_copernicus_sentinel_legal_notice":
            raise ValueError("Sentinel reuse terms are unresolved")
        path = (
            args.external_data_root
            / "sentinel1_original_safe"
            / (row["product_name"] + ".zip")
        )
        if sha256_file(path) != row["sha256"]:
            raise ValueError("SAFE bytes differ from recorded source identity")
        selected[role] = (row, path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    arrays, georeferencing = {}, {}
    for role, (row, path) in selected.items():
        for polarization in ("VV", "VH"):
            print(f"Warping {role} {polarization} onto the fixed 20 m grid", flush=True)
            with (
                rasterio.Env(GDAL_PAM_ENABLED="NO"),
                rasterio.open(
                    build_sentinel1_safe_band_uri(path, polarization)
                ) as source,
            ):
                gcps, crs = source.gcps
                if len(gcps) < 6 or crs is None:
                    raise ValueError("Original SAFE lacks usable GCP georeferencing")
                destination = np.full(size, np.nan, dtype="float32")
                reproject(
                    source=rasterio.band(source, 1),
                    destination=destination,
                    gcps=gcps,
                    src_crs=crs,
                    src_nodata=0,
                    dst_transform=grid,
                    dst_crs="EPSG:32647",
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                    num_threads=1,
                    MAX_GCP_ORDER=2,
                )
                arrays[role + polarization] = np.where(
                    destination > 0, destination, np.nan
                )
                georeferencing[role + polarization] = {
                    "gcp_count": len(gcps),
                    "gcp_crs": str(crs),
                }
    with np.errstate(invalid="ignore", divide="ignore"):
        drop = 0.4 * 20 * np.log10(
            arrays["preVV"] / arrays["postVV"]
        ) + 0.6 * 20 * np.log10(arrays["preVH"] / arrays["postVH"])
    inside = geometry_mask(
        [mapping(projected)], out_shape=size, transform=grid, invert=True
    )
    valid = inside & np.isfinite(drop)
    if valid.sum() == 0:
        raise ValueError("No jointly valid observations cover the AOI")
    # The original published rule was score=(drop-0.5)/(4-0.5), cutoff=0.5.
    # Retain its fixed 2.25 dB cutoff without tuning to roads, people or labels.
    threshold = 2.25
    mask = valid & (drop >= threshold)
    profile = {
        "driver": "GTiff",
        "width": size[1],
        "height": size[0],
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:32647",
        "transform": grid,
        "nodata": 255,
        "compress": "deflate",
    }
    with rasterio.open(
        args.output_dir / "candidate_mask.tif", "w", **profile
    ) as dataset:
        dataset.write(np.where(valid, mask.astype("uint8"), 255).astype("uint8"), 1)
    products = {}
    for name, selected_mask in (
        ("candidate_extent", mask),
        ("observation_footprint", valid),
    ):
        geometries = [
            shape(g)
            for g, value in shapes(
                selected_mask.astype("uint8"), mask=selected_mask, transform=grid
            )
            if value == 1
        ]
        geometry = unary_union(geometries).intersection(projected)
        payload = {
            "type": "FeatureCollection",
            "features": []
            if geometry.is_empty
            else [
                {
                    "type": "Feature",
                    "properties": {
                        "evidence_role": "candidate",
                        "event_id": "mae_sai_2024",
                        "product": name,
                        "official_warning": False,
                    },
                    "geometry": mapping(
                        transform(to_web, geometry.segmentize(resolution))
                    ),
                }
            ],
        }
        (args.output_dir / f"{name}.geojson").write_bytes(canonical_bytes(payload))
        products[name] = {
            "file": f"{name}.geojson",
            "sha256": sha256_file(args.output_dir / f"{name}.geojson"),
            "area_m2": geometry.area,
        }
    metadata = {
        "schema_version": "floodguard.sar_change_candidate.v1",
        "generated_at": args.generated_at,
        "event_id": "mae_sai_2024",
        "evidence_role": "candidate",
        "confidence_class": "low",
        "official_warning": False,
        "eligible_for_validation": False,
        "eligible_for_accepted_fpps": False,
        "processing_scope": "separate_non_operational_candidate_scenario_only",
        "source_timestamp": selected["post"][0]["acquisition_date"],
        "sources": [
            {
                k: row[k]
                for k in (
                    "product_id",
                    "product_name",
                    "acquisition_date",
                    "sha256",
                    "download_url",
                )
            }
            for row, _ in selected.values()
        ],
        "aoi_sha256": sha256_file(aoi_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "method": "gcp_order_2_warp_uncalibrated_amplitude_change_v1",
        "threshold_db": threshold,
        "polarization_weights": {"VV": 0.4, "VH": 0.6},
        "grid": {
            "crs": "EPSG:32647",
            "resolution_m": resolution,
            "shape": list(size),
            "transform": list(grid)[:6],
        },
        "georeferencing": georeferencing,
        "aoi_pixels": int(inside.sum()),
        "valid_pixels": int(valid.sum()),
        "candidate_pixels": int(mask.sum()),
        "valid_fraction": float(valid.sum() / inside.sum()),
        "products": products,
        "mask_sha256": sha256_file(args.output_dir / "candidate_mask.tif"),
        "implementation_sha256": sha256_file(Path(__file__)),
        "rights": {
            "local_processing": True,
            "hosted_display": True,
            "downloadable_derivatives": True,
            "terms_url": "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
            "attribution": "Contains modified Copernicus Sentinel data (2024), processed by FloodGuard.",
        },
        "limitations": [
            "Backscatter-drop candidate, not validated inundation or a calibrated flood probability.",
            "Uncalibrated amplitude, not sigma0/gamma0; no terrain correction, speckle filter or permanent-water exclusion.",
            "GCP polynomial warp aligns a common grid; metre-scale accuracy and local residual errors remain unverified.",
            "Observation question: change from 3 to 15 September, not September peak or all floodwater.",
            "No cross-border manual labels, review-only derivatives or weak-reference accuracy metrics enter this calculation.",
            "Qualified-reference gates and the original weak-reference package remain unchanged.",
        ],
    }
    for row, path in selected.values():
        if sha256_file(path) != row["sha256"]:
            raise ValueError("SAFE input changed during extraction")
    (args.output_dir / "manifest.json").write_bytes(canonical_bytes(metadata))
    print(
        json.dumps(
            {k: metadata[k] for k in ("valid_fraction", "candidate_pixels", "products")}
        )
    )


if __name__ == "__main__":
    main()
