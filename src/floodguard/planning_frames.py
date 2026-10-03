"""Planning frames for protocol v1b open item OI-09: pf-07 (case SE2) and the SE2-blind units.

The owners adopted the rules of owner choice 15 on 3 October 2026 (decision log
R12, all 23 choices as recommended):

* **pf-07 unit list:** every COD-AB ``tha_admin3`` unit of Mueang Chiang Rai
  district (TH5701).
* **SE2 routing geometry:** the union of those units, buffered by 3 km in
  EPSG:32647 and clipped to Thailand (COD-AB ``tha_admin0``).
* **SE2 hospitals:** every OSM hospital whose routing point lies inside that
  geometry. "OSM hospital" and "routing point" are the ones
  ``floodguard.evidence_context.build_context_inputs`` uses, so the list is the
  one a context build on that geometry would see.
* **SE2-blind units:** the tambon that holds the district office of the blind
  district, and every tambon of that district that touches it (option B).

The functions here are pure: they take boundary rows, geometries and OSM
features that were already read, so they run on fixtures.
``scripts/build_planning_frames.py`` reads the inputs and writes the files.
Nothing here reads a flood layer or computes an exposure, an access result, an
FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from floodguard.evidence_context import _tags

ROUTING_BUFFER_M = 3000.0
BUFFER_QUAD_SEGS = 16
METRIC_EPSG = 32647
# Thai "district office" (thi wa kan amphoe) and "district office" (samnak ngan amphoe),
# written as escapes so the source stays ASCII.
DISTRICT_OFFICE_PREFIX_TH = "ที่ว่าการอำเภอ"
DISTRICT_OFFICE_ALT_PREFIX_TH = "สำนักงานอำเภอ"
UNIT_FIELDS = ("adm3_pcode", "adm3_name", "adm3_name_th", "adm2_pcode", "adm2_name", "adm1_pcode")


class PlanningFrameError(ValueError):
    """Raised when a frame input is malformed or a rule cannot pick a unique answer."""


def district_units(rows: Sequence[Mapping[str, Any]], adm2_pcode: str) -> list[dict[str, Any]]:
    """Return every unit of one district, sorted by ``adm3_pcode``.

    Args:
        rows: Boundary rows with the keys of ``UNIT_FIELDS`` and a shapely ``geometry``.
        adm2_pcode: The district code, for example ``"TH5701"``.

    Returns:
        Copies of the district's rows, sorted by unit code.

    Raises:
        PlanningFrameError: when the district has no unit, a code repeats or a geometry is empty or invalid.
    """

    selected = [dict(row) for row in rows if row["adm2_pcode"] == adm2_pcode]
    if not selected:
        raise PlanningFrameError(f"no unit of district {adm2_pcode}")
    codes = [row["adm3_pcode"] for row in selected]
    if len(codes) != len(set(codes)):
        raise PlanningFrameError(f"a unit code repeats in district {adm2_pcode}")
    for row in selected:
        geometry = row["geometry"]
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            raise PlanningFrameError(f"unit {row['adm3_pcode']} has an empty or invalid geometry")
        if not str(row["adm3_pcode"]).startswith(adm2_pcode):
            raise PlanningFrameError(f"unit {row['adm3_pcode']} does not carry its district code")
    return sorted(selected, key=lambda row: row["adm3_pcode"])


def routing_geometry(
    unit_geometries_metric: Sequence[BaseGeometry],
    to_wgs84: Callable[[BaseGeometry], BaseGeometry],
    country_wgs84: BaseGeometry,
    buffer_m: float = ROUTING_BUFFER_M,
    quad_segs: int = BUFFER_QUAD_SEGS,
) -> BaseGeometry:
    """Union the units and buffer the union in a metric CRS, then clip it to the country in WGS84.

    Args:
        unit_geometries_metric: The frame's unit polygons in a metric CRS (EPSG:32647).
        to_wgs84: Projects a metric geometry back to WGS84.
        country_wgs84: The country polygon in WGS84 (COD-AB ``tha_admin0``).
        buffer_m: Buffer distance in metres.
        quad_segs: Segments per quarter circle of the buffer.

    Raises:
        PlanningFrameError: when there is no unit, the distance is not positive or the result is empty or invalid.
    """

    if not unit_geometries_metric:
        raise PlanningFrameError("no unit geometry to buffer")
    if not buffer_m > 0:
        raise PlanningFrameError("the buffer distance must be positive")
    buffered = unary_union(list(unit_geometries_metric)).buffer(buffer_m, quad_segs=quad_segs)
    clipped = to_wgs84(buffered).intersection(country_wgs84)
    if clipped.is_empty or not clipped.is_valid or clipped.geom_type not in {"Polygon", "MultiPolygon"}:
        raise PlanningFrameError("the routing geometry is empty or invalid")
    return clipped


def osm_identifier(tags: Mapping[str, str], geometry_type: str) -> str:
    """Name an OSM object the way ``evidence_context._osm_facilities`` does: OSM-node-, -way- or -relation-<id>."""

    if geometry_type == "Point":
        kind, osm_id = "node", tags.get("osm_id")
    elif tags.get("osm_way_id"):
        kind, osm_id = "way", tags.get("osm_way_id")
    else:
        kind, osm_id = "relation", tags.get("osm_id")
    if not osm_id:
        raise PlanningFrameError("an OSM object has no source ID")
    return f"OSM-{kind}-{osm_id}"


def _point_of(geometry: BaseGeometry) -> BaseGeometry:
    return geometry if geometry.geom_type == "Point" else geometry.representative_point()


def hospitals_inside(
    facilities: Sequence[Mapping[str, Any]],
    routing: BaseGeometry,
    english_names: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Keep the OSM hospitals whose routing point the routing geometry covers.

    Args:
        facilities: Rows from ``evidence_context._osm_facilities`` (``facility_id``, ``name``,
            ``service_type``, ``geometry`` as a GeoJSON point, ``source_geometry_type``, ``geometry_role``).
        routing: The routing geometry in WGS84.
        english_names: Optional ``name:en`` tag by facility ID.

    Returns:
        One record per hospital inside, sorted by facility ID. The test is the one
        ``build_context_inputs`` uses for ``within_routing_context`` (``covers``).
    """

    english_names = english_names or {}
    kept = []
    for row in facilities:
        if row.get("service_type") != "hospital":
            continue
        point = shape(row["geometry"])
        if not routing.covers(point):
            continue
        record = {
            "facility_id": row["facility_id"],
            "name": row["name"],
            "longitude": round(point.x, 7),
            "latitude": round(point.y, 7),
            "source_geometry_type": row.get("source_geometry_type"),
            "geometry_role": row.get("geometry_role"),
        }
        if row["facility_id"] in english_names:
            record["name_en"] = english_names[row["facility_id"]]
        kept.append(record)
    identifiers = [row["facility_id"] for row in kept]
    if len(identifiers) != len(set(identifiers)):
        raise PlanningFrameError("an OSM hospital appears twice")
    return sorted(kept, key=lambda row: row["facility_id"])


def hospital_counts(hospitals: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count OSM objects, distinct named hospitals and unnamed objects (owner choice 22 counts named hospitals)."""

    names = Counter(row["name"] for row in hospitals if row["name"] and row["name"] != "Unnamed OSM candidate")
    unnamed = sum(1 for row in hospitals if not row["name"] or row["name"] == "Unnamed OSM candidate")
    return {
        "osm_objects": len(hospitals),
        "distinct_named_hospitals": len(names),
        "unnamed_objects": unnamed,
        "objects_that_repeat_a_named_hospital": sum(count - 1 for count in names.values()),
    }


def district_office_candidates(
    features: Sequence[Mapping[str, Any]],
    district_name_th: str,
    district_geometry: BaseGeometry,
) -> dict[str, list[dict[str, Any]]]:
    """Find the OSM objects that are the district office of one district.

    An object counts when it lies inside the district polygon and its ``name`` or
    ``name:th`` is exactly "thi wa kan amphoe" or "samnak ngan amphoe" (both mean
    "district office") followed by the district's Thai name. It is a **tagged
    office** when it also carries ``amenity=townhall`` or an ``office=*`` tag.
    Otherwise it is listed apart as **named only**: such an object corroborates a
    location and never decides it.

    Args:
        features: GeoJSON features from the GDAL OSM driver (points or multipolygons).
        district_name_th: The district's Thai name in COD-AB (``adm2_name1``).
        district_geometry: The district polygon in WGS84.

    Returns:
        ``{"tagged_office": [...], "named_only": [...]}``, each sorted by OSM identifier.
        A record carries the identifier, the point used (node, or representative point
        of an area), the name and the tags that matter.
    """

    if not district_name_th:
        raise PlanningFrameError("the district's Thai name is empty")
    office_name = DISTRICT_OFFICE_PREFIX_TH + district_name_th
    alternative = DISTRICT_OFFICE_ALT_PREFIX_TH + district_name_th
    tagged: dict[str, dict[str, Any]] = {}
    named: dict[str, dict[str, Any]] = {}
    for feature in features:
        geometry_json = feature.get("geometry") or {}
        geometry_type = geometry_json.get("type")
        if geometry_type not in {"Point", "Polygon", "MultiPolygon"}:
            continue
        tags = _tags(feature.get("properties", {}))
        names = {tags.get("name"), tags.get("name:th")} - {None}
        if not names & {office_name, alternative}:
            continue
        point = _point_of(shape(geometry_json))
        if not district_geometry.covers(point):
            continue
        identifier = osm_identifier(tags, geometry_type)
        record = {
            "osm_identifier": identifier,
            "osm_type": identifier.split("-")[1],
            "osm_id": int(identifier.split("-")[2]),
            "name": tags.get("name"),
            "name_en": tags.get("name:en"),
            "tags": {key: tags[key] for key in ("amenity", "office", "government", "landuse", "building") if key in tags},
            "point_lon_lat": [round(point.x, 7), round(point.y, 7)],
            "point_source": "node" if geometry_type == "Point" else "representative point of the area",
        }
        if tags.get("amenity") == "townhall" or "office" in tags:
            tagged[identifier] = record
        else:
            named[identifier] = record
    return {
        "tagged_office": [tagged[key] for key in sorted(tagged)],
        "named_only": [named[key] for key in sorted(named)],
    }


def containing_unit(point: BaseGeometry, units: Sequence[Mapping[str, Any]]) -> str:
    """Return the code of the one unit whose polygon covers a point.

    Raises:
        PlanningFrameError: when no unit covers the point, or more than one does (a point on a shared boundary).
    """

    codes = sorted(row["adm3_pcode"] for row in units if row["geometry"].covers(point))
    if len(codes) != 1:
        raise PlanningFrameError(f"the point is covered by {len(codes)} units, not exactly one: {codes}")
    return codes[0]


def seat_unit(candidates: Sequence[Mapping[str, Any]], units: Sequence[Mapping[str, Any]]) -> str | None:
    """Return the unit that holds every tagged district office, or None when there is none.

    Raises:
        PlanningFrameError: when two tagged offices lie in different units.
    """

    if not candidates:
        return None
    codes = {containing_unit(shape({"type": "Point", "coordinates": row["point_lon_lat"]}), units) for row in candidates}
    if len(codes) != 1:
        raise PlanningFrameError(f"the tagged district offices lie in different units: {sorted(codes)}")
    return codes.pop()


def seat_and_touching_units(
    seat_code: str,
    district_code: str,
    units: Sequence[Mapping[str, Any]],
    to_metres: Callable[[BaseGeometry], BaseGeometry],
) -> dict[str, Any]:
    """Apply SE2-blind rule B: the seat unit and every unit of its district that touches it.

    Args:
        seat_code: The unit that holds the district office.
        district_code: The blind district. Units of other districts that touch the
            seat are reported and left out: the owner question was which tambons of
            the blind district make the case.
        units: Every unit that could touch the seat (in WGS84), from any district.
        to_metres: Projects a WGS84 geometry to a metric CRS, for the shared lengths.

    Returns:
        The sorted unit list and one record per touching unit with its contact type
        (``shared_boundary``, ``point_contact`` or ``overlap``) and shared boundary length.
    """

    by_code = {row["adm3_pcode"]: row for row in units}
    if seat_code not in by_code:
        raise PlanningFrameError(f"the seat unit {seat_code} is not among the units")
    if by_code[seat_code]["adm2_pcode"] != district_code:
        raise PlanningFrameError(f"the seat unit {seat_code} is not in district {district_code}")
    seat = by_code[seat_code]["geometry"]
    seat_metric = to_metres(seat)
    touching, outside = [], []
    for code in sorted(by_code):
        if code == seat_code:
            continue
        geometry = by_code[code]["geometry"]
        if not geometry.intersects(seat):
            continue
        metric = to_metres(geometry)
        overlap_m2 = metric.intersection(seat_metric).area
        shared_m = metric.boundary.intersection(seat_metric.boundary).length
        contact = "overlap" if overlap_m2 > 1.0 else "shared_boundary" if shared_m > 0 else "point_contact"
        record = {
            "adm3_pcode": code,
            "adm3_name": by_code[code]["adm3_name"],
            "adm2_pcode": by_code[code]["adm2_pcode"],
            "contact": contact,
            "shared_boundary_m": round(shared_m, 1),
        }
        (touching if by_code[code]["adm2_pcode"] == district_code else outside).append(record)
    return {
        "seat": seat_code,
        "unit_list": sorted([seat_code, *(row["adm3_pcode"] for row in touching)]),
        "touching_units": touching,
        "touching_units_outside_the_district": outside,
    }


def geometry_sha256(geometry: Mapping[str, Any]) -> str:
    """SHA-256 of a GeoJSON geometry with sorted keys and no spaces (as the spike hashes corridors)."""

    text = json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def geojson_geometry(geometry: BaseGeometry) -> dict[str, Any]:
    """Return a shapely geometry as plain GeoJSON (lists, not tuples), as it reads back from a file."""

    return json.loads(json.dumps(mapping(geometry)))


def encode_feature_collection(header: Mapping[str, Any], features: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialise a FeatureCollection with one feature per line: ASCII, LF, one final newline.

    The same header and features always give the same bytes, so the file's
    SHA-256 can be recorded and checked by rebuilding it.
    """

    if "features" in header or header.get("type") != "FeatureCollection":
        raise PlanningFrameError("the header must be a FeatureCollection without features")
    head = json.dumps(dict(header), ensure_ascii=True, separators=(",", ":"))
    lines = [json.dumps(feature, ensure_ascii=True, separators=(",", ":")) for feature in features]
    text = head[:-1] + ',"features":[\n' + ",\n".join(lines) + "\n]}\n"
    return text.encode("ascii")
