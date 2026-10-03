"""Guard the planning protocol drafts (v1a decision rules, v1b engineering addendum).

The drafts are written by agents and signed by people. These tests check that
the files are well formed, that they repeat the signed decisions and the scoring
code exactly, that the exploratory-knowledge disclosure is complete enough to
audit, that every reading the drafting agent made is flagged for the owners,
that nothing in a draft claims to be in force, and that a recorded protocol
still has the bytes its receipt names.

No test here computes an FPPS, an A-E class or an ensemble. The class thresholds
are read from the scoring module's source, not by scoring any row. Values used
to fill a copy of v1b are synthetic placeholders for schema checks, not results.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from floodguard.config import VALID_CONFIDENCE_CLASSES
from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS
from floodguard.sensitivity import WEIGHT_SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
SCORING = ROOT / "src" / "floodguard" / "scoring.py"
FINALS_CLOSURE = ROOT / "src" / "floodguard" / "evidence_flood_scenario.py"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
SIGNING_GUIDE = DOCS / "planning_protocol_v1_signing.md"
RECEIPT_SCRIPT = ROOT / "scripts" / "record_planning_protocol_receipt.py"
PROTOCOL_PATHS = {
    "v1a": DOCS / "planning_protocol_v1a.json",
    "v1b": DOCS / "planning_protocol_v1b.json",
}
SCHEMA_PATHS = {
    "v1a": DOCS / "planning_protocol_v1a.schema.json",
    "v1b": DOCS / "planning_protocol_v1b.schema.json",
}

_SPEC = importlib.util.spec_from_file_location("record_planning_protocol_receipt", RECEIPT_SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
receipt_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(receipt_tool)

# The owners change these values as each file moves on; see
# docs/proposal_execution/planning_protocol_v1_signing.md.
#   v1a: draft_for_signature -> signed
#   v1b: incomplete_draft -> draft_for_signature -> signed
EXPECTED_STATUS = {"v1a": "signed", "v1b": "incomplete_draft"}
DRAFT_STATUSES = {"draft_for_signature", "incomplete_draft"}

DISCLOSURE_KEY = "exploratory_knowledge_disclosure"
OPEN_DECISIONS = ["D5", "D8", "D10", "D14", "D15", "D16"]
AWAITING = "awaiting_owner_confirmation"

# Readings the drafting agent made where the plan is silent or says two things.
# Each must stay flagged in the file and in the signing guide while the file is a draft.
REQUIRED_READINGS = {
    "v1a": [f"DR-A{number:02d}" for number in range(1, 13)],
    "v1b": [f"DR-B{number:02d}" for number in range(1, 9)],
}
SECTIONS_WITH_STATUS = (
    "corridor_polygon", "grade_join_policy", "closure_rule_v1", "facility_sets", "critical_link_selection",
    "national_vulnerability_anchors", "ensemble_grid", "scenario_engine_grid", "class_rule_v2_inputs",
)

# Tokens that name a real scored unit in the Chiang Rai cases.
REAL_UNIT = re.compile(
    r"TH57\d{4}|Mae Sai|Huai Khrai|Ko Chang|Pong Pha|Si Mueang Chum|Wiang Phang Kham"
    r"|Ban Dai|Pong Ngam|Rim Kok|Rop Wiang|Ban Du"
)
SCORE_WORD = re.compile(r"fpps|priority score", re.IGNORECASE)
DECIMAL = re.compile(r"\d+\.\d+")
# A sentence that gives a real unit an A-E class, e.g. "Ko Chang is class B".
CLASS_STATEMENT = re.compile(
    r"\bclass(?:es)?\s+[A-E]\b(?!-)|\b(?:is|was|as|gets?|got|gives?|gave|reach(?:es|ed)?)\s+[A-E]\b(?![-\w])"
)
# A sentence that gives a real unit a value of one of the five components.
COMPONENT_WORD = re.compile(
    r"flood[- ]likelihood|flooded[- ](?:area |resident )?share|exposure|access[- ]gap|access loss"
    r"|road[- ]criticality|vulnerability|dependent share",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"(?<=[.;!?])\s+")
# FPPS values for real Mae Sai tambons that the team has already seen
# (replay commit 2e5a099 and the retired legacy lane).
SEEN_REAL_FPPS = ("89.34", "31.27", "53.65", "17.12", "18.01", "44.0")
UNIT_KEYS = {"subdistrict_id", "tambon", "tambon_id", "adm3_pcode", "unit_id"}
SCORE_KEY = re.compile(r"fpps|action_class|priority_score", re.IGNORECASE)
RESULT_KEY = re.compile(r"fpps|class|priority_score|_0_100$", re.IGNORECASE)
# Keys that hold a rule threshold on the FPPS scale, not a unit's score.
THRESHOLD_KEYS = {"fpps_min"}
# Sections outside the exploratory-knowledge disclosure that are themselves a required
# disclosure of something already seen (plan 6.1, signed in D7).
DISCLOSING_PATHS = {("case_portfolio", "case_selection_disclosure")}
# The plan's own term for the T4 hold-out; "frozen" is otherwise banned in a draft.
ALLOWED_PLAN_TERMS = ("frozen hold-out",)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocols() -> dict[str, dict[str, Any]]:
    return {name: _load(path) for name, path in PROTOCOL_PATHS.items()}


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return {name: _load(path) for name, path in SCHEMA_PATHS.items()}


@pytest.fixture(scope="module")
def receipts() -> list[dict[str, Any]]:
    return receipt_tool.parse_receipts(RECEIPTS.read_text(encoding="utf-8"))


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


def _encode(payload: dict[str, Any]) -> bytes:
    """Serialise a protocol the way the committed files are written."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _set_pointer(document: Any, pointer: str, value: Any) -> None:
    parts = pointer.lstrip("/").split("/")
    parent = receipt_tool.resolve_pointer(document, "/" + "/".join(parts[:-1])) if parts[:-1] else document
    if isinstance(parent, list):
        parent[int(parts[-1])] = value
    else:
        parent[parts[-1]] = value


def _real_unit_score_findings(value: Any) -> list[str]:
    """List places where a JSON value states a score, class or component value for a real unit."""

    findings: list[str] = []
    for path, node in _walk(value):
        where = "/".join(str(part) for part in path)
        if isinstance(node, str):
            if path in DISCLOSING_PATHS:
                continue
            if any(seen in node for seen in SEEN_REAL_FPPS):
                findings.append(f"{where}: repeats an FPPS value already seen for a real tambon")
            if REAL_UNIT.search(node) and SCORE_WORD.search(node) and DECIMAL.search(node):
                findings.append(f"{where}: names a real unit beside a score and a decimal value")
            for sentence in SENTENCE_END.split(node):
                if not REAL_UNIT.search(sentence):
                    continue
                if CLASS_STATEMENT.search(sentence):
                    findings.append(f"{where}: gives a real unit an A-E class")
                if COMPONENT_WORD.search(sentence) and re.search(r"\d", REAL_UNIT.sub("", sentence)):
                    findings.append(f"{where}: gives a real unit a component value")
        elif _is_number(node):
            if any(math.isclose(float(node), float(seen)) for seen in SEEN_REAL_FPPS):
                findings.append(f"{where}: number equals an FPPS value already seen for a real tambon")
            key = path[-1] if path else ""
            if isinstance(key, str) and SCORE_KEY.search(key) and key not in THRESHOLD_KEYS:
                findings.append(f"{where}: numeric value under a score key")
        elif isinstance(node, dict):
            keys = set(node)
            if keys & UNIT_KEYS and any(RESULT_KEY.search(key) for key in keys - UNIT_KEYS):
                findings.append(f"{where}: object pairs a unit identifier with a score, class or component")
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


def _as_draft(protocol: dict[str, Any]) -> dict[str, Any]:
    """Return a copy in the unsigned draft state, whatever state the committed file is in."""

    draft = deepcopy(protocol)
    for signer in draft["signature_block"]["signers"]:
        signer.update(signed_by=None, signed_at_utc=None, attestation=None)
    draft["signature_block"]["amendments_at_signing"] = []
    for entry in draft["drafter_readings"]:
        entry["status"] = AWAITING
    if draft["status"] == "signed":
        draft["status"] = "draft_for_signature"
    return draft


def _signed_copy(protocol: dict[str, Any], *, same_person: bool = False) -> dict[str, Any]:
    """Return a copy with the signature block filled and every reading confirmed (synthetic)."""

    signed = deepcopy(protocol)
    signed["status"] = "signed"
    names = ("I Putu Pramana Putra", "I Putu Pramana Putra" if same_person else "Rachmania Ulwani")
    for signer, name in zip(signed["signature_block"]["signers"], names):
        signer.update(signed_by=name, signed_at_utc="2026-10-02T03:00:00Z", attestation="Synthetic test entry.")
    for entry in signed["drafter_readings"]:
        entry["status"] = "confirmed"
    return signed


def _synthetic_value(pointer: str) -> Any:
    """A placeholder that satisfies the schema for one v1b parameter. Not a result."""

    leaf = pointer.rsplit("/", 1)[-1]
    if leaf.endswith("sha256"):
        return "0" * 63 + "1"
    if leaf == "result":
        return {
            "walking_closed_edges": 1824,
            "vehicle_closed_edges": 1738,
            "closed_edge_ids_match_exactly": True,
            "evidence_sha256": "0" * 63 + "2",
        }
    if leaf == "binding":
        return "bound_in_first_run_receipt"
    if leaf == "within_routing_context_for_named_ways":
        return True
    if leaf == "hospital_count":
        return 4
    if leaf == "baseline_vehicle_no_route_share":
        return 0.05
    if leaf in {"P5", "P10", "P75", "P90", "P95", "wall_time_minutes", "peak_ram_gib"}:
        return 0.5
    if leaf in {
        "edge_count", "grade_split_count", "join_count", "unit_count", "excluded_unit_count", "osm_hospitals",
        "dga_matched_hospitals", "located_ddpm_shelters", "corroborated_shelters", "k",
        "coincidence_tolerance_m", "motorway", "residential", "unclassified", "shelter_match_distance_m",
        "threshold_minutes", "plus", "vector_products",
    }:
        return 1
    if leaf == "unit_list":
        return ["synthetic unit"]
    return "synthetic placeholder for a schema test"


def _filled_v1b(protocol: dict[str, Any], v1a_sha256: str) -> dict[str, Any]:
    """Return a copy of v1b with every open item closed and every parameter filled (synthetic)."""

    filled = _as_draft(protocol)
    for item in filled["open_items"]:
        for pointer in item["parameter_pointers"]:
            _set_pointer(filled, pointer, _synthetic_value(pointer))
        item["status"] = "closed"
        item["closure"] = {
            "closed_on": "2026-10-02",
            "closed_by": "test",
            "value_or_location": "synthetic",
            "evidence_sha256": None,
        }
    filled["depends_on"]["v1a_sha256"] = v1a_sha256
    for section in SECTIONS_WITH_STATUS:
        filled[section]["status"] = "fixed"
    filled["status"] = "draft_for_signature"
    return filled


def _git(*args: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    except FileNotFoundError:
        return None


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
    assert raw == _encode(json.loads(raw.decode("ascii")))


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
        assert signers[0]["signed_by"].strip().casefold() != signers[1]["signed_by"].strip().casefold()


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_draft_does_not_claim_to_be_in_force(name: str, protocols: dict[str, dict[str, Any]]) -> None:
    if EXPECTED_STATUS[name] not in DRAFT_STATUSES:
        pytest.skip("signed file: force is read from RECEIPTS.jsonl (see the receipt test below)")
    text = PROTOCOL_PATHS[name].read_text(encoding="utf-8").lower()
    for term in ALLOWED_PLAN_TERMS:
        text = text.replace(term, "")
    assert "frozen" not in text
    assert "hashed" not in text
    assert "preregistered" not in protocols[name]["protocol_kind"]
    assert "not in force" in text or "nothing in this file is in force" in text
    for path, node in _walk(protocols[name]):
        key = path[-1] if path else ""
        if isinstance(key, str) and key in {"protocol_sha256", "self_sha256", "receipt_sha256"}:
            pytest.fail(f"draft records its own hash at {'/'.join(map(str, path))}: {node!r}")


def test_t4_admission_keeps_the_plan_wording(protocols: dict[str, dict[str, Any]]) -> None:
    t4 = next(tier for tier in protocols["v1a"]["evidence_tier_model"]["tiers"] if tier["tier"] == "T4")
    assert "frozen hold-out" in t4["admission"]


def test_no_receipt_names_a_draft_protocol() -> None:
    lines = [line for line in RECEIPTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "RECEIPTS.jsonl is empty"
    for line in lines:
        record = json.loads(line)
        assert record["schema_version"] == "floodguard.proposal_execution_receipt.v1"
    for name, status in EXPECTED_STATUS.items():
        if status in DRAFT_STATUSES:
            assert not any(f"planning_protocol_{name}" in line for line in lines), name


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_recorded_protocol_still_has_the_bytes_its_receipt_names(
    name: str, receipts: list[dict[str, Any]]
) -> None:
    """A protocol edited after its hash was recorded must fail here."""

    raw = PROTOCOL_PATHS[name].read_bytes()
    recorded = receipt_tool.recorded_protocol_hashes(receipts, name)
    state = receipt_tool.force_state(name, raw, receipts)
    if not recorded:
        if EXPECTED_STATUS[name] == "signed":
            assert state == "signed_not_in_force"
            pytest.skip(f"{name} is SIGNED BUT NOT IN FORCE: no line in RECEIPTS.jsonl records its hash")
        assert state == "draft"
        return
    assert EXPECTED_STATUS[name] == "signed", f"a receipt names {name}, so the file must be signed"
    assert len({entry["sha256"] for entry in recorded}) == 1, f"{name} was recorded with two different hashes"
    assert hashlib.sha256(raw).hexdigest() == recorded[-1]["sha256"], (
        f"{name} was edited after its hash was recorded; any change needs planning_protocol_v2"
    )
    assert state == "in_force"
    commit = recorded[-1]["source_commit"]
    relative = PROTOCOL_PATHS[name].relative_to(ROOT).as_posix()
    shown = _git("show", f"{commit}:{relative}")
    if shown is None or shown.returncode != 0:
        pytest.skip(f"git cannot read the signing commit {commit}; the file hash itself matches")
    assert hashlib.sha256(shown.stdout).hexdigest() == recorded[-1]["sha256"]
    ancestor = _git("merge-base", "--is-ancestor", commit, "HEAD")
    assert ancestor is not None and ancestor.returncode == 0, (
        f"the signing commit {commit} is not an ancestor of HEAD: the branch was squashed or rebased after signing"
    )


def test_force_state_notices_an_edit_after_the_receipt(protocols: dict[str, dict[str, Any]]) -> None:
    signed = _signed_copy(protocols["v1a"])
    raw = _encode(signed)
    line = {"source_commit": "0" * 40, "output_hashes": {"planning_protocol_v1a_sha256": hashlib.sha256(raw).hexdigest()}}
    assert receipt_tool.force_state("v1a", _encode(protocols["v1a"]), []) == (
        "draft" if EXPECTED_STATUS["v1a"] in DRAFT_STATUSES else "signed_not_in_force"
    )
    assert receipt_tool.force_state("v1a", raw, []) == "signed_not_in_force"
    assert receipt_tool.force_state("v1a", raw, [line]) == "in_force"

    edited = deepcopy(signed)
    edited["purpose"] += " One more sentence."
    assert receipt_tool.force_state("v1a", _encode(edited), [line]) == "hash_mismatch"
    second = {"source_commit": "1" * 40, "output_hashes": {"planning_protocol_v1a_sha256": "f" * 64}}
    assert receipt_tool.force_state("v1a", raw, [line, second]) == "hash_mismatch"


def test_schema_refuses_a_signature_on_a_draft_and_a_signed_file_without_one(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    for name in ("v1a", "v1b"):
        base = _as_draft(protocols["v1a"]) if name == "v1a" else _filled_v1b(protocols["v1b"], "0" * 64)
        draft = deepcopy(base)
        draft["status"] = "draft_for_signature"
        for signer in draft["signature_block"]["signers"]:
            signer.update(signed_by=None, signed_at_utc=None, attestation=None)
        assert _errors(schemas[name], draft) == [], name
        draft["signature_block"]["signers"][0]["signed_by"] = "I Putu Pramana Putra"
        assert _errors(schemas[name], draft), name

        unsigned = _signed_copy(base)
        assert _errors(schemas[name], unsigned) == [], name
        for signer in unsigned["signature_block"]["signers"]:
            signer.update(signed_by=None, signed_at_utc=None, attestation=None)
        assert _errors(schemas[name], unsigned), name


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_signer_constraints_apply_to_both_entries(
    name: str, protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    base = _as_draft(protocols["v1a"]) if name == "v1a" else _filled_v1b(protocols["v1b"], "0" * 64)
    assert _errors(schemas[name], _signed_copy(base)) == []
    for index in (0, 1):
        for field, bad in (
            ("signed_by", ""),
            ("signed_at_utc", "not a date"),
            ("attestation", ""),
            ("extra_key", "x"),
            ("signed_by", "Someone Else"),
        ):
            broken = _signed_copy(base)
            broken["signature_block"]["signers"][index][field] = bad
            assert _errors(schemas[name], broken), (name, index, field, bad)
    third = _signed_copy(base)
    third["signature_block"]["signers"].append(deepcopy(third["signature_block"]["signers"][0]))
    assert _errors(schemas[name], third)
    # The schema names each signer; the receipt script also refuses one person in both entries.
    same = _signed_copy(base, same_person=True)
    assert _errors(schemas[name], same)


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
# v1b cannot leave the draft state with an empty parameter
# ---------------------------------------------------------------------------


def test_v1b_cannot_be_signed_on_status_strings_alone(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    """Closing every item and signing, with every parameter still empty, must be refused."""

    hollow = deepcopy(protocols["v1b"])
    for item in hollow["open_items"]:
        item["status"] = "closed"
        item["closure"] = {
            "closed_on": "2026-10-02",
            "closed_by": "test",
            "value_or_location": "test",
            "evidence_sha256": None,
        }
    hollow["depends_on"]["v1a_sha256"] = "0" * 64
    if receipt_tool.empty_parameters(hollow):
        for status in ("draft_for_signature", "signed"):
            attempt = _signed_copy(hollow) if status == "signed" else deepcopy(hollow)
            attempt["status"] = status
            assert _errors(schemas["v1b"], attempt), status
    for section in SECTIONS_WITH_STATUS:
        hollow[section]["status"] = "fixed"
    if receipt_tool.empty_parameters(hollow):
        assert _errors(schemas["v1b"], _signed_copy(hollow))


def test_v1b_schema_requires_every_parameter_an_open_item_names(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    filled = _filled_v1b(protocols["v1b"], "0" * 64)
    assert receipt_tool.empty_parameters(filled) == []
    assert _errors(schemas["v1b"], filled) == []
    assert _errors(schemas["v1b"], _signed_copy(filled)) == []

    pointers = [pointer for item in filled["open_items"] for pointer in item["parameter_pointers"]]
    assert len(pointers) == len(set(pointers))
    for pointer in pointers:
        for candidate in (filled, _signed_copy(filled)):
            emptied = deepcopy(candidate)
            _set_pointer(emptied, pointer, None)
            assert _errors(schemas["v1b"], emptied), pointer

    for section in SECTIONS_WITH_STATUS:
        reopened = deepcopy(filled)
        reopened[section]["status"] = "open"
        assert _errors(schemas["v1b"], reopened), section

    for pointer, bad in (
        ("/corridor_polygon/e0_spike_record/hospital_count", 3),
        ("/corridor_polygon/e0_spike_record/baseline_vehicle_no_route_share", 0.11),
        ("/corridor_polygon/e0_spike_record/within_routing_context_for_named_ways", False),
    ):
        failing = deepcopy(filled)
        _set_pointer(failing, pointer, bad)
        assert _errors(schemas["v1b"], failing), pointer
    mismatch = deepcopy(filled)
    mismatch["closure_rule_v1"]["regression"]["result"]["closed_edge_ids_match_exactly"] = False
    assert _errors(schemas["v1b"], mismatch)

    bound = deepcopy(filled)
    bound["critical_link_selection"]["ranking_output"]["binding"] = "bound_here"
    assert _errors(schemas["v1b"], bound), "bound_here needs the ranking path and SHA-256"
    bound["critical_link_selection"]["ranking_output"].update(path="outputs/x.json", sha256="0" * 63 + "3")
    assert _errors(schemas["v1b"], bound) == []


def test_v1b_open_items_name_real_parameters_and_cover_every_empty_one(
    protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    named: set[str] = set()
    for item in protocol["open_items"]:
        assert item["parameter_pointers"], item["id"]
        for pointer in item["parameter_pointers"]:
            receipt_tool.resolve_pointer(protocol, pointer)  # raises if the pointer is stale
            named.add(pointer)
    # A closed item has every parameter filled; nothing is closed on a status string alone.
    assert receipt_tool.empty_parameters(protocol, closed_only=True) == []

    # Every empty value in the file is named by an open item, or is one of the slots below.
    allowed = re.compile(
        r"^/signature_block/signers/\d+/(signed_by|signed_at_utc|attestation)$"
        r"|^/downloads_requiring_owner_approval/\d+/(approved|approved_by|approved_on)$"
        r"|^/open_items/\d+/closure/evidence_sha256$"
        r"|/(ranking_output|add_destination_nodes)/(path|sha256)$"  # required only when binding is bound_here
    )
    orphans = []
    for path, node in _walk(protocol):
        pointer = "/" + "/".join(str(part) for part in path)
        if node is None and pointer not in named and not allowed.search(pointer):
            orphans.append(pointer)
    assert orphans == [], "empty parameters that no open item names"

    # Each section lists exactly the open items that point into it.
    for section in SECTIONS_WITH_STATUS:
        pointing = {
            item["id"]
            for item in protocol["open_items"]
            if any(pointer.startswith(f"/{section}/") for pointer in item["parameter_pointers"])
        }
        assert pointing <= set(protocol[section]["open_items"]), section
        still_open = [
            item["id"] for item in protocol["open_items"]
            if item["id"] in protocol[section]["open_items"] and item["status"] == "open"
        ]
        assert (protocol[section]["status"] == "open") == bool(still_open), section


# Slots that hold an owner decision. The drafting agent may put a proposal beside them, never a value in
# them: each stays empty while the open item that names it is open (review of 3 October 2026).
OWNER_DECISION_SLOTS = {
    "OI-01": ["/corridor_polygon/context_call/demand_area_rule"],
    "OI-03": ["/corridor_polygon/acceptance/hospital_count_unit"],
    "OI-04": ["/grade_join_policy/coincidence_tolerance_m"],
    "OI-05": [
        "/closure_rule_v1/unassigned_road_classes/length_threshold_m/motorway",
        "/closure_rule_v1/unassigned_road_classes/length_threshold_m/residential",
        "/closure_rule_v1/unassigned_road_classes/length_threshold_m/unclassified",
        "/closure_rule_v1/delay_under_strict/rule",
        "/closure_rule_v1/culvert_tag_handling/rule",
    ],
    "OI-08": [
        "/national_vulnerability_anchors/method/unit_set",
        "/national_vulnerability_anchors/method/percentile_method",
    ],
    "OI-09": [
        "/corridor_polygon/se2_frame/se2_blind_unit_rule",
        "/corridor_polygon/se2_frame/se2_blind_unit_list",
    ],
}


def test_v1b_owner_decision_slots_stay_empty_while_their_item_is_open(
    protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    items = {item["id"]: item for item in protocol["open_items"]}
    for identifier, pointers in OWNER_DECISION_SLOTS.items():
        answered = set(items[identifier].get("owner_answer", {}).get("pointers_filled", []))
        for pointer in pointers:
            assert pointer in items[identifier]["parameter_pointers"], (identifier, pointer)
            if items[identifier]["status"] == "open" and pointer not in answered:
                assert receipt_tool.resolve_pointer(protocol, pointer) is None, (
                    f"{pointer} is filled in while {identifier} is open and no owner answer names it"
                )

    # The SE2-blind district alone does not define the case: the unit rule and the unit list have their own slots.
    blind = protocol["corridor_polygon"]["se2_frame"]["se2_blind_district"]
    assert blind is None or "still_missing" not in blind

    # The plan's culvert tags stay listed; what the code can read is a separate, gated statement.
    closure = protocol["closure_rule_v1"]
    assert closure["parameters"]["bridge_culvert_tags"] == ["bridge=yes", "tunnel=culvert", "culvert=*"]
    if items["OI-05"]["status"] == "open":
        assert "awaiting an owner decision" in closure["bridge_culvert_note"]


# Owner choices answered with values for real tambons already in view (owner-choices sheet entries 4, 6, 13
# and 15). Decision log R12 approved them as recommended and gave no separate reason.
OUTCOME_AWARE_ITEMS = {"OI-05": 4, "OI-08": 6, "OI-12": 13, "OI-09": 15}
R12_LINE_SHA256 = "8c3f7e20cedabb8f4593311f1f3603880595cc40994006b6253e0b92cc579f50"


def test_v1b_owner_answers_on_open_items_fill_only_what_the_owners_decided(
    protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    for item in protocol["open_items"]:
        answer = item.get("owner_answer")
        if answer is None:
            continue
        assert "R12" in answer["answered_by"] and answer["answer"].strip(), item["id"]
        assert set(answer["pointers_filled"]) <= set(item["parameter_pointers"]), item["id"]
        for pointer in answer["pointers_filled"]:
            assert receipt_tool.resolve_pointer(protocol, pointer) is not None, (item["id"], pointer)
        if item["status"] == "open":
            # An item whose parameters are all filled is closed, not left open with an answer.
            assert any(
                receipt_tool.resolve_pointer(protocol, pointer) is None for pointer in item["parameter_pointers"]
            ), item["id"]
            assert answer["still_needed"].strip(), item["id"]


def test_v1b_items_closed_on_owner_answers_quote_the_decision(protocols: dict[str, dict[str, Any]]) -> None:
    protocol = protocols["v1b"]
    items = {item["id"]: item for item in protocol["open_items"]}
    record = protocol["source_documents"].get("decision_log_at_owner_choices")
    for item in items.values():
        closure = item.get("closure")
        if closure is None or "R12" not in closure["closed_by"]:
            continue
        assert record is not None and record["r12_line_sha256"] == R12_LINE_SHA256
        assert "entered by the AI coding agent" in closure["closed_by"], item["id"]
        assert closure["evidence_sha256"] and "owner choice" in closure["value_or_location"], item["id"]
    for identifier, entry in OUTCOME_AWARE_ITEMS.items():
        item = items[identifier]
        text = item["closure"]["value_or_location"] if "closure" in item else item.get("owner_answer", {}).get("answer")
        if not text:
            continue
        # The owners gave no reason of their own; the record says so and quotes the recommendation's reason.
        assert f"owner choice {entry}" in text, identifier
        assert "none given" in text and "recommendation's reason" in text and "outcome-aware" in text, identifier


def test_v1b_anchor_candidates_are_not_presented_as_decided(protocols: dict[str, dict[str, Any]]) -> None:
    protocol = protocols["v1b"]
    anchors = protocol["national_vulnerability_anchors"]
    item = next(item for item in protocol["open_items"] if item["id"] == "OI-08")
    candidates = anchors.get("anchor_candidates")
    if item["status"] == "open":
        assert anchors["status"] == "open" and "closure" not in item
        assert set(anchors["output_receipt"].values()) == {None}
        assert candidates is not None, "candidate anchors are kept beside the empty slots"
    if candidates is None:
        return
    rules = {rule["id"]: rule for rule in candidates["rules"]}
    assert set(rules) >= {"A", "B", "C", "D"}
    assert [rule["id"] for rule in candidates["rules"] if rule["is_the_proposal_in_this_file"]] == ["A"]
    for rule in rules.values():
        ordered = [rule["values"][key] for key in ("P5", "P10", "P75", "P90", "P95")]
        assert all(0 < value < 1 for value in ordered) and ordered == sorted(set(ordered)), rule["id"]
    # The choice is made with component inputs for real tambons in view, and the file says so.
    added = {entry["id"]: entry for entry in protocol["depends_on"]["exploratory_knowledge_added_for_v1b"]}
    assert "EK-B01" in candidates["outcome_awareness"] and "EK-04" in added["EK-B01"]["what_was_already_known"]
    assert "outcome-aware" in added["EK-B01"]["could_bias"]
    assert "exploratory_knowledge_added_for_v1b" in protocol["depends_on"]["exploratory_knowledge_disclosure"]
    if item["status"] == "closed":
        # The values in force are the chosen rule's values, copied from the receipt the candidates came from.
        decision = anchors["owner_decision"]
        assert anchors["values"] == rules[decision["rule_chosen"]]["values"]
        assert anchors["output_receipt"]["sha256"] == candidates["evidence_sha256"] == item["closure"]["evidence_sha256"]
        assert anchors["output_receipt"]["unit_count"] == rules[decision["rule_chosen"]]["unit_count"]
        assert "none given" in decision["owners_reason"] and "EK-B01" in decision["outcome_awareness"]


def test_v1b_spike_candidates_say_which_acceptance_criteria_are_met(protocols: dict[str, dict[str, Any]]) -> None:
    protocol = protocols["v1b"]
    items = {item["id"]: item for item in protocol["open_items"]}
    block = protocol["corridor_polygon"].get("e0_spike_candidates")
    if block is None:
        return
    for candidate in block["candidates"]:
        met = candidate["meets_plan_acceptance"]
        assert isinstance(met, dict), "one entry per criterion, not one flag"
        assert set(met) == {
            "hospitals_in_context_min", "named_ways_within_routing_context", "baseline_vehicle_no_route_share_max",
            "declared_compute_window", "all_criteria_met",
        }
        assert met["all_criteria_met"] == all(value for key, value in met.items() if key != "all_criteria_met")
        assert met["named_ways_within_routing_context"] == all(candidate["named_ways_within_routing_context"].values())
        breakdown = candidate["hospital_count_breakdown"]
        assert breakdown["osm_objects"] == candidate["hospital_count"]
        assert breakdown["osm_objects"] == (
            breakdown["distinct_named_hospitals"] + breakdown["unnamed_objects"]
            + breakdown["objects_that_repeat_a_named_hospital"]
        )
    if items["OI-03"]["status"] == "open":
        # A run outside a declared compute window cannot close OI-03 (plan 5 item 1).
        assert "compute window" in items["OI-03"]["produced_by"] and "compute window" in items["OI-03"]["note"]
    record = protocol["corridor_polygon"]["e0_spike_record"]
    if any(value is not None for value in record.values()):
        assert items["OI-02"]["status"] == "closed"


def test_v1b_lists_every_engineering_run_with_its_receipt(protocols: dict[str, dict[str, Any]]) -> None:
    runs = protocols["v1b"]["blinding"]["runs_before_v1b_is_in_force"]
    receipts_named = [run["receipt"] for run in runs]
    assert len(receipts_named) == len(set(receipts_named))
    for run in runs:
        path = ROOT / run["receipt"]
        assert path.is_file(), run["receipt"]
        receipt = json.loads(path.read_text(encoding="ascii"))
        assert receipt["generated_at_utc"] == run["generated_at_utc"], run["receipt"]
        assert isinstance(run["per_unit_values_written"], bool)
        if run["per_unit_values_written"]:
            assert run["per_unit_values_note"].strip()
        for earlier in run.get("earlier_runs", []):
            assert earlier["generated_at_utc"] < run["generated_at_utc"] and len(earlier["evidence_sha256"]) == 64
    committed = sorted(
        [
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "outputs" / "planning_v1").glob("*.json")
            if "grade_join_log" not in path.name
        ]
        # Planning-frame builds name tambons, so their receipts sit beside the frames, not in outputs/.
        + [path.relative_to(ROOT).as_posix() for path in (ROOT / "resources" / "planning_frames").glob("*_receipt.json")]
    )
    assert sorted(receipts_named) == committed


def test_v1b_points_at_the_recorded_v1a(
    protocols: dict[str, dict[str, Any]], receipts: list[dict[str, Any]]
) -> None:
    depends = protocols["v1b"]["depends_on"]
    assert (ROOT / depends["v1a_path"]) == PROTOCOL_PATHS["v1a"]
    declared = depends["v1a_sha256"]
    recorded = receipt_tool.recorded_protocol_hashes(receipts, "v1a")
    if declared is None:
        assert EXPECTED_STATUS["v1b"] == "incomplete_draft"
        return
    assert EXPECTED_STATUS["v1a"] == "signed"
    assert declared == hashlib.sha256(PROTOCOL_PATHS["v1a"].read_bytes()).hexdigest()
    assert recorded, "v1b names a v1a hash but RECEIPTS.jsonl records none"
    assert declared == recorded[-1]["sha256"]


def test_receipt_script_refuses_what_the_guide_says_it_refuses(
    protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    problems = receipt_tool.signing_problems
    draft_a = _encode(protocols["v1a"])
    if EXPECTED_STATUS["v1a"] in DRAFT_STATUSES:
        assert any("not 'signed'" in problem for problem in problems("v1a", draft_a, schemas["v1a"]))

    signed_a = _encode(_signed_copy(protocols["v1a"]))
    assert problems("v1a", signed_a, schemas["v1a"]) == []
    one_person = _encode(_signed_copy(protocols["v1a"], same_person=True))
    assert any("two different people" in problem for problem in problems("v1a", one_person, schemas["v1a"]))
    unconfirmed = _signed_copy(protocols["v1a"])
    unconfirmed["drafter_readings"][0]["status"] = AWAITING
    assert any("await" in problem for problem in problems("v1a", _encode(unconfirmed), schemas["v1a"]))
    assert any("LF" in problem for problem in problems("v1a", signed_a.replace(b"\n", b"\r\n"), schemas["v1a"]))

    sha_a = hashlib.sha256(signed_a).hexdigest()
    receipt_a = {"source_commit": "0" * 40, "output_hashes": {"planning_protocol_v1a_sha256": sha_a}}
    assert any("already records" in problem for problem in problems("v1a", signed_a, schemas["v1a"], receipts=[receipt_a]))

    good_b = _encode(_signed_copy(_filled_v1b(protocols["v1b"], sha_a)))
    assert problems("v1b", good_b, schemas["v1b"], receipts=[receipt_a], v1a_bytes=signed_a) == []
    # v1a signed but not recorded: v1b cannot be recorded.
    assert any("not in force" in problem for problem in problems("v1b", good_b, schemas["v1b"], v1a_bytes=signed_a))
    # A made-up v1a hash.
    zeros = _encode(_signed_copy(_filled_v1b(protocols["v1b"], "0" * 64)))
    found = problems("v1b", zeros, schemas["v1b"], receipts=[receipt_a], v1a_bytes=signed_a)
    assert any("not the SHA-256 of the committed v1a" in problem for problem in found)
    assert any("not the value in the v1a receipt" in problem for problem in found)
    # Closed on status strings alone.
    hollow = _signed_copy(protocols["v1b"])
    for item in hollow["open_items"]:
        item["status"] = "closed"
    hollow["depends_on"]["v1a_sha256"] = sha_a
    found = problems("v1b", _encode(hollow), schemas["v1b"], receipts=[receipt_a], v1a_bytes=signed_a)
    if receipt_tool.empty_parameters(protocols["v1b"]):
        assert any("are empty" in problem for problem in found)

    receipt = receipt_tool.build_receipt(
        "v1a", commit="0" * 40, tree="1" * 40, protocol_sha256=sha_a, input_hashes={}, test_summary="n passed",
        signed_by=["A", "B"], open_decisions=OPEN_DECISIONS, time_utc="2026-10-02T03:00:00Z",
    )
    existing = json.loads(RECEIPTS.read_text(encoding="utf-8").splitlines()[0])
    assert {"schema_version", "result", "source_commit", "source_tree", "output_hashes", "milestone"} <= set(receipt)
    assert receipt["schema_version"] == existing["schema_version"]
    assert receipt["human_acceptance"] is False and receipt["official_warning"] is False
    assert "D5, D8, D10, D14, D15, D16" in receipt["limitations"]


# ---------------------------------------------------------------------------
# Readings the drafting agent made: flagged in the file and in the guide
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_every_drafter_reading_is_flagged_where_it_applies(
    name: str, protocols: dict[str, dict[str, Any]], schemas: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols[name]
    readings = {entry["id"]: entry for entry in protocol["drafter_readings"]}
    assert len(readings) == len(protocol["drafter_readings"])
    assert set(REQUIRED_READINGS[name]) <= set(readings)
    guide = SIGNING_GUIDE.read_text(encoding="utf-8")
    for identifier, entry in readings.items():
        marker = receipt_tool.resolve_pointer(protocol, entry["pointer"])
        assert isinstance(marker, str) and identifier in marker, identifier
        assert entry["plan_says"].strip() and entry["draft_says"].strip(), identifier
        if EXPECTED_STATUS[name] in DRAFT_STATUSES:
            assert entry["status"] == AWAITING, identifier
            assert identifier in guide, f"{identifier} is not listed in the signing guide"
        else:
            assert entry["status"] in {"confirmed", "amended"}, identifier
    # Every "Drafter reading DR-..." marker in the file is in the registry.
    text = PROTOCOL_PATHS[name].read_text(encoding="utf-8")
    prefix = "DR-A" if name == "v1a" else "DR-B"
    assert set(re.findall(rf"{prefix}\d{{2}}", text)) == set(readings)
    # A signed file cannot keep a reading that awaits confirmation.
    base = _as_draft(protocol) if name == "v1a" else _filled_v1b(protocol, "0" * 64)
    pending = _signed_copy(base)
    pending["drafter_readings"][0]["status"] = AWAITING
    assert _errors(schemas[name], pending)


def test_plan_gaps_are_resolved_in_the_open_and_marked_as_readings(
    protocols: dict[str, dict[str, Any]]
) -> None:
    v1a, v1b = protocols["v1a"], protocols["v1b"]

    # Scenario rows: how C1 applies to tier T1 is stated and marked, not left to the implementer.
    scenario = v1a["confidence_rule_v1"]["scenario_rows"]
    assert "DR-A07" in scenario["rule_status"]
    assert any("C1" in line for line in scenario["rule"]) and scenario["alternatives"]
    assert "scenario_rows" in next(
        tier for tier in v1a["evidence_tier_model"]["tiers"] if tier["tier"] == "T1"
    )["max_confidence"]
    assert all(case["tier"] == "T1" for case in v1a["case_portfolio"]["cases"] if case["lane"] == "SCN-ENV")

    # Class rule v2: an order and an outcome when nothing matches.
    evaluation = v1a["class_rules"]["v2"]["evaluation"]
    assert sorted(evaluation["order"]) == ["A", "B", "C", "D", "E"] and evaluation["order"][0] == "E"
    assert evaluation["otherwise"] and "DR-A08" in evaluation["rule_status"]

    # Fewer than 100 residents: which rule wins is stated.
    gr1 = next(guardrail for guardrail in v1a["guardrails"] if guardrail["id"].startswith("GR1_"))
    assert "GR1" in gr1["precedence"] and "C6" in gr1["precedence"] and "DR-A09" in gr1["precedence_status"]

    # Plan wording restored or kept, with the reading beside it.
    assert "OBS or SCN lanes" in v1a["evidence_tier_model"]["no_assumed_components_in_obs_or_scn"]
    gr5 = next(guardrail for guardrail in v1a["guardrails"] if guardrail["id"].startswith("GR5_"))
    assert "DR-A06" in gr5["rule_status"] and "EK-R1" in gr5["known_departure"]
    for block in (v1a["signature_block"], v1b["signature_block"]):
        attestations = " ".join(block["attestations_required"])
        assert "planning-tier" not in attestations
        assert "since the plan date (2026-09-26)" in attestations
        assert "drafter_readings" in attestations
    assert "DR-A04" in v1a["demo_tambon_rule"]["rule_status"]

    # The flood-anchor count caveat is inside the file, not only in the guide.
    anchor = v1a["scoring_frame"]["components"]["flood_likelihood_0_100"]
    assert "5 of 8" in anchor["anchor_disclosure"] and "6 of the 8" in anchor["anchor_disclosure"]

    # The passability pairing is marked on both the rule and the ensemble axis.
    assert "DR-B01" in v1b["closure_rule_v1"]["delay_factor_pairing_status"]
    passability = next(axis for axis in v1b["ensemble_grid"]["core_axes"] if axis["axis"] == "passability")
    assert "DR-B01" in passability["levels_status"]


def test_guide_lists_every_open_item_and_does_not_overstate(protocols: dict[str, dict[str, Any]]) -> None:
    guide = SIGNING_GUIDE.read_text(encoding="utf-8")
    items = protocols["v1b"]["open_items"]
    for item in items:
        assert f"| {item['id']} |" in guide, item["id"]
    open_count = sum(item["status"] == "open" for item in items)
    if open_count == len(items):
        # The count in the guide describes the draft as handed over; it is not updated as items close.
        assert f"{open_count} open items" in guide
    assert "Everything the plan fixes is filled in. The rest are open items" not in guide
    for phrase in ("never squash", "git merge-base --is-ancestor", "scripts/record_planning_protocol_receipt.py"):
        assert phrase in guide, phrase
    assert 'EXPECTED_STATUS["v1b"]' in guide and "draft_for_signature" in guide
    assert f"{len(protocols['v1a'][DISCLOSURE_KEY]['items'])} items" in guide


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
    # v1a never carries the anchor values; they are recorded in v1b.
    assert set(vulnerability["anchor_values"].values()) == {None}

    assert frame["leave_one_component_out"]["required_on_every_row"] is True
    assert "0.20" in frame["signed_decision_text"]


def test_national_anchor_values_are_empty_until_their_open_item_is_closed(
    protocols: dict[str, dict[str, Any]]
) -> None:
    anchors = protocols["v1b"]["national_vulnerability_anchors"]
    assert set(anchors["values"]) == {"P5", "P10", "P75", "P90", "P95"}
    item = next(item for item in protocols["v1b"]["open_items"] if item["id"] == "OI-08")
    values = anchors["values"]
    if item["status"] == "open":
        # Fill the values and close OI-08 in the same edit, with the output receipt.
        assert set(values.values()) == {None}
        assert anchors["download_needed"] is False
        assert anchors["inputs"]["age_rasters"]["on_disk"] is True
    else:
        assert all(_is_number(value) and 0 <= value <= 1 for value in values.values())
        assert values["P5"] <= values["P10"] <= values["P75"] <= values["P90"] <= values["P95"]
        assert anchors["output_receipt"]["sha256"]


# ---------------------------------------------------------------------------
# v1a: class rules equal the scoring code (D6); plan thresholds are pinned
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


def test_v2_is_a_secondary_axis_with_the_plan_parameters(protocols: dict[str, dict[str, Any]]) -> None:
    rules = protocols["v1a"]["class_rules"]
    assert "D6" in rules["basis"]
    v2 = rules["v2"]
    assert v2["binding"] is False
    assert v2["role"] == "predeclared secondary axis"
    assert set(v2["triggers"]) == {"A", "B", "C", "D", "E"}
    assert v2["parameters"] == {
        "national_dependent_share_percentile": "P75",
        "critical_link_rank_max": 20,
        "isolated_residents_min": 500,
        "fpps_min": 35,
        "jrc_occurrence_min_percent": 25,
        "exposure_floor_for_non_e": 10,
    }
    triggers = v2["triggers"]
    assert "P75" in triggers["A"]
    assert "top-20" in triggers["B"] and "500" in triggers["B"]
    assert "35" in triggers["C"] and "uniquely located" in triggers["C"]
    assert "25 percent" in triggers["D"] and "same season" in triggers["D"]
    assert "below 10" in triggers["E"] and "below 35" in triggers["E"]


def test_confidence_skill_bar_guardrail_and_equity_thresholds_match_the_plan(
    protocols: dict[str, dict[str, Any]]
) -> None:
    v1a = protocols["v1a"]
    conditions = {condition["id"]: condition for condition in v1a["confidence_rule_v1"]["medium_requires_all"]}
    assert list(conditions) == [
        "C1_tier", "C2_recency", "C3_coverage", "C4_input_uncertainty", "C5_components", "C6_residents",
        "C7_baseline_no_route", "C8_hospital",
    ]
    assert conditions["C2_recency"]["threshold"] == {"recency_window_days": 3}
    assert conditions["C3_coverage"]["threshold"] == {"unit_valid_coverage_min": 0.8}
    assert conditions["C4_input_uncertainty"]["threshold"] == {
        "exposure_plus_minus_one_pixel_max_points": 15,
        "t2_abstention_fraction_max": 0.2,
    }
    assert conditions["C6_residents"]["threshold"] == {"unit_residents_min": 100}
    assert conditions["C7_baseline_no_route"]["threshold"] == {"baseline_vehicle_no_route_share_max": 0.1}
    assert conditions["C8_hospital"]["threshold"] == {"hospitals_reachable_at_baseline_min": 1}
    assert v1a["confidence_rule_v1"]["uses_ensemble_output"] is False
    assert v1a["confidence_rule_v1"]["rights_are_an_input"] is False

    assert v1a["t2_skill_bar"]["conditions"] == {
        "geoid_held_out_test_iou_min": 0.4,
        "mae_sai_abstention_fraction_max": 0.2,
        "mae_sai_unit_coverage_min": 0.8,
        "recency_window_days": 3,
    }
    assert v1a["t2_skill_bar"]["declared_unable_to_meet"] == [
        "legacy 2.25 dB mask", "UN-SPIDER reproduction", "M1-literal",
    ]

    guardrails = {guardrail["id"]: guardrail for guardrail in v1a["guardrails"]}
    assert guardrails["GR1_minimum_denominators"]["parameters"] == {
        "unit_residents_min_for_class": 100,
        "group_min_for_ratio": 50,
    }
    assert guardrails["GR8_headline_stability"]["parameters"] == {"class_retention_min": 0.6}
    assert guardrails["GR6_publication_eligibility"]["values"] == ["local", "pitch", "public"]
    assert v1a["equity_statement_rule"]["parameters"] == {"group_min_for_ratio": 50, "sign_retention_min": 0.6}
    assert v1a["equity_statement_rule"]["otherwise_fixed_sentence"] == (
        "no age-group gap distinguishable from zero under the tested assumptions"
    )


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
    # The OBS lane is defined by a reference date, so every OBS case has one.
    for case in portfolio["cases"]:
        if case["lane"] == "OBS":
            assert case["case_reference_date"], case["id"]
    h1 = next(case for case in portfolio["cases"] if case["id"] == "H1")
    assert "DR-A12" in h1["case_reference_date_status"]


def test_date_rule_matches_d3(protocols: dict[str, dict[str, Any]]) -> None:
    rule = protocols["v1a"]["date_rule"]
    assert rule["recency_window_days"] == 3
    assert rule["product_4009"]["accumulated_layer"]["lane"] == "SCN-ENV"
    assert rule["product_4009"]["accumulated_layer"]["use"] == "scenario only"
    assert rule["product_4009"]["layer_22_oct"]["case"] == "O2"
    recency = protocols["v1a"]["confidence_rule_v1"]["medium_requires_all"][1]
    assert recency["threshold"] == {"recency_window_days": 3}
    # Every temporal_relation in the file is one of the declared values.
    declared = set(rule["temporal_relation_values"])
    assert declared == {"event_aligned", "dated_other", "season_window"}
    for path, node in _walk(protocols["v1a"]):
        if path and path[-1] == "temporal_relation":
            assert node in declared, path
    assert "O2 only" in rule["product_4009"]["layer_22_oct"]["temporal_relation_scope"]


def test_all_nine_guardrails_and_every_rule_section_cite_a_basis(
    protocols: dict[str, dict[str, Any]]
) -> None:
    v1a = protocols["v1a"]
    assert [guardrail["id"][:3] for guardrail in v1a["guardrails"]] == [f"GR{n}" for n in range(1, 10)]
    for guardrail in v1a["guardrails"]:
        assert any("plan 2.3" in basis for basis in guardrail["basis"])
        # A guardrail says whether anything enforces it yet; none is presented as built when it is not.
        assert guardrail["enforcement"]["status"] in {"in_place", "partly_in_place", "not_built"}
        assert guardrail["enforcement"]["note"].strip()
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


def test_guardrails_do_not_claim_controls_that_are_missing(protocols: dict[str, dict[str, Any]]) -> None:
    if EXPECTED_STATUS["v1a"] not in DRAFT_STATUSES:
        pytest.skip("enforcement statuses describe the lineage on the drafting date")
    guardrails = {guardrail["id"]: guardrail for guardrail in protocols["v1a"]["guardrails"]}
    if not (ROOT / "scripts" / "verify_planning_assessment.py").exists():
        for identifier in ("GR2_no_max_normalisation", "GR3_lane_purity"):
            assert guardrails[identifier]["enforcement"]["status"] == "not_built"
            assert "must" in guardrails[identifier]["rule"]
    assert guardrails["GR9_ait_mbrsc_guard"]["enforcement"]["status"] == "not_built"
    assert "must fail" in guardrails["GR9_ait_mbrsc_guard"]["rule"]


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
        assert "drafter_readings" in rules


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
        assert isinstance(item["real_tambon_component_values_seen"], bool), item["id"]
        # A guard that names a control which does not exist yet says so.
        assert (item["guard_status"] == "control_missing") == bool(item["guard_gaps"]), item["id"]


def test_disclosure_covers_the_items_the_plan_and_the_owner_named(
    protocols: dict[str, dict[str, Any]]
) -> None:
    items = protocols["v1a"][DISCLOSURE_KEY]["items"]
    titles = " | ".join(item["title"].lower() for item in items)
    for phrase in (
        "gap-1", "gap-4", "decision-engine", "flood-anchor saturation", "all-tile geoid", "hat yai closure",
    ):
        assert phrase in titles, phrase

    replay = {item["id"]: item for item in items if item["lineage"] == "replay_lineage_master"}
    assert sorted(replay) == ["EK-R1", "EK-R2", "EK-R3", "EK-R4", "EK-R5"]
    first = replay["EK-R1"]
    assert "2e5a099" in first["what_was_seen"]
    assert "89.34" in first["what_was_seen"] and "31.27" in first["what_was_seen"]
    assert first["real_tambon_scores_or_classes_seen"] is True
    assert any("2e5a099" in location["value"] for location in first["locations"])
    assert "calibration-informed" in replay["EK-R2"]["what_was_seen"]
    assert "0.48" in replay["EK-R3"]["what_was_seen"]
    assert "VIIRS" in replay["EK-R4"]["what_was_seen"]
    assert "d942cb0" in replay["EK-R5"]["what_was_seen"] and "Equity Gap" in replay["EK-R5"]["what_was_seen"]


def test_disclosure_does_not_understate_what_was_seen(protocols: dict[str, dict[str, Any]]) -> None:
    items = {item["id"]: item for item in protocols["v1a"][DISCLOSURE_KEY]["items"]}

    # The replay commit showed would-be (score-implied) classes, not only class E, after the plan's rule.
    first = items["EK-R1"]
    seen = first["what_was_seen"]
    assert "score_implied_class" in seen and "A to D" in seen and "departure" in seen
    assert "26 Sep 2026" in seen and "28 Sep 2026" in seen
    assert "class_rules.v1.would_be_class" in first["informed_parameters"]

    # Component values for real tambons count as seen, even where no FPPS was computed.
    for identifier in ("EK-01", "EK-02", "EK-04", "EK-05", "EK-11", "EK-R1", "EK-R3"):
        assert items[identifier]["real_tambon_component_values_seen"] is True, identifier
    for identifier in ("EK-01", "EK-04", "EK-05", "EK-11", "EK-R1"):
        assert items[identifier]["real_tambon_scores_or_classes_seen"] is True, identifier

    # The Hat Yai sweep tried the same two lengths that closure rule v1 uses.
    hat_yai = items["EK-13"]
    assert "20 m" in hat_yai["what_was_seen"] and "50 m" in hat_yai["what_was_seen"]
    assert any("closure_rule_v1" in parameter for parameter in hat_yai["informed_parameters"])
    assert any("H1" in parameter for parameter in hat_yai["informed_parameters"])
    assert (ROOT / "docs" / "proposal_execution" / "hat_yai_transfer.md").exists()

    # Guards are requirements, and missing controls are named.
    assert items["EK-02"]["guard_status"] == "control_missing"
    assert "must" in items["EK-02"]["guard"]
    assert items["EK-11"]["guard_status"] == "control_missing"
    assert "are retired from live surfaces" not in items["EK-11"]["guard"]


def test_legacy_figure_gap_is_still_true_while_the_file_is_a_draft(
    protocols: dict[str, dict[str, Any]]
) -> None:
    if EXPECTED_STATUS["v1a"] not in DRAFT_STATUSES:
        pytest.skip("guard gaps describe the lineage on the drafting date")
    items = {item["id"]: item for item in protocols["v1a"][DISCLOSURE_KEY]["items"]}
    gaps = " ".join(items["EK-11"]["guard_gaps"])
    assert "offline-demo/mae-sai" in gaps
    demo = ROOT / "apps" / "web" / "public" / "offline-demo" / "mae-sai" / "areas.json"
    assert demo.exists() and "53.65" in demo.read_text(encoding="utf-8"), (
        "the legacy figure is gone from the offline demo: update the EK-11 guard gap before signing"
    )


# ---------------------------------------------------------------------------
# Blinding: no score, class or component value for a real unit outside the disclosure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["v1a", "v1b"])
def test_no_result_for_a_real_tambon_outside_the_disclosure(
    name: str, protocols: dict[str, dict[str, Any]]
) -> None:
    outside = {key: value for key, value in protocols[name].items() if key != DISCLOSURE_KEY}
    assert _real_unit_score_findings(outside) == []


def test_the_result_detector_sees_scores_classes_and_component_values(
    protocols: dict[str, dict[str, Any]]
) -> None:
    disclosure = protocols["v1a"][DISCLOSURE_KEY]
    assert _real_unit_score_findings(disclosure), "the detector must flag the disclosed replay scores"
    planted = {"rows": [{"subdistrict_id": "TH570903", "fpps_0_100": 12.5}]}
    assert len(_real_unit_score_findings(planted)) >= 2
    assert _real_unit_score_findings({"note": "Ko Chang FPPS 12.5"})
    assert _real_unit_score_findings({"note": "Ko Chang is class B."})
    assert _real_unit_score_findings({"note": "The envelope gives B for Ko Chang and D elsewhere."})
    assert _real_unit_score_findings({"note": "Rim Kok has exposure of 85 under the envelope."})
    assert _real_unit_score_findings({"rows": [{"tambon": "Pong Pha", "would_be_class": "C"}]})
    assert _real_unit_score_findings({"rows": [{"unit_id": "TH570901", "access_gap_0_100": 40}]})
    # Rule text that names no unit, or a unit with no result, is not flagged.
    assert _real_unit_score_findings({"note": "Class E never means safe."}) == []
    assert _real_unit_score_findings({"note": "The eight Mae Sai tambons are the reporting frame."}) == []
    assert _real_unit_score_findings({"weights": {"exposure_0_100": 0.25}}) == []


# ---------------------------------------------------------------------------
# v1b: open items, downloads, grid arithmetic
# ---------------------------------------------------------------------------


def test_v1b_open_items_say_what_who_and_whether_a_download_is_needed(
    protocols: dict[str, dict[str, Any]]
) -> None:
    protocol = protocols["v1b"]
    items = {item["id"]: item for item in protocol["open_items"]}
    assert len(items) == len(protocol["open_items"])
    assert list(items) == [f"OI-{number:02d}" for number in range(1, len(items) + 1)]
    for item in items.values():
        for field in ("parameter", "what_is_missing", "produced_by", "who"):
            assert item[field].strip(), (item["id"], field)
        assert isinstance(item["download_needed"], bool)
    referenced: set[str] = set()
    for path, node in _walk({key: value for key, value in protocol.items() if key != "open_items"}):
        if path and path[-1] == "open_items":
            referenced.update(node)
    assert referenced == set(items) - {"OI-11"}  # OI-11 is the v1a hash in depends_on
    produced = " ".join(item["produced_by"] for item in items.values())
    assert "E0" in produced and "E4" in produced and "E2" in produced


def test_v1b_names_the_choices_the_plan_leaves_open(protocols: dict[str, dict[str, Any]]) -> None:
    """Parameters the review found neither fixed nor listed are now open items with a slot."""

    v1b = protocols["v1b"]
    missing = " ".join(item["what_is_missing"] for item in v1b["open_items"])
    for phrase in (
        "terrain / remoteness proxy", "2024-rescaled demand", "A6-prime", "'one pixel'", "vehicle-only ensemble",
        "add_destination node list", "which facility 'serves' a unit",
    ):
        assert phrase in missing, phrase
    grid = v1b["ensemble_grid"]
    assert grid["terrain_remoteness_proxy"]["definition"] is None or v1b["ensemble_grid"]["status"] == "fixed"
    flood_axis = grid["core_axes"][0]
    assert set(flood_axis["t2_levels_by_input"]) >= {"M1-v2", "M1-literal", "UN-SPIDER reproduction", "A6-prime classifier"}
    assert flood_axis["one_pixel_m"]["minus"] == 20
    assert "vehicle mode only" in v1b["facility_sets"]["shelters_in_the_ensemble"]["conflict"]
    assert set(v1b["class_rule_v2_inputs"]) >= {
        "trigger_B_isolation", "trigger_C_serving_facility", "trigger_D_recurrence_flag",
    }
    assert any("class_rule_v2_inputs" in line for line in protocols["v1a"]["class_rules"]["v2"]["depends_on_v1b"])


def test_v1b_downloads_record_who_approved_them(protocols: dict[str, dict[str, Any]]) -> None:
    downloads = protocols["v1b"]["downloads_requiring_owner_approval"]
    assert downloads
    for download in downloads:
        for field in ("dataset", "file", "source", "approximate_size", "needed_for"):
            assert download[field].strip(), (download["id"], field)
        if download["approved"] is None:
            assert download["approved_by"] is None and download["approved_on"] is None
        else:
            # An owner records a yes or a no, with a name and a date. Agents do not fill this in.
            assert isinstance(download["approved"], bool)
            assert download["approved_by"] and download["approved_on"]


def test_v1b_ensemble_grid_arithmetic(protocols: dict[str, dict[str, Any]]) -> None:
    grid = protocols["v1b"]["ensemble_grid"]
    counts = [axis["count"] for axis in grid["core_axes"]]
    assert all(len(axis["levels"]) == axis["count"] for axis in grid["core_axes"])
    assert math.prod(counts) == grid["core_cells_per_lane"] == 540
    assert math.prod(counts[:3]) == grid["routing_combinations_per_lane"] == 27
    assert grid["headline_rule"]["class_retention_min"] == 0.60
    weights_axis = grid["core_axes"][-1]
    assert weights_axis["levels"] == list(WEIGHT_SCENARIOS)


def test_v1b_closure_rule_parameters_are_the_plan_values(protocols: dict[str, dict[str, Any]]) -> None:
    rule = protocols["v1b"]["closure_rule_v1"]
    # The plan lists k = 2 / 4 / 6 beside the three levels; pairing them is drafter reading DR-B01.
    assert [rule["levels"][level]["delay_factor_k"] for level in ("strict", "central", "permissive")] == [2, 4, 6]
    assert "DR-B01" in rule["delay_factor_pairing_status"]
    parameters = rule["parameters"]
    assert parameters["closed_fraction_min"] == 0.5
    assert parameters["bridge_culvert_closed_fraction_min"] == 0.25
    assert parameters["delay_min_intersected_length_m"] == 20
    assert parameters["length_threshold_m_by_road_class"] == {
        "trunk": 50, "primary": 50, "secondary": 50, "tertiary": 30, "local": 30,
    }
    assert parameters["raster_minimum_polygon_px"] == 5
    assert rule["regression"]["expected_closed_edges"] == {"walking": 1824, "vehicle": 1738}
    result = rule["regression"]["result"]
    if result is not None:
        # Recorded when E3 runs. A failing run is recorded as it is; signing needs an exact match.
        if result["closed_edge_ids_match_exactly"]:
            assert result["walking_closed_edges"] == 1824 and result["vehicle_closed_edges"] == 1738
    # The permissive level must use the same threshold as the finals code it has to reproduce.
    assert "length > 1e-6" in FINALS_CLOSURE.read_text(encoding="utf-8")
    assert "1e-6 m" in rule["levels"]["permissive"]["closed_when"]


def test_signing_guide_exists_and_names_the_receipt_schema() -> None:
    text = SIGNING_GUIDE.read_text(encoding="utf-8")
    assert "floodguard.proposal_execution_receipt.v1" in text
    assert "RECEIPTS.jsonl" in text
    assert "git show" in text and "sha256" in text.lower()
    assert b"\r" not in SIGNING_GUIDE.read_bytes()
    assert receipt_tool.RECEIPT_SCHEMA_VERSION == "floodguard.proposal_execution_receipt.v1"
    assert all((ROOT / path).exists() for path in receipt_tool.TEST_PATHS)
