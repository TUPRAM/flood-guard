"""Planning assessment overlay (plan 7.1, task E11): schema, strict validator, writer and the committed fixture.

Every overlay in this file is the committed fixture or a changed copy of it. The fixture is an invented case
with invented units (a fixture, not a place): no test here reads a flood layer, a population raster or a real
unit, and nothing is written under ``outputs/``.

The round trip is: Python builds the fixture, the JSON schema and the strict validator accept it, Python
writes it, and the web parser reads the same bytes (``apps/web/src/lib/planning-assessment-overlay.test.ts``).
This file proves the Python half and that the committed bytes are the ones Python writes today; the web test
proves that TypeScript finds the same content (file hash, content digest and counts). The refusal cases are
one JSON file read by both test suites.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from floodguard import planning_overlay as po
from floodguard.confidence import BASIS_VALUES, CONDITION_IDS, COMPONENT_STATUSES
from floodguard.rights_basis import RIGHTS_BASIS_4009_PATH, load_rights_basis
from floodguard.scoring import ACTION_REASON_CODES, SCORE_COMPONENTS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
V1A = DOCS / "planning_protocol_v1a.json"
V1B = DOCS / "planning_protocol_v1b.json"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
FIXTURES = ROOT / "apps" / "web" / "src" / "lib" / "__fixtures__"
FIXTURE = FIXTURES / "planning-assessment-overlay.fixture.json"
SUMMARY = FIXTURES / "planning-assessment-overlay.fixture.summary.json"
REFUSALS = FIXTURES / "planning-assessment-overlay.refusals.json"
GENERATOR = ROOT / "apps" / "web" / "scripts" / "planning-overlay-fixture.py"
WEB_PARSER = ROOT / "apps" / "web" / "src" / "lib" / "planning-assessment-overlay.ts"

# Codes only the Python side gives: they need the scorer, the protocol files or a target path.
PYTHON_ONLY_CODES = {
    po.CLASS_RULE_MISMATCH,
    po.PROTOCOL_NOT_IN_FORCE,
    po.FRAME_NOT_PROTOCOL_FRAME,
    po.COMPONENT_NOT_FRAME_RECORD,
    po.CONFIDENCE_NOT_RULE_RECORD,
    po.PUBLIC_WRITE_NOT_ELIGIBLE,
    po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED,
}
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


def _codes(problems: list[po.OverlayProblem]) -> set[str]:
    return {problem.code for problem in problems}


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
    assert headline["guardrail"]["const"] == "GR8_headline_stability"
    retention_min = guardrails["GR8_headline_stability"]["parameters"]["class_retention_min"]
    assert headline["class_retention_min"]["const"] == retention_min
    v2 = v1a["class_rules"]["v2"]
    class_v2 = defs["classV2"]["properties"]
    assert class_v2["label"]["const"] == v2["label_when_shown"]
    assert class_v2["binding"]["const"] is v2["binding"] is False
    assert class_v2["class_rule_version"]["const"] == v2["version"]
    assert v2["evaluation"]["otherwise"] == po.NO_V2_TRIGGER and po.NO_V2_TRIGGER in class_v2["result"]["enum"]
    assert tuple(v2["evaluation"]["order"]) == po.V2_TRIGGER_ORDER
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


def test_closure_rule_vocabulary_is_that_of_protocol_v1b(schema: dict[str, Any]) -> None:
    rule = json.loads(V1B.read_text(encoding="utf-8"))["closure_rule_v1"]
    closure = schema["$defs"]["closureRule"]["properties"]
    assert closure["version"]["const"] == rule["version"]
    assert closure["level"]["enum"] == list(rule["levels"])
    assert "closure_basis: modelled_from_<input>" in rule["closure_is_an_assumption"]
    assert closure["closure_basis"]["pattern"] == "^modelled_from_.+"


def test_product_4009_wording_is_the_signed_wording(v1a: dict[str, Any]) -> None:
    rights = load_rights_basis(ROOT / RIGHTS_BASIS_4009_PATH)
    assert po.PRODUCT_4009_CREDIT == v1a["wording"]["product_4009_credit"] == rights["required_attribution_text"]
    assert po.PRODUCT_4009_LICENCE == rights["licence"]["name"]


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
    overlay: dict[str, Any], v1a: dict[str, Any]
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
    assert not any(case["id"] == overlay["case"]["case_id"] for case in portfolio["cases"])
    assert not po.cites_product_4009(overlay)
    # Invented dates only: every acquisition and reference date is in 2030.
    dates = {
        row["confidence"]["measurements"][key]
        for row in overlay["rows"]
        if row["confidence"] and "measurements" in row["confidence"]
        for key in ("acquisition_date", "case_reference_date")
    }
    assert dates - {None} and all(value.startswith("2030-") for value in dates - {None})


def test_fixture_hashes_are_those_of_the_protocols_in_force(overlay: dict[str, Any]) -> None:
    in_force = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (("v1a", V1A), ("v1b", V1B))}
    assert overlay["protocol_sha256"] == in_force == overlay["scoring_frame"]["protocol_sha256"]
    for row in overlay["rows"]:
        for record in row["components"].values():
            if record is not None and "protocol_sha256" in record:
                assert record["protocol_sha256"] == in_force
        if row["confidence"] and "protocol_v1a_sha256" in row["confidence"]:
            assert row["confidence"]["protocol_v1a_sha256"] == in_force["v1a"]


def test_fixture_exercises_every_tier_reason_code_condition_and_outcome(overlay: dict[str, Any]) -> None:
    summary = po.summarise_overlay(overlay)

    def unused(counts: dict[str, int], keys: tuple[str, ...]) -> list[str]:
        return [key for key in keys if not counts[key]]

    assert unused(summary["rows_by_tier"], po.TIERS) == []
    assert unused(summary["rows_by_lane"], po.LANES) == []
    assert unused(summary["rows_by_temporal_relation"], po.TEMPORAL_RELATIONS) == []
    assert unused(summary["rows_by_reason_code"], po.REASON_CODES) == []
    assert unused(summary["rows_by_binding_class"], po.ACTION_CLASSES) == []
    assert unused(summary["rows_by_would_be_class"], po.ACTION_CLASSES) == []
    assert unused(summary["rows_by_v2_result"], (*po.ACTION_CLASSES, po.NO_V2_TRIGGER)) == []
    assert unused(summary["failed_condition_counts"], CONDITION_IDS) == []
    headline_statuses = (po.HEADLINE_NOT_EVALUATED, po.HEADLINE_ELIGIBLE, po.HEADLINE_UNSTABLE)
    assert unused(summary["rows_by_headline_status"], headline_statuses) == []
    assert unused(summary["inputs_by_rights_level"], po.PUBLICATION_LEVELS) == []
    assert unused(summary["rows_by_confidence_kind"], ("observed", "scenario", po.KIND_DECLARED)) == []
    assert summary["rows_under_gr1"] == 1 and summary["obs_rows_not_event_aligned"] == 1
    # The two states a fixture cannot show (see the generator's docstring): C3 by construction is granted to
    # product 4009 in the eight Mae Sai tambons only, and only two named detectors can pass the T2 skill condition.
    assert summary["basis_value_counts"]["by_construction"] == 0
    assert summary["basis_value_counts"]["by_scenario_declaration"] > 0
    t2_rows = [row for row in overlay["rows"] if row["tier"] == "T2"]
    assert t2_rows and all(row["confidence"]["t2_skill_condition"]["passes"] is False for row in t2_rows)
    assert all(row["action_class"] == "E" and row["action_reason_code"] == "low_confidence" for row in t2_rows)


def test_fixture_shows_each_guardrail_outcome(overlay: dict[str, Any]) -> None:
    small = _row(overlay, "obs-t3-c6-gr1-no-class")
    assert small["confidence"]["measurements"]["unit_residents"] < 100
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


def test_a_candidate_overlay_of_a_portfolio_case_is_accepted_too(
    overlay: dict[str, Any], schema: dict[str, Any]
) -> None:
    overlay["dataset_mode"] = "candidate"
    overlay["case"].update(kind="portfolio_case", fixture_notice=None)
    assert po.overlay_problems(overlay, schema) == []
    overlay["case"]["fixture_notice"] = "left over"
    assert _codes(po.overlay_problems(overlay, schema)) == {po.STRUCTURE}


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
    assert len(python_codes) == len(po.REFUSAL_CODES) and PYTHON_ONLY_CODES < python_codes
    # Every code the module can put in a problem is listed in REFUSAL_CODES.
    module_source = (ROOT / "src" / "floodguard" / "planning_overlay.py").read_text(encoding="utf-8")
    used = set(re.findall(r"OverlayProblem\(\s*([A-Z][A-Z0-9_]+)", module_source))
    used |= set(re.findall(r"[^_a-z]add\(\s*([A-Z][A-Z0-9_]+)", module_source))
    assert used and {getattr(po, name) for name in used} == python_codes
    assert web_codes == python_codes - PYTHON_ONLY_CODES
    # Every code a validator can give without a target path is exercised by a case.
    assert refused == python_codes - {po.PUBLIC_WRITE_NOT_ELIGIBLE, po.PRODUCT_4009_RIGHTS_NOT_CONFIRMED}
    for case in CASES:
        assert case["basis"].strip() and case["checked_by"], case["id"]
        assert ("typescript" in case["checked_by"]) <= (case["refuses"] in web_codes), case["id"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_overlay_is_refused(
    case: dict[str, Any], overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    changed = _patched(overlay, case["patch"])
    assert changed != overlay
    checked_by = case["checked_by"]
    without_protocols = _codes(po.overlay_problems(changed, schema))
    with_protocols = _codes(po.overlay_problems(changed, schema, binding=binding))
    assert without_protocols <= with_protocols
    if "schema" in checked_by:
        # Only the JSON schema gives the code "structure" for an object: the schema alone refuses this overlay.
        assert po.STRUCTURE in without_protocols
    if "python" in checked_by:
        assert case["refuses"] in without_protocols
    if "python_with_protocols" in checked_by:
        assert case["refuses"] not in without_protocols and case["refuses"] in with_protocols


def test_the_code_structure_comes_from_the_json_schema_alone(overlay: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema)
    for case in CASES:
        if "schema" in case["checked_by"]:
            changed = _patched(overlay, case["patch"])
            first = next(validator.iter_errors(changed), None)
            assert first is not None, f"the JSON schema alone must refuse {case['id']}"
    # A case the schema cannot see (arithmetic) gets no structure problem from the module either.
    arithmetic = _patched(overlay, next(item for item in CASES if item["id"] == "fpps-not-the-weighted-sum")["patch"])
    assert next(validator.iter_errors(arithmetic), None) is None and po.schema_problems(arithmetic, schema) == []


def test_validate_and_serialise_raise_with_every_reason(
    overlay: dict[str, Any], schema: dict[str, Any], binding: po.ProtocolBinding
) -> None:
    case = next(item for item in CASES if item["id"] == "class-above-e-with-low-confidence")
    changed = _patched(overlay, case["patch"])
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


def test_a_product_4009_overlay_reaches_public_files_only_with_the_confirmed_rights_record(
    overlay: dict[str, Any], schema: dict[str, Any], tmp_path: Path
) -> None:
    public_folder = tmp_path / "apps" / "web" / "public" / "planning-assessments"
    public_folder.mkdir(parents=True)
    public = _public_variant(overlay)
    boundaries = next(item for item in public["inputs"] if item["input_id"] == "fx_boundaries")
    boundaries["name"] = "UNOSAT/GISTDA product 4009 (name used by this test only; nothing is read)"
    assert po.cites_product_4009(public)
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
    table = page.split("## What is refused", 1)[1].split("## What the fixture", 1)[0]
    cells = [line.split("|")[2] for line in table.splitlines() if line.startswith("|")]
    codes = {code for cell in cells for code in re.findall(r"`([a-z0-9_]+)`", cell)}
    assert len(codes) >= 20 and codes <= set(po.REFUSAL_CODES)
    assert "not an official warning" in page and "class E never means safe" in page
