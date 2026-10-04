"""Source-bound reporting units and conservative event-reference eligibility.

This offline review never treats the AOI bounding rectangle as an administrative
unit, the union of flooded polygons as an observation footprint, or a public
download as permission to distribute a derivative or validate a model.
"""

from __future__ import annotations

import csv
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from .evidence_catalog import EVENTS, canonical_bytes, load_aois, sha256_file

REVIEW_VERSION = "event-review-1"
BOUNDARY_SOURCE = {
    "source_url": "https://data.humdata.org/dataset/cod-ab-tha",
    "metadata_url": "https://data.humdata.org/api/3/action/package_show?id=cod-ab-tha",
    "archive_url": "https://data.humdata.org/dataset/d24bdc45-eb4c-4e3d-8b16-44db02667c27/resource/ccbf3740-0638-48ea-b612-cdb61ef5462c/download/tha_admin_boundaries.gdb.zip",
    "source_sha256": "09e62345481bb80030ff6779e074bfb2c16629b70ae1e373ebd31945f1c6e0d8",
    "license": "CC BY 3.0 IGO",
    "license_url": "https://creativecommons.org/licenses/by/3.0/igo/legalcode",
    "license_snapshot_sha256": "ead394640e6e5bb492611a1993e95363af655e155f2c3391c289263b0ba2c4d2",
    "attribution": "Royal Thai Survey Department; OCHA ROAP / OCHA FIS, Thailand COD-AB, source valid 22 January 2022. FloodGuard selected intersecting ADM3 units and calculated AOI intersections. No endorsement implied.",
    "source_timestamp": "2022-01-22",
    "vintage_status": "2022_source_boundaries_event_era_currency_unverified",
    "public_derivatives": True,
}
_AREA = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _polygon(value: dict):
    if value.get("type") == "FeatureCollection":
        parts = [_polygon(f) for f in value["features"]]
        geom = unary_union(parts)
    elif value.get("type") == "Feature":
        geom = shape(value["geometry"])
    else:
        geom = shape(value)
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Expected nonempty polygon geometry")
    if not geom.is_valid:
        raise ValueError("Invalid polygon geometry requires an explicit repair review")
    if not (-180 <= geom.bounds[0] <= geom.bounds[2] <= 180):
        raise ValueError("Expected WGS84 longitude coordinates")
    if not (-90 <= geom.bounds[1] <= geom.bounds[3] <= 90):
        raise ValueError("Expected WGS84 latitude coordinates")
    return geom


def normalize_adm3_code(value: str | int) -> str:
    """Normalize an exact six-digit DOPA/HDX code; never join names or prefixes."""
    text = str(value).strip().upper().removeprefix("TH")
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"Not an ADM3 code: {value!r}")
    return "TH" + text


def build_reporting_crosswalk(aois: dict[str, dict], units: dict) -> dict:
    """Measure true polygon intersections with full-unit and AOI denominators.

    Areas use equal-area EPSG:6933. Coverage uses a union, so overlapping
    administrative polygons cannot silently double-count covered AOI area.
    Positive intersections below one square metre remain explicit slivers.
    """
    unit_rows = []
    seen = set()
    for feature in units["features"]:
        props = feature.get("properties", {})
        code = normalize_adm3_code(props["adm3_pcode"])
        if code in seen:
            raise ValueError(f"Duplicate ADM3 code: {code}")
        seen.add(code)
        geom = _polygon(feature)
        unit_rows.append((code, props, geom, transform(_AREA, geom)))
    rows = []
    for aoi_id, value in sorted(aois.items()):
        aoi = _polygon(value)
        projected_aoi = transform(_AREA, aoi)
        area = projected_aoi.area
        intersections, matches = [], []
        for code, props, geom, projected in unit_rows:
            # Intersect in source coordinates before projecting. Straight lines
            # transformed only at vertices otherwise introduce edge slivers.
            intersect = geom.intersection(aoi)
            if intersect.is_empty or intersect.area == 0:
                continue
            projected_intersection = transform(_AREA, intersect)
            measured = projected_intersection.area
            intersections.append(projected_intersection)
            matches.append(
                {
                    "adm3_pcode": code,
                    "name": props.get("name", props.get("adm3_name", code)),
                    "name_th": props.get("name_th", props.get("adm3_name1")),
                    "adm2_pcode": props.get("adm2_pcode"),
                    "adm1_pcode": props.get("adm1_pcode"),
                    "unit_area_km2": projected.area / 1e6,
                    "intersection_area_km2": measured / 1e6,
                    "unit_coverage_fraction": min(1.0, measured / projected.area),
                    "aoi_share": min(1.0, measured / area),
                    "scope": "full_unit" if aoi.covers(geom) else "partial_unit",
                    "sub_square_metre_intersection": measured < 1,
                }
            )
        covered = unary_union(intersections).area if intersections else 0.0
        overlap = max(0.0, sum(g.area for g in intersections) - covered)
        # Floating point residue below 1e-6 square metres is not an overlap/gap.
        overlap = 0.0 if overlap < 1e-6 else overlap
        uncovered = max(0.0, area - covered)
        uncovered = 0.0 if uncovered < 1e-6 else uncovered
        rows.append(
            {
                "aoi_id": aoi_id,
                "area_km2": area / 1e6,
                "covered_area_km2": covered / 1e6,
                "coverage_fraction": min(1.0, covered / area),
                "uncovered_area_km2": uncovered / 1e6,
                "overlapping_unit_area_km2": overlap / 1e6,
                "status": "no_intersection"
                if not matches
                else "covered"
                if covered / area >= 0.999999
                else "partial_coverage",
                "units": sorted(matches, key=lambda r: r["adm3_pcode"]),
            }
        )
    return {
        "schema_version": "1.0",
        "analysis_crs": "EPSG:6933",
        "numeric_area_tolerance_m2": 1e-6,
        "source_timestamp": BOUNDARY_SOURCE["source_timestamp"],
        "confidence_class": "low",
        "aois": rows,
        "assumptions": [
            "Source boundaries are from 2022; event-era currency is unverified.",
            "AOIs are study windows, not subdistricts. Partial-unit summaries describe only the AOI intersection.",
            "Coverage uses the union of unit intersections; overlapping membership must remain ambiguous in point joins.",
            "Uncovered AOI area has no reporting unit in this source; it is not zero population or dry land.",
            "No name-based or truncated-code joins. Point membership on shared boundaries requires explicit ambiguity handling.",
        ],
    }


def assess_event_evidence(
    event: dict, product: dict, aoi: dict, *, analysis_footprint: dict | None = None
) -> dict:
    """Keep temporal, footprint, rights and independent-validation gates separate.

    A positive result permits review as event-specific extent context. It is not
    accepted validation: that separate result requires explicit independent
    validation acceptance and rights for that use in the supplied review record.
    """
    start, end = date.fromisoformat(event["start"]), date.fromisoformat(event["end"])
    if start > end:
        raise ValueError("Event start is after its end")
    reasons = []
    try:
        first, last = (
            date.fromisoformat(product["start"]),
            date.fromisoformat(product["end"]),
        )
        if first > last:
            raise ValueError("Product start is after its end")
        within = start <= first <= last <= end
    except (KeyError, TypeError):
        within = False
        reasons.append("observation_dates_unavailable")
    if product.get("date_conflict", False):
        reasons.append("conflicting_observation_dates")
    if not within:
        reasons.append("not_contained_in_event_window")
    if not product.get("vector_or_raster_available", False):
        reasons.append("analysis_extent_asset_unavailable")
    if not product.get("public_derivatives", False):
        reasons.append("public_derivative_rights_unconfirmed")
    if not product.get("source_snapshot_verified", False):
        reasons.append("reviewed_source_snapshot_unavailable_or_changed")
    coverage = None
    if analysis_footprint is None:
        reasons.append("observation_footprint_unavailable")
    else:
        aoi_geom = _polygon(aoi)
        footprint = _polygon(analysis_footprint)
        coverage = min(
            1.0,
            transform(_AREA, aoi_geom.intersection(footprint)).area
            / transform(_AREA, aoi_geom).area,
        )
        if coverage == 0:
            reasons.append("no_observed_aoi_intersection")
    eligible = not reasons
    validation_reasons = list(reasons)
    if not product.get("independent_validation_accepted", False):
        validation_reasons.append("independent_validation_not_accepted")
    if not product.get("validation_use_permitted", False):
        validation_reasons.append("validation_use_rights_unconfirmed")
    return {
        "product_id": product["id"],
        "event_id": event["id"],
        "source_timestamp": product.get("end"),
        "confidence_class": "low",
        "temporal_match": within and not product.get("date_conflict", False),
        "observation_coverage_fraction": coverage,
        "event_context_eligible": eligible,
        "event_context_status": "eligible_for_review" if eligible else "not_admissible",
        "validation_eligible": not validation_reasons,
        "blocking_reasons": reasons,
        "validation_blocking_reasons": validation_reasons,
        "assumptions": [
            "Flood polygons do not establish observation coverage or imply dry land outside their union.",
            "A within-window cumulative product can describe the union across those dates, never a single date or the event peak.",
            "Event context eligibility does not validate detection accuracy or authorize an operational warning.",
        ],
    }


def _verified_snapshot(acquisition: Path, name: str, expected: str) -> bool:
    path = acquisition / name
    return path.is_file() and sha256_file(path) == expected


def _read_boundary_units(archive: Path, aois: dict[str, dict]) -> dict:
    import geopandas as gpd

    with zipfile.ZipFile(archive) as source:
        roots = {n.split("/")[0] for n in source.namelist() if ".gdb/" in n}
    if len(roots) != 1:
        raise ValueError("Boundary archive must contain exactly one file geodatabase")
    uri = "/vsizip/" + archive.resolve().as_posix() + "/" + next(iter(roots))
    features = {}
    for value in aois.values():
        aoi = _polygon(value)
        frame = gpd.read_file(
            uri, layer="tha_admin3", bbox=aoi.bounds, engine="pyogrio"
        )
        if frame.crs is None or frame.crs.to_epsg() != 4326:
            raise ValueError("Reviewed source must provide EPSG:4326 geometries")
        for _, row in frame.iterrows():
            geom = _polygon(mapping(row.geometry))
            if geom.intersection(aoi).area == 0:
                continue
            code = normalize_adm3_code(row["adm3_pcode"])
            if str(row["valid_on"])[:10] != BOUNDARY_SOURCE["source_timestamp"]:
                raise ValueError("Boundary vintage differs from the reviewed source")
            feature = {
                "type": "Feature",
                "id": code,
                "geometry": mapping(geom),
                "properties": {
                    "adm3_pcode": code,
                    "name": row["adm3_name"],
                    "name_th": row["adm3_name1"],
                    "adm2_pcode": row["adm2_pcode"],
                    "adm1_pcode": row["adm1_pcode"],
                    "source_timestamp": BOUNDARY_SOURCE["source_timestamp"],
                    "confidence_class": "low",
                    "role": "reporting_boundary",
                    "attribution": BOUNDARY_SOURCE["attribution"],
                    "license": BOUNDARY_SOURCE["license"],
                    "license_url": BOUNDARY_SOURCE["license_url"],
                },
            }
            if code in features and features[code] != feature:
                raise ValueError(f"Conflicting geometries for {code}")
            features[code] = feature
    return {
        "type": "FeatureCollection",
        "features": [features[k] for k in sorted(features)],
    }


def _review_products(acquisition: Path) -> list[dict]:
    """Versioned source review spec; all build-time inputs are local snapshots."""
    return [
        {
            "id": "unosat_4009_accumulated",
            "event_ids": ["mae_sai_2024"],
            "title": "UNOSAT 4009 accumulated water, August–October 2024",
            "source_url": "https://unosat.org/products/4009",
            "start": "2024-08-01",
            "end": "2024-10-22",
            "date_conflict": True,
            "layer_name_end_date": "2024-10-12",
            "metadata_end_date": "2024-10-22",
            "vector_or_raster_available": True,
            "public_derivatives": False,
            "source_snapshot_verified": True,
            "review_notes": [
                "Layer name ends 12 October; description and Sensor_Date end 22 October. No patch dates support a September-only extraction.",
                "CC BY-SA version remains unresolved. Preliminary product; no independent validation acceptance.",
            ],
        },
        {
            "id": "unosat_4009_oct22",
            "event_ids": ["mae_sai_2024"],
            "title": "UNOSAT 4009 single-date water, 22 October 2024",
            "source_url": "https://unosat.org/products/4009",
            "start": "2024-10-22",
            "end": "2024-10-22",
            "date_conflict": False,
            "vector_or_raster_available": True,
            "public_derivatives": False,
            "source_snapshot_verified": True,
            "review_notes": [
                "October 22 is outside the September event window; a near-empty October mask does not show September was dry.",
                "CC BY-SA version remains unresolved.",
            ],
        },
        {
            "id": "unosat_3991_sep13_19",
            "event_ids": ["mae_sai_2024"],
            "title": "UNOSAT 3991 water extents, 13–19 September 2024",
            "source_url": "https://unosat.org/products/3991",
            "start": "2024-09-13",
            "end": "2024-09-19",
            "date_conflict": False,
            "vector_or_raster_available": False,
            "public_derivatives": False,
            "source_snapshot_verified": _verified_snapshot(
                acquisition,
                "unosat_3991.json",
                "10022d0250530a5e1a68b89df84822b3e1f0b5214d93cc821bced56ba1060262",
            ),
            "review_notes": [
                "Official metadata matches the September event but provides no SHP/KML/GDB download. The map is a citation, not a machine-readable or independently validated extent."
            ],
        },
        {
            "id": "eos_hat_yai_20251123",
            "event_ids": ["hat_yai_2025"],
            "title": "EOS-RS Hat Yai flood proxy, 23 November 2025 v0.9",
            "source_url": "https://sentinel-asia.org/EO/2025/article20251119TH.html",
            "start": "2025-11-23",
            "end": "2025-11-23",
            "date_conflict": False,
            "vector_or_raster_available": (
                acquisition / "hat_yai_eos_20251123_shp.zip"
            ).is_file(),
            "public_derivatives": False,
            "source_snapshot_verified": _verified_snapshot(
                acquisition,
                "hat_yai_eos_20251123_shp.zip",
                "2eba3864e7ac8a1d14d5c97e5c34c74def16542b2d537b10ce9fa34e2ad297ca",
            ),
            "asset": "hat_yai_eos_20251123_shp.zip",
            "asset_sha256": "2eba3864e7ac8a1d14d5c97e5c34c74def16542b2d537b10ce9fa34e2ad297ca",
            "rights_status": "source_specific_terms_unavailable_host_terms_no_modification",
            "rights_url": "https://sentinel-asia.org/sitepolicy/SitePolicy.html",
            "source_legal_url": "https://sft.earthobservatory.sg/faq/",
            "review_notes": [
                "Original ZIP has 9,172 flood-proxy polygons (DN=100), WGS84, and no license or analysis footprint. Do not derive footprint from their union or bounding box.",
                "Map states roughly 30-metre likely flood pixels; lower reliability in urban and vegetated areas. Source preliminary checks use selected news/video imagery, not an independent project validation.",
                "Public map refers to an EOS legal page that failed DNS resolution. Sentinel Asia host terms forbid modification absent other permission; public derivatives remain blocked.",
            ],
        },
    ]


def build_event_review(
    *,
    aoi_dir: Path,
    acquisition_dir: Path,
    output_dir: Path,
    existing_boundary_zip: Path,
    prior_evidence_dir: Path,
    open_data_dir: Path,
) -> dict:
    """Build reporting units and event-source review from reviewed local inputs.

    ``acquisition_dir`` is the event-review acquisition directory; ``output_dir``
    holds generated derivatives. No network request occurs. The archived boundary
    checksum and specific HDX license must match before any geometry is emitted.
    """
    archive_hash = sha256_file(existing_boundary_zip)
    if archive_hash != BOUNDARY_SOURCE["source_sha256"]:
        raise ValueError("Boundary archive checksum is not the reviewed source")
    metadata_path = acquisition_dir / "hdx_cod_ab_metadata.json"
    metadata = _json(metadata_path)["result"]
    if (
        metadata.get("id") != "d24bdc45-eb4c-4e3d-8b16-44db02667c27"
        or metadata.get("license_id") != "cc-by-igo"
        or metadata.get("license_url", "").replace("http://", "https://")
        != BOUNDARY_SOURCE["license_url"]
        or metadata.get("dataset_source") != "Royal Thai Survey Department"
    ):
        raise ValueError(
            "Boundary metadata does not establish the reviewed source and license"
        )
    if not _verified_snapshot(
        acquisition_dir,
        "cc_by_igo_3_legalcode.html",
        BOUNDARY_SOURCE["license_snapshot_sha256"],
    ):
        raise ValueError("The reviewed CC BY 3.0 IGO license snapshot is required")
    loaded_aois = load_aois(aoi_dir)
    aois = {a["id"]: a["geometry"] for a in loaded_aois}
    units = _read_boundary_units(existing_boundary_zip, aois)
    crosswalk = build_reporting_crosswalk(aois, units)
    output_dir.mkdir(parents=True, exist_ok=True)
    unit_path = output_dir / "reporting_units.geojson"
    crosswalk_path = output_dir / "reporting_crosswalk.json"
    _write(unit_path, units)
    _write(crosswalk_path, crosswalk)
    csv_path = output_dir / "reporting_crosswalk.csv"
    columns = [
        "aoi_id",
        "adm3_pcode",
        "name",
        "name_th",
        "adm2_pcode",
        "adm1_pcode",
        "unit_area_km2",
        "intersection_area_km2",
        "unit_coverage_fraction",
        "aoi_share",
        "scope",
        "sub_square_metre_intersection",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for aoi in crosswalk["aois"]:
            writer.writerows({"aoi_id": aoi["aoi_id"], **unit} for unit in aoi["units"])
    input_hashes = {
        "boundary_archive": archive_hash,
        "boundary_metadata": sha256_file(metadata_path),
        "boundary_license": sha256_file(acquisition_dir / "cc_by_igo_3_legalcode.html"),
    }
    for path in sorted(aoi_dir.glob("*.geojson")):
        input_hashes["aoi/" + path.name] = sha256_file(path)
    products = _review_products(acquisition_dir)
    event_rows = []
    events = {event["id"]: event for event in EVENTS}
    for aoi in loaded_aois:
        for event_id in aoi["event_ids"]:
            candidates = [p for p in products if event_id in p["event_ids"]]
            if not candidates:
                event_rows.append(
                    {
                        "aoi_id": aoi["id"],
                        "event_id": event_id,
                        "product_id": None,
                        "event_context_eligible": False,
                        "validation_eligible": False,
                        "event_context_status": "source_not_acquired",
                        "observation_coverage_fraction": None,
                        "source_timestamp": None,
                        "confidence_class": "low",
                        "blocking_reasons": ["no_reviewed_event_extent_asset"],
                        "assumptions": [
                            "The bounded official HDX/UNOSAT search did not yield an acquired, admissible extent for this AOI/event; this is not evidence of no flood."
                        ],
                    }
                )
            for product in candidates:
                footprint = None
                reviewed = dict(product)
                if product["id"].startswith("unosat_4009"):
                    normal = prior_evidence_dir / "normalized"
                    category = (
                        "accumulated_extent"
                        if product["id"].endswith("accumulated")
                        else "single_date_extent"
                    )
                    extent_path = normal / f"flood_{aoi['id']}_{category}.geojson"
                    footprint_path = (
                        normal / f"flood_{aoi['id']}_analysis_footprint.geojson"
                    )
                    reviewed["vector_or_raster_available"] = extent_path.is_file()
                    reviewed["source_snapshot_verified"] = (
                        extent_path.is_file() and footprint_path.is_file()
                    )
                    if footprint_path.is_file():
                        footprint = _json(footprint_path)
                        input_hashes["prior/" + footprint_path.name] = sha256_file(
                            footprint_path
                        )
                    if extent_path.is_file():
                        input_hashes["prior/" + extent_path.name] = sha256_file(
                            extent_path
                        )
                result = assess_event_evidence(
                    events[event_id],
                    reviewed,
                    aoi["geometry"],
                    analysis_footprint=footprint,
                )
                event_rows.append({"aoi_id": aoi["id"], **result})
    for path in sorted(acquisition_dir.iterdir()):
        if path.is_file():
            input_hashes["acquisition/" + path.name] = sha256_file(path)
    # Bind the original acquisition README if present; the review never edits or
    # promotes its date conflict, rights decision or field-validation status.
    original_readme = open_data_dir / "flood_reference" / "README.md"
    if original_readme.is_file():
        input_hashes["original_flood_readme"] = sha256_file(original_readme)
    review = {
        "schema_version": "1.0",
        "review_version": REVIEW_VERSION,
        "source_timestamp": None,
        "confidence_class": "low",
        "products": products,
        "aois": event_rows,
        "event_context_eligible_count": sum(
            r["event_context_eligible"] for r in event_rows
        ),
        "validation_eligible_count": sum(r["validation_eligible"] for r in event_rows),
        "assumptions": [
            "Publicly accessible products are citation/context candidates until dates, observation footprint, use rights and independent evidence are established. No scoring or label gate is upgraded by this review."
        ],
    }
    review_path = output_dir / "event_evidence_review.json"
    _write(review_path, review)
    summary = {
        "schema_version": "1.0",
        "review_version": REVIEW_VERSION,
        "source_timestamp": BOUNDARY_SOURCE["source_timestamp"],
        "confidence_class": "low",
        "boundary_source": dict(BOUNDARY_SOURCE),
        "input_hashes": input_hashes,
        "reporting_units": {
            "path": unit_path.name,
            "count": len(units["features"]),
            "sha256": sha256_file(unit_path),
        },
        "crosswalk": {
            "path": crosswalk_path.name,
            "csv_path": csv_path.name,
            "sha256": sha256_file(crosswalk_path),
            "aois": crosswalk["aois"],
        },
        "event_evidence": {
            "path": review_path.name,
            "sha256": sha256_file(review_path),
            "eligible_count": review["event_context_eligible_count"],
            "validation_eligible_count": review["validation_eligible_count"],
        },
        "assumptions": crosswalk["assumptions"] + review["assumptions"],
    }
    _write(output_dir / "summary.json", summary)
    return summary
