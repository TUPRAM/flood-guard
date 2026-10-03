"""Plan task E4: the planning context of a case (protocol v1b, open items OI-04 and OI-06).

Plan 3.1 P2 builds the planning context with one call to
``floodguard.evidence_context.build_context_inputs``, unchanged, and adds the
grade joins of ``floodguard.grade_join`` (decision D13). This module holds the
parts of plan task E4 that are not that call:

* the DDPM located shelters the build supplies as facilities: read through the
  column whitelist of ``floodguard.ddpm_shelters`` (plan 2.2 G32), carrying the
  located-shelter flag of the shared-coordinate rule and the corroboration of
  owner choice 19 (an OSM building or amenity within 150 m; G33);
* the DGA match of the OSM hospitals the builder extracts (a DGA health-facility
  record within 150 m; facility set "corroborated");
* the main-road entries of owner choice 8: every node of a trunk or primary edge
  of the routing context, links included;
* the grade joins at a 0 m tolerance (owner choice 20) and their log;
* the facility table, the receipt and the comparison with the values the E0
  spike run of record measured (protocol v1b
  ``corridor_polygon.run_of_record.e4_reproduction_check``).

No shelter row leaves this module with a column outside the whitelist: no name
of a person, no phone number and no personal identifier. The facility table
holds DDPM rows and is pitch level; it is written outside Git. The receipt
holds counts, OSM hospital names and hashes only.

Nothing here reads a flood layer or computes a closure, an access loss, an FPPS,
an A-E class or an ensemble. The only access computation is the baseline
connected-no-route share to hospitals for the whole frame, which is the
acceptance value of plan row E4; no figure is written for a single tambon.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from floodguard.ddpm_shelters import CAPACITY_STATUS, LABEL, LOCATED, summarise
from floodguard.grade_join import COINCIDENCE_TOLERANCE_M, apply_grade_joins, join_log, joins_sha256
from floodguard.hospital_counts import count_hospitals
from floodguard.shelter_corroboration import corroborate_shelters

RECEIPT_SCHEMA = "floodguard.planning_context_e4.v1"
FACILITY_TABLE_SCHEMA = "floodguard.planning_facilities_e4.v1"
HOSPITAL = "hospital"
MAIN_ROAD_ENTRY = "main_road_entry"
DDPM_LOCATED_SHELTER = "ddpm_located_shelter"
# Owner choice 8: trunk and primary, links included. The context builder maps trunk_link and primary_link to these.
MAIN_ROAD_CLASSES = ("primary", "trunk")
# Plan 5 item 11 axis 3 (hospitals) and owner choice 19 (shelters).
MATCH_DISTANCE_M = 150.0
METRIC_EPSG = 32647
# Room around the routing context for OSM objects that a shelter near its edge can match (about 210 m at 20 N).
MATCH_OBJECT_MARGIN_DEG = 0.002
# The two GDAL OSM passes of the E0 spike (scripts/run_planning_context_spike.py, extract_match_objects).
OSM_MATCH_LAYERS = (
    ("multipolygons", "building IS NOT NULL OR amenity IS NOT NULL"),
    ("points", "other_tags LIKE '%building%' OR other_tags LIKE '%amenity%'"),
)
DDPM_ID_PREFIX = "DDPM-gd002-row-"
MAIN_ROAD_ID_PREFIX = "main-road-entry-"
DDPM_SOURCE_NAME = "DDPM listed shelters, dpm-gd002_final2.csv"
CORROBORATION_VALUES = ("building", "amenity_only", "none")

# The columns a supplied shelter row may carry, before the context builder snaps it.
SHELTER_SOURCE_KEYS = (
    "facility_id",
    "source_row_number",
    "service_type",
    "facility_type",
    "name",
    "province_th",
    "district_th",
    "tambon_th",
    "capacity",
    "capacity_status",
    "location_status",
    "label",
    "longitude",
    "latitude",
    "geometry_role",
    "location_review_status",
    "corroboration",
    "corroboration_distance_m",
    "candidate_destination_eligible",
    "identity_reconciled",
    "publication_level",
    "source_name",
)
# The keys build_context_inputs adds when it snaps a supplied facility.
BUILDER_SNAP_KEYS = ("node_id", "snap_distance_m", "within_routing_context", "connector_walkability")
SHELTER_FACILITY_KEYS = frozenset((*SHELTER_SOURCE_KEYS, *BUILDER_SNAP_KEYS))
# A second guard behind the whitelist: a column whose name reads like a personal field is refused even if someone
# adds it to the whitelist. English and Thai: phone, mobile, coordinator, person, contact, citizen or national ID,
# ID card, passport, e-mail, surname; Thai "name", "surname", "telephone", "coordinator", "card".
PERSONAL_FIELD = re.compile(
    r"phone|\btel\b|telephone|mobile|coordinator|person|contact|citizen|national_id|id_card|idcard|passport|e-?mail"
    r"|surname|first_name|last_name|full_name"
    r"|\u0e0a\u0e37\u0e48\u0e2d|\u0e2a\u0e01\u0e38\u0e25|\u0e42\u0e17\u0e23|\u0e1c\u0e39\u0e49\u0e1b\u0e23\u0e30\u0e2a\u0e32\u0e19"
    r"|\u0e1a\u0e31\u0e15\u0e23",
    re.IGNORECASE,
)
FACILITY_CONFIDENCE_BASIS = (
    "OSM hospitals, roads, buildings and amenities and DDPM listed shelters are unverified map and list records; "
    "the DGA match and the shelter corroboration show that a second record lies near the first, not that the site "
    "exists or was open. No facility was checked on the ground."
)
RECEIPT_CONFIDENCE_BASIS = (
    "OSM roads and hospitals, DDPM listed shelters and DGA health-facility records are unverified map and list "
    "records; travel times are modelled class speeds on an undirected graph; the grade joins are coordinate "
    "coincidences whose passability is unknown."
)
FACILITY_ASSUMPTIONS = (
    "A hospital is an OSM object tagged amenity=hospital or healthcare=hospital whose routing point lies in the "
    "routing context, as build_context_inputs extracts it. Every such object is a destination, named or not.",
    "A DGA match is a DGA health-facility record within 150 m of the hospital's OSM footprint or point, measured in "
    "EPSG:32647. It corroborates the location; it does not show the hospital is open.",
    "A DDPM row is located unless at least 3 rows of the national file share its exact coordinate "
    "(facility_sets.shelter_location_rule); only located rows inside the routing context are supplied.",
    "A located shelter is corroborated when an OSM building or amenity lies within 150 m of its listed coordinate "
    "(owner choice 19). That shows a mapped structure near the coordinate, not that it is the shelter or was open.",
    "Listed capacity is a planning figure (capacity_status listed_planned_unverified), not an available capacity.",
    "A main-road entry is a node of a trunk or primary edge, links included, of the routing context (owner choice "
    "8). Grade-join connectors are not main roads.",
)


class PlanningContextError(ValueError):
    """Raised when an input or an output of the E4 build breaks one of its rules."""


def encode_json(payload: Mapping[str, Any], *, indent: int | None = 2) -> bytes:
    """Serialise a JSON output: ASCII with escapes, LF, one final newline. Same payload, same bytes."""

    separators = None if indent is not None else (",", ":")
    text = json.dumps(payload, indent=indent, ensure_ascii=True, allow_nan=False, separators=separators)
    return (text + "\n").encode("ascii")


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of some bytes as lowercase hex."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_no_personal_fields(rows: Sequence[Mapping[str, Any]], allowed: frozenset[str] = SHELTER_FACILITY_KEYS) -> None:
    """Refuse shelter rows that carry a column outside the whitelist or a column that reads like a personal field.

    Args:
        rows: Shelter rows, before or after the context builder snaps them.
        allowed: The whitelist of column names.

    Raises:
        PlanningContextError: naming the offending column names (never their values).
    """

    for row in rows:
        outside = sorted(str(key) for key in row if key not in allowed)
        personal = sorted(str(key) for key in row if PERSONAL_FIELD.search(str(key)))
        if outside or personal:
            raise PlanningContextError(
                "a shelter row carries columns outside the PII whitelist: " + ", ".join(sorted({*outside, *personal}))
            )


def _corroboration(row: Mapping[str, Any], osm_objects: Sequence[tuple[frozenset[str], Any]], distance_m: float) -> str:
    """Return how one located row is corroborated, by the rule of ``corroborate_shelters`` applied to it alone."""

    single = corroborate_shelters([row], osm_objects, distance_m=distance_m)
    if single["matched_to_a_building_rows"]:
        return "building"
    if single["matched_to_an_amenity_only_rows"]:
        return "amenity_only"
    return "none"


def shelter_facilities(
    rows: Sequence[Mapping[str, Any]],
    routing_context: Any,
    osm_objects: Sequence[tuple[frozenset[str], Any]],
    *,
    distance_m: float = MATCH_DISTANCE_M,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the located DDPM shelters to supply to the context builder, and their counts.

    Args:
        rows: Rows of ``ddpm_shelters.read_ddpm_shelters`` for the whole national file, so that the
            shared-coordinate rule was applied over the whole file.
        routing_context: The routing polygon intersected with the reporting geometry (shapely, WGS84).
            A row is in the context when its coordinate is covered by it.
        osm_objects: ``(kinds, geometry)`` pairs of OSM buildings and amenities (see
            ``extract_osm_match_objects``).
        distance_m: The shelter match distance (owner choice 19: 150 m).

    Returns:
        The facility rows, sorted by ``facility_id``, each with only the whitelisted columns, and a
        summary: the rows with a coordinate in the routing context (``ddpm_shelters.summarise``) and
        the corroboration counts of ``corroborate_shelters``.

    Raises:
        PlanningContextError: when two rows share a source row number, when the per-row flags and the
            counts disagree, or when a column outside the whitelist would leave.
    """

    from shapely.geometry import Point

    inside = [
        row for row in rows
        if row.get("latitude") is not None and row.get("longitude") is not None
        and routing_context.covers(Point(row["longitude"], row["latitude"]))
    ]
    located = [row for row in inside if row["location_status"] == LOCATED]
    totals = corroborate_shelters(located, osm_objects, distance_m=distance_m)
    facilities = []
    for row in located:
        number = str(row["source_row_number"]).strip()
        if not number:
            raise PlanningContextError("a located shelter row has no source row number")
        facilities.append({
            "facility_id": DDPM_ID_PREFIX + number,
            "source_row_number": number,
            "service_type": DDPM_LOCATED_SHELTER,
            "facility_type": "listed_shelter",
            "name": row["place_name_th"],
            "province_th": row["province_th"],
            "district_th": row["district_th"],
            "tambon_th": row["tambon_th"],
            "capacity": row["listed_places"],
            "capacity_status": CAPACITY_STATUS,
            "location_status": row["location_status"],
            "label": LABEL,
            "longitude": float(row["longitude"]),
            "latitude": float(row["latitude"]),
            "geometry_role": "listed_coordinate_not_verified_entrance",
            "location_review_status": "ddpm_listed_coordinate_not_independently_verified",
            "corroboration": _corroboration(row, osm_objects, distance_m),
            "corroboration_distance_m": float(distance_m),
            "candidate_destination_eligible": True,
            "identity_reconciled": False,
            "publication_level": "pitch",
            "source_name": DDPM_SOURCE_NAME,
        })
    facilities.sort(key=lambda row: row["facility_id"])
    if len({row["facility_id"] for row in facilities}) != len(facilities):
        raise PlanningContextError("two located shelter rows share a source row number")
    flags = Counter(row["corroboration"] for row in facilities)
    if (flags["building"], flags["amenity_only"]) != (
        totals["matched_to_a_building_rows"], totals["matched_to_an_amenity_only_rows"]
    ):
        raise PlanningContextError("the per-row corroboration flags disagree with the corroboration counts")
    assert_no_personal_fields(facilities, frozenset(SHELTER_SOURCE_KEYS))
    return facilities, {
        "ddpm_rows_with_a_coordinate_in_the_routing_context": summarise(inside),
        "shelter_corroboration": totals,
    }


def extract_osm_match_objects(
    pbf: Path, bounds: Sequence[float], target: Path
) -> tuple[list[tuple[frozenset[str], Any]], dict[str, Any]]:
    """Extract OSM buildings and amenities inside ``bounds`` for shelter corroboration, as the E0 spike did.

    Two passes of the GDAL OSM driver (``OSM_MATCH_LAYERS``): closed ways and
    multipolygon relations tagged building or amenity, and nodes whose other tags
    mention either key. Each object keeps its match kinds
    (``shelter_corroboration.osm_match_kinds``); an object with neither kind is
    dropped. The extracted files are written in ``target`` (outside Git) and named
    in the returned record by their SHA-256.

    Args:
        pbf: The OSM extract of Thailand.
        bounds: ``(west, south, east, north)`` in WGS84.
        target: A scratch folder.
    """

    import pyogrio

    from floodguard.evidence_context import _tags, ogr_runtime_identity
    from floodguard.open_context_extract import _run_ogr2ogr, find_qgis_bin
    from floodguard.shelter_corroboration import osm_match_kinds

    target.mkdir(parents=True, exist_ok=True)
    bin_dir = find_qgis_bin()
    objects: list[tuple[frozenset[str], Any]] = []
    info: dict[str, Any] = {
        "bounds_wgs84": [round(value, 6) for value in bounds],
        "margin_deg": MATCH_OBJECT_MARGIN_DEG,
        "ogr_runtime": ogr_runtime_identity(bin_dir),
        "layers": {},
        "retained": False,
        "retained_note": "The extracted files were written outside Git and not kept; their SHA-256 values name them.",
    }
    for layer, where in OSM_MATCH_LAYERS:
        path = target / f"osm_{layer}_building_or_amenity.geojson"
        _run_ogr2ogr(bin_dir, ["-f", "GeoJSON", "-spat", *[str(value) for value in bounds], "-where", where,
                               "-lco", "RFC7946=YES", str(path), str(pbf), layer])
        frame = pyogrio.read_dataframe(path)
        columns = [column for column in frame.columns if column != "geometry"]
        kept: Counter[str] = Counter()
        for values, geometry in zip(frame[columns].itertuples(index=False, name=None), frame.geometry):
            if geometry is None or geometry.is_empty:
                continue
            # OSM attributes are strings; a missing one comes back as NaN or None and is left out.
            properties = {key: value for key, value in zip(columns, values) if isinstance(value, str)}
            kinds = osm_match_kinds(_tags(properties))
            if kinds:
                objects.append((kinds, geometry))
                kept["kept"] += 1
                for kind in kinds:
                    kept[kind] += 1
        info["layers"][layer] = {
            "where": where,
            "features_read": int(len(frame)),
            "objects_kept": kept["kept"],
            "with_building": kept["building"],
            "with_amenity": kept["amenity"],
            "file_sha256": sha256_file(path),
        }
        del frame
    return objects, info


def match_object_bounds(routing_context: Any) -> tuple[float, float, float, float]:
    """Return the bounds of the routing context widened by ``MATCH_OBJECT_MARGIN_DEG`` on each side."""

    west, south, east, north = routing_context.bounds
    margin = MATCH_OBJECT_MARGIN_DEG
    return (west - margin, south - margin, east + margin, north + margin)


def hospital_destinations(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the OSM hospitals of a context that are destinations: eligible and inside the routing context."""

    return [
        dict(row) for row in context["osm_facilities"]
        if row.get("service_type") == HOSPITAL and row.get("candidate_destination_eligible") is True
        and row.get("within_routing_context") is True
    ]


def dga_matches(
    hospitals: Sequence[Mapping[str, Any]],
    dga_points: Sequence[Sequence[float]],
    *,
    distance_m: float = MATCH_DISTANCE_M,
) -> dict[str, int]:
    """Count, for each hospital, the DGA records within ``distance_m`` of its OSM footprint or point.

    The rule of the E0 spike (``facility_counts``): the OSM source geometry and the
    DGA points are projected to EPSG:32647, and a DGA point matches when it lies
    within the distance of the geometry.

    Args:
        hospitals: Rows of ``hospital_destinations``, each with ``facility_id`` and ``source_geometry``.
        dga_points: ``(longitude, latitude)`` of every DGA record read.
        distance_m: The match distance (150 m).

    Returns:
        ``facility_id`` -> number of DGA records within the distance (0 when none).
    """

    from pyproj import Transformer
    from shapely import STRtree, points
    from shapely.geometry import shape
    from shapely.ops import transform

    if not math.isfinite(distance_m) or distance_m < 0:
        raise PlanningContextError("the DGA match distance must be a finite number of metres, 0 or more")
    to_metres = Transformer.from_crs(4326, METRIC_EPSG, always_xy=True).transform
    if not dga_points:
        return {str(row["facility_id"]): 0 for row in hospitals}
    lon = [point[0] for point in dga_points]
    lat = [point[1] for point in dga_points]
    x, y = to_metres(lon, lat)
    tree = STRtree(points(x, y))
    result = {}
    for row in hospitals:
        site = transform(to_metres, shape(row["source_geometry"]))
        result[str(row["facility_id"])] = int(len(tree.query(site, predicate="dwithin", distance=distance_m)))
    return result


def main_road_entries(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the main-road entries of owner choice 8: every node of a trunk or primary edge of the context.

    Links count, because the builder gives trunk_link and primary_link the class
    of their road. The edges are the context's own road edges; a grade-join
    connector is never a main road. Each entry is a destination at its own graph
    node, so its snap distance is 0 m.
    """

    coordinates = context["node_coordinates"]
    ways: dict[str, set[str]] = {}
    for edge in context["edges"]:
        if edge.get("road_class") in MAIN_ROAD_CLASSES and edge.get("edge_kind") is None:
            for node in (edge["from_node"], edge["to_node"]):
                ways.setdefault(str(node), set()).add(str(edge.get("osm_way_id")))
    return [
        {
            "facility_id": MAIN_ROAD_ID_PREFIX + node,
            "service_type": MAIN_ROAD_ENTRY,
            "node_id": node,
            "snap_distance_m": 0.0,
            "longitude": float(coordinates[node][0]),
            "latitude": float(coordinates[node][1]),
            "osm_way_ids": sorted(ways[node]),
        }
        for node in sorted(ways)
    ]


def no_route_share(access: Mapping[str, Any]) -> dict[str, float]:
    """Return the baseline connected-no-route share and its population terms (the E0 spike's definition)."""

    review = access["coverage_review"]
    total = access["totals"]["total_population"]
    connected = total - review["missing_graph_coverage_population"]
    no_route = review["baseline"]["graph_connected_no_modelled_route_population"]
    return {
        "residents": total,
        "graph_connected_residents": connected,
        "connected_residents_without_a_route": no_route,
        "share": no_route / connected if connected else 1.0,
        "residents_not_connected_to_the_graph": review["missing_graph_coverage_population"],
    }


def edge_tag_counts(edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count context edges by road class and by bridge and tunnel tag, for the whole context."""

    total = len(edges)
    by_class = Counter(str(edge["road_class"]) for edge in edges)
    bridge = Counter(str(edge.get("bridge", "no")) for edge in edges)
    tunnel = Counter(str(edge.get("tunnel", "no")) for edge in edges)
    return {
        "edges": total,
        "by_road_class": dict(sorted(by_class.items())),
        "by_bridge_tag": dict(sorted(bridge.items())),
        "by_tunnel_tag": dict(sorted(tunnel.items())),
        "bridge_yes_edges": bridge.get("yes", 0),
        "tunnel_culvert_edges": tunnel.get("culvert", 0),
    }


def reproduction_check(
    observed: Mapping[str, Any], expected: Mapping[str, Any], *, facilities_supplied: int
) -> dict[str, Any]:
    """Compare an E4 build with the values the E0 spike run of record measured.

    Args:
        observed: The E4 values: ``corridor_geometry_sha256``, ``edge_count``,
            ``grade_split_count``, ``joins_sha256``, ``join_count``, ``facility_counts``
            (the four counts of OI-06), ``hospital_facility_ids``,
            ``context_canonical_sha256`` and ``inputs`` (input file hashes).
        expected: Protocol v1b ``e4_reproduction_check`` with ``inputs`` added from the spike's receipt.
        facilities_supplied: How many facilities the E4 build supplied to the builder.

    Returns:
        One row per value with ``expected``, ``observed`` and ``same``; the keys that differ; and the
        context hash, which covers supplied facilities and so differs by construction when the E4
        build supplies any (the spike supplied none).
    """

    values: dict[str, dict[str, Any]] = {}
    for key in ("corridor_geometry_sha256", "edge_count", "grade_split_count", "joins_sha256", "join_count"):
        values[key] = {"expected": expected[key], "observed": observed[key]}
    for key, value in expected["facility_counts"].items():
        values[f"facility_counts.{key}"] = {"expected": value, "observed": observed["facility_counts"].get(key)}
    hospital = expected["mae_sai_hospital_facility_id"]
    values["mae_sai_hospital_facility_id"] = {
        "expected": hospital,
        "observed": hospital if hospital in set(observed["hospital_facility_ids"]) else None,
    }
    for key, value in sorted(expected.get("inputs", {}).items()):
        values[f"inputs.{key}"] = {"expected": value, "observed": observed["inputs"].get(key)}
    for row in values.values():
        row["same"] = row["expected"] == row["observed"]
    context_same = observed["context_canonical_sha256"] == expected["context_canonical_sha256"]
    differences = [key for key, row in values.items() if not row["same"]]
    if facilities_supplied == 0 and not context_same:
        differences.append("context_canonical_sha256")
    accepted = {str(entry.get("key")) for entry in expected.get("accepted_differences", [])}
    return {
        "rule": "Protocol v1b corridor_polygon.run_of_record.e4_reproduction_check: a value that differs is reported "
                "here, and the open item does not close on it until the owners accept the difference in the "
                "decision log (accepted_differences).",
        "source": expected.get("source"),
        "source_sha256": expected.get("source_sha256"),
        "values": values,
        "context_canonical_sha256": {
            "expected": expected["context_canonical_sha256"],
            "observed": observed["context_canonical_sha256"],
            "same": context_same,
            "facilities_supplied": facilities_supplied,
            "expected_to_differ": facilities_supplied > 0,
            "reason": "The spike supplied no facility to build_context_inputs; this build supplies the DDPM located "
                      "shelters (plan 3.1 P2), and the canonical SHA-256 of the context covers the supplied "
                      "facilities, so the two hashes differ by construction. The road graph, the joins and the "
                      "counts above must still match."
                      if facilities_supplied else
                      "No facility was supplied, so the context must be the spike's context.",
        },
        "differences": differences,
        "differences_accepted_by_the_owners": sorted(set(differences) & accepted),
        "all_same": not differences,
    }


def _rounded(values: Mapping[str, float], digits: int = 6) -> dict[str, float]:
    return {key: round(value, digits) for key, value in values.items()}


def _round_or_none(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def assemble_outputs(
    context: Mapping[str, Any],
    *,
    case: Mapping[str, Any],
    record: bool,
    generated_at_utc: str,
    shelter_summary: Mapping[str, Any],
    dga_points: Sequence[Sequence[float]],
    inputs: Mapping[str, Any],
    paths: Mapping[str, str],
    acceptance: Mapping[str, Any],
    load_aois_counts: Mapping[str, Any],
    expected: Mapping[str, Any] | None = None,
    status_notes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the join log, the facility table and the receipt of one E4 build from its context.

    Everything here is a function of the context and the arguments, so the same
    build gives the same bytes; the generation time is an argument, and the run's
    own record (timings, memory, compute window) is added by the caller beside
    the receipt body under the key ``run``.

    Args:
        context: The output of ``build_context_inputs`` for the case, with the DDPM located
            shelters supplied as facilities.
        case: ``case_id``, ``title``, ``travel_mode``, ``rules`` (texts for aoi, routing and
            reporting geometry), ``routing_source`` (path and hashes), ``named_ways`` (OSM way IDs
            that must be in the routing context), ``expected_hospital_ids`` (or None),
            ``reporting_units_intersecting``, ``main_road_entry_definition`` and
            ``reviewed_junctions_supplied``.
        record: True for the build of record, False for a candidate build.
        generated_at_utc: The generation time written into the join log, table and receipt.
        shelter_summary: The summary of ``shelter_facilities`` (with ``osm_extract`` added).
        dga_points: ``(longitude, latitude)`` of every DGA record.
        inputs: Hashes of the input files (``*_sha256``) that the receipt records.
        paths: Logical paths of the ``join_log``, ``facility_table``, ``context`` and ``receipt``.
        acceptance: Protocol v1b ``corridor_polygon.acceptance``.
        load_aois_counts: What ``load_aois`` returned for each AOI folder during the build.
        expected: The reproduction values (SE1 vehicle only) or None.
        status_notes: ``status_note`` texts for ``record`` and ``candidate`` (defaults are generic).

    Returns:
        ``join_log`` and ``facility_table`` (bytes), ``receipt_body`` (a dict without ``run``) and
        ``context_canonical_sha256``.

    Raises:
        PlanningContextError: when a supplied facility is not a whitelisted located shelter, or a
            supplied shelter falls outside the builder's routing context.
    """

    if not str(generated_at_utc).strip():
        raise PlanningContextError("a build needs a generation time")
    notes = {
        "record": "Build of record of plan task E4 for this case.",
        "candidate": "Candidate: an E4 build without a declared compute window. It is not the build of record and "
                     "closes no open item.",
        **(status_notes or {}),
    }
    status = "of_record" if record else "candidate"
    status_note = notes["record" if record else "candidate"]
    osm_retrieved_at = context["source_metadata"]["osm"]["retrieved_at_utc"]
    travel_mode = str(context["travel_mode"])

    supplied = [dict(row) for row in context["facilities"]]
    if any(row.get("service_type") != DDPM_LOCATED_SHELTER for row in supplied):
        raise PlanningContextError("only DDPM located shelters are supplied to the context builder")
    assert_no_personal_fields(supplied)
    if any(row.get("within_routing_context") is not True for row in supplied):
        raise PlanningContextError("a supplied shelter lies outside the builder's routing context")
    located = shelter_summary["ddpm_rows_with_a_coordinate_in_the_routing_context"]["located_rows"]
    if len(supplied) != located:
        raise PlanningContextError("the builder holds a different number of shelters than were supplied")

    hospitals = hospital_destinations(context)
    matches = dga_matches(hospitals, dga_points)
    entries = main_road_entries(context)
    joined_edges, joins = apply_grade_joins(context)
    from floodguard.evidence_scenarios import calculate_total_access

    unjoined_access = calculate_total_access(context["population"], context["edges"], hospitals)
    joined_access = calculate_total_access(context["population"], joined_edges, hospitals)
    share_joined, share_unjoined = no_route_share(joined_access), no_route_share(unjoined_access)

    breakdown = count_hospitals(hospitals)
    corroboration = shelter_summary["shelter_corroboration"]
    counts = {
        "osm_hospitals": len(hospitals),
        "dga_matched_hospitals": sum(matches[str(row["facility_id"])] > 0 for row in hospitals),
        "located_ddpm_shelters": located,
        "corroborated_shelters": corroboration["corroborated_rows"],
    }
    review = context["connectivity_review"]
    source_timestamps = {
        "osm_retrieved_at_utc": osm_retrieved_at,
        "population_year_represented": 2020,
        "boundaries_valid_on": "2022-01-22",
        "ddpm_list_file_dated": "2026-09-21 (open-data folder date)",
    }
    publication_note = ("Pitch level: the table holds DDPM listed-shelter rows (D8b). It stays outside Git; the receipt "
                        "names it by its SHA-256 and carries counts only.")

    hospital_rows = [
        {
            "facility_id": row["facility_id"],
            "name": row.get("name"),
            "source_url": row.get("source_url"),
            "source_geometry_type": row.get("source_geometry_type"),
            "geometry_role": row.get("geometry_role"),
            "longitude": row.get("longitude"),
            "latitude": row.get("latitude"),
            "node_id": row.get("node_id"),
            "snap_distance_m": row.get("snap_distance_m"),
            "dga_records_within_150_m": matches[str(row["facility_id"])],
            "dga_matched": matches[str(row["facility_id"])] > 0,
        }
        for row in hospitals
    ]
    table = {
        "schema_version": FACILITY_TABLE_SCHEMA,
        "case": case["case_id"],
        "travel_mode": travel_mode,
        "status": status,
        "status_note": status_note,
        "generated_at_utc": generated_at_utc,
        "source_timestamp": osm_retrieved_at,
        "source_timestamps": source_timestamps,
        "confidence_class": "low",
        "confidence_basis": FACILITY_CONFIDENCE_BASIS,
        "assumptions": list(FACILITY_ASSUMPTIONS),
        "official_warning": False,
        "operational_status": "non_operational",
        "publication_level": "pitch",
        "publication_note": publication_note,
        "context_canonical_sha256": context["canonical_sha256"],
        "counts": {**counts, "main_road_entries": len(entries)},
        "services": {
            HOSPITAL: {
                "rule": "Every OSM hospital that build_context_inputs extracts, that is eligible as a destination and "
                        "whose routing point lies in the routing context (facility_sets.services.hospital).",
                "dga_match_rule": "dga_matched is true when a DGA health-facility record lies within 150 m of the "
                                  "OSM footprint or point, measured in EPSG:32647 (facility set corroborated).",
                "rows": hospital_rows,
            },
            MAIN_ROAD_ENTRY: {
                "rule": case["main_road_entry_definition"],
                "rows": entries,
            },
            DDPM_LOCATED_SHELTER: {
                "rule": "DDPM rows located under the shared-coordinate rule whose coordinate lies in the routing "
                        "context, read through the column whitelist; supplied to build_context_inputs as facilities.",
                "corroboration_rule": corroboration["rule"],
                "corroboration_values": {
                    "building": "an OSM object tagged building lies within the match distance",
                    "amenity_only": "an OSM amenity, and no building, lies within the match distance",
                    "none": "no OSM building or amenity lies within the match distance",
                },
                "rows": supplied,
            },
        },
    }
    table_bytes = encode_json(table, indent=None)

    log_bytes = encode_json(join_log(
        joins, context_canonical_sha256=context["canonical_sha256"],
        status="log_of_record" if record else "candidate", status_note=status_note,
        source_timestamp=osm_retrieved_at, generated_at_utc=generated_at_utc,
    ))

    every_hospital = {row["facility_id"]: row for row in context["osm_facilities"] if row.get("service_type") == HOSPITAL}
    named_ways = {
        str(way): bool(every_hospital.get(f"OSM-way-{way}", {}).get("within_routing_context"))
        for way in case.get("named_ways", [])
    }
    hospital_count = breakdown["distinct_named_hospitals"]
    no_route_max = acceptance["baseline_vehicle_no_route_share_max"]
    aois_six = all(value == 6 for value in load_aois_counts.values()) and bool(load_aois_counts)
    vehicle = travel_mode == "legacy_vehicle"
    criteria = {
        "hospitals_in_context_min": hospital_count >= acceptance["hospitals_in_context_min"],
        "named_ways_within_routing_context": all(named_ways.values()),
        # The plan's no-route criterion is a vehicle criterion; a walking context reports its share without it.
        "baseline_vehicle_no_route_share_max": (share_joined["share"] <= no_route_max) if vehicle else None,
        "pii_whitelist": True,
        "load_aois_still_returns_6": aois_six,
    }
    observed = {
        "corridor_geometry_sha256": case["routing_source"].get("geometry_sha256"),
        "edge_count": len(context["edges"]),
        "grade_split_count": review["shared_coordinate_grade_split_count"],
        "joins_sha256": joins_sha256(joins),
        "join_count": len(joins),
        "facility_counts": counts,
        "hospital_facility_ids": [row["facility_id"] for row in hospitals],
        "context_canonical_sha256": context["canonical_sha256"],
        "inputs": dict(inputs),
    }
    frame_hospitals = None
    if case.get("expected_hospital_ids") is not None:
        wanted, got = sorted(case["expected_hospital_ids"]), sorted(observed["hospital_facility_ids"])
        frame_hospitals = {
            "rule": "The hospital objects of this context are compared with the hospital destinations protocol v1b "
                    "records for the frame (corridor_polygon.se2_frame.hospital_destinations).",
            "expected": wanted,
            "observed": got,
            "missing": sorted(set(wanted) - set(got)),
            "extra": sorted(set(got) - set(wanted)),
            "same": wanted == got,
        }
    coverage = context["coverage"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "generated_at_utc": generated_at_utc,
        "protocol_item": "Plan task E4 (plan 8.1, row E4) for protocol v1b open items OI-04 (join log) and OI-06 "
                         "(facility counts)",
        "case": case["case_id"],
        "case_title": case["title"],
        "travel_mode": travel_mode,
        "run_kind": "build_of_record" if record else "candidate",
        "status": status,
        "status_note": status_note,
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "One baseline context with its grade joins and facility table, and the baseline connected-no-route "
                    "share to hospitals for the whole frame. No flood layer, no closure, no access loss, no FPPS, no "
                    "A-E class, no ensemble, and no figure for a single tambon.",
        "source_timestamp": osm_retrieved_at,
        "source_timestamps": source_timestamps,
        "confidence_class": "low",
        "confidence_basis": RECEIPT_CONFIDENCE_BASIS,
        "context_call": {
            "function": "floodguard.evidence_context.build_context_inputs (unchanged)",
            "aoi_geometry": case["rules"]["aoi_geometry"],
            "routing_geometry": case["rules"]["routing_geometry"],
            "reporting_geometry": case["rules"]["reporting_geometry"],
            "reporting_units_intersecting": case["reporting_units_intersecting"],
            "travel_mode": travel_mode,
            "facilities_supplied": len(supplied),
            "facilities_supplied_service": DDPM_LOCATED_SHELTER,
            "facilities_supplied_note": "OSM hospitals are extracted by the builder itself; supplied and extracted "
                                        "facilities never merge (facility_sets.identity_rule). Main-road entries are "
                                        "graph nodes and are not supplied.",
            "reviewed_junctions_supplied": case["reviewed_junctions_supplied"],
            "reviewed_junctions_applied": len(coverage["reviewed_shared_node_junctions_applied"]),
        },
        "routing_source": dict(case["routing_source"]),
        "context": {
            "canonical_sha256": context["canonical_sha256"],
            "edges": len(context["edges"]),
            "road_nodes": coverage["road_nodes"],
            "connected_components": coverage["connected_components"],
            "segments_omitted_at_routing_boundary_or_degenerate":
                coverage["segments_omitted_at_routing_boundary_or_degenerate"],
            "population_cells": coverage["population_cells"],
            "modelled_population_2020": _round_or_none(coverage["modelled_population_2020"], 1),
            "population_snap_coverage_fraction": _round_or_none(coverage["population_snap_coverage_fraction"], 6),
            "input_hashes": dict(sorted(context["input_hashes"].items())),
            "retained": True,
            "path": paths["context"],
            "retained_note": "The context file is kept outside Git at this path (pitch level, because it holds the "
                             "supplied DDPM rows). Its canonical SHA-256 names it: the builder's hash of every "
                             "field except its generation time.",
        },
        "grade_joins": {
            "rule_version": joins[0]["rule_version"] if joins else None,
            "coincidence_tolerance_m": COINCIDENCE_TOLERANCE_M,
            "tolerance_decision": "Owner choice 20, option A (decision log R12): 0 m.",
            "join_count": len(joins),
            "grade_split_count": review["shared_coordinate_grade_split_count"],
            "possible_endpoint_transition_count": review["possible_endpoint_transition_count"],
            "joins_where_every_node_is_an_endpoint": sum(join["all_nodes_at_coordinate_are_endpoints"] for join in joins),
            "joins_sha256": joins_sha256(joins),
            "log_path": paths["join_log"],
            "log_sha256": sha256_bytes(log_bytes),
        },
        "edge_counts": edge_tag_counts(context["edges"]),
        "facilities": {
            "counts": counts,
            "hospital_count_breakdown": breakdown,
            "hospitals_in_routing_context": [
                {
                    "facility_id": row["facility_id"],
                    "name": row["name"],
                    "source_geometry_type": row["source_geometry_type"],
                    "snapped_to_graph": row["node_id"] is not None,
                    "dga_matched": row["dga_matched"],
                }
                for row in hospital_rows
            ],
            "hospitals_outside_routing_context": sum(
                row.get("within_routing_context") is not True for row in every_hospital.values()
            ),
            "dga_match_rule": "An OSM hospital is matched when a DGA record lies within 150 m of its OSM footprint or "
                              "point, measured in EPSG:32647.",
            "dga_records_read": len(dga_points),
            "main_road_entries": len(entries),
            "main_road_entry_definition": case["main_road_entry_definition"],
            "main_road_entry_node_ids_sha256": sha256_bytes(
                json.dumps([row["node_id"] for row in entries], separators=(",", ":")).encode("ascii")
            ),
            "ddpm_rows_with_a_coordinate_in_the_routing_context":
                dict(shelter_summary["ddpm_rows_with_a_coordinate_in_the_routing_context"]),
            "ddpm_location_rule": "A coordinate shared by at least 3 rows of the national file is a placeholder and "
                                  "those rows are not located (facility_sets.shelter_location_rule). Only located "
                                  "rows are supplied; each carries location_status.",
            "supplied_shelters_snapped_within_100_m": sum(row.get("node_id") is not None for row in supplied),
            "shelter_corroboration": {**corroboration, "osm_extract": shelter_summary.get("osm_extract")},
            "pii_whitelist": {
                "rule": "Shelter rows keep only whitelisted columns (floodguard.planning_context.SHELTER_FACILITY_KEYS): "
                        "no coordinator name, no phone number and no personal identifier. The build refuses any "
                        "other column, before and after the context builder.",
                "checked_at_build": True,
                "test": "tests/test_planning_context.py::test_pii_whitelist_keeps_no_personal_column_and_refuses_one",
            },
            "facility_table": {
                "path": paths["facility_table"],
                "sha256": sha256_bytes(table_bytes),
                "publication_level": "pitch",
                "retained_outside_git": True,
            },
        },
        "acceptance": {
            "plan_row": "E4: at least 4 hospitals; no-route share at most 10%; PII whitelist test; load_aois still 6.",
            "hospitals_in_context_min": acceptance["hospitals_in_context_min"],
            "hospital_count": hospital_count,
            "hospital_count_unit": "distinct named hospitals (owner choice 22)",
            "named_ways_within_routing_context": named_ways,
            "baseline_vehicle_no_route_share_max": no_route_max,
            "baseline_vehicle_no_route_share": round(share_joined["share"], 6) if vehicle else None,
            "load_aois_counts": dict(load_aois_counts),
            "criteria_met": criteria,
            "measured_criteria_met": all(value for value in criteria.values() if value is not None),
            "criteria_note": "pii_whitelist is enforced by this build and checked by the test named under "
                             "facilities.pii_whitelist. The compute window is recorded under run.",
        },
        "baseline_no_route": {
            "definition": "Residents on graph-connected demand cells with no modelled route to any OSM hospital in "
                          "the routing context, divided by all residents on graph-connected demand cells. Whole "
                          "frame only.",
            "travel_mode": travel_mode,
            "with_grade_joins": _rounded(share_joined),
            "without_grade_joins": _rounded(share_unjoined),
        },
        "reproduction_check": (
            reproduction_check(observed, expected, facilities_supplied=len(supplied))
            if expected is not None else None
        ),
        "frame_hospital_check": frame_hospitals,
        "input_hashes": dict(sorted(inputs.items())),
        "assumptions": [
            "The routing geometry, demand area and reporting geometry follow protocol v1b for this case and are "
            "named by their hashes.",
            "Road times are fixed class speeds on an undirected graph. One-way rules, turn restrictions and road "
            "condition are not represented.",
            "A grade join shows that two ways end at the same OSM coordinate (0 m tolerance). It does not show that "
            "the transition can be driven.",
            *FACILITY_ASSUMPTIONS,
        ],
        "limitations": [
            "One build on one machine. Facility counts are counts of map and list records; no hospital and no "
            "shelter was checked on the ground.",
            "The facility table and the context hold DDPM rows (pitch level) and stay outside Git.",
        ],
    }
    if expected is None:
        receipt["reproduction_check_note"] = (
            "The reproduction values of protocol v1b belong to the Mae Sai corridor in vehicle mode; this build has none."
        )
    return {
        "join_log": log_bytes,
        "facility_table": table_bytes,
        "receipt_body": receipt,
        "context_canonical_sha256": context["canonical_sha256"],
    }


def receipt_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return a receipt without its ``run`` section: the part a rebuild must reproduce byte for byte."""

    return {key: value for key, value in receipt.items() if key != "run"}
