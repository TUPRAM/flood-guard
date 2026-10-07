"""The planning assessment builder (plan task E8), run end to end on an invented frame.

Everything the builder reads here is invented and written into a temporary folder by this file: two units in the
open sea, a road graph of eight nodes, five demand cells, a flood polygon, a water polygon, a footprint, an age
table, and the receipts and register entries that bind them. The access table is made by the unchanged task E5
runner from the same invented graph. No layer or table of a real case is read and no component of a real unit is
computed. What is real is what every run reads unchanged: the two signed protocol files and the national-anchor
receipt protocol v1b names (constants for all of Thailand). One test reads two more committed files, the E1 and
E5 receipts of the Mae Sai frame, for what they bind for case O1 (nothing): the refusal of that case is worded
from them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import pytest
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

from floodguard import access_diff, flood_inputs, planning_assessment, rights
from floodguard.evidence_context import _context_content_hash
from floodguard.normalisation import NormalisationError
from floodguard.planning_overlay import SCHEMA_RELATIVE_PATH, load_overlay, load_overlay_schema

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
V1B = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
HASHES = {f"planning_protocol_{name}": hashlib.sha256((DOCS / f"planning_protocol_{name}.json").read_bytes()).hexdigest()
          for name in ("v1a", "v1b")}
TO_WGS84 = Transformer.from_crs(32647, 4326, always_xy=True).transform
# An invented origin in the open sea (about 97.2 E, 7.2 N): the units below are not a place.
ORIGIN_X, ORIGIN_Y = 300_000.0, 800_000.0
P10, P90 = 0.351416, 0.477677


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("build_planning_assessment", ROOT / "scripts" / "build_planning_assessment.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()
e5 = runner.e5_builder

CASE = "FX-E8"
UNIT_IDS = ("FX-E8-U1", "FX-E8-U2")
INPUT_ID = "fx_agency:INVENTED_LAYER"
FLOOD_NAME = "Fixture agency extent (invented, not a product)"
ATTRIBUTION = "FloodGuard fixture (invented, not a source)"
LICENCE = "none: invented fixture input"
PROCESSED = "proposal_execution/planning_v1"
LABEL = "<external_data_workspace>"


def metres(geometry: Any) -> Any:
    """Shift a geometry given in metres from the invented origin into EPSG:32647."""

    return transform(lambda x, y: (x + ORIGIN_X, y + ORIGIN_Y), geometry)


def lonlat(x_m: float, y_m: float) -> list[float]:
    longitude, latitude = TO_WGS84(ORIGIN_X + x_m, ORIGIN_Y + y_m)
    return [longitude, latitude]


def wgs84(geometry: Any) -> Any:
    return transform(lambda x, y: TO_WGS84(x + ORIGIN_X, y + ORIGIN_Y), geometry)


NODES = {"h": (-200.0, 0.0), "m0": (0.0, 0.0), "m1": (200.0, 0.0), "r1": (200.0, 200.0), "r2": (200.0, 400.0),
         "r2b": (200.0, 400.0), "r3": (200.0, 600.0), "q": (400.0, 200.0)}
STREETS = [  # edge, from, to, road class, vehicle speed km/h; every edge is 200 m long
    ("s-h", "h", "m0", "secondary", 50.0), ("p0", "m0", "m1", "primary", 60.0), ("r-a", "m1", "r1", "residential", 25.0),
    ("r-b", "r1", "r2", "residential", 25.0), ("r-c", "r2b", "r3", "residential", 25.0), ("r-q", "r1", "q", "residential", 25.0),
]
CELL_SITES = {"c1": ("r1", (200.0, 200.0)), "c2": ("r2", (200.0, 400.0)), "c3": ("r3", (200.0, 600.0)),
              "c4": ("q", (400.0, 200.0)), "c5": (None, (900.0, 100.0))}
# Unit 1 holds c1, c4 and c5; unit 2 holds c2 and c3. With these residents unit 2 is under 100 residents.
RESIDENTS = {"c1": 400.0, "c2": 20.0, "c3": 30.0, "c4": 4600.0, "c5": 500.0}
UNIT_BOXES = {"FX-E8-U1": box(-500.0, -500.0, 1500.0, 300.0), "FX-E8-U2": box(-500.0, 300.0, 1500.0, 1500.0)}
# The flood holds the centres of c1 and c2 at all three levels, and half of each residential edge around r1.
FLOOD = box(100.0, 100.0, 300.0, 500.0)
WATER = box(250.0, 100.0, 300.0, 150.0)       # 2,500 m2 of permanent water inside the flood, in unit 1
FOOTPRINT = box(-1000.0, -1000.0, 2000.0, 2000.0)
AGES = {"FX-E8-U1": (900.0, 1250.0, 5000.0), "FX-E8-U2": (10.0, 12.0, 60.0)}   # children 0-14, 60 and over, all residents


def invented_context(residents: dict[str, float]) -> dict[str, Any]:
    """A vehicle planning context of eight nodes, as ``build_context_inputs`` would write its parts."""

    edges = [{"edge_id": edge_id, "from_node": start, "to_node": end, "length_m": 200.0, "road_class": road_class,
              "normal_minutes": 200.0 / 1000 / speed * 60, "osm_way_id": edge_id, "bridge": "no", "layer": "0", "tunnel": "no",
              "travel_mode": "legacy_vehicle"} for edge_id, start, end, road_class, speed in STREETS]
    population = [{"population_id": identifier, "subdistrict_id": "aoi-demand-not-administrative-unit",
                   "total_population": residents[identifier], "node_id": node, "snap_distance_m": None if node is None else 0.0,
                   "longitude": lonlat(*centre)[0], "latitude": lonlat(*centre)[1]}
                  for identifier, (node, centre) in CELL_SITES.items()]
    context = {
        "travel_mode": "legacy_vehicle", "edges": edges, "generated_at": "2030-01-02T00:00:00+00:00",
        "node_coordinates": {node: lonlat(*position) for node, position in NODES.items()},
        "population": population,
        "osm_facilities": [{"facility_id": "OSM-way-1", "service_type": "hospital", "candidate_destination_eligible": True,
                            "within_routing_context": True, "node_id": "h", "snap_distance_m": 0.0, "name": "an invented hospital"}],
        "facilities": [],
        "connectivity_review": {"review_candidates": [{
            "coordinates": lonlat(200.0, 400.0),
            "nodes": [{"node_id": "r2", "grade": ["0", "no", "no"], "way_ids": ["r-b"], "endpoint_way_ids": ["r-b"]},
                      {"node_id": "r2b", "grade": ["1", "yes", "no"], "way_ids": ["r-c"], "endpoint_way_ids": ["r-c"]}]}]},
    }
    context["canonical_sha256"] = _context_content_hash(context)
    return context


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def register(world: dict[str, Any], name: str) -> None:
    """Write the run-register entry of a file of the invented planning output folder."""

    path = world["output_dir"] / name
    entry = {"path": f"outputs/planning_v1/{name}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    _write(world["register_dir"] / name, _json(entry))


def _layer(geometry: Any, what: str, level: str | None, frame: str) -> bytes:
    properties = {
        "what": what, "case_id": CASE, "input_id": INPUT_ID, "input_name": FLOOD_NAME, "level": level, "frame": frame,
        "source_timestamp": "2030-01-11", "confidence_class": "low", "confidence_basis": "An invented layer of a fixture.",
        "assumptions": ["Invented: this layer describes no place."], "official_warning": False,
        "operational_status": "non_operational", "licence": {"name": LICENCE}, "credit": ATTRIBUTION, "rights_level": "local",
        "change_notice": "An invented layer of a fixture: nothing was changed, because nothing was provided.",
    }
    return flood_inputs.encode_layer(metres(geometry), properties, f"{what}__{level}__{frame}")


def write_access_table(world: dict[str, Any], table: dict[str, Any]) -> None:
    """Write the invented access table and the invented E5 receipt that binds it, and register both."""

    sha256 = _write(world["output_dir"] / "fx_access_table.json", _json(table))
    receipt = {"generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": HASHES, "outputs": {CASE: {"files": [{
        "path": "outputs/planning_v1/fx_access_table.json", "sha256": sha256, "what": "unit_table",
        "service_set": "public_services", "publication_level": "local", "in_git": True}]}}}
    _write(world["output_dir"] / "fx_e5_receipt.json", _json(receipt))
    register(world, "fx_access_table.json")
    register(world, "fx_e5_receipt.json")


def build_world(tmp_path: Path, residents: dict[str, float] | None = None) -> dict[str, Any]:
    """Write an invented frame with everything the builder reads, and return where it is."""

    residents = dict(residents or RESIDENTS)
    root, external = tmp_path / "repo", tmp_path / "external"
    world: dict[str, Any] = {"root": root, "external": external, "output_dir": root / "outputs" / "planning_v1",
                             "register_dir": root / "outputs" / "planning_v1" / "run_register"}
    processed = external / PROCESSED
    # The units and their names.
    features = [{"type": "Feature", "geometry": mapping(wgs84(UNIT_BOXES[unit_id])),
                 "properties": {"unit_id": unit_id, "name_en": f"Invented unit {number} (fixture, not a place)",
                                "name_th": f"หน่วยทดสอบ {number} (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)", "name_th_language": "th"}}
                for number, unit_id in enumerate(UNIT_IDS, start=1)]
    world["boundaries"] = tmp_path / "fx_units.geojson"
    boundary_sha256 = _write(world["boundaries"], json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8"))
    # The rights record of the invented flood input, and the registry that knows it.
    record = {"schema": "floodguard.fixture_rights.v1", "record_id": "fx_rights_v1", "signed_by_human": True,
              "human_rights_clearance": True, "record_status": "confirmed",
              "owner_confirmation": {"status": "confirmed", "confirmed_by": ["an invented owner"], "confirmed_on": "2030-01-01"},
              "required_attribution_text": ATTRIBUTION, "official_warning": False, "can_feed_decision_layer": False,
              "licence": {"name": LICENCE}}
    world["rights_record"] = root / "rights" / "fx_rights.json"
    rights_sha256 = _write(world["rights_record"], _json(record))
    world["registry"] = rights.RightsRegistry(root, records=(
        rights.RegisteredRecord("fx_agency", "rights/fx_rights.json", "an invented layer of a fixture", "fixture_invented_source"),))
    # The planning context and its receipt.
    context = invented_context(residents)
    context_label = f"{LABEL}/{PROCESSED}/fx_case/e4_vehicle/context_inputs.json"
    _write(processed / "fx_case" / "e4_vehicle" / "context_inputs.json", json.dumps(context).encode("utf-8"))
    _write(world["output_dir"] / "fx_context_receipt.json", _json({
        "generated_at_utc": "2030-01-02T00:00:00Z", "run_kind": "build_of_record",
        "context": {"path": context_label, "canonical_sha256": context["canonical_sha256"]},
        "input_hashes": {"worldpop_2020_sha256": "9" * 64}, "source_timestamps": {"osm_retrieved_at_utc": "2030-01-01T00:00:00Z"}}))
    register(world, "fx_context_receipt.json")
    # The flood input as task E1 writes it: three levels in two frames, a footprint, the record, and the water of the frame.
    folder = processed / "fx_case" / "e1_flood_input"
    prefix = f"{LABEL}/{PROCESSED}/fx_case/e1_flood_input/"
    files, bound = [], []
    levels = {level: transform(lambda x, y: (x - ORIGIN_X, y - ORIGIN_Y), geometry)
              for level, geometry in flood_inputs.one_pixel_levels(metres(FLOOD), 20.0).items()}
    for level in flood_inputs.LEVELS:
        for frame in (flood_inputs.REPORTING_FRAME, flood_inputs.ROUTING_CONTEXT):
            name = f"flood_extent__{level}__{frame}.geojson"
            data = _layer(levels[level], "flood_extent", level, frame)
            files.append({"file": name, "sha256": _write(folder / name, data), "bytes": len(data), "what": "flood_extent",
                          "level": level, "frame": frame, "rights_level": "local"})
    name = f"product_footprint__{flood_inputs.REPORTING_FRAME}.geojson"
    data = _layer(FOOTPRINT, "product_footprint", None, flood_inputs.REPORTING_FRAME)
    files.append({"file": name, "sha256": _write(folder / name, data), "bytes": len(data), "what": "product_footprint",
                  "frame": flood_inputs.REPORTING_FRAME, "rights_level": "local"})
    flood_record = {
        "schema_version": flood_inputs.INPUT_RECORD_SCHEMA, "case_id": CASE, "input_id": INPUT_ID, "input_name": FLOOD_NAME,
        "lane": "OBS", "tier": "T3", "temporal_relation": "event_aligned", "case_reference_date": "2030-01-10",
        "acquisition_date": "2030-01-11", "season_window": None, "source_timestamp": "2030-01-11", "label": None,
        "field_validation": None, "source": {"layer": "INVENTED_LAYER"}, "levels": {"one_pixel_m": 20.0},
        "rights": {"licence": {"name": LICENCE, "full_name": LICENCE, "spdx_id": "none", "url": "none", "legal_code_url": "none"},
                   "attribution": ATTRIBUTION, "share_alike": None, "record_path": "rights/fx_rights.json",
                   "record_sha256": rights_sha256, "record_status": "confirmed", "confirmed_by": ["an invented owner"],
                   "confirmed_on": "2030-01-01", "rights_level": "local", "rights_level_basis": "an invented basis"},
        "protocol_sha256": HASHES, "files": files,
    }
    record_sha256 = _write(folder / flood_inputs.INPUT_RECORD_NAME, json.dumps(flood_record, indent=2).encode("ascii"))
    bound = [{"path": prefix + entry["file"], "sha256": entry["sha256"]} for entry in files]
    bound.append({"path": prefix + flood_inputs.INPUT_RECORD_NAME, "sha256": record_sha256})
    water_name = "permanent_water__reporting_frame.geojson"
    water_data = flood_inputs.encode_layer(metres(WATER), {
        "what": "permanent_water", "frame": flood_inputs.REPORTING_FRAME, "source_timestamp": "2029-01-01/2029-12-31",
        "confidence_class": "low", "confidence_basis": "An invented layer of a fixture.", "assumptions": ["Invented."],
        "official_warning": False, "operational_status": "non_operational",
        "change_notice": "An invented water layer of a fixture."}, "permanent_water__reporting_frame")
    water_sha256 = _write(processed / "fx_frame" / "e1_flood_input" / water_name, water_data)
    _write(world["output_dir"] / "fx_e1_receipt.json", _json({
        "generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": HASHES,
        "inputs": {"tambon_boundaries": {"sha256": boundary_sha256}},
        "outputs": {"frame": {"files": [{"path": f"{LABEL}/{PROCESSED}/fx_frame/e1_flood_input/{water_name}", "sha256": water_sha256}]},
                    CASE: {"files": bound}}}))
    register(world, "fx_e1_receipt.json")
    world["flood_folder"] = folder
    world["water_file"] = processed / "fx_frame" / "e1_flood_input" / water_name
    # The access table, made by the unchanged task E5 runner from the invented graph and the invented flood.
    graph = e5.mode_graph("vehicle", context)
    services = access_diff.service_rules(V1A, V1B)
    units = [(unit_id, wgs84(UNIT_BOXES[unit_id])) for unit_id in UNIT_IDS]
    cells = access_diff.demand_cells(graph.population, access_diff.assign_cells(graph.population, units))
    arguments = access_diff.closure_arguments(V1B)
    computed = e5.case_runs(CASE, INPUT_ID, {"as_provided": metres(FLOOD)}, {"vehicle": graph},
                            {"vehicle": e5.baseline_runs(graph, services)}, services, arguments, cells, list(UNIT_IDS))
    vehicle = {"status": "of_record", "run_kind": "build_of_record", "path": context_label,
               "canonical_sha256": context["canonical_sha256"], "osm_retrieved_at_utc": "2030-01-01T00:00:00Z"}
    closure_extent = next(entry for entry in files if entry["level"] == "as_provided" and entry["frame"] == flood_inputs.ROUTING_CONTEXT)
    table = e5.table_document(
        CASE, "public_services", "local", generated_at_utc="2030-01-03T00:00:00Z",
        receipt_label="outputs/planning_v1/fx_e5_receipt.json", record=flood_record,
        rules=flood_inputs.rules_from_protocols(V1A, V1B), hashes=HASHES, services=services, runs=computed["runs"],
        contexts={"vehicle": vehicle}, vehicle_context=vehicle,
        flood_files={"as_provided": {"path": prefix + closure_extent["file"], "sha256": closure_extent["sha256"]}},
        units={"valid_on": ["2030-01-01"]}, unit_ids=list(UNIT_IDS), arguments=arguments, notice_label="none")
    # The runner words its licence block for product 4009; an invented table states an invented one.
    table["case_frame"] = "fx_frame"
    table["licence"] = {"name": LICENCE, "credit": ATTRIBUTION, "change_notice": "An invented table of a fixture."}
    world["access_table"] = table
    write_access_table(world, table)
    # The age table and its receipt.
    age_table = {"schema_version": "floodguard.age_exposure.v1", "generated_at_utc": "2030-01-03T00:00:00Z",
                 "source_timestamp": "2029-09-01", "protocol_sha256": HASHES,
                 "units": [{"unit_id": unit_id, "children_0_14": children, "older_60_plus": older, "residents": total,
                            "dependent_share": 0.99, "dependent_share_unavailable_reason": None}
                           for unit_id, (children, older, total) in AGES.items()]}
    age_sha256 = _write(world["output_dir"] / "fx_age_table.json", _json(age_table))
    _write(world["output_dir"] / "fx_e7_receipt.json", _json({
        "generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": HASHES,
        "outputs": [{"path": "outputs/planning_v1/fx_age_table.json", "sha256": age_sha256}]}))
    register(world, "fx_age_table.json")
    register(world, "fx_e7_receipt.json")
    # The national-anchor receipt protocol v1b names: constants for all of Thailand, the same in every run.
    shutil.copy(ROOT / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json", world["output_dir"])

    def text(name: str, level: str = "public") -> Any:
        return runner.LineageText(f"Fixture {name} (invented)", LICENCE, ATTRIBUTION, level, "An invented level of a fixture.")

    world["frame_set"] = runner.FrameSet(
        name="fx_frame", title="an invented frame (fixture, not a place)", kind="fixture",
        case_folders={CASE: "fx_case"}, frame_folder="fx_frame", e1_receipt="fx_e1_receipt.json",
        e5_receipt="fx_e5_receipt.json", e7_receipt="fx_e7_receipt.json", context_binding=runner.CONTEXT_BY_REGISTER,
        context_receipt="fx_context_receipt.json",
        lineage={key: text(key.replace("_", " ")) for key in ("routing_context", "population", "boundaries", "permanent_water",
                                                              "age_structure", "national_anchors")},
        case_titles={}, rights_input={CASE: "fx_agency"}, unit_ids=UNIT_IDS, boundary_layer=None, unit_id_field="unit_id",
        unit_name_en_field="name_en", unit_name_th_field="name_th", unit_name_th_language_field="name_th_language",
        fixture_cases={CASE: planning_assessment.CaseSpec(
            case_id=CASE, kind="fixture", title_en="Invented case (fixture, not a place)",
            title_th="กรณีทดสอบ (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)", frame="Two invented units in the open sea (fixture, not a place)",
            case_reference_date=__import__("datetime").date(2030, 1, 10), lane="OBS", tier="T3",
            fixture_notice="Fixture, not a place: every unit, input, count and date of this file is invented.")},
        not_run={"FX-O1": runner.AwaitedCase(rights_source="fixture_radar_source", rights_source_text="invented radar data",
                                             open_point="FX-OP1", not_built="this builder does not read an invented radar case")})
    return world


def run(world: dict[str, Any], **changes: Any) -> dict[str, Any]:
    arguments = dict(root=world["root"], output_dir=world["output_dir"], register_dir=world["register_dir"],
                     registry=world["registry"], git_commit="0123abc")
    arguments.update(changes)
    return runner.run(CASE, world["frame_set"], world["external"], world["boundaries"], **arguments)


def nothing_was_written(world: dict[str, Any]) -> bool:
    receipt = runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"])
    stage = world["external"] / PROCESSED / "fx_case" / runner.STAGE_FOLDER
    return not receipt.exists() and not stage.exists() and not (world["register_dir"] / receipt.name).exists()


# ---------------------------------------------------------------------------
# End to end on the invented frame
# ---------------------------------------------------------------------------


def test_a_run_on_an_invented_frame_writes_an_overlay_the_validator_accepts(tmp_path: Path) -> None:
    world = build_world(tmp_path)
    summary = run(world)
    assert summary["overlay_written"] is True and summary["not_written_because"] is None
    # The lineage is below the public level (an invented local layer), so the overlay stays outside the repository.
    assert summary["publication_eligibility"] == "local" and summary["overlay_in_git"] is False
    overlay_path = world["external"] / PROCESSED / "fx_case" / runner.STAGE_FOLDER / "planning_assessment_overlay_fx-e8_fx_frame.json"
    assert summary["overlay"] == f"{LABEL}/{PROCESSED}/fx_case/{runner.STAGE_FOLDER}/{overlay_path.name}"
    raw = overlay_path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    rules = planning_assessment.load_assessment_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json",
                                                      DOCS / "RECEIPTS.jsonl")
    overlay = load_overlay(overlay_path, load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH), binding=rules.binding)
    assert overlay["dataset_mode"] == "fixture_demo" and overlay["case"]["case_id"] == CASE
    assert overlay["official_warning"] is False and overlay["operational_status"] == "non_operational"
    assert overlay["protocol_sha256"] == {"v1a": HASHES["planning_protocol_v1a"], "v1b": HASHES["planning_protocol_v1b"]}
    assert overlay["generated_at"] == summary["generated_at_utc"] and overlay["source_timestamp"] == "2030-01-11T00:00:00Z"
    flood_input = overlay["inputs"][0]
    assert flood_input["input_id"] == "fx_agency.invented_layer" and flood_input["name"] == FLOOD_NAME
    assert not list((tmp_path).rglob("apps")), "nothing is written under apps/web"

    first, second = overlay["rows"]
    # Unit 1 by hand. Flood likelihood: 200 m x 200 m of flood in the unit, less 2,500 m2 of permanent water, over
    # the unit's 2,000 m x 800 m less the same water, against the anchor 0.20.
    components = first["components"]
    assert components["flood_likelihood_0_100"]["value_0_100"] == pytest.approx(100 * (37_500 / 1_597_500) / 0.20, rel=1e-4)
    # Exposure: the 400 residents of cell c1 are inside the extent, of 5,500 in the unit (c1, c4 and the unconnected c5).
    assert components["exposure_0_100"]["inputs"] == {"residents_inside_flood_extent": 400.0, "unit_residents": 5500.0}
    assert components["exposure_0_100"]["value_0_100"] == pytest.approx(100 * 400 / 5500)
    # Access: the flood closes every residential edge at r1 (half of each lies inside), so the 5,000 connected
    # residents lose the hospital, the main-road entry and every route. The counts are those of the access table.
    assert components["access_gap_0_100"]["inputs"]["services"] == {
        "hospital": {"mode": "vehicle", "threshold_minutes": 30, "baseline_access_residents": 5000.0, "newly_lost_residents": 5000.0},
        "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15, "baseline_access_residents": 5000.0, "newly_lost_residents": 5000.0}}
    assert components["access_gap_0_100"]["value_0_100"] == 100.0 and components["access_gap_0_100"]["publication_level"] == "public"
    assert components["road_criticality_0_100"]["inputs"] == {"residents_losing_all_routes": 5000.0, "residents_with_baseline_route": 5000.0}
    # Vulnerability: (900 + 1,250) / 5,000 = 0.43 between the national P10 and P90; the share the table states (0.99) is not read.
    assert components["vulnerability_context_0_100"]["dependent_share"] == pytest.approx(0.43)
    assert components["vulnerability_context_0_100"]["value_0_100"] == pytest.approx(100 * (0.43 - P10) / (P90 - P10))
    by_hand = 0.30 * 100 * (37_500 / 1_597_500) / 0.20 + 0.25 * 100 * 400 / 5500 + 0.20 * 100 + 0.15 * 100 + 0.10 * 100 * (0.43 - P10) / (P90 - P10)
    assert first["fpps_0_100"] == pytest.approx(round(by_hand, 2)) == 46.56
    measurements = first["confidence"]["measurements"]
    assert first["confidence"]["confidence_class"] == "medium" and first["confidence"]["failed_conditions"] == []
    assert measurements["unit_valid_coverage"] == 1.0 and measurements["coverage_by_construction"] is False
    assert measurements["exposure_plus_minus_one_pixel_points"] == 0.0, "c1 is inside the extent at the minus and the plus level"
    assert measurements["baseline_vehicle_no_route_share"] == 0.0 and measurements["hospitals_reachable_at_baseline"] == 1
    # Class rule v1 is binding: road criticality 100 and access gap 100 give B. v2 is E, because the exposure is under 10.
    assert (first["action_class"], first["action_reason_code"], first["would_be_class"]) == ("B", "critical_route_access", None)
    assert first["class_v2"]["result"] == "E" and first["class_v2"]["binding"] is False and first["class_v2"]["label"] == "secondary"
    assert first["temporal_relation"] == "event_aligned" and first["lineage"]["closure_rule"] == {
        "version": "closure_rule_v1", "level": "central", "closure_basis": "modelled_from_fx_agency.invented_layer"}
    assert first["headline_stability"]["status"] == "not_evaluated"
    # Unit 2 has 50 residents: guardrail GR1, no class.
    assert second["components"]["exposure_0_100"]["inputs"] == {"residents_inside_flood_extent": 20.0, "unit_residents": 50.0}
    assert second["components"]["flood_likelihood_0_100"]["value_0_100"] == pytest.approx(100 * (40_000 / 2_400_000) / 0.20, rel=1e-4)
    assert (second["action_class"], second["action_reason_code"], second["would_be_class"]) == (None, "insufficient_denominator", None)
    assert second["class_v2"]["result"] is None and second["confidence"]["guardrail_gr1"]["applies"] is True

    # The receipt reports the run, binds the overlay and its inputs by SHA-256, and is registered with one small file.
    receipt_path = runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"])
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    entry = json.loads((world["register_dir"] / receipt_path.name).read_text(encoding="ascii"))
    assert entry == {"path": f"outputs/planning_v1/{receipt_path.name}", "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    assert receipt["protocol_sha256"] == HASHES and receipt["run_kind"] == "first_run" and receipt["status"] == "run_receipt"
    assert receipt["confidence_class"] == "low" and receipt["official_warning"] is False and receipt["assumptions"]
    assert receipt["generated_at_utc"] == summary["generated_at_utc"] and receipt["source_timestamp"] == "2030-01-11"
    bound = runner.bound_outputs(receipt["outputs"])
    assert bound == {summary["overlay"]: hashlib.sha256(raw).hexdigest()}
    assert receipt["rights"]["publication_eligibility"] == "local" and receipt["rights"]["written_under_apps_web_public"] is False
    assert receipt["lane_purity"]["result"] == "PASS" and set(receipt["lane_purity"]["compared"]) == {
        "flood_input_id", "flood_input_name", "closure_extent_sha256", "routing_context_canonical_sha256", "closure_basis",
        "closure_rule_version", "case_lane"}
    assert all(entry["result"] == "PASS" for entry in receipt["guardrails"].values())
    assert receipt["result"]["summary"]["row_count"] == 2 and receipt["result"]["summary"]["rows_under_gr1"] == 1
    assert receipt["result"]["rows_as_computed"] is None, "the overlay holds every row, so nothing is reported beside it"
    # Checks over the whole case: bounds, the weighted sum, leave-one-out, and the residents of the access table.
    whole = receipt["whole_case_checks"]
    assert whole["result"] == "PASS" and whole["rows"] == 2 and whole["component_values"] == 10
    assert whole["leave_one_component_out_consistent_with_the_fpps"] is True and whole["rows_with_leave_one_component_out"] == 2
    assert whole["residents_of_the_rows"] == whole["residents_counted_by_the_access_table"] == 5550.0
    assert whole["residents_same_as_the_access_table"] is True
    assert receipt["result"]["summary"]["binding_class_by_lane_column"]["OBS"]["B"] == 1
    assert receipt["parameters"]["closure_rule"]["level"] == "central" and receipt["parameters"]["services"] == ["hospital", "main_road_entry"]
    assert {point["id"] for point in receipt["open_points"]} >= {"E8-OP1", "E8-OP5"}
    assert "FX-E8-U1" not in json.dumps(receipt["result"]["summary"]), "the receipt holds counts for the case, not a unit's values"
    inputs = receipt["inputs"]
    assert inputs["access_table"]["table"]["sha256"] == hashlib.sha256((world["output_dir"] / "fx_access_table.json").read_bytes()).hexdigest()
    assert inputs["flood_input"]["extents_reporting_frame"]["as_provided"]["sha256"] == flood_input["sha256"]

    # The input check reads the same inputs, measures no unit and writes nothing.
    before = sorted(str(path) for path in tmp_path.rglob("*"))
    checked_inputs = runner.check_inputs(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                                         output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert checked_inputs["inputs_checked"] is True and checked_inputs["lane_purity"] == "PASS"
    assert checked_inputs["unit_residents_same_in_the_context_and_the_access_table"] is True
    assert checked_inputs["no_unit_row_of_the_access_table_stores_a_ratio"] is True
    assert checked_inputs["licence_block"] is False, "the invented flood input is not product 4009"
    assert checked_inputs["publication_eligibility"] == "local" and checked_inputs["overlay_would_go_to"] == summary["overlay"]
    assert checked_inputs["lineage"]["fx_agency.invented_layer"]["sha256"] == flood_input["sha256"]
    assert sorted(str(path) for path in tmp_path.rglob("*")) == before

    # --verify computes the overlay again, finds the same bytes and runs the verifier on the file.
    checked = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                            output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert checked["verified"] is True and checked["verifier"] == {"verified": True, "problems": []}
    assert checked["receipt_body_same"] is True and checked["receipt_fields_that_differ"] == []
    assert checked["outputs_block_same"] is True and checked["code_changed_since_the_run"] == []
    overlay_path.write_bytes(raw.replace(b'"action_class": "B"', b'"action_class": "A"', 1))
    changed = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                            output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert changed["verified"] is False and changed["overlay_on_disk_same"] is False
    overlay_path.write_bytes(raw)

    # The receipt carries the SHA-256 of the rows alone and the hashes of its lineage, and names the counts that
    # cover every row: such a count is a statement about each unit.
    assert receipt["result"]["rows_sha256"] == runner.rows_sha256(overlay["rows"]) and len(receipt["result"]["rows_sha256"]) == 64
    assert receipt["lineage_input_sha256"] == {item["input_id"]: item["sha256"] for item in overlay["inputs"]}
    declared = receipt["rights"]["figures_of_local_level_layers_in_this_receipt"]
    assert declared["counts_that_cover_every_row"] == runner.counts_that_cover_every_row(receipt["result"]["summary"])
    assert "headline_status_by_lane_column.OBS.not_evaluated" in declared["counts_that_cover_every_row"]
    assert "binding_class_by_lane_column.OBS.B" not in declared["counts_that_cover_every_row"], "one row of two is B"
    assert "states that value for each unit" in declared["what_the_counts_give_away"]
    assert receipt["licence"] is None, "an invented flood input has no product licence block"
    assert "In plan task E8" in flood_input["change_notice"] and "not the layer" in flood_input["change_notice"]

    # --verify compares the whole receipt, not only its result block: a body the code would not write does not verify.
    kept = receipt_path.read_bytes()
    edited = json.loads(kept)
    edited["rights"]["rule"] = "another sentence"
    edited["parameters"]["tolerances"]["residents_between_two_stages"] = 1.0
    receipt_path.write_bytes(runner.encode(edited))
    other = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                          output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert other["verified"] is False and other["receipt_result_same"] is True and other["overlay_bytes_same_as_recomputed"] is True
    assert other["receipt_body_same"] is False and other["receipt_fields_that_differ"] == ["parameters", "rights"]
    # A receipt written by other code says so, and still verifies when the code of today writes the same body.
    edited = json.loads(kept)
    edited["implementation"]["builder_sha256"] = "0" * 64
    receipt_path.write_bytes(runner.encode(edited))
    older = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                          output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert older["verified"] is True and older["code_changed_since_the_run"] == ["builder_sha256"]
    receipt_path.write_bytes(kept)


def test_a_second_run_needs_a_reason_and_names_the_run_it_replaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = build_world(tmp_path)
    # The two runs are minutes apart, so their overlays differ in their generation time and in nothing else.
    clock = iter(f"2030-02-01T00:{minute:02d}:00Z" for minute in range(60))
    monkeypatch.setattr(e5, "utc_now", lambda: next(clock))
    first = run(world)
    with pytest.raises(FileExistsError, match="--replace --reason"):
        run(world)
    second = run(world, replace_reason="an invented reason to run again")
    receipt = json.loads(runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).read_text(encoding="ascii"))
    assert receipt["run_kind"] == "superseding_run" and receipt["supersedes"]["receipt_sha256"] == first["receipt_sha256"]
    assert receipt["supersedes"]["reason"] == "an invented reason to run again" and receipt["supersedes"]["result_same"] is True
    assert [entry["receipt_sha256"] for entry in receipt["run_history"]] == [first["receipt_sha256"]]
    assert second["receipt_sha256"] != first["receipt_sha256"] and second["generated_at_utc"] != first["generated_at_utc"]
    assert receipt["run_history"][0]["result_same_as_the_run_that_replaced_it"] is True
    # The rows of the replaced run were read back from the file its receipt bound: the same rows, value by value.
    supersedes = receipt["supersedes"]
    assert supersedes["counts_same"] is True and supersedes["rows_same"] is True and supersedes["lineage_inputs_same"] is True
    assert supersedes["rows_sha256_of_the_superseded_run"] == supersedes["rows_sha256_of_this_run"] == receipt["result"]["rows_sha256"]
    assert "read back with the SHA-256 that receipt names" in supersedes["rows_of_the_superseded_run_read_from"]
    assert receipt["run_history"][0]["rows_sha256"] == receipt["result"]["rows_sha256"]
    # The replaced receipt and the overlay it bound are kept outside the repository, under the time of that run.
    archive = world["external"] / PROCESSED / "fx_case" / runner.STAGE_FOLDER / runner.SUPERSEDED_FOLDER / "20300201T000000Z"
    kept = {item["what"]: item for item in supersedes["copies_kept_outside_git"]}
    assert set(kept) == {"receipt", "file the receipt bound"} and all(item["path"].startswith(LABEL + "/") for item in kept.values())
    kept_receipt = archive / runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).name
    assert hashlib.sha256(kept_receipt.read_bytes()).hexdigest() == first["receipt_sha256"] == kept["receipt"]["sha256"]
    kept_overlay = archive / "planning_assessment_overlay_fx-e8_fx_frame.json"
    assert hashlib.sha256(kept_overlay.read_bytes()).hexdigest() == kept["file the receipt bound"]["sha256"]
    assert json.loads(kept_overlay.read_text(encoding="ascii"))["generated_at"] == first["generated_at_utc"]
    # The comparison of the counts leaves out the content hash of the overlay and the rows digest, and nothing
    # else: another row count is a difference.
    block = receipt["result"]
    other = json.loads(json.dumps(block))
    other["summary"]["content_sha256"] = "0" * 64
    other["rows_sha256"] = "1" * 64
    assert runner.result_without_the_run_time(other) == runner.result_without_the_run_time(block)
    other["summary"]["row_count"] += 1
    assert runner.result_without_the_run_time(other) != runner.result_without_the_run_time(block)
    assert runner.result_without_the_run_time(None) == {}
    with pytest.raises(FileNotFoundError, match="existing receipt"):
        run(build_world(tmp_path / "other"), replace_reason="nothing to replace")


def test_a_second_run_with_another_value_and_the_same_class_counts_is_not_the_same_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The counts of the whole case cannot show that no value of a unit changed; the SHA-256 of the rows can."""

    world = build_world(tmp_path)
    clock = iter(f"2030-02-01T00:{minute:02d}:00Z" for minute in range(60))
    monkeypatch.setattr(e5, "utc_now", lambda: next(clock))
    first = run(world)
    before = json.loads(runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).read_text(encoding="ascii"))
    # Ten more children in unit 1 of the invented age table: its vulnerability and its FPPS move, its class does not.
    age_path = world["output_dir"] / "fx_age_table.json"
    age_table = json.loads(age_path.read_text(encoding="ascii"))
    age_table["units"][0]["children_0_14"] += 10.0
    age_sha256 = _write(age_path, _json(age_table))
    _write(world["output_dir"] / "fx_e7_receipt.json", _json({
        "generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": HASHES,
        "outputs": [{"path": "outputs/planning_v1/fx_age_table.json", "sha256": age_sha256}]}))
    register(world, "fx_age_table.json")
    register(world, "fx_e7_receipt.json")
    run(world, replace_reason="an invented age count changed")
    receipt = json.loads(runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).read_text(encoding="ascii"))
    supersedes = receipt["supersedes"]
    assert supersedes["receipt_sha256"] == first["receipt_sha256"]
    assert supersedes["counts_same"] is True, "the same rows by class, reason code and confidence class"
    assert supersedes["rows_same"] is False and supersedes["result_same"] is False
    assert supersedes["rows_sha256_of_the_superseded_run"] == before["result"]["rows_sha256"] != receipt["result"]["rows_sha256"]
    assert supersedes["lineage_inputs_same"] is False and supersedes["lineage_inputs_that_differ"] == ["e7_age_exposure_table"]
    assert receipt["run_history"][0]["result_same_as_the_run_that_replaced_it"] is False


def test_a_run_whose_v2_result_nobody_can_state_writes_an_overlay_that_says_not_evaluated(tmp_path: Path) -> None:
    """With 1,000 residents in cell c1 the exposure of unit 1 is above 10, so v2 trigger E is not met and B decides.

    Nobody evaluated trigger B. Since overlay schema 1.1 (decision log R20) the overlay is written, and the v2 axis
    of that row says ``not_evaluated``; before, the run wrote no overlay and reported its rows beside the reason.
    """

    world = build_world(tmp_path, {**RESIDENTS, "c1": 1000.0})
    summary = run(world)
    assert summary["overlay_written"] is True and summary["not_written_because"] is None
    assert summary["rows_reported_as_computed"] is False
    overlay_path = world["external"] / PROCESSED / "fx_case" / runner.STAGE_FOLDER / "planning_assessment_overlay_fx-e8_fx_frame.json"
    rules = planning_assessment.load_assessment_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json",
                                                      DOCS / "RECEIPTS.jsonl")
    overlay = load_overlay(overlay_path, load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH), binding=rules.binding)
    assert overlay["schema_version"] == "1.1" and overlay["official_warning"] is False
    first, second = overlay["rows"]
    # Unit 1: 1,000 of 6,100 residents inside the extent, every connected resident cut off; class rule v1 gives B.
    assert first["components"]["exposure_0_100"]["value_0_100"] == pytest.approx(100 * 1000 / 6100)
    assert (first["action_class"], first["action_reason_code"], first["would_be_class"]) == ("B", "critical_route_access", None)
    assert first["fpps_0_100"] is not None and set(first["leave_one_component_out"]) == set(first["components"])
    v2 = first["class_v2"]
    assert v2["result"] == "not_evaluated" and (v2["label"], v2["binding"]) == ("secondary", False)
    assert {item["trigger"]: item["met"] for item in v2["trigger_evidence"]} == {"E": False, "A": False, "B": None, "C": None, "D": None}
    assert all(item["evidence"].startswith("Not evaluated") for item in v2["trigger_evidence"] if item["met"] is None)
    # Unit 2 is under 100 residents: guardrail GR1 gives it no class and no v2 class.
    assert second["action_class"] is None and second["class_v2"] == {
        "class_rule_version": "class_rule_v2", "label": "secondary", "binding": False, "result": None, "trigger_evidence": []}

    receipt_path = runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"])
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    assert receipt["result"]["overlay_written"] is True and receipt["result"]["not_written_because"] is None
    assert receipt["result"]["rows_as_computed"] is None, "the overlay holds every row, so nothing is reported beside it"
    assert "FX-E8-U1" not in json.dumps(receipt["result"]), "the receipt in Git names no unit"
    counts = receipt["result"]["summary"]
    assert counts["row_count"] == 2 and counts["rows_under_gr1"] == 1
    assert counts["binding_class_by_lane_column"]["OBS"]["B"] == 1 and counts["binding_class_by_lane_column"]["OBS"]["none"] == 1
    assert counts["v2_result_by_lane_column"]["OBS"] == {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "no_v2_trigger": 0,
                                                         "not_evaluated": 1, "none": 1}
    assert all(entry["result"] == "PASS" for entry in receipt["guardrails"].values())
    assert receipt["whole_case_checks"]["result"] == "PASS" and receipt["whole_case_checks"]["rows"] == 2
    assert {point["id"] for point in receipt["open_points"]} >= {"E8-OP1", "E8-OP6", "E8-OP7"}
    assert receipt["result"]["rows_sha256"] == runner.rows_sha256(overlay["rows"])
    assert (world["register_dir"] / receipt_path.name).is_file(), "every run is reported"

    checked = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                            output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert checked["verified"] is True and checked["overlay_written"] is True
    # An overlay that was changed after the run is found.
    overlay_path.write_bytes(overlay_path.read_bytes().replace(b'"action_class": "B"', b'"action_class": "A"', 1))
    changed = runner.verify(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                            output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])
    assert changed["verified"] is False


def test_the_command_line_returns_3_for_a_run_that_writes_no_overlay_and_0_for_one_that_does(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The exit code goes through ``main``: 3 says that units were measured, no overlay was written and a receipt was."""

    monkeypatch.delenv(runner.EXTERNAL_DATA_VARIABLE, raising=False)
    codes = {}
    def fail(*_positional: Any, **_named: Any) -> dict[str, Any]:
        raise planning_assessment.PlanningAssessmentError("an invented failure of guardrail_report")

    report_of_the_guardrails = planning_assessment.guardrail_report
    for name in ("no_overlay", "overlay"):
        world = build_world(tmp_path / name, RESIDENTS)
        through_main = runner.run
        # A check that fails after the units were measured is one way a run writes no overlay.
        monkeypatch.setattr(planning_assessment, "guardrail_report", fail if name == "no_overlay" else report_of_the_guardrails)

        def run_in_the_world(*positional: Any, world: dict[str, Any] = world, **named: Any) -> dict[str, Any]:
            return through_main(*positional, **named, root=world["root"], output_dir=world["output_dir"],
                                register_dir=world["register_dir"], registry=world["registry"], git_commit="0123abc")

        monkeypatch.setitem(runner.FRAME_SETS, "fx_frame", world["frame_set"])
        monkeypatch.setattr(runner, "run", run_in_the_world)
        codes[name] = runner.main(["--case", CASE, "--frame", "fx_frame", "--external-data", str(world["external"]),
                                   "--boundaries", str(world["boundaries"])])
        monkeypatch.setattr(runner, "run", through_main)
        printed = json.loads(capsys.readouterr().out)
        assert printed["overlay_written"] is (name == "overlay")
        receipt_path = runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"])
        assert receipt_path.is_file() and (world["register_dir"] / receipt_path.name).is_file()
    assert codes == {"no_overlay": runner.EXIT_NOT_WRITTEN, "overlay": runner.EXIT_WRITTEN}
    assert (runner.EXIT_WRITTEN, runner.EXIT_REFUSED, runner.EXIT_NOT_WRITTEN) == (0, 2, 3)


@pytest.mark.parametrize("failing, stage, code", [
    ("guardrail_report", "guardrail_report", "guardrail_failed"),
    ("whole_case_checks", "whole_case_checks", "whole_case_check_failed"),
    ("assemble_overlay", "row_assembly", "guardrail_failed"),
])
def test_a_run_that_scores_its_units_and_then_fails_a_check_is_still_reported(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        failing: str, stage: str, code: str) -> None:
    """Every run on real units is reported: a check that fails after the units were scored ends in a registered receipt."""

    world = build_world(tmp_path)
    scored: list[int] = []
    assemble = planning_assessment.assemble_overlay

    def assemble_and_count(*positional: Any, **named: Any) -> dict[str, Any]:
        overlay = assemble(*positional, **named)
        scored.append(sum(1 for row in overlay["rows"] if row["fpps_0_100"] is not None))
        if failing == "assemble_overlay":
            raise planning_assessment.PlanningAssessmentError("guardrail GR7: an invented breach in unit FX-E8-U1")
        return overlay

    def fail(*_positional: Any, **_named: Any) -> dict[str, Any]:
        raise planning_assessment.PlanningAssessmentError(f"an invented failure of {failing} that names unit FX-E8-U1")

    monkeypatch.setattr(planning_assessment, "assemble_overlay", assemble_and_count)
    if failing != "assemble_overlay":
        monkeypatch.setattr(planning_assessment, failing, fail)
    through_main = runner.run

    def run_in_the_world(*positional: Any, **named: Any) -> dict[str, Any]:
        return through_main(*positional, **named, root=world["root"], output_dir=world["output_dir"],
                            register_dir=world["register_dir"], registry=world["registry"], git_commit="0123abc")

    monkeypatch.setitem(runner.FRAME_SETS, "fx_frame", world["frame_set"])
    monkeypatch.setattr(runner, "run", run_in_the_world)
    exit_code = runner.main(["--case", CASE, "--frame", "fx_frame", "--external-data", str(world["external"]),
                             "--boundaries", str(world["boundaries"])])
    monkeypatch.setattr(runner, "run", through_main)
    summary = json.loads(capsys.readouterr().out)
    assert scored == [2], "both invented units had an FPPS before the check failed"
    assert exit_code == runner.EXIT_NOT_WRITTEN == 3
    assert summary["overlay_written"] is False and summary["not_written_because"] == code
    assert summary["rows_reported_as_computed"] is False

    receipt_path = runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"])
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    entry = json.loads((world["register_dir"] / receipt_path.name).read_text(encoding="ascii"))
    assert entry == {"path": f"outputs/planning_v1/{receipt_path.name}", "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    result = receipt["result"]
    assert result["overlay_written"] is False and result["summary"] is None and result["rows_as_computed"] is None
    assert result["rows_sha256"] is None, "a row that fails a check is not reported"
    refusal = result["not_written_because"]
    assert (refusal["code"], refusal["stage"], refusal["error"]) == (code, stage, "PlanningAssessmentError")
    assert refusal["units_measured"] == 2 and refusal["rows_scored"] == (None if failing == "assemble_overlay" else 2)
    assert "every run on real units is reported" in refusal["message"]
    assert "FX-E8-U1" not in json.dumps({key: value for key, value in receipt.items() if key != "parameters"}), (
        "the receipt in Git names no unit; the message of the check is outside Git")
    assert receipt["whole_case_checks"] is None and receipt["measurement_checks"]["demand_cells"] == 5
    assert receipt["rights"]["figures_of_local_level_layers_in_this_receipt"]["figures"] == []
    # The report outside Git holds the message of the check and no row; no overlay exists.
    stage_folder = world["external"] / PROCESSED / "fx_case" / runner.STAGE_FOLDER
    assert sorted(path.name for path in stage_folder.iterdir()) == [runner.NOT_WRITTEN_REPORT_NAME]
    report = json.loads((stage_folder / runner.NOT_WRITTEN_REPORT_NAME).read_text(encoding="ascii"))
    assert report["rows_as_computed"] is None and report["not_written_because"]["code"] == code
    assert "FX-E8-U1" in report["not_written_because"]["message"] and report["official_warning"] is False
    assert runner.bound_outputs(receipt["outputs"]) == {
        f"{LABEL}/{PROCESSED}/fx_case/{runner.STAGE_FOLDER}/{runner.NOT_WRITTEN_REPORT_NAME}":
            hashlib.sha256((stage_folder / runner.NOT_WRITTEN_REPORT_NAME).read_bytes()).hexdigest()}
    # A second run of the same thing needs a reason, like any other run on these units.
    with pytest.raises(FileExistsError, match="--replace --reason"):
        run(world)


def test_a_measurement_that_is_refused_after_the_input_checks_is_reported_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = build_world(tmp_path)

    def refuse(*_positional: Any, **_named: Any) -> Any:
        raise planning_assessment.PlanningAssessmentError("an invented refusal while unit FX-E8-U2 was measured")

    monkeypatch.setattr(runner, "unit_measurements", refuse)
    summary = run(world)
    assert summary["overlay_written"] is False and summary["not_written_because"] == "measurement_refused"
    receipt = json.loads(runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).read_text(encoding="ascii"))
    refusal = receipt["result"]["not_written_because"]
    assert (refusal["stage"], refusal["units_measured"], refusal["rows_scored"]) == ("unit_measurements", 0, None)
    assert "FPPS" not in refusal["message"] and receipt["measurement_checks"] is None
    assert (world["register_dir"] / runner.receipt_path_for(CASE, world["frame_set"], world["output_dir"]).name).is_file()


# ---------------------------------------------------------------------------
# What the builder refuses, before anything is computed or written
# ---------------------------------------------------------------------------


def test_the_builder_refuses_to_run_unless_both_protocols_are_in_force(tmp_path: Path) -> None:
    world = build_world(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("planning_protocol_v1a.json", "planning_protocol_v1b.json"):
        shutil.copy(DOCS / name, docs / name)
    lines = [line for line in (DOCS / "RECEIPTS.jsonl").read_text(encoding="utf-8").splitlines()
             if "planning_protocol_v1b_sha256" not in line]
    (docs / "RECEIPTS.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(NormalisationError, match="planning protocol v1b is not in force"):
        run(world, docs=docs)
    shutil.copy(DOCS / "RECEIPTS.jsonl", docs / "RECEIPTS.jsonl")
    (docs / "planning_protocol_v1a.json").write_bytes((DOCS / "planning_protocol_v1a.json").read_bytes() + b" ")
    with pytest.raises(NormalisationError, match="planning protocol v1a is not in force"):
        run(world, docs=docs)
    assert nothing_was_written(world)


def test_the_builder_refuses_an_input_that_is_not_registered_or_was_changed(tmp_path: Path) -> None:
    world = build_world(tmp_path)
    # A receipt that the run register does not hold.
    for name in ("fx_e5_receipt.json", "fx_e7_receipt.json", "fx_e1_receipt.json", "fx_context_receipt.json", "fx_age_table.json"):
        entry = world["register_dir"] / name
        kept = entry.read_bytes()
        entry.unlink()
        with pytest.raises(runner.BuildError, match="not registered in the run register"):
            run(world)
        entry.write_bytes(kept)
    # A registered file whose bytes changed since.
    for name in ("fx_age_table.json", "fx_access_table.json", "fx_e1_receipt.json"):
        path = world["output_dir"] / name
        kept = path.read_bytes()
        path.write_bytes(kept + b" ")
        with pytest.raises(runner.BuildError, match="not the file the run register holds"):
            run(world)
        path.write_bytes(kept)
    # A layer outside the repository that is not the bytes the registered E1 receipt binds.
    extent = world["flood_folder"] / "flood_extent__as_provided__reporting_frame.geojson"
    for path, message in ((extent, "cannot be read"), (world["water_file"], "not the file the registered E1 receipt binds"),
                          (world["flood_folder"] / flood_inputs.INPUT_RECORD_NAME, "not the one the registered E1 receipt binds")):
        kept = path.read_bytes()
        path.write_bytes(kept + b"\n")
        with pytest.raises(runner.BuildError, match=message):
            run(world)
        path.write_bytes(kept)
    # A planning context that is not the one its registered receipt names; a national-anchor receipt that is not v1b's.
    context = world["external"] / PROCESSED / "fx_case" / "e4_vehicle" / "context_inputs.json"
    kept = context.read_bytes()
    document = json.loads(kept)
    document["population"][0]["total_population"] += 1
    context.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(runner.BuildError, match="canonical SHA-256"):
        run(world)
    context.write_bytes(kept)
    anchors = world["output_dir"] / "national_vulnerability_anchors_v1.json"
    kept = anchors.read_bytes()
    anchors.write_bytes(kept + b" ")
    with pytest.raises(runner.BuildError, match="national-anchor receipt"):
        run(world)
    anchors.write_bytes(kept)
    boundaries = world["boundaries"].read_bytes()
    world["boundaries"].write_bytes(boundaries + b" ")
    with pytest.raises(runner.BuildError, match="boundary file"):
        run(world)
    world["boundaries"].write_bytes(boundaries)
    assert nothing_was_written(world)
    assert run(world)["overlay_written"] is True, "with every input restored the same world runs"


def test_the_builder_refuses_what_the_rights_registry_refuses(tmp_path: Path) -> None:
    world = build_world(tmp_path)
    with pytest.raises(rights.RightsRefusedError, match="no rights record is registered"):
        run(world, registry=rights.RightsRegistry(world["root"], records=()))
    record = json.loads(world["rights_record"].read_text(encoding="ascii"))
    world["rights_record"].write_bytes(_json({**record, "record_status": "draft"}))
    with pytest.raises(rights.RightsRefusedError, match="not confirmed by the owners"):
        run(world)
    # A record that is confirmed and is not the one the flood input names (another level or other bytes).
    world["rights_record"].write_bytes(_json({**record, "note": "edited after the flood input was written"}))
    with pytest.raises(runner.BuildError, match="not the confirmed record its flood input names"):
        run(world)
    assert nothing_was_written(world)


def test_the_builder_refuses_a_table_that_says_it_is_not_usable(tmp_path: Path) -> None:
    """The pitch-services tables of task E5 say ``usable_by_task_e8: false`` (open point E5-OP5)."""

    world = build_world(tmp_path)
    write_access_table(world, {**world["access_table"], "usable_by_task_e8": False,
                               "usable_by_task_e8_basis": "Not usable: the walking context is a candidate (open point E5-OP5)."})
    with pytest.raises(runner.BuildError, match="says it is not usable by task E8: Not usable: the walking context is a candidate"):
        run(world)
    with pytest.raises(runner.BuildError, match="binds no pitch_services table"):
        run(build_world(tmp_path / "pitch"), level="pitch")
    assert nothing_was_written(world)


def test_the_level_is_part_of_every_name_and_the_pitch_level_is_refused_until_its_lineage_is_built(tmp_path: Path) -> None:
    """A run at one level never supersedes or deletes the files of another; and no pitch overlay is built yet."""

    world = build_world(tmp_path)
    frame_set, output_dir, external = world["frame_set"], world["output_dir"], world["external"]
    public, pitch = (runner.receipt_path_for(CASE, frame_set, output_dir, level) for level in ("public", "pitch"))
    assert public.name == "e8_planning_assessment_fx-e8_fx_frame.json" == runner.receipt_path_for(CASE, frame_set, output_dir).name
    assert pitch.name == "e8_planning_assessment_fx-e8_fx_frame_pitch.json"
    for eligibility in ("public", "pitch", "local"):
        targets = {level: runner.overlay_target(CASE, frame_set, eligibility, external, output_dir, level)[0]
                   for level in ("public", "pitch")}
        assert targets["public"] != targets["pitch"] and targets["pitch"].name.endswith("_fx_frame_pitch.json")
        assert targets["public"].name == "planning_assessment_overlay_fx-e8_fx_frame.json"
    assert runner.stage_folder(CASE, frame_set, external).name == runner.STAGE_FOLDER
    assert runner.stage_folder(CASE, frame_set, external, "pitch").name == runner.STAGE_FOLDER + "_pitch"
    # A pitch-services table that says it is usable: the builder still refuses, and says what is not built.
    table = {**world["access_table"], "service_set": "pitch_services", "publication_level": "pitch", "usable_by_task_e8": True}
    sha256 = _write(output_dir / "fx_access_table.json", _json(table))
    _write(output_dir / "fx_e5_receipt.json", _json({"generated_at_utc": "2030-01-03T00:00:00Z", "protocol_sha256": HASHES, "outputs": {
        CASE: {"files": [{"path": "outputs/planning_v1/fx_access_table.json", "sha256": sha256, "what": "unit_table",
                          "service_set": "pitch_services", "publication_level": "pitch", "in_git": True}]}}}))
    register(world, "fx_access_table.json")
    register(world, "fx_e5_receipt.json")
    with pytest.raises(runner.BuildError, match="pitch level is not built yet.*walking context.*E5-OP5"):
        run(world, level="pitch")
    assert nothing_was_written(world) and not pitch.exists()


def test_the_builder_refuses_components_from_two_flood_inputs_or_two_contexts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guardrail GR3: the access table must come from the flood input, the extent bytes and the context this run reads."""

    world = build_world(tmp_path)
    table = world["access_table"]
    other_extent = json.loads(json.dumps(table))
    other_extent["flood_input"]["files"]["as_provided"]["sha256"] = "e" * 64
    other_context = json.loads(json.dumps(table))
    other_context["contexts"]["vehicle"]["canonical_sha256"] = "d" * 64
    other_input = json.loads(json.dumps(table))
    other_input["flood_input"]["input_id"] = "fx_agency:ANOTHER_LAYER"
    other_residents = json.loads(json.dumps(table))
    for item in other_residents["runs"]:
        item["units"][0]["residents"] += 1.0
    measured: list[str] = []
    measure = runner.unit_measurements
    monkeypatch.setattr(runner, "unit_measurements", lambda *positional, **named: measured.append("called") or measure(*positional, **named))

    def check(world: dict[str, Any]) -> dict[str, Any]:
        return runner.check_inputs(CASE, world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                                   output_dir=world["output_dir"], register_dir=world["register_dir"], registry=world["registry"])

    for changed, message in ((other_extent, "closure_extent_sha256"), (other_context, "routing_context_canonical_sha256"),
                             (other_input, "flood_input_id"), (other_residents, "do not agree on the residents")):
        write_access_table(world, changed)
        with pytest.raises(planning_assessment.LanePurityError, match=message):
            run(world)
        # The input check alone finds it too: nothing has to be measured against the flood input first.
        with pytest.raises(planning_assessment.LanePurityError, match=message):
            check(world)
    stored_ratio = json.loads(json.dumps(table))
    for item in stored_ratio["runs"]:
        item["units"][0]["routes"]["share_losing_all_routes"] = 1.0
    write_access_table(world, stored_ratio)
    with pytest.raises(planning_assessment.PlanningAssessmentError, match="never from a stored ratio"):
        run(world)
    with pytest.raises(planning_assessment.PlanningAssessmentError, match="never from a stored ratio"):
        check(world)
    # A table with no row for a unit of the frame.
    missing_row = json.loads(json.dumps(table))
    for item in missing_row["runs"]:
        item["units"] = item["units"][:1]
    write_access_table(world, missing_row)
    with pytest.raises(runner.BuildError, match="has no row for unit"):
        check(world)
    assert measured == [], "every one of these refusals comes before a unit is measured against the flood input"
    assert nothing_was_written(world)
    write_access_table(world, table)
    assert check(world)["inputs_checked"] is True and measured == []


def test_case_o1_and_an_unknown_case_are_refused_before_any_input_of_a_unit_is_read(tmp_path: Path) -> None:
    """Case O1 is refused from what the committed E1 and E5 receipts bind and what the rights registry holds today."""

    mae_sai = runner.FRAME_SETS["mae_sai"]
    # The two registered receipts are read from the repository: files in Git, with counts for whole frames only.
    with pytest.raises(runner.BuildError) as refused:
        runner.build("O1", mae_sai, tmp_path, tmp_path / "no-boundaries", generated_at_utc="2030-01-01T00:00:00Z", git_commit="0123abc")
    assert str(refused.value) == (
        "case O1 cannot be run: the registered E1 receipt binds no flood input of case O1; the registered E5 receipt "
        "binds no access table of case O1; the rights registry holds no record of Sentinel-1 data (open point E1-OP2)")
    with pytest.raises(runner.BuildError, match="not a case of frame mae_sai"):
        runner.build("SE2", mae_sai, tmp_path, tmp_path / "no-boundaries", generated_at_utc="2030-01-01T00:00:00Z",
                     output_dir=tmp_path, register_dir=tmp_path, git_commit="0123abc")
    assert not list(tmp_path.iterdir())


def test_the_refusal_of_an_awaited_case_follows_what_the_earlier_tasks_have_delivered(tmp_path: Path) -> None:
    """The sentence is read from the registered receipts and the registry, so it changes when an input is delivered."""

    world = build_world(tmp_path / "world")

    def refusal(registry: rights.RightsRegistry | None = None) -> str:
        with pytest.raises(runner.BuildError) as refused:
            runner.run("FX-O1", world["frame_set"], world["external"], world["boundaries"], root=world["root"],
                       output_dir=world["output_dir"], register_dir=world["register_dir"], registry=registry or world["registry"])
        return str(refused.value)

    assert refusal() == (
        "case FX-O1 cannot be run: the registered E1 receipt binds no flood input of case FX-O1; the registered E5 "
        "receipt binds no access table of case FX-O1; the rights registry holds no record of invented radar data "
        "(open point FX-OP1)")
    # Task E1 delivers a flood input for the case: the first clause goes.
    e1_path = world["output_dir"] / "fx_e1_receipt.json"
    e1_receipt = json.loads(e1_path.read_text(encoding="ascii"))
    e1_receipt["outputs"]["FX-O1"] = {"files": [{"path": f"{LABEL}/{PROCESSED}/fx_o1/e1_flood_input/input_record.json", "sha256": "a" * 64}]}
    e1_path.write_bytes(_json(e1_receipt))
    register(world, "fx_e1_receipt.json")
    assert refusal() == (
        "case FX-O1 cannot be run: the registered E5 receipt binds no access table of case FX-O1; the rights registry "
        "holds no record of invented radar data (open point FX-OP1)")
    # Task E5 delivers a table and the owners register a record of the source data: what is left is what is not built.
    e5_path = world["output_dir"] / "fx_e5_receipt.json"
    e5_receipt = json.loads(e5_path.read_text(encoding="ascii"))
    e5_receipt["outputs"]["FX-O1"] = {"files": [{"path": "outputs/planning_v1/fx_o1_table.json", "sha256": "b" * 64, "what": "unit_table"}]}
    e5_path.write_bytes(_json(e5_receipt))
    register(world, "fx_e5_receipt.json")
    with_record = rights.RightsRegistry(world["root"], records=(
        rights.RegisteredRecord("fx_agency", "rights/fx_rights.json", "an invented layer of a fixture", "fixture_invented_source"),
        rights.RegisteredRecord("fx_radar", "rights/fx_radar.json", "invented radar data of a fixture", "fixture_radar_source")))
    assert refusal(with_record) == (
        "case FX-O1 cannot be run yet: tasks E1 and E5 have delivered a flood input and an access table and the rights "
        "registry holds a record of invented radar data, and this builder does not read an invented radar case")
    # A receipt that is not the registered one is refused before it is read for the case.
    e5_path.write_bytes(e5_path.read_bytes() + b" ")
    assert "not the file the run register holds" in refusal(with_record)
    assert nothing_was_written(world)


def test_the_licence_block_of_a_product_4009_run_names_the_credit_the_licence_and_the_step_of_this_task() -> None:
    """Product 4009 content ships only under CC BY-SA 4.0 with its credit and a change notice (plan 7.1)."""

    sentence_rules = flood_inputs.rules_from_protocols(V1A, V1B)
    record = {
        "source": {"layer": "CHIANGRAI_20240801_20241012_AccumulatedFlood"},
        "rights": {"licence": {"name": "CC BY-SA 4.0", "full_name": "Creative Commons Attribution-ShareAlike 4.0 International",
                               "spdx_id": "CC-BY-SA-4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/",
                               "legal_code_url": "https://creativecommons.org/licenses/by-sa/4.0/legalcode"},
                   "attribution": "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009", "share_alike": "an invented sentence",
                   "record_path": "docs/proposal_execution/rights_basis_4009_v1.json", "record_sha256": "c" * 64,
                   "record_status": "confirmed", "confirmed_by": ["an invented owner"], "confirmed_on": "2030-01-01",
                   "rights_level": "public", "rights_level_basis": "an invented basis"}}
    block = runner.licence_block(record, sentence_rules, runner.FRAME_SETS["mae_sai"], "public", "local", "a notice file")
    assert (block["name"], block["spdx_id"]) == ("CC BY-SA 4.0", "CC-BY-SA-4.0")
    assert block["credit"] == "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" == V1A["wording"]["product_4009_credit"]
    assert block["standard_sentence"] == V1A["wording"]["standard_4009_sentence"] and "FloodGuard did not validate it" in block["standard_sentence"]
    notice = block["change_notice"]
    assert notice.startswith("Changed by FloodGuard: the layer CHIANGRAI_20240801_20241012_AccumulatedFlood")
    assert "(plan task E5)" in notice and "In plan task E8" in notice and "component values of planning frame v1" in notice
    assert notice.endswith("Source: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009, CC BY-SA 4.0.")
    assert block["rights_record"] == {"path": "docs/proposal_execution/rights_basis_4009_v1.json", "sha256": "c" * 64,
                                      "record_status": "confirmed", "confirmed_by": ["an invented owner"], "confirmed_on": "2030-01-01"}
    assert (block["publication_level"], block["flood_input_rights_level"], block["licence_notice_file"]) == ("local", "public", "a notice file")
    assert [item["id"] for item in block["other_inputs"]] == ["osm", "worldpop-2020", "cod-ab", "esa-worldcover-2021", "worldpop-2024-age-counts"]
    assert all(item["licence"].strip() and item["attribution"].strip() and item["used_for"].strip() for item in block["other_inputs"])
    assert "product 4009" in block["applies_to"] and block["not_legal_advice"] is True


def test_a_count_that_covers_every_row_is_named_because_it_states_a_value_for_each_unit() -> None:
    summary = {"row_count": 8, "unit_count": 8,
               "binding_class_by_lane_column": {"OBS": {"A": 0, "E": 8, "none": 0}, "SCN": {"A": 0, "E": 0, "none": 0}},
               "confidence_class_by_lane_column": {"OBS": {"low": 3, "medium": 5, "none": 0}},
               "failed_conditions_by_lane_column": {"OBS": {"C4_input_uncertainty": 8, "C7_baseline_no_route": 0}},
               "basis_values_by_lane_column": {"OBS": {"pass": 8, "fail": 56}}}
    assert runner.counts_that_cover_every_row(summary) == [
        "binding_class_by_lane_column.OBS.E", "failed_conditions_by_lane_column.OBS.C4_input_uncertainty"]
    assert runner.counts_that_cover_every_row(None) == [] and runner.counts_that_cover_every_row({"row_count": 0}) == []
    assert runner.rows_sha256([{"b": 1, "a": 2}]) == runner.rows_sha256([{"a": 2, "b": 1}]) != runner.rows_sha256([{"a": 2, "b": 2}])


def test_the_mae_sai_frame_set_states_its_cases_its_services_and_the_level_of_each_input() -> None:
    mae_sai = runner.FRAME_SETS["mae_sai"]
    assert set(mae_sai.case_folders) == {"SE1", "O2"} and set(mae_sai.not_run) == {"O1"}
    assert mae_sai.not_run["O1"].rights_source == rights.SOURCE_SENTINEL1 and mae_sai.not_run["O1"].open_point == "E1-OP2"
    assert mae_sai.context_binding == runner.CONTEXT_BY_PROTOCOL and mae_sai.reporting_frame == "mae_sai"
    assert runner.SERVICE_SETS == {"public": "public_services", "pitch": "pitch_services"}
    levels = {key: item.rights_level for key, item in mae_sai.lineage.items()}
    # Protocol v1b: public derivatives of the 2024 age rasters need a purpose-specific review; it is recorded (R21).
    assert levels["age_structure"] == "public" and "purpose-specific review" in mae_sai.lineage["age_structure"].rights_level_basis
    assert "decision log R21" in mae_sai.lineage["age_structure"].rights_level_basis
    assert {key for key, level in levels.items() if level == "public"} == {
        "routing_context", "population", "boundaries", "permanent_water", "national_anchors", "age_structure"}
    assert all(item.rights_level_basis.strip() and item.licence.strip() and item.attribution.strip() for item in mae_sai.lineage.values())
    # HDX COD-AB: adm3_name1 is the Thai name when lang1 says "th".
    assert (mae_sai.unit_id_field, mae_sai.unit_name_en_field, mae_sai.unit_name_th_field, mae_sai.unit_name_th_language_field) == (
        "adm3_pcode", "adm3_name", "adm3_name1", "lang1")
    for title_en, title_th, frame in mae_sai.case_titles.values():
        assert "Mae Sai" in title_en and "แม่สาย" in title_th and frame == "Mae Sai, 8 tambons"
        assert "น้ำค้าง" not in title_th, "the Thai word for dew is not the word for water that remains after a flood"
    # Residual water: water that still remains, as the replay page words a remaining extent. A scenario is named as one.
    assert "น้ำที่ยังเหลืออยู่ปลายฤดู 22 ตุลาคม พ.ศ. 2567" in mae_sai.case_titles["O2"][1]
    assert "สถานการณ์จำลอง" in mae_sai.case_titles["SE1"][1] and "พ.ศ. 2567" in mae_sai.case_titles["SE1"][1]
    assert runner.overlay_input_id("unosat_4009:CHIANGRAI_20240801_20241012_AccumulatedFlood") == (
        "unosat_4009.chiangrai_20240801_20241012_accumulatedflood")
    with pytest.raises(runner.BuildError, match="cannot be written as an input identifier"):
        runner.overlay_input_id("an input with spaces")


def test_the_command_line_wants_replace_and_reason_together_and_an_external_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(runner.EXTERNAL_DATA_VARIABLE, raising=False)
    for arguments in (["--case", "SE1", "--frame", "mae_sai"],
                      ["--case", "SE1", "--frame", "mae_sai", "--external-data", str(tmp_path), "--replace"],
                      ["--case", "SE1", "--frame", "mae_sai", "--external-data", str(tmp_path), "--reason", "why"]):
        with pytest.raises(SystemExit):
            runner.main(arguments)
    capsys.readouterr()
    # Case O1 is refused by the command line with exit code 2, and nothing is written.
    assert runner.main(["--case", "O1", "--frame", "mae_sai", "--external-data", str(tmp_path)]) == runner.EXIT_REFUSED
    assert "REFUSED: case O1 cannot be run: the registered E1 receipt binds no flood input of case O1" in capsys.readouterr().err
    assert runner.main(["--case", "O1", "--frame", "mae_sai", "--external-data", str(tmp_path), "--check-inputs"]) == runner.EXIT_REFUSED
    assert "the rights registry holds no record of Sentinel-1 data (open point E1-OP2)" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
