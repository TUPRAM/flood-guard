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
