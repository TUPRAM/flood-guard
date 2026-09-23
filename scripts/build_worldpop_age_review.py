"""Build an external, candidate-only age review from exact-year WorldPop rasters."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from floodguard.evidence_age_surface import AGE_BANDS, review_units


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _features(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError(f"Expected nonempty GeoJSON FeatureCollection: {path}")
    declared_crs = data.get("crs")
    if declared_crs is not None and declared_crs not in (
        "EPSG:4326",
        {"type": "name", "properties": {"name": "EPSG:4326"}},
        {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
    ):
        raise ValueError(f"GeoJSON geometry must be WGS84 longitude/latitude: {path}")
    return data["features"]


def build_review(
    acquisition_manifest: Path, unit_geojson: Path, aoi_geojson: Path,
    output_dir: Path, *, unit_id_field: str = "subdistrict_id",
) -> dict:
    """Verify every source byte and summarize whole units and clipped AOI counts."""
    if output_dir.exists():
        raise ValueError("Output directory already exists; create a new immutable run")
    manifest = json.loads(acquisition_manifest.read_text(encoding="utf-8"))
    year = manifest.get("year_represented")
    if (manifest.get("schema_version") != "floodguard.worldpop_age_acquisition.v1"
            or manifest.get("status") != "PASS" or year not in (2024, 2025)
            or "R2025A v1" not in manifest.get("product", "")):
        raise ValueError("Complete exact-year WorldPop R2025A v1 acquisition required")
    resolution = manifest.get("resolution_code", "100m")
    if resolution not in {"100m", "1km"}:
        raise ValueError("Unrecognized WorldPop source resolution")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != len(AGE_BANDS):
        raise ValueError("All 20 WorldPop age bands are required")
    paths = {}
    for record in records:
        band = record.get("band")
        if band not in AGE_BANDS or band in paths:
            raise ValueError("Unknown or duplicate age band")
        expected_name = (f"tha_t_{band}_{year}_CN_100m_R2025A_v1.tif"
                         if resolution == "100m" else
                         f"tha_t_{band}_{year}_CN_1km_R2025A_UA_v1.tif")
        if record.get("file") != expected_name:
            raise ValueError("Unexpected age raster filename")
        source_path = "100m" if resolution == "100m" else "1km_ua"
        expected_url = (
            "https://data.worldpop.org/GIS/AgeSex_structures/"
            f"Global_2015_2030/R2025A/{year}/THA/v1/{source_path}/"
            f"constrained/{expected_name}"
        )
        if record.get("url") != expected_url:
            raise ValueError("Unexpected age raster source URL")
        path = acquisition_manifest.parent / expected_name
        if (not path.is_file() or path.stat().st_size != record.get("bytes")
                or _sha(path) != record.get("sha256")):
            raise ValueError(f"Age raster byte identity failed: {band}")
        paths[band] = path
    if set(paths) != set(AGE_BANDS):
        raise ValueError("Age bands are incomplete")
    aoi_features = _features(aoi_geojson)
    if len(aoi_features) != 1:
        raise ValueError("Exactly one AOI feature is required")
    aoi = shape(aoi_features[0]["geometry"])
    if not aoi.is_valid or aoi.is_empty:
        raise ValueError("AOI geometry is invalid")
    units = {}
    unit_properties = {}
    for feature in _features(unit_geojson):
        unit_id = feature.get("properties", {}).get(unit_id_field)
        if not isinstance(unit_id, str) or not unit_id or unit_id in units:
            raise ValueError("Reporting units require unique string IDs")
        geom = shape(feature["geometry"])
        if not geom.is_valid or geom.is_empty:
            raise ValueError(f"Invalid reporting unit: {unit_id}")
        units[unit_id] = geom
        unit_properties[unit_id] = {
            key: value for key, value in feature.get("properties", {}).items()
            if key in {unit_id_field, "subdistrict_name", "subdistrict_name_th",
                       "name", "name_th", "boundary_valid_on", "boundary_version",
                       "source_name", "source_timestamp", "attribution", "license",
                       "license_url"}
        }
    selected = {key: geom for key, geom in units.items() if geom.intersects(aoi)}
    if not selected:
        raise ValueError("No reporting unit intersects AOI")
    projector = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
    clipped_geometries = [transform(projector, geom.intersection(aoi))
                          for geom in selected.values()]
    overlap_area = sum(geom.area for geom in clipped_geometries) - unary_union(clipped_geometries).area
    if overlap_area > 1.0:
        raise ValueError(f"Reporting unit AOI intersections overlap by {overlap_area:.2f} m2")
    rows = review_units(paths, selected, aoi)
    for row in rows:
        row["unit_source"] = unit_properties[row["unit_id"]]
    aoi_area = transform(projector, aoi).area
    covered_area = unary_union(clipped_geometries).area
    result = {
        "schema_version": "floodguard.worldpop_age_review.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "year_represented": year,
        "source_publication_date": manifest.get("publication_date"),
        "source_acquisition_manifest_sha256": _sha(acquisition_manifest),
        "source_catalog_url": manifest.get("catalog_url"),
        "source_product": manifest.get("product"),
        "source_resolution": resolution,
        "source_units": "modelled residential people per source grid cell",
        "age_groups": {"children": "0-14 inclusive", "older_adults": "60+ inclusive",
                       "other": "15-59 inclusive"},
        "aoi_id": aoi_features[0].get("properties", {}).get("aoi_id"),
        "aoi_geometry_sha256": _sha(aoi_geojson),
        "unit_geometry_sha256": _sha(unit_geojson),
        "aoi_area_km2": aoi_area / 1e6,
        "reporting_units_cover_aoi_fraction": min(1.0, covered_area / aoi_area),
        "aoi_outside_selected_reporting_units_km2": max(0.0, (aoi_area - covered_area) / 1e6),
        "units": rows,
        "status": "modelled_research_candidate" if all(
            row[grain]["status"] == "modelled_research_estimate"
            for row in rows for grain in ("full_unit", "aoi_intersection")
        ) else "partial_raster_coverage",
        "confidence_class": "unqualified_modelled_estimate",
        "operational_status": "non_operational",
        "official_warning": False,
        "accepted_exposure": None,
        "accepted_equity": None,
        "accepted_fpps": None,
        "limitations": [
            "Modelled residential age counts, not measured local counts or event-day presence.",
            "Full reporting-unit counts and AOI intersections are different denominators.",
            "AOI geometry outside selected reporting units is reported, not assumed to be missing Thai population.",
            "Direct fractional pixel overlap in EPSG:32647; no age-share transfer or bilinear interpolation.",
            "2024/2025 age estimates may differ in vintage from older candidate flood and routing packages.",
            "Hosted derivatives and downstream acceptance require separate purpose and evidence review.",
        ],
    }
    output_dir.mkdir(parents=True)
    output = output_dir / "age_review.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": "floodguard.worldpop_age_review_receipt.v1",
        "output_sha256": _sha(output),
        "output_bytes": output.stat().st_size,
        "source_acquisition_manifest_sha256": result["source_acquisition_manifest_sha256"],
        "aoi_geometry_sha256": result["aoi_geometry_sha256"],
        "unit_geometry_sha256": result["unit_geometry_sha256"],
        "status": result["status"],
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", required=True, type=Path)
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--aoi", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--unit-id-field", default="subdistrict_id")
    args = parser.parse_args()
    print(json.dumps(build_review(
        args.acquisition_manifest, args.units, args.aoi, args.output,
        unit_id_field=args.unit_id_field,
    )))


if __name__ == "__main__":
    main()
