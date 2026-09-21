"""Bounded, reproducible checks of published public acquisition routes.

An HTTP success is not a license or a qualified flood reference. Downloads stay
outside the public export and every route has an explicit analytical fallback.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROUTES = [
    (
        "mae-sai-september-reference",
        "mae_sai_2024",
        "https://unosat.org/our_products/3991",
        "Citation-only preliminary publication; cumulative October product remains historical context.",
    ),
    (
        "hii-september-listing",
        "mae_sai_2024",
        "https://tiservice.hii.or.th/opendata/data_catalog/water_level/2024/202409/",
        "No local Mae Sai hydrograph without the station/event file.",
    ),
    (
        "hii-mya004",
        "mae_sai_2024",
        "https://tiservice.hii.or.th/opendata/data_catalog/water_level/2024/202409/MYA004.csv",
        "Retain missing station/event observations.",
    ),
    (
        "dopa-2024",
        "all",
        "https://stat.bora.dopa.go.th/new_stat/webPage/statByProvince.php?year=67",
        "District/province observed context; 2024 Chiang Rai ages remain missing unless a usable table is recovered.",
    ),
    (
        "moph-public-register",
        "all",
        "https://hcode.moph.go.th/static/hcode/csv/health_office.csv",
        "Public identity register only; current identity cannot establish historical activation or service availability.",
    ),
    (
        "drr-road-records",
        "all",
        "https://dataportal.drr.go.th/dataset/187480f0-45e9-433f-9964-909cab4f5289/resource/a87bcef5-c3c6-4c0b-b86b-5fc2f1934277/download/flood.json",
        "Documentary incidents and explicit closure scenarios; no inferred passability.",
    ),
    (
        "ngis-drainage",
        "all",
        "https://ngis.go.th/arcgis/rest/services/Hosted?f=pjson",
        "Generalized HydroRIVERS only; no local culvert/levee or urban-drain claim.",
    ),
    (
        "gistda-public-catalog",
        "all",
        "https://data.gistda.or.th/api/3/action/package_search?q=flood&rows=5",
        "Existing published cumulative context or explicit scenarios; no private export dependency.",
    ),
    (
        "hat-yai-pre-safe",
        "hat_yai_2025",
        "https://catalogue.dataspace.copernicus.eu/odata/v1/Products(4e473302-943c-4798-8bfc-8287167792ed)?$expand=Attributes",
        "Explicit scenario if compatible original SAFE assets cannot be acquired and integrity checked.",
    ),
    (
        "hat-yai-post-safe",
        "hat_yai_2025",
        "https://catalogue.dataspace.copernicus.eu/odata/v1/Products(d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc)?$expand=Attributes",
        "Metadata availability alone does not establish local SAFE availability or a candidate flood layer.",
    ),
]


def check_public_routes(output_dir: Path, *, timeout: float = 20) -> dict:
    """Save public responses and a sanitized gap register, with at most one retry."""
    import requests

    output_dir.mkdir(parents=True, exist_ok=True)

    def check(route: tuple) -> dict:
        identifier, event, url, fallback = route
        record = {
            "id": identifier,
            "event": event,
            "url": url,
            "fallback": fallback,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "attempts": 0,
            "asset": None,
            "sha256": None,
            "terms": "No additional permission inferred from public access.",
            "qualified_for_validation": False,
            "http_status": None,
        }
        for attempt in range(2):
            record["attempts"] += 1
            try:
                response = requests.get(
                    url,
                    timeout=(min(timeout, 10), timeout),
                    headers={
                        "User-Agent": "FloodGuard-research/1.0 public-source-check"
                    },
                )
                record["http_status"] = response.status_code
                if response.status_code >= 500 and attempt == 0:
                    continue
                record["access"] = (
                    "downloaded_public_response"
                    if response.ok
                    else "authentication_required"
                    if response.status_code == 401
                    else "access_forbidden_reason_unconfirmed"
                    if response.status_code == 403
                    else "absent"
                    if response.status_code == 404
                    else "http_failure"
                )
                record["content_type"] = response.headers.get("Content-Type", "")
                if response.ok:
                    suffix = (
                        ".csv"
                        if ".csv" in url
                        else ".json"
                        if "json" in record["content_type"]
                        else ".html"
                    )
                    name = identifier + suffix
                    (output_dir / name).write_bytes(response.content)
                    record.update(
                        asset=name,
                        sha256=hashlib.sha256(response.content).hexdigest(),
                        bytes=len(response.content),
                    )
                    record["suitability"] = (
                        "unreviewed_public_response_not_an_accepted_dataset"
                    )
                    if (
                        b"Incapsula" in response.content
                        or b"Request unsuccessful" in response.content
                    ):
                        record["access"] = "blocked_access_response"
                return record
            except requests.RequestException as error:
                record["access"] = "access_failed"
                record["error_type"] = type(error).__name__
                if isinstance(error, requests.exceptions.SSLError):
                    break  # Do not bypass certificate checks.
        return record

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(check, ROUTES))
    report = {"schema_version": "1.0", "no_private_requests": True, "routes": results}
    (output_dir / "gap_register.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def review_public_responses(
    output_dir: str | Path, aoi_geometries: dict | list | None = None
) -> dict:
    """Interpret saved HTTP responses without mistaking metadata for data.

    This review is offline. It never assumes a 403 means an account is required,
    treats provider JSON errors as failures, and keeps original SAFE availability
    separate from catalogue compatibility.
    """
    from floodguard.evidence_adapters import _aoi_map, _read_json

    output_dir = Path(output_dir)
    report = _read_json(
        output_dir / "gap_register.json", {"schema_version": "1.0", "routes": []}
    )
    aois = _aoi_map(aoi_geometries or {})
    pair = []
    for record in report["routes"]:
        record["qualified_for_validation"] = False
        if record.get("http_status") == 403:
            record["access"] = "access_forbidden_reason_unconfirmed"
        name = record.get("asset")
        content = (
            (output_dir / name).read_bytes()
            if name and (output_dir / name).exists()
            else b""
        )
        try:
            doc = json.loads(content) if content else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            doc = None
        record["usable_dataset_acquired"] = False
        if isinstance(doc, dict) and doc.get("error"):
            record.update(
                suitability="provider_error_response", provider_error=doc["error"]
            )
            continue
        identifier = record["id"]
        if identifier == "mae-sai-september-reference" and isinstance(doc, dict):
            event = doc.get("map_event", {})
            vectors = [
                event.get(key)
                for key in ("shp_link", "kml_link", "wms_link", "wmap_link", "gdp_link")
                if event.get(key)
            ]
            record.update(
                suitability="publication_metadata_only"
                if not vectors
                else "published_vector_links_require_acquisition_review",
                published_vector_links=vectors,
                product_id=event.get("id"),
                published_date=event.get("created_at"),
                interval="2024-09-13/2024-09-19",
                independent_reference_status="unresolved_no_acquired_vector_or_specific_reuse_terms",
            )
        elif identifier == "hii-september-listing" and content:
            record.update(
                suitability="archive_listing_only", mya004_listed=b"MYA004" in content
            )
        elif identifier == "hii-mya004":
            record["suitability"] = (
                "station_month_absent"
                if record.get("http_status") == 404
                else "not_acquired"
            )
        elif identifier == "ngis-drainage" and isinstance(doc, dict):
            selected = [
                s
                for s in doc.get("services", [])
                if any(
                    word in s.get("name", "")
                    for word in ("NAT_STREAM_DWR", "NAT_WTR_BODY_DWR", "BASIN_DWR")
                )
            ]
            record.update(
                suitability="public_service_directory_not_feature_data",
                available_context_services=selected,
                fine_drainage_status="culverts_levees_urban_drain_capacity_not_established",
            )
            acquisition = _read_json(
                output_dir / "ngis" / "context_manifest.json", None
            )
            if acquisition:
                record["bounded_context_acquisition"] = {
                    key: acquisition[key]
                    for key in (
                        "status",
                        "files",
                        "feature_count_across_overlapping_aois",
                        "complete_responses",
                    )
                }
                record["usable_dataset_acquired"] = any(
                    r.get("status") == "downloaded_context_candidate"
                    and r.get("feature_count", 0)
                    for r in acquisition["records"]
                )
                record["suitability"] = (
                    "local_context_vectors_acquired_reuse_and_epoch_unresolved"
                    if record["usable_dataset_acquired"]
                    else record["suitability"]
                )
        elif identifier.startswith("hat-yai-") and isinstance(doc, dict):
            attributes = {a["Name"]: a.get("Value") for a in doc.get("Attributes", [])}
            product = {
                "id": doc.get("Id"),
                "name": doc.get("Name"),
                "online_catalogue": doc.get("Online"),
                "relative_orbit": attributes.get("relativeOrbitNumber"),
                "orbit_direction": attributes.get("orbitDirection"),
                "polarisation": attributes.get("polarisationChannels"),
                "platform": attributes.get("platformSerialIdentifier"),
                "processing_level": attributes.get("processingLevel"),
                "source_time_utc": doc.get("ContentDate", {}).get("Start"),
                "content_length_bytes": doc.get("ContentLength"),
                "original_archive_acquired_by_this_check": False,
                "download_access": "existing_CDSE_downloader_requires_authorized_account_credentials",
                "aoi_coverage": {},
            }
            if aois and doc.get("GeoFootprint"):
                try:
                    from pyproj import Transformer
                    from shapely.geometry import shape
                    from shapely.ops import transform, unary_union

                    project = Transformer.from_crs(
                        4326, 32647, always_xy=True
                    ).transform
                    footprint = shape(doc["GeoFootprint"])
                    for aoi, value in aois.items():
                        if aoi not in {"aoi-03_hat_yai_core", "aoi-04_hat_yai_basin"}:
                            continue
                        geom = (
                            unary_union(
                                [shape(f["geometry"]) for f in value["features"]]
                            )
                            if value.get("type") == "FeatureCollection"
                            else shape(value.get("geometry", value))
                        )
                        area = transform(project, geom).area
                        product["aoi_coverage"][aoi] = (
                            min(
                                1.0,
                                max(
                                    0.0,
                                    transform(
                                        project, geom.intersection(footprint)
                                    ).area
                                    / area,
                                ),
                            )
                            if area
                            else None
                        )
                except ImportError:
                    product["coverage_check"] = "optional_geo_dependencies_unavailable"
            pair.append(product)
            record.update(
                suitability="online_product_metadata_not_original_SAFE",
                product_review=product,
            )
        elif identifier == "moph-public-register":
            review = _read_json(
                output_dir.parent / "facility_review" / "facility_identity_review.json",
                {},
            )
            record.update(
                suitability="bulk_register_not_acquired",
                public_page_identity_matches=review.get(
                    "supported_identity_matches", 0
                ),
                historical_operation_or_capacity_verified=False,
                alternative_route="Public MOPH hcode detail pages inspected for names and addresses; HTTP-client snapshots may remain forbidden",
            )
        elif not content:
            record.setdefault("suitability", "not_acquired_keep_gap_explicit")
        record["qualified_for_validation"] = False
    if pair:
        compatible = (
            len(pair) == 2
            and len(
                {
                    (
                        p["relative_orbit"],
                        p["orbit_direction"],
                        p["polarisation"],
                        p["platform"],
                    )
                    for p in pair
                }
            )
            == 1
            and all(
                all(
                    p[k] is not None
                    for k in (
                        "relative_orbit",
                        "orbit_direction",
                        "polarisation",
                        "platform",
                    )
                )
                for p in pair
            )
        )
        report["hat_yai_pair_review"] = {
            "products": pair,
            "same_track_platform_polarisation": compatible,
            "status": "compatible_metadata_only"
            if compatible
            else "metadata_incomplete_or_incompatible",
            "qualified_reference": False,
        }
    report["response_review_completed"] = True
    (output_dir / "gap_register.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def acquire_ngis_context(
    output_dir: str | Path,
    aoi_geometries: dict | list,
    *,
    timeout: float = 20,
    max_features: int = 2000,
) -> dict:
    """Fetch two published DWR context layers, bounded to supplied AOI envelopes.

    One count and one bounded feature query per layer/AOI establish whether the
    response is complete. Incomplete results are retained and labelled partial.
    Geometry is not clipped, historical currency/reuse remains unresolved, and
    OSM-derived hospital POIs are deliberately excluded.
    """
    import requests
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from floodguard.evidence_adapters import _aoi_map

    output_dir = Path(output_dir) / "ngis"
    output_dir.mkdir(parents=True, exist_ok=True)
    aois = _aoi_map(aoi_geometries)
    services = {
        "NAT_STREAM_DWR": "fid,str_id,local_nam,str_type,str_name_t,str_name_e,typ_t,typ_e,namet,type_t,type_e",
        "NAT_WTR_BODY_DWR": "fid,wtr_code,wtr_name,wtr_type,tambon,amphoe,province,nat_wb_id,wb_name_t,wb_name_e,wb_type",
    }
    if not 1 <= max_features <= 2000:
        raise ValueError("NGIS acquisition bound must be between 1 and 2000 features")
    jobs = []
    for aoi, value in aois.items():
        geom = (
            unary_union([shape(f["geometry"]) for f in value["features"]])
            if value.get("type") == "FeatureCollection"
            else shape(value.get("geometry", value))
        )
        for service, fields in services.items():
            jobs.append((aoi, geom.bounds, service, fields))

    def fetch(job: tuple) -> dict:
        aoi, bounds, service, fields = job
        url = f"https://ngis.go.th/arcgis/rest/services/Hosted/{service}/FeatureServer/0/query"
        record = {
            "service": service,
            "aoi_id": aoi,
            "source_url": url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "role": "static_context_candidate",
            "source_epoch": None,
            "license": "unresolved_in_service_metadata",
            "public_redistribution_accepted": False,
            "qualified_for_validation": False,
            "assumptions": "AOI_envelope_intersection_full_features_not_clips;not_event_water;not_complete_urban_drainage;overlapping_AOIs_not_independent",
        }
        params = {
            "where": "1=1",
            "geometry": ",".join(str(x) for x in bounds),
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
        }
        try:
            response = requests.get(
                url, params={**params, "returnCountOnly": "true"}, timeout=timeout
            )
            response.raise_for_status()
            counts = response.json()
            if "error" in counts or "count" not in counts:
                record.update(
                    status="provider_error", error=counts.get("error", "missing count")
                )
                return record
            count_name = f"{aoi}_{service}_count.json"
            (output_dir / count_name).write_bytes(response.content)
            record.update(
                count_file=count_name,
                count_sha256=hashlib.sha256(response.content).hexdigest(),
                expected_features=counts["count"],
            )
            query = {
                **params,
                "f": "geojson",
                "outFields": fields,
                "outSR": 4326,
                "returnGeometry": "true",
                "resultRecordCount": max_features,
                "orderByFields": "fid ASC",
            }
            response = requests.get(url, params=query, timeout=timeout)
            response.raise_for_status()
            doc = response.json()
            if doc.get("type") != "FeatureCollection" or "features" not in doc:
                record.update(
                    status="not_feature_data", error=doc.get("error", "not GeoJSON")
                )
                return record
            filename = f"{aoi}_{service}.geojson"
            (output_dir / filename).write_bytes(response.content)
            geometries = [
                shape(f["geometry"]) for f in doc["features"] if f.get("geometry")
            ]
            complete = len(doc["features"]) == counts["count"] and not doc.get(
                "exceededTransferLimit", False
            )
            record.update(
                status="downloaded_context_candidate",
                query_url=response.url,
                file=filename,
                sha256=hashlib.sha256(response.content).hexdigest(),
                bytes=len(response.content),
                feature_count=len(doc["features"]),
                complete_response=complete,
                invalid_geometries=sum(not g.is_valid for g in geometries),
                missing_geometry_records=len(doc["features"]) - len(geometries),
            )
        except (requests.RequestException, ValueError) as error:
            record.update(status="acquisition_failed", error_type=type(error).__name__)
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, jobs))
    metadata_files = [
        {
            "file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for p in sorted(output_dir.glob("*_service.json"))
    ] + [
        {
            "file": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for p in sorted(output_dir.glob("*_layer.json"))
    ]
    report = {
        "status": "bounded_context_acquisition_complete",
        "records": records,
        "metadata_files": metadata_files,
        "files": sum("file" in r for r in records),
        "feature_count_across_overlapping_aois": sum(
            r.get("feature_count", 0) for r in records
        ),
        "complete_responses": sum(r.get("complete_response", False) for r in records),
        "exclusions": [
            "NGIS hospital_POI contains osm_id; OSM excluded as requested",
            "No culvert, levee or urban-drain capacity inference",
        ],
    }
    (output_dir / "context_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report
