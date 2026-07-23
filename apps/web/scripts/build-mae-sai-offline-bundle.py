"""Build the compact, provenance-bound Mae Sai command-map bundle.

The source files are committed FloodGuard derivatives. This script never reads
raw Sentinel products or private workspaces and writes only browser-safe JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from shapely.geometry import mapping, shape


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS = REPOSITORY_ROOT / "outputs"
WEB_PUBLIC_ROOT = REPOSITORY_ROOT / "apps" / "web" / "public"
TARGET = WEB_PUBLIC_ROOT / "offline-demo" / "mae-sai"
SOURCE_COMMIT = "22fc172aca78937bb7d1f8675d08527a8517da68"
DATA_VERSION = "mae-sai-candidate-2024-09-15-v1"
GENERATED_AT = "2026-07-20T08:15:08Z"
SOURCE_TIMESTAMP = "2024-09-15T23:16:01Z"
EVIDENCE_CONTEXT_ID = "mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1"
EVIDENCE_PACKAGE_ID = "mae-sai-historic-planning-2024-09-v1"
SOURCE_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "services"
    / "api"
    / "data"
    / "study_area_bundles"
    / "mae_sai_candidate_v1.json"
)
SOURCE_MANIFEST_SHA256 = "0bb7feff4b84d7a202b006856352d619d66607155bdf41430d5a5ea0f9d52026"
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


def _common(
    *,
    confidence: str,
    source_name: str,
    assumptions: list[str],
    source_timestamp: str = SOURCE_TIMESTAMP,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "source_timestamp": source_timestamp,
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


def _number(
    value: Any,
    *,
    field: str = "number",
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a finite number.") from None
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number.")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field} must be at most {maximum}.")
    return result


def _integer(value: Any, *, field: str = "integer", minimum: int = 0) -> int:
    result = _number(value, field=field, minimum=float(minimum))
    # Population allocation outputs can be fractional estimates. Conversion is
    # explicit and occurs only after finite/non-negative validation.
    return int(round(result))


def _validate_feature_numbers(layer_id: str, properties: dict[str, Any]) -> None:
    if layer_id == "priority_areas":
        for field in (
            "flood_likelihood_0_100",
            "exposure_0_100",
            "access_gap_0_100",
            "road_criticality_0_100",
            "vulnerability_context_0_100",
            "fpps_0_100",
        ):
            _number(properties.get(field), field=field, minimum=0, maximum=100)
        for field in (
            "mean_flood_probability_0_1",
            "p90_flood_probability_0_1",
            "binary_flood_share_0_1",
            "worldpop_bbox_coverage_rate",
            "road_snap_population_coverage_rate",
            "dem_population_coverage_rate",
        ):
            _number(properties.get(field), field=field, minimum=0, maximum=1)
        for field in (
            "total_population",
            "people_losing_30_min_access",
            "facility_count",
            "road_count",
            "bridge_count",
        ):
            _integer(properties.get(field), field=field)
        if properties.get("equity_gap_ratio") not in (None, ""):
            _number(
                properties.get("equity_gap_ratio"),
                field="equity_gap_ratio",
                minimum=0,
            )
    elif layer_id == "road_risk":
        _number(
            properties.get("road_disruption_probability_0_1"),
            field="road_disruption_probability_0_1",
            minimum=0,
            maximum=1,
        )
    elif layer_id == "access_hotspots":
        for field in (
            "people_losing_15_min_access",
            "people_losing_30_min_access",
            "people_losing_60_min_access",
        ):
            _integer(properties.get(field), field=field)
        if properties.get("equity_gap_ratio") is not None:
            _number(
                properties.get("equity_gap_ratio"),
                field="equity_gap_ratio",
                minimum=0,
            )


def _validate_pinned_inputs(
    source_manifest: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    *,
    input_paths: dict[str, Path] | None = None,
    manifest_path: Path | None = None,
) -> None:
    """Validate exact manifest identity and every consumed feature before writes."""

    paths = input_paths or INPUTS
    pinned_manifest_path = manifest_path or SOURCE_MANIFEST_PATH
    if _sha256(pinned_manifest_path) != SOURCE_MANIFEST_SHA256:
        raise ValueError("Mae Sai source manifest checksum validation failed.")

    expected_identity: dict[str, Any] = {
        "schema_version": "1.0",
        "study_area_id": "mae_sai_candidate_v1",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "data_version": DATA_VERSION,
        "git_commit": SOURCE_COMMIT,
        "source_timestamp": SOURCE_TIMESTAMP,
        "generated_at": GENERATED_AT,
        "evidence_context_id": EVIDENCE_CONTEXT_ID,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "expected_crs": "EPSG:4326",
    }
    for field, expected in expected_identity.items():
        if source_manifest.get(field) != expected:
            raise ValueError(f"Mae Sai source manifest {field} is not pinned.")

    area_ids = source_manifest.get("expected_area_ids")
    if not isinstance(area_ids, list) or len(area_ids) != 8 or len(set(area_ids)) != 8:
        raise ValueError("Mae Sai source manifest area identity is incomplete.")
    expected_area_ids = {str(value) for value in area_ids}
    bounds = source_manifest.get("expected_bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bounds)
    ):
        raise ValueError("Mae Sai source manifest bounds are invalid.")
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)

    components = source_manifest.get("source_components")
    if not isinstance(components, list) or not components:
        raise ValueError("Mae Sai source provenance is incomplete.")
    component_ids: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Mae Sai source provenance contains an invalid component.")
        component_id = str(component.get("source_component_id", ""))
        if not component_id or component_id in component_ids:
            raise ValueError("Mae Sai source component identity is invalid.")
        component_ids.add(component_id)
        if (
            component.get("freshness_policy_version") != "source-freshness-v1"
            or component.get("freshness_as_of") != GENERATED_AT
        ):
            raise ValueError("Mae Sai source freshness policy is not pinned.")

    layer_specs = source_manifest.get("layers")
    if not isinstance(layer_specs, list):
        raise ValueError("Mae Sai source layer manifest is missing.")
    specs = {
        str(spec.get("layer_id")): spec
        for spec in layer_specs
        if isinstance(spec, dict)
    }
    primary_keys = {
        "priority_areas": "subdistrict_id",
        "road_risk": "road_id",
        "facilities": "facility_id",
        "access_hotspots": "subdistrict_id",
    }
    for layer_id, path in paths.items():
        spec = specs.get(layer_id)
        source = sources.get(layer_id)
        if not isinstance(spec, dict) or not isinstance(source, dict):
            raise ValueError(f"Mae Sai input {layer_id} is not declared and loaded.")
        expected_relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if spec.get("relative_path") != expected_relative:
            raise ValueError(f"Mae Sai input {layer_id} path identity changed.")
        if spec.get("sha256") != _sha256(path):
            raise ValueError(f"Mae Sai input {layer_id} checksum validation failed.")
        if source.get("type") != "FeatureCollection":
            raise ValueError(f"Mae Sai input {layer_id} is not a FeatureCollection.")
        features = source.get("features")
        if (
            not isinstance(features, list)
            or len(features) != spec.get("expected_feature_count")
        ):
            raise ValueError(f"Mae Sai input {layer_id} feature count changed.")
        geometry_types = spec.get("geometry_types")
        required_properties = spec.get("required_properties")
        join_key = spec.get("join_key")
        if (
            not isinstance(geometry_types, list)
            or not isinstance(required_properties, list)
            or not isinstance(join_key, str)
        ):
            raise ValueError(f"Mae Sai input {layer_id} contract is incomplete.")
        primary_ids: set[str] = set()
        observed_area_ids: set[str] = set()
        for index, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError(f"Mae Sai input {layer_id} feature {index} is invalid.")
            properties = feature.get("properties")
            geometry = feature.get("geometry")
            if not isinstance(properties, dict) or not isinstance(geometry, dict):
                raise ValueError(f"Mae Sai input {layer_id} feature {index} is incomplete.")
            missing = [field for field in required_properties if field not in properties]
            if missing:
                raise ValueError(
                    f"Mae Sai input {layer_id} is missing required properties: {missing}."
                )
            if geometry.get("type") not in geometry_types:
                raise ValueError(f"Mae Sai input {layer_id} geometry type changed.")
            candidate = shape(geometry)
            if candidate.is_empty or not candidate.is_valid:
                raise ValueError(f"Mae Sai input {layer_id} contains invalid geometry.")
            if any(not math.isfinite(value) for value in candidate.bounds):
                raise ValueError(f"Mae Sai input {layer_id} contains non-finite geometry.")
            feature_min_x, feature_min_y, feature_max_x, feature_max_y = candidate.bounds
            if not (
                min_x <= feature_min_x <= max_x
                and min_y <= feature_min_y <= max_y
                and min_x <= feature_max_x <= max_x
                and min_y <= feature_max_y <= max_y
            ):
                raise ValueError(f"Mae Sai input {layer_id} escaped declared bounds.")
            area_id = str(properties.get(join_key, ""))
            if area_id not in expected_area_ids:
                raise ValueError(f"Mae Sai input {layer_id} has an unknown area join key.")
            observed_area_ids.add(area_id)
            primary_id = str(properties.get(primary_keys[layer_id], ""))
            if not primary_id or primary_id in primary_ids:
                raise ValueError(f"Mae Sai input {layer_id} has duplicate feature identity.")
            primary_ids.add(primary_id)
            _validate_feature_numbers(layer_id, properties)
        if layer_id in {"priority_areas", "access_hotspots"} and (
            observed_area_ids != expected_area_ids
        ):
            raise ValueError(f"Mae Sai input {layer_id} area coverage is incomplete.")


def _action_reason_code(properties: dict[str, Any]) -> str:
    if str(properties.get("confidence_class", "")).lower() == "low":
        return "low_confidence"
    if _number(properties.get("fpps_0_100")) < 35:
        return "low_priority_score"
    return {
        "A": "life_safety_exposure",
        "B": "critical_route_access",
        "C": "essential_service_access",
        "D": "resilience",
        "E": "low_priority_score",
    }[str(properties["action_class"])]


def _build_areas(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for source_feature in source["features"]:
        properties = source_feature["properties"]
        area_id = str(properties["subdistrict_id"])
        action_class = str(properties["action_class"])
        action_reason_code = _action_reason_code(properties)
        confidence = str(properties["confidence_class"])
        assumptions = _as_assumptions(properties.get("assumptions"))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "evidence_context_id": EVIDENCE_CONTEXT_ID,
                    "area_id": area_id,
                    "area_name_en": str(properties["subdistrict_name"]),
                    "area_name_th": str(properties["subdistrict_name_th"]),
                    "action_class": action_class,
                    "action_reason_code": action_reason_code,
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
            "evidence_context_id": EVIDENCE_CONTEXT_ID,
            "area_id": area_id,
            "area_name_th": str(properties["subdistrict_name_th"]),
            "area_name_en": str(properties["subdistrict_name"]),
            "fpps_0_100": _number(properties["fpps_0_100"]),
            "action_class": action_class,
            "action_reason_code": action_reason_code,
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


def _build_public_areas(areas: dict[str, Any]) -> dict[str, Any]:
    """Project only public-safe area fields; no road or facility evidence is copied."""

    features = []
    for feature in areas["features"]:
        properties = feature["properties"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "schema_version": "1.0",
                    "evidence_context_id": EVIDENCE_CONTEXT_ID,
                    "area_id": properties["area_id"],
                    "area_name_th": properties["area_name_th"],
                    "area_name_en": properties["area_name_en"],
                    "planning_priority_0_100": properties["fpps_0_100"],
                    "evidence_sufficiency": properties["confidence_class"],
                    "recommendation_code": properties["action_reason_code"],
                    "source_timestamp": SOURCE_TIMESTAMP,
                    "freshness": "historical",
                    "current_conditions_confirmed": False,
                },
                "geometry": feature["geometry"],
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "mae_sai_public_preparedness_areas",
        "features": features,
    }


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


def _layer(
    *,
    layer_id: str,
    title_th: str,
    title_en: str,
    url: str,
    source_name: str,
    source_timestamp: str,
    assumptions: list[str],
    attribution: list[str],
    role_visibility: list[str],
    evidence_state: dict[str, Any],
    source_components: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_common(
            confidence=str(evidence_state["confidence_class"]),
            source_name=source_name,
            assumptions=assumptions,
            source_timestamp=source_timestamp,
        ),
        "evidence_context_id": EVIDENCE_CONTEXT_ID,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "layer_id": layer_id,
        "title_th": title_th,
        "title_en": title_en,
        "role_visibility": role_visibility,
        "format": "geojson",
        "url": url,
        "data_state": "ready",
        "model_run_id": None,
        "evidence_state": evidence_state,
        "source_components": source_components,
        "attribution": attribution,
    }

def _model_evidence_projection(
    evidence_context: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Build the exact API-owned, fail-closed GeoAI v2 projection.

    Run the generator with the API environment so this static fallback and the
    live API serialize one canonical ModelRunV2/evaluation/product/registry
    chain. The active evidence context remains deliberately unbound.
    """

    import sys

    api_source = REPOSITORY_ROOT / "services" / "api" / "src"
    api_source_text = str(api_source)
    if api_source_text not in sys.path:
        sys.path.insert(0, api_source_text)
    try:
        from floodguard_api.dataset_registry import (
            MAE_SAI_STUDY_AREA,
            DatasetRegistry,
        )
        from floodguard_api.model_registry import (
            build_model_registry_bundles,
            observation_asset_descriptors,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Mae Sai model evidence requires the API environment; run "
            "`uv run --project services/api python "
            "apps/web/scripts/build-mae-sai-offline-bundle.py`."
        ) from exc

    repository = DatasetRegistry()
    api_context = repository.evidence_context(MAE_SAI_STUDY_AREA)
    expected_context = {
        "evidence_context_id": api_context.evidence_context_id,
        "study_area_id": api_context.study_area_id,
        "data_version": api_context.data_version,
        "evidence_package_sha256": api_context.evidence_package_sha256,
        "model_run_id": api_context.model_run_id,
        "dataset_mode": api_context.dataset_mode.value,
        "operational_status": api_context.operational_status.value,
        "official_warning": api_context.official_warning,
        "generated_at": api_context.generated_at.isoformat().replace("+00:00", "Z"),
    }
    actual_context = {key: evidence_context.get(key) for key in expected_context}
    if actual_context != expected_context:
        raise ValueError(
            "Mae Sai browser evidence context diverged from the API registry context."
        )

    projection = build_model_registry_bundles(
        repository,
        MAE_SAI_STUDY_AREA,
    )[0]
    return (
        [projection.entry.model_dump(mode="json")],
        [projection.model_run.model_dump(mode="json")],
        [projection.evaluation.model_dump(mode="json")],
        [projection.product.model_dump(mode="json")],
        observation_asset_descriptors(projection.product),
    )


def _build_bundle(
    records: list[dict[str, Any]],
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
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
        "evidence_context_id": EVIDENCE_CONTEXT_ID,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "study_area": "mae_sai_candidate_v1",
        "message_th": "ข้อมูลผู้สมัครแม่สายเพื่อการวางแผน ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ",
        "message_en": "Mae Sai planning candidate; not an official warning.",
        "data_state": "ready",
    }
    source_components = {
        item["source_component_id"]: item
        for item in source_manifest["source_components"]
    }
    layer_specs = {item["layer_id"]: item for item in source_manifest["layers"]}

    def components_for(layer_id: str) -> list[dict[str, Any]]:
        return [
            source_components[component_id]
            for component_id in layer_specs[layer_id]["source_component_ids"]
        ]

    public_evidence_state = {
        "evidence_type": "modelled",
        "granularity": "area_summary",
        "confidence_class": "low",
        "confidence_reason": (
            "Historic candidate evidence has not passed qualified real-event validation."
        ),
        "permitted_use": "public_preparedness",
        "required_gate": "local_current_condition_confirmation",
        "gate_state": "blocked",
    }
    layers = [
        _layer(
            layer_id="public_preparedness_areas",
            title_th="พื้นที่เตรียมพร้อมสาธารณะ",
            title_en="Public preparedness areas",
            url="/offline-demo/mae-sai/public-areas.json",
            source_name="FloodGuard reduced public preparedness projection",
            source_timestamp=SOURCE_TIMESTAMP,
            assumptions=[
                "Historic area-level planning context only; current conditions are not confirmed.",
                "Staff-only road, facility, access, and scoring-component details are omitted.",
            ],
            attribution=[
                "Copernicus Data Space Ecosystem",
                "Copernicus Sentinel-1",
                "HDX Thailand COD-AB",
                "WorldPop 2020",
                "OpenStreetMap contributors",
                "Geofabrik",
                "Copernicus DEM GLO-30",
                "FloodGuard",
            ],
            role_visibility=["public"],
            evidence_state=public_evidence_state,
            source_components=components_for("priority_areas"),
        ),
        *[
            _layer(
                layer_id=layer_id,
                title_th=title_th,
                title_en=title_en,
                url=url,
                source_name=layer_specs[layer_id]["source_name"],
                source_timestamp=layer_specs[layer_id]["source_timestamp"],
                assumptions=[layer_specs[layer_id]["reason_blocked"]],
                attribution=layer_specs[layer_id]["attribution"],
                role_visibility=layer_specs[layer_id]["role_visibility"],
                evidence_state=layer_specs[layer_id]["evidence_state"],
                source_components=components_for(layer_id),
            )
            for layer_id, title_th, title_en, url in (
                (
                    "priority_areas",
                    "พื้นที่รายงานแม่สาย",
                    "Mae Sai reporting areas",
                    "/offline-demo/mae-sai/areas.json",
                ),
                (
                    "road_risk",
                    "บริบทเครือข่ายถนน",
                    "Road network context",
                    "/offline-demo/mae-sai/roads.json",
                ),
                (
                    "facilities",
                    "สถานที่ที่ยังไม่ได้ยืนยัน",
                    "Unverified facility candidates",
                    "/offline-demo/mae-sai/facilities.json",
                ),
                (
                    "access_hotspots",
                    "หลักฐานการเข้าถึงแบบจำลอง",
                    "Modelled access evidence",
                    "/offline-demo/mae-sai/access-hotspots.json",
                ),
            )
        ],
    ]
    evidence_context = {
        "schema_version": "1.0",
        "evidence_context_id": EVIDENCE_CONTEXT_ID,
        "study_area_id": "mae_sai_candidate_v1",
        "data_version": DATA_VERSION,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "evidence_package_sha256": _sha256(SOURCE_MANIFEST_PATH),
        "model_run_id": None,
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "generated_at": GENERATED_AT,
        "source_components": source_manifest["source_components"],
    }
    (
        model_registry,
        model_runs_v2,
        model_evaluations,
        observation_products,
        model_asset_descriptors,
    ) = _model_evidence_projection(evidence_context)
    return {
        "evidence_context": evidence_context,
        "evidence_record": {
            "schema_version": "1.0",
            "evidence_record_id": f"{EVIDENCE_CONTEXT_ID}:blocked",
            "evidence_context": evidence_context,
            "evidence_scope": "Historic Mae Sai planning candidate; no qualified evaluation",
            "model_id": None,
            "model_version": None,
            "model_sha256": None,
            "evaluation_sha256": None,
            "decision": "blocked",
            "decision_authority": None,
            "decision_at": None,
            "operational_authorized": False,
            "blockers": [
                "No qualified Thailand event-flood reference evaluation is published.",
                "Facility roles and current operation are not agency verified.",
                "Road evidence is area-summary context, not segment-raster intersection.",
                "No agency operational acceptance is recorded.",
            ],
            "generated_at": GENERATED_AT,
        },
        "public_areas": [
            {
                "schema_version": "1.0",
                "evidence_context_id": EVIDENCE_CONTEXT_ID,
                "area_id": item["area_id"],
                "area_name_th": item["area_name_th"],
                "area_name_en": item["area_name_en"],
                "planning_priority_0_100": item["fpps_0_100"],
                "evidence_sufficiency": item["confidence_class"],
                "recommendation_code": item["action_reason_code"],
                "source_timestamp": SOURCE_TIMESTAMP,
                "freshness": "historical",
                "current_conditions_confirmed": False,
            }
            for item in records
        ],
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
        "model_runs_v2": model_runs_v2,
        "model_registry": model_registry,
        "model_evaluations": model_evaluations,
        "observation_products": observation_products,
        "model_asset_descriptors": model_asset_descriptors,
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


def _attach_layer_metadata(
    collection: dict[str, Any],
    layer: dict[str, Any],
    source_sha256: str,
) -> None:
    collection["floodguard_metadata"] = {
        "schema_version": "1.0",
        "study_area_id": "mae_sai_candidate_v1",
        "evidence_context_id": EVIDENCE_CONTEXT_ID,
        "evidence_package_id": EVIDENCE_PACKAGE_ID,
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "data_version": DATA_VERSION,
        "artifact_sha256": source_sha256,
        "source_timestamp": layer["source_timestamp"],
        "freshness": layer["source_components"][0]["freshness"],
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": layer["evidence_state"]["confidence_reason"],
        "role_visibility": layer["role_visibility"],
        "evidence_state": layer["evidence_state"],
        "source_components": layer["source_components"],
        "attribution": layer["attribution"],
    }


def _public_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return a cache-safe Public bundle with no staff-only evidence payload."""

    return {
        "evidence_context": bundle["evidence_context"],
        "evidence_record": bundle["evidence_record"],
        "public_areas": bundle["public_areas"],
        "status": bundle["status"],
        "layers": [
            layer for layer in bundle["layers"] if "public" in layer["role_visibility"]
        ],
        "hotlines": bundle["hotlines"],
        "shelters": [],
    }


def _write(name: str, value: dict[str, Any]) -> Path:
    TARGET.mkdir(parents=True, exist_ok=True)
    destination = TARGET / name
    destination.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination


def _write_model_asset_descriptors(
    bundle: dict[str, Any],
) -> list[dict[str, str]]:
    """Materialize each declared descriptor and prove its exact content hash."""

    descriptors = bundle["model_asset_descriptors"]
    expected_hashes = {
        asset["relative_path"]: asset["sha256"]
        for product in bundle["observation_products"]
        for asset in product["assets"]
    }
    if set(descriptors) != set(expected_hashes):
        raise ValueError("Model asset descriptor paths diverged from the product manifest.")

    written: list[dict[str, str]] = []
    for relative_path, descriptor in sorted(descriptors.items()):
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Model asset descriptor path must remain repository-relative.")
        destination = WEB_PUBLIC_ROOT.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            descriptor,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != expected_hashes[relative_path]:
            raise ValueError(
                f"Model asset descriptor hash mismatch for {relative_path}."
            )
        destination.write_bytes(payload)
        written.append(
            {
                "relative_url": f"/{relative.as_posix()}",
                "sha256": actual_sha256,
            }
        )
    return written


def main() -> None:
    sources = {key: _load(path) for key, path in INPUTS.items()}
    source_manifest = _load(SOURCE_MANIFEST_PATH)
    _validate_pinned_inputs(source_manifest, sources)
    areas, records = _build_areas(sources["priority_areas"])
    public_areas = _build_public_areas(areas)
    valid_area_ids = {str(feature["properties"]["area_id"]) for feature in areas["features"]}
    roads = _build_roads(sources["road_risk"], valid_area_ids)
    facilities = _build_facilities(sources["facilities"], valid_area_ids)
    access = _build_access(sources["access_hotspots"], valid_area_ids)
    bundle = _build_bundle(records, source_manifest)
    collections = {
        "public_preparedness_areas": ("public-areas.json", public_areas),
        "priority_areas": ("areas.json", areas),
        "road_risk": ("roads.json", roads),
        "facilities": ("facilities.json", facilities),
        "access_hotspots": ("access-hotspots.json", access),
    }
    layer_catalog = {item["layer_id"]: item for item in bundle["layers"]}
    source_layer_ids = {
        "public_preparedness_areas": "priority_areas",
        "priority_areas": "priority_areas",
        "road_risk": "road_risk",
        "facilities": "facilities",
        "access_hotspots": "access_hotspots",
    }
    for layer_id, (_, collection) in collections.items():
        source_layer_id = source_layer_ids[layer_id]
        _attach_layer_metadata(
            collection,
            layer_catalog[layer_id],
            _sha256(INPUTS[source_layer_id]),
        )
    written = {layer_id: _write(file_name, collection) for layer_id, (file_name, collection) in collections.items()}
    model_descriptor_manifest = _write_model_asset_descriptors(bundle)
    bundle_path = _write("bundle.json", bundle)
    public_bundle_path = _write("public-bundle.json", _public_bundle(bundle))
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
        "evidence_context": bundle["evidence_context"],
        "layers": [
            {
                "layer_id": layer_id,
                "relative_url": f"/offline-demo/mae-sai/{path.name}",
                "sha256": _sha256(path),
                "feature_count": len(collections[layer_id][1]["features"]),
                "source_relative_path": str(INPUTS[source_layer_ids[layer_id]].relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                "source_sha256": _sha256(INPUTS[source_layer_ids[layer_id]]),
                "role_visibility": layer_catalog[layer_id]["role_visibility"],
                "evidence_state": layer_catalog[layer_id]["evidence_state"],
                "source_components": layer_catalog[layer_id]["source_components"],
            }
            for layer_id, path in written.items()
        ],
        "bundle": {"relative_url": "/offline-demo/mae-sai/bundle.json", "sha256": _sha256(bundle_path)},
        "model_evidence_descriptors": model_descriptor_manifest,
        "public_bundle": {
            "relative_url": "/offline-demo/mae-sai/public-bundle.json",
            "sha256": _sha256(public_bundle_path),
        },
    }
    _write("manifest.json", manifest)
    print(
        "Mae Sai offline bundle: "
        f"{len(areas['features'])} areas, {len(roads['features'])} roads, "
        f"{len(facilities['features'])} facilities, {len(access['features'])} access hotspots, "
        f"{len(public_areas['features'])} public-safe areas"
    )


if __name__ == "__main__":
    main()
