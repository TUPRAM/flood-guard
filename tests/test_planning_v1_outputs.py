"""Every committed file under outputs/planning_v1 says what it is.

AGENTS.md asks every output for a source timestamp, a confidence and its
assumptions. These tests read the committed files only. They compute no FPPS,
no A-E class and no ensemble, and they check that no file names a tambon.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pytest

from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.hospital_counts import count_hospitals

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs" / "planning_v1"
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DOCUMENTATION = {"README.md"}
FILES = sorted(path for path in OUTPUTS.iterdir() if path.name not in DOCUMENTATION) if OUTPUTS.is_dir() else []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _documents(path: Path) -> list[dict[str, Any]]:
    """Return the objects of a file that must carry the provenance fields."""

    payload = json.loads(path.read_bytes().decode("ascii"))
    if path.suffix == ".geojson":
        assert payload["type"] == "FeatureCollection" and payload["features"]
        return [feature["properties"] for feature in payload["features"]]
    return [payload]


def test_the_folder_holds_only_json_geojson_and_its_readme() -> None:
    if not FILES:
        pytest.skip("no planning output on this checkout")
    assert all(path.suffix in {".json", ".geojson"} for path in FILES), [path.name for path in FILES]
    readme = (OUTPUTS / "README.md").read_text(encoding="utf-8")
    for path in FILES:
        assert f"`{path.name}`" in readme, f"{path.name} is not described in outputs/planning_v1/README.md"


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_every_output_carries_timestamp_confidence_and_assumptions(path: Path) -> None:
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    for document in _documents(path):
        assert isinstance(document["source_timestamp"], str) and document["source_timestamp"].strip(), path.name
        assert UTC.match(document["generated_at_utc"]), path.name
        assert document["confidence_class"] in VALID_CONFIDENCE_CLASSES, path.name
        assert document["confidence_class"] == "low", "no planning output has been checked against anything yet"
        assert document["confidence_basis"].strip(), path.name
        assumptions = document["assumptions"]
        assert isinstance(assumptions, list) and assumptions, path.name
        assert all(isinstance(line, str) and line.strip() for line in assumptions), path.name
        assert document["official_warning"] is False, path.name
        assert document["operational_status"] == "non_operational", path.name


@pytest.mark.parametrize("path", [path for path in FILES if "candidate" in path.name], ids=lambda path: path.name)
def test_a_candidate_file_says_it_is_a_candidate_inside_the_file(path: Path) -> None:
    """A join log or corridor copied out of the folder cannot pass for a decided one."""

    for document in _documents(path):
        assert document["status"] == "candidate", path.name
        assert "OI-02" in document["status_note"] and "not" in document["status_note"], path.name


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_no_output_names_a_tambon(path: Path) -> None:
    text = path.read_bytes().decode("ascii")
    assert not re.search(r"TH\d{6}", text), "an eight-character tambon code"
    assert "subdistrict_id" not in text and "adm3_pcode\":" not in text


def test_join_logs_and_corridors_match_their_spike_receipts() -> None:
    for variant in ("proposal", "whole_path"):
        receipt_path = OUTPUTS / f"e0_context_spike_{variant}.json"
        if not receipt_path.exists():
            pytest.skip("the E0 spike has not been run on this checkout")
        receipt = json.loads(receipt_path.read_text(encoding="ascii"))
        log_path = ROOT / receipt["grade_joins"]["log_path"]
        log = json.loads(log_path.read_text(encoding="ascii"))
        corridor = json.loads((ROOT / receipt["corridor"]["path"]).read_text(encoding="ascii"))
        properties = corridor["features"][0]["properties"]
        assert log["status"] == properties["status"] == "candidate"
        assert log["generated_at_utc"] == properties["generated_at_utc"] == receipt["generated_at_utc"]
        assert log["source_timestamp"] == properties["source_timestamp"] == receipt["source_timestamp"]
        assert log["context_canonical_sha256"] == receipt["context"]["canonical_sha256"]
        assert log["join_count"] == len(log["joins"]) == receipt["grade_joins"]["join_count"]
        assert log["joins_sha256"] == receipt["grade_joins"]["joins_sha256"]
        assert properties["geometry_sha256"] == receipt["corridor"]["geometry_sha256"]
        geometry = json.dumps(corridor["features"][0]["geometry"], sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(geometry.encode("ascii")).hexdigest() == properties["geometry_sha256"]
        assert properties["route_rule_variant"] == variant and properties["route_rule"] == receipt["route_rule"]

        # Numbers quoted to the owners come from the receipt: road classes, bridge tags, hospitals, rerun.
        counts = receipt["edge_counts"]
        assert counts["edges"] == receipt["e0_spike_record_candidate"]["edge_count"]
        assert sum(counts["by_road_class"].values()) == counts["edges"]
        assert sum(counts["by_bridge_tag"].values()) == sum(counts["by_tunnel_tag"].values()) == counts["edges"]
        assert counts["bridge_yes_edges"] == counts["by_bridge_tag"].get("yes", 0)
        breakdown = receipt["hospital_count_breakdown"]
        assert breakdown["osm_objects"] == receipt["e0_spike_record_candidate"]["hospital_count"]
        assert len(receipt["hospitals_in_routing_context"]) == breakdown["osm_objects"]
        repeat = receipt["reproducibility"]
        assert repeat["compared"] is True and repeat["all_same"] is True
        assert repeat["previous_run"]["generated_at_utc"] < receipt["generated_at_utc"]
        window = receipt["acceptance"]["compute_window"]
        assert window["met"] == bool(window["declared_by_the_operator"])
        assert receipt["acceptance"]["criteria_met"]["declared_compute_window"] == window["met"]
        assert receipt["acceptance"]["all_criteria_met"] == all(receipt["acceptance"]["criteria_met"].values())


RECORD_RECEIPT = OUTPUTS / "e0_context_run_of_record.json"


def test_the_run_of_record_is_consistent_and_says_what_it_is() -> None:
    """The corridor, join log and receipt of the run of record agree, and every plan criterion is met."""

    if not RECORD_RECEIPT.exists():
        pytest.skip("the run of record has not been made on this checkout")
    receipt = json.loads(RECORD_RECEIPT.read_text(encoding="ascii"))
    assert receipt["run_kind"] == receipt["status"] == "run_of_record"
    assert receipt["route_rule_variant"] == "whole_path"
    corridor_path = ROOT / receipt["corridor"]["path"]
    log_path = ROOT / receipt["grade_joins"]["log_path"]
    assert corridor_path.name == "corridor_of_record.geojson" and log_path.name == "grade_join_log_of_record.json"
    assert _sha256(corridor_path) == receipt["corridor"]["sha256"]
    assert _sha256(log_path) == receipt["grade_joins"]["log_sha256"]
    log = json.loads(log_path.read_text(encoding="ascii"))
    properties = json.loads(corridor_path.read_text(encoding="ascii"))["features"][0]["properties"]
    assert log["status"] == "log_of_record" and properties["status"] == "of_record"
    for document in (log, properties):
        assert "R12" in document["status_note"] and "compute window" in document["status_note"]
        assert document["generated_at_utc"] == receipt["generated_at_utc"]
        assert document["source_timestamp"] == receipt["source_timestamp"]
    assert log["join_count"] == len(log["joins"]) == receipt["grade_joins"]["join_count"]
    assert log["joins_sha256"] == receipt["grade_joins"]["joins_sha256"]
    assert log["context_canonical_sha256"] == receipt["context"]["canonical_sha256"]

    # Plan 5 item 1: a declared compute window, and every acceptance value.
    acceptance = receipt["acceptance"]
    window = acceptance["compute_window"]
    assert window["met"] is True and window["declared_by_the_operator"].strip()
    assert window["run_started_at_utc"] <= receipt["generated_at_utc"] <= window["run_finished_at_utc"]
    assert all(acceptance["criteria_met"].values()) and acceptance["all_criteria_met"] is True
    assert acceptance["load_aois_still_returns_6"] is True
    record = receipt["e0_spike_record"]
    breakdown = receipt["hospital_count_breakdown"]
    # Owner choice 22: distinct named hospitals; the OSM objects are all destinations.
    assert record["hospital_count"] == breakdown["distinct_named_hospitals"] >= 4
    assert breakdown["osm_objects"] == len(receipt["hospitals_in_routing_context"])
    assert record["within_routing_context_for_named_ways"] is True
    assert record["baseline_vehicle_no_route_share"] <= 0.1
    assert record["edge_count"] == receipt["edge_counts"]["edges"]
    # The record reproduces the whole-path candidate of 2 October.
    repeat = receipt["reproducibility"]
    assert repeat["compared"] is True and repeat["all_same"] is True
    candidate = json.loads((OUTPUTS / "e0_context_spike_whole_path.json").read_text(encoding="ascii"))
    assert repeat["previous_run"]["generated_at_utc"] == candidate["generated_at_utc"]

    # Shelter corroboration: counts only, consistent with the located rows.
    facilities = receipt["facility_counts"]
    corroboration = facilities["shelter_corroboration"]
    assert corroboration["located_rows"] == facilities["located_ddpm_shelters"]
    assert facilities["corroborated_shelters"] == corroboration["corroborated_rows"] <= corroboration["located_rows"]
    assert corroboration["match_distance_m"] == 150.0
    assert corroboration["corroborated_rows"] == (
        corroboration["matched_to_a_building_rows"] + corroboration["matched_to_an_amenity_only_rows"])


def test_protocol_v1b_records_the_run_of_record_exactly() -> None:
    if not RECORD_RECEIPT.exists():
        pytest.skip("the run of record has not been made on this checkout")
    protocol = json.loads(PROTOCOL.read_text(encoding="ascii"))
    receipt = json.loads(RECORD_RECEIPT.read_text(encoding="ascii"))
    corridor = protocol["corridor_polygon"]
    block = corridor.get("run_of_record")
    if block is None:
        pytest.skip("protocol v1b does not record the run of record yet")
    assert block["run_receipt_path"] == RECORD_RECEIPT.relative_to(ROOT).as_posix()
    assert block["run_receipt_sha256"] == _sha256(RECORD_RECEIPT)
    assert block["generated_at_utc"] == receipt["generated_at_utc"]
    assert block["context_canonical_sha256"] == receipt["context"]["canonical_sha256"]
    items = {item["id"]: item for item in protocol["open_items"]}
    if corridor["geometry_file"]["path"] is not None:
        assert corridor["geometry_file"] == {"path": receipt["corridor"]["path"], "sha256": receipt["corridor"]["sha256"]}
    if items["OI-03"]["status"] == "closed":
        assert corridor["e0_spike_record"] == receipt["e0_spike_record"]
    join_log = protocol["grade_join_policy"]["join_log"]
    if join_log["path"] is not None:
        assert join_log == {"path": receipt["grade_joins"]["log_path"], "sha256": receipt["grade_joins"]["log_sha256"],
                            "join_count": receipt["grade_joins"]["join_count"]}
    count_keys = ("osm_hospitals", "dga_matched_hospitals", "located_ddpm_shelters", "corroborated_shelters")
    counts = protocol["facility_sets"]["counts_in_corridor"]
    if counts["corroborated_shelters"] is not None and counts.get("evidence_sha256") == _sha256(RECORD_RECEIPT):
        for key in count_keys:
            assert counts[key] == receipt["facility_counts"][key], key

    # OI-04 and the counts of OI-06 follow from the E4 build. What this spike run measured is kept beside their
    # slots and is what E4 must reproduce; both copies repeat the receipt exactly.
    spike_log = protocol["grade_join_policy"]["join_log_from_spike_run_of_record"]
    assert {key: spike_log[key] for key in ("path", "sha256", "join_count", "joins_sha256")} == {
        "path": receipt["grade_joins"]["log_path"], "sha256": receipt["grade_joins"]["log_sha256"],
        "join_count": receipt["grade_joins"]["join_count"], "joins_sha256": receipt["grade_joins"]["joins_sha256"]}
    spike_counts = protocol["facility_sets"]["counts_from_spike_run_of_record"]
    assert {key: spike_counts[key] for key in count_keys} == {key: receipt["facility_counts"][key] for key in count_keys}
    assert spike_counts["evidence_sha256"] == _sha256(RECORD_RECEIPT)
    check = block["e4_reproduction_check"]
    assert check["source"] == RECORD_RECEIPT.relative_to(ROOT).as_posix() and check["source_sha256"] == _sha256(RECORD_RECEIPT)
    assert check["joins_sha256"] == receipt["grade_joins"]["joins_sha256"]
    assert check["join_count"] == receipt["grade_joins"]["join_count"]
    assert check["edge_count"] == receipt["e0_spike_record"]["edge_count"]
    assert check["grade_split_count"] == receipt["e0_spike_record"]["grade_split_count"]
    assert check["corridor_geometry_sha256"] == receipt["corridor"]["geometry_sha256"]
    assert check["context_canonical_sha256"] == receipt["context"]["canonical_sha256"]
    assert check["facility_counts"] == {key: receipt["facility_counts"][key] for key in count_keys}
    assert receipt["context_call"]["facilities_supplied"] == 0, "the context-hash note says no facility was supplied"
    assert check["mae_sai_hospital_facility_id"] in {row["facility_id"] for row in receipt["hospitals_in_routing_context"]}

    # The run's receipt is not edited; the protocol corrects what it got wrong.
    corrected = {entry["receipt_key"] for entry in block["receipt_corrections"]}
    assert {"reproducibility.note", "acceptance.compute_window.declared_by_the_operator"} <= corrected
    assert "replaced them" in receipt["reproducibility"]["note"]
    candidate_sha256 = next(candidate["spike_record_sha256"] for candidate in corridor["e0_spike_candidates"]["candidates"]
                            if candidate["route_rule_variant"] == "whole_path")
    assert _sha256(OUTPUTS / "e0_context_spike_whole_path.json") == candidate_sha256, "the run of record replaced nothing"

    # The spike now counts hospitals through the rule the planning frames use; it gives this run's breakdown.
    breakdown = receipt["hospital_count_breakdown"]
    assert count_hospitals(receipt["hospitals_in_routing_context"]) == {
        key: breakdown[key] for key in ("osm_objects", "distinct_named_hospitals", "unnamed_objects",
                                        "objects_that_repeat_a_named_hospital")}


def test_protocol_candidates_repeat_the_committed_files_exactly() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="ascii"))
    block = protocol["corridor_polygon"].get("e0_spike_candidates")
    if block is None:
        pytest.skip("protocol v1b no longer carries spike candidates")
    for candidate in block["candidates"]:
        receipt_path = ROOT / candidate["spike_record_path"]
        if not receipt_path.exists():
            pytest.skip("the E0 spike has not been run on this checkout")
        receipt = json.loads(receipt_path.read_text(encoding="ascii"))
        record = receipt["e0_spike_record_candidate"]
        assert candidate["spike_record_sha256"] == _sha256(receipt_path)
        assert candidate["spike_record_generated_at_utc"] == receipt["generated_at_utc"]
        assert candidate["corridor_sha256"] == _sha256(ROOT / candidate["corridor_path"])
        assert candidate["corridor_geometry_sha256"] == receipt["corridor"]["geometry_sha256"]
        assert candidate["grade_join_log_sha256"] == _sha256(ROOT / candidate["grade_join_log_path"])
        assert candidate["grade_joins_sha256"] == receipt["grade_joins"]["joins_sha256"]
        assert candidate["route_rule"] == receipt["route_rule"]
        for key in ("hospital_count", "edge_count", "wall_time_minutes", "peak_ram_gib", "grade_split_count"):
            assert candidate[key] == record[key], key
        assert candidate["baseline_vehicle_no_route_share"] == record["baseline_vehicle_no_route_share"]
        assert candidate["grade_join_count"] == receipt["grade_joins"]["join_count"]
        assert candidate["named_ways_within_routing_context"] == receipt["acceptance"]["named_ways_within_routing_context"]
        assert candidate["context_build_sampled_peak_gib"] == receipt["context_build_memory"]["sampled_peak_gib"]
        assert candidate["same_as_previous_run"] == receipt["reproducibility"]["all_same"]
        assert candidate["edge_counts"]["by_road_class"] == receipt["edge_counts"]["by_road_class"]
        assert candidate["edge_counts"]["bridge_yes_edges"] == receipt["edge_counts"]["bridge_yes_edges"]
        assert candidate["edge_counts"]["tunnel_culvert_edges"] == receipt["edge_counts"]["tunnel_culvert_edges"]
        met = {key: value for key, value in candidate["meets_plan_acceptance"].items() if key != "all_criteria_met"}
        assert met == receipt["acceptance"]["criteria_met"]
        for key, value in candidate["hospital_count_breakdown"].items():
            assert receipt["hospital_count_breakdown"][key] == value, key


def test_protocol_anchor_candidates_repeat_the_committed_receipt_exactly() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="ascii"))
    candidates = protocol["national_vulnerability_anchors"].get("anchor_candidates")
    if candidates is None:
        pytest.skip("protocol v1b no longer carries anchor candidates")
    path = ROOT / candidates["evidence_path"]
    if not path.exists():
        pytest.skip("the anchors have not been computed on this checkout")
    receipt = json.loads(path.read_text(encoding="ascii"))
    assert candidates["evidence_sha256"] == _sha256(path)
    assert candidates["evidence_generated_at_utc"] == receipt["generated_at_utc"]
    assert receipt["status"] == "candidate_measurement" and "OI-08" in receipt["status_note"]
    assert candidates["unit_table_sha256"] == receipt["unit_table_sha256"]
    assert candidates["units_read"] == receipt["counts"]["units_read"]
    assert candidates["bangkok_khwaeng_units"] == receipt["alternatives_for_review"]["bangkok_khwaeng_units"]
    # A replaced receipt names the one it supersedes, and says whether the figures moved.
    assert candidates["superseded_evidence_sha256"] == receipt["supersedes"]["receipt_sha256"]
    assert receipt["supersedes"]["reason"].strip() and receipt["supersedes"]["all_same"] is True
    for rule in candidates["rules"]:
        source: Any = receipt
        for key in rule["receipt_key"].split("."):
            source = source[key]
        assert {key: source[key] for key in ("P5", "P10", "P75", "P90", "P95")} == rule["values"], rule["id"]
        assert rule["unit_count"] == source.get("unit_count", receipt["unit_count"]), rule["id"]
    khwaeng = receipt["alternatives_for_review"]
    assert khwaeng["without_bangkok_khwaeng"]["unit_count"] + khwaeng["bangkok_khwaeng_units"] == receipt["unit_count"]
