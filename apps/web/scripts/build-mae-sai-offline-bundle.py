"""Build the compact, provenance-bound Mae Sai command-map bundle.

The source files are committed FloodGuard derivatives. This script never reads
raw Sentinel products or private workspaces and writes only browser-safe JSON.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS = REPOSITORY_ROOT / "outputs"
TARGET = REPOSITORY_ROOT / "apps" / "web" / "public" / "offline-demo" / "mae-sai"
SOURCE_COMMIT = "7e42882efb7cb7dc40b7c1cdd4c3fa960569b95f"
DATA_VERSION = "mae-sai-candidate-2024-09-15-v1"
GENERATED_AT = "2026-07-18T00:00:00Z"
SOURCE_TIMESTAMP = "2024-09-15T23:16:01Z"
EXPECTED_BOUNDS = [99.80, 20.24, 100.05, 20.48]

INPUTS = {
    "priority_areas": OUTPUTS / "mae_sai_priority_subdistricts.geojson",
    "road_risk": OUTPUTS / "mae_sai_road_risk.geojson",
    "facilities": OUTPUTS / "mae_sai_facilities.geojson",
    "access_hotspots": OUTPUTS / "mae_sai_access_hotspots.geojson",
}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round_coordinates(value: Any, digits: int) -> Any:
    if isinstance(value, list):
        return [_round_coordinates(item, digits) for item in value]
    if isinstance(value, tuple):
        return [_round_coordinates(item, digits) for item in value]
    if isinstance(value, float):
        return round(value, digits)
    return value


def _compact_geometry(geometry: dict[str, Any], tolerance: float, digits: int) -> dict[str, Any]:
    candidate = shape(geometry)
    if tolerance:
        candidate = candidate.simplify(tolerance, preserve_topology=True)
    if candidate.is_empty or not candidate.is_valid:
        raise ValueError("Geometry became empty or invalid during browser compaction.")
    encoded = mapping(candidate)
    geometry_type = encoded["type"]
    coordinates = encoded["coordinates"]
    if geometry["type"] == "MultiPolygon" and geometry_type == "Polygon":
        geometry_type = "MultiPolygon"
        coordinates = [coordinates]
    return {
        "type": geometry_type,
        "coordinates": _round_coordinates(coordinates, digits),
    }


def _common(*, confidence: str, source_name: str, assumptions: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "source_timestamp": SOURCE_TIMESTAMP,
        "generated_at": GENERATED_AT,
        "confidence_class": confidence,
        "source_name": source_name,
        "assumptions": assumptions,
        "official_warning": False,
        "data_version": DATA_VERSION,
        "git_commit": SOURCE_COMMIT,
    }


def _as_assumptions(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None or not str(value).strip():
        return []
    return [str(value)]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any) -> int:
    return int(round(_number(value)))


def _build_areas(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for source_feature in source["features"]:
        properties = source_feature["properties"]
        area_id = str(properties["subdistrict_id"])
        action_class = str(properties["action_class"])
        confidence = str(properties["confidence_class"])
        assumptions = _as_assumptions(properties.get("assumptions"))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "area_id": area_id,
                    "area_name_en": str(properties["subdistrict_name"]),
                    "area_name_th": str(properties["subdistrict_name_th"]),
                    "action_class": action_class,
                    "fpps_0_100": _number(properties["fpps_0_100"]),
                    "confidence_class": confidence,
                    "candidate_status": "provenance_tracked_candidate_analysis",
                },
                "geometry": _compact_geometry(source_feature["geometry"], 0.00001, 5),
            }
        )
        baseline = {
            "people_losing_30_min_access": _integer(properties.get("people_losing_30_min_access")),
            "equity_gap_ratio": None
            if properties.get("equity_gap_ratio") in (None, "")
            else _number(properties.get("equity_gap_ratio")),
            "delta": 0,
        }
        record = {
            **_common(
                confidence=confidence,
                source_name=str(properties["source_name"]),
                assumptions=assumptions,
            ),
            "area_id": area_id,
            "area_name_th": str(properties["subdistrict_name_th"]),
            "area_name_en": str(properties["subdistrict_name"]),
            "fpps_0_100": _number(properties["fpps_0_100"]),
            "action_class": action_class,
            "top_reason": str(properties["top_reason"]),
            "flood_likelihood_0_100": _number(properties["flood_likelihood_0_100"]),
            "exposure_0_100": _number(properties["exposure_0_100"]),
            "access_gap_0_100": _number(properties["access_gap_0_100"]),
            "road_criticality_0_100": _number(properties["road_criticality_0_100"]),
            "vulnerability_context_0_100": _number(properties["vulnerability_context_0_100"]),
            "total_population": _integer(properties["total_population"]),
            "people_losing_30_min_access": baseline["people_losing_30_min_access"],
            "equity_gap_ratio": baseline["equity_gap_ratio"],
            "scenario_results": {
                "baseline": baseline,
                "add_temporary_shelter": baseline,
                "close_road": baseline,
            },
            "candidate_evidence": {
                "mean_flood_probability_0_1": _number(properties.get("mean_flood_probability_0_1")),
                "p90_flood_probability_0_1": _number(properties.get("p90_flood_probability_0_1")),
                "binary_flood_share_0_1": _number(properties.get("binary_flood_share_0_1")),
                "facility_count": _integer(properties.get("facility_count")),
                "road_count": _integer(properties.get("road_count")),
                "bridge_count": _integer(properties.get("bridge_count")),
                "worldpop_bbox_coverage_rate": _number(properties.get("worldpop_bbox_coverage_rate")),
                "road_snap_population_coverage_rate": _number(properties.get("road_snap_population_coverage_rate")),
                "dem_population_coverage_rate": _number(properties.get("dem_population_coverage_rate")),
                "boundary_version": str(properties.get("boundary_version", "unknown")),
                "boundary_valid_on": str(properties.get("boundary_valid_on", "unknown")),
                "reference_status": str(properties.get("reference_status", "unqualified")),
                "processing_scope": str(properties.get("processing_scope", "candidate_analysis")),
            },
        }
        records.append(record)
    if len(features) != 8 or len({item["properties"]["area_id"] for item in features}) != 8:
        raise ValueError("Mae Sai browser bundle requires exactly eight unique reporting areas.")
    return {"type": "FeatureCollection", "name": "mae_sai_candidate_priority_areas", "features": features}, records


def _build_roads(source: dict[str, Any], valid_area_ids: set[str]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for source_feature in source["features"]:
        properties = source_feature["properties"]
        area_id = str(properties["subdistrict_id"])
        if area_id not in valid_area_ids:
            raise ValueError(f"Road references unknown reporting area {area_id}.")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "road_id": str(properties["road_id"]),
                    "area_id": area_id,
                    "road_name": str(properties.get("road_name") or ""),
                    "road_class": str(properties.get("road_class") or "unknown"),
                    "osm_highway": str(properties.get("osm_highway") or "unknown"),
                    "bridge_flag": bool(properties.get("bridge_flag")),
                    "road_disruption_probability_0_1": _number(properties.get("road_disruption_probability_0_1")),
                    "candidate_status": str(properties.get("candidate_status") or "candidate"),
                    "confidence_class": str(properties.get("confidence_class") or "low"),
                    "warning_text": str(properties.get("warning_text") or "Modelled candidate risk; not an observed closure."),
                },
                "geometry": _compact_geometry(source_feature["geometry"], 0.000015, 5),
            }
        )
    if len(features) != 4458:
        raise ValueError(f"Expected 4,458 Mae Sai roads, found {len(features)}.")
    return {"type": "FeatureCollection", "name": "mae_sai_candidate_road_risk", "features": features}


def _build_facilities(source: dict[str, Any], valid_area_ids: set[str]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for source_feature in source["features"]:
        properties = source_feature["properties"]
        area_id = str(properties["subdistrict_id"])
        if area_id not in valid_area_ids:
            raise ValueError(f"Facility references unknown reporting area {area_id}.")
        if properties.get("candidate_status") != "unverified_osm_candidate":
            raise ValueError("Candidate facility was unexpectedly promoted during browser-bundle generation.")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "facility_id": str(properties["facility_id"]),
                    "area_id": area_id,
                    "facility_name": str(properties.get("facility_name") or "Unnamed OSM feature"),
                    "facility_type": str(properties.get("facility_type") or "facility_candidate"),
                    "amenity": str(properties.get("amenity") or "unknown"),
                    "verification_status": "open_context_candidate",
                    "emergency_role": "no_confirmed_emergency_role",
                    "candidate_status": "unverified_osm_candidate",
                    "confidence_class": "low",
                    "source_name": str(properties.get("source_name") or "OpenStreetMap Thailand via Geofabrik"),
                    "source_timestamp": str(properties.get("source_timestamp") or "unknown"),
                    "warning_text": "Open-context facility candidate — emergency role and current operation unverified.",
                },
                "geometry": _compact_geometry(source_feature["geometry"], 0, 6),
            }
        )
    if len(features) != 42:
        raise ValueError(f"Expected 42 Mae Sai facility candidates, found {len(features)}.")
    return {"type": "FeatureCollection", "name": "mae_sai_open_context_facilities", "features": features}


def _build_access(source: dict[str, Any], valid_area_ids: set[str]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for source_feature in source["features"]:
        properties = source_feature["properties"]
        area_id = str(properties["subdistrict_id"])
        if area_id not in valid_area_ids:
            raise ValueError(f"Access hotspot references unknown reporting area {area_id}.")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "area_id": area_id,
                    "area_name_en": str(properties["subdistrict_name"]),
                    "people_losing_15_min_access": _integer(properties.get("people_losing_15_min_access")),
                    "people_losing_30_min_access": _integer(properties.get("people_losing_30_min_access")),
                    "people_losing_60_min_access": _integer(properties.get("people_losing_60_min_access")),
                    "equity_gap_ratio": None if properties.get("equity_gap_ratio") is None else _number(properties.get("equity_gap_ratio")),
                    "candidate_status": str(properties.get("candidate_status") or "candidate"),
                    "confidence_class": "low",
                    "warning_text": "Modeled access-loss candidate only. Not an observed service outage.",
                },
                "geometry": _compact_geometry(source_feature["geometry"], 0, 6),
            }
        )
    if len(features) != 8:
        raise ValueError(f"Expected eight Mae Sai access hotspots, found {len(features)}.")
    return {"type": "FeatureCollection", "name": "mae_sai_modeled_access_hotspots", "features": features}


def _layer(layer_id: str, title_th: str, title_en: str, url: str, source_name: str, assumptions: list[str], attribution: list[str]) -> dict[str, Any]:
    return {
        **_common(confidence="low", source_name=source_name, assumptions=assumptions),
        "layer_id": layer_id,
        "title_th": title_th,
        "title_en": title_en,
        "role_visibility": ["command", "studio"],
        "format": "geojson",
        "url": url,
        "data_state": "ready",
        "model_run_id": None,
        "attribution": attribution,
    }


def _build_bundle(records: list[dict[str, Any]]) -> dict[str, Any]:
    fixture = _load(REPOSITORY_ROOT / "apps" / "web" / "public" / "offline-demo" / "bundle.json")
    status = {
        **_common(
            confidence="low",
            source_name="FloodGuard Mae Sai provenance-tracked candidate context",
            assumptions=[
                "Open context combines HDX COD-AB, OpenStreetMap/Geofabrik, WorldPop, Copernicus DEM, and a Sentinel-1 candidate summary.",
                "Facility roles, road conditions, reference masks, and model accuracy are not agency verified.",
                "Candidate analysis is non-operational and is not an official warning.",
            ],
        ),
        "study_area": "mae_sai_candidate_v1",
        "message_th": "ข้อมูลผู้สมัครแม่สายเพื่อการวางแผน ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ",
        "message_en": "Mae Sai planning candidate; not an official warning.",
        "data_state": "ready",
    }
    layers = [
        _layer("priority_areas", "พื้นที่รายงานแม่สาย", "Mae Sai reporting areas", "/offline-demo/mae-sai/areas.json", "HDX COD-AB and FloodGuard candidate decision artifacts", ["Eight ADM3 reporting units; candidate FPPS values remain low confidence."], ["HDX COD-AB", "FloodGuard"]),
        _layer("road_risk", "ความเสี่ยงถนนเชิงแบบจำลอง", "Modelled road risk", "/offline-demo/mae-sai/roads.json", "OpenStreetMap Thailand via Geofabrik and FloodGuard", ["Area-summary candidate risk; not a segment-level flood-raster intersection and not an observed closure."], ["© OpenStreetMap contributors", "Geofabrik", "FloodGuard"]),
        _layer("facilities", "สถานที่ผู้สมัครจากข้อมูลเปิด", "Open-context facility candidates", "/offline-demo/mae-sai/facilities.json", "OpenStreetMap Thailand via Geofabrik", ["Emergency role, operation, capacity, and accessibility are unverified."], ["© OpenStreetMap contributors", "Geofabrik"]),
        _layer("access_hotspots", "จุดหลักฐานการเข้าถึงเชิงแบบจำลอง", "Modelled access evidence", "/offline-demo/mae-sai/access-hotspots.json", "FloodGuard nearest-facility shortest-path threshold analysis", ["Uses unverified OSM facility candidates and heuristic road delay; not capacity-aware 2SFCA."], ["FloodGuard", "© OpenStreetMap contributors"]),
    ]
    return {
        "status": status,
        "areas": records,
        "layers": layers,
        "readiness": [
            {"check_id": "real_open_context", "source": "Mae Sai derived context manifest", "status": "ready", "severity": "high", "reason_blocked": ""},
            {"check_id": "facility_verification", "source": "OSM facility candidates", "status": "blocked", "severity": "critical", "reason_blocked": "Emergency role, operation, capacity, and accessibility are not agency verified."},
            {"check_id": "segment_raster_intersection", "source": "Mae Sai candidate road risk", "status": "blocked", "severity": "high", "reason_blocked": "Current road risk inherits an ADM3 candidate summary; segment-level probability intersection is not yet accepted."},
            {"check_id": "reference_mask", "source": "Mae Sai weak reference", "status": "blocked", "severity": "critical", "reason_blocked": "The available weak reference is not qualified Thailand event-flood validation truth."},
            {"check_id": "reviewer_calibration", "source": "Governed label factory", "status": "blocked", "severity": "critical", "reason_blocked": "No passing blind reviewer-calibration and adjudication receipt exists."},
        ],
        "model_runs": [],
        "hotlines": fixture["hotlines"],
        "shelters": [],
        "error_categories": [
            {"category": "facility_role_unverified", "status": "not_evaluated", "note": "OSM facility tags are discovery context, not emergency designation."},
            {"category": "segment_raster_intersection_missing", "status": "not_evaluated", "note": "Current road risk is a candidate area-summary heuristic."},
            {"category": "reference_mask_unqualified", "status": "not_evaluated", "note": "Qualified spatial evaluation remains blocked."},
        ],
        "pilot_readiness": {
            **fixture["pilot_readiness"],
            "reason_blocked_th": "ข้อมูลผู้สมัครแม่สายยังไม่มีใบรับรองการยอมรับและการตรวจสอบภาคสนาม",
            "reason_blocked_en": "Mae Sai candidate data has no signed acceptance or field-validation receipt.",
        },
    }


def _bounds(collections: list[dict[str, Any]]) -> list[float]:
    geometries = [shape(feature["geometry"]) for collection in collections for feature in collection["features"]]
    return [
        round(min(geometry.bounds[0] for geometry in geometries), 6),
        round(min(geometry.bounds[1] for geometry in geometries), 6),
        round(max(geometry.bounds[2] for geometry in geometries), 6),
        round(max(geometry.bounds[3] for geometry in geometries), 6),
    ]


def _write(name: str, value: dict[str, Any]) -> Path:
    TARGET.mkdir(parents=True, exist_ok=True)
    destination = TARGET / name
    destination.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination


def main() -> None:
    sources = {key: _load(path) for key, path in INPUTS.items()}
    areas, records = _build_areas(sources["priority_areas"])
    valid_area_ids = {str(feature["properties"]["area_id"]) for feature in areas["features"]}
    roads = _build_roads(sources["road_risk"], valid_area_ids)
    facilities = _build_facilities(sources["facilities"], valid_area_ids)
    access = _build_access(sources["access_hotspots"], valid_area_ids)
    collections = {
        "priority_areas": ("areas.json", areas),
        "road_risk": ("roads.json", roads),
        "facilities": ("facilities.json", facilities),
        "access_hotspots": ("access-hotspots.json", access),
    }
    written = {layer_id: _write(file_name, collection) for layer_id, (file_name, collection) in collections.items()}
    bundle_path = _write("bundle.json", _build_bundle(records))
    actual_bounds = _bounds([areas, roads, facilities, access])
    if not (
        EXPECTED_BOUNDS[0] <= actual_bounds[0] <= EXPECTED_BOUNDS[2]
        and EXPECTED_BOUNDS[1] <= actual_bounds[1] <= EXPECTED_BOUNDS[3]
        and EXPECTED_BOUNDS[0] <= actual_bounds[2] <= EXPECTED_BOUNDS[2]
        and EXPECTED_BOUNDS[1] <= actual_bounds[3] <= EXPECTED_BOUNDS[3]
    ):
        raise ValueError(f"Mae Sai browser geometry escaped expected bounds: {actual_bounds}.")
    manifest = {
        "schema_version": "1.0",
        "study_area_id": "mae_sai_candidate_v1",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "data_version": DATA_VERSION,
        "source_commit": SOURCE_COMMIT,
        "source_timestamp": SOURCE_TIMESTAMP,
        "generated_at": GENERATED_AT,
        "expected_crs": "EPSG:4326",
        "bounds": actual_bounds,
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": "Real open context is available, but facilities, reference truth, segment-level raster consequences, and agency acceptance remain unqualified.",
        "layers": [
            {
                "layer_id": layer_id,
                "relative_url": f"/offline-demo/mae-sai/{path.name}",
                "sha256": _sha256(path),
                "feature_count": len(collections[layer_id][1]["features"]),
                "source_relative_path": str(INPUTS[layer_id].relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                "source_sha256": _sha256(INPUTS[layer_id]),
            }
            for layer_id, path in written.items()
        ],
        "bundle": {"relative_url": "/offline-demo/mae-sai/bundle.json", "sha256": _sha256(bundle_path)},
    }
    _write("manifest.json", manifest)
    print(
        "Mae Sai offline bundle: "
        f"{len(areas['features'])} areas, {len(roads['features'])} roads, "
        f"{len(facilities['features'])} facilities, {len(access['features'])} access hotspots"
    )


if __name__ == "__main__":
    main()
