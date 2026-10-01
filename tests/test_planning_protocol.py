"""Guard the planning protocol drafts (v1a decision rules, v1b engineering addendum).

The drafts are written by agents and signed by people. These tests check that
the files are well formed, that they repeat the signed decisions and the scoring
code exactly, that the exploratory-knowledge disclosure is complete enough to
audit, and that nothing in them claims to be in force.

No test here computes an FPPS, an A-E class or an ensemble. The class thresholds
are read from the scoring module's source, not by scoring any row.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS
from floodguard.sensitivity import WEIGHT_SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
SCORING = ROOT / "src" / "floodguard" / "scoring.py"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
SIGNING_GUIDE = DOCS / "planning_protocol_v1_signing.md"
PROTOCOL_PATHS = {
    "v1a": DOCS / "planning_protocol_v1a.json",
    "v1b": DOCS / "planning_protocol_v1b.json",
}
SCHEMA_PATHS = {
    "v1a": DOCS / "planning_protocol_v1a.schema.json",
    "v1b": DOCS / "planning_protocol_v1b.schema.json",
}

# The owners change these two values in the signing commit of each file; see
# docs/proposal_execution/planning_protocol_v1_signing.md.
EXPECTED_STATUS = {"v1a": "draft_for_signature", "v1b": "incomplete_draft"}
DRAFT_STATUSES = {"draft_for_signature", "incomplete_draft"}

DISCLOSURE_KEY = "exploratory_knowledge_disclosure"
OPEN_DECISIONS = ["D5", "D8", "D10", "D14", "D15", "D16"]

# Tokens that name a real scored unit in the Chiang Rai cases.
REAL_UNIT = re.compile(
    r"TH57\d{4}|Mae Sai|Huai Khrai|Ko Chang|Pong Pha|Si Mueang Chum|Wiang Phang Kham"
    r"|Ban Dai|Pong Ngam|Rim Kok|Rop Wiang|Ban Du"
)
SCORE_WORD = re.compile(r"fpps|priority score", re.IGNORECASE)
DECIMAL = re.compile(r"\d+\.\d+")
# FPPS values for real Mae Sai tambons that the team has already seen
# (replay commit 2e5a099 and the retired legacy lane).
SEEN_REAL_FPPS = ("89.34", "31.27", "53.65", "17.12", "18.01", "44.0")
UNIT_KEYS = {"subdistrict_id", "tambon", "tambon_id", "adm3_pcode", "unit_id"}
SCORE_KEY = re.compile(r"fpps|action_class|priority_score", re.IGNORECASE)
# Keys that hold a rule threshold on the FPPS scale, not a unit's score.
THRESHOLD_KEYS = {"fpps_min"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocols() -> dict[str, dict[str, Any]]:
    return {name: _load(path) for name, path in PROTOCOL_PATHS.items()}


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return {name: _load(path) for name, path in SCHEMA_PATHS.items()}


def _errors(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.path)}: {error.message}"
        for error in validator.iter_errors(payload)
    ]


def _walk(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], Any]]:
    """Yield every node of a JSON value with its path."""

    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, (*path, index))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _real_unit_score_findings(value: Any) -> list[str]:
    """List places where a JSON value states a score or class for a real unit."""

    findings: list[str] = []
    for path, node in _walk(value):
        where = "/".join(str(part) for part in path)
        if isinstance(node, str):
            if any(seen in node for seen in SEEN_REAL_FPPS):
                findings.append(f"{where}: repeats an FPPS value already seen for a real tambon")
            if REAL_UNIT.search(node) and SCORE_WORD.search(node) and DECIMAL.search(node):
                findings.append(f"{where}: names a real unit beside a score and a decimal value")
        elif _is_number(node):
            if any(math.isclose(float(node), float(seen)) for seen in SEEN_REAL_FPPS):
                findings.append(f"{where}: number equals an FPPS value already seen for a real tambon")
            key = path[-1] if path else ""
            if isinstance(key, str) and SCORE_KEY.search(key) and key not in THRESHOLD_KEYS:
                findings.append(f"{where}: numeric value under a score key")
        elif isinstance(node, dict):
            keys = set(node)
            if keys & UNIT_KEYS and any(SCORE_KEY.search(key) for key in keys):
                findings.append(f"{where}: object pairs a unit identifier with a score or class")
    return findings


def _v1_rules_from_code() -> tuple[list[dict[str, Any]], int, int]:
    """Read the v1 class rules from scoring.assign_action_class without running it."""

    tree = ast.parse(SCORING.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "assign_action_class"
    )
    operators = {ast.Eq: "==", ast.Lt: "<", ast.GtE: ">="}
    combiners = {ast.Or: "any", ast.And: "all"}
    variables: dict[str, str] = {}

    def column(expression: ast.AST) -> str:
        if isinstance(expression, ast.Name):
            return variables[expression.id]
        for node in ast.walk(expression):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "row"
                and isinstance(node.slice, ast.Constant)
            ):
                return str(node.slice.value)
        raise AssertionError("assign_action_class compares something that is not a row column")

    rules: list[dict[str, Any]] = []
    for statement in function.body:
        if isinstance(statement, ast.Assign):
            target = statement.targets[0]
            assert isinstance(target, ast.Name)
            variables[target.id] = column(statement.value)
        elif isinstance(statement, ast.If):
            test = statement.test
            assert isinstance(test, ast.BoolOp)
            conditions = []
            for compare in test.values:
                assert isinstance(compare, ast.Compare) and len(compare.ops) == 1
                comparator = compare.comparators[0]
                assert isinstance(comparator, ast.Constant)
                conditions.append(
                    {
                        "field": column(compare.left),
                        "operator": operators[type(compare.ops[0])],
                        "value": comparator.value,
                    }
                )
            returned = statement.body[0]
            assert isinstance(returned, ast.Return) and isinstance(returned.value, ast.Constant)
            rules.append(
                {
                    "class": returned.value.value,
                    "combine": combiners[type(test.op)],
                    "conditions": conditions,
                }
            )
        elif isinstance(statement, ast.Return):
            assert isinstance(statement.value, ast.Constant)
            rules.append({"class": statement.value.value, "combine": "otherwise", "conditions": []})
    return rules, function.lineno, function.end_lineno or 0


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_protocol_validates_against_its_schema(
    name: str, protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    Draft202012Validator.check_schema(schemas[name])
    assert _errors(schemas[name], protocols[name]) == []


@pytest.mark.parametrize("path", [*PROTOCOL_PATHS.values(), *SCHEMA_PATHS.values()])
def test_files_are_ascii_with_lf_endings(path: Path) -> None:
    raw = path.read_bytes()
    raw.decode("ascii")
    assert b"\r" not in raw
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_protocol_is_a_declared_protocol_and_not_a_warning(
    name: str, protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols[name]
    assert protocol["protocol_kind"] == "declared_protocol_after_exploratory_analysis"
    assert protocol["official_warning"] is False
    assert protocol["operational_status"] == "non_operational"
    assert protocol["assumptions"]


# ---------------------------------------------------------------------------
# Draft state: not signed, not in force
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_status_is_the_expected_state(name: str, protocols: dict[str, dict[str, Any]]) -> None:
    assert protocols[name]["status"] == EXPECTED_STATUS[name]


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_signature_block_matches_the_status(name: str, protocols: dict[str, dict[str, Any]]) -> None:
    block = protocols[name]["signature_block"]
    signers = block["signers"]
    assert [signer["role"] for signer in signers] == ["owner", "method_co_signer"]
    assert signers[0]["required_signer"].startswith("Putu")
    assert signers[1]["required_signer"].startswith("Rachmania")
    assert [signer["action"] for signer in signers] == ["signs", "co-signs"]
    if EXPECTED_STATUS[name] in DRAFT_STATUSES:
        for signer in signers:
            assert signer["signed_by"] is None
            assert signer["signed_at_utc"] is None
            assert signer["attestation"] is None
        assert block["amendments_at_signing"] == []
    else:
        for signer in signers:
            assert signer["signed_by"] and signer["signed_at_utc"] and signer["attestation"]


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_draft_does_not_claim_to_be_in_force(name: str, protocols: dict[str, dict[str, Any]]) -> None:
    if EXPECTED_STATUS[name] not in DRAFT_STATUSES:
        pytest.skip("signed file: force is read from RECEIPTS.jsonl")
    text = PROTOCOL_PATHS[name].read_text(encoding="utf-8").lower()
    assert "frozen" not in text
    assert "hashed" not in text
    assert "preregistered" not in protocols[name]["protocol_kind"]
    assert "not in force" in text or "nothing in this file is in force" in text
    for path, node in _walk(protocols[name]):
        key = path[-1] if path else ""
        if isinstance(key, str) and key in {"protocol_sha256", "self_sha256", "receipt_sha256"}:
            pytest.fail(f"draft records its own hash at {'/'.join(map(str, path))}: {node!r}")


def test_no_receipt_names_a_draft_protocol() -> None:
    lines = [line for line in RECEIPTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "RECEIPTS.jsonl is empty"
    for line in lines:
        record = json.loads(line)
        assert record["schema_version"] == "floodguard.proposal_execution_receipt.v1"
    for name, status in EXPECTED_STATUS.items():
        if status in DRAFT_STATUSES:
            assert not any(f"planning_protocol_{name}" in line for line in lines), name


def test_schema_refuses_a_signature_on_a_draft_and_a_signed_file_without_one(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    for name in ("v1a", "v1b"):
        signed_draft = deepcopy(protocols[name])
        signed_draft["status"] = EXPECTED_STATUS[name] if EXPECTED_STATUS[name] in DRAFT_STATUSES else "draft_for_signature"
        if name == "v1b" and signed_draft["status"] == "draft_for_signature":
            for item in signed_draft["open_items"]:
                item["status"] = "closed"
                item["closure"] = {
                    "closed_on": "2026-10-02",
                    "closed_by": "test",
                    "value_or_location": "test",
                    "evidence_sha256": None,
                }
        signed_draft["signature_block"]["signers"][0]["signed_by"] = "someone"
        assert _errors(schemas[name], signed_draft), name

        unsigned = deepcopy(protocols[name])
        unsigned["status"] = "signed"
        for signer in unsigned["signature_block"]["signers"]:
            signer.update(signed_by=None, signed_at_utc=None, attestation=None)
        assert _errors(schemas[name], unsigned), name


def test_v1b_stays_incomplete_while_any_item_is_open(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    open_ids = [item["id"] for item in protocol["open_items"] if item["status"] == "open"]
    if open_ids:
        assert protocol["status"] == "incomplete_draft"
        promoted = deepcopy(protocol)
        promoted["status"] = "draft_for_signature"
        assert _errors(schemas["v1b"], promoted)
    else:
        assert protocol["status"] != "incomplete_draft"


# ---------------------------------------------------------------------------
# v1a: scoring frame as signed in D4
# ---------------------------------------------------------------------------


def test_weights_sum_to_one_and_match_the_scoring_module(protocols: dict[str, dict[str, Any]]) -> None:
    frame = protocols["v1a"]["scoring_frame"]
    weights = frame["weights"]
    assert list(weights) == list(SCORE_COMPONENTS)
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)
    assert weights == DEFAULT_WEIGHTS
    assert [weights[component] for component in SCORE_COMPONENTS] == [0.30, 0.25, 0.20, 0.15, 0.10]
    assert set(frame["components"]) == set(SCORE_COMPONENTS)


def test_weight_presets_match_the_sensitivity_module(protocols: dict[str, dict[str, Any]]) -> None:
    presets = protocols["v1a"]["scoring_frame"]["weight_presets"]["raw_values_before_normalisation"]
    assert presets == WEIGHT_SCENARIOS
    assert len(presets) == 5


def test_d4_anchors_are_exactly_as_signed(protocols: dict[str, dict[str, Any]]) -> None:
    frame = protocols["v1a"]["scoring_frame"]
    assert "D4" in frame["basis"]
    components = frame["components"]

    flood = components["flood_likelihood_0_100"]
    assert flood["anchor"] == 0.20
    assert flood["anchor_sensitivity_one_at_a_time"] == [0.10, 0.30]
    assert "non-permanent-water land" in flood["definition"]
    assert "min(1," in flood["definition"]
    disclosure = flood["anchor_disclosure"]
    assert "0.05" in disclosure and "after" in disclosure and "saturate" in disclosure
    water = flood["permanent_water"]
    assert "WorldCover" in water["source"]
    assert water["class"] == 80
    assert water["applies_to"] == "every case"
    assert "JRC" in water["sensitivity_note"] and "sensitivity" in water["sensitivity_note"]

    exposure = components["exposure_0_100"]
    assert exposure["kind"] == "share_only"
    assert exposure["headcount_anchor"] is None
    assert exposure["density_anchor"] is None

    vulnerability = components["vulnerability_context_0_100"]
    assert vulnerability["lower_anchor"] == "national_P10"
    assert vulnerability["upper_anchor"] == "national_P90"
    assert vulnerability["anchor_sensitivity"] == {"lower": "national_P5", "upper": "national_P95"}
    assert vulnerability["terrain_remoteness_proxy"]["cases"] == ["O1"]
    assert "before any case scoring" in vulnerability["anchor_values_status"]

    assert frame["leave_one_component_out"]["required_on_every_row"] is True
    assert "0.20" in frame["signed_decision_text"]


def test_national_anchor_values_are_not_computed_yet(protocols: dict[str, dict[str, Any]]) -> None:
    if EXPECTED_STATUS["v1b"] != "incomplete_draft":
        pytest.skip("anchors are filled when the open item is closed")
    v1a_values = protocols["v1a"]["scoring_frame"]["components"]["vulnerability_context_0_100"]["anchor_values"]
    assert set(v1a_values.values()) == {None}
    anchors = protocols["v1b"]["national_vulnerability_anchors"]
    assert set(anchors["values"]) == {"P5", "P10", "P75", "P90", "P95"}
    assert set(anchors["values"].values()) == {None}
    assert anchors["download_needed"] is False
    assert anchors["inputs"]["age_rasters"]["on_disk"] is True


# ---------------------------------------------------------------------------
# v1a: class rules equal the scoring code (D6)
# ---------------------------------------------------------------------------


def test_v1_class_thresholds_equal_the_scoring_module(protocols: dict[str, dict[str, Any]]) -> None:
    v1 = protocols["v1a"]["class_rules"]["v1"]
    code_rules, first_line, last_line = _v1_rules_from_code()
    assert v1["rules"] == code_rules
    assert [rule["class"] for rule in v1["rules"]] == ["E", "A", "B", "C", "D"]
    assert v1["source"]["lines"] == f"{first_line}-{last_line}"
    assert v1["source"]["sha256"] == hashlib.sha256(SCORING.read_bytes()).hexdigest()
    assert v1["binding"] is True
    assert protocols["v1a"]["source_documents"]["scoring_module"]["sha256"] == v1["source"]["sha256"]
    assert protocols["v1a"]["confidence_rule_v1"]["vocabulary"] == list(VALID_CONFIDENCE_CLASSES)


def test_v2_is_a_secondary_axis_only(protocols: dict[str, dict[str, Any]]) -> None:
    rules = protocols["v1a"]["class_rules"]
    assert "D6" in rules["basis"]
    assert rules["v2"]["binding"] is False
    assert rules["v2"]["role"] == "predeclared secondary axis"
    assert set(rules["v2"]["triggers"]) == {"A", "B", "C", "D", "E"}


# ---------------------------------------------------------------------------
# v1a: decisions, cases, guardrails
# ---------------------------------------------------------------------------


def test_open_decisions_are_listed_as_undefined(protocols: dict[str, dict[str, Any]]) -> None:
    open_decisions = protocols["v1a"]["open_decisions"]
    assert [decision["id"] for decision in open_decisions] == OPEN_DECISIONS
    assert {decision["text"] for decision in open_decisions} == {"undefined in the plan files"}
    adopted = [decision["id"] for decision in protocols["v1a"]["signed_decisions"]["adopted"]]
    assert adopted == ["D1", "D2", "D3", "D4", "D6", "D7", "D8b", "D9", "D11", "D12", "D13"]
    assert not set(adopted) & set(OPEN_DECISIONS)


def test_case_portfolio_matches_d7(protocols: dict[str, dict[str, Any]]) -> None:
    portfolio = protocols["v1a"]["case_portfolio"]
    priority = {case["id"]: case["priority"] for case in portfolio["cases"]}
    assert priority == {
        "O1": "MUST",
        "O2": "MUST",
        "SE1": "MUST",
        "SE2": "MUST",
        "SE2-dist": "MUST",
        "SE2-blind": "SHOULD",
        "O4": "conditional",
        "H1": "stretch",
    }
    lanes = {case["id"]: case["lane"] for case in portfolio["cases"]}
    assert lanes["SE1"] == lanes["SE2"] == lanes["SE2-dist"] == lanes["SE2-blind"] == "SCN-ENV"
    assert lanes["O1"] == lanes["O2"] == "OBS"
    disclosure = portfolio["case_selection_disclosure"]
    assert "selected knowing" in disclosure and "same 2024 season product" in disclosure


def test_date_rule_matches_d3(protocols: dict[str, dict[str, Any]]) -> None:
    rule = protocols["v1a"]["date_rule"]
    assert rule["recency_window_days"] == 3
    assert rule["product_4009"]["accumulated_layer"]["lane"] == "SCN-ENV"
    assert rule["product_4009"]["accumulated_layer"]["use"] == "scenario only"
    assert rule["product_4009"]["layer_22_oct"]["case"] == "O2"
    recency = protocols["v1a"]["confidence_rule_v1"]["medium_requires_all"][1]
    assert recency["threshold"] == {"recency_window_days": 3}


def test_all_nine_guardrails_and_every_rule_section_cite_a_basis(
    protocols: dict[str, dict[str, Any]]
) -> None:
    v1a = protocols["v1a"]
    assert [guardrail["id"][:3] for guardrail in v1a["guardrails"]] == [f"GR{n}" for n in range(1, 10)]
    for guardrail in v1a["guardrails"]:
        assert any("plan 2.3" in basis for basis in guardrail["basis"])
    sections = (
        "evidence_tier_model", "date_rule", "confidence_rule_v1", "t2_skill_bar", "geoid_split",
        "scoring_frame", "class_rules", "equity_statement_rule", "case_portfolio",
        "demo_tambon_rule", DISCLOSURE_KEY, "change_control",
    )
    for section in sections:
        assert v1a[section]["basis"], section
    tiers = [tier["tier"] for tier in v1a["evidence_tier_model"]["tiers"]]
    assert tiers == ["T0", "T1", "T2", "T3", "T4"]
    assert {lane["lane"] for lane in v1a["evidence_tier_model"]["lanes"]} == {"OBS", "SCN", "SCN-ENV", "ENG"}


def test_geoid_split_is_fifteen_and_fourteen_disjoint_tiles(protocols: dict[str, dict[str, Any]]) -> None:
    split = protocols["v1a"]["geoid_split"]
    development, test = split["development_tile_ids"], split["test_tile_ids"]
    assert len(development) == 15 and len(test) == 14
    assert not set(development) & set(test)
    assert development == sorted(development) and test == sorted(test)
    assert max(development) < min(test)
    assert protocols["v1a"]["t2_skill_bar"]["conditions"]["geoid_held_out_test_iou_min"] == 0.40


def test_change_control_requires_a_v2_and_full_reporting(protocols: dict[str, dict[str, Any]]) -> None:
    for name in ("v1a", "v1b"):
        rules = " ".join(protocols[name]["change_control"]["rules"])
        assert "planning_protocol_v2" in rules and "written reason" in rules
        assert "Every run is reported" in rules


# ---------------------------------------------------------------------------
# v1a: exploratory-knowledge disclosure
# ---------------------------------------------------------------------------


def test_every_exploratory_item_has_a_location_and_an_informed_parameter(
    protocols: dict[str, dict[str, Any]]
) -> None:
    items = protocols["v1a"][DISCLOSURE_KEY]["items"]
    identifiers = [item["id"] for item in items]
    assert len(identifiers) == len(set(identifiers))
    for item in items:
        assert item["locations"], item["id"]
        for location in item["locations"]:
            assert location["value"].strip(), item["id"]
        assert item["informed_parameters"], item["id"]
        assert all(parameter.strip() for parameter in item["informed_parameters"]), item["id"]
        assert item["could_bias"].strip() and item["guard"].strip(), item["id"]


def test_disclosure_covers_the_items_the_plan_and_the_owner_named(
    protocols: dict[str, dict[str, Any]]
) -> None:
    items = protocols["v1a"][DISCLOSURE_KEY]["items"]
    titles = " | ".join(item["title"].lower() for item in items)
    for phrase in ("gap-1", "gap-4", "decision-engine", "flood-anchor saturation", "all-tile geoid"):
        assert phrase in titles, phrase

    replay = {item["id"]: item for item in items if item["lineage"] == "replay_lineage_master"}
    assert sorted(replay) == ["EK-R1", "EK-R2", "EK-R3", "EK-R4"]
    first = replay["EK-R1"]
    assert "2e5a099" in first["what_was_seen"]
    assert "89.34" in first["what_was_seen"] and "31.27" in first["what_was_seen"]
    assert first["real_tambon_scores_or_classes_seen"] is True
    assert any("2e5a099" in location["value"] for location in first["locations"])
    assert "calibration-informed" in replay["EK-R2"]["what_was_seen"]
    assert "0.48" in replay["EK-R3"]["what_was_seen"]
    assert "VIIRS" in replay["EK-R4"]["what_was_seen"]


# ---------------------------------------------------------------------------
# Blinding: no score for a real unit outside the disclosure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_no_fpps_value_for_a_real_tambon_outside_the_disclosure(
    name: str, protocols: dict[str, dict[str, Any]]
) -> None:
    outside = {key: value for key, value in protocols[name].items() if key != DISCLOSURE_KEY}
    assert _real_unit_score_findings(outside) == []


def test_the_score_detector_sees_the_disclosed_values(protocols: dict[str, dict[str, Any]]) -> None:
    disclosure = protocols["v1a"][DISCLOSURE_KEY]
    assert _real_unit_score_findings(disclosure), "the detector must flag the disclosed replay scores"
    planted = {"rows": [{"subdistrict_id": "TH570903", "fpps_0_100": 12.5}]}
    assert len(_real_unit_score_findings(planted)) >= 2
    assert _real_unit_score_findings({"note": "Ko Chang FPPS 12.5"})


# ---------------------------------------------------------------------------
# v1b: open items, downloads, grid arithmetic
# ---------------------------------------------------------------------------


def test_v1b_open_items_say_what_who_and_whether_a_download_is_needed(
    protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    items = {item["id"]: item for item in protocol["open_items"]}
    assert len(items) == len(protocol["open_items"])
    for item in items.values():
        for field in ("parameter", "what_is_missing", "produced_by", "who"):
            assert item[field].strip(), (item["id"], field)
        assert isinstance(item["download_needed"], bool)
    referenced: set[str] = set()
    for path, node in _walk({key: value for key, value in protocol.items() if key != "open_items"}):
        if path and path[-1] == "open_items":
            referenced.update(node)
    assert referenced <= set(items)
    produced = " ".join(item["produced_by"] for item in items.values())
    assert "E0" in produced and "E4" in produced and "E2" in produced


def test_v1b_downloads_await_owner_approval(protocols: dict[str, dict[str, Any]]) -> None:
    downloads = protocols["v1b"]["downloads_requiring_owner_approval"]
    assert downloads
    for download in downloads:
        assert download["approved"] is None
        for field in ("dataset", "file", "source", "approximate_size", "needed_for"):
            assert download[field].strip(), (download["id"], field)


def test_v1b_ensemble_grid_arithmetic(protocols: dict[str, dict[str, Any]]) -> None:
    grid = protocols["v1b"]["ensemble_grid"]
    counts = [axis["count"] for axis in grid["core_axes"]]
    assert all(len(axis["levels"]) == axis["count"] for axis in grid["core_axes"])
    assert math.prod(counts) == grid["core_cells_per_lane"] == 540
    assert math.prod(counts[:3]) == grid["routing_combinations_per_lane"] == 27
    assert grid["headline_rule"]["class_retention_min"] == 0.60
    weights_axis = grid["core_axes"][-1]
    assert weights_axis["levels"] == list(WEIGHT_SCENARIOS)


def test_v1b_closure_rule_matches_the_plan(protocols: dict[str, dict[str, Any]]) -> None:
    rule = protocols["v1b"]["closure_rule_v1"]
    assert [rule["levels"][level]["delay_factor_k"] for level in ("strict", "central", "permissive")] == [2, 4, 6]
    parameters = rule["parameters"]
    assert parameters["closed_fraction_min"] == 0.5
    assert parameters["bridge_culvert_closed_fraction_min"] == 0.25
    assert parameters["delay_min_intersected_length_m"] == 20
    assert parameters["length_threshold_m_by_road_class"] == {
        "trunk": 50, "primary": 50, "secondary": 50, "tertiary": 30, "local": 30,
    }
    assert rule["regression"]["result"] is None


def test_v1b_points_at_v1a_without_a_recorded_hash(protocols: dict[str, dict[str, Any]]) -> None:
    depends = protocols["v1b"]["depends_on"]
    assert (ROOT / depends["v1a_path"]) == PROTOCOL_PATHS["v1a"]
    if EXPECTED_STATUS["v1a"] in DRAFT_STATUSES:
        assert depends["v1a_sha256"] is None


def test_signing_guide_exists_and_names_the_receipt_schema() -> None:
    text = SIGNING_GUIDE.read_text(encoding="utf-8")
    assert "floodguard.proposal_execution_receipt.v1" in text
    assert "RECEIPTS.jsonl" in text
    assert "git show" in text and "sha256" in text.lower()
    assert b"\r" not in SIGNING_GUIDE.read_bytes()
