"""Planning assessment overlay (plan 7.1, task E11): schema, strict validator, writer and the committed fixture.

Every overlay in this file is the committed fixture or a changed copy of it. The fixture is an invented case
with invented units (a fixture, not a place): no test here reads a flood layer, a population raster or a real
unit, and nothing is written under ``outputs/``. Where a test needs a candidate overlay, it relabels fixture
rows in memory as protocol case O2 (``_relabelled_as_case_o2``): the header and the flood input take the names
protocol v1a gives, the units stay invented, and nothing is written to the repository.

The round trip is: Python builds the fixture, the JSON schema and the strict validator accept it, Python
writes it, and the web parser reads the same bytes (``apps/web/src/lib/planning-assessment-overlay.test.ts``).
This file proves the Python half and that the committed bytes are the ones Python writes today; the web test
proves that TypeScript finds the same content (file hash, content digest and counts). The refusal cases are
one JSON file read by both test suites.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from floodguard import planning_overlay as po
from floodguard.confidence import (
    BASIS_VALUES,
    C4_FLOAT_GUARD_POINTS,
    COMPONENT_STATUSES,
    CONDITION_IDS,
    derive_confidence,
)
from floodguard.normalisation import frame_record, protocol_hashes
from floodguard.rights_basis import RIGHTS_BASIS_4009_PATH, load_rights_basis
from floodguard.scoring import ACTION_REASON_CODES, SCORE_COMPONENTS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A = DOCS / "planning_protocol_v1a.json"
V1B = DOCS / "planning_protocol_v1b.json"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
WEB_LIB = ROOT / "apps" / "web" / "src" / "lib"
FIXTURES = WEB_LIB / "__fixtures__"
FIXTURE = FIXTURES / "planning-assessment-overlay.fixture.json"
SUMMARY = FIXTURES / "planning-assessment-overlay.fixture.summary.json"
REFUSALS = FIXTURES / "planning-assessment-overlay.refusals.json"
BINDING_FILE = WEB_LIB / "planning-protocol-binding.json"
GENERATOR = ROOT / "apps" / "web" / "scripts" / "planning-overlay-fixture.py"
WEB_PARSER = WEB_LIB / "planning-assessment-overlay.ts"

CASES: list[dict[str, Any]] = json.loads(REFUSALS.read_text(encoding="ascii"))["cases"]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return po.load_overlay_schema(ROOT / po.SCHEMA_RELATIVE_PATH)


@pytest.fixture(scope="module")
def binding() -> po.ProtocolBinding:
    return po.load_protocol_binding(V1A, V1B, RECEIPTS)


@pytest.fixture(scope="module")
def v1a() -> dict[str, Any]:
    return json.loads(V1A.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("planning_overlay_fixture", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def overlay() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="ascii"))


def _row(overlay: dict[str, Any], key: str) -> dict[str, Any]:
    return next(row for row in overlay["rows"] if row["row_id"] == f"FX-CASE-01:{key}")


def _patched(overlay: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the steps of a refusal case (see the ``patch_format`` note in the refusals file)."""

    changed = deepcopy(overlay)
    for step in steps:
        target: Any = changed
        if "row" in step:
            target = next(row for row in changed["rows"] if row["row_id"] == step["row"])
        if "input" in step:
            target = next(item for item in changed["inputs"] if item["input_id"] == step["input"])
        *head, last = step["path"]
        for key in head:
            target = target[key]
        if step.get("delete"):
            del target[last]
        else:
            target[last] = step["set"]
    return changed


def _case(case_id: str) -> dict[str, Any]:
    return next(case for case in CASES if case["id"] == case_id)


def _codes(problems: list[po.OverlayProblem]) -> set[str]:
    return {problem.code for problem in problems}


def _relabelled_as_case_o2(overlay: dict[str, Any], binding: po.ProtocolBinding) -> dict[str, Any]:
    """The fixture's dated agency rows relabelled, in memory, as a candidate overlay of protocol case O2.

    The case header and the flood input take the names and the date protocol v1a gives; the units stay
    invented. It tests the candidate path of the validator. It is not a result for any place.
    """

    candidate = deepcopy(overlay)
    case = binding.cases["O2"]
    name = case.flood_inputs[0]
    candidate["dataset_mode"] = "candidate"
    candidate["case"].update(
        case_id=case.case_id, kind="portfolio_case", fixture_notice=None, case_reference_date=case.case_reference_date
    )
    flood = next(item for item in candidate["inputs"] if item["input_id"] == "fx_agency_extent_dated")
    flood.update(
        name=name,
        source_product=po.PRODUCT_4009_SOURCE,
        acquisition_date=binding.product_4009.dated_acquisition_date,
        licence=po.PRODUCT_4009_LICENCE,
        attribution=f"{po.PRODUCT_4009_CREDIT}, CC BY-SA 4.0",
        change_notice="Changed by FloodGuard: text of this test only.",
    )
    candidate["rows"] = [
        row
        for row in candidate["rows"]
        if row["tier"] == "T3" and row["lineage"]["flood_input_id"] == flood["input_id"]
    ]
    for row in candidate["rows"]:
        row["flood_input"] = name
        row["confidence"]["flood_input"] = name
        row["confidence"]["measurements"].update(
            acquisition_date=flood["acquisition_date"], case_reference_date=case.case_reference_date, recency_days=0
        )
    return candidate


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------


def test_schema_is_a_valid_closed_draft_2020_12_schema(schema: dict[str, Any]) -> None:
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == po.SCHEMA_ID
    Draft202012Validator.check_schema(schema)
    raw = (ROOT / po.SCHEMA_RELATIVE_PATH).read_bytes()
    assert b"\r" not in raw and raw.isascii()

    # Every object that lists properties is closed and requires all of them: an absent value is written as null.
    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "properties" in node and node.get("type") == "object":
                assert node.get("additionalProperties") is False, path
                assert sorted(node["required"]) == sorted(node["properties"]), path
            for key, value in node.items():
                if key not in ("if", "then", "else", "allOf"):
                    walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(schema, "$")


def test_schema_vocabularies_are_those_of_the_signed_protocol_and_the_modules(
    schema: dict[str, Any], v1a: dict[str, Any]
) -> None:
    defs = schema["$defs"]
    tier_model = v1a["evidence_tier_model"]
    assert defs["tier"]["enum"] == [row["tier"] for row in tier_model["tiers"]] == list(po.TIERS)
    assert sorted(defs["lane"]["enum"]) == sorted(row["lane"] for row in tier_model["lanes"]) == sorted(po.LANES)
    assert {row["tier"]: (row["lane"],) for row in tier_model["tiers"] if row["tier"] != "T1"} == {
        tier: lanes for tier, lanes in po.TIER_LANES.items() if tier != "T1"
    }
    relations = v1a["date_rule"]["temporal_relation_values"]
    assert defs["temporalRelation"]["enum"] == relations == list(po.TEMPORAL_RELATIONS)
    rule = v1a["class_rules"]["v1"]
    reason_codes = [*rule["reason_codes"], *rule["added_reason_code"]]
    assert defs["actionReasonCode"]["enum"] == reason_codes == list(po.REASON_CODES)
    assert list(po.REASON_CODES[:-1]) == list(ACTION_REASON_CODES)
    assert defs["actionClass"]["enum"] == list(rule["class_names"]) == list(po.ACTION_CLASSES)
    assert {name: rule["reason_codes"][code] for name, code in po.REASON_BY_CLASS.items()} == {
        name: f"Class {name}." for name in po.CLASSES_ABOVE_E
    }
    assert defs["basisValue"]["enum"] == list(BASIS_VALUES)
    conditions = [row["id"] for row in v1a["confidence_rule_v1"]["medium_requires_all"]]
    assert defs["conditionId"]["enum"] == list(CONDITION_IDS) == conditions
    assert defs["componentName"]["enum"] == list(SCORE_COMPONENTS) == list(v1a["scoring_frame"]["weights"])
    statuses = defs["derivedConfidence"]["properties"]["measurements"]["properties"]["component_status"]["properties"]
    assert all(statuses[name]["enum"] == list(COMPONENT_STATUSES) for name in SCORE_COMPONENTS)
    # high is in the scorer's vocabulary, and the overlay never assigns it: it requires the locked tier T4.
    vocabulary = v1a["confidence_rule_v1"]["vocabulary"]
    assert defs["assignedConfidenceClass"]["enum"] == [name for name in reversed(vocabulary) if name != "high"]
    guardrails = {row["id"]: row for row in v1a["guardrails"]}
    levels = guardrails["GR6_publication_eligibility"]["values"]
    assert defs["publicationLevel"]["enum"] == levels == list(po.PUBLICATION_LEVELS)
    headline = defs["headlineStability"]["properties"]
    assert headline["guardrail"]["const"] == po.GUARDRAIL_GR8 == "GR8_headline_stability"
    retention_min = guardrails["GR8_headline_stability"]["parameters"]["class_retention_min"]
    assert headline["class_retention_min"]["const"] == retention_min
    v2 = v1a["class_rules"]["v2"]
    class_v2 = defs["classV2"]["properties"]
    assert class_v2["label"]["const"] == v2["label_when_shown"]
    assert class_v2["binding"]["const"] is v2["binding"] is False
    assert class_v2["class_rule_version"]["const"] == v2["version"]
    assert v2["evaluation"]["otherwise"] == po.NO_V2_TRIGGER and po.NO_V2_TRIGGER in class_v2["result"]["enum"]
    assert tuple(v2["evaluation"]["order"]) == po.V2_TRIGGER_ORDER
    assert v2["parameters"]["fpps_min"] == po.V2_FPPS_MIN
    assert v2["parameters"]["exposure_floor_for_non_e"] == po.V2_EXPOSURE_FLOOR_FOR_NON_E
    top = schema["properties"]
    assert top["official_warning"]["const"] is v1a["official_warning"] is False
    assert top["operational_status"]["const"] == v1a["operational_status"] == "non_operational"
    assert top["accepted_fpps"] == top["accepted_action_class"] == {"type": "null"}
    row_fields = defs["row"]["properties"]
    assert row_fields["accepted_fpps"] == row_fields["accepted_action_class"] == {"type": "null"}
    assert top["normalisation_version"]["const"] == v1a["scoring_frame"]["version"]
    assert top["confidence_rule_version"]["const"] == v1a["confidence_rule_v1"]["version"]
    assert top["class_rule_version"]["const"] == rule["version"]
    assert top["evidence_tier_model_version"]["const"] == tier_model["version"]


def test_schema_pins_the_signed_numbers(
    schema: dict[str, Any], v1a: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    defs = schema["$defs"]

    def constants(node: dict[str, Any]) -> dict[str, Any]:
        assert all(set(value) == {"const"} for value in node["properties"].values())
        return {name: value["const"] for name, value in node["properties"].items()}

    frame = v1a["scoring_frame"]
    header = frame_record(binding.frame)
    # Decision D4 and v1a scoring_frame: the weights, their leave-one-out sets, the flood anchor, the lane sentence.
    assert constants(defs["weights"]) == frame["weights"] == header["weights"]
    frame_node = defs["scoringFrame"]["properties"]
    assert frame_node["weights"] == {"$ref": "#/$defs/weights"}
    assert frame_node["flood_anchor"]["const"] == frame["components"]["flood_likelihood_0_100"]["anchor"] == 0.2
    assert frame_node["lane_disclosure"]["const"] == frame["lane_disclosure"]
    left_out = frame_node["leave_one_component_out_weights"]["properties"]
    assert {name: constants(left_out[name]) for name in SCORE_COMPONENTS} == header["leave_one_component_out_weights"]
    assert all(left_out[name]["properties"][name]["const"] == 0 for name in SCORE_COMPONENTS)
    # Guardrail GR1 and confidence rule v1: 100 residents, and the thresholds 3 / 0.8 / 15 / 0.2 / 100 / 0.1 / 1.
    guardrails = {row["id"]: row for row in v1a["guardrails"]}
    minimum = guardrails["GR1_minimum_denominators"]["parameters"]["unit_residents_min_for_class"]
    assert defs["guardrailGr1"]["properties"]["unit_residents_min_for_class"]["const"] == minimum == 100
    conditions = {row["id"]: row.get("threshold", {}) for row in v1a["confidence_rule_v1"]["medium_requires_all"]}
    expected = {key: value for threshold in conditions.values() for key, value in threshold.items()}
    expected["exposure_plus_minus_one_pixel_float_guard_points"] = C4_FLOAT_GUARD_POINTS
    assert constants(defs["derivedConfidence"]["properties"]["thresholds"]) == expected
    assert [expected[name] for name in defs["derivedConfidence"]["properties"]["thresholds"]["required"]] == [
        3, 0.8, 15, 1e-9, 0.2, 100, 0.1, 1,
    ]
    assert constants(defs["t2SkillCondition"]["properties"]["thresholds"]) == v1a["t2_skill_bar"]["conditions"]
    # by_construction is recorded for C3 only, by_scenario_declaration for C1 and C2 only (v1a basis_record).
    basis = defs["derivedConfidence"]["properties"]["basis"]["properties"]
    for name in CONDITION_IDS:
        allowed = set(basis[name].get("enum") or defs["passFail"]["enum"])
        assert ("by_construction" in allowed) == (name == "C3_coverage"), name
        assert ("by_scenario_declaration" in allowed) == (name in ("C1_tier", "C2_recency")), name
        assert {"pass", "fail"} <= allowed <= set(BASIS_VALUES)


def test_closure_rule_vocabulary_is_that_of_protocol_v1b(schema: dict[str, Any]) -> None:
    rule = json.loads(V1B.read_text(encoding="utf-8"))["closure_rule_v1"]
    closure = schema["$defs"]["closureRule"]["properties"]
    assert closure["version"]["const"] == rule["version"]
    assert closure["level"]["enum"] == list(rule["levels"])
    assert f"closure_basis: {po.CLOSURE_BASIS_PREFIX}<input>" in rule["closure_is_an_assumption"]
    assert closure["closure_basis"]["pattern"] == f"^{po.CLOSURE_BASIS_PREFIX}.+"


def test_product_4009_wording_is_the_signed_wording(
    schema: dict[str, Any], v1a: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    rights = load_rights_basis(ROOT / RIGHTS_BASIS_4009_PATH)
    assert po.PRODUCT_4009_CREDIT == v1a["wording"]["product_4009_credit"] == rights["required_attribution_text"]
    assert po.PRODUCT_4009_LICENCE == rights["licence"]["name"]
    assert po.PRODUCT_4009_EVENT_CODE == rights["product"]["event_code"]
    assert po.PRODUCT_4009_EVENT_CODE in po.PRODUCT_4009_CREDIT
    product = v1a["date_rule"]["product_4009"]
    assert po.PRODUCT_4009_LAYER_NAMES == (product["accumulated_layer"]["layer"], product["layer_22_oct"]["layer"])
    assert rights["product"]["layer_in_scope"] == po.PRODUCT_4009_LAYER_NAMES[0]
    layers = binding.product_4009
    assert layers.accumulated_names == (po.PRODUCT_4009_LAYER_NAMES[0], "UNOSAT/GISTDA product 4009, accumulated layer")
    assert layers.dated_names == (po.PRODUCT_4009_LAYER_NAMES[1], "UNOSAT/GISTDA product 4009, 22 Oct 2024 layer")
    assert layers.dated_acquisition_date == product["layer_22_oct"]["case_reference_date"] == "2024-10-22"
    assert re.fullmatch(schema["$defs"]["productId"]["pattern"], po.PRODUCT_4009_SOURCE)


# ---------------------------------------------------------------------------
# The protocol binding the web parser reads
# ---------------------------------------------------------------------------


def test_binding_file_is_what_python_writes_today_from_the_protocols_in_force(
    generator, binding: po.ProtocolBinding, v1a: dict[str, Any]
) -> None:
    committed = BINDING_FILE.read_bytes()
    assert b"\r" not in committed and committed.isascii()
    assert generator.binding_text() == committed.decode("ascii")
    record = json.loads(committed)
    assert record == po.protocol_binding_record(binding)
    in_force = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (("v1a", V1A), ("v1b", V1B))}
    assert record["protocol_sha256"] == in_force == protocol_hashes(binding.frame)
    assert record["scoring_frame"] == frame_record(binding.frame)
    assert record["class_rule_v1"]["rules"] == v1a["class_rules"]["v1"]["rules"]
    portfolio = v1a["case_portfolio"]
    assert [case["id"] for case in record["cases"]] == [case["id"] for case in portfolio["cases"]]
    for stated, case in zip(record["cases"], portfolio["cases"]):
        assert stated == {
            "id": case["id"],
            "case_reference_date": case["case_reference_date"],
            "lane": case["lane"],
            "tier": case["tier"],
            "flood_inputs": case["flood_inputs"],
        }
    assert record["cut_cases"] == portfolio["cut_now"]
    assert record["cases_without_class"] == list(po.CASES_WITHOUT_CLASS) == ["SE2-dist"]
    assert "no FPPS and no class" in next(case for case in portfolio["cases"] if case["id"] == "SE2-dist")["note"]
    by_construction = record["confidence_rule"]["coverage_by_construction"]
    assert by_construction["units"] == portfolio["mae_sai_reporting_frame"]["units"]
    # The record holds constants only: no row, no score and no class for any unit.
    assert not {"rows", "fpps_0_100", "action_class"} & set(re.findall(r'"([a-z0-9_]+)":', committed.decode("ascii")))


def test_web_parser_reads_the_binding_file_and_no_other_protocol_constant() -> None:
    source = WEB_PARSER.read_text(encoding="utf-8")
    assert 'import protocolBinding from "./planning-protocol-binding.json";' in source
    # The signed numbers are read from the binding: the parser source does not restate them.
    for number in ("0.35714285714285715", "0.454083", "0.351416"):
        assert number not in source
    assert not re.search(r"[0-9a-f]{64}", source)


# ---------------------------------------------------------------------------
# The fixture: Python writes, the schema validates
# ---------------------------------------------------------------------------


def test_committed_fixture_is_what_python_writes_today(generator) -> None:
    committed = FIXTURE.read_bytes()
    assert b"\r" not in committed and committed.isascii()
    text = generator.fixture_text()
    assert text == committed.decode("ascii")
    assert generator.summary_text(text) == SUMMARY.read_bytes().decode("ascii")
    summary = json.loads(SUMMARY.read_text(encoding="ascii"))
    assert summary["file_sha256"] == hashlib.sha256(committed).hexdigest()
    assert summary["summary"] == po.summarise_overlay(json.loads(committed))


def test_fixture_is_accepted_by_the_schema_alone_and_by_the_strict_validator(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    assert list(Draft202012Validator(schema).iter_errors(overlay)) == []
    assert po.overlay_problems(overlay, schema) == []
    assert po.overlay_problems(overlay, schema, binding=binding) == []
    po.validate_overlay(overlay, schema, binding=binding)
    assert po.load_overlay(FIXTURE, schema, binding=binding) == overlay


def test_writing_and_loading_round_trip_byte_for_byte(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding, tmp_path: Path
) -> None:
    committed = FIXTURE.read_bytes()
    assert po.overlay_text(overlay, schema, binding=binding).encode("ascii") == committed
    target = tmp_path / "overlay.json"
    written = po.write_overlay(overlay, target, schema, binding=binding)
    assert target.read_bytes() == committed
    assert written == {"path": str(target), "bytes": len(committed), "sha256": hashlib.sha256(committed).hexdigest()}
    assert po.load_overlay(target, schema, binding=binding) == overlay
    assert po.content_sha256(po.load_overlay(target, schema)) == po.content_sha256(overlay)


def test_fixture_is_an_invented_case_and_names_no_real_unit_or_flood_input(
    overlay: dict[str, Any], v1a: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    assert overlay["dataset_mode"] == "fixture_demo" and overlay["case"]["kind"] == "fixture"
    assert po.FIXTURE_LABEL in overlay["case"]["fixture_notice"]
    assert overlay["official_warning"] is False and overlay["operational_status"] == "non_operational"
    assert overlay["can_feed_decision_layer"] is False
    assert overlay["accepted_fpps"] is None and overlay["accepted_action_class"] is None
    assert overlay["source_timestamp"] and overlay["generated_at"] and len(overlay["assumptions"]) >= 5
    for row in overlay["rows"]:
        assert re.fullmatch(r"FX-[UE][0-9]{2}", row["unit_id"]), row["row_id"]
        assert po.FIXTURE_LABEL in row["unit_name_en"] and re.search("[฀-๿]", row["unit_name_th"])
        assert row["accepted_fpps"] is None and row["accepted_action_class"] is None
        assert row["source_timestamp"] and row["assumptions"]
    text = FIXTURE.read_text(encoding="ascii")
    assert not re.search(r"TH[0-9]{6}", text)
    portfolio = v1a["case_portfolio"]
    real_names = {name for case in portfolio["cases"] for name in case["flood_inputs"]}
    real_names |= {*v1a["t2_skill_bar"]["declared_unable_to_meet"], *v1a["t2_skill_bar"]["evaluated_by_the_rule"]}
    real_names |= {v1a["date_rule"]["product_4009"][key]["layer"] for key in ("accumulated_layer", "layer_22_oct")}
    used = {row["flood_input"] for row in overlay["rows"]} | {item["name"] for item in overlay["inputs"]}
    assert not used & real_names
    assert overlay["case"]["case_id"] not in binding.cases and overlay["case"]["case_id"] not in binding.cut_cases
    assert not po.cites_product_4009(overlay) and "4009" not in text
    assert {item["source_product"] for item in overlay["inputs"]} == {"fixture_invented_input"}
    # Invented dates only: every acquisition and reference date is in 2030.
    dates = {
        row["confidence"]["measurements"][key]
        for row in overlay["rows"]
        if row["confidence"] and "measurements" in row["confidence"]
        for key in ("acquisition_date", "case_reference_date")
    }
    dates |= {item["acquisition_date"] for item in overlay["inputs"]}
    assert dates - {None} and all(value.startswith("2030-") for value in dates - {None})


def test_fixture_carries_real_text_only_where_the_signed_protocols_put_it(
    overlay: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    """The fixture's notice may not claim more than is true: the frame header and the hashes are real."""

    header = frame_record(binding.frame)
    hashes = protocol_hashes(binding.frame)
    assert overlay["scoring_frame"] == header and overlay["protocol_sha256"] == hashes
    notice = overlay["case"]["fixture_notice"]
    assert "are those of the signed protocols" in notice and "every unit, input, date and number" not in notice
    assert any("They describe the protocol, not a unit of this file." in line for line in overlay["assumptions"])
    assert not any("every unit, flood input, date and number is invented" in line for line in overlay["assumptions"])

    # What is real in the file, exactly: frame text (which names real tambons), the national anchors, the hashes.
    real_text = (
        header["flood_anchor_disclosure"],
        header["normalisation_rule"],
        header["lane_disclosure"],
        header["permanent_water"]["source"],
        binding.frame.vulnerability_caveat,
        *binding.frame.definitions.values(),
        header["vulnerability_anchor_receipt_sha256"],
        *hashes.values(),
    )
    assert "Mae Sai" in header["flood_anchor_disclosure"]
    text = FIXTURE.read_text(encoding="ascii")
    stripped = text
    for value in real_text:
        encoded = json.dumps(value, ensure_ascii=True)[1:-1]
        assert encoded in stripped, value
        stripped = stripped.replace(encoded, "")
    # With that text removed, no real place, product or detector is named, and no other SHA-256 of a real file.
    real_names = r"Mae Sai|Chiang Rai|Rim Kok|Hat Yai|GISTDA|UNOSAT|WorldPop|WorldCover|Sentinel|ALOS"
    assert not re.search(real_names, stripped)
    invented_hashes = {item["sha256"] for item in overlay["inputs"]}
    assert set(re.findall(r"[0-9a-f]{64}", stripped)) == invented_hashes
    # The national anchors appear in the frame header and in the vulnerability records, which echo them.
    anchors = header["vulnerability_anchors"]["values"]
    for row in overlay["rows"]:
        record = row["components"]["vulnerability_context_0_100"]
        if record is not None and "anchors" in record:
            stated = record["anchors"]
            assert (stated["lower_value"], stated["upper_value"]) == (anchors["P10"], anchors["P90"])


def test_fixture_hashes_are_those_of_the_protocols_in_force(overlay: dict[str, Any]) -> None:
    in_force = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (("v1a", V1A), ("v1b", V1B))}
    assert overlay["protocol_sha256"] == in_force == overlay["scoring_frame"]["protocol_sha256"]
    for row in overlay["rows"]:
        for record in row["components"].values():
            if record is not None and "protocol_sha256" in record:
                assert record["protocol_sha256"] == in_force
        if row["confidence"] and "protocol_v1a_sha256" in row["confidence"]:
            assert row["confidence"]["protocol_v1a_sha256"] == in_force["v1a"]


def _across(by_column: dict[str, dict[str, int]]) -> dict[str, int]:
    """Add the counts of every lane column. Used only to ask whether the fixture shows a state at all."""

    out: dict[str, int] = {}
    for counts in by_column.values():
        for key, count in counts.items():
            out[key] = out.get(key, 0) + count
    return out


def test_fixture_exercises_every_tier_reason_code_condition_and_outcome(overlay: dict[str, Any]) -> None:
    summary = po.summarise_overlay(overlay)

    def unused(counts: dict[str, int], keys: tuple[str, ...]) -> list[str]:
        return [key for key in keys if not counts[key]]

    assert unused(summary["rows_by_tier"], po.TIERS) == []
    assert unused(summary["rows_by_lane"], po.LANES) == []
    assert unused(summary["rows_by_temporal_relation"], po.TEMPORAL_RELATIONS) == []
    assert unused(_across(summary["reason_code_by_lane_column"]), po.REASON_CODES) == []
    assert unused(summary["binding_class_by_lane_column"]["OBS"], po.ACTION_CLASSES) == []
    assert unused(summary["binding_class_by_lane_column"]["ENG"], po.ACTION_CLASSES) == []
    assert unused(_across(summary["would_be_class_by_lane_column"]), po.ACTION_CLASSES) == []
    assert unused(_across(summary["v2_result_by_lane_column"]), (*po.ACTION_CLASSES, po.NO_V2_TRIGGER)) == []
    assert unused(_across(summary["failed_conditions_by_lane_column"]), CONDITION_IDS) == []
    headline_statuses = (po.HEADLINE_NOT_EVALUATED, po.HEADLINE_ELIGIBLE, po.HEADLINE_UNSTABLE)
    assert unused(_across(summary["headline_status_by_lane_column"]), headline_statuses) == []
    assert unused(summary["inputs_by_rights_level"], po.PUBLICATION_LEVELS) == []
    assert unused(summary["rows_by_confidence_kind"], ("observed", "scenario", po.KIND_DECLARED)) == []
    assert summary["rows_under_gr1"] == 1 and summary["obs_rows_not_event_aligned"] == 1
    # The two states a fixture cannot show (see the generator's docstring): C3 by construction is granted to
    # product 4009 in the eight Mae Sai tambons only, and only two named detectors can pass the T2 skill condition.
    assert _across(summary["basis_values_by_lane_column"])["by_construction"] == 0
    assert summary["basis_values_by_lane_column"]["SCN"]["by_scenario_declaration"] > 0
    assert summary["basis_values_by_lane_column"]["OBS"]["by_scenario_declaration"] == 0
    t2_rows = [row for row in overlay["rows"] if row["tier"] == "T2"]
    assert t2_rows and all(row["confidence"]["t2_skill_condition"]["passes"] is False for row in t2_rows)
    assert all(row["action_class"] == "E" and row["action_reason_code"] == "low_confidence" for row in t2_rows)


def test_summary_counts_classes_and_confidence_per_lane_column_and_never_across(overlay: dict[str, Any]) -> None:
    """v1a: scenario classes are counted only in the SCN column; engine classes are never an observed or
    scenario distribution; scenario confidence is never counted as observed confidence."""

    summary = po.summarise_overlay(overlay)
    assert po.LANE_COLUMNS == ("OBS", "SCN", "ENG", "no_lane")
    lanes = ("OBS", "SCN", "SCN-ENV", "ENG", None)
    assert [po.lane_column(lane) for lane in lanes] == ["OBS", "SCN", "SCN", "ENG", "no_lane"]
    rows = overlay["rows"]
    for name, value in (
        ("binding_class_by_lane_column", lambda row: row["action_class"]),
        ("would_be_class_by_lane_column", lambda row: row["would_be_class"]),
        ("reason_code_by_lane_column", lambda row: row["action_reason_code"]),
        ("confidence_class_by_lane_column", lambda row: row["confidence"] and row["confidence"]["confidence_class"]),
    ):
        assert tuple(summary[name]) == po.LANE_COLUMNS, name
        for column in po.LANE_COLUMNS:
            own = [row for row in rows if po.lane_column(row["lane"]) == column]
            assert sum(summary[name][column].values()) == len(own), (name, column)
            for key, count in summary[name][column].items():
                expected = sum(1 for row in own if (value(row) or "none") == key)
                assert count == expected, (name, column, key)
    scenario_rows = summary["rows_by_lane"]["SCN"] + summary["rows_by_lane"]["SCN-ENV"]
    assert sum(summary["binding_class_by_lane_column"]["SCN"].values()) == scenario_rows == 4
    assert summary["binding_class_by_lane_column"]["no_lane"] == {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "none": 1}
    assert tuple(summary["failed_conditions_by_lane_column"]) == ("OBS", "SCN")
    assert tuple(summary["basis_values_by_lane_column"]) == ("OBS", "SCN")
    # No key of the summary holds a class or confidence count across the columns.
    across = r"rows_by_(binding_class|would_be_class|confidence_class|reason_code|v2_result)"
    merged = [key for key in summary if re.match(across, key)]
    assert merged == [] and "failed_condition_counts" not in summary and "basis_value_counts" not in summary


def test_fixture_shows_each_guardrail_outcome(overlay: dict[str, Any]) -> None:
    small = _row(overlay, "obs-t3-c6-gr1-no-class")
    assert small["confidence"]["measurements"]["unit_residents"] < 100
    scored_on = small["components"]["exposure_0_100"]["inputs"]["unit_residents"]
    assert small["confidence"]["measurements"]["unit_residents"] == scored_on
    assert small["action_class"] is None and small["would_be_class"] is None
    assert small["action_reason_code"] == "insufficient_denominator"
    assert small["class_v2"]["result"] is None and small["class_v2"]["trigger_evidence"] == []
    assert small["confidence"]["confidence_class"] == "low"
    assert small["confidence"]["failed_conditions"] == ["C6_residents"]
    assert all(entry["action_class"] is None for entry in small["leave_one_component_out"].values())

    late = _row(overlay, "obs-t3-c2-not-event-aligned")
    assert (late["lane"], late["temporal_relation"]) == ("OBS", "dated_other")
    assert (late["action_class"], late["would_be_class"]) == ("E", "B")
    assert late["confidence"]["failed_conditions"] == ["C2_recency"]

    no_trigger = _row(overlay, "obs-t3-no-v2-trigger")["class_v2"]
    assert (no_trigger["label"], no_trigger["binding"], no_trigger["result"]) == ("secondary", False, "no_v2_trigger")
    assert [item["trigger"] for item in no_trigger["trigger_evidence"]] == list(po.V2_TRIGGER_ORDER)
    assert not any(item["met"] for item in no_trigger["trigger_evidence"])

    assert _row(overlay, "obs-t3-class-a")["headline_stability"]["status"] == po.HEADLINE_ELIGIBLE
    assert _row(overlay, "obs-t3-class-b")["headline_stability"]["status"] == po.HEADLINE_UNSTABLE
    assert _row(overlay, "obs-t3-class-c")["headline_stability"] == {
        "guardrail": "GR8_headline_stability",
        "status": po.HEADLINE_NOT_EVALUATED,
        "class_retention": None,
        "class_retention_min": 0.6,
    }

    missing = _row(overlay, "obs-t3-c5-component-not-computed")
    assert missing["components"]["access_gap_0_100"] is None and missing["components"]["road_criticality_0_100"] is None
    assert (missing["fpps_0_100"], missing["action_class"]) == (None, "E")
    assert missing["would_be_class"] is None and missing["leave_one_component_out"] is None
    assert any("is not computed" in line for line in missing["assumptions"])

    locked = _row(overlay, "t4-locked")
    assert locked["tier"] == "T4" and locked["lane"] is None and locked["confidence"] is None
    assert all(value is None for value in locked["components"].values())

    scenario = _row(overlay, "scn-env-t1-class-c")
    assert scenario["confidence"]["confidence_kind"] == "scenario" and scenario["temporal_relation"] == "season_window"
    basis = scenario["confidence"]["basis"]
    assert basis["C1_tier"] == basis["C2_recency"] == "by_scenario_declaration"
    assert scenario["action_class"] == "C" and scenario["scenario"]["declaration"]
    disclosure = overlay["scoring_frame"]["lane_disclosure"]
    assert disclosure.startswith("One flood input drives 4 of 5 components (90% of weight)")
    pitch = _row(overlay, "obs-t3-class-d")["components"]["access_gap_0_100"]
    assert pitch["publication_level"] == "pitch" and overlay["publication_eligibility"] == "local"


def test_every_derived_row_follows_from_what_it_echoes(overlay: dict[str, Any], binding: po.ProtocolBinding) -> None:
    """The validator's own reading of rule v1 gives what ``confidence.derive_confidence`` gave for every row."""

    inputs = {item["input_id"]: item for item in overlay["inputs"]}
    derived = [
        row for row in overlay["rows"] if row["confidence"] and row["confidence"]["confidence_kind"] != "declared"
    ]
    assert len(derived) == 19
    for row in derived:
        record = row["confidence"]
        assert po.expected_basis(record) == record["basis"], row["row_id"]
        assert derive_confidence(po._confidence_inputs(record), binding.rule) == record, row["row_id"]
        window = record["thresholds"]["recency_window_days"]
        assert po.expected_temporal_relation(record["measurements"], window) == row["temporal_relation"], row["row_id"]
        flood = inputs[row["lineage"]["flood_input_id"]]
        assert flood["acquisition_date"] == record["measurements"]["acquisition_date"], row["row_id"]
        assert row["lineage"]["closure_rule"]["closure_basis"] == f"modelled_from_{flood['input_id']}"
    assert {item["acquisition_date"] for item in overlay["inputs"] if item["role"] != "flood_input"} == {None}


# ---------------------------------------------------------------------------
# A candidate overlay: the protocol binding is required, and the case is the protocol's case
# ---------------------------------------------------------------------------


def test_a_candidate_overlay_needs_the_protocol_binding_everywhere(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding, tmp_path: Path
) -> None:
    candidate = _relabelled_as_case_o2(overlay, binding)
    assert len(candidate["rows"]) == 12 and po.cites_product_4009(candidate)
    assert po.overlay_problems(candidate, schema, binding=binding) == []
    assert _codes(po.overlay_problems(candidate, schema)) == {po.PROTOCOL_BINDING_REQUIRED}
    for call in (
        lambda: po.validate_overlay(candidate, schema),
        lambda: po.overlay_text(candidate, schema),
        lambda: po.write_overlay(candidate, tmp_path / "candidate.json", schema),
    ):
        with pytest.raises(po.PlanningOverlayError) as refused:
            call()
        assert refused.value.codes == (po.PROTOCOL_BINDING_REQUIRED,)
    assert list(tmp_path.iterdir()) == []
    target = tmp_path / "candidate.json"
    po.write_overlay(candidate, target, schema, binding=binding)
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.load_overlay(target, schema)
    assert refused.value.codes == (po.PROTOCOL_BINDING_REQUIRED,)
    assert po.load_overlay(target, schema, binding=binding) == candidate
    # A leftover fixture notice on a portfolio case is refused by the schema.
    candidate["case"]["fixture_notice"] = "left over"
    assert _codes(po.overlay_problems(candidate, schema, binding=binding)) == {po.STRUCTURE}


def test_a_candidate_reaches_the_public_folder_only_with_the_binding(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding, tmp_path: Path
) -> None:
    """Guardrail GR2 and v1a change control: a real-case overlay is never written unchecked."""

    public_folder = tmp_path / "apps" / "web" / "public" / "planning-assessments"
    public_folder.mkdir(parents=True)
    candidate = _relabelled_as_case_o2(overlay, binding)
    for item in candidate["inputs"]:
        item["rights_level"] = "public"
    candidate["publication_eligibility"] = "public"
    candidate["rows"] = [
        row
        for row in candidate["rows"]
        if (row["components"]["access_gap_0_100"] or {}).get("publication_level") != "pitch"
    ]
    rights = load_rights_basis(ROOT / RIGHTS_BASIS_4009_PATH)
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(candidate, public_folder / "o2.json", schema, rights_basis_4009=rights)
    assert refused.value.codes == (po.PROTOCOL_BINDING_REQUIRED,)
    # The reviewed bypass: weights of 0.2 each, all inputs public, no binding. It is refused before any write.
    for name in SCORE_COMPONENTS:
        candidate["scoring_frame"]["weights"][name] = 0.2
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(candidate, public_folder / "o2.json", schema, rights_basis_4009=rights)
    assert {po.PROTOCOL_BINDING_REQUIRED, po.STRUCTURE} <= set(refused.value.codes)
    assert list(public_folder.iterdir()) == []


def test_case_header_is_the_case_protocol_v1a_describes(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    def problems(change) -> list[po.OverlayProblem]:
        candidate = _relabelled_as_case_o2(overlay, binding)
        change(candidate)
        return po.overlay_problems(candidate, schema, binding=binding)

    def paths(found: list[po.OverlayProblem]) -> set[str]:
        return {re.sub(r"\[[0-9]+\]", "[]", item.path) for item in found if item.code == po.CASE_NOT_PROTOCOL_CASE}

    # Another reference date than the one v1a gives case O2.
    moved = problems(lambda item: item["case"].update(case_reference_date="2030-01-10"))
    assert paths(moved) == {"$.case.case_reference_date"}
    # A case v1a cut, a name it never had, and the case the schema cannot carry (no FPPS and no class).
    for case_id in ("Phayao", "NOT-A-CASE", "SE2-dist"):
        found = problems(lambda item, case_id=case_id: item["case"].update(case_id=case_id))
        assert paths(found) == {"$.case.case_id"}, case_id
    assert "cut" in next(item.message for item in problems(lambda item: item["case"].update(case_id="Phayao")))
    distribution = problems(lambda item: item["case"].update(case_id="SE2-dist"))
    assert "no FPPS and no class" in next(item.message for item in distribution)
    # Case O1 is the own-candidate case (tier T2, reference 15 Sep): the 22 Oct agency layer is not its input.
    as_o1 = problems(lambda item: item["case"].update(case_id="O1"))
    assert paths(as_o1) == {"$.case.case_reference_date", "$.rows[].tier", "$.rows[].flood_input"}
    # Case SE1 is a season-envelope case: v1a gives it no observed row.
    assert "$.rows[].lane" in paths(problems(lambda item: item["case"].update(case_id="SE1")))
    # A fixture does not carry the id of a protocol case, with or without the label.
    fixture_named_o2 = deepcopy(overlay)
    fixture_named_o2["case"]["case_id"] = "O2"
    assert _codes(po.overlay_problems(fixture_named_o2, schema, binding=binding)) == {po.CASE_NOT_PROTOCOL_CASE}


def test_the_22_oct_layer_cannot_be_redated_to_be_event_aligned_in_september(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    """v1a date_rule: against a September reference date the 22 Oct layer is dated_other."""

    september = "2024-09-15"
    restated = _relabelled_as_case_o2(overlay, binding)
    restated["case"]["case_reference_date"] = september
    flood = next(item for item in restated["inputs"] if item["source_product"] == po.PRODUCT_4009_SOURCE)
    flood["acquisition_date"] = september
    for row in restated["rows"]:
        row["confidence"]["measurements"].update(acquisition_date=september, case_reference_date=september)
    found = po.overlay_problems(restated, schema, binding=binding)
    layer = [item for item in found if item.code == po.PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER]
    assert [item.path for item in layer] == ["$.inputs[0].acquisition_date"] and "2024-10-22" in layer[0].message
    assert po.CASE_NOT_PROTOCOL_CASE in _codes(found)

    # The accumulated layer has no single date and is used in lane SCN-ENV only.
    accumulated = _relabelled_as_case_o2(overlay, binding)
    flood = next(item for item in accumulated["inputs"] if item["source_product"] == po.PRODUCT_4009_SOURCE)
    flood["name"] = binding.product_4009.accumulated_names[1]
    for row in accumulated["rows"]:
        row["flood_input"] = row["confidence"]["flood_input"] = flood["name"]
    found = po.overlay_problems(accumulated, schema, binding=binding)
    layer = [item for item in found if item.code == po.PRODUCT_4009_LAYER_NOT_PROTOCOL_LAYER]
    paths = {re.sub(r"\[[0-9]+\]", "[]", item.path) for item in layer}
    assert paths == {"$.inputs[].acquisition_date", "$.rows[].lane"}


def test_the_schema_does_not_carry_a_row_with_two_components_and_no_class(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    """v1a case SE2-dist: flood likelihood and exposure only, no routing, no FPPS and no class.

    The protocols do not say whether that case is an overlay. Schema 1.0 does not carry it, and the validator
    refuses the nearest forms instead of letting the 124 units be written as class E. This is an open point for
    the owners (docs/planning_assessment_overlay.md).
    """

    shaped = deepcopy(overlay)
    row = _row(shaped, "scn-env-t1-class-c")
    for name in ("access_gap_0_100", "road_criticality_0_100", "vulnerability_context_0_100"):
        row["components"][name] = None
        row["confidence"]["measurements"]["component_status"][name] = "not_computed"
    row["lineage"].update(routing_context_id=None, closure_rule=None)
    row.update(fpps_0_100=None, action_class=None, action_reason_code=None, would_be_class=None,
               class_v2=None, leave_one_component_out=None)
    assert next(Draft202012Validator(schema).iter_errors(shaped), None) is not None
    assert po.STRUCTURE in _codes(po.overlay_problems(shaped, schema, binding=binding))
    renamed = _relabelled_as_case_o2(overlay, binding)
    renamed["case"]["case_id"] = "SE2-dist"
    found = [item for item in po.overlay_problems(renamed, schema, binding=binding) if item.path == "$.case.case_id"]
    assert [item.code for item in found] == [po.CASE_NOT_PROTOCOL_CASE]
    assert f"schema {po.SCHEMA_VERSION} does not carry it" in found[0].message


# ---------------------------------------------------------------------------
# Refusals (the cases are shared with the web test)
# ---------------------------------------------------------------------------


def test_refusal_cases_cover_the_named_refusals_and_every_shared_code() -> None:
    assert len({case["id"] for case in CASES}) == len(CASES)
    refused = {case["refuses"] for case in CASES}
    named = {
        po.UNKNOWN_TIER,
        po.CLASS_ABOVE_E_WITHOUT_MEDIUM_CONFIDENCE,
        po.ACCEPTED_VALUE_NOT_NULL,
        po.TEMPORAL_HONESTY_GR7,
    }
    assert named <= refused
    source = WEB_PARSER.read_text(encoding="utf-8")
    block = re.search(r"export const PLANNING_OVERLAY_REFUSAL_CODES = \[(.*?)\] as const;", source, flags=re.DOTALL)
    assert block is not None
    web_codes = set(re.findall(r'"([a-z0-9_]+)"', block.group(1)))
    python_codes = set(po.REFUSAL_CODES)
    python_only = set(po.PYTHON_ONLY_CODES)
    assert len(python_codes) == len(po.REFUSAL_CODES) and python_only < python_codes
    assert python_only == {
        po.PROTOCOL_BINDING_REQUIRED,
        po.PUBLIC_WRITE_NOT_ELIGIBLE,
        po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED,
    }
    # Every code the module can put in a problem is listed in REFUSAL_CODES.
    module_source = (ROOT / "src" / "floodguard" / "planning_overlay.py").read_text(encoding="utf-8")
    used = set(re.findall(r"OverlayProblem\(\s*([A-Z][A-Z0-9_]+)", module_source))
    used |= set(re.findall(r"[^_a-z]add\(\s*([A-Z][A-Z0-9_]+)", module_source))
    assert used and {getattr(po, name) for name in used} == python_codes
    # The web parser gives every code except the ones that need a missing binding or a target path.
    assert web_codes == python_codes - python_only
    # Every code a validator can give without a target path is exercised by a case.
    assert refused == python_codes - {po.PUBLIC_WRITE_NOT_ELIGIBLE, po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED}
    for case in CASES:
        assert case["basis"].strip() and case["checked_by"], case["id"]
        assert set(case["checked_by"]) <= {"schema", "python", "python_with_protocols", "typescript"}, case["id"]
        assert ("typescript" in case["checked_by"]) == (case["refuses"] in web_codes), case["id"]
        assert not {"python", "python_with_protocols"} <= set(case["checked_by"]), case["id"]
        assert {"python", "python_with_protocols"} & set(case["checked_by"]), case["id"]
    # Every case but the one the web parser cannot see is run by both suites.
    python_alone = [case["id"] for case in CASES if "typescript" not in case["checked_by"]]
    assert python_alone == ["candidate-without-the-protocol-binding"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_overlay_is_refused(
    case: dict[str, Any], overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    changed = _patched(overlay, case["patch"])
    assert changed != overlay
    checked_by = case["checked_by"]
    without_protocols = _codes(po.overlay_problems(changed, schema))
    with_protocols = _codes(po.overlay_problems(changed, schema, binding=binding))
    assert without_protocols - {po.PROTOCOL_BINDING_REQUIRED} <= with_protocols
    if "schema" in checked_by:
        # Only the JSON schema gives the code "structure" for an object: the schema alone refuses this overlay.
        assert po.STRUCTURE in without_protocols
    if "python" in checked_by:
        assert case["refuses"] in without_protocols
    if "python_with_protocols" in checked_by:
        assert case["refuses"] not in without_protocols and case["refuses"] in with_protocols
    with pytest.raises(po.PlanningOverlayError):
        po.validate_overlay(changed, schema, binding=binding)


def test_the_code_structure_comes_from_the_json_schema_alone(overlay: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema)
    for case in CASES:
        if "schema" in case["checked_by"]:
            changed = _patched(overlay, case["patch"])
            first = next(validator.iter_errors(changed), None)
            assert first is not None, f"the JSON schema alone must refuse {case['id']}"
    # A case the schema cannot see (arithmetic) gets no structure problem from the module either.
    arithmetic = _patched(overlay, _case("fpps-not-the-weighted-sum")["patch"])
    assert next(validator.iter_errors(arithmetic), None) is None and po.schema_problems(arithmetic, schema) == []


def _schema_conditionals(schema: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    """Every if / then / else rule of the schema: the definition it belongs to, its position and the rule."""

    rules = [("$", index, rule) for index, rule in enumerate(schema.get("allOf", []))]
    for name, node in schema["$defs"].items():
        rules += [(name, index, rule) for index, rule in enumerate(node.get("allOf", []))]
    return rules


def _instances(name: str, overlay: dict[str, Any]) -> list[Any]:
    """The parts of an overlay a definition with conditionals applies to."""

    rows = [row for row in overlay.get("rows", []) if isinstance(row, dict)]
    confidences = [row.get("confidence") for row in rows]
    return {
        "$": [overlay],
        "case": [overlay.get("case")],
        "input": list(overlay.get("inputs", [])),
        "row": rows,
        "derivedConfidence": [
            item for item in confidences if isinstance(item, dict) and item.get("confidence_kind") != "declared"
        ],
        "headlineStability": [row.get("headline_stability") for row in rows],
    }[name]


def test_every_schema_conditional_is_tripped_by_a_case_both_suites_run(
    overlay: dict[str, Any], schema: dict[str, Any]
) -> None:
    """The web test compares the two shapes field by field, which says nothing about the conditional rules.

    So each branch of each ``if`` / ``then`` / ``else`` of the schema has a refusal case that trips it and that
    both suites run: the web parser's hand-written conditionals are held to every one of them.
    """

    rules = _schema_conditionals(schema)
    with_rules = {"$", "case", "input", "row", "derivedConfidence", "headlineStability"}
    assert {name for name, _index, _rule in rules} == with_rules
    assert len(rules) == 31 and all("if" in rule for _name, _index, rule in rules)
    shared = [case for case in CASES if {"schema", "typescript"} <= set(case["checked_by"])]
    changed = {case["id"]: _patched(overlay, case["patch"]) for case in shared}
    untripped = []
    for name, index, rule in rules:
        whole = Draft202012Validator({**rule, "$defs": schema["$defs"]})
        condition = Draft202012Validator({**rule["if"], "$defs": schema["$defs"]})
        tripped = {branch: False for branch in ("then", "else") if branch in rule}
        assert tripped, (name, index)
        assert all(whole.is_valid(item) for item in _instances(name, overlay) if isinstance(item, dict))
        for candidate in changed.values():
            for item in _instances(name, candidate):
                if isinstance(item, dict) and not whole.is_valid(item):
                    tripped["then" if condition.is_valid(item) else "else"] = True
        untripped += [f"{name}.allOf[{index}].{branch}" for branch, seen in tripped.items() if not seen]
    assert untripped == []


def test_validate_and_serialise_raise_with_every_reason(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    changed = _patched(overlay, _case("class-above-e-with-low-confidence")["patch"])
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.validate_overlay(changed, schema, binding=binding)
    expected = {po.CLASS_ABOVE_E_WITHOUT_MEDIUM_CONFIDENCE, po.LOW_CONFIDENCE_FORCES_E, po.STRUCTURE}
    assert set(refused.value.codes) == expected
    assert all(problem.path.startswith("$.rows[7]") for problem in refused.value.problems)
    assert "planning overlay refused" in str(refused.value)
    with pytest.raises(po.PlanningOverlayError):
        po.overlay_text(changed, schema, binding=binding)


def test_values_that_are_not_an_overlay_are_refused(schema: dict[str, Any], tmp_path: Path) -> None:
    for value in (None, [], "overlay", 3, {}):
        assert po.STRUCTURE in _codes(po.overlay_problems(value, schema))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.load_overlay(broken, schema)
    assert refused.value.codes == (po.STRUCTURE,)
    with pytest.raises(po.PlanningOverlayError):
        po.load_overlay_schema(ROOT / "packages" / "contracts" / "schemas" / "status.schema.json")


def test_a_refused_overlay_is_never_written(overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path) -> None:
    overlay["rows"][0]["accepted_fpps"] = 80.0
    target = tmp_path / "refused.json"
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(overlay, target, schema)
    assert po.ACCEPTED_VALUE_NOT_NULL in refused.value.codes
    assert "accepted_value_not_null at $.rows[0].accepted_fpps" in str(refused.value)
    assert not target.exists()


# ---------------------------------------------------------------------------
# Guardrail GR1: one resident count per row
# ---------------------------------------------------------------------------


def test_gr1_cannot_be_bypassed_with_a_second_resident_count(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    """A 60-resident unit restated as 600 in its confidence record only, with the row rescored (DR-A09).

    The record is exactly what rule v1 derives for 600 residents, so re-deriving it finds nothing. The refusal
    comes from the exposure record of the same row, which counts 60.
    """

    case = _case("gr1-bypassed-by-a-second-resident-count")
    changed = _patched(overlay, case["patch"])
    row = _row(changed, "obs-t3-c6-gr1-no-class")
    record = row["confidence"]
    assert row["components"]["exposure_0_100"]["inputs"]["unit_residents"] == 60
    assert record["measurements"]["unit_residents"] == 600 and record["confidence_class"] == "medium"
    assert (row["action_class"], row["action_reason_code"]) == ("D", "resilience")
    assert derive_confidence(po._confidence_inputs(record), binding.rule) == record
    assert po.schema_problems(changed, schema) == []
    for found in (po.overlay_problems(changed, schema), po.overlay_problems(changed, schema, binding=binding)):
        assert [(item.code, item.path) for item in found] == [
            (po.CONFIDENCE_RECORD_MISMATCH, "$.rows[10].confidence.measurements.unit_residents")
        ]
        assert "60" in found[0].message and "GR1" in found[0].message
    # The original state of the row is the one the protocol requires: no class at all.
    original = _row(overlay, "obs-t3-c6-gr1-no-class")
    restated = dataclasses.replace(po._confidence_inputs(original["confidence"]), unit_residents=600.0)
    six_hundred = derive_confidence(restated, binding.rule)
    assert six_hundred == record and original["action_class"] is None


# ---------------------------------------------------------------------------
# The stated basis is recomputed, with and without the protocol files
# ---------------------------------------------------------------------------


def test_stated_basis_is_recomputed_from_the_echoed_measurements(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    def refused_paths(case_id: str) -> set[str]:
        changed = _patched(overlay, _case(case_id)["patch"])
        found = po.overlay_problems(changed, schema)
        assert po.CONFIDENCE_NOT_RULE_RECORD in _codes(po.overlay_problems(changed, schema, binding=binding)), case_id
        return {item.path.split(".confidence.")[-1] for item in found if item.code == po.CONFIDENCE_RECORD_MISMATCH}

    # A T2 own candidate below the skill bar, with C1 stated "pass": medium, class C.
    changed = _patched(overlay, _case("own-candidate-below-the-skill-bar-stated-medium")["patch"])
    row = _row(changed, "obs-t2-c1-own-candidate")
    assert row["confidence"]["t2_skill_condition"]["passes"] is False
    assert (row["confidence"]["confidence_class"], row["action_class"]) == ("medium", "C")
    assert refused_paths("own-candidate-below-the-skill-bar-stated-medium") == {"basis.C1_tier"}
    # An OBS row ten days from its reference date, stated event_aligned with C2 "pass": class B.
    changed = _patched(overlay, _case("obs-row-ten-days-late-stated-event-aligned")["patch"])
    row = _row(changed, "obs-t3-c2-not-event-aligned")
    assert row["confidence"]["measurements"]["recency_days"] == 10 and row["action_class"] == "B"
    assert refused_paths("obs-row-ten-days-late-stated-event-aligned") == {"basis.C2_recency"}
    assert po.TEMPORAL_RELATION_MISMATCH in _codes(po.overlay_problems(changed, schema))
    assert refused_paths("recency-days-not-the-days-between-the-dates") == {"measurements.recency_days"}
    assert refused_paths("skill-record-stated-as-passing") == {"t2_skill_condition.passes", "basis.C1_tier"}
    # Every condition of every row, stated the other way round, is caught on its own basis value.
    for name in CONDITION_IDS:
        flipped = deepcopy(overlay)
        expected = set()
        for index, row in enumerate(flipped["rows"]):
            record = row["confidence"]
            if record and record["confidence_kind"] != "declared" and record["basis"][name] in ("pass", "fail"):
                record["basis"][name] = "fail" if record["basis"][name] == "pass" else "pass"
                expected.add(f"$.rows[{index}].confidence.basis.{name}")
        problems = po.overlay_problems(flipped, schema)
        found = {item.path for item in problems if item.code == po.CONFIDENCE_RECORD_MISMATCH}
        assert len(expected) >= 15 and expected <= found, name


def test_an_overlay_under_other_protocol_bytes_is_refused_even_when_consistent_with_itself(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    hashes = protocol_hashes(binding.frame)
    text = FIXTURE.read_text(encoding="ascii").replace(hashes["v1a"], "0" * 64).replace(hashes["v1b"], "1" * 64)
    replaced = json.loads(text)
    found = _codes(po.overlay_problems(replaced, schema, binding=binding))
    assert po.PROTOCOL_NOT_IN_FORCE in found and po.PROTOCOL_HASH_MISMATCH not in found
    with pytest.raises(po.PlanningOverlayError):
        po.validate_overlay(replaced, schema, binding=binding)


def test_weights_other_than_the_signed_ones_are_refused_whatever_the_rows_say(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding, generator
) -> None:
    """Weights of 0.2 each with every row rescored: consistent with itself, and not the signed frame."""

    changed = deepcopy(overlay)
    frame = changed["scoring_frame"]
    frame["weights"] = {name: 0.2 for name in SCORE_COMPONENTS}
    frame["leave_one_component_out_weights"] = {
        dropped: {name: 0.0 if name == dropped else 0.25 for name in SCORE_COMPONENTS} for dropped in SCORE_COMPONENTS
    }
    rescored = 0
    for row in changed["rows"]:
        values = {name: None if record is None else record["value_0_100"] for name, record in row["components"].items()}
        if row["confidence"] is None or any(value is None for value in values.values()):
            continue
        confidence = row["confidence"]
        gr1 = bool(confidence.get("guardrail_gr1", {}).get("applies"))
        block = generator._scoring_block(values, confidence["confidence_class"], gr1, frame)
        rescored += any(row[name] != value for name, value in block.items())
        row.update(block)
    assert rescored == 24
    # Arithmetic alone no longer finds anything in the rows (v2 aside, which reads FPPS)...
    arithmetic = {
        po.FPPS_MISMATCH,
        po.CLASS_RULE_MISMATCH,
        po.LOCO_MISMATCH,
        po.WOULD_BE_CLASS_MISMATCH,
        po.SCORING_FRAME_INCONSISTENT,
    }
    assert not arithmetic & _codes(po.overlay_problems(changed, schema))
    # ...and the schema refuses the weights, and the binding the frame.
    assert next(Draft202012Validator(schema).iter_errors(changed), None) is not None
    assert po.STRUCTURE in _codes(po.overlay_problems(changed, schema))
    assert po.FRAME_NOT_PROTOCOL_FRAME in _codes(po.overlay_problems(changed, schema, binding=binding))


def test_v2_axis_is_checked_against_the_row(overlay: dict[str, Any], schema: dict[str, Any]) -> None:
    """v1a class_rules.v2: E is low confidence, exposure below 10 or FPPS below 35; A needs the v1 class A;
    C needs an FPPS of at least 35 and medium confidence; D needs an FPPS of at least 35."""

    def messages(key: str, met: dict[str, bool], result: str) -> str:
        changed = deepcopy(overlay)
        v2 = _row(changed, key)["class_v2"]
        for item in v2["trigger_evidence"]:
            item["met"] = met.get(item["trigger"], item["met"])
        v2["result"] = result
        found = [item for item in po.overlay_problems(changed, schema) if item.code == po.V2_RESULT_INCONSISTENT]
        assert len(found) <= 1
        return found[0].message if found else ""

    low_score = _row(overlay, "obs-t3-low-priority-score")
    assert low_score["fpps_0_100"] < 35 and low_score["confidence"]["confidence_class"] == "medium"
    assert "trigger E is met" in messages("obs-t3-low-priority-score", {"E": False, "A": True}, "A")
    assert "trigger A needs the v1 class A" in messages("obs-t3-low-priority-score", {"E": False, "A": True}, "A")
    assert "trigger D needs an FPPS of at least 35" in messages("obs-t3-low-priority-score", {"D": True}, "E")
    assert "trigger C needs an FPPS of at least 35" in messages("obs-t3-low-priority-score", {"C": True}, "E")
    # Trigger E stated as met on a row that is medium, scored and exposed.
    assert "trigger E is not met" in messages("obs-t3-class-b", {"E": True}, "E")
    # Trigger A on a row whose v1 class is B.
    assert "trigger A needs the v1 class A" in messages("obs-t3-class-b", {"A": True}, "A")
    # Unchanged rows are accepted, including the one where no trigger is met.
    assert messages("obs-t3-no-v2-trigger", {}, "no_v2_trigger") == ""
    assert messages("obs-t3-class-b", {}, "B") == ""


def test_one_row_is_one_unit_lane_flood_input_and_scenario(overlay: dict[str, Any], schema: dict[str, Any]) -> None:
    copied = deepcopy(overlay)
    twin = deepcopy(_row(copied, "obs-t3-class-a"))
    twin["row_id"] = "FX-CASE-01:obs-t3-class-a-again"
    copied["rows"].append(twin)
    found = po.overlay_problems(copied, schema)
    assert [(item.code, item.path) for item in found] == [(po.DUPLICATE_ID, "$.rows")]
    assert "FX-CASE-01:obs-t3-class-a" in found[0].message and "FX-CASE-01:obs-t3-class-a-again" in found[0].message
    # The same unit in another lane, or on another scenario, is another row: the fixture has both.
    keys = [po._row_key(row) for row in overlay["rows"]]
    assert len(set(keys)) == len(keys)
    assert len({row["unit_id"] for row in overlay["rows"]}) < len(keys)


# ---------------------------------------------------------------------------
# Refusals instead of exceptions, and the same answer as the web parser
# ---------------------------------------------------------------------------


def test_not_a_number_is_refused(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding, tmp_path: Path
) -> None:
    text = FIXTURE.read_text(encoding="ascii")
    fpps = _row(overlay, "obs-t3-class-a")["fpps_0_100"]
    for constant in ("NaN", "Infinity", "-Infinity"):
        target = tmp_path / f"{constant}.json"
        target.write_text(text.replace(f'"fpps_0_100": {fpps},', f'"fpps_0_100": {constant},', 1), encoding="ascii")
        for chosen in (None, binding):
            with pytest.raises(po.PlanningOverlayError) as refused:
                po.load_overlay(target, schema, binding=chosen)
            assert refused.value.codes == (po.STRUCTURE,) and "not valid JSON" in str(refused.value)
    # A parsed overlay that holds one (json.loads accepts NaN unless told otherwise) is refused too.
    for value in (float("nan"), float("inf")):
        changed = deepcopy(overlay)
        _row(changed, "obs-t3-class-a")["fpps_0_100"] = value
        for chosen in (None, binding):
            found = po.overlay_problems(changed, schema, binding=chosen)
            assert (po.STRUCTURE, "$.rows[0].fpps_0_100") in {(item.code, item.path) for item in found}
            with pytest.raises(po.PlanningOverlayError):
                po.overlay_text(changed, schema, binding=chosen)
    # A number too large for a float parses to infinity.
    target = tmp_path / "huge.json"
    target.write_text(text.replace(f'"fpps_0_100": {fpps},', '"fpps_0_100": 1e999,', 1), encoding="ascii")
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.load_overlay(target, schema)
    assert po.STRUCTURE in refused.value.codes


def test_malformed_overlays_are_refused_with_codes_and_never_with_another_exception(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    class_a = "FX-CASE-01:obs-t3-class-a"
    steps = [
        {"row": class_a, "path": ["confidence"], "set": None},
        {"row": class_a, "path": ["components"], "set": None},
        {"row": class_a, "path": ["lineage"], "set": None},
        {"row": class_a, "path": ["confidence", "measurements"], "set": None},
        {"row": class_a, "path": ["confidence", "measurements", "acquisition_date"], "set": "2030-13-45"},
        {"row": class_a, "path": ["confidence", "measurements", "case_reference_date"], "set": "2030-02-30"},
        {"path": ["case", "case_reference_date"], "set": "2030-00-10"},
        {"path": ["scoring_frame"], "set": None},
        {"path": ["case"], "set": None},
        {"path": ["inputs"], "set": None},
        {"path": ["rows"], "set": [None]},
    ]
    for step in steps:
        changed = _patched(overlay, [step])
        for chosen in (None, binding):
            assert po.STRUCTURE in _codes(po.overlay_problems(changed, schema, binding=chosen)), step["path"]
            with pytest.raises(po.PlanningOverlayError):
                po.validate_overlay(changed, schema, binding=chosen)


def test_patterns_are_anchored_as_the_web_parser_anchors_them(overlay: dict[str, Any], schema: dict[str, Any]) -> None:
    """Python's ``$`` also matches before a final line feed; ECMAScript's does not."""

    for steps in (
        [{"path": ["git_commit"], "set": "4624f8d\n"}],
        [{"path": ["protocol_sha256", "v1a"], "set": overlay["protocol_sha256"]["v1a"] + "\n"}],
        [{"path": ["source_timestamp"], "set": "2026-10-04T00:00:00Z\n"}],
        [{"input": "fx_boundaries", "path": ["input_id"], "set": "fx_boundaries\n"}],
        [{"path": ["case", "case_reference_date"], "set": "2030-01-10\n"}],
    ):
        changed = _patched(overlay, steps)
        assert po.STRUCTURE in _codes(po.schema_problems(changed, schema)), steps
    assert po._ecmascript_pattern("^[0-9a-f]{7,40}$") == r"^[0-9a-f]{7,40}\Z"
    assert po._ecmascript_pattern(r"^price\$") == r"^price\$" and po._ecmascript_pattern("not a place") == "not a place"
    # Every pattern of the schema that ends in "$" is one the two engines read alike after that change.
    schema_text = (ROOT / po.SCHEMA_RELATIVE_PATH).read_text(encoding="ascii")
    patterns = set(re.findall(r'"pattern": "((?:[^"\\]|\\.)*)"', schema_text))
    assert len(patterns) >= 6 and all(pattern.startswith("^") or pattern == "not a place" for pattern in patterns)


# ---------------------------------------------------------------------------
# Guardrail GR6: writing under apps/web/public
# ---------------------------------------------------------------------------


def _public_variant(overlay: dict[str, Any]) -> dict[str, Any]:
    """The fixture with every input at the public level and without its pitch-level row."""

    public = deepcopy(overlay)
    for item in public["inputs"]:
        item["rights_level"] = "public"
    public["publication_eligibility"] = "public"
    public["rows"] = [
        row for row in public["rows"]
        if (row["components"]["access_gap_0_100"] or {}).get("publication_level") != "pitch"
    ]
    return public


def test_only_a_public_overlay_is_written_under_the_web_public_folder(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    public_folder = tmp_path / "apps" / "web" / "public" / "planning-assessments"
    public_folder.mkdir(parents=True)
    assert po.is_public_web_path(public_folder / "x.json") and not po.is_public_web_path(tmp_path / "x.json")
    assert not po.is_public_web_path(FIXTURE)

    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(overlay, public_folder / "fixture.json", schema)
    assert refused.value.codes == (po.PUBLIC_WRITE_NOT_ELIGIBLE,)
    assert list(public_folder.iterdir()) == []

    # A rights level above the lineage minimum is refused before any path is looked at.
    claimed = deepcopy(overlay)
    claimed["publication_eligibility"] = "public"
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(claimed, public_folder / "claimed.json", schema)
    assert po.PUBLICATION_NOT_LINEAGE_MINIMUM in refused.value.codes

    # Public inputs with a pitch-level access gap (the located-shelter service) are still not public.
    public = _public_variant(overlay)
    public["rows"] = deepcopy(overlay["rows"])
    assert _codes(po.overlay_problems(public, schema)) == {po.PUBLICATION_NOT_LINEAGE_MINIMUM}

    public = _public_variant(overlay)
    written = po.write_overlay(public, public_folder / "public.json", schema)
    assert Path(written["path"]).read_bytes().count(b"\r") == 0 and written["bytes"] > 0


def test_the_public_write_gate_is_not_bypassed_by_a_path_with_dots(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = tmp_path / "apps" / "web"
    public_folder = web / "public"
    (web / "src").mkdir(parents=True)
    public_folder.mkdir()
    dotted = web / "src" / ".." / "public" / "local-overlay.json"
    assert ".." in dotted.parts and po.is_public_web_path(dotted)
    assert po.is_public_web_path(web / "PUBLIC" / "x.json") and po.is_public_web_path(str(dotted))
    assert not po.is_public_web_path(web / "public" / ".." / "src" / "x.json")
    for target in (dotted, web / "src" / ".." / "." / "public" / "nested" / ".." / "local-overlay.json"):
        with pytest.raises(po.PlanningOverlayError) as refused:
            po.write_overlay(overlay, target, schema)
        assert refused.value.codes == (po.PUBLIC_WRITE_NOT_ELIGIBLE,)
    # A relative path is judged from the working directory.
    monkeypatch.chdir(web / "src")
    assert po.is_public_web_path(Path("..") / "public" / "x.json") and not po.is_public_web_path(Path("x.json"))
    with pytest.raises(po.PlanningOverlayError):
        po.write_overlay(overlay, Path("..") / "public" / "x.json", schema)
    assert list(public_folder.iterdir()) == []


def test_the_public_write_gate_follows_a_link_to_the_public_folder(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    public_folder = tmp_path / "apps" / "web" / "public"
    public_folder.mkdir(parents=True)
    link = tmp_path / "elsewhere"
    try:
        os.symlink(public_folder, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        # Windows without the symbolic-link privilege: a directory junction needs none.
        try:
            import _winapi

            _winapi.CreateJunction(str(public_folder), str(link))
        except (ImportError, AttributeError, OSError):
            pytest.skip("this account may create neither a symbolic link nor a junction")
    assert po.is_public_web_path(link / "x.json")
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(overlay, link / "x.json", schema)
    assert refused.value.codes == (po.PUBLIC_WRITE_NOT_ELIGIBLE,) and list(public_folder.iterdir()) == []


def test_a_flood_input_without_a_declared_source_product_is_not_written_to_public_files(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    public_folder = tmp_path / "apps" / "web" / "public"
    public_folder.mkdir(parents=True)
    public = _public_variant(overlay)
    undeclared = next(item for item in public["inputs"] if item["input_id"] == "fx_season_layer")
    undeclared["source_product"] = None
    assert po.overlay_problems(public, schema) == []
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(public, public_folder / "undeclared.json", schema)
    assert refused.value.codes == (po.PUBLIC_WRITE_NOT_ELIGIBLE,)
    assert [item.path for item in refused.value.problems] == ["$.inputs[3].source_product"]
    assert list(public_folder.iterdir()) == []
    # Another role may leave it empty, and outside the public folder nothing is asked.
    undeclared["source_product"] = "fixture_invented_input"
    next(item for item in public["inputs"] if item["role"] == "boundaries")["source_product"] = None
    po.write_overlay(public, public_folder / "declared.json", schema)
    undeclared["source_product"] = None
    po.write_overlay(public, tmp_path / "local-copy.json", schema)


@pytest.mark.parametrize(
    "text",
    [
        "CHIANGRAI_20240801_20241012_AccumulatedFlood",
        "CHIANGRAI_20241022_FloodExtent",
        "chiangrai_20241022_floodextent",
        "FL20240912THA",
        "the 4009 22 Oct layer",
        "4009 accumulated layer",
        "UNOSAT/GISTDA product 4009, accumulated layer",
        "unosat4009/envelope.png",
        "UNOSAT_4009",
    ],
)
def test_product_4009_is_recognised_under_every_name_the_protocol_uses(
    text: str, overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    for field in ("name", "attribution"):
        named = deepcopy(overlay)
        item = next(item for item in named["inputs"] if item["input_id"] == "fx_season_layer")
        item[field] = text
        if field == "name":
            for row in named["rows"]:
                if row["lineage"]["flood_input_id"] == "fx_season_layer":
                    row["flood_input"] = row["confidence"]["flood_input"] = text
        assert po.cites_product_4009(named), field
        found = po.overlay_problems(named, schema)
        assert [(problem.code, problem.path) for problem in found] == [
            (po.SOURCE_PRODUCT_NOT_DECLARED, "$.inputs[3].source_product")
        ], field
        # Declared, it needs the licence, the credit and a change notice.
        item["source_product"] = po.PRODUCT_4009_SOURCE
        assert _codes(po.overlay_problems(named, schema)) == {po.PRODUCT_4009_LICENCE_MISSING}, field
    # The reviewed bypass: licence "unknown", attribution "GISTDA", no change notice, no rights record.
    public_folder = tmp_path / "apps" / "web" / "public"
    public_folder.mkdir(parents=True)
    public = _public_variant(overlay)
    item = next(item for item in public["inputs"] if item["input_id"] == "fx_local_only_layer")
    item.update(name=text, licence="unknown", attribution="GISTDA", change_notice=None)
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(public, public_folder / "accumulated.json", schema)
    assert refused.value.codes == (po.SOURCE_PRODUCT_NOT_DECLARED,) and list(public_folder.iterdir()) == []


def test_text_that_only_looks_like_the_product_number_is_not_product_4009(
    overlay: dict[str, Any], schema: dict[str, Any]
) -> None:
    for text in ("EPSG 32647 grid, 14009 cells", "Fixture layer 40090", "tile A4009B"):
        named = deepcopy(overlay)
        next(item for item in named["inputs"] if item["input_id"] == "fx_boundaries")["name"] = text
        assert not po.cites_product_4009(named) and po.overlay_problems(named, schema) == [], text


def test_a_product_4009_overlay_reaches_public_files_only_with_the_confirmed_rights_record(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    public_folder = tmp_path / "apps" / "web" / "public" / "planning-assessments"
    public_folder.mkdir(parents=True)
    public = _public_variant(overlay)
    boundaries = next(item for item in public["inputs"] if item["input_id"] == "fx_boundaries")
    boundaries["name"] = "UNOSAT/GISTDA product 4009 (name used by this test only; nothing is read)"
    assert po.cites_product_4009(public)
    assert _codes(po.overlay_problems(public, schema)) == {po.SOURCE_PRODUCT_NOT_DECLARED}
    boundaries["source_product"] = po.PRODUCT_4009_SOURCE
    assert _codes(po.overlay_problems(public, schema)) == {po.PRODUCT_4009_LICENCE_MISSING}
    boundaries.update(
        licence=po.PRODUCT_4009_LICENCE,
        attribution=f"{po.PRODUCT_4009_CREDIT}, CC BY-SA 4.0",
        change_notice="Changed by FloodGuard: test text only.",
    )
    assert po.overlay_problems(public, schema) == []

    target = public_folder / "with-4009.json"
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(public, target, schema)
    assert refused.value.codes == (po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED,)

    rights = load_rights_basis(ROOT / RIGHTS_BASIS_4009_PATH)
    pending = deepcopy(rights)
    pending["owner_confirmation"]["status"] = "pending"
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(public, target, schema, rights_basis_4009=pending)
    assert refused.value.codes == (po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED,) and not target.exists()

    assert rights["owner_confirmation"]["status"] == "confirmed"
    po.write_overlay(public, target, schema, rights_basis_4009=rights)
    assert target.is_file()
    # Declared under a name that does not cite it, the product is still product 4009: the record is asked for.
    boundaries["name"] = "Fixture unit boundaries (invented)"
    assert po.cites_product_4009(public) and po.overlay_problems(public, schema) == []
    with pytest.raises(po.PlanningOverlayError) as refused:
        po.write_overlay(public, public_folder / "declared-only.json", schema)
    assert refused.value.codes == (po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED,)
    # Outside the public folder the record is not asked for: the file does not ship.
    po.write_overlay(public, tmp_path / "local-copy.json", schema)


# ---------------------------------------------------------------------------
# The content digest both languages compute
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (15.0, "15"), (15, "15"), (-0.0, "0"), (0.1, "0.1"), (-2.5, "-2.5"), (63.63, "63.63"), (1e-09, "1e-9"),
        (1.5e-07, "1.5e-7"), (0.000001, "0.000001"), (123456.789, "123456.789"), (1e21, "1e+21"),
        (1e20, "100000000000000000000"), (5e-324, "5e-324"), (1.7976931348623157e308, "1.7976931348623157e+308"),
        (0.35714285714285715, "0.35714285714285715"),
        (True, "true"), (None, "null"), ("a\"b\\c\n", '"a\\"b\\\\c\\n"'), ("ท", '"ท"'),
        ({"b": [1, 2.0, None], "a": {"z": False, "y": "x"}}, '{"a":{"y":"x","z":false},"b":[1,2,null]}'),
    ],
)
def test_canonical_json_writes_numbers_as_ecmascript_does(value: Any, text: str) -> None:
    assert po.canonical_json(value) == text


def test_canonical_json_refuses_what_is_not_json() -> None:
    for value in (float("nan"), float("inf"), {1, 2}, b"bytes"):
        with pytest.raises(po.PlanningOverlayError):
            po.canonical_json(value)


def test_content_digest_ignores_layout_and_notices_a_changed_value(overlay: dict[str, Any]) -> None:
    digest = po.content_sha256(overlay)
    assert digest == json.loads(SUMMARY.read_text(encoding="ascii"))["summary"]["content_sha256"]
    reordered = json.loads(json.dumps(overlay, sort_keys=True, indent=7))
    assert po.content_sha256(reordered) == digest
    overlay["rows"][0]["fpps_0_100"] += 0.01
    assert po.content_sha256(overlay) != digest


# ---------------------------------------------------------------------------
# The reference page
# ---------------------------------------------------------------------------


def test_reference_page_states_the_fixture_counts_and_only_real_codes() -> None:
    page = (ROOT / "docs" / "planning_assessment_overlay.md").read_text(encoding="utf-8")
    summary = json.loads(SUMMARY.read_text(encoding="ascii"))["summary"]
    assert f"{summary['row_count']} rows on {summary['unit_count']} invented units" in page
    assert f"{len(CASES)} refusal cases" in page
    table = page.split("## What is refused", 1)[1].split("## What the fixture", 1)[0]
    cells = [line.split("|")[2] for line in table.splitlines() if line.startswith("|")]
    codes = {code for cell in cells for code in re.findall(r"`([a-z0-9_]+)`", cell)}
    assert codes == set(po.REFUSAL_CODES)
    assert "not an official warning" in page and "class E never means safe" in page
    # The open points for the owners are numbered, and the page names the ones the review added.
    open_points = page.split("## Points the protocols leave open", 1)[1]
    numbers = [int(number) for number in re.findall(r"^([0-9]+)\. \*\*", open_points, flags=re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 20
    added = ("SE2-dist", "permitted_use", "reason_blocked", "event_time", "reason_code_mapping", "`inputs[].role`")
    for phrase in (*added, "source_product"):
        assert phrase in open_points, phrase
