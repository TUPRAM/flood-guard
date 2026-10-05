"""Three records drafted for the owners on 5 October 2026, each of them pending.

* ``docs/proposal_execution/rights_basis_sentinel1_v1.json`` with its notice: a draft rights record for the two
  Sentinel-1 scenes the own radar candidates of case O1 are made from (open point E1-OP2);
* ``docs/proposal_execution/age_data_purpose_review_v1.md``: the purpose-specific review protocol v1b asks for
  before a public derivative of the 2024 age rasters (open point E8-OP5);
* ``docs/proposal_execution/walking_build_compute_window_v1.md``: the compute window of a walking context build
  of record (open point E5-OP5).

A draft is not a decision. These tests hold two things for each record. What it says is what committed files
say (scene names, sizes and SHA-256 values; quoted sentences; figures). And nothing in the code treats it as
confirmed: the rights registry, the flood-input loader and the builders refuse today exactly what they refused
before the drafts existed. Whoever records an owner's answer changes the record and these tests in one commit.

Nothing here opens a flood layer or computes a value for a real unit. The tests read committed receipts and
tables, the two signed protocol files, and invented copies written into a temporary folder.
"""

from __future__ import annotations

import copy
import csv
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest

from floodguard import flood_inputs, rights, rights_basis
from floodguard.rights import RegisteredRecord, RightsRefusedError, RightsRegistry
from floodguard.wording_lint import json_strings, lint_texts, load_rules, markdown_section, python_strings

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUTS = ROOT / "outputs" / "planning_v1"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")

RECORD_PATH = DOCS / "rights_basis_sentinel1_v1.json"
NOTICE_PATH = DOCS / "rights_basis_sentinel1_v1_NOTICE.txt"
AGE_REVIEW_PATH = DOCS / "age_data_purpose_review_v1.md"
WINDOW_PATH = DOCS / "walking_build_compute_window_v1.md"
DRAFTS = (RECORD_PATH, NOTICE_PATH, AGE_REVIEW_PATH, WINDOW_PATH)

V1A = json.loads((DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
V1B = json.loads((DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
OWNERS = ["Putu", "Rachmania"]
CREDIT = "Contains modified Copernicus Sentinel data 2024"
SHA256 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
# A drive letter that is not the end of a web address scheme, or a home folder.
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|\\Users\\|/home/")
CODE_FOLDERS = ("src", "scripts", "services", "apps/web/src", "apps/web/scripts")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs")
NOT_SOURCE = {"node_modules", ".venv", "__pycache__", ".next", "dist"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def text_of(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def script(name: str) -> Any:
    """Load a script of the repository as a module, once, under the name the other test files load it by."""

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs, because its dataclasses look their module up by name.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def code_files() -> tuple[tuple[str, str], ...]:
    """The code of the repository outside the tests: ``(path, text)`` of every script, module and web source file."""

    found = []
    for folder in CODE_FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.suffix in CODE_SUFFIXES and path.is_file() and NOT_SOURCE.isdisjoint(path.parts):
                found.append((path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8", errors="ignore")))
    return tuple(found)


def code_that_names(word: str) -> list[str]:
    """Every code file that names ``word``: a file that no code names is a file that no code reads."""

    assert len(code_files()) > 200
    return [name for name, text in code_files() if word in text]


def signature_rows(text: str, heading: str) -> list[list[str]]:
    """The rows of the signature table under ``heading``, without the header row and the rule under it."""

    lines = [line for line in markdown_section(text, heading).splitlines() if line.startswith("|")]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    assert rows[0][1:] == OWNERS and set("".join(rows[1])) <= set("-: "), "a table with one column for each owner"
    return rows[2:]


def unticked_options(text: str) -> list[tuple[str, str]]:
    return re.findall(r"^- \[(.)\] \*\*([A-Z])\.", text, flags=re.MULTILINE)


DRAFT = read_json(RECORD_PATH)
PROPOSED_ID = DRAFT["registration"]["proposed_input_id"]


def registered_as_sentinel1(root: Path, record: dict) -> RightsRegistry:
    """An invented registry (never the real one) that lists ``record`` as a record of Sentinel-1 data."""

    path = root / "docs" / "record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return RightsRegistry(root, (RegisteredRecord(PROPOSED_ID, "docs/record.json", "an invented entry", rights.SOURCE_SENTINEL1),))


# --- All three: drafts in the shared wording, with no machine path -------------------------------------------


def test_the_drafts_pass_the_shared_wording_lint_and_name_no_machine_path() -> None:
    items = [(f"{RECORD_PATH.name} {path}", text) for path, text in json_strings(DRAFT)]
    assert len(items) > 100
    items += [(path.name, text_of(path)) for path in DRAFTS[1:]]
    assert [finding.describe() for finding in lint_texts(items, RULES)] == []
    # The standing denials are really there, so passing is not an empty result.
    assert "not legal advice and not an official warning" in text_of(NOTICE_PATH)
    assert "ไม่ใช่การเตือนภัยอย่างเป็นทางการ" in text_of(NOTICE_PATH) and "not validated" in text_of(NOTICE_PATH)
    for path in DRAFTS:
        data = path.read_bytes()
        assert b"\r" not in data and data.endswith(b"\n"), f"{path.name}: LF line endings"
        assert not LOCAL_PATH.search(data.decode("utf-8")), f"{path.name} names a path on one machine"


# --- 1. The Sentinel-1 rights record (open point E1-OP2) ------------------------------------------------------


def test_the_sentinel1_record_is_a_draft_that_nobody_has_confirmed() -> None:
    assert DRAFT["schema"] == "floodguard.rights_basis_sentinel1.v1" != rights_basis.RIGHTS_BASIS_4009_SCHEMA
    assert DRAFT["record_status"] == rights_basis.RECORD_STATUS_BY_CONFIRMATION["pending"] == "draft_pending_owner_confirmation"
    assert DRAFT["record_status_text"] == "draft, pending confirmation by both owners"
    confirmation = DRAFT["owner_confirmation"]
    assert confirmation["status"] == "pending" and confirmation["required_from"] == OWNERS
    assert confirmation["confirmed_by"] == [] and confirmation["confirmed_on"] is None
    assert DRAFT["signed_by_human"] is False and DRAFT["human_rights_clearance"] is False
    assert DRAFT["signed_decision"] is None and DRAFT["publication_scope"]["chosen"] is None
    assert DRAFT["publication_scope"]["status"] == "pending_owner_choice"
    assert [option["id"] for option in DRAFT["publication_scope"]["options"]] == ["A", "B"]
    assert DRAFT["registration"]["registered"] is False
    assert rights_basis.owner_confirmed(DRAFT) is False
    with pytest.raises(rights_basis.RightsNotConfirmedError, match="not confirmed by the owners"):
        rights_basis.require_owner_confirmation(DRAFT)
    assert DRAFT["official_warning"] is False and DRAFT["operational_status"] == "non_operational"
    assert DRAFT["can_feed_decision_layer"] is False and DRAFT["not_legal_advice"] is True
    # Every output carries its source timestamp, its confidence and its assumptions.
    assert DRAFT["source_timestamp"] and DRAFT["confidence"] in ("high", "medium", "low") and DRAFT["confidence_reason"].strip()
    assert DRAFT["assumptions"] and DRAFT["limitations"] and all(item.strip() for item in DRAFT["assumptions"] + DRAFT["limitations"])

    notice = text_of(NOTICE_PATH)
    assert DRAFT["licence_notice_file"] == NOTICE_PATH.relative_to(ROOT).as_posix()
    assert RECORD_PATH.relative_to(ROOT).as_posix() in notice
    assert "STATUS: DRAFT, PENDING CONFIRMATION BY BOTH OWNERS" in notice and "STATUS: CONFIRMED" not in notice
    # The Thai half says the same of its status, and that no native speaker has read it (decision R18).
    assert "สถานะ: ฉบับร่าง รอการยืนยันจากเจ้าของโครงการทั้งสองคน" in notice and "ยังไม่ได้ตรวจทานโดยเจ้าของภาษา" in notice
    assert DRAFT["required_attribution_text"] == CREDIT and notice.count(CREDIT) == 2


def test_the_scenes_are_the_two_archives_the_radar_receipts_and_the_manifest_name() -> None:
    scenes = {scene["role"]: scene for scene in DRAFT["scenes"]}
    assert sorted(scenes) == ["post_event", "pre_event"]
    basis = DRAFT["scene_identity_basis"]
    for key in ("radar_receipt", "sensitivity_receipt"):
        receipt_path = ROOT / basis[key]["path"]
        assert sha256(receipt_path) == basis[key]["sha256"], (
            f"{basis[key]['path']} changed since the record was drafted: read it again, bring the record up to date and, "
            "if the owners had confirmed the record, ask them again")
        receipt = read_json(receipt_path)
        for role, scene in scenes.items():
            named = receipt["inputs"][f"{role}_safe"]
            assert (Path(named["path"]).name, named["sha256"], named["bytes"]) == (scene["file_name"], scene["sha256"], scene["bytes"])
            assert named["matches_the_acquisition_manifest"] is True
    stamps = read_json(ROOT / basis["radar_receipt"]["path"])["source_timestamps"]
    assert scenes["pre_event"]["acquisition_start_utc"] == stamps["pre_event_image_utc"]
    assert scenes["post_event"]["acquisition_start_utc"] == stamps["post_event_image_utc"]
    assert scenes["post_event"]["acquisition_in_thailand"] == stamps["post_event_image_in_thailand"]
    assert DRAFT["source_timestamp"] == f"{stamps['pre_event_image_utc']}/{stamps['post_event_image_utc']}"

    manifest_path = ROOT / basis["acquisition_manifest_in_git"]["path"]
    assert (sha256(manifest_path), manifest_path.stat().st_size) == (
        basis["acquisition_manifest_in_git"]["sha256"], basis["acquisition_manifest_in_git"]["bytes"])
    with manifest_path.open(encoding="utf-8", newline="") as source:
        rows = {row["product_name"]: row for row in csv.DictReader(source)}
    assert set(rows) == {scene["product_name"] for scene in scenes.values()}
    notice = text_of(NOTICE_PATH)
    for scene in scenes.values():
        row = rows[scene["product_name"]]
        assert (row["product_id"], row["sha256"], int(row["file_size_bytes"])) == (
            scene["catalogue_product_id"], scene["sha256"], scene["bytes"])
        assert row["source_license_status"] == "confirmed_copernicus_sentinel_legal_notice"
        # The note the record puts to the owners (open point A4-OP5) is really in the manifest.
        assert row["processing_allowed"] == "False" and "reference mask status is unresolved" in row["reason_blocked"]
        assert row["download_attempted"] == "False" and row["retrieved_at_utc"] == "2026-07-20T07:00:00Z"
        assert scene["file_name"] == scene["product_name"] + ".zip" and scene["relative_path"].endswith("/" + scene["file_name"])
        assert scene["kept_outside_git"] is True and ".." not in Path(scene["relative_path"]).parts
        assert (scene["pass"], scene["relative_orbit"]) == ("descending", 135)
        # Both halves of the notice name the scene, its size and its SHA-256.
        assert notice.count(scene["product_name"]) == 2 and notice.count(scene["sha256"]) == 2
        assert notice.count(f"{scene['bytes']:,}") == 2 and notice.count(scene["catalogue_product_id"]) == 2
    table = read_json(OUTPUTS / "radar_o1_mae_sai_v1.json")
    assert {table["image_pair"][key]["product"] for key in ("pre", "post")} == set(rows)
    assert {(table["image_pair"][key]["pass"], table["image_pair"][key]["relative_orbit"]) for key in ("pre", "post")} == {("descending", 135)}
    # Protocol v1a gives case O1 this acquisition and no other.
    case = next(item for item in V1A["case_portfolio"]["cases"] if item["id"] == "O1")
    assert case["input_acquisition"] == "Sentinel-1, 16 Sep 2024 06:16 ICT"


def test_the_record_states_no_term_without_a_repository_file_behind_it() -> None:
    licence = DRAFT["licence"]
    assert licence["name"] == DRAFT["legal_notice_title"] and licence["url"] == DRAFT["legal_notice_url"]
    sentinel2 = read_json(DOCS / "automated_track" / "rights_basis_v1.json")
    assert (DRAFT["legal_notice_title"], DRAFT["legal_notice_url"]) == (sentinel2["legal_notice_title"], sentinel2["legal_notice_url"])
    assert DRAFT["required_attribution_text"] == sentinel2["required_attribution_text"] == CREDIT

    cited = set()
    for term in licence["terms_as_the_repository_records_them"]:
        assert term["term"].strip() and term["recorded_in"]
        for entry in term["recorded_in"]:
            relative = entry.split(" ")[0]
            assert (ROOT / relative).is_file(), f"{relative} is cited and is not in the repository"
            cited.add(relative)
    log = text_of(ROOT / "docs" / "reference_mask_licensing_log.md")
    dossier = text_of(DOCS / "GATE_RESEARCH_DOSSIER.md")
    # The sentences the record takes its terms from are in the files it cites.
    assert DRAFT["legal_notice_url"] in log and DRAFT["legal_notice_url"] in dossier
    assert f"`{CREDIT}`" in log and "`Copernicus Sentinel data 2024`" in log and "Primary Sources Rechecked 2026-07-20" in log
    assert "https://dataspace.copernicus.eu/terms-and-conditions" in log
    assert "1159/2013" in dossier and "It\ngives no warranty of fitness" in dossier
    for use in sentinel2["permitted_lawful_uses"].values():
        assert use.split(",")[0] in licence["terms_as_the_repository_records_them"][0]["term"]
    assert "Copernicus Sentinel data terms (free, full and open)" in text_of(ROOT / "scripts" / "build_mae_sai_flood_timeline.py")
    assert f'"attribution": "{CREDIT}"' in text_of(ROOT / "scripts" / "build_mae_sai_radar_candidates.py")
    assert {"docs/reference_mask_licensing_log.md", "docs/proposal_execution/GATE_RESEARCH_DOSSIER.md",
            "docs/proposal_execution/SOURCES_AND_RIGHTS.md", "scripts/build_mae_sai_flood_timeline.py"} <= cited

    # What no repository file settles is put to the owners, each point with the page to check it against.
    to_check = licence["to_be_checked_by_the_owners_against_the_providers_page"]
    assert len(to_check) >= 5 and all(item["what"].strip() and item["page"].strip() for item in to_check)
    pages = " ".join(item["page"] for item in to_check)
    assert DRAFT["legal_notice_url"] in pages and "https://dataspace.copernicus.eu/terms-and-conditions" in pages
    assert "Nothing was quoted from memory" in " ".join(licence["notes"])
    # One phrase for these terms is in no other file of the repository, and the record says so; it states no term from it.
    assert any("Copernicus data and information policy" in item["what"] and "in no other file of the repository" in item["what"]
               for item in to_check)
    assert not [name for name, text in code_files() if "data and information policy" in text]

    notice = DRAFT["change_notice"]
    assert notice["template"].startswith("Changed by FloodGuard:") and notice["template"].endswith(CREDIT + ".")
    assert [step["id"] for step in notice["steps"]] == [
        "calibration", "geocoding", "resampling", "frame", "comparison_and_classification", "tier_label"]
    assert all(step["text"].strip() for step in notice["steps"]) and len(notice["what_a_change_notice_must_say"]) >= 4
    for placeholder in re.findall(r"\{([a-z_0-9]+)\}", notice["template"]):
        assert placeholder in ("calibration", "geocoding", "cell_size_m", "target_crs", "frame", "pre_event_date",
                               "post_event_date", "method")

    # The decisions the record cites are rows of the decision log, and it attributes no decision on Sentinel-1 rights.
    decisions = text_of(ROOT / "docs" / "decision-log-d1-d16.md")
    for reference in DRAFT["decision_refs"]:
        assert re.search(rf"^\| {reference['id']} \|", decisions, flags=re.MULTILINE), reference["id"]
    assert "gates the finals baseline only, not rights" in decisions
    assert "rights_basis_sentinel1" not in decisions and "No row of the decision log" in DRAFT["signed_decision_note"]


def test_the_rights_registry_still_refuses_sentinel1_data_while_the_record_is_pending(tmp_path: Path) -> None:
    """Open point E1-OP2 is not closed by a draft: the registry is as it was, and the draft alone opens nothing."""

    assert [entry.input_id for entry in rights.REGISTERED_RECORDS] == [rights.PRODUCT_4009, rights.SENTINEL2_AUTOMATED_TRACK]
    assert rights.SOURCE_SENTINEL1 not in {entry.source for entry in rights.REGISTERED_RECORDS}
    assert RECORD_PATH.relative_to(ROOT).as_posix() not in {entry.record_path for entry in rights.REGISTERED_RECORDS}
    registry = RightsRegistry(ROOT)
    assert PROPOSED_ID not in registry.input_ids() and DRAFT["registration"]["proposed_source"] == rights.SOURCE_SENTINEL1
    for call in (registry.require_use, registry.require_public_write):
        with pytest.raises(RightsRefusedError, match="no rights record is registered"):
            call(PROPOSED_ID)
    with pytest.raises(RightsRefusedError, match="no rights record is registered"):
        registry.require_use(PROPOSED_ID, source=rights.SOURCE_SENTINEL1)
    # No code names the draft, so no code reads it.
    assert code_that_names("rights_basis_sentinel1") == []

    # Registered exactly as it is drafted, the record is still refused: nobody signed it.
    as_drafted = registered_as_sentinel1(tmp_path / "as_drafted", DRAFT)
    for call in (as_drafted.require_use, as_drafted.require_public_write):
        with pytest.raises(RightsRefusedError, match="not signed by a human"):
            call(PROPOSED_ID)
    # The two flags alone do not confirm it, and neither does one owner.
    flags_only = {**copy.deepcopy(DRAFT), "signed_by_human": True, "human_rights_clearance": True}
    with pytest.raises(RightsRefusedError, match="not confirmed by the owners"):
        registered_as_sentinel1(tmp_path / "flags_only", flags_only).require_use(PROPOSED_ID, source=rights.SOURCE_SENTINEL1)
    one_owner = copy.deepcopy(flags_only)
    one_owner["record_status"] = "confirmed"
    one_owner["owner_confirmation"].update(status="confirmed", confirmed_by=["Putu"], confirmed_on="2030-01-01")
    with pytest.raises(RightsRefusedError, match="is missing: Rachmania"):
        registered_as_sentinel1(tmp_path / "one_owner", one_owner).require_use(PROPOSED_ID, source=rights.SOURCE_SENTINEL1)


def test_the_draft_holds_what_a_confirmed_record_needs_and_would_give_the_local_level_only(tmp_path: Path) -> None:
    """An invented confirmation in a temporary folder, never written into the repository: what the record says it would allow."""

    confirmed = copy.deepcopy(DRAFT)
    confirmed.update(record_status="confirmed", signed_by_human=True, human_rights_clearance=True)
    confirmed["owner_confirmation"].update(status="confirmed", confirmed_by=list(OWNERS), confirmed_on="2030-01-01")
    registry = registered_as_sentinel1(tmp_path, confirmed)
    grant = registry.require_use(PROPOSED_ID, source=rights.SOURCE_SENTINEL1)
    assert grant.attribution == CREDIT and grant.licence["name"] == DRAFT["legal_notice_title"]
    assert grant.licence["url"] == DRAFT["legal_notice_url"] and grant.record_id == "rights_basis_sentinel1_v1"
    assert grant.confirmed_by == tuple(OWNERS) and grant.source == rights.SOURCE_SENTINEL1
    assert grant.share_alike == DRAFT["share_alike"] and grant.share_alike.startswith("None recorded.")
    # The level the record states for itself is the level the code would give: local, and no public write.
    would_allow = DRAFT["would_allow_once_confirmed_and_registered"]
    assert grant.rights_level == would_allow["rights_level"] == DRAFT["publication_scope"]["level_the_code_gives_today"] == rights.LOCAL_LEVEL
    with pytest.raises(RightsRefusedError, match="rights level 'local'"):
        registry.require_public_write(PROPOSED_ID)
    assert any("apps/web/public/" in item for item in DRAFT["would_not_allow"])
    assert DRAFT["publication_scope"]["options"][1]["level"] == "public" and "reviewed change to floodguard.rights" in (
        DRAFT["publication_scope"]["options"][1]["text"])
    # The record names the open points it touches, and closes E1-OP2 only once confirmed and registered.
    touched = {item["id"]: item["effect"] for item in DRAFT["open_points_this_record_touches"]}
    assert set(touched) == {"E1-OP2", "A1-OP5", "A4-OP5", "E1-OP1", "A4-OP1"}
    assert "only once the record is confirmed and registered" in touched["E1-OP2"] and "A6-prime" in touched["E1-OP2"]
    readme = text_of(OUTPUTS / "README.md")
    for point in touched:
        assert point in readme, f"{point} is not an open point of outputs/planning_v1/README.md"


def test_the_loader_and_the_assessment_builder_still_refuse_case_o1(tmp_path: Path) -> None:
    """``load_o1`` and the planning-assessment builder say today what they said before the draft existed."""

    rules = flood_inputs.load_rules(DOCS / "planning_protocol_v1a.json", DOCS / "planning_protocol_v1b.json", DOCS / "RECEIPTS.jsonl")
    # An invented candidate receipt that names the draft's proposed registry key. No raster is written: the
    # registry is asked before any raster is opened.
    receipt = {
        "schema_version": flood_inputs.RADAR_RECEIPT_SCHEMA, "case_id": "O1", "candidate_id": "UN-SPIDER reproduction",
        "rights_input_id": PROPOSED_ID, "acquisition_time_utc": "2024-09-15T23:16:01Z", "acquisition_date": "2024-09-16",
        "level_kind": flood_inputs.ONE_PIXEL_LEVELS, "level_parameter": "one pixel on the output extent",
        "rasters": {flood_inputs.AS_PROVIDED: {"path": "no_such_raster.tif", "sha256": "0" * 64}},
        "encoding": {"flood": 1, "not_flood": 0, "no_answer": 255}, "protocol_sha256": flood_inputs.protocol_hashes(rules),
        "inputs": {"scene": {"sha256": "1" * 64}}, "source_timestamp": "2024-09-15T23:16:01Z",
        "generated_at_utc": "2030-01-01T00:00:00Z", "confidence_class": "low", "confidence_basis": "An invented candidate.",
        "assumptions": ["An invented candidate: it has no raster."], "official_warning": False,
        "operational_status": "non_operational",
    }
    assert set(receipt) == set(flood_inputs.RADAR_RECEIPT_KEYS)
    receipt_path = tmp_path / "candidate_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(RightsRefusedError, match="no rights record is registered"):
        flood_inputs.load_o1(receipt_path, [], rules=rules, registry=RightsRegistry(ROOT))
    with pytest.raises(RightsRefusedError, match="not signed by a human"):
        flood_inputs.load_o1(receipt_path, [], rules=rules, registry=registered_as_sentinel1(tmp_path / "as_drafted", DRAFT))

    runner = script("build_planning_assessment")
    mae_sai = runner.FRAME_SETS["mae_sai"]
    assert mae_sai.not_run["O1"].rights_source == rights.SOURCE_SENTINEL1 and mae_sai.not_run["O1"].open_point == "E1-OP2"
    outside = tmp_path / "no_external_data"
    with pytest.raises(runner.BuildError) as refused:
        runner.build("O1", mae_sai, outside, outside / "no-boundaries", generated_at_utc="2030-01-01T00:00:00Z", git_commit="0123abc")
    assert str(refused.value) == (
        "case O1 cannot be run: the registered E1 receipt binds no flood input of case O1; the registered E5 receipt "
        "binds no access table of case O1; the rights registry holds no record of Sentinel-1 data (open point E1-OP2)")
    assert not outside.exists()


# --- 2. The purpose review of the 2024 age counts (open point E8-OP5) --------------------------------------------


def test_the_age_review_is_pending_with_no_option_ticked_and_an_empty_signature_block() -> None:
    review = text_of(AGE_REVIEW_PATH)
    assert re.search(r"^Status: \*\*PENDING\*\* \(draft, pending an answer from both owners\)$", review, flags=re.MULTILINE)
    assert unticked_options(review) == [(" ", "A"), (" ", "B"), (" ", "C")]
    for option in ("**A. Confirm for public use.**", "**B. Confirm for pitch use only.**", "**C. Decline.**"):
        assert option in review
    rows = signature_rows(review, "## 9. Signature block")
    assert [row[0] for row in rows][0] == "Option chosen (A, B or C)" and len(rows) == 4
    assert all(row[1:] == ["", ""] for row in rows), "the signature block is left empty"
    assert "Decision-log row: _none yet_" in review
    # Source timestamp, confidence and assumptions (AGENTS.md, technical principle 3).
    about = markdown_section(review, "## 10. About this page")
    assert "**Source timestamp:**" in about and "**Confidence: low.**" in about and "**Assumptions:**" in about
    # The risks the review was asked to consider, and the mitigations that are already in the design.
    risks = markdown_section(review, "## 5. Risks considered")
    for heading in ("**5.1 Re-identification from a tambon aggregate.**", "**5.2 Misuse as a statement about individuals.**", "**5.3 Stigma.**"):
        assert heading in risks
    mitigations = markdown_section(review, "## 6. Mitigations")
    for words in ("**Tambon aggregates only.**", "**GR1: no class under 100 residents.**", "**Labels on the data.**", "**Not in the design today.**"):
        assert words in mitigations
    # The decision log records no answer, and the review attributes none.
    assert "age_data_purpose_review" not in text_of(ROOT / "docs" / "decision-log-d1-d16.md")


def test_the_age_review_quotes_the_signed_files_and_the_committed_tables_exactly() -> None:
    review = text_of(AGE_REVIEW_PATH)
    rasters = V1B["national_vulnerability_anchors"]["inputs"]["age_rasters"]
    assert rasters["rights"] == "Public catalog says CC BY 4.0. Public derivatives require purpose-specific review."
    assert f"> {rasters['rights']}" in review and review.count(rasters["rights"]) == 2
    assert "`national_vulnerability_anchors.inputs.age_rasters.rights`" in review
    assert rasters["manifest_sha256"] in review and f"{rasters['total_bytes']:,} bytes" in review
    assert "WorldPop Global2 R2025A v1, Thailand, 2024, constrained total-sex age counts" in rasters["product"]
    assert "WorldPop Global2 R2025A v1, Thailand, 2024, constrained total-sex age counts" in review
    acquire = text_of(ROOT / "scripts" / "acquire_worldpop_age.py")
    quoted = "Public catalog says CC BY 4.0; ODbL may apply to OSM/building-derived datasets. Public derivatives require purpose-specific review."
    assert quoted in acquire and quoted in " ".join(review.split())
    for address in ("https://hub.worldpop.org/geodata/summary?id=", "https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf"):
        assert address in acquire and address in review
    assert "hosted age derivatives still await product-specific" in text_of(DOCS / "SOURCES_AND_RIGHTS.md")
    assert "hosted age derivatives still await product-specific" in " ".join(review.split())

    flat = " ".join(review.split())
    gr1 = next(item for item in V1A["guardrails"] if item["id"] == "GR1_minimum_denominators")
    assert f'"{gr1["rule"]}"' in flat and gr1["parameters"]["unit_residents_min_for_class"] == 100
    component = V1A["scoring_frame"]["components"]["vulnerability_context_0_100"]
    assert f'"{component["caveat"]}"' in flat
    values = V1B["national_vulnerability_anchors"]["values"]
    assert f"P10 = {values['P10']} and P90 = {values['P90']}" in flat
    assert "Class E never means safe" in V1A["wording"]["class_e_wording"] and '"Class E never means safe"' in flat

    readme = " ".join(text_of(OUTPUTS / "README.md").split())
    for sentence in (
        "The owners record the review, or say that it is not needed for these derivatives, and their answer has to cover the E7 table that is already committed",
        "the FPPS and the binding class of each SE1 tambon can be worked out from committed files",
        "one age composition per district, applied to every cell of the district",
    ):
        assert sentence in readme and sentence in flat

    # Figures read from the committed age table: nothing is computed, the table's own numbers are set beside the text.
    table = read_json(OUTPUTS / "age_exposure_mae_sai_v1.json")
    receipt = read_json(OUTPUTS / "age_exposure_mae_sai_v1_receipt.json")
    assert receipt["inputs"]["age_acquisition_manifest"]["sha256"] == rasters["manifest_sha256"]
    assert sum(item["bytes"] for item in receipt["inputs"]["age_rasters"].values()) == rasters["total_bytes"]
    assert table["generated_at_utc"] == "2026-10-04T09:12:35Z" and "09:12:35 UTC" in review
    residents = {unit["unit_id"]: unit["residents"] for unit in table["units"]}
    smallest = min(residents, key=residents.get)
    assert f"{round(residents[smallest]):,} modelled residents in the 2024 age table ({smallest})" in flat
    assert f"The largest has {round(max(residents.values())):,}." in flat
    # The 2020 figure beside it is the smallest of the SE1 table of the README, and it is that tambon's.
    table_2020 = {code: int(count.replace(",", "")) for code, count in re.findall(r"^\| (TH\d{6}) [^|]+\| ([\d,]+) \| [\d.]+ \|", text_of(OUTPUTS / "README.md"), flags=re.MULTILINE)}
    assert len(table_2020) == 8 and min(table_2020, key=table_2020.get) == smallest
    assert f"and {table_2020[smallest]:,} in WorldPop 2020" in flat
    cells = [unit["age_cells"]["with_valid_counts"] for unit in table["units"]]
    assert f"from {min(cells)} to {max(cells)} one-kilometre cells" in flat
    inside = {round(unit["allocation_range"]["cells_wholly_inside"]["dependent_share"], 6) for unit in table["units"]}
    assert inside == {0.405551} and "the same share, 0.405551" in flat
    assert round(table["age_grid_reading"]["whole_grid"]["same_share_groups"]["share_of_populated_cells"], 3) == 0.894 and "89.4%" in flat
    assert sum(1 for unit in table["units"] if unit["cells_partly_outside_every_unit"]["cells"] > 0) == 4 and "Four of the eight tambons" in flat
    assert all(value > gr1["parameters"]["unit_residents_min_for_class"] for value in residents.values())
    assert "CC BY" not in text_of(OUTPUTS / "age_exposure_mae_sai_v1.json") and "carries no licence line of its own" in flat


def test_the_builders_still_hold_the_age_counts_at_the_local_level() -> None:
    """Open point E8-OP5 is not closed by a draft: the level is in the code and the code has not changed."""

    runner = script("build_planning_assessment")
    lineage = runner.FRAME_SETS["mae_sai"].lineage
    age = lineage["age_structure"]
    assert age.rights_level == rights.LOCAL_LEVEL
    assert "purpose-specific review" in age.rights_level_basis and "No such review is recorded in the repository" in age.rights_level_basis
    assert rights.minimum_level(item.rights_level for item in lineage.values()) == rights.LOCAL_LEVEL
    assert {key for key, item in lineage.items() if item.rights_level != rights.PUBLIC_LEVEL} == {"age_structure"}
    # No code names the review, so no answer can be read from it.
    assert code_that_names("age_data_purpose_review") == []
    # The committed runs say the same: the age table is the one input that keeps case SE1 below the public level.
    for name, below_public in (("e8_planning_assessment_se1_mae_sai.json", {"e7_age_exposure_table"}),
                               ("e10_uncertainty_ensemble_se1_mae_sai.json", {"e7_age_exposure_table"})):
        run_rights = read_json(OUTPUTS / name)["rights"]
        assert run_rights["publication_eligibility"] == rights.LOCAL_LEVEL and run_rights["written_under_apps_web_public"] is False
        assert {key for key, level in run_rights["lineage_levels"].items() if level != rights.PUBLIC_LEVEL} == below_public
    o2 = read_json(OUTPUTS / "e8_planning_assessment_o2_mae_sai.json")["rights"]
    assert o2["publication_eligibility"] == rights.LOCAL_LEVEL and o2["lineage_levels"]["e7_age_exposure_table"] == rights.LOCAL_LEVEL
    # Nothing of the planning assessment is under the public web folder.
    public = ROOT / rights.PUBLIC_WEB_ROOT
    assert not [path.name for path in public.rglob("*planning_assessment*")] and not [path.name for path in public.rglob("*age_exposure*")]


# --- 3. The compute window of a walking context build of record (open point E5-OP5) ----------------------------


def test_the_window_declaration_is_pending_with_no_option_ticked_and_an_empty_signature_block() -> None:
    declaration = text_of(WINDOW_PATH)
    assert re.search(r"^Status: \*\*PENDING\*\* \(draft, pending acceptance by both owners\)$", declaration, flags=re.MULTILINE)
    assert "**No build was run for this page, and none will be run until you accept a window.**" in declaration
    assert unticked_options(declaration) == [(" ", "A"), (" ", "B"), (" ", "C")]
    rows = signature_rows(declaration, "## 10. Signature block")
    assert len(rows) == 4 and all(row[1:] == ["", ""] for row in rows), "the signature block is left empty"
    assert "Decision-log row: _none yet_" in declaration
    about = markdown_section(declaration, "## 11. About this page")
    assert "**Source timestamp:**" in about and "**Confidence: low**" in about and "**Assumptions:**" in about

    flat = " ".join(declaration.split())
    # The plan's rule, as protocol v1b carries it, and the two decisions the page rests on, in their own words.
    rule = "Builds run serially in a declared compute window with no concurrent SNAP jobs"
    assert V1B["corridor_polygon"]["compute_window"].startswith(rule) and f'"{rule}."' in flat
    decisions = text_of(ROOT / "docs" / "decision-log-d1-d16.md")
    accepted = "in advance that the agent declares the E4 build's window on the same terms: no other project job running, and the window recorded"
    assert accepted in decisions and f'"{accepted}"' in flat
    assert "walking_build_compute_window" not in decisions, "the decision log records no acceptance of a walking window"
    readme = " ".join(text_of(OUTPUTS / "README.md").split())
    asked = ("The owners are asked for a walking build of record in a declared window they accept, with its receipt here; "
             "then task E5 is run again. Until then the shelter tables are not inputs of task E8.")
    assert asked in readme and f'"{asked}"' in flat
    shelters = V1B["facility_sets"]["shelters_in_the_ensemble"]
    assert "the shelter service is walking, 30 minutes" in shelters["status"] and '"the shelter service is walking, 30 minutes"' in flat
    # The sentence the owners would confirm names the page, the terms of R13 and the condition the drafter proposes.
    sentence = " ".join(line.lstrip("> ").strip() for line in declaration.splitlines() if line.lstrip().startswith(">"))
    assert sentence.startswith("We accept in advance that the AI coding agent declares one compute window for one walking build of record")
    assert WINDOW_PATH.relative_to(ROOT).as_posix() in sentence and "decision R13" in sentence
    assert sentence.endswith("Any difference comes back to us before anything is built on it.")


def test_every_figure_of_the_declaration_is_the_one_a_committed_file_records() -> None:
    declaration = text_of(WINDOW_PATH)
    flat = " ".join(declaration.split())
    report = read_json(OUTPUTS / "e5_walking_context_build_report_se1_mae_sai.json")
    vehicle = read_json(OUTPUTS / "e4_planning_context_se1_vehicle.json")
    e5 = read_json(OUTPUTS / "e5_access_diff_mae_sai.json")

    inputs = report["inputs"]["files_sha256"]
    assert inputs == vehicle["input_hashes"] and report["inputs"]["same_input_files_as_the_vehicle_context_of_record"] is True
    assert len(inputs) == 8 and all(value in declaration for value in inputs.values())
    assert sha256(ROOT / "resources" / "aoi" / "aoi-02_mae_sai_district.geojson") == inputs["aoi_02_sha256"]
    assert sha256(OUTPUTS / "corridor_of_record.geojson") == inputs["routing_file_sha256"] == report["inputs"]["routing_source"]["sha256"]

    # "Today's builder is the builder that made the candidate": the files on disk have the SHA-256 the build named.
    implementation = {key: value for key, value in report["implementation"].items() if key.endswith("_sha256")}
    on_disk = {"builder_sha256": ROOT / "scripts" / "build_planning_context.py",
               **{f"{name}_sha256": ROOT / "src" / "floodguard" / f"{name}.py"
                  for name in ("planning_context", "evidence_context", "grade_join", "ddpm_shelters", "shelter_corroboration", "hospital_counts")}}
    assert set(on_disk) == set(implementation)
    for key, path in on_disk.items():
        assert sha256(path) == implementation[key], (
            f"{path.relative_to(ROOT).as_posix()} is no longer the file the candidate walking build named: section 3 of "
            "the declaration says it is, so bring the declaration up to date before the owners read it")
        assert f"| `{path.relative_to(ROOT).as_posix()}` | `{implementation[key]}` |" in declaration

    protocols = report["protocol_sha256"]
    assert protocols == {f"planning_protocol_{name}": sha256(DOCS / f"planning_protocol_{name}.json") for name in ("v1a", "v1b")}
    context = next(item for item in report["outputs"] if item["what"] == "context")
    counts = report["counts"]
    known = {*inputs.values(), *implementation.values(), *protocols.values(), context["canonical_sha256"], counts["joins_sha256"]}
    assert set(SHA256.findall(declaration)) == known, "every SHA-256 on the page is one a committed file records, and none is missing"

    stamps = report["timestamps"]
    assert (stamps["build_started_at_utc"], stamps["build_finished_at_utc"]) == ("2026-10-04T13:07:10Z", "2026-10-04T13:09:33Z")
    assert "4 October 2026, 13:07:10 to 13:09:33 UTC | **2.38 minutes**" in flat and stamps["wall_time_minutes"] == 2.38
    run = vehicle["run"]
    assert (run["wall_time_minutes"], run["peak_working_set_gib"]) == (2.21, 0.58)
    assert "2.21 minutes; the Python process peaked at 0.58 GiB" in flat
    window = V1B["corridor_polygon"]["e4_build_of_record"]["compute_window"]
    assert (window["window_start_local"][11:19], window["window_end_local"][11:19]) == ("13:26:50", "13:29:08")
    assert (window["run_started_local"][11:19], window["run_finished_local"][11:19]) == ("13:26:53", "13:29:06")
    assert "2 minutes 18 seconds long for a build of 2 minutes 13 seconds" in flat
    assert e5["timestamps"]["wall_time_minutes"] == 19.53 and "its last run took 19.53" in flat

    assert f"| Grade joins | {counts['grade_join_connectors']}, joins SHA-256 `{counts['joins_sha256']}` |" in declaration
    assert f"{counts['edges']:,}; {counts['road_nodes']:,}; {counts['demand_cells']:,}" in declaration
    assert f"| {counts['located_ddpm_shelters_supplied']}; {counts['supplied_shelters_snapped_within_100_m']} |" in declaration
    sentence = " ".join(line.lstrip("> ").strip() for line in declaration.splitlines() if line.lstrip().startswith(">"))
    assert f"the same {counts['grade_join_connectors']} grade joins" in sentence and f"{counts['edges']:,} edges" in sentence
    assert (f"{counts['supplied_shelters_snapped_within_100_m']} of the {counts['located_ddpm_shelters_supplied']} located shelters"
            in sentence)

    # The two files a build of record would write, and the cells it is needed for, are named as the code names them.
    builder = script("build_planning_context")
    case = builder.Case("se1", None, None, {}, None, {"case_id": builder.CASE_IDS["se1"]})
    paths = builder.output_paths(case, "walking", True, Path("external"))
    for key in ("receipt", "join_log"):
        assert f"`{paths[key].relative_to(ROOT).as_posix()}`" in declaration
    assert paths["processed"].as_posix() == "external/proposal_execution/planning_v1/se1_mae_sai/e4_walking"
    assert "`<external_data_workspace>/proposal_execution/planning_v1/se1_mae_sai/e4_walking/`" in flat
    grid = V1B["ensemble_grid"]
    assert grid["core_cells_per_lane"] == 540 and [axis["count"] for axis in grid["core_axes"]] == [3, 3, 3, 2, 2, 5]
    facilities = next(axis for axis in grid["core_axes"] if axis["axis"] == "facilities")
    # Two of the three facility levels add shelters: two thirds of the 540 cells.
    assert facilities["levels"] == ["public", "corroborated", "all_listed"] and grid["core_cells_per_lane"] // 3 * 2 == 360
    assert "**360 of the 540 ensemble cells of each lane**" in declaration


def test_no_walking_build_of_record_exists_and_nothing_treats_the_candidate_as_accepted(tmp_path: Path) -> None:
    """Open point E5-OP5 is not closed by a draft: the candidate is a candidate, and R13 covers the vehicle build only."""

    for name in ("e4_planning_context_se1_walking.json", "grade_join_log_e4_se1_walking.json"):
        assert not (OUTPUTS / name).exists(), f"{name}: a walking build of record was made while the declaration is pending"
    assert not [path.name for path in (OUTPUTS / "run_register").glob("*walking*") if "build_report" not in path.name]
    assert code_that_names("walking_build_compute_window") == []

    report = read_json(OUTPUTS / "e5_walking_context_build_report_se1_mae_sai.json")
    assert report["status"] == "candidate_context_build_reported_after_the_fact" and report["usable_by_task_e8"] is False
    assert report["parameters"]["run_kind"] == "candidate" and report["parameters"]["travel_mode"] == "walking"
    window = report["compute_window"]
    assert window["declared"] is False and window["declared_by_the_operator"] is None and window["authority"] is None
    e5 = read_json(OUTPUTS / "e5_access_diff_mae_sai.json")
    walking = e5["inputs"]["planning_context_walking"]
    assert (walking["status"], walking["run_kind"], walking["usable_by_task_e8"]) == ("candidate", "candidate", False)
    assert e5["shelter_service"]["context_status"] == "candidate" and e5["shelter_service"]["usable_by_task_e8"] is False

    # The E4 builder: R13 names the vehicle build of case se1 and no other; a walking window has no authority
    # unless the operator cites a decision-log row, and no row accepts one.
    builder = script("build_planning_context")
    assert builder.R13_CASE == ("se1", "legacy_vehicle")
    assert builder.window_authority("se1", "walking", cited=None, earlier_record=False) is None
    assert builder.window_authority("se1", "walking", cited="  ", earlier_record=False) is None
    assert builder.authority_note(None) == builder.AUTHORITY_NOTES["none"] and builder.AUTHORITY_NOTES["none"].startswith("Awaiting owner acceptance")
    assert "it does not cover this build" in builder.AUTHORITY_NOTES["none"]
    decisions = text_of(ROOT / "docs" / "decision-log-d1-d16.md")
    rows = [line for line in decisions.splitlines() if re.match(r"\| [DR]\d+[a-z]? \|", line)]
    assert len(rows) >= 34 and any("accept in advance that the agent declares the E4 build's window" in line for line in rows)
    assert not [line[:8] for line in rows if "walking" in line and ("window" in line or "build of record" in line)], (
        "a row of the decision log speaks of a walking build: bring the declaration and this test up to date with it")

    # The planning-assessment builder: no pitch-level run without the pitch table, which rests on the candidate.
    runner = script("build_planning_assessment")
    outside = tmp_path / "no_external_data"
    with pytest.raises(runner.BuildError, match="pitch_services table of case SE1"):
        runner.prepare("SE1", runner.FRAME_SETS["mae_sai"], outside, outside / "no-boundaries", level="pitch")
    assert not outside.exists()
    refusals = python_strings(text_of(ROOT / "scripts" / "build_planning_assessment.py"))
    assert any("level is not built yet" in text and "no walking context of record exists (open point E5-OP5)" in text for text in refusals)

    # What the declaration says the builders do today is what they do (section 8 of the page).
    declaration = " ".join(text_of(WINDOW_PATH).split())
    vehicle_receipt = text_of(OUTPUTS / "e4_planning_context_se1_vehicle.json")
    join_log = text_of(OUTPUTS / "grade_join_log_e4_se1_vehicle.json")
    v1a_sha256 = sha256(DOCS / "planning_protocol_v1a.json")
    assert v1a_sha256 not in vehicle_receipt and v1a_sha256 not in join_log and "protocol_v1b_sha256_at_build" in vehicle_receipt
    assert "outputs" not in json.loads(vehicle_receipt)
    assert "The E4 builder names protocol v1b only, and its join log names neither protocol." in declaration
    e5_source = text_of(ROOT / "scripts" / "build_access_diff.py")
    assert '"usable_by_task_e8": of_record,' in e5_source and 'of_record = receipt["run_kind"] == RECORD' in e5_source
    assert "authority" not in e5_source, (
        "section 8.2 of the declaration says task E5 does not read who accepted a window: if it now does, bring that "
        "section and this test up to date")
    assert "Task E5 does not look at who accepted a window." in declaration
