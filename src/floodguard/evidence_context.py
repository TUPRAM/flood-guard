"""Checksum-bound OSM/WorldPop inputs for local, non-operational scenarios."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from floodguard.evidence_scenarios import (
    FACILITY_SNAP_LIMIT_M,
    MODELLED_ROAD_SPEED_KMH,
    POPULATION_SNAP_LIMIT_M,
    allocate_shelter_capacity,
    calculate_total_access,
    evidence_assessment,
)
from floodguard.open_context_extract import _run_ogr2ogr, find_qgis_bin

ROAD_CLASSES = {
    **{key: key for key in MODELLED_ROAD_SPEED_KMH},
    "motorway_link": "motorway",
    "trunk_link": "trunk",
    "primary_link": "primary",
    "secondary_link": "secondary",
    "tertiary_link": "tertiary",
    "service": "local",
    "living_street": "local",
    "road": "local",
    "track": "local",
}
OSM_FACILITY_TYPES = {
    "hospital": "healthcare",
    "clinic": "healthcare",
    "doctors": "healthcare",
    "pharmacy": "healthcare",
    "shelter": "shelter_context",
}
TO_METRES = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)


class EvidenceContextError(ValueError):
    """Raised when a source or spatial contract cannot support the scenario."""


def build_context_inputs(
    context_root: str | Path,
    aoi_geometry: Mapping[str, Any],
    routing_geometry: Mapping[str, Any],
    facilities: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build real context inputs using existing national source files only.

    Geometries must be WGS84 polygons, Features, or FeatureCollections. Routing
    context must cover the demand AOI (use district/basin context for core AOIs).
    Supplied facilities require facility_id and longitude/latitude, lon/lat, or
    Point geometry. Capacity may be null. identity_reconciled defaults false.
    Supplied and separately extracted OSM facilities never merge automatically.
    Files are written only under output_dir; source files are never modified.
    """
    aoi = _polygon(aoi_geometry)
    routing = _polygon(routing_geometry)
    if not routing.buffer(1e-9).covers(aoi):
        raise EvidenceContextError("routing geometry must contain the demand AOI")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    sources, metadata = _load_sources(Path(context_root))
    hashes = {key: _sha256(path) for key, path in sources.items()}
    for key, details in metadata.items():
        if hashes[key] != details["sha256"]:
            raise EvidenceContextError(f"source checksum changed for {key}")
    routing_hash = _canonical_hash(mapping(routing))
    roads, points = _extract_osm(
        sources["osm"], routing.bounds, target, hashes["osm"], routing_hash
    )
    edges, nodes, road_geojson, topology = _road_graph(roads, routing)
    index = _NodeIndex(nodes)
    population, population_coverage = _population_cells(sources["worldpop"], aoi, index)
    supplied = _snap_facilities(facilities, routing, index)
    osm_raw = _osm_facilities(points)
    osm = _snap_facilities(osm_raw, routing, index)
    assumptions = [
        "WorldPop 2020 is modelled residential population context, not event-year counts or observed evacuation demand.",
        "Demand contains positive raster cells whose centres fall in the AOI; boundary cells are not apportioned.",
        "Routing uses a surrounding district/basin polygon; paths outside that polygon are not evaluated.",
        "Road times use fixed class speeds on an undirected graph; one-way rules, turn restrictions and event passability are not represented.",
        "Only shared original OSM vertex coordinates with compatible layer/bridge/tunnel tags connect. Geometric crossings are never noded.",
        "Conservative grade separation may disconnect bridge approaches; disconnected components remain visible.",
        "100 m facility and 250 m population snaps use EPSG:32647; connector time is modelled at 5 km/h. Connector walkability and barriers are unverified.",
        "OSM healthcare points are candidate destinations. Generic amenity=shelter may be a bus shelter, farm cottage or rest pavilion and is excluded from destination access and shelter capacity.",
        "No flood layer is converted into observed closures or calibrated flood probability.",
    ]
    connection_review = topology.pop("grade_connection_review")
    package = {
        "schema_version": "floodguard.context_scenario_inputs.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_hash_scope": "all_fields_except_generated_at_and_canonical_sha256",
        "source_timestamp": None,
        "confidence_class": "low",
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "analysis_crs": "EPSG:32647",
        "population": population,
        "edges": edges,
        "facilities": supplied,
        "osm_facilities": osm,
        "node_coordinates": nodes,
        "connectivity_review": connection_review,
        "road_geojson": road_geojson,
        "facilities_geojson": _facility_geojson(supplied),
        "osm_facilities_geojson": _facility_geojson(osm),
        "coverage": {
            **population_coverage,
            **topology,
            "supplied_facilities": len(supplied),
            "osm_facilities": len(osm),
            "connected_supplied_facilities": sum(
                row["node_id"] is not None for row in supplied
            ),
            "connected_osm_facilities": sum(row["node_id"] is not None for row in osm),
        },
        "assumptions": assumptions,
        "source_metadata": metadata,
        "input_hashes": {
            **hashes,
            "aoi_geometry": _canonical_hash(mapping(aoi)),
            "routing_geometry": routing_hash,
            "supplied_facilities": _canonical_hash(list(facilities)),
            "extracted_osm_roads": _canonical_hash(roads),
            "extracted_osm_points": _canonical_hash(points),
        },
    }
    package["canonical_sha256"] = _context_content_hash(package)
    _write_json(target / "context_inputs.json", package)
    return package


def build_context_scenarios(
    input_dict: Mapping[str, Any],
    aoi_id: str,
    *,
    facility_source: str = "supplied",
    capacity_participation_fraction: float = 0.10,
) -> dict[str, Any]:
    """Evaluate four access families and separate shelter capacity experiments.

    Candidates use one deterministic baseline shortest-path tree and demand
    relevance. Their post-intervention outcomes do not select the candidates.
    Only reconciled shelter identities with numeric planned capacity enter the
    25/50/100 percent planned-capacity experiment; fixed 50/100/200 capacities
    apply only to reviewed unique shelter identities. Otherwise an explicitly
    hypothetical single temporary shelter supplies the capacity experiment.
    """
    if facility_source not in {"supplied", "osm"}:
        raise EvidenceContextError("facility_source must be supplied or osm")
    population = [dict(row, subdistrict_id=aoi_id) for row in input_dict["population"]]
    edges = input_dict["edges"]
    facilities = input_dict[
        "osm_facilities" if facility_source == "osm" else "facilities"
    ]
    facilities = [
        row
        for row in facilities
        if row.get("facility_type") in {"healthcare", "shelter", "shelter_candidate"}
    ]
    assumptions = [
        *input_dict["assumptions"],
        f"Destination source for this scenario family is explicitly {facility_source}.",
    ]
    baseline = calculate_total_access(
        population, edges, facilities, assumptions=assumptions
    )
    from .evidence_interventions import (
        intervention_effect_summary,
        select_interventions,
    )

    selection = select_interventions(population, edges, facilities, baseline)
    chosen_node = selection["hypothetical_added_node"]
    closed = selection["closed_edge_id"]
    removed = selection["removed_facility_id"]
    changes = {
        "close_edge": {"closed_edge_ids": [closed]} if closed else None,
        "remove_destination": {"removed_facility_ids": [removed]} if removed else None,
        "add_destination": {
            "added_facilities": [
                {
                    "facility_id": "scenario-added-destination",
                    "node_id": chosen_node,
                    "snap_distance_m": 0.0,
                    "facility_type": "shelter_candidate",
                    "capacity": None,
                    "synthetic": True,
                }
            ]
        }
        if chosen_node
        else None,
    }
    access = {"baseline": baseline}
    for name, change in changes.items():
        access[name] = (
            calculate_total_access(
                population,
                edges,
                facilities,
                scenario=change,
                assumptions=assumptions,
                baseline_result=baseline,
            )
            if change
            else {
                "status": "unavailable",
                "reason": "No eligible graph node/edge/destination for this scenario.",
            }
        )
    shelters = [
        row
        for row in facilities
        if row.get("facility_type") in {"shelter", "shelter_candidate"}
        and row.get("identity_reconciled") is True
        and row.get("capacity_scenario_eligible", True) is True
    ]
    hypothetical_capacity_site = None
    capacity_node = selection["hypothetical_capacity_node"]
    capacity_assumptions = list(assumptions)
    capacity_pairs_source = baseline["baseline_reachable_pairs"]
    if not shelters and capacity_node is not None:
        coordinate = input_dict.get("node_coordinates", {}).get(capacity_node)
        hypothetical_capacity_site = {
            "facility_id": "scenario-temporary-shelter",
            "node_id": capacity_node,
            "snap_distance_m": 0.0,
            "facility_type": "shelter_candidate",
            "capacity": None,
            "identity_reconciled": False,
            "synthetic": True,
            "coordinates": coordinate,
            "activation_status": "hypothetical_scenario_only",
            "selection_reason": selection["selection_reason"]["capacity_site"],
        }
        shelters = [hypothetical_capacity_site]
        capacity_assumptions.append(
            "No reviewed unique shelter identity is available for capacity analysis. Experiments use one hypothetical temporary shelter at the selected demand node, not a healthcare facility or duplicated source rows."
        )
        capacity_pairs_source = calculate_total_access(
            population, edges, shelters, assumptions=capacity_assumptions
        )["baseline_reachable_pairs"]
    shelter_ids = {row["facility_id"] for row in shelters}
    shelter_pairs = [
        pair for pair in capacity_pairs_source if pair["facility_id"] in shelter_ids
    ]
    capacity = []
    from .evidence_population_review import build_capacity_demand

    demand = build_capacity_demand(
        population,
        demand_basis="residential_participation",
        participation_fraction=capacity_participation_fraction,
        assumption_id="capacity_residential_participation_v1",
    )
    demand_summary = {
        key: value for key, value in demand.items() if key != "population_rows"
    }
    capacity_site_assumptions = list(capacity_assumptions)
    capacity_assumptions.append(
        f"Only an assumed {capacity_participation_fraction:.0%} of modelled residential population participates; actual evacuation demand is unknown."
    )
    if shelters:
        for amount in (50, 100, 200):
            result = allocate_shelter_capacity(
                demand["population_rows"],
                [{**row, "capacity": amount} for row in shelters],
                shelter_pairs,
                assumptions=[
                    *capacity_assumptions,
                    f"Each candidate shelter is assumed to offer {amount} places; this is not reported available capacity.",
                ],
            )
            capacity.append(
                {
                    "scenario_id": f"assumed_{amount}_per_candidate",
                    "title": f"Hypothetical temporary shelter: {amount} places / {capacity_participation_fraction:.0%} participation"
                    if hypothetical_capacity_site
                    else f"Assumed {amount} places per candidate shelter / {capacity_participation_fraction:.0%} participation",
                    **result,
                    "demand_assumptions": demand_summary,
                }
            )
    reconciled = [
        row
        for row in shelters
        if row.get("identity_reconciled") is True and row.get("capacity") is not None
    ]
    planned_ids = {row["facility_id"] for row in reconciled}
    if reconciled:
        for fraction in (0.25, 0.5, 1.0):
            result = allocate_shelter_capacity(
                demand["population_rows"],
                [{**row, "capacity": row["capacity"] * fraction} for row in reconciled],
                [pair for pair in shelter_pairs if pair["facility_id"] in planned_ids],
                assumptions=[
                    *capacity_assumptions,
                    f"Scenario makes {fraction:.0%} of reconciled planned shelter capacity available.",
                ],
            )
            capacity.append(
                {
                    "scenario_id": f"planned_capacity_{int(fraction * 100)}pct",
                    "title": f"Assumed availability: {int(fraction * 100)}% of reconciled planned capacity",
                    **result,
                    "demand_assumptions": demand_summary,
                }
            )
    participation_sensitivity = []
    if shelters:
        for fraction in (0.05, 0.10, 0.25):
            sensitivity_demand = build_capacity_demand(
                population,
                demand_basis="residential_participation",
                participation_fraction=fraction,
                assumption_id="capacity_residential_participation_v1",
            )
            allocation = allocate_shelter_capacity(
                sensitivity_demand["population_rows"],
                [{**row, "capacity": 100} for row in shelters],
                shelter_pairs,
                assumptions=[
                    *capacity_site_assumptions,
                    f"Sensitivity assumes {fraction:.0%} residential participation; each hypothetical/reviewed shelter is assigned 100 places. Actual evacuation demand is unknown.",
                ],
            )
            participation_sensitivity.append(
                {
                    "scenario_id": f"participation_{int(fraction * 100)}pct_capacity_100",
                    "title": f"Assumed {fraction:.0%} participation / 100 places per scenario shelter",
                    "demand_assumptions": {
                        key: value
                        for key, value in sensitivity_demand.items()
                        if key != "population_rows"
                    },
                    **allocation,
                }
            )
    effects = intervention_effect_summary(access)
    # All-OD pairs are intermediate allocator inputs, not four duplicate exports.
    # The standalone calculator preserves its public pairs API.
    for result in access.values():
        result.pop("baseline_reachable_pairs", None)
        result.pop("scenario_reachable_pairs", None)
    return {
        "schema_version": "floodguard.context_scenarios.v1",
        "aoi_id": aoi_id,
        "source_timestamp": None,
        "confidence_class": "low",
        "evidence_role": "scenario",
        "operational_status": "non_operational",
        "official_warning": False,
        "facility_source": facility_source,
        "source_input_sha256": input_dict.get("canonical_sha256"),
        "assumptions": assumptions,
        "stress_selection": selection,
        "intervention_effects": effects,
        "intermediate_pair_export": "omitted_recomputable_from_hash_bound_context_inputs",
        "access_scenarios": access,
        "capacity_scenarios": capacity,
        "capacity_participation_sensitivity": participation_sensitivity,
        "capacity_demand_assumptions": demand_summary,
        "scenario_assessments": {
            name: _access_assessment(result, aoi_id, assumptions)
            for name, result in access.items()
        },
        "hypothetical_capacity_site": hypothetical_capacity_site,
        "capacity_status": "scenario_only"
        if shelters
        else "unavailable_no_candidate_shelters",
        "planned_capacity_status": "scenario_only"
        if reconciled
        else "unavailable_no_reconciled_numeric_planned_capacity",
        "assessment": evidence_assessment({}, area_id=aoi_id, assumptions=assumptions),
    }


def _access_assessment(
    result: Mapping[str, Any], aoi_id: str, assumptions: Sequence[str]
) -> dict[str, Any]:
    transform_id = "scenario_30min_inaccessible_share_v1"
    totals = result.get("totals")
    if not isinstance(totals, Mapping):
        return {
            "assessment_status": "unavailable",
            "transform_id": transform_id,
            "fpps_0_100": None,
            "action_class": None,
            "reason": "The access scenario is unavailable.",
        }
    excluded = totals["unconnected_population"]
    included = totals["total_population"] - excluded
    if included <= 0:
        return {
            "assessment_status": "unavailable",
            "transform_id": transform_id,
            "fpps_0_100": None,
            "action_class": None,
            "reason": "No population is connected within the declared snap limit.",
        }
    inaccessible = (
        totals["people_already_without_30_min_access"]
        - excluded
        + totals["people_losing_30_min_access"]
        - totals["people_gaining_30_min_access"]
    )
    share = min(100.0, max(0.0, 100 * inaccessible / included))
    assessment = evidence_assessment(
        {"access_gap_0_100": share},
        area_id=aoi_id,
        assumptions=[
            *assumptions,
            "Experimental access component is the 30-minute inaccessible share of graph-connected population. Other FPPS inputs remain unknown; sensitivity completions are scenarios only.",
        ],
    )
    assessment["component_derivation"] = {
        "transform_id": transform_id,
        "component": "access_gap_0_100",
        "threshold_minutes": 30,
        "included_population": included,
        "excluded_unconnected_population": excluded,
        "scenario_inaccessible_population": max(0.0, min(included, inaccessible)),
        "formula": "100 * (already_without_30 - unconnected + losing_30 - gaining_30) / (total - unconnected)",
    }
    return assessment


def _load_sources(
    context_root: Path,
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    root = (
        context_root / "open_context"
        if (context_root / "open_context").exists()
        else context_root
    )
    paths = {
        "osm": root / "osm_geofabrik" / "thailand-latest.osm.pbf",
        "worldpop": root / "worldpop_population" / "tha_ppp_2020.tif",
    }
    manifest = (
        Path(__file__).resolve().parents[2]
        / "outputs"
        / "open_context_data_file_manifest.csv"
    )
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["source_group"]: row for row in csv.DictReader(handle)}
    metadata = {}
    for key, group in (("osm", "osm_geofabrik"), ("worldpop", "worldpop_population")):
        if not paths[key].is_file():
            raise EvidenceContextError(f"existing {key} context file is unavailable")
        row = rows[group]
        if (
            row["processing_allowed"].lower() != "true"
            or row["sha256_status"] != "recorded"
        ):
            raise EvidenceContextError(
                f"source manifest does not permit context processing for {key}"
            )
        metadata[key] = {
            field: row[field]
            for field in (
                "source_name",
                "source_url",
                "download_url",
                "sha256",
                "license_status",
                "retrieved_at_utc",
            )
        }
        metadata[key]["processing_scope"] = row["processing_scope"]
    return paths, metadata


def ogr_runtime_identity(bin_dir: Path | None = None) -> dict[str, str]:
    """Identify the separate OSM-extraction GDAL executable without exposing paths."""
    directory = bin_dir or find_qgis_bin()
    executable = directory / ("ogr2ogr.exe" if os.name == "nt" else "ogr2ogr")
    environment = {
        **os.environ,
        "PATH": str(directory) + os.pathsep + os.environ.get("PATH", ""),
    }
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EvidenceContextError(
            "Unable to identify the OSM extraction GDAL runtime"
        ) from error
    version = re.search(r"\bGDAL\s+(\d+\.\d+(?:\.\d+)?)", result.stdout)
    if result.returncode != 0 or version is None:
        raise EvidenceContextError("Unable to identify the OSM extraction GDAL runtime")
    return {"gdal_version": version.group(1), "executable_sha256": _sha256(executable)}


def _extract_osm(
    pbf: Path,
    bounds: Sequence[float],
    target: Path,
    source_hash: str,
    routing_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = target / "osm_extraction_receipt.json"
    outputs = {
        "roads": target / "osm_roads.geojson",
        "points": target / "osm_points.geojson",
    }
    bin_dir = find_qgis_bin()
    expected = {
        "pbf_sha256": source_hash,
        "routing_geometry_sha256": routing_hash,
        "method": "gdal_osm_bbox_filter_v1",
        "ogr_runtime": ogr_runtime_identity(bin_dir),
    }
    if receipt.exists() and all(path.exists() for path in outputs.values()):
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if all(saved.get(key) == value for key, value in expected.items()) and all(
            saved.get(f"{key}_sha256") == _sha256(path) for key, path in outputs.items()
        ):
            return tuple(
                json.loads(outputs[key].read_text(encoding="utf-8"))
                for key in ("roads", "points")
            )
    for key, layer, where in (
        ("roads", "lines", "highway IS NOT NULL"),
        ("points", "points", "other_tags LIKE '%amenity%'"),
    ):
        _run_ogr2ogr(
            bin_dir,
            [
                "-f",
                "GeoJSON",
                "-spat",
                *[str(value) for value in bounds],
                "-where",
                where,
                "-lco",
                "RFC7946=YES",
                str(outputs[key]),
                str(pbf),
                layer,
            ],
        )
    _write_json(
        receipt,
        {
            **expected,
            **{f"{key}_sha256": _sha256(path) for key, path in outputs.items()},
        },
    )
    return tuple(
        json.loads(outputs[key].read_text(encoding="utf-8"))
        for key in ("roads", "points")
    )


def _polygon(value: Mapping[str, Any]):
    if value.get("type") == "FeatureCollection":
        geometry = unary_union(
            [shape(feature["geometry"]) for feature in value["features"]]
        )
    else:
        geometry = shape(value["geometry"] if value.get("type") == "Feature" else value)
    if (
        geometry.is_empty
        or not geometry.is_valid
        or geometry.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise EvidenceContextError(
            "AOI/routing geometry must be valid nonempty polygons"
        )
    west, south, east, north = geometry.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise EvidenceContextError("geometry must use WGS84 longitude/latitude")
    return geometry


def _tags(properties: Mapping[str, Any]) -> dict[str, str]:
    result = {
        str(key): str(value)
        for key, value in properties.items()
        if value is not None and key != "other_tags"
    }
    for key, value in re.findall(
        r'"([^"\\]+)"=>"([^"\\]*)"', str(properties.get("other_tags", ""))
    ):
        result[key] = value
    return result


def _road_graph(
    geojson: Mapping[str, Any], routing
) -> tuple[
    list[dict[str, Any]], dict[str, list[float]], dict[str, Any], dict[str, Any]
]:
    edges, features = [], []
    nodes: dict[str, list[float]] = {}
    node_review = {}
    omitted = 0
    road_ids = set()
    for feature in sorted(
        geojson["features"],
        key=lambda item: str(item.get("properties", {}).get("osm_id", "")),
    ):
        tags = _tags(feature.get("properties", {}))
        road_class = ROAD_CLASSES.get(tags.get("highway", ""))
        if (
            road_class is None
            or tags.get("access") in {"no", "private"}
            or tags.get("motor_vehicle") == "no"
        ):
            continue
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "LineString":
            continue
        osm_id = tags.get("osm_id")
        if not osm_id or osm_id in road_ids:
            raise EvidenceContextError("OSM road IDs must be present and unique")
        road_ids.add(osm_id)
        grade = (
            tags.get("layer", "0"),
            tags.get("bridge", "no"),
            tags.get("tunnel", "no"),
        )
        coordinates = geometry["coordinates"]
        for offset, (start, end) in enumerate(pairwise(coordinates)):
            segment = LineString([start[:2], end[:2]])
            if segment.length == 0 or not routing.covers(segment):
                omitted += 1
                continue
            points = []
            for endpoint, coordinate in enumerate((start, end)):
                position = [float(coordinate[0]), float(coordinate[1])]
                node_id = "osm-node-" + _canonical_hash([position, grade])[:20]
                nodes[node_id] = position
                review = node_review.setdefault(
                    node_id,
                    {"grade": list(grade), "way_ids": set(), "endpoint_way_ids": set()},
                )
                review["way_ids"].add(osm_id)
                if (endpoint == 0 and offset == 0) or (
                    endpoint == 1 and offset == len(coordinates) - 2
                ):
                    review["endpoint_way_ids"].add(osm_id)
                points.append(node_id)
            length = transform(TO_METRES.transform, segment).length
            edge_id = f"osm-way-{osm_id}-segment-{offset}"
            row = {
                "edge_id": edge_id,
                "from_node": points[0],
                "to_node": points[1],
                "length_m": length,
                "road_class": road_class,
                "normal_minutes": length
                / 1000
                / MODELLED_ROAD_SPEED_KMH[road_class]
                * 60,
                "osm_way_id": osm_id,
                "bridge": grade[1],
                "layer": grade[0],
                "tunnel": grade[2],
            }
            edges.append(row)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        **row,
                        "evidence_role": "historical_context",
                        "condition_status": "unknown_not_observed",
                    },
                    "geometry": mapping(segment),
                }
            )
    import networkx as nx

    graph = nx.Graph()
    graph.add_edges_from((row["from_node"], row["to_node"]) for row in edges)
    return (
        edges,
        nodes,
        {"type": "FeatureCollection", "features": features},
        {
            "road_edges": len(edges),
            "road_nodes": len(nodes),
            "connected_components": nx.number_connected_components(graph),
            "segments_omitted_at_routing_boundary_or_degenerate": omitted,
            "topology_method": "shared_original_vertex_and_compatible_grade_no_crossing_noding",
            "grade_connection_review": _grade_connection_review(
                nodes, node_review, graph
            ),
        },
    )


def _grade_connection_review(nodes, details, graph) -> dict[str, Any]:
    """Diagnose equal-coordinate grade splits; never bridge them automatically."""
    import networkx as nx

    positions = {}
    for node, coordinate in nodes.items():
        positions.setdefault(tuple(coordinate), []).append(node)
    components = {}
    for component in nx.connected_components(graph):
        identifier = min(component)
        components.update({node: identifier for node in component})
    rows = []
    for coordinate, group in sorted(positions.items()):
        if len(group) < 2:
            continue
        variants = [
            {
                "node_id": node,
                "grade": details[node]["grade"],
                "way_ids": sorted(details[node]["way_ids"]),
                "endpoint_way_ids": sorted(details[node]["endpoint_way_ids"]),
                "component_id": components[node],
            }
            for node in sorted(group)
        ]
        endpoint_candidate = all(row["endpoint_way_ids"] for row in variants)
        rows.append(
            {
                "coordinates": list(coordinate),
                "nodes": variants,
                "distinct_components": len({row["component_id"] for row in variants}),
                "review_class": "possible_shared_endpoint_grade_transition"
                if endpoint_candidate
                else "coincident_grade_separated_vertices",
                "automatic_connection": False,
            }
        )
    return {
        "method": "same_original_coordinate_grade_split_review_v1",
        "shared_coordinate_grade_split_count": len(rows),
        "possible_endpoint_transition_count": sum(
            row["review_class"] == "possible_shared_endpoint_grade_transition"
            for row in rows
        ),
        "different_component_split_count": sum(
            row["distinct_components"] > 1 for row in rows
        ),
        "review_candidates": rows[:100],
        "candidate_display_limit": 100,
        "connections_added": 0,
        "interpretation": "These are review candidates, not confirmed junctions. Exact coordinates and endpoint tags do not establish shared OSM node identity or traversability. Verify original node IDs/grade continuity before connecting; interior crossings and river/grade gaps remain disconnected.",
    }


class _NodeIndex:
    def __init__(self, nodes: Mapping[str, Sequence[float]]):
        self.ids = sorted(nodes)
        self.points = [Point(TO_METRES.transform(*nodes[key])) for key in self.ids]
        self.tree = STRtree(self.points) if self.points else None

    def snap(
        self, longitude: float, latitude: float, limit: float
    ) -> tuple[str | None, float | None]:
        if self.tree is None:
            return None, None
        point = Point(TO_METRES.transform(longitude, latitude))
        nearest = int(self.tree.nearest(point))
        distance = float(point.distance(self.points[nearest]))
        # Resolve equidistant nodes in a stable order, without joining components.
        if distance <= limit:
            matches = self.tree.query(point.buffer(distance + 1e-7))
            nearest = min(
                (int(index) for index in matches),
                key=lambda index: (
                    round(point.distance(self.points[index]), 7),
                    self.ids[index],
                ),
            )
        return (self.ids[nearest] if distance <= limit else None), distance


def _population_cells(
    path: Path, aoi, index: _NodeIndex
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise EvidenceContextError("WorldPop must have one band and a declared CRS")
        local_geometry = transform_geom("EPSG:4326", dataset.crs, mapping(aoi))
        try:
            raster, affine = mask(
                dataset, [local_geometry], crop=True, filled=False, all_touched=False
            )
        except ValueError as exc:
            raise EvidenceContextError(
                "WorldPop raster does not overlap demand AOI"
            ) from exc
        values = raster[0]
        inside = geometry_mask(
            [local_geometry],
            out_shape=values.shape,
            transform=affine,
            invert=True,
            all_touched=False,
        )
        valid = (
            inside
            & ~np.ma.getmaskarray(values)
            & np.isfinite(values.data)
            & (values.data >= 0)
        )
        transformer = Transformer.from_crs(dataset.crs, "EPSG:4326", always_xy=True)
        population = []
        for row, column in np.argwhere(valid & (values.data > 0)):
            x, y = rasterio.transform.xy(affine, int(row), int(column))
            lon, lat = transformer.transform(x, y)
            node, distance = index.snap(lon, lat, POPULATION_SNAP_LIMIT_M)
            population.append(
                {
                    "population_id": f"worldpop2020-{lon:.8f}-{lat:.8f}",
                    "subdistrict_id": "aoi-demand-not-administrative-unit",
                    "total_population": float(values.data[row, column]),
                    "node_id": node,
                    "snap_distance_m": distance,
                    "longitude": lon,
                    "latitude": lat,
                    "population_reference_year": 2020,
                    "population_role": "modelled_residential_context",
                }
            )
        total = math.fsum(row["total_population"] for row in population)
        connected = math.fsum(
            row["total_population"] for row in population if row["node_id"] is not None
        )
        return population, {
            "population_cells": len(population),
            "modelled_population_2020": total,
            "population_connected_within_250m": connected,
            "population_unconnected": total - connected,
            "population_snap_coverage_fraction": connected / total if total else None,
            "aoi_raster_cells": int(inside.sum()),
            "valid_population_cells_including_zero": int(valid.sum()),
            "missing_or_invalid_population_cells": int((inside & ~valid).sum()),
        }


def _osm_facilities(points: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for feature in points.get("features", []):
        tags = _tags(feature.get("properties", {}))
        facility_type = OSM_FACILITY_TYPES.get(tags.get("amenity", ""))
        if facility_type is None or feature.get("geometry", {}).get("type") != "Point":
            continue
        osm_id = tags.get("osm_id")
        if not osm_id:
            raise EvidenceContextError("OSM facility has no source ID")
        result.append(
            {
                "facility_id": f"OSM-node-{osm_id}",
                "name": tags.get("name", "Unnamed OSM candidate"),
                "facility_type": facility_type,
                "geometry": feature["geometry"],
                "capacity": None,
                "identity_reconciled": False,
                "source_name": "OpenStreetMap contributors via Geofabrik",
                "source_license": "ODbL-1.0",
                "activation_status": "unknown",
                "osm_amenity": tags.get("amenity"),
                "osm_shelter_type": tags.get("shelter_type"),
                "source_description": tags.get(
                    "description:en", tags.get("description")
                ),
                "candidate_destination_eligible": facility_type == "healthcare",
                "emergency_shelter_role": "not_established_by_generic_osm_tag",
            }
        )
    return result


def _snap_facilities(
    rows: Sequence[Mapping[str, Any]], routing, index: _NodeIndex
) -> list[dict[str, Any]]:
    output, identifiers = [], set()
    for source in rows:
        row = dict(source)
        identifier = row.get("facility_id")
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier in identifiers
        ):
            raise EvidenceContextError(
                "facility IDs must be nonempty and unique within their source"
            )
        identifiers.add(identifier)
        if row.get("geometry", {}).get("type") == "Point":
            lon, lat = row["geometry"]["coordinates"][:2]
        else:
            lon, lat = (
                row.get("longitude", row.get("lon")),
                row.get("latitude", row.get("lat")),
            )
        try:
            lon, lat = float(lon), float(lat)
        except (ValueError, TypeError) as exc:
            raise EvidenceContextError(
                f"facility {identifier} needs Point coordinates"
            ) from exc
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise EvidenceContextError(
                f"invalid WGS84 coordinates for facility {identifier}"
            )
        capacity = row.get("capacity")
        if capacity is not None:
            try:
                if isinstance(capacity, bool):
                    raise TypeError("boolean capacity")
                capacity = float(capacity)
            except (ValueError, TypeError) as exc:
                raise EvidenceContextError(
                    f"facility {identifier} capacity must be numeric or null"
                ) from exc
            if not math.isfinite(capacity) or capacity < 0:
                raise EvidenceContextError(
                    f"facility {identifier} capacity must be finite and nonnegative"
                )
        in_context = routing.covers(Point(lon, lat))
        node, distance = (
            index.snap(lon, lat, FACILITY_SNAP_LIMIT_M) if in_context else (None, None)
        )
        output.append(
            {
                **row,
                "longitude": lon,
                "latitude": lat,
                "node_id": node,
                "snap_distance_m": distance,
                "within_routing_context": in_context,
                "capacity": capacity,
                "identity_reconciled": row.get("identity_reconciled") is True,
                "connector_walkability": "unverified_scenario_assumption",
            }
        )
    return sorted(output, key=lambda row: row["facility_id"])


def _facility_geojson(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    key: value for key, value in row.items() if key != "geometry"
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
            }
            for row in rows
        ],
    }


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _context_content_hash(value: Mapping[str, Any]) -> str:
    return _canonical_hash(
        {
            key: item
            for key, item in value.items()
            if key not in {"generated_at", "canonical_sha256"}
        }
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )
