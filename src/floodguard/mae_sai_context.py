"""Real open-context integration for the Mae Sai weak-reference decision lane."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
import re

import pandas as pd

from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss
from floodguard.open_context_extract import geojson_bounds
from floodguard.road_risk import score_road_disruption


CONTEXT_WARNING = (
    "Open context joined to real Sentinel-1 candidate evidence. Non-operational. "
    "Not official validation. Not an official warning."
)

DRIVABLE_ROAD_CLASS_MAP: dict[str, str] = {
    "motorway": "motorway",
    "motorway_link": "motorway",
    "trunk": "trunk",
    "trunk_link": "trunk",
    "primary": "primary",
    "primary_link": "primary",
    "secondary": "secondary",
    "secondary_link": "secondary",
    "tertiary": "tertiary",
    "tertiary_link": "tertiary",
    "residential": "residential",
    "living_street": "residential",
    "unclassified": "unclassified",
    "service": "local",
    "services": "local",
    "road": "local",
    "track": "local",
}

ROAD_SPEED_KMH: dict[str, float] = {
    "motorway": 80.0,
    "trunk": 70.0,
    "primary": 60.0,
    "secondary": 50.0,
    "tertiary": 40.0,
    "residential": 25.0,
    "unclassified": 25.0,
    "local": 20.0,
}

FACILITY_TYPE_MAP: dict[str, str] = {
    "hospital": "healthcare",
    "clinic": "healthcare",
    "doctors": "healthcare",
    "pharmacy": "healthcare",
    "shelter": "shelter_candidate",
    "school": "school",
    "kindergarten": "school",
    "community_centre": "community_facility",
    "townhall": "community_facility",
    "police": "emergency_service",
    "fire_station": "emergency_service",
}

VULNERABILITY_DEFINITION = (
    "terrain/remoteness proxy: WorldPop cell is proxy-vulnerable when sampled "
    "slope is at least 8 degrees or nearest drivable OSM road is at least 750 m "
    "away; this is not demographic vulnerability"
)


class MaeSaiContextError(ValueError):
    """Raised when Mae Sai context inputs cannot support a defensible join."""


@dataclass(frozen=True)
class MaeSaiContextOutputs:
    """Derived context artifacts produced by the Mae Sai integration."""

    population_context: pd.DataFrame
    population_nodes: pd.DataFrame
    road_risk: pd.DataFrame
    road_edges: pd.DataFrame
    facilities: pd.DataFrame
    access_loss: pd.DataFrame
    equity_gap: pd.DataFrame
    decision_inputs: pd.DataFrame
    quality_summary: pd.DataFrame


def build_road_risk_geojson(
    roads_geojson: Mapping[str, object],
    road_risk: pd.DataFrame,
) -> dict[str, object]:
    """Join derived candidate road risk back to OSM line geometry."""

    required = {
        "road_id",
        "subdistrict_id",
        "subdistrict_name",
        "road_disruption_probability_0_1",
        "closure_status",
        "confidence_class",
        "top_risk_reason",
        "source_name",
        "source_timestamp",
        "assumptions",
    }
    missing = sorted(required.difference(road_risk.columns))
    if missing:
        raise MaeSaiContextError(
            "Road-risk frame is missing GeoJSON fields: " + ", ".join(missing)
        )
    rows = road_risk.set_index(road_risk["road_id"].astype(str)).to_dict("index")
    features: list[dict[str, object]] = []
    for feature in _features(roads_geojson, "roads"):
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            continue
        road_id = str(properties.get("osm_id", "")).strip()
        row = rows.get(road_id)
        if row is None or geometry.get("type") != "LineString":
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "road_id": road_id,
                    "subdistrict_id": str(row["subdistrict_id"]),
                    "subdistrict_name": str(row["subdistrict_name"]),
                    "road_name": str(row.get("osm_name", "")),
                    "road_class": str(row.get("road_class", "")),
                    "osm_highway": str(row.get("osm_highway", "")),
                    "bridge_flag": bool(row.get("bridge_flag", False)),
                    "road_disruption_probability_0_1": round(
                        float(row["road_disruption_probability_0_1"]), 3
                    ),
                    "candidate_status": str(row["closure_status"]),
                    "top_risk_reason": str(row["top_risk_reason"]),
                    "confidence_class": str(row["confidence_class"]),
                    "source_name": str(row["source_name"]),
                    "source_timestamp": str(row["source_timestamp"]),
                    "assumptions": str(row["assumptions"]),
                    "warning_text": (
                        "Candidate road risk only. Not an observed closure and not "
                        "an official warning."
                    ),
                },
                "geometry": dict(geometry),
            }
        )
    if not features:
        raise MaeSaiContextError("No Mae Sai road-risk geometry could be joined.")
    return {
        "type": "FeatureCollection",
        "name": "mae_sai_candidate_road_risk",
        "features": features,
    }


def build_facility_geojson(facilities: pd.DataFrame) -> dict[str, object]:
    """Build candidate OSM facility points for dashboard context."""

    required = {
        "facility_id",
        "facility_type",
        "facility_name",
        "longitude",
        "latitude",
        "subdistrict_id",
        "subdistrict_name",
        "confidence_class",
        "source_name",
        "source_timestamp",
        "assumptions",
    }
    missing = sorted(required.difference(facilities.columns))
    if missing:
        raise MaeSaiContextError(
            "Facility frame is missing GeoJSON fields: " + ", ".join(missing)
        )
    features = []
    for row in facilities.to_dict("records"):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "facility_id": str(row["facility_id"]),
                    "facility_type": str(row["facility_type"]),
                    "facility_name": str(row["facility_name"]),
                    "amenity": str(row.get("amenity", "")),
                    "subdistrict_id": str(row["subdistrict_id"]),
                    "subdistrict_name": str(row["subdistrict_name"]),
                    "snap_distance_m": round(float(row["snap_distance_m"]), 1),
                    "candidate_status": "unverified_osm_candidate",
                    "confidence_class": str(row["confidence_class"]),
                    "source_name": str(row["source_name"]),
                    "source_timestamp": str(row["source_timestamp"]),
                    "assumptions": str(row["assumptions"]),
                    "warning_text": (
                        "Candidate facility context only. Not a confirmed emergency "
                        "facility or shelter."
                    ),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "mae_sai_candidate_facilities",
        "features": features,
    }


def build_access_hotspot_geojson(
    admin_geojson: Mapping[str, object],
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
) -> dict[str, object]:
    """Build one modeled access-loss marker per ADM3 reporting unit."""

    access_required = {
        "subdistrict_id",
        "people_losing_15_min_access",
        "people_losing_30_min_access",
        "people_losing_60_min_access",
        "confidence_class",
        "source_timestamp",
        "assumptions",
    }
    missing = sorted(access_required.difference(access_loss.columns))
    if missing:
        raise MaeSaiContextError(
            "Access-loss frame is missing hotspot fields: " + ", ".join(missing)
        )
    access_rows = access_loss.set_index(access_loss["subdistrict_id"].astype(str))
    equity_rows = equity_gap.set_index(equity_gap["subdistrict_id"].astype(str))
    features: list[dict[str, object]] = []
    for feature in _features(admin_geojson, "admin"):
        properties = feature["properties"]
        geometry = feature["geometry"]
        subdistrict_id = str(properties["subdistrict_id"])
        if subdistrict_id not in access_rows.index:
            raise MaeSaiContextError(
                f"Access-loss hotspot is missing subdistrict {subdistrict_id}."
            )
        access_row = access_rows.loc[subdistrict_id]
        equity_ratio: float | None = None
        if subdistrict_id in equity_rows.index:
            value = pd.to_numeric(
                pd.Series([equity_rows.loc[subdistrict_id, "equity_gap_ratio"]]),
                errors="coerce",
            ).iloc[0]
            if not pd.isna(value):
                equity_ratio = round(float(value), 3)
        losing_30 = float(access_row["people_losing_30_min_access"])
        longitude, latitude = geometry_representative_point(geometry)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "subdistrict_id": subdistrict_id,
                    "subdistrict_name": str(properties["subdistrict_name"]),
                    "people_losing_15_min_access": round(
                        float(access_row["people_losing_15_min_access"]), 3
                    ),
                    "people_losing_30_min_access": round(losing_30, 3),
                    "people_losing_60_min_access": round(
                        float(access_row["people_losing_60_min_access"]), 3
                    ),
                    "equity_gap_ratio": equity_ratio,
                    "candidate_status": (
                        "modeled_access_loss_candidate"
                        if losing_30 > 0
                        else "no_modeled_30_minute_loss"
                    ),
                    "confidence_class": str(access_row["confidence_class"]),
                    "source_timestamp": str(access_row["source_timestamp"]),
                    "assumptions": str(access_row["assumptions"]),
                    "warning_text": (
                        "Modeled access-loss candidate only. Not an observed service "
                        "outage and not an official warning."
                    ),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "mae_sai_modeled_access_hotspots",
        "features": features,
    }


class NearestRoadNodeIndex:
    """Small grid index for snapping population and facility points to roads."""

    def __init__(
        self,
        nodes: Mapping[str, tuple[float, float]],
        *,
        cell_size_degrees: float = 0.005,
    ) -> None:
        if not nodes:
            raise MaeSaiContextError("At least one road node is required.")
        self.nodes = dict(nodes)
        self.cell_size = cell_size_degrees
        self.buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
        for node_id, (longitude, latitude) in self.nodes.items():
            self.buckets[self._cell(longitude, latitude)].append(node_id)

    def nearest(
        self,
        longitude: float,
        latitude: float,
        *,
        max_distance_m: float = 5000.0,
    ) -> tuple[str, float] | None:
        origin = self._cell(longitude, latitude)
        best_node: str | None = None
        best_distance = math.inf
        max_ring = max(1, math.ceil(max_distance_m / 450.0))
        for ring in range(max_ring + 1):
            candidates: list[str] = []
            for x_offset in range(-ring, ring + 1):
                for y_offset in range(-ring, ring + 1):
                    if ring and max(abs(x_offset), abs(y_offset)) != ring:
                        continue
                    candidates.extend(
                        self.buckets.get(
                            (origin[0] + x_offset, origin[1] + y_offset), []
                        )
                    )
            for node_id in candidates:
                node_lon, node_lat = self.nodes[node_id]
                distance = haversine_m(longitude, latitude, node_lon, node_lat)
                if distance < best_distance:
                    best_node = node_id
                    best_distance = distance
            if best_node is not None and best_distance <= ring * 450.0:
                break
        if best_node is None or best_distance > max_distance_m:
            return None
        return best_node, best_distance

    def _cell(self, longitude: float, latitude: float) -> tuple[int, int]:
        return (
            math.floor(longitude / self.cell_size),
            math.floor(latitude / self.cell_size),
        )


class TerrainSampler:
    """Sample elevation and derived slope from a bounded DEM window."""

    def __init__(self, dem_path: str, analysis_bbox: tuple[float, float, float, float]):
        import numpy as np
        import rasterio
        from rasterio.windows import Window, from_bounds

        self.np = np
        with rasterio.open(dem_path) as dataset:
            if str(dataset.crs).upper() != "EPSG:4326":
                raise MaeSaiContextError("Mae Sai DEM must use EPSG:4326.")
            bounds = dataset.bounds
            left = max(bounds.left, analysis_bbox[0])
            bottom = max(bounds.bottom, analysis_bbox[1])
            right = min(bounds.right, analysis_bbox[2])
            top = min(bounds.top, analysis_bbox[3])
            if right <= left or top <= bottom:
                raise MaeSaiContextError("Selected DEM does not overlap Mae Sai ADM3.")
            raw_window = from_bounds(left, bottom, right, top, dataset.transform)
            window = raw_window.round_offsets().round_lengths().intersection(
                Window(0, 0, dataset.width, dataset.height)
            )
            elevation = dataset.read(1, window=window, masked=True).astype("float32")
            self.transform = dataset.window_transform(window)
            self.bounds = (
                max(bounds.left, analysis_bbox[0]),
                max(bounds.bottom, analysis_bbox[1]),
                min(bounds.right, analysis_bbox[2]),
                min(bounds.top, analysis_bbox[3]),
            )
        self.elevation = np.ma.filled(elevation, np.nan)
        center_latitude = (self.bounds[1] + self.bounds[3]) / 2.0
        x_resolution_m = abs(self.transform.a) * 111320.0 * math.cos(
            math.radians(center_latitude)
        )
        y_resolution_m = abs(self.transform.e) * 110540.0
        gradient_y, gradient_x = np.gradient(
            self.elevation,
            y_resolution_m,
            x_resolution_m,
        )
        self.slope = np.degrees(np.arctan(np.hypot(gradient_x, gradient_y)))

    def sample(self, longitude: float, latitude: float) -> tuple[float | None, float | None]:
        if not (
            self.bounds[0] <= longitude <= self.bounds[2]
            and self.bounds[1] <= latitude <= self.bounds[3]
        ):
            return None, None
        col, row = (~self.transform) * (longitude, latitude)
        row_index = int(math.floor(row))
        col_index = int(math.floor(col))
        if not (
            0 <= row_index < self.elevation.shape[0]
            and 0 <= col_index < self.elevation.shape[1]
        ):
            return None, None
        elevation = float(self.elevation[row_index, col_index])
        slope = float(self.slope[row_index, col_index])
        if not math.isfinite(elevation) or not math.isfinite(slope):
            return None, None
        return elevation, slope


def build_mae_sai_context_outputs(
    admin_geojson: Mapping[str, object],
    roads_geojson: Mapping[str, object],
    points_geojson: Mapping[str, object],
    sar_summary: pd.DataFrame,
    *,
    worldpop_path: str,
    dem_path: str,
) -> MaeSaiContextOutputs:
    """Join real context sources into deterministic Mae Sai decision inputs."""

    admin_features = _features(admin_geojson, "admin")
    road_features = _features(roads_geojson, "roads")
    point_features = _features(points_geojson, "points")
    _validate_sar_summary(sar_summary, admin_features)

    road_risk, road_edges, road_nodes = build_road_context(
        road_features,
        admin_features,
        sar_summary,
    )
    node_index = NearestRoadNodeIndex(road_nodes)
    terrain = TerrainSampler(dem_path, geojson_bounds(admin_features))
    population_context, population_nodes = build_population_context(
        worldpop_path,
        admin_features,
        node_index,
        terrain,
    )
    facilities = build_facility_context(point_features, admin_features, node_index)
    if facilities.empty:
        raise MaeSaiContextError(
            "No OSM candidate facilities could be snapped to the Mae Sai road graph."
        )
    access_loss = calculate_access_loss(
        population_nodes,
        road_edges.loc[:, ["from_node", "to_node", "normal_minutes", "disrupted_minutes"]],
        facilities.loc[:, ["facility_id", "facility_type", "node_id"]],
    )
    access_loss = _complete_access_rows(access_loss, admin_features, population_context)
    access_loss["confidence_class"] = "low"
    access_loss["source_timestamp"] = "2024-09-15T23:16:01Z"
    access_loss["vulnerability_definition"] = VULNERABILITY_DEFINITION
    access_loss["assumptions"] = (
        "Candidate OSM routing with heuristic Sentinel-1 road disruption. "
        "OSM shelters/facilities are unverified candidates, not official emergency sites."
    )
    equity_gap = compute_equity_gap(
        equity_input_from_access_loss(access_loss, threshold=30, confidence_class="low")
    )
    equity_gap["source_timestamp"] = "2024-09-15T23:16:01Z"
    equity_gap["vulnerability_definition"] = VULNERABILITY_DEFINITION
    equity_gap["assumptions"] = (
        "Equity uses a terrain/remoteness proxy group, not demographic vulnerability. "
        "Candidate metrics only."
    )
    decision_inputs = build_decision_inputs(
        admin_features,
        sar_summary,
        population_context,
        road_risk,
        access_loss,
        equity_gap,
        facilities,
    )
    quality_summary = build_context_quality_summary(
        admin_features,
        road_risk,
        road_edges,
        facilities,
        population_context,
        population_nodes,
    )
    return MaeSaiContextOutputs(
        population_context=population_context,
        population_nodes=population_nodes,
        road_risk=road_risk,
        road_edges=road_edges,
        facilities=facilities,
        access_loss=access_loss,
        equity_gap=equity_gap,
        decision_inputs=decision_inputs,
        quality_summary=quality_summary,
    )


def build_road_context(
    road_features: Sequence[Mapping[str, object]],
    admin_features: Sequence[Mapping[str, object]],
    sar_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[float, float]]]:
    """Build way-level road risk and a routable candidate edge table."""

    sar_by_id = sar_summary.set_index("subdistrict_id")
    road_inputs: list[dict[str, object]] = []
    metadata: list[dict[str, object]] = []
    road_coordinates: dict[str, list[tuple[float, float]]] = {}
    for feature in road_features:
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            continue
        highway = str(properties.get("highway", "")).lower()
        road_class = DRIVABLE_ROAD_CLASS_MAP.get(highway)
        if road_class is None or geometry.get("type") != "LineString":
            continue
        coordinates = [
            (float(coordinate[0]), float(coordinate[1]))
            for coordinate in geometry.get("coordinates", [])
        ]
        if len(coordinates) < 2:
            continue
        midpoint = coordinates[len(coordinates) // 2]
        admin = find_admin_for_point(midpoint[0], midpoint[1], admin_features)
        if admin is None:
            continue
        admin_properties = admin["properties"]
        subdistrict_id = str(admin_properties["subdistrict_id"])
        sar_row = sar_by_id.loc[subdistrict_id]
        road_id = str(properties.get("osm_id", "")).strip()
        if not road_id or road_id in road_coordinates:
            continue
        bridge = _tag_value(str(properties.get("other_tags", "")), "bridge")
        bridge_flag = bool(bridge and bridge.lower() not in {"no", "false", "0"})
        road_inputs.append(
            {
                "road_id": road_id,
                "road_class": road_class,
                "bridge_flag": bridge_flag,
                "subdistrict_id": subdistrict_id,
                "surrounding_inundation_0_1": float(
                    sar_row["p90_flood_probability_0_1"]
                ),
            }
        )
        metadata.append(
            {
                "road_id": road_id,
                "osm_name": str(properties.get("name", "")),
                "osm_highway": highway,
                "road_class": road_class,
                "bridge_flag": bridge_flag,
                "subdistrict_name": str(admin_properties["subdistrict_name"]),
            }
        )
        road_coordinates[road_id] = coordinates
    if not road_inputs:
        raise MaeSaiContextError("No drivable OSM road features overlap Mae Sai ADM3.")

    flood_frame = sar_summary.loc[
        :,
        [
            "subdistrict_id",
            "mean_flood_probability_0_1",
            "confidence_class",
            "source_timestamp",
        ],
    ].copy()
    flood_frame["source_name"] = "CDSE Sentinel-1 ADM3 candidate change summary"
    road_risk = score_road_disruption(pd.DataFrame(road_inputs), flood_frame)
    road_risk = road_risk.merge(pd.DataFrame(metadata), on="road_id", how="left", validate="one_to_one")
    road_risk["processing_scope"] = "osm_sentinel1_candidate_road_risk"
    road_risk["closure_status"] = road_risk.apply(
        lambda row: _candidate_closure_status(
            float(row["road_disruption_probability_0_1"]), bool(row["bridge_flag"])
        ),
        axis=1,
    )
    road_risk["assumptions"] = (
        "Heuristic candidate risk from ADM3-level Sentinel-1 mean/P90 change, "
        "OSM class, and OSM bridge tag; it is not a segment-level raster "
        "intersection. Not an observed or official road closure."
    )

    risk_by_id = road_risk.set_index("road_id")
    edge_rows: list[dict[str, object]] = []
    nodes: dict[str, tuple[float, float]] = {}
    edge_index = 1
    for road_id, coordinates in road_coordinates.items():
        risk_row = risk_by_id.loc[road_id]
        risk = float(risk_row["road_disruption_probability_0_1"])
        road_class = str(risk_row["road_class"])
        bridge_flag = bool(risk_row["bridge_flag"])
        status = str(risk_row["closure_status"])
        for start, end in zip(coordinates, coordinates[1:]):
            length_m = haversine_m(start[0], start[1], end[0], end[1])
            if length_m <= 0:
                continue
            start_id = _node_id(start)
            end_id = _node_id(end)
            nodes[start_id] = start
            nodes[end_id] = end
            normal_minutes = (length_m / 1000.0) / ROAD_SPEED_KMH[road_class] * 60.0
            disrupted_minutes: float | object
            if status == "candidate_closed":
                disrupted_minutes = pd.NA
            else:
                disrupted_minutes = normal_minutes * (1.0 + 4.0 * risk)
            edge_rows.append(
                {
                    "edge_id": f"MS-EDGE-{edge_index:07d}",
                    "road_id": road_id,
                    "from_node": start_id,
                    "to_node": end_id,
                    "normal_minutes": round(normal_minutes, 6),
                    "disrupted_minutes": (
                        round(float(disrupted_minutes), 6)
                        if not pd.isna(disrupted_minutes)
                        else pd.NA
                    ),
                    "road_disruption_probability_0_1": risk,
                    "candidate_closure_status": status,
                    "subdistrict_id": str(risk_row["subdistrict_id"]),
                    "road_class": road_class,
                    "bridge_flag": bridge_flag,
                }
            )
            edge_index += 1
    return road_risk, pd.DataFrame(edge_rows), nodes


def build_population_context(
    worldpop_path: str,
    admin_features: Sequence[Mapping[str, object]],
    node_index: NearestRoadNodeIndex,
    terrain: TerrainSampler,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate WorldPop and build road-snapped population nodes."""

    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds

    context_rows: list[dict[str, object]] = []
    node_totals: dict[tuple[str, str], dict[str, float | str]] = {}
    with rasterio.open(worldpop_path) as dataset:
        if str(dataset.crs).upper() != "EPSG:4326":
            raise MaeSaiContextError("WorldPop raster must use EPSG:4326.")
        for feature in admin_features:
            properties = feature["properties"]
            geometry = feature["geometry"]
            subdistrict_id = str(properties["subdistrict_id"])
            subdistrict_name = str(properties["subdistrict_name"])
            bounds = _geometry_bounds(geometry)
            left = max(bounds[0], dataset.bounds.left)
            bottom = max(bounds[1], dataset.bounds.bottom)
            right = min(bounds[2], dataset.bounds.right)
            top = min(bounds[3], dataset.bounds.top)
            if right <= left or top <= bottom:
                raise MaeSaiContextError(
                    f"WorldPop does not overlap subdistrict {subdistrict_id}."
                )
            window = from_bounds(left, bottom, right, top, dataset.transform)
            window = window.round_offsets().round_lengths().intersection(
                Window(0, 0, dataset.width, dataset.height)
            )
            data = dataset.read(1, window=window, masked=True).astype("float32")
            transform = dataset.window_transform(window)
            inside = geometry_mask(
                [geometry],
                out_shape=data.shape,
                transform=transform,
                invert=True,
                all_touched=False,
            )
            values = np.ma.filled(data, np.nan)
            valid = inside & np.isfinite(values) & (values >= 0)
            positive = valid & (values > 0)
            rows, cols = np.where(positive)
            total_population = float(values[valid].sum()) if bool(valid.any()) else 0.0
            snapped_population = 0.0
            vulnerable_population = 0.0
            elevation_weighted = 0.0
            slope_weighted = 0.0
            terrain_population = 0.0
            for row_index, col_index in zip(rows.tolist(), cols.tolist()):
                population = float(values[row_index, col_index])
                longitude, latitude = rasterio.transform.xy(
                    transform, row_index, col_index, offset="center"
                )
                snapped = node_index.nearest(float(longitude), float(latitude))
                elevation, slope = terrain.sample(float(longitude), float(latitude))
                road_distance = snapped[1] if snapped is not None else math.inf
                is_vulnerable = road_distance >= 750.0 or (
                    slope is not None and slope >= 8.0
                )
                if is_vulnerable:
                    vulnerable_population += population
                if elevation is not None and slope is not None:
                    elevation_weighted += elevation * population
                    slope_weighted += slope * population
                    terrain_population += population
                if snapped is None:
                    continue
                node_id = snapped[0]
                snapped_population += population
                key = (subdistrict_id, node_id)
                record = node_totals.setdefault(
                    key,
                    {
                        "node_id": node_id,
                        "subdistrict_id": subdistrict_id,
                        "subdistrict_name": subdistrict_name,
                        "total_population": 0.0,
                        "vulnerable_population": 0.0,
                        "non_vulnerable_population": 0.0,
                    },
                )
                record["total_population"] = float(record["total_population"]) + population
                if is_vulnerable:
                    record["vulnerable_population"] = (
                        float(record["vulnerable_population"]) + population
                    )
                else:
                    record["non_vulnerable_population"] = (
                        float(record["non_vulnerable_population"]) + population
                    )
            bbox_area = max((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]), 1e-12)
            covered_bbox_area = max((right - left) * (top - bottom), 0.0)
            context_rows.append(
                {
                    "subdistrict_id": subdistrict_id,
                    "subdistrict_name": subdistrict_name,
                    "total_population": round(total_population, 3),
                    "total_vulnerable_population": round(vulnerable_population, 3),
                    "total_non_vulnerable_population": round(
                        max(total_population - vulnerable_population, 0.0), 3
                    ),
                    "worldpop_positive_cell_count": int(len(rows)),
                    "population_node_count": 0,
                    "worldpop_bbox_coverage_rate": round(
                        min(covered_bbox_area / bbox_area, 1.0), 4
                    ),
                    "road_snap_population_coverage_rate": round(
                        snapped_population / total_population if total_population else 0.0,
                        4,
                    ),
                    "dem_population_coverage_rate": round(
                        terrain_population / total_population if total_population else 0.0,
                        4,
                    ),
                    "mean_elevation_m": round(
                        elevation_weighted / terrain_population, 2
                    )
                    if terrain_population
                    else pd.NA,
                    "mean_slope_degrees": round(slope_weighted / terrain_population, 2)
                    if terrain_population
                    else pd.NA,
                    "vulnerability_definition": VULNERABILITY_DEFINITION,
                    "source_name": "WorldPop Thailand 100m 2020; Copernicus DEM GLO-30; OSM",
                    "source_timestamp": "2020-01-01T00:00:00Z",
                    "confidence_class": "low",
                    "assumptions": (
                        "WorldPop 2020 population with terrain/remoteness vulnerability "
                        "proxy. Not current census totals or demographic vulnerability."
                    ),
                }
            )
    population_nodes = pd.DataFrame(node_totals.values())
    if population_nodes.empty:
        raise MaeSaiContextError("No WorldPop cells could be snapped to the road graph.")
    for column in ("total_population", "vulnerable_population", "non_vulnerable_population"):
        population_nodes[column] = population_nodes[column].astype(float).round(3)
    context = pd.DataFrame(context_rows)
    node_counts = population_nodes.groupby("subdistrict_id")["node_id"].nunique()
    context["population_node_count"] = (
        context["subdistrict_id"].map(node_counts).fillna(0).astype(int)
    )
    return context, population_nodes


def build_facility_context(
    point_features: Sequence[Mapping[str, object]],
    admin_features: Sequence[Mapping[str, object]],
    node_index: NearestRoadNodeIndex,
) -> pd.DataFrame:
    """Extract and snap candidate OSM facilities to the road graph."""

    rows: list[dict[str, object]] = []
    for feature in point_features:
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            continue
        if geometry.get("type") != "Point":
            continue
        amenity = _tag_value(str(properties.get("other_tags", "")), "amenity")
        facility_type = FACILITY_TYPE_MAP.get(str(amenity).lower()) if amenity else None
        if facility_type is None:
            continue
        coordinates = geometry.get("coordinates", [])
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
        admin = find_admin_for_point(longitude, latitude, admin_features)
        snapped = node_index.nearest(longitude, latitude, max_distance_m=2000.0)
        if admin is None or snapped is None:
            continue
        osm_id = str(properties.get("osm_id", "")).strip()
        if not osm_id:
            continue
        rows.append(
            {
                "facility_id": f"OSM-{osm_id}",
                "facility_type": facility_type,
                "amenity": amenity,
                "facility_name": str(properties.get("name", "")),
                "longitude": round(longitude, 7),
                "latitude": round(latitude, 7),
                "node_id": snapped[0],
                "snap_distance_m": round(snapped[1], 1),
                "subdistrict_id": str(admin["properties"]["subdistrict_id"]),
                "subdistrict_name": str(admin["properties"]["subdistrict_name"]),
                "source_name": "OpenStreetMap Thailand via Geofabrik",
                "source_timestamp": "2026-07-09T14:53:08Z",
                "confidence_class": "low",
                "assumptions": (
                    "OSM-tagged candidate facility; not verified as an official "
                    "emergency shelter or currently operating service."
                ),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.drop_duplicates("facility_id").sort_values("facility_id")
    return frame.reset_index(drop=True)


def build_decision_inputs(
    admin_features: Sequence[Mapping[str, object]],
    sar_summary: pd.DataFrame,
    population_context: pd.DataFrame,
    road_risk: pd.DataFrame,
    access_loss: pd.DataFrame,
    equity_gap: pd.DataFrame,
    facilities: pd.DataFrame,
) -> pd.DataFrame:
    """Build FPPS-ready inputs from real context and candidate flood evidence."""

    admin = pd.DataFrame(
        [
            {
                "subdistrict_id": feature["properties"]["subdistrict_id"],
                "subdistrict_name": feature["properties"]["subdistrict_name"],
                "subdistrict_name_th": feature["properties"].get(
                    "subdistrict_name_th", ""
                ),
            }
            for feature in admin_features
        ]
    )
    frame = admin.merge(sar_summary, on=["subdistrict_id", "subdistrict_name"], validate="one_to_one")
    frame = frame.merge(population_context, on=["subdistrict_id", "subdistrict_name"], validate="one_to_one", suffixes=("", "_population"))
    frame = frame.merge(access_loss, on=["subdistrict_id", "subdistrict_name"], validate="one_to_one", suffixes=("", "_access"))
    frame = frame.merge(
        equity_gap.loc[:, ["subdistrict_id", "equity_gap_ratio"]],
        on="subdistrict_id",
        validate="one_to_one",
    )
    road_group = road_risk.groupby("subdistrict_id")["road_disruption_probability_0_1"]
    road_stats = road_group.agg(["count", "mean", "max"]).reset_index()
    road_stats = road_stats.rename(
        columns={"count": "road_count", "mean": "mean_road_risk", "max": "max_road_risk"}
    )
    bridge_counts = (
        road_risk[road_risk["bridge_flag"].astype(bool)]
        .groupby("subdistrict_id")["road_id"]
        .count()
    )
    road_stats["bridge_count"] = road_stats["subdistrict_id"].map(bridge_counts).fillna(0).astype(int)
    frame = frame.merge(road_stats, on="subdistrict_id", how="left", validate="one_to_one")
    facility_counts = facilities.groupby("subdistrict_id")["facility_id"].count()
    frame["facility_count"] = frame["subdistrict_id"].map(facility_counts).fillna(0).astype(int)

    frame["expected_exposed_population_proxy"] = (
        pd.to_numeric(frame["total_population"])
        * pd.to_numeric(frame["mean_flood_probability_0_1"])
    )
    max_exposure = float(frame["expected_exposed_population_proxy"].max())
    frame["flood_likelihood_0_100"] = (
        pd.to_numeric(frame["mean_flood_probability_0_1"]) * 100.0
    ).round(2)
    frame["exposure_0_100"] = (
        frame["expected_exposed_population_proxy"] / max_exposure * 100.0
        if max_exposure > 0
        else 0.0
    ).round(2)
    access_denominator = pd.to_numeric(frame["total_population_access"], errors="coerce")
    frame["access_gap_0_100"] = (
        pd.to_numeric(frame["people_losing_30_min_access"], errors="coerce")
        .div(access_denominator.where(access_denominator > 0))
        .fillna(0.0)
        .mul(100.0)
        .clip(0.0, 100.0)
        .round(2)
    )
    frame["road_criticality_0_100"] = (
        (0.5 * frame["mean_road_risk"] + 0.5 * frame["max_road_risk"])
        .fillna(0.0)
        .mul(100.0)
        .clip(0.0, 100.0)
        .round(2)
    )
    frame["vulnerability_context_0_100"] = (
        pd.to_numeric(frame["total_vulnerable_population"])
        .div(pd.to_numeric(frame["total_population"]).where(pd.to_numeric(frame["total_population"]) > 0))
        .fillna(0.0)
        .mul(100.0)
        .clip(0.0, 100.0)
        .round(2)
    )
    frame["confidence_class"] = "low"
    frame["source_name"] = (
        "CDSE Sentinel-1; HDX COD-AB; WorldPop 2020; OSM/Geofabrik; Copernicus DEM GLO-30"
    )
    frame["source_timestamp"] = "2024-09-15T23:16:01Z"
    frame["assumptions"] = (
        "Real open context joined at COD-AB ADM3 grain. Flood probability is a "
        "non-ML Sentinel-1 candidate calibrated only against a nearby cross-border "
        "manual weak reference. Exposure is a relative WorldPop probability proxy; "
        "road disruption and access loss are heuristic; vulnerability is a "
        "terrain/remoteness proxy. Non-operational and not official validation."
    )
    frame["processing_scope"] = "mae_sai_adm3_real_context_candidate"
    frame["reference_status"] = "weak_reference_candidate_cross_border_calibration"
    frame["context_status"] = "real_open_context_joined_with_proxy_vulnerability"
    columns = [
        "subdistrict_id",
        "subdistrict_name",
        "subdistrict_name_th",
        "mean_flood_probability_0_1",
        "p90_flood_probability_0_1",
        "binary_flood_share_0_1",
        "flood_likelihood_0_100",
        "exposure_0_100",
        "access_gap_0_100",
        "road_criticality_0_100",
        "vulnerability_context_0_100",
        "total_population",
        "expected_exposed_population_proxy",
        "people_losing_15_min_access",
        "people_losing_30_min_access",
        "people_losing_60_min_access",
        "equity_gap_ratio",
        "road_count",
        "bridge_count",
        "facility_count",
        "mean_elevation_m",
        "mean_slope_degrees",
        "worldpop_bbox_coverage_rate",
        "road_snap_population_coverage_rate",
        "dem_population_coverage_rate",
        "confidence_class",
        "source_name",
        "source_timestamp",
        "assumptions",
        "processing_scope",
        "reference_status",
        "context_status",
    ]
    return frame.loc[:, columns].sort_values("subdistrict_id").reset_index(drop=True)


def build_context_quality_summary(
    admin_features: Sequence[Mapping[str, object]],
    road_risk: pd.DataFrame,
    road_edges: pd.DataFrame,
    facilities: pd.DataFrame,
    population_context: pd.DataFrame,
    population_nodes: pd.DataFrame,
) -> pd.DataFrame:
    """Build one compact data-quality row for the integrated context lane."""

    return pd.DataFrame(
        [
            {
                "study_area": "Mae Sai district, Chiang Rai, Thailand",
                "admin_feature_count": len(admin_features),
                "admin_id_unique": len(
                    {feature["properties"]["subdistrict_id"] for feature in admin_features}
                )
                == len(admin_features),
                "road_way_count": len(road_risk),
                "road_edge_count": len(road_edges),
                "bridge_way_count": int(road_risk["bridge_flag"].astype(bool).sum()),
                "facility_count": len(facilities),
                "population_node_count": len(population_nodes),
                "worldpop_total_population": round(
                    float(population_context["total_population"].sum()), 3
                ),
                "minimum_worldpop_bbox_coverage_rate": round(
                    float(population_context["worldpop_bbox_coverage_rate"].min()), 4
                ),
                "minimum_road_snap_population_coverage_rate": round(
                    float(population_context["road_snap_population_coverage_rate"].min()), 4
                ),
                "minimum_dem_population_coverage_rate": round(
                    float(population_context["dem_population_coverage_rate"].min()), 4
                ),
                "manual_reference_overlaps_thailand_adm3_candidate": False,
                "confidence_class": "low",
                "warning_text": CONTEXT_WARNING,
                "assumptions": (
                    "Manual weak-reference bbox is north of the COD-AB Thailand "
                    "boundary and is retained only as nearby cross-border calibration evidence."
                ),
            }
        ]
    )


def build_context_quality_report(
    quality: pd.DataFrame,
    decision_inputs: pd.DataFrame,
) -> str:
    """Build a concise Markdown quality report for the real context join."""

    if len(quality) != 1:
        raise MaeSaiContextError("Context quality summary must contain one row.")
    row = quality.iloc[0]
    top = decision_inputs.sort_values(
        ["expected_exposed_population_proxy", "subdistrict_id"],
        ascending=[False, True],
    ).iloc[0]
    return "\n".join(
        [
            "# Mae Sai Real Context Integration Quality Report",
            "",
            f"> {CONTEXT_WARNING}",
            "",
            "## Integration Result",
            "",
            f"- COD-AB ADM3 reporting units: {int(row['admin_feature_count'])}",
            f"- OSM drivable ways: {int(row['road_way_count']):,}",
            f"- Routable road edges: {int(row['road_edge_count']):,}",
            f"- OSM bridge-tagged ways: {int(row['bridge_way_count']):,}",
            f"- OSM candidate facilities: {int(row['facility_count']):,}",
            f"- Road-snapped population nodes: {int(row['population_node_count']):,}",
            f"- WorldPop 2020 aggregate population: {float(row['worldpop_total_population']):,.0f}",
            "",
            "## Coverage And Join Quality",
            "",
            f"- Minimum WorldPop bbox coverage: {float(row['minimum_worldpop_bbox_coverage_rate']):.1%}",
            f"- Minimum road-snap population coverage: {float(row['minimum_road_snap_population_coverage_rate']):.1%}",
            f"- Minimum DEM population coverage: {float(row['minimum_dem_population_coverage_rate']):.1%}",
            f"- Highest expected-exposure proxy: {top['subdistrict_id']} / {top['subdistrict_name']}",
            "",
            "## Material Limitations",
            "",
            "- The manual weak-reference polygon does not overlap the HDX COD-AB Thailand ADM3 candidate geometry; it is nearby cross-border calibration evidence only.",
            "- WorldPop is a 2020 modeled population surface, not a current census.",
            "- OSM roads, bridge tags, and facilities are community-mapped and unverified for emergency operations.",
            "- DEM coverage can be partial along the eastern edge of Mae Sai because the selected N20/E099 tile ends at 100E.",
            "- Vulnerability is a terrain/remoteness proxy, not demographic vulnerability.",
            "- Road risk uses ADM3-level Sentinel-1 mean/P90 proxies rather than segment-level raster intersections.",
            "- Road disruption and access loss are modeled candidates, not observed closures.",
            "",
            f"> {CONTEXT_WARNING}",
            "",
        ]
    )


def find_admin_for_point(
    longitude: float,
    latitude: float,
    admin_features: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    """Return the first ADM3 feature containing a point."""

    for feature in admin_features:
        geometry = feature.get("geometry")
        if isinstance(geometry, Mapping) and point_in_geometry(
            longitude, latitude, geometry
        ):
            return feature
    return None


def point_in_geometry(
    longitude: float,
    latitude: float,
    geometry: Mapping[str, object],
) -> bool:
    """Return whether a point lies inside a GeoJSON Polygon or MultiPolygon."""

    geometry_type = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return _point_in_polygon(longitude, latitude, coordinates)
    if geometry_type == "MultiPolygon":
        return any(
            _point_in_polygon(longitude, latitude, polygon)
            for polygon in coordinates
        )
    raise MaeSaiContextError(f"Unsupported admin geometry type: {geometry_type}")


def geometry_representative_point(
    geometry: Mapping[str, object],
) -> tuple[float, float]:
    """Return a deterministic label point for a Polygon or MultiPolygon."""

    geometry_type = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates", [])
    polygons = [coordinates] if geometry_type == "Polygon" else coordinates
    if geometry_type not in {"Polygon", "MultiPolygon"} or not polygons:
        raise MaeSaiContextError(
            f"Unsupported representative-point geometry: {geometry_type}"
        )
    ranked: list[tuple[float, Sequence[object]]] = []
    for polygon in polygons:
        if not isinstance(polygon, Sequence) or not polygon:
            continue
        ring = polygon[0]
        area, centroid = _ring_area_centroid(ring)
        if centroid is not None:
            ranked.append((abs(area), polygon))
    if not ranked:
        raise MaeSaiContextError("Polygon has no usable exterior ring.")
    polygon = max(ranked, key=lambda item: item[0])[1]
    _, centroid = _ring_area_centroid(polygon[0])
    if centroid is not None and _point_in_polygon(centroid[0], centroid[1], polygon):
        return centroid
    bounds = _geometry_bounds({"type": "Polygon", "coordinates": polygon})
    center = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
    if _point_in_polygon(center[0], center[1], polygon):
        return center
    first = polygon[0][0]
    return float(first[0]), float(first[1])


def haversine_m(
    longitude_a: float,
    latitude_a: float,
    longitude_b: float,
    latitude_b: float,
) -> float:
    """Return great-circle distance in meters."""

    radius = 6_371_000.0
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(math.sqrt(value))


def _features(value: Mapping[str, object], label: str) -> list[Mapping[str, object]]:
    features = value.get("features")
    if not isinstance(features, list) or not features:
        raise MaeSaiContextError(f"{label} GeoJSON must contain features.")
    return [feature for feature in features if isinstance(feature, Mapping)]


def _validate_sar_summary(
    sar_summary: pd.DataFrame,
    admin_features: Sequence[Mapping[str, object]],
) -> None:
    required = (
        "subdistrict_id",
        "subdistrict_name",
        "mean_flood_probability_0_1",
        "p90_flood_probability_0_1",
        "binary_flood_share_0_1",
        "confidence_class",
        "source_timestamp",
    )
    missing = [column for column in required if column not in sar_summary.columns]
    if missing:
        raise MaeSaiContextError(
            "SAR summary is missing required columns: " + ", ".join(missing)
        )
    expected = {str(feature["properties"]["subdistrict_id"]) for feature in admin_features}
    actual = set(sar_summary["subdistrict_id"].astype(str))
    if actual != expected:
        raise MaeSaiContextError("SAR summary ADM3 coverage does not match COD-AB.")


def _complete_access_rows(
    access_loss: pd.DataFrame,
    admin_features: Sequence[Mapping[str, object]],
    population_context: pd.DataFrame,
) -> pd.DataFrame:
    admin = pd.DataFrame(
        [
            {
                "subdistrict_id": feature["properties"]["subdistrict_id"],
                "subdistrict_name": feature["properties"]["subdistrict_name"],
            }
            for feature in admin_features
        ]
    )
    result = admin.merge(
        access_loss,
        on=["subdistrict_id", "subdistrict_name"],
        how="left",
        validate="one_to_one",
    )
    totals = population_context.set_index("subdistrict_id")
    for index, row in result.iterrows():
        subdistrict_id = str(row["subdistrict_id"])
        if pd.isna(row.get("total_population")):
            result.at[index, "total_population"] = float(
                totals.loc[subdistrict_id, "total_population"]
            )
            result.at[index, "total_vulnerable_population"] = float(
                totals.loc[subdistrict_id, "total_vulnerable_population"]
            )
            result.at[index, "total_non_vulnerable_population"] = float(
                totals.loc[subdistrict_id, "total_non_vulnerable_population"]
            )
    loss_columns = [
        column
        for column in result.columns
        if "losing_" in column and column.endswith("_min_access")
    ]
    result[loss_columns] = result[loss_columns].fillna(0.0)
    return result


def _candidate_closure_status(risk: float, bridge_flag: bool) -> str:
    if risk >= 0.35 or (bridge_flag and risk >= 0.25):
        return "candidate_closed"
    if risk >= 0.20:
        return "candidate_delayed"
    return "candidate_open_with_delay"


def _tag_value(tags: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"=>"([^"]+)"', tags)
    return match.group(1) if match else None


def _node_id(coordinate: tuple[float, float]) -> str:
    return f"N-{coordinate[0]:.7f}-{coordinate[1]:.7f}"


def _geometry_bounds(geometry: Mapping[str, object]) -> tuple[float, float, float, float]:
    coordinates: list[tuple[float, float]] = []

    def walk(value: object) -> None:
        if (
            isinstance(value, Sequence)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            coordinates.append((float(value[0]), float(value[1])))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates", []))
    if not coordinates:
        raise MaeSaiContextError("Geometry has no coordinates.")
    xs = [value[0] for value in coordinates]
    ys = [value[1] for value in coordinates]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_polygon(longitude: float, latitude: float, polygon: object) -> bool:
    if not isinstance(polygon, Sequence) or not polygon:
        return False
    outer = polygon[0]
    if not _point_in_ring(longitude, latitude, outer):
        return False
    return not any(
        _point_in_ring(longitude, latitude, hole) for hole in polygon[1:]
    )


def _point_in_ring(longitude: float, latitude: float, ring: object) -> bool:
    if not isinstance(ring, Sequence) or len(ring) < 3:
        return False
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        crosses = (y1 > latitude) != (y2 > latitude)
        if crosses:
            intersection = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < intersection:
                inside = not inside
        previous = current
    return inside


def _ring_area_centroid(
    ring: object,
) -> tuple[float, tuple[float, float] | None]:
    if not isinstance(ring, Sequence) or len(ring) < 3:
        return 0.0, None
    area_twice = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        cross = x1 * y2 - x2 * y1
        area_twice += cross
        centroid_x += (x1 + x2) * cross
        centroid_y += (y1 + y2) * cross
        previous = current
    if abs(area_twice) < 1e-12:
        return 0.0, None
    return (
        area_twice / 2.0,
        (
            centroid_x / (3.0 * area_twice),
            centroid_y / (3.0 * area_twice),
        ),
    )
