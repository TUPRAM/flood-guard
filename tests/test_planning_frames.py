"""The pf-07 frame, the SE2 routing geometry and hospitals, and the SE2-blind office lookup (OI-09).

Most tests run the rules of ``floodguard.planning_frames`` and the build step of
``scripts/build_planning_frames.py`` on invented squares and invented OSM
objects. The last tests read the committed frame files and check that they,
their receipt and protocol v1b say the same thing. Nothing here reads a flood
layer or computes an exposure, an FPPS, an A-E class or an ensemble.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

from floodguard import planning_frames as frames
from floodguard.config import VALID_CONFIDENCE_CLASSES

ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = ROOT / "resources" / "planning_frames"
FRAME = FRAME_DIR / "pf-07_mueang_chiang_rai.geojson"
ROUTING = FRAME_DIR / "pf-07_mueang_chiang_rai_routing.geojson"
RECEIPT = FRAME_DIR / "planning_frames_v1_receipt.json"
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
OFFICE_TH = frames.DISTRICT_OFFICE_PREFIX_TH
PHAN_TH = "พาน"
STEP = 0.01


def _identity(geometry: Any) -> Any:
    return geometry


def _square(column: int, row: int, x0: float, y0: float, step: float = STEP) -> Any:
    return box(x0 + column * step, y0 + row * step, x0 + (column + 1) * step, y0 + (row + 1) * step)


def _unit(code: str, district: str, geometry: Any, name: str | None = None) -> dict[str, Any]:
    return {
        "adm3_pcode": code, "adm3_name": name or f"Unit {code}", "adm3_name_th": f"th {code}",
        "adm2_pcode": district, "adm2_name": f"District {district}", "adm1_pcode": district[:4],
        "valid_on": "2022-01-22", "geometry": geometry,
    }


def _blind_grid() -> list[dict[str, Any]]:
    """Nine squares of district TH5705 (codes 01-09, row by row) and one square of TH5706 east of square 06."""

    units = [_unit(f"TH5705{row * 3 + column + 1:02d}", "TH5705", _square(column, row, 99.70, 19.50))
             for row in range(3) for column in range(3)]
    units.append(_unit("TH570601", "TH5706", _square(3, 1, 99.70, 19.50)))
    return units


def _point_feature(osm_id: str, coordinates: list[float], **tags: str) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"osm_id": osm_id, **tags},
            "geometry": {"type": "Point", "coordinates": coordinates}}


def _area_feature(way_id: str, polygon: Any, **tags: str) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"osm_way_id": way_id, **tags},
            "geometry": json.loads(json.dumps(polygon.__geo_interface__))}


# ---------------------------------------------------------------------------
# Units and routing geometry
# ---------------------------------------------------------------------------


def test_district_units_keeps_one_district_sorted_and_refuses_bad_rows() -> None:
    rows = [_unit("TH570102", "TH5701", box(0, 0, 1, 1)), _unit("TH570101", "TH5701", box(1, 0, 2, 1)),
            _unit("TH570201", "TH5702", box(2, 0, 3, 1))]
    assert [row["adm3_pcode"] for row in frames.district_units(rows, "TH5701")] == ["TH570101", "TH570102"]
    with pytest.raises(frames.PlanningFrameError, match="no unit"):
        frames.district_units(rows, "TH5799")
    with pytest.raises(frames.PlanningFrameError, match="repeats"):
        frames.district_units([*rows, _unit("TH570101", "TH5701", box(5, 5, 6, 6))], "TH5701")
    bowtie = shape({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]})
    with pytest.raises(frames.PlanningFrameError, match="invalid"):
        frames.district_units([_unit("TH570101", "TH5701", bowtie)], "TH5701")
    with pytest.raises(frames.PlanningFrameError, match="district code"):
        frames.district_units([_unit("TH570301", "TH5701", box(0, 0, 1, 1))], "TH5701")


def test_routing_geometry_buffers_the_union_and_clips_it_to_the_country() -> None:
    units = [box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000)]
    country = box(-10_000, -10_000, 10_000, 10_000)
    full = frames.routing_geometry(units, _identity, country, buffer_m=3000)
    assert full.covers(Point(-2999, 500)) and not full.covers(Point(-3001, 500))
    assert full.area == pytest.approx(2000 * 1000 + 2 * 3000 * (2000 + 1000) + 3.14159 * 3000**2, rel=2e-3)
    # The country ends 1 km west of the units: nothing west of it stays.
    clipped = frames.routing_geometry(units, _identity, box(-1000, -10_000, 10_000, 10_000), buffer_m=3000)
    assert clipped.bounds[0] == pytest.approx(-1000) and clipped.area < full.area
    with pytest.raises(frames.PlanningFrameError, match="no unit"):
        frames.routing_geometry([], _identity, country)
    with pytest.raises(frames.PlanningFrameError, match="positive"):
        frames.routing_geometry(units, _identity, country, buffer_m=0)
    with pytest.raises(frames.PlanningFrameError, match="empty"):
        frames.routing_geometry(units, _identity, box(50_000, 50_000, 60_000, 60_000))


def test_hospitals_inside_uses_the_routing_point_and_keeps_only_hospitals() -> None:
    routing = box(0, 0, 10, 10)
    rows = [
        {"facility_id": "OSM-way-2", "name": "B", "service_type": "hospital",
         "geometry": {"type": "Point", "coordinates": [5, 5]}, "source_geometry_type": "MultiPolygon"},
        {"facility_id": "OSM-node-1", "name": "A", "service_type": "hospital",
         "geometry": {"type": "Point", "coordinates": [10, 5]}},  # on the boundary: covered
        {"facility_id": "OSM-node-3", "name": "C", "service_type": "hospital",
         "geometry": {"type": "Point", "coordinates": [11, 5]}},
        {"facility_id": "OSM-node-4", "name": "D", "service_type": "primary_care",
         "geometry": {"type": "Point", "coordinates": [5, 5]}},
    ]
    kept = frames.hospitals_inside(rows, routing, {"OSM-way-2": "B hospital"})
    assert [row["facility_id"] for row in kept] == ["OSM-node-1", "OSM-way-2"]
    assert kept[1]["name_en"] == "B hospital" and "name_en" not in kept[0]
    with pytest.raises(frames.PlanningFrameError, match="twice"):
        frames.hospitals_inside([rows[0], rows[0]], routing)


def test_hospital_counts_separate_objects_names_and_unnamed_objects() -> None:
    rows = [{"name": "A"}, {"name": "A"}, {"name": "B"}, {"name": "Unnamed OSM candidate"}]
    assert frames.hospital_counts(rows) == {
        "osm_objects": 4, "distinct_named_hospitals": 2, "unnamed_objects": 1,
        "objects_that_repeat_a_named_hospital": 1,
    }


# ---------------------------------------------------------------------------
# District office lookup and the SE2-blind units (owner choice 15c, option B)
# ---------------------------------------------------------------------------


def test_office_lookup_needs_the_exact_name_an_office_tag_and_the_district() -> None:
    district = box(99.70, 19.50, 99.73, 19.53)
    inside, outside = [99.725, 19.515], [99.80, 19.515]
    features = [
        _point_feature("1", inside, name=OFFICE_TH + PHAN_TH, office="administrative"),
        _point_feature("2", inside, name=OFFICE_TH + PHAN_TH),  # named, no tag
        _point_feature("3", outside, name=OFFICE_TH + PHAN_TH, office="government"),  # other district
        _point_feature("4", inside, name=OFFICE_TH + PHAN_TH + "ทอง", office="government"),
        _point_feature("5", inside, name="something else", amenity="townhall"),
        _point_feature("6", inside, **{"name:th": frames.DISTRICT_OFFICE_ALT_PREFIX_TH + PHAN_TH,
                                       "other_tags": '"amenity"=>"townhall"'}),
        _area_feature("7", box(99.721, 19.511, 99.722, 19.512), name=frames.DISTRICT_OFFICE_ALT_PREFIX_TH + PHAN_TH,
                      landuse="commercial"),
        {"type": "Feature", "properties": {"osm_id": "8", "name": OFFICE_TH + PHAN_TH, "office": "government"},
         "geometry": {"type": "LineString", "coordinates": [inside, outside]}},
    ]
    found = frames.district_office_candidates(features, PHAN_TH, district)
    assert [row["osm_identifier"] for row in found["tagged_office"]] == ["OSM-node-1", "OSM-node-6"]
    assert [row["osm_identifier"] for row in found["named_only"]] == ["OSM-node-2", "OSM-way-7"]
    office = found["tagged_office"][0]
    assert office["osm_type"] == "node" and office["osm_id"] == 1 and office["point_lon_lat"] == inside
    assert office["tags"] == {"office": "administrative"} and office["point_source"] == "node"
    assert found["tagged_office"][1]["tags"] == {"amenity": "townhall"}
    assert found["named_only"][1]["point_source"] == "representative point of the area"
    with pytest.raises(frames.PlanningFrameError, match="Thai name"):
        frames.district_office_candidates(features, "", district)


def test_the_seat_is_the_one_unit_that_covers_every_tagged_office() -> None:
    units = _blind_grid()[:9]
    centre = list(_square(2, 1, 99.70, 19.50).centroid.coords[0])
    assert frames.containing_unit(Point(centre), units) == "TH570506"
    shared_edge_x = _square(1, 0, 99.70, 19.50).bounds[0]
    with pytest.raises(frames.PlanningFrameError, match="2 units"):
        frames.containing_unit(Point(shared_edge_x, 19.505), units)  # on the edge between squares 01 and 02
    with pytest.raises(frames.PlanningFrameError, match="0 units"):
        frames.containing_unit(Point(98.0, 18.0), units)

    assert frames.seat_unit([], units) is None
    office = {"point_lon_lat": centre}
    assert frames.seat_unit([office, deepcopy(office)], units) == "TH570506"
    elsewhere = {"point_lon_lat": list(_square(0, 0, 99.70, 19.50).centroid.coords[0])}
    with pytest.raises(frames.PlanningFrameError, match="different units"):
        frames.seat_unit([office, elsewhere], units)


def test_rule_b_takes_the_seat_and_every_touching_unit_of_its_district() -> None:
    result = frames.seat_and_touching_units("TH570506", "TH5705", _blind_grid(), _identity)
    assert result["seat"] == "TH570506"
    assert result["unit_list"] == ["TH570502", "TH570503", "TH570505", "TH570506", "TH570508", "TH570509"]
    contact = {row["adm3_pcode"]: row["contact"] for row in result["touching_units"]}
    assert contact == {"TH570502": "point_contact", "TH570503": "shared_boundary", "TH570505": "shared_boundary",
                       "TH570508": "point_contact", "TH570509": "shared_boundary"}
    assert [row["adm3_pcode"] for row in result["touching_units_outside_the_district"]] == ["TH570601"]
    with pytest.raises(frames.PlanningFrameError, match="not among"):
        frames.seat_and_touching_units("TH570599", "TH5705", _blind_grid(), _identity)
    with pytest.raises(frames.PlanningFrameError, match="not in district"):
        frames.seat_and_touching_units("TH570601", "TH5705", _blind_grid(), _identity)


def test_encoding_is_deterministic_ascii_and_one_feature_per_line() -> None:
    header = {"type": "FeatureCollection", "name": "x"}
    features = [{"type": "Feature", "properties": {"name": PHAN_TH}, "geometry": {"type": "Point", "coordinates": [1, 2]}},
                {"type": "Feature", "properties": {"name": "b"}, "geometry": {"type": "Point", "coordinates": [3, 4]}}]
    raw = frames.encode_feature_collection(header, features)
    assert raw == frames.encode_feature_collection(header, deepcopy(features))
    raw.decode("ascii")
    assert b"\r" not in raw and raw.endswith(b"]}\n") and not raw.endswith(b"\n\n")
    assert len(raw.splitlines()) == 2 + len(features)
    assert json.loads(raw) == {**header, "features": features}
    with pytest.raises(frames.PlanningFrameError):
        frames.encode_feature_collection({**header, "features": []}, features)
    geometry = {"type": "Point", "coordinates": [1.5, 2.5]}
    expected = hashlib.sha256(b'{"coordinates":[1.5,2.5],"type":"Point"}').hexdigest()
    assert frames.geometry_sha256(geometry) == expected


# ---------------------------------------------------------------------------
# The build step of the script, on invented inputs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("build_planning_frames", ROOT / "scripts" / "build_planning_frames.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_inputs(*, with_office: bool = True) -> dict[str, Any]:
    pf07 = [_unit(f"TH5701{index + 1:02d}", "TH5701", _square(index % 4, index // 4, 99.80, 19.90))
            for index in range(16)]
    hospitals = {"type": "FeatureCollection", "features": [
        _point_feature("11", [99.815, 19.915], amenity="hospital", name="Inside", **{"name:en": "Inside hospital"}),
        _area_feature("12", box(99.82, 19.92, 99.821, 19.921), healthcare="hospital", name="Area"),
        _point_feature("13", [99.20, 19.20], amenity="hospital", name="Far away"),
        _point_feature("14", [99.815, 19.915], amenity="clinic", name="Clinic"),
    ]}
    grid = _blind_grid()
    centre = list(_square(2, 1, 99.70, 19.50).centroid.coords[0])
    office = [_point_feature("21", centre, name=OFFICE_TH + PHAN_TH, office="administrative")] if with_office else []
    return {
        "pf07_rows": pf07,
        "near_blind_rows": grid,
        "blind_district": {"adm2_pcode": "TH5705", "adm2_name": "Phan", "adm2_name_th": PHAN_TH,
                           "geometry": unary_union([row["geometry"] for row in grid[:9]])},
        "country_wgs84": box(99.0, 19.0, 101.0, 21.0),
        "osm_extract": lambda bounds, wkb_sha256: (None, deepcopy(hospitals)),
        "office_features": office,
        "input_hashes": {"boundaries_sha256": "0" * 64, "osm_pbf_sha256": "1" * 64},
        "osm_retrieved_at_utc": "2026-07-10T02:46:49Z",
    }


def test_build_gives_the_same_bytes_twice_and_applies_every_rule(builder) -> None:
    first, second = builder.build_outputs(_fixture_inputs()), builder.build_outputs(_fixture_inputs())
    assert first["frame_bytes"] == second["frame_bytes"]
    assert first["routing_bytes"] == second["routing_bytes"]
    assert first["receipt_body"] == second["receipt_body"]

    frame = json.loads(first["frame_bytes"])
    codes = [feature["properties"]["adm3_pcode"] for feature in frame["features"]]
    assert codes == sorted(codes) and len(codes) == 16
    for feature in frame["features"]:
        properties = feature["properties"]
        assert properties["frame_id"] == "pf-07" and properties["source_timestamp"] == "2022-01-22"
        assert properties["confidence_class"] in VALID_CONFIDENCE_CLASSES and properties["assumptions"]
        assert properties["official_warning"] is False and properties["operational_status"] == "non_operational"
        assert "generated_at_utc" not in properties, "a run time would change the bytes from run to run"

    routing = json.loads(first["routing_bytes"])["features"][0]
    geometry = shape(routing["geometry"])
    assert routing["properties"]["geometry_sha256"] == frames.geometry_sha256(routing["geometry"])
    assert all(geometry.covers(feature_geometry) for feature_geometry in
               (shape(feature["geometry"]) for feature in frame["features"]))

    body = first["receipt_body"]
    assert body["pf07_frame"]["sha256"] == hashlib.sha256(first["frame_bytes"]).hexdigest()
    assert body["pf07_frame"]["unit_list"] == codes
    assert [row["facility_id"] for row in body["se2_hospitals"]["hospitals"]] == ["OSM-node-11", "OSM-way-12"]
    assert body["se2_hospitals"]["hospitals"][0]["name_en"] == "Inside hospital"
    lookup = body["district_office_lookup"]
    assert lookup["result"] == "found" and lookup["seat_adm3_pcode"] == "TH570506"
    assert lookup["tagged_office"][0]["osm_identifier"] == "OSM-node-21"
    assert body["se2_blind_units"]["unit_list"] == ["TH570502", "TH570503", "TH570505", "TH570506",
                                                    "TH570508", "TH570509"]
    assert body["official_warning"] is False and body["confidence_class"] == "low" and body["assumptions"]


def test_build_leaves_the_seat_empty_when_no_office_is_found(builder) -> None:
    body = builder.build_outputs(_fixture_inputs(with_office=False))["receipt_body"]
    assert body["district_office_lookup"]["result"] == "not_found"
    assert body["district_office_lookup"]["seat_adm3_pcode"] is None
    assert body["se2_blind_units"]["unit_list"] is None


def test_build_refuses_a_frame_that_is_not_sixteen_units(builder) -> None:
    inputs = _fixture_inputs()
    inputs["pf07_rows"] = inputs["pf07_rows"][:15]
    with pytest.raises(frames.PlanningFrameError, match="16"):
        builder.build_outputs(inputs)


# ---------------------------------------------------------------------------
# The committed frame files, their receipt and protocol v1b
# ---------------------------------------------------------------------------


def _committed() -> tuple[bytes, bytes, dict[str, Any], dict[str, Any]]:
    if not RECEIPT.exists():
        pytest.skip("the planning frames have not been built on this checkout")
    receipt = json.loads(RECEIPT.read_text(encoding="ascii"))
    protocol = json.loads(PROTOCOL.read_text(encoding="ascii"))
    return FRAME.read_bytes(), ROUTING.read_bytes(), receipt, protocol


def test_committed_frame_files_are_the_ones_the_receipt_and_the_protocol_name() -> None:
    frame_raw, routing_raw, receipt, protocol = _committed()
    for raw in (frame_raw, routing_raw, RECEIPT.read_bytes()):
        raw.decode("ascii")
        assert b"\r" not in raw and raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    se2 = protocol["corridor_polygon"]["se2_frame"]
    recorded = se2["sha256"] is not None  # filled when OI-09 closes
    frame_sha256 = hashlib.sha256(frame_raw).hexdigest()
    assert receipt["pf07_frame"]["sha256"] == frame_sha256
    routing_sha256 = hashlib.sha256(routing_raw).hexdigest()
    assert receipt["se2_routing_geometry"]["sha256"] == routing_sha256
    if recorded:
        assert se2["sha256"] == frame_sha256 and se2["routing_geometry"]["sha256"] == routing_sha256
        assert ROOT / se2["planning_frame_file"] == FRAME and se2["file_exists_on_this_lineage"] is True
        assert ROOT / se2["routing_geometry"]["path"] == ROUTING

    frame = json.loads(frame_raw)
    codes = [feature["properties"]["adm3_pcode"] for feature in frame["features"]]
    assert len(codes) == 16 and codes == sorted(codes)
    assert all(feature["properties"]["adm2_pcode"] == "TH5701" for feature in frame["features"])
    assert codes == receipt["pf07_frame"]["unit_list"]
    if recorded:
        assert se2["unit_list"] == codes
    for feature in frame["features"]:
        properties = feature["properties"]
        assert properties["source_timestamp"] and properties["confidence_class"] == "low"
        assert properties["confidence_basis"].strip() and properties["assumptions"]
        assert properties["official_warning"] is False and properties["operational_status"] == "non_operational"
        assert not any(word in key for key in properties for word in ("fpps", "class_", "_0_100", "exposure"))

    routing = json.loads(routing_raw)["features"][0]
    assert routing["properties"]["geometry_sha256"] == frames.geometry_sha256(routing["geometry"])
    assert routing["properties"]["geometry_sha256"] == receipt["se2_routing_geometry"]["geometry_sha256"]
    if recorded:
        assert routing["properties"]["geometry_sha256"] == se2["routing_geometry"]["geometry_sha256"]
    geometry = shape(routing["geometry"])
    assert geometry.is_valid
    assert all(geometry.covers(shape(feature["geometry"]).representative_point()) for feature in frame["features"])


def test_committed_hospitals_and_seat_lookup_match_the_protocol() -> None:
    _frame_raw, _routing_raw, receipt, protocol = _committed()
    se2 = protocol["corridor_polygon"]["se2_frame"]
    hospitals = receipt["se2_hospitals"]["hospitals"]
    assert receipt["se2_hospitals"]["counts"] == frames.hospital_counts(hospitals)
    lookup = receipt["district_office_lookup"]
    assert lookup["district"]["adm2_pcode"] == se2["se2_blind_district"]["adm2_pcode"]
    if lookup["result"] == "found":
        assert lookup["seat_adm3_pcode"] == receipt["se2_blind_units"]["seat"]
        assert lookup["seat_adm3_pcode"] in receipt["se2_blind_units"]["unit_list"]
    if "se2_blind_seat_lookup" not in se2:
        pytest.skip("OI-09 is not closed yet: protocol v1b does not repeat the build")

    assert [row["facility_id"] for row in se2["hospital_destinations"]] == [row["facility_id"] for row in hospitals]
    recorded = se2["se2_blind_seat_lookup"]
    if lookup["result"] == "not_found":
        assert se2["se2_blind_unit_list"] is None and recorded["seat_adm3_pcode"] is None
        return
    office = lookup["tagged_office"][0]
    assert recorded["office_osm_identifier"] == office["osm_identifier"]
    assert recorded["office_point_lon_lat"] == office["point_lon_lat"]
    assert recorded["seat_adm3_pcode"] == lookup["seat_adm3_pcode"] == receipt["se2_blind_units"]["seat"]
    assert se2["se2_blind_unit_list"] == receipt["se2_blind_units"]["unit_list"]
    assert lookup["seat_adm3_pcode"] in se2["se2_blind_unit_list"]
    district = se2["se2_blind_district"]["adm2_pcode"]
    assert all(code.startswith(district) for code in se2["se2_blind_unit_list"])
    assert recorded["build_receipt_sha256"] == hashlib.sha256(RECEIPT.read_bytes()).hexdigest()


def test_the_frame_build_is_listed_as_a_run_before_v1b_is_in_force() -> None:
    _frame_raw, _routing_raw, receipt, protocol = _committed()
    runs = {run["receipt"]: run for run in protocol["blinding"]["runs_before_v1b_is_in_force"]}
    run = runs[RECEIPT.relative_to(ROOT).as_posix()]
    assert run["generated_at_utc"] == receipt["generated_at_utc"]
    assert receipt["official_warning"] is False and receipt["confidence_class"] == "low"
    assert receipt["source_timestamp"] and receipt["assumptions"]
    assert "R12" in receipt["decision"]["decision_log_entry"]
