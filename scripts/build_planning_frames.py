"""Build the pf-07 planning frame, the SE2 routing geometry and hospitals, and the SE2-blind units.

Protocol v1b, open item OI-09. The owners adopted the rules of owner choice 15
on 3 October 2026 (decision log R12, every choice as recommended). The sheet had
asked Rachmania for the frame file; with the rule decided, this script builds it
from the rule, and Rachmania reviews the result. The rules are in
``floodguard.planning_frames``.

It writes three files under ``resources/planning_frames/`` (plan 3.1: new
frames live there, not in ``resources/aoi/``, so ``load_aois`` still returns six):

* ``pf-07_mueang_chiang_rai.geojson``: the 16 tambons of Mueang Chiang Rai
  district, one feature each, with their COD-AB geometry;
* ``pf-07_mueang_chiang_rai_routing.geojson``: the SE2 routing geometry;
* ``planning_frames_v1_receipt.json``: the SE2 hospital list, the district
  office lookup for the SE2-blind district, the SE2-blind unit list, and the
  hashes of every input and output.

The two GeoJSON files carry no run time, so rebuilding them from the same
inputs gives the same bytes; ``--verify`` rebuilds everything in memory and
compares it with the committed files without writing.

It reads no flood layer and computes no exposure, access result, FPPS, A-E class
or ensemble. Inputs live outside Git, so their locations are arguments::

    python scripts/build_planning_frames.py \
        --boundaries <external data root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip \
        --osm-pbf <external data root>/open_context/osm_geofabrik/thailand-latest.osm.pbf \
        --work-dir <a scratch folder outside Git> [--verify]
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import planning_frames as frames  # noqa: E402

SCHEMA_VERSION = "floodguard.planning_frames.v1"
FRAME_DIR = ROOT / "resources" / "planning_frames"
FRAME_PATH = FRAME_DIR / "pf-07_mueang_chiang_rai.geojson"
ROUTING_PATH = FRAME_DIR / "pf-07_mueang_chiang_rai_routing.geojson"
RECEIPT_PATH = FRAME_DIR / "planning_frames_v1_receipt.json"
PROTOCOL_V1B = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
SOURCE_MANIFEST = ROOT / "outputs" / "open_context_data_file_manifest.csv"
PF07_DISTRICT = "TH5701"
PF07_EXPECTED_UNITS = 16
BLIND_WINDOW_MARGIN_DEG = 0.05
# The drafting agent expected this tambon to hold the Phan district office (owner choice 15c) without checking.
EXPECTED_SEAT_BY_DRAFTER = "TH570513"

DECISION = {
    "decision_log_entry": "R12",
    "decided_on": "2026-10-03",
    "decided_by": "Owners Putu and Rachmania (decision log R12, relayed by Putu)",
    "owner_choice": 15,
    "answers": {
        "a_unit_list": "A: all 16 tambons of Mueang Chiang Rai district",
        "b_routing_and_hospitals": "as recommended: the union of the pf-07 tambons with a 3 km buffer, clipped to "
                                   "Thailand; every OSM hospital inside it",
        "c_se2_blind_units": "B: the tambon that holds the district office and every tambon that touches it",
    },
    "decision_log_line_sha256": "8c3f7e20cedabb8f4593311f1f3603880595cc40994006b6253e0b92cc579f50",
    "decision_log_line_note": "SHA-256 of the UTF-8 bytes of the R12 row of docs/decision-log-d1-d16.md, without its "
                              "line ending, at commit 522194e of branch claude/mae-sai-next.",
}
RULES = {
    "pf07_unit_list": "Every COD-AB tha_admin3 unit whose adm2_pcode is TH5701 (Mueang Chiang Rai district).",
    "se2_routing_geometry": "The union of the pf-07 units, buffered by 3,000 m in EPSG:32647 (16 segments per quarter "
                            "circle), projected to WGS84 and intersected with the COD-AB tha_admin0 polygon of "
                            "Thailand.",
    "se2_hospitals": "Every OSM object tagged amenity=hospital or healthcare=hospital whose routing point the routing "
                     "geometry covers. Object, identity and routing point as in "
                     "floodguard.evidence_context.build_context_inputs: a node is its point; a way or relation is its "
                     "representative point, or its one tagged entrance node when it has exactly one. The OSM extract "
                     "is the bounding box of the routing geometry, read as that builder reads it.",
    "district_office_lookup": "Inside the COD-AB polygon of the SE2-blind district, an OSM object whose name or "
                              "name:th is 'thi wa kan amphoe' or 'samnak ngan amphoe' (district office) followed by "
                              "the district's Thai name in COD-AB, and which carries amenity=townhall or an office=* "
                              "tag. A node is its point; an area is its representative point. The seat tambon is the "
                              "tha_admin3 unit that covers that point. Objects with the name and neither tag are "
                              "listed as corroboration only. No object, or tagged objects in two units, leaves the "
                              "seat empty.",
    "se2_blind_units": "Owner choice 15(c), option B: the seat tambon and every tha_admin3 unit of the same district "
                       "whose polygon touches it (shared boundary, point contact or overlap). A touching unit of "
                       "another district is reported and left out, because the question was which tambons of the "
                       "blind district make the case.",
}
CONFIDENCE_BASIS = (
    "Administrative boundaries valid on 2022-01-22 and OpenStreetMap records retrieved on 2026-07-10, neither checked "
    "on the ground. The rules are owner decisions; the build has not yet been reviewed by Rachmania."
)
FRAME_ASSUMPTIONS = [
    "The 2022 COD-AB tha_admin3 polygons are the tambons of Mueang Chiang Rai district; their geometry is copied "
    "unchanged.",
    "A planning frame lists units. It holds no flood input, no exposure, no access result, no FPPS and no class.",
]
ROUTING_ASSUMPTIONS = [
    "The routing geometry is the area the SE2 context build may route through. It is not a flood extent.",
    "Roads and hospitals outside it are left out of SE2 routing, even where a route would leave and re-enter it.",
    "Thailand is the COD-AB tha_admin0 polygon; roads in neighbouring countries are not used.",
]
RECEIPT_ASSUMPTIONS = [
    "OSM hospitals are map records. Their operation, entrances and capacity are not verified.",
    "The district office is located by an OSM object, not by an official register. The object's tags and the "
    "objects that corroborate it are recorded.",
    "COD-AB polygons of 2022 are taken as the tambons; a tambon boundary change since then is not reflected.",
]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    """Serialise the receipt: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _recorded_sources() -> dict[str, dict[str, str]]:
    with SOURCE_MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        return {row["source_group"]: row for row in csv.DictReader(stream)}


def _row(record: Any) -> dict[str, Any]:
    """One boundary row in the shape ``floodguard.planning_frames`` expects."""

    if str(record["lang1"]) != "th":
        raise frames.PlanningFrameError("COD-AB adm3_name1 is not the Thai name")
    return {
        "adm3_pcode": str(record["adm3_pcode"]),
        "adm3_name": str(record["adm3_name"]),
        "adm3_name_th": str(record["adm3_name1"]),
        "adm2_pcode": str(record["adm2_pcode"]),
        "adm2_name": str(record["adm2_name"]),
        "adm1_pcode": str(record["adm1_pcode"]),
        "valid_on": str(record["valid_on"])[:10],
        "geometry": record["geometry"],
    }


def read_inputs(boundaries: Path, pbf: Path, work_dir: Path) -> dict[str, Any]:
    """Read every input from disk and check its SHA-256 against the committed source manifest."""

    import pyogrio
    from shapely.geometry import box
    from shapely.ops import unary_union

    from floodguard.evidence_context import _extract_osm, ogr_runtime_identity
    from floodguard.open_context_extract import _run_ogr2ogr, find_qgis_bin

    recorded = _recorded_sources()
    hashes = {"boundaries_sha256": sha256_file(boundaries), "osm_pbf_sha256": sha256_file(pbf)}
    if hashes["boundaries_sha256"] != recorded["hdx_cod_ab"]["sha256"]:
        raise ValueError("the boundary file differs from outputs/open_context_data_file_manifest.csv")
    if hashes["osm_pbf_sha256"] != recorded["osm_geofabrik"]["sha256"]:
        raise ValueError("the OSM extract differs from outputs/open_context_data_file_manifest.csv")
    v1b = json.loads(PROTOCOL_V1B.read_text(encoding="utf-8"))
    if hashes["boundaries_sha256"] not in v1b["corridor_polygon"]["construction"]["boundary_source"]:
        raise ValueError("the boundary file is not the one protocol v1b names")
    blind_code = v1b["corridor_polygon"]["se2_frame"]["se2_blind_district"]["adm2_pcode"]

    columns = ["adm3_pcode", "adm3_name", "adm3_name1", "lang1", "adm2_pcode", "adm2_name", "adm1_pcode", "valid_on"]
    pf07 = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=columns, where=f"adm2_pcode = '{PF07_DISTRICT}'")
    district = pyogrio.read_dataframe(
        boundaries, layer="tha_admin2", columns=["adm2_pcode", "adm2_name", "adm2_name1", "lang1"],
        where=f"adm2_pcode = '{blind_code}'",
    )
    if len(district) != 1 or str(district.iloc[0]["lang1"]) != "th":
        raise ValueError(f"district {blind_code} must appear once with a Thai name")
    district_geometry = district.geometry.iloc[0]
    west, south, east, north = district_geometry.bounds
    margin = BLIND_WINDOW_MARGIN_DEG
    window = (west - margin, south - margin, east + margin, north + margin)
    near_blind = pyogrio.read_dataframe(boundaries, layer="tha_admin3", columns=columns, bbox=window)
    country = pyogrio.read_dataframe(boundaries, layer="tha_admin0", columns=["adm0_pcode"])
    if len(country) != 1:
        raise ValueError("tha_admin0 must hold one feature")

    pf07_rows = [_row(record) for _, record in pf07.iterrows()]
    unit_bounds = unary_union([row["geometry"] for row in pf07_rows]).bounds
    # Enough room for a 3 km buffer at this latitude; the clip only needs the country near the frame.
    pad = 0.1
    country_near = country.geometry.iloc[0].intersection(
        box(unit_bounds[0] - pad, unit_bounds[1] - pad, unit_bounds[2] + pad, unit_bounds[3] + pad)
    )

    office_dir = work_dir / "district_office"
    office_dir.mkdir(parents=True, exist_ok=True)
    routing_osm_dir = work_dir / "se2_routing_osm"
    routing_osm_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = find_qgis_bin()
    office_features: list[dict[str, Any]] = []
    for layer in ("points", "multipolygons"):
        target = office_dir / f"{layer}.geojson"
        _run_ogr2ogr(bin_dir, ["-f", "GeoJSON", "-spat", *[str(value) for value in district_geometry.bounds],
                               "-where", "name IS NOT NULL", "-lco", "RFC7946=YES", str(target), str(pbf), layer])
        office_features.extend(json.loads(target.read_text(encoding="utf-8"))["features"])

    return {
        "pf07_rows": pf07_rows,
        "near_blind_rows": [_row(record) for _, record in near_blind.iterrows()],
        "blind_district": {
            "adm2_pcode": blind_code,
            "adm2_name": str(district.iloc[0]["adm2_name"]),
            "adm2_name_th": str(district.iloc[0]["adm2_name1"]),
            "geometry": district_geometry,
        },
        "country_wgs84": country_near,
        "osm_extract": lambda routing_bounds, routing_wkb_sha256: _extract_osm(
            pbf, routing_bounds, routing_osm_dir, hashes["osm_pbf_sha256"], routing_wkb_sha256,
        ),
        "office_features": office_features,
        "input_hashes": hashes,
        "osm_retrieved_at_utc": recorded["osm_geofabrik"]["retrieved_at_utc"],
        "ogr_runtime": ogr_runtime_identity(bin_dir),
    }


def _frame_header(name: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
    }


def _provenance(source_timestamp: str, note: str, assumptions: list[str]) -> dict[str, Any]:
    return {
        "source_timestamp": source_timestamp,
        "source_timestamp_note": note,
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "assumptions": assumptions,
        "official_warning": False,
        "operational_status": "non_operational",
        "review_status": "Built by the AI coding agent from the rule the owners decided (R12); awaiting Rachmania's "
                         "review.",
    }


def build_outputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply the decided rules to inputs already read and return the file bytes and the receipt body.

    ``inputs`` holds the keys ``read_inputs`` returns. ``osm_extract`` is a callable
    that takes the routing bounds and the SHA-256 of the routing geometry's WKB and
    returns ``(roads, facility_features)`` as ``_extract_osm`` does.
    """

    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    from floodguard.evidence_context import _osm_facilities, _tags

    forward = Transformer.from_crs(4326, frames.METRIC_EPSG, always_xy=True).transform
    backward = Transformer.from_crs(frames.METRIC_EPSG, 4326, always_xy=True).transform

    def to_metres(geometry: Any) -> Any:
        return transform(forward, geometry)

    def to_wgs84(geometry: Any) -> Any:
        return transform(backward, geometry)

    units = frames.district_units(inputs["pf07_rows"], PF07_DISTRICT)
    if len(units) != PF07_EXPECTED_UNITS:
        raise frames.PlanningFrameError(f"Mueang Chiang Rai has {len(units)} units in COD-AB, not {PF07_EXPECTED_UNITS}")
    valid_on = sorted({row["valid_on"] for row in units})
    if len(valid_on) != 1:
        raise frames.PlanningFrameError("the pf-07 units carry different valid_on dates")
    boundary_note = "COD-AB valid_on date of the tambon boundaries."
    frame_features = []
    for row in units:
        properties = {
            "frame_id": "pf-07",
            "frame_name": "Mueang Chiang Rai",
            "case": "SE2",
            **{field: row[field] for field in frames.UNIT_FIELDS},
            "boundary_source": "HDX Thailand COD-AB, layer tha_admin3",
            "boundary_sha256": inputs["input_hashes"]["boundaries_sha256"],
            "rule": RULES["pf07_unit_list"],
            "decision": "Decision log R12, owner choice 15(a), option A.",
            **_provenance(valid_on[0], boundary_note, FRAME_ASSUMPTIONS),
        }
        frame_features.append({"type": "Feature", "properties": properties,
                               "geometry": frames.geojson_geometry(row["geometry"])})
    frame_bytes = frames.encode_feature_collection(_frame_header("pf-07_mueang_chiang_rai"), frame_features)

    routing = frames.routing_geometry([to_metres(row["geometry"]) for row in units], to_wgs84, inputs["country_wgs84"])
    routing_json = frames.geojson_geometry(routing)
    routing_geometry_sha256 = frames.geometry_sha256(routing_json)
    area_km2 = round(to_metres(routing).area / 1e6, 2)
    routing_feature = {
        "type": "Feature",
        "properties": {
            "id": "pf-07_se2_routing_geometry",
            "frame_id": "pf-07",
            "case": "SE2",
            "rule": RULES["se2_routing_geometry"],
            "decision": "Decision log R12, owner choice 15(b), as recommended.",
            "buffer_m": frames.ROUTING_BUFFER_M,
            "buffer_epsg": frames.METRIC_EPSG,
            "buffer_quad_segs": frames.BUFFER_QUAD_SEGS,
            "area_km2": area_km2,
            "geometry_sha256": routing_geometry_sha256,
            "boundary_sha256": inputs["input_hashes"]["boundaries_sha256"],
            **_provenance(valid_on[0], boundary_note, ROUTING_ASSUMPTIONS),
        },
        "geometry": routing_json,
    }
    routing_bytes = frames.encode_feature_collection(_frame_header("pf-07_mueang_chiang_rai_routing"), [routing_feature])

    # The hospital list is what a context build on the routing geometry would see.
    routing_from_file = shape(routing_json)
    _roads, facility_features = inputs["osm_extract"](routing_from_file.bounds,
                                                      hashlib.sha256(routing_from_file.wkb).hexdigest())
    del _roads
    english = {}
    for feature in facility_features["features"]:
        tags = _tags(feature.get("properties", {}))
        if "hospital" in {tags.get("amenity"), tags.get("healthcare")} and tags.get("name:en"):
            english[frames.osm_identifier(tags, feature["geometry"]["type"])] = tags["name:en"]
    facilities = _osm_facilities(facility_features, role_map={"hospital": "hospital"})
    hospitals = frames.hospitals_inside(facilities, routing_from_file, english)

    district = inputs["blind_district"]
    near = inputs["near_blind_rows"]
    district_rows = frames.district_units(near, district["adm2_pcode"])
    candidates = frames.district_office_candidates(inputs["office_features"], district["adm2_name_th"],
                                                   district["geometry"])
    seat = frames.seat_unit(candidates["tagged_office"], district_rows)
    names = {row["adm3_pcode"]: row["adm3_name"] for row in near}
    lookup: dict[str, Any] = {
        "district": {key: district[key] for key in ("adm2_pcode", "adm2_name", "adm2_name_th")},
        "office_names_searched": [frames.DISTRICT_OFFICE_PREFIX_TH + district["adm2_name_th"],
                                  frames.DISTRICT_OFFICE_ALT_PREFIX_TH + district["adm2_name_th"]],
        "tagged_office": candidates["tagged_office"],
        "named_only": candidates["named_only"],
        "result": "found" if seat else "not_found",
        "seat_adm3_pcode": seat,
        "seat_adm3_name": names.get(seat) if seat else None,
        "expected_by_the_drafting_agent": EXPECTED_SEAT_BY_DRAFTER,
        "matches_the_drafting_agent_expectation": seat == EXPECTED_SEAT_BY_DRAFTER,
    }
    corroboration = []
    for row in candidates["named_only"]:
        point = shape({"type": "Point", "coordinates": row["point_lon_lat"]})
        corroboration.append({"osm_identifier": row["osm_identifier"],
                              "covered_by": sorted(r["adm3_pcode"] for r in district_rows if r["geometry"].covers(point))})
    lookup["named_only_covered_by"] = corroboration

    blind = frames.seat_and_touching_units(seat, district["adm2_pcode"], near, to_metres) if seat else None

    receipt_body = {
        "schema_version": SCHEMA_VERSION,
        "protocol_item": "planning_protocol_v1b open item OI-09, corridor_polygon.se2_frame (plan 3.1, 6.1 and 8.1 "
                         "row P1; owner choice 15)",
        "status": "built_from_owner_decided_rules_awaiting_review",
        "status_note": "Built by the AI coding agent from the rules the owners adopted in decision log R12 (owner "
                       "choice 15, as recommended). The owner-choices sheet had asked Rachmania for the pf-07 frame "
                       "file; with the rule decided the agent built it from the rule. Rachmania reviews the frame, "
                       "the routing geometry, the hospital list and the district office lookup.",
        "decision": DECISION,
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "Unit lists, a buffered routing polygon, a list of OSM hospitals and a point-in-polygon lookup of "
                    "one OSM object. No flood layer is read. No exposure, access result, FPPS, A-E class or ensemble.",
        "source_timestamp": inputs["osm_retrieved_at_utc"],
        "source_timestamps": {"boundaries_valid_on": valid_on[0],
                              "osm_extract_retrieved_at_utc": inputs["osm_retrieved_at_utc"]},
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "rules": RULES,
        "pf07_frame": {
            "path": FRAME_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(frame_bytes).hexdigest(),
            "district": {"adm2_pcode": PF07_DISTRICT, "adm2_name": units[0]["adm2_name"]},
            "unit_count": len(units),
            "unit_list": [row["adm3_pcode"] for row in units],
        },
        "se2_routing_geometry": {
            "path": ROUTING_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(routing_bytes).hexdigest(),
            "geometry_sha256": routing_geometry_sha256,
            "geometry_type": routing.geom_type,
            "area_km2": area_km2,
            "bounds_wgs84": [round(value, 6) for value in routing_from_file.bounds],
        },
        "se2_hospitals": {
            "hospitals": hospitals,
            "counts": frames.hospital_counts(hospitals),
            "counts_note": "osm_objects counts OSM objects. Under owner choice 22 (R12) a hospital is a distinct "
                           "named hospital; both counts are given.",
        },
        "district_office_lookup": lookup,
        "se2_blind_units": blind or {"seat": None, "unit_list": None,
                                     "note": "No tagged district office was found, so the rule gives no unit list."},
        "input_hashes": inputs["input_hashes"],
        "assumptions": RECEIPT_ASSUMPTIONS,
        "limitations": [
            "SE2-blind is blind by rule, not by ignorance: flooded shares for every Chiang Rai tambon were seen in "
            "exploration (v1a disclosure item EK-09). The rules here read no flood layer.",
            "The choice of SE2 itself was made with the outcome in view (v1a case-selection disclosure); a whole "
            "district adds no further tambon-by-tambon choice.",
            "The hospital list depends on the OSM extract of 2026-07-10. A later extract can add or drop objects.",
        ],
    }
    return {"frame_bytes": frame_bytes, "routing_bytes": routing_bytes, "receipt_body": receipt_body}


def _library_versions(inputs: dict[str, Any]) -> dict[str, Any]:
    import pyproj
    import shapely

    return {
        "shapely": shapely.__version__,
        "geos": ".".join(str(part) for part in shapely.geos_version),
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "ogr_runtime": inputs["ogr_runtime"],
    }


def main(argv: list[str] | None = None) -> int:
    """Build the frames and write them, or rebuild and compare with ``--verify``."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--osm-pbf", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="scratch folder outside Git for OSM extracts")
    parser.add_argument("--verify", action="store_true", help="rebuild and compare with the committed files")
    args = parser.parse_args(argv)
    if ROOT in args.work_dir.resolve().parents or args.work_dir.resolve() == ROOT:
        parser.error("--work-dir must be outside the repository")

    inputs = read_inputs(args.boundaries, args.osm_pbf, args.work_dir)
    built = build_outputs(inputs)
    body = built["receipt_body"]
    if args.verify:
        committed = json.loads(RECEIPT_PATH.read_text(encoding="ascii"))
        problems = []
        if FRAME_PATH.read_bytes() != built["frame_bytes"]:
            problems.append("the pf-07 frame file differs from a rebuild")
        if ROUTING_PATH.read_bytes() != built["routing_bytes"]:
            problems.append("the routing geometry file differs from a rebuild")
        for key in ("pf07_frame", "se2_routing_geometry", "se2_hospitals", "district_office_lookup",
                    "se2_blind_units", "input_hashes", "rules"):
            if committed[key] != json.loads(json.dumps(body[key])):
                problems.append(f"receipt section {key} differs from a rebuild")
        print(json.dumps({"verified": not problems, "problems": problems}))
        return 1 if problems else 0

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    receipt = {
        "schema_version": body["schema_version"],
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **{key: value for key, value in body.items() if key != "schema_version"},
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "builder_sha256": sha256_file(Path(__file__)),
            "module_sha256": sha256_file(ROOT / "src" / "floodguard" / "planning_frames.py"),
            "libraries": _library_versions(inputs),
        },
    }
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    FRAME_PATH.write_bytes(built["frame_bytes"])
    ROUTING_PATH.write_bytes(built["routing_bytes"])
    RECEIPT_PATH.write_bytes(encode(receipt))
    print(json.dumps({
        "frame_sha256": body["pf07_frame"]["sha256"],
        "routing_sha256": body["se2_routing_geometry"]["sha256"],
        "receipt_sha256": sha256_file(RECEIPT_PATH),
        "hospitals": body["se2_hospitals"]["counts"],
        "seat": body["district_office_lookup"]["seat_adm3_pcode"],
        "se2_blind_units": body["se2_blind_units"]["unit_list"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
